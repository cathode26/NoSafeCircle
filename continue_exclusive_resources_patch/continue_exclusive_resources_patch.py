from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected repository file not found: {p}")
    return p.read_text(encoding="utf-8")

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")

def insert_after_once(path: str, anchor: str, addition: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(f"Anchor not found in {path}: {anchor!r}")
    idx += len(anchor)
    text = text[:idx] + addition + text[idx:]
    write(path, text)
    print(f"patched: {path} [{marker}]")

def replace_once(path: str, old: str, new: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    write(path, text.replace(old, new, 1))
    print(f"patched: {path} [{marker}]")

# 1) Dependency / decomposition auditor
path = "Pipeline/Reconciliation/prompts/verification/structure_auditor.md"

insert_after_once(
    path,
    "10. Would this graph allow `taskcontrol ready` to expose work before its real prerequisites exist?",
    "\n11. Do otherwise-independent tasks that will modify the same source file, Unity scene, prefab, builder, or non-merge-safe integration surface share the same `exclusive_resources` key?\n12. Are any exclusive-resource locks overbroad, speculative, or incorrectly being used as dependency ordering?",
    "11. Do otherwise-independent tasks",
)

insert_after_once(
    path,
    "Do not add dependencies merely because two systems interact. Dependencies are execution prerequisites, not conceptual associations.",
    "\n\nLikewise, do not invent dependency ordering merely because two tasks share an exclusive resource. A resource collision means both tasks may be ready but must not be dispatched concurrently. Use `category: exclusive_resource_problem` when the scheduling lock metadata is missing, inconsistent, or overbroad.",
    "Use `category: exclusive_resource_problem`",
)

# 2) Execution-scope auditor
path = "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md"

insert_after_once(
    path,
    "Do not score subjective difficulty. Evaluate execution boundaries.",
    "\n\nAlso keep concurrency separate from execution size:\n\n- `execution_scope` asks whether ONE agent can own the task.\n- `exclusive_resources` asks whether TWO otherwise-ready tasks can run at the same time.\n\nA task can legitimately be `single_agent` while requiring one or more exclusive resource locks. Do not mark a task `needs_execution_decomposition` merely because it shares a scene, prefab, or source file with another task.",
    "Also keep concurrency separate from execution size:",
)

replace_once(
    path,
    "- missing/unknown execution-scope metadata.",
    "- missing/unknown execution-scope metadata;\n- a task being treated as oversized when the real issue is only a shared exclusive resource;\n- obvious shared scene/prefab/file integration collisions that should be expressed as `exclusive_resources` instead of hidden inside execution-scope reasoning.",
    "obvious shared scene/prefab/file integration collisions",
)

insert_after_once(
    path,
    "Use `category: execution_scope_problem` for execution-size/handoff problems.",
    "\nUse `category: exclusive_resource_problem` when the task size is acceptable but concurrency metadata is unsafe or missing.",
    "Use `category: exclusive_resource_problem` when",
)

# 3) Refiner
path = "Pipeline/Reconciliation/prompts/verification/refiner.md"

replace_once(
    path,
    "- classify `execution_scope` separately from design decomposition. If approved design is concrete but the implementation item is too broad for one bounded agent handoff, use `needs_execution_decomposition` rather than inventing subtask design. Use `human_integration_required` when the next meaningful step fundamentally requires human Unity/editor/integration judgment.",
    "- classify `execution_scope` separately from design decomposition. If approved design is concrete but the implementation item is too broad for one bounded agent handoff, use `needs_execution_decomposition` rather than inventing subtask design. Use `human_integration_required` when the next meaningful step fundamentally requires human Unity/editor/integration judgment;\n- add, remove, or normalize `exclusive_resources` when current repository/GDD/architecture evidence establishes that otherwise-ready tasks would modify the same non-merge-safe source file, Unity scene, prefab, builder, or logical integration surface. Shared resource locks are scheduling constraints, not dependencies.",
    "Shared resource locks are scheduling constraints, not dependencies.",
)

replace_once(
    path,
    "- every work item has an `execution_scope` and `execution_reason`;\n- feature/organizational and already-complete work uses `not_applicable`;",
    "- every work item has an `execution_scope`, `execution_reason`, and `exclusive_resources`;\n- feature/organizational work has no exclusive resource locks;\n- tasks expected to modify the same non-merge-safe resource use an identical canonical resource key;\n- exclusive resources are not misrepresented as dependency ordering;\n- feature/organizational and already-complete work uses `not_applicable`;",
    "tasks expected to modify the same non-merge-safe resource",
)

# 4) Smoke test
path = "Pipeline/Reconciliation/verification_smoke_test.py"

anchor = '    assert legacy["work_items"][2]["execution_scope"] == "not_applicable"\n'
addition = r'''

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
'''
insert_after_once(
    path,
    anchor,
    addition,
    "resource_upgraded = reconciliation.ensure_exclusive_resource_defaults",
)

# 5) README
path = "Pipeline/Reconciliation/README.md"

replace_once(
    path,
    "- execution scope + reason (is this a safe one-agent handoff?);\n- confidence;",
    "- execution scope + reason (is this a safe one-agent handoff?);\n- exclusive resources (can this otherwise-ready work run concurrently?);\n- confidence;",
    "- exclusive resources (can this otherwise-ready work run concurrently?);",
)

insert_after_once(
    path,
    "Difficulty is not the classifier: a hard but bounded task can still be `single_agent`.",
    "\n\n## Exclusive resources and concurrency\n\nExecution readiness and parallel safety are separate.\n\n`exclusive_resources` records non-merge-safe resources that an open executable\ntask expects to modify or integrate against exclusively. Two tasks can both be\ndependency-ready and `single_agent` while still requiring sequential dispatch.\n\nCanonical lock keys use:\n\n- `repo-file:<repository-relative path>`\n- `unity-scene:<repository-relative Assets/... path>`\n- `unity-prefab:<repository-relative Assets/... path>`\n- `logical:<stable-lowercase-slug>` only when the shared integration resource\n  is established but no concrete path exists yet\n\nFor example, two tasks that both modify\n`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` should\nboth carry the exact same `repo-file:` lock key.\n\nThese locks are **not dependencies**. `taskcontrol ready` may still consider\nboth tasks ready. The future dispatcher must acquire all declared exclusive\nresource locks before starting a task and must not run two tasks concurrently\nwhen their lock sets intersect.\n\nReconciliation records only coarse, evidence-backed locks. A later Feature\nPlanning / Progressive Decomposition step may add more exact file/scene/prefab\nlocks as the implementation file list becomes concrete.",
    "## Exclusive resources and concurrency",
)

insert_after_once(
    path,
    "9. Every open executable item has a credible execution-scope classification before autonomous selection.",
    "\n10. Obvious shared file/scene/prefab integration surfaces are represented by identical `exclusive_resources` keys so otherwise-ready tasks cannot be dispatched concurrently against the same non-merge-safe resource.",
    "10. Obvious shared file/scene/prefab integration surfaces",
)

# 6) Verify all expected markers, including the already-applied core patch.
checks = {
    "Pipeline/Reconciliation/reconciliation_agent.py": [
        "EXCLUSIVE_RESOURCE_SCHEMA",
        '"exclusive_resources": {',
        "def ensure_exclusive_resource_defaults",
        "def _validate_exclusive_resources",
        "def build_exclusive_resource_groups",
        '"exclusive_resource_keys": [',
    ],
    "Pipeline/Reconciliation/prompts/reconcile.md": [
        "# Exclusive resources",
        "repo-file:<repository-relative path>",
    ],
    "Pipeline/Reconciliation/verification_crew.py": [
        '"exclusive_resource_problem"',
    ],
    "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": [
        "11. Do otherwise-independent tasks",
        "Use `category: exclusive_resource_problem`",
    ],
    "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md": [
        "Also keep concurrency separate from execution size:",
        "Use `category: exclusive_resource_problem` when",
    ],
    "Pipeline/Reconciliation/prompts/verification/refiner.md": [
        "Shared resource locks are scheduling constraints, not dependencies.",
        "tasks expected to modify the same non-merge-safe resource",
    ],
    "Pipeline/Reconciliation/verification_smoke_test.py": [
        "resource_upgraded = reconciliation.ensure_exclusive_resource_defaults",
    ],
    "Pipeline/Reconciliation/README.md": [
        "## Exclusive resources and concurrency",
    ],
}

missing = []
for file_path, markers in checks.items():
    text = read(file_path)
    for marker in markers:
        if marker not in text:
            missing.append(f"{file_path}: {marker}")

if missing:
    raise RuntimeError(
        "Exclusive-resource patch is still incomplete:\n- " + "\n- ".join(missing)
    )

print()
print("Exclusive-resource patch continuation completed successfully.")
print("All expected schema, prompt, verifier, smoke-test, and README markers are present.")
print()
print("Next command:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
