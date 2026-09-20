# `checkouts.lock` contention: deferral on the controller side, a real wait on the child side

Commit `24603b97cd1a071b3f48d14d15adb1d831f2cf95`, parent
`1dae47bea3625280e27170ea398aef9d881d744f`, branch `throughput/gauntlet-trial-fixes`,
worktree `C:\nscrev\gauntlet-fixes`. One commit, nine files, not pushed, not merged.
`git diff 1dae47b HEAD --check` is clean; the worktree is clean.

## 1. What actually happens (live evidence, read-only)

All timestamps are from
`C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6\.assistant-control\graph-controller-events.jsonl`
and the background-job receipts under the same root. Nothing under `C:\NSC` was
written, and no AssistantControl command was run against it.

`checkouts.lock` is one lock per checkout root, and every record transaction holds
it for the whole transaction. Measured hold, per action kind, over the whole run
(`action_started` to `action_completed`; for these kinds the lock is taken as the
first statement and held to the end, so the action duration *is* the hold):

| kind | n | min | median | max |
|---|---|---|---|---|
| `sync_candidate` | 29 | 9.47 s | 13.82 s | 19.52 s |
| `integrate` | 9 | 7.46 s | 14.83 s | 21.19 s |
| `reserve` | 11 | 4.24 s | 7.33 s | 20.98 s |
| `auto_approve` | 12 | 2.41 s | 4.10 s | 8.71 s |
| `prepare` | 11 | 4.09 s | 5.22 s | 7.09 s |
| `scope` | 11 | 2.20 s | 3.13 s | 4.05 s |
| `settle_worker` | 11 | 1.77 s | 2.22 s | 3.13 s |

Every waiter budgeted 10 s. **Three kinds have a median hold above that budget.**
Four transactions lost the wait in the 22 minutes from 02:37 to 02:56, and two more
later:

1. `post_crew NSC-1163` launch, `action_started` 02:37:47.225Z, `action_failed`
   02:37:57.228Z, `controller_released` 02:37:57.236Z. The NSC-1162 post-crew child
   launched 1.1 s earlier (02:37:46.581Z) was registering its candidate. State
   `blocked` with `last_error`, CLI exit 1, operator runner stopped. Nothing had
   been mutated; every background child kept running and wrote its receipt.
2. `sync_candidate NSC-1163` `action_failed` 02:50:47.425Z — same exception, same
   fatal path.
3. `auto_approve NSC-1162` `action_failed` 02:51:32.893Z — same.
4. `job_failed post_crew NSC-1164` 02:56:22.094Z, receipt of job
   `8b97d834d3aaa42737ddca36ba6ada81ed51ea2eb58eebeb72cd6cf746b192aa`: started
   02:55:07.018Z, failed 02:56:21.933Z, i.e. **74.9 s in** — past registration,
   past the Unity validation, in the transaction that persists the finished
   validation. The controller was running `sync_candidate NSC-1168` from
   02:56:05.729Z to 02:56:22.077Z: a 16.3 s hold.
5. `job_failed post_crew NSC-1173` 03:07:34.169Z, job
   `4ac95f738c10688f...`: launched 03:05:21.538Z, failed 03:07:27.319Z, **125.8 s
   in**, while the controller ran `sync_candidate NSC-1169` from 03:07:16.672Z to
   03:07:34.154Z: a 17.5 s hold.
6. The near-miss that shows the child-side hold exactly: `post_crew NSC-1164`
   `action_started` 02:46:54.359Z, `job_launched` 02:47:03.228Z — an **8.869 s**
   lock wait, 1.1 s inside the budget, immediately after the NSC-1163 child started
   at 02:46:53.986Z. So candidate registration holds `checkouts.lock` for about
   **9.2 s**.

### Why the two fatalities look inconsistent (the coordinator's question)

They are two different paths, and the fourth/fifth events are `job_failed`, not
`action_failed`:

- A **controller action** that raises goes through `_execute_timed`, which journals
  `action_failed` and re-raises; `_run_owned`'s `except Exception` writes
  `_save_state("blocked", error=...)` and re-raises; `run()` propagates it out of
  the `_controller_owner` context (which journals `controller_released` with
  `outcome: "exception"`); and `Pipeline/AssistantControl/__main__.py:498` catches
  `(ValueError, RuntimeError, OSError, subprocess.TimeoutExpired)` — `TimeoutError`
  **is** an `OSError` — prints `{"status": "command_failed", ...}` and returns 1.
  Fatal, every time, for every kind.
- A **background child** that raises writes its own `receipt.json` with
  `status: "failed"` and that error. The controller's `_harvest_jobs` persists the
  terminal observation through `background_jobs.harvest`, journals `job_failed` via
  `_append_job_event`, and the planner then lists the task in `blocked` with reason
  `background_job_failed`. The invocation returns normally with `last_error` null;
  the task stays blocked until an operator runs `clear-background-job` (needed twice
  tonight). Non-fatal to the run, but it destroys the child's work: 75 s and 126 s
  of finished Unity validation in cases 4 and 5.

So the fatality never depended on the action kind, the remaining `next_actions` or
the task being marked blocked. It depended only on whether the exception was raised
in the controller process or inside a child. Both behaviours are now uniform in
their own way: a lock-contended *allowlisted controller action* is always deferred
under the bound, and a child no longer loses that race at all for its two record
transactions.

## 2. Files changed

| file | what |
|---|---|
| `Pipeline/AssistantControl/graph_controller.py` | `LOCK_DEFERRABLE_ACTION_KINDS` with the per-kind proof, `LOCK_DEFERRAL_LIMIT`, `LOCK_DEFERRAL_WAIT_SECONDS`, `_ActionDeferred`, `_checkouts_lock_contention`, `_lock_deferral`, the `_execute_timed` branch, the `_run_owned` handler, `lock_deferrals` in the run result, per-invocation counter |
| `Pipeline/AssistantControl/background_jobs.py` | `LAUNCH_LOCK_TIMEOUT_SECONDS`, `PRE_MUTATION_LOCK_ATTRIBUTE`, `mark_pre_mutation_lock_contention`, `pre_mutation_lock_contention`, and the stamp on `launch`'s single pre-mutation acquisition |
| `Pipeline/AssistantControl/candidate.py` | `REGISTRATION_LOCK_TIMEOUT_SECONDS = 300.0`, used by `register_candidate` |
| `Pipeline/AssistantControl/post_crew_workflow.py` | `VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS = 300.0`, used by `_persist_candidate_validation` |
| `Pipeline/AssistantControl/test_background_jobs.py` | 7 new `BackgroundJobLoopTests`, 4 helpers, an optional `before=` seam on the existing `fake_foreground` |
| `Pipeline/AssistantControl/test_post_crew_workflow.py` | 5 new `PostCrewWorkflowNoUnityBuilderTests`, 3 helpers |
| `Pipeline/AssistantControl/README.md` | one paragraph after the background-job description |
| `Pipeline/AssistantControl/CURRENT.md` | dated entry, 2026-09-13 |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | loop description, items 4 and 5 |

No scheduling change: the planner, the priority order, the Source lane, the job
limit and capacity are untouched. No unrelated refactoring.

## 3. Classification

`_exclusive_file_lock` (`Pipeline/TaskReviewAgent/execution_session_pool.py:190`)
raises `TimeoutError(errno.ETIMEDOUT, f"timed out after {timeout_seconds:g}s
waiting for exclusive file lock", str(path))`. On Windows `errno.ETIMEDOUT` is
10060, which is the `[Errno 10060]` in the journal. `_checkouts_lock_contention`
checks, typed:

1. `isinstance(exc, TimeoutError)`;
2. `exc.errno == errno.ETIMEDOUT`;
3. `exc.filename == str(self.manager.records / "checkouts.lock")` — this checkout
   root's lock only, so a timeout on `assistant-control-integration.lock`, the
   Source registry lock, `decomposition.lock`, `maintenance.lock` or another
   root's records is not this contention;
4. the producer's exact wording as a prefix/suffix pair on `exc.strerror`, not the
   whole message and not the number of seconds (so a shortened budget in a test, or
   a future change of budget, does not change the classification);
5. the action kind is in `LOCK_DEFERRABLE_ACTION_KINDS`;
6. for the two launch kinds only, `background_jobs.pre_mutation_lock_contention(exc)`
   equals that same path.

Point 6 exists because `background_jobs.launch` is the one deferrable path that
takes `checkouts.lock` a **second** time after a durable write: `_mark_spawn_failed`
(`background_jobs.py:498`) runs when `host.handoff` fails, i.e. after the child was
spawned. `launch` now stamps only its first acquisition, at a raise site that is
lexically before the run root, the launch request, the index and the spawn. The
stamp is set on the original exception object with a bare `raise`, so the class,
the errno, the message, the `filename` and the traceback are byte-for-byte what
they are today: a caller that does not know about the stamp (any other caller of
`launch`, the CLI) sees exactly today's `TimeoutError`.

## 4. The allowlist, with the per-kind proof

Verified by reading each entry point at 1dae47b and by a mechanical scan of the
statements before the first `checkouts.lock` acquisition. The only filesystem
effect anywhere before the lock is `records.mkdir(parents=True, exist_ok=True)`,
which `_open_lock_region` performs itself in any case.

| kind | entry point | everything before the lock |
|---|---|---|
| `decompose`, `post_crew` | `graph_controller._launch_job` → `background_jobs.launch:568` | `_job_identity` reads only (`git rev-parse`, `git branch --show-current`, `load_committed_task`, the task record); in `launch`: `validate_task_id`, the kind/invocation/spend/compose checks, two `_json_copy` deep copies, `records.mkdir(exist_ok=True)`. Run root, `launch.request.json`, the index and `host.spawn` are all inside. Second acquisition (`_mark_spawn_failed`) excluded by the stamp. |
| `prepare` | `Checkouts.prepare` (`checkouts.py:39`) | `validate_task_id`, `records.mkdir(exist_ok=True)` |
| `refresh_prepared` | `prepared_refresh.refresh_prepared:102` | argument checks, two path computations. The Source registry lock is nested inside and is a different path. |
| `scope` | `scope.AssistantScopePlanner.validate_and_persist:82` | in `_execute_foreground`: `load_committed_task` and `scope_plan` (reads a JSON override file or computes the plan — no writes); in the method: `validate_task_id`, the lease check, `_plan_from_input` |
| `reserve` | `admission.reserve:252` | argument checks, `_source_registry_paths` (path computation). Registry lock nested inside. |
| `start_worker` | `worker_launcher.start:157` | `_json_config`, `require_reservation` (reads the registry and the record under its own `checkouts.lock`, writes nothing — so that acquisition is pre-mutation too), `_run_root` (computes a path; no `mkdir`), four more path computations. The run root and `launch.request.json` are created inside. |
| `settle_worker` | `worker_settlement.settle_completed:23` | `validate_task_id`, `_source_registry_paths` |
| `sync_candidate` | `source_update.synchronize_candidate:275` | argument checks, three path computations. `_source_integration_lock` and the registry lock are nested inside. |
| `auto_approve` | `review.ReviewGate.approve_validated_gauntlet:179` | in `_execute_foreground`: record reads and `ValueError` guards; in the method: one import and the message check |
| `integrate` | `review.ReviewGate.integrate:211` | the lock is the method's first statement |

Excluded, keeping today's exact failure path:

- **`apply_decomposition`** — it never acquires `checkouts.lock` at all. `apply`
  takes `_source_integration_lock(manager.source)` first and `_apply_locked` writes
  the record under it. A timeout it produced would be on a different path and is
  already excluded by the path check; listing the kind would be a lie.
- **`wait_worker`, `wait_job`** — the acquisitions reachable from
  `_wait_for_progress` are inside `background_jobs.harvest` (which exists to
  persist a terminal observation), `_finish_cleanup`, `_run_cleanup` and
  `_record_final_recheck` (which record the outcome of a Docker removal that has
  **already happened**). Deferring any of those would lose durable facts.
- Everything else is unproven and therefore unchanged.

`start_worker` is an addition to the list the brief and the coordinator named; it is
included because the coordinator's rule is "every action whose lock acquisition
precedes any durable write", it is provable, and `reserve`/`start_worker` are
frequent (a `reserve` took 20.98 s in this run). Flagging it explicitly so the
reviewer can drop it if they want a narrower list.

## 5. The bound and the wait

- `LOCK_DEFERRAL_LIMIT = 6` consecutive deferrals of the **same action** (keyed by
  the canonical JSON of the action dict, so a different action has its own count).
  The 7th attempt raises the original error, journals `action_failed`, writes
  `last_error`, sets state `blocked` and exits 1 — byte-identical to today.
- `LOCK_DEFERRAL_WAIT_SECONDS = 3.0`, taken through the controller's own `sleep`
  (so the fixture clock drives it in tests and no real time is burned). With a 10 s
  lock budget that is ~13 s per cycle and ~80 s of contention before the run fails.
  Once the lock is free the action starts at most 3 s later than it otherwise would.
- The count is reset when the invocation starts (`_controller_owner`) and when the
  action finally runs, so a restarted controller carries no deferral state and the
  bound is per invocation, as required.
- An operator stop is still honoured between deferrals: `continue` returns to the
  top of the loop, which checks `_bound_stop_request()` before planning.
- A deferral does not consume `max_actions`, so `run-graph --once` still performs
  its one action after a deferral rather than returning empty-handed.

## 6. The other side of the race: which child-side call sites take the lock, and for how long

A `post_crew` child's work is `background_jobs._run_kind` → `run_post_crew_workflow`.
The child wrapper itself takes no lock (it reads the record directly and writes its
receipt and progress with `write_record`, which is a temp-file + `os.replace` and
takes no lock). The lock sites are exactly three:

1. **`candidate.register_candidate`** (`candidate.py:215`). Holds the lock for the
   whole registration: record read, scope reconstruction, `bridge.require`, the
   candidate commit through `LocalCandidateCommitter`, and the record write.
   **Measured hold ≈ 9.2 s** (from the 8.869 s wait a competing launch survived at
   02:47:03.228Z, and >10.6 s in the 02:37:57Z failure). It does **not** span Unity
   validation.
2. **`post_crew_workflow._persist_candidate_validation`** (`post_crew_workflow.py:91`).
   Short by construction — record read, candidate re-verification, one write — and
   the **validation runs with the lock released** (that structure already existed at
   1dae47b; it is now covered by a regression test). This is where cases 4 and 5
   died: it asked for 10 s while a foreground `sync_candidate` held the lock for 16.3 s
   and 17.5 s respectively, and threw away 75 s and 126 s of completed Unity work.
3. **`unity_materialization.materialize_candidate`** (`unity_materialization.py:288`).
   This one **does** span the Unity work: it holds `checkouts.lock` across
   `run_door_prototype_builder` (bound `timeout_seconds=1800`) *and* the validation
   runner — minutes. It is not exercised by the current Gauntlet tasks (their scope
   registers no Unity-serialized generated asset, so `generated_paths` is empty and
   `materialize_candidate` is never called), which is why it does not appear in
   tonight's evidence. **Not changed here**, deliberately — see §9.

### Is 10 s the right number?

No, and not because of the tail: the **median** hold of `sync_candidate` (13.8 s),
`integrate` (14.8 s) and the max of `reserve` (21.0 s) all exceed it. A budget large
enough to cover them would have to be ~25 s, and `materialize_candidate` can hold
for minutes, so no finite budget is a correct answer for a waiter that has an
alternative. The controller has an alternative — re-plan — so it keeps its 10 s
budget and defers; the budget was **not** lengthened. A child has no next planning
cycle, and the two transactions above have either nothing to lose (registration) or
everything to lose (the persist), so those two now wait `300.0 s`. That is bounded,
it is above every observed non-materialization hold by more than an order of
magnitude, and `_exclusive_file_lock` already retries the acquisition every 50 ms
until its deadline, so a longer budget *is* the bounded retry the coordinator asked
for — an outer retry loop would only re-enter the same wait. The persist still
re-verifies the exact candidate commit on acquisition and refuses one that changed,
and refuses a failure-persist after review state advanced, so the longer wait
weakens no fail-closed guarantee.

## 7. Tests

Seven in `Pipeline/AssistantControl/test_background_jobs.py` `BackgroundJobLoopTests`
(real planner, real `checkouts.lock` held by a fixture thread, fixture children,
fixture clock) and five in
`Pipeline/AssistantControl/test_post_crew_workflow.py` `PostCrewWorkflowNoUnityBuilderTests`
(real Git fixture, fixture bridge/committer/validation runner).

| test | proves |
|---|---|
| `test_a_lock_contended_launch_is_deferred_and_launches_on_the_next_cycle` | (a) `action_deferred` journaled with task/kind/`lock_contention`/lock path/seconds waited/count/limit; `action_failed` absent; state `running` with `last_error` null at the deferral; no index, no run root, no launch; task not blocked; the launch succeeds on the next cycle; exactly one child; the run result's `lock_deferrals` equals the journal |
| `test_lock_contention_beyond_the_bound_fails_with_the_original_error` | (b) exactly 6 `action_deferred` then `action_failed`; `TimeoutError` with `errno.ETIMEDOUT` and the lock path propagates out of `run()` (which is what makes the CLI exit 1); state `blocked` with `last_error` starting `TimeoutError: [Errno `; nothing launched |
| `test_an_action_kind_outside_the_allowlist_still_fails_on_the_same_timeout` | (c) the allowlist's exact contents; its disjointness from `apply_decomposition` and the wait kinds; an excluded kind fails on the first identical timeout with zero deferrals |
| `test_a_deferred_launch_leaves_no_ticket_index_or_run_root` | (d) at every one of the 6 deferrals and after the fatal attempt: no index, no run root, no `candidate-receipts`, no launch, and the task record byte-identical |
| `test_a_lock_contended_sync_candidate_is_deferred_not_fatal` | a foreground Source-lane action is deferred and then runs (case 2) |
| `test_a_lock_contended_auto_approve_is_deferred_not_fatal` | the same for case 3 |
| `test_a_childs_own_lock_timeout_stays_a_harvested_job_failure` | both fatality paths: a child's identical timeout is still `job_failed`, blocks only its task with `background_job_failed`, produces no `action_deferred`/`action_failed`, and the invocation returns with `last_error` null |
| `test_a_child_whose_first_registration_lock_attempt_times_out_still_completes` | the registration transaction asks for the long budget (spied exactly) and survives a holder that would have beaten a 10 s wait; the child completes and its facts persist |
| `test_a_registration_lock_held_past_the_bound_fails_with_the_original_error` | registration is still bounded; no candidate was written |
| `test_validation_runs_with_the_checkout_lock_free_and_the_persist_outwaits_it` | the lock is free for the whole validation (a 0.1 s acquisition inside the runner succeeds); the persist asks for the long budget and survives a busy lock |
| `test_a_lock_held_past_the_persist_budget_fails_loudly_and_retains_state` | the persist is bounded; on failure no validations and no failure record are written |
| `test_the_persist_refuses_when_the_candidate_changed_underneath` | the re-lock re-verifies identity: a candidate replaced during validation is retained and the persist refuses |

### Failing-before on 1dae47b

`git worktree add --detach /c/nscrev/before-1dae47b 1dae47b`, both final test files
copied in. The bare copy cannot import (`ImportError: cannot import name
'LOCK_DEFERRABLE_ACTION_KINDS'`), which proves nothing about the defect, so the four
new names were then added to that throwaway worktree as **inert constants only** (no
behaviour: `launch`, `register_candidate` and the persist still used their literal
`10`). Per-test verdicts there:

```
A launch that cannot take `checkouts.lock` is re-planned, not fatal. ... ERROR
The bound keeps a wedged lock loud: exactly today's failure after N deferrals. ... FAIL
Only proven pre-mutation kinds are deferrable; everything else is unchanged. ... ok
Every deferral, and the fatal attempt after the bound, wrote nothing. ... FAIL
A foreground Source-lane action is deferred too (20260913, 02:50:47Z). ... ERROR
The other observed foreground casualty (20260913, 02:51:32Z). ... ERROR
The child side keeps its own path: a failed job, not a deferral. ... ERROR
A detached child must not become a failed job because the lock was busy. ... FAIL
The persist is bounded: a wedged lock is still an error, never a silent loss. ... ok
The registration wait is bounded: a wedged lock is still loud. ... FAIL
The lock is free during validation, so re-acquiring it reverifies the candidate. ... ok
A finished validation is never discarded because the lock was busy. ... FAIL
Ran 16 tests in 116.357s
FAILED (failures=5, errors=4)
```

The (a) test's failure is the live defect, reproduced verbatim:

```
File "...\before-1dae47b\Pipeline\AssistantControl\background_jobs.py", line 542, in launch
  with _exclusive_file_lock(manager.records / "checkouts.lock", timeout_seconds=10):
TimeoutError: [Errno 10060] timed out after 10s waiting for exclusive file lock: '...\checkouts\.assistant-control\checkouts.lock'
```

Three of the twelve pass before, correctly and by design: the allowlist-gate test
and `...persist is bounded...` assert behaviour that must **not** change, and
`...reverifies the candidate...` is a regression guard for a property that already
existed at 1dae47b. The remaining nine fail before and pass after. The worktree was
removed with `git worktree remove --force` and `git worktree prune`; `git worktree
list` no longer shows it.

### Exact result lines after the fix (committed tree)

```
### the 12 new tests
Ran 12 tests in 48.887s
OK

### Pipeline.AssistantControl.test_background_jobs.BackgroundJobLoopTests
Ran 35 tests in 191.170s
OK

### Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 86.472s
OK

### Pipeline.AssistantControl.test_decomposition
Ran 19 tests in 55.958s
OK

### Pipeline.AssistantControl.test_post_crew_workflow
Ran 15 tests in 108.140s
OK
```

Also run, because `background_jobs.launch` and `candidate.register_candidate`
changed: `Pipeline.AssistantControl.test_background_jobs` (all classes, including
the real detached-child tests) `Ran 67 tests in 278.141s OK`;
`test_candidate` + `test_unity_materialization` `Ran 15 tests in 96.419s OK`;
`test_gauntlet_replay` + `test_review` `Ran 13 tests in 57.617s OK`.

`git diff 1dae47b HEAD --check` → clean (no output).

## 8. Fail-closed guarantees preserved

- No new durable state, no schema change, no new file. `action_deferred` is a new
  journal event; `lock_deferrals` is a new key in the run result. `graph-controller.json`
  gains nothing.
- A deferral never marks a task blocked, never writes `last_error`, never counts as
  a completed action or a mutation, and never appears as `action_failed`.
- Every non-allowlisted exception, and every allowlisted exception that is not this
  exact contention, takes the unchanged path.
- Beyond the bound the original exception object propagates, so `action_failed`,
  `last_error`, `controller_released` with `outcome: "exception"` and CLI exit 1 are
  unchanged.
- A duplicate child is impossible even if the classification were wrong: `launch`
  refuses a second live job per task, and the planner emits `wait_job`, not a second
  launch, while a ticket is active.
- The child-side budgets only lengthen a wait. The waiter holds nothing while it
  waits, and every identity check on acquisition is unchanged.

## 9. Residual risks and what I did not do

1. **`materialize_candidate` still holds `checkouts.lock` across Unity.** This is
   the largest remaining hold in the system (up to the 1800 s builder bound plus the
   validation) and no waiter's budget can cover it; the controller-side deferral does
   not help either, since 6 × 13 s ≈ 80 s of deferral would be exhausted and the run
   would fail loudly. I did not change it because the minimal fix is not provably
   safe: the function acquires `checkouts.lock` **first** and then
   `_source_integration_lock` and the Source registry lock inside it. Releasing the
   checkout lock for the Unity window and re-acquiring it while still holding the
   Source lock inverts that order against every other caller (which goes
   checkouts → source), so two processes could deadlock — bounded, so both would time
   out rather than hang, but that is a new failure mode. It also needs a re-read and
   re-verify before each of six `write_record` sites that currently write an
   in-memory snapshot taken before the Unity run (`_finalize`,
   `_record_materialization_failure`, `_finalize_validation_failure`, three journal
   writes). Recommended as its own reviewed change: restructure to
   source-lock → checkouts-lock ordering, or move the record writes behind a
   re-verified transaction keyed on the journal's already-pinned
   `original_candidate_commit` / `original_candidate_tree` / `task_contract_sha256`.
2. **A long deferral chain across many distinct actions.** The bound is per action.
   With a wedged lock the planner returns the same action every cycle (nothing
   changes state), so the bound fires after ~80 s; but if records keep changing under
   a busy-but-moving lock, different actions can each accrue up to 6 deferrals. There
   is no global per-invocation deferral cap. In practice a truly wedged lock also
   fails `_harvest_jobs` (which takes the same lock inside `harvest`) and that
   exception is not deferrable, so the run still ends loudly. Worth a global cap if
   the reviewer wants belt and braces.
3. **`start_worker` in the allowlist** is beyond the requested list (§4).
4. **Test faithfulness.** The launch tests drive the real `background_jobs.launch`
   against a real held lock. The `sync_candidate`/`auto_approve`/`apply_decomposition`
   tests reproduce the production acquisition (same helper, same path, same exception
   object shape) from the fixture foreground rather than running the real
   `synchronize_candidate`/`ReviewGate` against a full candidate fixture; the proof
   that those production sites raise before writing is the audit in §4, restated in
   the code comment. The child-side tests exercise `run_post_crew_workflow` directly,
   not a real detached child, so "still completes with a receipt" is proven at the
   workflow-result level (the receipt is written by the unchanged child wrapper).
5. **`_mark_spawn_failed` can still mask a handoff error** with a `TimeoutError` on
   the same lock, after a child was spawned. Pre-existing, deliberately left alone,
   and deliberately *not* deferrable.
6. **Attribution.** The brief asked for `Co-Authored-By: Claude Fable 5.1`. The
   commit carries `Co-Authored-By: Claude Opus 5 (1M context)
   <noreply@anthropic.com>`, which is this session's actual model and the attribution
   the harness mandates for commits it creates (it states it replaces earlier
   attribution guidance). Given that this project verifies authorship rather than
   trusting it, signing as a model I am not seemed worse than the mismatch. Amend the
   trailer if Fable 5.1 was intended literally.
7. **Nothing was run against the live run.** No writes under `C:\NSC`, no
   AssistantControl command, no Docker, no GitHub, no push, no merge. The live run
   is still going (last journal event 03:19:52Z at the time of writing) and is
   unaffected by this branch.


## 10. Follow-up commit: per-cycle harvest, cleanup retries, startup

_Commit `b42d5197d006149f25cfa354f168deebeba1c151`, parent `24603b97cd1a071b3f48d14d15adb1d831f2cf95`, branch `throughput/gauntlet-trial-fixes`. Section appended by the coordinating session from the implementing agent's final message, because the agent's own report writes were refused._

### The gap, reproduced at 24603b9

`_harvest_jobs` runs at the top of every cycle, outside `_execute_timed`, and caught only `BackgroundJobError`. A lock timeout is an `OSError`, so it escaped and ended the run (`blocked`, exit 1). `_reconcile_startup` re-raised it as well. The failing-before run hits all three raise points: `_harvest_jobs -> harvest:1554`, `_harvest_jobs -> settle_cleanup -> _run_cleanup:1384`, and `reconcile_startup:2000 -> harvest:1554`.

### Mechanism

One helper, `_pre_mutation_lock`, marks a lost wait on the exception and re-raises it unchanged; it never marks an exception raised from the body. `stamped_lock_contention(exc, path)` accepts only a `TimeoutError` with `ETIMEDOUT`, that exact filename, the producer's wording and a stamp naming that path. The stamp proves only that the innermost transaction wrote nothing, so every caller that retries on it must also prove the retried call restarts from durable state; that proof is in the code comments. Stop paths and `clear` see exactly today's exceptions. `launch` now uses the same helper with no behaviour change, and the first commit's launch tests still pass.

### Lock acquisitions reachable from `_harvest_jobs` (line numbers at b42d519)

| Acquisition | Verdict | Why |
|---|---|---|
| `harvest` first transaction, 1619 | stamped | Only an outcome check precedes it; the status write, refusal, cleanup begin and index write are all under the lock. |
| `_run_cleanup` begin, 1440 | stamped | Each pass acquires before this call's writes and before the unlocked Docker work; a pass that only finds a live owner writes nothing. |
| `_record_final_recheck`, 1508 | stamped | A single read-verify-write transaction whose first statement is the lock. |
| `_finish_cleanup`, 1319 | refuted, unstamped | The cleanup generation's begin is already written and its Docker reconciliation, possibly `docker rm`, has already run; deferring would lose the durable record of work that happened. |

Earlier transactions inside the same `settle_cleanup` call have each recorded their outcome, and both `harvest` and `settle_cleanup` re-read the index and decide every step from it, exactly as a restarted controller does, so the harvest can be deferred safely.

Behaviour: the controller journals `job_harvest_deferred` with `reason: lock_contention`, a `step` (`harvest` or `settle_cleanup`), lock path, seconds waited, deferral count, limit and `detail`; it skips that job for the cycle and continues. The bound is 6 per `(task_id, job_id)`, reset on success and per invocation; the seventh loss raises the original error. An unmarked timeout, or one on another lock path, raises immediately. The existing `BackgroundJobError` variant of `job_harvest_deferred` is unchanged.

### Startup, retried in place

Re-running the whole of `reconcile_startup` would lose outcomes already persisted and would take the terminal branch for a ticket it had just harvested; skipping the ticket is not allowed because `_require_verified` must hold before the first plan. `reconcile_startup(..., lock_retry_limit, lock_retry_wait_seconds, on_lock_retry)` therefore retries only the contended call with the same arguments; the defaults of 0 keep today's behaviour for every other caller.

| Call site | Verdict |
|---|---|
| terminal-branch `settle_cleanup` | retried in place |
| harvest branch: `harvest`, then `settle_cleanup` | retried in place |
| quarantine `request_stop` (1729) | stamped and retried: its lock is its first effect, a repeat re-verifies an existing request, and it precedes anything irreversible |
| quarantine and unauthenticated `_record_reconciliation` (2163) | stamped and retried: single read-verify-write transaction |
| `_enforce_stop` (its own lock at 1804) | refuted, never wrapped: it terminates the tree and whether it can repeat depends on host process state, not durable records; a marked timeout from the harvest or cleanup inside it propagates unchanged |
| `host.adopt`, `authenticate_index`, `observe` | not lock sites |

The controller passes limit 6 and a 3 s wait and journals `startup_deferred` (task, kind, job, `step`, reason, lock path, seconds waited, count, limit, error). Past the bound the original `TimeoutError` propagates and the run ends `blocked`, exit 1, as before. The run result gains `harvest_deferrals` and `startup_deferrals`.

### Tests (6 in `BackgroundJobLoopTests`, 2 in `BackgroundJobMechanismTests`)

- Harvest deferred, then harvested next cycle: a real held lock yields `job_harvest_deferred`; the run continues through `auto_approve` and `integrate`; the next cycle harvests with the correct `receipt_sha256`; the index bytes are identical between the two attempts.
- Harvest past the bound: 6 deferrals, then the original error, state `blocked`, index still `running`.
- Unmarked timeout after cleanup began: with the real 10 s budget `_finish_cleanup` times out unmarked and the run ends as before; the index shows `completed` with cleanup `in_progress`.
- Cleanup retry deferred, then settled: the `_run_cleanup` begin loses its wait, then `job_container_verified` next cycle; the lost attempt changed no bytes and made no Docker call.
- Startup harvest retried in place: `startup_deferred`, then `job_completed`, and planning continues; exactly one Docker inspect.
- Startup past the bound: `controller_started`, 6 x `startup_deferred`, `controller_released`, original error.
- Stamp inventory: `launch`, `harvest`, `_run_cleanup`, `_record_final_recheck`, `request_stop` and `_record_reconciliation` each raise a marked timeout without changing the index; a raw timeout is unmarked, and a mark never matches another path.
- Quarantine at startup: `request_stop` and `_record_reconciliation` each lose their first wait and are retried in place; the tree is terminated once and the ticket is quarantined.

Failing-before on 24603b9, with two inert shims added (`JOB_INDEX_LOCK_TIMEOUT_SECONDS`, unused there, and `stamped_lock_contention`): `Ran 8 tests in 131.904s FAILED (failures=7, errors=4)`. The harvest, cleanup-retry and startup-harvest tests hit the three `TimeoutError` tracebacks above; the two bound tests fail because no deferrals are journaled; the inventory test fails 5 of 6 subtests (only `launch` was already marked); the quarantine test fails with `TypeError: unexpected keyword argument 'lock_retry_limit'`; the unmarked-timeout test passes by design because it guards behaviour that must not change.

Result lines, on the working tree immediately before the commit (which staged exactly these files; the tree was clean afterwards):

```
new tests: Ran 6 tests in 40.523s OK  |  Ran 2 tests in 2.493s OK
BackgroundJobLoopTests:     Ran 41 tests in 226.726s OK
test_graph_controller:      Ran 33 tests in 87.202s OK
test_post_crew_workflow:    Ran 15 tests in 95.587s OK
BackgroundJobMechanismTests: Ran 34 tests in 49.900s OK
test_decomposition:         Ran 19 tests in 52.400s OK
git diff 24603b9 HEAD --check: clean
```

### Residual risks

1. A same-task relaunch can still end the run. `_job_gate` lets a completed but unharvested job impose nothing, and the loop already plans beside one when harvest raises a `BackgroundJobError`. The narrow path: a post-crew task's harvest is deferred, a `sync_candidate` for it succeeds and clears the validations, the next harvest loses its wait again, and a `post_crew` launch in that cycle gets the lock; `launch` then refuses with "already has an active background job", which is fatal. The path already exists via the `BackgroundJobError` deferral; lock contention makes it more reachable. The planner was not changed. Suggested fix: while a harvest deferral is pending for that job, gate the task as `wait_job`.
2. A failed or died job with nothing else to do returns `blocked` (exit 1, as for any blocked graph), and its harvest record lands at the next startup.
3. A startup cleanup retry may wait out the tombstone again; this is bounded.
4. `_finish_cleanup`, `_enforce_stop`, `_mark_spawn_failed` and `clear` are unchanged by design.
