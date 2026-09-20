Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
```text
VERDICT: FIX FIRST
```

The artefact changed under me while I reviewed it. `propagation_check.py` went from `6a827fbe…` at my start to `20a02d5b…` and then `0fc2c121…` (mtime 18:09:56), as a `--baseline` feature was added. `test_propagation_check.py` changed too, from `65ca1fea…` to `a8778aad…`, after my last run. I wrote nothing outside `C:/nscrev/review-tmp/pc-r5` and `C:/nscrev/tmp/rev-pc5`.

Every finding below was re-run against one frozen snapshot, `pc-r5/snap/propagation_check.py` = `0fc2c121…`, with tests `65ca1fea…`. Line numbers are from `6a827fbe…`, the file I first read. The stale-id and untracked functions are identical between my mid-review copy (`20a02d5b…`) and the snapshot; only `analyse`, `build_report` and `main` differ. The new `--baseline` code runs `git worktree add` in the clone and no test among the 84 covers it. I have not reviewed it.

## Findings (most severe first)

- **[blocking] `propagation_check.py:438-454, 480-491`: the stale-id check still reports live ids and exits 1 over green CI. Reproduced.**
  - Input: `pc-r5/scen/S7`. Every class is plain `unittest.TestCase`. I ran all 12 workflow ids with `python -m unittest <id>` at head and all 12 are OK.
  - Output: "NO LONGER EXIST AT HEAD (10)", exit 1, next to "2 run, 0 failed".
  - The realistic shapes that are falsely flagged:
    - `setattr(SetattrTests, "test_case_"+n, fn)` in a loop after the class, which is the usual parametrise idiom.
    - `SetattrTests.test_x = fn` after the class.
    - A class decorator that adds methods. `decorator_list` is never checked.
    - `from pkg.tests.shared import TestCase`, a project base class that carries tests. The name `TestCase` is trusted without checking where it was imported from.
    - A class built inside a function, with its method attached before the `return`.
  - The exotic shapes that are falsely flagged:
    - `locals().update(...)` in the class body.
    - `vars()[name] = ...` in the class body.
    - An `import` statement in the class body.
    - A `for` loop target in the class body.
    - A walrus assignment in the class body.
  - Correctly silent: a metaclass (class keywords make it unverifiable), `Base = unittest.TestCase` used as a base, and `IsolatedAsyncioTestCase`.
  - Real repo today (`ff291624f`): 0 false positives.
    - Four plain-based classes there are already decorated with `@unittest.skipUnless`.
    - `WorkerViewTests` is one of them, and it sits in the same file as both real CI method ids.
    - The decorator shape is therefore one workflow line away from a false positive.
  - Suggested fix: stop proving absence at head and compare base with head instead.
    - Exit 1 only when the name was bound in the class at base and is not bound at head.
    - A method created dynamically is unbound at both revisions, so it stays silent.
    - This removes all ten shapes above, removes "already stale at base exits 1", and lets the mixin restriction relax.

- **[major] `tests/test_propagation_check.py:1251-1260`: three of the six original shapes are silent only because the fixture class has a mixin. Reproduced.**
  - `test_alias`, `test_generated` and `test_windows_only` all sit on `ViewerTests(SharedContract, unittest.TestCase)`. The bases guard silences them before the binding collection runs.
  - Nine mutations of mine survive the stale-id and untracked test classes (`StaleIdsHaveNoFalsePositives`, `StaleIdGuardsAreNotVacuous`, `StaleWorkflowTestIds`, `UntrackedPackageIsSeen`, `UntrackedFilesAreReported`):
    - `Assign` targets not collected.
    - Inner `ast.walk(node)` replaced by `node.body`.
    - `AnnAssign` targets not collected.
    - Duplicate class name trusted.
    - `node.keywords` (metaclass) ignored.
    - Any `unittest.<attr>` accepted as a base.
    - Trailing ` #` comment kept.
    - `candidate in seen` removed.
    - Quote strip removed.
  - My control mutation ("bindings always empty") is caught, so my runner works.
  - The code does handle these shapes. `pc-r5/scen/S2` has the same shapes on a plain class and gives exit 0. The suite does not pin that behaviour. This is the round-4 "vacuous guard" finding again in a new place.

- **[major] `:527-528` and harness `:275-280`: the second EXPECTED_REDUNDANT entry is not redundant. It causes a false green. Reproduced.**
  - Input: `pc-r5/scen/N`. The tests live in `pkg/tests/__init__.py`, CI runs `pkg.tests.ViewerTests.test_a`, and the method is renamed.
  - CI gives `errors=1`. The tool gives exit 0.
  - With the `__init__.py` guard removed (`pc-r5/mut/noinit.py`), N exits 1 correctly and S2's `module.Class` form stays silent.
  - The harness note "the package is never the owner of a Class.method id" is false.
  - The real repo has no TestCase in any `__init__.py`, so this is a false green in the code but not today.
  - The first entry, the trailing-dot match, is genuinely unreachable. It would need a class named after the tail of a sibling module's name.

- **[major] Three round-4 findings are neither fixed nor mentioned in the Round 4 report, and they are not on the admitted list. All three reproduce.**
  - `F`: a renamed test file that the workflow still names by path gives exit 0.
  - `C`: `module.Class` with the class renamed gives exit 0.
    - New variant `C2`: `module.Class.method` with the class renamed also gives exit 0.
    - Cause: "class absent" is treated as unverifiable.
    - CI gives `errors=1`. The removed class is printed with a `[CI WORKFLOW]` hit, but it does not fail the check.
  - `E` (`:1098-1101`): the text report to a pipe crashes with `UnicodeEncodeError` on `←`. The result is a 0-byte report, a traceback and exit 1.
  - Dropping findings without saying so is the misclassification you warned about.

- **[major] Mixin blindness is disclosed only in the fix report and one test name. The tool's output does not mention it. Reproduced (`X`).**
  - A method renamed on an `IsolatedAsyncioTestCase` class gives exit 0 while CI gives `errors=1`.
  - Nothing in the report, the JSON or `LIMITS_TEXT` says any id was skipped.
  - To the operator this is a false green. The tool should print "N workflow ids unverifiable" and carry the count in the JSON.

- **[minor] `:620-621`: a quoted untracked path is still missed (`U3`).** `?? "my lib/helper.py"` fails the `.endswith(".py")` test before the quotes are stripped.

- **[minor] `:896-899`: untracked noise can bury the forgotten file.**
  - With an un-ignored `.venv` of 80 `.py` files, the text report shows ten `.venv/...` lines plus "and 72 more".
  - The forgotten `pkg/helpers/util.py` never appears in the text. The JSON is complete.
  - The real `.gitignore` covers `.venv/` and `__pycache__/`, so this does not happen in the real repo.

- **[minor] Still open from earlier rounds.**
  - Harness `:287` runs a subprocess without `CREATE_NO_WINDOW`.
  - The README has no `--run-timeout`, no `--run-on-current-tree`, and nothing on the stale-id or untracked warnings.
  - `propcheck-nope-*` leaks on every suite run. There are two in my temp folder.

## Your priorities, answered

1. **The six false positives plus the commented line** are silent with exit 0, with and without `--run`. This holds for `S` (with the mixin) and for `S2` (plain bases, including a trailing `# was: <id>` comment). A seventh shape exists; there are ten.
2. **Did tightening blind the check on the real repo?**
   - Figures at `ff291624f`:
     - 250 test files, of which CI references 110.
     - 224 dotted strings in the workflows, exactly 2 of them `module.Class.method` ids.
     - Both ids are checkable, so tightening skipped 0 today.
   - In the test files, 117 classes are plain and 303 have other bases, so 72% of classes would be skipped if CI ever named one of their methods.
   - Tightening did not blind the check today, but the check covers 2 ids out of 110 CI test files.
   - The other 108 files are named by path or module, which is where `F` and `C` give a false green. The tool should state that coverage instead of implying more.
3. **EXPECTED_REDUNDANT:** the first entry is genuine. The second is an excuse for a hole, as `N` shows.
4. **`--untracked-files=all`:** cost is not a concern and noise is low on the real repo; I could not measure a real Unity checkout.
   - Cost: 0.06 s with 10,081 untracked files against 0.04 s with `no`. Ignored directories are not walked.
   - Both real clones are clean, so they tell me nothing about cost. I did not touch `C:\NSC`, so the real Unity tree is not measured.
   - Noise: low on the real repo because of its `.gitignore`. The minor finding above covers the un-ignored `.venv` case.
   - `seconds_analysis` excludes the `git status` call.
5. **The 31 mutations:**
   - 29 caught and 2 redundant, exit 0, in 4 min 40 s.
   - None is caught by a syntax error.
   - Each ERROR line is the real defect (the `TypeError` on a `None` exit code, the grandchild kill) and has a matching FAIL.
   - The labels match what goes red.
   - The gap is what the harness does not mutate: the nine survivors above.
6. **The admitted gaps:**
   - No baseline: a disclosed limit that can only produce a false red. It is now being replaced mid-review by unreviewed code that writes to the clone.
   - Re-parented grandchild: a disclosed leak, not a false green.
   - Round-1 minors: disclosed.
   - Mixin blindness: a false green, because the operator is never told.
   - Missing from the list entirely: `F`, `C`/`C2`, `E` and `N`.

## Tests re-run by reviewer

`TEMP` and `TMP` were `C:\nscrev\tmp\rev-pc5\t` throughout.

- **At my start:** `tests/test_propagation_check.py`, 84 tests, OK, 83.8 s. `tests/propagation_mutation_check.py` exit 0: baseline green, 29 caught, 2 redundant.
- **On the snapshot `0fc2c121…`:** 84 tests, OK, 102.5 s.
  - Scenario exit codes:

    | Exit | Scenarios |
    |---|---|
    | 0 | `S`, `S2`, `C`, `C2`, `F`, `N`, `X` |
    | 1 | `S7` (10 false stale ids), `M` (correct), `R` (correct), `E` (traceback) |

  - `U` and `U2` list the untracked files. `U3` lists none.
- **Real repo (my clone `pc-r2`), against the live tool mid-review:**
  - `6e718ece2~1..6e718ece2`: 22 tests, 12 CI, 0 stale ids, 0.78 s.
  - `HEAD~60..HEAD`: 42 tests, 19 CI, 0 stale ids, 1.41 s.
- **Base:** not re-run. The only `.bak` predates round 1. One round-4 comparison of mine pointed at a file that does not exist, so I discarded it.
- **Not done:**
  - Anything involving `--baseline`.
  - A full `--run` on the real repo.
  - Ctrl+C handling.
  - Concurrent runs.
  - Status cost on a real Unity tree.
  - The hashes moved after my first read, so parts of what I first read may have drifted.

## Scope check

- **Only intended files:** I cannot confirm this, because the tool and its test file were edited during the review and not by me.
- **New blocking gates:** exit 1 on a stale id is still advisory. With `S7` it must not be wired into rule 2.
- **Temp under `C:\NSC`:** none. Nothing was written there.
- **Identity:** the tool makes no commits.
- **Windows:**
  - All tool subprocess calls pass `CREATE_NO_WINDOW`, and none uses `DETACHED_PROCESS`.
  - The harness call at `:287` is the exception.
  - The files are LF with no BOM. Round 4 recorded CRLF throughout, and I cannot say when that flipped.
- `ci-134-fix` is still at `ca13f7511` and clean. I read it with `--no-optional-locks` only.
- I ran no Unity, Docker or providers, and I left no processes running.
