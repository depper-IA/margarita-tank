"""End-to-end test of the embedded NOTIFY_SCRIPT: write it to a tempfile,
invoke as a subprocess with a hook payload on stdin, assert it writes the
expected JSON to the daemon's ingress — a Unix socket on POSIX, an
authenticated loopback TCP connection on Windows.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from clawd_tank_menubar.hooks import NOTIFY_SCRIPT
from clawd_tank_daemon.protocol import hook_payload_to_daemon_message

WINDOWS = sys.platform == "win32"


def _make_sock_path() -> str:
    """Return the path the script will be pointed at through CLAWD_TANK_SOCKET.

    POSIX: the Unix socket itself, which must be short — pytest's tmp_path on
    macOS expands to a very long path under /private/var/folders/... that
    exceeds AF_UNIX's 104-byte limit, so it goes in /tmp instead.
    Windows: the endpoint file the daemon publishes its port and token in. No
    length limit applies, so the platform temp directory is fine.
    """
    fd, path = tempfile.mkstemp(
        prefix="ct_",
        suffix=".json" if WINDOWS else ".sock",
        dir=None if WINDOWS else "/tmp",
    )
    os.close(fd)
    os.unlink(path)  # bind() requires the file to not exist
    return path


def _listen(sock_path: str) -> tuple[socket.socket, str]:
    """Bind the ingress the script will connect to, returning it and the token
    it must present. On Windows the port and token are published exactly the way
    SocketServer publishes them; on POSIX there is no token."""
    if WINDOWS:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        token = secrets.token_urlsafe(32)
        Path(sock_path).write_text(
            json.dumps({"port": srv.getsockname()[1], "token": token}),
            encoding="utf-8",
        )
    else:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path)
        token = ""
    srv.listen(1)
    srv.settimeout(5.0)
    return srv, token


def _run_script_with_payload(payload: dict, sock_path: str,
                             auth_out: list | None = None) -> dict:
    """Run NOTIFY_SCRIPT in a subprocess with payload on stdin; return the JSON
    message it sent to the ingress. Returns {} if nothing arrived.

    The token is enforced, not just observed: a script that failed to
    authenticate delivers nothing, so every test here covers the handshake.
    Pass auth_out to also capture the line the script offered as its token.
    """
    received = {}
    srv, token = _listen(sock_path)

    def server():
        try:
            conn, _ = srv.accept()
            data = b""
            conn.settimeout(2.0)
            while True:
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                data += chunk
            conn.close()
            lines = data.decode("utf-8").splitlines()
            if WINDOWS:
                offered = lines.pop(0) if lines else ""
                if auth_out is not None:
                    auth_out.append(offered)
                if offered != token:
                    return
            if lines and lines[0].strip():
                received.update(json.loads(lines[0]))
        except socket.timeout:
            pass
        finally:
            srv.close()
            try:
                os.unlink(sock_path)
            except (FileNotFoundError, PermissionError):
                pass

    t = threading.Thread(target=server)
    t.start()

    # encoding="utf-8" matches install_notify_script(); without it Windows
    # writes the script in the locale codepage and the interpreter refuses
    # to parse its own source.
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as f:
        f.write(NOTIFY_SCRIPT)
        script_path = f.name
    os.chmod(script_path, 0o755)

    try:
        # Override the socket path the script uses via env (we'll modify the
        # script to honor CLAWD_TANK_SOCKET if set — see Step 3).
        env = os.environ.copy()
        env["CLAWD_TANK_SOCKET"] = sock_path
        subprocess.run(
            [sys.executable, script_path],
            input=json.dumps(payload).encode("utf-8"),
            env=env,
            timeout=5.0,
            capture_output=True,
        )
    finally:
        os.unlink(script_path)

    t.join(timeout=3.0)
    return received


def _assert_pid(msg: dict) -> None:
    """The script stamps the resolved Claude Code PID on POSIX. On Windows it
    stamps a claude.exe ancestor's PID, or none at all when there is no such
    ancestor — see NOTIFY_SCRIPT._find_claude_pid — so the daemon never watches
    a PID that is not Claude Code's. Which one depends on whether this suite
    itself runs under Claude Code."""
    if WINDOWS:
        pid = msg.get("pid")
        if pid is not None:
            from clawd_tank_daemon.pid_resolver import _windows_process_table
            _, name = _windows_process_table()[pid]
            assert name.lower() == "claude.exe"
    else:
        assert isinstance(msg.get("pid"), int)
        assert msg["pid"] > 0


def test_notify_script_stamps_pid_on_session_start(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SessionStart",
        "session_id": "test-session-123",
        "cwd": str(tmp_path),
        "source": "startup",
    }, sock_path)
    assert msg.get("event") == "session_start"
    assert msg.get("session_id") == "test-session-123"
    _assert_pid(msg)
    assert msg.get("source") == "startup"


def test_notify_script_stamps_pid_on_stop(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "Stop",
        "session_id": "s2",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "add"
    assert msg.get("hook") == "Stop"
    _assert_pid(msg)


def test_notify_script_session_end_includes_reason(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SessionEnd",
        "session_id": "s3",
        "reason": "logout",
    }, sock_path)
    assert msg.get("event") == "dismiss"
    assert msg.get("hook") == "SessionEnd"
    assert msg.get("reason") == "logout"
    _assert_pid(msg)


def test_notify_script_irrelevant_hook_sends_nothing(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "SomeUnhandledEvent",  # not handled
        "session_id": "s4",
    }, sock_path)
    assert msg == {}


def test_notify_script_post_tool_use_produces_tool_done(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PostToolUse",
        "session_id": "s5",
        "tool_name": "AskUserQuestion",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "tool_done"
    assert msg.get("session_id") == "s5"
    assert msg.get("tool_name") == "AskUserQuestion"
    _assert_pid(msg)


def test_notify_script_permission_request_produces_permission(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PermissionRequest",
        "session_id": "s6",
        "tool_name": "Bash",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "permission"
    assert msg.get("session_id") == "s6"
    assert msg.get("tool_name") == "Bash"
    _assert_pid(msg)


def test_notify_script_post_tool_use_failure_produces_tool_failed(tmp_path):
    sock_path = _make_sock_path()
    msg = _run_script_with_payload({
        "hook_event_name": "PostToolUseFailure",
        "session_id": "s7",
        "tool_name": "Read",
        "cwd": str(tmp_path),
    }, sock_path)
    assert msg.get("event") == "tool_failed"
    assert msg.get("session_id") == "s7"
    assert msg.get("tool_name") == "Read"
    _assert_pid(msg)


# --- Cross-validate the embedded script against the daemon-side converter ---
# The NOTIFY_SCRIPT is stdlib-only and cannot import protocol.py, so the two
# hook->message mappings are duplicated and must stay in sync. This guards drift.

_CROSS_CHECK_HOOKS = [
    {"hook_event_name": "SessionStart", "session_id": "s", "cwd": "/x/proj", "source": "startup"},
    {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": "/x/proj", "tool_name": "Bash"},
    {"hook_event_name": "PostToolUse", "session_id": "s", "cwd": "/x/proj", "tool_name": "AskUserQuestion"},
    {"hook_event_name": "PermissionRequest", "session_id": "s", "cwd": "/x/proj", "tool_name": "Bash"},
    {"hook_event_name": "PostToolUseFailure", "session_id": "s", "cwd": "/x/proj", "tool_name": "Read"},
    {"hook_event_name": "PreCompact", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "Stop", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "StopFailure", "session_id": "s", "cwd": "/x/proj", "error": "boom"},
    {"hook_event_name": "Notification", "notification_type": "idle_prompt",
     "session_id": "s", "cwd": "/x/proj", "message": "m"},
    {"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": "/x/proj"},
    {"hook_event_name": "SessionEnd", "session_id": "s", "cwd": "/x/proj", "reason": "logout"},
    {"hook_event_name": "SubagentStart", "session_id": "s", "cwd": "/x/proj", "agent_id": "a"},
    {"hook_event_name": "SubagentStop", "session_id": "s", "cwd": "/x/proj", "agent_id": "a"},
]


@pytest.mark.parametrize("hook", _CROSS_CHECK_HOOKS,
                         ids=[h["hook_event_name"] for h in _CROSS_CHECK_HOOKS])
def test_notify_script_matches_protocol_converter(hook):
    """The embedded NOTIFY_SCRIPT must emit the same daemon message as the daemon-side
    protocol.hook_payload_to_daemon_message (modulo pid, which the script computes from
    the process tree while protocol reads it from the payload)."""
    sock_path = _make_sock_path()
    script_msg = _run_script_with_payload(hook, sock_path)
    proto_msg = hook_payload_to_daemon_message(hook) or {}
    script_msg.pop("pid", None)
    proto_msg = {k: v for k, v in proto_msg.items() if k != "pid"}
    assert script_msg == proto_msg


# --- Windows ingress handshake -----------------------------------------------


@pytest.mark.skipif(not WINDOWS, reason="only the Windows ingress is authenticated")
def test_notify_script_presents_the_published_token_first():
    """The script must read the token the daemon published and send it ahead of
    the message; without it the server closes the connection unread."""
    sock_path = _make_sock_path()
    offered: list[str] = []
    msg = _run_script_with_payload(
        {"hook_event_name": "Stop", "session_id": "s8", "cwd": "/x/proj"},
        sock_path, auth_out=offered,
    )
    assert msg.get("event") == "add"  # delivered, so the token matched
    assert offered and offered[0]
    assert offered[0] != json.dumps(msg)  # it is the token line, not the payload


@pytest.mark.skipif(not WINDOWS, reason="only the Windows ingress is authenticated")
def test_notify_script_stays_quiet_when_the_endpoint_file_is_unusable():
    """A stale, truncated or missing endpoint file must make the hook a no-op, not
    a crash: notifications are best-effort and a non-zero exit is noise in
    Claude Code."""
    for content in (None, "", "{}", "not json"):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "endpoint.json"
            if content is not None:
                path.write_text(content, encoding="utf-8")

            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                             encoding="utf-8") as f:
                f.write(NOTIFY_SCRIPT)
                script_path = f.name
            try:
                env = os.environ.copy()
                env["CLAWD_TANK_SOCKET"] = str(path)
                result = subprocess.run(
                    [sys.executable, script_path],
                    input=json.dumps({"hook_event_name": "Stop", "session_id": "s",
                                      "cwd": "/x/proj"}).encode("utf-8"),
                    env=env, timeout=5.0, capture_output=True,
                )
            finally:
                os.unlink(script_path)
            assert result.returncode == 0, f"endpoint {content!r}: {result.stderr}"
