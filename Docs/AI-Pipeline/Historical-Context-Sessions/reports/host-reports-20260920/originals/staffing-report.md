# Persistent three-worker graph staffing — implementation report

**Exact commit:** `37899ac36423a0049df8232b3d9ca2e200d12630`
on `throughput/background-decomposition` in the isolated clone `C:\nscrev\throughput`,
directly on top of `e90670da5b5fc19567e1efe1cb655c43de292f4e` (HEAD was verified at
`e90670d` with a clean tree before any edit; nothing had advanced).
Not pushed, not merged. No live run, task checkout, Task contract, Asset, Docker
container, GitHub main or provider credential was touched; nothing under `C:\NSC` was
read or written, including the concurrent Gauntlet in
`C:\NSC\GauntletFresh1140-20260912-1`. No `docker` command ran; no provider was invoked.

**Files changed (8):**

| File | What changed |
|---|---|
| `Pipeline/AssistantControl/graph_controller.py` | `worker_slots` policy, staffing projection, journal, stop |
| `Pipeline/AssistantControl/__main__.py` | `--worker-slots` on `graph-plan` and `run-graph`; `--capacity` defaults to it |
| `Pipeline/AssistantControl/viewer.py` | read-only `staffing` projection with elapsed time |
| `Pipeline/AssistantControl/test_background_jobs.py` | new `GraphStaffingTests` (11 tests) |
| `Pipeline/AssistantControl/test_graph_controller.py` | one existing four-way admission test now also configures four slots |
| `Pipeline/AssistantControl/README.md` | staffing section |
| `Pipeline/AssistantControl/CURRENT.md` | dated section at the top of the background-job entries |
| `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md` | `--worker-slots`, loop item 4b, stop behaviour |

---

## Architecture, and what it deliberately is not

There is still **exactly one** `GraphController` with one planner, one owner lock and one
action per loop iteration. The three slots are a **durable projection and policy over the
existing mechanisms** — `admission.reserve`, `worker_launcher.start`,
`worker_control.status`, `worker_settlement.settle_completed` and the existing
`_reservation_owner_action` ownership proof — not a second scheduler and not three
competing controllers. No process, checkout, Job Object or Docker ownership check from
`e90670d` was altered.

Worker concurrency was already physically possible (the controller launches detached
workers and observes them). What was missing, and what this adds, is the explicit
persistent staffing contract: named slots with durable state, transition journalling,
refill-on-release, a viewer projection, and a stop that reaches staffed workers.

### `--worker-slots` reconciled with `--capacity`

Deliberately **not** two independent limits:

- `capacity` remains the admission ceiling `admission.reserve` enforces on the shared
  reservation registry, which may also be owned by work outside this graph.
- `worker_slots` (default 3) is the staffing contract: how many task workers this one
  controller keeps busy.
- `GraphPolicy.staffing_width = min(worker_slots, capacity)` is what the loop uses
  (`_choose_run_action`'s `capacity_full` check) and is reported in the state, the run
  result and the viewer so it is never silently clamped.
- The CLI defaults `--capacity` to `--worker-slots`, so `run-graph` staffs three out of
  the box; an explicit `--capacity` still wins. The `GraphPolicy` dataclass defaults are
  unchanged for library callers (`capacity=1`), so a direct construction behaves exactly
  as before until it opts in.

---

## Staffing state schema

Persisted under `staffing` in `graph-controller.json`, and in every `run-graph` result:

```json
{
  "schema_version": "assistant-graph-staffing/v1",
  "worker_slots": 3, "capacity": 3, "staffing_width": 3,
  "occupied": 2, "available": 1,
  "unslotted": [],
  "slots": [
    {
      "slot_id": "slot-1",
      "state": "working",
      "task_id": "NSC-1101",
      "run_id": "assistant-nsc-1101-35e171044bc5",
      "lease_id": "assistant-nsc-1101-…-lease",
      "worker_identity": {"pid": 88, "created_ticks": 1, "image": "worker"},
      "checkout": "…/checkouts/NSC-1101",
      "source_commit": "…40 hex…",
      "started_at_utc": "2026-09-12T…+00:00",
      "updated_at_utc": "2026-09-12T…+00:00",
      "last_result": {"task_id": "NSC-1100", "outcome": "blocked", "at_utc": "…"},
      "blocker": null,
      "next_action": {"kind": "wait_worker", "task_id": "NSC-1101", "run_id": "…"}
    }
  ]
}
```

`state` is one of `SLOT_STATES = ("idle", "claiming", "working", "settling", "blocked",
"awaiting_human", "stopped")`. A slot is **occupied** in `claiming`/`working`/`settling`
and **available** in the other four; an available slot keeps the task id and the outcome
of whatever last left it so an operator can see why, and is claimed by the next
compatible ready task regardless. `unslotted` names any reserved task beyond the staffing
width — reported, never dropped.

State derivation is from durable evidence only:

| Durable evidence | Slot state |
|---|---|
| Reservation bound to this Source/checkout, no worker record yet | `claiming` |
| Worker binds to the exact reservation (`_reservation_owner_action`), not terminal | `working` |
| Same, worker terminal and unsettled | `settling` |
| Reservation whose worker identity cannot be tied to it | `blocked` (`ownership_unverified`) |
| Reservation naming another Source/checkout root | `blocked` (`reservation_unverified`) |
| Released, task in `plan.waiting_human` | `awaiting_human` |
| Released, task in `plan.blocked` | `blocked` (planner reason) |
| Released, stopped by this controller | `stopped` |
| Otherwise | `idle` |

The viewer adds `elapsed_seconds` and `updated_seconds_ago` computed from those
timestamps. No slot state is inferred from process liveness.

### Journalled events

`staffing_slot_claimed`, `staffing_slot_started`, `staffing_slot_settling`,
`staffing_slot_released` (with `released_task_id`/`released_run_id`),
`staffing_slot_refilled`, `staffing_slot_idle`, `staffing_slot_blocked`,
`staffing_slot_awaiting_human`, `staffing_slot_stopped` — each carrying the slot id,
state, task, run and lease id, the exact `worker_identity`, checkout, Source commit,
blocker and next action. The previous view is seeded **once per invocation** from the
inherited state, so a transition is journalled exactly once however often the state is
saved.

---

## Cycle behaviour

On every cycle, before any action runs: existing jobs are authenticated and harvested
(unchanged), then `_refresh_staffing(plan)` recomputes the slots. Settlement is still the
first action class, so an ended worker settles, releases its admission and frees its slot
before anything else; `_choose_run_action` then fills every available slot
(`reserve`/`start_worker`) **before** the Source-moving lane, so newly ready work is
claimed in the same planning pass. Tasks already claimed are excluded (they have a
reservation and the planner offers `wait_worker`, never a second `start_worker`), and
tasks whose exclusive resources overlap a live admission are excluded by the existing
`admission.reserve` + `_resource_overlap_action` path. A worker completing, failing,
blocking or reaching human review releases its slot and only that task is affected.
With nothing ready, the existing bounded `_wait_for_progress` is used, waking on any
watched worker exit, any background-job end, a bound stop request, or the bounded
deadline.

**Restart:** slots are rebuilt from the durable reservation and worker records, not from
the persisted slot list (which only supplies stable slot ids). A live authenticated
worker is adopted and never relaunched; a reservation whose worker identity cannot be
tied to it is quarantined as `blocked` with `ownership_unverified`, and the other slots
keep working.

**Stop:** `stop-graph` and Ctrl+C stop every staffed worker by its exact recorded run
identity — `worker_control.request_stop` (which re-derives the worker from its own record
and refuses any other run id), the same bounded grace, then the existing exact
`force_stop` for whatever is still alive. Per-slot outcomes persist as `staffing_stops`
and in each slot's `last_result`. A worker that could not be stopped is **never** reported
as stopped: its slot stays `blocked` with `stop_failed` and the exact error. A failure in
worker stopping never prevents the background-job stop. Repeating the stop asks for
nothing new; background jobs keep their existing idempotent stop.

---

## Focused tests and results

New `GraphStaffingTests` in `test_background_jobs.py` — 11 deterministic tests on the
real planner, real `admission`, real scope planning and real Git fixtures, with fixture
workers and the fixture clock:

| Test | Owner's scenario |
|---|---|
| `test_three_slots_start_together_and_the_fourth_waits_for_a_release` | four ready → three start; fourth on release; duplicate-launch count |
| `test_two_ready_tasks_leave_the_third_slot_idle_and_repeat_launches_nothing` | two ready, one idle, no repeated launches |
| `test_a_blocked_task_blocks_only_its_slot_which_is_then_refilled` | one blocks, others ready |
| `test_a_satisfied_dependency_is_claimed_into_an_idle_slot_without_a_restart` | dependency completes |
| `test_decomposition_children_are_staffed_while_the_background_job_runs` | decomposition children; background jobs consume no slot |
| `test_overlapping_resource_tasks_never_occupy_two_slots` | overlapping resources |
| `test_human_review_task_frees_its_slot_and_is_never_auto_approved` | NSC-042 |
| `test_restart_adopts_staffed_workers_and_quarantines_only_the_ambiguous_one` | restart adoption; ambiguous ownership |
| `test_stop_graph_stops_only_the_exact_staffed_workers_and_repeats_idempotently` | stop + repeat + refused stop |
| `test_no_ready_work_waits_bounded_instead_of_busy_looping` | bounded waiting |
| `test_viewer_reports_every_staffing_slot` | viewer projection |

```
python -m unittest Pipeline.AssistantControl.test_background_jobs
Ran 65 tests in 356.834s
OK

python -m unittest Pipeline.AssistantControl.test_graph_controller
Ran 33 tests in 62.853s
OK

python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_cli_worker Pipeline.AssistantControl.test_worker_control Pipeline.AssistantControl.test_admission
Ran 25 tests in 69.032s
OK

python -m unittest Pipeline.AssistantControl.test_viewer
Ran 39 tests in 51.670s
FAILED (errors=1)
```

The single viewer error is the pre-existing, unrelated
`GraphControllerTimingEndToEndTests.test_build_projects_timing_for_the_in_scope_task_named_by_the_controller`
(`TypeError: '>=' not supported between instances of 'NoneType' and 'float'`). I ran it on
a stashed working tree at `e90670d` and it fails identically there.

`git diff --check`: clean, exit 0 (only the expected `LF will be replaced by CRLF` notice
for `test_background_jobs.py`).

One existing assertion was updated:
`test_available_slot_launches_fast_result_validation_then_admits_later_task` set
`capacity=4` and expected a fourth admission; it now sets `capacity=4, worker_slots=4`,
which preserves the test's intent (a controller configured for four admits a fourth)
under the new contract.

---

## Performance acceptance, measured

Fixture harness, four compatible ready tasks, `--worker-slots 3` (raw output kept at
`staffing-measurements.txt` in my scratch directory):

```
--- one controller cycle, four compatible ready tasks ---
actions               : prepare ×4, scope ×4, reserve, start_worker, reserve, start_worker, reserve, start_worker
workers started       : ['NSC-1101', 'NSC-1102', 'NSC-1103']
fixture clock at each : [0.0, 0.0, 0.0]
max active slots      : 3
duplicate launches    : 0
waits before 3rd start: 0
planner calls         : 15
planner time total    : 3.610s  mean 0.241s  max 0.999s
invocation wall time  : 17.515s

--- refill after one settlement ---
actions               : post_crew, reserve, start_worker, wait_job
refilled task         : ['NSC-1104']
refill latency (fixture clock)        : 0.000s
refill latency (wall, incl. real git) : 2.918s
max active slots      : 3
slots                 : slot-1 working NSC-1104, slot-2 working NSC-1102, slot-3 working NSC-1103
```

- **Three compatible tasks launched in one cycle without waiting for the first**: all
  three `start_worker` actions execute at the same fixture instant with **zero** wait
  actions between them.
- **Settling refills before an unnecessary planning delay**: the freed slot is refilled in
  the same planning pass, 0.000 s of fixture-clock latency after the admission is
  released; the 2.9 s wall figure is dominated by real `git` planning in the fixture, not
  by staffing.
- **Maximum active slots**: 3. **Duplicate launches**: 0 across all invocations in the
  test (asserted, not just measured).

---

## Things I had to interpret

1. **Slot lifetime.** Requirement 2 enumerates `blocked`/`awaiting_human`/`stopped` as
   slot states while requirement 4 demands the slot be released immediately. I made
   occupancy mean "this task holds an authenticated worker reservation"; a released slot
   keeps the outcome as its displayed state (`blocked`/`awaiting_human`/`stopped`) and is
   **still available** for the next task, becoming `idle` only when nothing was left
   behind. Both requirements hold and an operator can see why a slot was freed.
2. **A quarantined reservation holds its slot.** It still consumes admission capacity, so
   representing it as occupying a slot (state `blocked`, next action
   `operator_inspection`) is the honest accounting; the other slots are unaffected.
3. **`capacity` semantics.** See above; this is the one behaviour change for an existing
   caller — a library caller with `capacity=4` and default `worker_slots=3` now staffs 3.
   Reported as `staffing_width` everywhere rather than hidden.
4. **Fixture seams, labelled in the tests.** `fake_foreground`'s `settle_worker` does not
   release the real admission, so the refill tests call `admission.release(...)`
   explicitly — the exact call real settlement makes. The dependency test patches
   `approved_integration` and `admission._dependency_is_satisfied`, because dependency
   *completeness* has two independent oracles with their own tests; the staffing question
   under test is whether an idle slot claims the task once it is ready.
5. **Test fixture resources.** Every task in the shared graph fixture resolves its Unity
   filter to the same committed `GauntletTests.cs`, so all fixture tasks overlap on
   exclusive resources and only one could ever be admitted. The staffing tests therefore
   commit tasks with a private test file each; the shared-resource case is its own test
   and proves overlapping tasks are never staffed together.
6. **Stopping staffed workers is new destructive behaviour** in the stop path (previously
   `stop-graph` stopped only background jobs). Requirement 9 asks for it explicitly. It
   goes only through the existing exact-identity `worker_control` entry points, only for
   slots this controller authenticated, per-slot failures are retained rather than raised,
   and a refused stop is never reported as a stop.

---

## Remaining risks

- **`force_stop` reaches real Docker.** For a worker still alive after the grace, the stop
  path calls `worker_control.force_stop`, which terminates the recorded Job Object tree
  and runs `docker_workers.stop_containers` for that run's compose project. That is the
  pre-existing exact-identity mechanism, but `stop-graph` now invokes it where it
  previously did not. It has not been exercised against a live daemon in this clone, by
  instruction; the tests patch both `worker_control` entry points and assert exactly which
  `(task, run_id)` pairs are asked to stop.
- **The fixture worker path is not the real worker path.** `start_worker` is faked in
  every loop test, so the staffing tests prove planner, admission, slot projection,
  journalling and stop wiring, not the real `worker_launcher.start` process handshake
  (which has its own tests).
- **Planner cost bounds refill latency in production.** A refill costs one planning pass
  (mean 0.241 s, max 0.999 s in the fixture; the live graph's `plan()` was measured at
  15–25 s in the earlier Gauntlet analysis). Staffing removes the *waiting* between
  starts, not the per-cycle planning cost.
- **Three slots means three concurrent provider workers.** `--authorize-provider-spend`
  now authorizes up to `worker_slots` concurrent paid workers instead of one by default.
  The CLI default change (`--capacity` following `--worker-slots`) is the reason; an
  operator who wants the old single-worker behaviour passes `--worker-slots 1`.
- **`unslotted` is reported but not acted on.** A reservation beyond the staffing width
  (for example one owned by another graph on the same registry) is listed and otherwise
  left alone; it still consumes admission capacity, which the staffing width already
  respects.
- The pre-existing `test_viewer` timing failure is untouched and out of scope.
