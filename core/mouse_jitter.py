import ctypes
import ctypes.wintypes as wt
import time
import random
import threading

MOUSEEVENTF_MOVE = 0x0001
INPUT_MOUSE = 0
MY_EXTRA = 0xABCD1234
ULONG_PTR = ctypes.c_uint64


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", _InputUnion)]


_user32 = ctypes.WinDLL('user32.dll')

try:
    _ntdll = ctypes.WinDLL('ntdll.dll')
    _cur   = ctypes.c_ulong()
    _ntdll.NtSetTimerResolution(5000, True, ctypes.byref(_cur))
except Exception:
    pass
ctypes.windll.winmm.timeBeginPeriod(1)


def _send_mouse_move(dx: int, dy: int):
    ii_ = _InputUnion()
    ii_.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, MY_EXTRA)
    x = INPUT(INPUT_MOUSE, ii_)
    _user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


def apply_jitter(strength: float = 2.0, duration: float = 0.01, use_scheduler: bool = False):
    if strength <= 0:
        return

    if use_scheduler:
        from core.input_scheduler import get_shared_input_scheduler, InputPriority
        scheduler = get_shared_input_scheduler()

    perf    = time.perf_counter
    gauss   = random.gauss
    rnd     = random.random
    amp     = 1.5 + strength * 1.05
    interval = max(0.001, 0.007 - (strength - 1) * 0.00065)

    deadline = perf() + duration
    drift_x  = 0.0
    drift_y  = 0.0
    last     = perf()

    while perf() < deadline:
        target = last + interval
        slack = target - perf() - 0.0002
        if slack > 0:
            time.sleep(slack)
        while perf() < target:
            pass
        last = perf()

        drift_bias_x = -drift_x / amp * 1.5
        raw_x = gauss(drift_bias_x, strength * 0.55)
        dx = int(max(-amp, min(amp, raw_x)))
        if dx == 0:
            dx = 1 if rnd() < 0.5 else -1

        drift_bias_y = -drift_y / amp * 1.5
        raw_y = gauss(drift_bias_y, strength * 0.40)
        dy = int(max(-amp * 0.7, min(amp * 0.7, raw_y)))

        if dx != 0 or dy != 0:
            if use_scheduler:
                scheduler.queue_mouse_input(
                    MOUSEEVENTF_MOVE,
                    dx, dy,
                    priority=InputPriority.MEDIUM
                )
            else:
                _send_mouse_move(dx, dy)
            drift_x += dx
            drift_y += dy


def apply_jitter_during_click(
    is_left: bool,
    strength: float = 2.0,
    click_duration: float = 0.01,
    use_scheduler: bool = False,
):
    apply_jitter(strength, click_duration, use_scheduler=use_scheduler)