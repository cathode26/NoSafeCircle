## Item 1: checkouts.lock contention no longer ends a graph invocation

_Implemented by a delegated Opus 5 agent; independently reviewed by the Claude coordinating session before posting: full production diff read, the per-kind allowlist proofs checked against the code, the launch pre-mutation stamp and the `apply_decomposition` exclusion verified, failing-before reproduced on a fresh shimmed worktree of the parent, and the focused suites rerun on the exact commit._

### Why (run 2 evidence, root `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6`)

Every waiter on `<root>\.assistant-control\checkouts.lock` budgets 10 s, while its legitimate holders are slower. Measured holds across run 2 (action duration equals hold for these kinds):

| Holder | Samples | Median | Max |
|---|---|---|---|
| `sync_candidate` | 29 | 13.82 s | 19.52 s |
| `integrate` | 9 | 14.83 s | 21.19 s |
| `reserve` | 11 | 7.33 s | 20.98 s |
| `auto_approve` | 12 | 4.10 s | 8.71 s |
| post-crew candidate registration (child) | derived | about 9.2 s | |

Seven timeouts in total, all `TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: '...\.assistant-control\checkouts.lock'`: five in the controller, each ending its invocation, and two inside post-crew children, each failing its job (child rows show the job's failure time; the controller harvested them at 02:56:22.094 and 03:07:34.169):

| UTC (2026-09-13) | Where | Action | Task | Effect |
|---|---|---|---|---|
| 02:37:57.228 | controller | `post_crew` launch | NSC-1163 | invocation ended |
| 02:50:47.425 | controller | `sync_candidate` | NSC-1163 | invocation ended |
| 02:51:32.893 | controller | `auto_approve` | NSC-1162 | invocation ended |
| 02:56:21.933 | post-crew child | registration or persist | NSC-1164 | job failed; task blocked until `clear-background-job` |
| 02:59:41.142 | controller | `integrate` | NSC-1163 | invocation ended |
| 03:05:32.591 | controller | `auto_approve` | NSC-1170 | invocation ended |
| 03:07:27.319 | post-crew child | registration or persist | NSC-1173 | job failed; task blocked until `clear-background-job` |

The apparent inconsistency was two paths, not action kinds: a controller action that raises ends the invocation (`action_failed`, `blocked`, CLI `command_failed`, exit 1); the same timeout inside a post-crew child becomes that job's failed receipt (`job_failed`, task `background_job_failed`) and discards a finished Unity validation. The operator gaps this caused in run 2 totalled 11 min 50 s.

### Commits and lineage

| | Commit | Parent | Branch / isolated worktree |
|---|---|---|---|
| Reviewed original | `24603b97cd1a071b3f48d14d15adb1d831f2cf95` | `1dae47bea3625280e27170ea398aef9d881d744f` (the **rejected** re-pin, so not proposed on this parent) | `throughput/gauntlet-trial-fixes`, `C:\nscrev\gauntlet-fixes` |
| **Proposed for audit** | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` (cherry-pick of `24603b9`) | `36a000c3918680b150d950104c1b21724c0a3dd0` (item 2) | `throughput/assistantcontrol-fixes`, `C:\nscrev\ac-fixes` |

The two commits change disjoint files; after the cherry-pick every lock-fix file is byte-identical to `24603b9`, every migration file byte-identical to `36a000c`, and `1dae47b` is not an ancestor. `git diff 027e787 c8b07eb --check` is clean.

### Exact changed files (9)

| File | Change |
|---|---|
| `Pipeline/AssistantControl/graph_controller.py` | +164/-11: `LOCK_DEFERRABLE_ACTION_KINDS` with per-kind proof, `_checkouts_lock_contention`, `_lock_deferral`, `action_deferred` journal event, bounded retry in `_run_owned`, `lock_deferrals` in the run result |
| `Pipeline/AssistantControl/background_jobs.py` | +43/-1: `LAUNCH_LOCK_TIMEOUT_SECONDS`, and a pre-mutation stamp on `launch`'s first `checkouts.lock` acquisition only |
| `Pipeline/AssistantControl/candidate.py` | +15/-1: registration waits up to `REGISTRATION_LOCK_TIMEOUT_SECONDS = 300` |
| `Pipeline/AssistantControl/post_crew_workflow.py` | +17/-2: validation persist waits up to `VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS = 300` |
| `Pipeline/AssistantControl/test_background_jobs.py` | +325/-1: controller-side deferral tests |
| `Pipeline/AssistantControl/test_post_crew_workflow.py` | +190: child-side tests |
| `Pipeline/AssistantControl/README.md` | +28 |
| `Pipeline/AssistantControl/CURRENT.md` | +43 |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | +23/-1 |

### Behaviour

- **Controller side.** An action whose kind is in the allowlist and which loses its `checkouts.lock` wait before writing anything durable journals `action_deferred` (task, kind, `lock_contention`, lock path, seconds waited, count, limit), is not marked blocked, writes no `last_error`, keeps the invocation `running`, pauses 3 s through the controller's own `sleep`, and is re-emitted by the planner. After 6 consecutive deferrals of the same action it fails exactly as today. Deferral counts reset per invocation; stop requests are still honoured between deferrals.
- **Classification is typed.** `TimeoutError` with `errno.ETIMEDOUT`, `filename` equal to this checkout root's `checkouts.lock`, and the producer's exact wording. For the two launch kinds the exception must also carry the stamp `background_jobs.launch` sets on its single pre-mutation acquisition, because `_mark_spawn_failed` takes the same lock after a child exists.
- **Allowlist (11 kinds), each with a code-comment proof that the lock precedes every durable write:** `decompose`, `post_crew`, `prepare`, `refresh_prepared`, `scope`, `reserve`, `start_worker`, `settle_worker`, `sync_candidate`, `auto_approve`, `integrate`. Excluded: `apply_decomposition` (never takes `checkouts.lock`; verified it takes `decomposition.lock` and the Source integration lock) and the wait kinds (their acquisitions persist an observation or a Docker removal that already happened).
- **Child side.** Candidate registration and the post-validation record persist wait up to 300 s. `_exclusive_file_lock` already retries every 50 ms, so the longer budget is the bounded retry. Unity validation already ran with the lock released, and the persist re-verifies the exact candidate on acquisition. The launch budget was not lengthened.

### Tests

Twelve new tests:

| Test | Guards |
|---|---|
| `test_a_lock_contended_launch_is_deferred_and_launches_on_the_next_cycle` | launch deferral and later launch |
| `test_lock_contention_beyond_the_bound_fails_with_the_original_error` | the bound |
| `test_an_action_kind_outside_the_allowlist_still_fails_on_the_same_timeout` | unchanged behaviour outside the allowlist |
| `test_a_deferred_launch_leaves_no_ticket_index_or_run_root` | no durable residue |
| `test_a_lock_contended_sync_candidate_is_deferred_not_fatal` | foreground kind, run 2 02:50:47Z |
| `test_a_lock_contended_auto_approve_is_deferred_not_fatal` | foreground kind, run 2 02:51:32Z |
| `test_a_childs_own_lock_timeout_stays_a_harvested_job_failure` | child path kept distinct |
| `test_a_child_whose_first_registration_lock_attempt_times_out_still_completes` | child registration retry |
| `test_a_registration_lock_held_past_the_bound_fails_with_the_original_error` | child bound |
| `test_validation_runs_with_the_checkout_lock_free_and_the_persist_outwaits_it` | no discarded validation |
| `test_a_lock_held_past_the_persist_budget_fails_loudly_and_retains_state` | persist bound |
| `test_the_persist_refuses_when_the_candidate_changed_underneath` | identity re-check on re-lock |

**Failing-before on `1dae47b`** (the agent's run, with only the new constant names added as inert shims so the tests import): `FAILED (failures=5, errors=4)`; 9 fail, including the launch test reproducing the live error verbatim (`background_jobs.py:542 ... TimeoutError: [Errno 10060] timed out after 10s ... checkouts.lock`). Three pass before by design: the allowlist-gate test and the persist-bound test assert behaviour that must not change, and the candidate re-verification test guards a property that already existed.

**Reproduced by the coordinating session** on a fresh shimmed worktree of `1dae47b`: the launch-deferral and `sync_candidate`-deferral tests both `ERROR` with `TimeoutError: [Errno 10060] timed out after 0.2s waiting for exclusive file lock: '...\checkouts.lock'` (`Ran 2 tests ... FAILED (errors=2)`).

**Passing-after on `24603b9`, rerun by the coordinating session:**
- `Pipeline.AssistantControl.test_background_jobs.BackgroundJobLoopTests`: `Ran 35 tests in 221.539s` `OK`
- `Pipeline.AssistantControl.test_post_crew_workflow`: `Ran 15 tests in 113.728s` `OK`
- `Pipeline.AssistantControl.test_graph_controller`: `Ran 33 tests in 90.006s` `OK`
- `Pipeline.AssistantControl.test_decomposition`: `Ran 19 tests in 57.520s` `OK`
- `Pipeline.AssistantControl.test_candidate`: `Ran 9 tests in 51.135s` `OK`
- `Pipeline.AssistantControl.test_worker_control`: `Ran 10 tests in 18.700s` `OK`

Implementing agent, additionally: the 12 new tests `Ran 12 tests in 48.887s OK`; full `test_background_jobs` `Ran 67 tests OK`; `test_candidate` + `test_unity_materialization` `Ran 15 tests OK`; `test_gauntlet_replay` + `test_review` `Ran 13 tests OK`.

### Follow-up commit: per-cycle harvest, cleanup retries and startup reconciliation

| | Commit | Parent | Branch / isolated worktree |
|---|---|---|---|
| Reviewed original | `b42d5197d006149f25cfa354f168deebeba1c151` | `24603b97cd1a071b3f48d14d15adb1d831f2cf95` | `throughput/gauntlet-trial-fixes`, `C:\nscrev\gauntlet-fixes` |
| **Proposed for audit** | `42c09a3c5c3dd9e4582e329b361a2662ece4ab62` (cherry-pick of `b42d519`) | `c8b07eb138e2e23233eb4a464bd72b22ad1591db` | `throughput/assistantcontrol-fixes`, `C:\nscrev\ac-fixes` |

**The gap it closes.** Found in review of the first commit, with no test covering it: `_harvest_jobs` runs at the top of every cycle, outside `_execute_timed`, and caught only `BackgroundJobError`, while `background_jobs.harvest()` takes `checkouts.lock` with a 10 s budget. A lock timeout there escaped the loop and ended the invocation, contradicting the method's own docstring. `_reconcile_startup` re-raised the same timeout. Children now queue for up to 300 s instead of failing fast, which makes contiguous holds more likely, so this path had to close with the first commit.

**Exact changed files (6):**

| File | Change |
|---|---|
| `Pipeline/AssistantControl/background_jobs.py` | +169/-36: `_pre_mutation_lock` helper, `stamped_lock_contention`, `JOB_INDEX_LOCK_TIMEOUT_SECONDS`, stamps on the acquisitions below, retry-in-place parameters for `reconcile_startup` |
| `Pipeline/AssistantControl/graph_controller.py` | +84/-2: `_harvest_lock_deferral`, `job_harvest_deferred` with `reason: lock_contention`, `startup_deferred`, `harvest_deferrals` and `startup_deferrals` in the run result |
| `Pipeline/AssistantControl/test_background_jobs.py` | +368/-14: 8 tests |
| `Pipeline/AssistantControl/README.md` | +15 |
| `Pipeline/AssistantControl/CURRENT.md` | +27 |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | +9 |

**Which acquisitions may be deferred:**

| Acquisition | Verdict | Reason |
|---|---|---|
| `harvest`, first transaction | stamped | only an outcome check precedes it; the status write, cleanup begin and index write all happen under it |
| `_run_cleanup`, cleanup-generation begin | stamped | precedes this call's writes and its unlocked Docker work |
| `_record_final_recheck` | stamped | one read-verify-write transaction |
| `request_stop` | stamped | its lock is its first effect; a repeat re-verifies an existing request |
| `_record_reconciliation` | stamped | one read-verify-write transaction |
| `launch` | stamped, behaviour unchanged | now routed through the same helper |
| `_finish_cleanup` | refuted, unstamped | follows a written cleanup begin and a completed Docker reconciliation, possibly a removal |
| `_enforce_stop` | refuted, never retried | terminates a process tree; whether it can repeat depends on host state, not durable records |

**Behaviour.**
- **Per-cycle harvest.** A stamped timeout from `harvest` or `settle_cleanup` journals `job_harvest_deferred` (step, lock path, seconds waited, count, limit), skips that job for this cycle and keeps the invocation running. Bound: 6 per task and job, reset on success and per invocation; the seventh loss raises the original error.
- **Startup.** `reconcile_startup` retries only the contended call, in place and with the same arguments, up to 6 times with a 3 s wait, journaling `startup_deferred`. Re-running the whole reconciliation was rejected because it would lose outcomes already persisted and change the branch a ticket takes. Past the bound the original `TimeoutError` ends startup exactly as before.
- **Everything else is unchanged.** An unstamped timeout, or one on another lock path, keeps today's behaviour. Stop paths and `clear` see today's exceptions; the stamp is only an attribute on the unchanged `TimeoutError`.

**Review notes from the coordinating session.**
- `harvest()` has exactly two lock sites: the stamped first transaction, which precedes every write, and the unstamped `_finish_cleanup`. A stamped timeout therefore never follows a recorded harvest, so a retried harvest cannot skip its `job_completed` event.
- The startup retry wrapper binds each ticket's values before building the call and invokes it immediately, so no loop variable is captured late.

**Tests (8):**

| Test | Guards |
|---|---|
| `BackgroundJobLoopTests.test_a_lock_contended_harvest_is_deferred_and_the_job_is_harvested_on_a_later_cycle` | real held lock; the next cycle harvests with the correct receipt; index bytes unchanged between attempts |
| `BackgroundJobLoopTests.test_harvest_contention_beyond_the_bound_raises_the_original_error` | harvest bound |
| `BackgroundJobLoopTests.test_an_unstamped_lock_timeout_after_the_cleanup_began_still_ends_the_invocation` | the refuted `_finish_cleanup` path is unchanged |
| `BackgroundJobLoopTests.test_a_lock_contended_cleanup_retry_is_deferred_and_settled_on_a_later_cycle` | the lost attempt changes no bytes and makes no Docker call |
| `BackgroundJobLoopTests.test_a_lock_contended_startup_harvest_is_retried_in_place_and_the_run_continues` | startup retry in place; exactly one Docker inspect |
| `BackgroundJobLoopTests.test_startup_contention_beyond_the_bound_raises_the_original_error` | startup bound |
| `BackgroundJobMechanismTests.test_only_transactions_that_have_written_nothing_stamp_a_lost_checkouts_lock_wait` | stamp inventory; a raw timeout is unmarked; a mark never matches another path |
| `BackgroundJobMechanismTests.test_startup_retries_a_contended_stop_request_and_quarantine_record_in_place` | quarantine path retried in place; the tree is terminated once |

**Failing-before on `24603b9`** (implementing agent, with two inert shims so the tests import: `JOB_INDEX_LOCK_TIMEOUT_SECONDS`, unused there, and a `stamped_lock_contention` that honestly reads the stamp, which only `launch` sets at `24603b9`): `Ran 8 tests in 131.904s FAILED (failures=7, errors=4)`. The harvest, cleanup-retry and startup-harvest tests hit the three `TimeoutError` tracebacks (`_harvest_jobs -> harvest`, `_harvest_jobs -> settle_cleanup -> _run_cleanup`, `reconcile_startup -> harvest`). Both bound tests fail because nothing is journaled. The inventory test fails 5 of 6 subtests, since only `launch` was already stamped. The quarantine test fails on the missing `lock_retry_limit` keyword. The unstamped-timeout test passes by design.

**Reproduced by the coordinating session** on a fresh worktree of `24603b9` with the agent's identical shim: `Ran 8 tests in 130.208s FAILED (failures=7, errors=4)`, the same counts. Errors: the harvest, cleanup-retry and startup-harvest tests each end on `TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: '...\checkouts.lock'`, and the quarantine test on `TypeError: reconcile_startup() got an unexpected keyword argument 'lock_retry_limit'`. Failures: both bound tests (for example `Lists differ: ['job_launched', 'job_harvest_deferred', ...] != ['job_launched']`) and five inventory subtests (`False is not true`). The unstamped-timeout test passes, as designed. The worktree was removed and pruned afterwards.

**Passing-after on `b42d519`** (implementing agent, working tree immediately before the commit): new tests `Ran 6 tests in 40.523s OK` and `Ran 2 tests in 2.493s OK`; `BackgroundJobLoopTests` `Ran 41 tests in 226.726s OK`; `BackgroundJobMechanismTests` `Ran 34 tests in 49.900s OK`; `test_graph_controller` `Ran 33 tests in 87.202s OK`; `test_post_crew_workflow` `Ran 15 tests in 95.587s OK`; `test_decomposition` `Ran 19 tests in 52.400s OK`; `git diff 24603b9 b42d519 --check` clean. The coordinating session's single run on the combined head is at the top of this comment.

**Deliberately unchanged by the follow-up:** `_finish_cleanup`, `_enforce_stop`, `_mark_spawn_failed`, `clear`, and the planner.

**Follow-up residual risks:**
1. **A same-task relaunch can still end a run.** `_job_gate` treats a completed but unharvested job as imposing nothing. Narrow path: a post-crew task's harvest is deferred, a `sync_candidate` for that task succeeds, the next harvest loses its wait again, and a `post_crew` launch for the same task gets the lock in that cycle; `launch` then refuses with "already has an active background job", which ends the invocation. The path already existed through the `BackgroundJobError` deferral; lock contention makes it more reachable. **Decision: gate the task as `wait_job` while a harvest deferral is pending for its job (small planner change), or accept for now.**
2. A failed or died job with nothing else eligible ends the run `blocked`, as any blocked graph does; its harvest record lands at the next startup.
3. A startup cleanup retry may wait out the container tombstone again; bounded.

### Deliberately left unchanged

- `unity_materialization.materialize_candidate` still holds `checkouts.lock` across the Unity builder and validation. Releasing it mid-transaction would invert lock order against every other caller (checkouts lock, then Source lock) and would need re-verified re-reads before six record writes; it needs its own reviewed change. The current Gauntlet tasks never reach it.
- `apply_decomposition` and the wait kinds keep today's failure path (above).
- `_mark_spawn_failed` is deliberately not deferrable: it runs after a child exists.
- The 10 s launch budget and every other 10 s acquisition outside the allowlist (operator commands, stop and clear paths) are unchanged.
- The abandoned staffing work is not revived; no unrelated change is included.

### Residual risks and decisions needed

1. **Materialization lock hold** (above): the largest remaining hold; recommended as its own reviewed change before real-game tasks that materialize Unity builder output run at concurrency above 1.
2. **No global deferral cap.** The bound is per action. A lock that is busy but keeps moving could let several distinct actions each accrue deferrals; a truly wedged lock still fails loudly.
3. **Test faithfulness.** The launch tests drive the real `background_jobs.launch` against a real held lock. The `sync_candidate` and `auto_approve` tests reproduce the production acquisition from the fixture foreground; the proof that those production sites raise before writing is the per-kind audit in the code comment. The child tests exercise `run_post_crew_workflow` directly rather than a detached child.
4. **`start_worker` is in the allowlist** beyond the originally named kinds; its pre-mutation property was proven and accepted in review.
