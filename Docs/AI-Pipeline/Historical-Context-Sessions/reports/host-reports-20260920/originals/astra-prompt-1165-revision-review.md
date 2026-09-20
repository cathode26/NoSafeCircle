# Astra: please concur or correct — why NSC-1165 cannot split, and the proposed fix

Fresh agent, read-only review. Do not start, stop, clear or relaunch anything in the Gauntlet projects below, and do not modify any repository. If you want a mutation, name the exact command and why.

## What I need from you

1. Confirm or refute the diagnosis below, from the records rather than from my account.
2. Review the safety of the proposed change, a bounded third review call, before it is merged.
3. Tell us whether a faster or complementary fix is better for the Gauntlet symptom.

## What happened: two runs, identical shape

NSC-1165 is a synthetic Gauntlet parent whose split should be trivial: two children, each defining a constant value. Its D1B.2 decomposition stopped for a person in both consecutive runs.

| | First run (old code) | Fresh run (fixed code) |
|---|---|---|
| Round 1, `task_decomposer`, claude-code / claude-sonnet-5 | `candidate_valid` | `candidate_valid` |
| Round 2, `decomposition_reviewer`, openai-codex / gpt-5.6-sol | verdict `revise`, `revised_candidate_valid` | verdict `revise`, `revised_candidate_valid` |
| Reviewer's finding | `round-02-misstated-edit-mode-proof`: children's completion gates claim the Edit Mode tests prove a public static class; the tests only check the constant `Value` | `round-02-fabricated-gauntlet-gdd-evidence`: both children cite `provenance.origin human_approved_synthetic_gauntlet` as GDD evidence, but the parent records `assistant_control_local_gauntlet_replay` and the context has no GDD evidence |
| Calls used / max | 2 / 2 | 2 / 2 |
| Author corrections used | 0 | 0 |
| Outcome | `needs_human`, mislabelled as a failed job by the old controller | `needs_human`, recorded correctly as waiting for a person |

In the same fresh run, NSC-1160 and NSC-1166 split automatically: round 2 returned verdict `pass` (`independent_pass`), the run became `review_ready` with codex as the independent approver, and the controller applied it.

## Diagnosis

- **The stop is the call budget, not the split.** With `max_calls` 2, round 1 authors and round 2 reviews. When round 2 revises instead of passing, the budget is spent and the reviser may not approve its own revision, so the run ends `needs_human` with the rejection reason "call limit ended immediately after a revision; the latest author may not approve its own candidate" (`Pipeline/TaskDecomposition/round_robin_decomposition.py` line 1092).
- **The author-correction round cannot help.** `correction_eligible` (line 1115) requires round 1's candidate to have failed deterministic validation. NSC-1165's round 1 passed both times.
- **graph_delta is not involved.** Both revised candidates passed deterministic validation and carry graph plan ids (`GDP-57f5cb46...` and `GDP-42c9b3ce...`).
- **The findings are real provider-output problems.** Hypothesis, not proven: for synthetic Gauntlet tasks there is no design document, yet the child contract carries evidence and completion-gate fields, so the author fills them with claims the context does not support, and the reviewer correctly rewrites them.
- **The classification fix already works.** With `eb3beb7`, the fresh run recorded the stop honestly: ticket `completed` with `result_status` `needs_human`, record `needs_human`, viewer "Task Needs You", and the Source lane released so other tasks integrated immediately.

## Proposed change (Vincent's decision)

Vincent's position is that a split should just happen when two independent providers agree, and a person should only be asked when they still disagree. The earlier patch recommendation deferred a third decomposition call and said to optimise the review circuit separately; this is that separate change.

- **Trigger, all required:** round 2 is the reviewer round; its verdict is `revise`; the revised candidate passed deterministic validation; the provider call succeeded; Source did not move; nothing else was rejected; no revision review used yet.
- **Round 3:** a `decomposition_reviewer` call by the provider that did not author the latest candidate (for NSC-1165, claude), reviewing exactly the revised candidate, bound by its version and sha256, with the same review contract, validation and Source-identity checks as round 2.
- **Outcome:** `pass` makes the run `review_ready` exactly like a round-2 pass, with the round-3 provider as independent approver, and the controller applies it automatically. `revise`, `reject` or any failure ends `needs_human` or `rejected` with an explicit reason. Never a fourth call.
- **Recording:** `revision_reviews_used` (0 or 1), outside `max_calls`, mirroring `author_corrections_used`, so `max_calls` 2 and existing `calls_used` checks stay meaningful. Every consumer that authenticates run results must accept exactly this shape and nothing looser: TaskDecomposition contracts, AssistantControl `decomposition.py` proofs, the D1C apply authority if it checks review evidence, and decomposition replay if it validates rounds.
- **Scope:** all decompositions, real game tasks included. No Gauntlet-only auto-approval.
- **Status:** being implemented on branch `throughput/decomposition-revision-review` from `ade5bca` in `C:\nscrev\revision-review-fix`; not yet committed. The coordinating session will verify it with failing-before evidence before anything is merged.

## Alternatives to weigh

- **A. Author guidance for Gauntlet children.** Tell the decomposer exactly what synthetic Gauntlet children may cite in evidence and completion gates. If the hypothesis is right, the reviewer passes on call two and no circuit change is needed for the Gauntlet. Faster, but unproven, and it does not help real tasks whose reviewer legitimately revises.
- **B. The bounded third call above.** General, keeps independent approval, costs one extra provider call only when a reviewer revises.
- **C. Both.**

## Questions

1. Do you concur that the call budget, and not graph_delta, validation or the correction round, is why NSC-1165 cannot split?
2. Is a single round-3 review of the reviser's candidate by the other provider acceptable under D1B.2 independence, given exact binding to the revised candidate's version and sha256?
3. Should pooled-session runs be excluded from round 3, as they are from author correction?
4. Is recording `revision_reviews_used` outside `max_calls` sound, or should `calls_used`/`max_calls` change instead?
5. Is alternative A the better or faster fix for the Gauntlet, and should it be done instead of B, before B, or alongside it?
6. Any path to a trustworthy split for NSC-1165 today that does not weaken the independence rule?

## Evidence (read-only)

- First run: `C:\NSC\GauntletFresh1160-Reviewed-Standalone-Checkouts\.assistant-control\decomposition-runs\assistant-nsc-1165-decompose-c7cb184da82b\decomposition_run_result.json` and its `rounds\` folder.
- Fresh run: `C:\NSC\GauntletFresh1160-FixesRun-20260913-Checkouts\.assistant-control\decomposition-runs\assistant-nsc-1165-decompose-4f467687fd31\decomposition_run_result.json` and its `rounds\` folder.
- Normal splits for comparison, fresh run: `assistant-nsc-1160-decompose-5ff210375b4f` and `assistant-nsc-1166-decompose-3bde2bc6abfb` in the same `decomposition-runs` folder.
- Parent contract: `C:\NSC\GauntletFresh1160-FixesRun-20260913\Tasks\NSC-1165.yaml` (provenance origin `assistant_control_local_gauntlet_replay`).
- Code: `Pipeline/TaskDecomposition/round_robin_decomposition.py` lines 1092 and 1115; `Pipeline/TaskDecomposition/contracts.py` (`gdd_evidence`); `Pipeline/AssistantControl/decomposition.py` (`_review_ready_proof` expects `calls_used` 2).
- Verification record for the two fixes already made: `C:\nscrev\reports\fixes-1163-1165-verification.md`.

## Output I want

A verdict on each question, marking what you reproduced from records versus reasoned, and a recommendation among A, B and C with the safety conditions you require.
