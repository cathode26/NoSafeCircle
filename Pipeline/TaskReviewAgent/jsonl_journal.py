"""Process-safe append support for shared JSONL run journals."""

from __future__ import annotations

import os
import threading
from pathlib import Path


_THREAD_LOCK = threading.Lock()


def _lock_exclusive(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _unlock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError(
                f"short JSONL append: wrote {offset} of {len(payload)} bytes"
            )
        offset += written


def append_jsonl_bytes(path: Path | str, payload: bytes) -> None:
    """Append one complete UTF-8 JSON line across threads and processes.

    Windows CRT append mode is not a sufficient multi-process record boundary:
    two otherwise valid writers can interleave their seek/write operations.
    A persistent sibling lock file serializes the complete record while a
    process-local lock also makes the behavior unambiguous between threads.
    The lock file carries no workflow authority and may safely outlive a run.
    """

    journal = Path(path)
    if not journal.is_absolute():
        raise ValueError("JSONL journal path must be absolute")
    journal = journal.resolve()
    if not isinstance(payload, bytes) or not payload.endswith(b"\n"):
        raise ValueError("JSONL append must be bytes ending in one newline")
    if b"\n" in payload[:-1] or b"\r" in payload:
        raise ValueError("JSONL append must contain exactly one LF-terminated record")

    journal.parent.mkdir(parents=True, exist_ok=True)
    lock_path = journal.with_name(f".{journal.name}.append.lock")
    with _THREAD_LOCK:
        with lock_path.open("a+b") as lock_stream:
            lock_stream.seek(0, os.SEEK_END)
            if lock_stream.tell() == 0:
                lock_stream.write(b"\0")
                lock_stream.flush()
            _lock_exclusive(lock_stream)
            try:
                descriptor = os.open(
                    journal,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    0o600,
                )
                try:
                    _write_all(descriptor, payload)
                finally:
                    os.close(descriptor)
            finally:
                _unlock(lock_stream)
