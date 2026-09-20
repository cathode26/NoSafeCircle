Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
```text
VERDICT: FIX FIRST
```

Three of my four round-3 reproductions are closed. I re-ran each one and did not rely on the report's claim. The untracked-file fix is only half closed, the new `stale_workflow_test_ids` check reports ids that exist and run green, and the one test meant to guard against that is vacuous. A false positive now exits 1, so rule 2 of the runbook should not cite the exit code in this state.

## Findings (most severe first)

- **[blocking] `propagation_check.py:438-451, 479-489`: `stale_workflow_test_ids` reports ids that exist, and the check exits 1 while CI is fully green. Reproduced.**
  - Input: `scen/S`. `ci.yml` names eight ids, and I ran each with `python -m unittest <id>` at head: all eight OK.
  - Output: "NO LONGER EXIST AT HEAD (7)", exit 1, alongside "3 run, 0 failed".
  - These six live ids are flagged falsely:
    - `ViewerTests.test_shared_contract`, because the method is inherited from a mixin and `qualified_members` reads only the class's own body.
    - `ViewerTests.test_alias`, defined as `test_alias = test_direct`, because only `FunctionDef` nodes are counted.
    - `ViewerTests.test_generated`, which is assigned from a factory call.
    - `ViewerTests.test_windows_only`, which is a `def` inside `if sys.platform == ...:` in the class body.
    - `GuardedTests.test_guarded`, because the class sits under a module-level `if` and only `tree.body` is scanned.
    - `pkg.tests.test_viewer.ViewerTests`, the `module.Class` form. `pkg/tests/__init__.py` was selected as a test, so it became module `pkg.tests`. The suffix `test_viewer.ViewerTests` has one dot and was looked up as `Class.method` in `__init__.py`. The real repo has `Pipeline/TaskDecomposition/tests/__init__.py`.
  - The seventh id sits on a commented-out workflow line (`# retired: python -m unittest …test_retired_long_ago`). It is reported stale because the regex runs over raw text. That id really is gone, but CI never runs it.
  - Handled correctly: a module whose name is a prefix of another (`test_view` against `test_viewer`), `a.b.c.d.e`, and ids for tests the range did not select. The `::` form pytest uses for parametrised ids is ignored, because the regex only reads dotted ids; unittest ids carry no subTest or parameter part.
  - Real repo today: 0 false positives on `6e718ece2~1..6e718ece2` and on `HEAD~60..HEAD`. Both real method ids are plain methods defined in the class body.
  - Suggested fix:
    - Fail only when the class is found, all its bases are plainly `unittest.TestCase`, and the name is bound nowhere in the class (use `ast.walk`).
    - Otherwise report the id as unverifiable and do not exit 1.
    - Strip `#` comments from the workflow text.
    - Never treat an `__init__.py` package as the owner of a `module.Class` id.

- **[major] `tests/test_propagation_check.py:1111-1114`: the only false-positive guard passes for the wrong reason. Reproduced.**
  - `test_an_unrenamed_method_is_not_reported` analyses `base..base`, an empty range. Nothing is selected, so `by_module` is empty and the function returns `[]` before any comparison happens.
  - My mutation "members is always empty", which makes every id stale, survives: all four `StaleWorkflowTestIds` tests stay green.
  - Three more of my mutations survived:
    - removing the `suffix.count(".") != 1` filter;
    - `startswith(module)` without the trailing dot;
    - reading `HEAD:` instead of `rev:` in the stale check. This is the round-1 blocking class, and the new code has no test for it.
  - The author's 22 mutations are sound. None is caught by a syntax error.
    - Mutation 17 is now caught by the right assertion, "the grandchild (pid N) outlived the kill"; a tearDown ERROR also appears alongside it.
    - Mutations 18-22 each go red on an assertion that matches the label.

- **[major] `:531, :549`: a new untracked package is still not seen. Reproduced.**
  - Input: `scen/U2`. Head imports `pkg.helpers.util`, and `pkg/helpers/` exists on disk but is untracked.
  - `--untracked-files=normal` collapses the directory to `?? pkg/helpers/`, which does not end in `.py`.
  - Result: `untracked_python_files: []`, no warning, `--run` passes, exit 0, `run_tree_was_head: true`. A fresh clone fails with `ModuleNotFoundError: No module named 'pkg.helpers'`.
  - A new package is the commonest shape of a forgotten `git add`. The fixture only covers a file inside a directory that is already tracked.
  - The fix is `--untracked-files=all`.
  - A quoted path is also missed (`scen/U3`). For `?? "my lib/helper.py"` the `.endswith(".py")` test runs before the quotes are stripped, so that strip can never have any effect. My mutation removing it survives.

- **[major] `:904-909`: a renamed or deleted test file that a workflow still runs gives exit 0. Reproduced; already present at base.**
  - Input: `scen/F2`. `git mv pkg/tests/test_viewer.py pkg/tests/test_viewer_panel.py`, while `ci.yml` still runs `python pkg/tests/test_viewer.py`.
  - Output: "no references outside the changed files", the new file listed as `[   ]`, "1 run, 0 failed", exit 0. CI's result is `can't open file`.
  - This is the same kind of failure as the round-3 blocker, but for a test file instead of a source module. The real workflows name tests almost entirely by path, which is the form used here.
  - Fix: if a changed path is absent at head and its path or dotted name appears in the workflow text, treat it like a stale id.

- **[major] `:484-485`: `module.Class` with a renamed class gives exit 0. Reproduced.**
  - Input: `scen/C`. The workflow runs `python -m unittest pkg.tests.test_viewer.ViewerTests`, and the class is renamed.
  - Output: step 2+3 does show the `[CI WORKFLOW]` hit, but step 6 says "1 run, 0 failed" and the exit is 0. CI reports `errors=1`.
  - This is a genuine miss. The comment at `:1032` says a known-red CI command fails the check, and this one does not.
  - Also missed, and minor because the real repo does not do it: ids written relative to a `working-directory:` (`scen/W`).

- **[major] `:1030`: the text report crashes with `UnicodeEncodeError` when stdout is a file or pipe. Reproduced; already present at base.**
  - Input: any printed hit line containing a character outside cp1252. `scen/E` has `←` in `notes.md`.
  - Result: a traceback, a 0-byte report, and exit 1. That exit code is the same one used for "tests failed" and "stale id".
  - I hit this on the first real-repo rename I tried (`GauntletView/server.py`), after 14 s of analysis.
  - `--no-renames` multiplies the hit lines printed, so this is far more likely now than it was. `--json` is not affected.
  - Fix: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

- **[minor] `:180, :762-782`: a pure rename is noisy. Reproduced.**
  - `--no-renames` is correct and should stay.
  - A real pure rename (R100) of `GauntletView/server.py` produces a 928-line report with 127 "removed" symbols. 65 of them say "no references outside the changed files". It takes 12.8 s, against 0.7 s for a normal range.
  - `scen/P`, 40 functions with every importer updated: 159 lines, all noise, exit 0.
  - Test selection is not inflated. The old and new module names only select genuine importers.
  - Suggestion: when the file is absent at head, print one line, "module deleted or renamed, N names", and then list only the names that have external hits.

- **[minor] Exit code and `--json`.**
  - Exit 1 now means a stale id, a failed run, or (from the crash above) a traceback.
  - JSON consumers can tell the first two apart from `stale_workflow_test_ids` and `run_results`. There is no single `exit_reason` field.
  - The false positives above are the only legitimate case I found that exits 1.
  - A stale id that was already stale at base also exits 1. It is not attributed to the range, which is the no-baseline gap again.

- **[minor] Still open from earlier rounds.**
  - Harness `:201` runs a subprocess without `CREATE_NO_WINDOW`.
  - `README-propagation-check.md` has no `--run-timeout`, no `--run-on-current-tree`, and nothing on the stale-id or untracked warnings.
  - `propcheck-nope-*` leaks on every suite run.
  - The harness leaves its `propcheck-mutation-*` directory behind, because mutation 17's orphan sleeper holds it for 45 s.
  - A relative clone path still breaks every `--run` test. I hit it again: `U` "failed" until I passed absolute paths.

**The three admitted gaps.**
- **No baseline:** this can only produce a false red, so it is classified honestly.
- **Re-parented grandchild:** the run is still reported as TIMEOUT with exit 1. That is a leak, not a false green.
- **Round-1 minors:**
  - `A...B` read as `A..B` selects too much, which can only give a false red.
  - Test files with no `__main__` guard could read as "pass" with 0 tests run. In the real repo at `ff291624f` the only such file is `test_support.py`, which has 0 tests and is not in CI, so this is a theoretical limit and not a false green today.
- The genuine false greens this round are F2, C and U2 above. None of them is on the admitted list.

## Tests re-run by reviewer

`TEMP` and `TMP` were under `C:\nscrev\tmp\rev-pc4` throughout.

- **Head:**
  - `tests/test_propagation_check.py`: 73 tests, OK, 68.5 s.
  - `tests/propagation_mutation_check.py`: baseline green, 22 of 22 caught, exit 0.
- **Base:** I ran the `.bak` only for the encoding crash, and the result is identical.
- **Round-3 reproductions:**
  - Renamed module (R090): 5 symbols reported, the test selected as `[CI]`, "1 run, 1 failed", exit 1. Closed.
  - Renamed test method: reported as stale, exit 1 both with and without `--run`. Closed.
  - Untracked helper file: listed and warned about. Closed for a single file; open for a new directory (U2).
  - `.git/index`: byte-identical after an analysis run and after a `--run`, with a stale stat cache. A plain `git status` control did rewrite it. Closed. My real clone's index was also unchanged.
- **Real repository** (my clone `pc-r2`, at `ff291624f`):
  - `6e718ece2~1..6e718ece2`: 22 tests selected, 12 marked `[CI]`, 0 stale ids, 0.66 s. This matches rounds 2 and 3.
  - `HEAD~60..HEAD`: 42 tests, 19 `[CI]`, 0 stale ids, 1.2 s.
- **Not done:**
  - A full `--run` on the real repository.
  - Ctrl+C handling.
  - Concurrent runs.
  - Submodules.
  - The cost of `git status --untracked-files=all` on a Unity tree with many untracked files.

## Scope check

- The SHA-256 of all three reviewed files is identical before and after my review (`3fef0f2d…`, `402e62e6…`, `99f86168…`).
- `ci-134-fix` is still at `ca13f7511` and clean. I read it with `--no-optional-locks` only.
- All three files use CRLF throughout with no BOM, so there is no line-ending churn.
- All four subprocess calls in the tool pass `CREATE_NO_WINDOW`, and none uses `DETACHED_PROCESS`. The harness call at `:201` is the exception noted above.
- The tool makes no commits, so commit identity does not apply.
- New gate: exit 1 on a stale id with no `--run`. It is advisory, not a pipeline gate, and the report does not say Vincent was asked. With the false positives above it must not be wired into rule 2 yet.
- Nothing was written under `C:\NSC`. I ran no Unity, Docker or provider.
- My scratch files are in `C:/nscrev/review-tmp/pc-r4` and `C:/nscrev/tmp/rev-pc4`. No background processes remain.
