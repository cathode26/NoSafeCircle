# No Safe Circle — Autonomous AI Development Pipeline

## Master Context / Architecture Handoff

Use this file to start a fresh ChatGPT window when working on the autonomous development pipeline.

Last architecture reconciliation: 2026-08-18, after Assignment 6 and progressive-decomposition review.

## Project

Repository: `https://github.com/cathode26/NoSafeCircle`

Current course work has produced useful building blocks:

- Assignment 3: Agent Crew concept (Planner → Implementer → Validator).
- Assignment 4: RAG pipeline over the No Safe Circle GDD.
- Assignment 5: goal-oriented analysis and implementation agent.
- Assignment 6: working GER implementation — Generator/Implementer → Evaluator → Refiner → Circuit Breaker.
- Assignment 7: not yet implemented; intended to become a scored Style Evaluator specialization for authorized generated content.

The goal is to evolve these pieces into a practical system that can autonomously continue developing No Safe Circle while keeping project state durable, observable, inexpensive to reason about, resumable after failures, grounded in real Unity evidence, and protected from silent AI invention of missing game design.

## Core Architectural Decision

The LLM should NOT own project state or the continuous autonomous loop.

A local deterministic supervisor should own the loop.

Claude should be a bounded worker that receives one small piece of work at a time.

Persistent project state should live in local/versioned artifacts and GitHub, not in Claude's context window.

The worker may implement or generate work, but it does not get to declare that work complete. Completion is determined by project evidence and merge/approval state.

An implementation worker also does not get to silently invent missing game design. Missing design becomes an explicit artifact proposal.

## Post-Assignment-6 Architecture Correction

The original architecture treated GER mainly as a gate for generated content.

Assignment 6 demonstrated a broader and more useful role.

GER is the bounded self-correction loop around project work:

```text
Selected Bounded Work
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

The important abstraction is not "generated content." It is "a bounded work product that can be evaluated, repaired, and either approved or escalated."

## Progressive Task Decomposition

The task graph does not need to contain the entire game's lowest-level implementation plan in advance.

High-level work should be decomposed just in time as it approaches the actionable frontier.

The Progressive Decomposer asks:

> Is there enough approved design information to produce bounded executable child work?

If yes, it creates concrete child artifact or implementation work.

If no, it identifies the smallest missing design/content artifact needed to continue.

The Decomposer must not generate that missing design during the same decision.

Detecting that design is missing and creating that design are separate actions.

This prevents implementation agents from silently becoming game designers.

## Artifact Authority

A proposed design/content artifact must be authorized before generation.

The Artifact Authority Gate answers:

1. Is this artifact actually necessary to progress the parent work?
2. Which current GDD requirements or already-approved artifacts justify its creation?
3. Which design decisions may the artifact make?
4. Which design areas must it not invent, replace, or contradict?

If the proposal is not authorized, it returns to decomposition or human review.

The Authority Gate decides whether generation is permitted.

It does not decide whether the generated artifact is good.

## Canon and Approved Design Extensions

The GDD is root canon.

Approved artifacts may become project-authorized design extensions.

An AI-generated artifact follows this trust path:

```text
Proposed Artifact
    ↓
Artifact Authority Gate
    ↓
Authorized Generation
    ↓
Artifact GER
    ↓
Required Evaluators Pass
    ↓
Approved Artifact
    ↓
Trusted downstream design input
```

An approved artifact may add detail where the GDD leaves room for expansion.

It may not contradict or silently replace GDD canon.

Downstream agents may rely on approved artifacts but not on unapproved generated drafts.

## Desired End-to-End Loop

```text
GDD / Root Canon
 ↓
Persistent Work Graph
 ↓
Ready / Near-Ready Frontier
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
                ↑ Assignment 7
         ↓
   Approved Artifact
         ↓
   Back to Decomposer
         ↓
   Concrete Work Item
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
Repeat
```

The exact order of evaluator sub-checks may vary by work type, but cheap deterministic failures should be detected before spending model tokens on semantic review whenever practical.

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

- semantic decomposition of high-level work
- deciding whether existing information is sufficient to decompose
- interpreting ambiguous GDD intent
- evaluating whether proposed design expansion is justified
- resolving real planning ties
- bounded implementation planning/coding
- semantic GDD/task evaluation
- semantic diff review
- authorized content/design generation
- style evaluation/refinement
- refinement from structured failure feedback

## Sources of Truth

### Root Canon

The GDD is canonical game-design information.

Assignment 4 RAG should retrieve only relevant GDD chunks instead of repeatedly sending the whole GDD to the LLM.

Prior assignment artifacts may provide evidence or reusable machinery, but they do not override the current GDD or current `main` branch.

### Approved Design Extensions

Approved artifact outputs may extend root canon with additional project-authorized detail.

They must:

- have passed the Artifact Authority Gate before generation;
- have passed their required evaluators after generation;
- retain traceability to the parent work and source requirements;
- never override contradictory GDD canon.

Unapproved drafts are not trusted design input.

### Codebase Truth

The current `main` branch is the truth for what has actually been integrated.

Old Assignment 5 goal-selection output must not be treated as current codebase truth without rescanning/reconciling the repository.

### Durable Work Definition

Local work artifacts should define durable work:

```text
Tasks/
  NSC-001.yaml
  NSC-002.yaml
  ...
```

Each work item should define:

- ID
- title
- kind
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
- optional parent/feature
- optional artifact output path

Initial work kinds:

```text
feature
artifact
implementation
```

Definitions:

- `feature`: high-level work that may require progressive decomposition; not directly executable.
- `artifact`: work whose output is a design/content artifact; complete only after required approval.
- `implementation`: bounded project work that can be executed by an implementation worker.

A work item may later declare which validation/evaluator profiles apply, but do not over-design this before Milestone 1 works.

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

A work item is ready only when all required dependencies are complete/approved and the work kind is executable.

Feature nodes are not directly returned as ready implementation work.

Example candidate structure:

```text
Five-Room World [feature]
   ↓
Room 3 [feature]
   ↓
Room 3 Encounter Specification [artifact]
   ↓
Room 3 Layout [implementation]
Room 3 Enemy Configuration [implementation]
Room 3 Door Configuration [implementation]
Room 3 Validation [implementation]
```

The exact structure is created progressively, not fully in advance.

Existing technical candidates may still include:

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

Never allow autonomous implementation workers to develop directly on `main`.

For each implementation ticket:

```text
branch: claude/NSC-014-mana-resource
worktree: .worktrees/NSC-014/
```

Lifecycle:

```text
Ready → Claimed → In Progress → Validating → PR Ready → Merged → Done
```

"Done" means merged into `main`, not merely "Claude says it finished."

Artifact tasks may use an equivalent approval lifecycle, but artifact promotion/versioning details should be added only when Milestone 2 is implemented.

Prefer squash merging eventually so `main` has one clean logical commit per ticket. Create a Draft PR early so the human can watch work in progress.

## Assignment 3 Integration

Assignment 3's crew belongs inside bounded execution:

```text
Work Graph chooses WHAT
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

> What does the GDD say about this work?

A context builder should retrieve only the work item's relevant canonical chunks.

RAG is desired-state/canon retrieval, not codebase truth.

For progressive decomposition, RAG supplies the canonical constraints needed to determine whether more design is required.

For GER, retrieved GDD evidence can be supplied to semantic evaluators and refiners.

## Assignment 5 Integration

Assignment 5's lesson becomes the persistent planning/work system plus progressive decomposition.

The expensive full gap-analysis pass should not run before every feature.

Run full planning/reconciliation when:

- the GDD materially changes
- the backlog is empty/low
- a milestone completes
- a discovered dependency changes the plan
- the current repository and work graph disagree
- a human explicitly requests it

Normal progress should use the persistent graph.

Full reconciliation is append-only observation, not graph mutation.

Each run produces a new immutable snapshot. The old snapshot remains historically
true even after later work changes the repository. The persistent work graph is
the living operational state.

When a later reconciliation disagrees with `Tasks/*.yaml`, the result is a
proposed graph delta/conflict report. A deterministic reconciliation-diff/apply
step must decide what changes are safe to apply; the Reconciliation Agent does
not cascade edits through the graph itself.

As high-level work approaches the frontier, the Progressive Decomposer semantically expands only that bounded area.

Assignment 5's implementation agent can also be reused as a bounded implementer/refiner, as demonstrated by Assignment 6.

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

Future execution should build a validation/evidence bundle rather than relying on a single PASS/FAIL source.

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
Artifact canon/design evaluator
Artifact completeness evaluator
Style evaluator for player-facing content
Fresh semantic diff review
```

Not every work item needs every evaluator.

The work kind, type, source requirements, and acceptance criteria determine which evidence is required.

Failures should be normalized into structured feedback that the Refiner can consume.

## Assignment 7 / Style Guide Integration

Assignment 7 should not become a parallel autonomous architecture.

Progressive decomposition may identify authorized player-facing or style-sensitive artifact work.

After the Artifact Authority Gate approves creation, the artifact can be generated through GER.

Assignment 7 supplies a specialized scored evaluator:

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

The style evaluator must use actual No Safe Circle canon and approved prior work.

It judges whether authorized generated content matches No Safe Circle.

It does not authorize creation of new canon or design content.

Artifact authority and artifact quality are separate decisions.

## Autonomous Supervisor

The supervisor, not Claude, owns the continuous loop.

Conceptually:

```python
while game_not_complete:
    work = taskcontrol.next_ready()

    if work is None:
        work = expand_near_ready_feature_or_reconcile()

    if work.kind == "feature":
        run_progressive_decomposition(work)
        continue

    if work.kind == "artifact":
        if not artifact_is_authorized(work):
            authorize_or_escalate(work)
            continue
        run_bounded_artifact_ger(work)
        approve_or_escalate(work)
        continue

    claim(work)
    create_branch(work)
    create_worktree(work)
    open_draft_pr(work)

    context = build_context(work)
    result = run_bounded_ger_execution(work, context)

    if result.escalated:
        mark_needs_review(work)
        continue

    run_fresh_ai_diff_review(work)

    if everything_passes:
        merge(work)
        mark_done(work)
    else:
        repair_or_escalate(work)
```

This is conceptual architecture, not Milestone 1 scope.

## Safety / Cost Controls

Per-work limits should eventually include:

- maximum agent runs
- maximum repair attempts
- maximum runtime
- model/token budget
- maximum no-progress attempts

Stop/escalate for:

- repeated validation failures
- GDD ambiguity
- unauthorized design expansion
- architecture-changing dependencies
- Unity scene/prefab merge conflicts
- work scope expansion
- budget exhaustion
- repeated no-op refinement
- repeated GER failure

Autonomous means "continue safe bounded work," not "spend forever" or "invent whatever is missing."

## Parallelism

Do not start with multiple Claude workers.

First make one worker reliable.

Later allow parallel workers only when conflict/resource claims do not overlap.

Unity scene/prefab work should be treated conservatively.

## Near-Term Build Strategy

Do not finish the entire autonomous platform before building more of the game.

The next strategy is:

1. Produce an immutable reconciliation snapshot of current `main` against the GDD.
2. Review its proposed graph delta.
3. Implement the minimum persistent work graph.
4. Seed the graph from approved reconciliation records while preserving traceability.
5. Support `feature`, `artifact`, and `implementation` kinds.
6. Compute the ready/near-ready frontier.
7. Begin Milestone 2 only after Milestone 1 works.
8. Use progressive decomposition only on bounded near-frontier work.
9. Create artifact proposals when design is missing.
10. Authorize and evaluate generated artifacts before downstream use.
11. Execute real implementation work through the proven GER pattern.
12. Expand infrastructure only when the next real task requires it.

This keeps pipeline development tied to actual capstone progress.

## High-Level Build Milestones

1. Persistent work artifacts + deterministic `taskcontrol`
2. RAG canon service + Unity/code scanner + context builder + Progressive Decomposer + Artifact Authority Gate
3. One-ticket autonomous supervisor with branch/worktree/PR
4. Productionize GER execution + deterministic/Unity/runtime validation + evaluator profiles
5. GitHub dashboard sync + continuous scheduling + blocker handling + budgets + eventual parallelism

Assignment 6 has already produced a working prototype of Milestone 4's central repair-loop concept.

Assignment 7 will contribute a reusable evaluator profile used by artifact GER when style-sensitive content appears.

## Working Rule

Build this in small stages.

Do not try to implement the full autonomous pipeline in one chat/context or one coding session.

Each new window should work on one milestone/subsystem and leave durable repository documentation before ending.

The pipeline should increasingly build No Safe Circle, not become a separate project that indefinitely delays No Safe Circle.


### Reconciliation verification

Reconciliation is semantic enough that deterministic schema validation is necessary but insufficient. Before bootstrap seeding, run an independent multi-model verification crew: two GDD coverage auditors, a dependency/decomposition auditor, and a repository-evidence auditor. Their first-pass findings are independent and unioned rather than voted. Material findings produce a separate refined candidate and a second independent audit pass. The original snapshot remains immutable and `Tasks/*.yaml` remains untouched until human approval.
