# Stage 5 / D1C Task Decomposition Audit — Executive Summary

Base commit audited: `565898a80e16e2aaa7ecf78d024bca1197053aa4` (branch `design/stage5-decomposition-audit`).

This is a design/audit deliverable only. Nothing under `Pipeline/`, `Tasks/`, `.github/`, or any other
production path was modified to produce it. See `Docs/AI-Pipeline/Stage5-Decomposition-Design/` for the
full document set.

## What "Stage 5" actually means in this repository

**FACT.** The repository's own naming already reserves "Stage 5" for exactly one thing. `Pipeline/TaskReviewAgent/fresh_dispatch.py` states explicitly: *"Stage 5 decomposition: a `no_safe_work` plan is reported as-is; this module never routes into the Progressive Decomposer."* `AI_PIPELINE.md` lists **"D1C reusable reviewed graph application"** as a current intentional gap, alongside "Dependency readiness policy" and "Autonomous dispatch."

**INFERENCE.** Stage 5 is not "more decomposition intelligence." D1A (deterministic contracts/graph-delta planning) and D1B.1/D1B.2 (proposal + independent cross-provider review) are already implemented, tested, and in active production use (D1B.2 merged 2026-08-26 per `Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`). What does **not** exist is:

1. **D1C** — a reusable, deterministic, human-authorized boundary that takes a `review_ready` decomposition result plus its `graph_delta.json` and actually mutates `Tasks/*.yaml` + `Pipeline/TaskGraph/WORK_ID_MAP.json` + `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml` on disk, commits it, and hands the new parent/children back to the graph.
2. **Orchestrator integration** — today `decomposition` is a *documentation convention* (`AGENTS.md`, `AI_PIPELINE.md`, `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`) followed by a human-directed ChatGPT/Claude session running shell commands by hand. It is **not** wired into the deterministic Python dispatch/claim/Issue machinery (`dispatch_plan.py`, `fresh_dispatch.py`, `issue_workflow.py`) that governs real implementation work. There is no `work_type` field anywhere in `Pipeline/` code (`grep -r work_type Pipeline/` returns only prose in `Pipeline/TaskDecomposition/README.md`), no decomposition `WorkflowPhase`, and `evaluate_fresh_candidate()` structurally excludes every decomposition-relevant parent (it requires `kind == "implementation"`, `execution_scope == "single_agent"`, `decomposition_state == "concrete"` — see `Pipeline/TaskReviewAgent/dispatch_plan.py:190-203`).

So: **Stage 5 = D1C graph application + wiring decomposition into the same durable-Issue/claim/checkout machinery that already governs implementation work**, so that "go pick a task" can safely select, apply, and unlock decomposition work exactly as reliably as it already selects implementation work.

## What is already implemented (do not rebuild)

| Layer | State | Evidence |
| --- | --- | --- |
| D1A deterministic contracts/policy/graph-delta planning | **Implemented** | `Pipeline/TaskDecomposition/contracts.py`, `policy.py`; `Pipeline/TaskGraph/graph_delta.py` (`plan_graph_delta`) |
| D1B.1 single-provider proposal | **Implemented** | `Pipeline/TaskDecomposition/run_decomposition.py`, `live_decomposition.py` |
| D1B.2 round-robin cross-provider review | **Implemented, current normal mode** | `Pipeline/TaskDecomposition/run_round_robin_decomposition.py`, `round_robin_decomposition.py`, ADR-035 |
| Decomposed-aggregate graph semantics | **Implemented** | `Pipeline/TaskGraph/decomposition_graph_semantics.py`, consumed by `current_conformance.py` and `graph_delta.py` |
| `needs_replan` on aggregate requirement drift | **Implemented** | `Pipeline/TaskGraph/current_conformance.py:_explicit_aggregate_conformance` |
| Atomic multi-file staged graph publication (bootstrap only) | **Implemented, not reusable as-is** | `Pipeline/TaskGraph/work_graph_persist.py` (`persist_work_graph`) |
| TaskGraph logical readiness / dependency evaluation | **Partial** — evidence-derived conformance exists; a general readiness *policy* is an explicit listed gap | `current_conformance.py`; `AI_PIPELINE.md` "Current intentional gaps" |
| Exclusive-resource claims + short-lived atomic Git claim refs | **Implemented** | `Pipeline/TaskReviewAgent/claim_refs.py`, `claim_policy.py` |
| Durable GitHub Issue workflow authority | **Implemented for implementation work only** | `Pipeline/TaskReviewAgent/issue_workflow.py` (`WorkflowState`, `WorkflowPhase` has 5 values, none decomposition) |
| Generic resume-first / fresh dispatch | **Implemented for implementation work only** | `Pipeline/TaskReviewAgent/dispatch_plan.py`, `fresh_dispatch.py` |
| Isolated task checkout | **Implemented for implementation; documented-only for decomposition** | `Pipeline/TaskReviewAgent/durable_checkout.py`, `resumable_checkout.py`; decomposition checkout is `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` prose, no Python module |
| D1C reusable graph application | **Not implemented** | Explicitly listed as a gap in `AI_PIPELINE.md`, `CURRENT_PIPELINE_DESIGN.md`, `Pipeline/TaskDecomposition/README.md` |
| Decomposition as a dispatcher/claim/Issue work unit | **Not implemented** | No `work_type` in code; `fresh_dispatch.py` explicitly excludes it |

See `CURRENT_STATE_AUDIT.md` for the full capability-by-capability inventory with authority boundaries and test evidence.

## What remains (Stage 5 scope)

1. **D1C** — deterministic graph-application boundary (`D1C_GRAPH_APPLICATION_DESIGN.md`).
2. **Orchestrator integration** — decomposition as a first-class durable work unit alongside implementation (`ORCHESTRATOR_INTEGRATION_DESIGN.md`).
3. **Concurrency proof** — races specific to graph mutation, not just task claiming (`CONCURRENCY_AND_FAILURE_MODEL.md`).
4. **Bounded implementation slices** — `IMPLEMENTATION_SEQUENCE.md`.
5. **Test plan** — `TEST_PLAN.md`.
6. **Explicit Gauntlet dependency map** — `GAUNTLET_PREREQUISITES.md`.

## Recommended implementation sequence (summary; detail in `IMPLEMENTATION_SEQUENCE.md`)

```text
CURRENT PROJECT EXECUTION GATE: no Stage 5 code implementation until the live Gauntlet is accepted.
Design/audit/test specification may proceed while the Gauntlet runs.

1. D1C deterministic planner/preflight — IMPLEMENT AFTER GAUNTLET (design is deterministic and may be finalized now)
2. Local transactional materialization — IMPLEMENT AFTER GAUNTLET
3. D1C application tests — IMPLEMENT AFTER GAUNTLET
4. Durable Issue phase additions — IMPLEMENT AFTER GAUNTLET
5. Generic dispatcher/resume integration — AFTER GAUNTLET AND AFTER production #104 adoption audit is closed
6. Concurrency serialization / affected-contract authority — AFTER GAUNTLET; Slice 6b also needs its own proof
7. Live single-decomposition proof — AFTER Slices 1-6 and required prerequisites
8. Multi-worker proof — AFTER single-worker proof
9. Autonomous/background enablement consideration — separate authorization; out of Stage 5 scope
```

## Explicit prerequisites from the live Gauntlet

The Gauntlet is the first real multi-worker proof of `dispatch_plan.py` + `fresh_dispatch.py` + `claim_refs.py` + `issue_workflow.py` under genuine concurrent load (`Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md`: *"the next planned milestone is the dedicated multi-worker Gauntlet... run real simultaneous workers to prove concurrency behavior outside local synthetic fixtures"*). Stage 5's orchestrator-facing slices reuse or extend that machinery, and the current project gate therefore waits for Gauntlet acceptance before **any** Stage 5 code implementation begins. In addition, production issue **#104** must close the remaining direct Issue mutation → immediate-readback adoption gaps before Stage 5 enables Issue-mutating decomposition slices (Slice 5+). Gauntlet acceptance is necessary but does not by itself prove the new Slice 6b atomic multi-task claim extension. Full detail and per-prerequisite reasoning is in `GAUNTLET_PREREQUISITES.md`.

## GO / WAIT / DO-NOT-DO

| Item | Status | Reason |
| --- | --- | --- |
| Continue Stage 5 design/audit/test specification | **GO** | Documentation-only work does not mutate production behavior |
| Implement D1C planner/materializer/tests (Slices 1-3) | **WAIT** | Technically deterministic, but the current project gate freezes all Stage 5 code until Gauntlet acceptance |
| Implement D1C dry-run/mutation-plan code | **WAIT** | Same project gate; design may be finalized now |
| Wire `work_type: decomposition` into `dispatch_plan.py`/`issue_workflow.py` for real multi-worker use | **WAIT** | Requires Gauntlet acceptance; Issue-mutating use also depends on production #104 closure |
| Enable decomposition candidates in generic resume-first selection | **WAIT** | Same dependency; also depends on serialization design in `CONCURRENCY_AND_FAILURE_MODEL.md` |
| Run a live single-worker D1C application against a real parent | **WAIT** | Should follow, not precede, deterministic test coverage and Gauntlet acceptance |
| Run multi-worker D1C application races | **WAIT** | Explicitly the highest-risk untested case; must follow single-worker proof |
| Enable autonomous/background dispatch for decomposition | **DO NOT DO** | Out of scope for Stage 5 entirely; requires separate authorization per `AI_PIPELINE.md` |
| Speculatively decompose the whole backlog | **DO NOT DO** | Violates ADR-021 (progressive, just-in-time decomposition); unrelated to Stage 5 readiness |
| Reuse `work_graph_persist.py`'s bootstrap-only functions directly for D1C | **DO NOT DO** | `assert_bootstrap_targets_absent` refuses to run once `Tasks/` is non-empty; it is bootstrap-only by design, not a general apply primitive (see `D1C_GRAPH_APPLICATION_DESIGN.md`) |

## Biggest architectural risk found

Decomposition and implementation currently run on **two disconnected authority systems**: implementation work has a deterministic, tested, claim-guarded, durably-leased dispatch pipeline; decomposition work has a well-specified *deterministic core* (D1A/D1B) wrapped in a *prose-driven* orchestration convention with no code-level claim/lease/resume guarantees. A human/agent could decompose the same parent twice, or start applying a stale `graph_delta.json` after another worker already changed the parent, with nothing but a documentation convention (`AGENTS.md` line 25: *"Review-only decomposition outputs do not reserve future NSC IDs..."*) standing in the way. See `CURRENT_STATE_AUDIT.md` and `CONCURRENCY_AND_FAILURE_MODEL.md`.

## Documents in this set

```text
README.md                              — this file
CURRENT_STATE_AUDIT.md                 — code-grounded capability inventory
D1C_GRAPH_APPLICATION_DESIGN.md        — the missing graph-application boundary
ORCHESTRATOR_INTEGRATION_DESIGN.md     — decomposition as a durable orchestrator work unit
CONCURRENCY_AND_FAILURE_MODEL.md       — race-by-race threat model
IMPLEMENTATION_SEQUENCE.md             — bounded reviewable PR slices
TEST_PLAN.md                           — deterministic + live test plan, existing vs. missing
GAUNTLET_PREREQUISITES.md              — what Stage 5 must not assume until the Gauntlet proves it
```
