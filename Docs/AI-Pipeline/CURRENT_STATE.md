# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

## Current Phase

**Pipeline planning complete. Milestone 1 has not yet been implemented.**

Current milestone:

`01_MILESTONE_TASK_GRAPH.md`

## What Already Exists

Course work that the future pipeline will reuse:

- Assignment 3: Agent Crew concept — Planner → Implementer → Validator.
- Assignment 4: GDD RAG / retrieval pipeline.
- Assignment 5: goal-oriented analysis + implementation workflow.
- Assignment 6 concept: GER — Generator → Evaluator → Refiner → Circuit Breaker.

Assignment 5 successfully selected and implemented a Mana Resource System on the `assignment-5-goal-oriented-agent` branch. Verify merge status in Git before treating it as present on `main`.

## Current Architectural Decision

We are replacing repeated full-LLM project planning with persistent local project state:

```text
GDD / RAG
   ↓
Task Artifacts
   ↓
Dependency Graph
   ↓
Ready Queue
   ↓
Local Supervisor
   ↓
Branch + Worktree + GitHub Ticket/PR
   ↓
Bounded Claude Worker / Agent Crew
   ↓
GER if generated content is needed
   ↓
Deterministic + Unity Validation
   ↓
Merge
   ↓
Task Complete
   ↓
New Tasks Become Ready
```

## Immediate Next Goal

Implement Milestone 1:

1. Define `Tasks/*.yaml`.
2. Implement local Python `taskctl`.
3. Implement:
   - `list`
   - `show`
   - `validate`
   - `ready`
   - `graph`
4. Seed a small initial task graph from current No Safe Circle work.
5. Do this without an LLM dependency.

## Do Not Start Yet

Do not start these until Milestone 1 is working:

- GitHub synchronization
- autonomous Claude execution
- Git worktrees
- GER integration
- parallel workers
- automatic backlog replenishment

## Known Important Constraints

- Persistent task definitions should be local/versioned.
- Transient worker state should eventually live in the supervisor/GitHub rather than being committed on every worker branch.
- A task is `Done` only after its implementation is merged to `main`.
- A newly discovered substantial prerequisite becomes a blocker/new task; it should not be silently absorbed.
- Do not run multiple Claude workers until one-ticket execution is reliable.
- Unity scenes/prefabs/shared builder files require conservative conflict handling.

## Next Window Instructions

Read, in order:

1. `START_HERE.md`
2. this file
3. `00_MASTER_CONTEXT.md`
4. `01_MILESTONE_TASK_GRAPH.md`

Then inspect the repo and propose the smallest first implementation slice for Milestone 1.
