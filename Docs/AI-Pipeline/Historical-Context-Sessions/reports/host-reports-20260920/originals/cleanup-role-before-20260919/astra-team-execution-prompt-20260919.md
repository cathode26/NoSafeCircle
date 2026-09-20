# Revised brief: finish a safe cleanup sprint in hours

This replaces the earlier "days, not weeks" execution prompt. The original is preserved in [astra-team-execution-prompt-20260919.before-review.md](C:/nscrev/reports/astra-team-execution-prompt-20260919.before-review.md).

Vincent's current request is to review and improve this brief, with additional roles if useful, so the project can be cleaned up in hours instead of weeks. His further direction is to use many Claude subagents when work can run simultaneously. The resulting [team execution plan](C:/nscrev/reports/nsc-team-execution-plan-20260919.md) is the proposed operating plan. Reviewing these documents does not restart stopped sessions, authorize provider spend, create repositories or authorize deletion.

**Objective**

Run a 4–8 hour cleanup and recovery sprint, subject to measured transfer/verification time and Vincent's decisions. Target the first useful deletion batch in 2–4 hours. These are planning targets, not verified estimates or a promise to dispose of every directory.

Today's outcome is:
- Irreplaceable scaffolding, selected historical Git objects and every log in the selected source families have verified off-machine recovery.
- All selected inactive redundant copies with passed recovery receipts are actually deleted by Vincent.
- Retained paths have an owner/purpose or a specific unresolved blocker.
- Normal work continues in retained active paths.
- A repeat capture procedure and its owner exist; point-in-time protection is not described as continuous backup.

Full task undo is a separate engineering deliverable. Do not put six undo packages, a polished backup service, wholesale tool migration, historical task backfill or removal of compatibility junctions on today's deletion critical path.

**Inputs and authority**

Read the adopted [durability/cleanup/undo design](C:/nscrev/reports/nsc-durability-cleanup-and-undo-plan-20260919.md), [agent directory](C:/NSC/nsc-agent-directory.md), [cleanup guide](C:/NSC/nsc-cleanup-agent-guide.md), and live cleanup/decomposition queues. Reuse supplied measurements and inventories. Check current state only where it controls a capture, ownership decision or deletion; do not commission another global counting exercise.

The directory defines lanes. The plan may propose a temporary responsibility or rule change, but must name it and how it becomes authorized. A peer handoff is not Vincent's approval. No existing permission is broadened silently.

**Staffing**

Keep the nine current sessions. More standing sessions are not the default: they add startup and coordination cost and do not multiply disk or uplink throughput.

Add bounded helper functions under existing owners:
- Capture packager under Pipeline Maintainer.
- Independent recovery verifier under Cleanup, distinct from the capture author.
- Disposition scanner and deletion-script reviewer under Cleanup.
- Existing scribe/test-runner/reviewer helpers as needed.

Cleanup owns the master disposition ledger and sprint progress. Pipeline Maintainer owns preservation code and read-only-source capture operations. Release prepares repository provisioning and owns explicitly authorized archive publication. Documentation, Art, Game, GER and Decomposition supply their own content/ownership attestations. Viewer reports operational status without modifying records.

Plan 17 initial bounded helper jobs, expanding only when another independent deliverable is ready. Run about 8–12 lightweight jobs concurrently when their inputs are available; this is a starting configuration, not an artificial four-agent ceiling. Initially admit at most two heavy disk/network operations, increasing only if observed throughput improves without disrupting game work. Keep one writer per capture repository/master manifest. Helpers do not recursively delegate or send fleet messages. Owners accept their artifacts and conduct handoffs.

**Parallel schedule to produce**

Use hour windows, with a separate day-2/day-3 engineering continuation:
- 0–30 minutes: kickoff/authority packet, exact source exclusions and owner replies, three-repo provisioning preparation, parked-decomposition decision packet.
- 0–90 minutes: capture and publish sealed chunks while scripts, source maps and hash attestations are prepared in parallel.
- 1–3 hours: independent remote restores and first eligible batch review.
- 2–4 hours: Vincent executes Batch A.
- 4–8 hours: remaining captures/verifications and, if ready, Batch B; close out actual outcomes and blockers.

The hard path is capture -> upload -> independent restore -> candidate receipt -> sealed reviewed batch -> Vincent -> final verification. Pipeline code integration, experiment merge decisions and all-directory classification must not delay a separately safe batch.

Use the first completed upload/restore to revise the time estimate. Shared storage and network throughput are not divided by the number of agents. If full coverage cannot finish in the window, report exactly what is protected/deleted and what remains; do not rename partial completion as total cleanup.

**Constraints the earlier brief omitted**

1. Task-named worktrees require Vincent's archive decision. Dirty/untracked retirement requires an explicit per-item decision. Present all such decisions in one table; do not treat a generic cleanup go as every item's approval.
2. Never delete NSC-### branches. First batches remove working copies, not branch names or remote refs. Use the actual common Git directory for worktree operations, children before parent.
3. Cleanup currently forbids Git force operations. The first batches must work without them. Anything requiring an exception remains held unless a concrete exception is separately adopted.
4. Some current cleanup documentation still treats owner silence or an empty restore log as evidence. Those rules are rejected by the adopted preservation design. Silence means unresolved; quarantine age is never deletion proof.
5. The parked NSC-007 decomposition needs Vincent's exact-plan approval or abandonment in the Decomposition session. Preserve its records and referenced outputs first. The old NSC-015 plan is identified as stale and must not be applied.
6. While that plan is parked, graph/contract/new-task/policy writes remain held. It does not stop copying, verification or independent branch development. Any compatible game integration still uses fresh checks and a single writer slot.
7. Until a real common lock covers all writers, the Game Agent coordinates explicitly acknowledged short main-write slots. GER and Decomposition keep their own execution lanes. No timeout implies the prior writer finished.
8. Only Vincent creates repos and runs destructive scripts. Pushes need his own word in Release; game merges need his own word in Game. Decomposition has its separate exact-plan approval. Do not claim all of these can be replaced by one relayed go.
9. The brief's stop-work order remains until Vincent restarts the sessions. This document is not a restart instruction.
10. Cleanup needs no game merge, Unity run, in-game test or new art generation. If such work becomes necessary for a candidate, defer that candidate rather than add it to the entire sprint's critical path.

**Required work packages**

Assign one accountable owner per package and name executors/reviewers separately. Cover:
- Source coverage, active-path exclusion and disposition manifest.
- Fleet/evidence/history capture and the three new repositories.
- Upload, independent restore, per-candidate recovery receipts.
- Worktree retirement, quarantine, dirty salvage and two deletion batches.
- Repeat capture and honest backup-age reporting.
- GER tool consolidation and documentation, off today's critical path.
- Real main-write locking, followed separately by the six undo packages.

Code ownership stays with Pipeline Maintainer; GER supplies contract semantics, Game supplies integration/crew semantics, and those owners accept behavior. Parallel undo implementation uses isolated helper branches with agreed interfaces, not multiple sessions editing the same pipeline files.

**Handoff proof**

Each package carries a schema version, owner, run/package ID, exact inputs and their hashes, source IDs, tool version, payload locations, per-input results and outstanding errors. A producer returns a nonempty real artifact. The receiver parses it, checks assigned-input coverage and verifies the claims relevant to its gate.

Successful exit is necessary but insufficient. A helper that spawns a background scan and exits without the artifact has failed. Keep child jobs attached/awaited and return unresolved input rows on timeout.

A deletion candidate additionally requires original/restored file hashes, retained refs/full OIDs and dependency closure, exact remote recovery identities, independent restore results, owner release, and final source fingerprints. No local alternates or source-object borrowing may make the remote restore appear successful.

Seal each deletion batch to exact paths/actions and script/manifest hashes. Recheck under a path-specific retirement hold immediately before acting. Changed, missing or unreadable inputs cannot inherit the old approval. Report an incomplete batch honestly and retain successful per-item receipts for safe reruns.

**Vincent's interruptions**

Prepare complete packets before asking him to act:
- One kickoff/provisioning window, including bounded helper budget and narrow responsibility extensions.
- One Release-session authorization for the concrete sprint publication scope.
- One Decomposition-session decision packet, separate from cleanup authority.
- At most two deletion commands, each for a reviewed manifest; include any per-item exceptions explicitly.
- A Game-session merge approval only if a separate pipeline improvement is ready. It is not required to finish cleanup.

Count real session visits and scripts. Do not market five distinct authorizations as "one click." Proposed new permissions and task-worktree decisions must be visible.

**Cuts and honesty**

Preserve the four-repo design and recovery gates. Defer sophisticated incremental collectors, log-segmentation engineering unless a current payload needs it, viewer code, tool path rewrites, junction retirement, branch deletion, full task undo and historical midpoint reconstruction.

The second independent off-machine archive remains a durability milestone. Any proposed first-sprint deferral belongs explicitly in Vincent's kickoff scope decision. If it is deferred, disclose that residual risk and keep the local capture stores protected; do not claim the entire adopted durability design is finished.

Write a concrete team execution plan to C:\nscrev\reports\nsc-team-execution-plan-20260919.md, including an owner matrix, hour schedule, critical path, artifact contract, Vincent's exact actions, helper bounds, continuation dependencies, and a completion report that distinguishes protected, deleted, active and unresolved items.
