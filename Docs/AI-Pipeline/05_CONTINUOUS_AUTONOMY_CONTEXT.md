# Context 5 — Continuous Autonomous Development

## Goal

Once one-ticket execution is reliable, let the system continue through the safe ready backlog with minimal supervision.

## Main Loop

```python
while True:
    ready = taskctl.ready_ranked()

    if not ready:
        run_planning_reconciliation_or_pause()
        continue

    task = select_first_safe_task(ready)
    result = execute_ticket(task)

    if result == "merged":
        taskctl.recalculate()
        continue

    if result == "blocked":
        record_blocker()
        continue_with_another_ready_task()

    if result == "needs_human":
        surface_to_user()
        continue_with_other_safe_work_if_allowed()
```

## Principle

The supervisor is autonomous. Claude is a bounded/replaceable worker per ticket.

## Newly Discovered Blockers

If Fireball discovers a substantial missing Projectile Collision prerequisite:

1. report blocker
2. propose/create a new task
3. validate/add dependency
4. mark Fireball blocked
5. preserve its branch/PR if useful
6. scheduler chooses another safe ready task

Do not silently implement both goals.

## Planning / Backlog Replenishment

When the ready queue is empty or backlog coverage is low:

```text
GDD RAG + current project scanner + existing tasks
 ↓
requirements reconciliation
 ↓
proposed task artifacts/dependencies
 ↓
graph validation
 ↓
planning PR
```

Initially require human approval for roadmap/task-graph changes.

## GDD Change Detection

Track a GDD hash/version. On material changes, invalidate relevant caches and reconcile affected requirements/tasks rather than blindly rebuilding everything.

## GitHub Dashboard

The user should be able to see Backlog, Ready, In Progress, Blocked, Validating, Needs Review, and Done, with an Issue/PR/dependency/validation trail for active work.

## Merge Safety

Before final validation, update the ticket branch against current main and rerun validation. Consider a merge queue only once multiple workers exist.

## Parallelism

Only after single-worker reliability. Scheduler must reject overlapping conflict/resource claims. Be conservative with Unity scenes, prefabs, ProjectSettings, and shared builder scripts.

## Observability

Persist run records outside model context:

```text
Runs/
  NSC-014/
    <run-id>/
```

Record task ID, worker/model, timestamps, context hash, token/cost usage if available, commits, tests, retries, errors, and disposition.

## Budget Governance

Add project-level limits as well as ticket limits, e.g. daily budget, max concurrent workers, and pause thresholds for accumulated human-review items.

## Human Intervention Queue

Questions should be small and concrete. Once the human makes an architecture/design decision, persist it so agents do not ask the same question repeatedly.

## Long-Term Desired Experience

The user should be able to say:

> Work through No Safe Circle's safe ready backlog until you need me.

Then monitor GitHub to see what Claude is doing, what finished, what is blocked, what needs review, and what became ready next.

## Definition of Success

1. Project state survives chat/model restarts.
2. Claude receives small bounded contexts.
3. Dependencies are deterministic.
4. Code is isolated by branch/worktree.
5. Tests gate completion.
6. Merge defines Done.
7. Failures are bounded and observable.
8. System moves to another ready task without human prompting.
9. Roadmap changes are deliberate, not LLM drift.
10. Token/cost use is much lower than repeated full-repository reasoning.
