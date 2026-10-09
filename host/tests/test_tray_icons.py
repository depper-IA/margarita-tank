# host/tests/test_tray_icons.py
"""Tests for the tray icon assets.

Windows uses colored crab icons; macOS keeps its monochrome template icons
(rumps_view.py loads crab-*.png, which rumps renders as a template image).
"""
import importlib.resources

import pytest
from PIL import Image

pytest.importorskip("pystray")

from clawd_tank_menubar import windows_tray  # noqa: E402

CRAB_ORANGE = (0xDE, 0x88, 0x6D, 255)
BADGE_RED = (0xE5, 0x3E, 0x3E, 255)

ICONS_DIR = importlib.resources.files("clawd_tank_menubar") / "icons"


def _pixels(name: str) -> set:
    return set(windows_tray._load_icon_image(name).getdata())


@pytest.mark.parametrize("state", ["disconnected", "connected", "notifications"])
def test_every_windows_icon_resolves_and_loads_as_rgba(state):
    name = windows_tray._ICON_FILES[state]
    assert (ICONS_DIR / f"{name}.png").is_file()
    img = windows_tray._load_icon_image(name)
    assert img.mode == "RGBA"
    assert img.size == (32, 32)


def test_windows_uses_the_colored_variants():
    assert all(name.startswith("win-crab-") for name in windows_tray._ICON_FILES.values())


def test_connected_icon_is_the_orange_crab():
    assert CRAB_ORANGE in _pixels(windows_tray._ICON_FILES["connected"])


def test_disconnected_icon_is_gray():
    pixels = _pixels(windows_tray._ICON_FILES["disconnected"])
    assert CRAB_ORANGE not in pixels
    assert (0x8A, 0x8A, 0x8A, 255) in pixels


def test_notifications_icon_has_a_red_badge():
    pixels = _pixels(windows_tray._ICON_FILES["notifications"])
    assert CRAB_ORANGE in pixels
    assert BADGE_RED in pixels


@pytest.mark.parametrize("name", ["crab-disconnected", "crab-connected", "crab-notifications"])
def test_macos_template_icons_are_kept(name):
    path = ICONS_DIR / f"{name}.png"
    assert path.is_file()
    with importlib.resources.as_file(path) as p:
        Image.open(p).load()
