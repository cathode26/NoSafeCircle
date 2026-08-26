# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone, important implementation slice, or authoritative task/evidence state changes.
>
> This file is a routing/status snapshot, not a substitute for TaskGraph, committed evidence, or the current GDD.

Last updated: 2026-08-26, after D1B.2 round-robin decomposition verification/refinement merged to `main`.

## Current merged baseline

Observed merged `main`:

```text
fabb221c83efde230272760400d01747b90c0dc7
```

That baseline includes:

- schema-v2 persistent TaskGraph and evidence-derived conformance;
- provider-neutral AgentRuntime / TaskExecution;
- Claude Code and OpenAI/Codex provider adapters;
- Contract Locality Auditor and Minimum Production ExecutionCrew;
- TaskDelivery evidence closeout path;
- D1A deterministic decomposition contracts and graph-delta planning;
- explicit decomposed-parent aggregate-feature semantics;
- D1B.1 compatible one-provider decomposition;
- **D1B.2 bounded round-robin decomposition verification/refinement**.

## Current TaskGraph shape

Validated graph shape at this baseline:

```text
Task contract schema:  2.0
Active contracts:      49
Superseded contracts:  0
Cancelled contracts:   0
Parent edges:           48
Dependency edges:       82
Resource groups:        9
Project requirements:   17
Parent hierarchy:       connected + acyclic
Dependency graph:       acyclic
```

Autonomous dispatch remains intentionally disabled:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
EXECUTION AUTHORIZATION: DENIED
```

TaskGraph `state` is current evidence-derived information only. It does not grant dependency readiness, execution authority, graph-application authority, or merge authority.

## Current development lanes

The project is advancing in two human-directed lanes:

1. **game delivery** — bounded gameplay implementation through current task contracts, ExecutionCrew where appropriate, Unity/runtime/human validation, TaskDelivery, committed evidence, and TaskGraph-derived conformance;
2. **pipeline proving** — use the newly merged D1B.2 decomposition system on real near-frontier tasks before adding more decomposition infrastructure.

The current architecture rule remains:

```text
real game work
        ↓
use the current pipeline
        ↓
measure actual failure/cost/ambiguity
        ↓
add only the next bounded infrastructure slice justified by evidence
```

## Progressive decomposition state

### D1A — IMPLEMENTED

D1A is deterministic and model-free. It validates:

- decomposition schema and semantic policy;
- exact parent AC/VAL/INT coverage;
- child local keys and boundaries;
- existing/local dependencies;
- inbound dependency rewrites;
- resource ownership;
- graph cycles and complete proposed overlays;
- decomposed-parent aggregate semantics.

A D1A graph delta is review data only and is never automatically applied.

### Aggregate-feature transition — IMPLEMENTED

A successful new decomposition proposal transitions the selected parent into a non-executable aggregate feature.

The parent keeps stable identity and requirement traceability, but all implementation work must live in explicit executable descendants.

Current invariants include:

```text
kind: feature
execution_scope: not_applicable
decomposition_state: decomposed
decomposition_children: exact active direct-child set
exclusive_resources: []
```

Aggregate conformance is derived from its explicit child set while the parent requirement hash still matches the obligations that were decomposed.

No hidden post-child integration pass is allowed. If component work requires later assembly/sewing, that work must be another explicit child task.

Active downstream dependency edges to the decomposed aggregate must be rewritten to the concrete child capability they actually consume.

See:

```text
Docs/AI-Pipeline/ADR-034_DECOMPOSED_AGGREGATE_FEATURES.md
```

### D1B.1 — IMPLEMENTED, COMPATIBLE SINGLE-PROVIDER MODE

D1B.1 performs one read-only provider-backed decomposition call followed by deterministic D1A validation.

It remains useful for diagnostics, comparison, and one-provider proving, but it does not independently verify semantic ownership choices.

Compatible command:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <codex|claude>
```

### D1B.2 — IMPLEMENTED, MERGED, CURRENT NORMAL MODE

D1B.2 is the current normal path for new production decomposition work.

Default flow:

```text
Codex authors candidate 1
        ↓
deterministic D1A validation
        ↓
Claude independently reviews candidate 1
        ├─ PASS → review_ready
        ├─ NEEDS_HUMAN → needs_human
        └─ REVISE → Claude authors candidate 2
                         ↓
                  deterministic D1A validation
                         ↓
                  Codex independently reviews candidate 2
                         └─ continue while budget remains
```

The latest candidate author may never approve its own candidate.

D1B.2 reviewers explicitly challenge:

- duplicate ownership;
- hidden assembly/integration work;
- unnecessary integration tasks;
- non-local completion gates;
- incorrect inbound dependency rewrites;
- missing/misleading parent coverage;
- child granularity and local-completability;
- conflicts with existing TaskGraph/canon ownership;
- invented bookkeeping work;
- whether completing every child really completes the parent aggregate.

Every initial or revised candidate is deterministically validated before another provider sees it.

Blocking findings persist across rounds with explicit resolution state:

```text
resolved | withdrawn | still_blocking
```

Default circuit breaker: 4 AI calls.

If the final allowed call produces a revision, the run ends `needs_human`; an unreviewed revision cannot self-approve.

Normal command:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

Explicit defaults:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID> --providers codex,claude --max-calls 4
```

Canonical Docker invocation:

```bash
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

D1B.2 was deterministically validated on Windows against PR-head commit:

```text
11abe92f0e51f6678c84fbf55560f10886acdbcc
```

The validation suite included pass, revise, needs-human, invalid-revision, provider-failure, source-mutation, unresolved-finding, circuit-breaker, graph-delta, aggregate-semantics, D1B.1 regression, compile, whitespace, and clean-tree coverage.

See:

```text
Docs/AI-Pipeline/ADR-035_ROUND_ROBIN_DECOMPOSITION_REVIEW.md
Pipeline/TaskDecomposition/README.md
Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md
```

### D1C — NOT IMPLEMENTED

Reusable reviewed graph-application authority remains unimplemented.

D1B.1/D1B.2 outputs remain:

```text
review_only_not_applied
```

Human-reviewed targeted/manual graph application is still a separate authority boundary.

Future D1C must reconstruct/revalidate current graph identity and proposal semantics immediately before publication rather than trusting a stale stored graph delta.

## Current decomposition output convention

For real Windows task decomposition, the host output root is:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>
```

The pipeline creates a no-overwrite child directory for each run:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>\
```

Do not pre-create `<RunId>`.

D1B.2 preserves per-round request, runtime, review, candidate, finding, and deterministic graph artifacts. Root-level `decomposition_result.json` and `graph_delta.json` are published only after an independent PASS.

`needs_human` preserves review history/diagnostics without pretending an unapproved candidate is review-ready.

## Current GDDRAG state

`Pipeline/GDDRAG` is implemented as a deterministic, hash-verified production retrieval tool over the current canonical GDD.

It is **not currently connected to D1B.2**.

Current D1B.2 context still includes the full committed GDD. This is deliberate for the first proving phase.

We will first measure real decomposition behavior:

- semantic quality;
- number of calls/refinements;
- prompt/context pressure;
- provider latency;
- token usage when available;
- whether reviewers overlook relevant canon even though full canon is present.

Only if those measurements show a real need should GDDRAG be added to decomposition review.

### Possible future GDDRAG-assisted reviewer — DEFERRED

Preferred future shape, if justified:

```text
parent AC/VAL/INT
+ current proposed children
+ inbound dependency rewrites
+ unresolved findings
        ↓
deterministic review queries
        ↓
validate current GDDRAG index
        ↓
retrieve + deduplicate + text-cap current-canon chunks
        ↓
reviewer navigation hints
        + authoritative TaskGraph/full-canon context
```

Constraints:

- RAG remains navigation assistance, never canon authority;
- stale/invalid retrieval output is never used;
- top-k omission never proves a requirement absent;
- TaskGraph ownership still decides who owns implementation work;
- retrieval must be deterministic, capped, and preserved as review evidence;
- do not build this merely because the RAG subsystem exists.

The current decision is **test D1B.2 first, measure, then decide**.

## Current proving target

The immediate decomposition proving target is `NSC-016 — Ranged Enemy Archetype`.

Prior D1B.1 runs on NSC-016 exposed the exact semantic failure classes D1B.2 was built to challenge:

- downstream dependency ownership;
- aggregate-parent completion semantics;
- duplicate/downstream validation responsibility;
- whether a proposed integration child represents real sewing work or duplicated bookkeeping.

The next useful experiment is therefore a real D1B.2 NSC-016 run from current `main`, without GDDRAG assistance.

Record the run's provider calls, duration, result quality, findings, revisions, and practical context/token pressure before deciding whether retrieval should enter the reviewer loop.

## Implementation-delivery state

The gameplay implementation path remains:

```text
TaskGraph/GitHub selection
        ↓
canonical isolated task checkout
        ↓
Contract Locality Auditor
        ↓
ExecutionCrew
        ↓
Unity/runtime/human validation
        ↓
TaskDelivery review
        ↓
committed evidence
        ↓
TaskGraph-derived conformance
        ↓
human merge authority
```

ExecutionCrew does not automatically run Unity, apply graph deltas, commit, push, merge, grant conformance, or grant readiness.

## Current authority model

```text
GDD / approved artifacts        → design authority
Tasks/*.yaml                    → approved work-contract authority
Git + committed evidence        → delivery/conformance evidence authority
TaskGraph deterministic tools   → graph/conformance fact derivation
GitHub Issues                   → operational coordination only
D1B.2 providers                 → bounded semantic proposal/review
Human                           → design ambiguity, graph application, merge authority
```

## Current intentional gaps

Not yet production authority:

```text
D1C reusable graph application
Artifact Authority implementation
Artifact generation + Artifact GER production flow
Dependency readiness policy
Autonomous dispatch
Automatic merge authority
GDDRAG-assisted D1B.2 review
```

## Routing

Read next:

```text
Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md
```

When selecting/claiming tasks:

```text
Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md
Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md
```

When decomposing:

```text
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
Pipeline/TaskDecomposition/README.md
```

When implementing/closing gameplay work:

```text
Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md
Pipeline/ExecutionCrew/README.md
Pipeline/TaskDelivery/README.md
```

Broader RAG/scanner/artifact-authority context remains in:

```text
Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md
```

That broader file is not a statement that D1B.2 currently uses RAG.
