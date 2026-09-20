# Task Orchestrator: operating guide

The **Task Orchestrator** (formerly "Graph Sol") runs normal game tasks on the main project. It picks eligible tasks, gives each an isolated checkout and an execution crew, gets the result validated, puts it in front of Vincent, and integrates what he approves into local `main`.

Read `C:\NSC\nsc-pipeline-runbook.md` first. It covers Docker, logins, the viewer, Unity rules and the shared rules. This guide assumes all of it.

Written 2026-09-16. Commands are verified against `main` `22955c5a8` and the 9/14 Codex orchestrator's live runs.
**Updated 2026-09-17:** section 3a carries Vincent's standing authority to run as many tasks as reasonable, the concurrency limits, and what counts as dangerous. Crews run Claude-only in Docker on the Gmail account until Codex resets on 2026-09-22, and a merge that removes or renames a symbol now needs the propagation check (`nsc-main-orchestrator-guide.md` section 5).

---

## 1. Authority

**You may, without asking:**
- read anything;
- run `status`, `dependencies`, `readiness`, `worker-status`, `inspect-result`, `checkout`, `taskcontrol` reads, and the viewer API;
- run `prepare`, `scope`, `reserve`, `settle-worker`, `post-crew`, `sync-candidate`, `refresh-prepared` and `stop-worker` (cooperative);
- `integrate` a candidate Vincent approved;
- update `external-work-ids.json` for your own non-crew work;
- write your own journal sections;
- choose which eligible task goes next, within Vincent's priorities.

**Ask Vincent first:**
- every provider launch (`start-worker`/`run-worker --authorize-provider-spend`) unless he gave a standing go for that exact batch;
- `--allow-resource-overlap` for concurrent scene work;
- `stop-worker --force`;
- moving any record aside;
- anything that touches GitHub.

**Never:**
- call `review --decision approve` without Vincent's words approving that exact commit;
- push;
- run `run-graph`/`graph-preflight` on the main project, which is retired for now;
- do GER or decomposition (hand off instead);
- edit task contracts;
- delete checkouts or records;
- kill a process you have not identity-checked;
- rerun a crew whose final write may have been lost (section 7).

**Hand off to:**
- **Decomposition Orchestrator:** a task with `execution_scope: needs_execution_decomposition`, or one a crew or readiness shows is too large for one worker.
- **GER Orchestrator:** the contract is wrong, ambiguous, points at the wrong file, or lacks the spec a crew needs.
- **Orchestrator:** everything else that stops a task: a bug, a tooling gap, a design question. The Orchestrator talks to Vincent.

Behaviour Vincent asked for on 9/14:
- keep work moving, and aim for **3 tasks running**;
- message when you select a task;
- report a blocker immediately, mark that task unavailable, then keep scanning for other work;
- never go idle without saying so;
- don't stop the whole graph for one task's problem.

---

## 2. Startup (every session)

1. Read `AGENTS.md`, `Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md`, the runbook, and the newest sections of `graph-lead-journal.md`. The journal holds the **unavailable-task list**, holds, and recent decisions.
2. Run the runbook's section 2 checks: Source branch, HEAD and dirty state; running processes; Docker; `taskcontrol validate`.
3. Confirm Docker logins for the worker config you will use (runbook sections 3.2 and 3.3).
4. Make sure the viewer runs on the live pair at 8828 (runbook section 4). Viewer colors are a hint; records are the truth.
5. List the live task records:

   ```powershell
   Get-ChildItem C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\NSC-*.json | Where-Object Name -notmatch 'decomposition|materialization'
   ```

   For each one you might touch, read its `status`, `worker`, `candidate` and `approval`. **Retained unfinished candidates come before fresh work.**

Shell setup used below (PowerShell):

```powershell
$S = 'C:\NSC\NSC\NoSafeCircle'
$R = 'C:\NSC\NoSafeCircle-AssistantCheckouts'
$REC = "$R\.assistant-control"
Set-Location $S
```

Every AssistantControl command is `python -m Pipeline.AssistantControl --source $S --checkout-root $R <subcommand> ...`. The globals **must** come before the subcommand.

---

## 3. Choosing a task

1. Candidates: `python -B Pipeline/TaskGraph/taskcontrol.py states --state not_delivered` (add `--json` to filter).
2. Drop any task that:
   - is on the journal's unavailable list, or depends on one;
   - has `execution_scope: needs_execution_decomposition` or `decomposition_state: decomposed` (use `taskcontrol.py show NSC-###`);
   - is awaiting a design decision or contract revision per the journal. On 9/16 that was NSC-007, 008, 009, 030 and 078 (Claude was delegated to decide them), NSC-085 and 088 (approved, revision pending) and NSC-066 (contract points at the wrong builder);
   - already has a live record with a running worker or a pending candidate;
   - is a document-only kind (for example NSC-059), which the worker route does not support.
3. For each survivor:

   ```powershell
   python -m Pipeline.AssistantControl --source $S --checkout-root $R dependencies NSC-075
   python -m Pipeline.AssistantControl --source $S --checkout-root $R readiness NSC-075 --capacity 3
   ```

   `readiness` lists blockers: dependency evidence, checkout/scope, capacity, resource reservations, conflicting Source edits. **`readiness` defaults to capacity 1**, so always pass `--capacity 3`.
4. Priorities:
   - Vincent's current goal first. On 9/16 it was eight-direction wizard movement (**NSC-075 rev 2**).
     - That task is **already in progress in the branch-recovery session**: Codex branch `codex/nsc075-eight-direction-20260916`, being verified in `C:\nscrev\branch-verify`.
     - **Do not start a crew for NSC-075.** Check the journal for its status.
   - Then visual identity before behaviour (show the object before tuning its speed or health).
   - Then everything else.
5. Two tasks that claim the same scene or builder file (for example `DoorPrototypeGlobalSceneBuilder.cs`, `DoorPrototype.unity`) serialize by default. Running them together needs Vincent's OK and `--allow-resource-overlap` on `readiness` and `reserve`; each works in its own checkout and they are integrated one at a time.
6. **Art goes to the Art Director, not a crew.**
   - **Source-art tasks:** contract `type` of `art-acquisition` or a source-art kind such as `wizard-source-art-correction`, `wizard-cardinal-source-art` or `enemy-walk-source-art`. Hand them to the **Art Director Agent** session: message it by title (`C:\NSC\nsc-agent-directory.md`, section 5) with the brief from `C:\NSC\nsc-agent-launch-prompts.md` (Art Director section). The `art-director` subagent is only a fallback, for when no Art Director session is running and Vincent agrees.
   - **Integration tasks that put art on screen** (NSC-075, NSC-077, NSC-079-084) still run through crews. Before Vincent's Unity test, have the Art Director check the renders or screenshots against the art bible. Its notes go in the two-line ask to Vincent.
   - See `C:\NSC\nsc-art-director-guide.md`, section 1.

---

## 3a. How many tasks at once (Vincent, 2026-09-17)

His words: "They should be doing as many tasks as they see reasonable without getting dangerous."

**You no longer ask before each crew launch.** Pick eligible tasks and run them. Start the next one while the last is running, as section 4.5 already says.

**Reasonable, today:**
- **Up to 3 crews running at once.** Each needs its own checkout and container. Raise it only once `task_run.py` telemetry shows what a task really costs, and say so in the journal when you do.
- **Crew provider: Claude in Docker** with `worker-claude-sonnet-high.json` remains the default. **Codex is no longer off** — the first Pro account came back 2026-09-20 and the second resets 2026-09-22 18:55 local. **Before pairing a crew across providers, verify the model actually reached the container** (`actual_model` in the run result): the `--env` forward pools only on the same-provider path, so a mixed pair can silently run defaults while reporting success.
- **Check the account before a batch:** `claude -p "/usage"` should show `cathode26@gmail.com`. Stop starting new crews past about 60% of its weekly limit and tell Vincent.

**Dangerous, so stop and ask:**
- two tasks that claim the same scene or builder file (section 3, item 5). `--allow-resource-overlap` still needs his word;
- a contract that isn't review-clean, or whose dependencies aren't conformant;
- more than one Unity run at a time, or a Unity run while another agent has one going;
- more than one Source-moving operation at a time: integrate, sync-candidate, apply-decomposition and contract commits all share `main`;
- a task whose candidate fails materialization twice, or any failure you can't explain. Ask Astra (`C:\NSC\CLAUDE.md`) before a third attempt;
- anything that would push, delete, or move work outside the checkout.

**Still his, every time:** his own test of the game before integration (section 4.7), merges of side branches, and pushes (the Release Agent's lane).

---

## 4. Running one task

Use a readable, unique **lease id** and **run id**, for example `task-orch-nsc075-20260917` and `task-orch-nsc075-20260917-1`.

### 4.1 Prepare the checkout

```powershell
$head = git -C $S rev-parse HEAD
python -m Pipeline.AssistantControl --source $S --checkout-root $R prepare NSC-075 --source-commit $head
```

- This creates `$R\NSC-075` on branch `assistant/NSC-075`, cloned from the committed Source. Uncommitted edits in Vincent's project are never copied.
- It is idempotent, and it refuses an existing unowned folder.
- A clean, never-started checkout pinned to an old commit: `refresh-prepared NSC-075 --source-commit $head`.
- A checkout that already ran must use the candidate path instead: `sync-candidate` or `revise`.
- Speed tip: copy `Library` from another warm checkout before the first Unity run.

### 4.2 Scope

Write the scope plan next to the other plans in `$REC`. Paths come from the contract's `exclusive_resources` and acceptance criteria: existing files you will edit, and new files you will create. Include `.meta` companions only when the contract names them.

This example uses paths from NSC-075's `exclusive_resources`. Always derive them from the task's own contract (`taskcontrol.py show NSC-###`). The format matches `nsc043-scope-plan.json` in `$REC`.

```json
{
  "existing_implementation_paths": [
    "Assets/NoSafeCircle/DoorPrototype/Scripts/WizardAnimationController.cs",
    "Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs"
  ],
  "new_implementation_paths": [],
  "existing_test_paths": ["Assets/NoSafeCircle/DoorPrototype/Tests/Editor/WizardArtIntegrationTests.cs"],
  "new_test_paths": []
}
```

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R scope NSC-075 --plan $REC\nsc075-scope-plan.json --lease-id task-orch-nsc075-20260917
```

Vincent's rule: an undeclared new script or test path, or an outdated clean contract record, is **not** a reason to stop. Scope what the task needs; the crew may add needed files in its own checkout.

### 4.3 Reserve

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R reserve NSC-075 --run-id task-orch-nsc075-20260917-1 --capacity 3
```

Add `--allow-resource-overlap` only for Vincent-authorized concurrent scene work.

### 4.4 Launch the crew (no ask needed, within section 3a's limits)

**The dispatch sequence, which existed in no document until 2026-09-18:**

```text
settle -> retire-worker -> refresh-prepared -> scope -> reserve -> start-worker
```

Learned by hitting all four gates in one night after a cancelled run. **`scope` refusing with "worker or candidate work is already
underway" is correct behaviour demanding an explicit retire, not a defect** - it was reported as a bug and that report was wrong.
**Restore a candidate BEFORE retiring, never after:** retire leaves a `ready_pending` launch that makes restore refuse with "worker is
not settled", and retire has no undo.

**Pre-flight before spending an hour of crew time:** contract hash == policy hash **at the live head** (main moved ten times in one
night), the contract names its gate types, and the scope plan authorises every file the acceptance criteria actually require. NSC-097
burned 25 minutes and returned BLOCKED purely because its scope plan had an empty `new_implementation_paths` while AC-002 needed a
runtime file.

**Before you launch: a worker's lifetime can be smaller than one role's budget, so the stock profile cannot finish a repair cycle.**
Verified 2026-09-18:

```
worker-claude-sonnet-high.json   timeout_seconds : 3600
ROLE_BUDGET_DEFAULTS             implementer,full: (96, 3600.0)
  run_crew.py:1919-1922          test_author,full: (96, 3600.0)
```

**One role may legally consume the entire worker lifetime.** Measured on NSC-007, run `task-orch-nsc007-20260918-2`:

| Phase | Seconds |
|---|---|
| Implementer 1 | 642.1 |
| Test Author 1 | **2138.6** |
| Validator 1 | 571.8 -> `needs_changes`, which starts the repair cycle |
| Implementer 2 | 59.7 |
| Test Author 2 | killed at ~65 |
| **Total elapsed** | **3604s against a 3600 ceiling** |

The host worker was killed mid-role and wrote no `crew_result.json`. **This is a timeout, not a hang or a crash** - say so plainly, because
the symptom (silence, a container still up, the task going purple in the viewer) reads like a hang and sends people hunting the wrong thing.

**The fix needs no merge: `timeout_seconds` is a dispatch config value, not code.** Launch with **`worker-claude-sonnet-long.json`**
(`timeout_seconds: 10800`), everything else identical. A complete run with both cycles plausibly needs ~6700s, so three hours leaves real
headroom. NSC-097 was dispatched that way on 2026-09-18.

**And raising a role budget moves the wall, it does not remove it.** The test-author raise merged that evening was right on its own terms -
Test Author 1 would have died at the old 1200s default - but it let one role eat 2138s of the worker's 3600s, so the repair cycle hit the
worker ceiling instead. **Quote headroom from the worker's remaining lifetime, never from the role budget**; that error was reported to
Vincent as "40 minutes of headroom" when roughly 25 remained.


```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R start-worker NSC-075 --run-id task-orch-nsc075-20260917-1 --lease-id task-orch-nsc075-20260917 --config $REC\worker-claude-sonnet-high.json --authorize-provider-spend
```

- `start-worker` detaches; `run-worker` stays in the foreground.
- Worker configs:
  - `worker-claude-sonnet-high.json`: Claude Sonnet 5, `crew_profile: full`, `validation_profile: full_relevant`, 3600 s. This is the normal choice.
  - `worker-codex-sol-high.json`: Codex gpt-5.6-sol high, 1800 s.
  - `Pipeline\AssistantControl\worker-haiku.example.json`: Haiku/`lean`/`targeted`, cheap demos only.
- **Don't mix** `crew_profile: full` with `validation_profile: targeted`. The worker exits at once, making no provider call.
- The `full` crew is implementer, then Unity test author, then validator. The old contract-locality auditor was removed.
- Put the task in the viewer's blue state only through a real worker. For non-crew work use `external-work-ids.json` (runbook section 4.4).

### 4.5 Monitor

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R worker-status NSC-075
Get-ChildItem $REC\worker-runs\NSC-075 -Recurse -Filter *.log | Sort-Object LastWriteTime | Select-Object -Last 3
```

- The crew's result lands in `$R\NSC-075\Pipeline\ExecutionCrew\outputs\<crew_run_id>\crew_result.json`.
- `inspect-result NSC-075` re-hashes and summarizes the result.
- A crew typically takes 8-60 minutes.
- **Do not babysit one task.** Start the next eligible task while this one runs.

### 4.6 Settle, then post-crew

When `worker-status` shows the worker ended:

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R settle-worker NSC-075 --run-id task-orch-nsc075-20260917-1
python -m Pipeline.AssistantControl --source $S --checkout-root $R post-crew NSC-075 --run-id <crew_run_id> --config $REC\worker-claude-sonnet-high.json
```

**`post-crew` takes the crew's own run id.** That is `worker.crew_run_id` in `NSC-075.json`, for example `nsc-075-20260917t101500z`. It is not your launch run id; the wrong id fails with "ExecutionCrew receipt was not authenticated".

`post-crew` registers the candidate commit. If the candidate edits a registered Unity builder, it rebuilds the scene and runs the focused Unity tests. Outcomes:

| `status` | Meaning | Next |
|---|---|---|
| `awaiting_human` | Candidate ready. `automated_unity_validation: not_run` means the task has no or stale validation policy; say so honestly, it is not a pass. | Section 4.7 |
| `NEEDS_MATERIALIZATION` | Unity couldn't be resolved before launch; candidate kept | Fix Unity availability, then run the printed `materialize-candidate` command |
| `materialization_failed` | Unity build failed after start (often an unexpected `.meta`) | Report to the Orchestrator with the journal path. Recovery commands exist only for NSC-032's case. |
| `validation_failed` | Focused Unity tests failed | Report it; the printed `revise` command starts a fixing crew after Vincent's go |

A crew `rejected` with `role made no required file modification` means the behaviour already exists. See section 6.

### 4.7 Vincent's test

**Mixed pipeline first** (Vincent, 2026-09-16: "When our game agent does pipeline work, we want to prefer a mixed agent pipeline").
- **Mixed crews already exist as provider profiles:** `claude-architect-balanced` and `codex-architect-balanced` (`Pipeline/TaskReviewAgent/provider_profiles.py`; `Docs/AI-Pipeline/PROVIDER_PROFILES_AND_BUDGET_ROUTING.md`). In them, the implementer and test author share one provider (chosen by token balance), and the validator and lead developer use the other.
- **Not usable through AssistantControl yet (checked 2026-09-16).** A worker config's `provider_profile` reaches the crew unexpanded and the run would fail, so don't set it (`C:\nscrev\reports\mixed-provider-crews-verify-report.md`). After the Pipeline Maintainer Agent's small fix merges, set `"provider_profile": "codex-architect-balanced"` in the worker config.
- **Until then, or whenever a crew runs on one provider,** get the other provider's view of the candidate before Vincent's test:
  - a **Codex adversarial review** of the candidate commit (`C:\NSC\nsc-codex-jobs-guide.md`, section 4.2), for a crew run on Claude;
  - a fresh Claude review, for a crew run on Codex.
- Put the verdict in the ask to Vincent. It is advisory; Vincent's Unity test still decides.

Tell Vincent, in two or three lines:
- which task;
- the **exact checkout folder** (`C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-075`);
- the **exact commit**;
- what to open in Unity and what to check (from `post-crew`'s reproduction instructions);
- the question "pass or fail?".

Only after he answers:

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R review NSC-075 --tested-commit <commit> --decision approve --message "Vincent approved <commit> on 2026-09-17: <his words>"
```

- Use `--decision reject` with his feedback when he fails it.
- If validation did not run, the message must say so; don't imply a test pass.

### 4.8 Integrate (Source-moving: one at a time)

```powershell
if (git -C $S status --porcelain) { throw 'Source dirty: stop and check (runbook section 6)' }
$head = git -C $S rev-parse HEAD
python -m Pipeline.AssistantControl --source $S --checkout-root $R integrate NSC-075 --source-commit $head --target-branch main
python -B Pipeline/TaskGraph/taskcontrol.py validate
```

- `integrate` is a local fast-forward only. It refuses local edits and never pushes.
- **If Source moved** since the candidate, run `sync-candidate NSC-075 --candidate-commit <commit> --source-commit $head`. It creates a **new** commit that Vincent must test and approve again. Scene or builder conflicts are kept for a crew to reconcile, never auto-resolved.
- With several approved candidates, integrate one, sync the next, and have it re-tested. Batch approvals get silently invalidated.
- The branch-recovery session may also be merging into `main`. Check the journal and HEAD right before integrating.

### 4.9 Move the finished task to the successful-tasks folder (required)

Vincent keeps every **successful** task as a standalone Unity project in **`C:\NSC\SuccessfullTasks\<TASK-ID>`**. The folder name really is spelled `SuccessfullTasks`.

A task is successful once it is `conformant`: integrated, **and** delivery recorded (`nsc-delivery-evidence-guide.md`). The steps are the same as the Integration Steward guide, section 6.2. For a task you ran through AssistantControl, once the candidate is approved, integrated and delivered:

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R preserve-success NSC-075
Test-Path C:\NSC\SuccessfullTasks\NSC-075
git -C C:\NSC\SuccessfullTasks\NSC-075 log --oneline -1    # must show the exact approved commit
```

- The command **copies**. It clones the exact approved, integrated commit with its Git history, excluding Unity `Library` and cache. The worker checkout stays in `C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-075`.
- Then copy the task checkout's `Library` so the archive opens without a long import. The `NSC-042` precedent includes it:

  ```powershell
  robocopy C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-075\Library C:\NSC\SuccessfullTasks\NSC-075\Library /E
  ```

- **Never delete the task's `NSC-###` branch** (Vincent's rule, 9/16).
- **Don't move or delete the worker checkout by hand.** The task records and the viewer point at it, and Git worktree bookkeeping would break. Retire old checkouts through the Integration Steward's cleanup, with Vincent's OK.
- The command refuses when:
  - the task isn't Vincent-approved and integrated;
  - the destination already exists for another version (it never overwrites; for example `SuccessfullTasks\NSC-042` from 9/10 is kept as is);
  - the copy was interrupted (the staging folder is kept for inspection).
- The viewer shows the saved folder once it has checked the commit against the integration record.
- Then record delivery evidence so the task counts as done for dependencies (`nsc-delivery-evidence-guide.md`).
- A task counts as **complete** only when all four hold, in this order:
  1. integrated into `main`;
  2. delivery recorded (`taskcontrol state` = `conformant`);
  3. archived in `SuccessfullTasks` (with `Library`);
  4. its journal entry written.
- If delivery isn't recorded yet, archive after it is.

### 4.10 Journal

Append to `graph-lead-journal.md`:

```markdown
## 2026-09-17 Task Orchestrator NSC-075 <outcome>
- Source <sha>; checkout; lease/run ids; crew_run_id; worker config
- candidate <sha>; post-crew status; Vincent decision (quote); integrated as <sha> / not
- preserved: C:\NSC\SuccessfullTasks\NSC-075 at <sha> / not yet; delivery record: <DEL id / commit> / pending
- blockers; evidence paths
```

---

## 5. Stopping a worker

```powershell
python -m Pipeline.AssistantControl --source $S --checkout-root $R stop-worker NSC-075 --run-id <run>          # cooperative request
python -m Pipeline.AssistantControl --source $S --checkout-root $R worker-status NSC-075                        # confirm it ended
python -m Pipeline.AssistantControl --source $S --checkout-root $R stop-worker NSC-075 --run-id <run> --force  # only with Vincent's OK, after identity check
python -m Pipeline.AssistantControl --source $S --checkout-root $R settle-worker NSC-075 --run-id <run>
```

- `--force` stops the owned process tree and run-bound containers, and preserves files.
- For container cleanup after a terminal worker, use `maintenance-plan NSC-075 --action cleanup-worker-docker --run-id <run>` then `maintenance-run <ticket.json>`. Never `docker rm`.

---

## 6. Known traps

- **Already implemented.**
  - Symptom: a crew rejected with "role made no required file modification". Seen on NSC-003, 005, 038, 040 and 069.
  - There is **no** command on `main` to adopt existing code as delivered.
  - Don't make a crew add a meaningless edit.
  - Mark the task unavailable, report it to the Orchestrator, and let Vincent decide. He may confirm it done, which the Orchestrator records with `human-complete-ids.json` for display only.
- **Missing validation policy.** A new or decomposed task often has no entry in `Pipeline/TaskReviewAgent/authoritative_validation_policy.json`. `post-crew` then keeps the candidate `awaiting_human` with `not_run`. That is fine; tell Vincent tests were not run automatically.
- **Unity-generated `.meta` files** outside the scope boundary break materialization or clean-tree checks. Commit genuinely needed `.meta` files by exact path; report anything else.
- **Stale checkout.** A preserved checkout pinned to an old Source won't resume. Clean and never-started: `refresh-prepared`. Anything else: report it.
- **Two agents, one checkout.** Before writing in a checkout, check `git status` there and `worker-status`. Never start a second crew or agent on a checkout that has unexpected edits or a live worker.
- **Dependencies.** A dependency counts as delivered only through TaskGraph evidence or an assistant-approved local integration. Pass `--checkout-root` before `dependencies` so integrations count. A green overlay (`human-complete-ids.json`) does not unlock dependents.
- **Source dirty.** The 36 phantom wizard and tile files block `integrate`. Don't revert them without Vincent (runbook section 6).
- **The viewer lies in two known ways.** Approved or integrating candidates show blue. A dirty-but-harmless checkout can show "blocked" while `readiness`/records say otherwise. Trust the records.
- **Worker config pairing.** `full` crew + `targeted` validation exits immediately. Use the checked-in configs.
- **Capacity is per Source.** A stale reservation from another checkout root on the same Source eats a slot. `settle-worker` releases it.

## 7. Never rerun a crew whose final write may be lost

**Symptom:** the worker process is gone, but `NSC-###.json` still says the worker is `running`, and `worker-status` can't reconcile it.

The worker may have succeeded and lost its final record write (the NSC-1163 class). The only copy of its result is the receipt at `<checkout root>\.task-review-agent\NSC-###.execution.json`, or the crew's `crew_result.json`. A rerun overwrites it.

Mark the task unavailable, preserve everything, and escalate to the Orchestrator. The recovery command built on 9/13 (`recover-worker-result`) is **not on `main`**.

---

## 8. Marking a task unavailable

Per `GRAPH_TEAM_STARTUP.md`:
1. Stop work on that task only, using a safe exact stop path.
2. Preserve its checkout and evidence.
3. Append it to the journal's unavailable list: task id, run ids, Source sha, candidate sha, failure text, evidence paths.
4. Exclude it and its dependents from every selection. Re-check the list before every start.
5. Report the packet to the Orchestrator, then continue other eligible work.
6. Reconsider the task only when the Orchestrator says so, and after fresh readiness checks.

There is no CLI hold, and the viewer's `held-task-ids.json` does not stop anything. The journal list is the hold.

---

## 9. Reporting to Vincent

Keep it short. Lead with what he must do:

- "Test NSC-075: open `C:\NSC\NoSafeCircle-AssistantCheckouts\NSC-075` in Unity (commit `abc1234`), walk the wizard in all 8 directions. Pass or fail?"
- "Nothing needed. NSC-075 crew running (~20 min); NSC-049 queued behind it (same builder)."
- "Need your OK to spend: start crews for NSC-075 and NSC-090 (Sonnet, about 20 min each)?"

Put details in the journal, not in chat.
