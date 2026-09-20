# Codex blocker 4, fixture partition repair (F) and D1C advisory tests (D2): developer D's report

Received 2026-09-13 at about 23:25 UTC and recorded in summary by the coordinating session.

## Commits

Both commits are on `throughput/decomposition-fixture-partition` in `C:\nscrev\fixture-partition-fix`. The worktree is clean, nothing is pushed, `diff --check` is clean, and every file is i/lf w/crlf.

- **F `a03eb4bf4be3a01562bf94febcbf8bae3ba93f55`** (parent fce5398). Test fixtures only:
  - `Pipeline/TaskGraph/graph_delta_smoke_test.py` +70/-12
  - `Pipeline/TaskReviewAgent/tests/task_id_width_smoke_test.py` +14/-3
- **D2 `0b16e38e8cd3c89ef84d4f0b51fd690d39d1d289`** (parent F). Tests only:
  - `decomposition_authorization_revision_review_smoke_test.py` +144, which adds 4 advisory-pass tests using the producer's own validator. D1C already authorized advisory-only passes and refused blocking ones.

## Suites, run one at a time (before = fce5398, after = F)

| Suite | Before | After |
|---|---|---|
| graph_delta | partition error | PASS |
| graph_apply_plan | partition error | PASS |
| graph_apply | partition error | PASS |
| graph_apply_materialize | partition error | PASS |
| graph_undo | partition error | PASS (2) |
| decomposition_authorization | import error | PASS (59), also on D2 |
| decomposition_authorization_revision_review | 59 OK | 59 OK; 63 OK on D2 |
| local_decomposition_apply | 21 FAILED (1 failure, 20 errors) | 21 OK |
| local_decomposition_apply_revision_review | 7 OK | 7 OK |
| task_id_width | 3 failures | PASS (28); expectation NSC-991..1006 unchanged, the fixture now filters the assistant-control-local-replay-v1 family |
| candidate_source_integration | 9 (errors=2) | 9 OK |
| assigned_admission | 2 (errors=2) | 2 OK |
| race | 4 (errors=4) | 4 OK |
| read_race | 1 (errors=1) | 1 OK (redirected temp) |
| harvest | 5 (errors=5) | 5 FAILED (3 failures, 2 errors), pre-existing (below) |
| pending | 4 (errors=4) | 4 FAILED (3 failures, 1 error), pre-existing |
| wake | 6 (errors=2) | 6 (errors=2), pre-existing |
| reset_task | partition error | PASS |
| thousand_gauntlet | PASS | PASS |
| source_wait_completion | 2 errors | not run on F (hard-coded `C:\NSC` temp path) |
| immutable_crew_manifest | AttributeError | not run on F (hard-coded `C:\NSC` temp path) |

The graph-delta `created` resource-group branch is unreachable for decomposition deltas under exact partitioning, and the test now asserts this explicitly.

## Remaining failures, all pre-existing

1. **Pending and harvest:** `Snapshot.local_decomposition_stage()` raises TypeError (missing `record`).
2. **Wake:** `WakeScheduler._notify_local_candidate_applications` raises AttributeError.
3. **Harvest (a stale test double, now unmasked):** SimpleNamespace has no `consecutive_block_counts`. Production added that attribute in `6fc3f461` (2026-09-09).
4. **Pending and harvest (stale view assertions, now unmasked):** "0 need attention" and "1 need attention" are no longer found, and one status reads 'active' instead of 'human_action'.
   - `0c6e79e9` (2026-09-09) removed the "need attention" text from `GauntletView/pipeline_activity.py`.
   - The assertions added in `4ed02e81` were never updated.
   - An attribution run of harvest at ade5bca, with only F's fixture files copied in, gives the same 5 failures.
5. **immutable_crew_manifest:** `ExecutionCrewBridge.allow_materialization_bridge` AttributeError (not run).

## Disclosure: suites wrote under `C:\NSC`

**Which suites:**
- **Redirectable:**
  - `local_decomposition_pending_test` (and harvest, which runs the same class) uses `C:\NSC\DecompPendingTmp\pending-<uuid>`; override `NSC_DECOMP_PENDING_TEMP`.
  - `local_revision_read_race_test` uses `C:\NSC\RevisionRaceTmp`; override `NSC_REVISION_RACE_TEMP`.
- **Hard-coded:** `local_candidate_source_integration_test`, `local_source_wait_completion_test`, `immutable_crew_manifest_test`.

**When they ran:** the earlier D1C task's base+C0 and final runs, the fce5398 before-run, and on F: candidate_source_integration, harvest and pending.

**Effect:**
- Each test created and removed its own directory. The coordinator's listing confirmed only 2026-09-09 leftovers remain, and nothing was deleted or left behind.
- No live run directory was touched.
- After the redirect decision, pending, harvest, read_race and wake ran with temp roots under `C:\nscrev\test-temp`. The read-only `C:\NSC` snapshots before and after each run were identical.

## Proposed follow-ups (not done)

1. Test-only temp-root overrides defaulting to system temp for the three hard-coded suites, and move the pending and read_race defaults off `C:\NSC`.
2. Repair the pre-existing stale tests: the harvest double, the pending view assertions, the `Snapshot.local_decomposition_stage` call, the WakeScheduler rename, and `allow_materialization_bridge`.

## D3 (in progress)

- E has been cherry-picked as `24611424225d7fc9e68c46462fc7b84847156e73` (parent 0b16e38).
- **Coordinator decision:** option B. D3 is the D1C wrapper `validate_decomposition_authorization_with_committed_evidence`: the pure binder stays unchanged, a new reason code `child_gdd_evidence_invalid` is added, and tests cover it. The frozen decision type has no detail field, so E's message is not carried.
- **Audit:** no production caller reaches the D1C binder. Local apply authorizes through its own `_review_run_result`, and the Issue-workflow `host_decomposition_launcher` has no child-evidence gate.
- **Follow-ups listed for Codex:** local-apply wiring (needs a fixture GDD, `context.json` and a full local-suite rerun), and the `host_decomposition_launcher` proposal/apply gate.

## D3 final report (received about 23:45 UTC)

- **Commit:** D3 `c958824b712358a69b89aff682237fecc95a2494`, parent `2461142` (the E cherry-pick).
  - `decomposition_authorization.py` +74/-0 adds `validate_decomposition_authorization_with_committed_evidence` and the reason code `child_gdd_evidence_invalid`. The pure binder's source SHA-256 is unchanged.
  - New test file `decomposition_authorization_child_evidence_test.py` +340.
- **Failing-before** at 0b16e38 + E: Ran 11 tests, FAILED (errors=14).
  - 8 methods error because the wrapper does not exist yet. This is weak evidence, since the wrapper is new API.
  - 3 controls pass before and after: fixture classification, the pure binder with every side-effect path disabled, and the pure binder never reaching the evidence check.
- **Suites on c958824** (all exit 0; none writes under `C:\NSC`):

  | Suite | Result |
  |---|---|
  | decomposition_authorization_child_evidence_test | 11 OK |
  | decomposition_authorization_smoke_test | PASS (59) |
  | decomposition_authorization_revision_review_smoke_test | 63 OK |
  | child_gdd_evidence_smoke_test | PASS (17) |
  | decomposition_evidence_guidance_smoke_test | PASS (11) |
  | revision_review_fixtures_smoke_test | PASS (12) |
  | AssistantControl test_decomposition | 57 OK |
  | AssistantControl test_decomposition_needs_human | 37 OK |
  | AssistantControl revision-review integration | 7 OK |
  | decomposition_session_pool | PASS (10) |
  | provider_profiles_test | 41 OK |
  | pooled_decomposition | PASS (17) |

- **Decision type:** the wrapper returns the frozen `DecompositionAuthorizationDecision` unchanged. E's message is not carried, and the commit documents this.
- **Follow-ups for Codex:**
  - (a) Local-apply wiring. It first needs a test-only fixture commit (committed GDD, `context.json`, `context_sha256`; NSC-042 is human-only, so it is always `real_task`), then a full local-suite rerun with the test-temp overrides.
  - (b) `host_decomposition_launcher.py`: call E's check in `_run_proposal` before `publish_decomposition_handoff`, and optionally in `_run_apply` before `apply_graph_delta`.
  - (c) Test-temp overrides for the three hard-coded `C:\NSC` suites.
  - (d) Repair the pre-existing stale local tests.
- **Cleanup:** the d3-before worktree has been removed.
