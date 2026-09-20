# NSC-1165 needs_human fix: implementing agent's final report

Received 2026-09-13 about 15:35 UTC and recorded in substance by the coordinating session. The coordinating session's independent verification is recorded separately.

## Commit

- SHA `eb3beb75eeb8c4967594cd05877f64f86832781d`, parent `86068e6490c33bb71b025cbe1b6de204859a24af`, branch `throughput/decomposition-needs-human-fix`, worktree `C:\nscrev\decomp-needs-human-fix`.
- `decomposition.py` +160/-12, `graph_controller.py` +8/-0, `viewer.py` +36/-1, new `test_decomposition_needs_human.py` +913. All files `i/lf w/crlf`; `git diff --cached --check` clean.
- Cherry-picked unchanged into the combined proof branch `throughput/worker-and-decomposition-fixes`, head `ade5bca50d452b276a32f31a7ad8baeb770b2404`.

## What changed

1. `_authenticated_run_result` runs for every status before any proposal artifact is read. It checks a clean Source on the same branch, the recorded commit as an ancestor of HEAD, unchanged TaskGraph inputs, the artifact root bound to the record, the identity fields (`schema_version`, `mode`, `run_id`, `task_id`, `provider_order`, `max_calls` 2, independence, authority), `source_identity` head and tree, and the contract sha and revision.
2. `_verify_review` keeps its name and signature. It is the shared authentication plus `_review_ready_proof`: `calls_used` 2, `decision` decomposed, empty findings and rejections, then the artifact loads, then the unchanged remainder.
3. `_needs_human_proof` requires both proposal paths present and null, `calls_used` an exact integer within 0..max_calls with booleans refused, `author_corrections_used` null, 0 or 1, `rejection_reasons` a list of non-blank strings, each finding valid under `ReviewFinding.from_dict`, and at least one finding or reason.
4. `run()` records `status: needs_human`, `completed_at_utc`, `exit_code: 0` and a bounded `needs_human` block, then returns. The block holds rejection_reasons, unresolved_findings, human_next_step, calls_used, author_corrections_used, and latest_candidate limited to version, author_provider, sha256, decision and graph_delta_plan_id. Any other status or mismatch fails as before.
5. `inspect()` re-derives the needs_human facts read-only and raises on a mismatch. `apply()` is unchanged and refuses anything but review_ready.
6. Background execution needed no change: `succeeded` receipt, `completed` index, harvested `result_status` needs_human. Proven end to end in-process with a real launch, real `_child_main`, real `decomposition.run` and real harvest; only the Job Object calls and the compose container were faked.
7. Planner: one 8-line branch puts the parent in `waiting_human` as `{task_id, reason: decomposition_needs_human, run_id, artifact_root}`. It is never an action, never blocked, never retried, and it ends before the auto-approve code.
8. Viewer: `human_action`, phase `decomposition_needs_human`, a `human_reason`, and a transition context repeating the reason. A record with no reason shows the existing blocked `decomposition_record_invalid`. An extra guard beyond the brief: a running auto-approve Gauntlet controller used to relabel a synthetic `human_action` row as `active`/`automatic_validation`, and needs_human rows are now excluded.

## Proof that review_ready is not weakened

- The diff moves lines into `_review_ready_proof` without deleting any. Only the order changed, identity before artifact loads, so with several simultaneous defects the first reported error can differ.
- Differential probe: the exact 86068e6 `decomposition.py`, byte-checked against `git show`, loaded beside the fixed module, with both `_verify_review` versions run on 101 single-defect cases. 100 of 101 outcomes were identical: 5 equal review dicts, and the rest the same exception type and message across 52 distinct refusal messages. The one difference is a needs_human run result with no artifacts, which both refuse. Base says "Decomposition result is not one exact regular file"; the fix says "run_status is 'needs_human', expected 'review_ready'".

## Failing-before at 86068e6

The module was copied byte-for-byte with no shim. Base: `Ran 19 tests`, `FAILED (failures=35, errors=4)` counted per subtest; 15 tests fail and 4 pass. All 19 pass on eb3beb7.

| Test | At 86068e6 |
|---|---|
| test_needs_human_run_is_recorded_as_human_review_and_returned_without_raising | ERROR: the live incident ValueError |
| test_retained_facts_are_bounded_to_stated_reasons_counts_and_candidate_identity | ERROR: same ValueError |
| test_either_an_unresolved_finding_or_a_rejection_reason_is_a_stated_reason | ERROR in 2 subtests: same ValueError |
| test_needs_human_with_another_identity_still_fails | FAIL 11/11 subtests, weak: message only |
| test_needs_human_that_states_no_reason_still_fails | FAIL 5/5 subtests, weak: message only |
| test_needs_human_that_names_proposal_artifacts_or_overspends_still_fails | FAIL 6/6 subtests, weak: message only |
| test_any_other_run_status_still_fails_the_proposal | pass, guard |
| test_inspect_revalidates_the_retained_needs_human_facts_read_only | FAIL 5/5: base inspect did not validate |
| test_apply_refuses_a_needs_human_record | pass, guard |
| test_review_ready_run_is_still_recorded_review_ready_with_its_exact_proof | pass, guard |
| test_review_ready_record_whose_run_says_needs_human_is_never_applicable | pass, guard |
| test_needs_human_parent_waits_for_a_person_while_unrelated_work_continues | FAIL: waiting_human empty |
| test_needs_human_parent_alone_leaves_the_plan_awaiting_human | FAIL: parent blocked |
| test_run_loop_ends_awaiting_human_and_auto_approval_never_acts | FAIL: run ended blocked |
| test_needs_human_decompose_job_succeeds_harvests_completed_and_waits_for_a_person | FAIL: receipt failed with the live ValueError |
| test_needs_human_record_projects_human_action_with_its_stated_reasons | FAIL: state ready |
| test_needs_human_record_that_states_no_reason_is_not_authenticated | FAIL: state ready |
| test_running_auto_approve_controller_leaves_a_needs_human_parent_on_the_person | FAIL: relabelled active/automatic_validation |
| test_preflight_plan_with_a_waiting_human_decomposition_projects_consistently | FAIL: waiting_human reasons empty |

## Suites on eb3beb7, run sequentially

- test_decomposition_needs_human: Ran 19 tests in 135.927s, OK
- test_decomposition: Ran 26 tests in 179.778s, OK
- test_graph_controller: Ran 33 tests in 140.861s, OK
- test_viewer: Ran 39 tests in 153.816s, FAILED (errors=1). Pre-existing: base gives Ran 39 tests in 175.150s, FAILED (errors=1), same test `test_build_projects_timing_for_the_in_scope_task_named_by_the_controller`, same TypeError.
- test_background_jobs: Ran 81 tests in 662.049s, OK
- gauntlet_view_smoke_test.py: Ran 148 tests in 10.143s, FAILED (failures=3). Pre-existing: base shows the identical three failures, which are string checks against GauntletView's index.html and server.py.
- approval_smoke_test.py: Ran 10 tests in 0.098s, OK, and OK at base.

## Corrections to the brief

- For NSC-1165 the first gate is the failed ticket, `background_job_failed`, before the decomposition branch runs. Only after clearing the ticket does the failed record block as `decomposition_failed`.
- At base a needs_human record already landed in `blocked` with the same reason string, through the generic fallback.
- The brief missed the viewer's auto-approve relabel path.

## Residual risks

- NSC-1165 is not migrated. A relaunch at the same Source head is refused because the run id is fixed per head and the run directory exists. An operator must clear the ticket and archive the record and run directory, or wait for Source to move. The live run result bytes pass the new proof, and the test fixture is JSON-equal to the live file.
- A needs_human `inspect()` fails closed after any later TaskGraph change, with "TaskGraph inputs changed after the decomposition proposal". `run()` records a needs_human run as failed if Source moved during the run.
- The `decompose` CLI still exits 1 for anything but review_ready (`__main__.py:495`); it now prints the needs_human record.
- The viewer headline for every `human_action` row still reads "Test the exact candidate in Unity...", decomposition rows included.
- `waiting_human` now has two entry shapes, candidate and decomposition.
- A finding outside the D1B.2 schema makes the proposal failed.
- The background-job test runs only on Windows.
- Merge conflict risk with the routing fix is limited to the 8-line plan() hunk; the cherry-pick was clean.

## Proposed documentation text

README.md, after the decomposition-boundary paragraph:

> A proposal can also end `needs_human`: the D1B.2 circuit stopped at its human authority boundary, for example after a reviewer revision on the last allowed call, which its own author may not approve. That is a completed proposal, not a failure. `decompose` authenticates the run result exactly as for `review_ready`. It then requires both proposal artifact paths to be null, `calls_used` within `max_calls`, and at least one unresolved finding or rejection reason, and records `status: needs_human` with a bounded `needs_human` block. Nothing is applied: `apply-decomposition` refuses anything but `review_ready`, and `inspect-decomposition` re-derives the retained facts read-only. The command still exits 1 because no applicable plan exists.

README.md, graph controller section:

> A decompose job whose proposal ends `needs_human` gets a `succeeded` receipt and a `completed` index with `result_status: needs_human`. The planner lists the parent in `waiting_human` as `{task_id, reason: decomposition_needs_human, run_id, artifact_root}`. It is never an action, never blocked and never relaunched, and Gauntlet auto-approval cannot act on it. Unrelated tasks keep moving; the plan is `awaiting_human` only when nothing else is actionable. The viewer shows the parent as Task Needs You (`human_action`, phase `decomposition_needs_human`) with its rejection reasons and unresolved finding ids.

CURRENT.md, new dated entry:

> Decomposition needs_human, 2026-09-13. NSC-1165's decomposition ended `needs_human` as designed, but AssistantControl required the success-only `decomposition_result.json` before reading the run status, so the record, receipt and ticket landed `failed`. Fixed in eb3beb7: the run result is authenticated for every status first, and `needs_human` is recorded as a human-review state, harvested `completed`, planned into `waiting_human` and shown as `human_action`. The `review_ready` checks are unchanged. NSC-1165's existing failed record, ticket and run directory are not migrated.
