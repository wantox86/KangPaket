"""
KangPaket — Single source of truth for the app version.

Plain constant on purpose: it is imported like any other module, so it is
bundled by PyInstaller automatically (unlike importlib.metadata, which needs
the dist-info and falls back to "0.0.0" in a frozen build).
pyproject.toml carries the same number; tests/test_version.py keeps them in sync.
"""

__version__ = "1.1.0"
