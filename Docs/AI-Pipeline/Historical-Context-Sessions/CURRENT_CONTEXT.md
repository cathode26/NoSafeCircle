# Current Task Orchestrator Context

Last context update: 2026-08-30

> **Important:** Dynamic Git/GitHub facts below are the **last session-reported state**, not independent authority. Before any commit, push, PR, merge, claim, checkout mutation, or workflow transition, re-read the current repository and GitHub state.

## Current objective

Build a generic multi-worker Game Task Agent / TaskReviewAgent that can safely advance useful No Safe Circle work with minimal operator shepherding.

The desired long-term operator experience is one generic “do work” command. Multiple workers should be able to run concurrently, while the system:

- finishes advanced actionable work before starting new work;
- respects TaskGraph dependencies;
- avoids exclusive-resource/write-surface conflicts;
- uses atomic Git claims to arbitrate concurrent starts;
- uses GitHub Issues as durable agent/human workflow state;
- isolates implementation in task checkouts;
- serializes integration through current `main`;
- revalidates after integration;
- stops at genuine human-authority boundaries rather than inventing authority.

## Canonical local layout

Controller/main checkout:

```text
C:\NSC\NSC\NoSafeCircle
```

Task checkout root:

```text
C:\NSC\NSC
```

Canonical task checkout:

```text
C:\NSC\NSC\NSC-###
```

Durable local TaskReviewAgent state/output root:

```text
C:\NSC\NSC\.task-review-agent
```

Historical paths under `C:\UnityProjects\...` may legitimately remain inside old evidence/transcripts and must not be rewritten merely to match the new convention.

## Current workstream

### Stage 4.1 — Repository Binding Safety

Purpose: remove implicit/hard-coded repository authority from active TaskReviewAgent Issue, checkout, and downstream PR/Issue paths.

Key decisions already reviewed:

- controller checkout `origin` is production repository authority;
- an explicit repository argument is an assertion, not an alternate authority source;
- task checkout origin must match controller origin;
- downstream GitHub operations use the checkout-bound repository;
- missing/mismatched repository identity fails closed;
- credential-bearing rejected URLs are redacted in human-readable rejection paths;
- Stage 1 claim semantics are unchanged by this patch;
- autonomous dispatch remains disabled unless explicitly enabled.

Final adversarial review verdict reported:

```text
STAGE 4 REPOSITORY BINDING READY TO COMMIT
```

### Last session-reported Git state

The most recent continuation discussion reports:

```text
branch:          stage4-repository-binding-safety
reviewed base:   fbe193f9578f02110005c78a72f7ef0d6a7fff06
patch commit:    b6f21afdf87e3c4309f59f832dd19859a3bc7d7c
branch pushed:   yes
PR created:      no
main advanced:   no (as last reported)
```

The important recovery lesson is that the delivery runner originally assumed `HEAD` was still the reviewed base even though the exact reviewed commit had already been created. **Do not create another Stage 4.1 commit if Git confirms `b6f21af...` is already the exact eight-file patch.**

Verify all of the above before acting.

## Stage 4.1 reviewed patch surface

The reviewed patch was reported as exactly these eight files:

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

## Architecture that should survive future refactors

```text
TaskGraph
    logical readiness / dependencies / contracts

Exclusive resources + write boundaries
    concurrency compatibility

Git atomic claim refs
    short-lived race arbitration only

GitHub Issue workflow
    durable lease, phase, human/agent ownership, event log, resume token

Task checkout / branch
    isolated implementation state

ExecutionCrew / providers
    bounded semantic implementation and repair

Deterministic validation
    factual authority over scope, Git identity, tests, evidence, conformance

Integration
    serialized through current main + revalidation
```

The central rule remains:

> Model output is evidence or a proposal; deterministic project state owns factual authority.

## Non-negotiable decisions

- GitHub Issue workflow state is long-lived operational authority.
- Git claim refs are short-lived arbitration only.
- Claim acquisition/release uses exact CAS semantics; no “check then create” race.
- No TTL-based automatic deletion of stale claims.
- Stale-claim repair is exact-SHA/manual unless a later reviewed design explicitly changes that.
- A claim race loser should recompute work; contention is not a catastrophic pipeline failure.
- Generic scheduling should prefer finishing the most advanced actionable task before starting fresh work.
- Dependency readiness alone is insufficient for parallel safety; exclusive resources/write surfaces must also be compatible.
- Integration can be serialized even while implementation is massively parallel.
- Unknown TaskReviewAgent files should fail safe into Core CI coverage.
- Autonomous dispatch remains disabled until deliberately enabled and proven.
- Historical evidence is not rewritten to match current paths/configuration.
- Canonical Windows controller root is `C:\NSC\NSC\NoSafeCircle`.

## Operational hazards already encountered

Do not rediscover these from scratch:

- Windows PowerShell 5.1 may turn harmless native stderr into terminating errors.
- Multi-line PowerShell strings sent into Linux containers need CRLF -> LF normalization.
- Codex strict structured-output schemas require strict `required` handling, including nullable fields.
- `gh` JSON should be treated as UTF-8; Windows default code pages caused decoding failures.
- Task checkouts can have stale `origin/main` after controller main advances.
- Opening Unity can dirty known `ProjectSettings` files even when gameplay code is unchanged.
- A blocked/no-progress action must trip a circuit breaker rather than consume dozens of supervisor turns.
- Windows temporary bare-Git race fixtures can fail with filesystem/permission flakes; production must still classify those as operational errors rather than ordinary claim contention.
- PowerShell can insert line breaks into captured native error text; normalize whitespace before matching multi-word fixture signatures.
- Long Windows checkout roots caused path-length failures; the canonical root was shortened to `C:\NSC\NSC`.
- Docker provider authentication is intentionally persisted in named volumes; do not replace working CLI-volume authentication with unnecessary API-key prompts.
- Long-running agent commands should stream visible progress/heartbeats to PowerShell.

## Immediate next action

First verify the current Stage 4.1 state from the real repository and GitHub.

Minimum verification questions:

1. Is `stage4-repository-binding-safety` the intended branch?
2. Does commit `b6f21afdf87e3c4309f59f832dd19859a3bc7d7c` exist locally/remotely?
3. Is it exactly the reviewed eight-file patch with parent/base `fbe193f...`?
4. Is the branch already pushed at that exact commit?
5. Is there already an open PR for that branch?
6. Has `origin/main` advanced since the reviewed base?

If the reported state is confirmed, continue from the existing patch commit: **create/reuse the exact PR, run exact-head CI, and merge safely. Do not recommit.**

After Stage 4.1 lands, the next planned milestone is the dedicated multi-worker **Gauntlet**: update the Gauntlet template from the new main, use a dedicated/private GitHub repository with synthetic Issues, and run real simultaneous workers to prove concurrency behavior outside local synthetic fixtures.

## Read next

For rationale and detailed Stage 4.1 history:

- `2026-08-30-stage4-repository-binding.md`

For older/full history only when necessary:

- `raw/imported-2026-08-30-Build-Task-Orchestrator1.txt`
- `raw/imported-2026-08-30-Build-Task-Orchestrator2.txt`
- `raw/imported-2026-08-30-Set-Coding-Standards.txt`
