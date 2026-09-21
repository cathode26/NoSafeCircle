# Closure and GER review protocol: deployment cutover

Written 2026-09-21 by the Pipeline Maintainer, alongside the branch that changes
the protocol. **Nothing here has been performed.** Deployment is outside the
implementation assignment; this records what a future authorized cutover must
move, what it must check first, and what it can roll back to.

Every figure below was measured on 2026-09-21 and says how. **Re-measure at the
cutover**: this file records a state, not a guarantee.

**On the strength of these claims.** An earlier draft of this file said the live
runner "has never called" the closure checker and that "eight review rounds were
spent on a file the live path never ran". A byte comparison and a directory
listing, both taken at one moment, cannot support either statement - they
describe now, not history. Astra caught the overclaim. The observations below are
stated as observations, and where a historical conclusion would be convenient it
is left unmade.

## What changed

Closure and GER decision reviews now declare their verdict as one JSON object,
validated by `Tools/Host/review_result.py` and bound to the exact bytes the
reviewer was given. Markdown survives as a rendered human view that carries a
marker, and every legacy reader refuses text carrying it. The reasoning is in
`review_result.py`.

## The supported set: these deploy together or not at all

A closure review crosses several of these in one run. Deploying a subset produces
a launcher calling a validator with a different idea of what a result is - and
the prompt template is part of the set, because an old Markdown prompt with a new
JSON validator fails even when every module is present.

| Tracked source | Deployed path | Observed 2026-09-21 |
| --- | --- | --- |
| `Tools/Host/review_result.py` | `C:/NSC/tools/review_result.py` | absent |
| `Tools/Host/nsc_paths.py` | `C:/NSC/tools/nsc_paths.py` | absent |
| `Tools/Host/jobs/check_closure_report.py` | `C:/NSC/tools/jobs/` | absent |
| `Tools/Host/jobs/legacy_closure_markdown.py` | `C:/NSC/tools/jobs/` | absent (new name) |
| `Tools/Host/jobs/claude_closure_review.py` | `C:/NSC/tools/jobs/` | absent (new) |
| **`Tools/Host/jobs/closure_record.py`** | `C:/NSC/tools/jobs/` | absent (new) |
| **`Tools/Host/codex-jobs/templates/contract-closure-review-prompt.md`** | `C:/NSC/tools/codex-jobs/templates/` | directory absent |
| **`Tools/Host/codex-jobs/make_closure_prompt.py`** | `C:/NSC/tools/codex-jobs/` | directory absent |
| `Tools/Host/codex-jobs/run_closure_review.sh` | `C:/NSC/tools/codex-jobs/` | directory absent |
| `Tools/Host/ger/ger_round.py` | `C:/NSC/tools/ger/ger_round.py` | deployed, bytes match `d886ece91` |
| `Tools/Host/ger/ger_node.py` | `C:/NSC/tools/ger/ger_node.py` | deployed, bytes match |
| `Tools/Host/ger/apply_contract.py` | `C:/NSC/tools/ger/apply_contract.py` | deployed, bytes match |
| `Tools/Host/ger/ger_decision_revision.py` | `C:/NSC/tools/ger/` | deployed, bytes match |
| `Tools/Host/ger/apply_followup_revision.py` | `C:/NSC/tools/ger/` | deployed, bytes match |
| `Tools/Host/ger/contract_commit.py` | `C:/NSC/tools/ger/` | deployed, bytes match |
| `Tools/Host/ger/ger_patch.py` | `C:/NSC/tools/ger/ger_patch.py` | deployed, bytes match |
| `Tools/Host/ger/main_write.py` | `C:/NSC/tools/ger/main_write.py` | deployed, bytes match |

"Bytes match" means the deployed file equals `git show d886ece91:<tracked path>`
ignoring line endings.

**The job record is part of the set too.** `closure_record.py` defines what a
finished standalone closure job publishes and how a consumer reads it. Deploying
a launcher that writes the record without the consumer that requires it leaves
the record unread; deploying the consumer without the launchers makes every
generated post-commit check refuse, because no record will exist. Both ends move
together or the generated route stops working.

**The prompt and the validator are one unit.** The template now asks reviewers
for a JSON object; `make_closure_prompt.py` fills it. A deployment that moves the
validators but leaves an old template produces reviews the new readers refuse,
and a deployment that moves the template but not the validators produces JSON
nothing reads. Move the routing that selects them at the same time.

`C:/nscrev/ger-tools` resolves to `C:\NSC\tools\ger` (measured with
`Path.resolve()`), so it is that deployment under another name, not a second copy.

## What is observed about the live closure path

**The live launcher differs from the tracked one, today.**
`C:/nscrev/codex-jobs/run_closure_review.sh` is what runs. Its bytes differ from
`git show d886ece91:Tools/Host/codex-jobs/run_closure_review.sh`. The live copy
invokes `check_job_result.py --verdict-grep "Final recommendation"` at line 67
and contains no call to `check_closure_report.py`.

**No closure checker is deployed for it to call**, at
`C:/NSC/tools/jobs/` or anywhere else searched; `C:/NSC/tools/codex-jobs/` does
not exist.

**What that does and does not establish.** It establishes that the live path, as
it stands now, performs the generic job check and no closure-specific check. It
does NOT establish what the live path did at any earlier date, nor that the
tracked checker was never deployed and later removed, nor anything about which
file past review rounds were exercising. Those would need history this file does
not have. If the question matters at cutover, the deployed tree and any backups
are the place to answer it, not this measurement.

**There is no prior version of the dedicated checker to restore.** Nothing by
that name is deployed now, so a rollback cannot reinstate one. Do not invent one.

**The GER deployment is live and currently in sync.** Every GER tool this branch
changes has a deployed counterpart whose bytes match main. These are the files
needing a coordinated move, and where a partial deployment does damage: a
deployed `ger_round.py` writing `RESULT.json` beside a deployed
`apply_contract.py` that still greps `OUTPUT.md` would read a derived view as a
verdict.

## Drain or pin: what was observed, and what it is worth

Observed under `C:/nscrev/codex-jobs/`: the newest closure-family **report** is
dated 2026-09-17. Seven prompts have no report beside them - four closure reviews
from 2026-09-17, and three advice and design prompts from 2026-09-21 that are not
reviews. Review clones from the 2026-09-17 runs remain on disk.

**That is weak evidence and must not be treated as a clearance.** A file
timestamp says when something was last written, not whether a process is running;
an orphaned prompt may be abandoned or may be a job still going; and a run
started after this measurement would not appear in it at all.

**So the cutover must perform its own active-run check**, not rely on this
paragraph. Look for running provider processes, recently modified job
directories, and lock or clone directories with recent mtimes. This needs no job
launch and no spend. If an active run is found, let it finish on the tools it
started with, or pin it to them explicitly; if none is found, record that
explicitly as of that moment.

The rule that holds regardless: never feed JSON evidence to a Markdown reader,
and never retry a failed JSON parse with the old parser. Both are enforced in
code, not only here.

## Rollback

**GER family:** restore the previous deployed copies. They currently match
`d886ece91`, so that commit is the restore point, and the `.bak.py` convention
already in use in `C:/NSC/tools/ger/` is the mechanism.

**Closure family:** there is a live launcher family to return to, even though no
dedicated checker is deployed - so "nothing is deployed" would be too broad.
Reverting means restoring the observed launcher and helper set as it stands now:
`C:/nscrev/codex-jobs/run_closure_review.sh` with its generic
`check_job_result.py` call, the helpers under `C:/NSC/tools/jobs/`, and the two
external adapters under `C:/nscrev/claude-jobs/`. Take a copy of each before
changing anything, because the tracked source is NOT a faithful record of what is
live - the launcher already differs.

**If reverting leaves the new route unsupported, stop the new route** rather than
running it against old tools: new closure jobs must not launch into a
half-reverted set.

**Preserve JSON evidence through any rollback.** A `RESULT.json` is not readable
by the old tools and must not be converted, deleted, or reinterpreted as a legacy
report to make it readable.

## Explicitly not done, and not claimed

- **The two external adapters are not fixed.**
  `C:/nscrev/claude-jobs/host_closure_review.py` and `docker_closure_review.py`
  are untouched and still return exit 0 after a provider failure, and still read
  a verdict out of prose. `Tools/Host/jobs/claude_closure_review.py` is the
  source-tracked, tested replacement, but a tracked replacement existing is not
  the live files being fixed.
- No deployment, no cutover, no live enforcement change, and no edit to any file
  under `C:/NSC/tools/` or `C:/nscrev/` was made by this branch.
- Old reports and old GER packets stay readable through explicitly labelled
  legacy paths (`--legacy-report`, `--legacy-rounds`, `--post-commit-check-legacy`,
  `ger_decision_revision --legacy`). None is ever selected automatically.
