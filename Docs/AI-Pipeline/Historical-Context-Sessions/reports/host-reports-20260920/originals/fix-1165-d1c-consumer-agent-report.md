# NSC-1165 requirement 4 (D1C consumer): implementing agent's final report

The D1C developer's report, received 2026-09-13 at about 20:58 UTC. The coordinating session checked the commit identity, files and whitespace. Its own independent test runs will be recorded with the integrated head.

## 1. Commit

- SHA `4dce423b36b22d13df86c52e4b21bfde7cf6d699`, branch `throughput/decomposition-d1c-consumer`, worktree `C:\nscrev\d1c-consumer-fix`. The worktree is clean and the branch has no upstream and was not pushed.
- Parent `aac5ecef30c4050bd78c122a259d753d0a791b8f`, a cherry-pick of C0 `f941857` with the same tree.

| File | + | - |
|---|---|---|
| `Pipeline/TaskReviewAgent/decomposition_authorization.py` | 114 | 4 |
| `Pipeline/TaskReviewAgent/local_decomposition_apply.py` | 6 | 0 |
| `Pipeline/TaskReviewAgent/tests/decomposition_authorization_revision_review_smoke_test.py` (new) | 706 | 0 |
| `Pipeline/TaskReviewAgent/tests/local_decomposition_apply_revision_review_test.py` (new) | 358 | 0 |

`git diff --check` is clean, and all four files are `i/lf w/crlf`. The C0 fixture API matches design D1. C0 also adds `write_artifact_mapping`, finding helper functions and a JSON-copy `forge`; none of these affect D1C.

## 2. How C1 and C2 are implemented

- **`_call_accounting_valid`**
  - The int, call-limit and `2 <= calls_used <= max_calls` checks are unchanged.
  - A new `_exact_bounded_counter` reads an absent counter as 0. A present counter must be an exact int: 0 or 1 for revision reviews, 0 for author corrections.
  - When the revision count is 1, it requires `max_calls == 2`, `calls_used == 2` and the correction key present.
  - Rounds must number `calls_used + rev`, and history entries `calls_used - 1 + rev`.
  - Failures report `bounded_call_accounting_invalid`.
- **`_revision_review_shape_invalid`** is new.
  - It checks the nine design conditions, plus fail-closed guards for non-object rounds or candidates and non-int round numbers or versions.
  - It runs only when accounting passed and the count is exactly 1, and it still runs when the provider order is invalid.
  - It reports `round_sequence_inconsistent`.
- **`_independent_codex_roles`** returns False unless the revision count is absent or an exact int 0.
- **Round-3 invocation id: no code change.** The existing check already derives the id and the `rounds/NN` directory from the approving round's number. A round-3 approval therefore binds `nsc-010-d1b2-r03-decomposition-reviewer-e3faeb5f20eb`, covered by the golden test and F16.
- **Constants.** New local `D1B2_REVISION_REVIEW_CALL_LIMIT = 2`, `D1B2_REVISION_REVIEW_ROUND_NUMBER = 3` and `D1B2_CROSS_PROVIDER_INDEPENDENCE`. A test pins them to C0's constants.
- **No new reason codes.** The frozen names keep their signatures.
- **Nothing kept was changed.** The only replaced lines are the two length comparisons in `_call_accounting_valid`, and the `elif` that now also calls the shape check.
- **C2 `_review_run_result`.** Directly after the independence check, it refuses with the exact message when `revision_reviews_used` is present and not an exact int 0.

## 3. Failing-before and passing-after

"Before" is a detached `ade5bca`+C0 worktree with only the two new test files copied in. "After" is `4dce423`.

| Module | Before | After |
|---|---|---|
| D1C module | `Ran 59 tests FAILED (failures=41, errors=1)` (17 methods fail, 1 errors, 41 pass) | `Ran 59 tests OK` |
| C2 module | `Ran 7 tests FAILED (failures=33)`, subtests counted (3 methods fail, 4 pass) | `Ran 7 tests OK` |

**Strong failing-before.** Base behaves differently, and every name exists at base.
- `test_golden_revision_review_run_authorizes`: base returns `review_invalid (bounded_call_accounting_invalid)`. The purity test on the same run fails the same way.
- `test_a_revision_count_outside_a_two_call_circuit_is_refused`: base authorizes the (4,3) and (3,3) cases.
- `test_present_counts_must_be_exact_integers`: base authorizes all 14 cases.
- `test_pooled_runs_never_count_a_revision_review`: base `_independent_codex_roles` returns True and authorizes.
- The C2 tests `..._not_an_exact_zero_...` (24 subtests), `..._before_every_later_check` (8 subtests) and `..._non_pooled_..._by_its_count`: base does not raise, or raises a later message.

**Fail before on the reason code only.** Base also refused these runs, but without the code.
- `test_every_round_carries_a_null_correction_marker`
- `test_malformed_revision_review_rounds_fail_closed`
- `test_the_shape_is_proven_even_without_a_valid_rotation`

**Weak.** `test_binder_revision_review_constants_are_the_producers` errors at base only because the constant name is missing.

**D4 variants.** All 36 are refused after the change, each with the exact D4 status and reason code.

| Variants | Before | After |
|---|---|---|
| F1; F8d; F10 numbered-four, as-text, swapped, correction-of-round-two; F13 x2; F14 (9 tests) | FAIL: base refuses without the required code | pass |
| F2 x2, F3, F4 x2, F5, F6 x2, F7 x5, F8a-c, F9 x4, F10 history-4, F11, F12a, F12b, F15, F16, F17 (27 tests) | pass: base already refuses the whole three-round shape, so no failing-before evidence | pass |

Only the new shape check produces the F10 correction-of-round-two, F13 and F14 results. The needs_human golden runs (3) and forged variants (16) are refused with `d1b_run_status_not_review_ready` both before and after.

**Controls with identical decisions before and after**
- The two-call pass authorizes, with and without the counter keys.
- Author correction is refused with `(bounded_call_accounting_invalid,)`.
- The `max_calls` 4 three-round chain still authorizes.
- Five longer-limit refusals and the round-after-pass refusal are unchanged.
- The claude and codex pooled pairs authorize, and the shared-conversation forgery keeps its refusal.
- A pooled cross-provider pass authorizes.
- Today's NSC-1165 call-limit run gets the same exact 7-code decision.
- C2: today's pooled local shapes, with no count or an exact 0, are accepted before and after.

## 4. Suites

Suites ran sequentially. Results are identical at base+C0 and at the final commit unless shown.

| Suite | Result |
|---|---|
| New D1C / C2 modules | final `OK` / `OK` (base failures above) |
| automated_decomposition_replay_smoke_test | PASS (14 tests) |
| host_decomposition_launcher_smoke_test | PASS (20 tests) |
| decomposition_session_pool_smoke_test | PASS (10 tests) |
| ci_workflow_split_smoke_test | PASS |
| pooled_decomposition_smoke_test | PASS (17 tests) |
| revision_review_fixtures_smoke_test (imports D1C) | PASS (12 tests) |
| provider_profiles_test via `python -m unittest` | Ran 41 tests OK |
| local_decomposition_head_drift_test | Ran 4 tests OK |
| existing decomposition_authorization_smoke_test | fails at import, with the same traceback at plain ade5bca, base+C0 and final |
| existing local_decomposition_apply_test | imports, then Ran 21 tests FAILED (failures=1, errors=20), same per-test results in all three |
| local_candidate_source_integration / assigned_admission / harvest / pending / race / wake / revision_read_race / source_wait_completion | errors 2 / 2 / 5 / 4 / 4 / 2 / 1 / 2, same per-test results |
| immutable_crew_manifest_test | same AttributeError |

**Correction to the brief.** The existing local apply module does not fail at import; it fails during fixture setup.

**Pre-existing, out of scope**
- the shared fixture partition error;
- the `Snapshot.local_decomposition_stage()` TypeError;
- the `WakeScheduler._notify_local_candidate_applications` AttributeError;
- the `ExecutionCrewBridge.allow_materialization_bridge` AttributeError.

**Repaired-fixture check, as requested.** A throwaway worktree of `4dce423` with the repaired fixture copied in gives `Decomposition authorization tests: PASS (59 tests)`. That covers the accounting, revise-then-pass, both-chains, round-after-pass, rotation and no-side-effect tests. It passed twice.

**Process slip.** Stopping the old follow-up job killed only its wrapper. Its inner script kept running and started the dropped repaired-fixture `local_decomposition_apply_test`. The developer stopped both stray scripts after checking their command lines, and let that in-flight test finish. Its result (`FAILED (failures=1, errors=6)`) is void, because its worktree had already been removed while it ran.

## 5. D1C coverage not verified locally

- **Without the fixture repair**, none of these run cleanly: the 59 existing D1C tests, and all 21 tests in `local_decomposition_apply_test` (20 errors plus the fence test, which fails on the same error). Those 21 include the end-to-end `review_local_decomposition_plan` -> `_review_run_result` path and its independent-pass and revise refusals. The partition-blocked tests in the eight other local suites are also unverified.
- **With the repair**, the 59 D1C tests pass on the change. The end-to-end local apply path is still unverified with the change, and C2 is covered only by the direct `_review_run_result` tests.

## 6. Residual risks and design ambiguities

- **Intended tightenings.** These are now refused where base authorized them, and the producer emits none of them:
  - a count of 1 under `max_calls` 3 or 4;
  - a present non-int or non-zero counter on a normal pass, including null;
  - a pooled pair that counts a revision review.
- **Shape check with an invalid provider order.** The design is silent. It runs anyway (fail closed), so `provider_rotation_inconsistent` and `round_sequence_inconsistent` can both appear.
- **Round-3 invocation id.** Design step 6 was already true at base, so nothing changed. Round 3 is fixed indirectly: the shape check requires `rounds[2].round_number == 3`, and the approving round is the last one.
- **Local constants.** D1C keeps its own constants, because the round indices are hard-coded; a test catches drift.
- **Failing-before strength.** Only 9 of the 36 variants fail before, because base rejects every three-round two-call shape. The strong proof is the golden authorization test plus the counter and pooled tests.

## 7. Proposed documentation and CI (not applied; Vincent: CI out of scope for now)

Documentation text:

> D1C authorization accepts exactly one bounded extra provider call, the D1B.2 revision review. A review_ready run may count `revision_reviews_used: 1` only when `max_calls` and `calls_used` are 2, `author_corrections_used` is present and 0, and the run is `cross_provider` with no pooled sessions. It must have exactly three rounds and two history entries, with no correction marker or pooled session on any round. Round 3 must be an independent pass of round 2's exact version-2 revision, from the other provider and a different AgentRuntime identity, and the record names the round-3 approver, invocation and review evidence. Counters are exact integers, and an absent counter reads as 0. Author-correction runs stay unauthorizable, and pooled runs never count a revision review. Local decomposition application refuses any run whose `revision_reviews_used` is present and not 0.

Proposed CI step for `task-review-agent-deterministic.yml`: run `decomposition_authorization_revision_review_smoke_test.py` and `local_decomposition_apply_revision_review_test.py` under `run_full_core`. The D1C module depends on `Pipeline/TaskDecomposition/tests/revision_review_fixtures.py`.

## 8. Nothing live touched

- **C:\NSC:** nothing was written, run, cleared or relaunched. The developer only listed processes there, and stopped only its own two stray scripts.
- **External actions:** no Docker, providers, GitHub, push or merge.
- **Other worktrees:** `C:\nscrev\revision-review-fix` was only read. One file from `C:\nscrev\fixture-repair` was read and copied into throwaway worktrees only.
- **Cleanup:** all three throwaway worktrees were removed and pruned. Only `C:\nscrev\d1c-consumer-fix` remains, and it is clean. The fixture repair is not in the commit or branch.
