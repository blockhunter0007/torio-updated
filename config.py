import json
import os
import threading
import time
from typing import Any


class ConfigManager:
    DEFAULT_CONFIG = {
        "keybinds": {
            "brightness": "g",
            "zoom": "c",
            "sprint": "p",
            "jump": "space",
            "autoclicker_left": "mouse_left",
            "autoclicker_right": "x",
            "window_visibility": "right shift"
        },
        "feature_states": {
            "brightness": True,
            "zoom": True,
            "sprint": True,
            "coordinates": True,
            "speed": False,
            "reach": True,
            "autoclicker": True,
            "antiknockback": True,
            "hitbox": True,
            "streamprotect": False,
            "nohurtcam": False,
            "truesight": False,
            "timechanger": False,
            "fastitem": False,
            "systemtray": False,
            "aimassist": False,
            "jumpreset": True,
            "triggerbot": False,
            "microaim": True
        },
        "feature_settings": {
            "speed": {"speed": 1.0499999999999998},
            "reach": {"reach": 3.12},
            "autoclicker": {
                "left_cps": 13.399999999999999,
                "right_cps": 20.0,
                "left_enabled": True,
                "right_enabled": True,
                "jitter_enabled": True,
                "jitter_strength": 1.6
            },
            "hitbox": {"hitbox": 1.08},
            "antiknockback": {
                "xz": 0.99,
                "y": 0.98
            },
            "timechanger": {
                "time": 1000,
                "preset": "Day"
            },
            "jumpreset": {
                "timing": 0.36
            },
            "aimassist": {
                "sensitivity": 0.29,
                "max_dist": 5.3,
                "aim_only_on_autoclicker": True,
                "aim_player": True,
                "aim_other": False,
                "y_offset_player": 0.8,
                "y_offset_other": 0.8
            },
            "zoom": {
                "smooth_animation": False
            },
            "triggerbot": {
                "mode": "auto_click",
                "auto_cps": 13.4
            },
            "microaim": {
                "pulse_duration": 0.075
            }
        }
    }

    _DEBOUNCE_DELAY = 0.5

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config      = self._load_or_create()

        self._lock          = threading.Lock()
        self._dirty         = False
        self._debounce_timer: threading.Timer | None = None

    def _load_or_create(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return self._deep_merge(self.DEFAULT_CONFIG.copy(), loaded)
            except Exception:
                pass
        self._write_now(self.DEFAULT_CONFIG)
        return self.DEFAULT_CONFIG.copy()

    def _deep_merge(self, default: dict, override: dict) -> dict:
        for key, value in override.items():
            if isinstance(value, dict) and key in default and isinstance(default[key], dict):
                default[key] = self._deep_merge(default[key], value)
            else:
                default[key] = value
        return default

    def _write_now(self, data: dict):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _schedule_save(self):
        with self._lock:
            self._dirty = True
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            snapshot = json.loads(json.dumps(self.config))
            timer = threading.Timer(
                self._DEBOUNCE_DELAY,
                self._write_now,
                args=(snapshot,),
            )
            timer.daemon = True
            timer.start()
            self._debounce_timer = timer

    def _save(self, data: dict):
        self._schedule_save()

    def save(self):
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            snapshot = json.loads(json.dumps(self.config))
        self._write_now(snapshot)

    def get_keybind(self, feature: str) -> str | None:
        return self.config["keybinds"].get(feature)

    def set_keybind(self, feature: str, key: str):
        self.config["keybinds"][feature] = key
        self._schedule_save()

    def get_state(self, feature: str, default: bool = False) -> bool:
        return self.config["feature_states"].get(feature, default)

    def set_state(self, feature: str, state: bool):
        self.config["feature_states"][feature] = state
        self._schedule_save()

    def get_setting(self, feature: str, key: str, default: Any = None) -> Any:
        return self.config["feature_settings"].get(feature, {}).get(key, default)

    def set_setting(self, feature: str, key: str, value: Any):
        if feature not in self.config["feature_settings"]:
            self.config["feature_settings"][feature] = {}
        self.config["feature_settings"][feature][key] = value
        self._schedule_save()