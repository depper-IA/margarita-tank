"""Wiring the statusLine bridge into Claude settings.

install_hooks() points settings.statusLine at the bridge, saving the user's
original statusLine so the bridge can chain it and uninstall can restore it.
"""

import json
import sys

import pytest

from clawd_tank_menubar import hooks


@pytest.fixture
def settings_path(sandbox_home):
    return hooks.CLAUDE_SETTINGS_PATH


@pytest.fixture
def state_path():
    return hooks.CLAWD_DIR / hooks.STATUSLINE_STATE_NAME


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _read(path):
    return json.loads(path.read_text())


USER_STATUSLINE = {"type": "command", "command": "~/.claude/statusline.sh", "padding": 2}


def test_command_is_the_script_path_on_posix_and_names_interpreter_on_windows():
    assert hooks.build_statusline_command("darwin", False, "/py", "/h/.clawd-tank/statusline_bridge.py") \
        == "/h/.clawd-tank/statusline_bridge.py"
    assert hooks.build_statusline_command("win32", False, "C:\\py\\python.exe", "C:\\h\\statusline_bridge.py") \
        == '"C:\\py\\python.exe" "C:\\h\\statusline_bridge.py"'


def test_frozen_windows_command_runs_the_bundled_statusline_exe():
    cmd = hooks.build_statusline_command(
        "win32", True, "C:\\Apps\\Margarita Tank\\MargaritaTank.exe", "C:\\h\\statusline_bridge.py")
    assert cmd == '"C:\\Apps\\Margarita Tank\\margarita-statusline.exe"'


def test_posix_command_quotes_paths_with_spaces():
    cmd = hooks.build_statusline_command("darwin", False, "/py", "/Users/a b/.clawd-tank/statusline_bridge.py")
    assert cmd == "'/Users/a b/.clawd-tank/statusline_bridge.py'"


def test_install_script_writes_bridge(sandbox_home):
    hooks.install_statusline_bridge_script()
    assert hooks.STATUSLINE_SCRIPT_PATH.read_text(encoding="utf-8") == hooks.STATUSLINE_BRIDGE_SCRIPT
    if sys.platform != "win32":
        assert hooks.STATUSLINE_SCRIPT_PATH.stat().st_mode & 0o111


def test_install_without_existing_statusline_sets_bridge_alone(settings_path, state_path):
    assert hooks.install_hooks() is True
    settings = _read(settings_path)
    assert settings["statusLine"] == {"type": "command", "command": hooks.STATUSLINE_COMMAND}
    assert not state_path.exists()


def test_install_wraps_user_statusline_and_saves_original(settings_path, state_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE, "model": "opus"})
    hooks.install_hooks()
    settings = _read(settings_path)
    assert settings["statusLine"]["command"] == hooks.STATUSLINE_COMMAND
    assert settings["statusLine"]["type"] == "command"
    assert settings["model"] == "opus"
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}


def test_install_is_idempotent_and_never_wraps_the_bridge_in_itself(settings_path, state_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    first = settings_path.read_text()
    hooks.install_hooks()
    hooks.install_hooks()
    assert settings_path.read_text() == first
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}


def test_reinstall_picks_up_a_statusline_the_user_changed_since(settings_path, state_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    newer = {"type": "command", "command": "other-line"}
    settings = _read(settings_path)
    settings["statusLine"] = newer
    _write(settings_path, settings)
    hooks.install_hooks()
    assert _read(state_path) == {"statusLine": newer}
    assert _read(settings_path)["statusLine"]["command"] == hooks.STATUSLINE_COMMAND


def test_stale_bridge_command_is_refreshed_without_losing_original(settings_path, state_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    settings = _read(settings_path)
    stale = f'"C:\\gone\\python.exe" "{hooks.STATUSLINE_SCRIPT_PATH}"'
    settings["statusLine"]["command"] = stale
    _write(settings_path, settings)
    assert hooks.are_hooks_installed() is False
    hooks.install_hooks()
    assert _read(settings_path)["statusLine"]["command"] == hooks.STATUSLINE_COMMAND
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}


def test_are_hooks_installed_requires_the_statusline_bridge(settings_path):
    hooks.install_hooks()
    assert hooks.are_hooks_installed() is True
    settings = _read(settings_path)
    del settings["statusLine"]
    _write(settings_path, settings)
    assert hooks.are_hooks_installed() is False


def test_are_hooks_installed_false_when_statusline_is_users_own(settings_path):
    hooks.install_hooks()
    settings = _read(settings_path)
    settings["statusLine"] = USER_STATUSLINE
    _write(settings_path, settings)
    assert hooks.are_hooks_installed() is False


def test_statusline_that_already_writes_the_cache_is_still_wrapped(settings_path, state_path):
    mine = {"type": "command", "command": "~/.claude/statusline.sh # writes ~/.clawd-tank/statusline-cache.json"}
    _write(settings_path, {"statusLine": mine})
    hooks.install_hooks()
    assert _read(state_path) == {"statusLine": mine}


def test_uninstall_restores_original_statusline_exactly(settings_path, state_path):
    original = {"statusLine": USER_STATUSLINE, "env": {"A": "1"}, "model": "opus"}
    _write(settings_path, original)
    hooks.install_hooks()
    assert hooks.uninstall_hooks() is True
    assert _read(settings_path) == original
    assert not state_path.exists()


def test_uninstall_removes_statusline_when_there_was_none(settings_path):
    _write(settings_path, {"model": "opus"})
    hooks.install_hooks()
    hooks.uninstall_hooks()
    assert _read(settings_path) == {"model": "opus"}


def test_uninstall_leaves_a_statusline_the_user_set_after_install(settings_path, state_path):
    hooks.install_hooks()
    settings = _read(settings_path)
    settings["statusLine"] = USER_STATUSLINE
    _write(settings_path, settings)
    hooks.uninstall_hooks()
    assert _read(settings_path)["statusLine"] == USER_STATUSLINE


def test_uninstall_without_state_file_drops_our_statusline(settings_path, state_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    state_path.unlink()
    hooks.uninstall_hooks()
    assert "statusLine" not in _read(settings_path)


def test_uninstall_is_idempotent(settings_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    hooks.uninstall_hooks()
    first = settings_path.read_text()
    assert hooks.uninstall_hooks() is True
    assert settings_path.read_text() == first


def test_unparseable_settings_leave_state_untouched(settings_path, state_path):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{nope")
    assert hooks.install_hooks() is False
    assert settings_path.read_text() == "{nope"
    assert not state_path.exists()
