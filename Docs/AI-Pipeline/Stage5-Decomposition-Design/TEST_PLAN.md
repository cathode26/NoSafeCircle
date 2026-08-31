# Test Plan — Stage 5 / D1C

**RECOMMENDATION** document. Maps each required test to existing coverage (FACT, cites file) or marks it
missing (to be built per `IMPLEMENTATION_SEQUENCE.md`).

## Contract/schema validation

- **Status: exists.** `Pipeline/TaskDecomposition/tests/decomposition_contracts_smoke_test.py`,
  `Pipeline/TaskGraph/graph_delta_smoke_test.py`. No change needed for Stage 5; D1C consumes already-validated
  contracts.

## Stale-source rejection

- **Status: exists for D1B** (`Pipeline/TaskDecomposition/tests/context_builder_smoke_test.py` /
  `live_decomposition_smoke_test.py` cover `source_revalidation_reasons`).
- **Status: missing for D1C.** New: assert `apply_graph_delta`/Slice 1's planner rejects when
  `parent_before_hash` or `source_graph_semantic_hash` no longer match current HEAD (Slice 1 test suite,
  `IMPLEMENTATION_SEQUENCE.md`).

## Graph delta revalidation

- **Status: exists for planning-time validation** (`graph_delta_smoke_test.py` exercises
  `validate_work_graph_plan`/`validate_decomposition_graph_semantics` on the proposed overlay).
- **Status: missing for apply-time re-derivation.** New: assert D1C's recomputed plan equals the stored
  `graph_delta.json` byte-for-byte when nothing changed, and correctly diverges (with the divergence explained)
  when something did (Slice 1 test suite).

## ID collision

- **Status: exists for single-plan collision with existing reconciliation keys** (`graph_delta.py`'s
  `collisions = local_keys.intersection(source.id_map)` path, covered in `graph_delta_smoke_test.py`).
- **Status: missing for cross-application sequential allocation.** New: apply a plan for parent P1, THEN run a
  FRESH `plan_graph_delta` for a different parent P2 against the resulting HEAD, and assert the fresh plan
  correctly allocates the next ID after P1's children (Slice 2/3 test suite). **CORRECTED:** this is not "the
  same stored plan's recomputed allocation shifts" — a stale stored plan must instead be rejected as
  `stale_proposal` (see the "Sequential re-apply" test below and race #2 in `CONCURRENCY_AND_FAILURE_MODEL.md`).

## Sequential re-apply after another plan lands (broadened from "overlapping" — race #16, corrected)

- **Status: missing entirely.** New: race #16 fixture — apply plan A for any parent, then attempt to apply plan
  B (authorized against the same pre-A HEAD, for ANY other parent, whether or not their affected-contract sets
  literally overlap — since `source_graph_semantic_hash` covers the whole graph, overlap is not required to
  reproduce this); assert B fails closed as `stale_proposal`. A second case confirms a freshly re-run D1B for
  B's parent against post-A HEAD produces a new, independently valid `plan_id` (Slice 3/6 test suite).

## Parent → aggregate conversion

- **Status: exists for the read side** (`Pipeline/TaskGraph/aggregate_conformance_smoke_test.py` exercises
  `_explicit_aggregate_conformance`).
- **Status: missing for the write side.** New: after a full D1C apply against a synthetic repo, assert the
  materialized parent contract exactly matches `graph_delta.proposed_parent` (kind, execution_scope,
  decomposition_state, decomposition_children, decomposition_requirement_sha256, exclusive_resources==[])
  (Slice 2/3 test suite).

## Inbound rewrites

- **Status: exists for planning** (`_rewrite_dependent` covered in `graph_delta_smoke_test.py`).
- **Status: missing for materialization.** New: assert every rewritten dependent's file on disk after apply
  matches `proposed_graph_overlay.tasks` exactly, and every *non*-rewritten task file is byte-identical to
  before (proves the "changed files only" write scope from `D1C_GRAPH_APPLICATION_DESIGN.md`) (Slice 2 test
  suite).

## Resource locks

- **Status: exists for planning** (`_update_resource_groups` covered in `graph_delta_smoke_test.py`).
- **Status: missing for the claim-layer interaction.** New: assert D1C's orchestrator wrapper (Slice 6a)
  acquires the parent claim, every proposed child's `exclusive_resources`, and the global logical resource token
  (`logical:taskgraph-decomposition-apply-global`) before committing, and releases them after (or on abort)
  (Slice 6a test suite).

## Affected-contract authority (active-worker protection) — new, corrects an earlier gap

- **Status: missing entirely.** This capability does not exist in any form today; an earlier draft of this test
  plan incorrectly assumed the existing contract-hash staleness check was sufficient (see
  `CONCURRENCY_AND_FAILURE_MODEL.md` race #4, corrected). New deterministic tests (Slice 6b):
  - the decomposition parent's exact `agent_working` / `decomposition_apply` lease owned by the current D1C
    worker is accepted, while a parent lease owned by another worker or in another phase is rejected;
  - a dependent worker's `agent_working` lease acquisition wins the race BEFORE D1C attempts its
    affected-contract claim — assert D1C's durable-state check blocks and mutates nothing;
  - D1C's atomic multi-task claim wins FIRST — assert a subsequent implementation lease attempt on the same
    dependent loses the ordinary claim race, and correctly resumes/re-derives against the new contract once
    D1C's commit lands;
  - genuine simultaneous contention between a dependent worker's lease attempt and D1C's claim attempt resolves
    to exactly one winner, never both.

## `current_conformance` aggregate semantics

- **Status: exists, unchanged by Stage 5** (`aggregate_conformance_smoke_test.py`,
  `conformance_evaluator_smoke_test.py`). Stage 5 must add a regression test proving these pass **unmodified**
  against a D1C-materialized graph (not just a hand-authored fixture graph), to prove D1C's output is
  indistinguishable from a correctly hand-authored one (Slice 2/3 test suite).

## `needs_replan`

- **Status: exists for detection** (`current_conformance.py::_explicit_aggregate_conformance`, covered in
  `aggregate_conformance_smoke_test.py`).
- **Status: missing for the candidate-selection consequence.** New: assert the decomposition candidate-selection
  layer (Slice 5) treats a `needs_replan` aggregate as re-decomposable (per
  `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"`needs_replan` when parent requirements change").

## Dirty tree

- **Status: exists for D1B** (`capture_clean_source` cleanliness check, covered in
  `context_builder_smoke_test.py`).
- **Status: missing for D1C.** New: assert D1C refuses to run against a dirty checkout, reusing the identical
  check (Slice 1/3 test suite — should literally import and reuse `capture_clean_source`, so the test may be a
  thin wrapper proving reuse rather than reproving the check itself).

## Wrong origin

- **Status: exists for implementation checkout (Stage 4.1)**
  (`Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py`).
- **Status: missing for D1C's checkout.** New: extend or parametrize the existing origin-binding test to cover
  a decomposition-apply checkout (Slice 5 test suite, reusing the Stage 4.1 fixture pattern).

## Partial mutation recovery

- **Status: missing entirely.** New: crash-injection test (kill after N of M `os.replace` calls); assert (a)
  orphaned-child detection rejects the result on next load, (b) no auto-repair occurs, (c) the mutation-plan
  dry-run artifact from before the crash is still present for operator diagnosis (Slice 2 test suite; this is
  race #10 in `CONCURRENCY_AND_FAILURE_MODEL.md`).

## Issue read-after-write lag

- **Status: exists for the main Issue workflow path.** `Pipeline/TaskReviewAgent/issue_workflow_store.py`
  implements `_verify_post_mutation_state` /
  `POST_MUTATION_VERIFICATION_DELAYS_SECONDS = (0.0, 1.0, 2.0, 4.0, 8.0)` with the explicit rule "the mutation
  itself must NEVER be repeated merely because verification lagged; retry only the read side... then fail
  closed." Covered by `Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py` (lines ~328-428, which
  monkeypatch the delay tuple to `(0.0, 0.0, 0.0)` for fast deterministic testing). This corresponds to commit
  `109380b fix: tolerate GitHub read-after-write lag` visible in this repository's recent history.
- **CORRECTED — status is NOT "complete except for timing."** `goal_loop_guard.py::_release_active_lease` still
  performs a direct `backend.add_comment` → `backend.update_issue` → immediate `service.find(task_id)` → exact
  compare, bypassing the centralized verifier entirely. This is current, committed production code, not a
  hypothetical. This audit also found the same direct mutation-then-immediate-read shape in multiple transitions
  in `downstream_issue.py` and `downstream_runtime.py`. Production issue #104's class is open, not closed.
- **Status: missing for decomposition Issue paths, AND blocked on closing the production audit first.** New
  tests (Slice 4/5 test suite) must extend/reuse the `109380b` fixture for the new decomposition Issue writes
  (proposal creation, apply-authorization, closeout) — but per `GAUNTLET_PREREQUISITES.md` item 5, this is a
  hard prerequisite, not an optional tuning item: before any Stage 5 slice adds real decomposition Issue
  mutations, production must complete an audit of every direct Issue mutation/immediate-read path (at minimum
  `goal_loop_guard.py::_release_active_lease`, `downstream_issue.py`, `downstream_runtime.py`) and route them
  through the same central verifier Stage 5 will reuse.

## Claim contention

- **Status: exists for implementation task/resource claims** (`claim_refs_smoke_test.py`,
  `contention_retry_smoke_test.py`) — single-task `acquire()`/`release()` only.
- **Status: missing for decomposition-specific claims** (parent claim during proposal; global logical-resource
  claim during apply, Slice 6a; the NEW atomic multi-task claim over parent + affected dependents during apply,
  Slice 6b — this primitive does not exist yet and needs its own unit tests analogous to
  `claim_refs_smoke_test.py`, not just parametrization of the existing single-task fixtures). New: parametrize
  existing claim-conflict fixtures with decomposition claim refs, and add dedicated multi-task-claim unit tests
  (Slice 5/6 test suite).

## Global logical-resource D1C-vs-D1C race (race #2, Slice 6a)

- **Status: missing entirely.** New deterministic test (Slice 6a test suite, per
  `CONCURRENCY_AND_FAILURE_MODEL.md` race #2): two simulated concurrent D1C apply attempts (for two different
  parents, both planned against the same prior HEAD) both include
  `"logical:taskgraph-decomposition-apply-global"` in their `exclusive_resources` claim set and both attempt
  `acquire()` against a shared fake remote; assert **exactly one wins** the claim (no double grant), the loser
  receives an ordinary `ClaimConflict`, and the loser's retried apply attempt against the winner's post-commit
  HEAD is correctly rejected as `stale_proposal` rather than silently reallocated. This is distinct from the
  "ID collision"/"Sequential re-apply" tests above, which prove the *consequence* of losing the race; this test
  proves the claim-acquisition race itself resolves to one winner.

## Resume after crash

- **Status: partial for implementation.** `Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py` proves
  later-agent resume of an `agent_working` lease; `Pipeline/TaskReviewAgent/tests/durable_checkout_smoke_test.py`
  and `resumable_checkout.py` cover checkout resume. A single parametrized "crash at every named transition"
  test was not found as one unit in this pass — existing coverage is per-boundary (lease resume, checkout
  resume) rather than one exhaustive transition matrix; treat the matrix framing in this plan as the Stage 5
  addition, built on top of these existing per-boundary tests rather than replacing them.
- **Status: missing for decomposition** (all five new phases). New: parametrized crash-at-every-transition test
  per `CONCURRENCY_AND_FAILURE_MODEL.md` race #13 (Slice 5 test suite).

## Application idempotency

- **Status: missing entirely.** New: double-apply test asserting `already_applied` and zero additional
  filesystem/commit changes (Slice 3 test suite; race #15).

## One-worker live proof

- **Status: missing (by definition — nothing to prove live yet).** Planned as Slice 7. Not a deterministic
  test; a documented, evidenced live run.

## 2-3 worker contention proof

- **Status: missing (by definition).** Planned as Slice 8. Live, not deterministic; should regress-test any
  discovered defect back into the Slice 6 deterministic suite before being considered resolved.

## Larger concurrency proof

- **Status: missing, and explicitly out of near-term scope.** Not planned as part of Stage 5's initial slices;
  should only be considered after Slice 8 and after the underlying Gauntlet's own larger-scale (85-task)
  concurrency proof is accepted, since Stage 5 reuses that exact machinery (see `GAUNTLET_PREREQUISITES.md`).

## Summary table

| Area | Deterministic coverage today | Missing (Stage 5 must add) |
| --- | --- | --- |
| Contract/schema validation | Complete | None |
| Stale-source rejection (D1B) | Complete | D1C equivalent |
| Graph delta revalidation (plan-time) | Complete | D1C apply-time re-derivation |
| ID collision (single-plan) | Complete | Cross-application sequential allocation (fresh plan only, not shifted reapplication) |
| Sequential re-apply after another plan lands (#16) | None | Full new test — broadened, overlap not required |
| Affected-contract authority (active-worker protection, #4) | **None — new capability, not yet designed as of the prior draft** | Full new test (Slice 6b) |
| Parent→aggregate (read) | Complete | Write-side materialization |
| Inbound rewrites (plan) | Complete | Materialization + untouched-file proof |
| Resource locks (plan) | Complete | Claim-layer interaction (parent + children + global logical resource) |
| Aggregate conformance | Complete, unchanged | Regression against D1C output |
| `needs_replan` (detection) | Complete | Candidate-selection consequence |
| Dirty tree (D1B) | Complete | D1C reuse |
| Wrong origin (implementation) | Complete | D1C checkout |
| Partial mutation recovery | None | Full new test |
| Read-after-write lag | Exists for the main Issue workflow path; **NOT complete production-wide** (`goal_loop_guard.py`, `downstream_issue.py`, `downstream_runtime.py` bypass the central verifier) | Decomposition paths, gated on closing production #104 first |
| Claim contention | Complete (implementation, single-task) | Decomposition-specific refs; NEW multi-task claim primitive (Slice 6b) |
| Global logical-resource D1C-vs-D1C race (#2) | None | Full new test — exactly-one-winner claim race (Slice 6a) |
| Resume after crash | Partial (implementation) — confirm exact breadth | Decomposition, all phases |
| Application idempotency | None | Full new test |
| Live proofs (1-worker, 2-3 worker, larger) | None | Slices 7/8; larger scale deferred |
