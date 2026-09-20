# The graph viewer: how to use it, what's wrong, how to make it better

Written 2026-09-16. It covers the viewer for the main project. Short version: the runbook section 4. Problem IDs (V1...) match `C:\NSC\nsc-pipeline-problems.md`.

---

**Owner (2026-09-17):** the **Viewer Agent** session runs the viewer and changes the overlays for everyone (`nsc-viewer-agent-guide.md`). Other agents send it a `VIEWER:` line, and run `nsc_viewer.py` themselves only when no Viewer Agent session is running. Viewer code stays with the Pipeline Maintainer Agent.

## 1. What it is

- **It is a read-only web page** at **http://127.0.0.1:8828/**. It shows every task in the TaskGraph as a node, coloured by state, and a detail panel per task.
- **It changes nothing.** It never starts, stops or approves work. All POST/PUT/PATCH/DELETE requests are refused.
- **The server** is `Pipeline/AssistantControl/viewer.py`, run as `python -m Pipeline.AssistantControl ... viewer`.
  - The page itself is `Pipeline/TaskReviewAgent/GauntletView/index.html`, a Cytoscape graph.
  - `Pipeline/TaskReviewAgent/GauntletView/server.py` is an **older, different backend** for the legacy production/rehearsal modes. It is never used for the main project; don't debug it for main-project display bugs.
  - `C:\NSC\nsc-gauntlet-view\` is a third, standalone prototype outside git. Ignore it.
- **Where the data comes from.** It reads Source `C:\NSC\NSC\NoSafeCircle`: committed task contracts and TaskGraph evidence at HEAD. It also reads the checkout root's records in `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\`:
  - `NSC-###.json`, the task checkout, worker, candidate and approval record;
  - `NSC-###.decomposition.json`;
  - `graph-controller.json` and `graph-controller-owner.json`, retired-controller records that still affect scope when their status is `preflight` or `running`;
  - `viewer-simulation.json`, if present;
  - the three display overlays (section 4).

---

## 2. Everyday use: the control script (agents: use this, don't hand-edit)

`C:\NSC\tools\viewer\nsc_viewer.py` handles start, stop, status and overlay edits. It is Windows-only, lives outside git for now, and was tested on 2026-09-16 against a scratch copy.

```powershell
python -B C:\NSC\tools\viewer\nsc_viewer.py status          # running? right Source/checkout root? inspection_error? state counts
python -B C:\NSC\tools\viewer\nsc_viewer.py start           # live pair on 8828, hidden, logs in .assistant-control\viewer-logs
python -B C:\NSC\tools\viewer\nsc_viewer.py restart         # only after viewer code changed or identity is wrong
python -B C:\NSC\tools\viewer\nsc_viewer.py stop
python -B C:\NSC\tools\viewer\nsc_viewer.py list            # every viewer on 8700-8999; flags stale/research viewers
python -B C:\NSC\tools\viewer\nsc_viewer.py task NSC-075    # the viewer's row for one task
python -B C:\NSC\tools\viewer\nsc_viewer.py overlays        # show and validate the overlay files (exit 1 if a problem)
```

What the script guarantees:
- **`start`** refuses if the port belongs to anything but the live viewer, waits until it listens, and writes a receipt `viewer-logs\nsc_viewer-8828.json`.
- **`stop`** only kills a process whose command line is an AssistantControl or GauntletView viewer on that port. It refuses a viewer on another Source or checkout root unless you pass `--not-live-ok`, which needs Vincent's OK.
- **Every overlay write** takes the same lock as the GER marker CLI (`ger-viewer-overlay.lock`), validates the schema and invariants, refuses task IDs not committed at Source HEAD, and writes atomically as UTF-8 without a BOM.
- **Windows:** nothing the script starts opens a console window.
  - Helper calls use `CREATE_NO_WINDOW`. The viewer launches with a hidden console (`CREATE_NO_WINDOW`, plus `SW_HIDE`) so its git calls inherit it.
  - Verified 2026-09-16: 0 new windows across start, `/api/state`, stop, status and overlays.
  - The earlier version used `DETACHED_PROCESS`, which popped a window per git call.

The script prints JSON: `{"status":"refused","error":...}` with exit code 2 when a safety check refuses.

### Manual equivalents (if the script is unavailable)

```powershell
cd C:\NSC\NSC\NoSafeCircle
Start-Process -FilePath python -ArgumentList '-B','-m','Pipeline.AssistantControl','--source','C:\NSC\NSC\NoSafeCircle','--checkout-root','C:\NSC\NoSafeCircle-AssistantCheckouts','viewer','--port','8828' -WorkingDirectory C:\NSC\NSC\NoSafeCircle -WindowStyle Hidden -RedirectStandardOutput C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\viewer-logs\viewer-8828.out.log -RedirectStandardError C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\viewer-logs\viewer-8828.err.log
Invoke-RestMethod http://127.0.0.1:8828/api/state -TimeoutSec 90 | Select-Object -ExpandProperty viewer_identity
```

- Always pass `-WindowStyle Hidden`.
- From Git Bash, do not start the viewer with `nohup ... &`, because it can end up with no console and pop windows. Use the script.

---

## 3. Reading the page

- **Headline.** It shows `🐴 Vincent needed` and lists task IDs when any candidate waits for his Unity test.
- **Project checkout panel.** It shows the Source path, branch and commit. Check it names the live root; a wrong-root viewer shows every contract but **zero live workers** (V3).
- **Task detail** (click a node): state and phase, `transition_context` (what is happening), the checkout folder and commit (with a Copy button), the worker, the candidate, and the overlays.
- **Filters.**
  - "run scope only" hides tasks outside a controller scope. It only matters while a `graph-controller.json` is in `preflight`/`running`.
  - Clicking a legend entry hides that state.
  - There is no command-line filter (V15).
- **Refresh.** The snapshot is cached 30 s; overlay edits invalidate it at once. After a restart the first load takes 30-90 s (V7). Ask Vincent to press Ctrl+F5 after overlay or colour changes.

### Colours

| Colour / label | State key | Meaning | Known lies |
|---|---|---|---|
| Dark green, dashed border, "Awaiting Instruction" | `assistant_idle` | A task checkout exists and no worker is running | **Also approved and integrating candidates (V1)** |
| Purple "Task Unstarted" | `ready` | Active contract, not delivered | Also shows contract-changed tasks (`needs_replan`) and design-blocked tasks (V8). Doesn't mean dependencies are met. |
| Dark grey "Task Dependencies Unmet" | `pending` | Dependencies not delivered | |
| Light grey "Outside Current Run" | `excluded` / held overlay | Held for GER or design, or outside a controller scope | |
| Brown "GER in progress" (palette "Task Retired") | `ger_overlay: active` | A GER round is working on it | |
| Blue "Task Working" | `active` | Live AssistantControl worker, or a `working` overlay | **Also approved/integrating candidates while a controller runs (V1)**; a worker record stuck at `running` with unverifiable host identity |
| Pink "Task Needs You" | `human_action` | Candidate waiting for Vincent's Unity test | |
| Light pink "Local Review Ready" | `local_review_ready` | Local review state | |
| Orange "Task Blocked" | `blocked` | Record says blocked | Can disagree with the records (V2); check `readiness`/`worker-status` |
| Green "Task Complete" | `complete` / `local_accepted` | Delivered, or Vincent-confirmed via overlay | The overlay doesn't satisfy dependencies |
| "Decomposed Parent" / aggregate | `aggregate` | Split into children, or awaiting decomposition | |
| White "Candidate Ready — Waiting for Merge Gate" | `integration_queued` | *Should* show approved candidates | **Never assigned on main (V1)** |

---

## 4. Display overlays

These are the only files agents write for the viewer. They live in `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\`. **They change the display only.** Real holds live in `graph-lead-journal.md`, and real delivery comes from TaskGraph evidence.

| Script command | File (schema) | Effect | Use when |
|---|---|---|---|
| `hold NSC-###` / `unhold NSC-###` | `held-task-ids.json` (`assistant-viewer-held-tasks/v1`) `task_ids` | Grey "Outside Current Run". `unhold` drops the hold without marking it released. | GER or design hold starts or is cancelled. **Also** record it in the journal. |
| `ger-start NSC-###` | same, `active_ger_task_ids` | Brown "GER in progress" (must be held) | A GER round starts |
| `ger-pause NSC-###` | same | Back to grey, still held | GER blocked or waiting |
| `ger-finish NSC-### [--ready-child NSC-###]` | same, `released_ger_task_ids` | Purple "Task Unstarted" | Contract committed, or decomposition applied |
| `working NSC-### --description "..." [--minutes 30]` / `done NSC-###` | `external-work-ids.json` (`assistant-viewer-external-work/v1`) | Blue while unexpired | Real non-crew work: PixelLab generation, hand-run Unity validation. Refresh before expiry; `done` when finished. |
| `complete NSC-### --note "..."` / `uncomplete NSC-###` | `human-complete-ids.json` (`assistant-viewer-human-complete/v1`) | Green | Vincent said the existing implementation is done and no delivery record exists. Quote him in the note. |

Rules the viewer enforces:
- It **fails the whole page** (`inspection_error`) on a malformed file or an unknown task ID. The script prevents both.
- It requires active ⊆ held and held ∩ released = ∅.
- Expired `working` entries are ignored, and the script prunes them.
- A `working` marker doesn't override `active`, `complete` or `local_accepted`.
- A `complete` marker doesn't override `active`, `human_action`, `local_review_ready` or active GER.

---

## 5. For agents: the API

`GET http://127.0.0.1:8828/api/state` returns JSON. It can take 30-90 s after a restart; use a long timeout.

- **Top level:** `generated_at`, `tasks_dir`, `state_root`, `run`, `scheduler`, `events`, `tasks`, `pipeline_activity`, `human_actions`, `viewer_identity`, and `inspection_error` when broken.
- **`run`:** `mode` (`assistant` for main), `source_repository`, `source_commit`, `source_branch`, `status`.
- **`viewer_identity`:** `instance_id`, `pid`, `source`, `checkout_root`, `port`. Check this before trusting anything.
- **Each `tasks[]` row:** `id`, `title`, `parent`, `depends_on`, `kind`, `disposition`, `decomposition_state`, `decomposition_children`, `execution_scope`, `resources`, `acceptance`, `in_scope`, `state`, `checkout_path`, `checkout_exists`, `checkout_commit`, `worker`, `progress` (`phase`, `transition_context`), `token_cost`, `notes`, `reason`, `taskgraph`. Overlay keys appear when present: `held_overlay`, `ger_overlay`, `external_work_overlay`, `human_completion_overlay`.

The viewer is a hint. Decisions come from `readiness`, `worker-status`, `inspect-result`, `taskcontrol` and the records.

---

## 6. What is wrong with it

In priority order. Details and evidence are in the problem list, section A.

| ID | Problem | Symptom | Workaround today |
|---|---|---|---|
| V1 | Approved or integrating candidates show "Awaiting Instruction", or **blue** while a controller runs | "It stays blue after the work is done" | Read `NSC-###.json` status |
| V3 | Wrong checkout root shows **zero workers**; many stale viewers left running | "Why is nothing blue?" | `nsc_viewer.py status` / `list`; restart on the live pair |
| V2 | Viewer says blocked while records say `awaiting_human` | Orange node for a healthy candidate | Trust `readiness`/records |
| V8 | Purple means never started, contract changed, or blocked on design | Can't tell what is workable | Journal lists design-blocked tasks |
| V11 | Background-job waits and source-lane integration holds are invisible | "Why hasn't it committed?" | `graph-plan` `held[]` (gauntlet mode) |
| V12 | Tasks behind a failed background job show `ready` | Dependents look workable | Check records |
| V7 | `/api/state` slow (5-90 s); page looks dead after restart | Timeouts, blank page | Wait; don't restart repeatedly |
| V6 | Contract or graph changes sometimes needed a restart to show | Old task count | `nsc_viewer.py restart` |
| V4/V5 | Code default port 8813 vs team 8828; stale PID receipt | Wrong viewer opened | Always 8828 via script |
| V15 | No command-line scope or filter | Nearly deleted 92 tasks to hide them in a demo | "run scope only" checkbox plus legend toggles |
| V10 | Non-crew work is invisible unless a JSON marker is refreshed | Vincent undercounts running work | `nsc_viewer.py working` |
| V9 | Marker CLI lacks hold/unhold | Hand-edited JSON on 9/15 | `nsc_viewer.py hold` / `unhold` |
| V13 | "Unavailable" rows (local build SHA, GitHub repository) | Looks broken on camera | Ignore |
| V14 | Title says "NSC Gauntlet Graph" | Gauntlet/main confusion | Ignore |
| V16 | Two backends share `index.html`; legacy README misleads | Debugging the wrong server | Use `viewer.py` for main |
| V17 | Legacy `GauntletView/server.py` can share a port with another process | Stale data served silently | Don't use the legacy server |
| V18 | `test_viewer` 37/57 pass (fixture is pre-schema-v2; one timing `TypeError`) | Can't trust tests when changing the viewer | Fix fixture first |

Fixed on `main` already, don't redo: exclusive port binding; legend held count; solid grey held nodes; stale controller record overriding workers; stale decomposition failure; delivery vs idle checkout; content-identical cherry-pick; external work over `human_action`; human-complete overlay; the removed "rickroll" review alarm.

---

## 7. How to make it better (plan)

### Step 1: quick fixes (each small, one focused test)

1. **V1 state mapping.** In `viewer.py`, map candidate records with status `approved` or `integrating` to `integration_queued` in both places: `task_row` (about line 1011, no controller) and `_apply_running_controller_projection` (about line 662, controller running). Keep blue only for live work. Test both paths.
2. **V13 hide empty rows.** In `index.html` `renderRunDetails()`, hide a row whose value is null instead of writing "Unavailable".
3. **V14 title.** Use "No Safe Circle Task Graph", or derive it from `run.mode`.
4. **V18 tests.** Update the shared fixture in `test_inspect_project.py` to a schema-v2 contract; guard the `stage_elapsed_seconds` `None` case. Get `test_viewer` to 57/57 before any other viewer change.
5. **V9 marker CLI.** Add `hold` and `unhold` to `Pipeline/TaskDesignGER/ger_viewer_marker.py`, the same logic as the script.

### Step 2: structural (removes most confusion)

6. **Wrong-root banner (V3).** Add `viewer_identity` to the page header. Show a red banner when the checkout root has no `project.json` for this Source, or has no worker records while the Source's admission registry shows live reservations.
7. **One way to run it (V3/V4/V5).** Move `nsc_viewer.py` into the repo as `Pipeline/AssistantControl/viewer_control.py`, invoked as `python -m Pipeline.AssistantControl.viewer_control start|stop|status|list|hold|...`, with tests using a fixture root. Default the port to 8828 in one place. Have the viewer write and remove its own receipt.
8. **Distinct states (V8/V11/V12).**
   - Add a "Needs decision" overlay category and colour (a `needs-decision-ids.json`, or a field in the hold file).
   - Style `needs_replan` distinctly from `ready`.
   - Project `wait_job` and source-lane holds as "Waiting on NSC-xxx decomposition" or "Waiting on background job".
   - Surface a failed background job with no task record as blocked.
9. **Records win over projection (V2).** Blocked only when a record or plan reason says so; ignore hash-identical line-ending churn in a task checkout.
10. **Automatic external-work marking (V10).** Let the GER tools and PixelLab or Unity helper scripts call `viewer_control working/done` themselves, so no agent has to remember.

### Step 3: performance and polish

11. **V7 snapshot cost.** Profile `AssistantSnapshot.build()` (the git and TaskGraph evidence reads). Cache per-task evidence by blob id; serve the previous snapshot with a "refreshing" flag while rebuilding.
12. **V6 cache key.** Include Source HEAD and the `Tasks/` tree id so graph changes show without a restart.
13. **V15 display scope.** Add a scope file or `--task` for display only, separate from execution targets.
14. **V16/V17 legacy.** Put a banner on `GauntletView/README.md` ("legacy backend; the main project uses AssistantControl viewer.py"). Give `server.py` the exclusive-port fix, or retire the legacy modes once the gauntlet is retired.
15. **Gauntlet mode later.** When main runs `run-graph`, the viewer should show controller status, `next_actions`, `held[]` and `waiting_human[]` directly, with no need for `graph-plan`.

Suggested owner and order: a Sonnet or Codex fixer takes step 1 as five separate small commits on a branch; Claude reviews; Vincent says go per merge. Then step 2, items 6-7, then 8-10.
