"""
KangPaket — Entry point.
"""
import sys
from app.ui.app_window import AppWindow
from app.core.settings_manager import SettingsManager


def main() -> None:
    settings = SettingsManager()
    app = AppWindow(settings)
    app.run()


if __name__ == "__main__":
    main()
