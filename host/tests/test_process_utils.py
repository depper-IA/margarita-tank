"""Tests for portable process liveness and termination.

Every liveness assertion here is made against a real OS process that is really
spawned and really killed. `os.kill(pid, 0)` raises nothing for a
recently-exited PID on Windows, so a test that only mocked the probe would pass
against a completely broken implementation.
"""
import subprocess
import sys

import pytest

from clawd_tank_daemon.process_utils import pid_alive, terminate_pid

# High enough to be unallocated on every supported platform. On Windows
# OpenProcess fails with ERROR_INVALID_PARAMETER for it, which is exactly the
# case `os.kill(pid, 0)` turned into an uncaught OSError (WinError 87).
UNUSED_PID = 999999


@pytest.fixture
def sleeper():
    """A real, long-lived child process. Always reaped."""
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


def test_pid_alive_true_for_a_running_process(sleeper):
    assert pid_alive(sleeper.pid) is True


def test_pid_alive_false_after_the_process_exits(sleeper):
    """The Windows bug this exists for: a dead PID must read as dead."""
    assert pid_alive(sleeper.pid) is True
    sleeper.kill()
    sleeper.wait(timeout=30)
    assert pid_alive(sleeper.pid) is False


def test_pid_alive_false_after_a_process_exits_on_its_own():
    proc = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    proc.wait(timeout=30)
    assert pid_alive(proc.pid) is False


def test_pid_alive_false_for_an_unused_pid_without_raising():
    assert pid_alive(UNUSED_PID) is False


def test_pid_alive_true_for_a_process_we_may_not_control():
    """A real system process we lack rights over is alive, not gone.

    Windows returns ERROR_ACCESS_DENIED from OpenProcess here; POSIX raises
    PermissionError from os.kill. Both must read as alive.
    """
    system_pid = 4 if sys.platform == "win32" else 1
    assert pid_alive(system_pid) is True


def test_terminate_pid_actually_stops_the_process(sleeper):
    terminate_pid(sleeper.pid)
    assert sleeper.wait(timeout=30) is not None
    assert pid_alive(sleeper.pid) is False


def test_terminate_pid_raises_process_lookup_error_for_an_unused_pid():
    """_stop_existing_daemon() relies on this to mean 'already dead'."""
    with pytest.raises(ProcessLookupError):
        terminate_pid(UNUSED_PID)
