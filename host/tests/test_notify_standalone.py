"""Tests for the standalone host/clawd-tank-notify hook script.

The script is stdlib-only and deployed as a single file, so its daemon probe is
inlined rather than imported. These tests load it by path and check it against
real processes: if the probe wrongly reports a dead daemon as running, the hook
sends every event into a socket nobody is listening on and silently drops it.
"""
import importlib.util
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

NOTIFY_PATH = Path(__file__).resolve().parent.parent / "clawd-tank-notify"
UNUSED_PID = 999999


def _load_notify_script():
    loader = SourceFileLoader("clawd_tank_notify_standalone", str(NOTIFY_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def notify(tmp_path, monkeypatch):
    module = _load_notify_script()
    monkeypatch.setattr(module, "PID_PATH", tmp_path / "daemon.pid")
    return module


@pytest.fixture
def sleeper():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)


def test_no_pid_file_means_not_running(notify):
    assert notify.is_daemon_running() is False


def test_live_pid_means_running(notify, sleeper):
    notify.PID_PATH.write_text(str(sleeper.pid))
    assert notify.is_daemon_running() is True
    assert notify.PID_PATH.exists()


def test_dead_pid_means_not_running_and_clears_the_stale_file(notify, sleeper):
    """The real bug: a daemon that has exited must not read as running."""
    notify.PID_PATH.write_text(str(sleeper.pid))
    assert notify.is_daemon_running() is True

    sleeper.kill()
    sleeper.wait(timeout=30)

    assert notify.is_daemon_running() is False
    assert not notify.PID_PATH.exists()


def test_unused_pid_means_not_running(notify):
    notify.PID_PATH.write_text(str(UNUSED_PID))
    assert notify.is_daemon_running() is False
    assert not notify.PID_PATH.exists()


def test_garbage_pid_file_means_not_running(notify):
    notify.PID_PATH.write_text("not-a-pid")
    assert notify.is_daemon_running() is False
    assert not notify.PID_PATH.exists()
