# Current handoff — 2026-09-10

Vincent controls task work through conversation. Use `python -m Pipeline.AssistantControl`;
the viewer is read-only. `README.md` describes commands. `STATUS.md` is a historical
development log; earlier limitations there may have been fixed by later entries.

## Implemented and focused-tested

- Inspect committed tasks, dependencies, capacity and resource conflicts.
- Prepare independent Git/Unity task projects and register explicit scopes.
- Launch explicitly authorized workers; stop exact worker trees; settle capacity.
- Verify crew artifacts, commit candidates, and preserve separate receipts per run.
- Authenticate and summarize retained crew result/patch bytes without mutation.
- Materialize Door Prototype assets and run the committed task-specific Unity
  validation before asking Vincent to inspect the exact resulting commit.
- Chain candidate registration and, where a Unity builder is registered,
  materialization into one bounded `post-crew` command for the orchestrator,
  returning `NEEDS_MATERIALIZATION` or `validation_failed` with the exact next
  command instead of retrying or approving anything itself.
- Record Vincent's exact-commit approval or rejection. Re-observation keeps decisions.
- Revise rejected work without discarding it, including fresh feedback after a merge.
- Synchronize Source into candidates repeatedly, preserve history and recover interrupted
  publication. Every changed candidate needs a new test decision.
- Integrate approved commits locally, preserve existing edits, and retain successful
  task projects. No automatic push or production publication.
- Plan and resume an explicit bounded task graph through the existing checkout,
  worker, candidate, validation, decomposition, review, and local-integration
  components. Transitive prerequisites and decomposition descendants are included.
- Auto-approve only authenticated synthetic Gauntlet candidates after their exact
  focused validations pass. NSC-042 always stops for Vincent's visual approval.
- Run a restricted `--delegate-safe` subset for cheaper helpers. It permits only
  portable checkout preparation/refresh and exact scoping, stopping before
  reservation, provider/Docker/Unity work, receipt processing, graph mutation,
  approval, synchronization, or integration.

The tests use disposable real Git repositories, fixture providers, and some real
Windows child processes. They do not prove paid-provider behavior or Unity visuals.
The post-crew, materialization and viewer path has 23 passing focused tests,
including unavailable-Unity recovery without a second crew candidate. The existing
production candidate-integration suite has 6 passing smoke tests.
Failed materialization tests now block approval and can enter the existing fresh
revision path with their exact failure text; the 13 admission/revision tests pass.
Recent parent results: synchronization 12 passed; fresh-feedback bridge 4 passed;
revision completion 2 passed; separate receipt/re-observation 2 passed. Exact timings
and fixture boundaries are in the final sections of `STATUS.md`.

## Actual project state

Source: `C:/NSC/TenTaskFinalIntegration-20260905`. Vincent's uncommitted generator,
architectural tiles and scene changes must remain untouched.

Task checkout: `C:/NSC/TenTaskFinalIntegration-20260905-AssistantCheckouts/NSC-042`,
branch `assistant/NSC-042`. Its current committed Source binding is
`57b32e84b020bd4c54b70aa8948c4409680ae4ee`. A real Claude crew was launched through
the assistant controller and rejected after reaching its turn limit. That worker is
settled and retained. The known-good restoration was mechanically synchronized with
the latest committed controller history. The exact candidate is
`1fdb2918af4daaf478232b9790b39fa8bb7989cd`; it retains the restored candidate as
lineage, is marked `crew_review: false`, and awaits Vincent's visual test. It is not
approved, integrated or published.

Known good reference: `C:/NSC/SuccessfullTasks/NSC-042`. Preserve it. Read
`Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md` before creating or revising game tasks.

## Finish the goal

1. The actual launcher/runtime and rejected result have been demonstrated in a
   separate Unity checkout. Keep later provider work explicitly authorized.
2. Vincent tests exact candidate `1fdb2918af4daaf478232b9790b39fa8bb7989cd`
   and explicitly approves or rejects it. Integrate
   only an approved commit after resolving any Source working edits with him.

Retaining a conflicting merge safely is supported. An automatic conflict resolver,
decomposition is an explicit assistant operation: a two-role proposal remains
read-only until its exact independently reviewed plan is applied locally. GitHub
publication remains outside this controller.
Do not mark the goal complete from fixture approvals or add these as new blockers.

## Budget pause and Claude handoff — 2026-09-10

Vincent requested conservation of Codex usage and more work by Claude. Do not launch comparison crews or more helpers automatically. Both comparison setups under C:/NSC/AssistantControlEvidence/042-ab-20260910 remain unlaunched; comparison heartbeat is PAUSED. Vincent has the read-only log-analysis prompt to pass to Claude. Await that report before another experiment.

Observed: successful and recent implementer starting generator blobs are identical (SHA256 7c741147a4479102e0b5ced706afa2a60d3f5b334c4d156e33d60a9c54a0e498). Successful implementer made 21 calls; recent made 99, 90 aimed at WallTile.asset, ending error_max_turns. Historical one-attempt receipt does not prove first-ever success; earlier implementation 2a486123 is mentioned in preserved historical notes but its object was not found in the recovered clone. Do not infer model degradation or missing configured roles from this.

Separate demonstration checkout now contains reference generator/tests plus Unity-regenerated wall/scene. Three focused Unity tests passed; regenerated Texture2D pixels match recovered reference. This is an assistant restoration, NOT an independent crew success. See AssistantControlEvidence/crew-comparison/042-restored-verification.md. Incidental Unity changes were subsequently archived to 042-unity-incidental and excluded; four intended paths remain changed. No approval/integration/publication.

Controller repairs now include named Windows-job handle handoff, JSON provider-list conversion, and rejected-crew status and settlement. Real rejected run assistant-042-demo-20260910-four is settled, status failed, and capacity released. `register-restored-candidate` is wired into the common CLI and the viewer distinguishes `assistant_restored` from crew-reviewed work. Focused restored-candidate, settlement, launcher and Windows-job tests pass. Do not fabricate a reviewed-crew receipt.

Full AssistantControl audit: 145 tests passed in one discovery run. Four recovery
tests exposed a Windows-only fixture error that embedded CR as trailing whitespace
in generated patches; production correctly rejected those patches. The fixtures
now write LF-normalized bytes, and all four affected workflows pass on rerun. No
provider or GitHub operation was invoked by this audit.

Candidate synchronization also accepts an exact unreviewed `awaiting_human`
candidate when Source advances before Vincent's first test. It creates a mechanical
merge, grants no approval, and presents the new exact SHA for testing. Rejected or
otherwise advanced candidates remain ineligible. The source-sync suite and focused
authorization/recovery reruns pass.

The NSC-042 authoritative validation policy previously selected the unrelated
`GauntletTests` class. It now selects `DoorPrototypeSceneBuilderTests`, including
the repeating-pattern and stale-texture checks. Running the builder alone is not
acceptance: these tests judge deterministic behavior, and Vincent judges appearance.

The `readiness TASK` command now gives the assistant one compact, read-only answer
for dependencies, checkout/scope state, capacity, resource owners, and conflicting
Source edits. Its eight focused admission tests pass. On the current NSC-042 it
correctly refuses another worker because the candidate already awaits Vincent and
Source has edits to the builder and scene; it did not mutate either project.

## Windows materialization experiment — 2026-09-10

The controlled project `C:/NSC/NSC-042-BuildComparison` retained the fixed
generator/tests while its `WallTile.asset` and `DoorPrototype.unity` were restored
to the pre-fix commit. Vincent observed the bad wall, manually ran
`DoorPrototypeSceneBuilder.Build`, and then observed the fixed wall. The Build
changed 3,180 of 10,240 texture pixels; the resulting texture payload had zero
pixel differences from the preserved correct payload. Evidence is retained under
`C:/NSC/AssistantControlEvidence/NSC-042-build-comparison`.

Raw files did not compare byte-for-byte because Unity reassigned local YAML object
IDs and serialization order. Build also touched registered and incidental generated
files. The owned materializer must continue restoring unregistered tracked output
and judging semantic results/focused tests instead of using raw Unity YAML hashes.

The intended operating loop is now explicit: a Linux crew changes source and
focused tests; the assistant invokes Windows `materialize-candidate`; Windows Unity
runs the builder and exact-commit tests; source failures become compact retained
feedback for a bounded crew revision; Unity availability failures stop at
materialization; Vincent sees the exact candidate only after automated checks pass.
No retry launches implicitly, and no Build result grants human approval.

The individual commands already implement these stages. `post-crew` now joins
authenticated candidate registration and, when a Unity builder is registered,
materialization into one bounded step for the orchestrator to call after a crew
run ends, while preserving the existing explicit provider, review, integration
and publication boundaries. See its entry in `README.md`.

## Checkout-lock contention is deferred, never fatal — 2026-09-13

`checkouts.lock` serializes every record transaction in one checkout root, and
its legitimate holders are slow: in the 20260913 Gauntlet run a post-crew child
held it about 9 s registering its candidate and a foreground `sync_candidate`
held it 13-16 s, while every waiter budgeted 10 s. Four transactions lost that
wait in 22 minutes. Three were controller actions (`post_crew` launch,
`sync_candidate`, `auto_approve`) and each ended its invocation: the task was
marked `blocked`, `last_error` recorded the `TimeoutError`, and the CLI exited 1
(`TimeoutError` is an `OSError`, so `python -m Pipeline.AssistantControl` reports
`command_failed`). The fourth was a post-crew child, whose own lost wait is
journaled `job_failed` from its receipt, blocks only its task with
`background_job_failed` and needs an operator `clear-background-job` before the
planner will issue another ticket; two children died that way, and 75 s and 126 s
of finished Unity validation were thrown away with them.

Both sides are repaired. A controller action that cannot take the lock *before
it has written anything durable* is now deferred to the next planning cycle
instead of failing the invocation: `action_deferred` is journaled with the task,
kind, reason `lock_contention`, the lock path, the seconds waited and the
deferral count; the task is not blocked, no `last_error` is written, the
invocation stays `running`, the loop pauses a bounded three seconds and the
planner re-emits the action naturally. Only kinds whose lock acquisition provably
precedes every durable write are deferrable (`LOCK_DEFERRABLE_ACTION_KINDS` in
`graph_controller.py` carries the proof per kind); `apply_decomposition`, which
never takes that lock, and the wait kinds, which reach it only inside `harvest`
and the container-cleanup recorders, keep today's failure path. After six
consecutive deferrals of the same action the original error is raised exactly as
before, so a wedged lock stays loud. The bound is per invocation: a restarted
controller carries no deferral state.

Inside a post-crew child, the two record transactions that used to fail its whole
job now wait far longer than the controller does, since `_exclusive_file_lock`
already retries the acquisition every 50 ms until its deadline: candidate
registration (`candidate.REGISTRATION_LOCK_TIMEOUT_SECONDS`, which has mutated
nothing when it waits) and the post-validation persist
(`post_crew_workflow.VALIDATION_PERSIST_LOCK_TIMEOUT_SECONDS`, which must not
discard evidence that already exists). Both stay bounded, and the persist still
re-verifies the exact candidate on acquisition and refuses one that changed while
validation ran. `unity_materialization.materialize_candidate` still holds
`checkouts.lock` across the whole Unity builder and validation; that is a separate
defect, recorded in `README.md` and not changed here.

## Background job containment and operator stop — 2026-09-12

Two blockers in the first background-job commit are repaired: detached
children survived an operator stop, and a receipt was accepted on its ticket
hash alone. Now every child is assigned to a run-derived named Job Object
before it may work (worker-launcher handoff; the parent keeps its handle until
the exact child acknowledges with `job.opened.json`), receipts must carry the
recorded PID and process identity, Ctrl+C writes a bound `stop.request.json`
per active job, waits a bounded cooperative grace period (a decomposition child
stops its own uniquely named provider container), then terminates only the
recorded Job Object tree; the ticket is retained as `cancelled`, never a
provider failure, never relaunched. `stop-background-jobs` recovers after a
lost controller process and refuses while a controller owns the graph.
`stop-graph` gives a console-less controller (a detached runner) a sanctioned
stop: a request bound to the running invocation, PID and process identity that
the controller honors between actions and on every wait poll, returning status
`stopped`; unbound or stale requests are archived and ignored.

## Astra round-5 repair: the cooperative stop proves ownership first — 2026-09-12

The remaining finding is closed. The decomposition child's cooperative stop no
longer runs `docker stop <name>`: `cooperative_stop` inspects the ticket's exact
recorded name with the reconciliation's own format, requires the exact name,
compose project, `-decompose` service and both ownership labels to be the ones
the ticket records, and only then stops the container by its exact id (still
`docker stop --time 10`). A mismatch, a missing or unreadable label, an absent
container, a Docker failure or a ticket that does not authenticate stops
nothing; the decision is recorded durably as `cooperative-stop.json` in the run
root and returned rather than raised, so a refusal cannot turn the child's own
`stopped` receipt into a failure. The stop takes a Docker runner seam
(defaulting to `_run_docker`) so the decision is unit-testable with the fixture
Docker, and `_ticket_container_name`/`_ticket_container_labels` remain the only
source of truth for what the child may touch.

## Astra round-4 repairs: checkout-exact container identity, refusals that keep cleanup progress — 2026-09-12

Two further findings are closed. (1) The background-job id is now derived from
the owning Source path and checkout root as well as kind, task, identity and
attempt, so two checkouts (or two clones of the same Source commit) can never
derive the same ticket id or the same provider container name; the ticket also
fixes the labels the container must carry
(`com.nosafecircle.assistant.job`, `com.nosafecircle.assistant.checkout`),
`decomposition.run` stamps them with `docker compose run --label`, the inspect
format reads them back, and a container under the ticket's name without exactly
those labels is refused and never removed. Authentication re-derives both the
job id and the labels. (2) An authentication refusal no longer overwrites a
cleanup generation that is in flight under a live owner: the owner still
records its removals, sightings and renewed deadline, and that generation lands
as `refused` with `authentication_failed` instead of being discarded, so no
retry can begin against a shortened bound. A refusal with nothing in flight
preserves every progress field and can only keep or extend the deadline.

## Astra round-3 repairs: partial cleanup progress, full identity authentication, concurrency, unreadable indexes — 2026-09-12

Four further findings are closed. (1) A Docker failure or an interrupt after
the exact container was seen or removed no longer loses it: the removal and
the sighting are recorded, the operation bound restarts from them, the final
recheck is owed again and the record stays `cleanup_pending` with
`retry_after_utc`. The bound only moves forward, so nothing can restore an
older deadline or complete a cleanup that saw its container. (2) A request
file that is missing, empty, truncated or malformed now fails the recorded
hash comparison instead of skipping it, and every destructive path also
authenticates the recorded PID, the complete process identity, the Job Object
name, the derived container name and compose project and the owned run
directory against the artifacts the run itself wrote; a mismatch records
`authentication_failed` with every problem and inspects, removes, signals and
terminates nothing. (3) A ticket cleared or superseded while its Docker work
ran unlocked is returned as a concurrency outcome and journaled
(`job_cleanup_superseded`); cleanup and harvest errors are journaled per task,
so no concurrent `clear-background-job` aborts the controller or blocks
unrelated tasks. (4) An index that cannot be read or authenticated is never
"nothing remains": `stop-graph` reports `already_released_cleanup_pending` /
`stopped_cleanup_pending` and `stop-background-jobs` reports `cleanup_pending`,
both exit 1 with the exact path and error, and a controller start refuses;
nothing is deleted or repaired automatically.

## Astra round-2 repairs: unfinished tombstones, reauthentication, ownership, stop-graph — 2026-09-12

Four findings on the previous repair are closed. A verified-inside-the-window
cleanup whose tombstone is unfinished now stays pending: every stop takes one
exact look while the bound is active, `stop-background-jobs` waits the bound
out and records the final recheck before claiming `stopped`, a controller
start does the same before its first plan, and the running loop retries
pending cleanups after their bound. Every retry reauthenticates the immutable
ticket (request bytes, task id, job id, container derivation, owned run
directory) before anything destructive and fails closed as `refused` with
`authentication_failed`, never retried automatically. Cleanup ownership is
recorded with the generation: a live owner is waited for, a dead one taken
over, and a superseded result is discarded in favour of the durable record
instead of raising into the controller's failure path. `stop-graph` after the
owner released reports `already_released_cleanup_pending` (exit 1) and points
at `stop-background-jobs`. Tests: a create after the window but inside the
bound is caught by the repeated stop and by startup; an index rewritten to
another job's ticket, a non-derived container name and altered ticket bytes
remove nothing; a superseded generation leaves the controller running and is
taken over on the next start; a live owner is awaited; repeated `stop-graph`
after release exits 1 until `stop-background-jobs` finishes.

## Astra re-review repairs: window, stop retry, lock — 2026-09-12

Three P1 findings on the cleanup above are repaired. The container name is
now watched for the whole 15 s window (removing on every sighting) and
verified only when its final 3 s were absent, with a bounded extension after
a late sighting; a kill-path cleanup keeps a 60 s tombstone (one Docker
operation bound) that `clear-background-job` waits out and follows with one
recorded final recheck, and a retry ticket is refused until the prior attempt
is finally verified. A terminal job whose container is not verified absent is
still stop work: `cancel`, `cancel_all`, `stop-background-jobs` and a repeated
`stop-graph` retry the exact bound cleanup and do not report fully stopped
(`cleanup_pending` / `stopped_cleanup_pending`, exit 1) until it is verified;
after verified success a repeat makes no Docker call. Docker calls and
stabilization sleeps no longer run under `checkouts.lock`: the cleanup is
recorded as in progress with a generation under the lock, runs without it,
and is recorded only for that generation. Tests: a create at second 4 (after
the old 3 s boundary) is removed and the window still ends absent, a
late-window sighting extends the watch, churn stays `unverified`; Docker down
on the first stop and back on the repeated stop (cancel, cancel_all and the
CLI exit codes); unrelated checkout work acquires the lock during a slow
reconciliation and a stale generation cannot record; clear and relaunch wait
for the tombstone and recheck once.

## Exact container cleanup and restart reconciliation — 2026-09-12

Two remaining NO-GO findings are closed. A decomposition ticket now fixes its
exact provider container name and compose project before Docker can start;
after the child's tree has ended, only that name is inspected, only that exact
container id is removed, and the name is watched for a settle window so a
create landing after the first look is still caught; the verified outcome (or
a refusal: Docker unavailable, or another project/service under that name,
nothing removed) is retained as `provider_container_cleanup`, and
`clear-background-job` refuses until it is verified absent. A restarting
controller reconciles every retained ticket under its lock before the first
plan: authenticated live children are adopted (Job Object handle reopened, no
relaunch), ended ones harvested with their container reconciled, live children
with a bound identity but a ticket that no longer authenticates are stopped
exactly and quarantined (task blocked with the reason), and anything ambiguous
refuses startup with nothing killed or removed. `stop-graph` is idempotent.
Tests: stop during delayed container creation, abrupt controller death with a
child, grandchild and simulated container (fixture, plus one real Windows
process tree), forged process/container identity reaching nothing unrelated,
repeated stops, restart harvest without relaunch, and startup refusal until the
container is verified absent.

## Background management jobs — 2026-09-12

The fresh NSC-1130 gauntlet proved the controller loop was serialized on
management work: one decomposition proposal blocked it for 203 s, each
post-crew validation for 99–118 s, and a worker that finished during the
proposal waited 6 m 37 s for its 3 s settlement while the loop prepared and
started the generated children first. `decompose` and `post_crew` now run as
owned detached background jobs (`background_jobs.py`) with exact tickets,
process identity, retained receipts, restart recovery and duplicate-launch
prevention; the planner settles terminal workers first on every cycle, launches
jobs next, keeps preparing/reserving/starting unrelated tasks while they run,
and keeps every Source-moving action in one serialized foreground lane.
`decomposition.apply` now takes the Source integration lock. Sixteen focused
tests (`test_background_jobs.py`) cover overlap, settlement, admission, Source
lane exclusion, restart, failure isolation, limits and legacy state; one runs the
real detached child on Windows with a test-only ticket. `auto_approve` is now approval-only: it approves from the retained
focused-validation facts and fails closed without them, so no foreground path
runs Unity. `plan()` keeps per-HEAD caches (batch-read contracts, one
conformance view, record-keyed proofs); on the live 102-task graph a warm cycle
dropped from about 15 s and 189 git processes to about 0.2 s and four, and the
first cycle after a HEAD move to about 5 s. Not changed: the viewer does not
yet project `wait_job`.

## Bounded graph controller — 2026-09-11

`graph-plan` and `run-graph` now provide the missing outer loop while reusing the
existing AssistantControl components. The controller executes one durable action,
re-reads Source and task records, and plans again. It stops on unknown failures,
never pushes, and writes viewer-visible state to
`<checkout-root>/.assistant-control/graph-controller.json`.

Focused verification passed: 29 review/controller/viewer tests, followed by seven
controller tests after dependency-closure and fresh-state fixes. A disposable
real-project smoke test proved NSC-1010 brings NSC-1015/1016, NSC-1013/1014, and
NSC-1001 into scope. A `--delegate-safe` smoke run prepared and scoped NSC-042,
then returned `handoff_required` before reservation. No provider, Unity, GitHub,
or live task-graph work ran during these checks.
