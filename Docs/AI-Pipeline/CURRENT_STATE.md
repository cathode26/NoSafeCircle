# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last updated: 2026-08-21, after the post-Milestone-1 adversarial architecture review and the start of Architecture Correction Phase 1.

## Current Phase

**Architecture Correction Phase 1 — Task execution authority is being made fail-closed.**

Milestone 1 successfully created the persistent `Tasks/*.yaml` planning graph, stable `NSC-###` identities, deterministic dependency/resource validation, and the local `taskcontrol` inspection CLI.

The architecture review then found that the current task YAML combines a useful work contract with an unsafe operational claim: a mutable `status: complete` field can change the ready frontier without proving that implementation is integrated, validated, current against the GDD, or still valid after later changes.

The persistent graph is therefore retained, but its current status values are now treated as **legacy advisory planning metadata**, not autonomous execution authority.

The previously proposed bundled Milestone 2 is paused while the pipeline proves a smaller real delivery loop.

## Architecture Review Result

The review evaluated the repository at one frozen commit using eight independent specialist roles, synthesis, and an adversarial critique of the synthesis.

Result:

- eight of eight independent reviewers: `partially_unsound`
- synthesis: `partially_unsound`
- adversarial critique: `synthesis_needs_revision`

Accepted correction direction:

- preserve bounded workers, deterministic validation, GER repair, runtime evidence, human authority, and persistent task contracts;
- stop treating mutable task YAML status as completion truth;
- use reconciliation primarily for bootstrap, broad audits, and later change-impact proposals rather than routine global truth regeneration;
- do not implement the entire original Milestone 2 bundle before proving real gameplay delivery;
- establish the Unity/Windows delivery lane and then deliver smaller movement/input slices through a measured manual loop.

Architecture review tooling and outputs are described under:

`Pipeline/ArchitectureReview/README.md`

## Phase 1 Safety Guard

Phase 1 does not yet migrate all 37 task contracts to the future evidence-derived state model. It first prevents the legacy model from authorizing autonomous work.

Implemented/being implemented:

- `Pipeline/TaskGraph/execution_authority.py`
  - returns a deterministic denial for every legacy task;
  - explains that YAML status and the advisory ready queue are not execution authority;
  - provides a fail-closed exception for code that attempts to require authorization.
- `Pipeline/TaskGraph/taskcontrol.py`
  - labels `open`/`complete` as `legacy_status`;
  - makes `taskcontrol ready` explicitly advisory;
  - disables the old ambiguous Python `ready_tasks()` API;
  - adds `taskcontrol authorize <task>`, which returns `DENIED` with exit code `2` during Phase 1.
- `Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py`
  - proves that editing a dependency from `open` to `complete` may change the advisory frontier but never creates execution authority;
  - proves that editing the candidate itself to `complete` still does not authorize it.
- `Pipeline/TaskGraph/MANUAL_DELIVERY_RECORD_TEMPLATE.md`
  - provides a transitional human audit form for the first real delivery slices;
  - is not itself completion authority.

## Required Phase 1 Checks

From the repository root:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py validate
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py ready
```

The `ready` output must visibly state:

```text
ADVISORY READY WORK — NOT AUTHORIZED FOR AUTONOMOUS DISPATCH
```

Authorization must fail closed:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-037
```

Expected result:

```text
EXECUTION AUTHORIZATION: DENIED
```

with process exit code `2`.

## Milestone 1 Bootstrap State Retained

The approved bootstrap remains historically valid and useful.

Source reconciliation:

`20260821T193541Z-998ee7b5`

Successful verification:

`20260821T195959Z-43dba5de`

The approved bootstrap produced:

- 37 persistent work records
- 12 feature records
- 25 implementation records
- 0 artifact records at bootstrap
- 36 legacy `open` records
- 1 legacy `complete` record
- 59 dependency edges
- 36 parent edges
- 7 exclusive-resource groups
- 17 non-code project requirements
- one root: `NSC-001` / `no-safe-circle`

The only task seeded with legacy `status: complete` was:

`NSC-023 — Fixed Isometric Camera`

That status now means only that the approved bootstrap snapshot considered the camera implemented. It is not permanent current conformance proof.

The graph lives under:

`Tasks/NSC-001.yaml` through `Tasks/NSC-037.yaml`

Metadata lives under:

- `Pipeline/TaskGraph/WORK_ID_MAP.json`
- `Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml`
- `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
- `Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json`
- `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`

The task/metadata files use a deterministic JSON-compatible YAML 1.2 subset so Python's standard `json` parser can read them without an additional YAML dependency.

## Source-of-Truth Boundaries

### Game design canon

The current human-approved GDD and explicit approved design decisions define intended behavior.

The stored Assignment 4 RAG snapshot is currently stale relative to the August 21 GDD and must not be trusted as current canon until freshness binding is implemented. For the next bounded slices, use the current GDD or direct current sections.

### Task contracts

`Tasks/*.yaml` currently defines planned work identity, scope, dependencies, acceptance criteria, validation requirements, and bootstrap provenance.

Its `status` field is legacy advisory metadata only.

### Integrated implementation

The integrated Git tree is the authority for what code/assets are present.

Presence alone is still not completion proof.

### Validation and conformance

Current completion must eventually be derived from:

- the applicable task-contract revision/hash;
- governing GDD requirement revision/hash;
- the exact integrated Git tree;
- required deterministic, Unity, runtime, and semantic evidence;
- human approval where required;
- invalidation/revalidation after relevant design or implementation changes.

Phase 2 will implement that evidence-derived model.

### Reconciliation

Reconciliation outputs remain immutable point-in-time observations. They may propose graph changes but do not directly mutate the persistent graph.

Routine GDD iteration should eventually use scoped change-impact analysis rather than automatically regenerating global reconciliation truth after every edit.

## Immediate Next Delivery Sequence

### 1. Complete and verify the Phase 1 guard

Run the smoke tests above. No autonomous dispatcher should exist or be added while authorization is denied.

### 2. Establish the Unity/Windows delivery baseline with NSC-037

Use:

`NSC-037 — Windows Build Scene Registration`

Goals:

- register the canonical gameplay scene in Unity Build Settings;
- confirm Windows Standalone configuration;
- compile and run the practical Unity checks;
- produce a Windows development build;
- record exact commits, changed files, test/build evidence, human observations, and time spent using `MANUAL_DELIVERY_RECORD_TEMPLATE.md`.

This is a measured human-controlled delivery run. It does not require building a generic supervisor first.

### 3. Resolve mouse/input authority before implementing movement

Create one approved decision covering:

- which Input Action owns click-to-move/select;
- arbitration among UI click, movement, Fireball, Frost Field, and door selection;
- held-pointer steering;
- cancellation/replacement rules;
- arrival tolerance;
- movement restriction ownership.

### 4. Split the current NSC-003 contract

Preferred split:

- **NSC-003A — Runtime input and shared pointer projection foundation**
- **NSC-003B — Mouse-directed player movement, restrictions, reset, and suspension**

Deliver both through the same measured manual evidence loop before generalizing orchestration.

### 5. Automate only repeated bottlenecks

After NSC-037 and the two movement slices reveal the real repeated workflow, build the smallest restartable coordinator needed for:

```text
select human-approved task
→ freeze task/GDD/base identities
→ create or resume isolated branch/work area
→ run bounded worker
→ run known validation commands
→ retain evidence
→ request human runtime/merge decision
```

Do not add continuous dispatch, parallel workers, automatic merge, or broad GitHub synchronization before the one-ticket loop is proven.

## Deferred

Do not start these during Phase 1:

- full task-contract schema migration
- automatic evidence-derived completion
- automatic GDD impact analysis
- bundled Milestone 2 platform work
- stale RAG reuse
- Progressive Decomposer implementation
- Artifact Authority implementation
- autonomous task claiming/dispatch
- parallel workers/worktrees
- automatic merge
- continuous backlog processing

Those remain candidates for later phases, justified only by observed delivery bottlenecks.

## Next Window Instructions

Read, in order:

1. `START_HERE.md`
2. this file
3. `00_MASTER_CONTEXT.md`
4. `DECISIONS.md`
5. `Pipeline/TaskGraph/README.md`
6. inspect the actual repository state

Then:

1. run the Phase 1 smoke tests;
2. verify `taskcontrol ready` is explicitly advisory;
3. verify `taskcontrol authorize NSC-037` denies execution;
4. begin the human-controlled NSC-037 delivery baseline;
5. do not implement the original bundled Milestone 2;
6. do not let any worker or dispatcher treat YAML status as completion truth.

A new window should be able to resume from repository state without the prior chat transcript.
