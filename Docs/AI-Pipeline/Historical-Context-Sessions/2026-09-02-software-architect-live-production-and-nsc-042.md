# Software Architect Live Production and NSC-042 Builder Handoff

Date: 2026-09-02  
Session/topic: Software Architect integration -> live game work -> NSC-042 generated Unity state

## Goal

Move the supervised Software Architect from reviewed infrastructure into real No Safe Circle work,
fix only defects exposed by live use, and get back to game production. The session progressed from
the three parallel Software Architect lanes through production integration, then through real task
execution, Issue/human-handoff workflow, and into NSC-042. The remaining concrete problem is that
`DoorPrototypeSceneBuilder.Build()` must run **before** human validation and its intended generated
outputs must be part of the exact clean task commit that Vincent validates.

## Starting state

At the beginning of this session, historical context still described three parallel, mostly local
lanes:

```text
A. Software Architect Acceptance Gauntlet
B. Execution Routing v1
C. Decomposition Authorization Binder v1
```

The old context reported production `main` near `f80e077f...`/`fa5da9f...` and the dedicated
Software Architect integration checkout at `c32ac5f...`. Those values are historical only.

## Decisions made

### 1. A/B/C were integrated rather than redesigned

The accepted workflow remained:

```text
bounded implementation
-> deterministic/host validation
-> independent adversarial review
-> targeted correction
-> revalidation
-> guarded exact-path commit
-> deliberate integration
-> move on
```

No new general pipeline feature should be added unless actual integration/game work proves it is
needed.

### 2. The Software Architect is now a production scheduler/admission layer

The durable architecture remains:

```text
TaskGraph = structural/task authority
GitHub Issues = durable operational/workflow authority
Git claim refs = short-lived race protection

deterministic Stage 2 eligibility
-> Software Architect advice
-> deterministic admission/routing
-> explicit task-id worker
```

Workers do not self-select tasks. The architect may recommend execution strength/provider
preference, but deterministic Python owns the actual route. START is never cached. Integration
uncertainty fails closed as WAIT; HUMAN_REVIEW is reserved for real authority/design ambiguity.

### 3. Real worker controllers run on the Windows host

A first live launch exposed that wrapping `run_pipeline_agent.py` inside a provider container was
wrong: the controller needs host Git, authenticated `gh`, Docker, claims, Issues, checkouts, and
workflow state. Production was corrected so the polling scheduler launches the host controller;
Claude/Codex containers remain bounded provider sub-jobs.

### 4. Live defects are fixed narrowly

Real use exposed and production fixed several concrete operational defects:

- Windows GitHub CLI output must be captured as bytes and decoded as UTF-8, rather than relying on
  the Windows locale codec.
- The polling worker boundary must remain on the Windows host.
- Runner authors must reuse canonical mutation APIs rather than creating ad-hoc mutation paths.
- After two failed runner/proof attempts, preserve state and use a read-only engineering diagnosis
  instead of continuing wrapper guesswork.
- Human-action handoffs can notify Vincent through the established NSC-Vincent path.
- Current TaskGraph review states can be materialized into authorized/idempotent GitHub operational
  work before generic fresh dispatch.

### 5. Do not add speculative “advanced” acceptance scenarios yet

The ordinary Software Architect acceptance path is proven for its current scope. Scenario J
(two-scheduler singleton proof) remains deliberately pending. A full normal-task lifecycle and a
full decomposition lifecycle were discussed, but the decision was to run real work first and only
add advanced Gauntlet coverage when a real failure justifies it.

### 6. Builder-generated Unity output belongs before human validation

NSC-042 exposed a concrete ordering problem:

```text
AI implementation commit
-> human rebuilds DoorPrototype scene
-> generated .asset/.unity files become dirty
-> human validates dirty state
-> delivery refuses to merge because tested checkout != recorded commit
```

The desired ordering is now:

```text
AI candidate
-> run DoorPrototypeSceneBuilder.Build()
-> keep intended builder-owned generated outputs
-> discard/ignore unrelated Unity editor side effects
-> automated validation
-> commit/push exact clean task state
-> human validates that exact commit
-> PASS
-> delivery/integration
```

The intentionally simple builder-owned output boundary selected at the end of the session is:

```text
Assets/NoSafeCircle/DoorPrototype/**
Assets/Scenes/DoorPrototype.unity
```

Do **not** commit arbitrary Unity side effects such as `ProjectSettings/**` merely because Unity
touched them, unless they were already part of the verified AI candidate.

A broader pre-handoff generation/hygiene implementation exists as reviewed experimental evidence,
but it is intentionally **not** the chosen next production change because it grew into a much
larger subsystem than the immediate problem required.

## Work performed

Major reviewed/production milestones during this session included:

```text
Software Architect Gauntlet A:
  f7f13cd0dd5f8f3e8475a1da28fe374ccabe7e29

Execution Routing B:
  b3529d09aeb79ea410c14f4a139e3b9fe4f79844

Decomposition Authorization C:
  f998ff73f86b1bcc2c919582be95e3f34ac1bfe4

Software Architect real acceptance adapter:
  dbe657d130da840fa960b3468341f62b80d5769a

Windows GitHub UTF-8 boundary:
  2df60b26b0b8322a26ead787a99db701ced284a8

Polling worker host boundary:
  f596e30673ad9fc6833b3be77d912713abdd3ba1

Canonical mutation API documentation:
  3783280ee5304917785f08fee55766ca8c533cfb

Two-strike runner escalation documentation:
  088905294b22abfffbdef1e088b593f6917c47d7

Vincent human-handoff notification:
  be8347f2e74e0b3d8081fc3f3ca997352f7b6a8e

TaskGraph review-work materialization:
  c7c37cd80436e0c7d8fabd0b80f36790a5c9de7c
```

The first real scheduler preflight selected NSC-040, which was a sensible incremental
world-foundation task. Live execution then exposed the UTF-8 and host-controller defects above;
those were fixed before continuing. Subsequent real workflow use exercised Issue creation/lease,
human handoff, review-state materialization, and game-task progress rather than adding another
speculative infrastructure phase.

For NSC-042:

- Task: `Seamless Scalable Wall Tiling for Long Isometric Walls`.
- Real implementation commit exists on its task branch at
  `2a4861235e8ba363d4b85e8d0a77a807db5aec26`.
- Human rebuild of `DoorPrototypeSceneBuilder.Build()` produced the expected generated Unity state,
  but also Unity editor-setting side effects.
- Delivery correctly refused to claim/merge the tested state while the checkout was dirty.
- A broad feature branch,
  `pipeline/pre-handoff-unity-generation-hygiene-20260902-004901`, reached reviewed commit
  `473cf101502108b0844f7151f25c8255f30d8d45`, but was intentionally held because it changed 11
  files and created a larger pre-handoff subsystem.
- The chosen next approach was narrowed to builder execution + builder-owned output capture only.

## Validation / evidence

Accepted evidence accumulated during the session includes:

- Software Architect Gauntlet G1/G2/G3 adversarial reproductions and controls: approved.
- Execution Routing deterministic suites and line-ending control proof: passed before local commit.
- Decomposition Authorization independent review/corrections: approved before local commit.
- Real adapter final smoke suite reached 89/89 after adversarial identity/event coverage.
- Real Software Architect acceptance reached 12 PASS with Scenario J honestly pending.
- Windows-host live GitHub UTF-8 reads succeeded against real Unicode Issue data.
- Polling Orchestrator host-controller correction passed its focused regression and was integrated.
- TaskGraph validation repeatedly passed during live workflow work.
- NSC-042 builder itself succeeded; the immediate failure was the intentionally guarded dirty-path
  boundary, not the builder.

Do not infer that every local checkout is currently clean from this handoff.

## Ending state

### Live GitHub authority verified for this context update

```text
repository: cathode26/NoSafeCircle
main:       c7c37cd80436e0c7d8fabd0b80f36790a5c9de7c
main tip:   "Materialize TaskGraph review work"

NSC-042 remote branch:
  nsc-042-seamless-scalable-wall-tiling-for-long-isometric-walls
  2a4861235e8ba363d4b85e8d0a77a807db5aec26

Broad experimental pre-handoff branch:
  pipeline/pre-handoff-unity-generation-hygiene-20260902-004901
  473cf101502108b0844f7151f25c8255f30d8d45
```

### Last session-reported local NSC-042 state

The real builder was run from the NSC-042 checkout. The builder-owned generated files were dirty,
and Unity also touched:

```text
ProjectSettings/EditorBuildSettings.asset
ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json
```

No successful generated-state commit/push was reported after that build. Re-read the local
checkout before acting.

### Prepared but not yet run at the transcript boundary

A revised **narrow** infrastructure implementation was prepared to teach the pipeline:

```text
if DoorPrototypeSceneBuilder.cs changes:
    run DoorPrototypeSceneBuilder.Build()

capture additional builder changes only under:
    Assets/NoSafeCircle/DoorPrototype/**
    Assets/Scenes/DoorPrototype.unity

do not absorb unrelated Unity/editor side effects
```

The older narrower `Generated/ArchitecturalTiles/` rule was explicitly superseded by the broader
`Assets/NoSafeCircle/DoorPrototype/**` builder-owned root.

## Unresolved issues / known blockers

1. The narrow builder-output integration is not yet verified as implemented/merged.
2. NSC-042 still needs an exact clean post-builder commit that Vincent can validate.
3. The broad `473cf101...` pre-handoff feature is reviewed evidence, not approved production
   direction; do not merge it by inertia.
4. Local NSC-042 dirtiness must be inspected before any reset/restore/commit.
5. Scenario J remains intentionally pending; do not resurrect a large concurrency project unless
   real multi-scheduler use proves it is needed.

## Next action

> Re-read current `main`, the NSC-042 checkout/remote branch, Issue/workflow state, and TaskGraph.
> If the revised narrow builder-output integration has not been run, implement/review that exact
> small slice from current `main`. Then return to NSC-042: use the real builder output, discard only
> unrelated editor side effects, create/push the exact clean post-builder task commit, and have
> Vincent validate that exact commit before resuming delivery.

## Do not repeat

- Do not reconstruct or re-review A/B/C from scratch.
- Do not rerun the expensive accepted Software Architect Gauntlet proofs without new evidence.
- Do not rebuild the retired decentralized 10-worker wave or old Stage-5 Slices 4-8.
- Do not restart the CRLF/UTF-8/host-controller debugging paths already resolved in production.
- Do not merge the broad pre-handoff generation/hygiene branch merely because it passed review.
- Do not run the obsolete narrow builder rule that only captured
  `Generated/ArchitecturalTiles/**`; the intended boundary was revised.
- Do not commit arbitrary Unity-touched files outside the builder-owned boundary.
- Do not continue assistant-authored runner guessing after two failures; preserve state and invoke
  read-only diagnosis.

## Historical/raw source

Source for this handoff was the uploaded session transcript
`Ai assisted Game Course - Ask Completed Lane Report.txt`.

The raw transcript was **not** committed in this context update. Repository policy makes raw
transcripts optional; the concise structured handoff and refreshed `CURRENT_CONTEXT.md` are the
canonical historical continuation records. The source transcript contained many failed/superseded
runner commands and was scanned for common credential patterns before summarization.

## Authority reminder

This handoff is historical context. Before mutating the repository, verify current Git, TaskGraph,
GitHub Issue/PR, remote-ref, and test state. Current deterministic state wins if it disagrees with
this handoff.
