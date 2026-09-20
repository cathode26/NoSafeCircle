# Trace report: GauntletView projection (bullet h)

Reviewer scope: `Pipeline/TaskReviewAgent/GauntletView/{server.py,pipeline_activity.py,index.html}` in the
candidate tree `C:/nscrev/cand` (commit 0c6e79e9), compared with `C:/nscrev/base` (6d62f0a8). All
reproductions ran only under `C:/nscrev/`; the archived G8 runs under `C:/NSC/G8-0650` were read only.

Repro scripts (all runnable as-is):

| Script | Purpose |
|---|---|
| `C:/nscrev/repro/viewer-accept/accept_cases.py` | 19 adversarial inputs to `Snapshot.local_candidate_is_accepted` using the real receipt type and the real acceptance mutator |
| `C:/nscrev/repro/viewer-handoff/handoff_stage.py` | Replays NSC-898's four recorded stage boundaries from the archived Claude journal through the candidate viewer |
| `C:/nscrev/repro/viewer-activity/mixed_states.py` | `build_local_pipeline_activity` on 15 mixed-state task sets |
| `C:/nscrev/repro/viewer-activity/parent_partial.py` | The bundled acceptance test's own partial-parent snapshot through the candidate and baseline activity reducers |
| `C:/nscrev/repro/viewer-dom/dom_harness.cjs` | `node --check` of the inline script, timer behaviour with a realistic DOM (null for missing ids), legend/detail/labelFor for the new local `complete` state |
| `C:/nscrev/tmp/viewer/dump_g8.py` | Read-only dump of both archived G8 runs (records, issues, journal) used to build realistic inputs |

Bundled viewer tests, run in `C:/nscrev/cand` (only the temp root of `decomposition_transition_view_test.py`
was patched from `C:\NSC` to `C:/nscrev/tmp`): `decomposition_transition_view_test` 6/6 OK,
`local_candidate_acceptance_view_test` 5/5 OK (25 negative subcases inside one test),
`third_local_pipeline_activity_test` 25/25 OK. Total 36 passed, matching the bundle's claim. What they
actually assert is discussed under each finding.

## Phase map (candidate-relative, verified line numbers)

| Step | Location | Note |
|---|---|---|
| Snapshot read | `Pipeline/TaskReviewAgent/GauntletView/server.py:2126-2141` `local_snapshot` | `LocalRunObserver.snapshot` (`local_rehearsal.py:1256-1267`) re-checks manifest/source/contract bytes, loads state through `_load_unlocked` (`:662-717`) |
| Snapshot shape | `Pipeline/TaskReviewAgent/local_rehearsal.py:1212-1241` `_snapshot_from_state` | `contracts` come from the manifest, `tasks`/`events` from state; `decomposition_handoffs[task].last_event_id` is the Issue workflow event id (`:1224`) |
| Record journal id | `Pipeline/TaskReviewAgent/local_rehearsal.py:719-737` `_save` | `record["last_event_id"] = event["event_id"]` (`:733`) is the local journal hash, a different id space |
| Workflow mirror | `Pipeline/TaskReviewAgent/local_rehearsal.py:1322-1342` `update_issue` | mirrors state/pipeline_stage/worker_id/lease_id (`:1337-1339`); never writes `last_event_id` |
| Handoff -> pending | `Pipeline/TaskReviewAgent/local_rehearsal.py:837-861` | requires record `worker_id`/`lease_id` None and `pipeline_stage == human_action_required` |
| Authorized / applied | `Pipeline/TaskReviewAgent/local_rehearsal.py:829-835`, `:873-939`, `:1089-1143` | D1C rebinding admits children in the same locked state write (`:1102-1110`) and rewrites parent contract hash |
| Candidate acceptance state | `Pipeline/TaskReviewAgent/local_rehearsal.py:941-981`, `:1005-1030` | sets `local_candidate_accepted`, worker/lease None, `accepted_worker_id`, `source_commit = applied`, receipt sha |
| State map | `server.py:2467-2481` | eight local states -> viewer states; unknown state raises |
| Acceptance predicate | `server.py:2384-2453` `local_candidate_is_accepted` | record + result + receipt sha + contract + lineage exact match |
| Decomposition label | `server.py:2336-2381` `local_decomposition_stage` | `human_action_required` branch `:2350-2366`, review_pending/authorized evidence `:2368-2381` |
| State override | `server.py:2483-2489` | accepted -> `complete`; launch or decomposition label -> `active` |
| Worker/launch binding | `server.py:2288-2334` `bound_local_launch`, `:2143-2164` `bound_local_worker`, `:2196-2286` `bound_local_crew` | all require `record.worker_id`; none apply to accepted or handoff records |
| Node lines | `server.py:2704-2741` (active/accepted/review-ready), `:1990-2124` `node_lines` (aggregate) | |
| Parent aggregation | `server.py:2745-2775` | gate `:2747-2750`; children filter `:2753-2757`; `children_total` from contract `:2764`; `local_completion_only` `:2766`; state `aggregate` `:2773` |
| Activity reducer | `Pipeline/TaskReviewAgent/GauntletView/pipeline_activity.py:110-176` | counts `:118-127`, `terminal` `:128`, branch ladder `:129-142`, counters `:169-173` |
| HTTP | `server.py:3588-3593` `_state`, `:3607-3610` `/api/state` | `human_actions` only from `approval` (None for local) |
| Browser | `index.html:537-550` `labelFor`, `:767-804` `updateLegend`, `:822-876` sample/validation, `:884-905` `renderPipelineActivity`, `:907-927` `updatePipelineTimers`, `:1079-1170` `showDetail` | |

## Findings

### F1 (proven, medium) Automatic decomposition handoff is still projected as "Task Needs You"; the new `human_action_required` branch is dead code on real records

- File: `Pipeline/TaskReviewAgent/GauntletView/server.py:2363` (branch `:2350-2366`).
- Trigger: a decomposition worker publishes its reviewed handoff (Issue workflow -> `human_action_required` /
  `decomposition_apply_authorization`). `update_issue` (`local_rehearsal.py:1337-1339`) mirrors the record to
  `state=pipeline_stage=human_action_required`, worker/lease None, and `_save` (`:733`) stamps
  `record.last_event_id` with the local journal hash. The handoff projection (`:1224`) carries the Issue
  workflow's `last_event_id`. The candidate's branch requires
  `workflow.last_event_id == record.last_event_id` (`server.py:2363`), i.e. equality across two unrelated id spaces.
- Observed (archived Claude run, `g8-claude-20260909-0650`): Issue 1 workflow `last_event_id`
  `50b17873...` is not any journal `event_id` (`in_journal: False` in `dump_g8.out`); the record entered
  `human_action_required` at journal event 52 (07:08:15Z, worker/lease None, `last_event_id e3ffef25...`) and only
  reached `decomposition_review_pending` at event 53 (07:08:37Z). Replaying the event-52 record through the
  candidate (`handoff_stage.py`) gives `local_decomposition_stage -> None`, `task.state -> human_action`
  ("Task Needs You" in `STATES`, `index.html:272`), and the activity headline "Local pipeline blocked"
  (`pipeline_activity.py:127,134-135`). The same record with `last_event_id` forced equal to the workflow id
  yields "Checking decomposition for automatic application", proving the clause is the only blocker.
- Expected: during the machine-owned interval the node should read "TASK WORKING (DECOMPOSITION) / Checking
  decomposition for automatic application" and the headline "automatic decomposition in progress" (which the
  candidate does produce from event 53 onward).
- Why the tests pass: `decomposition_transition_view_test.py:30-49` hand-sets both the workflow and the record
  `last_event_id` to `"d"*64`; `test_real_local_snapshot_shape_projects_exact_handoff` checks only the
  snapshot shape. No test builds the record through `update_issue`/`_save`.
- Repair (minimal): delete the `last_event_id` clause at `server.py:2363`; the remaining bindings
  (head_commit == record.source_commit, contract sha, actor human, human_result None, worker/lease None,
  `route.work_type == decomposition`, `local_decomposition_apply` true) already identify the handoff. If an exact
  event binding is wanted, compare `workflow.last_event_id` with the newest `workflow_transition` journal event
  for the task instead, and fix the test fixture to use distinct ids for the two spaces.
- Impact: the operator-reported symptom "Task Needs You during automatic decomposition" persists for one
  scheduler refresh (22 s in the archived run; unbounded if the scheduler is stalled, e.g. after the
  `failed_child` stop described in the brief). The bundle's claim "Preserve decomposition display" is only true
  from `decomposition_review_pending` onward.

### F2 (proven, medium) Locally accepted tasks are captioned "Task Complete" (production delivery claim) in the detail pane and vanish from the legend counts

- Files: `server.py:2485` (state `complete`), `index.html:292-293` (`STATES.complete` = "Task Complete",
  hint "committed TaskGraph conformance evidence proves delivery"), `index.html:1081,1086` (detail pill uses
  `STATES[task.state].label`), `index.html:775` (`updateLegend` skips `complete` in local mode).
- Trigger: any accepted local candidate (`local_candidate_is_accepted` true).
- Observed (`dom_harness.cjs`): with five local tasks (`complete`, `local_review_ready`, `aggregate`,
  `blocked`, `ready`) the legend has no "Task Complete" row and its counts sum to 4; the detail pill for the
  accepted task reads "Task Complete" with the production hint. The node label itself is correct
  ("LOCAL ACCEPTED / Integrated into local Source", `server.py:2739`).
- Expected: the bundled test name `test_accepted_candidate_leaves_review_without_production_claim` describes
  the intent, but it only asserts server fields (`task["state"] == "complete"`, `run.complete False`,
  `counters.completed None`). The browser makes the production claim anyway, and the accepted count is shown
  nowhere (the `local_accepted` counter emitted at `pipeline_activity.py:172` is not rendered).
- Repair: give local acceptance its own state key (e.g. `local_accepted`) with a local-only legend row and
  pill label, mirroring how `local_review_ready` is handled (`index.html:274,774`); or in local mode override
  the `complete` label/hint and stop skipping it at `:775`. `validPipelineActivity` needs no change.
- Note: the local-mode skip at `:775` predates the candidate (baseline `index.html:778`), but the candidate
  is the change that first routes local tasks into `complete`.

### F3 (proven, low) An unsettled decomposed parent makes the activity headline "Local pipeline activity unavailable"

- File: `Pipeline/TaskReviewAgent/GauntletView/pipeline_activity.py:128-142`.
- Trigger: parent `aggregate` with `children_complete < children_total`, plus children whose states are only
  `complete`/`local_review_ready` (no active, blocked, ready, or automatic task). This is exactly the first
  snapshot built by the bundled `test_parent_counts_only_locally_accepted_children` (parent 1/2, NSC-1013
  accepted, NSC-1014 review-ready), which asserts parent fields but not the activity.
- Observed (`parent_partial.py`, `mixed_states.py`): `review_ready + accepted + settled_parents (0) != len(tasks)`
  so `terminal` is false; no earlier branch matches; result `stage="unknown"`, headline "Local pipeline activity
  unavailable". Same in the baseline reducer, so it is pre-existing, but the candidate rewrote this ladder and the
  bundle claims it now "report[s] local activity accurately".
- Expected: "Local pipeline idle" (nothing is running; a candidate awaits integration/review).
- Repair: count unsettled aggregate parents explicitly, e.g. `parents = sum(t["state"] == "aggregate" ...)` and
  use `elif review_ready or accepted or parents: stage/headline = local_review_ready / "Local pipeline idle"`
  before the `unknown` fallback; keep `terminal` as is.

### F4 (proven, low) Aggregate summary line never names review-ready or accepted children

- File: `server.py:1999-2009` (`node_lines` status tuple).
- Trigger: local parent with a child in `local_review_ready` (or `complete`).
- Observed: "1/2 children locally accepted" with no status suffix for the review-ready child
  (`parent_partial.py`; `children_by_state` = `{complete:1, local_review_ready:1}`); the tuple only knows
  production states. Harmless but the operator cannot see from the node that the other child is waiting for
  integration.
- Repair: add `("local_review_ready", "local review ready")` to the tuple (and optionally `("complete", ...)`
  is already summarised by the count).

### F5 (question, low) Manual (non-automatic) human handoff is headlined "Local pipeline blocked"

- File: `pipeline_activity.py:127,134-135`. With `local_decomposition_apply=false` a decomposition handoff is
  correctly a `human_action` node ("Task Needs You"), but it is folded into `attention` and the headline says
  "blocked". Whether "blocked" is acceptable wording for "waiting on you" is an operator call; noted only
  because the candidate reordered `attention` above `waiting`.

## Disproved suspicions

1. An unaccepted candidate can be displayed as accepted. Disproved for every constructed input
   (`accept_cases.py`, 19 cases, 0 mismatches): queued-not-integrated (fails `pipeline_stage` `:2391`), queued
   with a stale lineage entry, integrated-for-another-task with forged record fields (fails the lineage
   `task_id`/receipt match `:2447-2453`), receipt body edited / `receipt_sha256` replaced / consistently
   re-hashed receipt (`:2411-2417` and lineage sha), lineage entry with a different candidate identity, applied
   tree differing from `record.source_tree`, contract rewritten in manifest only or manifest+record
   (`:2437-2438`), foreign `source_base` (`:2443-2446`), blocked record with stale receipt, auto-accept flag
   off, reordered `final_actual_changed_paths`. Positive controls (plain acceptance, second candidate for the
   same task, candidate based on the initial commit integrated after a D1C) return true. Contract rewrite of an
   accepted task is additionally unreachable: `rebind_after_local_decomposition` refuses rewrites that reach a
   started task (`local_rehearsal.py:916-921`).
2. Original task records lack `task_id`, so the predicate could never fire. Disproved: `open()` writes
   `task_id` (`local_rehearsal.py:300`); archived records carry it.
3. Receipt hash instability across JSON (tuple vs list `changed_paths`). Disproved: `body()` already emits a
   list (`local_candidate_commit.py:57`); round-trip check in `accept_cases.py`.
4. Children can be lost from the tasks list. Disproved: D1C admits child records in the same locked write that
   revises the manifest (`local_rehearsal.py:1102-1110`); `_load_unlocked` fails closed unless
   `set(state.tasks) | pending_children == set(manifest.task_ids)` (`:697-698`) and `_require_manifest`
   requires a contract per task id (`:139-141`); `build_local` iterates every record (`server.py:2477`) and
   `run.targets` lists them all; no admission allowlist filters the viewer. Archived Claude state: NSC-1013/1014
   present with `parent: NSC-898` contracts (handoff replay [59] shows `children_total 2`, targets include both).
5. `children_total` undercounts when a child is missing or foreign. Disproved: total now comes from the
   contract (`:2764`), foreign children (parent mismatch) are excluded from `children` (`:2756`), so a missing
   or foreign child keeps the parent "IN PROGRESS" (bundled test `test_missing_or_foreign_child_cannot_complete_parent`
   and `mixed_states.py`).
6. Child accepted then parent re-decomposed. Unreachable: an applied parent is `local_review_ready`, not in
   `_DISPATCHABLE_STATES` (`local_rehearsal.py:1381`); authorization requires `human_action_required` (`:829-835`).
7. Review-pending / applying / applied stages mislabelled. Disproved with archived evidence shapes
   (`handoff_stage.py` [53] "Checking decomposition for automatic application", [58] "Applying decomposition",
   [59] aggregate "DECOMPOSED · CHILDREN IN PROGRESS / 0/2 children locally accepted · 2 unstarted"). Blocked
   refusal is `state=blocked` with `local_decomposition_refusal` surfaced as `reason` (`server.py:2676`).
8. Omitted timer nodes throw / later values never appear. Disproved (`dom_harness.cjs` with a DOM that returns
   null for missing ids): both omitted -> no throw; stage-only; both later available ("0m 28s"/"0m 43s");
   terminal frozen; values withdrawn -> spans removed (`index.html:912-917`). The unguarded
   `pipeline-freshness` read (`:919-920`) throws only if something other than `renderPipelineActivity`
   rewrites the body while a sample is held; the only other writer `showActivityUnavailable` nulls the sample
   first (`:833`). `node --check` of the inline script passed.
9. Duplicate counters/status text. Disproved: the candidate removed the counter grid and duplicated
   provider/model/liveness text from `renderPipelineActivity` (review.diff hunk at `index.html:877-905`); legend
   and run stats remain the single place for counts.
10. `state_map` raises on a mirrored workflow state. Disproved: `WorkflowState` values are
    agent_ready/agent_working/human_action_required/blocked/complete (`issue_workflow.py:60-65`); `update_issue`
    refuses COMPLETE (`local_rehearsal.py:1325`); all others are mapped (`server.py:2467-2476`).
11. A human approval button could appear on an automatic handoff. Disproved: `build_local` emits no
    `human_actions`; `_state` adds them only from `approval`, which is None for local runs (`server.py:3588-3593`).
12. `worker_id`/`lease_id` are still set at the handoff so the branch could never match anyway. Disproved:
    journal event 52 shows worker/lease None, and `record_local_decomposition_review_pending` requires None
    (`local_rehearsal.py:846`); the sole blocker is the id-space mismatch (F1).

## Answers

1. Unaccepted shown as accepted: no. Every adversarial input evaluated false; the predicate requires the
   record's post-integration fields, a self-consistent receipt, contract and result hash agreement, and an exact
   lineage entry (task, plan, candidate commit/tree, receipt sha, applied commit/tree). See disproved 1-3.
2. Parent counting: `children_total` is the contract's list, `children_complete` counts only present children
   with matching `parent` and state `complete`; missing/foreign/blocked children keep the parent in progress
   and appear in `children_by_state`. Children cannot be lost from the tasks list (disproved 4). The only gaps are
   presentational: review-ready children are not named in the summary (F4) and an unsettled parent turns the
   activity headline into "unavailable" (F3).
3. Handoff labeling: `human_action_required` with a bound workflow still reads "Task Needs You" and the
   headline "Local pipeline blocked" in every real run because of the id-space mismatch (F1, proven with the
   archived journal). `decomposition_review_pending` and `decomposition_apply_authorized` are labelled
   automatic; `decomposition_applied` becomes the aggregate parent; a refusal becomes "Task Blocked" with the
   refusal text. "Task Needs You" is correct only when `local_decomposition_apply` is false or the workflow
   identity really differs.
4. Timers/counters: verified with `node --check` and a null-returning DOM; no throw when spans are omitted,
   later values render, terminal samples freeze, withdrawn values remove spans; no duplicate counters remain.
   The bundled 25-test activity suite passes.
5. Terminal/headline: accepted only -> `local_accepted`/"Local task work accepted" (terminal); accepted +
   review-ready -> `local_review_ready`/"Local pipeline idle" (terminal); any blocked/failed/human_action ->
   "Local pipeline blocked" (not terminal); any ready -> idle (not terminal); automatic decomposition ->
   "automatic decomposition in progress". An aggregate parent with all children accepted counts as settled; a
   parent with 0 of N (children ready/blocked) is carried by its children's states; a parent with an
   unsettled mix of accepted/review-ready children, or a 0-child parent (unreachable via
   `rebind_after_local_decomposition`), falls to "Local pipeline activity unavailable" (F3).
