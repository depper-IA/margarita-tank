# host/windows/launcher_windows.py — PyInstaller entry point for the
# Windows tray build. Mirrors host/launcher.py (the py2app entry point for
# macOS): imports the package's main() so relative imports resolve, no
# other logic here.
from clawd_tank_menubar.__main__ import main

main()
