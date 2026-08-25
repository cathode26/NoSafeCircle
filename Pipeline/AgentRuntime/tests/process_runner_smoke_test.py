#!/usr/bin/env python3
"""Real subprocess smoke tests for the bounded standard process transport."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "Pipeline/AgentRuntime"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.process_runner import (
    ProcessTimeoutError,
    StandardProcessRunner,
)


def tree_hashes(path: Path) -> dict[str, str]:
    return {
        candidate.relative_to(path).as_posix(): hashlib.sha256(
            candidate.read_bytes()
        ).hexdigest()
        for candidate in path.rglob("*")
        if candidate.is_file()
    }


def rejects(callable_: Any, exception: type[BaseException]) -> BaseException:
    try:
        callable_()
    except exception as exc:
        return exc
    raise AssertionError(f"expected {exception.__name__}")


def process_is_running(pid: int) -> bool:
    if sys.platform.startswith("linux"):
        stat_path = Path(f"/proc/{pid}/stat")
        try:
            fields = stat_path.read_text("utf-8").split()
        except FileNotFoundError:
            return False
        if len(fields) >= 3 and fields[2] == "Z":
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until_stopped(pid: int, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not process_is_running(pid):
            return True
        time.sleep(0.02)
    return not process_is_running(pid)


def force_stop(pid: int) -> None:
    if not process_is_running(pid):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def test_real_success_capture_cwd_and_elapsed_time() -> None:
    code = (
        "import os,sys,time; "
        "data=sys.stdin.buffer.read(); time.sleep(0.05); "
        "sys.stdout.buffer.write(os.fsencode(os.getcwd())+b'\\0'+data); "
        "sys.stderr.buffer.write(b'exact stderr\\r\\n')"
    )
    stdin = b"exact stdin\x00with bytes\n"
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        argv = (sys.executable, "-S", "-c", code)
        result = StandardProcessRunner().run(
            argv,
            stdin=stdin,
            cwd=cwd,
            timeout_seconds=2,
        )
        assert result.argv == argv
        assert result.returncode == 0
        assert result.stdout == os.fsencode(cwd) + b"\0" + stdin
        assert result.stderr == b"exact stderr\r\n"
        assert 0.04 <= result.elapsed_seconds < 2
        assert list(cwd.iterdir()) == []


def test_shell_metacharacters_are_literal_argv() -> None:
    code = "import sys; sys.stdout.buffer.write(sys.argv[1].encode('utf-8'))"
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        marker = cwd / "shell-was-executed"
        dangerous = f"; touch {marker} && $(touch {marker}) | > {marker}"
        result = StandardProcessRunner().run(
            (sys.executable, "-S", "-c", code, dangerous),
            stdin=b"",
            cwd=cwd,
            timeout_seconds=2,
        )
        assert result.returncode == 0
        assert result.stdout.decode("utf-8") == dangerous
        assert result.stderr == b""
        assert not marker.exists()
        assert list(cwd.iterdir()) == []


def test_timeout_preserves_partial_output_and_terminates_process() -> None:
    code = (
        "import os,sys,time; "
        "sys.stdout.write(str(os.getpid())+'\\npartial stdout\\n'); "
        "sys.stdout.flush(); "
        "sys.stderr.write('partial stderr\\n'); sys.stderr.flush(); "
        "time.sleep(30)"
    )
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        runner = StandardProcessRunner(cleanup_timeout_seconds=0.3)
        started = time.monotonic()
        exception = rejects(
            lambda: runner.run(
                (sys.executable, "-S", "-c", code),
                stdin=b"",
                cwd=cwd,
                timeout_seconds=0.2,
            ),
            ProcessTimeoutError,
        )
        elapsed = time.monotonic() - started
        result = exception.result
        pid = int(result.stdout.splitlines()[0])
        try:
            assert result.stdout == f"{pid}\npartial stdout\n".encode("ascii")
            assert result.stderr == b"partial stderr\n"
            assert isinstance(result.returncode, int)
            assert 0.18 <= result.elapsed_seconds <= elapsed
            assert elapsed < 2
            assert wait_until_stopped(pid)
            assert list(cwd.iterdir()) == []
        finally:
            force_stop(pid)


def test_posix_timeout_terminates_same_group_descendant() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    descendant_code = "import time; time.sleep(30)"
    parent_code = (
        "import json,os,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-S','-c',sys.argv[1]]); "
        "print(json.dumps({'parent':os.getpid(),'descendant':child.pid,"
        "'parent_group':os.getpgrp(),'descendant_group':os.getpgid(child.pid)}),"
        "flush=True); time.sleep(30)"
    )
    parent_pid = 0
    descendant_pid = 0
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        runner = StandardProcessRunner(cleanup_timeout_seconds=0.3)
        exception = rejects(
            lambda: runner.run(
                (sys.executable, "-S", "-c", parent_code, descendant_code),
                stdin=b"",
                cwd=cwd,
                timeout_seconds=0.3,
            ),
            ProcessTimeoutError,
        )
        metadata = json.loads(exception.result.stdout.decode("utf-8"))
        parent_pid = metadata["parent"]
        descendant_pid = metadata["descendant"]
        try:
            assert metadata["parent_group"] == metadata["descendant_group"]
            assert wait_until_stopped(parent_pid)
            assert wait_until_stopped(descendant_pid)
            assert exception.result.elapsed_seconds < 2
            assert list(cwd.iterdir()) == []
        finally:
            force_stop(descendant_pid)
            force_stop(parent_pid)


def test_posix_keyboard_interrupt_cleans_up_launched_child() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    child_pid = 0
    interruption = KeyboardInterrupt("supervision interrupted")
    code = (
        "import os,signal,sys,time; "
        "path=sys.argv[1]; "
        "stream=open(path,'w',encoding='ascii'); "
        "stream.write(str(os.getpid())); stream.flush(); stream.close(); "
        "time.sleep(0.1); os.kill(os.getppid(),signal.SIGINT); time.sleep(30)"
    )

    def raise_interruption(signum: int, frame: Any) -> None:
        raise interruption

    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        pid_path = cwd / "child.pid"
        previous_handler = signal.signal(signal.SIGINT, raise_interruption)
        started = time.monotonic()
        try:
            exception = rejects(
                lambda: StandardProcessRunner(cleanup_timeout_seconds=0.3).run(
                    (sys.executable, "-S", "-c", code, os.fspath(pid_path)),
                    stdin=b"",
                    cwd=cwd,
                    timeout_seconds=3,
                ),
                KeyboardInterrupt,
            )
            assert exception is interruption
            child_pid = int(pid_path.read_text("ascii"))
            assert wait_until_stopped(child_pid)
            assert time.monotonic() - started < 2
        finally:
            signal.signal(signal.SIGINT, previous_handler)
            if child_pid == 0 and pid_path.exists():
                child_pid = int(pid_path.read_text("ascii"))
            if child_pid:
                force_stop(child_pid)


def test_posix_timeout_hard_kills_sigterm_ignoring_descendant() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    descendant_code = "\n".join(
        (
            "import os, signal, sys, time",
            "ready_path, term_path = sys.argv[1:3]",
            "def on_term(signum, frame):",
            "    with open(term_path, 'w', encoding='ascii') as stream:",
            "        stream.write('descendant received SIGTERM\\n')",
            "signal.signal(signal.SIGTERM, on_term)",
            "with open(ready_path, 'w', encoding='ascii') as stream:",
            "    stream.write(str(os.getpid()))",
            "while True:",
            "    time.sleep(30)",
        )
    )
    parent_code = "\n".join(
        (
            "import json, os, signal, subprocess, sys, time",
            "child_code, ready_path, term_path = sys.argv[1:4]",
            "child = subprocess.Popen(",
            "    [sys.executable, '-S', '-c', child_code, ready_path, term_path],",
            "    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,",
            "    stderr=subprocess.DEVNULL, close_fds=True)",
            "deadline = time.monotonic() + 2",
            "while not os.path.exists(ready_path):",
            "    if time.monotonic() >= deadline:",
            "        raise RuntimeError('descendant did not become ready')",
            "    time.sleep(0.01)",
            "def on_term(signum, frame):",
            "    deadline = time.monotonic() + 0.25",
            "    while not os.path.exists(term_path) and time.monotonic() < deadline:",
            "        time.sleep(0.005)",
            "    os._exit(0)",
            "signal.signal(signal.SIGTERM, on_term)",
            "print(json.dumps({'parent': os.getpid(), 'descendant': child.pid,",
            "    'parent_group': os.getpgrp(),",
            "    'descendant_group': os.getpgid(child.pid)}), flush=True)",
            "time.sleep(30)",
        )
    )
    parent_pid = 0
    descendant_pid = 0
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        ready_path = cwd / "descendant.ready"
        term_path = cwd / "descendant.term"
        try:
            exception = rejects(
                lambda: StandardProcessRunner(cleanup_timeout_seconds=0.5).run(
                    (
                        sys.executable,
                        "-S",
                        "-c",
                        parent_code,
                        descendant_code,
                        os.fspath(ready_path),
                        os.fspath(term_path),
                    ),
                    stdin=b"",
                    cwd=cwd,
                    timeout_seconds=0.5,
                ),
                ProcessTimeoutError,
            )
            metadata = json.loads(exception.result.stdout.decode("utf-8"))
            parent_pid = metadata["parent"]
            descendant_pid = metadata["descendant"]
            assert metadata["parent_group"] == metadata["descendant_group"]
            assert term_path.read_text("ascii") == "descendant received SIGTERM\n"
            assert wait_until_stopped(parent_pid)
            assert wait_until_stopped(descendant_pid)
            assert exception.result.elapsed_seconds < 2
        finally:
            if ready_path.exists() and descendant_pid == 0:
                descendant_pid = int(ready_path.read_text("ascii"))
            if descendant_pid:
                force_stop(descendant_pid)
            if parent_pid:
                force_stop(parent_pid)


def test_observed_streaming_happens_before_completion_and_matches_capture() -> None:
    code = (
        "import sys,time; "
        "sys.stdout.buffer.write(b'chunk-one\\n'); sys.stdout.buffer.flush(); "
        "time.sleep(0.25); "
        "sys.stdout.buffer.write(b'chunk-two\\n'); sys.stdout.buffer.flush(); "
        "time.sleep(0.05)"
    )
    observed: list[tuple[float, bytes]] = []
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        runner = StandardProcessRunner()
        started = time.monotonic()

        def observer(chunk: bytes) -> None:
            observed.append((time.monotonic() - started, chunk))

        result = runner.run(
            (sys.executable, "-S", "-c", code),
            stdin=b"",
            cwd=cwd,
            timeout_seconds=5,
            stdout_observer=observer,
        )
        assert result.argv == (sys.executable, "-S", "-c", code)
        assert result.returncode == 0
        assert result.stdout == b"chunk-one\nchunk-two\n"
        assert observed
        assert b"".join(chunk for _, chunk in observed) == result.stdout
        # The first observed chunk must arrive well before the process's total
        # elapsed time, proving delivery is live rather than buffered until exit.
        first_seen_seconds = observed[0][0]
        assert first_seen_seconds < result.elapsed_seconds - 0.1
        assert list(cwd.iterdir()) == []


def test_observed_stdout_delivery_is_synchronized_with_observer_acknowledgement() -> None:
    """Deterministic proof that small stdout chunks reach the observer while
    the child is still running, rather than only once buffered/EOF-flushed.

    The child writes and flushes one small chunk, then polls for a sentinel
    file within a bounded window; only the observer callback creates that
    sentinel, and only upon actually receiving the chunk. The child's final
    line records whether the sentinel appeared in time, so the assertion on
    that line's exact content -- not on wall-clock timing -- is what fails
    deterministically under a blocking ``read(65536)`` transport (the
    sentinel would only appear once the reader thread unblocks, by which
    point the child has already given up) and passes under a promptly
    delivering transport such as ``read1``/``os.read``.
    """
    code = "\n".join(
        (
            "import os, sys, time",
            "sentinel_path = sys.argv[1]",
            "sys.stdout.buffer.write(b'ping\\n')",
            "sys.stdout.buffer.flush()",
            "deadline = time.monotonic() + 3.0",
            "found = False",
            "while time.monotonic() < deadline:",
            "    if os.path.exists(sentinel_path):",
            "        found = True",
            "        break",
            "    time.sleep(0.005)",
            "sys.stdout.buffer.write(b'ack-seen\\n' if found else b'ack-missing\\n')",
            "sys.stdout.buffer.flush()",
        )
    )
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        sentinel = cwd / "observer.ack"
        observed: list[bytes] = []

        def observer(chunk: bytes) -> None:
            observed.append(chunk)
            if b"ping" in chunk and not sentinel.exists():
                sentinel.write_bytes(b"ack")

        result = StandardProcessRunner().run(
            (sys.executable, "-S", "-c", code, os.fspath(sentinel)),
            stdin=b"",
            cwd=cwd,
            timeout_seconds=5,
            stdout_observer=observer,
        )
        assert result.returncode == 0
        # Only reachable if the observer's sentinel was visible to the child
        # before its own bounded wait elapsed, i.e. observation happened
        # while the process was still running, not after it completed.
        assert result.stdout == b"ping\nack-seen\n"
        assert b"".join(observed) == result.stdout


def test_observed_stdout_exact_ordered_and_stderr_drained_for_large_output() -> None:
    code = (
        "import sys; "
        "sys.stdout.buffer.write(b'A'*70000); "
        "sys.stdout.buffer.write(b'B'*70000); "
        "sys.stderr.buffer.write(b'stderr-exact\\n')"
    )
    observed: list[bytes] = []
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        result = StandardProcessRunner().run(
            (sys.executable, "-S", "-c", code),
            stdin=b"",
            cwd=cwd,
            timeout_seconds=5,
            stdout_observer=observed.append,
        )
        assert result.returncode == 0
        assert result.stdout == b"A" * 70000 + b"B" * 70000
        assert b"".join(observed) == result.stdout
        # More than one 65536-byte read must have occurred for this input size.
        assert len(observed) >= 2
        assert result.stderr == b"stderr-exact\n"
        assert list(cwd.iterdir()) == []


def test_observed_non_observed_paths_return_identical_results() -> None:
    code = (
        "import sys; "
        "sys.stdout.buffer.write(b'identical stdout'); "
        "sys.stderr.buffer.write(b'identical stderr')"
    )
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        argv = (sys.executable, "-S", "-c", code)
        unobserved = StandardProcessRunner().run(
            argv, stdin=b"", cwd=cwd, timeout_seconds=5
        )
        observed_chunks: list[bytes] = []
        observed = StandardProcessRunner().run(
            argv,
            stdin=b"",
            cwd=cwd,
            timeout_seconds=5,
            stdout_observer=observed_chunks.append,
        )
        assert unobserved.stdout == observed.stdout == b"identical stdout"
        assert unobserved.stderr == observed.stderr == b"identical stderr"
        assert unobserved.returncode == observed.returncode == 0
        assert b"".join(observed_chunks) == observed.stdout
        assert list(cwd.iterdir()) == []


def test_observed_raising_observer_never_corrupts_capture_or_propagates() -> None:
    code = "import sys; sys.stdout.buffer.write(b'exact output regardless of observer')"

    def raising_observer(_: bytes) -> None:
        raise RuntimeError("presentation failure must never affect provider truth")

    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        result = StandardProcessRunner().run(
            (sys.executable, "-S", "-c", code),
            stdin=b"",
            cwd=cwd,
            timeout_seconds=5,
            stdout_observer=raising_observer,
        )
        assert result.returncode == 0
        assert result.stdout == b"exact output regardless of observer"
        assert list(cwd.iterdir()) == []


def test_observed_timeout_preserves_partial_output_and_kills_group() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    descendant_code = "import time; time.sleep(30)"
    parent_code = (
        "import json,os,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-S','-c',sys.argv[1]]); "
        "sys.stdout.write(json.dumps({'parent':os.getpid(),'descendant':child.pid,"
        "'parent_group':os.getpgrp(),'descendant_group':os.getpgid(child.pid)})+'\\n'); "
        "sys.stdout.flush(); time.sleep(30)"
    )
    observed: list[bytes] = []
    parent_pid = 0
    descendant_pid = 0
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        runner = StandardProcessRunner(cleanup_timeout_seconds=0.3)
        exception = rejects(
            lambda: runner.run(
                (sys.executable, "-S", "-c", parent_code, descendant_code),
                stdin=b"",
                cwd=cwd,
                timeout_seconds=0.3,
                stdout_observer=observed.append,
            ),
            ProcessTimeoutError,
        )
        result = exception.result
        assert b"".join(observed) == result.stdout
        metadata = json.loads(result.stdout.decode("utf-8"))
        parent_pid = metadata["parent"]
        descendant_pid = metadata["descendant"]
        try:
            assert metadata["parent_group"] == metadata["descendant_group"]
            assert wait_until_stopped(parent_pid)
            assert wait_until_stopped(descendant_pid)
            assert result.elapsed_seconds < 2
            assert list(cwd.iterdir()) == []
        finally:
            force_stop(descendant_pid)
            force_stop(parent_pid)


def test_posix_success_hard_kills_detached_same_group_descendant() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    descendant_code = "import time; time.sleep(30)"
    parent_code = (
        "import json,os,subprocess,sys; "
        "child=subprocess.Popen([sys.executable,'-S','-c',sys.argv[1]],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,close_fds=True); "
        "print(json.dumps({'parent':os.getpid(),'descendant':child.pid,"
        "'parent_group':os.getpgrp(),'descendant_group':os.getpgid(child.pid)}),"
        "flush=True)"
    )
    descendant_pid = 0
    with tempfile.TemporaryDirectory() as temporary:
        cwd = Path(temporary)
        try:
            result = StandardProcessRunner(cleanup_timeout_seconds=0.3).run(
                (sys.executable, "-S", "-c", parent_code, descendant_code),
                stdin=b"",
                cwd=cwd,
                timeout_seconds=3,
            )
            metadata = json.loads(result.stdout.decode("utf-8"))
            descendant_pid = metadata["descendant"]
            assert result.returncode == 0
            assert metadata["parent_group"] == metadata["descendant_group"]
            assert wait_until_stopped(descendant_pid)
            assert list(cwd.iterdir()) == []
        finally:
            if descendant_pid:
                force_stop(descendant_pid)

def main() -> None:
    before = tree_hashes(RUNTIME_ROOT)
    status_before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    test_real_success_capture_cwd_and_elapsed_time()
    test_shell_metacharacters_are_literal_argv()
    test_timeout_preserves_partial_output_and_terminates_process()
    test_posix_timeout_terminates_same_group_descendant()
    test_posix_keyboard_interrupt_cleans_up_launched_child()
    test_posix_timeout_hard_kills_sigterm_ignoring_descendant()
    test_posix_success_hard_kills_detached_same_group_descendant()
    test_observed_streaming_happens_before_completion_and_matches_capture()
    test_observed_stdout_delivery_is_synchronized_with_observer_acknowledgement()
    test_observed_stdout_exact_ordered_and_stderr_drained_for_large_output()
    test_observed_non_observed_paths_return_identical_results()
    test_observed_raising_observer_never_corrupts_capture_or_propagates()
    test_observed_timeout_preserves_partial_output_and_kills_group()
    after = tree_hashes(RUNTIME_ROOT)
    status_after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert before == after, "process runner tests modified AgentRuntime files"
    assert status_before == status_after, "process runner tests created repository output"
    print("StandardProcessRunner smoke test: PASS (real bounded child processes)")


if __name__ == "__main__":
    main()
