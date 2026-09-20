# Atomic expected-main publication fencing and versioned lease/operation identity (F1, F6)

Corrective implementation for the independent public integration-gate audit findings **F1**
(publication lacks an atomic expected-main check) and **F6** (the integration lease omits
source-commit and expected-main identities). No other audit finding was implemented.

---

## 1. Exact identities

| Item | Value |
| --- | --- |
| Frozen source (read-only, never modified) | `C:\NSC\PublicPipelineIntegration-Astra-20260907` |
| Source branch | `integration/production-orchestration-bb560d0e` |
| **Starting SHA (required base)** | `837eb4f0fa0ba8d619bbb78b500e73ccfd229792` |
| Isolated clone | `C:\NSC\ClaudePublicationFence-20260907\NoSafeCircle` |
| Local branch | `claude/fix-atomic-publication-fence` |
| **Final SHA** | `8fb844ca524313709bcaaa0c1c07d35ceb7814ea` |
| Pristine base checkout for red evidence | `C:\NSC\ClaudePublicationFence-20260907\BaseRed837eb4f` (detached at `837eb4f…`) |
| External evidence directory | `C:\NSC\ClaudePublicationFence-20260907\evidence` |

The source checkout was verified clean at `837eb4f…` before work began and was never written to.
The isolated clone was created with `git -c core.longpaths=true clone --no-hardlinks`. No global
`safe.directory` exception was added; identity was configured with `git config --local`.

**Note on the audit's own base.** The audit report was produced against `eb3353fc76630ebcfcdaa73626ef78b7b0c8273e`.
`git merge-base --is-ancestor eb3353f… 837eb4f…` exits 0, and the only commit between them is
`837eb4f Add read-only lifecycle navigation with public-isolated viewer defaults`, which the audit
itself recorded as touching visualizer, documentation and CI/test paths only. Both F1 and F6 were
independently reproduced at the required base `837eb4f…` (§7).

---

## 2. Root cause

`DownstreamTaskController.inspect_or_merge_pull_request` (`downstream_pipeline.py:1081-1153` at base)
ran the fresh mainline guard and then published:

```python
mainline_guard = getattr(self, "guard_current_main_before_pull_request_merge", None)
if callable(mainline_guard):
    guarded_result = mainline_guard()          # proves current main ⊆ approved task head
    if guarded_result is not None:
        return guarded_result
command = ("gh", "pr", "merge", str(number), "--repo", self._bound_repository(),
           "--merge", "--match-head-commit", self.state["evidence_commit"])
_run(self.command_runner, command, cwd=self.checkout, timeout_seconds=900.0)
```

Three facts combine into the defect:

1. `_fresh_mainline_status_before_merge` (`mainline_reintegration.py:828-901`) resolves `origin/main`
   into `main_head`, proves `main_head` is an ancestor of the task head, and then **discards
   `main_head`** — it survives only on `self._mainline_reintegration_status`.
2. `--match-head-commit` pins the *pull-request head*. GitHub's merge API has no expected-base
   parameter, so the exact base identity could not be expressed even if it had been carried.
3. The gate's compare-and-swap (`integration_gate.compare_and_swap`) fences
   `refs/nsc/claims/integration-gates/<domain>` — the gate's own journal ref — not `refs/heads/main`.
   It cannot observe, let alone reject, a competing writer on the target branch.

An external writer advancing `main` between step 1 and step 3 therefore had its change merged into
main together with an approved head that never contained it, and the controller recorded
`status=merged`.

A second read before the merge does not close this: any read-then-write leaves the same window. The
defect is the absence of an old-value predicate in the mutation itself.

---

## 3. Chosen atomic primitive

### The transaction

```
git -C <checkout> push --atomic --porcelain \
    --force-with-lease=refs/heads/<target>:<expected_main> \
    origin <approved_candidate>:refs/heads/<target>
```

`--force-with-lease=<ref>:<exact-oid>` places the expected old value **in the push request itself**.
`receive-pack` applies the update only when the ref is exactly that value, in one atomic ref
transaction; every other value is refused with the branch untouched. This is a genuine
server-enforced compare-and-swap on the authoritative ref, not a read-then-write.

### Why the lease is safe here (no rewind is possible)

The lease flag would otherwise permit a non-fast-forward update. `prove_publishable_candidate`
refuses to issue the transaction unless `expected_main` is proven an ancestor of the published
candidate, so the update can only *append* to the target branch. The lease is used **only** in its
exact-value form against the target branch. Bare `--force-with-lease`, `--force`,
`--force-if-includes`, inferred leases, fallback force pushes, `reset`, history rewrites and
re-leasing against a newly observed base after a rejection are all absent and regression-guarded
(`test_only_an_exact_lease_is_used_and_no_rewind_is_possible`).

### Why fast-forward alone was insufficient

A plain non-force push rejects any base movement that introduces content outside the approved head,
but it *accepts* a base already contained in the candidate — measured directly:

| Case | plain FF push | exact lease |
| --- | --- | --- |
| main moved to a disjoint commit | `[rejected] (fetch first)`, unchanged | `[rejected] (stale info)`, unchanged |
| main moved to a conflicting commit | `[rejected] (fetch first)`, unchanged | `[rejected] (stale info)`, unchanged |
| main moved *inside* the candidate's own ancestry | **accepted** | `[rejected] (stale info)`, unchanged |
| main exactly at `expected_main` | accepted | accepted |
| replay of an applied update | `[up to date]` | `[up to date]` |

Only the exact lease is a true expected-OID compare-and-swap. Measurements are in §7.4.

### What is published

The published commit is the **approved candidate itself** — the pull-request head — not a freshly
synthesized merge commit. This matters for the required-check contract: the delivery workflows check
out `github.event.pull_request.head.sha` explicitly, so the candidate head *is* the commit the checks
evaluated. Publishing a newly built merge commit would publish a topology no check ever saw.

Since the mainline guard proves `expected_main` is an ancestor of the candidate, advancing the target
branch to the candidate is a fast-forward: append-only history is preserved and no merge commit is
required.

### Which SHA the required checks actually validated

This was verified against the committed workflows rather than assumed:

| Workflow | `actions/checkout` ref | Validated commit |
| --- | --- | --- |
| `task-review-agent-deterministic.yml:46` | `${{ github.event.pull_request.head.sha \|\| github.sha }}` | candidate head |
| `task-review-agent-delivery.yml:64` | same | candidate head |
| `pull-request-check-authority-deterministic.yml:25` | same | candidate head |
| `d1b2-core-deterministic.yml:33` | same | candidate head |
| `history-migration-smoke.yml:26` | same | candidate head |
| `checkout-root-policy.yml:17-19` | *(default — no `ref:`)* | `refs/pull/N/merge` |
| `history-identity-migration-dry-run.yml:29-31` | *(default)* | `refs/pull/N/merge` |

The five load-bearing delivery/validation workflows override `actions/checkout`'s default merge-ref
behaviour and validate the candidate head itself. For the two that do not, the synthetic ref is
`merge(base_at_run, head)`; because the mainline guard proves the base is an ancestor of the
candidate, that merge is trivial and its tree equals the candidate's tree, and the fence rejects
publication if the base moved after that proof.

The implementation does not rely on this being true in general. `_accepted_validation_commit`
inspects the pull request's own rollup and **refuses publication when any reported check names a
commit other than the candidate**, so a rollup describing a merge ref (or any other topology) blocks
the transaction rather than being assumed equivalent
(`test_publication_refuses_checks_accepted_for_another_commit`,
`test_publication_requires_a_check_that_names_its_commit`).

Two distinct validations cover a delivery and only one covers the published commit:

* the human/automated Unity authority is accepted for the **implementation** commit, and the existing
  reader `_verified_evidence_head_for_integration` proves the evidence head descends from it;
* the required GitHub checks are accepted for the **pull-request head**, which is what is published.

An earlier revision of this change bound `validated_commit` to the Unity authority's
`tested_commit`. That is the implementation commit, not the evidence head, and it blocked the
automated delivery lifecycle — caught by `gate_resume_smoke_test.test_automatic_evidence_full_lifecycle_reuses_recorded_route`
before commit. The binding was corrected to the check evidence.

### `gh pr merge` is no longer on the publication path

The pull request remains the review/CI vehicle. After a proven transaction the controller verifies
the remote target equals the intended commit, then reconciles PR/Issue state. If GitHub reports the
PR merged with a *different* merge commit than this run published, publication fails closed for
reconciliation. There is no fallback to `gh pr merge`.

---

## 4. Versioned lease / operation schema

### Gate owner record (`integration_gate.py`)

Two shapes are accepted by `validate()` so durable history stays readable; only one carries authority.

```
LEGACY_OWNER_KEYS (13)  task_id, run_id, worker_id, lease_id, repository, target_branch,
                        acquired_at, heartbeat_at, progress, status, operation,
                        unity_seconds, ci_seconds
OWNER_KEYS (15)         LEGACY_OWNER_KEYS + protocol_version + publication
```

### Owner-bound publication operation (`owner["publication"]`, 17 keys, closed schema)

| Field | Meaning |
| --- | --- |
| `protocol_version` | `"2.0"` — the versioned publication contract |
| `repository`, `target_branch` | domain identity, re-checked against the gate's own domain |
| `task_id`, `run_id`, `worker_id`, `lease_id` | owner identity; must equal the owner's |
| `source_head` | the approved candidate that will become the target-branch commit |
| `validated_commit` | the exact SHA the required checks were accepted for |
| `expected_main` | the exact expected target-branch commit |
| `operation_id` | random 32-hex operation identity |
| `base_epoch` | monotonically increasing; a new base means a new epoch |
| `status` | typed `PublicationStatus` |
| `publication_commit` | the exact commit proposed/published |
| `observed_pre_image` | the value the transaction actually swapped from |
| `observed_target` | the target branch read back after the transaction |
| `detail` | bounded diagnostic text |

`validated_commit != source_head` is rejected at both the gate and the binding: an untested topology
can never be published.

### Where identities are validated

`GitIntegrationGate.require_owner(state, identity, *, source_head=None, expected_main=None)` is the
single centralised check. It refuses a legacy owner and delegates to `require_publication_identity`,
so a same task/run/worker presenting a different candidate or base never inherits the previous
authority. Exact call sites:

| Point | Where |
| --- | --- |
| fresh acquisition | `acquire()` constructs the 15-key owner (`integration_gate.py:340`) |
| same-owner resume | `acquire()` `:305`; `IntegrationWindow.checkpoint` `:114`, `:119` |
| renewal | `progress()` `:475` |
| publication binding | `bind_publication()` `:393` |
| publication outcome | `record_publication()` `:444` |
| every guarded controller mutation | `guard_controller_mutations` `:38` |
| completion / release | `release()` `:497`, then `_require_receipt(..., publication=…)` `:505` |
| quarantine | `quarantine()` `:571` |

**Recovery is the deliberate exception.** `recover()` does not call `require_owner` — a legacy or
quarantined owner must remain recoverable, and refusing it there would brick the reconciliation path
the contract requires. It validates instead through `_require_receipt(owner, receipt, publication=…)`
(`:591`) plus an explicit check that the receipt names the exact prior operation it reconciled.

### Settlement and recovery receipts

`RECEIPT_PUBLICATION_KEYS` are mandatory on any settlement that follows a real mutation, and each is
compared to the durable operation:

```
publication_operation_id, publication_status, publication_expected_main,
publication_source_head, publication_validated_commit, publication_commit,
publication_observed_main, publication_base_epoch
```

A completion additionally requires `verified_main == publication_commit`. A receipt naming a
publication the owner never performed is refused
(`test_settlement_cannot_claim_a_publication_that_never_happened`). Recovery must name the exact
prior operation it reconciled.

---

## 5. State transitions

### Publication operation

| From | Event | To | Target branch |
| --- | --- | --- | --- |
| *(absent)* | `gate_publication_bound` | `prepared` | unchanged |
| `prepared` | candidate proven publishable, record persisted | `attempting` | unchanged |
| `attempting` | porcelain ` ` with pre-image `== expected_main` | `published` | **advanced to candidate** |
| `attempting` | porcelain `=` `[up to date]` | `published` (idempotent replay) | already at candidate |
| `attempting` | porcelain ` ` with a different pre-image | `published_unexpected_pre_image` | advanced; **reconcile** |
| `attempting` | `!` `(stale info)` / `(fetch first)` / `(non-fast-forward)` / `cannot lock ref … is at X but expected Y` | `rejected_base_moved` | unchanged |
| `attempting` | `!` `[remote rejected]` (policy/permission) | `rejected_by_policy` | unchanged |
| `attempting` | `cannot lock ref … .lock: File exists` | `failed` | unchanged |
| `attempting` | no per-ref porcelain line, transport error, timeout | `uncertain` | **unknown; quarantine** |
| `rejected_base_moved` | reintegration + revalidation + renewed approval → new candidate | new operation, `base_epoch + 1` | unchanged |

### Controller disposition

| Outcome | Controller action |
| --- | --- |
| `published` | record, set `merged_commit`, confirm PR, return `merged` |
| `rejected_base_moved` | record, then `integrate_current_main()` — the existing reintegration/revalidation path |
| `rejected_by_policy`, `failed` | record, raise; the window quarantines (fail closed) |
| `uncertain`, `published_unexpected_pre_image` | record, raise; quarantine for reconciliation, **never retried** |
| prior `attempting` + remote == published commit | adopt as `published`; **no second publication** |
| prior `attempting` + remote == `expected_main` | proven not published; ordinary path may proceed |
| prior `attempting` + remote is neither | raise; quarantine and reconcile |

### Gate authority classes

| Durable record | Readable | Carries authority | Disposition |
| --- | --- | --- | --- |
| 15-key owner, `protocol_version == "2.0"` | yes | yes | normal |
| 13-key legacy owner | yes (audit + operator recovery) | **no** | `LegacyGateOwnerError`; explicit reconciliation |
| owner with `status ∈ {attempting, uncertain, published_unexpected_pre_image}` | yes | no new binding, no release | quarantine and reconcile |

---

## 6. Changed paths

One focused commit, 8 files (`8fb844ca…`):

| Path | Change |
| --- | --- |
| `Pipeline/TaskReviewAgent/publication_fence.py` | **new** — typed statuses, `PublicationBinding`, `PublicationOutcome`, ancestor proof, exact-lease transaction, porcelain classifier |
| `Pipeline/TaskReviewAgent/integration_gate.py` | versioned owner, publication operation schema/validation, `bind_publication`, `record_publication`, centralised `require_owner`, publication-bound receipts, `LegacyGateOwnerError` |
| `Pipeline/TaskReviewAgent/integration_window.py` | receipts bind the durable publication operation; imports `SCHEMA` |
| `Pipeline/TaskReviewAgent/downstream_pipeline.py` | publication path restructured: proven base, check-bound validated commit, owner-bound authority, durable outcome recording, crash adoption, reintegration on refusal |
| `Pipeline/TaskReviewAgent/gate_resume.py` | typed `GateResumeUnavailable` vs `GateResumeAuthorityError`; untrustworthy gate records block instead of triggering an architect call |
| `Pipeline/TaskReviewAgent/tests/publication_fence_smoke_test.py` | **new** — 24 deterministic regressions |
| `Pipeline/TaskReviewAgent/tests/gate_resume_smoke_test.py` | +4 authority/fallback regressions |
| `Pipeline/TaskReviewAgent/tests/production_end_to_end_smoke_test.py` | acceptance scenarios and GitHub emulator updated to the sanctioned protocol (§6.1) |
| `.github/workflows/task-review-agent-deterministic.yml` | registers the new regression in the Core gate step |

9 files, +2059 / -39. `git diff --check` exits 0 with no output. All 8 changed/added Python files
compile.

### 6.1 Why an acceptance test had to change

`production_end_to_end_smoke_test.run_positive_scenario` asserted the previous publication protocol
directly, and both assertions are now false by design:

* the exact external command sequence contained `"merge"` — `gh pr merge` is no longer issued at all;
* main's head was required to be a **two-parent merge commit** joining the initial main and the PR
  head — main now fast-forwards to the exact published candidate.

The orchestrator's ruling is explicit ("publish the exact approved and tested candidate commit
directly … verify that remote `main` equals the intended commit"), so leaving these assertions would
have left the committed suite contradicting the sanctioned design. They were replaced with stricter
statements of the new contract rather than relaxed:

* no `gh pr merge` appears anywhere in the command sequence;
* `main == pull_request["merged_head"]` — the exact commit the required checks were accepted for;
* `merge-base --is-ancestor <fenced base> <main>` exits 0 — append-only history preserved.

The emulator additionally settles a pull request whose head has become reachable from main, which is
how GitHub settles a pull request published by other means. That modelling assumption is called out
as unverified against live GitHub in §11.2.

This is the one behaviour-visible change outside the F1/F6 surface, and it is a direct consequence of
the sanctioned removal of `gh pr merge`. No assertion was weakened to accommodate the fix; the
earlier `_latest_validation_authority` binding error (§3) was caught by exactly this class of test
and was corrected rather than asserted around.

---

## 7. Red-before / green-after evidence

### 7.1 The audit's F1 reproduction at the required base

`main_cas_race_repro.py`, copied byte-identically from the audit evidence with only `SOURCE`/`EVIDENCE`
redirected so the audit's preserved output is not overwritten, run against `837eb4f…`:

```
AssertionError: 'merged' == 'merged' : Published against changed main:
exact-old main value was never part of the mutation
FAILED (failures=1)
```

Observed identities (`evidence/main-cas-race-observed-BASE-RED.json`):

```
approved task head     2d0dad37d3cb609d9a0fef3b66ea41533ba2afa5
guarded main           b160eb789b638ae4611432da4dc7c6691ab45a4a   ← proven integrated
main at publication    6effdbe9c82cd2e9d1fd595bdc3e2b41ea5ee9e8   ← competing writer
published merge        ab80a7ea76a4320ecece3f8aec77d7d76cfbb1c2
controller result      status = merged
approved head contains the concurrent change: False
```

The only publication command issued was
`gh pr merge 1 --repo … --merge --match-head-commit 2d0dad37…`. The guarded main `b160eb78…`
appears in **no** command.

### 7.2 F6 proven by durable-record inspection at the required base

The persisted gate owner from the same run carried exactly the 13 legacy keys:

```
acquired_at, ci_seconds, heartbeat_at, lease_id, operation, progress,
repository, run_id, status, target_branch, task_id, unity_seconds, worker_id
```

No approved source head. No expected main. Confirmed by code inspection at
`integration_gate.py:155-156` (closed 13-key set) and `:238-240` (the sole constructor).

### 7.3 Paired behavioural probes — same file, both revisions

`evidence/paired_publication_probes.py` imports only symbols that exist at the base, so identical
code runs against both trees. These are behavioural assertion failures on the real production path,
not import errors or missing symbols.

| Probe | Base `837eb4f…` | Final `8fb844ca…` |
| --- | --- | --- |
| `main_race_after_final_guard_is_rejected` | **FAIL** — `published against a changed base: controller reported 'merged'` | **PASS** |
| `durable_owner_binds_source_and_expected_main` | **FAIL** — `the durable owner record does not contain the approved source head …; keys=[13 legacy keys]` | **PASS** |
| `no_unfenced_main_mutation` | **FAIL** — `publication used 'gh pr merge', which pins only the pull-request head and cannot express the expected base` | **PASS** |
| `crash_after_publication_does_not_publish_twice` | **FAIL** — `recovery performed 2 authoritative merges` | **PASS** |

Logs: `paired-probes-base-RED.log`, `paired-probes-final-committed-GREEN.log`; machine-readable
`paired-probes-base.json`, `paired-probes-final-committed.json` (records `HEAD=f1860529…`).

### 7.4 Measured primitive semantics

Disposable local repositories, `evidence` scratch runs:

```
plain FF push, main moved disjoint      exit 1  ! [rejected] (fetch first)      main unchanged
plain FF push, main moved conflicting   exit 1  ! [rejected] (fetch first)      main unchanged
plain FF push, main inside candidate    exit 0    accepted            ← the hole
exact lease,  main inside candidate     exit 1  ! [rejected] (stale info)       main unchanged
exact lease,  main == expected          exit 0    <old>..<new>        main == candidate
exact lease,  replay                    exit 0  = [up to date]        idempotent
```

### 7.5 The audit reproduction at the corrected HEAD

Re-run unchanged against `8fb844ca…`: it errors with `KeyError: 'expected_main'`, because its
instrumentation point — the `gh pr merge` transport boundary — is no longer on the publication path.
The trace confirms this (`evidence/main-cas-race-observed-FINAL.json`): the only `gh` commands are
three `pr view` calls, `gh pr merge issued: False`, and the durable owner now carries the full
15-key record with a `published` operation whose `observed_pre_image` equals the bound
`expected_main`.

The original reproduction is preserved unchanged as historical evidence
(`evidence/main_cas_race_repro_base837.py`, `f1_repro_base837_RED.log`), and its interleaving is
retained as a committed regression at the new authoritative boundary
(`publication_fence_smoke_test.BaseMovementTests.test_main_changes_exactly_between_validation_and_publication`).

### 7.6 Regression coverage of the required matrix

| # | Required regression | Committed test |
| --- | --- | --- |
| 1 | Main changes exactly between validation and publication | `test_main_changes_exactly_between_validation_and_publication` |
| 2 | Disjoint competing main commit | `test_disjoint_competing_main_commit_is_a_base_change` |
| 3 | Conflicting competing main commit | `test_conflicting_competing_main_commit_is_rejected` |
| 4 | Main unchanged: publication succeeds exactly once | `test_unchanged_main_publishes_exactly_once` |
| 5 | Same task/run/worker, mismatched source commit | `test_mismatched_source_commit_does_not_inherit_authority` |
| 6 | Same task/run/worker, mismatched expected main | `test_mismatched_expected_main_does_not_inherit_authority` |
| 7 | Stale operation attempts publication | `test_stale_operation_cannot_record_a_publication`, `test_uncertain_operation_is_never_retried` |
| 8 | Stale operation attempts completion | `test_stale_operation_cannot_complete_the_gate` |
| 9 | Old-schema active owner fails closed | `test_old_schema_active_owner_fails_closed_but_stays_readable`, `test_legacy_gate_owner_blocks_gate_resume` |
| 10 | Legitimate reintegration creates new base-bound authority | `test_legitimate_reintegration_creates_new_base_bound_authority` |
| 11 | Crash after publication, before receipt; no double publication | `test_crash_after_publication_before_receipt_does_not_publish_twice` |
| 12 | Uncertain outcome; successor blocked pending reconciliation | `test_uncertain_outcome_quarantines_and_blocks_the_successor` |
| 13 | Required checks belong to the exact publication topology | `test_required_checks_belong_to_the_exact_publication_topology`, `test_publication_refuses_checks_accepted_for_another_commit`, `test_publication_requires_a_check_that_names_its_commit`, `test_publication_refuses_a_head_the_checks_did_not_cover` |
| 14 | No force/ref rewind in any publication command | `test_only_an_exact_lease_is_used_and_no_rewind_is_possible` |
| 15 | Durable receipt contains all required identities | `test_durable_receipt_contains_all_required_identities` |
| 16 | Moved base returns to reintegration, not a silent merge | `test_moved_base_returns_to_reintegration_not_a_silent_merge` |
| 17 | Queue and poke remain exactly-once | `test_queue_order_and_wake_remain_exactly_once_after_a_rejection` |

Additional: `test_validation_evidence_must_name_the_published_candidate`,
`test_settlement_cannot_claim_a_publication_that_never_happened`, and four gate-resume
authority/fallback cases.

All interleavings are produced at controlled transport boundaries — the exact command boundary at
which the competing writer runs — or by injected clocks and durable-state edits. No sleep is used as
a correctness oracle.

---

## 8. Test totals and exact commands

**31 scripts, 0 failed, 508 named cases** (156 unittest cases + 352 hand-rolled `PASS` lines),
1228.1s wall clock. Every script was executed from the final committed HEAD `8fb844ca…` as:

```bash
python -B <script>
```

with `cwd` = `C:\NSC\ClaudePublicationFence-20260907\NoSafeCircle`, `PYTHONUTF8=1`,
`PYTHONDONTWRITEBYTECODE=1`. The runner is `evidence/run_matrix.py`; per-script logs are in
`evidence/matrix-final/`, machine-readable results in `evidence/matrix-final/results.json`.

| Script | Cases | Counted as | Result | Seconds |
| --- | ---: | --- | --- | ---: |
| `integration_gate_smoke_test.py` | 14 | unittest | PASS | 83.6 |
| `integration_window_smoke_test.py` | 10 | unittest | PASS | 67.0 |
| `integration_gate_base_regression_test.py` | 18 | unittest | PASS | 86.7 |
| `gate_resume_smoke_test.py` | 23 | unittest | PASS | 213.7 |
| `gate_restart_recovery_smoke_test.py` | 5 | unittest | PASS | 43.5 |
| `autonomous_gate_wake_smoke_test.py` | 6 | unittest | PASS | 10.4 |
| `mainline_reintegration_smoke_test.py` | 9 | named PASS lines | PASS | 21.7 |
| `publication_fence_smoke_test.py` | 24 | unittest | PASS | 279.3 |
| `downstream_smoke_test.py` | 16 | named PASS lines | PASS | 5.4 |
| `downstream_issue_smoke_test.py` | 6 | named PASS lines | PASS | 0.2 |
| `downstream_determinism_smoke_test.py` | 14 | named PASS lines | PASS | 8.8 |
| `downstream_action_grounding_smoke_test.py` | 7 | named PASS lines | PASS | 0.2 |
| `downstream_resilience_smoke_test.py` | 11 | named PASS lines | PASS | 11.7 |
| `merge_closeout_check_repoll_smoke_test.py` | 6 | named PASS lines | PASS | 0.3 |
| `pull_request_check_authority_smoke_test.py` | 8 | named PASS lines | PASS | 0.2 |
| `polling_orchestrator_smoke_test.py` | 134 | named PASS lines | PASS | 63.2 |
| `production_graph_snapshot_smoke_test.py` | 1 | named PASS lines | PASS | 0.4 |
| `autonomous_graph_run_smoke_test.py` | 1 | named PASS lines | PASS | 0.5 |
| `autonomous_graph_cli_smoke_test.py` | 1 | named PASS lines | PASS | 0.5 |
| `contention_retry_smoke_test.py` | 17 | named PASS lines | PASS | 48.3 |
| `execution_routing_smoke_test.py` | 36 | named PASS lines | PASS | 0.4 |
| `issue_workflow_smoke_test.py` | 47 | named PASS lines | PASS | 50.1 |
| `actor_authorization_smoke_test.py` | 13 | named PASS lines | PASS | 0.2 |
| `ci_workflow_split_smoke_test.py` | 0 | named PASS lines | PASS | 0.1 |
| `git_identity_guard_smoke_test.py` | 0 | named PASS lines | PASS | 0.4 |
| `automated_validation_downstream_smoke_test.py` | 8 | named PASS lines | PASS | 33.9 |
| `durable_checkout_smoke_test.py` | 10 | named PASS lines | PASS | 25.3 |
| `public_synthetic_authority_smoke_test.py` | 10 | unittest | PASS | 0.4 |
| `pending_workflow_write_smoke_test.py` | 36 | unittest | PASS | 0.4 |
| `post_poll_observation_budget_smoke_test.py` | 10 | unittest | PASS | 0.6 |
| `production_end_to_end_smoke_test.py` | 7 | named PASS lines | PASS | 170.7 |

The matrix was run three times in total. The first authoritative run at `f1860529…` was
**31 scripts, 1 failed** — `production_end_to_end_smoke_test.py`, whose acceptance assertions
encoded the previous publication protocol (§6.1). The second at `21749e0d…` was 31/0 with 507 named
cases. This third run is the final one, after the live-payload correction in §11.9.

Deterministic checks, run from the committed HEAD:

```bash
python -B Pipeline/TaskGraph/taskcontrol.py validate
```
exit 0 — 60 active contracts, 59 parent edges, 106 dependency edges, 8 resource groups,
17 project requirements, parent hierarchy connected + acyclic, dependency graph acyclic,
autonomous dispatch authority DISABLED.

```bash
git diff --check
```
exit 0, no output.

Python compilation of all changed/added files: 7 files, all compile, no bytecode written.

---

## 9. Crash and recovery evidence

**Crash after the authoritative mutation, before the local receipt.** The regression performs the
real ref transaction against the real bare remote and then raises `SystemExit` at the transport
boundary. The durable record is left at `attempting` with the exact `publication_commit`; the remote
target already holds it. On re-entry `_adopt_prior_publication` runs **before** anything rebinds,
reads the target branch once, finds it equal to the recorded commit, and adopts the proven outcome:
`status=merged`, the same `merged_commit`, and the publication-push count unchanged. The paired probe
shows the base performing **2 authoritative merges** in the same scenario.

Ordering matters here and was found by test, not by inspection: an earlier revision derived a fresh
base before consulting the durable record. After a successful publication the freshly derived base is
the candidate itself, which produced a different binding and an `unreconciled (attempting)` refusal
instead of recovery. Recovery now precedes rebinding.

**Uncertain outcome.** A transport failure with no per-ref porcelain line classifies as `uncertain`,
is recorded durably, and raises. `IntegrationWindow.failure` quarantines the owner; a successor's
`acquire` returns `deferred`; the target branch is unchanged; and a second attempt refuses rather
than retrying.

**Crash before publication.** Unchanged from base behaviour: the durable owner and unfinished
operation are retained and no successor is authorized.

---

## 10. Compatibility and migration

* **The gate journal envelope was not version-bumped.** `SCHEMA` stays `"1.0"`. Bumping it would make
  every existing remote journal unreadable — `read()` → `validate()` → `IntegrationGateError`, with no
  migration writer anywhere in the tree, and `recover()` itself calls `read()`. Versioning is carried
  on the **owner** record instead, so existing journals stay readable and the queue keeps working.
* **Legacy 13-key owners remain readable** for audit and for explicit operator recovery, and are
  refused by every authority operation with a typed `LegacyGateOwnerError`. They are never
  reinterpreted as authorized new-schema leases.
* **Durable history is preserved.** The journal is append-only and parent-chained; no prior gate
  record is deleted or rewritten. A rebinding after reintegration appends a new operation with
  `base_epoch + 1` and a new operation identity; the prior operation remains in the journal
  (asserted by `test_legitimate_reintegration_creates_new_base_bound_authority`).
* **Receipt version.** `integration_window.py` now imports `SCHEMA` instead of hard-coding `"1.0"`, so
  a future bump cannot silently desynchronise receipts from `_require_receipt`.
* **`gate_resume` fallback contract preserved.** The saved route is host-owned history, not authority.
  A missing, corrupt or changed route receipt still falls back to the architect — this is an existing
  committed contract (`test_missing_corrupt_or_changed_route_uses_architect`) and an earlier revision
  of this change that promoted those to authority errors was reverted. Only untrustworthy **gate**
  records block.
* **Not implemented, by instruction:** F2, F3, F4, F5, F7, F8, visualizer work, package-fixture
  corrections.

---

## 11. Remaining uncertainty

1. **No live GitHub semantics were exercised.** The reported live configuration
   (`main.protected=false`, no required checks, zero rulesets) makes direct publication permitted, but
   that was supplied to this work rather than queried by it, and no live call was made. If protection
   is later enabled to require pull requests, the fenced transaction fails closed as
   `rejected_by_policy` and quarantines. That is safe but would stop delivery until the protocol is
   given a server-enforced merge-queue path.
2. **`gh pr merge` no longer runs**, so the pull request is expected to be marked merged by GitHub's
   reachability detection. That behaviour was not exercised against live GitHub. If the PR is not
   auto-marked, main is still authoritative and independently re-verified by
   `verify_post_merge_and_complete`; the controller records the observed PR state rather than
   publishing a second time.
3. **`--force-with-lease` client/server split.** `stale info` is the client-side rejection against the
   ref advertisement; `cannot lock ref … is at X but expected Y` is the server-side rejection. Both
   are classified as `rejected_base_moved`. Only the local-remote (client-side) form was exercised
   here; the server-side string is recognised by pattern and by the repository's existing
   `_contention_proof_pattern`, but was not produced by a live GitHub receive-pack in this work.
4. **`published_unexpected_pre_image` is unreachable under an exact lease** — the lease guarantees the
   pre-image. It is retained as a defence-in-depth classification and is not covered by a behavioural
   regression.
5. **Proven-failure disposition is conservative.** `rejected_by_policy` and `failed` quarantine even
   though the branch is proven unchanged. This is fail-closed but costs availability on a transient
   ref-lock; a bounded revalidation path could be added later.
6. **Paired red evidence covers the F1/F6 contract core** (§7.3), not every one of the 24 new cases
   individually. Cases asserting behaviour of contracts that do not exist at base (for example the
   legacy-owner refusal) have no meaningful base-behaviour form; they are stated as new-contract
   coverage, not as red/green pairs.
7. **The two merge-ref workflows** (`checkout-root-policy.yml`, `history-identity-migration-dry-run.yml`)
   validate a synthetic merge, not the candidate head. The argument that their tested tree equals the
   candidate's tree is given in §3 and enforced defensively by the check-commit binding, but it rests
   on the mainline guard's ancestry proof rather than on those workflows pinning the head. Pinning
   them would remove the argument entirely; that is outside this change's scope.
8. **The frozen source advanced during this work, and already contains it.**
   `C:\NSC\PublicPipelineIntegration-Astra-20260907` moved from `837eb4f…` to
   `0706fd0f18c5c849882c56d5091afc89e6a31a7c` while this change was being built — five commits,
   including `0103b1a Fence authoritative main publication to the exact validated base commit`
   (this commit's exact subject) plus F2-F8 work that was explicitly out of scope here. Its
   `publication_fence.py` is byte-identical to this branch's modulo line endings. This work was
   therefore landed upstream as it was produced; this branch is an independent, self-consistent
   copy on `837eb4f…`, not the only copy. The source checkout was not modified by this work and is
   clean; `837eb4f…` remains an ancestor of its current HEAD.

9. **A production-breaking bug shipped in an earlier revision of this change and was corrected.**
   `_accepted_validation_commit` originally *required* every `statusCheckRollup` entry to name its
   own commit, raising otherwise. That requirement is wrong: `gh pr view --json` has no field to
   request a per-entry commit, and no production code in this repository at `837eb4f…` reads one —
   the only `headSha` in the entire base tree is the end-to-end emulator's own invention
   (`production_end_to_end_smoke_test.py:1475`). A fixture artifact had been promoted to a hard
   production requirement, and every live GitHub rollup would have failed closed and blocked
   publication. The regressions did not catch it because the same author wrote fixtures that supply
   the field. The top-level `headRefOid` is now the binding (already asserted in
   `_proven_publication_base`) and a per-entry commit is an additional guard when present, so a
   rollup describing a synthetic merge ref still refuses publication. Upstream `783b320 Align
   publication evidence with live GitHub payloads` reached the same conclusion independently; the
   claim was re-verified against the base tree here rather than accepted on authority.

10. **Commit trailer.** No `Co-Authored-By` trailer was added. `AGENTS.md` requires a non-attributable
   automation identity for TaskReviewAgent commits, and the task specified that identity explicitly;
   adding an attributable co-author to an automation commit cuts against that policy. Flagged here
   rather than decided silently.

---

## 12. Isolation — no live system was touched

* The frozen source checkout was read only; it remained clean at `837eb4f…`.
* All work happened in `C:\NSC\ClaudePublicationFence-20260907\NoSafeCircle` on
  `claude/fix-atomic-publication-fence`. Nothing was pushed or merged.
* No global `safe.directory` exception was added.
* No GitHub, Docker, Unity, or Claude/Codex provider call was made; no live Issue was contacted. Every
  `gh` invocation in every test is a fake transport. Every Git mutation targeted a disposable local
  bare repository under a temporary directory, or the isolated checkout.
* Rehearsal repositories, live claims, workers, containers and task state were not touched.
* No provider or architect call exists in the publication or recovery paths. The change **removes** an
  architect invocation that a gate-authority failure would previously have triggered.
* `Tasks/`, `Docs/GDD/`, `Assets/`, `Packages/`, `ProjectSettings/` are unmodified; public TaskGraph
  metadata is byte-identical and `taskcontrol.py validate` passes with the audit's own figures.
  NSC-042's dependencies are untouched.

---

## 13. Commit identity and clean-tree proof

```
$ git log -1 --format='%H%n%an <%ae>%n%cn <%ce>%n%s'
8fb844ca524313709bcaaa0c1c07d35ceb7814ea
No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>
No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>
Fence authoritative main publication to the exact validated base commit

$ git status --porcelain --untracked-files=all
(empty)
```

One focused local commit. Nothing pushed. This report is uncommitted and lives outside the
repository at `C:\NSC\CLAUDE_ATOMIC_PUBLICATION_FENCE_REPORT.md`.
