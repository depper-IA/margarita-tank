# host/tests/test_menubar.py
"""Tests for menu bar app state transitions.

These test the observer-driven state updates without launching
the actual rumps app (which requires macOS AppKit).
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from clawd_tank_daemon.daemon import ClawdDaemon


class FakeObserver:
    """Minimal observer for testing daemon integration."""
    def __init__(self):
        self.connection_changes = []
        self.notification_changes = []

    def on_connection_change(self, connected: bool, transport: str = "") -> None:
        self.connection_changes.append((connected, transport))

    def on_notification_change(self, count: int) -> None:
        self.notification_changes.append(count)


@pytest.mark.asyncio
async def test_add_then_dismiss_observer_sequence():
    """Observer sees correct count sequence: 1, 2, 1, 0."""
    obs = FakeObserver()
    daemon = ClawdDaemon(observer=obs)

    await daemon._handle_message(
        {"event": "add", "session_id": "s1", "project": "p", "message": "m"}
    )
    await daemon._handle_message(
        {"event": "add", "session_id": "s2", "project": "p", "message": "m"}
    )
    await daemon._handle_message({"event": "dismiss", "session_id": "s1"})
    await daemon._handle_message({"event": "dismiss", "session_id": "s2"})

    assert obs.notification_changes == [1, 2, 1, 0]


@pytest.mark.asyncio
async def test_disconnect_callback_fires_observer():
    obs = FakeObserver()
    daemon = ClawdDaemon(observer=obs)
    # Mark BLE transport as disconnected so any() returns False
    mock_transport = AsyncMock()
    mock_transport.is_connected = False
    daemon._transports["ble"] = mock_transport
    daemon._on_transport_disconnect("ble")
    assert obs.connection_changes == [(False, "ble")]


@pytest.mark.asyncio
async def test_observer_receives_transport_name():
    obs = FakeObserver()
    daemon = ClawdDaemon(observer=obs)
    mock_transport = AsyncMock()
    mock_transport.is_connected = True
    daemon._transports["ble"] = mock_transport
    daemon._on_transport_connect("ble")
    assert obs.connection_changes == [(True, "ble")]


def test_launchd_is_enabled_checks_plist():
    """launchd.is_enabled returns True iff the plist file exists."""
    from clawd_tank_menubar import launchd
    with patch.object(launchd, "PLIST_PATH") as mock_path:
        mock_path.exists.return_value = True
        assert launchd.is_enabled() is True
        mock_path.exists.return_value = False
        assert launchd.is_enabled() is False


import tempfile
from pathlib import Path
from clawd_tank_menubar.preferences import load_preferences, save_preferences

def test_load_preferences_missing_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        prefs = load_preferences(Path(tmpdir) / "prefs.json")
        assert prefs == {"ble_enabled": True, "sim_enabled": True, "sim_window_visible": True, "sim_always_on_top": True, "claude_mod_enabled": False}

def test_save_and_load_preferences():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "subdir" / "prefs.json"
        save_preferences(path=path, updates={"sim_enabled": False})
        prefs = load_preferences(path)
        assert prefs["sim_enabled"] is False
        assert prefs["ble_enabled"] is True

def test_load_preferences_malformed_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "prefs.json"
        path.write_text("not json{{{")
        prefs = load_preferences(path)
        assert prefs == {"ble_enabled": True, "sim_enabled": True, "sim_window_visible": True, "sim_always_on_top": True, "claude_mod_enabled": False}
