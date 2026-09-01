# Session: PR #9 Exact-Head CI Recovered

Date: 2026-08-31  
Session/topic: Live Gauntlet NSC-601 merge-closeout CI authority

## Goal

Recover a legitimate green exact-head CI authority for private Gauntlet PR #9 without changing the immutable NSC-601 evidence commit.

## Starting state

```text
production code checkpoint:
0596dea8258718208a968cb36c18a552d2366441

private Gauntlet main:
3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5

PR #9 head / evidence:
33af4366a06e81e9e3c8751cbeb834722ebe183b

NSC-601 durable state:
agent_ready / merge_closeout / state_version 13

human-tested candidate:
2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f
```

The latest TaskReviewAgent Deterministic Validation visible at the start was run `33433789299`, which failed because the immutable evidence head's original workflow executed the production-only `Tasks/NSC-050.yaml` smoke fixture.

Private PR #10 had already repaired the Gauntlet `main` workflow to guard that fixture when it is absent.

## Diagnosis

The immutable evidence commit itself still contains the old workflow file. However, GitHub `pull_request` workflows are evaluated through the PR merge-ref context rather than by simply reading the head tree in isolation.

The current PR #9 synthetic merge commit was inspected directly and was proven to contain the repaired PR #10 workflow. The previous reopen had nevertheless produced a run using the older behavior, indicating the run was created before the merge-ref refresh had settled.

A second close/reopen was therefore performed only after proving the settled merge ref contained the repaired workflow. This did not change the PR head SHA.

GitHub regenerated PR #9's merge commit as:

```text
16f17b119a4c8deeef37e507911e851e17941e7c
```

That merge commit contains the guarded `NSC-050` workflow branch.

## Validation / evidence

The reopen created new exact-head runs attached to unchanged evidence SHA:

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

The formerly failing TaskReviewAgent step:

```text
Run deterministic TaskReviewAgent smoke tests
```

completed successfully under run `33441319866`, and every remaining Stage 1-4/Core/compile/whitespace step in that job also completed successfully.

Older failures remain attached to the commit as historical check runs. The committed `pull_request_check_authority.py` intentionally groups logical checks and selects the newest unambiguous result, so the new successful run supersedes the old failure for downstream authority.

## Ending state

```text
private PR #9: OPEN / mergeable
base: main
base SHA: 3198c5f2bdd2261a7d3a8842b3e1410c4a1a4ec5
head branch: gauntlet/nsc-601-submission-1
head SHA: 33af4366a06e81e9e3c8751cbeb834722ebe183b

newest required exact-head CI: GREEN

NSC-601 Issue #1:
agent_ready / merge_closeout
human_result: pass
head_commit: 33af4366a06e81e9e3c8751cbeb834722ebe183b
human_handoff_commit: 2cf3759aaccb8a6b9fdc76dccbcefcf13e4e349f

worker launched after CI recovery: NO
PR #9 merge attempted after CI recovery: NO
```

## Next action

Run exactly one synchronous Gauntlet synthetic worker from the clean private `main` controller.

Before mutation, prove the read-only planner selects:

```text
resume_existing
NSC-601
Issue #1
merge_closeout
33af4366a06e81e9e3c8751cbeb834722ebe183b
```

Then let the worker itself:

```text
acquire/resume durable closeout authority
→ inspect newest exact-head checks
→ merge PR #9 with exact-head protection
→ verify private main contains the evidence
→ verify unmodified TaskGraph derives NSC-601 conformant
→ complete Issue #1
→ release all Stage-1 claims
```

Issues #2-#4 must remain unchanged.

## Do not repeat

- Do not modify evidence commit `33af4366...`.
- Do not manually merge PR #9 outside the worker acceptance proof.
- Do not launch a second worker or worker wave.
- Do not recreate any bootstrap Issue or branch.
- Do not rerun bootstrap.
- Do not reopen PR #9 again merely to reproduce the successful CI result; the exact-head green runs already exist.
- Do not implement Stage 5 yet.

## Historical/raw source

The broader session is preserved in:

`raw/imported-2026-08-31-Build-Task-Orchestrator3.txt`

The immediately preceding detailed handoff is:

`2026-08-31-live-gauntlet-evidence-checkpoint.md`

## Authority reminder

This handoff records the verified state at this boundary. Re-read current GitHub PR/Issue/check state and Git refs before any later mutation.
