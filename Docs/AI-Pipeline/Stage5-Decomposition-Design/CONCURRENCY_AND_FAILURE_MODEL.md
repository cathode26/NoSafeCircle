# Concurrency and Failure Model — Stage 5 / D1C

**RECOMMENDATION** document (threat model for not-yet-built behavior), grounded in the concurrency primitives
that already exist and are audited in `CURRENT_STATE_AUDIT.md`.

For each race: **Authority** (what decides), **Fail-closed behavior**, **Retry/recovery**, **Serialization
required?**, **Proving test**.

## 1. Two workers choose the same decomposition parent

- **Authority:** `claim_refs.py` task claim ref on the parent ID (reused unchanged per
  `ORCHESTRATOR_INTEGRATION_DESIGN.md`).
- **Fail-closed:** the losing worker's `git push --atomic --force-with-lease=<parent-ref>:` fails with proven
  nonexistence-CAS rejection → typed `ClaimConflict(kind="held_by_other")`.
- **Retry/recovery:** loser is excluded via `excluded_task_ids` in
  `resolve_generic_dispatch_with_contention_retry` (reused unchanged) and the plan is rebuilt fresh.
- **Serialization required:** No — per-parent claim exclusion is sufficient; different parents proceed in
  parallel.
- **Proving test:** analogous to existing `Pipeline/TaskReviewAgent/tests/contention_retry_smoke_test.py`, with
  a decomposition-phase Issue substituted for an implementation one.

## 2. Two different decomposition applications allocate child IDs concurrently

- **Authority:** the logical exclusive-resource token `logical:taskgraph-decomposition-apply-global`
  (`ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Serialization of graph mutation"), included in the SAME atomic claim
  set as D1C's parent/affected-dependent/resource claims — not a literal new claim ref (`claim_refs.py`
  provides no such primitive today).
- **Fail-closed:** the second D1C attempt to acquire the shared claim set gets `ClaimConflict`; it must not
  proceed to `os.replace`/commit while holding no claim on the logical resource.
- **Retry/recovery: CORRECTED.** The losing attempt does not "recompute and correctly shift" the SAME reviewed
  `GraphDeltaPlan` into a successful apply. Because `source_graph_semantic_hash` is a whole-graph hash
  (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Deterministic child ID allocation and collision handling"), the winner's
  commit changes it regardless of which parent the winner decomposed. When the loser retries after the winner's
  commit is visible, D1C's identity-binding check (re-run against the new HEAD) almost always finds
  `source_graph_semantic_hash` no longer matches the loser's stored, reviewed plan — the correct, and typical,
  outcome is `stale_proposal`, not a silently-reallocated successful apply. Recovery is: rerun D1B against the
  new HEAD, producing a NEW `GraphDeltaPlan`/`plan_id` for the loser's parent (which will correctly allocate
  `NSC-{N+1}` because it now observes the winner's committed child), then obtain independent human
  re-authorization for that new `plan_id` before attempting to apply again. The global claim's value is
  preventing two applications from ever committing at the SAME instant (which would risk a genuine ID collision
  or a torn intermediate graph state); it does not, and cannot, make a stale reviewed proposal valid.
- **Serialization required:** **Yes — this is one of the two races in this document requiring a new mechanism**
  (see also race #4), because ID allocation (`next_number = max(existing) + 1`) reads global graph state and two
  D1C commits must never land in the same instant.
- **Proving test:** new deterministic test — two `GraphDeltaPlan`s for two different parents built against the
  same synthetic source graph, both attempt to acquire the shared logical-resource claim against a shared fake
  remote; assert exactly one wins; assert the loser's retried apply attempt against the winner's post-commit
  HEAD is correctly rejected as `stale_proposal` (NOT that it succeeds with a shifted allocation); assert a
  fresh D1B run against that same post-commit HEAD produces a new plan that DOES correctly allocate the shifted
  ID range.

## 3. Decomposition applies while another worker is computing fresh readiness

- **Authority:** `current_conformance.py`/`load_persistent_work_graph`, which always re-reads committed HEAD;
  there is no cached readiness snapshot with a staleness window in the reviewed code.
- **Fail-closed:** not applicable as a failure — a reader either observes pre-apply or post-apply HEAD, both of
  which are individually valid graphs (D1C never leaves an invalid committed state, per its Git-commit-boundary
  design). A reader never observes a torn/partial graph because it always reads one exact commit.
- **Retry/recovery:** none needed; this is not actually a race once D1C's atomicity guarantee
  (§"Git commit boundary" in `D1C_GRAPH_APPLICATION_DESIGN.md`) holds.
- **Serialization required:** No.
- **Proving test:** existing-pattern test — run `evaluate_current_conformance` against pre-apply commit and
  post-apply commit in the same synthetic repo and assert both are independently valid, self-consistent
  results.

## 4. Decomposition rewrites a dependency while dependent implementation is being claimed

- **Authority: CORRECTED.** The affected-contract authority set + atomic multi-task claim + durable Issue state
  check described in `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Protecting existing task contracts D1C rewrites" —
  not, as an earlier draft of this document claimed, "whichever commit lands first" alone.
- **Fail-closed:** D1C must prove, immediately before mutating, that no affected existing task (parent + every
  rewritten dependent) is currently `agent_working` for any worker or `human_action_required` in a phase where
  mutation is unsafe. If worker W already holds a verified `agent_working` durable Issue lease on dependent X
  when D1C attempts to claim X's contract-mutation authority, D1C's durable-state check finds this and D1C
  **blocks** — it does not proceed to rewrite X's `depends_on`/`contract_revision` underneath W. Conversely, if
  D1C's atomic multi-task claim on X is acquired first (and D1C's durable-state check found X safe to mutate at
  that moment), a NEW attempt by any worker to acquire an `agent_working` lease on X loses the ordinary claim
  race on the same `task_claim_ref(namespace, X)` D1C is holding — this is the SAME ref implementation dispatch
  already claims via `acquire_issue_lease_with_claims`, so no new ref-naming convention is needed, only the
  ability to hold multiple such refs atomically and for the duration of the whole apply (not release them
  immediately after acquisition, as an ordinary lease handoff does).
- **Retry/recovery:** a worker that lost the race to D1C's multi-task claim retries after D1C's commit lands and
  correctly observes the new contract (the existing stale-contract-hash resume defense in `durable_selection.py`
  still applies to any LATER resume, unchanged). A D1C attempt that found an affected task already
  `agent_working` reports blocked/retryable and must retry later, once that worker's lease is released, rather
  than proceeding partially.
- **Serialization required:** **Yes — this is the second race in this document requiring a new mechanism**: an
  atomic multi-task claim extension to `claim_refs.py` (new code — `acquire()` claims exactly one `task_id`
  today) plus a durable-state precondition check, both re-verified immediately before mutation. An earlier draft
  of this document incorrectly concluded "No — existing contract-hash staleness check is sufficient"; that check
  protects a later RESUME, not an ALREADY-ACTIVE worker, which is the actual case this race describes.
- **Proving test:** new deterministic tests (not yet built) covering: (a) a dependent worker's lease acquisition
  winning before D1C attempts its claim — D1C blocks and does not mutate; (b) D1C's multi-task claim winning
  first — a subsequent implementation lease attempt on the same dependent loses the ordinary claim race and
  correctly resumes/re-derives against the new contract after D1C's commit lands; (c) genuine simultaneous
  contention resolving to exactly one winner with no double-grant.

## 5. Task/resource claim succeeds then Issue mutation is stale

- **Authority:** `_exact_authority_failures` in `claim_refs.py` (already implemented, unchanged for
  decomposition) — re-reads the Issue after `acquire_agent_lease` and verifies exact `lease_id`,
  `state_version`, `last_event_id`.
- **Fail-closed:** any mismatch returns `status: "blocked"` with the claim released; this is **already fully
  implemented and reused verbatim** for decomposition leases.
- **Retry/recovery:** existing `_release_for_report` path; no change needed.
- **Serialization required:** No.
- **Proving test:** already covered by existing `claim_refs_smoke_test.py`; extend fixtures to include a
  decomposition `work_type` Issue.

## 6. Issue mutation succeeds but immediate read is stale (GitHub read-after-write lag)

- **Authority:** `Pipeline/TaskReviewAgent/issue_workflow_store.py::POST_MUTATION_VERIFICATION_DELAYS_SECONDS`
  (bounded retry `0.0, 1.0, 2.0, 4.0, 8.0`s on the *read* side only, never repeating the mutation) — this is the
  fix corresponding to commit `109380b fix: tolerate GitHub read-after-write lag`.
- **Fail-closed / retry:** **RECOMMENDATION** — reuse this exact helper for decomposition Issue reads (proposal
  creation, apply-authorization comment, closeout). Do not write a second, decomposition-specific read-after-
  write tolerance implementation.
- **Serialization required:** No.
- **Proving test:** `Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py` (~lines 328-428) already
  proves this for implementation Issue writes; extend the same monkeypatched-delay pattern to decomposition
  Issue writes rather than duplicating the fix.

## 7. Checkout HEAD differs from proposal source

- **Authority:** `context_builder.py::source_revalidation_reasons` (D1B) and D1C's own binding check
  (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Source HEAD/tree/task-contract identity binding").
- **Fail-closed:** both stages independently detect and reject drift; D1C never trusts D1B's revalidation as
  sufficient for its own, later-in-time apply step — it re-captures and re-checks.
- **Retry/recovery:** operator re-runs from fresh checkout at current HEAD.
- **Serialization required:** No.
- **Proving test:** deterministic test mutating the synthetic repo between D1B "acceptance" and D1C "apply" and
  asserting `stale_proposal` rejection.

## 8. Origin changes

- **Authority:** `Pipeline/TaskReviewAgent/real_checkout.py::CANONICAL_REMOTE` /
  `_normalized_remote` origin-binding checks (Stage 4.1, per
  `Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md`).
- **Fail-closed:** **RECOMMENDATION** — D1C's checkout preparation must reuse this exact origin-binding check,
  not a separate one, so a decomposition-apply checkout pointed at a fork or mismatched remote fails exactly as
  an implementation checkout would.
- **Serialization required:** No.
- **Proving test:** reuse/extend existing Stage 4.1 origin-binding tests
  (`Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py`) with a D1C-apply fixture.

## 9. Graph-application branch falls behind `main`

- **Authority:** ordinary Git push rejection (non-fast-forward) is sufficient *detection*; the global claim
  (race 2) is what prevents wasted human-authorization cycles, but even without it, a behind-`main` push simply
  fails and D1C must not force-push (`D1C_GRAPH_APPLICATION_DESIGN.md` §"No destructive reset/force-push
  assumptions").
- **Fail-closed:** push rejected → D1C reports `push_rejected_stale`, discards its local disposable commit, and
  the operator/automation restarts D1C from fresh HEAD.
- **Retry/recovery:** restart is safe/idempotent per §"Idempotency/replay behavior" in the D1C design.
- **Serialization required:** the global claim (race 2) makes this the *common* case rare, but this check must
  exist regardless as defense in depth.
- **Proving test:** simulate a push rejection against a fake remote and assert clean local-commit discard +
  no partial state left in the working tree.

## 10. Partial multi-file filesystem write

- **Authority:** the ordered `os.replace` sequence + post-write `validate_decomposition_graph_semantics`
  gap-closing check described in `D1C_GRAPH_APPLICATION_DESIGN.md` §"What happens if filesystem write succeeds
  partially."
- **Fail-closed:** on next `load_persistent_work_graph`, an orphaned child (provenance names a plan whose parent
  isn't yet decomposed) must be rejected — this is a **required new check**, not yet implemented, and is called
  out explicitly as a gap in the D1C design rather than assumed solved.
- **Retry/recovery:** manual operator recovery only (inspect partial `Tasks/` state, complete or revert);
  D1C must never auto-repair.
- **Serialization required:** No (this is a crash-recovery concern, not a concurrency one) — but note it
  compounds with race 2 if a crash happens while holding the global claim: the claim must remain held (no
  TTL/auto-release) until manually repaired, exactly as the existing claim-ref crash policy already specifies
  (`claim_refs.py` module docstring: *"Crash policy: there is no TTL... repaired manually with exact-SHA fencing
  only"*).
- **Proving test:** new deterministic test — kill the apply process (simulated by raising after N of M
  `os.replace` calls) and assert (a) the partial state is detected as invalid on next load, (b) no auto-repair
  occurs, (c) the global claim ref (if used) is still present for manual inspection.

## 11. Commit succeeds but push fails

- **Authority/fail-closed/retry:** covered in `D1C_GRAPH_APPLICATION_DESIGN.md` §"Recovery if commit/push/Issue
  update fails" — discard local commit, restart from fresh HEAD (safe due to idempotency).
- **Serialization required:** No.
- **Proving test:** simulate push failure against a fake remote; assert restart produces an equivalent
  (or correctly-rejected-if-conflicting) result.

## 12. Push succeeds but Issue closeout verification lags

- **Authority:** same read-after-write tolerance pattern as race 6.
- **Fail-closed:** never re-attempt the already-successful push/commit merely because the Issue read looked
  stale; retry only the read, bounded.
- **Serialization required:** No.
- **Proving test:** same class as race 6's test, applied to the decomposition-closeout write path.

## 13. Worker crashes at every transition

- **Authority:** durable Issue state (survives process crash by construction — it's on GitHub) + claim refs
  (survive by construction — they're on the remote) + local disposable checkout (does not survive, and is not
  relied upon to).
- **Fail-closed:** a crash before Issue lease acquisition leaves nothing (no claim, no Issue mutation) — a
  later worker just starts fresh. A crash after lease acquisition but before D1C mutation leaves an
  `agent_working` decomposition Issue a later worker can resume (§"Resuming interrupted proposal/review/
  application work" in `ORCHESTRATOR_INTEGRATION_DESIGN.md`). A crash during D1C mutation is race 10. A crash
  after push but before Issue closeout is race 12.
- **Retry/recovery:** case-by-case per above; no single crash produces silent data loss because every durable
  fact lives in GitHub (Issue) or Git (commit), never solely in local process memory.
- **Serialization required:** No additional mechanism beyond what's already listed per-transition.
- **Proving test:** a parametrized crash-injection test that kills the (simulated) worker at each named
  transition and asserts the next worker's resume/fresh-selection produces a safe, non-duplicating outcome.

## 14. Human approves an old proposal after parent contract changes

- **Authority:** D1C's stale-proposal rejection (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Source HEAD/tree/
  task-contract identity binding") is the final, authoritative check — it does not matter that a human already
  posted `Result: APPROVE`; D1C still independently re-verifies identity before mutating.
- **Fail-closed:** D1C reports `stale_proposal`; the apply-authorization Issue phase must then require a fresh
  D1B round (new proposal against the new parent) rather than silently re-approving the old one.
- **Retry/recovery:** operator/worker restarts decomposition from `decomposition_proposal` phase.
- **Serialization required:** No.
- **Proving test:** same as race 7's test, but specifically exercised through the human-approval Issue phase
  rather than directly against D1C's function boundary — proves the *orchestrator*, not just D1C in isolation,
  refuses to skip the check.

## 15. Decomposition applied twice

- **Authority:** D1C's idempotency check (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Idempotency/replay behavior").
- **Fail-closed:** second application detects `plan_id` already reflected in current HEAD and returns
  `already_applied` without mutating.
- **Retry/recovery:** not applicable — this is the safe terminal state.
- **Serialization required:** the global claim (race 2) also incidentally prevents most double-apply attempts
  from running concurrently, but the idempotency check is the actual defense for the *sequential* double-apply
  case (e.g., an operator re-runs a script by mistake after the first run already completed and released its
  claim).
- **Proving test:** new deterministic test — apply a `GraphDeltaPlan` to a synthetic repo, commit, then attempt
  to apply the identical plan again against the resulting HEAD; assert `already_applied` and zero additional
  file changes/commits.

## 16. Two approved graph deltas applied sequentially (overlapping or not)

- **Authority:** D1C's revalidation-from-current-HEAD (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Deterministic
  revalidation") — specifically, the whole-graph `source_graph_semantic_hash` comparison.
- **Fail-closed: CORRECTED and broadened.** Because `source_graph_semantic_hash` is a hash of the entire graph
  (`id_map` + `tasks` + `resource_groups` + `project_requirements`), applying plan A ALWAYS invalidates every
  other already-authorized plan B, whether or not A's and B's affected-contract sets literally overlap — an
  earlier draft of this document scoped this race to only the overlapping case, which understates it. Whichever
  plan applies second always fails `stale_proposal` against the first plan's post-apply HEAD; this is not a new
  mechanism, it is the ordinary identity-binding check.
- **Retry/recovery:** operator/orchestrator re-runs D1B for the second plan against the new graph, producing a
  new `plan_id`, and obtains independent human re-authorization for it — the previous `APPROVE` named the old
  `plan_id` and does not carry forward (`ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Human review/approval boundary").
- **Serialization required:** the global logical-resource claim (race 2) reduces how often two applications race
  to commit at the SAME instant, but does not eliminate the need for this check — A and B could be authorized
  minutes apart with B simply going stale in the interim, a purely sequential, non-concurrent case that still
  needs this defense every time.
- **Proving test:** new deterministic test applying plan A (any parent), then attempting to apply plan B
  (authorized against the same pre-A HEAD, for ANY other parent — overlapping affected-contracts not required to
  reproduce this), and asserting `stale_proposal`; a second test confirms a freshly re-run D1B for B's parent
  against post-A HEAD produces a new, independently valid `plan_id`.

## Summary: what genuinely needs new serialization vs. what is already covered

| Race class | New mechanism required? |
| --- | --- |
| Same-parent double-selection (#1) | No — reuse existing per-task claim |
| ID allocation across different concurrent applications (#2) | **Yes — global logical-resource claim, reused via `resource_claim_ref`** |
| Reader-during-write (#3) | No — atomic commit boundary already sufficient |
| Dependency rewrite vs. active dependent worker (#4) | **Yes — new atomic multi-task claim + durable-state precondition check** (corrected; an earlier "No" was wrong — see race #4) |
| Claim-then-stale-Issue (#5) | No — already implemented |
| Read-after-write lag (#6, #12) | Reuse existing centralized verifier — but production's own adoption of it is not yet complete; see `GAUNTLET_PREREQUISITES.md` item 5 and `goal_loop_guard.py::_release_active_lease` |
| Checkout/origin drift (#7, #8) | No — reuse existing checks |
| Falls behind main (#9) | No — ordinary push rejection + no-force-push discipline |
| Partial filesystem write (#10) | **Yes — new orphaned-child validation check** (called out as a real gap) |
| Push failure / crash at any transition (#11, #13) | No — durable-state-only-in-Git/Issue design already sufficient |
| Stale human approval (#14) / sequential re-apply (#16) | No new mechanism — D1C's own identity-binding check, reused; scope of #16 broadened, see race #16 |
| Double apply (#15) | **Yes — new idempotency check** (specified in D1C design, not yet built) |
