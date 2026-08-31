# D1C — Reusable Graph Application Design

This is a design proposal (**RECOMMENDATION**), not implemented behavior. It builds directly on facts
established in `CURRENT_STATE_AUDIT.md`.

## What Git can and cannot make atomic (state this up front)

**FACT/constraint that shapes the whole design:**

- Git *can* make a **single commit** atomic: either the commit object is created with a fully-formed tree, or
  it is not created at all. A commit is never partially written.
- Git *can* make a **local branch pointer update** atomic (`git update-ref`/`git commit` moving a ref is a
  single filesystem operation).
- Git *cannot* make a **multi-step remote push + external system update** (GitHub Issue comment, PR, merge)
  atomic as one transaction. Push can succeed while a subsequent Issue update fails; push can fail after local
  commit succeeds.
- Git *cannot* protect against **two independent commits both being technically valid but semantically
  conflicting** (two decompositions of overlapping parents) — that is a graph-semantics problem, not a Git
  problem, and must be solved by application-level preflight (source identity binding) not by Git alone.
- The working tree is *not* transactional across multiple files: writing `Tasks/NSC-030.yaml`,
  `Tasks/NSC-050.yaml`, ..., `WORK_ID_MAP.json`, and `RESOURCE_GROUPS.yaml` as five separate `write()` calls is
  not atomic at the filesystem level. `work_graph_persist.py` already solves this with a stage-then-`os.replace`
  pattern (see below) — that pattern, not raw multi-file writes, is the proven precedent D1C must follow.

**Consequence:** D1C's atomicity guarantee is **local-filesystem staged replace, followed by exactly one Git
commit**. Push and any downstream Issue/PR update are separate, non-atomic steps that must be individually
idempotent and recoverable (see §"Git commit boundary" and §"Recovery").

## Exact input authority

D1C accepts exactly:

1. A `decomposition_result.json` that has already reached `review_ready` under D1B.1 or D1B.2 (independent PASS,
   no unresolved blocking findings for D1B.2).
2. The `graph_delta.json` (`GraphDeltaPlan`) produced from that exact result by `plan_graph_delta`.
3. Explicit **human/operator authorization** to apply — a distinct action from "the result is `review_ready`."
   Per `Pipeline/TaskDecomposition/README.md`: *"Neither status is automatic graph-application approval... the
   human/orchestrator must still check execution locality and dependency realism."*

D1C **does not** re-derive a decomposition; it only re-validates and materializes an already-produced plan. It
must never call a provider.

## Source HEAD/tree/task-contract identity binding

**RECOMMENDATION.** D1C must bind to the graph delta's own recorded identity, not to whatever the operator's
working directory happens to contain:

```text
graph_delta.parent_before_hash        (semantic contract hash used at planning time)
graph_delta.source_graph_semantic_hash (whole-graph semantic hash used at planning time)
```

Before doing anything else, D1C must:

1. Load the **current committed** `Tasks/<parent-id>.yaml` at the exact commit D1C is about to build from
   (this must be `origin/main` HEAD in a completely clean checkout — reuse
   `Pipeline/TaskDecomposition/context_builder.py::capture_clean_source` verbatim; it already implements
   exact HEAD/tree/branch capture and a full untracked-files-included cleanliness check).
2. Recompute `semantic_json_sha256(current_parent)` and compare to `graph_delta.parent_before_hash`.
3. Recompute the full current graph's semantic hash (same construction `graph_delta.py::_plan_payload` +
   `semantic_json_sha256` uses) and compare to `graph_delta.source_graph_semantic_hash`.
4. If either differs, **fail closed** with a `stale_proposal` result — never attempt a "smart" partial
   reapplication.

**This is stale-proposal rejection.** It reuses existing hashing exactly (no new hash algorithm), so a stale
check is provably consistent with what D1B.1/D1B.2 already computed.

## Deterministic revalidation immediately before mutation

**RECOMMENDATION.** D1C re-runs `plan_graph_delta(current_graph, parent_selector, decomposition_result)`
itself, from the *current* committed graph, rather than trusting the stored `graph_delta.json` bytes for
mutation content. Two reasons:

- It reuses 100% of the existing deterministic validation (`validate_work_graph_plan`,
  `validate_decomposition_graph_semantics`, ID collision, cycle detection, inbound-rewrite coverage) with zero
  new logic.
- If nothing about the parent/graph changed since planning (identity check in the prior section already
  proved this), the recomputed `GraphDeltaPlan` is byte-identical to the stored one — D1C should assert that
  equality (`recomputed.canonical_json() == stored.canonical_json()`) as a second independent check, and fail
  closed if they differ (this would indicate either a bug or tampering with the stored artifact).

This recompute-and-compare step is a defense against bugs/tampering in the stored artifact, **not** a mechanism
for reallocating a stale proposal. A `source_graph_semantic_hash` mismatch is caught earlier, by the
identity-binding check above, and short-circuits to `stale_proposal` before this step ever runs — this step
only ever runs when the graph is already known to be unchanged.

## Deterministic child ID allocation and collision handling

**FACT.** `graph_delta.py` already allocates deterministically: `next_number = max(existing_numbers) + 1`,
contiguous per child in result order, and `source_graph_semantic_hash` is the semantic hash of the ENTIRE
graph (`id_map` + `tasks` + `resource_groups` + `project_requirements` — see `_plan_payload`), not just the
selected parent. This means `GraphDeltaPlan.plan_id` (§"Source HEAD/tree/task-contract identity binding")
is bound to the exact whole-graph state at planning time, and any change anywhere in the graph — including an
unrelated decomposition applying against a different parent — changes `source_graph_semantic_hash` and
therefore invalidates that binding.

**CORRECTION.** D1C never allocates a *new* ID range for an already-reviewed `GraphDeltaPlan` and silently
applies it as though the same human authorization still covers the result. A reviewed `GraphDeltaPlan` is
immutable authority bound to its exact `source_graph_semantic_hash` and `allocated_local_key_to_task_id`
(§"Source HEAD/tree/task-contract identity binding"; see also `CONCURRENCY_AND_FAILURE_MODEL.md` races #2 and
#16). D1C's revalidation step recomputes the plan **only to prove byte-for-byte equality with the stored,
reviewed plan**; it is never used to compute a *different*, silently-substituted allocation under that same
authorization.

**The actual cross-application collision case:** two *different* proposals for two *different* parents,
generated concurrently, both computed `next_number = N` because both were planned against the same prior
`main`. If proposal A applies first, `main` now contains ID `NSC-{N}` and its whole-graph semantic hash has
changed. If proposal B is then presented to D1C, revalidation (§"Deterministic revalidation") recomputes B's
plan against the now-current graph and finds it does **not** equal the stored, reviewed `GraphDeltaPlan` B
(different `source_graph_semantic_hash`, different `plan_id`) — this is `stale_proposal`, not a shifted
reapplication. Correct recovery is a fresh D1B round against the new `main`, producing a new
`GraphDeltaPlan`/`plan_id` for parent P2 (which will naturally allocate `NSC-{N+1}`, since it now observes A's
committed child), followed by independent human re-authorization of that new plan. The global apply-claim
serialization described in `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Serialization of graph mutation" reduces *how
often* two applications actually race to commit at the same instant, but it does not — and cannot — make a
stale reviewed proposal valid again. See `CONCURRENCY_AND_FAILURE_MODEL.md` race #2 for the full sequencing.

## Parent contract transition to aggregate/non-executable state

**FACT — already fully specified by `graph_delta.py::plan_graph_delta`.** The recomputed `proposed_parent`
already carries `kind=feature`, `execution_scope=not_applicable`, `decomposition_state=decomposed`,
`decomposition_children`, `decomposition_requirement_sha256`, `exclusive_resources=[]`, incremented
`contract_revision`, and machine-generated `execution_reason`/`decomposition_reason` text. D1C does not need to
construct any of this itself — it materializes `graph_delta.proposed_graph_overlay.tasks` verbatim.

## Child contract creation

**FACT — already fully specified.** `graph_delta.proposed_child_contracts` are complete schema-2.0 task
contracts (`_child_contract` in `graph_delta.py`), including `provenance.graph_delta_plan_id` linking each
child back to the exact `GraphDeltaPlan` that created it. D1C writes one file per child:
`Tasks/<child-id>.yaml` = `canonical_json_text(child_contract)` (reuse
`work_graph_persist.py::canonical_json_text` verbatim — 2-space indent, `ensure_ascii=False`, trailing
newline).

## Inbound dependency rewrites

**FACT — already fully specified.** `graph_delta.proposed_graph_overlay.tasks` already contains every
rewritten dependent with its `depends_on` updated and `contract_revision` incremented
(`graph_delta.py::_rewrite_dependent`). D1C does not compute rewrites; it writes whichever task files changed
between `source.tasks` and `proposed_graph_overlay.tasks` (parent, children, rewritten dependents) and leaves
every other `Tasks/*.yaml` file byte-identical and untouched.

### Authority over rewritten dependents before mutation (RECOMMENDATION — corrects an earlier gap)

**FACT.** `graph_delta.py::_rewrite_dependent` only changes a dependent's `depends_on` and increments its
`contract_revision`; it does not touch AC/VAL, resources, or any other executable content. **This does not make
the mutation safe to perform unconditionally.** A dependent's `contract_revision` and `depends_on` are part of
the exact contract identity an active implementation worker's durable Issue lease and any in-flight
evidence/delivery-review binding are built against; D1C changing them underneath an active worker is a contract
mutation the worker never agreed to, even though its AC/VAL text is untouched.

**RECOMMENDATION — required, not optional.** Before D1C may materialize any rewritten dependent, it must treat
every affected *existing* task ID exactly like the parent: an ID D1C must hold proven claim/lease authority over
before mutating its contract. "Affected existing task IDs" = the decomposition parent + every existing
dependent named in `graph_delta.inbound_dependency_changes` + any other existing task whose contract the exact
`GraphDeltaPlan` changes. See `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Protecting existing task contracts D1C
rewrites" for the full design — this is real new claim-layer work, not a zero-new-code reuse of `claim_refs.py`
as an earlier draft of this design assumed.

## Resource lock/resource-group updates

**FACT — already fully specified.** `graph_delta.proposed_graph_overlay.resource_groups` is the complete
post-application resource-group list (`graph_delta.py::_update_resource_groups`). D1C overwrites
`Pipeline/TaskGraph/RESOURCE_GROUPS.yaml` with this list in the same JSON-subset-YAML form
`work_graph_persist.py::metadata_payloads` already uses (`schema_version`, `serialization_format`,
`resource_groups`).

## Contract revision increments

**FACT — already handled.** Parent (`+1`) and every rewritten dependent (`+1`) revisions are already computed
inside `plan_graph_delta`. Children start at `contract_revision: 1`. D1C must not re-derive or second-guess
these values — doing so would risk drift from the hash the plan already committed to.

## Task-file and graph index/metadata writes

**RECOMMENDATION — reuse the `work_graph_persist.py` staging pattern, generalized for repeated use:**

```text
1. stage_dir = mkdtemp(dir=repo_root)              # same filesystem as the target, so os.replace is atomic
2. write every CHANGED task file into stage_dir/Tasks/<id>.yaml
       (parent, all proposed_child_contracts, every rewritten dependent — NOT the full task set)
3. write stage_dir/Pipeline/TaskGraph/WORK_ID_MAP.json   (merged: source.id_map + allocation)
4. write stage_dir/Pipeline/TaskGraph/RESOURCE_GROUPS.yaml (full replacement, from proposed_graph_overlay)
5. re-load a synthetic WorkGraphPlan combining: current committed tasks (unchanged files, read from HEAD)
   + staged changed files, and run validate_work_graph_plan + validate_decomposition_graph_semantics
   against the FULL resulting graph (mirrors validate_staged_bundle's role in the bootstrap path)
6. only after step 5 passes: os.replace() each staged file over its real target, changed files only,
   in a fixed order (children first, then rewritten dependents, then parent, then WORK_ID_MAP.json,
   then RESOURCE_GROUPS.yaml — parent last among task files so a crash mid-publish leaves the OLD parent
   still pointing at the OLD (correct, non-aggregate) state rather than a parent that claims decomposition
   while children are still missing)
7. on any exception before step 6 completes: remove the staging directory; the real Tasks/ tree is
   untouched because no os.replace has occurred yet
8. on any exception DURING step 6 (partial os.replace): see "partial filesystem write" below
```

This is a **deliberate generalization** of `work_graph_persist.py`'s bootstrap pattern to a "changed files
only" incremental apply, since D1C (unlike bootstrap) must not require `Tasks/` to be empty.

**DO NOT** call `work_graph_persist.persist_work_graph` directly for D1C — it asserts
`BOOTSTRAP_PERSISTED.json` does not yet exist and that `Tasks/` is empty, and it always writes the *entire*
task set rather than an incremental changeset. Reusing its *primitives*
(`canonical_json_text`, `sha256_bytes`, `write_text`, the stage → validate → `os.replace` shape) is correct;
calling the bootstrap function itself is not.

## `decomposition_children` and `decomposition_requirement_sha256`

**FACT — already correct in the plan.** No additional work; these are part of `proposed_parent` as computed
by `graph_delta.py` (see above). D1C's only job is to write that already-correct value unchanged.

## Preservation of canonical requirements/coverage

**FACT — enforced upstream, not by D1C.** `policy.validate_decomposition_result` already enforces exact parent
AC/VAL/INT coverage before a `GraphDeltaPlan` can exist at all. D1C's revalidation step (recomputing the plan
against current HEAD) re-proves this holds against the *current* parent, not just the parent as it existed at
proposal time.

## Repository dirty-tree preconditions

**RECOMMENDATION.** D1C must require a completely clean checkout at exact `origin/main` HEAD before doing
anything, using the same check `context_builder.capture_clean_source` already performs
(`git status --porcelain=v1 --untracked-files=all` must be empty). This is not a new requirement; it is the
existing D1B precondition applied one stage later. Running D1C against a dirty tree must be a hard refusal, not
a warning.

## Mutation plan / dry-run artifact

**RECOMMENDATION.** Before any `os.replace`, D1C should write one immutable `d1c_mutation_plan.json` artifact
(outside the repository tree, alongside the decomposition run's Downloads output root — never inside `Tasks/`)
recording: exact source identity, plan_id, recomputed vs. stored delta equality result, the full list of files
about to change with before/after semantic hashes, and human authorization identity/timestamp. A `--dry-run`
flag should stop after producing this artifact. This gives the human operator something concrete to review
before authorizing the real mutation — mirroring the existing Decomposition Closeout pattern but for the
*application* step specifically.

## Atomicity/transaction boundary across multiple files

Covered above: **staged-write + validate-staged + ordered `os.replace`** is the controlled publication
boundary **inside the isolated D1C-owned checkout**, but it is explicitly **not an atomic multi-file
transaction**. After the first `os.replace`, partial filesystem state can be visible to another process that
reads that same disposable checkout, and a process crash can leave only a prefix of the replacements present.
The ordering reduces the danger of that partial local state, and the orphaned-child validation below makes it
fail closed; it does not make the replacements atomic as a group.

The authoritative publication guarantee is stronger at the Git boundary: D1C must not commit, push, open/integrate
a PR, or update durable completion authority until **all** replacements finish and the full materialized graph
validates. A valid single Git commit then represents the complete semantic unit; shared `main` therefore sees
either the pre-apply commit or the fully validated post-apply commit, never the checkout's partial replacement
sequence. See the next section for crash recovery inside the isolated checkout.

## What happens if filesystem write succeeds partially

**RECOMMENDATION.** If the process crashes between `os.replace` calls in step 6 **inside the isolated
D1C-owned checkout**:

- Some child files exist in that disposable checkout; the parent file may still be the OLD
  (pre-decomposition) version, or the NEW one, depending on exactly where the crash occurred. This partial
  working-tree state must never be committed/pushed/integrated as authoritative graph state.
- `persistent_work_graph.py::load_persistent_work_graph` re-validates the **entire** graph on every load,
  including `validate_decomposition_graph_semantics`. If the parent is still old but children already exist as
  orphaned schema-valid files with `parent: <parent-id>` pointing at a still-non-aggregate parent, the loader
  does not currently reject "child contract exists but is not a member of any aggregate's
  `decomposition_children`" — **this is a real gap D1C's design must close**, not one that upstream code
  already covers.
- **Required addition (RECOMMENDATION, tracked as part of D1C, not D1A):** extend
  `decomposition_graph_semantics.py` (or add a D1C-owned check run immediately after any interrupted-apply
  recovery) to also reject: *any active task whose `provenance.graph_delta_plan_id` names a plan ID, where the
  named parent is not decomposed and does not list this child in `decomposition_children`.* This makes a
  half-applied D1C run **fail closed on next load** rather than silently leaving orphaned children invisible to
  the graph. Recovery is then: an operator inspects the staging leftovers / partial `Tasks/` state, and either
  completes the interrupted apply (re-running D1C, which will recompute a plan and, since the graph is now
  invalid, must itself fail closed and require manual repair) or manually reverts the partially-written files
  from Git history. **D1C must never auto-repair a partially-applied graph by guessing** — this is a
  human/operator recovery path, consistent with "no destructive reset/force-push assumptions" below.

## Git commit boundary

**RECOMMENDATION.** After all `os.replace` calls succeed and a fresh `load_persistent_work_graph` (from the
now-modified working tree, before commit) succeeds, D1C commits with `git add` limited to exactly the changed
paths (never `git add -A`, to avoid absorbing unrelated dirty state that should have already been rejected by
the precondition check) and a single commit using the existing non-attributable automation identity
(`Pipeline/TaskReviewAgent/git_identity_guard.py` — reuse, do not reinvent per `AGENTS.md` line 31).

**One canonical commit, yes.** All task-file, `WORK_ID_MAP.json`, and `RESOURCE_GROUPS.yaml` changes for one
`GraphDeltaPlan` application belong in exactly one commit, with a structured commit message carrying
`plan_id`, parent ID, child ID list, and the human authorization identity. This matches
`decomposition_children`/`inbound_dependency_rewrites` being a single atomic *semantic* unit — splitting it
across multiple commits would let `main` pass briefly through the invalid intermediate states described above.

## Post-commit TaskGraph validation

**RECOMMENDATION.** Immediately after the local commit (before push), run
`load_persistent_work_graph(root)` fresh from that commit's working tree as a final gate. If it fails, **do not
push**; instead `git reset --hard <pre-commit-sha>` on the *local, disposable D1C checkout only* (never on any
shared/controller checkout) and report `post_commit_validation_failed`. This is a local, single-branch,
pre-push reset — explicitly not the "no destructive reset" restriction described in `AGENTS.md`/global agent
policy, which is about not discarding *shared or human* state; a disposable D1C-owned checkout that has not yet
pushed has no shared state to lose.

## Post-commit source identity

**RECOMMENDATION.** The published closeout artifact must record the new commit SHA, new tree SHA, and the
`plan_id` applied, so any later process (including a second D1C run for an unrelated parent) can bind to this
as its new `parent_before` baseline via the same identity-binding mechanism described above.

## Recovery if commit/push/Issue update fails

- **Commit succeeds, push fails** (network, non-fast-forward because `main` advanced): the local commit is not
  lost — the disposable D1C checkout still has it. D1C must **not** force-push. If the push failed for a purely
  transient reason and `main` did not advance, retrying the identical push is safe under the same authorization
  (identity binding still matches the same HEAD). If `main` did advance — the ordinary non-fast-forward case —
  rebase is unsafe here (a decomposition commit touches specific files with exact hash preconditions), and the
  identity-binding check in §"Source HEAD/tree binding" will fail against the new HEAD: **discard the local
  commit and report `stale_proposal`.** Because `source_graph_semantic_hash` is a whole-graph hash, this is true
  even when the advancing commits never touched the decomposed parent, its children, or its dependents.
  Recovery requires the orchestration layer to rerun D1B against the new `main` (producing a new `GraphDeltaPlan`
  with a new `plan_id`) and obtain **independent human re-authorization** for that new `plan_id` — per
  `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Human review/approval boundary," an operator's earlier `APPROVE` names
  the old `plan_id` and does not carry forward to a new one. D1C must never treat "the decomposition result JSON
  is unchanged" as license to silently resubmit under a stale authorization.
- **Push succeeds, Issue/PR update fails:** the graph mutation is now real on `main`. This must be treated the
  same way `109380b fix: tolerate GitHub read-after-write lag` (visible in this repo's recent commit history)
  treats a successful GitHub write with a stale read: retry the Issue/closeout update with bounded
  read-after-write tolerance; never attempt to "undo" the already-pushed commit to compensate for a
  GitHub-side visibility failure.

## No destructive reset/force-push assumptions

Explicitly disallowed for any shared branch: `git push --force`, `git reset --hard` against `origin/main` or
any checkout another worker might be using, deleting another worker's branch. The only reset permitted above is
strictly local and strictly pre-push, on a disposable checkout D1C itself created and no one else has read.

## Idempotency/replay behavior

**RECOMMENDATION.** Applying the same `plan_id` twice must be a safe no-op, not a duplicate mutation.
Idempotency must be checked **before** the normal fresh-source eligibility/recompute path, because a successfully
applied parent is now `decomposed` / `execution_scope=not_applicable` and current
`plan_graph_delta()` deliberately refuses such a parent; therefore "recompute the old plan and observe zero
diff" is **not a valid idempotency mechanism**.

Instead, use the stored reviewed plan as the identity to inspect the current committed graph. Report
`already_applied` only when a fresh full graph load/validation succeeds and the committed graph proves this exact
plan is already represented: every child ID allocated by the stored plan exists with
`provenance.graph_delta_plan_id == plan_id` and the expected parent identity, the parent is decomposed and its
`decomposition_children` includes those exact plan children, and current decomposition semantics show no active
dependent still points at the aggregate parent. If those facts are incomplete or inconsistent, do not guess
that the plan was applied — fail closed as stale/partial state requiring normal recovery or operator inspection.
This directly defends against the "decomposition applied twice" race in
`CONCURRENCY_AND_FAILURE_MODEL.md` without asking `plan_graph_delta()` to accept an already-decomposed parent.

## No TTL stealing

Consistent with the existing claim-ref policy (`claim_refs.py`): D1C needs claim authority during application on
the parent, every affected existing dependent contract, every affected resource, and the global
decomposition-apply serialization point (see `ORCHESTRATOR_INTEGRATION_DESIGN.md` §"Serialization of graph
mutation" and §"Protecting existing task contracts D1C rewrites"). That claim authority follows the exact same
no-TTL, exact-SHA-fenced, manual-repair-only policy already in production (`claim_refs.py`'s crash policy). D1C
must not invent a second, weaker locking primitive — but see those two sections for why the *shape* of the
claim (multiple task refs acquired atomically in one push, and a logical resource token rather than a literal
new ref) is a real, new, minimal extension of `GitRefClaimClient`, not a zero-code reuse.
