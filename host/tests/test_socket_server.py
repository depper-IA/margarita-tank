"""Tests for SocketServer: concurrent connections, malformed JSON, clean shutdown."""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from clawd_tank_daemon.socket_server import MAX_LINE_BYTES, SocketServer

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="loopback TCP ingress is the Windows path"
)


def _ingress_path(tmpdir: str) -> Path:
    """What the server listens on: the Unix socket itself on POSIX, the file the
    Windows server publishes its port and token in."""
    name = "endpoint.json" if sys.platform == "win32" else "test.sock"
    return Path(tmpdir) / name


async def _connect(path: Path):
    """Open a connection to the server, authenticating where that is required."""
    if sys.platform == "win32":
        endpoint = json.loads(path.read_text(encoding="utf-8"))
        reader, writer = await asyncio.open_connection("127.0.0.1", endpoint["port"])
        writer.write(endpoint["token"].encode("utf-8") + b"\n")
        return reader, writer
    return await asyncio.open_unix_connection(str(path))


async def _send_raw(socket_path: Path, data: bytes) -> None:
    """Send data to the socket, appending a newline delimiter."""
    _, writer = await _connect(socket_path)
    writer.write(data + b"\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_socket_server_receives_message():
    """Server must deliver a well-formed JSON message to the callback."""
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()

        payload = {"event": "add", "session_id": "s1", "project": "p", "message": "m"}
        await _send_raw(sock_path, json.dumps(payload).encode())
        await asyncio.sleep(0.05)  # allow handler coroutine to run

        assert len(received) == 1
        assert received[0]["event"] == "add"
        assert received[0]["session_id"] == "s1"

        await server.stop()


@pytest.mark.asyncio
async def test_socket_server_concurrent_connections():
    """Multiple simultaneous connections must each deliver their message."""
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()

        messages = [
            {"event": "add", "session_id": f"s{i}", "project": "p", "message": "m"}
            for i in range(5)
        ]
        await asyncio.gather(*[
            _send_raw(sock_path, json.dumps(m).encode()) for m in messages
        ])
        await asyncio.sleep(0.1)

        assert len(received) == 5
        session_ids = {r["session_id"] for r in received}
        assert session_ids == {"s0", "s1", "s2", "s3", "s4"}

        await server.stop()


@pytest.mark.asyncio
async def test_socket_server_malformed_json_does_not_crash():
    """Invalid JSON must be silently absorbed — server must keep running."""
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()

        # Send garbage
        await _send_raw(sock_path, b"not json {{{{")
        await asyncio.sleep(0.05)

        # Server must still accept a subsequent valid message
        payload = {"event": "dismiss", "session_id": "s1"}
        await _send_raw(sock_path, json.dumps(payload).encode())
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["event"] == "dismiss"

        await server.stop()


@pytest.mark.asyncio
async def test_socket_server_stop_removes_socket_file():
    """stop() must clean up the socket file."""
    async def on_message(msg: dict) -> None:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()
        assert sock_path.exists()

        await server.stop()
        assert not sock_path.exists()


# --- Windows loopback ingress: the token is the access boundary ---------------


@windows_only
@pytest.mark.asyncio
async def test_tcp_ingress_rejects_a_wrong_token_and_keeps_serving():
    """A connection that does not present the secret must be dropped without its
    payload being delivered, and must not take the server down with it."""
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()
        port = json.loads(sock_path.read_text(encoding="utf-8"))["port"]

        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"not-the-token\n")
        writer.write(json.dumps({"event": "add", "session_id": "evil"}).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)

        assert received == []

        # The legitimate client is unaffected.
        await _send_raw(sock_path,
                        json.dumps({"event": "dismiss", "session_id": "s1"}).encode())
        await asyncio.sleep(0.05)
        assert [r["session_id"] for r in received] == ["s1"]

        await server.stop()


@windows_only
@pytest.mark.asyncio
async def test_tcp_ingress_survives_an_oversized_first_line():
    """A client that floods the token line without ever sending a newline must be
    cut off, not allowed to buffer without bound or wedge the server."""
    received: list[dict] = []

    async def on_message(msg: dict) -> None:
        received.append(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()
        port = json.loads(sock_path.read_text(encoding="utf-8"))["port"]

        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"A" * (MAX_LINE_BYTES + 4096))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.1)

        await _send_raw(sock_path,
                        json.dumps({"event": "dismiss", "session_id": "s1"}).encode())
        await asyncio.sleep(0.05)
        assert [r["session_id"] for r in received] == ["s1"]

        await server.stop()


@windows_only
@pytest.mark.asyncio
async def test_tcp_ingress_binds_loopback_only():
    """The listener must never be reachable from off the machine."""
    async def on_message(msg: dict) -> None:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()
        try:
            hosts = {s.getsockname()[0] for s in server._server.sockets}
            assert hosts == {"127.0.0.1"}
        finally:
            await server.stop()


@windows_only
@pytest.mark.asyncio
async def test_tcp_ingress_token_is_fresh_per_start():
    """A token recovered from an earlier run must not open the next one."""
    async def on_message(msg: dict) -> None:
        pass

    tokens = []
    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        for _ in range(2):
            server = SocketServer(on_message=on_message, socket_path=sock_path)
            await server.start()
            tokens.append(json.loads(sock_path.read_text(encoding="utf-8"))["token"])
            await server.stop()

    assert len(tokens[0]) >= 32
    assert tokens[0] != tokens[1]


@windows_only
@pytest.mark.asyncio
async def test_tcp_ingress_endpoint_file_is_readable_only_by_this_user():
    """The endpoint file holds the secret, so its ACL is the boundary the Unix
    socket gets from its 0600 mode. Nothing may be inherited into it."""
    async def on_message(msg: dict) -> None:
        pass

    with tempfile.TemporaryDirectory() as tmpdir:
        sock_path = _ingress_path(tmpdir)
        server = SocketServer(on_message=on_message, socket_path=sock_path)
        await server.start()
        try:
            acl = subprocess.run(["icacls", str(sock_path)],
                                 capture_output=True, text=True, timeout=10).stdout
            # One line per ACE, each "PRINCIPAL:(rights)"; the file name shares
            # the first. An inherited ACE is tagged "(I)" and there must be none.
            aces = [ln for ln in acl.splitlines() if ":(" in ln]
            assert len(aces) == 1, f"expected a single ACE, got:\n{acl}"
            assert "(I)" not in aces[0], f"inherited access survived:\n{acl}"
        finally:
            await server.stop()
