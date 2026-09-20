# NSC-1165 bounded revision review: producer's final report (C0 + P1)

Received 2026-09-13 at about 21:02 UTC and recorded here in substance by the coordinating session. The coordinating session checked the commit identities; its independent test runs will be recorded with the integrated head.

## 1. Commits and files

Branch `throughput/decomposition-revision-review`, worktree `C:\nscrev\revision-review-fix`. The worktree is clean at P1 with no stash; nothing was pushed or merged.

| Commit | SHA | Parent |
|---|---|---|
| C0 | `f941857ab97389f37d257c63cfcce73ae88aa88c` | `ade5bca50d452b276a32f31a7ad8baeb770b2404` |
| P1 | `9e7116ffb799bcb645814b588dc7155818496ef3` | C0 |

C0 changes no behaviour. Paths are under `Pipeline/TaskDecomposition/`.

| Commit | File | + / - |
|---|---|---|
| C0 | `round_robin_decomposition.py`: B1 constants; one identical literal replaced | +28 / -3 |
| C0 | `tests/revision_review_fixtures.py` (new, D1 API) | +1463 |
| C0 | `tests/revision_review_fixtures_smoke_test.py` (new) | +774 |
| P1 | `round_robin_decomposition.py` | +317 / -9 |
| P1 | `tests/revision_review_smoke_test.py` (new) | +1067 |
| P1 | `tests/round_invocation_id_smoke_test.py`: round 3 added | +2 |

These are unchanged: `review_contracts.py`, `prompts.py`, `review_prompts.py`, `contracts.py`, every consumer, the README, `Docs/` and the workflows.

## 2. How each requirement is enforced

Line numbers refer to `round_robin_decomposition.py` at P1.

### R1: three-call ceiling, mutual exclusion, exact counters

- **Physical counter.** `provider_calls` is incremented at each call site: ordinary rounds and round 3 at 1115, the author correction at 1530.
- **Ceiling.** Before every call, `provider_calls >= max_calls + 1` refuses with an internal error (1090).
- **Mutual exclusion.** The correction site refuses once a revision review has happened (1482). The grant predicate `_revision_review_refusal` (653) requires `author_corrections_used == 0` and `revision_reviews_used == 0` as exact ints.
- **End-of-run check.** At the end of every run (1675-1686), the run is rejected with an internal error unless all of these hold:
  - `provider_calls == calls_used + author_corrections_used + revision_reviews_used`
  - at most one extra call
  - at most `max_calls + 1` calls
- **Recorded.** `revision_reviews_used` is always written to the run result (1743) and to `run_completed` (1775).

### R2: pooled runs excluded

- `pooled_run` (936) is set by pooled sessions, a lease bundle, or independent same-provider roles. It refuses the grant.
- Such a run ends exactly as today: `needs_human` with `CALL_LIMIT_AFTER_REVISION_REASON`, and its leases settle idle.
- The predicate is re-checked before anything for round 3 is published (959). A failure is rejected with no call.
- Pool leases, settlement and `session_pool_support.py` are untouched.

### R3: round 3 bound to the exact revised candidate

- **Candidate.** The grant requires the latest candidate to be version 2, authored by the reviser. Round 3 goes through the unchanged reviewer prompt and `validate_decomposition_review(expected_candidate_sha256=<v2>, round_number=3, ...)`. `rounds/03-request.json` and the round-3 record carry the v2 summary.
- **Independence.** The reviewer is `order[2 % len]` and must not be the reviser. Its runtime identity is validated before the run (823) and must differ from the reviser's `AgentResult.provider`. After the provider bundle is built, the route must still resolve to that identity (1099-1113), or no call is made.
- **Invocation and provider identity.** After the call, `_revision_review_identity_rejections` (709, 1211) requires the round-3 invocation id, the reviewer role and the validated identity, never the reviser's identity. Otherwise the output is never read.
- **Source.** The existing revalidation runs after the call and at the end of the run; drift gives `rejected`.
- **Findings.** The existing contract is unchanged: `prior_finding_resolutions` must exactly cover the outstanding findings, and `pass` requires each one resolved or withdrawn.
- **Outcomes.**

  | Round 3 result | Run status | Reason |
  |---|---|---|
  | `pass` | `review_ready` (the only path to it) | none |
  | `revise` | `needs_human`, v3 adopted | `REVISION_REVIEW_REVISED_AGAIN_REASON` |
  | `needs_human` | `needs_human` | `REVISION_REVIEW_STOPPED_REASON` |
  | provider failure or schema-invalid output | `agent_failed` | prefix `REVISION_REVIEW_REJECTION_PREFIX` |
  | identity mismatch, invalid review or revision, or Source drift | `rejected` | prefix `REVISION_REVIEW_REJECTION_PREFIX` |

- **No fourth call.** The loop ends after round 3, and the ceiling guard refuses any further call.

### R4, R5, R6

- **R4 (consumers):** not in these commits. C0 gives consumers the D2 and D3 golden runs, the D4 forged variants and the artifact writers, and P1's golden-conformance cases prove the producer emits exactly those.
- **R5 (prompts):** out of scope.
- **R6:** the 21 cases in section 4. Every producer run in that suite is also checked against physical-call accounting.

## 3. Consumer audit (read-only)

| Reader | Status |
|---|---|
| `TaskReviewAgent/decomposition_authorization.py` | D1C developer; base refuses the three-record shape in `_call_accounting_valid` |
| `TaskReviewAgent/local_decomposition_apply.py` | D1C developer; requires pooled, distinct confirmed sessions, so it already refuses any non-pooled run |
| `AssistantControl/decomposition.py` | AssistantControl developer |
| `TaskReviewAgent/decomposition_replay.py` | no change; reads only Issue events, `graph_delta.json` and `decomposition_result.json` |
| `provider_budget.observe_decomposition_result` | no change; round 3 is an ordinary `rounds/03`, so its usage is counted |
| `decomposition_session_pool` settlement | no change; pooled runs only, and it refuses `round_number > max_calls` |
| `host_decomposition_launcher.py` | no change; default `--max-calls 4`. A non-pooled `--max-calls 2` run can hand off a round-3 approval, still gated by human authorization |
| `polling_orchestrator.py` | no change; its `--max-calls 2` runs are pooled same-provider pairs, which never qualify |
| `GauntletView/server.py` | no change; new `revision_review_*` events fall outside its `round_provider_*` filter |
| AssistantControl `viewer.py`, `graph_controller.py`, `background_jobs.py` | no change; they read record status and needs_human reasons |
| `run_round_robin_decomposition.py` | no change; exit code 0 for `review_ready` and `needs_human` |
| `run_round_robin_decomposition_rag.py` | no change; its `**kwargs` wrapper passes round 3 through |
| `run_reviewer_replay_ab.py`, `live_decomposition.py` | no change |

## 4. Per-test evidence

Failing-before ran in a detached `ade5bca`+C0 worktree with only `revision_review_smoke_test.py` and `round_invocation_id_smoke_test.py` copied in, and no shim. Result: FAIL, 21 of 21 cases. Passing-after on P1: PASS, 21 cases.

| Case | Before (base+C0) | Strength |
|---|---|---|
| golden review_ready / revised_again / stopped (3) | real run fields differ from the golden | strong |
| nsc1165 revision passed -> review_ready | `needs_human` at the call limit | strong |
| withdrawn prior finding permits pass | `needs_human` | strong |
| revises again -> needs_human | provider calls (1,1), not (2,1) | strong |
| stops at human authority | provider calls (1,1), not (2,1) | strong |
| provider failure -> agent_failed | `needs_human` | strong |
| malformed or invalid output never approves | `needs_human` | strong |
| must resolve every prior blocking finding | `needs_human` | strong |
| Source moving during review -> rejected | `needs_human` | strong |
| provider calls never exceed three | `needs_human` | strong |
| route changed -> no call | `needs_human`; base never reaches round 3 | shows the check exists |
| result identity authenticated | `needs_human`; base never reaches round 3 | shows the check exists |
| normal two-call approval, no extra call | KeyError `revision_reviews_used` | weak (control) |
| correction and revision review mutually exclusive | KeyError | weak at base |
| equal runtime identities, no review | KeyError | weak (control) |
| pooled runs, no review | KeyError | weak (control) |
| round-two outcomes, no review | KeyError | weak (control) |
| longer call limits, no review | KeyError | weak (control) |
| refusal-condition unit test | missing name `_revision_review_refusal` | weak |
| invocation-id round 3 | passes before and after | pin, not a regression |

**Reproduced defect in the earlier draft.** In the scenario "author correction, then a round-2 revise", the draft:
- made 4 provider calls (claude 3, codex 1);
- wrote 4 round records with counters 2/1/1;
- ended `review_ready` and published `decomposition_result.json`.

P1 makes 3 calls in that scenario, ends `needs_human` and publishes nothing. The mutual-exclusion and ceiling cases both fail against the draft.

## 5. Suites on P1 (one at a time)

C0 gate: `revision_review_fixtures_smoke_test` PASS (12), `round_invocation_id_smoke_test` PASS, `round_robin_decomposition_smoke_test` PASS.

On P1, 18 suites pass and 3 fail exactly as at untouched base.

| Suite | Result |
|---|---|
| author_correction, context_builder, decomposition_contracts, gdd_rag_review_context, live_decomposition, review_contracts, reviewer_replay, round_invocation_id, round_robin_decomposition | PASS |
| pooled_decomposition | PASS (17 tests) |
| revision_review_fixtures | PASS (12 tests) |
| revision_review | PASS (21 cases) |
| automated_decomposition_replay | PASS (14 tests) |
| decomposition_session_pool | PASS (10 tests) |
| host_decomposition_launcher | PASS (20 tests) |
| ci_workflow_split | PASS |
| `Pipeline.AssistantControl.test_decomposition` | Ran 26 tests OK |
| `Pipeline.AssistantControl.test_decomposition_needs_human` | Ran 19 tests OK |
| decomposition_authorization | fails at import (pre-existing) |
| task_id_width | 3 of 28 fail (pre-existing) |
| local_decomposition_apply | Ran 21 tests FAILED (failures=1, errors=20) (pre-existing) |

These pre-existing failures were proven identical at untouched `ade5bca`, with the same failure lists line for line. The causes:
- The shared graph_delta fixture predates the partition rule in `379685b`.
- The branch's committed NSC-1001..1139 contracts survive the task-ID-width fixture's filter, so allocation starts at NSC-1140 instead of NSC-991.

## 6. The earlier draft

- **Kept:**
  - the loop extended to `max_calls + 1`, so round 3 reuses the ordinary reviewer body;
  - `rounds/03`, the progress events and the reason texts (now constants);
  - the `revision_reviews_used` key and the `>=` in the revise branch;
  - most test scenarios.
- **Fixed:**
  - the grant ignored author corrections, which allowed 4 calls;
  - the counter was set before the call rather than at it;
  - missing: physical-call accounting, the ceiling, the call-time re-check, runtime-identity independence and result authentication;
  - tests shared one `fake` identity for both providers;
  - a draft test expected correction plus revision review to succeed;
  - schema-invalid output was expected to be `rejected` rather than `agent_failed`.
- **Discarded:**
  - the draft's AssistantControl edits, reverted on instruction because they accepted a four-round correction-plus-revision shape;
  - its change to case 4 of the round-robin smoke test.

## 7. Risks and contract notes

- `decomposition_replay.py` did not change.
- **No `reject` verdict exists.** It maps to `needs_human` (contract G1).
- **Refused grants are not byte-identical to base.** Status, reasons and rounds match, but the run result now always carries `revision_reviews_used: 0`. No reader was found that rejects unknown run-result keys.
- **Controls fail at base only on the new counter key.** Their behavioural assertions match base, although contract F4 says controls pass before and after.
- **Additions to the exact D1 API:**
  - `write_artifact_mapping`, for forged F18 artifacts;
  - an optional `model` argument on `RuntimeQueueProvider`;
  - extra exported constants and message templates.
- **Variant handling:**
  - F18 variants mutate the `round_artifacts` mapping and raise `TypeError` when given a run result; run-result variants raise `TypeError` when given a mapping.
  - `FORGED_NEEDS_HUMAN` variants apply to D3; N1 and N8 reshape it into the call-limit shape first.
  - D1C is included in the needs-human variants as `review_invalid` / `d1b_run_status_not_review_ready`. The D1C developer confirmed this in its report.
- **Choices where the contract was silent:** the S2 and SC pass summaries, and the SC rejection text.
- **Existing coverage unverified locally.** The existing D1C authorization and local-apply suites cannot run even at base.
- **The ordinary rounds' identity check is a tautology** (pre-existing): it compares two ids computed from the same inputs. Only round 3 authenticates `AgentResult.run_id`.
- **Shared-identity fakes never get a revision review.** Tests that need one must use the fixture module's identity-bound fakes.
- **Digest recomputation (important for consumers).**
  - `validate_decomposition_result` returns `DecompositionResult.from_dict(raw)` (`policy.py` 61, 289), and for revise rounds the producer hashes that same parse of `revised_decomposition`. A consumer recomputing a revise round's SHA from round 3's structured output therefore gets the producer's digest.
  - Consumers must not recompute author-round SHAs from raw structured output: the producer normalizes an empty artifact-proposal placeholder before hashing. Design contract C3 step 8 does not do this.
- **Accepted defaults kept:**
  - G6: the round-3 reviewer is not told it has the final call;
  - G7: a refusal after the provider bundle is built can leave `rounds/03-request.json` and a start event;
  - G4: the AssistantControl compose timeout stays at 3600 s. This is now superseded by developer T's timeout change, per Vincent.

## 8. Proposed documentation and CI

The coordinator applies these at merge if appropriate. Vincent has put CI out of scope for now.

- **`Pipeline/TaskDecomposition/README.md:123`**: replace the call-limit sentence to describe the one bounded revision review. It applies to a two-call, non-pooled, uncorrected circuit; the provider that did not author the revision reviews it as round 3 outside `max_calls`, counted by `revision_reviews_used`. Only `pass` gives `review_ready`. No run exceeds `max_calls + 1` provider calls, and a two-call run never exceeds three.
- **README artifact tree:** add `03-request.json` and a `03/` block containing:
  - `review.json`, `review_history_entry.json` and `round_result.json`;
  - `candidate.json`, `candidate_identity.json` and `candidate_graph_delta.json` when round 3 revised again;
  - `task_execution/<invocation-id>/` and `agent_runtime/<invocation-id>/`.
- **README, after the correction paragraph (line 388):**
  - Round 3 uses the same prompt, review contract, deterministic validation and Source revalidation as any reviewer round.
  - It must resolve or withdraw every outstanding blocking finding.
  - It is never offered to pooled runs or to runs that already made an author correction.
  - Provider calls always equal `calls_used + author_corrections_used + revision_reviews_used`, or the run is rejected as an internal error.
  - A grant that no longer holds at call time is rejected with no call.
- **Docs to update with the same one-sentence exception:**
  - `Docs/AI-Pipeline/ADR-035_ROUND_ROBIN_DECOMPOSITION_REVIEW.md:108`
  - `Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md:228`
  - `Docs/AI-Pipeline/CURRENT_STATE.md:210`
  - `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md:248`
  - `Docs/AI-Pipeline/Stage5-Decomposition-Design/CURRENT_STATE_AUDIT.md:70`, which also gets the two new test files added to its list
- **CI (not applied):** add steps to `d1b2-core-deterministic.yml` for `revision_review_fixtures_smoke_test.py` and `revision_review_smoke_test.py`. The suite takes 160-300 s locally, and pooled takes up to 469 s against a 20-minute job timeout.

## 9. What was and wasn't touched

- **C:\NSC:** nothing was written, run, cleared or relaunched; only retained run-result and review files were read.
- **Other systems:** no Docker, providers or GitHub, and no push or merge.
- **Messages:** only the two SHA notices to the coordinator.
- **Worktrees:** the evidence worktrees `C:\nscrev\rrbase` and `C:\nscrev\rrcur` were removed and pruned.
