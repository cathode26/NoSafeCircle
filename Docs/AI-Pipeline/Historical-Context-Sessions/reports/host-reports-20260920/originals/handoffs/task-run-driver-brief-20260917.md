# Brief: `task_run.py`, a thin task driver for the Game Agent (2026-09-17)

**From:** Documentation Agent. **To:** Pipeline Maintainer Agent. **Board:** H-20260917-26.

**Vincent:** "Assistant Control was the idea of using a controller to process the the tasks instead of a agent. Yeah we stopped working on it because the problems are numerous so I really need a smart agent in that role." Then: "Maybe we need a less complicated controller for the Game Agent so it has less work to do?" and "That sounds like a good plan."

## Why

Driving one task today means about ten `python -m Pipeline.AssistantControl ...` commands, and reading raw records, `run_result.json`, `progress.log`, git output and Unity logs into the Game Agent's session between them. That burns its context and its account's tokens, and a failed crew turns into a long diagnosis.

The controller layer of AssistantControl (`graph-plan`, `run-graph`, background jobs, `maintenance-*`) stays parked; dispatch authority is DISABLED and stays that way. This is a **driver with hard stops**, not a controller.

## Build

`C:\nscrev\game-tools\task_run.py`, outside git like `viewer-tools` and `ger-tools`, with a README.

| Command | What it does | Prints |
|---|---|---|
| `next` | Reads `readiness`, `status` and `dependencies`. Reserves nothing. | Ready tasks, one line each, with the blocker for the rest |
| `start NSC-### --worker <config> --go` | Preflight, then `prepare`, `scope`, `reserve`, `start-worker` | What it will spend, then the worker id and record paths |
| `watch NSC-###` | Waits for the worker, then reads the durable records | **Why** it ended that way, from `run_result.json` and `progress.log`, not raw logs |
| `candidate NSC-###` | `candidate`, then `materialize-candidate` (Unity builder and focused tests) | A verdict pack: tests, changed files, gates met, what's missing |

**Preflight for `start`** (fail closed, and say which check failed):
- the contract's state and revision, and any open contract check verdict;
- `Tasks/` and the canonical checkout clean, and no open `MAIN-WRITE START` in the journal;
- Docker up and the provider logged in;
- the worker config exists and names a Claude provider (no Codex until 2026-09-19);
- no other task run active.

**Hard stops.** It never runs `review --decision approve`, `integrate`, `publish-approved`, a push, a second task, a retry, or anything on a schedule. At each stop it prints the exact next command for the human or the Game Agent.

**Output discipline** (this is the point of the tool):
- every command prints **at most 20 lines**; everything else goes to a file, and it prints the path;
- summaries name the record field they came from, so the reader can check;
- `--json` prints the same summary as JSON for another tool to consume.

**Telemetry** (this also answers the architecture review's "no cost telemetry" finding): append one line per run to `C:\nscrev\game-tools\runs.jsonl` with the task, worker config, start and end times, wall-clock, provider token counts and cost from `run_result.json`, the outcome, and the record path. Never overwrite; never delete.

**Tests:** unit tests against recorded fixtures (copy real records into a temp folder), covering each summary, the preflight refusals, the "no second run" refusal and the telemetry line. No live crew launch in tests.

## Before you start

The Game Agent runs this chain today and knows its quirks (`refresh-prepared`, `sync-candidate`, validation-policy binding, the NSC-032 recovery commands). Ask it to confirm the exact chain and its traps once Vincent lifts the pause, then build.

Keep it small. AssistantControl started here; the stops and the no-scheduling rule are what keep this one a driver.
