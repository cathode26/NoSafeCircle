# Codex status check 2: NSC-1165 decomposition reliability work (22:50 UTC, 2026-09-13)

Prepared by the coordinating session for Codex at Vincent's request. Work continues while you read; nothing is paused. Please evaluate the direction and the evidence so far.

## 1. Headline: one full live Gauntlet passed with the core fix

- **Project.** `C:\NSC\GauntletFresh1160-FixesRun-20260913`, branch `gauntlet-test/fixes-ade5bca-1160`.
- **Code in the run.** Project head `3d5a8bb` carries the content of `ade5bca..0b16e38` (C0, A, P1, D1C, G, I1, F, D2). A2, T, T2 and E were deliberately NOT in this run.
- **Setup.** NSC-1165's retained `needs_human` job was archived with `clear-background-job`, and its record was renamed rather than deleted. The same controller then resumed with runner v11.
- **NSC-1165 split.** Run `assistant-nsc-1165-decompose-3d5a8bbbea59`, fresh plan, no reuse of the retained plan:

  | Round | Provider | Role | Duration | Result |
  |---|---|---|---|---|
  | 1 | claude | `task_decomposer` | 84.9 s | valid candidate |
  | 2 | codex | reviewer | 105.4 s | `revise`, valid revision |
  | 3 | claude | revision reviewer | 60.4 s | `pass` |

  - `run_completed review_ready` after 339.7 s, at 22:15:02 UTC.
- **Consumer check.** AssistantControl `_review_ready_proof` accepted this first real three-round run: `reviewer_provider` claude, models [gpt-5.6-sol, claude-sonnet-5], `revision_reviews_used` 1, `author_corrections_used` 0. It was applied at about 22:15:40 with no human involved.
- **Children.** NSC-1172 and NSC-1173 were built, validated, auto-approved and integrated (22:25:26 and 22:28:46).
- **Controller.** It ended `complete` at 22:29:26 UTC, and every target in NSC-1160..1167 is done. The previous fresh run had stopped `awaiting_human` on NSC-1165. Total time was about 22 minutes, with zero human actions.
- **Earlier replay check.** A read-only replay of all 19 retained real runs through the new AssistantControl checks, before A2, accepted every run and refused tampered controls. Details: `mid-dev-review-revision-review-20260913.md` section 8.

## 2. Snapshot for evaluation

`review/revision-review-mid2-20260913` = `322dfeb31af0809b56c2ea4f979cd2dfc530a2d0`, a local ref. It has 22 files, +9,337/-237 against `ade5bca`. All cherry-picks are patch-identical to the originals.

`c1077e0` C0 → `ac47d5e` A → `f39abd6` P1 → `514dfb9` D1C → `ce9ce13` G → `fce5398` I1 → `ff5bdc6` A2 → `4449fb8` T → `e36554e` F → `322dfeb` D2

Not yet included:
- **T2** `c245deba804fe3dd6d8cfd548d02f75274c28d33` (parent `008d1df`) is committed.
- **E** (evidence by context) is still running suites and is not committed.
- **A3a/A3b** (whole-stack tests) are in progress.

## 3. Your blockers: status

| # | Blocker | Status |
|---|---|---|
| 1 | Outer timeout from effective budgets | **Done: T `008d1df` + T2 `c245deb`.** See below. |
| 2 | Advisory-only pass accepted, blocking refused | **Done.** AssistantControl in A2 `ff5bdc6`; D1C was already correct, with tests in D2 `0b16e38`. |
| 3 | Evidence by context | **In progress (E).** Design accepted with amendments; details in section 4. |
| 4 | Repair the TaskGraph fixture partition | **Done: F `a03eb4b`, test files only.** Revived suites below. |
| 5 | Stronger needs_human revision-review identity | **Done in A2 `ff5bdc6`.** See below. |
| 6 | Whole-stack AssistantControl tests | **In progress.** A3a is on T + T2; A3b is the evidence wiring after E. |

**Blocker 1: timeout.**
- **Budgets.** They are resolved on the host with the producer's own budget functions, and an invalid override refuses before any write.
- **Container environment.** The exact values are forwarded into the container with `--env`.
- **Limits.** The container limit is author + reviewer + max(author, reviewer) + 600, which is 4680 s at defaults. The controller wait is the job's recorded limit + 180.
- **Slow and failed runs.** A run past 30 minutes journals one advisory `decomposition_slow` event with a `progress.jsonl` triage snapshot to `graph-controller-events.jsonl`, and a viewer detail says "orchestrator notified". A failed run journals `decomposition_failed`.
- **T2.** It moves command construction inside `run()`'s try, so a failure after the running record is written ends `failed` instead of stuck `running`.
- **Evidence.**
  - T: failing-before Ran 16, 23 failures and 5 errors.
  - T2: failing-before 18 tests with 4 failures.
  - On `fce5398` + T: triage 16, test_decomposition 57, needs_human 37 and IT 7, all OK; background_jobs 81 OK.
  - Triage passes 18/18 on T2, and on `ff5bdc6` + T + T2.
  - Report: `fix-decomposition-timeout-triage-agent-report.md`.

**Blocker 2: advisory-only pass.** It follows the producer's rule, `review_policy.validate_decomposition_review` (lines 81-99), and keeps every other B3 replay rule. D2 adds 4 D1C tests using the producer's own validator; the D1C module runs 63 tests OK.

**Blocker 4: revived suites on F.** Every one of these failed at `fce5398` on the partition error, or at import:
- graph_delta PASS; graph_apply_plan PASS; graph_apply PASS (559 s); graph_apply_materialize PASS; graph_undo PASS (2 tests)
- decomposition_authorization PASS (59)
- local_decomposition_apply Ran 21 OK (1312 s). This is also the first local verification of the end-to-end D1C local-apply path.
- task_id_width PASS (28). The fixture now filters the `assistant-control-local-replay-v1` family; the expectation is unchanged.
- local_candidate_source_integration 9 OK; assigned_admission 2 OK

Still running: harvest, pending, race, wake, revision_read_race, source_wait_completion, immutable_crew_manifest, reset_task and thousand_gauntlet (thousand_gauntlet already passes at `fce5398`). The `created` resource-group branch is unreachable for decomposition deltas under exact partitioning, and this is now asserted explicitly.

**Blocker 5: needs_human identity (A2).** For needs_human runs with `revision_reviews_used == 1`:
- the Source branch must match (M7);
- every round goes through the shared review-ready checks (requested provider, runtime identity, succeeded, review-only, non-pooled);
- round 3's provider must differ from round 2's;
- the SHA chain and B3 replay are checked;
- recorded paths must be the exact invocation paths;
- M6 file authentication runs whenever the rounds directory exists, and a partial deletion is refused;
- apply still refuses the run.

A2's suites all pass: test_decomposition 62, needs_human 41, graph_controller 33, IT 7. At `fce5398` those same tests failed (6 failures + 3 errors, and 15 failures), including forged and tampered needs_human evidence being accepted. Report: `fix-ac-a2-advisory-needs-human-agent-report.md`.

## 4. Blocker 3 (E): design and measurement so far

**Classification.**
- **Module.** A new pure module, `Pipeline/TaskDecomposition/child_gdd_evidence.py`, with no AssistantControl import.
- **Rule.** `synthetic_fixture_marker` copies the `is_synthetic_gauntlet` rule exactly: `human_approved_synthetic_gauntlet` origin, or a gauntlet_id in the two Gauntlet ids, walking `progressive_decomposition` ancestry; NSC-042 stays human-only. `automation_policy.is_synthetic_gauntlet` delegates to it, and all 80 tried combinations give identical results.

**Context.**
- **New block.** `build_context` adds a `child_gdd_evidence_policy` block: classification, marker, lineage, selected references, GDD sha256, anchor-set sha256 and resolver version.
- **Hash coverage.** The block is covered by `context_sha256`.
- **Legacy contexts.** Retained contexts without the block still match their recorded hashes and are treated as legacy.

**Rule.**
- **Synthetic fixture:** empty child `gdd_evidence` is allowed, but any cited entry must be inherited or resolve.
- **Real task:** every child needs at least one entry, and each entry must be inherited (an exact reference in the selected evidence) or resolve to the committed canonical GDD.
- **Empty selected evidence** exempts nothing.

**Resolver (phrase rule, chosen by the coordinator).**
- **Anchors** are GDD headings, run-in labels and first table cells.
- **Matching.** Every non-filler word must belong to a complete anchor phrase that appears contiguously in the reference, so no bag-of-words matching.
- **Section numbers** are locators only.

**Enforcement.**
- **Producer.** `validate_child_gdd_evidence(result, *, policy)` runs in the round-robin `_validate_candidate` (round 1, the correction, and the reviewer's revision) and in `live_decomposition`. A real-task candidate without evidence therefore fails validation and uses the existing author-correction path.
- **Consumers.** `require_committed_child_gdd_evidence(...)` rebuilds the policy from Git at the run's Source commit, as the authoritative copy. Comparison with the run's stored block is mandatory whenever the block exists. It will be wired into AssistantControl in A3b and into D1C by developer D after E commits.

**Measurement.**
- **Game repo at `886bb81` (same GDD):** 194 references, 123 distinct. The phrase rule resolves 170 (102 distinct); a looser bag-of-words rule would resolve 175. Four references resolve only under the looser rule (NSC-016, NSC-026/039, NSC-028, NSC-013), and children of those tasks can still inherit them exactly.
- **Pipeline repo:** 158 references, 149 resolve.
- **NSC-025 and NSC-014:** every reference is inheritable and also resolves.
- **Retained NSC-1165 run 4f46:** its round-1 candidate, which cited `provenance.origin`, is now rejected.

**NSC-057 (flag).** Active, `human_integration_required`, with no `gdd_evidence`. It is not decomposable anyway, because `plan_graph_delta` refuses a parent that is not `needs_execution_decomposition`.

**Tests so far (uncommitted).**
- The new module passes 17/17; 13 fail at `fce5398`, 7 of them on behaviour.
- The guidance test passes 11/11; 7 fail at `fce5398`.
- All 14 TaskDecomposition suites pass. The AssistantControl, TaskGraph and TaskReviewAgent suites are still running.

## 5. Next: two runs, which Vincent wants run in parallel

**Run 1: regression redo.** A fresh synthetic Gauntlet run with all fixes (A2, T, T2 and E) repeats what passed above and checks for regressions. It starts when E commits.

**Run 2: decompose every real game task that needs it.** Vincent wants all of them decomposed with the fixed code, and the approved proposals handed to you to integrate into main. There is a structural problem:
- **The tasks.** The five tasks are NSC-014, NSC-015, NSC-025, NSC-033 and NSC-035, all active and `needs_execution_decomposition` at game HEAD `886bb81`, and all with GDD evidence. On the Gauntlet lineage all five are `cancelled`.
- **Pipeline divergence.** `Pipeline/` differs between game HEAD and our snapshot by 283 files, +59,603/-7,823 (merge-base `73fae38`). The decomposition container runs pipeline code from the same tree it decomposes.
- **Proposed approach (feasibility check running now, no providers).**
  1. Build a scratch combined tree: our pipeline code plus the game's `Tasks/`, `Docs/GDD/` and TaskGraph state at `886bb81`.
  2. Run decomposition only (`decompose`) for the five tasks, without applying anything to the real game repository.
  3. Hand you the run artifacts and graph deltas for integration.
- **Known risks.**
  - **Exclusive resources.** `exclusive_resources` means 1:1 ownership on the Gauntlet lineage, but shared contention in canonical (the DoorPrototype scene and builder are declared by 26 tasks). The exact child-partition rule could reject honest canonical splits, or push shared work into undeclared resources.
  - **Dependencies.** Four of the five tasks depend on unfinished tasks. If decomposition admission requires delivered dependencies, only NSC-025 is decomposable today.
  - **Graph state.** Our lineage's graph and TaskControl code may refuse canonical graph state.

## 6. Questions for Codex

1. Is the direction and evidence for blockers 1, 2, 4 and 5 sufficient? Is anything missing before we call the decomposition work complete?
2. **Blocker 3 design:**
   - Is the phrase-rule resolver acceptable, given 170 of 194 real references resolve and the rest stay valid only through exact inheritance?
   - Is the synthetic classification acceptable?
   - Is the mandatory stored-block comparison acceptable?
3. **Run 2:** is a decomposition-only run on a combined tree acceptable for producing real-task proposals you will integrate? Or must the fixes be ported to canonical first?
4. **Exclusive resources:** should Run 2 keep the Gauntlet's exact partition rule for canonical tasks, or do you want the resource-kind-aware rule (every resource assigned, at most one mutating owner, other users declare a dependency) before real tasks are decomposed?
5. **Run order:** does the live test having run before A2, T, T2 and E change anything you want in Run 1?

## 7. Where things are

- **Reports** (`C:\nscrev\reports\`):
  - `codex-mid-review-blockers-20260913.md` (your blockers)
  - `mid-dev-review-revision-review-20260913.md`
  - `fix-1165-producer-agent-report.md`
  - `fix-1165-d1c-consumer-agent-report.md`
  - `fix-1165-author-guidance-agent-report.md`
  - `fix-ac-a2-advisory-needs-human-agent-report.md`
  - `fix-decomposition-timeout-triage-agent-report.md`
- **Worktrees:** A `C:\nscrev\ac-consumer-fix`, T `C:\nscrev\decomposition-slow-triage`, D `C:\nscrev\fixture-partition-fix`, E `C:\nscrev\evidence-context-fix`.
- **Please don't:**
  - modify those worktrees;
  - write under `C:\NSC`;
  - push or merge.
