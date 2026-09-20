# Adversarial review: Decomposition-apply/D1C recovery and multi-resume scheduling

Read-only review of the NoSafeCircle TaskReviewAgent orchestration. No push, no Issue mutation, no
containers, no production-file edits. `C:\NSC\Rehearsal\*` and the dirty controller checkout
`C:\NSC\NSC\NoSafeCircle` were not touched.

## Reviewed commit

| Item | Value |
|---|---|
| **Reviewed commit** | `27d0732c46fc73fa5ee02ca13c632d186e3b7b53` — "Stabilize Windows claim contention fixture" |
| Branch | `origin/review/orchestration-gauntlet-followup` |
| Parent | `e0f05306bc6e328a909cd71651b9c5cda5365f84` — "Repair merged scheduler replay fixture" |
| Merge-base with `origin/main` | `983ba6a66efc4a9fdc3a02262b2344e153a40c1d` |
| Production-code note | `27d0732` changes only `tests/contention_retry_smoke_test.py`. Every production file for both review areas is **byte-identical to `e0f0530`**. All probes below were run at both commits with identical results. |
| Clean clone | `C:\nscrev\repo` (fresh `git clone` of origin, `core.longpaths=true`, detached at `27d0732`, clean tree). The first attempt in the deep scratchpad path failed on Windows "Filename too long"; the short root was used instead. |
| Parent worktrees | `C:\nscrev\wt-<sha>` for `f76d59d 399fbac ead605a 0cdabfe d93c1c5 10e0357 c91ffcb c7405dc e0f0530` (disposable, used only for failing-before checks) |
| Disposable probes | `C:\nscrev\probe\*.py`, `*.sh` (outside the repository) |
| Tooling | git 2.45.1.windows.1, Python 3.13.1 (CI uses 3.12) |

Commits on the branch that own the two review areas (all ancestors of `27d0732`):

| Commit | Subject | Relevance |
|---|---|---|
| `d93c1c5` | Make scheduler admissions coherent and capacity aware | multi-launch capacity pass |
| `c91ffcb` | Batch architect admissions in one provider call | one architect batch, ordered admissions |
| `c7405dc` | Harden worker outcomes and decomposition recovery | `decomposition_replay.py`, `worker_result.py`, D1C apply/retry, multi-resume plan |
| `399fbac` | Exclude unauthorized Issues from agent-ready discovery | discovery |
| `ead605a` | Recognize the bounded managed-Issue pending transition window | discovery |
| `0cdabfe` | Match the real agent-ready label shape and convergence | discovery |
| `e0f0530`, `27d0732` | fixture repairs (test-only) | — |

Read first, as instructed: `AGENTS.md`, `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`,
`Pipeline/TaskReviewAgent/README.md`, plus `Docs/AI-Pipeline/Stage5-Decomposition-Design/D1C_GRAPH_APPLICATION_DESIGN.md`
and `CONCURRENCY_AND_FAILURE_MODEL.md` for the stated recovery contract.

---

## Verdict in one paragraph

The multi-resume scheduling logic is sound: every validated agent-ready Issue (any phase) enters the same
single paid architect batch, each candidate/work-type pair receives an independent START/WAIT/HUMAN_REVIEW
disposition, `decomposition_apply` resumes are explicit in the architect payload and are re-derived from the
durable Issue by the launcher, and capacity/reservation/dedup accounting is correct. The D1C idempotency and
authorization binding are also sound: no path was found that creates a second D1C commit or publishes
unauthorized graph state. **Three defects were reproduced.** Two are in D1C *recovery* and are
rehearsal-halting under ordinary transport failure (a rejected push leaves the shared controller ahead of
`origin/main` and wedges the scheduler with no recovery tool; a hung git call escapes every handler and
strands the Issue lease). One is a scheduling liveness/cost defect (an unsafe first admission discards the
whole batch for one poll). **The branch is not safe for an unattended 10-agent rehearsal that exercises
`decomposition_apply` until D1 and D3 are fixed; it is safe for the scheduling behaviour itself.**

---

## Commands and results

### Baseline suites at `27d0732` (clean clone, same invocations as CI)

```
python Pipeline/TaskReviewAgent/tests/polling_orchestrator_smoke_test.py          PASS
python Pipeline/TaskReviewAgent/tests/host_decomposition_launcher_smoke_test.py   PASS
python Pipeline/TaskReviewAgent/tests/architect_preflight_smoke_test.py           PASS
python Pipeline/TaskReviewAgent/tests/execution_routing_smoke_test.py             PASS
python Pipeline/TaskReviewAgent/tests/resource_reservation_smoke_test.py          PASS
python Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py                PASS
python Pipeline/TaskReviewAgent/tests/dispatch_plan_smoke_test.py                 PASS
python Pipeline/TaskReviewAgent/tests/actor_authorization_smoke_test.py           PASS
python Pipeline/TaskReviewAgent/tests/committed_task_loader_smoke_test.py         PASS
python Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py             PASS
python Pipeline/TaskReviewAgent/tests/claim_refs_smoke_test.py                    PASS
python Pipeline/TaskGraph/graph_apply_smoke_test.py                               PASS
```

### Probe scripts (all no-network; real local Git repos with a local bare origin where Git is involved)

| Script | What it drives | Result |
|---|---|---|
| `probe_git_recovery.py` | `refresh_source_main` on a controller left one commit ahead of origin; `_exact_d1c_commit` under later unrelated commits, a same-subject decoy, wrong `authorized_head`, merged history | P1 **wedge reproduced**; P2/P3 exact-commit identification proven |
| `probe_apply_push_failure.py` | real `_apply_approved_plan` with a bare origin whose `pre-receive` hook rejects the push (A), and with a succeeding push but failing `complete_decomposition` (B) | A: **local D1C commit left on controller**, `RuntimeError`, controller now "diverged"; B: `DecompositionApplyRetryableError`, D1C on origin, as designed |
| `probe_retry_and_authority.py` | retry after a successful push (0 and 3 later unrelated main commits); 12 durable-authorization tamper/ordering cases against `inspect_authorized_decomposition_replay` | retry completes with rc 0, **no new commit**, exact D1C commit recorded; all tamper cases refused |
| `probe_retry_after_failed_push.py` | retry while the controller is ahead after a failed push | rc 3, lease released with **wrong diagnosis** and `retry_phase=None` (approval discarded) |
| `probe_push_timeout.py`, `probe_main_timeout.py` | `_git` raising `subprocess.TimeoutExpired` (a hung push) inside `_apply_approved_plan`, then through `main()` using the repo test's own scaffolding | **uncaught**: no `run_result.json`, no lease release |
| `probe_scheduler.py` | real `PollingOrchestrator.poll_once` with the repo's `FakeArchitect`/fixtures: unsafe first vs last admission; independent verdicts; two `decomposition_apply` resumes in one batch | **batch discarded** when the first admission is unsafe; independence and dual-apply proven |
| `regress_sweep.sh`, `isolated_parent_check.py`, `iso_run.sh` | child test files / individual test functions against parent production trees | see "Test quality" |

---

## CONFIRMED (reproduced) defects

### D1 — A locally created D1C commit whose push genuinely fails leaves the shared controller ahead of `origin/main`; the scheduler wedges and there is no recovery path

**Severity: High** (availability; fail-closed but rehearsal-halting; contradicts the design document; no tool
or runbook covers the resulting state).

**Where.** `Pipeline/TaskReviewAgent/host_decomposition_launcher.py:681-690` (push block inside
`_apply_approved_plan`) and `Pipeline/TaskReviewAgent/polling_orchestrator.py:495-547` (`refresh_source_main`).

**Mechanism.** D1C commits directly on the controller's attached `main` (`main()` requires branch `main` and a
clean tree; `build_decomposition_worker_command` passes the scheduler's own `--source`). On push failure the
code re-observes `origin/main` and, if it did not accept the commit, re-raises. Nothing rolls the local commit
back. `refresh_source_main` then runs `merge-base --is-ancestor <local HEAD> origin/main` (`:525`), which is
false for a controller that is merely *ahead*, and raises "diverged … refusing rewrite". `poll_once` counts
that as a source-refresh failure and goes fatal at `DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES = 3`
(`:133`, `:2045`), i.e. after three polls (~3 minutes at `DEFAULT_POLL_SECONDS = 60`).
`reset_task.py --undo-decomposition` cannot help: it requires the D1C commit to be **both** HEAD and
`origin/main` (its own docstring). Even a manually launched retry (`probe_retry_after_failed_push.py`)
returns 3 and releases the lease with `"origin/main moved after authorization … a fresh D1B.2 proposal is
required"` and `retry_phase=None` — a wrong diagnosis (origin did not move; the local controller did) that
throws away a still-valid human approval and demands a paid D1B.2 rerun.

**Reproduction** (`probe_apply_push_failure.py` scenario A, `probe_git_recovery.py` P1):

```
=== A: genuine push rejection (remote never accepts) ===
  raised: RuntimeError: git push origin 3b1c18eb…:refs/heads/main failed: … [remote rejected] (pre-receive hook declined)
  local_head: 3b1c18eb          <- unpushed D1C commit remains on controller main
  origin_main: 63e79dff         <- still the authorized head
  completions: []
  refresh_source_main: IntegrationObservationError: scheduler controller main diverged from origin/main; refusing rewrite

retry rc: 3
lease release reason: origin/main moved after authorization (authorized=1ab0b417…, remote=8c8b0da1…); a fresh D1B.2 proposal is required.
retry_phase: None   (Issue returns to fresh-DECOMPOSITION phase; approval discarded)
```

**Design contract it violates.** `D1C_GRAPH_APPLICATION_DESIGN.md:306-320` ("Commit succeeds, push fails … If
the push failed for a purely transient reason and `main` did not advance, retrying the identical push is safe
under the same authorization … discard the local commit and report `stale_proposal`") and
`CONCURRENCY_AND_FAILURE_MODEL.md:183-189` ("Proving test: simulate push failure against a fake remote; assert
restart produces an equivalent … result"). No such test exists (`grep push|TimeoutExpired` in
`host_decomposition_launcher_smoke_test.py` → no hits). The runbook only says "A dirty or diverged controller
stops admissions without reset or overwrite"; nothing tells an operator how to recover.

**Smallest recommended fix.** In the push-failure handler of `_apply_approved_plan`, after confirming
`origin/main != applied_commit`, roll the controller back to `source_head` before re-raising, and release the
lease with `retry_phase=WorkflowPhase.DECOMPOSITION_APPLY` so the still-valid approval is retried instead of
discarded. `Pipeline/TaskGraph/apply_graph_delta.py:1120` already has the exact guarded primitive
(`_rollback_failed_commit(root, old_head, failed_commit)`: refuses unless HEAD is the failed commit and the
tree is clean, then `reset --hard old_head` and re-verifies) — the "strictly local and strictly pre-push"
reset the design explicitly permits. Export it (or a thin public wrapper) and call it here. Add the proving
test the design called for (bare origin with a rejecting `pre-receive`; assert controller HEAD == origin/main
== authorized head afterwards and that a retry applies once). Secondary: make `refresh_source_main` say
"ahead of origin/main by N commits" rather than "diverged", so the operator can distinguish this state.

### D2 — A deterministically unsafe **first** admission discards every later admitted candidate in the batch, including other ready resumes

**Severity: Medium-Low** (liveness/cost; self-heals on the next poll via the cached WAIT; costs one poll
interval and one extra paid architect call each time; contradicts the README's "without hiding fresh
implementation or decomposition work from the same architect call").

**Where.** `polling_orchestrator.py:2499-2570`, the "validate the complete ordered prefix" loop: on
`conflict / unknown surface / unconfirmed / gate != start` it records the gate, emits
`architect_batch_truncated` and **`break`s** (`:2569`). The later per-launch revalidation loop uses
`continue` for the same class of withdrawal (`architect_batch_candidate_withdrawn`), which is the documented
behaviour ("A withdrawn candidate is skipped"). Because `planned_reservations` only accumulates *admitted*
candidates, skipping an unsafe one can never make a later candidate less safe, so `break` buys no safety.

**Reproduction** (`probe_scheduler.py`; resume A repair, resume B `decomposition_apply`, fresh C, all admitted by
the architect, one active reservation overlapping exactly one of them, `max_workers=3`):

```
conflicting candidate: C (ordered LAST)     poll1_launched: ['NSC-101','NSC-102']  truncated: True  architect_calls: 1
conflicting candidate: A (ordered FIRST)    poll1_launched: []                     truncated: True  poll2: worker_launched  cumulative: ['NSC-102','NSC-103']  architect_calls: 2
```

With the conflict on the first admission, a conflict-free `decomposition_apply` resume and a conflict-free
fresh task both wait a full poll and a second paid architect call. The existing test
`test_conflicting_batch_truncates_before_second_launch` pins only the second-conflicts case.

**Smallest recommended fix.** `polling_orchestrator.py:2569`: replace `break` with `continue` (the gate
record and `temporary_exclusions.add` already happened) and emit `architect_batch_candidate_withdrawn`
instead of `architect_batch_truncated`. `test_conflicting_batch_truncates_before_second_launch` still passes
(B conflicts with A's planned reservation, A launches, planner called twice); add the first-conflicts case.

### D3 — A hung git call during D1C apply (`subprocess.TimeoutExpired`) escapes every handler: no `run_result.json`, no lease release, worker dies with a traceback

**Severity: Medium-High** (Issue stranded in `agent_working` under a dead `worker_id`, requiring manual lease
repair; scheduler goes fatal on the missing artifact; reachable by any 180 s stall on push **or fetch** — the
most realistic form of "genuinely failed push").

**Where.** `host_decomposition_launcher.py:119-133` (`_git` runs `subprocess.run(..., timeout=180.0)`, which
raises `subprocess.TimeoutExpired`, a `SubprocessError`, not an `OSError`/`RuntimeError`);
`:734` and `main()`'s handler (`except (DurableCheckoutError, KeyError, OSError, RuntimeError, TypeError,
ValueError)`) do not include it.

**Reproduction** (`probe_main_timeout.py`, which drives real `main()` with the same patch scaffolding as
`test_apply_resume_uses_historical_contract_and_skips_fresh_validation`):

```
RuntimeError (push rejected)      main(): returned 2      run_result.json written: True    lease released: True
TimeoutExpired (push hung 180s)   main(): UNCAUGHT TimeoutExpired (process exits 1 with traceback)
                                                          run_result.json written: False   lease released: False
```

The scheduler then reports `worker_failed: worker terminal artifact was missing or invalid` (fatal drain), and
the next worker sees `blocked_kind=durable_ownership_by_other`. If the hung push actually landed remotely,
the D1C commit is on `origin/main` and the Issue can never be completed without manual lease repair.

**Smallest recommended fix.** In `_git` (`:119`), catch `subprocess.TimeoutExpired` and re-raise as
`RuntimeError(f"git {' '.join(args)} timed out after 180s")`. That routes the failure through the existing
push-failure re-observation, lease release (`retry_phase=DECOMPOSITION_APPLY`) and `run_result.json` writer.
(Adding `subprocess.SubprocessError` to both `except` tuples is equivalent but touches more lines.) Add a test
that patches `_git` to raise `TimeoutExpired` and asserts exit 2/3, artifact present, lease released.

---

## Theoretical concerns (not reproduced as failures; design trade-offs or gaps worth knowing)

| # | Concern | Evidence / status |
|---|---|---|
| T1 | **Any** unrelated main commit between handoff (`head_commit` recorded at proposal time) and apply invalidates the approval: `_apply_approved_plan` requires `source_head == authorized_head` unless already applied, *and* `origin/main == source_head`. In a 10-agent rehearsal main moves constantly, so `decomposition_apply` may rarely succeed on first attempt and each miss costs a paid D1B.2 rerun plus a new human approval. | Pre-existing (parent `f76d59d` had the same rule, and returned 0 instead of 3); the branch *adds* the `already_applied` escape. Design doc §"Recovery" mandates this strictness because `source_graph_semantic_hash` is whole-graph. Not a defect; a throughput risk to plan for. |
| T2 | One invalid managed Issue (`list_agent_ready` raises at `issue_workflow_store.py:2196`) blocks the whole poll → `blocked_invalid_state` → fatal. | Documented fail-closed policy in `AGENTS.md`. Under 10 agents the blast radius is the whole scheduler. Not a defect. |
| T3 | "Resume first" ordering is cosmetic for the real architect: `_mixed_portfolio` sorts by task id (`:1918`), `poll_once` re-prepends resumes (`:2331`), but `architect_preflight._portfolio_candidates` re-sorts by task id (`:1010`) before building the prompt, and launch order follows the architect's `admissions` order. | The functional property (all pairs in one batch, independent dispositions) holds regardless; README wording ("appears first") overstates it. `resume_priority_applied` also reports only the first resume and hard-codes `deferred_fresh_candidate_count=0`. |
| T4 | `_exact_d1c_commit` fails closed in *merged* history with two same-subject children of `authorized_head` (probe P3). | Main is fast-forward-only, so unreachable in practice; fail-closed is the right default. |
| T5 | Handoffs without `graph_delta_sha256` are still accepted when the head has not moved (`decomposition_replay.py:133`). | Not exploitable: `plan_id` is a SHA-256 over the full decomposition result + source-graph hash + parent identity, and `plan_graph_apply` recomputes the plan and requires canonical-JSON equality (`graph_apply_plan.py:293-335`, covered by `verify_stale_and_recompute_mismatch`). The current proposal path always writes the hash. |
| T6 | Commit `0cdabfe` was pushed with a red core suite: its own `polling_orchestrator_smoke_test.py` fails at `0cdabfe` (`AttributeError: 'SimpleNamespace' object has no attribute 'pending_transition'`); `e0f0530` repaired the fixture. | Process observation, not a production defect. |

---

## Disproved suspicions (with evidence)

| Suspicion | Result | Evidence |
|---|---|---|
| A retry can apply the same graph delta twice / create a second D1C commit | **Disproved** | `graph_apply_smoke_test.py:365-390` (pre-existing): second `apply_graph_delta` → `already_applied`, `new_commit_sha is None`, commit count unchanged, `plan_graph_apply` never reached. `probe_retry_and_authority.py`: launcher retry after a successful push → rc 0, `commits_after` == base + D1C (+ unrelated), no push, completion records the exact D1C commit. |
| Issue-completion failure after a successful push does not resume safely | **Disproved** | Scenario B: `DecompositionApplyRetryableError`, D1C on `origin/main`, lease released to `DECOMPOSITION_APPLY` (`main():1058-1066`), exit 3 → `worker_blocked` (not fatal), Issue back to `agent_ready` with next action "Retry the exact approved graph application" (`issue_workflow_store.py:2044`); the retry completes (above). `_release_owned_decomposition_lease` only releases a lease this exact worker still owns. |
| Later unrelated main commits obscure the exact D1C commit | **Disproved** | Probe P2: found under 3 later commits; a later decoy commit with the identical subject is rejected because the parent must equal `authorized_head`; wrong `authorized_head` → `RuntimeError`. |
| Artifact tampering / missing hash / wrong plan id / stale authorization can publish unauthorized graph state | **Disproved** | 12-case authority probe: hash mismatch, approval naming another plan, approval without preceding handoff, handoff recorded after approval, missing hash + moved head, malformed plan id, artifact plan id ≠ handoff, unreadable artifact — all refused. Missing hash + unmoved head falls through to recomputation (T5). Stale authorization (head moved, plan not applied) → lease released, return 3 (`test_stale_authorized_plan_releases_to_fresh_decomposition`). |
| Partial graph application is reported as applied | **Disproved** | `_inspect_replay` requires every child's provenance/parent/reconciliation key/id-map binding and every inbound rewrite; otherwise `stale_or_partial` (`apply_graph_delta.py:566-720`; `verify_incomplete_replays_never_report_success`). |
| Main moving during publication can publish on a wrong base | **Disproved** | Both checks (`source_head == authorized_head` unless already applied; `origin/main == source_head` after fetch) run before the global claim; `apply_graph_delta(expected_head=source_head)` fences again; push is exact-SHA to `refs/heads/main` without force, and non-fast-forward rejection is handled as a push failure (→ D1 territory, but never a wrong-base publish). |
| Post-apply resume lease fails because the parent contract hash changed at HEAD | **Disproved** | `acquire_agent_lease(expected_workflow_contract_sha256=…)` overrides the current-HEAD hash only for `DECOMPOSITION_APPLY` (`issue_workflow_store.py:1279-1295`); the reservation observer accepts a changed parent contract only with an `already_applied` replay proof (`polling_orchestrator.py:706-733`). |
| The reservation observer rejects a normal pre-apply `decomposition_apply` Issue | **Disproved** | The replay check runs only when the committed contract hash differs from the Issue's; before D1C they are equal. |
| Not all ready Issues enter the same architect batch | **Disproved** | `build_poll_dispatch_plan` (`:963-1027`) makes `agent_ready[0]` the `resume` and prepends every other ready Issue as `additional_resumes` (with `resume_phase`) to `ranked_eligible_candidates`; `_ordered_candidates` + `_mixed_portfolio` carry all of them; `_portfolio_candidates` + batch validation require a disposition for every pair (`architect_preflight.py:1336`) and reject duplicate admissions (`:631`) and over-limit batches (`:1341`). Probe: three ready Issues → one `portfolio_calls` entry containing all three. |
| The lowest-numbered Issue receiving WAIT hides later ready Issues | **Disproved for architect WAIT** (see D2 for the deterministic-gate variant) | `test_first_resume_wait_does_not_hide_later_decomposition_apply_resume` (fails at parent `f76d59d` with a real assertion — see below); probe: HUMAN_REVIEW on 101, WAIT on 103, START on 102 from one call, 102 launched via `host_decomposition_launcher.py`. |
| `decomposition_apply` resumes can be mistaken for new decomposition work | **Disproved** | `_mixed_portfolio` restricts them to `["decomposition"]` and stamps `resume_phase`; `_portfolio_candidates` validates and forwards it; the prompt carries an explicit rule (`architect_preflight.py:1050`); the launcher re-reads the durable phase and takes the apply branch regardless of the architect (`main():935-950`); `test_approved_decomposition_resume_cannot_route_to_implementation`. |
| Capacity, dedup, reservations, fairness | **Sound** | `admission_limit = min(max_workers − active, 1000)`; launch loop stops at capacity; `_reap_workers` frees blocked/idle slots without fatal; `by_id`/`seen`/`considered` dedupe; `_integration_reservations` merges active assignments (architect-predicted surfaces) with durable reservations so a just-launched sibling is visible to the next launch; fresh candidates already ready are removed from the fresh list; per-launch re-plan/re-observe. |

---

## Area-by-area answers

### 1. Decomposition-apply / D1C recovery

- **Retries cannot apply the same graph delta twice** — proven (idempotent `already_applied`, plus the global
  `logical:taskgraph-decomposition-apply` claim serialising concurrent parents).
- **Issue-completion failure after a successful push resumes safely** — proven end-to-end (retryable error →
  lease released to `decomposition_apply` → next worker completes with the exact commit, no push).
- **Later unrelated main commits do not obscure the D1C commit** — proven, including a same-subject decoy.
- **Tampering / missing hashes / wrong plan IDs / stale authorization / partial application / main moving** —
  all refused; no unauthorized publication path found.
- **Local D1C commit + genuinely failed push** — **no safe recovery path** (D1); a *hung* push is worse (D3).
- **Any path creating a second D1C commit or publishing unauthorized graph state** — none found.

### 2. Multiple agent-ready resume scheduling

- **All ready Issues enter the same architect batch** — proven.
- **Lowest-numbered WAIT does not hide later ready Issues** — proven for architect WAIT/HUMAN_REVIEW; **not**
  true when the first *admitted* candidate fails the deterministic gate (D2).
- **`decomposition_apply` resumes are explicit and cannot be mistaken for new decomposition** — proven.
- **Ordering, capacity, dedup, reservations, fairness** — sound (T3 on ordering wording).
- **Architect can independently START / WAIT / HUMAN_REVIEW each resume candidate** — proven.

---

## Test quality: failing-before / passing-after evidence

Method: each child commit's test file was run against its parent's production tree (`regress_sweep.sh`),
then key test *functions* were run in isolation with only the child-only `worker_result` import stubbed
(`isolated_parent_check.py`), so a failure reflects behaviour rather than a missing symbol.

| Child → parent | Test | At parent | Quality |
|---|---|---|---|
| `c7405dc → f76d59d` | `test_first_resume_wait_does_not_hide_later_decomposition_apply_resume` | **FAIL (assertion)**: parent offered NSC-102 as `['decomposition','implementation']` — the `decomposition_apply` resume was not restricted | genuine regression proof |
| `c7405dc → f76d59d` | `test_production_poll_plan_batches_every_ready_resume_before_fresh_work` | **FAIL (assertion)**: parent plan lacked the additional resumes | genuine |
| `c7405dc → f76d59d` | `test_decomposition_apply_hash_change_requires_exact_replay` | FAIL (`AttributeError`, new symbol) | weak — cannot distinguish behaviour from absence |
| `c7405dc → f76d59d` | launcher tests `test_stale_authorized_plan…`, `test_apply_artifact_error…`, `test_apply_resume_uses_historical_contract…`, `test_scheduler_decomposition_run_writes…` | FAIL (`AttributeError` on `inspect_authorized_decomposition_replay`; argparse error on `--scheduler-output-root`) | weak (feature absent at parent) |
| `c7405dc → f76d59d` | `test_safe_resume_is_selected_before_fresh_start`, `test_resume_wait_does_not_starve_stage2_ranked_fresh_work`, `test_capacity_batch_uses_per_poll_budget_to_fill_slots`, `test_batch_candidate_withdrawal_does_not_starve_later_admission`, `test_approved_decomposition_resume_cannot_route_to_implementation`, `test_conflicting_batch_truncates_before_second_launch` | **PASS at parent** | regression guards only; they prove nothing new about `c7405dc` (behaviour introduced by `d93c1c5`/`c91ffcb`) |
| `d93c1c5 → 10e0357` | `test_safe_resume_is_selected_before_fresh_start` | **FAIL (assertion)** | genuine |
| `d93c1c5 → 10e0357` | `test_capacity_batch_uses_per_poll_budget_to_fill_slots`, `test_resume_wait_does_not_starve…` | FAIL (`poll_capacity_batch` missing) | weak |
| `c91ffcb → d93c1c5` | whole batch-API test set | import-blocked (`ARCHITECT_BATCH_SCHEMA*` absent) | cannot be expressed against the parent; the feature is new |
| `0cdabfe → ead605a` | `test_pending_issue_does_not_reject_disjoint_fresh_candidate`, `test_pending_issue_still_reserves_its_exclusive_resource` | **FAIL (assertion)**: parent rejected all fresh work / stopped reserving | genuine |
| `0cdabfe → ead605a` | `polling_orchestrator_smoke_test.py` (whole file) | FAIL — but the *same file fails at `0cdabfe` itself* (fixture missing `pending_transition`) | T6: red at its own commit |
| `399fbac → c7405dc` | `actor_authorization_smoke_test.py` | **FAIL (`IssueWorkflowStoreError`: unauthorized Issue halted discovery)** | genuine |
| `ead605a → 399fbac` | pending-transition tests | import-blocked (`PENDING_TRANSITION_MAX_AGE_SECONDS`) | weak |
| `e0f0530 → 0cdabfe`, `27d0732 → e0f0530` | fixture repairs | PASS at parent | expected; not regression tests |

**Tests that can pass without exercising the production path / coverage gaps found**

- No test names `_exact_d1c_commit`; the only coverage is transitive through my probes.
- No launcher test simulates a failed or hung push (`grep push|TimeoutExpired` → none), despite the design
  document naming that proving test. D1 and D3 would both have been caught by it.
- `DecompositionApplyRetryableError` is tested only by injecting it as `_apply_approved_plan`'s side effect
  (`host_decomposition_launcher_smoke_test.py:739`); the path that *raises* it (completion failure after a
  verified push) is exercised only by `probe_apply_push_failure.py` scenario B.
- `refresh_source_main` has tests for fast-forward and dirty controller but none for "ahead of origin".
- `test_apply_artifact_error_releases_global_claim` and `test_stale_authorized_plan…` replace
  `inspect_authorized_decomposition_replay` and `_git` wholesale; they verify claim/lease bookkeeping, not
  authority. The authority itself is covered by `decomposition_replay`'s callers only via
  `graph_apply_smoke_test.verify_read_only_exact_replay_inspection` (genuinely new at `c7405dc`; fails at the
  parent on `ImportError`).
- `test_scheduler_decomposition_run_writes_identity_bound_terminal_result` and the `worker_result` suite are
  thorough on artifact identity; they cannot detect D3 because the launcher never reaches `write_worker_result`.

---

## Is the branch safe for the 10-agent rehearsal?

- **Scheduling (area 2): yes.** Multi-resume batching, independent verdicts, capacity, reservations and
  dedup are correct and fail closed. D2 lowers throughput and adds paid architect calls under contention but
  cannot launch unsafe work or lose state.
- **D1C apply/recovery (area 1): not unattended.** Idempotency and authorization are solid, but ordinary
  transport failure produces states the system cannot leave on its own: a rejected push wedges the scheduler
  within three polls with no recovery tool and no runbook entry (D1); a hung git call strands the lease and
  kills the scheduler (D3). Both are two-to-ten-line fixes with existing primitives. Until they land, run the
  rehearsal either without `decomposition_apply` work, or with an operator ready to (a) `git reset --hard
  origin/main` the controller (safe: the approval is still valid on origin and a retry applies once) and
  (b) repair a stranded `agent_working` lease by hand. Expect T1 to force D1B.2 reruns whenever main moves
  between approval and apply.

No commit was authored. Probe files and parent worktrees under `C:\nscrev\` are disposable.
