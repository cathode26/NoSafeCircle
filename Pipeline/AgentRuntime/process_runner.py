"""Small synchronous subprocess transport shared by live provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float

    def __post_init__(self) -> None:
        if (
            type(self.argv) is not tuple
            or not self.argv
            or type(self.argv[0]) is not str
            or not self.argv[0]
            or any(type(argument) is not str for argument in self.argv)
        ):
            raise ValueError(
                "argv must be a non-empty string tuple with a non-empty executable"
            )
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise ValueError("returncode must be an integer")
        if type(self.stdout) is not bytes or type(self.stderr) is not bytes:
            raise ValueError("stdout and stderr must be exact bytes")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("elapsed_seconds must be finite and non-negative")


class ProcessTimeoutError(TimeoutError):
    """Raised after a timed-out process group has undergone bounded cleanup."""

    def __init__(self, result: ProcessResult) -> None:
        super().__init__("subprocess exceeded its external timeout")
        self.result = result


class ProcessRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        ...


class StandardProcessRunner:
    """Run one argv directly and supervise its newly created process group."""

    def __init__(self, *, cleanup_timeout_seconds: float = 1.0) -> None:
        if (
            isinstance(cleanup_timeout_seconds, bool)
            or not isinstance(cleanup_timeout_seconds, (int, float))
            or not math.isfinite(cleanup_timeout_seconds)
            or cleanup_timeout_seconds <= 0
        ):
            raise ValueError("cleanup_timeout_seconds must be finite and positive")
        self._cleanup_timeout_seconds = float(cleanup_timeout_seconds)

    def run(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        arguments = tuple(argv)
        if (
            not arguments
            or type(arguments[0]) is not str
            or not arguments[0]
            or any(type(argument) is not str for argument in arguments)
        ):
            raise ValueError(
                "argv must contain strings and a non-empty executable"
            )
        if type(stdin) is not bytes:
            raise TypeError("stdin must be exact bytes")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")

        process_options: dict[str, object] = {}
        if os.name == "nt":
            process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            process_options["start_new_session"] = True

        started = time.monotonic()
        process = subprocess.Popen(
            arguments,
            cwd=os.fspath(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **process_options,
        )
        group_id = process.pid
        try:
            try:
                stdout, stderr = process.communicate(
                    input=stdin,
                    timeout=float(timeout_seconds),
                )
            except subprocess.TimeoutExpired as first_timeout:
                stdout, stderr = self._terminate_after_timeout(
                    process,
                    group_id,
                    first_timeout,
                )
                timed_out = True
            else:
                timed_out = False
                self._cleanup_after_success(process, group_id)
        except BaseException:
            self._cleanup_after_exception(process, group_id)
            raise

        if timed_out:
            result = ProcessResult(
                arguments,
                process.returncode if process.returncode is not None else -1,
                stdout,
                stderr,
                time.monotonic() - started,
            )
            raise ProcessTimeoutError(result) from None

        return ProcessResult(
            arguments,
            process.returncode,
            stdout,
            stderr,
            time.monotonic() - started,
        )

    def _terminate_after_timeout(
        self,
        process: subprocess.Popen[bytes],
        group_id: int,
        initial: subprocess.TimeoutExpired,
    ) -> tuple[bytes, bytes]:
        stdout = _timeout_bytes(initial.output)
        stderr = _timeout_bytes(initial.stderr)
        self._signal_group(process, group_id, force=False)
        try:
            later_stdout, later_stderr = process.communicate(
                timeout=self._cleanup_timeout_seconds
            )
            stdout, stderr = _prefer_output(
                stdout,
                stderr,
                later_stdout,
                later_stderr,
            )
        except subprocess.TimeoutExpired as terminated:
            stdout, stderr = _prefer_partial(stdout, stderr, terminated)
        except Exception:
            pass

        # A root may exit and close its pipes while a detached descendant remains.
        # The original group ID remains the cleanup authority on POSIX, so never
        # make this final signal conditional on the root's poll/communicate state.
        self._signal_group(process, group_id, force=True)
        try:
            later_stdout, later_stderr = process.communicate(
                timeout=self._cleanup_timeout_seconds
            )
            stdout, stderr = _prefer_output(
                stdout,
                stderr,
                later_stdout,
                later_stderr,
            )
        except subprocess.TimeoutExpired as killed:
            stdout, stderr = _prefer_partial(stdout, stderr, killed)
        except Exception:
            pass
        finally:
            self._close_and_reap(process)
        return stdout, stderr

    def _cleanup_after_success(
        self,
        process: subprocess.Popen[bytes],
        group_id: int,
    ) -> None:
        """Ensure a successful root cannot leave same-group descendants running."""

        # communicate() proves only that the root exited and its captured pipes
        # reached EOF. A background descendant can detach those pipes and remain
        # in the original process group, so bounded invocations finish by forcing
        # that group down even after a zero exit.
        self._signal_group(process, group_id, force=True)
        self._close_and_reap(process)

    def _cleanup_after_exception(
        self,
        process: subprocess.Popen[bytes],
        group_id: int,
    ) -> None:
        """Best-effort cleanup whose failures cannot replace an active exception."""

        try:
            self._signal_group(process, group_id, force=False)
        except BaseException:
            pass
        try:
            process.communicate(timeout=self._cleanup_timeout_seconds)
        except BaseException:
            pass
        try:
            self._signal_group(process, group_id, force=True)
        except BaseException:
            pass
        try:
            process.communicate(timeout=self._cleanup_timeout_seconds)
        except BaseException:
            pass
        try:
            self._close_and_reap(process)
        except BaseException:
            pass

    def _close_and_reap(self, process: subprocess.Popen[bytes]) -> None:
        for stream in (process.stdout, process.stderr, process.stdin):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
        try:
            process.wait(timeout=self._cleanup_timeout_seconds)
        except Exception:
            pass

    def _signal_group(
        self,
        process: subprocess.Popen[bytes],
        group_id: int,
        *,
        force: bool,
    ) -> None:
        try:
            if os.name == "nt":
                if force:
                    self._force_kill_windows_tree(group_id)
                    if process.poll() is None:
                        process.kill()
                elif process.poll() is None:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(group_id, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                if force:
                    process.kill()
                else:
                    process.terminate()
            except Exception:
                pass

    def _force_kill_windows_tree(self, process_id: int) -> None:
        try:
            subprocess.run(
                ("taskkill", "/PID", str(process_id), "/T", "/F"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=self._cleanup_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def _timeout_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if type(value) is bytes:
        return value
    return value.encode("utf-8", "replace")


def _prefer_partial(
    stdout: bytes,
    stderr: bytes,
    timeout: subprocess.TimeoutExpired,
) -> tuple[bytes, bytes]:
    later_stdout = _timeout_bytes(timeout.output)
    later_stderr = _timeout_bytes(timeout.stderr)
    return (
        later_stdout if len(later_stdout) >= len(stdout) else stdout,
        later_stderr if len(later_stderr) >= len(stderr) else stderr,
    )


def _prefer_output(
    stdout: bytes,
    stderr: bytes,
    later_stdout: bytes,
    later_stderr: bytes,
) -> tuple[bytes, bytes]:
    return (
        later_stdout if len(later_stdout) >= len(stdout) else stdout,
        later_stderr if len(later_stderr) >= len(stderr) else stderr,
    )
