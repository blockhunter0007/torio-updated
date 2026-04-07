from __future__ import annotations

import collections
import ctypes
import ctypes.wintypes as wintypes
import math
import queue
import re
import struct
import threading
import time

import pymem
import pymem.process

from core.menu_monitor import get_shared_menu_monitor as _get_menu_monitor
from core.minecraft_windowmonitor import get_shared_window_monitor as _get_window_monitor
from core.input_scheduler import get_shared_input_scheduler, InputPriority
from core.click_priority import is_clicking_within_window, set_aim_tracking
import win32api

ctypes.windll.winmm.timeBeginPeriod(1)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

MAX_ENTITIES      = 100
RESET_INTERVAL    = 3.5

BASE_W   = 2560
BASE_H   = 1440
BASE_FOV = 110.0

DOT_RADIUS_BASE = 5

ESP_MAX_DIST      = 6.0
SELF_EXCLUDE_DIST = 2.7

_y_offset_lock         = threading.Lock()
_y_offset_player_value = 1.8
_y_offset_other_value  = 0.9

def _get_y_offset_player() -> float:
    with _y_offset_lock:
        return _y_offset_player_value

def _get_y_offset_other() -> float:
    with _y_offset_lock:
        return _y_offset_other_value

def _set_y_offset_player(value: float):
    global _y_offset_player_value
    value = max(1.10, min(2.60, round(float(value), 2)))
    with _y_offset_lock:
        _y_offset_player_value = value

def _set_y_offset_other(value: float):
    global _y_offset_other_value
    value = max(-0.20, min(1.50, round(float(value), 2)))
    with _y_offset_lock:
        _y_offset_other_value = value

_esp_max_dist_lock  = threading.Lock()
_esp_max_dist_value = ESP_MAX_DIST

def _get_esp_max_dist() -> float:
    with _esp_max_dist_lock:
        return _esp_max_dist_value

def _set_esp_max_dist(value: float):
    global _esp_max_dist_value
    value = max(3.0, min(8.0, round(float(value), 2)))
    with _esp_max_dist_lock:
        _esp_max_dist_value = value

_target_mode_lock   = threading.Lock()
_aim_player_enabled = True
_aim_other_enabled  = False

def _get_target_mode() -> tuple[bool, bool]:
    with _target_mode_lock:
        return _aim_player_enabled, _aim_other_enabled

def _set_target_mode(player: bool, other: bool):
    global _aim_player_enabled, _aim_other_enabled
    with _target_mode_lock:
        _aim_player_enabled = player
        _aim_other_enabled  = other

_TAG_PLAYER = "player"
_TAG_OTHER  = "other"

CORRECTION_SOUTH_BASE = -42
CORRECTION_NORTH_BASE =  47
CORRECTION_EAST_BASE  = -67
CORRECTION_WEST_BASE  =  47

EDGE_CORRECTION_SCALE_X_BASE = -50
EDGE_CORRECTION_SCALE_Y_BASE = -30

PREDICT_SCALE_MOVE = 1.0
DOT_SMOOTH_ALPHA   = 0.05
VEL_SMOOTH_ALPHA   = 0.05
DOT_JUMP_THRESHOLD = 200.0

AIM_DEADZONE_RATE = 0.060

LAG_BOOST_MAX       = 0.10
CONN_RESUME_ALPHA   = 0.90
CONN_DEADZONE_GRACE = 8
CONN_REVERSAL_DECAY = 0.40
CONN_SMOOTH_PERSIST = 0.05

BASE_SENSITIVITY = 0.32

AIM_PARAM_TABLE = {
    (2560, 110): (15.1,  0.33),
    (2560,  70): (13.0,  0.28),
    (1920, 110): (15.1,  0.33),
    (1920,  70): (13.0,  0.278),
    (1280, 110): ( 5.62, 0.17),
    (1280,  70): ( 5.15, 0.155),
}
HEIGHT_SCALE = 0.29

STRAFE_PREDICT_TIME  = 0.07
STRAFE_VEL_ALPHA     = 0.15
STRAFE_ACCEL_SCALE   = 0.15

PAGE_EXECUTE_READWRITE = 0x40
MEM_COMMIT             = 0x1000
MEM_RESERVE            = 0x2000
MEM_RELEASE            = 0x8000

MOUSEEVENTF_MOVE = 0x0001

SELF_TRAIL_LENGTH     = 240
SELF_TRAIL_MATCH_DIST = 2.2
SELF_TRAIL_DELAY_MAX  = 0.40
SELF_ENT_OFFSET_Y     = 1.62
SELF_SCORE_PROMOTE    = 0.18
SELF_SCORE_DECAY      = 0.015
SELF_SCORE_THRESHOLD  = 0.55


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]

class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT_UNION)]

_user32   = ctypes.WinDLL("user32",   use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _send_mouse_move(dx: int, dy: int):
    try:
        inp = _INPUT()
        inp.type = 0
        inp._input.mi.dx      = dx
        inp._input.mi.dy      = dy
        inp._input.mi.dwFlags = MOUSEEVENTF_MOVE
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    except Exception:
        pass


_sensitivity_lock    = threading.Lock()
_current_sensitivity = BASE_SENSITIVITY


def get_monitor_refresh_rate() -> int:
    try:
        devmode = win32api.EnumDisplaySettings(None, -1)
        freq = devmode.DisplayFrequency
        if 50 <= freq <= 720:
            return int(freq)
        else:
            print(f"Warning: Abnormal refresh rate detected {freq}Hz → falling back to 144Hz")
            return 144
    except Exception as e:
        print(f"Failed to get refresh rate: {e} → Falling back to 144Hz")
        return 144


def _get_sensitivity_scale() -> float:
    with _sensitivity_lock:
        s = _current_sensitivity
    return BASE_SENSITIVITY / s


def _set_sensitivity(value: float):
    global _current_sensitivity
    value = max(0.01, min(1.00, round(value, 2)))
    with _sensitivity_lock:
        _current_sensitivity = value


def _lookup_aim_params(sw: int, fov: float) -> tuple[float, float]:
    widths = sorted(set(w for w, _ in AIM_PARAM_TABLE))
    fovs   = sorted(set(f for _, f in AIM_PARAM_TABLE))

    def lerp(a, b, t):
        return a + (b - a) * t

    def clamp_interp(vals, v):
        if v <= vals[0]:  return vals[0], vals[0],  0.0
        if v >= vals[-1]: return vals[-1], vals[-1], 0.0
        for i in range(len(vals) - 1):
            if vals[i] <= v <= vals[i + 1]:
                t = (v - vals[i]) / (vals[i + 1] - vals[i])
                return vals[i], vals[i + 1], t
        return vals[-1], vals[-1], 0.0

    w0, w1, wt = clamp_interp(widths, sw)
    f0, f1, ft = clamp_interp(fovs,   fov)

    def get(w, f):
        return AIM_PARAM_TABLE.get(
            (w, f),
            AIM_PARAM_TABLE[min(AIM_PARAM_TABLE, key=lambda k: abs(k[0] - w) + abs(k[1] - f))]
        )

    mm00, sm00 = get(w0, f0)
    mm01, sm01 = get(w0, f1)
    mm10, sm10 = get(w1, f0)
    mm11, sm11 = get(w1, f1)

    mm = lerp(lerp(mm00, mm01, ft), lerp(mm10, mm11, ft), wt)
    sm = lerp(lerp(sm00, sm01, ft), lerp(sm10, sm11, ft), wt)
    return mm, max(0.05, min(0.99, sm))


def _get_scaled_params(sw: int, sh: int, fov: float) -> dict:
    MAX_SENS_SCALE = 36.0
    rs = sw / BASE_W
    ss = min(_get_sensitivity_scale(), MAX_SENS_SCALE)

    aim_max_move, aim_smoothing = _lookup_aim_params(sw, fov)
    aim_max_move = aim_max_move * ss

    with _monitor_hz_lock:
        fps_boost = _FPS_BOOST_SCALE
    aim_max_move = aim_max_move * fps_boost

    with _sensitivity_lock:
        cur_sens = _current_sensitivity
    if cur_sens <= 0.09:
        aim_max_move = aim_max_move * 2.0

    return {
        "res_scale"    : rs,
        "sens_scale"   : ss,
        "corr_s"       : CORRECTION_SOUTH_BASE * rs,
        "corr_n"       : CORRECTION_NORTH_BASE * rs,
        "corr_e"       : CORRECTION_EAST_BASE  * rs,
        "corr_w"       : CORRECTION_WEST_BASE  * rs,
        "edge_x"       : EDGE_CORRECTION_SCALE_X_BASE * rs,
        "edge_y"       : EDGE_CORRECTION_SCALE_Y_BASE * rs,
        "aim_max_move" : aim_max_move,
        "aim_smoothing": aim_smoothing,
        "dot_jump_thr" : DOT_JUMP_THRESHOLD * rs,
        "dot_radius"   : max(2, round(DOT_RADIUS_BASE * rs)),
    }


def _get_direction_correction(
    fx: float, fz: float,
    sx: float, sy: float,
    sw: int, sh: int,
    dist: float,
    sp: dict,
) -> tuple[float, float]:
    dist_scale = max(1.0, dist / 80.0)
    yaw = math.degrees(math.atan2(-fx, fz)) % 360
    anchors = [
        (0,   sp["corr_s"]),
        (90,  sp["corr_w"]),
        (180, sp["corr_n"]),
        (270, sp["corr_e"]),
        (360, sp["corr_s"]),
    ]
    base_correction = sp["corr_s"]
    for i in range(len(anchors) - 1):
        a0, c0 = anchors[i]
        a1, c1 = anchors[i + 1]
        if a0 <= yaw <= a1:
            t = (yaw - a0) / (a1 - a0)
            t_smooth = (1 - math.cos(t * math.pi)) / 2
            base_correction = c0 + (c1 - c0) * t_smooth
            break
    cx_ = sw / 2
    offset_x = (sx - cx_) / cx_
    edge_correction_x = offset_x * sp["edge_x"]
    cy_ = sh / 2
    offset_y = (sy - cy_) / cy_
    edge_correction_y = offset_y * sp["edge_y"]
    return (base_correction + edge_correction_x) * dist_scale, edge_correction_y * dist_scale


def _world_to_screen(
    ex: float, ey: float, ez: float,
    px: float, py: float, pz: float,
    fwd_x: float, fwd_y: float, fwd_z: float,
    fov_deg: float, sw: int, sh: int,
) -> tuple[float, float] | None:
    dx, dy, dz = ex - px, ey - py, ez - pz
    length = math.sqrt(fwd_x ** 2 + fwd_y ** 2 + fwd_z ** 2)
    if length < 1e-6:
        return None
    fx, fy, fz = fwd_x / length, fwd_y / length, fwd_z / length

    hlen = math.sqrt(fx ** 2 + fz ** 2)
    rx, rz = (fz / hlen, -fx / hlen) if hlen >= 1e-5 else (1.0, 0.0)

    ux, uy, uz = -fy * fx, 1.0 - fy * fy, -fy * fz
    ulen = math.sqrt(ux ** 2 + uy ** 2 + uz ** 2)
    if ulen < 1e-5:
        ux, uy, uz = 0.0, 0.0, -1.0
    else:
        ux, uy, uz = ux / ulen, uy / ulen, uz / ulen

    view_z = dx * fx + dy * fy + dz * fz
    view_x = dx * rx + dz * rz
    view_y = dx * ux + dy * uy + dz * uz

    dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
    if view_z <= 0 or view_z < 0.02 * dist:
        return None

    f_v  = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    f_h  = f_v / (sw / sh)
    sx_f = sw / 2 - (view_x / view_z) * f_h * (sw / 2)
    sy_f = sh / 2 - (view_y / view_z) * f_v * (sh / 2)

    if not math.isfinite(sx_f) or not math.isfinite(sy_f):
        return None
    return sx_f, sy_f


class _SelfPtrLocker:
    def __init__(self):
        self._trail: collections.deque = collections.deque(maxlen=SELF_TRAIL_LENGTH)
        self._scores: dict[int, float] = {}
        self._self_ptr: int | None = None

    def add_trail(self, px: float, py: float, pz: float):
        self._trail.append((px, py + SELF_ENT_OFFSET_Y, pz, time.perf_counter()))

    def _matches_trail(self, ex: float, ey: float, ez: float) -> bool:
        now = time.perf_counter()
        thr = SELF_TRAIL_MATCH_DIST ** 2
        trail_copy = list(self._trail)
        for tx, ty, tz, t in trail_copy:
            if now - t > SELF_TRAIL_DELAY_MAX:
                continue
            if (ex-tx)**2 + (ey-ty)**2 + (ez-tz)**2 <= thr:
                return True
        return False

    def update(self, entities: list, player_base: int) -> int | None:
        current_ptrs = {ptr for _, _, _, ptr in entities}

        if player_base in current_ptrs:
            self._self_ptr = player_base
            self._scores[player_base] = 1.0

        for ptr in list(self._scores.keys()):
            if ptr not in current_ptrs:
                del self._scores[ptr]

        for x, y, z, ptr in entities:
            if ptr == player_base:
                continue
            if ptr not in self._scores:
                self._scores[ptr] = 0.0
            if self._matches_trail(x, y, z):
                self._scores[ptr] = min(1.0, self._scores[ptr] + SELF_SCORE_PROMOTE)
            else:
                self._scores[ptr] = max(0.0, self._scores[ptr] - SELF_SCORE_DECAY)

        if self._scores:
            best_ptr, best_score = max(self._scores.items(), key=lambda kv: kv[1])
            if best_score >= SELF_SCORE_THRESHOLD:
                self._self_ptr = best_ptr
            elif self._self_ptr not in self._scores:
                self._self_ptr = None

        return self._self_ptr

    def invalidate(self):
        self._trail.clear()
        self._scores.clear()
        self._self_ptr = None


class _EnemyVelocityTracker:
    def __init__(self):
        self._state: dict[int, tuple] = {}

    def update(self, ptr: int, sx: float, sy: float) -> tuple[float, float]:
        now = time.perf_counter()
        if ptr not in self._state:
            self._state[ptr] = (sx, sy, 0.0, 0.0, 0.0, 0.0, now)
            return 0.0, 0.0

        prev_sx, prev_sy, prev_vx, prev_vy, prev_ax, prev_ay, prev_t = self._state[ptr]
        dt = now - prev_t
        if dt <= 0 or dt > 0.5:
            self._state[ptr] = (sx, sy, 0.0, 0.0, 0.0, 0.0, now)
            return 0.0, 0.0

        raw_vx = (sx - prev_sx) / dt
        raw_vy = (sy - prev_sy) / dt
        vx = STRAFE_VEL_ALPHA * raw_vx + (1.0 - STRAFE_VEL_ALPHA) * prev_vx
        vy = STRAFE_VEL_ALPHA * raw_vy + (1.0 - STRAFE_VEL_ALPHA) * prev_vy

        raw_ax = (vx - prev_vx) / dt
        raw_ay = (vy - prev_vy) / dt
        ax = STRAFE_VEL_ALPHA * raw_ax + (1.0 - STRAFE_VEL_ALPHA) * prev_ax
        ay = STRAFE_VEL_ALPHA * raw_ay + (1.0 - STRAFE_VEL_ALPHA) * prev_ay

        self._state[ptr] = (sx, sy, vx, vy, ax, ay, now)

        t = STRAFE_PREDICT_TIME
        ox = vx * t + 0.5 * ax * t * t * STRAFE_ACCEL_SCALE
        oy = vy * t + 0.5 * ay * t * t * STRAFE_ACCEL_SCALE
        return ox, oy

    def remove(self, ptr: int):
        self._state.pop(ptr, None)

    def clear_except(self, active_ptrs: set):
        for ptr in list(self._state.keys()):
            if ptr not in active_ptrs:
                self._state.pop(ptr)


class _SharedData:
    def __init__(self):
        self.player:       tuple | None = None
        self.forward:      tuple | None = None
        self.fov:          float | None = None
        self.entities:     list         = []
        self.move_vx       = 0.0
        self.move_vy       = 0.0
        self.move_vz       = 0.0
        self.player_time   = 0.0
        self.aim_target:   tuple | None = None
        self.self_ptr_locker: _SelfPtrLocker = _SelfPtrLocker()


class _HookBase:
    def __init__(self, pm: pymem.Pymem):
        self.pm             = pm
        self.process_handle = pm.process_handle
        self.target_addr    = None
        self.newmem         = None
        self.original_bytes = None
        self._patched       = False

        self.VirtualAllocEx = _kernel32.VirtualAllocEx
        self.VirtualAllocEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD,
        ]
        self.VirtualAllocEx.restype = wintypes.LPVOID

        self.VirtualFreeEx = _kernel32.VirtualFreeEx
        self.VirtualFreeEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
        ]
        self.VirtualFreeEx.restype = wintypes.BOOL

        self.VirtualProtectEx = _kernel32.VirtualProtectEx
        self.VirtualProtectEx.argtypes = [
            wintypes.HANDLE, wintypes.LPVOID,
            ctypes.c_size_t, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.VirtualProtectEx.restype = wintypes.BOOL

    def allocate_near(self, base_addr: int, size: int = 0x2000) -> int:
        start = base_addr & 0xFFFFFFFFFFFF0000
        for offset in range(0, 0x7FF00000, 0x10000):
            for d in [1, -1]:
                addr = start + offset * d
                if addr < 0x10000 or addr > 0x7FFFFFFFFFFF:
                    continue
                try:
                    mem = self.VirtualAllocEx(
                        self.process_handle, ctypes.c_void_p(addr),
                        size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE,
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
        raise MemoryError("allocate_near: failed")

    def scan_aob(self, pattern: bytes, patch_len: int) -> bool:
        try:
            module = pymem.process.module_from_name(
                self.process_handle, "Minecraft.Windows.exe"
            )
            base = module.lpBaseOfDll
            data = self.pm.read_bytes(base, module.SizeOfImage)
            matches = [m.start() for m in re.finditer(re.escape(pattern), data)]
            if not matches:
                return False
            self.target_addr    = base + matches[0]
            self.original_bytes = self.pm.read_bytes(self.target_addr, patch_len)
            return True
        except Exception:
            return False

    def rip_disp(self, target_val: int, sc: bytearray, instr_total_len: int) -> bytes:
        rip  = self.newmem + len(sc) + instr_total_len
        disp = target_val - rip
        if not (-0x80000000 <= disp <= 0x7FFFFFFF):
            raise RuntimeError(f"RIP out of range: {hex(disp)}")
        return struct.pack("<i", disp)

    def write_patch(self, patch_len: int):
        jmp_disp = self.newmem - (self.target_addr + 5)
        if not (-0x80000000 <= jmp_disp <= 0x7FFFFFFF):
            raise RuntimeError("newmem too far")
        patch    = b'\xE9' + struct.pack("<i", jmp_disp) + b'\x90' * (patch_len - 5)
        old_prot = wintypes.DWORD()
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(self.target_addr),
            patch_len, PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot),
        )
        self.pm.write_bytes(self.target_addr, patch, patch_len)
        self.VirtualProtectEx(
            self.process_handle, ctypes.c_void_p(self.target_addr),
            patch_len, old_prot.value, ctypes.byref(old_prot),
        )
        self._patched = True

    def reset(self, patch_len: int):
        if self._patched and self.target_addr and self.original_bytes:
            try:
                old_prot = wintypes.DWORD()
                self.VirtualProtectEx(
                    self.process_handle, ctypes.c_void_p(self.target_addr),
                    patch_len, PAGE_EXECUTE_READWRITE, ctypes.byref(old_prot),
                )
                self.pm.write_bytes(self.target_addr, self.original_bytes, patch_len)
                self.VirtualProtectEx(
                    self.process_handle, ctypes.c_void_p(self.target_addr),
                    patch_len, old_prot.value, ctypes.byref(old_prot),
                )
            except Exception:
                pass
        if self.newmem:
            self.VirtualFreeEx(
                self.process_handle, ctypes.c_void_p(self.newmem), 0, MEM_RELEASE,
            )
            self.newmem = None
        self._patched = False

class _PlayerEntityESPHook(_HookBase):
    PATTERN   = b'\xF3\x0F\x11\x8F\x94\x05\x00\x00'
    PATCH_LEN = 8

    def __init__(self, pm: pymem.Pymem):
        super().__init__(pm)
        self.entity_list_addr  = None
        self.entity_count_addr = None
        self.hit_count_addr    = None

    def install(self) -> bool:
        if not self.scan_aob(self.PATTERN, self.PATCH_LEN):
            return False
        try:
            self.newmem = self.allocate_near(self.target_addr, 0x4000)
            db = self.newmem + 0x1000
            self.entity_list_addr  = db
            self.entity_count_addr = db + 320
            self.hit_count_addr    = db + 324
            self.pm.write_bytes(db, b'\x00' * 328, 328)

            sc = bytearray()
            sc += b'\xF3\x0F\x11\x8F\x94\x05\x00\x00'
            sc += b'\x50\x51\x52'
            sc += b'\x8B\x05' + self.rip_disp(self.hit_count_addr, sc, 6)
            sc += b'\xFF\xC0'
            sc += b'\x89\x05' + self.rip_disp(self.hit_count_addr, sc, 6)
            sc += b'\x8B\x05' + self.rip_disp(self.entity_count_addr, sc, 6)
            sc += b'\x3D\x28\x00\x00\x00'
            jge_done_pos = len(sc); sc += b'\x7D\x00'
            sc += b'\x48\x8D\x15' + self.rip_disp(self.entity_list_addr, sc, 7)
            sc += b'\x33\xC9'
            chk_pos = len(sc)
            sc += b'\x3B\x0D' + self.rip_disp(self.entity_count_addr, sc, 6)
            jge_add_pos = len(sc); sc += b'\x7D\x00'
            sc += b'\x48\x3B\x3C\xCA'
            je_done_pos = len(sc); sc += b'\x74\x00'
            sc += b'\xFF\xC1'
            sc += b'\xEB' + struct.pack('b', chk_pos - (len(sc) + 1))
            add_pos = len(sc)
            sc[jge_add_pos + 1] = add_pos - (jge_add_pos + 2)
            sc += b'\x8B\x05' + self.rip_disp(self.entity_count_addr, sc, 6)
            sc += b'\x48\x89\x3C\xC2'
            sc += b'\xFF\xC0'
            sc += b'\x89\x05' + self.rip_disp(self.entity_count_addr, sc, 6)
            done_pos = len(sc)
            sc[jge_done_pos + 1] = done_pos - (jge_done_pos + 2)
            sc[je_done_pos  + 1] = done_pos - (je_done_pos  + 2)
            sc += b'\x5A\x59\x58'

            ret_addr = self.target_addr + self.PATCH_LEN
            jmp_back = ret_addr - (self.newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack("<i", jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack("<Q", ret_addr) + b'\xFF\xE0'

            self.pm.write_bytes(self.newmem, bytes(sc), len(sc))
            self.write_patch(self.PATCH_LEN)
            print(f"PlayerEntityESP: Initialized at 0x{self.target_addr:X}")
            return True
        except Exception:
            import traceback; traceback.print_exc()
            return False

    def reset_hook(self):
        self.reset(self.PATCH_LEN)

    def read_entities(self) -> tuple[int, list]:
        try:
            hit   = struct.unpack("<I", self.pm.read_bytes(self.hit_count_addr,    4))[0]
            count = struct.unpack("<I", self.pm.read_bytes(self.entity_count_addr, 4))[0]
            count = max(0, min(count, MAX_ENTITIES))
        except Exception:
            return 0, []
        entities = []
        for i in range(count):
            try:
                ptr = struct.unpack("<Q", self.pm.read_bytes(
                    self.entity_list_addr + i * 8, 8))[0]
                if ptr == 0:
                    continue
                raw = self.pm.read_bytes(ptr + 0x594, 12)
                x, y, z = struct.unpack_from("<fff", raw)
                if all(math.isfinite(v) and abs(v) < 1_000_000 for v in (x, y, z)):
                    entities.append((x, y, z, ptr))
            except Exception:
                continue
        return hit, entities

class _OtherEntityESPHook(_HookBase):
    PATTERN   = b'\xF2\x0F\x11\x00\x8B\x4D\xE8'
    PATCH_LEN = 7

    OFFSET_PATTERNS = [
        dict(ox=0x00, oy=0x04, oz=0x08, dbl=False),
        dict(ox=0x10, oy=0x14, oz=0x18, dbl=False),
        dict(ox=0x00, oy=0x08, oz=0x10, dbl=True),
        dict(ox=0x04, oy=0x08, oz=0x0C, dbl=False),
    ]

    def __init__(self, pm: pymem.Pymem):
        super().__init__(pm)
        self.entity_list_addr  = None
        self.entity_count_addr = None
        self.hit_count_addr    = None

    def install(self) -> bool:
        if not self.scan_aob(self.PATTERN, self.PATCH_LEN):
            return False
        try:
            self.newmem = self.allocate_near(self.target_addr, 0x4000)
            db = self.newmem + 0x1000
            self.entity_list_addr  = db
            self.entity_count_addr = db + 8000
            self.hit_count_addr    = db + 8004
            self.pm.write_bytes(db, b'\x00' * 8008, 8008)

            sc = bytearray()
            sc += b'\xF2\x0F\x11\x00'
            sc += b'\x8B\x4D\xE8'
            sc += b'\x50\x51\x57'
            sc += b'\x8B\x0D' + self.rip_disp(self.hit_count_addr, sc, 6)
            sc += b'\xFF\xC1'
            sc += b'\x89\x0D' + self.rip_disp(self.hit_count_addr, sc, 6)
            sc += b'\x8B\x0D' + self.rip_disp(self.entity_count_addr, sc, 6)
            sc += b'\x81\xF9\xE8\x03\x00\x00'
            jge_pos = len(sc); sc += b'\x7D\x00'
            sc += b'\x48\x8D\x3D' + self.rip_disp(self.entity_list_addr, sc, 7)
            sc += b'\x33\xC9'
            chk_pos = len(sc)
            sc += b'\x3B\x0D' + self.rip_disp(self.entity_count_addr, sc, 6)
            jge_nf_pos = len(sc); sc += b'\x7D\x00'
            sc += b'\x48\x39\x04\xCF'
            je_le_pos = len(sc); sc += b'\x74\x00'
            sc += b'\xFF\xC1'
            sc += b'\xEB' + struct.pack("b", chk_pos - (len(sc) + 2))
            nf_pos = len(sc)
            sc[jge_nf_pos + 1] = nf_pos - (jge_nf_pos + 2)
            sc += b'\x8B\x0D' + self.rip_disp(self.entity_count_addr, sc, 6)
            sc += b'\x48\x89\x04\xCF'
            sc += b'\xFF\xC1'
            sc += b'\x89\x0D' + self.rip_disp(self.entity_count_addr, sc, 6)
            le_pos = len(sc)
            sc[jge_pos + 1]   = le_pos - (jge_pos + 2)
            sc[je_le_pos + 1] = le_pos - (je_le_pos + 2)
            sc += b'\x5F\x59\x58'
            ret_addr = self.target_addr + self.PATCH_LEN
            jmp_back = ret_addr - (self.newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack("<i", jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack("<Q", ret_addr) + b'\xFF\xE0'

            self.pm.write_bytes(self.newmem, bytes(sc), len(sc))
            self.write_patch(self.PATCH_LEN)
            print(f"OtherEntityESP: Initialized at 0x{self.target_addr:X}")
            return True
        except Exception:
            import traceback; traceback.print_exc()
            return False

    def reset_hook(self):
        self.reset(self.PATCH_LEN)

    def _try_read_coords(self, ptr: int) -> tuple[float | None, float | None, float | None]:
        for p in self.OFFSET_PATTERNS:
            try:
                if p['dbl']:
                    x, y, z = struct.unpack_from("<ddd", self.pm.read_bytes(ptr + p['ox'], 24))
                else:
                    x, y, z = struct.unpack_from("<fff", self.pm.read_bytes(ptr + p['ox'], 12))
                if all(math.isfinite(v) and abs(v) < 1_000_000 for v in (x, y, z)):
                    return x, y, z
            except Exception:
                continue
        return None, None, None

    def read_entities(self) -> tuple[int, list]:
        try:
            hit   = struct.unpack("<I", self.pm.read_bytes(self.hit_count_addr,    4))[0]
            count = struct.unpack("<I", self.pm.read_bytes(self.entity_count_addr, 4))[0]
            count = max(0, min(count, MAX_ENTITIES))
        except Exception:
            return 0, []
        entities = []
        for i in range(count):
            try:
                ptr = struct.unpack("<Q", self.pm.read_bytes(
                    self.entity_list_addr + i * 8, 8))[0]
                if ptr == 0:
                    continue
                x, y, z = self._try_read_coords(ptr)
                if x is not None:
                    entities.append((x, y, z, ptr))
            except Exception:
                continue
        return hit, entities


class _LocalPlayerHook(_HookBase):
    PATTERN   = b'\x41\x0F\x11\x03\xF2\x41\x0F\x11\x53\x10'
    PATCH_LEN = 10

    def __init__(self, pm: pymem.Pymem):
        super().__init__(pm)
        self.slot0_addr = None
        self.slot1_addr = None
        self.slot2_addr = None
        self.base_addr  = None

    def install(self) -> bool:
        if not self.scan_aob(self.PATTERN, self.PATCH_LEN):
            return False
        try:
            self.newmem     = self.allocate_near(self.target_addr, 0x1000)
            db              = self.newmem + 0x800
            self.slot0_addr = db + 0x00
            self.slot1_addr = db + 0x04
            self.slot2_addr = db + 0x08
            self.base_addr  = db + 0x10
            self.pm.write_bytes(db, b'\x00' * 0x18, 0x18)

            sc = bytearray()
            sc += b'\x41\x0F\x11\x03'
            sc += b'\xF2\x41\x0F\x11\x53\x10'
            sc += b'\x50'
            sc += b'\xF3\x45\x0F\x10\x5B\x04'
            sc += b'\xF3\x44\x0F\x11\x1D' + self.rip_disp(self.slot0_addr, sc, 9)
            sc += b'\xF3\x45\x0F\x10\x5B\x08'
            sc += b'\xF3\x44\x0F\x11\x1D' + self.rip_disp(self.slot1_addr, sc, 9)
            sc += b'\xF3\x45\x0F\x10\x5B\x0C'
            sc += b'\xF3\x44\x0F\x11\x1D' + self.rip_disp(self.slot2_addr, sc, 9)
            sc += b'\x4C\x89\xD8'
            sc += b'\x48\x89\x05' + self.rip_disp(self.base_addr, sc, 7)
            sc += b'\x58'

            ret_addr = self.target_addr + self.PATCH_LEN
            jmp_back = ret_addr - (self.newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack("<i", jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack("<Q", ret_addr) + b'\xFF\xE0'

            self.pm.write_bytes(self.newmem, bytes(sc), len(sc))
            self.write_patch(self.PATCH_LEN)
            print(f"LocalPlayer: Initialized at 0x{self.target_addr:X}")
            return True
        except Exception:
            import traceback; traceback.print_exc()
            return False

    def reset_hook(self):
        self.reset(self.PATCH_LEN)

    def read_player(self) -> tuple | None:
        try:
            base = struct.unpack("<Q", self.pm.read_bytes(self.base_addr, 8))[0]
            if base == 0:
                return None
            s0 = struct.unpack("<f", self.pm.read_bytes(self.slot0_addr, 4))[0]
            s1 = struct.unpack("<f", self.pm.read_bytes(self.slot1_addr, 4))[0]
            s2 = struct.unpack("<f", self.pm.read_bytes(self.slot2_addr, 4))[0]
            return s2, s0, s1, base
        except Exception:
            return None


class _YawPitchHook(_HookBase):
    PATTERN   = b'\xF3\x41\x0F\x11\x52\x0C\xF3\x41\x0F\x11'
    PATCH_LEN = 6

    def __init__(self, pm: pymem.Pymem):
        super().__init__(pm)
        self.yaw_addr   = None
        self.pitch_addr = None

    def install(self) -> bool:
        if not self.scan_aob(self.PATTERN, self.PATCH_LEN):
            return False
        try:
            self.newmem = self.allocate_near(self.target_addr, 0x1000)
            db = self.newmem + 0x800
            self.pitch_addr = db + 0x00
            self.yaw_addr   = db + 0x04
            self.pm.write_bytes(db, b'\x00' * 8, 8)

            sc = bytearray()
            sc += b'\xF3\x41\x0F\x11\x52\x0C'
            sc += b'\x50'
            sc += b'\x41\x8B\x02'
            sc += b'\x89\x05' + self.rip_disp(self.pitch_addr, sc, 6)
            sc += b'\x41\x8B\x42\x0C'
            sc += b'\x89\x05' + self.rip_disp(self.yaw_addr, sc, 6)
            sc += b'\x58'

            ret_addr = self.target_addr + self.PATCH_LEN
            jmp_back = ret_addr - (self.newmem + len(sc) + 5)
            if -0x80000000 <= jmp_back <= 0x7FFFFFFF:
                sc += b'\xE9' + struct.pack("<i", jmp_back)
            else:
                sc += b'\x48\xB8' + struct.pack("<Q", ret_addr) + b'\xFF\xE0'

            self.pm.write_bytes(self.newmem, bytes(sc), len(sc))
            self.write_patch(self.PATCH_LEN)
            print(f"YawPitch: Initialized at 0x{self.target_addr:X}")
            return True
        except Exception:
            import traceback; traceback.print_exc()
            return False

    def reset_hook(self):
        self.reset(self.PATCH_LEN)

    def read_forward(self) -> tuple | None:
        try:
            yaw   = struct.unpack("<f", self.pm.read_bytes(self.yaw_addr,   4))[0]
            pitch = struct.unpack("<f", self.pm.read_bytes(self.pitch_addr, 4))[0]
            if not (math.isfinite(yaw) and math.isfinite(pitch)):
                return None
            if not (-180.1 <= yaw <= 180.1 and -89.5 <= pitch <= 89.5):
                return None
            yaw_r   = math.radians(yaw)
            pitch_r = math.radians(pitch)
            fx = -math.sin(yaw_r) * math.cos(pitch_r)
            fy = -math.sin(pitch_r)
            fz =  math.cos(yaw_r) * math.cos(pitch_r)
            length = math.sqrt(fx ** 2 + fy ** 2 + fz ** 2)
            if abs(length - 1.0) > 0.01:
                return None
            return fx, fy, fz
        except Exception:
            return None


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
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


class _FOVReader:
    RESCAN_INTERVAL = 30.0

    def __init__(self):
        self.pm         = None
        self.fov_addr   = None
        self.pattern    = "?? ?? ?? ?? 00 00 70 42 6F 12"
        self._lock      = threading.Lock()
        self._scanning  = False
        self._last_scan = 0.0
        self._cached: float | None = None

    def set_pm(self, pm: pymem.Pymem):
        self.pm        = pm
        self.fov_addr  = None
        self._cached   = None
        self._last_scan = 0.0

    def _scan_worker(self):
        if not self.pm:
            self._scanning = False
            return
        regex = re.compile(b''.join(
            bytes.fromhex(p) if p != '??' else b'.'
            for p in self.pattern.split()
        ))
        mbi  = _MEMORY_BASIC_INFORMATION()
        addr = 0
        found = None
        while _kernel32.VirtualQueryEx(
            self.pm.process_handle, ctypes.c_void_p(addr),
            ctypes.byref(mbi), ctypes.sizeof(mbi),
        ):
            if mbi.Protect in (0x04, 0x20):
                try:
                    data = self.pm.read_bytes(mbi.BaseAddress, mbi.RegionSize)
                    for m in regex.finditer(data):
                        pos = mbi.BaseAddress + m.start()
                        try:
                            val = self.pm.read_float(pos)
                            if 30.0 <= val <= 120.0:
                                found = pos
                                break
                        except Exception:
                            pass
                except Exception:
                    pass
            if found:
                break
            addr += mbi.RegionSize
            if addr > 0x7FFFFFFFFFFF:
                break
        with self._lock:
            self.fov_addr  = found
            self._last_scan = time.time()
            self._scanning  = False

    def trigger(self):
        with self._lock:
            if self._scanning:
                return
            self._scanning = True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def get(self) -> float | None:
        with self._lock:
            addr, last = self.fov_addr, self._last_scan
        if addr:
            try:
                val = self.pm.read_float(addr)
                if 30.0 <= val <= 120.0:
                    self._cached = val
                    return val
            except Exception:
                pass
            with self._lock:
                self.fov_addr = None
        if time.time() - last >= self.RESCAN_INTERVAL:
            self.trigger()
        return self._cached


def _precise_sleep(seconds: float):
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    slack = seconds - 0.001
    if slack > 0:
        time.sleep(slack)
    while time.perf_counter() < deadline:
        pass


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long), ("top",    ctypes.c_long),
        ("right",  ctypes.c_long), ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


try:
    import psutil as _psutil
    import win32gui    as _win32gui
    import win32process as _win32process
    _WIN32_AVAIL = True
except ImportError:
    _WIN32_AVAIL = False


def _get_minecraft_client_size() -> tuple[int, int] | None:
    if not _WIN32_AVAIL:
        return None
    try:
        TARGET = "Minecraft.Windows.exe"
        for proc in _psutil.process_iter(["pid", "name"]):
            if proc.info["name"].lower() != TARGET.lower():
                continue
            pid = proc.info["pid"]
            found: list[wintypes.HWND] = []

            @_WNDENUMPROC
            def _cb(hwnd, _):
                if not _user32.IsWindowVisible(hwnd):
                    return True
                wpid = ctypes.c_ulong(0)
                _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value != pid:
                    return True
                rc = _RECT()
                _user32.GetClientRect(hwnd, ctypes.byref(rc))
                w = rc.right  - rc.left
                h = rc.bottom - rc.top
                if w > 0 and h > 0:
                    found.append(hwnd)
                return True

            _user32.EnumWindows(_cb, 0)
            if found:
                hwnd = found[0]
                rc   = _RECT()
                _user32.GetClientRect(hwnd, ctypes.byref(rc))
                w = rc.right  - rc.left
                h = rc.bottom - rc.top
                if w > 0 and h > 0:
                    return w, h
    except Exception:
        pass
    return None


class _AimController:
    def __init__(self):
        self._smooth_x         = 0.0
        self._smooth_y         = 0.0
        self._prev_dx          = 0.0
        self._prev_dy          = 0.0
        self._deadzone_grace   = 0
        self._last_target:      tuple | None = None
        self._last_target_time: float        = 0.0
        self._was_reset        = True

        self._prev_target_sx:  float | None = None
        self._prev_target_sy:  float | None = None

        self._pre_jump_dx:          float = 0.0
        self._pre_jump_dy:          float = 0.0
        self._jump_reversal_frames: int   = 0

        self._autoclicker_ref         = None
        self._aim_only_on_autoclicker = False

    def _soft_reset(self):
        self._smooth_x             = 0.0
        self._smooth_y             = 0.0
        self._prev_dx              = 0.0
        self._prev_dy              = 0.0
        self._pre_jump_dx          = 0.0
        self._pre_jump_dy          = 0.0
        self._was_reset            = True
        self._prev_target_sx       = None
        self._prev_target_sy       = None
        self._jump_reversal_frames = 0

    def set_autoclicker_reference(self, autoclicker_ref, aim_only_on_autoclicker: bool):
        self._autoclicker_ref         = autoclicker_ref
        self._aim_only_on_autoclicker = aim_only_on_autoclicker

    def _is_autoclicker_left_clicking(self) -> bool:
        if not self._autoclicker_ref:
            return True
        try:
            key_held = self._autoclicker_ref._left_clicker._active.is_set()
            return key_held
        except Exception:
            return True

    def update(
        self,
        sd: _SharedData,
        sw: int,
        sh: int,
        window_active: bool,
        menu_open: bool,
    ):
        if not window_active or menu_open:
            self._soft_reset()
            self._deadzone_grace = 0
            self._last_target    = None
            return

        if self._aim_only_on_autoclicker and not self._is_autoclicker_left_clicking():
            self._soft_reset()
            self._deadzone_grace = 0
            self._last_target    = None
            return

        fov = sd.fov or BASE_FOV
        sp  = _get_scaled_params(sw, sh, fov)
        now = time.perf_counter()

        aim = sd.aim_target
        if aim is None:
            if (self._last_target is not None
                    and now - self._last_target_time < CONN_SMOOTH_PERSIST):
                aim = self._last_target
            else:
                self._soft_reset()
                self._deadzone_grace = 0
                return
        else:
            self._last_target      = aim
            self._last_target_time = now

        target_sx, target_sy = aim

        if self._prev_target_sx is not None:
            jump = math.sqrt(
                (target_sx - self._prev_target_sx) ** 2 +
                (target_sy - self._prev_target_sy) ** 2
            )
            if jump > sp["dot_jump_thr"]:
                self._pre_jump_dx          = self._prev_dx
                self._pre_jump_dy          = self._prev_dy
                self._smooth_x             = 0.0
                self._smooth_y             = 0.0
                self._was_reset            = True
                self._jump_reversal_frames = 6

        self._prev_target_sx = target_sx
        self._prev_target_sy = target_sy

        cx, cy = sw / 2.0, sh / 2.0
        dx = target_sx - cx
        dy = target_sy - cy
        dist_px  = math.sqrt(dx ** 2 + dy ** 2)
        deadzone = min(sw, sh) * AIM_DEADZONE_RATE

        if dist_px <= deadzone:
            if self._deadzone_grace > 0:
                self._deadzone_grace -= 1
                self._smooth_x *= 0.45
                self._smooth_y *= 0.45
                if abs(self._smooth_x) < 0.8 and abs(self._smooth_y) < 0.8:
                    self._smooth_x = 0.0
                    self._smooth_y = 0.0
                    return
                ix = int(self._smooth_x)
                iy = int(self._smooth_y)
                if ix != 0 or iy != 0:
                    _send_mouse_move(ix, iy)
                return
            else:
                self._soft_reset()
                return
        else:
            self._deadzone_grace = CONN_DEADZONE_GRACE

        if self._jump_reversal_frames > 0:
            ref_dx = self._pre_jump_dx
            ref_dy = self._pre_jump_dy
            self._jump_reversal_frames -= 1
        else:
            ref_dx = self._prev_dx
            ref_dy = self._prev_dy

        if ref_dx * dx < 0:
            self._smooth_x *= CONN_REVERSAL_DECAY
        if ref_dy * dy < 0:
            self._smooth_y *= CONN_REVERSAL_DECAY

        self._prev_dx = dx
        self._prev_dy = dy

        dist_px2 = math.sqrt(dx ** 2 + dy ** 2)
        if dist_px2 == 0.0:
            return

        nx = dx / dist_px2
        ny = dy / dist_px2
        effective = max(dist_px2 - deadzone, 0.0)

        aim_max  = sp["aim_max_move"]
        target_x = nx * min(effective, aim_max)
        target_y = ny * min(effective, aim_max)

        move_lag  = min(now - sd.player_time, 0.05)
        lag_norm  = min(move_lag / 0.001, 1.0)
        lag_boost = lag_norm * LAG_BOOST_MAX
        a = min(0.99, sp["aim_smoothing"] + lag_boost)

        is_clicking = is_clicking_within_window(window_ms=25.0)
        if is_clicking:
            a = min(0.99, a * 1.3)

        if self._was_reset:
            self._smooth_x = (self._smooth_x * CONN_RESUME_ALPHA
                              + target_x * (1.0 - CONN_RESUME_ALPHA))
            self._smooth_y = (self._smooth_y * CONN_RESUME_ALPHA
                              + target_y * (1.0 - CONN_RESUME_ALPHA))
            self._was_reset = False
        else:
            self._smooth_x = self._smooth_x * (1.0 - a) + target_x * a
            self._smooth_y = self._smooth_y * (1.0 - a) + target_y * a

        ix = int(self._smooth_x)
        iy = int(self._smooth_y)
        if ix == 0 and iy == 0:
            return

        _send_mouse_move(ix, iy)

MONITOR_HZ       = get_monitor_refresh_rate()
_AIM_LOOP_HZ     = min(MONITOR_HZ, 360)
_FPS_BOOST_SCALE = max(1.0, min(2.5, 144.0 / max(MONITOR_HZ, 60)))

print(f"Monitor refresh rate: {MONITOR_HZ} Hz")
print(f"Aim loop: {_AIM_LOOP_HZ} Hz / FPS Boost Scale: {_FPS_BOOST_SCALE:.2f}x")

_monitor_hz_lock   = threading.Lock()
_monitor_hz_value  = MONITOR_HZ
_monitor_hz_thread = None


def _refresh_rate_monitor_loop():
    global _monitor_hz_value, _AIM_LOOP_HZ, _FPS_BOOST_SCALE
    prev = MONITOR_HZ
    while True:
        time.sleep(10.0)
        try:
            hz = get_monitor_refresh_rate()
            with _monitor_hz_lock:
                if hz != prev:
                    print(f"Refresh rate change detection: {prev} → {hz} Hz")
                    _monitor_hz_value = hz
                    _AIM_LOOP_HZ      = min(hz, 360)
                    _FPS_BOOST_SCALE  = max(1.0, min(2.5, 144.0 / max(hz, 60)))
                    prev = hz
        except Exception:
            pass


def _ensure_refresh_rate_monitor():
    global _monitor_hz_thread
    if _monitor_hz_thread is None or not _monitor_hz_thread.is_alive():
        _monitor_hz_thread = threading.Thread(
            target=_refresh_rate_monitor_loop,
            daemon=True,
            name="RefreshRateMonitor"
        )
        _monitor_hz_thread.start()

class _ESPCore:
    def __init__(self, pm: pymem.Pymem, shared: _SharedData):
        self.pm               = pm
        self.shared           = shared
        self.player_ent_hook  = _PlayerEntityESPHook(pm)
        self.other_ent_hook   = _OtherEntityESPHook(pm)
        self.player_hook      = _LocalPlayerHook(pm)
        self.yp_hook          = _YawPitchHook(pm)
        self.fov_reader       = _FOVReader()
        self.fov_reader.set_pm(pm)

        self.running          = False
        self.ready            = False
        self.last_reset_p     = 0.0
        self.last_reset_o     = 0.0
        self.prev_hit_p       = 0
        self.prev_hit_o       = 0

        self._player_hook_ok  = False
        self._other_hook_ok   = False

        self._monitor_thread:    threading.Thread | None = None
        self._forward_thread:    threading.Thread | None = None
        self._player_ent_thread: threading.Thread | None = None
        self._other_ent_thread:  threading.Thread | None = None

        self._player_ents:       list          = []
        self._other_ents:        list          = []
        self._player_ents_lock:  threading.Lock = threading.Lock()
        self._other_ents_lock:   threading.Lock = threading.Lock()

    def install_hooks(self) -> bool:
        self._player_hook_ok = self.player_ent_hook.install()
        self._other_hook_ok  = self.other_ent_hook.install()
        ok_local = self.player_hook.install()
        ok_yp    = self.yp_hook.install()
        self.fov_reader.trigger()
        if ok_local and ok_yp:
            self.ready = True
        return ok_local and ok_yp

    def _reset_player_entities(self):
        if not (self.player_ent_hook and self.player_ent_hook._patched):
            return
        try:
            self.pm.write_int(self.player_ent_hook.entity_count_addr, 0)
            self.last_reset_p = time.time()
        except Exception:
            pass

    def _reset_other_entities(self):
        if not (self.other_ent_hook and self.other_ent_hook._patched):
            return
        try:
            self.pm.write_int(self.other_ent_hook.entity_count_addr, 0)
            self.last_reset_o = time.time()
        except Exception:
            pass

    def _forward_loop(self):
        sd = self.shared
        while self.running:
            if self.yp_hook and self.yp_hook._patched:
                result = self.yp_hook.read_forward()
                if result is not None:
                    sd.forward = result
            time.sleep(0.001)

    def _player_ent_loop(self):
        while self.running:
            with _monitor_hz_lock:
                ivl = 1.0 / _AIM_LOOP_HZ
            t0 = time.perf_counter()

            if time.time() - self.last_reset_p >= RESET_INTERVAL:
                self._reset_player_entities()

            aim_player, _ = _get_target_mode()
            if aim_player and self._player_hook_ok and self.player_ent_hook._patched:
                hit_p, ents_p = self.player_ent_hook.read_entities()
                if self.prev_hit_p >= 30 and hit_p < self.prev_hit_p * 0.25:
                    self._reset_player_entities()
                self.prev_hit_p = hit_p
                new_list = [(x, y, z, ptr, _TAG_PLAYER) for x, y, z, ptr in ents_p]
            else:
                new_list = []

            with self._player_ents_lock:
                self._player_ents = new_list

            elapsed = time.perf_counter() - t0
            remain  = ivl - elapsed
            if remain > 0:
                _precise_sleep(remain)

    def _other_ent_loop(self):
        while self.running:
            with _monitor_hz_lock:
                ivl = 1.0 / _AIM_LOOP_HZ
            t0 = time.perf_counter()

            if time.time() - self.last_reset_o >= RESET_INTERVAL:
                self._reset_other_entities()

            _, aim_other = _get_target_mode()
            if aim_other and self._other_hook_ok and self.other_ent_hook._patched:
                hit_o, ents_o = self.other_ent_hook.read_entities()
                if self.prev_hit_o >= 30 and hit_o < self.prev_hit_o * 0.25:
                    self._reset_other_entities()
                self.prev_hit_o = hit_o
                new_list = [(x, y, z, ptr, _TAG_OTHER) for x, y, z, ptr in ents_o]
            else:
                new_list = []

            with self._other_ents_lock:
                self._other_ents = new_list

            elapsed = time.perf_counter() - t0
            remain  = ivl - elapsed
            if remain > 0:
                _precise_sleep(remain)

    def _monitor_loop(self):
        sd      = self.shared
        prev_px = prev_py = prev_pz = None
        prev_pt = None

        while self.running:
            with _monitor_hz_lock:
                ivl = 1.0 / _AIM_LOOP_HZ
            t0 = time.perf_counter()

            if self.player_hook and self.player_hook._patched:
                p = self.player_hook.read_player()
                if p is not None:
                    now = time.perf_counter()
                    px, py, pz, base = p
                    if prev_px is not None and prev_pt is not None:
                        dt = now - prev_pt
                        if dt > 0:
                            raw_vx = (px - prev_px) / dt
                            raw_vy = (py - prev_py) / dt
                            raw_vz = (pz - prev_pz) / dt
                            raw_spd = math.sqrt(raw_vx ** 2 + raw_vy ** 2 + raw_vz ** 2)
                            if raw_spd < 50.0:
                                sd.move_vx = (VEL_SMOOTH_ALPHA * raw_vx
                                              + (1 - VEL_SMOOTH_ALPHA) * sd.move_vx)
                                sd.move_vy = (VEL_SMOOTH_ALPHA * raw_vy
                                              + (1 - VEL_SMOOTH_ALPHA) * sd.move_vy)
                                sd.move_vz = (VEL_SMOOTH_ALPHA * raw_vz
                                              + (1 - VEL_SMOOTH_ALPHA) * sd.move_vz)
                    sd.player      = p
                    sd.player_time = now
                    prev_px, prev_py, prev_pz = px, py, pz
                    prev_pt = now
                    sd.self_ptr_locker.add_trail(px, py, pz)

            sd.fov = self.fov_reader.get()

            with self._player_ents_lock:
                player_ents = list(self._player_ents)
            with self._other_ents_lock:
                other_ents = list(self._other_ents)

            combined = player_ents + other_ents

            seen_ptrs: set[int] = set()
            deduped: list = []
            for item in combined:
                ptr = item[3]
                if ptr not in seen_ptrs:
                    seen_ptrs.add(ptr)
                    deduped.append(item)

            sd.entities = deduped

            elapsed = time.perf_counter() - t0
            remain  = ivl - elapsed
            if remain > 0:
                _precise_sleep(remain)

    def start(self):
        if self.running:
            return
        self.running = True
        self._forward_thread = threading.Thread(
            target=self._forward_loop, daemon=True, name="AimESPForward"
        )
        self._player_ent_thread = threading.Thread(
            target=self._player_ent_loop, daemon=True, name="AimESPPlayerEnt"
        )
        self._other_ent_thread = threading.Thread(
            target=self._other_ent_loop, daemon=True, name="AimESPOtherEnt"
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="AimESPMonitor"
        )
        self._forward_thread.start()
        self._player_ent_thread.start()
        self._other_ent_thread.start()
        self._monitor_thread.start()

    def stop(self):
        self.running = False

    def cleanup(self):
        self.stop()
        for h in (self.player_ent_hook, self.other_ent_hook, self.player_hook, self.yp_hook):
            if h:
                h.reset_hook()


class _AimLoopThread(threading.Thread):
    def __init__(
        self,
        shared:         _SharedData,
        aim_ctrl:       _AimController,
        window_monitor,
        menu_monitor,
        stop_event:     threading.Event,
    ):
        super().__init__(daemon=True, name="AimAssistLoop")
        self._shared     = shared
        self._aim        = aim_ctrl
        self._win_mon    = window_monitor
        self._menu_mon   = menu_monitor
        self._stop_ev    = stop_event

    def run(self):
        while not self._stop_ev.is_set():
            with _monitor_hz_lock:
                ivl = 1.0 / _AIM_LOOP_HZ
            t0 = time.perf_counter()

            win_active = self._win_mon.get_is_active() if self._win_mon else False
            menu_open  = self._menu_mon.is_menu_open   if self._menu_mon else False

            if not win_active or menu_open:
                self._aim._soft_reset()
                self._aim._deadzone_grace = 0
                self._aim._last_target    = None
                self._shared.aim_target   = None
                set_aim_tracking(False)
                elapsed = time.perf_counter() - t0
                remain  = ivl - elapsed
                if remain > 0:
                    _precise_sleep(remain)
                continue

            size = _get_minecraft_client_size()
            if size is None:
                time.sleep(0.01)
                continue
            sw, sh = size

            self._compute_aim_target(sw, sh)
            self._aim.update(self._shared, sw, sh, win_active, menu_open)

            elapsed = time.perf_counter() - t0
            remain  = ivl - elapsed
            if remain > 0:
                _precise_sleep(remain)

    def _compute_aim_target(self, sw: int, sh: int):
        sd = self._shared
        sd.aim_target = None

        p           = sd.player
        fwd         = sd.forward
        fov         = sd.fov or BASE_FOV
        player_time = sd.player_time
        move_vx     = sd.move_vx
        move_vy     = sd.move_vy
        move_vz     = sd.move_vz
        entities    = sd.entities

        if not (p and fwd):
            return

        sp = _get_scaled_params(sw, sh, fov)

        px, py, pz, player_base = p
        fx, fy, fz              = fwd

        now      = time.perf_counter()
        move_lag = min(now - player_time, 0.05)
        pred_ex  = -move_vx * move_lag * PREDICT_SCALE_MOVE
        pred_ey  = -move_vy * move_lag * PREDICT_SCALE_MOVE
        pred_ez  = -move_vz * move_lag * PREDICT_SCALE_MOVE

        current_max_dist = _get_esp_max_dist()

        if p is not None:
            sd.self_ptr_locker.add_trail(px, py, pz)

        player_ents_raw = [(x, y, z, ptr) for x, y, z, ptr, tag in entities
                           if tag == _TAG_PLAYER]
        self_ptr = sd.self_ptr_locker.update(player_ents_raw, player_base)

        filtered = []
        for item in entities:
            x, y, z, ptr, tag = item

            if tag == _TAG_PLAYER:
                if ptr == player_base:
                    continue
                if self_ptr is not None and ptr == self_ptr:
                    continue
                dist3d = math.sqrt((x - px)**2 + (y - py)**2 + (z - pz)**2)
                if dist3d < SELF_EXCLUDE_DIST:
                    continue

            filtered.append((x, y, z, ptr, tag))

        candidates = sorted(
            [
                (math.sqrt((x - px) ** 2 + (y - py) ** 2 + (z - pz) ** 2), x, y, z, ptr, tag)
                for x, y, z, ptr, tag in filtered
                if math.sqrt((x - px) ** 2 + (y - py) ** 2 + (z - pz) ** 2) <= current_max_dist
            ],
            key=lambda e: e[0],
        )

        if not candidates:
            _vel_tracker.clear_except(set())
            set_aim_tracking(False)
            return

        dist, ex, ey, ez, ptr, tag = candidates[0]

        if tag == _TAG_PLAYER and dist < SELF_EXCLUDE_DIST:
            _vel_tracker.clear_except(set())
            set_aim_tracking(False)
            return

        ex_pred = ex + pred_ex
        ey_pred = ey + pred_ey
        ez_pred = ez + pred_ez

        height_diff      = ey_pred - py
        y_offset_base    = _get_y_offset_player() if tag == _TAG_PLAYER else _get_y_offset_other()
        dynamic_y_offset = y_offset_base + max(0.0, height_diff) * HEIGHT_SCALE

        res = _world_to_screen(
            ex_pred, ey_pred - dynamic_y_offset, ez_pred,
            px, py, pz,
            fx, fy, fz,
            fov, sw, sh
        )
        if res is None:
            _vel_tracker.clear_except(set())
            set_aim_tracking(False)
            return

        raw_sx, raw_sy = res
        corr_x, corr_y = _get_direction_correction(
            fx, fz, raw_sx, raw_sy, sw, sh, dist, sp
        )
        raw_sx += corr_x
        raw_sy += corr_y

        strafe_ox, strafe_oy = _vel_tracker.update(ptr, raw_sx, raw_sy)
        predicted_sx = raw_sx + strafe_ox
        predicted_sy = raw_sy + strafe_oy

        sd.aim_target = (predicted_sx, predicted_sy)
        set_aim_tracking(True)
        _vel_tracker.clear_except({ptr})


_vel_tracker = _EnemyVelocityTracker()


class AimAssistController:
    def __init__(self):
        self.pm:               pymem.Pymem | None = None
        self.process_handle                       = None
        self.update_queue:     queue.Queue | None = None

        self.is_active    = False
        self.initialized  = False

        self._sensitivity     = BASE_SENSITIVITY
        self._max_dist        = ESP_MAX_DIST
        self._aim_player      = True
        self._aim_other       = False
        self._y_offset_player = 1.8
        self._y_offset_other  = 0.9

        self._shared:     _SharedData     | None = None
        self._esp_core:   _ESPCore        | None = None
        self._aim_ctrl:   _AimController  | None = None
        self._aim_thread: _AimLoopThread  | None = None
        self._stop_event: threading.Event         = threading.Event()

        self._win_monitor  = None
        self._menu_monitor = None

        self._autoclicker_reference      = None
        self._aim_only_on_autoclicker    = False

    def set_pymem_process(self, pm: pymem.Pymem):
        self.pm             = pm
        self.process_handle = pm.process_handle

    def set_update_queue(self, q: queue.Queue):
        self.update_queue = q

    def set_sensitivity(self, value: float):
        value = max(0.01, min(1.00, round(float(value), 2)))
        self._sensitivity = value
        _set_sensitivity(value)
        if self._aim_ctrl is not None:
            self._aim_ctrl._soft_reset()
            self._aim_ctrl._deadzone_grace = 0
            self._aim_ctrl._last_target    = None
        if self._shared is not None:
            self._shared.aim_target = None

    def set_max_dist(self, value: float):
        value = max(3.0, min(8.0, round(float(value), 2)))
        self._max_dist = value
        _set_esp_max_dist(value)

    def set_target_mode(self, player: bool, other: bool):
        self._aim_player = player
        self._aim_other  = other
        _set_target_mode(player, other)

    def get_target_mode(self) -> tuple[bool, bool]:
        return self._aim_player, self._aim_other

    def set_y_offset_player(self, value: float):
        value = max(1.10, min(2.60, round(float(value), 2)))
        self._y_offset_player = value
        _set_y_offset_player(value)

    def set_y_offset_other(self, value: float):
        value = max(-0.20, min(1.50, round(float(value), 2)))
        self._y_offset_other = value
        _set_y_offset_other(value)

    def set_autoclicker_reference(self, autoclicker_controller):
        self._autoclicker_reference = autoclicker_controller

    def set_aim_only_on_autoclicker(self, enabled: bool):
        self._aim_only_on_autoclicker = enabled
        if self._aim_ctrl:
            self._aim_ctrl._aim_only_on_autoclicker = enabled

    def _update_status(self, message: str, color: str):
        if self.update_queue:
            self.update_queue.put(("status_update", ("aimassist", message, color)))

    def validate_process(self) -> bool:
        try:
            if not self.pm or not self.process_handle:
                return False
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                self.process_handle, ctypes.byref(code)
            ):
                return False
            return code.value == 259
        except Exception:
            return False

    def initialize(self) -> bool:
        if not self.validate_process():
            return False
        try:
            self._shared   = _SharedData()
            self._aim_ctrl = _AimController()

            self._esp_core = _ESPCore(self.pm, self._shared)
            ok = self._esp_core.install_hooks()
            if ok:
                self.ready = True

            try:
                self._win_monitor = _get_window_monitor()
            except Exception:
                self._win_monitor = None

            try:
                self._menu_monitor = _get_menu_monitor()
            except Exception:
                self._menu_monitor = None

            self.initialized = True
            return True
        except Exception:
            import traceback; traceback.print_exc()
            return False

    def start(self) -> bool:
        if not self.initialized:
            if not self.initialize():
                self._update_status("Init Failed", "#ff5252")
                return False

        if self.is_active:
            return True

        try:
            _set_sensitivity(self._sensitivity)
            _set_esp_max_dist(self._max_dist)
            _set_target_mode(self._aim_player, self._aim_other)
            _set_y_offset_player(self._y_offset_player)
            _set_y_offset_other(self._y_offset_other)

            _ensure_refresh_rate_monitor()

            self._esp_core.start()

            self._stop_event.clear()
            if self._aim_ctrl:
                self._aim_ctrl.set_autoclicker_reference(
                    self._autoclicker_reference,
                    self._aim_only_on_autoclicker
                )

            self._aim_thread = _AimLoopThread(
                shared         = self._shared,
                aim_ctrl       = self._aim_ctrl,
                window_monitor = self._win_monitor,
                menu_monitor   = self._menu_monitor,
                stop_event     = self._stop_event,
            )
            self._aim_thread.start()

            self.is_active = True
            self._update_status("Active", "#00e676")
            return True

        except Exception as e:
            self._update_status(f"Start Error: {e.__class__.__name__}", "#ff5252")
            return False

    def stop(self, is_app_closing: bool = False):
        if not self.is_active:
            return True
        self.is_active = False
        try:
            self._stop_event.set()
            t = self._aim_thread
            if t is not None and t.is_alive():
                t.join(timeout=1.0)
            self._aim_thread = None

            if self._esp_core is not None:
                self._esp_core.stop()
                for attr in ('_forward_thread', '_monitor_thread',
                             '_player_ent_thread', '_other_ent_thread'):
                    th = getattr(self._esp_core, attr, None)
                    if th is not None and th.is_alive():
                        th.join(timeout=0.5)

            if self._aim_ctrl is not None:
                self._aim_ctrl._soft_reset()
                self._aim_ctrl._deadzone_grace = 0
                self._aim_ctrl._last_target    = None

            if self._shared is not None:
                self._shared.aim_target = None

            self._update_status("Inactive", "#a0a0b0")
            return True
        except Exception:
            self.is_active = False
            import traceback; traceback.print_exc()
            self._update_status("Inactive", "#a0a0b0")
            return False

    def reset_to_default(self, is_app_closing: bool = False):
        self.stop(is_app_closing=is_app_closing)
        if self._esp_core:
            self._esp_core.cleanup()
            self._esp_core = None

        self._shared      = None
        self._aim_ctrl    = None
        self._aim_thread  = None
        self.initialized  = False
        self.is_active    = False
        return True