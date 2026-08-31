# Gauntlet Prerequisites — What Stage 5/D1C Must Not Assume Yet

**RECOMMENDATION** document, grounded in facts about what the live Gauntlet is and what Stage 5 would reuse.

## What the Gauntlet is

**FACT.** `Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md`: *"After Stage 4.1 lands, the next
planned milestone is the dedicated multi-worker Gauntlet: update the Gauntlet template from the new main, use a
dedicated/private GitHub repository with synthetic Issues, and run real simultaneous workers to prove
concurrency behavior outside local synthetic fixtures."* The same document's "Current objective" section lists
exactly the properties being proven: finishing advanced actionable work before starting new work, respecting
TaskGraph dependencies, avoiding exclusive-resource/write-surface conflicts, atomic Git claims for concurrent
starts, GitHub Issues as durable workflow state, isolated task checkouts, serialized integration through
`main`, revalidation after integration, and stopping at genuine human-authority boundaries.

**INFERENCE.** The Gauntlet is the **first live, real-GitHub, real-concurrency proof** of exactly the machinery
`ORCHESTRATOR_INTEGRATION_DESIGN.md` proposes reusing unchanged for decomposition: `dispatch_plan.py`,
`fresh_dispatch.py`, `claim_refs.py`, `claim_policy.py`, `issue_workflow.py`,
`issue_workflow_store.py`. Everything in that design that says "reuse X unchanged" is only as trustworthy as
the Gauntlet's proof that X is correct under real concurrent load, not just under synthetic single-process test
fixtures.

## Why this matters specifically for Stage 5, not just in general

Ordinary implementation-dispatch defects are *recoverable*: a worker claims the wrong task, loses a race, or
resumes incorrectly, and the fix is "release and retry" against code that never mutated the persistent graph.
Stage 5's D1C step is different in kind: it **writes new task contracts and rewrites existing ones into
`Tasks/*.yaml` on `main`**. If an undiscovered concurrency defect in the reused claim/Issue machinery let two
D1C applications proceed concurrently, the result is not "one worker retries" — it is a **corrupted or
double-decomposed persistent graph** that every other worker (implementation and decomposition alike) then reads
as authoritative. This asymmetry is why Stage 5's orchestrator-integration slices (4-8 in
`IMPLEMENTATION_SEQUENCE.md`) are gated on Gauntlet acceptance while the purely deterministic D1C slices (1-3)
are not.

## Prerequisite list

### 1. Generic resume/fresh selection

- **Why decomposition depends on it:** `ORCHESTRATOR_INTEGRATION_DESIGN.md` proposes extending
  `dispatch_plan.py`'s exact resume-first/fresh-candidate ranking to decomposition parents. If resume-first
  ordering has an undiscovered defect (e.g., picks a stale candidate, or fails to prefer resume over fresh under
  real timing), decomposition inherits it identically.
- **What Gauntlet behavior proves it:** repeated real invocations across many workers correctly finish
  in-flight work before starting new work, matching the documented objective.
- **What must remain blocked if it fails:** Slice 5 (generic dispatcher/resume integration) — do not extend
  ranking logic that hasn't been proven correct under load.
- **Architectural or operational?** Architectural — this is the actual selection algorithm decomposition would
  reuse, not a config knob.

### 2. Claim contention

- **Why decomposition depends on it:** Slice 6a's global logical-resource claim reuses the existing single-task
  `acquire()`/`resource_claim_ref()` path *unchanged*, so its correctness under real network/GitHub timing (not
  just synthetic bare-repo tests) is exactly what the Gauntlet is built to observe
  (`probe_remote_claim_namespace`'s docstring already flags namespace support as "unproven" pending a live
  capability test). **Slice 6b's atomic multi-task claim is different: it is new code the Gauntlet does not
  exercise at all, because it does not exist yet.** Gauntlet acceptance proves the single-task primitive 6b
  extends; it does not, by itself, prove the extension.
- **What Gauntlet behavior proves it:** real concurrent claim attempts against the dedicated Gauntlet repository
  correctly produce exactly one winner (or zero, on transient contention) with no double-grant — for the
  single-task primitive. This is a necessary, not sufficient, precondition for trusting Slice 6b's extension.
- **What must remain blocked if it fails:** Slice 6a entirely if the underlying single-task primitive fails;
  Slice 6b regardless, until its own dedicated proof (deterministic + live) is complete — a global/multi-task
  claim built on an unproven primitive is a false sense of safety for the two highest-risk races in
  `CONCURRENCY_AND_FAILURE_MODEL.md` (#2 ID collision, #4 active-worker contract protection).
- **Architectural or operational?** Architectural — the claim primitive itself, not its policy configuration.

### 3. Exclusive resources

- **Why decomposition depends on it:** D1C must claim every proposed child's `exclusive_resources` before
  committing (`ORCHESTRATOR_INTEGRATION_DESIGN.md` §"What resources must be locked during application"). This
  assumes resource-conflict detection correctly prevents two *unrelated* workers from touching the same
  Unity scene/prefab/logical resource concurrently — proven today only in synthetic fixtures
  (`Pipeline/TaskReviewAgent/tests/resource_reservation_smoke_test.py`).
- **What Gauntlet behavior proves it:** real parallel workers with overlapping `exclusive_resources` correctly
  block/serialize rather than both proceeding.
- **What must remain blocked if it fails:** any Stage 5 slice that claims resources for proposed children
  (Slice 6) — a proposed child's resource claim is only meaningful if resource-conflict detection is already
  trustworthy for *existing* tasks.
- **Architectural or operational?** Architectural.

### 4. Durable Issue leases

- **Why decomposition depends on it:** every new decomposition `WorkflowPhase` (Slice 4) rides on the exact
  same `WorkflowState`/lease/hash-chain machinery already used for `agent_working`/`human_action_required`.
  A defect in lease re-verification (`_exact_authority_failures` in `claim_refs.py`) under real concurrent
  GitHub API timing would silently grant decomposition authority incorrectly.
- **What Gauntlet behavior proves it:** real simultaneous lease-acquisition attempts across many workers never
  produce two workers believing they hold the same `agent_working` lease.
- **What must remain blocked if it fails:** Slice 4 (Issue phase additions) and everything after it — the
  schema addition itself is low-risk, but *using* it in real leases before this is proven is not.
- **Architectural or operational?** Architectural.

### 5. Bounded read-after-write verification

- **Why decomposition depends on it:** `CONCURRENCY_AND_FAILURE_MODEL.md` races #6/#12 require every new
  decomposition Issue write (proposal creation, apply-authorization, closeout) to reuse the central bounded
  verifier `Pipeline/TaskReviewAgent/issue_workflow_store.py::_verify_post_mutation_state`
  (`POST_MUTATION_VERIFICATION_DELAYS_SECONDS`), not a duplicated timing loop.
- **CORRECTED — this is not a pure tuning risk; production adoption of the pattern is itself incomplete.**
  `Pipeline/TaskReviewAgent/goal_loop_guard.py::_release_active_lease` performs a direct
  `backend.add_comment` → `backend.update_issue` → immediate `service.find(task_id)` → exact compare, with ONE
  immediate reread and no bounded retry — it does not call `_verify_post_mutation_state` at all. This is
  current, committed production code (not a hypothetical), and it is exactly the class of defect commit
  `109380b` fixed elsewhere. A pass over `Pipeline/TaskReviewAgent/downstream_issue.py` and
  `Pipeline/TaskReviewAgent/downstream_runtime.py` during this revision found the same direct
  `add_comment`/`update_issue` → immediate `find` shape in multiple additional transitions there, also bypassing
  the centralized verifier. The production #104 class ("tolerate GitHub read-after-write lag") is therefore
  open, not closed, even though the fix pattern itself is proven correct where it HAS been applied.
- **What Gauntlet behavior proves it:** the existing bounded retry window remains sufficient (or is found/fixed
  to be insufficient) under real concurrent write volume, for the paths that already use it — but the Gauntlet
  does not, by itself, close the adoption gap above; that requires a dedicated code audit and fix, independent
  of Gauntlet timing.
- **What must remain blocked if it fails, or while the adoption gap remains open:** any Stage 5 slice that adds
  real decomposition Issue mutations (Slice 4's schema-only additions are unaffected; Slice 5+ is blocked). This
  is a **hard prerequisite**, not an optional tuning item: Stage 5 must not add a new direct
  mutation-then-immediate-read path of its own, and production's existing direct paths (at minimum
  `goal_loop_guard.py`, and the additional instances found in `downstream_issue.py`/`downstream_runtime.py`)
  must be routed through the central verifier and closed as production issue #104 before Stage 5's
  Issue-mutating slices go live.
- **Architectural or operational?** Both: the mechanism itself is architecturally sound where applied (bounded
  read-only retry, never repeat the mutation) — but its incomplete rollout across existing direct
  mutation/read paths is an open architectural gap in production, not merely a tuning parameter.

### 6. Checkout/origin binding

- **Why decomposition depends on it:** D1C's checkout preparation is designed to reuse Stage 4.1's origin-
  binding checks verbatim (`CONCURRENCY_AND_FAILURE_MODEL.md` race #8). Stage 4.1 landed recently (per
  `Docs/AI-Pipeline/Historical-Context-Sessions/CURRENT_CONTEXT.md`, still being verified as of the last
  session) and has not yet been proven under real multi-worker load.
- **What Gauntlet behavior proves it:** many real concurrent checkouts against the dedicated Gauntlet
  repository never bind to the wrong origin or silently succeed against a mismatched remote.
- **What must remain blocked if it fails:** Slice 5/7 — do not create a decomposition-apply checkout variant of
  a binding check that hasn't itself been proven.
- **Architectural or operational?** Architectural (recently landed, unproven at scale).

### 7. Human handoff/result binding

- **Why decomposition depends on it:** `ORCHESTRATOR_INTEGRATION_DESIGN.md`'s
  `decomposition_apply_authorization` phase is modeled directly on the exact-commit PASS/FAIL binding pattern
  (`HUMAN_RESULT_RE`, `parse_human_validation_result`), extended to bind by `plan_id` instead of commit SHA.
  If the underlying exact-identity-binding pattern has an edge case under real human/timing variability (e.g.,
  a human approves while a new event is mid-append), decomposition's `plan_id` variant would inherit it.
- **What Gauntlet behavior proves it:** real human PASS/FAIL interactions, including any edge-case timing
  against concurrent agent activity, are correctly bound and never misattributed.
- **What must remain blocked if it fails:** Slice 4/5's apply-authorization phase design — the *pattern* would
  need revision before decomposition adopts it, not just decomposition's usage of it.
- **Architectural or operational?** Architectural for the binding pattern itself; the `plan_id` extension is a
  Stage 5-specific application of it.

### 8. Delivery evidence/conformance

- **Why decomposition depends on it:** `current_conformance.py`'s aggregate-conformance read path
  (`CURRENT_STATE_AUDIT.md` — already implemented and reused unchanged by Stage 5) sits downstream of the exact
  evidence-recording pipeline the Gauntlet exercises for implementation tasks. Stage 5 does not change this
  code, but its correctness under real concurrent delivery volume (many children delivered in parallel after
  one decomposition) is exactly the kind of load the Gauntlet is designed to surface defects under.
- **What Gauntlet behavior proves it:** many real parallel deliveries produce correct, non-conflicting evidence
  records and correct derived conformance.
- **What must remain blocked if it fails:** nothing Stage 5-specific — a defect here is upstream of Stage 5 and
  would need fixing regardless of decomposition.
- **Architectural or operational?** Architectural, but explicitly not Stage 5's own risk surface — listed here
  because Stage 5's value proposition (newly unlocked children get implemented) is meaningless if this layer is
  unreliable.

### 9. Merge closeout

- **Why decomposition depends on it:** D1C's own commit/push step (`D1C_GRAPH_APPLICATION_DESIGN.md` §"Git
  commit boundary") is a narrower, single-actor version of the same "commit lands on `main`, closeout follows"
  pattern the merge-closeout machinery (`Pipeline/TaskReviewAgent/downstream_pipeline.py`,
  `merge_closeout_check_repoll.py`) already implements for implementation PRs. `merge_closeout_check_repoll.py`
  itself documents a prior real defect (*"A prior terminal shortcut treated every agent-ready merge-closeout
  Issue with an open PR as `checks_pending`... even after GitHub reported all checks successful"*) — direct
  evidence that this exact class of live-timing defect has occurred before and was only caught through real use,
  not synthetic tests alone.
- **What Gauntlet behavior proves it:** the fixed repoll behavior holds under real concurrent multi-worker PR/
  check activity, not just the single-worker case that surfaced the original defect.
- **What must remain blocked if it fails:** Slice 7/8 (live proofs) — do not attempt a live D1C
  commit/push/closeout cycle while the pattern it's modeled on is still being stress-tested for similar defects.
- **Architectural or operational?** Operational precedent (a real defect was found and fixed) with
  architectural implications (the general "trust live GitHub state, not a cached assumption" lesson applies
  directly to D1C's own post-commit verification design).

### 10. Dependency unlocking

- **Why decomposition depends on it:** Stage 5's entire value proposition — "generic workers may pick newly
  unlocked children" (`ORCHESTRATOR_INTEGRATION_DESIGN.md` flow diagram, final step) — is *only* correct if
  ordinary dependency-readiness evaluation (`dispatch_plan.py`'s dependency-observation logic,
  `dependency_dispatch_satisfied_states`) is already reliable under real concurrent load. Stage 5 adds zero new
  code here; it is 100% reuse.
- **What Gauntlet behavior proves it:** real dependents of real completed tasks are correctly and promptly
  recognized as dispatchable by other concurrent workers.
- **What must remain blocked if it fails:** nothing Stage 5-specific to change — but Slice 7's live proof would
  be measuring a broken foundation, so it should wait.
- **Architectural or operational?** Architectural (unchanged code) but proof-of-correctness is entirely a
  Gauntlet concern.

### 11. Recovery with no leaked claims

- **Why decomposition depends on it:** the entire crash-recovery story in `CONCURRENCY_AND_FAILURE_MODEL.md`
  (races #10, #13, #15) depends on claim refs behaving exactly as documented under a real crash — no TTL,
  visible via `inspect_claims`, repairable only by exact-SHA fencing. This has been designed and unit-tested
  (`claim_refs.py` docstring, `claim_refs_smoke_test.py`) but not yet proven against a real crashed worker
  process in a real multi-worker environment.
- **What Gauntlet behavior proves it:** a real worker crash during the Gauntlet leaves claim refs exactly where
  `inspect_claims` says they are, with no silent leak, no silent double-grant, and no automatic (incorrect)
  cleanup.
- **What must remain blocked if it fails:** Slice 6 (global apply claim reuses this exact no-TTL/manual-repair
  policy) and Slice 8 (multi-worker live proof, which is specifically designed to provoke this case).
- **Architectural or operational?** Architectural — this is a core safety property of the claim design, not a
  tuning parameter.

## Net position

Every prerequisite above is either (a) code Stage 5 proposes reusing **completely unchanged**, or (b) a design
pattern Stage 5 proposes extending. That extension is not uniform across Slice 6: **Slice 6a** (the global
`logical:taskgraph-decomposition-apply-global` resource token) is a design pattern built *on top of* the same
proven-or-not `claim_refs.py` primitive, unchanged — an ordinary string through the existing
`resource_claim_ref()` path, no new code in `claim_refs.py` itself. **Slice 6b** (the atomic multi-task claim
protecting the decomposition parent plus every rewritten dependent's contract) is different in kind: it is
genuinely new code — a generalized `acquire()`/`release()` (or sibling `acquire_multi()`/`release_multi()`) and
a widened `ClaimReceipt` schema — that does not exist yet and that the Gauntlet therefore cannot exercise,
because there is nothing there yet for it to exercise (see item 2 above). Gauntlet acceptance of the existing
single-task primitive is a necessary precondition for trusting 6b's extension, not proof of 6b itself; 6b needs
its own dedicated deterministic and live proof (`IMPLEMENTATION_SEQUENCE.md` Slice 6b) in addition to Gauntlet
acceptance. This is why the GO/WAIT split in `README.md` draws the line exactly at "touches the reused
live-concurrency machinery" vs. "purely deterministic, synthetic-repo-only": the former inherits every open
question in this document, and Slice 6b additionally inherits a proof obligation the Gauntlet alone does not
discharge; the latter (Slices 1-3) inherits neither.
