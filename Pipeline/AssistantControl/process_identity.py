"""Windows host-process identity without trusting a recycled PID.

An inaccessible process is unknown, not dead. Explicit termination checks a
held process handle and makes no claim about Docker children.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def identify(pid: int) -> dict | None:
    if type(pid) is not int or pid <= 0:
        raise ValueError("A positive process ID is required")
    if os.name != "nt":
        raise NotImplementedError("Host identity currently supports Windows only")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # No such PID.
            return None
        raise ctypes.WinError(error)
    try:
        wait = kernel.WaitForSingleObject(handle, 0)
        if wait == 0:
            return None
        if wait != 258:  # WAIT_TIMEOUT means the process is still running.
            raise ctypes.WinError(ctypes.get_last_error())
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        image = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(image))
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return {"pid": pid, "created_ticks": created, "image": image.value.casefold()}
    finally:
        kernel.CloseHandle(handle)


def matches(identity: dict) -> bool:
    if (not isinstance(identity, dict) or type(identity.get("pid")) is not int
            or type(identity.get("created_ticks")) is not int
            or not isinstance(identity.get("image"), str)):
        raise ValueError("Incomplete process identity")
    current = identify(identity["pid"])
    return current is not None and current == identity


def terminate(identity: dict) -> bool:
    """Terminate only the identified host; never use a bare PID kill command."""
    if not matches(identity):
        if identify(identity["pid"]) is None:
            return True
        raise ValueError("Process identity changed; no process terminated")
    if identity["pid"] == os.getpid():
        raise ValueError("Refusing to terminate the controlling process")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    handle = kernel.OpenProcess(0x1000 | 0x100000 | 1, False, identity["pid"])
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return True
        raise ctypes.WinError(error)
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        if created != identity["created_ticks"]:
            raise ValueError("Process identity changed; no process terminated")
        if kernel.WaitForSingleObject(handle, 0) == 0:
            return True
        if not kernel.TerminateProcess(handle, 130):
            raise ctypes.WinError(ctypes.get_last_error())
        if kernel.WaitForSingleObject(handle, 10000) != 0:
            raise RuntimeError("Host termination is not yet confirmed")
        return True
    finally:
        kernel.CloseHandle(handle)
