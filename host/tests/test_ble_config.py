# host/tests/test_ble_config.py
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from clawd_tank_daemon.ble_client import (
    ClawdBleClient,
    CONFIG_CHR_UUID,
    VERSION_CHR_UUID,
)


@pytest.mark.asyncio
async def test_read_config_returns_dict():
    client = ClawdBleClient()
    client._client = MagicMock()
    client._client.is_connected = True
    client._client.read_gatt_char = AsyncMock(
        return_value=b'{"brightness":102,"sleep_timeout":300}'
    )
    result = await client.read_config()
    assert result == {"brightness": 102, "sleep_timeout": 300}
    client._client.read_gatt_char.assert_called_once_with(CONFIG_CHR_UUID)


@pytest.mark.asyncio
async def test_read_config_not_connected():
    client = ClawdBleClient()
    client._client = None
    result = await client.read_config()
    assert result == {}


@pytest.mark.asyncio
async def test_write_config_success():
    client = ClawdBleClient()
    client._client = MagicMock()
    client._client.is_connected = True
    client._client.write_gatt_char = AsyncMock()
    result = await client.write_config('{"brightness":200}')
    assert result is True
    client._client.write_gatt_char.assert_called_once_with(
        CONFIG_CHR_UUID, b'{"brightness":200}', response=False
    )


@pytest.mark.asyncio
async def test_write_config_not_connected():
    client = ClawdBleClient()
    client._client = None
    result = await client.write_config('{"brightness":200}')
    assert result is False


@pytest.mark.asyncio
async def test_write_config_ble_error():
    client = ClawdBleClient()
    client._client = MagicMock()
    client._client.is_connected = True
    client._client.write_gatt_char = AsyncMock(side_effect=Exception("BLE error"))
    result = await client.write_config('{"brightness":200}')
    assert result is False


# --- Transient GATT op retry ---
# A GATT op right after connect (or during a liveness probe) can fail
# transiently. One bounded retry should absorb that without tearing down
# the whole connection.

@pytest.mark.asyncio
async def test_write_notification_retries_once_on_transient_failure():
    disconnect_calls = []
    client = ClawdBleClient(on_disconnect_cb=lambda: disconnect_calls.append(True))
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.write_gatt_char = AsyncMock(
        side_effect=[Exception("Characteristic ... was not found!"), None]
    )
    client._client = underlying

    result = await client.write_notification('{"action":"set_time"}')

    assert result is True
    assert underlying.write_gatt_char.call_count == 2
    assert client._client is underlying
    assert disconnect_calls == []


@pytest.mark.asyncio
async def test_write_notification_drops_after_exhausting_retries():
    disconnect_calls = []
    client = ClawdBleClient(on_disconnect_cb=lambda: disconnect_calls.append(True))
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.write_gatt_char = AsyncMock(side_effect=Exception("BLE error"))
    underlying.disconnect = AsyncMock()
    client._client = underlying

    result = await client.write_notification('{"action":"set_time"}')

    assert result is False
    assert client._client is None
    assert disconnect_calls == [True]
    assert underlying.write_gatt_char.call_count == 2


# --- Active liveness probe (ping) ---
# Regression: on macOS CoreBluetooth the disconnect callback often does NOT fire
# on range/sleep link loss, and notification writes use response=False so a dead
# link never raises. is_connected then stays stale-True and the sender's reconnect
# branch is never taken. ping() is the active round-trip probe that surfaces the
# dead link so the sender re-scans.

@pytest.mark.asyncio
async def test_ping_returns_true_when_link_alive():
    client = ClawdBleClient()
    client._client = MagicMock()
    client._client.is_connected = True
    client._client.read_gatt_char = AsyncMock(return_value=b"2")
    result = await client.ping()
    assert result is True
    client._client.read_gatt_char.assert_called_once_with(VERSION_CHR_UUID)
    # Link is alive — client must NOT be dropped.
    assert client._client is not None


@pytest.mark.asyncio
async def test_ping_not_connected_returns_false():
    client = ClawdBleClient()
    client._client = None
    result = await client.ping()
    assert result is False


@pytest.mark.asyncio
async def test_ping_failure_drops_client_and_notifies():
    """A failed probe must clear the client (so is_connected -> False) and fire
    the disconnect callback, which is what triggers the sender to re-scan."""
    disconnect_calls = []
    client = ClawdBleClient(on_disconnect_cb=lambda: disconnect_calls.append(True))
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.read_gatt_char = AsyncMock(side_effect=Exception("link dead"))
    underlying.disconnect = AsyncMock()
    client._client = underlying

    result = await client.ping()

    assert result is False
    assert client._client is None          # client dropped -> is_connected False
    assert client.is_connected is False
    assert disconnect_calls == [True]      # observer notified


@pytest.mark.asyncio
async def test_ping_times_out_and_drops_client(monkeypatch):
    """A read that hangs on a stale-connected dead link must NOT block forever.
    The bounded timeout makes ping() fail fast, drop the client, and let the
    sender reconnect — without holding _lock for bleak's full default timeout."""
    import clawd_tank_daemon.ble_client as bc
    monkeypatch.setattr(bc, "GATT_READ_TIMEOUT_SECS", 0.05)
    client = ClawdBleClient()
    underlying = MagicMock()
    underlying.is_connected = True

    async def slow_read(uuid):
        await asyncio.sleep(1.0)  # longer than the patched timeout

    underlying.read_gatt_char = slow_read
    underlying.disconnect = AsyncMock()
    client._client = underlying

    result = await client.ping()

    assert result is False
    assert client._client is None


@pytest.mark.asyncio
async def test_read_version_returns_one_when_not_connected():
    client = ClawdBleClient()
    client._client = None
    assert await client.read_version() == 1


@pytest.mark.asyncio
async def test_read_version_parses_numeric_payload():
    client = ClawdBleClient()
    client._client = MagicMock()
    client._client.is_connected = True
    client._client.read_gatt_char = AsyncMock(return_value=b"2")
    assert await client.read_version() == 2


@pytest.mark.asyncio
async def test_read_version_non_numeric_payload_returns_one_without_drop():
    """A successful read of a non-numeric payload means v1 firmware — the link
    is alive, so the client must NOT be dropped."""
    client = ClawdBleClient()
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.read_gatt_char = AsyncMock(return_value=b"notanumber")
    underlying.disconnect = AsyncMock()
    client._client = underlying
    assert await client.read_version() == 1
    assert client._client is underlying  # link alive, not dropped


@pytest.mark.asyncio
async def test_read_version_read_failure_drops_client():
    client = ClawdBleClient()
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.read_gatt_char = AsyncMock(side_effect=Exception("link dead"))
    underlying.disconnect = AsyncMock()
    client._client = underlying
    assert await client.read_version() == 1
    assert client._client is None  # read failure dropped the client


@pytest.mark.asyncio
async def test_read_version_is_lock_guarded():
    """read_version reads the same characteristic as ping(); both must hold
    _lock so they never issue overlapping reads (bleak keys read futures by
    characteristic handle, so a concurrent read clobbers the in-flight one)."""
    client = ClawdBleClient()
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.read_gatt_char = AsyncMock(return_value=b"2")
    client._client = underlying

    await client._lock.acquire()
    task = asyncio.create_task(client.read_version())
    await asyncio.sleep(0.01)
    assert not task.done()  # blocked on the lock held by us
    client._lock.release()
    assert await task == 2


@pytest.mark.asyncio
async def test_disconnect_notified_only_once_per_connection():
    """The proactive drop (_handle_disconnect) and bleak's own disconnect
    callback (_on_disconnect) can both fire for the same physical disconnect;
    the daemon must be notified only once."""
    calls = []
    client = ClawdBleClient(on_disconnect_cb=lambda: calls.append(True))
    underlying = MagicMock()
    underlying.is_connected = True
    underlying.disconnect = AsyncMock()
    client._client = underlying

    await client._handle_disconnect()      # proactive drop notifies
    client._on_disconnect(underlying)      # bleak's late callback for same drop

    assert calls == [True]                 # collapsed to a single notification


@pytest.mark.asyncio
async def test_disconnect_notified_resets_on_new_connection():
    """A fresh connection re-arms the guard so the next disconnect notifies."""
    calls = []
    client = ClawdBleClient(on_disconnect_cb=lambda: calls.append(True))
    u1 = MagicMock()
    u1.is_connected = True
    u1.disconnect = AsyncMock()
    client._client = u1

    await client._handle_disconnect()
    assert calls == [True]

    client._disconnect_notified = False    # connect() does this on success
    u2 = MagicMock()
    u2.is_connected = True
    u2.disconnect = AsyncMock()
    client._client = u2

    await client._handle_disconnect()
    assert calls == [True, True]


@pytest.mark.asyncio
async def test_connect_bypasses_windows_gatt_cache():
    """Windows caches the GATT table per MAC; after a firmware update that
    changes the table, the stale cache hides characteristics. Services must
    always be read from the device."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    bleak_client = MagicMock()
    bleak_client.connect = AsyncMock()
    bleak_client.mtu_size = 256
    with patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(return_value=device),
    ), patch(
        "clawd_tank_daemon.ble_client.BleakClient", return_value=bleak_client
    ) as client_cls:
        await ClawdBleClient().connect()

    _, kwargs = client_cls.call_args
    assert kwargs["winrt"] == {"use_cached_services": False}


@pytest.mark.asyncio
async def test_concurrent_connects_share_one_scan_and_connection():
    """The sender's ensure_connected() and the daemon's reconnect() can ask
    for a connection at the same time. The device accepts a single
    connection, so a second caller must join the in-flight attempt instead
    of starting its own scan/connect loop — and must not tear down the
    connection that attempt just made."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    bleak_client = MagicMock()
    bleak_client.connect = AsyncMock()
    bleak_client.disconnect = AsyncMock()
    bleak_client.is_connected = True
    bleak_client.mtu_size = 256
    scan_gate = asyncio.Event()

    async def slow_scan(*args, **kwargs):
        await scan_gate.wait()
        return device

    ble = ClawdBleClient()
    with patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(side_effect=slow_scan),
    ) as scan, patch(
        "clawd_tank_daemon.ble_client.BleakClient", return_value=bleak_client
    ) as client_cls:
        both = asyncio.gather(ble.ensure_connected(), ble.connect())
        for _ in range(5):
            await asyncio.sleep(0)  # let both callers reach the scan
        scan_gate.set()
        await both

    assert scan.await_count == 1
    assert client_cls.call_count == 1
    bleak_client.disconnect.assert_not_awaited()
    assert ble.is_connected


@pytest.mark.asyncio
async def test_connect_retries_when_scan_never_finishes():
    """bleak's WinRT scanner stop() waits for the Stopped event with no
    timeout, so find_device_by_name can hang forever after its own scan
    timeout. The connect loop must bound the whole scan and keep retrying."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    bleak_client = MagicMock()
    bleak_client.connect = AsyncMock()
    bleak_client.is_connected = True
    bleak_client.mtu_size = 256
    never = asyncio.Event()
    calls = 0

    async def hung_then_found(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await never.wait()  # scanner stop() that never completes
        return device

    with patch(
        "clawd_tank_daemon.ble_client.SCAN_HARD_TIMEOUT_SECS", 0.05
    ), patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(side_effect=hung_then_found),
    ) as scan, patch(
        "clawd_tank_daemon.ble_client.BleakClient", return_value=bleak_client
    ) as client_cls:
        ble = ClawdBleClient()
        await asyncio.wait_for(ble.connect(), timeout=2)

    assert scan.await_count == 2
    assert client_cls.call_count == 1
    assert ble.is_connected


@pytest.mark.asyncio
async def test_connect_retries_when_connect_never_finishes():
    """bleak's WinRT connect() waits for the GATT session to become active
    outside its own timeout, so a single attempt can hang forever. The
    connect loop must bound each attempt and retry with a fresh client."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    never = asyncio.Event()

    async def hang():
        await never.wait()  # GATT session that never becomes active

    hung = MagicMock()
    hung.connect = AsyncMock(side_effect=hang)
    good = MagicMock()
    good.connect = AsyncMock()
    good.is_connected = True
    good.mtu_size = 256

    with patch(
        "clawd_tank_daemon.ble_client.CONNECT_HARD_TIMEOUT_SECS", 0.05
    ), patch(
        "clawd_tank_daemon.ble_client.SCAN_INTERVAL_SECS", 0
    ), patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(return_value=device),
    ), patch(
        "clawd_tank_daemon.ble_client.BleakClient", side_effect=[hung, good]
    ) as client_cls:
        ble = ClawdBleClient()
        await asyncio.wait_for(ble.connect(), timeout=2)

    assert client_cls.call_count == 2
    assert ble._client is good
    assert ble.is_connected


def _hangs_even_when_cancelled(release: asyncio.Event):
    """Fake that hangs, and keeps hanging during cancellation cleanup until
    ``release`` is set — like bleak's WinRT scanner stop() / connect cleanup,
    which run unbounded awaits in their finally / __aexit__ paths."""

    async def fake(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()  # cleanup hangs like bleak's stop()
            raise

    return fake


async def _release_abandoned(ble: ClawdBleClient, release: asyncio.Event, *tasks):
    """Let hung-on-cancel fakes finish so no task outlives the test."""
    release.set()
    for task in tasks:
        task.cancel()
    pending = [*tasks, *getattr(ble, "_abandoned_tasks", ())]
    if pending:
        await asyncio.wait(pending, timeout=1)


@pytest.mark.asyncio
async def test_connect_retries_when_scan_hangs_even_when_cancelled():
    """asyncio.wait_for cancels the inner task on timeout and then awaits its
    completion. bleak's WinRT scanner re-runs its unbounded stop() during
    cancellation cleanup, so wait_for itself never returns. The connect loop
    must abandon the hung scan instead of awaiting it, and retry."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    bleak_client = MagicMock()
    bleak_client.connect = AsyncMock()
    bleak_client.is_connected = True
    bleak_client.mtu_size = 256
    release = asyncio.Event()
    hung = _hangs_even_when_cancelled(release)
    calls = 0

    async def hung_then_found(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            await hung()
        return device

    ble = ClawdBleClient()
    with patch(
        "clawd_tank_daemon.ble_client.SCAN_HARD_TIMEOUT_SECS", 0.05
    ), patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(side_effect=hung_then_found),
    ) as scan, patch(
        "clawd_tank_daemon.ble_client.BleakClient", return_value=bleak_client
    ) as client_cls:
        outer = asyncio.ensure_future(ble.connect())
        try:
            done, _ = await asyncio.wait({outer}, timeout=2)
            assert outer in done, "connect() hung awaiting a cancelled scan"
            outer.result()
        finally:
            await _release_abandoned(ble, release, outer)

    assert scan.await_count == 2
    assert client_cls.call_count == 1
    assert ble.is_connected


@pytest.mark.asyncio
async def test_connect_retries_when_connect_hangs_even_when_cancelled():
    """Same as the scan case for bleak's WinRT connect cleanup: the hung
    attempt must be abandoned (not awaited), its BleakClient never kept, and
    a fresh client tried."""
    device = MagicMock(name="device", address="58:8C:81:54:73:46")
    release = asyncio.Event()

    hung = MagicMock()
    hung.connect = AsyncMock(side_effect=_hangs_even_when_cancelled(release))
    hung.is_connected = False
    good = MagicMock()
    good.connect = AsyncMock()
    good.is_connected = True
    good.mtu_size = 256

    ble = ClawdBleClient()
    with patch(
        "clawd_tank_daemon.ble_client.CONNECT_HARD_TIMEOUT_SECS", 0.05
    ), patch(
        "clawd_tank_daemon.ble_client.SCAN_INTERVAL_SECS", 0
    ), patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(return_value=device),
    ), patch(
        "clawd_tank_daemon.ble_client.BleakClient", side_effect=[hung, good]
    ) as client_cls:
        outer = asyncio.ensure_future(ble.connect())
        try:
            done, _ = await asyncio.wait({outer}, timeout=2)
            assert outer in done, "connect() hung awaiting a cancelled attempt"
            outer.result()
        finally:
            await _release_abandoned(ble, release, outer)

    assert client_cls.call_count == 2
    assert ble._client is good
    assert ble.is_connected


@pytest.mark.asyncio
async def test_cancelling_connect_propagates_and_cancels_inner_scan():
    """remove_transport/shutdown cancel connect(). That cancellation must
    propagate promptly (not wait for a scan whose cleanup hangs) and must
    cancel the in-flight scan too."""
    release = asyncio.Event()
    inner_cancelled = asyncio.Event()

    async def flag_on_cancel(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            inner_cancelled.set()
            await release.wait()  # cleanup hangs like bleak's stop()
            raise

    ble = ClawdBleClient()
    with patch(
        "clawd_tank_daemon.ble_client.BleakScanner.find_device_by_name",
        AsyncMock(side_effect=flag_on_cancel),
    ):
        outer = asyncio.ensure_future(ble.connect())
        try:
            for _ in range(5):
                await asyncio.sleep(0)  # let connect() reach the scan
            outer.cancel()
            done, _ = await asyncio.wait({outer}, timeout=2)
            assert outer in done, "cancelled connect() hung on scan cleanup"
            assert outer.cancelled()
            assert inner_cancelled.is_set()
        finally:
            await _release_abandoned(ble, release, outer)

    assert not ble.is_connected
