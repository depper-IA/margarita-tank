# host/clawd_tank_menubar/hooks.py
"""Install the Claude Code hook script and configure hooks in settings."""

import copy
import json
import logging
import ntpath
import os
import re
import shlex
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
# The same saved command as plain text, written verbatim. The POSIX sh bridge
# reads this instead of picking the string out of the JSON: it has no JSON parser.
STATUSLINE_COMMAND_NAME = "statusline-original.txt"
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


# The same bridge for macOS and Linux, in plain POSIX sh. The Python one above
# needs a working python3, and a Mac may have none (or only the Xcode command
# line tools stub): a statusLine that cannot start would take the user's own
# status line down with it. Windows keeps the Python bridge (margarita-statusline.exe).
STATUSLINE_BRIDGE_SH = textwrap.dedent('''\
    #!/bin/sh
    # statusline_bridge - Claude Code statusLine wrapper for Clawd Tank (macOS, Linux).
    #
    # Claude Code pipes a JSON document (including rate_limits) to the statusLine
    # command on every refresh. This script caches that JSON for the daemon's usage
    # bar, then runs the user's original statusLine command (saved verbatim by the
    # installer in statusline-original.txt) with the same stdin and prints its
    # output, so their status line keeps working.
    #
    # POSIX sh plus cat, mkdir, mv, rm and sleep: no Python and no jq. It must never
    # fail loudly: stderr is discarded and the exit code is always 0.
    #
    # Limits: the original is stopped with SIGTERM after CLAWD_TANK_STATUSLINE_TIMEOUT
    # seconds (default 10), together with its direct children when pgrep exists; a
    # deeper process tree can outlive it. The input is held in a shell variable, so
    # NUL bytes are dropped (a JSON document has none).
    # STATUSLINE_BRIDGE_VERSION: 1

    exec 2>/dev/null

    DIR=${CLAWD_TANK_DIR:-${HOME:+$HOME/.clawd-tank}}
    CACHE="$DIR/statusline-cache.json"
    SAVED="$DIR/statusline-original.txt"
    TIMEOUT=${CLAWD_TANK_STATUSLINE_TIMEOUT:-10}
    case $TIMEOUT in ''|.|*[!0-9.]*) TIMEOUT=10 ;; esac

    # Everything Claude Code sent, byte for byte (the x keeps the trailing newlines).
    INPUT=$(cat; printf x)
    INPUT=${INPUT%x}

    write_cache() {
        [ -n "$DIR" ] || return 0
        # Only a JSON object is cached: its first non-blank character is a brace.
        lead=${INPUT%%[![:space:]]*}
        case ${INPUT#"$lead"} in '{'*) ;; *) return 0 ;; esac
        [ ! -d "$CACHE" ] || return 0
        mkdir -p "$DIR" || return 0
        tmp="$CACHE.$$.tmp"
        # A temp file in the same folder and mv replace the cache atomically; the
        # umask keeps it private to the user.
        if ( umask 077 && printf '%s' "$INPUT" >"$tmp" ) && mv -f "$tmp" "$CACHE"; then
            :
        else
            rm -f "$tmp"
        fi
    }

    run_original() {
        # The payload arrives on stdin; a background job would get /dev/null.
        exec 3<&0
        CLAWD_TANK_STATUSLINE_BRIDGE=1 /bin/sh -c "$COMMAND" <&3 3<&- &
        child=$!
        (
            trap 'kill "$sleeper"; exit 0' TERM
            sleep "$TIMEOUT" &
            sleeper=$!
            wait "$sleeper"
            # Note the children first: once the parent dies they are re-parented.
            kids=$(pgrep -P "$child")
            kill "$child" $kids
        ) >/dev/null 2>&1 3<&- </dev/null &
        watchdog=$!
        wait "$child"
        kill "$watchdog"
    }

    write_cache

    # A bridge that finds itself as the "original" would fork forever.
    [ -z "$CLAWD_TANK_STATUSLINE_BRIDGE" ] || exit 0
    [ -n "$DIR" ] && [ -r "$SAVED" ] || exit 0
    COMMAND=$(cat "$SAVED")
    case $COMMAND in *[![:space:]]*) ;; *) exit 0 ;; esac
    printf '%s' "$INPUT" | run_original
    exit 0
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


def build_statusline_command(platform: str, frozen: bool, executable: str, script_path) -> str:
    """The statusLine command that runs the bridge on `platform`.

    Same rules as build_hook_command(): POSIX runs the executable script through
    its shebang (shell-quoted, since this one is a shell command line that may
    sit under a home directory with spaces); Windows names the interpreter, or
    runs the bundled console exe when frozen.
    """
    if platform == "win32":
        if frozen:
            exe = ntpath.join(ntpath.dirname(executable), STATUSLINE_EXE_NAME)
            return f'"{exe}"'
        return f'"{executable}" "{script_path}"'
    return shlex.quote(str(script_path))


STATUSLINE_COMMAND = build_statusline_command(
    sys.platform, getattr(sys, "frozen", False), sys.executable, STATUSLINE_SCRIPT_PATH
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


def install_statusline_bridge_script() -> None:
    """Write the standalone statusLine bridge to STATUSLINE_SCRIPT_PATH."""
    CLAWD_DIR.mkdir(parents=True, exist_ok=True)
    STATUSLINE_SCRIPT_PATH.write_text(STATUSLINE_BRIDGE_SCRIPT, encoding="utf-8")
    if sys.platform != "win32":
        STATUSLINE_SCRIPT_PATH.chmod(0o755)
    logger.info("Installed statusLine bridge: %s", STATUSLINE_SCRIPT_PATH)


def _statusline_state_path() -> Path:
    return CLAWD_DIR / STATUSLINE_STATE_NAME


def _statusline_is_ours(value) -> bool:
    """True if a settings.statusLine value runs our bridge: the current command,
    or one left by another interpreter / install folder (same script, or the
    bundled exe), so a reinstall replaces it instead of treating it as the
    user's own. A wrapper that merely mentions the script is not ours."""
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    if command == STATUSLINE_COMMAND or command.startswith(STATUSLINE_COMMAND + " "):
        return True
    script = re.escape(str(STATUSLINE_SCRIPT_PATH))
    pattern = (
        '^(?:"[^"]+" "' + script + '"'
        r'|"[^"]*[\\/](?i:' + re.escape(STATUSLINE_EXE_NAME) + ')")( |$)')
    return re.match(pattern, command) is not None


def _write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _wire_statusline(settings: dict) -> None:
    """Point settings.statusLine at the bridge, saving the user's own first.

    An already-ours value is only refreshed (never saved as the "original", or
    the bridge would chain into itself). Extra keys such as `padding` carry over.
    """
    current = settings.get("statusLine")
    state_path = _statusline_state_path()
    if not _statusline_is_ours(current):
        if current is None:
            state_path.unlink(missing_ok=True)
        else:
            _write_json_atomic(state_path, {"statusLine": current})
    base = current if isinstance(current, dict) else {}
    settings["statusLine"] = {**base, "type": "command", "command": STATUSLINE_COMMAND}


def _unwire_statusline(settings: dict) -> bool:
    """Undo _wire_statusline() in `settings`. Returns True if settings changed. A
    statusLine that is not ours (the user replaced it after install) is left alone.

    The saved original is NOT deleted here: the caller removes it only after the
    settings file was written, so a failed write cannot lose the original."""
    state_path = _statusline_state_path()
    if not _statusline_is_ours(settings.get("statusLine")):
        return False
    original = None
    try:
        original = json.loads(state_path.read_text(encoding="utf-8-sig")).get("statusLine")
    except (OSError, ValueError, AttributeError):
        pass
    if original is None:
        del settings["statusLine"]
    else:
        settings["statusLine"] = original
    return True


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


# --- Claude Code mod (the Margarita side panel) -------------------------------
#
# The mod is a plain Claude Code plugin folder shipped with the app (claude-mod/
# in a checkout, bundled as data in the packaged builds). The app copies it to
# ~/.clawd-tank/claude-mod/margarita-band and enables it by listing that folder
# in settings.json env.CLAUDE_CODE_PLUGIN_DIRS: Claude Code loads every folder in
# that os.pathsep-separated list like `--plugin-dir`. It is opt-in and separate
# from the hooks, and enabling or disabling touches only our own entry.

MOD_NAME = "margarita-band"
MOD_DIR = CLAWD_DIR / "claude-mod" / MOD_NAME
PLUGIN_DIRS_ENV = "CLAUDE_CODE_PLUGIN_DIRS"

# Never copied: dependency/cache folders and OS litter.
_MOD_SKIP_DIRS = frozenset({"node_modules", "__pycache__"})
_MOD_SKIP_FILES = frozenset({".DS_Store", "Thumbs.db"})
# Typings Claude Code generates when the mod is developed. Not part of the mod,
# so they are neither copied nor deleted from the installed copy.
_MOD_GENERATED_DIR = (".claude-plugin", "types")


def resolve_mod_source(frozen: bool, executable: str, resourcepath, module_file) -> Path:
    """Where the mod shipped with this build lives.

    A py2app bundle keeps data files under Contents/Resources (RESOURCEPATH); a
    PyInstaller onedir build puts them next to the exe; a checkout keeps the
    mod at the repository root, two folders above this package.
    """
    if frozen:
        base = Path(resourcepath) if resourcepath else Path(executable).parent
    else:
        base = Path(module_file).parents[2]
    return base / "claude-mod" / MOD_NAME


MOD_SOURCE_DIR = resolve_mod_source(
    bool(getattr(sys, "frozen", False)),
    sys.executable,
    os.environ.get("RESOURCEPATH"),
    Path(__file__).resolve(),
)


def _iter_mod_files(root: Path):
    """Relative path of every file the mod consists of under `root`."""
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _MOD_SKIP_DIRS and (rel_dir / d).parts != _MOD_GENERATED_DIR
        )
        for name in sorted(filenames):
            if name not in _MOD_SKIP_FILES:
                yield rel_dir / name


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Temp file + os.replace, so a Claude Code session loading the mod while the
    app refreshes it never reads a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def install_mod_files() -> bool:
    """Make MOD_DIR an exact copy of the bundled mod. Safe to run on every start:
    only files whose content differs are written, files the mod no longer ships
    are removed, and the typings Claude Code generated in the copy are kept.

    Returns False — without raising — when the build carries no mod or the copy
    fails, so a caller can tell the user instead of crashing the tray app."""
    if not MOD_SOURCE_DIR.is_dir():
        logger.error("Not installing the Claude Code mod: %s not found", MOD_SOURCE_DIR)
        return False
    try:
        wanted = set(_iter_mod_files(MOD_SOURCE_DIR))
        MOD_DIR.mkdir(parents=True, exist_ok=True)
        for rel in sorted(wanted):
            data = (MOD_SOURCE_DIR / rel).read_bytes()
            target = MOD_DIR / rel
            if target.is_file() and target.read_bytes() == data:
                continue
            _write_bytes_atomic(target, data)
        for rel in list(_iter_mod_files(MOD_DIR)):
            if rel not in wanted:
                (MOD_DIR / rel).unlink()
        # Folders emptied by the removals above (deepest first; the root stays).
        for dirpath, _dirs, _files in os.walk(MOD_DIR, topdown=False):
            rel_dir = Path(dirpath).relative_to(MOD_DIR)
            if rel_dir.parts and rel_dir.parts[:2] != _MOD_GENERATED_DIR and not any(Path(dirpath).iterdir()):
                Path(dirpath).rmdir()
    except OSError:
        logger.exception("Could not install the Claude Code mod into %s", MOD_DIR)
        return False
    logger.info("Installed Claude Code mod: %s", MOD_DIR)
    return True


def _is_our_mod_entry(entry: str) -> bool:
    """True if one plugin-folder entry names MOD_DIR (any spelling of the same
    folder: trailing separator, `~`, case on Windows)."""
    entry = entry.strip()
    if not entry:
        return False
    def normal(p):
        return os.path.normcase(os.path.normpath(os.path.expanduser(p)))
    return normal(entry) == normal(str(MOD_DIR))


def _plugin_dir_entries(settings: dict):
    """(env, entries): the settings `env` object and the folders listed in its
    CLAUDE_CODE_PLUGIN_DIRS. (None, None) when either has a shape we cannot
    edit safely (an `env` that is not an object, a value that is not a string)."""
    env = settings.get("env")
    if env is None:
        return {}, []
    if not isinstance(env, dict):
        return None, None
    value = env.get(PLUGIN_DIRS_ENV)
    if value is None:
        return env, []
    if not isinstance(value, str):
        return None, None
    return env, value.split(os.pathsep)


def _remove_mod_entry(settings: dict) -> bool:
    """Drop our folder from env.CLAUDE_CODE_PLUGIN_DIRS in `settings`. Returns True
    if settings changed. The user's other folders stay; the key goes when ours was
    the last one, and `env` goes only when removing the key emptied it."""
    env, entries = _plugin_dir_entries(settings)
    if not entries:
        return False
    kept = [e for e in entries if not _is_our_mod_entry(e)]
    if len(kept) == len(entries):
        return False
    kept = [e for e in kept if e.strip()]
    if kept:
        env[PLUGIN_DIRS_ENV] = os.pathsep.join(kept)
    else:
        del env[PLUGIN_DIRS_ENV]
        if not env:
            del settings["env"]
    return True


def is_mod_enabled() -> bool:
    """True if settings.json lists our mod folder in CLAUDE_CODE_PLUGIN_DIRS."""
    settings = _load_settings()
    if not settings:
        return False
    _env, entries = _plugin_dir_entries(settings)
    return any(_is_our_mod_entry(e) for e in entries or [])


def enable_mod() -> bool:
    """Add MOD_DIR to env.CLAUDE_CODE_PLUGIN_DIRS, after the user's own folders.
    Idempotent: the file is not rewritten when our folder is already listed.

    Returns False — leaving the file untouched — when the settings file cannot be
    parsed, or `env` / the variable has a shape we cannot extend safely."""
    CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not enabling the Claude Code mod: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False
    env, entries = _plugin_dir_entries(settings)
    if entries is None:
        logger.warning(
            "Not enabling the Claude Code mod: env.%s in %s is not a string; left untouched",
            PLUGIN_DIRS_ENV, CLAUDE_SETTINGS_PATH,
        )
        return False
    if any(_is_our_mod_entry(e) for e in entries):
        return True
    env[PLUGIN_DIRS_ENV] = os.pathsep.join([e for e in entries if e.strip()] + [str(MOD_DIR)])
    settings["env"] = env
    _write_settings_atomic(settings)
    logger.info("Enabled Claude Code mod in %s", CLAUDE_SETTINGS_PATH)
    return True


def disable_mod() -> bool:
    """Remove only our folder from env.CLAUDE_CODE_PLUGIN_DIRS. The copied files
    stay where they are. Idempotent; the file is not rewritten (or created) when
    our folder is not listed.

    Returns True when our folder is no longer listed. Returns False — leaving the
    file untouched — when an existing settings file cannot be parsed."""
    if not CLAUDE_SETTINGS_PATH.exists():
        return True
    settings = _load_settings()
    if settings is None:
        logger.warning(
            "Not disabling the Claude Code mod: %s is not a readable JSON object; left untouched",
            CLAUDE_SETTINGS_PATH,
        )
        return False
    if not _remove_mod_entry(settings):
        return True
    _write_settings_atomic(settings)
    logger.info("Disabled Claude Code mod in %s", CLAUDE_SETTINGS_PATH)
    return True


def install_mod() -> bool:
    """Copy (or refresh) the mod files, then enable the mod. The settings file is
    only touched once the folder it points at exists."""
    return install_mod_files() and enable_mod()


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
    statusline = settings.get("statusLine")
    return (isinstance(statusline, dict)
            and statusline.get("command") == STATUSLINE_COMMAND)


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

    _wire_statusline(settings)

    _write_settings_atomic(settings)
    logger.info("Installed hooks in %s", CLAUDE_SETTINGS_PATH)
    return True


def uninstall_hooks() -> bool:
    """Remove every Clawd Tank hook group from Claude Code settings and restore
    the user's original statusLine (or drop ours when there was none). Our
    Claude Code mod folder is dropped from env.CLAUDE_CODE_PLUGIN_DIRS too, so
    Claude Code is not left pointing at a folder the uninstaller is removing.

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

    is_unwired = _unwire_statusline(settings)
    changed = _remove_mod_entry(settings) or is_unwired

    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        hooks_changed = False
        for event_name, groups in list(hooks.items()):
            if not isinstance(groups, list):
                continue
            kept = [g for g in groups if not _is_our_managed_group(g)]
            if len(kept) == len(groups):
                continue
            hooks_changed = True
            if kept:
                hooks[event_name] = kept
            else:
                del hooks[event_name]
        if hooks_changed and not hooks:
            del settings["hooks"]
        changed = changed or hooks_changed

    if not changed:
        return True

    _write_settings_atomic(settings)
    if is_unwired:
        _statusline_state_path().unlink(missing_ok=True)
    logger.info("Uninstalled hooks from %s", CLAUDE_SETTINGS_PATH)
    return True
