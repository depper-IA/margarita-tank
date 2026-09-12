"""Tests for restrict_to_current_user — the access boundary under the endpoint
file that holds the Windows ingress token. A 0600 file and a single-ACE DACL are
the same promise spelled two ways, so both are asserted against the OS, not
against the call having been made."""

import os
import stat
import subprocess
import sys

import pytest

from clawd_tank_daemon.file_security import restrict_to_current_user


@pytest.fixture
def secret(tmp_path):
    path = tmp_path / "endpoint.json"
    path.write_text('{"port": 1, "token": "s"}', encoding="utf-8")
    return path


def test_owner_can_still_read_and_write_it(secret):
    restrict_to_current_user(secret)
    secret.write_text("rewritten", encoding="utf-8")
    assert secret.read_text(encoding="utf-8") == "rewritten"


@pytest.mark.skipif(sys.platform == "win32", reason="mode bits are POSIX-only")
def test_posix_mode_is_0600(secret):
    restrict_to_current_user(secret)
    assert stat.S_IMODE(os.stat(secret).st_mode) == 0o600


@pytest.mark.skipif(sys.platform != "win32", reason="DACLs are Windows-only")
def test_windows_dacl_drops_every_inherited_ace(secret):
    """A file under %USERPROFILE% inherits access for SYSTEM, Administrators and
    — on a shared or managed machine — whatever else the profile hands down. The
    protected DACL must replace all of it with one ACE for this user."""
    before = subprocess.run(["icacls", str(secret)], capture_output=True,
                            text=True, timeout=10).stdout
    restrict_to_current_user(secret)
    after = subprocess.run(["icacls", str(secret)], capture_output=True,
                           text=True, timeout=10).stdout

    def aces(output):
        return [line for line in output.splitlines() if ":(" in line]

    assert len(aces(before)) > 1, f"nothing was inherited to drop:\n{before}"
    assert len(aces(after)) == 1, f"expected a single ACE:\n{after}"
    assert "(I)" not in aces(after)[0], f"inherited access survived:\n{after}"


@pytest.mark.skipif(sys.platform != "win32", reason="DACLs are Windows-only")
def test_windows_failure_is_raised_not_swallowed(tmp_path):
    """Callers rely on this to protect a secret, so a file it could not reach has
    to surface as an error rather than a silently unprotected file."""
    with pytest.raises(OSError):
        restrict_to_current_user(tmp_path / "does-not-exist.json")
