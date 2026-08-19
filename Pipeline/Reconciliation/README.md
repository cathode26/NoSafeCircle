# No Safe Circle — Reconciliation Agent

## Purpose

The Reconciliation Agent is the occasional/global successor to the analysis side of Assignment 5.

Its job is to answer:

> What does No Safe Circle require, what is actually integrated today, and what coarse work graph should Milestone 1 seed?

It does **not**:

- choose the next goal;
- implement code;
- create missing game design;
- create `Tasks/*.yaml`;
- run continuously.

The output is a human-reviewable reconciliation artifact. After approval, a deterministic Work Graph Seeder can turn the approved records into `Tasks/*.yaml`.

## Architecture

```text
Current GDD
   +
Current main checkout
   +
Optional historical evidence
        ↓
Reconciliation Agent (Claude, read-only)
        ↓
Structured reconciliation.json
        ↓
Deterministic semantic validation
        ↓
RECONCILIATION.md
        ↓
Human review
        ↓
Later: deterministic Work Graph Seeder
        ↓
Tasks/*.yaml
```

## Why this is separate from the Progressive Decomposer

The Reconciliation Agent is **global and occasional**. It bootstraps or refreshes the coarse persistent work graph.

The Progressive Decomposer is **local and just-in-time**. It expands one near-frontier feature after Milestone 1 exists.

If reconciliation discovers that a high-level feature lacks enough design to decompose safely, it records:

`decomposition_state: needs_future_decomposition`

It does **not** invent the missing design and does **not** create an artifact proposal. Artifact proposals belong to the Progressive Decomposer in Milestone 2.

## Read-only boundaries

Claude is limited to `Read`, `Glob`, and `Grep`.

Primary truth:

- `Docs/GDD/No_Safe_Circle_GDD.md`
- `Assets/`
- `ProjectSettings/` when relevant
- `Packages/manifest.json` when installed package availability is relevant

Optional historical evidence:

- `Assignment6GER/README_Assignment6.md`
- `GoalOrientedAgent/outputs/goal_analysis.json`
- `GoalOrientedAgent/outputs/next_goal_selection.json`

Historical files may help locate prior work or validation history, but they never override the current GDD or current checkout.

## Outputs

Every run creates a new append-only snapshot directory:

```text
Pipeline/Reconciliation/outputs/
├── current/                         # mutable human-facing convenience view
│   ├── STATUS.md
│   ├── CANDIDATE.json
│   ├── CANDIDATE.md
│   ├── PROPOSED_GRAPH_DELTA.json
│   ├── PROPOSED_GRAPH_DELTA.md
│   ├── VERIFICATION_SUMMARY.json    # when verification exists
│   └── VERIFICATION.md              # when verification exists
├── LATEST.json
├── LATEST_VERIFICATION.json
└── runs/
    └── <timestamp>-<run-id>/
        ├── reconciliation.raw.json
        ├── reconciliation.json
        ├── RECONCILIATION.md
        ├── PROPOSED_GRAPH_DELTA.json
        ├── PROPOSED_GRAPH_DELTA.md
        └── verifications/
            └── <verification-run-id>/...
```

The files under `runs/<run-id>/` are point-in-time evidence and are never overwritten by a later reconciliation run. Verification history is nested beneath the reconciliation run it audited so the provenance relationship is visible in the filesystem.

`outputs/current/` is deliberately mutable. It answers **what should I read right now?** and is never the historical source of truth.

`LATEST.json` is only a convenience pointer to the newest successful snapshot.
It is mutable metadata, not project truth.


`reconciliation.json` is the machine-readable artifact.

`RECONCILIATION.md` is the human review table plus detailed evidence.

## Run

From the repository root:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/reconciliation_agent.py
```

The command is intentionally one line.

## Environment variables

Optional:

```text
RECONCILIATION_MODEL=sonnet
RECONCILIATION_TIMEOUT_SECONDS=1800
RECONCILIATION_MAX_TURNS=50

# Multi-model verification
RECONCILIATION_VERIFY_REFINER_MODEL=opus
RECONCILIATION_VERIFY_REFINER_TIMEOUT_SECONDS=1800
RECONCILIATION_VERIFY_RECOVERY_REFINER_MODEL=opus
```

## What the agent records

Each proposed work item contains:

- a stable reconciliation `key`;
- title;
- `kind`: `feature`, `artifact`, or `implementation`;
- parent hierarchy;
- requirement basis;
- GDD evidence;
- first-class acceptance criteria;
- first-class validation requirements;
- current repository state;
- proposed durable graph status (`open` / `complete`);
- repository evidence;
- real `depends_on` relationships;
- decomposition state (is approved design specific enough?);
- execution scope + reason (is this a safe one-agent handoff?);
- exclusive resources (can this otherwise-ready work run concurrently?);
- confidence;
- notes.

`parent_key` means **belongs under**.

`depends_on` means **cannot be executed until**.

They are deliberately separate.

## Design decomposition vs execution scope

These are separate axes.

`decomposition_state` asks whether the approved design is concrete enough to describe the work without inventing missing design.

`execution_scope` asks whether that known work is already small/bounded enough for one focused implementation agent. Values are:

- `single_agent`
- `needs_execution_decomposition`
- `human_integration_required`
- `not_applicable`
- `unknown`

A task can be `decomposition_state: concrete` while still being `execution_scope: needs_execution_decomposition`. That means the design is known, but the implementation node bundles too much work for one safe handoff. A future Progressive Decomposer may split the implementation work without inventing new game design.

Difficulty is not the classifier: a hard but bounded task can still be `single_agent`.

## Requirement representation taxonomy

A required GDD sentence does not automatically become a task.

The reconciliation/verification pipeline distinguishes:

- `work_item` — a distinct feature/artifact/implementation responsibility;
- `acceptance_criterion` — behavior/constraint owned by an existing task;
- `validation_requirement` — a test/check/inspection of mapped work;
- `non_code_requirement` — a required non-code obligation;
- `delivery_requirement` — a required build/delivery obligation;
- `pipeline_constraint` — a development-process invariant;
- `deferred_design` — required scope whose approved design is intentionally not
  concrete enough yet;
- `deferred_or_excluded` — stretch or explicitly excluded scope.

Work items carry `acceptance_criteria` and `validation_requirements` as
first-class structured fields so these requirements survive graph seeding
without becoming garbage microtasks.

The deterministic coverage check now reports ambiguous/misclassified
representation as `requirement_representation_problem`. It no longer equates
"required + ambiguous" with "missing task." A new task is created only after the
representation is established as `work_item`.

Examples:

- isometric sprite sorting check -> `validation_requirement`;
- Bone Archive lane/pathing check -> `validation_requirement`;
- Chapel of Ash occlusion check -> `validation_requirement`;
- encounter size 3–8 -> `acceptance_criterion`;
- Ranged Enemy not introduced alone -> `acceptance_criterion`;
- Windows build -> `delivery_requirement`;
- no concurrent edits to one Unity asset -> `pipeline_constraint`.


Non-code requirements are stored as first-class typed records with
`requirement_type`:

- `non_code_requirement`
- `delivery_requirement`
- `pipeline_constraint`

Coverage auditors name the exact stored record through
`mapped_non_code_titles`; they cannot claim a delivery/process requirement is
represented merely because the GDD mentions it. The proposed graph delta also
preserves these typed records so they are not dropped when the persistent work
graph is seeded or reconciled.

## Exclusive resources and concurrency

Execution readiness and parallel safety are separate.

`exclusive_resources` records non-merge-safe resources that an open executable
task expects to modify or integrate against exclusively. Two tasks can both be
dependency-ready and `single_agent` while still requiring sequential dispatch.

Canonical lock keys use:

- `repo-file:<repository-relative path>`
- `unity-scene:<repository-relative Assets/... path>`
- `unity-prefab:<repository-relative Assets/... path>`
- `logical:<stable-lowercase-slug>` only when the shared integration resource
  is established but no concrete path exists yet

For example, two tasks that both modify
`Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs` should
both carry the exact same `repo-file:` lock key.

These locks are **not dependencies**. `taskcontrol ready` may still consider
both tasks ready. The future dispatcher must acquire all declared exclusive
resource locks before starting a task and must not run two tasks concurrently
when their lock sets intersect.

Reconciliation records only coarse, evidence-backed locks. A later Feature
Planning / Progressive Decomposition step may add more exact file/scene/prefab
locks as the implementation file list becomes concrete.


## Deterministic execution-scope normalization

The structured-output schema can still produce combinations that are valid
enum values but structurally contradictory, such as:

`kind: implementation + graph_status: open + execution_scope: not_applicable`

The orchestrator repairs only these mechanical contradictions:

- feature -> `not_applicable`
- completed work that claims future decomposition/integration ->
  `not_applicable`
- open executable + `not_applicable` -> `unknown`

The last case is intentionally conservative. The orchestrator does not guess
`single_agent` versus decomposition; verification or human review must decide.
Every normalization is recorded as a seed warning.

## Verification refiner sizing and recovery

Independent auditors remain model-diverse and randomized. The Refiner is not
another vote: it is a synthesis step over the union of material findings, so it
defaults to `opus` for predictable capacity.

All `blocker` and `error` findings are sent to the Refiner. In addition,
warnings in the narrowly selected structural categories
`under_decomposition`, `overgrouped_work`, and `shared_capability_hidden` are
also sent because they can make required work undispatchable or hide real
prerequisites. Other warnings and suggestions remain preserved in the full
pass-1 merge and are reassessed by the independent pass-2 auditors.

If a verification run times out during refinement, the completed pass-1 audits
are not repeated. `recover_verification.py` can rerun only the missing Refiner
and then continue to pass 2.

## Deferred authoring must not hide known runtime work

`needs_future_decomposition` applies only to the design/content that is truly
unknown. If the same feature also contains a runtime rule already fully
specified by the GDD, reconciliation/refinement must split that runtime
responsibility into an implementation item rather than making it
undispatchable.

For encounter work this means room-specific placements, trigger positions,
exact compositions, and durability values may remain deferred, while the
specified active-enemy-ceiling activation rule is tracked as executable runtime
work.

## Important rules

### Complete means evidence exists now

A work item is not `complete` because an old assignment says it was completed.

Current integrated project evidence must support the claim.

Historical evidence can strengthen validation history only when the current implementation is also present.

### Capability-to-create is not current state

Builder/editor/setup code that *could* create a scene object is not proof that object is serialized in the project.

### Missing design is not permission to invent

If the GDD names a high-level feature but lacks enough detail for safe low-level decomposition, keep the feature coarse and mark it for future progressive decomposition.

Do not manufacture room designs, encounters, factions, lore, enemies, spells, or other requirements during reconciliation.

### Keep the graph coarse

This pass is not supposed to create the entire capstone backlog.

It should establish the truthful major hierarchy, known concrete implementation work, real dependencies, and places where future progressive decomposition is required.

## Human review checklist

Before using the output to seed `Tasks/*.yaml`, verify:

1. Required GDD scope is represented.
2. Stretch/excluded scope was not accidentally seeded.
3. `complete` claims are supported by current `main`.
4. Parent hierarchy is sensible.
5. Dependencies are actual prerequisites, not conceptual relationships.
6. Coarse features were not prematurely exploded into speculative microtasks.
7. Missing design was not silently invented.
8. Low-confidence or unresolved items are understood.
9. Every open executable item has a credible execution-scope classification before autonomous selection.
10. Obvious shared file/scene/prefab integration surfaces are represented by identical `exclusive_resources` keys so otherwise-ready tasks cannot be dispatched concurrently against the same non-merge-safe resource.
11. Required GDD statements are represented at the correct level: work item, acceptance criterion, validation requirement, non-code/delivery requirement, pipeline constraint, or deferred design.

## Next step after approval

Build the deterministic Work Graph Seeder / `taskcontrol` Milestone 1 implementation.

The Reconciliation Agent is intentionally not the system that writes the final task graph.


## Validator recovery behavior

Claude's structured result is written to `reconciliation.raw.json` before
deterministic semantic validation runs.

If the validator rejects the result, the raw model output remains available
for inspection so a several-minute Claude run is not lost.

Feature nodes are non-executable, but they may depend on concrete
`artifact` or `implementation` work. The dependency target may not be another
`feature` node.


## Forbidden-source recovery

The Claude prompt explicitly forbids inspection of:

- `AgentCrew/`
- `DynamicContentPipeline/`

The Python orchestrator also defensively removes evidence from those paths
before semantic validation. This prevents an otherwise-valid several-minute
reconciliation run from failing only because Claude referenced an excluded
historical source.

The sanitized run is marked `ready_with_warnings` when forbidden evidence was
removed. Normal evidence validation still applies afterward, so an
`implemented` or `partial` classification cannot survive if its only evidence
came from a forbidden source.


## Dangling-dependency recovery

The main prompt now requires dependency closure: every `depends_on[].key`
must match a work item in the same reconciliation output.

If Claude still references an omitted work item, the Python orchestrator does
not discard the full reconciliation. It launches a small read-only structural
Refiner that receives the missing key(s), the referencing work, a compact
work-item outline, and the reconciliation summary.

The Refiner may either:

- add the omitted, evidence-backed work item; or
- remove the dependency when the dependency relationship itself was invalid.

The repaired result is then run through the normal deterministic semantic
validator. This is a bounded structural GER-style repair, not a second full
repository reconciliation.


## Snapshot Semantics

A reconciliation result is an **immutable observation**, not the living
project database.

If a snapshot says Fireball was missing on a given run, implementing Fireball
later does not modify that old snapshot. The persistent `Tasks/*.yaml` graph
records operational progress.

A later Reconciliation Agent run creates a new snapshot.

```text
GDD + repository
      ↓
Reconciliation Agent
      ↓
immutable snapshot
      ↓
proposed graph delta
      ↓
review / deterministic diff
      ↓
Tasks/*.yaml
```

The Reconciliation Agent never directly rewrites `Tasks/*.yaml`.

### Before the persistent graph exists

`PROPOSED_GRAPH_DELTA.*` contains bootstrap seed proposals derived from the
snapshot. Human approval and the deterministic Work Graph Seeder are still
required.

### After the persistent graph exists

The Reconciliation Agent detects that `Tasks/*.yaml` exists and emits
`status: taskcontrol_diff_required`.

It does not attempt to cascade changes itself. A deterministic `taskcontrol`
reconciliation-diff/apply workflow will own that comparison in Milestone 1.

This prevents an LLM reconciliation run from silently restructuring or
rewriting the operational graph.

## Safe Cascades

Cascading readiness changes belong to deterministic graph logic, for example:

```text
Movement becomes complete
        ↓
Fireball dependency is satisfied
        ↓
taskcontrol ready changes
```

That is allowed.

An LLM reconciliation run directly rewriting many task files is not.

## Multi-model verification crew

A successful reconciliation run is now treated as a **candidate snapshot**, not
sufficient proof that the proposed graph is semantically complete.

Before the bootstrap seed is approved, run:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_crew.py
```

By default the crew verifies the run referenced by `outputs/LATEST.json`.
Use `--run-id <id>` to audit a specific immutable reconciliation run.

The crew runs five independent read-only audits:

1. **GDD Coverage Auditor A** — full requirement-to-graph coverage pass.
2. **GDD Coverage Auditor B** — a second independent coverage pass using a different model when the configured pool contains at least two models.
3. **Dependency and Decomposition Auditor** — tests parent/dependency semantics, shared capabilities, and over/under-decomposition.
4. **Repository Evidence Auditor** — independently challenges `implemented`, `partial`, `missing`, and especially `complete` claims.
5. **Execution Scope Auditor** — asks whether each open executable node is actually a safe one-agent handoff, needs implementation-only decomposition, or requires human integration.

The auditors do not see one another's findings during the first pass.
Findings are merged by **union, not majority vote**. One credible material
finding must be resolved even if the other auditors did not report it.

If pass 1 contains a blocker/error, a bounded Refiner produces a new candidate
without changing the original immutable reconciliation. The independent audit
crew then runs again against the refined candidate unless `--no-reverify` is
specified.

### Model diversity and randomness

The verifier defaults to this Claude Code model pool:

```text
opus,sonnet
```

These are model aliases passed directly to Claude Code's `--model` flag.
Assignments are randomized per verification run and saved to
`MODEL_ASSIGNMENTS.json`, including the random seed and exact requested model
for every auditor/refiner.

The two coverage auditors are guaranteed to receive different requested models when the pool contains at least two models. Structure, evidence, and execution-scope roles are varied across the configured model pool as well.

Override the pool with:

```text
RECONCILIATION_VERIFIER_MODELS=opus,sonnet
```

Additional full Claude model names can be added to the comma-separated pool if
they are supported by the installed Claude Code environment.

The structural dangling-dependency repair inside the main Reconciliation Agent
now defaults to `opus` rather than silently reusing the generator's `sonnet`
model. Override with:

```text
RECONCILIATION_REPAIR_MODEL=opus
```

### Verification outputs

Verification is append-only and stored **under the immutable source reconciliation run**:

```text
Pipeline/Reconciliation/outputs/
├── current/
├── LATEST.json
├── LATEST_VERIFICATION.json
└── runs/
    └── <reconciliation-run-id>/
        ├── reconciliation.json
        ├── RECONCILIATION.md
        └── verifications/
            └── <verification-run-id>/
                ├── MODEL_ASSIGNMENTS.json
                ├── pass1/
                │   └── <independent audit results>.json
                ├── MERGED_FINDINGS_PASS1.json
                ├── refined_candidate.raw.json          # only when refinement runs
                ├── refined_candidate.json              # only when refinement runs
                ├── REFINED_RECONCILIATION.md            # only when refinement runs
                ├── PROPOSED_REFINED_GRAPH_DELTA.json    # only when refinement runs
                ├── PROPOSED_REFINED_GRAPH_DELTA.md      # only when refinement runs
                ├── pass2/                               # unless re-verification skipped
                │   └── <independent audit results>.json
                ├── MERGED_FINDINGS_PASS2.json
                ├── VERIFICATION_SUMMARY.json
                └── VERIFICATION.md
```

Neither verification nor refinement mutates `Tasks/*.yaml`.

### Deterministic coverage guard

Each GDD Coverage Auditor emits a structured requirement map. Python adds a
material finding whenever that auditor classifies a required GDD requirement
as `unrepresented` or `ambiguous`.

This does not make semantic coverage deterministic—the auditor can still miss a
requirement—which is why two model-diverse coverage passes are used. It does
make each auditor's own coverage claims mechanically enforceable.

### Human gate

`verified` means **ready for human approval**. It never means automatically
seed the persistent graph.

The intended bootstrap path is now:

```text
immutable reconciliation snapshot
        ↓
independent multi-model verification
        ↓
bounded refinement when required
        ↓
independent re-verification
        ↓
human approval
        ↓
deterministic Work Graph Seeder
        ↓
Tasks/*.yaml
        ↓
taskcontrol
```


### Deterministic smoke test

This test does not call Claude:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py
```

It checks model-diversity assignment behavior, deterministic required-coverage handling, legacy execution-scope normalization, and verification bookkeeping-path sanitization.


## Current view and one-time output-layout migration

To rebuild the mutable `outputs/current/` view without calling any model:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/refresh_current_output.py
```

Older verification runs created before the nested layout may still live under `outputs/verifications/`. Migrate those directories beneath their source reconciliation runs with:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/migrate_output_layout.py
```

The migration changes directory location only, records `LAYOUT_MIGRATION.json`, updates the latest verification pointer, and then refreshes `outputs/current/`. Existing semantic reconciliation/verification artifacts are not rewritten.

## Verification recovery after post-refiner validation failure

If a verification run completed its expensive pass-1 auditors and Refiner but
then failed during deterministic validation, preserve that verification
directory. Do not rerun pass 1 automatically.

The Refiner is allowed to read the frozen candidate and merged findings, but
those generated `Pipeline/Reconciliation/outputs/...` files are verification
inputs, not repository evidence. The verifier now normalizes those bookkeeping
paths out of `sources.files_reviewed` before semantic validation while keeping
the normal repository-evidence boundary strict.

For the preserved run from this recovery case:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/recover_verification.py --source-run-id 20260819T050610Z-f640e5da --verification-run-id 20260819T055056Z-6d51b6a0
```

Recovery reuses the already-completed pass-1 audits and
`refined_candidate.raw.json`, validates and saves the refined candidate, then
runs only the still-missing pass-2 independent verification. It never rewrites
the original reconciliation snapshot or `Tasks/*.yaml`.
