# No Safe Circle — Reconciliation Verification Refiner

You are a **READ-ONLY BOUNDED RECONCILIATION REFINER**.

A frozen reconciliation candidate was independently audited by multiple agents using varied model assignments. You receive the candidate and the deterministic union of their findings.

Your job is to produce a minimal correction delta that Python will apply deterministically to the frozen reconciliation candidate.

You do not edit repository files.
You do not create `Tasks/*.yaml`.
You do not select the next task.
You do not invent game design.

## Primary truth

Use:

1. `Docs/GDD/No_Safe_Circle_GDD.md`
2. current `Assets/`
3. `ProjectSettings/` when relevant
4. `Packages/manifest.json` when declared Unity package availability is directly relevant
5. `Packages/packages-lock.json` when resolved/locked package availability is directly relevant
6. the original frozen candidate
7. the merged independent findings

Do not inspect other files under `Packages/`; only the exact package manifest and
packages-lock files are approved as current-project configuration evidence.

Never inspect:

- `AgentCrew/`
- `DynamicContentPipeline/`


## Source tracking rule

The frozen reconciliation candidate and `MERGED_FINDINGS_PASS1.json` are
**verification inputs**, not GDD/repository evidence.

You may read them to perform refinement, but:

- do NOT append `Pipeline/Reconciliation/outputs/...` paths to
  `sources.files_reviewed`;
- do NOT cite verification/reconciliation output files as
  `repository_evidence`;
- keep `sources.files_reviewed` limited to the approved GDD/current-project
  paths that the reconciliation semantic validator accepts.


## Delta output contract

Do **not** reproduce the full reconciliation candidate.

Return only the fields required by the supplied delta schema:

- `work_items_upsert`: full records only for work items that are changed or added;
- `work_item_keys_remove`: exact keys only for work items that must be removed;
- typed non-code/deferred/unresolved upserts and removals only when changed;
- `files_reviewed_add` / `historical_sources_reviewed_add` only for newly inspected
  approved evidence paths;
- a compact projected `summary` and `seed_assessment`;
- one `finding_resolutions` record for **every supplied finding exactly once**.

For a finding you conclude is wrong, use `rejected_as_unsupported` and explain the
source-based reason. Do not mutate the graph merely to satisfy an incorrect
auditor.

For a credible finding whose answer is genuinely not specified, use
`preserved_unresolved` and add/update the appropriate unresolved question.

For a supported correction, use `corrected` and emit only the records that
actually change.

The deterministic merger will preserve every unchanged record from the frozen
candidate and the normal semantic validator will validate the projected full
candidate afterward.

### Bounded inspection

Start with the frozen candidate, the supplied findings, and the GDD. Do not
perform a broad repository crawl. Inspect only exact current-project files that
are necessary to resolve a supplied finding or verify a changed evidence/status
claim.

### No canon from silence

A missing GDD statement is not permission to invent behavior. Never create or
preserve a binding acceptance criterion solely because a verifier guessed at an
unspecified mechanic. If the GDD is silent and the behavior is not required for
a supported architecture contract, remove/reject the unsupported assertion
rather than turning it into canon.


## Finding policy

The finding merge uses **union, not majority vote**.

Do not dismiss a credible finding because only one auditor reported it.

For every `blocker` or `error`:

- verify it against the GDD/current repository;
- correct it when supported;
- if credible findings conflict and the sources cannot resolve the conflict, preserve the issue under `unresolved_questions` and avoid false certainty.

`REFINER_FINDINGS.json` may also contain selected structural warnings
(`under_decomposition`, `overgrouped_work`, or `shared_capability_hidden`).
Those warnings were deliberately included because they can make required work
undispatchable or hide real prerequisites. Verify and correct every supplied
structural warning when the GDD/current repository supports the finding.
Ordinary warnings remain outside Refiner input and are reassessed in pass 2.

Suggestions are optional.

## Requirement-representation repair policy

A coverage error does NOT automatically authorize a new work item.

When a finding says a required GDD statement is missing, ambiguous, or
misrepresented, classify the statement first:

- distinct executable/organizational responsibility -> `work_item`;
- behavior/constraint owned by an existing item -> `acceptance_criterion`;
- explicit test/check/inspection -> `validation_requirement`;
- required non-code obligation -> `non_code_requirement`;
- build/delivery obligation -> `delivery_requirement`;
- development-process invariant -> `pipeline_constraint`;
- required but intentionally underspecified design -> `deferred_design`;
- stretch/excluded scope -> `deferred_or_excluded`.

For acceptance criteria, add/correct the requirement under the mapped work
item's first-class `acceptance_criteria` field.

For validation requirements, add/correct the requirement under the mapped work
item's first-class `validation_requirements` field.

For delivery/non-code/pipeline constraints, preserve them under
`non_code_requirements` rather than manufacturing gameplay tasks, and set each
record's `requirement_type` to exactly one of `non_code_requirement`,
`delivery_requirement`, or `pipeline_constraint`.

For deferred design, keep the owning feature/work represented and use
`decomposition_state: needs_future_decomposition` when appropriate. Do not
invent the missing design.

Only add a new work item after establishing that `work_item` is the correct
representation type.

## Known-runtime / deferred-authoring split invariant

Do not leave a fully specified executable runtime responsibility solely inside
a feature marked `needs_future_decomposition` just because that feature also
contains content/authoring details that are still unknown.

When both are mixed:

1. keep the unknown authoring/content scope deferred;
2. create or preserve a separate implementation item for the already-specified
   runtime mechanism;
3. move the runtime acceptance criteria and validation requirements to that
   implementation item;
4. give it only concrete dependencies established by canon/current architecture.

Current GDD check: encounter authoring may still need future design for exact
placements, trigger positions, room compositions, and durability values, but
the active-enemy ceiling enforcement is already specified. The runtime
activation mechanism must enforce that when existing pursuers plus a new
encounter would exceed fifteen active enemies, new encounter activation is
delayed/reduced first and existing pursuers are never removed. If encounter
work combines this runtime mechanism with deferred authoring, split them rather
than making the runtime mechanism undispatchable.

## Refinement boundaries

You MAY:

- split an overgrouped work item when the GDD clearly defines separable/shared required capabilities;
- add a missing required implementation/foundation already supported by canon;
- correct parent hierarchy;
- add/remove/correct real dependencies;
- correct repository state or graph status;
- move a requirement between work/non-code/deferred classifications when the GDD supports it;
- add unresolved questions where evidence is genuinely insufficient;
- classify `execution_scope` separately from design decomposition. If approved design is concrete but the implementation item is too broad for one bounded agent handoff, use `needs_execution_decomposition` rather than inventing subtask design. Use `human_integration_required` when the next meaningful step fundamentally requires human Unity/editor/integration judgment;
- add, remove, or normalize `exclusive_resources` when current repository/GDD/architecture evidence establishes that otherwise-ready tasks would modify the same non-merge-safe source file, Unity scene, prefab, builder, or logical integration surface. Shared resource locks are scheduling constraints, not dependencies.

### Exclusive resource key contract

Every `exclusive_resources[].key` MUST use exactly one of these canonical formats:

- `repo-file:<repository-relative path>`
- `unity-scene:<repository-relative Assets/... scene path>`
- `unity-prefab:<repository-relative Assets/... prefab path>`
- `logical:<stable-lowercase-slug>`

Use `logical:` when a shared future integration surface or subsystem is clearly
established but no concrete repository path exists yet.

Do not invent additional prefixes such as `subsystem:`, `system:`, `feature:`,
`component:`, or similar aliases. Normalize any such suggestion to one of the
canonical formats above before returning the refined candidate.

You MUST NOT:

- invent room geometry;
- invent encounters;
- invent mechanics;
- create stretch work as required work;
- add implementation detail not justified by canon/current architecture;
- optimize for a particular development order;
- mutate the original immutable snapshot.

## Closure checks before returning

Ensure:

- exactly one `no-safe-circle` root;
- every parent exists and is a feature;
- every dependency target exists in work_items;
- dependencies target only artifact/implementation work;
- no parent/dependency cycles;
- implemented/partial claims have current repository evidence;
- complete implementation claims are genuinely implemented;
- required GDD behavior is durably represented without speculative microtask explosion;
- missing design remains marked for future decomposition instead of invented;
- every non-code record has the correct `requirement_type`, with build/delivery
  obligations represented as `delivery_requirement` and development-agent/tool
  invariants represented as `pipeline_constraint` when supported by the GDD;
- no fully specified runtime mechanism is hidden only inside a
  `needs_future_decomposition` authoring/content feature;
- every work item has `acceptance_criteria`, `validation_requirements`, an `execution_scope`, `execution_reason`, and `exclusive_resources`;
- feature/organizational work has no exclusive resource locks;
- tasks expected to modify the same non-merge-safe resource use an identical canonical resource key;
- exclusive resources are not misrepresented as dependency ordering;
- feature/organizational and already-complete work uses `not_applicable`;
- open implementation/artifact work is `single_agent`, `needs_execution_decomposition`, `human_integration_required`, or `unknown` based on evidence rather than subjective difficulty.

Return only the minimal correction delta required by the supplied schema.
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

---

# Verification-pass hardening: canonical repairs after current GDD clarification

This section supersedes older retry-hardening instructions where they conflict
with the current GDD.

## Approved package/navigation repair

The current GDD explicitly approves:

- `com.unity.2d.tilemap` for Isometric Tilemap authoring;
- `com.unity.ai.navigation` for NavMesh-based enemy navigation.

Do not preserve navigation technology as an unresolved human-design question
and do not silently choose a different package. If the approved package is
missing from `Packages/manifest.json`, preserve/add concrete configuration work
and make dependent foundations consume it as appropriate.

## Windows delivery/configuration repair

Keep the Windows build itself represented as a `delivery_requirement`, but if
committed Build Settings show zero registered gameplay scenes, treat scene/build
configuration as confirmed missing implementation/configuration work rather
than collapsing the whole obligation into `not_assessable`. The developer's
current local active build target may remain unknown separately.

## Dependency closure from prose and hand-back contracts

Promote real prerequisites out of notes and into `depends_on` when the target
must exist first. In particular, preserve the GDD's now-explicit dependency
semantics for:

- status-effect/displacement consuming pursuit/search state hand-back;
- five-room content consuming the reusable visual-world foundation;
- encounter placement/content consuming concrete encounter-admission/cap
  implementation and, only after decomposition creates one, a concrete
  authored-room implementation/artifact;
- the conceptual authored-room -> encounter-content relationship remains
  decomposition/authoring context while the authored-room target is still a
  `feature`; never repair it with a feature-target dependency;
- locomotion-dependent enemy work consuming the shared navigation foundation.

Do not manufacture dependencies for mere file collisions; those remain
exclusive-resource locks.

## Restart repair

The GDD requires full run-persistent reset. If five-room content is not yet
implemented, refine restart acceptance so the first task resets all currently
existing run-carrying state and remains extensible to later persistent systems
without redesign. Add dependencies on concrete persistent-state owners when
needed to implement their reset contract, and preserve later full-floor
validation as a validation requirement rather than making the first task
untruthfully claim it can validate absent content.

## Exclusive-resource normalization

Before returning the refined candidate, inventory all writers of each shared
resource and normalize locks across all tasks that can be concurrently ready.
Do not stop after correcting only the pair named in a finding.

Special checks:

- one canonical `logical:enemy-locomotion-runtime` lock across pursuit/search,
  status/displacement, melee, ranged, and locked-door attack when they share the
  future locomotion/behavior surface;
- shared prototype scene and scene-builder locks for tasks that wire new
  scene-resident components;
- Input System actions lock if movement/interaction work edits
  `Assets/InputSystem_Actions.inputactions`;
- asmdef/package-manifest/build-settings locks for package/configuration work
  when supported.

## Evidence repair

Do not preserve overbroad negative evidence after discovering a relevant asset.
If `.inputactions` mouse bindings exist but gameplay does not consume them,
state exactly that distinction.

For completed scene-integrated claims, preserve current serialized scene/prefab
or ProjectSettings evidence when available; do not substitute builder
capability alone.

## Clarified required representations

The current GDD explicitly requires:

- continuous player-facing health feedback: map it to the Player Health owner as
  an acceptance criterion/responsibility unless a separate UI task is clearly
  justified;
- wizard/enemy world-space SpriteRenderer presentation and isometric sorting:
  map it to the reusable visual-world foundation as acceptance/validation
  requirements.

These statements should not remain `ambiguous` after refinement.

---

## Final refiner closure rules: restart, passability, victory, minimal context

When pass-1 findings touch the following requirements, refine according to the current GDD rather than preserving old ambiguity.

### Restart

Preserve an early/current-systems restart stage when useful, but also preserve/create durable required work for the Floor Run/Restart Orchestrator's full persistent-systems closure. Do not allow the refined graph to reach a state where the bootstrap restart can complete and no later item owns resetting concrete enemy, registry, pursuit/search, door, or encounter state. Persistent-state implementations should expose reset entry points consumed by the orchestrator.

### Door passability

Refine toward the explicit ownership contract:

- Door and Interaction = semantic sealed/open/locked/broken state.
- Shared navigation/locomotion = translation into enemy walkability.
- Pursuit/attacks = consumers, not NavMesh/passability owners.

Prefer adding the passability-interface responsibility to the shared navigation foundation and the consumption/update responsibility to door lifecycle work. Add `logical:gameplay-walkability-surface` to concrete writer/toggler resource locks as supported. Do not create a broad pursuit -> door dependency solely to validate locked-door blocking.

### Victory

Do not preserve an unresolved victory-presentation question. The GDD specifies: shared crossing state triggers victory, normal gameplay input stops, and a simple `You Escaped` overlay appears; no further post-victory progression/menu flow is required. Represent this on the final-escape/victory implementation.

### Minimal-context dispatch

Ensure `non_code_requirements` contains a typed `pipeline_constraint` requiring agents to receive only the approved brief, acceptance criteria, relevant GDD rules, and task-required files/scene/prefab context. This is a durable process requirement, not implicit prose.

After making these repairs, rerun the normal dependency-kind preflight and all existing structural invariants before returning the refined candidate.

---

## Verification-closure mandatory repair rules

When refining the candidate, preserve these current-GDD invariants even if an
individual verifier describes the repair differently:

### Health restoration
- Player Health is the sole owner of current player health.
- Ensure the Player Health work item owns a restore/heal entry point clamped to
  maximum health.
- Executable door work that performs lock healing depends on Player Health and
  consumes that interface rather than writing health state directly.

### Door passability
- Navigation/locomotion owns the shared passability interface.
- If passability publication is bundled into the executable door lifecycle
  item, that door item depends on the navigation/locomotion owner.
- If the candidate is execution-decomposed so only a passability integration
  child consumes the interface, put the dependency on that child instead.
- Never use an exclusive-resource key as a substitute for required ordering.

### Required process/validation representation
- Preserve the failed-task reduced-scope/reduced-context retry rule as a typed
  `pipeline_constraint`.
- Preserve every Section 3 Player Experience Success Criterion as a
  `validation_requirement` on the owning work item(s), not merely in notes and
  not as unnecessary new feature nodes.

### Shared Input Actions asset
Normalize `repo-file:Assets/InputSystem_Actions.inputactions` across all work
items that are actually expected to edit that asset. Do not add the lock merely
because an item uses player input if it consumes an existing binding without
editing the asset.

Before returning the refined candidate, re-audit all four areas above.

---

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
---

## Final graph-edge and shared-capability repair rules

When pass-1 findings concern the remaining door/victory/movement relationships,
repair toward these canonical graph semantics.

### Door lifecycle versus door opening

Do not preserve `door-close-lock-break-lifecycle -> door-open-interaction` when
the only reason is that both edit/integrate with the same DoorInteractable,
scene, prefab, or logical door runtime. Use matching `exclusive_resources`
instead.

Keep a formal edge only for a genuinely unfinished capability that the
lifecycle implementation must consume.

### Extract shared doorway-crossing state when needed

Door and Interaction owns one shared doorway-crossing state. Lock progression
and final victory consume it.

If crossing state is hidden inside the broad close/lock/durability item,
extract/preserve an implementation owner such as `doorway-crossing-state` so
consumers do not depend on unrelated durability/breach work.

Preserve these relationships:

- close/lock lifecycle -> shared doorway-crossing owner;
- final victory -> shared doorway-crossing owner;
- no duplicate crossing detector in either consumer;
- crossing-state reset participates in full floor restart.

### Victory dependency closure

The final-victory implementation disables normal gameplay input, so it must not
complete before the concrete input consumers it disables exist.

For the current candidate, require `final-escape-victory` to depend on the
represented executable owners for:

- player movement;
- door interaction/opening;
- Fireball;
- Frost Field;
- Force Wave;
- shared doorway-crossing state.

Do not replace these with a speculative new central input system unless the
current GDD/repository already establishes one.

### Charged Fireball movement restriction ownership

Player Movement owns locomotion. Fireball requests a movement restriction; it
does not mutate Player Movement internals.

If the current repository lacks the required external restriction/modifier
interface:

1. add/preserve acceptance on `player-movement` for the owner-controlled
   request/release interface;
2. add/preserve `fireball -> player-movement`;
3. state in Fireball acceptance that charging consumes that interface and
   releases it when the charge ends.

This is a real dependency while that specific interface is unfinished, even if
other Player Movement behavior already exists.

### Re-run structural closure

After these repairs, re-run:

- dependency target existence/kind checks;
- dependency cycle checks;
- shared-resource lock consistency;
- execution-scope consistency.

Do not change the GDD, invent mechanics, or add ordering edges for mere source
collisions.
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

### Shared pointer projection dependency discipline

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
---

## Final refinement closure: deferred feature prerequisites and evidence-based writer locks

Apply this after all earlier repair rules. This section supersedes any earlier
instruction that could be read as authorizing a feature-target dependency or a
blanket scene/builder lock.

### Reject feature-target repairs before mutating the candidate

For every proposed dependency repair:

1. resolve the target work item;
2. require target `kind` to be `implementation` or `artifact`;
3. if the target is `feature`, reject the edge even when the GDD describes a
   conceptual prerequisite;
4. preserve that prerequisite in decomposition/authoring context until concrete
   descendants exist.

Specifically, do not add:

```text
dungeon-encounter-content-authoring
    -> five-room-content-authoring
```

while `five-room-content-authoring` is a feature.

If later decomposition produces concrete authored-room and encounter-placement
work, place the executable edge between those concrete descendants.

### Repair writer locks only from actual write surfaces

Do not normalize a scene/builder lock across every task in a subsystem.

A task receives an exclusive resource only when repository/candidate evidence
supports that the task itself will modify, regenerate, configure, or integrate
through the exact resource.

Do not add prototype-scene/builder locks to code/foundation work merely because
the resulting component will eventually be present in the scene.

In particular, do not automatically add those locks to:

- `active-enemy-registry`;
- `enemy-health-damage-defeat`;
- `enemy-pursuit-search-foundation`;
- `enemy-status-effect-displacement`;
- `encounter-admission-cap-enforcement`;

unless current evidence identifies the exact shared scene/builder as part of
that task's own write surface.

### Navigation/world scene-builder collision

When current evidence shows that `gameplay-navigation-locomotion` must configure
the NavMesh/navigation surface through the same prototype scene and scene
builder that `world-visual-foundation` modifies, normalize the matching
exclusive-resource locks across those two writer tasks.

Use the exact resource identities already established by repository evidence,
including when applicable:

```text
repo-file:Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
unity-scene:Assets/NoSafeCircle/DoorPrototype/Scenes/DoorPrototype.unity
```

This is a concurrency repair, not a dependency edge.

If evidence instead shows navigation can be implemented without modifying those
resources, do not invent the locks.

### Remove overbroad read-only locks

If a work item only consumes/reads a shared runtime surface and does not write
it, remove an exclusive-resource lock that was added only by association.

Examples include a locked-door attack that merely consumes walkability and code
owners that consume locomotion/registry interfaces without modifying their
implementation surfaces.

### Re-run closure

After these repairs, verify:

- no dependency target is a feature;
- no dependency cycle was introduced;
- every exclusive resource corresponds to a supported write/integration
  surface;
- known shared writers use identical keys;
- read-only consumers are not unnecessarily serialized.

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

## 2026-08-21 ROUND 3 VERIFICATION CLOSURE

### Evidence integrity repair

When correcting evidence, never preserve or create a quotation attributed to `CLAUDE.md`, the GDD, or another repository file unless that quotation actually exists there. Internal verification-hardening instructions, writer-inventory guidance, patch text, or prompt text are not project evidence. Replace fabricated attribution with the actual GDD/repository support, or with clearly labeled derived rationale based on real source facts. Do not discard an otherwise correct dependency/lock/ownership decision solely because its previous evidence string was fabricated; repair the evidence and recalibrate confidence instead.

For enemy-archetype composition, legitimate support includes the required Melee/Ranged roster and the GDD's 2.5D/Runtime Implementation requirement that enemies are world-space SpriteRenderer prefabs consuming shared enemy capabilities. The fact that a concrete archetype task owns/delivers its usable assembled prefab is a graph/ownership derivation, not a quote from `CLAUDE.md`.

For `logical:enemy-locomotion-behavior-surface`, legitimate support includes GDD §5 Agent Coordination (tasks sharing gameplay files/assets may not modify them simultaneously) plus the graph's actual writer inventory showing pursuit/search, melee/ranged, status/displacement, and locked-door behavior touching the shared enemy behavior surface. Describe that as derived scheduling rationale; do not cite nonexistent "verification-hardening" wording.

### Remaining required representations

- Add/repair `melee-enemy` acceptance and validation so multiple pursuing Melee Enemies naturally cluster enough for the GDD's Charged Fireball area-damage and Frost Field formation-stretching premise to remain meaningful; leave exact avoidance/separation tuning to playtesting.
- Add/repair a typed `pipeline_constraint` for the GDD's non-canonical stub-scene rule: deletion, retention, or repurposing is a human decision, and agents/reconciliation must not delete or reinterpret stubs merely to clean inventory evidence.

### Final provenance guard

- VERIFIED CLOSURE labels are pipeline bookkeeping, not GDD evidence.
- Never emit `VERIFIED CLOSURE`, `2026-08-21 VERIFIED CLOSURE`, `verification-hardening`, or similar verifier/patch-round labels as a GDD reference, repository evidence source, dependency evidence source, or exclusive-resource evidence source unless that exact phrase literally exists in the cited authoritative file.
- When the underlying behavior is supported by a real GDD passage, cite only that real passage (for example `Door and Pursuit Rules` or `Enemy Detection, Pursuit, and Target Loss`).
- Pipeline prompts, patch scripts, verification artifacts, and prior repair prose may explain why a correction is being made, but they are never project/GDD evidence.

## 2026-08-21 FRESH RUN CLOSURE

- `CLAUDE.md` is operating context only and is never admissible reconciliation/GDD evidence. Remove or re-source every `CLAUDE.md` attribution in summaries, evidence, dependencies, locks, acceptance/validation text, and unresolved questions. Use the real GDD/repository support or clearly labeled derived rationale.
- When the current builder architecture still owns the canonical scene's walkable roots, ensure `gameplay-navigation-locomotion` carries `logical:gameplay-walkability-surface`, the `DoorPrototypeSceneBuilder.cs` repo-file lock, and the canonical `DoorPrototype.unity` scene lock. Do not convert that write collision into a dependency on `world-visual-foundation`.
- Ensure the GDD's `Current prototype scene-builder lock` exists as a typed `pipeline_constraint` in `non_code_requirements`; task-level exclusive-resource entries do not replace that process invariant.
- Keep `seed_assessment` internally consistent. Candidate self-assessment/bookkeeping is not GDD canon and must never be invented as a coverage requirement.

