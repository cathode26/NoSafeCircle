#!/usr/bin/env python3
"""Deterministically remove trailing spaces and tabs from Unity text logs.

Unity's batch-mode log regularly contains spaces immediately before line endings.
Those bytes carry no test meaning but fail `git diff --check` after the log is
packaged as TaskGraph evidence. This helper preserves every non-trailing byte,
all original line-ending sequences, any UTF-8 BOM, and the absence/presence of a
final newline. It is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class UnityLogHygieneError(RuntimeError):
    pass


@dataclass(frozen=True)
class UnityLogHygieneResult:
    path: str
    status: str
    changed_lines: int
    size_before: int
    size_after: int
    sha256_before: str
    sha256_after: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "path": self.path,
            "status": self.status,
            "changed_lines": self.changed_lines,
            "size_before": self.size_before,
            "size_after": self.size_after,
            "sha256_before": self.sha256_before,
            "sha256_after": self.sha256_after,
        }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_unity_log_bytes(data: bytes) -> tuple[bytes, int]:
    """Strip ASCII space/tab at logical line ends without decoding the log."""

    output = bytearray()
    changed_lines = 0
    line_start = 0
    index = 0
    length = len(data)

    while index < length:
        value = data[index]
        if value not in (10, 13):
            index += 1
            continue

        line = data[line_start:index]
        cleaned = line.rstrip(b" \t")
        if cleaned != line:
            changed_lines += 1
        output.extend(cleaned)

        if value == 13 and index + 1 < length and data[index + 1] == 10:
            output.extend(b"\r\n")
            index += 2
        else:
            output.append(value)
            index += 1
        line_start = index

    final_line = data[line_start:]
    cleaned_final = final_line.rstrip(b" \t")
    if cleaned_final != final_line:
        changed_lines += 1
    output.extend(cleaned_final)
    return bytes(output), changed_lines


def trailing_whitespace_line_count(data: bytes) -> int:
    return normalize_unity_log_bytes(data)[1]


def inspect_unity_log(path: Path | str) -> UnityLogHygieneResult:
    target = Path(path).expanduser().resolve(strict=True)
    if not target.is_file():
        raise UnityLogHygieneError(f"Unity log is not a regular file: {target}")
    data = target.read_bytes()
    normalized, changed = normalize_unity_log_bytes(data)
    return UnityLogHygieneResult(
        path=str(target),
        status="clean" if changed == 0 else "needs_normalization",
        changed_lines=changed,
        size_before=len(data),
        size_after=len(normalized),
        sha256_before=_sha(data),
        sha256_after=_sha(normalized),
    )


def normalize_unity_log(path: Path | str) -> UnityLogHygieneResult:
    target = Path(path).expanduser().resolve(strict=True)
    if not target.is_file():
        raise UnityLogHygieneError(f"Unity log is not a regular file: {target}")
    data = target.read_bytes()
    normalized, changed = normalize_unity_log_bytes(data)
    before = _sha(data)
    after = _sha(normalized)
    if changed:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(normalized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return UnityLogHygieneResult(
        path=str(target),
        status="normalized" if changed else "clean",
        changed_lines=changed,
        size_before=len(data),
        size_after=len(normalized),
        sha256_before=before,
        sha256_after=after,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "normalize"))
    parser.add_argument("--path", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (
            inspect_unity_log(args.path)
            if args.command == "check"
            else normalize_unity_log(args.path)
        )
    except (OSError, UnityLogHygieneError) as exc:
        print(f"unity_log_hygiene: FAIL\n{exc}")
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), sort_keys=True))
    else:
        print(
            f"Unity log hygiene: {result.status}; "
            f"changed_lines={result.changed_lines}; path={result.path}"
        )
    if args.command == "check" and result.changed_lines:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
