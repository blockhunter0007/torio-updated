# autoclicker.py
import ctypes
import ctypes.wintypes as wt
import time
import threading
import queue
import random
import keyboard
from core.menu_monitor import get_shared_menu_monitor as _get_menu_monitor
from core.minecraft_windowmonitor import get_shared_window_monitor as _get_window_monitor
from core.click_priority import (
    ac_try_start, ac_set_clicking, ac_is_blocked,
    ac_set_queued, register_ac_resume_callback, unregister_ac_resume_callback,
    set_ac_click_active, record_click_time,
    set_ac_jitter_active, is_aim_tracking,
)
from core.mouse_jitter import apply_jitter_during_click

ctypes.windll.winmm.timeBeginPeriod(1)

MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010
MOUSEEVENTF_MOVE      = 0x0001
INPUT_MOUSE           = 0
MY_EXTRA              = 0xABCD1234
WH_MOUSE_LL           = 14
WM_QUIT               = 0x0012
WM_LBUTTONDOWN        = 0x0201
WM_LBUTTONUP          = 0x0202
WM_RBUTTONDOWN        = 0x0204
WM_RBUTTONUP          = 0x0205
ULONG_PTR             = ctypes.c_uint64

# ブロック破壊試行時間（秒）
BLOCK_BREAK_PROBE_DURATION = 0.05


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wt.LONG),
        ("dy",          wt.LONG),
        ("mouseData",   wt.DWORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wt.WORD),
        ("wScan",       wt.WORD),
        ("dwFlags",     wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg",    wt.DWORD),
        ("wParamL", wt.WORD),
        ("wParamH", wt.WORD),
    ]

class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("union", _InputUnion)]

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          wt.POINT),
        ("mouseData",   wt.DWORD),
        ("flags",       wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

_user32 = ctypes.WinDLL('user32.dll')

def _send_mouse_event(flags: int):
    ii_    = _InputUnion()
    ii_.mi = MOUSEINPUT(0, 0, 0, flags, 0, MY_EXTRA)
    x = INPUT(INPUT_MOUSE, ii_)
    _user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

def _send_mouse_move(dx: int, dy: int):
    ii_    = _InputUnion()
    ii_.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, MY_EXTRA)
    x = INPUT(INPUT_MOUSE, ii_)
    _user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

_menu_open = threading.Event()

def _on_menu_state_changed(is_open: bool):
    _menu_open.set() if is_open else _menu_open.clear()

def _register_menu_monitor():
    try:
        m = _get_menu_monitor()
        try:
            m.remove_listener(_on_menu_state_changed)
        except Exception:
            pass
        m.add_listener(_on_menu_state_changed)
        _menu_open.set() if m.is_menu_open else _menu_open.clear()
    except Exception:
        _menu_open.clear()

_phys_left_down  = False
_phys_right_down = False
_phys_lock       = threading.Lock()
_hook_handle     = None
_hook_proc_ref   = None
_hook_thread     = None
_hook_thread_id  = None
_hook_meta_lock  = threading.Lock()

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, ctypes.c_uint64, ctypes.c_int64,
)
kernel32 = ctypes.WinDLL('kernel32.dll')
_user32.CallNextHookEx.restype  = ctypes.c_longlong
_user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.c_uint64, ctypes.c_int64,
]

def _make_hook_proc():
    def _proc(nCode, wParam, lParam):
        global _phys_left_down, _phys_right_down
        if nCode >= 0:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if info.dwExtraInfo != MY_EXTRA:
                with _phys_lock:
                    if   wParam == WM_LBUTTONDOWN: _phys_left_down  = True
                    elif wParam == WM_LBUTTONUP:   _phys_left_down  = False
                    elif wParam == WM_RBUTTONDOWN: _phys_right_down = True
                    elif wParam == WM_RBUTTONUP:   _phys_right_down = False
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)
    return _proc

def _hook_thread_func():
    global _hook_handle, _hook_proc_ref, _hook_thread_id
    _hook_thread_id = kernel32.GetCurrentThreadId()
    _hook_proc_ref  = HOOKPROC(_make_hook_proc())
    hmod = kernel32.GetModuleHandleW(None)
    _hook_handle = _user32.SetWindowsHookExW(WH_MOUSE_LL, _hook_proc_ref, hmod, 0)
    if not _hook_handle:
        _hook_handle = _user32.SetWindowsHookExW(WH_MOUSE_LL, _hook_proc_ref, None, 0)
    if not _hook_handle:
        _hook_thread_id = None
        return
    time.sleep(0.05)
    msg = wt.MSG()
    while True:
        ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or ret == -1:
            break
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))
    if _hook_handle:
        try:
            _user32.UnhookWindowsHookEx(_hook_handle)
        except Exception:
            pass
        _hook_handle = None
    _hook_thread_id = None

def _ensure_hook_running():
    global _hook_thread, _hook_handle
    with _hook_meta_lock:
        if _hook_thread is None or not _hook_thread.is_alive():
            if _hook_handle:
                try:
                    _user32.UnhookWindowsHookEx(_hook_handle)
                except Exception:
                    pass
                _hook_handle = None
            _hook_thread = threading.Thread(
                target=_hook_thread_func, name="ACHookThread", daemon=True
            )
            _hook_thread.start()
    for _ in range(20):
        if _hook_handle:
            break
        time.sleep(0.01)

def _force_release_all_hooks():
    global _hook_handle, _hook_thread, _hook_thread_id
    with _hook_meta_lock:
        if _hook_handle:
            try:
                _user32.UnhookWindowsHookEx(_hook_handle)
            except Exception:
                pass
            _hook_handle = None
        tid = _hook_thread_id
    if tid:
        try:
            _user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
        except Exception:
            pass
    t = _hook_thread
    if t and t.is_alive():
        t.join(timeout=2.0)
    with _hook_meta_lock:
        _hook_thread = _hook_thread_id = None

def _is_held(key: str) -> bool:
    if key == "mouse_left":
        with _phys_lock: return _phys_left_down
    if key == "mouse_right":
        with _phys_lock: return _phys_right_down
    return keyboard.is_pressed(key)


class _SideClicker:
    def __init__(self, is_left: bool):
        self._is_left   = is_left
        self._active    = threading.Event()
        self._stop_ev   = threading.Event()
        self._poll_t:  threading.Thread | None = None
        self._click_t: threading.Thread | None = None

        self.cps     = 10.0
        self.key     = "z" if is_left else "x"
        self.enabled = True

        self.is_mc_active:      callable = lambda: True
        self.is_menu_open:      callable = lambda: False
        self.is_block_breaking: callable = lambda: False

        self.jitter_enabled  = False
        self.jitter_strength = 2.0

        # ブロック破壊試行フェーズ管理（左クリッカーのみ使用）
        # _probe_state:
        #   "idle"    … 待機中
        #   "probing" … 0.4秒長押し試行中
        #   "breaking"… blockbreak_detectorがONになり長押し継続中
        #   "normal"  … 通常オートクリックモード
        self._probe_state      = "idle"
        self._probe_start_time = 0.0
        self._probe_lock       = threading.Lock()

    # ── ブロック破壊試行フェーズ API（左クリッカー専用） ──────────────

    def notify_break_detected(self):
        """blockbreak_detector から breaking=True が来たときに呼ばれる"""
        if not self._is_left:
            return
        with self._probe_lock:
            if self._probe_state in ("probing", "idle"):
                # probing中 or idleでもbreakingになったら即breaking状態へ
                self._probe_state = "breaking"

    def notify_break_ended(self):
        """blockbreak_detector から breaking=False が来たときに呼ばれる"""
        if not self._is_left:
            return
        with self._probe_lock:
            if self._probe_state == "breaking":
                # ブロック破壊が終わったので通常モードへ
                self._probe_state = "normal"

    def _reset_probe(self):
        """キーを離したとき or 停止時にリセット"""
        with self._probe_lock:
            self._probe_state      = "idle"
            self._probe_start_time = 0.0

    # ── ポーリングループ ────────────────────────────────────────────────

    def _poll_loop(self):
        while not self._stop_ev.is_set():
            if not self._is_left:
                # 右クリッカーは従来通り
                held = (
                    self.enabled
                    and self.is_mc_active()
                    and not self.is_menu_open()
                    and _is_held(self.key)
                )
                if held:
                    if not self._active.is_set():
                        if not ac_is_blocked():
                            ac_try_start()
                            self._active.set()
                else:
                    if self._active.is_set():
                        self._active.clear()
                    ac_set_clicking(False)
                time.sleep(0.005)
                continue

            # ── 左クリッカー ──────────────────────────────────────────
            held = (
                self.enabled
                and self.is_mc_active()
                and not self.is_menu_open()
                and _is_held(self.key)
            )

            if held:
                with self._probe_lock:
                    state = self._probe_state

                if state == "idle":
                    # キーを押し始めた → probe開始
                    with self._probe_lock:
                        self._probe_state      = "probing"
                        self._probe_start_time = time.perf_counter()
                    # 左クリック長押し開始
                    _send_mouse_event(MOUSEEVENTF_LEFTDOWN)

                elif state == "probing":
                    # 0.4秒経過チェック
                    elapsed = time.perf_counter() - self._probe_start_time
                    if elapsed >= BLOCK_BREAK_PROBE_DURATION:
                        # 0.4秒経ってもbreakingにならなかった → 通常オートクリック
                        _send_mouse_event(MOUSEEVENTF_LEFTUP)
                        with self._probe_lock:
                            self._probe_state = "normal"
                        if not self._active.is_set():
                            if not ac_is_blocked():
                                ac_try_start()
                                self._active.set()

                elif state == "breaking":
                    # blockbreak_detector がON → _click_loopは何もしない
                    # (autoclickerコントローラ側で左クリック長押し管理)
                    if self._active.is_set():
                        self._active.clear()

                elif state == "normal":
                    # 通常オートクリックモード
                    if not self._active.is_set():
                        if not ac_is_blocked():
                            ac_try_start()
                            self._active.set()

            else:
                # キーを離した
                with self._probe_lock:
                    state = self._probe_state

                if state == "probing":
                    # probe中にキーを離した → 左クリックUPが必要
                    _send_mouse_event(MOUSEEVENTF_LEFTUP)
                # breaking状態でキーを離した場合はコントローラ側でLEFTUPを送信済み

                self._reset_probe()
                if self._active.is_set():
                    self._active.clear()
                ac_set_clicking(False)

            time.sleep(0.005)

    # ── クリックループ ──────────────────────────────────────────────────

    def _click_loop(self):
        ctypes.windll.winmm.timeBeginPeriod(1)
        down_flag = MOUSEEVENTF_LEFTDOWN  if self._is_left else MOUSEEVENTF_RIGHTDOWN
        up_flag   = MOUSEEVENTF_LEFTUP    if self._is_left else MOUSEEVENTF_RIGHTUP
        perf = time.perf_counter
        last = 0.0

        try:
            while not self._stop_ev.is_set():
                if not self._active.is_set():
                    self._active.wait(timeout=0.01)
                    last = 0.0
                    continue

                if ac_is_blocked():
                    time.sleep(0.005)
                    last = 0.0
                    continue

                # 左クリッカーの場合、breaking/probingフェーズ中はここに来ない
                # （_poll_loopで_activeをセットしないため）
                if (self.is_menu_open() or
                    (self._is_left and self.is_block_breaking()) or
                    not self.is_mc_active()):
                    self._active.clear()
                    ac_set_clicking(False)
                    time.sleep(0.005)
                    last = 0.0
                    continue

                interval = 1.0 / max(1.0, self.cps)
                now      = perf()

                if now - last >= interval:
                    last = now
                    hold = min(0.008, interval * 0.35)

                    set_ac_click_active(True)
                    record_click_time()

                    _send_mouse_event(down_flag)

                    if self.jitter_enabled:
                        apply_jitter_during_click(self._is_left, self.jitter_strength, hold, use_scheduler=False)
                    else:
                        end_time = perf() + hold
                        while perf() < end_time:
                            pass

                    _send_mouse_event(up_flag)
                    set_ac_click_active(False)
                else:
                    remaining = (last + interval) - now
                    if remaining > 0.002:
                        time.sleep(remaining - 0.002)
                    target = last + interval
                    while perf() < target:
                        pass
        finally:
            ctypes.windll.winmm.timeEndPeriod(1)

    def start(self):
        self._stop_ev.clear()
        self._active.clear()
        self._reset_probe()
        self._poll_t  = threading.Thread(target=self._poll_loop,  daemon=True)
        self._click_t = threading.Thread(target=self._click_loop, daemon=True)
        self._poll_t.start()
        self._click_t.start()

    def stop(self):
        self._stop_ev.set()
        self._active.clear()
        self._reset_probe()
        ac_set_clicking(False)
        for t in (self._poll_t, self._click_t):
            if t and t.is_alive():
                t.join(timeout=1.0)


class AutoClickerController:
    def __init__(self):
        self.update_queue      = None
        self.should_stop       = threading.Event()
        self.is_active         = False
        self.initialized       = True
        self.left_cps          = 10.0
        self.right_cps         = 10.0
        self.left_key          = 'z'
        self.right_key         = 'x'
        self.left_enabled      = True
        self.right_enabled     = True

        self.jitter_enabled    = False
        self.jitter_strength   = 2.0
        self._jitter_drift     = 0.0
        self.minecraft_active  = False
        self._window_monitor   = None

        self._block_breaking      = threading.Event()
        self._bb_registered       = False
        self._bb_detector         = None
        self._last_break_end_time = 0.0

        self._ctrl_lock     = threading.Lock()

        self._left_clicker  = _SideClicker(is_left=True)
        self._right_clicker = _SideClicker(is_left=False)

        self._jitter_thread = None

    def _inject_callbacks(self):
        for sc in (self._left_clicker, self._right_clicker):
            sc.is_mc_active      = lambda: self.minecraft_active
            sc.is_menu_open      = lambda: _menu_open.is_set()
            sc.is_block_breaking = self._is_block_breaking

    def _on_mc_active_changed(self, is_active: bool):
        self.minecraft_active = is_active

    def _register_window_monitor(self):
        try:
            m = _get_window_monitor()
            m.add_listener(self._on_mc_active_changed)
            self.minecraft_active = m.get_is_active()
            self._window_monitor = m
        except Exception:
            self.minecraft_active = True

    def _unregister_window_monitor(self):
        try:
            if self._window_monitor:
                self._window_monitor.remove_listener(self._on_mc_active_changed)
                self._window_monitor = None
        except Exception:
            pass

    def _on_block_break_changed(self, is_breaking: bool):
        if is_breaking:
            self._block_breaking.set()
            # 左クリッカーのprobeフェーズに通知（probe中なら breaking状態へ遷移）
            self._left_clicker.notify_break_detected()
            # breaking状態では左クリック長押しを維持
            # （probe中にすでにLEFTDOWNを送信済みなので追加送信不要）
            # ただし、normalモードから急にbreakingになったケースに備えてLEFTDOWNを送る
            with self._left_clicker._probe_lock:
                state = self._left_clicker._probe_state
            if state == "breaking":
                _send_mouse_event(MOUSEEVENTF_LEFTDOWN)
        else:
            self._block_breaking.clear()
            self._last_break_end_time = time.perf_counter()
            # 左クリッカーに通知してnormalモードへ
            self._left_clicker.notify_break_ended()
            _send_mouse_event(MOUSEEVENTF_LEFTUP)

    def _register_blockbreak(self):
        if self._bb_registered:
            return
        try:
            from core.blockbreak_detector import get_shared_block_detector
            self._bb_detector = get_shared_block_detector()
            self._bb_detector.add_listener(self._on_block_break_changed)
            self._bb_registered = True
        except Exception:
            pass

    def _unregister_blockbreak(self):
        if not self._bb_registered:
            return
        try:
            if self._bb_detector is not None:
                self._bb_detector.remove_listener(self._on_block_break_changed)
        except Exception:
            pass
        self._bb_detector         = None
        self._bb_registered       = False
        self._block_breaking.clear()

    def _is_block_breaking(self) -> bool:
        if self._block_breaking.is_set():
            return True
        now = time.perf_counter()
        if now - self._last_break_end_time < 0.08:
            return True
        try:
            det = self._bb_detector
            if det is not None and det.is_active and det.is_breaking():
                self._block_breaking.set()
                return True
        except Exception:
            pass
        return False

    def _jitter_loop(self):
        ctypes.windll.winmm.timeBeginPeriod(1)
        try:
            ntdll = ctypes.WinDLL('ntdll.dll')
            cur   = ctypes.c_ulong()
            ntdll.NtSetTimerResolution(5000, True, ctypes.byref(cur))
        except Exception:
            pass

        send_input = _user32.SendInput
        sizeof_inp = ctypes.sizeof(INPUT)
        perf       = time.perf_counter
        sleep      = time.sleep
        gauss      = random.gauss
        rnd        = random.random

        def _move(dx, dy):
            ii_    = _InputUnion()
            ii_.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, MY_EXTRA)
            x = INPUT(INPUT_MOUSE, ii_)
            send_input(1, ctypes.byref(x), sizeof_inp)

        try:
            drift_x = 0.0
            drift_y = 0.0

            while not self.should_stop.is_set():
                try:
                    enabled   = self.jitter_enabled
                    strength  = self.jitter_strength
                    mc_active = self.minecraft_active

                    if not enabled or not mc_active or _menu_open.is_set():
                        set_ac_jitter_active(False)
                        drift_x = drift_y = 0.0
                        sleep(0.035)
                        continue

                    if self._block_breaking.is_set():
                        set_ac_jitter_active(False)
                        drift_x = drift_y = 0.0
                        sleep(0.005)
                        continue

                    left_held  = self.left_enabled  and _is_held(self.left_key)
                    right_held = self.right_enabled and _is_held(self.right_key)

                    if not (left_held or right_held):
                        set_ac_jitter_active(False)
                        drift_x = drift_y = 0.0
                        sleep(0.008)
                        continue

                    if is_aim_tracking():
                        set_ac_jitter_active(False)
                        drift_x = drift_y = 0.0
                        sleep(0.005)
                        continue

                    set_ac_jitter_active(True)

                    amp = 1.5 + strength * 1.05

                    drift_bias_x = -drift_x / amp * 1.5
                    raw_x = gauss(drift_bias_x, strength * 0.55)
                    dx = int(max(-amp, min(amp, raw_x)))
                    if dx == 0:
                        dx = 1 if rnd() < 0.5 else -1

                    drift_bias_y = -drift_y / amp * 1.5
                    raw_y = gauss(drift_bias_y, strength * 0.40)
                    dy = int(max(-amp * 0.7, min(amp * 0.7, raw_y)))

                    if dx != 0 or dy != 0:
                        _move(dx, dy)
                        drift_x += dx
                        drift_y += dy

                    interval = max(0.001, 0.007 - (strength - 1) * 0.00065)
                    deadline = perf() + interval
                    slack = deadline - perf() - 0.0002
                    if slack > 0:
                        sleep(slack)
                    while perf() < deadline:
                        pass

                except Exception:
                    set_ac_jitter_active(False)
                    drift_x = drift_y = 0.0
                    sleep(0.04)
        finally:
            set_ac_jitter_active(False)
            ctypes.windll.winmm.timeEndPeriod(1)

    def _apply_settings_to_clickers(self):
        self._left_clicker.cps              = self.left_cps
        self._right_clicker.cps             = self.right_cps
        self._left_clicker.key              = self.left_key
        self._right_clicker.key             = self.right_key
        self._left_clicker.enabled          = self.left_enabled
        self._right_clicker.enabled         = self.right_enabled
        self._left_clicker.jitter_enabled   = self.jitter_enabled
        self._right_clicker.jitter_enabled  = self.jitter_enabled
        self._left_clicker.jitter_strength  = self.jitter_strength
        self._right_clicker.jitter_strength = self.jitter_strength

    def set_update_queue(self, q: queue.Queue):
        self.update_queue = q

    def update_status(self, message, color):
        if self.update_queue:
            self.update_queue.put(('status_update', ('autoclicker', message, color)))

    def set_cps(self, left_cps: float, right_cps: float):
        self.left_cps  = max(1.0, min(20.0, left_cps))
        self.right_cps = max(1.0, min(20.0, right_cps))
        self._left_clicker.cps  = self.left_cps
        self._right_clicker.cps = self.right_cps

    def set_keybinds(self, left_key: str, right_key: str):
        old_l = self.left_key
        old_r = self.right_key
        self.left_key  = left_key.lower()
        self.right_key = right_key.lower()
        self._left_clicker.key  = self.left_key
        self._right_clicker.key = self.right_key
        need_restart = (
            self.is_active and (
                self._is_mouse_bind(old_l) != self._is_mouse_bind(self.left_key) or
                self._is_mouse_bind(old_r) != self._is_mouse_bind(self.right_key)
            )
        )
        if need_restart:
            def _restart():
                self.stop()
                self.start()
            threading.Thread(target=_restart, daemon=True, name="ACRestart").start()

    def set_click_enabled(self, left_enabled: bool, right_enabled: bool):
        self.left_enabled  = left_enabled
        self.right_enabled = right_enabled
        self._left_clicker.enabled  = left_enabled
        self._right_clicker.enabled = right_enabled

    def set_jitter(self, enabled: bool, strength: float):
        strength = max(1.0, min(10.0, strength))
        self.jitter_enabled  = enabled
        self.jitter_strength = strength
        self._left_clicker.jitter_enabled   = enabled
        self._right_clicker.jitter_enabled  = enabled
        self._left_clicker.jitter_strength  = strength
        self._right_clicker.jitter_strength = strength
        if not enabled:
            set_ac_jitter_active(False)

    @staticmethod
    def _is_mouse_bind(key: str) -> bool:
        return key in ("mouse_left", "mouse_right")

    def start(self):
        if self.is_active:
            return True
        try:
            self.should_stop.clear()
            self._block_breaking.clear()
            _menu_open.clear()

            self._jitter_drift        = 0.0
            self._last_break_end_time = 0.0

            ac_set_clicking(False)
            set_ac_jitter_active(False)

            self._register_window_monitor()
            self._register_blockbreak()
            _register_menu_monitor()

            if self._is_mouse_bind(self.left_key) or self._is_mouse_bind(self.right_key):
                def _hook_then_start():
                    _ensure_hook_running()
                    self._apply_settings_to_clickers()
                    self._inject_callbacks()
                    self._left_clicker.start()
                    self._right_clicker.start()
                threading.Thread(target=_hook_then_start, daemon=True, name="ACHookStart").start()
            else:
                self._apply_settings_to_clickers()
                self._inject_callbacks()
                self._left_clicker.start()
                self._right_clicker.start()

            self._jitter_thread = threading.Thread(
                target=self._jitter_loop, daemon=True, name="ACJitterThread"
            )
            self._jitter_thread.start()

            self.is_active = True
            self.update_status("Active", '#00e676')
            return True
        except Exception as e:
            self.update_status(f"Start Error: {e.__class__.__name__}", '#ff5252')
            return False

    def stop(self, is_app_closing=False):
        if not self.is_active:
            return True
        try:
            self.is_active = False
            self.should_stop.set()

            if self._block_breaking.is_set():
                _send_mouse_event(MOUSEEVENTF_LEFTUP)
            self._block_breaking.clear()

            # probe中に停止した場合もLEFTUPを保証
            with self._left_clicker._probe_lock:
                state = self._left_clicker._probe_state
            if state in ("probing", "breaking"):
                _send_mouse_event(MOUSEEVENTF_LEFTUP)

            self._left_clicker.stop()
            self._right_clicker.stop()

            self._unregister_window_monitor()
            self._unregister_blockbreak()
            unregister_ac_resume_callback()
            ac_set_clicking(False)
            set_ac_jitter_active(False)

            if self._jitter_thread and self._jitter_thread.is_alive():
                self._jitter_thread.join(timeout=1.0)
            self._jitter_thread = None

            self.minecraft_active     = False
            self._jitter_drift        = 0.0
            self._last_break_end_time = 0.0

            _menu_open.clear()
            self.update_status("Inactive", '#a0a0b0')
            return True
        except Exception as e:
            self.is_active = False
            _menu_open.clear()
            self.update_status(f"Stop Error: {e.__class__.__name__}", '#ff5252')
            return False

    def toggle(self):
        return self.stop() if self.is_active else self.start()

    def reset_to_default(self, is_app_closing=False):
        _force_release_all_hooks()
        self.stop(is_app_closing=is_app_closing)
        from core.click_priority import reset_all
        reset_all()
        self.minecraft_active     = False
        self._jitter_drift        = 0.0
        self._last_break_end_time = 0.0
        _menu_open.clear()
        return True

    def validate_process(self):
        return True

    def initialize(self):
        print("AutoClicker: Initialized")
        return True