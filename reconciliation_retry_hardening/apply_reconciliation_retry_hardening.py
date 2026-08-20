from __future__ import annotations

from pathlib import Path
import shutil

REPO_ROOT = Path.cwd()
PACKAGE_ROOT = Path(__file__).resolve().parent
UPDATED_ROOT = PACKAGE_ROOT / "updated"

PROMPTS = {
    "Pipeline/Reconciliation/prompts/reconcile.md": r"""

---

# Retry hardening: shared runtime ownership and dependency semantics

The current GDD now makes several shared runtime capabilities and ownership
boundaries explicit. Preserve them directly in the work graph instead of
re-inferring alternate architectures.

## Dependency versus exclusive-resource lock

A `depends_on` edge is valid only when one work item consumes behavior,
state, an interface, or an integration foundation that another work item must
create first.

A shared script, scene, prefab, builder, or other write surface is **not** by
itself a dependency. When otherwise-independent tasks merely collide on a
non-merge-safe resource, represent the collision with the same
`exclusive_resources` key on both tasks and keep them dependency-independent.

Do not serialize tasks with a dependency just because they edit the same door
script, scene builder, scene, prefab, or other shared integration file.

## Required shared-capability ownership

When two or more required behaviors consume the same reusable runtime state or
interface, preserve one authoritative owner. Do not silently implement the same
capability separately in multiple consumers.

The current GDD establishes these specific ownership boundaries:

- the Door and Interaction system owns shared doorway-crossing state;
  close/lock behavior and final-victory behavior consume that same state;
- Melee and Ranged Enemy attacks consume the shared Player Health damage
  interface; they do not own separate player-health state;
- the Enemy Pursuit side owns persistent Active Enemy Registry bookkeeping;
  encounter admission consumes that registry instead of maintaining a second
  count;
- enemy locomotion/pursuit consumes the shared gameplay navigation/locomotion
  layer instead of choosing or configuring navigation technology independently;
- the reusable visual Tilemap/SpriteRenderer world foundation is distinct from
  authoring the five named rooms and encounters.

If such a shared capability is required, absent, and independently reusable,
represent it as its own implementation/foundation work item when doing so is
supported by the GDD. Consumers must depend on that owner when the capability
must exist before they can execute or be meaningfully validated.

## Consumer prerequisite closure

Before returning, inspect each acceptance criterion and validation requirement
for consumed runtime capabilities. For each consumed capability, exactly one of
these must be true:

1. the current work item explicitly owns it; or
2. it already exists as implemented/complete work; or
3. the current work item has a real dependency on the represented owner.

Do not leave a required navigation, health, doorway-crossing, registry, damage,
or similar integration prerequisite only in notes or an unresolved question.

## Human-approved technical foundations

The GDD intentionally leaves the concrete Unity navigation implementation as a
human-approved technical choice. Do not make locomotion-dependent enemy work
ready before a minimal gameplay navigation/locomotion layer exists.

If the current repository does not establish that technical choice, represent
the navigation foundation conservatively (for example
`human_integration_required` when the next step genuinely requires human Unity
architecture/editor judgment) and make locomotion-dependent consumers depend on
it. Do not block that foundation on completion of all five room visuals or
encounter content.

## Runtime foundation versus deferred content

Keep already-specified reusable runtime foundations separate from deferred
content authoring:

- Active Enemy Registry bookkeeping can be implemented before exact room
  encounter layouts and trigger placement are authored;
- encounter admission consumes the registry and applies the fifteen-enemy rule;
- visual Tilemap/SpriteRenderer authoring conventions do not include authoring
  all five required rooms;
- room-specific layout/encounter authoring may remain
  `needs_future_decomposition` without hiding the reusable runtime foundations.

## Required process constraints

The GDD's **Development Agent Ownership Invariants** are mandatory process
requirements. Preserve them as one or more typed `pipeline_constraint` records,
not only as prose inside work-item notes, evidence, or acceptance criteria.

In particular, preserve the rule that an agent must not bypass another agent's
owned runtime interface merely because the systems interact.

## Execution-scope final check

An open item may be `single_agent` only when its own responsibility is bounded
and every required external integration surface is already implemented or
represented as a prerequisite. If a required human architecture decision is
still unresolved, or the item bundles reusable foundation work with broad room
content authoring, do not call it `single_agent`.
""",

    "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": r"""

---

# Retry hardening: dependency and shared-capability audit

Apply these additional structural checks to the candidate.

## False dependency check

A shared file/scene/prefab/builder collision is not a dependency. Flag a
`depends_on` edge when its only justification is that two tasks modify the same
resource. The correct representation for a pure write collision is a shared
`exclusive_resources` key.

## Shared capability owner check

When multiple tasks consume the same required runtime state/interface, verify
that the graph has one authoritative owner rather than duplicate hidden
implementations.

Current GDD ownership examples that should be represented structurally:

- shared doorway-crossing state is owned by Door and Interaction and consumed
  by close/lock and final victory;
- enemy attacks consume Player Health;
- persistent active-enemy bookkeeping is owned by the shared Active Enemy
  Registry and consumed by encounter admission;
- enemy pursuit/locomotion consumes the shared gameplay
  navigation/locomotion layer;
- visual world authoring foundation is distinct from five-room content
  authoring.

Flag missing dependencies from a consumer to a required owner when the owner
must exist first. Also flag an unnecessary dependency when interaction can be
handled through an already-existing interface plus exclusive-resource locking.

## Foundation/content split check

Do not allow a reusable foundation to absorb deferred content merely because
both eventually touch the same scene. In particular:

- navigation/walkability foundation must not require completed five-room visual
  authoring;
- Tilemap/SpriteRenderer authoring conventions must not claim responsibility
  for authoring all five room layouts/encounters;
- Active Enemy Registry bookkeeping must not be hidden behind exact encounter
  placement/trigger authoring.

## Ownership-invariant process representation

Verify that the GDD's Development Agent Ownership Invariants survive as typed
`pipeline_constraint` records. If the behaviors are only scattered across work
items and no durable process constraint represents the mandatory ownership
boundary, report a requirement-representation problem.
""",

    "Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md": r"""

---

# Retry hardening: execution-readiness boundaries

Use these additional checks when judging `single_agent`,
`needs_execution_decomposition`, and `human_integration_required`.

## External integration prerequisite check

A work item is not safely `single_agent` merely because its internal code is
small. If its acceptance/validation requires a shared runtime capability that
is not implemented and is not represented as a prerequisite, report an
execution-scope problem.

Pay special attention to:

- enemy attacks requiring Player Health;
- enemy pursuit/search requiring a gameplay navigation/locomotion layer;
- door locking and final victory requiring shared doorway-crossing state;
- encounter admission requiring Active Enemy Registry bookkeeping.

## Human-approved navigation decision

The current GDD deliberately leaves the concrete Unity navigation technology as
a human-approved technical choice. If the repository has not established that
choice, a navigation-foundation item should not be treated as an ordinary
single-agent coding handoff when the next meaningful step is architectural or
Unity-editor judgment.

Locomotion-dependent enemy work should remain blocked by that represented
foundation rather than receiving the unresolved decision implicitly.

## Foundation versus whole-content scope

Flag `single_agent` when a supposedly reusable foundation also claims broad
content-authoring responsibility such as building all five rooms, all encounter
layouts, or other independently verifiable content bundles.

A visual Tilemap/SpriteRenderer foundation may establish conventions and
visual/gameplay separation without authoring all five named room layouts.
An Active Enemy Registry may establish bookkeeping without authoring encounter
placements/triggers.

## Validation availability

Do not require a task to own deferred room content solely so a future
room-specific validation can eventually run. Keep the mechanism bounded and
record the room-specific check as validation that becomes executable when the
required content exists. If the task currently claims it can fully validate a
missing room-specific scenario, flag the scope claim rather than broadening the
task automatically.
""",

    "Pipeline/Reconciliation/prompts/verification/refiner.md": r"""

---

# Retry hardening: canonical repair rules

When pass-1 findings touch dependencies, shared state, execution scope, or
requirement representation, refine toward the current GDD's explicit ownership
model rather than inventing an alternate architecture.

## Dependency repairs

- Remove a dependency whose only purpose is serializing tasks that write the
  same file/scene/prefab/builder. Preserve or add the appropriate shared
  `exclusive_resources` lock instead.
- Add a dependency when a consumer genuinely requires a represented runtime
  owner/foundation to exist first.
- Do not use a dependency merely because two systems interact conceptually.

## Canonical shared owners from the current GDD

Preserve these boundaries when they are relevant to a finding:

- Door and Interaction owns shared doorway-crossing state. Door close/lock and
  final-victory logic consume it rather than implementing independent crossing
  detectors.
- Melee and Ranged Enemy attacks consume the shared Player Health damage
  interface.
- Enemy Pursuit owns shared Active Enemy Registry bookkeeping for persistent
  active enemy objects; Dungeon Encounter consumes the registry for admission
  policy and does not maintain a second count.
- Enemy locomotion/pursuit consumes a shared gameplay navigation/locomotion
  foundation. The concrete navigation technology is human-approved.
- The visual Tilemap/SpriteRenderer world foundation is reusable architecture,
  not the five-room content-authoring task.

When a finding shows one of these reusable capabilities is absent from the
candidate, add/narrow a supported work item or dependency as needed rather than
copying the capability into every consumer.

## Active-enemy refinement

Keep bookkeeping and admission policy conceptually separate:

- registry responsibility: persistent active set/count/capacity and updates on
  activation/defeat;
- encounter-admission responsibility: query capacity and delay/reduce new
  encounter activation before ever removing existing persistent enemies.

Do not make exact room layouts, encounter placements, or trigger authoring a
prerequisite for the reusable registry foundation.

## Navigation and human integration

If the navigation technology is still unresolved in current repository state,
repair the candidate so the shared navigation/locomotion foundation reflects
that human-approved decision and locomotion-dependent work depends on the
foundation. Do not solve this by making the visual world foundation own every
room or by silently choosing a navigation package.

## Typed process constraints

If coverage identifies the Development Agent Ownership Invariants as required
process rules, add/preserve an appropriate typed `pipeline_constraint` record.
Do not consider the requirement satisfied merely because individual work items
happen to contain related prose.

## Scope discipline

Do not introduce new mechanics, balance values, room layouts, encounter
placements, or navigation technology while repairing these findings. The goal
is to make ownership, prerequisite, resource-lock, and process representation
match the already-approved GDD.
""",
}


def append_block(path: Path, block: str) -> bool:
    marker = block.strip().splitlines()[0]
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"already patched: {path}")
        return False
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + block.lstrip("\n"), encoding="utf-8")
    print(f"patched prompt: {path}")
    return True


def copy_updated_gdd() -> None:
    # The revised GDD files were already copied into the repository manually.
    # Confirm they exist, then leave them untouched.
    for rel in (
        Path("Docs/GDD/No_Safe_Circle_GDD.md"),
        Path("Docs/GDD/No_Safe_Circle_GDD_Final.docx"),
    ):
        dst = REPO_ROOT / rel
        if not dst.exists():
            raise FileNotFoundError(
                f"Expected already-updated repository GDD is missing: {dst}"
            )
        print(f"leaving existing GDD unchanged: {dst}")


def main() -> int:
    expected = REPO_ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"
    if not expected.exists():
        raise RuntimeError(
            "Run this script from the NoSafeCircle repository root. "
            f"Could not find {expected}"
        )

    copy_updated_gdd()

    for rel, block in PROMPTS.items():
        path = REPO_ROOT / rel
        if not path.exists():
            raise FileNotFoundError(f"Expected prompt not found: {path}")
        append_block(path, block)

    print()
    print("Reconciliation retry hardening applied.")
    print("Recommended validation:")
    print(
        "docker compose run --rm claude python3 "
        "Pipeline/Reconciliation/verification_smoke_test.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())