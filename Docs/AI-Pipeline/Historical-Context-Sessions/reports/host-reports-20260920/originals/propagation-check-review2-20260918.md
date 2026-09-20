Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
```text
VERDICT: FIX FIRST
```

The round-1 blocking defect is fixed. I confirmed it on the real repository from a clone that was not at the head. The analysis half (steps 1–5, no `--run`) is now trustworthy from any checkout. The new `--run` work is not ready. It crashes on its own timeout path, accepts a dirty tree as "head", and leaves the text report silent about the tree mismatch and the missing baseline, although the fix report says the baseline caveat is in the report text. None of this needs a redesign; each fix is small.

## Findings (most severe first)

- **[blocking] `propagation_check.py:659`: any timed-out test crashes the default text report. Reproduced.**
  - The line formats `"exit %-3d" % result["exit_code"]`, and `exit_code` is `None` on a timeout.
  - Input: a range whose selected test sleeps past the timeout, plain `--run` without `--json`.
  - Result: `TypeError: %d format: a real number is required, not NoneType`. The whole report is lost after the run has already cost up to 900 s per test.
  - `--json` works and exits 1.
  - No test sends a timeout through `build_report` or `main`. `test_a_hung_test_times_out…` calls `run_tests` directly.
  - My mutation "main exits 0 on timeout" (`:820`) also survived the suite.

- **[major] `:429-440`: `head_matches_worktree` compares commits only, so a dirty tree counts as the head. Reproduced.**
  - Input: clone detached at `feature`, `pkg/mod.py` edited and staged but not committed, `main..feature --run`.
  - Result: both tests pass, exit 0, `run_tree_was_head: true`. At the real head, `test_old.py` fails. This is a false green, recorded as the range's result.
  - A `git status --porcelain` check on tracked files is needed. The refusal should cover a dirty tree, or the data should at least carry `worktree_dirty`.
  - Every ref form resolves correctly: branch, lightweight tag, annotated tag, 7-character sha, `HEAD`, `HEAD@{0}`, `x^{commit}` and a detached head.
  - An empty repository exits 2 cleanly, but with an empty message (`git rev-parse --verify --quiet failed … :`).
  - Submodules were not tested; the real repo has none that I saw. A submodule pointer that does not match its checkout would go undetected. Theoretical.

- **[major] `:593-677`: the text report never says the tree is not the head, and never prints the no-baseline caveat. Reproduced.**
  - `build_report` reads none of `worktree_at_head`, `run_tree_was_head` or `run_caveat`.
  - With `--run --run-on-current-tree` on `main`, the output is headed `propagation check main..feature` and lists `exit 0 tests/test_old.py ok`. That is a pass measured on `main`, shown under the feature range. A grep for tree, baseline or caveat wording in the text returned nothing.
  - So a reader of the text report can mistake the escape hatch's output for the range's. In JSON only a single boolean separates them.
  - The fix report's line "stated in the report *and* in the JSON" is false for the report.
  - `test_the_report_says_the_tree_is_not_the_head` (test file line 598) asserts a data key, not the report. Its name claims more than it checks.
  - Without `--run` from `main`, step 5 still prints "RUN THESE (from <clone>)" and `python -B tests/test_new.py`, a file that is not on disk there, with no warning.
  - The refusal message says "Analysis above is correct", but nothing is printed above it (stdout was 0 bytes). The refusal discards the analysis.

- **[major] `:547-564`: the timeout does not bound a test that started a child process. Reproduced.**
  - Input: a test that starts `python -c "time.sleep(25)"` and then hangs, with a 3.0 s timeout.
  - Result: it is reported as `timeout` after 25.1 s. On Windows, `subprocess.run` kills only the direct child and then waits on the pipe the grandchild still holds.
  - A grandchild that never exits (a viewer or server started by a test) still blocks forever, which is the original finding.
  - The orphan grandchild is left running.
  - It needs a kill of the whole process tree (job object or `taskkill /T`) and output that does not go through an inherited pipe.
  - There is no CLI flag for the timeout.

- **[major] `:169`: a renamed module selects nothing and reports nothing. Reproduced; this existed before the fix, was not found in round 1, and is a new finding.**
  - `git diff --name-only` detects renames and lists only the new path.
  - Input: `git mv pkg/old_name.py pkg/new_name.py`, with `tests/test_uses_old.py` (named in CI) still importing `pkg.old_name`.
  - Result: `removed []`, `selected []`, exit 0. CI would fail with `ImportError`.
  - The fix is `--no-renames`, or `--name-status` with the old path treated as changed.
  - This is the tool's headline case. It is a false green of the same kind as the round-1 blocker.

- **[major] The fix report's "Not done" list leaves out round-1 majors that are still open.**
  - Re-confirmed: a stale reference inside a workflow that the range also changed. In the synthetic repo, `ci.yml:6 from pkg.mod import gone` is tagged "same changed file - likely the rename itself", and the symbol reads "no references outside the changed files" (`:338, :620-625`).
  - Not re-tested, and the code is unchanged: the import-parser holes (64 of 248 test files), selection of direct importers only, the missing `NSC_*_TEMP` variables, and the guide §2.4 skip list for tests that hard-code `C:\NSC`.
  - Those last two are the way `--run` could write under `C:\NSC`.
  - A reader of the fix report would believe only minor items remain.

- **[major, judgement] The two classes the report admits are only partly answered.**
  - Shipping without them is defensible only if rule 2 cites the analysis, not `--run`'s exit code.
  - **No baseline.** At `6e718ece2`, 2 of 10 failures already fail at base, and `test_viewer` is 37/57 red before this range. Exit 1 would therefore fire on most real ranges, and people would learn to ignore it. It does not block the selection half. It does block naming `--run` as a pass/fail step.
  - **Method-level renames.** Re-reproduced on `330cd3777~1..330cd3777`:
    - `assistant-candidate-ci.yml:59-60` names two `ViewerTests.test_review_alarm_*` methods that no longer exist at that revision.
    - The tool reports only `HUMAN_REVIEW_ALARM_SECONDS` with 0 references, and marks `test_viewer.py` `[CI]`, which reads as reassurance.
    - This is one of PR #134's four rounds, and the LIMITS text covers it in a single line.
    - It does not block the tool as an advisory aid. It does block any wording in rule 2 that implies PR #134 is covered.
  - Round 4 (`1d0f84d14`) is now covered: `gauntlet_view_smoke_test.py` is selected and marked `[CI]`.

- **[minor] Harness audit.**
  - All 10 listed mutations disable what their labels say. The timeout mutation goes red because the 120 s sleep finishes and the test reads as a pass; the harness takes 3 minutes for that reason.
  - Three of my own mutations survived:
    - `tracked_paths` → `ls-files`. Every `ChangedTestFileSelectsItself` test sets the tree to the head, which is the same "fixture revisions agree" mistake the report says it fixed.
    - Removing `or entry.path in selected_paths`. `test_it_is_not_selected_twice` cannot fail, because the fixture's test imports no changed module.
    - `changed_files` diffing against the working tree survives the whole suite.
  - The harness counts any non-zero exit as "caught", so a mutation that produces a syntax error would be counted as pinned.
  - `propagation_mutation_check.py:106` runs a subprocess without `CREATE_NO_WINDOW`.

- **[minor] `README-propagation-check.md` was not touched (dated 17 Sep).**
  - It still says "29 tests", and `[--run] [--json] [--limit N]`.
  - It has nothing on `--run-on-current-tree`, the refusal, the timeout, `status`, or changed-test selection.
  - Its example is still `origin/main..HEAD`.

- **[minor] `--json` contract.**
  - `exit_code` can now be `null`, and `modules` can hold the non-module string `"(changed test file)"`.
  - There is still no version key.
  - I found no consumer of the JSON anywhere in `job-tools`, `reports` or `C:\NSC\*.md`, so nothing breaks today.
  - `status` and `exit_code` agree in all three branches.
  - `failed` at `:656` and the exit at `:820` both count `None` as failed, which is right.

- **[minor] `test_propagation_check.py:491`** leaks one `propcheck-nope-*` directory per run; I found three in my TEMP. The scratch-directory test globs `propcheck-*` in a shared TEMP, so it will flake under concurrent runs.

## Tests re-run by reviewer

`TEMP`/`TMP` were set to `C:/nscrev/tmp/rev-pc` throughout.

- **Head:**
  - `tests/test_propagation_check.py`: 44 tests, OK, 27.0 s.
  - `tests/propagation_mutation_check.py`: baseline green, 10 of 10 mutations caught, 3 min 3 s.
- **Base (the `.bak` tool) on the real range from my clone parked on `origin/main` at `ff291624f`:** 24 tests selected, the wrong set.
- **Head on the same clone:**
  - 22 selected, 12 marked `[CI]`.
  - All four PR #134 tests are selected and marked `[CI]`.
  - The JSON is identical, key for key, to a run from the clone detached at `6e718ece2`.
- **`--run` from the parked clone:** refuses with exit 2, and the message is correct. Read-only analysis against `ci-134-fix` (at `ca13f7511`) gives the same result: 22 tests, `worktree_at_head: false`.
- **Round-1 synthetic repo (`main..feature` run from `main`):** `test_new.py` is now selected and marked `[CI]`, and the stale symbol is found.
- **Working-tree reads:** no `ls-files` or `HEAD:` remains in the analysis path. `changed_files`, `removed_symbols`, `cat_file_batch`, both greps, `tracked_paths` and `workflow_references` all take the revision.
- **Not done:** a full `--run` on the real repo (6 min; round 1 already did it, and no `--run` code path for a passing run changed), submodules, and concurrent runs.

## Scope check

- Only `propagation_check.py`, its tests and the harness changed.
- The SHA-256 of all three files is identical before and after my review.
- `ci-134-fix` is still at `ca13f7511` with a clean status.
- All three subprocess calls in the tool pass `CREATE_NO_WINDOW`. None uses `DETACHED_PROCESS`. The harness call is the one exception, listed above.
- All three files use CRLF line endings. The `.bak` does too, so there is no line-ending churn. None has a BOM.
- The tool makes no commits, so commit identity does not apply.
- There is one new refusal. It sits inside an opt-in flag and has an escape hatch, so it is not a pipeline gate. The report does not say Vincent was asked.
- Nothing was written under `C:\NSC`. I ran no Unity, Docker or provider.
- My clones remain in `C:/nscrev/review-tmp/pc-r2` and `pc-r2-scen`. No background processes remain.
