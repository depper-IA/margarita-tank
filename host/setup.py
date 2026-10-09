# host/setup.py — py2app configuration for the Margarita Tank menubar app
import subprocess
from pathlib import Path
from setuptools import setup


def _bake_version():
    """Generate _version_info.py with the current git version."""
    def _run(args):
        return subprocess.run(args, capture_output=True, text=True, timeout=5)

    def _is_dirty():
        r = _run(["git", "status", "--porcelain"])
        return bool(r.stdout.strip())

    try:
        tag = _run(["git", "describe", "--tags", "--exact-match", "HEAD"])
        if tag.returncode == 0 and tag.stdout.strip():
            version = tag.stdout.strip()
            if _is_dirty():
                version += "-dirty"
        else:
            branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
            sha = _run(["git", "rev-parse", "--short", "HEAD"])
            b = branch.stdout.strip() if branch.returncode == 0 else "unknown"
            # On master/main, count against remote to show unpushed commits
            if b in ("master", "main"):
                count = _run(["git", "rev-list", "--count", "HEAD", f"^origin/{b}"])
                if count.returncode != 0:
                    count = _run(["git", "rev-list", "--count", "HEAD"])
            else:
                count = _run(["git", "rev-list", "--count", "HEAD", "^master"])
                if count.returncode != 0:
                    count = _run(["git", "rev-list", "--count", "HEAD", "^main"])
            s = sha.stdout.strip() if sha.returncode == 0 else "??????"
            n = count.stdout.strip() if count.returncode == 0 else "?"
            dirty = "-dirty" if _is_dirty() else ""
            version = f"{b}+{n}@{s}{dirty}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        version = "unknown"

    path = Path(__file__).parent / "clawd_tank_menubar" / "_version_info.py"
    path.write_text(f'VERSION = "{version}"\n')
    print(f"Baked version: {version}")


_bake_version()

APP = ["launcher.py"]
# The Claude Code panel mod ships as plain files under Resources/claude-mod/;
# the app copies it to ~/.clawd-tank/claude-mod/ when its menu toggle is on
# (hooks.resolve_mod_source() reads it back through RESOURCEPATH).
DATA_FILES = [("claude-mod", ["../claude-mod/margarita-band"])]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "AppIcon.icns",
    "plist": {
        "CFBundleName": "Margarita Tank",
        "CFBundleDisplayName": "Margarita Tank",
        # Kept from upstream so existing installs keep their Bluetooth permission
        # and launchd login item (launchd.PLIST_LABEL uses the same id).
        "CFBundleIdentifier": "com.clawd-tank.menubar",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,  # menu-bar-only app (no Dock icon)
        "NSBluetoothAlwaysUsageDescription": (
            "Margarita Tank uses Bluetooth to communicate with the ESP32 display."
        ),
    },
    "packages": ["clawd_tank_daemon", "clawd_tank_menubar"],
    "includes": ["rumps", "bleak", "objc"],
    "resources": ["clawd_tank_menubar/icons"],
}

setup(
    name="Margarita Tank",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
