# Pipeline Maintainer handoff — 2026-09-18 night

Successor to `nsc-handoff-20260918-evening-pipeline-maintainer.md`. **The authority for what is
next is `C:\NSC\agent-state\pipeline-maintainer-todo.md`**, not this file. This is why things are
where they are.

---

## 0. What this session actually was

It started as "durability and reset design" and became, at Vincent's direction, most of a disk
cleanup as well. Two threads ran all evening and both are unfinished in different ways.

**Nothing was merged, nothing was pushed, and the only deletion was Vincent's own.**

---

## 1. The state on disk, verified not assumed

### Tools moved — done, verified

Six folders moved `C:\nscrev\<x>` → `C:\NSC\tools\<y>` (`ger`, `jobs`, `viewer`, `astra`,
`session`, `art`), **2 MB total**, with a **directory junction left at every old path**. Verified
with `Get-Item ... LinkType`: all six report `Junction` with correct targets, and
`propagation_check.py`, `nsc_viewer.py`, `apply_contract.py`, `ask_astra.py` and
`nsc_session_digest.py` all resolve through both spellings.

**The junctions are load-bearing** until every reference is rewritten. The Cleanup Agent has been
warned in writing that a recursive walk following them descends into `C:\NSC\tools`.

**Doc sweep done and independently re-counted:** the Documentation Agent rewrote 67 references
across 19 files; I did 8 more in my own two state files. **0 stale references remain in live docs
or agent definitions.** ~55 remain deliberately, in frozen dated handoffs and other agents' state
files.

**`ger-contract-revisions-20260916` did NOT move** — 271 MB, holds the *only* copies of
`new_task_commit.py`, `policy_entry_commit.py` and `verify_filter.py`, and is the GER Agent's live
working area. So the tools genuinely live in two places. Deliberate; recorded in the runbook.

**Not yet done: 13 hardcoded `C:\nscrev` path references inside nine live tools.** They still work
through the junctions. `run_job.py` (3), `ask_astra.py` (4), `nsc_watch.py` (2),
`nsc_session_digest.py` (2), `main_write.py` (1), `nsc_viewer.py` (1). This is the first small
job for a successor.

### Quarantine — 45 directories, reversible

`C:\NSC-History-20260918`, review date **2026-10-09**. `MOVE-TO-HISTORY.ps1` (ran),
`MOVE-STRAGGLERS.ps1`, `MOVE-NSCREV.ps1` (dry-run only), `RESTORE.ps1`, `MANIFEST.json`
(45 entries, **UTF-8 without BOM**), `RESTORES.md` (created empty on purpose).

A 46th item, `nsc074-unity-validation-f7cb0f47` (1,477 MB), was recovered from the Recycle Bin at
Vincent's request and has its own `PROVENANCE-*.md`.

**`.assistant-control` went 1.5 GB → 60 MB.** 96% of it was that one stray Unity validation
checkout. The irreplaceable core is **320 KB of task records plus a 184 KB journal**.

---

## 2. Decisions Vincent made tonight

- **`.assistant-control` goes in git.** Measured: 60 MB raw, logs compress **5.1×**, so ~12 MB
  stored, ~2.4 MB/day packed. **This deletes v1's entire restic proposal** (Q4, step 6, B9).
- **Keep every log.** No pruning proposals.
- **Quarantine, not deletion**, with the rule that makes the deadline safe: *"if we go into the
  history folder and find something of value, it needs to come out."* Nothing of value may live
  there, so whatever remains on 2026-10-09 is junk by construction.
- **Cleanup Agent: reversed to STAFFED** (it was declined earlier the same day). It exists, it is
  briefed, and branch/worktree triage and disk cleanup are now its lane, not mine.
- **Tools extraction approved** and executed.
- **Undo must cover create / complete / edit as one call, and must "start midway"** — restore to
  an intermediate checkpoint and resume, not only rewind.

---

## 3. The design work — delivered, and the review is what matters

| document | state |
|---|---|
| `repo-durability-and-reset-design-20260918.md` | v1 |
| `repo-durability-and-reset-review-20260918.md` | **FIX FIRST, 9 blocking**, all reproduced from live data |
| `repo-durability-and-reset-design-v2-20260918.md` | claims 9 of 9 closed; **unreviewed** |
| `repo-topology-20260918.md` | running at session end — answers "one repo or two" |
| `state-and-plan-review-20260918.md` | running at session end — adversarial review of the state *and* the plan |

**The four findings worth carrying forward**, because they will otherwise be rediscovered:

- **B1:** the undo completion hook was on `review.py` "status becomes `integrated`", but only **2**
  live records are integrated against **44 merge commits naming a task**. `undo-task NSC-077
  --apply` would exit 0 having done nothing. The hook belongs on the merge path.
- **B3:** **88 of 104** contract commits already have a later commit touching their paths, because
  contract commits also touch `RESOURCE_GROUPS.yaml`, `WORK_ID_MAP.json` and the policy. A
  revert-based undo refuses. **Fix: undo-edit becomes a forward revision** — N+1 with the content
  of N−1 — through the tool that already rebinds the policy.
- **B4:** `reset_task.py` is not a base to extend. It **archives** records rather than restoring
  them and moves the task checkout away, destroying what a C5 resume needs.
  `integration.pre_task_commit` is a local variable, not a record field.
- **W1:** **agent definitions (14 files) and agent memory (108 files) live under
  `~\.claude\`, outside `C:\NSC` entirely.** No design covered them until the topology brief.
  Machine stolen → the fleet restores with rules but no agents and no memory.

**On "would multiple repos make undo easier?"** — the coupling that blocks undo is **task-to-task,
not content-type-to-content-type**. Splitting contracts into their own repo moves
`RESOURCE_GROUPS.yaml` with them, so NSC-015 still blocks NSC-007's undo. Split repos for
durability and blast radius; solve undo with forward revisions.

---

## 4. What is still not in a repo — the thing this session did not fix

Tonight reorganised. It did not protect. **Nothing was put under version control and nothing went
off the machine.**

| item | size |
|---|---|
| `C:\nscrev\reports` | 133 MB / 3,936 files — includes **uncommitted art** whose `sha256` is pinned by committed contracts |
| `ger-contract-revisions-20260916` | 271 MB, only-copy tools |
| `.assistant-control` | 60 MB (320 KB of it irreplaceable) |
| `C:\NSC\tools` | 3 MB / 192 files |
| `C:\NSC\*.md` | 1.3 MB / 80 files |
| `C:\NSC\agent-state` | 1 MB / 19 files |
| `~\.claude\agents`, `~\.claude\...\memory` | 14 + 108 files, outside `C:\NSC` |

**The `git bundle --all` into OneDrive was recommended five times and never run.** It remains the
cheapest thing on the list: minutes, no push, no new repo, and it covers the game repo's 133
off-main branches.

---

## 5. Lessons this session paid for

- **Asking the seven role agents beat all three delegated inventory jobs.** It found `art-tools`
  (only copy of an accepted toolkit, `Pipeline/ArtReview` greps zero on main) and
  `ger-contract-revisions-20260916` (only copies of three GER committers). Neither is
  distinguishable from junk by any rule.
- **Two of three delegated inventory jobs exited 0 having produced nothing**, each spawning a
  background scan and dying — despite the brief forbidding exactly that in bold. **Check for the
  artifact; never read exit 0 as success.** The instruction is not enough; structure the job so it
  cannot do that.
- **My own scanning contaminated the evidence.** `git status` rewrites `.git\index`, so an
  inventory pass makes every clone look "modified today". The first dry run kept 142 directories
  on timestamps I had created. **Exclude `\.git\` from any recency test.**
- **`Set-Content -Encoding utf8` emits a BOM on PowerShell 5.1**, which PowerShell reads back fine
  and python and jq choke on. A manifest can look healthy and be unreadable to everything else.
- **`$ErrorActionPreference = 'Stop'` plus native git is a trap.** Git writing to stderr becomes a
  terminating `NativeCommandError`. Three crashes came from this; check `$LASTEXITCODE` instead.
- **Verification can be wrong in the reassuring direction.** I reported the tools move had not run
  when it had: Git Bash's `find -type f` does not traverse Windows junctions, so the moved folder
  looked empty. Twice more a mis-escaped grep reported zero. **When a check says "nothing
  happened", suspect the check.**
- **`C:\nsc*` matches `C:\NSC` on Windows.** Case-insensitive globbing would have moved the entire
  workspace. Guard destructive patterns by exact name.
- Vincent, on being told the tools move would take weeks: *"maybe it didn't know what the
  essential tools were. We know what the tools are."* He was right. Three jobs tried to classify
  201 directories; the real question — *which files do we use?* — was one grep and the answer was
  23 files. **When an analysis is expensive, check whether it is the wrong question.**

---

## 6. First things for a successor

1. **Read the todo file**, not this one, for what is next.
2. **Both Fable jobs' output** — `repo-topology-20260918.md` and
   `state-and-plan-review-20260918.md`. The second reviews the *state of the machine* as well as
   the plan, including whether the quarantine is genuinely reversible (it was asked to restore
   something and put it back). **Read its "what cannot be undone" section first.**
3. **The 13 hardcoded tool paths.** Small, mechanical, and they are the last thing keeping the
   junctions load-bearing.
4. **`fix/mixed-provider-model-env` @ `d79bc26a9`** — verified end to end by the Game Agent,
   waiting only on Vincent's own word in their session.
5. **The decomp part-1 Fable audit**, which Vincent put at the top of the queue this morning and
   which is the one queue item that never got touched all evening.
