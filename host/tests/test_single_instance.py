"""Tests for the single-instance file lock.

These exercise the real lock: a real file is locked, and the contending
acquisition happens in a real second process. Lock ownership on both POSIX
(flock) and Windows (msvcrt.locking) is per-process, so a same-process retry
would prove nothing.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clawd_tank_daemon import single_instance

HOST_DIR = str(Path(__file__).resolve().parent.parent)

# Child program: acquire the lock, print the outcome, optionally hold it until
# stdin closes. Exit 0 = acquired, exit 3 = refused.
_CHILD = textwrap.dedent("""\
    import sys
    sys.path.insert(0, sys.argv[1])
    from clawd_tank_daemon import single_instance
    try:
        fd = single_instance.acquire(sys.argv[2])
    except OSError:
        print("REFUSED", flush=True)
        sys.exit(3)
    print("ACQUIRED", flush=True)
    if len(sys.argv) > 3 and sys.argv[3] == "hold":
        sys.stdin.read()
    sys.exit(0)
    """)


def _run_child(lock_path, *extra):
    return subprocess.run(
        [sys.executable, "-c", _CHILD, HOST_DIR, str(lock_path), *extra],
        capture_output=True, text=True, timeout=30,
    )


@pytest.fixture
def lock_path(tmp_path):
    return tmp_path / "daemon.lock"


def test_acquire_creates_and_locks_the_file(lock_path):
    fd = single_instance.acquire(lock_path)
    try:
        assert lock_path.exists()
        assert isinstance(fd, int)
    finally:
        os.close(fd)


def test_second_process_is_refused_while_lock_is_held(lock_path):
    """The whole point: a second process must not get the lock."""
    fd = single_instance.acquire(lock_path)
    try:
        result = _run_child(lock_path)
        assert result.stdout.strip() == "REFUSED", result.stderr
        assert result.returncode == 3
    finally:
        os.close(fd)


def test_lock_is_available_after_the_holder_closes_it(lock_path):
    fd = single_instance.acquire(lock_path)
    os.close(fd)

    result = _run_child(lock_path)
    assert result.stdout.strip() == "ACQUIRED", result.stderr
    assert result.returncode == 0


def test_lock_is_released_when_the_holding_process_exits(lock_path):
    """Release-on-exit is what makes a crashed daemon recoverable."""
    holder = subprocess.Popen(
        [sys.executable, "-c", _CHILD, HOST_DIR, str(lock_path), "hold"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "ACQUIRED"
        # Still held: we must be refused from this process.
        with pytest.raises(OSError):
            single_instance.acquire(lock_path)
    finally:
        holder.stdin.close()
        holder.wait(timeout=30)

    fd = single_instance.acquire(lock_path)
    os.close(fd)


def test_refused_acquire_does_not_leak_a_descriptor(lock_path):
    fd = single_instance.acquire(lock_path)
    try:
        holder = subprocess.Popen(
            [sys.executable, "-c", _CHILD, HOST_DIR, str(lock_path), "hold"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        holder.stdin.close()
        holder.wait(timeout=30)
        # After the refusal the lock file must still be openable (the child's
        # failed attempt closed its descriptor) and still held by us.
        result = _run_child(lock_path)
        assert result.stdout.strip() == "REFUSED", result.stderr
    finally:
        os.close(fd)
