from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
PROMPT = ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"

MARKER = "## Mandatory canonical coverage preflight"

BLOCK = r"""
## Mandatory canonical coverage preflight

Immediately before returning the final JSON, perform a second complete audit
that is independent of the dependency-kind preflight.

This audit answers:

> Has every mandatory GDD gameplay, ownership, validation, delivery, and
> pipeline rule been given a durable representation in the reconciliation?

Do not assume that a requirement is represented merely because related work
exists somewhere in the graph. The requirement must be attached to the correct
owner as one of:

- a concrete `implementation`/`artifact` work item;
- an `acceptance_criterion` on the owning work;
- a `validation_requirement` on the owning work;
- a typed `non_code_requirements` record using
  `non_code_requirement`, `delivery_requirement`, or `pipeline_constraint`;
- a deliberately deferred design/content feature when the GDD explicitly
  leaves the design unresolved.

If a required behavior needs runtime code and no existing executable work item
actually owns that behavior, create a concrete implementation work item rather
than hiding the behavior inside a feature note or another system's validation.

### Canonical coverage assertions for the current GDD

Before returning, explicitly verify all of the following.

#### Enemy shared health / damage / defeat ownership

The graph must contain concrete executable ownership for the shared enemy
health/damage/defeat capability required by the GDD.

That owner must cover, at minimum:

- enemies have health;
- spells can damage enemies through the owning interface;
- defeat updates the enemy's defeated state;
- defeat removes the enemy from Active Enemy Registry active-count bookkeeping;
- defeat/reset state participates in full floor-run restart closure.

Do not treat Fireball, Active Enemy Registry, or an enemy archetype as a
substitute merely because each interacts with this capability. If no concrete
owner exists, create one.

#### Locked-door enemy attack ownership

The graph must contain concrete executable ownership for the required behavior
where an enemy that is actively pursuing the player, witnessed the escape, and
is blocked by the locked door attacks that door until the door breaks or the
relevant pursuit condition changes.

Do not represent this only as:

- a Door lifecycle acceptance criterion;
- generic pursuit behavior;
- a validation note;
- deferred encounter content.

Door owns door state/durability. Enemy behavior owns causing the attack/damage
when the GDD conditions are satisfied. Represent the executable owner.

#### Persistent-state reset completeness

For every current implementation that owns run-persistent state, compare the
repository implementation against the GDD restart contract.

A component is NOT fully `implemented`/`complete` if the GDD now requires an
owner-controlled reset entry point and the current repository implementation
does not expose that reset participation yet.

In particular, inspect current Player Mana behavior rather than inheriting an
older completion claim. Spending and delayed regeneration alone do not satisfy
the current full-run reset contract.

Use:

- `partial` + `open` when meaningful behavior exists but reset participation is
  missing;
- `implemented` + `complete` only when all current GDD-required behavior owned
  by that work item is supported by current repository evidence.

Apply the same reasoning to every other run-persistent owner.

#### Single continuous floor / scene constraint

The required game is one continuous Unity floor/scene containing all five
connected spaces. No room-to-room scene loading or cross-scene state transfer
is required for the capstone.

This rule must be represented durably, normally as an acceptance criterion or
validation requirement on the world/floor/scene implementation and on any
build-scene registration work where appropriate.

Do not let "five rooms exist" substitute for "all five exist in one continuous
scene/floor."

#### Compile-before-validation gate

The GDD requires generated/changed C# to compile before gameplay validation
proceeds.

Represent this as a required pipeline/process rule. Do not leave it implicit in
a generic test checklist.

#### Isolated execution and task handoff requirements

The GDD requires implementation work to execute in isolated branches/workspaces
rather than allowing concurrent agents to mutate one shared checkout.

It also requires completed task handoff evidence including the required
changed-file list / implementation summary / known risks / Play Mode validation
checklist / source-control commit or equivalent durable handoff named by the
GDD.

Represent these as typed pipeline constraints or required process records.
Do not omit them because they are not gameplay code.

#### Agent scope and canon discipline

The graph/pipeline representation must preserve the rule that implementation
agents do not redesign mechanics, invent scope, reinterpret ownership, or
silently expand the GDD while executing a task.

Agents receive only the approved bounded context for the active task.

Represent these as pipeline constraints. Do not rely on prompt prose elsewhere
in the repository as the only durable representation.

#### Development Agent Ownership Invariants

Preserve the GDD's explicit ownership boundaries as durable criteria on the
owning work:

- Wizard Combat initiates spell behavior but does not own enemy locomotion,
  pursuit/search state, enemy attacks, door lifecycle, or encounter admission.
- Enemy Pursuit / shared enemy locomotion owns pursuit/search locomotion,
  Frost slow application/restore, forced displacement response, and enemy
  attack execution where the GDD assigns it.
- Door and Interaction owns doorway crossing and semantic door lifecycle state.
- Dungeon Encounter owns encounter activation/admission policy.
- Unity Validation validates required behavior and integration but does not
  redefine gameplay ownership.

Do not collapse these boundaries merely to reduce work-item count.

#### Generated-development-art import boundary

If development-time generation produces tiles, props, sprites, or similar art,
the resulting output is imported as ordinary Unity assets.

Generation does NOT automatically imply:

- prefab creation;
- collider setup;
- sorting configuration;
- scene placement;
- gameplay integration.

Represent this as a required process/validation constraint on the relevant
content/asset pipeline work. Do not mark gameplay integration complete merely
because generated art files exist.

#### Failed-task retry policy

Preserve the required failed-task behavior: reduce the failed task's scope and
context before retrying rather than resubmitting the entire project or broad
repository context.

Represent this as a typed `pipeline_constraint`.

#### Player-experience success criteria

The GDD's player-experience success criteria are required validation outcomes,
not optional commentary.

Attach them as `validation_requirements` to the work that owns the behavior,
including at least:

- players can understand the five-second door-opening rule and why attempts
  reset;
- players can understand that surviving enemies remain persistent threats
  across doors/rooms;
- players can read why they failed through required health/damage/door/failure
  feedback.

Do not create duplicate gameplay work solely to represent these checks; attach
them to the correct owning implementation items.

### Final canonical coverage assertion

Do not return the candidate until this is true:

```text
for every mandatory GDD requirement:
    exactly one durable representation strategy is identifiable
    AND the owning work/non-code record is present
    AND runtime behavior with no executable owner has a concrete implementation
    AND validation/process requirements are not silently dropped
    AND current repository completion claims include all newly-required owner
        contracts such as floor-run reset participation
```

If this audit finds a missing representation, repair the candidate and run the
coverage preflight again before returning JSON.

Do not solve a coverage failure by inventing new game design. Use the current
GDD's existing ownership, process, validation, and deferred-design rules.
""".strip()

text = PROMPT.read_text(encoding="utf-8")

if MARKER in text:
    print(f"already patched: {PROMPT}")
else:
    text = text.rstrip() + "\n\n---\n\n" + BLOCK + "\n"
    PROMPT.write_text(text, encoding="utf-8")
    print(f"patched: {PROMPT}")

print()
print("Canonical reconciliation coverage preflight hardening applied.")
print("No GDD, Python validator, verification prompt, or Tasks/*.yaml files were changed.")
