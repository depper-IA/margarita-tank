"""Restrict a file so that only the user who created it can read it.

POSIX expresses this as a 0600 mode. Windows has no mode bits — os.chmod there
only toggles the read-only attribute — so the equivalent is an explicit DACL
carrying a single ACE for the process token's own user, marked protected so
nothing is inherited from the parent directory.

Done through ctypes rather than pywin32: the host daemon ships without
third-party Windows dependencies, matching process_utils.py.
"""

import os
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _TOKEN_QUERY = 0x0008
    _TOKEN_USER = 1  # TOKEN_INFORMATION_CLASS.TokenUser
    _SDDL_REVISION_1 = 1
    _SE_FILE_OBJECT = 1
    _DACL_SECURITY_INFORMATION = 0x00000004
    _PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    # Declared explicitly: without argtypes/restype ctypes truncates handles and
    # pointers to a C int on 64-bit.
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
    _kernel32.LocalFree.restype = ctypes.c_void_p

    _advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD))
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG))
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    _advapi32.GetSecurityDescriptorDacl.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL))
    _advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
    _advapi32.SetNamedSecurityInfoW.argtypes = (
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    _advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

    class _TOKEN_USER_INFO(ctypes.Structure):
        """SID_AND_ATTRIBUTES, the whole of the TokenUser information class."""
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    def current_user_sid() -> str:
        """SDDL string form (S-1-5-...) of the process token's user SID."""
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            size = wintypes.DWORD()
            # First call fails with ERROR_INSUFFICIENT_BUFFER and reports the size.
            _advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0,
                                          ctypes.byref(size))
            buf = ctypes.create_string_buffer(size.value)
            if not _advapi32.GetTokenInformation(token, _TOKEN_USER, buf,
                                                 size.value, ctypes.byref(size)):
                raise ctypes.WinError(ctypes.get_last_error())
            sid = ctypes.cast(buf, ctypes.POINTER(_TOKEN_USER_INFO)).contents.Sid
            text = wintypes.LPWSTR()
            if not _advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                return text.value
            finally:
                _kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        finally:
            _kernel32.CloseHandle(token)

    def _restrict_windows(path) -> None:
        # "D:P" is a protected DACL: whatever %USERPROFILE% would hand down is
        # discarded, so the single "(A;;FA;;;<sid>)" ACE — full access for this
        # user and no one else — is the entire access list.
        sddl = f"D:P(A;;FA;;;{current_user_sid()})"
        descriptor = ctypes.c_void_p()
        if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, _SDDL_REVISION_1, ctypes.byref(descriptor), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            present = wintypes.BOOL()
            dacl = ctypes.c_void_p()
            defaulted = wintypes.BOOL()
            if not _advapi32.GetSecurityDescriptorDacl(
                descriptor, ctypes.byref(present), ctypes.byref(dacl),
                ctypes.byref(defaulted)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            # SetNamedSecurityInfoW returns a Win32 error code, not a BOOL.
            err = _advapi32.SetNamedSecurityInfoW(
                ctypes.create_unicode_buffer(str(path)),
                _SE_FILE_OBJECT,
                _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, dacl, None,
            )
            if err != 0:
                raise ctypes.WinError(err)
        finally:
            _kernel32.LocalFree(ctypes.cast(descriptor, ctypes.c_void_p))


def restrict_to_current_user(path) -> None:
    """Make path readable and writable only by the user running this process.

    Raises OSError if the restriction could not be applied. Callers must not
    swallow that: for a file holding a shared secret, the permissions are the
    access boundary, so failing to set them is failing to protect it.
    """
    if sys.platform == "win32":
        _restrict_windows(path)
        return
    os.chmod(path, 0o600)
