# P3: worker terminal-write retry and recover-worker-result

## Problem

P3 (NSC-1163, 2026-09-13): `crew_worker.run_worker`'s final terminal write took
`checkouts.lock` with one 10 s wait, outside any retry, on
`Pipeline/AssistantControl/crew_worker.py:255` (base `bdf618744`). Losing that
wait let the host die after a successful crew: the record stayed `running`
without a receipt, the graph controller's `_wait_for_progress` (formerly
`graph_controller.py:1476-1480`) kept planning `wait_worker` for it because it
never checked whether a confirmed-dead worker should instead be settled, and
the controller looped (~990 cycles). Rerunning the crew would overwrite the
only persisted receipt.

**Reproduced** (both behaviorally and via the exact scenario), not theoretical.

## Fix

Cherry-picked `aac2555c5b1a19d898237f8ba4e320ab3181bb9e`, proven live on
2026-09-13 on base `86068e6`, onto local main `bdf618744c5f286d9d4e78e2fe05e244e0366e5f`
in clone `C:\nscrev\worker-final-write-fix`, branch `fix/worker-final-write`.

- `crew_worker.py`: `locked_record_write` retries only a lost first wait for
  the final write (`TERMINAL_WRITE_LOCK_ATTEMPTS=6`,
  `TERMINAL_WRITE_LOCK_TIMEOUT_SECONDS=10.0`,
  `TERMINAL_WRITE_RETRY_PAUSE_SECONDS=2.0`), using the new
  `background_jobs._pre_mutation_lock` / `stamped_lock_contention` to prove the
  lost wait happened before `write()` ran anything.
- `graph_controller.py`: `_wait_for_progress` now polls a watched worker whose
  host is gone but whose Job Object tree is still active, instead of reporting
  `worker_exited` prematurely; `_unreleased_worker_action` /
  `_worker_exit_confirmed` route a confirmed-dead non-terminal worker to
  `settle_worker` instead of `wait_worker` forever.
- `worker_recovery.py` (new) + `__main__.py`: `recover-worker-result TASK
  --run-id ID --crew-run-id ID` records a surviving authenticated
  ExecutionCrew receipt for a dead worker without re-running the crew,
  approving or integrating.
- `README.md`: documents `recover-worker-result` in the per-task subcommand
  section.

### Conflict resolution

One conflict, in `graph_controller.py`'s `_wait_for_progress` docstring and
prologue (~line 1452). Main does not carry the throughput-stack's
`JOB_HARVEST_PENDING` harvest-pause path (`git grep JOB_HARVEST_PENDING main`
= 0 hits), so that docstring paragraph and its
`if action.get("reason") == JOB_HARVEST_PENDING: ...` branch were **dropped**.
Kept P3's own docstring paragraph (a watched worker whose host is gone but
whose Job Object tree is still active) and the `windows_job` import/polling
logic, which applied cleanly with no conflict.

A second symbol gap surfaced only at compile/test time, not in the conflict
markers: the fix's `crew_worker.py`/`worker_recovery.py` import
`background_jobs._pre_mutation_lock` (context manager) and
`background_jobs.stamped_lock_contention` (bool check), which exist at
`86068e6` but not on main — main still uses the older pattern of calling
`_exclusive_file_lock` directly plus manual
`mark_pre_mutation_lock_contention`/`pre_mutation_lock_contention`. These two
helpers are thin, generic wrappers around main's existing lock-stamping
functions, not throughput-stack behavior (they don't touch
`JOB_HARVEST_PENDING` or the harvest-pause path), and P3's own retry loop
needs exactly this API, so both were **ported** into `background_jobs.py`
verbatim from `86068e6`, plus the `errno` import and `Iterator` typing import
they need. Nothing else from the throughput refactor (e.g. converting the
dozen existing `_exclusive_file_lock` call sites to `_pre_mutation_lock`) was
touched.

A third gap surfaced only in the tests: `test_worker_recovery.py`'s
`TerminalWriteRetryTests` and `WorkerResultRecoveryTests` call
`bj.hold_lock(self, lock_path)` (a real-thread lock-holder fixture) which
exists in `86068e6`'s `test_background_jobs.py` but not on main's. Ported
unchanged (test-only fixture, no production behavior) as a second commit.

All symbols the ported diff references (`_bridge_options`, `_compose_project`,
`_now`, `_write_terminal`, `windows_job.active_count`,
`worker_control._POST_EXIT_IDENTITY_FIELDS`/`_worker`, `candidate._scope`,
`worker_control.matches` (imported from `process_identity`), `worker_settlement.settle_completed`,
`result_inspection.inspect_result`, `admission.REGISTRY_SCHEMA`/`_read_registry`/
`_source_registry_paths`, `graph_controller._reservation_owner_action`,
`ExecutionCrewBridge`/`ExecutionCrewReceipt`, `validated_agent_git_identity`)
were individually verified present on main before committing.

## Commits (branch `fix/worker-final-write`)

- `0cb156227828bfe7de62228146324a0b9e635b57` — P3: port worker terminal-write retry and recover-worker-result
- `37a9d7eca58a4c6c9956a3eefbaf08974ed9ffbe` — P3: add hold_lock test fixture for terminal-write retry tests

Base: `bdf618744c5f286d9d4e78e2fe05e244e0366e5f`. Head: `37a9d7eca58a4c6c9956a3eefbaf08974ed9ffbe`.

## Tests

`TEMP`/`TMP` = `C:\nscrev\tmp\worker-final-write`, run sequentially at head:

| Suite | Command | Result |
|---|---|---|
| test_worker_recovery | `python -B -m unittest Pipeline.AssistantControl.test_worker_recovery` | Before hold_lock fix: `Ran 28 tests, FAILED (failures=2, errors=1)`. After: `Ran 28 tests in 54.6s, OK` |
| test_crew_worker | `python -B -m unittest Pipeline.AssistantControl.test_crew_worker` | `Ran 16 tests in 31.1s, OK` |
| test_worker_settlement | `python -B -m unittest Pipeline.AssistantControl.test_worker_settlement` | `Ran 9 tests in 18.3s, OK` |
| test_worker_launcher | `python -B -m unittest Pipeline.AssistantControl.test_worker_launcher` | `Ran 12 tests in 30.4s, OK` |
| test_graph_controller | `python -B -m unittest Pipeline.AssistantControl.test_graph_controller` | `Ran 34 tests in 39.6s, OK` |

`python -B -m compileall -q Pipeline/AssistantControl`: clean.
`git diff --check bdf618744`: clean.
`git ls-files --eol` on all 8 changed files: all `i/lf w/crlf` (blobs are LF).

No pre-existing failures found in any suite at head (all suites are clean once
`hold_lock` was ported).

## Failing-before (base `bdf618744c5f286d9d4e78e2fe05e244e0366e5f`)

**(a) DeadWorkerRoutingTests**, run from a scratch copy of `Pipeline` under
`C:\nscrev\tmp\worker-final-write\base-pkg` with `graph_controller.py` and
`crew_worker.py` restored to base via `git show bdf618744:<path>` (everything
else, including the new `worker_recovery.py`/`test_worker_recovery.py` and
head's `background_jobs.py`/`test_background_jobs.py`, left at head so the
test module imports; those files are strict additions over base, nothing
removed):

`python -B -m unittest Pipeline.AssistantControl.test_worker_recovery.DeadWorkerRoutingTests -v`
→ base: `Ran 5 tests in 6.8s, FAILED (failures=3)` — the 3 failures are exactly
the dead-worker-with-empty-tree, dead-worker-with-stop-request, and
tree-then-empty scenarios, each planning `wait_worker` where head plans
`settle_worker`; the 2 guard tests (live host, unverifiable identity) already
passed on base. Head: `Ran 5 tests in 11.1s, OK` (5/5).
Scratch copy deleted after the run.

**(b) Real-time final-write probe.** A small script
(`probe_final_write.py`, written to `C:\nscrev\tmp\worker-final-write` and
deleted after use since no committed 9/13 probe script exists on disk — only
narrative results in `fixes-1163-1165-verification.md` line 28) reused
`TerminalWriteRetryTests`' real fixture (real Git source, real
`Checkouts`/`AssistantScopePlanner`, a fixture `Bridge`), holding the real
`checkouts.lock` from another thread for 12.5 s (longer than one 10 s wait)
across the final write, with **production** lock constants (no patched
attempts/timeout/pause):

- Base: `TimeoutError: ... timed out after 10s waiting for exclusive file
  lock`, elapsed ~10.8s, worker record left `status: "running"` with no
  receipt, crew ran once (`crew_runs: 1`) — the live NSC-1163 failure.
- Head: succeeded in ~13.2s with the receipt, worker record `status:
  "succeeded"`, crew ran once (`crew_runs: 1`, never re-run).

This matches the 9/13 verification report's "12.5s holder" real-time probe
method and result shape (`fixes-1163-1165-verification.md` line 28).

## Risks and follow-ups

- The ported `background_jobs._pre_mutation_lock`/`stamped_lock_contention`
  are additive; none of main's dozen existing `_exclusive_file_lock` call
  sites were changed to use them, so this PR does not adopt the
  throughput-stack's broader lock-retry refactor — only the two primitives
  P3's own code calls.
- D3 (`eb3beb75`) is a separate port, not included here.
- If Vincent later wants the throughput stack's `JOB_HARVEST_PENDING`
  harvest-pause behavior on main, that is an independent port with its own
  base-vs-main gap analysis; nothing about it was carried over here.
- `preserve-success`/Docker/Unity/live-provider paths were not exercised
  (out of scope, no Vincent go for those runs).

## Independent review (2026-09-17, Pipeline Maintainer Agent)

**VERDICT: APPROVE.** Fresh `pipeline-reviewer` on Fable, range `bdf618744..37a9d7eca`.
- **Port fidelity.** `crew_worker.py`, `worker_recovery.py` and `test_worker_recovery.py` are byte-identical to `aac2555c`. `graph_controller.py` differs from it only by the dropped `JOB_HARVEST_PENDING` branch. The two `background_jobs.py` helpers are verbatim from `86068e6`, and `_exclusive_file_lock` is identical between `86068e6` and main.
- **Retry.** It retries only a typed timeout on the exact lock path, at most 6 x 10 s plus 5 x 2 s. It never retries a write that has already started, and when retries run out it re-raises with the record still `running`, so it stays recoverable. `recover_result` is idempotent, bound to the exact run ids, and confined to the checkout's own files.
- **Tests at head:**
  - `test_worker_recovery` 28, `test_crew_worker` 16, `test_worker_settlement` 9, `test_worker_launcher` 12 and `test_graph_controller` 34 all pass.
  - `test_background_jobs` passes 67. The author's table left this suite out.
- **Failing before:**
  - `DeadWorkerRoutingTests`: 3 of 5 fail at base.
  - `TerminalWriteRetryTests`: 1 failure and 1 error at base.
  - Real-time probe: at base, a 12.5 s lock holder leaves the record `running` with no receipt. At head the worker succeeds with the receipt. The crew ran once in both cases.
- **Minor, not blocking** (`graph_controller.py:1826`): a dead non-terminal worker with no `job_name` counts as exited, and `worker_settlement` then refuses it, so the invocation ends as `action_failed` instead of looping. Only fixture or hand-run workers lack `job_name`, and a visible error is better than a silent loop.

## Second independent review (2026-09-17)

**VERDICT: APPROVE.** The port subagent started this reviewer itself. It reached the same conclusions and reproduced the bug at base in its own clone:
- `DeadWorkerRoutingTests`: 3 failures.
- `TerminalWriteRetryTests`: raises the real `TimeoutError ... timed out after 10s` at `crew_worker.py:255`.

Follow-ups, none blocking:
1. **Docs out of date after merge.**
   - `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md:89` says "a wait returns as soon as any watched worker exits". A dead host with an active Job Object tree is now polled.
   - `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` and `Pipeline/AssistantControl/STATUS.md:31` don't mention the automatic settle of a confirmed-dead worker.
   - Also add `recover-worker-result` to the C:\NSC runbook and the task-orchestrator guide (Documentation Agent).
2. **Operator visibility.** After the retries are used up (~70 s), a lost final write ends `blocked worker_failed`, and the receipt survives. Nothing tells the operator that a result can be recovered. Add an advisory hint in the settle reason or the viewer: "recoverable crew result: run recover-worker-result".
3. **Wording.** The Game Agent's draft merge message said the worker "is recovered". Corrected via message: it is settled as failed, and recovery is the manual command.

## Codex FIX_FIRST (2026-09-17): P3 v2, receipt-to-attempt binding

**Finding (major, reproduced).** Codex's stale-receipt probe
(`C:\nscrev\codex-jobs\codex-review-p3-worker-final-write-merge-20260917-0003\codex-tmp\stale_receipt_probe.py`,
verdict in that job's `CODEX_VERDICT.json`) showed `worker_recovery._verify`
(`worker_recovery.py:95-207` at head `37a9d7eca`) authenticates a persisted
`ExecutionCrewReceipt` against task, lease, plan, source, contract and crew
run id, but never against *which worker attempt* produced it. A crew run's id
is assigned by the crew's own pool assignment
(`Pipeline/TaskReviewAgent/execution_bridge.py:613-618`), independent of the
assistant worker's `--run-id`, so a dead attempt A's surviving receipt could
be handed to `recover-worker-result` with a live, unrelated attempt B's
`--run-id` and would be accepted and routed onto B.

**Binding chosen.** No exact, durable field ties a crew run to one assistant
worker attempt without changing the crew or receipt schema (checked
`crew_worker.py`, `worker_launcher.py` and `execution_bridge.py`; confirmed
`ExecutionCrewReceipt` carries no timestamp and the crew's `run_id` is
pool-assigned, not derived from `--run-id`). Used the smallest sound
substitute instead, both added to `_verify` in
`Pipeline/AssistantControl/worker_recovery.py`:

1. **Time window** (`_require_receipt_within_attempt_window`, called at
   `worker_recovery.py:291` after the receipt and both artifacts are already
   authenticated and path-checked). The crew result file's own mtime
   (`os.stat(receipt.result_path).st_mtime`) must fall at or after this
   attempt's `started_at` — written at `crew_worker.py:224`, *before* the
   bridge ever runs, so it cannot be forged by a lost terminal write — and at
   or before this attempt's `settled_at` (`worker_settlement.py:123`, dead-worker
   path) or `time.time()` (still-`running` path). A 5 s
   `_MAX_CLOCK_SKEW_SECONDS` tolerance absorbs ordinary clock drift between the
   worker host and the crew's filesystem.
2. **Consumption check** (`_require_crew_run_not_already_recorded`, called at
   `worker_recovery.py:129` right after state classification). The requested
   `crew_run_id` must not already appear as `worker.crew_run_id` on any entry
   in `record["worker_history"]` — the immutable archive `worker_launcher.
   _archive_previous_attempt` writes at `worker_launcher.py:112-124` every time
   a new attempt replaces a settled one — so a crew run already claimed by one
   archived attempt can never be claimed by another.

Either check failing raises `WorkerRecoveryError` before any write, and (per
`recover_result`'s existing structure) the same checks run again inside
`checkouts.lock` immediately before the write.

**Tests** (`Pipeline/AssistantControl/test_worker_recovery.py`,
`WorkerResultRecoveryTests`), all using the existing `_OwnedWorkerFixture`:

- `test_refuses_a_receipt_recovered_by_a_worker_attempt_that_started_after_it_was_persisted`
  — the Codex scenario: `started_at` pushed 1 h into the future relative to
  the already-persisted receipt; refused, record and files byte-identical
  (`assert_refused` diffs `record`, `registry`, `scope_state`,
  `execution_receipt`, `result`, `patch`).
- `test_refuses_a_receipt_that_predates_a_settled_attempts_start` — same
  mutation after `settle_completed`'s dead-worker path, exercising the
  `settled_at` branch of the window.
- `test_refuses_a_crew_run_already_recorded_by_a_prior_attempt` — a
  `worker_history` entry pre-recording `CREW_RUN_ID` under a different
  `run_id`; refused.

**Failing-before proof.** `git stash push --keep-index -- Pipeline/
AssistantControl/worker_recovery.py` at head `37a9d7eca` (restores the
pre-fix module, keeps the new tests staged), then:

```
python -B -m unittest Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests.test_refuses_a_receipt_recovered_by_a_worker_attempt_that_started_after_it_was_persisted Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests.test_refuses_a_receipt_that_predates_a_settled_attempts_start Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests.test_refuses_a_crew_run_already_recorded_by_a_prior_attempt
```
→ `Ran 3 tests ... FAILED (failures=3)` — all three succeed wrongly (no
`WorkerRecoveryError` raised), i.e. recovery accepts the stale/consumed
receipt at base. `git stash pop` restored the fix.

**Passing-after (head `247ed4bf5`).**

| Suite | Command | Result |
|---|---|---|
| test_worker_recovery | `python -B -m unittest Pipeline.AssistantControl.test_worker_recovery` | `Ran 31 tests in 63.8s, OK` |
| test_crew_worker | `python -B -m unittest Pipeline.AssistantControl.test_crew_worker` | `Ran 16 tests in 46.9s, OK` |
| test_worker_settlement | `python -B -m unittest Pipeline.AssistantControl.test_worker_settlement` | `Ran 9 tests in 17.5s, OK` |
| test_worker_launcher | `python -B -m unittest Pipeline.AssistantControl.test_worker_launcher` | `Ran 12 tests in 35.0s, OK` |
| test_graph_controller | `python -B -m unittest Pipeline.AssistantControl.test_graph_controller` | `Ran 34 tests in 38.6s, OK` |

`python -B -m compileall -q Pipeline/AssistantControl`: clean.
`git diff --check bdf618744`: clean.
`git ls-files --eol` on both changed files: `i/lf w/crlf` (blobs are LF).
No pre-existing failures found. Clone left with a clean tree.

**Commit.** `247ed4bf54c2d07039920c2767b6029c00cb7e4f` — "P3 v2: bind
recover-worker-result to the requesting attempt's time window", on
`fix/worker-final-write`, base `bdf618744`, prior head `37a9d7eca`, new head
`247ed4bf5`. Touches only `Pipeline/AssistantControl/worker_recovery.py` and
`Pipeline/AssistantControl/test_worker_recovery.py`.

**Not done:** a full two-`run_id` end-to-end simulation (real second
admission, launcher archive, second reservation) was judged out of proportion
to the fix — it would require re-deriving the launcher's full admission/
archive path inside the test fixture. The three tests above exercise the
exact mechanism (`_verify`'s new checks) that such a scenario would hit, via
the lighter, task-sanctioned time-mutation approach.

## Review minor fix (2026-09-17)

**Finding (minor, reproduced), `worker_recovery.py:150`.** The v2 window
check's own `_MAX_CLOCK_SKEW_SECONDS` tolerance is exploitable: a stale result
from attempt A written just 4 s before attempt B's `started_at` still falls
inside B's tolerant window (`persisted_at >= window_start - 5`) and is
accepted as B's, even though A itself was already recorded settled (in
`worker_history`) after that result was written — impossible for a genuine
result of B, since attempts on one reservation run one at a time.

**Fix.** Added a second, skew-free bound, `_require_receipt_not_before_other_
attempts` (`Pipeline/AssistantControl/worker_recovery.py`), called from
`_verify` right after the existing `_require_receipt_within_attempt_window`.
It reads `record["worker_history"]`, finds every entry for an *other* attempt
(`entry["run_id"] != run_id`), and takes the latest of each entry's own
`worker.settled_at` (`worker_settlement.py:123`) or, when a worker copy has
neither, the entry's `archived_at` (`worker_launcher.py:124`). The crew
result's mtime must be strictly greater than that latest time, with **no**
skew tolerance, both timestamps and the receipt's mtime being read from the
same host clock. No history, or no entry with either field, leaves the
existing window check as the sole bound. A helper
`_latest_other_attempt_settlement` computes the bound; both the module
docstring and the new functions' docstrings name it. No new gate applies when
there is no prior attempt, and the legitimate recovery of the current attempt
is unaffected.

**Tests** (`Pipeline/AssistantControl/test_worker_recovery.py`,
`WorkerResultRecoveryTests`):

- `test_refuses_a_result_persisted_before_a_prior_attempts_own_settlement` —
  the reviewer's exact scenario: a `worker_history` entry for another attempt
  settled 1 s after the crew result's mtime, and the current worker's
  `started_at` set to 4 s after that same mtime (inside the 5 s skew
  tolerance). Refused, record and every protected file byte-identical.
- `test_recovers_when_the_result_was_persisted_after_a_prior_attempts_settlement`
  — the same history shape but with the other attempt settled 30 s *before*
  the result's mtime (the ordinary case); recovery still succeeds.

**Failing-before proof.** `git add` the test file, then `git stash push
--keep-index -- Pipeline/AssistantControl/worker_recovery.py` at head
`247ed4bf5` (restores the pre-fix module, keeps the two new tests staged):

```
python -B -m unittest Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests.test_refuses_a_result_persisted_before_a_prior_attempts_own_settlement Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests.test_recovers_when_the_result_was_persisted_after_a_prior_attempts_settlement
```
→ `Ran 2 tests ... FAILED (failures=1)`: the reproduction test raises
`AssertionError: WorkerRecoveryError not raised` (the stale result is wrongly
accepted); the legitimate-recovery test already passes at base, as expected.
`git stash pop` restored the fix with no conflicts.

**Passing-after (new head, this commit).**

| Suite | Command | Result |
|---|---|---|
| test_worker_recovery | `python -B -m unittest Pipeline.AssistantControl.test_worker_recovery` | `Ran 33 tests in 61.6s, OK` |
| test_crew_worker | `python -B -m unittest Pipeline.AssistantControl.test_crew_worker` | `Ran 16 tests, OK` |
| test_worker_settlement | `python -B -m unittest Pipeline.AssistantControl.test_worker_settlement` | `Ran 9 tests, OK` |
| test_worker_launcher | `python -B -m unittest Pipeline.AssistantControl.test_worker_launcher` | `Ran 12 tests, OK` |
| test_graph_controller | `python -B -m unittest Pipeline.AssistantControl.test_graph_controller` | `Ran 34 tests, OK` |

Combined single run of all five modules: `Ran 104 tests in 190.5s, OK`.

`python -B -m compileall -q Pipeline/AssistantControl`: clean.
`git diff --check bdf618744` on both changed files: clean.
`git ls-files --eol` on both changed files: `i/lf w/crlf` (blobs are LF).
No pre-existing failures found. `TEMP`/`TMP` = `C:\nscrev\tmp\p3-v21`. Clone
left with a clean tree after the commit.

**Commit.** One commit on `fix/worker-final-write`, base `bdf618744`, prior
head `247ed4bf5`, touching only `Pipeline/AssistantControl/worker_recovery.py`
and `Pipeline/AssistantControl/test_worker_recovery.py`. Not merged, not
pushed (push URL disabled on this clone).

## Astra-advised receipt binding (2026-09-17)

**Finding (major, reproduced by Codex).** `CODEX_VERDICT.json`
(`codex-review-p3-worker-final-write-v2-20260917`) on head `95d5438e0`: the
v2/v2.1 window still authenticates a mutable, unauthenticated file
timestamp, not *which attempt* produced the receipt. Attempt A's crew
succeeds and its receipt is persisted; A loses its terminal write and is
archived by dead-worker settlement with no `crew_run_id`. A new attempt B
starts on the same reservation. Restoring or merely touching A's unchanged
`crew_result.json` after B starts moves its mtime inside B's window (and
past A's own recorded settlement), and recovery of B then records A's crew
result as B's own. Codex's own probe reproduced this with valid
worker-history timestamps and no content change. Root cause: nothing
durable ever tied a receipt to the one worker attempt allowed to claim it —
only its result file's mtime, which any process can rewrite without
changing a byte the hash covers.

**Design (Astra, `codex-advice-p3-recovery-binding-20260917.report.md`):
option (b), an explicit `assistant_worker_run_id` on the persisted receipt,
written once by the existing receipt write, checked by recovery.** This
replaces the entire mtime scheme rather than adding another timestamp bound
to it — a mutable value cannot be made trustworthy by narrowing its
tolerance further, and Astra's advice explicitly rejected doing so ((a) a
separate marker adds persistence for no better proof; (c) blocking on any
history gap also blocks valid new bindings).

- **The write.** `Pipeline/TaskReviewAgent/execution_bridge.py:204-260`:
  `ExecutionCrewReceipt` gains `assistant_worker_run_id: str | None = None`.
  `to_dict()` (`execution_bridge.py:226-260`) omits the key entirely when
  `None`, so a receipt persisted before this fix, and its `receipt_sha256`,
  hash identically to their original payload — `EXECUTION_RECEIPT_SCHEMA_VERSION`
  stays `"1.0"` as an additive extension. `__init__` gains a same-named
  parameter (`execution_bridge.py:276-303`), stored as `self.assistant_worker_run_id`,
  never itself validated against anything (the caller's own reservation
  already is). `_run_prepared` (`execution_bridge.py:790-834`, the receipt
  construction) is the **only** place a value is ever stamped, and only from
  `self.assistant_worker_run_id` — the bridge instance's own validated
  attempt, never inferred from the crew result. `Pipeline/AssistantControl/crew_worker.py:262-264`
  (`run_worker`): the validated reservation `run_id` is passed straight into
  the bridge constructor as this keyword, outside `_bridge_options`'s
  configurable allowlist (`crew_worker.py:132-146`), so no worker config can
  ever substitute a different value.
- **The read.** `execution_bridge.py:1093-1121` (`_load_current`, the state
  file every bridge for one task shares): the field is read only from the
  loaded JSON payload (`identity.get("assistant_worker_run_id")`), **never**
  from `self.assistant_worker_run_id` — a bridge built for a later attempt
  that merely loads an earlier attempt's persisted receipt must see who
  actually produced it, never itself. Covered by the same
  `receipt_sha256 == semantic_sha256(identity)` check as every other field,
  so a legacy receipt's absence of the key, and a tampered presence of one,
  are both caught the same way as before.
- **The check.** `Pipeline/AssistantControl/worker_recovery.py:242-252`
  (`_verify`, called once before `checkouts.lock` and again inside it by
  `recover_result`'s `write()` closure — i.e. both places the module
  docstring already promised): after the existing artifact-hash and
  crew-status checks, `verified.assistant_worker_run_id` must equal
  `--run-id` exactly; `None` (every receipt persisted before this fix,
  including NSC-1163's own) refuses with "receipt has no bound worker
  attempt", never inferred or manufactured. Removed entirely, replacing the
  whole mtime scheme: `_receipt_persisted_at`,
  `_require_receipt_within_attempt_window`, `_latest_other_attempt_settlement`,
  `_require_receipt_not_before_other_attempts`, `_MAX_CLOCK_SKEW_SECONDS`,
  and the now-unused `_parse_timestamp`. Unchanged: artifact hash/path
  authentication, crew-status gating, and
  `_require_crew_run_not_already_recorded`'s duplicate-consumption check
  (still the only other binding rule recovery applies).

**Compatibility (grepped every receipt reader).** `Pipeline/AssistantControl/candidate.py`,
`Pipeline/TaskReviewAgent/candidate_integration.py` and
`Pipeline/TaskReviewAgent/local_candidate_commit.py` only call `receipt.to_dict()`
or read named attributes — no fixed key-set assertion anywhere. No reader
compares `EXECUTION_RECEIPT_SCHEMA_VERSION`; `reset_task.py` does not touch
`ExecutionCrewReceipt` at all (its own `"assistant-reset-task/v2"` schema
constant is unrelated). A legacy receipt (the key absent) verifies exactly
as before; the new key is additive both to the payload and its hash.

**Tests** (`Pipeline/AssistantControl/test_worker_recovery.py`,
`WorkerResultRecoveryTests`, plus `test_crew_worker.py` and the
TaskReviewAgent smoke test):

- `test_refuses_a_stale_receipt_touched_after_a_new_attempt_started` — the
  reproduced scenario itself: attempt A settles dead (real
  `settle_completed`, no `crew_run_id`, archived into `worker_history`), a
  fresh self-consistent attempt B starts on the same reservation, A's result
  file mtime is pushed an hour forward (exactly what the removed window
  alone accepted), and recovering B is refused
  (`ExecutionCrew receipt is bound to a different worker attempt`) with zero
  writes and every protected byte unchanged.
- `test_refuses_a_receipt_with_no_bound_worker_attempt` — a receipt with
  `assistant_worker_run_id=None` (built through the real `to_dict()`/`_persist`
  path, so it is byte-for-byte what a pre-fix receipt looks like) refuses
  with a distinct message.
- `test_recovers_despite_a_touched_result_and_unsettled_older_history` — a
  correctly bound receipt still recovers with the result file's mtime pushed
  an hour into the past and an older `worker_history` entry carrying an
  unparseable `archived_at` (NSC-1163-era unbound history): neither the
  removed window nor the removed settlement-order check is missed.
- `test_refuses_a_crew_run_already_recorded_by_a_prior_attempt` — kept
  unchanged; the duplicate-consumption rule this fix does not touch.
- Removed (tested only the deleted mtime/settlement-order scheme):
  `test_refuses_a_receipt_recovered_by_a_worker_attempt_that_started_after_it_was_persisted`,
  `test_refuses_a_receipt_that_predates_a_settled_attempts_start`,
  `test_refuses_a_result_persisted_before_a_prior_attempts_own_settlement`,
  `test_recovers_when_the_result_was_persisted_after_a_prior_attempts_settlement`,
  and their shared `_with_prior_attempt_history` helper.
- `test_crew_worker.py::test_runs_once_with_exact_authorization_config_and_receipt`
  — extended: `run_worker` passes `assistant_worker_run_id` to the bridge
  constructor directly, and the value survives both the terminal write and a
  fresh reload of the record from disk.
- `production_pipeline_smoke_test.py::test_execution_receipt_binding_is_never_backfilled_on_load`
  (new, 7th smoke test) — a real `ExecutionCrewBridge` end to end: attempt
  A's bridge produces and persists a bound receipt; a second bridge built
  for attempt B (never running the crew) loads A's receipt unchanged rather
  than rebinding it; stripping the key and re-hashing the payload (a
  synthetic legacy receipt) still verifies with the field reported `None`.
  `prepare_builder_execution` gained an optional `assistant_worker_run_id`
  parameter defaulting to `None`, so its six existing callers are unaffected.

**Failing-before proof.** The whole `WorkerResultRecoveryTests` class
requires the new dataclass field to even construct its fixture receipt
(`setUp` calls `ExecutionCrewReceipt(..., assistant_worker_run_id=self.RUN_ID)`),
so committing the test file first and running it against the pre-fix
modules fails structurally rather than narrowly:

```
git stash push -m "prod fix" -- Pipeline/AssistantControl/crew_worker.py \
  Pipeline/AssistantControl/worker_recovery.py Pipeline/TaskReviewAgent/execution_bridge.py
python -B -m unittest Pipeline.AssistantControl.test_worker_recovery.WorkerResultRecoveryTests
```
→ `Ran 24 tests in 6.7s, FAILED (errors=24)` — every one
`TypeError: ExecutionCrewReceipt.__init__() got an unexpected keyword
argument 'assistant_worker_run_id'`. `git stash pop` restored the fix with
no conflicts. This is itself the proof that no such binding existed at
`95d5438e0`; Codex's own probe (`CODEX_VERDICT.json`, same date) already
demonstrated the concrete exploit — stale-receipt attribution via a touched
mtime alone — against the unmodified head.

**Passing-after (new head, this branch).**

| Suite | Command | Result |
|---|---|---|
| test_worker_recovery | `python -B -m unittest Pipeline.AssistantControl.test_worker_recovery` | `Ran 32 tests, OK` |
| test_crew_worker | `python -B -m unittest Pipeline.AssistantControl.test_crew_worker` | `Ran 16 tests, OK` |
| test_worker_settlement + test_worker_launcher + test_graph_controller | combined with the above two | `Ran 103 tests in 196.3s, OK` |
| test_candidate + test_post_crew_workflow (receipt readers) | `python -B -m unittest Pipeline.AssistantControl.test_candidate Pipeline.AssistantControl.test_post_crew_workflow` | `Ran 32 tests in 104.1s, OK` |
| production_pipeline_smoke_test | `PYTHONPATH=<clone> python -B Pipeline/TaskReviewAgent/tests/production_pipeline_smoke_test.py` | `PASS (7 tests)` |

`python -B -m compileall -q Pipeline/AssistantControl Pipeline/TaskReviewAgent`:
clean. `git diff --check f5217bca1`: clean. `git ls-files --eol` on every
changed file: `i/lf w/crlf` (blobs are LF, no mixed endings). No
pre-existing failures found; nothing skipped. `TEMP`/`TMP` =
`C:\nscrev\tmp\p3-v3`. Clone left with a clean tree after the commits.

**Commits** on `fix/worker-final-write`, base `f5217bca1` (rebased local
main), prior head `95d5438e0`:

1. `5545dd24e` — regression tests for the coming binding (fails structurally
   against `95d5438e0`, per above).
2. `2479d6ba7` — the fix itself: `execution_bridge.py`, `crew_worker.py`,
   `worker_recovery.py`.
3. `a8bdee7cf` — propagation/reload coverage in `test_crew_worker.py` and
   the TaskReviewAgent smoke test.

New head: `a8bdee7cf326246d8bd720bb67c70bd165ede968`. Not merged, not
pushed (push URL disabled on this clone). No provider, Docker, Unity or
live `.assistant-control` record was touched.

## Review minors (2026-09-17)

Three minor findings from an independent Claude Opus review of the branch
(base `3083ee002`, prior head `8911fc71f`), all fixed in one commit.

1. **Run-id reuse defeats the attempt binding.** Worker run ids are not
   guaranteed unique: `worker_launcher.start` only refuses a run id equal to
   the immediately preceding attempt, and the controller derives run ids
   from the plan, so a sequence X, Y, X is possible. Recovering the second X
   could accept the first X's receipt. **Fix:** `worker_recovery._verify`
   now calls a new `_require_run_id_not_reused`, refusing recovery when
   `--run-id` already appears in `record["worker_history"]`, before any
   receipt authentication. **Test:**
   `test_refuses_a_run_id_reused_by_a_later_attempt_on_the_same_task`
   archives run X then run Y through the real
   `worker_launcher._archive_previous_attempt` path, reuses X for a third
   attempt, and asserts recovery is refused with the record unchanged.
   Failing-before evidence (`git stash push --keep-index -- Pipeline/AssistantControl/worker_recovery.py`
   at `8911fc71f`, run the one test, then `git stash pop`): 1 test, 1 error
   (`ResultInspectionError: exactly one retained worker attempt must match
   the requested run`, raised only after `_write_terminal` had already
   written the stale `succeeded` record, which the `write()` `except`
   restored). Passing-after: 1 test, ok.
2. **Stale doc.** `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` line
   89-90 said a wait returns as soon as any watched worker exits. Corrected
   to match `GraphController._worker_exit_confirmed`: a wait returns on a
   proven exit (host confirmed gone and, when recorded, its Job Object tree
   also empty) or a background job ending; a dead host with an active tree
   keeps being polled; a confirmed-dead non-terminal worker is settled by
   the planner instead of waited on. No other wording changed.
3. **Comments named the reviewer.** Reworded the four "Astra-advised
   receipt binding (2026-09-17)" comments in `crew_worker.py` (1),
   `execution_bridge.py` (2) and `worker_recovery.py` (1) to state why the
   binding exists (recovery must prove which attempt produced a receipt),
   with no reviewer name or date. The module docstring's separate inline
   citation in `worker_recovery.py` line 29 was left as-is (different
   phrasing, not a comment naming the reviewer as advising the design).

**Commit:** `acf0d7773` on `fix/worker-final-write`, base `3083ee002`.

**Verify (sequential):**
- `Pipeline.AssistantControl.test_worker_recovery test_crew_worker
  test_worker_settlement test_worker_launcher test_graph_controller`: 104
  tests, ok.
- `Pipeline.AssistantControl.test_candidate test_post_crew_workflow`: 32
  tests, ok.
- `python -B -m compileall -q Pipeline/AssistantControl
  Pipeline/TaskReviewAgent`: clean.
- `git diff --check 3083ee002`: clean.
- `git ls-files --eol` on all 5 changed files: `i/lf w/crlf` (blobs LF).
- `TEMP`/`TMP` = `C:\nscrev\tmp\p3-minors`. Clone left clean.

New head: `acf0d7773`. Not merged, not pushed (push URL disabled on this
clone). No provider, Docker, Unity or live `.assistant-control` record was
touched. Local `main` has moved past base `3083ee002`; rebase is left to
the handoff step per instructions.
