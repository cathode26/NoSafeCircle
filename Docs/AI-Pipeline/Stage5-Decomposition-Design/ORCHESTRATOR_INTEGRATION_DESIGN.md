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
  claims a task ID. This proposal-phase claim (one task ID, via the existing `acquire()`) is a **direct,
  zero-new-code reuse**; the apply-phase claim set is not — see §"Protecting existing task contracts D1C
  rewrites" and §"Serialization of graph mutation" below for the parts of Stage 5's claim usage that ARE new
  code.
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
  `exclusive_resources`, using the existing single-task `acquire()` unchanged. Proposed children do not exist
  yet and own no resources yet — nothing to claim for them.
- **Apply phase (D1C):** claim, in ONE atomic acquisition:
  - the parent task ref (re-claim; it may have been released after proposal completed — do not assume
    continuity);
  - the task ref of every existing dependent whose contract the `GraphDeltaPlan` rewrites (see
    §"Protecting existing task contracts D1C rewrites" below — **new**, not covered by proposal-phase claiming);
  - every resource named in every proposed child's `exclusive_resources` from the `graph_delta.json` about to be
    applied (closes the same-tick-apply race described below);
  - the global logical serialization resource, `logical:taskgraph-decomposition-apply-global`
    (§"Serialization of graph mutation").

  Claiming the child's resource *before* committing closes the window where an implementation worker's stale
  claim-namespace enumeration could theoretically overlap a same-tick apply (a resource claim ref does not
  require the resource's owning task to exist yet — `claim_refs.py::resource_claim_ref` hashes an arbitrary
  resource string, not a task ID).
- Release all of these claims only after the D1C commit is verified pushed (or after a clean rollback if D1C
  aborts before mutating). **Unlike an ordinary implementation lease handoff**, D1C holds this claim set for the
  full apply attempt rather than releasing immediately after acquisition — see §"Protecting existing task
  contracts D1C rewrites" for why the holding duration matters.

**CORRECTION.** Claiming multiple task refs (parent + every affected dependent) in one atomic acquisition is
**not** something `GitRefClaimClient.acquire()` supports today — it accepts exactly one `task_id`. This is real
new Stage 5 claim-layer work (see §"Protecting existing task contracts D1C rewrites" and
`IMPLEMENTATION_SEQUENCE.md` Slice 6), not a zero-new-code reuse.

## What resources/tasks must be locked during application

Exactly: the parent task ref + the task ref of every existing dependent whose contract will be rewritten + the
parent's exclusive resources (about to be cleared) + the union of every proposed child's exclusive resources
(about to be created) + the global logical serialization resource. **Correction to an earlier draft of this
document:** a rewritten dependent's `exclusive_resources` value is unchanged by `_rewrite_dependent` (only
`depends_on`/`contract_revision` change), so no *resource* claim is required for a dependent — but its **task
claim ref** is required, because D1C is about to mutate that dependent's contract, and contract-mutation
authority is exactly what a task claim ref represents.

## Protecting existing task contracts D1C rewrites

**RECOMMENDATION — required, corrects an earlier gap.** `graph_delta.py::_rewrite_dependent` changes a
dependent's `depends_on` and increments its `contract_revision`. Durable stale-contract-hash selection
(`durable_selection.py`) already protects a *later* resume/fresh-selection attempt against an outdated contract
— but it does **not** revoke or pause a worker that is **already** `agent_working` on that dependent under the
old contract, because that worker acquired its durable Issue lease before D1C's mutation, and
`acquire_issue_lease_with_claims` releases the ephemeral task claim ref immediately after the durable lease is
verified (`claim_refs.py::acquire_issue_lease_with_claims` — the claim is a brief startup-window guard, not
persistent authority for the lease's whole lifetime). A D1C application must not mutate a task contract
underneath an active implementation worker.

**Affected-contract authority set.** For one `GraphDeltaPlan`:

```text
affected existing task IDs =
    decomposition parent
    + every existing dependent named in inbound_dependency_changes
    + any other existing task contract the exact GraphDeltaPlan changes
```

D1C must prove safe authority over EVERY ID in this set before mutating any of them.

**Design (minimal extension, direction A from the review — extend the claim contract).** Because
`GitRefClaimClient.acquire()` claims exactly one task ref plus resources, and current implementation dispatch
does not claim any logical serialization token, neither the existing single-task claim nor the logical resource
token from §"Serialization of graph mutation" alone protects a rewritten dependent's contract — an
implementation worker never claims `logical:taskgraph-decomposition-apply-global`, so that token cannot fence a
dependent-contract mutation on its own. The required extension:

1. **Extend the claim acquisition contract to atomically claim multiple task refs plus all relevant resources in
   one Git atomic push.** This reuses the exact same nonexistence-CAS mechanism (`--atomic
   --force-with-lease=<ref>:` per ref) `acquire()`/`release()` already use, generalized from one `task_id` to a
   `Sequence[str]` of task IDs. It requires: a new method (e.g. `acquire_multi`) or a widened `acquire()`
   signature; a widened `ClaimReceipt` schema (`task_id: str` → `task_ids: tuple[str, ...]`, or an additional
   receipt field) so `inspect_claims`/stale-claim repair can still parse a multi-task claim; `release()`
   generalized the same way. This is the minimal shape that reuses the proven CAS primitive without inventing a
   second locking mechanism. **This is new code** — it does not exist in `claim_refs.py` today.
2. Because the multi-task claim uses the identical `task_claim_ref(namespace, task_id)` ref an ordinary
   implementation worker's `acquire_issue_lease_with_claims` call would claim for that same task ID, a NEW
   implementation-lease acquisition attempt on an affected dependent started *after* D1C begins holding its
   multi-task claim correctly loses the race (`ClaimConflict`) — this closes the "I checked no lease exists,
   then a new worker acquired one" window, PROVIDED D1C acquires and holds the claim for the entire span from
   its durable-state check through the mutation (see below), not just momentarily.
3. **Before acquiring the multi-task claim, and again immediately before mutating** (re-verify — do not trust a
   check performed before the claim was held), D1C must read current durable Issue state
   (`IssueWorkflowService.find`) for every affected existing task ID and confirm none of them is currently
   `agent_working` for any worker, nor `human_action_required` in a phase where contract mutation would be
   unsafe. If any affected task is unsafe to mutate, D1C must **block** — report a typed, retryable outcome —
   and must not mutate any file for this `GraphDeltaPlan` (all-or-nothing across the whole affected set, not a
   partial apply that mutates only the currently-safe subset).
4. This two-part design (atomic multi-task claim + durable-state check, both re-verified immediately before
   mutation) handles both races Finding 3 identifies: (a) a dependent worker already `agent_working` before D1C
   attempts anything — durable-state check blocks D1C; (b) the race between "D1C checked no lease exists" and a
   new worker acquiring one in the gap — closed by D1C holding the atomic multi-task claim across that entire
   gap, so the new worker's own claim attempt on the same task ref loses.
5. Claim release follows the exact same no-TTL, exact-SHA-fenced policy as every other claim in this design; no
   TTL stealing, no automatic cleanup, manual exact-SHA repair only for a claim orphaned by a D1C crash.

**Concurrency preserved for unrelated work.** This does not serialize D1C against implementation work in
general — only against workers targeting one of the SAME affected task IDs. An implementation worker on
`NSC-044` is unaffected by a D1C application whose affected-contract set is `{NSC-021, NSC-030, NSC-031}`.

**Required tests** (see `TEST_PLAN.md` and `CONCURRENCY_AND_FAILURE_MODEL.md` race #4, revised): a dependent
worker's lease acquisition winning the race before D1C attempts its claim (D1C blocks); D1C's multi-task claim
winning first (a subsequent implementation lease attempt on the same dependent loses the race and retries after
D1C's commit lands, observing the new contract); and genuine simultaneous contention resolving to exactly one
winner with no double-grant.

## Serialization of graph mutation vs. parallel implementation workers

**RECOMMENDATION — this is one of the two most important new invariants Stage 5 adds** (the other is
§"Protecting existing task contracts D1C rewrites" above). D1C application must be **serialized globally**, not
just per-parent, with respect to any *other* D1C application, because two concurrent applications both recompute
`next_number = max(existing) + 1` against a `main` that neither has observed the other's commit on yet (see
`D1C_GRAPH_APPLICATION_DESIGN.md` §"Deterministic child ID allocation and collision handling").

**CORRECTION.** `GitRefClaimClient.acquire()` (`claim_refs.py`) constructs exactly one task claim ref from one
`task_id`, plus zero or more resource claim refs derived from canonical resource strings — it does not expose an
arbitrary literal ref such as `refs/nsc/claims/decomposition-apply-global`, and adding one would be a new
primitive shape the client does not support today. The preferred design instead represents the global
serialization point as **one canonical logical exclusive-resource token**:

```text
logical:taskgraph-decomposition-apply-global
```

This is an ordinary string passed through the existing `resource_claim_ref(namespace, resource)` hashing path
(`claim_refs.py::canonical_resource_hash` — any non-empty string under the length bound is already accepted;
nothing distinguishes a "real" Unity-asset resource token from a logical one). Concretely:

1. **(Preferred — reuses the existing primitive, does not require a new claim client method.)** Every D1C apply
   attempt includes `"logical:taskgraph-decomposition-apply-global"` in the SAME `exclusive_resources` set
   passed to `acquire()` alongside its other resources (parent + affected children + affected dependents — see
   above), in one atomic claim set, one atomic push. Two concurrent D1C applications both name this same logical
   resource, so their acquisitions collide on the resulting shared `resource_claim_ref` exactly as two ordinary
   tasks sharing a real exclusive resource would — this is the existing conflict semantics, not new conflict
   logic. A losing worker gets an ordinary `ClaimConflict` and retries later — consistent with "race losers
   recompute" — with the correction from `D1C_GRAPH_APPLICATION_DESIGN.md` that "recompute" almost always means
   **fresh D1B against the new HEAD**, not a silent reallocation of the same reviewed plan (see §"Human
   review/approval boundary" below and `CONCURRENCY_AND_FAILURE_MODEL.md` race #2). This claim is held for the
   full apply attempt, not released immediately after acquisition the way an ordinary implementation
   lease-handoff claim is — see §"Protecting existing task contracts D1C rewrites" for why the holding duration
   matters.
2. **Rejected for now: a literal new `refs/nsc/claims/decomposition-apply-global` ref.** This would work, but it
   requires extending `claim_refs.py`'s public surface with a bespoke ref outside the `tasks/<id>` /
   `resources/<hash>` shape `_claim_refs` already builds, and gives no capability the logical resource token does
   not already provide. It would only be preferable if some future requirement needed to distinguish "the global
   decomposition lock" from "an ordinary resource claim" in `inspect_claims` output; nothing identified in this
   audit needs that distinction. Default to the logical-resource design.
3. Rejected alternative: rely on push-time non-fast-forward rejection alone. This works for *detecting* the race
   but wastes an entire D1B.2 authorization cycle's worth of work on the loser and does not prevent the ID
   `NSC-{N}` from being *proposed* twice to two different humans for authorization simultaneously, which is
   confusing operationally even though D1C's stale-check would eventually reject the second one. The global
   claim reduces wasted human authorization cycles, not just wasted compute — though per the correction above,
   it does not eliminate them, since any unrelated commit landing between authorization and apply still forces a
   fresh D1B round.

This does **not** need to serialize with *implementation* claims — an implementation worker claiming
`NSC-044`'s resources is unaffected by a concurrent decomposition-apply logical-resource claim for `NSC-021`,
since they touch disjoint task/resource claim refs. Only D1C-vs-D1C needs the extra global point.

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

## Read-after-write verification for new decomposition Issue writes

**RECOMMENDATION, hard prerequisite.** Every new Issue mutation this design introduces (`decomposition_proposal`
creation, `decomposition_review` posting, `decomposition_apply_authorization` posting, `decomposition_apply`
closeout) must reuse the SAME bounded read-after-write verification `issue_workflow_store.py` already
centralizes (`_verify_post_mutation_state`, behind commit `109380b`), not a new, duplicated timing loop. **This
is not yet true of all EXISTING direct Issue-mutation paths in production**, so it cannot be assumed solved
merely because the pattern exists somewhere in the codebase — see `CONCURRENCY_AND_FAILURE_MODEL.md` races
#6/#12 and `GAUNTLET_PREREQUISITES.md` item 5 for the current, incomplete audit state
(`goal_loop_guard.py::_release_active_lease` is named there as current evidence a direct
`add_comment`/`update_issue` → immediate `find` path still bypasses the centralized verifier; this audit also
found the same shape in `downstream_issue.py` and `downstream_runtime.py`). Stage 5 must not add another direct
mutation-then-immediate-read path of its own; every new decomposition Issue write goes through the central
verifier, and production's existing direct paths must be audited and closed onto the same verifier (production
issue #104) before any Stage 5 slice that adds real decomposition Issue mutations (Slice 4+ in
`IMPLEMENTATION_SEQUENCE.md`) is enabled for live use.

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
