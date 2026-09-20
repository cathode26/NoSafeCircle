# NSC-1163 and NSC-1165 fixes: independent verification (draft, run still in progress)

Coordinating session record, 2026-09-13. Nothing is merged or pushed. Canonical `main` is untouched. The fresh Gauntlet run's outcome and the NSC-1163 recovery proof on the old checkout root are still pending and will be appended.

## Defects (confirmed by Astra)

- **NSC-1163, P1 hang.** The crew succeeded at 13:38:32Z. The worker host's final terminal write took `checkouts.lock` with a single 10 s wait, lost it, and the host died. The launcher recorded `child_failed`, the record stayed `running` without a receipt, and the controller returned `worker_exited` as progress for about 990 wait actions. The authenticated receipt and patch survived at `<root>\.task-review-agent\NSC-1163.execution.json`. No work was lost or double-applied.
- **NSC-1165, P2 classification.** The decomposition correctly ended `needs_human`, but `decomposition._verify_review` loaded the success-only artifacts before reading `run_status`, so the job and record landed `failed` and blocked relaunch. The reviewer's finding was valid: the gates overstated what the Edit Mode tests prove.

Correction to my own earlier Astra prompt: it cited `worker_control.py` lines 102 and 140, which are stop paths. The real crash site is the final `checkouts.lock` acquisition in `crew_worker.run_worker`.

## Commits

| Fix | Commit | Branch | Worktree |
|---|---|---|---|
| NSC-1163 worker recovery | `aac2555c5b1a19d898237f8ba4e320ab3181bb9e` | `throughput/worker-recovery-fix` | `C:\nscrev\worker-recovery-fix` |
| NSC-1165 needs_human | `eb3beb75eeb8c4967594cd05877f64f86832781d` | `throughput/decomposition-needs-human-fix` | `C:\nscrev\decomp-needs-human-fix` |
| Combined proof branch | `ade5bca50d452b276a32f31a7ad8baeb770b2404` (86068e6 + f5b6ba0 + ade5bca) | `throughput/worker-and-decomposition-fixes` | `C:\nscrev\proof-fixes` |

Both fixes branch from the audited head `86068e6`, so the head Astra is re-checking did not move. Both cherry-picks were clean and byte-identical to their originals. The implementing agents' full reports are `fix-1163-worker-recovery-agent-report.md` and `fix-1165-needs-human-agent-report.md` in this folder.

## Independent failing-before, run by the coordinating session at 86068e6

| Evidence | 86068e6 | Fix |
|---|---|---|
| `test_decomposition_needs_human`, module copied byte-for-byte, no shim | Ran 19, FAILED (failures=35, errors=4), matching the agent exactly; 4 guards pass | 19 OK |
| `test_worker_recovery.DeadWorkerRoutingTests` | Ran 5, FAILED (failures=3): empty tree settles, stop request settles as stopped, active tree keeps waiting; 2 guards pass | 5 OK |
| Real-time probe, production lock constants, 12.5 s holder before the final write | timed out after the 10 s wait, record left `running` without a receipt, crew run once: the live NSC-1163 failure | succeeded in 16.7 s with the receipt, crew run once |

## Suites on the combined head `ade5bca`, sequential, tree clean afterwards

| Suite | Result |
|---|---|
| test_worker_recovery | Ran 28 tests in 240.844s, OK |
| test_decomposition_needs_human | Ran 19 tests in 109.281s, OK |
| test_crew_worker | Ran 16 tests in 146.070s, OK |
| test_worker_settlement | Ran 9 tests in 68.443s, OK |
| test_worker_launcher | Ran 12 tests in 137.924s, OK |
| test_graph_controller | Ran 33 tests in 150.902s, OK |
| test_decomposition | Ran 26 tests in 178.416s, OK |
| test_background_jobs | Ran 81 tests in 528.818s, OK |
| test_viewer | Ran 39 tests in 106.079s, FAILED (errors=1): the pre-existing `test_build_projects_timing_for_the_in_scope_task_named_by_the_controller` TypeError, identical at 86068e6 |
| gauntlet_view_smoke_test.py | Ran 148 tests in 5.829s, FAILED (failures=3): the same three pre-existing string checks as 86068e6 |
| approval_smoke_test.py | Ran 10 tests in 0.056s, OK |

## Read-only proofs against live records

- **NSC-1165.** The fixed `_needs_human_proof` classifies the exact retained run result as `needs_human`, keeping the rejection reason, finding `round-02-misstated-edit-mode-proof`, calls 2 of 2, and the latest candidate identity. The live finding fields equal the ReviewFinding contract fields exactly. The old ordering raises the production ValueError on the same inputs. The file was unchanged.
- **NSC-1163.** A bridge built with the worker's own options loads the persisted receipt, and `require("nsc-1163-20260913t133611z")` passes with identity equal to the worker record. A bridge without the worker's profiles loads nothing and refuses; a wrong crew run id refuses. The record, receipt and scope state were byte-identical afterwards.
- All 17 modules recovery depends on are byte-identical between 86068e6 and the old live project.

## Fresh Gauntlet on fixed code (in progress)

- Project `C:\NSC\GauntletFresh1160-FixesRun-20260913`, branch `gauntlet-test/fixes-ade5bca-1160`, head `5ff210375b4fc19ea9ca84de5a4fc6a424ddc828` (ff5e328 plus both fixes), checkout root `...-Checkouts`, viewer port 8820, runner v10 started 16:16:50 UTC. Same NSC-1160 to NSC-1167 family as the first run.
- **The NSC-1163 failure mode recurred and was survived.** Crew completion to terminal write: NSC-1162 26.4 s and NSC-1163 21.4 s, both landing at 16:21:13 as `succeeded` with no launcher failure. Retries are not logged, so this is inferred from timing: NSC-1168's prepare lost its own full 10 s wait at 16:20:58 and got the lock only at 16:21:13, while post-crew candidate registration for NSC-1161 and NSC-1162 held it. On 86068e6 both workers would have died after one wait.

- **The NSC-1165 failure mode recurred and was classified correctly.** NSC-1165's decomposition (run `assistant-nsc-1165-decompose-4f467687fd31`, 254 s, calls 2 of 2) ended `needs_human` with the same rejection reason as the first run, "call limit ended immediately after a revision; the latest author may not approve its own candidate", and a new valid reviewer finding, `round-02-fabricated-gauntlet-gdd-evidence` (authority_conflict): both proposed children cited `provenance.origin human_approved_synthetic_gauntlet` as GDD evidence while the committed parent records `assistant_control_local_gauntlet_replay`, and the context held no GDD evidence. Outcome on fixed code:
  - job ticket `completed`, `result_status` `needs_human`, no error (first run: `failed` with the missing-artifact ValueError);
  - decomposition record `needs_human`, `exit_code` 0, bounded facts retained, no children applied;
  - the Source-lane hold released at once: NSC-1162, held behind the proposal since 16:31:30, integrated at 16:33:43, and NSC-1166's decomposition launched at 16:34:00;
  - viewer on 8820 shows NSC-1165 as `human_action`, phase `decomposition_needs_human`, with the rejection reason and finding id, and the transition context "Independent review stopped at a human authority boundary; no children were applied."
- NSC-1163 integrated at 16:28:11, 11 min 21 s into the run; NSC-1161 at 16:25:39; NSC-1162 at 16:33:43.

## Fresh run outcome

The run ended at 16:55:07 UTC after 38.3 minutes in a single controller invocation, released with controller status `awaiting_human` because NSC-1165 is the only remaining task. The runner exited as designed.

| Measure | First run, old code | Fresh run, fixed code |
|---|---|---|
| Tasks integrated | 8, then stuck | 9, every finishable task |
| NSC-1163 | hung forever after its crew succeeded | integrated at 16:28:11 |
| NSC-1165 | background job `failed`, blocked | `needs_human`, shown as needing a person |
| Background jobs failed | 1 | 0 of 27 |
| Controller invocations | 3 | 1 |
| Lock deferrals | all recovered | 9, all recovered, at most 2 per action |

Integrations: NSC-1161 16:25:39, NSC-1163 16:28:11, NSC-1162 16:33:43, NSC-1164 16:38:17, NSC-1168 16:41:47, NSC-1169 16:44:43, NSC-1170 16:46:46, NSC-1171 16:49:07, NSC-1167 16:54:59. NSC-1166 split normally: its reviewer approved on call two, it went `review_ready` at 16:37:59, and it applied automatically at 16:38:37 into NSC-1170 and NSC-1171.

## NSC-1163 recovery proof on the original stuck run

Performed on the first run's checkout root after its old controller was stopped cleanly, with the patched controller running from `C:\nscrev\proof-fixes` (`ade5bca`) through runner v9, which changes only the control directory and expected head.

1. **Routing.** The patched controller started at 16:56:36 UTC and planned `settle_worker` for NSC-1163 at 16:56:51, where the old controller had planned `wait_worker` about 990 times. Settlement recorded exactly the dead-worker path: status `failed`, `settlement_reason` "Exited without a completed worker result", `capacity_released` true, and none of `receipt`, `crew_run_id`, `finished_at` or `error`. The controller then released with status `blocked` (NSC-1163 `worker_failed`, NSC-1165 still behind its old failed ticket).
2. **Recovery.** `recover-worker-result NSC-1163 --run-id assistant-nsc-1163-18f8332f93f9 --crew-run-id nsc-1163-20260913t133611z`, run from the verified worktree against the first run's records, exited 0 and changed the record (sha256 prefix `5e916dfd5b7fbd85` to `a96a8bd2a17596f0`). Result: `recovered` true, `recovered_from` `settled_dead_worker`, `prior_status` `failed`, `prior_settlement_reason` "Exited without a completed worker result", `worker_status` `succeeded`, `crew_status` `review_ready`, `capacity_released` true, `next_step` `post_crew`, and `provider_invoked`, `crew_rerun`, `approval_granted`, `integration_performed` all false. Its `inspect_result` authenticated crew run `nsc-1163-20260913t133611z`.
3. **Continuation.** Runner v9 relaunched (controller started 16:58:11). The patched controller launched post-crew for the recovered crew run at 16:58:23 (completed `awaiting_human` at 17:00:21), synced the candidate to the moved Source at 17:00:36, re-validated it with a second post-crew job (17:00:38 to 17:01:41), auto-approved it at 17:01:46, and **integrated NSC-1163 at 17:02:01**. The task that hung for about 990 wait cycles on the old controller reached integration from its surviving authenticated result with no provider call and no crew rerun.

## Pending

- Vincent chose a bounded third review call for the D1B.2 circuit, so that a reviewer's valid revision on call two is independently reviewed once by the other provider instead of stopping for a person. It is being implemented on branch `throughput/decomposition-revision-review` from `ade5bca`; NSC-1165 will be re-run on it.
- A likely upstream cause of both NSC-1165 stops is the author filling required fields for synthetic Gauntlet tasks with claims the context does not support (an overstated test proof; an invented GDD provenance label). Telling the author what Gauntlet children should cite is a candidate follow-up.
- NSC-1163 recovery proof on the old checkout root: patched controller settles the dead worker, then `recover-worker-result` restores the surviving result.
- Vincent's decision on `5e23243`, the stricter replay commit carried by both Gauntlet projects but not in the audited stack.
