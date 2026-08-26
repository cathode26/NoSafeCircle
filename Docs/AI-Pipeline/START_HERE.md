# START HERE — No Safe Circle AI Pipeline

This is the first file any AI assistant or developer should read before working on the autonomous development pipeline.

## Core rule

**The repository is the source of truth.**

Do not reconstruct the current pipeline from an old chat transcript. Read the current repository state and routed documentation first.

## Current status snapshot

Last refreshed after D1B.2 round-robin decomposition merged to `main` on 2026-08-26.

Observed merged baseline:

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

Current implemented major pipeline pieces include:

- persistent schema-v2 TaskGraph;
- evidence-derived current conformance;
- provider-neutral AgentRuntime / TaskExecution;
- Claude Code and OpenAI/Codex provider adapters;
- Contract Locality Auditor;
- Minimum Production ExecutionCrew;
- Unity/runtime/human validation and TaskDelivery evidence path;
- D1A deterministic progressive-decomposition contracts and graph planning;
- decomposed-parent aggregate-feature semantics;
- D1B.1 compatible one-provider decomposition;
- **D1B.2 bounded round-robin decomposition verification/refinement**.

Autonomous dispatch remains intentionally disabled:

```text
TASK READINESS: UNAVAILABLE — DISPATCH POLICY NOT ENABLED
EXECUTION AUTHORIZATION: DENIED
```

A `conformant` state never grants readiness, execution, graph-application, or merge authority.

## Read current architecture first

For the concise design that exists now:

`Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`

For live routing/status and current proving priorities:

`Docs/AI-Pipeline/CURRENT_STATE.md`

## If the human asks you to pick and start a task

A request such as **"pick a task," "start another task," or "go pick a task and start on it"** is sufficient instruction to begin the repository-driven task-selection workflow. Do not require the human to preselect an NSC ID when the committed selection policy can choose safely.

Before selecting work:

1. read `Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md`;
2. read `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`;
3. read `Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md`;
4. inspect current TaskGraph state;
5. inspect GitHub Issues for shared operational claims;
6. inspect exclusive-resource conflicts;
7. claim before execution.

Fresh implementation candidate discovery starts with:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

Decomposition candidate discovery also inspects active contracts:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

`not_delivered` and contract shape are candidate signals only. They do not prove dependency readiness or execution authorization.

## Current decomposition rule

For normal new production decomposition, use **D1B.2 round robin**, not the old one-provider path.

Normal CLI:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

Default provider sequence:

```text
Codex authors
    ↓
Claude reviews/revises
    ↓
Codex reviews/revises
    ↓
Claude reviews/revises
```

The run stops earlier when an independent reviewer passes or when the system reaches `needs_human`, failure, or the circuit breaker.

The most recent candidate author may never approve that candidate.

Canonical Docker-backed invocation:

```bash
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

Real Windows decomposition output belongs under:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>\
```

All D1B.2 output is `review_only_not_applied`.

The compatible D1B.1 one-provider command remains available only when specifically desired:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <codex|claude>
```

Read:

```text
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
Pipeline/TaskDecomposition/README.md
Docs/AI-Pipeline/ADR-034_DECOMPOSED_AGGREGATE_FEATURES.md
Docs/AI-Pipeline/ADR-035_ROUND_ROBIN_DECOMPOSITION_REVIEW.md
Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md
```

## Current GDDRAG boundary

`Pipeline/GDDRAG` is a production deterministic search tool over the current canonical GDD, but **D1B.2 does not currently use it**.

Current decomposition review receives the full committed GDD through the deterministic context package. The project is intentionally proving this full-context round-robin design before adding retrieval complexity.

A possible future GDDRAG-assisted reviewer is documented in `CURRENT_PIPELINE_DESIGN.md`. It should be built only if live decomposition shows meaningful token/context/latency pressure or repeated canon-attention failures.

## If you are implementing gameplay

Read:

```text
Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md
Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md
Pipeline/ExecutionCrew/README.md
Pipeline/TaskDelivery/README.md
Docs/Engineering/UNITY_TESTING_POLICY.md
```

The current implementation flow is:

```text
clean source + TaskGraph preflight
        ↓
Contract Locality Auditor
        ├─ contract problem → CONTRACT_REVIEW_REQUIRED
        └─ local contract
               ↓
           Implementer
               ↓
       deterministic scope check
               ↓
         Unity Test Author
               ↓
       deterministic scope check
               ↓
          read-only Validator
               ↓
      optional bounded repair
               ↓
          human review
               ↓
 authoritative Unity/runtime evidence
               ↓
 TaskDelivery + committed evidence
               ↓
 evidence-derived conformance
               ↓
       human merge authority
```

ExecutionCrew does not run Unity, apply graph deltas, commit/push/merge automatically, or grant conformance/readiness.

## Decomposed-parent rule

A newly decomposed parent becomes a non-executable aggregate feature. Its explicit executable descendants own all implementation work.

If components require later assembly or sewing, that work must be its own child task. There is no hidden implementation pass on the aggregate parent.

Downstream tasks must consume the concrete child capability they actually need rather than keeping an ordinary dependency on the decomposed aggregate.

## Current intentional gaps

Still not implemented as production authority:

```text
D1C reusable reviewed graph application
Artifact Authority / production artifact-generation GER
Dependency readiness policy
Autonomous dispatch
Automatic merge authority
GDDRAG-assisted D1B.2 review
```

## Required reading order

1. `Docs/AI-Pipeline/CURRENT_STATE.md`
2. `Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`
3. task-selection/orchestration docs when choosing real work;
4. delivery docs when implementing/closing gameplay work;
5. `Pipeline/TaskDecomposition/README.md` when decomposing;
6. `Docs/AI-Pipeline/DECISIONS.md` when changing architecture/authority semantics;
7. broader milestone context only when the current work actually needs it.

`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md` is broader architectural/future context. It must not be mistaken for the exact current D1B.2 runtime: current D1B.2 still includes the full committed GDD and does not yet use GDDRAG retrieval.

## Development rule

Use the real game to decide what infrastructure to build next:

```text
real near-frontier work
        ↓
use current pipeline
        ↓
measure what failed or cost too much
        ↓
add the smallest justified infrastructure slice
```

In particular, test D1B.2 decomposition before adding GDDRAG to it.

## End-of-session rule

Before ending a meaningful pipeline architecture session:

1. update `CURRENT_STATE.md` when the current architecture/proving frontier changed;
2. update `CURRENT_PIPELINE_DESIGN.md` when actual runtime architecture changed;
3. update `DECISIONS.md` or an ADR when authority semantics changed;
4. keep commands and usage examples current;
5. commit documentation with the implementation or architecture change it describes.
