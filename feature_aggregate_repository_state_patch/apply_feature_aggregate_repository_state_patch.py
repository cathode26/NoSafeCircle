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
        raise RuntimeError(f"Expected patch anchor not found in {path}: {anchor!r}")
    write(path, text[:idx] + addition + text[idx:])
    print(f"patched: {path} [{marker}]")


# 1. Deterministic semantic validator.
path = "Pipeline/Reconciliation/reconciliation_agent.py"

replace_once(
    path,
    '''        if repo_state in ("implemented", "partial") and not repo_evidence:
            raise RuntimeError(
                f"{key!r} is {repo_state!r} but has no repository evidence."
            )
''',
    '''        # Feature nodes may summarize aggregate progress from their child work.
        # Direct repository evidence belongs on implementation/artifact nodes.
        if (
            kind in {"implementation", "artifact"}
            and repo_state in ("implemented", "partial")
            and not repo_evidence
        ):
            raise RuntimeError(
                f"{key!r} is {repo_state!r} but has no repository evidence."
            )
''',
    marker="Feature nodes may summarize aggregate progress from their child work.",
)

# 2. Reconciliation prompt.
path = "Pipeline/Reconciliation/prompts/reconcile.md"

insert_before_once(
    path,
    "# Proposed graph status",
    '''## Feature aggregate repository-state rule

Feature nodes are organizational/aggregate records, so their repository state
may summarize the current state of represented child work:

- `implemented` may be used when the represented required feature is currently
  satisfied;
- `partial` may be used when meaningful represented child work exists but the
  feature is incomplete;
- `missing` may be used when the represented feature has no meaningful current
  implementation;
- `not_applicable` remains valid when implementation state is not useful for an
  organizational feature;
- `unknown` remains valid when the aggregate cannot be classified safely.

Do **not** duplicate child `repository_evidence` entries onto a feature merely
to justify an aggregate state. A feature may therefore have
`repository_state: partial` or `implemented` with an empty
`repository_evidence` list when that state is an aggregate of represented child
work.

This exception applies only to `kind: feature`. Any `implementation` or
`artifact` marked `implemented` or `partial` must still provide direct,
allowed current-project repository evidence supporting that claim.

''',
    marker="## Feature aggregate repository-state rule",
)

# 3. Smoke tests.
path = "Pipeline/Reconciliation/verification_smoke_test.py"

insert_before_once(
    path,
    '    print("verification smoke test passed")',
    '''    # Feature nodes may summarize child progress without duplicating
    # repository evidence from executable children.
    aggregate_feature = {
        "root-feature": {
            "key": "root-feature",
            "kind": "feature",
            "basis": "direct_gdd",
            "gdd_evidence": [
                {
                    "reference": "Section Test",
                    "requirement": "Aggregate feature requirement.",
                }
            ],
            "repository_state": "partial",
            "repository_evidence": [],
            "graph_status": "open",
        }
    }
    reconciliation._validate_evidence_and_status(aggregate_feature)

    # The exemption must not weaken evidence requirements for executable work.
    executable_without_evidence = {
        "partial-task": {
            "key": "partial-task",
            "kind": "implementation",
            "basis": "direct_gdd",
            "gdd_evidence": [
                {
                    "reference": "Section Test",
                    "requirement": "Executable requirement.",
                }
            ],
            "repository_state": "partial",
            "repository_evidence": [],
            "graph_status": "open",
        }
    }
    try:
        reconciliation._validate_evidence_and_status(
            executable_without_evidence
        )
    except RuntimeError as exc:
        assert "has no repository evidence" in str(exc)
    else:
        raise AssertionError(
            "Partial implementation work must still require repository evidence."
        )

''',
    marker="aggregate_feature = {",
)

# 4. README.
path = "Pipeline/Reconciliation/README.md"

insert_before_once(
    path,
    "## Deterministic execution-scope normalization",
    '''## Feature aggregate repository state

`feature` nodes are organizational/aggregate records. They may report aggregate
`implemented`, `partial`, `missing`, `not_applicable`, or `unknown` repository
state without duplicating repository evidence already owned by their child
implementation/artifact nodes.

For example, the `no-safe-circle` root may truthfully be `partial` because some
represented child systems are implemented while others are still open, even
though the root itself has no source file to cite.

Direct repository evidence remains mandatory for any `implementation` or
`artifact` classified as `implemented` or `partial`. This preserves the
evidence safety rule where it matters while avoiding artificial evidence
duplication on feature groups.

''',
    marker="## Feature aggregate repository state",
)

print()
print("Feature aggregate repository-state patch applied.")
print("Next:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
