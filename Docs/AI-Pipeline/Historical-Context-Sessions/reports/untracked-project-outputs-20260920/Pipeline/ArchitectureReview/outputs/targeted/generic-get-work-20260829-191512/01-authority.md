I've read the brief and inspected the pipeline code (`execution_authority.py`, `taskcontrol.py`, `current_conformance.py`, the Issue workflow store and its lease mechanics, the selection modules, checkout/branch conventions, task contracts, resource groups, and the test inventory). Below is the design. Throughout, **[fact]** marks something verified in the frozen checkout at `131cc63`, and **[rec]** marks a recommendation.

## Current authority gap

**[fact]** `Pipeline/TaskGraph/execution_authority.py:30-39` unconditionally returns `authorized=False` with reason code `evidence_derived_dispatch_policy_not_enabled` for every task; `taskcontrol.ready_tasks()` (`taskcontrol.py:205-211`) raises `UnsafeExecutionAuthorizationError` by design, and `taskcontrol ready` prints "DISPATCH POLICY NOT ENABLED" for schema-v2 graphs.

**[fact]** With no `-TaskId`, `run_pipeline_agent.py:163-174` calls `generic_selection.select_agent_ready_task`, which only resumes an already-initialized `nsc-state:agent-ready` Issue and stops with exit 2 on an empty queue (`generic_selection.py:23-28`). Fresh work can only enter the system when a human passes `-TaskId`, which then initializes the Issue via `IssueWorkflowService._initialize_issue` with **no dependency, decomposition, disposition, priority, or WIP check at all** — `acquire_agent_lease` (`issue_workflow_store.py:403-506`) checks only exclusive-resource overlap against other open Issues and the contract hash.

**[fact]** There is no priority signal anywhere: schema-v2 contracts carry no priority field (`Tasks/NSC-053.yaml`, `task_contract_schema.py`), and both resume orderings are issue-number order (`issue_workflow_store.py:700`, `completed_issue_guard.py:110`). The project's own architecture-review evidence flags that "the ready list is ID-ordered and encodes safety only weakly."

**[fact]** There is no linearization point for a fresh claim. `acquire_agent_lease` is read → post comment → edit body → re-read verify. A two-worker race on the *same* task fails closed (duplicate event sequence numbers invalidate the chain — `issue_workflow.py:896-915`, `ISSUE_WORKFLOW_STATE_MACHINE.md:218`), which protects against split leases but means a race produces two failures, not one winner. Nothing at all serializes two workers *initializing Issues for two overlapping candidates* from an empty queue — `_resource_conflicts` (`issue_workflow_store.py:325-359`) only sees Issues that already exist, so two concurrent fresh dispatches can both pass it.

The gap is therefore exactly three missing committed artifacts: a **dependency-readiness definition**, a **dispatch authorization policy with human-owned priority and WIP limits**, and a **claim linearization mechanism** for fresh work.

## Candidate eligibility predicate

**[rec]** Define one pure, deterministic function, `evaluate_fresh_dispatch_eligibility(graph, policy, issue_snapshot, remote_refs, task_id) -> EligibilityAssessment`, evaluated against a single recorded `origin/main` HEAD. A task is a fresh-dispatch candidate iff **all** of the following hold; every failure gets a stable reason code in the assessment so `taskcontrol` can print why each task is excluded.

1. **Contract shape.** `schema_version == "2.0"`, `contract_disposition == "active"`, `kind ∈ {"implementation", "artifact"}`, `execution_scope == "single_agent"`, `decomposition_state == "concrete"`. **[fact]** `coarse`, `decomposed`, `needs_future_decomposition`, `needs_execution_decomposition`, and `not_applicable` all exist in `Tasks/` today and none is safely executable by one agent; `evaluate_current_conformance` already classifies features/non-single-agent contracts as `aggregate` (`current_conformance.py:244-246`).

2. **Own conformance state is exactly `not_delivered`.** But — honoring the brief — `not_delivered` is *necessary, never sufficient*; it is one clause among nine. `needs_testing`, `needs_replan`, `needs_human`, `invalid_evidence`, and `ambiguous_evidence` are **not** fresh-dispatch states in policy v1: they mean prior evidence exists and requires human triage or a resume path, so they yield `blocked_needs_human_triage`, not eligibility.

3. **Dependency readiness (the missing definition).** For every `d ∈ depends_on`: `evaluate_current_conformance(d).state == "conformant"` — which for a decomposed feature dependency is already the derived aggregate-of-children conformance (`current_conformance.py:138-214`). A dependency whose disposition is `superseded` or `cancelled`, or whose state is anything else, makes the candidate ineligible with reason `dependency_not_conformant`; there is no transitive shortcut and no "probably done" tier. `dirty_worktree` on any evaluation fails the whole enumeration closed (mutation invariant).

4. **Policy authorization.** The task ID appears in the committed dispatch policy's priority lanes (below) and the policy is `enabled`. Absence means ineligible — this is how "do not silently enable every active task" is enforced structurally.

5. **Issue state.** Using completed-Issue-aware discovery (`completed_issue_guard.install_completed_issue_guard()` must be installed on this path): no open managed Issue exists for the task in any state (an open Issue means resume, not fresh dispatch), and no closed `COMPLETE` Issue exists. A closed COMPLETE Issue together with a non-conformant TaskGraph state is a contradiction to surface for human review, never to dispatch through. Closed non-complete Issues (abandoned drafts) do not block, but their numbers are recorded in the claim receipt.

6. **Branch and claim-ref state.** No remote branch `nsc-###-<title-slug>` (**[fact]** deterministic name, `real_checkout.py:105-106`) and no claim ref `refs/nsc/claims/NSC-###` exists at the fetched remote. An orphan task branch or claim ref with no matching open Issue makes the task ineligible with reason `orphan_remote_state_requires_reconciliation` — recovery is explicit (see receipts), never silent reuse.

7. **Resource authority.** `exclusive_resources` must be disjoint from (a) resources of every open Issue in `agent_working`, `human_action_required`, or `blocked` (the existing `_resource_conflicts` semantics, but driven by committed contracts, not the stubbed empty `task_loader` used at `generic_selection.py:20` **[fact]** — that stub must be replaced with `_committed_task` as `durable_selection.py:34-55` already does), and (b) resources of any task with a live claim ref. `RESOURCE_GROUPS.yaml` stays the authority for which tasks share a resource; `work_graph_validate.py:365-417` already cross-checks membership **[fact]**.

8. **WIP limits** (below) not exceeded.

9. **Freshness.** The predicate's inputs were all read at one recorded `origin/main` SHA fetched at dispatch start; if the remote advances before the claim completes, re-evaluate.

## Priority and WIP policy

**[rec]** Priority is a **human-authored, committed, ordered artifact**, not a derived score. Source of truth: Vincent encodes it, informed by the GDD Section 5 six-week plan and the "Schedule-slip scope-reduction order" already captured in `PROJECT_REQUIREMENTS.yaml` **[fact]** (required systems — spells, two enemy types, door loop, pursuit, final escape — outrank stretch). The policy file holds ordered *lanes*:

```yaml
priority_lanes:
  - lane: "required-critical-path"
    rationale: "GDD Section 5 six-week plan, weeks 3-4"
    task_ids: ["NSC-053", "NSC-054", "NSC-055", ...]   # order within lane is meaningful
  - lane: "required-followup"
    task_ids: [...]
```

Selection order: first eligible task by lane order, then by within-lane list order. The only tie-break is the list itself — the human's typed order *is* the priority. Task-number ordering appears nowhere in fresh selection. (Resume ordering also changes: among validated agent-ready Issues, resume the one whose task is highest in the lanes; issue-number order remains only as the final deterministic tie-break for tasks the policy ranks identically, and that fact is printed, not hidden.) An LLM never ranks or selects; the whole path is host code.

**WIP limits**, all in the policy file, all counted from the completed-aware Issue snapshot plus live claim refs:

- `max_agent_working: 2` — leases concurrently held (matches "two workers" goal).
- `max_open_managed_issues: 4` — total non-complete managed Issues; prevents fresh dispatch from minting Issues faster than the human can absorb.
- `max_human_action_required: 2` — stop creating new work when Vincent already has two Unity validation handoffs queued; this is the practically binding limit for a one-human pipeline.
- Per-resource concurrency is already structurally 1 via exclusive resources; no extra knob.

When a limit is hit, fresh dispatch reports `blocked_wip_limit` — it does not queue-jump or degrade to resume-only silently.

## Durable state and receipts

**[rec]** Three durable layers, each with a defined owner:

1. **The policy file** — `Pipeline/TaskGraph/DISPATCH_POLICY.yaml` (JSON-subset, like the graph's other files): `schema_version`, `enabled: true|false`, `approved_by`, `approval_reference` (PR URL/number), `priority_lanes`, `wip_limits`, `policy_revision`. **Human approval mechanism:** the policy is enabled only by a reviewed PR to `main` that sets `enabled: true` with `approved_by` naming the human; the dispatcher reads the policy from the fetched `origin/main` HEAD it is claiming against (never a stale local copy), and records that file's semantic SHA-256 as `policy_sha256` in every claim and lease. Approval is thus Git-audited, versioned, and revocable by a one-line revert. Deny-by-default is preserved: file missing, unparseable, `enabled: false`, or hash-invalid ⇒ `execution_authority` keeps returning the current denial.

2. **The claim ref — the linearization point.** Analysis of the brief's options: GitHub label writes and `gh issue edit` are last-write-wins (no CAS) — rejected. A serialized GitHub Actions dispatcher gives real serialization but adds a remote scheduler, latency, and a second execution environment for a two-worker shop — more machinery than the failure model needs. A coordination-Issue election inherits the same non-atomic comment/edit substrate it is trying to fix; the existing event chain makes races *fail closed*, not *elect a winner*. **Chosen: atomic remote ref creation.** The claiming worker builds a claim commit — an empty-tree-delta commit on top of the recorded `origin/main` SHA whose message is a canonical JSON receipt (`task_id`, `worker_id`, `lease nonce`, `base_head`, `task_contract_sha256`, `policy_sha256`, `occurred_at_utc`) — and pushes it to `refs/nsc/claims/NSC-###`. Because every worker's claim commit is unique (nonce), the second creation attempt is rejected by the remote; exactly one worker holds the ref. This is a true compare-and-swap on GitHub's ref store, works across processes and machines, and needs no new infrastructure. The claim ref is *not* a task branch: `refs/nsc/claims/*` is outside `refs/heads/*`, so it never pollutes branch listings, and the claim commit itself is the durable receipt.

3. **The Issue** remains the workflow authority exactly as today. New receipt fields ride in existing event `details`: `workflow_initialized` and `agent_lease_acquired` gain `claim_ref`, `claim_commit`, `policy_sha256`, `eligibility_evaluated_at` (the base SHA). Boundary recovery is then fully deterministic: candidate selected but claim lost → next candidate; claim won but Issue not created (crash) → any later dispatcher finds a claim ref with no matching Issue and, if the receipt's worker is not this worker, reports it as an orphan (reclaim requires an explicit `dispatch gc` run that *reports* orphans and deletes a claim ref only with `--force` and an age threshold — never automatic, per the non-mutation ethos); claim won by *this* worker with no Issue → idempotently continue to Issue creation; Issue created but lease not acquired → the ordinary resume path already handles an `agent_ready` Issue; `main` or the contract advancing mid-dispatch → contract-hash check at lease time already fails closed (`issue_workflow_store.py:428-431` **[fact]**) and the dispatcher re-runs selection; task completes → closeout deletes the claim ref as its final step, and a lingering claim ref for a `complete` Issue is GC-reportable.

## CLI semantics

**[rec]** `Start-GameTaskAgent.ps1` / `run_pipeline_agent.py`, keeping the normal command argument-free:

| Invocation / situation | Behavior | Exit |
|---|---|---|
| no args, validated agent-ready Issue exists | resume highest-priority (lane-ordered) Issue — unchanged pipeline after selection | 0 |
| no args, empty queue, eligible candidate | claim → initialize Issue → lease → checkout → run | 0 |
| no args, claim lost to concurrent worker | deterministically retry next eligible candidate (bounded, e.g. 5 attempts), then normal outcome codes | per outcome |
| `-TaskId NSC-###` | explicit override: skips priority *selection* only; the same eligibility predicate still runs for fresh work (safety is never bypassable), resume works as today | 0 / 5 |
| `-ResumeOnly` | today's exact behavior, retained for operators who want no fresh claims | 0 / 3 |
| zero policy-listed candidates and empty queue | "NO ELIGIBLE WORK" with per-task reason table | 3 |
| policy missing / `enabled: false` / hash-invalid | current denial message plus how to enable | 4 |
| candidates exist but all blocked by deps/resources/WIP/orphans | reason table naming each blocker | 5 |
| contract/store/Git error | unchanged | 2 |

Exit 0 stays "work progressed"; 3/4/5 are distinct quiet-stop conditions an operator or wrapper script can branch on; 2 stays "something is wrong."

## Exact module and schema changes

**[rec]**

- **New** `Pipeline/TaskGraph/DISPATCH_POLICY.yaml` — schema above.
- **New** `Pipeline/TaskGraph/dispatch_policy.py` — load/validate the policy (task IDs exist, are `active`, no duplicates across lanes, WIP limits positive ints); expose `policy_sha256` via the existing `semantic_json_sha256`.
- **New** `Pipeline/TaskGraph/dependency_readiness.py` — clause 3 of the predicate, built on `evaluate_current_conformance`; returns per-dependency findings.
- **Modify** `Pipeline/TaskGraph/execution_authority.py` — `assess_execution_authorization(task, *, policy, readiness, issue_snapshot, refs)` returns `authorized=True` only when the full predicate passes; keep `UnsafeExecutionAuthorizationError`, keep the current denial verbatim as the no-policy default, add reason codes (`policy_disabled`, `not_in_priority_lanes`, `dependency_not_conformant`, `wip_limit`, `resource_reserved`, `orphan_remote_state`, …).
- **Modify** `Pipeline/TaskGraph/taskcontrol.py` — implement `ready_tasks()` as the gated predicate; `command_ready` prints the lane-ordered eligible list plus the exclusion table; add `taskcontrol dispatch-plan --json` (read-only dry run) for the pre-enable rollout phase.
- **Modify** `Pipeline/TaskGraph/work_graph_validate.py` — validate `DISPATCH_POLICY.yaml` membership when the file exists.
- **New** `Pipeline/TaskReviewAgent/fresh_dispatch.py` — candidate enumeration at a fetched `origin/main` SHA, claim-commit construction, `git push` of `refs/nsc/claims/NSC-###`, loser detection, Issue initialization handoff, plus the `gc`/orphan-report entry point.
- **Modify** `Pipeline/TaskReviewAgent/generic_selection.py` — `select_work()`: resume-first (fix the empty `task_loader` stub to use committed contracts as `durable_selection._committed_task` does), fall through to `fresh_dispatch`; keep `select_agent_ready_task` for `-ResumeOnly`.
- **Modify** `Pipeline/TaskReviewAgent/run_pipeline_agent.py` and `Start-GameTaskAgent.ps1` — `--resume-only`, exit-code mapping, install `completed_issue_guard` on the selection path.
- **Modify** `Pipeline/TaskReviewAgent/issue_workflow_store.py` / `issue_workflow.py` — accept the new optional lease/init `details` keys (`claim_ref`, `claim_commit`, `policy_sha256`, `eligibility_evaluated_at`); event schema version can stay 1.0 since `details` is already an open object **[fact]** (`issue_workflow.py:129-140`).
- **Task contracts: no change.** Priority and WIP are operational state; schema v2 deliberately forbids operational fields (`FORBIDDEN_V2_OPERATIONAL_FIELDS` **[fact]**) and that boundary should hold — putting priority in contracts would churn contract hashes and trigger spurious `needs_replan`.

## Migration and rollout

**[rec]** Four phases, each independently revertible: (1) land all code with no policy file — behavior is byte-identical to today (deny-by-default, resume-only), proven by existing smoke tests; (2) land `DISPATCH_POLICY.yaml` with `enabled: false` — `taskcontrol dispatch-plan` becomes a reviewable dry run the human can compare against their own intent for a few days; (3) human PR flips `enabled: true` with `approved_by`/`approval_reference`, `max_agent_working: 1` — single-worker fresh dispatch in production; (4) raise to `max_agent_working: 2` only after the two-worker race suite (below) has run green against a real bare remote and one supervised real concurrent session. Rollback at any phase is a one-line policy revert; the code path degrades to the current denial, never to an intermediate state.

## Required tests

**[rec]** All deterministic, no live GitHub, following the existing smoke-test pattern (`MemoryIssueBackend` plus temporary local bare Git repos as remotes):

1. **Predicate unit table** — every clause independently falsified: coarse decomposition, non-single-agent scope, superseded dependency, `needs_testing` self-state, unlisted task, dirty worktree ⇒ fail-closed.
2. **Real two-worker race from an empty queue** (the brief's mandatory case): two `fresh_dispatch` workers against one bare remote and a shared `MemoryIssueBackend`, overlapping candidate lists; assert exactly one claim ref per task, distinct tasks assigned, zero duplicate Issues, zero split leases (event chains stay valid), and no exclusive-resource overlap between the two assignments. Run both orderings and a same-single-candidate variant (one worker must exit 3/5).
3. **Crash-at-every-boundary**: kill after claim push, after Issue create, after lease, after checkout; a fresh dispatcher run must resume or report the orphan deterministically, never double-claim.
4. **Orphan lifecycle**: stale claim ref with no Issue → task ineligible, `gc` reports it, `--force` reclaim restores eligibility; claim ref with closed COMPLETE Issue → GC-reportable, task never redispatched (extends `completed_issue_guard_smoke_test.py`).
5. **Mid-dispatch drift**: advance the bare remote's `main` and mutate the task contract between selection and claim; assert re-evaluation/fail-closed via the contract-hash check.
6. **Policy gating**: missing file, `enabled:false`, bad hash, duplicate lane entry, unknown task ID ⇒ exits 4/validation failure; priority order (not ID order) proven for both fresh selection and resume ordering.
7. **WIP limits**: saturate `max_human_action_required` and `max_agent_working` with fixture Issues; assert `blocked_wip_limit`, exit 5.
8. **Byte-identical phase-1 regression**: with no policy file present, existing `taskcontrol` and selection behavior unchanged.

## Unsafe shortcuts to reject

- **Labels or `gh issue edit` as a lock.** Both are last-write-wins reads-then-writes; the existing event chain only makes races fail closed, it does not elect a winner.
- **`not_delivered` ⇒ ready.** It says "no evidence," not "dependencies satisfied, decomposed, prioritized, and unclaimed."
- **Conformance ⇒ dependency readiness without the explicit policy clause.** The repo's own denial message warns against exactly this; keep the readiness rule as a named, versioned policy artifact.
- **Enabling every `active` contract.** 55 contracts include `coarse`, `not_applicable`, and `needs_execution_decomposition` scopes **[fact]**; a blanket enable dispatches undecomposed features.
- **Task-number order as priority.** It encodes reconciliation history, not product value; it must never survive as a hidden default beyond the declared final tie-break.
- **LLM ranking or selection.** Selection stays pure host code end to end; the model only executes the already-selected task.
- **A local file lock as the claim.** Correct for one machine today, silently wrong the day a second machine or cloud worker appears; the remote ref costs nothing more.
- **Auto-deleting or auto-reusing orphan branches, claim refs, or checkouts.** Report and require explicit human/GC action, consistent with the checkout-path convention's existing-checkout rule and the testing policy's "preserve, don't repair" stance.
- **Letting `-TaskId` bypass the eligibility predicate.** The override may skip priority *choice*, never dependency, resource, disposition, Issue-state, or WIP safety — otherwise the manual path remains the unguarded hole it is today.
- **A database or standing scheduler service.** The failure model (two-ish workers, one human, GitHub as the durable store) is fully served by one atomic ref push plus the existing Issue state machine.
