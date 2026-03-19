"""
KangPaket — App settings manager (reads/writes data/settings.json).
"""
import json
import os

from app.config import SETTINGS_FILE

DEFAULT_SETTINGS: dict = {
    "default_timeout": 30.0,
    "follow_redirects": True,
    "verify_ssl": True,
    "max_response_size_mb": 10,
    "theme": "dark",
    "font_size": 13,
    "default_collection": "Default",
    "proxy_enabled": False,
    "proxy_http": "",
    "proxy_https": "",
}


class SettingsManager:
    def __init__(self) -> None:
        self._settings: dict = dict(DEFAULT_SETTINGS)
        self.load_settings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_settings(self) -> dict:
        """Load settings from disk. Missing keys fall back to defaults."""
        if not os.path.exists(SETTINGS_FILE):
            self.save_settings(self._settings)
            return self._settings

        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge: loaded values override defaults, but keep missing defaults
            merged = dict(DEFAULT_SETTINGS)
            merged.update(loaded)
            self._settings = merged
        except (json.JSONDecodeError, OSError) as e:
            print(f"[SettingsManager] Failed to load settings: {e}. Using defaults.")
            self._settings = dict(DEFAULT_SETTINGS)

        return self._settings

    def save_settings(self, settings: dict | None = None) -> None:
        """Save settings to disk."""
        if settings is not None:
            self._settings = settings
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except OSError as e:
            print(f"[SettingsManager] Failed to save settings: {e}")

    def get(self, key: str, default=None):
        """Get a setting value by key."""
        return self._settings.get(key, default)

    def set(self, key: str, value) -> None:
        """Set a setting value and persist to disk."""
        self._settings[key] = value
        self.save_settings()

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults and persist."""
        self._settings = dict(DEFAULT_SETTINGS)
        self.save_settings()

    @property
    def all(self) -> dict:
        return dict(self._settings)
