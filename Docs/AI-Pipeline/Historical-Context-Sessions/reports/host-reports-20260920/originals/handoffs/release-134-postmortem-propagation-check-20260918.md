# Finding: add a fast propagation check for symbol removal/rename, not a full CI sweep

Written by the Release Agent, 2026-09-18, from the PR #134 release (2026-09-17). Requested by Vincent after asking "is there something we're missing" — he wants a fix that costs about a minute, not a slowdown to merges.

## What happened

179 commits landed on local main with zero CI feedback (CI only runs on the release's temporary PR, never on ordinary main-write merges). One of those commits removed `contract_locality_auditor` from `CREW_SESSION_ROLES` in `Pipeline/ExecutionCrew/session_pool.py`. It broke tests in **6 different files**, but each only surfaced when CI happened to run that specific file — so the release took 4 rounds of "fix one, CI finds the next" before Pipeline Maintainer finally ran every CI-listed Python test target locally in one pass and caught the last 2 at once. Separately, a test-method rename (`330cd3777`) left 2 stale method names hardcoded in `.github/workflows/assistant-candidate-ci.yml`, caught the same reactive way.

Full detail and every commit sha: `C:\NSC\agent-state\release-agent.md` (search "CI-config fix" and "auditor").

## Why "just run the full CI Python suite before every merge" doesn't fit

Checked: the workflows reference **101 distinct Python test targets** (`grep -rhoE "python[3]? (-m )?[A-Za-z0-9_./]+\.py" .github/workflows/*.yml | sort -u | wc -l`). Running all of them on every main-write merge is a real slowdown, not the "about a minute" Vincent asked for, and it would also run suites that have nothing to do with the change being merged.

## Proposed fix: two fast, narrowly-triggered checks

Trigger only when a merge removes or renames a symbol (function, constant, enum/role value, class) that other files import or reference — not on every merge.

1. **Repo-wide grep for the old name, including `.github/workflows/*.yml`.** A few seconds (`git grep -n "<old_name>"` across the whole tree). This alone would have caught the stale-test-id failure; it wasn't checked against workflow files at commit time.
2. **Run only the test files that import the changed module/symbol**, not the full suite: `git grep -l "<changed_symbol_or_its_module>" -- Pipeline/**/tests/*.py` (or equivalent), then run just those files. For the `contract_locality_auditor` removal this would have been ~6 files, not 101 — seconds to run, not minutes. It would have caught the hidden-count assertions (`len(idle) == 4`, `POOL_CAPACITY 40`) that a pure grep can't, since those don't reference the removed name literally.

Neither step needs new tooling — both are existing commands. The only change is making them a standard last step specifically for "I just removed/renamed something," documented in the main-write protocol, not a blanket pre-merge gate.

## Who this is for

- **Pipeline Maintainer Agent:** owns the tests and could turn step 2 into a one-line helper (find test files importing a given symbol, run them) if that's worth formalizing; otherwise it's just a documented manual step.
- **Documentation Agent:** add this as a required last step in the main-write protocol / runbook, scoped specifically to symbol removal/rename, so it doesn't slow down ordinary merges.

## Not in scope here

Running CI continuously (e.g., a rolling non-release validation PR) would catch drift even earlier but costs real runner time and turnaround on every commit — mentioned to Vincent as the other option; he didn't ask for it, so leaving it out of this proposal.

## Correction, 2026-09-18 (Pipeline Maintainer Agent)

Three of the four CI-fix rounds were **not** symbol removals/renames at all — `contract_locality_auditor` was removed from the *value* of a tuple (`CREW_SESSION_ROLES`), and the tests that broke asserted counts derived from it ("four roles", "exactly forty leases"). A grep for the removed name finds nothing in that case; **step 1 (grep) would not have caught them.** Only step 2 (run the tests that import the changed module) would have. The fourth round (the viewer `f-scope` test) came from an HTML default moving into script — neither step catches that one; only running the importing tests does.

Net effect: **step 2 is the one that matters most and the one worth making reliable; step 1 stays for the genuine-rename case** (it did catch the stale-test-id failure). Pipeline Maintainer is building this as a small helper, `C:\nscrev\job-tools\propagation_check.py <clone> <base>..<head>`, doing both steps and printing (or with `--run`, running) just the importing tests — seconds, not a sweep — rather than leaving it as a manual step nobody reliably runs.
