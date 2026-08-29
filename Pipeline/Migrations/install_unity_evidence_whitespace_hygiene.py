#!/usr/bin/env python3
"""One-shot installer for deterministic Unity evidence-log whitespace hygiene."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{label}: expected block not found in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def append_once(path: str, marker: str, content: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return
    target.write_text(text.rstrip() + "\n\n" + content.rstrip() + "\n", encoding="utf-8", newline="\n")


def install_helper() -> None:
    write(
        "Pipeline/Testing/unity_log_hygiene.py",
        '''#!/usr/bin/env python3
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
''',
    )


def install_tests() -> None:
    write(
        "Pipeline/Testing/unity_log_hygiene_smoke_test.py",
        '''#!/usr/bin/env python3
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
        b"\\xef\\xbb\\xbfUnity log  \\r\\n"
        b"interior  spaces stay\\tinside\\n"
        b"tab at end\\t\\r"
        b"clean line\\n"
        b"final trailing   "
    )
    expected = (
        b"\\xef\\xbb\\xbfUnity log\\r\\n"
        b"interior  spaces stay\\tinside\\n"
        b"tab at end\\r"
        b"clean line\\n"
        b"final trailing"
    )
    normalized, changed = normalize_unity_log_bytes(original)
    require(normalized == expected, "normalizer changed non-trailing content or line endings")
    require(changed == 3, f"expected three changed lines, found {changed}")
    require(trailing_whitespace_line_count(normalized) == 0, "normalized bytes remain dirty")


def test_file_normalization_is_atomic_and_idempotent() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-log-hygiene-") as temporary:
        path = Path(temporary) / "unity.log"
        path.write_bytes(b"one   \\r\\ntwo\\t\\nthree\\n")
        first = normalize_unity_log(path)
        require(first.status == "normalized", "first pass did not normalize")
        require(first.changed_lines == 2, "wrong changed-line count")
        require(path.read_bytes() == b"one\\r\\ntwo\\nthree\\n", "normalized bytes are wrong")
        second = normalize_unity_log(path)
        require(second.status == "clean", "second pass was not idempotent")
        require(second.sha256_before == second.sha256_after, "clean pass changed identity")
        require(inspect_unity_log(path).changed_lines == 0, "inspection did not report clean")


def test_cli_check_and_normalize_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-log-cli-") as temporary:
        path = Path(temporary) / "unity.log"
        path.write_bytes(b"dirty  \\n")
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
        require(path.read_bytes() == b"dirty\\n", "CLI did not rewrite exact bytes")
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
            "Pipeline/TaskGraph/evidence/**/artifacts/*.log -whitespace\\n",
            encoding="utf-8",
        )
        (repo / "base.txt").write_text("base\\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)
        legacy = repo / "Pipeline" / "TaskGraph" / "evidence" / "NSC-001" / "artifacts" / "Unity.log"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy   \\n")
        (repo / "source.py").write_text("value = 1   \\n", encoding="utf-8")
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
''',
    )


def patch_runner() -> None:
    path = "Pipeline/Testing/run_unity_tests_clean.ps1"
    old = '''    $manifestPath = Join-Path $artifactDirectory "validation-manifest.json"
    $manifestTemporaryPath = Join-Path $artifactDirectory (".validation-manifest-" + [Guid]::NewGuid().ToString("N") + ".tmp")
    try {
        $xmlFile = Get-Item -LiteralPath $xmlPath -ErrorAction Stop
'''
    new = '''    $manifestPath = Join-Path $artifactDirectory "validation-manifest.json"
    $manifestTemporaryPath = Join-Path $artifactDirectory (".validation-manifest-" + [Guid]::NewGuid().ToString("N") + ".tmp")

    # Unity batch logs regularly contain trailing spaces. Normalize them before
    # their SHA/size identities enter the authoritative validation manifest, so
    # the exact reviewed artifact is also safe for a later evidence commit.
    $logHygieneScript = Join-Path $resolvedProjectPath "Pipeline\\Testing\\unity_log_hygiene.py"
    if (-not (Test-Path -LiteralPath $logHygieneScript -PathType Leaf)) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log hygiene helper is missing: $logHygieneScript"
    }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $normalizationLines = @(
            & python $logHygieneScript normalize --path $logPath --json 2>&1
        )
        $normalizationExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $normalizationOutput = ($normalizationLines | Out-String).Trim()
    if ($normalizationExitCode -ne 0) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log normalization failed with exit code $normalizationExitCode.`n$normalizationOutput"
    }
    try {
        $logNormalization = $normalizationOutput | ConvertFrom-Json
    }
    catch {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log normalizer returned invalid JSON.`n$normalizationOutput"
    }
    Write-Host "Unity log hygiene: $($logNormalization.status) (changed lines: $($logNormalization.changed_lines))"

    try {
        $xmlFile = Get-Item -LiteralPath $xmlPath -ErrorAction Stop
'''
    replace_once(path, old, new, "authoritative runner normalization")


def patch_validation_loader() -> None:
    path = "Pipeline/Testing/validation_manifest.py"
    replace_once(
        path,
        "from typing import Any\n\n\nclass ValidationManifestError",
        '''from typing import Any

try:
    from .unity_log_hygiene import trailing_whitespace_line_count
except ImportError:  # direct script/module-path execution
    from unity_log_hygiene import trailing_whitespace_line_count


class ValidationManifestError''',
        "validation manifest hygiene import",
    )
    replace_once(
        path,
        '''    if xml.relative_path != "test-results.xml" or log.relative_path != "unity.log":
        raise ValidationManifestError("Artifact relative paths do not match the supported manifest schema.")
    runner = _object(root["runner"], "runner", {"path"})
''',
        '''    if xml.relative_path != "test-results.xml" or log.relative_path != "unity.log":
        raise ValidationManifestError("Artifact relative paths do not match the supported manifest schema.")
    try:
        dirty_log_lines = trailing_whitespace_line_count(log.path.read_bytes())
    except OSError as exc:
        raise ValidationManifestError("Unity log artifact could not be inspected for hygiene.") from exc
    if dirty_log_lines:
        raise ValidationManifestError(
            "Unity log artifact contains trailing whitespace on "
            f"{dirty_log_lines} line(s); run_unity_tests_clean.ps1 must normalize it "
            "before publishing the validation manifest."
        )
    runner = _object(root["runner"], "runner", {"path"})
''',
        "validation manifest hygiene enforcement",
    )


def patch_record_delivery() -> None:
    path = "Pipeline/TaskGraph/record_delivery.py"
    replace_once(
        path,
        '''ROOT = Path(__file__).resolve().parents[2]

DELIVERY_SPEC_SCHEMA_VERSION = "1.0"
''',
        '''ROOT = Path(__file__).resolve().parents[2]
TESTING_ROOT = ROOT / "Pipeline" / "Testing"
if str(TESTING_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTING_ROOT))
from unity_log_hygiene import trailing_whitespace_line_count

DELIVERY_SPEC_SCHEMA_VERSION = "1.0"
''',
        "record delivery hygiene import",
    )
    replace_once(
        path,
        '''def validate_unity_log(data: bytes, source_label: str) -> None:
    if not data:
        raise RecordDeliveryError(f"Unity log artifact at {source_label} is empty.")
''',
        '''def validate_unity_log(data: bytes, source_label: str) -> None:
    if not data:
        raise RecordDeliveryError(f"Unity log artifact at {source_label} is empty.")
    dirty_lines = trailing_whitespace_line_count(data)
    if dirty_lines:
        raise RecordDeliveryError(
            f"Unity log artifact at {source_label} contains trailing whitespace on "
            f"{dirty_lines} line(s). The authoritative Unity runner must normalize "
            "the log before review and packaging."
        )
''',
        "record delivery hygiene enforcement",
    )


def patch_downstream() -> None:
    path = "Pipeline/TaskReviewAgent/downstream_pipeline.py"
    old = '''    def _validate_staged_whitespace(self, created: list[str]) -> None:
        result = _git(
            self.command_runner,
            self.checkout,
            "diff",
            "--cached",
            "--check",
            check=False,
        )
        if result.returncode == 0:
            return
        output = _decode(result.stdout + result.stderr, "staged whitespace check")
        offending: set[str] = set()
        for line in output.splitlines():
            match = re.match(r"^(.+?):\\d+:", line)
            if match:
                offending.add(match.group(1))
        if not offending or any(path not in created or not path.casefold().endswith(".log") for path in offending):
            raise DownstreamPipelineError("staged evidence failed whitespace validation:\\n" + output)
        structured = [path for path in created if not path.casefold().endswith(".log")]
        if structured:
            _git(
                self.command_runner,
                self.checkout,
                "diff",
                "--cached",
                "--check",
                "--",
                *structured,
            )
'''
    new = '''    def _validate_staged_whitespace(self, created: list[str]) -> None:
        result = _git(
            self.command_runner,
            self.checkout,
            "diff",
            "--cached",
            "--check",
            "--",
            *created,
            check=False,
        )
        if result.returncode != 0:
            output = _decode(result.stdout + result.stderr, "staged whitespace check")
            raise DownstreamPipelineError(
                "staged evidence failed whitespace validation; Unity logs must be "
                "normalized before their validation manifest is created:\\n" + output
            )
'''
    replace_once(path, old, new, "downstream staged whitespace enforcement")


def patch_workflows() -> None:
    task_path = ".github/workflows/task-review-agent-deterministic.yml"
    replace_once(
        task_path,
        '      - "Pipeline/TaskGraph/**"\n      - "Tasks/**"\n',
        '      - "Pipeline/TaskGraph/**"\n      - "Pipeline/Testing/**"\n      - "Tasks/**"\n',
        "task workflow Testing path",
    )
    replace_once(
        task_path,
        '''      - name: Run downstream action grounding tests
        run: python Pipeline/TaskReviewAgent/tests/downstream_action_grounding_smoke_test.py

      - name: Run deterministic TaskReviewAgent smoke tests
''',
        '''      - name: Run downstream action grounding tests
        run: python Pipeline/TaskReviewAgent/tests/downstream_action_grounding_smoke_test.py

      - name: Run Unity evidence log hygiene tests
        shell: pwsh
        run: |
          $test = "Pipeline/Testing/unity_log_hygiene_smoke_test.py"
          if (Test-Path -LiteralPath $test -PathType Leaf) {
            python $test
          } else {
            Write-Host "Legacy PR head predates Unity evidence-log hygiene; compatibility whitespace policy still applies."
          }

      - name: Run deterministic TaskReviewAgent smoke tests
''',
        "task workflow hygiene test",
    )
    replace_once(
        task_path,
        '''          if ([string]::IsNullOrWhiteSpace($baseSha)) {
            git diff --check HEAD^...HEAD
          } else {
            git diff --check "$baseSha...HEAD"
          }
''',
        '''          # Existing hash-approved Unity logs are immutable evidence. Exclude
          # their machine-generated trailing spaces from the source whitespace gate.
          # New logs are normalized before their validation manifest is written.
          $evidenceLogExclusion = ":(exclude)Pipeline/TaskGraph/evidence/**/artifacts/*.log"
          if ([string]::IsNullOrWhiteSpace($baseSha)) {
            git diff --check HEAD^...HEAD -- . $evidenceLogExclusion
          } else {
            git diff --check "$baseSha...HEAD" -- . $evidenceLogExclusion
          }
''',
        "task workflow evidence log exclusion",
    )

    core_path = ".github/workflows/d1b2-core-deterministic.yml"
    replace_once(
        core_path,
        '      - "Pipeline/TaskGraph/**"\n      - "compose.yaml"\n',
        '      - "Pipeline/TaskGraph/**"\n      - "Pipeline/Testing/**"\n      - "compose.yaml"\n',
        "core workflow Testing path",
    )
    replace_once(
        core_path,
        '''      - name: Current persistent TaskGraph validation
        run: python Pipeline/TaskGraph/taskcontrol.py validate

      - name: Python compile check
''',
        '''      - name: Current persistent TaskGraph validation
        run: python Pipeline/TaskGraph/taskcontrol.py validate

      - name: Unity evidence log hygiene
        shell: pwsh
        run: |
          $test = "Pipeline/Testing/unity_log_hygiene_smoke_test.py"
          if (Test-Path -LiteralPath $test -PathType Leaf) {
            python $test
          } else {
            Write-Host "Legacy PR head predates Unity evidence-log hygiene; compatibility whitespace policy still applies."
          }

      - name: Python compile check
''',
        "core workflow hygiene test",
    )
    replace_once(
        core_path,
        '''      - name: Pull-request whitespace check
        shell: pwsh
        run: |
          git diff --check origin/${{ github.event.pull_request.base.ref }}...HEAD
''',
        '''      - name: Pull-request whitespace check
        shell: pwsh
        run: |
          $evidenceLogExclusion = ":(exclude)Pipeline/TaskGraph/evidence/**/artifacts/*.log"
          git diff --check origin/${{ github.event.pull_request.base.ref }}...HEAD -- . $evidenceLogExclusion
''',
        "core workflow evidence log exclusion",
    )


def install_attributes_and_docs() -> None:
    attributes = ROOT / ".gitattributes"
    line = "Pipeline/TaskGraph/evidence/**/artifacts/*.log -whitespace"
    if attributes.exists():
        text = attributes.read_text(encoding="utf-8")
        if line not in text.splitlines():
            attributes.write_text(text.rstrip() + "\n" + line + "\n", encoding="utf-8", newline="\n")
    else:
        attributes.write_text(
            "# Raw Unity logs are machine evidence; new logs are normalized upstream.\n"
            + line
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    append_once(
        "Docs/AI-Pipeline/UNITY_WORKSPACE_HYGIENE.md",
        "## Authoritative Unity evidence-log hygiene",
        '''## Authoritative Unity evidence-log hygiene

Workspace cleanup and committed evidence cleanup are separate boundaries. The
workspace helper restores proven-safe editor churn. Authoritative Unity logs are
instead normalized by `Pipeline/Testing/run_unity_tests_clean.ps1` before the log
SHA-256 and byte size enter `validation-manifest.json`.

The normalizer removes only ASCII spaces and tabs at logical line ends. It
preserves non-trailing content, original line endings, BOM bytes, and final-newline
state. `validation_manifest.py`, `record_delivery.py`, and the downstream staged
evidence check all reject a future unnormalized log.

Previously approved raw logs remain byte-for-byte immutable. The repository
whitespace gates exclude only `Pipeline/TaskGraph/evidence/**/artifacts/*.log` for
that compatibility case; source, JSON, XML, task contracts, and every other path
continue to use the full whitespace gate.
''',
    )


def main() -> int:
    install_helper()
    install_tests()
    patch_runner()
    patch_validation_loader()
    patch_record_delivery()
    patch_downstream()
    patch_workflows()
    install_attributes_and_docs()
    print(json.dumps({"status": "installed", "policy": "normalize_before_manifest"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
