# No Safe Circle — Claude Project Instructions

This repository is the Unity capstone game **No Safe Circle** and its AI-assisted development pipeline.

## Source-of-truth boundary

This file is **operating guidance only**. It is not game-design canon and it is not admissible GDD/repository evidence for reconciliation, verification, dependency, ownership, exclusive-resource, or completion claims. Agents must never cite `CLAUDE.md` as the authority for a game requirement or graph decision.

Use these sources instead:

- Root game-design canon: `Docs/GDD/No_Safe_Circle_GDD.md`
- Integrated project truth: the current checkout, especially `Assets/`, relevant `ProjectSettings/`, and approved package manifests/locks when applicable
- AI pipeline routing/context: `AI_PIPELINE.md` and `Docs/AI-Pipeline/START_HERE.md`

If this operating guidance and current project canon/state appear inconsistent, do not manufacture a reconciliation fact from this file. Follow the active task's explicit source boundaries and surface the discrepancy for review when necessary.

## Required engineering policy

@Docs/Engineering/UNITY_TESTING_POLICY.md

The imported document is engineering operating guidance, not game-design canon. It does not weaken or replace the source-of-truth boundary above.

## Required dependency-state policy

@Docs/AI-Pipeline/ADR-045_NEEDS_TESTING_NON_BLOCKING_DEPENDENCY.md

When selecting, checking, or executing downstream task work, never treat a dependency's `needs_testing` state as a blocker by itself and never require every dependency to report exactly `conformant`. `needs_testing` is revalidation debt on previously delivered/evidenced work, not revocation of the integrated dependency. Separate concrete dependency problems still require normal review.

## Required decomposition checkout policy

@Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md

When acting as a task orchestrator, decomposition work must leave the shared `C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle` checkout after claim and before D1B.1 execution. Create and enter the task-identifying standalone decomposition clone required by the imported policy. This is operator coordination guidance and does not grant the decomposition agent additional repository-write authority.

## Global operating rules

- Do not expand approved feature/task scope without authorization.
- Do not silently invent missing game design.
- Generated gameplay code must be testable and understandable by a human Unity developer.
- Treat Unity scenes, prefabs, shared builder scripts, and ProjectSettings conservatively because they are non-merge-safe integration surfaces.
- Do not directly edit Unity scene YAML unless an explicitly approved task requires that mechanism; prefer the project's established authoring path.
- Do not commit, push, reset, rebase, or modify Git history unless the active task explicitly authorizes Git operations.
- Human inspection, merge/approval, and final Unity/runtime validation remain required where the pipeline specifies them.
