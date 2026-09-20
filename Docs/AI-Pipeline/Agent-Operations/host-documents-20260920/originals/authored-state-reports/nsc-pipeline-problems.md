# Pipeline, viewer, Docker, GER and docs: problem list

> **AssistantControl scope (Vincent, 2026-09-17):** "Assistant Control was the idea of using a controller to process the the tasks instead of a agent. Yeah we stopped working on it because the problems are numerous so I really need a smart agent in that role."
> The 2026-09-17 architecture review called AssistantControl a large sunk cost with nothing shipped through it. Read that as the **controller and autonomy layer** being parked, not the whole subsystem: crew workers, the `.assistant-control` records, candidate and integration commands and the viewer are all in daily use. A write-off decision, if any, is Vincent's.

Written 2026-09-16 to get these fixed and make the pipeline easy to run.

**Sources:**
- the Codex orchestrator session (9/13-9/14);
- the Claude sessions of 9/15-9/16, including the demo run;
- current code and tests on `main` `22955c5a8`;
- the graph-lead journal, the reports and the memory notes.

Status was checked against `main` with read-only `git grep`/`git log` where possible.

**Status key:**
- **OPEN**: still broken on `main`.
- **PARTIAL**: partly fixed.
- **UNMERGED FIX**: a fix exists on a branch or clone, not on `main`.
- **BY DESIGN**: intended behaviour that needs docs or UX.
- **ENV**: machine or provider environment.
- **VINCENT**: needs Vincent.

---

## Top 13 to fix first (biggest win for "easy to run")

| # | Problem | Why first |
|---|---|---|
| 1 | **E13**: stale Codex automation still polling every 5 min | 1-minute fix; burning Codex quota now (VINCENT) |
| 2 | **P18**: Source is never clean (36 phantom files, Unity churn) | Blocks every `decompose` and `integrate` today |
| 3 | **V1**: approved candidates show blue or "Awaiting Instruction", never "approved" | The viewer lies about the most important state |
| 4 | **V3/V4/V5**: no single "the viewer"; wrong-root viewers show zero workers; port and receipt drift | Caused most viewer confusion; fixable with one launcher script and a banner |
| 5 | **P2**: "already implemented" tasks get rejected with no adopt path | Hit 5 real tasks; each needed a manual workaround |
| 6 | **P3**: lost final worker write wedges a task; fix built but unmerged | Silent infinite loop; a rerun destroys the result |
| 7 | **D3/D5**: decomposition `needs_human` shows as failed; no retry command | Every failed or needs-human run needs hand surgery |
| 8 | **D1/D2**: real-task splits rejected by gauntlet-only rules; better guidance unmerged | Most real decompositions failed on these |
| 9 | **G1/G2**: GER tools live only in `C:\nscrev`; marker CLI missing hold verbs | Losing `C:\nscrev` loses GER; hand-edited JSON is risky |
| 10 | **E3**: `codex`/`claude` compose services mount the real repo read-write | A container `git checkout` switched Vincent's real branch |
| 11 | **DOC1-DOC6**: three generations of contradictory run docs | Every new agent starts confused |
| 12 | **P26/P27**: several agents write `main` and share checkouts with no claim or lock | Collisions on 9/14 (NSC-074 triple session; foreign commits mid-operation) |
| 13 | **E16/G16**: provider quota runs out silently | The overnight run stopped with no alert |

---

## A. Viewer

**V1. Approved or integrating candidates never show as approved: blue, or "Awaiting Instruction".** OPEN. Pointers re-checked against `main` `7fc15c528` on 2026-09-16.
- **Fix built:** `fix/viewer-step1` commit `281d4b118` maps approved and integrating candidates to `integration_queued` on both paths.
  - Approved by an independent review on 2026-09-16; with the Game Agent for merge on Vincent's go.
  - **After merge, mark this PARTIAL, not fixed.** Workers with unverifiable host identity, decomposition records left `running`, and unexpired `working` overlays can still show blue.
  - The `integration_queued` help text at `index.html:312` still says "and human handoff".
- `integration_queued` ("Candidate Ready — Waiting for Merge Gate") is never assigned in `Pipeline/AssistantControl/viewer.py`.
- **No controller running (main today):** record status `approved` or `integrating` maps to `assistant_idle`, dark-green dashed "Awaiting Instruction" (`task_row`, `viewer.py:1011-1015`).
- **Controller `running` (gauntlet mode):** `_apply_running_controller_projection` sets `state="active"` (blue) for `has_candidate and phase in {approved, integrating}` (`viewer.py:662-671`).
- **Other ways finished work stays blue:**
  - a worker record still `running` while `host_identity_alive` is `None` (`viewer.py:1144-1149`; compare P3);
  - a decomposition record left `running` (`viewer.py:901`);
  - an unexpired `working` overlay.
- Vincent (9/16): "We shouldnt be blue, after the work is done." Which of these paths he was looking at is unconfirmed.
- An attempted fix (`4ab9336`) exists only in a throwaway clone of the rehearsal repo and is unproven.
- **Fix:** map approved/integrating/waiting-to-merge records to `integration_queued`, with a focused test.

**V2. The viewer says "blocked" while the controller says `awaiting_human`.** OPEN.
- NSC-200 showed `blocked / checkout_needs_attention` because of three hash-identical Unity churn files. `graph-plan` said `blocked: []`.
- **Fix:** derive blocked only from record or plan reasons; ignore hash-identical line-ending churn.

**V3. A viewer on any checkout root other than the live one shows every contract but zero workers, with no warning.** OPEN.
- It recurred at least three times on 9/14 ("why do I see no blue"). Many viewers were left running at once: 8817, 8818, 8820-8826, 8828, 8830-8832.
- A doc-only explanation (`codex/viewer-instructions-20260914`) is already reflected in the README.
- **Fix:** a banner showing Source and checkout root, a red warning when the root has no live worker records, and a `Start-NscViewer.ps1` that always uses the live pair on 8828 and refuses otherwise.

**V4. Default port 8813 in code; the team uses 8828.** OPEN.
- The README says both (`Pipeline/AssistantControl/README.md:78` vs `:91`). Forgetting `--port` gives a valid but "wrong" viewer.
- **Fix:** one configured port, or the launcher script.

**V5. The viewer PID receipt goes stale.** OPEN.
- `viewer-8818.json` named a dead PID.
- **Fix:** write the receipt on start, remove it on exit, and have the launcher verify it.

**V6. The viewer caches graph state; task-count changes needed a manual restart during the demo.** OPEN.
- Overlay edits do invalidate the cache (mtime); contract changes did not.
- **Fix:** include Source HEAD and `Tasks/` state in the cache key.

**V7. `/api/state` is slow or hangs (5-90 s) after a restart or heavy churn.** OPEN.
- Timeouts, `WinError 10053` traces, the page looking dead.
- **Fix:** profile the snapshot build; serve the last snapshot with a "refreshing" flag.
- **Note (2026-09-16 review):** `fix/viewer-step1` raised the `DuplicateViewerPortTests` `/api/state` timeout from 5 s to 30 s, which hides this slowness in tests.

**V8. Purple "Task Unstarted" means three things.** BY DESIGN, needs UX.
- It can mean never started; contract revision changed since delivery (NSC-023, `needs_replan`); or, since the 9/15 hold clearing, blocked on a design decision (NSC-007, 008, 009, 030, 078, 085, 088).
- **Fix:** a distinct "needs decision" overlay or colour and a distinct `needs_replan` style.

**V9. The GER marker CLI has no `hold` or "unhold without release" verb.** PARTIAL.
- This forced a raw JSON hand-edit on 9/15.
- Helper `C:\NSC\tools\ger\hold_ger_task.py` added 2026-09-16 (outside git; tested on a copy).
- **Fix:** add `hold`/`unhold` to `Pipeline/TaskDesignGER/ger_viewer_marker.py` with tests.
- **Built:** `fix/viewer-step1` commit `2e76ab22d` (approved 2026-09-16, awaiting merge).
- **Remaining gap:** `hold` and `finish --ready-child` accept task IDs that aren't committed tasks (`ger_viewer_marker.py:50`). The viewer page then fails with "Held task overlay names unknown task IDs" until someone runs `unhold`. `nsc_viewer.py` checks IDs; the in-repo CLI doesn't.

**V10. Non-crew work (PixelLab, hand-run Unity) is invisible unless someone hand-edits `external-work-ids.json` with expiry times.** OPEN.
- Dozens of manual edits on 9/14. The BOM pitfall broke one write.
- **Fix:** a CLI such as `mark-external-work TASK --minutes N --description ...`.

**V11. Background-job waits and source-lane holds are never shown.** OPEN.
- `wait_job` is not projected (`CURRENT.md` says so).
- `held[]` `decomposition_proposal_in_flight` appears only in `graph-plan`; Vincent thought commits were stuck.
- **Fix:** project both as a visible "waiting on X" state.

**V12. A task blocked by a failed background job with no task record shows `ready`, and so do its dependents.** OPEN/UNKNOWN (seen in gauntlet trial 1140).

**V13. Run-detail rows always read "Unavailable".** OPEN, cosmetic.
- "Uncommitted local build SHA-256" and "GitHub repository" read "Unavailable" in assistant mode (`index.html:870-897`).
- A 9/16 fix attempt was abandoned.
- **Fix:** hide rows whose value is null.
- **Built:** `fix/viewer-step1` commit `d41170774` (approved 2026-09-16, awaiting merge).

**V14. The page title "NSC Gauntlet Graph" also appears for the real project.** OPEN, cosmetic.
- **Built:** `fix/viewer-step1` commit `3a72777b5` ("No Safe Circle Task Graph"; approved 2026-09-16, awaiting merge).

**V15. No CLI scope filter.** OPEN.
- `viewer` accepts only `--port`, so `--task` (in old notes) is rejected. Scope comes only from a `graph-controller.json` in preflight or running status plus the "run scope only" checkbox.
- In the demo this nearly led to deleting 92 real tasks "to hide them".
- **Fix:** a `--task`/scope file for display only.

**V16. Two server backends serve the same `index.html`.** OPEN.
- `Pipeline/AssistantControl/viewer.py` handles assistant mode; `Pipeline/TaskReviewAgent/GauntletView/server.py` handles production and local rehearsal.
- An hour on 9/16 went into debugging `server.py`, which is never reached in assistant mode.
- `GauntletView/README.md` documents the legacy product and points at `C:\NSC\nsc-gauntlet-view` outside the repo.
- **Fix:** doc banner in both, or retire the legacy server.

**V17. `GauntletView/server.py` still uses a plain `ThreadingHTTPServer`.** OPEN.
- On Windows two processes can share its port silently (`server.py:4876`).
- The AssistantControl viewer was fixed with `SO_EXCLUSIVEADDRUSE`.

**V18. Viewer tests are red for fixture reasons.** OPEN.
- `Pipeline.AssistantControl.test_viewer`: **37/57 pass**. 20 fail because the shared fixture (`test_inspect_project.py:29-33`) commits a pre-schema-v2 task.
- One timing test hits a `TypeError: None >= 42.0`.
- GauntletView smoke: 175/176 (the `f-scope` default-checked expectation).
- A repair (`c12f702`, `C:\NSC\AssistantControlViewerRegression-20260913`) was never merged. It looks lost; branch `assistant/viewer-regression-suite-20260913` no longer exists.
- **Built:** `fix/viewer-step1` commit `2afc30596` ports it.
  - `test_viewer` goes to 68/68 and the GauntletView smoke tests to 176/176, both re-run by the reviewer. Approved 2026-09-16, awaiting merge.
  - Review note: the new timing test pins `total_elapsed_seconds == 0.0`, and the report's `None >= 42.0` explanation is unproven.
- **Still red, separate fixture bug:** `Pipeline/AssistantControl/test_completion_workflow.py` raises `StopIteration` from the `CandidateRecoveryTests` fixture in `test_candidate.py`. See also P36.
- **Fix:** update the fixture to schema v2; guard the timing assertion.

---

## B. Task execution pipeline (AssistantControl / ExecutionCrew)

**P1. The main project has no automatic dispatch.** BY DESIGN for now.
- `taskcontrol ready`/`authorize` are disabled and `run-graph` is retired for main, so an agent hand-drives every select, launch, post-crew, review and integrate.
- On 9/14 the orchestrator did this for about 9 hours.
- Vincent's goal is to later run main in "gauntlet mode" (FUT1).

**P2. "Already implemented" tasks are rejected (`role made no required file modification`), with no way to adopt existing code.** OPEN.
- Hit NSC-003, 005, 038, 040 and 069. `run_crew.py:679` rejects.
- No revalidate or adopt subcommand exists in `__main__.py`.
- **Fix:** an `adopt-existing TASK` command that runs the task's focused validation on the unchanged commit and registers it as a candidate for Vincent's review.

**P3. A lost final worker write wedges a task forever.** UNMERGED FIX.
- `crew_worker.run_worker` makes one 10 s `checkouts.lock` attempt, outside its `try`.
- The record stays `running` and the controller loops (about 990 cycles, NSC-1163). Rerunning the crew overwrites the only receipt.
- Fix `aac2555c` (bounded retry plus `recover-worker-result`) is proven live but absent from `main`.
- **Fix:** port it.

**P4. `materialize_candidate` holds `checkouts.lock` for the whole Unity build and validation (up to 30+ min).** OPEN.
- It blocks every other checkout-root action. Documented in `CURRENT.md`.
- **Fix:** a reviewed lock-order change.

**P5. Lock contention.** PARTIAL.
- Base action deferral is on `main` (`01112057d`, `LOCK_DEFERRABLE_ACTION_KINDS`).
- The harvest, cleanup and startup follow-up (`b42d5197`) is unconfirmed.
- The harvest-gate and policy re-pin parts of the throughput stack (`86068e6` line) are absent.

**P6. `post-crew` needs the crew's own run id, not the launch run id.** OPEN.
- Error: "ExecutionCrew receipt was not authenticated".
- **Fix:** accept the launch run id and look up `worker.crew_run_id`.

**P7. `readiness`/`reserve` default to `--capacity 1`, silently.** OPEN.
- Only one worker ran when three were intended.
- **Fix:** configurable default of 3, or print the capacity used.

**P8. Invalid worker-config pairings are accepted until launch.** OPEN.
- `crew_profile: full` + `validation_profile: targeted` exits immediately.
- **Fix:** validate at `reserve`/`start-worker`.

**P9. New and decomposed tasks lack authoritative validation policy entries.** PARTIAL.
- They land `awaiting_human` with `not_run`. The misclassification as "focused tests failed" was fixed (`65ff86439`).
- **Fix:** a generator or checklist so new tasks get a policy entry.

**P10. Unity-generated `.meta` files outside the scope boundary break materialization and clean-tree checks.** OPEN.
- Examples: NSC-032 `Enemies.meta`, NSC-050 validation copy, 177 PixelLab metas.
- Recovery commands are NSC-032-specific.
- **Fix:** a generic `.meta`-companion policy and a generic recovery command.

**P11. Task-specific one-off tools in the shared CLI.** OPEN.
- `recover-nsc032-materialization`, `refresh-nsc032-recovered-index`, `recover-nsc032-missing-validation-policy`, plus bespoke scripts (`ca298253` Issue migration, `nsc014_apply_approved.py`).
- **Fix:** generalize or retire them.

**P12. Stale preserved checkouts pinned to an old Source can't resume.** PARTIAL.
- `4ad1d1f82` handles clean, unleased checkouts; others need manual paths.

**P13. Batch approvals get silently discarded.** OPEN.
- When one candidate integrates, the others are synced to **new SHAs** and approvals bound to the old SHAs are dropped with no warning.
- The job record shows `completed` with null timestamps.
- **Fix:** record and surface "approval superseded by sync"; enforce one approval at a time.

**P14. Gauntlet mode: preflight and run policy must match byte for byte.** OPEN.
- The error doesn't name the mismatched field. No hot policy change without relaunch, which kills in-flight decomposition.
- **Fix:** diff fields in the error; offer a combined preflight-and-run command.

**P15. `--auto-approve-gauntlet` only works for tasks with synthetic-gauntlet `provenance`.** BY DESIGN.
- Cloned tasks never qualify. Relevant when main moves to gauntlet mode: real tasks will always stop for Vincent.

**P16. Global-flag ordering trap.** OPEN.
- `--source`/`--checkout-root` after the subcommand gives the misleading "Specify --checkout-root outside the source project".
- **Fix:** accept them in either position, or give a clear error.

**P17. `decompose` and similar commands exit 0 when they print `command_failed`.** OPEN.
- **Fix:** nonzero exit.

**P18. The Source is almost never clean.** OPEN, VINCENT.
- Unity and GitHub Desktop churn line endings. 36 wizard and tile assets on `main` show modified with identical content.
- `git checkout --`, `update-index --refresh` and `safe_unity_churn.py` don't clear them. The safe-churn allowlist covers only three `ProjectSettings` files.
- `decompose` and `integrate` refuse a dirty Source.
- **Fix:**
  1. Decide with Vincent on a one-time renormalization commit (`git add --renormalize` for those paths) and `.gitattributes` rules for Unity YAML.
  2. Extend `safe_unity_churn.py` to hash-identical generated assets.

**P19. `taskcontrol state` reads only the committed tree, without warning.** BY DESIGN, needs a warning.
- Uncommitted new tasks read "Unknown task"; deleted evidence still counts.

**P20. `taskcontrol validate` refuses removing any bootstrap-baseline task file.** BY DESIGN, undocumented.

**P21. `taskcontrol.py list --status open` fails.** OPEN, minor. The flag values don't match what was tried.

**P22. Delivery evidence packaging is fragile.** OPEN.
- `record_delivery.py` rejects Unity logs with trailing whitespace and self-referential artifact paths; the runner doesn't normalize its logs.
- **Fix:** normalize in `run_unity_tests_clean.ps1`.

**P23. Unity `-quit` with `-runTests` exits 0 with no XML (a false pass) in hand-written commands.** OPEN (docs and wrapper). It happened four times on 9/14.

**P24. Document-only task kinds are undispatchable by the worker route.** OPEN. Example: NSC-059.

**P25. Paid crews run on tasks whose files already exist, then are rejected.** OPEN.
- **Fix:** a pre-flight check of `exclusive_resources` existence and content.

**P26. No per-checkout claim.** OPEN.
- Two or three agent sessions worked in `NSC-074-current` at once on 9/14, with duplicate paid PixelLab jobs. Two Haiku sessions hit NSC-063.
- **Fix:** a claim file checked by agents and launchers.

**P27. Several agents write local `main` with only ad hoc checks.** OPEN.
- Writers: the Task, GER and Decomposition Orchestrators and the branch-recovery session.
- Foreign commits appeared mid-operation on 9/14.
- The Source integration lock covers only `integrate`/`sync-candidate`/`apply-decomposition`, not GER contract commits or branch merges.
- **Fix:** one shared "main writer" lock or queue that the GER tools and merge scripts also take.

**P28. No CLI hold for tasks.** OPEN.
- "Unavailable" is a journal convention agents must re-read before each start. `held-task-ids.json` is display-only.
- **Fix:** hold records that `readiness`/`reserve` honor.

**P29. Legacy GitHub-Issue lifecycle collisions.** OPEN.
- `launcher_preflight.py` refused NSC-089 over an unrelated closed Issue's label.
- `Start-GameTaskAgent.ps1 -DirectManual` nearly auto-pushed.
- Stale Issue leases need bespoke migrations.
- **Fix:** keep the main project off the legacy Issue path, and say so in the docs.

**P30. Capacity is counted per Source (`.git\assistant-control-admissions.json`), not per checkout root.** BY DESIGN, undocumented. A stale reservation from another root eats slots.

**P31. Different checkouts run different CLI vintages with no version banner.** OPEN.
- `TenTaskFinalIntegration-20260905` has no `graph-preflight` and no `--background-jobs`.

**P32. Audit gates.** PARTIAL.
- Too many blocking audits: "I need 20 audits before you can run a task." The paid `contract_locality_auditor` and the exact new-file gate were removed or loosened on `main` (`8b84f1af7`).
- `ExecutionCrew/README.md` still lists the auditor.

**P34. Pipeline stub `.meta` files import as cubemaps.** FIXED 2026-09-17: merge `e1ce889b0` (fix/stub-meta-texture @ `412e5f4b4`; report `C:\nscrev\reports\stub-meta-texture-fix-report.md`). Found 2026-09-16 by the branch-recovery session.
- **What changed:**
  - `unity_meta_bytes` writes Unity 6000.1's default TextureImporter meta for LDR textures (same GUID; sha256 pinned in tests), and a Unity import check passed;
  - a human-review retry refreshes sidecars when it applies the prior candidate;
  - a retry of a candidate committed with stale sidecars stops and names the file to fix;
  - after the conformant meta is committed, the retry resumes.
- **Takes effect:** only for newly prepared crew checkouts.
- **Unchanged:** HDR textures (`.exr`, `.hdr`) and other importer types still get the two-line stub, as a follow-up. `DoorPrototypeGlobalSceneBuilder`'s wizard workaround stays.
- `Pipeline/ExecutionCrew/run_crew.py` `unity_meta_bytes` writes GUID-only `.meta` files.
- In Unity 6000.1.8f1 such PNGs import as `textureShape: 2` (Cube) with a point-light cookie and gamma decoding, not Texture2D. Unity never rewrites the stub, so tests stay green until a builder needs a Sprite.
- It broke NSC-075's builder: "Wizard source did not import as a Sprite".
- The NSC-075 stack works around it (`0d28b0bf5`, which sets `textureShape` and resets the cookie and gamma fields).
- **Fix:** write full importer metas in the pipeline, or normalize in every art-importing builder. Check staged art with `grep textureShape` on its metas.

**P35. Archiving successful tasks is half-tooled.** OPEN.
- Vincent's rule (9/16): keep every NSC-### branch, and archive conformant tasks as usable projects in `C:\NSC\SuccessfullTasks\<TASK-ID>`.
- Only NSC-042 is archived (with `Library`), while 15 tasks are conformant.
- `preserve-success` needs AssistantControl approved and integrated records and skips `Library`. Tasks landed by branch merge have no such records, so the command refuses.
- **Fix:** an `archive-successful NSC-###` command that reads the DEL record's integrated commit, clones on the task branch, copies a warm `Library`, and never overwrites.

**P37. `execution_crew_smoke_test` stops partway (line 335), and pre-existing red tests have no owner.** OPEN. Reported 2026-09-16 by the Pipeline Maintainer Agent.
- Red suites hide real coverage: this one, the 3 GauntletView modules broken by P36, and the `test_completion_workflow` fixture bug (V18 note).
- **Fix:** the Pipeline Maintainer Agent owns pre-existing test debt, working through it weekly with a pipeline-maintainer subagent, one suite per branch.

**P36. `Pipeline/TaskReviewAgent/local_rehearsal.py` is missing from the repo.** OPEN. Found 2026-09-16 by the viewer-step1 Pipeline Maintainer run.
- The module is imported but not in git on `main` `7fc15c528`.
- It breaks 3 GauntletView test modules and one test in `Pipeline/AssistantControl/test_completion_workflow.py`, identically on the base commit.
- It likely matters only to the legacy local-rehearsal viewer modes (V16), but the tests stay red until it's resolved.
- **Fix:** find where the module went (git history, rehearsal clones under `C:\nscrev`). Restore it, or remove the dead imports and their tests if local rehearsal is retired. Owner: the Pipeline Maintainer Agent.

**P33. NSC-042 tile matcher (game test gap).** OPEN.
- `ArchitecturalTileVisualMatches` compares size and pivot only, never pixels, so a half-fixed seam passes every automated gate. It was seen again on 9/16 (NSC-200).

---

## C. Decomposition

**D1. The exact-partition rule rejects legitimate real-task splits.** OPEN.
- `Pipeline/TaskDecomposition/policy.py:147` requires children's `exclusive_resources` to exactly partition the parent's.
- That is correct for the synthetic gauntlet's 1:1 ownership, but real tasks share contention tokens (up to 26 tasks on one file) and children need new files. 7 of 9 real drafts broke this or a related rule.
- **Fix:** Fable's 9/12 real-task rule. Every parent resource is owned by at least one child; children may share a real contention boundary and add needed new files.

**D2. Better decomposer and reviewer guidance is unmerged.** UNMERGED FIX.
- Coverage mapping, candidate-wide rules, "tests must run the production path", and `.asmdef` edit authority are on `codex/coverage-mapping-guidance-20260913` (`616ca980`..`c6f7981a`), Astra-approved for research only.

**D3. `needs_human` is reported as `failed`.** UNMERGED FIX.
- `decomposition._verify_review` checks artifacts before `run_status`. There are zero `needs_human` references in the AssistantControl consumer.
- Fix `eb3beb75` is proven live but unmerged.

**D4. The container timeout is a flat 3600 s.** UNMERGED FIX.
- `decomposition.py:423`; `graph_controller.py:77` waits 3780 s. Valid slow runs exceed it and fail permanently, with no alert.
- Fix `008d1df` (derived budgets and a `decomposition_slow` event) is unmerged.

**D5. No retry path.** OPEN.
- Any existing `<TASK>.decomposition.json`, even `failed`, blocks a new `decompose` ("record already exists ... preserved"), and there is no CLI to archive it.
- NSC-015 is blocked this way today.
- **Fix:** `archive-decomposition TASK --run-id ID` that moves the record aside with an audit entry.

**D6. Recursive decomposition is not on `main`.** UNMERGED FIX.
- Children must be `single_agent` (`policy.py:117`, `schemas.py:57`). The recursive change was built on 9/14 (`codex/recursive-decomposition-20260914`) but `main` doesn't have it.
- **Fix:** port it with tests.

**D7. The revision-review third call was proven but never merged.** UNMERGED FIX.
- Author, then reviewer revise, then one independent revision review, so valid-but-revised splits don't dead-end.
- NSC-1165 split automatically, about 20 min; head `4fd54b8c` in `C:\nscrev\final-integration`.

**D8. New single-owner files are not reserved by resource groups** (the "B2" gap). OPEN.
- Two tasks could plan to create the same new file.

**D9. Proposals don't reserve child IDs.** BY DESIGN, documented. Apply one proposal, then replan the others; the ordering is manual.

**D10. Two decomposition entry points, and no doc says which to use.** OPEN.
- AssistantControl `decompose` uses project `nosafecircle` volumes. `Pipeline/TaskDecomposition/run_round_robin_decomposition.py` via `-p nosafecircle-m2a` uses different credential volumes.
- `GRAPH_TEAM_STARTUP.md` never mentions decomposition.

**D11. Paid launches need Vincent's live go every time.** BY DESIGN.
- The classifier refuses from subagents, and once from the main session. Documented in the Decomposition guide.

**D12. The two-provider design has no fallback when one provider is out of quota mid-run.** OPEN. Three real decompositions stalled at round 2 on 9/13.

**D13. `decomposition_authorization.py` (legacy Issue path) refuses a corrected three-round shape.** UNKNOWN.

**D14. Throughput stack landed only partly.** PARTIAL. The policy re-pin and harvest-gate blockers from Astra round 6 are absent. Decide whether to finish or drop them.

---

## D. GER

**G1. The GER round and commit toolchain exists only in `C:\NSC\tools\ger\`.** OPEN.
- Not in git: `ger_node.py`, `ger_round.py`, `ger_patch.py`, `apply_contract.py`, `ger_decision_revision.py`, `apply_followup_revision.py`, `contract_commit.py` (G15, 2026-09-17), `watch_issue.py`, and the new `hold_ger_task.py`.
- There are 13 `*.bak.py` files and a stale `next\` copy.
- **Fix:** port into `Pipeline/TaskDesignGER/` with smoke tests (`GER_AUTOMATION.md` already recommends this).

**G2. Workspace trust stalls non-interactive rounds.** OPEN, ENV.
- `claude -p` in a new folder (snapshot, worktree) hangs on the trust prompt. A GER round stalled for 30 min unnoticed.
- **Fix:** pre-trust the snapshot root, or run with a trusted parent.

**G3. Resume refuses a changed addendum or context and pins the old snapshot.** BY DESIGN. A new design input needs a fresh packet.

**G4. A failed round must be renamed `.failed-<UTC>` by hand before retry.** OPEN, toil. `ger_round.py:538` refuses existing directories; `--retry-transient-failure` doesn't cover quota.

**G5. Round recommendations are parsed from free text.** OPEN.
- A parser bug on 9/14 read "needs_design ... could recommend commit_contract" as `commit_contract`. It was fixed, but the channel is fragile.
- **Fix:** structured recommendation output.

**G6. Packet hash "mismatches" on GDD and art-direction files.** BY DESIGN (Vincent chose not to fix). CRLF vs LF makes every reviewer re-explain it.

**G7. Re-audits keep asking for single-owner resource groups the validator doesn't want.** OPEN. Prompt fix.

**G8. NSC-015 fell out of hold and release tracking in the 9/15 resync.** OPEN.
- Its decomposition then ran and failed (revise); the state is recorded in the Decomposition guide.

**G9. Parallel contract authors drift on shared conventions.** PROCESS.
- On 9/15: Tilemap names, offsets, collider names. A harmonizing pass fixed it.

**G10. Reference projects are documented but not wired.** OPEN.
- `Pipeline/ReferenceSources/reference_sources.json` points at non-existent `C:\UnityProjects\...`; the real SpaceInvaders is at `C:\NSC\SpaceInvaders`. No `/reference` mount.
- Vincent: "I said many times to use the space invaders as an example."
- **Fix:** point it at the real path and add it to GER addenda.

**G11. "GER" names two unrelated systems.** OPEN (docs).
- `Assignment6GER/` (Docker, implementation content) vs `Pipeline/TaskDesignGER/` (host, contract review).

**G12. GER artifacts pile up in Downloads.** OPEN, minor. 60+ packets, many superseded, with no retention policy.

**G13. GER scope had to be re-stated repeatedly.** PROCESS.
- "All tasks, not just rooms" was repeated six times on 9/14. GER was wrongly described to Claude as "review-only". The GER Orchestrator guide now states both.

**G14. Codex↔Claude handoff runs through GitHub issue #127 and a polling script.** PROCESS, ad hoc. Decide whether to keep it.

**G15. The GER commit tools don't fit the 2026-09-17 contract check.** FIXED 2026-09-17: installed in `C:\NSC\tools\ger` after three approved review rounds. The tools are `apply_followup_revision.py --reviewer`, the new `contract_commit.py`, and post-commit check flags. Report: `C:\nscrev\reports\g15-ger-followup-tools-report.md`. The GER guide update is with the Documentation Agent.
- **The process:** commits are never blocked. Design revisions get one Codex buildability check right after commit, and the verdict must be seen before a crew starts (`nsc-ger-orchestrator-guide.md`, "The contract check").
- `apply_followup_revision.py` labels every review "independent Claude Sonnet re-check". It needs a `--reviewer` label.
- The supported path for commits with no review is a one-off script, `C:\nscrev\ger-contract-revisions-20260916\runbook_contract_commit.py` (`review: none`, supports `superseded_by`). Fold it into `C:\NSC\tools\ger` with tests.
- Optional: let a later revision's provenance record a post-commit Codex check.
- **Agreed plan (Pipeline Maintainer Agent, 2026-09-17):**
  1. `apply_followup_revision.py` keeps `--report` required and gains `--reviewer`.
  2. `runbook_contract_commit.py` becomes a supported `ger-tools` committer for any validated revision with `review: none` (design revisions, `superseded_by`, disposition).
  3. Optional post-commit Codex check fields (report path, sha256, verdict, checked commit) can go in a later revision's provenance.
  4. No `--mechanical` mode.
  - The final flags come to the Documentation Agent at install, to update the GER guide.
- The owner revisions committed on 2026-09-16 (NSC-077 rev 3, NSC-055 rev 3, NSC-015 rev 7) are getting Codex retro-checks from the GER Agent.

**G16. No lookup of which tasks reference a given task, and no record of code landing outside the graph.** OPEN. Reported by the GER Agent 2026-09-16.
- Cascades are found by grep: superseding NSC-094 forced the NSC-015 and NSC-055 revisions.
- Code committed without a task (playable build `9a3d22c56`: a DemoRunFlow fireball, a 9-enemy squad, a stationary fire caster) forced a fresh research pass before every decision.
- **Fix ideas:** a `taskcontrol references NSC-###` command, and a journal section or tag listing task-less code commits.

---

## E. Docker and environment

**E1. No documented Claude Docker login in the repo.** OPEN (docs).
- Only the Codex device auth is in `Pipeline/ArchitectureReview/README.md`.
- The runbook section 3.3 now has Vincent's verified commands: `docker compose -p nosafecircle run --rm claude claude auth status --text` and `claude auth login`.

**E2. About 313 images (151 one-off `assistant-crew-*`), 47 volumes and 257 build-cache entries.** OPEN.
- About 3 GB reclaimable each, with no cleanup procedure and no guidance on which volumes are live credentials.

**E3. The plain `codex`/`claude` compose services mount the real repo read-write.** OPEN.
- A `git checkout` inside the container switched Vincent's real `main` checkout (9/15).
- Those services don't set `core.autocrlf`, so git inside sees 1,744 phantom changes.
- **Fix:** run bulk jobs in clones or the `:ro` services; add `GIT_CONFIG_*` to those services.

**E4. Docker Desktop mount-path ownership check is raw string equality.** UNMERGED FIX.
- `docker_workers.py` can reject a legitimately owned container over Windows path formats. Fix `8d8ae6cd0` is in `C:\NSC\NoSafeCircle-AssistantControl-SpeedIntegration` only.

**E5. Only one Unity may run at a time on this host.** ENV. Every validation serializes on the "Unity slot"; throughput is capped.

**E6. Unity licensing exit 199 or "readonly database" under a sandboxed identity.** ENV. Rerun as the normal user.

**E7. Some packages need a one-time GUI setup.** ENV. DOTween did; it blocks fully headless runs.

**E8. Git for Windows "couldn't create signal pipe" on fresh clones.** ENV. Intermittent; escalate, don't loop.

**E9. PowerShell traps.** ENV, docs.
- `-Encoding UTF8` writes a BOM that breaks JSON.
- Smart quotes break `gh` bodies.
- PowerShell 5.1 has case-insensitive variables.
- Claude permission prompts stall on commands over about 1 KB.
- Long Bash heredocs can silently run nothing.

**E10. Hibernation pauses runs; everything is bound to the local machine.** ENV.

**E11. Three regression suites write temp dirs straight under `C:\NSC`, with no override.** OPEN.
- `local_candidate_source_integration_test`, `local_source_wait_completion_test`, `immutable_crew_manifest_test`.

**E12. The credential copy between volumes is blocked by the classifier.** BY DESIGN. Design diagnostics around it.

**E13. The Codex desktop automation "Poll Gauntlet repair board" is still ACTIVE.** OPEN, VINCENT.
- It runs every 5 min against archived issue #142 and was still writing `C:\NSC\GauntletRecoveryAuditEvidence-20260909\github-poll-state.json` on 9/16, spending quota.
- **Fix:** tell Codex "Use automation_update to set the automation with id poll-gauntlet-repair-board to status PAUSED."

**E14. Provider hiccups.** ENV.
- PixelLab OAuth expiry, a self-signed certificate error, and Claude or Codex session limits have each killed sessions.

**E15. Stale processes from old runs linger.** OPEN. Viewers on 8817, 8830-8832, and so on.

**E16. Quota exhaustion is silent.** OPEN.
- On 9/14 Codex hit 100% at 14:29Z. The 20-minute heartbeat kept firing empty turns for 80 minutes with no alert to Vincent.
- **Fix:** orchestrators check quota before batches and notify on provider-limit errors.

**E17. The watch tool sees only the host Codex account.** OPEN. Reported by the Game Agent 2026-09-17; handed to the Pipeline Maintainer (board H-20260917-03).
- `nsc_watch.py` reads quota from host rollouts only. Docker jobs use the `nosafecircle_codex-config` volume login, which may be a different account, so the 90% pause rule is ambiguous for them.
- On 2026-09-17 three host jobs failed with 401 while the login file was being rewritten.
- **Fix:**
  - report quota per account (host and volume);
  - add a login-status check for both, using `codex login status` and, for the volume, `docker compose -p nosafecircle run --rm -T codex codex login status` from a clone;
  - alert on logged-out or high quota.

---

## F. Docs and process

**DOC1. Three generations of "how to run" docs coexist with no retirement notices.** OPEN.
1. `NscRun.cmd`, TaskReviewAgent scheduler, port 8813, `C:\NSC\TenTaskFinalIntegration-20260905`, the GitHub-Issue human PASS path.
2. The `graph-preflight`/`run-graph` controller with Opus/Sonnet/Haiku staffing guides.
3. The three-agent conversational team (current).

**DOC2. `Docs/AI-Pipeline/START_HERE.md` ("the first file any AI assistant should read") is from 8/26.** OPEN. It never mentions AssistantControl, the viewer, Docker or GER.

**DOC3. `Pipeline/AssistantControl/CURRENT.md` is stale.** OPEN. The README calls it "a short handoff", but it describes `TenTaskFinalIntegration-20260905`. `STATUS.md` is historical.

**DOC4. `Pipeline/AssistantControl/README.md` mixes current per-task commands with the retired "Bounded graph controller" section without an inline marker.** OPEN. Examples hard-code TenTaskFinalIntegration.

**DOC5. Startup scripts contradict the retirement.** OPEN.
- `CodexGraphTeamStartup.ps1:29` and `Check-ClaudeGraphTeamStartup.ps1:53` print "sole normal run-graph authority", contradicting `GRAPH_TEAM_STARTUP.md`.

**DOC6. `GRAPH_TEAM_STARTUP.md` has no decomposition or GER sections.** OPEN. The two decomposition entry points aren't reconciled.

**DOC7. `ExecutionCrew/README.md` "full" profile still lists the removed Contract Locality Auditor.** OPEN.

**DOC8. `GauntletView/README.md` documents the legacy viewer and an out-of-repo path.** OPEN.

**DOC9. Checkout path conventions conflict.** OPEN.
- `Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md` mandates `C:\NSC\NSC\<TASK-ID>` and forbids `NoSafeCircle-NSC...` names.
- AssistantControl uses `<root>\<TASK-ID>`, and ad hoc worktrees use the forbidden style.

**DOC10. Staffing is documented three different ways, and none matches practice.** PARTIAL.
- The new Task, GER and Decomposition Orchestrator guides (`C:\NSC\nsc-*-guide.md`) describe the model Vincent asked for on 9/16; they still need a home in the repo.

**DOC11. Runbooks pin commits and go stale within hours.** PROCESS.
- Two runner scripts once targeted the same checkout root.
- Memory notes also go stale: `ger-queue-state.md` says 22 holds (now 0); the viewer-fix note says "not merged" (it is merged); "Codex out until Sep 19" was the old account.

**DOC12. Handoffs lose the operating model.** PROCESS.
- On 9/14 the new orchestrator rebuilt the retired controller workflow from docs ("slight confusion on how the project is supposed to run"). A terse context-free handoff to a fresh Claude was refused as a possible injection.
- **Fix:** complete, self-contained handoff prompts that point to these guides.

**DOC13. Overloaded words.** PROCESS.
- "Scene" meant graph state vs a Unity `.unity` file and cost 40 min on 9/16. Brown "Task Retired" is used for GER in progress. "Gauntlet" means both the test harness and the mode.

**DOC14. Stale branches inflate the apparent pending work.** OPEN.
- 9 of 12 viewer, pipeline and doc branches checked are already on `main` in substance: `codex/viewer-instructions`, `ger-held-viewer`, `ger-active-viewer`, `viewer-held-overlay`, `assistant/viewer-external-active`, `codex/remove-blocking-audits`, `parallel-scene-reservation`, `missing-validation-policy-review`, and `docs/ger-agent-runbook` (superseded).
- About 118 local branches are unmerged overall; the branch-recovery session is working through them.

**DOC15. `compose.yaml` services are documented piecemeal across three READMEs.** OPEN. The runbook section 1 summarizes them.

**DOC16. Status reports are too long, and sometimes claim progress that hadn't happened.** PROCESS. The guides require short, verified reports.

---

## G. Later work Vincent has asked about

**FUT1. Retire the gauntlet; run the main project in gauntlet mode** (`graph-preflight` + `run-graph` + viewer).
- Prerequisites from this list:
  - V1, V3, V11;
  - P2, P3, P4, P13, P14, P28;
  - D1, D3, D4, D5, D6;
  - E3, E16;
  - a decided policy for which real tasks may auto-advance and which stop for Vincent.
- The gauntlet harness (`prepare_synthetic_gauntlet.py`, synthetic task families, `GauntletTests.cs`) can then be removed. It is all-or-nothing and needs a three-file lockstep to add a task.

**FUT2. A documentation RAG.**
- `Pipeline/GDDRAG` is deterministic lexical retrieval over **one hard-coded file**: the GDD, 78 chunks, `gddctl rebuild|validate|search`, SHA-bound freshness.
- Generalizing it is moderate work, not a rewrite:
  - a source-file list or glob instead of `CANONICAL_GDD_PATH`;
  - per-file hashes;
  - file-namespaced chunk IDs;
  - per-file freshness in `status`/`validate`;
  - a per-corpus regression baseline.
- **Do DOC1-DOC9 first**: a RAG over contradictory stale docs retrieves the stale answer. Index only the current set, with historical docs excluded or tagged.

**FUT3. Agent definitions for the Task, GER and Decomposition Orchestrators**, pointing at the guides.
- For example `~/.claude/agents/*.md`, or Codex prompts.
- Move the guides into the repo, for example `Docs/AI-Pipeline/agents/`.
- **Started 2026-09-16:** custom agents in `C:\Users\VincentLiguori\.claude\agents\`:
  - `art-director.md`, which carries the art bible;
  - `pipeline-maintainer.md`, the rules for the Pipeline Maintainer Agent session;
  - `pipeline-reviewer.md`, the fresh Opus reviewer for pipeline fixes.
  - The orchestrators are still prompts only.
  - Who runs as which session: `C:\NSC\nsc-agent-directory.md`.

**FUT5. Generic Codex jobs with adversarial review.** Handed to the Pipeline Maintainer Agent 2026-09-16.
- Vincent: "have codex do tasks for us which will include adversarial review. We want codex to verify our work through the pipeline. IT should support generic tasks."
- Also for easy work, to spare Claude tokens.
- Spec: `C:\nscrev\reports\handoffs\pipeline-maintainer-codex-jobs-and-mixed-crews-brief-20260916.md` (Feature A).
- Interim manual recipes and templates: `C:\NSC\nsc-codex-jobs-guide.md`, section 4; `C:\nscrev\codex-jobs\templates\`.

**FUT6. Mixed crews as the Game Agent's default.** Handed to the Pipeline Maintainer Agent 2026-09-16 as "verify and enable".
- Vincent: "When our game agent does pipeline work, we want to prefer a mixed agent pipeline."
- **The mixed profiles already exist:** `claude-architect-balanced` and `codex-architect-balanced` in `Pipeline/TaskReviewAgent/provider_profiles.py`. The validator runs on the provider opposite the implementer.
- AssistantControl worker configs accept `provider_profile`, but the live configs don't set it.
- **Checked 2026-09-16 by the Pipeline Maintainer Agent** (`C:\nscrev\reports\mixed-provider-crews-verify-report.md`): it does not work through AssistantControl.
  - The profile string reaches `ExecutionCrewBridge` unexpanded, because `expand_profile` is only called in the legacy `run_autonomous_graph.py`.
  - Worker and candidate records carry no per-role provider.
  - `viewer.py` doesn't feed the per-role display that `index.html` already has.
  - **Fix (small):** expand the exact named profile in `crew_worker` and `candidate`, the way `run_autonomous_graph.py:240` does; ship an example config; wire the viewer; add a test. Queued after P3 and viewer-step1 merge.
- Spec: same brief, Feature B (revised).

**FUT4. One-command helpers.**
- `Check-NscPrereqs.ps1`: Docker up, both volumes logged in, host CLIs logged in, Source clean, Unity closed, no stray viewers.
- `Start-NscViewer.ps1` / `Stop-NscViewer.ps1`: live pair, port 8828, identity check.

---

## Already fixed on `main` (don't re-fix)

- **Viewer binds its port exclusively** (`_ExclusiveHTTPServer`, `SO_EXCLUSIVEADDRUSE`). Memory said "not merged"; it is merged.
- **Viewer timing projection** (`a960ee0`) and **`reset-task` as a selective revert** (`70d709a`).
- **Viewer display fixes:**
  - the legend now counts held nodes;
  - held nodes are solid grey;
  - a stale controller record no longer overrides live workers;
  - a committed decomposition supersedes an old failure (`87d9f6a66`);
  - committed delivery beats a stale idle checkout;
  - a content-identical cherry-pick keeps delivery;
  - external work shows over `human_action` (`63f5814d2`);
  - the human-complete overlay.
- **Coercive "rickroll" review alarm removed** (`330cd3777`).
- **Post-crew:**
  - a missing validation policy routes to human review (`65ff86439`);
  - code-only candidates skip scene rebuild.
- **Blocking audits removed** (`8b84f1af7`).
- **Concurrent scene reservation** `--allow-resource-overlap` (`4cea6164c`).
- **Room-scene builder registry** (`ROOM_SCENE_BUILDERS`, from `d201f5d90a`).
- **Checkout-lock deferral** for controller actions (`01112057d`).
- **Client connection aborts no longer log tracebacks.**
- **The `RolePathPlan` materialization crash from the 9/16 demo** can't happen on `main`; the dual-path guard predates it. It was only in the rehearsal repo, and no test covers that function.
- **Stale clean unleased checkouts recover** (`4ad1d1f82`).
- **`taskcontrol validate` scene-path scanner false positive** (`3198afcfd3`).
