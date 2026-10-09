"""The packaged builds must carry the Claude Code mod the menu toggle installs.

setup.py (py2app) and margarita_tank.spec (PyInstaller) cannot be imported in a
test, so these read them the way test_statusline_install reads the spec.
"""

from pathlib import Path

from clawd_tank_menubar import hooks

ROOT = Path(__file__).resolve().parents[2]


def test_the_mod_source_the_builds_bundle_exists():
    assert (ROOT / "claude-mod" / hooks.MOD_NAME / ".claude-plugin" / "plugin.json").is_file()


def test_py2app_bundles_the_mod_under_resources_claude_mod():
    setup = (ROOT / "host" / "setup.py").read_text(encoding="utf-8")
    assert f'("claude-mod", ["../claude-mod/{hooks.MOD_NAME}"])' in setup


def test_pyinstaller_bundles_the_mod_next_to_the_exe():
    spec = (ROOT / "host" / "windows" / "margarita_tank.spec").read_text(encoding="utf-8")
    assert f'"claude-mod", "{hooks.MOD_NAME}"), "claude-mod/{hooks.MOD_NAME}"' in spec
