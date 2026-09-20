# Durable storage and easy reset for the No Safe Circle workspace

Decision document, 2026-09-18. Pipeline Maintainer. Design only: nothing here has been built, no
repository was created, nothing was pushed.

**The short answer**

- **Durability and reset are two problems.** Durability is "a copy that is not on this machine".
  Reset is "commits reverted, record dispatchable again, leases and workers released". A local
  `git init` gives neither: no remote, so it burns with the drive; and git never touches a record
  or a lease.
- **Shape: one reset repo plus two archive repos, all private.** Tools move *into* the game repo.
  Docs and reports each become a private archive repo. Only the game repo ever takes part in a
  reset, so there is never a cross-repo revert.
- **Undo is one command built on the `reset_task.py` you already have**, extended with automatic
  checkpoints. Git restores the files half; a checkpoint ledger restores the record half.
- **Do this today, before any of the design:** one `git bundle --all` of the game repo into
  OneDrive. It needs no GitHub repo, no push, no new tool, and it saves all 133 local-only branches.

Numbers: `exposure-facts.md` was empty when I read it (header only). I used the brief's
orders of magnitude: ops material single-digit MB, `reports` ~100+ MB / ~3,900 files,
`.assistant-control` ~1.5 GB. Verified myself today: 141 local branches, 133 without upstream;
`main` level with `origin/main`; 98 task contracts.

---

## 1. Recommended repo shape

**Rule used to decide: split along the reset boundary, not along the kind of content.** Anything
that must roll back *together with a task* lives in one repo. Anything that never rolls back with
a task can live elsewhere at no reset cost.

| Option | Repos in a task reset | Cross-repo reset cost (§4.4) | Other cost | Verdict |
|---|---|---|---|---|
| **A. Everything in the game repo** | 1 | None | Every task gets its own clone of this repo; ~100 MB of daily-churning reports multiplies across ~100 task checkouts. Doc set holds account details; the game repo may be public (Q1). Reports inside the checkout dirty the tree and break `run_unity_tests_clean.ps1` (§4.2) | Rejected |
| **B. Game repo + tools repo + artifacts repo** (his question 1) | 2–3 | **High.** `ger-tools` commits contracts to main and must match the pipeline code at that commit. Tool in repo 2, contract in repo 1, evidence in repo 3: "reset NSC-042" is a coordinated revert at three shas, and nothing records the tuple | Tools lose the pipeline's tests and review flow | Rejected |
| **C. One repo per folder** (his question 2) | 3+ | Highest. Same as B, more tuples | More remotes, more first-push scans | Rejected |
| **D. Recommended: game repo (now incl. tools) + `nsc-ops` + `nsc-reports`** | **1** | **None.** A task reset touches only the game repo plus records. A fleet mistake touches only `nsc-ops`. No reset ever spans two repos | Three remotes to keep pushed; one backup script covers all | **Chosen** |

Answer to his questions: **tools do not get their own repo — they go into the game repo**, under
`Pipeline/` with tests (this is already the Maintainer's standing job; `main_write.py` was ported
this way in G15b). **Artifacts do get their own repo**, because they must stay out of the game
checkout (§4.2) and they never roll back with a task. "Everything in its own repo" makes reset
harder, not easier: git's undo is per repo, and a consistent point in time across repos only
exists if something records the tuple of shas. Design D avoids needing that tuple at all.

What goes where:

| Content | Home | Why |
|---|---|---|
| `C:\nscrev\ger-tools`, `viewer-tools`, the jobs tools | Game repo, `Pipeline/...` | Version-locked to the pipeline code. Replaces the hand-made `.bak.py` rollbacks with history |
| `C:\NSC` doc set, `CLAUDE.md`, `agent-state\`, agent definitions | `nsc-ops`: a repo **in place** at `C:\NSC` with a whitelist `.gitignore` (`/*`, then `!nsc-*.md`, `!CLAUDE.md`, `!agent-state/`) | No file moves, so no path in any guide breaks. `C:\NSC` holds hundreds of scratch folders and the game checkout; the whitelist ignores all of them |
| `C:\nscrev\reports` (incl. `handoffs\BOARD.md`) | `nsc-reports`: a repo in place at `C:\nscrev\reports` | Different root from the doc set, so one repo cannot cover both without moving files. It never takes part in a reset, so the extra repo is free |
| 133 local-only branches; fix branches in review clones | A **private backup remote** for the game repo (not `origin`) | Pushing 133 branches to `origin` would mean "release" and clutter it. See §2 |
| `.assistant-control` | Not git. Snapshot backup. See §2 | §4.1 |

---

## 2. What makes it durable

All remotes **private**. Until Q1 is answered, assume the existing `origin` may be public and put
nothing new on it.

| Asset | Off-machine copy | Trigger and cadence | Worst-case loss |
|---|---|---|---|
| Game `main` and all 141 branches | Private backup remote `NoSafeCircle-backup`, refspec `+refs/heads/*:refs/heads/*`, **no `--prune`, no `--mirror`** so nothing is ever deleted there (§4.8) | Scheduled task every 15 min, plus at every checkpoint event (§3) | **15 min** of commits |
| Fix branches in `C:\nscrev\*` clones | Same backup remote. The backup script *fetches from* each clone into a local bare hub (`refs/backup/<clone>/*`), then pushes the hub. Read-only on the clones; their push stays DISABLED | Same run | 15 min |
| `nsc-ops`, `nsc-reports` | Private GitHub repos | Same run: auto-commit then push | 15 min |
| Per-task records, journals, overlays, worker configs, checkpoint ledger (small, irreplaceable) | Encrypted snapshot (restic recommended; not installed today) to cloud storage | Hourly, and at every checkpoint event | **60 min** |
| `worker-runs\`, `decomposition-runs\`, `viewer-logs\`, task checkouts (the bulk of the 1.5 GB) | Same snapshot tool, deduplicated | Nightly. Keep 7 daily + 4 weekly | **24 h** of run logs |
| Uncommitted work inside a running task checkout | None | — | The run in flight: up to 60 min of provider spend (3600 s worker timeout) |

**Headline window: 15 minutes for committed work, 1 hour for records, 24 hours for run logs.**

Why `.assistant-control` is a snapshot and not a repo (§4.1): it is written during runs, so a
commit would race the writers and the index; 1.5 GB of logs would bloat history forever; and its
value is "latest state plus a few days back", which is retention, not version history. It is
**not** disposable: the records are the truth about what ran, and the run logs cost provider money
to reproduce. The small irreplaceable part gets the tight cadence; the bulk gets nightly. The
backup reads files only and takes no pipeline lock. Records are written by atomic replace, so a
snapshot sees a whole old file or a whole new one, never a torn one.

Secrets (§4.5) — **nothing is pushed before this runs clean:**

1. Run `gitleaks detect --no-git` over each folder before its first commit (not installed today;
   one winget install). Add a plain grep for `sk-ant-`, `sk-`, `ghp_`, `github_pat_`,
   `CLAUDE_CODE_OAUTH_TOKEN`, `Bearer `, and the PixelLab token prefix.
2. Known suspects found today: `C:\nscrev\claude-jobs\account-cache.json` and the `*.log` job
   dumps beside it. Keep `claude-jobs\` and `codex-jobs\` run folders **out** of any repo; only
   their templates and tool scripts move.
3. Reports hold account emails and log dumps. Private repo is mandatory, and the scan still runs.
4. In the backup script a finding is **advisory**: the file is left uncommitted and named in
   `backup-warnings.txt`; everything else still backs up. It never blocks a task.

Settings for each new repo (§4.6): `core.longpaths=true`; `core.autocrlf=false` with a
`.gitattributes` of `* -text`, so the archive repos store bytes exactly as written and no CRLF
file is ever rewritten. The game repo keeps its current `autocrlf=true`. The backup script follows
the Windows rules: `CREATE_NO_WINDOW`, hidden scheduled task, no detached process, UTF-8 without
BOM, atomic replace.

Lanes (§4.7): creating the three private repos is **Vincent's** action. Pushing is the Release
Agent's lane on his go. The 15-minute push only works with a **standing go limited to the backup
remotes, never `origin`** (Q2). Without it, the fallback is the same script writing bundles into
OneDrive: no push at all, same 15-minute window, clumsier restore.

---

## 3. The reset design

### 3.1 The hypothesis: "if every checkpoint is a commit, start-midway is just a checkout"

**Half right.** For create and edit it is fully right: each is already exactly one commit on
`main` ("TaskGraph: add NSC-099", "owner contract revision 8 for NSC-007"), and the policy rebind
is in the same commit. For the run and integrate phases it is wrong on its own, because a
checkpoint there is also:

- the record `NSC-###.json` (status, candidate, approval, `integration.pre_task_commit`);
- `NSC-###.decomposition.json`;
- the reservation in `.git\assistant-control-admissions.json` (per source, outside every tree);
- worker entries, leases, containers and host processes.

None of those are in any git tree, and the last group is not files at all. So: **git is the file
half, a checkpoint ledger is the record half, and leases are never restored — only proven
released.**

### 3.2 Checkpoints, captured automatically

A checkpoint is one small JSON file in `<checkout-root>\.assistant-control\checkpoints\NSC-###\`,
written by the pipeline command that performs the mutation, inside the lock that command already
holds. No agent has to remember anything.

Each entry holds: sequence number, event, time, `main` sha, task-branch sha, sha256 plus an
embedded copy of the record and decomposition record, the sha256 of the task's entry in
`authoritative_validation_policy.json`, and the task's admission entry. Because the entry names
every sha it depends on, it *is* the tuple from §4.4 — and with one reset repo it has one repo in
it.

| # | Boundary | Hooked into | Why it is a seam |
|---|---|---|---|
| C1 | Contract created | the contract commit tool (`contract_commit.py`, once in the repo) | One commit on main. Undo target for *create* |
| C2 | Contract revised | same tool, per revision | One commit incl. the policy rebind (§4.9). Undo target for *edit* |
| C3 | Children applied | `apply-decomposition` | Moves main and writes the decomposition record |
| C4 | Prepared | `checkouts.py` when status becomes `prepared` | Clean clone at a known `source_commit`. Resume here = re-run the whole crew |
| C5 | Candidate produced | `candidate.py` | Exact candidate commit on `assistant/NSC-###`. **The most valuable midway point**: re-review and re-integrate without paying for the crew again |
| C6 | Approved | `review.py` | Resume here = re-run integration only |
| C7 | Integrated | `review.py` when status becomes `integrated` | Already records `pre_task_commit` and candidate. Undo target for *complete* |
| C8 | Evidence recorded | `record_delivery` | The evidence commit on main |

Not a boundary, on purpose: **individual crew roles.** I found no per-role commit in
`ExecutionCrew`, and a provider session cannot be restored. Resuming between roles needs proof the
crew can restart at a role boundary. Phase 2, and only if C4/C5 turn out too coarse. Heartbeats
and viewer overlays are not boundaries either: nothing resumes from them.

### 3.3 The command

```
python -m Pipeline.AssistantControl undo-task NSC-042                 # dry run: prints the plan
python -m Pipeline.AssistantControl undo-task NSC-042 --apply         # back to the previous checkpoint
python -m Pipeline.AssistantControl undo-task NSC-042 --to C5 --apply # start midway
python -m Pipeline.AssistantControl checkpoints NSC-042               # list them
```

It extends `Pipeline/AssistantControl/reset_task.py`, which already has the hard parts: dry run by
default, revert instead of hard reset, a resumable journal, and refusal on a live worker, an
active reservation, a running controller, overlapping later paths, or later-integrated dependents.

| Mutation undone | Files | Record |
|---|---|---|
| **Create** (C1) | `git revert` of the single add commit; the policy entry leaves with it | No record exists yet. If one does (already prepared), refuse and say "undo to C1 requires undoing C4 first" — or do both in order with `--to C0` |
| **Edit** (C2) | `git revert` of that one revision commit. Contract and policy binding return together because they were committed together. Then check the restored policy hash against the checkpoint; on mismatch, stop before committing | If a checkout was prepared against the undone revision, the record is marked for the existing `refresh-prepared` path |
| **Complete** (C7, C8) | `git revert --no-commit pre_task_commit..candidate` as today, plus the evidence commit | Record restored from the target checkpoint (below) |
| **Midway** (`--to CN`) | Revert this task's main commits after CN. The task branch gets a new `assistant/NSC-###-resume-<n>` branch at CN's sha; the old branch and its commits stay (§4.8) | Record restored to CN |

**Restoring a record is a merge, not a paste.** From the checkpoint: status, candidate, approval,
integration fields. Never from the checkpoint: `worker`, leases, reservation — these keep their
current, settled values, and `worker_history` stays append-only. An `undo` entry is appended with
from, to and the revert sha. The files set aside go to the archive folder, as `reset_task` does
today.

**"Dispatchable" is not redefined (§4.10).** `worker_state.py` holds the shared predicates the
four gates use (`is_finished_worker`, `finished_run_ids`, `is_finished_launch`; note `succeeded`
is deliberately not "finished"). Undo's last step calls those same predicates plus the four gates
in dry-run form and reports `dispatchable: true/false, refused by: <gate>`. If a gate would still
refuse, the command says so; it does not claim success.

**Work before N stays trusted** because undo is refused unless (a) checkpoint N's `main` sha is an
ancestor of HEAD, (b) the record and policy hashes stored at N still match what git and the
archive hold, and (c) no commit after N from *another* task touches this task's paths. If a later
phase of the *same* task changed an earlier phase's output, the range revert undoes it, and the
staged-paths check already in `reset_task` proves the revert touched exactly the expected files.

**Fails safe:**

- Nothing to undo: exit 0, "nothing to undo", no writes.
- Live worker, unsettled capacity, active reservation, controller running, dirty tree, overlap,
  dependents, hash mismatch: refuse with the reason and mutate nothing. It never stops a worker or
  removes a container itself; it names the existing command (`stop-worker`, `settle-worker`).
- Crash midway: the retained journal resumes it; a second reset for a different task is refused
  until the first is resolved.
- These refusals are reused from `reset_task`, not new gates on normal work.

**One existing guard must change, and that needs Vincent's yes (Q3):** `reset_task` refuses any
source with a git remote, because it was written for gauntlet replays. For live use that guard
becomes "revert commits only, never rewrite history", which is safe on a pushed `main`. Undo on
the live source moves `main`, so it runs under the main-write protocol, by the Game Agent or
Vincent.

**Cannot be undone, and the command says so:** a push to `origin` (the revert is a new commit on
top), provider spend, GitHub PRs or issues already opened, a WebGL build already published, and
Unity `Library` state.

### 3.4 Fleet-level mistakes (a bad rule, guide or tool edit)

Different mechanism, because there is no record and no lease:

- **Doc, rule, agent-state or agent-definition edit:** `git revert <sha>` in `nsc-ops`. The
  15-minute auto-commit gives fine-grained history without anyone committing by hand. One repo,
  no tuple. Running sessions must re-read the file; say so in the revert message.
- **Tool edit:** tools are in the game repo, so it is a normal revert on `main` through the Game
  Agent. This retires the `.bak.py` files.
- **A bad tool edit that already wrote bad contracts:** revert the tool, then `undo-task` each
  affected task. The C1/C2 checkpoints record which tool commit wrote them, so the affected list
  is a query, not an investigation.

---

## 4. Migration order, cheapest risk reduction first

| # | Step | Effort | Risk removed | Needs |
|---|---|---|---|---|
| **1** | **`git bundle create <OneDrive>\nsc-<date>.bundle --all` for the game repo, then one per review clone holding an unmerged fix branch.** Creates a file, changes nothing in the repo | **Minutes** | **All 133 local-only branches and the finished fix branches** | OneDrive folder exists on this machine. Vincent's go, since the bundle is the whole repo history going to his cloud |
| 2 | Zip `C:\NSC\nsc-*.md`, `CLAUDE.md`, `agent-state\`, `ger-tools`, `viewer-tools` to the same folder | Minutes | Docs and tools (single-digit MB) | Eyeball for tokens first |
| 3 | Vincent creates three private repos: `NoSafeCircle-backup`, `nsc-ops`, `nsc-reports` | 10 min | — | Vincent only |
| 4 | Secret scan, then `git init` the two archive repos in place, first push | 1–2 h | Docs, agent-state, reports get history and an off-machine copy | Release Agent + go |
| 5 | Backup script + hidden 15-minute scheduled task (branches, clone hub, archive repos) | One fix branch | Closes the window to 15 min for good | Q2 standing go |
| 6 | restic (or chosen tool) snapshots of `.assistant-control` | Half a day | The 1.5 GB | Q4 |
| 7 | Port `ger-tools` and `viewer-tools` into the game repo with tests; delete nothing until merged | Already queued | Tools get history; `.bak.py` retired | Normal review + Game Agent |
| 8 | Checkpoint ledger hooks (C1–C8) | One fix branch | Reset points exist when needed | Review with `model: fable` (locking code) |
| 9 | `undo-task` on top of `reset_task.py`, proven on a gauntlet source first | One fix branch | The one-call undo | Q3 |

Steps 1–2 remove most of today's exposure this afternoon. Steps 8–9 are what deliver "undo with
one function call".

---

## 5. Out of scope, and what stays at risk

- **The run in flight.** Uncommitted work in a running task checkout is lost with the drive: up to
  one hour of provider spend.
- **Up to 24 h of run logs**, 1 h of records, 15 min of commits — the windows above, not zero.
- **Unity `Library`, Docker images and volumes, Python environments:** rebuildable, not backed up.
- **Provider logins, GitHub credentials, PixelLab account:** deliberately never in a repo. A stolen
  machine means rotating them; that is a checklist for the Documentation Agent, not this design.
- **Machine rebuild.** This design saves the work, not the workstation. Restoring onto a new
  machine is a separate runbook.
- **Scratch folders** under `C:\NSC` and `C:\nscrev` (hundreds of test and review directories):
  treated as disposable, except unmerged fix branches, which the clone hub captures.
- **PixelLab-side assets** are on PixelLab's servers; local art files are covered only if they
  are committed or under `reports`.
- **Resume between crew roles:** not delivered; C4 and C5 are the finest midway points.
- **GitHub itself being lost**, or the GitHub account compromised: the OneDrive bundle from step 1,
  refreshed weekly, is the second copy.
- **Things already pushed or spent** stay pushed and spent.

---

## 6. Open questions for Vincent (each has a default; "yes to all" works)

| # | Question | Recommended default |
|---|---|---|
| Q1 | Is `github.com/cathode26/NoSafeCircle` public or private? | Whatever it is, all three new repos are **private** and nothing new goes to `origin` |
| Q2 | Standing go for an automatic 15-minute push, limited to the backup remotes and never `origin`? | **Yes.** If no: bundles into OneDrive on the same schedule |
| Q3 | Let `undo-task` run on the live source by replacing the "refuses a source with a remote" guard with "revert-only, never rewrite"; Game Agent or you run `--apply` | **Yes** |
| Q4 | Where do `.assistant-control` snapshots go? | restic, encrypted, to OneDrive now (it is already here); Backblaze B2 later if 1.5 GB plus retention outgrows it |
| Q5 | OK to bundle the whole game repo into OneDrive today (step 1)? | **Yes — do it first** |
| Q6 | Reports repo: keep images (contact sheets, screenshots) in git, or text only? | Keep everything; revisit if it passes 1 GB |
