# G15: GER commit tools fit the 2026-09-17 contract check

Problem: `nsc-pipeline-problems.md` G15. Scope: `apply_followup_revision.py` reviewer label, folding
`runbook_contract_commit.py` into a supported `ger-tools` script, optional post-commit-check provenance.
No provider calls, Docker or Unity used. Nothing merged, pushed or installed by me.

## Round 2 (2026-09-17): review findings fixed

A fresh review of round 1 found 2 major and 4 minor defects. All six are fixed in
`C:\nscrev\ger-tools-dev\g15\new\`. Work done only in that folder plus the disposable test clone
`C:\nscrev\g15-ger-tools-test`; nothing in `C:\NSC`, `C:\nscrev\ger-tools\` or
`C:\nscrev\ger-contract-revisions-20260916\` was touched.

| # | Finding | Fix |
|---|---|---|
| 1 (major) | `--post-commit-check-verdict` accepted APPROVE/FIX_FIRST/REJECT, disconnected from the real Codex contract-check report vocabulary (`commit_contract \| commit_contract_then_decompose \| revise`); `ac.final_recommendation` can't even parse "revise". | Removed the flag from both tools. Added `apply_contract.parse_post_commit_verdict()` (parses the report's own last `Final recommendation:` line, case-insensitive, markdown-tolerant) and `apply_contract.resolve_post_commit_check()` (ties report + verdict + commit together). `verdict` is now always parsed from `--post-commit-check-report` itself, never asserted by the caller. |
| 2 (major) | Every git call in `contract_commit.py`/`apply_followup_revision.py` goes through `apply_contract.git()`, which lacked `CREATE_NO_WINDOW`; running from a shell popped console windows. | Added `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` to `apply_contract.py`'s `git()` helper (line 93-98) and its own `taskcontrol validate` `subprocess.run` call in `main()` (line ~417-420) — the only two `subprocess.run` call sites in that file. No other direct `subprocess`/`Popen` calls found in the new tools (grepped). |
| 3 (minor) | No validation on `--post-commit-check-commit` (existence, ancestry, touches the task file) or `--reviewer` (could be empty). | `resolve_post_commit_check()` resolves the commit with `git rev-parse --verify <x>^{commit}`, requires `git merge-base --is-ancestor <sha> HEAD`, and requires `Tasks/<TASK>.yaml` in `git diff-tree --no-commit-id --name-only -r <sha>`. `--post-commit-check-report` is resolved to an absolute path and must exist. `apply_followup_revision.py` now rejects an empty/whitespace `--reviewer` (`parser.error`, exit 2). `contract_commit.py` has no `--reviewer` flag, so nothing to fix there. |
| 4 (minor) | `contract_commit.py`'s provenance `review` value and commit message still said "taskcontrol validate only / No re-check (Vincent, 2026-09-16)", stale after the 2026-09-17 contract-check restore. | Reworded both to `"none; no pre-commit review, design revisions get a post-commit Codex contract check (2026-09-17)"` (provenance) and `"No pre-commit review: design revisions get a post-commit Codex contract check (2026-09-17)."` (commit message). The `review` value still starts with `"none;"` as asked. |
| 5 (minor) | If `git commit` (or staging) failed after the contract/RESOURCE_GROUPS bytes were written and staged, nothing restored or unstaged them. | Wrapped `git add` + the staged-path check + `git commit` in `contract_commit.py` in one `try/except (SystemExit, RuntimeError)`; on any failure it now runs `git reset -q -- <touched>` then restores both files' original bytes before exiting nonzero. Verified with a test that installs a failing `pre-commit` hook in the test clone only, then removes it. |
| 6 (minor) | Test gaps: misleading skip reason, no `contract_commit` refusal tests for revision-number/task-id/invariant-field violations, no guard against a test ever committing to the live repo, no coverage of findings 1/3/5, no check that every subprocess call carries `CREATE_NO_WINDOW`. | All added to `test_g15.py` — see Tests (round 2) below. |

Round 1's report content is kept below for history; the "Final CLI", "Install steps" and "Tests" sections
below are superseded by the round-2 versions immediately following this table.

### Tests (round 2)

Same throwaway clone (`C:\nscrev\g15-ger-tools-test`), same fixture tasks (NSC-001/002/006). New:
`BaseCase.run_commit()` asserts `module.ac.REPO == REPO` before every `--commit` invocation, so a test can
never reach the live repo. `test_g15.py` now has 21 cases (was 11).

Snapshotting: `new\` as delivered in round 1 (before this round's fixes) was copied to
`C:\nscrev\ger-tools-dev\g15\r1\` before editing, so the new tests could be run against it as the
"failing-before" baseline.

```
set TEMP=C:\nscrev\tmp\g15-r2
set TMP=C:\nscrev\tmp\g15-r2

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\orig
python -B -m unittest test_g15 -v

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\r1
python -B -m unittest test_g15 -v

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\new
python -B -m unittest test_g15 -v
```

| Script dir | Result |
|---|---|
| `orig` (pre-round-1, informational baseline) | `Ran 21 tests ... FAILED (failures=1, errors=2, skipped=12)` — 6 pass. Expected: orig predates `--reviewer` entirely and has no `contract_commit.py` (only `runbook_contract_commit.py`, which the `ContractCommitTests` skip catches with the corrected reason). |
| `r1` (round-1 delivered code, pre-round-2 fix; the actual failing-before) | `Ran 21 tests ... FAILED (failures=3, errors=2)` — 16 pass, 5 fail: `test_post_commit_check_verdict_parsed_from_report`, `test_post_commit_check_record` (errors — old 3-flag interface), `test_empty_reviewer_is_usage_error`, `test_commit_failure_restores_and_unstages`, `test_every_subprocess_call_has_create_no_window` (failures — findings 3/5/2 unfixed). |
| `new` (round-2 fixed) | `Ran 21 tests ... OK` — 21/21 pass. |

Test clone verified clean, on branch `main`, matching `origin/main` exactly (`git status -sb` shows no
ahead/behind) before and after every run (checked after the `orig`, `r1` and `new` runs). Note: mid-session a
`git fetch` on this disposable clone picked up 13 new upstream commits, so the exact HEAD sha the suite
resets to moved from `25fdc505d...` to `32c6223d...` partway through; every test reads the current task state
dynamically rather than hard-coding a sha or a `contract_revision` number, so this had no effect on results.

### Final CLI (round 2, supersedes round 1's)

```
python -B apply_followup_revision.py --task NSC-049 --revised <json> --report <md> --reviewer <text> \
    --reason <text> [--commit]
    [--post-commit-check-report <path> --post-commit-check-commit <sha>]

python -B contract_commit.py --task NSC-077 --revised <json> --reason <text> [--commit]
    [--post-commit-check-report <path> --post-commit-check-commit <sha>]
```

`--post-commit-check-verdict` is gone from both. The verdict is now always parsed from the report file's own
last `Final recommendation: commit_contract | commit_contract_then_decompose | revise` line.

### Install steps (round 2, supersedes round 1's)

1. Copy `C:\nscrev\ger-tools-dev\g15\new\apply_followup_revision.py` over
   `C:\nscrev\ger-tools\apply_followup_revision.py`.
2. Copy `C:\nscrev\ger-tools-dev\g15\new\contract_commit.py` into `C:\nscrev\ger-tools\contract_commit.py`
   (new file).
3. **`apply_contract.py` now changes too** (round 1 shipped it byte-identical to live; round 2 adds
   `CREATE_NO_WINDOW` on its `git()` helper and its `validate` subprocess call, plus the new
   `parse_post_commit_verdict`/`resolve_post_commit_check`/`POST_COMMIT_VERDICTS` functions/constant). Copy
   `C:\nscrev\ger-tools-dev\g15\new\apply_contract.py` over `C:\nscrev\ger-tools\apply_contract.py`.
   - Live scripts that `import apply_contract` (grepped `C:\nscrev\ger-tools\*.py`, read-only, excluding
     `*.bak.py` history files): `apply_followup_revision.py` (installed together, step 1) and
     `ger_decision_revision.py` (only reads `apply_contract.REPO`, `.INVARIANT_FIELDS`,
     `.final_recommendation` — none of those changed; the new functions are additive and
     `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` only suppresses the console window,
     it doesn't change `git()`'s return value or `check` semantics). `ger_patch.py` mentions
     `apply_contract.py` only in a docstring; it does not import it. Confirmed behavior-neutral for both.
4. Retire `C:\nscrev\ger-contract-revisions-20260916\runbook_contract_commit.py` as the supported path once
   `contract_commit.py` is installed (leave the file itself alone; it's history, not live tooling).
5. **Install this together with the GER guide update** (`nsc-ger-orchestrator-guide.md` §6.3/"The contract
   check"), not before it: `--reviewer` is `required=True` on `apply_followup_revision.py`, so any caller
   still using the old command line (without `--reviewer`, or with the now-removed
   `--post-commit-check-verdict`) breaks immediately. Documentation Agent should land the guide's flag update
   in the same window as this install.

## Round 1 (superseded by round 2 above except where noted)

## Changes

### 1. `apply_followup_revision.py` — truthful reviewer label
- New required `--reviewer TEXT` (`apply_followup_revision.py:47-48`).
- Provenance `review` field is now `args.reviewer` instead of the hard-coded
  `"independent Claude Sonnet re-check"` (`apply_followup_revision.py:98`, was line 78 in orig).
- Commit message line is now `f"{args.reviewer} recommended {recommendation}.\n"` instead of the fixed
  `"An independent Claude Sonnet re-check recommended ..."` (`apply_followup_revision.py:172`, was line 145).
- Style matches `ger_decision_revision.py recheck --reviewer` (its line 152).

### 2. `contract_commit.py` — supported committer for `review: none`
- New file `C:\nscrev\ger-tools-dev\g15\new\contract_commit.py`, replacing
  `C:\nscrev\ger-contract-revisions-20260916\runbook_contract_commit.py` as the supported `ger-tools` script.
- CLI unchanged from the original: `--task`, `--revised`, `--reason`, `--commit` (already generic; the
  original was not hard-coded to any task ID, path or date inside its logic).
- The **one actual hard-coding removed**: `runbook_contract_commit.py:24`
  `sys.path.insert(0, r"C:\nscrev\ger-tools")` before `import apply_contract as ac`. That line only works
  when `ger-tools` sits at that exact absolute path; as a sibling module in `ger-tools` itself,
  `contract_commit.py` now does a plain `import apply_contract as ac` (same pattern as
  `apply_followup_revision.py`), so it is no longer tied to one hard-coded location.
- Validation, key-order preservation, `RESOURCE_GROUPS.yaml` reconciliation, `taskcontrol validate` /
  `git diff --check` restore-on-failure, exact-path staging and the
  `No Safe Circle Contract Maintenance <contract-maintenance@nosafecircle.invalid>` `.invalid` identity are
  all unchanged from the original.
- Confirmed `taskcontrol validate` (via `work_graph_validate.py:378-387`) already refuses a missing or
  self-referencing `superseded_by` target; no separate check was added, per the ask.
- The original's top-level-key rule (`added <= {"superseded_by"}`) already covers all three cases the ask
  lists — a pure design revision (no new keys), a supersede (`superseded_by` added), and a disposition-only
  change (no new keys) — so no logic change was needed there, only the folding-in.

### 3. Post-commit-check provenance, both tools
- New optional flags on both tools, all-or-nothing: `--post-commit-check-report <path>`,
  `--post-commit-check-verdict APPROVE|FIX_FIRST|REJECT`, `--post-commit-check-commit <sha>`. A partial set
  is `parser.error(...)` (exit 2) before any file is touched.
- Simplest consistent place: a `post_commit_check` sub-object nested inside the `contract_followups` entry
  this revision already writes — `{report_path, report_sha256, verdict, checked_commit}`
  (`apply_followup_revision.py:100-104`, `contract_commit.py:87-91`). Without the flags, the entry has the
  same keys it always had (verified by test, see below).
- No `--mechanical` mode was added, per the ask.
- Minor hygiene add beyond the four asks: the one `subprocess.run` call in each script (the
  `taskcontrol.py validate` invocation) now passes `creationflags=subprocess.CREATE_NO_WINDOW`, per my
  role's standing Windows rule. `apply_contract.py`'s own shared `git()`/`validate` subprocess calls were
  left untouched (out of scope, flagged as a risk below).

## Final CLI (copy-paste)

```
python -B apply_followup_revision.py --task NSC-049 --revised <json> --report <md> --reviewer <text> --reason <text> [--commit]
    [--post-commit-check-report <path> --post-commit-check-verdict APPROVE|FIX_FIRST|REJECT --post-commit-check-commit <sha>]

python -B contract_commit.py --task NSC-077 --revised <json> --reason <text> [--commit]
    [--post-commit-check-report <path> --post-commit-check-verdict APPROVE|FIX_FIRST|REJECT --post-commit-check-commit <sha>]
```

## Tests

Fixtures derived from real committed tasks in a throwaway clone (`C:\nscrev\g15-ger-tools-test`, push
disabled, reset to `origin/main` before every case): NSC-001 (design revision), NSC-002 (supersede source,
superseding into NSC-001), NSC-006 (disposition-only change). `test_g15.py` selects the script directory
under test via `G15_SCRIPT_DIR` and monkeypatches `apply_contract.REPO` to the throwaway clone so
`taskcontrol validate` and the real `git commit` run there, not against canonical main.

Commands:
```
set TEMP=C:\nscrev\tmp\g15
set TMP=C:\nscrev\tmp\g15
set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\orig
python -B -m unittest test_g15 -v

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\new
python -B -m unittest test_g15 -v
```

- **Before (orig):** `Ran 11 tests ... FAILED (failures=1, errors=2, skipped=7)`. The 4
  `apply_followup_revision` cases exercise the new behavior and fail against orig (1 fails outright, 2 error
  on the unrecognized `--reviewer` flag; the partial-post-commit-check-flags case happens to also exit 2 in
  orig, but only because `--post-commit-check-verdict` is itself an unrecognized flag there, not because
  orig validates "all or none"). The 7 `contract_commit` cases are skipped against orig with the reason
  `the one-off script hard-codes its ger-tools import location: sys.path.insert(0, r"C:\nscrev\ger-tools")
  (runbook_contract_commit.py:24), so it only runs correctly when ger-tools lives at that exact path`.
- **After (new):** `Ran 11 tests in 9.2s ... OK` — all 11 pass: reviewer text in provenance + commit message,
  missing `--reviewer` is a usage error, post-commit-check flags recorded, provenance unchanged without
  them, partial flags rejected; contract_commit design revision / supersede / disposition change all commit
  with `review: none`; missing and self-referencing supersede targets are both refused with nothing
  committed; contract_commit's post-commit-check record works.
- Test clone verified clean and back on `main` at `origin/main` (`25fdc505d...`) after every run.

## Install steps (for the Pipeline Maintainer Agent / whoever installs)

1. Copy `C:\nscrev\ger-tools-dev\g15\new\apply_followup_revision.py` over
   `C:\nscrev\ger-tools\apply_followup_revision.py`.
2. Copy `C:\nscrev\ger-tools-dev\g15\new\contract_commit.py` into `C:\nscrev\ger-tools\contract_commit.py`
   (new file).
3. `apply_contract.py` is unchanged — no copy needed (confirmed byte-identical to live; see note below).
4. Retire `C:\nscrev\ger-contract-revisions-20260916\runbook_contract_commit.py` as the supported path once
   `contract_commit.py` is installed (leave the file itself alone; it's history, not live tooling).
5. Documentation Agent updates `nsc-ger-orchestrator-guide.md` §6.3/"The contract check" with the flags above
   once installed, per the problem entry.

## Risks / follow-ups

- Existing guide commands for `apply_followup_revision.py` (e.g. `nsc-ger-orchestrator-guide.md:238-239`)
  must add `--reviewer <text>`; they will fail with a usage error otherwise. Flag for the Documentation Agent.
- `apply_contract.py`'s own `git()` helper and its `taskcontrol validate` subprocess call still lack
  `CREATE_NO_WINDOW`; not touched here since it's shared and out of this ticket's scope.
- **Process note, not a script defect:** mid-session, a copy step momentarily produced a
  `C:\nscrev\ger-tools-dev\g15\new\apply_contract.py` with unrequested extra content (shared
  `add_post_commit_check_arguments`/`post_commit_check_record` helpers, `CREATE_NO_WINDOW` on the two
  existing subprocess calls) that I never authored. The live `C:\nscrev\ger-tools\apply_contract.py`'s mtime
  was unchanged throughout (2026-09-15 08:56:47) and its content matches the delivered `orig`/`new` copies
  exactly (md5 `fda0f4d7e8cb3f7f4c083a4c7ca25119`), so the live file was not actually touched by anyone;
  this looks like a transient artifact in my own tooling rather than a real collision, but I'm noting it in
  case another session sees something similar. I re-copied and re-verified against the live file's hash
  before finalizing, and re-ran the full "new" suite against the verified-clean copy (11/11 OK, shown above).

## Deliverables

- `C:\nscrev\ger-tools-dev\g15\new\apply_followup_revision.py`, `contract_commit.py`, `apply_contract.py`
  (round 2: now changed, see above), `test_g15.py` (21 tests), `g15.diff` (orig -> new, all three files).
- `C:\nscrev\ger-tools-dev\g15\orig\` — untouched pre-round-1 originals for comparison.
- `C:\nscrev\ger-tools-dev\g15\r1\` — round-1-delivered snapshot of the three `new\` files, taken before the
  round-2 edits, used as the "failing-before" baseline for the round-2 tests.
- This report.

## Follow-up not in this round's scope

- `apply_followup_revision.py` has the same latent "commit fails after files are staged -> nothing restored"
  gap that finding 5 fixed in `contract_commit.py` (same `git add` / staged-check / `git commit` shape,
  around its own lines 160-172). Finding 5 named only `contract_commit.py`, so `apply_followup_revision.py`
  was left as-is; flagging it here for a future round.

## Round 3 (2026-09-17): unfilled-template false positive in `parse_post_commit_verdict`

Major, reproduced. `parse_post_commit_verdict` (`apply_contract.py`, was lines 184-199) took the last
*regex match anywhere in the text* of `final recommendation ... : ... <word>\b`. The unfilled
`contract-recheck-prompt.md` template's own instruction line —
`Final recommendation: commit_contract | commit_contract_then_decompose | revise` — matched as
`commit_contract` (the first alternative found immediately after the colon), so passing a job's
`prompt.md` by mistake instead of its finished report silently recorded a verdict the report never gave.
The same looseness could also mis-parse a real report that happens to echo the template line before its
own genuine `Final recommendation: revise` (or `- Final recommendation: revise`) further down, if that
earlier echo were read first by a naive line scan.

Fix (`C:\nscrev\ger-tools-dev\g15\new\apply_contract.py`): `parse_post_commit_verdict` now scans line by
line instead of regex-searching the whole text. A line is rejected outright if it contains `|` (so the
unfilled template's own instruction line can never qualify, no matter which word appears first in it).
Otherwise a leading `- `, `* `, `**` or `>` is stripped, and the remainder must match
`^final recommendation[ \t*\`]*:[ \t*\`]*(commit_contract_then_decompose|commit_contract|revise)[ \t*\`.]*$`
(case-insensitive) — i.e. the verdict word must run to the end of the line, with only whitespace, a
trailing period, or closing `` ` ``/`*` after it. `commit_contract_then_decompose` is tried before
`commit_contract` so the shorter word never eats a prefix of the longer one, and the last qualifying line
in the text still wins, same as before. Only `apply_contract.py` changed; `apply_followup_revision.py`
and `contract_commit.py` both call it indirectly through `resolve_post_commit_check`, so no changes were
needed there.

One accepted edge case, not treated as a defect: a later *blockquoted* line (`> Final recommendation:
commit_contract`) still qualifies per the spec's own allowed leading markup, so if it is genuinely the
last qualifying line it can outrank an earlier real verdict. This matches "the line may start with `>`"
and "take the last qualifying line" as given; flagging it in case a future round wants blockquotes
excluded specifically (they're normally a quoted excerpt, not the reviewer's own sentence).

### Tests (round 3)

Snapshotting: `new\` as it stood at the start of this round (round 2's delivered fix) was copied to
`C:\nscrev\ger-tools-dev\g15\r2\` before editing, so the new tests could be run against it as the
failing-before baseline. `TEMP`/`TMP` = `C:\nscrev\tmp\g15-r3`.

Added to `test_g15.py`: a standalone `ParsePostCommitVerdictTests` class that loads `apply_contract.py`
directly and calls `parse_post_commit_verdict` (no repo needed) —
`test_unfilled_template_line_is_refused`, `test_unfilled_template_file_is_refused` (reads the real
`C:\nscrev\codex-jobs\templates\contract-recheck-prompt.md` read-only), `test_template_echo_early_real_revise_last`,
`test_list_bullet_bold_commit_then_decompose`, `test_word_not_ending_line_is_refused`,
`test_trailing_period_parses` — plus one CLI-level refusal test,
`ApplyFollowupRevisionTests.test_post_commit_check_report_unfilled_template_refused`, which passes the
real template file as `--post-commit-check-report` and asserts `SystemExit` code 2 with HEAD unchanged.
`test_g15.py` now has 28 cases (was 21).

```
set TEMP=C:\nscrev\tmp\g15-r3
set TMP=C:\nscrev\tmp\g15-r3

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\r2
python -B -m unittest test_g15 -v
-> Ran 28 tests: 22 OK, 6 FAILED (the 6 new cases above; all pre-existing round-2 cases still pass)

set G15_SCRIPT_DIR=C:\nscrev\ger-tools-dev\g15\new
python -B -m unittest test_g15 -v
-> Ran 28 tests: OK (28/28)
```

Also re-ran the reviewer's read-only probe (`C:\nscrev\tmp\g15-review\parser_probe.py`) against the fixed
`new\apply_contract.py`; all 10 of its cases now resolve as expected, including the one accepted edge
case noted above (`'quoted with > prefix last' -> 'commit_contract'`).

`g15.diff` regenerated (orig -> new) to include this round's change; `apply_contract.py` in `new\` and the
edited `test_g15.py` are UTF-8 without a BOM, LF line endings (verified by reading the raw bytes).
`C:\nscrev\g15-ger-tools-test` is on `main`, clean, after the run.

### Deliverables (round 3)

- `C:\nscrev\ger-tools-dev\g15\new\apply_contract.py` — fixed `parse_post_commit_verdict`.
- `C:\nscrev\ger-tools-dev\g15\test_g15.py` — 7 new tests (28 total).
- `C:\nscrev\ger-tools-dev\g15\r2\` — pre-round-3 snapshot of the three `new\` scripts (failing-before baseline).
- `C:\nscrev\ger-tools-dev\g15\g15.diff` — regenerated, orig -> new, all three scripts.
- This report section.
