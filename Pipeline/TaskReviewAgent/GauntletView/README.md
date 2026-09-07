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

## What it reads

| Source | Used for |
|---|---|
| `Tasks/NSC-*.yaml` | nodes, `parent`, `depends_on`, title, resources, acceptance criteria |
| `.task-review-agent/autonomous-runs/<repo>/<run>/manifest.json` | run scope, capacity, excluded ids |
| `.../progress.json` | poll cycles, worker launches, architect invocations |
| `.../events.jsonl` | `worker_launched` / `worker_finished` → which tasks are active now |
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

## Live updates

The page opens an SSE connection to `/api/stream`. The server fingerprints the
mtime and size of every file above once per second and pushes a new snapshot
only when something actually changed; otherwise it sends a keepalive. The page
applies changes incrementally — a state change repaints one node and pulses its
border, and the layout only re-runs when nodes or edges are added or removed.

## Controls

- **Mouse wheel** zoom, **drag** to pan, or the **Zoom +/− / Fit** buttons.
- **Dependencies** lays the graph out left-to-right along `depends_on`.
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
`Task In CI` is teal, `Task Needs You` is pink, `Task Blocked` is orange,
`Task Failed` is red, `Task Retired` is brown, and `Task Excluded` is silver.
Ordinary available work is purple while available decomposition is yellow.

Labels fade out below a zoom threshold so a 1,000-node graph stays readable
when fully zoomed out.

## Vendored libraries

`vendor/` holds Cytoscape.js 3.30.2, dagre 0.8.5 and cytoscape-dagre 2.5.0
(all MIT). They are served from disk, so this works with no network access.
