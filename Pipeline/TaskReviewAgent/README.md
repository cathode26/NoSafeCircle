# TaskReviewAgent — explicit task to human candidate review

This module is the production-oriented goal-agent layer around the existing No Safe Circle pipeline.

Its eventual goal is:

```text
explicit NSC implementation task
        ↓
inspect current pipeline state
        ↓
claim GitHub Issue + prepare canonical checkout
        ↓
validate exact role paths + run ExecutionCrew
        ↓
deterministically prove review_ready candidate.patch
        ↓
HUMAN_REVIEW_READY
```

The goal stops at **candidate review**. It does not apply the patch, open Unity, run Unity tests, commit implementation, push, merge, package delivery evidence, or claim TaskGraph conformance.

## Current real boundary

Two production boundaries are now real.

### 1. Real repository and TaskGraph observation

For the explicit task, the observer reads:

- Git repository root, branch, `HEAD`, tree, `origin/main`, and clean/dirty state;
- real `python Pipeline/TaskGraph/taskcontrol.py validate`;
- exact committed `Tasks/<TASK-ID>.yaml` bytes using `git show HEAD:<path>`;
- SHA-256 of those exact task-contract bytes;
- real `taskcontrol state <TASK-ID> --json`;
- real state for every declared dependency;
- exact AC/VAL/INT entries and exclusive resources.

The task and every dependency state must refer to the same `HEAD`.

### 2. Real GitHub-claim inspection and checkout preparation

The checkout stage adds:

- read-only `gh` inspection of the exact task Issue;
- verification that the Issue is open, assigned to `cathode26`, and the latest TaskReviewAgent claim marker names the same worker ID;
- exact canonical checkout path:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

- deterministic branch name derived from the task ID and committed task title;
- source `HEAD == origin/main` enforcement;
- canonical GitHub remote enforcement;
- standalone remote clone, never a worktree or local-source clone;
- TaskGraph validation inside the new checkout;
- exact source commit/tree and task-contract hash verification;
- clean-checkout verification;
- an external identity manifest under:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\.task-review-agent\<TASK-ID>.json
```

The checkout is cloned into a temporary sibling directory first. The canonical `<TASK-ID>` path appears only after every validation passes. A failed clone or validation cannot leave a partial canonical checkout.

An existing canonical directory is never reset, deleted, overwritten, or bypassed with a differently named duplicate:

- exact clean matching checkout + matching manifest → `ready`;
- exact clean matching checkout without a manifest → safely adoptable;
- wrong branch, commit, tree, remote, task hash, worker manifest, or any dirty state → `conflict` and human reconciliation.

## GitHub claim boundary

This slice **inspects** GitHub coordination but does not yet create, assign, comment on, or release an Issue.

For an otherwise eligible task:

```text
no Issue / open unassigned → claim_task
claimed by this exact worker → prepare_checkout
assigned to another worker / closed / duplicate match → needs_human
gh unavailable or unauthenticated → blocked
```

Checkout creation is impossible unless the observation already says `claimed_by_worker`.

The next slice will implement the controlled claim action before checkout.

## Commands

### Real read-only task observation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode observe-real
```

### Real claim inspection and checkout preparation

This command may create or resume the canonical checkout only if the task is eligible and already claimed by the same worker:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode checkout-real -WorkerId task-review-agent-vincent
```

The controller checkout must be clean and exactly synchronized with `origin/main`.

### OpenAI-controlled checkout stage

Install the isolated dependency:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
```

Set `OPENAI_API_KEY`, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode openai-checkout-real -WorkerId task-review-agent-vincent
```

The OpenAI agent receives only:

```text
observe_goal_state
prepare_task_checkout
```

It cannot claim the Issue. It must stop on `claim_task`, and it can call `prepare_task_checkout` only after deterministic observation reports `prepare_checkout`. After preparation it must re-observe; deterministic code rejects a final `validate_scope` claim unless the checkout is actually `ready`.

The model defaults to `gpt-5.6` and can be overridden with `-Model` or `TASK_REVIEW_AGENT_MODEL`.

## Current NSC-050 proving result

Real observation of `NSC-050` correctly stops before GitHub or checkout work because its declared dependencies are not both conformant:

```text
NSC-020 = not_delivered
NSC-004 = needs_testing
```

The checkout boundary was therefore proven with temporary synthetic Git repositories in Windows CI, not by creating a real `NSC-050` checkout.

## Retained fake end-to-end regression

The fake workflow remains useful for safely testing the future downstream loop:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-050 -Mode scripted
```

It demonstrates:

1. fake checkout preparation;
2. deterministic rejection of an incorrect existing/new test-path classification;
3. corrected scope validation;
4. fake ExecutionCrew `review_ready`;
5. hash-bound fake proof;
6. rejection of forged or tampered proof.

A real OpenAI agent can navigate those same fake downstream tools with `-Mode openai-fake`.

Fake output is explicitly labeled `simulated`.

## Authority boundary

No current real mode can:

- create, assign, comment on, close, or release a GitHub Issue;
- plan implementation/test write paths;
- invoke ExecutionCrew;
- edit gameplay or test files;
- apply `candidate.patch`;
- run Unity;
- commit implementation;
- push or merge;
- edit task contracts or the GDD;
- package delivery evidence;
- claim delivery or TaskGraph conformance.

The only real write authority is creation or adoption of one exact canonical task checkout after all eligibility and pre-existing claim checks pass.

## Validation

```powershell
python Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py
python Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode observe-real --source .
python -m compileall -q Pipeline/TaskReviewAgent
```

The Windows checkout suite creates a temporary bare remote and proves:

- an eligible claimed task advances to `prepare_checkout`;
- a standalone checkout is created at the exact canonical child path;
- source commit/tree, task-contract hash, branch, remote, TaskGraph, and cleanliness are verified;
- the external manifest does not dirty the checkout;
- an exact managed checkout resumes without recloning;
- an unclaimed task cannot create a checkout;
- a dirty existing checkout becomes `conflict` and stops at human reconciliation;
- the controller repository remains unchanged.

## Next implementation slice

Add the controlled GitHub claim action:

```text
real task/dependency observation
        ↓
resource-conflict check
        ↓
create Issue when absent or assign when available
        ↓
post Claim / Planned Approach with worker/base/branch/checkout
        ↓
re-observe claimed_by_worker
        ↓
prepare canonical checkout
```

After claim + checkout works in one command, replace the next fake boundary with bounded repository read/search and deterministic implementation/test path planning.

Do not grant patch application or Unity execution authority in this goal. Those belong to the later `READY_FOR_HUMAN_UNITY_VALIDATION` goal.
