# Durable integration and commit gate

The Game Task Agent may implement and validate an initial candidate concurrently
with other tasks. Its final delivery window has one owner per repository and
target branch. The gate makes no architect, supervisor, Claude, Codex, or OpenAI
call. Existing path-conflict reservations, Issue leases, checkout isolation,
required CI checks, and exact-commit validation remain separate requirements.

## Why delivery previously repeated work

`ResumableDownstreamTaskController` routes a validated delivery task through
`integrate_current_main`, authoritative Unity validation, evidence publication,
pull-request checks, merge, and post-merge verification. The reintegration
extension refreshes main again immediately before the PR merge. A newly changed
main correctly invalidates the previous exact-commit validation and evidence.

Previously, independent workers could all enter this sequence against the same
main commit. If three tasks all completed validation/CI before the first merged,
the remaining tasks could do 1, 2, and 3 cycles. Every check was locally correct;
the missing constraint was ownership of the entire final delivery window.

The gate is acquired before the authoritative main refresh. The existing
reintegration machinery still merges main into the task branch, invalidates old
evidence, and requires validation of the new commit. Evidence packaging may add
an evidence-only commit under the existing policy; the PR head must be exactly
that evidence commit, bound to the exact validated implementation commit/tree.
The gate does not reinterpret an evidence-only commit as a new human PASS.

## State and ownership

```text
durable eligible Issue event -> queued (ready UTC time, then task ID)
queued -> held                 one exact remote-ref CAS
held -> held                  confirmed operation/progress; same lease identity
held -> free + wake next       verified closeout or quiescent settlement receipt
held -> quarantined           interrupted/uncertain operation; no successor
quarantined -> free + wake     explicit fenced recovery receipt and exact-OID CAS
queued -> withdrawn            verified human/blocked/complete Issue event
```

Schema version `1.0` is independent of the existing Issue/downstream schemas.
The journal ref is
`<activated-claim-namespace>/integration-gates/<sha256(canonical-domain)>`.
The domain hashes canonical JSON `[repository_identity, target_branch]`.
GitHub HTTPS, SSH URL and SCP origins resolve to lowercase
`github.com/owner/repository`. Branch names remain case-sensitive. Local bare
repositories use resolved absolute file URIs for deterministic offline tests.
Checkout paths, providers, task IDs, worker IDs and controller IDs are not part
of the production integration domain.

Each parent-linked journal commit stores:

| Field | Meaning |
| --- | --- |
| `schema_version`, `repository`, `target_branch`, `revision` | Versioned domain identity |
| `queue` | Unique task IDs, original ready time/event hash, advisory wake endpoints, optional exact Issue/contract/resource reservation and waiter quarantine disposition |
| `owner` | Null, or the exact lease record below |
| `event` | This immutable transition, timestamp, previous OID, and applicable receipt |

The owner records `lease_id` (random UUID), `task_id`, `run_id`, `worker_id`,
`repository`, `target_branch`, `acquired_at`, `heartbeat_at`, `status`,
`progress`, `operation` (kind/start time), `unity_seconds`, and `ci_seconds`.
The local owner handle is stored outside the checkout under
`.task-review-agent/integration-owners/<domain>/<run-worker-key>.json`.
It is only a handle: every operation requires the matching remote owner.
A partial/mismatched handle fails closed. Repeated exact-owner admission is
idempotent; an unfinished operation must be reconciled before retrying.

Queue registration, acquisition, progress and release use remote Git
compare-and-swap, reusing the claim primitive's guarded automation identity and
precise rejection classification. The branch/index/worktree are not used for
journal commits. Each update preserves the complete previous history as its
parent. Release stores its exact owner-bound receipt and successor wake intent
in the same transaction; a subprocess exit code is never a receipt.
Completed settlement also requires the verified final Issue event to name this
worker and the same merged commit as its closeout artifact. A copied journal
with severed Git ancestry is rejected, even when its JSON is otherwise valid.

Queue/acquisition contention returns a nonfatal deferred result. Owner updates
retry only proven CAS contention, at most four attempts; transport uncertainty
does not trigger a blind replay. No process-local or machine-wide file mutex
provides integration authority. The normal ephemeral claim inspector excludes
the explicitly named gate subtree; stale-claim deletion rejects it. Existing
task/resource claims remain observable, while the gate has its own reader and
structured scheduler events.

## Delivery, waiting and wake-up

The production scheduler registers the eligible delivery set before selecting
its oldest waiter from that controller's authorized set. An older waiter owned
by another run scope stays durable but cannot strand an unowned gate: the
current controller may select its own oldest authorized waiter, and the gate's
remote-ref compare-and-swap still permits only one owner. It filters occupied/
queued delivery tasks before the existing architect selection. Implementation
and ExecutionCrew work remain parallel and keep all existing admission checks.
Workers independently repeat gate admission, so a second controller cannot
bypass the remote-ref arbiter.

`integration_gate_waiting` is worker status `blocked`, exit `3`, with the normal
identity-verified `run_result.json`. It does not increment the fatal counter.
The gate is outside the provider action menu, so a wait never buys a supervisor
turn. It does not loop internally until admission succeeds.

One UDP listener per controller signals its existing worker-completion event
for the whole pending set. Waiters persist listener endpoints in the journal.
Release immediately sends the next task's advisory wake, including to independent
controllers/hosts. The default production address is the host's resolved IPv4
interface; `NSC_GATE_WAKE_HOST` may select a reachable local interface. Routers
and firewalls must allow the advertised datagram endpoint for immediate remote
wake delivery. Lost datagrams, a dead listener or a crash after the release CAS
are recovered by the existing bounded scheduler fallback poll. Datagrams grant
no task authority: every wake is followed by fresh durable-state checks. A
separate pending event closes the scheduler clear/wait race.

Fairness applies to the registered eligible set. Timestamps are parsed as UTC
instants and equal times use the task ID. A task becoming eligible after another
has acquired cannot preempt the owner. Registration is idempotent and keeps the
original ready event rather than resetting priority on every controller poll.
Missing or malformed queued Issue authority receives a durable waiter quarantine,
never an inferred completion or withdrawal. Host reconciliation runs before the
default scheduler and coherent-snapshot workflow readers. Stage 2 retains its
known resources as an unresolved reservation; the task cannot be selected or
reinitialized. Unknown or empty resource ownership blocks admission. Known,
nonempty disjoint resources permit the existing architect disjointness review;
the final gate independently checks those resources again. Conflicting waiters
remain queued while a proven-disjoint waiter may proceed. FIFO is retained
within each controller's authorized admissible set. Waiters outside that set
retain their original ready time and position for a controller that can run
them, but they do not create a global liveness dependency. A held owner always
blocks every other waiter regardless of scope, and quarantined entries are
never silently removed.

Reappearance clears quarantine only when the original ready event remains in
the validated history and the exact Issue number, committed task-contract hash,
and reserved resources match. Identical reconciliation is a no-op. An unbound
replacement Issue or a legacy entry with unknown ownership requires explicit
operator investigation; automatic admission cannot establish the missing facts.
A verified human/blocked/complete transition can withdraw a reconciled waiter
without deleting its history.

A cryptographically proven pending workflow write is a bounded delivery wait at
the legacy-owner fence, preserving the queue and resources without buying an
architect or worker turn. Closed completion prefixes reach full-history
classification before duplicate filtering. Even a COMPLETE body retains resources
while its final label write is pending. Expired proven writes follow the existing
fatal corruption policy; quarantine never renews their allowance.

## Human and automated validation

This public distribution leaves the synthetic repository allowlist empty and
rejects synthetic run enablement. The automated extension described below is
retained for deterministic component tests; it supplies no public-task approval.

An actual `human_action_required` wait releases the gate after the durable Issue
handoff is verified. On return, the task queues/acquires again and refreshes main.
Any newly integrated commit needs new exact-commit approval. Human PASS is never
fabricated, carried across commits, or derived from automated evidence.

When the existing exact authority is automated, the worker retains the gate
across bounded reintegration validation. It calls the existing private synthetic
validator for that one task, with the exact gate owner. The normal repository,
private-gauntlet lineage, NSC-042 exclusion, policy, runner identity, commit/tree,
artifact hash and Issue-event checks still apply. The independent autonomous
pump excludes the gate-owned task. The worker reimports the new manifest using
the newly recorded event's exact hashes and the normal evidence publisher,
preventing a second Unity run on the same integrated commit. This is automated
authority only; no `human_result` is created.

For the existing thousand-profile `SyntheticSource` policy, an exact gate-held
validation operation may obtain fresh source evidence after integration using
the existing trusted constant/sidecar validator. Repository, task, policy,
runner bytes, commit/tree and artifact checks still apply. Ordinary ungated
handoffs retain the pre-handoff-evidence requirement. Source checks record a
`source` operation, never a Unity execution or human PASS. The regression proves
one exact source task; it does not establish thousand-task throughput.

The existing Unity timeout and bounded CI wait bound ordinary automated work.
The gate stays held throughout those operations. A CI wait timeout with a
verified quiescent Issue release can release the gate; a later run reacquires
and rechecks main. This recovery path may need another validation cycle if main
advanced. The one-cycle expectation assumes operations finish within their
bounds and no external main writer intervenes.

## Failure, interruption and recovery

| Situation | Gate policy |
| --- | --- |
| Verified post-merge main and Issue closeout | Persist completed receipt, release, wake next |
| Real human wait | Persist quiescent receipt, release, wake next |
| Returned test failure or known failed CI checks | Verify Issue relinquishment, persist failure settlement, release |
| Deterministically handled merge conflict/blocker | Preserve existing conflict/evidence handling, settle at the durable blocker |
| Provider failure between completed operations | Relinquish exact Issue lease and gate with quiescent receipt |
| Unity/CI/process timeout with uncertain subprocess survival | Quarantine; reconcile processes and remote state |
| Interrupted or ambiguous merge/post-merge operation | Quarantine; never authorize a successor from exit zero |
| Hard worker/controller crash | Owner/operation remains visible; no automatic reaping |
| Owner identity, receipt, schema, Git or Issue corruption | Fail closed with exact ref/identity diagnostic |

There is **no TTL, automatic stealing or automatic stale-owner deletion**.
An hour-long Unity run or CI wait cannot lose ownership merely because time has
elapsed. The prior ephemeral/resource reservations are not cleared by gate
recovery, and immutable evidence and logs are preserved.

Recovery is an explicit host/operator operation, never a provider decision.
First read `GitIntegrationGate.read()` and preserve the exact ref OID, owner,
run/worker records, Issue history, operation logs, task branch, PR/check state and
main. Fence all old worker/controller/subprocess execution capable of publishing;
reconcile any in-flight GitHub merge or branch push to a definite outcome. An
unknown outcome remains quarantined. Repair the Issue through its normal workflow
so the next run has coherent authority. Then `recover(expected_oid=..., receipt=...)`
requires the exact owner identity, schema `1.0`, status `recovered`, the verified
Issue event hash, verified main SHA, `processes_fenced: true`,
`remote_operations_reconciled: true`, and the preserved `operator_evidence`
reference. This is an explicit attestation of performed checks, not evidence
inferred from timestamps, a missing PID, or a zero process exit. A moved ref
rejects the recovery. The recovery decision and receipt remain in the journal.

## Compatibility and rollout

Old Issues and run files remain readable; their schemas are unchanged. An old
`agent_ready` run joins the gate using its verified current event. An active
downstream Issue worker without a matching gate owner is a legacy/uncertain
reservation and stops admission. Fence and reconcile that worker and relinquish
its Issue lease before resuming under the gate. Do not run old and new delivery
binaries concurrently: older code cannot enforce a gate it does not know about.
An unknown gate schema refuses admission rather than initializing another owner.

The gate coordinates participating Game Task Agent delivery workers. A human,
administrator, D1C graph publisher, or other external main writer can still move
main; the existing pre-merge ancestry, exact PR-head, required-check and
post-merge checks remain necessary and unchanged. No force-push to main and no
required-check bypass is introduced. Independently targeted branches and other
repositories use distinct domains.

## Evidence and expected cost

Journal events cover eligibility/queueing, acquisition and wait duration, owner
identity, confirmed progress, release/reason/receipt, successor wake intent,
withdrawal, quarantine and recovery. Scheduler events include
`integration_gate_observed` and `gate_next_waiter_woken`. Releases report
gate-held Unity seconds, CI seconds and total integration-window seconds.
No prompt, credential or provider token is logged.

The real-local-Git simulation reproduces `[1, 2, 3]` cycles without the gate and
`[1, 1, 1]` with it. The corresponding worst aligned ten-task schedule is
55 cycles versus 10 (45 avoided, about 82%); three tasks avoid 3 of 6 cycles
(50%). These are workload counts, not measured production wall-clock savings.
Initial implementation/provider work is unchanged. Gate operations use zero
provider tokens. Avoided delivery/revalidation/CI cycles should avoid their
associated calls/tokens, but there is no defensible token total or ten-task
runtime prediction without per-phase measurements. The serialized final window
also has Git coordination overhead and may trade idle worker time for fewer
doomed cycles.

Offline regressions use local Git repositories/refs, separate processes,
in-memory managed Issue backends, real hash-checked artifact files, and bounded
Unity/CI stand-ins. The paired base test loads the exact base application code;
the new gate writer only seeds remote input fixtures and does not patch the base
controller/loop. New protection assertions fail there while an authorized
integration control still passes. Production GitHub namespace/network behavior,
cross-host firewall routing, actual Unity duration and live token savings require
a separately authorized deployment/rehearsal. No live gauntlet is required to run
the deterministic tests.

## Regression map

The portable `integration_gate_base_regression_test.py` runs the same assertions
against the candidate or a separate exact-base checkout selected by
`NSC_GATE_TEST_SOURCE`. Its gate writer seeds remote test input only; it never
patches base controller methods, the host loop, or the Issue state machine.
Seventeen regression cases fail on base
`7749a37dd606621515bc2ed25048558f026660d2`; all eighteen cases are green on the
candidate. The eighteenth is an unchanged authorized-integration control.

| Requirement | Behavioral evidence |
| --- | --- |
| A, E | Separate local clones/processes contend for one remote ref; base public controller enters without ownership, candidate refuses |
| B, Q | Real Git schedule reproduces `[1,2,3]` exact validation/CI cycles before the gate and `[1,1,1]` after it |
| C, K | Base human handoff leaves seeded ownership/no wake; candidate verifies handoff, releases and delivers UDP wake; primitive test wakes task 2 then task 3 |
| D | Base host ignores equal-time older task ID; candidate returns waiting without a provider turn |
| F | Repository/branch independence is a compatibility invariant; distinct gate domains acquire concurrently |
| G | Existing resume compatibility is retained; exact run/worker/lease resumes idempotently, an unfinished operation stops |
| H, I, J | Base ignores mismatched worker/run/lease, long-running operation and quarantine; candidate refuses entry; primitive tests reject foreign/missing receipts and require explicit fenced recovery |
| L | Base host returns a human wait after automated reintegration; candidate reaches the bounded validator while holding the exact lease; runtime test imports new commit/tree/hash-bound output and retains ownership through CI. Base source validator refuses missing pre-handoff evidence; the gated candidate produces a new exact source manifest and hashed machine event |
| M | Base host leaves seeded gate untouched on provider failure, interruption and closeout; candidate settles ordinary failure/verified closeout and quarantines interruption; runtime tests exercise test/CI failures and uncertain merge |
| N | Base waiting case makes fixture-provider decisions; candidate makes zero; scheduler tests filter the pending set before the architect |
| O, P | Authorized single-task behavior, reintegration, invalidation, exact human/automated authority and required-check tests remain green; synthetic acceptance runs the production admission and worker boundaries |

The distinct-domain, same-owner-resume and existing-safety cases are preservation
tests, not claimed pre-existing defects. The cycle simulation is a deterministic
schedule model using real Git, not a live Unity/CI timing benchmark. The three
new scripts contain 42 tests (14 gate, 10 runtime, 18 paired application cases).

The public integration is tested against its exact public base separately.
Historical rehearsal test results do not establish the public branch's result.
