# fix/retired-auditor-test-debt, commit 3

Head: `207f607ac` "ExecutionCrew tests: finish the retired-auditor expectations" (on top of `8f10e36a5`, which is on top of `a71849dc5`). Not pushed. Working tree is clean.

Files: `Pipeline/ExecutionCrew/tests/execution_crew_smoke_test.py`, `Pipeline/ExecutionCrew/README.md`, `Pipeline/TaskReviewAgent/execution_session_pool.py`. All three stay LF. `git diff --check a71849dc5` is clean. `git diff --stat a71849dc5` shows 8 files, +112 / -416, with no whole-file churn.

## Scenarios changed or deleted (line numbers at a71849dc5)

| a71849dc5 line | Scenario | Asserted | Asserts now |
|---|---|---|---|
| 503 | pass (run 1) | `contract_locality_status=="pass"`, audit path not None | `"not_required_by_profile"`, audit path `is None` |
| 504-507 | pass (run 1) | audit path `samefile` the audit file; `audit_artifact` schema_version, task_id, status, source_head, contract identity | deleted; now asserts `contract_locality_audit.json` does not exist in the run directory |
| 527 | pass (run 1) | 4 distinct role run_ids | 3 (predecessor already changed this in commit 1) |
| 535 | pass (run 1) | 4 `task_request.json`, 4 `agent_runtime/*/result.json` | 3 and 3 |
| 538 | pass (run 1) | token_usage 4/8/44, reported 4/8/44, invocation_count 4, usage_available 4 | 3/6/33, reported 3/6/33, invocation_count 3, usage_available 3 |
| 547 | repair (run 2) | invocation_count 7, tokens 10/17/80 | 6, tokens 9/15/69 |
| 551 | provider_failure_usage (run 153) | total_tokens 22 | 11 |
| 556 | missing_usage (run 154) | reported_total_tokens 33 | 22 |
| 1241-1245 | locality pass (run 102) | review_ready, role calls, `contract_locality_status=="pass"` | **deleted**: it only tested the auditor passing |
| 1335 | validator fallback (runs 112, 113) | `contract_locality_status=="pass"` | `"not_required_by_profile"` |
| 1329, 1342 | validator fallback, comments | "mandatory pre-Implementer audit already passed" / "not the (already-passed) audit" | comments only: "even though the writers already ran" / "no audit artifact exists". Stale comments inside the scenario from decision 4 |
| 1398-1403 | pre-feature retry, comment | "always runs the mandatory current auditor" | no crew role audits locality; the retry writes no audit and reports not_required_by_profile |
| 1407-1417 | pre-feature retry (run 130) fixture | `auditor_request_dirs` search, `len==1`, agent_runtime search/rmtree, `contract_locality_auditor_1.json` unlink | deleted (fresh runs create none of these) |
| 1422 | pre-feature retry fixture | `role_results` filter that removed the auditor entry | deleted |
| 1420-1421, 1424-1425 | pre-feature retry fixture | pop of the 3 locality fields; audit-file unlink(missing_ok)+absence | kept unchanged |
| 1446-1447 | pre-feature retry (run 131) | status `"pass"`, audit path not None, `samefile` audit file | `"not_required_by_profile"`, path `is None`, audit file does not exist |

Decision 6: after these edits the whole file passed on the first run. No other assertion failed, so no other scenario was changed.

## Decision 2: derived vs actual numbers

Each derived number is the a71849dc5 value minus one first-attempt invocation (the "pass" implementer record: input 1, output 2, total 11). Every derived number matched the run. The test passed on the first execution, and no number was taken from the run output.

| Assertion | a71849dc5 | Derived | Actual |
|---|---|---|---|
| pass input/output/total (and reported) | 4/8/44 | 3/6/33 | 3/6/33 ✓ |
| pass invocation_count / usage_available | 4/4 | 3/3 | 3/3 ✓ |
| pass distinct run_ids, task_request, result.json | 4/4/4 | 3/3/3 | 3/3/3 ✓ |
| repair invocation_count | 7 | 6 | 6 ✓ |
| repair input/output/total | 10/17/80 | 9/15/69 | 9/15/69 ✓ |
| provider_failure_usage total_tokens | 22 | 11 | 11 ✓ |
| missing_usage reported_total_tokens | 33 | 22 | 22 ✓ |
| call counts (needs_twice 7→6, design 4→3, blocker 2→1, criteria_* 4→3, missing_usage 4→3) | already applied in commit 1 | −1 each | ✓ |

## Decision 7

- `README.md:8`: `full:` now reads `Implementer -> Unity Test Author -> Validator`, which matches `CREW_PROFILE_ROLES["full"]` in `run_crew.py`.
- `execution_session_pool.py:626`: a grep of the whole repo found the text only at its definition, so no test asserts it. The message is now "profile must carry exactly the profile crew roles". No test changed. No suite that runs in this container reaches this line (see below), so the new wording has not been run here.

## Tests (details in /out/after-commit3.txt)

| Suite | after commit 2 | after commit 3 |
|---|---|---|
| ExecutionCrew/tests/execution_crew_smoke_test.py | FAIL | **PASS** |
| ExecutionCrew/tests/pooled_run_crew_smoke_test.py | FAIL* | FAIL* (unchanged) |
| the other 8 ExecutionCrew/tests/*_test.py | PASS | PASS |
| AgentRuntime/tests/provider_session_smoke_test.py | PASS | PASS |
| GauntletView/tests/local_crew_view_test.py | PASS | PASS |
| TaskReviewAgent/tests/execution_session_pool_smoke_test.py | not run before; FAIL* at a71849dc5 and 8f10e36a5 | FAIL* (unchanged) |
| TaskReviewAgent/tests/provider_profiles_test.py | not run before; FAIL** at a71849dc5 and 8f10e36a5 | FAIL** (unchanged; 37/41 pass) |

\* `CrewBlocked: checkout identity manifest lacks an absolute Windows host path`. Linux-container limitation.
\** 4 `LauncherProfileTests.*_two_launcher_handoff` errors: `FileNotFoundError: 'powershell.exe'`. Linux-container limitation.

To get the baselines for the two TaskReviewAgent suites, I extracted each commit with `git archive` into `/tmp` and ran them there. The repository was not touched.

Totals: 10/12 → 11/12 on the predecessor's set; 11/14 → 12/14 counting the two TaskReviewAgent suites, which fail the same way at both base commits.

## Stopped on

Nothing.
