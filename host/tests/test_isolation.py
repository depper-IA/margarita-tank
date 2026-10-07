"""Guards for tests/conftest.py: no test may touch the real home directory.

A live Margarita Tank daemon publishes its port + token in
~/.clawd-tank/endpoint.json. Constructing ClawdDaemon() in a test and stopping
it used to unlink that file, cutting every running Claude Code session off from
the real daemon. These tests pin the redirection so it cannot regress.
"""

from pathlib import Path

from clawd_tank_daemon import daemon as daemon_mod
from clawd_tank_daemon import session_store, socket_server
from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_menubar import __main__ as entry
from clawd_tank_menubar import hooks, preferences
from clawd_tank_menubar.controller import ClawdTankController

# Captured at import (collection), before the autouse fixture moves HOME.
_REAL_DIRS = (Path.home() / ".clawd-tank", Path.home() / ".claude")


def _is_under(path, root) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def test_home_env_points_into_the_sandbox(sandbox_home):
    assert _is_under(Path.home(), sandbox_home)


def test_module_level_paths_point_into_the_sandbox(sandbox_home):
    for path in (
        socket_server.CLAWD_DIR,
        socket_server.SOCKET_PATH,
        session_store.SESSIONS_PATH,
        daemon_mod.PID_PATH,
        daemon_mod.LOCK_PATH,
        daemon_mod.USAGE_CACHE_PATH,
        preferences.PREFS_PATH,
        hooks.CLAWD_DIR,
        hooks.NOTIFY_SCRIPT_PATH,
        hooks.CLAUDE_SETTINGS_PATH,
        entry.LOG_DIR,
    ):
        assert _is_under(path, sandbox_home), f"{path} escapes the test sandbox"
        for real in _REAL_DIRS:
            assert not _is_under(path, real), f"{path} is inside the real {real}"


def test_daemon_socket_server_uses_the_redirected_endpoint(sandbox_home):
    """The default socket path must be read when the server is built, not when
    the module is imported — otherwise patching SOCKET_PATH does nothing and
    stop() unlinks the live daemon's endpoint file."""
    daemon = ClawdDaemon()
    assert _is_under(daemon._socket._socket_path, sandbox_home)


def test_preferences_default_path_is_redirected(sandbox_home):
    assert _is_under(preferences.PREFS_PATH, sandbox_home)
    preferences.save_preferences(updates={"ble_enabled": False})
    assert preferences.PREFS_PATH.exists()
    assert preferences.load_preferences()["ble_enabled"] is False


def test_controller_default_prefs_path_is_redirected(sandbox_home):
    class _View:
        def __getattr__(self, name):
            return lambda *a, **k: None

    controller = ClawdTankController(_View())
    assert _is_under(controller._prefs_path, sandbox_home)


def test_hook_command_matches_the_redirected_notify_script():
    """HOOK_COMMAND and the ownership regex are derived from NOTIFY_SCRIPT_PATH;
    redirecting one without the others would make install/uninstall tests
    disagree with themselves."""
    assert str(hooks.NOTIFY_SCRIPT_PATH) in hooks.HOOK_COMMAND or \
        "margarita-notify.exe" in hooks.HOOK_COMMAND
    assert hooks._command_is_ours(hooks.HOOK_COMMAND)
