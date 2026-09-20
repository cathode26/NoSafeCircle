# Independent reproduction and classification of public integration audit

Verdict: **BLOCK remains justified. No corrective edits were made.**

Frozen integration: `C:\NSC\PublicPipelineIntegration-Astra-20260907`, branch `integration/production-orchestration-bb560d0e`, HEAD `837eb4f0fa0ba8d619bbb78b500e73ccfd229792`, tree `083cde1aa0b68d48eef769e8844714f06ad5f922`.

Exact base comparison: `C:\NSC\PublicPipelineBaseVerification-20260907`, HEAD `73fae3818ded52eec10e12230de7403cafda4081`. Both remained clean with unchanged HEAD/tree before and after probes. The auditor's `eb3353fc` production gate/workflow files are unchanged in `837eb4f`.

## Scope and method

These are pure/component and serialization regression-only checks, not Unity/gameplay acceptance. They use invented ordinary-human Issue histories, disposable local Git repositories, controlled clocks, and fake provider/process/GitHub transports. No live Issue, external Git remote, provider, Unity project, or public branch was mutated. Git transport was process-limited to `file`. Original auditor evidence/scripts were read and preserved; external wrapper `C:\NSC\public_pipeline_reproduce_audit.py` retargeted source and output locations only for final-head probes.

The baseline publication adapter in `C:\NSC\public_pipeline_base_race_fixture.py` uses the real baseline normal controller constructor and its mainline/Issue fixture. It explicitly verifies that baseline has no integration-window property. Compatibility notification objects are no-ops outside the controller, because no gate API existed at base; no baseline production method was patched or fabricated.

## Findings reproduced

| Finding | Frozen integration observation | Exact public-base classification |
| --- | --- | --- |
| F1: no atomic expected-main publication fence | Real controller accepts a controlled concurrent main commit after the fresh ancestry guard, emits head-only `gh pr merge --match-head-commit`, records `status=merged`; approved task head lacks the concurrent file. One desired-behavior assertion fails, no setup error. | **Behaviorally reproduced at exact base too.** Baseline normal controller also merges against changed main. Inherited publication weakness, not a new transplant algorithm divergence. Added gate does not close it. |
| F2: proven pending write fatals at migration fence | Seven-case workflow probe fails the direct gate filter assertion. Separate real scheduler probe confirms pending reservation/event, zero corruption counter, no architect/process/queue mutation, then `IntegrationGateError` at `require_no_legacy_delivery_owner`. | Gate/window modules are absent at base; no honest same-API gate assertion exists there. This is a new gate/stranded-classifier integration gap, not evidence from an import failure. |
| F3: closed pending completion is discarded | Direct snapshot says pending, but actual bulk reservation API returns `[]`, per-task status is `agent_ready_uninitialized`, and full production snapshot classifies actionable rather than temporary wait. Two desired-behavior assertions fail. | Identical invented history through actual base reservation API also returns `[]` / uninitialized, but base direct classifier does **not** recognize no-label pending. Closed prefilter is inherited; newly supported pending completion was not wired through its consumers. |
| F4: unusable waiter blocks valid delivery | Real valid control launches once. Missing and malformed queued Issues each yield zero launches and owner null while preserving queue; two liveness assertions fail. | Durable integration gate is absent at base, so this queue-specific liveness contract is newly introduced and incomplete, not baseline behavioral equivalence. |
| F5: weaker label-first evidence | Unauthorized label actor and body commit inconsistent with hashed history both receive pending treatment; two assertions fail. | **Both cases behaviorally reproduced at exact base**, with the same pending type and 59-second age. Inherited bounded/non-runnable authority weakness; no unauthorized merge is claimed by these cases. |
| F6: source/main omitted from lease | Captured actual F1 gate owner has task/run/worker/lease/domain but no source or expected-main value. Strict owner schema requires exactly 13 keys and operation schema only kind/start time. | No integration-gate module at base. This is a new lease-contract omission inherited from the validated source implementation, not a foreign-owner takeover demonstration. |
| F7: two defined CI guards not run | Both guards pass actual workflow. In-memory widened prefix still passes registered `main()`, while direct omitted guard rejects it. Confirmed against current child head, not merely auditor's older CI blob. | The ordinary-delivery selection feature/guards were added during the transplant. Registered runner omission is a coverage defect; actual prefix currently passes the guards. |
| F8: runbook drift | Lines 115-117 still describe synthetic private-repository opt-in despite public denial; lines 495/498 refer to absent `muffcabbage_end_to_end_smoke_test.py`, now `production_end_to_end_smoke_test.py`. | Public adaptation/rename documentation was incomplete. No runtime mutation needed to establish this. |

## Exact evidence

Each probe directory has `before.json`, `after.json`, `provenance.json` and result/trace files. Unittest probes additionally have `unittest.log` and `result.json` with failures and error counts.

- F1/F6 final: `C:\NSC\PublicIntegrationF16-Final-20260907` — one assertion failure, zero errors. Local guarded main `b8aa9ca86c28ba46cdd4af326d442623fa40f30b`, main at publication `715c5dd3fdd3f99c218180f2a011bfd707d26770`, published merge `c5c1a9be41ee34ae5f7774aad79ae094e7dd8088`.
- F1 exact base: `C:\NSC\PublicIntegrationF1-Base-20260907` — one assertion failure, zero errors. Guarded main `b45d56dabae037752860b482f1f84ad7184e4d8b`, publication main `f64dce6e3f1ac2c562ba8c538732c7ff6f1733d9`, published merge `152bf3b0d22da6bd996652970d781a9def1f9d47`.
- F2/F3/F5 final: `C:\NSC\PublicIntegrationF235-Final-20260907` — seven cases, two controls pass / five assertions fail, zero errors.
- F2 real scheduler: `C:\NSC\PublicIntegrationF2-Final-20260907` — one assertion failure, zero errors.
- F3 paired actual reservation API: `C:\NSC\PublicIntegrationF3-Discovery-FinalCompatible-20260907` and `C:\NSC\PublicIntegrationF3-Discovery-BaseCompatible-20260907` — both diagnostics execute successfully and record classifier/discovery differences.
- F4: `C:\NSC\PublicIntegrationF4-Final-20260907` — three cases, one valid control pass / two liveness assertions fail, zero errors.
- F5 exact base: `C:\NSC\PublicIntegrationF5-Base-20260907` — two assertions fail, zero errors. Only unused absent-gate import removed in the external harness; workflow production unchanged.
- F7: `C:\NSC\PublicIntegrationF7-Final-20260907` — successful diagnostic confirms registered runner falsely passes the widened-prefix in-memory mutation.

One baseline F3 diagnostic first named the newer `observe_durable_workflows` convenience function, absent at base. That AttributeError is **not behavioral evidence** and is preserved in `C:\NSC\PublicIntegrationF3-Discovery-Base-20260907`. Source inspection identified the actual shared public API, `observe_durable_integration_reservations`; paired compatible diagnostics then ran successfully without changing production.

## Corrections to plan, not yet implement

1. F1/F6 require an explicit publication/lease contract: record exact validated source and main in a versioned owner-bound operation and enforce changed-main refusal at the authoritative mutation. A second client read is not atomic. Choose and test a server-enforced merge queue or equivalent exact-base primitive that preserves required checks and append-only main. Live branch protection/merge service settings have not been inspected; the local fake transport proves the current command does not carry the required expected-main value, not all live-service outcomes.
2. F2 should return a typed bounded wait at the migration fence for proven pending state, preserving reservations and durable queue. A disjoint-admission optimization needs proof of no hidden legacy owner; do not simply ignore pending/invalid ownership.
3. F3 should route authorized closed candidates through full-history proof before deciding that an old incomplete duplicate can be ignored. Cover both prefix lengths, convergence, expiration, malformed suffix and contradictory close events through bulk, per-task and production snapshot consumers.
4. F4 needs explicit durable quarantine/reconciliation and resource-conflict policy, not silent queue removal. Unknown ownership/resources cannot be treated as safe or completed; test conflicting-resource control as well as unrelated progress.
5. F5 should apply actor and complete canonical body/history binding to label-first proof with tampering negatives; preserve valid additive/replaced labels and repeated validation cycles.
6. F7: actually call both defined guards from `main()` and prove the widened-prefix mutation fails through the registered command. F8: update public-disabled guidance and renamed test path.
7. Separately fix the acceptance package allowlist omission identified by the full-case diagnostic; retain the new scheduler-adapter regression in its exact expected file set. This change also remains unapplied under the freeze.

## Existing full-suite result is not approval

At frozen `837eb4f`, 137/138 standard scripts pass, plus TaskGraph/GDD/diff validators (140/141 command records). Windows ILPP all four cases pass with exact source blobs retained. Acceptance standard runner stops on base-reproduced symlink privilege failure; extended all-case diagnostics find the additional package allowlist defect. See `C:\NSC\PublicPipelineFinalValidation-20260907` and `C:\NSC\PublicPipelineIntegrationReport-20260907.md`.

Passing committed regression suites and exact source fidelity do not clear the independently reproduced production-path failures. No corrective changes, commit, push, or remote merge was performed during this diagnosis. Next action: review the publication/queue/lease contracts and authorize bounded corrections while retaining these failing probes as regression evidence.
