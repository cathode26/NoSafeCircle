# Session: Stage 4.1 Repository Binding Safety

Date: 2026-08-30

## Goal

Remove implicit or hard-coded production-repository authority from active TaskReviewAgent Issue, checkout, and downstream GitHub operations, while preserving the existing claim/Issue architecture.

## Starting point

The work was developed on:

```text
branch: stage4-repository-binding-safety
reviewed base: fbe193f9578f02110005c78a72f7ef0d6a7fff06
```

The candidate patch was restricted to eight files:

```text
Pipeline/TaskReviewAgent/downstream_pipeline.py
Pipeline/TaskReviewAgent/downstream_runtime.py
Pipeline/TaskReviewAgent/durable_checkout.py
Pipeline/TaskReviewAgent/issue_workflow_store.py
Pipeline/TaskReviewAgent/real_checkout.py
Pipeline/TaskReviewAgent/tests/downstream_smoke_test.py
Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py
Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py
```

## Durable decisions

- The controller checkout origin is repository authority.
- Explicit repository arguments are assertions, not alternate/fallback authority.
- Task checkout origin must match controller origin.
- Downstream PR/Issue operations use the checkout-bound repository.
- Repository/checkout mismatch fails before GitHub mutation.
- Missing controller origin fails closed.
- Human-readable rejected credential-bearing URLs use the shared redactor.
- Stage 1 claim behavior is not changed by this patch.
- Stage 5 remains out of scope.
- Autonomous dispatch remains disabled.

## Review

The final adversarial Fable closure reported:

```text
STAGE 4 REPOSITORY BINDING READY TO COMMIT
```

It reported the prior MEDIUM findings closed and no new BLOCKER/HIGH/MEDIUM defect.

A LOW follow-up was noted: some structured observation fields such as `remote_url` may still carry an unredacted credential-bearing origin even though human-readable rejection strings are redacted. This was explicitly treated as non-blocking for Stage 4.1.

The PowerShell wrapper independently reached:

```text
[PASS] STAGE 4.1 FINAL REVIEW COMPLETE
```

## Validation history

The delivery gate exercised the relevant TaskReviewAgent regression surface, including:

- Issue workflow
- real checkout
- durable checkout
- resumable checkout
- downstream
- mainline reintegration
- Stage 1 claims
- Stage 2 dispatch
- Stage 3 fresh dispatch
- Stage 4 stress
- resource reservations
- workflow runtime
- CI routing
- TaskGraph validation
- Python compile
- scoped whitespace validation

Several reruns were blocked by Windows temporary bare-Git fixture permission errors. The important production behavior remained correct: those failures were classified as `claim_operational_error`, not ordinary claim contention.

The wrapper was improved to normalize captured whitespace before matching known Windows fixture failures because PowerShell inserted line wraps inside messages such as:

```text
unable to migrate objects
to permanent storage
```

and even inside:

```text
NSC-80
1.lock
```

These were test-environment flakes, not production claim correctness failures.

## Latest session-reported ending state

A later continuation established that the exact patch commit had already been created:

```text
patch commit: b6f21afdf87e3c4309f59f832dd19859a3bc7d7c
parent/reviewed base: fbe193f9578f02110005c78a72f7ef0d6a7fff06
branch: stage4-repository-binding-safety
branch pushed: yes
PR: not yet created
main: reported unchanged
```

This state must be verified against real Git/GitHub before acting.

The key recovery point is:

> **Do not create another commit merely because an older delivery runner expected `HEAD == fbe193f...`. The commit step already happened if Git confirms `b6f21af...`.**

## Next action

Verify the exact branch/commit/remote/PR/main state.

If the reported state is still correct:

1. reuse the existing `b6f21af...` patch commit;
2. create or reuse the PR for that exact head;
3. run/verify exact-head CI;
4. merge only if main/integration safety checks still hold;
5. verify fresh main and clean local state.

Then move to the dedicated multi-worker Gauntlet preparation and live concurrency proof.

## Do not repeat

Do not rerun Sonnet/Fable Stage 4.1 implementation/review unless new code or new evidence invalidates the prior approval.

Do not treat Windows temp-Git fixture permission failures as claim contention.

Do not rewrite historical logs to replace old checkout paths.

## Raw historical sources

- `raw/imported-2026-08-30-Build-Task-Orchestrator2.txt`
- `raw/imported-2026-08-30-Build-Task-Orchestrator1.txt`

## Authority reminder

This file records session history. Current Git, TaskGraph, GitHub Issue/PR state, remote refs, committed configuration, and deterministic tests are authoritative.
