# Context 1 — Persistent Task Artifacts + Dependency Graph

## Goal

Build the durable local planning foundation for the No Safe Circle autonomous AI development pipeline.

This milestone should work without Claude/LLMs.

It should also become useful quickly enough that the next step is a real gameplay task, not another long stretch of infrastructure-only development.

## Why

Assignment 5 repeatedly reconstructed what work exists, what depends on what, what is blocked, and what is ready. That is expensive and ephemeral.

The project should remember this locally.

Assignment 6 added a second lesson: once a real task is selected, a bounded GER repair loop can implement, evaluate, refine, and eventually approve or escalate it.

Therefore Milestone 1 should answer **what is actually ready now**, so the proven execution loop can be used on real game development.

## Critical Reconciliation Rule

Do not seed this graph directly from old Assignment 5 goal-selection output.

Before assigning task status or dependencies:

1. inspect the current `main` branch;
2. inspect current GDD requirements;
3. use prior assignment artifacts as evidence/history;
4. mark a task complete only if the integrated repository state supports it.

Assignment 6 treated Mana as already completed for lightweight reselection, but that does not remove the need to verify merge state when building the durable graph.

The Assignment 6 fixed isometric camera work is the newest known implementation slice and should also be reconciled against current `main`.

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

### Future Validation Metadata

Later, a task may need to declare validation/evaluator requirements, for example:

```yaml
validation:
  - unity_editmode
  - unity_playmode
  - gdd_semantic
```

or a style/content evaluator profile.

Do **not** add this to Milestone 1 unless the first real execution ticket proves it is necessary. The task graph must work first.

## Status Semantics

Durable task files may initially use:

- `open`
- `complete`

Operational states such as Claimed/In Progress/Validating should eventually be synchronized through GitHub rather than constantly committed into task files.

The key local truth is whether a dependency has been completed/merged.

A task is not complete because an assignment output says it was implemented. It is complete when the current integrated project supports that claim.

## Required `taskctl` Commands

```text
python -m taskctl list
python -m taskctl show NSC-014
python -m taskctl validate
python -m taskctl ready
python -m taskctl graph
```

### `validate`

Detect:

- duplicate task IDs
- missing dependency IDs
- self-dependencies
- cycles
- invalid enum/status values
- malformed required fields

### `ready`

A task is ready when it is not complete and every task in `depends_on` is complete.

Eventually support:

```text
python -m taskctl ready --json
```

### `graph`

Text output is enough initially.

Example:

```text
NSC-014 Mana [COMPLETE]
  ├─ NSC-021 Fireball [READY]
  ├─ NSC-022 Frost Field [READY]
  └─ NSC-023 Force Wave [READY]
```

This is only an example. Do not assume these exact statuses until reconciliation.

Do not spend time on a fancy visualization until graph logic is correct.

## Terminology

Use `ready_tasks` or `actionable_tasks`.

Avoid "leaf node" because its meaning depends on edge direction.

## Deterministic Ranking

Later allow fields such as `unlock_value` and rank obvious ready tasks locally.

Example scoring may use:

- required scope
- unlock value
- foundation value
- risk
- effort

The exact weights matter less than avoiding an LLM call for obvious comparisons.

Do not add ranking until deterministic readiness works.

## Seed Task Candidates

Reasonable initial tasks to reconcile against the current GDD/project include:

- fixed isometric camera
- mouse-directed movement
- Tilemap world foundation
- navigation foundation
- mana
- Fireball
- Frost Field
- Force Wave
- melee enemy
- ranged enemy
- door lifecycle
- death/restart
- five-room encounter/content work

These are **candidates**, not truth.

Do not assume exact dependencies or status without checking the current GDD/project.

## Post-Assignment-6 Execution Hand-off

Milestone 1 does not need to implement the production GER supervisor.

But its output must be useful to one.

Once `taskctl ready` works:

1. choose one actual ready gameplay task;
2. construct a bounded task contract from the task artifact;
3. use the Assignment 6 GER pattern to implement/refine that task;
4. validate it using the strongest relevant evidence;
5. after merge, mark the task complete;
6. run `taskctl ready` again and observe the new frontier.

This is the first practical bridge from persistent planning to autonomous game development.

## Runtime-Aware Planning Note

Task acceptance criteria should be written so that later validation can distinguish "code exists" from "feature works."

For interactive Unity tasks, avoid acceptance criteria that can only be satisfied by source inspection if the intended behavior is visual, timing-dependent, or runtime-dependent.

Assignment 6 demonstrated why this matters: the camera satisfied static criteria before the game was actually usable.

## Assignment 7 Note

Do not add style-guide tasks merely because Assignment 7 exists.

When a real player-facing content feature is ready, style constraints can become a specialized evaluator/validation profile inside GER.

Until then, the graph should represent real No Safe Circle work and real dependencies.

## Completion Criteria

1. Task files are parseable.
2. Graph validation catches bad graphs.
3. `ready` is deterministic.
4. Completing a dependency causes downstream tasks to become ready.
5. No LLM is required for any of the above.
6. Seeded task state has been reconciled against current `main`, not copied blindly from old assignment output.
7. The graph can identify at least one real next gameplay task or truthfully report why none is ready.

## Next

After Milestone 1 works, use the ready frontier to select a real game task and exercise the proven GER pattern.

Then continue with `02_RAG_SCANNER_CONTEXT.md` when the next execution slice needs durable canon/code scanning and compact context construction.
