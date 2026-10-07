# host/clawd_tank_menubar/app.py
"""Clawd Tank macOS status bar application.

Thin by design: this class owns only what rumps requires to live on the
App instance itself (menu/icon/title, and the @rumps.timer-decorated health
check — rumps discovers timers by scanning the App subclass), and wires them
to a ClawdTankController. All business logic (transport toggles, simulator
lifecycle, hooks, autostart, quit sequencing) lives in controller.py and is
UI-framework-independent; all rumps-specific menu construction and
repainting lives in rumps_view.py.
"""
import logging
from pathlib import Path

import rumps

from . import hooks
from .controller import ClawdTankController
from .rumps_view import RumpsTrayView
from .version import get_version

logger = logging.getLogger("clawd-tank.menubar")


class ClawdTankApp(rumps.App):
    def __init__(self):
        super().__init__("Margarita Tank", quit_button=None)
        self._view = RumpsTrayView(self)
        self._controller = ClawdTankController(self._view)
        self._view.build(self._controller)

    def start(self) -> None:
        self._controller.start()

    @rumps.timer(30)
    def _health_check(self, _):
        """rumps requires @timer methods to live on the App instance; the
        actual health-check logic is controller.check_daemon_health()."""
        self._controller.check_daemon_health()


def main():
    log_dir = Path.home() / "Library" / "Logs" / "ClawdTank"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "clawd-tank.log"),
        ],
    )
    logger = logging.getLogger("clawd-tank.menubar")
    logger.info("Clawd Tank %s starting", get_version())

    hooks.install_notify_script()
    if not hooks.are_hooks_installed():
        logger.info("Hooks outdated, auto-updating...")
        hooks.install_hooks()

    # Kill stale sim processes synchronously before anything else
    from clawd_tank_daemon.sim_process import SimProcessManager
    SimProcessManager.kill_stale_sims()

    app = ClawdTankApp()
    app.start()
    app.run()


if __name__ == "__main__":
    main()
