# host/clawd_tank_menubar/hooks.py
"""Install the Claude Code hook script and configure hooks in settings."""

import copy
import json
import logging
import os
import re
import stat
import sys
import tempfile
import textwrap
from pathlib import Path

from clawd_tank_daemon.protocol import ASK_USER_QUESTION_TOOL

logger = logging.getLogger("clawd-tank.hooks")

CLAWD_DIR = Path.home() / ".clawd-tank"
# Windows cannot execute an extensionless file with a shebang, and the command
# below names the interpreter explicitly, so the script needs the .py suffix
# for that interpreter to accept it.
NOTIFY_SCRIPT_PATH = CLAWD_DIR / (
    "clawd-tank-notify.py" if sys.platform == "win32" else "clawd-tank-notify"
)
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# Standalone hook script — uses only Python stdlib, no external imports.
NOTIFY_SCRIPT = textwrap.dedent('''\
    #!/usr/bin/env python3
    """clawd-tank-notify - Claude Code hook handler for Clawd Tank.

    Reads hook payload from stdin, converts it to a daemon message, and forwards
    it to the daemon: a Unix socket on POSIX, an authenticated loopback TCP
    connection on Windows. No external dependencies.
    """
    # NOTIFY_SCRIPT_VERSION: 2026-09-12-windows-ingress

    import json
    import os
    import re
    import socket
    import subprocess
    import sys
    from pathlib import Path

    # POSIX: the Unix socket itself. Windows: the file the daemon publishes its
    # loopback port and shared secret in.
    SOCKET_PATH = os.environ.get(
        "CLAWD_TANK_SOCKET",
        str(Path.home() / ".clawd-tank"
            / ("endpoint.json" if sys.platform == "win32" else "sock")),
    )

    _CLAUDE_ARGV_RE = re.compile(r"(^|/)claude($|\\s)")


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


    def _find_claude_pid():
        """Walk from os.getppid() up the process tree to find the long-lived
        Claude Code PID. Falls back to os.getppid() if no `claude` ancestor.

        Mirrors clawd_tank_daemon/pid_resolver.py — keep in sync.

        Returns None on Windows, where the daemon then falls back to the
        staleness timeout: there is no `ps`, a Toolhelp32 snapshot exposes image
        names but not the argv that identifies a node-hosted `claude`, and the
        hook itself runs under a shell that exits the moment it returns. Sending
        that shell's PID would be worse than sending none — the daemon would see
        it die and evict a session that is very much alive.
        """
        if sys.platform == "win32":
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
                "project": project or "unknown",
                "message": "Waiting for input",
                "pid": pid,
            }

        if event_name == "StopFailure":
            message = hook.get("error", "") or hook.get("stop_reason", "") or "API error"
            return {
                "event": "add",
                "hook": "StopFailure",
                "session_id": session_id,
                "project": project or "unknown",
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
                "project": project or "unknown",
                "message": hook.get("message", "Waiting for input"),
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
''')

# POSIX runs the script directly through its shebang. Windows has no shebang
# support, so the interpreter is named explicitly. A .cmd shim would work too,
# but it puts a second process between Claude Code and the hook on the hot path
# of every event, for nothing.
if sys.platform == "win32":
    # Quoted because either path may contain spaces; Claude Code hands the
    # command to `cmd.exe /d /s /c "<command>"`, which strips only the outer
    # pair and passes the rest through verbatim.
    HOOK_COMMAND = f'"{sys.executable}" "{NOTIFY_SCRIPT_PATH}"'
else:
    HOOK_COMMAND = str(NOTIFY_SCRIPT_PATH)

HOOKS_CONFIG = {
    "SessionStart": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "Stop": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "StopFailure": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "Notification": [
        {
            "matcher": "idle_prompt",
            "hooks": [{"type": "command", "command": HOOK_COMMAND}],
        }
    ],
    "UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "PreToolUse": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    # Scoped to AskUserQuestion only: the sole purpose is clearing the "waiting
    # for input" alert when the user answers. Registering PostToolUse for every
    # tool would double the device's event/BLE traffic for no added value.
    "PostToolUse": [
        {
            "matcher": ASK_USER_QUESTION_TOOL,
            "hooks": [{"type": "command", "command": HOOK_COMMAND}],
        }
    ],
    # Claude is blocked waiting for the user to approve a tool → waiting/alert.
    "PermissionRequest": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    # A tool genuinely errored (not a non-zero shell exit) → confused.
    "PostToolUseFailure": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "PreCompact": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "SessionEnd": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "SubagentStart": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
    "SubagentStop": [
        {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ],
}


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
if sys.platform == "win32":
    _OUR_COMMAND_RE = re.compile(
        '^"[^"]+" "' + re.escape(str(NOTIFY_SCRIPT_PATH)) + '"( |$)')
else:
    _OUR_COMMAND_RE = None


def _command_is_ours(command) -> bool:
    """True only if a hook command actually invokes our notify script — the exact
    path, or the path followed by args. A command that merely CONTAINS the path as a
    substring (a wrapper, or `cat <path>`) is not ours."""
    if not isinstance(command, str):
        return False
    if _OUR_COMMAND_RE is not None:
        return _OUR_COMMAND_RE.match(command) is not None
    return command == HOOK_COMMAND or command.startswith(HOOK_COMMAND + " ")


def _group_runs_our_command(entry: dict) -> bool:
    """True if a hook group contains a hook that runs the Clawd Tank notify script."""
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list):
        return False
    return any(isinstance(h, dict) and _command_is_ours(h.get("command", "")) for h in hooks_list)


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
    """True if some existing group with the same matcher already runs our command."""
    if not isinstance(existing_entries, list):
        return False
    for entry in existing_entries:
        if _matcher_of(entry) == our_matcher and _group_runs_our_command(entry):
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
