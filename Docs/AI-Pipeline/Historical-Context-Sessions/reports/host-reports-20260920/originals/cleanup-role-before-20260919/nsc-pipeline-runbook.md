# No Safe Circle pipeline runbook (main project)

Written 2026-09-16. It covers the main project only; the synthetic gauntlet was a test harness.

Sources:
- the Codex orchestrator session of 9/13-9/14;
- the Claude sessions of 9/15-9/16, including the demo run;
- the code and docs on local `main` at `22955c5a8`;
- the graph-lead journal, the reports in `C:\nscrev\reports`, and memory notes.

Every command below was checked against `main` or seen working in those sessions. If a doc disagrees with `--help`, trust `--help`.

## The document set

| File | For |
|---|---|
| `C:\NSC\nsc-pipeline-runbook.md` (this file) | Everyone. Docker, logins, viewer basics, Unity rules, roles, troubleshooting. |
| `C:\NSC\nsc-agent-launch-prompts.md` | Paste-ready prompts to start each agent role |
| `C:\NSC\nsc-agent-directory.md` | **Which agent owns which work**, the helper subagent types, how to hand off out-of-lane work, how to message a session by its sidebar title, and how to add agents |
| `C:\NSC\nsc-agent-roster.md` | Every standing agent session: exact title, model, state file (`C:\NSC\agent-state\`), start or resume prompts, and the checkpoint prompt for moving an agent to another Claude account |
| `C:\NSC\tools\session\README.md` and `nsc_session_digest.py` | Replacing an agent session: a read-only digest of an old session's transcript (`list`, `digest --title`), plus the Retire, Successor and Recovery prompts for a full context or an account switch |
| `C:\nscrev\reports\handoffs\BOARD.md` | The live handoff board: one row per handoff between agents, with status |
| `C:\Users\VincentLiguori\.claude\agents\*.md` | Custom agents: `art-director`, `pipeline-maintainer`, `pipeline-reviewer`, `merge-verifier`, `unity-runner`, `delivery-evidence`, `test-runner`, `ger-drafter`, `pixellab-batch-recorder`, `scribe` |
| `C:\NSC\nsc-main-orchestrator-guide.md` | Main Orchestrator: Vincent's contact, triage, main-write coordination, budgets |
| `C:\NSC\nsc-task-orchestrator-guide.md` | Task Orchestrator: normal game tasks through crews, Vincent's test, integrate, archive |
| `C:\NSC\nsc-ger-orchestrator-guide.md` | GER Orchestrator: contract improvement and commits |
| `C:\NSC\nsc-decomposition-orchestrator-guide.md` | Decomposition Orchestrator: splitting oversized tasks |
| `C:\NSC\nsc-integration-steward-guide.md` | Integration Steward: branches, worktrees, merges, archives to `SuccessfullTasks`, pushes |
| `C:\NSC\nsc-release-agent-guide.md` | Release Agent session: pushes on Vincent's word, CI through temporary PRs (fixing CI or handing failures to owners), WebGL builds and github.io publishing |
| `C:\NSC\nsc-cleanup-agent-guide.md` | Branch and worktree triage and disk cleanup procedure. Owned by the Cleanup Agent, running since 2026-09-18: a plan plus a dry-run script that Vincent runs |
| `C:\NSC\nsc-art-director-guide.md` | Art Director: routing all art to the Art Director Agent session, PixelLab procedures, provenance, review packages, Vincent's picks, `.meta` rules, open art questions, art queue. It replaces the Art Producer guide. |
| `C:\Users\VincentLiguori\.claude\agents\art-director.md` | The `art-director` Claude Code agent. It is the **art bible**: vision, palette, light, scale, readability checks, and the identity of every approved asset family with reference images. |
| `C:\NSC\CLAUDE.md` | Loaded by every Claude session under `C:\NSC`: route all art to `art-director`; start from this runbook |
| `C:\NSC\nsc-pipeline-maintainer-guide.md` | Pipeline Maintainer and independent Reviewer: fixing the pipeline, porting unmerged fixes. Runs as the **Pipeline Maintainer Agent** session (rules: `C:\Users\VincentLiguori\.claude\agents\pipeline-maintainer.md`); reviews by `pipeline-reviewer` subagents (`C:\Users\VincentLiguori\.claude\agents\pipeline-reviewer.md`). |
| `C:\NSC\nsc-watcher-guide.md` | Watcher: read-only health checks and alerts |
| `C:\NSC\nsc-delivery-evidence-guide.md` | Everyone: how a task becomes `conformant` (delivery records) |
| `C:\NSC\nsc-codex-jobs-guide.md` | Everyone: running Codex bulk jobs safely in Docker clones. Section 4.4: **ask Astra when stuck or when things go bad**. Section 4.3: **Claude helper jobs in Docker on the Gmail account**, templates in `C:\nscrev\claude-jobs\templates\` |
| `C:\NSC\nsc-checkpoint-handoff-guide.md` | Everyone: checkpoints, handoffs, resuming after limits |
| `C:\NSC\nsc-quiet-windows-guide.md` | Everyone: never open a visible console window on Vincent's desktop; the flags for Python, PowerShell, background jobs and Unity |
| `C:\NSC\nsc-viewer-guide.md` | Everyone who touches the viewer: control script, reading the page, overlays, API, what's wrong, improvement plan |
| `C:\NSC\nsc-viewer-agent-guide.md` | Viewer Agent session: owns the viewer process and its display overlays; how other agents send it `VIEWER:` requests; keeping the page true |
| `C:\NSC\nsc-pipeline-problems.md` | The fix list: everything known to be broken or confusing |
| `C:\NSC\tools\viewer\nsc_viewer.py` | Viewer control: start, stop, status, list, task, and overlay edits. Use it instead of hand edits. |
| `C:\NSC\tools\viewer\nsc_watch.py` | Read-only health snapshot with alerts |
| `C:\NSC\tools\ger\hold_ger_task.py` | Add or drop a GER display hold |

---

## 0. Rules that apply to every agent

1. **Never push** to GitHub unless Vincent says so for that exact push. From 2026-09-17 the **Release Agent** pushes, and one "push" from Vincent covers one release run: the CI branch, the temporary PR, fixes, and the green commit to `main` (Vincent: "Why dont you want the release agent to push when we say so and handle what is wrong with CI and task which ever agents needs to fix it or fix the CI issues?"; `nsc-release-agent-guide.md` section 2). Local `main` is 166 commits ahead (2026-09-17) of `origin/main` on purpose.
2. **One Source-moving operation at a time.** `integrate`, `sync-candidate`, `apply-decomposition` and contract commits all move `C:\NSC\NSC\NoSafeCircle` `main`.
   - Before any of them, re-read `git rev-parse HEAD` and `git status --porcelain`.
   - Abort if HEAD moved or the tree is dirty with anything you did not expect.
   - Several agents share this `main`.
   - **Removed or renamed a symbol in that merge?** Run the propagation check before journaling the end: grep the tree for the old name including `.github/workflows/*.yml`, and run only the tests that reference it (`nsc-main-orchestrator-guide.md` section 5). PR #134 needed four CI-fix rounds for want of it.
3. **Never approve for Vincent.** `review --decision approve` runs only after Vincent's own words approve that exact commit.
4. **Provider spend needs his go.** That covers `start-worker`/`run-worker` with `--authorize-provider-spend`, `decompose`, GER rounds, and Codex "do" jobs. A standing "go ahead with X" covers only X.
   - **Standing exception (Vincent, 2026-09-16):** Codex **review** jobs on our own work and on merge candidates are pre-approved, including host runs. Pause them once Codex weekly quota passes 90%. See `nsc-codex-jobs-guide.md` section 4.2.
   - **Approved 2026-09-17** (Vincent: "give all the agents everything they want"):
     - the Art Director's one-off Codex "do" job to build the art-review toolkit and a PixelLab spend ledger;
     - the GER Agent's medium-effort Codex jobs for mechanical contract cascades (about weekly);
     - the Pipeline Maintainer's Unity proof runs in its own clones through `unity-runner`. It tells the Game Agent first, and only one Unity runs at a time.
   - **Approved 2026-09-17** (Vincent: "use the pipeline for sub agents"): Docker Claude helper jobs on the Gmail account, for helper work in each agent's own lane. Stop them when a job reports a usage limit. See `nsc-codex-jobs-guide.md` section 4.3.
   - **Approved 2026-09-17** (Vincent: "When things go [bad], Ask Codex, use a Astra for advice. If that advice doesnt help, then ask me."): read-only Codex advice jobs, which ask Astra about questions an agent is stuck on and when things go bad. Use Astra once Codex is updated. See `nsc-codex-jobs-guide.md` section 4.4.
   - Claude Code's auto-mode classifier refuses paid launches from subagents, and sometimes from the main session. Do not work around a refusal. Ask Vincent.
5. **Don't trust viewer colors or PIDs alone.** The durable records under `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\` and the `graph-plan`/`worker-status`/`readiness` output are the truth.
6. **Never delete or hand-edit durable records** under `.assistant-control`. The exceptions are the three display overlays in section 4.4. Never delete a task checkout to "retry", and never `docker rm` an owned container.
   - If a record must move aside, ask Vincent. Move it to an archive name; never delete it.
7. **Never run a wipe or reset for a run that might be alive.** A blank viewer is not proof a run is dead.
8. **Keep replies to Vincent short.** Lead with what he must do, and put details in files.
9. **Write long scripts to files, then run them.**

    **And write Windows paths with forward slashes in any generated text.** Backslash escapes get eaten by the shell or by a
    format string and become **real control characters**: `\n` a newline, `\r` a CR, `\a` a 0x07. This has now corrupted a board
    row, a memory index line and a report path - **three times in this workspace**, each time producing a file that looks fine in a
    terminal because CR repositions the cursor. Use `C:/nscrev/...` in appended lines, and scan the bytes afterwards rather than
    trusting how it renders. Long quoted heredocs in the Bash tool can silently run nothing. `sed -i` in Bash strips CRLF.
   - **No console pop-ups.** Every spawned process gets `CREATE_NO_WINDOW` (`0x08000000`) in Python, or `-WindowStyle Hidden` / `-NoNewWindow` with `Start-Process`. Never `DETACHED_PROCESS`, `start` or `cmd /c start`. See `nsc-quiet-windows-guide.md`.
10. **Commits use `.invalid` identities.** Examples: `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`, `No Safe Circle Task Design GER <task-design-ger@nosafecircle.invalid>`. Stage exact paths only. **`rebase`, `cherry-pick`, `am` and `commit --amend` set the committer from git config**, so pass the identity to them too (`git -c user.name="..." -c user.email="...@nosafecircle.invalid" rebase ...`). On 2026-09-17, 11 unpushed commits were found with Vincent's real email as committer.
11. **Never delete or propose deleting an `NSC-###` task branch** (Vincent, 2026-09-16). Successful tasks are archived as usable projects in `C:\NSC\SuccessfullTasks\<TASK-ID>`.
12. **All 2D art goes to the Art Director Agent session** (Vincent, 2026-09-16). That covers PixelLab generation, repairs, new facings or animations, review packages, recording picks, and art-direction advice. The `art-director` subagent is only a fallback, when no session runs and Vincent agrees. Never hand art to a general-purpose subagent. See `C:\NSC\nsc-art-director-guide.md`, section 1.
13. **Work outside your lane goes to its owner by name** (Vincent, 2026-09-16). `C:\NSC\nsc-agent-directory.md` lists every agent session, which work each owns, and how to message a session by its sidebar title. Don't do another agent's work; hand it off and tell Vincent in one line.
14. **A pause stops new work, not release work** (Vincent, 2026-09-17: "we are paused on them to release and that they may ask for fixes from other agents and when the release agent asks for work, the agents that are paused must do that work"). While the team is paused, the Release Agent keeps going, and a fix it asks you for is work you do now: that fix only, then back to paused. Spend, Unity, merge and push approvals are unchanged.

---

15. **A direct fix's artifact is unclaimed by every contract** (Game Agent and GER Agent, 2026-09-17). A file created outside a task contract is in no `exclusive_resources` list, so two tasks can edit it concurrently and only collide at integration. Name the files a direct fix created, and ask the GER Agent to fold them into the owning task's resources. **Live worked example, still unfixed:** `IsometricSortingRenderTests.cs` was written as a direct fix on 2026-09-17 and **no contract claims it today** - verified with `git grep -l IsometricSortingRenderTests -- Tasks/`, which matches only NSC-075, and NSC-075 mentions it in prose while its `exclusive_resources` do not list it. It was *reported* as being folded into NSC-064; that never happened, and this rule recorded the intention as an accomplished fact. **Someone should fold it in** (Game Agent to raise with the GER Agent). See `nsc-integration-steward-guide.md` section 5a.

16. **A refusal in your session is not a routing problem** (2026-09-17). If a tool call is denied or blocked, you don't hand that same work to another agent, a helper subagent, or the `scribe`, and you don't offer "I'm blocked" as the reason someone else should do it. Say what was refused, to Vincent, and let it wait. Two examples from one evening, both caught and reported by the Game Agent: a refused journal append written by the `scribe` instead, and a doc commit offered to the Documentation Agent because canonical writes were refused. **The second landed with the right agent anyway** - doc commits are the Documentation Agent's lane - and that is the distinction: take work because it is yours, never because someone else is blocked. CLAUDE.md states the agent-to-agent half of this rule; the helper-subagent half is the one that slips through.

17. **A crew's worker lifetime can be smaller than one role's budget** (measured 2026-09-18). The stock profile gives the worker 3600s while a single full-profile role may take 3600s, so a repair cycle cannot finish. Dispatch with `worker-claude-sonnet-long.json` (10800s) - it is a config value, not code, so it needs no merge. **Quote headroom from the worker's remaining lifetime, not from the role budget.** A worker killed at its ceiling writes no `crew_result.json` and looks exactly like a hang. `nsc-task-orchestrator-guide.md` section 4.4.

18. **Never conclude about runtime behaviour from a static artefact** (three wrong diagnoses in one evening, 2026-09-17/18). A `compose.yaml` block, a code comment and a stdout capture each looked authoritative and each was out of date; the launcher that builds the command was one grep away in every case. **Read the launcher, or inspect the running thing** — `docker inspect <container> --format '{{range .Config.Env}}{{println .}}{{end}}'` settled in seconds what two agents argued about from source. **And prefer recording what a run was actually launched with** over leaving readers to infer it: `crew_result.json` already records `role_budgets`, the budget every role really ran under, and that shape cannot rot because the code that launches the run produces it. **Record the variables that were present but NOT forwarded too** - "not forwarded" is otherwise invisible, and it is the exact case that made one override path-dependent and fooled three agents. A record still only says what run N used, so forwarding also needs a test to answer the question before a run exists; there is none today. **The fact that would have prevented both false alarms: `docker compose run --env NAME=VALUE` supplements a service's static `environment:` block rather than being blocked by it** — so a missing entry in `compose.yaml` proves nothing about what a container receives. **But the two launchers forward different classes of variable, so do not claim parity:** `execution_bridge.py:468-472` forwards budget overrides (`NSC_<ROLE>_TURN_LIMIT` / `_TIMEOUT_SECONDS`) to crews and **never forwards a model override at all** - `grep -c MODEL` on that file returns 0. `decomposition_transport.py:73-76` forwards the model, and only on the pooled path. So: **budget overrides reach crews; model overrides are decomposition-only.** The belief the three diagnoses got wrong was that a missing compose entry proved unreachability - that part was false for every case examined.

19. **A measurement that refutes another agent's claim goes to that agent, not only to whoever asked** (Art Director, 2026-09-18). A day after it measured the enemy sprite scale and disproved a "38% size pop", the agent that owned the claim repeated it - the correction had reached the requester and never the source. **Findings propagate by being sent to the owner; nothing else carries them.** If a measurement changes what another agent believes about its own work, message that agent directly and say what it refutes.

20. **Keep a live work queue at a stable path** (Vincent, 2026-09-18: *"every agent should write down their work current work queue / state so they know what they need to do next when they refresh"*). Each agent keeps `C:\NSC\agent-state\<role>-todo.md` - never dated, never renamed, never archived - and **that file is the authority for what is next.** A dated `nsc-handoff-*.md` is frozen the moment it is written, so where the two disagree the todo file wins on *what to do* and the handoff wins on *what was true*. **Each agent writes only its own;** nobody writes another's queue, because only that role knows what half-finished work means. Keep it honest: **delete finished items** rather than ticking them off (the journal is the record of what happened, and a queue that only grows stops being read), name the evidence file for each item, say what "done" looks like, mark each blocker with what unblocks it, and put no narrative in it. Worked example: `C:\NSC\agent-state\pipeline-maintainer-todo.md`. **This is also the other half of the journal rule** (section 1, "Record every handoff in `graph-lead-journal.md`, under your own dated heading")**:** the journal says *what happened*, the board *what was handed over*, the todo file *what is left*. On 2026-09-18, the day of a full succession round, the journal got **6 entries from 4 of 8 agents** - measured, not estimated.

21. **Never move a registered git worktree as a folder** (measured 2026-09-18: **138 registered worktrees on this machine**, 79 under `C:/NSC/_worktrees`, 4 pointing into `C:/nscrev`, and 48 directories in `C:/nscrev` whose `.git` is a file). A bare `Move-Item` or `robocopy` leaves the parent's `.git/worktrees/<name>` pointing at a dead path **and** leaves git believing that branch is still checked out, so **the branch cannot be checked out anywhere until `git worktree prune`**. Doing ~130 by hand without pruning would lock ~130 branches, and **this is the one case where moving something is not reversible by moving it back.** Use `git worktree move` or `git worktree remove`, or a folder move followed by `git worktree prune` in the parent. **Test before you trust a path:** a worktree is a directory whose `.git` is a *file*, not a directory. And **worktree parents cross the directory boundary** - `C:/nscrev/wt-base-sessions` is a worktree of `C:/NSC/ClaudeProviderSessions/NoSafeCircle` - so a cleanup of one tree can break the other. Details: `nsc-cleanup-agent-guide.md`.

22. **The history folder is a waiting room, never a home** (Vincent, 2026-09-18: *"if we go into the history folder and find something of value, it needs to come out of the history folder"*). Quarantined directories live at `C:/NSC-History-20260918` with a `MANIFEST.json` recording where each came from. **If you open something in there and it turns out to matter, take it out** - do not copy it, do not cite it in place, do not leave a note and walk away:

    C:\NSC-History-20260918\RESTORE.ps1 -Name <folder> -Reason "<why>" -Apply

    That logs the restore to `RESTORES.md`. **The habit is what keeps the 2026-10-09 review cheap:** under it, anything still sitting there has been *looked at and left*, rather than never examined. **It does not make the folder safe to delete unread** - see the correction below.

    **CORRECTION, 2026-09-19 — do not delete that folder on the review date without a real audit.** This rule first said its contents would be "junk by construction" and that an empty `RESTORES.md` proved nothing was needed. **Both premises are false**, per the adversarial review of 2026-09-19 (relayed, not re-measured here): **19 of 28 quarantined clones hold branch tips the game repo does not have, 3 were moved while dirty, and 6 `.bundle` files hold commits found nowhere else on this machine.** Separately, `RESTORE.ps1` was moving folders and then **crashing before it logged**, so restores succeeded unlogged - since fixed, but it means an empty log cannot be trusted for anything before the fix. **The waiting-room habit still stands and is still worth keeping** - take a thing out rather than citing it in place - but it buys a cleaner review, not a free deletion.

## 1. What runs where

| Thing | Location / value |
|---|---|
| Canonical game repo (the **Source**) | `C:\NSC\NSC\NoSafeCircle`, branch `main`, local only |
| Live checkout root | `C:\NSC\NoSafeCircle-AssistantCheckouts`, with one clone per task at `<root>\NSC-###` on branch `assistant/NSC-###` |
| Live state records | `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\`. Contents: `NSC-###.json` (checkout/worker/candidate/approval), `NSC-###.decomposition.json`, `decomposition-runs\`, `decomposition-launch\`, `worker-runs\`, `graph-lead-journal.md`, `held-task-ids.json`, `external-work-ids.json`, `human-complete-ids.json`, worker configs `worker-*.json`, `viewer-logs\`. |
| Source-scoped admission registry | `C:\NSC\NSC\NoSafeCircle\.git\assistant-control-admissions.json`. `--capacity` counts here, per Source, not per checkout root. |
| Pipeline CLI | `python -m Pipeline.AssistantControl [--source S] [--checkout-root R] <subcommand>`. `--source`/`--checkout-root` are **global** and must come **before** the subcommand. There are 38 subcommands; run `--help`. |
| Task graph CLI | `python -B Pipeline/TaskGraph/taskcontrol.py validate\|states\|state\|show\|graph`. Run it as a **script path**, not `-m`. `ready`/`authorize` are deliberately disabled: "dispatch policy not enabled". |
| Viewer | `http://127.0.0.1:8828/` (section 4) |
| Docker | Docker Desktop. The compose file is in the repo: `compose.yaml` plus the auto-merged `compose.override.yaml`. Credential volumes: `nosafecircle_claude-config`, `nosafecircle_codex-config`. |
| Host CLIs (used by GER) | `codex` at `C:\Users\VincentLiguori\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`; `claude` at `C:\Users\VincentLiguori\.local\bin\claude.exe`; `gh`; `python` at `C:\Python313\python.exe` |
| **Successful tasks** | `C:\NSC\SuccessfullTasks\<TASK-ID>`: a standalone, openable Unity project (with `Library`) for every **conformant** task. Never overwrite. Precedent: `NSC-042` at `aee1623`. How to create one: Integration Steward guide, section 6.2. The copy comes from the integrated commit; worker checkouts and NSC-### branches stay. |
| Agent tools (outside git) | `C:\NSC\tools\` - `ger`, `jobs`, `viewer`, `astra`, `session`, `art`. **Moved here from `C:\nscrev\<x>-tools` on 2026-09-18**, with a **directory junction left at every old path**, so both spellings still resolve; the doc set was swept to the new paths the same evening. Prefer the new path in anything you write. |
| Tools that did **not** move, deliberately | `C:\nscrev\ger-contract-revisions-20260916\` still holds the only copies of `new_task_commit.py`, `policy_entry_commit.py` and `verify_filter.py`, because it is also the GER Agent's live working area. **So tools live in two places on purpose** - check here before concluding a script is missing, and do not "tidy" that folder into `C:\NSC\tools\` without the GER Agent. |
| GER / decomposition artifacts | `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\{RoomContentGER,TaskDesignGER,<TASK-ID>}` |
| Unity | `C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe` |
| Unity test runner | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File Pipeline\Testing\run_unity_tests_clean.ps1 -TestPlatform EditMode\|PlayMode -TestFilter "A.B.C;A.B.D" -ProjectPath <checkout>` |
| Reports | `C:\nscrev\reports\` |
| Worker configs | `worker-claude-sonnet-high.json` (Claude Sonnet 5, `full` crew, `full_relevant` validation, 3600 s) and `worker-codex-sol-high.json` (Codex gpt-5.6-sol high, 1800 s), both in `.assistant-control`. `Pipeline/AssistantControl/worker-haiku.example.json` is the cheap Haiku/lean demo config. Mixed crews use a `provider_profile` key (`claude-architect-balanced` or `codex-architect-balanced`; see `Docs/AI-Pipeline/PROVIDER_PROFILES_AND_BUDGET_ROUTING.md`); **it doesn't work through `start-worker` yet**, because the profile isn't expanded; don't set it until the Pipeline Maintainer's fix merges. |

### Roles

Vincent decided on 9/14 that the old autonomous controller (`run-graph`) is **retired for the main project**: "3 agents with some rules". Vincent wants these agents:

| Agent | Does | Never does |
|---|---|---|
| **Main Orchestrator** (Vincent's primary, formerly "Orchestrator Sol") | Talks to Vincent, receives problem reports, coordinates repairs, decides when a parked task may return, protects `main` and budgets | Do the other roles' work; pick every task for them |
| **Task Orchestrator** (formerly "Graph Sol") | Runs eligible normal tasks through crews: prepare, scope, reserve, start worker, post-crew, Vincent review, integrate, deliver, archive | GER, decomposition, approving for Vincent |
| **GER Orchestrator** | Improves task contracts with Codex and Claude GER rounds, commits contract revisions, hands oversized tasks to decomposition | Run crews, push, apply a decomposition |
| **Decomposition Orchestrator** | Runs D1B.2 decomposition for tasks marked `needs_execution_decomposition`, presents the plan, applies it after Vincent's exact-plan approval | Run crews, edit contracts by hand |
| **Integration Steward** | Merges side branches one at a time, keeps branch and worktree records, archives successful tasks (pushes moved to the Release Agent) | Delete NSC-### branches, batch merges |
| **Release Agent** | Pushes local `main` on Vincent's word, runs CI on a temporary PR, fixes CI config and hands code failures to owners, builds WebGL and publishes github.io on his word | Merge the temporary PR, move local `main`, push without Vincent's word |
| **Cleanup Agent** (running since 2026-09-18) | Branch and worktree triage, disk cleanup. Writes a plan plus a dry-run script for Vincent to run | Delete, remove, prune or force anything itself; touch NSC-### branches, uncommitted work, records or remote branches |
| **Art Director** (custom agent `art-director`; replaces the Art Producer) | **All 2D art**: PixelLab generation and repairs in the game's style, provenance, review packages, Vincent's picks, art-direction advice | Integrate into scenes, approve art, use other generators |
| **Pipeline Maintainer** (plus a separate **Reviewer**) | Fixes the pipeline in clones with tests; the Reviewer checks each fix | Merge, push, add blocking gates |
| **Watcher** | Read-only health checks and alerts | Change anything |

**AssistantControl: the controller idea is parked** (Vincent, 2026-09-17: "Assistant Control was the idea of using a controller to process the the tasks instead of a agent. Yeah we stopped working on it because the problems are numerous so I really need a smart agent in that role.").
- **Parked:** the autonomous controller layer, meaning automatic task selection and dispatch. `taskcontrol validate` reports "Autonomous dispatch authority: DISABLED".
- **Still in daily use:** crew workers and their configs, the durable records under `.assistant-control`, candidate and integration commands, and the viewer.
- **An agent does the controller's job:** picking the next task, launching crews, reading worker outcomes and moving a task forward. Today that is the Game Agent, as the Task Orchestrator.

Execution **crews** (implementer, test author, validator) are a separate layer inside a task. They are not these agents.

Handoffs:
- GER to Decomposition: a contract is committed with verdict `commit_contract_then_decompose`.
- Decomposition to Task: children are applied and released.
- Task to Decomposition: a crew or readiness says the task is too big.
- Task to GER: the contract is wrong or ambiguous.
- Anyone to Orchestrator/Vincent: a design decision, a spend go, a bug.

Record every handoff in `graph-lead-journal.md`, under your own dated heading.

**Later, not now:** Vincent plans to retire the gauntlet and run the main project in "gauntlet mode": the `graph-preflight` + `run-graph` controller with the viewer. Section 8 records how that mode ran on 9/16 so it can be resumed.

---

## 2. Start-of-session checks (read-only, 2 minutes)

Run these from PowerShell in `C:\NSC\NSC\NoSafeCircle`:

```powershell
git -C C:\NSC\NSC\NoSafeCircle status --short --branch | Select-Object -First 5
git -C C:\NSC\NSC\NoSafeCircle log --oneline -3
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|Unity' -and $_.CommandLine -match 'AssistantControl|Unity' } | Select-Object ProcessId,Name,CommandLine | Format-List
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -ge 8800 -and $_.LocalPort -le 8899 } | Select-Object LocalPort,OwningProcess
docker version --format '{{.Server.Version}}'
docker ps --format '{{.Names}}  {{.Status}}'
python -B Pipeline/TaskGraph/taskcontrol.py validate
```

Then read the newest sections of `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`.

**State on 2026-09-16:**
- `main` is at `22955c5a8`, 50 ahead of `origin`.
- No viewer or worker is running, and no container is running.
- 36 wizard `.anim`/`.controller`/tile `.asset` files show "modified" but are line-ending churn only. Do not commit or revert them.
  - They make the Source **dirty**, so `decompose` and `integrate` will refuse until they are cleared. Ask Vincent before touching them; section 6 has the check.
- `graph-controller.json` still says `blocked` from 2026-09-13. It is a stale retired-controller record; the owner record says `controller_released`.

---

## 3. Docker: start it and log in

Crews and decomposition run in Docker. GER rounds do **not**; they use the host CLIs (section 3.4).

**Which Claude account is where (Vincent, 2026-09-17).** Vincent has two Claude accounts, which split the load:
- **Desktop agent sessions** (Game, GER, Art Director, Pipeline Maintainer, Documentation, Decomposition) run on his **Outlook account** (Vincent.J.Liguori@...).
- **Docker Claude** (volume `nosafecircle_claude-config`: Claude crews, decomposition calls, `claude-exec`) is logged in to his **Gmail account** (cathode26@...), a Max plan. Pipeline Claude usage therefore doesn't draw on the desktop account.
- **The host `claude` CLI** is **also on the Gmail account** (checked 2026-09-17). It is `C:\Users\VincentLiguori\.local\bin\claude`, used by GER's Claude steps and by `claude -p` jobs.
- **Vincent (2026-09-17):** "we have plenty of claude tokens, so use all claude provider. Make sure to use the docker." and "It is essential that you empty the cathode26@gmail.com account (icognito before you empty your own account of tokens)". Use the Gmail account first, and the desktop account last.
- **Which account am I spending?** Run `claude -p "/usage"` (in Git Bash prefix `MSYS_NO_PATHCONV=1`). It prints the signed-in account's session and week usage with reset times.
  - On 2026-09-17 the host CLI and Docker both printed the Gmail account's resets (session 7:10 am, week Wednesday 9 am) and rose from 1% to 5% of the session while jobs ran.
  - The desktop account resets at different times (session 5:50 am, week Tuesday midnight), so the reset times tell the accounts apart.
- **Never run `claude auth login` or `/login` in a host terminal.** It would replace the CLI's Gmail login, and GER's Claude steps and every host job would start spending the desktop account.
- **Is two accounts allowed?** Checked 2026-09-17 against anthropic.com/legal/aup and /legal/consumer-terms:
  - neither forbids one person holding two paid accounts;
  - the terms forbid sharing login information or making an account available to anyone else;
  - the usage policy forbids evading a ban with another account, automated account creation, and coordinating malicious activity across accounts to circumvent guardrails.
  - **So keep it clean:** Vincent owns and pays for both, nobody else uses them, credentials are never shared or put in third-party tools (only Anthropic's own CLI, Docker image and app), and no automation fails over to the other account when one hits its limit. Details: `C:\nscrev\claude-jobs\two-accounts-policy-research-20260917.json`.
- **Codex** logins (host and the `nosafecircle_codex-config` volume) are ChatGPT logins and are separate from both. **`codex login status` cannot tell you WHICH Codex account you are on** - it prints only `Logged in using ChatGPT`. On 2026-09-19 the host was silently signed in as a **third** account on a `prolite` plan, and a live Astra call was spent there before anyone noticed. **Decode the token's identity claims instead: `nsc-codex-jobs-guide.md` section 1a.**
- Check the Docker Claude account with `docker compose -p nosafecircle run --rm -T claude claude auth status --text`, run from a repo copy. **Don't re-login Docker to the desktop account** unless Vincent asks; that would merge the two quotas.

### 3.1 Start Docker

1. Start Docker: `docker desktop start`. It blocks until the engine is up. Docker Desktop is a per-user install under `%LOCALAPPDATA%\Programs\DockerDesktop`; there is also a Desktop shortcut.
2. Confirm it prints a version (29.x): `docker version --format '{{.Server.Version}}'`
3. Confirm the credential volumes exist: `docker volume ls --format '{{.Name}}' | Select-String 'nosafecircle_(claude|codex)-config'`
4. Images normally already exist: `nosafecircle-claude-exec`, `nosafecircle-codex`, `nosafecircle-round-robin-decompose`. If one is missing, build it from the repo dir: `docker compose -p nosafecircle build claude-exec codex round-robin-decompose`
   - **Updating Claude or Codex inside the images** (done 2026-09-17):
     - wait until `docker ps` shows no `nosafecircle-*`, `assistant-crew-*` or `nsc-decompose-*` containers;
     - then run `docker compose -p nosafecircle build --no-cache` from the repo dir.
     - The Dockerfile copies no repo files, and the logins live in the volumes, so they survive a rebuild.
     - The install scripts give stable releases: Claude Code 2.1.274 and Codex 0.152.1 on 09-17. That Codex can't run Astra; use the Codex app's CLI on the host (`nsc-codex-jobs-guide.md` 4.4).

Run every compose command **from `C:\NSC\NSC\NoSafeCircle`** with **`-p nosafecircle`**. That makes the volumes `nosafecircle_claude-config` and `nosafecircle_codex-config`, which are the ones the worker configs, `decompose` (`--compose-project nosafecircle`) and the supervisors use.

### 3.2 Codex login (Docker volume `nosafecircle_codex-config`)

This is what Vincent ran on 9/15. It uses his ChatGPT account and device auth.

```powershell
cd C:\NSC\NSC\NoSafeCircle
docker compose -p nosafecircle run --rm codex codex login status
# If not logged in, or switching accounts:
docker compose -p nosafecircle run --rm codex codex logout
docker compose -p nosafecircle run --rm codex codex login --device-auth
# Open https://auth.openai.com/codex/device, enter the one-time code (15 min), wait for "Successfully logged in".
```

Only Vincent can do the browser step. Agents must never copy `auth.json` between volumes; the permission classifier blocks it, correctly.

### 3.3 Claude login (Docker volume `nosafecircle_claude-config`)

This is not documented in the repo. Vincent verified these commands on 2026-09-16:

```powershell
cd C:\NSC\NSC\NoSafeCircle
docker compose -p nosafecircle run --rm claude claude auth status --text
# If logged out:
docker compose -p nosafecircle run --rm claude claude auth login
```

Older interactive fallback: `docker compose -p nosafecircle run --rm claude-exec claude`, then `/login` in the prompt, finish in the browser, `/exit`. `docker compose run` allocates a TTY by default. Compose v5 has no `-t` flag, so don't pass `-it`. From the Bash tool, add `-T`.

**Cheap functional check** (spends a few tokens; do it once before a big batch):

```powershell
docker compose -p nosafecircle run --rm -T codex-review codex exec --skip-git-repo-check "Reply with exactly OK"
docker compose -p nosafecircle run --rm -T claude-review claude -p "Reply with exactly OK"
```

If a crew or decomposition fails with an authentication error, Vincent re-runs the login. An OAuth session can expire after hours of disuse.

### 3.4 Host logins (GER and ad hoc Codex/Claude jobs)

```powershell
codex login status          # host Codex; log in via the Codex desktop app or `codex login`
                            # WARNING: this never names the account. To learn WHICH account,
                            # see nsc-codex-jobs-guide.md section 1a (decode auth.json).
claude                      # host Claude Code; /status, /login if needed, /exit
```

- **Workspace trust.** A non-interactive `claude -p` in a folder that was never opened interactively stalls on a trust prompt. This includes new git worktrees and GER snapshot folders.
  - Fix: open `claude` once in that folder, accept trust, then `/exit`.
  - This silently stalled a GER round for 30 minutes on 9/14.
- **Codex quota.** On 9/14 the *old* Codex account hit its limit ("retry Sep 19"). The account logged in on 9/15 has capacity.
  - A Codex round that dies with `FAILED.json` `"exit code 1; empty or missing OUTPUT.md"` is almost always quota.
  - Check the Codex app's usage before a long GER or decomposition batch.

### 3.5 Docker hygiene

- There are about 313 images and 47 volumes, with about 3 GB reclaimable each. **Do not prune** without Vincent. The volumes include the live credential stores and per-run stores that owned-container cleanup needs.
- Never `docker stop/rm/compose down` a `nsc-decompose-*`, `nosafecircle-round-robin-decompose-run-*` or `assistant-crew-*` container by hand. Use `stop-worker`/`maintenance-plan ... cleanup-worker-docker`/`stop-background-jobs`.
- **Mount warning.** The plain `codex` and `claude` services mount the **real repo read-write**. A `git checkout` inside that container switches Vincent's real `main` checkout. It happened on 9/15.
  - For Codex bulk jobs, use a standalone clone made with `-c core.autocrlf=true -c core.filemode=false`. Run compose **from the clone folder** with `-p nosafecircle`. Details: `nsc-codex-jobs-guide.md`.
  - Or use the read-only `codex-exec`/`claude-exec` services, which mount `/workspace:ro`.
  - Inside containers `core.autocrlf` is unset for `codex`/`claude`, so git sees every file as modified. The `*-exec`/`*-review`/`*-decompose` services set it; clone-local config also fixes it.
  - Never point a container at a git **worktree**: its `.git` file names a Windows path the container can't resolve.

---

## 4. The viewer

It is a read-only web page over the live records. It never starts, stops or approves anything; POST/PUT/PATCH/DELETE are refused.

**Owner: the Viewer Agent session** (2026-09-17; `C:\NSC\nsc-viewer-agent-guide.md`). Send it one line, `VIEWER: <command> NSC-### | reason`. The commands below are for the Viewer Agent, and for anyone when no Viewer Agent session is running.

**Agents: use `python -B C:\NSC\tools\viewer\nsc_viewer.py status|start|stop|restart|list|task|overlays|hold|unhold|ger-start|ger-pause|ger-finish|working|done|complete|uncomplete`.** The full guide is `C:\NSC\nsc-viewer-guide.md`. The manual commands below are the fallback.

### 4.1 Start it

```powershell
cd C:\NSC\NSC\NoSafeCircle
python -m Pipeline.AssistantControl --source C:\NSC\NSC\NoSafeCircle --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts viewer --port 8828
```

- It prints `{"viewer_url": "http://127.0.0.1:8828/", "read_only": true}` and keeps running in that window.
- Background form, with logs:

  ```powershell
  Start-Process -FilePath python -ArgumentList '-m','Pipeline.AssistantControl','--source','C:\NSC\NSC\NoSafeCircle','--checkout-root','C:\NSC\NoSafeCircle-AssistantCheckouts','viewer','--port','8828' -WorkingDirectory C:\NSC\NSC\NoSafeCircle -WindowStyle Hidden -RedirectStandardOutput C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\viewer-logs\viewer-8828.out.log -RedirectStandardError C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\viewer-logs\viewer-8828.err.log
  ```

- Open **http://127.0.0.1:8828/**. It binds to 127.0.0.1 only.
- Port **8828** is the team convention. The code default is 8813, so always pass `--port 8828`.
- `--source` and `--checkout-root` must come before `viewer` and **must be the live pair above**. A viewer pointed at any other checkout root shows every contract but **zero live workers**; that confused everyone on 9/14.
- The only `viewer` flag is `--port`. `--task` is rejected. Scope filtering comes only from a `graph-controller.json` in `preflight`/`running` status, plus the "run scope only" checkbox in the page.

### 4.2 Check it is the right viewer

```powershell
$s = Invoke-RestMethod http://127.0.0.1:8828/api/state -TimeoutSec 60
$s.viewer_identity        # pid, source, checkout_root, port: must match the live pair
$s.inspection_error       # must be empty; a non-empty value means a record or overlay is malformed
```

- The first `/api/state` after a restart can take 30-90 s while it builds the snapshot.
- State is cached for 30 s. Overlay file edits invalidate the cache immediately.

### 4.3 Restart or stop it

A restart is needed only when:
- viewer code changed on `main`;
- `viewer_identity` is wrong;
- the process is gone.

"A task looks stuck" is **not** a reason; read the records instead.

```powershell
$c = Get-NetTCPConnection -LocalPort 8828 -State Listen -ErrorAction SilentlyContinue
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)"
$p.CommandLine    # must contain 'Pipeline.AssistantControl' and 'viewer' and '8828', else STOP: it is not ours
Stop-Process -Id $c.OwningProcess
# wait until Get-NetTCPConnection -LocalPort 8828 -State Listen returns nothing, then start again (4.1)
```

- A second viewer on the same port now fails at bind (`ExclusiveListenerError`) instead of silently sharing it.
- Old viewers from other runs may still be listening, for example 8817 on `GauntletFresh1140`, and 8830-8832 from the 9/16 demo copies. They are harmless, but ask Vincent before killing one.
- The page `<title>` says "NSC Gauntlet Graph" even for the real game. That is cosmetic.
- Tell Vincent to hard-refresh (Ctrl+F5) after a viewer restart or overlay change.

### 4.4 Display overlays (the only `.assistant-control` files agents may write)

All three live in `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\`. They change **display only**. They never block or start work.

**`held-task-ids.json`** (schema `assistant-viewer-held-tasks/v1`)
- Keys: `task_ids`, which are held and show grey "Outside Current Run"; `active_ger_task_ids`, which show brown "GER in progress" (palette name "Task Retired"); `released_ger_task_ids`, which show purple "Task Unstarted".
- Invariants: active ⊆ held, and held ∩ released = ∅.
- Edit it **only** with the marker CLI:

  ```powershell
  python -m Pipeline.TaskDesignGER.ger_viewer_marker start  NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
  python -m Pipeline.TaskDesignGER.ger_viewer_marker pause  NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
  python -m Pipeline.TaskDesignGER.ger_viewer_marker finish NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts [--ready-child NSC-101 ...]
  ```

- `start` requires the ID to be in `task_ids` already.
- The marker CLI has no verb to add a hold, or to drop one without releasing it. Use the helper (outside git, same lock, schema checks and atomic write):

  ```powershell
  cd C:\NSC\NSC\NoSafeCircle
  python -B C:\NSC\tools\ger\hold_ger_task.py hold   NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
  python -B C:\NSC\tools\ger\hold_ger_task.py unhold NSC-080 --checkout-root C:\NSC\NoSafeCircle-AssistantCheckouts
  ```
- In Git Bash use forward slashes: `--checkout-root C:/NSC/NoSafeCircle-AssistantCheckouts`.

**`external-work-ids.json`** (schema `assistant-viewer-external-work/v1`)
- Format: `{"schema_version":"assistant-viewer-external-work/v1","tasks":[{"task_id":"NSC-057","description":"...","expires_at":"<UTC ISO, 20-30 min ahead>"}]}`
- Use it to show **blue "Task Working"** for real work that is not an AssistantControl crew, such as PixelLab generation or hand-run Unity validation.
- Refresh `expires_at` while working, and remove the entry when done.

**`human-complete-ids.json`** (schema `assistant-viewer-human-complete/v1`)
- Format: `{"schema_version":"assistant-viewer-human-complete/v1","tasks":[{"task_id":"NSC-067","note":"Vincent confirmed complete 2026-09-14"}]}`
- It shows green for tasks Vincent says are done but that have no delivery record.
- It does **not** satisfy dependencies. Only a real delivery record does.

Prefer the script for these two files:
- `nsc_viewer.py working NSC-### --description "..." --minutes 30`, and `done NSC-###`;
- `nsc_viewer.py complete NSC-### --note "..."`, and `uncomplete NSC-###`.

It locks, validates task IDs against Source HEAD, and writes atomically.

**Fallback only: safe hand write.** It uses no BOM and an atomic replace. A malformed overlay makes the whole viewer show `inspection_error`.

```powershell
$path = 'C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\external-work-ids.json'
$json = $obj | ConvertTo-Json -Depth 6
$tmp = "$path.tmp-$PID"
[System.IO.File]::WriteAllText($tmp, $json, [System.Text.UTF8Encoding]::new($false))
Move-Item -Force $tmp $path
python -c "import json; json.load(open(r'$path', encoding='utf-8'))"
```

### 4.5 What the colors mean

| Color / label | Meaning | Watch out |
|---|---|---|
| Purple "Task Unstarted" (`ready`) | Contract active, no delivery evidence | It also means "needs revalidation because the contract revision changed" (for example NSC-023), and "blocked on a design question" since the 9/15 hold clearing. It does not mean dependencies are met. |
| Grey "Task Dependencies Unmet" (`pending`) | Dependencies are not delivered | |
| Grey "Outside Current Run" | Held by the overlay, or outside a controller scope | |
| Brown "Task Retired" palette | GER actively working (overlay) | |
| Blue "Task Working" (`active`) | Live worker, or external-work overlay | **Bug:** approved or integrating candidates also show blue. `integration_queued` is never assigned on main. |
| Pink "Task Needs You" (`human_action`) | A candidate awaits Vincent's Unity test | Tell Vincent the exact folder and commit |
| Orange "Task Blocked" | Blocked record | It can disagree with `graph-plan`; trust `graph-plan` and the records |
| Green "Task Complete" | Conformant delivery, or human-complete overlay | |
| "Decomposed Parent" / `aggregate` | Parent split into children, or awaiting decomposition | |

The page's "Uncommitted local build SHA-256" and "GitHub repository" rows always say "Unavailable" in this mode. That is cosmetic.

---

## 5. Unity rules

- **Close Unity on the Source** (`C:\NSC\NSC\NoSafeCircle`) before `decompose`, `integrate`, `apply-decomposition` or any batchmode build of that project. An open editor holds the project lock and rewrites files (line endings, `ProjectSettings`), making the Source dirty.
- **One batchmode Unity at a time.** Guard every hand launch:

  ```powershell
  if (Get-CimInstance Win32_Process -Filter "Name='Unity.exe'") { throw 'Unity busy' }
  ```

  Queue PlayMode and EditMode runs sequentially; two Unity instances on the same project collide on `Library`.
- **Never pass `-quit` with `-runTests`.** Unity exits before writing the XML and returns 0 with no results, a false pass. Prefer `Pipeline\Testing\run_unity_tests_clean.ps1`.
  - Its exit codes: 10 precondition, 20 Unity, 30 result, 40 repo mutated.
  - It fails if the repo changed during the run.
- **Test filters use semicolons**, not commas. A comma list silently runs zero tests.
- **Licensing exit 199** or "unable to open database file" means Unity was launched under a sandboxed identity. Rerun under the normal Windows user; nothing needs a restart.
- **DOTween** needs a one-time interactive "Tools > Demigiant > DOTween Utility Panel > Setup DOTween". It is done and committed on main; new packages like it will need Vincent at the GUI.
- **Warm a new checkout.** A fresh checkout's first import is slow. Copy `Library` from an existing checkout with `robocopy` (1.3 GB, about 2 min).
- **Authoring room scenes** (`Assets/Scenes/Rooms/*.unity`) have no camera or light by design; opening one alone looks black. Open the composed `Assets/Scenes/DoorPrototype.unity`.
- **Scenes are binary-ish.** Don't grep them to count objects.

---

## 6. Line-ending churn

Unity and GitHub Desktop are usually open on the Source, so files flip dirty with no content change.

Before assuming a real edit, check one file:

```powershell
git hash-object <path>          # working bytes as git would store them
git rev-parse HEAD:<path>        # committed blob
```

If the two match, it is churn.
- `git checkout -- <path>` clears most cases.
- The 36 wizard/tile assets on main do **not** clear with `checkout`, `update-index --refresh` or `safe_unity_churn.py`. Stage by exact path and leave them alone.
- They still make `decompose`/`integrate` refuse "Source must be clean". Ask Vincent how he wants that resolved; see the problem list.

---

**Applying a patch to a file a contract pins by hash.** Our clones check out CRLF (`git ls-files --eol` reports `i/lf w/crlf`) while patches are LF.
Hashing the worktree copy therefore gives the wrong value, and the gate refuses a commit that is actually correct.

**Apply with the clone's own config. Do not force `core.autocrlf=false`** (2026-09-17: that advice was wrong and it failed) - with a CRLF worktree and an LF
patch git finds no matching context and refuses with "patch does not apply", *after* `git apply --check` passed under the normal config. With `autocrlf=true`
git normalises for matching and converts back to LF on commit, so the committed blob is LF and hashes correctly.

```bash
git apply <patch>                         # the clone's own config
git show <commit>:<path> | sha256sum      # the only hash that matters
```

Forcing `core.autocrlf=false` is right only in a scratch clone **checked out** that way, where the worktree is already LF.

If the landed hash doesn't match the contract's pin, **report the hash and let the GER Agent rebind it**. Never edit approved wording to chase a
precomputed constant: the text is the authority, the hash is bookkeeping that points at it.

---

## 7. Roles in practice

- **Coordination file.** `graph-lead-journal.md` is the shared durable log.
  - Append a dated section per agent action: what, task IDs, commits, run IDs, blockers, evidence paths.
  - Never edit another agent's section.
  - The unavailable/hold list for tasks lives there too; see the Task Orchestrator guide.
- **Codex coordination thread.** GitHub issue `cathode26/NoSafeCircle#127` carried Codex-Claude GER handoffs on 9/14: "Ready for Codex — NSC-0xx" and "Received — NSC-0xx". Use it only if Vincent re-enables that loop. Keep local paths and logs out of the issue.
- **Budget.** Vincent's standing rule (9/15): send bulk work to Codex and cheaper subagents (Sonnet/Haiku); keep Claude Opus for decisions, review, commits and graph state.
- **Durable automations.** A Codex desktop automation "Poll Gauntlet repair board" was still firing every 5 minutes on 9/16 against an archived issue. Pause stale automations; for Codex: "Use automation_update to set the automation with id poll-gauntlet-repair-board to status PAUSED."

---

## 8. Gauntlet mode (the `run-graph` controller): reference for later

It is retired for the main project today. Vincent wants the main project to run this way eventually. This is exactly how it ran on 9/16 on a disposable copy (`C:\NSC\NSCDemoGauntlet-20260916`).

```bash
SRC=C:/NSC/NSCDemoGauntlet-20260916; ROOT=C:/NSC/NSCDemoGauntlet-20260916-Checkouts
python -B -m Pipeline.AssistantControl --source "$SRC" --checkout-root "$ROOT" graph-plan --task NSC-200 --task NSC-201
python -B -m Pipeline.AssistantControl --source "$SRC" --checkout-root "$ROOT" graph-preflight \
  --target-branch demo/gauntlet-20260916 --worker-config Pipeline/AssistantControl/worker-haiku.example.json \
  --providers claude,codex --compose-project nosafecircle --capacity 6 --background-jobs 2 \
  --authorize-provider-spend --task NSC-200 --task NSC-201 --task NSC-1101
python -B -m Pipeline.AssistantControl --source "$SRC" --checkout-root "$ROOT" run-graph \
  <identical flags> --max-actions 120
```

- **`graph-preflight` and `run-graph` flags must match byte for byte.** That covers targets, human-review tasks, `--auto-approve-gauntlet`, capacity, target branch, scope dir, providers, compose project, background jobs and `--authorize-provider-spend`.
  - Otherwise: `command_failed: Graph preflight no longer matches Source or controller policy/config bytes`.
  - `--max-actions` is exempt.
  - Changing any policy flag mid-run means a new preflight and relaunch, which kills in-flight decomposition.
- **Statuses:**
  - Invoke again: `capacity_full`, `worker_still_running`, `background_jobs_running`, `action_limit_reached`.
  - Stop and read: `awaiting_human`, `blocked`, `command_failed`.
- **Stop it:**

  ```text
  python -m Pipeline.AssistantControl --source S --checkout-root R stop-graph --reason "..." --grace-seconds 15 --wait-seconds 120
  ```

  Then `stop-background-jobs` if it reports `*_cleanup_pending`. Killed containers need a 60 s tombstone; that is not a hang.
- **Human review.** NSC-042 is permanently human-review only. `--auto-approve-gauntlet` only approves tasks whose `provenance` marks them synthetic gauntlet. Cloned tasks never qualify, so real tasks always stop at `awaiting_human`.
- **Approve one candidate at a time.** Integrating one candidate moves Source and re-syncs the others to **new SHAs**, silently discarding approvals given to the old SHAs.
- **Integration hold.** While a decomposition runs, `integrate` for that Source commit is **held**. `graph-plan` shows `held[]` with `decomposition_proposal_in_flight`; the viewer shows nothing.
- **Code drift.** The rehearsal repo `C:\NSC\TenTaskFinalIntegration-20260905` is older code: it has no `graph-preflight` and no `--background-jobs`. Always run `--help` against the Source you are using.

---

## 9. Troubleshooting

| Symptom | Likely cause | Do this |
|---|---|---|
| Viewer shows 0 blue while workers run | Viewer on the wrong checkout root | Check `viewer_identity`; restart on the live pair |
| Viewer page blank or `/api/state` slow | Snapshot rebuild after restart; big state | Wait 60-90 s; read records meanwhile. Don't restart repeatedly. |
| Task blue but its crew finished | Known bug: approved/integrating shows `active` | Read `NSC-###.json` status |
| `command_failed: Specify --checkout-root outside the source project` | `--checkout-root` placed after the subcommand, or missing | Put global flags before the subcommand |
| `Source must be clean before decomposition` | Dirty Source (Unity churn, `.meta` from an import, 36 phantom files) | Section 6; commit real generated `.meta`s by exact path; ask Vincent |
| `Decomposition record already exists with status failed; it was preserved` | An old `NSC-###.decomposition.json` exists | Decomposition guide, "Retrying" |
| `post-crew`: "ExecutionCrew receipt was not authenticated" | Wrong run id | Use the crew's own `crew_run_id` from `worker-status`, not your launch run id |
| Worker exits immediately, no provider call | Bad config pairing (for example `full` crew + `targeted` validation) | `settle-worker`, fix config, reserve again |
| Crew `rejected: role made no required file modification` | Task already implemented | Not a pipeline bug; see the Task guide, "Already implemented" |
| Unity tests "pass" with no XML | `-quit` with `-runTests` | Rerun without `-quit` |
| GER round stuck at start | Claude workspace-trust prompt | Open `claude` once in that folder; accept trust |
| Codex round `FAILED.json`: empty OUTPUT.md | Quota | Check usage; rename the round `.failed-<UTC>`; resume later |
| Controller "running" forever with `worker_exited` loops | Lost final worker write (NSC-1163 class); no fix on main | **Do not rerun the crew** (it overwrites the receipt); escalate |

---

## 10. Where records live

- Journal: `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md`
- Branch recovery: `C:\NSC\nsc-handoff-20260916.md`, `C:\nscrev\reports\branch-recovery\`
- Codex 9/13-9/14 digest: `C:\NSC\nsc-codex-0913-0914-digest.md` (full: `Desktop\nsc-codex-0913-0914-context.md`)
- GER overnight report and questions: `C:\nscrev\reports\ger-overnight-20260914.md`
- Older-generation docs, **historical, don't follow**: `C:\nscrev\reports\NEXT-ASSISTANT-BRIEF.md`, `RUNNING-LOCAL-VS-PRODUCTION.md` (`NscRun.cmd`, port 8813, TenTaskFinalIntegration)
- Gauntlet runbooks, **test harness only**: `C:\nscrev\reports\gauntlet-run-instructions.md`, `gauntlet-orchestration-staffing.md`
- In-repo docs that are **stale**, don't follow blindly: `Docs/AI-Pipeline/START_HERE.md`, `Pipeline/AssistantControl/CURRENT.md`, `STATUS.md`, the "Bounded graph controller" half of `Pipeline/AssistantControl/README.md`, `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md`
