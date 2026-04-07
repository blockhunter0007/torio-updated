import pymem
import pymem.process
import ctypes
from ctypes import wintypes
import struct
import re
import time
import threading


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT  = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000

AIM_PATTERN = b'\x48\x8B\x42\x40\x48\x89\x41\x40\xF0'


class AimDetector:

    def __init__(self):
        self.pm              = None
        self.process_handle  = None
        self.initialized     = False
        self._running        = False
        self.should_stop     = threading.Event()
        self._monitor_thread = None

        self.inject_addr = None
        self.newmem      = None
        self._aim_flag   = None

        self.is_aiming       = False
        self._aim_ended      = True
        self._reset_count    = 0
        self.CHECK_INTERVAL  = 0.01
        self.MAX_RETRY       = 3

        self._reset_lock = threading.Lock()
        self._resetting  = False

        self._listeners      = []
        self._listener_lock  = threading.Lock()

        self.VirtualAllocEx = kernel32.VirtualAllocEx
        self.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD
        ]
        self.VirtualAllocEx.restype = wintypes.LPVOID

        self.VirtualFreeEx = kernel32.VirtualFreeEx
        self.VirtualFreeEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD
        ]
        self.VirtualFreeEx.restype = wintypes.BOOL

        self.VirtualProtectEx = kernel32.VirtualProtectEx
        self.VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD)
        ]
        self.VirtualProtectEx.restype = wintypes.BOOL

    def set_pymem_process(self, pm: pymem.Pymem):
        self.pm             = pm
        self.process_handle = pm.process_handle

    def validate_process(self) -> bool:
        try:
            if not self.pm or not self.process_handle:
                return False
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                self.process_handle, ctypes.byref(exit_code)
            ):
                return False
            return exit_code.value == 259
        except Exception:
            return False

    def add_listener(self, callback):
        with self._listener_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback):
        with self._listener_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, is_aiming: bool):
        with self._listener_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(is_aiming)
            except Exception:
                pass

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

    def _allocate_near(self, base_addr: int, size: int = 0x1000) -> int:
        start = base_addr & 0xFFFFFFFFFFFF0000
        for offset in range(0, 0x7FF00000, 0x10000):
            for direction in [1, -1]:
                addr = start + offset * direction
                if addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
                    continue
                try:
                    mem = self.VirtualAllocEx(
                        self.process_handle, ctypes.c_void_p(addr), size,
                        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
                    )
                    if mem and abs(mem - base_addr) < 0x7FF00000:
                        return mem
                    if mem:
                        self.VirtualFreeEx(self.process_handle, mem, 0, MEM_RELEASE)
                except Exception:
                    continue
        mem = self.VirtualAllocEx(
            self.process_handle, None, size,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
        )
        if mem:
            return mem
        raise MemoryError("Memory allocation failed")

    def _scan_inject_point(self) -> bool:
        try:
            module = pymem.process.module_from_name(
                self.process_handle, "Minecraft.Windows.exe"
            )
            base = module.lpBaseOfDll
            size = module.SizeOfImage
            data = self.pm.read_bytes(base, size)
            matches = [
                m.start()
                for m in re.finditer(re.escape(AIM_PATTERN), data)
            ]
            if not matches:
                return False
            self.inject_addr = base + matches[0]
            return True
        except Exception:
            return False

    def _build_shellcode(self) -> bytes:
        sc = bytearray()

        sc += b'\x48\x8B\x42\x40'
        sc += b'\x48\x85\xC0'

        jz_pos = len(sc)
        sc += b'\x74\x00'

        sc += b'\x51'
        sc += b'\x48\xB9' + struct.pack("<Q", self._aim_flag)
        sc += b'\xC7\x01\x01\x00\x00\x00'
        sc += b'\x59'

        jmp_done_pos = len(sc)
        sc += b'\xEB\x00'

        to_zero_pos = len(sc)
        sc[jz_pos + 1] = to_zero_pos - (jz_pos + 2)

        sc += b'\x51'
        sc += b'\x48\xB9' + struct.pack("<Q", self._aim_flag)
        sc += b'\xC7\x01\x00\x00\x00\x00'
        sc += b'\x59'

        aim_done_pos = len(sc)
        sc[jmp_done_pos + 1] = aim_done_pos - (jmp_done_pos + 2)

        sc += b'\x48\x89\x41\x40'

        return_addr = self.inject_addr + 8
        jmp_back = return_addr - (self.newmem + len(sc) + 5)
        if abs(jmp_back) < 0x7FFFFFFF:
            sc += b'\xE9' + struct.pack("<i", jmp_back)
        else:
            sc += b'\x51'
            sc += b'\x48\xB9' + struct.pack("<Q", return_addr)
            sc += b'\x48\x87\x0C\x24'
            sc += b'\xC3'

        return bytes(sc)

    def _install_hook(self) -> bool:
        try:
            self._aim_flag = self.VirtualAllocEx(
                self.process_handle, None, 8,
                MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
            )
            if not self._aim_flag:
                return False
            self.pm.write_int(self._aim_flag, 0)

            self.newmem = self._allocate_near(self.inject_addr, 0x300)
            shellcode = self._build_shellcode()
            self.pm.write_bytes(self.newmem, shellcode, len(shellcode))

            self._write_jmp_to_newmem()
            return True
        except Exception:
            return False

    def _write_jmp_to_newmem(self):
        old = self._set_writable(self.inject_addr, 9)
        jmp_offset = self.newmem - (self.inject_addr + 5)
        patch = b'\xE9' + struct.pack("<i", jmp_offset) + b'\x90' * 3
        self.pm.write_bytes(self.inject_addr, patch, 8)
        self._restore_protect(self.inject_addr, 9, old)

    def _write_original_bytes(self):
        old = self._set_writable(self.inject_addr, 9)
        self.pm.write_bytes(self.inject_addr, AIM_PATTERN[:8], 8)
        self._restore_protect(self.inject_addr, 9, old)

    def _reset_hook(self):
        try:
            self._write_original_bytes()
            self.pm.write_int(self._aim_flag, 0)
            time.sleep(0.05)
            self._write_jmp_to_newmem()
            time.sleep(0.03)
            self._reset_count += 1
        except Exception:
            pass

    def _async_reset(self):
        if not self._reset_lock.acquire(blocking=False):
            return
        try:
            self._resetting = True
            self._reset_hook()
            time.sleep(0.05)
            recheck = self._read_aim_flag()
            retry = 0
            while recheck == 1 and retry < self.MAX_RETRY:
                self._reset_hook()
                time.sleep(0.05)
                recheck = self._read_aim_flag()
                retry += 1
        except Exception:
            pass
        finally:
            self._resetting = False
            self._reset_lock.release()

    def _read_aim_flag(self) -> int:
        try:
            val = self.pm.read_int(self._aim_flag)
            return val if val is not None else 0
        except Exception:
            return 0

    def _check(self):
        current = self._read_aim_flag()

        if current == 1:
            if not self.is_aiming:
                self.is_aiming = True
                if self._aim_ended:
                    self._aim_ended = False
                    threading.Thread(
                        target=self._notify,
                        args=(True,),
                        daemon=True
                    ).start()
            if not self._resetting:
                threading.Thread(target=self._async_reset, daemon=True).start()

        elif self.is_aiming and current == 0:
            if not self._resetting:
                self.is_aiming = False
                self._aim_ended = True
                threading.Thread(
                    target=self._notify,
                    args=(False,),
                    daemon=True
                ).start()

    def _monitor_loop(self):
        while not self.should_stop.is_set():
            try:
                self._check()
            except Exception:
                pass
            self.should_stop.wait(timeout=self.CHECK_INTERVAL)

    def initialize(self) -> bool:
        if self.initialized:
            return True
        if not self.validate_process():
            return False
        if not self._scan_inject_point():
            return False
        if not self._install_hook():
            return False
        self.initialized = True
        return True

    def reinitialize(self, pm: pymem.Pymem) -> bool:
        self.stop()

        if self.inject_addr and self.process_handle:
            try:
                self._write_original_bytes()
            except Exception:
                pass

        for attr in ('newmem', '_aim_flag'):
            addr = getattr(self, attr, None)
            if addr and self.process_handle:
                try:
                    self.VirtualFreeEx(
                        self.process_handle,
                        ctypes.c_void_p(addr), 0, MEM_RELEASE
                    )
                except Exception:
                    pass
                setattr(self, attr, None)

        self.inject_addr  = None
        self.initialized  = False
        self.is_aiming    = False
        self._aim_ended   = True
        self._resetting   = False
        self._reset_count = 0
        self._reset_lock  = threading.Lock()

        self.set_pymem_process(pm)

        return self.initialize()

    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                return False
        if self._running:
            return True
        self.should_stop.clear()
        self.is_aiming   = False
        self._aim_ended  = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()
        self._running = True
        return True

    def stop(self):
        if not self._running:
            return
        self.should_stop.set()
        self.is_aiming  = False
        self._aim_ended = True
        self._running   = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)

    def cleanup(self):
        self.stop()
        if not self.validate_process():
            return
        if self.inject_addr:
            try:
                self._write_original_bytes()
            except Exception:
                pass
        if self.newmem:
            try:
                self.VirtualFreeEx(
                    self.process_handle,
                    ctypes.c_void_p(self.newmem), 0, MEM_RELEASE
                )
            except Exception:
                pass
            self.newmem = None
        if self._aim_flag:
            try:
                self.VirtualFreeEx(
                    self.process_handle,
                    ctypes.c_void_p(self._aim_flag), 0, MEM_RELEASE
                )
            except Exception:
                pass
            self._aim_flag = None

        self.inject_addr = None
        self.initialized = False

_shared_detector: AimDetector | None = None
_detector_lock = threading.Lock()


def get_shared_detector() -> AimDetector:
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            _shared_detector = AimDetector()
        return _shared_detector


def reset_shared_detector():
    global _shared_detector
    with _detector_lock:
        if _shared_detector is not None:
            _shared_detector.cleanup()
            _shared_detector = None


def reinitialize_shared_detector(pm: pymem.Pymem) -> bool:
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            _shared_detector = AimDetector()
        detector = _shared_detector

    return detector.reinitialize(pm)