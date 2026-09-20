# Final integration verification: NSC-1165 decomposition reliability stack

Run by the coordinating session, finishing at about 00:25 UTC on 2026-09-14. Logs are in `C:\nscrev\final-verify\` (one log per suite, plus `summary.txt`); the script is `run_final_verify.py`.

## Head under test

- **Head:** `4fd54b8ce167bd87897926384839b03378e86232` on `throughput/decomposition-final-integration` (worktree `C:\nscrev\final-integration`).
- **Diff against base `ade5bca`:** 30 files, +12,549 / -282. `git diff --check` is clean for the whole stack.

Commits, oldest first (each kept separate by owner):

| # | Commit | Owner | Purpose |
|---|---|---|---|
| 1 | `c1077e0` C0 | producer | revision-review constants and golden fixtures (inert) |
| 2 | `ac47d5e` A | AssistantControl | replay and authenticate the bounded revision-review round history |
| 3 | `f39abd6` P1 | producer | one bounded, independent revision review of a last-call revision (three-call cap) |
| 4 | `514dfb9` D1C | D1C | authorize exactly the bounded revision-review shape |
| 5 | `ce9ce13` G | guidance | child evidence and completion-gate guidance |
| 6 | `fce5398` I1 | AssistantControl | end-to-end integration tests |
| 7 | `ff5bdc6` A2 | AssistantControl | advisory-only passes (blocker 2); needs_human revision-review identity (blocker 5) |
| 8 | `4449fb8` T | timeout | limit derived from effective budgets (blocker 1); 30-minute `decomposition_slow` and `decomposition_failed` events |
| 9 | `e25b53e` T2 | timeout | a failure while building the compose command ends `failed`, never stuck `running` |
| 10 | `01f2660` A3a | AssistantControl | whole-stack tests (blocker 6) |
| 11 | `de46660` F | D1C | TaskGraph fixture partition repair (blocker 4) |
| 12 | `f7d14b7` D2 | D1C | D1C advisory-only pass tests |
| 13 | `65a73d0` E | evidence | child GDD evidence depends on context (blocker 3) |
| 14 | `65e770b` D3 | D1C | D1C wrapper, pure binder untouched, reason `child_gdd_evidence_invalid` |
| 15 | `4fd54b8` A3b | AssistantControl | AssistantControl consumer evidence check plus whole-stack evidence tests |

## Suite results on `4fd54b8`

Suites ran one at a time. Result: **33 of 34 exit 0.**

### TaskDecomposition (12 suites, all PASS)

| Suite | Result |
|---|---|
| revision_review | 21 cases |
| child_gdd_evidence | 17 |
| decomposition_evidence_guidance | 11 |
| revision_review_fixtures | 12 |
| pooled_decomposition | 17 |
| round_robin_decomposition, author_correction, round_invocation_id, live_decomposition, context_builder, review_contracts, decomposition_contracts | PASS |

### AssistantControl (7 of 8 OK)

| Suite | Result |
|---|---|
| test_decomposition | 62 OK |
| test_decomposition_needs_human | 41 OK |
| test_decomposition_revision_review_integration | 7 OK |
| test_decomposition_whole_stack | 16 OK |
| test_decomposition_triage | 18 OK |
| test_graph_controller | 33 OK |
| test_background_jobs | 81 OK |
| test_viewer | 39 run, 1 error (pre-existing) |

The `test_viewer` error is `GraphControllerTimingEndToEndTests.test_build_projects_timing_for_the_in_scope_task_named_by_the_controller`: `stage_elapsed_seconds` is None, so the `>= 42.0` comparison raises a TypeError. It is identical at `f941857` and at `fce5398` (developers T and E), so it predates this stack.

### TaskGraph (all PASS; before the F fixture repair, every one of these failed on the partition error)

- graph_delta
- graph_apply_plan
- graph_apply_materialize
- graph_undo (2 tests)
- graph_apply

### TaskReviewAgent (all PASS)

| Suite | Result |
|---|---|
| decomposition_authorization | 59 |
| decomposition_authorization_revision_review | 63 OK |
| decomposition_authorization_child_evidence | 11 OK |
| local_decomposition_apply_revision_review | 7 OK |
| task_id_width | 28 |
| automated_decomposition_replay | 14 |
| host_decomposition_launcher | 20 |
| decomposition_session_pool | 10 |
| local_decomposition_apply | 21 OK |

### Deliberately not run

These local suites write temporary directories under `C:\NSC`. D ran them on F with redirected temp roots; the results are in `fix-fixture-partition-f-d2-agent-report.md`.

- **Redirectable:** pending, harvest, read_race, wake.
- **Hard-coded `C:\NSC` paths:** candidate_source_integration, source_wait_completion, immutable_crew_manifest.

Their remaining failures are all pre-existing and attributed:
- `Snapshot.local_decomposition_stage` TypeError
- `WakeScheduler._notify_local_candidate_applications` AttributeError
- a stale SimpleNamespace test double, from `6fc3f461`
- stale "need attention" view assertions, from `0c6e79e9`
- `ExecutionCrewBridge.allow_materialization_bridge`

## Live evidence

- **Live test 1:** `C:\NSC\GauntletFresh1160-FixesRun-20260913` at `3d5a8bb`, which is the stack through D2 without A2/T/E. NSC-1165 split in three calls: claude authored, codex revised, claude revision-reviewed and passed. `review_ready` took 339.7 s, AssistantControl accepted the real three-round run and applied it, and children NSC-1172/1173 integrated. The controller ended `complete` in about 22 minutes with zero human actions.
- **Run 1 regression** (`C:\nscrev\g1160-reg`, code `9dee4a6` = stack through E):
  - First attempt: every decomposition failed because the pipeline's Codex account hit its usage limit ("try again at Sep 19th, 2026 8:10 AM"). This was not a code defect.
  - After Vincent switched Codex accounts: NSC-1160 split in two calls (`review_ready`, applied), and 4 tasks integrated.
  - Vincent then stopped the run to conserve provider usage (`stop-graph`, cleanup verified).
- **Run 2, five real game tasks** (combined tree `80a7537`, proposals only): no split succeeded. NSC-025, NSC-035 and NSC-014 were rejected, and NSC-015 was rejected after the Codex review. NSC-033 was stopped by Vincent. Every rejection came from two coverage-mapping rules the prompts never state; 7 of 9 drafts broke one, from both providers. See `codex-prompt-coverage-mapping-fix.md`.

## Open items

1. **Coverage-mapping fix.** Astra gave GO. It is being implemented on `codex/coverage-mapping-guidance-20260913` in `C:\nscrev\coverage-mapping-guidance-fix`.
2. **Re-run the five real tasks** after that fix: rebuild the combined tree with `rebuild_combined.py`, and use a new checkout root.
3. **Follow-ups for Codex:**
   - local-apply child-evidence wiring (needs a fixture GDD and `context.json`);
   - the child-evidence gate in `host_decomposition_launcher.py` (Issue workflow);
   - test-temp overrides for the three hard-coded `C:\NSC` suites;
   - repairs for the stale local tests;
   - the pre-existing `test_viewer` timing error.
4. **Documentation and CI proposals** from the developer reports are not yet applied (Vincent put CI out of scope).
