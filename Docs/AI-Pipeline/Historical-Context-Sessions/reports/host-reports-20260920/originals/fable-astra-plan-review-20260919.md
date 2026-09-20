# Fable adversarial review - Astra cleanup / durability / undo plan and team brief

**VERDICT: FIX FIRST.**
**Can the first milestone start today as written? No.** Preparation steps 1-3 (schema, candidate choice, dispatch cards) can start today. The milestone itself (capture -> publication -> independent restore -> reviewed dry-run retirement package) cannot complete with what exists on this machine: every tool in that chain is unwritten, the three repositories do not exist, and no document names a candidate. Two exposures below are on a clock that does not wait for the plan.

Reviewer: Fable 5.1 (pipeline-reviewer role), 2026-09-19, read-only. This is a plan review, not a fix review: there is no clone, range or test suite, so those parts of my usual format do not apply. Blocking findings: **3**. Major: **6**. Minor/opinion: **5**.

The architecture is sound and I am not asking for a redesign. Four repositories, narrow capture roots, nothing tracked through a junction, manifest published last, Vincent alone deletes, undo kept off the critical path of the cleanup - all correct. The defects are in what the plan trusts, what it never looked at on disk, and its clock.

How to read the evidence tags: **[verified]** = I ran it on this machine today. **[documented]** = known tool behaviour I did not reproduce here. **[reasoned]** = argument only.

---

## Blocking

### B1. The capture can be verified only against itself, so an enumeration blind spot is invisible [verified mechanism, live example]

All the independence in the plan is on the restore side: a different helper restores from the remote and compares against the manifest. Nothing says who produces the source-side truth. If the same code enumerates the source, copies it and writes the manifest, then anything that code cannot see is missing from the source list, the capture, the manifest and the restore alike, and every comparison is green.

This happened to me during this review. My first scan of seven capture sources reported `files=0, errors=0`, exit 0, for every root - "no nested repositories, no long paths, no large files". All seven roots exist. A malformed long-path prefix made `os.walk` raise on every root and my own error handler discarded the exception. I caught it only because I held an independent expectation (Test-Path said the roots exist; the baseline says reports has 3936 files). I discarded that run entirely and none of its numbers appear below. The corrected run fails hard on any zero count and prints walk errors; it matched the baseline (tools 193 vs 192, agents 14 vs 14, reports 3976 vs 3936 two days ago). The plan has no equivalent independent expectation, and the history of this project (a recency check that measured its own writes; 62 green tests on a tool that refused every command) says it needs one.

Concrete blind spots that exist on this disk today:

| Blind spot | On disk [verified] | Effect |
|---|---|---|
| A `.gitignore` inside the payload takes effect in the capture repo | `C:\NSC\tools\.gitignore` ignores `*.log`, `/session/digests/`, `/viewer/audit_raw.json`. Two digest files exist now under `tools\session\digests\`. | Copy tools into `nsc-fleet`, `git add -A`, exit 0, push succeeds. Session digests - a mandatory family in plan section 5 - are silently not committed. The design notices `*.log` (defect 6) but not that the ignore file travels with the copy. |
| Nested `.gitattributes` beat the root `* -text` | 183 git special files under `Downloads\NoSafeCircleOutput`, including nested `.gitattributes` | [documented] A deeper `.gitattributes` has higher precedence than the root one. Byte preservation is lost for those subtrees. Not reproduced: it needs a repository and I was told to create none. |
| Nested `.git` directories | 334 under `Downloads\NoSafeCircleOutput` | [documented] `git add` records a gitlink or skips the directory. The content is absent from the commit; the push is green. |
| Empty directories and zero-byte files | 8 empty dirs + 14 zero-byte files in reports; 348 empty dirs in NoSafeCircleOutput | Git cannot store an empty directory. The fingerprint requires a "complete directory-entry inventory", so a git restore can never equal the source. Either every such candidate is HOLD forever, or the tool quietly stops comparing directories. |
| Paths of 260+ characters | 326 under NoSafeCircleOutput (max 307). 0 in tools, agent-state, reports, control, nsc-astra, agents. | This machine has Windows PowerShell 5.1 only (`pwsh` is not installed). Python needed the extended-length path prefix. Untested which cmdlets the capture will use. |

**Failure sequence:** the PM adapter enumerates with one method -> copies -> hashes what it copied -> writes manifest -> Release publishes -> H14 restores and compares to that manifest: 100 percent match -> candidate retired -> the digests / nested-repo contents / long-path files were never in the capture.

**Fix (small):** (1) the source-side inventory is produced by a second enumerator in a different implementation (for example Python `os.scandir` with the long-path prefix versus `robocopy /L /E /XJ /NJH`), by someone other than the capture author, and the two must reconcile on count and bytes per source row before capture is accepted; (2) every source row carries an expected-count floor from the existing baseline, and zero or a large drop is a failure, never a result; (3) the restore is compared to the source inventory, not to `git ls-files`; (4) payload `.gitignore`/`.gitattributes`/`.git` are neutralised on the way in (store under a renamed path with a reassembly map, or add with `--force` and check `git status --ignored` is empty) and that check is a fixture; (5) empty directories are recorded in the manifest and recreated by the restore tool.

### B2. 1.6 GB of session transcripts are in no source family and are on a 30-day deletion timer [verified size and config; documented default]

`%USERPROFILE%\.claude\projects` holds **3180 files, 1628 MB** for NSC, nscrev and NoSafeCircleOutput paths - the full record of what every agent session did and decided. That is more than reports (129 MB) and control (60 MB) combined. The families in the plan list agents, memory, skills, settings and "session digests". The only mention of transcripts in all six documents is one word in the assumptions of the design (line 285); no row, owner or path.

`cleanupPeriodDays` is set in none of the settings files I checked (user, `C:\NSC\.claude`, `C:\nscrev\.claude`, managed). [documented] The Claude Code default is 30 days, applied at startup. The oldest file is dated 2026-08-31, so removal starts around **2026-09-30** - inside the horizon of the plan itself, and independent of whether the plan runs. I did not test the deletion; treat the date as the documented default, and check it.

One file is 82 MB: over the 40 MiB segment rule in the plan, under the GitHub 100 MiB block. None exceeds 100 MiB. A count-only pattern scan of the 1.2 GB `C--NSC` and `C--nscrev` sets found no credible secret (eight key-shaped strings were all inside longer words; one URL credential was a placeholder). That is a pattern scan, not proof.

**Fix:** a decision for Vincent this week, not a tool: set `cleanupPeriodDays` high in user settings, and add the transcript directories as a mandatory family with Documentation as owner. Note that transcript folders are keyed by working directory, so retiring a worktree does not retire its transcript.

### B3. The first milestone assumes a toolchain that does not exist [verified]

| Needed for the milestone | State on this machine |
|---|---|
| git 2.45.1, git-lfs, gh (logged in as `cathode26`, scopes `repo`, `workflow`, `gist`, `read:org`), Python 3.13.1, robocopy, tar, Docker, `run_job.py` | Present |
| File capture adapter, full fingerprint tool, history exporter with immutable ref map, provisioning script, remote-only restore verifier, deletion runner, fixtures | **None exist.** A glob of `C:\NSC\tools` for capture, fingerprint, restore, manifest, retire, backup, collector, slot returns nothing; the same glob form finds `run_job.py` and `main_write.py`, so the negative is real. |
| `C:\NSC-Repositories`, `C:\NSC-Backup-Staging`, `cleanup-runs`, `C:\nscrev\work` | Do not exist |
| Remotes `nsc-fleet`, `nsc-evidence`, `nsc-history` | Do not exist on the account (26 repos listed; none match) |
| Workspace registry | README only. No `inbox`, no `index.md`. Zero receipts. |
| Heavy-operation slot ledger | Does not exist; `run_job.py` has no slot, semaphore or concurrency code |
| Second off-machine copy (P16) | **No tool.** rclone, aws, az, gcloud, restic are absent. A OneDrive client is running, but the design itself requires download through the service to prove upload, and nothing installed can do that unattended. |
| PowerShell 7 | Absent. Every `.ps1` package runs on 5.1. |
| 7z, zstd | Absent (only matters for later log segments; tar and Python lzma exist) |
| A named candidate | None in any of the six documents |

The plan is honest that tooling is "to build". What it does not do is count it: six tools, seven Windows fixture classes, two fresh reviews, one provisioning run by Vincent, and at least five visits by Vincent across three sessions, before the first byte is captured. See M6.

---

## Major

### M1. The disposal rule has gaps that only appear under concurrency or a half-finished item

(a) **Redundancy can be circular** [reasoned]. "A clean redundant copy may proceed when ... its independently retained counterpart proves redundancy." Clone X and clone Y both hold `exp/foo`, which canonical never saw. H05 marks X redundant citing Y; H07 marks Y redundant citing X. The "one job owns each shared store" rule does not apply - they are separate stores. Both retire in different batches. What survives is one GitHub copy with no second copy, which is exactly what the unique-original rule was written to prevent. Fix: a counterpart cited as proof of redundancy is placed under a named hold until the citing item is retired, and a held item cannot itself be a candidate.

(b) **A half-deleted item has no legal state** [reasoned, Windows specifics verified]. Directory deletion on Windows is not atomic; it stops on a locked file. The plan says both "partial completion is recoverable and rerunnable" and "any mismatch stops the batch". On rerun, the fingerprint of the half-deleted item cannot match, so it stops; it is now also "dirty", so the no-force rule holds it for good. The per-item intent record exists in the plan but nothing says the rerun accepts "a strict subset of the sealed fingerprint under an open intent" as the one allowed mismatch. Without that sentence the runner either wedges or someone adds a skip.

(c) **No grace period removes the only defence against a wrong verifier** [reasoned]. Conditions (b) and (d) are judged by tools that do not exist yet, in a project whose recurring failure is a green check that checked nothing. A grace period was never about age; it is the window in which a verifier bug gets noticed before it is irreversible. Disk pressure is not a reason to skip it: C: has **2491 GB free** and F: **2309 GB free** [verified]. Suggested: for the first batches only, the runner copies each item to a tombstone on F: (`robocopy /E /XJ`, junctions excluded) before deleting, with a purge tied to a second, later restore drill rather than to a date. That keeps C: clean, keeps the logic of the rule, and costs minutes.

(d) **Condition (a) cannot be checked, only asserted** [reasoned]. See M2.

### M2. Holds are acknowledgements from sessions that are stopped, and they bind nothing that is not a session

The brief requires "current path-specific acknowledgements" kept through final drain, capture, publication, restore and execution - hours. The plan also says stopped sessions stay stopped until Vincent restarts them. A stopped session cannot acknowledge, and a running one cannot bind its detached helper job, its successor after a context reset, a Docker container, the Unity editor, or Vincent working by hand. Astra finding 3 asked for this to be proved; the revision restates the requirement and adds "prove Windows writer-race behaviour". A fixture proves the runner notices a change it is shown. It does not create exclusion.

**Failure sequence:** full fingerprint recheck of a clone passes at T (it takes minutes on a large tree) -> at T+30 s a helper launched an hour earlier writes its result log into the candidate -> deletion at T+2 min removes the only copy of that log. Every gate was green.

**Fix:** state plainly that the final check is a race the plan narrows but does not close, and narrow it mechanically: recheck per item immediately before that item, not per batch; probe for open handles at that moment; and keep the M1(c) tombstone so that a lost race is recoverable. Nothing here needs the fencing from the undo work.

### M3. "At most two heavy operations" with three owners who each believe they hold a slot [verified: no mechanism]

The ledger has a single writer, Cleanup, which is a session that may be stopped or mid-turn. PM, Release and Cleanup each read "one slot in use", each start. It is check-then-act across agents that talk by message. Alternatively the ledger writer is unavailable, and owners either wait indefinitely or grant themselves a slot.

Consequence, stated honestly: not data loss, and not disk exhaustion (2.4 TB free). It corrupts step 8. The slice exists to measure byte rates and publish a forecast; three overlapping hash/clone/upload jobs produce rates that describe contention, and the forecast built on them is wrong. It also turns timeouts into routine, and a timed-out capture is the input to the "exit nonzero but a file exists" judgement the plan warns about.

**Fix (about twenty lines):** two slot files created with exclusive-create (`open(path, "x")`), holding owner, PID, process start time and operation; a slot whose PID is dead is reported, not silently reclaimed. No scheduler needed.

### M4. The deletion runner will run on PowerShell 5.1, next to six junctions into live tools [verified layout; behaviour not reproduced]

All six junctions are at the top of `C:\nscrev` and all point into `C:\NSC\tools` (`art-tools`, `astra`, `ger-tools`, `job-tools`, `session-tools`, `viewer-tools`). `C:\NSC` has none at depth 1-2. `C:\nscrev` is a cleanup root.

[documented] The recursive forced form of the PowerShell `Remove-Item` cmdlet in Windows PowerShell 5.1 has a known defect of descending into a junction and deleting the contents of the target; it was fixed in PowerShell 6+. **I did not reproduce this.** My scratch-only test was refused by the deletion guard of my own sandbox (it misread `cmd /c` as a path), and I did not work around a guard to run a deletion. That test created nothing.

The preflight in the plan rejects reparse points, which covers the known six. It does not pin the engine or the primitive. **Fix:** the package states its required engine and refuses to run elsewhere; deletion is per entry and never descends a reparse point (Python 3.13 `shutil.rmtree` refuses junction traversal; or remove the junction entry itself first); and the reparse fixture must include "junction created inside the candidate after sealing", on 5.1, because that is the engine Vincent has.

### M5. "The game repo is safe" is true of `main` only, and the easy fix is closed [verified]

`main == origin/main == 2559514826e9` - confirmed. But in canonical, **72 of 155 local branches have commits reachable from no remote-tracking ref**, and there is 1 stash. `origin` (`cathode26/NoSafeCircle`) is **PUBLIC**, so "just push them" is a privacy decision, not a command. Their protection therefore waits for `nsc-history`, which waits for B3. The ten-line `git bundle create --all` step in the design would close this tonight; after six documents it has not been run. With F: available it need not even wait for a remote decision.

Good news from the same check: all 23 detached worktree HEADs in the canonical store have zero commits off every ref. The documents hold "three unique detached-head worktrees"; either those belong to another parent store or they have since gained refs. Recheck rather than trust either number.

Also [verified]: the canonical pack files carry 139-140 hard links each. Most local clones share pack bytes with canonical, so summed directory sizes overstate the landfill badly and reclaimed space per clone will be far below its apparent size. A forced removal clears the read-only attribute before deleting, and attributes are shared across hard links, so the runner will flip the canonical packs to writable. Harmless, but it will show up as an unexplained change in any fingerprint of canonical.

### M6. Timing: 4-8 hours is optimistic by roughly three times, and the fixtures are what will be cut [opinion, reasoned from counts]

B3 lists the work. The loop this project uses for a single pipeline fix is: failing-before and passing-after tests, a fresh reviewer, then Game merges when Vincent says so; and the modal first verdict is FIX FIRST - this plan drew one. Six tools through that loop, plus Vincent as a serial gate at kickoff, provisioning, publication word and execution, is two to four working days to a first deletion. The allowance is labelled "unmeasured", which is honest, but a number in a brief becomes a target. When it slips, the seven fixture classes are the only compressible item, and they are the entire defence.

**Suggestion:** drop the hours, or split the slice into two halves that do not block each other. Half A: bundle canonical and the named non-Git families to F: and one remote tonight (existing commands). Half B: prove the deletion runner on a candidate that is pure redundancy - a clean clone with zero unique refs and zero untracked or ignored files - which needs a fingerprint and a redundancy proof but none of the three repositories.

---

## Minor and opinion

- **m1. `Downloads\NoSafeCircleOutput` is 27,836 files, 894 MB, 334 nested repositories** [verified]. The plan names one summary file in it. About 105 transcript folders point into it. It sits in a Downloads folder. Storage Sense is enabled with temp-file cleanup on [verified]; its Downloads rule is not configured and its cadence is "low disk space", so it is not firing today. Classify the directory; do not leave it as one named file.
- **m2. Review briefs and helper scratch live under `%TEMP%\claude`** [verified], including the brief for this review. No family covers them.
- **m3. Provisioning must assert privacy.** The game remote is public, so "created" is not "private". Check `visibility == PRIVATE` through the API after creation and before the first push. The shared token has `repo` scope and no `delete_repo`: agents cannot delete the repositories, but any of them can force-push or delete refs, so "immutable refs" is a convention. I could not read the account plan (the token lacks that scope), so I do not know whether rulesets are available on private repos.
- **m4. `git status` writes.** Any fingerprint that covers `.git\index` and also runs `git status` will perturb what it measures, which this project has already been bitten by. Set `GIT_OPTIONAL_LOCKS=0` in every inspection tool. I did, throughout.
- **m5. `core.autocrlf=true` at system level** [verified]. The committed `* -text` in the plan handles it and the earlier tools review reproduced that. It survives - except for the nested attribute files in B1.

## The undo design (brief item 7)

Sound in principle, and correctly scoped: it is last in the order, "never a prerequisite", and nothing in the cleanup path depends on it. The one leak - checkpoint capsules listed as `nsc-evidence` content - is harmless. Three cautions, all opinion: (1) reversing a task that touched Unity scene or prefab YAML can merge cleanly and be semantically broken, and only a Unity run shows it, one Unity at a time, so undo-complete will cost about what the task cost; (2) "every writer participates" includes Vincent working by hand and the Unity editor, so coverage will not reach 100 percent and "refuse affected undos" risks being the normal answer; (3) six packages is a large build for one developer. A one-day version - `git revert -m 1` of the recorded landing merge, a forward contract revision, evidence marked invalid - would deliver most of the value now and teach what the full design needs.

## Does the revised brief close the Astra FIX FIRST? (brief item 1)

| Astra finding | Revised text | Closed? |
|---|---|---|
| 1 preparation missing from clock | Preparation gate added; 2-4 h replaced by 4-8 / 6-12 "unmeasured" | In text. See M6. |
| 2 roster is not an allocation | "NOT READY" rule and card contents | In text. Zero cards exist. |
| 3 holds and deletion predicates unproven | Fingerprint contents now specified; holds still acknowledgements; "prove writer-race" repeated | **Restated, not closed.** See M2. |
| 4 reverse-dependency map | Specified | In text. |
| 5 recovery point binding | Manifest last, remote bootstrap | In text. Source-side truth still unowned - B1. |
| 6 every-log coverage | Mandatory families added | **Partly.** Transcripts absent (B2); NoSafeCircleOutput reduced to one file (m1). |
| 7 second copy and repeat capture | Default retain originals | In text. P16 has no tool on this machine (B3). |

The Astra follow-up then declared "no remaining material documentation blocker" and says in the same paragraph that nothing was run. It compared text to text. That is the false green one level up: the review passed because the documents agree with each other.

## What the Astra review missed

1. **It never touched the disk.** All seven findings are document-against-document. Everything in B1, B2, B3, M4, M5 came from running something.
2. **Self-consistent verification (B1).** Independence was placed on the restore side only. The `.gitignore` inside the payload hiding a mandatory family is a one-line check nobody made.
3. **The transcripts and their timer (B2)** - the largest body of evidence in the project, in no family, with a default expiry.
4. **F: exists.** A second 4 TB NVMe with 2.3 TB free. "F:", "LData" and "second disk" appear in none of the six documents [verified by grep]. It is not off-machine and does not satisfy P16, but it turns one disk into two in an hour with existing commands, and it makes the no-grace rule unnecessary.
5. **There is no disk problem.** 2.49 TB free, and the clones are hard-linked. The urgency is disorder. Nothing justifies deleting fast.
6. **`origin` is public (M5, m3)**, which is why the unpushed branches cannot simply be pushed.
7. **Holds assume running sessions (M2)** while the same plan keeps them stopped.
8. **Only PowerShell 5.1 (M4).**

## Reviewer errors and limits

- First source scan was **void** (swallowed exception, all zeros). Discarded whole; rerun with error reporting and count assertions. Disclosed in B1.
- An early branch count of 151 used `--no-contains origin/main`, which does not mean "unpushed". Discarded; the 72 figure uses `rev-list --count <head> --not --remotes` per branch.
- One PowerShell call failed on my own quoting of a `jq` expression; rerun without it.
- The junction deletion test did not run (blocked by my sandbox guard; not circumvented). The behaviour in M4 is documented, not reproduced.
- Writing this file took several attempts. Three whole-file writes failed before executing and wrote nothing (checked each time). I first blamed apostrophes in the prose; probes showed that was wrong. The pattern that fits is a command-length limit near 8 KB: a 5.8 KB command succeeded, an 8.5 KB one failed. One PowerShell attempt was refused because its deletion guard read the cmdlet name quoted in M4 as a real removal. The report was then written as six parts in my session scratchpad and assembled by one Python step. The possessive-free wording is a leftover of the wrong theory, not a requirement. No deletion command was involved at any point.
- Not done: no repository created, so nested-attribute precedence, gitlink behaviour and long-path cmdlet behaviour are documented or reasoned, not reproduced. No restore, no network fetch of repository content, no process or handle census, no test suite. The four earlier inputs the brief lists were sampled (tools-move review B1/B2 only), not read in full. The `cleanupPeriodDays` default is from documentation.
- Network calls made, all read-only: `gh auth status`, `gh api user`, `gh repo list`.

## Workspace closeout

No workspace, clone, worktree or repository was created, so no registration was needed. Outputs: this file, plus six part files `part1.md` to `part6.md` left in my session scratchpad (`%LOCALAPPDATA%\Temp\claude\C--nscrev\8a04446c-f69c-42be-a9b8-eb7406c0f41e\scratchpad`). I left them because I was told to delete nothing; they are copies of this text and can go whenever that scratchpad does. TEMP/TMP unchanged; nothing written under `C:\NSC`. No background process started; all commands ran in the foreground and have exited. Artifact: complete. Processes: settled. Owner release: not applicable - nothing to release. No deletion authority used or implied; nothing was moved or deleted.
