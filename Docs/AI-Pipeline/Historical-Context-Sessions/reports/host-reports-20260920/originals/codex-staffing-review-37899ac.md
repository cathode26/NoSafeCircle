# Adversarial staffing review — 37899ac

## Verdict

**FIX FIRST** for `37899ac36423a0049df8232b3d9ca2e200d12630`.

Verified parent: `e90670da5b5fc19567e1efe1cb655c43de292f4e`. The scheduling fixtures support basic concurrency, but they do not substantiate safe stopping or all claimed slot behavior. Four stop-path findings require repair before a live trial.

This review was read-only. No files in the reviewed repository were written, no file-producing repository tests were run, and Docker, providers, GitHub, and `C:\NSC` were untouched.

## Findings

### P1 — A newly launched worker can escape a graph stop

`Pipeline/AssistantControl/graph_controller.py:1155`, `:1982`

After the controller projects a slot as `claiming`, `start_worker` may write the worker record before the next staffing refresh. A stop arriving in that window uses the stale cached slot, which has no worker identity and may have no run ID. `stop-graph` or Ctrl+C can then report stopped while the worker continues.

The existing stop test begins with workers already projected. Add failing-before coverage for stop immediately after the launch record is written and for interruption after child handshake but before launch returns. Build stop inventory from current authenticated reservations and worker/launch records; never use the presentation cache as stop authority.

### P1 — Stop is not bound to the slot's recorded process identity

`Pipeline/AssistantControl/graph_controller.py:1163`, `:1188`

If a slot records run `R`, lease `L`, identity `A`, and the durable worker record changes to identity `B` while retaining `R`, the controller supplies only task and run ID. `worker_control.force_stop` rereads and acts on `B`. A corrupt record containing another live process identity can therefore reach termination. PID-reuse checking against `B` does not prove `B` belongs to the staffed attempt.

Add a test that changes process, lease, and Job Object identity while preserving run ID and proves no process/container operation reaches the replacement. Pass an authenticated expected-attempt identity into the stop API and verify it atomically inside the destructive boundary.

### P1 — Host exit is incorrectly accepted as complete worker cleanup

`Pipeline/AssistantControl/graph_controller.py:1181`, `:1193`

When grace polling sees `host_identity_alive=False`, the worker leaves the pending set and is marked stopped even if its owned Docker container remains alive. `worker_control.status` explicitly says host exit does not prove Docker children exited. An in-memory probe returned `stopped` with zero cleanup calls in this case.

Add a test where the host exits during grace while its owned container remains active. Require exact tree/container cleanup evidence before declaring stopped, while preserving a legitimate terminal worker result.

### P1 — Worker-stop failures disappear from public graph completion

`Pipeline/AssistantControl/graph_controller.py:1968`, `:2116`, `:2166`

If every worker stop fails, slots record `stop_failed` but the graph returns `status: stopped`. `request_stop` only considers background cleanup, so its CLI path can still succeed. A repeat can return `already_released` and say nothing remains while workers live. A later `_save_state` also drops `staffing_stops` unless explicitly supplied.

Add an end-to-end graph-stop test with worker-stop failure and no background jobs, followed by a repeated stop. Require non-success, durable unresolved worker stops, and an exact recovery command until cleanup is verified.

### P2 — Foreign reservations consume local slots and can starve this graph

`Pipeline/AssistantControl/graph_controller.py:1757`, `:989`

With global capacity 20 and local staffing width 3, three reservations belonging to another checkout root make `len(reservations) >= staffing_width` true. This controller then admits no workers, and its projection assigns those foreign reservations to local blocked slots.

Add a two-checkout-root test sharing one Source registry. Enforce global reservations against global capacity and this controller's authenticated reservations against local staffing width; continue checking resources globally.

### P2 — Quarantined reservations are counted as available

`Pipeline/AssistantControl/graph_controller.py:1081`

A reservation quarantined as `blocked` still consumes admission and a slot, but `_SLOT_AVAILABLE` includes every blocked slot. Two working slots plus one quarantined reservation therefore reports `occupied=2, available=1`, although scheduling cannot use the third slot.

Extend the quarantine test to assert capacity counts and inability to refill. Separate reservation occupancy from display state: a retained blocked reservation is occupied; a released blocked outcome is available.

### P2 — Initial/error state saving can mask the real startup failure

`Pipeline/AssistantControl/graph_controller.py:1252`, `:1975`

Before startup reconciliation, `_save_state("running")` calls uncached `staffing()`, which reads the admission registry and task records. An unreadable registry can raise before the protected main `try`, preventing both reconciliation and a durable refusal. An error-path save can fail similarly and mask the original error.

Add a test with an unreadable registry plus a distinct original startup error. Save a supplied/cached snapshot and serialize staffing as unavailable with its observation error; keep admission refused and move startup saving into the protected path.

No repeated full rescan per save was demonstrated after `_refresh_staffing`; normal later saves use the cache.

### P2 — The advertised grace is not a hard deadline

`Pipeline/AssistantControl/graph_controller.py:1170`

Grace polling uses `Checkouts.observe`, which may perform several Git operations including untracked-file inventory. The deadline is checked outside a whole worker batch, so one slow checkout—or several—can exceed the configured grace substantially. Cooperative stop requests also run before the deadline starts.

Add a test where status consumes more than the remaining grace and other workers remain pending. Poll lightweight exact identity/liveness with operations bounded by remaining time and check the deadline between workers.

### P3 — Successful releases lose their last result

`Pipeline/AssistantControl/graph_controller.py:1045`

When a successful task releases its reservation and is neither blocked nor waiting for human review, the slot becomes idle, clears its task ID, and often retains null or an older task's `last_result`. Capture the departing attempt's exact terminal result before clearing/refilling the slot. Add a release test asserting this history.

## What the eleven tests establish

They give useful evidence for basic single-root admission, no repeated launches in their fixture, separate background-job capacity, resource overlap, bounded idle waiting, and slot serialization. They do not prove the complete claims:

- Refill manually calls `admission.release` and uses another controller instance.
- The “without a restart” dependency test constructs a new controller and patches both dependency authorities.
- The decomposition test starts an already committed child; it does not prove discovery of newly applied children.
- Failed and human-held scenarios begin after capacity was already released.
- The stop test mocks both stop APIs and uses zero grace.
- The viewer test calls `_staffing_projection` directly; it does not exercise `/api/state` or browser rendering.
- Fixture-clock throughput excludes real planning and command duration.

The CLI default increase to three workers is explicit and documented. No new Windows path-spelling defect was demonstrated. Sticky released states and cosmetic next actions are acceptable once occupancy is corrected. Sequential refresh/save avoids obvious duplicate event emission, but it does not prove crash-safe exactly-once journaling. The HTML still does not render staffing slots.

## Commands and tests actually run

All commands ran read-only from `C:\nscrev\throughput`:

- `git rev-parse HEAD`
- `git show -s --format='%H%n%P%n%s' 37899ac`
- `git diff --stat e90670da5b5fc19567e1efe1cb655c43de292f4e 37899ac36423a0049df8232b3d9ca2e200d12630`
- Scoped `git diff e90670d 37899ac -- …` for controller, CLI, viewer, staffing tests, README, CURRENT, and autonomous-graph documentation.
- `git diff --check e90670d 37899ac` — clean, exit 0.
- Read-only status, numbered source reads, and `rg` searches over the reviewed files and their dependencies.
- `python -B -c $reviewCode` — five in-memory probes using AST-extracted methods and stubbed collaborators; exit 0. These reproduced findings 1, 3, 5, 6, and 7.

Repository test suites run: **none**. There are no reviewer-produced `Ran N tests … OK/FAILED` lines. The implementer's reported suite results were not independently reproduced.

## Residual risks

Real Windows launch/stop races, Docker cleanup, and production throughput remain unmeasured. After repair, require a disposable real-child stop test covering launch interruption and identity changes, a controlled owned-container cleanup test, and a multi-root admission test. Human-review settlement and newly applied decomposition-child discovery also need integration coverage rather than preconstructed fixture state.
