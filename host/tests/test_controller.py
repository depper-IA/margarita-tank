"""Tests for ClawdTankController — the platform-independent tray controller.

These exercise real behavior against test doubles, not mocks of the thing
under test: a FakeTrayView stands in for rumps/pystray (the whole point of
the extraction is that the controller has no UI framework coupling), and
FakeDaemon/FakeSimProcess are lightweight collaborators that record calls so
we can assert on real call order and arguments. Preferences are exercised for
real against a temp file — never mocked.
"""
import asyncio
import json
import sys
import threading
import time

import pytest

from clawd_tank_menubar import autostart, hooks
from clawd_tank_menubar.controller import ClawdTankController, TrayState
from clawd_tank_menubar.preferences import load_preferences


# --- Test doubles -----------------------------------------------------------


class FakeView:
    """Records everything the controller told it to do."""

    def __init__(self):
        self.renders: list[TrayState] = []
        self.alerts: list[tuple[str, str]] = []
        self.quit_called = False

    def render(self, state: TrayState) -> None:
        self.renders.append(state)

    def alert(self, title: str, message: str) -> None:
        self.alerts.append((title, message))

    def quit(self) -> None:
        self.quit_called = True


class FakeClient:
    is_connected = True


class FakeDaemon:
    """Records calls in order; async methods behave like the real ones enough
    for the controller's orchestration to be exercised."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def add_transport(self, name, client):
        self.calls.append(("add_transport", name))

    async def remove_transport(self, name):
        self.calls.append(("remove_transport", name))

    async def read_config(self):
        self.calls.append(("read_config",))
        return {}

    async def write_config(self, payload):
        self.calls.append(("write_config", payload))
        return True

    async def reconnect(self):
        self.calls.append(("reconnect",))

    async def _shutdown(self):
        self.calls.append(("_shutdown",))

    def set_session_timeout(self, seconds):
        self.calls.append(("set_session_timeout", seconds))


class FakeSimProcess:
    def __init__(self, on_window_event=None, start_pinned=False):
        self.on_window_event = on_window_event
        self.start_pinned = start_pinned
        self.calls: list[tuple] = []
        self.killed = False
        self.stopped = False

    async def start(self):
        self.calls.append(("start",))
        return FakeClient()

    async def stop(self):
        self.calls.append(("stop",))
        self.stopped = True

    async def kill(self):
        self.calls.append(("kill",))
        self.killed = True

    async def show_window(self):
        self.calls.append(("show_window",))
        return True

    async def hide_window(self):
        self.calls.append(("hide_window",))
        return True

    async def set_pinned(self, pinned):
        self.calls.append(("set_pinned", pinned))
        return True


class DeadThread:
    def is_alive(self):
        return False


class AliveThread:
    def is_alive(self):
        return True


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def prefs_path(tmp_path):
    return tmp_path / "preferences.json"


@pytest.fixture(autouse=True)
def _isolate_autostart(monkeypatch):
    """Never touch the real registry/launchd from controller unit tests —
    every controller construction calls autostart.is_enabled(), and this
    machine's real autostart key gets flipped on/off later in this session
    for the manual Windows tray proof, so tests must not depend on it."""
    state = {"enabled": False}
    monkeypatch.setattr(autostart, "is_enabled", lambda: state["enabled"])
    monkeypatch.setattr(autostart, "enable", lambda: state.__setitem__("enabled", True))
    monkeypatch.setattr(autostart, "disable", lambda: state.__setitem__("enabled", False))
    monkeypatch.setattr(autostart, "is_stale", lambda: False)
    return state


@pytest.fixture
def loop_thread():
    """A real asyncio loop running on a real background thread, exactly like
    production. Needed so asyncio.run_coroutine_threadsafe calls the
    controller makes are actually executed, not merely scheduled."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    loop.close()


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_controller(prefs_path, sim_factory=None):
    view = FakeView()
    controller = ClawdTankController(
        view,
        prefs_path=prefs_path,
        sim_process_factory=sim_factory or (lambda **kw: FakeSimProcess(**kw)),
    )
    return controller, view


# --- Toggling a transport ----------------------------------------------------


def test_toggle_ble_enabled_off_removes_transport_and_saves_prefs(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._ble_enabled = True
    controller._transport_status["ble"] = True

    controller.toggle_ble_enabled()

    assert _wait_until(lambda: ("remove_transport", "ble") in daemon.calls)
    assert controller._ble_enabled is False
    assert load_preferences(prefs_path)["ble_enabled"] is False
    # transport_status is cleared immediately (synchronously), before the
    # daemon call is even scheduled.
    assert "ble" not in controller._transport_status


def test_toggle_ble_enabled_on_adds_transport_and_saves_prefs(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._ble_enabled = False

    controller.toggle_ble_enabled()

    assert _wait_until(lambda: ("add_transport", "ble") in daemon.calls)
    assert controller._ble_enabled is True
    assert load_preferences(prefs_path)["ble_enabled"] is True
    assert controller._transport_status["ble"] is False  # not yet connected


def test_toggle_sim_enabled_on_starts_simulator_and_adds_transport(prefs_path, loop_thread):
    sim_processes = []

    def factory(**kw):
        sp = FakeSimProcess(**kw)
        sim_processes.append(sp)
        return sp

    controller, view = make_controller(prefs_path, sim_factory=factory)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._sim_enabled = False

    controller.toggle_sim_enabled()

    assert _wait_until(lambda: ("add_transport", "sim") in daemon.calls)
    assert controller._sim_enabled is True
    assert load_preferences(prefs_path)["sim_enabled"] is True
    assert len(sim_processes) == 1
    assert ("start",) in sim_processes[0].calls
    # Let _do_start's tail (show_window/set_pinned) finish before the loop
    # fixture tears down, so no task gets destroyed mid-flight.
    assert _wait_until(lambda: ("set_pinned", True) in sim_processes[0].calls)


def test_toggle_sim_enabled_off_stops_simulator_and_removes_transport(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._sim_enabled = True
    fake_sim = FakeSimProcess()
    controller._sim_process = fake_sim
    controller._transport_status["sim"] = True

    controller.toggle_sim_enabled()

    assert _wait_until(lambda: ("remove_transport", "sim") in daemon.calls)
    assert _wait_until(lambda: fake_sim.stopped)
    assert controller._sim_enabled is False
    assert load_preferences(prefs_path)["sim_enabled"] is False
    assert controller._sim_process is None


def test_toggle_sim_window_and_pinned_update_preferences_and_render(prefs_path):
    controller, view = make_controller(prefs_path)
    controller._sim_window_visible = True
    controller._sim_pinned = False

    controller.toggle_sim_window()
    controller.toggle_sim_pinned()

    prefs = load_preferences(prefs_path)
    assert prefs["sim_window_visible"] is False
    assert prefs["sim_always_on_top"] is True
    last = view.renders[-1]
    assert last.sim_window_visible is False
    assert last.sim_pinned is True


# --- Session timeout ---------------------------------------------------------


def test_select_session_timeout_while_connected_writes_config_and_sets_daemon_timeout(
    prefs_path, loop_thread
):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._transport_status["sim"] = True  # connected

    controller.select_session_timeout(600)

    assert controller._session_timeout_seconds == 600
    assert _wait_until(lambda: ("set_session_timeout", 600) in daemon.calls)
    assert _wait_until(lambda: any(c[0] == "write_config" for c in daemon.calls))
    assert any(
        call[0] == "write_config" and json.loads(call[1]) == {"sleep_timeout": 600}
        for call in daemon.calls
    )
    assert view.renders[-1].session_timeout_seconds == 600


def test_select_session_timeout_survives_a_later_unrelated_render(prefs_path, loop_thread):
    """Regression test: an earlier version of _render() re-derived
    session_timeout_seconds from the last device-read config on every call,
    which immediately clobbered a fresh user selection back to the stale
    value (caught live during the Windows tray proof run — see
    controller.py's _render() docstring). A later, unrelated render trigger
    (here, a notification count change) must not revert the user's choice."""
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._transport_status["sim"] = True
    controller._current_config = {"sleep_timeout": 0}  # stale device echo

    controller.select_session_timeout(600)
    assert view.renders[-1].session_timeout_seconds == 600

    controller.on_notification_change(3)  # unrelated render trigger

    assert controller._session_timeout_seconds == 600
    assert view.renders[-1].session_timeout_seconds == 600


def test_select_session_timeout_while_disconnected_does_not_touch_daemon(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    controller._daemon = daemon
    controller._loop = loop_thread
    # no transports connected

    controller.select_session_timeout(60)

    assert controller._session_timeout_seconds == 60
    time.sleep(0.1)  # give any (incorrect) scheduled call a chance to land
    assert daemon.calls == []
    assert view.renders[-1].session_timeout_seconds == 60


# --- Health check -------------------------------------------------------------


def test_health_check_detects_dead_daemon_thread_and_updates_icon(prefs_path):
    controller, view = make_controller(prefs_path)
    controller._daemon_thread = AliveThread()
    controller.check_daemon_health()
    renders_while_alive = len(view.renders)

    controller._daemon_thread = DeadThread()
    controller.check_daemon_health()

    assert len(view.renders) == renders_while_alive + 1
    assert view.renders[-1].icon == "disconnected"


def test_health_check_is_a_noop_while_daemon_thread_is_alive(prefs_path):
    controller, view = make_controller(prefs_path)
    controller._daemon_thread = AliveThread()

    controller.check_daemon_health()

    assert view.renders == []


# --- Quit sequencing -----------------------------------------------------------


def test_quit_stops_things_in_order_then_quits_the_view(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)
    daemon = FakeDaemon()
    sim = FakeSimProcess()
    controller._daemon = daemon
    controller._loop = loop_thread
    controller._sim_process = sim

    controller.quit()

    # sim transport removed from the daemon, then the sim process killed,
    # then (only after both) the daemon is fully shut down.
    call_names = [c[0] for c in daemon.calls]
    assert call_names == ["remove_transport", "_shutdown"]
    assert daemon.calls[0] == ("remove_transport", "sim")
    assert sim.killed is True
    assert controller._sim_process is None
    assert view.quit_called is True


def test_quit_force_exits_on_failure_without_crashing_the_test(prefs_path, loop_thread):
    controller, view = make_controller(prefs_path)

    class BoomDaemon(FakeDaemon):
        async def remove_transport(self, name):
            raise RuntimeError("boom")

    controller._daemon = BoomDaemon()
    controller._loop = loop_thread
    exit_calls = []
    controller._force_exit = lambda code: exit_calls.append(code)

    controller.quit()

    assert exit_calls == [1]
    assert view.quit_called is False


# --- Observer callbacks / icon logic -------------------------------------------


def test_connection_and_notification_changes_drive_icon(prefs_path):
    controller, view = make_controller(prefs_path)
    controller._daemon_thread = AliveThread()

    controller.on_connection_change(True, "sim")
    assert view.renders[-1].icon == "connected"

    controller.on_notification_change(2)
    assert view.renders[-1].icon == "notifications"

    controller.on_notification_change(0)
    assert view.renders[-1].icon == "connected"

    controller.on_connection_change(False, "sim")
    assert view.renders[-1].icon == "disconnected"


# --- Preferences round-trip through the real module ----------------------------


# --- Hooks install -------------------------------------------------------------


def test_install_hooks_writes_real_settings_file_and_alerts_first_time(prefs_path, tmp_path, monkeypatch):
    settings_path = tmp_path / "claude-settings.json"
    notify_dir = tmp_path / "clawd-dir"
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(hooks, "CLAWD_DIR", notify_dir)
    monkeypatch.setattr(hooks, "NOTIFY_SCRIPT_PATH", notify_dir / "clawd-tank-notify")

    controller, view = make_controller(prefs_path)
    assert controller._hooks_installed is False

    controller.install_hooks()

    assert settings_path.exists()  # real file, really written
    assert controller._hooks_installed is True
    assert hooks.STATUSLINE_SCRIPT_PATH.read_text(encoding="utf-8") == \
        hooks.build_statusline_script(sys.platform)
    assert view.alerts == [
        (
            "Hooks Installed",
            "Claude Code hooks have been added to ~/.claude/settings.json. "
            "Restart your Claude Code sessions for the hooks to take effect.",
        )
    ]
    assert view.renders[-1].hooks_installed is True


def test_install_hooks_alerts_updated_when_already_installed(prefs_path, tmp_path, monkeypatch):
    settings_path = tmp_path / "claude-settings.json"
    notify_dir = tmp_path / "clawd-dir"
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(hooks, "CLAWD_DIR", notify_dir)
    monkeypatch.setattr(hooks, "NOTIFY_SCRIPT_PATH", notify_dir / "clawd-tank-notify")
    hooks.install_notify_script()
    hooks.install_hooks()  # pre-install so are_hooks_installed() is True

    controller, view = make_controller(prefs_path)
    controller.install_hooks()

    assert view.alerts[0][0] == "Hooks Updated"


# --- Autostart -------------------------------------------------------------------


def test_toggle_login_enables_then_disables(prefs_path, _isolate_autostart):
    state = _isolate_autostart
    controller, view = make_controller(prefs_path)
    assert controller._login_enabled is False

    controller.toggle_login()
    assert state["enabled"] is True
    assert controller._login_enabled is True
    assert view.renders[-1].login_enabled is True

    controller.toggle_login()
    assert state["enabled"] is False
    assert controller._login_enabled is False
    assert view.renders[-1].login_enabled is False


def test_toggle_preserves_other_preference_keys(prefs_path):
    controller, view = make_controller(prefs_path)
    controller.toggle_sim_window()  # writes sim_window_visible only

    prefs = load_preferences(prefs_path)
    # defaults for keys this toggle never touched are still present (a real
    # read-modify-write against the file, not a mock of preferences.py).
    assert "ble_enabled" in prefs
    assert "sim_always_on_top" in prefs


def test_install_hooks_alerts_failure_when_settings_unparseable(prefs_path, tmp_path, monkeypatch):
    settings_path = tmp_path / "claude-settings.json"
    settings_path.write_text('{"model": "opus",}', encoding="utf-8")
    notify_dir = tmp_path / "clawd-dir"
    monkeypatch.setattr(hooks, "CLAUDE_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(hooks, "CLAWD_DIR", notify_dir)
    monkeypatch.setattr(hooks, "NOTIFY_SCRIPT_PATH", notify_dir / "clawd-tank-notify")

    controller, view = make_controller(prefs_path)
    controller.install_hooks()

    assert settings_path.read_text(encoding="utf-8") == '{"model": "opus",}'
    assert controller._hooks_installed is False
    assert view.alerts[0][0] == "Hooks Not Installed"


# --- Daemon thread death ---------------------------------------------------------


def test_daemon_thread_logs_system_exit(prefs_path, monkeypatch, caplog):
    """SystemExit is not an Exception: sys.exit() inside the daemon (e.g. a
    failed takeover lock) used to kill the thread without a log line."""
    import clawd_tank_menubar.controller as controller_mod

    class ExitingDaemon:
        def __init__(self, **kwargs):
            pass

        async def run(self):
            raise SystemExit(1)

    monkeypatch.setattr(controller_mod, "ClawdDaemon", ExitingDaemon)
    prefs_path.write_text(json.dumps({"ble_enabled": False, "sim_enabled": False}))
    controller, view = make_controller(prefs_path)

    with caplog.at_level("ERROR"):
        controller.start()
        controller._daemon_thread.join(timeout=2)

    assert not controller._daemon_thread.is_alive()
    assert any(
        r.levelname == "ERROR" and "exit" in r.getMessage().lower() and "1" in r.getMessage()
        for r in caplog.records
    )
    controller.check_daemon_health()
    assert view.renders[-1].icon == "disconnected"


# --- Claude Code mod (the side panel) ------------------------------------------


PLUGIN_DIRS = "CLAUDE_CODE_PLUGIN_DIRS"


def _mod_installed() -> bool:
    return (hooks.MOD_DIR / ".claude-plugin" / "plugin.json").is_file()


def test_claude_mod_is_off_by_default_and_reaches_the_view(prefs_path):
    controller, view = make_controller(prefs_path)
    assert controller.claude_mod_enabled is False
    controller.toggle_sim_window()  # any render
    assert view.renders[-1].claude_mod_enabled is False


def test_claude_mod_preference_is_the_initial_state(prefs_path):
    prefs_path.write_text(json.dumps({"claude_mod_enabled": True}))
    controller, _view = make_controller(prefs_path)
    assert controller.claude_mod_enabled is True


def test_toggle_claude_mod_on_installs_enables_saves_and_asks_for_a_restart(prefs_path):
    controller, view = make_controller(prefs_path)

    controller.toggle_claude_mod()

    assert _mod_installed()
    assert hooks.is_mod_enabled()
    assert controller.claude_mod_enabled is True
    assert load_preferences(prefs_path)["claude_mod_enabled"] is True
    assert view.renders[-1].claude_mod_enabled is True
    title, message = view.alerts[-1]
    assert title == "Claude Code Mod Enabled"
    assert "Restart your Claude Code sessions" in message


def test_toggle_claude_mod_off_removes_only_our_folder_and_asks_for_a_restart(prefs_path):
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text(
        json.dumps({"env": {PLUGIN_DIRS: "/my/mods/a"}}), encoding="utf-8")
    controller, view = make_controller(prefs_path)
    controller.toggle_claude_mod()
    assert hooks.is_mod_enabled()

    controller.toggle_claude_mod()

    assert not hooks.is_mod_enabled()
    settings = json.loads(hooks.CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8"))
    assert settings == {"env": {PLUGIN_DIRS: "/my/mods/a"}}
    assert controller.claude_mod_enabled is False
    assert load_preferences(prefs_path)["claude_mod_enabled"] is False
    assert view.renders[-1].claude_mod_enabled is False
    title, message = view.alerts[-1]
    assert title == "Claude Code Mod Disabled"
    assert "Restart your Claude Code sessions" in message


def test_toggle_claude_mod_updates_the_check_before_the_blocking_alert(prefs_path):
    # rumps.alert is modal: whatever is not rendered before it opens stays stale
    # on screen until the user dismisses it, which reads as "the click did nothing".
    controller, view = make_controller(prefs_path)
    seen_at_alert = []
    original_alert = view.alert

    def alert(title, message):
        seen_at_alert.append(view.renders[-1].claude_mod_enabled)
        original_alert(title, message)

    view.alert = alert
    controller.toggle_claude_mod()
    controller.toggle_claude_mod()

    assert seen_at_alert == [True, False]


def test_toggle_claude_mod_preserves_other_preference_keys(prefs_path):
    prefs_path.write_text(json.dumps({"sim_enabled": False}))
    controller, _view = make_controller(prefs_path)
    controller.toggle_claude_mod()
    prefs = load_preferences(prefs_path)
    assert prefs["sim_enabled"] is False
    assert prefs["ble_enabled"] is True


def test_toggle_claude_mod_on_stays_off_when_settings_are_unparseable(prefs_path):
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text('{"model": "opus",}', encoding="utf-8")
    controller, view = make_controller(prefs_path)

    controller.toggle_claude_mod()

    assert hooks.CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8") == '{"model": "opus",}'
    assert controller.claude_mod_enabled is False
    assert load_preferences(prefs_path)["claude_mod_enabled"] is False
    assert view.renders[-1].claude_mod_enabled is False
    assert view.alerts[-1][0] == "Claude Code Mod Not Enabled"


def test_toggle_claude_mod_on_stays_off_when_the_build_has_no_mod(prefs_path, tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "MOD_SOURCE_DIR", tmp_path / "missing")
    controller, view = make_controller(prefs_path)

    controller.toggle_claude_mod()

    assert not hooks.CLAUDE_SETTINGS_PATH.exists()
    assert controller.claude_mod_enabled is False
    assert view.alerts[-1][0] == "Claude Code Mod Not Enabled"


def test_toggle_claude_mod_off_stays_on_when_settings_are_unparseable(prefs_path):
    controller, view = make_controller(prefs_path)
    controller.toggle_claude_mod()
    hooks.CLAUDE_SETTINGS_PATH.write_text("{nope", encoding="utf-8")

    controller.toggle_claude_mod()

    assert hooks.CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8") == "{nope"
    assert controller.claude_mod_enabled is True
    assert load_preferences(prefs_path)["claude_mod_enabled"] is True
    assert view.renders[-1].claude_mod_enabled is True
    assert view.alerts[-1][0] == "Claude Code Mod Not Disabled"


def test_refresh_claude_mod_updates_an_enabled_mod_silently(prefs_path):
    prefs_path.write_text(json.dumps({"claude_mod_enabled": True}))
    controller, view = make_controller(prefs_path)
    assert not _mod_installed()

    controller.refresh_claude_mod()

    assert _mod_installed()
    assert hooks.is_mod_enabled()
    assert view.alerts == []


def test_refresh_claude_mod_fixes_a_stale_installed_copy(prefs_path):
    prefs_path.write_text(json.dumps({"claude_mod_enabled": True}))
    controller, _view = make_controller(prefs_path)
    controller.refresh_claude_mod()
    register = hooks.MOD_DIR / "hooks" / "register.tsx"
    register.write_text("// outdated", encoding="utf-8")

    controller.refresh_claude_mod()

    assert register.read_text(encoding="utf-8") \
        == (hooks.MOD_SOURCE_DIR / "hooks" / "register.tsx").read_text(encoding="utf-8")


def test_refresh_claude_mod_does_nothing_while_the_mod_is_off(prefs_path):
    controller, view = make_controller(prefs_path)

    controller.refresh_claude_mod()

    assert not hooks.MOD_DIR.exists()
    assert not hooks.CLAUDE_SETTINGS_PATH.exists()
    assert view.alerts == []


def test_refresh_claude_mod_survives_unparseable_settings(prefs_path, caplog):
    prefs_path.write_text(json.dumps({"claude_mod_enabled": True}))
    hooks.CLAUDE_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    hooks.CLAUDE_SETTINGS_PATH.write_text("{nope", encoding="utf-8")
    controller, view = make_controller(prefs_path)

    with caplog.at_level("WARNING"):
        controller.refresh_claude_mod()

    assert hooks.CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8") == "{nope"
    assert controller.claude_mod_enabled is True  # the user's choice is not undone
    assert view.alerts == []
    assert any("mod" in r.getMessage().lower() for r in caplog.records)


def test_start_refreshes_the_mod_when_enabled(prefs_path, monkeypatch):
    import clawd_tank_menubar.controller as controller_mod

    class QuietDaemon:
        def __init__(self, **kwargs):
            pass

        async def run(self):
            return None

    monkeypatch.setattr(controller_mod, "ClawdDaemon", QuietDaemon)
    prefs_path.write_text(json.dumps(
        {"ble_enabled": False, "sim_enabled": False, "claude_mod_enabled": True}))
    controller, _view = make_controller(prefs_path)

    controller.start()
    controller._daemon_thread.join(timeout=2)

    assert _mod_installed()
    assert hooks.is_mod_enabled()
