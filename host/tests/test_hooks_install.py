"""Tests for additive (non-clobbering) hook installation into Claude settings.

install_hooks() must MERGE Clawd Tank's hooks into the user's existing
Claude Code settings without removing the user's own hooks, and must be
idempotent (re-running never duplicates our entries). are_hooks_installed()
must be matcher-aware so a new/changed matcher is detected as "outdated".
"""

import json
import sys

import pytest

from clawd_tank_menubar import hooks
from clawd_tank_menubar.hooks import (
    HOOKS_CONFIG,
    HOOK_COMMAND,
    are_hooks_installed,
    install_hooks,
)


@pytest.fixture(autouse=True)
def settings_path(tmp_path, monkeypatch):
    """Redirect the Claude settings path to a temp file for every test."""
    p = tmp_path / "settings.json"
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS_PATH", p)
    return p


def _read(settings_path) -> dict:
    return json.loads(settings_path.read_text())


def _commands_for(settings: dict, event: str) -> list[str]:
    """Flatten every hook command registered for an event across all groups.

    Tolerates malformed groups (e.g. a user's {"hooks": null}) the installer leaves
    untouched."""
    cmds = []
    for group in settings.get("hooks", {}).get(event, []):
        hooks_list = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(hooks_list, list):
            continue
        for h in hooks_list:
            if isinstance(h, dict):
                cmds.append(h.get("command", ""))
    return cmds


def _our_command_count(settings: dict, event: str) -> int:
    return sum(1 for c in _commands_for(settings, event) if HOOK_COMMAND in c)


# --- Fresh install ---


def test_install_creates_settings_when_absent(settings_path):
    assert not settings_path.exists()
    install_hooks()
    assert settings_path.exists()
    assert are_hooks_installed() is True


def test_install_registers_every_managed_event(settings_path):
    install_hooks()
    settings = _read(settings_path)
    for event in HOOKS_CONFIG:
        assert _our_command_count(settings, event) >= 1, f"{event} missing our hook"


# --- Preserving the user's own hooks (the core requirement) ---


def test_install_preserves_user_hook_on_managed_event(settings_path):
    """A user's own SessionStart hook must survive installation."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "/my/own/script.sh"}]}
            ]
        }
    }))
    install_hooks()
    cmds = _commands_for(_read(settings_path), "SessionStart")
    assert "/my/own/script.sh" in cmds, "user's hook was clobbered"
    assert any(HOOK_COMMAND in c for c in cmds), "our hook was not added"


def test_install_preserves_unrelated_settings_keys(settings_path):
    settings_path.write_text(json.dumps({
        "model": "opus",
        "permissions": {"allow": ["Bash"]},
        "hooks": {},
    }))
    install_hooks()
    settings = _read(settings_path)
    assert settings["model"] == "opus"
    assert settings["permissions"] == {"allow": ["Bash"]}


def test_install_preserves_user_postooluse_with_different_matcher(settings_path):
    """Our AskUserQuestion PostToolUse hook must coexist with a user's Bash one."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "/my/bash/hook"}]}
            ]
        }
    }))
    install_hooks()
    groups = _read(settings_path)["hooks"]["PostToolUse"]
    user_group = next((g for g in groups if g.get("matcher") == "Bash"), None)
    our_group = next((g for g in groups if g.get("matcher") == "AskUserQuestion"), None)
    assert user_group is not None, "user's Bash PostToolUse group was removed"
    assert any(h["command"] == "/my/bash/hook" for h in user_group["hooks"])
    assert our_group is not None, "our AskUserQuestion PostToolUse group missing"
    assert any(HOOK_COMMAND in h["command"] for h in our_group["hooks"])


def test_install_preserves_user_no_matcher_hook_on_permissionrequest(settings_path):
    """Real-world case: a user's own no-matcher PermissionRequest hook (e.g. a
    third-party tool) must survive — ours is appended as a separate group."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "PermissionRequest": [
                {"hooks": [{"type": "command", "command": "/opt/other-tool/hook.sh"}]}
            ]
        }
    }))
    install_hooks()
    cmds = _commands_for(_read(settings_path), "PermissionRequest")
    assert "/opt/other-tool/hook.sh" in cmds, "user's PermissionRequest hook was clobbered"
    assert any(HOOK_COMMAND in c for c in cmds), "our PermissionRequest hook was not added"


def test_install_preserves_user_command_sharing_a_group(settings_path):
    """If the user shares a group with us, re-install keeps theirs and ours once."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [
                {"hooks": [
                    {"type": "command", "command": "/their/hook"},
                    {"type": "command", "command": HOOK_COMMAND},
                ]}
            ]
        }
    }))
    install_hooks()
    settings = _read(settings_path)
    cmds = _commands_for(settings, "SessionStart")
    assert "/their/hook" in cmds
    assert _our_command_count(settings, "SessionStart") == 1, "duplicated our hook"


# --- Idempotency ---


def test_install_is_idempotent(settings_path):
    install_hooks()
    install_hooks()
    install_hooks()
    settings = _read(settings_path)
    for event, entries in HOOKS_CONFIG.items():
        assert _our_command_count(settings, event) == len(entries), (
            f"{event} has duplicate Clawd Tank hooks after repeated installs"
        )


# --- Matcher-aware "outdated" detection ---


def test_are_hooks_installed_true_after_install(settings_path):
    install_hooks()
    assert are_hooks_installed() is True


def test_are_hooks_installed_false_when_event_missing(settings_path):
    install_hooks()
    settings = _read(settings_path)
    del settings["hooks"]["PostToolUse"]
    settings_path.write_text(json.dumps(settings))
    assert are_hooks_installed() is False


def test_are_hooks_installed_matcher_aware(settings_path):
    """Our command present under the WRONG matcher must count as not-installed."""
    install_hooks()
    settings = _read(settings_path)
    # Replace our AskUserQuestion group with a Bash-matched one (wrong matcher).
    settings["hooks"]["PostToolUse"] = [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    ]
    settings_path.write_text(json.dumps(settings))
    assert are_hooks_installed() is False


def test_are_hooks_installed_false_on_empty_settings(settings_path):
    settings_path.write_text(json.dumps({}))
    assert are_hooks_installed() is False


# --- Pruning superseded groups / self-heal (matcher changes) ---


def test_install_prunes_stale_our_group_on_matcher_change(settings_path):
    """An older install registered PostToolUse with NO matcher; the current config
    scopes it to AskUserQuestion. Install must drop the stale wildcard group, not
    leave it firing the notify script on every tool."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "PostToolUse": [
                {"hooks": [{"type": "command", "command": HOOK_COMMAND}]}  # stale, no matcher
            ]
        }
    }))
    install_hooks()
    groups = _read(settings_path)["hooks"]["PostToolUse"]
    our_groups = [g for g in groups
                  if any(HOOK_COMMAND in h.get("command", "") for h in g.get("hooks", []))]
    assert len(our_groups) == 1, "stale wildcard PostToolUse group was not pruned"
    assert our_groups[0].get("matcher") == "AskUserQuestion"


def test_are_hooks_installed_false_on_stale_our_group(settings_path):
    """A leftover our-exclusive group under an unexpected matcher must read as outdated
    so the startup auto-update re-runs install and cleans it up."""
    install_hooks()
    settings = _read(settings_path)
    settings["hooks"]["PostToolUse"].append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    )
    settings_path.write_text(json.dumps(settings))
    assert are_hooks_installed() is False


def test_install_self_heals_stale_group(settings_path):
    install_hooks()
    settings = _read(settings_path)
    settings["hooks"]["PostToolUse"].append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": HOOK_COMMAND}]}
    )
    settings_path.write_text(json.dumps(settings))
    install_hooks()
    groups = _read(settings_path)["hooks"]["PostToolUse"]
    matchers = sorted(g.get("matcher") for g in groups
                      if any(HOOK_COMMAND in h.get("command", "") for h in g["hooks"]))
    assert matchers == ["AskUserQuestion"]
    assert are_hooks_installed() is True


# --- Robustness on malformed settings ---


def test_install_does_not_crash_on_null_hooks_value(settings_path):
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [{"matcher": "X", "hooks": None}]}
    }))
    install_hooks()  # must not raise TypeError
    assert any(HOOK_COMMAND in c for c in _commands_for(_read(settings_path), "SessionStart"))


def test_are_hooks_installed_does_not_crash_on_null_hooks_value(settings_path):
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [{"hooks": None}]}
    }))
    assert are_hooks_installed() is False  # must not raise


# --- Precise command matching (no substring false positives) ---


def test_install_not_fooled_by_substring_command(settings_path):
    """A user command that merely contains the notify path (a wrapper, a cat) is not
    'our' hook, so our real bare-command group must still be added."""
    settings_path.write_text(json.dumps({
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": "/bin/cat " + HOOK_COMMAND}]}
            ]
        }
    }))
    install_hooks()
    cmds = _commands_for(_read(settings_path), "SessionStart")
    assert "/bin/cat " + HOOK_COMMAND in cmds, "user's command was clobbered"
    assert any(c == HOOK_COMMAND for c in cmds), "our real hook was not added"


# --- Windows: the command embeds an interpreter path that can move ------------


@pytest.mark.skipif(sys.platform != "win32",
                    reason="only the Windows command embeds an interpreter path")
def test_install_replaces_a_group_left_by_a_different_interpreter(settings_path):
    """A rebuilt venv or a moved Python changes HOOK_COMMAND. The prior group must
    be recognised as ours and replaced, not left behind pointing at an
    interpreter that is no longer there."""
    stale = f'"C:\\gone\\python.exe" "{hooks.NOTIFY_SCRIPT_PATH}"'
    assert stale != HOOK_COMMAND
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": stale}]}
        ]}
    }))
    install_hooks()
    cmds = _commands_for(_read(settings_path), "SessionStart")
    assert stale not in cmds, "stale interpreter group was left behind"
    assert cmds == [HOOK_COMMAND]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command form")
def test_windows_command_names_the_interpreter_and_a_py_file():
    """Windows cannot run an extensionless shebang script, so the hook command has
    to name an interpreter and a .py file, both quoted against spaces in paths."""
    assert hooks.NOTIFY_SCRIPT_PATH.suffix == ".py"
    assert HOOK_COMMAND == f'"{sys.executable}" "{hooks.NOTIFY_SCRIPT_PATH}"'


# --- Windows packaged build: sys.executable is the tray exe, not Python ------


_FROZEN_TRAY = "C:\\Users\\me\\AppData\\Local\\Programs\\Margarita Tank\\MargaritaTank.exe"
_FROZEN_NOTIFY = "C:\\Users\\me\\AppData\\Local\\Programs\\Margarita Tank\\margarita-notify.exe"


def test_frozen_windows_command_runs_the_bundled_notify_exe():
    """In a PyInstaller build sys.executable is the tray app itself: naming it as
    the 'interpreter' would launch a second tray instance on every hook. The
    command must run the console notify exe shipped next to it instead."""
    cmd = hooks.build_hook_command(
        platform="win32", frozen=True, executable=_FROZEN_TRAY,
        script_path=hooks.NOTIFY_SCRIPT_PATH,
    )
    assert cmd == f'"{_FROZEN_NOTIFY}"'


def test_unfrozen_windows_command_names_interpreter_and_script():
    cmd = hooks.build_hook_command(
        platform="win32", frozen=False, executable="C:\\py\\python.exe",
        script_path="C:\\Users\\me\\.clawd-tank\\clawd-tank-notify.py",
    )
    assert cmd == '"C:\\py\\python.exe" "C:\\Users\\me\\.clawd-tank\\clawd-tank-notify.py"'


def test_posix_command_is_the_script_path_even_when_frozen():
    cmd = hooks.build_hook_command(
        platform="darwin", frozen=True, executable="/Applications/X.app/Contents/MacOS/X",
        script_path="/Users/me/.clawd-tank/clawd-tank-notify",
    )
    assert cmd == "/Users/me/.clawd-tank/clawd-tank-notify"


def _use_hook_command(monkeypatch, command):
    monkeypatch.setattr(hooks, "HOOK_COMMAND", command)
    monkeypatch.setattr(hooks, "HOOKS_CONFIG", hooks.build_hooks_config(command))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command form")
def test_frozen_install_replaces_a_group_left_by_the_python_interpreter(
        settings_path, monkeypatch):
    """Upgrading from a source checkout to the installer must self-heal: the old
    `"python.exe" "clawd-tank-notify.py"` group is ours and gets replaced."""
    stale = f'"C:\\venv\\python.exe" "{hooks.NOTIFY_SCRIPT_PATH}"'
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": stale}]}]}
    }))
    frozen_cmd = f'"{_FROZEN_NOTIFY}"'
    _use_hook_command(monkeypatch, frozen_cmd)
    install_hooks()
    assert _commands_for(_read(settings_path), "SessionStart") == [frozen_cmd]
    assert are_hooks_installed()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command form")
def test_frozen_build_reports_hooks_outdated_while_python_groups_remain(
        settings_path, monkeypatch):
    """Startup only reinstalls when are_hooks_installed() is False. A group left by
    a source checkout is ours, but not the CURRENT command — reporting it as
    installed would keep hooks pointing at a venv the installer does not own."""
    stale = f'"C:\\venv\\python.exe" "{hooks.NOTIFY_SCRIPT_PATH}"'
    settings_path.write_text(json.dumps({"hooks": {
        event: [{**({"matcher": e["matcher"]} if "matcher" in e else {}),
                 "hooks": [{"type": "command", "command": stale}]} for e in entries]
        for event, entries in HOOKS_CONFIG.items()
    }}))
    _use_hook_command(monkeypatch, f'"{_FROZEN_NOTIFY}"')
    assert not are_hooks_installed()
    install_hooks()
    assert are_hooks_installed()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command form")
def test_install_replaces_a_notify_exe_group_from_another_install_folder(
        settings_path, monkeypatch):
    """Moving the install (or going back to a source checkout) must not leave a
    group pointing at a notify exe that is no longer there."""
    stale = '"D:\\Old Place\\MargaritaTank\\margarita-notify.exe"'
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": stale}]}]}
    }))
    install_hooks()
    assert _commands_for(_read(settings_path), "SessionStart") == [HOOK_COMMAND]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command form")
def test_wrapper_around_the_notify_exe_is_not_ours(settings_path):
    """Same anchoring rule as for the script: `cmd /c "<notify exe>"` is a user's
    wrapper and must survive a reinstall."""
    wrapper = f'cmd /c "{_FROZEN_NOTIFY}"'
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": wrapper}]}]}
    }))
    install_hooks()
    assert wrapper in _commands_for(_read(settings_path), "SessionStart")


# Non-ASCII user content: on Windows the default text encoding is the ANSI code
# page (cp1252), which cannot decode UTF-8 bytes like 0x9d ("”" = e2 80 9d).
# Settings must always be read and written as UTF-8.
_NON_ASCII_SETTINGS = {"statusLine": {"command": "echo “Margarita” — ñandú"}}


def test_are_hooks_installed_reads_utf8_settings(settings_path):
    settings_path.write_text(json.dumps(_NON_ASCII_SETTINGS, ensure_ascii=False), encoding="utf-8")
    install_hooks()
    assert are_hooks_installed() is True


def test_install_preserves_non_ascii_user_settings(settings_path):
    settings_path.write_text(json.dumps(_NON_ASCII_SETTINGS, ensure_ascii=False), encoding="utf-8")
    install_hooks()
    written = json.loads(settings_path.read_text(encoding="utf-8"))
    assert written["statusLine"] == _NON_ASCII_SETTINGS["statusLine"]


# --- Never clobber a settings file we cannot parse ----------------------------


def test_install_reads_settings_saved_with_utf8_bom(settings_path):
    """Windows editors (Notepad) may prepend a UTF-8 BOM; it must not count as invalid."""
    settings_path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"model": "opus"}).encode("utf-8"))
    assert install_hooks() is True
    written = _read(settings_path)
    assert written["model"] == "opus"
    assert any(HOOK_COMMAND in c for c in _commands_for(written, "SessionStart"))


@pytest.mark.parametrize("raw", [
    b'{"model": "opus",}',             # invalid JSON (trailing comma)
    b'["not", "an", "object"]',        # valid JSON, wrong shape
    b'{"model": "\xff\xfe opus"}',     # not decodable as UTF-8
])
def test_install_leaves_unparseable_settings_untouched(settings_path, raw):
    settings_path.write_bytes(raw)
    assert install_hooks() is False
    assert settings_path.read_bytes() == raw


def test_are_hooks_installed_false_on_undecodable_settings(settings_path):
    settings_path.write_bytes(b'{"model": "\xff\xfe"}')
    assert are_hooks_installed() is False  # must not raise


@pytest.mark.parametrize("raw", [b"", b"  \n"])
def test_install_treats_empty_settings_file_as_empty_object(settings_path, raw):
    settings_path.write_bytes(raw)
    assert install_hooks() is True
    assert any(HOOK_COMMAND in c for c in _commands_for(_read(settings_path), "SessionStart"))


def test_install_writes_through_a_symlinked_settings_file(settings_path, tmp_path):
    target = tmp_path / "dotfiles" / "settings.json"
    target.parent.mkdir()
    target.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    try:
        settings_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this system")
    assert install_hooks() is True
    assert settings_path.is_symlink()
    assert json.loads(target.read_text(encoding="utf-8"))["model"] == "opus"
    assert any(HOOK_COMMAND in c for c in _commands_for(_read(target), "SessionStart"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_install_preserves_settings_file_mode(settings_path):
    settings_path.write_text("{}", encoding="utf-8")
    settings_path.chmod(0o644)
    install_hooks()
    assert settings_path.stat().st_mode & 0o777 == 0o644
