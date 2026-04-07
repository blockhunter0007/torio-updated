import threading
import time
import psutil
import win32gui
import win32process


TARGET_PROCESS = "Minecraft.Windows.exe"
_CHECK_INTERVAL = 0.05


class MinecraftWindowMonitor:
    def __init__(self):
        self._hwnd: int | None = None
        self._running = False
        self._should_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

        self.is_active = False

        self._listeners: list = []
        self._listener_lock = threading.Lock()
        self._state_lock = threading.Lock()

    def add_listener(self, callback):
        with self._listener_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback):
        with self._listener_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, is_active: bool):
        with self._listener_lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(is_active)
            except Exception:
                pass

    def _find_hwnd(self) -> int | None:
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"].lower() == TARGET_PROCESS.lower():
                    pid = proc.info["pid"]
                    found: list[int] = []

                    def _enum(hwnd, _):
                        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
                        if wpid == pid and win32gui.IsWindowVisible(hwnd):
                            found.append(hwnd)

                    win32gui.EnumWindows(_enum, None)
                    if found:
                        return found[0]
        except Exception:
            pass
        return None

    def _check_active(self) -> bool:
        try:
            if not self._hwnd:
                self._hwnd = self._find_hwnd()
                if not self._hwnd:
                    return False
            fg = win32gui.GetForegroundWindow()
            if fg == self._hwnd:
                return True
            if not win32gui.IsWindow(self._hwnd):
                self._hwnd = None
            return False
        except Exception:
            self._hwnd = None
            return False

    def _monitor_loop(self):
        current = self._check_active()
        with self._state_lock:
            self.is_active = current
        prev_active = current
        self._notify(current)

        while not self._should_stop.is_set():
            current = self._check_active()

            with self._state_lock:
                self.is_active = current

            if current != prev_active:
                prev_active = current
                threading.Thread(
                    target=self._notify,
                    args=(current,),
                    daemon=True,
                ).start()

            self._should_stop.wait(timeout=_CHECK_INTERVAL)

    def start(self):
        if self._running:
            return
        self._should_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="MCWindowMonitorThread",
            daemon=True,
        )
        self._monitor_thread.start()
        self._running = True

    def stop(self):
        if not self._running:
            return
        self._should_stop.set()
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        self._monitor_thread = None

    def get_is_active(self) -> bool:
        with self._state_lock:
            return self.is_active

    def invalidate_hwnd(self):
        self._hwnd = None


_shared_monitor: MinecraftWindowMonitor | None = None
_monitor_lock = threading.Lock()


def get_shared_window_monitor() -> MinecraftWindowMonitor:
    global _shared_monitor
    with _monitor_lock:
        if _shared_monitor is None:
            _shared_monitor = MinecraftWindowMonitor()
            _shared_monitor.start()
        return _shared_monitor


def reset_shared_window_monitor():
    global _shared_monitor
    with _monitor_lock:
        if _shared_monitor is not None:
            _shared_monitor.stop()
            _shared_monitor = None


def reinitialize_shared_window_monitor():
    global _shared_monitor
    with _monitor_lock:
        if _shared_monitor is not None:
            _shared_monitor.stop()
        _shared_monitor = MinecraftWindowMonitor()
        _shared_monitor.start()
    return _shared_monitor