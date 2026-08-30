# No Safe Circle — Claude Project Instructions

This repository is the Unity capstone game **No Safe Circle** and its AI-assisted development pipeline.

## Source-of-truth boundary

This file is **operating guidance only**. It is not game-design canon and it is not admissible GDD/repository evidence for reconciliation, verification, dependency, ownership, exclusive-resource, or completion claims. Agents must never cite `CLAUDE.md` as the authority for a game requirement or graph decision.

Use these sources instead:

- Root game-design canon: `Docs/GDD/No_Safe_Circle_GDD.md`
- Integrated project truth: the current checkout, especially `Assets/`, relevant `ProjectSettings/`, and approved package manifests/locks when applicable
- AI pipeline routing/context: `AI_PIPELINE.md` and `Docs/AI-Pipeline/START_HERE.md`

If this operating guidance and current project canon/state appear inconsistent, do not manufacture a reconciliation fact from this file. Follow the active task's explicit source boundaries and surface the discrepancy for review when necessary.

## Required engineering standards

@Docs/Engineering/ENGINEERING_STANDARDS.md

## Required Unity testing policy

@Docs/Engineering/UNITY_TESTING_POLICY.md

## Required external reference-project policy

@Docs/Engineering/REFERENCE_PROJECTS.md

@Pipeline/ReferenceSources/README.md

The imported documents are engineering operating guidance, not game-design canon. They do not weaken or replace the source-of-truth boundary above. External reference projects remain optional, read-only, and non-authoritative.

## Required human-facing Unity language

@Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md

The primary human reader is a Unity game programmer. Write task titles, task requirements, review findings, implementation summaries, test summaries, validation summaries, issue comments, closeouts, handoffs, and documentation in concrete Unity terms. Keep abstract taxonomy in machine-facing schema fields, and do not invent implementation details merely to make wording more concrete.

## Required task checkout path policy

@Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md

The shared operator checkout is `C:\NSC\NSC\NoSafeCircle`. A claimed NSC task uses `C:\NSC\NSC\<TASK-ID>`, preserving the hyphenated ID, for example `C:\NSC\NSC\NSC-021`. Do not invent `NoSafeCircle-NSC...` directory variants.

## Required decomposition checkout policy

@Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md

When acting as a task orchestrator, decomposition work must leave the shared checkout after claim and before D1B.1 execution. Decomposition uses the same canonical task directory, e.g. `C:\NSC\NSC\NSC-021`, with authoritative outputs in a filesystem-disjoint sibling such as `C:\NSC\NSC\NSC-021-Outputs`. This is operator coordination guidance and does not grant the decomposition agent additional repository-write authority.

## Global operating rules

- Do not expand approved feature/task scope without authorization.
- Do not silently invent missing game design.
- Generated gameplay code must be testable and understandable by a human Unity developer.
- Human-facing output must name the concrete Unity asset, component, behavior, method, or test whenever that information is established.
- Treat Unity scenes, prefabs, shared builder scripts, and ProjectSettings conservatively because they are non-merge-safe integration surfaces.
- Do not directly edit Unity scene YAML unless an explicitly approved task requires that mechanism; prefer the project's established authoring path.
- Do not commit, push, reset, rebase, or modify Git history unless the active task explicitly authorizes Git operations.
- Human inspection, merge/approval, and final Unity/runtime validation remain required where the pipeline specifies them.
