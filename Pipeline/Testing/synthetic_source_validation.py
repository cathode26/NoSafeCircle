"""Exact C# constant/.meta validation for the private thousand profile only.

This runner proves source bytes, not a Unity import, compilation, or runtime
test. Its manifest explicitly identifies that narrower evidence type.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (
    GAUNTLET_ID, _guid, _repository_from_origin, _test_filter, _value_paths, authorized_repository,
    SyntheticGauntletError,
)

PLATFORM = "SyntheticSource"
RUNNER_PATH = "Pipeline/Testing/synthetic_source_validation.py"


def constant_tokens(value: str) -> tuple[str, ...]:
    """Permit formatting between tokens without joining broken C# tokens."""
    tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[{}.;=]|[^ \t\r\n]", value)
    return tuple(tokens)


def git(source: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=source, capture_output=True,
                                text=True, encoding="utf-8", check=True, timeout=30)
    except subprocess.SubprocessError as exc:
        raise ValueError("exact source-validation Git observation failed") from exc
    return result.stdout.strip()


def source_contract(source: Path, task: dict) -> tuple[str, str, int]:
    """Return the exact script/meta/value or refuse unrelated contracts."""
    if task.get("id") == "NSC-042" or task.get("execution_scope") != "single_agent":
        raise ValueError("source validation requires a concrete synthetic implementation")
    provenance = task.get("provenance") or {}
    parent = task
    if provenance.get("origin") == "progressive_decomposition":
        parent_id = provenance.get("parent_task_id")
        if not isinstance(parent_id, str) or not re.fullmatch(r"NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})", parent_id):
            raise ValueError("synthetic child has no exact parent")
        parent = json.loads(git(source, "show", f"HEAD:Tasks/{parent_id}.yaml"))
        if task["id"] not in parent.get("decomposition_children", []):
            raise ValueError("synthetic child is not in its committed parent scope")
    origin = parent.get("provenance") or {}
    if (origin.get("origin") != "human_approved_synthetic_gauntlet"
            or origin.get("gauntlet_id") != GAUNTLET_ID or origin.get("profile") != "thousand"):
        raise ValueError("source validation is restricted to the thousand profile")
    number = int(parent["id"][4:])
    if not 2000 <= number <= 2999:
        raise ValueError("source validation parent is outside the reserved range")
    paths = {resource.removeprefix("repo-file:") for resource in task["exclusive_resources"]
             if resource.startswith("repo-file:")}
    suffixes = ("Alpha", "Beta") if parent is not task else ("",)
    for suffix in suffixes:
        script, meta = _value_paths(number, suffix)
        if paths == {script, meta}:
            return script, meta, number
    raise ValueError("synthetic contract does not own one exact source/meta pair")


def validate(source: Path, task_id: str, test_filter: str, output: Path) -> Path:
    source = source.resolve()
    if not re.fullmatch(r"NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})", task_id):
        raise ValueError("invalid task identity")
    origin = git(source, "remote", "get-url", "origin")
    try:
        repository = authorized_repository(_repository_from_origin(origin))
    except SyntheticGauntletError as exc:
        raise ValueError(str(exc)) from exc
    if git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("source validation requires a clean checkout")
    commit, tree = git(source, "rev-parse", "HEAD"), git(source, "rev-parse", "HEAD^{tree}")
    task = json.loads(git(source, "show", f"{commit}:Tasks/{task_id}.yaml"))
    script, meta, number = source_contract(source, task)
    suffix = Path(script).stem.removeprefix(f"MuffcabbageGauntlet{number}")
    if test_filter != _test_filter(number, suffix):
        raise ValueError("source validation filter differs from the exact task")
    expected = (f"namespace NoSafeCircle.DoorPrototype {{ public static class {Path(script).stem} "
                f"{{ public const int Value = {number}; }} }}")
    # Exact lexical tokens permit formatting, never split keywords/identifiers,
    # comments, extra members, attributes or alternate expressions.
    if constant_tokens((source / script).read_text(encoding="utf-8-sig")) != constant_tokens(expected):
        raise ValueError("C# source differs from the exact constant-only contract")
    meta_text = (source / meta).read_text(encoding="utf-8-sig")
    if re.findall(r"(?m)^guid:\s*(\S+)\s*$", meta_text) != [_guid(script)]:
        raise ValueError("Unity sidecar GUID differs from its deterministic source identity")
    if re.findall(r"(?m)^fileFormatVersion:\s*(\S+)\s*$", meta_text) != ["2"]:
        raise ValueError("Unity sidecar file format is invalid")
    if (git(source, "rev-parse", "HEAD") != commit
            or git(source, "rev-parse", "HEAD^{tree}") != tree
            or git(source, "remote", "get-url", "origin") != origin
            or git(source, "status", "--porcelain=v1", "--untracked-files=all")):
        raise ValueError("checkout moved during source validation")
    if output.resolve().is_relative_to(source):
        raise ValueError("source-validation evidence must be outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    xml = ET.Element("test-run", result="Passed", total="2", passed="2", failed="0", skipped="0")
    for name in ("exact_csharp_constant", "deterministic_unity_sidecar"):
        ET.SubElement(xml, "test-case", name=name, result="Passed")
    (output / "test-results.xml").write_bytes(ET.tostring(xml, encoding="utf-8", xml_declaration=True))
    (output / "source-validation.log").write_text(
        f"Exact source checks passed for {task_id} in {repository} at {commit}.\n"
        "No Unity import, C# compiler, or runtime test was executed.\n", encoding="utf-8", newline="\n")
    def artifact(name):
        data = (output / name).read_bytes()
        return {"relative_path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    manifest = {
        "schema_version": "1.0", "manifest_type": "synthetic_source_validation", "status": "passed",
        "repository": repository,
        "validated_state": {"commit": commit, "tree": tree, "post_commit": commit, "post_tree": tree,
                            "repository_clean_before": True, "repository_clean_after": True},
        "executor": {"version": sys.version.split()[0], "executable": sys.executable, "exit_code": 0,
                     "test_platform": PLATFORM, "test_filter": test_filter},
        "test_run": {"result": "Passed", "total": 2, "passed": 2, "failed": 0, "skipped": 0},
        "artifacts": {"xml": artifact("test-results.xml"), "log": artifact("source-validation.log")},
        "runner": {"path": RUNNER_PATH},
    }
    path = output / "validation-manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--test-filter", required=True)
    args = parser.parse_args()
    # Reserve a disposable parent; validate creates the child without overwrite.
    output = Path(tempfile.mkdtemp(prefix="nsc-source-validation-")) / "evidence"
    path = validate(args.source, args.task_id, args.test_filter, output)
    print(f"Validation manifest: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
