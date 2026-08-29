from __future__ import annotations

"""Strict, provider-neutral loader for clean Unity validation manifests."""

import hashlib
import json
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .unity_log_hygiene import trailing_whitespace_line_count
except ImportError:  # direct script/module-path execution
    from unity_log_hygiene import trailing_whitespace_line_count


class ValidationManifestError(RuntimeError):
    """Raised when a validation manifest or one of its artifacts is invalid."""


@dataclass(frozen=True)
class ArtifactFact:
    relative_path: str
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ValidatedState:
    commit: str
    tree: str
    post_commit: str
    post_tree: str


@dataclass(frozen=True)
class UnityFact:
    version: str
    executable: str
    exit_code: int
    test_platform: str
    test_filter: str


@dataclass(frozen=True)
class TestRunFact:
    result: str
    total: int
    passed: int
    failed: int
    skipped: int


@dataclass(frozen=True)
class UnityValidationManifest:
    path: Path
    validated_state: ValidatedState
    unity: UnityFact
    test_run: TestRunFact
    xml: ArtifactFact
    log: ArtifactFact


_SHA40 = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _object(value: Any, label: str, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationManifestError(f"{label} must be an object.")
    missing, extra = fields - set(value), set(value) - fields
    if missing or extra:
        raise ValidationManifestError(f"{label} fields differ from schema (missing={sorted(missing)}, extra={sorted(extra)}).")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationManifestError(f"{label} must be a non-empty string.")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationManifestError(f"{label} must be a nonnegative integer.")
    return value


def _regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValidationManifestError(f"{label} is missing or inaccessible: {path}") from exc
    if not stat.S_ISREG(mode):
        raise ValidationManifestError(f"{label} must be a regular file: {path}")


def _artifact_path(directory: Path, value: Any, label: str) -> tuple[str, Path]:
    relative = _text(value, label)
    if "\\" in relative or relative.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", relative):
        raise ValidationManifestError(f"{label} must be a repository-independent relative path.")
    pure = PurePosixPath(relative)
    if relative != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValidationManifestError(f"{label} contains an empty, non-canonical, or traversal component.")
    candidate = directory.joinpath(*pure.parts)
    _regular_file(candidate, label)
    try:
        candidate.resolve(strict=True).relative_to(directory.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValidationManifestError(f"{label} escapes the manifest directory.") from exc
    return relative, candidate


def _artifact(directory: Path, raw: Any, label: str) -> ArtifactFact:
    item = _object(raw, label, {"relative_path", "sha256", "size_bytes"})
    relative, path = _artifact_path(directory, item["relative_path"], f"{label}.relative_path")
    digest = _text(item["sha256"], f"{label}.sha256")
    if not _SHA256.fullmatch(digest):
        raise ValidationManifestError(f"{label}.sha256 must be lowercase SHA-256.")
    size = _integer(item["size_bytes"], f"{label}.size_bytes")
    try:
        actual_size = path.stat().st_size
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise ValidationManifestError(f"Unable to verify {label}.") from exc
    if actual_size != size:
        raise ValidationManifestError(f"{label} byte size does not match the manifest.")
    if hasher.hexdigest() != digest:
        raise ValidationManifestError(f"{label} SHA-256 does not match the manifest.")
    return ArtifactFact(relative, path.resolve(), digest, size)


def _xml_count(root: ET.Element, name: str) -> int:
    raw = root.get(name)
    if raw is None or not re.fullmatch(r"[0-9]+", raw):
        raise ValidationManifestError(f"Unity XML test-run {name} is missing or invalid.")
    return int(raw)


def load_validation_manifest(path: Path) -> UnityValidationManifest:
    path = Path(path)
    _regular_file(path, "Validation manifest")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationManifestError(f"Unable to parse validation manifest JSON at {path}.") from exc
    root = _object(raw, "manifest", {"schema_version", "manifest_type", "status", "validated_state", "unity", "test_run", "artifacts", "runner"})
    if root["schema_version"] != "1.0" or root["manifest_type"] != "unity_test_validation" or root["status"] != "passed":
        raise ValidationManifestError("Unsupported validation manifest schema, type, or status.")

    state = _object(root["validated_state"], "validated_state", {"commit", "tree", "post_commit", "post_tree", "repository_clean_before", "repository_clean_after"})
    for name in ("commit", "tree", "post_commit", "post_tree"):
        if not isinstance(state[name], str) or not _SHA40.fullmatch(state[name]):
            raise ValidationManifestError(f"validated_state.{name} must be a lowercase 40-character Git SHA.")
    if state["commit"] != state["post_commit"] or state["tree"] != state["post_tree"]:
        raise ValidationManifestError("Pre/post validated Git identities differ.")
    if state["repository_clean_before"] is not True or state["repository_clean_after"] is not True:
        raise ValidationManifestError("Validation requires clean-before and clean-after to be exactly true.")

    unity = _object(root["unity"], "unity", {"version", "executable", "exit_code", "test_platform", "test_filter"})
    version, executable, test_filter = (_text(unity[k], f"unity.{k}") for k in ("version", "executable", "test_filter"))
    if unity["exit_code"] != 0 or isinstance(unity["exit_code"], bool):
        raise ValidationManifestError("unity.exit_code must be exactly zero.")
    if unity["test_platform"] not in {"EditMode", "PlayMode"}:
        raise ValidationManifestError("unity.test_platform must be EditMode or PlayMode.")

    run = _object(root["test_run"], "test_run", {"result", "total", "passed", "failed", "skipped"})
    if run["result"] != "Passed":
        raise ValidationManifestError("test_run.result must be exactly Passed.")
    counts = {name: _integer(run[name], f"test_run.{name}") for name in ("total", "passed", "failed", "skipped")}
    if counts["failed"] != 0:
        raise ValidationManifestError("test_run.failed must be zero.")
    if counts["total"] < counts["passed"] + counts["failed"] + counts["skipped"]:
        raise ValidationManifestError("test_run.total is smaller than its component counts.")

    artifacts = _object(root["artifacts"], "artifacts", {"xml", "log"})
    xml = _artifact(path.parent, artifacts["xml"], "artifacts.xml")
    log = _artifact(path.parent, artifacts["log"], "artifacts.log")
    if xml.relative_path != "test-results.xml" or log.relative_path != "unity.log":
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
    if runner["path"] != "Pipeline/Testing/run_unity_tests_clean.ps1":
        raise ValidationManifestError("runner.path is unsupported.")

    try:
        xml_root = ET.parse(xml.path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValidationManifestError("Unity XML artifact is malformed.") from exc
    if xml_root.tag != "test-run" or xml_root.get("result") != run["result"]:
        raise ValidationManifestError("Unity XML result does not match the manifest.")
    for name, expected in counts.items():
        if _xml_count(xml_root, name) != expected:
            raise ValidationManifestError(f"Unity XML {name} does not match the manifest.")

    return UnityValidationManifest(
        path=path.resolve(),
        validated_state=ValidatedState(state["commit"], state["tree"], state["post_commit"], state["post_tree"]),
        unity=UnityFact(version, executable, 0, unity["test_platform"], test_filter),
        test_run=TestRunFact(run["result"], counts["total"], counts["passed"], counts["failed"], counts["skipped"]),
        xml=xml,
        log=log,
    )
