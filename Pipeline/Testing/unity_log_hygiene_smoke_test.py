#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.Testing.unity_log_hygiene import (
    inspect_unity_log,
    normalize_unity_log,
    normalize_unity_log_bytes,
    trailing_whitespace_line_count,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_byte_normalization_preserves_content_and_line_endings() -> None:
    original = (
        b"\xef\xbb\xbfUnity log  \r\n"
        b"interior  spaces stay\tinside\n"
        b"tab at end\t\r"
        b"clean line\n"
        b"final trailing   "
    )
    expected = (
        b"\xef\xbb\xbfUnity log\r\n"
        b"interior  spaces stay\tinside\n"
        b"tab at end\r"
        b"clean line\n"
        b"final trailing"
    )
    normalized, changed = normalize_unity_log_bytes(original)
    require(normalized == expected, "normalizer changed non-trailing content or line endings")
    require(changed == 3, f"expected three changed lines, found {changed}")
    require(trailing_whitespace_line_count(normalized) == 0, "normalized bytes remain dirty")


def test_file_normalization_is_atomic_and_idempotent() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-log-hygiene-") as temporary:
        path = Path(temporary) / "unity.log"
        path.write_bytes(b"one   \r\ntwo\t\nthree\n")
        first = normalize_unity_log(path)
        require(first.status == "normalized", "first pass did not normalize")
        require(first.changed_lines == 2, "wrong changed-line count")
        require(path.read_bytes() == b"one\r\ntwo\nthree\n", "normalized bytes are wrong")
        second = normalize_unity_log(path)
        require(second.status == "clean", "second pass was not idempotent")
        require(second.sha256_before == second.sha256_after, "clean pass changed identity")
        require(inspect_unity_log(path).changed_lines == 0, "inspection did not report clean")


def test_cli_check_and_normalize_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-log-cli-") as temporary:
        path = Path(temporary) / "unity.log"
        path.write_bytes(b"dirty  \n")
        script = ROOT / "Pipeline" / "Testing" / "unity_log_hygiene.py"
        dirty = subprocess.run(
            [sys.executable, str(script), "check", "--path", str(path), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        require(dirty.returncode == 1, "check did not reject dirty log")
        dirty_json = json.loads(dirty.stdout)
        require(dirty_json["changed_lines"] == 1, "check JSON omitted dirty line")
        cleaned = subprocess.run(
            [sys.executable, str(script), "normalize", "--path", str(path), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        require(cleaned.returncode == 0, f"normalize failed: {cleaned.stderr}")
        require(json.loads(cleaned.stdout)["status"] == "normalized", "normalize JSON is wrong")
        require(path.read_bytes() == b"dirty\n", "CLI did not rewrite exact bytes")
        clean = subprocess.run(
            [sys.executable, str(script), "check", "--path", str(path), "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        require(clean.returncode == 0, "check rejected normalized log")


def test_git_whitespace_policy_preserves_legacy_logs_only() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-log-whitespace-git-") as temporary:
        repo = Path(temporary)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
        (repo / ".gitattributes").write_text(
            "Pipeline/TaskGraph/evidence/**/artifacts/*.log -whitespace\n",
            encoding="utf-8",
        )
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)
        legacy = repo / "Pipeline" / "TaskGraph" / "evidence" / "NSC-001" / "artifacts" / "Unity.log"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy   \n")
        (repo / "source.py").write_text("value = 1   \n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", "."], cwd=repo, check=True)
        failed = subprocess.run(["git", "diff", "--cached", "--check"], cwd=repo, stdout=subprocess.PIPE, text=True)
        require(failed.returncode != 0, "source trailing whitespace was incorrectly ignored")
        require("source.py" in failed.stdout, "source failure was not reported")
        require("Unity.log" not in failed.stdout, "legacy Unity log was not exempted")


def main() -> int:
    tests = (
        test_byte_normalization_preserves_content_and_line_endings,
        test_file_normalization_is_atomic_and_idempotent,
        test_cli_check_and_normalize_contract,
        test_git_whitespace_policy_preserves_legacy_logs_only,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Unity evidence log hygiene tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
