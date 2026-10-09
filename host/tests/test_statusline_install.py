"""Wiring the statusLine bridge into Claude settings.

install_hooks() points settings.statusLine at the bridge, saving the user's
original statusLine so the bridge can chain it and uninstall can restore it.
"""

import json
import shlex
import sys

import pytest

from clawd_tank_menubar import hooks


@pytest.fixture
def settings_path(sandbox_home):
    return hooks.CLAUDE_SETTINGS_PATH


@pytest.fixture
def state_path():
    return hooks.CLAWD_DIR / hooks.STATUSLINE_STATE_NAME


@pytest.fixture
def command_path():
    """The plain-text copy of the saved command, which the sh bridge reads."""
    return hooks.CLAWD_DIR / hooks.STATUSLINE_COMMAND_NAME


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _read(path):
    return json.loads(path.read_text())


USER_STATUSLINE = {"type": "command", "command": "~/.claude/statusline.sh", "padding": 2}


def test_command_runs_the_sh_bridge_on_posix_and_names_interpreter_on_windows():
    for platform in ("darwin", "linux"):
        assert hooks.build_statusline_command(
            platform, False, "/py", "/h/.clawd-tank/statusline_bridge.sh") \
            == "/bin/sh /h/.clawd-tank/statusline_bridge.sh"
    assert hooks.build_statusline_command("win32", False, "C:\\py\\python.exe", "C:\\h\\statusline_bridge.py") \
        == '"C:\\py\\python.exe" "C:\\h\\statusline_bridge.py"'


def test_frozen_windows_command_runs_the_bundled_statusline_exe():
    cmd = hooks.build_statusline_command(
        "win32", True, "C:\\Apps\\Margarita Tank\\MargaritaTank.exe", "C:\\h\\statusline_bridge.py")
    assert cmd == '"C:\\Apps\\Margarita Tank\\margarita-statusline.exe"'


def test_posix_command_quotes_paths_with_spaces():
    cmd = hooks.build_statusline_command("darwin", False, "/py", "/Users/a b/.clawd-tank/statusline_bridge.sh")
    assert cmd == "/bin/sh '/Users/a b/.clawd-tank/statusline_bridge.sh'"


def test_the_bridge_script_is_sh_on_posix_and_python_on_windows():
    assert hooks.build_statusline_script("darwin") is hooks.STATUSLINE_BRIDGE_SH
    assert hooks.build_statusline_script("linux") is hooks.STATUSLINE_BRIDGE_SH
    assert hooks.build_statusline_script("win32") is hooks.STATUSLINE_BRIDGE_SCRIPT
    assert hooks.STATUSLINE_SCRIPT_PATH.name == (
        "statusline_bridge.py" if sys.platform == "win32" else "statusline_bridge.sh")


def test_install_script_writes_bridge(sandbox_home):
    hooks.install_statusline_bridge_script()
    expected = hooks.build_statusline_script(sys.platform)
    assert hooks.STATUSLINE_SCRIPT_PATH.read_text(encoding="utf-8") == expected
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


def test_uninstall_keeps_state_when_the_settings_write_fails(settings_path, state_path, monkeypatch):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()

    def boom(_settings):
        raise OSError("disk full")

    monkeypatch.setattr(hooks, "_write_settings_atomic", boom)
    with pytest.raises(OSError):
        hooks.uninstall_hooks()
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}


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


def test_install_saves_the_original_command_as_plain_text_too(settings_path, state_path, command_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    assert command_path.read_text(encoding="utf-8") == USER_STATUSLINE["command"]
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}


def test_plain_text_command_is_verbatim_even_with_quotes_and_newlines(settings_path, command_path):
    tricky = 'printf \'%s\' "a \\"b\\" \\\\ $HOME \u00e9"\necho done'
    _write(settings_path, {"statusLine": {"type": "command", "command": tricky}})
    hooks.install_hooks()
    assert command_path.read_bytes() == tricky.encode("utf-8")


def test_no_original_means_no_plain_text_command(settings_path, state_path, command_path):
    hooks.install_hooks()
    assert not command_path.exists()
    # A leftover from an earlier install must not chain a command the user dropped.
    command_path.write_text("stale")
    hooks.install_hooks()
    assert not command_path.exists()


def test_original_without_a_command_has_no_plain_text_command(settings_path, command_path):
    _write(settings_path, {"statusLine": {"type": "static", "text": "hi"}})
    hooks.install_hooks()
    assert not command_path.exists()


def test_reinstall_follows_a_statusline_the_user_changed_since_in_the_plain_text_copy(
        settings_path, command_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    settings = _read(settings_path)
    settings["statusLine"] = {"type": "command", "command": "other-line"}
    _write(settings_path, settings)
    hooks.install_hooks()
    assert command_path.read_text(encoding="utf-8") == "other-line"


def test_a_missing_plain_text_copy_counts_as_outdated_and_is_restored(settings_path, command_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    assert hooks.are_hooks_installed() is True
    command_path.unlink()
    assert hooks.are_hooks_installed() is False
    hooks.install_hooks()
    assert command_path.read_text(encoding="utf-8") == USER_STATUSLINE["command"]
    assert hooks.are_hooks_installed() is True


def test_uninstall_removes_the_plain_text_copy_with_the_saved_original(
        settings_path, state_path, command_path):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()
    hooks.uninstall_hooks()
    assert not command_path.exists()
    assert not state_path.exists()


def test_uninstall_keeps_the_plain_text_copy_when_the_settings_write_fails(
        settings_path, command_path, monkeypatch):
    _write(settings_path, {"statusLine": USER_STATUSLINE})
    hooks.install_hooks()

    def boom(_settings):
        raise OSError("disk full")

    monkeypatch.setattr(hooks, "_write_settings_atomic", boom)
    with pytest.raises(OSError):
        hooks.uninstall_hooks()
    assert command_path.read_text(encoding="utf-8") == USER_STATUSLINE["command"]


# --- migration from the python3 bridge (POSIX) --------------------------------
#
# Before the sh bridge, POSIX settings.json pointed statusLine straight at
# ~/.clawd-tank/statusline_bridge.py. Such a value is ours, not the user's own:
# it must be replaced, never saved as the "original" (the new bridge would chain
# into the old one), and the user's real original must survive the move.

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX settings only")


def _legacy_command():
    return shlex.quote(str(hooks.STATUSLINE_SCRIPT_PATH.with_name("statusline_bridge.py")))


@posix_only
def test_a_settings_file_wired_to_the_python_bridge_is_migrated(
        settings_path, state_path, command_path):
    _write(settings_path, {"statusLine": {**USER_STATUSLINE, "command": _legacy_command()}})
    _write(state_path, {"statusLine": USER_STATUSLINE})
    assert hooks.are_hooks_installed() is False  # so the start-up auto-update runs

    assert hooks.install_hooks() is True

    assert _read(settings_path)["statusLine"] == {
        **USER_STATUSLINE, "type": "command", "command": hooks.STATUSLINE_COMMAND}
    assert _read(state_path) == {"statusLine": USER_STATUSLINE}  # not the old bridge
    assert command_path.read_text(encoding="utf-8") == USER_STATUSLINE["command"]
    assert hooks.are_hooks_installed() is True


@posix_only
def test_migration_without_a_saved_original_just_rewires(settings_path, state_path, command_path):
    _write(settings_path, {"statusLine": {"type": "command", "command": _legacy_command()}})
    hooks.install_hooks()
    assert _read(settings_path)["statusLine"]["command"] == hooks.STATUSLINE_COMMAND
    assert not state_path.exists()
    assert not command_path.exists()


@posix_only
def test_a_legacy_command_is_recognised_under_a_folder_with_spaces(monkeypatch):
    # The old command shell-quoted its path, so a home with spaces gave '...'.
    from pathlib import Path
    monkeypatch.setattr(
        hooks, "STATUSLINE_SCRIPT_PATH", Path("/Users/a b/.clawd-tank/statusline_bridge.sh"))
    legacy = "'/Users/a b/.clawd-tank/statusline_bridge.py'"
    assert hooks._statusline_is_ours({"type": "command", "command": legacy}) is True
    assert hooks._statusline_is_ours({"type": "command", "command": legacy + " --x"}) is True
    # A wrapper that merely mentions the old script is the user's own.
    assert hooks._statusline_is_ours({"type": "command", "command": "cat " + legacy}) is False


@posix_only
def test_uninstall_restores_the_original_from_a_python_bridge_wiring(settings_path, state_path):
    _write(settings_path, {"statusLine": {**USER_STATUSLINE, "command": _legacy_command()},
                           "model": "opus"})
    _write(state_path, {"statusLine": USER_STATUSLINE})
    assert hooks.uninstall_hooks() is True
    assert _read(settings_path) == {"statusLine": USER_STATUSLINE, "model": "opus"}


@posix_only
def test_the_old_python_bridge_file_goes_once_settings_point_at_the_sh_bridge(settings_path):
    legacy_script = hooks.STATUSLINE_SCRIPT_PATH.with_name("statusline_bridge.py")
    legacy_script.parent.mkdir(parents=True, exist_ok=True)
    legacy_script.write_text("#!/usr/bin/env python3\n")
    _write(settings_path, {"statusLine": {"type": "command", "command": _legacy_command()}})
    hooks.install_hooks()
    assert not legacy_script.exists()


@posix_only
def test_the_old_python_bridge_file_stays_when_settings_cannot_be_updated(settings_path):
    legacy_script = hooks.STATUSLINE_SCRIPT_PATH.with_name("statusline_bridge.py")
    legacy_script.parent.mkdir(parents=True, exist_ok=True)
    legacy_script.write_text("#!/usr/bin/env python3\n")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{nope")  # unparseable: install refuses, the wiring is untouched
    assert hooks.install_hooks() is False
    assert legacy_script.exists()


def test_windows_spec_and_release_check_ship_the_statusline_exe():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    spec = (root / "host" / "windows" / "margarita_tank.spec").read_text(encoding="utf-8")
    release = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert f'STATUSLINE_NAME = "{hooks.STATUSLINE_EXE_NAME[:-4]}"' in spec
    assert hooks.STATUSLINE_EXE_NAME in release
