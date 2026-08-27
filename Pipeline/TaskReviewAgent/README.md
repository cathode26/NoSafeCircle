# TaskReviewAgent — explicit task to human candidate review

This module is the first production-oriented goal-agent slice built around the existing No Safe Circle pipeline.

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

The current slice uses deterministic fake pipeline tools. It proves the orchestration contract before real Git, GitHub, checkout, and ExecutionCrew side effects are exposed.

The scripted smoke path demonstrates:

1. the task starts without a checkout;
2. the controller prepares the canonical task checkout;
3. the first implementation/test path plan is rejected because an absent test file was incorrectly classified as existing;
4. the controller submits the corrected exact-new test path;
5. fake ExecutionCrew returns `review_ready`;
6. a deterministic proof is minted;
7. success is rejected unless the final output carries that exact known proof.

The optional `openai-fake` mode lets a real OpenAI Agents SDK agent navigate the same fake tools. It still cannot touch the repository or run ExecutionCrew.

## Deterministic smoke run

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050
```

Or directly:

```powershell
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode scripted
```

Expected outcome:

```text
outcome.status = human_review_ready
authority = review_only_not_applied
```

## Optional live OpenAI run against fake tools

The module is tested against OpenAI Agents SDK `0.22.0`.

Install its isolated dependency:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
```

Set `OPENAI_API_KEY`, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode openai-fake
```

The model defaults to `gpt-5.6` and can be overridden with `-Model` or `TASK_REVIEW_AGENT_MODEL`.

## Authority boundary

The OpenAI model never mints success authority. `verify_human_review_ready` creates a hash-bound proof only after deterministic checks. The final outcome is validated again against the proof retained by the tool implementation.

The agent has no arbitrary shell, file-write, patch-application, commit, push, merge, Unity, task-contract, GDD, evidence, or conformance tool.

## Next implementation slice

Replace fake tools one at a time while preserving the same contracts:

1. real TaskGraph/environment observation;
2. real canonical checkout preparation/resume;
3. bounded repository read/search for path planning;
4. real deterministic execution-scope validation;
5. real ExecutionCrew invocation;
6. real candidate artifact and `git apply --check` verification.

Do not grant patch application or Unity execution authority in this goal. Those belong to the later `READY_FOR_HUMAN_UNITY_VALIDATION` goal.
