# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last reconciled: 2026-08-18, after Assignment 6.

## Current Phase

Pipeline architecture planning is complete enough to begin turning the course assignments into durable production infrastructure.

Milestone 1 has not yet been implemented:

`01_MILESTONE_TASK_GRAPH.md`

However, Assignment 6 has now produced a working GER implementation and changed an important architectural assumption. GER is no longer considered only a future generated-content subsystem; it is a proven bounded implementation/repair loop that should eventually wrap normal ticket execution.

## What Already Exists

Course work that the production pipeline will reuse:

- Assignment 3: Agent Crew concept — Planner → Implementer → Validator.
- Assignment 4: GDD RAG / retrieval pipeline and consistency checking.
- Assignment 5: goal-oriented analysis + implementation workflow.
- Assignment 6: working GER orchestration — Generator/Implementer → Evaluator → Refiner → Circuit Breaker.

### Assignment 6 Result

Assignment 6 reused the earlier systems rather than creating isolated demo agents:

- Assignment 5 implementation agent acted as Generator and Refiner.
- Assignment 3 validation infrastructure acted as Evaluator.
- Assignment 6 added orchestration, a GDD-specific evaluator contract, runtime-feedback handling, a progress/no-op guard, and a Circuit Breaker.
- The selected feature was the fixed orthographic isometric camera.
- Static evaluation passed before the runtime result was actually correct.
- Unity runtime failures were captured as structured feedback and re-entered into the Refiner loop.
- A no-op refinement was rejected as failed progress instead of being accepted as success.
- The final camera implementation passed the GER evaluator and the relevant Unity EditMode/PlayMode tests.

Reference:

`Assignment6GER/README_Assignment6.md`

### Assignment 5 State

Assignment 5 selected and implemented a Mana Resource System on the `assignment-5-goal-oriented-agent` branch.

Assignment 6 treated Mana as an already-completed goal when performing lightweight reselection, but Milestone 1 must still inspect the actual current `main` branch before marking Mana or any other task `complete`.

Do not seed task completion status from old Assignment 5 output alone.

## Current Architectural Decision

We are replacing repeated full-LLM project planning with persistent local project state, while preserving the useful agent behaviors already proven by the assignments.

The target architecture is now:

```text
GDD / Canon
   ↓
Persistent Task Artifacts
   ↓
Dependency Graph
   ↓
Ready Queue
   ↓
Local Supervisor
   ↓
Bounded Ticket + Context Package
   ↓
Worker / Agent Crew
   ↓
==============================
        GER REPAIR LOOP
------------------------------
Implement / Generate
   ↓
Evaluate against task + GDD
   ↓
Deterministic / Unity / Runtime Evidence
   ↓
PASS? ───────────────→ Approved
   │
   └─ FAIL
        ↓
   Structured Feedback
        ↓
      Refiner
        ↓
    Re-evaluate
        ↓
   Retry to Budget
        ↓
  Circuit Breaker
==============================
   ↓
Fresh AI Diff Review
   ↓
Merge
   ↓
Task Complete
   ↓
Dependency Graph Recalculates
```

GER is the bounded self-correction mechanism around project work. Generated content is one application of GER, not its definition.

## Important Validation Lesson

A source-level or static PASS is not sufficient evidence that a Unity feature works.

Assignment 6 proved this twice:

1. The first camera implementation satisfied the written/static camera rules but faced the wrong direction and did not follow the player correctly.
2. A later implementation again passed static evaluation while framing gameplay incorrectly.

Future ticket execution should collect validation evidence from the strongest practical sources available:

- Git/scope checks
- static checks
- Unity compilation
- EditMode tests
- PlayMode tests
- runtime observations
- later simulation/adversarial-agent evidence where appropriate
- semantic/GDD evaluation

Failed evidence should become structured Refiner input.

## Immediate Next Goal

Implement the smallest useful version of Milestone 1 and use it to advance the real game.

1. Inspect current `main`.
2. Reconcile the actual implemented game state against the GDD and existing assignment artifacts.
3. Define a small set of `Tasks/*.yaml`.
4. Implement local Python `taskctl`.
5. Implement:
   - `list`
   - `show`
   - `validate`
   - `ready`
   - `graph`
6. Seed only task/dependency facts that are supported by the current repository.
7. Let the graph identify the real ready frontier.
8. Select a real gameplay task from that frontier and execute it through the existing/proven GER pattern.

The pipeline should begin earning its keep by building No Safe Circle rather than delaying gameplay until every autonomous subsystem exists.

## Assignment 7 Position

Assignment 7's Style Guide Agent has not been implemented yet.

Do not invent new lore or force a style system onto game content that does not yet exist. When a suitable player-facing content feature is ready, Assignment 7 should become an evaluator specialization inside the same GER architecture:

`Generator → scored Style Evaluator (SCORE + REASON) → Refiner`

Potential targets should be chosen from actual game needs and prior work, not from placeholder lore.

## Do Not Start Yet

Do not start these until Milestone 1 is working and the current task graph is truthful:

- GitHub synchronization
- fully autonomous continuous Claude execution
- Git worktrees managed by the supervisor
- parallel workers
- automatic backlog replenishment

GER itself is no longer in this list: the pattern has already been proven in Assignment 6. What is deferred is production integration of GER into the future supervisor.

## Known Important Constraints

- Persistent task definitions should be local/versioned.
- Transient worker state should eventually live in the supervisor/GitHub rather than being committed on every worker branch.
- A task is `Done` only after its implementation is merged to `main`.
- A newly discovered substantial prerequisite becomes a blocker/new task; it should not be silently absorbed.
- Do not run multiple Claude workers until one-ticket execution is reliable.
- Unity scenes/prefabs/shared builder files require conservative conflict handling.
- Static evaluation cannot substitute for Unity/runtime evidence when behavior is visual or interactive.
- A refinement that produces no relevant change while failures remain counts as failed progress.
- All autonomous repair loops require retry/runtime/cost budgets and a Circuit Breaker.

## Next Window Instructions

Read, in order:

1. `START_HERE.md`
2. this file
3. `00_MASTER_CONTEXT.md`
4. `01_MILESTONE_TASK_GRAPH.md`
5. `DECISIONS.md`

Then inspect the current repository and implement the smallest first slice of Milestone 1.

Do not use the old Assignment 5 goal-selection snapshot as current project truth.
