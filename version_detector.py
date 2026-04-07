import subprocess
import json
import re
from subprocess import CREATE_NO_WINDOW

class MinecraftVersionDetector:
    SUPPORTED_VERSION_SERIES = {
        "1.21.130": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.21.13"
        },
        "1.21.131": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.21.13"
        },
        "1.21.132": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.21.13"
        },
        "1.26.2": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.26.2"
        },
        "1.26.101": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.26.101"
        },
        "1.26.201": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.26.201"
        },
        "1.26.301": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20',
            "shadow_pattern": b'\xF3\x44\x0F\x11\x42\x10',
            "shadow_patch_type": "default",
            "shadow_value_on": 0.6,
            "shadow_value_off": 0.6,
            "shadow_patch_length": 6,
            "jumpreset_supported": True,
            "series": "1.26.301"
        },
        "1.26.1004": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20\x5F',
            "hitbox_patch_length": 5,
            "hitbox_patch_type": "default",
            "jumpreset_supported": True,
            "series": "1.26.1004"
        },
        "1.26.1101": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20\x5F',
            "hitbox_patch_length": 5,
            "hitbox_patch_type": "default",
            "jumpreset_supported": True,
            "series": "1.26.1101"
        },
        "1.26.1202": {
            "speed_pattern": b'\xF3\x0F\x10\x40\x7C\xF3\x0F\x11\x44\x24\x28',
            "speed_original_length": 11,
            "hitbox_pattern": b'\xF3\x0F\x10\x40\x18\x48\x83\xC4\x20\x5F',
            "hitbox_patch_length": 5,
            "hitbox_patch_type": "default",
            "jumpreset_supported": True,
            "series": "1.26.1202"
        },
    }

    FOUR_DIGIT_PATCHES = {"1004", "1101", "1202"}

    JUMPRESET_EXACT_VERSIONS = [
        "1.21.130", "1.21.131", "1.21.132",
        "1.26.2", "1.26.101", "1.26.201", "1.26.301",
        "1.26.1004", "1.26.1101", "1.26.1202",
    ]

    DISPLAY_SUPPORTED_VERSIONS = [
        "1.21.130",
        "1.26.20",
        "1.26.100",
        "1.26.201",
        "1.26.301",
        "1.26.1004",
        "1.26.1101",
        "1.26.1202",
    ]

    @staticmethod
    def is_jumpreset_supported(full_version):
        if not full_version:
            return False
        normalized = MinecraftVersionDetector.parse_version(full_version)
        if not normalized:
            return False
        return normalized in MinecraftVersionDetector.JUMPRESET_EXACT_VERSIONS

    @staticmethod
    def get_installed_version():
        powershell_command = (
            'Get-AppxPackage -Name "Microsoft.MinecraftUWP" | '
            'Select-Object Version | '
            'ConvertTo-Json'
        )
        try:
            result = subprocess.run(
                ["powershell", "-Command", powershell_command],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8',
                timeout=10,
                creationflags=CREATE_NO_WINDOW
            )
            json_output = result.stdout.strip()
            if not json_output:
                return None
            packages = json.loads(json_output)
            if not isinstance(packages, list):
                packages = [packages]
            for package in packages:
                if 'Version' in package:
                    return package['Version']
            return None
        except Exception:
            return None

    @staticmethod
    def parse_version(version_string):
        if not version_string:
            return None
        match4 = re.match(r'(\d+\.\d+\.)(\d{4})', version_string.strip())
        if match4 and match4.group(2) in MinecraftVersionDetector.FOUR_DIGIT_PATCHES:
            return match4.group(1) + match4.group(2)
        match = re.match(r'(\d+\.\d+\.)(\d{1,3})', version_string.strip())
        if match:
            prefix = match.group(1)
            patch  = match.group(2)
            full   = prefix + patch
            return full
        return None

    @classmethod
    def is_version_supported(cls, version_string):
        series_version = cls.parse_version(version_string)
        if not series_version:
            return False, None, None
        if series_version in cls.SUPPORTED_VERSION_SERIES:
            return True, series_version, cls.SUPPORTED_VERSION_SERIES[series_version]
        return False, series_version, None

    @classmethod
    def get_version_config(cls, version_string):
        _, _, config = cls.is_version_supported(version_string)
        if config:
            config_copy = config.copy()
            config_copy['jumpreset_supported'] = cls.is_jumpreset_supported(version_string)
            return config_copy
        return config

    @classmethod
    def check_compatibility(cls):
        installed = cls.get_installed_version()

        if not installed:
            return {
                'installed_version': None,
                'series_version': None,
                'supported': False,
                'config': None,
                'jumpreset_supported': False,
                'message': 'Minecraft Bedrock Edition not found'
            }

        supported, series_version, config = cls.is_version_supported(installed)
        display_version = cls.parse_version(installed) or installed
        jumpreset_supported = cls.is_jumpreset_supported(installed)

        if config:
            config = config.copy()
            config['jumpreset_supported'] = jumpreset_supported
            series_version = config.get('series', series_version)

        return {
            'installed_version': display_version,
            'series_version': series_version,
            'supported': supported,
            'config': config,
            'jumpreset_supported': jumpreset_supported,
            'message': ''
        }

if __name__ == "__main__":
    result = MinecraftVersionDetector.check_compatibility()
    print(json.dumps(result, indent=2, ensure_ascii=False))