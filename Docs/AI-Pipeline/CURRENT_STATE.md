# CURRENT STATE — No Safe Circle AI Pipeline

> Update this file whenever a milestone or important implementation slice changes.

Last reconciled: 2026-08-18, after Assignment 6 and progressive-decomposition architecture review.

## Current Phase

Pipeline architecture planning is complete enough to begin turning the course assignments into durable production infrastructure.

Milestone 1 has not yet been implemented:

`01_MILESTONE_TASK_GRAPH.md`

Assignment 6 produced a working GER implementation and changed an important architectural assumption. GER is no longer considered only a future generated-content subsystem; it is a proven bounded implementation/repair loop that should eventually wrap normal ticket execution.

A second architectural gap has now been identified: some high-level work cannot be safely decomposed into implementation tickets until missing design/content exists. The pipeline therefore needs progressive task decomposition plus an Artifact Authority Gate before AI-generated design becomes trusted project input.

## What Already Exists

Course work that the production pipeline will reuse:

- Assignment 3: Agent Crew concept — Planner → Implementer → Validator.
- Assignment 4: GDD RAG / retrieval pipeline and consistency checking.
- Assignment 5: goal-oriented analysis + implementation workflow.
- Assignment 6: working GER orchestration — Generator/Implementer → Evaluator → Refiner → Circuit Breaker.
- Assignment 7: not yet implemented; planned as a scored Style Evaluator specialization for authorized style-sensitive content artifacts.

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

Assignment 6 treated Mana as an already-completed goal when performing lightweight reselection, but Milestone 1 must still inspect the actual current `main` branch before marking Mana or any other work item `complete`.

Do not seed completion status from old Assignment 5 output alone.

## Current Architectural Decision

We are replacing repeated full-LLM project planning with persistent local project state while preserving the useful agent behaviors already proven by the assignments.

The target architecture is now:

```text
GDD / Canon
   ↓
Persistent Work Graph
   ↓
Ready / Near-Ready Frontier
   ↓
Progressive Decomposer
   ↓
Enough approved information to execute?
   │
   ├─ YES → Concrete Artifact or Implementation Work
   │
   └─ NO
        ↓
   Proposed Missing Artifact
        ↓
   Artifact Authority Gate
        ↓
   Authorized?
      /     \
    YES      NO
     ↓        ↓
Artifact GER  Re-plan / Human Review
     ↓
Approved Artifact
     ↓
Back to Progressive Decomposer
     ↓
Concrete Work Item
     ↓
==============================
        GER REPAIR LOOP
------------------------------
Implement / Generate
   ↓
Evaluate against task + GDD + approved artifacts
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
Merge / Approve Artifact
   ↓
Work Complete
   ↓
Dependency Graph Recalculates
```

GER is the bounded self-correction mechanism around project work. Generated content is one application of GER, not its definition.

Progressive decomposition prevents the system from inventing missing design merely to make a high-level task executable.

## Canon and Approved Design Extensions

The GDD is root canon.

An AI-generated artifact is not trusted merely because it was generated.

A proposed design/content artifact must first pass an Artifact Authority Gate that identifies:

- why the artifact is needed;
- which existing requirements authorize its creation;
- which design decisions it may make;
- which design areas it must not invent or change.

After generation, the artifact must pass its required evaluators.

Only then may it become an approved design extension that downstream work can depend on.

Approved artifacts may add detail where the GDD leaves room for expansion, but they may not contradict or silently replace GDD canon.

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
- artifact/canon evaluation where applicable
- style evaluation where applicable

Failed evidence should become structured Refiner input.

## Immediate Next Goal

### Milestone 1 — Persistent Work Graph

1. Inspect current `main`.
2. Run/read the Reconciliation Agent to create an immutable point-in-time snapshot of GDD requirements versus current repository state.
3. Review the snapshot's proposed graph delta.
4. Seed a coarse persistent work graph from approved reconciliation records; do not treat the snapshot itself as the mutable graph.
5. Support three work kinds:
   - `feature`
   - `artifact`
   - `implementation`
6. Implement local Python `taskctl`.
7. Implement:
   - `list`
   - `show`
   - `validate`
   - `ready`
   - `graph`
8. Seed only work/dependency facts that are supported by the current repository.
9. Preserve `reconciliation_key` traceability from seeded work back to the snapshot record that proposed it.
10. Do not fully decompose distant features merely to fill the graph.

Milestone 1 remains deterministic and should work without an LLM dependency.

### After Milestone 1

Begin Milestone 2:

1. Reuse/build the GDD RAG interface.
2. Build the deterministic project-state scanner.
3. Build compact context packs.
4. Add the Progressive Decomposer.
5. When decomposition discovers missing design, create an artifact proposal.
6. Run the Artifact Authority Gate before generation.
7. Generate authorized artifacts through GER.
8. Re-run the Decomposer using the approved artifact.
9. Execute the resulting concrete implementation task through the Assignment 6 GER pattern.

The pipeline should begin earning its keep by building No Safe Circle rather than delaying gameplay until every autonomous subsystem exists.

## Assignment 7 Position

Assignment 7 now has a concrete architectural role.

Progressive decomposition may identify required player-facing or style-sensitive content artifacts. After the Artifact Authority Gate approves creation, those artifacts are generated through GER.

Assignment 7 supplies the specialized scored Style Evaluator:

`Generator → Style Evaluator (SCORE + REASON) → Refiner`

The Style Evaluator judges whether authorized generated content matches No Safe Circle.

It does not decide whether new content was authorized to exist.

## Do Not Start Yet

Do not start these until Milestone 1 is working and the current work graph is truthful:

- GitHub synchronization
- fully autonomous continuous Claude execution
- Git worktrees managed by the supervisor
- parallel workers
- automatic backlog replenishment

Production integration of the Progressive Decomposer and Artifact Authority Gate belongs in Milestone 2.

GER itself is no longer in this list: the pattern has already been proven in Assignment 6. What is deferred is production integration of GER into the future supervisor.

## Known Important Constraints

- Persistent work definitions should be local/versioned.
- Reconciliation outputs are immutable point-in-time snapshots and must not be edited to reflect later work.
- A reconciliation rerun creates a new snapshot; it never directly rewrites `Tasks/*.yaml`.
- Reconciliation-to-graph changes must pass through a deterministic diff/proposed-delta step.
- Cascading readiness changes are computed by `taskctl`, not by the Reconciliation Agent.
- Transient worker state should eventually live in the supervisor/GitHub rather than being committed on every worker branch.
- An implementation task is `complete` only after its implementation is merged to `main`.
- An artifact task is `complete` only after the artifact is approved by its required evaluators and stored as trusted project input.
- Feature nodes are organizational/decomposition nodes and are not directly handed to implementation workers.
- A newly discovered substantial prerequisite becomes a blocker/new work item; it should not be silently absorbed.
- Missing design becomes an artifact proposal rather than silent invention.
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
Do not implement the Progressive Decomposer yet; Milestone 1 must first establish a truthful deterministic work graph.
