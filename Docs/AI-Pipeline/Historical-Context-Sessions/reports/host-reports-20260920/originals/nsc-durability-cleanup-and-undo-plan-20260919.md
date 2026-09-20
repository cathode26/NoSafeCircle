# No Safe Circle: the replacement plan

Decision: keep the game repository intact; add three private repositories; preserve unique material before deleting its working copies; build task undo as a new transactional operation.

This plan replaces the storage, cleanup and undo recommendations in the earlier designs. It does not replace unrelated pipeline work. I read all nine requested documents, including the live queue's URGENT section. Your supplied measurements are the baseline; I did not recount directories, worktrees, branches, files or secrets. This is a plan, not a migration already performed. The command interfaces marked **to build** do not exist yet.

**1. Verdict on the existing work**

The game source is already safe: `main == origin/main == 255951482`. The immediate exposure is the scaffolding, unique experimental history, dirty checkouts and uncommitted deliverables. Another inventory or a rearrangement of folders does not close that exposure.

| Keep | Replace or discard |
|---|---|
| The game, Pipeline and task contracts stay together. Port tools that depend on their schemas into that repository. | Splitting contracts into another repo to make task undo easier. It moves the shared registries along with them and changes no task dependency. |
| The tools move, with the six existing compatibility junctions retained for now. | Tracking anything through a junction, including the proposed linked agent definitions and memory. |
| Git for control records and every log; byte-exact art preservation; verified remote copies and restore drills. | v1's snapshot-only control storage, log pruning, broad secret-pattern exclusions, and success inferred merely from an exit code. Your settled decisions override those proposals. |
| Forward contract revisions for undo-edit; cancellation for undo-create; a new undo module. | Extending `reset_task.py`, reverting whole contract commits, or resetting pushed main. |
| Quarantine manifests as evidence of what happened. | The date-based wholesale deletion rule, empty restore logs as proof, and the unreviewed bulk move scripts as executable plans. |
| Explicit checkpoint capture on every real source mutation path. | A completion hook only in `review.integrate`, or merely adding a best-effort hook to `main-write end`. |

**The v1 review is substantially right. V2 repairs several concepts but is not implementation-ready. The topology document is wrong about junction tracking and overstates worktree protection.** Its claim that no checkpoint tuple is needed is also wrong: task recovery already combines source, candidate, contract, records and runtime reconciliation, even if only one repository receives undo commits.

The 88-of-104 result is evidence against path-level contract reverts, not against putting contracts in Git. Undo-edit must change one task semantically and regenerate shared structures against today's graph.

Do not repeat two stale findings as current facts. The later tools review reports Astra working after its code/state split; the remaining issues are default-environment tests, missing `LOCALAPPDATA`, documentation and a mutation harness that changes the live tool. The live queue says restore logging was fixed. That repair is claimed, not proven here; require a full restore round trip before relying on it. The topology document exists now; its absence in the earlier review was timing.

**Additional defects the replacement must address:**

1. **The current main-write journal is not a lock.** A narrow source inspection of [main_write.py](C:/NSC/tools/ger/main_write.py:85) shows a text scan followed by an append, a 30-minute window, and same-role writers excluded from conflicts. Two sessions can pass it. Add real mutual exclusion and durable operation identity.
2. **V2's backup hub can overwrite history despite removing `+`.** Fetches into custom namespaces such as `refs/backup/*` permit non-fast-forward updates without force. Its fallback that waits for rejection is insufficient. Use immutable destination refs from the outset. This behavior is documented in [Git 2.45 fetch](https://git-scm.com/docs/git-fetch/2.45.0).
3. **Reverting a merge does not remove its ancestry.** Simply syncing and merging the old candidate again cannot reliably restore the removed work. Resume after undo-complete must reapply the recorded task changes onto the new main and create a new candidate. [Git revert](https://git-scm.com/docs/git-revert) explicitly describes the merge consequence.
4. **Worktrees can belong to different parent repositories.** The cleanup handoff identifies `wt-base-sessions` as belonging to `C:\NSC\ClaudeProviderSessions\NoSafeCircle`. Canonical's object store cannot be assumed to protect all 138. Detached heads also need retained refs.
5. **An end hook misses the crash between mutation and recording.** Name-based scans miss unnamed changes. V2 also mixes contract writes into C7 attribution while claiming completion reverts never touch contracts. Mutation type and ownership must be explicit before the write.
6. **Astra history moved outside the proposed backups.** Include `%LOCALAPPDATA%\nsc-astra` durable contents, plus NSC job outputs and session digests. Ignoring `*.log` in a tools repo must route logs to preservation, not discard them.
7. **Local Git configuration does not travel with a clone.** Commit byte-preservation attributes in the repository; do not rely only on `info/attributes`. Verify restored bytes, not just object names.

Evidence: [v1 review](C:/nscrev/reports/repo-durability-and-reset-review-20260918.md), [state review](C:/nscrev/reports/state-and-plan-review-20260918.md), [tools review](C:/nscrev/reports/tools-move-review-20260919.md), and [live queue URGENT](C:/NSC/agent-state/pipeline-maintainer-todo.md:370). These are evidence records; the decisions below govern execution.

**2. Repo design: four hosted repositories total**

This count includes the existing game repository and the history archive. It means **three new private remotes**, not four new ones plus a separately counted backup remote.

| Repository | Local storage | Contents and ownership |
|---|---|---|
| Existing `NoSafeCircle` | `C:\NSC\NSC\NoSafeCircle\.git`, unchanged | Game source, Pipeline, task contracts, validation policy and generated/shared task registries. Eventually the contract/main writers and their tests. |
| New private `nsc-fleet` | `C:\NSC-Repositories\nsc-fleet\.git` | Real-file captures of fleet docs, agent-state, tools, agent definitions, memory, project-specific configuration and reproducible setup/backup scripts. Human-maintained material and its change history. |
| New private `nsc-evidence` | `C:\NSC-Repositories\nsc-evidence\.git` | Reports, exact art deliverables, GER drafts, control records and journals from every relevant root, all NSC logs, checkpoint capsules, dirty-work salvage, source maps, preservation/deletion receipts. One retention rule: preserve valuable evidence and every log. |
| New private `nsc-history` | `C:\NSC-Repositories\nsc-history.git`, a bare repo | Retained Git objects and immutable refs from canonical, standalone clones, task candidates, linked worktrees, quarantine and existing bundles. This is also the backup of canonical's local-only history. |

Reports and control do not need separate repositories: both are captured evidence, retained indefinitely and never restored by checking out over live runtime state. Directory-specific history keeps them readable. Keeping their machine-written commits out of `nsc-fleet` preserves useful fleet history. Git object history belongs in a bare repo, not thousands of bundle blobs in the evidence tree.

**Reject `git init C:\NSC` and overlapping external git directories over broad live trees.** External gitdirs can avoid ambient Git discovery, but a verb allow-list is a convention, not a safety boundary. They still expose the whole work tree to a wrong command and require custom handling of ordinary Git operations. Dedicated capture roots give ordinary Git a narrow, disposable work tree. No new `.git` goes at `C:\NSC`, `C:\nscrev` or the user's `.claude` root.

The tradeoff is explicit: live files remain at their working paths; their versioned copies are captures. They are **not a second editable installation**. A source map defines, for every managed item, its live path, repository path, owner, byte hash, expected presence, capture method and restoration method. The collector refuses uncommitted edits in a capture destination that do not belong to its own interrupted transaction.

For now, copy live -> capture -> commit. Later migration of a particular tool to the game repo is a deliberate ownership change. Do not move the documentation tree merely to get a conventional checkout: `CLAUDE.md`, current sessions and existing absolute references make that needless disruption.

**Agent definitions and memory:** copy the actual 14 agent files and 108 memory files into ordinary directories such as `nsc-fleet\claude\agents` and `nsc-fleet\claude\memory\C--NSC`. Capture directly from their real `.claude` locations. Create no `linked\` junctions. On restore, extract into a temporary directory, show the diff, capture the current live version, require its hash still to match, then replace the selected live files. A Git operation in the capture repo never writes into `.claude`. Existing sessions may need restarting or an explicit reread before changed instructions affect them.

Use the same one-way copy and explicit restore rule for docs, state and tools. A future `nsc fleet restore <capture> <item>` command can make this convenient; automatic two-way synchronization is excluded.

**Protect the current paths immediately:**

| Source | Capture treatment |
|---|---|
| Top-level project docs and scripts in `C:\NSC`; `agent-state`; `C:\NSC\tools` | Named source list, real paths only. Classify all 300 top-level files, including non-Markdown files; do not use a silent size cutoff. |
| `C:\nscrev\reports` | Copy all current files. Preserve the 28 fireball and 12 enemy-death deliverables byte-for-byte; verify against contract hashes. Keep their live paths working. |
| `ger-contract-revisions-20260916` and relevant `ger-tools-dev` material | Preserve drafts/tools now; handle nested clones separately through history plus dirty salvage. Do not dismiss small real diffs as line-ending noise. |
| `.assistant-control` roots and `C:\NSC\NSC\.assistant-control` | Enumerate by source identity/project configuration; retain records, journals, outputs and every log. Capture historical/gauntlet logs too before retiring their roots. |
| Source-common-dir admissions data | Copy an audit snapshot under an ordinary evidence path. Never restore it as live ownership. |
| `.claude` agents, NSC memory, custom NSC skills and non-secret settings | Named copy-in mappings. Include a rebuildable config template for machine-specific settings. Do not blanket-copy the whole profile. |
| `%LOCALAPPDATA%\nsc-astra`, `claude-jobs`, `codex-jobs`, session digests and other NSC run output | Preserve logs, answers, prompts and durable metadata in evidence. Exclude transient lock files from restoration. |

Keep the six old tool junctions as compatibility paths, outside every tracked capture path. Retire them only after imports, output paths, READMEs, successor prompts, agent-state, memory, game documentation and existing sessions no longer depend on them. They are cheap and are not today's disk problem.

At a GER quiet point, copy `new_task_commit.py`, `policy_entry_commit.py` and `verify_filter.py` into the real tools home, fix imports, and leave forwarding stubs at old entry points. Preserve the stale local `main_write.py` as historical evidence; never install it over the authoritative version. Port schema-coupled writers into the game repo afterward. Operator tools remain in fleet captures. Do not postpone protection until porting finishes.

**Byte and log rules:** establish committed root `.gitattributes` before first content add, with `* -text`; disable applicable clean/smudge/encoding conversions for captured payloads; set `core.autocrlf=false` and `core.longpaths=true`. The verification manifest records SHA-256 of the original and restored bytes. Preserve mixed encodings as bytes.

All logs remain recoverable. Start with the measured data as it is. Add sealed, losslessly compressed log segments with byte offsets, original length and SHA-256 before large append-only files become expensive. A truncated/replaced source log starts a new generation; never truncate stored history. Segment large logs/salvage archives below 40 MiB per stored blob, with a reassembly manifest. GitHub blocks ordinary Git files above 100 MiB; do not discover that only after a commit makes the whole push fail. [GitHub file limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

The measured 5.1x compression is useful; it is not a reliable multi-year growth forecast. Measure repository growth and arrange storage expansion or sealed archive volumes before limits are approached. Batch initial history/payload uploads to stay below GitHub's [2 GiB push limit](https://docs.github.com/en/get-started/using-git/troubleshooting-the-2-gb-push-limit); small blobs do not bound the total push. No log pruning is the default. If existing history contains oversized Git objects, remote preservation is blocked until an appropriate remote or a complete segmented bundle archive is verified; do not silently rewrite original history to fit.

**Deliberately not versioned as live content:** rebuildable Unity caches, temporary files, Python environments and bytecode, downloaded dependency caches, reinstallable container images, locks, PIDs, sockets and active leases. Preserve the dependency/configuration information needed to recreate them. Treat container volumes as unknown until shown to contain only reproducible data. Credentials remain in the credential manager or a separately recoverable secret store, not Git. Your measured zero-secret result stands; do not repeat three scans as a prerequisite to preserving the agreed material. Newly added credential/config paths still require deliberate selection.

**3. Durability: when a copy counts**

Use one collector with an actual machine-wide lock shared by manual and scheduled runs. Capture on explicit fleet edits and task checkpoints; run a 15-minute sweep as a safety net. Schedule it hidden and catch up after sleep. No network operation runs while holding the game's mutation lock.

There are two distinct products:

- **A sweep capture:** useful file history, possibly from different moments. Stable-copy checks retry changing files and label incomplete/unstable items. It is not a valid task-resume point merely because Git committed it.
- **A committed checkpoint capsule:** a coherent, schema-validated task snapshot produced by the task mutation protocol described below, with exact content and object references.

For Git history, assign each source a stable ID and retain a map of original ref -> full OID/object type -> archive ref. Inspect all refs, including archive/trial/integration refs, tags, every retained stash entry and remote-tracking refs that may be the only anchors of useful history. Explicitly include each worktree HEAD, including detached HEAD, and every record-referenced source/candidate OID. Inspect reflog-only recovery candidates before disposing of their last repository. `--all` does not mean dirty files or every formerly reachable commit.

Write new immutable destination refs for changed tips, under collision-free names containing source ID and capture identity. Use ordinary heads for commits or namespaced tags for arbitrary object types; preserve annotated tags themselves. Never update or delete an earlier capture ref. Generate explicit push refspecs. Do not rely on rejection, a negative push refspec, a broad mirror push, or mutable refs called `backup`. A mirror clone used only for a restore drill is different from a destructive mirror push.

A recovery manifest, committed in `nsc-evidence` **after its payload dependencies are uploaded**, records the fleet commit, retained game/candidate object refs, checkpoint hashes, artifact hashes and included source list. It refers to payload commits without trying to include its own commit hash. Its own commit ID is the recovery-point ID. This is the consistent recovery tuple; the repo count does not eliminate it.

Mark a recovery point **off-machine verified** only when:

1. Every expected source is accounted for. A required missing path, changed identity, unreadable directory, new unclassified entry or unexpected reparse point makes coverage incomplete. Absence is recorded as an intentional deletion only when established by the source owner/operation.
2. Referenced commits and objects are retained on the remote, and advertised OIDs match. Candidate coverage is checked for every applicable record, not only canonical branches.
3. A fresh remote fetch into an independent directory can read the required objects and payloads. Restore the baseline and each deletion candidate before trusting it; routine subsequent jobs can verify manifests/OIDs, with full restore drills monthly and after storage/schema changes.
4. Restored control records parse; checkpoint schemas and hashes validate; the 40 pinned art hashes match; fleet bytes match; no linked Git object store, missing bundle prerequisite, omitted LFS object or external submodule remains an unstated recovery dependency.

Display separate timestamps for last capture, last verified remote recovery point and last full restore drill. A missing, incomplete or stale capture cannot produce a green durability indicator just because an unchanged branch pushed successfully. Compute age outside the backup process, in the viewer and session-start report. The target is a 15-minute capture cadence while awake plus transfer time; there is **no unconditional 15-minute maximum loss window** through sleep, network failures or dead credentials.

Keep a second, independently restorable copy of all four repositories/capsules on separate off-machine storage, initially a verified cloud copy and then refreshed regularly. A local OneDrive file is not proof of upload: download it through the service into a separate location and verify it. Do not use a live `.git` directory as a synced-folder backup. Account recovery and any encryption key must be recoverable without this PC.

**4. Cleanup and actual deletion**

Stop scheduling the old bulk moves. Fix the existing restore path enough to recover material already quarantined; there is no value in repairing the proposed mass-quarantine system merely to fill another quarantine.

Use one disposition manifest for every existing top-level directory/file and every registered worktree. Reuse the supplied inventories; verify a candidate's current state just before acting. A row records exact absolute path, kind, real/common Git parent, active owner/process, retained refs, file manifest, remote recovery receipt, disposition and reason. This accounts for all 788 top-level directories, 300 files and the corresponding nscrev inventory without assigning value from directory names.

**The disposal rule:** delete a working copy when (a) it has no active user or runtime dependency, (b) every valuable byte and reachable history chosen for retention has an independently verified recovery location, (c) deliberately discarded content is documented as reproducible or explicitly unwanted, and (d) a final state check matches the preservation receipt. No grace period is required after those conditions pass. No amount of elapsed time substitutes for them.

| Material | Decision and action |
|---|---|
| Reproducible caches/bytecode/temp in inactive, identified paths | Delete outright after confirming no unique output/log is inside and no process uses it. No quarantine. A name such as `Temp` alone is insufficient. |
| Clean redundant clones and retired worktrees | Preserve named tips, required metadata and evidence; verify recovery; delete the working copies in the same batch. |
| Approximately 60 undecided clone-only experiments | Default to **archive, do not merge**. Retain immutable refs and provenance remotely. Then delete the clone directories once inactive. Whether the code deserves integration is a separate, nonblocking decision. |
| Three dirty quarantined clones and other dirty/untracked work | Capture base/HEAD, staged and unstaged changes, actual working bytes, deletion markers, untracked and valuable ignored files. Restore the capsule once; then delete the original if inactive. Patches alone are insufficient. |
| Six unique bundles and other existing bundles | Preserve the original byte archive initially; import all required objects/refs; satisfy incremental prerequisites; verify from an empty independent store. Then delete redundant local bundle files. An ordinary tar archive is file data, not a Git bundle: inspect and preserve its contents separately. |
| Historical `.bak.py`, obsolete patch scripts and duplicated tools | Capture once with provenance, remove from the active installation, keep in Git history. Fix callers before deleting an imported helper. |
| GER scratch clones | Preserve their real diffs and all refs. Keep live writers out; then retire the clones. Do not delete the whole working area containing only-copy tools/drafts. |
| Pinned art and live reports | Preserve exactly and keep live paths. They are needed inputs; neither age nor a successful backup makes them junk. |
| Active work, unknown owners, unknown content or live dependency | Record the specific blocker. Preserve by default; do not infer permission or worthlessness from no response. Resolve ownership, then archive/delete the inactive copy. |

This resolves most historical indecision without hundreds of aesthetic judgments: **uncertain value defaults to durable archive; it does not default to retaining an enormous checkout.** Permanent destruction of the only retained copy still needs an explicit discard decision. Logs are not eligible for that decision under the current keep-every-log requirement.

**All 138 registered worktrees get a disposition.** The 79 under `_worktrees` are included; none is implicitly protected or disposable because of its location. For each, identify its actual parent using Git's common-directory information, preserve its HEAD and dirty state, and record all children of any parent clone that is to be removed.

Retire clean linked worktrees using `git -C <actual-parent> worktree remove <exact-path>`. Retire children before their parent clone. A dirty worktree may be force-removed only by a narrowly approved manifest action after exact recovery is proven and the last state check passes; never globally force-clean it. For previously moved worktrees, repair valid connections before operating. Prune only metadata proven stale after recovery—not as a substitute for preserving data. Submodules and locked worktrees require individual handling. These choices follow Git's [worktree management](https://git-scm.com/docs/git-worktree).

The quarantine review date, 2026-10-09, becomes a deadline to resolve remaining manifest rows. Remove each recoverable, inactive item immediately when eligible; do not wait until that date. Preserve the small manifest, provenance and restore history in evidence. Once no unresolved row remains and the directory is confirmed empty, remove the quarantine root in a separate nonrecursive operation. An empty `RESTORES.md` proves nothing.

**Deletion implementation requirements:** validate each resolved absolute target is inside its explicitly named cleanup root and is not the root itself, canonical game, a capture repo, a live control root, reports or live tools. Reject reparse points and unexpected nested repositories; never recursively follow them. Hold a maintenance exclusion against writers for the batch and recheck state. Use exact literal paths in one shell, not `C:\nsc*`, shell-built wildcard commands, `robocopy /MOVE`, or a PowerShell enumeration piped into another shell. Write a per-item intent before deletion and a receipt afterward; partial completion is recoverable and rerunnable. The final receipt records files actually gone and actual free space recovered—no estimate needed now.

The existing named protection list must also include the dedicated capture repositories and collector configuration. Do not let a stopped backup job age its own storage into the deletion list.

**5. Undo: one command, with real checkpoint restoration**

Build a new `undo_task` coordinator. Reuse ideas and proven helpers from `reset_task.py`, not its archive-and-remove workflow or its assumptions about integration fields. Keep that tool for its existing gauntlet use. Use real schema fields such as `source_commit` and `integration.source_before` where appropriate; a new checkpoint schema explicitly records before/after source commits.

Proposed interface, **to build**:

```text
nsc checkpoints NSC-042
nsc undo NSC-042 --apply
nsc undo NSC-042 --operation create|edit|complete --apply
nsc undo NSC-042 --to <unique-checkpoint-id> --resume --apply
nsc undo NSC-042 --to <unique-checkpoint-id> --resume --stop-running --apply
nsc undo --continue <operation-id>
```

Without `--apply`, show the exact operation plan. Default undo reverses the last successful logical create/edit/complete operation, not the last periodic file capture. `--operation` selects one of the three named operations (the vertical bars above mean alternatives). `--to` names a unique task-generation/revision/sequence checkpoint; repeated C2 or C5 events cannot share an ambiguous label. `--resume` restores and launches the next valid stage through normal admission. `--stop-running` explicitly includes stopping this task's owned runtime in that one command. It never kills unrelated sessions.

One command means a common interface and coordinated steps. It does not promise that an unsafe or historically unknowable operation will succeed.

**Capture at mutation boundaries, before and after:**

| Boundary | Required capture |
|---|---|
| Before create | Explicit absence of task/record and relevant ID allocation; current graph/policy state. Never reuse a cancelled task ID. |
| Before/after contract revision or cancellation | Complete per-task contract and policy entry, including absence, filters and provenance; revision identity; relevant shared graph inputs. |
| Before/after decomposition application | Parent/child identity and dependency closure, allocations and graph validation. Record now; grouped undo is separate from ordinary single-task undo. |
| Prepared | Source/base objects, checkout tree, contract/policy bindings and record; next action is crew execution. |
| Candidate saved | Candidate/base objects and exact task delta, evidence/artifact hashes, record/decomposition state; next action is review. |
| Approved | All candidate data plus approval's exact subject: candidate, contract, policy and relevant source/dependency identities. |
| Before/after landing or evidence acceptance | Explicit task IDs, operation kind, exact landed first-parent commits/merge parents, actual landed delta, before/after source and record state; include manual Game Agent merge path. |
| User checkpoint at a supported pause | Worktree/index/untracked payload as needed, with next legal stage. A running process cannot be made resumable by naming its folder a checkpoint. |

A checkpoint capsule contains: schema version and globally unique ID; task generation and operation ID; parent checkpoint; all relevant repository identities and full OIDs; saved source/candidate deltas; contract bytes plus SHA-256; full prior policy data; dependency identities and resource state needed for validation; task and decomposition record snapshots; dirty/index/untracked state where required; pinned artifact hashes and durable locations; exact pipeline/tool/config versions; evidence/approval subjects; permitted next action; and audit copies of runtime ownership. Active leases and process IDs are diagnostic data, never restoration instructions.

Pin every required object before declaring a local checkpoint complete. Mark it remotely durable only after its complete recovery manifest is verified. A checksum proves bytes survived, not that their contents were valid: checkpoint eligibility requires schema and invariant validation too.

**Make all real source writers use a transaction:**

1. Acquire an actual source-write mutex in the source common directory, then task/runtime locks in a fixed order. Adapt existing source locking so all writers participate in the same protocol; do not introduce a second independent lock beside it. Use a durable operation ID and task generation, not role names or a 30-minute log timeout.
2. Record a durable write-ahead intent and the before-image before changing source or records. Assign every mutation an explicit kind and affected task IDs. Generate and validate the proposed commit in an isolated checkout; do not mutate main and validate afterward.
3. Check expected HEAD and record generation immediately before applying the validated result. Fast-forward the canonical checkout under the lock, preserving checkout/index consistency; do not merely change its ref behind an open working tree.
4. Save after-images and a completion receipt. Release locks, then queue remote capture. A crash leaves an incomplete intent that recovery reconciles, not a fabricated successful checkpoint.

Cover contract committers, creation/policy tools, decomposition, integration, candidate sync, evidence writers and the Game Agent's manual merge command. Record-only writers also participate: prepare, candidate publication, review/approval and runtime status transitions need write-ahead receipts, generation checks and the same ownership/locking protocol. Otherwise they can race undo even while main is locked. Every main advancement since the ledger epoch must be explained by a receipt, whether or not its subject names a task. Unexpected advancements make undo coverage incomplete until reconciled. Local hooks alone cannot enforce this against agents that bypass them; the launch paths and role instructions must use the coordinator.

**The three undo meanings:**

| User operation | Implementation and result |
|---|---|
| Undo create | If the task already ran or landed, first plan and reverse its later effects, then write a forward cancellation/tombstone and remove it from runnable work. A disposition change alone does not undo landed code. Keep the original contract, ID and audit history. Refuse while active dependents need it or later effects cannot be safely inverted, unless a separately reviewed dependency-group operation is supplied. This undoes creation's operational effect; it does not erase history. |
| Undo edit | Write revision N+1 with the previous checkpoint's logical task content and policy semantics, preserving identity/provenance and incrementing revision. Recompute shared registries from the current full graph; do not replace their historical whole files. Recompute the contract SHA-256 from proposed bytes, rebind policy, and validate the complete proposed tree before landing. |
| Undo complete | Make new commits reversing exactly the task's recorded landed code/asset effects. Use a landing merge as one unit with its recorded mainline parent; never also revert its merged children. Invalidate current completion/evidence claims with new records; retain historical logs and receipts. Restore the task to the selected valid stage. |

For source changes, use current-tree semantic/dependency checks, three-way application in isolation and relevant tests. A later change to the same file is not automatically a conflict, but a clean textual merge is not proof of semantic independence. Refuse unknown ownership or inseparable mixed-task landing commits; name the dependent tasks/commit and produce a reviewable inverse/group plan. Never quietly undo a sibling task or every task since the checkpoint.

Undo-edit changes the contract hash. Default to re-prepare and fresh validation, with the old candidate retained as salvage. Candidate reuse across revisions requires an explicit, tested rebinding rule; it is not assumed. The old content may violate today's schema or invariants—in that case refuse with the incompatibility before landing.

**Intermediate resume is a real restored workspace:**

`--to` is a composite plan: reverse every later logical operation of this task before restoring the selected stage. A candidate checkpoint selected after completion includes undoing subsequent landings and evidence acceptance; restoring only its record would be wrong. Later contract edits require forward corrections too. If any required inverse is unsupported or the requested target becomes incompatible with a new contract/policy binding, refuse the whole plan before landing and name the available target. Do not silently return a partial restoration or substitute a fresh crew run for a requested candidate resume.

- **Prepared:** reconstruct the captured prepared tree in an isolated task checkout and restore compatible record fields; rerun the crew. Preserve current dirty work in a rescue capsule first.
- **Candidate:** reconstruct the candidate and its evidence, clear any invalid approvals/integration state, and rerun review without rerunning the authoring crew when the snapshot is still compatible.
- **Approved:** reuse approval only if every approval subject still matches and no integration has occurred. Otherwise require selection of the review-stage alternative; never silently call it an approved resume.
- **After undoing a landing:** keep current main, with the new inverse commit. Reapply the saved candidate/landed task delta onto that current base to create a new candidate commit; validate and review it. This is essential because merging the old reverted ancestry again can omit the work. Preserve the old candidate, and use the pipeline-supported `assistant/<task-id>` branch in the replacement task checkout rather than inventing an unsupported resume branch name.

This preserves unrelated tasks. It is not a global rewind of main. If the user wants an exact historical project universe, reconstruct the entire recovery tuple in a separate environment; do not present that as selective task undo.

**Runtime is reconciled, not restored from JSON.** Before mutation, fence new admission, relaunch and publication for the affected task generation. One authoritative owner/fence/generation is keyed by stable source identity plus task ID and is consulted across every checkout root, including standalone task clones; it is not a separate counter in each root. A source-wide admission pause during the final transaction is acceptable initially. Without `--stop-running`, live workers/controllers cause a specific refusal. With it, stop only identified owned containers and host process trees using their management APIs; wait for termination and settlement. Use run IDs plus process creation identity/container labels, not a reusable PID alone. A stopped parent does not prove its descendants stopped.

After proving ownership settled, release leases/reservations through their normal APIs. Preserve worker history; create new generation/run/lease IDs on resume. Every result publisher must reject stale generation tokens, so a late result cannot overwrite restored state. If a runtime cannot be inspected, stopped or fenced, stop the undo with the fence intact and a recoverable error. Do not clear a lease to make the record look dispatchable.

**Failure behavior:** build and validate the entire plan before source mutation. Capture a rescue checkpoint of present files/records; verify its durable recovery before destructive replacement. If validation, hash checks or dependency checks fail, do not land an inverse. Stopping a worker is itself an effect—if that was requested and later work fails, report that it remains stopped.

Git plus several runtime files is not an atomic database transaction. Persist phases such as `planned`, `quiesced`, `source-applied`, `records-applied`, `verified`, `resumed`; each is idempotent under the operation ID. After a crash, keep dispatch fenced and reconcile actual HEAD/records with the intended before/after states. Roll forward to the validated result or require a reviewed compensation; never hard-reset pushed main. `--continue` resumes the same operation without duplicate reverts or launches.

Unknown task ID, missing checkpoint, unsupported decomposition undo, missing object, unexplained history and non-restorable legacy state all return nonzero. Only a ledger-proven already-satisfied operation returns a successful no-op. Implement real read-only explanations for prepare, launch, scope and reserve, using the same predicates as their mutations. Even a successful preflight does not guarantee future capacity: claim `resumed` only after actual admission and launch receipts. Distinguish restored/ready, restored/waiting-capacity, refused and recovery-required; machine-readable output must not collapse these into exit-0 success.

The 44 historical task-naming merges are a backfill queue, not existing checkpoints. Attribute them explicitly, validate reconstructed before/after code and policy states, and mark confidence/capability per task. Where only source inversion can be established, offer that capability; do not invent lost runtime or intermediate snapshots. New tasks gain full coverage only after every writer is instrumented.

Decomposition C3 remains an explicit unsupported target in the first release: child cancellation alone does not restore parent graph semantics. Supporting it requires a grouped dependency operation, inverse ordering and full graph validation. Per-role provider-session resume is also not promised until the crew implementation has a tested durable role boundary.

**6. Execution order and what to do tonight**

The following are gates, not vague parallel projects. Preservation and ordinary deletion do not wait for undo implementation.

| Order | Work | Exit condition |
|---|---|---|
| Tonight 1 | Pause bulk cleanup and coordinate a quiet capture window for irreplaceable live state. Protect canonical, reports, tools, control roots, GER area, profile sources and new capture roots. | No mover/deleter can race the capture. Do not assume other agents have stopped. |
| Tonight 2 | Make byte-preserving emergency copies of the non-Git material listed above, including all logs and dirty quarantined work. Prioritize records/journal, only-copy tools, agent definitions/memory and pinned art. In parallel, preserve Git refs and the existing bundles. | Hash manifests and an off-machine copy that can be downloaded and restored. No need to rewrite 124 references first. |
| Tonight 3 | Create the three new private remotes and dedicated local roots. Commit byte attributes, source map and collector/bootstrap configuration first; commit fleet/evidence captures; push history captures. | Independent restore and hash checks pass. Local `git init` or a successful `git push` alone does not pass. |
| Tonight 4 | Prove restore of an existing quarantine item with unique manifest ID and exact Source/Dest, including logging. Select a small inactive redundant batch: the recovered NSC-074 validation copy, clean redundant clones/worktrees or verified caches are candidates, subject to final checks. | Preservation/deletion receipts for the specific candidates; actually delete them. If their state changed, substitute another verified batch. |
| Next 1 | Complete the single collector, source coverage manifest, immutable history refs, recovery-manifest publisher, visible status and hidden schedule. | Failure tests pass; missing sources/objects, failed uploads and stale jobs cannot show green. |
| Next 2 | Process all 138 worktrees and every top-level disposition row; archive the undecided experiments; retire redundant clones and quarantine contents in batches. | Every item has an active home, verified archive plus deleted working copy, or a specific unresolved blocker. No unknown directory is called clean. |
| Next 3 | Consolidate the three GER tools, port source-coupled writers, fix Astra follow-ups and tool outputs, update current references and ownership rules. | One authoritative implementation per tool; default-path smoke tests; compatibility junctions removable only when no consumer remains. |
| Then | Build and prove the six undo work packages below. | Full acceptance matrix passes before live undo is advertised. |

Do not execute the old `MOVE-NSC-FOLDERS.ps1 -Apply` or `MOVE-NSCREV.ps1 -Apply` tonight. The live queue explicitly forbids them, and their destination/file/collision and partial-move flaws are unrelated to whether restore logging was later repaired.

The previously proposed game bundle is still useful for off-main refs, but it is not a reason to defer unversioned scaffolding. Here is one **existing-command** emergency step, run after choosing a real backup destination. It does not cover dirty files or other repositories:

```powershell
# Choose this directory explicitly; upload/download verification follows separately.
$backupDir = 'C:\NSC-Backup-Staging'
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bundlePath = Join-Path $backupDir ('canonical-' + $stamp + '.bundle')
git -C 'C:\NSC\NSC\NoSafeCircle' bundle create $bundlePath --all
if ($LASTEXITCODE -ne 0) { throw 'Bundle creation failed' }
git -C 'C:\NSC\NSC\NoSafeCircle' bundle verify $bundlePath
if ($LASTEXITCODE -ne 0) { throw 'Bundle verification failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath $bundlePath
```

Repeat preservation for each relevant independent object store, not just canonical, after pinning needed detached/reflog entries. Verify imported bundle contents from an empty recovery store before source deletion. [Git bundle](https://git-scm.com/docs/git-bundle) distinguishes self-contained bundles from ones with prerequisites. The immediate copy can use existing file/archive tools under a quiet window; reject reparse points, preserve hidden files/bytes and validate extraction. Never label a running-tree zip a coherent checkpoint.

Tonight's minimum successful stopping point is **verified remote scaffolding and history coverage, plus one completed deletion batch**, with any remaining exposure named. If the full inventory cannot be preserved tonight, leave those specific items undeleted and show incomplete coverage. Do not delay all useful work until a perfect collector exists.

**Six undo work packages, each separately reviewable:**

1. Real source/task synchronization, operation IDs, generation fencing and read-only readiness explanations.
2. Checkpoint schema/storage, write-ahead receipts, all real mutation-path integrations and unexplained-history detection.
3. Read-only undo planning, legacy attribution/backfill, rescue capture and crash recovery protocol.
4. Semantic undo-create/edit with graph and recomputed policy validation before landing.
5. Exact completion inversion, mixed-task/dependency refusals and evidence invalidation.
6. Prepared/candidate/approved restoration, reapplication after reverted merges and real resume orchestration.

These are work packages, not a claim that six small branches finish the job. Do not combine this with unrelated decomposition work or assume its unmerged branches are deployed. Preserve those active branches during cleanup.

Acceptance must include: two tasks modifying different entries of shared registries; mixed-task commits; missing legacy records; unnamed main writes; wrong or stale policy hashes; candidate existing only in a standalone checkout; branch-name restrictions; dirty/untracked rescue; cancelled-task ID reuse prevention; later semantic dependents with disjoint paths; a candidate target selected after completion; reverted merge followed by successful reapplication; concurrent approval during undo; a late worker from another checkout root publishing after fencing; runtime stop/settle failures; and crashes after each persisted phase. Prove intermediate resume avoids repeating already-valid crew work. Exercise restoration from remote storage on a fresh checkout, not only local mocks.

**7. Residual risk and stated assumptions**

- Protection starts when remote recovery is verified. Commits/captures not uploaded, live log tails and uncheckpointed in-flight edits remain exposed. Sleep/network failure stretches the window; scheduled cadence is not a guarantee.
- Full historical midpoint undo cannot be reconstructed from absent records. Existing source commits may support reviewed inverses, but lost process state, old approvals and unsaved files stay lost. Neither this plan nor a repo can recover the original pre-sweep files/metadata already lost in the earlier moves.
- Stopping runtime cannot refund provider spend or restore provider process/session memory. Publications, messages, opened PRs/issues and external service mutations require separate compensating actions. A pushed commit remains part of history even after its effects are reverted.
- Undeclared semantic dependencies can defeat selective undo even when a patch applies cleanly. Explicit dependency tracking, validation and review reduce that risk; they cannot prove arbitrary game behavior unchanged.
- Old tools or agents that bypass the mutation coordinator can corrupt consistency. Until every writer and publisher participates, advertise partial coverage and refuse affected undos.
- Four repos require complete recovery manifests. Partial uploads remain incomplete; a restored record must never refer to a missing candidate or artifact. All logs kept forever imply growing storage and operating cost.
- Git stores file content/history, not full Windows machine state, ACLs or all service configuration. Rebuild instructions and selected metadata are needed. A machine rebuild starts with no controllers/workers, then restores data, validates it and reacquires runtime ownership afresh.
- A single hosting account is a correlated failure point. The independent second copy and account/key recovery matter even when every repo is private. Privacy is not protection against deletion by a compromised account.
- I have not verified new remote names, remote permissions, current uploader availability, free space, present-day repair success, LFS/submodule/alternate-object-store usage, or the current liveness of individual cleanup candidates. Verify those bounded prerequisites at execution; none changes the design or licenses deleting uncertain data.
- I assume the existing absolute live paths should keep working during migration, the agreed repo material remains appropriate for private storage, and “every log” includes NSC logs/transcripts outside `.assistant-control`. Non-NSC personal account history is not silently included or deleted.

The finish line is concrete: all valuable scaffold files and historical objects have verified remote recovery; every remaining live directory has an owner and purpose; redundant local directories and quarantine contents are actually removed; all logs remain recoverable; and a new task can be created, edited, completed, undone and resumed from a recorded midpoint through one tested command.

Inputs read: [v1](C:/nscrev/reports/repo-durability-and-reset-design-20260918.md), [v1 review](C:/nscrev/reports/repo-durability-and-reset-review-20260918.md), [v2](C:/nscrev/reports/repo-durability-and-reset-design-v2-20260918.md), [topology](C:/nscrev/reports/repo-topology-20260918.md), [state review](C:/nscrev/reports/state-and-plan-review-20260918.md), [tools review](C:/nscrev/reports/tools-move-review-20260919.md), [cleanup handoff](C:/nscrev/reports/handoffs/cleanup-agent-request-20260918-pipeline-maintainer.md), [night handoff](C:/NSC/nsc-handoff-20260918-night-pipeline-maintainer.md), [live queue](C:/NSC/agent-state/pipeline-maintainer-todo.md).
