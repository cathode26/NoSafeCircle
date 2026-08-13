# Assignment 5 — Goal-Oriented Coding Agent Workflow

This document records how the Assignment 5 implementation is being built so the process can be repeated later.

## Assignment Goal

Assignment 5 asks for a goal-oriented coding agent that can:

1. Read the Game Design Document (GDD).
2. Scan the existing codebase.
3. Detect gaps between the GDD and the implementation.
4. Prioritize the missing features.
5. Generate code for at least one missing feature.

The main learning objective is the **reasoning layer**: how the agent decides what should be built next and why.

## Relationship to Earlier Assignments

This repository already contains:

- `AgentCrew/` — Assignment 3.
- `DynamicContentPipeline/` — Assignment 4.

Assignment 5 should not replace or modify either project.

Useful ideas are reused:

- Assignment 3 provides a proven Claude Code / Docker invocation pattern.
- Assignment 4 established the GDD as canonical source material.
- Assignment 5 adds goal selection: compare the desired game against the current implementation, identify gaps, and choose the next goal.

## Branch

Assignment 5 is developed on:

```text
assignment-5-goal-oriented-agent
```

Before making changes, verify:

```powershell
git status
```

Expected result:

```text
On branch assignment-5-goal-oriented-agent
nothing to commit, working tree clean
```

## Assignment 5 Folder

The intended structure is:

```text
GoalOrientedAgent/
├── goal_agent.py
├── prompts/
│   └── analyze.md
├── outputs/
│   └── goal_analysis.json
├── Setup-Assignment5-Analysis.ps1
└── WORKFLOW.md
```

The repository root also contains:

```text
Run-Assignment5-Setup.cmd
```

`Run-Assignment5-Setup.cmd` exists only as a convenient Windows launcher for the PowerShell setup script.

## Phase 1 — Build the Analysis Harness

Run:

```text
Run-Assignment5-Setup.cmd
```

You can double-click the file in Windows Explorer, or run it from the repository root.

The launcher executes:

```text
GoalOrientedAgent\Setup-Assignment5-Analysis.ps1
```

The PowerShell script invokes Claude Code inside the existing Docker environment.

### Important Permission Distinction

There are two separate Claude invocations.

**Setup Claude**

The setup script gives Claude these tools:

```text
Read, Glob, Grep, Write
```

It needs `Write` because its job is to create the Assignment 5 files.

It is not allowed to use `Edit`.

**Goal-Oriented Agent — Analysis Phase**

The agent created by the setup step must use only:

```text
Read, Glob, Grep
```

during analysis.

The analysis agent must not have `Write` or `Edit` permission. It is supposed to inspect the project and choose a goal, not alter gameplay code yet.

## Desired State vs. Current State

The core reasoning model for Assignment 5 is:

```text
Desired State - Current State = Gaps
```

For this project:

```text
GDD requirements
-
existing Unity implementation
=
missing or partial game features
```

The agent then reasons:

```text
Gaps
  ↓
Evaluate
  ↓
Prioritize
  ↓
Choose one goal
  ↓
Act
```

In Phase 1, the process intentionally stops after **Choose one goal**.

Code generation is added only after the goal-selection behavior has been reviewed.

## What the Analysis Agent Must Inspect

### Desired State

The agent reads:

```text
Docs/GDD/No_Safe_Circle_GDD.md
```

The GDD is treated as the desired state.

### Current State

The agent scans:

```text
Assets/
```

This is the actual Unity implementation.

The agent should use repository evidence instead of assuming that a feature exists merely because a similarly named file exists.

## Gap Classification

Required GDD features should be classified as:

```text
implemented
partial
missing
```

The agent should distinguish required scope from stretch goals.

## Goal Evaluation

Missing features should be evaluated using factors such as:

- Dependencies.
- Whether prerequisites already exist.
- How many required systems the feature unlocks.
- Implementation size and risk.
- Whether the feature is required or merely a stretch goal.
- Whether it can be implemented and tested as a bounded next step.

The selected feature must not be hard-coded.

For example, a human may predict that the mana system is a strong candidate, but the agent must independently choose its goal from GDD and codebase evidence.

## Required Analysis Output

Phase 1 should create:

```text
GoalOrientedAgent/outputs/goal_analysis.json
```

The JSON should include:

```text
desired_state
current_state
gaps
candidate_goals
selected_goal
selection_reason
dependencies
evidence
rejected_high_priority_alternatives
```

The terminal output should also provide a readable explanation of the selected goal.

## Review Gate

After the setup script finishes, do **not** immediately run the generated agent.

First run:

```powershell
git status
```

Then inspect:

```text
GoalOrientedAgent/goal_agent.py
GoalOrientedAgent/prompts/analyze.md
```

The important checks are:

1. Analysis uses only read-only tools.
2. The selected feature is not hard-coded.
3. The GDD is treated as the desired state.
4. `Assets/` is scanned as the current implementation.
5. The agent records evidence for its conclusions.
6. It chooses exactly one goal.
7. Analysis does not modify Unity files.

After that review, the analysis agent can be run.

## Later Phase — Code Generation

Assignment 5 ultimately requires generating code for at least one missing feature.

That will be a separate action phase.

The intended progression is:

```text
Phase 1
Analyze → Detect gaps → Prioritize → Select goal

Phase 2
Selected goal → Plan implementation → Generate code

Phase 3
Review → Run in Unity → Document result
```

Separating analysis from implementation makes the agent's decision process visible and prevents it from changing the Unity project before its reasoning has been inspected.

## Deliverables to Finish

Before submission, Assignment 5 needs:

- A complete runnable goal-oriented agent.
- Any configuration required to run it.
- Code generated for at least one missing feature.
- A README explaining:
  - What feature the agent built.
  - Why the agent selected that feature.
  - Whether the generated feature was successfully run in the game.

## Git Workflow

After a meaningful working checkpoint:

```powershell
git status
```

Review the changes, then:

```powershell
git add GoalOrientedAgent Run-Assignment5-Setup.cmd
```

Commit with a descriptive message, for example:

```powershell
git commit -m "Add Assignment 5 goal agent analysis harness"
```

Then push:

```powershell
git push
```

Do not merge to `main` until Assignment 5 is working and ready for submission.
