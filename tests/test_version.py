"""Version has one source (app/version.py); pyproject and config must agree."""
import re
from pathlib import Path

from app import config
from app.version import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_config_uses_version_module():
    assert config.APP_VERSION == __version__


def test_version_is_semver_and_not_placeholder():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert __version__ != "0.0.0"


def test_pyproject_matches():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m and m.group(1) == __version__
