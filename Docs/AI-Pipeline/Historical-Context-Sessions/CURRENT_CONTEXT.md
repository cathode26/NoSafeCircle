# Current Task Orchestrator / Live Gauntlet Context

Last context update: 2026-08-31

> **Important:** Dynamic facts in this file are a continuation checkpoint, not authority by themselves. Before any mutation, re-read current Git, TaskGraph, GitHub Issue/PR, Actions, and remote-ref state. Current deterministic state wins.

## Immediate objective

Finish the first complete live synthetic task lifecycle in the private 85-task Orchestrator Gauntlet before increasing concurrency.

The current task is **NSC-601**. Its implementation, human PASS, synthetic delivery evidence, and durable evidence-head checkpoint have succeeded. It is now parked at `merge_closeout`.

The immediate blocker is **required exact-head CI on private PR #9**, not implementation logic.

Do not start another worker until that CI authority is resolved.

## Canonical repositories / local roots

Production:

```text
GitHub: cathode26/NoSafeCircle
local:  C:\NSC\NSC\NoSafeCircle
```

Private live Gauntlet:

```text
GitHub: cathode26/TaskOrchestratorGauntletLive-20260831
local:  C:\NSC\NSC\TaskOrchestratorGauntletLive-20260831
```

Historical Stage-4 Gauntlet:

```text
cathode26/orchestrator-gauntlet-stage4-20260830-060118
```

Treat the historical Stage-4 repo as read-only evidence.

## Production code checkpoint

Last independently verified production `main` / code checkpoint:

```text
0596dea8258718208a968cb36c18a552d2366441
```

This is the merge of production PR #109:

```text
TaskReviewAgent: complete bounded read-after-write verification
```

The repair centralizes bounded post-mutation rereads, never replays a successful mutation, and fails closed on conflicting/sufficiently-new authority.

Production Issue #104 remains open only as a **live acceptance gate**.

### Stage 5

The reviewed Stage 5/D1C design blueprint is merged.

**Stage 5 implementation is NOT STARTED and remains frozen until the live Gauntlet is accepted.**

## Private live Gauntlet checkpoint

Last independently verified private `main`:

```text
3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
```

This includes:
- production #104 TaskReviewAgent behavior resynced into the private repository;
- Gauntlet-only synthetic implementation adapter;
- synthetic DELIVERY evidence / real TaskGraph conformance support;
- synthetic downstream delivery-review / merge-closeout lifecycle;
- crash/resume downstream hardening;
- private CI compatibility guard for production-only `Tasks/NSC-050.yaml`.

## Current live durable Issues

There are four managed live Issues.

### #1 — NSC-601

```text
state:                 agent_ready
phase:                 merge_closeout
state_version:         13
branch:                gauntlet/nsc-601-submission-1
durable head:          33af4366a06e81e9e3c8751cbeb834722ebe183b
human_handoff_commit:  2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
human_result:          pass
```

Meaning:

- `2cf3759a...` is the exact human-tested candidate.
- `33af4366...` is the exact evidence commit.
- The tested candidate identity is intentionally preserved separately from the evidence head.
- The worker reached a deliberate evidence-head checkpoint and released durable ownership.
- Merge has **not** been attempted.

### #2 — NSC-602

```text
state:     agent_working
phase:     implementation
worker_id: gauntlet-bootstrap
```

This is the interrupted-work resume fixture.

### #3 — NSC-603

```text
state: human_action_required
phase: unity_runtime_validation
```

This is the human-hold fixture.

### #4 — NSC-604

```text
state: agent_ready
phase: repair
```

This is the repair-priority fixture.

Do not delete/recreate these Issues.

## Private PR #9 — current acceptance boundary

```text
PR:         #9
title:      NSC-601: synthetic delivery evidence
state:      OPEN
base:       main
base SHA:   3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
head branch: gauntlet/nsc-601-submission-1
head SHA:   33af4366a06e81e9e3c8751cbeb834722ebe183b
changed files: 4
```

### Required CI is still red

Latest verified exact-head Actions state on `33af4366...` includes:

```text
Canonical Checkout Root Policy:           SUCCESS
D1B.2 Core Deterministic Validation:       SUCCESS
TaskReviewAgent Deterministic Validation:  FAILURE
```

Latest failing TaskReviewAgent run:

```text
run id: 33433789299
job:    windows-smoke
```

The failure is the production-only `NSC-050` real-repository smoke fixture.

The private `main` workflow **has already been repaired** to guard that fixture when `Tasks/NSC-050.yaml` is absent. However, after PR #9 was refreshed/reopened, the new exact-head run still executed the old unguarded behavior from the immutable evidence head.

So this already failed:

```text
repair private main
→ close/reopen PR #9
→ expect fresh PR run to use repaired guard
```

Do not blindly repeat it.

## Next action

Diagnose and prove the correct **exact-head CI/check authority** for PR #9 without changing the evidence SHA.

Before any mutation, re-read:
1. private PR #9 metadata/head/base;
2. workflow runs on `33af4366...`;
3. private `main`;
4. Issue #1;
5. live `refs/nsc/claims/*`.

Then determine how the repaired Gauntlet-compatible deterministic policy can validly produce the required green check on the immutable evidence commit.

Until that is solved:

- do not modify `33af4366...`;
- do not merge PR #9;
- do not run another worker;
- do not recreate the Issue/branch;
- do not launch a contention or 10-worker wave.

Once exact-head CI is legitimately green:

```text
resume exactly one NSC-601 merge_closeout worker
→ inspect/merge PR #9
→ verify main contains exact evidence
→ verify unmodified TaskGraph says NSC-601 conformant
→ verify Issue #1 complete
→ verify dependent work unlocks
→ verify claims return to zero
```

Then:
1. close production #104 as live-proven;
2. run a small multi-worker contention proof;
3. launch the 10-worker wave against the 85-task graph;
4. keep Stage 5 implementation frozen until Gauntlet acceptance.

## Architecture invariants

```text
TaskGraph
  logical dependencies/contracts/conformance

Exclusive resources + write boundaries
  concurrency compatibility

Git claim refs
  short-lived atomic race arbitration only

GitHub Issue
  durable workflow/lease/human-agent authority

Task checkout + branch
  isolated task work

Execution backend
  production Unity executor OR explicit Gauntlet synthetic executor

Delivery evidence
  legitimate committed TaskGraph evidence, never fake completion

Integration
  serialized through current main and revalidated
```

Non-negotiable:
- Issue workflow state is durable authority.
- Git claims are not long-lived leases.
- No TTL claim deletion.
- Contention loser replans instead of treating contention as catastrophic.
- Generic workers prefer actionable resume work before fresh work.
- Repository identity is bound from checkout origin and mismatches fail closed.
- Synthetic execution must not widen production Unity write authority.
- Human-tested candidate SHA and later evidence SHA are distinct authorities.
- Task completion must be derived by real TaskGraph conformance.
- Model output is proposal/evidence; deterministic project state owns factual authority.

## Completed milestones

- Stage 1 — atomic task/resource claims.
- Stage 2 — deterministic fresh-work planning.
- Stage 3 — real generic fresh dispatch.
- Stage 4 — contention loser retries another candidate.
- Stage 4.1 — repository binding / cross-repository safety.
- Live private Gauntlet repository published.
- Four durable resume fixtures bootstrapped.
- Production #104 bounded read-after-write repair implemented and merged.
- Gauntlet-only synthetic execution adapter implemented.
- Synthetic DELIVERY evidence makes real TaskGraph derive conformant/unlock dependencies.
- Synthetic downstream lifecycle implemented and independently reviewed.
- NSC-601 implementation + human PASS + evidence-head checkpoint exercised live.
- Private PR #10 fixed the production-only NSC-050 CI fixture assumption on private main.

## Known command/runner hazards

The detailed backlog is production Issue #103 and the operator/prompt standards.

High-value reminders:
- Windows PowerShell 5.1 compatibility matters.
- Native stderr is not native failure; exit code is authority.
- Keep stdout machine data separate from stderr diagnostics.
- Do not trim whitespace-significant machine formats.
- Prefer scalar `gh --jq length` for cardinality.
- Avoid quote-bearing native mini-languages when a quote-free query exists.
- Allow legitimate empty arrays explicitly in PowerShell parameter contracts.
- Apply `-split`, `-replace`, etc. to a captured/parenthesized value, not directly after a command invocation.
- Use `$($Variable):` / `${Variable}:`, not `$Variable:`.
- Build one semantic native argument into a scalar before inserting it in argv.
- Verify producer JSON schema instead of guessing nested fields.
- Generated `.ps1` must pass parser preflight.
- Mutating runners must observe current state before work and be resume-safe.
- A stopped runner may have completed an earlier durable mutation; inspect authority before retrying.

## Delegation strategy

Use coding agents for bounded implementation/audit work to conserve supervisor context:

```text
strict prompt + invariants
→ disposable clone/branch
→ Codex or Claude
→ host deterministic validation
→ independent review for high-risk changes
→ merge decision
```

Agents must not receive implicit authority to:
- mutate live Issues;
- launch worker waves;
- force-push;
- weaken TaskGraph/claims/leases;
- implement Stage 5;
- broaden scope simply to make tests pass.

## Open follow-ups

Production:
- Issue #103 — command-governance follow-up backlog.
- Issue #104 — keep open until live downstream acceptance completes.
- Issue #106 — synthetic execution architecture record / Gauntlet blocker history.
- PR #108 — draft agent prompt/runner construction rules; review/merge separately without disturbing live acceptance sequencing.

## Read next

Focused handoff:

- `2026-08-31-live-gauntlet-evidence-checkpoint.md`

Earlier Stage 4.1 rationale:

- `2026-08-30-stage4-repository-binding.md`

Raw session archaeology only if needed:

- `raw/imported-2026-08-31-Build-Task-Orchestrator3.txt`

## Authority reminder

This file is working memory. It is not allowed to override current Git/GitHub/TaskGraph state. Verify dynamic facts before mutations.
