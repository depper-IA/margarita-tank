"""Translate OpenAI Codex CLI hook payloads into the daemon's normalized messages.

Codex CLI exposes lifecycle hooks whose event names and JSON fields overlap almost
one-to-one with Claude Code's (SessionStart, PreToolUse, PostToolUse, PermissionRequest,
UserPromptSubmit, Stop, SubagentStart/Stop, SessionEnd, PreCompact; fields session_id,
cwd, tool_name, hook_event_name). This module reuses that normalized vocabulary so the
daemon reacts to a Codex session exactly as it does to a Claude Code one — no daemon
changes needed. See the shared contract in protocol.hook_payload_to_daemon_message.

Format reference: OpenAI Codex hooks documentation (public spec, not vendored code).
Config lives at ~/.codex/config.toml ([hooks] tables) or ~/.codex/hooks.json.

Two Codex-specific concerns are handled here:
  1. Session IDs are namespaced with a "codex:" prefix so a Codex session and a Claude
     session that happen to share an ID get separate crab slots.
  2. Codex tool names are mapped to the daemon's existing animation vocabulary. Codex's
     shell/apply_patch/MCP tools map onto the same TOOL_ANIMATION_MAP the daemon already
     uses, so most names pass straight through.
"""

from pathlib import Path
from typing import Optional

# Prefix that keeps Codex session IDs from colliding with Claude Code's in the
# daemon's per-session state. The daemon treats session_id as an opaque key, so a
# prefix is enough to give each agent its own crab.
CODEX_SESSION_PREFIX = "codex:"

# Fixed display name on Codex notification cards, mirroring protocol.DISPLAY_NAME
# for Claude. Kept here so the Codex card can read differently if desired later.
CODEX_DISPLAY_NAME = "Codex"

# Codex tool name -> the daemon's tool name (which TOOL_ANIMATION_MAP keys on).
# Codex surfaces shell as "Bash" and file edits as "Write"/"Edit" already, so those
# pass through unchanged; this table only remaps the few that differ. Unmapped tools
# fall through to the daemon's default (typing), and any "mcp__" prefix is detected by
# the daemon's _tool_to_anim as the MCP beacon, same as Claude.
CODEX_TOOL_ALIASES = {
    "shell": "Bash",
    "apply_patch": "Write",
    "local_shell": "Bash",
}


def _codex_tool_name(raw: str) -> str:
    """Normalize a Codex tool name to the daemon's vocabulary. An MCP tool keeps its
    `mcp__` prefix so the daemon maps it to the beacon animation."""
    if not raw:
        return ""
    if raw.startswith("mcp__"):
        return raw
    return CODEX_TOOL_ALIASES.get(raw, raw)


def _namespaced(session_id: str) -> str:
    """Prefix a Codex session ID so it never collides with a Claude session's."""
    sid = session_id or ""
    return f"{CODEX_SESSION_PREFIX}{sid}" if sid else sid


def codex_hook_payload_to_daemon_message(hook: dict) -> Optional[dict]:
    """Convert a Codex CLI hook stdin payload to a daemon message.

    Mirrors protocol.hook_payload_to_daemon_message but for Codex's event vocabulary.
    Returns None if the hook event is not relevant (ignored). The emitted message uses
    the SAME schema the daemon already consumes, with a namespaced session_id.
    """
    event_name = hook.get("hook_event_name", "")
    session_id = _namespaced(hook.get("session_id", ""))
    cwd = hook.get("cwd", "")
    project = Path(cwd).name if cwd else ""
    # Codex does not expose a hostable long-lived PID the way the Claude hook resolver
    # finds claude.exe; omit it. The daemon then evicts the session on the shorter
    # no-PID staleness timeout instead of PID liveness, which is correct for Codex.
    pid = None

    if event_name == "SessionStart":
        msg = {
            "event": "session_start",
            "session_id": session_id,
            "project": project,
            "pid": pid,
        }
        source = hook.get("source") or hook.get("matcher")
        if source is not None:
            msg["source"] = source
        return msg

    if event_name == "PreToolUse":
        return {
            "event": "tool_use",
            "session_id": session_id,
            "tool_name": _codex_tool_name(hook.get("tool_name", "")),
            "project": project,
            "pid": pid,
        }

    if event_name == "PostToolUse":
        return {
            "event": "tool_done",
            "session_id": session_id,
            "tool_name": _codex_tool_name(hook.get("tool_name", "")),
            "project": project,
            "pid": pid,
        }

    if event_name == "PermissionRequest":
        return {
            "event": "permission",
            "session_id": session_id,
            "tool_name": _codex_tool_name(hook.get("tool_name", "")),
            "project": project,
            "pid": pid,
        }

    if event_name in ("PreCompact", "PostCompact"):
        # Only PreCompact drives the sweeping oneshot; PostCompact is ignored (the
        # daemon has no post-compact behavior and would just stamp last_event).
        if event_name == "PostCompact":
            return None
        return {
            "event": "compact",
            "session_id": session_id,
            "pid": pid,
        }

    if event_name == "Stop":
        return {
            "event": "add",
            "hook": "Stop",
            "session_id": session_id,
            "project": CODEX_DISPLAY_NAME,
            "message": "Esperando tu respuesta",
            "pid": pid,
        }

    if event_name == "UserPromptSubmit":
        return {
            "event": "dismiss",
            "hook": "UserPromptSubmit",
            "session_id": session_id,
            "pid": pid,
        }

    if event_name == "SessionEnd":
        msg = {
            "event": "dismiss",
            "hook": "SessionEnd",
            "session_id": session_id,
            "pid": pid,
        }
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
