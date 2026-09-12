"""Small named Windows Job Object wrapper for assistant-owned worker trees.

The implementation follows the Win32 Job Objects contract documented at
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects:
assigned children remain in the job unless breakaway is enabled, and a job
survives closing its last handle until assigned processes have exited. This
module deliberately omits ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and all
breakaway flags. It never discovers or terminates arbitrary processes.
"""
from __future__ import annotations

import ctypes
import os
import re
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Mapping


ERROR_ALREADY_EXISTS = 183
ERROR_FILE_NOT_FOUND = 2
ERROR_INVALID_NAME = 123
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102
JobObjectBasicAccountingInformation = 1

_NAME = re.compile(r"^assistant-job-(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})$")


class WindowsJobError(RuntimeError):
    """A named assistant Job Object operation failed."""


def _require_windows() -> None:
    if os.name != "nt":
        raise NotImplementedError("Windows Job Objects are available only on Windows")


def _name(name: str) -> str:
    if type(name) is not str or not _NAME.fullmatch(name):
        raise ValueError("job name must be an assistant-job- UUID or hash name")
    return name


def _kernel32() -> Any:
    _require_windows()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _win_error(message: str) -> WindowsJobError:
    error = ctypes.get_last_error()
    return WindowsJobError(f"{message} (WinError {error})")


def _identity_from_handle(kernel: Any, handle: Any, pid: int) -> dict[str, Any]:
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise _win_error("GetProcessTimes failed")
    image = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(image))
    if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
        raise _win_error("QueryFullProcessImageNameW failed")
    created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    return {"pid": pid, "created_ticks": created, "image": image.value.casefold()}


def _open_verified_child(identity: Mapping[str, Any]) -> Any:
    if (not isinstance(identity, Mapping) or type(identity.get("pid")) is not int
            or identity["pid"] <= 0 or type(identity.get("created_ticks")) is not int
            or not isinstance(identity.get("image"), str) or not identity["image"]):
        raise ValueError("child identity must contain pid, created_ticks, and image")
    kernel = _kernel32()
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    access = PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA | PROCESS_TERMINATE
    handle = kernel.OpenProcess(access, False, identity["pid"])
    if not handle:
        raise _win_error("OpenProcess failed")
    try:
        if kernel.WaitForSingleObject(handle, 0) == WAIT_OBJECT_0:
            raise WindowsJobError("child process exited before Job Object assignment")
        observed = _identity_from_handle(kernel, handle, identity["pid"])
        expected = {
            "pid": identity["pid"], "created_ticks": identity["created_ticks"],
            "image": identity["image"].casefold(),
        }
        if observed != expected:
            raise WindowsJobError("child identity changed before Job Object assignment")
        return handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


@dataclass
class WindowsJob:
    """An owned handle to a named Job Object; close does not kill its members."""

    name: str
    _handle: Any

    def close(self) -> None:
        if self._handle:
            kernel = _kernel32()
            kernel.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "WindowsJob":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def create_and_assign(name: str, exact_child_identity: Mapping[str, Any]) -> WindowsJob:
    """Create a fresh assistant Job Object and assign exactly one held child."""
    _require_windows()
    name = _name(name)
    kernel = _kernel32()
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, name)
    error = ctypes.get_last_error()
    if not job:
        raise _win_error("CreateJobObjectW failed")
    if error == ERROR_ALREADY_EXISTS:
        kernel.CloseHandle(job)
        raise WindowsJobError("assistant Job Object name already exists")
    child = None
    try:
        child = _open_verified_child(exact_child_identity)
        if not kernel.AssignProcessToJobObject(job, child):
            raise _win_error("AssignProcessToJobObject failed")
    except BaseException:
        kernel.CloseHandle(job)
        raise
    finally:
        if child:
            kernel.CloseHandle(child)
    return WindowsJob(name, job)


class _BasicAccounting(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


def _open_job(name: str, access: int) -> Any | None:
    _name(name)
    kernel = _kernel32()
    kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenJobObjectW.restype = wintypes.HANDLE
    handle = kernel.OpenJobObjectW(access, False, name)
    if handle:
        return handle
    error = ctypes.get_last_error()
    if error in (ERROR_FILE_NOT_FOUND, ERROR_INVALID_NAME):
        return None
    raise _win_error("OpenJobObjectW failed")


def open_named(name: str) -> "WindowsJob":
    """Open and retain an assistant job handle for a contained child."""
    _require_windows()
    handle = _open_job(name, JOB_OBJECT_QUERY)
    if handle is None:
        raise WindowsJobError("assistant Job Object disappeared before child handoff")
    return WindowsJob(name, handle)


def is_assigned(name: str, exact_identity: Mapping[str, Any]) -> bool:
    """Check one exact held process against the named job; never assign it.

    A missing job returns False. An invalid or changed process identity raises,
    including when the job is missing.
    """
    _require_windows()
    _name(name)
    kernel = _kernel32()
    child = _open_verified_child(exact_identity)
    job = None
    try:
        job = _open_job(name, JOB_OBJECT_QUERY)
        if job is None:
            return False
        kernel.IsProcessInJob.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        kernel.IsProcessInJob.restype = wintypes.BOOL
        assigned = wintypes.BOOL()
        if not kernel.IsProcessInJob(child, job, ctypes.byref(assigned)):
            raise _win_error("IsProcessInJob failed")
        return bool(assigned.value)
    finally:
        if job is not None:
            kernel.CloseHandle(job)
        kernel.CloseHandle(child)


def active_count(name: str) -> int:
    """Return active assigned process count; a missing job is reported as zero."""
    kernel = _kernel32()
    handle = _open_job(name, JOB_OBJECT_QUERY)
    if handle is None:
        return 0
    try:
        kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        info = _BasicAccounting()
        returned = wintypes.DWORD()
        if not kernel.QueryInformationJobObject(
                handle, JobObjectBasicAccountingInformation, ctypes.byref(info),
                ctypes.sizeof(info), ctypes.byref(returned)):
            raise _win_error("QueryInformationJobObject failed")
        return int(info.ActiveProcesses)
    finally:
        kernel.CloseHandle(handle)


def terminate_job(name: str, *, timeout_seconds: float = 10.0,
                  poll_interval: float = 0.05) -> bool:
    """Terminate all members of the named assistant job and bounded-wait for zero."""
    if timeout_seconds <= 0 or poll_interval <= 0:
        raise ValueError("termination timeout and poll interval must be positive")
    kernel = _kernel32()
    handle = _open_job(name, JOB_OBJECT_TERMINATE | JOB_OBJECT_QUERY)
    if handle is None:
        return True
    try:
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        if not kernel.TerminateJobObject(handle, 137):
            raise _win_error("TerminateJobObject failed")
        deadline = time.monotonic() + timeout_seconds
        while active_count(name) != 0:
            if time.monotonic() >= deadline:
                raise TimeoutError("Job Object members did not reach zero before timeout")
            time.sleep(poll_interval)
        return True
    finally:
        kernel.CloseHandle(handle)


__all__ = ["WindowsJob", "WindowsJobError", "active_count", "create_and_assign", "is_assigned", "open_named", "terminate_job"]
