# Decomposition timeout and slow-run triage (developer T): final report

Received 2026-09-13 at about 22:30 UTC and recorded in substance by the coordinating session. Covers Codex blocker 1, plus Vincent's 30-minute orchestrator event. The coordinator has checked the commit identity, files and whitespace.

## Commit

- `008d1dfcf832de609ce180de027701f06406f59d` on `throughput/decomposition-slow-triage`, parent `f941857` (C0). Not pushed; worktree clean.
- It cherry-picks onto `fce5398` with no conflicts: `decomposition.py` auto-merges and `git diff --cached --check` is clean.
- Files, under `Pipeline/AssistantControl/`:
  - `decomposition_triage.py` (new, +602)
  - `test_decomposition_triage.py` (new, +776)
  - `graph_controller.py` (+53/-2)
  - `viewer.py` (+17)
  - `decomposition.py` (+6/-1, in 5 hunks)

## How each requirement is met (file:line at 008d1df)

1. **Container limit from the effective budgets.**
   - `decomposition_triage.py:78 resolve_container_budgets()` resolves both budgets on the host with the producer's own `decomposer_budgets()` and `reviewer_budgets()`.
   - An invalid value raises `ValueError` (`:95`) at `decomposition.py:483`, before any record, log directory or docker call.
   - The limit is derived in one place (`:67`): author + reviewer + max(author, reviewer) + 600, which is 4680 s at defaults.
   - `decomposition.py:546` forwards `--env NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS=<v> --env NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS=<v>` right after `run ... -T`.
   - `:558` uses the limit as the subprocess timeout.
   - `:518` records `container_budgets`: both budgets, the margin, the limit and the forwarded strings.
   - Nothing hashes the compose command or its environment. `request_sha256` covers only the launch request bytes (`background_jobs.py:673`), and `job_id_for` covers kind, task, identity, attempt, Source and checkout root.
2. **Controller wait** is the job's own recorded limit + 180 s (`graph_controller.py:79`, `:1579`, `:1621`).
   - Before the child writes its record, the host configuration is used.
   - With an invalid host configuration, the longest valid limit is used; such a child refuses to start within seconds.
   - Direct call results: 4860 at defaults; 7980 for a recorded 7800 limit; 259980 for an invalid host configuration.
3. **`decomposition_slow` event.**
   - **Trigger:** a decompose job still active 1800 s after `launched_at_utc`, measured on the clock that stamped the launch (`decomposition_triage.py:420`).
   - **Checked:** on every wait poll (`graph_controller.py:1646`) and every planning cycle (`:2093`).
   - **Exactly once** per (event, job_id). Each invocation reads the journal once (`:461`, `:537`, `graph_controller.py:433`).
   - **Advisory only:** a journal line plus a viewer marker at `records/decomposition-triage/<task>.json` (`:490`); the snapshot builder is read-only (`:315`).
   - **Torn or garbage `progress.jsonl`:** degrades to partial facts or `no_progress` (`:215`).
   - **Triage failure:** journaled once as `decomposition_triage_error`; the graph never stops (`graph_controller.py:1357`).
4. **`decomposition_failed` event.** It is new because the existing lines are not equivalent: `job_failed` carries no snapshot, and a non-zero container exit is journaled only as `job_completed` with `result_status: failed`.
   - It fires once, for either a timeout or a non-zero exit.
   - Died, cancelled and spawn_failed jobs keep their existing events.
5. **Viewer** (`viewer.py:645`, `:695`). The detail shows only while the slow condition holds and the marker proves this job's event was journaled. It is a freshly measured summary line ending "; orchestrator notified.".

## Failing before and passing after

The same committed test file (sha `ff4eb5b4...`) was run at both commits:
- `f941857`: Ran 16, FAILED (failures=23, errors=5).
- `008d1df`: Ran 16, OK.

Failures at `f941857`, each for the intended reason:
- timeout 3600 instead of 4680;
- an env override not applied (3600 instead of 9100.5);
- an invalid override not refused (12 subtests);
- the wait expiring as `background_jobs_running`;
- no slow event, whether during the wait, on a planning cycle, or after restarts;
- no triage-error event;
- no viewer detail;
- no `decomposition_failed` event for a non-zero exit or a timeout;
- errors in the 5 snapshot tests, because the module does not exist yet.

## Suites

| Suite | 008d1df | fce5398 + cherry-pick |
|---|---|---|
| test_decomposition_triage | 16 OK | 16 OK |
| test_graph_controller | 33 OK | n/a (file unchanged in the stack) |
| test_decomposition | 26 OK | 57 OK |
| test_decomposition_needs_human | 19 OK | 37 OK |
| test_decomposition_revision_review_integration | n/a | 7 OK |
| test_viewer | 39 run, errors=1 (pre-existing) | n/a |
| test_background_jobs | 81 OK | n/a |

The `test_viewer` error is `test_build_projects_timing_for_the_in_scope_task_named_by_the_controller` (`stage_elapsed_seconds` is None). It is identical at `f941857` and when run alone.

## Residual risks (as reported)

- **Retained failed jobs.** Any retained failed decompose job journals one `decomposition_failed` on the first cycle after deploy.
- **Turn limits.** An invalid host turn-limit variable now refuses launch. Turn limits are still not forwarded.
- **Forward call outside the try block.** Like the existing `--name` insertion, `forward_container_budgets` runs outside `run()`'s try. If `build_compose_command` stopped emitting `run ... -T`, it would raise and leave the record `running`. The coordinator asked for follow-up T2 to close this window.
- **Long wait budget.** With an invalid host configuration and no record yet, the wait budget is about 72 hours. The wait still returns as soon as the job ends, and such a child fails within seconds.
- **Exactly-once assumptions.** Exactly-once assumes the journal is not rotated. A torn last line may cause one duplicate event.
- **Missing viewer detail.** A job past 30 minutes that never wrote its record, or a marker write that keeps failing, gets the event but no viewer detail.

## Orchestrator watch command

```
tail -n0 -F "<checkout-root>/.assistant-control/graph-controller-events.jsonl" | grep --line-buffered -E '"event":"decomposition_(slow|failed|triage_error)"'
```

Checked against real `_append_event` output: a decoy line containing `"reason":"decomposition_failed"` does not match. Each matching line carries `task_id`, `job_id`, `run_id`, `summary` and `triage`.

## Nothing live touched

- `C:\NSC` was only read.
- No docker, gh, claude or codex was run, and nothing was pushed, merged or posted.
- There were no CI or fixture changes.
- The temporary worktrees were removed and pruned.

## Follow-up T2: close the stuck-running window (reported about 22:55 UTC)

- **Commit.** `c245deba804fe3dd6d8cfd548d02f75274c28d33`, parent `008d1df`. Not pushed; tree clean.
- **What changed.** `decomposition.run()` now builds the whole compose command inside the existing try: `build_compose_command`, `--name`/`--label`, the forwarded budgets, `--source`/`--output-root`, the environment and the creationflags. Any failure after the running record is written is now recorded `failed` by the existing `except BaseException` handler, which then re-raises.
- **What stayed the same.** Budgets are still resolved before any write. On the success path the command and every record field are byte-identical, and a new exact-launch test asserts this.
- **Diff.** `decomposition.py` +20/-18 (`git diff -w` is +3/-1); `test_decomposition_triage.py` +83/-9.
- **Failing-before at `008d1df`**, run with the committed T2 test file (sha256 `ca17c08e`): 18 ran, failures=4. All four are sub-cases of the new window test, and in each the record stayed `('running', None)`:
  - no-run-subcommand
  - named-without-run
  - no-tty-option
  - builder-refuses

  The exact-launch guard passes at `008d1df`.
- **Suites on T2 (all OK):** test_decomposition_triage 18, test_decomposition 26, test_decomposition_needs_human 19.
- **Cherry-picking `008d1df` then `c245deb` onto `ff5bdc6` (A2):**
  - No conflicts; `decomposition.py` auto-merged both times, and `diff --check` is clean.
  - In the merged `run()`, the moved `try` is at line 1182, and A2's `_needs_human_proof(record, authenticated)` is intact at 1225.
  - Suites there: test_decomposition_triage 18 OK, test_decomposition_needs_human 41 OK.
- **On developer A's branch,** T2 was cherry-picked as `e25b53e`, right after T `4449fb8`.
