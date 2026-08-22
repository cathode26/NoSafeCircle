# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last updated: 2026-08-21, after integrating the production GDD RAG, completing Architecture Correction Phases 1 and 2, and fixing the schema-v2 migration override boundary.

## Current Phase

**Architecture Correction Phase 2 — COMPLETE.**

The repository now contains a coherent post-review foundation:

- Milestone 1's persistent task graph and stable `NSC-###` identities;
- the Phase 1 fail-closed execution-authority guard;
- 37 live task contracts migrated to schema 2.0;
- a current, deterministic, integrity-validated production GDD RAG;
- preserved architecture-review evidence;
- combined TaskGraph and GDDRAG regression coverage.

The task graph remains useful, but task contracts no longer claim operational completion. `taskcontrol ready` is intentionally unavailable, and autonomous dispatch remains disabled until Phase 3 can derive current conformance from evidence.

The next architecture slice is:

**Phase 3 — Minimum Delivery/Revalidation Evidence and Derived Conformance.**

The original bundled Milestone 2 roadmap is not the active implementation plan. Future infrastructure must be introduced incrementally and justified by real game-development work.

## Architecture Review Result

The post-Milestone-1 architecture review evaluated one frozen repository commit through eight independent specialist reviews, a synthesis, and an adversarial critique of that synthesis.

Result:

- eight of eight independent reviewers: `partially_unsound`;
- synthesis: `partially_unsound`;
- adversarial critique: `synthesis_needs_revision`.

Accepted correction direction:

- preserve bounded workers, deterministic validation, GER repair, runtime evidence, human authority, and persistent task contracts;
- stop treating mutable task metadata as completion truth;
- distinguish historical delivery evidence from current conformance;
- use reconciliation for bootstrap, broad audits, and reviewed change-impact proposals rather than routine global truth regeneration;
- avoid implementing the entire original Milestone 2 bundle before proving smaller real delivery loops;
- keep one worker and human merge/design authority until the one-ticket process is trustworthy;
- do not treat either reviewer consensus or the task graph's current ordering as automatic product priority.

The accepted immutable review evidence is preserved under:

`Pipeline/ArchitectureReview/evidence/20260821T222222Z-40fdf9ce/`

That directory contains:

- `manifest.json`;
- `model_assignments.json`;
- all eight independent reviews;
- `synthesis.json`;
- `adversarial_critique.json`.

Generated `outputs/current/` and `outputs/runs/` remain transient and ignored by default.

## Architecture Correction Phase 1 — COMPLETE

Phase 1 prevented the legacy task model from authorizing autonomous work before the schema migration existed.

Implemented:

- `Pipeline/TaskGraph/execution_authority.py`
  - fails closed when evidence-derived conformance is unavailable;
  - prevents contract metadata from being mistaken for execution authority.
- `Pipeline/TaskGraph/taskcontrol.py`
  - exposes validation and inspection commands;
  - rejects autonomous authorization while conformance is unavailable.
- `Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py`
  - proves mutable legacy task metadata cannot authorize execution.

Phase 1 originally made the old status-derived ready frontier explicitly advisory. Phase 2 superseded that transitional behavior by removing operational status from task contracts entirely. The current behavior is stricter:

```text
TASK READINESS: UNAVAILABLE — EVIDENCE-DERIVED CONFORMANCE NOT IMPLEMENTED
```

and:

```text
EXECUTION AUTHORIZATION: DENIED
```

A nonzero exit from `taskcontrol authorize` is an intentional policy denial, not a Docker failure.

## Architecture Correction Phase 2 — COMPLETE

All 37 persistent task records were migrated from schema 1.0 to **task-contract schema 2.0**.

Current graph state:

- 37 active contracts;
- 0 superseded contracts;
- 0 cancelled contracts;
- 36 parent edges;
- 59 dependency edges;
- 7 exclusive-resource groups;
- 17 non-code project requirements;
- 75 completion gates;
- 2 downstream integration obligations;
- one root: `NSC-001` / `no-safe-circle`.

Schema 2.0 defines:

```text
Tasks/*.yaml = approved definition of work
```

not:

```text
Tasks/*.yaml = definition + running state + validation state + completion truth
```

Each contract now has:

- `schema_version: "2.0"`;
- `contract_revision`;
- `contract_disposition` (`active`, `superseded`, or `cancelled`);
- stable acceptance-criterion IDs;
- stable completion-gate IDs;
- separate downstream integration obligations;
- per-contract provenance.

Top-level mutable `status` was removed. The old bootstrap observation is retained only under provenance as historical information.

Reviewed migration identity:

`task-contract-schema-v2-20260822-r2`

Important reviewed corrections:

- NSC-003 duplicate suspend criteria were merged;
- NSC-003's future pointer-consumer validation became a downstream integration obligation;
- NSC-019 duplicate suspend criteria were merged;
- NSC-019 duplicate reset criteria were merged;
- NSC-023's fixed-camera checks remain completion gates;
- NSC-023's future visual-foundation compatibility check remains a downstream integration obligation.

The quality audit reports:

- 0 duplicate/near-duplicate acceptance-criteria findings;
- 0 future-dependent completion-gate findings.

Production-specific migration overrides are now bound to all of the following:

- exact task ID;
- exact `reconciliation_key`;
- reconciliation run `20260821T193541Z-998ee7b5`;
- verification run `20260821T195959Z-43dba5de`.

This prevents synthetic tests or future unrelated tasks from receiving corrections merely because they reuse an `NSC-###` ID.

Important Phase 2 files:

- `Pipeline/TaskGraph/TASK_CONTRACT_SCHEMA_V2.md`;
- `Pipeline/TaskGraph/TASK_CONTRACT_V2_QUALITY_REVIEW.md`;
- `Pipeline/TaskGraph/TASK_CONTRACT_V2_MIGRATION.json`;
- `Pipeline/TaskGraph/task_contract_schema.py`;
- `Pipeline/TaskGraph/task_contract_migration.py`;
- `Pipeline/TaskGraph/migrate_task_contracts_v2.py`;
- `Pipeline/TaskGraph/task_contract_quality_audit.py`;
- `Docs/AI-Pipeline/ADR-031_TASK_STATUS_ADVISORY.md`;
- `Docs/AI-Pipeline/ADR-032_TASK_CONTRACT_SCHEMA_V2.md`.

## Milestone 1 Bootstrap State Retained

The initial human-approved, independently verified bootstrap remains valid historical provenance.

Source reconciliation:

`20260821T193541Z-998ee7b5`

Successful verification:

`20260821T195959Z-43dba5de`

The bootstrap originally produced:

- 37 persistent records;
- 12 feature records;
- 25 implementation records;
- 0 artifact records;
- 36 historical `open` observations;
- 1 historical `complete` observation;
- 59 dependency edges;
- 36 parent edges;
- 7 exclusive-resource groups;
- 17 non-code project requirements.

The only task historically observed as `complete` at bootstrap was:

`NSC-023 — Fixed Isometric Camera`

That observation is not current conformance proof. It is retained only as task provenance.

The graph lives under:

`Tasks/NSC-001.yaml` through `Tasks/NSC-037.yaml`

Metadata lives under:

- `Pipeline/TaskGraph/WORK_ID_MAP.json`;
- `Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml`;
- `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`;
- `Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json`;
- `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`;
- `Pipeline/TaskGraph/TASK_CONTRACT_V2_MIGRATION.json`.

The task and metadata files use a deterministic JSON-compatible YAML 1.2 subset so Python's standard `json` parser can read them without another YAML dependency.

Do not rerun the one-time bootstrap against the existing repository.

## Production GDD RAG — CURRENT AND VALIDATED

`Pipeline/GDDRAG` is the current production retrieval layer for the canonical GDD.

Canonical source:

`Docs/GDD/No_Safe_Circle_GDD.md`

Current production index:

`Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`

Current index state:

- 41 deterministic chunks;
- source SHA-256 matches the current canonical GDD;
- `gddctl status` reports `CURRENT`;
- `gddctl validate` passes.

The production integrity boundary verifies:

- every source path points to the canonical GDD;
- every line range is valid and in bounds;
- every chunk exactly matches its declared source lines;
- chunk SHA-256 and character counts match indexed text;
- every production chunk has `canonical: true` and `domain: game_design`;
- the complete index matches a deterministic rebuild;
- direct `GDDRetriever` consumers cannot bypass freshness/integrity validation.

The historical Assignment 4 RAG under `DynamicContentPipeline/` remains completed course output built from the older July GDD. It is not trusted as current production canon.

### RAG authority boundary

The current production RAG solves freshness, provenance, integrity, and deterministic rebuild concerns. It does **not** yet prove that a top-k result set contains every cross-cutting requirement governing a task.

Therefore:

```text
Canonical GDD = game-design authority
Production GDDRAG = validated search, discovery, and navigation aid
Top-k retrieval alone != complete task canon
```

The GDD remains small enough and cross-linked enough that bounded implementation workers should receive the whole current GDD until task-context coverage is independently proven.

Known retrieval behavior, including broad ownership tables occasionally ranking above dedicated prose sections, is documented and pinned by regression tests rather than hidden.

## Combined Validation Status

The combined TaskGraph and production GDD RAG state has passed its regression suite.

TaskGraph checks:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_transform_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_validate_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_persist_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit.py --strict
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py validate
```

Production GDD RAG checks:

```powershell
docker compose run --rm codex-review python3 Pipeline/GDDRAG/tests/gdd_rag_smoke_test.py
docker compose run --rm codex-review python3 Pipeline/GDDRAG/tests/integrity_regression_test.py
docker compose run --rm codex-review python3 Pipeline/GDDRAG/tests/retrieval_regression_test.py
docker compose run --rm codex-review python3 Pipeline/GDDRAG/gddctl.py status
docker compose run --rm codex-review python3 Pipeline/GDDRAG/gddctl.py validate
```

Current policy checks:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py ready
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-003
```

Expected policy state:

- readiness unavailable;
- autonomous authorization denied.

Temporary broad Claude permissions used during RAG investigation were removed. `.claude/settings.local.json` is back to its narrow read-only local policy. This permission file does not control Docker/Codex Python tests.

## Source-of-Truth Boundaries

### Game-design canon

The current human-approved GDD and explicit approved design decisions define intended behavior.

### Production GDD retrieval

`Pipeline/GDDRAG` provides current, hash-bound, integrity-validated retrieval over the canonical GDD. It is not a substitute for the complete canon when retrieval coverage has not been proven.

### Task contracts

`Tasks/*.yaml` defines approved work identity, scope, dependencies, acceptance criteria, completion gates, downstream obligations, exclusive resources, and provenance.

Task contracts do not contain current execution or completion truth.

### Integrated implementation

The integrated Git tree is the authority for what code and assets are present.

Presence alone is not completion proof.

### Current conformance

Current conformance must eventually be derived from:

- exact task-contract revision and hash;
- current governing canon identity and hash;
- exact tested/integrated Git tree;
- required deterministic, Unity, runtime, and semantic evidence;
- human approval where required;
- invalidation or revalidation after relevant design or implementation changes.

This evidence-derived model is not implemented yet.

### Reconciliation

Reconciliation outputs are immutable point-in-time observations.

A reconciliation run may propose new, changed, conflicting, stale, or superseded work, but it may not directly mutate the living task contracts.

Routine GDD iteration should eventually use reviewed, scoped impact analysis rather than automatically regenerating global project truth after every edit.

### Architecture review evidence

The preserved review run is primary evidence for the accepted corrections, but reviewer recommendations are not automatic project decisions. Human authority decides which recommendations to adopt.

## Immediate Next Goal

### Phase 3 — Minimum Delivery/Revalidation Evidence and Derived Conformance

Build only enough state and validation to answer:

> Does this exact task contract currently conform on the integrated project state?

Minimum authority inputs:

```text
task-contract revision/hash
+ current canon identity/hash
+ exact tested and integrated Git tree
+ required deterministic/Unity/runtime evidence
+ human approval where required
+ invalidation/revalidation state
= derived current conformance
```

Phase 3 must not recreate mutable completion truth under another filename.

It must account for at least:

- evidence produced before versus after merge;
- squash or conflict-resolved merges that change the tested tree;
- later relevant code or GDD changes;
- reverts and semantic overwrites;
- contract revision or supersession;
- duplicate or contradictory delivery records;
- missing required gate evidence.

The first implementation should be the smallest evidence model needed for one real task, not a general autonomous platform.

Autonomous dispatch remains disabled until this boundary is trustworthy.

### Real-task selection

The next real task is **not automatically selected by this document, the task graph, or reviewer consensus**.

`NSC-037` was discussed as a review/test candidate. It is not the committed next game-development task.

`NSC-003` remains a possible high-leverage anchor, but it must not be handed to a worker unchanged merely because the bootstrap labels it `single_agent`.

Before executing NSC-003, human review should decide:

- which Input Action owns click-to-move/select;
- arbitration among UI click, movement, Fireball, Frost Field, Force Wave, and door selection;
- click versus held-pointer steering behavior;
- destination replacement and cancellation;
- approach/arrival semantics;
- movement pathing expectations;
- movement-restriction ownership and release semantics.

Human review should also decide whether to supersede the current NSC-003 contract with smaller contracts, such as:

- runtime input and shared pointer-projection foundation;
- mouse-directed movement, restriction, reset, and suspension.

Task selection and any split must be explicitly approved before implementation.

## Deferred Until Evidence Justifies It

Do not begin these merely because schema 2.0 and production RAG now exist:

- autonomous task claiming or continuous dispatch;
- parallel workers or broad worktree orchestration;
- automatic merge or merge queues;
- broad GitHub Issues/Projects synchronization;
- automatic backlog replenishment;
- full-game speculative decomposition;
- Progressive Decomposer implementation as a bundled platform;
- Artifact Authority implementation without a real blocking design need;
- top-k-only task context packs presented as complete canon;
- automatic GDD impact analysis without a reviewed causal model;
- a general supervisor before repeated delivery bottlenecks justify one.

These remain candidates for later phases, driven by observed production needs rather than roadmap momentum.

## Obsolete Branch/Plan Warning

Do not resume `milestone-2a-nsc-003-context` unchanged.

That branch predates:

- the accepted architecture review corrections;
- the Phase 1 execution-authority guard;
- task-contract schema 2.0;
- the reviewed migration quality corrections;
- the production GDD RAG integrity boundary.

Useful work should be rebased or recreated from the corrected current repository state rather than continuing the obsolete plan as written.

## Next Window Instructions

Read, in order:

1. `Docs/AI-Pipeline/START_HERE.md`;
2. this file;
3. `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`;
4. `Docs/AI-Pipeline/DECISIONS.md`;
5. `Pipeline/TaskGraph/README.md`;
6. `Pipeline/TaskGraph/TASK_CONTRACT_SCHEMA_V2.md`;
7. `Pipeline/GDDRAG/README.md`;
8. `Pipeline/GDDRAG/INTEGRITY.md`;
9. `Pipeline/ArchitectureReview/evidence/20260821T222222Z-40fdf9ce/` when reviewing the correction rationale;
10. inspect the actual repository and branch state.

Then:

1. confirm the combined TaskGraph and GDDRAG tests still pass;
2. confirm `taskcontrol ready` remains unavailable;
3. confirm `taskcontrol authorize <task>` remains denied;
4. merge the completed correction/integration branch into `main` if it is not already integrated;
5. create a fresh Phase 3 branch from current `main`;
6. define the minimum evidence-derived conformance model;
7. select one real bounded task through explicit human review;
8. do not automatically select NSC-037 or execute the current NSC-003 contract unchanged;
9. do not treat top-k RAG retrieval as complete canon;
10. do not enable autonomous dispatch yet.

A new window should be able to resume from repository state without the prior chat transcript.
