# TaskControl current-state migration

The implementation makes committed TaskControl selection, contract applicability, and additive lifecycle events authoritative for delivery and eligibility. Old task names and unrelated delivery artifacts no longer select a current implementation. Selected evidence still has to prove its exact Git objects, contract, validation policy, epoch, artifact hashes, and required approval.

The isolated checkout is `C:\NSC\TaskControlCurrentState-20260907`, on `taskcontrol-current-state`, created from the fetched `origin/main` commit `73fae3818ded52eec10e12230de7403cafda4081`. The active operator checkout was only inspected to locate the remote and guidance. No live Issues, claims, containers, workers, or gauntlet runs were operated. Nothing was pushed or merged.

## Audit and replacement rules

| Original rule / assumption | Canonical replacement |
| --- | --- |
| `current_conformance.py` loaded every task delivery record and `_maximal` inferred the current one from validated-commit ancestry. Old records could make a new revision delivered/stale/ambiguous without an explicit current selection. | `taskcontrol_state.current_selection` resolves the committed selection first. No selection means `not_delivered`; only the selected record and its required revalidation basis chain are evaluated. Ancestry validates an explicit reference rather than choosing one. |
| The history-identity CI workflow required NSC-020 to remain conformant with `DEL-NSC-020-5827effabf60`. A deliberate reset/revision could violate that permanent historical expectation. | All three affected workflows run `taskcontrol.py validate-current --source .` against the exact checked-out PR head. Existing history-identity object/tree audit remains in place. |
| The synthetic-gauntlet test fixture used the checkout's real Tasks and reconstructed fixtures by deleting the entire 911â€“990 range. It depended on a particular historic/current installation, including assumptions about partial existing contracts. | The test fixture owns a complete, deterministic, small input graph. A regression poisons the unrelated checkout with historical synthetic IDs and verifies unchanged fixture output. The production installer still refuses to overwrite existing contracts. |
| Acceptance-harness prose described NSC-900â€“999 as a permanently reserved range outside production. | IDs are local fixture-manifest identities. History does not reserve them. |
| Thirteen admission/execution/decomposition/accounting/launcher regexes admitted exactly three digits although TaskGraph already admitted three or more. | These boundaries preserve full IDs of at least three digits. NSC-1000 now passes the same admission path without aliasing or truncation. Invalid or command-shaped IDs remain rejected. |
| The dispatch policy's known-state list could not represent newly canonical `retired`/`excluded` states. The bulk reader would reject the entire snapshot. | Both states are recognized but remain absent from fresh-eligible and dependency-satisfied sets. CLI filters also expose them. |

The audit did **not** find a general CI rule that reserves every task ID found in commit messages. The actual historical inferences above were repaired. Other Git history scans were classified rather than removed: immutable record/event path checks; exact commit/tree translation; decomposition replay/undo ancestry; operational branch/claim inventories; Git author audits; and publication boundaries remain safety or audit checks. Reusing an immutable evidence **path** is still forbidden; reusing a task through a new epoch and evidence path is supported.

## Schema, commands, and publication

`TASKCONTROL_CURRENT.json` is a one-time generated activation marker with schema, fixed authority name, exact migration base commit, and 14 frozen legacy selections. It was produced by `taskcontrol.py migrate-current`, not manually authored. Its edits or deletion fail validation after activation.

`taskcontrol.py transition` is the single host-owned lifecycle writer. `reset`, `retired`, `cancelled`, and `excluded` append an event and advance the epoch; `select --record-id` appends an exact selection in the current epoch. Every event has a contiguous revision, predecessor semantic hash, base commit, contract binding, operation, disposition, and reason. Publication exclusively creates the next file. The command requires a clean checkout and rechecks HEAD and cleanliness before publication. It does not invoke Git mutations or execute task-provided commands.

Selection binds record ID/hash, task ID, contract revision/hash/path, tested and delivered 40-character commits, lifecycle epoch, and a fixed validation-policy identity with a hash of the task's completion gates and authoritative policy entry. New selected evidence must match the tested contract and policy, and the tested commit must contain the exact epoch-start event. Reset/revision does not delete old commits or records. A contract revision is committed before the canonical transition can bind it; an old selection with a mismatched contract fails closed until reset/selection is committed.

The delivery packager calls the same planner. Its exact path list includes the selection event; draft validation compares the staged event to the canonical plan alongside the record/artifacts. Existing authorization, resource, dependency, decomposition and publication checks remain additional gates. A lifecycle reset grants no execution authority and performs none of the separate operational reset helper's cleanup.

`validate-current` reconstructs the complete TaskGraph from committed Git objects, validates graph invariants, and evaluates every task in numeric ID order using one captured HEAD. It rejects malformed current records and orphan selections. It ignores uncommitted content. Unstarted tasks are valid repository state. Schedulers retain the existing bulk TaskControl JSON reader. No visualizer implementation or visualizer-state suite exists at the captured baseline; no separate lifecycle model was added.

## Compatibility and limits

Repositories that predate the activation marker retain the original evidence semantics for historical inspection. Once a marker exists, it cannot be removed to fall back. The migration freezes valid legacy selections, including `needs_replan`/`needs_testing`; it does not manufacture passing results. Existing approved, tree-preserving history-identity translations remain supported without editing old record bytes.

Git objects and artifact hashes prove exact committed provenance under the existing review trust model. This change does not add signed test attestations or rerun Unity from task data. A new selection is not an arbitrary `complete` flag. Existing record-schema, gate, artifact, historical contract, canon, surface, topology and human-approval checks still determine whether it is conformant. Revalidation basis records remain subject to their historical provenance checks even though only the explicit selection controls current applicability.

All execution in this work used temporary Git fixtures and local validation snapshots. No Unity editor/test runner, external provider, live scheduler launch, or acceptance gauntlet run was invoked. The missing baseline quick/width/thousand suites were covered by new deterministic width and repository tests; existing scheduler, dispatch, decomposition, identity, reset/rehearsal and acceptance-harness suites were exercised.

## Final commit

- Commit: `420665fa1be2d1c5415df42daef19b1b3eefc782`
- Exact parent: `73fae3818ded52eec10e12230de7403cafda4081`
- Tested tree: `e31f42da757572811b56e2ad39b2132e52cea7ef`
- Author and committer: `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`
- Checkout clean: `True`; pushed: `False`.

[Canonical validation of the exact final commit](C:/NSC/TaskControlCurrentState-evidence/final-head-validation.json) returned valid with zero failures.

## Exact audit references

Baseline line references refer to the exact parent SHA above. Current references refer to the final commit.

| Finding | Baseline | Current replacement / retained check |
| --- | --- | --- |
| Ancestry inferred selection from all records | [Pipeline/TaskGraph/current_conformance.py:201](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskGraph/current_conformance.py#L201) | [Pipeline/TaskGraph/current_conformance.py:325](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/current_conformance.py:325) |
| Every historical record entered current evaluation | [Pipeline/TaskGraph/current_conformance.py:330](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskGraph/current_conformance.py#L330) | [Pipeline/TaskGraph/conformance_records.py:269](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/conformance_records.py:269) |
| Permanent NSC-020 CI proof | [.github/workflows/history-identity-migration-dry-run.yml:373](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/.github/workflows/history-identity-migration-dry-run.yml#L373) | [.github/workflows/history-identity-migration-dry-run.yml:347](C:/NSC/TaskControlCurrentState-20260907/.github/workflows/history-identity-migration-dry-run.yml:347) |
| Fixture copied live checkout graph | [Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:161](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py#L161) | [Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:161](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:161) |
| Fixture expected a particular synthetic installation | [Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:174](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py#L174) | [Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:184](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py:184) |
| Production overwrite refusal retained | [Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py:486](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py#L486) | [Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py:486](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py:486) |
| Immutable evidence-path audit retained | [Pipeline/TaskGraph/validate_draft_evidence.py:257](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskGraph/validate_draft_evidence.py#L257) | [Pipeline/TaskGraph/validate_draft_evidence.py:258](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/validate_draft_evidence.py:258) |
| Scheduler recognition of inactive lifecycle states | [Pipeline/TaskReviewAgent/dispatch_policy.json:13](https://github.com/cathode26/NoSafeCircle/blob/73fae3818ded52eec10e12230de7403cafda4081/Pipeline/TaskReviewAgent/dispatch_policy.json#L13) | [Pipeline/TaskReviewAgent/dispatch_policy.json:23](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/dispatch_policy.json:23) |

Additional function-level line inventory: [audit-lines.json](C:/NSC/TaskControlCurrentState-evidence/audit-lines.json). New authority/schema implementation: [taskcontrol_state.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol_state.py:45); repository-wide validation: [taskcontrol.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol.py:24).

Exact task-ID width boundaries (the original three-digit restriction was widened in place):

| Path | Baseline line | Current line |
| --- | ---: | ---: |
| `Pipeline/ExecutionCrew/run_crew.py` | 46 | 46 |
| `Pipeline/TaskDecomposition/context_builder.py` | 33 | 33 |
| `Pipeline/TaskDecomposition/live_decomposition.py` | 361 | 361 |
| `Pipeline/TaskDecomposition/round_robin_decomposition.py` | 436 | 436 |
| `Pipeline/TaskDecomposition/run_reviewer_replay_ab.py` | 302 | 302 |
| `Pipeline/TaskExecution/contracts.py` | 17 | 17 |
| `Pipeline/TaskGraph/token_usage_metrics.py` | 13 | 13 |
| `Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1` | 3 | 3 |
| `Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1` | 4 | 4 |
| `Pipeline/TaskReviewAgent/contracts.py` | 15 | 15 |
| `Pipeline/TaskReviewAgent/reset_task.py` | 977 | 977 |
| `Pipeline/TaskReviewAgent/token_usage.py` | 18 | 18 |
| `Pipeline/TaskReviewAgent/worker_result.py` | 95 | 95 |

## Red-before and green-after evidence

The baseline proof restored the original evaluator, packager, draft validator, CLI, CI workflows and width validators from the exact parent. New tests and transition scaffolding were retained so the old behavior could be exercised. This was a separate disposable clone, not a change to the implementation branch. Compatibility and retained-defense tests are expected to pass before the migration; they are not claimed as behavior-changing red tests.

- [red-v2_Pipeline_TaskGraph_taskcontrol_current_state_smoke_test.py.log](C:/NSC/TaskControlCurrentState-evidence/red-v2_Pipeline_TaskGraph_taskcontrol_current_state_smoke_test.py.log): Ran 14 tests in 88.534s; FAILED (failures=19).
- [red-v2_Pipeline_TaskGraph_task_id_width_smoke_test.py.log](C:/NSC/TaskControlCurrentState-evidence/red-v2_Pipeline_TaskGraph_task_id_width_smoke_test.py.log): Ran 2 tests in 0.002s; FAILED (errors=2).
- [red-v2_Pipeline_TaskGraph_taskcontrol_repository_smoke_test.py.log](C:/NSC/TaskControlCurrentState-evidence/red-v2_Pipeline_TaskGraph_taskcontrol_repository_smoke_test.py.log): Ran 4 tests in 23.543s; FAILED (failures=3, errors=3).

The synthetic-fixture regression also failed against the original fixture builder because it depended on the unrelated checkout's graph. The scheduler-recognition test failed on the old policy's unknown `retired` state before that policy was fixed. A development regression test reproduced a falsely conformant revalidation with a bad basis canon hash, then passed after restoring basis provenance checks.

- [TaskControlCurrentState-red-v2-progress.txt](C:/NSC/TaskControlCurrentState-red-v2-progress.txt)
- [TaskControlCurrentState-red-scheduler.txt](C:/NSC/TaskControlCurrentState-red-scheduler.txt)
- [TaskControlCurrentState-red-basis.txt](C:/NSC/TaskControlCurrentState-red-basis.txt)

| Required scenario | Regression coverage |
| --- | --- |
| 1. Historical delivery, new unselected revision, dispatch | history_does_not_deliver_unselected_current_revision; dependencies_use_current_state_and_reset_task_is_dispatchable |
| 2. Exact new commit and matching evidence | exact_selection_reset_and_reselection; packager_and_draft_validator_use_same_state_writer |
| 3. Reset supersedes selection without rewriting history | exact_selection_reset_and_reselection (ancestry assertions for all prior commits) |
| 4. Old branches/messages/artifacts cannot override | history_does_not_deliver_unselected_current_revision; unselected_artifacts_cannot_override_current_state; superseded_invalid_artifact_is_not_current |
| 5–7. Foreign/unreachable/malformed/contract/evidence mismatch | selection_bindings_reject_corruption (8 subcases); unreachable_commit_present_in_object_database_fails_closed |
| 8. Forged complete or unsupported evidence | forged_current_selection_fails_closed; empty_validation_evidence_cannot_prove_delivery; selected_revalidation_checks_its_basis_provenance |
| 9. Current dependencies and children | decomposition_reads_current_child_selection; dependencies_use_current_state_and_reset_task_is_dispatchable |
| 10. Inactive tasks remain nondispatchable | inactive_states_never_become_delivered; inactive_tasks_do_not_poison_the_scheduler_snapshot |
| 11. Existing production records | legacy_production_record_compatibility; exact comparison of all 60 baseline/final task states and selected IDs |
| 12. Reused synthetic IDs and CI | gauntlet fixture independence; thousand_tasks_are_deterministic_with_reused_synthetic_history; ci_runs_canonical_candidate_validation_for_state_and_policy_changes |
| 13. Whole repository and deterministic HEAD | quick_profile_reads_only_candidate_head_and_does_not_mutate_git; repository_wide_validation_rejects_unrequested_task_forgery; thousand-task repeated validation |
| 14. No destructive Git operation introduced | quick-profile exact refs/history preservation; reset ancestry assertions; review of the read-only Git calls in taskcontrol_state.py |

## Full test results

**59 of 60 distinct suites pass** after targeted reruns. The acceptance harness has the exact same 14 pre-existing failures on baseline and candidate; 75 of its 89 checks pass on both. Every failure is the adapter rejecting the existing `scheduler_wait_source_refresh` event. This unrelated safety behavior was preserved. The final tree's 16 lifecycle tests pass. Repository validation reports `{"aggregate": 22, "conformant": 7, "needs_replan": 5, "needs_testing": 2, "not_delivered": 24}` across 60 tasks, with zero failures. Baseline and final `(state, selected_record_id)` mappings are identical for all 60 tasks.

The full run used clean committed snapshots. Later targeted snapshots reran checks affected by the scheduler policy and basis-validation corrections. The guarded final commit verified its staged tree exactly equals the final tested snapshot tree. Per-suite logs retain exact exit status and duration.

Initial test-harness problems were recorded and corrected: an environment-level Git identity override, missing `python3`, a reset fixture created inside a concurrently inspected checkout, and overly long Windows temporary paths. No failing harness run is counted as a passing suite. Temporary paths were shortened without changing production path guards or task eligibility.

| Suite | Result | Seconds | Log |
| --- | --- | ---: | --- |
| `Gauntlet/SoftwareArchitectAcceptance/acceptance_smoke_test.py` | Same baseline failure (75/89 pass) | 11.13 | [log](C:/NSC/TaskControlCurrentState-evidence/acceptance-candidate-all.json) |
| `Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py` | PASS | 463.88 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_ExecutionCrew_tests_execution_crew_smoke_test.py.log) |
| `Pipeline/ExecutionCrew/tests/prompt_blocker_policy_smoke_test.py` | PASS | 0.14 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_ExecutionCrew_tests_prompt_blocker_policy_smoke_test.py.log) |
| `Pipeline/HistoryMigration/history_identity_smoke_test.py` | PASS | 9.34 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_HistoryMigration_history_identity_smoke_test.py.log) |
| `Pipeline/HistoryMigration/issue_migration_smoke_test.py` | PASS | 1.03 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_HistoryMigration_issue_migration_smoke_test.py.log) |
| `Pipeline/HistoryMigration/migration_plan_smoke_test.py` | PASS | 0.33 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_HistoryMigration_migration_plan_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/context_builder_smoke_test.py` | PASS | 2.25 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_context_builder_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/decomposition_contracts_smoke_test.py` | PASS | 0.48 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_decomposition_contracts_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/gdd_rag_review_context_smoke_test.py` | PASS | 1.86 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_gdd_rag_review_context_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/live_decomposition_smoke_test.py` | PASS | 28.27 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_live_decomposition_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/review_contracts_smoke_test.py` | PASS | 0.37 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_review_contracts_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/reviewer_replay_smoke_test.py` | PASS | 4.35 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_reviewer_replay_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/round_invocation_id_smoke_test.py` | PASS | 0.47 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_round_invocation_id_smoke_test.py.log) |
| `Pipeline/TaskDecomposition/tests/round_robin_decomposition_smoke_test.py` | PASS | 22.02 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskDecomposition_tests_round_robin_decomposition_smoke_test.py.log) |
| `Pipeline/TaskExecution/tests/task_execution_smoke_test.py` | PASS | 0.68 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskExecution_tests_task_execution_smoke_test.py.log) |
| `Pipeline/TaskGraph/aggregate_conformance_smoke_test.py` | PASS | 1.69 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_aggregate_conformance_smoke_test.py.log) |
| `Pipeline/TaskGraph/bootstrap_inputs_smoke_test.py` | PASS | 1.35 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_bootstrap_inputs_smoke_test.py.log) |
| `Pipeline/TaskGraph/conformance_evaluator_smoke_test.py` | PASS | 76.39 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v4_Pipeline_TaskGraph_conformance_evaluator_smoke_test.py.log) |
| `Pipeline/TaskGraph/decomposition_graph_semantics_smoke_test.py` | PASS | 1.11 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_decomposition_graph_semantics_smoke_test.py.log) |
| `Pipeline/TaskGraph/graph_apply_materialize_smoke_test.py` | PASS | 7.59 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_graph_apply_materialize_smoke_test.py.log) |
| `Pipeline/TaskGraph/graph_apply_plan_smoke_test.py` | PASS | 3.48 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_graph_apply_plan_smoke_test.py.log) |
| `Pipeline/TaskGraph/graph_apply_smoke_test.py` | PASS | 199.68 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_graph_apply_smoke_test.py.log) |
| `Pipeline/TaskGraph/graph_delta_smoke_test.py` | PASS | 5.44 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_graph_delta_smoke_test.py.log) |
| `Pipeline/TaskGraph/graph_undo_smoke_test.py` | PASS | 93.31 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_graph_undo_smoke_test.py.log) |
| `Pipeline/TaskGraph/history_identity_migration_smoke_test.py` | PASS | 7.95 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_history_identity_migration_smoke_test.py.log) |
| `Pipeline/TaskGraph/migrate_task_contracts_v2_smoke_test.py` | PASS | 0.48 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_migrate_task_contracts_v2_smoke_test.py.log) |
| `Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py` | PASS | 0.46 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_phase1_execution_authority_smoke_test.py.log) |
| `Pipeline/TaskGraph/record_delivery_smoke_test.py` | PASS | 77.88 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_record_delivery_smoke_test.py.log) |
| `Pipeline/TaskGraph/task_contract_quality_audit_smoke_test.py` | PASS | 0.22 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_task_contract_quality_audit_smoke_test.py.log) |
| `Pipeline/TaskGraph/task_id_width_smoke_test.py` | PASS | 1.24 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_task_id_width_smoke_test.py.log) |
| `Pipeline/TaskGraph/taskcontrol_current_state_smoke_test.py` | PASS | 207.77 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v4_Pipeline_TaskGraph_taskcontrol_current_state_smoke_test.py.log) |
| `Pipeline/TaskGraph/taskcontrol_repository_smoke_test.py` | PASS | 13 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v5-linux.log) |
| `Pipeline/TaskGraph/taskcontrol_smoke_test.py` | PASS | 3.9 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_taskcontrol_smoke_test.py.log) |
| `Pipeline/TaskGraph/validate_draft_evidence_smoke_test.py` | PASS | 470.73 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_validate_draft_evidence_smoke_test.py.log) |
| `Pipeline/TaskGraph/work_graph_persist_smoke_test.py` | PASS | 0.35 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_work_graph_persist_smoke_test.py.log) |
| `Pipeline/TaskGraph/work_graph_transform_smoke_test.py` | PASS | 0.16 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_work_graph_transform_smoke_test.py.log) |
| `Pipeline/TaskGraph/work_graph_validate_smoke_test.py` | PASS | 0.21 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_work_graph_validate_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/actor_authorization_smoke_test.py` | PASS | 0.64 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_actor_authorization_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py` | PASS | 0.08 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v5_Pipeline_TaskReviewAgent_tests_ci_workflow_split_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/committed_task_loader_smoke_test.py` | PASS | 6.68 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_committed_task_loader_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/completed_issue_guard_smoke_test.py` | PASS | 0.53 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_completed_issue_guard_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/contention_retry_smoke_test.py` | PASS | 55.9 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v4_Pipeline_TaskReviewAgent_tests_contention_retry_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/decomposition_authorization_smoke_test.py` | PASS | 1.74 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_decomposition_authorization_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/dispatch_plan_smoke_test.py` | PASS | 69.78 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_TaskReviewAgent_tests_dispatch_plan_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/downstream_determinism_smoke_test.py` | PASS | 22.73 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_downstream_determinism_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/downstream_smoke_test.py` | PASS | 14.49 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_downstream_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/execution_routing_smoke_test.py` | PASS | 1.42 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_execution_routing_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/fresh_dispatch_smoke_test.py` | PASS | 105.28 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v4_Pipeline_TaskReviewAgent_tests_fresh_dispatch_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/git_identity_guard_smoke_test.py` | PASS | 1.73 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_git_identity_guard_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/host_decomposition_launcher_smoke_test.py` | PASS | 3.28 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_host_decomposition_launcher_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/launcher_preflight_smoke_test.py` | PASS | 0.61 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_launcher_preflight_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/polling_orchestrator_smoke_test.py` | PASS | 155.09 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_TaskReviewAgent_tests_polling_orchestrator_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py` | PASS | 2.66 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_prepare_synthetic_gauntlet_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py` | PASS | 11.99 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v4_Pipeline_TaskReviewAgent_tests_real_checkout_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/reset_rehearsal_task_smoke_test.py` | PASS | 7.16 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_reset_rehearsal_task_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/reset_task_smoke_test.py` | PASS | 245.17 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_reset_task_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/resource_reservation_smoke_test.py` | PASS | 1.36 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_resource_reservation_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/synthetic_gauntlet_approver_smoke_test.py` | PASS | 0.95 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_synthetic_gauntlet_approver_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py` | PASS | 250.3 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_task_review_agent_smoke_test.py.log) |
| `Pipeline/TaskReviewAgent/tests/workflow_runtime_smoke_test.py` | PASS | 0.74 | [log](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskReviewAgent_tests_workflow_runtime_smoke_test.py.log) |

Python/JSON/workflow PowerShell parsing: 42 checks PASS. Both changed launcher scripts also passed Windows PowerShell 5.1 parsing. `git diff --check` and staged `git diff --cached --check`: PASS.

No dedicated visualizer suite exists in the parent checkout; the canonical bulk state output, scheduler snapshot, aggregate/dependency tests and read-only inspection tests cover the available consumers. The quick and thousand-task tests are new. Acceptance-harness testing uses captured/injected scheduler observations and does not start a live gauntlet.

The complete acceptance comparison is recorded in [baseline checks](C:/NSC/TaskControlCurrentState-evidence/acceptance-baseline-all.json) and [candidate checks](C:/NSC/TaskControlCurrentState-evidence/acceptance-candidate-all.json); test names, pass/fail results, error types and messages match exactly. Real symlinks were tested on the existing Ubuntu runtime because Windows denied symlink creation. No Windows privileges or security settings were changed.

Both Windows repository-suite runs also passed ([run 1](C:/NSC/TaskControlCurrentState-evidence/candidate-v2_Pipeline_TaskGraph_taskcontrol_repository_smoke_test.py.log), [run 2](C:/NSC/TaskControlCurrentState-evidence/candidate-v3_Pipeline_TaskGraph_taskcontrol_repository_smoke_test.py.log)). They took over 20 minutes each under host load. The full four-test suite passed on Ubuntu in about 26 seconds, so CI retains quick checks in the existing Windows job and runs repeated thousand-task validation in a separate Ubuntu job.

## Every changed path

- [.github/workflows/d1b2-core-deterministic.yml](C:/NSC/TaskControlCurrentState-20260907/.github/workflows/d1b2-core-deterministic.yml)
- [.github/workflows/history-identity-migration-dry-run.yml](C:/NSC/TaskControlCurrentState-20260907/.github/workflows/history-identity-migration-dry-run.yml)
- [.github/workflows/task-review-agent-deterministic.yml](C:/NSC/TaskControlCurrentState-20260907/.github/workflows/task-review-agent-deterministic.yml)
- [Docs/AI-Pipeline/FRESH_TASK_RESET_RUNBOOK.md](C:/NSC/TaskControlCurrentState-20260907/Docs/AI-Pipeline/FRESH_TASK_RESET_RUNBOOK.md)
- [Gauntlet/SoftwareArchitectAcceptance/README.md](C:/NSC/TaskControlCurrentState-20260907/Gauntlet/SoftwareArchitectAcceptance/README.md)
- [Gauntlet/SoftwareArchitectAcceptance/acceptance_lib.py](C:/NSC/TaskControlCurrentState-20260907/Gauntlet/SoftwareArchitectAcceptance/acceptance_lib.py)
- [Pipeline/ExecutionCrew/run_crew.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/ExecutionCrew/run_crew.py)
- [Pipeline/TaskDecomposition/context_builder.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskDecomposition/context_builder.py)
- [Pipeline/TaskDecomposition/live_decomposition.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskDecomposition/live_decomposition.py)
- [Pipeline/TaskDecomposition/round_robin_decomposition.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskDecomposition/round_robin_decomposition.py)
- [Pipeline/TaskDecomposition/run_reviewer_replay_ab.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskDecomposition/run_reviewer_replay_ab.py)
- [Pipeline/TaskExecution/contracts.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskExecution/contracts.py)
- [Pipeline/TaskGraph/CONFORMANCE_RECORDS.md](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/CONFORMANCE_RECORDS.md)
- [Pipeline/TaskGraph/README.md](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/README.md)
- [Pipeline/TaskGraph/TASKCONTROL_CURRENT.json](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/TASKCONTROL_CURRENT.json)
- [Pipeline/TaskGraph/TASKCONTROL_CURRENT_STATE.md](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/TASKCONTROL_CURRENT_STATE.md)
- [Pipeline/TaskGraph/TASK_STATES.md](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/TASK_STATES.md)
- [Pipeline/TaskGraph/conformance_records.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/conformance_records.py)
- [Pipeline/TaskGraph/current_conformance.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/current_conformance.py)
- [Pipeline/TaskGraph/record_delivery.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/record_delivery.py)
- [Pipeline/TaskGraph/task_id_width_smoke_test.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/task_id_width_smoke_test.py)
- [Pipeline/TaskGraph/taskcontrol.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol.py)
- [Pipeline/TaskGraph/taskcontrol_current_state_smoke_test.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol_current_state_smoke_test.py)
- [Pipeline/TaskGraph/taskcontrol_repository_smoke_test.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol_repository_smoke_test.py)
- [Pipeline/TaskGraph/taskcontrol_state.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/taskcontrol_state.py)
- [Pipeline/TaskGraph/token_usage_metrics.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/token_usage_metrics.py)
- [Pipeline/TaskGraph/validate_draft_evidence.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskGraph/validate_draft_evidence.py)
- [Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1)
- [Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1)
- [Pipeline/TaskReviewAgent/contracts.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/contracts.py)
- [Pipeline/TaskReviewAgent/dispatch_policy.json](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/dispatch_policy.json)
- [Pipeline/TaskReviewAgent/reset_task.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/reset_task.py)
- [Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/tests/prepare_synthetic_gauntlet_smoke_test.py)
- [Pipeline/TaskReviewAgent/token_usage.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/token_usage.py)
- [Pipeline/TaskReviewAgent/worker_result.py](C:/NSC/TaskControlCurrentState-20260907/Pipeline/TaskReviewAgent/worker_result.py)

## Remaining uncertainty

GitHub Actions itself was not executed because this branch was not pushed. Local canonical validation and migration regressions passed; the acceptance harness retains its separately proven baseline failure described above. Unity was not run because the change is Python/PowerShell infrastructure and no Unity behavior or assets were changed. Legacy activation is intentionally one-time; subsequent changes must append canonical transitions.
