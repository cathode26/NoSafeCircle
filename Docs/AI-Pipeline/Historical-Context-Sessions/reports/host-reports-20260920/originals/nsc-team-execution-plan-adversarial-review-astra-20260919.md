# Adversarial review — NSC team execution plan

**VERDICT: FIX FIRST. Safe architecture for a staged cleanup, but not a dispatch-ready 2–4-hour execution plan. Do not approve deletion from these documents alone.**

Independent Astra review, 2026-09-19. I first inspected the project and wrote `C:\nscrev\reports\nsc-project-analysis-astra-20260919.md`, then sent the analysis-complete milestone, and only then read the execution plan and revised brief. No cleanup, runtime change, Git mutation, provider launch or external peer message occurred. Only these two reports were written.

The user's extra caution about the repository landfill is justified. This plan is materially better than indiscriminate quarantine or age-based removal. Its explicit gates would prevent many failures **if implemented**. The main defect is presenting their future implementation, ownership and verification as a short schedule without ready source partitions, runnable jobs, schemas or demonstrated recovery. Keep its structure; close the concrete gaps below before committing to deletion times.

Inputs: `nsc-team-execution-plan-20260919.md` (PLAN), `astra-team-execution-prompt-20260919.md` (BRIEF), `nsc-durability-cleanup-and-undo-plan-20260919.md` (DESIGN), all under `C:\nscrev\reports`. Parent-supplied initial SHA-256 values: PLAN `9255DA1F1F463216A6E916FE1E7699D4D34F755CB91EE384562F763EC69B8534`; BRIEF `2C7454C9484CC99B0ACFC3B9C3C75A648820EC173F5D3DB96E821F44ABD43AB8`; DESIGN `E1B367749E5FECF3D6FB0CFBFBE8F13135B902097CABDEF8AADFC7CAD490561B`. These are provenance supplied at review start, not independent hashes claimed by this reviewer.

## Prioritized findings

### 1. HIGH — The preparation phase is missing from the advertised clock

**Evidence:** PLAN:93–109 makes H09 adapter/validator development and H15 deletion-runner development real jobs; H10/H11 wait for H09, H16/H17 review those new implementations. PLAN:131–134 nevertheless expects schema, mapping, provisioning, first capture, review, publish, remote restore and deletion in 2–4 hours. PLAN:211 treats building tooling from scratch as an eventuality. DESIGN:5 explicitly says named command interfaces are not implemented. The inspected existing bulk mover is unsuitable: `C:\NSC-History-20260918\MOVE-NSC-FOLDERS.ps1:68,708–718,875–877` and `RESTORE.ps1:53–64`; the cleanup guide:167 already stops it.

**Failure scenario:** H01–H08 produce incompatible inventories while H09 guesses the schema; H15 assumes a different fingerprint or cache-exclusion rule. PM and Cleanup spend the first hours reconciling artifacts and fixing Windows edge cases. Pressure to meet the announced first-deletion window then turns a fixture pass into acceptance of a real destructive package.

**Minimum correction:** add an explicit preparation gate before the deletion forecast: freeze a minimal schema/example, choose one concrete Batch A partition, name existing primitives and exact new code, implement capture/history/restore and deletion runner, independently review Windows failure fixtures, and complete one real remote round trip. Schema ownership is joint PM/Cleanup acceptance, not parallel invention. Publish a measured estimate after this vertical slice. Do not require a generalized backup framework; do require the minimum runner the plan already promises.

### 2. HIGH — “17 jobs” is a roster, not an executable helper allocation

**Evidence:** PLAN:89,111,123 promises 8–12 light jobs, custom helper types, Windows packaging and complete packets. H01/H02/H04–H08 require host/profile/control-root/topology access. `C:\NSC\tools\jobs\run_job.py:323–360` requires standalone clones and rejects linked worktrees; :502–506 requires compose.yaml; :1136–1140 refuses Docker `--agent`; :1188–1193 makes `--add-dir` host-only. Host types at :134–153 are read-only; :433–463 prevents adding Write/Edit to such a type. `compose.yaml:39–62` does not expose arbitrary host sources. PLAN supplies no per-job backend, account, executable command, input staging route or approved output mechanism.

**Failure scenario:** a mapper launched in Docker cannot see `.claude` or a linked worktree's real object store. A packaging helper assigned a host-lookup profile cannot perform its expected writes through the intended tool contract. Parents compensate by doing the work themselves, or broaden shell permissions ad hoc. Eight simultaneous “light” examiners also end up hashing the same objects.

**Minimum correction:** one dispatch card per ready job: owner, exact backend/account/model, immutable input packet or named host read roots, approved output route, fresh output directory, bounded command and evidence of relevant tool access. Use host owners/deterministic scripts for actual packaging; helpers can design/review scripts and return data via the runner's captured response. Do not silently turn host lookup into a general mutation job. Budget the owner review time and disk work, not just provider calls. Start all genuinely independent cards once ready; there is no reason for an artificial four-helper ceiling, nor evidence that twelve are ready now.

### 3. HIGH — Path holds and “mechanically evaluable” deletion predicates still lack an operational proof

**Evidence:** PLAN:47,170–181 specifies releases, current fingerprints, dependency exclusion and final checks, but no fingerprint contents, hold record lifecycle or exact consumer check. Existing main-write code is explicitly inadequate: `C:\NSC\tools\ger\main_write.py:85–113` scans a time-limited role journal then appends, with no mutual exclusion. `Pipeline/AssistantControl/checkouts.py:29–44,104–135` binds absolute source/checkouts to independent clones and records; individual JSON atomic replacement (:18–25) is not a cross-file snapshot. The former cleanup queue includes owner-silence and stale extraction assumptions, so a prior “released” line cannot be current retirement authority.

**Failure scenario:** after final status/hash inspection, a resumed session or unattended publisher writes one ignored result into the candidate. A directory removal deletes the new only copy. Alternatively refs and journal are copied at different moments and a restored record refers to an absent candidate. A final HEAD equality check sees neither error.

**Minimum correction:** for each batch, name all known writers/launchers and obtain a current path-specific acknowledgement through the whole operation, stop or exclude unaccounted automation, and seal a fingerprint covering files including ignored/untracked entries, refs, HEADs, Git identity/config dependency data and directory entries. Any new/unreadable entry is HOLD. Record capture start/end and stable-input results; deletion candidates require sealed stable captures, while live nontransactional captures are explicitly ineligible. Recheck immediately before each destructive item; mismatches stop. Prove this with a writer-race fixture on Windows. This does not require implementing full task fencing before cleanup: uncertain candidates stay, unrelated game work continues.

### 4. HIGH — Topology discovery must be an explicit reverse-dependency product, not only a source list

**Evidence:** PLAN:98–100 partitions by folders/stores, :145 addresses parent/worktree order, and :166 mentions alternates/LFS/submodules. However its source contract (:159) has a generic “active dependencies” field rather than a defined all-store reverse dependency map. The prior inventory proves multiple parent stores (DESIGN:31) and the measured 138 worktrees are not all canonical children. The actual task preparation uses `clone --no-local`, not Git worktrees (`checkouts.py:121–126`). Owner ledger `C:\nscrev\reports\cleanup\owner-replies-20260918.md` explicitly retains review-tmp despite another owner's release and identifies protected art refs.

**Failure scenario:** an independent clone looks clean and fully archived, but a retained checkout uses its `.git/objects` through alternates, a linked gitdir, or a local-origin workflow. Deleting it breaks that survivor. A top-level non-Git row can also contain nested stores or valuable ignored outputs. Parallel H05/H06/H07 each believe another job owns the dependency.

**Minimum correction:** partition once by stable resolved common-store identity, with each worktree/clone/path mapped back to it. Include reverse users: gitdir/commondir links, alternates and supported object-store indirections, local remote URLs, nested repos, submodules/LFS requirements and task/caller references. A candidate must have no unresolved reverse consumer, or each consumer must have a verified repair accepted by its owner. Preserve config/provenance needed to rebuild intended behavior; Git trees alone do not preserve local config. Shared store groups must not be independently retired by two jobs. Unknown reverse dependencies are candidate-specific HOLD, not a reason to freeze the whole project.

### 5. HIGH — The compact handoff contract does not fully bind the adopted recovery point

**Evidence:** DESIGN:77–81 requires byte-preserving attributes before content, conversion controls, segmentation and push-size handling; :98 requires the recovery manifest to be committed **after** uploaded dependencies, its commit becoming the recovery ID. PLAN:160–168 asks for hashes/OIDs and independent restoration, but does not specify that final manifest commit/seal order or a bootstrap mechanism for a reviewer with no original machine. PLAN:222 defers generalized segmentation unless needed, without an explicit pre-import size gate. Tools-move-review-20260919.md, B2, records a prior actual default-clone byte mismatch in 128/176 files.

**Failure scenario:** payloads restore during today's drill using local package manifests, but the PC dies and those manifests were never in the hosted recovery point. Or first import contains one oversized historical object, blocking a publication containing otherwise easy candidates. Or inherited attributes/filters alter captured tools/log bytes.

**Minimum correction:** make H13/H09/H12 explicitly own byte attributes/filter control, bounded blob/pack eligibility checks and a self-contained recovery bootstrap. Publish payload dependencies, publish immutable refs, then commit and publish the final evidence manifest referencing them; verify that exact remote manifest from scratch. Store the restore instructions and required metadata remotely too. A recovery receipt binds this manifest commit, exact tool/schema version and all payload identities. Test a fresh restore without local object borrowing and compare every required file/object. Large-object failure holds its partition; do not rewrite original history to fit. The plan's refusal of sampled restores is correct and must survive implementation.

### 6. MEDIUM — “Selected families” permits a useful first batch but leaves every-log durability unfinished

**Evidence:** BRIEF:12 narrows protection to selected source families. PLAN:168 preserves every byte *captured* and permits pending tails; :226 makes a second capture merely preferred. DESIGN:68–71 explicitly includes all control roots, gauntlet/historical logs, profile-adjacent Astra output, job outputs and session digests. PLAN's jobs themselves create additional logs while the source map is being captured.

**Failure scenario:** the closeout truthfully reports protected selected families, yet helper logs, Downloads plan summaries or `%LOCALAPPDATA%\nsc-astra` were never assigned a source ID. That is not deletion data loss if those paths remain protected, but it underdelivers the user's durability goal and can become loss during a later cleanup.

**Minimum correction:** use the adopted named source list as mandatory coverage rows, include newly produced sprint evidence and set an explicit capture cutoff/generation. Every missing row/open tail has an exact retained path, owner and follow-up capture. Final drain of retired candidates is mandatory; every log in a deleted path must be restored exactly. Overall durability completion requires full named-source coverage, not just the chosen Batch A. No new broad recount or repeated secret scan is needed.

### 7. MEDIUM — The two-copy and repeat-capture cuts need stronger closeout ownership

**Evidence:** PLAN:189,224 and BRIEF:104 explicitly propose deferring the second off-machine copy; DESIGN:109 requires it and :283 explains correlated account failure. PLAN:226 leaves later publication dependent on future approval.

**Failure scenario:** “cleanup complete” becomes the practical end of the effort, while only one hosting account and one local disk retain the original histories; new fleet changes accumulate after the one-off capture. No individual deletion gate fixes account-level loss or backup staleness.

**Minimum correction:** given the user's explicit extra caution, default to retaining the existing originals of unique/dirty/irreplaceable material until the second independently restorable copy exists; allow redundant copies with proven independent retention to proceed. Any weaker scope remains a clearly itemized user decision. Name the second-copy executor/storage/access recovery and a concrete follow-up milestone. Require a successful rerun before claiming ongoing protection. This is not a fifth Git repository requirement.

## What survived scrutiny

- Four remotes total, narrow real-file capture roots, no tracking through junctions, and retained live paths are sound.
- Separating first cleanup from full transactional undo, semantic experiment adoption, broad tool migration and Unity work is the right scope cut. Full undo is a separate multi-day engineering effort with serial integration/failure tests.
- Producer/reviewer separation, per-candidate remote restoration, exact manifests, no force/default destructive operations, Vincent executing deletion, and protected capture stores are necessary and correctly stated.
- Current NSC-007 JSON was observed as `review_ready`, run `decomp-nsc007-20260918e`, source `2559514826e919bea243e1bf6fda4ad73462ac62`. I did not run its inspection command or validate the complete proposal. Source `decomposition.py:115–138,303–308` really permits an ancestor advance with Tasks/TaskGraph/validation policy unchanged; the plan is right not to freeze all main movement blindly. The old queue is discovery, not authority.
- The supplied baseline already establishes game source at origin at that point. Re-running a global inventory or three secret scans is not a prerequisite. Unknown historical value can default to archive rather than integration review.

## Timing and real concurrency

**Earliest useful cleanup:** verified reproducible caches or a very small previously released redundant partition can plausibly finish in 2–4 hours, provided its script and recovery proof are already ready. That is a conditional opportunity, not today's demonstrated readiness. The owner ledger supplies candidates (ci-fix-stale-viewer-ids, ci-fix-unity-whitespace, cj-ws-advice and others), not current safe-delete receipts.

**Conservative planning allowance from the inspected state:** 4–8 working hours to prepare and prove the first complete capture/publish/remote-restore/deletion slice; approximately 6–12 working hours to the first modest remote-backed deletion if there are no broken histories, access delays or large-file problems. These are assumption-based allowances, not measured forecasts. A broader useful cleanup can occupy one to two working days; complete landfill retirement cannot responsibly be dated until disposition, transfer throughput and exceptional decisions are known. Full task undo has no defensible hours estimate. Reserve a separate multi-day implementation/review effort and re-estimate after a real crash-recovery prototype.

The critical path is schema and real candidate selection -> tooling/review -> stable capture and object closure -> permitted publication -> fresh independent restore -> sealed exact action package/review -> Vincent -> final verification. Nine sessions starting, scoped approval messages, remote provisioning and PM/Cleanup acceptance are real latency, even if excluded from a chart's time zero. Report wall time from the user's go as well as active work time.

Run simultaneously: independent source attestations; topology partitions sharing one immutable store index; adapter authoring versus independent fixture design; provisioning preparation; parked-plan packet; per-partition capture/upload/restore once prerequisites exist. Keep the first two heavy streams global, including clone creation, hashing, compression and verification. “Light” classification by job name is insufficient. PM's H09/H10/H11/H12/H16 acceptance and Release publication remain serial bottlenecks. Wake Viewer only for a useful status action; it need not be on every handoff. Keep many helpers, but launch only ready cards and roll completion into the next card.

## Concrete holds and approval prerequisites

Keep canonical, live control roots, reports/pinned art, tools, all six compatibility junctions, profile sources, capture stores and the new cleanup-run evidence root protected. Keep tmp-ga, review-tmp, the three unique detached-head worktrees, dirty candidates, unknown parent/alternate stores and unreconciled NSC-### task worktrees held until their specific proof/authority is present. These are named discovery targets; this report does not certify their current state. Never run the old bulk movers or infer dispensability from an empty restore log.

Before approving a first destructive package require:

1. Concrete assigned candidate IDs and a closed dependency map, current owner/launcher releases, and no unknown overlapping store.
2. Runnable reviewed Windows scripts plus race, reparse, missing-file, changed-input, interrupted-operation and rerun fixtures.
3. Remote committed recovery manifest, immutable retained objects, exact dirty/index/untracked/ignored/log/pinned-byte coverage, and fresh per-candidate restoration without source access.
4. Sealed action hashes, per-item permission class, child-before-parent operations, current complete fingerprint and a maintained retirement hold through execution.
5. Explicit retained originals/second-copy scope and continued-capture obligation; no claim that a partial batch completes full durability.
6. Enough disk headroom for capture plus independent restore while originals remain, measured first-partition I/O/uplink rate, and a revised forecast. No deletion to make scratch room before its own gates pass.

## Verification limits

This was a source/document review, not a running-system or restore audit. No benchmark, Docker/provider launch, live process/handle census, network fetch, repository provisioning, tests or destructive dry run was performed. Source paths and line references support the findings; historical measurements remain attributed to the supplied baseline and earlier reports. I cannot certify any folder safe to delete, the current remote retention of all refs, available provider quotas, actual eight/twelve-job throughput, or the ability of an unimplemented runner to satisfy its contract. Those are exactly the proofs the preparation gate must produce.

## Added user objective: prevent recurrence and review the Cleanup role

**Separate finding — HIGH: the live role still teaches unsafe/stale rules that the proposed sprint rejects.** Changing only the sprint plan would leave future successors loading them again.

Exact evidence in `C:\NSC\nsc-cleanup-agent-guide.md`:

- Line 172 explicitly makes no reply mean no ownership. Silence must mean unresolved.
- Line 184 permits wholesale deletion after an empty RESTORES.md at a date. Empty logs prove neither lack of value nor complete recovery; remove this rule, not merely its date.
- Line 43 groups Unity `Logs` with noise. Logs are categorically retained under the adopted every-log decision, even when other contents of a Library/Temp/obj tree are rebuildable.
- Lines 70–72 use seven-day age and missing references as eligibility signals. They may prioritize inspection, never establish retirement safety.
- Lines 161–163 call worktrees the only irreversible part and the remainder mechanical. Dirty standalone clones, logs, only-copy tools and externally dependent stores have equally consequential loss modes.
- Lines 131,170,183 carry old counts, broad recount instructions and a tools move still described as unassigned although the recorded move is complete. Preserve these as dated history, not current next actions. The current queue likewise repeats empty-restore-log deletion and tools extraction.
- Lines 14–15 say the role removes branches/worktrees while line 33 correctly says only Vincent removes anything. Rewrite the ownership summary to mean prepares verified retirement packages, avoiding contradictory permission language.

**Can Cleanup keep the project organized while Vincent alone deletes? Yes, if it manages intake and closure continuously rather than periodically rediscovering the disk.** It cannot prevent unregistered producers by prompt alone. All creating roles and job launchers must participate, and missing registration must become visible immediately. This is a small operating-contract change first; launcher enforcement is later PM code, reviewed normally.

Minimum prevention contract to adopt through Documentation, without broadening destructive authority:

1. **Register before creating persistent workspaces.** Each producer supplies workspace ID, owner, task/job/run ID, exact canonical path, source commit, Git kind/common store, expected outputs, protected dependencies, and intended closeout. Use approved job/task locations and unique job output paths. Do not create ad hoc root folders to evade a busy workspace. Exceptions are named and registered. Linked worktrees versus independent task clones remain distinct.
2. **The producer owns completion handoff.** Success, failure, interruption and abandoned experiments all produce a closure packet: exact refs/OIDs, dirty/untracked/ignored classification, all log/output paths, active descendants, pending publication and whether the workspace may retire. A producer does not disappear and leave Cleanup to infer intent from file age. Agent replacement carries forward its open workspace IDs.
3. **Cleanup owns one durable bounded queue.** States should distinguish active, closeout-needed, preserve-needed, restore-verified, decision-needed, ready-for-Vincent and retired. Each blocked row has a reason and owner. No deletion on timeout, silence or TTL. Process completed-work packets promptly and a bounded stale-owner exception list; avoid repeatedly scanning all 788 directories. An occasional reconciliation against registered roots catches unregistered births without becoming daily global forensics.
4. **Keep logs out of disposable workspace ambiguity.** Prefer stable per-run evidence output roots from the outset, with all stdout/stderr/provider output retained. When a tool still writes inside its clone, closure must name and preserve that location before removal. Never change existing hash-bound evidence paths casually. Recording a log destination does not prove the file was uploaded; recovery receipts do.
5. **Offer human batches, not human research projects.** Cleanup prepares small sealed packages with verified recovery, exact eligible IDs, effects and holds. Vincent decides exceptional rows and runs deletion. Until he acts, the package is merely ready; storage remains occupied. Revalidate stale packages rather than treating old approval as permission for changed contents. Notifications should be driven by a ready useful batch, a blocked owner decision or a concrete capacity problem, not unchanged periodic prose.
6. **Measure recurrence.** Report newly created versus closed/retired registered workspaces, unregistered paths, age of unresolved closeouts, last verified recovery and actual retained/reclaimed space. Count archival backlog and approval backlog separately. A quiet queue with an increasing number of unregistered clones is failure. Limit concurrent workspace creation using measured disk headroom and job ownership, not an arbitrary session count.
7. **Keep code and authority lanes.** Cleanup does read-only verification, ledger/packet preparation and receipt checks; PM owns launcher/capture code, Release owns authorized remote publication, Documentation owns the adopted guide/prompt, and Vincent retains destructive execution. A successor's start prompt must load the current registry, policies and unresolved operations, reconcile actual state and reject historical permission claims. No standing automation is activated by this review.

A registry plus completion handoffs is the most direct way to stop another landfill. It does not require full task undo or a new standing agent. The initial retrofit should register the protected active workspaces and incoming jobs first; import historical inventory incrementally as each existing item is classified. Do not delay the first independently proven cleanup batch until every historical row has been made perfect.

Final provenance check: independently computed SHA-256 for all three review inputs at completion; all match the supplied start hashes. Both report files are present and nonempty.

Provenance clarification after document revision: this original review and its line citations concern the pre-revision execution plan, brief, Cleanup guide/queue and shared instructions. Byte-exact frozen copies are now at C:\nscrev\reports\cleanup-role-before-20260919\ with the same filenames; manifest.json records source paths and SHA-256 identities. The reviewer verified every listed frozen copy against that manifest. The current live files may be revised; this report does not imply approval of any replacement execution plan or role instructions. The adopted durability design remains identified by the hash above.
