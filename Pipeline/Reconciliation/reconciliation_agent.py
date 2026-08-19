from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "Pipeline" / "Reconciliation"
PROMPT_PATH = AGENT_ROOT / "prompts" / "reconcile.md"
OUTPUT_DIR = AGENT_ROOT / "outputs"
JSON_OUTPUT_PATH = OUTPUT_DIR / "reconciliation.json"
MARKDOWN_OUTPUT_PATH = OUTPUT_DIR / "RECONCILIATION.md"

MODEL = os.environ.get("RECONCILIATION_MODEL", "sonnet")
TIMEOUT_SECONDS = int(os.environ.get("RECONCILIATION_TIMEOUT_SECONDS", "1800"))
MAX_TURNS = int(os.environ.get("RECONCILIATION_MAX_TURNS", "50"))


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
        "confidence",
        "notes",
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


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _is_allowed_review_path(value: str) -> bool:
    path = _normalize_path(value)
    if path in ALLOWED_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


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

        if item.get("kind") == "feature" and deps:
            raise RuntimeError(
                f"Feature node {key!r} must not have executable dependencies."
            )

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
    items = payload.get("work_items", [])
    if not isinstance(items, list) or not items:
        raise RuntimeError("work_items must be a non-empty list.")

    items_by_key = _validate_unique_keys(items)
    _validate_root(items_by_key)
    _validate_parent_links(items_by_key)
    _validate_dependency_links(items_by_key)
    _validate_evidence_and_status(items_by_key)
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
        "Graph status | Depends on | Decomposition | Confidence |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|"
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
        "Human-review this reconciliation. After approval, use the "
        "approved records to seed the deterministic Milestone 1 "
        "`Tasks/*.yaml` graph. Do not automatically promote this output "
        "without review."
    )
    lines.append("")

    return "\n".join(lines)


def save_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(payload), encoding="utf-8")


# ============================================================
# TERMINAL SUMMARY
# ============================================================

def print_summary(payload: dict[str, Any]) -> None:
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
    print(f"Unresolved questions: {len(unresolved)}")
    print(
        "Seed assessment: "
        f"{payload.get('seed_assessment', {}).get('status')}"
    )
    print()
    print(f"Saved: {JSON_OUTPUT_PATH.relative_to(ROOT)}")
    print(f"Saved: {MARKDOWN_OUTPUT_PATH.relative_to(ROOT)}")
    print()
    print("Human review is required before seeding Tasks/*.yaml.")
    print("=" * 72)


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    try:
        payload = run_reconciliation_agent()
        run_semantic_validation(payload)

        save_json(JSON_OUTPUT_PATH, payload)
        save_markdown(MARKDOWN_OUTPUT_PATH, payload)

        print_summary(payload)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("RECONCILIATION AGENT FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
