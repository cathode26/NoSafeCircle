# Review: durable storage and easy reset design (2026-09-18)

Reviewed: `C:/nscrev/reports/repo-durability-and-reset-design-20260918.md`
Against: the design brief, `exposure-facts.md`, and real source at `C:/NSC/NSC/NoSafeCircle`
(`main` = `255951482`). Everything below was read-only. Nothing was run that mutates the repo, the
live records, or the network. Reviewer: pipeline-reviewer.

## VERDICT: FIX FIRST

**What Vincent can do today, unchanged:** migration steps 1 and 2 (the `git bundle --all` and the
zip). They are sound, they cover refs the later design forgets, and I found **no tokens or
credentials** in anything they would copy (details under Secrets). Two small amendments: add the
four tool folders step 2 leaves out, and confirm OneDrive shows the files as *synced* before
trusting them.

**What must not be acted on as written:** the 15-minute backup (steps 4-6) and the whole undo half
(steps 8-9). The repo *shape* (design D: tools into the game repo, two archive repos, one reset
repo) is right and survives the real numbers. But the design contains four places where a check
would report success while the data is gone or the undo did nothing, and the claim "extend
`reset_task.py`, it already has the hard parts" is not true of the code.

Blocking findings: 9. Worth fixing: 7. Minor: 6.

---

## Blocking findings

### B1. `undo-task` on a completed task is a false green for most real tasks (reproduced from live data)

**What is wrong.** The C7 checkpoint hooks into `review.py` "when status becomes `integrated`".
Most real tasks never pass through there. They land on `main` as Game Agent merge commits:

```
9ffa77847 Merge NSC-077: enemy art integration for the existing moving enemies
7bfbe21c7 Merge NSC-075 eight-direction wizard locomotion source and tests
22955c5a8 Merge NSC-074 cardinal wizard walk source art
1147fce3f Merge codex/nsc017-locked-door-attack-20260914 (NSC-017)
```

44 merge commits on `main` name a task. In the live root
`C:/NSC/NoSafeCircle-AssistantCheckouts/.assistant-control` only **2** records are `integrated`
(NSC-042, NSC-061). NSC-077, 075, 074, 073, 093, 017 and 053 have **no record at all**; NSC-063
is merged on `main` while its record still says `prepared`.

**Failure scenario.** Vincent runs `undo-task NSC-077 --apply`. No record, no C7, no checkpoints.
The design's first fail-safe rule fires: *"Nothing to undo: exit 0, 'nothing to undo', no
writes."* The task's work is still on `main`. The command reported success and did nothing. This
is exactly the project's recurring failure shape.

**Fix.** (a) "No checkpoints" must never be "nothing to undo". If `main` holds any commit naming
the task, or a contract exists, and the ledger is empty, exit non-zero with "this task is not
known to the ledger; undo cannot act". (b) The completion hook must be on the path tasks really
take: the Game Agent's main-write / merge path, not only `review.integrate`. (c) Say plainly that
every task completed before the ledger ships has no one-call undo.

### B2. Undo-of-edit verifies the policy binding against the wrong thing (claim 4 is false)

**What is wrong.** The design says each revision is "exactly one commit incl. the policy rebind"
and that after the revert it will "check the restored policy hash against the checkpoint". I
checked every commit on `main` that touched a contract while that task had a policy entry: **92
commits, of which 22 left `task_contract_sha256` not matching the contract at that same commit**
(binding repaired by a later commit). Examples:

```
NSC-077 d9af025a5 owner contract revision 3     (stale)   25fdc505d rev 4 (stale)
NSC-077 db0532ab4 owner contract revision 5     (stale)   3eb886805 rev 6 (stale)
NSC-077 a58d21e31 owner contract revision 7     <- first commit that rebinds
NSC-044 1795df8fd GER rev 4, d387d5ce0 follow-up rev 5; NSC-049 df90eb340; NSC-082 ddd45426b; NSC-020 d69ad5f7c
```

Also, 13 tasks got their policy entry in a **separate** commit ("TaskReviewAgent: add the
validation policy entry for NSC-067", also 007, 017, 032, 050-053, 068, 089-092), and some
commits create or revise **several tasks at once** (`36b629f73 TaskGraph: add NSC-095 and
NSC-096`; `82c96a9d9` touches NSC-049 and NSC-069; every decomposition apply).

Since about 2026-09-17 the owner-revision commits do rebind in the same commit (all of NSC-077
rev 7-10, NSC-007 rev 6-8, NSC-097/098/099). So the claim is true of the *current tool*, false of
*history*, and nothing in the repo enforces it - `contract_commit.py` lives outside the repo.

**Failure scenario.** `undo-task NSC-077` back across `a58d21e31`. The single revert restores the
revision 6 contract together with the revision-2-era hash. The binding is stale; candidates park.
The design's safety check compares the restored policy hash with the hash *recorded at the
checkpoint* - which, for a checkpoint taken at a stale commit, is the same stale value. The check
passes. Undo reports success and the task cannot run. This is the brief's constraint 9 worked
example, reproduced.
Second scenario: undo-create of NSC-095 reverts `36b629f73` and silently deletes NSC-096 too.

**Fix.** After the revert is staged and before it is committed, **recompute**
`sha256(Tasks/NSC-###.yaml)` and compare with the entry's `task_contract_sha256`, then run the real
`taskcontrol validate` on the result. Never compare against a stored copy of the same field.
Refuse any undo whose commit touches another task's contract. Better still, see B3's fix.

### B3. Undo of create or edit is refused for ~85% of real contract commits, so it is not "one call"

**What is wrong.** The design reuses `reset_task`'s rule "(c) no commit after N from another task
touches this task's paths". A contract commit does not touch only the contract. Real examples:

```
255951482 rev 8 NSC-007: RESOURCE_GROUPS.yaml, authoritative_validation_policy.json, Tasks/NSC-007.yaml
3cbea24bd add NSC-099:   RESOURCE_GROUPS.yaml, WORK_ID_MAP.json, authoritative_validation_policy.json, Tasks/NSC-099.yaml
```

Those shared files are touched by nearly every other task's contract commit. Measured today: of
**104** contract commits on `main`, **88** already have a later commit touching one of their
paths. With the path-level overlap rule those 88 undos refuse. Without it, `git revert` works on
hunks inside one shared JSON file and "the staged-paths check proves the revert touched exactly
the expected files" proves nothing about *which entries inside the file* moved.

**Failure scenario.** Vincent edits NSC-007, then the GER agent revises NSC-015 (touching
`RESOURCE_GROUPS.yaml`). "Undo my NSC-007 edit" is now refused, permanently. The feature he asked
for works only while the edit is the newest contract commit on `main`.

**Fix.** Do not revert contract commits. Make undo-edit a **forward revision**: revision N+1 whose
content is revision N-1, written through the same contract tool that already rebinds the policy
and updates the shared files. It is additive, it cannot leave a stale binding, it needs no overlap
rule, and it goes through validation that already exists. Undo-create becomes a contract
disposition change (retire), not a deletion.

### B4. `reset_task.py` is much thinner than "it already has the hard parts" (claim 1 is only partly true)

Verified true: dry-run default, `git revert --no-commit`, resumable journal, staged-paths check,
refusal on live worker / reservation / running controller / overlap / dependents. But:

1. **Three guards block live use, not one.** Q3 asks Vincent to relax only the remote guard. The
   code also has
   `if not isinstance(branch, str) or not branch.startswith(GAUNTLET_REPLAY_PREFIX): raise ...`
   (all three live integrated records say `branch: main`), and
   `if record.get("status") != "integrated": raise ResetTaskError(...)`. Q3 understates what
   Vincent would be agreeing to.
2. **It only handles one state.** Create, edit, C3-C6 and "midway" all fail the `integrated`
   check. Nothing in the file reverts a contract commit or an evidence commit.
3. **It does not restore a record. It removes it.** Phase 2 does
   `shutil.move(str(record_file), str(archived_records / record_file.name))` for every
   `NSC-###.*` file and moves the whole task checkout into the archive. The design's central
   mechanism - "restoring a record is a merge", keep `worker_history`, append an `undo` entry,
   resume at C5 with the candidate still in the checkout - has **no existing code**, and the
   existing behaviour (archive the checkout) destroys the thing a C5 resume needs.
4. **`integration.pre_task_commit` does not exist.** `grep pre_task_commit` over `Pipeline/` finds
   it only as a local variable here, set from `record.get("source_commit")`. The real fields are
   `source_commit` and `integration.source_before`. The design read the variable name, not the
   record.
5. Theoretical, fails loud: `source_update.py:380` synchronises candidates with
   `merge --no-ff`. A range containing a merge makes `git revert A..B` stop ("is a merge but no -m
   option"). Not a false green, but another case the "as today" row does not cover.

**Consequence.** Step 9 is not "one fix branch on top of `reset_task.py`". It is a new module that
borrows the refusal list and the journal pattern. Re-estimate before committing to it.

### B5. "dispatchable: true" cannot be computed the way the design says (false-green risk)

The design: "`worker_state.py` holds the shared predicates the four gates use ... Undo's last step
calls those same predicates plus the four gates in dry-run form".

- Only **two** modules import the predicates: `prepared_refresh.py:12` and `worker_launcher.py:28`.
  `scope.py` and `admission.py` (reserve) do not. Claim 3 (the exports, and `succeeded` excluded:
  `FINISHED_WORKER_STATUSES = frozenset({"failed", "stopped"})`) is true; "the four gates use
  them" is not.
- None of the four gate modules has a dry-run mode (`grep dry_run|dry-run` = no hits), and scope
  cannot even be asked without a lease: `raise ScopePlanningError("assistant scope planning
  requires a lease_id")`.

**Failure scenario.** The implementer cannot call what does not exist, so `dispatchable` is
computed from the predicates alone. Undo prints `dispatchable: true`; the next real dispatch is
refused by scope or reserve. That is the four-refusals incident again, now with a green light on
it.

**Fix.** Either add a real read-only `explain` path to each of the four gates and call all four,
or report `dispatchable: unknown (scope, reserve not checked)`. Never print `true` from a subset.

### B6. The headline "15 minutes for committed work" is false for candidate commits (reproduced)

Task checkouts are **standalone clones** (`NSC-003/.git` is a directory). A candidate commit
exists only there until `integrate` fetches it. Checked the live records:

```
NSC-007 awaiting_human  candidate ce1e22832  in source repo objects: False
NSC-032 awaiting_human  candidate 622ac7630  in source repo objects: False
NSC-043 approved        candidate debc55ee8  in source repo objects: False
```

The 15-minute job pushes the game repo's branches and fetches from `C:\nscrev\*` review clones.
It never looks inside task checkouts. Those fall under "task checkouts ... nightly". So C5 - which
the design itself calls "the most valuable midway point", paid-for crew output, in one case
already **approved** - has a **24-hour** window, and its only copy is a file-level copy of a live
`.git` directory, which is the one thing per-file atomicity does not protect.

**Fix.** The backup hub must also `git fetch` (read-only) from every task checkout under every
live checkout root, into `refs/backup/checkouts/<root>/<task>/*`, on the 15-minute run.

### B7. The backup remote is not append-only, and it skips 117 refs

The design: refspec `+refs/heads/*:refs/heads/*`, "no `--prune`, no `--mirror` so nothing is ever
deleted there".

- The leading `+` is a **force** update. It does not delete branch names, but it replaces a branch
  tip with whatever is local. **Scenario:** an agent botches a rebase or `reset --hard` on
  `assistant/NSC-042`, or a ref is corrupted. Within 15 minutes the good tip on the backup is
  overwritten; the old commits become unreachable and GitHub eventually collects them. The backup
  faithfully preserved the mistake - the opposite of "we should be able to fuck up and reset".
- `refs/heads/*` misses what this repo really has:
  `108 refs/archive, 5 refs/trial, 3 refs/integration, 1 refs/stash`. `refs/archive/*` is where
  archived branch tips live. Step 1's `bundle --all` does cover them; the ongoing job does not,
  so they age out of protection the day step 5 replaces step 1.

**Fix.** Push without `+`. When a branch is not a fast-forward, also push the new tip to
`refs/history/<branch>/<utc>` and leave the old one. Use `refs/*:refs/*` minus `refs/remotes/*`.

### B8. The secret scan as specified silently drops most of the backup (false green, measured)

Step 1 of the scan adds "a plain grep for `sk-ant-`, `sk-`, ... `Bearer `". Rule 4 makes a hit
advisory: "the file is left uncommitted and named in `backup-warnings.txt`; everything else still
backs up."

`sk-` matches "ta**sk-**", "ri**sk-**", "di**sk-**". Measured today against that grep:

- `C:/nscrev/reports`: **73** text files match, including `handoffs/BOARD.md` (the shared handoff
  board) and this design document itself;
- `C:/NSC` top-level docs: **45 of 80**; `agent-state`: **12 of 17**.

None of them contains a secret. **Failure scenario:** the job runs green every 15 minutes for
months while the handoff board and most of the agent state were never committed; the only trace
is a text file nobody opens. More generally, nothing in the design detects a backup that has
stopped: expired GitHub auth, a push rejected for one bad file, a sleeping laptop, a disabled
scheduled task all look the same as success.

**Fix.** (a) Only anchored patterns (`sk-ant-[A-Za-z0-9_-]{20,}`, `ghp_[A-Za-z0-9]{30,}`,
`github_pat_...`, PEM headers) plus gitleaks. (b) A skipped file must make the run **not green**.
(c) After each push, verify with `git ls-remote` that remote sha == local sha per ref, write
`last-verified-utc`, and show "backup age" where Vincent already looks (viewer header or session
start). Stale by more than an hour = visible red. (d) A restore drill is part of "done": clone
from the backup remote into a scratch folder and run the non-Unity suite.

### B9. The `.assistant-control` answer has no key-custody or "is it actually off the machine" story

Constraint 1 did get a real answer (tiered restic snapshots, retention stated), so it is not waved
through. But two holes make it unsafe to trust:

- **Where does the restic password live?** The design never says. If it is only on this machine,
  a stolen or dead machine leaves an encrypted repository nobody can open. That is total loss
  reported as "backed up hourly".
- **restic into the OneDrive folder is a local write.** It is off-machine only after the OneDrive
  client uploads, which the script cannot see, and OneDrive syncing a restic repository (many
  small pack/lock files, Files On-Demand) is a known source of partial or conflicted repos. The
  real window is "60 min + unknown sync lag", unverifiable.

**Fix.** Password in Vincent's password manager plus a printed copy, stated in the design. Use a
restic backend that confirms the upload (B2, S3, rclone to OneDrive) or, if staying on the sync
folder, run `restic check` plus a test restore weekly and surface the result like B8(c).

---

## Worth fixing

**W1. Things still only on this drive after full implementation.** The design's table puts "agent
definitions" in `nsc-ops`, an in-place repo at `C:\NSC`. They are not under `C:\NSC`: there are 14
files in `C:\Users\VincentLiguori\.claude\agents\` and nothing in `C:\NSC\.claude\agents`. Agent
memory is at `C:\Users\VincentLiguori\.claude\projects\C--NSC\memory`. Neither can be covered by
that repo. Also uncovered: `.git\assistant-control-admissions.json` (inside the source `.git`, so
in no tree, no snapshot path and no push), `C:\NSC\NSC\.assistant-control\` (architect journal and
`recovery\`), the 45 top-level `CLAUDE_*.md` / `CODEX_*.md` files in `C:\NSC` that the whitelist
`!nsc-*.md` excludes (35 of 80 are covered), 220 top-level non-md files in `C:\NSC` (scripts such
as `adopt_nsc_1101.py`), the scheduled task definition and the backup script's own config.
Scenario: machine stolen; the restored fleet has rules but no agent definitions and no memory.
Fix: copy-in (a sync step into `nsc-ops`) for the out-of-tree folders, and an explicit decision on
the 45 other md files.

**W2. Tools have no ongoing protection between step 2 and step 7.** The design names `ger-tools`,
`viewer-tools` and "the jobs tools". Real set: six folders, **72** `.py` (`ger-tools` 43,
`job-tools` 13, `claude-jobs` 8, `astra` 4, `viewer-tools` 3, `session-tools` 1). Step 2 zips only
two of them, once. Porting 72 files with tests through review is weeks, not "already queued".
Scenario: drive dies in week two; every `ger-tools` edit since the zip is gone, and `ger-tools` is
the tool that writes contracts to `main`. Fix: put all six tool folders (scripts only, run output
excluded) into `nsc-ops` or a fourth small repo **now**, and delete them from it as each is ported.
**The recommendation itself survives the real count:** the argument for tools-in-game-repo is
version lock with the pipeline, not size, and 72 files of a few MB changes nothing about it.

**W3. Undo of C3 (children applied) is listed as a checkpoint but never designed.** The "mutation
undone" table has no C3 row. A revert of a decomposition commit removes child contracts that may
already have records, checkouts and reservations, and it lands on `main` without the committed
graph validation that `apply_graph_delta` runs. The design rightly does not use that function's
seams - its docstring says "Production callers must use the defaults and must not use the seams to
weaken materialization, committed validation, or rollback" - but it also cannot borrow its
rollback, which is `reset --hard old_head` (`_rollback_failed_commit`) and is unusable on a pushed
`main`. Fix: either declare C3 not undoable in phase 1, or specify: refuse if any child has a
record; run the same committed-graph validation on the staged revert before committing.

**W4. Per-file atomic replace is true for records, not for the snapshot.** Claim 5 verified for
records: `write_record` writes a temp file, `os.fsync`, then `os.replace(temporary, path)`. Not
atomic: `run_crew.py:2976` `crew_result.json`, `:2605/:2621` handoff files, `:2655` audit artifact
(`write_text`), and the `.jsonl` event logs (append). And atomic files do not make a consistent
*set*: a snapshot mid-mutation pairs a new record with an old checkout `.git`. Fix: run restic
with `--use-fs-snapshot` (VSS) so each snapshot is one point in time, and treat run-folder JSON as
possibly truncated on restore.

**W5. "`.assistant-control`" is not one folder.** The real source has at least three checkout
roots with records (`NoSafeCircle-AssistantCheckouts` 37 records, written today;
`NoSafeCircle-Game-Checkouts-3` 14; `-2`), plus dozens of gauntlet roots. The design says
`<checkout-root>\.assistant-control` as if singular and never lists which roots are live. A
snapshot include-list that names one root silently omits the others. Fix: enumerate roots by
`project.json` whose `source` is the live repo, and print the list in every run.

**W6. A `.git` at `C:\NSC` changes git's answer for hundreds of scratch folders under it**
(theoretical). Today `git -C C:/NSC rev-parse` fails. After `git init`, any tool or agent that
runs git from a non-repo scratch folder under `C:\NSC` resolves to `nsc-ops` instead of failing;
a stray `git add -A` there stages against the fleet-rules repo. Fix: keep the git dir outside the
tree and drive it only from the backup script with explicit `--git-dir` / `--work-tree`, so no
`.git` ever appears in `C:\NSC`.

**W7. Midway resume creates `assistant/NSC-###-resume-<n>`; nothing shows the pipeline accepts a
record whose branch is not `assistant/NSC-###`.** Unverified - I did not trace every reader of
`record["branch"]`. It needs a test before step 9 is sized.

---

## Minor

- **m1. Claim 8 is overstated.** `account-cache.json` is 108 bytes:
  `{"claude-exec": {"account": <an email address>, "checked_at": <float>}}`. No token. The `*.log`
  files beside it are at most 300 bytes: Docker "Container ... Created" lines and a Claude Code
  workspace-trust warning. Keeping run folders out of the repos is still right (403 entries of
  prompts and outputs), but the design should not call these credentials.
- **m2.** Q1 is answerable in one command (`gh repo view cathode26/NoSafeCircle --json
  visibility`); I did not run it because it is a network call outside this review's lane.
- **m3.** The step 1 bundle is the whole history, unencrypted, in a synced folder on the same
  laptop. Fine against a dead drive; against theft it depends on BitLocker. Say which.
- **m4.** `core.autocrlf=false` + `* -text` for the archive repos is right. The `nsc-*.md` files
  have no CRLF today, so there is nothing to churn.
- **m5.** 15-minute auto-commits in `nsc-ops` will capture half-written docs. Harmless for backup;
  say that `git revert <sha>` there may need to target a range.
- **m6.** No report file exceeds 20 MB, so GitHub's 100 MB per-file limit is not in play yet; with
  Q6 "keep everything" it should be a checked condition, since one oversize file fails the whole
  push (and see B8: nobody would notice).

---

## The eight named claims

| # | Claim | Result | Evidence |
|---|---|---|---|
| 1 | `reset_task.py` has dry-run default, revert, journal, staged-paths check, the refusals | **True for the listed items; false as a basis for "extend this"** | `if not apply: return {**plan_reset(...), "apply": False}`; `git(source, "revert", "--no-commit", ...)`; `if staged != sorted(task_changed_paths...)`. But status/branch guards and archive-not-restore: see B4 |
| 2 | Refuses any source with a remote | **True** | `raise ResetTaskError(f"reset-task refuses a source with a Git remote: {remotes}")`. Two more guards exist that Q3 does not mention (B4) |
| 3 | `worker_state.py` exports the three predicates; `succeeded` not finished | **True** | `FINISHED_WORKER_STATUSES = frozenset({"failed", "stopped"})` and the comment above it. "The four gates use them" is false: two importers (B5) |
| 4 | Create and revise are each exactly one commit incl. the rebind | **False for history, true for the last ~2 days** | 22 of 92 stale-at-commit; 13 entries added in separate commits; multi-task commits (B2) |
| 5 | Records written by atomic replace | **True for records; false for run artifacts; insufficient for a snapshot** | `os.replace(temporary, path)` in `write_record`; `write_text` in `run_crew.py` (W4) |
| 6 | Reservations in `.git/assistant-control-admissions.json` | **True** | `return common / "assistant-control-admission.lock", common / "assistant-control-admissions.json"`; file present, 5,118 bytes. Consequence the design misses: nothing backs it up (W1) |
| 7 | No per-role commit in `ExecutionCrew` | **True** | no `git commit` invocation anywhere in non-test `Pipeline/ExecutionCrew`. The design is not over-pessimistic here |
| 8 | `account-cache.json` and the logs hold credentials | **False** | one email address and a timestamp; logs are Docker/CLI noise (m1) |

---

## The seven questions

1. **Durability.** The 15-minute window is real only for branches in the game repo and the review
   clones. Candidate commits: 24 h (B6). 117 non-branch refs: unprotected after step 5 (B7). The
   trigger is a scheduled task plus checkpoint events; when it does not fire nothing notices (B8).
   Still only on this drive after full implementation: see W1, plus uncommitted work in flight
   (disclosed).
2. **Three undos.** Walked *edit* end to end on NSC-077 and NSC-007: refused by path overlap in
   the common case (B3), and where it runs it can restore a stale binding and pass its own check
   (B2). *Complete*: exits 0 with nothing done for hand-merged tasks (B1). *Create*: can delete a
   sibling task (B2). None of the three is reachable by one call today's design would make safe.
3. **Start midway.** The boundaries are reasonable *rewind* points. As *resume* points only C4 and
   C6/C7 hold: C5 needs the candidate in the checkout, which the borrowed code archives away (B4.3)
   and which is the least-protected data in the system (B6). "A later phase changed an earlier
   phase's output" is answered only by the path check, which B3 shows is too coarse.
4. **Cross-repo.** Genuinely solved, not restated: one reset repo, so no tuple is needed. This is
   the strongest part of the design. Caveat: until step 7 finishes, the contract tool is outside
   the repo, so "which tool wrote this contract" (section 3.4) has nothing to record.
5. **Secrets.** Asserted, not checked: two suspects named, one of them wrongly. What I found:
   zero token-shaped strings in all six tool folders, in `claude-jobs`, `codex-jobs`, in
   `C:/nscrev/reports` (3,913 files), in the 80 top-level docs and in `agent-state`. The only hits
   anywhere under `C:/nscrev` are copies of the repo's own test fixture
   `secret = "ghs_faketokenvalue"`, already on `origin`. Email addresses: 74 report files (mostly
   commit-message trailers), 10 docs. Private repos are required for that reason, as the design
   says. Not scanned: binary files, and the PixelLab token (unknown prefix) - gitleaks must still
   run.
6. **Constraints.** 4.1 satisfied in intent, holes B9/W4/W5. 4.2 satisfied. 4.3 addressed in
   design, unsupported by the code it cites (B4, B5). 4.4 satisfied. 4.5 **violated** - push
   recommended on an assertion, and the specified scan is harmful (B8). 4.6 satisfied. 4.7
   satisfied. 4.8 satisfied for branches by name; weakened by the force refspec (B7). 4.9
   **violated** (B2). 4.10 **violated** in effect (B5).
7. **Scope honesty.** Thinner than reality. Missing from "what stays at risk": candidate commits,
   non-branch refs, agent definitions and memory, the admissions registry, every task completed
   before the ledger exists, the restic password, and "the backup stopped and nobody knew".

## Do the real numbers move anything?

No recommendation moves. Reports at 133 MB / 3,913 files fit a private repo comfortably. 72 tools
instead of 46 does not change where they belong; it changes the *effort* and therefore the length
of the unprotected gap (W2).

## What I ran, and what I did not

Read-only `git log/show/diff/rev-list/for-each-ref/cat-file` in `C:/NSC/NSC/NoSafeCircle`;
read-only JSON reads of live records; ripgrep/grep scans that printed file names and counts only,
never matched values. Not run: any test suite (this is a design, there is no head/base), Unity,
Docker, providers, any network call, anything that writes under `C:\NSC`. Unverified and marked
as such: W6, W7, B4.5, and Q1's answer.