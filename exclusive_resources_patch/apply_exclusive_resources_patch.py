from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected repository file not found: {p}")
    return p.read_text(encoding="utf-8")

def write(path: str, text: str) -> None:
    p = ROOT / path
    p.write_text(text, encoding="utf-8")

def replace_once(path: str, old: str, new: str, marker: str | None = None) -> None:
    text = read(path)
    if marker and marker in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    write(path, text.replace(old, new, 1))
    print(f"patched: {path}")

# ============================================================================
# reconciliation_agent.py
# ============================================================================

path = "Pipeline/Reconciliation/reconciliation_agent.py"

replace_once(
    path,
    '''DEPENDENCY_SCHEMA: dict[str, Any] = {
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
''',
    '''DEPENDENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "key": {"type": "string"},
        "reason": {"type": "string"},
        "evidence": {"type": "string"},
    },
    "required": ["key", "reason", "evidence"],
}

EXCLUSIVE_RESOURCE_SCHEMA: dict[str, Any] = {
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
''',
    marker="EXCLUSIVE_RESOURCE_SCHEMA: dict[str, Any]",
)

replace_once(
    path,
    '''        "depends_on": {
            "type": "array",
            "items": DEPENDENCY_SCHEMA,
        },
        "decomposition_state": {
''',
    '''        "depends_on": {
            "type": "array",
            "items": DEPENDENCY_SCHEMA,
        },
        "exclusive_resources": {
            "type": "array",
            "items": EXCLUSIVE_RESOURCE_SCHEMA,
        },
        "decomposition_state": {
''',
    marker='"exclusive_resources": {\n            "type": "array"',
)

replace_once(
    path,
    '''        "repository_evidence",
        "depends_on",
        "decomposition_state",
''',
    '''        "repository_evidence",
        "depends_on",
        "exclusive_resources",
        "decomposition_state",
''',
    marker='        "exclusive_resources",\n        "decomposition_state",',
)

replace_once(
    path,
    '''9. Added work items must classify `execution_scope` separately from design decomposition and provide `execution_reason`. Use `unknown` rather than guessing when task handoff size cannot be established from this bounded repair.
10. Return only the JSON required by the supplied schema.
''',
    '''9. Added work items must classify `execution_scope` separately from design decomposition and provide `execution_reason`. Use `unknown` rather than guessing when task handoff size cannot be established from this bounded repair.
10. Added work items must include `exclusive_resources`. Use an empty list unless a concrete shared write/integration resource is established by the current repository or approved architecture.
11. Return only the JSON required by the supplied schema.
''',
    marker="Added work items must include `exclusive_resources`",
)

replace_once(
    path,
    '''def _validate_unresolved_refs(
    payload: dict[str, Any],
    items_by_key: dict[str, dict[str, Any]],
) -> None:
''',
    '''def ensure_exclusive_resource_defaults(payload: dict[str, Any]) -> list[str]:
    # Upgrade legacy candidates that predate exclusive_resources.
    upgraded: list[str] = []
    for item in payload.get("work_items", []):
        if "exclusive_resources" in item:
            continue
        item["exclusive_resources"] = []
        upgraded.append(str(item.get("key", "")))
    return upgraded


def _validate_exclusive_resources(
    items_by_key: dict[str, dict[str, Any]],
) -> None:
    allowed_prefixes = {
        "repo-file",
        "unity-scene",
        "unity-prefab",
        "logical",
    }

    for key, item in items_by_key.items():
        resources = item.get("exclusive_resources", [])
        if not isinstance(resources, list):
            raise RuntimeError(
                f"{key!r} exclusive_resources must be a list."
            )

        if item.get("kind") == "feature" and resources:
            raise RuntimeError(
                f"Feature {key!r} is non-executable and must not own "
                "exclusive resource locks."
            )

        seen: set[str] = set()

        for resource in resources:
            if not isinstance(resource, dict):
                raise RuntimeError(
                    f"{key!r} has a malformed exclusive resource entry."
                )

            resource_key = str(resource.get("key", "")).strip()
            reason = str(resource.get("reason", "")).strip()
            evidence = str(resource.get("evidence", "")).strip()

            if not resource_key or ":" not in resource_key:
                raise RuntimeError(
                    f"{key!r} has invalid exclusive resource key "
                    f"{resource_key!r}."
                )

            prefix, value = resource_key.split(":", 1)
            if prefix not in allowed_prefixes:
                raise RuntimeError(
                    f"{key!r} has unsupported exclusive resource prefix "
                    f"{prefix!r}."
                )

            if resource_key in seen:
                raise RuntimeError(
                    f"{key!r} lists duplicate exclusive resource "
                    f"{resource_key!r}."
                )
            seen.add(resource_key)

            if not reason:
                raise RuntimeError(
                    f"{key!r} exclusive resource {resource_key!r} requires "
                    "a non-empty reason."
                )
            if not evidence:
                raise RuntimeError(
                    f"{key!r} exclusive resource {resource_key!r} requires "
                    "non-empty evidence/basis."
                )

            if prefix == "logical":
                slug = value.strip()
                if (
                    not slug
                    or slug != slug.lower()
                    or any(
                        not (ch.isalnum() or ch in "-_.")
                        for ch in slug
                    )
                ):
                    raise RuntimeError(
                        f"{key!r} logical exclusive resource must use a "
                        f"stable lowercase slug: {resource_key!r}."
                    )
                continue

            normalized = _normalize_path(value.strip())
            if not normalized or ".." in normalized.split("/"):
                raise RuntimeError(
                    f"{key!r} has unsafe exclusive resource path "
                    f"{resource_key!r}."
                )

            if _is_forbidden_path(normalized):
                raise RuntimeError(
                    f"{key!r} exclusive resource references forbidden "
                    f"project area: {resource_key!r}."
                )

            if normalized.startswith("Pipeline/Reconciliation/outputs/"):
                raise RuntimeError(
                    f"{key!r} cannot lock generated reconciliation output "
                    f"as a project resource: {resource_key!r}."
                )

            if prefix in {"unity-scene", "unity-prefab"} and not normalized.startswith(
                "Assets/"
            ):
                raise RuntimeError(
                    f"{key!r} {prefix} resource must use a repository-relative "
                    f"Assets/ path: {resource_key!r}."
                )


def build_exclusive_resource_groups(
    work_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Shared locks are valid; they force sequential dispatch.
    owners: dict[str, list[str]] = {}

    for item in work_items:
        if item.get("kind") not in {"implementation", "artifact"}:
            continue
        if item.get("graph_status") != "open":
            continue

        item_key = str(item.get("key", ""))
        for resource in item.get("exclusive_resources", []):
            resource_key = str(resource.get("key", "")).strip()
            if not resource_key:
                continue
            owners.setdefault(resource_key, []).append(item_key)

    return [
        {
            "resource_key": resource_key,
            "work_keys": sorted(set(work_keys)),
        }
        for resource_key, work_keys in sorted(owners.items())
        if len(set(work_keys)) > 1
    ]


def _validate_unresolved_refs(
    payload: dict[str, Any],
    items_by_key: dict[str, dict[str, Any]],
) -> None:
''',
    marker="def ensure_exclusive_resource_defaults(",
)

replace_once(
    path,
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_execution_scope_defaults(payload)
    items = payload.get("work_items", [])
''',
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_execution_scope_defaults(payload)
    ensure_exclusive_resource_defaults(payload)
    items = payload.get("work_items", [])
''',
    marker="    ensure_exclusive_resource_defaults(payload)\n    items = payload.get",
)

replace_once(
    path,
    '''    _validate_evidence_and_status(items_by_key)
    _validate_execution_scope(items_by_key)
    _validate_unresolved_refs(payload, items_by_key)
''',
    '''    _validate_evidence_and_status(items_by_key)
    _validate_execution_scope(items_by_key)
    _validate_exclusive_resources(items_by_key)
    _validate_unresolved_refs(payload, items_by_key)
''',
    marker="    _validate_exclusive_resources(items_by_key)",
)

replace_once(
    path,
    '''                    "execution_scope": item.get("execution_scope", "unknown"),
                    "parent_reconciliation_key": item.get("parent_key"),
''',
    '''                    "execution_scope": item.get("execution_scope", "unknown"),
                    "exclusive_resource_keys": [
                        resource.get("key")
                        for resource in item.get("exclusive_resources", [])
                    ],
                    "parent_reconciliation_key": item.get("parent_key"),
''',
    marker='"exclusive_resource_keys": [',
)

replace_once(
    path,
    '''            "proposed_changes": [],
            "conflicts": [],
            "next_action": "human_review_then_seed",
''',
    '''            "exclusive_resource_groups": build_exclusive_resource_groups(
                work_items
            ),
            "proposed_changes": [],
            "conflicts": [],
            "next_action": "human_review_then_seed",
''',
    marker='"exclusive_resource_groups": build_exclusive_resource_groups(\n                work_items',
)

replace_once(
    path,
    '''        "proposed_seed_records": [],
        "proposed_changes": [],
        "conflicts": [],
        "next_action": "taskcontrol_reconciliation_diff",
''',
    '''        "proposed_seed_records": [],
        "exclusive_resource_groups": build_exclusive_resource_groups(work_items),
        "proposed_changes": [],
        "conflicts": [],
        "next_action": "taskcontrol_reconciliation_diff",
''',
    marker='"exclusive_resource_groups": build_exclusive_resource_groups(work_items),',
)

replace_once(
    path,
    '''            "| Reconciliation key | Kind | Title | Proposed status | Execution | Parent | "
            "Depends on |"
        )
        lines.append("|---|---|---|---|---|---|---|")
''',
    '''            "| Reconciliation key | Kind | Title | Proposed status | Execution | "
            "Exclusive resources | Parent | Depends on |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
''',
    marker='"Exclusive resources | Parent | Depends on |"',
)

replace_once(
    path,
    '''                        _cell(item.get("execution_scope")),
                        _cell(item.get("parent_reconciliation_key")),
''',
    '''                        _cell(item.get("execution_scope")),
                        _cell(", ".join(
                            str(value)
                            for value in item.get("exclusive_resource_keys", [])
                        )),
                        _cell(item.get("parent_reconciliation_key")),
''',
    marker='item.get("exclusive_resource_keys", [])',
)

replace_once(
    path,
    '''        "| Key | Parent | Kind | Title | GDD basis | Repo state | "
        "Graph status | Depends on | Decomposition | Execution | Confidence |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )
''',
    '''        "| Key | Parent | Kind | Title | GDD basis | Repo state | "
        "Graph status | Depends on | Exclusive resources | Decomposition | "
        "Execution | Confidence |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
''',
    marker='"Graph status | Depends on | Exclusive resources | Decomposition | "',
)

# This anchor appears only in the reconciliation table row before the patch.
replace_once(
    path,
    '''                    _cell(_deps_text(item)),
                    _cell(item.get("decomposition_state")),
                    _cell(item.get("execution_scope")),
''',
    '''                    _cell(_deps_text(item)),
                    _cell(", ".join(
                        str(resource.get("key", ""))
                        for resource in item.get("exclusive_resources", [])
                    )),
                    _cell(item.get("decomposition_state")),
                    _cell(item.get("execution_scope")),
''',
    marker='str(resource.get("key", ""))\n                        for resource in item.get("exclusive_resources", [])',
)

replace_once(
    path,
    '''        deps = item.get("depends_on", [])
        if deps:
            lines.append("**Dependencies**")
''',
    '''        resources = item.get("exclusive_resources", [])
        if resources:
            lines.append("**Exclusive resources**")
            lines.append("")
            for resource in resources:
                lines.append(
                    f"- `{_cell(resource.get('key'))}` — "
                    f"{_cell(resource.get('reason'))} "
                    f"Evidence/basis: {_cell(resource.get('evidence'))}"
                )
            lines.append("")

        deps = item.get("depends_on", [])
        if deps:
            lines.append("**Dependencies**")
''',
    marker='            lines.append("**Exclusive resources**")',
)

# ============================================================================
# reconcile.md
# ============================================================================

path = "Pipeline/Reconciliation/prompts/reconcile.md"

replace_once(
    path,
    '''Do not confuse difficulty with execution scope. A technically difficult task can still be `single_agent` if it is bounded. A straightforward task can require `needs_execution_decomposition` if it bundles several independently verifiable responsibilities.

# Requirement basis
''',
    '''Do not confuse difficulty with execution scope. A technically difficult task can still be `single_agent` if it is bounded. A straightforward task can require `needs_execution_decomposition` if it bundles several independently verifiable responsibilities.

# Exclusive resources

`exclusive_resources` answers a fourth, separate question:

> Can this otherwise-ready work execute at the same time as another task without both agents writing or integrating against the same non-merge-safe resource?

This is NOT a dependency and it is NOT execution scope.

Two tasks can both be dependency-ready and `execution_scope: single_agent` while still being unsafe to dispatch concurrently because they share an exclusive resource.

Use an exclusive resource only for a resource the task is expected to **modify, regenerate, configure, or integrate against exclusively**. Do not lock files merely because the agent needs to read them.

Every resource entry contains:

- `key` — canonical lock identity;
- `reason` — why simultaneous execution would be unsafe;
- `evidence` — repository/GDD/architecture basis for the lock.

Canonical key formats:

- `repo-file:<repository-relative path>` for a specific shared source/editor file;
- `unity-scene:<repository-relative Assets/... scene path>` for a known Unity scene;
- `unity-prefab:<repository-relative Assets/... prefab path>` for a known prefab;
- `logical:<stable-lowercase-slug>` only when a shared future integration resource is clearly required but no repository path exists yet.

Examples:

- `repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`
- `unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity`
- `logical:main-floor-scene`

Rules:

1. If two open executable items are expected to modify the same resource, use the exact SAME resource key on both.
2. Prefer a concrete repository path when one is known.
3. Do not guess a future path; use `logical:` only when the shared resource itself is established.
4. Feature/organizational nodes should use an empty list.
5. Already-complete work normally uses an empty list because it is not awaiting dispatch.
6. A shared exclusive resource does not imply either task depends on the other. It means the scheduler must acquire the lock before dispatch and run colliding tasks sequentially.
7. Be conservative. Do not turn broad domains such as `combat` or `enemies` into global locks.

# Requirement basis
''',
    marker="# Exclusive resources",
)

# ============================================================================
# verification_crew.py
# ============================================================================

path = "Pipeline/Reconciliation/verification_crew.py"

replace_once(
    path,
    '''                "shared_capability_hidden",
                "execution_scope_problem",
                "other",
''',
    '''                "shared_capability_hidden",
                "execution_scope_problem",
                "exclusive_resource_problem",
                "other",
''',
    marker='"exclusive_resource_problem"',
)

# ============================================================================
# structure_auditor.md
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/structure_auditor.md"

replace_once(
    path,
    '''10. Would this graph allow `taskcontrol ready` to expose work before its real prerequisites exist?

Be especially alert to cross-system requirements.
''',
    '''10. Would this graph allow `taskcontrol ready` to expose work before its real prerequisites exist?
11. Do otherwise-independent tasks that will modify the same source file, Unity scene, prefab, builder, or non-merge-safe integration surface share the same `exclusive_resources` key?
12. Are any exclusive-resource locks overbroad, speculative, or incorrectly being used as dependency ordering?

Be especially alert to cross-system requirements.
''',
    marker="11. Do otherwise-independent tasks",
)

replace_once(
    path,
    '''Do not add dependencies merely because two systems interact. Dependencies are execution prerequisites, not conceptual associations.

If ordering is uncertain, report it rather than inventing certainty.
''',
    '''Do not add dependencies merely because two systems interact. Dependencies are execution prerequisites, not conceptual associations.

Likewise, do not invent dependency ordering merely because two tasks share an exclusive resource. A resource collision means both tasks may be ready but must not be dispatched concurrently. Use `category: exclusive_resource_problem` when the scheduling lock metadata is missing, inconsistent, or overbroad.

If ordering is uncertain, report it rather than inventing certainty.
''',
    marker="Use `category: exclusive_resource_problem`",
)

# ============================================================================
# execution_scope_auditor.md
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md"

replace_once(
    path,
    '''Do not score subjective difficulty. Evaluate execution boundaries.

## Expected execution-scope values
''',
    '''Do not score subjective difficulty. Evaluate execution boundaries.

Also keep concurrency separate from execution size:

- `execution_scope` asks whether ONE agent can own the task.
- `exclusive_resources` asks whether TWO otherwise-ready tasks can run at the same time.

A task can legitimately be `single_agent` while requiring one or more exclusive resource locks. Do not mark a task `needs_execution_decomposition` merely because it shares a scene, prefab, or source file with another task.

## Expected execution-scope values
''',
    marker="Also keep concurrency separate from execution size:",
)

replace_once(
    path,
    '''- missing/unknown execution-scope metadata.

Do not decompose the game into speculative microtasks and do not invent missing design.
''',
    '''- missing/unknown execution-scope metadata;
- a task being treated as oversized when the real issue is only a shared exclusive resource;
- obvious shared scene/prefab/file integration collisions that should be expressed as `exclusive_resources` instead of hidden inside execution-scope reasoning.

Do not decompose the game into speculative microtasks and do not invent missing design.
''',
    marker="obvious shared scene/prefab/file integration collisions",
)

replace_once(
    path,
    '''Use `category: execution_scope_problem` for execution-size/handoff problems.

Use blocker/error only when
''',
    '''Use `category: execution_scope_problem` for execution-size/handoff problems.
Use `category: exclusive_resource_problem` when the task size is acceptable but concurrency metadata is unsafe or missing.

Use blocker/error only when
''',
    marker="Use `category: exclusive_resource_problem` when",
)

# ============================================================================
# refiner.md
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/refiner.md"

replace_once(
    path,
    '''- classify `execution_scope` separately from design decomposition. If approved design is concrete but the implementation item is too broad for one bounded agent handoff, use `needs_execution_decomposition` rather than inventing subtask design. Use `human_integration_required` when the next meaningful step fundamentally requires human Unity/editor/integration judgment.

You MUST NOT:
''',
    '''- classify `execution_scope` separately from design decomposition. If approved design is concrete but the implementation item is too broad for one bounded agent handoff, use `needs_execution_decomposition` rather than inventing subtask design. Use `human_integration_required` when the next meaningful step fundamentally requires human Unity/editor/integration judgment;
- add, remove, or normalize `exclusive_resources` when current repository/GDD/architecture evidence establishes that otherwise-ready tasks would modify the same non-merge-safe source file, Unity scene, prefab, builder, or logical integration surface. Shared resource locks are scheduling constraints, not dependencies.

You MUST NOT:
''',
    marker="Shared resource locks are scheduling constraints, not dependencies.",
)

replace_once(
    path,
    '''- every work item has an `execution_scope` and `execution_reason`;
- feature/organizational and already-complete work uses `not_applicable`;
''',
    '''- every work item has an `execution_scope`, `execution_reason`, and `exclusive_resources`;
- feature/organizational work has no exclusive resource locks;
- tasks expected to modify the same non-merge-safe resource use an identical canonical resource key;
- exclusive resources are not misrepresented as dependency ordering;
- feature/organizational and already-complete work uses `not_applicable`;
''',
    marker="tasks expected to modify the same non-merge-safe resource",
)

# ============================================================================
# verification_smoke_test.py
# ============================================================================

path = "Pipeline/Reconciliation/verification_smoke_test.py"

replace_once(
    path,
    '''    upgraded = crew.ensure_execution_scope_defaults(legacy)
    assert set(upgraded) == {"root", "todo", "done"}
    assert legacy["work_items"][0]["execution_scope"] == "not_applicable"
    assert legacy["work_items"][1]["execution_scope"] == "unknown"
    assert legacy["work_items"][2]["execution_scope"] == "not_applicable"

    print("verification smoke test passed")
''',
    '''    upgraded = crew.ensure_execution_scope_defaults(legacy)
    assert set(upgraded) == {"root", "todo", "done"}
    assert legacy["work_items"][0]["execution_scope"] == "not_applicable"
    assert legacy["work_items"][1]["execution_scope"] == "unknown"
    assert legacy["work_items"][2]["execution_scope"] == "not_applicable"

    resource_legacy = {
        "work_items": [
            {"key": "feature", "kind": "feature", "graph_status": "open"},
            {"key": "task-a", "kind": "implementation", "graph_status": "open"},
            {"key": "task-b", "kind": "implementation", "graph_status": "open"},
        ]
    }
    resource_upgraded = reconciliation.ensure_exclusive_resource_defaults(
        resource_legacy
    )
    assert set(resource_upgraded) == {"feature", "task-a", "task-b"}

    shared = {
        "key": (
            "repo-file:"
            "Assets/NoSafeCircle/DoorPrototype/Editor/"
            "DoorPrototypeSceneBuilder.cs"
        ),
        "reason": "Both tasks modify the same scene builder.",
        "evidence": "Current repository uses one builder for the prototype scene.",
    }
    resource_legacy["work_items"][1]["exclusive_resources"] = [dict(shared)]
    resource_legacy["work_items"][2]["exclusive_resources"] = [dict(shared)]

    by_key = reconciliation._validate_unique_keys(
        resource_legacy["work_items"]
    )
    reconciliation._validate_exclusive_resources(by_key)
    groups = reconciliation.build_exclusive_resource_groups(
        resource_legacy["work_items"]
    )
    assert groups == [
        {
            "resource_key": shared["key"],
            "work_keys": ["task-a", "task-b"],
        }
    ]

    invalid_resource = {
        "feature": {
            "key": "feature",
            "kind": "feature",
            "graph_status": "open",
            "exclusive_resources": [
                {
                    "key": "logical:should-not-lock-feature",
                    "reason": "invalid",
                    "evidence": "invalid",
                }
            ],
        }
    }
    try:
        reconciliation._validate_exclusive_resources(invalid_resource)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Feature nodes must not carry exclusive resource locks."
        )

    print("verification smoke test passed")
''',
    marker="resource_upgraded = reconciliation.ensure_exclusive_resource_defaults",
)

# ============================================================================
# README.md
# ============================================================================

path = "Pipeline/Reconciliation/README.md"

replace_once(
    path,
    '''- execution scope + reason (is this a safe one-agent handoff?);
- confidence;
''',
    '''- execution scope + reason (is this a safe one-agent handoff?);
- exclusive resources (can this otherwise-ready work run concurrently?);
- confidence;
''',
    marker="- exclusive resources (can this otherwise-ready work run concurrently?);",
)

replace_once(
    path,
    '''Difficulty is not the classifier: a hard but bounded task can still be `single_agent`.


## Verification refiner sizing and recovery
''',
    '''Difficulty is not the classifier: a hard but bounded task can still be `single_agent`.

## Exclusive resources and concurrency

Execution readiness and parallel safety are separate.

`exclusive_resources` records non-merge-safe resources that an open executable
task expects to modify or integrate against exclusively. Two tasks can both be
dependency-ready and `single_agent` while still requiring sequential dispatch.

Canonical lock keys use:

- `repo-file:<repository-relative path>`
- `unity-scene:<repository-relative Assets/... path>`
- `unity-prefab:<repository-relative Assets/... path>`
- `logical:<stable-lowercase-slug>` only when the shared integration resource
  is established but no concrete path exists yet

For example, two tasks that both modify
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` should
both carry the exact same `repo-file:` lock key.

These locks are **not dependencies**. `taskcontrol ready` may still consider
both tasks ready. The future dispatcher must acquire all declared exclusive
resource locks before starting a task and must not run two tasks concurrently
when their lock sets intersect.

Reconciliation records only coarse, evidence-backed locks. A later Feature
Planning / Progressive Decomposition step may add more exact file/scene/prefab
locks as the implementation file list becomes concrete.


## Verification refiner sizing and recovery
''',
    marker="## Exclusive resources and concurrency",
)

replace_once(
    path,
    '''9. Every open executable item has a credible execution-scope classification before autonomous selection.
''',
    '''9. Every open executable item has a credible execution-scope classification before autonomous selection.
10. Obvious shared file/scene/prefab integration surfaces are represented by identical `exclusive_resources` keys so otherwise-ready tasks cannot be dispatched concurrently against the same non-merge-safe resource.
''',
    marker="10. Obvious shared file/scene/prefab integration surfaces",
)

print()
print("Exclusive-resource scheduling metadata patch applied.")
print("Run:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
