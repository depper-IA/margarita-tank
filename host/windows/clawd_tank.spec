# host/windows/clawd_tank.spec — PyInstaller spec for the Windows tray build.
#
# Mirrors setup.py (the py2app config for the macOS .app bundle): same two
# packages, same bundled icons, same bundled simulator binary. Build with:
#
#   cd host
#   .venv/Scripts/pyinstaller.exe windows/clawd_tank.spec --noconfirm
#
# Produces dist/ClawdTank/ClawdTank.exe (onedir build — the simulator binary
# and icons sit as plain files next to the exe, matching how
# sim_process.py's _find_binary() looks next to sys.executable, and how
# rumps_view.py/windows_tray.py load icons via importlib.resources — a
# onefile build works too but adds one PyInstaller-managed unpack step
# before either lookup, which isn't needed here).
import os

HOST_DIR = os.path.abspath(os.path.join(SPECPATH, ".."))
REPO_ROOT = os.path.abspath(os.path.join(HOST_DIR, ".."))
SIM_EXE = os.path.join(REPO_ROOT, "simulator", "build", "clawd-tank-sim.exe")

block_cipher = None

a = Analysis(
    [os.path.join(HOST_DIR, "windows", "launcher_windows.py")],
    pathex=[HOST_DIR],
    binaries=[(SIM_EXE, ".")] if os.path.isfile(SIM_EXE) else [],
    datas=[
        (os.path.join(HOST_DIR, "clawd_tank_menubar", "icons"), "clawd_tank_menubar/icons"),
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClawdTank",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # tray app: no console window
    # No .exe icon set: PyInstaller's `icon=` needs a .ico, and the repo only
    # has .png icons (used at runtime for the tray itself, via
    # importlib.resources, not for the exe's own file icon). Converting one
    # is a trivial follow-up, not attempted here.
    icon=None,
    # PyInstaller 6.x's default onedir layout nests every bundled file
    # (including clawd-tank-sim.exe) under dist/ClawdTank/_internal/, one
    # level below the exe itself. sim_process.py's _find_binary() looks for
    # the simulator NEXT TO sys.executable (that's how the macOS .app bundle
    # works too) — contents_directory="." restores the flat, pre-6.0 layout
    # so the simulator binary actually lands beside ClawdTank.exe.
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ClawdTank",
)
