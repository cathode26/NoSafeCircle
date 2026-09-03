# TaskReviewAgent — durable Issue workflow to human Unity work

TaskReviewAgent is the goal-oriented OpenAI supervisor around the existing No Safe Circle pipeline.

The workflow is designed so a task can survive interruptions, model changes, browser closure, and human delay without requiring a task-specific resume command.

```text
generic agent starts
        ↓
resume a valid agent-ready Issue before selecting new work
        ↓
acquire the Issue lease
        ↓
create/resume canonical checkout and task branch
        ↓
implement candidate
        ↓
refresh current main and apply the candidate on top of it
        ↓
test, commit, and push the exact integrated candidate
        ↓
write the branch, commit, summary, and Unity checklist into the Issue
        ↓
Issue becomes human_action_required
        ↓
Vincent posts PASS or FAIL and adds nsc-state:agent-ready
        ↓
GitHub Action validates the result and changes the phase
        ↓
any later generic agent resumes the same Issue
```

After Vincent actually completes the Issue checklist and chooses PASS,
`pass_and_resume_task.py` is the standard combined PASS/label/wait/resume entry
point. It binds the PASS to the exact clean handoff commit and waits for the
GitHub workflow state and hashed event count to agree before it launches the
agent. See `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md` for the command.

## Durable Issue controller

The task Issue now carries three operational layers.

### Visible dashboard

The top of the Issue says:

```text
Current state
Current owner
Current phase
Branch
Commit
Checkout
Next action
```

This is the human recovery view when returning after a distraction.

### Managed state block

A hidden `nsc-workflow-state` JSON block records:

- exact task ID and task-contract SHA-256;
- state and phase;
- human or agent ownership;
- worker and lease identities;
- branch, commit, and checkout;
- human handoff commit and PASS/FAIL result;
- state version and final event ID.

Humans do not edit this block.

### Append-only event comments

Every transition appends a readable comment with a hidden `nsc-workflow-event` object. Events carry a sequence, prior event ID, state/phase transition, actor, timestamp, task-contract hash, and SHA-256 event identity.

The next agent validates the entire chain. Missing, edited, duplicated, forked, reordered, or stale events fail closed.

## States and phases

Main states:

| State | Next owner |
| --- | --- |
| `agent_ready` | any generic agent may resume |
| `agent_working` | the recorded worker owns the lease |
| `human_action_required` | Vincent owns the recorded Unity/runtime checklist |
| `blocked` | a human decision or external prerequisite is required |
| `complete` | no further workflow action |

State labels mirror the managed state:

```text
nsc-state:agent-ready
nsc-state:agent-working
nsc-state:human-action
nsc-state:blocked
nsc-state:complete
```

The phase tells the next agent what work to perform:

```text
implementation
repair
unity_runtime_validation
delivery_evidence
merge_closeout
decomposition
decomposition_apply_authorization
decomposition_apply
```

A human PASS moves the Issue to `agent_ready / delivery_evidence`. A human FAIL moves it to `agent_ready / repair`.

An exact-commit human PASS also supplies the delivery authorization for that
unchanged commit. After authoritative Unity tests pass and the hash-bound
delivery proposal is generated, the controller proceeds to `merge_closeout`
without asking Vincent for a second approval. This automatic continuation is
allowed only while the canonical checkout is clean and still points to the
human-tested commit. Any new or uncommitted repository change stops for human
reconciliation instead of reusing the earlier PASS.

If `origin/main` advances after that PASS, the controller merges current main
into the task branch and pushes the resulting merge commit. Every such merge,
including one classified as automation-only, creates a new exact-commit human
handoff. Vincent must test and approve that integrated commit. Once it passes,
the unchanged integrated commit proceeds through delivery and merge closeout
without a second approval.

These are intentionally two independent current-main boundaries. Before the
first human handoff, the candidate is validated against current `origin/main`,
the task branch is advanced to that exact base, and the candidate is committed
and tested there. After the human PASS, downstream delivery fetches
`origin/main` again. A no-op second synchronization preserves the exact tested
commit and continues automatically; a synchronization that creates a new
commit invalidates the older PASS and returns the integrated commit for another
human test. A merge conflict is a repair problem at the task checkout, never
permission to overwrite either side.

## Decomposition handoff and application

The software architect may select one eligible `work_type: decomposition`
candidate from the same mixed portfolio as implementation work. Decomposition
does not wait for the implementation portfolio to become empty. The selected
parent acquires the ordinary durable Issue/task claim, while the Docker
round-robin service receives a physically read-only repository and writes only
to the external no-overwrite output root.

A `review_ready` plan is published as an exact `plan_id` handoff in
`human_action_required / decomposition_apply_authorization`. It is still
review-only. Vincent may approve that exact plan with:

```powershell
python Pipeline\TaskReviewAgent\pass_and_resume_task.py NSC-### --source . --checkout-root C:\NSC\NSC --execution-provider claude --approve-decomposition --apply
```

The helper reads the plan identity from the durable Issue, posts an exact-plan
APPROVE, waits for GitHub to enter `agent_ready / decomposition_apply`, and
starts the distinct host application boundary. Application is serialized by a
global D1C claim, requires the authorized source to remain exact current main,
uses the network-free `apply_graph_delta()` transaction, pushes the exact
resulting commit, and records completion. If main moved while the plan waited,
the plan is not applied; its lease is released to fresh decomposition so child
IDs and graph rewrites are replanned against the new graph.

## Agent lease and resource conflict checks

Before checkout work, the agent:

1. validates current Git and TaskGraph state;
2. checks every declared dependency;
3. inspects managed open Issues;
4. blocks tasks whose exclusive resources overlap another `agent_working`, `human_action_required`, or `blocked` Issue;
5. creates or initializes the task Issue when needed;
6. appends an `agent_lease_acquired` event;
7. changes the Issue to `agent_working`;
8. verifies the resulting Issue state and event chain.

If two agents race from the same state, duplicate sequence/previous-event relationships produce an invalid chain instead of silently granting both agents authority.

## Canonical checkout

After a valid Issue lease, the agent may create or resume only:

```text
C:\NSC\NSC\<TASK-ID>
```

Checkout preparation still enforces:

- clean controller with `HEAD == origin/main`;
- approved GitHub remote;
- standalone clone rather than a Windows worktree;
- deterministic task branch;
- exact source commit/tree and task-contract hash;
- TaskGraph validation in the clone;
- clean checkout;
- external checkout identity manifest.

A wrong or dirty existing checkout becomes a human conflict. It is never reset, deleted, overwritten, or bypassed with a differently named directory.

## Human handoff

The downstream implementation stage will call `publish_human_handoff` only after it has committed and pushed the branch. The Issue comment records:

- branch and exact commit to test;
- canonical checkout path;
- what was implemented;
- checks already completed;
- numbered Unity steps;
- exact expected result;
- a PASS/FAIL comment template.

The Issue then becomes:

```text
human_action_required / unity_runtime_validation
```

On the real production composition, that verified transition also posts one routing comment to the
open authorized `NSC-Vincent` Issue. The notification points back to the source task Issue and exact
commit/checkout; it does not duplicate the Unity checklist or become workflow/evidence authority.
Vincent records PASS/FAIL on the source Issue, then manually deletes the corresponding
`NSC-Vincent` notification comment. An exact handoff retry is notification-idempotent and does not
repeat the source Issue transition.

Vincent posts a result such as:

```text
## Human validation result

Result: FAIL
Tested commit: `0123456789abcdef0123456789abcdef01234567`

Failed step:
...

Reproduction:
...

Expected:
...

Observed:
...
```

Then Vincent adds:

```text
nsc-state:agent-ready
```

`.github/workflows/nsc-issue-workflow.yml` validates that the Issue is actually human-owned, finds the latest result, requires the exact handoff commit, appends the human workflow event, updates the dashboard/state block, and selects `repair` or `delivery_evidence`.

No task-specific PowerShell resume command is required.

## Generic-agent queue

Before selecting fresh TaskGraph work, a generic agent should run:

```powershell
python Pipeline/TaskReviewAgent/issue_queue.py --source .
```

Only Issues whose managed state, state label, and complete event chain all prove `agent_ready` are returned. Generic selection must resume these Issues before choosing a new task.

## Current real command

For an eligible explicit task, the deterministic mode can initialize/acquire the Issue lease and prepare the checkout in one bounded stage:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode checkout-real -WorkerId task-review-agent-vincent
```

The OpenAI-driven equivalent is:

```powershell
python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt
$env:OPENAI_API_KEY = "..."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Pipeline\TaskReviewAgent\Start-TaskReviewAgent.ps1 -TaskId NSC-### -Mode openai-checkout-real -WorkerId task-review-agent-vincent
```

The OpenAI agent receives only:

```text
observe_goal_state
acquire_agent_lease
prepare_task_checkout
```

It cannot yet plan write paths, run ExecutionCrew, edit gameplay/tests, commit, push, publish a human handoff, run Unity, merge, package evidence, or claim conformance.

## Current NSC-050 result

`NSC-050` still stops before Issue/checkout changes because its current declared dependency states are:

```text
NSC-020 = not_delivered
NSC-004 = needs_testing
```

The workflow state and checkout boundaries are tested using deterministic in-memory Issues and temporary synthetic Git repositories instead of creating an inappropriate live NSC-050 task.

## Validation

```powershell
python Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py
python Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py
python Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py
python Pipeline/TaskReviewAgent/run_agent.py --task-id NSC-050 --mode observe-real --source .
python -m compileall -q Pipeline/TaskReviewAgent
```

The Issue workflow tests prove:

- state and event round trips;
- hash-chain verification;
- agent lease creation and later-agent resume;
- committed human handoff state;
- exact-commit PASS/FAIL enforcement;
- FAIL → repair and PASS → delivery-evidence phase selection;
- agent-ready queue discovery;
- exclusive-resource conflict rejection;
- tampered history rejection.

## Next boundary

The next implementation slice connects bounded repository read/search and deterministic implementation/test path planning. After that, real ExecutionCrew can generate the candidate, and the later application stage can commit and push before calling the already-defined human handoff transition.

Patch application and Unity execution remain separate authority boundaries.
