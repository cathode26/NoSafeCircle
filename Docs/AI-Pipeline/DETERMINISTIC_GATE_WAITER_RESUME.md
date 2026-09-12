# Deterministic admission of a routed integration-gate waiter

The scheduler can resume a fully proven downstream continuation without another architect invocation. It still launches the normal host worker, which acquires the durable gate and runs current-main integration, exact-commit validation, evidence publication, CI, merge and post-merge verification.

## Original paid-call path

At base `120ec005304508383db651985bceeb975d10bba2`, `GateAdmission.filter()` (`integration_window.py:324`) registers validated delivery waiters and keeps only the durable queue head when there is no owner. Its listener emits `gate_next_waiter_woken` (`:332`). Candidate discovery and the existing safety checks precede this filter. `PollingOrchestrator.poll_once()` applies `resume_priority_applied` (`polling_orchestrator.py:3371`), but then unconditionally enters architect budget/preflight and `architect_started` (`:3418`). Resume priority changes the portfolio, not the provider requirement.

The new seam is immediately after gate filtering, resume priority and the dry-run return, before architect budget/preflight. It rejoins the existing launch loop, including its forced source refresh, fresh Stage 2 plan and reservation checks. No architect advisory object or artifact is created for the shortcut.

## Required proof

Every condition is required, and the proof is repeated before launch:

- The current validated, authorized managed Issue is unleased `agent_ready` in `delivery_evidence` or `merge_closeout`, with no pending transition. The task is single-agent implementation work inside the admission allowlist.
- A fresh read of the durable gate agrees with the admission observation: no owner, and this task is exactly the ordered queue head. Wake packets and labels confer no authority.
- The current committed contract, Issue number/URL and hashed event history, task branch and exact HEAD, canonical checkout, origin repository and remote task branch all agree. The source is clean, attached to main and equal to the just-refreshed origin/main. A local-ahead source is excluded.
- A hash-checked host route receipt binds the actual earlier architect-backed launch to its task, Issue history, source, checkout, repository, worker/run, recommendation, predicted surface and resolved route. The recorded worker must occur in the verified Issue history. Failures, repair/migration events or non-gate error releases after that route disable reuse.
- The existing downstream authority reader verifies human PASS or automated PASS for the current exact commit. Automated validation also verifies the committed test policy and evidence. A corrupt downstream receipt or new unrecognized comment after validation disables reuse.
- The original route source is an ancestor of both current main and the task head. Actual task paths are nonempty and remain inside the established exact predicted paths. New main changes must be disjoint from the actual task paths; changes to validation or execution pipeline code disable reuse.
- Dependencies are currently conformant. Existing capacity, lease, resource, reservation, cooldown, pending-transition and corruption checks remain. Both blocking and architect-confirmable unknown reservation surfaces require judgment. Recent capacity-health failures and the explicit-architect-capacity `thousand` profile are excluded.
- Current provider restrictions and rigor/routing policy reproduce the entire established route exactly, including provider, models, effort, turn budget, crew and validation settings. Any change disables reuse.

Absent, stale or ambiguous optimization evidence emits `integration_gate_resume_requires_architect` and retains the ordinary architect path. Existing earlier fail-closed exclusions remain exclusions. If proof changes between selection and launch, the candidate is withdrawn without launching; the next cycle observes again. The gate's worker-side acquisition remains the final ownership barrier against a change after the scheduler's last read.

`integration_gate_resume_admitted` records zero architect invocations, no advisory artifact, the resolved route, and exact gate OID, Issue event, contract, branch/HEAD, checkout, repository, source-main SHA, validation event, dependency states and route receipt identity. Poll and run counters naturally report zero for this admission.

## Route history and conservative exclusions

The host writes `.task-review-agent/admission-routes/<TASK-ID>.json` beneath the checkout root before an architect-backed implementation launch, using atomic replacement and a semantic hash. It records history; it does not authorize an Issue, gate or worker. A failed later launch replaces the old record, so the scheduler cannot silently reuse an earlier route.

Pre-upgrade workers have no receipt and continue through the architect. This change does not retroactively optimize the already-running rehearsal. A new scheduler worker cannot inherit an existing owner's worker/run contract, so owner-held resumes retain the existing exclusion. A merge-closeout state is eligible only when current HEAD is itself the validated commit; an evidence-only successor commit requiring additional historical proof retains the architect path. Disjoint-path checks are deliberately conservative and may reject a merge Git could perform automatically.

## Regression evidence

`tests/gate_resume_smoke_test.py` drives the real scheduler with disposable local Git repositories and hashed Issue workflows. `NSC_GATE_RESUME_SOURCE` selects the untouched exact application base for paired testing; the test expectations are unchanged between base and candidate.

The suite covers delivery and safe merge-closeout, queue order and conflicting owners, stale wakes, changed identities/receipts/source/policy, feedback and failure, fresh/repair/decomposition work, capacity/scope/cooldown/pending transitions, known and unknown reservations, dependency states, both providers across all rigor tiers, and last-moment proof changes. It verifies current-main worker arguments and performs a real local merge that invalidates the earlier PASS before new validation. A complete automatic-evidence lifecycle records the route on the initial architect-backed launch and resumes through the shortcut to verified completion: one initial architect invocation, two worker launches, and zero architect invocations for the delivery admission.

These are component/regression tests with fake provider, GitHub and Unity boundaries. They do not establish Unity gameplay acceptance. The independent controller wait-contract defect belongs in a separate commit; this change does not alter the controller's wait or drain behavior.
