# NSC team execution plan: cleanup in hours

**Decision:** use the existing nine sessions as accountable owners and fan out 17 bounded helper jobs. Target the first useful deletion batch in 2–4 elapsed hours and a substantial cleanup/recovery sprint in 4–8 hours. Do not make task-undo engineering a prerequisite for reclaiming disk or protecting files.

This is a reviewed execution proposal, not evidence that sessions have restarted or any cleanup has run. It implements the cleanup/durability portion of the [adopted design](C:/nscrev/reports/nsc-durability-cleanup-and-undo-plan-20260919.md). The [revised brief](C:/nscrev/reports/astra-team-execution-prompt-20260919.md) supersedes the [preserved original brief](C:/nscrev/reports/astra-team-execution-prompt-20260919.before-review.md).

Vincent's latest direction is to use many Claude subagents when work can happen at the same time. That is the execution model here. A session owner makes decisions and accepts outputs; helpers do independently specified work. More helpers can shorten preparation, analysis and review. They do not multiply the bandwidth of one disk or uplink.

**1. What changes in the brief**

The earlier brief made three things unnecessarily serial: all-directory cleanup, a permanent backup service, and six packages of new transactional undo. They have different finish lines.

| Outcome | Today's finish line | What does not block it |
|---|---|---|
| Recoverable scaffolding | Selected source families captured into the agreed repositories, uploaded and restored independently, with exact coverage/remaining gaps recorded | Full incremental collector, viewer integration, cross-repo task checkpoints |
| Useful disk cleanup | Vincent actually removes the inactive redundant copies whose recovery and authority gates pass; receipts verify what disappeared | Deciding whether old experiments should merge, every other candidate finishing, source-writer porting |
| Continued game work | Active paths protected; branch work continues; main writers use short acknowledged slots | New mutex deployment, full undo, broad path rewrites |
| Full task undo | A separately reviewed engineering release | Not a condition for declaring a particular deletion batch finished |

A 4–8 hour outcome is conditional. It is not a promise that all 788 directories disappear, that all 138 worktrees are disposable, or that every unresolved historical case can be settled today. Accounting for every row is also not the same as preserving and deleting every eligible row. Completion reports must keep those distinctions.

**Keep the four-repo decision:** existing game repository plus new private nsc-fleet, nsc-evidence and nsc-history. Dedicated local capture roots stay at C:\NSC-Repositories; no new Git repository covers broad live roots and no tracked junctions are introduced. Every log stays recoverable. The only-copy tools, dirty state, unknown Git histories and pinned art remain preservation priorities.

**2. Authority, operating holds and the current blocker**

The [agent directory](C:/NSC/nsc-agent-directory.md) is the routing authority. A package owner is accountable for delivery; it does not gain another owner's permissions. The user has authorized this document review/revision. The proposed sprint still needs its kickoff and the concrete execution approvals below.

The [cleanup guide](C:/NSC/nsc-cleanup-agent-guide.md:39) adds restrictions missing from the original brief:
- Task-named worktrees require Vincent's archive decision through the Game Agent.
- Dirty/untracked removal requires explicit per-item approval.
- NSC-### branches are never deleted.
- The default script cannot use Git force operations.
- Only Vincent executes destructive scripts.

Use clean, inactive, non-task candidates for Batch A. Prepare a single itemized decision table for task-named/dirty candidates rather than repeatedly interrupting Vincent. A task's delivery/archive state is not inferred from a folder name. No task branch or remote ref is deleted by either batch. Any protected task-ref migration needed to retire an independent clone requires the Game Agent's checked disposition; ambiguity is HOLD.

The narrow extension proposed for Release is publication of the three new archive repositories during this sprint. It does not grant automatic game pushes, force updates, ref deletion or future unlimited backup pushes. Cleanup's coordinator duty is tracking artifacts and exceptions, not commanding another role's domain decisions. Documentation records these temporary responsibilities when Vincent adopts the kickoff packet; no new standing session is necessary.

**Resolve the parked decomposition in parallel, not as a cleanup prerequisite.** The [live Decomposition queue](C:/NSC/agent-state/decomposition-agent-todo.md:19) identifies NSC-007 plan GDP-737cfe15b2d9dd172e71cf3e6407ac3e9e8f224d98f1c60541be1a51e5d9e2f5, run decomp-nsc007-20260918e, as awaiting exact-plan approval or abandonment in that session. It identifies the old NSC-015 plan as stale and forbids applying it. These are discovery inputs, re-inspected before action—not an approval.

Decomposition prepares one decision packet: current plan/hash identities, fresh compatibility inspection, its existing summary and explicit approve/abandon alternatives. The referenced NSC-007 summary under C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput is an additional named preservation source; do not assume everything important lives under NSC/nscrev.

Until Vincent decides, graph/contract/new-task/policy writes remain held. Copying, remote verification, cleanup of inactive paths and independent game branch work continue. Unrelated game integrations can proceed only after checking compatibility and existing approvals. Current decomposition code checks ancestry plus changes under Tasks, Pipeline/TaskGraph and the validation policy; fresh inspection determines the apply source. Do not reuse an old apply SHA after main advances. No timeout abandons the plan, moves its record, releases the freeze or authorizes another paid decompose.

**Temporary main-write serialization:** Game Agent coordinates short named slots, but GER and Decomposition remain the executors of their own authorized writes. At kickoff each writer acknowledges the queue and identifies any unattended publisher. A slot names operation ID, owner, expected HEAD and intended paths. Completion returns actual before/after HEAD, changed paths and validation evidence. No next slot until completion is verified. A crash or missing reply requires reconciliation, not automatic expiry. main_write.py remains an audit aid, not a mutex. An unaccounted publisher must be paused or kept outside affected maintenance. Uploads, hashing, reviews and branch development never occupy a main-write slot.

**Path-specific retirement holds:** before a candidate enters a deletion batch, its owner releases that exact path, including any process/launcher or other checkout depending on it. The hold includes the real Git parent and linked children where relevant. A revoke, unexpected writer or changed fingerprint invalidates the candidate. A hold timeout stops further deletion; it must not reopen a path while an operation is running. Normal work uses protected active paths throughout.

Use a brief initial quiet window for core live records when practical, targeting 5–10 minutes rather than hours. That is a coordination target, not a forced shutdown. A changing live source gets a labeled non-transactional backup or waits for its own safe point; it never becomes a deletion candidate merely because a sweep copied it.

**3. Work packages: one accountable owner each**

No equal-sized allocation is required. An agent can finish its attestation and return to game work. Producer, reviewer and executor are separate roles.

| Package | Accountable owner | Output / handoff | Why this owner; boundary |
|---|---|---|---|
| P0 Sprint ledger, coverage and disposition | Cleanup Agent | Master source/disposition rows, active exclusions, package status, two batch queues | Owns branch/disk triage. Other owners attest content; helpers return fragments, never edit the master concurrently. |
| P1 Capture tooling and source-copy operations | Pipeline Maintainer | Small reviewed capture adapters, sealed fleet/evidence payloads and manifests | Owns tools. Reads live sources and writes capture roots only; no live-record editing or canonical mutation. Use existing Git/file tools first. |
| P2 Fleet content specification | Documentation Agent | Docs, agent definitions, NSC memory, settings/custom-skill source map and byte receipt | Owns these documents/definitions. PM implements copying; Documentation does not write collector code or inspect broad unrelated profile data. |
| P3 Runtime/candidate coverage | Game Agent | All applicable control roots, candidate OIDs, admissions audit source, live-path exclusions | Owns crews/integration. Supplies required identities; PM captures bytes and objects; no blanket restore of runtime ownership. |
| P4 Pinned art coverage | Art Director Agent | Contract-derived identities/hashes, source paths, restored-byte acceptance | Owns art. No re-export, regeneration, paid art job or Unity requirement for this check. |
| P5 GER/decomposition preservation | GER Agent | GER drafts and only-copy tools map, outstanding graph constraints | Owns contract work. Decomposition supplies its plan/record/output identity; PM owns tool code and copying. |
| P6 Git history capture | Pipeline Maintainer | Immutable namespaced refs and source/ref/OID map, detached heads, stashes/reflog salvage, complete bundle dependencies | Owns preservation implementation. Cleanup supplies actual stores/worktrees; no changes to source branch tips. |
| P7 Repo provisioning package | Release Agent | Reviewed one-time provisioning script/spec for the three private remotes and dedicated local Git roots; remote identities/access check | Owns remote operations. Vincent runs creation; Release does not interpret a handoff as authorization. |
| P8 Publication | Release Agent | Verified push/upload receipts, immutable recovery identities | Requires Vincent's own scoped publication word. Sole publisher to the new remotes during sprint. |
| P9 Independent recovery verification | Cleanup Agent | Per-source/per-candidate remote restore receipts from a fresh helper | Read-only with respect to sources; writes only verification scratch. Different verifier from capture author. Cleanup accepts verified output, not the producer's success claim. |
| P10 Retirement and two deletion scripts | Cleanup Agent | Exact parent-aware action lists, dry-run script, independent review, sealed package | Owns local hygiene. Vincent executes; no forced removal, broad move, branch deletion or destructive Docker action. |
| P11 Deletion execution | Vincent | Batch A/B run logs and per-item intents/results | Existing human-only authority. Cleanup subsequently checks actual effects. |
| P12 Recovery/run instructions and scope updates | Documentation Agent | Compact operator README, adopted temporary routing/authority facts, restart pointers | Owns documentation. Scribe handles bookkeeping; no broad rewriting of all old paths. |
| P13 Operational visibility | Viewer Agent | Accurate protected/pending/blocked status using existing mechanisms | Owns operations/overlays. Any viewer code belongs to PM and is deferred. No fake task completion markers. |
| P14 Parked-plan resolution | Decomposition Agent | Exact-plan decision packet, authorized apply/abandon outcome, freeze release evidence | Owns decomposition. Vincent's decision must arrive there; GER checks the resulting graph/policy state. |
| P15 Repeat capture / minimal ongoing protection | Pipeline Maintainer | Reviewed rerunnable capture command; second-run evidence; later scheduler | Owns automation code. Release owns each authorized publication. Day-one periodic operation is not claimed until a second run succeeds. |

**Post-sprint packages remain assigned, not mixed into deletion:**
- **T1 GER tool consolidation and Astra follow-ups — Pipeline Maintainer.** GER verifies operational semantics; Documentation updates the live callers. Preserve all originals first. Compatibility junction removal waits.
- **L1 real common writer mutex — Pipeline Maintainer.** Fresh independent review; Game integrates on Vincent's direct go. Cover every existing writer before calling it exclusion. A lock used by only one caller does not replace the temporary queue.
- **U1 operation IDs, generations, fencing and readiness explanations — Pipeline Maintainer.** Builds on L1; Game supplies cross-root runtime cases.
- **U2 checkpoint schema and all mutation-path receipts — Pipeline Maintainer.** Game, GER and Decomposition identify actual write paths.
- **U3 undo planning, rescue, attribution and crash recovery — Pipeline Maintainer.** Game supplies landing provenance; Cleanup supplies recovery evidence.
- **U4 semantic create/edit inverse — Pipeline Maintainer.** GER owns semantic acceptance examples and resulting contracts.
- **U5 completion inverse/evidence invalidation — Pipeline Maintainer.** Game owns landing/evidence acceptance.
- **U6 midpoint reconstruction/resume — Pipeline Maintainer.** Game accepts actual crew behavior; Viewer reports results only.
- **Integration of each code release — Game Agent.** Exact reviewed head and Vincent's own go in that session; Release pushes only under its separate authority.

All six U packages are pipeline implementation, so assigning them to GER, Art or Documentation would violate lanes. Parallelism comes from isolated helpers under PM after interfaces are agreed, and from domain-owner acceptance fixtures prepared concurrently. Keep a single integration owner.

**4. Explicit helper fanout**

This is a rolling roster of 17 jobs, not 17 long-running new sessions and not a four-helper ceiling. Start 8–12 lightweight jobs together when inputs are ready. Launch follow-ons as individual partitions finish, rather than waiting for the slowest entire wave. Reuse completed helpers only with a new bounded input packet.

| Job | Parent owner | Exact independent deliverable | Start dependency |
|---|---|---|---|
| H01 Fleet mapper | Documentation | Named docs/agents/memory/config inputs; hashes/required-presence map; exclude unrelated profile content | Kickoff and source schema |
| H02 Tool/draft mapper | PM, using GER's attestation | Real tools plus GER only-copy/draft inputs; old/new authoritative paths | Kickoff; no tool edits |
| H03 Art verifier | Art Director | All 40 contract-pinned inputs, exact paths and expected/current hashes | Existing contracts/reports |
| H04 Runtime mapper | Game | Source/control-root/candidate map, all identified NSC log sources, active owner exclusions | Current records; no record edits |
| H05 Quarantine examiner | Cleanup | Each assigned quarantine clone/bundle: refs, dirty/untracked/ignored needs, recovery dependencies | Existing quarantine manifest |
| H06 Worktree examiner | Cleanup | Assigned registered worktrees: actual common parent, detached/ref identities, owner status | Existing worktree inventory |
| H07 Clone-history examiner | Cleanup | Remaining enumerated independent stores in NSC/nscrev; unique-history capture requirements | Disjoint list excluding H05/H06 |
| H08 Non-Git examiner | Cleanup | Assigned top-level nonrepo directories/files, valuable contents and explicit cache exclusions | Existing inventory; no recount project |
| H09 Capture adapter author/tester | PM | Minimal adapters and source-manifest validator; fixture tests for missing/reparse/changed inputs | Fixed schema; can use fixtures before maps arrive |
| H10 Fleet packager | PM | Sealed fleet payload plus byte manifest; sole writer to its partition | H01/H02 partitions accepted, H09 usable |
| H11 Evidence packager | PM | Reports/control/log/dirty-salvage payload partitions, exact byte manifests | Any accepted H03–H08 partition, H09 usable |
| H12 History importer | PM | Retained immutable ref map and full object closure per accepted source partition | Any accepted H04–H07 partition |
| H13 Remote preparer | Release | Three-repo provisioning package and explicit publication list; private visibility/access checks | Repo names/design; no capture dependency |
| H14 Recovery verifier | Cleanup | Fresh remote fetch/extract/restore receipts; errors and dependencies per candidate | Each published partition; different identity from H09–H12 |
| H15 Batch author | Cleanup | Exact-target retirement script/package; fixtures and dry run; no source mutation | Starts with mocked receipts; binds real P9 receipts later |
| H16 Independent capture reviewer | PM | Verdict on H09 and history tooling: missing/reparse/changed inputs, byte preservation, retained object closure and failure behavior | Each fixture version as ready; fresh reviewer who authored none of the implementation |
| H17 Independent deletion reviewer | Cleanup | Verdict on exact H15 script/manifest hash: protected roots, source races, partial failure, parent ordering and reruns | H15 fixture version first; final bound package rechecked before seal |

Use existing custom helper types where their scope fits: scribe for exact rows, test-runner for bounded tests, delivery-evidence for Game's evidence mapping, pipeline-maintainer for code, and fresh review jobs for capture/deletion logic. Review jobs use the approved Fable CLI configuration when available. Artifact packaging/Windows path checks run on Windows; do not assume a Docker-only check proves NTFS junction or process behavior. Paid external helper jobs start only within Vincent's approved account/job budget.

**Resource limits, not arbitrary agent limits:**
- Initially two heavy hash/copy/compress/restore streams across the machine; measure whether adding another helps before increasing. Cheap schema review, drafting and metadata-only checks can continue.
- One writer per capture repo and one master-ledger writer. Helpers write disjoint staging directories; owner commits serialize.
- One Release publisher per destination. Parallel pushes to independent remotes are allowed only when the uplink benefits.
- One actual source writer at a time until common locking is proven.
- Existing one-Unity-process constraint remains; this sprint needs no Unity job.
- No concurrent generic scans over the same whole disk. Each source has a single inventory producer and reusable results.

A waiting uploader does not consume a code-review slot. Conversely, having 17 helper jobs does not justify 17 simultaneous full-volume hashes. If H14 becomes the bottleneck, split it by disjoint sealed candidate groups under Cleanup, preserving independent identity and the I/O cap. Add helpers only when an independent ready input/output partition exists.

Each helper's packet specifies: source IDs, exact permitted output directory, required schema/artifacts, dependencies, no-go paths, foreground/awaited execution, a bounded first deliverable and stopping condition. Target 20–45 minute work slices; a slow transfer is reported as a supervised transfer, not a completed job. No orphan background scan, recursive delegation or self-review. The parent checks the artifact, schema and complete assigned-input coverage before accepting success. Exit zero without evidence fails; nonzero cannot be ignored because an output file exists.

**5. Hour schedule and critical path**

Time starts when the needed sessions are restarted, remote access is available and the scoped work is authorized. Human waiting and unavailable credentials are elapsed blockers, not time mysteriously excluded from the final report.

| Window | Work on the critical path | Work that runs at the same time |
|---|---|---|
| 0–30 min | Cleanup establishes schema/IDs, protected paths and candidate partitions. Release readies provisioning; Vincent creates remotes. PM starts irreplaceable capture once source owners acknowledge. | H01–H09 and H13/H15 fixture work start where independent. Decomposition presents its decision packet. Game establishes the writer queue. |
| 30–90 min | H10–H12 seal first partitions; Release publishes each ready package immediately. | Remaining mapping and dirty-salvage prep; H16/H17 review capture/deletion code independently; owners release inactive paths; normal branch work resumes. |
| 1–3 h | H14 restores first published partitions and issues exact candidate receipts; Cleanup binds Batch A and completes review. | Later partitions upload; task/dirty exceptions are presented together; source maps and recovery instructions finish. |
| 2–4 h | Vincent runs Batch A; Cleanup verifies removals/registry state and records actual reclaimed space. | H14 continues other partitions; no wait for all histories or every directory. |
| 4–6 h | Archive-and-verify remaining chosen experiments/quarantine/worktrees; seal Batch B if its gates pass. | PM exercises repeat capture, if ready; Documentation and Viewer reflect actual coverage; optional L1 branch/review continues off-path. |
| 6–8 h | Vincent runs Batch B. Cleanup closes actual outcomes and names blocked rows. | Normal game work continues; engineering packages remain separately scheduled. |

**Hard dependencies:**

    per-source map + owner release -> capture/history closure -> upload
    -> independent remote restoration -> recovery receipt
    -> exact batch + independent review + human authority
    -> final hold/state checks -> Vincent executes -> outcome verification

Provisioning, script drafting and fixture review overlap capture. No batch waits for unrelated source failures. A parent-clone deletion does wait for every dependent worktree's preservation and retirement. Whole-quarantine deletion waits for every remaining row; an individual safe item does not.

**Critical-path timing floor:** serial capture/packaging, transfer, independent readback/restoration and final verification for the last required partition, plus human approval latency. Pipelining overlaps different partitions; adding agents does not reduce the actual bytes that must cross the same disk/network. At 45–60 minutes use real first-partition progress to update the forecast. No fresh data-volume estimate or reclaimed-space promise is invented here.

If credentials, quotas, artifact size, missing objects or an owner decision block a candidate, mark that row and dependencies HOLD and keep other partitions moving. Do not compress verification to make an advertised hour.

**6. The handoff contract**

Store each immutable package under C:\nscrev\reports\cleanup-runs\<run-id>\<package-id>. This root is protected from cleanup. The master ledger is a single-writer index of immutable package IDs, not a shared file that helpers overwrite.

Every packet has schema_version, run_id, package_id, owner, created_at, tool_version, input_artifact_hashes, assigned_source_ids, completed_source_ids and errors. Unknown is a result requiring a row, not permission to omit the source.

| Producer -> receiver | Required artifact | Receiver's check |
|---|---|---|
| Content owner -> PM/Cleanup | sources.json: exact path, source identity/kind, required presence, owner, active dependencies, real Git parent, exclusions | Parse; match source IDs to assigned inventory; missing/reparse/unreadable sources are explicit failures |
| PM -> Release | files.json, refs.json and actual sealed payloads: byte SHA-256/length, original ref/full OID/object type, dirty/index/untracked data, dependencies | Files exist; hashes/schema/input coverage match; no unsafe filters, nested repository treated as bytes, or omitted logs |
| Release -> verifier | publication.json: exact remote identities/ref OIDs/payload commits and dependency manifest | Restore from those remotes into an independent directory, never source-local alternates/hardlinks |
| Verifier -> Cleanup | recovery.json: source ID, recovery ID, verifier identity, every restored file/object comparison, external dependency checks, errors | Each candidate has complete recovery. Clean tracked state may use verified Git trees/objects; dirty/nongit/pinned data requires byte restoration |
| Cleanup -> reviewer/Vincent | disposition.json, Apply.ps1, README, review.json; exact paths/actions, child-before-parent ordering, hold IDs, fingerprints, script/manifest hashes | Only recovery-backed eligible IDs; branch/ref protections; exactly reviewed artifact identities; correct authority for exceptional rows |
| Vincent's run -> Cleanup | Per-item intent/results, aggregate run result | Verify actual absence or worktree retirement, retained refs/recovery artifacts, and measure actual reclaimed space |

The complete recovery proof includes named refs for detached heads, actual candidate commits, stashes/reflog choices, bundle prerequisites, and any relevant LFS/submodule/alternate-store dependencies. A successful local fetch or the existence of an object in canonical is not remote retention.

For pinned art, Art's expected hashes and H14's independently restored hashes must both match. For logs, retain every byte captured; an open tail may remain pending but cannot be silently excluded from the coverage report. For dirty state, preserve staged versus unstaged meaning, actual files, untracked/valuable ignored bytes and deletion markers. Every deletion candidate is restored, not merely sampled.

**Candidate gate, mechanically evaluable by Cleanup:**
- Correct live identity/path/common Git parent and explicit owner release.
- Complete preservation manifest and independent recovery receipt for that exact capture.
- No runtime, launcher, path-reference or child-worktree dependency that still needs the live directory.
- Current permission class: clean/non-task, or explicit named exception already authorized.
- Current refs/files/status still match the approved candidate, accounting only for earlier actions in the same batch.
- No reparse surprise, unexpected nested repo or protected-root overlap.
- Reviewed script and action manifest match their sealed hashes.

A global main advance does not automatically invalidate an unrelated retired checkout; compare the candidate's actual retained objects/content/dependencies. Equally, a stable main HEAD does not prove its dirty working files are unchanged.

**Deletion runner contract:** dry-run by default; exact literal paths in one shell; validated resolved roots; no wildcard deletions, broad moves, live-source reset, branch deletion, remote deletion, Docker pruning or Git force. Worktree removal uses the actual parent. Preflight ineligible items are reported and omitted before sealing. A new mismatch or unexpected error during apply stops the remaining batch under the current cleanup rule; return incomplete, retain receipts, and replan the unfinished subset. No automatic recapture-and-delete under old approval. Final empty quarantine-root removal is a separate nonrecursive action.

Vincent's task/dirty decision table names each item ID, exact path, preserved changes, remote receipt and intended action. He can select several item IDs in one response: that is explicit per-item approval in a batch, not inferred blanket permission. If current no-force rules prevent a dirty item from being retired, it remains held or gets its own reviewed exact exception; it is not smuggled into the common runner.

**7. Vincent's steps, with the real friction shown**

This minimizes interruptions rather than pretending different authorities collapse into one click.

1. **Kickoff window, start:** restart the selected existing sessions using one reusable packet; designate Cleanup as ledger coordinator, adopt Release's narrow archive-publisher duty, confirm retained active paths, and approve a bounded helper/account budget. The packet proposes the 17 named jobs, up to 8–12 lightweight jobs concurrently and two initial heavy I/O operations. It explicitly presents the proposed first-sprint scope of local capture plus one independently verified remote, with the second off-machine copy deferred only if Vincent adopts that scope. Model/account/tool availability is checked first; it is not inferred from old reset dates. A session-specific own-word rule still requires his message in that session; coordinators do not relay it as approval.
2. **Provisioning/publication window, early:** run Release's reviewed script once to create the three named private remotes and dedicated local Git roots, refusing unrelated pre-existing contents. In Release's session, authorize one sprint publication scope: the specified run ID, the three remotes and their approved capture namespaces/payload families, append-only/no force/no deletion, expiring at sprint close. This covers incremental partitions within that concrete run without a fresh request per ref; later runs need their own authority unless a standing policy is explicitly adopted.
3. **Decomposition window, early and independent:** review the exact NSC-007 decision packet in Decomposition's session and approve or abandon it. Handle permission for the known-stale record only as explicitly listed. He may defer; cleanup continues while the relevant graph freeze remains.
4. **Batch A window, about hours 2–4:** run one manifest-bound command after receiving exact targets, review/hash identity and recovery receipts. No item requiring extra task/dirty authority is included without it.
5. **Batch B window, about hours 4–8:** decide the compact exceptional-item table, including task-worktree archive decisions prepared by Game where needed, then run one reviewed command for the accepted IDs. Unselected items remain. If no second safe batch is ready, skip this command and report the blocker.
6. **Only if a separate code release is ready:** give the exact merge go in Game's session. Cleanup does not depend on this. Release's archive authorization does not authorize pushing game main.

Thus the default cleanup has one provisioning script and at most two destructive commands, plus the unavoidable session-specific decisions. It needs no in-game test or new game merge. First-batch preparation should be complete before Vincent is interrupted. A representative dry run and fixture review happen before the first apply, not as another indefinite design gate.

Before restarting, Documentation can prepare the exact copy/paste kickoff messages with the same run ID; each owner attaches its own necessary authority clause. Creating extra standing agent sessions would increase this startup work, so it is deferred.

**8. Day 2/day 3 and engineering parallelism**

These are conditional continuation slots, not claims that full undo will be done by day 3.

| Window | Parallel engineering | Serial gate |
|---|---|---|
| Day 2 | PM helpers develop L1/common-lock coverage, repeat-capture/scheduling, and checkpoint schema/fixtures in isolated branches. GER supplies create/edit cases; Game supplies landing/runtime cases; Decomposition supplies graph-boundary cases. Docs writes operator recovery steps; Cleanup resolves remaining retirement holds. | Agree checkpoint/receipt/generation interfaces first. Independently review and integrate the foundational lock/receipt change before trusting dependent live operations. |
| Day 3 | U3 planner/recovery, U4 contract inverses and U5 completion inverse can use those frozen interfaces in disjoint helper branches; separate helpers run failure and regression tests. U6 fixtures can be prepared in parallel. | U6 live resume needs working capture, fencing and inverse semantics. Final combined review/tests on the actual integrated head precede Game merge approval. |

One PM session remains accountable, but it does not write every line or run every test itself. Helpers own disjoint files/modules or sequential patches; no two jobs edit the same worktree. PM integrates and judges boundary changes, reviewers are fresh, and Game owns landing. Source locks plus runtime fencing cannot be declared complete just because one mutex helper passed unit tests.

**Duration statement:** first verified deletions in 2–4 hours and substantial cleanup in 4–8 hours are feasible targets if access, owners, approved helper capacity and existing Git/file tooling are available and the necessary remote transfer fits. Complete all-source cleanup in that window is unproven until first-run evidence exists. If tooling must be built from scratch or recovery dependencies are broken, safe completion can extend beyond the day. Full create/complete/edit/midpoint undo has a multi-day serial integration/failure-testing path; there is no evidence supporting an hours promise. Re-estimate it after L1/U2 interfaces and a crash-recovery prototype are reviewed.

**9. What is cut or deferred, and the cost**

| Defer | Time saved today | Explicit cost |
|---|---|---|
| Six undo packages and historical midpoint backfill | Removes the largest source-integration/testing chain | No new one-command task undo today |
| Porting all schema writers and broad tool consolidation | Avoids source merges and caller migration | Captured old tooling remains operational; existing defects remain tracked |
| Rewriting 124 old paths/removing junctions | Avoids nine-session context/caller churn | Compatibility links remain load-bearing |
| Deciding whether historical experiments merit merging | Replaces subjective review with archive-preserve-delete | Archived code remains unadopted |
| New viewer code and elaborate dashboards | Avoids another pipeline merge | Existing status/Markdown reports show coverage |
| A generalized archive/segmentation framework when current payloads do not need it | Allows existing Git/file capture now | Required large-file handling is still mandatory for any affected payload |
| Automatic branch pruning, Docker/volume cleanup, active-workspace rearrangement | Avoids permission and dependency risk | Some clutter/disk remains deliberately |
| Second independent off-machine archive, if unavailable within this window | Avoids holding every first verified working-copy deletion for a new backend | First sprint has local capture + one verified remote, not full independent-provider durability; both remain protected, Release owns closing the gap |

A rerunnable second capture is strongly preferred before close; if not ready, report the exact snapshot time and have PM/Release perform the existing manual capture/publication procedure at the next approved boundary. Do not report continuous protection from a one-time snapshot. Keep all local capture stores outside every deletion batch.

The source discovery, remote proof, current-state check, independent review of destructive scripts, pinned-byte check and authority checks are not cut. Those are what distinguish fast cleanup from fast data loss.

**10. Completion report**

Cleanup returns one concise report, populated from receipts:
- **Protected:** source families and exact verified recovery IDs/timestamps; all-log coverage and any open tails.
- **Deleted:** exact retired item IDs, worktree-registry outcome and actual reclaimed space.
- **Retained active:** owner and purpose, including protected parent repositories and live references.
- **Held:** per-item blocker, owner and next concrete decision; not an undifferentiated quarantine.
- **Ongoing protection:** second capture result, schedule/manual owner, last verified remote age.
- **Deferred engineering:** L1/U1–U6 and tool work, with no implication they shipped.

A safe independent batch may finish while another remains blocked. Do not call the whole project clean while there are unclassified or unpreserved sources; do not delay proven useful deletion merely because some other row is hard.

The practical acceleration is the combination of many bounded subagents, early partitioned uploads/restores, two human deletion windows, and keeping unrelated engineering off the cleanup path. The final authority stays with the existing owners and Vincent.
