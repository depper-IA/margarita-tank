"""Tests for gating animation names by each transport's protocol version.

Protocol v3 firmware accepts "happy", "low_battery" and "hat_mishap" in
set_sessions. v2 firmware drops a slot whose animation name it doesn't know,
so the daemon must downgrade those names for v2 transports.
"""

import asyncio
import json
import time

import pytest
from unittest.mock import AsyncMock

import clawd_tank_daemon.daemon as daemon_mod
from clawd_tank_daemon.daemon import (
    MIN_PROTOCOL_FOR_PHASE1_ANIMS,
    PHASE1_ANIM_FALLBACKS,
    SIM_PROTOCOL_VERSION,
    ClawdDaemon,
    LOW_BATTERY_USAGE_PCT,
    downgrade_display_state,
)


class MockTransport:
    def __init__(self):
        self.is_connected = True
        self.written: list[str] = []

    async def write_notification(self, payload: str) -> None:
        self.written.append(payload)


def make_daemon(**versions):
    """Daemon with one MockTransport per keyword, at the given protocol version."""
    d = ClawdDaemon(sim_only=True)
    d._transports.clear()
    d._transport_queues.clear()
    transports = {}
    for name, version in versions.items():
        t = MockTransport()
        d._transports[name] = t
        d._transport_queues[name] = asyncio.Queue()
        d._transport_versions[name] = version
        transports[name] = t
    return d, transports


def _add_session(d, sid, state_dict):
    d._session_states[sid] = state_dict
    d._session_order.append((sid, d._next_display_id))
    d._next_display_id += 1


def sessions_of(transport):
    return [json.loads(p) for p in transport.written
            if json.loads(p).get("action") == "set_sessions"]


# --- Constants and the pure downgrade helper ---


def test_min_protocol_constant_is_three():
    assert MIN_PROTOCOL_FOR_PHASE1_ANIMS == 3


def test_fallback_mapping():
    assert PHASE1_ANIM_FALLBACKS == {
        "low_battery": "idle",
        "hat_mishap": "confused",
        "happy": "idle",
    }


def test_downgrade_maps_new_names_for_v2():
    state = {"anims": ["low_battery", "hat_mishap", "happy", "typing"],
             "ids": [1, 2, 3, 4], "subagents": 0}
    out = downgrade_display_state(state, 2)
    assert out["anims"] == ["idle", "confused", "idle", "typing"]
    assert out["ids"] == [1, 2, 3, 4]
    # The input is not mutated: other transports still need the original.
    assert state["anims"] == ["low_battery", "hat_mishap", "happy", "typing"]


def test_downgrade_keeps_new_names_for_v3():
    state = {"anims": ["low_battery", "hat_mishap", "happy"], "ids": [1, 2, 3], "subagents": 0}
    assert downgrade_display_state(state, 3) == state


def test_downgrade_passes_status_states_through():
    assert downgrade_display_state({"status": "sleeping"}, 2) == {"status": "sleeping"}


# --- Regular broadcasts ---


@pytest.mark.asyncio
async def test_v2_transport_gets_confused_instead_of_hat_mishap():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "WebFetch"})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "WebFetch"})
    assert sessions_of(t["ble"])[-1]["anims"] == ["confused"]
    assert not any("hat_mishap" in p for p in t["ble"].written)


@pytest.mark.asyncio
async def test_v3_transport_gets_hat_mishap():
    d, t = make_daemon(ble=3)
    _add_session(d, "s1", {"state": "working", "last_event": time.time(), "tool_name": "WebFetch"})
    await d._handle_message({"event": "tool_failed", "session_id": "s1", "tool_name": "WebFetch"})
    assert sessions_of(t["ble"])[-1]["anims"] == ["hat_mishap"]


@pytest.mark.asyncio
async def test_v2_transport_gets_idle_instead_of_low_battery():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    d._latest_usage = {"session_pct": LOW_BATTERY_USAGE_PCT, "weekly_pct": 0}
    await d._broadcast_display_state_if_changed(force=True)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_mixed_transports_each_get_their_own_payload():
    d, t = make_daemon(ble=2, sim=3)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})
    d._latest_usage = {"session_pct": 0, "weekly_pct": LOW_BATTERY_USAGE_PCT + 5}
    await d._broadcast_display_state_if_changed(force=True)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle", "confused"]
    assert sessions_of(t["sim"])[-1]["anims"] == ["low_battery", "hat_mishap"]
    # The cached display state keeps the real (undowngraded) names.
    assert d._last_display_state["anims"] == ["low_battery", "hat_mishap"]


@pytest.mark.asyncio
async def test_v1_transport_still_gets_set_status_mapping():
    d, t = make_daemon(ble=1)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})
    await d._broadcast_display_state_if_changed(force=True)
    payloads = [json.loads(p) for p in t["ble"].written]
    assert payloads == [{"action": "set_status", "status": "confused"}]


# --- Oneshots ---


STOP_MSG = {"event": "add", "hook": "Stop", "session_id": "aaa",
            "project": "p", "message": "Waiting"}


@pytest.mark.asyncio
async def test_v2_transport_gets_no_happy_oneshot_on_end_of_turn():
    d, t = make_daemon(ble=2)
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    t["ble"].written.clear()

    await d._handle_message(dict(STOP_MSG))

    assert not any("happy" in p for p in t["ble"].written)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_mixed_transports_happy_oneshot_only_on_v3():
    d, t = make_daemon(ble=2, sim=3)
    await d._handle_message({"event": "session_start", "session_id": "aaa"})
    await d._handle_message({"event": "tool_use", "session_id": "aaa", "tool_name": "Bash"})
    for tr in t.values():
        tr.written.clear()

    await d._handle_message(dict(STOP_MSG))

    assert [s["anims"] for s in sessions_of(t["sim"])] == [["happy"], ["idle"]]
    assert not any("happy" in p for p in t["ble"].written)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_v2_subagent_stop_sends_no_happy():
    d, t = make_daemon(ble=2)
    await d._handle_message({"event": "session_start", "session_id": "s1"})
    await d._handle_message({"event": "subagent_start", "session_id": "s1", "agent_id": "a1"})
    t["ble"].written.clear()

    await d._handle_message({"event": "subagent_stop", "session_id": "s1", "agent_id": "a1"})

    assert not any("happy" in p for p in t["ble"].written)
    assert sessions_of(t["ble"])[-1]["anims"] == ["idle"]


@pytest.mark.asyncio
async def test_v2_oneshot_downgrades_other_slots():
    """A oneshot every version knows still downgrades the other slots for v2."""
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "idle", "last_event": time.time()})
    _add_session(d, "s2", {"state": "confused", "last_event": time.time(), "tool_name": "WebFetch"})
    sent = await d._send_session_oneshot("s1", "alert")
    assert sent is True
    assert sessions_of(t["ble"])[-1]["anims"] == ["alert", "confused"]


@pytest.mark.asyncio
async def test_v2_compact_sweep_downgrades_other_slots():
    d, t = make_daemon(ble=2)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebFetch"})
    _add_session(d, "s2", {"state": "idle", "last_event": time.time()})
    await d._handle_message({"event": "compact", "session_id": "s2"})
    assert sessions_of(t["ble"])[0]["anims"] == ["confused", "sweeping"]
    assert not any("hat_mishap" in p for p in t["ble"].written)


# --- Post-connect sync / replay ---


@pytest.mark.asyncio
async def test_post_connect_replay_downgrades_for_v2_firmware(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(return_value=2)
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert d._transport_versions["ble"] == 2
    assert sessions_of(transport)[-1]["anims"] == ["confused"]


@pytest.mark.asyncio
async def test_post_connect_replay_keeps_new_names_for_v3_firmware(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(return_value=3)
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert sessions_of(transport)[-1]["anims"] == ["hat_mishap"]


@pytest.mark.asyncio
async def test_failed_version_read_defaults_to_v1(monkeypatch):
    d, t = make_daemon()
    transport = MockTransport()
    transport.read_version = AsyncMock(side_effect=RuntimeError("boom"))
    d._transports["ble"] = transport
    d._transport_queues["ble"] = asyncio.Queue()
    monkeypatch.setattr(daemon_mod, "read_usage_from_cache", lambda path: None)
    _add_session(d, "s1", {"state": "confused", "last_event": time.time(), "tool_name": "WebSearch"})

    await d._post_connect_sync(transport, "ble")

    assert d._transport_versions["ble"] == 1
    payloads = [json.loads(p) for p in transport.written]
    assert {"action": "set_status", "status": "confused"} in payloads
    assert not any(p.get("action") == "set_sessions" for p in payloads)


# --- Simulator ---


def test_simulator_is_treated_as_v3():
    assert SIM_PROTOCOL_VERSION == 3
    d, _ = make_daemon()
    d._on_transport_connect("sim")
    assert d._transport_versions["sim"] == 3
