# DRAFT, NOT POSTED. Awaiting Vincent's decision on which option to send.

## Context

Issue #36 comment 5651834313 (2026-09-13 07:04 UTC) proposed head
`86068e6490c33bb71b025cbe1b6de204859a24af` for re-check and closed Astra's two
FIX FIRST blockers. In the blocker-1 section it recorded one open decision:

> Decision for Astra: do you want the replay to also require that only
> `parent_task_contract_sha256` and `task_contract_sha256` values differ between the
> two documents? It was left out because you asked for no broadening beyond the named fix.

That decision has since been answered in code, in a commit that was never in the bundle.

## The commit

`5e23243b11d4788e2de550a96582d23571e8f179`, "TaskReviewAgent: require exact policy
re-pin replay diff", authored 2026-09-13 05:25:54 -0500 by cathode26, on branch
`fix/exact-repin-replay-diff` in clone `C:\nscrev\throughput`. Its single parent is
the proposed head `86068e6`. It touches two files, +112/-13:
`Pipeline/TaskReviewAgent/decomposition_replay.py` and the replay smoke test.

What it changes, relative to the audited head:

1. Condition 4 of `_working_policy_is_the_authorized_repin` is replaced. The audited
   head required only that this parent's own `decomposition_child_templates` entry be
   byte-identical at the authorized head and at the D1C commit. The new helper
   `_policy_is_exact_authorized_repin` reconstructs the entire expected policy
   document: it deep-copies the authorized document, and for each dependent task the
   graph delta actually rewrites, it verifies the old pin matches that task's
   committed identity at the authorized head, verifies the new pin matches it at the
   D1C commit, and writes only that one field into the expected copy. It then requires
   the D1C document to equal the reconstruction exactly. Any other difference anywhere
   in the policy refuses.
2. The set of rewritten dependents is derived from the durable graph delta's
   `inbound_dependency_changes`, not from a caller argument.
3. The exception clause around the proof widens from
   `(DecompositionReplayError, ValidationPolicyAuditError)` to `Exception`, still
   returning False, so any unprovable proof refuses rather than propagating.

This is strictly narrower acceptance than the audited head: every policy difference the
audited head accepted is still accepted only if it is exactly a pin re-write of the
dependents this apply touches.

## Verification

Its suite is green on the commit itself, run in a throwaway detached worktree of
`5e23243` isolated from any live run: `automated decomposition replay smoke suite
(15 tests)`, all PASS, worktree removed afterwards. The audited head carried 14 tests;
the added one is `test_apply_that_rewrites_the_parent_template_refuses`, and
`test_exact_d1c_with_unrelated_valid_filter_change_refuses` now proves the whole-document
exactness rather than the single-entry check.

Not yet done for this commit: the failing-before reproduction on `86068e6`, and the
other eight suites that were run on `86068e6`.

## Why this note exists

The disposable 1160 Gauntlet currently running carries `5e23243`, not `86068e6`. Three
of its four controller files are byte-identical to `86068e6`; the replay module is this
stricter variant. So that run is not evidence for exactly the head under re-check.

## OPTION A, if the stack should move

Say: the head for re-check becomes `5e23243`, the open decision is withdrawn because it
is now implemented, and the remaining verification (failing-before on `86068e6`, plus
the eight other suites) will be completed and posted before merge.

## OPTION B, if the stack should stay

Say: `86068e6` remains the head for re-check, `5e23243` exists as a proposed follow-up
answering the open decision, and Astra may review it separately or fold it into the
verdict. The Gauntlet evidence is then labelled as exercising the follow-up, not the
audited head.
