# propagation_check.py adversarial review — Release Agent's independent pass, 2026-09-18

Reviewer: `pipeline-reviewer` subagent, commissioned by the Release Agent session before
discovering `propagation-check-review-20260918.md` (Fable review) had already landed the same
verdict on board row H-20260917-32. Kept as a second, independently-arrived-at data point —
different investigation, same root defect, worth having both when fixing.

## VERDICT: FIX FIRST (independently converges with the Fable review)

## Blocking finding (matches the Fable review's #1)

`propagation_check.py:274-303, 427-462, 478-507` — steps 3, 4 and `--run` read the clone's
checked-out **working tree**, not `<head>`. Only the AST symbol diff (steps 1-2) reads the named
revisions via `git cat-file`. Nothing checks or warns that `HEAD == head`.

Reproduced on the real repo (`6e718ece2`, the PR #134 root cause commit) two ways:

- Clone on `main`, `propagation_check.py <clone> 6e718ece2~1..6e718ece2 --run` → 24 selected,
  **zero of the real regressions reproduced** (wrong tests entirely, since `main` has files that
  exist at neither endpoint).
- Clone checked out at `6e718ece2` (head) → 22 selected, `--run`: 22 run, 10 failed.
- Clone checked out at `6e718ece2~1` (base) → 22 run, only 2 failures, both pre-existing
  (identical at head) — proving the other 8 are real regressions, but only knowable by manually
  diffing two separate invocations since the tool has no built-in base comparison.

## Additional findings this pass surfaced (beyond the Fable review)

- **No baseline in `--run`.** It reports one revision's pass/fail with nothing to compare against
  `<base>`; 2 of the 10 head failures (`test_fresh_revision_feedback.py`,
  `test_revision_completion.py`) are pre-existing and unrelated to the commit under test, but the
  tool's single-revision report can't say so.
- **No subprocess timeout anywhere** (`grep -n timeout propagation_check.py` → nothing). Measured
  wall time: 366s (head) / 598s (base) for `--run` on a single-commit range — the board row's
  "0.7s" is the AST-only steps, not `--run`, and nothing warns a reader off that reading.
- **`last_meaningful_line` can make a failing test read as passing** — `production_end_to_end_smoke_test.py`
  printed a per-case `PASS ...` line as its last line at `exit 1`, identical text to its `exit 0`
  run at base.
- Minor: asymmetric comment-stripping in the import-line regex (`import X  # noqa` missed, `from X import Y  # noqa` caught); `module_level_names` misses re-exports and names bound inside
  `try:`/`TYPE_CHECKING`; `A...B` ranges silently downgrade to `A..B`; leaked `mkdtemp` scratch
  dirs (never cleaned up); substring-based reference counting inflates hit counts; 3 of 243
  test-shaped files have no `__main__` guard and would falsely report `exit 0`.

## Verified clean

Process hygiene: all subprocess calls use `CREATE_NO_WINDOW`, no `DETACHED_PROCESS`; UTF-8/LF-only
files; no writes to the clone; temp dirs correctly kept out of `C:\NSC`; `[CI]` marking (both
path-form and dotted-form workflow references) verified correct against the real repo. The core
"step 4 catches value changes, not just renames" design claim holds against the real repo — the
false-green in the blocking finding is what undercuts trusting an ad hoc invocation without HEAD
verification.

## Relationship to the Fable review

Both reviews independently identified the same root cause (working-tree read instead of `<head>`)
as the single blocking issue via different reproduction paths. The Fable review additionally found
two more blocking cases from the same root family (a changed test file never selecting itself —
PR #134 round 4; method-level renames invisible to the module-level-only symbol diff — PR #134
round 1) that this pass didn't isolate as separately blocking. This pass adds the no-baseline,
no-timeout, and misleading-last-line findings in more depth. Recommend the fixer read both.
