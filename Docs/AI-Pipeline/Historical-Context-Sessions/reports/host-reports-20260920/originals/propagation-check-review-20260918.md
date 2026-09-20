VERDICT: FIX FIRST

The PR #134 claim holds: all four failed tests are selected and marked `[CI]`, and `--run` makes all four fail at `6e718ece2`. It should not go into runbook rule 2 or the merge steps yet, because I reproduced five cases where it reports a clean result and is wrong. Two of those five are PR #134's other two rounds.

**Findings (most severe first)**

- **[blocking] `propagation_check.py:289, 410, 435-437, 490-492` — the repo-wide grep, test selection, `[CI]` marking and `--run` all read the checked-out tree, never `<head>`.** Only the symbol diff reads the range.
  - Input: a synthetic repo with `main` checked out and range `main..feature`. The feature branch shrinks a tuple, adds `tests/test_new.py` and a workflow line.
  - Result: "0 tests … nothing selected … 0 run, 0 failed", exit 0.
  - With `feature` checked out, the same range selects `test_new.py` as `[CI]` and it fails with exit 1.
  - "On main, about to merge a branch" is the posture the steward and orchestrator guides would run it in.
  - The tool neither checks nor warns that HEAD differs from `<head>`, and the README example is `origin/main..HEAD`.
  - Reproduced.

- **[blocking] `:621-622` — a changed test file is never selected for itself, and a non-Python change selects nothing. This is PR #134's round 4.**
  - Input: `1d0f84d14~1..1d0f84d14`, which changes `index.html` and `gauntlet_view_smoke_test.py`.
  - Result: `selected []`, although `task-review-agent-deterministic.yml:372` runs that test.
  - The README (lines 57-59) and report §1 imply step 4 covers this round. It does not.
  - Reproduced.

- **[blocking] `:187-204` — only module-level names are compared, so the one real rename failure in PR #134 is missed.**
  - Input: `330cd3777~1..330cd3777` with the tree at `330cd3777`. Two `ViewerTests.test_review_alarm_*` methods are renamed.
  - The stale method IDs are still at `assistant-candidate-ci.yml:59-60` in that tree.
  - The tool reports only `HUMAN_REVIEW_ALARM_SECONDS` with "no references outside the changed files".
  - `--run` cannot catch it either: it runs the whole file, while CI calls the named method IDs.
  - The limit is documented, but this was the one case the grep half was kept for.
  - Reproduced.

- **[major] `:338-341, 351-375` — the import parser misses common forms, so test selection has holes.** A whole-repo comparison against `ast` found 64 of 248 test files with at least one import the tool cannot see; 25 of those are CI-referenced.
  - **Trailing comment on a plain import.** `import X.Y as z  # noqa: E402` returns `set()`. `importing_tests('.', ['Pipeline.TaskReviewAgent.run_autonomous_graph'])` omits `autonomous_graph_cli_smoke_test.py`, that module's own CI test. There are 60 such import lines in tests.
  - **Bare-name imports after a `sys.path` insert.** `Pipeline.TaskGraph.graph_delta` does not select `graph_delta_smoke_test.py` or `graph_apply_materialize_smoke_test.py`. 48 test files use this form; 10 are CI-referenced.
  - **Multi-line `from pkg import (` with submodules on the following lines.** `Pipeline.TaskReviewAgent.durable_selection` selects `[]`. The documented limit undersells this.
  - A semicolon after an import also defeats the regex; that is from code inspection only.
  - Reproduced.

- **[major] `:427-462` — selection covers direct importers only.**
  - `execution_session_pool.py` iterates `CREW_SESSION_ROLES` (`:622, :1233` at `6e718ece2`) and was itself edited in fix `ca13f7511`.
  - `test_post_crew_workflow.py` (`[CI]`) and `test_background_jobs.py` import only that wrapper and are not selected.
  - The full transitive closure is 152 of 248 test files, so that is not the fix. One hop through non-test modules, or at least a printed warning, would be.
  - LIMITS does not mention transitivity.
  - Theoretical on this range: all six files that really broke were direct importers.

- **[major] `:616, 313, 546-547` — a stale reference inside a workflow that the range also touched is mislabelled.**
  - `changed_paths` includes non-Python files.
  - In the synthetic repo, the stale `from pkg.mod import gone` in `ci.yml` is tagged "same changed file - likely the rename itself", and the symbol reads "no references outside the changed files".
  - Reproduced.

- **[major] `:478-507` — `--run` has no safety rails.**
  - There is no `timeout=`, so one hung test blocks forever. From code inspection.
  - Nothing is printed until every test finishes; the real run gave six minutes of silence.
  - The three `NSC_*_TEMP` variables from guide §2.4 are not set.
  - The guide's skip list (`local_candidate_source_integration_test`, `local_source_wait_completion_test`, `immutable_crew_manifest_test`, which hard-code `C:\NSC`) is not honoured. If selected, those tests would run.
  - Only a 200-character last line is kept. `production_end_to_end_smoke_test.py` reported exit 1 with last line `PASS test_pre_handoff_…`, which is misleading.
  - The `mkdtemp` scratch folder is never removed.
  - A failing test does not stop the rest, which is good. An import error is reported as exit 1.

- **[major] `--run` makes no base comparison and the run is too noisy to act on.** The real run at `6e718ece2` had 10 failures out of 22.
  - Genuine: the four named tests, plus `execution_crew_smoke_test`, `prompt_context_reduction_smoke_test` (7 failures) and `quota_failover_smoke_test` (`[CI]`; passes at `~1`, fails at the commit).
  - Pre-existing: `test_fresh_revision_feedback` and `test_revision_completion` fail identically at `6e718ece2~1` with a `ScopePlanningError`.
  - Unclassified: `production_end_to_end_smoke_test` (188 s, exit 1). I did not re-run it at base.
  - `test_viewer.py` is marked `[CI]` as a whole file, but CI runs only named methods of it. The guide records 37/57 as pre-existing, so `--run` will be red on it regardless.

- **[minor] `:627-629` — CI marking is accurate today but fragile.** I audited 110 marked files and found none named only in a trigger block and no prefix collisions. The check is still a substring match on the dotted name, and any mention counts as "runs".

- **[minor] `--json` is not a stable contract.**
  - There is no schema or version key.
  - `run_results` and `seconds_run` exist only with `--run`.
  - Errors produce exit 2 and stderr with no JSON.
  - `hits` is truncated by `--limit` with no flag saying so.
  - Nothing states whether a result is for the tree or for the head.

- **[minor] Test theatre.** The 29 tests cover the happy paths well: `ValueRemovedFromTuple`, `RemovedFunctionWithWorkflowReference`, `RunReportsFailingTest` and `ImportFormsAndMapping`. No test covers:
  - tree ≠ head;
  - a changed test file being selected;
  - a trailing-comment import;
  - a bare-name import;
  - a multi-line submodule import;
  - a workflow changed in the same range;
  - a hung or non-importable test under `--run`;
  - dotted-form `[CI]` marking, which the report calls a fixed bug but leaves untested;
  - the `--json` key set.
  
  Every finding above would pass the current suite.

**Tests re-run by reviewer**

- `tests/test_propagation_check.py`, with `TEMP`/`TMP` set to `C:/nscrev/tmp/pc`: 29 tests, OK, 12.7 s on Windows against the 0.86 s claimed.
- Real range in `C:/nscrev/ci-134-fix`, read-only: 6 changed files, 0 symbols, 24 selected with 12 `[CI]`, in 0.45 s. The four PR #134 tests:

  | Test | Selected | `[CI]` |
  |---|---|---|
  | `execution_session_pool_smoke_test.py` | yes | yes |
  | `session_pool_smoke_test.py` | yes | yes |
  | `provider_profiles_test.py` | yes | yes |
  | `pooled_run_crew_smoke_test.py` | yes | yes |

  The tool's direct-import selection matches an `ast` ground truth exactly on this range (24 of 24).
- `--run`, in my own clone `C:/nscrev/review-tmp/propagation-check-run` detached at `6e718ece2`:
  - 6 min 5 s, exit 1, 22 run (two of the 24 files do not exist at that commit), 10 failed.
  - All four named tests fail for the right reasons: "four roles not idle", `('implementer','test_author','validator')`, `unsupported ExecutionCrew pool role: contract_locality_auditor`, and `failures=1, errors=1`.
  - The tree was clean afterwards.
  - No Docker or provider started. The "docker" strings in those tests are fakes.
- `--run` now counts as proven against the real repo for executing the tests and catching PR #134. It is not proven for hangs, and its output needs a base comparison before it is usable as a gate.

**Scope check**

- The tool is stdlib only and sits in `job-tools`; it adds no blocking gates.
- Both subprocess calls pass `CREATE_NO_WINDOW`, and there is no `DETACHED_PROCESS`.
- It makes no commits, so commit identity does not apply.
- I edited nothing and did not touch `ci-134-fix`.
- `C:\NSC\astra-should-not-happen\tmp` appeared at 06:25:56, during my run. The string is in neither the repo at `6e718ece2` nor `job-tools`, and other agents' sessions were running at the same time. I did not create or touch it and could not identify its origin. Someone should check it.
- Reviewer clones are left in `C:/nscrev/review-tmp/propagation-check-{run,rename}`. No background processes remain.
