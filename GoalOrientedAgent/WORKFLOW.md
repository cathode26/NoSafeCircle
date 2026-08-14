# Assignment 5 — Goal-Oriented Coding Agent Workflow

This document records the repeatable process used to build Assignment 5.

## Assignment Goal

The Assignment 5 agent must:

1. Read the GDD.
2. Scan the existing codebase.
3. Detect gaps.
4. Prioritize the gaps.
5. Select what to build next.
6. Generate code for at least one missing feature.

The important new concept is the reasoning layer:

```text
Desired State - Current State = Gaps
```

Then:

```text
Gaps
→ Evaluate
→ Prioritize
→ Choose one goal
→ Act
```

## Existing Repository Work

Prior assignments remain separate:

```text
AgentCrew/                Assignment 3
DynamicContentPipeline/  Assignment 4
GoalOrientedAgent/       Assignment 5
```

Assignment 5 may learn from the infrastructure used in Assignment 3 during bootstrap generation, but the actual Assignment 5 analysis is intentionally restricted to:

```text
Docs/GDD/No_Safe_Circle_GDD.md
Assets/
```

## Branch

Work is performed on:

```text
assignment-5-goal-oriented-agent
```

Verify before making changes:

```powershell
git status
```

## Files Used to Bootstrap Assignment 5

Repository root:

```text
Run-Assignment5-Setup.cmd
```

Assignment 5 folder:

```text
GoalOrientedAgent/
├── Setup-Assignment5-Analysis.ps1
├── WORKFLOW.md
├── goal_agent.py                 generated
├── prompts/
│   └── analyze.md                generated
└── outputs/
    └── goal_analysis.json        produced later
```

## Regenerating the Analysis Harness

Run:

```text
Run-Assignment5-Setup.cmd
```

The launcher executes:

```text
GoalOrientedAgent\Setup-Assignment5-Analysis.ps1
```

The setup script intentionally deletes these two generated files first:

```text
GoalOrientedAgent/goal_agent.py
GoalOrientedAgent/prompts/analyze.md
```

This forces Claude to regenerate them from the improved instructions rather than patching an earlier attempt.

## Two Different Claude Roles

There are two Claude executions with different permissions and different repository boundaries.

### 1. Bootstrap Claude

The setup script launches Claude with:

```text
Read
Glob
Grep
Write
```

This Claude needs `Write` because its job is to create the Assignment 5 harness.

It may read:

```text
AgentCrew/orchestrator.py
```

only to learn the existing repository's subprocess/Claude invocation pattern.

### 2. Goal-Oriented Analysis Claude

The generated `goal_agent.py` must launch the actual analysis agent with:

```text
--permission-mode dontAsk
--tools Read,Glob,Grep
--allowedTools Read,Glob,Grep
--disallowedTools Edit,Write,mcp__*
```

The analysis agent must not receive:

```text
Bash
Write
Edit
```

It must not modify files.

Its repository-analysis boundary is:

```text
Docs/GDD/No_Safe_Circle_GDD.md
Assets/
```

It must not inspect:

```text
AgentCrew/
DynamicContentPipeline/
```

## Desired State

The desired state comes from:

```text
Docs/GDD/No_Safe_Circle_GDD.md
```

The GDD defines what the game is supposed to contain.

## Current State

The actual gameplay implementation is determined by scanning:

```text
Assets/
```

Only real gameplay evidence under `Assets/` counts as implementation evidence.

## Gap Detection

Each required gameplay/code feature should be classified as:

```text
implemented
partial
missing
```

The agent must cite actual code evidence.

A promising filename is not enough; relevant files should be read.

## Non-Code Requirements

Some GDD requirements may not be assessable from gameplay code under `Assets/`.

For example:

```text
Windows build
packaging/build-target requirements
```

These are reported separately in:

```text
non_code_requirements
```

Allowed statuses are:

```text
confirmed
not_assessable_from_assets
```

A requirement is not automatically `missing` just because Assets/ cannot prove its status.

Unassessable non-code requirements are not coding-goal candidates.

## Candidate Goal Selection

The agent should build at least three strong candidate goals TOTAL from missing or meaningfully partial required gameplay features.

It should not create three candidate goals for every missing feature.

Each candidate is evaluated using:

- dependencies
- prerequisite readiness
- unlock value
- implementation risk and size
- required-vs-stretch scope

The schema keeps two concepts separate:

```text
scope
```

means only:

```text
required
stretch
```

while:

```text
implementation_scope
```

describes likely files/components/systems involved.

Then the agent selects exactly one next goal.

No feature is hard-coded as the winner.

## Phase 1 Output Responsibility

The read-only Claude analysis agent does not write files.

It returns structured JSON.

The Python orchestrator receives `structured_output` and writes:

```text
GoalOrientedAgent/outputs/goal_analysis.json
```

This separation keeps the reasoning phase read-only while still preserving its result.

## Bootstrap Self-Validation

The setup prompt requires Claude to reread both generated files before finishing and verify:

- read-only analysis permissions are correct
- `--allowedTools` is present
- Bash/Write/Edit are unavailable to the analysis agent
- the GDD is desired state
- Assets/ is current state
- AgentCrew/ and DynamicContentPipeline/ are completely excluded from the analysis pass
- required/stretch/excluded scope is distinguished
- at least three candidate goals TOTAL are compared
- exactly one goal is selected
- no winner is hard-coded
- candidate `scope` is strictly `required` or `stretch`
- `implementation_scope` is separate
- non-code requirements are reported separately
- unassessable non-code requirements are not mislabeled as missing
- the Python orchestrator, not Claude, saves the JSON
- no Unity, GDD, Assignment 3, or Assignment 4 files were modified

If validation fails, Claude is instructed to correct the generated files and validate again before stopping.

## Review Gate

After regeneration:

```powershell
git status
```

Then review:

```text
GoalOrientedAgent/goal_agent.py
GoalOrientedAgent/prompts/analyze.md
```

Do not run the goal agent until those files have been reviewed.

## Running the Analysis Agent

After the generated files have been reviewed, run from the repository root:

```powershell
docker compose run --rm claude python3 GoalOrientedAgent/goal_agent.py
```

The expected output file is:

```text
GoalOrientedAgent/outputs/goal_analysis.json
```

## Phase 2 — Implementation

Once the selected goal is trustworthy, Assignment 5 continues with an action phase:

```text
Selected goal
→ Plan implementation
→ Generate Unity code
→ Test in Unity
```

The implementation phase will have different permissions from the analysis phase and should be added deliberately rather than silently giving the analysis agent write access.

## Final Assignment 5 Deliverables

The finished submission needs:

- the runnable goal-oriented agent
- required configuration
- generated code for at least one missing feature
- README explaining:
  - what feature the agent built
  - why it selected that feature
  - whether the feature was successfully run in the game

## Git Checkpoint

After the analysis harness is working:

```powershell
git status
```

Then:

```powershell
git add GoalOrientedAgent Run-Assignment5-Setup.cmd
```

Commit:

```powershell
git commit -m "Add Assignment 5 goal analysis harness"
```

Push:

```powershell
git push
```

Do not merge into `main` until the assignment is working and ready to submit.
