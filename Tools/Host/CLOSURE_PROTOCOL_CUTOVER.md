# Closure and GER review protocol: deployment cutover

Written 2026-09-21 by the Pipeline Maintainer, alongside the branch that changes
the protocol. **Nothing here has been performed.** Deployment is outside the
implementation assignment; this records what a future authorized cutover must
move, what it must check first, and what it can roll back to.

**The deployed state is no longer recorded here. Ask the tool:**

```
python -B Tools/Host/deploy_tools.py --check
```

It reports every declared file as current, stale, modified, absent or extra,
and names the commit the deployment was made from. The table below says WHAT
deploys; `deploy_tools.py` says what is deployed right now.

This column used to hold hand-measured results - "deployed, bytes match
`d886ece91`" - and the reason it is gone is worth stating exactly, because it is
not the obvious one.

**Those cells were never false.** All seven deployed GER tools still match
`d886ece91` byte for byte; that was verified on 2026-09-22, after the merge that
moved main to `ba2ce2b00`. What expired was not their accuracy but their
usefulness: the column answered "does the deployment match `d886ece91`?" while
every reader was asking "is the deployment current?", and once main moved those
stopped being the same question.

The GER Agent raised it on 2026-09-22 by comparing deployed against MAIN and
finding two of three drifted. That measurement is correct and it is why the
cutover was held. The inference that the table was stale is the part to be
careful with - the table never claimed deployed equals main.

**A stale-but-true measurement is worse than a wrong one**, which is the whole
argument for deleting the column rather than refreshing it. A wrong claim gets
caught the first time somebody checks it. This one survived checking, because
checking confirmed it.

Every other figure below was measured on 2026-09-21 and says how. **Re-measure at the
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

| Tracked source | Deployed path |
| --- | --- |
| `Tools/Host/review_result.py` | `C:/NSC/tools/review_result.py` |
| `Tools/Host/nsc_paths.py` | `C:/NSC/tools/nsc_paths.py` |
| `Tools/Host/jobs/check_closure_report.py` | `C:/NSC/tools/jobs/` |
| `Tools/Host/jobs/legacy_closure_markdown.py` | `C:/NSC/tools/jobs/` |
| `Tools/Host/jobs/claude_closure_review.py` | `C:/NSC/tools/jobs/` |
| **`Tools/Host/jobs/closure_record.py`** | `C:/NSC/tools/jobs/` | absent (new) |
| **`Tools/Host/codex-jobs/templates/contract-closure-review-prompt.md`** | `C:/NSC/tools/codex-jobs/templates/` | directory absent |
| **`Tools/Host/codex-jobs/make_closure_prompt.py`** | `C:/NSC/tools/codex-jobs/` | directory absent |
| `Tools/Host/codex-jobs/run_closure_review.sh` | `C:/NSC/tools/codex-jobs/` |
| `Tools/Host/ger/ger_round.py` | `C:/NSC/tools/ger/ger_round.py` |
| `Tools/Host/ger/ger_node.py` | `C:/NSC/tools/ger/ger_node.py` |
| `Tools/Host/ger/apply_contract.py` | `C:/NSC/tools/ger/apply_contract.py` |
| `Tools/Host/ger/ger_decision_revision.py` | `C:/NSC/tools/ger/` |
| `Tools/Host/ger/apply_followup_revision.py` | `C:/NSC/tools/ger/` |
| `Tools/Host/ger/contract_commit.py` | `C:/NSC/tools/ger/` |
| `Tools/Host/ger/ger_patch.py` | `C:/NSC/tools/ger/ger_patch.py` |
| `Tools/Host/ger/main_write.py` | `C:/NSC/tools/ger/main_write.py` |

`deploy_tools.py` compares with line endings normalised, because deployed
copies are CRLF in the working tree while tracked blobs are LF - an unnormalised
comparison calls every file different.

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

### Where the closure family must land, and why it is not where the docs say

**Fable, 2026-09-21, measured.** The launcher now resolves its helpers relatively
- `$HERE/../jobs` - and refuses rather than reaching for an absolute fallback.
That makes the deployed LOCATION load-bearing, and the two constraints on it did
not agree:

- Every doc that names this family puts it at `C:/nscrev/codex-jobs/`
  (`Tools/Host/README.md`, `Docs/AI-Pipeline/Agent-Operations/maintained-locations.md`,
  and the command line in `C:/NSC/nsc-ger-orchestrator-guide.md`). Deployed
  there, `$HERE/../jobs` is `C:/nscrev/jobs`, **which does not exist** - verified.
  Exit 2 on every run.
- Deployed to `C:/NSC/tools/codex-jobs/` instead, the table above is satisfied but
  `make_closure_prompt.py` used to write the prompt beside ITSELF while the runner
  reads `<work root>/codex-jobs/<job>.prompt.md`. Exit 2, "missing prompt".

Either reading gave a dead closure path. **The writer is fixed rather than the
document**: `make_closure_prompt.py` now writes to the work root through the same
`nsc_paths` resolver the runner uses, so where the prompt goes is one rule in one
place. The templates stay beside the script, because they are part of the tool.

**So: deploy this family to `C:/NSC/tools/codex-jobs/` and `C:/NSC/tools/jobs/`**,
siblings, as the table says - and treat every doc that says `C:/nscrev/codex-jobs/`
as needing the same edit in the same window. Those docs are the Documentation
Agent's and the GER Agent's; this branch does not touch them.

**Two helpers were missing from the table and are added below**, because the
launcher refuses without them:

| Tracked source | Deployed path | Observed 2026-09-21 |
| --- | --- |
| `Tools/Host/jobs/resolve_codex.py` | `C:/NSC/tools/jobs/` |
| `Tools/Host/jobs/check_job_result.py` | `C:/NSC/tools/jobs/` |

The deployed `resolve_codex.py` predates two fixes that are on `main` already, not
on this branch: a candidate whose `--version` exits non-zero is no longer accepted
on the strength of its stdout, and an explicit `NSC_CODEX_EXE` is now held to the
same probe as a discovered one. The launcher hands it contract reviews. **Refresh
it in the same window** - the drift is not this branch's doing and is this branch's
problem, because relative resolution means whatever is beside the launcher is what
runs.

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

**The GER deployment is live and is NO LONGER in sync.** This sentence said "is
currently in sync" and was true on 2026-09-21, when main was `d886ece91`. Main is
past that now and the deployment is not: the seven changed GER tools still hold
the `d886ece91` bytes. That is a complete, self-consistent OLD family, which is
the permitted state - not a half-deployed one - but it is no longer main. This
was the one genuinely false sentence in this document, and it is here rather than
in the table the GER Agent flagged; run `deploy_tools.py --check` instead of
trusting either. These are the files
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

## An in-flight packet cannot cross the cutover

The new producer refuses a historical decision prerequisite and has no
legacy-continuation flag, deliberately: continuing an old packet on new tools
would mean one of the two things this protocol exists to prevent - inferring a
verdict from a report that never declared one, or rewriting old evidence into a
shape the new reader accepts.

So a packet that is part-way through its rounds when the cutover happens has
exactly two honest outcomes:

- **Pin it.** Finish it on the tool family it started with, kept in place for
  that packet. The legacy consumers stay supported for exactly this reason.
- **Start a new packet.** Run the remaining rounds as a new JSON packet, with
  the old one closed as superseded and its reports left as they are.

**Not an option:** reinterpreting an old report as a new result, back-filling a
`RESULT.json` from a Markdown report, or passing a historical record through a
legacy flag to get it accepted by a new consumer. `--legacy-rounds` and the other
legacy flags read old evidence as old evidence; they are not a migration.

Old reports and old packets remain **readable and applicable** through those
explicit consumers after the cutover. Nothing already recorded stops working.
What stops working is mixing the two families inside one packet.

This is a stated limit of this delivery, not a defect to fix later: no
historical-resume feature is planned, and if one is ever wanted it needs its own
design, because it has to answer what a verdict means when the round that
produced it never declared one.

## Three ways a post-commit check reaches `apply_contract`, and how to say which

The flags are not interchangeable and none of them is a fallback for another. A
generated job that fails does NOT become an import by leaving its record out; a
legacy report is not selected because a JSON parse failed. Say which route this
evidence took.

**Generated here** - the launcher produced `JOB.result.json`, the derived
`JOB.report.md` beside it, and `JOB.result.json.metadata.json`:

```text
--post-commit-check-report <jobs>/JOB.result.json --post-commit-check-commit <SHA>
```

**Imported JSON** - a person carried a `.result.json` from somewhere this host did
not run. There is no job record, so the import has to be declared, with who:

```text
--post-commit-check-report <path>.result.json --post-commit-check-commit <SHA> \
  --post-commit-check-import "<who carried it>"
```

**Imported Markdown**, written before the cutover - **both** flags, because it is
both hand-carried and in the old format:

```text
--post-commit-check-report <path>.md --post-commit-check-commit <SHA> \
  --post-commit-check-import "<who carried it>" --post-commit-check-legacy
```

`--post-commit-check-legacy` alone is refused: nothing in current use produces
that format, so a legacy report is necessarily hand-carried and the two
selections stay separate on purpose.

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
