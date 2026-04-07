import pymem
import pymem.process
import struct
import ctypes
from ctypes import wintypes
import re
import time
import threading
import random
from config import ConfigManager

from core.minecraft_windowmonitor import get_shared_window_monitor as _get_window_monitor
from core.menu_monitor import get_shared_menu_monitor as _get_menu_monitor
from core.world_status import get_shared_world_monitor as _get_world_monitor

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PAGE_EXECUTE_READWRITE = 0x40
PAGE_READWRITE         = 0x04
MEM_COMMIT             = 0x1000
MEM_RESERVE            = 0x2000
MEM_RELEASE            = 0x8000

INPUT_KEYBOARD      = 1
KEYEVENTF_KEYUP     = 0x0002
KEYEVENTF_SCANCODE  = 0x0008

VK_SPACE  = 0x20
VK_MAP = {
    "space": VK_SPACE,
}

_user32 = ctypes.WinDLL("user32", use_last_error=True)

ULONG_PTR = ctypes.c_uint64


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class _InputUnion(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("_pad", ctypes.c_byte * 28),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type",  wintypes.DWORD),
        ("union", _InputUnion),
    ]


def _send_key(vk: int, key_up: bool = False):
    flags = KEYEVENTF_KEYUP if key_up else 0
    ii = _InputUnion()
    ii.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    inp = INPUT(type=INPUT_KEYBOARD, union=ii)
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _press_key(vk: int):
    _send_key(vk, key_up=False)

def _release_key(vk: int):
    _send_key(vk, key_up=True)

def _resolve_vk(key_name: str) -> int:
    low = key_name.lower()
    if low in VK_MAP:
        return VK_MAP[low]
    if len(low) == 1:
        vk = _user32.VkKeyScanW(ord(low)) & 0xFF
        if vk:
            return vk
    return VK_SPACE


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_void_p),
        ("AllocationBase",    ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("PartitionKey",      ctypes.c_ushort),
        ("RegionSize",        ctypes.c_size_t),
        ("State",             ctypes.c_ulong),
        ("Protect",           ctypes.c_ulong),
        ("Type",              ctypes.c_ulong),
    ]


class JumpResetController:
    PLAYER_PATTERNS = {
        "1.21.132": "18 B9 ?? ?? ?? 7F ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0F 00 00 00 00 00 00 00 05 00 01 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.2":   "10 A2 ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0F 00 00 00 00 00 00 00 05 00 01 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.101": "10 A2 ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0F 00 00 00 00 00 00 00 05 00 01 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.201": "D0 A2 ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0F 00 00 00 00 00 00 00 05 00 01 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.301": "D0 A1 ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 0F 00 00 00 00 00 00 00 05 00 01 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.1004": "60 BD ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? 00 00 00 00 00 00 00 ?? 00 ?? 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.1101": "60 BD ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? 00 00 00 00 00 00 00 ?? 00 ?? 00 00 00 00 00 00 00 00 00 00 00",
        "1.26.1202": "60 7D ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? 00 00 00 00 00 00 00 ?? 00 ?? 00 00 00 00 00 00 00 00 00 00 00",
        "1.21.131": "10 81 ?? ?? ?? 7F ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? 00 00 00 00 00 00 00 ?? 00 ?? 00 00 00 00 00 00 00 00 00 00 00",
        "1.21.130": "58 70 ?? ?? ?? 7F 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? ?? ?? 00 00 ?? ?? ?? ?? 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ?? 00 00 00 00 00 00 00 ?? 00 ?? 00 00 00 00 00 00 00 00 00 00 00",
    }

    INJECT_PATTERNS = {
        "default":  b'\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00\x8B',
        "1.21.130": b'\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00\x41',
        "1.21.131": b'\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00\x41',
    }

    _FOUR_DIGIT_PATCHES = {"1004", "1101", "1202"}

    @staticmethod
    def _normalize_version(version_string):
        if not version_string:
            return None
        # まず4桁パッチを試みる
        match4 = re.match(r'(\d+\.\d+\.)(\d{4})', str(version_string).strip())
        if match4 and match4.group(2) in JumpResetController._FOUR_DIGIT_PATCHES:
            return match4.group(1) + match4.group(2)
        # 通常の3桁以下
        match = re.match(r'(\d+\.\d+\.)(\d{1,3})', str(version_string).strip())
        if match:
            return match.group(1) + match.group(2)
        return None

    @staticmethod
    def _get_inject_pattern(version_string):
        normalized = JumpResetController._normalize_version(version_string)
        if normalized and normalized in JumpResetController.INJECT_PATTERNS:
            return JumpResetController.INJECT_PATTERNS[normalized]
        return b'\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00\x8B'

    @staticmethod
    def _is_legacy_version(version_string):
        normalized = JumpResetController._normalize_version(version_string)
        return normalized in ("1.21.130", "1.21.131")

    @staticmethod
    def is_supported_version(version_string):
        try:
            from version_detector import MinecraftVersionDetector
            return MinecraftVersionDetector.is_jumpreset_supported(version_string)
        except ImportError:
            SUPPORTED_VERSIONS = ["1.26.2", "1.26.101", "1.21.132", "1.21.131", "1.21.130", "1.26.1004"]
            normalized = JumpResetController._normalize_version(version_string)
            return normalized in SUPPORTED_VERSIONS if normalized else False

    @staticmethod
    def get_pattern_version(version_string):
        if not version_string:
            return None
        if not JumpResetController.is_supported_version(version_string):
            return None
        normalized = JumpResetController._normalize_version(version_string)
        if normalized and normalized in JumpResetController.PLAYER_PATTERNS:
            return normalized
        return None

    def __init__(self, version_config=None, full_version=None):
        self.pm             = None
        self.process_handle = None
        self.should_stop    = threading.Event()
        self.is_active      = False
        self.initialized    = False
        self.version_config = version_config
        self.full_version   = full_version

        if full_version:
            self.minecraft_version = self._normalize_version(full_version)
        else:
            version_string = version_config.get('series') if version_config else None
            self.minecraft_version = self._normalize_version(version_string)

        if self.minecraft_version and not JumpResetController.is_supported_version(self.minecraft_version):
            self.minecraft_version = None

        self.inject_pattern  = self._get_inject_pattern(self.minecraft_version)
        self.target_addr     = None
        self.newmem          = None
        self.damage_flag     = None
        self.my_player       = None
        self.original_bytes  = None

        self.config_manager  = ConfigManager("config.json")
        self.current_key     = self.config_manager.get_keybind('jump') or 'space'
        self.jump_key        = self.current_key
        self.jump_hold_time  = 1.0

        self._jump_vk = _resolve_vk(self.current_key)

        self._hit_count     = 0
        self._last_hit_time = 0.0
        self._combo_window  = 1.5

        self.update_queue = None
        self._state_lock  = threading.Lock()

        self.player_in_world  = False
        self._world_monitor   = _get_world_monitor()

        self.keybind_monitoring_active = False
        self.keybind_monitor_thread    = None
        self.monitor_thread     = None
        self.auto_hook_thread   = None

        self._scan_request    = threading.Event()
        self._scan_thread     = None

        self._window_monitor_ref = None
        self._mc_active_cache    = False
        self._menu_monitor       = _get_menu_monitor()

        self.VirtualAllocEx  = kernel32.VirtualAllocEx
        self.VirtualAllocEx.argtypes  = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
        self.VirtualAllocEx.restype   = wintypes.LPVOID
        self.VirtualProtectEx = kernel32.VirtualProtectEx
        self.VirtualProtectEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.VirtualProtectEx.restype  = wintypes.BOOL
        self.WriteProcessMemory = kernel32.WriteProcessMemory
        self.WriteProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self.WriteProcessMemory.restype  = wintypes.BOOL
        self.VirtualFreeEx = kernel32.VirtualFreeEx
        self.VirtualFreeEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD]
        self.VirtualFreeEx.restype  = wintypes.BOOL

    def _on_world_status_changed(self, world_status: int):
        if world_status == 1:
            self._scan_request.set()
        else:
            with self._state_lock:
                self.my_player       = None
                self.player_in_world = False
            if self.newmem:
                try:
                    my_player_mem = self.newmem + 0x200
                    self.pm.write_ulonglong(my_player_mem, 0)
                except Exception:
                    pass

    def _connect_world_monitor(self):
        try:
            self._world_monitor.add_listener(self._on_world_status_changed)
            if self._world_monitor.world_status == 1:
                self._scan_request.set()
        except Exception:
            pass

    def _disconnect_world_monitor(self):
        try:
            self._world_monitor.remove_listener(self._on_world_status_changed)
        except Exception:
            pass

    def _on_mc_active_changed(self, is_active: bool):
        with self._state_lock:
            self._mc_active_cache = is_active

    def _connect_window_monitor(self):
        try:
            monitor = _get_window_monitor()
            monitor.add_listener(self._on_mc_active_changed)
            current = monitor.get_is_active()
            with self._state_lock:
                self._mc_active_cache = current
            self._window_monitor_ref = monitor
        except Exception:
            with self._state_lock:
                self._mc_active_cache = True
            self._window_monitor_ref = None

    def _disconnect_window_monitor(self):
        try:
            if self._window_monitor_ref is not None:
                self._window_monitor_ref.remove_listener(self._on_mc_active_changed)
                self._window_monitor_ref = None
        except Exception:
            pass

    def _is_minecraft_active(self) -> bool:
        with self._state_lock:
            return self._mc_active_cache

    def _is_menu_open(self) -> bool:
        try:
            return self._menu_monitor.is_menu_open
        except Exception:
            return False

    def monitor_keybind(self):
        while self.keybind_monitoring_active and not self.should_stop.is_set():
            try:
                new_key = self.config_manager.get_keybind("jump") or "space"
                if new_key != self.current_key:
                    self.current_key = new_key
                    self.jump_key    = new_key
                    self._jump_vk    = _resolve_vk(new_key)
            except Exception:
                pass
            self.should_stop.wait(timeout=0.3)

    def start_keybind_monitoring(self):
        if not self.keybind_monitoring_active:
            self.keybind_monitoring_active = True
            self.keybind_monitor_thread = threading.Thread(
                target=self.monitor_keybind, daemon=True
            )
            self.keybind_monitor_thread.start()

    def stop_keybind_monitoring(self):
        if self.keybind_monitoring_active:
            self.keybind_monitoring_active = False
            if (self.keybind_monitor_thread
                    and threading.current_thread() is not self.keybind_monitor_thread):
                try:
                    self.keybind_monitor_thread.join(timeout=1)
                except Exception:
                    pass
            self.keybind_monitor_thread = None

    def set_version_config(self, version_config, full_version=None):
        self.version_config = version_config
        if full_version:
            self.full_version      = full_version
            self.minecraft_version = self._normalize_version(full_version)
        else:
            version_string         = version_config.get('series') if version_config else None
            self.minecraft_version = self._normalize_version(version_string)
        if not JumpResetController.is_supported_version(self.minecraft_version):
            self.minecraft_version = None
        self.inject_pattern = self._get_inject_pattern(self.minecraft_version)

    def set_pymem_process(self, pm):
        self.pm             = pm
        self.process_handle = pm.process_handle

    def set_update_queue(self, queue):
        self.update_queue = queue

    def set_jump_key(self, key):
        self.jump_key    = key
        self.current_key = key
        self._jump_vk    = _resolve_vk(key)

    def set_jump_timing(self, hold_time):
        self.jump_hold_time = hold_time

    def _send_status_update(self, message, color):
        if self.update_queue:
            self.update_queue.put(('status_update', ('jumpreset', message, color)))

    def compile_wildcard_pattern(self, pattern):
        parts = pattern.split()
        regex_parts = []
        for part in parts:
            if part == '??':
                regex_parts.append(b'.')
            else:
                regex_parts.append(bytes.fromhex(part))
        return b''.join(regex_parts)

    def scan_player_address(self, silent=False):
        if not self.minecraft_version:
            return False
        pattern_key = JumpResetController.get_pattern_version(self.minecraft_version)
        if not pattern_key or pattern_key not in self.PLAYER_PATTERNS:
            return False
        player_pattern = self.PLAYER_PATTERNS[pattern_key]
        try:
            regex_pattern = self.compile_wildcard_pattern(player_pattern)
            mbi     = MEMORY_BASIC_INFORMATION()
            address = 0
            while kernel32.VirtualQueryEx(
                self.process_handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi)
            ):
                if mbi.Protect == PAGE_READWRITE:
                    try:
                        memory = self.pm.read_bytes(mbi.BaseAddress, mbi.RegionSize)
                        for match in re.finditer(regex_pattern, memory, re.DOTALL):
                            match_address = mbi.BaseAddress + match.start()
                            if match_address != self.my_player:
                                print(f"JumpReset: Player address at 0x{match_address:X}")
                            with self._state_lock:
                                self.my_player       = match_address
                                self.player_in_world = True
                            if self.newmem:
                                my_player_mem = self.newmem + 0x200
                                self.pm.write_ulonglong(my_player_mem, self.my_player)
                            try:
                                self._world_monitor.set_world_status(1)
                            except Exception:
                                pass
                            return True
                    except Exception:
                        pass
                address += mbi.RegionSize
                if address >= 0x7FFFFFFFFFFFFFFF:
                    break
            with self._state_lock:
                self.player_in_world = False
            return False
        except Exception:
            return False

    def _world_enter_scan_loop(self):
        while not self.should_stop.is_set():
            triggered = self._scan_request.wait(timeout=1.0)
            if self.should_stop.is_set():
                break
            if not triggered:
                continue

            self._scan_request.clear()

            if not self.is_active:
                continue

            max_retry   = 10
            retry_delay = 0.5
            for attempt in range(max_retry):
                if self.should_stop.is_set():
                    break
                success = self.scan_player_address(silent=False)
                if success:
                    if not self.newmem and self.target_addr:
                        self.install_hook()
                    break
                self.should_stop.wait(timeout=retry_delay)

    def allocate_near(self, base_addr: int, size: int = 0x1000):
        start      = base_addr & 0xFFFFFFFFFFFF0000
        max_offset = 0x7FF00000
        step       = 0x10000
        for offset in range(0, max_offset, step):
            for direction in [1, -1]:
                addr = start + (offset * direction)
                if addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
                    continue
                try:
                    mem = self.VirtualAllocEx(
                        self.process_handle, ctypes.c_void_p(addr), size,
                        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE
                    )
                    if mem:
                        if abs(mem - base_addr) < 0x7FF00000:
                            return mem
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

    def scan_aob(self):
        try:
            module = pymem.process.module_from_name(self.process_handle, "Minecraft.Windows.exe")
            base   = module.lpBaseOfDll
            size   = module.SizeOfImage
            data   = self.pm.read_bytes(base, size)
            matches = [m.start() for m in re.finditer(re.escape(self.inject_pattern), data)]
            if not matches:
                return False
            self.target_addr    = base + matches[0]
            self.original_bytes = self.pm.read_bytes(self.target_addr, 10)
            print(f"JumpReset: Initialized at 0x{self.target_addr:X}")
            return True
        except Exception:
            return False

    def install_hook(self):
        if not self.target_addr or not self.my_player:
            return False
        use_legacy = self._is_legacy_version(self.minecraft_version)
        try:
            self.newmem      = self.allocate_near(self.target_addr, 0x1000)
            self.damage_flag = self.newmem + 0x100
            my_player_mem    = self.newmem + 0x200
            self.pm.write_ulonglong(my_player_mem, self.my_player)

            if use_legacy:
                self.pm.write_bytes(self.damage_flag, b'\x00', 1)
                shellcode = bytearray()
                shellcode += b"\x50"
                shellcode += b"\x48\xA1" + struct.pack("<Q", my_player_mem)
                shellcode += b"\x48\x39\xC7"
                shellcode += b"\x58"
                jne_ph = len(shellcode)
                shellcode += b"\x75\x00"
                rip = self.newmem + len(shellcode) + 7
                disp32 = self.damage_flag - rip
                if not (-0x80000000 <= disp32 <= 0x7FFFFFFF):
                    raise RuntimeError(f"RIP offset out of range: {hex(disp32)}")
                shellcode += b"\xC6\x05" + struct.pack("<i", disp32) + b"\x02"
                shellcode[jne_ph + 1] = len(shellcode) - (jne_ph + 2)
                shellcode += b"\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00"
                return_addr    = self.target_addr + 10
                jmp_back       = return_addr - (self.newmem + len(shellcode) + 5)
                if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                    shellcode += b"\xE9" + struct.pack("<i", jmp_back)
                else:
                    shellcode += b"\x48\xB8" + struct.pack("<Q", return_addr) + b"\xFF\xE0"
            else:
                self.pm.write_int(self.damage_flag, 0)
                shellcode = bytearray()
                shellcode += b"\x50"
                shellcode += b"\x48\xA1" + struct.pack("<Q", my_player_mem)
                shellcode += b"\x48\x39\xC7"
                shellcode += b"\x58"
                jne_ph = len(shellcode)
                shellcode += b"\x75\x00"
                rip = self.newmem + len(shellcode) + 6
                disp32 = self.damage_flag - rip
                if not (-0x80000000 <= disp32 <= 0x7FFFFFFF):
                    raise RuntimeError(f"RIP offset out of range: {hex(disp32)}")
                shellcode += b"\x00\x05" + struct.pack("<i", disp32)
                shellcode[jne_ph + 1] = len(shellcode) - (jne_ph + 2)
                shellcode += b"\xC7\x87\x9C\x01\x00\x00\x0A\x00\x00\x00"
                return_addr = self.target_addr + 10
                jmp_back    = return_addr - (self.newmem + len(shellcode) + 5)
                if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                    shellcode += b"\xE9" + struct.pack("<i", jmp_back)
                else:
                    shellcode += b"\x48\xB8" + struct.pack("<Q", return_addr) + b"\xFF\xE0"

            self.pm.write_bytes(self.newmem, bytes(shellcode), len(shellcode))

            jmp_offset = self.newmem - (self.target_addr + 5)
            if not (-0x80000000 <= jmp_offset <= 0x7FFFFFFF):
                raise RuntimeError(f"Jump offset too far: {hex(jmp_offset)}")

            jmp_bytes  = b"\xE9" + struct.pack("<i", jmp_offset)
            multi_nop  = b"\x0F\x1F\x44\x00\x00"
            old_prot   = wintypes.DWORD()
            kernel32.VirtualProtectEx(
                self.process_handle, ctypes.c_void_p(self.target_addr), 10,
                PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot)
            )
            self.pm.write_bytes(self.target_addr, jmp_bytes, 5)
            self.pm.write_bytes(self.target_addr + 5, multi_nop, 5)
            kernel32.VirtualProtectEx(
                self.process_handle, ctypes.c_void_p(self.target_addr), 10,
                old_prot.value, ctypes.byref(old_prot)
            )
            return True
        except Exception:
            return False

    def monitor_damage(self):
        use_byte_flag = self._is_legacy_version(self.minecraft_version)

        while not self.should_stop.is_set():
            if not self.is_active or not self.my_player or not self.damage_flag:
                self.should_stop.wait(timeout=0.06)
                continue

            try:
                if use_byte_flag:
                    flag = self.pm.read_bytes(self.damage_flag, 1)[0]
                else:
                    flag = self.pm.read_int(self.damage_flag)

                if flag > 0:
                    if use_byte_flag:
                        self.pm.write_bytes(self.damage_flag, b'\x00', 1)
                    else:
                        self.pm.write_int(self.damage_flag, 0)

                    with self._state_lock:
                        in_world = self.player_in_world

                    now = time.time()
                    if now - self._last_hit_time > self._combo_window:
                        self._hit_count = 0
                    self._hit_count    += 1
                    self._last_hit_time = now

                    if (self._hit_count >= 2
                            and self._is_minecraft_active()
                            and in_world
                            and not self._is_menu_open()):
                        try:
                            vk         = self._jump_vk
                            press_time = self.jump_hold_time + random.uniform(-0.015, 0.025)
                            _press_key(vk)
                            time.sleep(press_time)
                            _release_key(vk)
                        except Exception:
                            pass

            except Exception:
                self.should_stop.wait(timeout=0.2)
                continue

            self.should_stop.wait(timeout=0.033)

    def _initialize_async(self):
        try:
            self.scan_player_address(silent=False)
            if not self.scan_aob():
                return
            if self.my_player:
                self.install_hook()
            self.initialized = True
        except Exception:
            pass

    def initialize(self):
        if not self.pm or not self.process_handle:
            return False
        if not self.minecraft_version:
            return False
        if not JumpResetController.is_supported_version(self.minecraft_version):
            return False
        print(f"JumpReset: Initializing for version {self.minecraft_version}...")
        self.scan_player_address(silent=False)
        if not self.scan_aob():
            return False
        if self.my_player:
            self.install_hook()
        self.initialized = True
        return True

    def _join_all_threads(self):
        for t in (self.monitor_thread, self.auto_hook_thread, self._scan_thread):
            if t and t.is_alive() and threading.current_thread() is not t:
                try:
                    t.join(timeout=1.0)
                except Exception:
                    pass

    def start(self):
        if not self.pm or not self.process_handle:
            self._send_status_update("Not initialized", '#ff9800')
            return
        if not self.minecraft_version or not JumpResetController.is_supported_version(self.minecraft_version):
            self._send_status_update("Not initialized", '#ff9800')
            return
        if self.is_active:
            return

        self.should_stop.clear()
        self.is_active = True
        self._hit_count     = 0
        self._last_hit_time = 0.0
        self._scan_request.clear()

        if self._window_monitor_ref is None:
            self._connect_window_monitor()
        else:
            try:
                with self._state_lock:
                    self._mc_active_cache = self._window_monitor_ref.get_is_active()
            except Exception:
                with self._state_lock:
                    self._mc_active_cache = True

        try:
            self._menu_monitor.start()
        except Exception:
            pass

        self._connect_world_monitor()

        if not self.keybind_monitoring_active:
            self.start_keybind_monitoring()

        self.monitor_thread   = threading.Thread(target=self.monitor_damage,       daemon=True)
        self.auto_hook_thread = threading.Thread(target=self._auto_hook_installer, daemon=True)
        self._scan_thread     = threading.Thread(target=self._world_enter_scan_loop, daemon=True)

        self.monitor_thread.start()
        self.auto_hook_thread.start()
        self._scan_thread.start()

        if not self.initialized:
            threading.Thread(target=self._initialize_async, daemon=True).start()
        elif not self.newmem and self.target_addr and self.my_player:
            threading.Thread(target=self.install_hook, daemon=True).start()

        self._send_status_update("Active", '#00e676')

    def _auto_hook_installer(self):
        while not self.should_stop.is_set():
            try:
                if not self.newmem and self.my_player and self.target_addr:
                    self.install_hook()
            except Exception:
                pass
            self.should_stop.wait(timeout=2.0)

    def stop(self, is_app_closing=False):
        if not self.is_active:
            return
        self.should_stop.set()
        self.is_active = False
        self._scan_request.set()
        self.stop_keybind_monitoring()
        self._disconnect_world_monitor()
        self._join_all_threads()
        if not is_app_closing:
            self._send_status_update("Inactive", '#a0a0b0')

    def _is_process_alive(self):
        if not self.pm or not self.process_handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(
                self.process_handle, ctypes.byref(exit_code)
            ) == 0:
                return False
            return exit_code.value == 259
        except Exception:
            return False

    def reset_to_default(self, is_app_closing=False):
        self.should_stop.set()
        self.is_active = False
        self._scan_request.set()
        self.stop_keybind_monitoring()
        self._disconnect_world_monitor()
        self._join_all_threads()
        self._disconnect_window_monitor()

        if not self._is_process_alive():
            self.initialized = False
            self.newmem      = None
            self.damage_flag = None
            return

        if not self.target_addr or not self.original_bytes:
            self.initialized = False
            self.newmem      = None
            self.damage_flag = None
            return

        try:
            old_prot = wintypes.DWORD()
            kernel32.VirtualProtectEx(
                self.process_handle, ctypes.c_void_p(self.target_addr), 10,
                PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot)
            )
            self.pm.write_bytes(self.target_addr, self.original_bytes, 10)
            kernel32.VirtualProtectEx(
                self.process_handle, ctypes.c_void_p(self.target_addr), 10,
                old_prot.value, ctypes.byref(old_prot)
            )
        except Exception:
            pass

        if self.newmem:
            try:
                kernel32.VirtualFreeEx(
                    self.process_handle, ctypes.c_void_p(self.newmem), 0, MEM_RELEASE
                )
            except Exception:
                pass
            self.newmem = None

        self.damage_flag = None
        self.initialized = False

    def validate_process(self):
        if not self.pm or not self.process_handle:
            return False
        try:
            self.pm.read_int(self.pm.base_address)
            return True
        except Exception:
            return False

    def cleanup(self):
        self.stop_keybind_monitoring()
        self.reset_to_default(is_app_closing=True)