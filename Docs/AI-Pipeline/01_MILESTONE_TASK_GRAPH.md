# Context 1 — Persistent Task Artifacts + Dependency Graph

## Goal

Build the durable local planning foundation for the No Safe Circle autonomous AI development pipeline.

This milestone should work **without Claude/LLMs**.

## Why

Assignment 5 repeatedly reconstructed what work exists, what depends on what, what is blocked, and what is ready. That is expensive and ephemeral. The project should remember this locally.

## Deliverables

Create:

```text
Tasks/
  NSC-001.yaml
  NSC-002.yaml
  ...
```

and a local Python CLI called `taskctl`.

## Initial Task Schema

```yaml
id: NSC-014
title: Mana Resource System

type: gameplay
status: open

source_requirements:
  - GDD-MANA-001

depends_on: []

scope:
  - Add mana pool
  - Spend mana
  - Regenerate after delay

out_of_scope:
  - Fireball
  - Frost Field
  - Force Wave

acceptance_criteria:
  - Spending reduces mana when enough is available
  - Spending fails without mutation when mana is insufficient
  - Regeneration pauses after spending
  - Regeneration resumes after configured delay
  - Mana cannot exceed maximum

priority: required
risk: low
estimated_effort: small
parent: ""
claims: []
```

Do not over-design the schema before the first working version.

## Status Semantics

Durable task files may initially use `open` and `complete`. Operational states such as Claimed/In Progress/Validating should eventually be synchronized through GitHub rather than constantly committed into task files.

The key local truth is whether a dependency has been completed/merged.

## Required `taskctl` Commands

```text
python -m taskctl list
python -m taskctl show NSC-014
python -m taskctl validate
python -m taskctl ready
python -m taskctl graph
```

### `validate`

Detect duplicate task IDs, missing dependency IDs, self-dependencies, cycles, invalid enum/status values, and malformed required fields.

### `ready`

A task is ready when it is not complete and every task in `depends_on` is complete.

Eventually support:

```text
python -m taskctl ready --json
```

### `graph`

Text output is enough initially.

```text
NSC-014 Mana [COMPLETE]
  ├─ NSC-021 Fireball [READY]
  ├─ NSC-022 Frost Field [READY]
  └─ NSC-023 Force Wave [READY]
```

Do not spend time on a fancy visualization until graph logic is correct.

## Terminology

Use `ready_tasks` or `actionable_tasks`. Avoid “leaf node” because its meaning depends on edge direction.

## Deterministic Ranking

Later allow fields such as `unlock_value` and rank obvious ready tasks locally. Example scoring may use required scope, unlock value, foundation value, risk, and effort. The exact weights matter less than avoiding an LLM call for obvious comparisons.

## Seed Tasks

Reasonable initial tasks to reconcile against the current GDD/project include fixed isometric camera, mouse-directed movement, Tilemap world foundation, navigation foundation, mana, three spells, melee/ranged enemy, door lifecycle, death/restart, and five-room encounter/content work.

Do not assume exact dependencies without checking the current GDD/project when implementing this milestone.

## Completion Criteria

1. Task files are parseable.
2. Graph validation catches bad graphs.
3. `ready` is deterministic.
4. Completing a dependency causes downstream tasks to become ready.
5. No LLM is required for any of the above.

## Next

Continue with `02_RAG_SCANNER_CONTEXT.md`.
