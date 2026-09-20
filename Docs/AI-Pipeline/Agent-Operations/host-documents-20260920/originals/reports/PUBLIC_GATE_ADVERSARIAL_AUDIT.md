# Independent adversarial audit: public integration gate and stranded wake

**Verdict: BLOCK.** The gate serializes its own journal, but publication does not atomically fence the expected main commit. The stranded-wake classifier also does not survive two existing production consumers: gate admission treats a proven pending write as fatal, and closed-Issue discovery discards a supported pending completion. Deterministic reproductions demonstrate all three problems at the audited commit.

The public transplant boundary passes the inspected ancestry, artifact, and byte-equivalence checks. Passing committed tests do not resolve the production-path failures below. No fixes or source/integration delivery mutations were performed. Test-created commits, ref pushes and merges occurred only inside disposable local fixtures; no external repository or live Issue was mutated.

## Audited identity and isolation

| Item | Exact value |
| --- | --- |
| Source | `C:\NSC\PublicPipelineIntegration-Astra-20260907` |
| Source branch | `integration/production-orchestration-bb560d0e` |
| Audited HEAD | `eb3353fc76630ebcfcdaa73626ef78b7b0c8273e` |
| Audited tree | `aa4373178dc1bb1ff74c6e61fc6e0dcc583d202b` |
| Isolated clone | `C:\NSC\PublicGateAdversarialAudit-20260907T033720Z` |
| Local audit branch | `audit/public-gate-adversarial` |
| External evidence directory | `C:\NSC\PublicGateAdversarialAudit-20260907T033720Z-evidence` |
| Public base | `73fae3818ded52eec10e12230de7403cafda4081` |
| Stable comparison boundary | `bb560d0e56b77156b0d59cd1f60b1ac2fb02a371` |
| Read-only source correction | `11dcd130665d531d556af48756d4d5291cd3991e` |
| Source correction parent | `aac323d23a183631cf2850909b770d9db9f313fa` |

Exact integration parent chain:

```text
eb3353fc76630ebcfcdaa73626ef78b7b0c8273e
  -> e5eb662a205d741874330784dc27912ae6eeea43
  -> ba18e34d36fb2435133d89804df0c1d62e1f358e
  -> 73fae3818ded52eec10e12230de7403cafda4081
  -> e5061fdfe259bedef5d1293680e7b2ec03bcaf42
```

Readiness observation began at **2026-09-07 03:31:21 UTC**, with deadline **04:01:21 UTC**. Observations were:

| UTC | HEAD | Status / readiness |
| --- | --- | --- |
| 03:31:21 | `e5eb662…` | Clean; required committed regression files absent |
| 03:32:11 | `e5eb662…` | Same |
| 03:33:26 | `e5eb662…` | Six modified tracked files and three untracked regression files |
| 03:34:34 | `e5eb662…` | Same uncommitted state |
| 03:35:46 | `e5eb662…` | Same uncommitted state |
| 03:37:02 | `eb3353f…` | Clean; ancestor test passes; all three regression files committed |

The final commit also contains the four production correction files. Only after readiness passed was that exact SHA cloned locally with `--no-hardlinks --no-checkout`, then checked out on the audit branch. Intermediate implementation trees were not audited. Required AGENTS, testing policy, Game Task Agent, Issue workflow, gate, resume, and operator guidance were read. Tests are component/regression tests using temporary repositories, in-memory Issues, controlled clocks and fake external transports. Unity executable/XML and gameplay acceptance are not applicable. The visualizer was excluded from substantive review; the requested all-changed-Python compilation and public-artifact inventory still cover its files mechanically.

**Later source movement:** at 04:00:46 UTC the source was clean at `837eb4f0fa0ba8d619bbb78b500e73ccfd229792`, a direct child of the audited SHA titled “Add read-only lifecycle navigation with public-isolated viewer defaults.” A read-only changed-path comparison shows eight visualizer, documentation and CI/test paths; none of the audited production gate/workflow/scheduler files changed. This report and its test totals apply to `eb3353fc…`, not that later commit's visualizer or CI/test changes. The isolated audit checkout did not move. The read-only correction source remained clean at `11dcd130…`.

## Findings, ordered by priority

No P0 finding was established. F1–F3 are release blockers. F4–F6 are additional unmet audit requirements. F7–F8 are non-blocking follow-ups.

### F1 — P1: publication has no atomic expected-main check

References: [downstream_pipeline.py:1124](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/downstream_pipeline.py:1124), [publication command:1133](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/downstream_pipeline.py:1133), [receipt persistence:1152](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/downstream_pipeline.py:1152).

The real pre-merge guard proves that current main is integrated into the approved task head. The later `gh pr merge --match-head-commit <task-head>` pins only that task head. An external main writer can move main between the guard and the mutation. The gate's compare-and-swap operates on a separate journal ref, so it cannot reject this main movement.

**Deterministic reproduction:** [main_cas_race_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/main_cas_race_repro.py) runs a normally constructed controller, actual Issue transitions/leases, real local Git gate, actual check evaluation and mainline guard. At the fake GitHub transport boundary immediately after the guard, it makes a disjoint local main commit, then performs the merge allowed by the supplied command. No sleeps determine the interleaving. The unchanged controller returns `status=merged` and persists the receipt.

Observed local fixture identities:

- Approved task: `9d99f6513728def9d31ea4db69719fd54a5902bb`.
- Guarded main: `bebe7bb55e335c7c953e4bfa32f7dd8a41267e49`.
- Main at publication: `b2e3c8e0d0e3eff584464ff9a3eee11237eb6668`.
- Published merge: `83fcc194d7f51caefdbb641e075af1cc6e473b0a`.

The approved task does not contain the concurrent main change. The desired assertion that changed main prevents publication fails. [Trace and preserved fixture location](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/main-cas-race-observed.json); [authoritative log](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/main_cas_race_repro-reviewed.log).

**Minimal correction:** bind the validated main OID to the publication attempt and enforce it atomically at the authoritative branch mutation, preserving append-only topology and required checks. A server-enforced merge queue or equivalent publication primitive must reject or revalidate a changed base. Another read immediately before the current command does not close the race. Retain this interleaving as a regression. Uninspected live branch protection might independently reject the merge; the implementation neither establishes nor tests that guarantee, and no live settings were queried.

### F2 — P1: a proven pending write still causes fatal gate admission

References: [integration_window.py:55](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_window.py:55), [gate filter:339](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_window.py:339), [scheduler call:3370](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/polling_orchestrator.py:3370), [outer failure/drain:2175](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/autonomous_graph_run.py:2175).

An authorized, recent human-result transition has its hashed event and trusted source-label removal visible while no state label is visible. Production observation correctly recognizes pending, reserves resources, emits `issue_pending_transition`, and leaves the corruption counter at zero. A second coherent delivery task has disjoint resources. `require_no_legacy_delivery_owner()` rejects every pending snapshot anyway. The exception escapes before queue registration, architect invocation or worker launch; the outer controller records an error and drains.

**Deterministic reproduction:** [pending_gate_scheduler_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/pending_gate_scheduler_repro.py), [log](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/pending_gate_scheduler_repro.log). The production scheduler, reservation observer, gate filter and local Git CAS all execute. Assertions establish a genuine pending event, counter zero, no calls or gate mutation, followed by an unexpected fatal exception. One desired-behavior test fails without a setup error.

**Minimal correction:** make a proven pending workflow a bounded wait at the migration fence, retaining reservations and the durable queue. Waiting all delivery admission is safe; allowing disjoint delivery requires proof that the pending write cannot conceal a legacy owner. Do not simply ignore invalid ownership. Test pending plus a delivery candidate through the real scheduler, subsequent convergence and exactly-one admission, and expiry into the existing corruption path.

### F3 — P1: closed pending completion disappears before classification

References: [bulk prefilter:polling_orchestrator.py:878](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/polling_orchestrator.py:878), [per-task prefilter:completed_issue_guard.py:81](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/completed_issue_guard.py:81), [resource enumeration:issue_workflow_store.py:1520](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/issue_workflow_store.py:1520), [snapshot reservations:production_graph_snapshot.py:473](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/production_graph_snapshot.py:473).

The new classifier supports a closed Issue whose body lags by a delivery lease and COMPLETED event. Its canonical hash chain, label-removal event and close event can prove a bounded pending completion. Existing enumeration paths discard a CLOSED Issue whose stale body is not already COMPLETE, before reading that evidence.

**Deterministic reproduction:** [independent_workflow_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/independent_workflow_repro.py), [final log](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/independent_workflow_repro_final.log). Direct `_snapshot` proves pending; the real production snapshotter then returns `pending=()`, `reservations=()`, `issues=[]`. The graph evaluator returns `actionable` with `internally_stalled=True` instead of `temporary_wait`; per-task observation reports `agent_ready_uninitialized`. Two assertions fail on reservation retention and production graph classification. This proves authority/discoverability loss, not an actually repeated delivery commit.

**Minimal correction:** let authorized closed managed candidates reach full-history classification before applying the historical closed-incomplete-duplicate rule. Preserve a proven completion prefix consistently in bulk, per-task and resource readers. Positively classify old incomplete duplicates; do not upgrade arbitrary closed Issues into authority. Test both allowed prefix lengths, coherent completion, expiration, contradictory close records and malformed suffixes. A settled COMPLETE body with expired missing labels already fails closed; the stale-prefix prefilter must not bypass that protection indefinitely.

### F4 — P2: one unusable queued Issue blocks authorized delivery

References: [migration fence:integration_window.py:44](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_window.py:44), [queued-entry validation:340](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_window.py:340).

With no gate owner, a missing queued Issue raises before a valid delivery can register. A malformed managed queued Issue fails even earlier at the migration fence. The queue is preserved, but the availability requirement is not: unrelated authorized delivery cannot progress. Ordinary unauthorized Issues are correctly ignored by the actor-authorization tests; that does not repair a poisoned durable queue entry.

**Deterministic reproduction:** [queue_liveness_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/queue_liveness_repro.py), [log](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/queue_liveness_repro.log). A real GateResume fixture launches its valid control once. Adding either a missing or malformed queued task yields zero launches with `owner=null`; both desired liveness assertions fail. No production scheduler, filter or queue method is patched.

**Minimal correction:** introduce an explicit durable quarantine/reconciliation disposition for an unusable waiter instead of an undifferentiated global exception. Retain history and known resources; permit other work only after proving it does not conflict with unresolved ownership. Missing or malformed data must never silently mean completed, withdrawn or safe. Add these two cases and a conflicting-resource control.

### F5 — P2, inherited: label-first pending accepts weaker evidence

References: [issue_workflow_store.py:364](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/issue_workflow_store.py:364), [label-first dispatch:1043](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/issue_workflow_store.py:1043).

The existing label-first classifier checks target and age but does not check the label event actor or replay all body fields. Independent ordinary human-history tests change only the event actor to an unauthorized account, or change both body head/handoff commits while preserving history proving another commit. Both still receive pending treatment. The new no-label replay path correctly rejects corresponding evidence; the combined classifier remains inconsistent.

Reproduction: the two `test_label_first_*` cases in [independent_workflow_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/independent_workflow_repro.py). Both fail at final and exact `e5eb662`; source inspection locates this classifier already in public base `73fae381`. This is an inherited weakness against the requested invariant, not a new correction regression. Pending remains non-runnable and bounded; no unauthorized merge is claimed.

**Minimal correction:** apply authorized label-actor checks and canonical replay/body binding to label-first pending too. Preserve valid additive/replaced label forms and repeated human validation cycles. Add altered commit, lease, worker, unauthorized actor and timestamp cases to that path.

### F6 — P2: the lease omits source and expected-main identities

References: [owner schema:integration_gate.py:155](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_gate.py:155), [acquisition:225](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_gate.py:225), [owner record:238](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/integration_gate.py:238).

The owner is bound to task, run, worker, random lease, repository and target branch. Its strict schema contains neither source commit nor expected main. The persisted owner in F1's trace demonstrates the omission. Separate Issue/mainline guards provide some checks, but the requested lease-level identity cannot be established; same-owner admission resumes the old record without either value.

**Minimal correction:** add versioned, exact source and publication-base identities to the appropriate lease/operation record, validate them on resume and each mutation, and bind them into completion/recovery receipts. If current main is intentionally refreshed after acquisition, record that exact value in an owner-bound operation transition before publishing. Test mismatched source/base independently of task/run/worker mismatches. This is a contract gap; it is not evidence that a foreign worker can steal the current lease.

### F7 — P2, non-blocking: two CI selection guards are not registered

References: [ci_workflow_split_smoke_test.py:313](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py:313), [second omitted guard:336](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py:336), [main:475](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Pipeline/TaskReviewAgent/tests/ci_workflow_split_smoke_test.py:475).

The registered script calls 12 checks and omits the two new ordinary-delivery/Core-selection guards. An external in-memory mutation widens the allowed evidence prefix to all of `Pipeline/`; registered `main()` still returns PASS, while the omitted guard rejects the exact same text. Both omitted guards pass on the actual committed workflow, so no currently unsafe production prefix was demonstrated.

Reproduction and result: [ci_unregistered_repro.py](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/ci_unregistered_repro.py), [JSON](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/ci-unregistered-repro.json). **Minimal correction:** call both functions from `main()` and verify that the deliberate widened-prefix mutation fails through the registered command.

### F8 — P3: public runbook contains obsolete guidance and test path

References: [GAME_TASK_AGENT_RUNBOOK.md:115](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md:115), [public disable statement:332](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md:332), [acceptance command:498](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z/Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md:498).

An earlier section still describes synthetic enablement for a private repository although this public build rejects it. The acceptance section names the old `muffcabbage_end_to_end_smoke_test.py`, renamed to `production_end_to_end_smoke_test.py`. Executable consumers were updated. **Minimal correction:** make the earlier enablement description match the public disabled policy and update the prose/command to the existing test filename.

## Invariant matrix

PASS means the stated local implementation path is supported by inspection and deterministic evidence, not a universal distributed-system proof. PARTIAL identifies a narrower guarantee or missing evidence; FAIL identifies an unmet requirement. Findings above contain the correction plans.

### Durable serialization

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| One integration owner; competing workers cannot both acquire | PASS | Real local Git remote-ref CAS and separate-process contention; gate/window suites |
| Lease binds task, run, worker, source and expected main | FAIL | Task/run/worker/lease/domain bound; source/main absent, F6 |
| Stale/foreign owner cannot renew, release or complete another lease | PASS | Exact identity checks, wrong-owner/receipt negative cases, stale-OID recovery rejection |
| Stale/foreign worker cannot publish through guarded controller | PASS within gate identity model | Normal controller construction installs owner/active-operation guard; no authorization from a poke |
| Crash cannot turn uncertain publication into another attempt | PASS for fail-closed safety | Persisted unfinished operation/quarantine blocks blind replay; manual reconciliation required |
| Retry/resume never duplicates delivery | PARTIAL | Same-owner and terminal settlement idempotence tested; uncertain outcomes stop. Exhaustive real-service crash recovery not established |
| Main movement checked with exact expected-old value | FAIL | F1 |
| No destructive force publication, rewind, reset or unsafe fallback | PASS in audited gate/delivery paths | Normal merge/push behavior retained. Gate journal CAS uses exact-ref fencing and parent-linked additive history; not a main rewind |
| Queue order/selection deterministic | PASS for registered eligible set | UTC ready instant, task-ID tie break, preserved original ready event |
| No permanent deadlock after ordinary worker failure | PARTIAL | Known/quiescent failures release; hard crash/uncertain subprocess deliberately requires explicit fenced recovery, without an automatic completion deadline |
| Failure retains durable state for recovery | PASS for state retention; PARTIAL for time bound | Journal/owner/operation/receipts survive; recovery API is fenced. Human fencing and remote reconciliation are not time-bounded by this code |

### Waiting-task behavior

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| Waiting task remains durably discoverable | FAIL in closed-prefix case | Open waiters/queue retained; F3 loses pending closed workflow discovery |
| Owner completion chooses next authorized waiter | PARTIAL | Atomic release/next wake and deterministic order pass with valid entries; F4 stops on unusable entries |
| Duplicate wakes do not create duplicate workers | PASS | Gate resume/restart, duplicate loopback wake and polling tests |
| Worker/task cannot disappear from both coordination views | FAIL | F3 removes pending workflow from production observation/reservations; no actual duplicate commit claimed |
| Fairness defined rather than Issue enumeration order | PASS within registered set | Stable timestamp/task ordering; no preemption of current owner |
| Stale cached Issue cannot silently skip queue entry | PASS for retention, PARTIAL for availability | Selected authority rechecked; failures stop/preserve rather than silently withdraw; F4 |
| Unauthorized/malformed Issue cannot block all authorized work | FAIL | Ordinary unauthorized Issues filtered; malformed/missing durable waiter blocks delivery, F4 |

### Stranded-wake correction

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| Recent provable mutation may have no label | PASS | Canonical fixed-time no-label tests and independent ordinary-human control |
| Observation is bounded PENDING_TRANSITION instead of fatal corruption | FAIL combined | Classifier succeeds, gate guard then fatals, F2 |
| Proof uses valid hashed authorized history | PASS new no-label path; FAIL combined exception policy | Exact replay and actor negatives pass there; inherited label-first gap, F5 |
| Pending continues reserving resources | FAIL | Open path passes; closed prefix is dropped, F3 |
| Pending does not increment fatal-corruption counter | PASS at observation boundary | Counter remains zero even in F2; this does not prevent the later fatal exception |
| Pending is not prematurely ordinary runnable work | FAIL | Open queue excludes it; F3 reports uninitialized/actionable task |
| Pending expires after defined interval | PASS in classifier | 600 seconds, anchored to evidence timestamps, controlled clock; repeated reads/activity do not renew it |
| Expired missing labels fail closed | PARTIAL | Direct/settled-body reads fail closed; closed stale-body prefilter in F3 bypasses classification entirely |
| Forged/malformed/contradictory/unauthorized/future/replayed/mismatched evidence never pending | FAIL combined | Broad no-label negative coverage passes; label-first actor/body counterexamples, F5 |
| Closed completed Issues retain complete label | PARTIAL | Settled COMPLETE body is checked; stale completion prefix can disappear, F3 |

### Observation retry budget

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| Post-poll production snapshots use bounded transient policy | PASS | Typed production adapter and boundary-local controller loop; 10-case suite |
| Only typed transient failures retry | PASS at post-poll boundary | Explicit transient consistency, timeout/connection types; generic failures not string-classified |
| Policy/evidence/graph/programming failures remain fatal | PASS for tested post-poll failures | Negative exception tests; F5 separately shows an older classifier accepting invalid pending evidence |
| No repeated provider/architect/selection/lease/checkout/launch in retry | PASS | Retry encloses snapshot only; exact poll/side-effect counters in behavioral paired cases |
| Counter bounded; only coherent success resets retry sequence | PASS | Local post-poll failure count not reset by intervening successful admission reads |
| Exhaustion records error before drain | PASS | Error journal/timeline and autonomous wake tests |
| Drain retains gate queue and recoverable workers | PASS in tested lifecycle | No kill/lease-steal or queue erase; bounded drain records surviving workers |
| Restart consumes authorized durable waiter once | PASS, preservation coverage | Five restart cases pass before and after the correction; not causal red/green evidence |

### Poke and scheduler lifecycle

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| Poke advisory; durable state authoritative | PASS | Fresh Issue/gate checks precede launch |
| Poke plus polling cannot duplicate launch | PASS | Loopback barrier/event tests and retained assignment checks |
| Poke while draining cannot claim task resumed | PASS for admission behavior | Drain does not launch; wake telemetry denotes a hint, not resumed ownership |
| Later restart can consume retained wake | PASS | Queue survives stopped listener; new scheduler launches once |
| Saved routing bypass requires valid identity/source/policy/provider/authorization | PARTIAL | Contract/Issue/checkout/source ancestry/current policy/allowed-provider route revalidated. Live credential/quota availability is not proven; prior run ID is syntactically checked, not independently bound by workflow history |
| Invalid saved route falls back safely | PASS for tested evidence changes | Nineteen gate-resume cases cover corrupt/missing receipts, identity/source/policy/feedback/health changes and prelaunch withdrawal |

### Public boundary and equivalence

| Required invariant | Result | Evidence / qualification |
| --- | --- | --- |
| No actual private repository identity introduced | PASS within inspected source identifiers | Expanded scan across all three added commits has zero matches |
| No live Issue 113/114 body/comment/URL/path/worker/delivery evidence copied | PASS within inspected incident tokens | 42 private tokens, 251 unique changed path/blob pairs, zero matches; no incident report/fixture shipped |
| Historical fixture invented and deterministic | PASS | Six canonical fixed-time events, invented identities and repeated fixture SHAs |
| Dynamically referenced fixture class compatible | PASS | SixEventWorkflowWriteFixture and post-poll consumer changed coherently |
| Test authority explicitly scoped, no production environment switch | PASS | Context-managed fixture constant patches restored; production does not import helper; test source selectors do not authorize production |
| Public automated allowlists closed by default | PASS | Empty production constants and early fresh/resumed synthetic-run rejection |
| No private task contracts/evidence/assets/claims/provider sessions/run artifacts | PASS for committed trees and final clone inventory | All three added commit trees inventoried; generic synthetic test literals are not actual task/artifact authority |
| Public tasks and graph metadata byte-identical to base | PASS | 197 authoritative paths preserved in every added commit; 60 task contracts |
| NSC-042 depends only on legitimate public dependency | PASS | Tasks/NSC-042.yaml retains only NSC-039; blob unchanged |
| Stable production semantics transplanted | PASS for fidelity | 278/286 production Python files match stable; four correction files plus four public controls account for differences; correctness still blocked above |
| Exact stranded-wake production delta transplanted | PASS | All four changed production files byte-identical to 11dcd130 |
| No rehearsal ancestry imported | PASS | Neither stable nor source correction is an ancestor; no source-private ancestry intersection beyond public base |

## Regression quality and red-before/green-after

Tests were inspected for observable assertions and bypassed production boundaries. The audit does not credit missing symbols/import errors as behavioral red evidence, nor a test that already passes before its claimed fix.

| Cohort and exact applicable before state | Before | Final | What it establishes |
| --- | --- | --- | --- |
| Gate application cohort, public `73fae381…` | 15 behavioral failures, 1 authorized control pass | Same 16 methods pass | Public-controller gate enforcement, host-loop behavior, release/quarantine; external writer only seeds remote gate input |
| Saved-route cohort, exact `645843740df1ae7ae2b16b3fb1e4bae2591cb7ee` | 7 methods fail (12 failure entries with subtests), 11 pass | Same 18 methods pass | Real architect-call counts and prelaunch proof rechecks; exact parent of routing fix `33a4decb9189a2c9232938a8a19f6540de86d393` |
| No-label workflow, public `e5eb662…` | 28 pass, 7 assertion failures, 1 real workflow error across 36 cases | 36 pass | Positive pending cases and queue read actually change; negative controls mostly preserve behavior |
| Post-poll observation, public `e5eb662…` | 4 methods pass, 4 fail (6 failure entries including subtests), 2 raise actual timeout-derived errors | 10 methods pass | Incident run, bounded retry counts and one/two-timeout recovery. New-exception-type-only assertions are not standalone behavioral proof |
| Restart recovery, public `e5eb662…` | 5 pass | 5 pass | Preservation only; does not demonstrate a correction |
| Public authority, stable `bb560d0e…` | 3 fail | Same 3 pass | One default-policy invariant and two actual fresh/resumed CLI refusal-order behaviors, using exact stable production modules |

Historical compatibility exclusions are explicit: the paired gate cohort omits two synthetic-policy cases whose framework is absent from public base; the paired route cohort omits one end-to-end case that imports a fixture renamed during public sanitization. Their complete final suites still pass. The eleven route controls that pass both revisions are preservation evidence. Exact production modules remain unchanged; existing test-only source selectors choose the historical checkout. See [paired gate runner](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/paired_gate_regressions.py), [paired route runner](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/paired_route_regressions.py), and [gate contribution](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/gate-audit-contribution.md).

Not every behavior-changing test across the 236-file transplant has a before-state execution. The paired cohorts prove the named gate, pending, retry and public-authority changes; they are not blanket red/green certification of all provider/session/orchestration changes.

Important test limitations:

- Committed closed-prefix pending tests call `_snapshot` directly and miss the bulk/per-task prefilters in F3.
- The committed incident post-poll test uses a fake scheduler poll, so it cannot expose the real gate migration fence in F2.
- Restart fixtures normally stub reservation observation. The independent F2 reproduction substitutes the actual production observer while retaining real scheduler and Git gate behavior.
- Some low-level window fixtures deliberately bypass controller construction; those do not prove installation of publication guards. F1 uses normal construction and the actual merge/check/guard/receipt path.
- Fake providers, architects, Unity/check results and worker processes are appropriate external boundaries, but do not prove their live behavior. The main-race fake backend explicitly implements the supplied head-only publication semantics and a controlled competing main write.
- CI source/registration checks support registration claims, not concurrency or runtime correctness. F7 demonstrates why merely defining an assertion is insufficient.

## Executed tests and commands

**35 committed test scripts passed: 693 named top-level case executions, zero failed scripts.** Subtests/parameter combinations are not added as extra cases. Separately, public TaskGraph validation passed, and two omitted CI guards passed when called directly. Paired reruns and adversarial probes are separate below.

All script paths in this table are relative to the exact isolated clone. Each was executed as `python -B <script>` with Python 3.13.1; this is an execution record, not a new operator mutation command.

| Script family / filenames | Named cases | Result |
| --- | ---: | --- |
| TaskReviewAgent: integration_gate, integration_window, integration_gate_base_regression, gate_resume, mainline_reintegration | 14 + 10 + 18 + 19 + 8 = 69 | PASS |
| TaskReviewAgent: pending_workflow_write, post_poll_observation_budget, gate_restart_recovery, autonomous_gate_wake | 36 + 10 + 5 + 6 = 57 | PASS |
| TaskReviewAgent: issue_workflow, actor_authorization, pending_transition_label_event | 46 + 12 + 19 = 77 | PASS |
| TaskReviewAgent: polling_orchestrator, production_graph_snapshot, autonomous_graph_run, autonomous_graph_cli | 133 + 6 + 34 + 5 = 178 | PASS |
| TaskReviewAgent: contention_retry, downstream_resilience, durable_checkout | 16 + 10 + 9 = 35 | PASS |
| TaskReviewAgent: execution_routing, execution_session_pool, supervisor_session_pool, decomposition_session_pool | 35 + 16 + 21 + 10 = 82 | PASS |
| TaskReviewAgent: codex_architect_session_pool, architect_session_owner, supervisor_provider_selection | 9 + 27 + 12 = 48 | PASS |
| AgentRuntime: durable_session_pool, provider_session, session_lifecycle | 13 + 23 + 14 = 50 | PASS |
| ExecutionCrew: session_pool, pooled_run_crew; TaskDecomposition: pooled_decomposition | 37 + 17 + 17 = 71 | PASS |
| TaskReviewAgent: public_synthetic_authority, ci_workflow_split, git_identity_guard | 10 + 12 + 4 = 26 | PASS |

Filenames above end in `_smoke_test.py` except `integration_gate_base_regression_test.py`. Exact paths/argv and per-script logs are retained in [root execution records](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/root-elevated/results.json), the gate/workflow contributions and [public execution records](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/test-results.json).

Additional executed checks:

- `python -B Pipeline/TaskGraph/taskcontrol.py validate`: exit 0; 60 active contracts, 59 parent edges, 106 dependency edges, 8 resource groups and 17 project requirements; valid connected/acyclic hierarchy and acyclic dependencies; autonomous dispatch disabled.
- `git diff --check 73fae3818ded52eec10e12230de7403cafda4081 HEAD`: exit 0, no output.
- Compile each `git diff --name-only --diff-filter=ACMR <public-base> HEAD -- '*.py'` file with Python `compile(read_bytes(), filename, 'exec')`: **206 changed Python files**, success, no bytecode written.
- Repeated `git rev-parse HEAD HEAD^{tree}` and `git status --porcelain --untracked-files=all`: pinned HEAD/tree and empty status before/after meaningful suite groups. Ignored-path inventory was also empty at the final public scan.

Independent desired-behavior probes at final HEAD:

| Probe | Outcome |
| --- | --- |
| Main publication race | 1 assertion failure, F1 |
| Real pending-plus-delivery scheduler | 1 assertion failure, F2 |
| Independent workflow assertions | 7 cases: 2 controls pass, 5 fail; three underlying findings F2/F3/F5 |
| Missing/malformed durable queue | 3 cases: 1 control pass, 2 fail; F4 |
| Actual subprocess exits before/after local publication | 2 passing crash-safety cases; fresh gate/window instances reject replay and successor |
| In-memory CI prefix mutation | Registered command falsely passes; omitted guard rejects; F7 |

There are **nine failing desired-behavior assertions across the first four probes**, not nine distinct defects. No assertions were weakened and no production fixes were made. Scripts, logs and local fixture locations are linked with each finding.

The first sandboxed Git clone failed in Git's shell helper; scoped escalation completed a local-only clone. Several sandboxed filesystem tests failed during temporary-directory setup/cleanup with Windows access errors. Those logs are retained and excluded from product failures and red/green evidence. Exact unchanged suites then passed with scoped execution outside the sandbox and temporary roots under the evidence directory. The root runner restricts Git to file transport. No external service was contacted. The main-race harness initially had two fixture precondition problems; after the repository's required independent read-only runner review, its fake check data was corrected to an explicit successful check. Only the reviewed final run is credited.

## Deterministic concurrency coverage

| Requested interleaving | Evidence / outcome |
| --- | --- |
| Two workers contend for one slot | Separate processes and real local Git CAS; one owner |
| Owner crashes before publication | Durable owner/unfinished operation retained; no automatic successor; explicit fenced recovery tested |
| Publication succeeds before receipt persistence | Child performs real local main update then os._exit(17); reconstructed gate/window blocks exact-run replay and competing successor, even with clock advanced to 2099 |
| Stale owner completes | Identity/receipt/OID checks reject foreign or stale settlement |
| Duplicate pokes | Event/loopback tests plus fallback poll preserve one assignment |
| No-label proven transition | Fixed canonical human and synthetic fixture histories; classifier passes; F2/F3 expose consumer failures |
| Repeated stale observations until expiry | Frozen/advanced clock anchored to original evidence; 600-second limit |
| Post-poll failures below/at limit | Same-poll observation counters and fatal exhaustion; no repeated paid or launch operations |
| Restart with one authorized waiter | Five real scheduler/local-gate cases; one launch, durable queue retained |
| Invalid saved routing proof | Receipt/source/policy/authorization negatives fall back or withdraw before launch; gate-resume suite |
| Main changes between validation and publication | Controlled fake transport boundary and real local competing commit; F1 fails |

Barriers, controlled call boundaries, event state and injected clocks establish these interleavings. Timing-only sleep is not the primary correctness oracle. Timeouts bound hangs, and normal polling/wait behavior remains where part of a tested lifecycle.

The independent [crash harness](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/crash_publication_repro.py) and [log](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/crash_publication_repro.log) preserve both subprocess-exit boundaries. They use real production gate/window storage with a minimal controller shell and real local Git publication; they do not simulate a complete live GitHub merge service. The remote main OID remains unchanged after the attempted restart.

## Public leak and ancestry audit

All three added commits were inspected, not only final working files. The expanded scan covers **251 unique changed path/blob pairs and 42 extracted private identifiers** with **zero matches**, excluding explicitly authorized public/base/source boundary references. No concrete private identity or live incident content is reproduced in this report. This is an exact-token/artifact audit of the available source material, not a claim to detect every possible paraphrase of unknown private information.

All **197 authoritative public task/evidence/graph metadata paths** remain blob-identical to base in each added commit. There are no imported private task contracts, evidence, assets, claims, sessions or generated-run artifacts. Generic fixture IDs/examples remain data in deterministic tests. `NSC-042` retains only `NSC-039` as dependency. The public validation-policy task entries remain unchanged; the additional decomposition-template map is empty.

Of **286 production Python files** compared with the stable boundary, excluding tests and the visualizer, **278 match byte-for-byte**. Four differences are exactly the stranded-wake correction: `autonomous_graph_run.py`, `issue_workflow_store.py`, `polling_orchestrator.py`, `production_graph_snapshot.py`. The other four are narrowly public authority controls: empty synthetic constants, no default private destination, early fresh/resumed synthetic-run rejection, and runtime default lookup compatible with scoped fixture tests. No other gate, routing or session algorithm differs from stable. This proves transplant fidelity; F1–F6 show why fidelity does not prove correctness.

Neither the stable rehearsal boundary nor source correction commit is reachable from the public integration as an ancestor. The source-only ancestor intersection beyond public base is empty. Detailed evidence: [public boundary report](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/PUBLIC_BOUNDARY_AND_EQUIVALENCE.md), [boundary summary](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/boundary-summary.json), [incident scan](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/incident-token-scan.json), [all-commit artifact inventory](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/history-artifact-summary.json).

## Remaining uncertainty and release requirements

No live GitHub namespace semantics, branch protection, cross-host network routing, real provider availability, Unity execution, paid calls or real production process crash was exercised. The gate safely declines to steal an uncertain owner; automatic unattended bounded recovery after a hard crash is not provided. Explicit recovery requires fencing old processes and proving remote outcomes, and these operator steps have no guaranteed completion time.

Saved route reuse validates policy-allowed providers, not live quota/credentials. Full provider/session change history was exercised with final-state regression suites, not paired before-state tests for every change. The compatible paired cohorts and their exclusions must not be advertised as red/green proof for every behavior-changing regression in the entire transplant.

The report requires F1–F3 to be corrected and reproduced through the same complete production paths before approval. F4–F6 also need either the stated implementation corrections or an explicit revised requirement supported by a documented safety/availability contract. F7–F8 can be handled as non-blocking follow-ups. Preserve the current failing assertions and evidence; do not suppress exceptions, relax labels, discard queue entries or add lease time-stealing to make tests pass.

Supporting analysis: [gate contribution](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/gate/gate-audit-contribution.md), [workflow contribution](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/workflow/workflow-audit.md), [public contribution](C:/NSC/PublicGateAdversarialAudit-20260907T033720Z-evidence/public/PUBLIC_BOUNDARY_AND_EQUIVALENCE.md). The audit report is uncommitted outside the isolated checkout. The integration, shared operator checkout and rehearsal checkouts were not modified.
