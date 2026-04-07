import threading
import time

_lock              = threading.Lock()
_ac_clicking       = False
_tb_clicking       = False
_ac_click_active   = False
_tb_click_active   = False
_last_click_time   = 0.0
_ac_jitter_active  = False


def reset_all():
    global _ac_clicking, _tb_clicking, _ac_click_active, _tb_click_active, _last_click_time, _ac_jitter_active
    with _lock:
        _ac_clicking      = False
        _tb_clicking      = False
        _ac_click_active  = False
        _tb_click_active  = False
        _last_click_time  = 0.0
        _ac_jitter_active = False


def ac_try_start() -> bool:
    global _ac_clicking
    with _lock:
        if _tb_clicking:
            return False
        _ac_clicking = True
        return True


def ac_set_clicking(active: bool):
    global _ac_clicking
    with _lock:
        _ac_clicking = active


def ac_is_blocked() -> bool:
    with _lock:
        return _tb_clicking


def tb_try_start() -> bool:
    global _tb_clicking
    with _lock:
        if _ac_clicking:
            return False
        _tb_clicking = True
        return True


def tb_set_clicking(active: bool):
    global _tb_clicking
    with _lock:
        _tb_clicking = active


def tb_is_blocked() -> bool:
    with _lock:
        return _ac_clicking


def ac_set_queued(v: bool):
    pass


def register_ac_resume_callback(fn):
    pass


def unregister_ac_resume_callback():
    pass

def set_ac_click_active(active: bool):
    global _ac_click_active
    with _lock:
        _ac_click_active = active


def set_tb_click_active(active: bool):
    global _tb_click_active
    with _lock:
        _tb_click_active = active


def is_any_clicking() -> bool:
    with _lock:
        return _ac_click_active or _tb_click_active


def is_ac_clicking() -> bool:
    with _lock:
        return _ac_click_active


def is_tb_clicking() -> bool:
    with _lock:
        return _tb_click_active


def is_clicking_within_window(window_ms: float = 20.0) -> bool:
    with _lock:
        elapsed = (time.time() - _last_click_time) * 1000
        return elapsed < window_ms


def record_click_time():
    global _last_click_time
    with _lock:
        _last_click_time = time.time()

def set_ac_jitter_active(active: bool):
    global _ac_jitter_active
    with _lock:
        _ac_jitter_active = active


def is_ac_jitter_active() -> bool:
    with _lock:
        return _ac_jitter_active

_aim_tracking = False


def set_aim_tracking(active: bool):
    global _aim_tracking
    with _lock:
        _aim_tracking = active


def is_aim_tracking() -> bool:
    with _lock:
        return _aim_tracking