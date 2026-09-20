Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
```text
VERDICT: FIX FIRST
```

All four round-2 reproductions are closed. I re-ran each one, and the grandchild is dead after the timeout, not just unwaited-for. The blocker is the renamed module. The report files it under "what the tool does not catch", but it produces a false green: "0 run, 0 failed", exit 0, while the test CI runs fails with `ImportError`. A one-flag change closes it. The dirty-tree fix also still lets untracked files through, so a forgotten `git add` gives the same false green.

## Findings (most severe first)

- **[blocking] `propagation_check.py:172`: a renamed module gives a confident green over a red CI. Reproduced.**
  - Input: `git mv pkg/old_name.py pkg/new_name.py` plus a one-line edit, which git scores as R090. `tests/test_uses_old.py` is named in `ci.yml` and still imports `pkg.old_name`. Run `main~1..main --run`.
  - Output: step 2+3, headed "REMOVED OR RENAMED", prints "none - no module-level name present at base is absent at head". That statement is false, because every name in `pkg.old_name` is gone.
  - Step 4 selects 0 tests, step 6 says "0 run, 0 failed", and the exit code is 0.
  - Truth at head: `ModuleNotFoundError: No module named 'pkg.old_name'`.
  - `LIMITS_TEXT` never mentions renames, and it tells the reader to trust step 4, which is empty here.
  - The fix is one flag. In a scratch copy with `--no-renames` on that diff, the same input gives 4 removed symbols with the stale hits, the test selected as `[CI]`, "1 run, 1 failed", exit 1.
  - A plain `git rm` of a module already works. Only the rename path is wrong.

- **[major] `:454`: untracked files still count as the head. Reproduced.**
  - This is the forgotten-`git add` case, and it leaves the round-2 dirty-tree finding half closed.
  - Input: head commits `pkg/api.py` importing `pkg.helper`, and `pkg/helper.py` exists on disk but is untracked.
  - Result: `--run` passes with exit 0, `run_tree_was_head: true`, `worktree_dirty: false`.
  - A fresh clone of the same head fails with `No module named 'pkg.helper'`.
  - `--untracked-files=no` makes this blind by design. At minimum the tool should warn, in the data and the text report, when untracked non-ignored `.py` files exist. A refusal is not required.

- **[major] `:689-705, :53-63`: a method-level rename still reads as reassurance under `--run`. Reproduced.**
  - Input: `ci.yml` runs `python -m unittest pkg.tests.test_viewer.ViewerTests.test_review_alarm_fires`, and the range renames that method.
  - Output: `[CI] pkg/tests/test_viewer.py`, "1 run, 0 failed", exit 0. The CI command fails with errors=1.
  - By the report's own test this is "green when it is red". It is disclosed only by the last `LIMITS_TEXT` line.
  - I am not blocking the tool on it as an advisory aid. It does block citing `--run`'s exit code in runbook rule 2 until it is fixed.
  - A cheap partial fix is to look for `dotted.Class.method` IDs in the workflow text for each `[CI]` test and check them against the head's AST.

- **[major] `:836, :454`: the new always-on `git status` writes to the clone the CLI calls "read-only". Reproduced.**
  - An analysis-only run, without `--run`, changed the SHA-256 of `.git/index` in my scratch repo, because `git status` refreshes the index.
  - Pointed at a live checkout, that is a write under `C:\NSC` and an `index.lock` window for concurrent git commands.
  - `git --no-optional-locks status …` left the index byte-identical in the same setup.

- **[minor] `propagation_mutation_check.py:147-152`: mutation 17 is caught for the wrong reason. Reproduced.**
  - With `kill_process_tree` replaced by `proc.kill()`, both assertions in `test_a_test_that_spawns_a_child_still_times_out_promptly` pass, because the file sink alone makes the timeout prompt.
  - The only red is a tearDown `PermissionError [WinError 32]`: the surviving grandchild's working directory is the fixture repo. No test asserts that the grandchild is dead.
  - The mutation's stated reason, "the timeout waited for it", no longer describes what it reverts.
  - The harness run left a live `python -c "time.sleep(45)"` (PID 38800) and an undeleted `propcheck-mutation-*` directory behind.
  - The other 16 mutations are sound. Each anchor is present, each is a behaviour change and not a syntax break, and each goes red on an assertion that matches its label.
  - The three ERROR lines under "formats a None exit code" are the intended `TypeError`.

- **[minor] `:537-563`: a re-parented grandchild survives `taskkill /T`. Reproduced.**
  - Input: the test starts a launcher, the launcher starts a sleeper and exits, and the test then hangs.
  - Result: the run is reported as a timeout at 4.3 s, which is good. The sleeper stays alive and `propcheck-*/out-0.log` leaks, because it holds the log handle.
  - A job object would close this.
  - `CREATE_NEW_PROCESS_GROUP` plays no part in the kill; the comment at `:41-43` overstates what it does.

- **[minor] `:706-714, :730-733`: the wording is wrong when the clone is at the head but dirty. Reproduced.**
  - The report prints "this clone is checked out at 90c57f95c6f4, not at the head (main)", and 90c57f9 is main.
  - It offers `git checkout --detach main`, which does nothing in that state.
  - The run section repeats the same false sentence before the correct dirty-tree line.

- **[minor] `:585`: a relative clone path breaks every `--run` test. Reproduced; already present at base.**
  - `PYTHONPATH=T` combined with `cwd=T` gives `No module named 'pkg'`. This is a false red.
  - `data["clone"]` is made absolute, but the value passed to `run_tests` is not.

- **[minor] Mutation survivors; the first three are unchanged from round 2 and the report does not mention them.**
  - `tracked_paths` reading `ls-files`.
  - Dropping `or entry.path in selected_paths`.
  - `changed_files` diffing against the working tree.
  - `if data.get("run_dirty_worktree")` forced to `False`: no test reads the dirty line in the text report.
  - The call-time read of `RUN_TIMEOUT_SECONDS`: change 5 in the report is not pinned by any test.

- **[minor] Still open from round 2.**
  - `README-propagation-check.md` is untouched and has no `--run-timeout` or `--run-on-current-tree`.
  - Harness line 159 runs a subprocess without `CREATE_NO_WINDOW`.
  - The refusal message says "Analysis above is correct" with nothing printed above it.
  - `test_missing_clone…` leaks a `propcheck-nope-*` directory on every run.
  - A negative `--run-timeout` marks every test as TIMEOUT.

The no-baseline gap is classified honestly. It can only produce a false red, never a green. The exit-1 noise from it remains a reason not to cite `--run`'s exit code in rule 2.

## Tests re-run by reviewer

`TEMP` and `TMP` were under `C:\nscrev\tmp\rev-pc3` throughout.

- **Head:**
  - `tests/test_propagation_check.py`: 57 tests, OK, 53.8 s.
  - `tests/propagation_mutation_check.py`: baseline green, 17 of 17 caught, exit 0. See the mutation-17 finding above.
- **Base:** not re-run this round. The `.bak` is unchanged since round 2.
- **Round-2 reproductions:**
  - Timeout with a grandchild: `TIMEOUT 3.30s`, "1 run, 1 failed", exit 1. The grandchild PID was confirmed dead and the scratch directory was removed.
  - Staged edit at head: refused with exit 2, naming `M  pkg/mod.py`.
  - Escape hatch: the text report carries NOT THIS RANGE'S, the dirty line and NO BASELINE.
  - Step-5 warning: present for both the synthetic repo and the real one.
- **Real repository:** `6e718ece2~1..6e718ece2` from my clone `pc-r2`, parked at `ff291624f`.
  - 22 tests selected, 12 marked `[CI]`, in 0.8 s. This matches round 2.
  - `--run` refuses with exit 2.
- **`status` and `exit_code`:** they agree in all three branches, and `main` exits 1 on `None`.
- **File sink:** the handle closes on every path, and the log is removed unless an orphan holds it.
- **Refusal on a legitimate run:** I found no way to trigger it. A clean real-repo clone reports clean, in 0.08 s.
- **Not done:**
  - A full `--run` on the real repository.
  - Submodules.
  - Ctrl+C during `proc.wait`; in theory this leaves the child running.
  - Concurrent runs.

## Scope check

- The SHA-256 of all three reviewed files is identical before and after my review (`c3d68e9c…`, `8443214f…`, `c21be0a2…`).
- `ci-134-fix` is still at `ca13f7511` and clean. I read it with `--no-optional-locks` only.
- All four subprocess calls in the tool pass `CREATE_NO_WINDOW`, and none uses `DETACHED_PROCESS`. The harness call is the exception noted above.
- All three files use CRLF with no BOM, so there is no line-ending churn.
- The tool makes no commits, so commit identity does not apply.
- The dirty-tree refusal is a second new refusal. It sits inside the opt-in `--run` flag and has an escape hatch, so it is not a pipeline gate. The report does not say Vincent was asked.
- Nothing was written under `C:\NSC`. I ran no Unity, Docker or provider.
- My scratch files are in `C:/nscrev/review-tmp/pc-r3` and `C:/nscrev/tmp/rev-pc3`. I killed my one orphan process, and no background processes remain.
