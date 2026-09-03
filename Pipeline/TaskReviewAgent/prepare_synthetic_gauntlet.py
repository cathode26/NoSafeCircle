#!/usr/bin/env python3
"""Prepare the private rehearsal repository for the synthetic 80-task gauntlet.

The tool preserves TaskGraph audit history: existing contracts stay on disk, but
every active contract except the structural NSC-001 root and NSC-042 is changed
to ``contract_disposition: cancelled``. Eighty synthetic contracts are added in
eight dependency waves. The first task in each wave requires decomposition; the
other nine are exact, disjoint two-file C#/.meta changes.

Mutation is deliberately restricted to a clean, synchronized, attached ``main``
checkout of an explicitly confirmed private GitHub rehearsal repository. The
tool does not commit or push. A failed materialization is rolled back in-process.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from persistent_work_graph import load_persistent_work_graph  # noqa: E402
from work_graph_transform import WorkGraphPlan  # noqa: E402
from work_graph_validate import validate_work_graph_plan  # noqa: E402
from decomposition_graph_semantics import (  # noqa: E402
    validate_decomposition_graph_semantics,
)
from graph_delta import semantic_json_sha256  # noqa: E402


GAUNTLET_SCHEMA_VERSION = "1.0"
GAUNTLET_FIRST_ID = 911
GAUNTLET_TASK_COUNT = 80
GAUNTLET_WAVE_SIZE = 10
GAUNTLET_ID = "synthetic-architect-gauntlet-v1"
ROOT_TASK_ID = "NSC-001"
PRESERVED_TASK_ID = "NSC-042"
TEST_FILTER = "NoSafeCircle.DoorPrototype.Tests.Editor.MuffcabbageGauntletTests"
TEST_RELATIVE = Path(
    "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/MuffcabbageGauntletTests.cs"
)
TEST_META_RELATIVE = Path(str(TEST_RELATIVE) + ".meta")
POLICY_RELATIVE = Path("Pipeline/TaskReviewAgent/authoritative_validation_policy.json")
SHA40 = re.compile(r"[0-9a-f]{40}")


class SyntheticGauntletError(RuntimeError):
    """Raised when rehearsal setup cannot be proven safe and exact."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _task_id(number: int) -> str:
    return f"NSC-{number:03d}"


def _guid(label: str) -> str:
    return hashlib.sha256(f"{GAUNTLET_ID}:{label}".encode("utf-8")).hexdigest()[:32]


def _value_paths(number: int, suffix: str = "") -> tuple[str, str]:
    stem = f"MuffcabbageGauntlet{number:03d}{suffix}"
    source = f"Assets/NoSafeCircle/DoorPrototype/Scripts/{stem}.cs"
    return source, source + ".meta"


def _test_method(number: int, suffix: str = "") -> str:
    return f"MuffcabbageGauntlet{number:03d}{suffix}HasExpectedValue"


def _test_filter(number: int, suffix: str = "") -> str:
    return f"{TEST_FILTER}.{_test_method(number, suffix)}"


def _dependency_ids(index: int) -> list[str]:
    if index < GAUNTLET_WAVE_SIZE:
        return []
    dependencies = [_task_id(GAUNTLET_FIRST_ID + index - GAUNTLET_WAVE_SIZE)]
    column = index % GAUNTLET_WAVE_SIZE
    if column > 0:
        dependencies.append(
            _task_id(GAUNTLET_FIRST_ID + index - GAUNTLET_WAVE_SIZE - 1)
        )
    return dependencies


def _acceptance(identifier: str, requirement: str) -> dict[str, str]:
    return {
        "criterion_id": identifier,
        "reference": "Human-approved private synthetic orchestration gauntlet",
        "requirement": requirement,
    }


def _gate(identifier: str, requirement: str) -> dict[str, str]:
    return {
        "gate_id": identifier,
        "reference": "Authoritative Unity EditMode validation",
        "requirement": requirement,
    }


def _concrete_task(number: int, index: int) -> dict[str, Any]:
    task_id = _task_id(number)
    source, meta = _value_paths(number)
    dependencies = _dependency_ids(index)
    dependency_text = (
        "No earlier gauntlet value is required."
        if not dependencies
        else "The scheduler must wait for " + ", ".join(dependencies) + " to become conformant."
    )
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": f"Muffcabbage Gauntlet {number}: Publish Its Isolated Value",
        "reconciliation_key": f"muffcabbage-gauntlet-{number}-value",
        "kind": "implementation",
        "type": "engineering-validation",
        "execution_scope": "single_agent",
        "execution_reason": (
            "One agent creates one uniquely named C# constant and its deterministic "
            "Unity .meta companion; no shared implementation file or design decision is involved."
        ),
        "decomposition_state": "concrete",
        "decomposition_reason": (
            f"Create {source} with one public constant Value = {number} and create its "
            f"specified .meta companion; {dependency_text}"
        ),
        "parent": ROOT_TASK_ID,
        "depends_on": dependencies,
        "exclusive_resources": [f"repo-file:{source}", f"repo-file:{meta}"],
        "acceptance_criteria": [
            _acceptance(
                "AC-001",
                f"Create {source} in namespace NoSafeCircle.DoorPrototype with a public "
                f"static class MuffcabbageGauntlet{number:03d} containing exactly "
                f"public const int Value = {number};.",
            ),
            _acceptance(
                "AC-002",
                f"Create {meta} with fileFormatVersion 2 and guid {_guid(task_id)}; do not "
                "modify any other task's value file.",
            ),
        ],
        "completion_gates": [
            _gate(
                "VAL-001",
                f"Unity EditMode filter {_test_filter(number)} passes for the exact commit "
                f"and proves Value == {number} for "
                f"MuffcabbageGauntlet{number:03d}.",
            )
        ],
        "downstream_integration_obligations": [],
        "basis": "human_approved_engineering_guidance",
        "source_scope": "engineering",
        "confidence": "high",
        "notes": (
            "Disposable private-repository gauntlet only. The file pair is intentionally "
            "disjoint so the software architect can admit safe parallel work."
        ),
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": GAUNTLET_ID,
            "wave": index // GAUNTLET_WAVE_SIZE + 1,
            "column": index % GAUNTLET_WAVE_SIZE + 1,
            "expected_value": number,
            "expected_paths": [source, meta],
        },
    }


def _decomposition_task(number: int, index: int) -> dict[str, Any]:
    task_id = _task_id(number)
    alpha, alpha_meta = _value_paths(number, "Alpha")
    beta, beta_meta = _value_paths(number, "Beta")
    dependencies = _dependency_ids(index)
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": f"Muffcabbage Gauntlet {number}: Split Alpha and Beta Values",
        "reconciliation_key": f"muffcabbage-gauntlet-{number}-pair",
        "kind": "implementation",
        "type": "engineering-validation",
        "execution_scope": "needs_execution_decomposition",
        "execution_reason": (
            "The parent deliberately owns two independently implementable and independently "
            "verifiable C#/.meta file pairs. The architect must choose decomposition rather "
            "than sending both responsibilities to one implementation worker."
        ),
        "decomposition_state": "concrete",
        "decomposition_reason": (
            "Produce exactly two concrete single-agent children: Alpha owns only its source/meta "
            "pair and Beta owns only its source/meta pair. Preserve the parent's dependencies on "
            "both children; rewrite every inbound dependent to the concrete child capabilities it uses."
        ),
        "parent": ROOT_TASK_ID,
        "depends_on": dependencies,
        "exclusive_resources": [
            f"repo-file:{alpha}",
            f"repo-file:{alpha_meta}",
            f"repo-file:{beta}",
            f"repo-file:{beta_meta}",
        ],
        "acceptance_criteria": [
            _acceptance(
                "AC-001",
                f"Create {alpha} and {alpha_meta}; the Alpha class is public static, is named "
                f"MuffcabbageGauntlet{number:03d}Alpha, and contains public const int Value = {number};. "
                f"The .meta guid is {_guid(task_id + '-alpha')}.",
            ),
            _acceptance(
                "AC-002",
                f"Create {beta} and {beta_meta}; the Beta class is public static, is named "
                f"MuffcabbageGauntlet{number:03d}Beta, and contains public const int Value = {number};. "
                f"The .meta guid is {_guid(task_id + '-beta')}.",
            ),
        ],
        "completion_gates": [
            _gate(
                "VAL-001",
                f"Unity EditMode filter {_test_filter(number, 'Alpha')} passes for the exact Alpha child commit and "
                f"proves MuffcabbageGauntlet{number:03d}Alpha.Value == {number}.",
            ),
            _gate(
                "VAL-002",
                f"Unity EditMode filter {_test_filter(number, 'Beta')} passes for the exact Beta child commit and "
                f"proves MuffcabbageGauntlet{number:03d}Beta.Value == {number}.",
            ),
        ],
        "downstream_integration_obligations": [],
        "basis": "human_approved_engineering_guidance",
        "source_scope": "engineering",
        "confidence": "high",
        "notes": (
            "Disposable private-repository gauntlet only. This deliberately exercises provider "
            "decomposition, exact-plan approval, D1C application, child allocation, and inbound "
            "dependency rewrite while ordinary implementation work remains available."
        ),
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": GAUNTLET_ID,
            "wave": index // GAUNTLET_WAVE_SIZE + 1,
            "column": 1,
            "requires_decomposition": True,
            "expected_values": [number, number],
            "expected_paths": [alpha, alpha_meta, beta, beta_meta],
        },
    }


def _cancel_for_gauntlet(task: Mapping[str, Any]) -> dict[str, Any]:
    cancelled = deepcopy(dict(task))
    if cancelled.get("contract_disposition") == "active":
        cancelled["contract_revision"] = int(cancelled["contract_revision"]) + 1
    cancelled["contract_disposition"] = "cancelled"
    cancelled.pop("superseded_by", None)
    # Strict aggregate semantics govern active applied decompositions. Once the
    # complete historical subtree is cancelled, retaining an active-child list
    # would falsely require those cancelled children to remain executable.
    cancelled.pop("decomposition_children", None)
    cancelled.pop("decomposition_requirement_sha256", None)
    cancelled["cancellation_reason"] = (
        "Removed from the active task tree for the human-approved private synthetic "
        f"orchestration gauntlet {GAUNTLET_ID}; historical contract retained for audit."
    )
    provenance = deepcopy(cancelled.get("provenance") or {})
    provenance["synthetic_gauntlet_retirement"] = GAUNTLET_ID
    cancelled["provenance"] = provenance
    return cancelled


def _preserve_42(task: Mapping[str, Any]) -> dict[str, Any]:
    preserved = deepcopy(dict(task))
    preserved["contract_revision"] = int(preserved["contract_revision"]) + 1
    preserved["parent"] = ROOT_TASK_ID
    preserved["depends_on"] = [_task_id(GAUNTLET_FIRST_ID + GAUNTLET_TASK_COUNT - 1)]
    provenance = deepcopy(preserved.get("provenance") or {})
    provenance["synthetic_gauntlet_rewire"] = GAUNTLET_ID
    provenance["synthetic_gauntlet_original_parent"] = task.get("parent")
    provenance["synthetic_gauntlet_original_dependencies"] = list(
        task.get("depends_on") or []
    )
    preserved["provenance"] = provenance
    return preserved


def _test_source() -> bytes:
    methods: list[str] = []
    for index in range(GAUNTLET_TASK_COUNT):
        number = GAUNTLET_FIRST_ID + index
        suffixes = ("Alpha", "Beta") if index % GAUNTLET_WAVE_SIZE == 0 else ("",)
        for suffix in suffixes:
            method = _test_method(number, suffix)
            type_name = f"MuffcabbageGauntlet{number:03d}{suffix}"
            methods.append(
                "\n".join(
                    (
                        "        [Test]",
                        f"        public void {method}()",
                        "        {",
                        f'            AssertValue("{type_name}", {number});',
                        "        }",
                    )
                )
            )
    text = r'''using System;
using System.Reflection;
using NUnit.Framework;

namespace NoSafeCircle.DoorPrototype.Tests.Editor
{
    public class MuffcabbageGauntletTests
    {
        private static void AssertValue(string typeName, int expected)
        {
            string qualifiedName = $"NoSafeCircle.DoorPrototype.{typeName}";
            Type type = typeof(DoorInteractable).Assembly.GetType(qualifiedName);
            Assert.That(type, Is.Not.Null, qualifiedName);
            FieldInfo field = type.GetField("Value", BindingFlags.Public | BindingFlags.Static);
            Assert.That(field, Is.Not.Null, qualifiedName);
            Assert.That(field.IsLiteral, Is.True, qualifiedName);
            Assert.That((int)field.GetRawConstantValue(), Is.EqualTo(expected), qualifiedName);
        }
__METHODS__
    }
}
'''
    text = text.replace("__METHODS__", "\n\n".join(methods))
    return text.replace("\n", "\r\n").encode("utf-8")


def _meta_source() -> bytes:
    return (
        "fileFormatVersion: 2\n"
        f"guid: {_guid(TEST_RELATIVE.as_posix())}\n"
    ).encode("utf-8")


def _validation_policy(
    source: Path,
    tasks: Sequence[Mapping[str, Any]],
    task_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    existing = json.loads((source / POLICY_RELATIVE).read_text(encoding="utf-8"))
    preserved = deepcopy((existing.get("tasks") or {}).get(PRESERVED_TASK_ID))
    if not isinstance(preserved, dict):
        raise SyntheticGauntletError("NSC-042 validation policy must already exist")
    preserved["task_contract_sha256"] = _sha256(task_bytes[PRESERVED_TASK_ID])
    policy: dict[str, Any] = {
        "schema_version": "1.0",
        "tasks": {PRESERVED_TASK_ID: preserved},
        "decomposition_child_templates": {},
    }
    for task in tasks:
        task_id = str(task["id"])
        provenance = task.get("provenance") or {}
        if provenance.get("gauntlet_id") != GAUNTLET_ID:
            continue
        number = int(task_id.split("-")[1])
        if task.get("execution_scope") == "single_agent":
            policy["tasks"][task_id] = {
                "task_contract_sha256": _sha256(task_bytes[task_id]),
                "required_test_platforms": ["EditMode"],
                "test_filters": {"EditMode": _test_filter(number)},
                "authority": "committed_private_synthetic_gauntlet_validation_policy",
            }
            continue
        alpha, alpha_meta = _value_paths(number, "Alpha")
        beta, beta_meta = _value_paths(number, "Beta")
        policy["decomposition_child_templates"][task_id] = {
            "parent_task_contract_sha256": semantic_json_sha256(
                {key: value for key, value in dict(task).items() if key != "task_contract_sha256"}
            ),
            "validation_variants": [
                {
                    "required_exclusive_resources": [
                        f"repo-file:{alpha}",
                        f"repo-file:{alpha_meta}",
                    ],
                    "required_test_platforms": ["EditMode"],
                    "test_filters": {"EditMode": _test_filter(number, "Alpha")},
                },
                {
                    "required_exclusive_resources": [
                        f"repo-file:{beta}",
                        f"repo-file:{beta_meta}",
                    ],
                    "required_test_platforms": ["EditMode"],
                    "test_filters": {"EditMode": _test_filter(number, "Beta")},
                },
            ],
            "authority": (
                "committed_private_synthetic_gauntlet_decomposition_child_policy"
            ),
        }
    return policy


def build_validation_repair_bundle(
    source: Path,
) -> tuple[dict[Path, bytes], dict[str, Any]]:
    graph = load_persistent_work_graph(source)
    tasks = [deepcopy(task) for task in graph.plan.tasks]
    by_id = {str(task["id"]): task for task in tasks}
    if PRESERVED_TASK_ID not in by_id:
        raise SyntheticGauntletError("validation repair requires NSC-042")
    gauntlet_tasks: list[dict[str, Any]] = []
    for index in range(GAUNTLET_TASK_COUNT):
        number = GAUNTLET_FIRST_ID + index
        task_id = _task_id(number)
        task = by_id.get(task_id)
        if task is None or (task.get("provenance") or {}).get("gauntlet_id") != GAUNTLET_ID:
            raise SyntheticGauntletError(
                "validation repair requires the exact materialized NSC-911 through NSC-990 graph"
            )
        task["contract_revision"] = int(task["contract_revision"]) + 1
        if index % GAUNTLET_WAVE_SIZE == 0:
            task["completion_gates"] = [
                _gate(
                    "VAL-001",
                    f"Unity EditMode filter {_test_filter(number, 'Alpha')} passes for the exact Alpha child commit and proves MuffcabbageGauntlet{number:03d}Alpha.Value == {number}.",
                ),
                _gate(
                    "VAL-002",
                    f"Unity EditMode filter {_test_filter(number, 'Beta')} passes for the exact Beta child commit and proves MuffcabbageGauntlet{number:03d}Beta.Value == {number}.",
                ),
            ]
        else:
            task["completion_gates"] = [
                _gate(
                    "VAL-001",
                    f"Unity EditMode filter {_test_filter(number)} passes for the exact commit and proves Value == {number} for MuffcabbageGauntlet{number:03d}.",
                )
            ]
        gauntlet_tasks.append(task)

    validate_work_graph_plan(
        WorkGraphPlan(
            id_map=deepcopy(graph.plan.id_map),
            tasks=tuple(tasks),
            resource_groups=deepcopy(graph.plan.resource_groups),
            project_requirements=deepcopy(graph.plan.project_requirements),
        )
    )
    task_bytes = {str(task["id"]): _json_bytes(task) for task in tasks}
    bundle = {
        Path("Tasks") / f"{task['id']}.yaml": task_bytes[str(task["id"])]
        for task in gauntlet_tasks
    }
    bundle[POLICY_RELATIVE] = _json_bytes(
        _validation_policy(source, tasks, task_bytes)
    )
    bundle[TEST_RELATIVE] = _test_source()
    return bundle, {
        "schema_version": GAUNTLET_SCHEMA_VERSION,
        "gauntlet_id": GAUNTLET_ID,
        "repaired_task_contracts": len(gauntlet_tasks),
        "test_methods": GAUNTLET_TASK_COUNT + GAUNTLET_TASK_COUNT // GAUNTLET_WAVE_SIZE,
        "target_paths": len(bundle),
    }


def build_bundle(source: Path) -> tuple[dict[Path, bytes], dict[str, Any]]:
    graph = load_persistent_work_graph(source)
    by_id = graph.tasks_by_id
    if ROOT_TASK_ID not in by_id or PRESERVED_TASK_ID not in by_id:
        raise SyntheticGauntletError("source graph must contain NSC-001 and NSC-042")
    if any(_task_id(number) in by_id for number in range(GAUNTLET_FIRST_ID, 991)):
        raise SyntheticGauntletError("synthetic NSC-911 through NSC-990 contracts already exist")

    tasks: list[dict[str, Any]] = []
    for task in graph.plan.tasks:
        task_id = task["id"]
        if task_id == ROOT_TASK_ID:
            tasks.append(deepcopy(task))
        elif task_id == PRESERVED_TASK_ID:
            tasks.append(_preserve_42(task))
        else:
            tasks.append(_cancel_for_gauntlet(task))

    decomposition_ids: list[str] = []
    concrete_ids: list[str] = []
    for index in range(GAUNTLET_TASK_COUNT):
        number = GAUNTLET_FIRST_ID + index
        if index % GAUNTLET_WAVE_SIZE == 0:
            task = _decomposition_task(number, index)
            decomposition_ids.append(task["id"])
        else:
            task = _concrete_task(number, index)
            concrete_ids.append(task["id"])
        tasks.append(task)

    tasks.sort(key=lambda item: int(item["id"].split("-")[1]))
    id_map = deepcopy(graph.plan.id_map)
    for task in tasks:
        id_map[task["reconciliation_key"]] = task["id"]
    plan = WorkGraphPlan(
        id_map=id_map,
        tasks=tuple(tasks),
        resource_groups=deepcopy(graph.plan.resource_groups),
        project_requirements=deepcopy(graph.plan.project_requirements),
    )
    validate_work_graph_plan(plan)
    validate_decomposition_graph_semantics(plan)

    bundle: dict[Path, bytes] = {}
    task_bytes: dict[str, bytes] = {}
    for task in tasks:
        data = _json_bytes(task)
        task_bytes[task["id"]] = data
        bundle[Path("Tasks") / f"{task['id']}.yaml"] = data

    taskgraph = Path("Pipeline/TaskGraph")
    bundle[taskgraph / "WORK_ID_MAP.json"] = _json_bytes(
        {
            "schema_version": "1.0",
            "serialization_format": "json",
            "reconciliation_run_id": GAUNTLET_ID,
            "verification_run_id": GAUNTLET_ID,
            "id_map": id_map,
        }
    )
    bundle[taskgraph / "RESOURCE_GROUPS.yaml"] = _json_bytes(
        {
            "schema_version": "1.0",
            "serialization_format": "yaml_1_2_json_subset",
            "reconciliation_run_id": GAUNTLET_ID,
            "verification_run_id": GAUNTLET_ID,
            "resource_groups": list(plan.resource_groups),
        }
    )
    bundle[taskgraph / "PROJECT_REQUIREMENTS.yaml"] = _json_bytes(
        {
            "schema_version": "1.0",
            "serialization_format": "yaml_1_2_json_subset",
            "reconciliation_run_id": GAUNTLET_ID,
            "verification_run_id": GAUNTLET_ID,
            "requirements": list(plan.project_requirements),
        }
    )

    policy = _validation_policy(source, tasks, task_bytes)
    bundle[POLICY_RELATIVE] = _json_bytes(policy)
    bundle[TEST_RELATIVE] = _test_source()
    bundle[TEST_META_RELATIVE] = _meta_source()

    summary = {
        "schema_version": GAUNTLET_SCHEMA_VERSION,
        "gauntlet_id": GAUNTLET_ID,
        "initial_synthetic_tasks": GAUNTLET_TASK_COUNT,
        "dependency_waves": GAUNTLET_TASK_COUNT // GAUNTLET_WAVE_SIZE,
        "wave_size": GAUNTLET_WAVE_SIZE,
        "decomposition_parents": decomposition_ids,
        "concrete_tasks": len(concrete_ids),
        "preserved_active_task": PRESERVED_TASK_ID,
        "cancelled_historical_tasks": sum(
            1
            for task in tasks
            if task["id"] not in {ROOT_TASK_ID, PRESERVED_TASK_ID}
            and task.get("provenance", {}).get("synthetic_gauntlet_retirement")
            == GAUNTLET_ID
        ),
        "target_paths": len(bundle),
        "bundle_sha256": _sha256(
            b"".join(
                path.as_posix().encode("utf-8") + b"\0" + bundle[path]
                for path in sorted(bundle, key=lambda item: item.as_posix())
            )
        ),
    }
    return bundle, summary


def _run(source: Path, *command: str) -> str:
    completed = subprocess.run(
        command,
        cwd=str(source),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180.0,
    )
    if completed.returncode != 0:
        raise SyntheticGauntletError(
            f"{' '.join(command)} failed: {' '.join(completed.stderr.split())[:700]}"
        )
    return completed.stdout.strip()


def _repository_from_origin(origin: str) -> str:
    match = re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+?)(?:\.git)?",
        origin.strip(),
        flags=re.IGNORECASE,
    )
    if match is None:
        raise SyntheticGauntletError("origin must be one github.com repository")
    return f"{match.group(1)}/{match.group(2)}"


def _preflight_mutation(
    source: Path,
    *,
    expected_head: str,
    confirmed_repository: str,
) -> str:
    if SHA40.fullmatch(expected_head) is None:
        raise SyntheticGauntletError("--expected-head must be a lowercase 40-character SHA")
    repository = _repository_from_origin(_run(source, "git", "remote", "get-url", "origin"))
    if repository.casefold() != confirmed_repository.casefold():
        raise SyntheticGauntletError(
            f"--confirm-repository must exactly name {repository}"
        )
    if repository.casefold() == "cathode26/nosafecircle":
        raise SyntheticGauntletError("synthetic gauntlet setup refuses the production repository")
    if "rehearsal" not in repository.casefold():
        raise SyntheticGauntletError("repository name must explicitly identify a rehearsal")
    metadata = json.loads(
        _run(
            source,
            "gh",
            "repo",
            "view",
            repository,
            "--json",
            "nameWithOwner,isPrivate,defaultBranchRef",
        )
    )
    if metadata.get("nameWithOwner", "").casefold() != repository.casefold():
        raise SyntheticGauntletError("GitHub metadata resolved a different repository")
    if metadata.get("isPrivate") is not True:
        raise SyntheticGauntletError("synthetic gauntlet mutation requires a private repository")
    if (metadata.get("defaultBranchRef") or {}).get("name") != "main":
        raise SyntheticGauntletError("rehearsal default branch must be main")
    if _run(source, "git", "branch", "--show-current") != "main":
        raise SyntheticGauntletError("rehearsal checkout must be attached to main")
    if _run(source, "git", "rev-parse", "HEAD") != expected_head:
        raise SyntheticGauntletError("rehearsal HEAD differs from --expected-head")
    if _run(source, "git", "status", "--porcelain=v1", "--untracked-files=all"):
        raise SyntheticGauntletError("rehearsal checkout must be completely clean")
    _run(source, "git", "fetch", "origin", "main")
    if _run(source, "git", "rev-parse", "origin/main") != expected_head:
        raise SyntheticGauntletError("origin/main differs from the exact local HEAD")
    return repository


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".synthetic-gauntlet.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise SyntheticGauntletError(f"temporary target already exists: {temporary}")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def apply_bundle(source: Path, bundle: Mapping[Path, bytes]) -> None:
    absolute = {source / relative: data for relative, data in bundle.items()}
    before = {path: path.read_bytes() if path.is_file() else None for path in absolute}
    try:
        for path in sorted(absolute, key=lambda item: item.as_posix()):
            _write_atomic(path, absolute[path])
        graph = load_persistent_work_graph(source)
        validate_work_graph_plan(graph.plan)
        validate_decomposition_graph_semantics(graph.plan)
        _run(source, "git", "diff", "--check")
    except Exception:
        for path in sorted(before, key=lambda item: item.as_posix(), reverse=True):
            original = before[path]
            if original is None:
                if path.exists() or path.is_symlink():
                    path.unlink()
            else:
                _write_atomic(path, original)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--expected-head")
    parser.add_argument("--confirm-repository")
    parser.add_argument("--repair-validation", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = args.source.resolve()
        bundle, summary = (
            build_validation_repair_bundle(source)
            if args.repair_validation
            else build_bundle(source)
        )
        if not args.apply:
            print(json.dumps({**summary, "status": "ready_dry_run"}, indent=2, sort_keys=True))
            return 0
        if not args.expected_head or not args.confirm_repository:
            raise SyntheticGauntletError(
                "--apply requires --expected-head and --confirm-repository"
            )
        repository = _preflight_mutation(
            source,
            expected_head=args.expected_head.strip().lower(),
            confirmed_repository=args.confirm_repository.strip(),
        )
        apply_bundle(source, bundle)
        print(
            json.dumps(
                {
                    **summary,
                    "status": "materialized_uncommitted",
                    "repository": repository,
                    "expected_head": args.expected_head.strip().lower(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, SyntheticGauntletError) as exc:
        print(f"Synthetic gauntlet setup blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
