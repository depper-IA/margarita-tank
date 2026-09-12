"""Exclusive, non-blocking single-instance lock on a file.

POSIX uses fcntl.flock; Windows uses msvcrt.locking. Both are held for the
lifetime of the returned descriptor and are released by the OS when the
process exits, so a crashed daemon never leaves the lock stuck.
"""

import os
import sys

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Windows locks a byte range rather than the whole file; one byte at offset 0
# is enough as long as every instance agrees on the range.
_WINDOWS_LOCK_BYTES = 1


def _try_lock(fd: int) -> None:
    """Take an exclusive, non-blocking lock on fd. Raises OSError if held."""
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, _WINDOWS_LOCK_BYTES)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire(path) -> int:
    """Open path and take the lock, returning the open file descriptor.

    Raises OSError if another process already holds it. Close the descriptor
    to release the lock.
    """
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _try_lock(fd)
    except OSError:
        os.close(fd)
        raise
    return fd
