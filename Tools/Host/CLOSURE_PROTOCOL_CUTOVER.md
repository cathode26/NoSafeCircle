# Closure and GER review protocol: deployment cutover

Written 2026-09-21 by the Pipeline Maintainer, alongside the branch that changes
the protocol. **Nothing here has been performed.** Deployment is outside the
implementation assignment; this records what a future authorized cutover must
move, what it must check first, and what it can roll back to.

Every figure below was measured on 2026-09-21 and says how. **Re-measure at the
cutover**: this file records a state, not a guarantee, and four of these facts
were not what the tracked source implied.

## What changed

Closure and GER decision reviews now declare their verdict as one JSON object,
validated by `Tools/Host/review_result.py` and bound to the exact bytes the
reviewer was given. Markdown survives as a rendered human view that carries a
marker, and every legacy reader refuses text carrying it. The reasoning is in
`review_result.py`; the short version is that eight review rounds were spent
trying to infer a verdict from prose and the defect space never closed.

## The supported set: these deploy together or not at all

A closure review crosses four of these in one run. Deploying a subset produces a
launcher that calls a validator with a different idea of what a result is.

| Tracked source | Deployed path | Today |
| --- | --- | --- |
| `Tools/Host/review_result.py` | `C:/NSC/tools/review_result.py` | **not deployed** (new) |
| `Tools/Host/jobs/check_closure_report.py` | `C:/NSC/tools/jobs/` | **not deployed** (never was) |
| `Tools/Host/jobs/legacy_closure_markdown.py` | `C:/NSC/tools/jobs/` | **not deployed** (new name) |
| `Tools/Host/jobs/claude_closure_review.py` | `C:/NSC/tools/jobs/` | **not deployed** (new) |
| `Tools/Host/nsc_paths.py` | `C:/NSC/tools/nsc_paths.py` | **not deployed** |
| `Tools/Host/codex-jobs/run_closure_review.sh` | `C:/NSC/tools/codex-jobs/` | **directory does not exist** |
| `Tools/Host/ger/ger_round.py` | `C:/NSC/tools/ger/ger_round.py` | deployed, in sync with `d886ece91` |
| `Tools/Host/ger/ger_node.py` | `C:/NSC/tools/ger/ger_node.py` | deployed, in sync |
| `Tools/Host/ger/apply_contract.py` | `C:/NSC/tools/ger/apply_contract.py` | deployed, in sync |
| `Tools/Host/ger/ger_decision_revision.py` | `C:/NSC/tools/ger/ger_decision_revision.py` | deployed, in sync |
| `Tools/Host/ger/apply_followup_revision.py` | `C:/NSC/tools/ger/apply_followup_revision.py` | deployed, in sync |
| `Tools/Host/ger/contract_commit.py` | `C:/NSC/tools/ger/contract_commit.py` | deployed, in sync |
| `Tools/Host/ger/main_write.py` | `C:/NSC/tools/ger/main_write.py` | deployed, in sync |

"In sync" measured by comparing the deployed bytes with `git show
d886ece91:<tracked path>`, ignoring line endings. All seven GER files matched.

`C:/nscrev/ger-tools` resolves to `C:\NSC\tools\ger` (measured with
`Path.resolve()`), so it is the same deployment under another name, not a second
copy.

## Findings a cutover plan has to start from

**1. The live closure runner has never called the closure checker.**

`C:/nscrev/codex-jobs/run_closure_review.sh` is the script that actually runs.
Its bytes DIFFER from the tracked `Tools/Host/codex-jobs/run_closure_review.sh`
at `d886ece91`, and it is the older shape: it invokes `check_job_result.py` with
`--verdict-grep "Final recommendation"` at line 67 and then stops. There is no
`check_closure_report.py` call in it, and no such file is deployed anywhere for
it to call.

This resolves a question that had been open in the Pipeline Maintainer queue:
"the live closure runner may still use the old generic checker; resolve which is
live." It does, and only that. **Eight rounds of review were spent on a file the
live path never ran.** That is not an argument that the work was wasted - it is
the reason the cutover is a first deployment rather than a replacement.

**2. There is therefore no prior version of the dedicated checker to restore.**
Rollback for that file means removing it and returning the launcher to its
current grep-only form, not reinstating an earlier checker. Do not invent one.

**3. The shared module root is empty.** Neither `nsc_paths.py` nor
`review_result.py` is deployed at `C:/NSC/tools/`. The tracked launcher resolves
helpers through `$HERE/../jobs` and then `nsc_paths.py` beside them; the deployed
layout has no such file, so deploying the tracked launcher without the Host-root
modules gives a script that exits 2 at setup.

**4. The GER deployment is real, live, and complete.** Unlike the closure path,
every GER tool this branch changes has a deployed counterpart that is currently
in sync with main. These are the files that need a coordinated move, and the ones
where a partial deployment does damage: a deployed `ger_round.py` writing
`RESULT.json` beside a deployed `apply_contract.py` that still greps `OUTPUT.md`
would read a derived view as a verdict.

## Drain or pin: measured now, re-measure then

**No closure review is in flight.** The newest closure-family *report* under
`C:/nscrev/codex-jobs/` is dated 2026-09-17. Seven prompts there have no report
beside them; four are closure reviews from 2026-09-17, abandoned or superseded
four days ago, and three are advice and design prompts from 2026-09-21 that are
not reviews at all. Leftover review clones from the 2026-09-17 runs remain on
disk and are stale artifacts, not active work.

So **no drain or pin is required for work that exists today.** At the cutover,
repeat this measurement rather than trusting it: a run started in between would
change the answer, and the correct handling of one is to let it finish on the
tools it started with, or to pin it to them explicitly.

The rule that does not depend on the measurement: never feed JSON evidence to a
Markdown reader, and never retry a failed JSON parse with the old parser. Both
are enforced in code, not only here.

## Rollback

For the GER family, restore the previous deployed copies - they are in sync with
`d886ece91`, so that commit is the restore point, and the existing `.bak.py`
convention in `C:/NSC/tools/ger/` is the mechanism already in use there.

For the closure family there is nothing to restore, because nothing is deployed.
Rollback is removing what was added and leaving
`C:/nscrev/codex-jobs/run_closure_review.sh` as it is.

If a rollback happens with v2 evidence already on disk: keep it. A `RESULT.json`
is not readable by the old tools and must not be converted, deleted, or
reinterpreted as a legacy report to make it readable.

## Explicitly not done, and not claimed

- **The two external adapters are not fixed.**
  `C:/nscrev/claude-jobs/host_closure_review.py` and `docker_closure_review.py`
  are untouched and still return exit 0 after a provider failure, and still read
  a verdict out of prose. `Tools/Host/jobs/claude_closure_review.py` is the
  source-tracked, tested replacement for both, but a tracked replacement existing
  is not the live files being fixed. Until a cutover deploys it and the callers
  are pointed at it, those two remain live and defective.
- No deployment, no cutover, no live enforcement change, and no edit to any file
  under `C:/NSC/tools/` or `C:/nscrev/` was made by this branch.
- Old reports and old GER packets stay readable through the explicitly labelled
  legacy paths (`--legacy-report`, `--legacy-rounds`, `--post-commit-check-legacy`,
  `ger_decision_revision --legacy`). None of them is ever selected automatically.
