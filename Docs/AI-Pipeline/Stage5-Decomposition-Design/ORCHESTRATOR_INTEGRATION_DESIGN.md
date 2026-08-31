# Orchestrator Integration Design — Decomposition as a Durable Work Unit

**RECOMMENDATION** document. Builds on facts in `CURRENT_STATE_AUDIT.md` and the D1C design in
`D1C_GRAPH_APPLICATION_DESIGN.md`.

## End-to-end flow

```text
generic request ("go pick a task and start on it")
        |
        v
resume existing actionable decomposition work first when appropriate
   (new: durable_selection-equivalent query that ALSO returns decomposition-phase Issues,
    not just implementation-phase Issues)
        |
        v
select eligible decomposition parent
   (new: Stage-2-equivalent planner branch; reuses context_builder.validate_task_selection
    as the safety kernel, exactly as evaluate_fresh_candidate is reused for implementation)
        |
        v
claim task/resources
   (reuse claim_refs.py unchanged: same task_claim_ref/resource_claim_ref primitives,
    same exclusive_resources from the PARENT contract)
        |
        v
durable Issue lease
   (reuse issue_workflow.py's WorkflowState machine; ADD WorkflowPhase values, do not
    replace the state machine)
        |
        v
isolated checkout/source snapshot
   (reuse durable_checkout.py/resumable_checkout.py primitives; decomposition needs
    read-only source + a disjoint output root, which is a NARROWING of the existing
    checkout contract, not a new one)
        |
        v
D1B.1 or D1B.2 proposal/review
   (UNCHANGED — existing Pipeline/TaskDecomposition/* code, invoked by the same worker
    process instead of by hand)
        |
        v
durable decomposition closeout/review boundary
   (new Issue phase: decomposition_review_ready or decomposition_needs_human)
        |
        v
explicit human/operator graph-application authorization
   (new: human_action_required / decomposition_apply_authorization phase --
    mirrors the existing human PASS/FAIL pattern in issue_workflow.py exactly)
        |
        v
D1C application
   (new module, per D1C_GRAPH_APPLICATION_DESIGN.md)
        |
        v
commit/push/integrate
   (reuse git_identity_guard.py; reuse downstream_pipeline.py's push/PR patterns
    where they already generalize)
        |
        v
TaskGraph recompute
   (reuse load_persistent_work_graph -- no new code)
        |
        v
parent aggregate state / child readiness
   (reuse current_conformance.py -- no new code, already correct per CURRENT_STATE_AUDIT.md)
        |
        v
Issue closeout
   (new: decomposition Issue -> complete, plus per-child Issues created/left for
    normal implementation dispatch to discover)
        |
        v
generic workers may pick newly unlocked children
   (reuse dispatch_plan.py UNCHANGED -- children are ordinary kind=implementation,
    execution_scope=single_agent contracts the instant they are committed)
```

**Key design principle:** almost nothing about *implementation* dispatch needs to change. Newly created
children are ordinary schema-2.0 `kind: implementation` contracts; `evaluate_fresh_candidate` will pick them up
automatically once committed to `main`, with zero decomposition-awareness required in `dispatch_plan.py`.

## Issue phase/state values needed

**RECOMMENDATION.** Reuse the existing five `WorkflowState` values (`agent_ready`, `agent_working`,
`human_action_required`, `blocked`, `complete`) unchanged — they already express the right *ownership*
semantics (agent turn vs. human turn vs. terminal). Add new `WorkflowPhase` values, since phase already exists
precisely to say "what kind of work should happen during this agent/human turn":

```text
existing: implementation, repair, unity_runtime_validation, delivery_evidence, merge_closeout
new:      decomposition_proposal          (agent_working: run D1B.1/D1B.2)
          decomposition_review            (human_action_required or agent_working, depending on
                                            D1B.2 outcome -- needs_human vs review_ready)
          decomposition_apply_authorization (human_action_required: human authorizes D1C)
          decomposition_apply             (agent_working: run D1C, commit, push)
          decomposition_closeout          (agent_working -> complete)
```

**Why extend rather than replace:** `issue_workflow.py`'s state/event/hash-chain machinery
(`STATE_MARKER`, `EVENT_MARKER`, append-only chain verification) is state-machine-shape-agnostic — it does not
hardcode the five existing phase strings anywhere in its verification logic (verified by reading
`issue_workflow.py:1-90`; `WorkflowPhase` is a plain string enum consumed by comparison, not by chain
verification). Adding enum members is additive and backward compatible; every existing implementation Issue
continues to validate exactly as before.

## `work_type: decomposition` stays explicit

**RECOMMENDATION.** Add a `work_type` field to the managed state block (`nsc-workflow-state` JSON), with
values `"implementation"` or `"decomposition"`, set once at Issue initialization and immutable thereafter. This
turns the current prose convention (AGENTS.md line 25, `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md` §6)
into a machine-checkable field so `dispatch_plan.py`/`issue_workflow.py` can distinguish "this Issue's
`agent_working` lease is for decomposing NSC-021" from "this Issue's `agent_working` lease is for implementing
NSC-021" — which matters because, per ADR-034/current_conformance.py, a task ID can only ever be *one* of
implementation or decomposition target, but the *type of work currently happening against its Issue* still
needs to be unambiguous to a resuming worker.

## Preventing duplicate decomposition runs on the same parent/hash

**RECOMMENDATION.** This is exactly the claim-ref mechanism already built for implementation, applied to the
parent's task ID:

- Acquiring a `decomposition_proposal` lease claims `task_claim_ref(namespace, parent_id)` exactly as
  implementation does — `claim_refs.py` has no notion of "implementation task" vs. "decomposition target"; it
  claims a task ID. This is a **direct, zero-new-code reuse**.
  the same task ID *cannot* be claimed for parallel proposal work while it's already agent_working for
  implementation, and vice versa — which is correct, because `context_builder.validate_task_selection` already
  refuses to decompose an already-`concrete`/`single_agent` task, and `evaluate_fresh_candidate` already refuses
  to dispatch implementation against a task whose `decomposition_state` isn't `concrete`.
- The **hash** part ("same parent/hash") is handled by D1C's stale-proposal rejection
  (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Source HEAD/tree/task-contract identity binding"), not by the claim
  layer — the claim layer prevents concurrent *proposal* runs; the hash check prevents applying a *stale*
  proposal after the parent changed, which can legitimately happen sequentially (propose → time passes → parent
  edited by an unrelated change → apply attempted).

## Resuming interrupted proposal/review/application work

**RECOMMENDATION.** Extend `durable_selection.py::select_agent_ready_issue` (or add a sibling function) to
also return decomposition-phase `agent_ready` Issues, not just implementation-phase ones. The existing contract
hash check (*"Issue contract hash differs from current committed contract"* → stale, excluded) applies
unchanged: if the parent contract changed since the decomposition Issue was last touched, resume must fail
closed exactly as it does today for implementation, forcing a fresh eligibility check
(`context_builder.validate_task_selection`) rather than blindly resuming a stale proposal round.

For `decomposition_apply` specifically: because D1C's own idempotency check
(`D1C_GRAPH_APPLICATION_DESIGN.md` §"Idempotency/replay behavior") already makes re-running D1C against an
already-applied plan a safe no-op, resuming an interrupted `decomposition_apply` phase is simply "run D1C
again" — no special partial-apply resume logic is needed in the orchestrator layer itself, only in D1C.

## How Stage-1 claims interact with parent and proposed children

**RECOMMENDATION.**

- **Proposal phase (D1B.1/D1B.2):** claim only the parent task ref + the parent's *current*
  `exclusive_resources`. Proposed children do not exist yet and own no resources yet — nothing to claim for
  them.
- **Apply phase (D1C):** claim the parent task ref again (it may have been released after proposal completed;
  re-claim rather than assume continuity) **plus every resource named in every proposed child's
  `exclusive_resources`** from the `graph_delta.json` about to be applied. This is the mechanism that prevents
  the race in `CONCURRENCY_AND_FAILURE_MODEL.md` where an implementation worker starts claiming a
  soon-to-exist child's resource concurrently with D1C creating that child — impossible in practice today since
  the child doesn't exist to be claimed, but becomes possible the instant D1C's commit lands and a fast
  worker's stale claim-namespace enumeration could theoretically overlap a same-tick apply. Claiming the
  child's resource *before* committing closes this window (a resource claim ref does not require the resource's
  owning task to exist yet — `claim_refs.py::resource_claim_ref` hashes an arbitrary resource string, not a task
  ID).
- Release all of these claims only after the D1C commit is verified pushed (or after a clean rollback if D1C
  aborts before mutating).

## What resources must be locked during application

Exactly: the parent's exclusive resources (about to be cleared) + the union of every proposed child's
exclusive resources (about to be created) + the parent task ref itself. Not every dependent's resources — inbound
dependency rewrites change `depends_on`, not `exclusive_resources`, so no dependent resource claim is required.

## Serialization of graph mutation vs. parallel implementation workers

**RECOMMENDATION — this is the single most important new invariant Stage 5 adds.** D1C application must be
**serialized globally**, not just per-parent, with respect to any *other* D1C application, because two
concurrent applications both recompute `next_number = max(existing) + 1` against a `main` that neither has
observed the other's commit on yet (see `D1C_GRAPH_APPLICATION_DESIGN.md` §"ID allocation"). The existing claim
mechanism gives per-task/per-resource exclusion, not a global serialization point. Two options:

1. **(Preferred, minimal new mechanism.)** Add one more claim ref,
   `refs/nsc/claims/decomposition-apply-global`, that every D1C application must acquire (in addition to its
   parent/resource claims) before it may commit, and release immediately after push succeeds or the attempt
   aborts. This reuses `claim_refs.py`'s exact atomic nonexistence-CAS primitive with zero new code beyond
   naming one more ref. A losing worker gets an ordinary `ClaimConflict` and retries later — consistent with
   "race losers recompute."
2. Rejected alternative: rely on push-time non-fast-forward rejection alone. This works for *detecting* the
   race but wastes an entire D1B.2 authorization cycle's worth of work on the loser and does not prevent the ID
   `NSC-{N}` from being *proposed* twice to two different humans for authorization simultaneously, which is
   confusing operationally even though D1C's stale-check would eventually reject the second one. The global
   claim prevents wasted human authorization cycles, not just wasted compute.

This does **not** need to serialize with *implementation* claims — an implementation worker claiming
`NSC-044`'s resources is unaffected by a concurrent decomposition-apply global claim for `NSC-021`, since they
touch disjoint task/resource claim refs. Only D1C-vs-D1C needs the extra global point.

## Preventing an implementation worker from starting from stale TaskGraph authority

**FACT, already solved, zero new code needed.** `dispatch_plan.py`'s docstring states Stage 2 "never mutates
anything" and Stage 3 (`fresh_dispatch.py`) always calls `observe_goal_state()` fresh — *"re-derives eligibility
from CURRENT committed/Issue state — never trusts the stale plan snapshot."* An implementation worker that
happened to plan against pre-D1C-commit `main` and then loses the race to actually acquire its lease (because
D1C's commit landed first and, e.g., changed that task's `depends_on`) will simply have its `acquire_agent_lease`
call re-derive against the new HEAD, which is already the existing, tested behavior for any concurrent `main`
change — decomposition is not a special case here.

## Interaction with current generic dispatch contention retry

**RECOMMENDATION.** `fresh_dispatch.py::resolve_generic_dispatch_with_contention_retry` already loops on
ordinary `claim_conflict`, excluding the lost candidate and rebuilding the plan from scratch. Extending the
candidate pool to include decomposition parents means this exact retry loop starts working for decomposition
"for free" — a decomposition claim conflict is reported and excluded exactly like an implementation one, with
no new retry logic required. The one addition needed is in the **candidate-ranking** step (Stage 2 `plan_dispatch`
equivalent), which today only ranks `fresh_implementation_derived_states` (`not_delivered`). It must gain a
second candidate-generation path for decomposition parents, feeding into the *same* `excluded_task_ids`
mechanism.

## Human review/approval boundary

**RECOMMENDATION.** Model exactly on the existing `human_action_required` / `unity_runtime_validation` →
PASS/FAIL pattern (`issue_workflow.py::parse_human_validation_result`,
`.github/workflows/nsc-issue-workflow.yml`). A `decomposition_apply_authorization` phase posts: parent ID,
proposed child summary, `plan_id`, D1C dry-run mutation-plan artifact link/hash. The human posts:

```text
## Decomposition application result

Result: APPROVE | REJECT
Reviewed plan_id: <exact plan_id>
```

Exact `plan_id` binding (not just PASS/FAIL) is required because, unlike Unity validation which is bound to one
commit, a decomposition proposal could theoretically be superseded by a newer round between posting and
approval — the same exact-commit-binding discipline `HUMAN_RESULT_RE` already enforces for implementation
(`Tested commit: <sha>`) applies here as `Reviewed plan_id: <plan_id>`.

## Decomposition `needs_human`

**FACT, already correctly scoped by D1B.2.** A `needs_human` result from the review circuit is a **different**
human touchpoint than apply-authorization — it means the *proposal itself* could not be resolved to
`review_ready` within the circuit breaker. **RECOMMENDATION:** route this to its own
`decomposition_review` / `human_action_required` phase distinct from `decomposition_apply_authorization`,
since the required human action is different (resolve a design ambiguity vs. authorize a structurally valid
mutation).

## Failure/circuit-breaker behavior

**RECOMMENDATION.** Reuse existing patterns without inventing a new circuit breaker:

- D1B.2's own circuit breaker (max calls) is unchanged and already bounded.
- D1C's stale-proposal/collision failures are terminal for that attempt (no retry loop inside D1C itself — an
  operator or a fresh generic-dispatch cycle decides whether to re-propose).
- `goal_loop_guard.py`'s existing no-progress circuit-breaker concept (referenced in
  `Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md` — *"A blocked/no-progress action must trip a
  circuit breaker rather than consume dozens of supervisor turns"*) should apply identically to a decomposition
  Issue stuck retrying the same D1C claim conflict.

## Downstream conformance behavior for aggregate parent

**FACT, already implemented, zero new code.** `current_conformance.py::_explicit_aggregate_conformance`
already derives `conformant`/`aggregate`/`needs_replan` from `decomposition_children` +
`decomposition_requirement_sha256`. Stage 5 orchestration integration does not touch this file.

## `needs_replan` when parent requirements change

**FACT, already implemented.** If a human edits the *already-decomposed* parent's AC/VAL/INT after
application (which is possible — the aggregate contract still exists, just non-executable),
`aggregate_requirement_sha256` will no longer match `decomposition_requirement_sha256`, and
`current_conformance.py` already reports `needs_replan`. **RECOMMENDATION:** the orchestrator's decomposition
candidate-selection step (feeding `evaluate_fresh_candidate`-equivalent logic) should treat a `needs_replan`
aggregate as a **new, distinct decomposition-relevant candidate** — i.e., re-running D1B.1/D1B.2 against an
already-decomposed-but-now-stale parent is a legitimate future decomposition work unit, not an error. This is a
policy addition to the *candidate selection* layer, not to D1A/D1C, which already handle it correctly by
construction (any such re-proposal simply produces a new `plan_id` with a fresh child set/rewrite plan).

## No speculative whole-backlog decomposition

**RECOMMENDATION, reinforcing ADR-021.** The candidate-ranking addition described above must not become "queue
every `needs_execution_decomposition` task automatically." It should apply the same selection preference logic
already documented in `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md` §"Selection
preference" (prefer fresh implementation when comparable; prefer decomposition only when it unlocks blocked
work or no fresh candidate exists) — this is a ranking-weight decision, not a new architectural mechanism, and
should not be implemented as an unconditional queue-everything policy.
