"""Tests for Codex hook installation into ~/.codex/hooks.json.

install_codex_hooks() must MERGE our groups without clobbering the user's own
Codex hooks, be idempotent, and uninstall_codex_hooks() must remove only ours.
"""

import json

import pytest

from clawd_tank_menubar import hooks
from clawd_tank_menubar.hooks import install_codex_hooks, uninstall_codex_hooks


@pytest.fixture(autouse=True)
def codex_path(tmp_path, monkeypatch):
    p = tmp_path / "hooks.json"
    monkeypatch.setattr(hooks, "CODEX_HOOKS_PATH", p)
    return p


def _read(p) -> dict:
    return json.loads(p.read_text())


def _our_count(data: dict, event: str) -> int:
    n = 0
    for group in data.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            if hooks.HOOK_COMMAND in h.get("command", ""):
                n += 1
    return n


def test_fresh_install_writes_our_groups(codex_path):
    assert install_codex_hooks() is True
    data = _read(codex_path)
    # Every Codex event we manage has exactly one of our groups.
    for event in hooks.CODEX_HOOKS_CONFIG:
        assert _our_count(data, event) == 1, event
    # The command carries the codex agent arg.
    cmd = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert cmd.endswith(" codex")


def test_idempotent(codex_path):
    install_codex_hooks()
    install_codex_hooks()
    data = _read(codex_path)
    for event in hooks.CODEX_HOOKS_CONFIG:
        assert _our_count(data, event) == 1, event


def test_preserves_user_groups(codex_path):
    user = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-script.sh"}]}
            ],
            "CustomEvent": [
                {"hooks": [{"type": "command", "command": "user-thing"}]}
            ],
        }
    }
    codex_path.write_text(json.dumps(user))
    install_codex_hooks()
    data = _read(codex_path)
    # User's PreToolUse group survives alongside ours.
    pre_cmds = [h["command"] for g in data["hooks"]["PreToolUse"] for h in g["hooks"]]
    assert "my-own-script.sh" in pre_cmds
    assert any(c.endswith(" codex") for c in pre_cmds)
    # A user event we don't manage is untouched.
    assert data["hooks"]["CustomEvent"][0]["hooks"][0]["command"] == "user-thing"


def test_uninstall_removes_only_ours(codex_path):
    user = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-script.sh"}]}
            ],
        }
    }
    codex_path.write_text(json.dumps(user))
    install_codex_hooks()
    assert uninstall_codex_hooks() is True
    data = _read(codex_path)
    pre_cmds = [h["command"] for g in data["hooks"].get("PreToolUse", []) for h in g["hooks"]]
    # Ours gone, user's kept.
    assert "my-own-script.sh" in pre_cmds
    assert not any(c.endswith(" codex") for c in pre_cmds)
    # Events that held only our groups are dropped entirely.
    assert "SessionStart" not in data.get("hooks", {})


def test_uninstall_absent_file_is_noop(codex_path):
    assert not codex_path.exists()
    assert uninstall_codex_hooks() is True


def test_unparseable_file_left_untouched(codex_path):
    codex_path.write_text("{ not json")
    assert install_codex_hooks() is False
    # The bad file is left exactly as-is.
    assert codex_path.read_text() == "{ not json"
