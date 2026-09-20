# NSC-1163 worker recovery fix: implementing agent's final report

Received 2026-09-13 about 15:55 UTC, after the agent was resumed following an API outage, and recorded in substance by the coordinating session. The coordinating session's independent verification is recorded separately.

## State at report time

- Committed locally at `aac2555` on `throughput/worker-recovery-fix`. All six required suites completed OK on that commit. The recovery command was not run on NSC-1163.
- After the resume message the agent started no tests and changed no commits. One overlap: its earlier suite chain was still inside `test_background_jobs` when the message arrived and finished on its own at about 578 s, so it probably ran alongside the coordinating session's suites in `C:\nscrev\proof-fixes` for part of that window.
- It removed its base worktree `C:\nscrev\wrf-base` and ran `git worktree prune`. `C:\nscrev\worker-recovery-fix` is clean at `aac2555`. Nothing live was written: the live NSC-1163 record, receipt, artifacts and `launcher.status.json` keep their 08:35-08:38 local mtimes.

## 1. Commit

- SHA `aac2555c5b1a19d898237f8ba4e320ab3181bb9e`, parent `86068e6490c33bb71b025cbe1b6de204859a24af`, not pushed.
- Subject `AssistantControl: retry the worker's terminal write and recover a surviving crew result`, ending with the Co-Authored-By line.
- `__main__.py` +15/-0, `crew_worker.py` +59/-2, `graph_controller.py` +65/-10, new `worker_recovery.py` +266, new `test_worker_recovery.py` +962. `git diff --check` clean; all five files `i/lf w/crlf`.
- Cherry-picked unchanged into the combined proof branch `throughput/worker-and-decomposition-fixes` as `f5b6ba0`, beneath `ade5bca50d452b276a32f31a7ad8baeb770b2404`.

## 2. What changed

### Change 1: retry only the final terminal write (`crew_worker.py`)

- New helper `locked_record_write` reads three module constants at call time: 6 attempts, 10.0 s per attempt, 2.0 s pause, with the pause behind a `_terminal_write_pause` seam. Tests patch all four, following the `background_jobs` constant pattern.
- It retries only when the acquisition timed out before the lock was held. Both must hold: `background_jobs.stamped_lock_contention(exc, <root>/checkouts.lock)` is true, which requires `_pre_mutation_lock` to have stamped the timeout, and an `entered` flag shows the write body never started, so even a stamped timeout raised inside the body is not retried.
- Any other exception propagates on first occurrence. After the last lost wait the original `TimeoutError` is raised unchanged, and the launcher writes `child_failed` as before.
- `run_worker` writes through a `persist_terminal` closure that re-reads the record inside the lock. Status, error and receipt are computed once; the crew and bridge are never called again.
- The admission write and the early "stop requested before provider start" write are unchanged. If the early write loses its wait, the record stays `running` and the new routing settles it as `stopped` because `stop.request` exists, with no provider started. If the admission write loses its wait, the record has only its `launch` block, which routing settles as failed or stopped. That last path is reasoned from the code, not tested.

### Change 2: settle a confirmed-dead worker (`graph_controller.py`)

- New `_unreleased_worker_action` is used by both `plan()` and `_reservation_owner_action()`; the owner path covers `_resource_overlap_action`, the capacity-full owner branch and the reserve-overlap fallback. It returns `settle_worker` when the status is terminal or `_worker_exit_confirmed` holds, otherwise `wait_worker`.
- `_worker_exit_confirmed` is read-only and requires `worker_control.status` to report `host_identity_alive is False`, its re-read to name the same run with a non-terminal status, and, when the worker has a `job_name`, `windows_job.active_count(job_name) == 0`. A cheap `worker_control.matches` check runs first, so a live host costs one identity check. Any `OSError`, `RuntimeError`, `ValueError`, `TypeError` or `KeyError` during the proof gives `wait_worker`, whose wait still refuses an unverifiable identity.
- Why decide at plan level: settlement keeps its first-priority slot; the dead worker leaves `_watched_workers` (otherwise every other wait returns at once, the spin seen in the incident); both paths agree by construction; `plan()` stays mutation-free. `graph-plan` gains reads only, and the viewer does not call `plan()`.
- Extra edit in `_wait_for_progress`, not listed in the brief: a dead host whose re-read is non-terminal, with a `job_name` and `active_count != 0`, keeps polling within the existing budget. Without it "active tree keeps waiting" is unachievable, because the base wait returns `worker_exited` at once for any dead host.
- Settlement semantics unchanged; the test at `test_background_jobs.py` line 535 is unchanged and passes.

### Change 3: `worker_recovery.recover_result` and `recover-worker-result TASK --run-id --crew-run-id`

- Preconditions checked once before and again inside the lock, written through the same `locked_record_write`.
- Writes `_write_terminal(status="succeeded", receipt=verified)` plus `crew_run_id` and a `recovery` block (`schema_version`, `recovered_at`, `crew_run_id`, `prior_status`, `reason`, and `prior_settlement_reason` when present).
- Case (a), running record: capacity stays held, `next_step` `settle_worker`. Case (b), dead-worker settlement: `capacity_released` and `settled_at` kept, `settlement_reason` moved into `recovery`, `next_step` `post_crew`.
- `inspect_result` runs inside the same locked transaction right after the write; on any exception the exact prior bytes are restored atomically and the error re-raised, so the restore can never overwrite a concurrent writer.
- The bridge is built exactly as `run_worker` built it: `crew_worker._bridge_options(config)`, `execution_model` stripped, the worker's `compose_project`, `allow_materialization_bridge` defaulting to True, scope from `candidate._scope`, then `bridge.require(crew_run_id)`.

## 3. Failing-before and passing-after

Base: detached worktree at `86068e6` with only `test_worker_recovery.py` copied in (line-ending-normalized SHA-256 equal to the committed file, `e9a1ed44...`). No shim: `worker_recovery` is imported inside the tests and the retry constants and pause seam are patched with `create=True`, so base ignores them. Command `python -m unittest --durations 30 -v Pipeline.AssistantControl.test_worker_recovery`. Base: `Ran 28 tests in 112.501s`, `FAILED (failures=4, errors=55)` including subtests. After: `Ran 28 tests in 304.000s OK`.

| Test | 86068e6 | aac2555 |
|---|---|---|
| test_final_write_outwaits_a_holder_longer_than_one_lock_attempt | ERROR `TimeoutError: timed out after 10s ...checkouts.lock`, the incident failure | OK |
| test_exhausted_final_write_raises_the_original_timeout_and_leaves_the_record_running | FAIL: strerror `10s` differs from `0.1s`, no bounded retries; weaker proof, base also raises and leaves `running` | OK |
| test_a_failure_inside_the_locked_write_is_raised_once_and_never_retried | OK, regression guard | OK |
| test_confirmed_dead_worker_with_an_empty_tree_is_settled_instead_of_waited_on | FAIL: plan emitted `wait_worker` | OK |
| test_confirmed_dead_worker_with_a_stop_request_settles_as_stopped | FAIL: plan emitted `wait_worker` | OK |
| test_a_dead_host_whose_job_tree_is_still_active_keeps_waiting | FAIL: `action_limit_reached` instead of `worker_still_running` | OK |
| test_a_live_host_keeps_waiting_within_the_bounded_wait | OK, guard | OK |
| test_an_unverifiable_host_identity_still_refuses | OK, guard | OK |
| 19 WorkerResultRecoveryTests, from recovering a running record through the CLI forwarding test | ERROR `ImportError: cannot import name 'worker_recovery'`; weak proof, module absent | OK |
| test_cli_refusal_exits_nonzero_and_changes_nothing | ERROR `SystemExit: 2`, argparse has no such command | OK |

## 4. Suite results on aac2555, sequential, all seen to complete

| Suite | Result |
|---|---|
| test_worker_recovery | Ran 28 tests in 304.000s, OK |
| test_crew_worker | Ran 16 tests in 166.451s, OK |
| test_worker_settlement | Ran 9 tests in 86.440s, OK |
| test_worker_launcher | Ran 12 tests in 173.577s, OK |
| test_graph_controller | Ran 33 tests in 196.218s, OK |
| test_background_jobs | Ran 81 tests in 578.468s, OK |

## 5. Corrections to the brief and residual risks

Corrections and deviations:

- The events journal has 1985 `wait_worker` event lines for NSC-1163, about 990 wait actions, not "hundreds".
- The lock really was contended at the time: NSC-1168's `scope` action started 13:38:33.75, lost its own 10 s wait (deferred 13:38:46.54), and its retry at 13:38:50.95 succeeded. The agent infers the new 70 s bound would have covered NSC-1163's write; it did not identify the holder.
- Live evidence re-checked read-only: `identify(42248)` returns None, the job's `active_count` is 0, both artifact hashes match the receipt, no stop request exists, the checkout HEAD equals `source_commit` and the checkout is clean.
- `job_name` is mandatory for recovery, unlike the brief's "(if job_name)": `settle_completed` waives the tree-exit proof only for `succeeded` records it assumes the host wrote, and a recovered record has no such guarantee, so recovery must prove the tree is gone. Real workers always have a `job_name`.
- Job-less running workers are never routed to settlement; `worker_control.status` already raises for an incomplete `running` identity.
- Extra recovery preconditions beyond the brief: no registered candidate; owned paths match via `_worker` and the fresh read equals the verified record; `compose_project` matches the run; `error`, `docker_cleanup` and `host_exit_confirmed` must also be absent; case (a) also requires no `settled_at` or `settlement_reason`; the stop request is checked with `lexists`.
- The receipt-versus-worker identity check is defence in depth: with the real bridge a mismatched persisted receipt is already dropped by `_load_current`.
- Test fixture shortcuts: the Source repo, task checkout and scope state are built once per process and copied into each test (about 657 s down to about 263 s); the receipt store is written with the bridge's own `_persist` using a fixture scope stub; recovery itself always rebuilds the real scope.

Residual risks:

- `plan()` now performs read-only process and job observations, running a full status call (git and possibly `inspect_result`) only for workers whose host is gone, so `graph-plan` output can vary with process state, as `_job_gate` already does.
- An `active_count` error inside the wait, for a dead host with a non-terminal record, now stops the run instead of reporting `worker_exited`.
- A lock held longer than the ~70 s bound still produces `child_failed`, but routing plus recovery now resolve it.
- A Ctrl+C during a retry pause escapes, as it would have during the old wait.
- `crew_worker` now imports `background_jobs`, including private `_pre_mutation_lock`, at worker start.
- `DEAD_WORKER_SETTLEMENT_REASON` duplicates the literal in `worker_settlement.py`; a test settles through the real function and asserts equality.
- A recovered record's `finished_at` is the recovery time; the crew itself finished at 13:38:32Z per `stderr.log`.
- Host and tree checks are point-in-time, re-checked under the lock, the same assumption settlement makes.
- Recovery does not take the graph-controller lock. Case (a) is safe beside a running pre-fix controller, which then settles it through the normal `succeeded` path.

## 6. Proposed documentation (README.md, after the `settle-worker` paragraph)

> A worker whose host dies before recording its own terminal status is no longer waited on forever. When the worker's host identity is confirmed gone, the re-read record is still the same non-terminal run, and its Job Object has no active process, the graph controller plans `settle_worker` instead of `wait_worker`. Settlement records the attempt exactly as before (`failed`, "Exited without a completed worker result", or `stopped` when a stop was requested) and releases capacity. An unverifiable host identity still stops the run, and a dead host whose contained tree is still running keeps waiting within the normal worker wait budget. The worker's own final status write waits out a busy `checkouts.lock` (up to six 10 s attempts with a 2 s pause, retried only when the lock was never acquired, never re-running the crew).
>
> `recover-worker-result TASK --run-id RUN --crew-run-id CREW` restores an ExecutionCrew result that survived such a host failure. It refuses, writing nothing, unless the worker is exactly that run with its host and Job Object tree confirmed gone; no stop was requested; the worker never wrote a terminal outcome of its own (still `running` with capacity held, or settled with exactly "Exited without a completed worker result"); the checkout is still at the worker's source commit; and the persisted execution receipt authenticates through the bridge the worker built (same rigor profiles and model), names that crew run and the worker's reservation identity, has status `review_ready` or `materialization_required`, and keeps both artifacts inside the checkout's `Pipeline/ExecutionCrew/outputs`. It rechecks all of this under `checkouts.lock`, records `succeeded` with the receipt, crew run id and a `recovery` block, and restores the previous record bytes if `inspect-result` rejects the result. From a running record, `settle_worker` re-verifies the artifacts and releases capacity next. From a dead-worker settlement the planner resumes with `post_crew`. It never starts a provider, re-runs the crew, approves, integrates, or changes crew artifacts, the execution receipt or another task. A repeat invocation refuses.

## 7. NSC-1163 recovery command (not run by the agent)

From a checkout containing the fix, with `PYTHONUTF8=1`:

```
python -m Pipeline.AssistantControl --source C:\NSC\GauntletFresh1160-Reviewed-Standalone --checkout-root C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts recover-worker-result NSC-1163 --run-id assistant-nsc-1163-18f8332f93f9 --crew-run-id nsc-1163-20260913t133611z
```

Checks, once before the lock and again under `checkouts.lock` just before the write (the first argument checks run once):

1. Valid task id; both run ids non-empty with no surrounding whitespace.
2. `NSC-1163.json` readable, with `task_id`, `source` and `checkout` matching.
3. A `worker` block with `run_id` `assistant-nsc-1163-18f8332f93f9`.
4. No registered `candidate`.
5. None of `receipt`, `crew_run_id`, `finished_at`, `error`, `docker_cleanup`, `host_exit_confirmed`.
6. State (a) `running`, capacity not released, no `settled_at` or `settlement_reason` (the live state), or (b) `failed`, `capacity_released`, reason exactly "Exited without a completed worker result".
7. Every identity field present, including `process_identity`, `stop_request_path` and `job_name`.
8. `worker_control._worker` confirms the owned stop path and job name `assistant-job-7e004a58...`; the fresh read equals the record.
9. Worker task, lease `assistant-nsc-1163-8493baac8ba14c57-lease`, plan `scope-e8933461...8332f93f9`, `source_head` `ff5e328b...` and contract `08266597...` equal the record's scope, `source_commit` and contract.
10. `compose_project` `assistant-crew-c957f9501d3572c377f7`.
11. No `stop.request` at the owned path.
12. `matches(process_identity)` False; an error refuses.
13. `active_count(job)` 0; an error refuses.
14. Checkout HEAD `ff5e328be8aa53813b87ad17f0b9c5334dbb3b6e`.
15. Config names `execution_model` `claude-haiku-4-5-20251001`.
16. `candidate._scope` succeeds: clean checkout on `assistant/NSC-1163`, contract hash at HEAD, registered scope equals scope state.
17. `ExecutionCrewBridge` built with lean/targeted profiles, 900 s timeout, allowlist `claude`, session pool off, that model and compose project, materialization bridge allowed; loads `.task-review-agent\NSC-1163.execution.json`, then `require("nsc-1163-20260913t133611z")` re-hashes `crew_result.json` (`fb554327...`) and `candidate.patch` (`c1a735a2...`).
18. Receipt run id, task, lease, plan, `source_head` and contract equal the worker's.
19. `crew_status` `review_ready` or `materialization_required`.
20. Both artifact paths inside `...\NSC-1163\Pipeline\ExecutionCrew\outputs`.

Then it writes the recovered record and requires `inspect_result(NSC-1163, assistant_run_id=...)` to pass, or restores the prior bytes and raises. Expected live outcome from the current state: case (a), `next_step: settle_worker`, then `post_crew` for `nsc-1163-20260913t133611z` after settlement.
