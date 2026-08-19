# No Safe Circle — Autonomous AI Development Pipeline
## Master Context / Architecture Handoff

Use this file to start a fresh ChatGPT window when working on the autonomous development pipeline.

## Project

Repository:
https://github.com/cathode26/NoSafeCircle

Current course work has produced useful building blocks:

- Assignment 3: Agent Crew concept (Planner → Implementer → Validator).
- Assignment 4: RAG pipeline over the No Safe Circle GDD.
- Assignment 5: goal-oriented analysis and implementation agent.
- Assignment 6: GER — Generator → Evaluator → Refiner → Circuit Breaker.

The goal now is to evolve these pieces into a practical system that can autonomously continue developing No Safe Circle while keeping project state durable, observable, inexpensive to reason about, and resumable after failures.

## Core Architectural Decision

The LLM should NOT own the project state or the autonomous loop.

A local deterministic supervisor should own the loop.

Claude should be a bounded worker that receives one small task at a time.

Persistent project state should live in local/versioned artifacts and GitHub, not in Claude's context window.

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
Claude Worker / Agent Crew
 ↓
GER when generated content is required
 ↓
Deterministic Validation
 ↓
Unity Validation
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

## Guiding Principle

**Use code for facts and computation. Use the LLM for judgment.**

Deterministic/local work includes file enumeration, code/component detection, Unity YAML inspection, `.meta` GUID relationships, dependency readiness, ready-queue computation, obvious ranking, graph validation, Git checks, and Unity tests.

LLM work includes semantic decomposition of tasks, interpreting ambiguous GDD intent, resolving real planning ties, bounded implementation planning/coding, semantic diff review, content generation, and refinement.

## Sources of Truth

### Canon
The GDD is canonical game-design information. Assignment 4 RAG should retrieve only relevant GDD chunks instead of repeatedly sending the whole GDD to the LLM.

### Durable Work Definition
Local task artifacts should define durable work:

```text
Tasks/
  NSC-001.yaml
  NSC-002.yaml
  ...
```

Each task should define ID, title, type, source GDD requirements, dependencies, scope, out-of-scope work, acceptance criteria, priority, risk, effort, optional resource/conflict claims, and optional parent/epic.

### Operational Status
GitHub Issues + GitHub Projects should be the human-facing dashboard for Backlog, Ready, In Progress, Blocked, Validating, Needs Review, and Done.

Do not make transient “Claude is working right now” state part of task-branch commits if that can create conflicting operational state.

## Task Dependencies

A task is ready only when all required dependencies are complete/merged.

Example:

```text
NSC-010 Fixed Isometric Camera
   ↓
NSC-011 Tilemap World Foundation
   ↓
NSC-012 Navigation Foundation
   ↓
NSC-013 Melee Enemy
```

Separately:

```text
NSC-014 Mana
   ↓
NSC-021 Fireball
NSC-022 Frost Field
NSC-023 Force Wave
```

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

“Done” means merged into `main`, not merely “Claude says it finished.” Prefer squash merging eventually so main has one clean logical commit per ticket. Create a Draft PR early so the human can watch work in progress.

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

## Assignment 4 Integration

RAG answers: **What does the GDD say about this task?**

A context builder should retrieve only the task's relevant canonical chunks. RAG is desired-state/canon retrieval, not codebase truth.

## Assignment 5 Integration

Assignment 5's lesson becomes the persistent planning/task system. The expensive full gap-analysis pass should not run before every feature.

Run planning/reconciliation when the GDD materially changes, the backlog is empty/low, a milestone completes, a discovered dependency changes the plan, or a human explicitly requests it.

## Assignment 6 / GER Integration

GER applies to generated artifacts/content:

```text
Generator
 ↓
Evaluator
 ↓ PASS → Approved Artifact

FAIL
 ↓
Refiner
 ↓
Evaluator
 ↓
(retry to configured limit)
 ↓
Circuit Breaker
 ↓
Needs Human Review
```

RAG feeds the evaluator with relevant GDD rules. Generated artifacts can become dependencies of implementation tasks.

Example:

```text
NSC-035 Generate Bone Archive Encounter Spec
        ↓
approved artifact
        ↓
NSC-040 Implement Bone Archive Encounter
```

## Autonomous Supervisor

The supervisor, not Claude, owns the loop.

```python
while game_not_complete:
    task = taskctl.next_ready()
    if task is None:
        run_planning_cycle()
        continue

    claim(task)
    create_branch(task)
    create_worktree(task)
    open_draft_pr(task)

    context = build_context(task)
    run_worker(task, context)

    if task.requires_generated_content:
        run_ger(task)

    run_deterministic_validation(task)
    run_unity_validation(task)
    run_fresh_ai_diff_review(task)

    if everything_passes:
        merge(task)
        mark_done(task)
    else:
        repair_or_escalate(task)
```

## Safety / Cost Controls

Per-ticket limits should eventually include maximum agent runs, repair attempts, runtime, and budget. Stop/escalate for repeated validation failures, GDD ambiguity, architecture-changing dependencies, Unity scene/prefab merge conflicts, task scope expansion, budget exhaustion, and repeated GER failure.

Autonomous means “continue safe bounded work,” not “spend forever.”

## Parallelism

Do not start with multiple Claude workers. First make one worker reliable. Later allow parallel workers only when conflict/resource claims do not overlap.

Examples:

```yaml
claims:
  - System:PlayerResources
```

or:

```yaml
claims:
  - Scene:DoorPrototype
```

Unity scene/prefab work should be treated conservatively.

## High-Level Build Milestones

1. Persistent task artifacts + `taskctl`
2. RAG canon service + Unity/code scanner + context builder
3. One-ticket autonomous supervisor with branch/worktree/PR
4. Validation loop + Unity + AI diff review + GER
5. GitHub dashboard sync + continuous scheduling + blocker handling + budgets + eventual parallelism

## Working Rule

Build this in small stages. Do not try to implement the full autonomous pipeline in one chat/context or one coding session. Each new window should work on one milestone/subsystem and leave durable repo documentation before ending.
