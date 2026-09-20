# NSC team execution plan: a measured cleanup sprint

**Decision:** keep the existing nine sessions, use many bounded Claude helper jobs where their inputs and access are ready, and prove one real recovery-to-retirement path before forecasting the wider cleanup. Preserve first, archive experiments without deciding whether to merge them, and retire only the exact copies whose recovery, dependency and authority checks pass. Full task undo is separate work.

**Revision after independent review.** This replaces the version inspected in the [Astra adversarial review](C:/nscrev/reports/nsc-team-execution-plan-adversarial-review-astra-20260919.md), which returned **FIX FIRST**. Read that alongside the [project-first analysis](C:/nscrev/reports/nsc-project-analysis-astra-20260919.md). The exact reviewed [plan](C:/nscrev/reports/cleanup-role-before-20260919/nsc-team-execution-plan-20260919.md) and [brief](C:/nscrev/reports/cleanup-role-before-20260919/astra-team-execution-prompt-20260919.md) remain frozen; their SHA-256 values are in the [preservation manifest](C:/nscrev/reports/cleanup-role-before-20260919/manifest.json). The current [brief](C:/nscrev/reports/astra-team-execution-prompt-20260919.md) follows this revision. That review was an inspection, not a restore audit or certification of a deletion candidate.

The earlier deletion times omitted work that is not implemented or proved. The present **unmeasured planning allowance** is 4–8 working hours to prepare and prove a small capture/publication/remote-restore/action-package vertical slice, and approximately 6–12 working hours from kickoff to a first modest remote-backed deletion, including that preparation. Access problems, broken histories, large objects, owner decisions or second-copy requirements can extend it. A broader useful pass may take one to two working days. Publish an evidence-based forecast after the slice; do not promise a whole-project finish from directory counts. Report wall time from Vincent's go as well as active work time.

This is documentation, not a restart, provider-spend approval, repository creation, installed backup service or destructive execution. No helper allocation is dispatch-ready merely because it appears below.

## 1. Scope and authority

Keep the [adopted four-repository design](C:/nscrev/reports/nsc-durability-cleanup-and-undo-plan-20260919.md): existing game repository plus private nsc-fleet, nsc-evidence and nsc-history. Use narrow real-file capture roots under C:\NSC-Repositories. Preserve live paths, every NSC log and exact pinned art bytes. No broad live-tree repository, tracked junction, fifth Git repository or new standing agent is needed.

| Outcome | Proof of completion |
|---|---|
| One cleanup batch | Exact eligible copies removed by Vincent; per-item recovery and retirement receipts verified |
| Full named-source durability | Every adopted source row covered as of a stated cutoff; complete remote recovery manifests, independent restores and required second copy |
| Ongoing protection | Successful repeat capture/publication/validation and a concrete authorized next-run owner or installed tested schedule |
| Prevention of another landfill | Producers register workspaces and hand off closure; Cleanup maintains a bounded exception/retirement queue |
| Full task undo | Separately implemented and tested engineering release; never a prerequisite for this cleanup |

The [agent directory](C:/NSC/nsc-agent-directory.md), [Cleanup guide](C:/NSC/nsc-cleanup-agent-guide.md) and [shared workspace lifecycle policy](C:/NSC/nsc-workspace-lifecycle-policy.md) define operating responsibilities. A package owner does not inherit another role's authority. Registration and closure are operating instructions; automated launcher enforcement is not installed by this document.

Only Vincent creates the proposed repositories and executes destructive scripts. Release needs his own scoped publication word; Game needs his own merge word in the Game session. Decomposition needs approval of the exact plan in its session. Peer messages do not carry these approvals. Stopped sessions stay stopped until Vincent restarts selected owners.

Task-named worktrees require Vincent's archive decision through Game. Dirty/untracked retirement needs an explicit per-item decision. Never delete NSC-### branches; no batch here deletes source branches or remote refs. Preserve the current no-force rule. Present exceptional rows together; a generic cleanup go is not their approval. Task-ref preservation/disposition needed before an independent clone can retire is checked by Game; ambiguity is HOLD.

The proposed narrow extension for Release is publication of the three capture repositories and a named second off-machine copy within an approved run. It grants no automatic game push, force update, ref deletion or future unlimited publication. Documentation records adopted temporary duties.

Default to **retaining the existing originals of unique, dirty and irreplaceable material until a second independently restorable off-machine copy is verified**. A clean redundant copy may proceed when its exact recovery receipts and independently retained counterpart prove redundancy. A fresh local capture on the same PC is not that second off-machine copy. A weaker policy is an itemized decision for Vincent naming affected sources and risk; it is never a timeout or schedule cut.

## 2. One accountable owner per package

| Package | Owner | Deliverable and boundary |
|---|---|---|
| P0 Coverage, disposition and sprint ledger | Cleanup | Single master index, source/store partitions, active exclusions and exceptions; owners attest their own content |
| P1 Capture tooling and source-copy operations | Pipeline Maintainer (PM) | Minimal reviewed adapters/validator and sealed payloads; reads sources and writes approved capture/staging roots only |
| P2 Fleet content specification | Documentation | Exact docs, definitions, NSC memory, custom skills and selected config map; PM writes tooling |
| P3 Runtime/candidate coverage | Game | Applicable control roots, source/candidate OIDs, logs, admissions audit source and protected paths; no live-record editing |
| P4 Art coverage | Art Director | Contract-derived pinned paths/hashes and restored-byte acceptance; no generation or Unity work |
| P5 GER preservation | GER | Drafts, only-copy tool inputs, consumers and contract constraints; PM owns tool code |
| P6 Git-history preservation | PM | Immutable ref/object maps, dirty-salvage interfaces and bundle closure; Cleanup supplies actual stores/reverse consumers |
| P7 Repository provisioning | Release | Reviewed spec/script for three private remotes and dedicated local Git roots; Vincent creates them, refusing unrelated pre-existing contents |
| P8 Publication and recovery-point sealing | Release | Payload/immutable-ref publication, final manifest published last, remote bootstrap and receipts; requires scoped authority |
| P9 Independent recovery verification | Cleanup | Fresh per-candidate remote restores by a helper different from capture authors |
| P10 Retirement scripts/packages | Cleanup | Exact parent-aware actions, dry-run script, fixtures, fresh review and sealed batch |
| P11 Destructive execution | Vincent | Exact reviewed batch execution; Cleanup verifies effects |
| P12 Recovery/lifecycle documentation | Documentation | Bootstrap, adopted scope and shared lifecycle/startup instructions; no installed-enforcement claim |
| P13 Operational visibility | Viewer | Existing status mechanisms when useful; viewer code remains PM work |
| P14 Parked decomposition | Decomposition | Exact-plan decision packet and separately authorized resolution; GER checks graph/policy effects |
| P15 Repeat capture | PM | Rerunnable command and proved second run; Release publishes within actual authority |
| P16 Second off-machine copy | Release | Named destination, executor, access/key recovery and milestone; Cleanup independently restores it before unique-original retirement |

Every producer owns its workspace registration and closure packet; Cleanup owns queue integration, not other roles' source judgments. PM and Cleanup jointly accept one minimal handoff schema: PM owns implementation, Cleanup accepts that it supports candidate decisions. They do not invent incompatible formats in parallel.

**Later engineering owners:** PM owns T1 GER-tool consolidation/Astra follow-ups; L1 the actual common writer mutex; and U1 synchronization/operation IDs/generations/fencing, U2 checkpoints/all mutation receipts, U3 planning/rescue/backfill/crash recovery, U4 semantic create/edit inverse, U5 completion inverse/evidence invalidation, and U6 midpoint reconstruction/resume. GER supplies contract semantics, Game supplies landing/runtime acceptance, Decomposition supplies graph cases, Documentation supplies instructions and Viewer reports state. Game integrates reviewed code on Vincent's direct go; Release pushes under separate authority. No cleanup script is represented as transactional task undo.

## 3. Preparation gate: prove one real vertical slice

Reuse supplied inventories and measurements. Select one small, currently clean, inactive, non-task candidate partition with a known owner and readily recoverable contents. Historical releases are discovery inputs, never fresh receipts. Keep canonical, live control roots, reports/pinned art, tools, profile sources, compatibility junctions, capture stores and the new run-evidence root protected. The review's tmp-ga, review-tmp, unique detached-head worktrees, dirty candidates and unknown stores remain held until their specific proof exists.

Before forecasting Batch A:

1. **Choose exact IDs and interfaces.** Cleanup selects candidate IDs; owners confirm identities. PM/Cleanup accept a minimal schema, worked example, error states and expected-input list. Partition by resolved common-store identity and reverse consumers. No whole-project recount is needed.
2. **Name installed primitives and missing code.** Record executable versions and exact commands for file capture, Git export, publication, remote-only restoration, validation and deletion. Existing Git/file commands may suffice; missing adapters/runners are explicitly authored. Never use the old bulk movers or their empty restore log as proof.
3. **Make runnable dispatch cards.** Confirm backend/account/model/tools, input visibility, output mechanism and bounded command. Inaccessible host data needs an approved staged input or host-owner route.
4. **Check capacity and remote eligibility.** Measure headroom for originals plus capture and independent restore. Check blob/pack/upload eligibility before importing a blocking object into a shared publication. No deletion to make scratch room before its own gates pass.
5. **Implement and independently review only necessary code.** Prove Windows reparse, missing/unreadable/new input, ignored-log, writer-race, changed-ref, interrupted-operation and rerun fixtures. Capture/history review belongs to PM; deletion review to Cleanup; reviewers are fresh.
6. **Run the real recovery slice.** Under current writer holds, capture the selected real partition; publish payloads/refs then the final remote manifest/bootstrap; independently restore from that exact remote manifest without access to original stores. Include second-copy proof if its retention class requires it.
7. **Seal a real action package.** Bind exact paths, reverse dependencies, holds, complete fingerprints, script/manifest/review hashes and permission class. Run its real dry run. This proves a package can be prepared, not that deletion occurred.
8. **Measure and reforecast.** Record preparation and parent-review time, bytes, I/O/uplink/readback rate, space, errors and human latency. Publish the measured forecast and concrete authority packet. Vincent's execution and Cleanup's verified result complete the path.

Ready mapping, fixture-design, documentation and provisioning cards run concurrently. Broader capture rolls per ready partition after these contracts are proved. Unknown historical cases hold their own candidate/store group, not every safe batch.

## 4. Helper fanout: proposed roles become runnable cards

Keep many helpers and no artificial four-helper ceiling. These 17 roles are a proposed roster, not executable launches or evidence that twelve host jobs have access now. Launch every independent ready card within actual account/job budget and capacity. Prefer bounded deliverables to long sessions.

| Job | Parent | Deliverable | Prerequisite |
|---|---|---|---|
| H01 Fleet mapper | Documentation | Docs/agents/memory/config fragment | Accepted schema and verified host visibility or staged packet |
| H02 Tool/draft mapper | PM with GER attestation | Real tools/drafts, authority/caller paths | Same; no tool edits |
| H03 Art verifier | Art Director | All 40 pinned paths and expected/current hashes | Contracts/reports and permitted file access |
| H04 Runtime mapper | Game | Control/source/candidate/log map and active exclusions | Current records; no mutation |
| H05 Quarantine examiner | Cleanup | Assigned refs, dirty/ignored needs, bundle dependencies | Explicit disjoint store IDs |
| H06 Worktree examiner | Cleanup | Linked worktrees/common stores/reverse users | Store index; distinguish standalone task clones |
| H07 Clone examiner | Cleanup | Other stores, nested repos and local-origin consumers | Disjoint IDs excluding H05/H06 ownership |
| H08 Non-Git examiner | Cleanup | Bounded files/dirs, valuable bytes and proven cache exclusions | Named paths; nested stores returned to index |
| H09 Adapter author/tester | PM | Minimum adapters/validators and fixtures | Frozen example/schema; permitted development root |
| H10 Fleet packaging role | PM | Sealed fleet bytes/stability manifest | Accepted maps/reviewed commands; host owner or deterministic script writes |
| H11 Evidence packaging role | PM | Reports/control/log/dirty-salvage partitions | Same; exact logs/final drain |
| H12 History import role | PM | Immutable ref/object closure | Accepted store map/preflight/reviewed commands |
| H13 Remote preparer | Release | Provisioning/publication/second-copy cards and bootstrap | Named destinations; authority before mutation |
| H14 Recovery verifier | Cleanup | Exact-remote restoration receipts | Published final manifest; independent of authors |
| H15 Batch author | Cleanup | Runner/fixtures/action package | May start on fixed fixtures; real receipts bind before seal |
| H16 Capture/history reviewer | PM | Fresh review of exact adapter/export candidate | H09/H12 candidate; no self-review |
| H17 Deletion reviewer | Cleanup | Fresh script/race/recovery/rerun and exact-batch review | H15 candidate; final changes reviewed before seal |

Use existing helper types only when their real contract fits. A read-only host lookup can return structured data through the runner's captured response; it is not silently granted Write/Edit because a table calls it a packager. Approved deterministic host scripts or the authorized host owner perform capture writes. Docker needs suitable standalone clones/compose and staged input/output routes; it does not automatically see profiles, arbitrary control roots or linked object stores. The inspected runner rejects linked-worktree Docker roots, Docker --agent and host-style --add-dir assumptions. Verify the installed route; do not improvise broader permissions.

Each dispatch card specifies:

- Card/job/parent/run IDs; exact backend, account, model, helper type and budget.
- Verified executable version, tool allow-list and bounded executable command; missing command means NOT READY.
- Immutable input/digest or exact host read roots; source/store partition and no-go paths.
- Fresh registered work/output location, approved output channel/mount and verified access probe on non-sensitive fixtures.
- Required artifacts/schema, expected IDs, validator, foreground/awaited supervision, timeout/error behavior and completion evidence.
- Dependencies, resource class, parent reviewer, log/closeout destinations and recipient.

A background scan must remain attached/awaited. Exit zero without a nonempty valid artifact fails; nonzero is not ignored because a file exists. Parent acceptance validates coverage and relevant facts. No recursive delegation, self-review or helper-to-fleet messages.

**Global resource limit: at most two heavy operations across all owners**, including clone creation, object traversal/hash, capture, compression, publication, restore and large verification. A job name does not make it light. Cleanup maintains the shared slot ledger; PM/Release report starts/completions. This is an operating rule, not an installed scheduler. Cheap drafting, schema checks and bounded metadata work can run concurrently. A job that becomes heavy obtains a slot. One writer per capture repository/master ledger, one publisher per destination and one actual source writer are separate limits. No duplicate full-disk scans. This sprint needs no Unity job.

Budget parent-review time: PM's capture/history acceptance and Release's publication are real serial constraints. Wake Viewer for useful status work, not every handoff.

## 5. Mandatory sources, reverse dependencies and stable inputs

Every adopted source family gets a mandatory row, even if its first result is HOLD. Batch A coverage never substitutes for this list.

| Required family | Content/discovery owner |
|---|---|
| C:\NSC top-level docs/scripts, agent-state, tools and selected nonsecret project config | Documentation; PM attests tools |
| C:\nscrev\reports, pinned art, reviews/handoffs and provenance | Cleanup maps reports; Art accepts pinned bytes |
| GER revisions area, ger-tools-dev, only-copy tools/drafts and nested stores | GER; PM tools; Cleanup store partition |
| Every applicable .assistant-control root, including C:\NSC\NSC\.assistant-control; records, journal, outputs, historical/gauntlet logs | Game |
| Source-common admissions audit data | Game; audit only, never restored as active leases |
| Real .claude agents, NSC memory, custom NSC skills and deliberately selected nonsecret settings | Documentation; no broad personal-profile copy |
| %LOCALAPPDATA%\nsc-astra, NSC claude-jobs/codex-jobs, session digests and other NSC stdout/stderr/prompts/answers/metadata | Producing owners supply exact paths; Game/PM consolidate |
| Named external inputs, including NSC-007 summary under Downloads\NoSafeCircleOutput | Decomposition; exact file paths |
| Independent stores, bundles, detached/ref/reflog/candidate history and dirty salvage | Cleanup discovers; PM captures |
| Sprint helper/runner logs, manifests, reviews, fixtures, publication/restore/deletion receipts and lifecycle registry | Each producing parent; Cleanup owns final coverage |

Use a stated capture cutoff and source/log generation. All logs remain valuable even inside Library, Temp, obj, ignored paths or otherwise reproducible caches. Preserve them before classifying other bytes as disposable. New sprint outputs join coverage through their parent's registration/closeout.

Each missing source, unreadable input or open tail has an exact retained path, owner and next capture milestone. **Final drain is mandatory for every retiring candidate:** stop/settle its known writers under the hold, capture through the cutoff, restore every log byte and recheck before retirement. A moving sweep is ineligible. At close, finish producer logs and publish a final evidence generation containing their results. Still-running producers retain their paths with explicit pending generations. Full durability is only claimed as of a complete named-source cutoff. Capture-process logs produced afterward belong to an explicitly owned next generation, never an invisible exclusion.

Build a **reverse-dependency map**, not just a source list. Stable store IDs include resolved common-directory identity. Distinguish .git directories/files, linked worktrees and standalone task clones. Map reverse users: gitdir/commondir, alternates and supported object-store indirections, local remote URLs, nested repos, submodules/LFS, task records, callers/imports, launcher config and process use. Preserve local Git config/provenance needed to rebuild behavior, handling secrets deliberately; trees alone do not preserve it. A candidate must have no unresolved reverse consumer, or each surviving consumer must have a verified repair accepted by its owner. Unknowns hold that store group. One job owns each shared store; others contribute references rather than independently retiring it.

A **retirement hold** names candidate/store group, writers/launchers, current acknowledgements, children/consumers, start time, capture window, revocation and completion state. Keep it through final drain, stable capture, publication, verification and deletion. Stop or exclude unaccounted automation. Owner silence, stale release, a viewer marker or journal entry is not exclusion. Expiry/lost acknowledgement stops progress; it never reopens a path underneath a running operation. Unrelated retained paths keep working.

The sealed **fingerprint** includes:

- Resolved path/type and complete directory-entry inventory, including hidden, untracked, ignored, unexpected reparse and nested-repo entries.
- Every file's byte length/SHA-256, including hidden, untracked and ignored files; explicit deletions/discard classifications and reconstruction metadata.
- Symbolic/detached HEAD, refs/full OIDs/types, index/staged/unstaged state, and retained stash/reflog choices.
- Git/common-store identity, required config/provenance, worktree membership and object/config dependencies.
- Known consumers/writers, hold identity, capture start/end, cutoff/generation and stable-input comparison.

Require complete pre/post equality under the acknowledged hold. New, missing, unreadable or unknown entries are HOLD. Recheck the full fingerprint immediately before each destructive item; HEAD equality and ordinary git status are insufficient. Earlier reviewed actions in the same dependency-ordered batch may produce only explicitly modelled changes. Any other mismatch stops the batch. Prove Windows writer-race behavior; no claim is made that a prompt or viewer overlay is a filesystem lock.

## 6. Recovery contract: final remote manifest last

Use immutable packages under C:\nscrev\reports\cleanup-runs\<run-id>\<package-id>, a protected root. One ledger writer indexes package IDs; helpers write separate partitions. Schema fields bind owner/run/package/tool/schema IDs, expected/completed input IDs, digests, timestamps/cutoff, source/store identities, locations, errors and explicit unknowns.

Before first content add, commit root .gitattributes with * -text, set core.autocrlf=false and appropriate long-path settings. Disable applicable clean/smudge/encoding conversions for capture payloads and inspect inherited attributes/config. Verify source and restored bytes: object names alone do not prove this, as the earlier default-clone mismatch showed.

Before import/commit/push, inspect file/blob and pack/push eligibility against actual destination limits. The adopted baseline uses segments below 40 MiB where necessary and accounts for GitHub ordinary 100 MiB blobs/2 GiB pushes; Release verifies limits at execution. Preserve reassembly metadata. Oversized history holds its partition until a complete supported destination or segmented bundle route is proved. Never rewrite original history to fit. Generalized segmentation can wait; required current handling cannot.

Publish in this order:

1. PM seals payloads and ref/object maps with stability/closure evidence.
2. Release publishes every referenced fleet/evidence payload commit and immutable history ref; confirms remote identities/OIDs. Never mirror-push, force-update or overwrite prior captures.
3. Release assembles, commits and publishes the **final nsc-evidence recovery manifest last**. It references uploaded dependencies, remotely stored bootstrap/restore instructions, source map, tool/schema version, bundle prerequisites, hashes and object identities. Its commit is the recovery-point ID; it does not include its own hash.
4. Cleanup's independent verifier obtains that exact manifest/bootstrap from remote alone without original-machine data, source alternates, hardlink borrowing or hidden local prerequisites. Restore every candidate payload/object, parse records and validate required hashes/schemas.
5. Release provides the named second off-machine copy; Cleanup independently restores it for sources requiring that protection. Name destination, access/key recovery outside this PC, receipt and milestone. A local synced file is not upload proof.

| Handoff | Artifact and receiver check |
|---|---|
| Owners -> PM/Cleanup | sources/dependency fragments; assigned IDs, presence, paths, owners and permissions reconcile |
| PM -> Release | files/refs/closure manifests and actual payloads; hashes/OIDs, size preflight, stable inputs and no omitted logs |
| Release -> verifier | Exact final-manifest commit and bootstrap; all dependencies retrievable remotely |
| Verifier -> Cleanup | recovery.json binds manifest commit, tool/schema versions, every comparison, store independence and errors |
| Cleanup -> reviewer/Vincent | Action/disposition manifests, runner, README/review bind exact paths/actions/holds/fingerprints and hashes |
| Vincent -> Cleanup | Per-item intent/result and aggregate status; verify effects, retained recovery and actual reclaimed space |

Dirty salvage retains actual bytes, staged/unstaged meaning, deletion markers, untracked and valuable ignored files; patches alone fail. Retain candidate OIDs from every root, detached heads, annotated tags, selected stash/reflog entries and full bundle prerequisites. Restore or eliminate external alternate/submodule/LFS dependencies explicitly. Art's expected hashes must match restored bytes. Every deletion candidate is restored, never sampled.

P16's milestone is before unique/dirty/irreplaceable originals enter a ready batch. P15's is a successful repeat capture and authorized publication before claiming ongoing protection. If blocked, name executor, destination/access or next exact authorized boundary; retain affected originals and keep that completion status false. A generic promise to return later does not close either package.

## 7. Candidate acceptance and execution

A ready candidate has resolved identity/store/reverse consumers, active writer holds, a matching full stable fingerprint, exact remotely committed recovery manifest independently restored, final log drain, applicable second-copy protection, actual per-item authority, and matching sealed script/manifest/review hashes.

The runner is dry-run by default and uses exact literal absolute paths in one shell. Validate resolved targets inside explicitly named roots but never the root itself; exclude all protected paths. Reject reparse surprises or unclassified nested stores. No wildcard removal, broad move, reset, branch/ref deletion, Docker/volume pruning or Git force. Retire linked worktrees through the actual parent, children before parent. A surviving dependent blocks parent retirement; a dirty/no-force refusal stays held absent a separate concrete exception.

Omit preflight-ineligible items before sealing. During apply, any changed/new/unreadable entry, lost hold or unexpected error stops the remaining batch and records incomplete status. Preserve successful receipts, reconcile and replan the unfinished subset. Never recapture-and-delete automatically under old approval. Empty quarantine-root removal is separate and nonrecursive after every row is settled.

Vincent's item table names ID/path, actual changes, source/task-branch treatment, remote/second-copy receipts, required authority and action. He may select several named IDs in one response; unselected IDs remain. A weaker unique-original retention policy is a distinct itemized decision.

Batch A and Batch B are opportunities, not deadlines or quotas. Prefer few useful commands, but do not combine unrelated stores or changed authority scopes to preserve a two-command claim.

## 8. Schedule and Vincent's steps

The serial path is:

    accepted schema + exact candidate/store partition + ready commands
    -> reviewed minimum tooling + current holds
    -> stable capture + object/dependency closure
    -> permitted payload/ref publication -> final manifest
    -> independent restore (+ required second copy)
    -> sealed exact action package + review + actual authority
    -> final held-state/fingerprint check -> Vincent executes -> verified result

Preparation, owner attestations, reverse-map partitions, fixture design, provisioning and the parked-plan packet overlap. Capture/upload/restore then roll per ready partition under the global two-heavy-operation limit. Parent stores wait for dependent children; safe individual items do not wait for unrelated quarantine rows.

| Phase | Allowance / trigger | Parallel work |
|---|---|---|
| Preparation and real recovery/action-package slice | Unmeasured 4–8 working hours; section 3 before wider forecast | Every ready independent mapping/review/provisioning card; protected game branch work |
| First modest remote-backed deletion | Approximately 6–12 working hours from kickoff including preparation, conditional on access/history/retention/decisions | Later partitions, all-source coverage, final drains and repeat capture |
| Broader useful cleanup | Provisionally one to two working days; revise after measurement | Remaining independent batches and bounded exceptions |
| Whole landfill closure | No responsible date until dependencies, transfers and owner/exceptional decisions are known | Register/close new work immediately |
| Full task undo | Separate multi-day effort, re-estimated after foundations/crash-recovery prototype | Domain fixtures and isolated implementation |

Do not exclude restarts, credentials, budgets, schema acceptance or Vincent from wall-time reports. A second-copy delay for unique sources holds those sources; proven redundant copies can continue.

Prepare complete packets before asking Vincent:

1. **Kickoff:** restart selected owners; adopt temporary duties/lifecycle contract; authorize an actual helper/account budget. Cards show real tools/access/commands; no forecast assumes all roles runnable.
2. **Provisioning/publication:** run the reviewed script for three private remotes/local Git roots. In Release authorize named run, destinations, append-only namespaces/payloads and expiry, including concrete second-copy scope. List access/key recovery without exposing secrets.
3. **Decomposition, independently:** review exact NSC-007 plan/run/hash and fresh compatibility in Decomposition; approve, abandon or leave pending. The recorded old NSC-015 plan is stale and cannot be applied. Preserve records and referenced Downloads outputs first.
4. **First batch when proved:** receive measured slice report, exact actions and recovery/retention receipts; run one manifest-bound command. Named task/dirty decisions remain required.
5. **Later batch if ready:** select exceptional IDs and run its reviewed command; otherwise retain sources and report blockers.
6. **Separate code release only:** approve an exact reviewed merge in Game. Cleanup needs no game merge, Unity, in-game test or new art; archive publication does not authorize game-main pushes.

Pending decomposition holds graph/contract/new-task/policy writes, not copying or unrelated branch work. Fresh inspection determines integration compatibility; never reuse an old apply SHA after main advances. No timeout abandons a plan or releases its freeze.

Until real common locking covers every writer, Game coordinates acknowledged short main-write slots; GER and Decomposition execute their own authorized writes. Name owner/operation/expected HEAD/paths, then close with verified before/after HEAD/evidence. Account for unattended publishers. Silence or timeout requires reconciliation, never the next writer. main_write.py remains an audit aid, not a mutex. Hashing, uploads and reviews do not occupy the source-write slot.

## 9. Prevent recurrence through producer registration and closeout

Use the [shared lifecycle policy](C:/NSC/nsc-workspace-lifecycle-policy.md) and revised [Cleanup guide](C:/NSC/nsc-cleanup-agent-guide.md). Documentation owns instructions; PM owns future launcher enforcement. This plan installs no scheduler, registry writer, interception hook or automatic deletion.

Before creating a persistent workspace, its producing owner registers ID, owner, task/job/run, exact path, source commit, Git kind/common store, output/log roots, protected dependencies and intended closeout. Use approved roots and unique outputs; register an exception before an ad hoc path. Start with active protected workspaces and incoming jobs; import historical rows as inspected.

The **parent producer owns closeout** on success, failure, timeout, interruption and abandonment: refs/OIDs, dirty/untracked/ignored classification, every log/output, active descendants, pending publication, known consumers and retirement intent. Helper exit is not parent closeout. Replacement sessions inherit open workspace IDs and pending operations.

Cleanup maintains one durable index using the shared policy states: registered, active, closing, released, recovery-verified, batch-ready and retired, with held as an explicit exception state. Keep closeout-needed, preserve-needed and decision-needed in separate blocker/next-action columns, not a second lifecycle. Each blocker names owner/next evidence. Process incoming closures and a bounded stale-owner list, with periodic reconciliation of registered roots to find unregistered births. Silence, age, TTL or empty restore logs never authorizes retirement.

Prefer stable per-run evidence roots outside disposable clones. Existing hash-bound paths stay valid. Clone-local logs remain listed/preserved. Protect the registry and Cleanup's own outputs. Cleanup produces sealed human batches; Vincent executes. Notify on useful ready batches, owner decisions or capacity problems, not unchanged periodic prose.

Measure new versus closed/retired workspaces, unregistered paths, unresolved-closeout age, archival versus approval backlog, recovery age and actual retained/reclaimed space. A quiet queue with growing unregistered clones is failure. Creation concurrency uses measured headroom/ownership and the global heavy limit.

## 10. Continuation and completion

After the slice, PM can develop repeat capture/scheduling and L1 in isolated branches while Cleanup closes safe rows. Domain owners prepare U-package fixtures concurrently. Agree receipt/checkpoint/generation interfaces before dependent implementations; integrated-head independent review/failure tests precede live undo claims. U6 needs real capture, fencing and inverses, not merely a CLI.

Defer generalized collectors when reviewed primitives suffice; broad tool migration/schema-writer ports; midpoint backfill and all six undo packages; viewer code; broad path rewrites/junction retirement; experiment integration decisions; branch pruning; Docker/volume cleanup; and active-workspace rearrangement. Owners remain assigned. Required blob handling, topology, stability, every-log coverage/final drains, independent recovery, unique-original second-copy protection and authority are not cuts.

Cleanup's report uses receipts:

- **Execution:** wall/active and preparation/review time, bytes/rates/headroom, revised forecast and bottlenecks.
- **Protected:** every mandatory row, exact final-manifest IDs/cutoffs, independent/second-copy receipts, missing rows/open generations.
- **Deleted:** exact IDs/actions, parent/worktree outcomes, verified absence and reclaimed space.
- **Active:** owner, purpose, registry ID and protected dependencies.
- **Held:** exact blocker, owner, retained original and next concrete evidence/decision.
- **Ongoing protection:** repeat result and authorized next boundary/tested schedule; no continuous claim from one capture.
- **Prevention:** registrations/closeouts, unregistered births, pending parent packets and ready human batches.
- **Deferred engineering:** T1/L1/U1–U6, without implying implementation shipped.

A batch may finish while others are held. Full durability remains incomplete until every named source is covered; the project is not clean while unclassified, unpreserved or unclosed work remains. Ready parallel jobs and partitioned recovery accelerate this work while producer closeouts stop new clutter from accumulating.
