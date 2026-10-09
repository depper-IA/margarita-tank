"""Shared test fixtures."""

import pytest

import clawd_tank_daemon.daemon as daemon_mod
import clawd_tank_daemon.session_store as session_store
import clawd_tank_daemon.socket_server as socket_server
import clawd_tank_menubar.__main__ as entry
import clawd_tank_menubar.hooks as hooks
import clawd_tank_menubar.preferences as preferences


@pytest.fixture(autouse=True)
def sandbox_home(tmp_path_factory, monkeypatch):
    """Keep every test out of the real ~/.clawd-tank and ~/.claude.

    A live Margarita Tank daemon may be running on the machine that runs the
    suite: a test that stops a ClawdDaemon built with default paths would unlink
    its endpoint file, and one that saves preferences would rewrite the user's.
    Module-level paths are computed from Path.home() at import time, so the
    environment alone cannot redirect them — each one is patched here, and HOME /
    USERPROFILE are pointed at a sandbox for anything that resolves the home
    directory later (including subprocesses such as the notify script).

    The sandbox lives outside tmp_path so tests that list tmp_path see only
    what they created. Returns the sandbox home directory.
    """
    home = tmp_path_factory.mktemp("home")
    clawd_dir = home / ".clawd-tank"
    clawd_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAWD_TANK_SOCKET", raising=False)

    # Daemon
    monkeypatch.setattr(session_store, "SESSIONS_PATH", clawd_dir / "sessions.json")
    monkeypatch.setattr(socket_server, "CLAWD_DIR", clawd_dir)
    monkeypatch.setattr(socket_server, "SOCKET_PATH",
                        clawd_dir / socket_server.SOCKET_PATH.name)
    monkeypatch.setattr(daemon_mod, "PID_PATH", clawd_dir / "daemon.pid")
    monkeypatch.setattr(daemon_mod, "LOCK_PATH", clawd_dir / "daemon.lock")
    monkeypatch.setattr(daemon_mod, "USAGE_CACHE_PATH",
                        str(clawd_dir / "statusline-cache.json"))

    # Menu bar / tray app
    monkeypatch.setattr(preferences, "PREFS_PATH", clawd_dir / "preferences.json")
    monkeypatch.setattr(entry, "LOG_DIR", clawd_dir / "logs")

    # Claude Code hooks. HOOK_COMMAND, HOOKS_CONFIG and the ownership pattern
    # are all derived from NOTIFY_SCRIPT_PATH, so they move together.
    script = clawd_dir / hooks.NOTIFY_SCRIPT_PATH.name
    command = hooks.build_hook_command(
        hooks.sys.platform, getattr(hooks.sys, "frozen", False),
        hooks.sys.executable, script,
    )
    monkeypatch.setattr(hooks, "CLAWD_DIR", clawd_dir)
    monkeypatch.setattr(hooks, "NOTIFY_SCRIPT_PATH", script)
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS_PATH", home / ".claude" / "settings.json")
    monkeypatch.setattr(hooks, "HOOK_COMMAND", command)
    monkeypatch.setattr(hooks, "HOOKS_CONFIG", hooks.build_hooks_config(command))
    sl_script = clawd_dir / hooks.STATUSLINE_SCRIPT_PATH.name
    monkeypatch.setattr(hooks, "STATUSLINE_SCRIPT_PATH", sl_script)
    monkeypatch.setattr(hooks, "STATUSLINE_COMMAND", hooks.build_statusline_command(
        hooks.sys.platform, getattr(hooks.sys, "frozen", False),
        hooks.sys.executable, sl_script))
    monkeypatch.setattr(hooks, "_OUR_COMMAND_RE",
                        hooks.build_our_command_re(hooks.sys.platform, script))
    return home
