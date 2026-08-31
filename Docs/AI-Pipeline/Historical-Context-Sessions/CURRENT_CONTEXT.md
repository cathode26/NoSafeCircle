# Current Task Orchestrator / Live Gauntlet Context

Last context update: 2026-08-31

> **Important:** This file is continuation memory, not authority by itself. Before mutation, re-read current Git, TaskGraph, GitHub Issue/PR, Actions, and remote-ref state. Current deterministic state wins.

## Immediate objective

Finish the first complete live synthetic task lifecycle in the private 85-task Orchestrator Gauntlet.

**The PR #9 exact-head CI blocker is solved.**

The next action is exactly one synchronous NSC-601 `merge_closeout` worker. Do not launch a worker wave.

## Canonical repositories

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

## Production checkpoint

Last verified production **code** checkpoint:

```text
0596dea8258718208a968cb36c18a552d2366441
```

This is production PR #109: complete bounded GitHub read-after-write verification.

Production Issue #104 remains open only as a live-acceptance gate until NSC-601 closeout proves the repaired path end-to-end.

### Stage 5

The reviewed Stage 5/D1C design blueprint is merged.

**Stage 5 implementation is NOT STARTED and remains frozen until live Gauntlet acceptance.**

## Private live Gauntlet checkpoint

Last verified private `main` before NSC-601 merge:

```text
3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
```

It contains:
- production #104 TaskReviewAgent behavior resynced into the private repo;
- Gauntlet-only synthetic implementation/repair adapter;
- synthetic DELIVERY evidence using real TaskGraph conformance;
- synthetic delivery-review / merge-closeout lifecycle;
- crash/resume downstream hardening;
- PR #10's private CI compatibility guard for missing production-only `Tasks/NSC-050.yaml`.

## Current durable Issues

Exactly four live managed Issues remain.

### #1 — NSC-601

```text
state:                 agent_ready
phase:                 merge_closeout
state_version:         13
branch:                gauntlet/nsc-601-submission-1
head_commit:           33af4366a06e81e9e3c8751cbeb834722ebe183b
human_handoff_commit:  2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
human_result:          pass
```

Meaning:
- `2cf3759a...` is the exact human-tested candidate.
- `33af4366...` is the exact evidence commit.
- Those identities must remain distinct.
- The durable Issue is intentionally parked at an evidence-head checkpoint before merge.

### #2 — NSC-602

```text
state: agent_working
phase: implementation
worker_id: gauntlet-bootstrap
```

Interrupted-work resume fixture.

### #3 — NSC-603

```text
state: human_action_required
phase: unity_runtime_validation
```

Human-hold fixture.

### #4 — NSC-604

```text
state: agent_ready
phase: repair
```

Repair-priority fixture.

Do not delete/recreate these Issues.

## PR #9 — exact evidence delivery

```text
repository: cathode26/TaskOrchestratorGauntletLive-20260831
PR:         #9
state:      OPEN
base:       main
base SHA:   3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
head branch: gauntlet/nsc-601-submission-1
head SHA:   33af4366a06e81e9e3c8751cbeb834722ebe183b
```

### Newest exact-head CI is GREEN

The settled PR merge-ref was proven to contain PR #10's repaired Gauntlet-compatible workflow. PR #9 was then closed/reopened again without changing its head SHA.

The newest exact-head runs are:

```text
TaskReviewAgent Deterministic Validation
run: 33441319866
result: SUCCESS

D1B.2 Core Deterministic Validation
run: 33441319813
result: SUCCESS

Canonical Checkout Root Policy
run: 33441320024
result: SUCCESS
```

TaskReviewAgent run `33441319866` passed every Core/Stage 1-4/compile/whitespace step, including the formerly failing deterministic smoke fixture and the long Stage 4 contention test.

Older red runs remain historical on the same commit. `pull_request_check_authority.py` intentionally chooses the newest unambiguous result per logical workflow/job, so those older failures no longer veto the current green authority.

## Exact next action

Run exactly one synchronous synthetic worker after a read-only planner preflight.

The planner must first return:

```text
decision:     resume_existing
task_id:      NSC-601
issue_number: 1
phase:        merge_closeout
branch:       gauntlet/nsc-601-submission-1
commit:       33af4366a06e81e9e3c8751cbeb834722ebe183b
```

Then let the worker itself:

```text
resume merge_closeout
→ acquire real durable authority
→ consume newest exact-head checks
→ merge PR #9 with exact-head protection
→ verify private main contains exact evidence
→ verify unmodified TaskGraph derives NSC-601 conformant
→ complete Issue #1
→ return Stage-1 claim refs to zero
```

Postconditions:
- PR #9 merged from exact evidence head;
- private `main` is the reported PR merge commit;
- exact evidence commit is an ancestor of `main`;
- TaskGraph selects `DEL-NSC-601-2cf3759aaccb` as current conformant record;
- Issue #1 is `complete`;
- Issues #2-#4 are unchanged;
- Stage-1 claims are zero;
- no second worker has started.

If the worker fails after acquiring downstream authority, **do not blindly rerun it**. Inspect Issue/PR/Git/claim authority first.

## After NSC-601 passes

1. Close production Issue #104 as live-proven.
2. Run a small multi-worker contention proof.
3. If clean, launch the 10-worker wave against the 85-task graph.
4. Continue reviewer/downstream cycles until the Gauntlet completion verifier passes.
5. Keep Stage 5 implementation frozen until Gauntlet acceptance.

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
- GitHub Issue state is durable authority.
- Git claim refs are short-lived arbitration, not durable leases.
- No TTL claim deletion.
- Contention loser replans.
- Resume work outranks fresh work.
- Repository identity is bound from checkout origin; mismatches fail closed.
- Synthetic execution must not widen production Unity write authority.
- Human-tested candidate SHA and evidence SHA are distinct authorities.
- Completion must be derived by real TaskGraph conformance.
- Model output is proposal/evidence; deterministic project state owns factual authority.

## Completed milestones

- Stage 1 atomic claims.
- Stage 2 deterministic planning.
- Stage 3 generic fresh dispatch.
- Stage 4 contention retry.
- Stage 4.1 repository binding safety.
- Private live Gauntlet published.
- Four durable resume fixtures bootstrapped.
- Production #104 bounded read-after-write repair implemented/merged/resynced.
- Synthetic implementation adapter implemented.
- Synthetic DELIVERY evidence produces real TaskGraph conformance/dependency unlock.
- Synthetic downstream lifecycle implemented and independently reviewed.
- NSC-601 implementation, human PASS, and evidence-head checkpoint exercised live.
- PR #10 fixed private CI's production-only NSC-050 assumption.
- PR #9 exact evidence SHA now has newest green exact-head CI.

## Command / runner hazards

Production Issue #103 is the detailed backlog. High-value reminders:
- Windows PowerShell 5.1 compatibility matters.
- Native stderr is not failure; exit code is authority.
- Keep machine stdout separate from stderr diagnostics.
- Do not trim whitespace-significant machine data.
- Prefer scalar `gh --jq length` for cardinality.
- Avoid quote-bearing native mini-languages when possible.
- Legitimate empty arrays need explicit parameter support.
- Apply operators such as `-split` to captured/parenthesized values.
- Use `$($Variable):` / `${Variable}:`, not `$Variable:`.
- Precompute one semantic native argument before inserting it in argv.
- Verify producer JSON schema instead of guessing.
- Function output can collapse one-element arrays into scalars; normalize collection shape explicitly.
- `git diff` means unstaged tracked changes; `git diff --cached` means staged; `git diff HEAD` means both.
- Generated `.ps1` runners require parser preflight.
- Mutating runners must observe current state and be resume-safe.

## Delegation strategy

Use Codex/Claude for bounded implementation/audit work when possible:

```text
strict prompt + invariants
→ disposable clone/branch
→ agent implementation
→ host deterministic validation
→ independent high-risk review
→ merge decision
```

Do not give agents implicit authority to mutate live Issues, launch worker waves, force-push, weaken TaskGraph/claims/leases, or implement Stage 5.

## Open follow-ups

Production:
- Issue #103 — command-governance backlog.
- Issue #104 — close after NSC-601 live downstream completion.
- Issue #106 — synthetic execution architecture record / acceptance history.
- PR #108 — draft agent prompt/runner construction rules.

Context archive:
- PR #110 — draft context/archive checkpoint. Keep it unmerged until live acceptance sequencing permits a production-main documentation move.

## Read next

Most recent focused handoff:

- `2026-08-31-pr9-exact-head-ci-recovered.md`

Earlier detailed live handoff:

- `2026-08-31-live-gauntlet-evidence-checkpoint.md`

Raw session archaeology only if needed:

- `raw/imported-2026-08-31-Build-Task-Orchestrator3.txt`

## Authority reminder

This file is working memory. Verify dynamic Git/GitHub/TaskGraph facts before mutation.
