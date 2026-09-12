"""Portable process liveness and termination.

POSIX uses os.kill. Windows has no signals, so liveness goes through
kernel32 via ctypes — deliberately not psutil, because the standalone
clawd-tank-notify hook script is stdlib-only and mirrors this logic.

`os.kill(pid, 0)` is not a usable probe on Windows: it raises nothing for a
process that has already exited, and raises a bare OSError (WinError 87)
for a PID that never existed.
"""

import os
import signal
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_TERMINATE = 0x0001
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5
    _ERROR_INVALID_PARAMETER = 87

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Declared explicitly: without an argtypes/restype declaration ctypes
    # truncates the returned HANDLE to a C int on 64-bit.
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, wintypes.LPDWORD)
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    def _open_error(pid: int) -> OSError:
        """Translate an OpenProcess failure into the POSIX exception callers expect."""
        err = ctypes.get_last_error()
        if err == _ERROR_INVALID_PARAMETER:
            return ProcessLookupError(f"No such process: {pid}")
        if err == _ERROR_ACCESS_DENIED:
            return PermissionError(f"Access denied for process: {pid}")
        return ctypes.WinError(err)


def pid_alive(pid: int) -> bool:
    """True if pid names a running process.

    A PID owned by another user counts as alive — it exists, we just cannot
    signal it.
    """
    if sys.platform == "win32":
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            # A handle to an exited process still opens, so the exit code is
            # the only thing that actually answers the question.
            code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_pid(pid: int) -> None:
    """Ask pid to stop.

    POSIX sends SIGTERM, so the target can shut down gracefully. Windows has
    no SIGTERM: this calls TerminateProcess, which is unconditional, so the
    target's shutdown handler never runs. Graceful shutdown on Windows needs
    an IPC stop request instead.

    Raises ProcessLookupError if pid is gone and PermissionError if it belongs
    to someone else, matching os.kill on both platforms.
    """
    if sys.platform == "win32":
        handle = _kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
        if not handle:
            raise _open_error(pid)
        try:
            if not _kernel32.TerminateProcess(handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.CloseHandle(handle)
        return
    os.kill(pid, signal.SIGTERM)
