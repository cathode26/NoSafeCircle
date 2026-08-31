# Current State Audit — Decomposition and Orchestrator Capabilities

Base commit: `565898a80e16e2aaa7ecf78d024bca1197053aa4`.

Legend: **FACT** = directly observed in code/tests/docs at this commit. **INFERENCE** = logically follows
from observed facts. **RECOMMENDATION** = proposed for Stage 5, not current state.

## D1A — deterministic decomposition contracts/policy/graph-delta planning

**Status: Implemented.**

- `Pipeline/TaskDecomposition/contracts.py` — immutable `DecompositionResult`/`ParentTaskIdentity`/child
  contract dataclasses; strict parse/validate from provider JSON.
- `Pipeline/TaskDecomposition/policy.py` — `validate_decomposition_result`, `semantic_json_sha256`; enforces
  exact parent AC/VAL/INT coverage, resource-lock forms, child boundaries.
- `Pipeline/TaskGraph/graph_delta.py::plan_graph_delta` — pure function: reparses a validated
  `DecompositionResult`, deterministically allocates child `NSC-###` IDs (`next_number = max(existing) + 1`,
  contiguous), builds a complete in-memory `proposed_graph_overlay` (id_map, tasks, resource_groups,
  project_requirements), and validates it with `validate_work_graph_plan` +
  `validate_decomposition_graph_semantics` before returning. **Performs no filesystem writes** (FACT, no
  `open(..., "w")`/`Path.write*` calls in the module).
- `Pipeline/TaskGraph/decomposition_graph_semantics.py` — post-decomposition invariants: parent
  `kind=feature`, `execution_scope=not_applicable`, `exclusive_resources=[]`, `decomposition_children` exactly
  equals active direct children, no active contract may still `depends_on` a decomposed aggregate,
  `decomposition_requirement_sha256` present and well-formed.
- Authority boundary: **read-only over the graph; produces an immutable `GraphDeltaPlan` value object.**
  `graph_delta.py` payload literally carries `"authority": "review_only_not_applied"`.
- Tests: `Pipeline/TaskGraph/graph_delta_smoke_test.py`,
  `Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py`,
  `Pipeline/TaskDecomposition/tests/decomposition_contracts_smoke_test.py`.
- Docs/code agreement: consistent. `Pipeline/TaskDecomposition/README.md` §"D1A deterministic foundation"
  matches the code exactly, including the "D1A is model-free and performs no writes" claim.

## D1B.1 — single-provider proposal/diagnosis

**Status: Implemented.**

- `Pipeline/TaskDecomposition/run_decomposition.py`, `live_decomposition.py`,
  `Pipeline/TaskDecomposition/context_builder.py` (`build_context`, `capture_clean_source`,
  `source_revalidation_reasons`, `validate_task_selection`).
- Source binding: exact HEAD/tree/branch captured before the provider call
  (`context_builder.capture_clean_source`), revalidated after
  (`source_revalidation_reasons`) and again immediately before publishing accepted artifacts
  (per `Pipeline/TaskDecomposition/README.md` — confirmed by the presence of
  `source_revalidation_reasons` as a distinct post-call check).
- Physical isolation: `require_physical_read_only` (statvfs `ST_RDONLY` check) and
  `require_output_disjoint` (output root must not be equal to, under, or contain the source root).
- Authority: `review_only_not_applied`. No write capability granted to the provider
  (`context_builder` never includes `repository_write`; `Pipeline/TaskDecomposition/README.md` states the
  Decomposer receives only `repository_read`/`repository_search`).
- Tests: `Pipeline/TaskDecomposition/tests/context_builder_smoke_test.py`,
  `Pipeline/TaskDecomposition/tests/live_decomposition_smoke_test.py`.
- **Doc/doc contradiction (FACT):** `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md` and
  `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` still describe D1B.1 as *"the production command"* /
  *"the existing Stage D1B.1 read-only pipeline"* for generic selection, while
  `AI_PIPELINE.md`, `Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`, and
  `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md` all state D1B.2 is now the normal mode and D1B.1 is
  compatibility-only. `GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md` and
  `DECOMPOSITION_CHECKOUT_ISOLATION.md` were not updated when D1B.2 shipped (2026-08-26). This is a stale-doc
  gap, not a code defect — an operator following the older doc would run the compatibility path by default.

## D1B.2 — round-robin cross-provider review/refinement

**Status: Implemented, current normal mode.**

- `Pipeline/TaskDecomposition/round_robin_decomposition.py`, `run_round_robin_decomposition.py`.
- Enforces: latest author may never approve; every candidate/revision revalidated through the full D1A stack
  before another provider reviews it; structured findings with persistent IDs and
  `resolved|withdrawn|still_blocking` tracking; circuit breaker defaulting to 4 calls
  (`NSC_DECOMPOSITION_ROUND_ROBIN_MAX_CALLS`, range 2-12); unreviewed final revision cannot self-approve
  (`needs_human`).
- Tests: `Pipeline/TaskDecomposition/tests/round_robin_decomposition_smoke_test.py`,
  `round_invocation_id_smoke_test.py`, `review_contracts_smoke_test.py`.
- Authority: `review_only_not_applied` (ADR-035, `Pipeline/TaskDecomposition/README.md`).
- GDDRAG (`Pipeline/GDDRAG`) exists but is explicitly **not connected** to D1B.2
  (`AI_PIPELINE.md` §"GDDRAG and decomposition"). Not part of Stage 5 scope.

## Decomposition as an orchestrator work type

**Status: Documentation convention only. Not implemented in code.**

- **FACT:** `grep -r work_type Pipeline/` matches exactly one file,
  `Pipeline/TaskDecomposition/README.md` (prose), and zero `.py` files. There is no `work_type` field in any
  dataclass, JSON schema, or Issue state model in `Pipeline/`.
- **FACT:** `Pipeline/TaskReviewAgent/issue_workflow.py::WorkflowPhase` enumerates exactly
  `IMPLEMENTATION, REPAIR, UNITY_RUNTIME_VALIDATION, DELIVERY_EVIDENCE, MERGE_CLOSEOUT`. No decomposition
  phase exists.
- **FACT:** `Pipeline/TaskReviewAgent/dispatch_plan.py::evaluate_fresh_candidate` requires
  `kind == "implementation"`, `execution_scope == "single_agent"`, `decomposition_state == "concrete"`
  (lines ~190-203). A decomposition-relevant parent (`execution_scope: needs_execution_decomposition`) is
  therefore **structurally rejected** by the same deterministic kernel used for both automatic ranking and
  explicit `-TaskId` admission.
- **FACT:** `Pipeline/TaskReviewAgent/fresh_dispatch.py` module docstring states outright: *"Stage 5
  decomposition: a `no_safe_work` plan is reported as-is; this module never routes into the Progressive
  Decomposer."*
- **INFERENCE:** Everything the docs describe as "decomposition orchestrator work type" — claiming the parent's
  GitHub Issue, posting `work_type: decomposition` in a Claim/Planned Approach comment, running the Docker
  compose CLI by hand, posting a Decomposition Closeout comment — is executed by a **human-directed reasoning
  agent following markdown instructions**, not by `dispatch_plan.py`/`fresh_dispatch.py`/`issue_workflow.py`.
  There is no deterministic guarantee (lease, claim ref, state machine) preventing two orchestrators from
  decomposing the same parent concurrently; the only defense is the documented convention in `AGENTS.md`
  line 25 and `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md` ("keep the parent
  operationally reserved... so another orchestrator does not immediately rerun the same decomposition").
- Docs consistently and correctly describe this as *prose convention*, not as a stronger guarantee — none of
  the reviewed docs claim code-level lease protection for decomposition. So this is a **gap**, not a
  doc/code contradiction.

## Durable Issue coordination (implementation work)

**Status: Implemented for implementation; absent for decomposition.**

- `Pipeline/TaskReviewAgent/issue_workflow.py` — `WorkflowState` (`agent_ready`, `agent_working`,
  `human_action_required`, `blocked`, `complete`), append-only hash-chained events, state-label
  synchronization, exact-commit PASS/FAIL parsing.
- `Pipeline/TaskReviewAgent/issue_workflow_store.py` — `IssueWorkflowService`, `list_agent_ready()`.
- Tests: `Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py` proves state/event round trips, hash-chain
  verification, lease creation/resume, exact-commit PASS/FAIL enforcement, tampered-history rejection.
- No decomposition-specific Issue phase or state exists (see above).

## Reservation/resume behavior

**Status: Implemented for implementation via claim refs + durable Issue leases. Not implemented for
decomposition.**

- `Pipeline/TaskReviewAgent/claim_refs.py` — short-lived atomic `refs/nsc/claims/tasks/<ID>` and
  `refs/nsc/claims/resources/<hash>` refs; `git push --atomic --force-with-lease=<ref>:` nonexistence CAS;
  fenced exact-SHA release; explicit no-TTL, no-automatic-GC policy (module docstring, `claim_policy.py`).
- `Pipeline/TaskReviewAgent/claim_policy.py` — committed, fail-closed policy; requires explicit
  `activation.status == "active"` naming a proven `activated_namespace` before any production claim ref may
  be created (`ClaimCoordinationNotActivatedError`). Live capability proof referenced:
  `Pipeline/TaskReviewAgent/evidence/stage1-github-claim-capability-20260830.json`.
- `acquire_issue_lease_with_claims` — holds the claim across durable-Issue acquisition, re-reads and verifies
  **exact** authority (task, `agent_working`, worker, `lease_id`, `state_version`, `last_event_id`) before
  releasing the claim; typed `lease_acquired_claim_cleanup_required` outcome when release fails after a
  verified acquisition — the durable fact is never silently lost.
- Tests: `Pipeline/TaskReviewAgent/tests/claim_refs_smoke_test.py`,
  `Pipeline/TaskReviewAgent/tests/contention_retry_smoke_test.py`.
- Decomposition has none of this. The only "resume/reservation" mechanism for decomposition is the prose
  instruction to keep the parent's Issue "clearly reserved/marked."

## Graph application

**Status: Not implemented.**

- **FACT:** No module in `Pipeline/TaskGraph/` or `Pipeline/TaskDecomposition/` writes a `GraphDeltaPlan` to
  `Tasks/*.yaml`. `grep -rn "graph_delta" Pipeline/` shows only planning (`graph_delta.py`) and consumption in
  tests/README prose — no apply/materialize function.
- **FACT:** `Pipeline/TaskGraph/work_graph_persist.py::persist_work_graph` is the closest existing pattern
  (stage to temp dir → validate staged bundle byte-for-byte → `os.replace` each artifact in order → rollback on
  exception), but it is **bootstrap-only**: `assert_bootstrap_targets_absent` raises
  `WorkGraphPersistenceError` if `Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json` already exists, or if
  `Tasks/` is non-empty. It is not reusable unmodified for repeated D1C applications against a populated
  graph.
- Explicit gap statements: `AI_PIPELINE.md` ("D1C reusable graph application" under "Current intentional
  gaps"); `Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md` ("D1C reusable application tooling is NOT
  implemented"); `Pipeline/TaskDecomposition/README.md` ("Stage D1C graph application is not implemented").
  All three agree; no contradiction.

## Post-application validation

**Status: Not implemented (nothing applies yet), but the validators it would reuse already exist.**

- `Pipeline/TaskGraph/work_graph_validate.py::validate_work_graph_plan` and
  `decomposition_graph_semantics.py::validate_decomposition_graph_semantics` are exactly the functions
  `graph_delta.py` already calls to certify the *proposed* overlay before returning it. A D1C apply step would
  reuse them to certify the *materialized* result — this is a strong, already-proven precedent
  (see `D1C_GRAPH_APPLICATION_DESIGN.md`).
- `Pipeline/TaskGraph/persistent_work_graph.py::load_persistent_work_graph` already re-validates the entire
  graph (structural + decomposition semantics) on every load from committed HEAD. It has no notion of "just
  applied" vs. "always was this way" — which is fine, since post-application validation is really just
  "load and validate," already implemented.

## Rollback/recovery

**Status: Pattern exists (bootstrap), not implemented for repeated D1C use.**

- `work_graph_persist.py::persist_work_graph`'s `except Exception` block reverse-walks `published` and
  removes/rmtree's each artifact it already replaced. This is filesystem-level, pre-commit rollback — it says
  nothing about Git-commit or push-level recovery, which D1C additionally needs (see
  `D1C_GRAPH_APPLICATION_DESIGN.md` §"Git commit boundary").

## Conformance/readiness after application

**Status: Implemented and ready to be exercised by D1C once it exists.**

- `Pipeline/TaskGraph/current_conformance.py::_explicit_aggregate_conformance` already fully implements the
  post-decomposition read path: hash-check `decomposition_requirement_sha256` against
  `aggregate_requirement_sha256(task)` (→ `needs_replan` on mismatch), else recurse into each
  `decomposition_children` entry and derive `conformant`/`aggregate` from child states.
- **This means D1C's job is narrower than it might appear**: it only needs to *materialize* a validated
  `GraphDeltaPlan` correctly. It does not need to invent new conformance logic — `current_conformance.py`
  already knows how to read the result.
- Tests: `Pipeline/TaskGraph/aggregate_conformance_smoke_test.py`,
  `Pipeline/TaskGraph/conformance_evaluator_smoke_test.py`.

## Dependency readiness policy (general)

**Status: Explicit gap, independent of decomposition.** `AI_PIPELINE.md` lists "Dependency readiness policy"
as not yet production authority. `Pipeline/TaskReviewAgent/dispatch_plan.py` implements a narrower
*dispatch-safety* kernel (own-state + dependency-state + resource/claim checks) that is sufficient for
Stage 4 implementation dispatch but is explicitly not a general graph-readiness policy. **INFERENCE:** Stage 5
does not need to solve general readiness; it only needs D1C to leave the graph in a state
`current_conformance.py` and `dispatch_plan.py` already interpret correctly (aggregate parent excluded from
dispatch, active children eligible).

## Human validation boundary

**Status: Implemented for implementation (`human_action_required`, exact-commit PASS/FAIL). Not implemented
for decomposition/application.** No code path exists today that asks a human to authorize "apply this
`graph_delta.json`." That authorization is currently 100% out-of-band (a human reads `decomposition_result.json`
and manually edits `Tasks/*.yaml`, per `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` §"Human review
must check completion locality").

## Delivery evidence/conformance/closeout pipeline

**Status: Implemented for implementation work; not connected to decomposition.**

- `Pipeline/TaskReviewAgent/downstream_pipeline.py`, `downstream_issue.py`, `delivery_review.py`,
  `record_delivery.py` — commit/push/PR/merge-closeout machinery for implementation tasks.
- Nothing in this pipeline currently has a route for "graph application landed on `main`"; D1C would need its
  own commit/push/closeout path (see `D1C_GRAPH_APPLICATION_DESIGN.md` §"Git commit boundary" and
  `ORCHESTRATOR_INTEGRATION_DESIGN.md`).

## Autonomous/background dispatch

**Status: Explicitly disabled.** `Pipeline/TaskReviewAgent/dispatch_policy.json`:
`"autonomous_dispatch": false`. Confirmed consistently across every reviewed doc. Not in scope for Stage 5.

## Summary table

| Capability | Status | Primary evidence |
| --- | --- | --- |
| D1A | Implemented | `graph_delta.py`, `contracts.py`, `policy.py` |
| D1B.1 | Implemented (compatibility) | `run_decomposition.py`, `context_builder.py` |
| D1B.2 | Implemented (normal mode) | `round_robin_decomposition.py`, ADR-035 |
| Decomposition as orchestrator work type | **Doc-only, not coded** | no `work_type` in `Pipeline/`; `fresh_dispatch.py` docstring |
| Durable Issue coordination (decomposition) | **Not implemented** | `WorkflowPhase` has no decomposition value |
| Reservation/resume (decomposition) | **Not implemented** | no claim-ref/lease integration |
| D1C graph application | **Not implemented** | explicit gap in 3 docs; no apply function found |
| Post-application validation | Ready to reuse, unexercised | `work_graph_validate.py`, `persistent_work_graph.py` |
| Rollback/recovery | Pattern exists, bootstrap-only | `work_graph_persist.py` |
| Conformance/readiness after application | Implemented | `current_conformance.py::_explicit_aggregate_conformance` |
