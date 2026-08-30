# GitHub Issue Orchestration

## Purpose

GitHub Issues are the durable operational controller for No Safe Circle task orchestration.

TaskGraph remains the authority for task meaning, dependencies, acceptance criteria, completion gates, exclusive resources, and committed conformance. Git and validation artifacts remain the authority for implementation and test facts.

The Issue records:

- who acts next;
- which workflow phase is active;
- which agent owns the current lease;
- which task branch and commit must be resumed or tested;
- what Vincent must do in Unity;
- the complete append-only transition history.

Read the complete state/event contract:

```text
Docs/AI-Pipeline/ISSUE_WORKFLOW_STATE_MACHINE.md
Pipeline/TaskReviewAgent/README.md
```

## Resume before selecting new work

A generic agent must first run:

```powershell
python Pipeline/TaskReviewAgent/issue_queue.py --source .
```

Validated `agent_ready` Issues must be resumed before the agent selects a new TaskGraph task.

Only when the queue is empty may the agent continue to fresh candidate discovery:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

`not_delivered` remains a discovery signal, not dependency readiness or autonomous dispatch authority.

## Source-of-truth split

### TaskGraph

TaskGraph owns durable work truth:

- task identity and contract revision;
- required Unity behavior;
- dependencies;
- acceptance criteria and completion gates;
- downstream obligations;
- exclusive resources;
- evidence-derived current conformance.

### Git and validation artifacts

Git and deterministic runners own:

- task branch and commit identity;
- actual changed files;
- clean/dirty state;
- Unity test execution results;
- validation manifests and evidence bytes.

### GitHub Issue workflow

The managed Issue owns operational state:

- `agent_ready`;
- `agent_working`;
- `human_action_required`;
- `blocked`;
- `complete`.

Its phase records whether the next agent should perform implementation, repair, delivery evidence, or merge closeout.

GitHub workflow state does not create delivery or conformance.

## Managed Issue state

The Issue body contains a visible dashboard and hidden `nsc-workflow-state` JSON.

Every transition is an append-only Issue comment containing a hidden `nsc-workflow-event` JSON object. Event IDs form a SHA-256 chain. The managed state must match the final event and exactly one matching state label.

State labels:

```text
nsc-state:agent-ready
nsc-state:agent-working
nsc-state:human-action
nsc-state:blocked
nsc-state:complete
```

If the state block, label, task-contract hash, event sequence, previous-event chain, or final state disagrees, agents stop for reconciliation.

## Agent lease

An agent may begin task work only after it acquires a managed lease.

The lease transition records:

- worker ID;
- exact current main commit;
- intended task branch;
- canonical checkout path;
- concrete planned approach;
- expected validation.

Before granting the lease, the workflow checks other managed Issues for overlapping task `exclusive_resources`. Issues in `agent_working`, `human_action_required`, or `blocked` continue reserving their resources.

The Issue then becomes:

```text
agent_working
```

Only the worker named in the lease may continue that state.

GitHub assignment to `cathode26` remains a visible repository convention, but assignment alone no longer establishes agent ownership. The managed state and lease do.

## Canonical checkout

The shared controller checkout is:

```text
C:\NSC\NSC\NoSafeCircle
```

The task checkout is:

```text
C:\NSC\NSC\<TASK-ID>
```

The task ID remains hyphenated. Do not create `NoSafeCircle-NSC...`, `-DECOMP`, `-FINAL`, or timestamped task-checkout variants.

The workflow creates a standalone clone from the approved remote, validates the exact task contract and TaskGraph, creates the deterministic task branch, and writes its checkout identity manifest outside the repository.

After a human handoff, the checkout may be resumed by a different agent worker. The task branch/commit—not the old worker ID—is the durable checkout identity.

A missing checkout can be recreated from the exact recorded remote task branch and handoff commit.

## Agent-to-human handoff

A human handoff is allowed only after the task work is:

- committed;
- in a clean canonical checkout;
- on the recorded task branch;
- descended from the workflow base;
- pushed as the exact remote task branch;
- still bound to the current task-contract hash.

The agent appends an Issue comment containing:

- branch;
- exact commit to test;
- checkout path;
- concrete implementation summary;
- checks already completed;
- numbered Unity steps;
- expected result;
- PASS/FAIL result template.

The Issue then becomes:

```text
human_action_required / unity_runtime_validation
```

Agents stop. Vincent owns the next action.

## Human result

Vincent tests the exact handoff commit and posts:

```text
## Human validation result

Result: PASS
Tested commit: `<40-character commit SHA>`

Completed steps:
- ...

Notes:
...
```

or:

```text
## Human validation result

Result: FAIL
Tested commit: `<40-character commit SHA>`

Failed step:
...

Reproduction:
...

Expected:
...

Observed:
...
```

Vincent then applies:

```text
nsc-state:agent-ready
```

The Issue workflow Action validates the managed state, event chain, result format, and exact tested commit.

Result transition:

```text
PASS -> agent_ready / delivery_evidence
FAIL -> agent_ready / repair
```

An invalid transition restores `nsc-state:human-action` and leaves a rejection comment.

## Later-agent resume

A later generic agent discovers the Issue through `issue_queue.py`, acquires a new lease, and resumes the recorded branch and commit.

After PASS it continues authoritative validation, TaskDelivery, evidence, conformance, and closeout.

After FAIL it uses the human report as repair input, commits and pushes a new branch commit, and creates a new human handoff.

The same Issue retains every handoff and result.

## Blocked and complete

Use `blocked` for a human decision or external prerequisite that prevents the next authorized action. Record the exact blocker and safe work that can continue.

Use `complete` only after the normal delivery, evidence, conformance, merge, and operational closeout process is finished. Closing an Issue by itself never establishes TaskGraph conformance.

## Decomposition work

Decomposition remains review-only until separately applied. A decomposition Issue can use the same durable workflow states, but `review_ready` decomposition does not mean the parent implementation is delivered.

Follow:

```text
Pipeline/TaskDecomposition/README.md
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
```

## Authority boundary

The Issue state machine grants bounded operational authority. It never overrides:

- the selected task contract;
- approved GDD canon;
- exact write boundaries;
- Unity testing policy;
- human review requirements;
- delivery evidence validation;
- TaskGraph conformance;
- merge authority.
