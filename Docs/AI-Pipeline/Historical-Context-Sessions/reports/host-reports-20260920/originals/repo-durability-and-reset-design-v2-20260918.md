# Durable storage and easy reset for the No Safe Circle workspace — v2

Decision document, 2026-09-18, round 2. Pipeline Maintainer. Design only: nothing here has been
built, no repository was created, nothing was pushed, nothing was deleted. Supersedes
`repo-durability-and-reset-design-20260918.md` (v1). Review answered:
`repo-durability-and-reset-review-20260918.md` (FIX FIRST, 9 blocking). Base: `main` = `255951482`.

**The short answer**

- **Shape unchanged (D3):** one reset repo (the game repo, tools move into it) plus private archive
  repos that never take part in a reset. v2 adds two archive repos the facts force:
  `nsc-control` (D1) and `nsc-home` (W1). Five private repos, one backup job, one status line.
- **`.assistant-control` goes in git (D1); restic is gone.** Whitelist only. Every log is kept (D2).
- **No `.git` appears anywhere new (W6).** Every archive repo keeps its git dir under
  `C:\nscrev\backup\git\` and is driven only by the backup job with explicit
  `--git-dir`/`--work-tree`.
- **The undo half is rebuilt.** Undo-edit is a forward revision, undo-create is a disposition
  change, undo-complete hooks the main-write path tasks really take, and "I know nothing about
  this task" is a non-zero refusal. It is a new module, four fix branches, not one.
- **A backup is only counted when it is verified and its age is visible.** Green requires
  `ls-remote` sha equality, zero skipped files, and a passed restore drill.
- **Still do this first, today:** the `git bundle --all` into OneDrive. It has **not** been done
  yet (no bundle in `C:\Users\VincentLiguori\OneDrive` as of this writing).

## What changed from v1 and why

| Finding | v1 said | v2 says | Where |
|---|---|---|---|
| **B1** | C7 hooks `review.py` "status becomes integrated"; no checkpoints = exit 0 "nothing to undo" | Completion hook is `main-write end` (the journal protocol every main writer already uses: 118 STARTs live — GER 97, Game Agent 11, Documentation 9) plus the three pipeline commands. Empty ledger + `main` names the task or a contract exists = **exit 2, refusal**. Pre-ledger tasks have no one-call undo, said plainly | §3.2, §3.3, §5 |
| **B2** | Revert the revision commit, compare policy hash with the checkpoint's stored hash | No contract commit is ever reverted. After the forward revision: recompute `sha256(Tasks/NSC-###.yaml)` from the file, compare with the policy entry, run real `taskcontrol validate`. A forward revision touches one task by construction, so multi-task commits (`36b629f73`) cannot delete a sibling | §3.3 |
| **B3** | `git revert` of the contract commit, refused on path overlap (88 of 104 real commits) | **Reviewer's fix adopted.** Undo-edit = revision N+1 with revision N−1's content through `contract_commit.py`. Undo-create = `contract_disposition: cancelled`. No overlap rule needed. Cost to "start midway" worked through in §3.5 | §3.3, §3.5 |
| **B4** | "Extends `reset_task.py`, which already has the hard parts"; one fix branch; Q3 names one guard | New module `undo_task.py`. Borrows the refusal list and the journal pattern only. `reset_task.py` is left untouched for gauntlet replays. Real fields used: `source_commit`, `integration.source_before`. Step 9 re-estimated as four branches. Q3 restated to cover all three guards | §3.3, §4, §6 |
| **B5** | Prints `dispatchable: true/false` from "the four gates in dry-run form" | Phase 1 prints per-gate lines and `dispatchable: unknown (scope, reserve not checked)`. `true` is only printable after a read-only `explain` exists on all four gates (proposed separately) | §3.3 |
| **B6** | Task checkouts "nightly"; candidates had a 24 h window | The hub `git fetch`es read-only from every task checkout and every `.sync-*` staging clone under every live root, every 15 min, and verifies each record's candidate sha is in the hub | §2 |
| **B7** | `+refs/heads/*:refs/heads/*` | No `+`. `refs/*:refs/*` minus `refs/remotes/*`. A non-fast-forward writes `refs/history/<ref>/<utc>` for the old tip first, so the backup can never lose a good tip to a botched rebase | §2 |
| **B8** | Plain `sk-` grep; a hit is advisory and the file is silently skipped | Anchored patterns plus gitleaks. A skipped file makes the run **not green**. Every push verified by `ls-remote`. Backup age shown in the viewer header, red when stale. Restore drill is part of "done" | §2 |
| **B9** | restic password unspecified | **Moot under D1:** there is no restic, no snapshot tool and no password. v1 Q4 and migration step 6 are deleted | — |
| W1 | Agent definitions "in `nsc-ops` at `C:\NSC`" (they are not under `C:\NSC`) | New `nsc-home` repo over `C:\Users\VincentLiguori\.claude` (agents, memory, skills, settings). Admissions registry and the scheduled-task definition are copied in, because git refuses paths inside a `.git`. All 80 top-level `.md`, not only `nsc-*.md` | §1, §2 |
| W2 | Step 2 zips two tool folders once; port "already queued" | All six tool folders (72 `.py`) are tracked from step 4 on, scripts only, and each is removed as it is ported | §1, §4 |
| W3 | C3 listed, no undo designed | **C3 is not undoable in phase 1.** The command refuses and names the forward alternative | §3.3 |
| W4 | "Atomic replace, so a snapshot is never torn" | True for records only. Stated as a property of the commits (§2.1); undo never reads a sweep commit | §2.1 |
| W5 | "`<checkout-root>\.assistant-control`" as if one | Roots are enumerated by `project.json` on every run and printed. Four roots point at the live source today | §2.2 |
| W6 | `git init` in place at `C:\NSC` | Git dirs live outside the trees; decision needed (Q7), default yes | §1 |
| W7 | Midway creates `assistant/NSC-###-resume-<n>` | Dropped: `publication.py:194` refuses any branch other than `assistant/{task_id}`. The old tip is kept under `refs/archive/` instead | §3.5 |
| m1 | `account-cache.json` holds credentials | Withdrawn; it is one email and a timestamp. Run folders still stay out of the repos (403 entries of prompts and outputs) | §2.4 |
| v1 claim | "`main_write.py` was ported into the game repo in G15b" | Wrong. It was ported into `C:\nscrev\ger-tools`; no ref of the game repo contains it. It moves into the repo with step 7 | §3.2 |

**New facts found this round, not in the review:**

1. **The pipeline itself writes full Unity clones inside `.assistant-control`.**
   `source_update.py:366`: `staging = checkouts.records / f".sync-{task_id}-{operation_slug}"`,
   then `git clone`, retained on failure. `NoSafeCircle-Game-Checkouts-3\.assistant-control`
   holds **four** of them today (`.sync-NSC-045…048`, most of that root's 204 MB). So "exactly one
   stray-shape folder existed" is true of the main root only, and the whitelist is not just
   prevention: a blacklist would commit the next failed sync.
2. **24 `.bundle` files sit at the top of `C:\NSC`** (most of the 214 MB of non-md files). They
   may hold commits that exist nowhere else. The hub fetches from each (§2).
3. Record counts: the main root has 23 task records (`NSC-###.json`) and 37 `NSC-*.json` files in
   all; the review's "37 records" counts the second.

---

## 1. Recommended repo shape

Decision rule and options table A–D: **unchanged (D3).** Design D stands: only the game repo ever
takes part in a reset, so no sha tuple is needed.

What changes is the list of archive repos and how they are held.

**Every archive repo uses an external git dir (W6).** `git --git-dir=C:\nscrev\backup\git\<name>.git
--work-tree=<root>`, run only by the backup job. Consequences:

| Property | Result |
|---|---|
| `git -C C:/NSC rev-parse` | Still fails, as today. A stray `git add -A` in a scratch folder still has no repo to stage against |
| Several repos over one tree | Allowed: `nsc-ops` and `nsc-control` both use work-tree `C:\NSC` with different whitelists |
| Where the whitelist lives | `core.excludesFile` per git dir, generated by the job from one config file. No `.gitignore` is written into `C:\NSC`, a control folder or `.claude` |
| Commands the job may run | `add`, `commit`, `push`, `fetch` (hub only), `ls-remote`, `status`, `rev-parse`. **Never** `clean`, `reset`, `checkout`, `restore`, `stash`: with a work-tree this wide any of them could destroy scratch work |
| Restore | Always `git clone` from the remote into a new folder, then copy. Never a checkout over the live tree |

What goes where:

| Repo (all private) | Work-tree | Whitelist | Size today | In a task reset? |
|---|---|---|---|---|
| Game repo + remote `NoSafeCircle-backup` | `C:\NSC\NSC\NoSafeCircle` | `refs/*` minus `refs/remotes/*`, plus hub refs (§2) | — | **Yes, the only one** |
| `nsc-ops` | `C:\NSC` | `/*.md` (all 80, not only `nsc-*.md`), `/agent-state/`, top-level `*.py *.ps1 *.sh *.json *.txt *.xml *.patch *.diff` under 5 MB | ~3 MB | No |
| `nsc-control` (D1) | `C:\NSC` | Per live root: `/<root>/.assistant-control/` named entries (§2.2); `/NSC/.assistant-control/` (architect journal, `recovery\`) | 60 MB raw ≈ 12 MB packed | No (§3.1) |
| `nsc-reports` | `C:\nscrev` | `/reports/`; **interim:** scripts of `ger-tools`, `job-tools`, `claude-jobs`, `viewer-tools`, `astra`, `session-tools` (no run folders); `/backup/config/`, `/backup/copy-in/` | 133 MB + ~5 MB | No |
| `nsc-home` (W1) | `C:\Users\VincentLiguori\.claude` | `/agents/` (14 files, 100 KB), `/projects/C--NSC/memory/` (108 files, 708 KB), `/skills/` (8.3 MB), `/settings.json`. **Never** credentials files: the whitelist makes that the default | ~9 MB | No |

- **Tools still belong in the game repo (D3).** `nsc-reports` holds them only until each is ported;
  the port commit removes the folder from the whitelist config.
- **Copy-in, because git refuses any path containing `.git`:**
  `.git\assistant-control-admissions.json` (5,118 bytes) and the exported scheduled-task XML are
  copied by the job (read, then atomic write) into `C:\nscrev\backup\copy-in\` each run.
- **The 24 top-level `.bundle` files and 1 `.tar`** are not committed as blobs (they would bloat
  `nsc-ops` to 200+ MB for data git already stores well). The hub fetches each bundle into
  `refs/backup/bundles/<name>/*`, which costs only the commits the game repo does not already have.
- **Why `nsc-home` is a repo and not a copy-in:** a bad agent-definition edit is then undone in
  place with one revert (§3.4), and no stale second copy of the fleet's agents exists to confuse a
  session. Cost: one more private repo.

---

## 2. What makes it durable

All remotes **private**; nothing new goes to `origin` (Q1 unchanged).

| Asset | Off-machine copy | Cadence | Worst-case loss |
|---|---|---|---|
| Game `main`, 141 branches, **108 `refs/archive`, 5 `refs/trial`, 3 `refs/integration`, stash** | `NoSafeCircle-backup`, refspec `refs/*:refs/*` and `^refs/remotes/*` (git 2.45.1 here supports negative refspecs), **no `+`, no `--prune`, no `--mirror`** | 15 min, and on every checkpoint poke (§2.1) | 15 min |
| **Candidate commits in task checkouts** (B6) — live: NSC-007 `ce1e22832`, NSC-032 `622ac7630`, NSC-043 `debc55ee8` (approved), none in the source repo's objects | Hub fetches read-only from every `<root>\NSC-###` (30 in the main root) and every `<root>\.assistant-control\.sync-*` into `refs/backup/checkouts/<root>/<task>/*`; hub is pushed to the same remote | 15 min | **15 min** (was 24 h) |
| Fix branches in `C:\nscrev\*` clones | Hub, `refs/backup/clones/<clone>/*`. Clones stay push-DISABLED; fetch is read-only on them | 15 min | 15 min |
| `nsc-ops`, `nsc-reports`, `nsc-home` | Private GitHub repos; auto-commit, push, verify | 15 min | 15 min |
| `nsc-control`: records, journal, ledger, **all logs** (D2) | Private GitHub repo | 15 min sweep + checkpoint poke | 15 min; tail of an open log may be cut (§2.1) |
| Uncommitted work inside a running task checkout | None | — | The run in flight: up to 60 min of provider spend |

**Headline: 15 minutes for anything committed or written to a record or log, candidates
included — and only while the backup-age line is green (§2.3).** The run in flight is still
uncovered.

**Non-fast-forward rule (B7), used for both the push and the hub fetch.** Per ref: try the plain
update. If git rejects it as non-fast-forward, first write the *old* tip to
`refs/history/<ref>/<utc>` on the destination, then update the ref. The old commits stay
reachable, so a botched rebase or `reset --hard` that the job faithfully copies can still be
undone from the backup. Branches deleted locally are never deleted remotely.

### 2.1 Liveness of `nsc-control` — the surviving objection (D1)

**Answer: both a timer and checkpoint boundaries, with one committer, and the consistency never
comes from the commit.**

| Piece | Who, when | Lock |
|---|---|---|
| **Ledger entry** (§3.2) | The pipeline command that performs the mutation, at the end of its locked section | **Inside the lock it already holds.** It embeds its own copy of the record and its hashes, so it is self-consistent whatever git does later |
| **Checkpoint poke** | Same command, after releasing the lock: `schtasks /run /tn NSC-Backup` with `CREATE_NO_WINDOW`. Fire and forget; a failure is logged and never fails the command | None |
| **Sweep** | The scheduled task, every 15 min | None |
| **The only committer** | The backup job. Task Scheduler's "do not start a new instance" makes it single, so there is no `index.lock` race and no git call inside any pipeline lock | Its own job lock only |

Why not commit inside the pipeline lock: it puts git, the network-free but slow `add` of 500+
files, and a new failure mode into the locked section of identity and locking code, to buy a
property undo does not need.

| A commit taken mid-run **is** good for | It is **not** good for |
|---|---|
| Disaster restore: every record is whole (`write_record` = temp, `fsync`, `os.replace`) | A reset target. `undo-task` **never reads a commit of `nsc-control`**; it reads ledger entries and verifies their sha256 |
| History of the journal, the ledger, controller state and scope plans | Proving a cross-file state: the record, the decomposition record and the checkout `.git` may be from different moments |
| Every log kept off-machine (D2) | The tail of a file being written: `.jsonl` and `.log` are appended, and `run_crew.py` writes `crew_result.json`, handoff files and the audit artifact with plain `write_text` (W4). The next sweep completes them |
| Audit: "what did the fleet look like around 14:15" | Restoring a worker, lease or reservation. Those are never restored, only proven released (unchanged from v1 §3.1) |

### 2.2 Which roots get a repo (W5) and the whitelist (D1)

Roots are found by `project.json`, never by name. Of 85 `.assistant-control` folders under
`C:\NSC`, those whose `source` is the live repo today:

| Root | Task records | Size | Last write | In `nsc-control` |
|---|---|---|---|---|
| `NoSafeCircle-AssistantCheckouts` | 23 | 60 MB | 2026-09-18 | Yes |
| `NoSafeCircle-Game-Checkouts-3` | 6 | 204 MB, of which four `.sync-*` Unity clones | 2026-09-13 | Yes; `.sync-*` excluded, their commits go to the hub |
| `NoSafeCircle-Game-Checkouts-2` | 1 | 91 KB | 2026-09-13 | Yes |
| `NoSafeCircle-Multiscene-Checkouts` | 1 | 87 KB | 2026-09-12 | Yes |
| 6 roots on other sources (`Sorting-Source`, `TenTaskFinalIntegration-*`) and ~75 gauntlet roots | — | — | — | No: not the live game. Listed once, by count, in the run output |

One repo covers all four: they share the work-tree `C:\NSC`. **Every run prints the root list.**
A root whose `project.json` names the live source but is not in the whitelist makes the run not
green.

Whitelist rules inside a root:

| Rule | Detail |
|---|---|
| Ignore everything, then allow by name | Top-level files by pattern: `NSC-*.json`, `*.json`, `*.jsonl`, `*.md`, `*.log`, `*.ps1`, `*.py`. Folders by **exact name**: `decomposition-runs`, `worker-runs`, `viewer-logs`, `operator-logs`, `operator-prompts`, `outputs`, `candidate-receipts`, `checkpoints`, `graph-crew`, `graph-scopes`, `decomposition-launch`, `decomposition-pool`, `materialization-recovery`, `materialization-policy-recovery`, `art-registration`, `viewer`, `.scope-state`, and the eight dated review and builder-log folders that exist today, each by full name |
| No name patterns for folders | `nsc-032-unity-builder-*` (logs, under 1 MB) and the deleted `nsc074-unity-validation-*` (a 1.4 GB checkout) have the same shape of name. A pattern that admits one admits the other |
| Never allowed | `*.lock`, `.sync-*`, anything containing `.git`, or `Assets` beside `ProjectSettings` |
| Second guard at add time | A whitelisted folder that gains a file over 50 MB, or a nested `.git`, is not added; the run goes red and names it |
| An unknown top-level entry | Not committed. The run is **amber**, the status names it and prints the one config line that would admit it. Backup-side only: no task, worker or command is ever blocked by it |

Size (D1, measured): 60 MB raw ≈ 12 MB packed today. **Year one at the current hot pace:
~4.4 GB raw on disk, ~0.9 GB packed in git.** Nothing is pruned (D2). Retention *options for
later*, none of which deletes a log: (a) yearly rollover — freeze `nsc-control-2026` read-only and
start `nsc-control-2027` from the then-current tree; (b) move to a storage-backed remote if one
repo passes 2 GB; (c) do nothing until the measured number says otherwise. Default: (c), recheck
at 500 MB packed.

### 2.3 "Green" means verified (B8)

| Check | Rule |
|---|---|
| Secret scan | gitleaks plus anchored patterns only: `sk-ant-[A-Za-z0-9_-]{20,}`, `ghp_[A-Za-z0-9]{30,}`, `github_pat_[A-Za-z0-9_]{30,}`, `gh[osu]_[A-Za-z0-9]{30,}`, PEM headers, and the PixelLab prefix once Vincent supplies it (Q8). The bare `sk-` and `Bearer ` greps are removed: they match "ta**sk-**" in 73 report files including `BOARD.md` |
| A scan hit | That file is not committed, everything else still is, and the run is **red** and names the file. It never blocks a task |
| Any skipped, unknown or oversize path | Run is **not green** (amber), named in the status |
| After every push | `git ls-remote` per target; every local ref sha must equal the remote sha. Only then is `last_verified_utc` written |
| Candidate coverage | For every record with a candidate sha: `git cat-file -e` in the hub. Status shows `candidates 3/3` |
| Status file | `C:\nscrev\backup\status.json`, UTF-8 without BOM, atomic replace: per-target state, `last_verified_utc`, skipped files, unknown entries, roots list, unledgered-commit count (§3.3) |
| Where Vincent sees it | One item in the GauntletView header: `Backup 6 min ✓`, amber with a count, red past 60 min. **The viewer computes the age from `last_verified_utc` itself**, so a dead scheduled task, expired GitHub auth, a sleeping laptop and a rejected push all turn it red with no help from the job |
| Restore drill — part of "done" for step 5 | Clone each remote into a scratch folder under `C:\nscrev`; game repo: run the non-Unity suite and confirm all four ref namespaces arrived (this also proves GitHub accepted `refs/archive` and `refs/history`); `nsc-control`: all records parse and ledger hashes verify; `nsc-home`: 14 agents, 108 memory files. Repeat monthly; the result goes in the status file |

### 2.4 Secrets — measured, not asserted

Zero token-shaped strings across all six tool folders, `claude-jobs`, `codex-jobs`, all 3,913
report files, the 80 docs and `agent-state`, confirmed independently by the reviewer and by the
Pipeline Maintainer. The only hits are copies of the repo's own test fixture
(`ghs_faketokenvalue`), already on `origin`. Email addresses in 74 report files and 10 docs are
why every repo is private. **Not yet covered, so gitleaks still runs before every first push:**
binary files, the PixelLab token prefix, and the two trees this round adds — `.claude`
(`settings.json`, `skills\`) and the four control roots.

Repo settings, Windows process rules and lanes: **unchanged**, except that five repos need
creating rather than three, and the standing go (Q2) names five remotes.

---

## 3. The reset design

### 3.1 The hypothesis

**Unchanged in its conclusion** (git is the file half, the ledger is the record half, leases are
never restored), with two corrections:

- "Create and edit are each exactly one commit including the rebind" is **true of the current
  tool only** (since about 2026-09-17), false of history (22 of 92 stale at commit, 13 policy
  entries in separate commits, multi-task commits). v2 does not depend on it: no contract commit
  is reverted.
- The record field is `source_commit` / `integration.source_before`.
  `integration.pre_task_commit` does not exist; it was a local variable in `reset_task.py`.
- `nsc-control` being in git does **not** make it a reset repo. Undo restores a record from a
  ledger entry, never by a git operation in `nsc-control`.

### 3.2 Checkpoints

Ledger location, entry content and "written inside the lock the command already holds":
**unchanged.** Each entry also stores `contract_revision` and `task_contract_sha256` (needed by
§3.5). Changed rows:

| # | Boundary | Hooked into | Change |
|---|---|---|---|
| C1, C2 | Contract created / revised | `contract_commit.py` (today in `C:\nscrev\ger-tools`, in the repo after step 7) | Entry stores the commit that holds this revision's content, so undo-edit can read revision N−1 without guessing |
| C3 | Children applied | `apply-decomposition` | Recorded, **not undoable in phase 1** (W3) |
| C4–C6 | Prepared, candidate, approved | unchanged | — |
| **C7** | **Landed on `main`** | **`main-write end`**, one function `ledger.record_main_range(old_head, new_head, role, operation)`, called from (a) the main-write tool for Game Agent merges, GER contract commits and Documentation Agent writes, and (b) `integrate`, `sync-candidate` and `apply-decomposition`, which share a lock instead of writing journal lines | Was `review.py` only. For every task named in a commit subject in `old..new`, or whose `Tasks/NSC-###.yaml` the range touches, it writes an entry holding the range, each commit sha and, for a merge, the first parent. **No record is required**, because most merged tasks have none |
| C8 | Evidence recorded | `record_delivery` | unchanged |

The main-write protocol already exists (`nsc-main-orchestrator-guide.md` §5) and every role
already writes its START and END lines. v2 makes one command write them
(`python -m Pipeline.AssistantControl main-write start|end`), which removes hand-typing and adds
no step. The ledger call is inside `end`; if it fails, `end` still writes the journal line and
reports the failure.

**Safety net for a merge made by hand without the tool:** `checkpoints`, `undo-task` and the
backup job all run the same read-only scan — first-parent commits on `main` since the ledger
epoch that name a task and sit in no ledger range. They are reported as *unledgered*, counted in
the backup status, and they turn an undo into a refusal (§3.3). Advisory everywhere else.

Not a boundary (crew roles, heartbeats, overlays): **unchanged.**

### 3.3 The command

CLI shape: **unchanged** (`undo-task`, `--apply`, `--to CN`, `checkpoints`). It is a **new module,
`Pipeline/AssistantControl/undo_task.py`** (B4). From `reset_task.py` it takes the refusal list
and the resumable-journal pattern, nothing else. `reset_task.py` keeps all three of its guards and
stays the gauntlet-replay tool. `undo_task.py` never archives a record and never moves a checkout.

| Mutation undone | Files | Record |
|---|---|---|
| **Create** (C1) | Forward revision setting `contract_disposition: cancelled` (an existing value: `current_conformance.py:361`, `apply_graph_delta.py:627`). The file, the policy entry and every sibling created in the same commit stay | Untouched. Refused while a worker is live or an active task depends on it (listed by id) |
| **Edit** (C2) | **Forward revision N+1 whose content is revision N−1**, read with `git show <C2[N−1].commit>:Tasks/NSC-###.yaml`, revision number and provenance set to "undo of revision N", then written by `contract_commit.py --task --revised --reason`, first without `--commit`, then with. The tool rebinds the policy and updates `RESOURCE_GROUPS.yaml` and `WORK_ID_MAP.json` itself. If revision N changed the policy filters, N−1's filters are passed back the same way. **Then:** recompute `sha256` of the file at HEAD, compare with the entry's `task_contract_sha256`, run `taskcontrol validate`. Either failing = non-zero exit naming the mismatch | A checkout prepared against the undone revision is marked for the existing `refresh-prepared` path (§3.5) |
| **Children applied** (C3) | **Refused in phase 1, exit 2:** "C3 is not undoable. Forward alternative: cancel each child with `undo-task <child> --to C0`." `apply_graph_delta`'s own rollback is `reset --hard old_head`, unusable on a pushed `main`, and a revert would land without its committed-graph validation. Phase 2 only if needed: refuse if any child has a record; run the same committed-graph validation on the staged revert | — |
| **Complete** (C7, C8) | Revert exactly the commits the C7 entry lists: `git revert -m 1 <merge>` for a merge, `--no-commit` range for linear commits, plus the C8 evidence commit. Path overlap with later commits from another task = refusal (the rule is right for code and assets; it was only wrong for the shared contract files, which this row never touches) | If a record exists: restored as a merge from the target entry (rules unchanged from v1: never `worker`, leases or reservation; `worker_history` append-only; an `undo` entry appended). If none exists: none is invented |
| **Midway** (`--to CN`) | §3.5 | §3.5 |

Lane: undo-create and undo-edit write a contract, so they run under the GER Agent's or Vincent's
hand; undo-complete moves `main`, so the Game Agent or Vincent. All under main-write START/END.
The tool makes no design decision: it only re-applies content that was already approved once.

**Dispatchable (B5).** Phase 1 output, always this shape, never a bare `true`:

```
prepared_refresh : ok            (worker_state predicates)
worker_launcher  : ok            (worker_state predicates)
scope            : not checked   (cannot be asked without a lease)
reserve          : not checked   (admission.py has no read-only path)
dispatchable     : unknown (scope, reserve not checked)
```

Only `prepared_refresh.py:12` and `worker_launcher.py:28` import the predicates, and none of the
four gates has a dry-run mode. A read-only `explain` on all four is worth having on its own (it
is the four-refusals incident's missing tool) and is proposed as a separate problem entry; when it
ships, this block may print `true`.

**Fails safe** — changed rules only:

| Situation | v2 behaviour |
|---|---|
| Ledger empty, **and** `main` holds a commit naming the task **or** a contract file exists | **Exit 2.** "NSC-077 is not known to the ledger; undo cannot act. `main` holds 1 commit naming it: `9ffa77847`." Lists the commits so the Game Agent can revert by hand |
| Unledgered commits exist for this task after its last entry | Exit 2, same message |
| Ledger empty and nothing anywhere names the task | Exit 0, "unknown task id, nothing to undo" |
| Validation or hash recompute fails after a forward revision | Non-zero; says the fix is another revision, never a rewrite |
| Live worker, reservation, controller, dirty tree, dependents, journal from another undo | Unchanged: refuse, mutate nothing, name the existing command |

**Tasks completed before the ledger ships have no one-call undo.** That is 44 merge commits
naming a task today, including NSC-077, 075, 074, 073, 093, 017 and 053 (no record at all) and
NSC-063 (merged while its record says `prepared`). For them the command refuses and lists the
commits. A backfill that writes C7 entries from `git log` is possible later; it is not promised
here.

Cannot be undone (push to `origin`, provider spend, PRs, published builds, Unity `Library`):
**unchanged.**

### 3.4 Fleet-level mistakes

**Unchanged**, with three corrections: an agent-definition or memory edit is reverted in
**`nsc-home`**, not `nsc-ops`; a revert in any auto-commit repo may need a range, since a
15-minute sweep can catch a half-written doc (m5); and until a tool is ported (step 7), a bad
edit to it is reverted in `nsc-reports`, and "which tool commit wrote this contract" has nothing
to record.

### 3.5 What forward revisions mean for "start midway" (B3)

`main` never rewinds for a contract change, so the contract is no longer part of what "go back
to CN" restores. The consequences, stated once:

| Fact | Consequence |
|---|---|
| Revision N+1 has revision N−1's content but its own revision number, so its sha256 differs from N−1's | A checkout or candidate bound to N−1's hash is **not** valid for N+1 |
| Every C4–C6 entry stores `task_contract_sha256` | `--to CN` is refused when CN's contract hash is not the current one: "contract changed since C5; resume from C4 by re-preparing" |
| So | **Midway resume works only inside the current contract revision. An undo-edit always costs a re-prepare and a crew run.** That is the honest price of B3's fix; the alternative was an undo that refused 88 times in 104 |
| Not verified | `revisions.py` and the candidate-receipt revision path may already carry a candidate across a content-identical revision. If so, phase 2 can reuse it. Not assumed here |

Targets, within one contract revision:

| `--to` | Files | Record | Holds as a resume point? |
|---|---|---|---|
| C4 prepared | Old branch tip kept as `refs/archive/assistant/NSC-###/<utc>` in the checkout (and fetched by the hub); then the existing `refresh-prepared` path. The branch name stays `assistant/NSC-###` | status `prepared`; candidate, approval, integration fields moved to history | Yes: re-runs the crew |
| C5 candidate | `main` untouched. Candidate verified with `git cat-file -e` in the checkout; if missing, fetched back from the hub ref; if in neither, refused | approval and integration fields cleared | Yes: re-review without paying for the crew again. Protected by B6's fix |
| C6 approved | Only when nothing landed on `main` | unchanged | **Only then.** After an undo-complete, `main` has moved, so the candidate needs `sync-candidate`, which by rule resets approvals. It lands at C5 and says so |

---

## 4. Migration order, cheapest risk reduction first

| # | Step | Effort | Risk removed | Needs |
|---|---|---|---|---|
| **1** | **`git bundle create <OneDrive>\nsc-<date>.bundle --all`** for the game repo, then one per review clone with an unmerged fix branch. **Amendment:** afterwards confirm OneDrive shows each file as *synced*, not pending. Note: unencrypted full history in a synced folder; fine against a dead drive, against theft it relies on BitLocker | Minutes | All 133 local-only branches, all 117 non-branch refs, the finished fix branches. **Not** candidates in task checkouts (step 5) | Vincent's go (Q5). **Not done yet** |
| 2 | Zip to the same folder: the 80 top-level `.md`, `agent-state\`, **all six tool folders** (scripts only), `.claude\agents`, `.claude\projects\C--NSC\memory`, the admissions registry. Confirm *synced* | Minutes | Docs, tools, agents, memory (under 20 MB) | The measured scan in §2.4 already covers all of it except `.claude`; eyeball `settings.json` |
| 3 | Create five private repos: `NoSafeCircle-backup`, `nsc-ops`, `nsc-control`, `nsc-reports`, `nsc-home` | 10 min | — | Vincent, or his go to the Release Agent |
| 4 | gitleaks over each tree, then create the five external git dirs, first commit, first push, `ls-remote` verify. Tools are protected from here on (W2) | 2–3 h | Docs, agent-state, reports, tools, agents, memory, **records and logs** get history and an off-machine copy | Release Agent + go |
| 5 | Backup job + hidden 15-minute scheduled task: root enumeration, whitelists, hub fetch (checkouts, `.sync-*`, clones, bundles), no-`+` push with `refs/history`, verify, `status.json`, viewer header item, **restore drill** | Two fix branches (job; viewer item) | Closes the window to 15 min, candidates included, and makes a stopped backup visible | Q2 standing go; review with `model: fable` (provider-adjacent, credentials in use) |
| ~~6~~ | ~~restic snapshots~~ | — | **Deleted (D1)** | — |
| 7 | Port the six tool folders into the game repo with tests, `contract_commit.py` and `main_write.py` first. Remove each from the `nsc-reports` whitelist as it lands | **Weeks** (72 `.py`), one folder per branch | Tools get real history and review; `.bak.py` retired | Normal review + Game Agent |
| 8 | Ledger: entry writer, C1–C8 hooks, `main-write start|end` command, `record_main_range`, unledgered scan, checkpoint poke | Two fix branches | Reset points exist, on the path tasks really take | Step 7's first two tools; `model: fable` (locking code) |
| 9a | `undo_task.py`: `checkpoints`, dry-run plan, every refusal, exit codes. Mutates nothing | One branch | The false green (B1) is closed before any undo can run | — |
| 9b | Undo-complete: revert from a C7 entry incl. `-m 1`, record merge-restore | One branch | One-call undo of a landed task | Q3; proven on a gauntlet source first |
| 9c | Undo-edit and undo-create as forward revisions | One branch | One-call undo of a contract change | GER Agent review of the contract rules it must obey (key set, invariant fields, revision numbering, provenance) |
| 9d | Midway `--to C4/C5` | One branch | Start midway | W7 test: every reader of `record["branch"]` |

Steps 1–2 remain the only thing protecting anything today. Steps 8–9 were "two fix branches" in
v1; they are **six**.

---

## 5. Out of scope, and what stays at risk

| Still at risk | Why, and how large |
|---|---|
| The run in flight | Uncommitted work in a running task checkout: up to 60 min of provider spend |
| **Candidate commits** | 15 min once step 5 runs. **Until then, on this drive only** — NSC-007, NSC-032 and approved NSC-043 right now. Step 1 does not cover them |
| **Non-branch refs** (117) | Covered by step 1 and by step 5. Between a step-1 bundle and step 5 they age with the bundle |
| **Agent definitions and memory** | Covered from step 2 (zip) and step 4 (`nsc-home`). Session transcripts (122 project folders under `.claude\projects`) are **not** covered; say if they matter |
| **The admissions registry** | Copied in every 15 min after step 5. It is never restored as state — reservations are only proven released — so the copy is for audit |
| **Every task completed before the ledger exists** | No one-call undo, ever, unless a backfill is built. 44 merge commits today, and every task that lands before step 8 ships |
| **"The backup stopped and nobody noticed"** | Mitigated, not removed: the viewer computes the age itself and goes red. If nobody opens the viewer for a week, nobody sees it. A second surface (a session-start line for the Main Orchestrator) is the Documentation Agent's lane |
| Tail of an open log at sweep time | Completed by the next sweep; lost only if the drive dies in between |
| C3 (children applied) | Not undoable in phase 1 |
| Midway resume across a contract change | Not possible by design (§3.5) |
| A hand merge that skips `main-write` | Reported as unledgered; undo refuses for that task |
| 6 roots on other sources, ~75 gauntlet roots, scratch folders | Treated as disposable; unique commits in their clones reach the hub only if they are task checkouts of a live root |
| GitHub lost or the account compromised | The OneDrive bundle from step 1, refreshed weekly by the job, is the second copy |
| Unity `Library`, Docker images, Python environments, provider logins, machine rebuild, PixelLab-side assets, things already pushed or spent | Unchanged from v1 |

---

## 6. Open questions for Vincent (each has a default; "yes to all" works)

Settled and removed: v1 Q4 (restic destination) by D1. Log retention by D2. Repo shape by D3.

| # | Question | Recommended default |
|---|---|---|
| Q1 | Is `github.com/cathode26/NoSafeCircle` public or private? (`gh repo view --json visibility` answers it) | Either way, all five new repos are **private** and nothing new goes to `origin` |
| Q2 | Standing go for the automatic 15-minute push, limited to the **five** backup remotes, never `origin`? | **Yes.** If no: bundles into OneDrive on the same schedule, same status line |
| Q3 | **Restated (B4).** OK for a *new* command, `undo-task`, to make **revert commits on the live, pushed `main`**? It is not `reset_task.py` with a guard relaxed: that file keeps all three of its guards (refuses a source with a remote; refuses any branch outside `gauntlet-replay/`; refuses `status != integrated`) and stays gauntlet-only. The new command instead: allows a remote but only ever adds commits, never rewrites; allows branch `main` only on the canonical source under main-write START/END; accepts the statuses each target needs. `--apply` by the Game Agent or you only | **Yes**, after 9a and a gauntlet proof |
| Q5 | OK to bundle the whole game repo into OneDrive today (step 1)? | **Yes — do it first; it has not been done** |
| Q6 | Reports repo: keep images in git, or text only? | Keep everything. The job checks every file against GitHub's 100 MB limit (largest today is under 20 MB) and goes amber instead of failing the push |
| Q7 | **New (W6).** Keep every archive repo's git dir outside its tree (`C:\nscrev\backup\git\`), driven only by the job, so no `.git` ever appears in `C:\NSC`, a control folder or `.claude`? | **Yes.** Cost: you cannot `cd C:\NSC && git log`; the job ships a `nsc-backup log <repo>` wrapper |
| Q8 | **New.** What prefix do PixelLab tokens have, so the scan can anchor on it? | Until answered, gitleaks' generic rules only |
| Q9 | **New (W1).** `nsc-home` as its own repo over `.claude`, or copy the agents and memory into `nsc-ops`? | **Own repo**: reverts happen in place and there is no stale copy |
| Q10 | **New (W1).** All 80 top-level `.md` and the small top-level scripts into `nsc-ops`, and the 24 `.bundle` files into the hub as refs? | **Yes to both** |
| Q11 | **New (D1).** An unknown new folder inside `.assistant-control`: leave it uncommitted and show amber until someone admits it by name (whitelist, as you asked), or auto-admit anything that passes the shape and size guard? | **Amber.** Auto-admit is a blacklist by another name, and the pipeline does write Unity clones there (`.sync-*`) |
