# Cleanup Agent handover — from the Pipeline Maintainer, 2026-09-18

Written for the Documentation Agent, who is building the role's guide and launch prompt. This is
only what I hold: what was done, how the judgements were computed, and what I deliberately left
alone. The role's lane, authority and reporting lines are the Documentation Agent's to write.

Companion document: `cleanup-agent-request-20260917.md` (the Game Agent's), which is the other
half of this role's inheritance.

---

## 1. What is already done — and it is smaller than the proposals

**A quarantine scheme exists and works.** `C:\NSC-History-20260918\`, dated in the name so the
folder's own age is visible without a reminder. **Review date 2026-10-09.**

| artifact | state |
|---|---|
| `MANIFEST.json` | 45 entries, valid UTF-8 **without BOM** |
| `MOVE-TO-HISTORY.ps1` | ran; moved 45 of the `C:\nsc*` root directories |
| `MOVE-STRAGGLERS.ps1` | written, dry-run tested, not needed in the end |
| `MOVE-NSCREV.ps1` | written, dry-run tested, **never applied** |
| `MOVE-NSC-FOLDERS.ps1` | written by a delegated job, **never applied, never reviewed by me** |
| `RESTORE.ps1` | takes a bare folder name, `-Reason` required, logs every restore |
| `RESTORES.md` | **created empty on 2026-09-18, deliberately** — see §5 |
| `README.md` | states Vincent's rule first, above everything else |

**Moved so far: the 45 `C:\nsc*` directories at the drive root, and nothing else.** `C:\` root now
holds only `NSC`, `nscrev` and the history folder.

**A 46th item is in there by a different route:** `nsc074-unity-validation-f7cb0f47`, 1,477 MB,
recovered from the Recycle Bin at Vincent's explicit request after he deleted it. It has its own
`PROVENANCE-*.md` because the manifest cannot describe it. Verified redundant before deletion:
HEAD `f7cb0f478` is merged to `main`, `main` is pushed, the parent clone is still on disk, nothing
uncommitted outside `Library/`. It is 95% Unity `Library` cache.

**Vincent ran every `-Apply`.** The one move I made myself was that Recycle Bin recovery, on his
instruction. That division — the agent writes the script, Vincent runs it — is the documented
procedure and it held all evening.

---

## 2. The guarded list, and how it is computed

**Two kinds of guard. Both matter, and the second is the one an inheriting agent will get wrong.**

### 2a. Named guards — a person said they need it

Derived by **asking all seven role agents before proposing the big pass**, not by inference. That
check found two things no scan would have:

- **`C:\nscrev\art-tools`** — 35 files, a flat copy with **no git history**. `Pipeline/ArtReview`
  greps **zero** on `main` (I verified). It is the only home of an accepted, Vincent-approved
  toolkit. Nothing about the folder looks special.
- **`C:\nscrev\ger-contract-revisions-20260916`** — holds the **only** copies of
  `new_task_commit.py`, `policy_entry_commit.py` and `verify_filter.py` (verified by `find`:
  exactly one copy of each under `C:\nscrev`). Quarantining it takes two of the GER Agent's three
  committers plus the filter verifier, right before the NSC-007 policy entries need them.

**The lesson to carry into the guide: asking the owners was worth more than all three delegated
inventory jobs.** Neither of those folders is distinguishable from junk by any automated rule.

Current named list, with who asked and why, is in the `$Keep` array at the top of
`MOVE-NSCREV.ps1` — each entry carries its reason as a comment. Summary:

- **tools and output:** `ger-tools`, `job-tools`, `claude-jobs`, `codex-jobs`, `viewer-tools`,
  `astra`, `session-tools`, `art-tools`, `reports`
- **finished or live work:** `decomp-snapshot`, `mixed-provider-env`, `mixed-provider-verify`,
  `ci-134-fix`, `fixrepo`, `ci-fix-executioncrew-coverage`, `ger-contract-revisions-20260916`,
  `ger-tools-dev`, `branch-verify`, `review-tmp`, `release-pages`, `release-webgl`,
  `viewer-step1-fix`, `viewer-step1-tmp`, `viewer-stage-detail`, `viewer-fix`

**`reports` deserves a special note:** it holds **uncommitted deliverables**, not just reports —
28 fireball sprites and 12 enemy death looks staged under `reports\art-director\`, whose `sha256`
values are pinned by committed contracts. If that guard is ever narrowed, those exact bytes are
unrecoverable, and they must be copied verbatim rather than re-exported.

### 2b. Computed guards — evaluated at run time, per directory

`MOVE-NSCREV.ps1` classifies **at run time rather than from a stored inventory**, so there is no
gap between what a scan saw and what is on disk. A directory is KEPT if **any** of these holds:

| condition | why |
|---|---|
| on the named list | a person said so |
| `.git` is a **file** → registered worktree | see §3, this is the dangerous one |
| `git status --porcelain` non-empty, excluding `Library/Temp/obj/Build` | uncommitted work |
| `git stash list` non-empty | stashed work |
| `git cat-file -e <HEAD>` fails **in canonical** | local-only commit, canonical has never seen it |
| `git merge-base --is-ancestor <HEAD> main` fails in canonical | tip not on main |
| newest file inside is within 3 days | recently active |
| git unreadable for any reason | **cannot verify → keep** |

**Two implementation traps the next agent must not re-introduce:**

1. **Exclude `\.git\` from the recency check.** `git status` and `git rev-parse` rewrite
   `.git\index`, so *any* inventory pass makes every clone look "modified today". My first dry
   run kept 142 directories on timestamps my own scanning had created. Judging recency on `.git`
   files measures the scan, not anyone's work.
2. **Set `$ErrorActionPreference = 'Continue'` around native git and check `$LASTEXITCODE`.**
   Under `Stop`, git writing to stderr (missing object, broken worktree, not-a-repo) becomes a
   terminating `NativeCommandError` and kills the whole run. Three separate crashes came from this.

Also: `Set-Content -Encoding utf8` on Windows PowerShell 5.1 **emits a BOM**, which makes
`MANIFEST.json` unreadable to python and jq (PowerShell's own `ConvertFrom-Json` tolerates it, so
it hides). Write with
`[System.IO.File]::WriteAllText($p, $json, (New-Object System.Text.UTF8Encoding $false))`.

---

## 3. `C:\NSC\_worktrees` — the explicit answer

**Do not move a registered worktree as a folder. Ever.** This is the one case where the
quarantine's reversibility guarantee does not hold: restoring the directory does **not** restore
the state.

Measured in canonical (`git worktree list`):

| | |
|---|---|
| registered worktrees total | **138** |
| under `C:\NSC\_worktrees` | **79** |
| pointing into `C:\nscrev` | 4 |
| directories in `C:\nscrev` whose `.git` is a file | **48** |

That last figure was reached independently of the Game Agent's scan and matches their count of 48
exactly.

**What breaks:** moving the directory leaves the parent's `.git\worktrees\<name>` pointing at a
dead path, **and** git still believes that worktree's branch is checked out — so the branch cannot
be checked out anywhere until `git worktree prune`. Doing ~130 by hand with no prune would lock
~130 branches.

**Correct handling:** `git worktree move` or `git worktree remove`, or a folder move followed by
`git worktree prune` in the parent. Never a bare `Move-Item`/`robocopy`.

**Two further complications the inheriting agent will hit:**

- **Worktree parents cross the directory boundary.** `C:\nscrev\wt-base-sessions` is a worktree of
  `C:\NSC\ClaudeProviderSessions\NoSafeCircle`. So the `C:\NSC` and `C:\nscrev` passes are **not
  independent** — moving one can break the other.
- **`C:\NSC\_worktrees` was never on my guarded list, and it is where the large reclaim lives.**
  It is excluded from everything I wrote only because I never ran the `C:\NSC` pass at all.
  Guard it explicitly before anything touches `C:\NSC`.

`MOVE-NSCREV.ps1` now detects worktrees by the `.git`-is-a-file test and always keeps them.
`MOVE-NSC-FOLDERS.ps1`, written by a delegated job, **has not been checked for this** — see §5.

---

## 4. The proposed passes, and how the candidates were counted

**Neither has been applied. Both are proposals.**

| pass | counted | verdict |
|---|---|---|
| `C:\nscrev` | 201 top-level dirs, 15 files | **KEEP 152 / MOVE 48**, dry-run verified by me |
| `C:\NSC` | 788 top-level dirs, 300 files | **move 416 (~100 GB) / keep 41 / ask 330**, produced by a delegated job, **not verified by me** |

**Depth: my own scans are depth-1** — top-level children of `C:\nscrev` and `C:\` only. They do
not descend, so nothing inside `C:\NSC\_worktrees` was ever enumerated by me. I cannot vouch for
the depth of the delegated `C:\NSC` job; treat its 416/41/330 as unverified until re-derived.

**Clone-only work, from the Game Agent's independent scan
(`C:\nscrev\reports\cleanup-safety-scan-20260918.txt`, tool `cleanup-safety-scan.py`):** **81
branches across 32 clones are commits canonical has never seen.** They have already fetched the
*active* merge candidates into canonical as refs, so roughly 13 no longer depend on any clone.
**The remaining ~60 are historical throughput and gauntlet experiments and are undecided** — that
is squarely the new agent's first real judgement call, and it is Vincent's call whether they are
preserved as refs or allowed to lapse.

---

## 5. What I deliberately did not do, and why

This section matters more than the inventory.

1. **I never ran `-Apply` on `C:\NSC` or `C:\nscrev`.** Both scripts exist and are dry-run
   verified; neither has moved a byte.
2. **I never touched `C:\NSC\_worktrees`.** 132 entries, 79 registered worktrees, and the bulk of
   the reclaimable space. It needs worktree-aware handling, not a folder move.
3. **I did not review `MOVE-NSC-FOLDERS.ps1`.** A delegated job wrote it and I never checked it
   against the worktree rule in §3. **Treat it as unverified.** Two of three delegated inventory
   jobs tonight also failed by spawning a background scan and exiting 0 with no deliverable — so
   verify any artifact a job claims to have produced, and never read exit 0 as success.
4. **I did not act on the 330 "ask" directories.** They are a decision queue, not a backlog.
5. **I deleted nothing.** The only deletion tonight was Vincent's own, and I recovered it from the
   Recycle Bin when he asked.
6. **I did not move the tool folders**, though the extraction is approved in principle. Moving
   them breaks **36 doc files and 11 agent definitions** that cite `C:\nscrev\<tool>` paths, so it
   needs a coordinated doc sweep, and a directory junction at each old path during the transition
   so live agents do not break mid-move.
7. **I created `RESTORES.md` empty, with a header and the review date**, on the Documentation
   Agent's point that an *absent* file cannot be distinguished from a lost one — so emptiness on
   2026-10-09 is evidence rather than ambiguity.

---

## 6. What I would tell the new agent

**First, before anything:**

1. **Re-run the Game Agent's safety scan** (`C:\nscrev\reports\cleanup-safety-scan.py`, read-only,
   under a minute) before *every* batch. State goes stale fast here.
2. **Ask the owners before proposing a pass.** Seven sessions, one short message each, and make
   "no reply" mean "nothing of mine is there". It found two near-misses tonight that no rule would
   have caught.
3. **Start with `C:\NSC\_worktrees`**, because it holds the large reclaim and is the only part
   that is genuinely irreversible if done wrong. Get worktree retirement right and the rest is
   mechanical.

**Never:**

- move a registered worktree as a folder;
- delete an `NSC-###` branch (runbook rule 11);
- move `C:\nscrev\reports` or narrow its guard — uncommitted art deliverables with contract-pinned
  `sha256` values live there;
- run an `-Apply` yourself. **You write the script; Vincent runs it.** That is the procedure
  Vincent set when he declined this role the first time, and it is what kept tonight recoverable.

**One judgement to inherit rather than re-litigate:** the quarantine is deliberately conservative,
and "cannot verify" resolves to *keep*. A folder kept wrongly costs disk. A folder moved wrongly
costs someone's evening — or, for a registered worktree, a locked branch nobody can explain.

---

## 7. Open items I am handing over

- The **~60 undecided clone-only branches** (§4).
- The **330 "ask" directories** from the `C:\NSC` inventory (§4).
- **Verification of `MOVE-NSC-FOLDERS.ps1`** against the worktree rule (§5.3).
- The **tools extraction** and its 36-doc / 11-agent-definition sweep (§5.6) — approved by Vincent
  in principle tonight; the doc sweep is the Documentation Agent's, the move is unassigned.
- **`C:\NSC-History-20260918` review on 2026-10-09**: if `RESTORES.md` is still empty, the folder
  can be deleted wholesale.
