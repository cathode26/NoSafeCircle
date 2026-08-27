# TaskReviewAgent — explicit task to human candidate review

This module is the production-oriented goal-agent layer around the existing No Safe Circle pipeline.

Its eventual goal is:

```text
explicit NSC implementation task
        ↓
inspect current pipeline state
        ↓
choose the next bounded approved action
        ↓
prepare checkout + validate exact role paths + run ExecutionCrew
        ↓
deterministically prove review_ready candidate.patch
        ↓
HUMAN_REVIEW_READY
```

The goal stops at **candidate review**. It does not apply the patch, open Unity, run Unity tests, commit implementation, push, merge, package delivery evidence, or claim TaskGraph conformance.

## Current milestone

The first fake end-to-end slice remains available, but the first production boundary is now real:

```text
current Git checkout
        ↓
real HEAD/tree/branch/cleanliness observation
        ↓
real taskcontrol validate
        ↓
exact committed Tasks/<TASK-ID>.yaml bytes + SHA-256
        ↓
real taskcontrol state for the selected task
        ↓
real taskcontrol state for every declared dependency
        ↓
deterministic next-action assessment
```

This observation layer is read-only. It does not fetch, claim an Issue, create a task checkout, inspect provider authentication, plan write paths, invoke ExecutionCrew, or create a candidate.

### Facts returned by real observation

- repository root, branch, HEAD, tree, `origin/main` identity when available, and porcelain status;
- complete `taskcontrol validate` result;
- exact committed task-contract SHA-256;
- task disposition, kind, execution scope, decomposition state, and current evidence-derived state;
- every declared dependency's evidence-derived state;
- exact acceptance criteria, completion gates, downstream obligations, and exclusive resources;
- a semantic hash binding the complete observation.

The observer reads task bytes with:

```text
git show HEAD:Tasks/<TASK-ID>.yaml
```

It therefore reports committed task authority rather than trusting an uncommitted working-tree file.

## Real read-only observation

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode observe-real
```

Or directly:

```powershell
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode observe-real --source .
```

The output includes:

```text
observation_authority = real_read_only
downstream_authority = not_exposed
authority = observation_only
```

`deterministic_assessment.next_action` is currently one of:

```text
prepare_checkout
needs_human
blocked
```

The observer reports `prepare_checkout` only when the exact committed task is active, `implementation`, `single_agent`, `concrete`, `not_delivered`, every declared dependency is `conformant`, TaskGraph validates, and the controller checkout is clean.

## Optional OpenAI interpretation of real facts

The module is tested against OpenAI Agents SDK `0.22.0`.

Install its isolated dependency:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
```

Set `OPENAI_API_KEY`, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode openai-observe-real
```

The OpenAI agent receives exactly one tool: `observe_goal_state`. It has no action tool. Its task ID, observation hash, next action, and authority are checked against the deterministic assessment before output is accepted. Model-written explanatory reasons are retained separately from the deterministic reasons.

The model defaults to `gpt-5.6` and can be overridden with `-Model` or `TASK_REVIEW_AGENT_MODEL`.

## Retained fake end-to-end slice

The deterministic fake workflow is still useful for regression testing the later stages:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode scripted
```

It demonstrates:

1. a missing fake checkout;
2. fake checkout preparation;
3. deterministic rejection of an incorrect existing/new test-path classification;
4. corrected scope validation;
5. fake ExecutionCrew `review_ready`;
6. hash-bound fake proof;
7. rejection of forged or tampered proof.

A real OpenAI agent can navigate the same fake downstream tools with `-Mode openai-fake`.

Fake-mode output is explicitly labeled:

```text
observation_authority = simulated
downstream_authority = simulated
```

## Authority boundary

No current mode can:

- create or modify the canonical task checkout;
- edit gameplay or test files;
- apply `candidate.patch`;
- run Unity;
- commit implementation;
- push or merge;
- edit task contracts or the GDD;
- package delivery evidence;
- claim delivery or TaskGraph conformance.

The OpenAI model never establishes repository facts. Real facts come from Git and TaskGraph commands, and fake success proof remains confined to the explicitly simulated regression mode.

## Validation

```powershell
python Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode observe-real --source .
python -m compileall -q Pipeline/TaskReviewAgent
```

The real-observation regression verifies that observation:

- matches exact committed task bytes and `taskcontrol state`;
- derives dependency conformance from each dependency's real state;
- does not fabricate checkout or write-scope facts;
- preserves HEAD, tree, and clean working-tree state;
- rejects a missing committed task contract.

## Next implementation slice

Replace the next fake boundary while preserving this real observation contract:

1. real canonical checkout inspection;
2. safe create-or-resume preparation for `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>`;
3. re-observe the prepared checkout and bind it to the original source/task identities;
4. keep path planning, ExecutionCrew, and candidate verification fake until checkout behavior is proven.

Do not grant patch application or Unity execution authority in this goal. Those belong to the later `READY_FOR_HUMAN_UNITY_VALIDATION` goal.
