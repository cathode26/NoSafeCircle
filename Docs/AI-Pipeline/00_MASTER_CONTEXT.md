# No Safe Circle — Autonomous AI Development Pipeline

## Master Context / Architecture Handoff

Use this file for the durable target architecture when continuing work on the autonomous development pipeline.

For exact current implementation status, always read `CURRENT_STATE.md` first.

Last architecture/status reconciliation: 2026-08-21, after Milestone 1 completion and the post-M1 adversarial-architecture-review branch merge.

## Current Architecture Status

The architecture is no longer purely prospective.

**Milestone 1 is implemented and merged.** The repository now contains:

- a human-approved persistent work graph under `Tasks/`;
- stable `NSC-###` work IDs;
- reconciliation-key provenance;
- deterministic graph validation;
- deterministic dependency/parent hierarchy reconstruction;
- exclusive-resource metadata;
- project-level non-code requirements;
- a working local `taskcontrol` CLI;
- a real deterministic ready frontier.

The current graph contains 37 work records and the first real `taskcontrol ready` calculation returned seven executable one-agent implementation tasks.

The next planned infrastructure milestone is Milestone 2: targeted GDD/project context, Progressive Decomposition, and Artifact Authority.

Before substantial Milestone 2 expansion, the M1-complete architecture should be reviewed through `Pipeline/ArchitectureReview/` and any accepted architectural corrections should be persisted in `DECISIONS.md` and `CURRENT_STATE.md`.

## Project

Repository: `https://github.com/cathode26/NoSafeCircle`

Course work already provides reusable building blocks:

- Assignment 3: Agent Crew concept — Planner → Implementer → Validator.
- Assignment 4: RAG/retrieval over the No Safe Circle GDD.
- Assignment 5: goal-oriented gap analysis and bounded implementation agent.
- Assignment 6: working GER implementation — Implement/Generate → Evaluate → Refine → Circuit Breaker, including runtime-feedback repair.
- Assignment 7: not yet implemented; intended to become a scored Style Evaluator specialization when real authorized style-sensitive artifact work exists.

The production goal is to evolve these pieces into a system that can continue developing No Safe Circle while keeping project state durable, observable, resumable after model/context failures, bounded in cost, grounded in real Unity evidence, and protected from silent AI invention of missing game design.

## Core Architectural Decision

The LLM does **not** own durable project state or the continuous autonomous loop.

A local deterministic supervisor eventually owns the loop.

Claude or another coding model is a bounded worker that receives one small piece of approved work at a time.

Persistent project state lives in repository artifacts and later GitHub operational state, not in a model context window.

A worker may implement or generate work, but it does not declare that work complete. Completion is determined by project evidence plus merge/approval state.

An implementation worker also does not silently invent missing game design. Missing design becomes an explicit artifact proposal.

## Desired End-to-End Loop

```text
GDD / Root Canon
 ↓
Persistent Work Graph                         ← M1 COMPLETE
 ↓
Ready / Near-Ready Frontier                   ← M1 COMPLETE
 ↓
Targeted Task + GDD + Project Context          ← M2 NEXT
 ↓
Progressive Decomposer
 ↓
Enough approved information?
 ├─ yes → Concrete child work
 └─ no  → Proposed artifact
               ↓
         Artifact Authority Gate
               ↓
          Authorized?
          /       \
        yes        no
         ↓          ↓
   Artifact Generator   Re-plan / Human Review
         ↓
      Artifact GER
         ├─ Canon / Design Evaluator
         ├─ Completeness Evaluator
         └─ Style Evaluator when applicable
         ↓
   Approved Artifact
         ↓
   Back to Decomposer
         ↓
   Concrete Work Item
         ↓
Local Supervisor                               ← M3
 ↓
Claim Ticket
 ↓
Git Branch + Git Worktree + Draft PR
 ↓
Build Small Context Package
 ↓
Bounded Worker / Agent Crew
 ↓
==============================
        GER EXECUTION LOOP                     ← M4 production integration
------------------------------
Implement / Generate
 ↓
Task/GDD/Artifact Evaluation
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
PR Merge / Artifact Approval
 ↓
Work = Complete
 ↓
Dependency Graph Recalculates
 ↓
New Work Becomes Ready
 ↓
Continuous Safe Backlog Processing             ← M5
```

The exact evaluator order may vary by work type, but cheap deterministic failures should be detected before spending model tokens on semantic review whenever practical.

## Guiding Principle

**Use deterministic code for facts and computation. Use LLMs for semantic judgment and bounded implementation.**

Deterministic/local responsibilities include:

- work identity and dependency bookkeeping;
- graph validation/readiness;
- file enumeration;
- code/component detection;
- Unity YAML inspection;
- `.meta` GUID relationships;
- obvious project-state queries;
- Git/scope checks;
- compilation/test orchestration;
- progress/no-op detection;
- budget/circuit-breaker bookkeeping.

LLM responsibilities include:

- semantic decomposition of bounded near-frontier work;
- deciding whether approved information is sufficient to decompose;
- distinguishing missing design from oversized implementation scope;
- interpreting genuinely ambiguous intent;
- bounded implementation planning/coding;
- semantic task/GDD evaluation;
- fresh semantic diff review;
- authorized design/content generation;
- style evaluation/refinement;
- repair from structured failure evidence.

## Sources of Truth

### Root Canon

The current GDD is root game-design canon.

RAG should retrieve only relevant canonical chunks instead of repeatedly sending the entire GDD to a model.

Prior assignment artifacts may provide history or reusable machinery, but they do not override current GDD or integrated repository state.

### Approved Design Extensions

Approved artifact outputs may later extend root canon with project-authorized detail.

An artifact becomes trusted only after this path:

```text
Artifact proposal
 ↓
Artifact Authority Gate
 ↓
Authorized generation
 ↓
Required evaluators / GER
 ↓
Approved artifact
 ↓
Trusted downstream input
```

Approved artifacts may add detail only inside the authority granted to them. They may not contradict or silently replace GDD canon.

Unapproved drafts are not trusted design input.

### Codebase Truth

The current integrated `main` branch is the authority for what implementation actually exists and is complete.

Old assignment planning output is not current codebase truth unless reconciled against the repository.

### Durable Work Definition

The living operational work graph now exists under:

```text
Tasks/
  NSC-001.yaml
  ...
  NSC-037.yaml
```

Initial supported work kinds are:

```text
feature
artifact
implementation
```

Definitions:

- `feature` — organizational/high-level work that may require progressive decomposition; never a direct implementation handoff.
- `artifact` — work whose output is approved design/content; complete only after required authority/evaluation/promotion.
- `implementation` — concrete repository work that can be executed when dependencies and execution scope allow it.

Stable `reconciliation_key` values preserve traceability back to the reconciliation record that proposed each initial work item.

### Operational Status

Durable task definitions currently use `open` / `complete`.

Later, GitHub Issues/Projects should provide human-facing transient execution visibility such as:

- Backlog
- Ready
- In Progress
- Blocked
- Validating
- Needs Review
- Done

Do not make ephemeral “worker is running” state a constantly committed task-file concern if the supervisor/GitHub can own it safely.

## Milestone 1 Persistent Work Graph

Milestone 1 is complete. See `01_MILESTONE_TASK_GRAPH.md` for its completion record.

The initial graph was created through:

```text
GDD + repository state
 ↓
immutable reconciliation snapshot
 ↓
independent multi-model verification
 ↓
bounded repair / re-verification
 ↓
0 final material findings
 ↓
human approval
 ↓
deterministic bootstrap
 ↓
persistent graph
```

Approved reconciliation:

`20260821T193541Z-998ee7b5`

Successful verification:

`20260821T195959Z-43dba5de`

The one-time bootstrap is marked by:

`Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json`

Do not rerun the initial `--apply` bootstrap after that marker exists.

### Current Task-Control Interface

```text
python Pipeline/TaskGraph/taskcontrol.py validate
python Pipeline/TaskGraph/taskcontrol.py list
python Pipeline/TaskGraph/taskcontrol.py show NSC-003
python Pipeline/TaskGraph/taskcontrol.py ready
python Pipeline/TaskGraph/taskcontrol.py graph
```

A work item is executable-ready only when it is open, is an `artifact` or `implementation`, has `execution_scope: single_agent`, and all dependencies are complete.

This readiness calculation is deterministic.

## Reconciliation Boundary

Reconciliation is an immutable point-in-time observation, not the mutable work database.

Every full reconciliation run creates a new versioned snapshot of GDD requirements versus repository state.

A later reconciliation may propose additions/changes/conflicts against the persistent graph, but the Reconciliation Agent does not directly rewrite `Tasks/*.yaml`.

Future graph changes must cross an explicit deterministic diff/review/apply boundary.

Old reconciliation snapshots remain historically true even after later implementation changes the repository.

The persistent graph is the living operational state.

## Progressive Task Decomposition

The graph should **not** contain the entire game's lowest-level implementation plan in advance.

High-level work is decomposed just in time as it approaches the actionable frontier.

The Progressive Decomposer must first determine *why* an item is not a safe one-agent handoff.

Two distinct cases exist:

1. **Design decomposition** — approved design/content is missing or too coarse. Identify the smallest missing artifact needed to continue.
2. **Execution decomposition** — design is concrete, but the implementation record still bundles too many responsibilities/validation targets. Split only already-approved responsibilities.

The Decomposer must not generate missing design during the same decision that detects the gap.

Detecting missing design and creating missing design are separate authority events.

## Artifact Authority

Before a proposed design/content artifact may be generated, the Artifact Authority Gate answers:

1. Is the artifact necessary to progress parent work?
2. Which current GDD requirements or approved artifacts authorize it?
3. Which design decisions may it make?
4. Which areas must it not invent, replace, or contradict?

Possible outcomes conceptually include:

```text
AUTHORIZED
REJECTED
NEEDS_HUMAN_REVIEW
```

The gate authorizes existence/generation. It does not judge the quality of the generated artifact.

After authorization, Artifact GER and applicable evaluator profiles determine whether the artifact is good enough to promote to trusted input.

## Assignment 3 Integration

Assignment 3's crew belongs **inside bounded ticket execution**:

```text
Persistent Work Graph chooses WHAT
        ↓
Task Context
        ↓
Planner
        ↓
Implementer
        ↓
Validator
```

The crew should not reconstruct the global roadmap.

## Assignment 4 Integration

Assignment 4 RAG answers:

> What does the GDD say about this work?

It supplies canonical evidence to context building, decomposition, semantic evaluation, and refinement.

RAG is desired-state/canon retrieval, not repository-state truth.

Milestone 2 should reuse/wrap this machinery rather than rebuild a second RAG system without need.

## Assignment 5 Integration

Assignment 5's goal-oriented lesson is now represented by persistent work state plus progressive decomposition.

Full gap/reconciliation analysis should not run before every feature.

Use full reconciliation when justified by events such as:

- material GDD change;
- milestone completion;
- low/empty backlog;
- significant newly discovered dependency;
- disagreement between repository and work graph;
- explicit human request.

Normal progress uses the persistent graph.

Assignment 5's implementation agent may also be reused as a bounded implementer/refiner, as Assignment 6 demonstrated.

## Assignment 6 / GER Integration

Assignment 6 proved the central repair-loop concept needed later for production execution:

```text
Implement / Generate
 ↓
Evaluate
 ↓
Validation Evidence
 ├─ PASS → approved
 └─ FAIL → structured feedback → Refiner → re-evaluate
                                      ↓
                               retry to budget
                                      ↓
                               Circuit Breaker
```

The camera run established production rules:

1. Static evaluator PASS is not sufficient for interactive Unity behavior.
2. Runtime observations must re-enter the repair loop as structured evidence.
3. Validation history should be auditable enough to reconstruct what happened.
4. A Refiner that makes no relevant change while failures remain has not made progress.
5. No-op repair attempts count against the repair budget.
6. Circuit Breakers bound retries and escalate instead of looping forever.
7. Evaluator contracts should be task/GDD specific, not merely “does it compile?”

Reference:

`Assignment6GER/README_Assignment6.md`

## Validation Evidence Model

Production execution should build an evidence bundle rather than trust one PASS/FAIL source.

Possible evidence sources include:

```text
Git / scope validation
Static checks
Unity compilation
EditMode tests
PlayMode tests
Runtime observations
Simulation/adversarial-agent results (later)
Task/GDD semantic evaluation
Artifact canon/design evaluation
Artifact completeness evaluation
Style evaluation when applicable
Fresh semantic diff review
```

Not every work item needs every evaluator.

Work type, source requirements, acceptance criteria, and risk determine which evidence is required.

Failures should be normalized into structured Refiner input.

## Assignment 7 / Style Evaluator Integration

Assignment 7 should not become a parallel autonomous architecture.

When Progressive Decomposition identifies an authorized style-sensitive artifact, Assignment 7 can supply a scored evaluator inside Artifact GER:

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

The Style Evaluator judges quality/style of content already authorized to exist.

It does not authorize creation of new canon or design content.

Artifact authority and artifact quality remain separate decisions.

## Git Model

Autonomous implementation workers must not develop directly on `main`.

For each implementation ticket, Milestone 3 should eventually create a branch and worktree such as:

```text
branch: claude/NSC-003-player-movement
worktree: .worktrees/NSC-003/
```

Expected lifecycle:

```text
Ready → Claimed → In Progress → Validating → PR Ready → Merged → Done
```

“Done” means merged/integrated evidence supports completion, not merely that a worker says it finished.

Draft PRs should be opened early so humans can inspect ongoing work.

## Autonomous Supervisor

The supervisor, not the model, owns the eventual continuous loop.

Conceptually:

```python
while game_not_complete:
    ready = taskcontrol.ready()

    if not ready:
        expand_near_frontier_or_reconcile()
        continue

    work = choose_safe_ready_work(ready)

    if work_needs_decomposition(work):
        run_progressive_decomposition(work)
        continue

    if work.kind == "artifact":
        authorize_generate_evaluate_or_escalate(work)
        continue

    claim(work)
    create_branch_worktree_and_draft_pr(work)
    context = build_compact_context(work)
    result = run_bounded_execution_ger(work, context)

    if result.needs_human:
        preserve_and_escalate(work)
        continue

    if validation_and_review_pass(result):
        merge(work)
        mark_complete(work)
```

This remains target architecture; the supervisor itself is not yet implemented.

## Safety / Cost Controls

Per-work limits should eventually include:

- maximum agent runs;
- maximum repair attempts;
- maximum runtime;
- model/token budget;
- maximum no-progress attempts.

Stop/escalate for:

- repeated validation failure;
- GDD ambiguity;
- unauthorized design expansion;
- architecture-changing dependencies;
- Unity scene/prefab/shared-resource conflict;
- scope expansion;
- budget exhaustion;
- repeated no-op refinement.

Autonomous means “continue safe bounded work,” not “spend forever” or “invent whatever is missing.”

## Parallelism

Do not start with multiple coding workers.

First make one-ticket execution reliable and restartable.

Later parallelism must honor exclusive-resource claims and be conservative around Unity scenes, prefabs, ProjectSettings, Input Actions, and shared builder scripts.

## Near-Term Build Strategy

Milestone 1 is finished. Do not rebuild it.

The current strategy is:

1. confirm `taskcontrol validate` and `taskcontrol ready` remain truthful;
2. run/review the post-M1 adversarial architecture checkpoint;
3. use one real ready/near-ready No Safe Circle task as the anchor for the next slice;
4. build the smallest targeted task-context path needed for that work;
5. reuse Assignment 4 RAG and existing deterministic reconciliation/scanner capabilities where practical;
6. add Progressive Decomposition only when a near-frontier item actually needs it;
7. create artifact proposals rather than invent missing design;
8. authorize/evaluate generated artifacts before downstream use;
9. add the single-ticket supervisor only after compact task context is reliable;
10. productionize generic GER/Unity validation around real tickets;
11. enable continuous autonomous backlog processing only after single-ticket execution is trustworthy;
12. add parallel workers last.

A strong current real-task anchor is `NSC-003` Player Movement because it is already ready, bounded, and unlocks multiple later systems.

This keeps pipeline development tied to capstone progress.

## High-Level Build Milestones

1. **Persistent work artifacts + deterministic `taskcontrol` — COMPLETE**
2. **RAG canon service + deterministic project scanner + compact context builder + Progressive Decomposer + Artifact Authority Gate — NEXT**
3. One-ticket autonomous supervisor with claims + branch/worktree/Draft PR
4. Productionize GER execution + deterministic/Unity/runtime validation + evaluator profiles
5. Continuous scheduling + blocker handling + budgets + GitHub visibility + eventual safe parallelism

Assignment 6 has already produced a working prototype of Milestone 4's central repair-loop concept, so Milestone 4 is production integration rather than invention from zero.

## Working Rule

Build in small stages.

Do not try to implement the full autonomous pipeline in one context or coding session.

Each meaningful session should leave durable repository state/documentation so the next session can resume without the previous chat transcript.

From Milestone 2 onward, infrastructure should increasingly be proven by advancing actual No Safe Circle gameplay rather than becoming a separate project that indefinitely delays the game.
