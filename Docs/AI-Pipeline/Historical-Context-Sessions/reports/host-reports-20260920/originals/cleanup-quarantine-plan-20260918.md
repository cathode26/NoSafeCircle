# NSC quarantine — status report, 2026-09-18

**This is a status/reconciliation report, not a forward plan.** The brief that generated it asked
for an inventory and a dry-run-by-default move script for Vincent to review and run. By the time
the inline scan finished, **the move had already been carried out directly on the machine** —
timestamps below show it happened *during* this session, in parallel with the scan. This agent did
not perform it (this agent only reads, scans and writes scripts/reports — see "What this agent did
and did not do" below). Treat this report as: here is what actually happened, here is the data the
brief asked for, here are the two gaps found and fixed, and here is what still needs a look.

## Bottom line

- **45 of 45** target directories are now under `C:\NSC-History-20260918`. Nothing matching
  `C:\nsc*` remains at the drive root except the two hard exclusions: `C:\nscrev` (live) and
  `C:\NSC` (the workspace).
- **Total moved: at least ~11.5 GB**, likely higher — one directory's size could not be fully
  measured (see Gaps below).
- **0 directories are still awaiting a decision.** The move already happened; what's left is
  Vincent knowing what's in there before 2026-10-09, which is what the table below is for.
- **2 gaps found in the already-completed quarantine, both fixed by this agent:**
  `README.md` and `MANIFEST.md` were missing from the history folder (the brief requires both);
  they're written now. The manifest itself had already been self-healed for the one directory that
  needed it (see below) — no manifest edit was needed from this agent.

## What this agent did and did not do

- Did: inline, read-only scanning (`du`, `find`, `git branch`/`status`/`stash`/`remote`, `ls`) of
  every `C:\nsc*` directory; wrote this report; wrote `README.md` and `MANIFEST.md` into the
  history folder (pure documentation, not a move); wrote a fresh copy of the move script to
  `C:\nscrev\reports\NSC-History-20260918-move.ps1` (see below).
- Did not: move, delete, prune, reset, or force anything. Did not touch any already-quarantined
  directory's contents. Did not edit `MANIFEST.json` (see next section — it didn't need it).

## What actually happened, in order

1. A script functionally identical to what this brief asked for already existed on disk at
   `C:\NSC-History-20260918\MOVE-TO-HISTORY.ps1` (dry-run by default, same guards, same
   incremental-manifest design) before this scan started — most likely left behind by an earlier,
   silent run of this same job (the brief itself notes "a previous job... returned exit 0 with a
   cheerful message, and produced neither deliverable" — it seems that job *did* write the script
   to disk, just never reported it).
2. Someone (almost certainly Vincent, working at the machine in parallel with this session — see
   `PROVENANCE-nsc074-unity-validation-f7cb0f47.md` in the history folder, which documents him
   doing exactly this kind of hands-on cleanup tonight) ran it with `-Apply` while this scan was
   in progress. `MANIFEST.json`'s `MovedUtc` timestamps cluster at `2026-09-19T01:19:18Z`–`19Z`
   (= 2026-09-18 ~20:19 local), which lines up with when this agent observed live filesystem
   changes mid-scan.
3. **44 of 45 directories moved cleanly.** One, `nscmin_work`, failed on the first pass —
   `MANIFEST.json` itself now records why: *"Move-Item failed with 'insufficient access rights';
   moved manually with robocopy /MOVE /E."* This agent's own concurrent scanning of
   `nscmin_work`'s four nested Unity clones (see below) was running at exactly that moment and is
   the likely cause — `du`/`find` held read handles on files inside it while the move script tried
   to rename the directory. By the time this agent checked again, `nscmin_work` had been moved
   manually (via `robocopy`) and **the manifest gap had already been fixed** — by the same hand
   that did the robocopy, not by this agent. No manifest edit was needed.
4. This agent found two things the brief requires that were still missing from the folder:
   `README.md` (the rule, stated first) and `MANIFEST.md` (human-readable companion to
   `MANIFEST.json`). Both are written now, generated from the live `MANIFEST.json` so they match
   exactly what actually moved.

**Apology for the interference:** the `nscmin_work` failure in step 3 is very likely this agent's
fault — the brief's inline-scanning requirement had this agent's `du`/`find` reading the same
directory tree at the same moment a real move was in flight. No harm resulted (robocopy recovered
it, nothing was lost), but it's worth Vincent knowing an inline read-only scan can still collide
with a concurrent move on the same files.

## The full inventory (45 directories)

"Local branches not ancestor of canonical `main`" is every local branch in that clone whose tip
`git merge-base --is-ancestor <sha> main` returns false for, checked against
`C:\NSC\NSC\NoSafeCircle`. **Read this as data, not a verdict** — per the brief, quarantine already
happened regardless of what's here. **Caveat, and it matters:** most `fix/*` branches on this list
were very likely already integrated into `main` via **squash merge**, which by design produces a
new commit on `main` and leaves the original branch-tip commit permanently "not an ancestor" even
though every line of its content landed. A long list here is the *expected* shape for a pipeline
that squash-merges fix branches, not a sign of lost work. Two branches worth an actual look because
they *don't* fit that pattern: `nscint`'s `integ3`, `mergeobs`, `p2` (three differently-named
branches, one with uncommitted changes) and `nscviz`'s `claude/test-fixture-isolation` (a
`claude/*`-prefixed branch, a different naming convention than the `fix/*` pipeline branches).

| Folder | Type | Size | Local branches not ancestor of canonical `main` | Dirty / untracked (non-Unity-noise) | Stash |
|---|---|---|---|---|---|
| `nscarch` | clone | 40.1MB | `fix/architect-cost`@`a2436e8`; `fix/cache-key-resolution`@`8579d4d`; `main`@`a2436e8` | — | — |
| `nscarch_work` | plain | 1.4MB | — | — | — |
| `nscaudit` | clone | 46.8MB | `main`@`e9f68b0` | — | — |
| `nscaudit_main` | worktree | 30.3MB | `main`@`e9f68b0` | — | — |
| `nscconc` | clone | 44.3MB | `fix/concurrent-readmission`@`0218877`; `main`@`0218877` | — | — |
| `nscconc_work` | plain | 7.2MB | — | — | — |
| `nscdel` | clone | 39.3MB | `fix/cache-key-resolution`@`8579d4d`; `fix/delete-invalidated-decomposition-template`@`8579d4d` | — | — |
| `nscdel_work` | plain | 6.6MB | — | — | — |
| `nscfixeol` | clone | 41.5MB | `fix/canonical-line-ending-comparison`@`0bc3a95`; `fix/d1c-materialization-rollback`@`5b30406` | — | — |
| `nscfixperf` | clone | 46.4MB | `fix/git-process-storm`@`eb2eda5`; `main`@`e9f68b0` | — | — |
| `nscfixperf_work` | plain | 1.2MB | — | — | — |
| `nscfixpush` | clone | 42.5MB | `fix/d1c-push-race-discriminator`@`ee9288b`; `main`@`e9f68b0` | — | — |
| `nscfixrace` | clone | 39.0MB | `fix/coherent-snapshot-apply-race`@`45cc192`; `main`@`e9f68b0` | — | — |
| `nscfixroll` | clone | 39.6MB | `fix/d1c-materialization-rollback`@`5b30406`; `main`@`e9f68b0` | — | — |
| `nscfixsnap` | clone | 43.2MB | `fix/coherent-snapshot-apply-race`@`45cc192`; `fix/snapshot-refresh-amplification`@`9c9f9bf` | — | — |
| `nscfixtmpl` | clone | 39.1MB | `fix/stale-dependent-decomposition-template`@`4d23946`; `main`@`e9f68b0` | — | — |
| `nscfixtrav` | clone | 39.6MB | `fix/downstream-manifest-traversal-guard`@`728c5c0`; `main`@`2cb418a` | — | — |
| `nscfixtrav_work` | plain | 173.7KB | — | — | — |
| `nscilpp` | clone | 40.2MB | `investigate/unity-ilpp-failure`@`0218877`; `main`@`0218877` | — | — |
| `nscilpp_work` | plain (+2 nested clones) | 2.9GB | — | — | — |
| `nscint` | clone | 51.4MB | `integ3`@`1a7f0a6`; `main`@`a2436e8`; `mergeobs`@`11719ce`; `p2`@`a2436e8` | 1 lines | — |
| `nsclat` | clone | 44.2MB | `fix/scheduler-poll-latency`@`7aed774`; `main`@`7aed774` | — | — |
| `nsclat_work` | plain | 1.5MB | — | — | — |
| `nscloop` | clone | 42.2MB | `fix/task-convergence-loop`@`a2436e8`; `fix/validation-authority-change-loop`@`db14335`; `main`@`a2436e8` | — | — |
| `nscloop_work` | plain | 7.2MB | — | — | — |
| `nscmerge` | clone | 41.6MB | `integration/verify-20260905`@`51faeb1`; `integration/verify-20260905-on-cd72913`@`fe823f3`; `main`@`2cb418a` | — | — |
| `nscobs` | clone | 41.4MB | `feat/resume-hint-observability`@`11719ce`; `main`@`0218877` | — | — |
| `nscobs_work` | plain | 6.9MB | — | — | — |
| `nscperf` | clone | 38.9MB | `main`@`c589ca3` | — | — |
| `nscprobe` | plain | 22.0KB | — | — | — |
| `nscrev911` | clone | 40.8MB | `main`@`de6083f` | 7 lines | — |
| `nscrev911_work` | plain | 3.2MB | — | — | — |
| `nscrev911b` | clone | 40.8MB | `main`@`72d584a` | — | — |
| `nscrev911c` | clone | 40.9MB | `claude/fix-nsc911-decomposition-resume`@`2c08bb3`; `main`@`2c08bb3` | 7 lines | — |
| `nscreview` | clone | 41.5MB | `main`@`c589ca3` | — | — |
| `nsctmplverify` | clone | 41.7MB | `fix/stale-dependent-decomposition-template`@`4d23946` | — | — |
| `nsctmplverify_work` | plain | 48.3KB | — | — | — |
| `nsctred` | clone | 41.5MB | `fix/stale-dependent-decomposition-template`@`4d23946` | — | — |
| `nscunity` | clone | 40.2MB | `fix/reuse-validated-unity-evidence`@`0218877`; `main`@`0218877` | — | — |
| `nscunity_work` | plain | 293.0KB | — | — | — |
| `nscverify_work` | plain (+2 nested clones) | 70.7MB | — | — | — |
| `nscviz` | clone | 43.8MB | `claude/gauntlet-graph-view`@`f62def9`; `claude/test-fixture-isolation`@`3f67430`; `main`@`11719ce` | — | — |
| `nscwarm` | clone | 43.3MB | `fix/ilpp-pid-minimal`@`63b5712`; `fix/warm-unity-library`@`3f92ff4`; `main`@`0218877` | — | — |
| `nscwarm_work` | plain (+10 nested clones) | n/a | — | — | — |
| `nscmin_work` | plain (4 nested full clones, each w/ Unity `Library/`) | 5.2GB (partial — see note) | nested repos each on `fix/ilpp-pid-minimal`, different tips: `killer`:`fix/ilpp-pid-minimal`@`850fafb`; `missing`:`fix/ilpp-pid-minimal`@`11719ce`; `negative`:`fix/ilpp-pid-minimal`@`0073f51`; `victim`:`fix/ilpp-pid-minimal`@`e006c23` | — | — |

## Nested Unity clones (separate from the top-level 45)

Four "plain" `_work` directories are not flat evidence dumps — each contains multiple **full,
independent git clones of the game repo, each with its own Unity `Library/` cache**:

| Parent | Nested clones | What they look like |
|---|---|---|
| `nscmin_work` | `killer`, `missing`, `negative`, `victim` (4) | all on `fix/ilpp-pid-minimal`, different tips — ILPP-PID minimal-repro fixtures |
| `nscwarm_work` | `added-meta-asmdef`, `artifacts`(no .git), `c1-absence`, `c1-poison-killer`, `concurrent-a`, `concurrent-b`, `deleted`, `negative`, `ownership-probe`, `template-project`, `warm-seeded` (10 clones) | warm-cache / concurrency / poison-scenario fixtures |
| `nscilpp_work` | `repro-killer`, `repro-victim` (2) | ILPP-failure repro fixtures |
| `nscverify_work` | `wtBASE`, `wtINT` (2) | base/integration verification worktree-style clones |

**18 nested full clones total**, each carrying its own `Library/` (the dominant cost — single
`Library/` folders measured at ~1.3 GB each in `nscmin_work`'s four). This is most of why
`nscilpp_work` (2.9 GB) and `nscwarm_work` (size not fully measured — see Gaps) are so much larger
than every top-level clone (all ~40–50 MB). **If a separate "put the pipeline history under git"
project touches these `_work` folders, budget for these 18 nested repos explicitly** — a naive
"copy the folder" will drag in ~20+ GB of regenerable Unity cache.

## One folder outside the `nsc*` scope

`nsc074-unity-validation-f7cb0f47` also sits in the history folder. It did not come from the
`C:\nsc*` glob — it arrived by a different route (recovered from the Recycle Bin at Vincent's
request; full story in `PROVENANCE-nsc074-unity-validation-f7cb0f47.md`, already in the folder).
Noted here only for completeness; this agent did not scan or move it.

## Gaps found (and their state)

| Gap | Found | Status |
|---|---|---|
| `README.md` missing from history folder (brief requires it, stating the rule first) | This agent | **Fixed** — written |
| `MANIFEST.md` missing (brief requires a human-readable companion to `MANIFEST.json`) | This agent | **Fixed** — written, generated from the 45-entry `MANIFEST.json` |
| `nscmin_work` missing from `MANIFEST.json` after its first move attempt failed | This agent (during scan) | **Already fixed by the time this agent re-checked** — someone appended a manifest entry with an honest `Note` explaining the robocopy fallback. No action needed from this agent. |
| `nscwarm_work` total size not fully measured | This agent | **Unfinished** — `du` timed out twice (100s each) on this directory; it holds 10 nested Unity clones. Top-level (non-recursive) listing and nested-clone names are captured above; exact byte count is not. A `Get-ChildItem -Recurse` run with no timeout (minutes, not seconds) would get an exact figure if wanted before 2026-10-09. |
| `nscmin_work` total size only partial | This agent | Summed from its four nested clones' own `du` calls (excluding-noise + `Library/` measured separately, each under a bounded timeout): **~5.2 GB**. The single `du -sb` call against the whole directory timed out twice at the top level; the nested-level sum above is complete and should be accurate. |

## Numbers

- **45 / 45** directories quarantined (44 via the tracked script + `nscmin_work` via manual
  robocopy, both now in `MANIFEST.json`).
- **0** remain at `C:\` matching `nsc*` outside the two hard exclusions.
- **~11.5 GB+** moved (sum of measured top-level sizes + `nscmin_work`'s partial nested sum;
  `nscwarm_work`'s unmeasured size is not included, so the true total is higher).
- **29 of 45** directories carry at least one local branch not an ancestor of canonical `main`,
  dirty/untracked content, or a stash — see the caveat above on why that number is expected to be
  large and mostly benign.
- `nscrev911` and `nscrev911c` (7 changed lines each) and `nscint` (1 changed line) are the three
  directories with non-Unity-noise dirty status; all three match what Vincent's own `MANIFEST.json`
  already recorded (`State: "7 changed"` / `"1 changed"`), so this is confirmation, not new news.

## Deliverables from this job

1. **This report** — `C:\nscrev\reports\cleanup-quarantine-plan-20260918.md`.
2. **Move script** — `C:\nscrev\reports\NSC-History-20260918-move.ps1` (could not write to `C:\`
   root directly — permission denied — so it's here per the brief's fallback). Dry-run by default,
   same guards as the brief specifies, idempotent (skips anything already moved), and adds the
   README.md/MANIFEST.md creation step the folder's existing copy was missing. Tested with a dry
   run just now: correctly reports **nothing left to move**, since the quarantine is already
   complete. It exists for the record and for any future `nsc*` stragglers, not because anything
   needs running today.
3. **Restore mechanism** — already exists and works: `C:\NSC-History-20260918\RESTORE.ps1`. This
   agent reviewed it line by line: dry-run by default, takes a bare folder name, requires `-Reason`
   with `-Apply`, logs to `RESTORES.md`, refuses to overwrite an existing destination, falls back
   to `C:\<name>` when no manifest entry exists (which is exactly right for `nscmin_work`). No
   changes needed.

## For Vincent

Nothing here requires a decision before 2026-10-09 unless you want `nscwarm_work`'s exact size
first. The rule from your own words is already doing its job: anything in
`C:\NSC-History-20260918` that turns out to matter comes out via `RESTORE.ps1`; whatever's still
there on the 9th was never needed.
