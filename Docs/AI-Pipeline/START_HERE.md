# START HERE — No Safe Circle AI Pipeline

This is the first file any AI assistant or developer should read before working on the autonomous development pipeline.

## Purpose

The pipeline is being built across multiple work sessions and multiple AI contexts. Do not rely on conversation memory as the source of truth.

The repository is the source of truth.

## Required Reading Order

1. Read `Docs/AI-Pipeline/CURRENT_STATE.md`.
2. Read `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`.
3. Read the milestone file named by `CURRENT_STATE.md`.
4. Read `Docs/AI-Pipeline/DECISIONS.md` if the work touches architecture, Git workflow, task semantics, autonomy, RAG, GER, evaluation, refinement, validation, progressive decomposition, or artifact authority.
5. Inspect the actual repository state before changing anything.

Do not read every milestone file unless you need the broader design. Work primarily from the current milestone.

## Milestone Routing Table

Current work | Read this file
--- | ---
Persistent tasks, work schema, dependency graph, ready queue | `01_MILESTONE_TASK_GRAPH.md`
RAG canon retrieval, Unity/code scanner, context packs, progressive decomposition, artifact authority | `02_RAG_SCANNER_CONTEXT.md`
Supervisor, task claiming, Git branches, worktrees, GitHub Issues/Projects/PRs | `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md`
Assignment 3 crew, Assignment 6 GER, bounded repair loops, deterministic tests, Unity/runtime validation, evaluator specializations | `04_EXECUTION_GER_VALIDATION_CONTEXT.md`
Continuous autonomous ticket processing, budgets, blockers, parallel workers, planning refresh | `05_CONTINUOUS_AUTONOMY_CONTEXT.md`

## Important Post-Assignment-6 Lesson

Assignment 6 demonstrated that GER is not only a gate for generated content.

For No Safe Circle, the successful loop was:

`bounded task → implement → evaluate → collect validation/runtime feedback → refine → re-evaluate → approve or circuit-break`

The camera implementation passed static evaluation before it was actually usable in Unity. Runtime failures were converted into structured feedback and sent back through the Refiner. Future execution work must therefore treat runtime evidence as first-class validation input rather than assuming source-level success means the feature works.

See:

- `Assignment6GER/README_Assignment6.md`
- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`

## Important Progressive-Decomposition Lesson

The task graph does not need the entire game decomposed into low-level implementation tickets in advance.

When high-level work approaches the actionable frontier, the Progressive Decomposer determines whether enough approved design information exists to produce concrete child work.

If required design/content is missing, the Decomposer must propose a new artifact dependency rather than silently inventing the missing design.

Artifact creation must be authorized before generation.

See:

- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`

## End-of-Session Rule

Before ending a meaningful pipeline work session:

1. Update `CURRENT_STATE.md`.
2. Add an entry to `DECISIONS.md` if an architectural decision changed.
3. Ensure commands and newly-created files are documented.
4. Commit the documentation with the implementation it describes.

A new AI window should be able to resume by reading the repository without needing the previous chat transcript.

## Core Principle

Use deterministic local tools for facts and computation. Use LLMs for judgment and bounded implementation.

The local supervisor owns the autonomous loop. Claude is a bounded worker operating on one selected piece of work at a time.

A worker does not declare itself successful. Project evidence does.

An implementation worker also does not silently create new game design. Missing design becomes an explicit artifact proposal.
