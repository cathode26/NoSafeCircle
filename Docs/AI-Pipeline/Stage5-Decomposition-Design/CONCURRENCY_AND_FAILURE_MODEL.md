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

- **Authority:** the proposed global `refs/nsc/claims/decomposition-apply-global` claim ref
  (`ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Serialization of graph mutation").
- **Fail-closed:** the second D1C attempt to acquire the global claim gets `ClaimConflict`; it must not proceed
  to `os.replace`/commit while holding no global claim.
- **Retry/recovery:** losing D1C attempt waits (or is reported `blocked`/`retryable`) and re-attempts after the
  first application's commit is visible; because D1C recomputes its plan from *current* HEAD before mutating
  (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Deterministic revalidation"), the retried attempt allocates the correctly
  shifted ID range automatically.
- **Serialization required:** **Yes — this is the one race in this document that requires a new global
  serialization point**, not just per-task/per-resource exclusion, because ID allocation
  (`next_number = max(existing) + 1`) reads global graph state.
- **Proving test:** new deterministic test — two `GraphDeltaPlan`s for two different parents built against the
  same synthetic source graph, both attempt to acquire the global claim against a shared fake remote; assert
  exactly one wins and the loser's retried allocation, recomputed after the winner's commit, does not collide.

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

- **Authority:** whichever commit lands first on `main` is authoritative; a dependent's implementation claim
  is only valid against the exact contract hash it observed.
- **Fail-closed:** if D1C's commit (rewriting dependent X's `depends_on` from parent P to child C, and
  incrementing X's `contract_revision`) lands *after* worker W already acquired an `agent_working` lease on X
  under the old contract hash, W's lease remains valid for the work it already started (the contract's
  *executable content* — AC/VAL, resources — did not change, only `depends_on`), but any *later* resume of W's
  Issue must re-observe the new contract hash. This is exactly the existing stale-contract-hash defense in
  `durable_selection.py` (*"Issue contract hash differs from current committed contract"* → excluded from
  resume). If D1C's commit lands *before* W's claim attempt, W's claim naturally reads the new dependency graph
  because Stage 3 always re-observes current HEAD (`fresh_dispatch.py`).
- **Retry/recovery:** normal resume-staleness handling; no new mechanism.
- **Serialization required:** No — existing contract-hash staleness check is sufficient.
- **Proving test:** extend `durable_selection.py`'s existing staleness test with a fixture where the dependent's
  `depends_on` (not just AC/VAL) changed between Issue creation and resume.

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

## 16. Two approved graph deltas overlap in affected contracts/resources

- **Authority:** D1C's revalidation-from-current-HEAD (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Deterministic
  revalidation") plus `validate_decomposition_graph_semantics`' existing rule that no active contract may
  depend on a decomposed aggregate.
- **Fail-closed:** if plan A (decomposing parent P1) and plan B (decomposing parent P2, where P2 was one of
  P1's proposed children, or where P1 and P2 shared an inbound dependent) were both authorized before either
  applied, whichever applies second will recompute its delta against post-A HEAD. If B's proposal's
  `parent_before_hash` for P2 (or for the shared dependent) no longer matches, B fails closed as `stale_proposal`
  exactly like race 14 — this is not a new mechanism, it is the same identity-binding check catching a
  cross-plan overlap rather than a same-plan staleness.
- **Retry/recovery:** operator re-runs D1B for plan B against the new graph.
- **Serialization required:** the global apply claim (race 2) again reduces the *frequency* of this outcome
  (only one D1C apply proceeds at a time) but does not eliminate the *need* for the check, because A and B could
  be authorized minutes apart with B's proposal simply going stale in the interim — a purely sequential,
  non-concurrent case that still needs this defense.
- **Proving test:** new deterministic test with two `GraphDeltaPlan`s whose affected-contract sets overlap
  (e.g., parent P1's proposed rewrite touches a dependent that P2's proposal also rewrites); apply A, then
  attempt to apply B, and assert `stale_proposal` with a diagnostic naming the specific overlapping contract.

## Summary: what genuinely needs new serialization vs. what is already covered

| Race class | New mechanism required? |
| --- | --- |
| Same-parent double-selection (#1) | No — reuse existing per-task claim |
| ID allocation across different concurrent applications (#2) | **Yes — global apply claim** |
| Reader-during-write (#3) | No — atomic commit boundary already sufficient |
| Dependency rewrite vs. dependent claim (#4) | No — existing contract-hash staleness check |
| Claim-then-stale-Issue (#5) | No — already implemented |
| Read-after-write lag (#6, #12) | No — reuse existing fix pattern |
| Checkout/origin drift (#7, #8) | No — reuse existing checks |
| Falls behind main (#9) | No — ordinary push rejection + no-force-push discipline |
| Partial filesystem write (#10) | **Yes — new orphaned-child validation check** (called out as a real gap) |
| Push failure / crash at any transition (#11, #13) | No — durable-state-only-in-Git/Issue design already sufficient |
| Stale human approval (#14) / overlapping plans (#16) | No — D1C's own identity-binding check, reused |
| Double apply (#15) | **Yes — new idempotency check** (specified in D1C design, not yet built) |
