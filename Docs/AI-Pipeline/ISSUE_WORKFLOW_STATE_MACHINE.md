# Durable Issue Workflow State Machine

## Purpose

A No Safe Circle task must remain resumable after a browser closes, an agent stops, Vincent gets distracted, or a different model continues the work.

The GitHub Issue is the durable operational controller for that task. It records who acts next, which phase is active, which branch and commit are authoritative for the handoff, and the complete transition history.

The Issue does **not** replace:

- the committed TaskGraph contract as the definition of work;
- Git as the implementation and branch authority;
- Unity/XML/Git validation as test evidence;
- committed TaskGraph evidence as conformance authority.

The Issue answers the operational question:

> What should a human or generic agent do next, and exactly which branch/commit/state should they resume?

## Golden path

```text
generic agent starts
        ↓
list and validate agent-ready Issues
        ↓
resume agent-ready work before selecting a new task
        ↓
acquire an agent lease
        ↓
create/resume the canonical checkout and branch
        ↓
implement, validate, commit, and push
        ↓
publish exact branch/commit and Unity checklist
        ↓
human_action_required
        ↓
Vincent tests the exact recorded commit
        ↓
Vincent posts PASS or FAIL
        ↓
Vincent adds nsc-state:agent-ready
        ↓
GitHub Action validates the result and event chain
        ↓
PASS -> agent_ready / delivery_evidence
FAIL -> agent_ready / repair
        ↓
any later generic agent resumes the same Issue
```

No task-specific resume command is required.

## Managed Issue layers

### Visible dashboard

The top of the Issue contains a managed dashboard:

```text
Current state
Current owner
Current phase
Branch
Commit
Checkout
Next action
```

This is the first thing Vincent or a later agent reads after returning to the task.

### Machine-readable state

A hidden `nsc-workflow-state` JSON block records:

- schema version;
- exact `NSC-###` task ID;
- state and phase;
- current human/agent owner;
- current worker and lease IDs while an agent owns the task;
- branch, commit, and canonical checkout path;
- exact task-contract SHA-256;
- human handoff commit and PASS/FAIL result;
- state version and final event ID;
- update timestamp.

Humans do not manually edit this block.

### Append-only event log

Every transition is a readable Issue comment containing a hidden `nsc-workflow-event` JSON object.

Each event records:

- contiguous sequence number;
- previous event ID;
- event type;
- old and new state;
- old and new phase;
- actor type and actor identity;
- task-contract SHA-256;
- timestamp;
- transition-specific details;
- SHA-256 event ID.

The event IDs form a hash chain. The current state must point to the final event.

The workflow stops when it detects:

- missing or duplicate sequence numbers;
- duplicate event IDs;
- an incorrect `previous_event_id`;
- a state/phase discontinuity;
- a task or contract-hash change;
- an Issue state that does not match the final event;
- more than one workflow state block;
- an incorrect or multiple state label.

### Completed-workflow repository-history maintenance

A closed `complete` Issue remains durable terminal workflow authority. It is not discarded merely because GitHub marks the Issue closed, and a later generic agent must not initialize a replacement Issue for the same completed task.

A deliberate Git history identity rewrite is the one supported case where the live Git commit identity stored by a completed Issue may need to change without reopening gameplay work. The maintenance event is:

```text
complete / merge_closeout
        ↓
repository_history_migrated (human)
        ↓
complete / merge_closeout
```

This event is allowed only when committed repository-history migration authority proves the exact old/new commit translation and preserved Git tree. It records:

- migration ID and committed manifest path;
- rewrite-report SHA-256;
- old and new live workflow commit;
- preserved tree identity;
- old and new human-handoff commit.

The event does **not** change the task-contract hash, human PASS/FAIL result, branch, phase, or completed state. The historical event comments that named the old commits remain unchanged. A migration helper appends exactly one new hashed event and replaces only the live dashboard/state commit identity. It then re-reads the Issue and validates the full event chain again.

A closed incomplete duplicate Issue is not upgraded into migration authority. It remains historical/duplicate and is ignored by the agent-ready queue.

## States

| State | Next owner | Meaning |
| --- | --- | --- |
| `agent_ready` | generic agent | A validated agent may acquire the next lease. |
| `agent_working` | recorded worker | Only the worker recorded in the lease may continue. |
| `human_action_required` | Vincent | The branch is committed/pushed and awaits the recorded human checklist. |
| `blocked` | human or agent | A decision or external prerequisite prevents progress. |
| `complete` | nobody | Delivery/closeout is finished. |

The matching labels are:

```text
nsc-state:agent-ready
nsc-state:agent-working
nsc-state:human-action
nsc-state:blocked
nsc-state:complete
```

Exactly one managed state label must match the hidden state.

## Phases

| Phase | Agent behavior |
| --- | --- |
| `implementation` | Implement the original bounded task. |
| `repair` | Use the human failure report to repair the existing pushed branch. |
| `unity_runtime_validation` | Vincent owns the requested Unity/visual/input/runtime checks. |
| `delivery_evidence` | Human result passed; create authoritative validation and delivery evidence. |
| `merge_closeout` | Finish TaskGraph conformance, merge, and operational closeout. |

State answers **who acts next**. Phase answers **what kind of work happens next**.

## Generic-agent selection priority

Before selecting new TaskGraph work, run:

```powershell
python Pipeline/TaskReviewAgent/issue_queue.py --source .
```

The command returns only Issues whose:

- hidden state parses and validates;
- full event chain validates;
- state is `agent_ready`;
- state label is exactly `nsc-state:agent-ready`.

Generic agents must resume these Issues before selecting a fresh `not_delivered` task.

A generic agent does not infer resume state from prose alone. It uses the validated state, event chain, branch, commit, phase, and human result.

## Agent lease

Before task checkout or implementation work, the agent:

1. validates the task and every declared dependency;
2. checks other managed Issues for overlapping exclusive resources;
3. creates or initializes the task Issue if needed;
4. appends `agent_lease_acquired` with worker, source commit, branch, checkout, approach, and expected validation;
5. changes the Issue to `agent_working`;
6. re-reads and validates the state/event chain.

A task cannot acquire a lease while another managed Issue reserves an overlapping resource in:

```text
agent_working
human_action_required
blocked
```

A race between two agents fails closed. Two competing events based on the same state produce duplicate sequence/previous-event relationships rather than silently authorizing two workers.

## Canonical checkout continuity

The checkout remains:

```text
C:\NSC\NSC\<TASK-ID>
```

For fresh implementation, the checkout starts from current `origin/main` and creates the deterministic task branch.

After a human handoff, the workflow records the exact pushed branch and commit. A later agent may:

- resume the existing clean checkout at that exact branch/commit; or
- recreate the checkout from the exact remote task branch and recorded commit.

The checkout identity is task-owned, not worker-owned. A different agent worker may resume after acquiring the next lease.

The workflow stops on:

- wrong branch;
- wrong commit;
- recorded commit absent from the remote branch;
- wrong remote;
- changed task-contract hash;
- dirty checkout;
- nested/non-standalone repository;
- conflicting external checkout manifest.

It never deletes, resets, overwrites, or silently replaces an existing canonical task checkout.

## Agent-to-human handoff

The human handoff is allowed only after the implementation stage proves:

- the canonical task branch is checked out;
- the working tree is completely clean;
- the recorded commit is checkout `HEAD`;
- the commit descends from the workflow base/handoff commit;
- the exact commit is pushed as the remote task branch;
- the checkout remote matches the controller remote;
- the commit contains the current task-contract identity.

The handoff comment contains:

- branch;
- exact commit to test;
- canonical checkout path;
- concrete implementation summary;
- checks already completed;
- numbered steps for Vincent;
- expected result;
- PASS/FAIL result template.

The Issue transitions to:

```text
human_action_required / unity_runtime_validation
```

## Vincent's human result

Vincent tests the exact recorded commit and posts:

```text
## Human validation result

Result: PASS
Tested commit: `0123456789abcdef0123456789abcdef01234567`

Completed steps:
- ...

Notes:
...
```

For failure:

```text
## Human validation result

Result: FAIL
Tested commit: `0123456789abcdef0123456789abcdef01234567`

Failed step:
...

Reproduction:
1. ...

Expected:
...

Observed:
...
```

Then Vincent applies:

```text
nsc-state:agent-ready
```

The Issue workflow Action validates:

- current managed state is `human_action_required`;
- the event chain is valid;
- a human result exists;
- result is exactly PASS or FAIL;
- tested commit exactly matches the handoff commit.

It then appends the human event and updates the state:

```text
PASS -> agent_ready / delivery_evidence
FAIL -> agent_ready / repair
```

The PASS is also conditional delivery authorization for the exact tested
commit. After authoritative validation and proposal generation, the agent may
advance directly to `merge_closeout` without a second human approval only when
the canonical checkout is clean and its commit identity is unchanged. New or
uncommitted changes invalidate that automatic continuation and require human
reconciliation.

When `origin/main` has advanced, the controller merges it into the task branch
before delivery. Because that operation creates a new commit, the Issue returns
to `human_action_required` and requires PASS or FAIL for the exact integrated
commit regardless of whether the drift is runtime-sensitive or automation-only.
After PASS, that unchanged integrated commit can continue through delivery and
merge closeout without a second approval.

If validation fails, the Action restores `nsc-state:human-action`, comments the reason, and leaves the task human-owned.

## Later generic-agent behavior

### After PASS

The next agent:

1. acquires the Issue lease;
2. resumes the exact pushed branch/commit;
3. performs authoritative validation required by the task;
4. packages delivery evidence;
5. continues to conformance and merge closeout.

### After FAIL

The next agent:

1. acquires the Issue lease;
2. resumes the exact pushed branch/commit;
3. treats the human failure comment as repair input;
4. repairs the implementation on the same branch;
5. commits and pushes a new commit;
6. publishes a new human checklist and handoff commit;
7. returns the Issue to `human_action_required`.

The loop can repeat without losing prior handoffs, results, or repair history.

## Authority boundary

Issue workflow state is operational authority only. It does not prove:

- implementation correctness;
- Unity test success;
- delivery evidence validity;
- TaskGraph conformance;
- merge authorization.

Those facts remain owned by the repository's deterministic tools and human approval boundaries.
