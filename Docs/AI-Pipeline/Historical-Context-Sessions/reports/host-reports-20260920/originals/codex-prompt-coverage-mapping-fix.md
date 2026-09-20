# Codex: fix real-task decomposition failures on the coverage-mapping rules

Prepared by the coordinating session on 2026-09-13 at about 23:55 UTC, for Vincent to send to Codex. Fresh agent.

## Context

The NSC-1165 decomposition reliability stack is complete. The final integration head is `4fd54b8ce167bd87897926384839b03378e86232` on branch `throughput/decomposition-final-integration`, worktree `C:\nscrev\final-integration`. It covers all six of your mid-review blockers.

We then ran decompositions only (no apply) on the five real game tasks that need splitting: NSC-014, NSC-015, NSC-025, NSC-033 and NSC-035. They ran on a combined tree: our pipeline code at `9dee4a6` plus the game's `Tasks/`, GDD and TaskGraph state at `886bb81`. That tree is commit `80a7537`, `C:\nscrev\realdecomp-run2-src`. Setup details: `C:\nscrev\reports\run2-real-task-decomposition-feasibility.md`.

The three-call design works live: synthetic NSC-1165 split through the round-3 revision review, and NSC-1160 split in two calls. The real tasks, however, fail before they ever reach the reviewer.

## Failure evidence

Run artifacts are under `C:\nscrev\realdecomp-Checkouts\.assistant-control\decomposition-runs\run2-<task>-80a7537befae\`. The author is claude-sonnet-5.

| Task | Result | Round 1 (author) | Bounded author correction |
|---|---|---|---|
| NSC-025 | `rejected`, no Codex call | "Distinct parent obligations must have injective child mappings; door-state-enemy-passability-interface/acceptance_criteria/AC-001 is reused by acceptance_criteria/AC-003 and acceptance_criteria/AC-004." | "Parent completion_gates/VAL-001 must map to child completion_gates entries, not downstream_integration_obligations." |
| NSC-035 | `rejected`, no Codex call | "Parent acceptance_criteria/AC-002 must map to child acceptance_criteria entries, not downstream_integration_obligations." | "Distinct parent obligations must have injective child mappings; victory-suspend-coordinator/acceptance_criteria/AC-001 is reused by acceptance_criteria/AC-001 and acceptance_criteria/AC-002." |
| NSC-014 | `rejected`, no Codex call | "Distinct parent obligations must have injective child mappings; enemy-doorway-passability-pursuit-continuity/acceptance_criteria/AC-001 is reused by acceptance_criteria/AC-002 and acceptance_criteria/AC-006." | "Parent acceptance_criteria/AC-008 must map to child acceptance_criteria entries, not completion_gates." |
| NSC-015 | `rejected` after the Codex review | Author passed validation | Not used. The **Codex round-2 reviewer** returned `revise` with 4 legitimate blocking findings: duplicated reset validation, a missing Player Health dependency, a risk of duplicating NSC-077's Melee Enemy prefab, and locomotion owned by an attack component. **Its revised candidate then failed:** "Distinct parent obligations must have injective child mappings; melee-enemy-prefab-assembly/acceptance_criteria/AC-001 is reused by acceptance_criteria/AC-001 and acceptance_criteria/AC-003." |
| NSC-033 | stopped by Vincent during the Codex round-2 review (to save usage) | Rejected: floor-restart-orchestrator-reset-invocation/acceptance_criteria/AC-002 is claimed by parent AC-001 and AC-002 (injective) | Passed validation, so the correction can work |

Final tally at 23:53 UTC:
- **7 of 9 drafts broke one of the two unstated rules.** Across all five tasks there were 9 drafts: 5 author drafts, 3 corrections and 1 reviewer revision.
- **Both providers broke them:** the Claude author and the Codex reviewer.
- **One draft each, no more:** each failing draft broke exactly one rule, and 3 of the 4 corrections that failed broke the other rule.
- **No real task split.** Four were rejected on these rules alone; NSC-033 was stopped.
- **The review circuit did its job on NSC-015.** Codex's findings were substantive.
- **Gap:** a reviewer revision that fails deterministic validation ends the run `rejected`, because reviewer revisions get no correction. Stating the rules to the reviewer is therefore as important as stating them to the author.

I scanned the raw structured outputs (`rounds/<n>/agent_runtime/*/result.json`). Five real-task drafts have been scanned so far:

- **NSC-015** round 1 is clean.
- **Each of the other four has exactly one violation** of one of the two rules below.
- **Each correction fixed the reported violation and introduced a violation of the other rule.** This is not a pile of errors hidden behind first-error reporting. The author does not know the rules.

## Root cause

- **Two rules are enforced but never stated.** They live in `Pipeline/TaskDecomposition/policy.py:209-224` and apply only to parent `acceptance_criteria` and `completion_gates` entries:
  1. **Same kind.** A child target must be in the same collection as the parent entry: parent AC maps to child `acceptance_criteria`, and parent VAL maps to child `completion_gates`. Parent `downstream_integration_obligations` entries are exempt.
  2. **Injective.** A child AC/VAL entry may be claimed by at most one distinct parent AC/VAL entry.
- **The author prompt does not mention either rule.** `Pipeline/TaskDecomposition/prompts.py:162-174` says every parent AC/VAL/INT entry needs exactly one coverage record, and gives the target format and an existence-only self-check. Synthetic Gauntlet parents have one or two ACs, so the gap never showed. Real tasks have several overlapping ACs and VALs, and integration-flavoured work, so the author merges two parent ACs into one child AC, or maps an AC or VAL onto a child INT entry.
- **The validator stops at the first violation.** Validation raises on the first one, and the single bounded correction sees only that message, without the rule it belongs to.

## Proposed fix

Keep the bounded author → independent reviewer → one-revision design and its three-call cap. Do not relax, exempt or reinterpret either mapping rule.

1. **State both rules in the author guidance** (`prompts.py`, the coverage section around lines 162-174).
   - **Same kind:** for each parent `acceptance_criteria` or `completion_gates` entry, every child target must be in that same collection. Only parent `downstream_integration_obligations` entries may target other collections.
   - **One parent per child entry:** a child AC or VAL entry may be the target of at most one parent AC/VAL entry. If two parent entries need the same child work, give the child one entry per parent entry (for example child AC-001 for parent AC-003 and child AC-002 for parent AC-004), even when the wording overlaps.
   - **Extended self-check:** build a map from each child target to the parent entry that claims it. Split or retarget before returning if any child AC/VAL entry is claimed twice, or any parent AC/VAL entry targets a different collection.
   - **Same text everywhere:** the bounded author-correction prompt and the reviewer prompt must carry the same text. They already carry the shared child-evidence rules block the same way.
2. **Report every coverage violation at once** (`policy.py`).
   - Collect all coverage violations for a candidate (unknown child or entry, cross-kind, non-injective, missing coverage) and raise one `DecompositionPolicyError` listing all of them in deterministic order.
   - The rule semantics must stay exactly the same.
   - Make sure the author-correction request shows the full list and the rule text (see `round_robin_decomposition.py` around line 1511, where the correction is requested).
   - Audit tests and consumers that match exact error strings.
3. **Optional, your call.** Let the author run the deterministic candidate validator inside its own session before returning. This would be a check in the same provider call, not an extra call. The final deterministic validation stays authoritative. It may be out of scope; say whether you want it now or as a follow-up.

## Tests (failing-before at `4fd54b8`)

- **Prompt tests:** the author, correction and reviewer prompts render both rules and the extended self-check.
- **Validator tests:** one candidate with several violations (cross-kind plus injective plus unknown entry) gets every violation in one message. Single-violation messages stay precise. Parent INT entries remain exempt from both rules.
- **Regression tests:** synthetic reproductions of the four observed patterns: two parent ACs sharing one child AC; parent VAL mapped to child INT; parent AC mapped to child INT; a correction that fixes one rule and breaks the other. Do not commit real game task content. Reading the retained artifacts above (read-only) to model the fixtures is fine.
- **Existing suites:** the TaskDecomposition suites (round_robin, author_correction, live_decomposition, revision_review, child_gdd_evidence, guidance, contracts, pooled) and AssistantControl `test_decomposition`, `test_decomposition_whole_stack`. Report exact counts.

## Live verification (after review; Vincent approves the spend)

- **Rebuild the combined tree on the fix:** `C:\Python313\python.exe C:\nscrev\realdecomp-tools\rebuild_combined.py --code <fix sha>`.
- **Re-run the rejected tasks** (NSC-025, NSC-035, and NSC-033 if it is rejected) with a new `--checkout-root`, because there is one record per task per root. The commands are in the feasibility report.
- **Success criterion:** each real task reaches Codex review and ends `review_ready` or a reasoned `needs_human`, never `rejected` on these mapping rules.

## Constraints and delivery

- **Work location:** a new branch from `4fd54b8` in a new worktree under `C:\nscrev`.
- **Do not write under `C:\NSC`.** The game repository `C:\NSC\NSC\NoSafeCircle` is read-only.
- **Do not:** push, merge, run provider or Docker commands, or edit CI or docs.
- **Windows:** CRLF via autocrlf, never `sed -i`, and `git diff --check` must be clean.
- **Some local TaskReviewAgent suites write temp dirs under `C:\NSC`.** Set `NSC_DECOMP_PENDING_TEMP`, `NSC_REVISION_RACE_TEMP` and `NSC_DECOMP_WAKE_TEMP` to a scratch dir, and skip `local_candidate_source_integration_test`, `local_source_wait_completion_test` and `immutable_crew_manifest_test`.
- **Report:**
  - commit SHA and parent;
  - files changed;
  - how each fix is enforced (file:line);
  - failing-before/passing-after table;
  - suite counts;
  - residual risks;
  - whether you did optional item 3.
