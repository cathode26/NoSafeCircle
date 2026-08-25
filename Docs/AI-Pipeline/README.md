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
- `REAL_TASK_DELIVERY_RUNBOOK.md` — authoritative end-to-end procedure for delivering one real task.
- `STANDALONE_CLONE_QUICKSTART.md` — copy/paste workflow for an isolated clone, feature branch, validation, and fixed Compose project name.
- `REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md` — detailed Windows rationale, failure modes, and Docker authentication-volume rules for standalone clones.

Operational subsystem references:

- `Pipeline/ExecutionCrew/README.md` — exact bounded existing/new role-path execution, deterministic locality/scope audit, human review, and retry semantics.
- `Pipeline/TaskDelivery/README.md` — human-reviewed bridge from strict validation manifests to `record_delivery.py`-compatible delivery specs.

`REAL_TASK_DELIVERY_RUNBOOK.md` remains the authoritative end-to-end procedure.

## Maintenance Rule

`CURRENT_STATE.md` is the file that tells a fresh window **where we are now**.

Whenever a milestone advances, update it in the same commit.
