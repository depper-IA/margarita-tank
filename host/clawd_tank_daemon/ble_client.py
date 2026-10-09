"""BLE GATT client for communicating with the Clawd Tank ESP32 device."""

import asyncio
import json
import logging
from bleak import BleakClient, BleakScanner

logger = logging.getLogger("clawd-tank.ble")

# BLE advertised name the firmware uses (ble_service.c). Must match exactly or
# the scanner never finds the device. Single source of truth for renaming.
DEVICE_NAME = "Margarita"

SERVICE_UUID = "aecbefd9-98a2-4773-9fed-bb2166daa49a"
NOTIFICATION_CHR_UUID = "71ffb137-8b7a-47c9-9a7a-4b1b16662d9a"
CONFIG_CHR_UUID = "e9f6e626-5fca-4201-b80c-4d2b51c40f51"
VERSION_CHR_UUID = "b6dc9a5b-5041-4b32-9f8d-34321df8637c"
SCAN_INTERVAL_SECS = 5
# Hard bound on a whole scan. find_device_by_name's timeout covers detection
# only; bleak's WinRT scanner stop() then awaits the Stopped event with no
# timeout and can hang forever, freezing the reconnect loop.
SCAN_HARD_TIMEOUT_SECS = SCAN_INTERVAL_SECS + 5
# A scan that raises instead of timing out is retried after a growing delay
# (base * 2**n, capped). On macOS the first CBCentralManager of a process waits
# for the TCC privacy check, which takes 2-4 s at app start; bleak 0.22.3's
# CentralManagerDelegate.init blocks the event loop for 1 s and then raises
# BleakError("Bluetooth device is turned off"). The next attempt succeeds, so
# the first retry comes quickly, but a Bluetooth radio that really is off must
# not cost one blocked second every few seconds forever.
SCAN_ERROR_RETRY_BASE_SECS = 1.0
SCAN_ERROR_RETRY_MAX_SECS = 10.0
# Consecutive identical scan outcomes (errors, "not found") are logged at the
# first occurrence and then once per this many, so a stuck loop is visible in
# the log without a line per attempt.
SCAN_LOG_EVERY_N = 6
# Hard bound on a single connect attempt. bleak's WinRT connect() waits for
# the GATT session to become active outside its own 10s timeout, so an
# attempt can likewise hang forever.
CONNECT_HARD_TIMEOUT_SECS = 20
# Upper bound for a single GATT read. bleak's CoreBluetooth backend has its own
# (much longer, ~20s) read timeout, but on a stale-connected dead link that long
# hold blocks every other GATT op behind _lock and delays reconnect. Fail fast.
GATT_READ_TIMEOUT_SECS = 5.0
# A GATT op right after connect (or during a liveness probe) can fail
# transiently — see the CharacteristicNotFoundError investigation. One
# bounded retry absorbs that without tearing down the whole connection.
GATT_OP_MAX_ATTEMPTS = 2
GATT_OP_RETRY_DELAY_SECS = 0.3


class _BoundedTimeout(asyncio.TimeoutError):
    """Raised by _run_bounded when it abandons a task. It has already been
    logged there; a plain TimeoutError (e.g. bleak's own connect timeout)
    has not, so callers tell the two apart by type."""


class ClawdBleClient:
    """Manages BLE connection to the Clawd Tank ESP32 device."""

    def __init__(self, on_disconnect_cb=None, on_connect_cb=None):
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        # Serializes connect() so concurrent callers (the sender's
        # ensure_connected and the daemon's reconnect) share one scan/connect
        # loop. Separate from _lock: GATT ops must not wait on a scan.
        self._connect_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_disconnect_cb = on_disconnect_cb
        self._on_connect_cb = on_connect_cb
        # Collapses the proactive drop (_handle_disconnect) and bleak's own
        # disconnected_callback into a single notification per connection.
        self._disconnect_notified = False
        # Strong references to scan/connect tasks abandoned by _run_bounded
        # after a timeout, so they are not garbage-collected mid-flight.
        self._abandoned_tasks: set[asyncio.Task] = set()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        """Scan for and connect to the Clawd Tank device. Retries until found.

        Single-flight: a caller that arrives while another connect is in
        progress waits for it and reuses the resulting connection instead of
        starting a second scan/connect loop (the device accepts only one
        connection, and tearing down the fresh one would undo the attempt).
        """
        joined_in_flight = self._connect_lock.locked()
        async with self._connect_lock:
            if joined_in_flight and self.is_connected:
                return
            await self._connect_until_found()

    async def _connect_until_found(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._client is not None:
            await self.disconnect()
        scan_errors = 0  # consecutive scans that raised
        misses = 0  # consecutive scans that finished without finding the board
        while True:
            logger.info("Scanning for %s device...", DEVICE_NAME)
            try:
                device = await self._run_bounded(
                    BleakScanner.find_device_by_name(
                        DEVICE_NAME, timeout=SCAN_INTERVAL_SECS
                    ),
                    SCAN_HARD_TIMEOUT_SECS,
                    "BLE scan",
                )
            except _BoundedTimeout:
                continue
            except asyncio.TimeoutError:
                logger.warning("BLE scan timed out, retrying...")
                continue
            except Exception as e:
                # Anything else the scanner raises (bleak's "Bluetooth device
                # is turned off" / "not authorized" while CoreBluetooth is
                # still starting up) must not end this loop: it would end the
                # sender task above it, and nothing would reconnect again.
                scan_errors += 1
                delay = min(
                    SCAN_ERROR_RETRY_MAX_SECS,
                    SCAN_ERROR_RETRY_BASE_SECS * 2 ** min(scan_errors - 1, 10),
                )
                level = (
                    logging.WARNING
                    if scan_errors == 1 or scan_errors % SCAN_LOG_EVERY_N == 0
                    else logging.DEBUG
                )
                logger.log(
                    level,
                    "BLE scan failed (%d in a row): %s; retrying in %gs",
                    scan_errors, e or repr(e), delay,
                )
                await asyncio.sleep(delay)
                continue
            scan_errors = 0
            if device is None:
                misses += 1
                if misses % SCAN_LOG_EVERY_N == 0:
                    logger.info(
                        "%s not found after %d scans in a row; still looking",
                        DEVICE_NAME, misses,
                    )
                else:
                    logger.debug("%s not found, retrying...", DEVICE_NAME)
                continue
            misses = 0

            logger.info("Found %s: %s (%s)", DEVICE_NAME, device.name, device.address)
            try:
                # Windows caches the GATT table per MAC; a firmware update that
                # changes it leaves stale handles ("Characteristic not found").
                client = BleakClient(
                    device,
                    disconnected_callback=self._on_disconnect,
                    winrt={"use_cached_services": False},
                )
                # An abandoned attempt's client is never kept as self._client.
                await self._run_bounded(
                    client.connect(),
                    CONNECT_HARD_TIMEOUT_SECS,
                    "BLE connect",
                    on_abandoned_done=lambda task, c=client: (
                        self._drop_stray_client(c, task)
                    ),
                )
                self._client = client
                self._disconnect_notified = False  # re-arm for this connection
                logger.info("Connected to %s (MTU: %d)", DEVICE_NAME, client.mtu_size)
                if self._on_connect_cb:
                    self._on_connect_cb()
                return
            except _BoundedTimeout:
                await asyncio.sleep(SCAN_INTERVAL_SECS)
            except asyncio.TimeoutError:
                logger.warning(
                    "Connection failed: timed out after bleak's connect timeout, "
                    "retrying..."
                )
                await asyncio.sleep(SCAN_INTERVAL_SECS)
            except Exception as e:
                logger.warning("Connection failed: %s, retrying...", e or repr(e))
                await asyncio.sleep(SCAN_INTERVAL_SECS)

    async def _run_bounded(
        self, coro, timeout: float, what: str, on_abandoned_done=None
    ):
        """Run ``coro`` as a task and return its result within ``timeout``.

        Plain ``asyncio.wait_for`` is not enough: on timeout (or when the
        caller is cancelled) it cancels the inner task and then awaits its
        completion. bleak's WinRT scanner re-runs its unbounded stop() during
        cancellation cleanup, and its connect cleanup can hang the same way, so
        that await never returns. Here a timed-out task is cancelled and
        abandoned instead of awaited, and asyncio.TimeoutError is raised so
        the caller can retry. If the caller itself is cancelled, the task is
        cancelled too and the CancelledError propagates.

        ``on_abandoned_done(task)``, if given, is called once an abandoned
        task finally finishes, so the caller can undo a late side effect.
        """
        task = asyncio.ensure_future(coro)
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            self._abandon(task, on_abandoned_done)
            raise
        if task in done:
            return task.result()
        logger.warning(
            "%s did not finish within %ss; abandoned it, retrying", what, timeout
        )
        self._abandon(task, on_abandoned_done)
        raise _BoundedTimeout(f"{what} timed out after {timeout}s")

    def _abandon(self, task: asyncio.Task, on_done=None) -> None:
        """Cancel ``task`` without awaiting it, keeping it referenced until
        it finishes and retrieving its exception so asyncio does not log
        "Task exception was never retrieved"."""
        task.cancel()
        if task.done():
            return
        self._abandoned_tasks.add(task)
        task.add_done_callback(self._on_abandoned_done)
        if on_done is not None:
            task.add_done_callback(on_done)

    def _on_abandoned_done(self, task: asyncio.Task) -> None:
        self._abandoned_tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                logger.debug("Abandoned BLE task finished with: %s", exc)

    def _drop_stray_client(self, client: BleakClient, task: asyncio.Task) -> None:
        """Disconnect a client whose abandoned connect() came up anyway.

        bleak's cleanup can let an abandoned attempt finish and bring the
        link up. The daemon never tracks that client, and the ESP32 accepts
        a single connection, so the stray link would block every retry.
        """
        if client is self._client:
            return
        succeeded = not task.cancelled() and task.exception() is None
        if not (succeeded or client.is_connected):
            return
        logger.warning(
            "Abandoned BLE connect came up later; disconnecting the stray link"
        )
        cleanup = asyncio.ensure_future(self._disconnect_stray(client))
        self._abandoned_tasks.add(cleanup)
        cleanup.add_done_callback(self._abandoned_tasks.discard)

    @staticmethod
    async def _disconnect_stray(client: BleakClient) -> None:
        try:
            await client.disconnect()
        except Exception as e:
            logger.debug("Stray BLE client disconnect failed: %s", e)

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnect — may be called from a non-event-loop thread."""
        if self._client is not None and client is not self._client:
            # A stray client (e.g. an abandoned connect torn down by
            # _drop_stray_client) must not drop the current link.
            logger.debug("Ignoring disconnect of a stale BLE client")
            return
        logger.warning("Disconnected from %s", DEVICE_NAME)
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._clear_client)
            self._loop.call_soon_threadsafe(self._notify_disconnect)
        else:
            self._clear_client()
            self._notify_disconnect()

    def _clear_client(self) -> None:
        self._client = None

    def _notify_disconnect(self) -> None:
        """Fire the disconnect callback at most once per connection.

        A proactive drop (_handle_disconnect, after a write/read/probe failure)
        and bleak's own disconnected_callback (_on_disconnect) can both fire for
        the same physical disconnect. This guard collapses them so the daemon —
        and the menu bar icon — sees a single disconnect. The guard is re-armed
        on the next successful connect().
        """
        if self._disconnect_notified:
            return
        self._disconnect_notified = True
        if self._on_disconnect_cb:
            self._on_disconnect_cb()

    async def _handle_disconnect(self) -> None:
        """Force-drop the bleak client after an op failure and notify."""
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
        self._notify_disconnect()

    async def _retry_gatt_op(self, op):
        """Run a GATT operation, retrying up to GATT_OP_MAX_ATTEMPTS times with
        a short delay on failure. Re-raises the last exception if every
        attempt fails; the caller decides how to handle that (as it already
        does today for a single-attempt failure)."""
        for attempt in range(1, GATT_OP_MAX_ATTEMPTS + 1):
            try:
                return await op()
            except Exception as e:
                if attempt == GATT_OP_MAX_ATTEMPTS:
                    raise
                logger.warning(
                    "GATT op failed (attempt %d/%d), retrying: %s",
                    attempt, GATT_OP_MAX_ATTEMPTS, e,
                )
                await asyncio.sleep(GATT_OP_RETRY_DELAY_SECS)

    async def ensure_connected(self) -> None:
        """Reconnect if disconnected."""
        if not self.is_connected:
            await self.connect()

    async def write_notification(self, payload: str) -> bool:
        """Write a JSON payload to the notification characteristic.

        Returns True on success, False on failure.
        """
        async with self._lock:
            if not self.is_connected:
                logger.warning("Not connected, cannot write")
                return False
            try:
                data = payload.encode("utf-8")
                await self._retry_gatt_op(
                    lambda: self._client.write_gatt_char(
                        NOTIFICATION_CHR_UUID, data, response=False
                    )
                )
                logger.debug("Wrote %d bytes to BLE", len(data))
                return True
            except Exception as e:
                logger.error("BLE write failed: %s", e)
                await self._handle_disconnect()
                return False

    async def read_config(self) -> dict:
        """Read full device config from the config characteristic.

        Returns empty dict if not connected or on error.
        """
        async with self._lock:
            if not self.is_connected:
                logger.warning("Not connected, cannot read config")
                return {}
            try:
                data = await self._retry_gatt_op(
                    lambda: self._client.read_gatt_char(CONFIG_CHR_UUID)
                )
                return json.loads(data.decode("utf-8"))
            except Exception as e:
                logger.error("Config read failed: %s", e)
                await self._handle_disconnect()
                return {}

    async def _read_version_char(self) -> bytes:
        """Lock-guarded, timeout-bounded read of the version characteristic.

        Shared by read_version() and ping() so the version round-trip lives in
        one place. The lock serializes it with writes and with a concurrent
        read of the same characteristic (bleak keys in-flight read futures by
        characteristic handle, so overlapping reads would clobber each other).
        Raises if the link is down; on a read failure it drops the client (so
        the sender re-scans) and re-raises.
        """
        async with self._lock:
            if not self.is_connected:
                raise ConnectionError("BLE link not connected")
            try:
                return await self._retry_gatt_op(
                    lambda: asyncio.wait_for(
                        self._client.read_gatt_char(VERSION_CHR_UUID),
                        timeout=GATT_READ_TIMEOUT_SECS,
                    )
                )
            except Exception as e:
                logger.warning("BLE version read failed: %s", e)
                await self._handle_disconnect()
                raise

    async def read_version(self) -> int:
        """Read protocol version from firmware. Returns 1 if characteristic
        absent, unreadable, or the link is down."""
        try:
            data = await self._read_version_char()
        except Exception:
            return 1  # not connected, or read failed (client already dropped)
        try:
            return int(data.decode("utf-8").strip())
        except ValueError:
            return 1  # payload wasn't a number — firmware speaks v1

    async def ping(self) -> bool:
        """Active liveness probe: a round-trip GATT read that proves the link.

        macOS CoreBluetooth frequently fails to fire ``disconnected_callback``
        when the link is lost to range or sleep, and notification writes use
        ``response=False`` (no ACK), so a dead link never surfaces as an error.
        ``is_connected`` therefore stays stale-True and the sender's reconnect
        branch is never taken. This probe forces a round-trip; on failure it
        drops the client (clearing ``is_connected``) and fires the disconnect
        callback, which is what makes the sender re-scan and reconnect.

        Returns True if the link round-trips, False otherwise.
        """
        try:
            await self._read_version_char()
            return True
        except Exception:
            return False

    async def write_config(self, payload: str) -> bool:
        """Write a partial config JSON to the config characteristic.

        Returns True on success, False on failure.
        """
        async with self._lock:
            if not self.is_connected:
                logger.warning("Not connected, cannot write config")
                return False
            try:
                data = payload.encode("utf-8")
                await self._retry_gatt_op(
                    lambda: self._client.write_gatt_char(
                        CONFIG_CHR_UUID, data, response=False
                    )
                )
                logger.debug("Config write: %s", payload)
                return True
            except Exception as e:
                logger.error("Config write failed: %s", e)
                await self._handle_disconnect()
                return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
