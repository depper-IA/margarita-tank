"""Server that receives hook messages from clawd-tank-notify.

POSIX listens on a Unix socket, whose 0600 mode is what keeps other users out.

Windows asyncio has no Unix-socket support, so the ingress there is a loopback
TCP listener on an ephemeral port. A port is not an access boundary — any local
process can reach 127.0.0.1 — so the daemon mints a fresh shared secret at every
start and publishes it, with the port, in an endpoint file restricted to the
current user. A connection whose first line is not that secret is closed without
its payload ever being parsed. Both notify clients mirror this handshake.
"""

import asyncio
import hmac
import json
import logging
import os
import secrets
import sys
from pathlib import Path
from typing import Callable, Awaitable

from .file_security import restrict_to_current_user

logger = logging.getLogger("clawd-tank.socket")

CLAWD_DIR = Path.home() / ".clawd-tank"

# Where clawd-tank-notify looks for the daemon: the Unix socket itself on POSIX,
# the published port + token on Windows.
if sys.platform == "win32":
    SOCKET_PATH = CLAWD_DIR / "endpoint.json"
else:
    SOCKET_PATH = CLAWD_DIR / "sock"

# A hook message is a few hundred bytes. readline() raises ValueError once a
# line grows past this, so a client that never sends a newline cannot grow the
# read buffer without bound. Same value as asyncio's own default.
MAX_LINE_BYTES = 64 * 1024


class UnixSocketServer:
    """Listens on a Unix socket for JSON messages from clawd-tank-notify."""

    def __init__(self, on_message: Callable[[dict], Awaitable[None]],
                 socket_path: Path = SOCKET_PATH):
        self._on_message = on_message
        self._socket_path = socket_path
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self._socket_path)
        )
        # Make socket writable by owner
        os.chmod(self._socket_path, 0o600)
        logger.info("Listening on %s", self._socket_path)

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter) -> None:
        # Messages are newline-delimited JSON. readline() gives a clean
        # message boundary regardless of TCP/socket buffering.
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line:
                try:
                    msg = json.loads(line.decode("utf-8"))
                    await self._on_message(msg)
                except json.JSONDecodeError:
                    logger.error("Received malformed JSON: %r", line[:200])
        except TimeoutError:
            logger.warning("Timed out waiting for message from client")
        except Exception:
            logger.exception("Unexpected error handling socket message")
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._socket_path.exists():
            self._socket_path.unlink()


class TcpSocketServer:
    """Listens on a loopback TCP port for JSON messages from clawd-tank-notify.

    Used where there is no Unix socket to protect with a file mode. The port is
    ephemeral and bound to 127.0.0.1 only; the shared secret published alongside
    it in `socket_path` is what actually authorises a client, so that file — not
    the listener — is the access boundary.
    """

    def __init__(self, on_message: Callable[[dict], Awaitable[None]],
                 socket_path: Path = SOCKET_PATH):
        self._on_message = on_message
        self._socket_path = socket_path
        self._server: asyncio.Server | None = None
        self._token = b""

    async def start(self) -> None:
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        # Fresh per daemon start: a token leaked from an earlier run is useless.
        token = secrets.token_urlsafe(32)
        self._token = token.encode("ascii")

        # Port 0 asks the OS for a free ephemeral port; 127.0.0.1 keeps the
        # listener off every other interface.
        self._server = await asyncio.start_server(
            self._handle_client, host="127.0.0.1", port=0, limit=MAX_LINE_BYTES
        )
        port = self._server.sockets[0].getsockname()[1]
        _publish_endpoint(self._socket_path, port, token)
        logger.info("Listening on 127.0.0.1:%d (endpoint %s)", port, self._socket_path)

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        # Framing: the shared secret on the first line, then one line of JSON.
        # readline() gives a clean message boundary regardless of TCP buffering.
        try:
            offered = await asyncio.wait_for(reader.readline(), timeout=5.0)
            # compare_digest, not ==, so a wrong token cannot be recovered one
            # byte at a time from how long the comparison took.
            if not hmac.compare_digest(offered.strip(), self._token):
                logger.warning("Rejected connection from %s: invalid token",
                               writer.get_extra_info("peername"))
                return
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if line:
                try:
                    msg = json.loads(line.decode("utf-8"))
                    await self._on_message(msg)
                except json.JSONDecodeError:
                    logger.error("Received malformed JSON: %r", line[:200])
        except TimeoutError:
            logger.warning("Timed out waiting for message from client")
        except ValueError:
            # readline() raises ValueError once a line passes MAX_LINE_BYTES.
            # Dropping the connection is the whole response: a client that never
            # sends a newline must not be allowed to buffer indefinitely.
            logger.warning("Rejected connection: line exceeded %d bytes",
                           MAX_LINE_BYTES)
        except Exception:
            logger.exception("Unexpected error handling socket message")
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        # The token dies with the endpoint file; nothing can connect afterwards.
        self._socket_path.unlink(missing_ok=True)


def _publish_endpoint(path: Path, port: int, token: str) -> None:
    """Write the port and token where clawd-tank-notify can find them.

    Built under a temporary name so the permissions are locked down before the
    token is ever written to disk, then moved into place — os.replace is atomic,
    so a notify client never reads a half-written endpoint.
    """
    tmp = path.with_name(path.name + ".new")
    tmp.unlink(missing_ok=True)
    # O_EXCL so this fails rather than adopting a file someone else created
    # (and therefore owns the permissions of).
    os.close(os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    restrict_to_current_user(tmp)
    tmp.write_text(json.dumps({"port": port, "token": token}), encoding="utf-8")
    os.replace(tmp, path)


# Same constructor, same on_message contract, same start()/stop() lifecycle —
# daemon.py does not care which transport it got.
SocketServer = TcpSocketServer if sys.platform == "win32" else UnixSocketServer
