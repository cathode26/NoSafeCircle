# Context 3 — Supervisor + Git Branches/Worktrees + GitHub Tickets/PRs

## Goal

Create the first autonomous execution loop for **one ticket at a time**.

Prerequisites: task graph, ready queue, and at least a minimal task context builder.

## Critical Design Decision

Claude does not own the autonomous loop. A local supervisor owns it and invokes Claude as a worker.

This allows project execution to resume after crashes, context loss, model session limits, and timeouts.

## Git Strategy

Never let autonomous workers modify `main` directly.

For a task such as NSC-014:

```text
branch: claude/NSC-014-mana-resource
worktree: .worktrees/NSC-014/
```

Worktrees isolate ticket work and prepare for future safe parallelism.

Do **not** introduce parallel Claude workers yet.

## GitHub Mapping

Each local task should map to a GitHub Issue. GitHub is the human-facing dashboard.

Suggested Project statuses:

- Backlog
- Ready
- In Progress
- Blocked
- Validating
- Needs Review
- Done

Mirror task dependencies into GitHub when practical.

## Source-of-Truth Split

Local task artifact owns durable definition: scope, dependencies, acceptance criteria, canon references.

GitHub owns operational visibility: who/what is working, Draft PR, review state, blocked state, merge/close history.

Avoid storing transient worker state in every Git branch.

## Draft PR Early

When a ticket is claimed:

1. create branch/worktree
2. mark GitHub Issue In Progress
3. open Draft PR immediately
4. launch Claude

PR body should include ticket ID/title, scope, acceptance criteria, validation checklist, task-artifact reference, and a closing issue link/keyword when appropriate.

## Commit Strategy

Claude may make multiple working commits on its ticket branch, e.g.:

```text
NSC-014: Add PlayerMana component
NSC-014: Add mana tests
NSC-014: Fix regen delay behavior
```

Eventually prefer squash merge into main so main contains one clean logical commit per completed ticket.

A downstream dependency becomes satisfied only after the task is merged to main.

## Supervisor First Version

```text
1. taskctl ready
2. choose highest-ranked safe task
3. claim it
4. create branch/worktree
5. open Draft PR
6. build context
7. run Claude
8. collect result
9. move to validation
```

Do not automate merge until validation is reliable.

## Claims / Leases

Implement a claim concept before parallelism:

- task ID
- worker ID
- started time
- expiration/heartbeat later

Tasks may eventually have conflict/resource claims, e.g. `System:PlayerResources` or `Scene:DoorPrototype`.

## Failure Behavior

If Claude fails/times out:

- preserve task, branch, PR, and logs
- do not mark complete
- retry only within configured limits
- make supervisor restartable/idempotent

## Completion Criteria

One real ticket can reliably go:

```text
Ready → Claimed → Branch/Worktree → Draft PR → Claude implementation → commits visible → waiting for validation
```

## Next

Continue with `04_EXECUTION_GER_VALIDATION_CONTEXT.md`.
