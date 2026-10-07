"""Tests for find_claude_pid — walks process ancestors via `ps` to find the
long-lived Claude Code PID, mirroring claude-plugins/agent-bus/lib/common.sh.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from clawd_tank_daemon import pid_resolver
from clawd_tank_daemon.pid_resolver import find_claude_pid
from clawd_tank_menubar.hooks import NOTIFY_SCRIPT


@pytest.fixture(autouse=True)
def _posix_by_default(monkeypatch):
    """The `ps`-based tests below describe the POSIX walk; pin the platform so
    they exercise it on Windows too. Windows tests override this."""
    monkeypatch.setattr(pid_resolver, "_is_windows", lambda: False)


def _make_ps_mock(responses):
    """responses: dict of (field, pid) -> raw stdout string (will get a trailing newline).

    Each subprocess.run call gets args=["ps", "-o", "<field>=", "-p", "<pid>"].
    Returns MagicMock with .stdout matching the responses table, empty otherwise.
    """
    def side_effect(args, **kwargs):
        field = args[2].rstrip("=")
        pid = int(args[4])
        out = responses.get((field, pid), "")
        return MagicMock(stdout=out + "\n", returncode=0)
    return side_effect


def test_direct_parent_is_claude():
    """getppid() returns claude — return it directly."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=100):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 100): "claude",
            })
            assert find_claude_pid() == 100


def test_walks_past_shell_wrapper():
    """getppid() is zsh, ancestor is claude — walk and find it."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=200):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 200): "zsh",
                ("command", 200): "zsh -c /Users/me/.clawd-tank/clawd-tank-notify",
                ("ppid", 200): "300",
                ("comm", 300): "claude",
            })
            assert find_claude_pid() == 300


def test_node_install_matches_via_command_regex():
    """Node-wrapped install: comm is 'node', argv invokes a path ending in `claude`."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=400):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 400): "node",
                ("command", 400): "node /opt/claude-code/bin/claude --resume xyz",
            })
            assert find_claude_pid() == 400


def test_node_install_with_path_prefix_matches():
    """Command starts with /usr/local/bin/claude."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=500):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 500): "claude-wrapper",
                ("command", 500): "/usr/local/bin/claude --resume abc",
            })
            assert find_claude_pid() == 500


def test_shell_snapshot_does_NOT_match():
    """Critical negative case (agent-bus calls this out): the Bash tool spawns
    `zsh -c '... ~/.claude/shell-snapshots/...'`. A loose substring would match
    the zsh's argv. The strict `comm == "claude"` and `(^|/)claude($|\\s)` regex
    must NOT match this shell.
    """
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=600):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 600): "zsh",
                ("command", 600): "zsh -c source ~/.claude/shell-snapshots/snap-12345.sh; /tmp/cmd",
                ("ppid", 600): "1",  # walk terminates
            })
            # No claude ancestor found, falls back to getppid()
            assert find_claude_pid() == 600


def test_falls_back_to_getppid_when_no_claude_ancestor():
    """Walk reaches pid 1 without finding claude — return original getppid()."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=700):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({
                ("comm", 700): "zsh",
                ("command", 700): "zsh",
                ("ppid", 700): "1",
            })
            assert find_claude_pid() == 700


def test_falls_back_to_getppid_when_ps_fails():
    """ps returns empty (process gone mid-walk) — fall back gracefully."""
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=800):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = _make_ps_mock({})  # all empty
            assert find_claude_pid() == 800


def test_ps_timeout_does_not_raise():
    """subprocess timeout returns empty string, walk falls back."""
    import subprocess as sp
    with patch("clawd_tank_daemon.pid_resolver.os.getppid", return_value=900):
        with patch("clawd_tank_daemon.pid_resolver.subprocess.run") as run:
            run.side_effect = sp.TimeoutExpired(cmd="ps", timeout=1.0)
            assert find_claude_pid() == 900


# --- Windows: Toolhelp32 snapshot walk ---------------------------------------
#
# Windows has no `ps`. The resolver takes ONE Toolhelp32 snapshot, builds a
# pid -> (ppid, exe name) table and walks it. Observed ancestry of a hook on a
# native install: python.exe -> bash.exe (x1-3) -> claude.exe -> cmd.exe.


def _notify_script_namespace():
    """Load the embedded NOTIFY_SCRIPT as a module namespace (main() not run)."""
    ns = {"__name__": "clawd_tank_notify_under_test"}
    exec(compile(NOTIFY_SCRIPT, "clawd-tank-notify", "exec"), ns)
    return ns


# The pure walk exists twice (daemon module + stdlib-only hook script). Every
# walk test runs against both so the copies cannot drift.
_WALKERS = [
    pytest.param(pid_resolver.walk_to_claude, id="pid_resolver"),
    pytest.param(_notify_script_namespace()["_walk_to_claude"], id="notify_script"),
]

_NATIVE_TREE = {
    10: (11, "python.exe"),   # venv redirector's child (the hook itself)
    11: (12, "python.exe"),   # venv redirector
    12: (13, "bash.exe"),
    13: (14, "bash.exe"),
    14: (20, "bash.exe"),
    20: (30, "claude.exe"),   # the long-lived Claude Code process
    30: (40, "cmd.exe"),
    40: (0, "explorer.exe"),
}


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_finds_claude_several_levels_up(walk):
    assert walk(11, _NATIVE_TREE) == 20


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_returns_start_when_it_is_claude(walk):
    assert walk(20, _NATIVE_TREE) == 20


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_matches_exe_name_case_insensitively(walk):
    assert walk(1, {1: (2, "cmd.exe"), 2: (3, "Claude.EXE")}) == 2


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_does_not_match_lookalike_names(walk):
    table = {1: (2, "claude-helper.exe"), 2: (3, "notclaude.exe"), 3: (0, "claude")}
    assert walk(1, table) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_returns_none_without_a_claude_ancestor(walk):
    table = {1: (2, "python.exe"), 2: (3, "bash.exe"), 3: (0, "explorer.exe")}
    assert walk(1, table) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_returns_none_on_a_missing_parent(walk):
    """The parent exited (or its PID is not in the snapshot) — stop, no guess."""
    assert walk(1, {1: (2, "python.exe"), 2: (99, "bash.exe")}) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_returns_none_for_an_unknown_start(walk):
    assert walk(5, _NATIVE_TREE) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_stops_on_a_cycle(walk):
    """Windows never rewrites a dead parent's PID in its children, so a reused
    PID can make the parent chain loop. It must terminate, not spin."""
    table = {1: (2, "python.exe"), 2: (3, "bash.exe"), 3: (1, "cmd.exe")}
    assert walk(1, table) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_stops_on_a_self_parented_process(walk):
    assert walk(0, {0: (0, "System Idle Process")}) is None


@pytest.mark.parametrize("walk", _WALKERS)
def test_windows_walk_gives_up_past_the_depth_limit(walk):
    """A claude.exe buried beyond the depth limit is not this hook's Claude."""
    depth = 200
    table = {i: (i + 1, "bash.exe") for i in range(1, depth)}
    table[depth] = (0, "claude.exe")
    assert walk(1, table) is None
    # ...but the same table with claude.exe close by is found.
    table[3] = (4, "claude.exe")
    assert walk(1, table) == 3


def _as_windows(monkeypatch, table, ppid=11):
    monkeypatch.setattr(pid_resolver, "_is_windows", lambda: True)
    monkeypatch.setattr(pid_resolver.os, "getppid", lambda: ppid)
    if isinstance(table, Exception):
        def boom():
            raise table
        monkeypatch.setattr(pid_resolver, "_windows_process_table", boom)
    else:
        monkeypatch.setattr(pid_resolver, "_windows_process_table", lambda: table)


def test_find_claude_pid_on_windows_walks_the_snapshot(monkeypatch):
    _as_windows(monkeypatch, _NATIVE_TREE)
    assert find_claude_pid() == 20


def test_find_claude_pid_on_windows_never_falls_back_to_the_parent(monkeypatch):
    """Unlike POSIX, no Claude ancestor means None: the hook's parent is a shell
    that exits as soon as the hook returns, and the liveness checker would
    evict a live session the moment it saw that PID die."""
    _as_windows(monkeypatch, {11: (12, "bash.exe"), 12: (0, "explorer.exe")})
    assert find_claude_pid() is None


def test_find_claude_pid_on_windows_swallows_snapshot_failures(monkeypatch):
    _as_windows(monkeypatch, OSError("CreateToolhelp32Snapshot failed"))
    assert find_claude_pid() is None


def test_find_claude_pid_on_windows_handles_an_empty_snapshot(monkeypatch):
    _as_windows(monkeypatch, {})
    assert find_claude_pid() is None


@pytest.mark.skipif(sys.platform != "win32", reason="real Toolhelp32 snapshot")
@pytest.mark.parametrize("table_fn", [
    pytest.param(lambda: pid_resolver._windows_process_table(), id="pid_resolver"),
    pytest.param(lambda: _notify_script_namespace()["_windows_process_table"](),
                 id="notify_script"),
])
def test_windows_process_table_reports_this_process_and_its_parent(table_fn):
    table = table_fn()
    ppid, name = table[os.getpid()]
    assert ppid == os.getppid()
    assert name.lower() == os.path.basename(sys.executable).lower()
