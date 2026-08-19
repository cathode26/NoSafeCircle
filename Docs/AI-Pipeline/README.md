# No Safe Circle AI Pipeline Documentation

Start with:

**`START_HERE.md`**

The documentation is intentionally split so a fresh AI context only needs the master architecture plus the milestone currently being implemented.

## Files

- `START_HERE.md` — routing / table of contents for humans and AI assistants.
- `CURRENT_STATE.md` — exactly where pipeline implementation currently stands and the next action.
- `DECISIONS.md` — durable architecture decisions so they are not repeatedly re-litigated.
- `00_MASTER_CONTEXT.md` — complete target architecture.
- `01_MILESTONE_TASK_GRAPH.md` — task artifacts, dependency graph, ready queue.
- `02_RAG_SCANNER_CONTEXT.md` — GDD RAG, project scanner, compact context builder.
- `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md` — supervisor, Git isolation, GitHub dashboard.
- `04_EXECUTION_GER_VALIDATION_CONTEXT.md` — Agent Crew, GER, validation and repair.
- `05_CONTINUOUS_AUTONOMY_CONTEXT.md` — continuous operation, blockers, budgets and later parallelism.
- `06_NEW_WINDOW_HANDOFF_TEMPLATE.md` — optional starter prompt for a fresh AI window.

## Maintenance Rule

`CURRENT_STATE.md` is the file that tells a fresh window **where we are now**.

Whenever a milestone advances, update it in the same commit.
