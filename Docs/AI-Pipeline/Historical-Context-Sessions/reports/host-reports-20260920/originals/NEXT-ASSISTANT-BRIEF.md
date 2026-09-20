# NoSafeCircle pipeline — brief for the next assistant (written 2026-09-09, late)

You are picking up an autonomous software pipeline that Vincent (GitHub login `cathode26`, the only human operator) uses to build his Unity game *No Safe Circle*. The game is due in about a week. Vincent is exhausted and wants things simple; he has said, verbatim: "this is not NASA", "I want flexibility not accounting", "it should be as if it never happened" (for failed runs). Keep answers short, give copy-paste commands, don't lecture.

Read this file first, then `handoff-20260909.md`, then `local-vs-production-comparison.md` in this folder.

---

## 1. What the system is

- **Task contracts** live in `Tasks/NSC-<id>.yaml` (JSON despite the extension). A **TaskGraph** (`Pipeline/TaskGraph/`) derives each task's state from committed evidence; `python Pipeline/TaskGraph/taskcontrol.py validate` must print `taskcontrol validate: PASS`.
- A **scheduler** (`Pipeline/TaskReviewAgent/run_autonomous_graph.py` → `polling_orchestrator.py`) hosts a **Software Architect** (a Claude session) that admits tasks; each admitted task gets a **worker** (`host_worker_launcher.py` → `openai_pipeline.run_openai_production_pipeline`) whose host is deterministic and whose supervisor (Claude) only picks bounded actions.
- The worker runs an **ExecutionCrew** (implementer + validator, Claude in Docker; `execution_bridge.py`) that produces `candidate.patch`, then the host commits, pushes, and hands the task to the human on a GitHub Issue.
- Two modes: **local rehearsal** (no GitHub; commits into a local source; auto-accepts everything except NSC-042) and **production** (GitHub Issues coordinate; a serialized merge gate; human PASS; delivery evidence; merge into `main`).
- A **viewer** (`Pipeline/TaskReviewAgent/GauntletView/server.py` + `index.html`) shows the run on http://127.0.0.1:8813 with Start/Stop/Reset/Poke buttons.
- Docker: Claude credentials live in volume `nosafecircle_claude-config`; the OAuth token expires every few hours. Refresh with `docker compose -p nosafecircle run --rm -it claude-exec claude` then `/login`, `/exit`. The launcher refuses to start with < 30 min left.

## 2. Where everything is

| What | Where |
|---|---|
| Vincent's working checkout (the **Source**, must be on `main`, clean) | `C:\NSC\TenTaskFinalIntegration-20260905` |
| Checkout root (worker checkouts `NSC-<id>\`, run state under `.task-review-agent\`) | `C:\NSC\TenTaskFinalIntegration-20260905-Checkouts` |
| GitHub repo (rehearsal copy of the real game repo) | `cathode26/NoSafeCircle-Homework-Rehearsal` |
| My branch line (all fixes; Vincent fast-forwards `main` from it) | GitHub `integration/gauntlet-convergence-20260908` at **722eb70bf**; local worktree `C:\nscrev\prodmain` |
| Older local-only line (has the code fixes, not the content scrub) | GitHub `integration/local-gauntlet-20260909`; local `C:\nscrev\fixrepo` |
| Reports (this folder) | `C:\nscrev\reports` |
| Patch scripts I used (python, idempotent asserts) | `C:\nscrev\repro\apply_*.py` |

Run folders: `<CheckoutRoot>\.task-review-agent\autonomous-runs\<sha>\production-all-claude-<stamp>\` with `events.jsonl` (the journal), `manifest.json`, `stop-request.json` when stopped. Worker outputs: `<CheckoutRoot>\.task-review-agent\outputs\NSC-<id>\scheduler-nsc-<id>-<hex>\progress.log` (human-readable) and `debug.log`. Launch logs: `<CheckoutRoot>\launch-logs\<run-id>.stdout.log`.

## 3. The operator loop (what Vincent does)

```
cd C:\NSC\TenTaskFinalIntegration-20260905
.\NscRun.cmd viewer -Production          # persistent viewer on 8813, nine gauntlet tasks, human review on
```
On the page: click a task → **Enable/Disable for run**; **Start run** (opens a console; 2–3 min to first node); **Stop run** (cooperative drain; workers hand leases back); **Stop now** (kill); **Reset** (delete the run folder, only after a stop). `NscRun.cmd stop -Force` from the console kills a run when the page can't.

Pulling my fixes into main (**only when no run is live**):
```
cd C:\NSC\TenTaskFinalIntegration-20260905; git fetch origin; git merge --ff-only origin/integration/gauntlet-convergence-20260908; git push origin main
```
If `server.py`/`index.html` changed, restart the viewer: `.\NscRun.cmd viewer-stop; .\NscRun.cmd viewer -Production`.

The nine-task scope (from `Run-ProfileGauntlet.ps1`): NSC-1001, 1003, 1004, 1005, 1007, 1008, 898, 899 (synthetic "Gauntlet NNNN" tasks that create one C# constant each; 898 and 1007 are decomposition parents producing Alpha/Beta children) plus **NSC-042** (the one real task: "Seamless Scalable Wall Tiling for Long Isometric Walls", always human-reviewed, crew takes ~25 min).

## 4. The human path in production, as it runs today

1. crew → `integrate_commit_push_and_handoff`: commit on branch `nsc-<id>-<slug>`, push, Issue → `candidate_ready_for_gate` (queued in a hidden git ref `refs/nsc/claims/integration-gates/<hash>`).
2. Gate worker (one candidate at a time): merges current main into the candidate, runs Unity EditMode validation, then `human_handoff_created` → Issue label `nsc-state:human-action`, viewer node "Task Needs You".
3. Vincent posts a comment (the handoff comment now contains it with the commit prefilled):
   ```
   ## Human validation result

   Result: PASS
   Tested commit: <sha>
   ```
   The GitHub Action `.github/workflows/nsc-issue-workflow.yml` fires on the comment (or on the `nsc-state:agent-ready` label) and applies it.
4. `delivery_evidence` phase: if main moved since the PASS → `integrate_current_main` → **`human_revalidation_required`** (a second PASS on the new integrated commit) → delivery review draft → publish evidence → PR → merge → Issue closed `complete`. Only now is the task **delivered** for TaskGraph, which is what unlocks dependents (1007 depends on 1001).
5. Decomposition parents (898, 1007): the Issue asks for `## Decomposition application result` / `Result: APPROVE` / `Reviewed plan_id: GDP-...`, then the children are generated and committed to main by the pipeline itself.

**Vincent's stated design wish (not yet built):** production should mirror local's commit path with a human PASS exactly where local auto-accepts; no gate-first queue, no second validation, no PR ceremony. `local-vs-production-comparison.md` sections 4–5 contain the design and the plan (estimate 1–2 careful days; the crux is that TaskGraph "delivered" needs a DEL evidence record, which local sidesteps with an acceptance overlay).

## 5. Rules learned the hard way

1. **Never pull or push `main` while a run is live.** Stop → wait for the architect line to say "exited" → update → Start. A main move after a PASS forces re-validation of every PASSed-but-undelivered task; a main move during a crew breaks its handoff ("not descended from the recorded workflow head").
2. **A task reset is four deletions**, or the next run trips on the leftover: the Issue (`gh issue delete N --yes`), the task branch on GitHub, the hidden refs (`gh api -X DELETE repos/cathode26/NoSafeCircle-Homework-Rehearsal/git/refs/nsc/claims/...`; list with `gh api repos/.../git/matching-refs/nsc`), and the worker checkout folder `<CheckoutRoot>\NSC-<id>` (never while its worker is alive).
3. A **closed "complete" Issue** makes a worker exit "complete" in one turn without doing anything; the scheduler then flaps the task blue/purple. Delete such Issues when resetting.
4. **Stop-Force kills crews mid-edit** and leaves a dirty checkout; the loop guard parks the task after 3 blocks; delete the checkout before the next run.
5. The production launcher spawns a **per-run viewer** (port 8787+) that holds `gauntlet-view.log` open in the run folder; it blocks manual deletion of run folders. Kill with: `Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'GauntletView' -and $_.CommandLine -match '--run-dir' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`.
6. Windows PowerShell 5.1: variable names are case-insensitive (`$RunsRoot` vs `$runsRoot` collide), `\"` to pass quotes to native commands, DETACHED_PROCESS PowerShell exits silently (use CREATE_NEW_CONSOLE / CREATE_NO_WINDOW). Git Bash `sed -n "$((L-4)),..."` breaks when `$L` is empty; guard your variables.
7. The Claude Code auto-mode classifier (if the next assistant is Claude Code) refused: launching production runs, pressing Stop via the viewer API, editing Issue labels, `Remove-Item` on the checkouts, sometimes `git checkout` in a live clone. Vincent runs those himself; give him the exact command.
8. Write patch scripts to files and run them (`C:\nscrev\repro\apply_*.py`); long heredocs in Bash mangle quotes.

## 6. State when I stopped (23:25 UTC, 2026-09-09)

- Open Issues: #24 (042, agent-ready, stale local checkout to delete), #30 (899) and #31 (1001) PASSed and in `delivery_evidence` (will ask for one re-validation because main moved), #32–#34 (1004, 1003, 1005) queued at the gate, #35 (898) decomposing/human-action. No stray branches; gate ref healthy.
- Branch `integration/gauntlet-convergence-20260908` = 722eb70bf, one commit ahead of what Vincent had pulled (b217c54). Next step for him: pull, Start, answer re-validations, PASS the rest, then decide on the redesign.
- Pre-existing failing tests unrelated to this work: `tests/codex_supervisor_turn_smoke_test.py` (plan_id), `tests/automated_validation_downstream_smoke_test.py`, some `GauntletView/tests` at 8d7ca778.

## 7. What was built or fixed on 2026-09-09 (all on the branch, all with tests)

Operator loop: `NscRun.cmd` (start-here, start-production, stop [-Force], reset, status, prune, viewer [-Production], viewer-stop); persistent viewer with production mode, Start/Stop toggle, Stop now, Reset, Poke the architect, architect alive/dead line, per-task Enable/Disable, Create GitHub Issue (creates the task Issue + NSC-Vincent inbox), checkout folder row, GitHub repo row; dead or journal-less runs read as finished; stale start markers discarded.
Launch: `-HumanReview` disables the synthetic evidence pump (default for the production viewer; `-AutoApprove` restores it); fresh-seed prerequisite; credential expiry check.
Scheduler: cooperative operator stop reaches workers and crews (stop hands the lease back to agent-ready); a task blocked 3× in a row is parked (`task_admission_suspended`); a crashed worker parks only its task, 3 distinct crashes end the run; a momentary double state label is a re-read; the gate defers an unreadable owner/waiter Issue for up to 5 polls; gate-queue exits don't count as blocks.
Pipeline: Unity YAML trailing whitespace normalised before `git diff --check`; `integrate_current_main` added to the supervisor's argument contracts; PASS comment hash accepted with or without trailing newline; Issue Action fires on the result comment itself and ignores a concurrent duplicate; handoff template carries the commit; child-template parent hashes use `parent_semantic_hash`; `validate-current` tolerates legacy selections whose contracts were deleted.
Content: "Muffcabbage" scrubbed (98 synthetic contracts + 25 evidence folders + 58 Unity files deleted; 8 live tasks renamed to "Gauntlet NNNN" with guids re-derived from the new paths; generator, policy, scripts, tests, docs renamed).

## 8. Useful commands

```
# graph
python Pipeline\TaskGraph\taskcontrol.py validate
python Pipeline\TaskGraph\taskcontrol.py state NSC-1001
# tests that cover today's work
python Pipeline\TaskReviewAgent\tests\polling_orchestrator_smoke_test.py
python -m unittest Pipeline.TaskReviewAgent.GauntletView.tests.local_stop_endpoint_test Pipeline.TaskReviewAgent.tests.operator_stop_request_test Pipeline.TaskReviewAgent.tests.operator_stop_propagation_test
python Pipeline\TaskReviewAgent\tests\gauntlet_end_to_end_smoke_test.py
python Pipeline\TaskReviewAgent\tests\integration_gate_smoke_test.py
# GitHub state
gh issue list -R cathode26/NoSafeCircle-Homework-Rehearsal --state all --json number,state,title,labels
gh api repos/cathode26/NoSafeCircle-Homework-Rehearsal/git/matching-refs/nsc --jq '.[].ref'
gh run list -R cathode26/NoSafeCircle-Homework-Rehearsal --workflow nsc-issue-workflow.yml --limit 5
```

Good luck. The pipeline ran the full human path end to end for the first time tonight; the remaining work is making it simpler, not fixing it.
