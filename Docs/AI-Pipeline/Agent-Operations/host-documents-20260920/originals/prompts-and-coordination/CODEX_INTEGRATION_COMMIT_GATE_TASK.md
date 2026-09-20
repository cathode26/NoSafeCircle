# Codex task: durable integration/commit gate

Use gpt-6-astra with xhigh reasoning.

Implement a deterministic integration/commit gate for the No Safe Circle Game Task Agent pipeline.

## Repository and safety

- Read AGENTS.md completely and follow the Game Task Agent runbook.
- Use a fresh isolated checkout or worktree.
- Base the work exactly on commit 7749a37dd606621515bc2ed25048558f026660d2.
- Create branch fix/durable-integration-commit-gate.
- Do not touch C:\NSC\Rehearsal\ThreeTaskClaudeClean-20260906-190022Z or any other rehearsal checkout.
- Do not mutate GitHub Issues, pull requests, branches, claims, or running containers.
- Do not run a live gauntlet.
- Do not push. Produce one focused commit using the repository's required automation identity.

## Observed production defect

A clean fully autonomous three-task Claude gauntlet launched NSC-922, NSC-923, and NSC-924 concurrently. Implementation parallelism worked. The delivery phase behaved like this:

1. All three independently merged the then-current main into their branches.
2. All three ran authoritative Unity validation.
3. All three produced delivery evidence and started GitHub CI.
4. NSC-923 merged first.
5. NSC-922 correctly detected that main had changed, reintegrated main, invalidated its old evidence, reran validation, reran CI, and then merged.
6. NSC-924 correctly detected that main had changed again, reintegrated main a second time, invalidated its evidence again, and completed a third validation/CI cycle.

This is safe, but creates triangular/O(N-squared)-like finalization work. Later tasks repeatedly spend Unity time, CI time, provider tokens, and GitHub operations on commits that are predictably going to become stale as earlier tasks merge.

## Required architecture

Add a durable deterministic integration/commit gate. This is not a new LLM agent and must make no provider call. The Software Architect remains responsible for task selection, rigor, capacity, and implementation parallelism. The new gate serializes only the narrow final integration-and-publication window.

A task may implement, validate its initial implementation, and wait for delivery concurrently. Before it performs the final sequence that can publish to main, it must acquire the integration gate.

While holding the gate, the task performs this exact sequence:

1. Refresh authoritative origin/main.
2. Merge current main into its task branch using the existing deterministic reintegration machinery.
3. If that changes the commit, invalidate stale validation/evidence exactly as current policy requires.
4. Obtain validation for the exact integrated commit.
5. Produce delivery evidence for that exact commit.
6. Open or update the pull request and wait for required CI.
7. Merge that exact commit to main.
8. Verify the resulting main state and closeout.
9. Release the gate and immediately wake the next eligible waiter.

The gate must prevent a second task or controller from entering that sequence concurrently for the same repository/main integration domain.

## Core requirements

### 1. Provider-free

- No Claude, Codex, or OpenAI call may be added for gate admission, ordering, acquisition, renewal, release, or wake-up.
- Decisions must be derived from durable workflow state.

### 2. Durable and multi-process safe

- It must work across worker processes and independent controller processes, not merely through an in-memory mutex.
- Reuse the repository's existing claim/ref or durable reservation primitives where appropriate.
- Do not add a global filesystem lock that works on only one machine.
- Do not serialize implementation or ExecutionCrew work.

### 3. Deterministic fairness

- Eligible waiters must have a deterministic order.
- Prefer durable ready/event time, then task ID as a stable tie-breaker.
- A task that cannot acquire the gate returns a nonfatal deferred/waiting result. It must not consume the fatal counter, spin, or invoke the architect/provider repeatedly.
- One bounded/event-driven wait should serve the pending set.
- Releasing the gate must poke/wake the next waiter immediately. Fallback polling is recovery only.

### 4. Exact integration domain

- Key the gate by canonical repository identity and target branch, not checkout path, worker ID, provider, or task ID.
- Different repositories or independent target branches must not block each other.

### 5. Lease identity and stale-owner safety

- Acquisition must record an unguessable lease identity plus task ID, run ID, worker ID, repository identity, target branch, acquisition time, and last confirmed progress or heartbeat.
- Only the exact owner may renew or release.
- A stale artifact, mismatched worker, mismatched run, or missing durable completion receipt must never be treated as success.
- Define and document safe crash recovery. Do not silently steal a gate merely because wall-clock time elapsed while CI or Unity is legitimately running.
- If ownership is uncertain, fail closed with an actionable diagnostic.
- Repeated resume by the same durable owner must be idempotent.

### 6. Human versus automated validation

- Fully automated or synthetic-authority gauntlets should retain the gate across bounded automated revalidation and CI so main cannot become stale underneath them.
- Do not hold the entire repository hostage indefinitely while waiting for an actual human.
- For unbounded human_action_required, release or defer safely. On human return, the task reacquires the gate and rechecks main, accepting that another exact revalidation may be necessary.
- Preserve the rule that human PASS applies only to the exact tested commit. Never fabricate or reinterpret human approval.
- Document this distinction and test it.

### 7. Failure and interruption behavior

- Release on verified terminal completion.
- Define safe handling for test failure, CI failure, merge conflict, provider failure elsewhere, worker crash, controller interruption, and resume.
- Do not release early merely because a subprocess exited zero.
- Do not leak the gate after an ordinary recoverable failure.
- Do not delete immutable logs or evidence.
- Existing active integration reservations must remain observable.

### 8. Preserve current safety

- Keep the existing merge-main-into-task-branch-before-final-validation behavior.
- Never force-push main.
- Never bypass required checks.
- Never merge a stale, unvalidated, or mismatched commit.
- Existing corruption and identity checks must remain fail-closed.
- Do not weaken path-conflict admission or checkout isolation.
- Keep all current provider-neutral behavior.

### 9. Observability

Add durable structured events sufficient to measure:

- gate eligible
- queued
- acquired
- wait duration
- owner identity
- renewed or progress confirmed
- released and reason
- next waiter woken
- crash or recovery decision
- gate-held Unity duration
- gate-held CI duration
- total integration-window duration

Do not log secrets or provider credentials.

### 10. Compatibility and migration

- Existing Issues and runs without gate metadata must remain readable.
- Schema changes must be versioned.
- A resumed old run must fail safely or migrate deterministically. It must not create two owners.

## Regression requirements

Write deterministic tests that fail before the fix and pass afterward. At minimum prove:

A. Three ready tasks may implement concurrently, but only one may enter final integration.
B. With three non-conflicting tasks, each performs at most one post-acquisition main integration, one exact validation/evidence cycle, and one CI/merge cycle when no external writer changes main.
C. Releasing task 1 immediately wakes task 2; releasing task 2 wakes task 3.
D. Queue ordering is deterministic under equal timestamps.
E. A second controller cannot acquire the same repository/main gate.
F. Different repositories or target branches do not block each other.
G. Same-owner resume is idempotent.
H. Foreign, stale, or mismatched release is rejected.
I. A long-running active Unity or CI operation is not reaped solely by elapsed time.
J. A genuinely abandoned owner has a documented fail-closed recovery path.
K. Human-action waiting does not hold the gate indefinitely.
L. Automated exact-commit revalidation may retain the gate through bounded validation and CI.
M. CI, test, or merge failure releases or quarantines according to the documented policy without allowing an unsafe successor.
N. No provider invocation occurs in any gate path.
O. Existing single-task behavior is unchanged except for gate events.
P. Existing reintegration and evidence invalidation tests remain green.
Q. A pre-fix simulation reproduces the three-task repeated-cycle defect; the post-fix simulation proves later tasks no longer run doomed CI cycles.

For every new behavioral regression, explicitly demonstrate that it fails against the base semantics and passes after the implementation. Do not add source-presence or monkeypatch-only tests that could pass without behavior changing. Use real local Git repositories and refs where practical. Make no GitHub, Docker, provider, or Unity live calls.

## Likely areas to inspect

Follow actual call paths rather than assuming these are exhaustive:

- Pipeline/TaskReviewAgent/polling_orchestrator.py
- delivery reintegration and inspect_or_merge_pull_request paths
- issue_workflow_store.py
- durable integration reservation and claim code
- autonomous graph wake-up and local resume hints
- run evidence and timeline instrumentation
- existing contention, reservation, reintegration, synthetic gauntlet, and resume tests

## Deliverables

- Root-cause and call-path explanation with exact file and line references.
- State machine and gate ownership schema.
- One focused commit SHA and exact parent.
- Changed-path list.
- Red-before and green-after evidence for each behavioral change.
- Complete deterministic test results.
- Explanation of expected three-task and ten-task timing and token changes.
- Explicit uncertainties and deliberately excluded follow-ups.
- Confirmation that the checkout is clean, nothing was pushed, and no live Issue, pull request, container, or rehearsal state was touched.
