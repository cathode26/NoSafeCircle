from __future__ import annotations

"""Canonical Unity scene-path policy for tracked assets and live repository text."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

CANONICAL_SCENE_ROOT = "Assets/Scenes/"
_SCENE_RE = re.compile(
    r"Assets/(?:[A-Za-z0-9_.()@+ -]+/)+[A-Za-z0-9_.()@+ -]+\.unity(?:\.meta)?"
)
_TEXT_SUFFIXES = frozenset(
    {
        ".asmdef",
        ".asmref",
        ".asset",
        ".cs",
        ".inputactions",
        ".json",
        ".md",
        ".prefab",
        ".ps1",
        ".py",
        ".shader",
        ".txt",
        ".uss",
        ".uxml",
        ".yaml",
        ".yml",
    }
)
_TOP_LEVEL_TEXT_FILES = frozenset(
    {
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "README.md",
    }
)
_LIVE_ROOTS = ("Assets/", "Docs/", "Packages/", "Pipeline/", "ProjectSettings/")
_IMMUTABLE_OR_GENERATED_PREFIXES = (
    "Docs/AI-Pipeline/Historical-Context-Sessions/raw/",
    "Pipeline/ArchitectureReview/outputs/",
    "Pipeline/ExecutionCrew/outputs/",
    "Pipeline/GDDRAG/knowledge_base/",
    "Pipeline/Reconciliation/outputs/",
    "Pipeline/TaskDecomposition/outputs/",
    "Pipeline/TaskGraph/migrations/",
)
_HISTORICAL_REFERENCE_ALLOWLIST = frozenset(
    {
        (
            "Docs/GDD/No_Safe_Circle_GDD.md",
            "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity",
        ),
        (
            "Pipeline/TaskGraph/scene_path_policy.py",
            "Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity",
        ),
    }
)


class ScenePathPolicyError(RuntimeError):
    pass


def _root(value: Path | str | None = None) -> Path:
    return Path(value).resolve() if value is not None else Path(__file__).resolve().parents[2]


def _run_git(repository: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ScenePathPolicyError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _tracked_paths(repository: Path, *patterns: str) -> list[str]:
    data = _run_git(repository, "ls-files", "-z", "--", *patterns)
    return sorted(item.decode("utf-8") for item in data.split(b"\0") if item)


def _references(value: Any, location: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        for match in _SCENE_RE.finditer(value):
            yield location, match.group(0)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _references(item, f"{location}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _references(item, f"{location}.{key}")


def _is_live_text_path(path: str) -> bool:
    if path.startswith("Tasks/"):
        return False
    if any(path.startswith(prefix) for prefix in _IMMUTABLE_OR_GENERATED_PREFIXES):
        return False
    if not (path.startswith(_LIVE_ROOTS) or "/" not in path):
        return False
    return PurePosixPath(path).suffix.casefold() in _TEXT_SUFFIXES or path in _TOP_LEVEL_TEXT_FILES


def _historical_reference_allowed(path: str, reference: str) -> bool:
    return (path, reference) in _HISTORICAL_REFERENCE_ALLOWLIST


def inspect_scene_path_policy(root: Path | str | None = None) -> dict[str, Any]:
    repository = _root(root)
    findings: list[str] = []

    tracked_scene_assets = _tracked_paths(repository, "*.unity", "*.unity.meta")
    for path in tracked_scene_assets:
        if not path.startswith(CANONICAL_SCENE_ROOT):
            findings.append(
                f"tracked Unity scene asset is outside {CANONICAL_SCENE_ROOT}: {path}"
            )

    contract_count = 0
    task_reference_count = 0
    for contract_path in sorted((repository / "Tasks").glob("NSC-*.yaml")):
        contract_count += 1
        relative = contract_path.relative_to(repository).as_posix()
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            findings.append(f"could not inspect {relative}: {exc}")
            continue
        for location, reference in _references(contract, relative):
            task_reference_count += 1
            if not reference.startswith(CANONICAL_SCENE_ROOT):
                findings.append(f"noncanonical scene reference at {location}: {reference}")

    live_text_file_count = 0
    live_text_reference_count = 0
    historical_reference_count = 0
    for relative in _tracked_paths(repository):
        if not _is_live_text_path(relative):
            continue
        live_text_file_count += 1
        path = repository / PurePosixPath(relative)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(f"could not inspect live text file {relative}: {exc}")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in _SCENE_RE.finditer(line):
                reference = match.group(0)
                if _historical_reference_allowed(relative, reference):
                    historical_reference_count += 1
                    continue
                live_text_reference_count += 1
                if not reference.startswith(CANONICAL_SCENE_ROOT):
                    findings.append(
                        f"noncanonical live scene reference at {relative}:{line_number}: {reference}"
                    )

    return {
        "schema_version": "1.0",
        "canonical_root": CANONICAL_SCENE_ROOT,
        "tracked_scene_assets": tracked_scene_assets,
        "task_contract_count": contract_count,
        "task_scene_reference_count": task_reference_count,
        "live_text_file_count": live_text_file_count,
        "live_text_scene_reference_count": live_text_reference_count,
        "allowed_historical_scene_reference_count": historical_reference_count,
        "allowed_historical_scene_references": [
            {"path": path, "reference": reference}
            for path, reference in sorted(_HISTORICAL_REFERENCE_ALLOWLIST)
        ],
        "excluded_historical_prefixes": list(_IMMUTABLE_OR_GENERATED_PREFIXES),
        "findings": findings,
        "status": "pass" if not findings else "fail",
    }


def validate_scene_path_policy(root: Path | str | None = None) -> dict[str, Any]:
    result = inspect_scene_path_policy(root)
    if result["findings"]:
        raise ScenePathPolicyError("\n".join(result["findings"]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_scene_path_policy(args.root)
    except ScenePathPolicyError as exc:
        print(f"scene path policy: FAIL\n{exc}")
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("scene path policy: PASS")
        print(f"Canonical root:        {result['canonical_root']}")
        print(f"Tracked scene assets:  {len(result['tracked_scene_assets'])}")
        print(f"Task scene references: {result['task_scene_reference_count']}")
        print(f"Live text references:  {result['live_text_scene_reference_count']}")
        print(f"Historical exceptions: {result['allowed_historical_scene_reference_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
