"""Resolve the long-lived Claude Code session PID by walking the process tree.

Mirrors claude-plugins/agent-bus/lib/common.sh:_find_claude_pid. The embedded
NOTIFY_SCRIPT in clawd_tank_menubar/hooks.py duplicates this logic — keep them
in sync.
"""

import os
import re
import subprocess
import sys
from typing import Optional

_CLAUDE_ARGV_RE = re.compile(r"(^|/)claude($|\s)")

# Windows: image name of the native Claude Code install. A node-hosted install
# (`node.exe ...\cli.js`) is not recognized — that would need each ancestor's
# command line, which Toolhelp32 does not expose.
_CLAUDE_EXE_NAME = "claude.exe"
# A hook sits a handful of levels below Claude (python launcher, python, one to
# three bash.exe). Anything deeper is not this hook's Claude.
_MAX_ANCESTRY_DEPTH = 32


def _is_windows() -> bool:
    return sys.platform == "win32"


def _ps(field: str, pid: int) -> str:
    """Run `ps -o <field>= -p <pid>` and return trimmed stdout. Empty on error."""
    try:
        r = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(pid)],
            capture_output=True, text=True, timeout=1.0,
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def walk_to_claude(start: int, table: dict) -> Optional[int]:
    """Return the first PID at or above `start` whose image is claude.exe.

    `table` maps pid -> (parent pid, exe name), as read from one Toolhelp32
    snapshot. Returns None when the chain breaks (parent already exited),
    loops (a reused PID), or exceeds the depth limit.
    """
    pid = start
    seen = set()
    for _ in range(_MAX_ANCESTRY_DEPTH):
        if pid in seen or pid not in table:
            return None
        seen.add(pid)
        ppid, name = table[pid]
        if name.lower() == _CLAUDE_EXE_NAME:
            return pid
        pid = ppid
    return None


def _windows_process_table() -> dict:
    """Snapshot every process once: pid -> (parent pid, exe name)."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    th32cs_snapprocess = 0x00000002
    invalid_handle = wintypes.HANDLE(-1).value
    snap = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if not snap or snap == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    table = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return table


def _find_claude_pid_windows() -> Optional[int]:
    """Windows: walk one Toolhelp32 snapshot. Never raises; None if not found.

    No os.getppid() fallback here (unlike POSIX): the hook's parent is a shell
    that exits as soon as the hook returns, and the daemon's liveness checker
    would evict the still-running session the moment it saw that PID die.
    None makes the daemon fall back to time-based eviction instead.
    """
    try:
        return walk_to_claude(os.getppid(), _windows_process_table())
    except Exception:
        return None


def find_claude_pid() -> Optional[int]:
    """Walk from os.getppid() up the process tree to find the long-lived
    Claude Code PID. On POSIX, falls back to os.getppid() if no `claude`
    ancestor is found; on Windows, returns None instead (see
    _find_claude_pid_windows).

    POSIX identification (in order, per ancestor):
      1. `ps -o comm=` exactly equals "claude" (native binary)
      2. `ps -o command=` matches (^|/)claude($|\\s) (node-wrapped install)

    Loose substring matching against argv is DELIBERATELY AVOIDED — see the
    agent-bus comment block (lib/common.sh:36-47) for the rationale.

    Windows identification: the ancestor's image name is claude.exe.
    """
    if _is_windows():
        return _find_claude_pid_windows()
    start = os.getppid()
    pid = start
    while pid > 1:
        if _ps("comm", pid) == "claude":
            return pid
        if _CLAUDE_ARGV_RE.search(_ps("command", pid)):
            return pid
        ppid_str = _ps("ppid", pid)
        try:
            pid = int(ppid_str)
        except ValueError:
            break
    return start
