from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"already patched: {path}")
        return
    if old not in text:
        raise RuntimeError(f"Expected text not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {path}")


def append_block(path: Path, marker: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"already patched: {path} ({marker})")
        return
    path.write_text(text.rstrip() + "\n\n---\n\n" + block.strip() + "\n", encoding="utf-8")
    print(f"patched: {path} ({marker})")


# ---------------------------------------------------------------------------
# Verification taxonomy: required technical implementation/configuration is
# neither player-facing gameplay nor a development-process invariant.
# ---------------------------------------------------------------------------
crew = ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py"
replace_once(
    crew,
    '''                "required_gameplay",\n                "required_non_code",\n                "required_process",\n                "stretch",''',
    '''                "required_gameplay",\n                "required_implementation",\n                "required_non_code",\n                "required_process",\n                "stretch",''',
)
replace_once(
    crew,
    '''        "required_non_code": {\n            "non_code_requirement",\n            "delivery_requirement",\n        },\n        "required_process": {''',
    '''        "required_implementation": {\n            "work_item",\n            "acceptance_criterion",\n            "validation_requirement",\n            "deferred_design",\n        },\n        "required_non_code": {\n            "non_code_requirement",\n            "delivery_requirement",\n        },\n        "required_process": {''',
)


# ---------------------------------------------------------------------------
# Smoke-test the new taxonomy classification.
# ---------------------------------------------------------------------------
smoke = ROOT / "Pipeline" / "Reconciliation" / "verification_smoke_test.py"
replace_once(
    smoke,
    '''                    {\n                        "requirement_id": "REQ-PIPELINE",\n                        "reference": "Section Test",\n                        "requirement": "Do not concurrently modify one Unity asset",''',
    '''                    {\n                        "requirement_id": "REQ-IMPLEMENTATION",\n                        "reference": "Section Test",\n                        "requirement": "Install a required Unity package",\n                        "classification": "required_implementation",\n                        "representation": "work_item",\n                        "mapped_keys": ["package-configuration"],\n                        "mapped_non_code_titles": [],\n                        "explanation": "Required technical implementation/configuration work.",\n                    },\n                    {\n                        "requirement_id": "REQ-PIPELINE",\n                        "reference": "Section Test",\n                        "requirement": "Do not concurrently modify one Unity asset",''',
)


# ---------------------------------------------------------------------------
# Reconciliation hardening: preserve the real omissions and distinguish
# interface consumption from true unfinished prerequisites.
# ---------------------------------------------------------------------------
reconcile = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "reconcile.md"
RECONCILE_MARKER = "## Post-verification semantic closure preflight"
RECONCILE_BLOCK = r'''
## Post-verification semantic closure preflight

This preflight supplements the canonical-coverage preflight above. Apply it
immediately before returning the candidate.

### Current persistent-state inventory must come from repository truth

Do not hard-code the set of currently-existing run-persistent owners from an
older reconciliation. Inspect the current project.

If the current DoorInteractable/opening implementation already stores state
such as opening progress, an opened/latching flag, persistent visual state, or a
doorway blocker/collider state that survives for the run, then door-opening
state is already a current run-persistent owner even if the later close/lock/
break lifecycle is not implemented yet.

In that case:

- `door-open-interaction` must include an owner-controlled reset entry point for
  the state it currently owns;
- the Floor Run/Restart Orchestrator's current-owner inventory must include it;
- the orchestrator must formally depend on the executable reset owner when that
  reset interface still has to be created.

Do not defer an already-existing persistent door state solely because a broader
future door-lifecycle item will eventually own additional crossing/durability
state.

### Required acceptance criteria that must not disappear

Preserve these current-GDD requirements on their actual owners:

- `player-health`: no passive health regeneration during a room or between
  rooms; health persists across room transitions for the whole run except for
  owner-controlled damage, the fixed door-lock restore request, and the
  orchestrator-invoked floor reset.
- `player-health`: expose an observable zero-health/death transition that the
  Floor Run/Restart Orchestrator can consume without polling or mutating health
  internals directly.
- `melee-enemy`: a retreating player cannot maintain indefinite safety through
  ordinary movement alone; melee pursuit gradually closes distance over time,
  with exact speed/tuning left to playtesting. Add a validation requirement for
  this behavior rather than inventing a fixed speed value.
- `door-close-lock-break-lifecycle`: required breach feedback is implementation
  behavior, not validation-only prose. Acceptance must require the player-facing
  durability indicator and near-breach banging/shaking/crack feedback; retain a
  corresponding validation requirement.
- `fireball` and `frost-field`: casting spends mana through the shared Player
  Mana spend interface. Record that as acceptance behavior.

### Interface consumption is not automatically a dependency

A formal `depends_on` edge means unfinished prerequisite work must complete
before the consumer can execute or be meaningfully validated.

If an owner-side interface already exists and is usable in the current
repository, a consumer may reference that interface in acceptance criteria
without depending on the owner's still-open unrelated work.

Examples:

- if `PlayerHealth.TakeDamage` already exists, Melee/Ranged attacks do not need
  to wait for unrelated Player Health UI/heal/reset work solely to call damage;
- if Player Mana's spend interface already exists, Fireball/Frost Field do not
  need to wait for unrelated Player Mana reset/readability work solely to spend
  mana.

Add a dependency only when the specific capability the consumer needs is still
missing or must be changed first. Apply this rule consistently across all
shared-owner interfaces.

### Repository-state precision

When a work item combines existing implementation with missing required
behavior, use `partial`, not `missing`.

Current checks include:

- player movement may already have serialized CharacterController locomotion
  even when click/hold cursor-directed movement and position reset are missing;
- Player Mana may already have a serialized continuous mana indicator even when
  reset or denied-cast/post-cast-delay feedback remains incomplete.

State exactly what exists and what is missing.

### Parent hierarchy cleanup

The fixed isometric camera and the shared gameplay navigation/locomotion
foundation are world/foundation responsibilities. Parent them under the `world`
feature group rather than Wizard Combat or the Enemies feature merely because
those systems consume them.

### Camera completion and future integration validation

Do not turn an implementation/integration question into a missing GDD design
question.

If the current serialized camera satisfies its owned orthographic fixed-angle
follow behavior, it may remain implemented/complete for that owned requirement.
Compatibility with the later Tilemap/SpriteRenderer foundation belongs as a
validation requirement on world/visual integration. Which concrete `.unity`
scene becomes the final canonical gameplay scene is an implementation/
integration decision owned by world authoring/build-scene registration, not a
new gameplay-design requirement.

### Human integration record taxonomy

A required human merge/scene-inspection/Play Mode gate is a development
pipeline invariant. Represent `Human inspection and final integration authority`
as `pipeline_constraint`, not a generic `non_code_requirement`.

### Force Wave canon

Use the current GDD literally: Force Wave is player-centered radial knockback
and does not use cursor direction or cursor target selection. Do not create an
unresolved aiming-model question for Force Wave and do not make it depend on
cursor targeting solely for aiming.
'''
append_block(reconcile, RECONCILE_MARKER, RECONCILE_BLOCK)


# ---------------------------------------------------------------------------
# Coverage auditor taxonomy and ambiguity rules.
# ---------------------------------------------------------------------------
coverage = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "coverage_auditor.md"
COVERAGE_MARKER = "## Required-implementation classification and integration-question rules"
COVERAGE_BLOCK = r'''
## Required-implementation classification and integration-question rules

The coverage schema includes `required_implementation` in addition to
`required_gameplay`, `required_non_code`, and `required_process`.

Use the classifications this way:

- `required_gameplay`: player-facing/runtime game behavior and mechanics;
- `required_implementation`: mandatory technical architecture,
  configuration, integration prerequisite, or executable authoring constraint
  required to realize the GDD, but not itself a player-facing mechanic and not
  a rule about how development agents operate;
- `required_process`: development-pipeline rules such as agent context limits,
  isolation, compile/test gates, source-control handoff, or human merge gates;
- `required_non_code`: delivery or other non-code obligations.

For `required_implementation`, valid durable representations are `work_item`,
`acceptance_criterion`, `validation_requirement`, or `deferred_design`.

Examples that should normally be `required_implementation`, not
`required_process`:

- installing/configuring the GDD-approved `com.unity.ai.navigation` package;
- installing/configuring the GDD-approved `com.unity.2d.tilemap` package;
- a concrete shared navigation/passability prerequisite between executable
  systems;
- concrete room/encounter authoring prerequisites already established by the
  approved architecture.

A development-process rule is about how work is performed. A required Unity
package or runtime architecture dependency is technical implementation work.

### Do not invent GDD ambiguity from implementation choices

Coverage audits test whether required behavior is represented. They do not
require the GDD to pre-decide every repository path or integration detail.

- The exact `.unity` file that ultimately becomes the canonical continuous
  gameplay scene is an implementation/integration choice already owned by the
  world/scene-registration work. Do not classify the absence of a preselected
  scene path as an ambiguous gameplay requirement.
- Compatibility between an already-implemented fixed isometric camera and a
  future Tilemap/SpriteRenderer visual foundation is a validation/integration
  question. Map it to a `validation_requirement` on the relevant world/visual
  integration work rather than classifying the camera requirement as
  ambiguous.
- Current Force Wave canon is explicit: it is player-centered radial knockback
  and does not use cursor direction or target selection. Map this to the Force
  Wave owner's acceptance criteria; do not report an aiming-model ambiguity.

### Acceptance versus validation

If the GDD requires visible/player-facing behavior, there must be an acceptance
criterion obliging some implementation owner to provide it. A validation
requirement may check the behavior but cannot be the only durable
representation of required implementation behavior. Door breach feedback is a
canonical example.

### Existing interface versus unfinished task

Do not infer a missing dependency merely because a consumer uses an interface
owned by another work item. A dependency is required only when the specific
owner-side capability needed by the consumer is still unfinished. Existing
usable damage/spend interfaces may be consumed while unrelated UI/reset/heal
work on the same owner remains open.
'''
append_block(coverage, COVERAGE_MARKER, COVERAGE_BLOCK)


# ---------------------------------------------------------------------------
# Refiner: same semantic rules, plus keep packages-lock inside its approved
# source boundary (reconciliation/evidence auditor already allow it).
# ---------------------------------------------------------------------------
refiner = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md"
replace_once(
    refiner,
    '''4. `Packages/manifest.json` when installed Unity package availability is directly relevant\n5. the original frozen candidate\n6. the merged independent findings''',
    '''4. `Packages/manifest.json` when declared Unity package availability is directly relevant\n5. `Packages/packages-lock.json` when resolved/locked package availability is directly relevant\n6. the original frozen candidate\n7. the merged independent findings''',
)
replace_once(
    refiner,
    '''Do not inspect other files under `Packages/`; only the exact package manifest is\napproved as current-project configuration evidence.''',
    '''Do not inspect other files under `Packages/`; only the exact package manifest and\npackages-lock files are approved as current-project configuration evidence.''',
)

REFINER_MARKER = "## Post-verification semantic closure repair rules"
REFINER_BLOCK = r'''
## Post-verification semantic closure repair rules

When repairing findings from the current verification semantics, apply these
rules before changing the graph.

### Required technical implementation is not a pipeline constraint

Do not delete or convert legitimate executable/configuration work merely because
a coverage auditor called it `required_process`.

The verification taxonomy now uses `required_implementation` for mandatory
technical architecture/configuration such as approved Unity package
configuration, shared runtime prerequisites, and concrete authoring
prerequisites. Preserve the matching work item/acceptance/dependency when canon
supports it.

### Current persistent Door state participates in staged restart

Inspect current DoorInteractable/opening state. If the existing implementation
already owns run-persistent opening/progress/visual/blocker state, add/preserve
an owner-controlled reset criterion on `door-open-interaction` and include that
owner in the Floor Run/Restart Orchestrator's current-stage reset closure. Do
not pretend only Player Health, Player Mana, and player position currently
persist when repository evidence shows otherwise.

### Preserve omitted gameplay criteria

Repair the owning acceptance/validation fields when missing:

- Player Health: no passive in-room/between-room regeneration; health persists
  across the run except owned damage, fixed door-lock restore, and floor reset;
- Player Health: expose an observable zero-health/death transition consumed by
  restart orchestration;
- Melee Enemy: ordinary retreat alone cannot sustain indefinite safety; melee
  pursuit closes distance over time, with exact tuning deferred to playtesting;
- Door lifecycle: durability indicator plus near-breach banging/shaking/crack
  feedback is acceptance behavior as well as something to validate;
- Fireball/Frost Field: spend through the shared Player Mana spend interface.

### Dependency discipline for already-existing interfaces

Do not block a consumer on an open owner task when the exact interface it needs
already exists in the current repository and the owner's remaining open work is
unrelated.

For example, existing Player Health damage and Player Mana spend interfaces may
be consumed without waiting for unrelated heal/UI/reset work. Add a formal
edge only if the specific capability needed by the consumer is unfinished.

### Repository-state and hierarchy cleanup

- Existing serialized locomotion plus missing cursor-directed input/reset is
  `partial`, not `missing`.
- Include existing serialized mana-UI evidence when present and narrow missing
  readability work to what is actually absent.
- Parent fixed camera and shared gameplay navigation/locomotion under `world`.
- Classify the human final-integration/merge gate as `pipeline_constraint`.

### Do not manufacture integration ambiguity

- The exact canonical `.unity` path is an implementation choice owned by world
  authoring/build registration; it is not missing game design.
- Camera compatibility with the future Tilemap/SpriteRenderer foundation is a
  validation/integration obligation, not a reason by itself to invalidate an
  otherwise evidenced fixed-camera implementation.
- Force Wave is explicitly player-centered radial knockback and does not use
  cursor direction/target selection; remove any stale unresolved aiming-model
  question.
'''
append_block(refiner, REFINER_MARKER, REFINER_BLOCK)

print()
print("Verification semantics hardening applied successfully.")
print("Run verification_smoke_test.py before the next reconciliation.")
