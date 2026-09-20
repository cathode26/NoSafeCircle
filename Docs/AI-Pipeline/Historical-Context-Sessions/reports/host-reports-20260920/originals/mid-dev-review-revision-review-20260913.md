# Mid-development review: NSC-1165 bounded revision review (snapshot at 21:05 UTC, 2026-09-13)

Prepared by the coordinating session for Codex, at Vincent's request. This is a snapshot of work in progress, taken without stopping the developers. It is not the final review request: work is still landing, and the coordinator's independent verification and the Issue #36 post come later.

## 1. What to review

- **Snapshot branch:** `review/revision-review-mid-20260913` = `ce9ce1373f120e3bae105d372f2016144d490878`. It is a local ref in the repository shared by the `C:\nscrev` worktrees, and it does not move.
- **Base:** `ade5bca50d452b276a32f31a7ad8baeb770b2404`, the already-reviewed NSC-1163/NSC-1165 fixes.
- **Size:** 5 commits, 15 files, +6824 / -215. About 4,900 of those added lines are tests and golden fixtures.
- **Order:** the commits are stacked in the order the AssistantControl developer cherry-picked them. The coordinator checked that every cherry-pick is patch-id identical to the original commit.

| # | Stacked SHA | Original SHA | Owner | Commit |
|---|---|---|---|---|
| C0 | `c1077e0be18e35281a747e44e666349aa0134349` | `f941857` | producer | TaskDecomposition: export revision-review constants and shared golden fixtures (inert) |
| A | `ac47d5ed596f3a6063c98a3f25c1cca099331153` | same | AssistantControl developer | AssistantControl: replay and authenticate the bounded revision-review round history |
| P1 | `f39abd6609db15ef321ed8471762e4155532f918` | `9e7116f` | producer | TaskDecomposition: bound one independent revision review of a last-call revision |
| D1C | `514dfb9e45829869392eab3d80503d0eb359134f` | `4dce423` | D1C developer | TaskReviewAgent: authorize exactly the bounded revision-review shape in D1C |
| G | `ce9ce1373f120e3bae105d372f2016144d490878` | `13618d8` | guidance developer | TaskDecomposition: guide child evidence and completion gates to claim only what the context proves |

Files changed, relative to `Pipeline/`:
- **AssistantControl:** `decomposition.py` (+649), `test_decomposition.py` (+646/-), `test_decomposition_needs_human.py` (+261).
- **TaskDecomposition:**
  - `round_robin_decomposition.py` (+355)
  - `prompts.py` (+66)
  - `review_prompts.py` (+15)
  - `tests/revision_review_fixtures.py` (+1463)
  - `tests/revision_review_fixtures_smoke_test.py` (+774)
  - `tests/revision_review_smoke_test.py` (+1067)
  - `tests/decomposition_evidence_guidance_smoke_test.py` (+553)
  - `tests/round_invocation_id_smoke_test.py` (+2)
- **TaskReviewAgent:** `decomposition_authorization.py` (+118), `local_decomposition_apply.py` (+6), `tests/decomposition_authorization_revision_review_smoke_test.py` (+706), `tests/local_decomposition_apply_revision_review_test.py` (+358).

## 2. Background and binding documents

- **The problem.** NSC-1165 stopped `needs_human` in two consecutive Gauntlet runs. Round 2's independent reviewer returned a valid `revise`, and the two-call budget left nobody independent to approve the revision.
- **The agreed fix (Astra).** Add one bounded round-3 review of the exact revised candidate by the other provider, plus better author guidance.
- **Astra's six required repairs:** `C:\nscrev\reports\astra-1165-revision-review-requirements.md`.
- **Binding design** (contract sections A-G, golden fixtures D1-D4, merge plan F, open questions G): `C:\nscrev\reports\revision-review-design.md`.
- **Developer reports:**
  - producer (C0 + P1): `C:\nscrev\reports\fix-1165-producer-agent-report.md`
  - D1C: `C:\nscrev\reports\fix-1165-d1c-consumer-agent-report.md`
  - guidance: `C:\nscrev\reports\fix-1165-author-guidance-agent-report.md`
  - AssistantControl: not written yet; its commit message describes the implementation.
- **Earlier verification** of the base fixes: `C:\nscrev\reports\fixes-1163-1165-verification.md`.

## 3. How each requirement is enforced (as claimed; independent verification pending)

**R1: at most three physical provider calls; counters exact; `total = calls_used + author_corrections_used + revision_reviews_used`.**
- **Producer** (`round_robin_decomposition.py` at P1):
  - The physical `provider_calls` counter is incremented at each call site (1115, 1530).
  - A pre-call ceiling of `max_calls + 1` applies (1090).
  - A correction is refused after a revision review (1482).
  - The grant predicate `_revision_review_refusal` (653) needs both counters to be exact int 0.
  - An end-of-run accounting identity check (1675-1686) rejects any mismatch as an internal error.
  - `revision_reviews_used` is always written (1743, 1775).
- **AssistantControl (M1-M4):** exact int 0/1, never both counters 1, exactly three rounds and two history entries when the revision count is 1.
- **D1C:** `_exact_bounded_counter`. A revision count of 1 requires `max_calls == calls_used == 2`, the correction key present, and round and history counts of `calls_used + rev` and `calls_used - 1 + rev`.

**R2: pooled sessions excluded.**
- **Producer:** `pooled_run` (936) refuses the grant, so the run ends `needs_human` exactly as before, re-checked before publishing round 3 (959). Leases and settlement are untouched.
- **AssistantControl:** M8 refuses any run carrying pooled sessions.
- **D1C:** `_independent_codex_roles` refuses a pooled run that counts a revision review; `local_decomposition_apply._review_run_result` refuses a present non-zero count.

**R3: round 3 bound to the exact revised candidate.**
- **Candidate:** version 2 by the reviser, checked through `validate_decomposition_review(expected_candidate_sha256=<v2>, round_number=3)`.
- **Reviewer:** must not be the reviser, and its runtime identity must differ from the reviser's `AgentResult.provider`. The route is re-resolved after the provider bundle is built (1099-1113).
- **Result authentication:** `_revision_review_identity_rejections` (709, 1211) checks the invocation id, role and identity.
- **Source:** revalidated after the call and at the end of the run.
- **Findings:** `prior_finding_resolutions` must cover every outstanding finding, and `pass` needs each one resolved or withdrawn.
- **Outcomes:**

  | Round 3 | Run result |
  |---|---|
  | `pass` | `review_ready` (the only path to it) |
  | `revise` | `needs_human` |
  | `needs_human` | `needs_human` |
  | provider failure or schema-invalid output | `agent_failed` |
  | identity mismatch, invalid output or Source drift | `rejected` |

- **No fourth call.**

**R4: every accepting consumer.**
- **AssistantControl `_review_ready_proof`** accepts exactly three shapes: pair, pair plus the one author correction, and pair plus the one revision review. Every shape then gets:
  - M7: Source branch must match;
  - M5: full ordered round-history replay, including runtime identities from D1C's `RUNTIME_PROVIDER_IDENTIFIERS`, the candidate chain v1 to published, an approver independent of the latest author, and the B3 finding replay ending in a clean pass;
  - M6: authentication of every round's own invocation artifacts (`decomposition.py:711-803`).
- **AssistantControl `_needs_human_proof` and `inspect`:** refuse impossible counts, an unproven revision review, a round beyond `max_calls` that no count names, and a retained Source-movement rejection. They keep `revision_reviews_used` in the facts, and accept records retained before the count existed.
- **D1C:** the changed `_call_accounting_valid` plus the new `_revision_review_shape_invalid` (nine design conditions). The round-3 invocation id was already derived from the approving round's number, so it needed no change. No new reason codes were added.
- **Consumer audit.** The producer's report section 3 lists every other reader; they need no change.

**R5: author guidance, with no Gauntlet-only bypass.**
- `prompts.child_evidence_and_gate_rules(context)` renders one block, used identically in the author, author-correction and reviewer prompts.
- **Provenance rule:** provenance, bootstrap observations, notes and tests are never GDD evidence.
- **Empty evidence:** when `selected_task_gdd_evidence == []`, every child's `gdd_evidence` stays empty.
- **Recorded evidence:** a non-empty list keeps being cited.
- **Gates:** a gate claims only what its test proves.
- **Engineering requirements:** public/static class shape, names, constants, `.meta` GUIDs, exact `exclusive_resources` partitioning and full coverage all stay required.
- **No identity effect.** No identity or authorization hash covers prompt text.

**R6: failing-before regressions.** See section 4.

## 4. Evidence so far (from the developers' reports; not yet re-run by the coordinator)

| Commit | Failing-before (detached `ade5bca`+C0 unless noted) | After |
|---|---|---|
| C0 | inert | fixtures smoke PASS (12 tests); round_robin and invocation-id PASS |
| P1 | `revision_review_smoke_test` FAIL, 21 of 21 cases (14 strong, 7 weak or control) | PASS (21 cases); 18 focused suites pass; 3 fail identically at untouched `ade5bca` |
| D1C | new D1C module `Ran 59 tests FAILED (failures=41, errors=1)`; C2 module `Ran 7 tests FAILED (failures=33)` (subtests counted) | `Ran 59 tests OK`; `Ran 7 tests OK`; all other suites match base |
| G | 9 of 11 new tests fail at `ade5bca` (all AssertionError on absent text) | 11 PASS; all TaskDecomposition suites and 3 AssistantControl suites pass |
| A | report pending | report pending |

- **The 3 pre-existing failures:** decomposition_authorization smoke (fails at import), task_id_width (3 of 28), local_decomposition_apply (21 tests: 1 failure, 20 errors).
- **The whole stack has not been tested yet.** The AssistantControl developer's integration tests are running on it now.
- **A notable reproduction.** The earlier, discarded draft made **4 provider calls** and published `review_ready` in the "author correction, then round-2 revise" scenario. P1 makes 3 calls, ends `needs_human`, and publishes nothing.

## 5. Still in progress (not in the snapshot)

1. **Integration tests IT1-IT7** (AssistantControl developer), new file `Pipeline/AssistantControl/test_decomposition_revision_review_integration.py`, staged on top of `ce9ce13`.
2. **Timeout + slow-decomposition triage**, added by Vincent (developer T, branch `throughput/decomposition-slow-triage` from C0; no diff yet). This supersedes open question G4. The design being implemented:
   - **Container limit.** The `docker compose run` limit (now `timeout=3600` in `decomposition.py`) is derived from the per-call budgets: author 1440 + reviewer 1200 + max(1440, 1200) + 600 s of margin, about 4680 s. The worst three-call runs are 3840 s and 4080 s, so today's 3600 s limit can kill a legitimate run. That fails the job and blocks the parent (`decomposition_failed`) until a human clears it.
   - **Controller wait.** `_DECOMPOSITION_JOB_WAIT_SECONDS` becomes the limit + 180.
   - **Slow event.** At 30 minutes, the controller appends exactly one durable `decomposition_slow` event to the existing `graph-controller-events.jsonl`. The event carries a deterministic triage snapshot from the run's `progress.jsonl`: current round, role and provider; how long that round has run; last heartbeat age with a fresh/stale classification; completed rounds; log paths. The orchestrator watches that stream and investigates. The event never kills or changes the job.
   - **Failure event and viewer.** A `decomposition_failed` event carries the same snapshot, and the viewer shows a one-line detail.
3. **Real-run replay check** (verification agent). It runs every retained real decomposition under `C:\NSC` through the new AssistantControl checks and through the base checks: 17 independent passes and 2 NSC-1165 `needs_human` runs. Any refusal on the new code that the base does not also give is a reliability regression to fix before merge. Data point already gathered: all 17 real passes carry 0 findings, and the 2 revises carry 1 blocking finding each.
4. **Coordinator merge, independent verification, and the Issue #36 post.** Documentation proposals from the reports will be applied then. Vincent has put CI out of scope for now, so no workflow edits.

## 6. Questions for Codex

1. **R1-R4 enforcement.** Is the enforcement in section 3 sufficient and correctly placed? In particular, is the producer's end-of-run accounting identity the right backstop, and is the call-time re-check (route re-resolution after the bundle is built) complete?
2. **AssistantControl strictness (the main reliability risk).** A false refusal fails a valid decomposition closed: failed job, then manual clearing. Please look for checks that real producer output might not always satisfy:
   - the `findings` / `prior_finding_resolutions` `to_dict()` round-trip comparison (`decomposition.py:783-793`);
   - the `provider` / `model` equality against the round entry (752-753);
   - `provider_configuration_key == f"{requested_provider}-decomposition"` (768-769);
   - the clean-pass rule (700-701, design G3): a pass that carries advisory findings is refused, although the producer calls it `review_ready`. It has never occurred in the 19 retained real reviews, but the contract allows it. Keep it, or accept advisory-only passes?
3. **D1C tightenings.** These are now refused where base authorized them, and the producer emits none:
   - a revision count of 1 under `max_calls` 3 or 4;
   - a present non-int or non-zero counter (including `null`) on a normal pass;
   - a pooled pair that counts a revision review.

   Acceptable?
4. **Guidance (needs Astra's confirmation).** "Leave unsupported `gdd_evidence` empty" is implemented as all children empty whenever `selected_task_gdd_evidence == []`. That also forbids citing real GDD sections the context does not record. The provenance rule was broadened to every provenance field, plus bootstrap observations, notes and tests. Is that right for real game tasks with no recorded evidence (47 committed tasks today)?
5. **Timeout + triage design (in progress).** Is the derived limit right? Is `graph-controller-events.jsonl` the right channel for the orchestrator event? Should anything other than an event happen at 30 minutes? The design deliberately never kills the job.
6. **Producer notes.**
   - Refused grants now always carry `revision_reviews_used: 0`, so they are not byte-identical to base. No reader rejects unknown keys.
   - The ordinary rounds' identity check compares two ids derived from the same inputs (pre-existing).
   - Consumers must not recompute author-round SHAs from raw structured output, because the producer normalizes an empty artifact-proposal placeholder first. AssistantControl only recomputes revise-round SHAs (`decomposition.py:775-799`).
7. **Commit shape (G8).** Keep per-developer commits, or squash for integration?
8. **Known coverage gaps.**
   - The end-to-end local apply path with the D1C change is unverified, because the shared graph_delta test fixture breaks `local_decomposition_apply_test` at base.
   - The 59 existing D1C tests pass only with a throwaway repaired fixture.
   - Vincent chose to leave the fixture repair out of this work (see `C:\nscrev\reports\graph-delta-fixture-decision-for-codex.md`).

   Is anything here a blocker?

## 7. How to look (read-only)

```bash
git -C C:/nscrev/revision-review-integration log --oneline ade5bca..review/revision-review-mid-20260913
git -C C:/nscrev/revision-review-integration diff ade5bca review/revision-review-mid-20260913 -- Pipeline/TaskDecomposition/round_robin_decomposition.py
git -C C:/nscrev/revision-review-integration worktree add --detach C:/nscrev/codex-mid-review review/revision-review-mid-20260913
```

Key tests, if you run any. They are optional: developers are using the CPU, and the revision-review suite takes about 5 minutes.

```bash
python Pipeline/TaskDecomposition/tests/revision_review_smoke_test.py
python Pipeline/TaskDecomposition/tests/decomposition_evidence_guidance_smoke_test.py
python Pipeline/TaskReviewAgent/tests/decomposition_authorization_revision_review_smoke_test.py
python Pipeline/TaskReviewAgent/tests/local_decomposition_apply_revision_review_test.py
python -m unittest Pipeline.AssistantControl.test_decomposition Pipeline.AssistantControl.test_decomposition_needs_human
```

**Please do not:**
- touch the developers' worktrees (`C:\nscrev\ac-consumer-fix`, `C:\nscrev\decomposition-slow-triage`, `C:\nscrev\revision-review-integration`);
- write anything under `C:\NSC` (retained Gauntlet evidence);
- push or merge.

Remove your review worktree when done.

## 8. Update: real-run replay result (~21:28 UTC, after the snapshot)

The verification agent from section 5, item 3, finished. Scripts, evidence copies and per-run results are in `C:\nscrev\real-run-replay\` (`run_one.py`, `drive_all.py`, `results\*.json`, `summary.json`).

**Result.** All 19 retained real runs were **accepted on both `ce9ce13` and `ade5bca`**, with zero refusals and zero unreplayable runs:
- 16 `review_ready` pair shapes;
- 1 `review_ready` with the one author correction (NSC-1165 `242be48439c3`, from an earlier Gauntlet);
- 2 NSC-1165 `needs_human` runs.

**What ran for real.** `_authenticated_run_result`, then `_review_ready_proof` or `_needs_human_proof`, against the copied bytes, including the new M5 replay and M6 per-round `task_request.json` / `result.json` authentication. `inspect()`'s retained-versus-recomputed comparison was also reproduced, including the carve-out for records written before `revision_reviews_used` existed.

**What was stubbed** (Source-dependent only, identical for every run):
- `_require_clean_source` returns the recorded Source identity;
- `load_committed_task` returns the run's recorded contract identity, which matched `record.task_contract_sha256` in all 19 runs;
- the graph-apply plan check was replaced by a synthetic "fresh" plan.

**Positive control.** On tampered copies, the new code refused while the base accepted:
- a changed round `actual_model` gave `Decomposition round 2 invocation artifacts do not authenticate: result.json model is 'gpt-5.6-sol', expected 'not-the-real-model'`;
- a changed Source branch gave `Decomposition run used another source branch`.

So the zero-refusal result is not a harness artifact.

**Coverage gap.** No retained real run has the new `revision_reviews_used == 1` shape, because every one predates P1. An explicit `revision_reviews_used: 0` follows the same code path as an absent count, so pair and corrected runs from the new producer are covered by this evidence. The three-round shape is covered only by golden fixtures until the next Gauntlet.

**Anomaly.** `GauntletFresh1160-Reviewed-Standalone-Checkouts/.assistant-control/NSC-1165.decomposition.json` shows `status: failed` ("Decomposition result is not one exact regular file") over a `needs_human` run. This is the original NSC-1165 misclassification from the old controller: that project ran before fix `eb3beb7`, the ancestor of `ade5bca`, which reads `run_status` before requiring proposal artifacts. Both commits accept that run through `_needs_human_proof`. It is not a new defect.
