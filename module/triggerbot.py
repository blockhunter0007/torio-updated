import ctypes
from ctypes import wintypes
import time
import threading
import queue

from core.aim_detector import get_shared_detector
from core.menu_monitor import get_shared_menu_monitor
from core.click_priority import tb_try_start, tb_set_clicking, tb_is_blocked, set_tb_click_active, record_click_time
from core.minecraft_windowmonitor import get_shared_window_monitor
from core.mouse_jitter import apply_jitter_during_click
from pynput.keyboard import Controller as KeyboardController, Key

MOUSEEVENTF_LEFTDOWN  = 0x0002
MOUSEEVENTF_LEFTUP    = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP   = 0x0010
INPUT_MOUSE = 0

MY_EXTRA  = 0xABCD1234
ULONG_PTR = ctypes.c_uint64

_user32 = ctypes.windll.user32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg",    wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


def _send_mouse_input(flags: int) -> bool:
    ii_    = _InputUnion()
    ii_.mi = MOUSEINPUT(0, 0, 0, flags, 0, MY_EXTRA)
    x = INPUT(INPUT_MOUSE, ii_)
    return _user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x)) == 1

_SPECIAL_KEYS = {
    "space":     Key.space,
    "enter":     Key.enter,
    "shift":     Key.shift,
    "ctrl":      Key.ctrl,
    "alt":       Key.alt,
    "tab":       Key.tab,
    "backspace": Key.backspace,
    "delete":    Key.delete,
    "escape":    Key.esc,
    "up":        Key.up,
    "down":      Key.down,
    "left":      Key.left,
    "right":     Key.right,
    "f1":  Key.f1,  "f2":  Key.f2,  "f3":  Key.f3,  "f4":  Key.f4,
    "f5":  Key.f5,  "f6":  Key.f6,  "f7":  Key.f7,  "f8":  Key.f8,
    "f9":  Key.f9,  "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
}

_keyboard = KeyboardController()


def is_mouse_button(attack: str) -> bool:
    return attack in ("mouse_left", "mouse_right")


def _resolve_key(key_name: str):
    low = key_name.lower()
    if low in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[low]
    return low


def send_attack_once(attack: str):
    if tb_is_blocked():
        return

    if attack == "mouse_left":
        _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        time.sleep(0.01)
        _send_mouse_input(MOUSEEVENTF_LEFTUP)
    elif attack == "mouse_right":
        _send_mouse_input(MOUSEEVENTF_RIGHTDOWN)
        time.sleep(0.01)
        _send_mouse_input(MOUSEEVENTF_RIGHTUP)
    else:
        key = _resolve_key(attack)
        try:
            _keyboard.press(key)
            time.sleep(0.01)
            _keyboard.release(key)
        except Exception:
            pass


class _AutoClicker:
    def __init__(self, cps: float = 12.0, attack: str = "mouse_left"):
        self._cps      = max(1.0, min(20.0, cps))
        self._attack   = attack
        self._clicking = threading.Event()
        self._stop_ev  = threading.Event()
        self._thread: threading.Thread | None = None
        self.jitter_enabled = False
        self.jitter_strength = 2.0

    @property
    def cps(self):
        return self._cps

    @cps.setter
    def cps(self, v: float):
        self._cps = max(1.0, min(20.0, v))

    def set_attack(self, attack: str):
        self._attack = attack

    def _loop(self):
        last = 0.0
        while not self._stop_ev.is_set():
            if not self._clicking.is_set():
                self._clicking.wait(timeout=0.01)
                last = 0.0
                continue

            if tb_is_blocked():
                time.sleep(0.005)
                last = 0.0
                continue

            interval = 1.0 / self._cps

            now = time.perf_counter()
            elapsed = now - last

            if elapsed >= interval:
                last = now
                self._do_attack()
            else:
                remaining = interval - elapsed
                if remaining > 0.002:
                    time.sleep(remaining - 0.002)
                target = last + interval
                while time.perf_counter() < target:
                    pass

    def _do_attack(self):
        attack = self._attack
        click_duration = 0.01
        
        if attack == "mouse_left":
            # クリック中フラグをセット（エイムアシストブースト用）
            set_tb_click_active(True)
            record_click_time()  # クリック時刻を記録
            
            # 直接SendInput（高速、スケジューラのキューイングなし）
            _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
            if self.jitter_enabled:
                apply_jitter_during_click(True, self.jitter_strength, click_duration, use_scheduler=False)
            else:
                time.sleep(click_duration)
            _send_mouse_input(MOUSEEVENTF_LEFTUP)
            
            set_tb_click_active(False)
        elif attack == "mouse_right":
            set_tb_click_active(True)
            record_click_time()
            
            _send_mouse_input(MOUSEEVENTF_RIGHTDOWN)
            if self.jitter_enabled:
                apply_jitter_during_click(False, self.jitter_strength, click_duration, use_scheduler=False)
            else:
                time.sleep(click_duration)
            _send_mouse_input(MOUSEEVENTF_RIGHTUP)
            
            set_tb_click_active(False)
        else:
            key = _resolve_key(attack)
            try:
                _keyboard.press(key)
                time.sleep(click_duration)
                _keyboard.release(key)
            except Exception:
                pass

    def start_thread(self):
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_thread(self):
        self._stop_ev.set()
        self._clicking.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def enable(self):
        if tb_is_blocked():
            return
        if tb_try_start():
            self._clicking.set()
    def disable(self):
        self._clicking.clear()
        tb_set_clicking(False)   # ← 条件なしで常にリセット


class TriggerBotController:
    def __init__(self):
        self.update_queue: queue.Queue | None = None
        self.initialized   = False
        self.is_active     = False

        self.mode          = "first_hit"
        self.auto_cps      = 12.0
        self.attack_button = "mouse_left"
        self.jitter_enabled = False
        self.jitter_strength = 2.0

        self._detector     = get_shared_detector()
        self._menu_monitor = get_shared_menu_monitor()
        self._window_monitor = get_shared_window_monitor()
        self._auto_clicker = _AutoClicker(cps=self.auto_cps, attack=self.attack_button)

    def set_update_queue(self, q: queue.Queue):
        self.update_queue = q

    def set_pymem_process(self, pm):
        self._detector.set_pymem_process(pm)
        self._menu_monitor.set_pymem_process(pm)

    def validate_process(self) -> bool:
        return self._detector.validate_process()

    def set_mode(self, mode: str):
        self.mode = mode
        if self.is_active and mode == "auto_click":
            self._auto_clicker.start_thread()
        elif self.is_active and mode == "first_hit":
            self._auto_clicker.stop_thread()

    def set_auto_cps(self, cps: float):
        self.auto_cps          = min(cps, 20.0)
        self._auto_clicker.cps = self.auto_cps

    def set_attack_button(self, attack: str):
        self.attack_button = attack
        self._auto_clicker.set_attack(attack)

    def set_mouse_button(self, button: str):
        mapping = {"left": "mouse_left", "right": "mouse_right"}
        self.set_attack_button(mapping.get(button, button))

    def set_jitter(self, enabled: bool, strength: float):
        self.jitter_enabled = enabled
        self.jitter_strength = max(1.0, min(5.0, strength))
        self._auto_clicker.jitter_enabled = self.jitter_enabled
        self._auto_clicker.jitter_strength = self.jitter_strength

    def _on_aim_changed(self, is_aiming: bool):
        if not self.is_active:
            return

        if self._menu_monitor.is_menu_open:
            return

        if not self._window_monitor.get_is_active():
            return

        if is_aiming:
            if self.mode == "first_hit":
                threading.Thread(
                    target=send_attack_once,
                    args=(self.attack_button,),
                    daemon=True
                ).start()
            elif self.mode == "auto_click":
                self._auto_clicker.enable()
        else:
            if self.mode == "auto_click":
                self._auto_clicker.disable()

    def _on_menu_changed(self, is_menu_open: bool):
        if not self.is_active:
            return
        if is_menu_open:
            if self.mode == "auto_click":
                self._auto_clicker.disable()
        else:
            if not self._window_monitor.get_is_active():
                return
            if self._detector.is_aiming:
                if self.mode == "auto_click":
                    self._auto_clicker.enable()
                elif self.mode == "first_hit":
                    threading.Thread(
                        target=send_attack_once,
                        args=(self.attack_button,),
                        daemon=True
                    ).start()

    def _register_window_monitor(self):
        try:
            m = get_shared_window_monitor()
            m.add_listener(self._on_mc_active_changed)
            with self._state_lock:
                self.minecraft_active = m.get_is_active()
            self._window_monitor = m
        except Exception:
            with self._state_lock:
                self.minecraft_active = True

    def _on_window_changed(self, is_window_active: bool):
        if not self.is_active:
            return
        if not is_window_active:
            # ウィンドウが非アクティブになったらクリッカーを無効化
            if self.mode == "auto_click":
                self._auto_clicker.disable()
        else:
            # ウィンドウがアクティブになったらエイム状態を確認
            if self._detector.is_aiming:
                if self.mode == "auto_click":
                    self._auto_clicker.enable()
                elif self.mode == "first_hit":
                    threading.Thread(
                        target=send_attack_once,
                        args=(self.attack_button,),
                        daemon=True
                    ).start()

    def _update_status(self, message: str, color: str):
        if self.update_queue:
            self.update_queue.put(('status_update', ('triggerbot', message, color)))

    def initialize(self) -> bool:
        self.initialized = False

        from core.aim_detector import get_shared_detector
        from core.menu_monitor import get_shared_menu_monitor
        self._detector     = get_shared_detector()
        self._menu_monitor = get_shared_menu_monitor()
        self._window_monitor = get_shared_window_monitor()

        if not self._detector.initialize():
            self._update_status("Init Failed", '#ff5252')
            return False

        if not self._menu_monitor.initialized:
            self._menu_monitor.initialize()

        self.initialized = True
        print("TriggerBot: Initialized")
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

        self._window_monitor.add_listener(self._on_window_changed)
        self._window_monitor.start()

        if self.mode == "auto_click":
            self._auto_clicker.set_attack(self.attack_button)
            self._auto_clicker.cps = self.auto_cps
            self._auto_clicker.start_thread()

        self.is_active = True
        self._update_status("Active", '#00e676')
        return True

    def stop(self, is_app_closing: bool = False):
        if not self.is_active:
            return True
        self._detector.remove_listener(self._on_aim_changed)

        self._menu_monitor.remove_listener(self._on_menu_changed)

        self._window_monitor.remove_listener(self._on_window_changed)

        self._auto_clicker.disable()
        self._auto_clicker.stop_thread()
        self.is_active = False
        self._update_status("Inactive", '#b0b0b0')
        return True

    def reset_to_default(self, is_app_closing: bool = False):
        self.stop(is_app_closing=is_app_closing)
        self.initialized = False
        return True

    def validate_process(self) -> bool:
        return self._detector.validate_process()