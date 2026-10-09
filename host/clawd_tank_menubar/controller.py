# host/clawd_tank_menubar/controller.py
"""Platform-independent controller for the Clawd Tank tray application.

Everything that used to live directly on rumps widgets in app.py (which
transports are enabled, the simulator window/pin state, the selected session
timeout, the last known brightness, hook/autostart status) lives here as
plain controller state instead. The controller talks to a tray UI only
through the small TrayView protocol below, so it has zero dependency on
rumps, pystray, or any other UI framework — that is the whole point of the
extraction, and what makes it testable without a display.
"""
import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from clawd_tank_daemon.daemon import ClawdDaemon, DaemonObserver

from . import autostart, hooks, preferences
from .preferences import load_preferences, save_preferences

logger = logging.getLogger("clawd-tank.menubar")

SESSION_TIMEOUT_OPTIONS = [
    ("1 minute", 60),
    ("2 minutes", 120),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("30 minutes", 1800),
    ("Never", 0),
]

DEFAULT_SESSION_TIMEOUT_SECONDS = 300
DEFAULT_BRIGHTNESS = 102


@dataclass(frozen=True)
class TrayState:
    """A single, complete snapshot of everything a view needs to paint the
    tray menu. One immutable value the controller hands to the view, rather
    than many individual setter calls — this mirrors the original
    `_update_menu_state()`, which always recomputed every menu item from
    current state in one pass, and preserves its threading contract: one
    main-thread hop per update, not one per widget.
    """

    icon: str  # "disconnected" | "connected" | "notifications"
    ble_enabled: bool
    ble_connected: bool
    sim_enabled: bool
    sim_connected: bool
    sim_window_visible: bool
    sim_pinned: bool
    brightness: int
    brightness_enabled: bool
    session_timeout_seconds: int
    hooks_installed: bool
    login_enabled: bool
    claude_mod_enabled: bool


class TrayView(Protocol):
    """What the controller needs from a tray UI, macOS or Windows.

    Deliberately three methods:
    - `render` repaints the whole menu from one TrayState snapshot (see
      TrayState's docstring for why this is one call and not many).
    - `alert` and `quit` are one-shot actions with no steady state to
      snapshot, so they stay as their own methods.
    """

    def render(self, state: TrayState) -> None: ...

    def alert(self, title: str, message: str) -> None: ...

    def quit(self) -> None: ...


def _default_sim_process_factory(on_window_event, start_pinned):
    from clawd_tank_daemon.sim_process import SimProcessManager

    return SimProcessManager(on_window_event=on_window_event, start_pinned=start_pinned)


class ClawdTankController(DaemonObserver):
    def __init__(
        self,
        view: TrayView,
        *,
        prefs_path: Optional[Path] = None,
        sim_process_factory: Optional[Callable] = None,
        force_exit: Callable[[int], None] = os._exit,
    ):
        self._view = view
        self._prefs_path = preferences.PREFS_PATH if prefs_path is None else prefs_path
        self._sim_process_factory = sim_process_factory or _default_sim_process_factory
        self._force_exit = force_exit

        self._daemon: Optional[ClawdDaemon] = None
        self._daemon_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_ready = threading.Event()
        self._transport_status: dict[str, bool] = {}
        self._notification_count = 0
        self._current_config: dict = {}
        self._sim_process = None

        prefs = load_preferences(self._prefs_path)
        self._ble_enabled = bool(prefs.get("ble_enabled", True))
        self._sim_enabled = bool(prefs.get("sim_enabled", True))
        self._sim_window_visible = bool(prefs.get("sim_window_visible", True))
        self._sim_pinned = bool(prefs.get("sim_always_on_top", True))
        self._brightness = DEFAULT_BRIGHTNESS
        self._session_timeout_seconds = DEFAULT_SESSION_TIMEOUT_SECONDS

        self._hooks_installed = hooks.are_hooks_installed()
        self._claude_mod_enabled = bool(prefs.get("claude_mod_enabled", False))

        if autostart.is_enabled() and autostart.is_stale():
            logger.info("Autostart entry is stale, updating to current executable")
            autostart.enable()
        self._login_enabled = autostart.is_enabled()

        # Deliberately no self._render() here: at this point the daemon
        # thread does not exist yet, so the original _update_menu_state()
        # would have set the icon (already done directly by view construction)
        # and returned immediately, touching nothing else. The first real
        # render happens once the daemon actually starts producing events.

    # --- Derived state -------------------------------------------------

    @property
    def connected(self) -> bool:
        return any(self._transport_status.values()) if self._transport_status else False

    @property
    def daemon_alive(self) -> bool:
        return self._daemon_thread is not None and self._daemon_thread.is_alive()

    # --- Read-only initial state, for a view to bootstrap its widgets from
    # before the first render() (see the note at the end of __init__ about
    # why no render happens until the daemon actually starts). ---

    @property
    def ble_enabled(self) -> bool:
        return self._ble_enabled

    @property
    def sim_enabled(self) -> bool:
        return self._sim_enabled

    @property
    def sim_window_visible(self) -> bool:
        return self._sim_window_visible

    @property
    def sim_pinned(self) -> bool:
        return self._sim_pinned

    @property
    def hooks_installed(self) -> bool:
        return self._hooks_installed

    @property
    def login_enabled(self) -> bool:
        return self._login_enabled

    @property
    def claude_mod_enabled(self) -> bool:
        return self._claude_mod_enabled

    @property
    def session_timeout_seconds(self) -> int:
        return self._session_timeout_seconds

    def _compute_icon(self) -> str:
        if not self.daemon_alive:
            return "disconnected"
        if self.connected:
            return "notifications" if self._notification_count > 0 else "connected"
        return "disconnected"

    def _render(self) -> None:
        """Recompute and push the full tray state. A pure snapshot of
        current controller fields — it never mutates anything. (An earlier
        version of this method re-derived brightness/session_timeout from
        self._current_config here, mirroring the original
        _update_menu_state()'s `if connected: brightness =
        self._current_config.get(...)` block literally. That turned out to
        be a real behavioral regression, caught by the Windows tray proof
        run: because every mutator here now calls _render() immediately
        (the original did not — most of its toggle handlers hand-patched
        one widget directly and never called _update_menu_state() at all),
        selecting a session timeout would immediately self-clobber back to
        the stale last-read device value in the same call, before the user
        ever saw their selection. The original could only ever revert on a
        *later*, unrelated render — never synchronously within the
        selection itself. See _read_device_config() for where config-echoed
        values are now applied instead, exactly when a fresh echo arrives.)
        """
        state = TrayState(
            icon=self._compute_icon(),
            ble_enabled=self._ble_enabled,
            ble_connected=self._transport_status.get("ble", False),
            sim_enabled=self._sim_enabled,
            sim_connected=self._transport_status.get("sim", False),
            sim_window_visible=self._sim_window_visible,
            sim_pinned=self._sim_pinned,
            brightness=self._brightness,
            brightness_enabled=self.connected,
            session_timeout_seconds=self._session_timeout_seconds,
            hooks_installed=self._hooks_installed,
            login_enabled=self._login_enabled,
            claude_mod_enabled=self._claude_mod_enabled,
        )
        self._view.render(state)

    # --- Lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Start the daemon's asyncio event loop in a background thread and
        wire up transports according to preferences. Moved verbatim from
        app.py's _start_daemon_thread()."""
        self.refresh_claude_mod()

        self._daemon = ClawdDaemon(observer=self, headless=False)

        def run_loop():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop_ready.set()
                self._loop.run_until_complete(self._daemon.run())
                logger.info("Daemon thread exited normally")
            except SystemExit as e:
                # Not an Exception: without this, sys.exit() in the daemon
                # (e.g. a failed takeover lock) kills the thread silently.
                logger.error("Daemon thread exited via SystemExit (code %s)", e.code)
            except Exception:
                logger.exception("Daemon thread crashed")
            finally:
                self._loop_ready.set()  # unblock main thread if still waiting

        self._daemon_thread = threading.Thread(target=run_loop, daemon=True)
        self._daemon_thread.start()
        self._loop_ready.wait(timeout=5)

        prefs = load_preferences(self._prefs_path)

        if prefs.get("ble_enabled", True):
            from clawd_tank_daemon.ble_client import ClawdBleClient

            client = ClawdBleClient()
            self._transport_status["ble"] = False
            asyncio.run_coroutine_threadsafe(
                self._daemon.add_transport("ble", client), self._loop
            )

        if prefs.get("sim_enabled", True):
            self._start_simulator()

    def quit(self) -> None:
        try:
            if self._loop and self._daemon:
                future = asyncio.run_coroutine_threadsafe(
                    self._shutdown_sequence(), self._loop
                )
                future.result(timeout=8)
            self._view.quit()
        except Exception:
            logger.exception("Error during quit, force-killing")
            logging.shutdown()
            self._force_exit(1)

    async def _shutdown_sequence(self) -> None:
        # Remove sim transport from daemon first (avoids double-disconnect).
        await self._daemon.remove_transport("sim")
        # Kill sim process (client already disconnected, just kill the process).
        if self._sim_process:
            await self._sim_process.kill()
            self._sim_process = None
        # Now shut down daemon (BLE disconnect, socket cleanup).
        await self._daemon._shutdown()

    # --- DaemonObserver callbacks (called from the asyncio thread) ------

    def on_connection_change(self, connected: bool, transport: str = "") -> None:
        if transport:
            self._transport_status[transport] = connected
        if connected and self._loop:
            asyncio.run_coroutine_threadsafe(self._read_device_config(), self._loop)
        self._render()

    def on_notification_change(self, count: int) -> None:
        self._notification_count = count
        self._render()

    async def _read_device_config(self) -> None:
        if self._daemon:
            config = await self._daemon.read_config()
            if config:
                self._current_config = config
                self._brightness = config.get("brightness", self._brightness)
                self._session_timeout_seconds = config.get(
                    "sleep_timeout", self._session_timeout_seconds
                )
                self._render()

    # --- Health check ------------------------------------------------------

    def check_daemon_health(self) -> None:
        """Periodic check to detect daemon thread death. Called by the view
        on a ~30s timer (rumps.timer on macOS, a background loop on Windows)."""
        if not self.daemon_alive:
            self._render()

    # --- Menu actions --------------------------------------------------

    def toggle_ble_enabled(self) -> None:
        self._ble_enabled = not self._ble_enabled
        save_preferences(self._prefs_path, updates={"ble_enabled": self._ble_enabled})

        if self._ble_enabled:
            from clawd_tank_daemon.ble_client import ClawdBleClient

            client = ClawdBleClient()
            self._transport_status["ble"] = False
            self._render()
            if self._loop and self._daemon:
                asyncio.run_coroutine_threadsafe(
                    self._daemon.add_transport("ble", client), self._loop
                )
        else:
            self._transport_status.pop("ble", None)
            self._render()
            if self._loop and self._daemon:
                asyncio.run_coroutine_threadsafe(
                    self._daemon.remove_transport("ble"), self._loop
                )

    def toggle_sim_enabled(self) -> None:
        self._sim_enabled = not self._sim_enabled
        save_preferences(self._prefs_path, updates={"sim_enabled": self._sim_enabled})

        if self._sim_enabled:
            self._start_simulator()
        else:
            self._stop_simulator()
        self._render()

    def toggle_sim_window(self) -> None:
        self._sim_window_visible = not self._sim_window_visible
        save_preferences(
            self._prefs_path, updates={"sim_window_visible": self._sim_window_visible}
        )
        if self._sim_process and self._loop:
            if self._sim_window_visible:
                asyncio.run_coroutine_threadsafe(self._sim_process.show_window(), self._loop)
            else:
                asyncio.run_coroutine_threadsafe(self._sim_process.hide_window(), self._loop)
        self._render()

    def toggle_sim_pinned(self) -> None:
        self._sim_pinned = not self._sim_pinned
        save_preferences(self._prefs_path, updates={"sim_always_on_top": self._sim_pinned})
        if self._sim_process and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._sim_process.set_pinned(self._sim_pinned), self._loop
            )
        self._render()

    def _on_sim_window_event(self, event: dict) -> None:
        """Handle events from the simulator process (e.g. window_hidden)."""
        if event.get("event") == "window_hidden":
            self._sim_window_visible = False
            save_preferences(self._prefs_path, updates={"sim_window_visible": False})
            self._render()

    def select_session_timeout(self, seconds: int) -> None:
        self._session_timeout_seconds = seconds
        if self._loop and self.connected and self._daemon:
            payload = json.dumps({"sleep_timeout": seconds})
            asyncio.run_coroutine_threadsafe(self._daemon.write_config(payload), self._loop)
            self._daemon.set_session_timeout(seconds)
        self._render()

    def set_brightness(self, value: int) -> None:
        """Called from the slider (macOS) or a discrete step (Windows)."""
        if self._loop and self.connected:
            payload = json.dumps({"brightness": value})
            asyncio.run_coroutine_threadsafe(self._daemon.write_config(payload), self._loop)

    def install_hooks(self) -> None:
        was_installed = hooks.are_hooks_installed()
        hooks.install_notify_script()
        hooks.install_statusline_bridge_script()
        if not hooks.install_hooks():
            self._view.alert(
                title="Hooks Not Installed",
                message=(
                    "~/.claude/settings.json could not be parsed, so it was left "
                    "untouched. Fix the file and try again."
                ),
            )
            self._render()
            return
        self._hooks_installed = True
        if was_installed:
            self._view.alert(
                title="Hooks Updated",
                message=(
                    "Claude Code hooks have been updated. "
                    "Restart your Claude Code sessions for the changes to take effect."
                ),
            )
        else:
            self._view.alert(
                title="Hooks Installed",
                message=(
                    "Claude Code hooks have been added to ~/.claude/settings.json. "
                    "Restart your Claude Code sessions for the hooks to take effect."
                ),
            )
        self._render()

    def toggle_claude_mod(self) -> None:
        """Turn the Margarita side panel in Claude Code on or off. The choice is
        saved only once settings.json really changed, so the menu check never
        claims a state that did not happen."""
        if self._claude_mod_enabled:
            if not hooks.disable_mod():
                self._view.alert(
                    title="Claude Code Mod Not Disabled",
                    message=(
                        "~/.claude/settings.json could not be parsed, so it was left "
                        "untouched. Fix the file and try again."
                    ),
                )
                self._render()
                return
            self._claude_mod_enabled = False
            save_preferences(self._prefs_path, updates={"claude_mod_enabled": False})
            self._view.alert(
                title="Claude Code Mod Disabled",
                message=(
                    "The Margarita panel was removed from ~/.claude/settings.json. "
                    "Restart your Claude Code sessions for the change to take effect."
                ),
            )
        else:
            if not hooks.install_mod():
                self._view.alert(
                    title="Claude Code Mod Not Enabled",
                    message=(
                        "The Margarita panel could not be installed: its files could not "
                        "be copied, or ~/.claude/settings.json could not be parsed and "
                        "was left untouched. See the log for details."
                    ),
                )
                self._render()
                return
            self._claude_mod_enabled = True
            save_preferences(self._prefs_path, updates={"claude_mod_enabled": True})
            self._view.alert(
                title="Claude Code Mod Enabled",
                message=(
                    "The Margarita panel was added to Claude Code. Restart your Claude "
                    "Code sessions for it to appear; type /margarita to open it."
                ),
            )
        self._render()

    def refresh_claude_mod(self) -> None:
        """On app start, bring an enabled mod up to date with the bundled one
        (same idea as the hooks auto-update). Silent: a failure only reaches the
        log, and never undoes the user's choice."""
        if not self._claude_mod_enabled:
            return
        if not hooks.install_mod():
            logger.warning("Could not refresh the Claude Code mod; see earlier log lines")

    def toggle_login(self) -> None:
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        self._login_enabled = autostart.is_enabled()
        self._render()

    def reconnect(self) -> None:
        if self._loop and self._daemon:
            asyncio.run_coroutine_threadsafe(self._daemon.reconnect(), self._loop)

    # --- Simulator lifecycle --------------------------------------------

    def _start_simulator(self) -> None:
        """Start the simulator process and add it as a transport."""
        prefs = load_preferences(self._prefs_path)
        self._sim_process = self._sim_process_factory(
            on_window_event=self._on_sim_window_event,
            start_pinned=prefs.get("sim_always_on_top", True),
        )
        self._transport_status["sim"] = False

        async def _do_start():
            client = await self._sim_process.start()
            if client:
                await self._daemon.add_transport("sim", client)
                # Wait for the sender task to establish the TCP connection.
                # Don't call ensure_connected() here - it races with the
                # sender task's connect() and causes duplicate background readers.
                for _ in range(100):  # up to 10 seconds
                    if client.is_connected:
                        break
                    await asyncio.sleep(0.1)
                cur_prefs = load_preferences(self._prefs_path)
                if cur_prefs.get("sim_window_visible", True):
                    await self._sim_process.show_window()
                    # Let the window manager finish presenting before pinning.
                    await asyncio.sleep(0.2)
                await self._sim_process.set_pinned(cur_prefs.get("sim_always_on_top", True))

        if self._loop and self._daemon:
            asyncio.run_coroutine_threadsafe(_do_start(), self._loop)

    def _stop_simulator(self) -> None:
        """Stop the simulator process and remove it as a transport."""

        async def _do_stop():
            await self._daemon.remove_transport("sim")
            if self._sim_process:
                await self._sim_process.stop()
                self._sim_process = None
            self._transport_status.pop("sim", None)

        if self._loop and self._daemon:
            asyncio.run_coroutine_threadsafe(_do_stop(), self._loop)
