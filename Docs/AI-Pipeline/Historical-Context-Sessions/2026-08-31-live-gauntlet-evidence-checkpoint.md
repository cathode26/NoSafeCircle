# Session: Live Gauntlet — Synthetic Lifecycle, #104 Hardening, and NSC-601 Evidence Checkpoint

Date: 2026-08-31  
Session/topic: Task Orchestrator live multi-worker Gauntlet

## Goal

Advance the Stage 1–4.1 TaskReviewAgent from local/synthetic regression coverage into a real private GitHub acceptance environment, prove one real generic worker through durable selection/claim/Issue/checkout/downstream boundaries, and prepare the 85-task live concurrency Gauntlet.

This session also deliberately delegated large implementation and review slices to Codex and Claude while retaining deterministic host validation and human/architect merge authority.

## Starting state

The session began immediately after Stage 4.1 repository-binding safety had landed in production and the historical-context system had been introduced.

Early verified checkpoint:

```text
production repository: cathode26/NoSafeCircle
Stage 4.1 merge:        305930b5e3323a3f9533b6f5973df6a63685a5be
Stage 4.1 patch:        b6f21afdf87e3c4309f59f832dd19859a3bc7d7c
```

The existing 85-task Gauntlet V2 fixture was preserved rather than regenerated.

## Major decisions made

### Live Gauntlet authority

A dedicated private repository is the acceptance environment:

```text
cathode26/TaskOrchestratorGauntletLive-20260831
```

The older repository:

```text
cathode26/orchestrator-gauntlet-stage4-20260830-060118
```

is historical Stage-4 evidence and should remain intact.

Production `NoSafeCircle` must never become the Gauntlet's durable synthetic Issue authority.

### Synthetic execution boundary

The live generic orchestrator is more generic than the production implementation engine.

Production `ExecutionCrew` / repository scope is intentionally Unity-specific and cannot legitimately execute synthetic Fibonacci/dice work under `Gauntlet/`. The accepted design is therefore:

```text
REAL production orchestration
  generic dispatch
  dependency/resource filtering
  atomic Git claims
  durable GitHub Issue lease
  resumable checkout/branch authority
        ↓
Gauntlet-only synthetic execution adapter
        ↓
REAL production downstream Issue/lease semantics
        ↓
REAL TaskGraph DELIVERY evidence/conformance
```

Do **not** globally widen production Unity read/write roots merely to make the Gauntlet pass.

### Synthetic downstream boundary

Synthetic delivery must not fake conformance or completion.

Job 1 established a real evidence package that makes the unmodified TaskGraph derive `conformant` and unlock a real dependent task.

Job 2 wired this evidence mechanism into durable delivery-review / merge-closeout lifecycle semantics.

### Human-tested candidate identity vs evidence identity

For NSC-601:

```text
human-tested candidate:
2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f

evidence commit:
33af4366a06e81e9e3c8751cbeb834722ebe183b
```

The tested candidate remains `human_handoff_commit`. The durable Issue `head_commit` may advance to the evidence commit during `merge_closeout`. Those identities are intentionally different and must not be collapsed.

### Eventual-consistency repair

GitHub write -> immediate read is not reliable enough for durable state verification.

Production #104 now uses bounded read-only verification after successful mutations:
- do not replay the mutation;
- accept only exact expected state;
- fail closed on same/newer conflicting authority;
- fail closed after finite stale-read retries.

### Stage 5

Stage 5/D1C design work was allowed in parallel as design/audit only. The blueprint was reviewed and merged, but **Stage 5 production implementation remains unstarted and frozen until Gauntlet acceptance**.

### Delegation model

For large bounded implementation slices:

```text
architect defines invariants
→ Codex/Claude implements in disposable clone
→ host enforces path/authority boundaries + deterministic tests
→ independent model reviews high-risk work
→ architect decides merge
```

Do not spend the supervisor context manually reproducing large coding-agent work when the job can be delegated safely.

## Work performed

### Command/operator governance

Production gained:
- `OPERATOR_COMMAND_STANDARDS.md`
- `OPERATOR_COMMAND_TEMPLATE.md`
- mandatory AGENTS/CLAUDE pointers
- deterministic PowerShell/native-command policy smoke coverage

Later command failures were recorded in production Issue #103, including:
- PowerShell 5.1 JSON empty-array cardinality;
- quote-bearing `jq` corruption;
- empty-array mandatory parameter binding;
- operators such as `-split` parsed as parameters after command calls;
- `.Trim()` corrupting whitespace-significant machine data;
- `$Variable:` interpolation parser failures;
- compound native argv expression splitting;
- verifier schema assumptions that disagreed with the producer.

Draft PR #108 adds a larger agent prompt/runner rulebook and is still open as of this checkpoint.

### Historical context policy

Raw historical transcripts were explicitly excluded from live scene-path and checkout-root policy interpretation while `CURRENT_CONTEXT.md` remains live-enforced documentation.

### Private live repository and bootstrap

The validated Gauntlet fixture was published privately.

Exactly four durable resume fixtures were bootstrapped:
- NSC-601
- NSC-602
- NSC-603
- NSC-604

The bootstrap itself exposed production #104 (GitHub read-after-write lag).

### Production #104

The initial bounded verification repair was implemented and live-exercised.

A later repo-wide audit found remaining one-shot mutation/readback callers. Codex repaired them in PR #109 and Claude independently reviewed the exact PR head as `READY_TO_MERGE`.

Production PR #109 merged at:

```text
0596dea8258718208a968cb36c18a552d2366441
```

This is the current verified production **code checkpoint** at this handoff.

Production Issue #104 remains open only as a live-acceptance gate until the repaired code is exercised through the private Gauntlet lifecycle.

### Synthetic implementation adapter

Private Gauntlet PR #5 added synthetic implementation/repair support while keeping production TaskReviewAgent and TaskGraph semantics unchanged.

### Synthetic delivery evidence — Job 1

Private PR #6 added the evidence/conformance mechanism.

The central proof:

```text
real task not_delivered
dependent blocked
→ synthetic validation + legitimate DELIVERY evidence
→ unmodified TaskGraph derives conformant
→ existing dispatch logic says dependent is eligible
```

### Synthetic downstream lifecycle — Job 2

Private PR #7 added durable delivery-evidence / merge-closeout lifecycle support.

Claude independently returned `READY_TO_MERGE`. Three medium defensive findings were then rolled into the next combined hardening pass rather than causing a second huge validation cycle.

### #104 resync + downstream hardening

Private PR #8 merged production #104 behavior plus the downstream hardenings.

Private merge commit:

```text
63758af42be1efcc110b525ddb157b0be81f4560
```

### One-worker evidence-head proof

A real generic worker selected NSC-601 in `merge_closeout`.

The worker:
- used real production generic dispatch;
- selected existing advanced work before fresh work;
- used the real durable Issue state;
- reached the synthetic downstream adapter;
- created/recognized the exact evidence commit;
- advanced the durable Issue head from candidate to evidence;
- opened PR #9;
- did **not** merge;
- returned at a deliberate durable boundary;
- left zero Stage-1 claim refs according to the runner.

Result:

```text
task:            NSC-601
candidate:       2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
evidence:        33af4366a06e81e9e3c8751cbeb834722ebe183b
private PR:      #9
Issue state:     agent_ready
Issue phase:     merge_closeout
state version:   13
durable head:    33af4366a06e81e9e3c8751cbeb834722ebe183b
human handoff:   2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
merge attempted: no
```

This is meaningful live #104 evidence: the evidence-head checkpoint and bounded durable verification succeeded.

### Private CI compatibility repair

PR #9's Core CI exposed a Gauntlet compatibility problem: `task_review_agent_smoke_test.py` contains a production-only `NSC-050` real-repository observation fixture.

Private PR #10 changed only:

```text
.github/workflows/task-review-agent-deterministic.yml
```

It preserves full behavior when `Tasks/NSC-050.yaml` exists, but in the private Gauntlet runs the five compatible smoke tests and skips only that production-only observation fixture.

PR #10 merged at:

```text
3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
```

This is the current verified private Gauntlet `main` at this handoff.

## Current verified live state

### Production

```text
repository:                cathode26/NoSafeCircle
production code checkpoint: 0596dea8258718208a968cb36c18a552d2366441
Stage 5 implementation:    NOT STARTED
```

### Private live Gauntlet

```text
repository: cathode26/TaskOrchestratorGauntletLive-20260831
main:       3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
```

### Managed Issues

Exactly four managed live Issues remain:

```text
#1 NSC-601  agent_ready            merge_closeout
#2 NSC-602  agent_working          implementation
#3 NSC-603  human_action_required  unity_runtime_validation
#4 NSC-604  agent_ready            repair
```

For #1, GitHub currently reports:

```text
branch:               gauntlet/nsc-601-submission-1
durable head:         33af4366a06e81e9e3c8751cbeb834722ebe183b
human_handoff_commit: 2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
human_result:         pass
state_version:        13
```

### Private PR #9

GitHub currently reports:

```text
PR:        #9
state:     OPEN
mergeable: yes
base:      main
base SHA:  3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
head:      gauntlet/nsc-601-submission-1
head SHA:  33af4366a06e81e9e3c8751cbeb834722ebe183b
changed files: 4
```

## Current blocker: PR #9 exact-head CI is still red

This is the most important continuation fact.

After PR #10 merged, PR #9 was refreshed/reopened and new workflow runs were created on exact evidence head:

```text
33af4366a06e81e9e3c8751cbeb834722ebe183b
```

The latest visible results include:

```text
Canonical Checkout Root Policy:             SUCCESS
D1B.2 Core Deterministic Validation:         SUCCESS
TaskReviewAgent Deterministic Validation:    FAILURE
```

The latest failing deterministic run was:

```text
run id: 33433789299
job:    windows-smoke
```

Its log proves the workflow executed:

```text
python Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py
```

and then failed because:

```text
Tasks/NSC-050.yaml
```

does not exist in the synthetic Gauntlet.

Important contradiction:

- private `main` at `3198c5...` contains the repaired guarded workflow;
- the fresh PR #9 run on immutable head `33af4366...` still executed the old unguarded workflow behavior.

Therefore **do not treat “base fixed + close/reopen” as sufficient**. It has already been tried and the new run is still red.

The next problem is specifically how to establish a valid required exact-head CI authority for the immutable evidence commit while using the repaired Gauntlet-compatible policy.

## Validation / evidence completed

The session ran or reviewed substantial coverage, including:
- Stage 1 atomic claims;
- Stage 2 deterministic planning;
- Stage 3 fresh dispatch;
- Stage 4 contention retry;
- Stage 4.1 repository binding;
- live GitHub Issue bootstrap;
- live durable lease acquisition;
- bounded read-after-write verification;
- synthetic Fibonacci/dice/hybrid execution;
- real synthetic DELIVERY evidence;
- unmodified TaskGraph conformance;
- dependent-task unlock;
- downstream crash/resume tests;
- Windows long-path-safe temporary Git clones;
- private CI compatibility smoke;
- Claude adversarial reviews of Stage 5 design, Job 2, and production #104.

Do not rerun the entire history merely to regain confidence. Run only tests required by the next changed boundary.

## Unresolved issues / blockers

1. **PR #9 exact-head deterministic CI remains red.**
2. Determine the correct GitHub Actions/check-authority mechanism for immutable evidence heads whose branch contains an older workflow definition.
3. Production #104 should remain open until the NSC-601 downstream lifecycle completes live with repaired production semantics.
4. Production #106 remains the historical architecture record for why the Gauntlet uses a synthetic executor. Close only after acceptance demonstrates the reviewed alternative boundary.
5. Production #103 remains a command-governance backlog.
6. Production PR #108 is still a draft documentation follow-up.
7. No ten-worker wave until the single-task lifecycle is genuinely complete.
8. Stage 5 implementation remains frozen until Gauntlet acceptance.

## Next action

> Re-read private PR #9, its exact-head workflow runs, private `main`, Issue #1, and live claim refs. Diagnose how to obtain a green required `TaskReviewAgent Deterministic Validation` check for immutable evidence head `33af4366...` using the repaired private-main CI policy. Do not change the evidence commit, merge PR #9, or start another worker until that check is valid.

After that check is legitimately green:

1. resume exactly one NSC-601 `merge_closeout` worker;
2. prove PR merge/integration;
3. prove unmodified TaskGraph conformance;
4. prove Issue #1 completes;
5. prove dependent work unlocks;
6. prove claims return to zero;
7. close #104 after live acceptance;
8. perform a small contention wave;
9. then launch the 10-worker / 85-task Gauntlet.

## Do not repeat

- Do not rebuild the 85-task fixture.
- Do not recreate the four bootstrap Issues.
- Do not rerun bootstrap.
- Do not widen production Unity repository scope to `Gauntlet/`.
- Do not change NSC-601's tested candidate or evidence SHA merely to obtain CI.
- Do not merge PR #9 while required CI is red.
- Do not launch another worker while PR #9 is at this unresolved CI boundary.
- Do not implement Stage 5 yet.
- Do not assume a failed runner means its prior durable mutation failed; observe current state first.
- Do not use old giant recovery scripts whose pinned SHAs predate this handoff.

## Historical/raw source

`raw/imported-2026-08-31-Build-Task-Orchestrator3.txt`

## Authority reminder

This handoff is historical context. Before mutating either repository, verify current Git, GitHub Issue/PR, Actions, remote-ref/claims, and TaskGraph state. Current deterministic state wins if it disagrees with this file.
