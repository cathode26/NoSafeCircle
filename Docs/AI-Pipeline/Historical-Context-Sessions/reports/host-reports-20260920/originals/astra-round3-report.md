# Round-3 repair of the four NO-GO findings — for Codex / Astra

**Exact commit:** `91a0b0dfd9ad605d39e565b014ea95c099e8d42b`
on `throughput/background-decomposition` in the isolated clone `C:\nscrev\throughput`,
directly on top of `62245a1d9bc0c2c34196f8641cf03aa84a0402fd`.
Not pushed, not merged. No live run, task contract, Unity Asset, Docker object, GitHub
branch or main checkout was touched; no provider was invoked; every Docker interaction
in the tests goes through the fixture Docker CLI.

**Files changed (7):**

| File | What changed |
|---|---|
| `Pipeline/AssistantControl/background_jobs.py` | all four repairs |
| `Pipeline/AssistantControl/graph_controller.py` | findings 3 and 4 (loop defence, `stop-graph` diagnostics) |
| `Pipeline/AssistantControl/__main__.py` | finding 4 (`stop-background-jobs` diagnostics) |
| `Pipeline/AssistantControl/test_background_jobs.py` | 7 new regressions, 2 updated assertions |
| `Pipeline/AssistantControl/README.md` | background-jobs section |
| `Pipeline/AssistantControl/CURRENT.md` | dated round-3 section at the top of the background-job entries |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | numbered item 7 |

---

## Failing-before evidence

Method: `git worktree add --detach /c/nscrev/before-62245a1 62245a1`, the **final**
`test_background_jobs.py` copied in unchanged, only the new tests run there; worktree
removed afterwards. Assertion lines quoted verbatim.

### Finding 1 — a Docker failure after a sighting loses the removal and the renewed bound

`test_docker_failure_after_a_late_sighting_keeps_the_removal_and_the_renewed_bound`

```
AssertionError: Tuples differ: ('refused', ['40fbbf509625f5e8664868ccd24d9158f63da0dc...1f']) != ('refused', [])
First differing element 1:
['40fbbf509625f5e8664868ccd24d9158f63da0dcdfd0b2d6f02956cf55ce031f']
[]
```

On `62245a1` the container was found and removed, Docker then failed on the next call,
and the durable record kept **no** removal at all — so `_finish_cleanup` saw no new
removals and never renewed the tombstone. The bound that expired was the one from
*before* the container appeared.

`test_interrupted_cleanup_keeps_its_removal_durable_and_never_completes`

```
AssertionError: Tuples differ: ('cancelled', 'refused', ['22bfa0af...ff']) != ('cancelled', 'in_progress', [])
First differing element 1:
'refused'
'in_progress'
```

An interrupt between `_begin_cleanup` and `_finish_cleanup` left the record `in_progress`
with the carried (older) deadline and no record of the removal that had already happened.

### Finding 2 — an empty request authenticates; process identity is not checked

`test_empty_or_malformed_launch_request_never_authenticates_a_cleanup`, subtest `request='empty'`

```
AssertionError: 'refused' != 'verified_absent'
- refused
+ verified_absent
```

On `62245a1` a zero-byte `launch.request.json` skipped the hash comparison entirely
(`if request_bytes:` guarded it), the ticket authenticated, and the cleanup went on to
inspect and remove the container. The `truncated` and `malformed` subtests errored on
`KeyError: 'authentication'` (no durable authentication record existed).

`test_process_identity_mismatch_refuses_every_destructive_path`

```
Pipeline.AssistantControl.background_jobs.BackgroundJobError: fixture stop names another Job Object
During handling of the above exception, another exception occurred:
AssertionError: "does not authenticate" does not match "fixture stop names another Job Object"
```

An index carrying its own ticket, run root, Job Object name and container but **another
job's live child** as its PID and process identity passed `request_stop` (a bound stop
request was written), reached `_enforce_stop`, and only the *host* refused, at the
`host.stop(...)` call itself. Nothing in `background_jobs` had compared the recorded PID
or the process identity dict against `launcher.identity.json` /
`child.identity.json` / `job.opened.json` for a stop.

### Finding 3 — a concurrent clear aborts the controller

`test_concurrent_clear_during_cleanup_does_not_abort_the_controller` (loop level)

```
  File "...graph_controller.py", line 1566, in _run_owned
    harvested_jobs.extend(self._reconcile_startup())
  File "...background_jobs.py", line 1457, in reconcile_startup
    _require_verified(label, current, outcomes)
Pipeline.AssistantControl.background_jobs.StartupRefused: NSC-1200 background job 98c5bfcf...:
provider container 'nsc-decompose-98c5bfcf50c9e062bd28c0f8' is not verified absent
(in_progress: None); refusing to plan beside it
```

The clear landed while the exact look ran unlocked; `_finish_cleanup` returned the stale
`begun` record, which still read as pending `in_progress`, and the exception came out of
`controller.run`.

`test_a_concurrent_clear_is_a_cleanup_outcome_not_a_failure` (mechanism level)

```
AssertionError: True is not false        # background_jobs.cleanup_pending(outcome)
```

and the superseded case raised
`BackgroundJobError: background job index changed before container reconciliation`
out of `_run_cleanup`.

### Finding 4 — an unreadable index lets a released stop-graph report success

`test_unreadable_pending_index_never_reports_a_released_stop_graph_as_finished`, all four
subtests (`empty`, `truncated`, `not an object`, `other identity`):

```
AssertionError: 'already_released_cleanup_pending' != 'already_released'
```

Behavioural script on the same worktree (`old_behaviour_finding4.py`, same scenario,
printing exactly what the operator sees), abridged — identical for all four corruptions:

```
--- index empty (...\.assistant-control\NSC-1200.background-job.json) ---
  request_stop status : already_released
  cleanup_pending     : []
  unreadable_indexes  : <absent>
  stop-graph           : exit 0 status already_released | error None
  stop-background-jobs : exit 1 status command_failed | error background job record is unreadable: ...
```

`stop-graph` **exited 0 and reported the graph finished** while a durable job index could
not be read at all; `stop-background-jobs` gave a bare `command_failed` with no structured
diagnostics.

The same script against `91a0b0d`:

```
--- index empty (...) ---
  request_stop status : already_released_cleanup_pending
  unreadable_indexes  : [{'task_id': 'NSC-1200', 'path': '...NSC-1200.background-job.json',
                          'error': 'background job record is unreadable: ...'}]
  stop-graph           : exit 1 status already_released_cleanup_pending
  stop-background-jobs : exit 1 status cleanup_pending | unreadable [{...same...}]
  index bytes unchanged: True
```

---

## Exact behaviour now

### 1. Partial cleanup progress is durable; the bound only moves forward

`reconcile_provider_container` takes a `progress` dict and updates it **in place** with
every observation, every confirmed sighting of its own container and every removal, as
they happen. Any failure inside the watch loop is raised as `ContainerReconcileError`
with that partial record attached; `_reconcile_unlocked` turns it (and any other
exception) into `{"status": "refused", "error": ..., "removed": [...],
"observations": [...], "container_sighted": ...}`. `_run_cleanup` and `harvest` pass the
same dict and, on a `BaseException` (Ctrl+C), call `_finish_interrupted` to record the
same partial result before re-raising.

`_finish_cleanup` then:
- merges removals cumulatively (unchanged);
- treats a **removal or any sighting** as grounds to restart the operation bound;
- writes `tombstone_until_utc = _later_utc(recorded, merged, renewed)` — the latest of
  the three, so no failure, interrupt or stale result can move a deadline backwards;
- sets `final_recheck_at_utc = None` whenever the container was seen, and records
  `container_sighted` on the generation.

`_record_final_recheck` additionally refuses to complete a generation whose
`container_sighted` is true. The record stays `cleanup_pending`, `_stop_result` keeps
`retry_after_utc`, `stop_complete` stays false, and the next retry runs the whole window
again before the final exact absence check after the deadline.

Operator sees: `provider_container_cleanup.status = refused` with the Docker error, the
removed container id retained, a `tombstone_until_utc` later than before, and
`retry_after_utc` on the stop result. `stop-background-jobs` exit 1, `cleanup_pending`.

### 2. Authentication before anything destructive

`_ticket_problems` now compares `sha256(request_bytes)` against `request_sha256` on
**every** path — a missing file, an empty file, a truncated file and a malformed file all
fail that comparison instead of skipping it, and each also reports its own problem
(`launch request is missing` / `is empty` / `is unreadable` / `is not an object`), plus
`index records no ticket hash` when the recorded hash is not a 64-character string. The
task id is validated, and the ticket's schema, `job_id`, `task_id`, `kind`, `identity`,
`job_name`, `source`, `checkout_root` and `provider_container` must equal the index.

New `_identity_problems` proves the **owned run directory**, the **Job Object name
derived from it**, the **job kind**, the **derived container name and its compose
project**, the **recorded PID** and the **complete process identity dict** against
`launcher.identity.json`, `child.identity.json` and `job.opened.json`. A ticket whose
child was never spawned (`spawn_failed` before the launcher record) records no identity
and none is invented, but any artifact that does exist must match exactly.

`_authentication_problems` = identity + ticket, and gates: every cleanup generation
(`_run_cleanup`), `harvest`'s cleanup, and `clear`. The identity set alone gates
`request_stop` (before a stop request is bound) and `_enforce_stop` (immediately before
the only `host.stop` call). On a mismatch `_refuse_authentication` writes, under the lock:
`provider_container_cleanup.status = refused` with `authentication_failed: true` and the
joined problem list, plus a new `authentication` block
(`{"status": "authentication_failed", "problems": [...], "at_utc": ...}`) now carried in
`summary()` and therefore in stop results, journal events and the viewer. Nothing is
inspected, removed, signalled or terminated; `cleanup_retry_due` stays false; startup
refuses; `clear` refuses.

One deliberate exception, unchanged from round 2 and covered by the real-Windows
quarantine test: a `child.identity.json` that names **other ticket bytes** stays a
*ticket* problem (`_handshake_ticket_problems`, used only by `authenticate_index`), not
an identity one. The recorded child is still provably itself and the container name is
still derived from an authenticating ticket, so a restart can still stop, quarantine and
clean up exactly that tree instead of leaving a container behind.

### 3. Concurrency is an outcome, not a failure

`_run_cleanup`, `_finish_cleanup`, `_record_final_recheck` and `settle_cleanup` return
`_concurrency_outcome(...)` — `{"task_id", "kind", "job_id", "status",
"provider_container": None, "provider_container_cleanup": None, "cleanup_concurrency":
"cleared" | "superseded", "detail": ...}` — instead of raising when the index was cleared
or its job id changed. Such an outcome reads as not pending (whatever replaced it owes
its own cleanup), so `_require_verified` does not refuse startup on it and
`stop_complete` is satisfied. Every re-read after the unlocked window (including the one
after `_wait_for_tombstone`) is guarded, and `_exact_look` propagates the outcome.

`reconcile_startup` journals it as the `cleanup_superseded` outcome
(`job_cleanup_superseded` event) and wraps `settle_cleanup` so a genuine
`BackgroundJobError` becomes a journaled `StartupRefused` rather than a bare exception.
`GraphController._harvest_jobs` journals `job_cleanup_superseded` for the outcome, and
catches `BackgroundJobError` from both `settle_cleanup` (journaled `job_cleanup_pending`
with the detail) and `harvest` (journaled `job_harvest_deferred`), continuing with the
other tasks. `_finish_cleanup` on a superseded generation still returns the durable
record, as in round 2.

Operator sees: the run completes, `state.last_error` is null, the journal carries
`job_cleanup_superseded` with the reason, unrelated tasks keep being planned.

### 4. Unreadable indexes fail closed

New `scan_indexes(manager) -> (readable, unreadable)` returns every readable index plus a
JSON-safe `{"task_id", "path", "error"}` diagnostic for each index that is missing,
empty, truncated, malformed, names another Source or checkout root, or whose file name is
not a valid task id. `list_indexes` still raises on the first such index (unchanged
contract); `unreadable_indexes` is the public read-only view.

- `graph_controller._cleanup_pending_tasks` now returns `(pending, unreadable)` and no
  longer swallows `ValueError`.
- `stop-graph`: `already_released_cleanup_pending` or `stopped_cleanup_pending`
  (**exit 1**) with `unreadable_indexes` and a `note` naming each path and error and
  saying the file must be repaired or archived by hand.
- `cancel_all` emits one `{"status": "unreadable_index", "cleanup_pending": true, "path",
  "error"}` result per such index, so `stop-background-jobs` reports `cleanup_pending`
  (**exit 1**) with `unreadable_indexes` in the payload, and `stop_complete` is false.
- `reconcile_startup` raises `StartupRefused` naming every path and error before it
  reconciles anything, so a controller start journals `startup_refused` and does not plan.
- Nothing deletes, rewrites or "repairs" such a file. After an operator repairs it by
  hand the same commands report `already_released` / `stopped` and exit 0 again
  (asserted in the test).

---

## Tests

New regressions (all fail on `62245a1`, all pass on `91a0b0d`):

| Finding | Test |
|---|---|
| 1 | `test_docker_failure_after_a_late_sighting_keeps_the_removal_and_the_renewed_bound` |
| 1 | `test_interrupted_cleanup_keeps_its_removal_durable_and_never_completes` |
| 2 | `test_empty_or_malformed_launch_request_never_authenticates_a_cleanup` (missing / empty / truncated / malformed subtests) |
| 2 | `test_process_identity_mismatch_refuses_every_destructive_path` |
| 3 | `test_a_concurrent_clear_is_a_cleanup_outcome_not_a_failure` (cleared and superseded) |
| 3 | `test_concurrent_clear_during_cleanup_does_not_abort_the_controller` (loop) |
| 4 | `test_unreadable_pending_index_never_reports_a_released_stop_graph_as_finished` (loop + CLI, four corruptions) |

Each of them also asserts that no unrelated process or container is inspected, killed or
removed (victim container still present, victim child still `running` with `stopped is
None`, no stop request file written, Docker call count unchanged), and that repeated
stops and cleanups stay idempotent (equal record, zero further Docker calls, exit 0 after
repair).

Two existing assertions were updated, both strengthening:

1. `test_forged_identity_cannot_reach_an_unrelated_process_or_container`, case 4: the
   forged process identity is now refused by `request_stop` with
   `does not authenticate` **before** the host is asked to stop anything, instead of the
   old `fixture stop names another Job Object` raised from inside `host.stop`. The test
   now also asserts the durable `authentication_failed` record and that no stop request
   file was written.
2. `test_stop_background_jobs_cli_refuses_while_a_controller_owns_the_graph`: the empty
   payload now carries `"unreadable_indexes": []`.

Results on `91a0b0d`:

```
python -m unittest Pipeline.AssistantControl.test_background_jobs
Ran 50 tests in 226.127s
OK

python -m unittest Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 109.238s
OK

python -m unittest Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control Pipeline.AssistantControl.test_decomposition
Ran 17 tests in 32.169s
OK
```

(50 = 43 previous + 7 new, including the three tests that launch the real detached
Windows child.) `git diff --check`: clean, exit 0 — the only output is the expected
`LF will be replaced by CRLF` notice for the two LF files.

---

## Residual risks, stated plainly

- `_harvest_jobs` catches `BackgroundJobError` only. A `TimeoutError` on
  `checkouts.lock`, or an `OSError`, still blocks the controller. That is deliberate:
  broadening the catch would hide genuine faults, and the finding named concurrency.
- The tombstone bound is still Docker's 60 s CLI timeout, not a proof about the daemon. A
  sighting now restarts it, so a container that keeps reappearing keeps its ticket pending
  indefinitely rather than completing — correct, but it needs an operator.
- **Operator burden worth flagging:** an index that cannot be read now blocks
  `stop-graph` and `stop-background-jobs` with a nonzero exit *for the whole graph*, not
  just that task, and refuses a controller start, until a human repairs or archives the
  file. There is deliberately no `--repair` or `--force` path. If a record is corrupted by
  a crash mid-write, the operator must move it aside by hand before anything can run
  again. I judged that the correct reading of "fail closed ... until the state can be
  authenticated or explicitly repaired", but it is a new way to wedge a graph and you may
  want an explicit, audited archive command in a later round.
- Second operator burden: a cleanup that can never be authenticated (tampered ticket
  bytes, a mismatched identity artifact) blocks its task permanently and refuses startup;
  nothing retries it. Unchanged from round 2, now reachable through more checks.
- `_refuse_authentication` writes through `index_path`, which validates the task id. Every
  caller passes an index freshly read under the lock (so its task id is already valid), but
  a hand-edited record with an invalid `task_id` would raise out of the refusal path rather
  than recording it. That failure is fail-closed (nothing destructive happened first).
- Owner liveness is still by exact process identity; an owner on another machine sharing
  the checkout root would read as gone and be taken over. The checkout root is local by
  design.
- The real `docker` CLI path remains exercised read-only. Every mutation test drives the
  fixture Docker.

---

Requesting Astra's re-review of **`91a0b0dfd9ad605d39e565b014ea95c099e8d42b`** before merge.
