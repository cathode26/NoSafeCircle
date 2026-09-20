# Agent survey: what are we missing, and who could we delegate to? (2026-09-16)

Vincent asked the Documentation Agent to ask every agent. The same three questions went to the Game Agent, GER Agent, Art Director Agent and Pipeline Maintainer Agent:
1. What's missing?
2. What would you delegate, and to what kind of agent?
3. What's wrong or unclear in the directory?

Answers are added below as they arrive, followed by a combined summary.

---

## Documentation Agent

**Missing:**
1. **A live board of agent work.**
   - "In flight" lives in scattered places: the journal, handoff briefs, session messages and directory section 8.
   - Today section 8 was hand-edited about six times to stay current.
   - A small shared file (for example `C:\nscrev\reports\handoffs\board.json`) that every handoff appends to, or a viewer panel, would replace that.
2. **Handoffs aren't queryable.**
   - A session message arrives as a user turn in the receiver. Nothing lists open handoffs, their owner, or whether they were answered, unless you read transcripts.
3. **Doc claims drift from the code.**
   - Twice today the docs stated something wrong about code: the V1 pointer, and "crews are single-provider".
   - Both were caught only by luck. Nothing checks code citations in guides.

**Would delegate:**
- **Codex doc-verification job** (FUT5 review mode against a doc): check every file:line and behaviour claim in a changed guide. After each major doc change, a few times a day.
- **A cheap "doc sync" helper** (Haiku or Sonnet subagent): propagate one decision across the doc set, re-grep, and make the mechanical edits. Several times a day.
- **A "Scribe" helper** (Haiku): turn handoff messages and decisions into journal lines and the live board. Continuous; this is the biggest time saver.

**Directory:** section 8 goes stale within hours, so it should point to the live board once one exists. The roles still without a session or stand-in (Decomposition, Watcher) are unresolved.

---

## Game Agent (game developer and Integration Steward)

**Missing:**
1. **A single "verify candidate" command.** Each merge candidate is about 15 manual steps: fetch, trial merge in `branch-verify`, clone, fill the review prompt, run Codex, parse `CODEX_VERDICT.json`, write the merge message, fast-forward. Today viewer-step1 and P34 each needed all of them.
2. **A runner preflight.**
   - Host Codex `workspace-write` can't write `.git`, so host "do" jobs fail.
   - Docker was stopped, and the first NSC-077 run wasted a round.
   - The Codex jobs CLI should pick Docker for do jobs and check that Docker is up.
3. **Unity verification is manual.** It needs scratch Editor scripts, a stale `Temp\UnityLockfile`, and cleanup of 36 line-ending churn files and code-coverage `Settings.json` after every run. Churn on `WizardAnimator.controller` blocked a fast-forward in Vincent's checkout. A churn tool that really clears content-identical files is needed.
4. **Also manual:**
   - `SuccessfullTasks` archiving: `archive_successful_tasks.py` exists only in the Game Agent's session scratchpad;
   - delivery evidence;
   - host-sandbox test errors (SID mapping, `TemporaryDirectory` ACL) add noise to Codex verdicts.

**Would delegate:**
- **"merge-verifier"** custom subagent (Sonnet): the trial merge, non-Unity suites, launching the Codex review, and a one-paragraph verdict. Every candidate, several a day.
- **"unity-runner"** helper (Sonnet subagent, or a host job once Unity is allowed): builder run twice plus test filters on the exact commit, churn cleanup, counts and log paths. Every game candidate, daily.
- **"delivery-evidence"** subagent (Sonnet, following `nsc-delivery-evidence-guide.md`): every merged task. Also the archive script turned into a repo tool by the Pipeline Maintainer. A few a day.

**Directory:**
- Make sure it records Vincent's ruling that the Game Agent is also the Integration Steward. *(Checked: section 2 already says so.)*
- `nsc_watch.py` shows only the host Codex account's quota, while Docker jobs may use a different login, so the 90% pause rule is ambiguous for Docker jobs.

## GER Agent

**Missing:**
1. **A supported commit-and-supersede path without the re-check.**
   - The GER Agent reports that Vincent dropped the re-check gate on 2026-09-16, but GER guide sections 6.2 and 6.3 still require one.
   - `apply_followup_revision.py` refuses `superseded_by`, so NSC-094's supersede went through a one-off runbook script.
   - Needs a Pipeline Maintainer tool plus a guide update.
2. **No record of code that lands outside the task graph.** The 9/14 GER packets predate the playable-build commit `9a3d22c56`: a DemoRunFlow fireball, a 9-enemy squad with no task, and a stationary, untested fire caster. So every decision today first needed a fresh research pass over `main`.
3. **No cascade lookup.** Superseding NSC-094 forced NSC-015 and NSC-055 revisions, and the 9/15 room revisions will put the fixed squad in the wrong rooms. Dependents and text references are found by grep; a "who references X" tool would help.

**Would delegate:**
- **A `ger-drafter` custom subagent** (Sonnet), with the key-set, invariant and folder-claim rules built in: turns packets into briefs and drafts revisions from the GER Agent's decisions. Used today for 5 tasks; several times per queue burst.
- **Medium Codex jobs** for mechanical contract cascades: dependency swaps, renames across `Tasks/`, in-memory validation. About weekly.
- **Already delegating:** art-contract content (NSC-078 prop list and prompts) to the Art Director Agent, and GER helper-script fixes to the Pipeline Maintainer (the hold helper was fixed today).

**Directory:**
- Section 8 is stale:
  - NSC-077 rev 3 is committed with the Lantern Wraith;
  - NSC-094 is superseded;
  - the follow-ups are NSC-055 rev 3 and NSC-015 rev 7;
  - the NSC-077 implementation has started (Codex, under the Game Agent's review).
  - *(Checked on `main`: NSC-077 rev 3 is `d9af025a5`, NSC-055 rev 3 is `588bfc03b`, NSC-015 rev 7 is `50753aa52`, and NSC-094 rev 2 superseded by NSC-077 is `95492e43d`. Directory updated. The implementation start is as reported.)*
- The GER Agent row should record Vincent's 9/16 rule: no re-check gate, and `taskcontrol validate` is the only check. It should also say NSC-015's decomposition rerun must use rev 7. *(The rev 7 note is added. The no-re-check rule waits for Vincent's confirmation in the Documentation Agent session, because it removes a check from the GER guide.)*

## Art Director Agent

**Missing:**
1. **In-game captures.** It can't take a 1080p or 1440p Game-view shot. Today the wizard's real size came from code plus an old NSC-044 test render; the screenshot requested from Vincent never arrived.
2. **Reusable review tooling.** It rebuilds it by hand for every job: today about 10 one-off Pillow scripts (contact sheets, game-scale simulation, GIFs, mask-diff proof, frame metrics).
3. **PixelLab spend tracking.** Quotes are provisional. The shared balance moved 1 generation more than the 19 the tools reported, and there's no per-job charge history.

**Would delegate:**
- **Keep the Sonnet art-director subagent** for sheets, GIFs and metrics on every art job (used twice today; it worked).
- **A one-off Codex job** to build a reusable art-review toolkit: camera-model game-scale panel, sheets, GIFs, mask-diff, frame metrics.
- **The Game Agent, or a Unity capture script:** gameplay-camera shots at 1080p and 1440p after each art integration, or on request (about weekly).
- **A Haiku helper** for every PixelLab batch: download logs, SHA-256, alpha bounding boxes and inventory JSON.

**Directory:**
- Section 3.1 names no owner for in-game screenshots used in art review. *(Done: the Game Agent owns them; row added.)*
- The Art Director launch prompt said "don't delegate it to an art-director subagent". *(Checked: already replaced 2026-09-16 in `launch-prompt-density-and-wisp-20260916.md`; no copy of that line remains.)*

## Pipeline Maintainer Agent

**Missing:**
1. **No Unity or Codex runs in its own lane.** P34's import proof and every Codex review go round-trip through the Game Agent. Today P34 and viewer-step1 each got a Codex FIX_FIRST only after the Maintainer's own reviewer approved, which cost two extra rounds.
2. **Approved branches go stale.** Branches are based on a `main` that has since moved. A cheap "rebase and trial-merge onto current main" step in the Maintainer's lane would catch overlaps earlier.
3. **Pre-existing red tests hide coverage, and nobody owns them.** `execution_crew_smoke_test` stops at line 335, and `local_rehearsal.py` is missing (P36; breaks 3 GauntletView modules).

**Would delegate:**
- **A Codex review job on every fix branch before handoff** (Feature A, being built). About 3 a day.
- **A Sonnet helper** for ports and small fixes (already in use). Several a day.
- **A Haiku "test-runner" subagent:** runs the listed suites at base and head and returns counts only. Several a day.
- **An owner for pre-existing test debt:** a pipeline-maintainer subagent, weekly.

**Directory:**
- Section 2 still says a Documentation Agent subagent covers the Pipeline Maintainer. *(Checked: already fixed; the row says "running since 2026-09-16". The Maintainer likely read an older copy.)*
- Say explicitly that the GER helper scripts in `C:\nscrev\ger-tools` are Pipeline Maintainer code, while GER holds and releases are GER Agent work. *(Done: section 3.1.)*

---

## Combined summary for Vincent (2026-09-17)

### The five themes

1. **Verification is manual and runs through the Game Agent.**
   - A merge candidate takes about 15 manual steps.
   - The Pipeline Maintainer can't run Codex reviews or Unity itself, which cost two extra review rounds today.
   - **Fix:**
     - the Codex jobs tool (FUT5, being built);
     - a **merge-verifier** helper;
     - the Pipeline Maintainer runs its own Codex review before handoff (already pre-approved; Docker for anything that commits).
2. **Unity work is manual.**
   - Runs need scratch Editor scripts; lockfiles and 36 or more line-ending churn files need clearing after every run.
   - Nobody can take in-game screenshots for art review.
   - **Fix:** a **unity-runner** helper; a churn cleanup that really clears content-identical files (P18); the Game Agent owns screenshots (directory updated), with a capture script as a follow-up.
3. **Useful tools live in scratchpads or one-off scripts:**
   - the Game Agent's `archive_successful_tasks.py`;
   - the GER Agent's `runbook_contract_commit.py`;
   - about 10 Pillow review scripts the Art Director rewrites per job.
   - **Fix:** make them supported tools: P35 (archive), G15 (contract commits, in progress), and a one-off Codex job to build an art-review toolkit.
4. **Nothing tracks the shared picture:**
   - open handoffs;
   - PixelLab spend per job (provisional quotes differ from charges);
   - quota for the Docker Codex account (the watch tool sees only the host account);
   - code committed without a task;
   - which tasks reference a given task.
   - **Fix:** a live handoff board plus a Haiku scribe; a PixelLab spend ledger; per-account quota in the watch tool; `taskcontrol references` and a task-less code log (G16).
5. **Red tests nobody owns** hide coverage (P36, P37). **Fix:** a weekly test-debt pass by the Pipeline Maintainer.

### Helper agents the agents asked for

| Helper | Kind | Used by | How often | Recommendation |
|---|---|---|---|---|
| **merge-verifier** | custom subagent, Sonnet | Game Agent | several a day | Create now: biggest time saver |
| **test-runner** | custom subagent, Haiku; returns counts only | Pipeline Maintainer, Game Agent | several a day | Create now; shared by all |
| **ger-drafter** | custom subagent, Sonnet; key-set, invariant and folder-claim rules | GER Agent | bursts (5 today) | Create now |
| **delivery-evidence** | custom subagent, Sonnet | Game Agent | a few a day | Create now |
| **unity-runner** | custom subagent, Sonnet; builder twice, test filters, churn cleanup | Game Agent | daily | Create now, under the Game Agent's existing Unity authority |
| art batch recorder | Haiku helper: downloads, hashes, bounding boxes, inventory | Art Director | every PixelLab batch | Later; a general Haiku subagent works today |
| scribe | Haiku helper: journal lines and live board | Documentation Agent | continuous | Later, together with the board |

### Tools to build (Pipeline Maintainer, or Codex jobs)

In suggested order after the current queue:
1. **The Codex jobs tool** (in progress), with a "verify candidate" flow on top.
2. **Churn cleanup** (P18).
3. **`archive-successful`** (P35).
4. **GER contract commit tool** (G15, in progress).
5. **`taskcontrol references`** and a task-less code log (G16).
6. **The art-review toolkit:** a Codex "do" job, which needs Vincent's go.
7. **A Unity capture script** (1080p and 1440p).
8. **A PixelLab spend ledger.**
9. **A live handoff board.**

### Decisions for Vincent

1. Create the five helper agent definitions now (merge-verifier, test-runner, ger-drafter, delivery-evidence, unity-runner)? They cost nothing until used.
2. Go for a Codex "do" job to build the art-review toolkit?
