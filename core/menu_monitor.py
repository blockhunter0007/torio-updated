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

PATTERN_OPEN_CLOSE = b'\x48\x8B\x47\x38\x48\x85\xC0\x0F\x84\x8B'

PATTERN_CLOSE_ONLY = b'\x48\x89\x56\x38\x0F\x10\x46\x78'

CLOSE_WAIT_SEC = 0.03


class MenuMonitor:
    def __init__(self):
        self.pm             = None
        self.process_handle = None
        self.initialized    = False
        self._running       = False
        self.should_stop    = threading.Event()
        self._monitor_thread: threading.Thread | None = None

        self._inject_addr_oc    = None
        self._original_bytes_oc: bytes | None = None
        self._newmem_oc         = None

        self._inject_addr_cl    = None
        self._original_bytes_cl: bytes | None = None
        self._newmem_cl         = None

        self._flags_mem        = None
        self._tick_counter_ptr = None
        self._close_flag_ptr   = None

        self.is_menu_open  = False

        self.CHECK_INTERVAL = 0.01

        self._listeners      = []
        self._listener_lock  = threading.Lock()
        self._reset_lock     = threading.Lock()

        self._prev_tick      = 0
        self._pending_time   = None

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

    def _notify(self, is_menu_open: bool):
        with self._listener_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(is_menu_open)
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
            addr_oc = self._scan_pattern(PATTERN_OPEN_CLOSE)
            if addr_oc is None:
                return False
            self._inject_addr_oc    = addr_oc
            self._original_bytes_oc = self.pm.read_bytes(addr_oc, 7)

            addr_cl = self._scan_pattern(PATTERN_CLOSE_ONLY)
            if addr_cl is None:
                return False
            self._inject_addr_cl    = addr_cl
            self._original_bytes_cl = self.pm.read_bytes(addr_cl, 8)

            return True
        except Exception:
            return False

    def _alloc_flags(self) -> bool:
        try:
            mem = self._allocate_near(self._inject_addr_oc, 0x1000)
            self._flags_mem        = mem
            self._tick_counter_ptr = mem + 0x00
            self._close_flag_ptr   = mem + 0x04
            self.pm.write_bytes(self._flags_mem, b'\x00' * 0x10, 0x10)
            return True
        except Exception:
            return False

    def _install_hook_open_close(self) -> bool:
        try:
            newmem = self._allocate_near(self._inject_addr_oc, 0x1000)
            self._newmem_oc = newmem

            shellcode = bytearray()

            shellcode += b'\x50'

            rip_after_tick = newmem + len(shellcode) + 6
            disp_tick = self._tick_counter_ptr - rip_after_tick
            if not (-0x80000000 <= disp_tick <= 0x7FFFFFFF):
                raise RuntimeError(f"tick_counter RIP offset out of range: {hex(disp_tick)}")
            shellcode += b'\xFF\x05' + struct.pack('<i', disp_tick)

            shellcode += b'\x58'

            shellcode += b'\x48\x8B\x47\x38'
            shellcode += b'\x48\x85\xC0'

            return_addr = self._inject_addr_oc + 7
            jmp_back = return_addr - (newmem + len(shellcode) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                shellcode += b'\xE9' + struct.pack('<i', jmp_back)
            else:
                shellcode += b'\x48\xB8' + struct.pack('<Q', return_addr) + b'\xFF\xE0'

            self.pm.write_bytes(newmem, bytes(shellcode), len(shellcode))

            jmp_offset = newmem - (self._inject_addr_oc + 5)
            if not (-0x80000000 <= jmp_offset <= 0x7FFFFFFF):
                raise RuntimeError("newmem_oc is too far")

            old = self._set_writable(self._inject_addr_oc, 7)
            patch = b'\xE9' + struct.pack('<i', jmp_offset) + b'\x90' * 2
            self.pm.write_bytes(self._inject_addr_oc, patch, 7)
            self._restore_protect(self._inject_addr_oc, 7, old)

            return True
        except Exception:
            return False

    def _install_hook_close_only(self) -> bool:
        try:
            newmem = self._allocate_near(self._inject_addr_cl, 0x1000)
            self._newmem_cl = newmem

            shellcode = bytearray()

            shellcode += b'\x50'

            rip_after_cf = newmem + len(shellcode) + 7
            disp_cf = self._close_flag_ptr - rip_after_cf
            if not (-0x80000000 <= disp_cf <= 0x7FFFFFFF):
                raise RuntimeError(f"close_flag RIP offset out of range: {hex(disp_cf)}")
            shellcode += b'\x48\x8D\x05' + struct.pack('<i', disp_cf)
            shellcode += b'\xC7\x00\x01\x00\x00\x00'

            shellcode += b'\x58'

            shellcode += b'\x48\x89\x56\x38'
            shellcode += b'\x0F\x10\x46\x78'

            return_addr = self._inject_addr_cl + 8
            jmp_back = return_addr - (newmem + len(shellcode) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                shellcode += b'\xE9' + struct.pack('<i', jmp_back)
            else:
                shellcode += b'\x48\xB8' + struct.pack('<Q', return_addr) + b'\xFF\xE0'

            self.pm.write_bytes(newmem, bytes(shellcode), len(shellcode))

            jmp_offset = newmem - (self._inject_addr_cl + 5)
            if not (-0x80000000 <= jmp_offset <= 0x7FFFFFFF):
                raise RuntimeError("newmem_cl is too far")

            old = self._set_writable(self._inject_addr_cl, 8)
            patch = b'\xE9' + struct.pack('<i', jmp_offset) + b'\x90' * 3
            self.pm.write_bytes(self._inject_addr_cl, patch, 8)
            self._restore_protect(self._inject_addr_cl, 8, old)

            return True
        except Exception:
            return False

    def _restore_hook_oc(self):
        if self._inject_addr_oc and self._original_bytes_oc:
            try:
                old = self._set_writable(self._inject_addr_oc, 7)
                self.pm.write_bytes(self._inject_addr_oc, self._original_bytes_oc, 7)
                self._restore_protect(self._inject_addr_oc, 7, old)
            except Exception:
                pass

    def _restore_hook_cl(self):
        if self._inject_addr_cl and self._original_bytes_cl:
            try:
                old = self._set_writable(self._inject_addr_cl, 8)
                self.pm.write_bytes(self._inject_addr_cl, self._original_bytes_cl, 8)
                self._restore_protect(self._inject_addr_cl, 8, old)
            except Exception:
                pass

    def _free_newmem(self):
        for attr in ('_newmem_oc', '_newmem_cl', '_flags_mem'):
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
        self._tick_counter_ptr = None
        self._close_flag_ptr   = None

    def _read_tick(self) -> int | None:
        try:
            return self.pm.read_int(self._tick_counter_ptr)
        except Exception:
            return None

    def _read_close_flag(self) -> int | None:
        try:
            return self.pm.read_int(self._close_flag_ptr)
        except Exception:
            return None

    def _reset_close_flag(self):
        try:
            self.pm.write_bytes(self._close_flag_ptr, b'\x00\x00\x00\x00', 4)
        except Exception:
            pass

    def _check(self):
        now  = time.perf_counter()
        tick = self._read_tick()
        if tick is None:
            return

        if tick != self._prev_tick:
            self._prev_tick    = tick
            self._pending_time = now

        if self._pending_time is not None and (now - self._pending_time) >= CLOSE_WAIT_SEC:
            close_val = self._read_close_flag()

            new_state = (close_val != 1)

            self._reset_close_flag()
            self._pending_time = None

            if new_state != self.is_menu_open:
                self.is_menu_open = new_state
                threading.Thread(
                    target=self._notify,
                    args=(new_state,),
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
        if not self._scan_inject_points():
            return False
        if not self._alloc_flags():
            return False
        if not self._install_hook_open_close():
            return False
        if not self._install_hook_close_only():
            return False
        self.initialized = True
        return True

    def reinitialize(self, pm: pymem.Pymem) -> bool:
        self.stop()
        self._restore_hook_oc()
        self._restore_hook_cl()
        self._free_newmem()

        self._inject_addr_oc    = None
        self._original_bytes_oc = None
        self._inject_addr_cl    = None
        self._original_bytes_cl = None
        self.initialized        = False
        self.is_menu_open       = False
        self._prev_tick         = 0
        self._pending_time      = None

        self.set_pymem_process(pm)
        return self.initialize()

    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                return False
        if self._running:
            return True
        self.should_stop.clear()
        self.is_menu_open    = False
        self._prev_tick      = self._read_tick() or 0
        self._pending_time   = None
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
        self.is_menu_open = False
        self._running     = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)

    def cleanup(self):
        self.stop()
        if not self.validate_process():
            return
        self._restore_hook_oc()
        self._restore_hook_cl()
        self._free_newmem()
        self._inject_addr_oc    = None
        self._original_bytes_oc = None
        self._inject_addr_cl    = None
        self._original_bytes_cl = None
        self.initialized        = False


_shared_menu_monitor: MenuMonitor | None = None
_monitor_lock = threading.Lock()


def get_shared_menu_monitor() -> MenuMonitor:
    global _shared_menu_monitor
    with _monitor_lock:
        if _shared_menu_monitor is None:
            _shared_menu_monitor = MenuMonitor()
        return _shared_menu_monitor


def reset_shared_menu_monitor():
    global _shared_menu_monitor
    with _monitor_lock:
        if _shared_menu_monitor is not None:
            _shared_menu_monitor.cleanup()
            _shared_menu_monitor = None


def reinitialize_shared_menu_monitor(pm: pymem.Pymem) -> bool:
    global _shared_menu_monitor
    with _monitor_lock:
        if _shared_menu_monitor is None:
            _shared_menu_monitor = MenuMonitor()
        monitor = _shared_menu_monitor
    result = monitor.reinitialize(pm)
    if result:
        monitor.start()
    return result