Codex, please adversarially review one new commit in the isolated throughput clone. This is a review, not a repair: report findings, do not edit, commit, push, merge, run Docker, call a provider, or touch GitHub.

# What to review

- Repository: `C:\nscrev\throughput`, branch `throughput/background-decomposition`
- Commit under review: `37899ac36423a0049df8232b3d9ca2e200d12630` ("AssistantControl: persistent three-worker staffing slots under the one graph controller")
- Parent: `e90670da5b5fc19567e1efe1cb655c43de292f4e` (the round-5 repair Astra was asked to re-review; treat it as the baseline, not as reviewed)
- Diff: `git -C C:\nscrev\throughput diff e90670d 37899ac` (8 files, +1023/-18; `git diff --check` is clean)
- Implementer's report: `C:\nscrev\reports\staffing-report.md`
- Files: `Pipeline/AssistantControl/graph_controller.py` (+413/-13), `__main__.py`, `viewer.py`, `test_background_jobs.py` (+468, new `GraphStaffingTests`, 11 tests), `test_graph_controller.py` (one existing test now also sets `worker_slots=4`), `README.md`, `CURRENT.md`, `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md`

If you want to run anything, use a detached worktree so the clone's branch is never moved: `git -C C:\nscrev\throughput worktree add --detach C:\nscrev\staffing-review 37899ac`, work there, then `git worktree remove --force C:\nscrev\staffing-review` and `git worktree prune`. Do not touch anything under `C:\NSC` (a live 1140 project, its checkout roots and a viewer on port 8817 are there) and do not touch `C:\nscrev\decomp-fix` (another agent is committing there on top of 37899ac).

# What the commit claims

One GraphController, one planner, and `--worker-slots` (default 3) persistent logical worker slots beneath it, as a durable projection over the existing reservation, worker-launch and settlement mechanisms:

1. `GraphPolicy.worker_slots` (default 3) beside `capacity`; `staffing_width = min(worker_slots, capacity)`. `_choose_run_action` now treats admission as full at `staffing_width` instead of `capacity`. The CLI's `--capacity` default changed from 1 to `--worker-slots`, so `run-graph`/`graph-plan` without `--capacity` now admit three workers (library `GraphPolicy` defaults still give width 1).
2. Each cycle, after harvest and `plan()`, `_refresh_staffing(plan)` projects the durable reservations and task records onto stable slots `slot-1..slot-N`: `claiming` (reservation, no worker yet), `working`/`settling` (worker bound to the exact reservation via the existing `_reservation_owner_action` proof), `blocked` (`ownership_unverified` when a worker exists whose identity cannot be tied to the reservation, `reservation_unverified` when the reservation names another Source/checkout). A released slot keeps the outcome of the task that left it (`blocked`, `awaiting_human`, `stopped`, else `idle`) and stays available. More reservations than width are reported as `unslotted`.
3. Persisted as `staffing` in `graph-controller.json` and in every `run-graph` result (`schema_version: assistant-graph-staffing/v1`, `worker_slots`, `capacity`, `staffing_width`, `occupied`, `available`, `unslotted`, `slots[]` with slot_id, state, task_id, run_id, lease_id, worker_identity, checkout, source_commit, started_at_utc, updated_at_utc, last_result, blocker, next_action). Transitions journaled as `staffing_slot_claimed/started/settling/released/refilled/idle/blocked/awaiting_human/stopped`, compared against a seed taken once per invocation so each transition is journaled once.
4. `stop-graph` and Ctrl+C now also stop every staffed worker by its exact recorded run id: `worker_control.request_stop`, the bounded grace with `worker_control.status` polling on `host_identity_alive`, then the existing exact `worker_control.force_stop` for whatever is still alive (this reaches real Job Object termination and the worker's Docker project). Per-slot outcomes persisted as `staffing_stops`; a worker that could not be stopped is never reported stopped, its slot stays `blocked` with `stop_failed`, and a worker-stop failure never prevents the background-job stop.
5. Viewer: `state["staffing"]` is added to `/api/state` by `AssistantSnapshot._staffing_projection` (elapsed seconds from the controller's own timestamps). `Pipeline/TaskReviewAgent/GauntletView/index.html` was not changed, so nothing renders the slots yet.

Implementer's test results (Windows, 2026-09-12):

```
python -m unittest Pipeline.AssistantControl.test_background_jobs   -> Ran 65 tests OK (about 6 min; includes real Windows child tests)
python -m unittest Pipeline.AssistantControl.test_graph_controller  -> Ran 33 tests OK
python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control Pipeline.AssistantControl.test_admission -> Ran 25 tests OK
python -m unittest Pipeline.AssistantControl.test_viewer            -> 39 tests, 1 error, pre-existing and identical on e90670d (GraphControllerTimingEndToEndTests.test_build_projects_timing...)
```

Claude's independent rerun of the same suites is in progress and will be reported separately. No live gauntlet has run with this commit yet: the run-3 evidence under `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-4` was produced by the pre-staffing build (AssistantControl at e90670d plus the viewer-scope commit), so every staffing claim is fixture-only so far.

# Review targets (in priority order)

1. Exact identity and fail-closed behaviour of the new worker stop in `GraphController._stop_staffed_workers` (graph_controller.py, around lines 1000-1085) and its callers `stopped()` and the Ctrl+C handler: can it ever stop a worker that this controller does not staff, or a different run of a staffed task? What happens when `worker_control.status` raises, returns `host_identity_alive: None`, or observes a worker that wrote its terminal record during the grace? Is the grace bound honoured on the real clock? Does a `force_stop` failure leave durable state that a later `run-graph`, `stop-worker` or `settle-worker` cannot recover from? Is stopping the task workers on `stop-graph` what the staffing specification asked for (its "stop-graph integration" item), given the previous behaviour left detached workers running for a later harvest?
2. Slot projection correctness in `_staffing_view` / `_slot_occupancy` / `_journal_staffing`: duplicate-launch or starvation paths (a task reserved but `unslotted`; a task whose slot was released while its reservation persisted; a quarantined reservation holding a slot forever; two controllers with different checkout roots sharing one Source registry); whether a slot that shows `blocked` with `stop_failed` is correctly recomputed as `working` by the next invocation while `staffing_stops` retains the failure; whether the seeded comparison journals exactly once across `_save_state` rewrites; whether `_reservation_bound` string comparisons (`str(self.manager.source)`, `str(self.manager.root / task_id)`) hold for the path spellings real invocations use on Windows.
3. Scheduling change: `capacity_full = len(reservations) >= staffing_width` counts every reservation in the Source registry, including ones from other checkout roots. Check the interaction with `admission.reserve`'s own `capacity` check, with the shared-resource overlap rule, and with the changed CLI default (three concurrent paid workers under `--authorize-provider-spend` unless `--worker-slots 1` or `--capacity 1` is passed).
4. New work inside `_save_state`: `self.staffing()` recomputes the projection (reads the admission registry and every task record) when no refresh has happened yet, including the `preflight` save and error-path saves; check that an unreadable registry cannot mask the original error or turn a refusal into a crash, and the cost per save on a large graph.
5. The eleven `GraphStaffingTests` (test_background_jobs.py from line 1383): do they prove the claims or only the fixture? Note the acknowledged seams: the fixture's settle does not release real admission so refill tests call `admission.release(...)` directly; the dependency test patches `approved_integration` and `admission._dependency_is_satisfied`; `request_stop`/`force_stop` are patched in the stop test, so no test exercises the real grace polling against `worker_control.status`. Name the missing test that would have caught each finding you raise.
6. Smaller items to confirm or dismiss: a successful release records no `last_result` on the freed slot; a released slot's terminal display state is sticky until a new task claims it and is counted as `available`; `next_action` on idle slots is a cosmetic pop of the plan's pending admissions; the viewer HTML shows nothing for staffing; docs vs code (README, CURRENT, ASSISTANT_AUTONOMOUS_GRAPH) for any promise the code does not keep.

# Report format

Reply in chat and write the same text to `C:\nscrev\reports\codex-staffing-review-37899ac.md`:

- Verdict: GO, FIX FIRST, or NO-GO for 37899ac.
- Findings ranked P1/P2/P3, each with `file:line`, a concrete failure scenario (inputs and durable state that produce the wrong outcome), why the existing tests did not catch it, and the smallest repair plus the failing-before test you would require.
- Exactly which commands you ran and their exact `Ran N tests ... OK/FAILED` lines, or say you ran none.
- Residual risks you could not settle by reading, with what evidence would settle them.

Do not repair anything: another agent is committing decomposer and planner fixes on top of 37899ac in `C:\nscrev\decomp-fix`, so any staffing repair will be sequenced after those commits land.
