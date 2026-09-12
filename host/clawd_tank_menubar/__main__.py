# host/clawd_tank_menubar/__main__.py
"""Entry point: `python -m clawd_tank_menubar`.

Dispatches to the macOS rumps app (unchanged) or the Windows pystray tray.
Runnable in a dev checkout on either platform without a packaged build —
app.py (which imports rumps) is only imported on darwin, so this module
itself has no import-time platform dependency.
"""
import sys


def _run_macos() -> None:
    from .app import main
    main()


def _run_windows() -> None:
    import logging
    import sys
    import traceback
    from pathlib import Path

    log_dir = Path.home() / ".clawd-tank" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "clawd-tank.log"

    # A packaged (PyInstaller, console=False) build has no console, and
    # sys.stdout/sys.stderr are not readable/writable streams in that mode
    # (bootloader-dependent: None on some versions, a stub that raises on
    # others). A bare logging.StreamHandler() defaulting to sys.stderr can
    # therefore fail before the FileHandler ever gets its first record —
    # this was caught by the packaging step's manual run: the built exe
    # produced a completely empty log file with console=False, discovered
    # only by rebuilding with console=True to see the traceback. Only add
    # the console handler when there's an actual usable stream; always keep
    # the file handler so a packaged run never fails silently.
    handlers = [logging.FileHandler(log_file)]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=handlers,
    )
    logger = logging.getLogger("clawd-tank.menubar")

    try:
        from . import hooks
        from .controller import ClawdTankController
        from .version import get_version
        from .windows_tray import WindowsTrayView

        logger.info("Clawd Tank %s starting (Windows tray)", get_version())

        hooks.install_notify_script()
        if not hooks.are_hooks_installed():
            logger.info("Hooks outdated, auto-updating...")
            hooks.install_hooks()

        from clawd_tank_daemon.sim_process import SimProcessManager
        SimProcessManager.kill_stale_sims()

        view = WindowsTrayView()
        controller = ClawdTankController(view)
        view.build(controller)
        controller.start()
        view.run()
    except Exception:
        # Same silent-crash risk as the logging handler above: a packaged
        # windowed build has nowhere else to surface this. Log it, in
        # whatever handlers actually work, then re-raise.
        logger.critical("Unhandled exception, exiting:\n%s", traceback.format_exc())
        raise


def main() -> None:
    if sys.platform == "darwin":
        _run_macos()
    else:
        _run_windows()


if __name__ == "__main__":
    main()
