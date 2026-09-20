# `propagation_check.py` — fixes for the two reviews of 2026-09-18

**Board:** H-20260917-32. **Tool:** `C:\nscrev\job-tools\propagation_check.py`.
**Pre-fix backup:** `propagation_check.before-review-fixes-20260918T154614.bak.py`.

Two reviews, arrived at independently:

- `C:\nscrev\reports\propagation-check-review-20260918.md` — Fable, FIX FIRST.
- `C:\nscrev\reports\propagation-check-review-release-agent-20260918.md` — a pipeline-reviewer the
  Release Agent commissioned before seeing the first, FIX FIRST.

They found the **same blocking root cause by different reproductions**, which is the strongest
signal this tool has had. Both are answered here.

## The blocking defect: it read the working tree, not `<head>`

Only the AST symbol diff read the named revisions. The repo-wide grep, the test selection, the
`[CI]` marking and `--run` all read whatever the clone happened to have checked out. So the
posture the runbook would put it in — *a clone sitting on `main`, about to merge a branch* —
returned "0 symbols, nothing selected, exit 0". A confident false green.

**Fixed by reading the revision, not the disk.** `git grep` and `git ls-tree` both take a
revision; `git grep <rev>` prefixes each hit with `<rev>:`, which `_strip_rev_prefix` removes.
`workflow_references` now lists workflows with `ls-tree <rev>` and reads them at `<rev>:path`
instead of `HEAD:path`. No temp checkout is needed and the tool got no slower.

`--run` is different: it executes tests from disk, so it cannot be fixed by reading git. It now
**refuses** when the clone is not checked out at `<head>`, naming the commit it found, the one it
wanted, and the `git checkout --detach` to fix it. `--run-on-current-tree` is the explicit escape
hatch, and the data records `run_tree_was_head` either way.

### Verified against the real repository

From `C:/nscrev/ci-134-fix`, checked out at `ca13f7511` — *not* the commit under test:

| | old tool | new tool |
|---|---|---|
| tests selected | 24 (wrong ones: files existing at neither endpoint) | **22**, matching what the reviewer got only by checking the clone out at head |
| the 4 tests that failed in PR #134 | not the ones selected | **all 4 selected** |
| `--run` | would have run the wrong tests | **refuses**, and says how to fix it |

## The other findings

| finding | fix |
|---|---|
| a changed test file was never selected for itself — PR #134 round 4, where a test changed alongside `index.html` and nothing was selected | changed test files are added to the selection, unless the range deletes them |
| `--run` had no timeout anywhere; a real run took 366s and one hung test would block forever | per-test timeout, default 900s, reported as `status: timeout` |
| `last_meaningful_line` could make a failing test read as passing — `production_end_to_end_smoke_test.py` printed a per-case `PASS ...` as its last line while exiting 1 | the verdict is the exit code alone; `last_line` is context only. New explicit `status` field |
| `--run` printed nothing until every test finished | one line per test to stderr as it completes |
| the `mkdtemp` scratch directory was never removed | removed in a `finally` |
| no baseline comparison: a failure may be pre-existing | not fixed — stated in the report *and* in the JSON, as `run_baseline: null` plus a `run_caveat` naming the base to re-run at |

## Evidence

**29 → 44 tests**, all green. `tests/propagation_mutation_check.py` reverts each of the 10 fixes
one at a time, against a **copy** of `job-tools` so the live tool is never modified, and proves
the unmutated copy green before breaking anything:

    all 10 review fixes are pinned by a test

**The harness earned itself twice.** On its first run three mutations survived: my
working-tree-versus-head tests were passing for the wrong reason, because the fixture's parked
commit happened to contain the same `Docs/stale.md` and the same `ci.yml` as the head. The fixture
now makes the two revisions genuinely differ — the doc is deleted and the workflow is **renamed** —
and only then did reverting the grep, the workflow read and the workflow listing each go red.
Without the harness all three would have shipped as green tests over a defect.

## Not done, and why

- **No baseline comparison in `--run`.** Doing it properly means running the selected tests at
  `<base>` too, which needs a second checkout — a `git worktree`, with the cleanup and
  kill-safety that implies. It is the right next change and it is bigger than the rest combined.
  Until then the tool says plainly, in both the report and the JSON, that a failure is not proof
  of a regression.
- **Method-level renames are still invisible** (the Fable review's third blocking case, PR #134
  round 1). The symbol diff is module-level; catching `ViewerTests.test_review_alarm_*` means
  diffing class members and matching them against the dotted method IDs workflows name. Real, and
  a separate change from the one the two reviews agreed on.
- Minor items from the Release Agent's pass, not yet addressed: asymmetric comment-stripping in
  the import regex, re-exports and `TYPE_CHECKING` names missed by `module_level_names`, `A...B`
  ranges silently downgrading to `A..B`, substring-based reference counting inflating hit counts,
  and three test-shaped files with no `__main__` guard that would report exit 0.

**Still not fit for runbook rule 2 or the merge steps** until a re-review passes. The false green
is closed, but two of the three blocking classes the Fable review named are only partly answered.

---

# Round 2 — answering the re-review (2026-09-18)

Review: `C:\nscrev\reports\propagation-check-review2-20260918.md`, VERDICT FIX FIRST.
The round-1 blocking defect was confirmed fixed on the real repository from a clone not at the
head. Everything below is what the round-1 fixes introduced or left.

## First, a correction to what I wrote above

Round 1's report said the no-baseline caveat was "stated in the report **and** in the JSON".
**That was false for the text report** — `build_report` read none of `worktree_at_head`,
`run_tree_was_head` or `run_caveat`. The reviewer checked and I had not. It is true now, and the
tests below pin it, but the claim was wrong when I made it.

## [blocking] A timed-out test crashed the report

`"exit %-3d" % result["exit_code"]`, with `exit_code` None on a timeout — `TypeError`, and the
whole report lost *after* `--run` had already spent up to the timeout on every test. Mine, from
round 1, and no test covered it because `test_a_hung_test_times_out…` called `run_tests` directly
and never went through `build_report` or `main`.

Fixed; a timeout now prints as `TIMEOUT` and counts as a failure, so `main` exits 1.

## [major] A dirty tree counted as the head

`head_matches_worktree` compared commits only. A clone detached at the head with an edited tracked
file passed, ran something that was not the head, and recorded `run_tree_was_head: true` — a false
green wearing the range's name. `worktree_is_dirty` now runs `git status --porcelain
--untracked-files=no`, `--run` refuses, and the data carries `worktree_dirty`.

## [major] The text report never carried the warnings

They existed only in the JSON, so a reader of the default output could not tell
`--run-on-current-tree` results from the range's. The report now prints, in the run section, that
the results are **not this range's**, that the tree was dirty, and the no-baseline caveat — and,
in step 5, that the commands it is offering name files that may not exist in this checkout.

## [major] The timeout did not stop a test that spawned a child

Two causes, both fixed. Output went to a **pipe**, so after killing the direct child
`subprocess.run` blocked reading a pipe the surviving grandchild still held — the exact hang the
timeout exists to prevent, reported only when the grandchild happened to exit. And only the direct
child was killed, leaving an orphan. Output now goes to a file, and `kill_process_tree` uses
`taskkill /T /F` on Windows with `proc.kill()` as the fallback.

The reviewer also noted there was no CLI flag for the timeout. There is now: `--run-timeout`.
Adding it exposed a further defect of mine — `timeout: float = RUN_TIMEOUT_SECONDS` in the
signature binds at import, so the constant only *looked* configurable and neither a caller nor a
test could change it. Read at call time now.

## Evidence

**44 → 57 tests**, green, and the suite went from 404 s to **51 s** because the new hang fixtures
sleep just past a 2–3 s timeout instead of the default.

`tests/propagation_mutation_check.py` now reverts **17** fixes one at a time, proves the
unmutated copy green first, and catches every one. Two of the additions were themselves wrong at
first and the harness said so: one mutation "caught" with zero red lines, because it broke syntax
rather than behaviour — a mutation that cannot even import proves nothing — and another anchored
on a string that no longer existed. Both are now anchored on the guard they claim to remove.

## Still not done

- **No baseline comparison.** Unchanged from round 1: doing it properly needs a second checkout.
  The report and the JSON both say plainly that a failure is not proof of a regression.
- **Method-level renames still invisible** (Fable round 1, PR #134 round 1).
- **A renamed module selects nothing** — new in round 2, and pre-existing rather than introduced:
  `git diff --name-only` reports only the new path, so importers of the old module name are
  neither selected nor warned about.
- Submodules untested; the repo has none visible.

Three of the review's named gaps therefore remain, all of them in the "what this tool does not
catch" family rather than the "it says green when it is red" family that round 1 was. It should
still not go into runbook rule 2 until a reviewer agrees that boundary is drawn honestly.

---

# Round 3 — answering the review (2026-09-18)

Review: `C:\nscrev\reports\propagation-check-review3-20260918.md`, VERDICT FIX FIRST.
All four round-2 reproductions confirmed closed, including that the grandchild is dead rather
than merely unwaited-for.

## I classified the blocking finding wrongly, and the reviewer proved it

Round 2's report filed "a renamed module selects nothing" under *what the tool does not catch*,
and argued that family does not block. The reviewer tested the claim instead of accepting it:

> step 2, headed "REMOVED OR RENAMED", prints "none — no module-level name present at base is
> absent at head". That statement is false. Step 4 selects 0 tests, step 6 says "0 run, 0 failed",
> exit 0. Truth at head: `ModuleNotFoundError`.

That is **green while red** — the exact category the tool exists to prevent — not a disclosed
limit. My classification was the error, and asking the reviewer to test the distinction rather
than accept it is what surfaced it.

**Fixed with the one flag the reviewer identified**: `git diff --no-renames`. Git scores a
rename-plus-edit as R090 and reports only the new path, so every name in the old module looked
untouched. A plain `git rm` always worked; only the rename path was wrong.

## [major] Untracked files still counted as the head

`--untracked-files=no` was blind to a forgotten `git add`: head commits a module importing a
helper, the helper exists only on disk, `--run` passes, and a fresh clone of the same head dies.
Not a refusal — an untracked file is usually noise — but `untracked_python_files` now lists them
in the data and the report warns.

## [major] A renamed test method still read as reassurance

CI runs named `module.Class.method` ids, and the symbol diff is module-level, so renaming a
method left `--run` reporting "1 run, 0 failed" over a CI command that dies with errors=1.
`stale_workflow_test_ids` now parses each `[CI]` test's AST at head and reports every dotted id a
workflow names that no longer exists. **It fails the check on its own**, without `--run`, because
reporting a known-red CI command while exiting 0 is the same confident green.

## [major] The tool wrote to the clone it calls read-only

The always-on `git status` refreshes `.git/index` — a write under `C:\NSC` if pointed at a live
checkout, and an `index.lock` window for anything else using it. Now
`git --no-optional-locks status`.

## [minor] Two honest corrections

- Mutation 17 was **caught for the wrong reason**. Once output went to a file the timeout was
  prompt either way, so the only red was a tearDown `PermissionError` from the surviving
  grandchild — no test asserted it was dead. `TheGrandchildIsActuallyDead` now reads the
  grandchild's pid from the fixture and polls `tasklist` for its death.
- The `CREATE_NEW_PROCESS_GROUP` comment claimed it was part of the timeout kill. It is not;
  `taskkill /T` is. Corrected.

## The index test needed measuring, not reasoning

It passed with the guard removed. Straight after a checkout git has nothing to refresh, so no
write happens either way. I assumed a 0.02 s mtime bump would make the entry stale; a probe
showed git's stat cache has **one-second** granularity, so the sleep has to cross a whole second.
With 1.1 s, plain `git status` rewrites the index and `--no-optional-locks` does not — measured,
and now the test fails when the guard is removed.

## Evidence

**57 → 73 tests**, green. The mutation harness now reverts **22** fixes and catches every one,
proving the unmutated copy green first.

## Still not done

- **No baseline comparison in `--run`.** Unchanged, and still the largest remaining gap.
- **A re-parented grandchild survives `taskkill /T`** (launcher starts sleeper, launcher exits).
  The run still times out promptly; the orphan and its log leak. A Windows job object closes it
  properly and is a bigger change than anything here.
- Round 1's minor list from the Release Agent's pass: import-regex comment asymmetry, re-exports
  and `TYPE_CHECKING` names, `A...B` downgrading to `A..B`, substring reference counting, and
  three test-shaped files with no `__main__` guard.

---

# Round 4 — answering the review (2026-09-18)

Review: `C:\nscrev\reports\propagation-check-review4-20260918.md`, VERDICT FIX FIRST.
Three of four round-3 reproductions closed. The blocking finding was in the code I added in
round 3, which is where I asked the reviewer to look hardest.

## [blocking] My new check reported ids that exist, and exited 1 over green CI

`stale_workflow_test_ids` flagged **six live ids**, each a method that exists but is not a plain
`FunctionDef` in its class's own body: inherited from a mixin, `test_alias = test_direct`,
assigned from a factory, defined inside an `if` in the class body, a class nested under a
module-level `if`, and the `module.Class` form claimed by a `pkg/tests/__init__.py`. A seventh
came from a commented-out workflow line, because the regex ran over raw text.

**A false stale id exits 1, so it is exactly as harmful as a miss** — worse, in a way, because it
teaches people to ignore the tool.

Rewritten to report only what it can prove: the class is found by `ast.walk` (so a guarded class
counts), its bases are literally `TestCase`/`unittest.TestCase`, and the name is bound nowhere in
the class by any construct. Anything else — class absent, a mixin, a computed base, a duplicate
class name — is **unverifiable and never fails the check**. Comments are stripped; an
`__init__.py` is never the owner of a `Class.method` id.

**The cost is stated, not hidden.** `test_a_class_with_a_mixin_is_deliberately_unverifiable` pins
that renaming a method on a mixin-based class is *not* reported. That is a real miss, accepted on
purpose.

## [major] The guard that should have caught this was vacuous

`test_an_unrenamed_method_is_not_reported` analysed `base..base`. Nothing was selected, so the
comparison never ran — four of the reviewer's mutations survived behind it, including reading
`HEAD:` instead of the revision, which is round 1's blocking class in code written after round 1.
Replaced by `StaleIdGuardsAreNotVacuous`, which first asserts the range really selects the tests.

## [major] A new untracked package was still invisible

`--untracked-files=normal` collapses a new directory to `?? pkg/helpers/`, which does not end in
`.py` — and a new package is the commonest shape of a forgotten `git add`. Now `=all`.

## Evidence

**73 → 84 tests**, green. **0 false positives on the real repository** for
`6e718ece2~1..6e718ece2`.

The harness reverts **31** fixes. 29 are caught; **2 are declared redundant with a written
reason** — the trailing-dot module match and the `__init__.py` exclusion are both already covered
by the "class not found" guard, and no honest input reaches them. They are listed rather than
quietly dropped, the harness fails if a *new* unexplained survivor appears, and it also fails if
one of the two ever stops surviving, since the note would then be a lie.

Two of my own new mutations were wrong at first and the harness said so: the `module.Class` and
commented-line probes used a mixin-based class, where the lookup is unverifiable anyway, so they
proved nothing until they were pointed at a plainly-based class.
