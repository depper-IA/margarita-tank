# host/clawd_tank_menubar/autostart.py
"""Cross-platform "Launch at Login" abstraction.

macOS delegates to launchd.py unchanged (a launchd user agent plist).
Windows writes/reads HKCU Software\\Microsoft\\Windows\\CurrentVersion\\Run,
pointing at the installed exe when running packaged (PyInstaller sets
sys.frozen), or at `pythonw.exe -m clawd_tank_menubar` in a dev checkout.
"""
import sys
from pathlib import Path

if sys.platform == "darwin":
    from . import launchd as _launchd

    def is_enabled() -> bool:
        return _launchd.is_enabled()

    def enable() -> None:
        _launchd.enable()

    def disable() -> None:
        _launchd.disable()

    def is_stale() -> bool:
        return _launchd.is_stale()

elif sys.platform == "win32":
    import winreg

    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _VALUE_NAME = "ClawdTank"

    def _expected_command() -> str:
        """The command that should be registered to relaunch the tray app.

        Packaged (PyInstaller sets sys.frozen): sys.executable IS the app, so
        register it directly. Unpackaged (dev): run the package with
        pythonw.exe so no console window flashes at login; fall back to the
        plain interpreter if pythonw.exe isn't next to it (e.g. some venvs).
        """
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        interpreter = pythonw if pythonw.exists() else exe
        return f'"{interpreter}" -m clawd_tank_menubar'

    def is_enabled() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return False

    def enable() -> None:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _expected_command())

    def disable() -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass

    def is_stale() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        except FileNotFoundError:
            return False
        return value != _expected_command()

else:
    def is_enabled() -> bool:
        return False

    def enable() -> None:
        pass

    def disable() -> None:
        pass

    def is_stale() -> bool:
        return False
