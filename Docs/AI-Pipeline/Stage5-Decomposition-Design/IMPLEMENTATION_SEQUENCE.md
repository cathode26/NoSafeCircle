# Implementation Sequence — Bounded PR Slices for Stage 5 / D1C

**RECOMMENDATION** document. All slices assume `AGENTS.md`, `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`,
and normal human-merge authority continue to apply unchanged. No slice enables autonomous/background dispatch.

## Slice 1 — Deterministic D1C planner/preflight

- **Files to change:** new `Pipeline/TaskGraph/graph_apply_plan.py` (pure function:
  source identity binding + recompute-and-compare against stored `GraphDeltaPlan`, per
  `D1C_GRAPH_APPLICATION_DESIGN.md` §"Source HEAD/tree/task-contract identity binding" and §"Deterministic
  revalidation").
- **Files that must NOT change:** `Pipeline/TaskGraph/graph_delta.py`,
  `Pipeline/TaskGraph/decomposition_graph_semantics.py`, `Pipeline/TaskDecomposition/**` (D1A/D1B are proven;
  this slice only consumes their outputs).
- **Tests:** new `Pipeline/TaskGraph/graph_apply_plan_smoke_test.py` — fresh match, stale parent hash, stale
  graph hash, tampered stored-delta-vs-recomputed mismatch.
- **Acceptance criteria:** pure function, no filesystem writes, no Git mutation; returns a typed
  `fresh | stale_proposal | recompute_mismatch` result.
- **Rollback/recovery:** trivial — delete the new module; nothing else depends on it yet.
- **Dependency on prior slice:** none (first slice).
- **Can happen before Gauntlet completes?** **Yes.** Purely deterministic, no concurrency primitive involved.

## Slice 2 — Local transactional materialization

- **Files to change:** new `Pipeline/TaskGraph/graph_apply_materialize.py` implementing the
  stage → validate-staged → ordered `os.replace` sequence from
  `D1C_GRAPH_APPLICATION_DESIGN.md` §"Task-file and graph index/metadata writes," reusing
  `work_graph_persist.py`'s `canonical_json_text`/`sha256_bytes`/`write_text` primitives by import, not
  copy-paste.
- Also in this slice: the orphaned-child detection addition to
  `Pipeline/TaskGraph/decomposition_graph_semantics.py` described in the D1C design's §"What happens if
  filesystem write succeeds partially" (this is the one required change to existing D1A code, and it is
  additive — a new rejection case, not a change to any existing accepted case).
- **Files that must NOT change:** `Pipeline/TaskGraph/work_graph_persist.py` itself (bootstrap path stays
  bootstrap-only; do not generalize it in place — import its primitives instead), `Tasks/*.yaml` (no live data
  touched by tests; use temp directories).
- **Tests:** new `Pipeline/TaskGraph/graph_apply_materialize_smoke_test.py` — full apply against a synthetic
  repo fixture (mirroring the fixture style already used in `work_graph_persist_smoke_test.py`); partial-write
  crash injection (kill after N of M `os.replace` calls) proving the orphaned-child check now rejects the
  result; full round-trip (`load_persistent_work_graph` succeeds after a clean apply).
- **Acceptance criteria:** clean apply produces a graph `load_persistent_work_graph` accepts; injected partial
  apply produces a graph `load_persistent_work_graph`/`validate_decomposition_graph_semantics` rejects with a
  specific, diagnosable error naming the orphaned child and its plan ID.
- **Rollback/recovery:** delete the new module; the additive semantics check in
  `decomposition_graph_semantics.py` can be reverted independently since it is a strict superset of prior
  accepted inputs for every case that isn't a half-applied D1C run (verify with the full existing
  `decomposition_graph_semantics_smoke_test.py` suite passing unchanged).
- **Dependency on prior slice:** Slice 1 (consumes its `fresh` result before materializing).
- **Can happen before Gauntlet completes?** **Yes.** Still fully deterministic, synthetic-repo-only.

## Slice 3 — D1C application tests (end-to-end, still deterministic)

- **Files to change:** new `Pipeline/TaskGraph/graph_apply_smoke_test.py` (or equivalent) exercising Slice 1 +
  Slice 2 together as one `apply_graph_delta(...)` entry point, including the idempotency check
  (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Idempotency/replay behavior") and the local commit/rollback boundary
  (`git commit` against a real disposable temp Git repo — no network, no GitHub).
- Introduce the public entry point itself here: new `Pipeline/TaskGraph/apply_graph_delta.py` wiring Slices 1-2
  plus the local Git commit step (§"Git commit boundary," §"Post-commit TaskGraph validation" — local-repo
  reset-on-failure only, no push yet).
- **Files that must NOT change:** anything under `Pipeline/TaskReviewAgent/` (no orchestrator wiring yet — this
  slice proves D1C works as a standalone deterministic tool an operator could invoke by hand, matching how
  D1B.1/D1B.2 were originally proven before any orchestrator integration existed).
- **Tests:** double-apply idempotency; ID-collision-avoidance-by-recomputation (two plans applied sequentially
  against the same synthetic repo, second correctly shifts allocation); post-commit validation failure triggers
  local rollback and leaves the disposable repo's branch pointer unchanged.
- **Acceptance criteria:** `apply_graph_delta()` is a fully tested, network-free, GitHub-free deterministic tool.
  Exit codes/typed results distinguish `applied`, `already_applied`, `stale_proposal`, `post_commit_validation_
  failed`.
- **Rollback/recovery:** delete the module; nothing downstream depends on it yet.
- **Dependency on prior slice:** Slices 1-2.
- **Can happen before Gauntlet completes?** **Yes.** Still no network/GitHub/concurrency primitive.

## Slice 4 — Durable Issue phase additions

- **Files to change:** `Pipeline/TaskReviewAgent/issue_workflow.py` (add `WorkflowPhase` members per
  `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Issue phase/state values needed"; add `work_type` to the managed state
  block schema, defaulting existing implementation Issues to `"implementation"` for backward compatibility).
- **Files that must NOT change:** the existing five `WorkflowPhase` values' semantics; the hash-chain
  verification algorithm itself (`STATE_RE`/`EVENT_RE` parsing, sequence/prior-event validation) — this slice is
  additive vocabulary only.
- **Tests:** extend `Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py` with decomposition-phase
  fixtures; a regression test asserting every existing implementation-Issue fixture still validates identically
  (proves backward compatibility).
- **Acceptance criteria:** old Issues (no `work_type` field) still parse and validate; new Issues can express
  `work_type: decomposition` and the five new phases; hash-chain verification is unchanged for both.
- **Rollback/recovery:** revert the enum/schema addition; no live Issues would yet carry the new phases (nothing
  downstream produces them until Slice 5+).
- **Dependency on prior slice:** none technically (Slice 4 could be built independently of 1-3), but it is
  sequenced after them so review can focus on one authority boundary at a time.
- **Can happen before Gauntlet completes?** **WAIT.** This slice changes the durable-Issue schema that the
  Gauntlet is specifically proving under real concurrent load. Landing a schema change mid-Gauntlet risks
  invalidating in-flight Gauntlet evidence or requiring re-runs. Land after Gauntlet acceptance.

## Slice 5 — Generic dispatcher/resume integration

- **Files to change:** `Pipeline/TaskReviewAgent/dispatch_plan.py` (new decomposition-candidate branch feeding
  the same `excluded_task_ids`/ranking mechanism), `durable_selection.py` /
  `generic_selection.py` (return decomposition-phase `agent_ready` Issues too), new
  `Pipeline/TaskReviewAgent/decomposition_dispatch.py` bridging Stage 2/3 to
  `Pipeline/TaskDecomposition/*` and the new `apply_graph_delta` entry point from Slice 3.
- **Files that must NOT change:** `evaluate_fresh_candidate` itself (implementation eligibility kernel stays
  exactly as-is; decomposition gets its own parallel kernel reusing
  `context_builder.validate_task_selection`, per design).
- **Tests:** new `Pipeline/TaskReviewAgent/tests/decomposition_dispatch_smoke_test.py` covering candidate
  selection, claim acquisition/conflict, resume-after-crash at each phase transition (race 13 in
  `CONCURRENCY_AND_FAILURE_MODEL.md`).
- **Acceptance criteria:** a synthetic multi-fixture test proves a decomposition Issue can be created, claimed,
  resumed after simulated crash at every phase, and closed out — all without a real GitHub/network call
  (fake `IssueBackend`, matching the existing test style for implementation).
- **Rollback/recovery:** revert; Slice 4's schema additions remain unused but harmless.
- **Dependency on prior slice:** Slices 1-4.
- **Can happen before Gauntlet completes?** **WAIT.** Directly extends the exact dispatch/claim machinery the
  Gauntlet is proving.

## Slice 6 — Concurrency serialization (global apply claim)

- **Files to change:** `Pipeline/TaskReviewAgent/claim_refs.py` (add the
  `refs/nsc/claims/decomposition-apply-global` ref as a named constant/helper — not a new mechanism, per
  `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Serialization of graph mutation"), wire acquisition/release into
  `apply_graph_delta`'s orchestrator-facing wrapper from Slice 5.
- **Files that must NOT change:** the core atomic-CAS push/release logic in `claim_refs.py` (`acquire`,
  `release`, `_fenced_atomic_delete`) — reused verbatim, not modified.
- **Tests:** new deterministic race test per `CONCURRENCY_AND_FAILURE_MODEL.md` race #2 (two simulated
  concurrent D1C applications against a shared fake remote; assert exactly one wins, the loser's retry after the
  winner's commit correctly reallocates IDs).
- **Acceptance criteria:** race #2's proving test passes; races #10 and #15 proving tests (partial write,
  double apply) also pass end-to-end through the orchestrator wrapper, not just the standalone Slice 3 tool.
- **Rollback/recovery:** revert; Slice 5's dispatcher would then be vulnerable to race #2 again — this slice is
  a hard prerequisite before any live multi-worker decomposition use, called out explicitly.
- **Dependency on prior slice:** Slice 5.
- **Can happen before Gauntlet completes?** **WAIT.** Depends on the claim-ref activation/policy machinery
  (`claim_policy.py`) the Gauntlet also exercises under real load.

## Slice 7 — Live single-decomposition proof

- **Scope:** one human-authorized, single-worker, real GitHub/real-repository run: propose (D1B.2) → human
  authorizes → apply (D1C) → commit/push → verify `current_conformance.py` reports the parent as `aggregate`
  and children as `not_delivered`/dispatchable.
- **Files to change:** none (proof run only); may produce a small `evidence/` artifact under
  `Pipeline/TaskReviewAgent/evidence/` or `Pipeline/TaskGraph/evidence/`, following the existing evidence
  convention (`current_conformance.py`'s `artifact_prefix` pattern).
- **Tests:** the proof *is* the test; no new automated test required beyond what Slices 1-6 already added,
  though a regression test capturing the specific real parent's before/after graph shape as a fixture is
  encouraged.
- **Acceptance criteria:** the applied graph passes `taskcontrol validate`/`states`; the human sign-off from
  `decomposition_apply_authorization` is traceable in the Issue event chain; no destructive action against
  `main` was needed to recover from anything.
- **Rollback/recovery:** if the live proof fails, the failure must be diagnosable from Issue events + Git
  history alone (dogfooding the recovery story from `CONCURRENCY_AND_FAILURE_MODEL.md`) — treat any case where
  it isn't as a Stage 5 defect, not an operator error.
- **Dependency on prior slice:** Slices 1-6, **and** Gauntlet acceptance.
- **Can happen before Gauntlet completes?** **WAIT.**

## Slice 8 — Multi-worker proof

- **Scope:** 2-3 simultaneous workers, at least one decomposition-apply race deliberately provoked (e.g., two
  operators authorize two overlapping proposals close together) to exercise race #2/#16 live, not just in
  deterministic tests.
- **Files to change:** none expected; any defect found here should produce a new deterministic regression test
  added to Slice 6's suite before the fix is considered complete (mirroring how the Gauntlet itself is expected
  to surface and regress-test implementation-side defects).
- **Tests:** the live races themselves; deterministic regression tests for anything discovered.
- **Acceptance criteria:** every race in `CONCURRENCY_AND_FAILURE_MODEL.md` marked "new mechanism required"
  (#2, #10, #15) is observed to fail closed correctly at least once under real concurrent load, not just in a
  synthetic fixture.
- **Rollback/recovery:** same discipline as Slice 7.
- **Dependency on prior slice:** Slice 7.
- **Can happen before Gauntlet completes?** **WAIT.**

## Slice 9 — Autonomous/background enablement consideration

- **Scope:** explicitly **not a Stage 5 implementation slice.** Recorded here only to state that it is out of
  scope: `AI_PIPELINE.md`, `dispatch_policy.json` (`"autonomous_dispatch": false`), and this audit all agree
  autonomous/background dispatch requires separate, later, explicit authorization and is not unlocked merely by
  Stage 5/D1C landing.
- **Can happen before Gauntlet completes?** **DO NOT DO**, and not planned as part of Stage 5 at all.

## Cross-cutting note on test-first ordering

Slices 1-3 are deliberately ordered so that D1C exists as a fully proven, standalone, deterministic tool
*before* any orchestrator wiring touches it — mirroring exactly how D1A and D1B.1/D1B.2 were each proven
standalone before being composed. This lets Slices 1-3 proceed in parallel with (not blocked by) the live
Gauntlet, since they touch none of the machinery the Gauntlet is validating.
