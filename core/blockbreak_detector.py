# blockbreak_detector.py
import pymem
import pymem.process
import struct
import ctypes
from ctypes import wintypes
import re
import time
import threading

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT  = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000


class BlockBreakDetector:
    OFF_DELAY = 0.15  # OFFと判定するまでの遅延秒数

    def __init__(self):
        self.pm             = None
        self.process_handle = None
        self.should_stop    = threading.Event()

        self.pattern_on_str  = "C6 80 ?? ?? 00 00 01 40 B7 01 EB 60 48 8B 7E 08"
        self.pattern_off_str = "C6 83 ?? ?? 00 00 00 F2 0F 10 41 10 F2 0F 11 44 24"
        self.len_on      = 7
        self.len_off     = 7

        self.inject_on   = None
        self.inject_off  = None
        self.newmem_on   = None
        self.newmem_off  = None
        self.blockstatus = None
        self.orig_on     = None
        self.orig_off    = None
        self.is_active   = False

        self._listeners      = []
        self._listener_lock  = threading.Lock()

        self._last_status    = 0
        self._monitor_thread = None

        # OFF遅延管理
        self._off_pending_time: float | None = None  # OFFを検出した時刻

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

    def _notify(self, is_breaking: bool):
        with self._listener_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(is_breaking)
            except Exception:
                pass

    def _pattern_to_regex(self, pattern_str: str) -> bytes:
        regex_parts = []
        for byte in pattern_str.split():
            if byte == '??':
                regex_parts.append(b'.')
            else:
                regex_parts.append(re.escape(bytes.fromhex(byte)))
        return b''.join(regex_parts)

    def _find_pattern(self, data: bytes, pattern_str: str) -> list[int]:
        regex = self._pattern_to_regex(pattern_str)
        return [m.start() for m in re.finditer(regex, data, re.DOTALL)]

    def _scan_aob(self) -> bool:
        try:
            module = pymem.process.module_from_name(
                self.process_handle, "Minecraft.Windows.exe"
            )
            base = module.lpBaseOfDll
            size = module.SizeOfImage
            data = self.pm.read_bytes(base, size)

            matches_on = self._find_pattern(data, self.pattern_on_str)
            if not matches_on:
                print("[BlockBreakDetector] ERROR: ON pattern not found")
                return False
            self.inject_on = base + matches_on[0]
            self.orig_on   = self.pm.read_bytes(self.inject_on, self.len_on)

            matches_off = self._find_pattern(data, self.pattern_off_str)
            if not matches_off:
                print("[BlockBreakDetector] ERROR: OFF pattern not found")
                return False
            self.inject_off = base + matches_off[0]
            self.orig_off   = self.pm.read_bytes(self.inject_off, self.len_off)

            return True
        except Exception as e:
            print(f"[BlockBreakDetector] _scan_aob error: {e}")
            return False

    def _allocate_near(self, base_addr: int, size: int = 0x1000) -> int:
        start = base_addr & 0xFFFFFFFFFFFF0000
        for offset in range(0, 0x7FF00000, 0x10000):
            for direction in [1, -1]:
                addr = start + offset * direction
                if addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
                    continue
                mem = self.VirtualAllocEx(
                    self.process_handle, ctypes.c_void_p(addr),
                    size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
                )
                if mem and abs(mem - base_addr) < 0x7FF00000:
                    return mem
                if mem:
                    self.VirtualFreeEx(self.process_handle, mem, 0, MEM_RELEASE)
        mem = self.VirtualAllocEx(
            self.process_handle, None,
            size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
        )
        if mem:
            return mem
        raise MemoryError("Memory allocation failed")

    def _write_protected(self, addr: int, data: bytes):
        old_prot = wintypes.DWORD()
        kernel32.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot)
        )
        self.pm.write_bytes(addr, data, len(data))
        kernel32.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(addr),
            len(data), old_prot.value, ctypes.byref(old_prot)
        )

    def _build_hook_on(self, orig_bytes: bytes) -> tuple:
        sc = bytearray()
        sc += orig_bytes
        disp_pos = len(sc) + 2
        sc += b'\xC7\x05' + b'\x00\x00\x00\x00' + b'\x01\x00\x00\x00'
        jmp_pos = len(sc) + 1
        sc += b'\xE9' + b'\x00\x00\x00\x00'
        return sc, disp_pos, jmp_pos

    def _build_hook_off(self, orig_bytes: bytes) -> tuple:
        sc = bytearray()
        disp_pos = len(sc) + 2
        sc += b'\xC7\x05' + b'\x00\x00\x00\x00' + b'\x00\x00\x00\x00'
        sc += orig_bytes
        jmp_pos = len(sc) + 1
        sc += b'\xE9' + b'\x00\x00\x00\x00'
        return sc, disp_pos, jmp_pos

    def _install_hooks(self) -> bool:
        try:
            self.newmem_on  = self._allocate_near(self.inject_on,  0x1000)
            self.newmem_off = self._allocate_near(self.inject_off, 0x1000)

            self.blockstatus = self.newmem_on + 0xF00
            self.pm.write_int(self.blockstatus, 0)

            sc_on, disp_on, jmp_on = self._build_hook_on(self.orig_on)
            sc_on = bytearray(sc_on)

            rip_end_on = self.newmem_on + disp_on + 8
            disp32_on  = self.blockstatus - rip_end_on
            if not (-0x80000000 <= disp32_on <= 0x7FFFFFFF):
                raise RuntimeError(f"ON: RIP relative offset out of range: {hex(disp32_on)}")
            struct.pack_into('<i', sc_on, disp_on, disp32_on)

            return_on     = self.inject_on + self.len_on
            jmp_target_on = return_on - (self.newmem_on + jmp_on + 4)
            if not (-0x80000000 <= jmp_target_on <= 0x7FFFFFFF):
                raise RuntimeError("ON: jmp out of range")
            struct.pack_into('<i', sc_on, jmp_on, jmp_target_on)
            self.pm.write_bytes(self.newmem_on, bytes(sc_on), len(sc_on))

            sc_off, disp_off, jmp_off = self._build_hook_off(self.orig_off)
            sc_off = bytearray(sc_off)

            rip_end_off = self.newmem_off + disp_off + 8
            disp32_off  = self.blockstatus - rip_end_off
            if not (-0x80000000 <= disp32_off <= 0x7FFFFFFF):
                raise RuntimeError(f"OFF: RIP relative offset out of range: {hex(disp32_off)}")
            struct.pack_into('<i', sc_off, disp_off, disp32_off)

            return_off     = self.inject_off + self.len_off
            jmp_target_off = return_off - (self.newmem_off + jmp_off + 4)
            if not (-0x80000000 <= jmp_target_off <= 0x7FFFFFFF):
                raise RuntimeError("OFF: jmp out of range")
            struct.pack_into('<i', sc_off, jmp_off, jmp_target_off)
            self.pm.write_bytes(self.newmem_off, bytes(sc_off), len(sc_off))

            jmp_to_on = self.newmem_on - (self.inject_on + 5)
            patch_on  = b'\xE9' + struct.pack('<i', jmp_to_on) + b'\x90\x90'
            self._write_protected(self.inject_on, patch_on)

            jmp_to_off = self.newmem_off - (self.inject_off + 5)
            patch_off  = b'\xE9' + struct.pack('<i', jmp_to_off) + b'\x90\x90'
            self._write_protected(self.inject_off, patch_off)

            self.is_active = True
            return True

        except Exception as e:
            print(f"[BlockBreakDetector] _install_hooks error: {e}")
            return False

    def _reset_hooks(self):
        if self.inject_on and self.orig_on:
            try:
                self._write_protected(self.inject_on, self.orig_on)
            except Exception:
                pass

        if self.inject_off and self.orig_off:
            try:
                self._write_protected(self.inject_off, self.orig_off)
            except Exception:
                pass

        for attr in ('newmem_on', 'newmem_off'):
            addr = getattr(self, attr)
            if addr:
                try:
                    self.VirtualFreeEx(
                        self.process_handle,
                        ctypes.c_void_p(addr), 0, MEM_RELEASE
                    )
                except Exception:
                    pass
                setattr(self, attr, None)

        self.blockstatus = None
        self.is_active   = False

    def _monitor_loop(self):
        """
        OFF遅延ロジック:
        - current=0になったら即OFFにせず、_off_pending_timeに時刻を記録
        - OFF_DELAY秒以内にcurrent=1が来たら → ONを継続（ブロック連続破壊）
        - OFF_DELAY秒経過してもcurrent=0のまま → 本当のOFFとして_notify(False)
        """
        while not self.should_stop.is_set():
            if not self.is_active or not self.blockstatus:
                time.sleep(0.004)
                continue
            try:
                current = self.pm.read_int(self.blockstatus)
                now     = time.monotonic()

                if current == 1:
                    if self._last_status == 0:
                        # 新たにON → 即通知、OFF待機をキャンセル
                        self._off_pending_time = None
                        self._notify(True)
                    elif self._off_pending_time is not None:
                        # OFF待機中にONが戻ってきた → 連続破壊、OFF待機キャンセル
                        self._off_pending_time = None
                        # _last_statusは0になっている可能性があるので通知
                        self._notify(True)

                else:  # current == 0
                    if self._last_status == 1 and self._off_pending_time is None:
                        # 初めて0になった → OFF待機開始
                        self._off_pending_time = now

                    if self._off_pending_time is not None:
                        if now - self._off_pending_time >= self.OFF_DELAY:
                            # 遅延時間経過 → 本当のOFF
                            self._off_pending_time = None
                            self._notify(False)

                self._last_status = current

            except Exception:
                pass
            time.sleep(0.004)

    def is_breaking(self) -> bool:
        if not self.is_active or not self.blockstatus:
            return False
        try:
            return self.pm.read_int(self.blockstatus) == 1
        except Exception:
            return False

    def initialize(self) -> bool:
        if self.is_active:
            return True
        if not self.validate_process():
            return False
        if not self._scan_aob():
            return False
        if not self._install_hooks():
            return False
        return True

    def start(self) -> bool:
        if not self.initialize():
            return False
        self.should_stop.clear()
        self._last_status      = 0
        self._off_pending_time = None
        self._monitor_thread   = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()
        return True

    def stop(self):
        self.should_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)

    def cleanup(self):
        self.stop()
        if self.validate_process():
            self._reset_hooks()

    def reinitialize(self, pm: pymem.Pymem) -> bool:
        self.cleanup()
        self.inject_on         = None
        self.inject_off        = None
        self.orig_on           = None
        self.orig_off          = None
        self.is_active         = False
        self._last_status      = 0
        self._off_pending_time = None
        self.set_pymem_process(pm)
        return self.initialize()


_shared_detector: BlockBreakDetector | None = None
_detector_lock = threading.Lock()


def get_shared_block_detector() -> BlockBreakDetector:
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            _shared_detector = BlockBreakDetector()
        return _shared_detector


def reset_shared_block_detector():
    global _shared_detector
    with _detector_lock:
        if _shared_detector is not None:
            _shared_detector.cleanup()
            _shared_detector = None


def reinitialize_shared_block_detector(pm: pymem.Pymem) -> bool:
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            _shared_detector = BlockBreakDetector()
        detector = _shared_detector
    return detector.reinitialize(pm)