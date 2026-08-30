# Session Handoff Template

Date: YYYY-MM-DD  
Session/topic: SHORT TITLE

## Goal

What concrete outcome was this session trying to reach?

## Starting state

Record only facts that were actually verified during the session.

```text
repository:
controller path:
branch:
HEAD:
origin/main:
working tree:
Issue/PR:
TaskGraph state:
```

If a fact was assumed rather than verified, label it explicitly.

## Decisions made

List architectural or operational decisions that future agents should understand. Separate durable design decisions from temporary troubleshooting choices.

## Work performed

Summarize the actual repository/workflow changes. Include exact files or subsystems when useful.

## Validation / evidence

Record the checks that actually ran and their outcomes.

Examples:

```text
TaskGraph:
Core CI:
Supervisor CI:
Delivery CI:
Unity EditMode:
Unity PlayMode:
adversarial review:
exact reviewed SHA:
```

Do not write “all tests passed” if some test was not executed successfully.

## Ending state

Record the exact state at the moment the session ended.

```text
branch:
HEAD:
origin branch:
origin/main:
working tree:
Issue state:
PR:
uncommitted files:
```

If a commit has already been created, say so prominently. This prevents a later runner from creating a duplicate commit.

## Unresolved issues / known blockers

List only real remaining blockers or deliberately deferred follow-ups.

## Next action

Give one concrete continuation action.

Prefer:

> Verify X; if confirmed, do Y.

over a long speculative plan.

## Do not repeat

List expensive reviews, migrations, or debugging paths that have already been completed and should not be rerun without new evidence.

## Historical/raw source

If a raw transcript was retained, reference it here.

## Authority reminder

This handoff is historical context. Before mutating the repository, verify current Git, TaskGraph, GitHub Issue/PR, remote-ref, and test state. Current deterministic state wins if it disagrees with this handoff.
