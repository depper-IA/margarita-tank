# host/clawd_tank_menubar/preferences.py
"""Persistent preferences for the Clawd Tank menubar app."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("clawd-tank.menubar")

DEFAULTS = {
    "ble_enabled": True,
    "sim_enabled": True,
    "sim_window_visible": True,
    "sim_always_on_top": True,
    # Opt-in: the Margarita side panel inside Claude Code (see hooks.install_mod).
    "claude_mod_enabled": False,
}
PREFS_PATH = Path.home() / ".clawd-tank" / "preferences.json"


def load_preferences(path: Path | None = None) -> dict:
    """Load preferences from disk, merged with defaults for missing keys."""
    # PREFS_PATH is looked up per call (not bound as a default) so tests can
    # redirect it away from the user's real preferences file.
    path = PREFS_PATH if path is None else path
    result = dict(DEFAULTS)
    try:
        stored = json.loads(path.read_text())
        result.update(stored)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return result


def save_preferences(path: Path | None = None, updates: dict = None) -> None:
    """Read-modify-write: load existing, merge updates, save back."""
    path = PREFS_PATH if path is None else path
    if updates is None:
        updates = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    try:
        existing = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    existing.update(updates)
    path.write_text(json.dumps(existing, indent=2) + "\n")
