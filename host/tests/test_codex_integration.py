"""End-to-end: a Codex hook payload, translated and fed through the daemon, drives
the same display animations as a Claude Code session — and the two agents coexist
as separate crab slots.

This exercises the real path: codex_protocol translation -> daemon._handle_message ->
per-session state -> _compute_display_state, without any transport or hardware.
"""

import asyncio

from clawd_tank_daemon.daemon import ClawdDaemon
from clawd_tank_daemon.codex_protocol import (
    codex_hook_payload_to_daemon_message,
    CODEX_SESSION_PREFIX,
)


def make_daemon():
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    return d


def feed_codex(d, hook):
    """Translate a Codex hook payload and run it through the daemon, like the socket
    server would for a real event."""
    msg = codex_hook_payload_to_daemon_message(hook)
    assert msg is not None, f"event {hook.get('hook_event_name')} should translate"
    asyncio.run(d._handle_message(msg))
    return msg


def test_codex_shell_tool_shows_building():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    feed_codex(d, {
        "hook_event_name": "PreToolUse", "session_id": "cx", "cwd": "/p",
        "tool_name": "shell",
    })
    state = d._compute_display_state()
    # Codex "shell" -> "Bash" -> "building".
    assert state["anims"] == ["building"]


def test_codex_apply_patch_shows_typing():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    feed_codex(d, {
        "hook_event_name": "PreToolUse", "session_id": "cx", "cwd": "/p",
        "tool_name": "apply_patch",
    })
    # "apply_patch" -> "Write" -> "typing".
    assert d._compute_display_state()["anims"] == ["typing"]


def test_codex_mcp_tool_shows_beacon():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    feed_codex(d, {
        "hook_event_name": "PreToolUse", "session_id": "cx", "cwd": "/p",
        "tool_name": "mcp__srv__call",
    })
    assert d._compute_display_state()["anims"] == ["beacon"]


def test_codex_prompt_submit_shows_thinking():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    feed_codex(d, {"hook_event_name": "UserPromptSubmit", "session_id": "cx"})
    assert d._compute_display_state()["anims"] == ["thinking"]


def test_codex_permission_shows_alert():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    feed_codex(d, {
        "hook_event_name": "PermissionRequest", "session_id": "cx", "cwd": "/p",
        "tool_name": "shell",
    })
    assert d._compute_display_state()["anims"] == ["alert"]


def test_codex_and_claude_coexist_as_two_crabs():
    """A Codex session and a Claude session with the SAME raw id must not collide:
    the codex: prefix keeps them as two separate slots."""
    d = make_daemon()
    # Claude session (raw id "dup") working on a Bash tool -> building.
    asyncio.run(d._handle_message({
        "event": "session_start", "session_id": "dup", "project": "p", "pid": None,
    }))
    asyncio.run(d._handle_message({
        "event": "tool_use", "session_id": "dup", "tool_name": "Bash",
        "project": "p", "pid": None,
    }))
    # Codex session with the SAME raw id "dup" editing -> typing.
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "dup", "cwd": "/p"})
    feed_codex(d, {
        "hook_event_name": "PreToolUse", "session_id": "dup", "cwd": "/p",
        "tool_name": "apply_patch",
    })
    state = d._compute_display_state()
    # Two distinct slots, not one overwriting the other.
    assert len(state["anims"]) == 2
    assert set(state["anims"]) == {"building", "typing"}
    assert ("dup" in d._session_states) and (CODEX_SESSION_PREFIX + "dup" in d._session_states)


def test_codex_session_end_removes_slot():
    d = make_daemon()
    feed_codex(d, {"hook_event_name": "SessionStart", "session_id": "cx", "cwd": "/p"})
    assert d._compute_display_state().get("anims") == ["idle"]
    feed_codex(d, {"hook_event_name": "SessionEnd", "session_id": "cx"})
    # No sessions left -> sleeping.
    assert d._compute_display_state() == {"status": "sleeping"}
