# No Safe Circle — Autonomous AI Development Pipeline

## Master Context / Architecture Handoff

Use this file to start a fresh ChatGPT window when working on the autonomous development pipeline.

Last architecture reconciliation: 2026-08-18, after Assignment 6.

## Project

Repository: `https://github.com/cathode26/NoSafeCircle`

Current course work has produced useful building blocks:

- Assignment 3: Agent Crew concept (Planner → Implementer → Validator).
- Assignment 4: RAG pipeline over the No Safe Circle GDD.
- Assignment 5: goal-oriented analysis and implementation agent.
- Assignment 6: working GER implementation — Generator/Implementer → Evaluator → Refiner → Circuit Breaker.

The goal is to evolve these pieces into a practical system that can autonomously continue developing No Safe Circle while keeping project state durable, observable, inexpensive to reason about, resumable after failures, and grounded in real Unity evidence.

## Core Architectural Decision

The LLM should NOT own project state or the continuous autonomous loop.

A local deterministic supervisor should own the loop.

Claude should be a bounded worker that receives one small task at a time.

Persistent project state should live in local/versioned artifacts and GitHub, not in Claude's context window.

The worker may implement or generate work, but it does not get to declare that work complete. Completion is determined by project evidence and merge state.

## Post-Assignment-6 Architecture Correction

The original architecture treated GER mainly as a gate for generated content.

Assignment 6 demonstrated a broader and more useful role.

GER is the bounded self-correction loop around project work:

```text
Selected Bounded Task
        ↓
Implement / Generate
        ↓
Evaluate
        ↓
Collect Deterministic + Unity + Runtime Evidence
        ↓
      PASS?
     /     \
   yes      no
    ↓        ↓
Approve   Structured Feedback
              ↓
           Refiner
              ↓
          Re-evaluate
              ↓
        retry to budget
              ↓
        Circuit Breaker
```

Generated game/content artifacts remain one GER use case. Unity code implementation is another.

The important abstraction is not "generated content." It is "a bounded artifact or implementation that can be evaluated, repaired, and either approved or escalated."

## Desired End-to-End Loop

```text
GDD
 ↓
RAG / Canon Retrieval
 ↓
Persistent Task Artifacts
 ↓
Dependency Graph
 ↓
Ready Queue
 ↓
Local Supervisor
 ↓
Claim Ticket
 ↓
Git Branch + Git Worktree + Draft PR
 ↓
Build Small Context Package
 ↓
Bounded Claude Worker / Agent Crew
 ↓
==============================
        GER EXECUTION LOOP
------------------------------
Implement / Generate
 ↓
Task/GDD Evaluation
 ↓
Deterministic Validation
 ↓
Unity / Runtime Validation
 ↓
PASS?
 ├─ yes → Approved Work
 └─ no  → Feedback Bundle → Refiner → Re-evaluate
                         ↓
                 retry/cost/runtime limit
                         ↓
                  Circuit Breaker
==============================
 ↓
Fresh AI Diff Review
 ↓
PR Merge
 ↓
Task = Done
 ↓
Dependency Graph Recalculates
 ↓
New Tasks Become Ready
 ↓
Repeat
```

The exact order of evaluator sub-checks may vary by task, but cheap deterministic failures should be detected before spending model tokens on semantic review whenever practical.

## Guiding Principle

Use code for facts and computation. Use the LLM for judgment.

Deterministic/local work includes:

- file enumeration
- code/component detection
- Unity YAML inspection
- `.meta` GUID relationships
- dependency readiness
- ready-queue computation
- obvious ranking
- graph validation
- Git checks
- scope checks
- Unity compilation/tests
- progress/no-op detection

LLM work includes:

- semantic decomposition of tasks
- interpreting ambiguous GDD intent
- resolving real planning ties
- bounded implementation planning/coding
- semantic GDD/task evaluation
- semantic diff review
- player-facing content generation
- refinement from structured failure feedback

## Sources of Truth

### Canon

The GDD is canonical game-design information.

Assignment 4 RAG should retrieve only relevant GDD chunks instead of repeatedly sending the whole GDD to the LLM.

Prior assignment artifacts may provide evidence or reusable machinery, but they do not override the current GDD or current `main` branch.

### Codebase Truth

The current `main` branch is the truth for what has actually been integrated.

Old Assignment 5 goal-selection output must not be treated as current codebase truth without rescanning/reconciling the repository.

### Durable Work Definition

Local task artifacts should define durable work:

```text
Tasks/
  NSC-001.yaml
  NSC-002.yaml
  ...
```

Each task should define:

- ID
- title
- type
- source GDD requirements
- dependencies
- scope
- out-of-scope work
- acceptance criteria
- priority
- risk
- effort
- optional resource/conflict claims
- optional parent/epic

A task may later also declare which validation/evaluator profiles apply, but do not over-design this before Milestone 1 works.

### Operational Status

GitHub Issues + GitHub Projects should be the human-facing dashboard for:

- Backlog
- Ready
- In Progress
- Blocked
- Validating
- Needs Review
- Done

Do not make transient "Claude is working right now" state part of task-branch commits if that can create conflicting operational state.

## Task Dependencies

A task is ready only when all required dependencies are complete/merged.

Example candidates from the current design include:

```text
Fixed Isometric Camera
   ↓
Tilemap World Foundation
   ↓
Navigation Foundation
   ↓
Melee Enemy
```

Separately:

```text
Mana
   ↓
Fireball
Frost Field
Force Wave
```

These are planning examples, not guaranteed current dependencies. Milestone 1 must reconcile them against the current GDD and codebase before creating the durable graph.

The local graph calculates the actionable/ready frontier.

## Git Model

Never allow autonomous workers to develop directly on `main`.

For each ticket:

```text
branch: claude/NSC-014-mana-resource
worktree: .worktrees/NSC-014/
```

Lifecycle:

```text
Ready → Claimed → In Progress → Validating → PR Ready → Merged → Done
```

"Done" means merged into `main`, not merely "Claude says it finished."

Prefer squash merging eventually so `main` has one clean logical commit per ticket. Create a Draft PR early so the human can watch work in progress.

## Assignment 3 Integration

Assignment 3's crew belongs inside ticket execution:

```text
Task Graph chooses WHAT
        ↓
Planner
        ↓
Implementer
        ↓
Validator
```

The crew should not reconstruct the global roadmap.

The Validator can contribute evidence to the GER evaluation bundle, but it is not the only source of truth for interactive Unity behavior.

## Assignment 4 Integration

RAG answers:

> What does the GDD say about this task?

A context builder should retrieve only the task's relevant canonical chunks.

RAG is desired-state/canon retrieval, not codebase truth.

For GER, retrieved GDD evidence can be supplied to semantic evaluators and refiners.

## Assignment 5 Integration

Assignment 5's lesson becomes the persistent planning/task system.

The expensive full gap-analysis pass should not run before every feature.

Run planning/reconciliation when:

- the GDD materially changes
- the backlog is empty/low
- a milestone completes
- a discovered dependency changes the plan
- the current repository and task graph disagree
- a human explicitly requests it

Assignment 5's implementation agent can also be reused as a bounded ticket implementer/refiner, as demonstrated by Assignment 6.

## Assignment 6 / GER Integration

Assignment 6 proved the following reusable execution pattern:

```text
Generator / Implementer
        ↓
Evaluator
        ↓
Validation Evidence
    ┌───┴────┐
   PASS     FAIL
    ↓         ↓
Approved   Refiner
              ↓
          Evaluator
              ↓
        retry to budget
              ↓
       Circuit Breaker
              ↓
       Human Review
```

The Assignment 6 camera run established several production rules:

1. A static evaluator PASS is not sufficient for interactive Unity features.
2. Runtime observations must be able to re-enter the repair loop as structured feedback.
3. Validation history should be append-only/auditable enough to reconstruct what happened.
4. A Refiner that makes no relevant change while unresolved failures remain has not made progress.
5. No-op repair attempts count against the repair budget.
6. Circuit Breakers bound the number of retries and escalate rather than looping forever.
7. The evaluator contract should be task/GDD-specific, not merely "does the code compile?"

Reference:

`Assignment6GER/README_Assignment6.md`

## Validation Evidence Model

Future ticket execution should build a validation/evidence bundle rather than relying on a single PASS/FAIL source.

Possible evidence sources:

```text
Git / scope validation
Static checks
Unity compilation
EditMode tests
PlayMode tests
Runtime observations
Simulation/adversarial-agent results (later)
Task/GDD semantic evaluator
Style evaluator for player-facing content (later)
Fresh semantic diff review
```

Not every ticket needs every evaluator.

The task type and acceptance criteria determine which evidence is required.

Failures should be normalized into structured feedback that the Refiner can consume.

## Assignment 7 / Style Guide Integration

Assignment 7 should not become a parallel autonomous architecture.

When the game has an appropriate player-facing content target, its Style Guide Agent should be implemented as an evaluator specialization inside GER:

```text
Generator
  ↓
Style Evaluator
  ↓
SCORE + REASON
  ↓
Refiner
  ↓
Style Evaluator
```

The style evaluator must use actual No Safe Circle canon/prior work and should not invent a new universe merely to create style constraints.

Potential targets should be selected from real game needs as the playable game develops.

## Autonomous Supervisor

The supervisor, not Claude, owns the continuous loop.

Conceptually:

```python
while game_not_complete:
    task = taskctl.next_ready()

    if task is None:
        run_reconciliation_or_planning_cycle()
        continue

    claim(task)
    create_branch(task)
    create_worktree(task)
    open_draft_pr(task)

    context = build_context(task)

    result = run_bounded_ger_execution(task, context)

    if result.escalated:
        mark_needs_review(task)
        continue

    run_fresh_ai_diff_review(task)

    if everything_passes:
        merge(task)
        mark_done(task)
    else:
        repair_or_escalate(task)
```

The implementation of `run_bounded_ger_execution` should choose the relevant evaluator/validation profile for the task rather than running every possible check blindly.

## Safety / Cost Controls

Per-ticket limits should eventually include:

- maximum agent runs
- maximum repair attempts
- maximum runtime
- model/token budget
- maximum no-progress attempts

Stop/escalate for:

- repeated validation failures
- GDD ambiguity
- architecture-changing dependencies
- Unity scene/prefab merge conflicts
- task scope expansion
- budget exhaustion
- repeated no-op refinement
- repeated GER failure

Autonomous means "continue safe bounded work," not "spend forever."

## Parallelism

Do not start with multiple Claude workers.

First make one worker reliable.

Later allow parallel workers only when conflict/resource claims do not overlap.

Unity scene/prefab work should be treated conservatively.

## Near-Term Build Strategy

Do not finish the entire autonomous platform before building more of the game.

The next strategy is:

1. Reconcile current `main`.
2. Implement the minimum persistent task graph.
3. Seed the graph from actual current project state.
4. Compute the ready frontier.
5. Select a real ready gameplay task.
6. Use the proven GER pattern to implement/repair it.
7. Feed the result back into the graph.
8. Expand infrastructure only when the next real task requires it.

This keeps pipeline development tied to actual capstone progress.

## High-Level Build Milestones

1. Persistent task artifacts + `taskctl`
2. RAG canon service + Unity/code scanner + context builder
3. One-ticket autonomous supervisor with branch/worktree/PR
4. Productionize GER execution + deterministic/Unity/runtime validation + evaluator profiles
5. GitHub dashboard sync + continuous scheduling + blocker handling + budgets + eventual parallelism

Assignment 6 has already produced a working prototype of Milestone 4's central repair-loop concept. The milestone is still future work because it has not yet been integrated into the supervisor/task system.

## Working Rule

Build this in small stages.

Do not try to implement the full autonomous pipeline in one chat/context or one coding session.

Each new window should work on one milestone/subsystem and leave durable repository documentation before ending.

The pipeline should increasingly build No Safe Circle, not become a separate project that indefinitely delays No Safe Circle.
