# ADR-044: TaskGraph-to-GitHub Issue State Mirror

- Status: Accepted
- Date: 2026-08-25

## Context

TaskGraph owns durable work contracts and evidence-derived current state. GitHub Issues own operational visibility for claims, releases, closeout history, and human coordination. Production use exposed a missing bridge: after a later implementation changes a tracked conformance surface, a previously completed task may move from `conformant` to `needs_testing`, while its older GitHub Issue still visually reads as completed/conformant unless a human or ChatGPT manually notices the drift.

The Issue lifecycle cannot safely stand in for TaskGraph state. A closed Issue means the prior orchestration finished; it does not prove the task remains conformant forever. Conversely, reopening every Issue whose evidence needs testing would conflate current evidence state with operational claim state.

## Decision

Define an on-demand, one-way **TaskGraph → GitHub Issue state mirror**.

A human instruction such as `Sync TaskGraph states to the GitHub Issues` authorizes a fresh ChatGPT orchestrator to read current committed TaskGraph states and update an idempotent managed state block in existing matching Issues, including closed Issues.

TaskGraph remains authoritative. The GitHub mirror never writes back into TaskGraph and never becomes conformance authority.

A pure sync does not change Issue open/closed state, assignment, claims, branches, checkouts, implementation, testing, or evidence. In particular, a previously closed Issue whose current TaskGraph state is `needs_testing` remains closed but its managed mirror block must be updated to `needs_testing`.

Default sync updates existing unique `NSC-###` Issues only. It does not create missing Issues unless the human separately requests materialization. Duplicate Issue mappings fail closed for the affected task.

The detailed managed-block format, state meanings, idempotency rules, and completion report are defined in `Docs/AI-Pipeline/TASKGRAPH_GITHUB_ISSUE_STATE_SYNC.md`.

## Consequences

- `needs_testing` becomes visible on historical completed Issues without falsely claiming the implementation was never completed.
- GitHub open/closed/assignment remains an orchestration axis separate from evidence-derived TaskGraph state.
- Repeated syncs update one managed body block rather than spamming comments.
- Fresh ChatGPT instances can execute a short human instruction consistently from repository documentation.
- Automatic/background synchronization remains unimplemented; this ADR defines the human-invoked synchronization workflow.
- TaskGraph readiness, execution authorization, merge authority, and autonomous dispatch remain unchanged.
