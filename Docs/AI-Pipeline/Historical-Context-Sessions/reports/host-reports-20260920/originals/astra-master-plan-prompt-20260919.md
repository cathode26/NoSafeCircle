You are reviewing a pile of design work and producing the plan that replaces it.

Context: a solo developer's Windows game project, "No Safe Circle", built by a fleet of ~9 AI agent
sessions. Over two days the fleet produced several design documents and three adversarial reviews
about storage, cleanup and undo. They partly contradict each other. Nothing has been acted on
except a tools move and a folder quarantine. I want one plan, from you, that I can execute.

Read these before answering. They are on disk and you have read access:

- C:\nscrev\reports\repo-durability-and-reset-design-20260918.md          (v1 design)
- C:\nscrev\reports\repo-durability-and-reset-review-20260918.md          (review of v1: FIX FIRST, 9 blocking)
- C:\nscrev\reports\repo-durability-and-reset-design-v2-20260918.md       (v2, claims all 9 closed, never reviewed)
- C:\nscrev\reports\repo-topology-20260918.md                             (repo topology: "one repo or two", never reviewed)
- C:\nscrev\reports\state-and-plan-review-20260918.md                     (adversarial review of machine state AND plan)
- C:\nscrev\reports\tools-move-review-20260919.md                         (tools move + commit readiness)
- C:\nscrev\reports\handoffs\cleanup-agent-request-20260918-pipeline-maintainer.md
- C:\NSC\nsc-handoff-20260918-night-pipeline-maintainer.md
- C:\NSC\agent-state\pipeline-maintainer-todo.md                          (live queue; see its URGENT section)

## What I actually want

Four outcomes, in one plan:

1. **Clean up everything.** The disk is a mess and I want the project back in order.
2. **Delete what we don't need.** Actually gone, not endlessly quarantined.
3. **Everything that should be in a repo, in a repo.** Off this machine, recoverable.
4. **Undo a task easily.** One command. Covering create / complete / edit, and able to restore to
   an intermediate checkpoint and resume from there, not only rewind to the beginning.

## Measured facts — use these, do not re-derive or estimate

- Game repo `C:\NSC\NSC\NoSafeCircle`: `main` == `origin/main` == `255951482`, pushed to GitHub.
  **The game source is already safe.** Everything below is the scaffolding around it.
- `C:\NSC`: **788 top-level directories** — 277 with their own `.git`, 511 without. 300 top-level files.
- **138 registered git worktrees** on this machine; **79 under `C:\NSC\_worktrees`**, 4 into `C:\nscrev`.
- `C:\nscrev`: 201 top-level directories. 48 are worktrees. **81 branches across 32 clones are
  commits canonical has never seen**; ~13 of those have since been fetched into canonical as refs,
  leaving ~60 historical experiments undecided.
- `.assistant-control`: **60 MB** (was 1.5 GB until a stray Unity checkout was removed). The
  irreplaceable core is **320 KB of task records + a 184 KB journal**. Run logs compress **5.1x**.
  The owner has decided this goes in git and that **every log is kept**.
- `C:\nscrev\reports`: **133 MB, 3,936 files.** Includes **uncommitted art deliverables** (28 fireball
  sprites, 12 enemy death looks) whose **sha256 values are pinned by committed task contracts** —
  they must be preserved byte-for-byte, never re-exported.
- `C:\NSC\tools`: 2.0 MB, 192 files (177 tracked after ignore rules). Moved here on 2026-09-18 from
  `C:\nscrev`, with **directory junctions left at the six old paths** so ~124 absolute-path
  references in guides kept working.
- `C:\nscrev\ger-contract-revisions-20260916`: **271 MB**, live working area, and holds the **only
  copies** of three essential tools (`new_task_commit.py`, `policy_entry_commit.py`, `verify_filter.py`).
- **Agent definitions (14 files) and agent memory (108 files) live under `C:\Users\<user>\.claude\`,
  outside `C:\NSC` entirely.** No design covered them until very recently.
- `C:\NSC-History-20260918`: 45 directories already quarantined, with a manifest and a restore script.
- **Secrets: measured three times, zero.** No token-shaped strings anywhere in the material proposed
  for a repo. A handful of real email addresses. Private repos are sufficient.

## The contested points — the reviews disagree, and I need you to settle them

1. **How many repos?** v2 said 5. The topology document said 4 (game repo unchanged + one new
   `nsc-fleet` + two archives). Another view is that more repos make undo *harder*, because git's
   undo is per-repo and there is no consistent point-in-time across repos without recording a tuple.
2. **Does splitting repos make undo easier?** One argument says no: the coupling that blocks undo is
   **task-to-task, not content-type-to-content-type**. Contract commits also touch shared files
   (`RESOURCE_GROUPS.yaml`, `WORK_ID_MAP.json`, the validation policy), so **88 of 104** contract
   commits already have a later commit on their paths and a revert-based undo refuses. Moving
   contracts to their own repo moves those shared files with them and changes nothing. Is that right?
3. **Junctions and git — reproduced, and it breaks a proposal.** Git walks a junction as an ordinary
   directory on read, but on `checkout`/`reset --hard`/`stash`/`switch` it **deletes the real file
   through the junction and then fails**; in one test an uncommitted edit was destroyed. This kills
   the topology document's plan to link agent definitions and memory into the repo at `C:\NSC\linked\`.
   What should replace it?
4. **`reset_task.py` is not a base to extend**, though v1 assumed it was: it *archives* records rather
   than restoring them, moves the task checkout away (destroying what a mid-point resume needs), and
   `integration.pre_task_commit` is a local variable, not a record field. The undo work was
   re-estimated from 2 fix branches to 6.
5. **The completion hook is on a path real tasks do not take.** Only **2** live task records are
   `integrated`, while **44 merge commits on main name a task**. So `undo-task <id>` would exit 0
   having done nothing for most real tasks.
6. **The quarantine folder is not "junk by construction".** A review found **19 of 28 quarantined
   clones hold branch tips the game repo does not have**, three were moved dirty, and six `.bundle`
   files hold commits found nowhere else. So the "delete it in three weeks if nobody restored
   anything" rule is unsafe as written. What is the right disposal rule?
7. **`git init` at `C:\NSC` is hazardous**: it would capture 511 directories that have no `.git` of
   their own, and the 79 registered worktrees would be recorded as gitlinks with **no content** — a
   backup that reports success and contains nothing. One proposal is a git dir outside the work tree
   driven by a wrapper with a verb allow-list. Is that sound, or is it too clever?

## What to produce

A single executable plan. Be concrete and be willing to contradict the documents — they are inputs,
not constraints. I would rather you tell me two of them are wrong than harmonise them.

1. **The verdict on the existing work**: what survives, what to discard, what nobody has noticed.
2. **The repo design**: how many, what is in each, where the git directories live, what is
   deliberately *not* versioned and why. Answer the agent-definitions-and-memory problem.
3. **The cleanup and deletion plan**: what gets deleted outright, what needs a decision first, and in
   what order. Include the 138 worktrees and the ~60 undecided clone-only branches. I want things
   actually deleted, not quarantined forever — so give me the disposal rule that makes deletion safe.
4. **The undo design**: one command, covering create/complete/edit and mid-point resume. Say where
   the checkpoint is captured, what it must contain, what cannot be undone, and how it fails safely.
   Account for the fact that leases, running containers and worker processes are not files.
5. **Order of execution**, with the cheapest risk-reduction first, and what I can do tonight.
6. **What stays at risk** after all of it. Be honest here rather than reassuring.

Where a recommendation depends on something you could not verify from the documents, say so and
state the assumption rather than guessing silently.
