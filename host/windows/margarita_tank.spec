# host/windows/margarita_tank.spec — PyInstaller spec for the Windows tray build.
#
# Mirrors setup.py (the py2app config for the macOS .app bundle): same two
# packages, same bundled icons, same bundled simulator binary. Build with:
#
#   cd host
#   .venv/Scripts/pyinstaller.exe windows/margarita_tank.spec --noconfirm
#
# Produces a onedir build in dist/MargaritaTank/ holding two executables that
# share one set of runtime files:
#
#   MargaritaTank.exe     the tray app (windowed, no console)
#   margarita-notify.exe  the Claude Code hook handler (console subsystem, so
#                         it reads the hook payload from the stdin pipe Claude
#                         Code hands it). hooks.py points HOOK_COMMAND at it
#                         when running frozen: sys.executable is the tray app
#                         there, not a Python interpreter.
#
# Onedir, not onefile: the simulator binary and icons sit as plain files next
# to the exe, matching how sim_process.py's _find_binary() looks next to
# sys.executable, and how windows_tray.py loads icons via importlib.resources.
#
# host/windows/installer.iss packages this folder into Margarita-Tank-Setup.exe.
import os
import sys

from PIL import Image

HOST_DIR = os.path.abspath(os.path.join(SPECPATH, ".."))
REPO_ROOT = os.path.abspath(os.path.join(HOST_DIR, ".."))

APP_NAME = "MargaritaTank"
NOTIFY_NAME = "margarita-notify"  # must match hooks.NOTIFY_EXE_NAME

# The static simulator (CI and distribution builds) wins over a dev build.
SIM_EXE = next(
    (p for p in (
        os.path.join(REPO_ROOT, "simulator", "build-static", "clawd-tank-sim.exe"),
        os.path.join(REPO_ROOT, "simulator", "build", "clawd-tank-sim.exe"),
    ) if os.path.isfile(p)),
    None,
)

os.makedirs(workpath, exist_ok=True)

# Exe/installer icon, generated from the committed macOS iconset so the repo
# carries no second copy of the artwork.
ICON_PATH = os.path.join(workpath, APP_NAME + ".ico")
Image.open(os.path.join(REPO_ROOT, "assets", "AppIcon.iconset", "icon_256x256.png")).save(
    ICON_PATH, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)

# The notify exe runs exactly the stdlib-only script the tray app installs on
# POSIX and in a source checkout (hooks.NOTIFY_SCRIPT), so both paths behave
# the same and there is a single copy of the hook logic to maintain.
sys.path.insert(0, HOST_DIR)
from clawd_tank_menubar.hooks import NOTIFY_EXE_NAME, NOTIFY_SCRIPT  # noqa: E402
from clawd_tank_menubar.version import _version_from_git  # noqa: E402

# Bake the version like setup.py does for the .app: a packaged build has no git
# checkout to ask at runtime. _version_info.py is gitignored.
VERSION = _version_from_git()
with open(os.path.join(HOST_DIR, "clawd_tank_menubar", "_version_info.py"), "w",
          encoding="utf-8") as f:
    f.write(f'VERSION = "{VERSION}"\n')
print(f"Baked version: {VERSION}")

assert NOTIFY_EXE_NAME == NOTIFY_NAME + ".exe", NOTIFY_EXE_NAME
NOTIFY_ENTRY = os.path.join(workpath, "margarita_notify.py")
with open(NOTIFY_ENTRY, "w", encoding="utf-8") as f:
    f.write(NOTIFY_SCRIPT)

block_cipher = None

tray = Analysis(
    [os.path.join(HOST_DIR, "windows", "launcher_windows.py")],
    pathex=[HOST_DIR],
    binaries=[(SIM_EXE, ".")] if SIM_EXE else [],
    datas=[
        (os.path.join(HOST_DIR, "clawd_tank_menubar", "icons"), "clawd_tank_menubar/icons"),
        (ICON_PATH, "."),
    ],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "clawd_tank_daemon",
        "clawd_tank_daemon.ble_client",
        "clawd_tank_daemon.sim_process",
        "clawd_tank_menubar",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["rumps", "AppKit", "objc", "PyObjCTools"],  # macOS-only, never on Windows
    noarchive=False,
)

notify = Analysis(
    [NOTIFY_ENTRY],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Stdlib only: keep the per-hook start-up lean.
    excludes=["tkinter", "PIL", "bleak", "pystray", "clawd_tank_daemon", "clawd_tank_menubar"],
    noarchive=False,
)

tray_pyz = PYZ(tray.pure, tray.zipped_data, cipher=block_cipher)
notify_pyz = PYZ(notify.pure, notify.zipped_data, cipher=block_cipher)

# PyInstaller 6.x's default onedir layout nests every bundled file (including
# clawd-tank-sim.exe) under _internal/, one level below the exe.
# sim_process.py's _find_binary() looks for the simulator NEXT TO
# sys.executable (that's how the macOS .app bundle works too), so
# contents_directory="." restores the flat, pre-6.0 layout for both exes.
tray_exe = EXE(
    tray_pyz,
    tray.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # tray app: no console window
    icon=ICON_PATH,
    contents_directory=".",
)

notify_exe = EXE(
    notify_pyz,
    notify.scripts,
    [],
    exclude_binaries=True,
    name=NOTIFY_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Console subsystem: Claude Code runs hooks from its own console with piped
    # stdio, so no window appears, and stdin carries the hook payload.
    console=True,
    icon=ICON_PATH,
    contents_directory=".",
)

coll = COLLECT(
    tray_exe,
    tray.binaries,
    tray.zipfiles,
    tray.datas,
    notify_exe,
    notify.binaries,
    notify.zipfiles,
    notify.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
