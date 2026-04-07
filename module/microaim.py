import pymem
import pymem.process
import ctypes
from ctypes import wintypes
import struct
import re
import time
import threading
import queue

from core.aim_detector import get_shared_detector
from core.menu_monitor import get_shared_menu_monitor


kernel32_dll = ctypes.WinDLL("kernel32", use_last_error=True)

PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT  = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000

SENS_SCAN_PATTERN = b'\xF3\x0F\x10\x40\x14\xC3\xCC'
SENS_ORIG_BYTES   = b'\xF3\x0F\x10\x40\x14'
SENS_PATCH_SIZE   = 5
FIXED_SENS_VALUE  = 0.001

class SensHook:
    def __init__(self, pm, process_handle,
                 VirtualProtectEx, VirtualAllocEx, VirtualFreeEx):
        self.pm               = pm
        self.process_handle   = process_handle
        self.VirtualProtectEx = VirtualProtectEx
        self.VirtualAllocEx   = VirtualAllocEx
        self.VirtualFreeEx    = VirtualFreeEx

        self.sens_addr     = None
        self._sens_newmem  = None
        self._float_addr   = None
        self._patch_bytes  = None
        self._pulse_lock   = threading.Lock()

        self.pulse_duration   = 0.1
        self.fixed_sens_value = FIXED_SENS_VALUE

    def _set_writable(self, addr: int, size: int) -> int:
        old = wintypes.DWORD()
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            size, PAGE_EXECUTE_READWRITE, ctypes.byref(old)
        )
        return old.value

    def _restore_protect(self, addr: int, size: int, old_prot: int):
        dummy = wintypes.DWORD()
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            size, old_prot, ctypes.byref(dummy)
        )

    def scan(self) -> bool:
        try:
            module = pymem.process.module_from_name(
                self.process_handle, "Minecraft.Windows.exe"
            )
            if module is None:
                return False

            base = module.lpBaseOfDll
            size = module.SizeOfImage
            data = self.pm.read_bytes(base, size)
            matches = [
                m.start()
                for m in re.finditer(re.escape(SENS_SCAN_PATTERN), data)
            ]
            if not matches:
                return False
            self.sens_addr = base + matches[0]

            float_addr = self.VirtualAllocEx(
                self.process_handle, None, 8,
                MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
            )
            if not float_addr:
                return False
            self._float_addr = float_addr
            self.pm.write_bytes(
                float_addr, struct.pack("<f", self.fixed_sens_value), 4
            )

            self._build_patch_newmem()
            return True
        except Exception:
            return False

    def _build_patch_newmem(self):
        newmem = None
        base = self.sens_addr & 0xFFFFFFFFFFFF0000
        for offset in range(0x10000, 0x7FF00000, 0x10000):
            for direction in [1, -1]:
                addr = base + offset * direction
                if addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
                    continue
                try:
                    mem = self.VirtualAllocEx(
                        self.process_handle, ctypes.c_void_p(addr), 0x100,
                        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
                    )
                    if mem and abs(mem - self.sens_addr) < 0x7FF00000:
                        newmem = mem
                        break
                    if mem:
                        self.VirtualFreeEx(
                            self.process_handle, ctypes.c_void_p(mem), 0, MEM_RELEASE
                        )
                except Exception:
                    continue
            if newmem:
                break
        if not newmem:
            raise MemoryError("newmem allocation failed")
        self._sens_newmem = newmem

        sc = bytearray()
        float_embed_addr = newmem + 13
        rip_after_movss  = newmem + 8
        sc += b'\xF3\x0F\x10\x05' + struct.pack("<i", float_embed_addr - rip_after_movss)
        return_addr   = self.sens_addr + SENS_PATCH_SIZE
        rip_after_jmp = newmem + len(sc) + 5
        sc += b'\xE9' + struct.pack("<i", return_addr - rip_after_jmp)
        sc += struct.pack("<f", self.fixed_sens_value)

        self.pm.write_bytes(newmem, bytes(sc), len(sc))

        rel32_to_newmem   = newmem - (self.sens_addr + SENS_PATCH_SIZE)
        self._patch_bytes = b'\xE9' + struct.pack("<i", rel32_to_newmem)

    def set_pulse_duration(self, seconds: float):
        self.pulse_duration = max(0.01, min(0.5, seconds))

    def pulse(self, stop_event: threading.Event | None = None):
        if not self.sens_addr or not self._patch_bytes:
            return
        if not self._pulse_lock.acquire(blocking=False):
            return

        duration = self.pulse_duration

        def _do():
            try:
                old = self._set_writable(self.sens_addr, SENS_PATCH_SIZE)
                self.pm.write_bytes(self.sens_addr, self._patch_bytes, SENS_PATCH_SIZE)
                self._restore_protect(self.sens_addr, SENS_PATCH_SIZE, old)

                if stop_event:
                    stop_event.wait(timeout=duration)
                else:
                    time.sleep(duration)

                old = self._set_writable(self.sens_addr, SENS_PATCH_SIZE)
                self.pm.write_bytes(self.sens_addr, SENS_ORIG_BYTES, SENS_PATCH_SIZE)
                self._restore_protect(self.sens_addr, SENS_PATCH_SIZE, old)
            except Exception:
                pass
            finally:
                self._pulse_lock.release()

        threading.Thread(target=_do, daemon=True).start()

    def restore(self):
        if self.sens_addr:
            try:
                old = self._set_writable(self.sens_addr, SENS_PATCH_SIZE)
                self.pm.write_bytes(self.sens_addr, SENS_ORIG_BYTES, SENS_PATCH_SIZE)
                self._restore_protect(self.sens_addr, SENS_PATCH_SIZE, old)
            except Exception:
                pass

    def cleanup(self):
        self.restore()
        for attr in ('_sens_newmem', '_float_addr'):
            addr = getattr(self, attr, None)
            if addr:
                try:
                    self.VirtualFreeEx(
                        self.process_handle, ctypes.c_void_p(addr), 0, MEM_RELEASE
                    )
                except Exception:
                    pass
                setattr(self, attr, None)

class MicroAimController:
    def __init__(self):
        self.update_queue: queue.Queue | None = None
        self.initialized = False
        self.is_active   = False

        self.pulse_duration = 0.1

        self._detector      = get_shared_detector()
        self._menu_monitor  = get_shared_menu_monitor()

        self._sens_hook: SensHook | None = None
        self._pulse_stop_event: threading.Event | None = None

        self._VirtualProtectEx = kernel32_dll.VirtualProtectEx
        self._VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)
        ]
        self._VirtualProtectEx.restype = wintypes.BOOL

        self._VirtualAllocEx = kernel32_dll.VirtualAllocEx
        self._VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD
        ]
        self._VirtualAllocEx.restype = wintypes.LPVOID

        self._VirtualFreeEx = kernel32_dll.VirtualFreeEx
        self._VirtualFreeEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD
        ]
        self._VirtualFreeEx.restype = wintypes.BOOL

        self._pm = None

    def set_update_queue(self, q: queue.Queue):
        self.update_queue = q

    def set_pymem_process(self, pm):
        self._pm = pm
        self._detector.set_pymem_process(pm)
        self._menu_monitor.set_pymem_process(pm)

    def validate_process(self) -> bool:
        return self._detector.validate_process()

    def set_pulse_duration(self, seconds: float):
        self.pulse_duration = max(0.01, min(0.5, seconds))
        if self._sens_hook:
            self._sens_hook.set_pulse_duration(self.pulse_duration)

    def _on_aim_changed(self, is_aiming: bool):
        if not self.is_active:
            return

        if self._menu_monitor.is_menu_open:
            return

        if is_aiming:
            if self._sens_hook:
                self._pulse_stop_event = threading.Event()
                self._sens_hook.pulse(stop_event=self._pulse_stop_event)
        else:
            if self._pulse_stop_event:
                self._pulse_stop_event.set()
                self._pulse_stop_event = None

    def _on_menu_changed(self, is_menu_open: bool):
        if not self.is_active:
            return
        if is_menu_open:
            if self._pulse_stop_event:
                self._pulse_stop_event.set()
                self._pulse_stop_event = None

    def _update_status(self, message: str, color: str):
        if self.update_queue:
            self.update_queue.put(('status_update', ('microaim', message, color)))

    def initialize(self) -> bool:
        self.initialized = False
        self._sens_hook = None

        if not self._detector.initialize():
            self._update_status("Init Failed", '#ff5252')
            return False

        if self._pm is None:
            self._update_status("No process", '#ff5252')
            return False

        if not self._menu_monitor.initialized:
            self._menu_monitor.initialize()

        self._sens_hook = SensHook(
            self._pm,
            self._pm.process_handle,
            self._VirtualProtectEx,
            self._VirtualAllocEx,
            self._VirtualFreeEx
        )
        self._sens_hook.set_pulse_duration(self.pulse_duration)
        if self._sens_hook.scan():
            print(f"MicroAim: Initialized sens at 0x{self._sens_hook.sens_addr:X}")

        self.initialized = True
        return True

    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                return False
        if self.is_active:
            return True

        self._detector.add_listener(self._on_aim_changed)
        self._detector.start()

        self._menu_monitor.add_listener(self._on_menu_changed)
        self._menu_monitor.start()

        self.is_active = True
        self._update_status("Active", '#00e676')
        return True

    def stop(self, is_app_closing: bool = False):
        if not self.is_active:
            return True

        self._detector.remove_listener(self._on_aim_changed)

        self._menu_monitor.remove_listener(self._on_menu_changed)

        if self._pulse_stop_event:
            self._pulse_stop_event.set()
            self._pulse_stop_event = None

        self.is_active = False
        self._update_status("Inactive", '#b0b0b0')
        return True

    def reset_to_default(self, is_app_closing: bool = False):
        self.stop(is_app_closing=is_app_closing)
        if self._sens_hook:
            try:
                self._sens_hook.cleanup()
            except Exception:
                pass
            self._sens_hook = None
        self.initialized = False
        return True