from pathlib import Path

ROOT = Path.cwd()

RECONCILE = ROOT / "Pipeline/Reconciliation/prompts/reconcile.md"
COVERAGE = ROOT / "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md"
REFINER = ROOT / "Pipeline/Reconciliation/prompts/verification/refiner.md"

RECONCILE_REQUIRED = "## Final graph-edge and shared-capability closure preflight"
COVERAGE_REQUIRED = "## Final verifier closure: deferred feature prerequisites and runtime-AI classification"
REFINER_REQUIRED = "## Final verifier closure repair: reject illegal feature edges and preserve runtime-AI non-code scope"

RECONCILE_MARKER = "## Spell/reset, feedback, and ownership closure preflight"
COVERAGE_MARKER = "## Spell/reset and ownership coverage closure"
REFINER_MARKER = "## Spell/reset and ownership repair closure"

RECONCILE_BLOCK = r"""

---

## Spell/reset, feedback, and ownership closure preflight

Apply this after the earlier graph-edge closure preflight and before returning
the candidate.

### Do not assign spell-owned state to Player Mana

Player Mana owns the shared mana resource and its own mana-regeneration timing
state. It does not become the owner of every spell's cooldown, charge, active
cast, or other spell-local state merely because all spells spend mana.

For the current GDD:

- `player-mana` owns current mana plus its own post-cast regeneration-delay
  state and exposes/reset those through its owner-controlled interface;
- `force-wave` owns its long cooldown state and must expose an owner-controlled
  floor-run reset for that cooldown;
- `fireball` owns its tap/charge/cast state and must expose an owner-controlled
  floor-run reset for any such state that can be active when a restart occurs;
- `frost-field` owns its Wizard-Combat-side cast/placement/active-field state and
  must expose an owner-controlled floor-run reset for that owned state;
- enemy-side Frost slowdown/application/restoration state remains owned by the
  Enemy Pursuit/status-effect side and is not transferred to the Frost Field
  casting item.

Do not claim that `player-mana` resets generic "spell cooldowns" unless a
concrete repository implementation actually places that state inside Player
Mana and the ownership remains consistent with the GDD.

### Full floor-restart closure includes required spell owners

The staged/current-owner restart task and the full persistent-systems closure
are different.

The early staged orchestrator may validate only against persistent owners that
currently exist. The full `floor-run-restart-persistent-closure` cannot be
complete until every required run-persistent owner exposes a reset contract and
is invoked through that contract.

When the spell reset interfaces above are still unfinished, preserve formal
dependencies from the full persistent closure to the concrete spell owners:

- `fireball`;
- `frost-field`;
- `force-wave`.

Also preserve the existing dependencies on Player Mana and the other persistent
owners required by the GDD. The dependency reason should name the unfinished
owner-side reset capability, not merely say that the systems conceptually
interact.

Do not add these spell dependencies to an intentionally narrow early-stage
restart task merely because the future spell work exists.

### Frost Field feedback is required acceptance behavior

The Wizard Combat Agent owns Frost Field casting, mana cost, and feedback.

`frost-field` acceptance criteria must require player-facing feedback that makes
the cast and/or active field readable to the player. Do not invent a specific
particle system, color, sound, animation, shader, or other presentation detail
that the GDD does not specify.

A safe representation is equivalent to:

```text
Frost Field provides player-facing feedback that makes the cast and active field
readable while preserving the Enemy Pursuit Agent's ownership of actual
slowdown application/restoration.
```

Feedback must be acceptance behavior, not only a validation note.

### Preserve explicit spell/enemy behavior in acceptance criteria

Do not leave these requirements only in GDD evidence:

- `fireball`: cursor-aimed tap/charge casting, with Force Wave remaining the
  explicit player-centered no-cursor exception;
- `ranged-enemy`: keeps moderate distance and fires a **slow, telegraphed**
  ranged shot; line-of-sight/occlusion remains required as already specified.

These are runtime behaviors and belong in acceptance criteria on their owners.

### Player Experience failure readability remains validation scope

Preserve the Section 3 Player Experience Success Criterion that failure is
readable, including poor positioning, low mana, wasting Force Wave before an
immediate threat, and waiting too long.

Map the applicable portions to validation requirements on the owning work. Do
not invent a separate gameplay feature solely to represent the validation
obligation.

### Door input/selection write surface

When `door-open-interaction` must change the current interaction input/selection
implementation, inspect repository truth and include
`Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs` in
`exclusive_resources` if that file is expected to be modified.

Do not omit the file lock merely because DoorInteractable owns the door state.
Input/selection wiring and door lifecycle state are separate write surfaces.

### Cursor reference is a shared convention, not automatically Player Movement ownership

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

### Staged restart execution scope

A narrowly bounded current-owner restart orchestrator may be `single_agent`
when it only subscribes to the existing zero-health signal and invokes a small,
known set of already-defined owner reset interfaces.

Do not classify that staged task as `needs_execution_decomposition` solely
because future persistent owners will later join the full restart closure. The
full persistent-systems closure may still require broader execution
decomposition when its actual scope warrants it.

### Final assertion

Before returning JSON, verify:

```text
Player Mana does not absorb spell-local state by convenience
AND Force Wave owns/reset its cooldown
AND Fireball owns/reset its charge/cast state
AND Frost Field owns/reset its casting-side state
AND full persistent restart closure depends on unfinished required spell reset owners
AND Frost Field feedback exists as acceptance behavior
AND Fireball cursor-aiming is explicit
AND Ranged Enemy slow/telegraphed attack is explicit
AND cursor targeting has no invented Player Movement ownership
AND door interaction locks PlayerInteractionController.cs when it must modify it
```
"""

COVERAGE_BLOCK = r"""

---

## Spell/reset and ownership coverage closure

Apply these mappings before returning material findings.

### Separate restart gameplay from reset-interface architecture

The player-facing requirement "zero health restarts the entire floor" is
`required_gameplay`.

The technical ownership requirement that each run-persistent owner exposes its
own reset entry point and that the Floor Run/Restart Orchestrator invokes those
owned interfaces is `required_implementation`.

Coverage of full restart closure must therefore verify that required
run-persistent owners are represented. For current required spells:

- Force Wave's long cooldown is spell-owned reset state;
- Fireball's charge/cast state is Fireball-owned reset state;
- Frost Field's casting-side active/cast state is Frost-Field-owned reset
  state;
- Player Mana owns mana and its own regeneration-delay state, not generic
  spell-local state.

If the candidate's full persistent restart closure omits unfinished spell-owner
reset contracts/dependencies, that is a legitimate coverage/structure issue.

Do not demand future spell dependencies on an intentionally narrow staged
current-owner restart task.

### Frost Field feedback

The Wizard Combat Agent's responsibility for Frost Field casting, mana cost,
and feedback is runtime gameplay coverage.

Require an acceptance criterion on `frost-field` for readable player-facing
cast/active-field feedback. Do not require a specific visual/audio treatment
that the GDD does not choose.

### Ownership invariants are process requirements when auditing the invariant itself

The Section 4 Development Agent Ownership Invariants are mandatory development
process constraints.

When inventorying the invariant that Wizard Combat triggers Frost Field while
Enemy Pursuit/status-effect ownership applies and restores enemy slowdown, use:

```text
classification: required_process
representation: pipeline_constraint
```

when the candidate contains the corresponding typed pipeline constraint.

Runtime acceptance criteria on `frost-field` and the enemy status-effect owner
may additionally embody the behavior split, but do not map the
`required_process` inventory row to `acceptance_criterion` merely because those
runtime criteria also exist.

In other words:

```text
process ownership invariant -> pipeline_constraint
runtime Frost cast behavior -> acceptance_criterion
runtime enemy slowdown apply/restore -> acceptance_criterion
```

Keep those inventory rows conceptually separate.

### Preserve explicit runtime details

Treat these as required gameplay acceptance behavior, not GDD-evidence-only
context:

- Fireball is cursor-aimed;
- Ranged Enemy fires a slow, telegraphed shot while maintaining its moderate
  distance behavior;
- Frost Field provides readable player-facing casting/field feedback.

### Do not invent cursor ownership

The shared cursor targeting/reference convention does not by itself establish a
Player Movement-owned implementation interface.

Do not report a missing dependency from cursor-aimed spells or door targeting
to Player Movement solely because all use the cursor. Require a formal
dependency only when the candidate/repository contains a concrete shared
targeting owner whose unfinished capability is actually prerequisite.

The charged-Fireball movement-restriction interface remains a separate,
legitimate Player Movement dependency when unfinished.

### Player Experience validation

The failure-readability success criterion, including poor positioning, low mana,
Force Wave misuse/unavailability, and waiting too long, must remain represented
through validation requirements on the work that owns those behaviors. Do not
classify the criterion as unrepresented merely because it has no standalone
work-item node.
"""

REFINER_BLOCK = r"""

---

## Spell/reset and ownership repair closure

Use these rules when repairing the candidate after verification.

### Repair reset ownership on the real state owner

Do not fix restart findings by putting all player-resource/cooldown reset state
into `player-mana`.

Preserve ownership as follows:

- Player Mana: mana and Player-Mana-owned regeneration-delay state;
- Force Wave: Force-Wave-owned long cooldown;
- Fireball: Fireball-owned charge/cast state;
- Frost Field: Frost-Field-owned Wizard-Combat-side cast/placement/active-field
  state;
- enemy Frost slowdown/restoration: Enemy Pursuit/status-effect owner.

Add/preserve owner-controlled reset acceptance on the corresponding work item.

When those required spell reset interfaces are unfinished, add/preserve
dependencies from the **full** persistent restart closure to `fireball`,
`frost-field`, and `force-wave`. Do not add them to a deliberately staged
current-owner restart task solely because they will exist later.

### Repair Frost Field feedback without inventing presentation

If Frost Field lacks its Wizard-Combat-owned feedback responsibility, add an
acceptance criterion requiring readable player-facing cast/active-field
feedback.

Do not invent particle, audio, color, animation, or shader requirements.

### Repair process-invariant mapping instead of rewriting gameplay

If a coverage finding maps the Wizard Combat / Enemy Pursuit Frost ownership
split as:

```text
required_process -> acceptance_criterion
```

preserve the runtime acceptance criteria but correct the process representation
to the existing typed `pipeline_constraint`.

Do not delete the runtime criteria and do not add duplicate gameplay work solely
to satisfy the process inventory row.

### Preserve missing explicit runtime criteria

When absent, repair the owner's acceptance criteria so that:

- Fireball is explicitly cursor-aimed;
- Ranged Enemy explicitly fires a slow, telegraphed shot and keeps moderate
  distance;
- Frost Field has player-facing feedback.

### Cursor-targeting dependency discipline

Do not preserve a Door/Frost/Fireball -> Player Movement dependency when the only
reason is shared cursor targeting/reference.

The GDD's cursor convention does not by itself make Player Movement the owner of
a shared cursor-world-target service.

Keep Fireball -> Player Movement when the separate movement-restriction
interface is unfinished.

### Write-surface/resource repair

If Door Open/Interaction changes the existing input/selection implementation,
add/preserve:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerInteractionController.cs
```

as an exclusive resource when repository evidence shows that file is part of
the write surface.

### Validation and execution-scope cleanup

Preserve the player-experience failure-readability validation obligations,
including poor positioning.

A bounded staged restart orchestrator that only coordinates current owners may
be repaired to `single_agent` when that is the truthful current execution
scope. Do not let future full-reset participants inflate the staged task's
handoff size.

### Re-run closure

After repairs, re-run:

- dependency target existence/kind checks;
- dependency cycle checks;
- exclusive-resource consistency;
- full persistent-owner reset coverage;
- process-requirement representation checks;
- execution-scope consistency.
"""

def require_marker(path: Path, marker: str) -> str:
    if not path.exists():
        raise RuntimeError(f"Missing expected file: {path}")
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        raise RuntimeError(
            f"Expected current-state marker not found in {path}: {marker!r}. "
            "Refusing to patch an unexpected version."
        )
    return text

def append_once(path: Path, prerequisite: str, marker: str, block: str) -> None:
    text = require_marker(path, prerequisite)
    if marker in text:
        print(f"already present: {path}")
        return
    path.write_text(text.rstrip() + "\n" + block.strip("\n") + "\n", encoding="utf-8")
    print(f"updated: {path}")

append_once(RECONCILE, RECONCILE_REQUIRED, RECONCILE_MARKER, RECONCILE_BLOCK)
append_once(COVERAGE, COVERAGE_REQUIRED, COVERAGE_MARKER, COVERAGE_BLOCK)
append_once(REFINER, REFINER_REQUIRED, REFINER_MARKER, REFINER_BLOCK)

print("Done.")
print("Patched only reconciliation/verification prompts.")
print("No GDD files were read, copied, moved, replaced, or modified.")
print("Tasks/*.yaml was not touched.")
