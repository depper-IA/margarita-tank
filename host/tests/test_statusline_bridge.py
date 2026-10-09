"""Tests for the standalone statusLine bridge script.

The bridge sits between Claude Code and the user's statusLine: it caches the
statusLine stdin JSON (which carries rate_limits) for the daemon, then chains
the user's original statusLine command so their status line keeps working.
It runs on every statusLine refresh, so it must never fail loudly.
"""

import json
import os
import subprocess
import sys

import pytest

from clawd_tank_daemon.protocol import read_usage_from_cache
from clawd_tank_menubar import hooks

PAYLOAD = {
    "model": {"display_name": "Opus"},
    "rate_limits": {
        "five_hour": {"used_percentage": 42.0, "resets_at": 1900000000},
        "seven_day": {"used_percentage": 7.0, "resets_at": 1900500000},
    },
}


@pytest.fixture
def bridge(tmp_path):
    """Return run(stdin, original=...) executing the bridge in a sandbox dir."""
    script = tmp_path / "statusline_bridge.py"
    script.write_text(hooks.STATUSLINE_BRIDGE_SCRIPT, encoding="utf-8")
    clawd_dir = tmp_path / "clawd"
    clawd_dir.mkdir()

    def run(stdin, original="<unset>"):
        if original != "<unset>":
            (clawd_dir / "statusline-original.json").write_text(
                json.dumps(original), encoding="utf-8")
        env = {**os.environ, "CLAWD_TANK_DIR": str(clawd_dir)}
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=stdin if isinstance(stdin, bytes) else stdin.encode(),
            capture_output=True, env=env, timeout=30,
        )
        return proc, clawd_dir / "statusline-cache.json"

    return run


def test_writes_cache_the_daemon_can_read(bridge):
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    usage = read_usage_from_cache(str(cache))
    assert usage["session_pct"] == 42
    assert usage["weekly_pct"] == 7


def test_write_is_atomic_and_leaves_no_temp_files(bridge):
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert sorted(p.name for p in cache.parent.iterdir()) == ["statusline-cache.json"]


def test_overwrites_previous_cache(bridge):
    bridge(json.dumps({"rate_limits": {"five_hour": {"used_percentage": 1}}}))
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert json.loads(cache.read_text())["rate_limits"]["five_hour"]["used_percentage"] == 42.0


def test_no_original_prints_nothing_and_exits_zero(bridge):
    proc, _ = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert proc.stdout == b""


def test_chains_original_command_with_same_stdin(bridge):
    # The original reads stdin and echoes the model name: proves it got the JSON.
    original_cmd = (
        f'"{sys.executable}" -c "import json,sys; '
        f'print(\'ORIG:\' + json.load(sys.stdin)[\'model\'][\'display_name\'])"'
    )
    proc, cache = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "ORIG:Opus"
    assert cache.exists()


def test_invalid_json_does_not_write_cache_but_still_chains(bridge):
    original_cmd = f'"{sys.executable}" -c "import sys; sys.stdout.write(sys.stdin.read())"'
    proc, cache = bridge(
        "not json {",
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout == b"not json {"
    assert not cache.exists()


def test_non_object_json_is_not_cached(bridge):
    proc, cache = bridge("[1, 2]")
    assert proc.returncode == 0
    assert not cache.exists()


def test_empty_stdin_exits_zero(bridge):
    proc, cache = bridge("")
    assert proc.returncode == 0
    assert not cache.exists()


@pytest.mark.parametrize("original", [
    "garbage-not-a-dict",
    {"statusLine": None},
    {"statusLine": {"type": "command"}},
    {"statusLine": "just a string"},
])
def test_unusable_original_state_is_ignored(bridge, original):
    proc, cache = bridge(json.dumps(PAYLOAD), original=original)
    assert proc.returncode == 0
    assert proc.stdout == b""
    assert cache.exists()


def test_corrupt_state_file_is_ignored(bridge, tmp_path):
    (tmp_path / "clawd" / "statusline-original.json").write_text("{nope")
    proc, cache = bridge(json.dumps(PAYLOAD))
    assert proc.returncode == 0
    assert cache.exists()


def test_failing_original_command_still_exits_zero(bridge):
    proc, cache = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": "definitely-not-a-command-xyz"}},
    )
    assert proc.returncode == 0
    assert cache.exists()


def test_unwritable_cache_dir_still_chains_and_exits_zero(bridge, tmp_path):
    original_cmd = f'"{sys.executable}" -c "print(\'still works\')"'
    # Point the state dir at a path whose cache cannot be created.
    clawd = tmp_path / "clawd"
    (clawd / "statusline-cache.json").mkdir()  # os.replace onto a directory fails
    proc, _ = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": original_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "still works"


def test_bridge_does_not_recurse_into_itself(bridge, tmp_path):
    script = tmp_path / "statusline_bridge.py"
    self_cmd = f'"{sys.executable}" "{script}"'
    proc, _ = bridge(
        json.dumps(PAYLOAD),
        original={"statusLine": {"type": "command", "command": self_cmd}},
    )
    assert proc.returncode == 0
    assert proc.stdout == b""
