# Context 1 — Persistent Work Artifacts + Dependency Graph

## Goal

Build the durable local planning foundation for the No Safe Circle autonomous AI development pipeline.

This milestone should work without Claude/LLMs.

It should also become useful quickly enough that the next step is a real gameplay task, not another long stretch of infrastructure-only development.

## Why

Assignment 5 repeatedly reconstructed what work exists, what depends on what, what is blocked, and what is ready. That is expensive and ephemeral.

The project should remember this locally.

Assignment 6 added a second lesson: once a real bounded piece of work is selected, a GER repair loop can implement, evaluate, refine, and eventually approve or escalate it.

A later architecture review identified a third requirement: not every high-level feature can be safely decomposed all the way into implementation tickets in advance. Some work requires missing design/content artifacts first.

Milestone 1 therefore stores a coarse truthful work graph and calculates readiness deterministically.

Progressive AI decomposition belongs to Milestone 2, not this milestone.

## Critical Reconciliation Rule

Reconciliation is an immutable input snapshot, not the task database.

Each reconciliation run is versioned. The persistent graph may be seeded or
updated only from an approved proposed delta. Rerunning reconciliation does not
directly cascade edits through `Tasks/*.yaml`.

Do not seed this graph directly from old Assignment 5 goal-selection output.

Before assigning status or dependencies:

1. inspect the current `main` branch;
2. inspect current GDD requirements;
3. use prior assignment artifacts as evidence/history;
4. mark implementation work complete only if the integrated repository state supports it.

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

## Work Kinds

Milestone 1 supports three work kinds:

```text
feature
artifact
implementation
```

### `feature`

High-level work that may require further decomposition.

A feature is not directly handed to an implementation worker.

Examples:

- Five-Room World
- Room 3
- Combat System

### `artifact`

Work whose output is a design/content artifact.

An artifact may become a dependency of later artifact or implementation work.

Artifact generation/authority/evaluation is Milestone 2+ behavior, but Milestone 1 must be able to represent the dependency.

Examples:

- Room 3 Encounter Specification
- Failure Hint Set
- Spell Progression Specification

### `implementation`

Concrete project work that an implementation worker can execute.

Examples:

- Implement Melee Enemy Chase
- Add Fireball Projectile
- Configure Room 3 Door

## Initial Work Schema

```yaml
id: NSC-014
title: Mana Resource System
reconciliation_key: player-mana

kind: implementation
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

## Artifact Work Example

Milestone 1 only needs to represent artifact work.

Generation and evaluation happen later.

```yaml
id: NSC-A130
title: Room 3 Encounter Specification
reconciliation_key: room-3-encounter-spec

kind: artifact
type: encounter-design
status: open

parent: NSC-130

source_requirements:
  - GDD-WORLD-001
  - GDD-ENCOUNTER-001

depends_on: []

artifact_path: Design/Encounters/Room3.md

scope:
  - Define encounter structure
  - Use existing enemy types
  - Define enemy placement and pressure
  - Define door/progression interaction

out_of_scope:
  - New factions
  - New spells
  - New enemy archetypes
  - Unsupported lore

acceptance_criteria:
  - Uses only authorized mechanics and enemies
  - Provides enough detail for implementation decomposition
  - Does not contradict GDD canon

priority: required
risk: medium
estimated_effort: small
claims: []
```

This example is illustrative. Do not create Room 3 artifact work unless the actual project reconciliation shows it is needed.

## Status Semantics

Durable work files may initially use:

- `open`
- `complete`

Operational states such as Claimed/In Progress/Validating should eventually be synchronized through GitHub rather than constantly committed into work files.

The key local truth is whether a dependency has been completed/approved.

### Completion Rules

`implementation` is complete when the current integrated project supports that claim.

Later, production semantics should require merge to `main`.

`artifact` is complete only when the artifact has been approved by its required authority/evaluation process.

During Milestone 1 bootstrapping, do not invent approved artifacts merely to satisfy dependencies.

`feature` is organizational/decomposition work. It is not directly executable.

A feature may be considered complete when its required child work is complete, but do not implement automatic roll-up unless needed for the first useful graph.

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

- duplicate work IDs
- missing dependency IDs
- self-dependencies
- cycles
- invalid `kind`
- invalid status values
- malformed required fields

### `ready`

An executable work item is ready when:

1. it is not complete;
2. every item in `depends_on` is complete;
3. its `kind` is `artifact` or `implementation`.

Feature nodes are not returned by `taskctl ready`.

Eventually support:

```text
python -m taskctl ready --json
```

### `graph`

Text output is enough initially.

Example:

```text
NSC-100 Five-Room World [FEATURE]
  └─ NSC-130 Room 3 [FEATURE]
      └─ NSC-A130 Room 3 Encounter Specification [ARTIFACT / READY]
          ├─ NSC-131 Room 3 Layout [IMPLEMENTATION / BLOCKED]
          └─ NSC-132 Room 3 Enemy Configuration [IMPLEMENTATION / BLOCKED]
```

This is only an example.

Do not create speculative distant child work merely to make the graph look complete.

Do not spend time on a fancy visualization until graph logic is correct.

## Terminology

Use `ready_work`, `ready_tasks`, or `actionable_work`.

Avoid "leaf node" because its meaning depends on edge direction.

## Deterministic Ranking

Later allow fields such as `unlock_value` and rank obvious ready work locally.

Example scoring may use:

- required scope
- unlock value
- foundation value
- risk
- effort

The exact weights matter less than avoiding an LLM call for obvious comparisons.

Do not add ranking until deterministic readiness works.

## Seed Work Candidates

Reasonable initial candidates to reconcile against the current GDD/project include:

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
- five-room world
- encounter/content work only where the current design actually requires it

These are candidates, not truth.

Do not assume exact dependencies or status without checking the current GDD/project.

## Progressive-Decomposition Boundary

Milestone 1 does not run Claude to decompose feature nodes.

It only stores enough structure to support later progressive decomposition.

Do not fully decompose distant features in advance.

If a high-level feature cannot yet be represented as concrete artifact/implementation work without inventing design, leave it coarse.

Milestone 2 will inspect bounded near-frontier feature work and decide whether:

- enough approved information exists to produce child implementation work; or
- a missing design/content artifact must be proposed.

## Post-Assignment-6 Execution Hand-off

Milestone 1 does not need to implement the production GER supervisor.

But its output must be useful to one.

Once `taskctl ready` works:

1. inspect the ready/near-ready frontier;
2. if a concrete implementation item is ready, it can later be executed through the Assignment 6 GER pattern;
3. if only coarse feature work remains, Milestone 2 progressive decomposition is the next requirement.

## Runtime-Aware Planning Note

Implementation acceptance criteria should be written so later validation can distinguish "code exists" from "feature works."

For interactive Unity tasks, avoid acceptance criteria that can only be satisfied by source inspection if the intended behavior is visual, timing-dependent, or runtime-dependent.

Assignment 6 demonstrated why this matters: the camera satisfied static criteria before the game was actually usable.

## Assignment 7 Note

Do not add style-guide tasks merely because Assignment 7 exists.

Assignment 7 will become useful when progressive decomposition identifies an authorized style-sensitive artifact such as player-facing hints, tutorial text, or another content form grounded in actual No Safe Circle needs.

The Style Evaluator will judge generated artifact quality.

It will not authorize new content creation.

## Completion Criteria

1. Work files are parseable.
2. Graph validation catches bad graphs.
3. `feature`, `artifact`, and `implementation` kinds are represented.
4. `ready` is deterministic.
5. Feature nodes are not returned as executable ready work.
6. Completing/approving a dependency causes downstream executable work to become ready.
7. No LLM is required for any of the above.
8. Seeded state has been reconciled against current `main`, not copied blindly from old assignment output.
9. Seeded records preserve a stable `reconciliation_key` linking operational work back to the reconciliation record that proposed it.
10. Reconciliation reruns create immutable snapshots and cannot directly rewrite `Tasks/*.yaml`.
11. A deterministic reconciliation diff can classify agreement, proposed additions/changes, and conflicts before graph mutation.
12. Dependency/status changes cascade through deterministic graph computation, not LLM file rewrites.
13. The graph can identify at least one real next executable item or truthfully report that progressive decomposition is required.

## Next

After Milestone 1 works, continue with `02_RAG_SCANNER_CONTEXT.md`.

Milestone 2 will add RAG/scanner context, progressive decomposition, and artifact authority rather than forcing Milestone 1 to become LLM-dependent.
