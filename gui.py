import customtkinter as ctk
from PIL import Image
import os
import sys
import threading
import time
import queue
import pymem
import ctypes
import re
from config import ConfigManager
from module.antiknockback import AntiKnockbackController
from module.reach import ReachController
from module.hitbox import HitboxController
from module.zoom import ZoomController
from module.brightness import BrightnessController
from keybindgui import KeybindWindow
from module.streamprotect import StreamProtectController
from module.speed import SpeedController
from module.coordinates import CoordinatesController
from module.autoclicker import AutoClickerController
from module.sprint import SprintController
from version_detector import MinecraftVersionDetector
from module.nohurtcam import NoHurtCamController
from module.truesight import TrueSightController
from module.timechanger import TimeChangerController
from module.fastitem import FastItemController
from module.systemtray import SystemTrayController
from module.jumpreset import JumpResetController
from module.triggerbot import TriggerBotController
from module.microaim import MicroAimController
from module.aimassist import AimAssistController
from core.click_priority import reset_all as reset_click_priority
from core.aim_detector import reset_shared_detector
from core.menu_monitor import reset_shared_menu_monitor, reinitialize_shared_menu_monitor
from core.minecraft_windowmonitor import (
    get_shared_window_monitor,
    reset_shared_window_monitor,
    reinitialize_shared_window_monitor,
)
from core.blockbreak_detector import (
    get_shared_block_detector,
    reset_shared_block_detector,
    reinitialize_shared_block_detector,
)
from core.world_status import (
    get_shared_world_monitor,
    reset_shared_world_monitor,
    reinitialize_shared_world_monitor,
)
from core.input_scheduler import reset_scheduler
from tkinter import Canvas
from PIL import Image, ImageDraw, ImageTk
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
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

def _ac_key_display(key: str) -> str:
    if key == "mouse_left":  return "L_M"
    if key == "mouse_right": return "R_M"
    return key.upper()

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
def load_custom_font(font_path, font_name):
    try:
        from ctypes import windll, create_unicode_buffer
        FR_PRIVATE = 0x10
        path = resource_path(font_path)
        windll.gdi32.AddFontResourceExW(create_unicode_buffer(path), FR_PRIVATE, 0)
        return font_name
    except Exception as e:
        print(f"フォント読み込み失敗: {e}")
        return "Segoe UI"
class ModernButton(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "corner_radius": 12,
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
            "corner_radius": 16,
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
class ModernSlider(ctk.CTkSlider):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "button_color": COLORS["accent"],
            "button_hover_color": COLORS["accent_light"],
            "progress_color": COLORS["accent"],
            "fg_color": COLORS["border"],
            "height": 16,
            "corner_radius": 8,
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)
class ModernSwitch(ctk.CTkSwitch):
    @staticmethod
    def _get_parent_bg_color_static(master):
        try:
            parent = master
            while parent:
                try:
                    parent_bg = parent.cget("fg_color")
                    if parent_bg and parent_bg != "transparent":
                        if isinstance(parent_bg, tuple):
                            color = parent_bg[1] if ctk.get_appearance_mode() == "Dark" else parent_bg[0]
                            if isinstance(color, str) and " " in color:
                                color = color.split()[0]
                            return color
                        elif isinstance(parent_bg, str):
                            if " " in parent_bg:
                                return parent_bg.split()[0]
                            return parent_bg
                    parent = parent.master
                except:
                    parent = getattr(parent, 'master', None)
            return "#1a1a24"
        except:
            return "#1a1a24"
    def _get_parent_bg_color(self):
        try:
            parent = self.master
            while parent:
                try:
                    parent_bg = parent.cget("fg_color")
                    if parent_bg and parent_bg != "transparent":
                        if isinstance(parent_bg, tuple):
                            color = parent_bg[1] if ctk.get_appearance_mode() == "Dark" else parent_bg[0]
                            if isinstance(color, str) and " " in color:
                                color = color.split()[0]
                            return color
                        elif isinstance(parent_bg, str):
                            if " " in parent_bg:
                                return parent_bg.split()[0]
                            return parent_bg
                    parent = parent.master
                except:
                    parent = None
            return "#1a1a24"
        except:
            return "#1a1a24"
    def __init__(self, master, width=44, height=24, command=None, **kwargs):
        kwargs.pop('text', None)
        if 'fg_color' not in kwargs:
            kwargs['fg_color'] = self._get_parent_bg_color_static(master)
        super().__init__(master, width=width, height=height, **kwargs)
        for child in self.winfo_children():
            child.place_forget()
            child.pack_forget()
            child.grid_forget()
        self.width = width
        self.height = height
        self.command = command
        self.is_on = False
        self.current_progress = 0.0
        self.animating = False
        self.pack_propagate(False)
        self.grid_propagate(False)
        canvas_bg = self._get_parent_bg_color()
        if isinstance(canvas_bg, str) and " " in canvas_bg:
            canvas_bg = canvas_bg.split()[0]
        self.scale = 2
        self.canvas_width = width * self.scale
        self.canvas_height = height * self.scale
        self.canvas = Canvas(
            self,
            width=width,
            height=height,
            bg=canvas_bg,
            highlightthickness=0
        )
        self.canvas.place(x=0, y=0, width=width, height=height)
        self.off_color = "#2a2a38"
        self.on_color = "#ff4081"
        self.knob_color = "#ffffff"
        self.bg_color = canvas_bg
        self.knob_radius = (height // 2 - 3) * self.scale
        self.photo = None
        self.draw_switch(0.0)
        self.canvas.bind("<Button-1>", self.toggle)
        self.bind("<Button-1>", self.toggle)
    def draw_switch(self, progress=0.0):
        img = Image.new('RGBA', (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img, 'RGBA')
        current_color = self._interpolate_color(self.off_color, self.on_color, progress)
        padding = 2 * self.scale
        radius = (self.height // 2) * self.scale
        draw.rounded_rectangle(
            [padding, padding, self.canvas_width - padding, self.canvas_height - padding],
            radius=radius,
            fill=current_color
        )
        start_x = self.height // 2
        end_x = self.width - (self.height // 2)
        knob_x = (start_x + (end_x - start_x) * progress) * self.scale
        knob_y = (self.height // 2) * self.scale
        knob_bbox = [
            knob_x - self.knob_radius,
            knob_y - self.knob_radius,
            knob_x + self.knob_radius,
            knob_y + self.knob_radius
        ]
        draw.ellipse(knob_bbox, fill=self.knob_color)
        img_resized = img.resize((self.width, self.height), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img_resized)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.current_progress = progress
    def toggle(self, event=None):
        if self.animating:
            return
        self.is_on = not self.is_on
        self.animate()
        if self.command:
            self.command()
    def animate(self):
        self.animating = True
        target = 1.0 if self.is_on else 0.0
        start = self.current_progress
        steps = 20
        duration = 0.20
        start_time = time.time()
        for i in range(steps + 1):
            if not self.winfo_exists():
                break
            p = i / steps
            eased = 4 * p ** 3 if p < 0.5 else 1 - pow(-2 * p + 2, 3) / 2
            progress = start + (target - start) * eased
            self.draw_switch(progress)
            self.canvas.update()
            elapsed = time.time() - start_time
            expected = (i + 1) * (duration / steps)
            time.sleep(max(0, expected - elapsed))
        self.animating = False
    def _interpolate_color(self, color1, color2, progress):
        r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
        r = int(r1 + (r2 - r1) * progress)
        g = int(g1 + (g2 - g1) * progress)
        b = int(b1 + (b2 - b1) * progress)
        return f"#{r:02x}{g:02x}{b:02x}"
    def get(self):
        return 1 if self.is_on else 0
    def select(self):
        if not self.is_on:
            self.is_on = True
            try:
                self.draw_switch(1.0)
            except:
                pass
    def deselect(self):
        if self.is_on:
            self.is_on = False
            try:
                self.draw_switch(0.0)
            except:
                pass
class ModernCheckBox(ctk.CTkCheckBox):
    def __init__(self, master, **kwargs):
        default_kwargs = {
            "fg_color": COLORS["accent"],
            "border_color": COLORS["border"],
            "hover_color": COLORS["accent_light"],
            "hover": False,
            "text_color": COLORS["text"],
            "font": ("Segoe UI", 12),
            "border_width": 2,
            "corner_radius": 8,
        }
        default_kwargs.update(kwargs)
        super().__init__(master, **default_kwargs)
       
class MinecraftModApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._is_closing = False
        self._version_check_timer = None
        self.update_queue = queue.Queue()
        version_check = MinecraftVersionDetector.check_compatibility()
        if not version_check['supported']:
            self.show_version_error(version_check)
            self.start_version_monitoring()
            return
        self.minecraft_version = version_check['series_version']
        self.version_config = version_check['config']
        self.full_version = version_check['installed_version']
        self._initialize_main_app()
    def _start_keybind_focus_polling(self):
        self._keybind_poll_active = True
        self._keybind_focus_poll()

    def _stop_keybind_focus_polling(self):
        self._keybind_poll_active = False

    def _keybind_focus_poll(self):
        if not self._keybind_poll_active:
            return
        if not (hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists()):
            self._keybind_poll_active = False
            return
        try:
            import ctypes
            hwnd_foreground = ctypes.windll.user32.GetForegroundWindow()
            hwnd_main = ctypes.windll.user32.FindWindowW(None, f"Torio Client - Minecraft {self.minecraft_version}")
            if hwnd_foreground == hwnd_main:
                self.keybind_window.lift()
                self.keybind_window.focus_force()
        except Exception as e:
            print(f"Keybind focus poll error: {e}")
        self.after(150, self._keybind_focus_poll)

    def _initialize_main_app(self):
        if not hasattr(self, 'full_version') or self.full_version is None:
            version_check = MinecraftVersionDetector.check_compatibility()
            self.full_version = version_check['installed_version']
        try:
            self.iconbitmap(resource_path("icons/icon.ico"))
        except Exception as e:
            print(f"Failed to set window icon: {e}")
  
        self.title(f"Torio Client - Minecraft {self.minecraft_version}")
        self.geometry("600x480")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["background"])
  
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.config = ConfigManager("config.json")
        self.update_queue = queue.Queue()
        self.game_process = None
  
        self.antikb_controller = AntiKnockbackController()
        self.reach_controller = ReachController()
        self.hitbox_controller = HitboxController(version_config=self.version_config)
        self.zoom_controller = ZoomController()
        self.brightness_controller = BrightnessController()
        self.speed_controller = SpeedController(version_config=self.version_config)
        self.coordinates_controller = CoordinatesController()
        self.autoclicker_controller = AutoClickerController()
        self.sprint_controller = SprintController()
        self.autoclicker_controller.set_update_queue(self.update_queue)
        self.nohurtcam_controller = NoHurtCamController()
        self.truesight_controller = TrueSightController()
        self.timechanger_controller = TimeChangerController()
        self.fastitem_controller = FastItemController()
        self.systemtray_controller = SystemTrayController(self)
        self.jumpreset_controller = JumpResetController(
            version_config=self.version_config,
            full_version=self.full_version
        )
        self.triggerbot_controller = TriggerBotController()
        self.microaim_controller = MicroAimController()
        self.aimassist_controller = AimAssistController()
        self.blockbreak_detector = get_shared_block_detector()
  
        self.streamprotect_controller = StreamProtectController()
        self.streamprotect_controller.set_update_queue(self.update_queue)
  
        self.tab_labels = {}
        self.current_tab = "Player"
        self.tab_frames = {}
        self.widgets = {
            "Visual": {},
            "Combat": {},
            "Movement": {},
            "Misc": {}
        }
  
        self.create_loading_screen()
        self.create_main_widgets()
  
        self.after(100, self.start_initialization_thread)
        self.after(100, self.process_queue)
  
        self.check_process_timer = self.after(5000, self.check_process_alive)

    def show_version_error(self, version_check):
        try:
            self.iconbitmap(resource_path("icons/icon.ico"))
        except:
            pass
        self.title("Torio Client - Version Error")
        self.geometry("520x440")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["background"])

        error_frame = ModernFrame(self, fg_color=COLORS["surface"])
        error_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9, relheight=0.92)

        icon_canvas = Canvas(
            error_frame, width=72, height=66,
            bg=COLORS["surface"], highlightthickness=0
        )
        icon_canvas.pack(pady=(22, 4))
        icon_canvas.create_polygon(
            36, 5, 69, 63, 3, 63,
            fill="", outline="#ff5252", width=4
        )
        icon_canvas.create_rectangle(33, 19, 39, 44, fill="#ff5252", outline="")
        icon_canvas.create_oval(33, 49, 39, 55, fill="#ff5252", outline="")

        ModernLabel(
            error_frame,
            text="Unsupported Minecraft Version",
            font=("Segoe UI", 20, "bold"),
            text_color='#ff5252'
        ).pack(pady=(8, 6))

        if version_check['installed_version']:
            full_version = version_check['installed_version']
            match = re.match(r'(\d+\.\d+\.\d{1,3})', full_version)
            display_version = match.group(1) if match else full_version
            message = f"Installed: {display_version}\n\nThis version is not supported."
        else:
            message = (
                "Minecraft Bedrock Edition not found.\n\n"
                "Please install Minecraft from the Microsoft Store."
            )

        ModernLabel(
            error_frame, text=message,
            font=("Segoe UI", 12), text_color=COLORS["text"], justify="center"
        ).pack(pady=10)

        ModernLabel(
            error_frame, text="Supported Versions:",
            font=("Segoe UI", 12, "bold"), text_color=COLORS["accent"]
        ).pack(pady=(10, 4))

        versions_text = ", ".join(MinecraftVersionDetector.DISPLAY_SUPPORTED_VERSIONS)
        ModernLabel(
            error_frame, text=versions_text,
            font=("Segoe UI", 11), text_color=COLORS["text_secondary"],
            justify="center", wraplength=430
        ).pack(pady=6)

        self.protocol("WM_DELETE_WINDOW", self.safe_destroy)

    def start_version_monitoring(self):
        if self._is_closing:
            return
        def check_version():
            if self._is_closing:
                return
            version_check = MinecraftVersionDetector.check_compatibility()
            if version_check['supported']:
                self.update_queue.put(('version_compatible', version_check))
            else:
                self._version_check_timer = self.after(5000, check_version)
        self.after(100, check_version)

    def handle_version_compatible(self, version_check):
        if self._is_closing:
            return
        if self._version_check_timer:
            self.after_cancel(self._version_check_timer)
            self._version_check_timer = None

        self.minecraft_version = version_check['series_version']
        self.version_config = version_check['config']
        self.full_version = version_check['installed_version']
        for widget in self.winfo_children():
            widget.destroy()
        self._initialize_main_app()

    def safe_destroy(self):
        if self._is_closing:
            return
        self._is_closing = True
        try:
            if self._version_check_timer:
                self.after_cancel(self._version_check_timer)
                self._version_check_timer = None
            for after_id in self.tk.call('after', 'info'):
                try:
                    self.after_cancel(after_id)
                except:
                    pass
            self.quit()
            self.destroy()
        except Exception as e:
            print(f"Error during window destruction: {e}")
            import sys
            sys.exit(0)

    def open_keybind_settings(self):
        if hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists():
            self.keybind_window.lift()
            return
        self._block_input()
        def on_close_callback():
            self._stop_keybind_focus_polling()
            self._unblock_input()
            self.keybind_window = None
        keybind_window = KeybindWindow(
            self, self.config,
            update_callback=self.update_feature_titles,
            on_close_callback=on_close_callback
        )
        self.keybind_window = keybind_window
        if self.config.get_state("streamprotect"):
            keybind_window.attributes('-topmost', True)
        def on_close():
            self.streamprotect_controller.unregister_window("Keybind Settings")
            on_close_callback()
            keybind_window.destroy()
        keybind_window.protocol("WM_DELETE_WINDOW", on_close)
        if not self.config.get_state("streamprotect"):
            self._start_keybind_focus_polling()
        if self.streamprotect_controller.initialized:
            def register():
                if keybind_window.winfo_exists():
                    hwnd = ctypes.windll.user32.FindWindowW(None, "Keybind Settings")
                    if hwnd != 0:
                        self.streamprotect_controller.register_window_affinity_only("Keybind Settings", hwnd)
            self.after(100, register)

    def update_feature_titles(self):
        for feature_key in ["brightness", "zoom"]:
            if feature_key in self.widgets["Visual"]:
                widget = self.widgets["Visual"][feature_key]
                if "title" in widget and "keybind_key" in widget:
                    keybind = widget["keybind_key"]
                    if keybind:
                        key = self.config.get_keybind(keybind)
                        base_title = widget["title"].cget("text").split(" (")[0]
                        new_title = f"{base_title} ({key.upper()})" if key else base_title
                        widget["title"].configure(text=new_title)
        if "sprint" in self.widgets["Movement"]:
            widget = self.widgets["Movement"]["sprint"]
            if "title" in widget and "keybind_key" in widget:
                keybind = widget["keybind_key"]
                if keybind:
                    key = self.config.get_keybind(keybind)
                    base_title = widget["title"].cget("text").split(" (")[0]
                    new_title = f"{base_title} ({key.upper()})" if key else base_title
                    widget["title"].configure(text=new_title)
        if "autoclicker" in self.widgets["Combat"]:
            widget = self.widgets["Combat"]["autoclicker"]
            left_key = self.config.get_keybind("autoclicker_left") or "z"
            right_key = self.config.get_keybind("autoclicker_right") or "x"
            new_title = f"AutoClicker (L:{_ac_key_display(left_key)} R:{_ac_key_display(right_key)})"
            widget["title"].configure(text=new_title)
            if self.autoclicker_controller.is_active:
                self.autoclicker_controller.set_keybinds(left_key, right_key)
                widget["status"].configure(
                    text=f"Active (L:{_ac_key_display(left_key)} R:{_ac_key_display(right_key)})",
                    text_color=COLORS["success"]
                )

    def create_loading_screen(self):
        self.loading_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92, relheight=0.92)
        self.loading_label = ModernLabel(self.loading_frame, text="Searching for Minecraft.Windows.exe...", font=("Segoe UI", 18, "bold"), justify="center")
        self.loading_label.pack(pady=(80, 20), fill="x")
        self.status_label = ModernLabel(self.loading_frame, text="", text_color=COLORS["text_secondary"], font=("Segoe UI", 12), justify="center")
        self.status_label.pack(pady=(15, 0), fill="x")
        self.progress_container = ctk.CTkFrame(self.loading_frame, fg_color="transparent")
        self.progress_container.pack(pady=(30, 10), padx=40, fill="x")
        self.progress_label = ModernLabel(self.progress_container, text="Initializing modules...", text_color=COLORS["text_secondary"], font=("Segoe UI", 11), justify="center")
        self.progress_label.pack(pady=(0, 5), fill="x")
        self.module_progress = ctk.CTkProgressBar(self.progress_container, orientation="horizontal", mode="determinate", width=240, height=4, fg_color=COLORS["border"], progress_color=COLORS["success"], corner_radius=2)
        self.module_progress.pack(fill="x", pady=(0, 5))
        self.module_progress.set(0)
        self.percentage_label = ModernLabel(self.progress_container, text="0%", text_color=COLORS["accent"], font=("Segoe UI", 10, "bold"), justify="center")
        self.percentage_label.pack(pady=5)
        self.progress_container.pack_forget()
        self.reconnect_button = ModernButton(self.loading_frame, text="Reconnect to Minecraft", command=self.start_initialization_thread)
        self.reconnect_button.pack_forget()

    def start_initialization_thread(self):
        version_check = MinecraftVersionDetector.check_compatibility()
        if not version_check['supported']:
            self.show_reconnect_screen(
                f"Incompatible version detected: {version_check['installed_version'] or 'Unknown'}\n"
                f"Please install a supported version."
            )
            return
        if version_check['series_version'] != self.minecraft_version:
            print(f"Version changed: {self.minecraft_version} -> {version_check['series_version']}")
            old_version = self.minecraft_version
            self.minecraft_version = version_check['series_version']
            self.version_config = version_check['config']
            self.full_version = version_check['installed_version']
            self.title(f"Torio Client - Minecraft {self.minecraft_version}")
            if hasattr(self, 'hitbox_controller'):
                self.hitbox_controller.set_version_config(self.version_config)
            if hasattr(self, 'speed_controller'):
                self.speed_controller.set_version_config(self.version_config)
            if hasattr(self, 'main_container') and self.main_container.winfo_exists():
                if old_version == "1.21.13" and hasattr(self, 'nohurtcam_controller'):
                    if self.nohurtcam_controller.initialized:
                        self.nohurtcam_controller.reset_to_default(is_app_closing=True)
                self.nohurtcam_controller = NoHurtCamController()
                self._rebuild_ui_for_version_change()
        self.show_loading_screen("Searching for Minecraft.Windows.exe...", COLORS["accent"])
        self.loading_thread = threading.Thread(target=self._initialize_backend, daemon=True)
        self.loading_thread.start()

    def _rebuild_ui_for_version_change(self):
        if "Visual" in self.widgets:
            if "nohurtcam" in self.widgets["Visual"]:
                self.widgets["Visual"]["nohurtcam"]["card"].destroy()
                del self.widgets["Visual"]["nohurtcam"]
        if "Movement" in self.widgets:
            if "jumpreset" in self.widgets["Movement"]:
                self.widgets["Movement"]["jumpreset"]["card"].destroy()
                del self.widgets["Movement"]["jumpreset"]
        self.nohurtcam_controller = NoHurtCamController()
        self.jumpreset_controller = JumpResetController(version_config=self.version_config, full_version=self.full_version)
        self.jumpreset_controller.set_update_queue(self.update_queue)
        if "Visual" in self.tab_frames:
            visual_frame = self.tab_frames["Visual"]
            for widget in visual_frame.winfo_children():
                widget.destroy()
            self.create_visual_tab(visual_frame)
        if "Movement" in self.tab_frames:
            movement_frame = self.tab_frames["Movement"]
            for widget in movement_frame.winfo_children():
                widget.destroy()
            self.create_movement_tab(movement_frame)
        if self.current_tab == "Visual":
            self.switch_tab("Visual")
        elif self.current_tab == "Movement":
            self.switch_tab("Movement")

    def _initialize_backend(self):
        try:
            pm = pymem.Pymem("Minecraft.Windows.exe")
            self.game_process = pm

            def _check_process_alive():
                try:
                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                    h = ctypes.windll.kernel32.OpenProcess(
                        PROCESS_QUERY_LIMITED_INFORMATION, False, pm.process_id
                    )
                    if not h:
                        return False
                    code = ctypes.c_ulong(0)
                    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                    ctypes.windll.kernel32.CloseHandle(h)
                    return code.value == 259
                except Exception:
                    return False

            from core.aim_detector import reinitialize_shared_detector
            reinitialize_shared_detector(pm)
            from core.menu_monitor import reinitialize_shared_menu_monitor
            from core.menu_monitor import get_shared_menu_monitor
            reinitialize_shared_menu_monitor(pm)
            reinitialize_shared_window_monitor()
            reinitialize_shared_block_detector(pm)
            reinitialize_shared_world_monitor(pm)
            world_monitor = get_shared_world_monitor()
            world_monitor.start()
            block_detector = get_shared_block_detector()
            block_detector.start()
            self.update_queue.put(('show_progress', True))

            memory_modules = [
                ("AntiKnockback", self.antikb_controller),
                ("Reach", self.reach_controller),
                ("Hitbox", self.hitbox_controller),
                ("Zoom", self.zoom_controller),
                ("Brightness", self.brightness_controller),
                ("Speed", self.speed_controller),
                ("Coordinates", self.coordinates_controller),
                ("Sprint", self.sprint_controller),
                ("TrueSight", self.truesight_controller),
                ("TimeChanger", self.timechanger_controller),
                ("FastItem", self.fastitem_controller),
                ("TriggerBot", self.triggerbot_controller),
                ("MicroAim", self.microaim_controller),
                ("AimAssist", self.aimassist_controller),
            ]
            if self.minecraft_version == "1.21.13":
                memory_modules.append(("NoHurtCam", self.nohurtcam_controller))
            if MinecraftVersionDetector.is_jumpreset_supported(self.full_version):
                memory_modules.append(("JumpReset", self.jumpreset_controller))

            non_memory_modules = [
                ("AutoClicker", self.autoclicker_controller),
                ("StreamProtect", self.streamprotect_controller),
                ("SystemTray", self.systemtray_controller),
            ]

            all_modules = memory_modules + non_memory_modules
            total_modules = len(all_modules)
            initialized_count = 0
            init_results = {}

            for module_name, controller in all_modules:
                progress = initialized_count / total_modules
                self.update_queue.put(('progress_update', (progress, f"Initializing {module_name}...", initialized_count, total_modules)))

                try:
                    if (module_name, controller) in memory_modules:
                        controller.set_pymem_process(pm)
                        controller.set_update_queue(self.update_queue)
                        if module_name == "AntiKnockback":
                            xz_mult = self.config.get_setting("antiknockback", "xz", 0.8)
                            y_mult = self.config.get_setting("antiknockback", "y", 0.8)
                            controller.kb_xz_mult = xz_mult
                            controller.kb_y_mult = y_mult
                        elif module_name == "Reach":
                            reach_value = self.config.get_setting("reach", "reach", 3.0)
                            controller.current_reach = reach_value
                        elif module_name == "Hitbox":
                            controller.set_version_config(self.version_config)
                            hitbox_value = self.config.get_setting("hitbox", "hitbox", 1.0)
                            controller.current_hitbox = hitbox_value
                        elif module_name == "Speed":
                            controller.set_version_config(self.version_config)
                        init_success = controller.initialize()
                        init_results[module_name.lower().replace(" ", "")] = init_success
                    else:
                        if hasattr(controller, 'set_update_queue'):
                            controller.set_update_queue(self.update_queue)
                        if hasattr(controller, 'initialize'):
                            init_success = controller.initialize()
                            init_results[module_name.lower().replace(" ", "")] = init_success
                        else:
                            init_results[module_name.lower().replace(" ", "")] = True
                        time.sleep(0.1)
                except Exception as e:
                    init_results[module_name.lower().replace(" ", "")] = False
                    time.sleep(0.1)

                initialized_count += 1
                time.sleep(0.05)

                if not _check_process_alive():
                    self.game_process = None
                    self.update_queue.put((
                        'init_complete', False,
                        "Minecraft was closed during initialization."
                    ))
                    return

            self.update_queue.put(('progress_update', (1.0, "Initialization complete!", total_modules, total_modules)))
            time.sleep(0.3)

            if not _check_process_alive():
                self.game_process = None
                self.update_queue.put((
                    'init_complete', False,
                    "Minecraft was closed during initialization."
                ))
                return

            if any(init_results.values()):
                self.update_queue.put(('init_complete', True))
                if self.config.get_state("antiknockback") and init_results.get("antiknockback"):
                    self.antikb_controller.start()
                if self.config.get_state("reach") and init_results.get("reach"):
                    self.reach_controller.start()
                if self.config.get_state("hitbox") and init_results.get("hitbox"):
                    self.hitbox_controller.start()
                if self.config.get_state("zoom") and init_results.get("zoom"):
                    zoom_key = self.config.get_keybind("zoom") or "c"
                    self.zoom_controller.start(zoom_key)
                if self.config.get_state("brightness") and init_results.get("brightness"):
                    self.brightness_controller.start()
                if self.config.get_state("speed") and init_results.get("speed"):
                    speed_value = self.config.get_setting("speed", "speed", 0.5)
                    self.speed_controller.set_speed_value(speed_value)
                    self.speed_controller.start()
                if self.config.get_state("coordinates") and init_results.get("coordinates"):
                    self.coordinates_controller.start()
                if self.config.get_state("sprint") and init_results.get("sprint"):
                    sprint_key = self.config.get_keybind("sprint") or "p"
                    self.sprint_controller.current_key = sprint_key
                    self.sprint_controller.start()
                if self.config.get_state("truesight") and init_results.get("truesight"):
                    self.truesight_controller.start()
                if self.config.get_state("timechanger") and init_results.get("timechanger"):
                    time_value = self.config.get_setting("timechanger", "time", 1000)
                    self.timechanger_controller.set_time(time_value)
                    self.timechanger_controller.start()
                if self.config.get_state("fastitem") and init_results.get("fastitem"):
                    self.fastitem_controller.start()
                if MinecraftVersionDetector.is_jumpreset_supported(self.full_version):
                    if self.config.get_state("jumpreset") and init_results.get("jumpreset"):
                        jump_key = self.config.get_keybind("jump") or "space"
                        jump_timing = self.config.get_setting("jumpreset", "timing", 0.54)
                        self.jumpreset_controller.set_jump_key(jump_key)
                        self.jumpreset_controller.set_jump_timing(jump_timing)
                        self.jumpreset_controller.start()
                if self.minecraft_version == "1.21.13":
                    if self.config.get_state("nohurtcam") and init_results.get("nohurtcam"):
                        self.nohurtcam_controller.start()
                if self.config.get_state("autoclicker") and init_results.get("autoclicker"):
                    if self.autoclicker_controller.is_active:
                        self.autoclicker_controller.stop()
                    self.autoclicker_controller.reset_to_default()

                    left_cps      = self.config.get_setting("autoclicker", "left_cps", 10.0)
                    right_cps     = self.config.get_setting("autoclicker", "right_cps", 10.0)
                    left_enabled  = self.config.get_setting("autoclicker", "left_enabled", True)
                    right_enabled = self.config.get_setting("autoclicker", "right_enabled", True)
                    left_key      = self.config.get_keybind("autoclicker_left") or "z"
                    right_key     = self.config.get_keybind("autoclicker_right") or "x"
                    jitter_on     = self.config.get_setting("autoclicker", "jitter_enabled", False)
                    jitter_str    = self.config.get_setting("autoclicker", "jitter_strength", 2.0)
                    self.autoclicker_controller.set_cps(left_cps, right_cps)
                    self.autoclicker_controller.set_click_enabled(left_enabled, right_enabled)
                    self.autoclicker_controller.set_keybinds(left_key, right_key)
                    self.autoclicker_controller.set_jitter(jitter_on, jitter_str)
                    self.triggerbot_controller.set_jitter(jitter_on, jitter_str)
                    self.autoclicker_controller.start()
                if self.config.get_state("triggerbot") and init_results.get("triggerbot"):
                    tb_mode = self.config.get_setting("triggerbot", "mode", "first_hit")
                    tb_cps  = self.config.get_setting("triggerbot", "auto_cps", 12.0)
                    tb_atk  = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
                    if tb_atk in ("left", "right"):
                        tb_atk = "mouse_" + tb_atk
                    self.triggerbot_controller.set_mode(tb_mode)
                    self.triggerbot_controller.set_auto_cps(tb_cps)
                    self.triggerbot_controller.set_attack_button(tb_atk)
                    self.triggerbot_controller.start()
                if self.config.get_state("microaim") and init_results.get("microaim"):
                    pulse = self.config.get_setting("microaim", "pulse_duration", 0.1)
                    self.microaim_controller.set_pulse_duration(pulse)
                    self.microaim_controller.start()

                if self.config.get_state("aimassist") and init_results.get("aimassist"):
                    sens = self.config.get_setting("aimassist", "sensitivity", 0.50)
                    max_dist = self.config.get_setting("aimassist", "max_dist", 6.0)
                    aim_only_on_ac = self.config.get_setting("aimassist", "aim_only_on_autoclicker", False)
                    self.aimassist_controller.set_sensitivity(sens)
                    self.aimassist_controller.set_max_dist(max_dist)
                    self.aimassist_controller.set_autoclicker_reference(self.autoclicker_controller)
                    self.aimassist_controller.set_aim_only_on_autoclicker(aim_only_on_ac)
                    self.aimassist_controller.start()
            else:
                self.update_queue.put(('init_complete', False))

        except pymem.exception.ProcessNotFound:
            self.game_process = None
            self.update_queue.put(('init_complete', False))
        except Exception as e:
            print(f"Initialization Error: {e}")
            import traceback
            traceback.print_exc()
            self.update_queue.put(('init_complete', False, f"Error: {e.__class__.__name__}"))

    def show_loading_screen(self, message, color):
        if hasattr(self, 'main_container') and self.main_container.winfo_exists():
            self.main_container.pack_forget()
        self.loading_frame.tkraise()
        self.loading_label.configure(text=message, text_color=color)
        self.status_label.configure(text="", text_color=COLORS["text_secondary"])
        self.reconnect_button.pack_forget()
        self.progress_container.pack_forget()

    def show_main_gui(self):
        self.loading_frame.lower()
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.apply_config_to_gui()
        main_hwnd = ctypes.windll.user32.FindWindowW(None, f"Torio Client - Minecraft {self.minecraft_version}")
        if main_hwnd != 0:
            self.streamprotect_controller.register_window("Torio Client", main_hwnd)
            self.streamprotect_controller.initialize()
            if self.config.get_state("streamprotect"):
                self.streamprotect_controller.start()

    def show_reconnect_screen(self, message):
        if hasattr(self, 'main_container') and self.main_container.winfo_exists():
            self.main_container.pack_forget()
        self.loading_frame.tkraise()
        self.loading_label.configure(text="Connection Failed", text_color='#ff5252')
        self.status_label.configure(text=message, text_color=COLORS["text_secondary"])
        self.reconnect_button.pack(pady=20)
        self.progress_container.pack_forget()

    def check_process_alive(self):
        if self.game_process and (self.antikb_controller.initialized or self.reach_controller.initialized or
                                   self.hitbox_controller.initialized or self.zoom_controller.initialized or
                                   self.brightness_controller.initialized or self.speed_controller.initialized or
                                   self.coordinates_controller.initialized or
                                   (self.minecraft_version == "1.21.13" and self.nohurtcam_controller.initialized)):
            antikb_valid       = self.antikb_controller.validate_process() if self.antikb_controller.initialized else True
            reach_valid        = self.reach_controller.validate_process() if self.reach_controller.initialized else True
            hitbox_valid       = self.hitbox_controller.validate_process() if self.hitbox_controller.initialized else True
            zoom_valid         = self.zoom_controller.validate_process() if self.zoom_controller.initialized else True
            brightness_valid   = self.brightness_controller.validate_process() if self.brightness_controller.initialized else True
            speed_valid        = self.speed_controller.validate_process() if self.speed_controller.initialized else True
            coordinates_valid  = self.coordinates_controller.validate_process() if self.coordinates_controller.initialized else True
            sprint_valid       = self.sprint_controller.validate_process() if self.sprint_controller.initialized else True
            truesight_valid    = self.truesight_controller.validate_process() if self.truesight_controller.initialized else True
            timechanger_valid  = self.timechanger_controller.validate_process() if self.timechanger_controller.initialized else True
            fastitem_valid     = self.fastitem_controller.validate_process() if self.fastitem_controller.initialized else True
            triggerbot_valid   = self.triggerbot_controller.validate_process() if self.triggerbot_controller.initialized else True
            microaim_valid     = self.microaim_controller.validate_process() if self.microaim_controller.initialized else True
            aimassist_valid = self.aimassist_controller.validate_process() if self.aimassist_controller.initialized else True
            if self.version_config.get('jumpreset_supported', False):
                jumpreset_valid = self.jumpreset_controller.validate_process() if self.jumpreset_controller.initialized else True
            else:
                jumpreset_valid = True
            if self.minecraft_version == "1.21.13":
                nohurtcam_valid = self.nohurtcam_controller.validate_process() if self.nohurtcam_controller.initialized else True
            else:
                nohurtcam_valid = True
            if not all([antikb_valid, reach_valid, hitbox_valid, zoom_valid, brightness_valid, speed_valid,
                        coordinates_valid, sprint_valid, nohurtcam_valid, truesight_valid, timechanger_valid,
                        fastitem_valid, jumpreset_valid, triggerbot_valid, microaim_valid, aimassist_valid]):
                print("Process died. Resetting state.")
                self.antikb_controller.reset_to_default(is_app_closing=True)
                self.reach_controller.reset_to_default(is_app_closing=True)
                self.hitbox_controller.reset_to_default(is_app_closing=True)
                self.zoom_controller.reset_to_default(is_app_closing=True)
                self.brightness_controller.reset_to_default(is_app_closing=True)
                self.speed_controller.reset_to_default(is_app_closing=True)
                self.coordinates_controller.reset_to_default(is_app_closing=True)
                self.sprint_controller.reset_to_default(is_app_closing=True)
                self.truesight_controller.reset_to_default(is_app_closing=True)
                self.timechanger_controller.reset_to_default(is_app_closing=True)
                self.fastitem_controller.reset_to_default(is_app_closing=True)
                self.triggerbot_controller.reset_to_default(is_app_closing=True)
                self.microaim_controller.reset_to_default(is_app_closing=True)
                self.aimassist_controller.reset_to_default(is_app_closing=True)
                self.autoclicker_controller.stop(is_app_closing=True)
                self.autoclicker_controller.reset_to_default()
                from core.menu_monitor import reset_shared_menu_monitor
                reset_shared_menu_monitor()
                reset_click_priority()
                reset_shared_window_monitor()
                reset_shared_block_detector()
                reset_shared_world_monitor()
                if self.version_config.get('jumpreset_supported', False):
                    self.jumpreset_controller.reset_to_default(is_app_closing=True)
                if self.minecraft_version == "1.21.13":
                    self.nohurtcam_controller.reset_to_default(is_app_closing=True)
                self.game_process = None
                self.show_reconnect_screen("Minecraft process has closed. Attempt reconnect.")
        self.check_process_timer = self.after(5000, self.check_process_alive)

    def process_queue(self):
        try:
            while True:
                item = self.update_queue.get_nowait()
                if item is None:
                    continue
                type = item[0]
                if type == 'version_compatible':
                    self.handle_version_compatible(item[1])
                    return
                elif type == 'show_progress':
                    self.progress_container.pack(pady=(30, 10), padx=40, fill="x")
                    self.module_progress.set(0)
                    self.percentage_label.configure(text="0%")
                elif type == 'progress_update':
                    progress, message, current, total = item[1]
                    self.module_progress.set(progress)
                    percentage = int(progress * 100)
                    self.percentage_label.configure(text=f"{percentage}%")
                    self.progress_label.configure(text=f"{message} ({current}/{total})")
                elif type == 'raise_keybind_window':
                    if hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists():
                        self.keybind_window.lift()
                        self.keybind_window.focus_force()
                elif type == 'init_complete':
                    success = item[1]
                    if success:
                        self.show_main_gui()
                    else:
                        error_msg = item[2] if len(item) > 2 else "Process not found or initialization error."
                        self.show_reconnect_screen(error_msg)
                elif type == 'status_text':
                    self.status_label.configure(text=item[1])
                elif type == 'status_update':
                    feature_name, message, color = item[1]
                    widget_location = None
                    if feature_name == "antiknockback":
                        widget_location = ("Movement", feature_name)
                    elif feature_name in ["reach", "hitbox", "autoclicker", "triggerbot", "microaim", "aimassist"]:
                        widget_location = ("Combat", feature_name)
                    elif feature_name in ["zoom", "brightness", "coordinates", "nohurtcam", "truesight", "timechanger"]:
                        widget_location = ("Visual", feature_name)
                    elif feature_name in ["speed", "sprint", "jumpreset"]:
                        widget_location = ("Movement", feature_name)
                    elif feature_name == "fastitem":
                        widget_location = ("Player", feature_name)
                    elif feature_name in ["streamprotect", "systemtray"]:
                        widget_location = ("Misc", feature_name)
                    if widget_location:
                        tab, feat = widget_location
                        if tab in self.widgets and feat in self.widgets[tab]:
                            widget = self.widgets[tab][feat]
                            widget["status"].configure(text=message, text_color=color)
                            if message == "Inactive" or message.startswith("Inactive ("):
                                if not self.config.get_state(feature_name):
                                    widget["switch"].deselect()
                            elif message.startswith("Active"):
                                if self.config.get_state(feature_name):
                                    widget["switch"].select()
        except queue.Empty:
            pass
        finally:
            self.after(50, self.process_queue)

    def create_main_widgets(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        self.main_container.pack_forget()
        sidebar_frame = ModernFrame(self.main_container, width=170, fg_color=COLORS["surface"])
        sidebar_frame.pack(side="left", fill="y", pady=0, padx=(0, 10))
        sidebar_frame.pack_propagate(False)
        sidebar_frame.grid_propagate(False)
        sidebar_frame.grid_columnconfigure(0, weight=1)
        self.after(10, lambda: sidebar_frame.configure(width=170))
        self.content_frame = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(side="right", fill="both", expand=True)
        title_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        title_container.pack(pady=(5, 10), fill="x", anchor="w")
        LOGO_FONT = load_custom_font("fonts/PoetsenOne-Regular.ttf", "PoetsenOne")
        title_row = ctk.CTkFrame(title_container, fg_color="transparent")
        title_row.pack(anchor="w", pady=(0, 2))
        try:
            _title_icon = ctk.CTkImage(light_image=Image.open(resource_path("icons/icon.png")), size=(49, 49))
            icon_lbl = ctk.CTkLabel(title_row, image=_title_icon, text="")
            icon_lbl.pack(side="right", padx=(0, 6))
            icon_lbl._title_icon = _title_icon
        except Exception as e:
            print(f"タイトルアイコン読み込み失敗: {e}")
        ctk.CTkLabel(title_row, text="Torio Client", font=(LOGO_FONT, 36, "bold"), text_color=COLORS["accent"], anchor="w").pack(side="left")
        ctk.CTkLabel(title_container, text="Minecraft Ghost Client Made by Ducky:)", font=("Segoe UI", 12), text_color=COLORS["text_secondary"], anchor="w").pack(anchor="w")
        icon_size = (27, 27)
        try:
            player_icon   = ctk.CTkImage(light_image=Image.open(resource_path("icons/player.png")), size=icon_size)
            visual_icon   = ctk.CTkImage(light_image=Image.open(resource_path("icons/visual.png")), size=icon_size)
            combat_icon   = ctk.CTkImage(light_image=Image.open(resource_path("icons/combat.png")), size=icon_size)
            movement_icon = ctk.CTkImage(light_image=Image.open(resource_path("icons/movement.png")), size=icon_size)
            misc_icon     = ctk.CTkImage(light_image=Image.open(resource_path("icons/misc.png")), size=icon_size)
        except:
            player_icon = visual_icon = combat_icon = movement_icon = misc_icon = None
        tabs = ["Player", "Visual", "Combat", "Movement", "Misc"]
        icons = {"Player": player_icon, "Visual": visual_icon, "Combat": combat_icon, "Movement": movement_icon, "Misc": misc_icon}
        for i in range(len(tabs)):
            sidebar_frame.grid_rowconfigure(i, weight=1)
        for i, tab in enumerate(tabs):
            label = ctk.CTkLabel(sidebar_frame, text=tab, font=("Segoe UI", 17, "bold"), text_color=COLORS["text_secondary"],
                                 image=icons.get(tab), compound="left", anchor="w", padx=8, height=60, corner_radius=8)
            label.grid(row=i, column=0, sticky="nsew", padx=8, pady=5)
            label.bind("<Button-1>", lambda e, t=tab: self.switch_tab(t))
            self.tab_labels[tab] = label
        self.tab_content_frame = ModernFrame(self.content_frame, fg_color=COLORS["surface"])
        self.tab_content_frame.pack(padx=0, pady=8, fill="both", expand=True)
        for tab in tabs:
            frame = ctk.CTkFrame(self.tab_content_frame, fg_color=COLORS["surface"])
            self.tab_frames[tab] = frame
            if tab == "Player":
                self.create_player_tab(frame)
            elif tab == "Visual":
                self.create_visual_tab(frame)
            elif tab == "Combat":
                self.create_combat_tab(frame)
            elif tab == "Movement":
                self.create_movement_tab(frame)
            elif tab == "Misc":
                self.create_misc_tab(frame)
        self.switch_tab("Player")
        self._setup_scroll_binding()
        controls = ModernFrame(self.content_frame)
        controls.pack(pady=(10, 5), fill="x")
        ModernButton(controls, text="Customize Keybinds", height=42, font=("Segoe UI", 13, "bold"), command=self.open_keybind_settings).pack(pady=16, padx=16, fill="x")

    def create_feature_card(self, parent, title, feature_name, keybind_key=None):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(pady=12, padx=16, fill="x")
        header.grid_columnconfigure(1, weight=1)
        key = self.config.get_keybind(keybind_key) if keybind_key else None
        title_text = title if not key else f"{title} ({key.upper()})"
        title_lbl = ModernLabel(header, text=title_text, font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature(feature_name, status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        return {"card": card, "status": status_lbl, "switch": switch, "title": title_lbl, "keybind_key": keybind_key}

    def create_slider_card(self, parent, title, feature_name, setting_key, minv, maxv, default, steps=100, keybind_key=None):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        key = self.config.get_keybind(keybind_key) if keybind_key else None
        title_text = title if not key else f"{title} ({key.upper()})"
        title_lbl = ModernLabel(header, text=title_text, font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature(feature_name, status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(5, 12))
        val_lbl = ModernLabel(slider_frame, text=f"Value: {default:.2f}", font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        val_lbl.pack(anchor="w", pady=(0, 8))
        def slider_command(v, feature=feature_name, key=setting_key, label=val_lbl):
            val = float(v)
            label.configure(text=f"Value: {val:.2f}")
            self.config.set_setting(feature, key, val)
            if feature == "reach":
                if self.reach_controller:
                    self.reach_controller.set_reach_value(val)
            elif feature == "hitbox":
                if self.hitbox_controller:
                    self.hitbox_controller.set_hitbox_value(val)
            elif feature == "speed":
                if self.speed_controller:
                    self.speed_controller.set_speed_value(val)
        slider = ModernSlider(slider_frame, from_=minv, to=maxv, number_of_steps=steps, width=380, command=slider_command)
        slider.pack(fill="x")
        rng = ctk.CTkFrame(slider_frame, fg_color="transparent")
        rng.pack(fill="x", pady=(4, 0))
        ModernLabel(rng, text=str(minv), font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(rng, text=str(maxv), font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="right")
        return {"card": card, "status": status_lbl, "switch": switch, "slider": slider, "value_label": val_lbl, "title": title_lbl, "keybind_key": keybind_key}

    def create_triggerbot_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)

        title_lbl = ModernLabel(header, text="TriggerBot",
                                 font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")

        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11),
                                  text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")

        switch = ModernSwitch(
            header, text="",
            command=lambda: self.toggle_feature("triggerbot", status_lbl, switch)
        )
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))

        mode_frame = ctk.CTkFrame(card, fg_color="transparent")
        mode_frame.pack(fill="x", padx=16, pady=(0, 6))

        saved_mode = self.config.get_setting("triggerbot", "mode", "first_hit")
        mode_var   = ctk.StringVar(value=saved_mode)

        def on_mode_change():
            new_mode = mode_var.get()
            self.config.set_setting("triggerbot", "mode", new_mode)
            if self.triggerbot_controller.is_active:
                self.triggerbot_controller.set_mode(new_mode)
            if new_mode == "auto_click":
                cps_frame.pack(fill="x", padx=16, pady=(0, 6))
            else:
                cps_frame.pack_forget()

        ModernCheckBox(
            mode_frame, text="First Hit Only",
            variable=mode_var, onvalue="first_hit", offvalue="auto_click",
            command=on_mode_change
        ).pack(side="left", padx=(0, 16))

        ModernCheckBox(
            mode_frame, text="AutoClick",
            variable=mode_var, onvalue="auto_click", offvalue="first_hit",
            command=on_mode_change
        ).pack(side="left")

        cps_frame   = ctk.CTkFrame(card, fg_color="transparent")
        saved_cps   = min(self.config.get_setting("triggerbot", "auto_cps", 12.0), 20.0)
        cps_val_lbl = ModernLabel(cps_frame, text=f"AutoClick CPS: {saved_cps:.1f}",
                                   font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        cps_val_lbl.pack(anchor="w", pady=(0, 8))

        def on_cps_change(v):
            val = float(v)
            cps_val_lbl.configure(text=f"AutoClick CPS: {val:.1f}")
            self.config.set_setting("triggerbot", "auto_cps", val)
            if self.triggerbot_controller.is_active:
                self.triggerbot_controller.set_auto_cps(val)

        cps_slider = ModernSlider(cps_frame, from_=1.0, to=20.0, number_of_steps=190,
                                   width=380, command=on_cps_change)
        cps_slider.set(saved_cps)
        cps_slider.pack(fill="x")

        cps_rng = ctk.CTkFrame(cps_frame, fg_color="transparent")
        cps_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(cps_rng, text="1",  font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(cps_rng, text="20", font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")

        if saved_mode == "auto_click":
            cps_frame.pack(fill="x", padx=16, pady=(0, 6))

        atk_frame = ctk.CTkFrame(card, fg_color="transparent")
        atk_frame.pack(fill="x", padx=16, pady=(4, 12))
        atk_frame.grid_columnconfigure(1, weight=1)

        ModernLabel(atk_frame, text="Attack Button:", font=("Segoe UI", 11),
                    text_color=COLORS["text_secondary"], anchor="w").grid(
            row=0, column=0, sticky="w")

        def _attack_to_display(val: str) -> str:
            if val == "mouse_left":  return "MOUSE L"
            if val == "mouse_right": return "MOUSE R"
            if val == "left":        return "MOUSE L"
            if val == "right":       return "MOUSE R"
            return val.upper()

        saved_atk = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
        if saved_atk == "left":  saved_atk = "mouse_left"
        if saved_atk == "right": saved_atk = "mouse_right"

        atk_entry = ctk.CTkEntry(
            atk_frame, width=130, justify="center", corner_radius=6,
            border_width=2, border_color=COLORS["border"],
            fg_color=COLORS["card"], text_color=COLORS["text"],
            font=("Segoe UI", 12), height=32
        )
        atk_entry.grid(row=0, column=1, sticky="e")
        atk_entry.insert(0, _attack_to_display(saved_atk))
        atk_entry.configure(state="readonly")

        _state = {"waiting": False, "bind_id_b1": None, "bind_id_b3": None}

        def _set_entry(text, border=COLORS["border"], color=COLORS["text"]):
            if atk_entry.winfo_exists():
                atk_entry.configure(state="normal", border_color=border, text_color=color)
                atk_entry.delete(0, "end")
                atk_entry.insert(0, text)
                atk_entry.configure(state="readonly")

        def _unbind_mouse():
            try:
                if _state["bind_id_b1"]:
                    self.unbind("<Button-1>", _state["bind_id_b1"])
                    _state["bind_id_b1"] = None
            except Exception:
                pass
            try:
                if _state["bind_id_b3"]:
                    self.unbind("<Button-3>", _state["bind_id_b3"])
                    _state["bind_id_b3"] = None
            except Exception:
                pass

        def _finish():
            _state["waiting"] = False
            _unbind_mouse()
            cur = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
            _set_entry(_attack_to_display(cur), COLORS["border"], COLORS["text"])
            try:
                if atk_entry.winfo_exists():
                    atk_entry.bind("<Button-1>", on_entry_click)
            except Exception:
                pass
            self.focus()

        def _restore():
            _state["waiting"] = False
            _unbind_mouse()
            cur = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
            _set_entry(_attack_to_display(cur), COLORS["border"], COLORS["text"])
            try:
                if atk_entry.winfo_exists():
                    atk_entry.bind("<Button-1>", on_entry_click)
            except Exception:
                pass
            self.focus()

        def _apply(new_val: str):
            _state["waiting"] = False
            _unbind_mouse()
            self.config.set_setting("triggerbot", "attack_button", new_val)
            if self.triggerbot_controller.is_active:
                self.triggerbot_controller.set_attack_button(new_val)
            _set_entry(_attack_to_display(new_val), COLORS["success"], COLORS["success"])
            self.after(700, _finish)

        def _register_mouse_binds():
            if not _state["waiting"]:
                return

            def on_window_left(event):
                if not _state["waiting"]:
                    return
                if event.widget is atk_entry or str(event.widget) == str(atk_entry):
                    return
                _apply("mouse_left")
                return "break"

            def on_window_right(event):
                if not _state["waiting"]:
                    return
                _apply("mouse_right")
                return "break"

            _state["bind_id_b1"] = self.bind("<Button-1>", on_window_left, add="+")
            _state["bind_id_b3"] = self.bind("<Button-3>", on_window_right, add="+")

        def on_entry_click(event):
            if _state["waiting"]:
                return "break"
            _state["waiting"] = True
            _set_entry("Press key / click...", COLORS["accent_light"], COLORS["accent_light"])
            atk_entry.focus_set()
            atk_entry.unbind("<Button-1>")
            self.after(200, _register_mouse_binds)
            return "break"

        def on_key_press(event):
            if not _state["waiting"]:
                return
            key = event.keysym.lower()
            ignore = ["shift", "shift_l", "shift_r",
                    "control", "control_l", "control_r",
                    "alt", "alt_l", "alt_r",
                    "caps_lock", "tab", "escape",
                    "super_l", "super_r", "win_l", "win_r"]
            if key in ignore:
                cur = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
                _state["waiting"] = False
                _unbind_mouse()
                _set_entry(_attack_to_display(cur), "#ff5252", "#ff5252")
                self.after(1200, _finish)
                return "break"
            _apply(key)
            return "break"

        def on_focus_out(event):
            if _state["waiting"]:
                self.after(150, lambda: _restore() if _state["waiting"] else None)

        atk_entry.bind("<Button-1>", on_entry_click)
        atk_entry.bind("<KeyPress>",  on_key_press)
        atk_entry.bind("<FocusOut>",  on_focus_out)

        return {
            "card":        card,
            "status":      status_lbl,
            "switch":      switch,
            "title":       title_lbl,
            "mode_var":    mode_var,
            "atk_entry":   atk_entry,
            "cps_slider":  cps_slider,
            "cps_val_lbl": cps_val_lbl,
            "cps_frame":   cps_frame,
        }

    def create_microaim_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        title_lbl = ModernLabel(header, text="MicroAim", font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature("microaim", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))

        slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(0, 12))

        saved_pulse = self.config.get_setting("microaim", "pulse_duration", 0.1)
        saved_ms    = int(round(saved_pulse * 1000))
        pulse_lbl   = ModernLabel(slider_frame, text=f"Sensitivity Reduction: {saved_ms}ms",
                                   font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        pulse_lbl.pack(anchor="w", pady=(0, 8))

        def on_pulse_change(v):
            ms  = int(float(v))
            sec = ms / 1000.0
            pulse_lbl.configure(text=f"Sensitivity Reduction: {ms}ms")
            self.config.set_setting("microaim", "pulse_duration", sec)
            if self.microaim_controller.is_active:
                self.microaim_controller.set_pulse_duration(sec)

        pulse_slider = ModernSlider(slider_frame, from_=10, to=500, number_of_steps=490, width=380, command=on_pulse_change)
        pulse_slider.set(saved_ms)
        pulse_slider.pack(fill="x")

        rng = ctk.CTkFrame(slider_frame, fg_color="transparent")
        rng.pack(fill="x", pady=(4, 0))
        ModernLabel(rng, text="10ms", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(rng, text="500ms", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="right")

        return {
            "card": card,
            "status": status_lbl,
            "switch": switch,
            "title": title_lbl,
            "pulse_slider": pulse_slider,
            "pulse_lbl": pulse_lbl,
        }

    def create_autoclicker_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        left_key = self.config.get_keybind("autoclicker_left") or "z"
        right_key = self.config.get_keybind("autoclicker_right") or "x"
        title_text = f"AutoClicker (L:{_ac_key_display(left_key)} R:{_ac_key_display(right_key)})"
        title_lbl = ModernLabel(header, text=title_text, font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11),
                                  text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="",
                               command=lambda: self.toggle_feature("autoclicker", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))

        left_cps_frame = ctk.CTkFrame(card, fg_color="transparent")
        left_cps_frame.pack(fill="x", padx=16, pady=6)
        left_cps_val_lbl = ModernLabel(left_cps_frame, text="Left CPS: 10.0",
                                        font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        left_cps_val_lbl.pack(anchor="w", pady=(0, 8))
        def left_cps_slider_command(v):
            val = float(v)
            left_cps_val_lbl.configure(text=f"Left CPS: {val:.1f}")
            self.config.set_setting("autoclicker", "left_cps", val)
            if self.autoclicker_controller.is_active:
                right_cps = self.config.get_setting("autoclicker", "right_cps", 10.0)
                self.autoclicker_controller.set_cps(val, right_cps)
        left_cps_slider = ModernSlider(left_cps_frame, from_=1.0, to=20.0,
                                        number_of_steps=190, width=380,
                                        command=left_cps_slider_command)
        left_cps_slider.pack(fill="x")

        right_cps_frame = ctk.CTkFrame(card, fg_color="transparent")
        right_cps_frame.pack(fill="x", padx=16, pady=6)
        right_cps_val_lbl = ModernLabel(right_cps_frame, text="Right CPS: 10.0",
                                         font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        right_cps_val_lbl.pack(anchor="w", pady=(0, 8))
        def right_cps_slider_command(v):
            val = float(v)
            right_cps_val_lbl.configure(text=f"Right CPS: {val:.1f}")
            self.config.set_setting("autoclicker", "right_cps", val)
            if self.autoclicker_controller.is_active:
                left_cps = self.config.get_setting("autoclicker", "left_cps", 10.0)
                self.autoclicker_controller.set_cps(left_cps, val)
        right_cps_slider = ModernSlider(right_cps_frame, from_=1.0, to=20.0,
                                         number_of_steps=190, width=380,
                                         command=right_cps_slider_command)
        right_cps_slider.pack(fill="x")

        chk_frame = ctk.CTkFrame(card, fg_color="transparent")
        chk_frame.pack(fill="x", padx=16, pady=(6, 12))

        left_var  = ctk.BooleanVar(value=self.config.get_setting("autoclicker", "left_enabled", True))
        right_var = ctk.BooleanVar(value=self.config.get_setting("autoclicker", "right_enabled", True))
        jitter_var = ctk.BooleanVar(value=self.config.get_setting("autoclicker", "jitter_enabled", False))

        def left_checkbox_command():
            enabled = left_var.get()
            self.config.set_setting("autoclicker", "left_enabled", enabled)
            if self.autoclicker_controller.is_active:
                self.autoclicker_controller.set_click_enabled(enabled, right_var.get())

        def right_checkbox_command():
            enabled = right_var.get()
            self.config.set_setting("autoclicker", "right_enabled", enabled)
            if self.autoclicker_controller.is_active:
                self.autoclicker_controller.set_click_enabled(left_var.get(), enabled)

        def on_jitter_toggle():
            enabled  = jitter_var.get()
            strength = self.config.get_setting("autoclicker", "jitter_strength", 2.0)
            self.config.set_setting("autoclicker", "jitter_enabled", enabled)
            if enabled:
                jitter_slider_frame.pack(fill="x", padx=16, pady=(0, 12))
            else:
                jitter_slider_frame.pack_forget()
            self.autoclicker_controller.set_jitter(enabled, strength)
            self.triggerbot_controller.set_jitter(enabled, strength)

        ModernCheckBox(chk_frame, text="Left Click", variable=left_var,
                       command=left_checkbox_command).pack(side="left", padx=(0, 12))
        ModernCheckBox(chk_frame, text="Right Click", variable=right_var,
                       command=right_checkbox_command).pack(side="left", padx=(0, 12))
        ModernCheckBox(chk_frame, text="Jitter", variable=jitter_var,
                       command=on_jitter_toggle).pack(side="left")

        jitter_slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        saved_jitter_strength = self.config.get_setting("autoclicker", "jitter_strength", 2.0)
        jitter_val_lbl = ModernLabel(jitter_slider_frame,
                                      text=f"Jitter Strength: {saved_jitter_strength:.1f}",
                                      font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        jitter_val_lbl.pack(anchor="w", pady=(0, 8))

        def on_jitter_strength_change(v):
            val = float(v)
            jitter_val_lbl.configure(text=f"Jitter Strength: {val:.1f}")
            self.config.set_setting("autoclicker", "jitter_strength", val)
            enabled = self.config.get_setting("autoclicker", "jitter_enabled", False)
            self.autoclicker_controller.set_jitter(enabled, val)
            self.triggerbot_controller.set_jitter(enabled, val)

        jitter_slider = ModernSlider(jitter_slider_frame, from_=1.0, to=10.0,
                                      number_of_steps=90, width=380,
                                      command=on_jitter_strength_change)
        jitter_slider.set(saved_jitter_strength)
        jitter_slider.pack(fill="x")

        jitter_rng = ctk.CTkFrame(jitter_slider_frame, fg_color="transparent")
        jitter_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(jitter_rng, text="1.0", font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(jitter_rng, text="10.0", font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")

        if jitter_var.get():
            jitter_slider_frame.pack(fill="x", padx=16, pady=(0, 12))
        else:
            ctk.CTkFrame(card, fg_color="transparent", height=12).pack()

        return {
            "card": card,
            "status": status_lbl,
            "switch": switch,
            "left_slider": left_cps_slider,
            "right_slider": right_cps_slider,
            "left_value_label": left_cps_val_lbl,
            "right_value_label": right_cps_val_lbl,
            "title": title_lbl,
            "left_var": left_var,
            "right_var": right_var,
            "jitter_var": jitter_var,
            "jitter_slider": jitter_slider,
            "jitter_val_lbl": jitter_val_lbl,
            "jitter_slider_frame": jitter_slider_frame,
        }

    def create_antiknockback_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        title_lbl = ModernLabel(header, text="AntiKnockback", font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature("antiknockback", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        xz_frame = ctk.CTkFrame(card, fg_color="transparent")
        xz_frame.pack(fill="x", padx=16, pady=6)
        xz_lbl = ModernLabel(xz_frame, text="X/Z: 0.80", font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        xz_lbl.pack(anchor="w", pady=(0, 8))
        def xz_slider_command(v):
            val = float(v)
            xz_lbl.configure(text=f"X/Z: {val:.2f}")
            self.config.set_setting("antiknockback", "xz", val)
            if self.antikb_controller:
                current_y = self.config.get_setting("antiknockback", "y", 0.8)
                self.antikb_controller.set_multipliers(val, current_y)
        xz_slider = ModernSlider(xz_frame, from_=0.0, to=2.0, number_of_steps=200, width=380, command=xz_slider_command)
        xz_slider.pack(fill="x")
        y_frame = ctk.CTkFrame(card, fg_color="transparent")
        y_frame.pack(fill="x", padx=16, pady=(6, 12))
        y_lbl = ModernLabel(y_frame, text="Y: 0.80", font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        y_lbl.pack(anchor="w", pady=(0, 8))
        def y_slider_command(v):
            val = float(v)
            y_lbl.configure(text=f"Y: {val:.2f}")
            self.config.set_setting("antiknockback", "y", val)
            if self.antikb_controller:
                current_xz = self.config.get_setting("antiknockback", "xz", 0.8)
                self.antikb_controller.set_multipliers(current_xz, val)
        y_slider = ModernSlider(y_frame, from_=0.0, to=2.0, number_of_steps=200, width=380, command=y_slider_command)
        y_slider.pack(fill="x")
        return {"card": card, "status": status_lbl, "switch": switch, "xz_slider": xz_slider, "y_slider": y_slider, "xz_label": xz_lbl, "y_label": y_lbl}

    def create_jumpreset_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        title_lbl = ModernLabel(header, text="Jump Reset", font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature("jumpreset", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        keybind_frame = ctk.CTkFrame(card, fg_color="transparent")
        keybind_frame.pack(fill="x", padx=16, pady=(4, 0))
        keybind_frame.grid_columnconfigure(1, weight=1)
        ModernLabel(keybind_frame, text="Set Your Jump Key:", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w").grid(row=0, column=0, sticky="w")
        current_jump_key = self.config.get_keybind("jump") or "space"
        jump_key_entry = ctk.CTkEntry(keybind_frame, width=120, justify="center", corner_radius=6, border_width=2,
                                      border_color=COLORS["border"], fg_color=COLORS["card"], text_color=COLORS["text"],
                                      font=("Segoe UI", 12), height=32)
        jump_key_entry.grid(row=0, column=1, sticky="e")
        jump_key_entry.insert(0, current_jump_key.upper())
        jump_key_entry.configure(state="readonly")
        def _finish_jump_entry(border, text_color):
            jump_key_entry.configure(border_color=border, text_color=text_color)
            self.focus()
        def on_jump_key_press(event):
            new_key = event.keysym.lower()
            ignore_keys = ["shift","shift_l","shift_r","control","control_l","control_r","alt","alt_l","alt_r","caps_lock","tab","escape","super_l","super_r","win_l","win_r"]
            if new_key in ignore_keys:
                orig = jump_key_entry.get()
                jump_key_entry.configure(state="normal", border_color="#ff5252", text_color="#ff5252")
                jump_key_entry.delete(0, "end")
                jump_key_entry.insert(0, "Invalid Key!")
                jump_key_entry.configure(state="readonly")
                self.after(1200, lambda: _restore_jump_entry(orig))
                return
            current_keybinds = self.config.config.get("keybinds", {})
            for other_feature, bound_key in current_keybinds.items():
                if other_feature != "jump" and bound_key == new_key:
                    orig = jump_key_entry.get()
                    jump_key_entry.configure(state="normal", border_color="#ff5252", text_color="#ff5252")
                    jump_key_entry.delete(0, "end")
                    jump_key_entry.insert(0, "Key in Use!")
                    jump_key_entry.configure(state="readonly")
                    self.after(1200, lambda: _restore_jump_entry(orig))
                    return
            display_key = new_key.upper()
            self.config.set_keybind("jump", new_key)
            jump_key_entry.configure(state="normal")
            jump_key_entry.delete(0, "end")
            jump_key_entry.insert(0, display_key)
            jump_key_entry.configure(state="readonly", border_color=COLORS["success"], text_color=COLORS["success"])
            self.after(600, lambda: _finish_jump_entry(COLORS["border"], COLORS["text"]))
            if self.jumpreset_controller.is_active:
                self.jumpreset_controller.set_jump_key(new_key)
            return "break"
        def _restore_jump_entry(original_text):
            jump_key_entry.configure(state="normal", border_color=COLORS["border"], text_color=COLORS["text"])
            jump_key_entry.delete(0, "end")
            jump_key_entry.insert(0, original_text)
            jump_key_entry.configure(state="readonly")
            self.focus()
        def on_jump_entry_click(event):
            jump_key_entry.configure(border_color=COLORS["accent_light"])
        def on_jump_entry_focus_out(event):
            jump_key_entry.configure(border_color=COLORS["border"])
        jump_key_entry.bind("<KeyPress>", on_jump_key_press)
        jump_key_entry.bind("<Button-1>", on_jump_entry_click)
        jump_key_entry.bind("<FocusOut>", on_jump_entry_focus_out)
        slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(10, 12))
        default_timing = self.config.get_setting("jumpreset", "timing", 0.54)
        timing_lbl = ModernLabel(slider_frame, text=f"Jump Hold Time: {default_timing:.2f}s", font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        timing_lbl.pack(anchor="w", pady=(0, 8))
        def slider_command(v):
            val = float(v)
            timing_lbl.configure(text=f"Jump Hold Time: {val:.2f}s")
            self.config.set_setting("jumpreset", "timing", val)
            if self.jumpreset_controller.is_active:
                self.jumpreset_controller.set_jump_timing(val)
        slider = ModernSlider(slider_frame, from_=0.1, to=1.0, number_of_steps=90, width=380, command=slider_command)
        slider.pack(fill="x")
        rng = ctk.CTkFrame(slider_frame, fg_color="transparent")
        rng.pack(fill="x", pady=(4, 0))
        ModernLabel(rng, text="0.1s", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(rng, text="1.0s", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="right")
        return {"card": card, "status": status_lbl, "switch": switch, "slider": slider, "timing_label": timing_lbl, "jump_key_entry": jump_key_entry}

    def create_zoom_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(pady=12, padx=16, fill="x")
        header.grid_columnconfigure(1, weight=1)
        zoom_key = self.config.get_keybind("zoom") or "c"
        title_text = f"Zoom ({zoom_key.upper()})"
        title_lbl = ModernLabel(header, text=title_text, font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature("zoom", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        chk_frame = ctk.CTkFrame(card, fg_color="transparent")
        chk_frame.pack(fill="x", padx=16, pady=(0, 12))
        smooth_var = ctk.BooleanVar(value=self.config.get_setting("zoom", "smooth_animation", True))
        def on_smooth_toggle():
            enabled = smooth_var.get()
            self.config.set_setting("zoom", "smooth_animation", enabled)
            if hasattr(self, 'zoom_controller'):
                self.zoom_controller.set_smooth_animation(enabled)
        ModernCheckBox(chk_frame, text="Smooth Animation", variable=smooth_var, command=on_smooth_toggle).pack(side="left", padx=(0, 8))
        return {"card": card, "status": status_lbl, "switch": switch, "title": title_lbl, "keybind_key": "zoom", "smooth_var": smooth_var}

    def create_visual_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        w = self.create_feature_card(parent, "Fullbright", "brightness", "brightness")
        self.widgets["Visual"]["brightness"] = w
        w = self.create_zoom_card(parent)
        self.widgets["Visual"]["zoom"] = w
        w = self.create_feature_card(parent, "Coordinates", "coordinates")
        self.widgets["Visual"]["coordinates"] = w
        w = self.create_feature_card(parent, "TrueSight", "truesight")
        self.widgets["Visual"]["truesight"] = w
        w = self.create_timechanger_card(parent)
        self.widgets["Visual"]["timechanger"] = w
        if self.minecraft_version == "1.21.13":
            w = self.create_feature_card(parent, "No Hurt Cam", "nohurtcam")
            self.widgets["Visual"]["nohurtcam"] = w

    def create_combat_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        w = self.create_slider_card(parent, "Reach", "reach", "reach", 3.0, 7.0, 3.0, steps=400)
        self.widgets["Combat"]["reach"] = w
        w = self.create_autoclicker_card(parent)
        self.widgets["Combat"]["autoclicker"] = w
        w = self.create_slider_card(parent, "Hitbox", "hitbox", "hitbox", 1.0, 2.0, 1.0, steps=100)
        self.widgets["Combat"]["hitbox"] = w
        w = self.create_triggerbot_card(parent)
        self.widgets["Combat"]["triggerbot"] = w
        w = self.create_microaim_card(parent)
        self.widgets["Combat"]["microaim"] = w
        w = self.create_aimassist_card(parent)
        self.widgets["Combat"]["aimassist"] = w

    def create_movement_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        w = self.create_feature_card(parent, "Toggle Sprint", "sprint", "sprint")
        self.widgets["Movement"]["sprint"] = w
        w = self.create_slider_card(parent, "Speed", "speed", "speed", 0.5, 5.0, 0.5, steps=450)
        self.widgets["Movement"]["speed"] = w
        if hasattr(self, 'full_version') and MinecraftVersionDetector.is_jumpreset_supported(self.full_version):
            w = self.create_jumpreset_card(parent)
            self.widgets["Movement"]["jumpreset"] = w
        w = self.create_antiknockback_card(parent)
        self.widgets["Movement"]["antiknockback"] = w
    def create_aimassist_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
 
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
 
        title_lbl = ModernLabel(
            header, text="Aim Assist",
            font=("Segoe UI", 13, "bold"), anchor="w"
        )
        title_lbl.grid(row=0, column=0, sticky="w")
 
        status_lbl = ModernLabel(
            header, text="Inactive",
            font=("Segoe UI", 11),
            text_color=COLORS["text_secondary"], anchor="w"
        )
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
 
        switch = ModernSwitch(
            header, text="",
            command=lambda: self.toggle_feature("aimassist", status_lbl, switch)
        )
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
 
        sens_frame = ctk.CTkFrame(card, fg_color="transparent")
        sens_frame.pack(fill="x", padx=16, pady=(0, 6))
 
        saved_sens = self.config.get_setting("aimassist", "sensitivity", 0.50)
        saved_sens = max(0.01, min(1.00, float(saved_sens)))
 
        sens_lbl = ModernLabel(
            sens_frame,
            text=f"Set In-Game Sensitivity: {saved_sens:.2f}",
            font=("Segoe UI", 11),
            text_color=COLORS["accent"], anchor="w"
        )
        sens_lbl.pack(anchor="w", pady=(0, 8))
 
        def on_sens_change(v):
            val = round(float(v), 2)
            sens_lbl.configure(text=f"Set In-Game Sensitivity: {val:.2f}")
            self.config.set_setting("aimassist", "sensitivity", val)
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_sensitivity(val)
 
        sens_slider = ModernSlider(
            sens_frame,
            from_=0.01, to=1.00,
            number_of_steps=99,
            width=380,
            command=on_sens_change,
        )
        sens_slider.set(saved_sens)
        sens_slider.pack(fill="x")
 
        sens_rng = ctk.CTkFrame(sens_frame, fg_color="transparent")
        sens_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(sens_rng, text="0.01 (Slow)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(sens_rng, text="1.00 (Fast)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")
 
        dist_frame = ctk.CTkFrame(card, fg_color="transparent")
        dist_frame.pack(fill="x", padx=16, pady=(6, 6))
 
        saved_dist = self.config.get_setting("aimassist", "max_dist", 6.0)
        saved_dist = max(3.0, min(8.0, float(saved_dist)))
 
        dist_lbl = ModernLabel(
            dist_frame,
            text=f"Max Range: {saved_dist:.2f}",
            font=("Segoe UI", 11),
            text_color=COLORS["accent"], anchor="w"
        )
        dist_lbl.pack(anchor="w", pady=(0, 8))
 
        def on_dist_change(v):
            val = round(float(v), 2)
            dist_lbl.configure(text=f"Max Range: {val:.2f}")
            self.config.set_setting("aimassist", "max_dist", val)
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_max_dist(val)
 
        dist_slider = ModernSlider(
            dist_frame,
            from_=3.0, to=8.0,
            number_of_steps=50,
            width=380,
            command=on_dist_change,
        )
        dist_slider.set(saved_dist)
        dist_slider.pack(fill="x")
 
        dist_rng = ctk.CTkFrame(dist_frame, fg_color="transparent")
        dist_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(dist_rng, text="3.0",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(dist_rng, text="8.0",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")
 
        player_yoff_frame = ctk.CTkFrame(card, fg_color="transparent")
        player_yoff_frame.pack(fill="x", padx=16, pady=(6, 6))

        saved_player_yoff = self.config.get_setting("aimassist", "y_offset_player", 0.22)
        saved_player_yoff = max(0.0, min(1.0, float(saved_player_yoff)))

        player_yoff_lbl = ModernLabel(
            player_yoff_frame,
            text=f"Player Y Offset: {saved_player_yoff:.2f}",
            font=("Segoe UI", 11),
            text_color=COLORS["accent"], anchor="w"
        )
        player_yoff_lbl.pack(anchor="w", pady=(0, 8))

        def on_player_yoff_change(v):
            val = round(float(v), 2)
            player_yoff_lbl.configure(text=f"Player Y Offset: {val:.2f}")
            self.config.set_setting("aimassist", "y_offset_player", val)
            actual = 2.60 - val * 1.50
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_y_offset_player(actual)

        player_yoff_slider = ModernSlider(
            player_yoff_frame,
            from_=0.0, to=1.0,
            number_of_steps=100,
            width=380,
            command=on_player_yoff_change,
        )
        player_yoff_slider.set(saved_player_yoff)
        player_yoff_slider.pack(fill="x")

        player_yoff_rng = ctk.CTkFrame(player_yoff_frame, fg_color="transparent")
        player_yoff_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(player_yoff_rng, text="0.00 (Leg)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(player_yoff_rng, text="1.00 (Head)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")
 
        other_yoff_frame = ctk.CTkFrame(card, fg_color="transparent")
        other_yoff_frame.pack(fill="x", padx=16, pady=(6, 6))

        saved_other_yoff = self.config.get_setting("aimassist", "y_offset_other", 0.53)
        saved_other_yoff = max(0.0, min(1.0, float(saved_other_yoff)))

        other_yoff_lbl = ModernLabel(
            other_yoff_frame,
            text=f"Other Entity Y Offset: {saved_other_yoff:.2f}",
            font=("Segoe UI", 11),
            text_color=COLORS["accent"], anchor="w"
        )
        other_yoff_lbl.pack(anchor="w", pady=(0, 8))

        def on_other_yoff_change(v):
            val = round(float(v), 2)
            other_yoff_lbl.configure(text=f"Other Entity Y Offset: {val:.2f}")
            self.config.set_setting("aimassist", "y_offset_other", val)
            actual = 1.50 - val * 1.70
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_y_offset_other(actual)

        other_yoff_slider = ModernSlider(
            other_yoff_frame,
            from_=0.0, to=1.0,
            number_of_steps=100,
            width=380,
            command=on_other_yoff_change,
        )
        other_yoff_slider.set(saved_other_yoff)
        other_yoff_slider.pack(fill="x")

        other_yoff_rng = ctk.CTkFrame(other_yoff_frame, fg_color="transparent")
        other_yoff_rng.pack(fill="x", pady=(4, 0))
        ModernLabel(other_yoff_rng, text="0.00 (Leg)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(other_yoff_rng, text="1.00 (Head)",
                    font=("Segoe UI", 9),
                    text_color=COLORS["text_secondary"]).pack(side="right")
 
        auto_clicker_frame = ctk.CTkFrame(card, fg_color="transparent")
        auto_clicker_frame.pack(fill="x", padx=16, pady=(6, 4))
 
        saved_auto_click_only = self.config.get_setting("aimassist", "aim_only_on_autoclicker", False)
        auto_click_var = ctk.BooleanVar(value=saved_auto_click_only)
 
        def on_auto_click_toggle():
            self.config.set_setting("aimassist", "aim_only_on_autoclicker", auto_click_var.get())
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_aim_only_on_autoclicker(auto_click_var.get())
 
        ModernCheckBox(
            auto_clicker_frame,
            text="Left Auto-Click Only",
            variable=auto_click_var,
            command=on_auto_click_toggle
        ).pack(side="left", padx=(0, 12))
 
        target_mode_frame = ctk.CTkFrame(card, fg_color="transparent")
        target_mode_frame.pack(fill="x", padx=16, pady=(2, 12))
 
        saved_aim_player = self.config.get_setting("aimassist", "aim_player", True)
        saved_aim_other  = self.config.get_setting("aimassist", "aim_other",  False)
 
        player_var = ctk.BooleanVar(value=saved_aim_player)
        other_var  = ctk.BooleanVar(value=saved_aim_other)
 
        def _on_target_change():
            p = player_var.get()
            o = other_var.get()
            self.config.set_setting("aimassist", "aim_player", p)
            self.config.set_setting("aimassist", "aim_other",  o)
            if hasattr(self, 'aimassist_controller'):
                self.aimassist_controller.set_target_mode(p, o)
 
        ModernCheckBox(
            target_mode_frame,
            text="Only PlayerEntitys",
            variable=player_var,
            command=_on_target_change,
        ).pack(side="left", padx=(0, 12))
 
        ModernCheckBox(
            target_mode_frame,
            text="Other Entitys",
            variable=other_var,
            command=_on_target_change,
        ).pack(side="left")
 
        return {
            "card":               card,
            "status":             status_lbl,
            "switch":             switch,
            "title":              title_lbl,
            "sens_slider":        sens_slider,
            "sens_lbl":           sens_lbl,
            "dist_slider":        dist_slider,
            "dist_lbl":           dist_lbl,
            "player_yoff_slider": player_yoff_slider,
            "player_yoff_lbl":    player_yoff_lbl,
            "other_yoff_slider":  other_yoff_slider,
            "other_yoff_lbl":     other_yoff_lbl,
            "auto_click_var":     auto_click_var,
            "player_var":         player_var,
            "other_var":          other_var,
        }
    def create_timechanger_card(self, parent):
        card = ModernFrame(parent, border_color=COLORS["border"])
        card.pack(pady=5, padx=10, fill="x")
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 8))
        header.grid_columnconfigure(1, weight=1)
        title_lbl = ModernLabel(header, text="Time Changer", font=("Segoe UI", 13, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="w")
        status_lbl = ModernLabel(header, text="Inactive", font=("Segoe UI", 11), text_color=COLORS["text_secondary"], anchor="w")
        status_lbl.grid(row=0, column=1, padx=(20, 0), sticky="w")
        switch = ModernSwitch(header, text="", command=lambda: self.toggle_feature("timechanger", status_lbl, switch))
        switch.grid(row=0, column=3, sticky="e", padx=(10, 0))
        preset_frame = ctk.CTkFrame(card, fg_color="transparent")
        preset_frame.pack(fill="x", padx=16, pady=6)
        preset_options = ["Day", "Noon", "Sunset", "Night", "Midnight", "Sunrise"]
        preset_var = ctk.StringVar(value="Day")
        def preset_changed(choice):
            time_value = self.timechanger_controller.TIME_PRESETS[choice]
            self.config.set_setting("timechanger", "time", time_value)
            self.config.set_setting("timechanger", "preset", choice)
            slider.set(time_value)
            time_lbl.configure(text=f"Time: {int(time_value)} ({choice})")
            if self.timechanger_controller.is_active:
                self.timechanger_controller.set_time(time_value)
        preset_dropdown = ctk.CTkOptionMenu(preset_frame, variable=preset_var, values=preset_options, command=preset_changed,
                                            fg_color=COLORS["accent"], button_color=COLORS["accent_dark"], button_hover_color=COLORS["accent_light"],
                                            dropdown_fg_color=COLORS["card"], dropdown_hover_color=COLORS["card_hover"],
                                            font=("Segoe UI", 12), dropdown_font=("Segoe UI", 11), width=380)
        preset_dropdown.pack(fill="x")
        slider_frame = ctk.CTkFrame(card, fg_color="transparent")
        slider_frame.pack(fill="x", padx=16, pady=(10, 12))
        default_time = self.config.get_setting("timechanger", "time", 1000)
        time_lbl = ModernLabel(slider_frame, text=f"Time: {int(default_time)} (Day)", font=("Segoe UI", 11), text_color=COLORS["accent"], anchor="w")
        time_lbl.pack(anchor="w", pady=(0, 8))
        def slider_command(v):
            val = int(v)
            preset_name = "Custom"
            for name, preset_val in self.timechanger_controller.TIME_PRESETS.items():
                if abs(preset_val - val) < 100:
                    preset_name = name
                    preset_var.set(name)
                    break
            display_text = f"Time: {val}" + (f" ({preset_name})" if preset_name != "Custom" else "")
            time_lbl.configure(text=display_text)
            self.config.set_setting("timechanger", "time", val)
            if self.timechanger_controller.is_active:
                self.timechanger_controller.set_time(val)
        slider = ModernSlider(slider_frame, from_=0, to=24000, number_of_steps=240, width=380, command=slider_command)
        slider.pack(fill="x")
        rng = ctk.CTkFrame(slider_frame, fg_color="transparent")
        rng.pack(fill="x", pady=(4, 0))
        ModernLabel(rng, text="0", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="left")
        ModernLabel(rng, text="24000", font=("Segoe UI", 9), text_color=COLORS["text_secondary"]).pack(side="right")
        return {"card": card, "status": status_lbl, "switch": switch, "slider": slider, "time_label": time_lbl, "preset_var": preset_var, "preset_dropdown": preset_dropdown}

    def create_misc_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        w = self.create_feature_card(parent, "Streamprotect", "streamprotect")
        self.widgets["Misc"]["streamprotect"] = w
        w_tray = self.create_feature_card(parent, title="System Tray", feature_name="systemtray")
        self.widgets["Misc"]["systemtray"] = w_tray

    def create_player_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        w = self.create_feature_card(parent, title="Fast Item", feature_name="fastitem")
        self.widgets.setdefault("Player", {})["fastitem"] = w

    def switch_tab(self, tab_name):
        for name, lbl in self.tab_labels.items():
            if name == tab_name:
                lbl.configure(fg_color=COLORS["sidebar_active"], text_color=COLORS["text"])
            else:
                lbl.configure(fg_color="transparent", text_color=COLORS["text_secondary"])
        for frame in self.tab_frames.values():
            frame.pack_forget()
        self.current_tab = tab_name
        self.tab_frames[tab_name].pack(fill="both", expand=True, padx=12, pady=12)
        self.after(50, lambda: self._rebind_scroll_for_tab(self.tab_frames[tab_name]))
        self.after(10, lambda: self.content_frame._parent_canvas.yview_moveto(0))

    def _setup_scroll_binding(self):
        def _on_mousewheel(event):
            try:
                self.content_frame._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        def _bind_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
            for child in widget.winfo_children():
                _bind_recursive(child)
        self._on_mousewheel_handler = _on_mousewheel
        self._bind_recursive_fn = _bind_recursive
        _bind_recursive(self.tab_content_frame)
        self.content_frame.bind("<MouseWheel>", _on_mousewheel, add="+")

    def _rebind_scroll_for_tab(self, frame):
        if hasattr(self, '_bind_recursive_fn'):
            self._bind_recursive_fn(frame)

    def toggle_feature(self, feature_name, status_label, switch):
        state = switch.get() == 1
        self.config.set_state(feature_name, state)

        if feature_name == "antiknockback":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                xz_value = self.config.get_setting("antiknockback", "xz", 0.8)
                y_value  = self.config.get_setting("antiknockback", "y", 0.8)
                self.antikb_controller.set_multipliers(xz_value, y_value)
                self.antikb_controller.start()
            else:
                self.antikb_controller.stop()
        elif feature_name == "reach":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                reach_value = self.config.get_setting("reach", "reach", 3.0)
                self.reach_controller.set_reach_value(reach_value)
                self.reach_controller.start()
            else:
                self.reach_controller.stop()
        elif feature_name == "hitbox":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                hitbox_value = self.config.get_setting("hitbox", "hitbox", 1.0)
                self.hitbox_controller.set_hitbox_value(hitbox_value)
                self.hitbox_controller.start()
            else:
                self.hitbox_controller.stop()
        elif feature_name == "zoom":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                zoom_key = self.config.get_keybind("zoom") or "c"
                self.zoom_controller.start(zoom_key)
            else:
                self.zoom_controller.stop()
        elif feature_name == "brightness":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                self.brightness_controller.start()
            else:
                self.brightness_controller.stop()
        elif feature_name == "speed":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                speed_value = self.config.get_setting("speed", "speed", 0.5)
                self.speed_controller.set_speed_value(speed_value)
                self.speed_controller.start()
            else:
                self.speed_controller.stop()
        elif feature_name == "coordinates":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                self.coordinates_controller.start()
            else:
                self.coordinates_controller.stop()
        elif feature_name == "autoclicker":
            if state:
                left_cps      = self.config.get_setting("autoclicker", "left_cps", 10.0)
                right_cps     = self.config.get_setting("autoclicker", "right_cps", 10.0)
                left_enabled  = self.config.get_setting("autoclicker", "left_enabled", True)
                right_enabled = self.config.get_setting("autoclicker", "right_enabled", True)
                left_key      = self.config.get_keybind("autoclicker_left") or "z"
                right_key     = self.config.get_keybind("autoclicker_right") or "x"
                jitter_on     = self.config.get_setting("autoclicker", "jitter_enabled", False)
                jitter_str    = self.config.get_setting("autoclicker", "jitter_strength", 2.0)
                self.autoclicker_controller.set_cps(left_cps, right_cps)
                self.autoclicker_controller.set_click_enabled(left_enabled, right_enabled)
                self.autoclicker_controller.set_keybinds(left_key, right_key)
                self.autoclicker_controller.set_jitter(jitter_on, jitter_str)
                self.triggerbot_controller.set_jitter(jitter_on, jitter_str)
                self.autoclicker_controller.start()
            else:
                self.autoclicker_controller.stop()
        elif feature_name == "sprint":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                sprint_key = self.config.get_keybind("sprint") or "p"
                self.sprint_controller.current_key = sprint_key
                self.sprint_controller.start()
            else:
                self.sprint_controller.stop()
        elif feature_name == "nohurtcam":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                self.nohurtcam_controller.start()
            else:
                self.nohurtcam_controller.stop()
        elif feature_name == "truesight":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                self.truesight_controller.start()
            else:
                self.truesight_controller.stop()
        elif feature_name == "timechanger":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                time_value = self.config.get_setting("timechanger", "time", 1000)
                self.timechanger_controller.set_time(time_value)
                self.timechanger_controller.start()
            else:
                self.timechanger_controller.stop()
        elif feature_name == "fastitem":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                self.fastitem_controller.start()
            else:
                self.fastitem_controller.stop()
        elif feature_name == "jumpreset":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                jump_key    = self.config.get_keybind("jump") or "space"
                jump_timing = self.config.get_setting("jumpreset", "timing", 0.54)
                self.jumpreset_controller.set_jump_key(jump_key)
                self.jumpreset_controller.set_jump_timing(jump_timing)
                self.jumpreset_controller.start()
            else:
                self.jumpreset_controller.stop()

        elif feature_name == "triggerbot":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                tb_mode = self.config.get_setting("triggerbot", "mode", "first_hit")
                tb_cps  = self.config.get_setting("triggerbot", "auto_cps", 12.0)
                tb_atk  = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
                if tb_atk in ("left", "right"):
                    tb_atk = "mouse_" + tb_atk
                self.triggerbot_controller.set_mode(tb_mode)
                self.triggerbot_controller.set_auto_cps(tb_cps)
                self.triggerbot_controller.set_attack_button(tb_atk)
                self.triggerbot_controller.start()
            else:
                self.triggerbot_controller.stop()

        elif feature_name == "microaim":
            if not self.game_process:
                switch.deselect(); status_label.configure(text="Inactive", text_color='#ff5252'); self.config.set_state(feature_name, False); return
            if state:
                pulse = self.config.get_setting("microaim", "pulse_duration", 0.1)
                self.microaim_controller.set_pulse_duration(pulse)
                self.microaim_controller.start()
            else:
                self.microaim_controller.stop()

        elif feature_name == "aimassist":
            if not self.game_process:
                switch.deselect()
                status_label.configure(text="Inactive", text_color='#ff5252')
                self.config.set_state(feature_name, False)
                return
            if state:
                sens          = self.config.get_setting("aimassist", "sensitivity", 0.50)
                max_dist      = self.config.get_setting("aimassist", "max_dist", 6.0)
                aim_only_on_ac = self.config.get_setting("aimassist", "aim_only_on_autoclicker", False)
                aim_player    = self.config.get_setting("aimassist", "aim_player", True)
                aim_other     = self.config.get_setting("aimassist", "aim_other",  False)
                self.aimassist_controller.set_sensitivity(sens)
                self.aimassist_controller.set_max_dist(max_dist)
                self.aimassist_controller.set_autoclicker_reference(self.autoclicker_controller)
                self.aimassist_controller.set_aim_only_on_autoclicker(aim_only_on_ac)
                self.aimassist_controller.set_target_mode(aim_player, aim_other)
                self.aimassist_controller.start()
            else:
                self.aimassist_controller.stop()

        elif feature_name == "systemtray":
            if state:
                success = self.systemtray_controller.start()
                if success:
                    status_label.configure(text="Active", text_color=COLORS["success"])
                else:
                    switch.deselect()
                    status_label.configure(text="Failed to create tray", text_color='#ff5252')
                    self.config.set_state("systemtray", False)
            else:
                self.systemtray_controller.stop()
                status_label.configure(text="Inactive", text_color=COLORS["text_secondary"])
        elif feature_name == "streamprotect":
            if not self.streamprotect_controller.initialized:
                switch.deselect(); status_label.configure(text="Not initialized", text_color='#ff9800'); self.config.set_state(feature_name, False); return
            if state:
                self.streamprotect_controller.start()
                self.attributes('-topmost', True)
                if hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists():
                    self.keybind_window.attributes('-topmost', True)
                status_label.configure(text="Active", text_color=COLORS["success"])
            else:
                self.streamprotect_controller.stop()
                self.attributes('-topmost', False)
                if hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists():
                    self.keybind_window.attributes('-topmost', False)
                status_label.configure(text="Inactive", text_color=COLORS["text_secondary"])

    def _block_input(self):
        hwnd = ctypes.windll.user32.FindWindowW(None, f"Torio Client - Minecraft {self.minecraft_version}")
        if hwnd:
            ctypes.windll.user32.EnableWindow(hwnd, False)

    def _unblock_input(self):
        hwnd = ctypes.windll.user32.FindWindowW(None, f"Torio Client - Minecraft {self.minecraft_version}")
        if hwnd:
            ctypes.windll.user32.EnableWindow(hwnd, True)

    def apply_config_to_gui(self):
        c = self.config
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)
        for f in ["coordinates"]:
            if f in self.widgets["Visual"]:
                w = self.widgets["Visual"][f]
                if c.get_state(f):
                    w["switch"].select()
                    w["status"].configure(text="Active", text_color=COLORS["success"])
        if "brightness" in self.widgets["Visual"]:
            w_brightness = self.widgets["Visual"]["brightness"]
            if c.get_state("brightness"):
                w_brightness["switch"].select()
                w_brightness["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        if "zoom" in self.widgets["Visual"]:
            w_zoom = self.widgets["Visual"]["zoom"]
            if c.get_state("zoom"):
                w_zoom["switch"].select()
                w_zoom["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            if "smooth_var" in w_zoom:
                w_zoom["smooth_var"].set(self.config.get_setting("zoom", "smooth_animation", True))
        if "coordinates" in self.widgets["Visual"]:
            w_coordinates = self.widgets["Visual"]["coordinates"]
            if c.get_state("coordinates"):
                w_coordinates["switch"].select()
                w_coordinates["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        w_reach = self.widgets["Combat"]["reach"]
        if c.get_state("reach"):
            w_reach["switch"].select()
            w_reach["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        reach_value = c.get_setting("reach", "reach", 3.0)
        w_reach["slider"].set(reach_value)
        w_reach["value_label"].configure(text=f"Value: {reach_value:.2f}")
        w_hitbox = self.widgets["Combat"]["hitbox"]
        if c.get_state("hitbox"):
            w_hitbox["switch"].select()
            w_hitbox["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        hitbox_value = c.get_setting("hitbox", "hitbox", 1.0)
        w_hitbox["slider"].set(hitbox_value)
        w_hitbox["value_label"].configure(text=f"Value: {hitbox_value:.2f}")
        w_autoclicker = self.widgets["Combat"]["autoclicker"]
        left_cps_value  = self.config.get_setting("autoclicker", "left_cps", 10.0)
        right_cps_value = self.config.get_setting("autoclicker", "right_cps", 10.0)
        w_autoclicker["left_slider"].set(left_cps_value)
        w_autoclicker["right_slider"].set(right_cps_value)
        w_autoclicker["left_value_label"].configure(text=f"Left CPS: {left_cps_value:.1f}")
        w_autoclicker["right_value_label"].configure(text=f"Right CPS: {right_cps_value:.1f}")
        left_enabled  = self.config.get_setting("autoclicker", "left_enabled", True)
        right_enabled = self.config.get_setting("autoclicker", "right_enabled", True)
        w_autoclicker["left_var"].set(left_enabled)
        w_autoclicker["right_var"].set(right_enabled)
        if self.config.get_state("autoclicker"):
            w_autoclicker["switch"].select()
            left_key  = self.config.get_keybind("autoclicker_left") or "z"
            right_key = self.config.get_keybind("autoclicker_right") or "x"
            self.autoclicker_controller.set_cps(left_cps_value, right_cps_value)
            self.autoclicker_controller.set_click_enabled(left_enabled, right_enabled)
            self.autoclicker_controller.set_keybinds(left_key, right_key)
            self.autoclicker_controller.start()
            w_autoclicker["status"].configure(text=f"Active (L:{_ac_key_display(left_key)} R:{_ac_key_display(right_key)})", text_color=COLORS["success"])
        else:
            w_autoclicker["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        if "jitter_var" in w_autoclicker:
            jitter_on  = self.config.get_setting("autoclicker", "jitter_enabled", False)
            jitter_str = self.config.get_setting("autoclicker", "jitter_strength", 2.0)
            w_autoclicker["jitter_var"].set(jitter_on)
            w_autoclicker["jitter_slider"].set(jitter_str)
            w_autoclicker["jitter_val_lbl"].configure(
                text=f"Jitter Strength: {jitter_str:.1f}")
            if jitter_on:
                w_autoclicker["jitter_slider_frame"].pack(fill="x", padx=16, pady=(0, 12))
            else:
                w_autoclicker["jitter_slider_frame"].pack_forget()
            self.autoclicker_controller.set_jitter(jitter_on, jitter_str)

        if "triggerbot" in self.widgets["Combat"]:
            w_tb       = self.widgets["Combat"]["triggerbot"]
            saved_mode = self.config.get_setting("triggerbot", "mode", "first_hit")
            saved_cps  = min(self.config.get_setting("triggerbot", "auto_cps", 12.0), 20.0)
            saved_atk  = self.config.get_setting("triggerbot", "attack_button", "mouse_left")
            if saved_atk == "left":  saved_atk = "mouse_left"
            if saved_atk == "right": saved_atk = "mouse_right"

            def _atk_disp(v):
                if v == "mouse_left":  return "MOUSE L"
                if v == "mouse_right": return "MOUSE R"
                return v.upper()

            w_tb["mode_var"].set(saved_mode)
            w_tb["cps_slider"].set(saved_cps)
            w_tb["cps_val_lbl"].configure(text=f"AutoClick CPS: {saved_cps:.1f}")

            w_tb["atk_entry"].configure(state="normal")
            w_tb["atk_entry"].delete(0, "end")
            w_tb["atk_entry"].insert(0, _atk_disp(saved_atk))
            w_tb["atk_entry"].configure(
                state="readonly",
                border_color=COLORS["border"],
                text_color=COLORS["text"]
            )

            if saved_mode == "auto_click":
                w_tb["cps_frame"].pack(fill="x", padx=16, pady=(0, 6))
            else:
                w_tb["cps_frame"].pack_forget()

            if c.get_state("triggerbot"):
                w_tb["switch"].select()
                w_tb["status"].configure(text="Inactive",
                                          text_color=COLORS["text_secondary"])
            else:
                w_tb["switch"].deselect()

        if "microaim" in self.widgets["Combat"]:
            w_ma = self.widgets["Combat"]["microaim"]
            saved_pulse = self.config.get_setting("microaim", "pulse_duration", 0.1)
            saved_ms    = int(round(saved_pulse * 1000))
            w_ma["pulse_slider"].set(saved_ms)
            w_ma["pulse_lbl"].configure(text=f"Sensitivity Reduction: {saved_ms}ms")
            if c.get_state("microaim"):
                w_ma["switch"].select()
                w_ma["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_ma["switch"].deselect()

        w_sprint = self.widgets["Movement"]["sprint"]
        if c.get_state("sprint"):
            w_sprint["switch"].select()
            w_sprint["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        w_speed = self.widgets["Movement"]["speed"]
        if c.get_state("speed"):
            w_speed["switch"].select()
            w_speed["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        speed_value = c.get_setting("speed", "speed", 0.5)
        w_speed["slider"].set(speed_value)
        w_speed["value_label"].configure(text=f"Value: {speed_value:.2f}")
        w_antikb = self.widgets["Movement"]["antiknockback"]
        xz_value = c.get_setting("antiknockback", "xz", 0.8)
        y_value  = c.get_setting("antiknockback", "y", 0.8)
        w_antikb["xz_slider"].set(xz_value)
        w_antikb["y_slider"].set(y_value)
        w_antikb["xz_label"].configure(text=f"X/Z: {xz_value:.2f}")
        w_antikb["y_label"].configure(text=f"Y: {y_value:.2f}")
        if c.get_state("antiknockback"):
            w_antikb["switch"].select()
            w_antikb["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        else:
            w_antikb["switch"].deselect()
            w_antikb["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        if self.minecraft_version == "1.21.13" and "nohurtcam" in self.widgets["Visual"]:
            w_nohurtcam = self.widgets["Visual"]["nohurtcam"]
            if c.get_state("nohurtcam"):
                w_nohurtcam["switch"].select()
                w_nohurtcam["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_nohurtcam["switch"].deselect()
                w_nohurtcam["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        w_streamprotect = self.widgets["Misc"]["streamprotect"]
        if c.get_state("streamprotect"):
            w_streamprotect["switch"].select()
            w_streamprotect["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            self.attributes('-topmost', True)
        else:
            w_streamprotect["switch"].deselect()
            self.attributes('-topmost', False)
        if "truesight" in self.widgets["Visual"]:
            w_truesight = self.widgets["Visual"]["truesight"]
            if c.get_state("truesight"):
                w_truesight["switch"].select()
                w_truesight["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_truesight["switch"].deselect()
        if "timechanger" in self.widgets["Visual"]:
            w_timechanger = self.widgets["Visual"]["timechanger"]
            time_value  = self.config.get_setting("timechanger", "time", 1000)
            preset_name = self.config.get_setting("timechanger", "preset", "Day")
            w_timechanger["slider"].set(time_value)
            w_timechanger["preset_var"].set(preset_name)
            w_timechanger["time_label"].configure(text=f"Time: {int(time_value)} ({preset_name})")
            if self.config.get_state("timechanger"):
                w_timechanger["switch"].select()
                w_timechanger["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_timechanger["switch"].deselect()
        if "fastitem" in self.widgets.get("Player", {}):
            w_fastitem = self.widgets["Player"]["fastitem"]
            if c.get_state("fastitem"):
                w_fastitem["switch"].select()
                w_fastitem["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_fastitem["switch"].deselect()
                w_fastitem["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
        if self.version_config.get('jumpreset_supported', False) and "jumpreset" in self.widgets["Movement"]:
            w_jumpreset  = self.widgets["Movement"]["jumpreset"]
            timing_value = self.config.get_setting("jumpreset", "timing", 0.54)
            jump_key     = self.config.get_keybind("jump") or "space"
            w_jumpreset["slider"].set(timing_value)
            w_jumpreset["timing_label"].configure(text=f"Jump Hold Time: {timing_value:.2f}s")
            w_jumpreset["jump_key_entry"].configure(state="normal")
            w_jumpreset["jump_key_entry"].delete(0, "end")
            w_jumpreset["jump_key_entry"].insert(0, jump_key.upper())
            w_jumpreset["jump_key_entry"].configure(state="readonly")
            if self.config.get_state("jumpreset"):
                w_jumpreset["switch"].select()
                w_jumpreset["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])
            else:
                w_jumpreset["switch"].deselect()
        if "aimassist" in self.widgets["Combat"]:
            w_aa = self.widgets["Combat"]["aimassist"]
 
            saved_player_yoff = self.config.get_setting("aimassist", "y_offset_player", 0.22)
            saved_player_yoff = max(0.0, min(1.0, float(saved_player_yoff)))
            w_aa["player_yoff_slider"].set(saved_player_yoff)
            w_aa["player_yoff_lbl"].configure(text=f"Player Y Offset: {saved_player_yoff:.2f}")
            actual_player = 2.60 - saved_player_yoff * 1.50
            self.aimassist_controller.set_y_offset_player(actual_player)

            saved_other_yoff = self.config.get_setting("aimassist", "y_offset_other", 0.53)
            saved_other_yoff = max(0.0, min(1.0, float(saved_other_yoff)))
            w_aa["other_yoff_slider"].set(saved_other_yoff)
            w_aa["other_yoff_lbl"].configure(text=f"Other Entity Y Offset: {saved_other_yoff:.2f}")
            actual_other = 1.50 - saved_other_yoff * 1.70
            self.aimassist_controller.set_y_offset_other(actual_other)
 
            saved_auto_click_only = self.config.get_setting("aimassist", "aim_only_on_autoclicker", False)
            if "auto_click_var" in w_aa:
                w_aa["auto_click_var"].set(saved_auto_click_only)
 
            saved_aim_player = self.config.get_setting("aimassist", "aim_player", True)
            saved_aim_other  = self.config.get_setting("aimassist", "aim_other",  False)
            if "player_var" in w_aa:
                w_aa["player_var"].set(saved_aim_player)
            if "other_var" in w_aa:
                w_aa["other_var"].set(saved_aim_other)
            self.aimassist_controller.set_target_mode(saved_aim_player, saved_aim_other)
 
            if c.get_state("aimassist"):
                w_aa["switch"].select()
                w_aa["status"].configure(text="Inactive",
                                         text_color=COLORS["text_secondary"])
            else:
                w_aa["switch"].deselect()
        if "systemtray" in self.widgets["Misc"]:
            w_tray = self.widgets["Misc"]["systemtray"]
            if self.config.get_state("systemtray", False):
                w_tray["switch"].select()
                success = self.systemtray_controller.start()
                if success:
                    w_tray["status"].configure(text="Active", text_color=COLORS["success"])
                else:
                    w_tray["switch"].deselect()
                    w_tray["status"].configure(text="Failed to create tray", text_color='#ff5252')
                    self.config.set_state("systemtray", False)
            else:
                w_tray["switch"].deselect()
                w_tray["status"].configure(text="Inactive", text_color=COLORS["text_secondary"])

    def on_closing(self):
        self._is_closing = True
        if self._version_check_timer:
            self.after_cancel(self._version_check_timer)
        if hasattr(self, 'check_process_timer') and self.check_process_timer:
            self.after_cancel(self.check_process_timer)
        if hasattr(self, 'antikb_controller') and self.antikb_controller and self.antikb_controller.initialized:
            if self.antikb_controller.is_active:
                self.antikb_controller.disable_antiknockback()
            self.antikb_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'reach_controller') and self.reach_controller and self.reach_controller.initialized:
            if self.reach_controller.is_active:
                self.reach_controller.disable_reach()
            self.reach_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'hitbox_controller') and self.hitbox_controller and self.hitbox_controller.initialized:
            if self.hitbox_controller.is_active:
                self.hitbox_controller.disable_hitbox()
            self.hitbox_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'zoom_controller') and self.zoom_controller and self.zoom_controller.initialized:
            if self.zoom_controller.is_active:
                self.zoom_controller.stop(is_app_closing=True)
            self.zoom_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'brightness_controller') and self.brightness_controller and self.brightness_controller.initialized:
            if self.brightness_controller.is_active:
                self.brightness_controller.stop(is_app_closing=True)
            self.brightness_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'coordinates_controller') and self.coordinates_controller and self.coordinates_controller.initialized:
            if self.coordinates_controller.is_active:
                self.coordinates_controller.stop(is_app_closing=True)
            self.coordinates_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'autoclicker_controller') and self.autoclicker_controller and self.autoclicker_controller.is_active:
            self.autoclicker_controller.stop(is_app_closing=True)
            self.autoclicker_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'streamprotect_controller') and self.streamprotect_controller:
            self.streamprotect_controller.stop_keybind_monitoring()
            self.streamprotect_controller._unregister_hotkey()
        if hasattr(self, 'speed_controller') and self.speed_controller and self.speed_controller.initialized:
            if self.speed_controller.is_active:
                self.speed_controller.stop(is_app_closing=True)
            self.speed_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'sprint_controller') and self.sprint_controller and self.sprint_controller.initialized:
            if self.sprint_controller.is_active:
                self.sprint_controller.stop(is_app_closing=True)
            self.sprint_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'truesight_controller') and self.truesight_controller and self.truesight_controller.initialized:
            if self.truesight_controller.is_active:
                self.truesight_controller.stop(is_app_closing=True)
            self.truesight_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'timechanger_controller') and self.timechanger_controller and self.timechanger_controller.initialized:
            if self.timechanger_controller.is_active:
                self.timechanger_controller.stop(is_app_closing=True)
            self.timechanger_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'fastitem_controller') and self.fastitem_controller and self.fastitem_controller.initialized:
            if self.fastitem_controller.is_active:
                self.fastitem_controller.stop(is_app_closing=True)
            self.fastitem_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'jumpreset_controller') and self.jumpreset_controller:
            self.jumpreset_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'systemtray_controller'):
            self.systemtray_controller.reset_to_default(is_app_closing=True)
        if self.minecraft_version == "1.21.13" and hasattr(self, 'nohurtcam_controller') and self.nohurtcam_controller and self.nohurtcam_controller.initialized:
            if self.nohurtcam_controller.is_active:
                self.nohurtcam_controller.stop(is_app_closing=True)
            self.nohurtcam_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'triggerbot_controller') and self.triggerbot_controller:
            self.triggerbot_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'microaim_controller') and self.microaim_controller:
            self.microaim_controller.reset_to_default(is_app_closing=True)
        if hasattr(self, 'aimassist_controller') and self.aimassist_controller:
            self.aimassist_controller.reset_to_default(is_app_closing=True)
        reset_shared_detector()
        reset_shared_menu_monitor()
        reset_shared_window_monitor()
        reset_shared_block_detector()
        reset_shared_world_monitor()
        reset_click_priority()
        reset_scheduler()
        try:
            self.attributes('-topmost', False)
            if hasattr(self, 'keybind_window') and self.keybind_window and self.keybind_window.winfo_exists():
                self.keybind_window.attributes('-topmost', False)
        except:
            pass
        self.destroy()

if __name__ == "__main__":
    app = MinecraftModApp()
    app.mainloop()