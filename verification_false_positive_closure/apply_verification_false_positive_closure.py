from pathlib import Path

ROOT = Path.cwd()

COVERAGE = ROOT / "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md"
REFINER = ROOT / "Pipeline/Reconciliation/prompts/verification/refiner.md"

COVERAGE_MARKER = "## Final verifier closure: deferred feature prerequisites and runtime-AI classification"
REFINER_MARKER = "## Final verifier closure repair: reject illegal feature edges and preserve runtime-AI non-code scope"

COVERAGE_BLOCK = r"""

---

## Final verifier closure: deferred feature prerequisites and runtime-AI classification

Apply these rules before returning the requirement map or material findings.

### Deferred feature relationships do not authorize feature-target dependencies

The reconciliation graph intentionally separates organizational/deferred
features from executable prerequisites.

A `feature` work item MAY itself have dependencies, but every dependency target
must still be an `implementation` or `artifact`. The fact that one feature
validly depends on an implementation does NOT imply that a feature may depend
on another feature.

Current canonical example:

- `five-room-content-authoring`
  - kind: `feature`
  - may validly depend on `world-visual-foundation` because that target is a
    concrete `implementation`.
- `dungeon-encounter-content-authoring`
  - kind: `feature`
  - MUST NOT depend directly on `five-room-content-authoring` while the latter
    remains a `feature`.

The GDD statement that encounter placement/content consumes authored room
spaces is still required. Preserve it durably as decomposition/authoring context
on the deferred encounter-content feature until Progressive Decomposition
creates concrete implementation/artifact descendants.

When concrete descendants exist, attach the real executable dependency there,
for example:

```text
concrete encounter placement implementation
    -> concrete authored-room implementation/artifact
```

Do not report a missing dependency solely because the current bootstrap graph
does not contain an illegal `feature -> feature` edge.

A downstream deferred feature may still depend on concrete reusable
implementation/artifact prerequisites such as encounter-admission/cap
enforcement. That does not weaken the prohibition on feature targets.

### Finished-build runtime-AI prohibition is required non-code scope

The GDD requirement that the finished build uses no runtime generative AI and
has no external AI service/network dependency is NOT player-facing gameplay.

Classify it as:

```text
classification: required_non_code
representation: non_code_requirement
```

when the candidate contains the corresponding typed non-code record.

Do not classify this requirement as `required_gameplay`, and do not manufacture
a gameplay work item merely because the prohibition constrains the final
runtime architecture.

If the candidate already contains a durable record equivalent to
`No runtime generative AI or external AI service in the finished build`, map
the requirement to that record through `mapped_non_code_titles`.

### Final check

Before returning:

```text
no finding requests a dependency whose target is kind=feature
AND "no runtime generative AI / no external AI service" is required_non_code
    mapped to a typed non_code_requirement when that record exists
```
"""

REFINER_BLOCK = r"""

---

## Final verifier closure repair: reject illegal feature edges and preserve runtime-AI non-code scope

Use these rules when pass-1 findings request one of the two repairs below.

### Do not add feature-target dependencies

Never repair a finding by adding a `depends_on` edge whose target is a
`feature`.

In particular, do NOT add:

```text
dungeon-encounter-content-authoring
    -> five-room-content-authoring
```

while `five-room-content-authoring` remains `kind: feature`.

The GDD prerequisite relationship is real, but at this bootstrap level it is
preserved as deferred decomposition/authoring context. Later concrete
implementation/artifact descendants may carry the executable edge.

Do not treat this as inconsistent with a feature depending on
`world-visual-foundation`: that edge is valid because
`world-visual-foundation` is an `implementation`, not a feature.

If a supplied finding recommends a feature-target dependency, reject that
recommended graph mutation and preserve the candidate's dependency-kind
invariant.

### Preserve finished-build runtime-AI prohibition as non-code

If a coverage finding classifies the finished-build prohibition on runtime
generative AI / external AI services as gameplay, do not convert the candidate
into gameplay work.

When the candidate already stores the requirement as a typed
`non_code_requirement`, preserve that representation.

The correct coverage semantics are:

```text
required_non_code -> non_code_requirement
```

This is a verifier-classification correction, not a reason to add a new
implementation node.

### Structural closure

After any related refinement, re-run the existing assertions:

- every dependency target exists;
- every dependency target is `implementation` or `artifact`;
- no feature-target dependency was introduced;
- no dependency cycle was introduced;
- existing required non-code records remain typed correctly.
"""

def append_once(path: Path, marker: str, block: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Missing expected file: {path}")
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"already present: {path}")
        return
    path.write_text(text.rstrip() + "\n" + block.strip("\n") + "\n", encoding="utf-8")
    print(f"updated: {path}")

append_once(COVERAGE, COVERAGE_MARKER, COVERAGE_BLOCK)
append_once(REFINER, REFINER_MARKER, REFINER_BLOCK)

print("Done. This patch changes verification prompts only.")
print("No GDD files are read, copied, moved, replaced, or modified.")
