# total_provider_calls (0419f853): coordinator verification (2026-09-14)

**Status:**
- Verified locally by the coordinator.
- Not yet reviewed by Astra, and not on canonical main.
- **Recommendation:** leave it out of the current guarded push unless Codex and Astra review it first.

## 1. Commit

- **Commit:** `0419f853eb5833b350fd33a5380de9b6ee4d3180`, parent `3a0645350f522e653d04c6ec6b04291967ea1e8b`, on branch `codex/total-provider-calls-20260914` (worktree `C:\nscrev\total-provider-calls-fix`).
- **Identity:** author and committer `No Safe Circle Call Reporting <call-reporting@nosafecircle.invalid>`, with the `Co-Authored-By: Claude Opus 5` trailer.
- **Size:** 11 files, +406/−40.
- **Hygiene:** `git diff --check` is clean and the worktree is clean. The guidance files are untouched: `prompts.py`, `review_prompts.py`, `README.md` and the candidate-wide test.
- **Merges:** clean with the guidance line.
  - `git merge-tree --write-tree` exits 0 against `e70b2fe4`, and against `c6f7981a` (tree `bbe73b6143fa7012fae564cf65463c0b96d6990d`).
  - No file is touched by both sides since `3a06453`.

## 2. What it does (per the developer's report; verified by the tests below, not by a line-by-line review)

- **Producer:** `total_provider_calls`, the physical provider-call count, is written to the D1B.2 run result and to the `run_completed` event. `calls_used`, `author_corrections_used` and `revision_reviews_used` keep their meaning and values.
- **AssistantControl:** the review-ready proof, `needs_human` facts, and `inspect`/`apply` all handle the new field the same way.
  - An absent key is accepted, which covers legacy runs.
  - A present key must be an exact integer (not a bool) equal to `calls_used + author_corrections_used + revision_reviews_used`, otherwise the record is refused.
- **D1C:**
  - The same integrity rule applies, using the existing reason `bounded_call_accounting_invalid`; no new reason code was added.
  - The binder stays pure.
- **Golden fixtures:** the run result now has 29 keys. The GDDRAG A/B manifest also carries the total.

## 3. Coordinator test run

Script: `C:\nscrev\final-verify\tpc\verify_tpc.sh`. Logs are in `C:\nscrev\final-verify\tpc\`.

**Failing-before:** the 7 committed test files run against untouched `3a06453` in a detached worktree, since removed.

| Suite | Result at `3a06453` |
|---|---|
| revision_review_smoke_test | FAIL (21 of 22 cases) |
| revision_review_fixtures_smoke_test | PASS (12). Expected: it compares fixtures with the contract only. |
| AssistantControl test_decomposition | FAILED, 63 tests: 12 failures, 3 errors |
| AssistantControl test_decomposition_needs_human | FAILED, 44 tests: 26 failures, 13 errors |
| AssistantControl test_decomposition_revision_review_integration | FAILED, 9 tests: 6 errors |
| D1C decomposition_authorization_revision_review_smoke_test | FAILED, 67 tests: 20 failures |

**Passing-after, on `0419f853`:**

| Suite | Result |
|---|---|
| revision_review_smoke_test | PASS (22 cases) |
| revision_review_fixtures_smoke_test | PASS (12) |
| round_robin_decomposition_smoke_test | PASS |
| author_correction_smoke_test | PASS |
| AssistantControl test_decomposition | Ran 63, OK |
| AssistantControl test_decomposition_needs_human | Ran 44, OK |
| AssistantControl test_decomposition_revision_review_integration | Ran 9, OK |
| AssistantControl test_decomposition_whole_stack | Ran 16, OK |
| D1C decomposition_authorization_smoke_test | PASS (59) |
| D1C decomposition_authorization_revision_review_smoke_test | Ran 67, OK |

These counts match the developer's reported results.

## 4. Residual risks (developer's report)

1. **Mixed versions:** newer `inspect` refuses a `needs_human` record written by older AssistantControl code over a run from the newer producer. This mirrors the existing `revision_reviews_used` precedent.
2. **Missing counters:** an absent counter reads as 0 next to a present total. No producer writes that shape.
3. **Internal-error branch:** it can write a total that disagrees with the counters. Such a run is always `rejected` and is refused anyway.
4. **Not surfaced everywhere:** triage and the viewers don't show the total, and the manifest line for the GDDRAG A/B runner has no committed test.

## 5. Requested

- **Review:** Codex and Astra review before carrying it into main.
- **Research tree:** decide whether the next research tree should include it. The coordinator can build the code commit as `c6f7981a` plus `0419f853`, which merges cleanly, together with a local test run.
