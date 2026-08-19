from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from output_layout import write_current_view


ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "Pipeline" / "Reconciliation"
PROMPT_PATH = AGENT_ROOT / "prompts" / "reconcile.md"
OUTPUT_DIR = AGENT_ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "runs"
LATEST_POINTER_PATH = OUTPUT_DIR / "LATEST.json"
TASKS_DIR = ROOT / "Tasks"

MODEL = os.environ.get("RECONCILIATION_MODEL", "sonnet")
REPAIR_MODEL = os.environ.get("RECONCILIATION_REPAIR_MODEL", "opus")
TIMEOUT_SECONDS = int(os.environ.get("RECONCILIATION_TIMEOUT_SECONDS", "1800"))
MAX_TURNS = int(os.environ.get("RECONCILIATION_MAX_TURNS", "50"))

REPAIR_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_REPAIR_TIMEOUT_SECONDS", "600")
)
REPAIR_MAX_TURNS = int(
    os.environ.get("RECONCILIATION_REPAIR_MAX_TURNS", "20")
)
MAX_STRUCTURAL_REPAIR_PASSES = int(
    os.environ.get("RECONCILIATION_MAX_STRUCTURAL_REPAIRS", "2")
)


# ============================================================
# STRUCTURED OUTPUT SCHEMA
# ============================================================

GDD_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reference": {"type": "string"},
        "requirement": {"type": "string"},
    },
    "required": ["reference", "requirement"],
}

REPOSITORY_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "path": {"type": "string"},
        "evidence_type": {
            "type": "string",
            "enum": [
                "code",
                "scene",
                "prefab",
                "test",
                "project_setting",
                "history",
            ],
        },
        "observation": {"type": "string"},
    },
    "required": ["path", "evidence_type", "observation"],
}

DEPENDENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "key": {"type": "string"},
        "reason": {"type": "string"},
        "evidence": {"type": "string"},
    },
    "required": ["key", "reason", "evidence"],
}

WORK_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "key": {"type": "string"},
        "title": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": ["feature", "artifact", "implementation"],
        },
        "type": {"type": "string"},
        "parent_key": {"type": "string"},
        "basis": {
            "type": "string",
            "enum": [
                "direct_gdd",
                "derived_required_foundation",
                "existing_integrated_work",
            ],
        },
        "source_scope": {
            "type": "string",
            "enum": ["required", "supporting"],
        },
        "gdd_evidence": {
            "type": "array",
            "items": GDD_EVIDENCE_SCHEMA,
        },
        "repository_state": {
            "type": "string",
            "enum": [
                "implemented",
                "partial",
                "missing",
                "not_applicable",
                "unknown",
            ],
        },
        "graph_status": {
            "type": "string",
            "enum": ["open", "complete"],
        },
        "repository_evidence": {
            "type": "array",
            "items": REPOSITORY_EVIDENCE_SCHEMA,
        },
        "depends_on": {
            "type": "array",
            "items": DEPENDENCY_SCHEMA,
        },
        "decomposition_state": {
            "type": "string",
            "enum": [
                "concrete",
                "coarse",
                "needs_future_decomposition",
                "not_applicable",
            ],
        },
        "decomposition_reason": {"type": "string"},
        "execution_scope": {
            "type": "string",
            "enum": [
                "single_agent",
                "needs_execution_decomposition",
                "human_integration_required",
                "not_applicable",
                "unknown",
            ],
        },
        "execution_reason": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "notes": {"type": "string"},
    },
    "required": [
        "key",
        "title",
        "kind",
        "type",
        "parent_key",
        "basis",
        "source_scope",
        "gdd_evidence",
        "repository_state",
        "graph_status",
        "repository_evidence",
        "depends_on",
        "decomposition_state",
        "decomposition_reason",
        "execution_scope",
        "execution_reason",
        "confidence",
        "notes",
    ],
}


MISSING_DEPENDENCY_REPAIR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "work_items_to_add": {
            "type": "array",
            "items": WORK_ITEM_SCHEMA,
        },
        "dependencies_to_remove": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "owner_key": {"type": "string"},
                    "dependency_key": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["owner_key", "dependency_key", "reason"],
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": [
        "work_items_to_add",
        "dependencies_to_remove",
        "reasoning",
    ],
}


NON_CODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["confirmed", "not_assessable", "unknown"],
        },
        "gdd_evidence": {"type": "array", "items": GDD_EVIDENCE_SCHEMA},
        "evidence": {"type": "string"},
    },
    "required": ["title", "status", "gdd_evidence", "evidence"],
}

DEFERRED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": ["stretch", "explicitly_excluded"],
        },
        "reason": {"type": "string"},
        "gdd_evidence": {"type": "array", "items": GDD_EVIDENCE_SCHEMA},
    },
    "required": ["title", "classification", "reason", "gdd_evidence"],
}

UNRESOLVED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "question": {"type": "string"},
        "affects_keys": {
            "type": "array",
            "items": {"type": "string"},
        },
        "why_unresolved": {"type": "string"},
        "recommended_resolution": {
            "type": "string",
            "enum": [
                "human_review",
                "runtime_validation",
                "later_decomposition",
                "repository_inspection",
            ],
        },
    },
    "required": [
        "question",
        "affects_keys",
        "why_unresolved",
        "recommended_resolution",
    ],
}

RECONCILIATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string"},
        "summary": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "desired_state_summary": {"type": "string"},
                "current_state_summary": {"type": "string"},
                "major_findings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "desired_state_summary",
                "current_state_summary",
                "major_findings",
            ],
        },
        "sources": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "gdd": {"type": "string"},
                "code_root": {"type": "string"},
                "historical_sources_reviewed": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "files_reviewed": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "gdd",
                "code_root",
                "historical_sources_reviewed",
                "files_reviewed",
            ],
        },
        "work_items": {
            "type": "array",
            "items": WORK_ITEM_SCHEMA,
            "minItems": 1,
        },
        "non_code_requirements": {
            "type": "array",
            "items": NON_CODE_SCHEMA,
        },
        "deferred_or_excluded": {
            "type": "array",
            "items": DEFERRED_SCHEMA,
        },
        "unresolved_questions": {
            "type": "array",
            "items": UNRESOLVED_SCHEMA,
        },
        "seed_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ready", "ready_with_warnings", "blocked"],
                },
                "blockers": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "warnings": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["status", "blockers", "warnings"],
        },
    },
    "required": [
        "schema_version",
        "summary",
        "sources",
        "work_items",
        "non_code_requirements",
        "deferred_or_excluded",
        "unresolved_questions",
        "seed_assessment",
    ],
}


# ============================================================
# PATH / BOUNDARY VALIDATION
# ============================================================

ALLOWED_EXACT_PATHS = {
    "Docs/GDD/No_Safe_Circle_GDD.md",
    "Assignment6GER/README_Assignment6.md",
    "GoalOrientedAgent/outputs/goal_analysis.json",
    "GoalOrientedAgent/outputs/next_goal_selection.json",
}

ALLOWED_PREFIXES = (
    "Assets/",
    "ProjectSettings/",
)

FORBIDDEN_PREFIXES = (
    "AgentCrew/",
    "DynamicContentPipeline/",
)


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _is_allowed_review_path(value: str) -> bool:
    path = _normalize_path(value)
    if path in ALLOWED_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def _is_forbidden_path(value: str) -> bool:
    path = _normalize_path(value)
    return any(path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)


def sanitize_forbidden_evidence(payload: dict[str, Any]) -> list[str]:
    """
    Remove evidence from explicitly forbidden repository areas before semantic
    validation.

    This is a recovery boundary, not permission for the model to inspect those
    paths. The prompt still forbids them. We preserve a warning describing what
    was removed, then validate the remaining evidence normally.

    If removing forbidden evidence leaves an implemented/partial item without
    valid current-project evidence, normal semantic validation will still fail.
    """
    removed: list[str] = []

    sources = payload.setdefault("sources", {})

    history = sources.get("historical_sources_reviewed", [])
    clean_history = []
    for value in history:
        if _is_forbidden_path(str(value)):
            removed.append(str(value))
        else:
            clean_history.append(value)
    sources["historical_sources_reviewed"] = clean_history

    reviewed = sources.get("files_reviewed", [])
    clean_reviewed = []
    for value in reviewed:
        if _is_forbidden_path(str(value)):
            removed.append(str(value))
        else:
            clean_reviewed.append(value)
    sources["files_reviewed"] = clean_reviewed

    for item in payload.get("work_items", []):
        evidence_list = item.get("repository_evidence", [])
        clean_evidence = []
        for evidence in evidence_list:
            path = str(evidence.get("path", ""))
            if _is_forbidden_path(path):
                removed.append(path)
            else:
                clean_evidence.append(evidence)
        item["repository_evidence"] = clean_evidence

    if removed:
        unique_removed = sorted(set(removed))
        seed = payload.setdefault(
            "seed_assessment",
            {"status": "ready_with_warnings", "blockers": [], "warnings": []},
        )
        warnings = seed.setdefault("warnings", [])
        warning = (
            "Reconciliation model referenced forbidden source path(s); "
            "the orchestrator removed them before validation: "
            + ", ".join(unique_removed)
        )
        if warning not in warnings:
            warnings.append(warning)

        if seed.get("status") == "ready":
            seed["status"] = "ready_with_warnings"

        return unique_removed

    return []


def validate_reviewed_paths(payload: dict[str, Any]) -> None:
    reviewed = payload.get("sources", {}).get("files_reviewed", [])
    violations = [
        str(path)
        for path in reviewed
        if not _is_allowed_review_path(str(path))
    ]
    if violations:
        raise RuntimeError(
            "Reconciliation output reports reviewing paths outside the "
            f"approved boundary: {violations}"
        )

    historical = payload.get("sources", {}).get(
        "historical_sources_reviewed", []
    )
    invalid_history = [
        str(path)
        for path in historical
        if _normalize_path(str(path)) not in ALLOWED_EXACT_PATHS
        or _normalize_path(str(path))
        == "Docs/GDD/No_Safe_Circle_GDD.md"
    ]
    if invalid_history:
        raise RuntimeError(
            "historical_sources_reviewed contains unsupported paths: "
            f"{invalid_history}"
        )


# ============================================================
# STRUCTURAL REPAIR — DANGLING DEPENDENCY REFERENCES
# ============================================================

def find_missing_dependency_references(
    payload: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    keys = {
        str(item.get("key", ""))
        for item in payload.get("work_items", [])
    }

    missing: dict[str, list[dict[str, str]]] = {}

    for item in payload.get("work_items", []):
        owner_key = str(item.get("key", ""))
        owner_title = str(item.get("title", ""))
        for dep in item.get("depends_on", []):
            dep_key = str(dep.get("key", ""))
            if dep_key and dep_key not in keys:
                missing.setdefault(dep_key, []).append(
                    {
                        "owner_key": owner_key,
                        "owner_title": owner_title,
                        "reason": str(dep.get("reason", "")),
                        "evidence": str(dep.get("evidence", "")),
                    }
                )

    return missing


def run_missing_dependency_repair_agent(
    payload: dict[str, Any],
    missing: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    existing_outline = [
        {
            "key": item.get("key"),
            "title": item.get("title"),
            "kind": item.get("kind"),
            "parent_key": item.get("parent_key"),
            "repository_state": item.get("repository_state"),
            "graph_status": item.get("graph_status"),
        }
        for item in payload.get("work_items", [])
    ]

    compact_context = {
        "missing_dependency_references": missing,
        "existing_work_items": existing_outline,
        "summary": payload.get("summary", {}),
        "sources": {
            "gdd": payload.get("sources", {}).get("gdd", ""),
            "code_root": payload.get("sources", {}).get("code_root", ""),
            "files_reviewed": payload.get("sources", {}).get(
                "files_reviewed", []
            ),
        },
    }

    prompt = f"""
You are the read-only STRUCTURAL REFINER for the No Safe Circle
Reconciliation Agent.

The main reconciliation completed, but deterministic validation found formal
dependencies whose keys do not exist in work_items.

Repair ONLY those dangling dependency references.

You may use Read, Glob, and Grep to verify the current GDD/current project.

Primary truth:
- Docs/GDD/No_Safe_Circle_GDD.md
- Assets/
- ProjectSettings/ only when relevant

Explicitly forbidden:
- AgentCrew/
- DynamicContentPipeline/

Rules:
1. If a missing dependency key represents real required/supporting work that
   should exist in the graph, return a complete work item for that exact key.
2. Prefer adding the omitted work item when the dependency itself is valid.
3. Remove a dependency only when the original dependency relationship was
   incorrect or too speculative to be formalized.
4. Any added work item's parent_key must reference an EXISTING feature key.
5. Added work items may depend only on existing artifact/implementation keys
   or on other work items added in this same repair.
6. Do not create game design, lore, encounters, room layouts, mechanics, or
   speculative backlog.
7. Do not change unrelated work.
8. Current repository evidence is required for implemented/partial claims.
9. Added work items must classify `execution_scope` separately from design decomposition and provide `execution_reason`. Use `unknown` rather than guessing when task handoff size cannot be established from this bounded repair.
10. Return only the JSON required by the supplied schema.

Compact reconciliation context:
{json.dumps(compact_context, indent=2, ensure_ascii=False)}
""".strip()

    compact_schema = json.dumps(
        MISSING_DEPENDENCY_REPAIR_SCHEMA,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    command = [
        "claude",
        "-p",
        "--model",
        REPAIR_MODEL,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(REPAIR_MAX_TURNS),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        "Edit,Write,mcp__*",
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print()
    print(
        "Structural validation found dangling dependency key(s): "
        + ", ".join(sorted(missing))
    )
    print(
        "Running targeted reconciliation refiner instead of repeating the "
        "full repository reconciliation."
    )

    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=REPAIR_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Targeted reconciliation structural repair exceeded the "
            f"{REPAIR_TIMEOUT_SECONDS}-second timeout."
        ) from exc

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            "Targeted reconciliation structural repair failed with exit "
            f"code {process.returncode}.\n{error_text}"
        )

    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Targeted reconciliation structural repair did not return "
            "valid Claude JSON."
        ) from exc

    structured_output = envelope.get("structured_output")
    if not isinstance(structured_output, dict):
        raise RuntimeError(
            "Targeted reconciliation structural repair did not return "
            "structured_output."
        )

    return structured_output


def apply_missing_dependency_repair(
    payload: dict[str, Any],
    missing: dict[str, list[dict[str, str]]],
    repair: dict[str, Any],
) -> None:
    existing_keys = {
        str(item.get("key", ""))
        for item in payload.get("work_items", [])
    }
    missing_keys = set(missing)

    added_keys: set[str] = set()

    for item in repair.get("work_items_to_add", []):
        key = str(item.get("key", ""))

        if key not in missing_keys:
            raise RuntimeError(
                "Structural refiner attempted to add unrelated work item "
                f"{key!r}."
            )
        if key in existing_keys or key in added_keys:
            raise RuntimeError(
                f"Structural refiner returned duplicate work item {key!r}."
            )

        payload.setdefault("work_items", []).append(item)
        added_keys.add(key)

    for removal in repair.get("dependencies_to_remove", []):
        owner_key = str(removal.get("owner_key", ""))
        dependency_key = str(removal.get("dependency_key", ""))

        if dependency_key not in missing_keys:
            raise RuntimeError(
                "Structural refiner attempted to remove unrelated dependency "
                f"{dependency_key!r}."
            )

        owner = next(
            (
                item
                for item in payload.get("work_items", [])
                if str(item.get("key", "")) == owner_key
            ),
            None,
        )
        if owner is None:
            raise RuntimeError(
                "Structural refiner referenced missing dependency owner "
                f"{owner_key!r}."
            )

        before = len(owner.get("depends_on", []))
        owner["depends_on"] = [
            dep
            for dep in owner.get("depends_on", [])
            if str(dep.get("key", "")) != dependency_key
        ]
        if len(owner["depends_on"]) == before:
            raise RuntimeError(
                "Structural refiner tried to remove dependency "
                f"{dependency_key!r} from {owner_key!r}, but it was not "
                "present."
            )

    seed = payload.setdefault(
        "seed_assessment",
        {"status": "ready_with_warnings", "blockers": [], "warnings": []},
    )
    warnings = seed.setdefault("warnings", [])
    warning = (
        "Deterministic validation found dangling dependency references and "
        "a targeted read-only reconciliation refinement repaired them: "
        + ", ".join(sorted(missing_keys))
    )
    if warning not in warnings:
        warnings.append(warning)
    if seed.get("status") == "ready":
        seed["status"] = "ready_with_warnings"


def repair_missing_dependency_references(
    payload: dict[str, Any],
) -> None:
    for _ in range(MAX_STRUCTURAL_REPAIR_PASSES):
        missing = find_missing_dependency_references(payload)
        if not missing:
            return

        repair = run_missing_dependency_repair_agent(payload, missing)
        apply_missing_dependency_repair(payload, missing, repair)
        sanitize_forbidden_evidence(payload)

    remaining = find_missing_dependency_references(payload)
    if remaining:
        raise RuntimeError(
            "Targeted structural repair could not resolve dangling "
            "dependency key(s): "
            + ", ".join(sorted(remaining))
        )


# ============================================================
# SEMANTIC VALIDATION
# ============================================================

def _validate_unique_keys(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("key", "")).strip()
        if not key:
            raise RuntimeError("Every work item must have a non-empty key.")
        if key in by_key:
            raise RuntimeError(f"Duplicate work item key: {key!r}")
        by_key[key] = item
    return by_key


def _validate_root(items_by_key: dict[str, dict[str, Any]]) -> None:
    root = items_by_key.get("no-safe-circle")
    if root is None:
        raise RuntimeError(
            "The reconciliation must contain root key 'no-safe-circle'."
        )
    if root.get("kind") != "feature":
        raise RuntimeError("'no-safe-circle' root must be kind=feature.")
    if root.get("parent_key") != "":
        raise RuntimeError("'no-safe-circle' root must have parent_key=''.")
    roots = [
        item.get("key")
        for item in items_by_key.values()
        if item.get("parent_key") == ""
    ]
    if roots != ["no-safe-circle"]:
        raise RuntimeError(
            "Exactly one root is allowed and it must be 'no-safe-circle'. "
            f"Found roots: {roots}"
        )


def _validate_parent_links(items_by_key: dict[str, dict[str, Any]]) -> None:
    for key, item in items_by_key.items():
        if key == "no-safe-circle":
            continue
        parent_key = item.get("parent_key")
        if not parent_key:
            raise RuntimeError(f"{key!r} must have a parent_key.")
        if parent_key == key:
            raise RuntimeError(f"{key!r} cannot parent itself.")
        parent = items_by_key.get(str(parent_key))
        if parent is None:
            raise RuntimeError(
                f"{key!r} references missing parent {parent_key!r}."
            )
        if parent.get("kind") != "feature":
            raise RuntimeError(
                f"{key!r} parent {parent_key!r} must be kind=feature."
            )

    # Parent-cycle detection.
    for start in items_by_key:
        seen: set[str] = set()
        current = start
        while current:
            if current in seen:
                raise RuntimeError(
                    f"Parent hierarchy contains a cycle involving {current!r}."
                )
            seen.add(current)
            current = str(
                items_by_key.get(current, {}).get("parent_key", "")
            )


def _validate_dependency_links(items_by_key: dict[str, dict[str, Any]]) -> None:
    adjacency: dict[str, list[str]] = {}

    for key, item in items_by_key.items():
        deps = item.get("depends_on", [])

        # Feature nodes are not executable and will never be returned by
        # taskcontrol ready, but they MAY still depend on concrete artifact or
        # implementation work. This records real prerequisite relationships
        # without making the feature itself executable.
        dep_keys: list[str] = []
        for dep in deps:
            dep_key = str(dep.get("key", ""))
            if dep_key == key:
                raise RuntimeError(f"{key!r} cannot depend on itself.")
            target = items_by_key.get(dep_key)
            if target is None:
                raise RuntimeError(
                    f"{key!r} depends on missing work key {dep_key!r}."
                )
            if target.get("kind") == "feature":
                raise RuntimeError(
                    f"{key!r} depends on feature {dep_key!r}. Dependencies "
                    "must target artifact/implementation work."
                )
            if dep_key in dep_keys:
                raise RuntimeError(
                    f"{key!r} lists duplicate dependency {dep_key!r}."
                )
            dep_keys.append(dep_key)
        adjacency[key] = dep_keys

    # Dependency-cycle detection.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise RuntimeError(
                f"Dependency graph contains a cycle involving {node!r}."
            )
        visiting.add(node)
        for dep in adjacency.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for key in adjacency:
        visit(key)


def _validate_evidence_and_status(items_by_key: dict[str, dict[str, Any]]) -> None:
    for key, item in items_by_key.items():
        basis = item.get("basis")
        gdd_evidence = item.get("gdd_evidence", [])
        repo_state = item.get("repository_state")
        repo_evidence = item.get("repository_evidence", [])
        graph_status = item.get("graph_status")
        kind = item.get("kind")

        if (
            key != "no-safe-circle"
            and basis in ("direct_gdd", "derived_required_foundation")
            and not gdd_evidence
        ):
            raise RuntimeError(
                f"{key!r} requires at least one GDD evidence entry."
            )

        if repo_state in ("implemented", "partial") and not repo_evidence:
            raise RuntimeError(
                f"{key!r} is {repo_state!r} but has no repository evidence."
            )

        if graph_status == "complete":
            if kind == "implementation" and repo_state != "implemented":
                raise RuntimeError(
                    f"{key!r} implementation cannot be complete while "
                    f"repository_state={repo_state!r}."
                )
            if kind == "artifact" and repo_state != "implemented":
                raise RuntimeError(
                    f"{key!r} artifact cannot be complete without an "
                    "implemented/approved current artifact."
                )
            if repo_state in ("missing", "partial", "unknown"):
                raise RuntimeError(
                    f"{key!r} cannot be complete while "
                    f"repository_state={repo_state!r}."
                )

        for evidence in repo_evidence:
            path = str(evidence.get("path", ""))
            if not _is_allowed_review_path(path):
                raise RuntimeError(
                    f"{key!r} contains repository evidence outside the "
                    f"approved boundary: {path!r}"
                )


def ensure_execution_scope_defaults(payload: dict[str, Any]) -> list[str]:
    """
    Upgrade legacy reconciliation candidates that predate execution_scope.

    Features and already-complete work are not execution candidates. Open
    implementation/artifact work is conservatively marked unknown until an
    execution-scope audit or human review classifies it.
    """
    upgraded: list[str] = []
    for item in payload.get("work_items", []):
        if item.get("execution_scope"):
            if "execution_reason" not in item:
                item["execution_reason"] = "Execution scope supplied without an explicit reason in a legacy candidate."
            continue

        kind = item.get("kind")
        status = item.get("graph_status")
        if kind == "feature" or status == "complete":
            item["execution_scope"] = "not_applicable"
            item["execution_reason"] = "Organizational or already-complete work is not awaiting an implementation-agent handoff."
        else:
            item["execution_scope"] = "unknown"
            item["execution_reason"] = "Legacy candidate predates execution-scope classification; verification or human review is required."
        upgraded.append(str(item.get("key", "")))
    return upgraded


def _validate_execution_scope(items_by_key: dict[str, dict[str, Any]]) -> None:
    allowed = {
        "single_agent",
        "needs_execution_decomposition",
        "human_integration_required",
        "not_applicable",
        "unknown",
    }
    for key, item in items_by_key.items():
        scope = str(item.get("execution_scope", ""))
        reason = str(item.get("execution_reason", "")).strip()
        kind = item.get("kind")
        status = item.get("graph_status")

        if scope not in allowed:
            raise RuntimeError(f"{key!r} has invalid execution_scope={scope!r}.")
        if not reason:
            raise RuntimeError(f"{key!r} requires a non-empty execution_reason.")
        if kind == "feature" and scope != "not_applicable":
            raise RuntimeError(
                f"Feature {key!r} must use execution_scope='not_applicable'."
            )
        if status == "complete" and scope not in {"not_applicable", "single_agent"}:
            raise RuntimeError(
                f"Completed work {key!r} cannot require future execution decomposition/integration."
            )
        if (
            kind in {"implementation", "artifact"}
            and status == "open"
            and scope == "not_applicable"
        ):
            raise RuntimeError(
                f"Open executable work {key!r} cannot use execution_scope='not_applicable'."
            )


def _validate_unresolved_refs(
    payload: dict[str, Any],
    items_by_key: dict[str, dict[str, Any]],
) -> None:
    for question in payload.get("unresolved_questions", []):
        for key in question.get("affects_keys", []):
            if key not in items_by_key:
                raise RuntimeError(
                    "unresolved_questions references unknown work key "
                    f"{key!r}."
                )


def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_execution_scope_defaults(payload)
    items = payload.get("work_items", [])
    if not isinstance(items, list) or not items:
        raise RuntimeError("work_items must be a non-empty list.")

    items_by_key = _validate_unique_keys(items)
    _validate_root(items_by_key)
    _validate_parent_links(items_by_key)
    _validate_dependency_links(items_by_key)
    _validate_evidence_and_status(items_by_key)
    _validate_execution_scope(items_by_key)
    _validate_unresolved_refs(payload, items_by_key)
    validate_reviewed_paths(payload)


# ============================================================
# CLAUDE INVOCATION
# ============================================================

def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Reconciliation prompt not found: {PROMPT_PATH}"
        )
    return PROMPT_PATH.read_text(encoding="utf-8-sig")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def create_run_paths() -> dict[str, Any]:
    """
    Create a unique append-only output directory for this reconciliation run.

    Snapshot files inside a completed run are never reused by later runs.
    `outputs/LATEST.json` is only a mutable convenience pointer and is not
    itself reconciliation truth.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id

    if run_dir.exists():
        raise RuntimeError(
            f"Refusing to reuse reconciliation run directory: {run_dir}"
        )

    run_dir.mkdir(parents=True, exist_ok=False)

    return {
        "run_id": run_id,
        "created_at_utc": utc_now_iso(),
        "run_dir": run_dir,
        "raw": run_dir / "reconciliation.raw.json",
        "json": run_dir / "reconciliation.json",
        "markdown": run_dir / "RECONCILIATION.md",
        "delta_json": run_dir / "PROPOSED_GRAPH_DELTA.json",
        "delta_markdown": run_dir / "PROPOSED_GRAPH_DELTA.md",
    }


def save_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(
            f"Refusing to overwrite immutable reconciliation artifact: {path}"
        )
    save_json(path, value)


def save_new_text(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(
            f"Refusing to overwrite immutable reconciliation artifact: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_reconciliation_agent() -> dict[str, Any]:
    prompt = load_prompt()

    compact_schema = json.dumps(
        RECONCILIATION_SCHEMA,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    command = [
        "claude",
        "-p",
        "--model",
        MODEL,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(MAX_TURNS),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        "Edit,Write,mcp__*",
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print()
    print("=" * 72)
    print("Starting agent: No Safe Circle Reconciliation Agent")
    print(f"Model: {MODEL}")
    print("Tools: Read,Glob,Grep (read-only, no MCP)")
    print(f"Max turns: {MAX_TURNS}")
    print("=" * 72)
    print(
        "Claude will reconcile the current GDD and project into a coarse "
        "human-reviewable work hierarchy."
    )

    started = time.monotonic()

    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Reconciliation agent exceeded the "
            f"{TIMEOUT_SECONDS}-second timeout."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"Reconciliation agent failed with exit code "
            f"{process.returncode}.\n{error_text}"
        )

    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Reconciliation agent returned output that was not valid "
            "Claude JSON."
        ) from exc

    structured_output = envelope.get("structured_output")
    if not isinstance(structured_output, dict):
        raise RuntimeError(
            "Reconciliation agent did not return structured_output."
        )

    print(f"Completed reconciliation agent in {duration} seconds.")
    return structured_output


# ============================================================
# RECONCILIATION SNAPSHOT / PROPOSED GRAPH DELTA
# ============================================================

def build_proposed_graph_delta(
    payload: dict[str, Any],
    run_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    """
    Describe what this reconciliation proposes relative to the persistent
    graph WITHOUT changing the graph.

    Milestone 1/taskcontrol does not exist yet in the current bootstrap state, so
    this function deliberately does not invent a YAML parser or graph-mutation
    policy inside the Reconciliation Agent.

    Before Tasks/*.yaml exists, every reconciled work item is a proposed seed
    record. Once Tasks/*.yaml exists, taskcontrol must own the deterministic
    snapshot-vs-graph diff and application workflow.
    """
    task_files = sorted(TASKS_DIR.glob("*.yaml")) if TASKS_DIR.exists() else []
    work_items = payload.get("work_items", [])

    if not task_files:
        return {
            "schema_version": "1.0",
            "reconciliation_run_id": run_id,
            "created_at_utc": created_at_utc,
            "status": "bootstrap_seed_proposal",
            "persistent_graph_present": False,
            "persistent_graph_mutated": False,
            "summary": (
                "No persistent Tasks/*.yaml graph exists yet. This snapshot "
                "proposes bootstrap seed records only; human approval and the "
                "deterministic Work Graph Seeder are required before any "
                "persistent task state is created."
            ),
            "proposed_seed_records": [
                {
                    "reconciliation_key": item.get("key"),
                    "title": item.get("title"),
                    "kind": item.get("kind"),
                    "proposed_status": item.get("graph_status"),
                    "execution_scope": item.get("execution_scope", "unknown"),
                    "parent_reconciliation_key": item.get("parent_key"),
                    "depends_on_reconciliation_keys": [
                        dep.get("key")
                        for dep in item.get("depends_on", [])
                    ],
                }
                for item in work_items
            ],
            "proposed_changes": [],
            "conflicts": [],
            "next_action": "human_review_then_seed",
        }

    return {
        "schema_version": "1.0",
        "reconciliation_run_id": run_id,
        "created_at_utc": created_at_utc,
        "status": "taskcontrol_diff_required",
        "persistent_graph_present": True,
        "persistent_graph_mutated": False,
        "summary": (
            "A persistent Tasks/*.yaml graph already exists. The "
            "Reconciliation Agent does not rewrite it. This snapshot must be "
            "compared against the graph by deterministic taskcontrol reconciliation "
            "diff logic before any approved graph delta is applied."
        ),
        "task_files_observed": [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in task_files
        ],
        "proposed_seed_records": [],
        "proposed_changes": [],
        "conflicts": [],
        "next_action": "taskcontrol_reconciliation_diff",
    }


def render_graph_delta_markdown(delta: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Proposed Persistent-Graph Delta")
    lines.append("")
    lines.append(
        "> This is a proposal generated from an immutable reconciliation "
        "snapshot. It does not modify `Tasks/*.yaml`."
    )
    lines.append("")
    lines.append(
        f"- **Reconciliation run:** `{delta.get('reconciliation_run_id', '')}`"
    )
    lines.append(f"- **Status:** `{delta.get('status', '')}`")
    lines.append(
        "- **Persistent graph mutated:** "
        f"`{str(delta.get('persistent_graph_mutated', False)).lower()}`"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(str(delta.get("summary", "")))
    lines.append("")

    seeds = delta.get("proposed_seed_records", [])
    if seeds:
        lines.append("## Proposed Bootstrap Seed Records")
        lines.append("")
        lines.append(
            "| Reconciliation key | Kind | Title | Proposed status | Execution | Parent | "
            "Depends on |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for item in seeds:
            deps = ", ".join(
                str(value)
                for value in item.get(
                    "depends_on_reconciliation_keys", []
                )
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(item.get("reconciliation_key")),
                        _cell(item.get("kind")),
                        _cell(item.get("title")),
                        _cell(item.get("proposed_status")),
                        _cell(item.get("execution_scope")),
                        _cell(item.get("parent_reconciliation_key")),
                        _cell(deps),
                    ]
                )
                + " |"
            )
        lines.append("")

    task_files = delta.get("task_files_observed", [])
    if task_files:
        lines.append("## Persistent Task Files Observed")
        lines.append("")
        for path in task_files:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append("## Next Action")
    lines.append("")
    lines.append(f"`{delta.get('next_action', '')}`")
    lines.append("")
    return "\n".join(lines)


def write_latest_pointer(run_paths: dict[str, Any]) -> None:
    pointer = {
        "schema_version": "1.0",
        "latest_successful_run_id": run_paths["run_id"],
        "created_at_utc": run_paths["created_at_utc"],
        "snapshot_directory": str(
            run_paths["run_dir"].relative_to(ROOT)
        ).replace("\\", "/"),
        "reconciliation_json": str(
            run_paths["json"].relative_to(ROOT)
        ).replace("\\", "/"),
        "reconciliation_markdown": str(
            run_paths["markdown"].relative_to(ROOT)
        ).replace("\\", "/"),
        "proposed_graph_delta_json": str(
            run_paths["delta_json"].relative_to(ROOT)
        ).replace("\\", "/"),
        "proposed_graph_delta_markdown": str(
            run_paths["delta_markdown"].relative_to(ROOT)
        ).replace("\\", "/"),
    }

    # LATEST.json is intentionally mutable metadata. It is not project truth;
    # the immutable run directory is.
    save_json(LATEST_POINTER_PATH, pointer)


# ============================================================
# MARKDOWN RENDERING
# ============================================================

def _cell(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", r"\|").replace("\n", " ").strip()


def _deps_text(item: dict[str, Any]) -> str:
    deps = item.get("depends_on", [])
    if not deps:
        return ""
    return ", ".join(str(dep.get("key", "")) for dep in deps)


def _gdd_basis_text(item: dict[str, Any]) -> str:
    refs = [
        str(e.get("reference", ""))
        for e in item.get("gdd_evidence", [])
        if e.get("reference")
    ]
    if refs:
        return "; ".join(refs)
    return item.get("basis", "")


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    sources = payload.get("sources", {})
    seed = payload.get("seed_assessment", {})
    work_items = payload.get("work_items", [])

    lines: list[str] = []
    lines.append("# No Safe Circle — Reconciliation")
    lines.append("")
    lines.append(
        "> Human-review artifact. This file does not itself become the "
        "persistent task graph."
    )
    lines.append("")
    lines.append("## Seed Assessment")
    lines.append("")
    lines.append(f"**Status:** `{_cell(seed.get('status', ''))}`")
    lines.append("")

    blockers = seed.get("blockers", [])
    if blockers:
        lines.append("**Blockers:**")
        for value in blockers:
            lines.append(f"- {_cell(value)}")
        lines.append("")

    warnings = seed.get("warnings", [])
    if warnings:
        lines.append("**Warnings:**")
        for value in warnings:
            lines.append(f"- {_cell(value)}")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("### Desired State")
    lines.append("")
    lines.append(_cell(summary.get("desired_state_summary", "")))
    lines.append("")
    lines.append("### Current State")
    lines.append("")
    lines.append(_cell(summary.get("current_state_summary", "")))
    lines.append("")

    findings = summary.get("major_findings", [])
    if findings:
        lines.append("### Major Findings")
        lines.append("")
        for finding in findings:
            lines.append(f"- {_cell(finding)}")
        lines.append("")

    lines.append("## Reconciliation Table")
    lines.append("")
    lines.append(
        "| Key | Parent | Kind | Title | GDD basis | Repo state | "
        "Graph status | Depends on | Decomposition | Execution | Confidence |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )

    for item in work_items:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("key")),
                    _cell(item.get("parent_key")),
                    _cell(item.get("kind")),
                    _cell(item.get("title")),
                    _cell(_gdd_basis_text(item)),
                    _cell(item.get("repository_state")),
                    _cell(item.get("graph_status")),
                    _cell(_deps_text(item)),
                    _cell(item.get("decomposition_state")),
                    _cell(item.get("execution_scope")),
                    _cell(item.get("confidence")),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Detailed Evidence")
    lines.append("")

    for item in work_items:
        lines.append(
            f"### `{_cell(item.get('key'))}` — {_cell(item.get('title'))}"
        )
        lines.append("")
        lines.append(
            f"- **Kind:** `{_cell(item.get('kind'))}`"
        )
        lines.append(
            f"- **Type:** `{_cell(item.get('type'))}`"
        )
        lines.append(
            f"- **Parent:** `{_cell(item.get('parent_key'))}`"
        )
        lines.append(
            f"- **Basis:** `{_cell(item.get('basis'))}` / "
            f"`{_cell(item.get('source_scope'))}`"
        )
        lines.append(
            f"- **Repository state:** "
            f"`{_cell(item.get('repository_state'))}`"
        )
        lines.append(
            f"- **Proposed graph status:** "
            f"`{_cell(item.get('graph_status'))}`"
        )
        lines.append(
            f"- **Decomposition:** "
            f"`{_cell(item.get('decomposition_state'))}` — "
            f"{_cell(item.get('decomposition_reason'))}"
        )
        lines.append(
            f"- **Execution scope:** `{_cell(item.get('execution_scope'))}` — "
            f"{_cell(item.get('execution_reason'))}"
        )
        lines.append(
            f"- **Confidence:** `{_cell(item.get('confidence'))}`"
        )
        lines.append("")

        gdd_evidence = item.get("gdd_evidence", [])
        if gdd_evidence:
            lines.append("**GDD evidence**")
            lines.append("")
            for evidence in gdd_evidence:
                lines.append(
                    f"- `{_cell(evidence.get('reference'))}` — "
                    f"{_cell(evidence.get('requirement'))}"
                )
            lines.append("")

        repo_evidence = item.get("repository_evidence", [])
        if repo_evidence:
            lines.append("**Repository evidence**")
            lines.append("")
            for evidence in repo_evidence:
                lines.append(
                    f"- `{_cell(evidence.get('path'))}` "
                    f"(`{_cell(evidence.get('evidence_type'))}`) — "
                    f"{_cell(evidence.get('observation'))}"
                )
            lines.append("")

        deps = item.get("depends_on", [])
        if deps:
            lines.append("**Dependencies**")
            lines.append("")
            for dep in deps:
                lines.append(
                    f"- `{_cell(dep.get('key'))}` — "
                    f"{_cell(dep.get('reason'))} "
                    f"Evidence/basis: {_cell(dep.get('evidence'))}"
                )
            lines.append("")

        if item.get("notes"):
            lines.append(f"**Notes:** {_cell(item.get('notes'))}")
            lines.append("")

    non_code = payload.get("non_code_requirements", [])
    lines.append("## Non-Code Requirements")
    lines.append("")
    if non_code:
        for item in non_code:
            lines.append(
                f"- **[{_cell(item.get('status'))}] "
                f"{_cell(item.get('title'))}:** "
                f"{_cell(item.get('evidence'))}"
            )
    else:
        lines.append("(none)")
    lines.append("")

    deferred = payload.get("deferred_or_excluded", [])
    lines.append("## Deferred / Excluded")
    lines.append("")
    if deferred:
        for item in deferred:
            lines.append(
                f"- **[{_cell(item.get('classification'))}] "
                f"{_cell(item.get('title'))}:** "
                f"{_cell(item.get('reason'))}"
            )
    else:
        lines.append("(none)")
    lines.append("")

    unresolved = payload.get("unresolved_questions", [])
    lines.append("## Unresolved Questions")
    lines.append("")
    if unresolved:
        for item in unresolved:
            affects = ", ".join(item.get("affects_keys", []))
            lines.append(f"### {_cell(item.get('question'))}")
            lines.append("")
            lines.append(f"- **Affects:** {_cell(affects)}")
            lines.append(
                f"- **Why unresolved:** "
                f"{_cell(item.get('why_unresolved'))}"
            )
            lines.append(
                f"- **Recommended resolution:** "
                f"`{_cell(item.get('recommended_resolution'))}`"
            )
            lines.append("")
    else:
        lines.append("(none)")
        lines.append("")

    lines.append("## Sources")
    lines.append("")
    lines.append(f"- **GDD:** `{_cell(sources.get('gdd'))}`")
    lines.append(f"- **Code root:** `{_cell(sources.get('code_root'))}`")

    history = sources.get("historical_sources_reviewed", [])
    if history:
        lines.append("- **Historical evidence reviewed:**")
        for path in history:
            lines.append(f"  - `{_cell(path)}`")

    lines.append("")
    lines.append("## Next Step")
    lines.append("")
    lines.append(
        "Treat this file as an immutable point-in-time reconciliation "
        "snapshot. Do not edit it to reflect later implementation progress. "
        "Review the accompanying `PROPOSED_GRAPH_DELTA.md`; approved changes "
        "belong in the persistent `Tasks/*.yaml` graph, not back in this "
        "snapshot."
    )
    lines.append("")

    return "\n".join(lines)


def save_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(payload), encoding="utf-8")


# ============================================================
# TERMINAL SUMMARY
# ============================================================

def print_summary(
    payload: dict[str, Any],
    run_paths: dict[str, Any],
    delta: dict[str, Any],
) -> None:
    items = payload.get("work_items", [])
    by_kind = {
        kind: [item for item in items if item.get("kind") == kind]
        for kind in ("feature", "artifact", "implementation")
    }
    by_status = {
        status: [
            item for item in items if item.get("graph_status") == status
        ]
        for status in ("complete", "open")
    }
    future_decomposition = [
        item
        for item in items
        if item.get("decomposition_state")
        == "needs_future_decomposition"
    ]
    execution_decomposition = [
        item for item in items
        if item.get("execution_scope") == "needs_execution_decomposition"
    ]
    human_integration = [
        item for item in items
        if item.get("execution_scope") == "human_integration_required"
    ]
    unknown_execution = [
        item for item in items
        if item.get("execution_scope") == "unknown"
    ]
    unresolved = payload.get("unresolved_questions", [])

    print()
    print("=" * 72)
    print("NO SAFE CIRCLE -- RECONCILIATION SUMMARY")
    print("=" * 72)
    print(f"Work items: {len(items)}")
    print(f"  Features: {len(by_kind['feature'])}")
    print(f"  Artifacts: {len(by_kind['artifact'])}")
    print(f"  Implementations: {len(by_kind['implementation'])}")
    print(f"  Proposed complete: {len(by_status['complete'])}")
    print(f"  Proposed open: {len(by_status['open'])}")
    print(
        "  Needs future progressive decomposition: "
        f"{len(future_decomposition)}"
    )
    print(f"  Needs execution decomposition: {len(execution_decomposition)}")
    print(f"  Human integration required: {len(human_integration)}")
    print(f"  Unknown execution scope: {len(unknown_execution)}")
    print(f"Unresolved questions: {len(unresolved)}")
    print(
        "Seed assessment: "
        f"{payload.get('seed_assessment', {}).get('status')}"
    )
    print()
    print(f"Run ID: {run_paths['run_id']}")
    print(f"Saved immutable snapshot directory: {run_paths['run_dir'].relative_to(ROOT)}")
    print(f"Saved: {run_paths['json'].relative_to(ROOT)}")
    print(f"Saved: {run_paths['markdown'].relative_to(ROOT)}")
    print(f"Saved: {run_paths['delta_json'].relative_to(ROOT)}")
    print(f"Saved: {run_paths['delta_markdown'].relative_to(ROOT)}")
    print(f"Updated convenience pointer: {LATEST_POINTER_PATH.relative_to(ROOT)}")
    print(f"Graph delta status: {delta.get('status')}")
    print()
    print("The reconciliation snapshot did NOT mutate Tasks/*.yaml.")
    print("=" * 72)


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    run_paths: dict[str, Any] | None = None

    try:
        # Each invocation gets its own append-only run directory. A later run
        # can never overwrite the evidence from this run.
        run_paths = create_run_paths()

        payload = run_reconciliation_agent()

        # Save Claude's unsanitized structured output before semantic
        # validation. If validation/refinement fails, the expensive model run
        # remains inspectable inside this unique run directory.
        save_new_json(run_paths["raw"], payload)

        removed_forbidden = sanitize_forbidden_evidence(payload)
        if removed_forbidden:
            print(
                "Warning: removed forbidden reconciliation evidence before "
                "semantic validation: "
                + ", ".join(removed_forbidden)
            )

        # Referential-integrity defects are repairable model-output mistakes.
        # Run a small targeted read-only refinement instead of throwing away
        # the completed full reconciliation.
        repair_missing_dependency_references(payload)

        run_semantic_validation(payload)

        delta = build_proposed_graph_delta(
            payload,
            run_id=run_paths["run_id"],
            created_at_utc=run_paths["created_at_utc"],
        )

        save_new_json(run_paths["json"], payload)
        save_new_text(run_paths["markdown"], render_markdown(payload))
        save_new_json(run_paths["delta_json"], delta)
        save_new_text(
            run_paths["delta_markdown"],
            render_graph_delta_markdown(delta),
        )

        # Only a fully validated successful reconciliation becomes "latest."
        write_latest_pointer(run_paths)
        write_current_view(
            source_reconciliation_run_id=run_paths["run_id"],
            status="unverified_reconciliation",
            candidate_json=run_paths["json"],
            candidate_markdown=run_paths["markdown"],
            delta_json=run_paths["delta_json"],
            delta_markdown=run_paths["delta_markdown"],
        )

        print_summary(payload, run_paths, delta)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("RECONCILIATION AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        if run_paths is not None:
            print(
                "Run directory preserved: "
                f"{run_paths['run_dir'].relative_to(ROOT)}",
                file=sys.stderr,
            )
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
