"""The "Claude Code Mod (panel)" menu item in both tray views.

The macOS view is built for real with rumps against a stand-in app object. The
Windows view needs pystray, which is not installed off Windows, so it runs
against a minimal stand-in recording the menu structure it is given.
"""
import importlib
import sys
import types
from types import SimpleNamespace

import pytest

from clawd_tank_menubar.controller import TrayState

LABEL = "Claude Code Mod (panel)"
HOOKS_LABEL = "Install Claude Code Hooks"


def _state(**overrides) -> TrayState:
    values = dict(
        icon="connected", ble_enabled=True, ble_connected=True, sim_enabled=True,
        sim_connected=True, sim_window_visible=True, sim_pinned=True, brightness=102,
        brightness_enabled=True, session_timeout_seconds=300, hooks_installed=True,
        login_enabled=False, claude_mod_enabled=False,
    )
    values.update(overrides)
    return TrayState(**values)


class _Controller:
    """Just what the views read at build time, plus a record of clicks."""

    ble_enabled = sim_enabled = sim_window_visible = sim_pinned = True
    session_timeout_seconds = 300
    hooks_installed = True
    login_enabled = False

    def __init__(self, claude_mod_enabled=False):
        self.claude_mod_enabled = claude_mod_enabled
        self.calls = []

    def toggle_claude_mod(self):
        self.calls.append("toggle_claude_mod")

    def install_hooks(self):
        self.calls.append("install_hooks")

    def __getattr__(self, name):  # every other action is a recorded no-op
        return lambda *a, **k: self.calls.append(name)


# --- macOS ----------------------------------------------------------------------


@pytest.fixture
def mac_view():
    rumps = pytest.importorskip("rumps")
    from clawd_tank_menubar.rumps_view import RumpsTrayView

    app = SimpleNamespace(menu=None, icon=None, template=None, title=None)
    view = RumpsTrayView(app)
    return view, app, rumps


def _mac_item(app, title):
    return next(i for i in app.menu if i is not None and i.title == title)


def test_mac_menu_lists_the_mod_item_right_after_the_hooks_item(mac_view):
    view, app, _rumps = mac_view
    view.build(_Controller())
    titles = [i.title if i is not None else None for i in app.menu]
    assert titles.index(LABEL) == titles.index(HOOKS_LABEL) + 1


@pytest.mark.parametrize("enabled", [False, True])
def test_mac_mod_item_starts_with_the_saved_choice(mac_view, enabled):
    view, app, _rumps = mac_view
    view.build(_Controller(claude_mod_enabled=enabled))
    assert bool(_mac_item(app, LABEL).state) is enabled


def test_mac_clicking_the_mod_item_toggles_through_the_controller(mac_view):
    view, app, _rumps = mac_view
    controller = _Controller()
    view.build(controller)
    item = _mac_item(app, LABEL)
    item.callback(item)
    assert controller.calls == ["toggle_claude_mod"]


def test_mac_repaint_follows_the_controller_state(mac_view):
    view, app, _rumps = mac_view
    view.build(_Controller())
    item = _mac_item(app, LABEL)

    view._paint(_state(claude_mod_enabled=True))
    assert bool(item.state) is True
    view._paint(_state(claude_mod_enabled=False))
    assert bool(item.state) is False


# --- Windows --------------------------------------------------------------------


class _FakeMenu:
    SEPARATOR = object()

    def __init__(self, *items):
        self.items = items


class _FakeMenuItem:
    def __init__(self, text, action, checked=None, radio=False, default=False,
                 visible=True, enabled=True):
        self.text, self.action, self.checked, self.enabled = text, action, checked, enabled


class _FakeIcon:
    def __init__(self, name, icon=None, title=None, menu=None):
        self.name, self.icon, self.title, self.menu = name, icon, title, menu

    def update_menu(self):
        pass


@pytest.fixture
def windows_view(monkeypatch):
    """windows_tray imported against a fake pystray, and forgotten again after."""
    fake = types.ModuleType("pystray")
    fake.Menu, fake.MenuItem, fake.Icon = _FakeMenu, _FakeMenuItem, _FakeIcon
    monkeypatch.setitem(sys.modules, "pystray", fake)
    monkeypatch.delitem(sys.modules, "clawd_tank_menubar.windows_tray", raising=False)
    import clawd_tank_menubar as package
    monkeypatch.delattr(package, "windows_tray", raising=False)
    module = importlib.import_module("clawd_tank_menubar.windows_tray")
    yield module
    sys.modules.pop("clawd_tank_menubar.windows_tray", None)
    if hasattr(package, "windows_tray"):
        delattr(package, "windows_tray")


def _win_items(view):
    return [i for i in view._icon.menu.items if isinstance(i, _FakeMenuItem)]


def _win_item(view, text):
    return next(i for i in _win_items(view) if i.text == text)


def test_windows_menu_lists_the_mod_item_right_after_the_hooks_item(windows_view):
    view = windows_view.WindowsTrayView()
    view.build(_Controller())
    texts = [i.text for i in _win_items(view)]
    assert texts.index(LABEL) == texts.index(HOOKS_LABEL) + 1


def test_windows_mod_item_is_checked_from_the_rendered_state(windows_view):
    view = windows_view.WindowsTrayView()
    view.build(_Controller())
    item = _win_item(view, LABEL)
    assert item.checked(item) is False  # nothing rendered yet

    view.render(_state(claude_mod_enabled=True))
    assert item.checked(item) is True
    view.render(_state(claude_mod_enabled=False))
    assert item.checked(item) is False


def test_windows_clicking_the_mod_item_toggles_through_the_controller(windows_view):
    view = windows_view.WindowsTrayView()
    controller = _Controller()
    view.build(controller)
    item = _win_item(view, LABEL)
    item.action(item)
    assert controller.calls == ["toggle_claude_mod"]
