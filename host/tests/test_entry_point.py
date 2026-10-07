"""Tests for the tray entry point's --uninstall-hooks mode.

The Windows uninstaller runs `MargaritaTank.exe --uninstall-hooks` before it
deletes the notify exe, so Claude Code is not left calling a missing program on
every hook event. That mode must do only that: no tray, no daemon.
"""

import json
import sys

import pytest

from clawd_tank_menubar import __main__ as entry
from clawd_tank_menubar import hooks


@pytest.fixture
def no_tray(monkeypatch):
    """Fail the test if either platform's tray/daemon startup is reached."""
    started = []
    monkeypatch.setattr(entry, "_run_windows", lambda: started.append("windows"))
    monkeypatch.setattr(entry, "_run_macos", lambda: started.append("macos"))
    return started


def _run_main(monkeypatch, *args) -> int:
    monkeypatch.setattr(sys, "argv", ["MargaritaTank.exe", *args])
    with pytest.raises(SystemExit) as exc:
        entry.main()
    return exc.value.code


def test_uninstall_flag_exits_zero_on_success_without_starting_tray(monkeypatch, no_tray):
    calls = []
    monkeypatch.setattr(hooks, "uninstall_hooks", lambda: calls.append(1) or True)
    assert _run_main(monkeypatch, "--uninstall-hooks") == 0
    assert calls == [1]
    assert no_tray == []


def test_uninstall_flag_exits_one_on_failure(monkeypatch, no_tray):
    monkeypatch.setattr(hooks, "uninstall_hooks", lambda: False)
    assert _run_main(monkeypatch, "--uninstall-hooks") == 1
    assert no_tray == []


def test_uninstall_flag_exits_one_when_uninstall_raises(monkeypatch, no_tray):
    """An uninstaller step must end with an exit code, not a traceback dialog."""
    def boom():
        raise OSError("settings locked")
    monkeypatch.setattr(hooks, "uninstall_hooks", boom)
    assert _run_main(monkeypatch, "--uninstall-hooks") == 1
    assert no_tray == []


def test_uninstall_flag_logs_the_outcome(monkeypatch, no_tray):
    monkeypatch.setattr(hooks, "uninstall_hooks", lambda: True)
    _run_main(monkeypatch, "--uninstall-hooks")
    for handler in __import__("logging").getLogger().handlers:
        handler.flush()
    log = (entry.LOG_DIR / "clawd-tank.log").read_text(encoding="utf-8")
    assert "hooks" in log.lower()


def test_uninstall_flag_removes_installed_hooks(monkeypatch, no_tray):
    """End to end through the real hooks module, on the sandboxed settings."""
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    hooks.install_hooks()
    assert hooks.are_hooks_installed()

    assert _run_main(monkeypatch, "--uninstall-hooks") == 0
    assert json.loads(hooks.CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8")) == {"model": "opus"}


def test_without_flag_starts_the_platform_tray(monkeypatch, no_tray):
    monkeypatch.setattr(sys, "argv", ["MargaritaTank.exe"])
    entry.main()
    assert no_tray == ["macos" if sys.platform == "darwin" else "windows"]
