# Assistant-operated pipeline: working handoff

Historical development log, updated 2026-09-10. Read `CURRENT.md` first for the current
state and remaining requirements. Earlier entries below are superseded by later
verification; they are retained as evidence, not instructions to redo completed work.

## Objective and ownership

Vincent controls work through conversation. The assistant selects and launches scoped workers, presents separate Unity projects and exact candidate commits, and integrates only Vincent's explicit approval of that commit. The existing visualizer is read-only. Preserve user edits and the existing successful NSC-042 project.

Use small independent assignments and cheaper agents; keep reports on disk. No automatic paid-provider retries. No GitHub messages, real approvals, or publication are implied by component tests.

## Implemented

- JSON CLI: committed inventory, dependency inspection, owned isolated checkouts, explicit scope validation, review decisions, local fast-forward integration, success-project preservation, read-only viewer.
- Scope uses the existing RepositoryScopeAuthority. `scope TASK --plan FILE --lease-id ID` validates a plan; it does not authorize execution.
- Approval binds to candidate SHA/tree and task contract. Candidate registration remains a test fixture until the crew adapter is connected.
- Success preservation defaults to `C:/NSC/SuccessfullTasks/TASK`; existing unowned projects are never adopted or overwritten.
- Scope tests: 3 passed on 2026-09-10. Existing component tests and limitations are described in their test modules.
- Dependency inspection can now recognize matching human-approved local integration receipts whose candidate is an ancestor of Source and whose contract still matches. Approval alone does not unlock work. Review plus dependency tests: 9 passed, temporary Git only.
- Windows process identity uses PID, creation ticks and executable path. Three tests passed with real short-lived local Python processes; no providers. Unknown/inaccessible identity is not treated as dead.
- worker_control.py and CLI worker-status/stop-worker target an exact run, validate owned stop paths, preserve output, and never release capacity or claim Docker cleanup. Two fixture-worker/real-Git tests passed.
- Viewer reads worker host identity, shows stop requests without claiming stopped, and blocks unverifiable running workers. Four viewer tests passed after this change.
- CLI reserve/run-worker connected; run-worker requires explicit spend authorization and runs foreground. No real worker invoked. Combined admission/crew tests raced agents' ongoing revisions: 15 tests, 1 failure and 5 errors (reservation metadata/fixture root mismatches). Sent results back; wait for both completion notifications then rerun. Do not report this combined path as passing yet.
- Both agents finished revisions. Parent's worker rerun: 11 tests passed after credential mapping hookup. New runtime_config.py creates per-run Compose external-volume mapping; 1 generator test passed. Worker tests mock Compose-file generation and provider bridge explicitly; no Docker auth/live provider proof. Admission rerun pending below.
- Parent admission rerun: 7 passed. The earlier combined failures are superseded by these completed focused reruns.
- New bounded assignments: Maxwell candidate.py/test_candidate.py real receipt recovery via verified disposable base scope (no private constructor bypass); Singer worker_launcher.py/test_worker_launcher.py detached launch with pre-provider receipt/ready handshake. Do not edit these files concurrently until agents finish. No actual game workers authorized or started.
- docker_workers.py inspects/stops only exact run-project containers with matching /workspace checkout mount, never deletes volumes or claims host exit/capacity release. 3 mocked-Docker tests passed; actual Docker Desktop mount-format compatibility still needs verification.
- Immediate stop now has checked-handle Windows host termination (4 real disposable-process tests), then exact run-bound Docker stop and retained stopped record (worker-control 4 tests use mocked host/Docker, real temporary Git). CLI stop-worker --force connected. Refuses success if containers remain. No live worker stopped; capacity settlement remains pending.
- worker_control/viewer recognize launch records before worker exists, so startup can receive cooperative stop. Launcher agent is adding bound launch metadata/config hash and path checks; verify before wiring detached start CLI.
- worker_settlement.py / settle-worker CLI releases only completed crew runs after exact receipt/artifact checks, host absent and Docker containers not running. Two fixture-host/Docker + real-Git tests passed, including repeat settlement preserving another admission. Failure/forced-stop capacity settlement still needs process-tree proof; not automatically released.
- Maxwell completed candidate recovery using real constructor, base clone and committer. Parent reviewed implementation and started targeted real-Git/real-bridge/real-committer fixture recovery test; result pending. Still not a paid-provider/Unity proof.
- Parent recovery test passed (1 test, 7.3 seconds). Fixture manually creates matching candidate commit/trailers with no committer receipt, then actual bridge verification and committer recover it without a second commit. Normal adapter tests were separately run earlier.
- Detached launcher revision parent-verified: 6 tests passed, including real fixture subprocess, missing-ready timeout, stop-before-worker, config tampering. CLI start-worker now connected (same arguments as run-worker, explicit spend authorization). No paid task launch occurred.
- Actual Docker Compose config resolution (no containers) passed: external Claude volume resolves to nosafecircle_claude-config and /workspace bind is the intended checkout/read-only. Does not prove authentication or Docker inspect mount formats.
- Offline completion demonstration passed: test_completion_workflow (1 test, 11.6s) uses fixture-generated crew artifacts then actual bridge verification/recovery -> rejected unapproved integration -> fixture-only exact approval -> actual local merge -> preserved project -> viewer local_accepted. No live provider or human approval claimed.
- Singer doing read-only integration review (control-integration-review.md). Maxwell implementing windows_job.py/test_windows_job.py to contain host descendants before launch readiness, enabling proven crash/force-stop settlement; no launcher/control edits assigned. Named-job lifecycle reference: https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects . Current force-stop still does not prove host descendants exited.
- Real NSC-042 preparation completed through CLI at C:/NSC/TenTaskFinalIntegration-20260905-AssistantCheckouts/NSC-042, branch assistant/NSC-042, pinned source 7c0212d7e1c70634bfcb5d631fef3ba3b29ea027, clean. Scope validated from evidence/crew-comparison/042-scope.json, lease assistant-042-preflight-20260910, plan scope-a96d760e4cc38ade19e73648ef18d85df219df31e8b8e3401156e737ca0cbaf2. No admission, provider worker or human approval. Source uncommitted Unity edits intentionally NOT copied; clone generator still has committed 48-pixel value. SuccessfulTasks reference untouched.
- Actual read-only viewer loaded against current Source on temporary port 55067 (no worker/checkouts created), showing 69 tasks/10 scope, no controls. Browser revealed misleading pending label on all active tasks. Added assistant_idle state/legend and assistant local-acceptance legend filter correction. Temporary browser and owned server were stopped; post-fix browser verification still pending. No existing operator viewer was stopped.
- Claude reported on Issue 36. Parent accepted pixel-refresh diagnosis but corrected broad claim that batchmode does not exist: production candidate_integration.py already runs it; local path differs. Assigned Claude a proposed patch in evidence directory only (not live Assets) plus focused C# regression patch. Continue coordination on Issue 36.
- Viewer now projects a verified candidate as needing human review, approved-but-not-integrated, or changes requested. Dirty candidate checkout is blocked. Viewer tests: 3 passed; no browser visual test yet.

## Current delegated work

- Kepler completed gate review: `C:/NSC/AssistantControlEvidence/crew-comparison/codex-gate-review.md`.
- Singer completed review.py/test_review.py fixes: ignored-file collision and branch-switch during fetch. Parent reviewed changes and reran the 7 review tests successfully. See gate-fix-report.md; arbitrary external writers do not obey the cooperating lock.
- Scope agent completed scope.py/test_scope.py; report scope-agent-report.md in the same evidence folder.
- Maxwell (gpt-5.6-luna, medium), agent `01a08cb2-8ce8-7df3-8f6e-645701927ace`, implementing candidate.py/test_candidate.py against the existing verified bridge and committer. Read candidate-agent-report.md before relying on it.
- Parent requested candidate revision: remove private scope-constructor bypass during recovery, bind scope to checkout record source/contract, reject integrating status. Candidate adapter not yet accepted or wired into CLI.
- Candidate revision applied and parent reran 8 focused tests successfully. CLI `candidate TASK --run-id ID --config FILE` now invokes it; no provider launch. Recovery after candidate HEAD advances remains incomplete and preserves state. Tests use explicitly fake bridge/committer seams.
- Singer is implementing admission.py/test_admission.py: source-wide capacity/resource reservations. Maxwell is implementing crew_worker.py/test_crew_worker.py: synchronous bridge invocation core, not child-process launch/cleanup. Both remain on their existing agent IDs. Parent must review before wiring.
- Claude assignments and communication now use https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36. Authorized to comment there as Codex. No Claude comments at last check. Do not silently launch another Claude comparison in parallel with Vincent's issue worker.
- Claude acknowledged assignment on Issue 36; Codex replied there narrowing focus to materialization and texture refresh. Minimize chat updates to Vincent and keep routine coordination on the issue/disk.
- Claude comparison ended at its 16-turn limit without a report. claude-result.json records the terminal error. Do not count it as independent review or restart the broad assignment automatically.

## Remaining work

Connect authentic ExecutionCrew receipts and candidate commit recovery; implement worker launch/stop/liveness, admission/capacity/resource reservations, feedback/retries, dependency acceptance and decomposition children. Connect those states to the viewer. Verify the UI and demonstrate one task. No real game task has been launched or approved by these new tools.

The gate review found that Git's default merge can overwrite ignored files and that a branch switch during fetch can produce an incorrect integration receipt. Source-wide cooperating locks and explicit branch checks cannot prevent arbitrary external Git commands; report that limit honestly.

## NSC-042 investigation

Reference project: `C:/NSC/SuccessfullTasks/NSC-042`, previously observed commit aee162377a9dbbba4f5862d8629efb69452b2b3b (verify from Git before use).

Prior inspection found identical tracked AgentCrew blobs, but different ExecutionCrew/runtime and launch paths. The old successful crew produced generator/tests; production subsequently materialized Unity assets. Recent local handoffs did not run that production materialization. Latest blocked worker explicitly could not regenerate the long serialized texture with its available tools while AC005 required the assets.

The successful generator compared pixel content when refreshing existing tiles. Current generator lacked that comparison. Current saved WallTile texture matched the old 48-pixel pattern while Vincent's working generator edit used 32. These are prior code/byte comparisons, not a new Unity visual test. Preserve all current Assets edits and the reference project. Recheck exact files before implementing a fix.

## Process-tree settlement verification (2026-09-10)
Named Windows Job containment is now wired before detached-worker readiness. Settlement checks remaining job members even when a worker wrote `succeeded`; failed/stopped workers can release capacity after the contained tree and bound Docker containers have exited. Unrelated admissions are retained and no approval/integration is granted by settlement.
Executed: `python -m unittest Pipeline.AssistantControl.test_windows_job Pipeline.AssistantControl.test_worker_launcher Pipeline.AssistantControl.test_worker_control Pipeline.AssistantControl.test_worker_settlement` — 18 tests passed (43.691s). Job tests use real disposable Windows processes; settlement/Docker observations use fixtures. No paid provider or Unity run occurred. Foreground failed-run containment and pre-identity startup recovery remain under review; use detached start-worker for the intended operator workflow.

## Startup/retry corrections (2026-09-10)
Foreground run-worker now launches the same contained child as start-worker and waits for its exact identity. Ctrl-C during status inspection or waiting requests stop for that exact run. Direct real bridge invocation without membership in its owned Windows job is refused; injectable fixture bridges remain available to tests.
A settled failed/stopped launch can be archived and replaced by a different admitted run. Definite no-child creation failures and retained-handle-confirmed pre-readiness exits can settle; absent identity alone is insufficient. A child-written hash-bound identity handshake allows inspection/stop after a parent crash before its identity write. Capacity release does not approve or integrate a candidate.
Parent verification: 24 CLI/settlement/crew-worker tests passed (56.011s); after handshake integration, 13 worker-control/settlement tests passed (33.350s). Five direct-provider-entry/Windows job tests passed (3.286s). Completion-workflow fixture still passes (11.427s), using real Git/bridge receipt verification with fixture result bytes and test-only approval. No paid provider/Unity run or real task approval occurred. Final launcher/CLI rerun recorded next when complete.
Final parent rerun: python -m unittest Pipeline.AssistantControl.test_worker_launcher Pipeline.AssistantControl.test_cli_worker — 16 passed (47.548s). Includes real disposable launcher processes, no paid provider. Remaining verification: final browser projection, actual NSC-042 materialization and explicit human approval; no live worker has been started.
Viewer follow-up: parent ran 7 viewer tests (14.106s), all passed. Real source cold snapshot: 69 tasks, 2.78s, no inspection error after removing duplicate contract loads. Browser showed Assistant-managed project, live, workers now 0, conversation control, Awaiting Instruction 10, and no start/stop controls. HTTP NSC-042 row verified its owned checkout path and exact source commit. JavaScript syntax passed; assistant-only scheduler counters/identity text omitted. Temporary viewer verification server is shut down after inspection.

## Rejected-candidate revision (2026-09-10)
Added revise command and revisions.py. An exact rejected candidate can become the next worker base without deleting its code; prior state remains in revision_history, approval is cleared, worker capacity must be settled, and source ancestry/contract bindings are rechecked. Admission recognizes that revision base and preserves known ignored Unity caches while refusing unrelated ignored content or real edits.
Parent ran test_revisions + test_admission: 13 passed (47.507s). Includes Source advancing/refusal with unchanged record bytes; paired worker/launch settlement; actual ignored Library fixture retention; old candidate SHA approval refusal; fixture second candidate approval/local integration. Second candidate metadata is explicitly fixture-seeded, not independent provider review.
Feedback follow-up: inspection and execution showed the existing ExecutionCrew retry accepts a descendant candidate base and verifies the old patch as already present. revision_feedback.py now binds the archived candidate/result/patch and exact rejection message, checks compatible scope/provider configuration, and supplies retry_run_id plus feedback_file to the real bridge. This supersedes the earlier assumption that retry required the identical old Source commit.

Parent ran `python -m unittest Pipeline.AssistantControl.test_revision_feedback_integration`: 1 passed (9.637s). This pure/component test uses disposable real Git repositories and the actual ExecutionCrew retry implementation with fixture provider responses. It asserts review_ready, already_present seed mode, candidate-base HEAD/tree, unchanged original Source, and exact rejection notes in implementer/test-author/validator prompts. Candidate metadata is fixture-created; this test does not prove the complete reject-to-new-commit workflow or independent provider review. Earlier focused helper/worker tests passed separately. No paid provider or Unity invocation occurred.

Remaining concrete gaps: source-divergence update is not implemented; its design report is advisory. NSC-042 live demonstration and Vincent's real Unity approval remain outstanding. No live source/task checkout was revised.

## Revision completion follow-up (2026-09-10)

Parent ran `python -m unittest Pipeline.AssistantControl.test_revision_completion`:
1 passed (17.250s). The disposable real-Git test rejects a fixture-registered first
candidate, preserves it through begin_revision, creates a fresh scope/admission,
exercises actual ExecutionCrew retry with fixture provider responses, then uses
the real bridge receipt verification and LocalCandidateCommitter to register a
different candidate. Old-SHA approval is refused; labeled test-only approval of
the new SHA permits local integration. The bridge receipt is explicitly persisted
by the fixture, not obtained from a live worker process. This covers the revision
components together, not paid-provider or Windows-worker orchestration end to end.

Parent also ran test_review + test_revisions: 13 passed (38.760s). Source-sync
implementation and its review/CLI/viewer wiring are now in progress, superseding
the earlier absence note; do not treat that path as validated until its focused
verification is recorded. No game files, real approvals, or remote branches changed.

## Initial Source synchronization (2026-09-10)

Added source_update.py and sync-candidate CLI, connected synchronized-candidate
validation to ReviewGate and viewer, and preserved exact rejection while refusing
unsupported synchronized-worker revisions before state mutation. The operation
stages a mechanical merge of the selected Source SHA into an approved candidate,
checks merge-tree equality and task-path containment, then fast-forwards only the
owned task checkout. Approval is cleared; no new crew review is claimed. Current
support handles one synchronization, with exact-command publication recovery.

Parent ran `python -m unittest Pipeline.AssistantControl.test_source_update`:
9 passed (34.870s). Real disposable Git tests cover new-SHA approval and local
integration, old-SHA refusal, preserved rejection, Source working edits, conflict
retention, post-FF journal recovery, settled worker/launch pairs, active-reservation
recovery blocking, and altered merge-proof rejection. Original candidates and human
decisions are labeled fixtures. Syntax compilation of the connected modules and
tracked-file whitespace checks passed. No providers, Unity, real task changes or
publication occurred.

Remaining: repeated synchronization; worker revision after rejecting a synchronized
candidate; conflict-resolution workflow; authorized live task/Unity demonstration.
The initial sync path is not proof of a complete parallel-task integration loop.

## Fresh revision and receipt corrections (2026-09-10)

Synchronized rejection now enters a fresh scoped revision, preserving its merge
lineage and exact rejected base. Added optional revision_feedback_file transport
through the bridge and ExecutionCrew, distinct from legacy patch retry. Exact
feedback bytes/digest are persisted and checked during candidate registration.
Receipts now live under candidate-receipts/TASK/sha256(crew_run).json, preserving
previous runs. Same-result registration retains approval/status. Parent caught and
fixed the missing _run_prepared argument forwarding before any real launch.

Parent verification: test_candidate_receipt_revisions 2 passed (19.454s);
test_revision_feedback + test_admission 11 passed (34.721s);
test_fresh_revision_feedback 4 passed (12.967s);
test_revision_completion 2 passed (39.802s). These cover actual Git/committer
receipt isolation, unchanged approval on re-observation, bridge-to-runner argument
forwarding, and synchronized rejection -> fresh fixture crew -> real new candidate
commit -> test-only approval/integration. Fixture provider output and persisted
bridge receipt inputs are explicit seams; there was no paid provider, Unity,
Docker or real human approval. Syntax and tracked whitespace checks passed.

Repeated-sync and second-publication recovery changes are under final verification.
Old prepared task runtimes need the new ExecutionCrew code before fresh-feedback
launches; no live checkout was modified or automatically upgraded.

## Repeated synchronization verification (2026-09-10)

Parent ran `python -m unittest Pipeline.AssistantControl.test_source_update`:
12 passed (74.561s). Repeated merges now retain per-operation journals and merge
lineage; each version loses the previous approval. Tests cover a second Source
advance, exact old-command replay without rollback, injected second-finalization
failure recovery, fresh feedback/admission after synchronized rejection, approval
and local integration, conflicts, Source edits, settled worker pairs and altered
merge evidence. Every linked mechanical merge is checked against Git's merge tree.
The Source-ancestry check now distinguishes a revision worker's rejected base from
the actual Source commit. No paid execution, Unity testing or live task mutation.

Remaining: resolution of retained merge conflicts and a real, authorized one-task
demonstration with Vincent's Unity decision. The previously prepared NSC-042 project
still has its older runtime; it must not be claimed to contain these new features.
