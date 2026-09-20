# Gauntlet time optimizations: design for adversarial review

Date: 2026-09-12. Author: Fable session nsc-f7 (trial owner). Status: proposal, nothing implemented.
Code citations are against the trial head `14776a8` in `C:\NSC\GauntletFresh1140-20260912-1`
(identical for these files to `027e787` on `throughput/gauntlet-trial` in `C:\nscrev\throughput`).

## 0. Baseline and evidence

Two runs of the disposable 1140 Gauntlet on the asynchronous controller:

- Run 3 (2026-09-12, root `-Checkouts-4`, pre-trial code, capacity 10, background-jobs 4):
  decomposition launched at +3 s, four crews within 50 s, four independent tasks integrated by
  +11 min; both decompositions lost (one-child proposal; Source moved under a proposal).
- Trial run (2026-09-12 19:28 local, root `-Checkouts-5`, head `14776a8`, same parameters,
  Sonnet delegate-safe setup before the Opus lead's normal loop). Journal
  `-Checkouts-5\.assistant-control\graph-controller-events.jsonl` at +26 min:

Section 0 was corrected on 2026-09-12 after Astra's review (`astra-design-review.md`), which
re-derived every number from the journal with named clock boundaries. Corrected values:

| Measurement (clock boundary) | Value |
|---|---|
| delegate-safe invocation (controller_started to release) | 27.5 s: four `prepare`/`scope` pairs, total action time 22.6 s |
| gap between the delegate-safe release and the normal invocation | 177.3 s, cause not recorded in the journal (operator handoff) |
| `decompose` NSC-1140 launched (normal invocation) | +208.6 s from trial t0 (run 3: +3.3 s) |
| four independent crews dispatched (`start_worker` completed) | +214.7 to +242.2 s (run 3: +30.5 to +49.5 s) |
| `decompose` NSC-1140 / NSC-1145 (ticket created to harvest) | 289.1 s / 238.4 s; child receipts 288.2 / 237.4 s; both `review_ready`, applied |
| `apply_decomposition` | 12.2 s and 4.5 s |
| focused validation attempts (`post_crew`) by +26 min | 22 across eight implementation tasks incl. generated children; 21 passing, 1 `validation_failed` (Unity licensing error, not a cold baseline) |
| first successful validation per task, child receipt | 113.3 to 161.6 s (seven samples, overlapping, no Library census) |
| repeat validation on the same checkout, child receipt | 56.3 to 144.2 s, median 66.0 s (fourteen samples; same directory does not prove a warm cache) |
| `sync_candidate` (foreground) | 6.8 to 20.7 s, mean 11.0 s, fourteen syncs, total 154.4 s |
| `auto_approve` / `integrate` | 1.7 to 11.5 s (mean 3.7) / 6.0 to 14.9 s (mean 8.7) |
| integrations | six by +24.7 min, seventh at +26.0 min; controller released at +26.5 min with the graph blocked (NSC-1146 stale template), not completed |
| `source_lane_held` | three events for NSC-1144/1148/1149, all awaiting NSC-1145's proposal; observed waits about 139, 63 and 61 s, overlapping |
| Unity compile graph on NSC-1142's first validation | "9249 ToBuild, 108 ToUse" (unity.log line 240); later repeats show the same summary, so this is scheduling, not proof of cold work |
| Library size, machine memory | not in the authorized evidence; to be measured with timestamps during the next run |

Where the wall clock goes, as far as the journal supports it: (1) repeated validation work: 22
attempts totalling 2,041 child-seconds, fourteen of them following a `sync_candidate` after a
Source move, largely overlapping so not additive; (2) the 177 s operator gap between the
delegate-safe release and the normal loop, which is the largest single measured setup cost, not
the prepares themselves; (3) integration waits during the second proposal (about 139, 63 and
61 s, overlapping), not the proposals' full durations. The savings claimed in the original
sections 6 and 9 are therefore unsupported estimates until the instrumentation Astra asked for
exists; the designs stand as directions, with Astra's required changes governing.

The five designs below attack exactly those. None changes what is validated, approved or
integrated for a real-game task; D2b changes when a candidate is validated relative to its
integration and is therefore the only one that touches the authoritative policy.

---

## D1. Seed each task checkout's Unity Library from a verified warm cache

### Problem and evidence
`Checkouts.prepare` (`Pipeline/AssistantControl/checkouts.py:36`, clone at lines 119 to 124)
creates every checkout with `git clone --no-local --no-checkout` and, by explicit comment,
copies "no working files or ignored Unity Library". The Source itself has no `Library`. The
focused validation (`Pipeline/TaskReviewAgent/authoritative_candidate_validation.py:124`,
`run_authoritative_candidate_validations`, Unity in `-batchmode` against the checkout as
`-projectPath`) therefore imports and compiles the whole project the first time it runs in a
checkout: the unity.log of NSC-1142's first validation shows 9,249 build-graph nodes built and
108 reused. Measured: first validations 114 to 162 s under concurrency, later validations on
the same checkout 57 to 81 s. `Library/` is ignored (`.gitignore:9 /[Ll]ibrary/`) and the
post-run churn check reported `{"paths": [], "status": "clean"}`, so the Library is invisible
to every Git-based proof.

### Design
1. A verified cache per checkout root: `<checkout-root>\.assistant-control\unity-library-cache\<key>\Library`
   plus `seed-manifest.json` written last (`completed: true`, key, Unity version, file count,
   byte count, the checkout and validation job that produced it, timestamp). The key is
   `sha256(ProjectSettings/ProjectVersion.txt + Packages/manifest.json + Packages/packages-lock.json)`
   of the checkout's committed bytes at its `source_commit`: the inputs that decide whether a
   Library is compatible. An optional `--unity-library-cache <dir>` lets an operator point at a
   persistent cache outside the root so even the first validation of a fresh root is warm; the
   fresh-root rule concerns run evidence, and the cache carries none.
2. Populate: after a focused validation job completes successfully in a checkout (Unity has
   exited; `Library/ilpp.pid` absent), and only when the cache for that key has no completed
   manifest, the `post_crew` child copies `<checkout>\Library` into a staging directory
   `<key>.staging-<uuid>` with `robocopy /E /MT:16 /R:1 /W:1`, excluding lock and instance
   files (`ilpp.pid`, `*.lock`, `EditorInstance.json`, `ArtifactDB-lock`, `SourceAssetDB-lock`,
   `Bee/*.lock`), writes the manifest, then renames the staging directory into place. A cache
   entry is immutable once completed; a newer key gets a new entry.
3. Seed: `Checkouts.prepare` (and `prepared_refresh.refresh_prepared`,
   `Pipeline/AssistantControl/prepared_refresh.py:95`, which recreates a checkout at a new
   commit) computes the checkout's key, and if a completed cache entry matches, copies it into
   `<staging>\Library` before the staging directory is renamed to the checkout, then verifies
   file count and bytes against the manifest. On any mismatch or copy error the partial
   `Library` is removed and the checkout proceeds cold. The record gains
   `unity_library_seed: {key, cache_entry, files, bytes, seconds}` or `{key, seeded: false, reason}`.
4. No seeding into a checkout that has a running worker or an active job; `prepare` runs
   before either exists, and `refresh_prepared` only when no reservation is held (existing rule).

### Identity and fail-closed properties
- Authority is unchanged: Unity's Asset Database validates every cached artifact by content
  hash and re-imports anything whose source differs, so a seeded Library can make Unity faster
  but not wrong; the validation fact still binds the exact `commit` and `tree`
  (`authoritative_candidate_validation.py:115,160`).
- The cache is written only from a checkout whose validation completed, only when Unity has
  exited, and only atomically (staging directory plus manifest-last plus rename).
- A key mismatch, an incomplete manifest, or a verification failure means cold, never a
  partially seeded checkout.
- `git status` in a seeded checkout must be empty (`Library/` ignored); `prepare` asserts it.

### Tests (failing-before on the current code)
- Fixture project with a synthetic `Library` tree: `prepare` seeds when a completed manifest
  matches, records the seed, and leaves `git status` clean; refuses to seed on key mismatch,
  on a manifest without `completed`, and on a byte-count mismatch (partial copy removed).
- A `post_crew` completion populates the cache exactly once per key, atomically, and never
  while `ilpp.pid` exists.
- Real measurement (acceptance): with the cache warm, the "ToUse" share of the compile graph
  and the `post_crew` `duration_seconds` on first validations drop; target under 45 s alone.

### Not in scope
Unity Accelerator (helps asset import, not script compilation; needs a service) and a shared
symlinked Library (Unity locks it; concurrent instances would collide) were rejected.

---

## D2. The resync cascade

Today (`graph_controller.py:833-875`): when `record.source_commit != head`, the planner emits
`sync_candidate` (foreground, `_execute_foreground` line 1437 calls
`source_update.synchronize_candidate`, which takes `_source_integration_lock`), then a new
`post_crew` background validation, then `auto_approve` (line 1443, which refuses without
retained `authoritative_validations`), then `integrate` (line 1463, `ReviewGate.integrate`
under the same lock). With P pending candidates and M Source moves the run performs about
P x M syncs and validations: 22 validations for 8 tasks after 26 minutes of this trial.

### D2a. Sync as part of the background validation job (small, safe)
Fold the mechanical synchronization into the `post_crew` job instead of running it as a
foreground Source-lane action. The planner emits `post_crew` with `sync_to_source_commit: head`
whenever the candidate is behind; the child performs exactly `synchronize_candidate` (same
function, same `_source_integration_lock`, same `candidate-sync` receipt) and then the
validation, and its receipt carries the synced candidate commit and the validation facts. The
job ticket binds task, the pre-sync candidate commit, the target Source commit and the contract
hash, so a receipt for another head or another candidate is refused at harvest exactly as
`post_crew` receipts are today (`background_jobs.py` ticket and receipt identity). The
foreground `sync_candidate` action stays for the `approved`-but-stale path, which needs no
validation and moves nothing.

Effect: removes 10 to 15 s of serialized foreground time per pending candidate per Source move
and one controller cycle per candidate. Safety unchanged: the same lock, the same function,
the same receipt; the only difference is which process runs it.

### D2b. Batch integration on a validated union tree (policy change; needs Vincent and Astra)
Goal: one Source move and P validations per batch instead of P x M, without weakening
"validated on the exact tree that is integrated". Today that equality holds because the synced
candidate already contains the head H it was validated on and `ReviewGate.integrate` refuses
when the Source is no longer at its `expected_source_commit`, so the merge result's tree is the
validated tree; D2b keeps the same equality for a batch by fast-forwarding the target branch to
the exact validated union commit and recording the tree equality in every receipt.

1. Batch formation: when at least two candidates are validated at the current head H (their
   `authoritative_validations` bind H's tree), no proposal is in flight, and no other batch is
   open, the controller opens batch `B` (durable record
   `.assistant-control\integration-batches\<batch-id>.json`: head H, ordered task list, state).
2. Union tree: `ReviewGate.integrate` is fast-forward only (`review.py:210`, `merge --ff-only`
   at line 288, refusing unless the Source is at `expected_source_commit`, line 251), so the
   batch is built the same way, sequentially: for each candidate in task-id order,
   `synchronize_candidate` it onto the batch's current tip (the same mechanical merge it performs
   today, in the task's own checkout, producing a synced commit that contains the tip), then
   fast-forward the batch tip to that synced commit in an ephemeral worktree of the Source
   started at H (`git worktree add --detach <checkout-root>\.assistant-control\integration-batches\<batch-id>\tree H`).
   That yields H1..Hn with every tip recorded and `union_tree = rev-parse Hn^{tree}`. A
   synchronization conflict removes that candidate from the batch (it returns to the ordinary
   path) and the batch continues with the remaining ones. The syncs are still P per batch; the
   saving is in validations and Source moves, not in syncs.
3. Batch validation: launch one `post_crew` job per candidate against the union worktree at Hn
   (same `run_authoritative_candidate_validations`, same test filter), all in parallel under
   `--background-jobs`. Each fact binds `commit: Hn, tree: union_tree`.
4. Landing: if every fact passed, under `_source_integration_lock` verify the Source is still at
   H, fast-forward the target branch to Hn, and record per task an integration receipt whose
   `integrated_commit`/`integrated_tree` equal the validated ones; `auto_approve` runs per task
   with `tested_commit: Hn` and the candidate's own commit retained as `candidate_commit`.
   If the Source is no longer at H, the batch is discarded unlanded (nothing moved) and the
   candidates return to the ordinary path.
5. Failure: any failed fact marks that task `validation_failed` with its evidence, discards the
   batch worktree, and re-batches the passing candidates once at the same H; a second failure
   falls back to the ordinary one-at-a-time path for that head.
6. Proof recorded in every receipt: `integrated_tree == validated_tree`, plus the batch id and
   the ordered candidate list. `apply_decomposition` never joins a batch; it stays a single
   Source move.

Effect: for this trial's shape (6 to 8 candidates pending across ~10 Source moves), validations
drop from roughly 25 to 30 to roughly 10 to 12 and Source moves from ~10 to ~4. Cost: a new
durable record type, a new worktree lifecycle with exact cleanup, changes to
`ReviewGate.integrate`/`approve_validated_gauntlet`, the fact binding, the planner and the
viewer. This is the one design that changes the authoritative validation policy's timing and
must be decided by Vincent and reviewed as a policy change before implementation.

### Tests
D2a: a job whose receipt names a different target head or candidate is refused at harvest; the
synced record equals the foreground path's record byte for byte apart from timestamps; the
foreground `sync_candidate` still runs for `approved` candidates. D2b: union-tree equality is
asserted on every landing; a Source move between batch formation and landing discards the
batch; a conflict removes only the conflicting candidate; a failed fact fails only its task;
crash between worktree creation and landing leaves the Source untouched and the batch record
reconstructable.

---

## D3. Run decomposition on a snapshot clone and retire the Source-lane hold

### Problem and evidence
`decomposition.run` (`Pipeline/AssistantControl/decomposition.py:315-420`) launches the
container with `cwd=manager.source` (line 419) and `--source /workspace`, so the proposal reads
the live Source mount. `source_revalidation_reasons` (`Pipeline/TaskDecomposition/context_builder.py:133`)
then compares the mount's HEAD and tree after every provider call, which is why NSC-1145's
correct proposal was rejected in run 3 when NSC-1143 integrated mid-call. The lane hold on the
trial branch (`DECOMPOSITION_HELD_ACTION_KINDS`, `graph_controller.py:71`) prevents that by
holding `integrate` and `apply_decomposition` while a proposal runs: correct, but it costs the
whole proposal duration (289 s and 238 s in this trial) of integration latency, three times so
far. The repository's own isolation doc (`Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`)
already says decomposition runs from a task checkout, not the shared root.

### Design
1. Decomposition parents get a checkout: the planner emits `prepare` for a
   `needs_execution_decomposition` task before `decompose` (today it emits `decompose` directly;
   NSC-1140 has no directory under the root). `Checkouts.prepare` is unchanged; the record's
   `checkout` and `source_commit` bind the snapshot.
2. `decomposition.run` launches the container with `cwd=<checkout>` so `/workspace` is the
   snapshot at exactly `source_commit`; the ticket, container name, labels and output root are
   unchanged. Preflight (`decomposition_preflight`) runs against the snapshot. The in-run
   `source_revalidation_reasons` keeps its exact semantics and now guards the snapshot, which
   nothing moves: the check still fails closed on a dirty or moved snapshot.
3. Apply keeps using the Source and the existing advancement proof
   (`_source_advancement_proof`, `decomposition.py:93`, enforced at lines 149 to 154:
   reviewed head is an ancestor of the current head, authoritative graph inputs unchanged,
   parent contract semantic hash compatible). One extension makes it exact for a snapshot:
   the run result already knows its `context_paths` (`_context_paths`,
   `context_builder.py:275-311`: the task's, parent's, children's and dependencies' contracts,
   the GDD, the resource-groups file, existing exclusive-resource paths and bootstrap-evidence
   paths); apply must additionally prove those exact paths are byte-identical between the
   reviewed head and the current head (and that a path absent at review is still absent), and
   refuse otherwise. That is the precise statement of "the proposal's inputs did not change".
4. Retire lane-hold rule 1 (integrations wait for a proposal) and rule 3 (Source move first);
   keep rule 2 as a configurable cost bound (`--decompositions-in-flight`, default 1) using the
   existing `held` plumbing and `source_lane_held` journal, renamed to what it now means.

### Identity and fail-closed properties
- The proposal binds the snapshot's head and tree; the apply proof binds the proposal's exact
  input paths to the current head; anything else refuses, as today.
- Docker mounts a per-task clone, which the crews already do; the Source is never mounted for
  decomposition again.
- The snapshot is a normal task checkout: same cleanup, same identity records, same quarantine.

### Tests
Failing-before: an integration during a fixture proposal no longer rejects the proposal, and
apply then succeeds via the advancement proof; apply refuses when a context path changed
between the reviewed head and the current head (each category: a contract, the GDD, a resource
path that appeared); a dirty or moved snapshot still fails the in-run check; the one-in-flight
bound still holds and is journaled once.

---

## D4. Concurrency bound for validations

`--background-jobs` (default 4) bounds decompositions and validations together. After D1 and
D2a a Source move puts P validations in flight at once; after D2b a batch puts P at once by
design. Each Unity batch instance needs roughly 2 to 3 GB; the machine showed 63.4 GB total and
29 GB free with three or four crews and validations running. Design: default `--background-jobs`
to 6, add `--validation-jobs` as a separate bound for `post_crew` (default 6) so a long
decomposition never starves validations and vice versa, and record each job's peak working set
in its receipt (`Get-Process` at completion) so the sizing rule is measured, not guessed. No
identity change; the bounds are enforced where they are today (`_choose_run_action`'s
background-launch count).

---

## D5. Setup ordering: prepare as background work, dispatch immediately

### Problem and evidence
The staffing guide orders Sonnet's `run-graph --delegate-safe` before the lead's normal loop;
delegate-safe returns `handoff_required` before any provider or Docker work, so the loop that
may launch the decomposition starts only after all eight `prepare`/`scope` actions have run
serially: +3.5 min to the first `decompose` launch in the trial versus +3 s in run 3, and the
first crews at +3.6 to +4.0 min versus under 50 s.

### Design
1. `prepare` and `refresh_prepared` become owned background jobs (kind `prepare`), ticketed like
   `post_crew` (task, source commit, contract hash, checkout root), with the receipt being the
   prepared record; the child runs exactly `Checkouts.prepare` or
   `prepared_refresh.refresh_prepared` (`prepared_refresh.py:95`), nothing else. They are bounded by a separate
   `--setup-jobs` (default 4) because they use Git only. The planner treats an active prepare job
   as `wait_job` for that task and leaves `scope` foreground (seconds).
2. The launch priority already puts owned background jobs before setup and admission
   (`ASSISTANT_AUTONOMOUS_GRAPH.md` item 4), so on the first cycle the lead's loop launches the
   decomposition and up to four prepares within seconds; crews start as each task becomes
   prepared and scoped instead of after all eight.
3. Procedure: `--delegate-safe` may launch prepare jobs (Git only, no provider, no Docker) and
   returns `handoff_required` at the first `wait_job`; the guide's step 3 then completes in
   seconds and the lead's normal loop harvests the prepares. If Vincent prefers no child
   processes under delegate-safe, the alternative is procedural only: the lead starts the normal
   loop right after Sonnet's `graph-plan` verification and Sonnet's `run-graph --delegate-safe`
   is dropped; that alone recovers the decomposition's three minutes but not the crews'.

### Tests
Failing-before: with eight ready tasks the first `decompose` launches on the first cycle while
prepares are active; a prepare receipt for another commit or contract is refused; a prepare
child that dies leaves the task blocked, never relaunched; delegate-safe stops at `wait_job`.

---

## 6. Expected savings, risk and order

| Design | Expected saving on an 8-task Gauntlet | Risk / review need | Order |
|---|---|---|---|
| D1 Library seeding | 60 to 90 s per cold validation; ~8 cold validations per run | Low: cache only, verified, no authority | 1 |
| D5 prepare jobs, immediate dispatch | ~3 min on the decomposition path, ~2 min on the first crews | Low: Git only, existing job machinery | 2 |
| D2a sync inside the validation job | 10 to 15 s per candidate per Source move; frees the Source lane | Low: same function, same lock, same receipt | 3 |
| D4 concurrency bounds | removes queueing when many validations coincide | Low, measured sizing | 3 |
| D3 snapshot decomposition, retire hold rule 1 | 4 to 5 min of integration latency per proposal | Medium: apply proof must be made exact | 4 |
| D2b batch integration | validations from ~25 to 30 down to ~10 to 12; Source moves from ~10 to ~4 | High: policy timing change, new records and worktree lifecycle | 5, after decision |

D1, D5, D2a and D4 together should bring the trial's ~40 minutes toward ~20 for the same graph
without touching any authority. D3 and D2b are where the rest is.

## 7. Astra's FIX AFTER backlog (trial review of 573302b..027e787) and how these designs touch it

1. P2 corrected-run evidence validation (malformed histories, contradictory round numbers): a
   consumer-side tightening in `_verify_review`; independent of D1 to D5. Fix alongside D3.
2. P2 failed decomposition apply can repeat (a safe pre-mutation refusal stays `review_ready`):
   D3 changes apply's proof; the repair (record the refusal on the decomposition record so the
   planner blocks the parent instead of retrying) belongs in the same commit set.
3. P2 production human-authorization path rejects corrected runs
   (`decomposition_authorization.py`): independent; required before the upstream port.
4. P3 legacy viewer correction timing: independent, display only.
5. P3 hold reasons missing from the viewer: D3 renames and narrows the hold; the viewer shows
   the remaining `held` records' task, job and reason.
6. P3 hold journaling on a reused controller object: D3 keeps the journal for the remaining
   rule; fix the seed-per-invocation bookkeeping there.
7. P3 vague malformed-evidence errors: distinct messages per refusal in `_verify_review`;
   with item 1.

## 8. Decisions needed from Vincent
- D2b: accept batch integration as a policy change for the Gauntlet (and later upstream), or
  keep one-at-a-time integration with revalidation.
- D5: allow `--delegate-safe` to launch Git-only prepare children, or keep delegate-safe
  process-free and change the staffing procedure instead.
- D1: whether a persistent cache directory outside the fresh checkout root is acceptable
  (`--unity-library-cache`), or the cache always starts empty with each root.

## 9. Acceptance measurements (from the journal, no new instrumentation needed except D4's peak memory)
- time to first `decompose` launch and to the fourth `start_worker` (D5);
- `post_crew` `duration_seconds`, split cold versus warm by the presence of
  `unity_library_seed` (D1), and validations per task (D2);
- `integrate` count versus Source moves and `source_lane_held` events (D2b, D3);
- end-to-end time from `controller_started` to the last `integrate` for the same eight-task
  graph, against this trial's journal as the baseline.
