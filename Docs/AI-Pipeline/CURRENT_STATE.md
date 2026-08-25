# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone, important implementation slice, or authoritative task/evidence state changes.
>
> For real gameplay work, update this file when a task becomes authoritatively delivered/conformant/merged, or when that completion materially changes the next human-selected work frontier.

Last updated: 2026-08-25, after the NSC-038 implementation/evidence merge and the task-start plus validation-manifest/TaskDelivery closeout acceleration merge reached `main`.

## Current Snapshot

The repository is now past the original architecture-correction bootstrap and into two parallel human-directed lanes:

1. **game delivery**, using bounded task contracts, ExecutionCrew where appropriate, Unity/human validation, committed evidence, and TaskGraph-derived conformance;
2. **pipeline development**, where the next architectural slice is D1B.2 independent decomposition verification/refinement.

Merged `main` observed for this documentation update:

```text
0e64f17991d07c3b49491573ad486794b1576316
```

That state includes the NSC-038 implementation and evidence merge, ExecutionCrew exact-approved-new-file task-start acceleration, and clean-validation-manifest plus human-reviewed TaskDelivery closeout acceleration.

Current validated TaskGraph shape at the observed merged `main`:

```text
Task contract schema:  2.0
Active contracts:      40
Superseded contracts:  0
Cancelled contracts:   0
Parent edges:           39
Dependency edges:       63
Resource groups:        9
Project requirements:   17
Parent hierarchy:       connected + acyclic
Dependency graph:       acyclic
```

Autonomous dispatch remains intentionally disabled.

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
EXECUTION AUTHORIZATION: DENIED
```

A `conformant` task is evidence-derived current-state information. It does not grant dependency readiness, execution authorization, merge authority, or autonomous dispatch authority.

## Immediate Game-Development State

### NSC-024 — Tilemap and AI Navigation Package Configuration — COMPLETED, EVIDENCED, AND MERGED

NSC-024 is the prerequisite package-configuration task for the world-visual work.

Current task contract:

```text
Tasks/NSC-024.yaml
contract_revision: 2
contract_disposition: active
execution_scope: single_agent
decomposition_state: concrete
```

Its live exclusive-resource boundary was corrected before implementation to include both package files:

```text
repo-file:Packages/manifest.json
repo-file:Packages/packages-lock.json
```

The resolved package state committed by NSC-024 is:

```text
com.unity.2d.tilemap   1.0.0
com.unity.ai.navigation 2.0.14
```

Implementation/package commit:

```text
fa488e3cda1dd03c72f9fd0c1da21700412d0c04
```

Validated implementation tree:

```text
4bef4f19a36d3cf453252165c80f917d3433b7f5
```

Committed delivery record:

```text
Pipeline/TaskGraph/evidence/NSC-024/records/DEL-NSC-024-fa488e3cda1d.json
```

Record ID:

```text
DEL-NSC-024-fa488e3cda1d
```

Human validation artifact:

```text
Pipeline/TaskGraph/evidence/NSC-024/artifacts/HumanValidation-fa488e3cda1d.txt
```

Evidence commit:

```text
8da2cbc686394bc8899858259346925251293006
```

The delivery record binds the exact committed package surfaces:

```text
Packages/manifest.json      blob c5a459601696a8fbb98d8e20125bf6821f21b66c
Packages/packages-lock.json blob 7629b5aa28096ec2e0b542f2834969a8769a51f0
```

and records `VAL-001` as passed through explicit developer inspection after Unity Package Manager resolution.

TaskGraph selected `DEL-NSC-024-fa488e3cda1d` and reported:

```text
state: conformant
```

The NSC-024 branch was synchronized with the then-current `main` and merged into `main` at:

```text
ad88d76e1ac4eb736285a9888a5e33e2b0915d29
```

The current `main` package blobs still match the delivery record. This documentation file is not an NSC-024 conformance surface and does not change the task contract or GDD canon.

### World-foundation sequence

The immediate world-foundation dependency chain is:

```text
NSC-024 — Tilemap and AI Navigation Package Configuration
    ↓
NSC-038 — Isometric Tilemap Architectural Visual Layer
    ↓
NSC-039 — World-Space SpriteRenderer Prefab and Sorting Foundation
    ↓
NSC-040 — Visual/Simulation Separation and Continuous-Scene Integration
```

NSC-024 and NSC-038 are now implemented, evidenced, and merged. The world-foundation frontier has therefore moved to NSC-039, subject to current TaskGraph inspection and explicit human selection.

### NSC-038 — COMPLETED, EVIDENCED, AND MERGED

`NSC-038` remains an active revision-3, concrete, `single_agent` implementation contract depending on NSC-024. It delivered the reusable isometric Tilemap architectural layer while preserving separate gameplay ownership.

Committed delivery record:

```text
Pipeline/TaskGraph/evidence/NSC-038/records/DEL-NSC-038-54d53e230457.json
```

Implementation/integrated commit and validated tree:

```text
commit 54d53e2304576d6bc236c7a188e6ae8cc21bd174
tree   2b177cc82da8c98f60e6d143d38ed63222835922
```

`VAL-001` records authoritative EditMode validation passing 23/23 plus human Unity visual inspection of the generated architectural presentation. NSC-038 was merged to `main` through:

```text
199d77fb5bbb61a29ac501ff04eab7b0210070be
```

Shared DoorPrototype evidence was subsequently revalidated after NSC-038 in:

```text
890b050118053085356c9a816965931d995485d3
```

At current HEAD, `taskcontrol state NSC-038 --json` selects `DEL-NSC-038-54d53e230457` and reports:

```text
state: conformant
```

### NSC-039 — next world-foundation human-selected candidate

`NSC-039 — World-Space SpriteRenderer Prefab and Sorting Foundation` is active, concrete, `single_agent`, and depends on NSC-038. Its current exclusive-resource scope is:

```text
Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs
Assets/Scenes/DoorPrototype.unity
```

It owns reusable world-space SpriteRenderer prefab and isometric sorting conventions for independently sorted or interactive world objects. `VAL-001` requires representative Unity validation of their ordering relative to Tilemap geometry and to one another at different isometric positions.

At current HEAD, `taskcontrol state NSC-039 --json` reports `not_delivered` with no committed evidence. This is current conformance state only: readiness policy remains unavailable, authorization remains denied, and NSC-039 requires human selection before any run.

### Five-room content remains separate

`NSC-029 — Five-Room Floor Content Authoring` is still a distinct downstream content-authoring feature.

The NSC-026 decomposition deliberately did **not** invent exact dimensions, prop placement, chokepoint geometry, cover positions, or final room layouts for:

- Ruined Entry;
- Bone Archive;
- Chapel of Ash;
- Lower Vault;
- Final Room.

The reusable world foundation should be built before those room layouts are authored. Missing room geometry must not be fabricated merely to make the foundation task executable.

## Progressive Decomposition State

### Stage D1A — COMPLETE AND MERGED

Stage D1A — Decomposition Contracts Plus Deterministic Incremental Graph-Delta Planning — is complete and merged into `main` at:

```text
08ebfd497360b46f801a63e9b3d4d6a365b40bb1
```

D1A is model-free. It implements:

- strict decomposition-result contracts;
- four decisions: `already_concrete`, `decomposed`, `needs_artifact`, `needs_human`;
- semantic gap types: `none`, `execution`, `design`, `uncertain`;
- exact parent AC/VAL/INT coverage;
- proposal-local child keys;
- deterministic permanent NSC-ID allocation above the highest current numeric ID;
- existing/local dependency resolution;
- dependency-cycle rejection;
- copied ID-map/resource-group updates;
- in-memory graph overlay planning;
- whole-overlay validation through the production TaskGraph validator;
- immutable review-only graph-delta output.

D1A never applies the graph delta and never grants readiness, execution, delivery, completion, or conformance authority.

During D1B.1 integration, the D1A semantic boundary was narrowly strengthened with exact artifact-source matching and canonical proposed-child resource-key syntax. The live decomposer prompt was also clarified so proposed `local_key` values use durable lowercase kebab-case reconciliation keys and invalid snake_case model output continues to fail closed rather than being silently normalized.

### Stage D1B.1 — COMPLETE, LIVE-PROVEN, AND MERGED

Stage D1B.1 — Model-Backed Task Decomposition Invocation and Review Artifacts — is no longer the active unfinished slice.

It is implemented and merged into `main`.

D1B.1 performs one human-selected, provider-selected, read-only decomposition invocation through:

```text
TaskExecution
    ↓
AgentRuntime
    ↓
Claude Code or OpenAI/Codex
    ↓
D1A semantic validation
    ↓
graph-delta planning only when decision == decomposed
```

The production source checkout remains physically read-only to the decomposer. Accepted outputs are written outside the repository to the sibling decomposition-output directory and remain review-only.

The deterministic context binds:

- full committed GDD;
- selected task;
- exact TaskExecution byte identity;
- distinct D1A semantic task identity;
- complete task catalog;
- graph neighborhood;
- relevant resource groups;
- historical bootstrap observations labelled as historical;
- approved-artifact context;
- repository context paths;
- explicit authority boundaries.

D1B.1 deterministic regression coverage includes all four decisions, malformed output, semantic rejection, source mutation/dirty-source rejection, graph-planner failure, provider failures, output-root overlap, run collisions, exact prompt identity, source preservation, and no-overwrite publication.

#### Live proving history

The first real Codex run exposed a strict structured-output compatibility problem: `artifact_proposal` was optional in the schema shape that OpenAI required to be fully `required`. The provider-neutral fix made the field required but nullable and added narrow nullable-schema support in AgentRuntime.

A later real run reached semantic validation but returned snake_case child keys. D1A correctly rejected it. The prompt was then clarified with the durable lowercase-kebab-case key rule. The validator was not weakened and automatic normalization was not added.

A live NSC-021 decomposition subsequently reached `review_ready`, proving the pipeline could generate a semantically valid reviewed decomposition proposal. That earlier proposal was not blindly applied when its source graph became stale relative to a rapidly advancing `main`.

The current targeted world proof was the live NSC-026 run:

```text
nsc-026-decomp-20260824t092227z-3ac18b3531a3
```

It returned:

```text
run_status: review_ready
decision: decomposed
graph validation: valid
children: 3
```

The proposed child responsibilities were reviewed and accepted as:

```text
NSC-038 — Isometric Tilemap Architectural Visual Layer
NSC-039 — World-Space SpriteRenderer Prefab and Sorting Foundation
NSC-040 — Visual/Simulation Separation and Continuous-Scene Integration
```

### NSC-026 reviewed decomposition applied to the persistent graph

The reviewed NSC-026 proposal was manually applied as a targeted human-reviewed graph change and committed at:

```text
0459ec4baa48e257e39665534de2ca2f0623223b
```

`NSC-026` is now revision 2 with:

```text
execution_scope: not_applicable
decomposition_state: decomposed
```

Its execution responsibilities are delegated to NSC-038, NSC-039, and NSC-040.

The application also corrected NSC-026 and its new children to use the canonical scene resource:

```text
unity-scene:Assets/Scenes/DoorPrototype.unity
```

The persistent graph now contains 40 active contracts.

Important authority distinction:

> This was a human-reviewed targeted application of a D1B.1 proposal. It does **not** mean Stage D1C reviewed graph-application tooling has been implemented.

### Stage D1B.2 — NEXT PIPELINE ARCHITECTURE SLICE

D1B.2 remains unimplemented.

Its intended bounded role is an **independent verifier/refiner** for D1B.1 proposals, not a general GER loop.

It should challenge at least:

- whether each child is truly bounded and realistically single-agent;
- dependency correctness;
- completion-gate sufficiency;
- resource-claim correctness/existence;
- current repository evidence versus stale bootstrap observations;
- unsupported design assumptions;
- semantic adequacy of parent obligation coverage;
- whether downstream integration checks have incorrectly been promoted to child completion gates.

At most one bounded refinement cycle is the current intended direction. D1B.2 must remain separate from graph application.

The ExecutionCrew Contract Locality Auditor is intentionally downstream of D1B.2. D1B.2 asks whether a proposed decomposition is semantically sound before graph application; the locality auditor asks whether an already-approved concrete task is actually locally implementable/provable immediately before writers run. Both checks are required because they protect different authority boundaries.

### Stage D1C — NOT IMPLEMENTED

A reusable reviewed graph-application authority is not implemented.

Future D1C must not trust an old stored graph delta blindly. It should reconstruct/revalidate the current source graph, current parent identity, current reconciliation-key set, proposed IDs, dependencies, and resource metadata immediately before publication.

This is the next place where stronger artifact-integrity/tamper protections become materially important because D1C crosses from review data into persistent authority.

## Task Contracts and Current Conformance

### Task-contract authority

Task-contract schema 2.0 remains the live contract model:

```text
Tasks/*.yaml = approved definition of work
```

not:

```text
Tasks/*.yaml = definition + running state + validation state + completion truth
```

Task contracts contain work identity, scope, dependencies, acceptance criteria, completion gates, downstream obligations, resources, contract revision/disposition, and provenance.

They intentionally do not contain mutable `status: complete` truth.

### Evidence-derived conformance authority

Immutable records live under:

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/records/
```

with committed artifacts under:

```text
Pipeline/TaskGraph/evidence/<TASK-ID>/artifacts/
```

Supported record types remain:

- `delivery`;
- `baseline`;
- `revalidation`.

`Pipeline/TaskGraph/current_conformance.py` evaluates committed records against current committed HEAD.

A record can support conformance only when current task/canon/surface/gate/artifact/approval identities remain valid.

Mutable authority fields such as `status`, `complete`, `current`, `ready`, and `authorized` are forbidden in conformance records.

### Proven production records

The original Phase 3 production proof remains:

```text
NSC-023 — Fixed Isometric Camera
BASE-NSC-023-86af98f41ab5
```

NSC-024 now provides a second clear example of the delivery-evidence path:

```text
NSC-024 — Tilemap and AI Navigation Package Configuration
DEL-NSC-024-fa488e3cda1d
```

Other committed evidence directories exist for additional delivered gameplay work. Always use `taskcontrol state <TASK-ID> --json` against current HEAD rather than inferring current conformance merely from the presence of an evidence directory.

## Provider-Neutral AgentRuntime and ExecutionCrew

### AgentRuntime — integrated

The provider-neutral AgentRuntime foundation is integrated and includes:

- immutable `AgentInvocationRequest` / `AgentResult` contracts;
- semantic capabilities and write boundaries;
- `low_cost`, `standard`, and `high_reasoning` capability classes;
- strict provider configuration;
- bounded request budgets;
- normalized provider failures;
- strict JSON/schema trust boundaries;
- immutable no-overwrite runtime artifacts;
- Claude Code and OpenAI/Codex adapters;
- deterministic FakeProvider regression coverage.

Provider output remains a claim until independently checked by Git, Unity, schema, TaskGraph, or human validation as appropriate.

### Minimum Production ExecutionCrew — integrated, contract-locality hardened, and exact-new-file accelerated

The current bounded ExecutionCrew supports one human-selected eligible implementation task and one human-selected provider.

The production order is now:

```text
deterministic clean-source + authoritative persistent-TaskGraph preflight
    ↓
read-only Contract Locality Auditor (high_reasoning)
    ↓
    ├── nonlocal/ambiguous contract → CONTRACT_REVIEW_REQUIRED
    │                              → no Implementer/Test Author/Validator invocation
    │                              → human reviews/repairs the task contract
    │
    └── locally executable/provable contract
            ↓
        Implementer
            ↓
        deterministic incremental Git scope check
            ↓
        Unity Test Author
            ↓
        deterministic incremental Git scope check
            ↓
        read-only Validator
            ↓
        optional one repair cycle
            ↓
        human review
```

A selected task must still be:

```text
contract_disposition: active
kind: implementation
execution_scope: single_agent
decomposition_state: concrete
```

Those fields are necessary eligibility conditions, but they are no longer treated as sufficient proof that the contract is a truthful one-agent handoff.

Before any writer runs, the **Contract Locality Auditor** classifies every acceptance criterion and completion gate exactly once as:

- `local_to_task`;
- `requires_declared_dependency`;
- `downstream_integration`;
- `missing_design`;
- `ambiguous`.

The audit is semantic and read-only. It is grounded in the exact task contract, canonical GDD, source HEAD/tree, and the authoritative validated persistent TaskGraph. It never edits `Tasks/*.yaml`, adds dependencies, moves gates, grants readiness, or authorizes execution.

A nonlocal or ambiguous AC/VAL returns:

```text
CONTRACT_REVIEW_REQUIRED
```

before the Implementer is invoked. The resulting audit artifact is review guidance only; a human must repair or clarify the task contract through the normal TaskGraph workflow and rerun ExecutionCrew.

The independent Validator now gives every AC/VAL result a structured `reason_code`. In particular:

```text
not_proven + runtime_not_executed
    → locally valid gate whose authoritative Unity/runtime evidence has not run yet
    → semantic REVIEW_READY may still be allowed

not_proven + missing_integration_dependency
    → current task cannot prove the gate under its declared dependencies
    → blocked_by_design
    → CONTRACT_REVIEW_REQUIRED

not_proven + design_ambiguity
    → approved design/contract is insufficiently clear
    → blocked_by_design
    → CONTRACT_REVIEW_REQUIRED
```

`missing_required_artifact` and `insufficient_evidence` also cannot be hidden beneath an overall Validator pass. Deterministic semantic checks reject inconsistent status/reason-code combinations even if a model claims success.

This execution-time locality check does **not** replace progressive decomposition. D1B.2 remains the planned upstream independent verifier/refiner for decomposition proposals and should prevent many bad child contracts from entering the persistent graph. The Contract Locality Auditor is the final pre-write safety net for an already-approved concrete task.

Eligibility remains distinct from readiness or authorization.

ExecutionCrew:

- never applies `candidate.patch` automatically;
- never commits, pushes, or merges automatically;
- never treats Validator pass as Unity execution evidence;
- never grants conformance or completion;
- accepts existing tracked role paths through `--implementation-path` / `--test-path` and exact approved absent paths through `--new-implementation-path` / `--new-test-path`;
- grants exact-new authority to one named file only, never a directory, helper, or design decision; its parent must already be a committed Git tree and ExecutionCrew never creates missing directories;
- no longer normally requires scaffold-only commits merely to make an approved absent exact file writable;
- keeps providers outside `.meta` authority and generates deterministic pipeline-owned `.meta` sidecars for successfully created new files under `Assets/`; approved new files and sidecars are included in `candidate.patch`;
- keeps implementation and test scopes disjoint;
- reruns the locality audit on human-review retries, including retries of historical pre-auditor runs, and preserves/reconciles prior existing/new classifications without allowing feedback to widen scope;
- emits human-readable review instructions and immutable run artifacts.

### Standalone clone / Compose rule

Real task execution should use a standalone clone from GitHub.

On this machine, task clones should pin the shared Compose project namespace so they reuse configured provider volumes rather than creating clone-specific authentication/config volumes.

Follow the current repository runbook and clone note rather than reconstructing the command from old chat transcripts:

```text
Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md
Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md
```

## Unity Validation Boundary

Canonical testing policy:

```text
Docs/Engineering/UNITY_TESTING_POLICY.md
```

Core rules remain:

- a passing source-level/agent review is not Unity execution evidence;
- authoritative Unity evidence must bind to an exact clean committed HEAD/tree;
- normal tests must not mutate canonical tracked assets;
- builder tests use in-memory or otherwise non-saving seams;
- committed-scene/prefab conformance checks deliberately open exact committed assets and close without saving;
- human Play Mode/visual review remains required where source assertions cannot prove quality;
- Unity-generated incidental project-setting rewrites should be inspected and restored when unrelated.

A successful authoritative clean runner now atomically emits `validation-manifest.json` beside its XML and Unity log. The manifest binds the exact clean commit/tree, Unity invocation metadata, test counts, and exact XML/log hashes and sizes; it is deterministic validation fact, not proof that a task gate or conformance claim is true. Keep the manifest, XML, and log unchanged through TaskDelivery finalization and `record_delivery.py` evidence packaging.

For scene-builder work such as NSC-038, prefer an in-memory builder test path before regenerating the canonical scene through Unity for human inspection.

### Validation Manifest and TaskDelivery Closeout

The normal human-reviewed closeout path is now:

```text
committed implementation
    -> clean Unity validation
    -> validation-manifest.json
    -> TaskDelivery draft
    -> human truth review
    -> TaskDelivery finalize
    -> record_delivery.py
    -> staged-evidence validation
    -> evidence commit
    -> TaskGraph-derived conformance
```

The validation manifest supplies machine-readable deterministic facts. `Pipeline/TaskDelivery/generate_delivery_spec.py` is the clerical bridge from one or more manifests bound to the same exact commit/tree into a `record_delivery.py`-compatible spec; it is not conformance authority. Draft may infer the base from a review-ready `crew_result.json` or accept explicit `--base-commit`, while review/spec outputs remain external and no-overwrite. Finalize fails closed on stale, tampered, removed, duplicated, unbound, or Git/task-drifted evidence.

Humans still decide selected conformance surfaces, semantic roles, evidence-to-gate mappings, gate notes, whether human validation actually occurred and is truthful, and approval. `record_delivery.py`, validation of the staged evidence, committed TaskGraph evidence, and TaskGraph-derived current conformance remain authoritative. TaskDelivery does not run Unity, stage, commit, push, merge, create evidence, derive readiness, or authorize dispatch.

Operational references:

```text
Pipeline/TaskDelivery/README.md
Pipeline/Testing/README.md
Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md
```

## Production GDD and RAG

Game-design authority remains:

```text
Docs/GDD/No_Safe_Circle_GDD.md
```

Production retrieval layer:

```text
Pipeline/GDDRAG
Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json
```

Current authority boundary:

```text
Canonical GDD = game-design authority
Production GDDRAG = validated search/discovery/navigation aid
Top-k retrieval alone != complete task canon
```

Historical Assignment 4 material under `DynamicContentPipeline/` is course output and is not production canon.

## Architecture Review and Correction History

The preserved post-Milestone-1 architecture review remains under:

```text
Pipeline/ArchitectureReview/evidence/20260821T222222Z-40fdf9ce/
```

The accepted architecture direction remains:

- preserve bounded workers and deterministic validation;
- preserve human design/merge authority;
- use immutable evidence and derived current conformance rather than mutable task completion status;
- separate historical delivery evidence from current conformance;
- prove small real delivery loops before adding broad autonomy;
- avoid treating task-graph order or reviewer consensus as automatic product priority.

Historical correction milestones:

```text
Architecture Correction Phase 1  — fail-closed legacy execution authority
Architecture Correction Phase 2  — task-contract schema 2.0 migration
Architecture Correction Phase 3A — evidence-derived current conformance
Architecture Correction Phase 3B — first real production baseline
Provider-neutral AgentRuntime       — integrated
Minimum Production ExecutionCrew   — integrated
ExecutionCrew exact-new-file start — merged/live
Validation Manifest + TaskDelivery — merged/live human-reviewed closeout bridge
Stage D1A                          — deterministic decomposition contracts/planning
Stage D1B.1                        — live read-only model-backed decomposition proposals
```

Historical Assignment 3/4/5/6 course directories remain preserved as coursework evidence and should not be silently rewritten into production architecture.

## Current Dispatch Policy

Dependency readiness and autonomous dispatch remain deliberately unavailable.

Readiness inspection:

```powershell
python Pipeline/TaskGraph/taskcontrol.py ready
```

Expected policy result begins with:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
```

Authorization:

```powershell
python Pipeline/TaskGraph/taskcontrol.py authorize NSC-039
```

Expected result is a policy denial with:

```text
reason_code: evidence_derived_dispatch_policy_not_enabled
```

NSC-039 may be considered as the next world-lane candidate because NSC-038 is currently conformant, but TaskGraph reports NSC-039 itself as `not_delivered`. Human selection is still required; neither dependency conformance nor graph order makes NSC-039 automatically ready or authorized.

## Source-of-Truth Boundaries

### Game-design canon

The committed human-approved GDD defines intended game behavior.

### Task contracts

`Tasks/*.yaml` defines approved work. It does not define mutable completion truth.

### Integrated implementation

The committed Git tree defines what code/assets/configuration currently exist.

Presence alone is not completion proof.

### Delivery/revalidation records

Committed immutable evidence records bind exact task, canon, Git, gate, artifact, and approval identities.

### Current conformance

TaskGraph deterministically derives current conformance from committed evidence and current committed HEAD.

### AgentRuntime / ExecutionCrew output

Agent output is execution/review data, not design canon, deterministic Unity evidence, conformance, readiness, or authorization.

### Progressive decomposition output

D1B.1 output is review-only. It is not persistent graph authority until a separate human-reviewed application step changes the graph.

### Reconciliation

Bootstrap reconciliation remains historical point-in-time provenance. Historical repository observations may be stale and must not override current repository evidence.

### Architecture review

Architecture-review recommendations are evidence for human decisions; they do not automatically become project authority.

## Deferred / Not Yet Implemented

Do not treat any of the following as available merely because neighboring infrastructure exists:

- D1B.2 independent decomposition verifier/refiner;
- reusable D1C reviewed graph-application tooling;
- Artifact Authority / design-artifact generation;
- a general GER loop for decomposition;
- dependency-derived `taskcontrol ready`;
- autonomous execution authorization;
- continuous/autonomous task claiming;
- parallel gameplay workers;
- automatic Git commit/merge/merge queues;
- mixed-provider ExecutionCrew orchestration;
- Unity execution initiated autonomously by an agent;
- provider fallback;
- broad automatic GDD impact analysis;
- full-game speculative decomposition.

Implement these only when a concrete production boundary justifies them.

## Next Work

### Human-selected game lane

Start from current `main`; if a human selects the world lane, create/use an isolated NSC-039 task clone.

Before running ExecutionCrew:

1. run `taskcontrol.py validate`;
2. inspect `taskcontrol.py show NSC-039`, `state NSC-038 --json`, and `state NSC-039 --json`;
3. inspect current repository reality and the GDD;
4. read the real-task runbook plus ExecutionCrew and TaskDelivery READMEs;
5. confirm exact existing/new implementation/test write paths;
6. keep serialized scene publication under Unity/human review rather than giving the worker broad scene-YAML write authority.

Target world sequence:

```text
NSC-038 Tilemap architectural visual layer — conformant/merged
    ↓
NSC-039 SpriteRenderer prefab/sorting foundation — next human-selected candidate
    ↓
NSC-040 visual/simulation continuity
    ↓
later five-room authored content (NSC-029)
```

### Pipeline lane

The next approved architecture discussion should be D1B.2 independent verification/refinement, keeping D1C and Artifact Authority separate.

Do not build D1B.2 merely to delay the game lane. The game can continue through existing human-selected bounded tasks while pipeline architecture evolves separately.

## Next Window Instructions

Read, in order:

1. `Docs/AI-Pipeline/START_HERE.md`;
2. this file;
3. `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md` for real implementation work;
4. `Pipeline/ExecutionCrew/README.md` for real task-start scope and review;
5. `Pipeline/TaskDelivery/README.md` for real task closeout;
6. `Pipeline/TaskDecomposition/README.md` for decomposition work;
7. the selected `Tasks/NSC-###.yaml`;
8. `Docs/GDD/No_Safe_Circle_GDD.md`;
9. `Docs/Engineering/UNITY_TESTING_POLICY.md` when Unity/tests/scenes are involved;
10. inspect actual Git/TaskGraph state before acting.

For the immediate world lane, inspect:

```text
Tasks/NSC-024.yaml
Tasks/NSC-026.yaml
Tasks/NSC-038.yaml
Tasks/NSC-039.yaml
Tasks/NSC-040.yaml
Pipeline/TaskGraph/evidence/NSC-038/
Pipeline/TaskGraph/evidence/NSC-038/records/DEL-NSC-038-54d53e230457.json
Packages/manifest.json
Packages/packages-lock.json
```

Then confirm repository state rather than trusting this document blindly.

The expected immediate continuation is:

```text
NSC-024 package prerequisite — completed/evidenced/merged
NSC-038 Tilemap foundation      — completed/evidenced/merged; currently conformant
NSC-039 SpriteRenderer foundation — next world-foundation human-selected candidate; currently not_delivered
```

That candidate remains subject to fresh `taskcontrol` state, current repository/GDD reality, and explicit human selection; readiness and authorization are not implied.

A new window should be able to resume from the repository without the prior chat transcript.
