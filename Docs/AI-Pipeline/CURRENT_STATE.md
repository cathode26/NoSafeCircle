# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last updated: 2026-08-22, after Architecture Correction Phase 3 was fast-forward merged into `main` and the `provider-neutral-execution-crew` branch was created.

## Current Phase

**Architecture Correction Phase 3 — COMPLETE AND MERGED.**

Phase 3A — Evidence-Derived Current Conformance Evaluator — is complete.

Phase 3B — First Real Production Baseline — is complete.

Phase 3 was fast-forward merged into `main` at:

```text
43fdf0a163e281204906abd43a241db211587a0f
```

The current development branch is:

```text
provider-neutral-execution-crew
```

The active implementation stage is:

**Provider-Neutral Execution Crew Plan — Stage 3: Extract the provider-neutral AgentRuntime foundation.**

The next bounded slice is to implement:

- provider-neutral `AgentRequest` and `AgentResult` contracts;
- semantic capability and write-boundary contracts;
- model capability classes;
- immutable run-directory handling;
- provider configuration validation;
- a deterministic fake provider;
- shared contract and failure-mode tests.

No live Claude Code adapter, OpenAI/Codex adapter, production `ExecutionCrew` role orchestration, task readiness, or autonomous dispatch has been implemented yet.

Architecture Correction Phase 3 remains intentionally fail-closed for execution:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
```

and:

```text
EXECUTION AUTHORIZATION: DENIED
```

Evidence-derived conformance has been proven for `NSC-023`, but a conformant task does not establish dependency readiness or execution authority.

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
- do not treat reviewer consensus or task-graph ordering as automatic product priority.

Accepted immutable review evidence is preserved under:

`Pipeline/ArchitectureReview/evidence/20260821T222222Z-40fdf9ce/`

That directory contains the frozen manifest, model assignments, all eight independent reviews, synthesis, and adversarial critique.

Generated `Pipeline/ArchitectureReview/outputs/` remains transient and ignored by default.

## Architecture Correction Phase 1 — COMPLETE

Phase 1 prevented the legacy task model from authorizing autonomous work before the task-contract migration and evidence model existed.

Key invariant retained:

> Mutable task metadata cannot authorize execution.

Implemented safeguards include:

- `Pipeline/TaskGraph/execution_authority.py`;
- `Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py`;
- fail-closed authorization behavior in `taskcontrol`.

Phase 2 removed operational completion status from the contracts themselves. Phase 3A now provides current-state inspection, but execution authority intentionally remains disabled.

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

Each contract contains:

- `schema_version: "2.0"`;
- `contract_revision`;
- `contract_disposition` (`active`, `superseded`, or `cancelled`);
- stable acceptance-criterion IDs;
- stable completion-gate IDs;
- separate downstream integration obligations;
- per-contract provenance.

Top-level mutable `status` is gone. Historical bootstrap status is retained only as provenance.

Reviewed migration identity:

`task-contract-schema-v2-20260822-r2`

Important reviewed corrections:

- NSC-003 duplicate suspend criteria merged;
- NSC-003 future pointer-consumer validation moved to a downstream obligation;
- NSC-019 duplicate suspend criteria merged;
- NSC-019 duplicate reset criteria merged;
- NSC-023 fixed-camera checks remain completion gates;
- NSC-023 future visual-foundation compatibility remains a downstream obligation.

Production-specific migration overrides are bound to the exact task ID, reconciliation key, and approved bootstrap reconciliation/verification provenance. Synthetic tasks that merely reuse an NSC numeric ID do not receive production-specific corrections.

The migration-report verifier was also made portable across Git-for-Windows line endings: migrated target verification normalizes UTF-8 BOM/CRLF/lone-CR differences while source hashes and pre-publication concurrent-change checks remain byte-exact.

The reviewed migration and quality audit currently pass against all 37 contracts.

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
- 36 historical `open` observations;
- 1 historical `complete` observation;
- 59 dependency edges;
- 36 parent edges;
- 7 exclusive-resource groups;
- 17 non-code project requirements.

The only task historically observed as `complete` at bootstrap was:

`NSC-023 — Fixed Isometric Camera`

That historical observation was **not** Phase 3 conformance evidence. Before the baseline record was committed, the evaluator correctly ignored the uncommitted evidence and reported NSC-023 as `not_delivered`. Once the evidence was committed, the derived state changed to `conformant`.

## Production GDD RAG — CURRENT AND VALIDATED

`Pipeline/GDDRAG` is the current production retrieval layer for the canonical GDD.

Canonical source:

`Docs/GDD/No_Safe_Circle_GDD.md`

Current production index:

`Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`

Current production state:

- 41 deterministic chunks;
- source SHA-256 matches the canonical GDD;
- `gddctl status` reports `CURRENT`;
- `gddctl validate` passes;
- direct `GDDRetriever` consumers enforce the same freshness/integrity boundary.

The production integrity boundary verifies canonical path/line ranges, chunk text, character counts, SHA-256 values, canonical/domain flags, and equivalence to a deterministic rebuild.

The historical Assignment 4 RAG under `DynamicContentPipeline/` remains course output built from the older July GDD and is not trusted as current production canon.

### RAG authority boundary

The production RAG solves freshness, provenance, integrity, and deterministic rebuild concerns. It does **not** prove that a top-k result set contains every cross-cutting requirement governing a task.

Therefore:

```text
Canonical GDD = game-design authority
Production GDDRAG = validated search, discovery, and navigation aid
Top-k retrieval alone != complete task canon
```

Because the GDD is still relatively small and highly cross-linked, bounded implementation workers should receive the whole current GDD until context-pack coverage is independently proven.

## Architecture Correction Phase 3A — IMPLEMENTED AND TESTED

### Purpose

Phase 3A answers:

> What does committed repository evidence currently prove about this exact task contract?

It does not answer:

> May an autonomous worker execute this task?

Those are intentionally separate authority questions.

### New Phase 3A files

- `Docs/AI-Pipeline/ADR-033_EVIDENCE_DERIVED_CONFORMANCE.md`;
- `Pipeline/TaskGraph/CONFORMANCE_RECORDS.md`;
- `Pipeline/TaskGraph/conformance_records.py`;
- `Pipeline/TaskGraph/current_conformance.py`;
- `Pipeline/TaskGraph/conformance_evaluator_smoke_test.py`.

Updated Phase 3A integration files include:

- `Pipeline/TaskGraph/taskcontrol.py`;
- `Pipeline/TaskGraph/execution_authority.py`;
- `Pipeline/TaskGraph/taskcontrol_smoke_test.py`;
- `Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py`;
- `Pipeline/TaskGraph/README.md`.

### Evidence record model

Phase 3A defines immutable records under:

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/records/<RECORD-ID>.json
```

with committed artifacts conventionally stored under:

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/artifacts/
```

Supported record types:

- `delivery`;
- `baseline`;
- `revalidation`.

Records bind evidence to:

- exact task ID;
- task-contract revision and semantic canonical JSON hash;
- canonical GDD path and normalized text hash;
- validated Git commit and tree;
- completion-gate results;
- conformance-surface Git blob SHAs;
- committed evidence-artifact blob SHAs;
- required human approval;
- delivery or revalidation lineage.

Delivery records require their validated commit/tree to equal the recorded integrated commit/tree.

Revalidation records require an existing same-task basis record and valid ancestry with no revalidation cycle.

Records cannot recreate mutable authority fields such as `status`, `complete`, `current`, `ready`, or `authorized`.

### Repository authority boundary

The evaluator reads contracts, GDD text, evidence records, and evidence artifacts from **committed Git objects at HEAD**, not from uncommitted working-copy contents.

A dirty working tree is reported as a warning, but it does not alter the derived state of committed HEAD.

This was demonstrated directly: while Phase 3A source files were still uncommitted, `taskcontrol state` reported committed HEAD and warned that the working tree was dirty.

### Deterministic current-state checks

A record can support conformance only when the evaluator can verify the required Git and evidence relationships, including:

- validated commit exists and is ancestral to current HEAD;
- recorded tree matches the actual tree of the validated commit;
- task-contract revision/hash is correct at the validated commit and current HEAD;
- canonical GDD hash is correct at the validated commit and current HEAD;
- every current completion gate has exactly one passing gate result;
- evidence artifacts are committed and match recorded Git blob SHAs;
- conformance surfaces match both the validated commit and current HEAD;
- required human approval exists;
- revalidation basis records are valid and acyclic;
- duplicate, malformed, contradictory, or incomparable evidence is not silently accepted.

### Derived states

Phase 3A implements deterministic states including:

- `aggregate`;
- `not_delivered`;
- `conformant`;
- `needs_revalidation`;
- `needs_replan`;
- `needs_human`;
- `invalid_evidence`;
- `ambiguous_evidence`;
- `superseded`;
- `cancelled`.

When multiple otherwise-current records exist, Git ancestry is used to select a strict descendant. Incomparable maximal records produce `ambiguous_evidence`; timestamps do not decide authority.

### First real production conformance proof

Human-readable:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py state NSC-023
```

Structured output:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py state NSC-023 --json
```

Current real-project result:

```text
NSC-001 -> aggregate
NSC-023 -> conformant
```

NSC-023 selects:

```text
BASE-NSC-023-86af98f41ab5
```

The production proof is bound to:

- validated implementation commit: `86af98f41ab53016ef55eca9516cc339a1e4f5d1`;
- validated implementation tree: `3e89c4a4879d1bf4179ae48f95b85dee1abc0d4d`;
- evidence commit: `8933e67c7767abf45634f7bade79c734f334eea5`;
- authoritative centralized scene: `Assets/Scenes/DoorPrototype.unity`;
- scene meta GUID: `92dbd0a3e6c18e245896a66c5120379d`;
- in-memory builder suite: 12 passed, 0 failed;
- direct committed-scene camera suite: 2 passed, 0 failed;
- Unity version for both runs: `6000.1.8f1`;
- repository state after both runs: clean;
- required human Play Mode approval: explicitly approved by Vincent Liguori.

Uncommitted evidence was correctly ignored before commit. Committing the evidence changed the derived state from `not_delivered` to `conformant`.

### Phase 3A regression status

The conformance evaluator smoke test passes and proves, in a temporary Git repository, at least:

1. no records -> `not_delivered`;
2. valid committed delivery -> `conformant`;
3. unrelated descendant commit with unchanged conformance surfaces -> still `conformant`;
4. tracked implementation-surface change -> `needs_revalidation`;
5. GDD change -> `needs_revalidation`;
6. task-contract revision/hash change -> `needs_replan`;
7. missing required human approval -> `needs_human`;
8. malformed/missing gate, wrong tree/blob, or altered evidence artifact -> `invalid_evidence`;
9. validated commit not ancestral to HEAD -> stale/revalidation-required state;
10. valid revalidation after a tracked change -> `conformant`;
11. incomparable current evidence -> `ambiguous_evidence`;
12. uncommitted evidence is ignored because authority is committed HEAD.

Existing TaskGraph transform, graph validation, persistence, taskcontrol, migration, quality-audit, and Phase 1 authorization regressions also pass.

The Python `py_compile` command is not used through `codex-review` because Python attempts to write `__pycache__` into the intentionally read-only repository mount. The actual smoke tests import and execute the new modules successfully.

## Provider-Neutral Execution Crew Preparatory Stage 1 — COMPLETE

Stage 1 of `Docs/AI-Pipeline/06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md` established the canonical provider-neutral Unity testing policy and deterministic clean runner before the Phase 3B proof.

Implemented:

- `Docs/Engineering/UNITY_TESTING_POLICY.md`;
- the provider-neutral testing-policy instruction bridge in `AGENTS.md`;
- the testing-policy import in `CLAUDE.md`;
- `Pipeline/Testing/run_unity_tests_clean.ps1`;
- `Pipeline/Testing/testing_policy_smoke_test.py`;
- `Pipeline/Testing/README.md`.

Deterministic checks passed:

- `testing_policy_smoke_test.py`;
- Windows PowerShell syntax parsing of `run_unity_tests_clean.ps1`.

The clean runner was also proven through a real Unity run with these exact facts:

- branch: `phase-3-evidence-derived-conformance`;
- commit: `1d3ed42db6fd595283bd1b57a008a4f4c5438796`;
- tree: `9ce6f9fae545bc187f6b3869c4c36b17ac5f8a45`;
- Unity: `6000.1.8f1`;
- platform: `PlayMode`;
- filter: `NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests`;
- total: 5;
- passed: 5;
- failed: 0;
- skipped: 0;
- result: `Passed`;
- Unity exit code: 0;
- repository clean before and after the run.

The runner proves Unity and Git execution facts. The separately committed NSC-023 baseline record binds those facts into Phase 3 conformance evidence. Neither the runner nor a conformant result enables readiness or authorization; `taskcontrol ready` remains unavailable and `taskcontrol authorize` remains denied.

Stage 1 did **not** implement `AgentRuntime`, provider adapters, `ExecutionCrew`, or a dedicated test-author agent. Those remain later stages with the entry criteria and authority boundaries defined by the plan and ADR-034.

## Current Dispatch Policy

Evidence-derived state inspection exists, but **dependency readiness and autonomous dispatch are not enabled**.

Current readiness command:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py ready
```

Expected output begins:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
```

and explicitly states:

- evidence-derived current-state inspection exists through `taskcontrol state`;
- evidence-derived current conformance has been proven on at least one real task;
- a conformant result does not establish dependency readiness;
- dependency-readiness policy has not been implemented or approved;
- dispatch authorization policy has not been implemented or approved;
- state inspection and a conformant result never authorize autonomous execution;
- zero tasks are authorized for autonomous dispatch.

Authorization command:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-023
```

Expected result:

```text
EXECUTION AUTHORIZATION: DENIED
reason_code: evidence_derived_dispatch_policy_not_enabled
```

A nonzero exit from `authorize` is an intentional policy denial, not a Docker failure.

## Source-of-Truth Boundaries

### Game-design canon

The current human-approved GDD and explicit approved design decisions define intended behavior.

### Production GDD retrieval

`Pipeline/GDDRAG` provides current, hash-bound, integrity-validated retrieval over the canonical GDD. It is not a substitute for complete canon when retrieval coverage has not been proven.

### Task contracts

`Tasks/*.yaml` defines approved work identity, scope, dependencies, acceptance criteria, completion gates, downstream obligations, exclusive resources, contract revision/disposition, and provenance.

Task contracts do not contain current execution or completion truth.

### Integrated implementation

The integrated Git tree is the authority for what code and assets are present.

Presence alone is not completion proof.

### Delivery/revalidation records

Phase 3 records are immutable evidence claims tied to exact task, canon, Git, gate, artifact, and approval identities.

A record does not contain mutable current-completion authority.

### Current conformance

`Pipeline/TaskGraph/current_conformance.py` deterministically evaluates committed evidence against current committed HEAD.

State inspection is now implemented.

Production proof now exists for NSC-023 through committed baseline `BASE-NSC-023-86af98f41ab5`. No real production revalidation record exists yet.

### Reconciliation

Reconciliation outputs remain immutable point-in-time observations. They may propose graph changes but do not directly mutate living task contracts or current conformance state.

Routine GDD iteration should eventually use reviewed, scoped impact analysis rather than global reconciliation after every edit.

### Architecture review evidence

The preserved architecture review is primary evidence for the accepted correction direction, but reviewer recommendations do not automatically become project decisions.

## Immediate Next Goal

### Provider-Neutral Execution Crew Plan — Stage 3

Extract the reusable, provider-neutral `AgentRuntime` foundation from the architectural lessons of Assignment 3 without rewriting the historical `AgentCrew/` implementation.

The first Stage 3 slice should establish:

```text
AgentRequest
+ AgentResult
+ provider interface
+ semantic capability/write-boundary contracts
+ immutable run layout
+ provider configuration validation
+ deterministic fake provider
```

The first slice must not yet implement:

- a live Claude Code provider;
- a live OpenAI/Codex provider;
- Implementer/Test Author/Validator orchestration;
- Unity execution initiated by an agent;
- GER integration;
- task selection;
- dependency readiness;
- dispatch authorization;
- automatic Git commits, merges, or worktrees.

The fake provider and shared fixtures should prove the provider-neutral contract before either live provider adapter is introduced.

Architecture Correction Phase 3 is already merged. Its current authority boundary remains active:

- `NSC-023` derives as `conformant`;
- readiness remains unavailable;
- authorization remains denied;
- no worker or provider result establishes completion, readiness, or dispatch authority.

No real production revalidation record exists yet. Do not fabricate a gameplay, contract, GDD, scene, implementation, or test change merely to produce one. The first legitimate relevant change will exercise the production revalidation path.

## Real Gameplay Task Selection After the Evidence Proof

The first gameplay implementation task is **not automatically selected** by this document, the graph, or reviewer consensus.

`NSC-037` was discussed during architecture review as a possible delivery-lane experiment. It is not the committed gameplay priority.

`NSC-003` remains a possible high-leverage gameplay anchor, but it should not be handed to a worker unchanged merely because its task contract currently says `single_agent`.

Before implementing NSC-003, human review should resolve:

- which Input Action owns click-to-move/select;
- arbitration among UI click, movement, Fireball, Frost Field, Force Wave, and door selection;
- click versus held-pointer steering;
- destination replacement and cancellation;
- approach/arrival semantics;
- movement pathing expectations;
- movement-restriction ownership/release semantics.

Human review should also decide whether NSC-003 should be superseded by smaller contracts, for example:

- runtime input and shared pointer-projection foundation;
- mouse-directed movement, restriction, reset, and suspension.

## Deferred Until Evidence Justifies It

Do not enable or build these merely because Phase 3 exists:

- dependency-derived `taskcontrol ready`;
- autonomous execution authorization;
- autonomous task claiming or continuous dispatch;
- parallel workers or broad worktree orchestration;
- automatic merge/merge queues;
- broad GitHub Issues/Projects synchronization;
- automatic backlog replenishment;
- full-game speculative decomposition;
- Progressive Decomposer as a bundled platform;
- Artifact Authority without a real blocking design need;
- top-k-only task context presented as complete canon;
- automatic GDD impact analysis without a reviewed causal model;
- a general supervisor before repeated delivery bottlenecks justify one.

These remain later candidates driven by observed production needs rather than roadmap momentum.

## Obsolete Branch/Plan Warning

Do not resume `milestone-2a-nsc-003-context` unchanged.

That branch predates the accepted architecture corrections, task-contract schema 2.0, reviewed migration corrections, production GDD RAG integrity boundary, and Phase 3 conformance model.

Useful ideas should be recreated from the corrected current repository state rather than continuing the obsolete plan as written.

## Next Window Instructions

Read, in order:

1. `Docs/AI-Pipeline/START_HERE.md`;
2. this file;
3. `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`;
4. `Docs/AI-Pipeline/DECISIONS.md`;
5. `Docs/AI-Pipeline/06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md`;
6. `Docs/AI-Pipeline/ADR-034_PROVIDER_NEUTRAL_AGENT_RUNTIME.md`;
7. `Pipeline/TaskGraph/README.md`;
8. `Pipeline/TaskGraph/TASK_CONTRACT_SCHEMA_V2.md`;
9. `Pipeline/TaskGraph/CONFORMANCE_RECORDS.md`;
10. `Docs/AI-Pipeline/ADR-033_EVIDENCE_DERIVED_CONFORMANCE.md`;
11. `Pipeline/GDDRAG/README.md`;
12. `Pipeline/GDDRAG/INTEGRITY.md`;
13. inspect `AgentCrew/orchestrator.py` and `Assignment6GER/ger_pipeline.py` as historical reusable prototypes, not production runtime authority;
14. inspect the actual repository and branch state.

Then:

1. confirm the current branch is `provider-neutral-execution-crew`;
2. confirm the branch starts from merged `main` commit `43fdf0a163e281204906abd43a241db211587a0f`;
3. confirm the working tree is clean;
4. read `Docs/AI-Pipeline/06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md`;
5. read `Docs/AI-Pipeline/ADR-034_PROVIDER_NEUTRAL_AGENT_RUNTIME.md`;
6. inspect `AgentCrew/orchestrator.py` and `Assignment6GER/ger_pipeline.py` as historical reusable prototypes, not production runtime authority;
7. define provider-neutral request/result and provider-interface contracts;
8. implement immutable run-directory handling and a deterministic fake provider;
9. add shared contract, permission, budget, timeout, schema, and failure-normalization fixtures;
10. do not implement either live provider adapter until the fake-provider foundation passes;
11. do not implement production Execution Crew roles yet;
12. keep `taskcontrol ready` unavailable and `taskcontrol authorize` denied.

A new window should be able to resume from repository state without the prior chat transcript.
