import customtkinter as ctk
from config import ConfigManager
import sys
import os
import ctypes

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

COLORS = {
    "background": "#0a0a0f",
    "surface": "#12121a",
    "card": "#1a1a24",
    "card_hover": "#1f1f2e",
    "accent": "#ff4081",
    "accent_light": "#ff6b9d",
    "accent_dark": "#e91e63",
    "text": "#ffffff",
    "text_secondary": "#a0a0b0",
    "success": "#00e676",
    "border": "#2a2a38",
    "sidebar_active": "#ff4081",
    "gradient_start": "#ff4081",
    "gradient_end": "#e91e63",
}

class ModernButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "corner_radius": 8,
            "border_width": 0,
            "fg_color": COLORS["accent"],
            "hover_color": COLORS["accent_light"],
            "text_color": COLORS["text"],
            "font": ("Segoe UI", 13, "bold"),
            "height": 42,
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)

class ModernFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "corner_radius": 10,
            "border_width": 1,
            "border_color": COLORS["border"],
            "fg_color": COLORS["card"],
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)

class ModernLabel(ctk.CTkLabel):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "text_color": COLORS["text"],
            "font": ("Segoe UI", 13),
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)

class ModernEntry(ctk.CTkEntry):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "corner_radius": 6,
            "border_width": 2,
            "border_color": COLORS["border"],
            "fg_color": COLORS["card"],
            "text_color": COLORS["text"],
            "font": ("Segoe UI", 12),
            "height": 32,
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)

_MOUSE_ALLOWED_FEATURES = {"autoclicker_left", "autoclicker_right"}

def _display_key(raw: str) -> str:
    if raw == "mouse_left":  return "MOUSE L"
    if raw == "mouse_right": return "MOUSE R"
    return raw.upper()

def _raw_key(display: str) -> str:
    if display == "MOUSE L": return "mouse_left"
    if display == "MOUSE R": return "mouse_right"
    return display.lower()


class KeybindWindow(ctk.CTkToplevel):
    WDA_NONE = 0x00000000
    WDA_EXCLUDEFROMCAPTURE = 0x00000011

    def __init__(self, parent, config: ConfigManager, update_callback=None,
                 stream_protect_active=False, on_close_callback=None):
        super().__init__(parent)
        self.geometry("420x520+-10000+-10000")

        self.config = config
        self.update_callback = update_callback
        self.keybind_entries = {}
        self.stream_protect_active = stream_protect_active
        self.on_close_callback = on_close_callback

        self._active_entry_key = None
        self._waiting = False
        self._mouse_bind_ids: dict[str, str] = {}

        self.title("Keybind Settings")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["background"])

        self.overrideredirect(True)
        self.transient(parent)
        self.grab_set()

        self._drag_x = 0
        self._drag_y = 0

        self.create_widgets()
        self.bind("<KeyPress>", self._on_window_keypress, add="+")
        self.after(150, self._move_to_center)

    def _move_to_center(self):
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w, h = 420, 520
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.geometry(f"{w}x{h}+{x}+{y}")
            if self.stream_protect_active:
                self.after(30, self._apply_stream_protect)
        except Exception as e:
            print(f"KeybindWindow move error: {e}")

    def _apply_stream_protect(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Keybind Settings")
            if hwnd and hwnd != 0:
                user32.SetWindowDisplayAffinity(hwnd, self.WDA_EXCLUDEFROMCAPTURE)
        except Exception as e:
            print(f"KeybindWindow StreamProtect apply error: {e}")

    def remove_stream_protect(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Keybind Settings")
            if hwnd and hwnd != 0:
                user32.SetWindowDisplayAffinity(hwnd, self.WDA_NONE)
        except Exception as e:
            print(f"KeybindWindow StreamProtect remove error: {e}")

    def _on_window_keypress(self, event):
        if self._active_entry_key is not None and self._waiting:
            entry_info = self.keybind_entries.get(self._active_entry_key)
            if entry_info:
                entry_info["handler"](event)
            return "break"

    def _register_mouse_binds(self, feature_key: str, on_left, on_right):
        self._unbind_mouse_binds()

        def _left(event):
            entry = self.keybind_entries.get(feature_key, {}).get("entry")
            if entry and (event.widget is entry or str(event.widget) == str(entry)):
                return
            on_left()
            return "break"

        def _right(event):
            on_right()
            return "break"

        b1 = self.bind("<Button-1>", _left, add="+")
        b3 = self.bind("<Button-3>", _right, add="+")
        self._mouse_bind_ids = {"b1": b1, "b3": b3}

    def _unbind_mouse_binds(self):
        try:
            if "b1" in self._mouse_bind_ids:
                self.unbind("<Button-1>", self._mouse_bind_ids["b1"])
        except Exception:
            pass
        try:
            if "b3" in self._mouse_bind_ids:
                self.unbind("<Button-3>", self._mouse_bind_ids["b3"])
        except Exception:
            pass
        self._mouse_bind_ids = {}

    def create_widgets(self):
        titlebar = ctk.CTkFrame(
            self, fg_color=COLORS["surface"], corner_radius=0, height=40, border_width=0,
        )
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            titlebar, text="Keybind Settings",
            font=("Segoe UI", 13, "bold"), text_color=COLORS["text"], anchor="w",
        )
        title_lbl.pack(side="left", padx=14)

        close_btn = ctk.CTkButton(
            titlebar, text="✕", width=40, height=40, corner_radius=0,
            fg_color="transparent", hover_color="#c0392b",
            text_color=COLORS["text_secondary"], font=("Segoe UI", 13),
            command=self.close_window,
        )
        close_btn.pack(side="right")

        for widget in (titlebar, title_lbl):
            widget.bind("<ButtonPress-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

        separator = ctk.CTkFrame(self, fg_color=COLORS["border"], height=1, corner_radius=0)
        separator.pack(fill="x")

        main_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["surface"], corner_radius=0, border_width=0,
        )
        main_frame.pack(fill="both", expand=True, padx=15, pady=(10, 0))

        keybind_features = {
            "brightness":        "Fullbright",
            "zoom":              "Zoom",
            "sprint":            "Sprint",
            "autoclicker_left":  "AutoClicker (Left)",
            "autoclicker_right": "AutoClicker (Right)",
            "window_visibility": "Window Visibility Toggle",
        }

        for feature_key, feature_name in keybind_features.items():
            self.create_keybind_card(main_frame, feature_key, feature_name)

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill="x", padx=15, pady=10)
        ModernButton(button_frame, text="Close", command=self.close_window).pack(
            side="right", fill="x", expand=True
        )

    def _on_drag_start(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag_motion(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def create_keybind_card(self, parent, feature_key: str, feature_name: str):
        card = ModernFrame(parent)
        card.pack(fill="x", pady=6)

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=16, pady=12)
        content.grid_columnconfigure(1, weight=1)

        ModernLabel(
            content, text=feature_name,
            font=("Segoe UI", 13, "bold"), anchor="w"
        ).grid(row=0, column=0, sticky="w", padx=(0, 20))

        current_raw = self.config.get_keybind(feature_key) or "None"
        current_display = _display_key(current_raw)

        key_entry = ModernEntry(content, width=120, justify="center")
        key_entry.grid(row=0, column=1, sticky="e")
        key_entry.insert(0, current_display)
        key_entry.configure(state="readonly")

        allow_mouse = feature_key in _MOUSE_ALLOWED_FEATURES

        def _set_entry(text, border=COLORS["border"], color=COLORS["text"]):
            key_entry.configure(state="normal", border_color=border, text_color=color)
            key_entry.delete(0, "end")
            key_entry.insert(0, text)
            key_entry.configure(state="readonly")

        def _stop_waiting():
            self._unbind_mouse_binds()
            self._active_entry_key = None
            self._waiting = False

        def _restore():
            _stop_waiting()
            raw = self.config.get_keybind(feature_key) or "None"
            _set_entry(_display_key(raw), COLORS["border"], COLORS["text"])

        def _apply(new_raw: str):
            _stop_waiting()
            self.config.set_keybind(feature_key, new_raw)
            _set_entry(_display_key(new_raw), COLORS["success"], COLORS["success"])
            self.after(600, lambda: _set_entry(_display_key(new_raw)))
            if self.update_callback:
                self.update_callback()

        def on_key_press(event):
            if self._active_entry_key != feature_key or not self._waiting:
                return

            new_key = event.keysym.lower()

            if feature_key == "window_visibility":
                if new_key in ["shift_l", "shift_r"]:
                    new_key = "left shift" if new_key == "shift_l" else "right shift"
            else:
                ignore_keys = [
                    "shift", "shift_l", "shift_r",
                    "control", "control_l", "control_r",
                    "alt", "alt_l", "alt_r",
                    "caps_lock", "tab", "escape",
                    "super_l", "super_r", "win_l", "win_r",
                ]
                if new_key in ignore_keys:
                    _stop_waiting()
                    self.show_error(key_entry, "Invalid Key!", feature_key)
                    return "break"

            if not new_key.startswith("mouse_"):
                current_keybinds = self.config.config.get("keybinds", {})
                for other_feature, bound_key in current_keybinds.items():
                    if other_feature != feature_key and bound_key == new_key:
                        _stop_waiting()
                        self.show_error(key_entry, "Key in Use!", feature_key)
                        return "break"

            _apply(new_key)
            return "break"

        def _start_waiting():
            if self._waiting and self._active_entry_key != feature_key:
                old_key = self._active_entry_key
                if old_key and old_key in self.keybind_entries:
                    old_entry = self.keybind_entries[old_key]["entry"]
                    self._unbind_mouse_binds()
                    self._active_entry_key = None
                    self._waiting = False
                    old_raw = self.config.get_keybind(old_key) or "None"
                    old_entry.configure(state="normal", border_color=COLORS["border"],
                                        text_color=COLORS["text"])
                    old_entry.delete(0, "end")
                    old_entry.insert(0, _display_key(old_raw))
                    old_entry.configure(state="readonly")

            self._active_entry_key = feature_key
            self._waiting = True
            _set_entry("Press key / click...", COLORS["accent_light"], COLORS["accent_light"])
            self.focus_set()

            if allow_mouse:
                self.after(150, lambda: _register_mouse_if_waiting())

        def _register_mouse_if_waiting():
            if not self._waiting or self._active_entry_key != feature_key:
                return
            self._register_mouse_binds(
                feature_key,
                on_left=lambda: _apply("mouse_left"),
                on_right=lambda: _apply("mouse_right"),
            )

        def on_click(event):
            _start_waiting()

        def on_focus_out(event):
            if self._active_entry_key == feature_key and self._waiting:
                focused = self.focus_get()
                if focused is None:
                    _restore()

        key_entry.bind("<Button-1>", on_click)
        key_entry.bind("<FocusOut>", on_focus_out)

        self.keybind_entries[feature_key] = {
            "entry":   key_entry,
            "handler": on_key_press,
        }

    def _stop_waiting(self, feature_key=None):
        if feature_key is None or self._active_entry_key == feature_key:
            self._unbind_mouse_binds()
            self._active_entry_key = None
            self._waiting = False

    def show_success(self, entry):
        entry.configure(border_color=COLORS["success"], text_color=COLORS["success"])
        self.after(600, lambda: entry.configure(
            border_color=COLORS["border"], text_color=COLORS["text"]
        ))

    def show_error(self, entry, message, feature_key=None):
        if feature_key:
            raw = self.config.get_keybind(feature_key) or "None"
            original_text = _display_key(raw)
        else:
            original_text = entry.get()
            if original_text == "Press key / click...":
                fk = self._active_entry_key
                raw = self.config.get_keybind(fk) or "None" if fk else "None"
                original_text = _display_key(raw)

        entry.configure(state="normal", border_color="#ff5252", text_color="#ff5252")
        entry.delete(0, "end")
        entry.insert(0, message)
        entry.configure(state="readonly")
        self.after(1200, lambda: self.restore_entry(entry, original_text))

    def restore_entry(self, entry, original_text):
        entry.configure(state="normal", border_color=COLORS["border"],
                        text_color=COLORS["text"])
        entry.delete(0, "end")
        entry.insert(0, original_text)
        entry.configure(state="readonly")

    def close_window(self):
        self._stop_waiting()
        if self.on_close_callback:
            self.on_close_callback()
        self.geometry("420x520+-10000+-10000")
        if self.stream_protect_active:
            self.remove_stream_protect()
        self.grab_release()
        self.after(80, self.destroy)