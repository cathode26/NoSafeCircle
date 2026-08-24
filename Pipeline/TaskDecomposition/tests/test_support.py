"""Synthetic committed graph fixtures for deterministic D1B.1 smoke tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.providers.fake import FakeProvider
from TaskDecomposition.policy import semantic_json_sha256


def _run(root: Path, *args: str) -> None:
    subprocess.run(
        args,
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _entry_set(label: str) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    return (
        [{"criterion_id": "AC-001", "reference": "Synthetic GDD", "requirement": f"{label} acceptance."}],
        [{"gate_id": "VAL-001", "reference": "Synthetic policy", "requirement": f"{label} validation."}],
        [{"obligation_id": "INT-001", "reference": "Synthetic integration", "requirement": f"{label} integration."}],
    )


def task(
    task_id: str,
    key: str,
    kind: str,
    parent: str,
    scope: str,
    decomposition: str,
    *,
    dependencies: tuple[str, ...] = (),
    resources: tuple[str, ...] = (),
    bootstrap_evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    acceptance, gates, obligations = _entry_set(key)
    return {
        "schema_version": "2.0",
        "id": task_id,
        "contract_revision": 2 if task_id == "NSC-010" else 1,
        "contract_disposition": "active",
        "title": key.replace("-", " ").title(),
        "reconciliation_key": key,
        "kind": kind,
        "type": "synthetic",
        "execution_scope": scope,
        "execution_reason": "Synthetic bounded execution classification.",
        "decomposition_state": decomposition,
        "decomposition_reason": "Synthetic decomposition classification.",
        "parent": parent,
        "depends_on": list(dependencies),
        "exclusive_resources": list(resources),
        "acceptance_criteria": acceptance,
        "completion_gates": gates,
        "downstream_integration_obligations": obligations,
        "gdd_evidence": [
            {"reference": "Synthetic GDD section", "requirement": f"Canon for {key}."}
        ],
        "basis": "direct_gdd",
        "source_scope": "required",
        "confidence": "high",
        "notes": "",
        "repository_state_at_bootstrap": "missing",
        "repository_evidence_at_bootstrap": bootstrap_evidence or [],
        "provenance": {"origin": "synthetic_test_fixture"},
    }


def create_repository(root: Path) -> dict[str, dict[str, Any]]:
    tasks = [
        task("NSC-001", "no-safe-circle", "feature", "", "not_applicable", "coarse"),
        task("NSC-002", "selected-feature", "feature", "NSC-001", "unknown", "coarse"),
        task(
            "NSC-003", "dependency-runtime", "implementation", "NSC-001",
            "single_agent", "concrete", resources=("repo-file:Assets/Shared.cs",),
        ),
        task("NSC-004", "selected-sibling", "implementation", "NSC-002", "single_agent", "concrete"),
        task(
            "NSC-010", "selected-parent", "implementation", "NSC-002",
            "needs_execution_decomposition", "concrete",
            dependencies=("NSC-003",),
            resources=(
                "repo-file:Assets/Shared.cs",
                "unity-scene:Assets/Synthetic.unity",
            ),
            bootstrap_evidence=[
                {
                    "path": "Assets/Evidence.cs",
                    "evidence_type": "code",
                    "observation": "Historical bootstrap observation.",
                }
            ],
        ),
        task(
            "NSC-011", "existing-child", "implementation", "NSC-010",
            "single_agent", "concrete", resources=("logical:child-surface",),
        ),
        task(
            "NSC-012", "direct-dependent", "implementation", "NSC-001",
            "single_agent", "concrete", dependencies=("NSC-010",),
        ),
        task("NSC-1000", "numeric-tail", "implementation", "NSC-001", "single_agent", "concrete"),
    ]
    by_id = {item["id"]: item for item in tasks}
    (root / "Docs" / "GDD").mkdir(parents=True)
    (root / "Tasks").mkdir()
    (root / "Pipeline" / "TaskGraph").mkdir(parents=True)
    (root / "Assets").mkdir()
    (root / "Docs" / "GDD" / "No_Safe_Circle_GDD.md").write_text(
        "# Synthetic No Safe Circle GDD\n\nFull committed canon.\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "Assets" / "Shared.cs").write_text("// shared\n", encoding="utf-8", newline="\n")
    (root / "Assets" / "Evidence.cs").write_text("// evidence\n", encoding="utf-8", newline="\n")
    (root / "Assets" / "Synthetic.unity").write_text("synthetic scene\n", encoding="utf-8", newline="\n")
    for item in tasks:
        (root / "Tasks" / f"{item['id']}.yaml").write_text(
            json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    graph_root = root / "Pipeline" / "TaskGraph"
    id_map = {item["reconciliation_key"]: item["id"] for item in tasks}
    (graph_root / "WORK_ID_MAP.json").write_text(
        json.dumps({"id_map": id_map}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (graph_root / "PROJECT_REQUIREMENTS.yaml").write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "title": "Human review",
                        "requirement_type": "pipeline_constraint",
                        "status": "confirmed",
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    groups = {
        "resource_groups": [
            {
                "resource_key": "repo-file:Assets/Shared.cs",
                "work_ids": ["NSC-003", "NSC-010"],
                "reconciliation_keys": ["dependency-runtime", "selected-parent"],
            }
        ]
    }
    (graph_root / "RESOURCE_GROUPS.yaml").write_text(
        json.dumps(groups, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    baseline_paths = [
        "Docs/GDD/No_Safe_Circle_GDD.md",
        "Pipeline/TaskGraph/WORK_ID_MAP.json",
        "Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml",
        "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml",
        *(f"Tasks/{item['id']}.yaml" for item in tasks),
    ]
    marker = {
        "schema_version": "1.0",
        "bootstrap_status": "complete",
        "serialization_format": "yaml_1_2_json_subset",
        "output_sha256": {path: "0" * 64 for path in baseline_paths},
    }
    (graph_root / "BOOTSTRAP_PERSISTED.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _run(root, "git", "init", "-b", "main")
    _run(root, "git", "config", "user.name", "D1B Test")
    _run(root, "git", "config", "user.email", "d1b@example.invalid")
    _run(root, "git", "add", ".")
    _run(root, "git", "commit", "-m", "synthetic graph")
    _run(root, "git", "commit", "--allow-empty", "-m", "stable source identity")
    return by_id


def parent_identity(parent: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": parent["id"],
        "contract_revision": parent["contract_revision"],
        "contract_sha256": semantic_json_sha256(parent),
    }


def base_result(parent: dict[str, Any], decision: str, gap: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "parent_task": parent_identity(parent),
        "decision": decision,
        "gap_type": gap,
        "reason": "Synthetic deterministic review proposal.",
        "children": [],
        "parent_requirement_coverage": [],
        "unsupported_assumptions": [],
        "unresolved_questions": [],
        "artifact_proposal": None,
    }


def _coverage(disposition: str, targets: dict[str, list[dict[str, str]]] | None = None) -> list[dict[str, Any]]:
    targets = targets or {}
    return [
        {
            "parent_entry_type": entry_type,
            "parent_entry_id": entry_id,
            "disposition": disposition,
            "child_targets": targets.get(entry_type, []),
            "reason": "Exact synthetic coverage.",
            "integration_rationale": "",
        }
        for entry_type, entry_id in (
            ("acceptance_criteria", "AC-001"),
            ("completion_gates", "VAL-001"),
            ("downstream_integration_obligations", "INT-001"),
        )
    ]


def already_concrete_result(parent: dict[str, Any]) -> dict[str, Any]:
    value = base_result(parent, "already_concrete", "none")
    value["parent_requirement_coverage"] = _coverage("retained_by_parent")
    return value


def decomposed_result(parent: dict[str, Any], *, missing_dependency: bool = False) -> dict[str, Any]:
    value = base_result(parent, "decomposed", "execution")
    value["children"] = [
        {
            "local_key": "bounded-child",
            "title": "Bounded child",
            "kind": "implementation",
            "type": "synthetic_child",
            "execution_scope": "single_agent",
            "execution_reason": "One bounded responsibility.",
            "decomposition_state": "concrete",
            "decomposition_reason": "Canon is sufficient.",
            "existing_task_dependencies": ["NSC-999" if missing_dependency else "NSC-003"],
            "local_dependencies": [],
            "exclusive_resources": ["repo-file:Assets/Shared.cs"],
            "acceptance_criteria": [
                {"criterion_id": "AC-001", "reference": "Parent AC-001", "requirement": "Child acceptance."}
            ],
            "completion_gates": [
                {"gate_id": "VAL-001", "reference": "Parent VAL-001", "requirement": "Child validation."}
            ],
            "downstream_integration_obligations": [
                {"obligation_id": "INT-001", "reference": "Parent INT-001", "requirement": "Child integration."}
            ],
            "gdd_evidence": [
                {"reference": "Synthetic GDD", "requirement": "Approved behavior only."}
            ],
            "basis": "direct_gdd",
            "source_scope": "required",
            "confidence": "high",
            "notes": "",
        }
    ]
    value["parent_requirement_coverage"] = _coverage(
        "assigned_to_child",
        {
            "acceptance_criteria": [
                {"local_key": "bounded-child", "child_entry_type": "acceptance_criteria", "child_entry_id": "AC-001"}
            ],
            "completion_gates": [
                {"local_key": "bounded-child", "child_entry_type": "completion_gates", "child_entry_id": "VAL-001"}
            ],
            "downstream_integration_obligations": [
                {"local_key": "bounded-child", "child_entry_type": "downstream_integration_obligations", "child_entry_id": "INT-001"}
            ],
        },
    )
    return value


def needs_artifact_result(parent: dict[str, Any]) -> dict[str, Any]:
    value = base_result(parent, "needs_artifact", "design")
    value["parent_requirement_coverage"] = _coverage("retained_by_parent")
    value["parent_requirement_coverage"][0]["disposition"] = "blocked_by_artifact"
    value["artifact_proposal"] = {
        "title": "Smallest missing design",
        "purpose": "Resolve only the blocking boundary.",
        "source_parent_obligations": [
            {"parent_entry_type": "acceptance_criteria", "parent_entry_id": "AC-001"}
        ],
        "authorized_decisions_needed": ["Choose the approved boundary."],
        "out_of_scope": ["New mechanics."],
    }
    return value


def needs_human_result(parent: dict[str, Any]) -> dict[str, Any]:
    value = base_result(parent, "needs_human", "uncertain")
    value["parent_requirement_coverage"] = _coverage("retained_by_parent")
    value["parent_requirement_coverage"][0]["disposition"] = "blocked_by_human"
    value["unresolved_questions"] = ["Which approved interpretation applies?"]
    return value


def fake_factory(provider: FakeProvider):
    def factory(provider_name: str, _source: Path):
        key = f"{provider_name}-decomposition"
        model = "deterministic-fake-model"
        configuration = RuntimeConfiguration({
            key: {
                "provider": "fake",
                "models": {
                    "low_cost": model,
                    "standard": model,
                    "high_reasoning": model,
                },
            }
        })
        return key, configuration, {"fake": provider}
    return factory


def protected_bytes(root: Path) -> dict[str, str]:
    paths = sorted(root.glob("Tasks/*.yaml")) + [
        root / "Docs" / "GDD" / "No_Safe_Circle_GDD.md",
        root / "Pipeline" / "TaskGraph" / "BOOTSTRAP_PERSISTED.json",
        root / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json",
        root / "Pipeline" / "TaskGraph" / "PROJECT_REQUIREMENTS.yaml",
        root / "Pipeline" / "TaskGraph" / "RESOURCE_GROUPS.yaml",
    ]
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }
