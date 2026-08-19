# START HERE — No Safe Circle AI Pipeline

This is the first file any AI assistant or developer should read before working on the autonomous development pipeline.

## Purpose

The pipeline is being built across multiple work sessions and multiple AI contexts. Do not rely on conversation memory as the source of truth.

The repository is the source of truth.

## Required Reading Order

1. Read `Docs/AI-Pipeline/CURRENT_STATE.md`.
2. Read `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`.
3. Read the milestone file named by `CURRENT_STATE.md`.
4. Read `Docs/AI-Pipeline/DECISIONS.md` if the work touches architecture, Git workflow, task semantics, autonomy, RAG, GER, or validation.
5. Inspect the actual repository state before changing anything.

Do **not** read every milestone file unless you need the broader design. Work primarily from the current milestone.

## Milestone Routing Table

| Current work | Read this file |
|---|---|
| Persistent tasks, task schema, dependency graph, ready queue | `01_MILESTONE_TASK_GRAPH.md` |
| Assignment 4 RAG reuse, GDD canon retrieval, Unity/code scanner, context packs | `02_RAG_SCANNER_CONTEXT.md` |
| Supervisor, task claiming, Git branches, worktrees, GitHub Issues/Projects/PRs | `03_SUPERVISOR_GIT_GITHUB_CONTEXT.md` |
| Assignment 3 crew, Assignment 6 GER, deterministic tests, Unity validation, repair loop | `04_EXECUTION_GER_VALIDATION_CONTEXT.md` |
| Continuous autonomous ticket processing, budgets, blockers, parallel workers, planning refresh | `05_CONTINUOUS_AUTONOMY_CONTEXT.md` |

## End-of-Session Rule

Before ending a meaningful pipeline work session:

1. Update `CURRENT_STATE.md`.
2. Add an entry to `DECISIONS.md` if an architectural decision changed.
3. Ensure commands and newly-created files are documented.
4. Commit the documentation with the implementation it describes.

A new AI window should be able to resume by reading the repository without needing the previous chat transcript.

## Core Principle

**Use deterministic local tools for facts and computation. Use LLMs for judgment and bounded implementation.**

The local supervisor owns the autonomous loop. Claude is a worker operating on one bounded task at a time.
