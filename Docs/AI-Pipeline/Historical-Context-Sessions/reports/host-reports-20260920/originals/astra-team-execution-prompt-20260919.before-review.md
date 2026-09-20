You produced `C:\nscrev\reports\nsc-durability-cleanup-and-undo-plan-20260919.md`. It is right, and
I am adopting it. Read it again first — this prompt does not repeat its content.

The problem is that it is **role-blind**. It says what must be done and in what order, but not *who*
does each piece, and read as a single queue it looks like weeks of serial work. It is not a solo
project. I have a team. **Re-cast that plan as a team execution plan that finishes in days, not
weeks**, by assigning every piece to the right member and running independent work in parallel.

## The team

Nine agents, each a separate long-running session with its own context window and its own lane.
They message each other directly. The authoritative routing document is
`C:\NSC\nsc-agent-directory.md` — read it.

| Session | Owns | Cannot do |
|---|---|---|
| **Vincent** (human) | Every merge, every push, provider spend, repo creation, running any destructive script, the in-game test | is the bottleneck; minimise his steps |
| **Game Agent** | Game code, Unity, AssistantControl crews, **merges into local `main`**, integration, delivery evidence, `SuccessfullTasks` | push; act without Vincent's own word on a merge |
| **Pipeline Maintainer Agent** | The pipeline itself: AssistantControl, ExecutionCrew, TaskGraph, decomposition tooling, the viewer server, `C:\NSC\tools` | merge; push; game features; contracts; docs |
| **Cleanup Agent** | Branch and worktree triage, disk cleanup under `C:\nscrev` and `C:\NSC\_worktrees` | delete anything itself — **writes plans and scripts that Vincent runs** |
| **Release Agent** | Pushing local `main` when Vincent says so, CI via temporary PRs, WebGL/github.io | push without Vincent's word |
| **Documentation Agent** | The `C:\NSC\nsc-*.md` doc set, `CLAUDE.md`, agent definitions, launch prompts, the runbook | code, contracts, art |
| **GER Agent** | Task contract revisions, GER rounds, contract commits, design decisions | game code, pipeline code |
| **Decomposition Agent** | Splitting oversized tasks, decomposition runs and applies | — |
| **Art Director Agent** | All 2D art, PixelLab, art review packages | — |
| **Viewer Agent** | The viewer process and its overlays | — |

**Force multipliers — use them; they are why this need not take weeks:**

- Any agent can spawn **helper jobs** on a second Claude account via `claude -p --model <model>
  --agent <type>`, and **Docker Claude jobs** in a job clone. These run in parallel with the session
  and cost a different quota. Helper types exist for review, test runs, evidence, drafting and
  bookkeeping (directory section 2).
- Reviews run as **Fable CLI jobs**; design questions come to **me (Astra)**.
- Several helper jobs can run at once. Parallelism across sessions is the explicit goal.
- **Known failure mode, plan around it:** two of three delegated inventory jobs recently exited 0
  having produced nothing, each spawning a background scan and dying. Treat a job's exit code as
  meaningless; require the artifact.

**Hard constraints that shape sequencing:**

- A session's context is finite; a very long single-threaded job forces a mid-work handover.
  Prefer work split into pieces one session can finish.
- **Only Vincent runs destructive scripts.** Every deletion batch is a script he executes. Batch
  them so he runs few commands, not dozens.
- Merges need Vincent's own word **in the Game Agent's session**; a relayed go does not count.
- `main_write.py` is **not actually a lock** (read-then-append, a 30-minute window, same-role
  writers excluded), so concurrent writers to `main` are a live hazard while this work runs.
- A **decomposition plan awaiting apply freezes every contract, new-task and policy commit**. One is
  parked right now. Sequencing that ignores it will stall the GER and Decomposition agents.
- Agents are currently on a stop-work order and will be restarted to execute this.

## What I want back

A **team execution plan**, not a task list. Specifically:

1. **Work packages with an owner each.** Every piece of your plan — preservation, the three new
   repos, the disposition manifest, worktree retirement, deletion batches, the tool consolidation,
   the six undo packages, the `main_write` lock — assigned to exactly one session, with a sentence
   on why that owner and not another. Say explicitly where your plan crosses a lane boundary and
   how to split it so it does not.
2. **A parallel schedule.** What runs simultaneously on day 1, day 2, day 3. Show the **critical
   path** and what is merely attached to it. If something genuinely cannot be parallelised, say why.
3. **The handoff contract between packages** — what one owner must hand the next, and how the
   receiver verifies it rather than trusting it. Your plan gates deletion on verified preservation;
   make that gate concrete and checkable by the Cleanup Agent without reopening the whole design.
4. **Vincent's steps, minimised and batched.** A numbered list of exactly what he must personally do
   and when. If you can cut one of his steps by restructuring, do it.
5. **Where to buy time with helper jobs.** Which packages should fan out to parallel helper jobs, at
   what granularity, and what each must return as proof.
6. **The realistic duration**, with the assumption behind it. If days is not achievable, say what
   the true floor is and which constraint sets it — do not tell me days to be agreeable.
7. **What to cut.** If some of your own plan should be deferred or dropped to get the project back
   in order sooner, say which parts and what is lost. I would rather ship a smaller correct scope
   this week than a complete one in a month.

Two things I want protected in whatever you propose: **nothing valuable is deleted without verified
recovery**, and **the fleet can keep doing normal game work while this happens** — it must not
require freezing everything for days.

Write the plan to `C:\nscrev\reports\nsc-team-execution-plan-20260919.md`.
