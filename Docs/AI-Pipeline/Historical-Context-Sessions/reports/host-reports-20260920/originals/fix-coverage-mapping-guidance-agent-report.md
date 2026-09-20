# Coverage-mapping guidance and aggregation fix: developer report

Astra gave GO on this plan at base `4fd54b8`. The report was received about 00:50 UTC on 2026-09-14 and is recorded here in substance. The coordinating session reviewed the diff against the constraints; independent test runs are recorded below once they finish.

## Commit

- **SHA:** `616ca980f642a99c37d23655c27c062015505e91`, parent `4fd54b8ce167bd87897926384839b03378e86232`.
- **Where:** branch `codex/coverage-mapping-guidance-20260913`, worktree `C:\nscrev\coverage-mapping-guidance-fix`. No upstream; nothing pushed.
- **Identity:** author and committer are both `No Safe Circle Coverage Mapping Fix <coverage-mapping-fix@nosafecircle.invalid>`. The message ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Hygiene:** all four files are i/lf w/crlf, and `git diff --check` is clean.

| File | Change |
|---|---|
| `Pipeline/TaskDecomposition/policy.py` | +41/-14 |
| `Pipeline/TaskDecomposition/prompts.py` | +45 |
| `Pipeline/TaskDecomposition/review_prompts.py` | +11/-1 |
| `Pipeline/TaskDecomposition/tests/coverage_mapping_guidance_smoke_test.py` (new) | +867 |

## How Astra's constraints are enforced (line numbers at 616ca98)

- **Same-kind rule and ownership key unchanged** (`policy.py:229-245`). The rule still covers parent AC/VAL only, with key `(local_key, child_entry_type, child_entry_id)`.
  - **Parent INT:** never enters the ownership block, so it neither claims nor conflicts.
  - **Integration-flavoured parent VAL:** no exemption; still same-kind.
- **Aggregated defects**, appended to `coverage_defects`:
  - unknown child (228)
  - cross-kind (231)
  - non-injective (241)
  - unknown child entry (250)
  - missing parent coverage (259; IDs still sorted, 258)
- **Unchanged immediate raises:** early structural and disposition checks (197-224). Later checks, including needs_artifact/needs_human and untraced child entries, still run only after the aggregate raise.
- **Unknown child guarded:** recorded, then ownership is skipped (`elif child is not None`, 235) and the entry-ID check is skipped (`continue`, 247-248).
- **First owner retained:** `setdefault` (239). A later distinct claimant's defect names the first owner.
- **Order:** record order, then target order; missing coverage last. One `DecompositionPolicyError` is raised (260-261).
- **Exact single-defect text:** `_coverage_defects_message` (`policy.py:45-46`) returns the individual text unchanged.
- **Multi-defect format:** one line, `Parent requirement coverage has N defects: (1) <text> (2) <text> ... (N) <text>`.
- **Shared guidance block:** `prompts.coverage_mapping_rules()` (`prompts.py:103-141`).
  - **Author prompt:** rendered under "Parent coverage mapping rules:" (147, 262-263).
  - **Correction prompt:** inherits it by embedding the author prompt (350).
  - **Reviewer prompt:** renders it explicitly (`review_prompts.py:10, 66, 140, 170-176`), with a replacement invariant saying a rejected replacement ends the run.
  - End markers are unchanged.
- **One exception, one rejection element:** `round_robin_decomposition.py` is unchanged.
  - The aggregate reaches the correction prompt verbatim through `initial_validation_failure` (1266-1269, 1425, 1517, 1536, 1561-1566, `prompts.py:358`).
  - A failed reviewer revision is still one string (1352-1355).
- **Decision for Astra:** a cross-kind target records its defect but never claims ownership (`policy.py:235`). This matches the reachable behaviour at base, where the cross-kind check raised before ownership was recorded, and it avoids false injective defects. It is pinned by the "parent AC mapped to child VAL" case.

## Failing-before at 4fd54b8, and after (developer)

The developer copied only the test file into a detached base worktree.

| Result | 4fd54b8 | 616ca98 |
|---|---|---|
| FAIL | 8 | 0 |
| PASS | 2 | 10 |

**Failing at base:**
- the author, correction and reviewer prompts each state the rules (3 tests);
- every defect reported in order (8 defects, first owner kept, missing IDs sorted);
- parent INT sharing in both orders, inside an aggregate;
- structural and disposition errors raised first;
- an invalid reviewer revision gives one reason and no extra calls;
- a stubbed correction carries the full aggregate within the limits (2/2/1/0).

**Passing at base (pins):**
- exact single-defect texts (7 cases);
- integration-flavoured VAL is still same-kind.

## Suites on the fix (developer, sequential)

All pass. Logs are in `C:\nscrev\test-temp\cmg-suite-logs`.

| Area | Suite | Result |
|---|---|---|
| TaskDecomposition | coverage_mapping_guidance | 10 |
| | revision_review | 21 |
| | child_gdd_evidence | 17 |
| | decomposition_evidence_guidance | 11 |
| | pooled_decomposition | 17 |
| | revision_review_fixtures | 12 |
| | round_robin, author_correction, live_decomposition, decomposition_contracts, review_contracts, round_invocation_id, context_builder | PASS |
| AssistantControl | test_decomposition | 62 OK |
| | test_decomposition_whole_stack | 16 OK |
| | revision_review_integration | 7 OK |
| TaskReviewAgent | decomposition_authorization | 59 |
| TaskGraph | graph_delta | PASS |
| TaskDecomposition (consume the reviewer prompt) | reviewer_replay, gdd_rag_review_context | PASS |

## Error-string audit (developer)

Nothing depends on first-error-only behaviour.

- **Single-defect substring tests** (text unchanged):
  - `round_robin_decomposition_smoke_test.py:397`
  - `author_correction_smoke_test.py:370`
  - `live_decomposition_smoke_test.py:312`
  - `revision_review_smoke_test.py:600`
  - `decomposition_contracts_smoke_test.py:394/400/403`
  - `graph_delta_smoke_test.py:348`
- **`revision_review_fixtures.py:117-120`** is a hand-built record, not validator output.
- **AssistantControl `decomposition.py:708-711`** requires exactly one initial rejection with the `initial candidate deterministic validation failed: ` prefix. This still holds, which is why the aggregate is one element.
- **D1C** catches `DecompositionPolicyError` by type only.

## Residual risks

1. **Not in CI.** The new suite is not in `d1b2-core-deterministic.yml` (CI edits were out of scope).
2. **Stale README advice.** `Pipeline/TaskDecomposition/README.md:425` still recommends mapping a parent obligation to the downstream integration entry, which contradicts the same-kind rule for parent AC/VAL (docs out of scope). There is also an existing limitation: a child INT entry can only be traced through a parent INT record.
3. **Live effect unproven.** Model compliance has not been tested live. Reviewer revisions still get no correction.
4. **Precedence change.** An early structural or disposition error in a later coverage record now wins over mapping defects collected from earlier records. No consumer depends on the old order.
5. **Unspecified-case decision.** Cross-kind targets never claiming ownership is the developer's reading of a case the brief did not cover (see above).
6. **Minor.** Identical defect texts are not de-duplicated, and each prompt grows by about 25-30 lines.
7. **Not done.** Optional item 3, an in-session self-validation tool.

## Coordinator's independent verification (about 01:08 UTC, 2026-09-14)

Script `C:\nscrev\final-verify\cmg\verify_cmg.sh`; logs and `summary.txt` are in the same folder.

- **Diff review:** the `policy.py`, `prompts.py` and `review_prompts.py` changes match each of Astra's constraints above.
- **Failing-before:** a fresh detached worktree at `4fd54b8`, with only the committed test file copied in: **8 FAIL, 2 PASS**, the same as the developer's result. The 8 fail on behaviour, not on missing names:
  - the header is missing from the author, correction and reviewer prompts;
  - only the first defect is reported;
  - INT sharing inside an aggregate;
  - early-error precedence;
  - the invalid-reviewer-revision aggregate;
  - the bounded-correction aggregate.

  The two passes are the pins: exact single-defect text, and integration-flavoured VAL. The worktree was removed afterwards.
- **Passing-after on `616ca98`:** coverage_mapping_guidance PASS (10 tests).
- **Key suites on `616ca98`, all exit 0:**

  | Suite | Result |
  |---|---|
  | decomposition_contracts | PASS |
  | round_robin_decomposition | PASS |
  | author_correction | PASS |
  | revision_review | PASS (21 cases) |
  | graph_delta | PASS |
  | AssistantControl test_decomposition_whole_stack | OK |

- **Worktree state:** the fix worktree is clean after the runs.

## Nothing live touched

- **`C:\NSC` untouched.** Nothing was written under it; tests used user temp. `RevisionRaceTmp`/`DecompPendingTmp` timestamps predate the runs, and none of the `C:\NSC`-writing suites ran.
- **No external systems.** No provider CLI, no Docker, no push, no merge.
- **Cleanup.** The temporary worktree `cmg-before` was removed and pruned.
