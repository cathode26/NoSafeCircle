# NSC Gauntlet Graph

A live, zoomable view of the gauntlet task graph. Read-only: it opens your
contract and run files, never writes to them, and never touches git, GitHub,
Docker or any provider.

## Run

```
python Pipeline/TaskReviewAgent/GauntletView/server.py
```

Then open <http://127.0.0.1:8787>.

By default it reads this checkout's `Tasks/` and run state. It never searches
sibling checkouts. Select an external task-state directory explicitly:

```
python Pipeline/TaskReviewAgent/GauntletView/server.py --tasks C:\NSC\NSC\NoSafeCircle\Tasks --state C:\NSC\NSC --port 8787
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
| `.task-review-agent/outputs/<TASK>/<run>/progress.jsonl` | per-task turn, action, phase, issue state, terminal status |

For each task it takes the newest run directory by `progress.jsonl` mtime, and
reads only the tail of that file, so a long run stays cheap to poll.

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
- **Click a state in the legend** to show or hide it; hover a row to see what it
  means and the underlying state key. `Task Retired` is hidden by default.
- **run scope only** narrows to the task ids named in the run manifest.

Legend labels are presentation only and live in the `STATES` map at the top of
`index.html`. The state keys the server emits are unchanged:

| Label | State key | Meaning |
|---|---|---|
| Task Working | `active` | a worker is running it right now |
| Task In CI | `checks_pending` | waiting on GitHub pull-request checks |
| Task Unstarted | `ready` | dependencies satisfied, nobody has picked it up |
| Task Dependencies Unmet | `pending` | a `depends_on` task is not complete |
| Task Needs You | `human_action` | your Unity checklist |
| Task Complete | `complete` | finished with terminal status `complete` |
| Task Blocked | `blocked` | worker stopped short — you inspect or repair |
| Task Failed | `failed` | worker run failed — you diagnose |
| Task Retired | `cancelled` | contract cancelled/superseded |
| Task Excluded | `excluded` | in the manifest exclusion list |

Labels fade out below a zoom threshold so a 1,000-node graph stays readable
when fully zoomed out.

## Vendored libraries

`vendor/` holds Cytoscape.js 3.30.2, dagre 0.8.5 and cytoscape-dagre 2.5.0
(all MIT). They are served from disk, so this works with no network access.
