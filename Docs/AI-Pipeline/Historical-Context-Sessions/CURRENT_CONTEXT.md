# Current Task Orchestrator / Live Gauntlet Context

Last context update: 2026-08-31

> **Important:** This file is continuation memory, not authority by itself. Before mutation, re-read current Git, TaskGraph, GitHub Issue/PR, Actions, canonical checkout, and remote-ref state. Current deterministic state wins.

## Immediate objective

The first complete live synthetic lifecycle is **accepted**.

NSC-601 passed through generic resume, durable Issue lease, canonical checkout, immutable evidence PR, protected merge, post-merge TaskGraph conformance, and durable completion.

**Next:** design and run a deliberately small multi-worker contention proof. Do not launch the 10-worker wave yet.

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

Production code `main` remains:

```text
0596dea8258718208a968cb36c18a552d2366441
```

This includes production PR #109: bounded GitHub read-after-write verification.

Production Issue #104 is now **CLOSED / COMPLETED** after the private live lifecycle acceptance.

Production Issue #103 remains the command-governance backlog.

Production Issue #106 remains the synthetic execution architecture/acceptance record.

### Stage 5

The reviewed Stage 5/D1C design blueprint is merged.

**Stage 5 implementation is NOT STARTED and remains frozen until the live Gauntlet is accepted at the intended concurrency scale.**

## Private live Gauntlet checkpoint

Current accepted private `main`:

```text
77b4fe4cc43968dc5f7a7b2abacb73081348d980
```

This is private PR #9's merge commit.

Immediately before PR #9, private PR #11 repaired the Gauntlet-only synthetic closeout check reader so it reuses production `latest_effective_check_state()` instead of treating superseded historical failures as current.

Private PR #11 merged at:

```text
c92b3d00417ab66416c29a35cee9a17bc0599b06
```

## NSC-601 — accepted lifecycle

Authority identities:

```text
human-tested candidate:
2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f

evidence commit / PR #9 head:
33af4366a06e81e9e3c8751cbeb834722ebe183b

PR #9 merge commit / current private main:
77b4fe4cc43968dc5f7a7b2abacb73081348d980

selected current record:
DEL-NSC-601-2cf3759aaccb
```

PR #9:

```text
state: MERGED
head branch: gauntlet/nsc-601-submission-1
head SHA: 33af4366a06e81e9e3c8751cbeb834722ebe183b
merge commit: 77b4fe4cc43968dc5f7a7b2abacb73081348d980
```

Post-merge TaskGraph:

```text
task: NSC-601
state: conformant
selected_record_id: DEL-NSC-601-2cf3759aaccb
head_commit: 77b4fe4cc43968dc5f7a7b2abacb73081348d980
```

Managed Issue #1:

```text
state: complete
phase: merge_closeout
state_version: 15
branch: gauntlet/nsc-601-submission-1
head_commit: 33af4366a06e81e9e3c8751cbeb834722ebe183b
human_handoff_commit: 2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
human_result: pass
lease_id: null
worker_id: null
label: nsc-state:complete
```

The completion event binds PR #9, merge commit `77b4fe4c...`, conformant record `DEL-NSC-601-2cf3759aaccb`, and post-merge TaskGraph conformance.

Stage-1 claim refs after acceptance:

```text
0
```

## Preserved special fixtures

Exactly four original managed Issues still exist; #1 is complete and #2-#4 remain live special fixtures.

### #2 — NSC-602

```text
state: agent_working
phase: implementation
worker_id: gauntlet-bootstrap
lease_id: a113fedc61c790c53a0a22435aeb787df1d05456ca503e07e25d3e0fa7537c84
```

Interrupted-work resume fixture. It must not be stolen by another worker.

### #3 — NSC-603

```text
state: human_action_required
phase: unity_runtime_validation
branch: gauntlet/nsc-603-pending-decision
```

Human-hold fixture. Generic workers must not mutate it while the human result is absent.

### #4 — NSC-604

```text
state: agent_ready
phase: repair
branch: gauntlet/nsc-604-repair-priority
human_result: fail
```

Repair-priority fixture. A generic worker should resume this before attractive fresh work.

Do not delete/recreate these Issues.

## NSC-601 closeout recovery lesson

The first live closeout worker used:

```text
worker_id: gauntlet-nsc601-closeout-20260831-171058
lease_id: 89a684dcfeda0c54a4c035df600b66d002ce22710cecafccb6f547612bf77c91
```

It acquired the real durable lease and stopped because an acceptance wrapper supplied a fresh `--output-root` instead of the original durable package root.

The original root was:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput
```

The same worker resumed the same lease against that original package/cache and completed. Generic dispatch was not rerun, no second lease was acquired, and no manual merge/reset/Issue rewrite occurred.

This is useful positive evidence for durable resume semantics as well as a command-governance lesson.

## Current CI authority relevant to accepted PR #9

The final pre-merge exact-head runs on evidence SHA `33af4366...` were:

```text
TaskReviewAgent Deterministic Validation
run: 33443876051
result: SUCCESS

D1B.2 Core Deterministic Validation
run: 33443876070
result: SUCCESS

Canonical Checkout Root Policy
run: 33443876048
result: SUCCESS
```

Historical older failures remain evidence only; current logical check authority is newest unambiguous result per production `latest_effective_check_state()`.

## Exact next stage — small contention proof

Do **not** jump directly to 10 workers.

The next proof should be intentionally small and should demonstrate concurrent generic-agent safety while preserving the special fixtures.

Required properties:

1. `NSC-604` repair-ready work outranks fresh work for a generic worker.
2. `NSC-602` remains owned by `gauntlet-bootstrap`; another worker must not steal or rewrite its durable lease.
3. `NSC-603` remains `human_action_required`; no worker treats it as actionable agent work.
4. Ordinary fresh-task contention exercises the real Stage-1 claim namespace and Stage-4 loser replan behavior.
5. Concurrent workers must not create duplicate Issues/branches/leases for one task.
6. Every acquired ephemeral claim is released; zero claim refs remain at the proof boundary.
7. Controller/main and canonical checkouts remain clean or at explicitly verified durable boundaries.

Design the exact worker count and synchronization before launching. Prefer 2-3 concurrent workers, not a broad wave.

The proof should capture each worker's dispatch decision and durable result so we can distinguish:

```text
resume_existing repair
vs
fresh_started
vs
claim_conflict → replan
```

Do not consume or mutate the human-hold fixture merely to manufacture contention.

## After the small contention proof

If the small proof is clean:

1. checkpoint the result;
2. launch the 10-worker live wave;
3. continue reviewer/downstream cycles through the 85-task graph;
4. run the full Gauntlet completion verifier;
5. only then unfreeze Stage 5 implementation.

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
- Contention loser replans only for recognized ordinary contention.
- Resume work outranks fresh work.
- Existing `agent_working` durable ownership must not be stolen.
- `human_action_required` is a real hold, not spare capacity.
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
- Production #104 bounded read-after-write repair implemented/merged/resynced/live-accepted.
- Synthetic implementation adapter implemented.
- Synthetic DELIVERY evidence produces real TaskGraph conformance/dependency unlock.
- Synthetic downstream lifecycle implemented and independently reviewed.
- PR #10 fixed private CI's production-only NSC-050 assumption.
- PR #11 made synthetic closeout reuse production latest-check authority.
- NSC-601 complete live lifecycle accepted.
- PR #9 merged exact evidence into private main.
- NSC-601 post-merge TaskGraph conformance and durable Issue completion proven.

## Command / runner hazards

Production Issue #103 is the detailed backlog. High-value reminders include:
- Windows PowerShell 5.1 compatibility matters.
- Native stderr is not failure; exit code is authority.
- Keep machine stdout separate from stderr diagnostics.
- Do not trim whitespace-significant machine data.
- Prefer scalar machine output for cardinality checks.
- Avoid quote-bearing native mini-languages when possible.
- Normalize one-element/empty collection shape explicitly in PowerShell.
- `git diff` = unstaged tracked; `git diff --cached` = staged; `git diff HEAD` = total tracked delta.
- Generated PowerShell requires parser preflight.
- Generated Python requires more than `py_compile`: audit local helper signatures.
- Critical imported function/constructor calls should be pre-bound with `inspect.signature(...).bind(...)` before mutation.
- Resumable external package/cache roots are continuation identity and must not be silently changed.
- Mutating runners must inspect durable state and continue from it instead of resetting/replaying.

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

Do not give agents implicit authority to mutate live Issues, launch broad worker waves, force-push, weaken TaskGraph/claims/leases, or implement Stage 5.

## Open follow-ups

Production:
- Issue #103 — command-governance backlog.
- Issue #106 — synthetic execution architecture / acceptance history.
- PR #108 — draft agent prompt/runner construction rules.

Context archive:
- PR #110 — draft context/archive checkpoint. Keep it documentation-only and unmerged during the remaining live Gauntlet acceptance sequence unless deliberately deciding to integrate the archive.

## Read next

Most recent focused handoff:

- `2026-08-31-nsc601-live-lifecycle-accepted.md`

Earlier CI handoff:

- `2026-08-31-pr9-exact-head-ci-recovered.md`

Earlier detailed live handoff:

- `2026-08-31-live-gauntlet-evidence-checkpoint.md`

Raw session archaeology only if needed:

- `raw/imported-2026-08-31-Build-Task-Orchestrator3.txt`

## Authority reminder

This file is working memory. Verify dynamic Git/GitHub/TaskGraph facts before mutation.
