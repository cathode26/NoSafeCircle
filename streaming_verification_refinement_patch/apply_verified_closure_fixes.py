from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "2026-08-21 VERIFIED CLOSURE"

GDD = ROOT / "Docs" / "GDD" / "No_Safe_Circle_GDD.md"
RECONCILE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
COVERAGE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md"
REFINER = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md"
STRUCTURE = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "structure_auditor.md"
VERIFICATION_CREW = ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def replace_if_present(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    return replace_once(text, old, new, label)


def append_once(path: Path, marker: str, section: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    text += "\n" + section.strip() + "\n"
    path.write_text(text, encoding="utf-8")


def patch_gdd() -> None:
    text = GDD.read_text(encoding="utf-8")

    text = text.replace('revised_date: "2026-08-20"', 'revised_date: "2026-08-21"')
    text = text.replace(
        "Originally July 21, 2026; revised August 20, 2026",
        "Originally July 21, 2026; revised August 21, 2026",
    )

    old = (
        "- After the shared doorway-crossing state confirms that the wizard reached the forward side, "
        "the door automatically closes and locks; the player does not provide a second close/lock input. "
        "The completed automatic lock requests the small fixed health restoration through Player Health. "
        "Enemies actively pursuing the player that witnessed the escape and are blocked by that locked door "
        "begin attacking it; an enemy that has already lost the player does not begin attacking a locked door "
        "solely because it is nearby. Once locked, a door cannot be reopened, unlocked, or crossed again by "
        "the player — the floor is a forward-only escape sequence."
    )
    new = (
        "- After the shared doorway-crossing state confirms that the wizard reached the forward side, "
        "the door automatically closes and locks; the player does not provide a second close/lock input. "
        "The completed automatic lock requests the small fixed health restoration through Player Health. "
        "Any surviving enemy that is still actively tracking/pursuing the player and whose route to the player "
        "is blocked by that locked door begins attacking the door. No separate `witnessed escape` or "
        "line-of-sight-to-the-crossing state is tracked: if the enemy can still track the player, it is already "
        "aggroed/pursuing. An enemy that has already lost the player does not begin attacking a locked door solely "
        "because it is nearby. When the door breaks, those tracking/pursuing enemies continue their pursuit through "
        "the now-passable doorway. Once locked, a door cannot be reopened, unlocked, or crossed again by the player "
        "— the floor is a forward-only escape sequence."
    )
    text = replace_if_present(text, old, new, "locked-door pursuit canon")

    old_role = (
        "Qualifying locked-door attacks request damage through the Door and Interaction damage interface rather "
        "than mutating door durability or lifecycle state."
    )
    new_role = (
        "When a surviving enemy is still actively tracking/pursuing the player and a locked door blocks its route, "
        "Enemy Pursuit owns initiating the locked-door attack; no separate witness flag is required. The attack "
        "requests damage through the Door and Interaction damage interface rather than mutating door durability or "
        "lifecycle state, and pursuit continues through the doorway after the door breaks."
    )
    text = replace_if_present(text, old_role, new_role, "Enemy Pursuit locked-door role")

    GDD.write_text(text, encoding="utf-8")


def patch_verification_selection() -> None:
    text = VERIFICATION_CREW.read_text(encoding="utf-8")
    old = '''REFINER_WARNING_CATEGORIES = {
    "under_decomposition",
    "overgrouped_work",
    "shared_capability_hidden",
}
'''
    new = '''REFINER_WARNING_CATEGORIES = {
    "under_decomposition",
    "overgrouped_work",
    "shared_capability_hidden",
    "requirement_representation_problem",
}
'''
    text = replace_if_present(
        text,
        old,
        new,
        "refiner warning category selection",
    )
    VERIFICATION_CREW.write_text(text, encoding="utf-8")


def patch_stale_cursor_rules() -> None:
    reconcile_text = RECONCILE.read_text(encoding="utf-8-sig")
    old_reconcile = '''### Cursor reference is a shared convention, not automatically Player Movement ownership

The GDD says the cursor is the targeting reference for cursor-aimed spells and
cursor-targeted interactions. It does not, by that statement alone, assign a
shared cursor-world-target service to Player Movement.

Therefore:

- do not make Door Interaction, Frost Field, or Fireball depend on Player
  Movement solely because each needs the cursor targeting/projection
  convention;
- do not invent a `player-movement`-owned cursor-world-target interface unless
  current repository architecture or an explicit approved requirement
  establishes that ownership;
- a formal dependency is appropriate only if a concrete represented owner must
  create an unfinished shared targeting capability first.

This does not change the separate charged-Fireball dependency on Player
Movement when the movement-restriction interface is unfinished.
'''
    new_reconcile = '''### Shared pointer projection ownership and consumer dependencies

The current GDD explicitly assigns the shared cursor-to-gameplay-plane projection
to Player Movement. Player Movement exposes the resulting world-space pointer
target; movement, cursor-aimed spells, and Door/Interaction consume that shared
result instead of independently projecting pointer coordinates.

Therefore:

- do not invent a second cursor-world-target owner inside Fireball, Frost Field,
  or Door/Interaction;
- when the Player Movement-owned shared projection capability is still unfinished,
  a cursor-targeted executable consumer that requires it has a real prerequisite
  on `player-movement` (or a later concrete artifact/implementation that owns the
  same approved capability);
- once that specific owner-side capability exists and remaining Player Movement
  work is unrelated, re-evaluate the dependency under the normal existing-interface
  rule rather than preserving stale ordering forever;
- Force Wave remains the explicit player-centered radial exception and does not
  depend on pointer projection for aiming.

Charged Fireball may also independently depend on Player Movement while its
owner-controlled movement-restriction interface remains unfinished.
'''
    reconcile_text = replace_if_present(
        reconcile_text,
        old_reconcile,
        new_reconcile,
        "reconciliation cursor ownership rule",
    )
    reconcile_text = reconcile_text.replace(
        "AND cursor targeting has no invented Player Movement ownership",
        "AND shared cursor projection remains owned by Player Movement and unfinished consumers depend on that owner",
    )
    RECONCILE.write_text(reconcile_text, encoding="utf-8")

    coverage_text = COVERAGE.read_text(encoding="utf-8-sig")
    old_coverage = '''### Do not invent cursor ownership

The shared cursor targeting/reference convention does not by itself establish a
Player Movement-owned implementation interface.

Do not report a missing dependency from cursor-aimed spells or door targeting
to Player Movement solely because all use the cursor. Require a formal
dependency only when the candidate/repository contains a concrete shared
targeting owner whose unfinished capability is actually prerequisite.

The charged-Fireball movement-restriction interface remains a separate,
legitimate Player Movement dependency when unfinished.
'''
    new_coverage = '''### Shared pointer projection ownership is explicit canon

The current GDD explicitly makes Player Movement the owner of the shared
cursor-to-gameplay-plane projection and exposed world-space pointer target.
Cursor-aimed spells and Door/Interaction consume that owner-controlled result.

Do not classify this as merely a cursor convention. If the specific shared
projection capability is unfinished, a concrete cursor-targeted consumer may
legitimately require a dependency on `player-movement`. Once that capability is
implemented, unrelated remaining Player Movement work does not keep the consumer
blocked. Force Wave remains the player-centered radial exception.

The charged-Fireball movement-restriction interface is a separate possible
Player Movement prerequisite when unfinished.
'''
    coverage_text = replace_if_present(
        coverage_text,
        old_coverage,
        new_coverage,
        "coverage cursor ownership rule",
    )
    COVERAGE.write_text(coverage_text, encoding="utf-8")

    refiner_text = REFINER.read_text(encoding="utf-8-sig")
    old_refiner = '''### Cursor-targeting dependency discipline

Do not preserve a Door/Frost/Fireball -> Player Movement dependency when the only
reason is shared cursor targeting/reference.

The GDD's cursor convention does not by itself make Player Movement the owner of
a shared cursor-world-target service.

Keep Fireball -> Player Movement when the separate movement-restriction
interface is unfinished.
'''
    new_refiner = '''### Shared pointer projection dependency discipline

The current GDD explicitly makes Player Movement the owner of the shared
cursor-to-gameplay-plane projection and exposed world-space pointer target.
Do not invent a contrary pipeline discipline.

When that specific owner-side capability is still unfinished, preserve/add a
real dependency from a concrete cursor-targeted consumer such as Frost Field,
Fireball, or Door/Interaction when the consumer cannot execute or validate
without it. Once the projection capability exists and remaining Player Movement
work is unrelated, re-evaluate the edge under the normal existing-interface rule.

Force Wave is the player-centered radial exception. Fireball may additionally
require Player Movement while the separate movement-restriction interface is
unfinished.
'''
    refiner_text = replace_if_present(
        refiner_text,
        old_refiner,
        new_refiner,
        "refiner cursor ownership rule",
    )
    REFINER.write_text(refiner_text, encoding="utf-8")


def append_closure_guidance() -> None:
    append_once(
        RECONCILE,
        MARKER,
        r'''
---

## 2026-08-21 VERIFIED CLOSURE

These rules are derived from the current GDD plus the verified repository
architecture and supersede older prompt language where they conflict.

### Five-room content coverage must include all five named spaces

`five-room-content-authoring` or its later concrete descendants must durably
preserve the GDD's tactical/layout requirements for **all five** named spaces:
Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, and Final Room.
Do not let Ruined Entry or Final Room disappear merely because other rooms have
more specialized validation cases.

At the current coarse feature level, preserve the named-space requirements as
acceptance/decomposition context without inventing exact geometry.

### Cross-room pursuit is executable behavior

Enemy pursuit/search must explicitly require actual forward traversal through
open and broken doorways when navigation/passability permits it. The weaker
statement "crossing a doorway does not clear pursuit" is not sufficient by
itself. Preserve an acceptance criterion and validation requirement that a
tracking/pursuing enemy can follow the player or last-known position through an
open/broken doorway without losing target solely because of the crossing.

### Locked-door attack uses existing tracking/pursuit state

There is no separate `witnessed escape` state. A surviving enemy that is still
actively tracking/pursuing the player and whose route is blocked by the newly
locked door attacks that door through the Door-owned damage interface. An enemy
that has already lost the player does not attack the door merely because it is
nearby. When the door breaks, the still-tracking enemy continues pursuit through
the now-passable doorway.

### Current scene-builder writer locks

Under the current prototype architecture, if implementing a spell or other
runtime item requires adding/configuring that component or its feedback on
objects generated/maintained through
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs`, the
work item must lock both:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

This currently applies to Fireball, Frost Field, and Force Wave when their
implementation/integration writes through that builder/scene. Do not carry the
locks forward if repository evidence later moves those write surfaces to a
separately owned prefab/asset. Locks follow actual write/integration surfaces,
not subsystem membership.

### Enemy archetype prefab composition must have an owner

The required Melee Enemy and Ranged Enemy are world-space SpriteRenderer prefab
archetypes, not merely disconnected pursuit/health/attack components. At the
current coarse graph level, `melee-enemy` and `ranged-enemy` should each own or
explicitly deliver a usable assembled archetype prefab that integrates the
shared pursuit/locomotion, Enemy Health/Defeat, Active Enemy Registry
participation, archetype attack behavior, and world-space SpriteRenderer
presentation required for that archetype. Dungeon Encounter consumes those
usable archetypes for placement/content authoring.

Do not create another composition task unless repository architecture actually
establishes a separate concrete owner.

### Final preflight

Before returning the candidate, verify that:

```text
all five named spaces remain durably represented
AND pursuit explicitly crosses open/broken doorways
AND locked-door attack uses tracking/pursuit state rather than a witness flag
AND unfinished shared pointer projection has correct consumer prerequisites
AND current builder/scene writers carry matching locks
AND Melee/Ranged archetype assembly has a concrete owner
```
''',
    )

    append_once(
        COVERAGE,
        MARKER,
        r'''
---

## 2026-08-21 VERIFIED CLOSURE

### Split compound GDD passages by semantic requirement

When one GDD paragraph contains both a runtime owner/consumer contract and a
development-process ownership invariant, emit separate conceptual requirement
rows instead of forcing the entire passage into one classification.

Example:

```text
runtime Frost Field cast/slowdown ownership behavior
    -> required_gameplay or required_implementation
    -> acceptance_criterion on the concrete runtime owner(s)

Development Agent Ownership Invariant governing that split
    -> required_process
    -> pipeline_constraint
```

Do not classify a runtime acceptance criterion as `required_process`, and do not
classify the process invariant as gameplay merely because both originate in the
same paragraph.

### Required-room inventory

Inventory Ruined Entry, Bone Archive, Chapel of Ash, Lower Vault, and Final Room
individually. All five must have durable representation under five-room content
work or later concrete descendants. A room's requirement is not represented
merely because the feature says "five rooms" generically.

### Pursuit/door semantics

Treat actual pursuit through open/broken doorways as required gameplay behavior.
Treat locked-door attack eligibility as existing tracking/pursuit state plus a
locked door blocking the route; no separate witness-state requirement exists.
''',
    )

    append_once(
        REFINER,
        MARKER,
        r'''
---

## 2026-08-21 VERIFIED CLOSURE

Do not invent named "pipeline disciplines" or dependency-exclusion policies
that are unsupported by the current GDD, repository evidence, or deterministic
pipeline invariants. In particular, the GDD explicitly assigns shared
cursor-to-gameplay-plane projection to Player Movement.

When repairing current findings, preserve/correct these established contracts:

- all five named room requirements, including Ruined Entry and Final Room, must
  remain durably represented under five-room content work;
- enemy pursuit must explicitly support forward traversal through open/broken
  doorways rather than merely saying a doorway crossing does not clear target;
- a tracking/pursuing enemy blocked from the player by a locked door attacks it;
  no separate witness flag is required, and pursuit continues after breach;
- if the Player Movement-owned shared pointer projection is unfinished,
  cursor-targeted consumers that require it have a real prerequisite on that
  owner until the specific capability exists;
- Fireball, Frost Field, and Force Wave receive prototype scene-builder and
  canonical-scene locks only when current evidence shows their implementation
  writes/integrates through those resources;
- Melee Enemy and Ranged Enemy must each have an owner for usable prefab/archetype
  assembly rather than leaving pursuit, health, attack, and presentation as
  disconnected responsibilities.

If an early proposed repair conflicts with any of these rules, reject that
portion and synthesize the correction from the original candidate plus current
canon/evidence.
''',
    )

    append_once(
        STRUCTURE,
        MARKER,
        r'''
---

## 2026-08-21 VERIFIED CLOSURE

Apply these additional structural checks:

- if Player Movement's canon-owned shared pointer projection is unfinished,
  verify that concrete cursor-targeted consumers which require that capability
  have a real dependency on its concrete owner;
- verify pursuit acceptance includes actual traversal through open/broken
  doorways, not only target retention across a crossing;
- verify Melee/Ranged archetype work has a concrete owner for producing usable
  assembled prefab archetypes consumed by encounter authoring;
- when Fireball/Frost Field/Force Wave currently integrate through
  `DoorPrototypeSceneBuilder.cs` and the canonical DoorPrototype scene, verify
  matching writer locks on those exact resources; do not add those locks if
  current evidence shows the task no longer writes through them;
- do not introduce any separate `witnessed escape` state: locked-door attack
  eligibility derives from active tracking/pursuit plus the locked door blocking
  the enemy's route to the player.
''',
    )


def main() -> int:
    patch_gdd()
    patch_verification_selection()
    patch_stale_cursor_rules()
    append_closure_guidance()
    print("Applied approved 2026-08-21 verification closure fixes.")
    print("Updated root canon: Docs/GDD/No_Safe_Circle_GDD.md")
    print("Updated reconciliation/verifier/refiner guidance and refiner finding selection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
