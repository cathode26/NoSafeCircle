# Game Task Agent — one command to a committed human Unity handoff

## Purpose

The Game Task Agent connects the durable GitHub Issue workflow to the existing real implementation pipeline:

```text
explicit eligible task or validated agent-ready Issue
        ↓
managed Issue lease
        ↓
canonical task checkout and branch
        ↓
bounded repository inspection
        ↓
exact implementation/test scope validation
        ↓
ExecutionCrew
  Contract Locality Auditor
  Implementer
  Test Author
  Validator
  bounded repair
        ↓
verified review-ready candidate.patch
        ↓
independent apply/check in disposable clone
        ↓
apply to canonical task checkout
        ↓
commit and push exact task branch
        ↓
Issue checklist for Vincent
        ↓
human_action_required
```

The agent does not ask Vincent to review a raw patch or finish implementation. It commits and pushes the work before handing over the Issue.

## Prerequisites

From the clean shared controller checkout:

```text
C:\NSC\NSC\NoSafeCircle
```

confirm:

- Git is available;
- GitHub CLI is authenticated with `gh auth login`;
- Docker Desktop and Docker Compose are running;
- Claude or Codex provider authentication used by the repository is available;
- `OPENAI_API_KEY` is set for the OpenAI supervisor;
- the OpenAI Agents SDK dependency is installed.

Install the isolated Python dependency once:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
```

## Start one explicit task

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude
```

The explicit task must pass the real TaskGraph eligibility and dependency checks. The agent does not silently switch to another task when the named task is blocked.

Use Codex for ExecutionCrew instead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider codex
```

The OpenAI supervisor model can be selected independently:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -ExecutionProvider claude -Model gpt-5.6
```

## Resume durable agent-ready work

Run the same launcher without a task ID:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1
```

The launcher first finds fully validated `nsc-state:agent-ready` Issues. It resumes the oldest valid Issue rather than selecting a new task. The Issue state, event chain, phase, branch, commit, human result, and task-contract identity are revalidated before work begins.

When no validated agent-ready Issue exists, generic resume stops and asks for an explicit task ID. It does not guess dependency readiness or autonomously invent fresh work.

## What happens during a fresh implementation run

1. The controller validates the selected task, TaskGraph, dependencies, controller `HEAD`, working-tree cleanliness, and exclusive-resource availability.
2. It creates or initializes the task Issue and records a hashed agent lease.
3. It creates or resumes:

   ```text
   C:\NSC\NSC\<TASK-ID>
   ```

4. The OpenAI supervisor receives bounded repository read, search, and exact file-list tools. It does not receive unrestricted shell or direct game-code write authority.
5. The supervisor proposes the smallest exact implementation and Unity-test file set.
6. Deterministic validation rejects wrong existing/new classifications, missing committed parents, ignored paths, test/implementation overlap, protected repository areas, unrelated resource roots, and unsafe file types.
7. The existing Docker ExecutionCrew performs implementation, test authorship, semantic validation, and its bounded repair cycle.
8. A `review_ready` result is checked against its persisted `crew_result.json`, source commit, task-contract hash, exact requested paths, final changed paths, and candidate SHA-256.
9. The candidate is first applied in a disposable clone. The path set, whitespace, TaskGraph, and task-contract identity are revalidated.
10. The candidate is applied to the canonical task checkout, staged only by its exact verified paths, committed, and pushed without force.
11. The Issue receives the exact branch, commit, concrete implementation summary, checks already completed, numbered Unity steps, expected result, and PASS/FAIL template.
12. The Issue changes to:

    ```text
    human_action_required / unity_runtime_validation
    ```

The agent then stops.

## Vincent's task

The Issue is the durable to-do item. It states:

- the canonical checkout;
- exact branch;
- exact commit to test;
- scene or setup to open;
- numbered Play Mode steps;
- observable PASS criteria;
- what to include in a failure reproduction.

Test only the commit named in the Issue.

Post a result comment:

```text
## Human validation result

Result: PASS
Tested commit: `<exact 40-character SHA>`

Completed steps:
- ...

Notes:
...
```

or:

```text
## Human validation result

Result: FAIL
Tested commit: `<exact 40-character SHA>`

Failed step:
...

Reproduction:
1. ...

Expected:
...

Observed:
...
```

Then apply:

```text
nsc-state:agent-ready
```

The GitHub Action validates the managed state, event chain, exact tested commit, and PASS/FAIL format before changing the phase.

## Resume behavior after human work

The Issue workflow records:

```text
PASS -> agent_ready / delivery_evidence
FAIL -> agent_ready / repair
```

A later generic agent therefore knows which branch and commit to resume and whether it is handling repair or delivery continuation. It never relies on the previous browser conversation.

The connected production controller in this milestone is authoritative through the committed-and-pushed human Unity handoff. The durable Issue state already routes PASS and FAIL. Fully automatic human-feedback repair injection, authoritative clean Unity test execution, TaskDelivery finalization, evidence commits, conformance, and merge closeout remain later pipeline boundaries; they are not falsely claimed by this command.

## Read-only inspection

To inspect what the production controller would do without acquiring a lease or writing an Issue:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1 -TaskId NSC-### -Mode observe
```

## Safety boundaries

The Game Task Agent cannot:

- edit `main`;
- force-push a task branch;
- silently widen the validated file scope;
- edit the selected task contract or GDD as part of implementation;
- treat non-`review_ready` ExecutionCrew output as applyable;
- hand off an uncommitted or unpushed candidate;
- claim that human Unity validation occurred;
- claim TaskGraph delivery or conformance;
- merge the task.

A wrong branch, unexpected remote movement, dirty checkout, changed task contract, candidate hash mismatch, path mismatch, TaskGraph failure, Issue event-chain problem, or resource conflict stops for reconciliation and remains visible in the durable Issue log.
