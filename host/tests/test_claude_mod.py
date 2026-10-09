"""Installing and enabling the Margarita Claude Code mod (the side panel).

The app copies the bundled mod to ~/.clawd-tank/claude-mod/margarita-band and
enables it by listing that folder in settings.json env.CLAUDE_CODE_PLUGIN_DIRS
(a path list joined with os.pathsep). Enabling and disabling touch only our own
entry, never the user's other paths or any other settings key.
"""

import json
import os
from pathlib import Path

import pytest

from clawd_tank_menubar import hooks

PLUGIN_DIRS = "CLAUDE_CODE_PLUGIN_DIRS"


@pytest.fixture
def settings_path(sandbox_home):
    return hooks.CLAUDE_SETTINGS_PATH


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root: Path) -> dict:
    """Relative path -> content, for every file under root."""
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _ours() -> str:
    return str(hooks.MOD_DIR)


@pytest.fixture
def mod_source(tmp_path, monkeypatch):
    """A fake bundled mod, with the things that must never be installed."""
    src = tmp_path / "bundle" / "claude-mod" / "margarita-band"
    (src / ".claude-plugin").mkdir(parents=True)
    (src / ".claude-plugin" / "plugin.json").write_text('{"name": "margarita-band"}', encoding="utf-8")
    (src / "hooks" / "anims").mkdir(parents=True)
    (src / "hooks" / "hooks.json").write_text('{"modules": ["./register.tsx"]}', encoding="utf-8")
    (src / "hooks" / "register.tsx").write_text("// v1", encoding="utf-8")
    (src / "hooks" / "anims" / "idle.ts").write_text("// idle", encoding="utf-8")
    (src / ".claude-plugin" / "types").mkdir()
    (src / ".claude-plugin" / "types" / "index.d.ts").write_text("// generated", encoding="utf-8")
    (src / "node_modules" / "dep").mkdir(parents=True)
    (src / "node_modules" / "dep" / "index.js").write_text("// dep", encoding="utf-8")
    (src / "hooks" / "__pycache__").mkdir()
    (src / "hooks" / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    (src / ".DS_Store").write_text("junk", encoding="utf-8")
    monkeypatch.setattr(hooks, "MOD_SOURCE_DIR", src)
    return src


SOURCE_FILES = {
    ".claude-plugin/plugin.json": '{"name": "margarita-band"}',
    "hooks/hooks.json": '{"modules": ["./register.tsx"]}',
    "hooks/register.tsx": "// v1",
    "hooks/anims/idle.ts": "// idle",
}


# --- Locating the bundled mod ---------------------------------------------------


def test_mod_is_installed_next_to_the_other_clawd_tank_files(sandbox_home):
    assert hooks.MOD_NAME == "margarita-band"
    assert hooks.MOD_DIR == hooks.CLAWD_DIR / "claude-mod" / "margarita-band"


def test_source_in_a_checkout_is_the_repo_folder():
    module_file = Path("/repo/host/clawd_tank_menubar/hooks.py")
    assert hooks.resolve_mod_source(False, "/py", None, module_file) \
        == Path("/repo/claude-mod/margarita-band")


def test_source_in_a_py2app_bundle_is_under_resources():
    resources = "/Applications/Margarita Tank.app/Contents/Resources"
    assert hooks.resolve_mod_source(True, "/x/MacOS/python", resources, Path("/z/hooks.py")) \
        == Path(resources) / "claude-mod" / "margarita-band"


def test_source_in_a_pyinstaller_build_is_next_to_the_exe():
    assert hooks.resolve_mod_source(True, "/app/MargaritaTank/MargaritaTank.exe", None, Path("/z/hooks.py")) \
        == Path("/app/MargaritaTank") / "claude-mod" / "margarita-band"


def test_checkout_ships_a_valid_mod_folder():
    plugin = json.loads(
        (hooks.MOD_SOURCE_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == hooks.MOD_NAME
    assert (hooks.MOD_SOURCE_DIR / "hooks" / "hooks.json").is_file()


# --- Copying the files ----------------------------------------------------------


def test_install_files_copies_the_mod_and_skips_generated_junk(mod_source):
    assert hooks.install_mod_files() is True
    assert _tree(hooks.MOD_DIR) == SOURCE_FILES


def test_install_files_updates_changed_files_and_drops_stale_ones(mod_source):
    hooks.install_mod_files()
    (mod_source / "hooks" / "register.tsx").write_text("// v2", encoding="utf-8")
    (mod_source / "hooks" / "anims" / "idle.ts").unlink()
    (mod_source / "hooks" / "anims" / "new.ts").write_text("// new", encoding="utf-8")

    assert hooks.install_mod_files() is True

    assert _tree(hooks.MOD_DIR) == {
        ".claude-plugin/plugin.json": '{"name": "margarita-band"}',
        "hooks/hooks.json": '{"modules": ["./register.tsx"]}',
        "hooks/register.tsx": "// v2",
        "hooks/anims/new.ts": "// new",
    }


def test_install_files_does_not_rewrite_unchanged_files(mod_source):
    """The refresh runs on every app start; touching files would make a running
    Claude Code session see a change for nothing."""
    hooks.install_mod_files()
    target = hooks.MOD_DIR / "hooks" / "register.tsx"
    before = target.stat().st_mtime_ns

    hooks.install_mod_files()

    assert target.stat().st_mtime_ns == before


def test_install_files_keeps_typings_claude_code_generated_in_the_copy(mod_source):
    hooks.install_mod_files()
    types = hooks.MOD_DIR / ".claude-plugin" / "types"
    types.mkdir()
    (types / "index.d.ts").write_text("// generated by claude", encoding="utf-8")

    hooks.install_mod_files()

    assert (types / "index.d.ts").read_text(encoding="utf-8") == "// generated by claude"


def test_install_files_fails_without_a_bundled_mod(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "MOD_SOURCE_DIR", tmp_path / "missing")
    assert hooks.install_mod_files() is False
    assert not hooks.MOD_DIR.exists()


def test_install_files_reports_a_failed_copy_instead_of_raising(mod_source, sandbox_home):
    (hooks.CLAWD_DIR / "claude-mod").write_text("a file where the folder should go", encoding="utf-8")
    assert hooks.install_mod_files() is False


# --- Enabling in settings.json --------------------------------------------------


def test_enable_creates_settings_with_our_folder(settings_path):
    assert not settings_path.exists()
    assert hooks.enable_mod() is True
    assert _read(settings_path) == {"env": {PLUGIN_DIRS: _ours()}}
    assert hooks.is_mod_enabled() is True


def test_enable_keeps_every_other_setting_and_env_var(settings_path):
    _write(settings_path, {
        "model": "opus",
        "permissions": {"allow": ["Bash"]},
        "env": {"FOO": "bar"},
        "hooks": {"Stop": []},
    })
    assert hooks.enable_mod() is True
    assert _read(settings_path) == {
        "model": "opus",
        "permissions": {"allow": ["Bash"]},
        "env": {"FOO": "bar", PLUGIN_DIRS: _ours()},
        "hooks": {"Stop": []},
    }


def test_enable_appends_to_the_users_own_plugin_folders(settings_path):
    mine = os.pathsep.join(["/my/mods/a", "/my dir/b"])
    _write(settings_path, {"env": {PLUGIN_DIRS: mine}})
    hooks.enable_mod()
    assert _read(settings_path)["env"][PLUGIN_DIRS] == os.pathsep.join(["/my/mods/a", "/my dir/b", _ours()])


def test_enable_is_idempotent_and_leaves_the_file_alone(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: "/my/mods/a"}})
    hooks.enable_mod()
    first = settings_path.read_bytes()
    mtime = settings_path.stat().st_mtime_ns

    assert hooks.enable_mod() is True

    assert settings_path.read_bytes() == first
    assert settings_path.stat().st_mtime_ns == mtime


def test_enable_recognises_our_folder_spelled_with_a_trailing_separator(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: _ours() + os.sep}})
    before = settings_path.read_bytes()
    assert hooks.enable_mod() is True
    assert settings_path.read_bytes() == before


def test_enable_replaces_an_empty_value(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: ""}})
    hooks.enable_mod()
    assert _read(settings_path)["env"][PLUGIN_DIRS] == _ours()


def test_enable_refuses_an_unparseable_settings_file(settings_path):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text('{"model": "opus",}', encoding="utf-8")
    assert hooks.enable_mod() is False
    assert settings_path.read_text(encoding="utf-8") == '{"model": "opus",}'
    assert hooks.is_mod_enabled() is False


@pytest.mark.parametrize("settings", [
    {"env": ["not", "a", "dict"]},
    {"env": {PLUGIN_DIRS: ["/a", "/b"]}},
])
def test_enable_refuses_settings_it_cannot_extend_safely(settings_path, settings):
    _write(settings_path, settings)
    before = settings_path.read_bytes()
    assert hooks.enable_mod() is False
    assert settings_path.read_bytes() == before


def test_enable_writes_atomically_through_the_shared_helper(settings_path, monkeypatch):
    calls = []
    real = hooks._write_settings_atomic
    monkeypatch.setattr(hooks, "_write_settings_atomic", lambda s: (calls.append(s), real(s)))
    hooks.enable_mod()
    assert len(calls) == 1
    assert not list(settings_path.parent.glob("*.tmp"))


def test_install_mod_copies_the_files_then_enables(mod_source, settings_path):
    assert hooks.install_mod() is True
    assert _tree(hooks.MOD_DIR) == SOURCE_FILES
    assert hooks.is_mod_enabled() is True


def test_install_mod_does_not_touch_settings_when_the_copy_fails(tmp_path, monkeypatch, settings_path):
    monkeypatch.setattr(hooks, "MOD_SOURCE_DIR", tmp_path / "missing")
    assert hooks.install_mod() is False
    assert not settings_path.exists()


def test_install_mod_leaves_unparseable_settings_untouched(mod_source, settings_path):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{nope", encoding="utf-8")
    assert hooks.install_mod() is False
    assert settings_path.read_text(encoding="utf-8") == "{nope"


# --- Disabling ------------------------------------------------------------------


def test_disable_removes_only_our_folder(settings_path):
    mine = os.pathsep.join(["/my/mods/a", _ours(), "/my dir/b"])
    _write(settings_path, {"model": "opus", "env": {"FOO": "bar", PLUGIN_DIRS: mine}})
    assert hooks.disable_mod() is True
    assert _read(settings_path) == {
        "model": "opus",
        "env": {"FOO": "bar", PLUGIN_DIRS: os.pathsep.join(["/my/mods/a", "/my dir/b"])},
    }
    assert hooks.is_mod_enabled() is False


def test_disable_drops_the_key_when_it_becomes_empty(settings_path):
    _write(settings_path, {"env": {"FOO": "bar", PLUGIN_DIRS: _ours()}})
    hooks.disable_mod()
    assert _read(settings_path) == {"env": {"FOO": "bar"}}


def test_disable_drops_env_only_when_it_emptied_it(settings_path):
    _write(settings_path, {"model": "opus", "env": {PLUGIN_DIRS: _ours()}})
    hooks.disable_mod()
    assert _read(settings_path) == {"model": "opus"}


def test_disable_leaves_an_env_the_user_left_empty(settings_path):
    _write(settings_path, {"env": {}})
    before = settings_path.read_bytes()
    assert hooks.disable_mod() is True
    assert settings_path.read_bytes() == before


def test_disable_leaves_the_users_own_folders_untouched_when_ours_is_absent(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: "/my/mods/a"}})
    before = settings_path.read_bytes()
    mtime = settings_path.stat().st_mtime_ns
    assert hooks.disable_mod() is True
    assert settings_path.read_bytes() == before
    assert settings_path.stat().st_mtime_ns == mtime


def test_disable_without_a_settings_file_creates_nothing(settings_path):
    assert hooks.disable_mod() is True
    assert not settings_path.exists()


def test_disable_is_idempotent(settings_path):
    hooks.enable_mod()
    assert hooks.disable_mod() is True
    assert hooks.disable_mod() is True
    assert _read(settings_path) == {}


def test_disable_refuses_an_unparseable_settings_file(settings_path):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{nope", encoding="utf-8")
    assert hooks.disable_mod() is False
    assert settings_path.read_text(encoding="utf-8") == "{nope"


def test_disable_ignores_env_values_it_does_not_understand(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: ["/a"]}})
    before = settings_path.read_bytes()
    assert hooks.disable_mod() is True
    assert settings_path.read_bytes() == before


def test_enable_then_disable_restores_the_original_settings(settings_path):
    original = {"model": "opus", "env": {"FOO": "bar"}}
    _write(settings_path, original)
    hooks.enable_mod()
    hooks.disable_mod()
    assert _read(settings_path) == original


# --- Coexisting with the hooks --------------------------------------------------


def test_install_hooks_does_not_enable_the_mod(settings_path):
    hooks.install_hooks()
    assert hooks.is_mod_enabled() is False
    assert "env" not in _read(settings_path)


def test_install_hooks_keeps_an_enabled_mod(settings_path):
    hooks.enable_mod()
    hooks.install_hooks()
    assert hooks.is_mod_enabled() is True
    assert hooks.are_hooks_installed() is True


def test_uninstall_hooks_also_removes_our_folder(settings_path):
    mine = os.pathsep.join(["/my/mods/a", _ours()])
    _write(settings_path, {"model": "opus", "env": {PLUGIN_DIRS: mine}})
    hooks.install_hooks()
    assert hooks.is_mod_enabled() is True

    assert hooks.uninstall_hooks() is True

    assert _read(settings_path) == {"model": "opus", "env": {PLUGIN_DIRS: "/my/mods/a"}}
    assert hooks.is_mod_enabled() is False


def test_uninstall_hooks_removes_the_mod_even_when_no_hooks_remain(settings_path):
    _write(settings_path, {"model": "opus"})
    hooks.enable_mod()
    assert hooks.uninstall_hooks() is True
    assert _read(settings_path) == {"model": "opus"}


def test_uninstall_hooks_leaves_a_users_own_plugin_folders_alone(settings_path):
    _write(settings_path, {"env": {PLUGIN_DIRS: "/my/mods/a"}})
    hooks.install_hooks()
    hooks.uninstall_hooks()
    assert _read(settings_path) == {"env": {PLUGIN_DIRS: "/my/mods/a"}}


def test_uninstall_hooks_refuses_unparseable_settings_without_touching_the_mod(settings_path):
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{nope", encoding="utf-8")
    assert hooks.uninstall_hooks() is False
    assert settings_path.read_text(encoding="utf-8") == "{nope"
