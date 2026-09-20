# Design problem: make the ordinary Game Task Agent command truly get work

## Frozen repository

Commit: `131cc63079532c0e741aa69791681fa153b0ebc5`

Inspect the repository at this exact commit. Treat documentation and existing code as claims to verify, not as automatically correct architecture.

## Operator goal

The operator wants one ordinary command, with no task ID, to mean:

1. Resume the highest-priority existing durable agent-ready task when one exists.
2. Otherwise safely select and claim a new eligible TaskGraph task.
3. Permit two or more copies of the same command to start concurrently and receive different non-conflicting tasks.
4. Continue using the existing Issue state machine, isolated task branches/checkouts, human Unity validation, delivery evidence, pull request, merge, and closeout pipeline.

The command must not require the operator to inspect the TaskGraph or manually supply `-TaskId` during normal work.

## Confirmed current behavior

With no `-TaskId`, `run_pipeline_agent.py` calls the generic Issue selector. `generic_selection.py` looks only for an already initialized and validated `nsc-state:agent-ready` Issue. If the queue is empty it stops with:

> No validated agent-ready Issue exists. Pass an explicit -TaskId to begin fresh work; generic resume never silently invents a new task.

`Pipeline/TaskGraph/execution_authority.py` currently denies every autonomous dispatch because dependency-readiness and dispatch policy have not been implemented or approved.

The existing workflow already has valuable mechanisms that should be preserved unless a reviewer proves they are wrong:

- append-only workflow events in GitHub Issues;
- `agent_ready -> agent_working` leases with worker and lease IDs;
- separate task branches and isolated checkouts;
- exclusive-resource conflict checks;
- durable human handoff and downstream closeout;
- completed-Issue duplicate prevention;
- deterministic TaskGraph conformance evaluation.

## Required properties

The final design must provide all of these:

### Deterministic authority

- A committed, reviewable, versioned dispatch policy must explicitly authorize fresh-task selection.
- An LLM must not choose the task.
- `not_delivered` alone must not imply readiness.
- Dependency readiness, task kind/scope/decomposition, contract disposition, WIP limits, priorities, resource reservations, and existing workflow/branch state must be handled explicitly.
- The design must explain where task priority comes from. Task-number ordering must not silently become product priority.

### Correct concurrency

Starting two generic workers from an empty Issue queue must not assign the same task or conflicting resources.

The design must identify a real linearization point for a fresh claim. Labels and ordinary read-then-write Issue updates are not automatically compare-and-swap operations. Analyze at least these options and choose one:

- atomic creation of a deterministic remote Git ref/task branch as the claim;
- a serialized GitHub Actions dispatcher;
- append-only claim election through a durable coordination Issue;
- another mechanism with stronger evidence.

Do not rely only on a local file lock because the durable architecture should remain safe across processes and eventually across machines.

### Recovery

Define deterministic recovery for failure after each boundary, including:

- candidate selected but claim not won;
- claim won but Issue not created;
- Issue created but lease not acquired;
- lease acquired but checkout not created;
- process crash;
- stale/orphan branch or claim;
- task contract or `main` advancing during dispatch;
- candidate becoming resource-conflicted during the claim;
- zero eligible work;
- completed or previously abandoned tasks.

### Operator semantics

Recommend the exact CLI behavior and exit statuses for:

- normal no-argument â€œget workâ€;
- explicit `-TaskId` override;
- resume-only mode, if retained;
- no work available;
- policy disabled;
- all candidates blocked by dependencies/resources/WIP;
- concurrent worker loses a claim and retries another candidate.

The normal command should remain simple.

### Minimal safe implementation

Name exact existing modules/functions to change and any new modules or policy files to add. Specify schemas, state transitions, durable receipts/events, and test seams. Prefer deterministic host code over additional model prompting.

### Tests

Specify a deterministic regression suite. It must include a real two-worker race from an empty queue and prove distinct task assignment, no duplicate Issues, no split leases, no overlapping exclusive resources, and recoverability from orphaned claims.

## Files to inspect at minimum

- `Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1`
- `Pipeline/TaskReviewAgent/run_pipeline_agent.py`
- `Pipeline/TaskReviewAgent/generic_selection.py`
- `Pipeline/TaskReviewAgent/durable_selection.py`
- `Pipeline/TaskReviewAgent/issue_queue.py`
- `Pipeline/TaskReviewAgent/issue_workflow.py`
- `Pipeline/TaskReviewAgent/issue_workflow_store.py`
- `Pipeline/TaskReviewAgent/completed_issue_guard.py`
- `Pipeline/TaskReviewAgent/real_workflow.py`
- `Pipeline/TaskReviewAgent/production_pipeline.py`
- `Pipeline/TaskReviewAgent/resumable_checkout.py`
- relevant TaskReviewAgent tests
- `Pipeline/TaskGraph/taskcontrol.py`
- `Pipeline/TaskGraph/execution_authority.py`
- `Pipeline/TaskGraph/current_conformance.py`
- `Pipeline/TaskGraph/persistent_work_graph.py`
- `Pipeline/TaskGraph/RESOURCE_GROUPS.yaml`
- `Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml`
- representative `Tasks/NSC-*.yaml`
- `Docs/AI-Pipeline/ISSUE_WORKFLOW_STATE_MACHINE.md`
- `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`

## Do not do these things

- Do not edit repository files or GitHub state.
- Do not propose â€œjust pass `-TaskId`â€ as the final operator workflow.
- Do not let an LLM rank or select tasks.
- Do not equate conformance with dependency readiness without an explicit policy.
- Do not use labels alone as an atomic distributed lock.
- Do not silently enable every active task.
- Do not add a database or large scheduler unless the failure model proves it is necessary.
- Do not optimize only for a single local process while claiming multi-worker correctness.