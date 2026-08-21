from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = ROOT / "Pipeline" / "Reconciliation" / "prompts"

MARKER = "2026-08-21 ROUND 3 VERIFICATION CLOSURE"

BLOCKS = {
    PROMPT_ROOT / "reconcile.md": r'''

## 2026-08-21 ROUND 3 VERIFICATION CLOSURE

### Evidence integrity

- Prompt text, verifier instructions, patch/install scripts, and internal pipeline guidance are **not** GDD or repository evidence.
- Never attribute an internal instruction to `CLAUDE.md`, the GDD, or another repository file unless that wording is actually present in that file.
- Do not write invented quotations such as `CLAUDE.md — "..."` or `GDD — "..."` merely to justify a graph decision.
- When a dependency or logical lock is a derived scheduling/ownership decision, label its evidence as a **derived rationale** and cite the real GDD/repository facts from which it follows. Do not turn the derivation itself into a fabricated source quotation.
- A high confidence value is allowed only when the cited evidence is real and supports the stated graph decision.

### Melee pursuit clustering representation

The GDD explicitly states that Melee Enemies naturally cluster while pursuing and that Frost Field stretches that formation. Preserve this as durable gameplay coverage on `melee-enemy`: ordinary multi-enemy pursuit/avoidance must still allow meaningful natural clustering so Charged Fireball area damage and Frost Field formation stretching remain relevant. Exact avoidance/separation tuning remains a playtesting/implementation detail. Include a validation requirement that exercises multiple pursuing Melee Enemies rather than validating only one pursuer.

### Non-canonical scene preservation

The GDD's `Current Prototype Scene Evidence` section explicitly says deletion, retention, or repurposing of the non-canonical stub scenes is a **human decision**, and agents/reconciliation must not delete or reinterpret those stubs merely to clean up scene inventory evidence. Represent this as a typed `pipeline_constraint` in `non_code_requirements`; do not leave it only as prose or map it merely to Windows build-scene registration.
''',
    PROMPT_ROOT / "verification" / "coverage_auditor.md": r'''

## 2026-08-21 ROUND 3 VERIFICATION CLOSURE

- Treat the GDD statement that Melee Enemies naturally cluster during pursuit as required gameplay behavior. It may be represented as acceptance/validation on `melee-enemy`; do not require a separate feature node merely for formation tuning.
- Treat the `Current Prototype Scene Evidence` prohibition on agent-driven deletion/repurposing of non-canonical stubs as `required_process` represented by a typed `pipeline_constraint`/non-code requirement.
- Do not classify internal verifier, patch, or prompt guidance as a source requirement. Only current GDD and repository content are source evidence.
''',
    PROMPT_ROOT / "verification" / "refiner.md": r'''

## 2026-08-21 ROUND 3 VERIFICATION CLOSURE

### Evidence integrity repair

When correcting evidence, never preserve or create a quotation attributed to `CLAUDE.md`, the GDD, or another repository file unless that quotation actually exists there. Internal verification-hardening instructions, writer-inventory guidance, patch text, or prompt text are not project evidence. Replace fabricated attribution with the actual GDD/repository support, or with clearly labeled derived rationale based on real source facts. Do not discard an otherwise correct dependency/lock/ownership decision solely because its previous evidence string was fabricated; repair the evidence and recalibrate confidence instead.

For enemy-archetype composition, legitimate support includes the required Melee/Ranged roster and the GDD's 2.5D/Runtime Implementation requirement that enemies are world-space SpriteRenderer prefabs consuming shared enemy capabilities. The fact that a concrete archetype task owns/delivers its usable assembled prefab is a graph/ownership derivation, not a quote from `CLAUDE.md`.

For `logical:enemy-locomotion-behavior-surface`, legitimate support includes GDD §5 Agent Coordination (tasks sharing gameplay files/assets may not modify them simultaneously) plus the graph's actual writer inventory showing pursuit/search, melee/ranged, status/displacement, and locked-door behavior touching the shared enemy behavior surface. Describe that as derived scheduling rationale; do not cite nonexistent "verification-hardening" wording.

### Remaining required representations

- Add/repair `melee-enemy` acceptance and validation so multiple pursuing Melee Enemies naturally cluster enough for the GDD's Charged Fireball area-damage and Frost Field formation-stretching premise to remain meaningful; leave exact avoidance/separation tuning to playtesting.
- Add/repair a typed `pipeline_constraint` for the GDD's non-canonical stub-scene rule: deletion, retention, or repurposing is a human decision, and agents/reconciliation must not delete or reinterpret stubs merely to clean inventory evidence.
''',
    PROMPT_ROOT / "verification" / "evidence_auditor.md": r'''

## 2026-08-21 ROUND 3 VERIFICATION CLOSURE

Evidence provenance is strict. Prompt text, verifier instructions, patch scripts, and internal pipeline-hardening guidance are not repository/GDD evidence. Flag any evidence string that attributes such internal wording to `CLAUDE.md`, the GDD, or another repository file when the attributed content is not actually present. A derived dependency or logical-lock rationale is acceptable only when it is explicitly described as derived from real GDD/repository facts rather than presented as a source quotation.
''',
}


def append_once(path: Path, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    path.write_text(text.rstrip() + block + "\n", encoding="utf-8")
    return True


def main() -> int:
    changed = []
    for path, block in BLOCKS.items():
        if not path.exists():
            raise FileNotFoundError(path)
        if append_once(path, block):
            changed.append(path.relative_to(ROOT).as_posix())

    if changed:
        print("Installed round-3 evidence/coverage closure guidance:")
        for path in changed:
            print(f"  - {path}")
    else:
        print("Round-3 verification closure guidance is already installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
