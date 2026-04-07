import ctypes
import threading
import time
import keyboard
from config import ConfigManager

class StreamProtectController:
    WDA_NONE = 0x00000000
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    GWL_EXSTYLE = -20
    GWL_STYLE = -16
    GWLP_HWNDPARENT = -8
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    WS_MINIMIZEBOX = 0x00020000
    SW_HIDE = 0
    SW_SHOW = 5

    SWP_FRAMECHANGED = 0x0020
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_DRAWFRAME = 0x0020
    
    def __init__(self):
        self.is_active = False
        self.initialized = False
        self.update_queue = None
        self.protected_windows = {}
        self.affinity_only_windows = {}
        self.affinity_only_titles = set()
        self.hidden_parent = None
        self.original_parents = {}
        self.original_ex_styles = {}
        self.original_styles = {}
        self.windows_visible = True
        self.hotkey_registered = False
        
        self.config_manager = ConfigManager("config.json")
        self.current_key = self.config_manager.get_keybind('window_visibility') or 'right shift'
        self.keybind_monitoring_active = False
        self.keybind_monitor_thread = None
        self.should_stop = threading.Event()
        
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.SetWindowDisplayAffinity = self.user32.SetWindowDisplayAffinity
        self.GetWindowLongW = self.user32.GetWindowLongW
        self.GetWindowLongPtrW = self.user32.GetWindowLongPtrW
        self.SetWindowLongW = self.user32.SetWindowLongW
        self.SetWindowLongPtrW = self.user32.SetWindowLongPtrW
        self.IsWindow = self.user32.IsWindow
        self.FindWindowW = self.user32.FindWindowW
        self.CreateWindowExW = self.user32.CreateWindowExW
        self.DestroyWindow = self.user32.DestroyWindow
        self.ShowWindow = self.user32.ShowWindow
        self.SetWindowPos = self.user32.SetWindowPos
        self.InvalidateRect = self.user32.InvalidateRect
        self.UpdateWindow = self.user32.UpdateWindow
        
        self.user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        self.user32.SetForegroundWindow.restype = ctypes.c_bool
        self.user32.SetActiveWindow.argtypes = [ctypes.c_void_p]
        self.user32.SetActiveWindow.restype = ctypes.c_void_p
        self.user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        self.user32.BringWindowToTop.restype = ctypes.c_bool
        self.user32.SetFocus.argtypes = [ctypes.c_void_p]
        self.user32.SetFocus.restype = ctypes.c_void_p
        self.user32.GetForegroundWindow.argtypes = []
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        self.user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
        self.user32.AttachThreadInput.restype = ctypes.c_bool
        
    def _create_hidden_parent(self):
        if self.hidden_parent is None:
            self.hidden_parent = self.CreateWindowExW(
                0x08000000,
                "Static",
                "",
                0x80000000,
                0, 0, 0, 0,
                None, None, None, None
            )
        return self.hidden_parent

    def set_update_queue(self, queue):
        self.update_queue = queue

    def register_window(self, window_title: str, hwnd: int = None):
        """通常の保護登録（スタイル変更あり）"""
        if hwnd is None:
            hwnd = self.FindWindowW(None, window_title)
        if hwnd != 0 and self.IsWindow(hwnd):
            self.protected_windows[window_title] = hwnd
            if self.is_active:
                self._apply_protection(hwnd)
            return True
        return False

    def register_window_affinity_only(self, window_title: str, hwnd: int = None):
        """SetWindowDisplayAffinityのみ適用（スタイル変更なし）"""
        if hwnd is None:
            hwnd = self.FindWindowW(None, window_title)
        if hwnd != 0 and self.IsWindow(hwnd):
            self.affinity_only_windows[window_title] = hwnd
            self.affinity_only_titles.add(window_title)
            if self.is_active:
                self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)
            return True
        return False

    def unregister_window(self, window_title: str):
        if window_title in self.protected_windows:
            hwnd = self.protected_windows[window_title]
            if self.is_active:
                self._remove_protection(hwnd)
            del self.protected_windows[window_title]
            if hwnd in self.original_parents:
                del self.original_parents[hwnd]
            if hwnd in self.original_ex_styles:
                del self.original_ex_styles[hwnd]
            if hwnd in self.original_styles:
                del self.original_styles[hwnd]
        elif window_title in self.affinity_only_windows:
            hwnd = self.affinity_only_windows[window_title]
            if self.is_active:
                self.SetWindowDisplayAffinity(hwnd, self.WDA_NONE)
            del self.affinity_only_windows[window_title]
            self.affinity_only_titles.discard(window_title)

    def _reapply_affinity_by_title(self):
        for title in list(self.affinity_only_titles):
            hwnd = self.FindWindowW(None, title)
            if hwnd and hwnd != 0 and self.IsWindow(hwnd):
                self.affinity_only_windows[title] = hwnd
                self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)

    def _force_focus_to_window(self, target_hwnd):
        try:
            current_thread = self.kernel32.GetCurrentThreadId()
            foreground_hwnd = self.user32.GetForegroundWindow()
            if foreground_hwnd:
                foreground_thread = self.user32.GetWindowThreadProcessId(foreground_hwnd, None)
                self.user32.AttachThreadInput(foreground_thread, current_thread, True)
            
            self.user32.BringWindowToTop(target_hwnd)
            self.user32.ShowWindow(target_hwnd, self.SW_SHOW)
            self.user32.SetForegroundWindow(target_hwnd)
            self.user32.SetFocus(target_hwnd)
            self.user32.SetActiveWindow(target_hwnd)
            
            if foreground_hwnd:
                self.user32.AttachThreadInput(foreground_thread, current_thread, False)
                
            return True
        except Exception as e:
            print(f"Focus error: {e}")
            return False

    def _toggle_window_visibility(self):
        if not self.is_active:
            return
    
        self.windows_visible = not self.windows_visible

        if self.windows_visible:
            for hwnd in self.protected_windows.values():
                if self.IsWindow(hwnd):
                    self.ShowWindow(hwnd, self.SW_SHOW)
            for hwnd in self.affinity_only_windows.values():
                if self.IsWindow(hwnd):
                    self.ShowWindow(hwnd, self.SW_SHOW)
        
            time.sleep(0.1)
        
            for hwnd in self.protected_windows.values():
                if self.IsWindow(hwnd):
                    self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)
            for hwnd in self.affinity_only_windows.values():
                if self.IsWindow(hwnd):
                    self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)

            self._reapply_affinity_by_title()

            time.sleep(0.05)
            first_hwnd = next(iter(self.protected_windows.values()), None)
            if first_hwnd and self.IsWindow(first_hwnd):
                self._force_focus_to_window(first_hwnd)

            if self.update_queue:
                self.update_queue.put(('raise_keybind_window', None))
        else:
            for hwnd in self.protected_windows.values():
                if self.IsWindow(hwnd):
                    self.ShowWindow(hwnd, self.SW_HIDE)
            for hwnd in self.affinity_only_windows.values():
                if self.IsWindow(hwnd):
                    self.ShowWindow(hwnd, self.SW_HIDE)
            self._hide_affinity_only_by_title()

        if self.update_queue:
            visibility_status = "Visible" if self.windows_visible else "Hidden"
            self.update_queue.put(('visibility_update', visibility_status))

    def _hide_affinity_only_by_title(self):
        for title in list(self.affinity_only_titles):
            hwnd = self.FindWindowW(None, title)
            if hwnd and hwnd != 0 and self.IsWindow(hwnd):
                self.affinity_only_windows[title] = hwnd
                self.ShowWindow(hwnd, self.SW_HIDE)

    def monitor_keybind(self):
        while self.keybind_monitoring_active and not self.should_stop.is_set():
            try:
                new_key = self.config_manager.get_keybind("window_visibility") or "right shift"
                if new_key != self.current_key:
                    print(f"StreamProtect: Keybind changed from '{self.current_key}' to '{new_key}'")
                    self._unregister_hotkey()
                    self.current_key = new_key
                    self._register_hotkey()
                time.sleep(0.3)
            except Exception as e:
                print(f"Keybind monitoring error: {e}")
                time.sleep(1)

    def start_keybind_monitoring(self):
        if not self.keybind_monitoring_active:
            self.keybind_monitoring_active = True
            self.should_stop.clear()
            self.keybind_monitor_thread = threading.Thread(target=self.monitor_keybind, daemon=True)
            self.keybind_monitor_thread.start()
            print("StreamProtect: Keybind monitoring started")

    def stop_keybind_monitoring(self):
        if self.keybind_monitoring_active:
            self.keybind_monitoring_active = False
            if self.keybind_monitor_thread and threading.current_thread() is not self.keybind_monitor_thread:
                try:
                    self.keybind_monitor_thread.join(timeout=1)
                except Exception:
                    pass
                self.keybind_monitor_thread = None
            else:
                self.keybind_monitor_thread = None
            print("StreamProtect: Keybind monitoring stopped")

    def _register_hotkey(self):
        if not self.hotkey_registered:
            try:
                keyboard.on_press_key(self.current_key, lambda _: self._toggle_window_visibility())
                self.hotkey_registered = True
                print(f"StreamProtect: '{self.current_key}' hotkey registered")
            except Exception as e:
                print(f"Hotkey registration error: {e}")

    def _unregister_hotkey(self):
        if self.hotkey_registered:
            try:
                keyboard.unhook_key(self.current_key)
                self.hotkey_registered = False
                print(f"StreamProtect: '{self.current_key}' hotkey unregistered")
            except Exception as e:
                print(f"Hotkey unregistration error: {e}")

    def _apply_protection(self, hwnd: int):
        try:
            self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)
        
            if hwnd not in self.original_parents:
                self.original_parents[hwnd] = self.GetWindowLongPtrW(hwnd, self.GWLP_HWNDPARENT)
        
            if hwnd not in self.original_ex_styles:
                self.original_ex_styles[hwnd] = self.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
        
            if hwnd not in self.original_styles:
                self.original_styles[hwnd] = self.GetWindowLongW(hwnd, self.GWL_STYLE)
        
            parent = self._create_hidden_parent()
            self.SetWindowLongPtrW(hwnd, self.GWLP_HWNDPARENT, parent)
            ex_style = self.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
            ex_style &= ~self.WS_EX_APPWINDOW
            ex_style &= ~self.WS_EX_TOOLWINDOW
            ex_style |= self.WS_EX_NOACTIVATE
            self.SetWindowLongW(hwnd, self.GWL_EXSTYLE, ex_style)
        
            style = self.GetWindowLongW(hwnd, self.GWL_STYLE)
            style &= ~self.WS_MINIMIZEBOX
            self.SetWindowLongW(hwnd, self.GWL_STYLE, style)
        
            self.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                self.SWP_FRAMECHANGED | self.SWP_NOMOVE | self.SWP_NOSIZE | 
                self.SWP_NOZORDER | self.SWP_NOACTIVATE
            )
        
            self.InvalidateRect(hwnd, None, True)
            self.UpdateWindow(hwnd)
        
        except Exception as e:
            print(f"Protection error: {e}")

    def _remove_protection(self, hwnd: int):
        try:
            self.SetWindowDisplayAffinity(hwnd, self.WDA_NONE)
        
            original_parent = self.original_parents.get(hwnd, 0)
            self.SetWindowLongPtrW(hwnd, self.GWLP_HWNDPARENT, original_parent)
        
            original_ex_style = self.original_ex_styles.get(hwnd, None)
            if original_ex_style is not None:
                self.SetWindowLongW(hwnd, self.GWL_EXSTYLE, original_ex_style)
            else:
                ex_style = self.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
                ex_style |= self.WS_EX_APPWINDOW
                ex_style &= ~self.WS_EX_TOOLWINDOW
                ex_style &= ~self.WS_EX_NOACTIVATE
                self.SetWindowLongW(hwnd, self.GWL_EXSTYLE, ex_style)
    
            original_style = self.original_styles.get(hwnd, None)
            if original_style is not None:
                self.SetWindowLongW(hwnd, self.GWL_STYLE, original_style)
            else:
                style = self.GetWindowLongW(hwnd, self.GWL_STYLE)
                style |= self.WS_MINIMIZEBOX
                self.SetWindowLongW(hwnd, self.GWL_STYLE, style)
        
            self.ShowWindow(hwnd, self.SW_HIDE)
        
            self.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                self.SWP_FRAMECHANGED | self.SWP_NOMOVE | self.SWP_NOSIZE | 
                self.SWP_NOZORDER | self.SWP_NOACTIVATE
            )
        
            HWND_NOTOPMOST = -2
            self.SetWindowPos(
                hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE
            )
        
            self.ShowWindow(hwnd, self.SW_SHOW)
            self.user32.SetForegroundWindow(hwnd)
            self.InvalidateRect(hwnd, None, True)
            self.UpdateWindow(hwnd)
    
        except Exception as e:
            print(f"Unprotection error: {e}")

    def start(self):
        if not self.initialized or self.is_active:
            return False

        for hwnd in self.protected_windows.values():
            if self.IsWindow(hwnd):
                self._apply_protection(hwnd)

        for hwnd in self.affinity_only_windows.values():
            if self.IsWindow(hwnd):
                self.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)

        self.is_active = True
        self.windows_visible = True
        
        self._register_hotkey()
        self.start_keybind_monitoring()
        
        if self.update_queue:
            self.update_queue.put(('status_update', ('streamprotect', "Active", '#00e676')))
        return True

    def stop(self):
        if not self.is_active:
            return True
        
        self.stop_keybind_monitoring()
        self._unregister_hotkey()
        
        for hwnd in self.protected_windows.values():
            if self.IsWindow(hwnd):
                self._remove_protection(hwnd)

        for hwnd in self.affinity_only_windows.values():
            if self.IsWindow(hwnd):
                self.SetWindowDisplayAffinity(hwnd, self.WDA_NONE)

        self.is_active = False
        self.windows_visible = True
        if self.update_queue:
            self.update_queue.put(('status_update', ('streamprotect', "Inactive", '#b0b0b0')))
        return True

    def initialize(self):
        if len(self.protected_windows) == 0:
            return False
        self.initialized = True
        print("StreamProtect: initialized")
        return True

    def reset_to_default(self, is_app_closing=False):
        if self.is_active:
            self.stop()
        
        self.stop_keybind_monitoring()
        self._unregister_hotkey()
        
        if self.hidden_parent:
            self.DestroyWindow(self.hidden_parent)
            self.hidden_parent = None
            
        self.protected_windows.clear()
        self.affinity_only_windows.clear()
        self.affinity_only_titles.clear()
        self.original_parents.clear()
        self.original_ex_styles.clear()
        self.original_styles.clear()
        self.initialized = False

    def cleanup(self):
        self.stop_keybind_monitoring()
        self.reset_to_default(is_app_closing=True)