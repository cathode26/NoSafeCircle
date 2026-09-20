I've read the brief and inspected the selection, workflow-store, state-machine, checkout, conformance, and authority code. Below is the architecture review. All file references are at frozen commit `131cc63`.

First, the load-bearing facts I verified in the repository, since the brief says to treat docs as claims:

- With no `-TaskId`, `run_pipeline_agent.py:169` calls `select_agent_ready_task`, which only reads the validated agent-ready queue and raises on empty (`generic_selection.py:24-28`). There is no fresh-task path; `execution_authority.py:30-39` unconditionally returns `authorized=False`.
- Issue creation is not guarded: `IssueWorkflowService.acquire_agent_lease` does `find()` → `_initialize_issue()` → `create_issue` (`issue_workflow_store.py:419-421, 386-391`). `find()` raises on multiple matches (`issue_workflow_store.py:270-274`) — *after* duplicates exist.
- The lease transition is read-then-write: compute event `sequence = state_version + 1` (`issue_workflow.py:597`), `add_comment`, `update_issue`, then a verify re-read (`issue_workflow_store.py:485-506`). Duplicate sequences make the whole chain invalid (`issue_workflow.py:896-897`), so a race fails closed — but by *wedging the Issue for everyone*, not by electing a winner.
- Resource conflicts are a read-only snapshot over Issues in `agent_working`/`human_action_required`/`blocked` (`issue_workflow_store.py:339-343`). Notably `agent_ready` does **not** reserve.
- Labels are updated via read-current-labels → add/remove diff (`issue_workflow_store.py:930-936`) — read-modify-write, not CAS.
- The task branch is created only locally at claim time (`real_checkout.py:538-544`) and reaches origin only at handoff (`real_workflow.py:315-327`), so today no remote ref exists during the claim window.
- Task contracts carry no priority field (no `Tasks/*.yaml` contains `"priority"`); ordering everywhere is numeric-ID or issue-number sort (`taskcontrol.py:20-25`, `issue_workflow_store.py:700`).

---

# Current race window

Assume the fresh-selection feature is added naively (deterministic candidate enumeration bolted onto the existing calls) and two workers, W1 and W2, start `Start-GameTaskAgent.ps1` with no arguments against an empty Issue queue. The timeline has six distinct race windows:

**R1 — Candidate selection (guaranteed collision).** Both workers read the same `origin/main`, the same TaskGraph, the same conformance results, and the same (empty) Issue list. Any deterministic ranking means they select the *same* task. Determinism, which the brief correctly requires for authority, converts a probabilistic collision into a certain one. The selection step therefore cannot be the safety mechanism; something downstream must arbitrate.

**R2 — Issue existence check → creation.** Both call `find(task_id)` → `None`, both call `_initialize_issue` → `gh issue create` (`issue_workflow_store.py:386-391`). GitHub happily creates two Issues for NSC-053. From then on, every `find()` for that task raises "multiple open GitHub Issues match" (`issue_workflow_store.py:270-274`): the task is wedged for both workers and for all future workers until a human closes one Issue. This race does *not* fail closed into a recoverable state — it fails closed into a permanently stuck one.

**R3 — Lease event append (split-then-wedge).** If only one Issue exists (e.g., W2's create raced behind W1's and W2's `find()` now sees it in `agent_ready`), both workers read `state_version = 0` and both build a sequence-1 `agent_lease_acquired` event. Comments append independently; two sequence-1 events land. Each worker's verify re-read (`issue_workflow_store.py:500-506`) then fails chain validation (`issue_workflow.py:896-897`) — for *both* of them. No split lease (good), but the Issue's event log is permanently corrupt: `validate_event_chain` can never pass again, so the Issue drops out of `list_agent_ready` and needs manual comment surgery. This is the resume race too — it exists today whenever two workers resume the same `ready[0]` from a non-empty queue, since both `generic_selection.py:29` and `durable_selection.py:95` pick the first item of the same sorted list.

**R4 — Label/body last-writer-wins.** `update_issue` computes label diffs from a freshly read Issue (`issue_workflow_store.py:927-936`). Interleaved with another writer, the Issue can end with zero or two `nsc-state:*` labels and a body whose state block belongs to the loser. The snapshot validator flags the mismatch (`issue_workflow_store.py:224-230`), again wedging rather than electing.

**R5 — Exclusive-resource reservation.** W1 selects NSC-053 and W2 selects NSC-054 (both in `logical:enemy-locomotion-behavior-surface`, `RESOURCE_GROUPS.yaml:14-23`). Both run `_resource_conflicts` before either lease lands; both see no reserving Issue; both acquire leases on *different* Issues. Each Issue's event chain is individually valid, so **nothing ever fails closed here**. Two agents now hold concurrent leases on tasks that the GDD-derived pipeline constraint ("No concurrent Unity asset edits", `PROJECT_REQUIREMENTS.yaml:24-38`) says must be sequential. This is the most dangerous window because it is silent.

**R6 — Checkout and branch creation.** Same machine: the canonical path `<CheckoutRoot>/<TASK-ID>` collision is handled — staging-clone-then-rename, with an existence check that refuses to overwrite (`real_checkout.py:546-556`). Cross-machine: two checkouts of the same task on different machines are both locally valid; the collision surfaces only at handoff push, when the second `git push` of the task branch is rejected as non-fast-forward — after hours of duplicated implementation work. Also note `remote main moved during checkout preparation` is already detected (`real_checkout.py:534-537`).

Cross-cutting: `main` advancing or a contract migration mid-dispatch is largely covered by contract-hash pinning (`durable_selection.py:90`, `issue_workflow_store.py:428-431`), and completed-task duplication is covered by `completed_issue_guard.py`. Abandoned work is *not* covered: a manually closed non-complete Issue is invisible to candidates (`completed_issue_guard.py:69-70`) while its pushed task branch may still exist on origin; a fresh claim would create a new Issue whose eventual handoff push collides with the stale branch.

# Safety and liveness invariants

Safety (must never be violated, even under crash + concurrency):

- **S1 — Single Issue per task.** At most one open managed Issue exists per task ID, ever, across all machines.
- **S2 — Single lease.** At most one worker is recorded in `agent_working` per task; a worker acts only while its `worker_id`/`lease_id` are the current ones.
- **S3 — Exclusive-resource exclusion.** For each `exclusive_resources` key, at most one task is anywhere between claim-win and Issue `complete`. (Stronger than today's rule, which exempts `agent_ready` — see Resource-conflict revalidation.)
- **S4 — Deterministic authority.** The chosen task is a pure function of: the committed dispatch policy, the committed TaskGraph at a recorded commit, deterministic conformance evaluation, the Issue-queue snapshot, and the claim-ref snapshot. No LLM ranks or selects; `not_delivered` alone never implies eligibility.
- **S5 — Event-chain integrity.** Contiguous sequences, valid hash chain, one state block, one state label — exactly the current `validate_event_chain` rules, preserved as the last-line backstop.
- **S6 — Terminal permanence.** A task with a closed `complete` Issue or `conformant` state is never re-claimed or re-initialized.
- **S7 — Additive Git only.** The claim mechanism creates/deletes refs only inside a dedicated namespace; it never force-pushes, rewrites, or deletes branches, per the global operating rules.

Liveness (must eventually hold):

- **L1 — Progress.** If ≥1 eligible task exists and ≥1 worker runs, some worker acquires some task. A claim loser deterministically retries the next candidate rather than exiting.
- **L2 — Bounded termination.** A worker terminates after a bounded number of claim attempts with a distinct machine-readable exit status; it never spins.
- **L3 — Crash convergence.** After a worker crashes at *any* protocol boundary, re-running the ordinary no-argument command (by anyone, on any machine) either resumes or releases the partial state within one lease TTL, with no manual Git or Issue surgery for any single-crash scenario.
- **L4 — No wedge from a clean race.** Two healthy concurrent workers must never produce a permanently invalid Issue (this is where the current design fails: R2/R3 satisfy "no split lease" but violate L4).

# Claim mechanism comparison

The linearization point must be a single durable compare-and-swap that all machines share. Candidates from the brief:

**A. Atomic creation of a deterministic remote Git ref (recommended).**
A `git push` that *creates* a ref is a server-side atomic test-and-set: receive-pack locks the ref, and of two concurrent creators exactly one succeeds while the other is rejected. With `git push --atomic` a multi-refspec push commits all refs or none, which lets one claim cover the task *and* every exclusive resource in a single linearizable operation. Properties: durable (lives on GitHub), cross-machine by construction, uses the exact auth surface the pipeline already requires (branch push), O(1) observability via `ls-remote`, and testable against a local bare repository with identical semantics. The claim ref can point at a small commit whose blob records `{worker_id, task_id, source_head, task_contract_sha256, created_at_utc, nonce}` — a durable receipt and a fencing token in one. Weaknesses: refs need garbage collection after crashes (solvable with TTL + fenced deletion via `--force-with-lease=<ref>:<expected-sha>`), and refs outside `refs/heads/` are invisible to branch protection (irrelevant here — the namespace carries no reviewed content).

One deliberate sub-choice: use a dedicated `refs/nsc/claims/...` namespace, **not** the task branch itself, as the claim. The task branch name embeds the title slug (`real_checkout.py:105-106`) so it changes across contract revisions; the branch is semantically "implementation content pushed at handoff" and the handoff verifier requires the remote branch head to equal the tested commit (`real_workflow.py:315-327`). Overloading it as a claim conflates claim lifetime with content lifetime and complicates abandoned-branch recovery.

**B. Serialized GitHub Actions dispatcher.**
A single `workflow_dispatch` "claim" workflow with a `concurrency` group would serialize all claims through one runner. Rejected as primary: GitHub Actions `concurrency` queues at most one pending run and *cancels* older pending runs, so a third concurrent claimer's request is silently dropped — a liveness hole exactly in the multi-worker case we are designing for. It also couples every claim to Actions availability and queue latency (tens of seconds to minutes), makes the local two-worker regression test the brief demands effectively impossible to run hermetically, and gives the runner write authority that then needs its own audit story. Actions remains valuable where it already sits: as the *validator* of human label transitions (`nsc-issue-workflow.yml`, `issue_workflow_action.py`), which is idempotent per Issue and tolerant of cancellation.

**C. Append-only claim election via a coordination Issue.**
Comment creation is atomic and comments are totally ordered by ID, so "first comment claiming (task, epoch) wins" is a real linearization point. Rejected as primary: the election read is a *list* operation whose read-after-someone-else's-write timing GitHub does not contract; a worker must re-read and may see its own comment before a slightly earlier rival's, requiring settle-delays or multi-round confirmation. It also needs epoch bookkeeping to distinguish claim generations, grows an unbounded hot Issue, and duplicates what the per-task event chain already does well. The mechanism is sound but strictly more moving parts than A for the same guarantee.

**D. Local file locks.** Excluded by the brief and correctly so: they serialize one machine's processes only, and the operator explicitly runs multiple machines/terminals.

**Chosen linearization point:** the atomic creation of `refs/nsc/claims/<TASK-ID>/v<state_version>` (plus resource refs, same atomic push) on the GitHub origin. Every state-advancing claim — fresh or resume — is won or lost at that single ref-creation instant.

# Recommended atomic claim protocol

## Deterministic authority and priority (prerequisite)

Fresh selection is enabled by a new committed, versioned policy file, `Pipeline/TaskGraph/DISPATCH_POLICY.yaml`:

```json
{
  "schema_version": "1.0",
  "enabled": true,
  "priority_tiers": [
    {"tier": 1, "reason": "current vertical slice", "tasks": ["NSC-053", "NSC-054", "NSC-055"]},
    {"tier": 2, "reason": "door chain", "tasks": ["NSC-050", "NSC-051"]}
  ],
  "unlisted_tasks": "ineligible",
  "wip_limit_total": 3,
  "wip_limit_per_worker": 1,
  "claim_ttl_minutes": 30,
  "allowed_kinds": ["implementation"],
  "allowed_execution_scopes": ["single_agent"]
}
```

Priority comes from the human operator's ordered tiers in this reviewed file — this answers "where does task priority come from." Within a tier, ties break by numeric ID, and *that* choice is now explicit and committed rather than a silent artifact of sort order. `"unlisted_tasks": "ineligible"` keeps deny-by-default: nothing is dispatched merely for existing ("do not silently enable every active task"). `execution_authority.assess_execution_authorization` is rewritten to read this file; absent or `enabled: false` reproduces today's denial with the existing reason-code mechanism.

Eligibility for a fresh candidate is the conjunction of explicit checks (each producing a recorded reason on failure):

1. listed in an enabled policy tier;
2. `contract_disposition == "active"`, `kind` and `execution_scope` in the policy's allowed sets, `decomposition_state == "concrete"` (mirrors `real_checkout.py:379-390`);
3. `evaluate_current_conformance(task) == "not_delivered"` — and explicitly *not* `needs_replan` / `needs_testing` / `needs_human` / `invalid_evidence`, which route to the operator (`current_conformance.py:345-356`);
4. every `depends_on` entry evaluates `conformant` (the existing `dependencies_conformant` computation, `real_observation.py:289-294`) — conformance of the task's dependencies, never `not_delivered`-ness of the task, is what establishes readiness;
5. no open managed Issue and no closed-complete Issue for the task (via `completed_issue_guard`);
6. **no pre-existing remote task branch**: `ls-remote refs/heads/<branch_name(task)>` must be empty, otherwise the task is classified `abandoned_branch_requires_human` — this is the explicit handling of previously abandoned work;
7. no exclusive-resource overlap with any reserving Issue or active claim ref (next section);
8. open-Issue count in non-complete states plus active claims < `wip_limit_total`, and this worker holds < `wip_limit_per_worker`.

The candidate list is emitted as a durable JSON receipt (task order, per-task reasons, inputs' hashes: policy blob SHA, `source_head`, Issue-queue snapshot) under the worker's output root, so any selection is auditable and reproducible.

## The claim protocol

Namespace: `refs/nsc/claims/task/<TASK-ID>/v<N>` (transition guard for advancing the Issue from state_version N) and `refs/nsc/claims/res/<sha256-16(resource_key)>` (resource guard). Each ref points to a claim commit (empty tree, JSON message) recording worker, task, `source_head`, contract hash, UTC time, and a random nonce.

**Fresh claim (empty queue), per candidate in policy order:**

1. **Select** candidate C deterministically (above). Record receipt.
2. **CAS-win:** one `git push --atomic origin <claim>:refs/nsc/claims/task/C/v0 <claim>:refs/nsc/claims/res/<r1> ...` for all of C's exclusive resources. Rejected ⇒ claim lost; refresh the claim-ref snapshot, exclude C and any resource-conflicted candidates, continue with the next candidate (this is the loser-retries path). Accepted ⇒ this is **the linearization point**: W1's and W2's pushes for the same task or overlapping resources cannot both succeed.
3. **Revalidate after winning** (main may have advanced during steps 1–2): re-fetch `origin/main`; recompute the contract hash at the new head; re-run `find(C)`; re-run the resource check against Issues. Contract changed, an Issue appeared, or a resource became Issue-reserved ⇒ **abort**: fenced-delete own refs, restart selection. Never proceed on stale identity.
4. **Initialize the Issue** exactly as `_initialize_issue` does today (state_version 0, `agent_ready`). Then verify with `find(C)`: exactly one match whose state block is ours. If two Issues are somehow found (residual window), deterministic self-repair: lower Issue number is canonical; the worker that created the higher one closes it with a "duplicate, superseded by #N" comment and, if it created the lower one, proceeds; otherwise aborts to resume path.
5. **Acquire the lease** (`agent_lease_acquired`, sequence 1) — safe because only the holder of `.../v0` may write this transition, and before *each* Issue write the worker re-verifies via `ls-remote` that the claim ref still points at its exact claim commit (fencing check).
6. **Verify** the transition with the existing re-read (`issue_workflow_store.py:500-506`) — S5 remains the backstop if the fencing discipline is ever violated.
7. **Release the claim:** fenced-delete `.../v0` and all resource refs (`git push --force-with-lease=<ref>:<claim-sha> origin :<ref>`). From this instant, the open Issue itself (in *any* non-complete state, per the reservation fix below) is the durable reservation of both the task and its resources.
8. **Checkout** proceeds unchanged through `ResumableTaskCheckoutManager.prepare` — checkout creation is deliberately *after* the durable lease, so a checkout failure leaves a resumable `agent_working` Issue, not an orphaned directory holding an implicit claim.

**Resume claim (non-empty queue), fixing today's R3:** to transition an existing Issue observed at `state_version = N`, first CAS-create `refs/nsc/claims/task/<ID>/v<N>`; only the winner appends event N+1; the ref is fenced-deleted after the verify re-read. The loser re-reads the Issue: if it moved to `agent_working` by another worker, take the next queue item; the queue-drain loop replaces the current "always take `ready[0]`" logic. No resource refs are needed on resume: the open Issue already reserves them.

**Operator CLI semantics** (`run_pipeline_agent.py` exit codes; `Start-GameTaskAgent.ps1` maps them to messages):

| Invocation / situation | Behavior | Exit |
|---|---|---|
| no args, work obtained (resume or fresh) | runs the pipeline as today | 0 |
| `-TaskId NSC-###` | same full eligibility + claim protocol; only *ranking* is skipped — no bypass of dependency/resource/branch checks | 0 / below |
| `-ResumeOnly` (retained) | current behavior; empty queue is a clean stop | 3 |
| zero eligible work (queue empty, no policy candidate) | prints the per-task reason table from the receipt | 3 |
| policy missing or `enabled: false` | names `DISPATCH_POLICY.yaml` and the enabling steps | 4 |
| candidates exist but all blocked by deps/resources/WIP | prints blocking reasons per candidate | 5 |
| lost a claim | **not an exit**: retry next candidate, bounded at `min(len(candidates), 10)` attempts, then 3/5 |
| contract/chain/identity integrity error | stop for human | 2 |

3/4/5 are non-error idle states distinguishable by schedulers; 2 remains "human needed."

# Crash and orphan recovery

Every boundary from the brief, with the deterministic recovery:

| Failure point | Durable state left | Recovery |
|---|---|---|
| Candidate selected, claim not won | none (receipt file only) | Nothing to recover; next candidate or exit 3/5. |
| Claim won, crash before Issue created | claim refs only | Same worker rerun: recognizes its own `worker_id` in the claim commit, resumes at step 3. Others: CAS fails; after `claim_ttl_minutes` with no Issue and the ref's claim commit unchanged, `claim_recovery.py gc` fenced-deletes the refs (`--force-with-lease=<ref>:<sha>` makes deletion itself a CAS, so a revived original and a collector cannot both think they won — the revived worker's next fencing check fails). |
| Issue created, lease not acquired | `agent_ready` Issue at v0 + refs | The Issue is now durably visible: any worker's normal resume path picks it up via `list_agent_ready`; its resume-CAS on `v0` supersedes the orphan refs, which the GC then removes (Issue exists ⇒ task ref redundant). |
| Lease acquired, checkout not created | `agent_working` Issue, refs released | Already handled today: same worker resumes (`status: "resumed"`, `issue_workflow_store.py:432-433`); a different worker sees `agent_working_by_other` and skips. Lease staleness (worker died for good) is a human `blocked`/release decision or a future lease-TTL event — the design does not let agents steal `agent_working` leases automatically, matching the fail-closed doctrine. |
| Process crash mid-Issue-write | possibly a comment without a body update | The snapshot validator already flags label/state mismatch; because only the fenced ref-holder could have written, there is at most one seq-N+1 event — the same worker (or, after GC + re-CAS of `v<N>`, a successor holding the guard) completes the body/label update idempotently by replaying the transition it can reconstruct from the last event. No duplicated sequences can exist, so the wedge of R3 is gone. |
| Stale/orphan branch or claim | remote task branch with no open Issue | Fresh-selection check 6 refuses to claim; `claim_recovery.py list` reports it as `abandoned_branch_requires_human`. Never auto-deleted (S7). |
| Contract or `main` advanced during dispatch | contract hash mismatch | Abort at step 3 (fresh) or the existing hash guards (`issue_workflow_store.py:428-431`, `durable_selection.py:90`); the claim is fenced-deleted and selection reruns against the new head. |
| Candidate became resource-conflicted during claim | overlapping ref/Issue detected at step 3 | Abort, delete refs, next candidate. |
| Zero eligible work / all blocked | — | Exit 3 / 5 with reasons. |
| Completed or abandoned task | closed `complete` Issue / closed draft | `completed_issue_guard` keeps completed tasks terminal (S6); closed non-complete Issues stay ignored, and the branch check above catches their leftovers. |

Cross-machine behavior: all claim state lives on the GitHub origin, so the protocol is machine-agnostic by construction. Worker IDs already embed hostname (`run_pipeline_agent.py:64-69`). Clock skew: TTLs are advisory triggers only — every destructive step (ref deletion) is fenced on the exact claim-commit SHA, never on wall-clock alone, so skewed clocks can delay GC but cannot cause a double-grant. Checkout paths remain per-machine canonical; the Issue's recorded `checkout_path` plus the exact-remote-branch resume rules (state-machine doc, `ISSUE_WORKFLOW_STATE_MACHINE.md` "Canonical checkout continuity") already handle resuming on a different machine.

# Resource-conflict revalidation

Three changes, one of which fixes a latent bug that exists independent of this design:

1. **Reservation states must include `agent_ready`.** `_resource_conflicts` currently exempts `agent_ready` (`issue_workflow_store.py:339-343`). An Issue that is `agent_ready` in `repair` or `delivery_evidence` phase has an unmerged pushed branch that edits its exclusive resources; today a second task overlapping those resources can acquire a lease. The rule becomes: **every open managed Issue reserves its task's exclusive resources until `complete`.** This is what makes it safe to release resource claim refs as soon as the Issue exists.
2. **Conflict check inputs = Issues ∪ claim refs.** The revalidation reads both the open-Issue reservations and `ls-remote refs/nsc/claims/res/*`, so a rival's just-won fresh claim is visible before its Issue exists.
3. **Revalidate after the linearization point, not only before.** The pre-claim check is an optimization; the authoritative check is step 3, after winning the atomic push, when no rival can concurrently win an overlapping resource ref. Order of authority: atomic resource refs serialize *fresh vs. fresh*; Issue reservations serialize *anything vs. in-flight*; the post-win revalidation stitches the two.

Also note `generic_selection.py:20` feeds a stub `task_loader` returning empty `exclusive_resources`; harmless today because it never leases, but the fresh-claim path must always use the committed-contract loader (`durable_selection._committed_task` / `real_workflow._load_committed_task`) so resource sets are real.

# Exact module changes

New files:

- `Pipeline/TaskGraph/DISPATCH_POLICY.yaml` — schema above; reviewed via PR like any contract.
- `Pipeline/TaskReviewAgent/claim_refs.py` — `ClaimStore` protocol: `try_claim(refs: dict[ref, payload]) -> won|lost`, `read_claims() -> {ref: (sha, payload)}`, `release(ref, expected_sha)`, `verify_held(ref, expected_sha)`. Implementations: `GitRefClaimStore` (`git push --atomic`, `ls-remote`, fenced deletes against the controller origin) and `MemoryClaimStore`/`FileClaimStore` for tests.
- `Pipeline/TaskReviewAgent/fresh_candidate_selection.py` — deterministic eligibility + tier ordering; emits the JSON selection receipt. Pure host code, no model prompting.
- `Pipeline/TaskReviewAgent/fresh_claim.py` — the protocol driver (steps 1–8), with an `on_step(name)` seam for tests/crash injection; returns a selection dict shaped like `select_agent_ready_task`'s so `run_pipeline_agent` routing is unchanged.
- `Pipeline/TaskReviewAgent/claim_recovery.py` — `list` and `gc` subcommands; `gc` deletes only refs proven orphaned (TTL elapsed + Issue-state cross-check + fenced delete); never mutates Issues.

Modified files:

- `Pipeline/TaskGraph/execution_authority.py` — `assess_execution_authorization` loads `DISPATCH_POLICY.yaml`; returns `authorized=True` with reason code `dispatch_policy_v1_tiered` only for tasks passing policy checks; retains the current denial (same message discipline) when the file is absent/disabled. `taskcontrol.py:69`'s "Autonomous dispatch authority: DISABLED" line becomes policy-derived.
- `Pipeline/TaskReviewAgent/generic_selection.py` — `select_agent_ready_task` gains the queue-drain loop with per-item resume-CAS; on an exhausted queue, delegates to `fresh_claim` instead of raising; new distinct exceptions (`NoEligibleWork`, `PolicyDisabled`, `AllCandidatesBlocked`) for exit-code mapping.
- `Pipeline/TaskReviewAgent/issue_workflow_store.py` — `acquire_agent_lease` accepts an optional `claim` guard and calls `claim.verify_held()` before `add_comment`/`update_issue`; `_resource_conflicts` includes `AGENT_READY` in reserving states and consults the claim store.
- `Pipeline/TaskReviewAgent/run_pipeline_agent.py` — `--resume-only` flag, exit codes 3/4/5, wiring of the claim store (origin URL from the existing `_remote_url` logic).
- `Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1` — `-ResumeOnly` switch; maps 3/4/5 to friendly non-throwing messages (today any nonzero throws, `Start-GameTaskAgent.ps1:279-281`).

Durable receipts/events: the claim commit (in-ref receipt), the selection receipt JSON under the worker output root, and one new optional Issue event detail on `agent_lease_acquired`: `claim_ref`, `claim_commit`, `selection_receipt_sha256` — additive keys inside `details`, no schema-version bump needed since `details` is free-form (`issue_workflow.py:129-140`).

# Concurrency test harness

All tests follow the Unity testing policy's non-mutation invariant: temp directories, disposable bare repos, no tracked-file writes.

**Tier 1 — deterministic in-process interleavings** (`tests/fresh_claim_smoke_test.py`): `MemoryClaimStore` + `MemoryIssueBackend` (already exists, `issue_workflow_store.py:703`) + scripted `on_step` hooks that pause worker A at a named boundary while worker B runs to completion. Covered scripts: both-select-same-task (loser retries and gets task 2); overlapping-resource fresh claims (exactly one wins the atomic multi-ref claim); rival Issue appears between CAS-win and initialize (abort path); contract hash changes after CAS-win (abort path); resume race on one `agent_ready` Issue (loser drains to next queue item); crash injected after *each* of the 8 protocol steps followed by (a) same-worker rerun and (b) other-worker rerun + `gc`, asserting convergence to invariants S1–S6; ABA revival (GC deletes, original revives, fencing check rejects its write).

**Tier 2 — real two-process race from an empty queue** (the brief's required test): a temp *bare* Git repository as `origin` (file:// transport exercises genuine receive-pack ref locking and `--atomic` semantics), a `FileIssueBackend` implementing the `IssueBackend` protocol over a shared directory where each API call is a single `O_CREAT|O_EXCL` or lock-guarded write — mimicking GitHub's per-request atomicity while leaving the *between-call* races fully real. Two `subprocess` workers block on a barrier file, then run the full claim path against a policy with two eligible tasks (variant B: two tasks sharing one exclusive resource; variant C: one task). Assertions after both exit: distinct task IDs claimed (variant A), exactly one claim succeeded and the other exited 5 (variant B/C), exactly one Issue file per task, exactly one sequence-1 `agent_lease_acquired` per Issue, `validate_event_chain` passes for every Issue, resource sets of `agent_working` Issues are pairwise disjoint, and zero refs remain under `refs/nsc/claims/`. Repeat the whole race 20× for scheduler-driven interleaving diversity — allowed because every assertion is invariant-based, not order-based.

**Tier 3 — orphan recovery end-to-end:** kill worker A (SIGKILL via a `NSC_TEST_CRASH_AFTER=<step>` seam) at each boundary, run worker B, assert B either completes A's partial state or claims different work, then run `claim_recovery.py gc` with a zero TTL override and assert the ref namespace is empty and every Issue still chain-validates.

**Regression pins:** the current wedge behaviors become explicit regression tests — duplicate-Issue creation and duplicate-sequence events must now be *unreachable* through the guarded path, and the tests assert the guard refuses the write rather than relying on post-hoc chain invalidation.

# Designs that appear safe but are not

1. **Labels as a lock.** `gh issue edit --add-label` is read-modify-write server-side merged; two workers can both "win" the `agent-working` label, and list endpoints can serve stale label sets. The brief bans this; the code's own label handling (`issue_workflow_store.py:930-936`) shows why.
2. **Verify-after-write as a CAS.** The existing re-read (`issue_workflow_store.py:500-506`) *detects* races but resolves none: both writers fail, and the duplicate-sequence comments permanently poison `validate_event_chain`. Detection without election violates L4. Keep it — as a backstop, not the mechanism.
3. **"Create the Issue, then dedupe by lowest number."** Without a prior ref guard, both `gh issue create` calls succeed, and the loser may already have appended lease events to its copy before either sees the other (Issue list reads lag). Dedupe is acceptable only as a last-resort repair behind the CAS, never as the protocol.
4. **Deterministic selection as collision avoidance.** "Two workers will probably pick different tasks" is exactly backwards: required determinism guarantees they pick the *same* one. Arbitration must be downstream of selection.
5. **The task branch as the claim ref.** Tempting (it's already a deterministic ref), but the branch name embeds the mutable title slug (`real_checkout.py:105-106`), the branch is created at handoff-push semantics today, and the handoff verifier requires remote-branch == tested commit — a claim-time push of an empty branch at `main` breaks abandoned-branch detection and entangles claim GC with implementation history. Use a dedicated namespace.
6. **Multi-ref push without `--atomic`.** Default push updates refs independently; worker A could win the task ref while B wins one resource ref — a deadlock-ish partial claim. Atomicity must be requested explicitly.
7. **`--force-with-lease` without explicit expected values.** The bare form leases against local remote-tracking refs, which are only as fresh as the last fetch; only the `<ref>:<expected-sha>` form is a real CAS. This matters for GC deletes.
8. **TTL-only claim stealing.** Deleting a "stale" claim by timestamp alone invites ABA: the original worker revives post-GC and writes with a claim it no longer holds. Every delete must be fenced on the claim-commit SHA and every holder must re-verify its ref before each durable write.
9. **A GitHub Actions `concurrency` queue as the dispatcher.** Pending-run *cancellation* (queue depth 1) silently drops the third-and-later claimers — a built-in lost-wakeup. Fine for idempotent label validation; wrong for claim election.
10. **Equating conformance with readiness.** `derived_state == "not_delivered"` plus `dependencies_conformant` describes *deliverability*, not *authorization*; `needs_testing`/`needs_replan` states (`current_conformance.py:345-356`) look temptingly close to "ready to work on" but route to humans. The policy file is the only thing that turns readiness into dispatch authority.
11. **Trusting the resource snapshot.** The current `_resource_conflicts` is doubly unsafe: it is a non-atomic read (R5) *and* it exempts `agent_ready` Issues that still hold unmerged branches touching exclusive resources. Both halves must be fixed; fixing only the atomicity would still let a fresh claim overlap an Issue sitting in `agent_ready`/`repair`.
12. **The canonical checkout directory as a lock.** It serializes one machine only, and its existence check races with `rename` on network filesystems; the brief explicitly excludes single-machine reasoning. It stays what it is today — a local safety net (`real_checkout.py:546-556`), not the claim.

**Bottom line:** the linearization point is the atomic `git push --atomic` creation of `refs/nsc/claims/task/<TASK-ID>/v<N>` plus per-resource refs on the GitHub origin; a committed `DISPATCH_POLICY.yaml` supplies the only fresh-dispatch authority and the only priority order; the existing event-chain validation is retained unchanged as the fail-closed backstop; and the two independently silent defects worth fixing regardless of this design are the unguarded `gh issue create` duplicate window and the `agent_ready` exemption in `_resource_conflicts`.
