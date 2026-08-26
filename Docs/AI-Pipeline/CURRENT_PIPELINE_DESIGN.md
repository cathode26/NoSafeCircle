# Current No Safe Circle AI Pipeline Design

Status: current architecture snapshot after D1B.2 round-robin decomposition merged to `main` on 2026-08-26.

This document describes the system that exists now. It separates current runtime behavior from future possibilities so an agent does not accidentally treat an architectural idea as implemented authority.

## Current merged baseline

Observed merged `main` for this snapshot:

```text
fabb221c83efde230272760400d01747b90c0dc7
```

Current validated TaskGraph shape:

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

Autonomous dispatch remains disabled. TaskGraph state inspection never grants readiness, execution, merge, or graph-application authority.

## System at a glance

```text
                           APPROVED CANON
                    Docs/GDD/No_Safe_Circle_GDD.md
                              │
                              ▼
                        Persistent TaskGraph
                     Tasks/*.yaml schema 2.0
                              │
            ┌─────────────────┴──────────────────┐
            │                                    │
            ▼                                    ▼
   CONCRETE EXECUTABLE WORK             OVERSIZED / DECOMPOSITION WORK
            │                                    │
            ▼                                    ▼
 Contract Locality Auditor             D1A deterministic contracts
            │                                    │
            ▼                                    ▼
       ExecutionCrew                    D1B.2 round-robin circuit
            │                         Codex → Claude → Codex → Claude
            ▼                                    │
 Implementer → Test Author                        ▼
       → Validator                       deterministic validation
            │                           after every candidate
            ▼                                    │
 Unity/runtime/human validation                   ▼
            │                         PASS / REVISE / NEEDS_HUMAN
            ▼                                    │
 TaskDelivery + committed evidence                ▼
            │                          review_only_not_applied
            ▼                                    │
 evidence-derived conformance                     ▼
                                                HUMAN REVIEW
                                                    │
                                                    ▼
                                      targeted/manual graph application
                                      (D1C reusable application tooling
                                             is NOT implemented)
```

## Authority layers

### Canon

The current committed GDD is root game-design authority. Approved subordinate design artifacts may extend allowed detail but may not contradict canon.

### Task contracts

`Tasks/*.yaml` defines approved bounded work. Task contracts own:

- stable `NSC-###` identity;
- parent/dependencies;
- AC/VAL/INT obligations;
- execution/decomposition scope;
- exclusive resources;
- contract revision/disposition;
- decomposition aggregate metadata when applicable.

Task contracts do not store mutable completion truth.

### Evidence-derived conformance

`Pipeline/TaskGraph/current_conformance.py` derives state from committed task/evidence/Git identities. It does not use GDDRAG and should remain exact rather than retrieval-based.

### GitHub Issues

GitHub Issues are shared operational coordination only: claim, worker identity, planned approach, closeout, and human visibility. TaskGraph and committed evidence remain authoritative.

## Implementation-work path

For one concrete task:

```text
human/generic selection
        ↓
TaskGraph + GitHub claim/resource checks
        ↓
canonical isolated task checkout
        ↓
Contract Locality Auditor
        ├─ contract problem → CONTRACT_REVIEW_REQUIRED
        └─ local contract
               ↓
          ExecutionCrew
               ↓
       candidate implementation
               ↓
      Unity/runtime/human proof
               ↓
        TaskDelivery review
               ↓
       committed evidence
               ↓
 evidence-derived conformance
               ↓
        human merge authority
```

The implementation path remains bounded and human-controlled. ExecutionCrew does not grant its own completion or merge authority.

## Progressive decomposition path

### D1A — deterministic decomposition semantics

D1A validates decomposition-result schema/policy, exact parent requirement coverage, child boundaries, local/existing dependencies, inbound dependency rewrites, resource ownership, and complete proposed graph overlays.

A successful new decomposition proposal transitions the selected parent conceptually from executable task work into a non-executable aggregate feature:

```text
kind: feature
execution_scope: not_applicable
decomposition_state: decomposed
decomposition_children: [all active direct children]
exclusive_resources: []
```

Aggregate completion is derived from its explicit child set, bound to the parent requirements that were actually decomposed.

No required implementation or integration work may remain hidden in the parent. If independently implemented components need a later sewing/assembly pass, that pass must itself be an explicit executable child task.

Active downstream dependencies on a decomposed aggregate are rewritten to the concrete child capability they consume. Ordinary executable work does not remain dependent on the aggregate parent.

### D1B.1 — compatible single-provider mode

D1B.1 remains available for diagnostics, comparison, and compatibility:

```text
one provider authors candidate
        ↓
deterministic D1A validation
        ↓
review-only result
```

It does not provide independent semantic cross-review.

### D1B.2 — current normal decomposition mode

D1B.2 is now implemented and is the normal path for new production decomposition work.

Default provider order:

```text
Round 1  Codex   authors candidate 1
              ↓
         deterministic validation
              ↓
Round 2  Claude  independently reviews
              ├─ PASS → review_ready
              ├─ NEEDS_HUMAN → needs_human
              └─ REVISE → Claude authors candidate 2
                                 ↓
                            deterministic validation
                                 ↓
Round 3  Codex   independently reviews candidate 2
              └─ continue while budget remains
```

The key invariant is:

```text
The provider that most recently authored or revised the current candidate
may not approve that candidate.
```

There is no majority vote. A current deterministically valid candidate becomes `review_ready` when an independent reviewer returns PASS and no blocking finding remains unresolved.

Reviewers explicitly challenge:

- duplicate responsibilities;
- hidden integration/sewing work;
- unnecessary integration children;
- non-local completion gates;
- incorrect downstream dependency rewrites;
- missing or misleading parent coverage;
- child granularity/local-completability;
- ownership conflicts with existing tasks/canon;
- invented bookkeeping work;
- whether completing every child really completes the parent feature.

Every initial or revised candidate passes deterministic D1A/graph/aggregate validation before another provider reviews it.

### Findings and refinement

Blocking findings are immutable structured records. Later rounds must classify each unresolved prior finding as:

```text
resolved
withdrawn
still_blocking
```

A persistent defect keeps the same finding ID instead of being recreated every round.

The default circuit breaker is four AI calls. If the last allowed call produces a revision, the run ends `needs_human`; an unreviewed revision cannot self-approve.

## Current decomposition usage

### Normal D1B.2 command

From a physically read-only decomposition checkout in Docker:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id NSC-016
```

Default providers are:

```text
codex,claude
```

Explicit equivalent:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id NSC-016 --providers codex,claude --max-calls 4
```

Canonical Compose invocation:

```bash
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id NSC-016
```

The `round-robin-decompose` service has both Claude and Codex auth/config volumes, a physically read-only `/workspace`, and an external writable decomposition-output mount.

### Canonical Windows output root

Before running real decomposition:

```powershell
$TaskId = "NSC-016"
$env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT = "C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\$TaskId"
New-Item -ItemType Directory -Force -Path $env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT | Out-Null
```

Each run creates its own no-overwrite child directory:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>\
```

Do not pre-create the `<RunId>` directory.

### D1B.2 exit/status meaning

The CLI returns success for either bounded useful outcome:

```text
review_ready
needs_human
```

`review_ready` means the current candidate passed deterministic validation and an independent provider review. It still does not authorize TaskGraph application.

`needs_human` means the bounded review circuit reached an authority/circuit-breaker boundary. It is a useful decomposition diagnosis, not permission to invent a resolution.

Provider/runtime/invalid-output failures remain non-success outcomes.

### Compatible D1B.1 command

Use D1B.1 only when one-provider behavior is specifically desired:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-016 --provider codex
```

Normal new decomposition should prefer D1B.2.

## Current decomposition outputs

A D1B.2 run preserves the original context plus every round:

```text
<RunId>/
  decomposition_request.json
  context.json
  progress.jsonl
  decomposition_run_result.json
  decomposition_result.json       # only after independent PASS
  graph_delta.json                 # only after independent PASS + decomposed
  rounds/
    01-request.json
    01/...
    02-request.json
    02/...
    ...
```

All artifacts are `review_only_not_applied`.

D1C reusable reviewed graph-application tooling is not implemented. Human-reviewed targeted application remains a separate authority boundary.

## GDDRAG — current role

`Pipeline/GDDRAG` exists as a production, deterministic, hash-verified search index over the current canonical GDD.

It is **not currently connected to D1B.2**.

Current D1B.2 reviewer context includes the full committed GDD through the deterministic context package. We are intentionally testing this design first instead of prematurely optimizing it.

The immediate proving question is:

```text
Does full-context round-robin decomposition produce reliable semantic review
without unacceptable token use, latency, or context-pressure failures?
```

## Possible future GDDRAG assist — not implemented

Only add GDDRAG to D1B.2 if live proving shows a real need, such as:

- provider context/token pressure;
- repeated latency caused by large full-context prompts;
- relevant canon being overlooked despite being present;
- materially unnecessary repeated whole-GDD prompt cost.

If needed, the preferred future design is additive:

```text
current candidate + TaskGraph context
        ↓
deterministically derive review queries from
parent AC/VAL/INT + proposed children + rewrites + unresolved findings
        ↓
validate current GDDRAG index
        ↓
retrieve + deduplicate + cap current-canon chunks
        ↓
reviewer receives targeted navigation hints
        + existing authoritative context
```

Important future constraints:

- GDDRAG remains navigation assistance, not canon authority;
- stale/invalid RAG output is never used;
- top-k omission never proves a requirement is absent;
- TaskGraph ownership and full committed canon remain authoritative;
- retrieval should be deterministic, deduplicated, and text-capped;
- per-round retrieval should be preserved as an immutable review artifact;
- RAG should not be added merely because it exists; add it only after measurement justifies the complexity.

A possible later optimization, only after enough live data, is to reduce repeated full-GDD prompt material while keeping a fail-closed path to complete canon. That is not the current system.

## What is deliberately not implemented yet

```text
D1C reusable graph application authority
Artifact Authority implementation
Artifact generation/Artifact GER production flow
Dependency readiness policy
Autonomous dispatch
Automatic merge authority
GDDRAG-assisted D1B.2 review
```

## Current proving strategy

Use the actual game to test the pipeline before adding more infrastructure:

```text
real near-frontier task
        ↓
D1B.2 decomposition
        ↓
inspect quality + calls + latency + context/token behavior
        ↓
apply/fix only what evidence shows is missing
```

The immediate decomposition proving target is the Ranged Enemy (`NSC-016`) because prior single-provider runs exposed exactly the semantic ownership/locality problems D1B.2 was built to catch.

Do not add GDDRAG to D1B.2 until that proving run tells us whether it is necessary.

## Core principle

```text
Deterministic tools establish facts, identities, graph validity, and evidence.
LLMs make bounded semantic judgments.
Independent providers cross-review decomposition decisions.
Humans retain authority over design ambiguity, graph application, and merge.
```
