# Context 4 — Agent Crew + GER + Validation / Repair Loop

## Goal

Turn ticket implementation into a reliable bounded execution pipeline.

Prerequisites: supervisor, worktree/branch/PR, and task context.

## Assignment 3 Crew Placement

The crew belongs inside ticket execution:

```text
Persistent Task Graph chooses WHAT
       ↓
Ticket Context
       ↓
Planner
       ↓
Implementer
       ↓
Validator
```

Do not let the crew rebuild the global roadmap.

## Planner

Input: task artifact, acceptance criteria, relevant GDD chunks, relevant project state/files.

Output: small implementation plan, expected files, validation plan.

No scope broadening.

## Implementer

Implement only the selected ticket. If a new substantial prerequisite is discovered, stop and report a blocker instead of silently absorbing another ticket.

## Deterministic Validation First

Run local checks before asking another model:

- `git diff --check`
- prohibited-file/path checks
- scope checks
- static checks
- task graph checks
- unit tests
- Unity compile
- Unity EditMode tests
- Unity PlayMode tests

## Unity Validation

Eventually run Unity command-line/batch validation on the real development machine. Do not treat a Docker environment without Unity as final runtime truth.

Produce machine-readable test results.

## Fresh AI Diff Review

After deterministic validation, give a fresh reviewer only:

- task contract
- acceptance criteria
- relevant GDD evidence
- git diff
- deterministic test results

Ask whether the diff satisfies the ticket without exceeding scope.

## Repair Loop

```text
failure evidence → Implementer repair → deterministic tests → AI diff review
```

Limit retries.

## Assignment 6 — GER

Use GER for generated game content/artifacts:

```text
Generator
 ↓
Evaluator
 ↓ PASS → approved artifact

FAIL
 ↓
Refiner
 ↓
Evaluator
 ↓
(retry limit)
 ↓
Circuit Breaker
 ↓
Needs Human Review
```

RAG feeds the evaluator with exact GDD rules.

Possible generated artifact directories:

```text
Artifacts/
  Encounters/
  ArtSpecs/
  Tutorials/
  Balance/
  Dialogue/
```

A generated artifact can be a dependency of a later code/content task.

Example:

```text
NSC-035 Generate Bone Archive Encounter
        ↓
approved artifact
        ↓
NSC-040 Implement Bone Archive Encounter
```

## Cost / Circuit Breakers

Per ticket define limits such as max agent runs, max repair attempts, runtime, and budget. Escalate on GDD ambiguity, repeated test/GER failure, architecture-changing dependencies, scope expansion, Unity conflicts, or budget exhaustion.

## Completion Definition

```text
implementation → deterministic tests → Unity tests → fresh AI review → PR ready → merge → task complete
```

A worker saying “implemented” is not completion.

## Completion Criteria

A ticket reliably reaches either `Merged / Done` or `Needs Human Review`, with bounded spending and clear evidence.

## Next

Continue with `05_CONTINUOUS_AUTONOMY_CONTEXT.md`.
