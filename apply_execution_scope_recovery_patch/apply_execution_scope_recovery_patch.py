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


def replace_once(path: str, old: str, new: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    write(path, text.replace(old, new, 1))
    print(f"patched: {path} [{marker}]")


def insert_before_once(path: str, anchor: str, addition: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(f"Anchor not found in {path}: {anchor!r}")
    write(path, text[:idx] + addition + text[idx:])
    print(f"patched: {path} [{marker}]")


path = "Pipeline/Reconciliation/reconciliation_agent.py"

insert_before_once(
    path,
    "def _validate_execution_scope(",
    '''def normalize_execution_scope_consistency(
    payload: dict[str, Any],
) -> list[str]:
    normalized: list[str] = []

    for item in payload.get("work_items", []):
        key = str(item.get("key", ""))
        kind = item.get("kind")
        status = item.get("graph_status")
        scope = str(item.get("execution_scope", ""))

        if kind == "feature":
            if scope != "not_applicable":
                item["execution_scope"] = "not_applicable"
                item["execution_reason"] = (
                    "Deterministic normalization: feature/organizational work "
                    "is not an implementation-agent execution unit."
                )
                normalized.append(key)
            continue

        if status == "complete":
            if scope not in {"not_applicable", "single_agent"}:
                item["execution_scope"] = "not_applicable"
                item["execution_reason"] = (
                    "Deterministic normalization: completed work is not "
                    "awaiting another implementation-agent handoff."
                )
                normalized.append(key)
            continue

        if (
            kind in {"implementation", "artifact"}
            and status == "open"
            and scope == "not_applicable"
        ):
            item["execution_scope"] = "unknown"
            item["execution_reason"] = (
                "Deterministic normalization: open executable work cannot be "
                "not_applicable. Verification or human review must classify "
                "its execution scope."
            )
            normalized.append(key)

    if normalized:
        seed = payload.setdefault(
            "seed_assessment",
            {"status": "ready_with_warnings", "blockers": [], "warnings": []},
        )
        warnings = seed.setdefault("warnings", [])
        warning = (
            "Deterministic validation normalized contradictory execution_scope "
            "values for: " + ", ".join(sorted(set(normalized)))
        )
        if warning not in warnings:
            warnings.append(warning)
        if seed.get("status") == "ready":
            seed["status"] = "ready_with_warnings"

    return sorted(set(normalized))


''',
    marker="def normalize_execution_scope_consistency(",
)

replace_once(
    path,
    '''    ensure_requirement_detail_defaults(payload)
    ensure_execution_scope_defaults(payload)
    ensure_exclusive_resource_defaults(payload)
''',
    '''    ensure_requirement_detail_defaults(payload)
    ensure_execution_scope_defaults(payload)
    normalize_execution_scope_consistency(payload)
    ensure_exclusive_resource_defaults(payload)
''',
    marker="    normalize_execution_scope_consistency(payload)",
)

path = "Pipeline/Reconciliation/prompts/reconcile.md"
insert_before_once(
    path,
    "# Exclusive resources",
    '''## Execution-scope consistency invariant

Before returning:

- every `feature` must use `execution_scope: not_applicable`;
- every open `implementation` or `artifact` MUST NOT use
  `execution_scope: not_applicable`;
- when an open executable item's handoff size cannot be classified safely, use
  `execution_scope: unknown` and explain why;
- completed work must not claim that future execution decomposition or human
  integration is still required.

This is a structural consistency rule, not a judgment about task difficulty.

''',
    marker="## Execution-scope consistency invariant",
)

path = "Pipeline/Reconciliation/verification_smoke_test.py"
insert_before_once(
    path,
    '    print("verification smoke test passed")',
    '''    contradictory_scope = {
        "seed_assessment": {
            "status": "ready",
            "blockers": [],
            "warnings": [],
        },
        "work_items": [
            {
                "key": "open-task",
                "kind": "implementation",
                "graph_status": "open",
                "execution_scope": "not_applicable",
                "execution_reason": "Incorrect model classification.",
            },
            {
                "key": "feature-task",
                "kind": "feature",
                "graph_status": "open",
                "execution_scope": "single_agent",
                "execution_reason": "Incorrect model classification.",
            },
        ],
    }
    normalized_scope = reconciliation.normalize_execution_scope_consistency(
        contradictory_scope
    )
    assert set(normalized_scope) == {"open-task", "feature-task"}
    assert contradictory_scope["work_items"][0]["execution_scope"] == "unknown"
    assert (
        contradictory_scope["work_items"][1]["execution_scope"]
        == "not_applicable"
    )
    assert (
        contradictory_scope["seed_assessment"]["status"]
        == "ready_with_warnings"
    )

''',
    marker="normalized_scope = reconciliation.normalize_execution_scope_consistency",
)

path = "Pipeline/Reconciliation/README.md"
insert_before_once(
    path,
    "## Verification refiner sizing and recovery",
    '''## Deterministic execution-scope normalization

The structured-output schema can still produce combinations that are valid
enum values but structurally contradictory, such as:

`kind: implementation + graph_status: open + execution_scope: not_applicable`

The orchestrator repairs only these mechanical contradictions:

- feature -> `not_applicable`
- completed work that claims future decomposition/integration ->
  `not_applicable`
- open executable + `not_applicable` -> `unknown`

The last case is intentionally conservative. The orchestrator does not guess
`single_agent` versus decomposition; verification or human review must decide.
Every normalization is recorded as a seed warning.

''',
    marker="## Deterministic execution-scope normalization",
)

print("Execution-scope consistency patch applied.")
print("Next:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
