from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
PROMPT = ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"

MARKER = "## Mandatory final dependency-kind preflight"

BLOCK = r"""
## Mandatory final dependency-kind preflight

Immediately before returning the final JSON, perform a complete dependency-kind
audit over the candidate you are about to return.

For **every** work item and **every** entry in `depends_on`:

1. Resolve `depends_on[].key` to an actual work item in `work_items`.
2. Confirm the target exists.
3. Confirm the target's `kind` is exactly `implementation` or `artifact`.
4. If the target's `kind` is `feature`, remove that dependency unless an
   already-existing implementation/artifact item is the true concrete
   prerequisite.
5. Do not invent a replacement dependency merely to preserve ordering.
6. Re-run this audit after making any correction.

A dependency on a `feature` is invalid even when both feature nodes describe
required work and even when one feature will eventually need content produced
under the other.

Deferred-content features are especially important here. Their relationship is
often a future decomposition relationship, not an executable dependency.

Example from the current GDD:

```text
five-room-content-authoring
    kind: feature

dungeon-encounter-content-authoring
    kind: feature
```

This is INVALID:

```text
dungeon-encounter-content-authoring
    depends_on:
      - five-room-content-authoring
```

Both nodes are deferred organizational/content features and are not directly
dispatchable.

The valid bootstrap representation is to keep both feature nodes without a
formal dependency between them. Preserve the relationship in
`decomposition_reason`, `notes`, or GDD evidence. Later, when the Progressive
Decomposer creates concrete implementation/artifact descendants, those
executable descendants may receive real `depends_on` edges if the prerequisite
is then established.

A concrete implementation may still be a valid dependency of a deferred
feature when the implementation is an actual reusable prerequisite. For
example, a deferred encounter-content feature may depend on an existing
`implementation` item that owns encounter-admission/cap enforcement.

### Final assertion

Do not return the JSON until this assertion is true:

```text
for every work_item:
    for every dependency in work_item.depends_on:
        dependency_target_exists
        AND dependency_target.kind in {"implementation", "artifact"}
```

If any dependency fails that assertion, repair the candidate first.

"""

def main() -> int:
    if not PROMPT.exists():
        raise FileNotFoundError(f"Expected prompt not found: {PROMPT}")

    text = PROMPT.read_text(encoding="utf-8")
    if MARKER in text:
        print("Dependency-kind preflight hardening is already present.")
        return 0

    anchor = "\n---\n\n# Repository state\n"
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(
            "Could not find the expected insertion point before '# Repository state'."
        )

    updated = text[:idx] + "\n" + BLOCK.rstrip() + "\n" + text[idx:]
    PROMPT.write_text(updated, encoding="utf-8")

    print(f"Patched: {PROMPT}")
    print()
    print("Added:")
    print("- mandatory dependency target existence check")
    print("- mandatory dependency target kind check")
    print("- explicit ban on feature -> feature depends_on edges")
    print("- deferred-content example matching the latest failed run")
    print("- mandatory re-audit after corrections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
