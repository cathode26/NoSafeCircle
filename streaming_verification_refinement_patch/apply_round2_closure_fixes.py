from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "2026-08-21 VERIFICATION ROUND 2 CLOSURE"

RECONCILE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
COVERAGE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md"
REFINER = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md"
STRUCTURE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "structure_auditor.md"


def append_once(path: Path, section: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if MARKER in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + section.strip() + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    append_once(
        RECONCILE,
        r'''
---

## 2026-08-21 VERIFICATION ROUND 2 CLOSURE

These rules close verified gaps from verification run
`20260821T060257Z-98087458`. They refine representation/ownership only and do
not add new game design.

### Enemy restart reposition ownership

The Floor Run/Restart Orchestrator coordinates restart but does not write enemy
Transform/locomotion internals itself. The enemy pursuit/locomotion owner must
expose an owner-controlled restart/reset operation that consumes the original
authored encounter/spawn-region information, returns that persistent enemy to
that region, and restores its initial pursuit/search/attack state. The
orchestrator calls that owner operation. Do not describe enemy repositioning as
an orchestrator-owned body movement.

### Runtime Input System obligations belong on each spell

Fireball, Frost Field, and Force Wave are runtime input consumers. Their
acceptance criteria must explicitly preserve the GDD contract that casting is
routed through the project's Unity Input System/Input Actions layer and does not
perform independent direct hardware polling. An Input Actions file lock is not
a substitute for this behavioral acceptance criterion.

### Frost Field cursor placement is now explicit canon

When the current GDD states that Frost Field is placed at the current shared
world-space pointer target exposed by Player Movement, treat that as direct GDD
evidence, not inference. Preserve the `frost-field -> player-movement`
prerequisite while the shared projection capability is unfinished. Do not emit
or preserve an unresolved question asking whether Frost Field is cursor-targeted
when that wording is present in current canon.

### Player Movement current builder/scene write surfaces

Under the current DoorPrototype architecture, converting Player Movement to the
required mouse-directed/Input-System behavior writes integration owned by
`DoorPrototypeSceneBuilder.cs` and the canonical DoorPrototype scene. In
addition to its Input Actions resource, `player-movement` must carry these
exclusive resources while that architecture remains current:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

This is especially required while the builder creates/configures PlayerMovement
and player-facing movement/control presentation. Remove these locks only if
repository evidence later moves those write surfaces elsewhere.

### Full restart closure shares the orchestrator integration surface

`floor-run-restart-bootstrap` and `floor-run-restart-persistent-closure` are two
stages of one restart orchestrator. Under the current builder-driven scene
architecture both stages share a logical orchestrator resource:

```text
logical:floor-run-restart-orchestrator
```

When either stage creates/wires/extends restart participants through the current
scene builder, it must also lock:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

Do not leave the persistent-closure task lock-free merely because its additional
participants are implemented later.

### Runtime input classification

A requirement such as "runtime gameplay input is routed through Unity Input
System/Input Actions rather than direct hardware polling" is a
`required_implementation` runtime/technical contract when mapped to gameplay
acceptance criteria. Development-agent process rules about who may edit or own
that work remain separate `required_process -> pipeline_constraint` records.
Do not classify the runtime input behavior itself as `required_process`.

### Preflight

Before returning a candidate, verify:

```text
enemy restart repositioning is performed by an enemy owner reset entry point
AND each spell explicitly consumes Input System/Input Actions
AND explicit Frost cursor placement is not left unresolved
AND Player Movement carries current builder/scene locks
AND both restart stages carry the shared logical orchestrator lock
AND persistent restart closure carries current builder/scene locks
```
''',
    )

    append_once(
        COVERAGE,
        r'''
---

## 2026-08-21 VERIFICATION ROUND 2 CLOSURE

### Runtime input is implementation behavior, not development process

Classify the GDD requirement that runtime gameplay input uses Unity Input
System/Input Actions and avoids direct hardware polling as
`required_implementation` (or `required_gameplay` only when the statement is
purely player-visible behavior). It may be represented by acceptance/validation
requirements on Player Movement, Fireball, Frost Field, Force Wave, and other
runtime consumers. Do not classify this runtime technical contract as
`required_process` merely because the GDD also contains Development Agent
Ownership Invariants nearby.

### Frost Field current canon

If the current GDD explicitly states that Frost Field is placed at the shared
cursor world-space target exposed by Player Movement, map that as direct required
implementation/gameplay evidence. An unresolved question asking whether Frost
Field is cursor-targeted is stale and should be removed by refinement.

### Restart ownership split

Represent "restart returns persistent enemies to their original authored region"
as behavior owned by an enemy reset/reposition entry point consumed by the Floor
Run/Restart Orchestrator. Do not map direct enemy Transform movement to the
orchestrator merely because it coordinates restart.
''',
    )

    append_once(
        REFINER,
        r'''
---

## 2026-08-21 VERIFICATION ROUND 2 CLOSURE

When the supplied findings touch these verified gaps, prefer the following
bounded repairs rather than inventing new architecture:

- Enemy restart: keep the Floor Run/Restart Orchestrator as coordinator and make
  the enemy pursuit/locomotion owner expose the reset/reposition operation that
  consumes authored spawn-region data and restores initial AI state.
- Spell input: add explicit Input System/Input Actions acceptance criteria to
  Fireball, Frost Field, and Force Wave; resource locks alone do not represent
  runtime behavior.
- Frost Field: current canon explicitly places it at Player Movement's shared
  world-space pointer target. Treat that as direct GDD evidence, retain the real
  prerequisite while that shared projection is unfinished, raise confidence
  when appropriate, and remove the obsolete unresolved targeting question.
- Player Movement: under the current builder-driven prototype, add the
  DoorPrototypeSceneBuilder file lock and canonical DoorPrototype scene lock in
  addition to the Input Actions lock.
- Restart closure: add the current builder/scene locks to
  `floor-run-restart-persistent-closure` and give both restart stages the shared
  `logical:floor-run-restart-orchestrator` lock.
- Runtime Input System coverage: correct a `required_process` classification to
  `required_implementation` instead of weakening the deterministic coverage
  validator or converting an acceptance criterion into a process record.

Do not preserve a human-review question when current GDD/repository evidence now
resolves it. Do not loosen deterministic representation rules to make a bad
classification pass.
''',
    )

    append_once(
        STRUCTURE,
        r'''
---

## 2026-08-21 VERIFICATION ROUND 2 CLOSURE

### Current builder/scene writers

Repository evidence currently makes the DoorPrototype scene builder and canonical
scene positive write/integration surfaces for Player Movement and for restart
orchestrator wiring. Therefore:

- `player-movement` must carry the builder file and canonical scene locks while
  converting/wiring the current generated PlayerMovement setup;
- `floor-run-restart-bootstrap` and
  `floor-run-restart-persistent-closure` must share
  `logical:floor-run-restart-orchestrator`;
- the persistent-closure stage must also carry the builder file and canonical
  scene locks when it extends the same builder-wired orchestrator with later
  reset participants.

These locks follow the current repository write surfaces. They may be removed in
a later reconciliation only when concrete repository architecture moves those
writes to separately owned assets or self-registration that no longer edits the
builder/canonical scene.

### Enemy reset ownership

A restart dependency may coordinate an enemy reset, but it must not make the
orchestrator the writer of enemy Transform/locomotion state. The enemy
pursuit/locomotion owner should expose the reset/reposition entry point, preserving
owner-controlled state boundaries.
''',
    )

    print("Installed verification round-2 closure guidance for six remaining root issues.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
