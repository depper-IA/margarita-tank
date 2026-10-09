# host/clawd_tank_menubar/hooks.py
"""Install the Claude Code hook script and configure hooks in settings."""

import copy
import json
import logging
import ntpath
import os
import re
import stat
import sys
import tempfile
import textwrap
from pathlib import Path

from clawd_tank_daemon.protocol import ASK_USER_QUESTION_TOOL, DISPLAY_NAME

logger = logging.getLogger("clawd-tank.hooks")

CLAWD_DIR = Path.home() / ".clawd-tank"
# Windows cannot execute an extensionless file with a shebang, and the command
# below names the interpreter explicitly, so the script needs the .py suffix
# for that interpreter to accept it.
NOTIFY_SCRIPT_PATH = CLAWD_DIR / (
    "clawd-tank-notify.py" if sys.platform == "win32" else "clawd-tank-notify"
)
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# The statusLine bridge keeps the same file name on every platform: it is always
# run through an explicit interpreter on Windows and via its shebang on POSIX.
STATUSLINE_SCRIPT_PATH = CLAWD_DIR / "statusline_bridge.py"
# The user's pre-existing statusLine, saved so the bridge can chain it and
# uninstall can restore it exactly.
STATUSLINE_STATE_NAME = "statusline-original.json"
STATUSLINE_EXE_NAME = "margarita-statusline.exe"

# Standalone hook script — uses only Python stdlib, no external imports.
NOTIFY_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """clawd-tank-notify - Claude Code hook handler for Clawd Tank.

    Reads hook payload from stdin, converts it to a daemon message, and forwards
    it to the daemon: a Unix socket on POSIX, an authenticated loopback TCP
    connection on Windows. No external dependencies.
    """
    # NOTIFY_SCRIPT_VERSION: 2026-10-08-display-name

    import json
    import os
    import re
    import socket
    import subprocess
    import sys
    from pathlib import Path

    # Fixed name on every notification card (protocol.DISPLAY_NAME).
    DISPLAY_NAME = __DISPLAY_NAME__

    # POSIX: the Unix socket itself. Windows: the file the daemon publishes its
    # loopback port and shared secret in.
    SOCKET_PATH = os.environ.get(
        "CLAWD_TANK_SOCKET",
        str(Path.home() / ".clawd-tank"
            / ("endpoint.json" if sys.platform == "win32" else "sock")),
    )

    _CLAUDE_ARGV_RE = re.compile(r"(^|/)claude($|\\s)")

    # Windows: image name of the native Claude Code install.
    _CLAUDE_EXE_NAME = "claude.exe"
    # A hook sits a handful of levels below Claude (python launcher, python, one
    # to three bash.exe). Anything deeper is not this hook's Claude.
    _MAX_ANCESTRY_DEPTH = 32


    def _ps(field, pid):
        """Run `ps -o <field>= -p <pid>`, return trimmed stdout. Empty on error."""
        try:
            r = subprocess.run(
                ["ps", "-o", field + "=", "-p", str(pid)],
                capture_output=True, text=True, timeout=1.0,
            )
            return r.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            return ""


    def _walk_to_claude(start, table):
        """Return the first PID at or above `start` whose image is claude.exe.

        `table` maps pid -> (parent pid, exe name) from one Toolhelp32 snapshot.
        None when the chain breaks (parent already exited), loops (a reused
        PID), or exceeds the depth limit.

        Mirrors clawd_tank_daemon/pid_resolver.py:walk_to_claude — keep in sync.
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


    def _windows_process_table():
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


    def _find_claude_pid():
        """Walk from os.getppid() up the process tree to find the long-lived
        Claude Code PID.

        Mirrors clawd_tank_daemon/pid_resolver.py — keep in sync.

        POSIX: asks `ps` per ancestor; falls back to os.getppid() if no
        `claude` ancestor.

        Windows: walks one Toolhelp32 snapshot for a claude.exe ancestor (the
        native install). Returns None if there is none, or on any failure — never
        os.getppid(): the hook runs under a shell that exits the moment it
        returns, and sending that shell's PID would make the daemon's liveness
        checker evict a session that is very much alive. A node-hosted install
        is not recognized (that needs argv, which the snapshot lacks), so it
        falls back to the daemon's staleness timeout.
        """
        if sys.platform == "win32":
            try:
                return _walk_to_claude(os.getppid(), _windows_process_table())
            except Exception:
                return None
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


    def hook_to_message(hook):
        """Convert a Claude Code hook payload to a daemon message."""
        event_name = hook.get("hook_event_name", "")
        session_id = hook.get("session_id", "")
        cwd = hook.get("cwd", "")
        project = Path(cwd).name if cwd else ""
        pid = _find_claude_pid()

        if event_name == "SessionStart":
            msg = {"event": "session_start", "session_id": session_id, "project": project, "pid": pid}
            source = hook.get("source")
            if source is not None:
                msg["source"] = source
            return msg

        if event_name == "PreToolUse":
            return {"event": "tool_use", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}

        if event_name == "PostToolUse":
            return {"event": "tool_done", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}

        if event_name == "PermissionRequest":
            return {"event": "permission", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}

        if event_name == "PostToolUseFailure":
            return {"event": "tool_failed", "session_id": session_id, "tool_name": hook.get("tool_name", ""), "project": project, "pid": pid}

        if event_name == "PreCompact":
            return {"event": "compact", "session_id": session_id, "pid": pid}

        if event_name == "Stop":
            return {
                "event": "add",
                "hook": "Stop",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": "Esperando tu respuesta",
                "pid": pid,
            }

        if event_name == "StopFailure":
            message = hook.get("error", "") or hook.get("stop_reason", "") or "Error de API"
            return {
                "event": "add",
                "hook": "StopFailure",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": message,
                "pid": pid,
            }

        if event_name == "Notification":
            if hook.get("notification_type") != "idle_prompt":
                return None
            return {
                "event": "add",
                "hook": "Notification",
                "session_id": session_id,
                "project": DISPLAY_NAME,
                "message": hook.get("message", "Esperando tu respuesta"),
                "pid": pid,
            }

        if event_name == "UserPromptSubmit":
            return {"event": "dismiss", "hook": "UserPromptSubmit", "session_id": session_id, "pid": pid}

        if event_name == "SessionEnd":
            msg = {"event": "dismiss", "hook": "SessionEnd", "session_id": session_id, "pid": pid}
            reason = hook.get("reason")
            if reason is not None:
                msg["reason"] = reason
            return msg

        if event_name == "SubagentStart":
            return {
                "event": "subagent_start",
                "session_id": session_id,
                "agent_id": hook.get("agent_id", ""),
                "pid": pid,
            }

        if event_name == "SubagentStop":
            return {
                "event": "subagent_stop",
                "session_id": session_id,
                "agent_id": hook.get("agent_id", ""),
                "pid": pid,
            }

        return None


    def main():
        try:
            raw = sys.stdin.read()
            if not raw.strip():
                sys.exit(0)
            payload = json.loads(raw)
        except json.JSONDecodeError:
            sys.exit(1)

        msg = hook_to_message(payload)
        if msg is None:
            sys.exit(0)

        # Windows has no AF_UNIX: connect to the loopback port the daemon
        # published and present its shared secret as the first line.
        if sys.platform == "win32":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(3.0)
            if sys.platform == "win32":
                with open(SOCKET_PATH, encoding="utf-8") as f:
                    endpoint = json.load(f)
                sock.connect(("127.0.0.1", endpoint["port"]))
                sock.sendall(endpoint["token"].encode("utf-8") + b"\\n")
            else:
                sock.connect(SOCKET_PATH)
            sock.sendall(json.dumps(msg).encode("utf-8") + b"\\n")
        # The last two cover a torn or stale endpoint file and can only be
        # raised on the Windows branch, so POSIX behaviour is unchanged.
        except (ConnectionRefusedError, FileNotFoundError, socket.timeout,
                json.JSONDecodeError, KeyError):
            sys.exit(0)
        finally:
            sock.close()


    if __name__ == "__main__":
        main()
''').replace("__DISPLAY_NAME__", repr(DISPLAY_NAME))

# File name of the console-subsystem notify exe that the Windows PyInstaller
# build ships next to the tray exe (see host/windows/margarita_tank.spec).
STATUSLINE_BRIDGE_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """statusline_bridge - Claude Code statusLine wrapper for Clawd Tank.

    Claude Code pipes a JSON document (including rate_limits) to the statusLine
    command on every refresh. This script caches that JSON for the daemon's usage
    bar, then chains the user's original statusLine command (saved at install time)
    with the same stdin and prints its output, so their status line keeps working.
    It must never fail loudly: every error is swallowed and the exit code is 0.
    No external dependencies.
    """
    # STATUSLINE_BRIDGE_VERSION: 1

    import json
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    CLAWD_DIR = Path(os.environ.get("CLAWD_TANK_DIR") or (Path.home() / ".clawd-tank"))
    CACHE_PATH = CLAWD_DIR / "statusline-cache.json"
    STATE_PATH = CLAWD_DIR / "statusline-original.json"
    GUARD_ENV = "CLAWD_TANK_STATUSLINE_BRIDGE"
    CHAIN_TIMEOUT_S = 10


    def write_cache(raw):
        try:
            if not isinstance(json.loads(raw.decode("utf-8-sig")), dict):
                return
            CLAWD_DIR.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(CLAWD_DIR), suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(raw)
                os.replace(tmp, CACHE_PATH)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception:
            pass


    def original_command():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
            command = state["statusLine"]["command"]
            return command if isinstance(command, str) and command.strip() else None
        except Exception:
            return None


    def chain(command, raw):
        # A bridge that finds itself as the "original" would fork forever.
        if os.environ.get(GUARD_ENV):
            return
        try:
            proc = subprocess.run(
                command, shell=True, input=raw, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=CHAIN_TIMEOUT_S,
                env={**os.environ, GUARD_ENV: "1"},
            )
            sys.stdout.buffer.write(proc.stdout)
            sys.stdout.buffer.flush()
        except Exception:
            pass


    def main():
        try:
            raw = sys.stdin.buffer.read()
        except Exception:
            raw = b""
        write_cache(raw)
        command = original_command()
        if command:
            chain(command, raw)


    if __name__ == "__main__":
        try:
            main()
        except Exception:
            pass
        sys.exit(0)
''')

NOTIFY_EXE_NAME = "margarita-notify.exe"


def build_hook_command(platform: str, frozen: bool, executable: str, script_path) -> str:
    """The command Claude Code runs for every hook.

    POSIX runs the script directly through its shebang. Windows has no shebang
    support, so the interpreter is named explicitly. A .cmd shim would work too,
    but it puts a second process between Claude Code and the hook on the hot
    path of every event, for nothing.

    A packaged Windows build (PyInstaller sets sys.frozen) has no Python
    interpreter to name: sys.executable is the tray app itself, so naming it
    would start another tray instance on every hook. It runs the bundled
    console notify exe that sits next to the tray exe instead.

    Windows paths are quoted because they may contain spaces; Claude Code hands
    the command to `cmd.exe /d /s /c "<command>"`, which strips only the outer
    pair and passes the rest through verbatim.
    """
    if platform == "win32":
        if frozen:
            notify_exe = ntpath.join(ntpath.dirname(executable), NOTIFY_EXE_NAME)
            return f'"{notify_exe}"'
        return f'"{executable}" "{script_path}"'
    return str(script_path)


HOOK_COMMAND = build_hook_command(
    sys.platform, getattr(sys, "frozen", False), sys.executable, NOTIFY_SCRIPT_PATH
)


def build_hooks_config(command: str) -> dict:
    """Every managed hook group, each running `command`."""
    return {
        "SessionStart": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "StopFailure": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "Notification": [
            {
                "matcher": "idle_prompt",
                "hooks": [{"type": "command", "command": command}],
            }
        ],
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        # Scoped to AskUserQuestion only: the sole purpose is clearing the "waiting
        # for input" alert when the user answers. Registering PostToolUse for every
        # tool would double the device's event/BLE traffic for no added value.
        "PostToolUse": [
            {
                "matcher": ASK_USER_QUESTION_TOOL,
                "hooks": [{"type": "command", "command": command}],
            }
        ],
        # Claude is blocked waiting for the user to approve a tool → waiting/alert.
        "PermissionRequest": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        # A tool genuinely errored (not a non-zero shell exit) → confused.
        "PostToolUseFailure": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "PreCompact": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SubagentStart": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
        "SubagentStop": [
            {"hooks": [{"type": "command", "command": command}]}
        ],
    }


HOOKS_CONFIG = build_hooks_config(HOOK_COMMAND)


def install_notify_script() -> None:
    """Write the standalone notify script to NOTIFY_SCRIPT_PATH."""
    CLAWD_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFY_SCRIPT_PATH.write_text(NOTIFY_SCRIPT, encoding="utf-8")
    if sys.platform != "win32":
        # Windows has no execute bit — chmod there only toggles read-only — and
        # HOOK_COMMAND names the interpreter, so nothing needs to be executable.
        NOTIFY_SCRIPT_PATH.chmod(0o755)
    logger.info("Installed hook script: %s", NOTIFY_SCRIPT_PATH)


def _matcher_of(entry: dict):
    """Normalised matcher of a hook group. Absent/empty matcher → None.

    Claude Code treats a group with no matcher (or "") as matching everything,
    so they are equivalent for the purpose of locating "our" group.
    """
    if not isinstance(entry, dict):
        return None
    matcher = entry.get("matcher")
    return matcher if matcher else None


# The prefix match below anchors on the whole command, which is stable on POSIX
# but not on Windows: HOOK_COMMAND embeds an absolute interpreter path that a
# rebuilt venv or a moved Python changes, while the script path never moves. An
# unrecognised prior command is not pruned on reinstall, so it would linger as a
# duplicate group invoking an interpreter that is no longer there. Match on the
# script instead, anchored so only `"<interpreter>" "<script>"` with nothing in
# front of it counts — a wrapper such as `cat "<script>"` still does not.
# The packaged build's `"<install dir>\margarita-notify.exe"` is matched the same
# way, on the exe's file name, so switching between a source checkout and an
# installed build (or moving the install) replaces the previous group too.
def build_our_command_re(platform: str, script_path):
    """Pattern recognising any command of ours on `platform`. None on POSIX,
    where only the exact current command counts."""
    if platform != "win32":
        return None
    return re.compile(
        '^(?:"[^"]+" "' + re.escape(str(script_path)) + '"'
        r'|"[^"]*[\\/](?i:' + re.escape(NOTIFY_EXE_NAME) + ')")( |$)')


_OUR_COMMAND_RE = build_our_command_re(sys.platform, NOTIFY_SCRIPT_PATH)


def _command_is_ours(command) -> bool:
    """True only if a hook command actually invokes our notify script — the exact
    path, or the path followed by args. A command that merely CONTAINS the path as a
    substring (a wrapper, or `cat <path>`) is not ours."""
    if not isinstance(command, str):
        return False
    if _OUR_COMMAND_RE is not None:
        return _OUR_COMMAND_RE.match(command) is not None
    return _command_is_current(command)


def _command_is_current(command) -> bool:
    """True only if a hook command is exactly the CURRENT HOOK_COMMAND (optionally
    followed by args). On Windows _command_is_ours() also accepts commands left by
    another interpreter or install folder, so they get pruned on reinstall; those
    must not count as installed, or startup would never replace them."""
    if not isinstance(command, str):
        return False
    return command == HOOK_COMMAND or command.startswith(HOOK_COMMAND + " ")


def _group_runs_current_command(entry: dict) -> bool:
    """True if a hook group contains a hook that runs the current notify command."""
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list):
        return False
    return any(isinstance(h, dict) and _command_is_current(h.get("command", "")) for h in hooks_list)


def _is_our_managed_group(entry: dict) -> bool:
    """True if this group was created by Clawd Tank — a non-empty hooks list where
    EVERY hook runs our notify script. Such groups are safe to prune on install;
    a group the user shares with us (mixing their command with ours) is not."""
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list) or not hooks_list:
        return False
    return all(isinstance(h, dict) and _command_is_ours(h.get("command", "")) for h in hooks_list)


def _our_hook_present(existing_entries, our_matcher) -> bool:
    """True if some existing group with the same matcher already runs the current command."""
    if not isinstance(existing_entries, list):
        return False
    for entry in existing_entries:
        if _matcher_of(entry) == our_matcher and _group_runs_current_command(entry):
            return True
    return False


def _load_settings() -> dict | None:
    """Parse the Claude settings file. Returns {} when it does not exist and None
    when it exists but cannot be read, decoded or parsed into a JSON object.

    Read as utf-8-sig so a BOM left by a Windows editor is not treated as invalid.
    """
    if not CLAUDE_SETTINGS_PATH.exists():
        return {}
    try:
        text = CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8-sig")
        if not text.strip():
            return {}  # an empty file holds no user settings to protect
        settings = json.loads(text)
    except (ValueError, OSError):  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        return None
    return settings if isinstance(settings, dict) else None


def _write_settings_atomic(settings: dict) -> None:
    """Write via a temp file + os.replace so a crash mid-write never truncates
    the user's settings. Replaces the symlink target (not the link itself) and
    keeps the existing file's permission bits."""
    target = CLAUDE_SETTINGS_PATH.resolve()
    fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        if target.exists():
            os.chmod(tmp_path, stat.S_IMODE(target.stat().st_mode))
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def are_hooks_installed() -> bool:
    """True only if every Clawd Tank hook (event + matcher) is already registered.

    Matcher-aware: a hook whose command is present but under the wrong matcher
    (e.g. a new matcher we started requiring) counts as NOT installed, so the
    menu bar app treats it as outdated and re-runs install_hooks().
    """
    settings = _load_settings()
    if not settings:
        return False
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return False
    for event_name, our_entries in HOOKS_CONFIG.items():
        existing = hooks.get(event_name, [])
        expected_matchers = {_matcher_of(e) for e in our_entries}
        # (a) every expected event+matcher must be present
        for our_entry in our_entries:
            if not _our_hook_present(existing, _matcher_of(our_entry)):
                return False
        # (b) no leftover Clawd Tank group under a matcher we no longer use —
        # otherwise a superseded group would persist forever (install never re-runs).
        if isinstance(existing, list):
            for g in existing:
                if _is_our_managed_group(g) and _matcher_of(g) not in expected_matchers:
                    return False
    return True


def install_hooks() -> bool:
    """Merge Clawd Tank hooks into Claude Code settings without clobbering the user's
    own hooks. For each managed event we drop our OWN prior groups (so a changed
    matcher self-heals instead of leaving a stale duplicate), then append the current
    config only where it isn't already present. The user's groups — and any group the
    user shares with us — are never modified or removed. Idempotent.

    Returns False — leaving the file untouched — when an existing settings file
    cannot be parsed, since rewriting it would discard the user's settings.
    """
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not installing hooks: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    for event_name, our_entries in HOOKS_CONFIG.items():
        existing = hooks.get(event_name)
        if not isinstance(existing, list):
            existing = []
        # Prune our own prior groups (self-heal across matcher/config changes); keep
        # the user's groups and any group the user shares with us untouched.
        kept = [g for g in existing if not _is_our_managed_group(g)]
        for our_entry in our_entries:
            if not _our_hook_present(kept, _matcher_of(our_entry)):
                kept.append(copy.deepcopy(our_entry))
        hooks[event_name] = kept

    _write_settings_atomic(settings)
    logger.info("Installed hooks in %s", CLAUDE_SETTINGS_PATH)
    return True


def uninstall_hooks() -> bool:
    """Remove every Clawd Tank hook group from Claude Code settings.

    Uses the same ownership rule install_hooks() prunes with, applied to every
    event (not only those HOOKS_CONFIG lists today), so groups left by an older
    interpreter, install folder or retired event go too. The user's groups, and
    any group the user shares with us, are left exactly as they are. An event
    list is dropped only when it held nothing but our groups, and the "hooks"
    object only when removing them emptied it. Idempotent; the file is not
    rewritten when nothing of ours is in it.

    Returns True when no hook of ours remains (including when there is no
    settings file, which is left uncreated). Returns False — leaving the file
    untouched — when an existing settings file cannot be parsed.
    """
    if not CLAUDE_SETTINGS_PATH.exists():
        return True

    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not uninstalling hooks: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return True

    changed = False
    for event_name, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept = [g for g in groups if not _is_our_managed_group(g)]
        if len(kept) == len(groups):
            continue
        changed = True
        if kept:
            hooks[event_name] = kept
        else:
            del hooks[event_name]

    if not changed:
        return True
    if not hooks:
        del settings["hooks"]

    _write_settings_atomic(settings)
    logger.info("Uninstalled hooks from %s", CLAUDE_SETTINGS_PATH)
    return True
