# fix/retired-auditor-test-debt

Branch head: `8f10e36a5` (based on `a71849dc5`)

- `27a9508dc` ExecutionCrew tests: stop expecting the retired contract locality auditor
- `8f10e36a5` ExecutionCrew: drop the unreachable contract locality auditor branch

`git diff --check a71849dc5`: clean. `git diff --stat a71849dc5`: 7 files, +94 / -376, with no whole-file churn (all files stay LF).

## Results

The files are `/out/before.txt`, `/out/after-commit1.txt` and `/out/after-commit2.txt`. Each run covers 12 suites: the five named suites plus every `*_test.py` in `Pipeline/ExecutionCrew/tests`.

| Suite | before | after commit 1 | after commit 2 |
|---|---|---|---|
| AgentRuntime/tests/provider_session_smoke_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/crew_provider_session_smoke_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/execution_crew_smoke_test.py | FAIL (line 335) | FAIL (line 465) | FAIL (line 465) |
| ExecutionCrew/tests/pooled_run_crew_smoke_test.py | FAIL* | FAIL* | FAIL* |
| ExecutionCrew/tests/prompt_blocker_policy_smoke_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/prompt_context_reduction_smoke_test.py | FAIL (7) | PASS (11/11) | PASS (11/11) |
| ExecutionCrew/tests/quota_failover_smoke_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/retry_sidecar_refresh_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/role_budgets_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/session_pool_smoke_test.py | PASS | PASS | PASS |
| ExecutionCrew/tests/unity_meta_bytes_test.py | PASS | PASS | PASS |
| TaskReviewAgent/GauntletView/tests/local_crew_view_test.py | PASS | PASS | PASS |
| **Total** | **9 pass / 3 fail** | **10 pass / 2 fail** | **10 pass / 2 fail** |

\* `pooled_run_crew_smoke_test.py` already failed before any edit, and it fails the same way on every run: `CrewBlocked: checkout identity manifest lacks an absolute Windows host path` (`run_crew.py` uses `PureWindowsPath`). CI runs this suite on `windows-latest`, so this is a Linux-container limitation, not something these commits caused. I did not touch that file.

## execution_crew_smoke_test.py (line numbers at a71849dc5)

| a71849dc5 line | Scenario | Rule | What changed / property involved |
|---|---|---|---|
| 2 | module docstring | — | "four-role" → "three-role" |
| 24 | imports | R2 | dropped `audit_commands` (only the deleted `locality_review_required` scenario used it) |
| 69 | fake provider feedback check | R2 | `and self.role!="contract_locality_auditor"` dropped: the auditor is never invoked now |
| 83-120 | fake provider auditor branch | R2 | deleted; it only fed the deleted scenarios, and no kept run invokes the auditor. `elif validator` became `if` |
| 27, 35-37, 53 | `RELATED_TASK` / `related_task()` in the fixture graph | kept on purpose | it is written into the graph every scenario uses; removing it would change the fixture's task-graph inputs for all scenarios (R5) |
| 314 | profile comment | — | "default remains the full four roles" corrected |
| 335-337 | default_full (272) | R1 | role-call list |
| 394 | all_new (46) | R1 | role-call list |
| 435, 448 | comments | — | stale "locality auditor" wording removed |
| 445 | cache preflight (148) | R1 | role-call list |
| 502 | pass (1) | R1 | role-call list |
| 503-507 | pass (1) | **STOP** | `contract_locality_status=="pass"`, audit path, `contract_locality_audit.json` contents. Now `not_required_by_profile` / `None` / no file |
| 527 | pass (1) | R1 | `len({run_id for calls})` 4→3 (count of distinct role-call invocations) |
| 535 | pass (1) | **STOP** | 4 `task_request.json` / 4 `result.json` artifacts. Now 3 |
| 538 | pass (1) | **STOP** | `token_usage`: invocation_count 4, tokens 4/8/44. Now 3, 3/6/33 |
| 530 | existing_test_adequate (155) | R1 | role-call list |
| 546 | repair (2) | R1 | role-call list |
| 547 | repair (2) | **STOP** | token_usage 7 / 10 / 17 / 80. Now 6 / 9 / 15 / 69 |
| 549 | provider_failure_usage (153) | R1 | role-call list |
| 551 | provider_failure_usage (153) | **STOP** | `total_tokens==22`. Now 11 |
| 553 | missing_usage (154) | R1 | `len(calls)` 4→3 |
| 556 | missing_usage (154) | **STOP** | `reported_total_tokens==33`. Now 22 |
| 558 | no_op_repair (6) | R1 | role-call list |
| 560, 561, 562, 568 | needs_twice / design / blocker / criteria_* | R1 | `len(state.calls)` 7→6, 4→3, 2→1, 4→3 |
| 644 | retry_noop (164) | R1 | role-call list |
| 726, 739, 749 | human-review retries (71, 75, 76) | R1 | role-call lists |
| 836, 846 | blocker_leak / test_blocker_leak (77, 78) | R1 | role-call lists |
| 995 | stale diverged retry (72) | R3 | calls → `[]`. The "neither applies cleanly" CrewBlocked message check still passes |
| 1023 | legacy retry (74) | R1 | `calls[1]` → `calls[0]` (index into the role-call list; the Implementer is now first) |
| 1169-1206 | locality_review_required (100) | R2 deleted | auditor output `contract_review_required`; calls == [auditor] |
| 1208-1228 | locality_add_dependency_empty_related (104), _mismatch (105) | R2 deleted | `related_task_ids` validation; calls == [auditor] |
| 1230-1239 | locality_invalid (101) | R2 deleted | reasons start "contract locality auditor: "; calls == [auditor] |
| 1242-1244 | locality pass (102) | R1 | role-call list |
| 1245 | locality pass (102) | **STOP** | `contract_locality_status=="pass"`. This whole scenario exists to test the auditor passing, but it does not meet R2's literal test (no custom auditor output, calls != [auditor]), so I kept it. Recommend deleting it |
| 1247-1306 | nsc012_like (103) | R2 deleted | NSC-012-like auditor classification; calls == [auditor]; includes its clone/task fixtures |
| 1313 | reason_code_pass_invalid (110) | R1 | role-call list |
| 1333 | validator fallback (112, 113) | R1 | role-call list |
| 1335 | validator fallback (112, 113) | **STOP** | `contract_locality_status=="pass"`. Now `not_required_by_profile`. Its comments (1329, 1342) were left alone |
| 1358, 1373 | persistent-graph loader (120) | R1 | first role call is now `implementer`; the comment now says the loader runs "before any provider role" (the recording loader still asserts that no role ran first) |
| 1375-1396 | broken graph (121) | kept unchanged | `contract_locality_audit.json` absence still holds |
| 1406, 1444 | pre-feature retry (130, 131) | R4 + R1 | role-call lists |
| 1409 | pre-feature retry (130) | **STOP** | `len(auditor_request_dirs)==1`. Now 0. The next lines (`rmtree(...[0])`, `unlink()` of `contract_locality_auditor_1.json`) would also raise, because a fresh run no longer produces those artifacts |
| 1446-1447 | pre-feature retry (131) | **STOP** | `contract_locality_status=="pass"` and audit path. Now `not_required_by_profile` / `None` |
| 1476, 1480 | cross_new / retry_noop new-path retries (138, 137) | R1 | role-call lists |
| 1491 | partial new retry (136) | R3 | calls → `[]`; CrewBlocked message check kept |
| 1501 | tampered sidecar retry (135) | R3 | calls → `[]`; CrewBlocked message check kept |
| 1510 | committed new retry (141) | R1 | `calls[1]` → `calls[0]` |

How I found the stop list: I ran a throwaway copy in `/tmp` (never committed) where every `assert` in `main()` only logs a failure, and the three auditor-artifact reads were guarded. That copy ran to the end, and only the lines marked **STOP** above failed. The real file stops at the first one, line 465 in the new numbering (503 at a71849dc5).

## prompt_context_reduction_smoke_test.py (line numbers at a71849dc5)

| a71849dc5 line | Test | Action | Property |
|---|---|---|---|
| 11-14, 27-28 | module docstring | updated | no crew role inlines the GDD; the auditor prompt builder still carries the reduced locality evidence |
| 78-83 | imports | added `CREW_SESSION_ROLES` | the invoked roles now come from production |
| 92-100 | `ROLES`, `INLINE_GDD_ROLE`, `NO_INLINE_GDD_ROLES`, `ROLE_CLASSES` | `ROLES` / `INLINE_GDD_ROLE` kept (the unchanged measured-bytes tests use them through `_fixed_prompts`); dropped the auditor's `ROLE_CLASSES` entry (nothing uses it now) | |
| 303-348, 373-374 | `State.audit`, `_audit_output`, fake auditor branch | deleted | only the deleted fail-closed tests used them |
| 429 | `test_exactly_one_role_prompt_carries_the_inline_committed_gdd` | renamed `test_no_crew_role_prompt_carries_the_inline_committed_gdd` | asserts the invoked roles are exactly `CREW_SESSION_ROLES` and that no request prompt contains the GDD body or sentinel |
| 509 | `test_a_reused_pooled_session_receives_no_stale_or_inline_canon` | switched to validator | leases `CREW_SESSION_ROLES`. The first-run "auditor saw the stale GDD" check became "the committed GDD at `head_one` is the stale one". The final auditor checks became: the Validator's `context_paths` binds the committed GDD and its prompt has no stale text. The per-role stale / inline / read-instruction / capsule / commit checks are unchanged |
| 594, 607 | `test_the_auditor_still_fails_closed_on_missing_design`, `..._on_a_missing_declared_dependency` | **deleted** | blocking audits removed on purpose in 6e718ece2 |
| 618 | `test_deterministic_locality_validation_is_unchanged` | kept unchanged | |
| 695 | `test_the_auditor_prompt_still_carries_the_locality_evidence` | converted | now calls `contract_locality_auditor_prompt` directly via `_fixed_prompts(gdd_text())`; every sentinel / path / instruction assertion kept |
| 730 | `test_each_role_still_receives_its_required_context` | auditor block (744-748) and auditor feedback-leak check (800-801) dropped | Implementer / Test Author / Validator checks unchanged |
| 807 | `test_prompt_construction_is_byte_identical_across_repeated_runs` | iterates `CREW_SESSION_ROLES` | |
| 864, 899 | measured-bytes tests | kept unchanged | |

## Other files

- `crew_provider_session_smoke_test.py:34`: the `CREW_ROLES` tuple is replaced by `from Pipeline.ExecutionCrew.session_pool import CREW_SESSION_ROLES as CREW_ROLES`. The suite passes.
- Docs (commit 1). Each edit is limited to the sentence it corrects:
  - `Pipeline/ExecutionCrew/README.md` lines 48, 139 and 456;
  - the `session_pool.py` docstring, line 11;
  - `Docs/AI-Pipeline/PROVIDER_PROFILES_AND_BUDGET_ROUTING.md` lines 138 and 150. The capacity sentence next to 138 also said "five roles for ten workers"; it now reads "fifty leases, above the forty that four roles for ten workers need" (`execution_session_pool.py:414` still uses 50).
- `run_crew.py` (commit 2): removed the `if "contract_locality_auditor" in required_roles:` branch and kept the former `else` body un-indented. Removed the imports only that branch used: `CONTRACT_LOCALITY_AUDIT_SCHEMA_VERSION`, `validate_locality_audit_output` and `CONTRACT_LOCALITY_AUDITOR_OUTPUT_SCHEMA`. I checked with grep that nothing re-imports them from `run_crew`. `read_only_role_counts` and `ROLE_EVIDENCE_OBLIGATIONS` are untouched.
- Left unchanged as instructed: `AgentRuntime/tests/provider_session_smoke_test.py`, `local_crew_view_test.py`, `GauntletView/server.py`, `AssistantControl/viewer.py`, `contract_locality.py`, `prompts.py`, and the three CI tests. None of them needed a change.

## Stopped on / follow-ups

1. **`execution_crew_smoke_test.py` still fails.** Seven kept scenarios assert non-role-call output that no longer holds. R1/R3/R5 say not to change them, so each needs a decision:
   - pass (1): lines 503-507, 535 and 538 (a71849dc5 numbering);
   - repair (2): line 547;
   - provider_failure_usage (153): line 551;
   - missing_usage (154): line 556;
   - locality pass (102): line 1245. I recommend deleting this scenario; its only purpose is the auditor;
   - validator fallback (112, 113): line 1335;
   - pre-feature retry (130, 131): lines 1409 and 1446-1447. This scenario builds its "old run" by stripping auditor artifacts from a fresh run, and fresh runs no longer produce them.
2. `pooled_run_crew_smoke_test.py` fails in this Linux container, the same way before and after my changes (Windows host path check). CI runs it on Windows.
3. Stale auditor wording I left alone because it is outside the named lines:
   - `README.md` line 8 (`full: Contract Locality Auditor -> ...`), plus lines 22-42, 56-92, 436, 453, 480, 526-542 and 558;
   - `execution_session_pool.py:626`, whose error message says "exactly five distinct crew roles" although profiles now have four.
4. `run_crew.py:2150-2155` builds `task_catalog`, `dependency_contracts`, `dependent_contracts` and `valid_task_ids`, and nothing reads them now. I kept them because `build_task_catalog` and `auditor_dependent_contract_payload` still fail closed on a malformed graph.
