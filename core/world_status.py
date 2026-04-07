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

PATTERN_ENTER = b'\x48\xC7\x42\x30\x0F\x00\x00\x00\x88\x42\x18\x48\x89\x42\x38\x48'

PATTERN_EXIT  = b'\x48\xC7\x07\x0F\x00\x00\x00\xC6\x47\xE8\x00\x48\x83\xC5'


class WorldStatusMonitor:
    def __init__(self):
        self.pm             = None
        self.process_handle = None
        self.initialized    = False
        self._running       = False
        self.should_stop    = threading.Event()
        self._monitor_thread: threading.Thread | None = None

        self._inject_addr_enter    = None
        self._original_bytes_enter: bytes | None = None
        self._newmem_enter         = None

        self._inject_addr_exit     = None
        self._original_bytes_exit: bytes | None = None
        self._newmem_exit          = None

        self._flags_mem       = None
        self._enter_flag_ptr  = None
        self._exit_flag_ptr   = None

        self.world_status: int = 0

        self.CHECK_INTERVAL = 0.05

        self._listeners     = []
        self._listener_lock = threading.Lock()
        self._reset_lock    = threading.Lock()

        self._prev_enter    = 0
        self._prev_exit     = 0

        self.VirtualAllocEx = kernel32.VirtualAllocEx
        self.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
        ]
        self.VirtualAllocEx.restype = wintypes.LPVOID

        self.VirtualFreeEx = kernel32.VirtualFreeEx
        self.VirtualFreeEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
        ]
        self.VirtualFreeEx.restype = wintypes.BOOL

        self.VirtualProtectEx = kernel32.VirtualProtectEx
        self.VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
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

    def _notify(self, world_status: int):
        with self._listener_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(world_status)
            except Exception:
                pass

    def _set_writable(self, addr: int, size: int) -> int:
        old = wintypes.DWORD()
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            size, PAGE_EXECUTE_READWRITE, ctypes.byref(old),
        )
        return old.value

    def _restore_protect(self, addr: int, size: int, old_prot: int):
        dummy = wintypes.DWORD()
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            size, old_prot, ctypes.byref(dummy),
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
                        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE,
                    )
                    if mem and abs(mem - base_addr) < 0x7FF00000:
                        return mem
                    if mem:
                        self.VirtualFreeEx(self.process_handle, mem, 0, MEM_RELEASE)
                except Exception:
                    continue
        mem = self.VirtualAllocEx(
            self.process_handle, None, size,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE,
        )
        if mem:
            return mem
        raise MemoryError("Memory allocation failed")

    def _scan_pattern(self, pattern: bytes):
        module = pymem.process.module_from_name(
            self.process_handle, "Minecraft.Windows.exe"
        )
        base = module.lpBaseOfDll
        size = module.SizeOfImage
        data = self.pm.read_bytes(base, size)
        matches = [m.start() for m in re.finditer(re.escape(pattern), data)]
        if not matches:
            return None
        return base + matches[0]

    def _scan_inject_points(self) -> bool:
        try:
            addr_enter = self._scan_pattern(PATTERN_ENTER)
            if addr_enter is None:
                return False
            self._inject_addr_enter    = addr_enter
            self._original_bytes_enter = self.pm.read_bytes(addr_enter, 8)

            addr_exit = self._scan_pattern(PATTERN_EXIT)
            if addr_exit is None:
                return False
            self._inject_addr_exit    = addr_exit
            self._original_bytes_exit = self.pm.read_bytes(addr_exit, 7)

            return True
        except Exception:
            return False

    def _alloc_flags(self) -> bool:
        try:
            mem = self._allocate_near(self._inject_addr_enter, 0x1000)
            self._flags_mem      = mem
            self._enter_flag_ptr = mem + 0x00
            self._exit_flag_ptr  = mem + 0x04
            self.pm.write_bytes(self._flags_mem, b'\x00' * 0x10, 0x10)
            return True
        except Exception:
            return False

    def _install_hook_enter(self) -> bool:
        try:
            newmem = self._allocate_near(self._inject_addr_enter, 0x1000)
            self._newmem_enter = newmem

            sc = bytearray()

            sc += b'\x50'

            rip_after = newmem + len(sc) + 6
            disp = self._enter_flag_ptr - rip_after
            if not (-0x80000000 <= disp <= 0x7FFFFFFF):
                raise RuntimeError(f"enter_flag RIP offset out of range: {hex(disp)}")
            sc += b'\xFF\x05' + struct.pack('<i', disp)

            sc += b'\x58'

            sc += b'\x48\xC7\x42\x30\x0F\x00\x00\x00'

            return_addr = self._inject_addr_enter + 8
            jmp_back = return_addr - (newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack('<i', jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack('<Q', return_addr) + b'\xFF\xE0'

            self.pm.write_bytes(newmem, bytes(sc), len(sc))

            jmp_offset = newmem - (self._inject_addr_enter + 5)
            if not (-0x80000000 <= jmp_offset <= 0x7FFFFFFF):
                raise RuntimeError("newmem_enter is too far")

            old = self._set_writable(self._inject_addr_enter, 8)
            patch = b'\xE9' + struct.pack('<i', jmp_offset) + b'\x90' * 3
            self.pm.write_bytes(self._inject_addr_enter, patch, 8)
            self._restore_protect(self._inject_addr_enter, 8, old)

            return True
        except Exception as e:
            return False

    def _install_hook_exit(self) -> bool:
        try:
            newmem = self._allocate_near(self._inject_addr_exit, 0x1000)
            self._newmem_exit = newmem

            sc = bytearray()

            sc += b'\x50'

            rip_after = newmem + len(sc) + 6
            disp = self._exit_flag_ptr - rip_after
            if not (-0x80000000 <= disp <= 0x7FFFFFFF):
                raise RuntimeError(f"exit_flag RIP offset out of range: {hex(disp)}")
            sc += b'\xFF\x05' + struct.pack('<i', disp)

            sc += b'\x58'

            sc += b'\x48\xC7\x07\x0F\x00\x00\x00'

            return_addr = self._inject_addr_exit + 7
            jmp_back = return_addr - (newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack('<i', jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack('<Q', return_addr) + b'\xFF\xE0'

            self.pm.write_bytes(newmem, bytes(sc), len(sc))

            jmp_offset = newmem - (self._inject_addr_exit + 5)
            if not (-0x80000000 <= jmp_offset <= 0x7FFFFFFF):
                raise RuntimeError("newmem_exit is too far")

            old = self._set_writable(self._inject_addr_exit, 7)
            patch = b'\xE9' + struct.pack('<i', jmp_offset) + b'\x90' * 2
            self.pm.write_bytes(self._inject_addr_exit, patch, 7)
            self._restore_protect(self._inject_addr_exit, 7, old)

            return True
        except Exception as e:
            return False

    def _restore_hook_enter(self):
        if self._inject_addr_enter and self._original_bytes_enter:
            try:
                old = self._set_writable(self._inject_addr_enter, 8)
                self.pm.write_bytes(
                    self._inject_addr_enter, self._original_bytes_enter, 8
                )
                self._restore_protect(self._inject_addr_enter, 8, old)
            except Exception:
                pass

    def _restore_hook_exit(self):
        if self._inject_addr_exit and self._original_bytes_exit:
            try:
                old = self._set_writable(self._inject_addr_exit, 7)
                self.pm.write_bytes(
                    self._inject_addr_exit, self._original_bytes_exit, 7
                )
                self._restore_protect(self._inject_addr_exit, 7, old)
            except Exception:
                pass

    def _free_newmem(self):
        for attr in ('_newmem_enter', '_newmem_exit', '_flags_mem'):
            addr = getattr(self, attr, None)
            if addr and self.process_handle:
                try:
                    self.VirtualFreeEx(
                        self.process_handle,
                        ctypes.c_void_p(addr), 0, MEM_RELEASE,
                    )
                except Exception:
                    pass
            setattr(self, attr, None)
        self._enter_flag_ptr = None
        self._exit_flag_ptr  = None

    def _read_enter_flag(self) -> int | None:
        try:
            return self.pm.read_int(self._enter_flag_ptr)
        except Exception:
            return None

    def _read_exit_flag(self) -> int | None:
        try:
            return self.pm.read_int(self._exit_flag_ptr)
        except Exception:
            return None

    def _check(self):
        enter_val = self._read_enter_flag()
        exit_val  = self._read_exit_flag()
        if enter_val is None or exit_val is None:
            return

        entered = enter_val != self._prev_enter
        exited  = exit_val  != self._prev_exit

        self._prev_enter = enter_val
        self._prev_exit  = exit_val

        if entered and not exited:
            if self.world_status != 1:
                self.world_status = 1
                threading.Thread(
                    target=self._notify, args=(1,), daemon=True
                ).start()

        elif exited:
            if self.world_status != 0:
                self.world_status = 0
                threading.Thread(
                    target=self._notify, args=(0,), daemon=True
                ).start()

    def _monitor_loop(self):
        while not self.should_stop.is_set():
            try:
                self._check()
            except Exception:
                pass
            self.should_stop.wait(timeout=self.CHECK_INTERVAL)

    def set_world_status(self, status: int):
        if self.world_status != status:
            self.world_status = status
            threading.Thread(
                target=self._notify, args=(status,), daemon=True
            ).start()

    def initialize(self) -> bool:
        if self.initialized:
            return True
        if not self.validate_process():
            return False
        if not self._scan_inject_points():
            return False
        if not self._alloc_flags():
            return False
        if not self._install_hook_enter():
            return False
        if not self._install_hook_exit():
            return False
        self.initialized = True
        return True

    def reinitialize(self, pm: pymem.Pymem) -> bool:
        self.stop()
        self._restore_hook_enter()
        self._restore_hook_exit()
        self._free_newmem()

        self._inject_addr_enter    = None
        self._original_bytes_enter = None
        self._inject_addr_exit     = None
        self._original_bytes_exit  = None
        self.initialized           = False
        self.world_status          = 0
        self._prev_enter           = 0
        self._prev_exit            = 0

        self.set_pymem_process(pm)
        return self.initialize()

    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                return False
        if self._running:
            return True
        self.should_stop.clear()
        self.world_status  = 0
        self._prev_enter   = self._read_enter_flag() or 0
        self._prev_exit    = self._read_exit_flag()  or 0
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
        self.world_status = 0
        self._running     = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)

    def cleanup(self):
        self.stop()
        if not self.validate_process():
            return
        self._restore_hook_enter()
        self._restore_hook_exit()
        self._free_newmem()
        self._inject_addr_enter    = None
        self._original_bytes_enter = None
        self._inject_addr_exit     = None
        self._original_bytes_exit  = None
        self.initialized           = False

_shared_world_monitor: WorldStatusMonitor | None = None
_monitor_lock = threading.Lock()


def get_shared_world_monitor() -> WorldStatusMonitor:
    global _shared_world_monitor
    with _monitor_lock:
        if _shared_world_monitor is None:
            _shared_world_monitor = WorldStatusMonitor()
        return _shared_world_monitor


def reset_shared_world_monitor():
    global _shared_world_monitor
    with _monitor_lock:
        if _shared_world_monitor is not None:
            _shared_world_monitor.cleanup()
            _shared_world_monitor = None


def reinitialize_shared_world_monitor(pm: pymem.Pymem) -> bool:
    global _shared_world_monitor
    with _monitor_lock:
        if _shared_world_monitor is None:
            _shared_world_monitor = WorldStatusMonitor()
        monitor = _shared_world_monitor
    result = monitor.reinitialize(pm)
    if result:
        monitor.start()
    return result