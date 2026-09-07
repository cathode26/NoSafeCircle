# NSC Gauntlet Graph

A live, zoomable view of the gauntlet task graph. Read-only: it opens your
contract and run files, never writes to them, and never mutates Git, GitHub,
Docker or any provider. Its TaskGraph completion check is a local, read-only
evaluation of committed HEAD.

## Run

```
python Pipeline/TaskReviewAgent/GauntletView/server.py
```

Then open <http://127.0.0.1:8787>.

By default it reads this checkout's `Tasks/` and run state. It never searches
sibling checkouts. Select an external task-state directory explicitly:

```
python Pipeline/TaskReviewAgent/GauntletView/server.py --tasks C:\Work\NoSafeCircle\Tasks --state C:\Work\TaskRuns --port 8787
```

`--state` is the directory that *contains* `.task-review-agent`, not the
`.task-review-agent` directory itself.

### Operator display selection

Repeat `--display-task-id NSC-ID` to select the contracts to watch. This is
independent of the newest autonomous run's execution targets. The server first
evaluates the full authoritative graph, including dependencies outside the
selection, then limits the API's `tasks` array to the selected contracts. The
`display.task_ids` field records the selection on both `/api/state` and every
SSE snapshot. `run.targets` and each task's `in_scope` still describe execution.
The selection does not change when a new run or SSE update arrives.

With an explicit selection, **run scope only** starts off. Turning it on
temporarily intersects the selection with the current run; turning it off shows
the whole selection again. That filter preference is saved per task directory,
state directory and display selection, independently of the run ID. Without an
explicit selection, the existing initial run filter is retained. The state
legend and cancelled-task filter continue to work as before.

Invalid or missing task IDs stop launch with a clear error. If a selected
contract later disappears, `display.missing_task_ids` and the sidebar report it;
the server does not fabricate a node or state. The selection is launch
configuration, so page refreshes and SSE updates retain it without writing any
task, run, Issue or history artifact.

For this isolated fix checkout, this exact PowerShell command launches a
separate viewer on port 8788 showing NSC-1001 through NSC-1008. It reads the
rehearsal's existing contracts and run artifacts; it does not start a scheduler
or change the visualizer already running on another port. A port already in use
causes launch to fail rather than replace a process. This command is documented,
not executed as part of the offline regression validation.

```powershell
python C:\NSC\GauntletViewScopeLayout-20260907\Pipeline\TaskReviewAgent\GauntletView\server.py --tasks C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal\Tasks --state C:\NSC\Rehearsal --port 8788 --display-task-id NSC-1001 --display-task-id NSC-1002 --display-task-id NSC-1003 --display-task-id NSC-1004 --display-task-id NSC-1005 --display-task-id NSC-1006 --display-task-id NSC-1007 --display-task-id NSC-1008
```

Open <http://127.0.0.1:8788>. The task list is an example launch configuration;
these IDs are not embedded in the server's graph rules.

## What it reads

| Source | Used for |
|---|---|
| `Tasks/NSC-*.yaml` | nodes, `parent`, `depends_on`, title, resources, acceptance criteria |
| `.task-review-agent/autonomous-runs/<repo>/<run>/manifest.json` | run scope, capacity, excluded ids |
| `.../progress.json` | poll cycles, worker launches, architect invocations |
| `.../events.jsonl` | `worker_launched` / `worker_finished` → which tasks are active now |
| `.../run_timeline.jsonl` | exact-run start, error, and graph-complete observations; participates in SSE fingerprinting |
| `.../graph-complete.json` | terminal receipt |
| `.task-review-agent/outputs/<TASK>/<run>/progress.jsonl` | per-task turn, action, phase, Issue/PR identity, provider-usage receipts, Issue state, terminal status |
| `.task-review-agent/outputs/<TASK>/<run>/run_result.json` | durable fallback Issue number for the newest worker run |
| `.task-review-agent/outputs/<TASK>/<run>/ci_snapshot.json` | optional bounded local snapshot of PR checks already observed by the worker |
| committed TaskGraph conformance at `Pipeline/TaskGraph/evidence/<TASK>/records/` | authoritative delivered/complete state |
| committed `Pipeline/TaskGraph/evidence/<TASK>/metrics/token-usage.json` | authoritative completed-task token total, when valid and present |

For each task it takes the newest run directory by `progress.jsonl` mtime, and
reads only the tail of that file, so a long run stays cheap to poll.

The server recognizes `issue_url`, `result_issue_url`, `issue_number`, and
`result_issue_number` in that progress tail. If the early Issue event has
fallen outside the tail, it uses the newest run's durable `run_result.json`
Issue number. The manifest repository must be exactly two safe GitHub path
components and the Issue number must be a positive integer. The displayed URL
is then constructed as `https://github.com/<owner>/<repository>/issues/<number>`;
artifact-supplied text is never passed through as a link. This remains entirely
local and read-only: the visualizer makes no GitHub or other network calls.

The same rule protects pull-request links: the visualizer accepts an exact PR
number or an exact `https://github.com/<manifest-repository>/pull/<number>` as
evidence, then constructs the link itself. It never exposes an arbitrary
artifact URL as an `href`.

### Optional local CI snapshot

A PR-monitoring worker may persist the checks it already fetched beside its
`progress.jsonl` as `ci_snapshot.json`. This visualizer does not create that
file and does not add pipeline-side persistence. The optional schema is:

```json
{
  "schema_version": "1.0",
  "task_id": "NSC-701",
  "run_id": "the-containing-run-directory-name",
  "repository": "owner/repository",
  "pull_request_number": 116,
  "pull_request_url": "https://github.com/owner/repository/pull/116",
  "observed_at_utc": "2026-09-07T01:23:45Z",
  "checks": [
    {
      "name": "windows-core",
      "status": "IN_PROGRESS",
      "conclusion": null,
      "step": "Core tests"
    }
  ]
}
```

`pull_request_url` and each check's `conclusion` and `step` are optional. The
task ID and run ID must match the containing directory, the repository must
exactly match the validated manifest repository, the PR number must be a
positive integer, and `observed_at_utc` must be timezone-aware ISO-8601. Check
statuses use the GitHub rollup vocabulary (`QUEUED`, `PENDING`, `IN_PROGRESS`,
or `COMPLETED`); conclusions such as `SUCCESS`, `FAILURE`, `CANCELLED`, and
`TIMED_OUT` are preserved. A snapshot older than 60 seconds is shown as stale
without changing the lifecycle state. If no trustworthy local rollup exists,
the UI honestly says **Check status unavailable**. It never contacts GitHub to
fill the gap.

### State projection and freshness

The visual state describes lifecycle meaning separately from process activity.
An active worker in `merge_closeout` running
`inspect_or_merge_pull_request` with exact open-PR evidence is **Task In CI**;
the details still say **Worker active**, **Monitoring CI**, and show its turn.
Ordinary implementation, repair, validation, evidence, and decomposition work
remains **Task Working**.

Available work is also separated by TaskGraph contract type. A dependency-ready
active `implementation` contract whose `execution_scope` is
`needs_execution_decomposition` and whose `decomposition_state` is `concrete`
is **Decomposition Available**, with a gold node distinct from ordinary purple
**Task Unstarted** work. The distinction applies only while the task is ready;
active decomposition still uses the lifecycle state **Task Working**.

Evidence is ordered by its durable observation timestamp. Current TaskGraph
conformance wins for completion. A current failure or human-action transition
wins over older CI evidence; current checks/PR inspection wins over generic
worker activity; current implementation/repair wins over stale CI; and a task
whose newest workflow transition is `agent_ready` in `delivery_evidence` or
`merge_closeout`, with no active worker, is
**Verified — Waiting for CI Slot** only when the newest local
`integration_gate_observed.queued_task_ids` contains it. This prevents an old
worker terminal event from making resumed or completed work regress.

Active nodes receive up to three server-normalized status lines: semantic
stage, readable current action, elapsed time, exact local CI rollup, retry or
decomposition context, and a recorded cost line when available. Turn count is
never treated as percent complete. Timing estimates require at least three
matching local historical run samples, are displayed as a range, and become
**Running longer than usual** after the historical upper bound instead of
showing a negative ETA. Older artifacts degrade to `unavailable`.

### Token and cost data

GauntletView contains no pricing table and performs no repricing. In-flight
figures come from durable `provider_usage` receipts in that task's own worker
journals, deduplicated by run ID and turn so refreshes and pooled-session reuse
cannot charge the same receipt twice or move usage between assignments.
Missing receipt data makes the result explicitly partial (`at least ...` and a
missing-call count). Provider/model/role and cache categories appear only when
the receipt preserves them. Explicit scheduler batch receipts are allocated
only when they name the exact tasks, with the full shared cost and equal-share
method both displayed; nothing is guessed from an unlabeled batch.

For delivered work, the TaskGraph evaluator reads committed conformance and
the strict committed `metrics/token-usage.json`; that total replaces rather
than overlaps operational token receipts. A projected final cost is separate
from recorded cost and appears only after at least three comparable completed
tasks have persisted costs. Local Unity execution time is never presented as
model cost. No provider is contacted.

## Pipeline Activity and artifact precedence

The compact panel above the graph explains global orchestration independently
of task workflow state. An eligible task stays **Task Unstarted** while the
Software Architect considers it. No task is marked working by the activity
reducer. The existing graph orientation, colors, Issue links, compact progress,
cost details, and workflow classification remain unchanged.

Pipeline Activity starts at 176px high. **Collapse / Expand** keeps a 64px
header with the current recorded stage visible while releasing graph height.
Drag its bottom grip to resize it between 120px and the smaller of 480px or
45% of the viewport height. The body scrolls independently.

Task details start at 320px wide. The header arrow collapses them to a 44px
reopen control; the graph receives the released width. Drag the left grip to
resize between 220px and 560px, further limited to 45% of the viewport width
and enough room for at least 360px of graph width at desktop sizes. Selecting a
node updates hidden details and **never reopens a collapsed panel**.

Both panels save their expanded size and collapsed state in browser
`localStorage` (`nsc.gauntlet.panels.v1`). Resizing the browser clamps the visible
size while retaining the saved preference for a larger window. Storage is
optional: corrupt or blocked storage falls back to defaults without breaking
the view. These preferences are local to the browser and viewer origin/port.

Collapse buttons work with Enter/Space. Focus a grip and use Up/Down for
Pipeline Activity or Left/Right for details in 20px steps; Home/End chooses
the minimum/maximum. Grips expose orientation and current size to assistive
technology. Panel resizing updates Cytoscape's actual container without changing
node positions, ordering, graph direction or zoom. **Fit** and **Zoom +/−** use
the resulting graph area.

`pipeline_activity.py` is a deterministic reducer with an injected clock and no
file, process, provider, Docker, or GitHub access. `server.py` loads its inputs.
The explicit `PRECEDENCE` table selects the first available class:

| Priority | Durable evidence | Display |
|---|---|---|
| 1 | `autonomous_run_error`, fatal `poll_capacity_batch_completed`, `scheduler_stopped`, exact-run `graph_complete_receipt_written`, or `graph-complete.json` | Run failed/stopped or Graph complete |
| 2 | `architect_started` with no subsequent matching return/failure/reconciliation | Software Architect reviewing the recorded eligible portfolio |
| 3 | An in-scope `worker_launched` and that exact worker run's action journal | Starting work, checkout preparation, implementation, validation, integration, evidence, or CI inspection |
| 4 | Latest recognized scheduler observation | Initialization, refresh boundary, portfolio boundary, cached decision, deliberate WAIT, fallback/event wait, integration gate, or scheduler idle |
| 5 | No usable evidence | Pipeline activity unavailable |

Records are ordered by timezone-aware durable timestamps, with journal order as
the tie-breaker. Untimed records precede timed records and cannot supply elapsed
time. Unknown event names remain in recent activity and do not replace a known
stage. Exact duplicate records are ignored. The latest terminal observation wins,
except a normal stop after fatal failure preserves **Run failed**. A completion
receipt without a terminal timeline supplies **Graph complete** with unavailable
timing; a later timestamped failure is not erased by an older receipt. Terminal
observations always outrank nonterminal records, including later drain activity.
`KeyboardInterrupt` is displayed as stopped, not failed. A task failure alone
does not prove the entire run failed.

The current scheduler serializes architect calls. `architect_provider_call` is a
**return receipt**, emitted after the provider invocation, before per-task
`architect_completed` records. Both can close the open call; capacity decisions,
an unusable-call `architect_wait`, and session reconciliation also retire it.
Different explicit source heads are not matched. Completed calls are deduplicated
by invocation/analysis identity or their start record; per-task admissions are
not counted as separate calls from one batch. The saved
`architect_invocations_total` counts attempts and is not used as completed calls.

`architect_wait_started` is a scheduler sleep, never a provider invocation.
`wait_mode=fallback_timer` and `event_or_fallback` have separate headlines.
`cached=true` identifies a cached verdict. **All-WAIT** requires noncached wait
records for every task in the last recorded portfolio, linked to the same
returned analysis, with no task admitted from that analysis. One task's WAIT or
`plan_idle` alone cannot establish an all-WAIT decision. The wait headline carries
the preceding decision as explanatory text when the scheduler enters its sleep.

Worker action evidence is joined only through this autonomous run's
`worker_launched.task_id` and `run_id`, using a bounded local path under
`.task-review-agent/outputs`. No artifact-supplied absolute path is followed.
Historical worker runs are excluded from global stage and freshness. Action
completion removes its active headline; heartbeats advance freshness without
resetting a known action start. Concurrent work is summarized by the most recent
recorded worker stage; the active count still includes every recorded worker.
Once the newest autonomous run begins scheduling, its in-scope task nodes use
only the exact worker run IDs recorded by that run. Immutable output from an
older attempt remains on disk but cannot make a freshly reset task look blocked,
active, completed, or more expensive than its current attempt.

Counters use manifest capacity and scope, current node dependency/completion
projection, this run's launch/return records, deduplicated architect returns, and
saved progress totals for launches and wakeups. Ready/queued counts describe
workflow availability, not a promise that the scheduler will admit those tasks.
Manifest candidates are shown separately during architect review. Zero recorded
returns means zero observed returns, not proof that missing journals contain no
calls. Saved progress counters can lag events until the controller saves them.

### Exact honesty boundary

The panel describes **recorded activity**, not live process inspection.
For an open architect call it displays provider/model from the start event or
the manifest's exact `runtime_configuration.architect_provider` and
`architect_model`, explicitly labelled as configuration. It never substitutes
the execution-worker model, infers a model from an all-Codex profile, or reuses
an old call's model. Missing fields say **unavailable**. A recorded provider
attempt does not prove billing success; the display says billing confirmation
is unavailable until a receipt is written. No percentage or ETA is invented.

Elapsed time uses durable timestamps, never artifact mtimes. After 60 seconds
without a new event, the freshness line is highlighted:
**No new durable event for X; process status is unknown from artifacts.**
The same precise wording remains visible before that threshold. Without any
timestamp it says the last event time is unavailable. An open call is described
as **recorded as in progress**, alongside **Artifact-only liveness is not proof
of process liveness.** No silence threshold means hung, alive, progressing, or
failed. The browser clock advances the elapsed display between SSE changes and
while disconnected; the stream indicator describes the visualizer connection.

Current artifacts cannot distinguish every internal substep. After a source or
reservation completion record, the panel names the next expected step as
**next**, not as a proven start. A broad `run_execution_crew` action does not
prove which internal crew role is currently running. Unity's broad validation
action does not establish Edit Mode versus Play Mode; it says **Unity
validation**. CI inspection does not prove Unity validation is running. A
controller exit that has no stop/error/complete record remains **unknown from
artifacts**. Existing node CI and Issue projections remain available in task
details; the global reducer does not turn old snapshots into live activity.

The reducer trusts local journal provenance and existing completion receipts as
the visualizer already does; it is not a cryptographic run-audit verifier.

### Focused validation

`python -m unittest discover -s Pipeline/TaskReviewAgent/GauntletView/tests -p "*_smoke_test.py"`
runs 110 pure/component regressions, including display-scope HTTP/SSE coverage
and the existing Pipeline Activity cases. These
use disposable synthetic artifacts and a fixed clock; they never run a gauntlet
or Unity. The new cases also cover launch-before-progress-file compatibility,
exact worker-run matching, and terminal precedence. Check the inline JavaScript
with `node --check`, compile changed Python files, and run `git diff --check`.

`python Pipeline/TaskReviewAgent/GauntletView/tests/browser_smoke_test.py` runs
14 additional real-browser checks with Node.js, Playwright and a local Chromium
installation. Set `NODE_PATH` if Playwright is outside Node's normal module
path, and `NSC_VIEW_CHROMIUM` to an installed Chromium executable if Playwright's
browser is unavailable. Optional `NSC_VIEW_SCREENSHOTS` saves fixture screenshots.
The runner owns an ephemeral loopback server and isolated headless browser,
blocks external browser requests, uses vendored scripts, and checks artifact
hashes. Its one deliberate fixture progress update drives a real SSE refresh.
It does not attach to the operator's browser or visualizer. Missing dependencies
fail the browser command; they are not counted as skipped/passed tests.

## Live updates

The page opens an SSE connection to `/api/stream`. The server fingerprints the
mtime and size of every file above once per second and pushes a new snapshot
only when something actually changed; otherwise it sends a keepalive. The page
applies changes incrementally — a state change repaints one node and pulses its
border, and the layout only re-runs when nodes or edges are added or removed.

## Controls

- **Mouse wheel** zoom, **drag** to pan, or the **Zoom +/− / Fit** buttons.
- **Dependencies** lays the graph out top-to-bottom along `depends_on`.
  **Hierarchy** lays it top-down along `parent`.
- **Click a node** to see its full contract and its worker's current turn,
  action, phase and issue state; its dependency neighbourhood is highlighted
  and everything else fades.
- The detail panel puts **Open GitHub Issue** immediately below the selected
  task's state and title. `Task Needs You` uses the prominent primary treatment;
  active, checks-pending, blocked, failed and complete tasks use the same exact
  managed-Issue destination when available. If local durable evidence cannot
  prove the Issue identity, the panel says **GitHub Issue unavailable** instead
  of falling back to a repository link. Opening the Issue uses a new browser tab.
- **Click a state in the legend** to show or hide it; hover a row to see what it
  means and the underlying state key. `Task Retired` is hidden by default; retired contracts remain available through the filter.
- **run scope only** narrows to the task ids named in the run manifest.

Legend labels are presentation only and live in the `STATES` map at the top of
`index.html`. The server emits these state keys:

| Label | State key | Meaning |
|---|---|---|
| Task Working | `active` | a worker is running it right now |
| Task In CI | `checks_pending` | waiting on GitHub pull-request checks |
| Verified — Waiting for CI Slot | `integration_queued` | `agent_ready` work queued behind the local integration gate |
| Task Unstarted | `ready` | dependencies satisfied, nobody has picked it up |
| Decomposition Available | `decomposition_ready` | dependencies satisfied and the exact TaskGraph contract is eligible for decomposition |
| Task Dependencies Unmet | `pending` | a `depends_on` task is not complete |
| Task Needs You | `human_action` | your Unity checklist |
| Task Complete | `complete` | current committed TaskGraph conformance proves delivery |
| Task Blocked | `blocked` | worker stopped short — you inspect or repair |
| Task Failed | `failed` | worker run failed — you diagnose |
| Task Retired | `cancelled` | contract cancelled/superseded |
| Task Excluded | `excluded` | in the manifest exclusion list |

The legend uses a high-separation categorical palette across every state, not
neighboring shades for related states. In particular: `Task Working` is blue,
`Task In CI` is cyan, `Task Needs You` is pink, `Task Blocked` is orange,
`Task Failed` is red, `Task Retired` is brown, and `Task Excluded` is silver.
Ordinary available work is purple while available decomposition is yellow.

Labels fade out below a zoom threshold so a 1,000-node graph stays readable
when fully zoomed out.

## Vendored libraries

`vendor/` holds Cytoscape.js 3.30.2, dagre 0.8.5 and cytoscape-dagre 2.5.0
(all MIT). They are served from disk, so this works with no network access.
