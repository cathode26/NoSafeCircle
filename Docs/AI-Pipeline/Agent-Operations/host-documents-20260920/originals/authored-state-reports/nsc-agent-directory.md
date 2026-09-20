# Agent directory and work routing

Vincent runs dedicated agents as separate Claude sessions, listed in the app sidebar by title. **Each agent does only its own work. When an agent reaches work that belongs to another agent, it hands that work to the owner by name instead of doing it.**

This file lists the agents, which agent owns each kind of work, how to hand work off, and how to add agents. Written 2026-09-16; the Documentation Agent keeps it current.

Every Claude session under `C:\NSC` loads `C:\NSC\CLAUDE.md`, which points here.

---

## 1. Know who you are

- **Your identity is your session title** ("Game Agent", "Art Director Agent", ...). If unsure, load `mcp__ccd_session_mgmt__get_session` with ToolSearch and call it with `"self"`.
- **Memory is shared.** Every session under `C:\NSC` reads the same memory folder, `C:\Users\VincentLiguori\.claude\projects\C--NSC\memory\`. A memory that says "I am the game developer" was written by the Game Agent and is not about you.
- **Write memories in the third person,** naming the agent: "The Game Agent owns merges", never "I own merges".

---

## 2. The agents

### Running as sessions

| Sidebar title | Role and guide | Owns |
|---|---|---|
| **Game Agent** | Game developer **and** Integration Steward (Vincent, 2026-09-16). Guides: `nsc-integration-steward-guide.md`, `nsc-task-orchestrator-guide.md`, `nsc-delivery-evidence-guide.md` | Building and fixing the game in Unity; merges into local main; branch recovery; archiving to `SuccessfullTasks`; pushes moved to the Release Agent (2026-09-17) |
| **Documentation Agent** | Documentation, agent definitions. Guide: `nsc-pipeline-runbook.md` (doc index) | The `C:\NSC\nsc-*.md` doc set, launch prompts, this directory, `C:\NSC\CLAUDE.md`, custom agent files in `C:\Users\VincentLiguori\.claude\agents\`, the problem list. **GDD edits** (from 2026-09-17), after Vincent approves each change. |
| **GER Agent** | GER Orchestrator. Guide: `nsc-ger-orchestrator-guide.md` | Task contract revisions, GER rounds, design decisions Vincent delegated, contract commits, GER holds and releases. GDD changes go to the Documentation Agent. **Contract check (2026-09-17):** commits are never blocked. Design revisions get one Codex buildability check right after commit, and its verdict is seen before a crew starts or Vincent tests. Mechanical revisions get a reference grep only. See guide section "The contract check". |
| **Art Director Agent** | Art Director. Guide: `nsc-art-director-guide.md`; bible: `C:\Users\VincentLiguori\.claude\agents\art-director.md` | All 2D art: PixelLab generation and repairs, review packages, recording Vincent's picks, art-direction advice |
| **Pipeline Maintainer Agent** (running since 2026-09-16) | Pipeline Maintainer. Guide: `nsc-pipeline-maintainer-guide.md`; rules: `C:\Users\VincentLiguori\.claude\agents\pipeline-maintainer.md`; reviews by `pipeline-reviewer` subagents | Pipeline code and tools: AssistantControl, ExecutionCrew, TaskGraph, TaskDecomposition, TaskDesignGER tooling, the viewer and GauntletView page, Docker worker plumbing, the helper scripts in `C:\NSC\tools\viewer` and `C:\NSC\tools\ger` |
| **Decomposition Agent** (created 2026-09-17) | Decomposition Orchestrator. Guide: `nsc-decomposition-orchestrator-guide.md`; state file: `C:\NSC\agent-state\decomposition-agent.md` | Splitting oversized tasks, including tasks marked `execution_scope: needs_execution_decomposition`: `decompose` (provider spend, so Vincent's go) and `apply-decomposition` (moves main, so the main-write protocol) |
| **Viewer Agent** (running since 2026-09-17) | Viewer state. Guide: `nsc-viewer-agent-guide.md`; viewer reference: `nsc-viewer-guide.md`; state file: `C:\NSC\agent-state\viewer-agent.md` | Task state and new-task intake (2026-09-17): verifying whether tasks are really done and reporting mismatches; taking new task requests, checking for duplicates, reserving the ID and writing the intent for the GER Agent. Also the viewer process on port 8828 and its three display overlays: holds and GER markers, working markers, and complete markers that need Vincent's words. Applied from other agents' one-line `VIEWER:` requests, keeping the page true to the records. Not viewer code (Pipeline Maintainer Agent), and never records or contracts |
| **Release Agent** (new 2026-09-17) | Release. Guide: `nsc-release-agent-guide.md`; state file: `C:\NSC\agent-state\release-agent.md` | Pushing local `main` to GitHub when Vincent says so (one "push" covers one release run); CI through a temporary PR, fixing CI config and handing code failures to their owners; WebGL builds and github.io publishing on Vincent's word; release notes |
| **Cleanup Agent** (running since 2026-09-18; instructions revised 2026-09-19) | Workspace lifecycle and recovery-backed retirement. Guide: `nsc-cleanup-agent-guide.md`; canonical prompt: `nsc-cleanup-agent-start.md`; state: `agent-state/cleanup-agent.md` | Registration index, bounded drift/exception queue, verified retirement packages and post-run checks. Producers register and close their own work; Vincent executes destructive actions. |

### Roles with no session yet

Prompts are in `nsc-agent-launch-prompts.md`.

| Role | Guide | Who covers it until Vincent starts a session |
|---|---|---|
| Task Orchestrator (AssistantControl crews) | `nsc-task-orchestrator-guide.md` | **Game Agent** (default; Vincent to confirm) |
| Watcher | `nsc-watcher-guide.md` | Nobody. Any agent may run `python -B C:\NSC\tools\viewer\nsc_watch.py` (read-only). The Viewer Agent covers the watcher loop if Vincent asks. |
| Main Orchestrator | `nsc-main-orchestrator-guide.md` | Vincent coordinates the sessions himself |

### Helper agents (custom subagent types)

Created 2026-09-17 after the agent survey, with Vincent's approval: "give all the agents everything they want". Sessions call them with the Agent tool. Their definitions are in `C:\Users\VincentLiguori\.claude\agents\`.

| `subagent_type` | Model | Used by | Does |
|---|---|---|---|
| `merge-verifier` | Sonnet | Game Agent | merge-tree inspection, trial merge in `branch-verify`, validate and non-Unity suites, the Codex review of the trial merge, a verdict paragraph. Never merges or pushes. |
| `unity-runner` | Sonnet | Game Agent; Pipeline Maintainer in its own clones, after telling the Game Agent | Builders and Unity test filters on an exact commit, cleanup of EOL-only churn, counts and logs. One Unity at a time. |
| `delivery-evidence` | Sonnet | Game Agent | Delivery records per `nsc-delivery-evidence-guide.md` for an integrated task |
| `test-runner` | Haiku | any agent | Runs the given non-Unity test commands at base and head; returns counts only |
| `ger-drafter` | Sonnet | GER Agent | Briefs from packets, and draft contract revisions from the GER Agent's decisions (key-set and invariant rules, scratch validate). Never commits or decides. |
| `pixellab-batch-recorder` | Haiku | Art Director Agent | Downloads a finished PixelLab batch with read-only tools; hashes, bounding boxes, a draft inventory, a spend note. It has no generation tools. |
| `scribe` | Haiku | any agent | Appends and updates rows on the handoff board and lines in the journal, exactly as told |
| `pipeline-reviewer` | Opus xhigh | Pipeline Maintainer Agent | Fresh independent review of a pipeline fix |
| `pipeline-maintainer`, `art-director` | Sonnet, Opus | their sessions | The role's rules in subagent form, for easy steps with a `model` override |

---

## 3. Who owns what

### 3.1 By kind of work

| Work | Owner |
|---|---|
| Game features in Unity: C# runtime code, builders, generated scenes, prefabs and clips, Edit and Play Mode tests, gameplay bugs, preparing Vincent's in-game checks | Game Agent |
| Running AssistantControl crews: prepare, scope, reserve, start-worker, post-crew, review, integrate | Task Orchestrator; for now the Game Agent |
| Unity test runs and audits on an exact commit | Game Agent |
| In-game screenshots for art review: gameplay-camera Game-view shots at 1920x1080 and 2560x1440, after each art integration or when the Art Director asks | Game Agent (Unity). It also builds the reusable Unity capture script, an Editor tool in the game repo (approved 2026-09-17). |
| Reusable art-review toolkit (game-scale camera panel, contact sheets, GIFs, mask-diff proof, frame metrics) and a PixelLab spend ledger | Art Director Agent, through a Codex "do" job (approved by Vincent 2026-09-17). The code gets a Codex review before use. |
| Tool asks from the survey: churn cleanup (P18), `archive-successful` (P35), `taskcontrol references` and a task-less code log (G16), watch-tool quota and login per Codex account (E17), Codex jobs preflight and a verify-candidate command (FUT5), weekly test debt (P36, P37) | Pipeline Maintainer Agent (board H-20260917-03) |
| Merges into local `main`, branch recovery, `SuccessfullTasks` archives, delivery evidence | Game Agent (Integration Steward) |
| Workspace lifecycle index, drift/exception queue, branch/worktree/disk retirement planning and verification | **Cleanup Agent**. Every producer owns registration, running children, all outputs/logs and explicit closeout/release under `nsc-workspace-lifecycle-policy.md`. Cleanup prepares verified dry-run packages; Vincent runs destructive actions. Remote publication stays with Release; NSC-### branches are never proposed for deletion. |
| Pushes to GitHub; CI (temporary PRs, `.github/workflows`, CI failures); WebGL builds and github.io publishing; release notes | **Release Agent** (2026-09-17), on Vincent's word. It fixes CI config itself and sends code failures to their owners. |
| Task contract changes of any kind, GER rounds, delegated design decisions, contract commits, GER holds and releases | GER Agent |
| **Queue and status sections of each role guide** (for example the art queue, the GER queue, the maintainer queue) | The agent whose guide it is keeps them current. The Documentation Agent owns cross-cutting docs (runbook, directory, `CLAUDE.md`, launch prompts, agent files, problem list, GDD). Other docs link to the directory instead of repeating routing (2026-09-17). |
| **GDD edits** (`Docs/GDD/No_Safe_Circle_GDD.md`): after Vincent approves the specific change. Edit in a clone, rebuild the GDD RAG index and run its tests, commit both files, land on local main with the main-write protocol, and tell the requester the sha. | Documentation Agent (Vincent, 2026-09-17). Other agents send requests with Vincent's quoted approval; the GER Agent holds GER packets that depend on the GDD until the sha arrives. |
| **Factual updates to an agent's own agent file** (`C:\Users\VincentLiguori\.claude\agents\<name>.md`), for example the Art Director updating its art bible after a merge | Documentation Agent applies them when the owning agent asks, **without asking Vincent each time** (Vincent, 2026-09-17: "yes"). The request must come from that file's own agent and be facts: game state, paths, merged commits, Vincent's quoted words. Changes to rules, permissions, tools, model or lane still need Vincent. |
| Running game tasks through crews | **Game Agent**, as Task Orchestrator. Vincent, 2026-09-17: "as many tasks as they see reasonable without getting dangerous", so no per-launch ask; limits and stop conditions in `nsc-task-orchestrator-guide.md` section 3a |
| Reading the whole backlog for buildability | **Decomposition Agent**, standing duty. Vincent, 2026-09-18: "read every task that still needs work, then decide if the task is too hard for the agents to complete", with **NSC-007 as the benchmark for too hard**. Findings go to the GER Agent as proposed splits; see `nsc-decomposition-orchestrator-guide.md` section 1a |
| Splitting an oversized task (`decompose`, `apply-decomposition`) | **Decomposition Agent** |
| **Adding a new game task** | **Viewer Agent** takes the request, checks for duplicates, reserves the ID and writes the intent; the **GER Agent** writes and commits the contract (`new_task.py`, queued with the Pipeline Maintainer, H-20260917-25). Vincent approves new work as usual. **Drafts when Vincent asks (2026-09-17):** if Vincent asks the Viewer Agent for a task, it may create it itself as a draft that no crew can start, and tell the GER Agent. If the Viewer Agent thinks of a task, it asks Vincent or hands it to the GER Agent. |
| **All 2D art:** PixelLab generation, repairs, new facings or animations, portraits, UI and title art, review packages, recording Vincent's picks, advice on how something should look | Art Director Agent |
| Putting approved art into Unity (import settings, Animator, prefabs, scenes) | Game Agent. The Art Director Agent checks the look before Vincent's test. |
| Pipeline code and tools: AssistantControl, ExecutionCrew (`run_crew.py`), TaskGraph, TaskDecomposition, the viewer code, the viewer and GER helper scripts | Pipeline Maintainer Agent. A fresh `pipeline-reviewer` subagent checks each fix; the Game Agent merges on Vincent's go. **Code vs. operations:** the code of the GER helper scripts in `C:\NSC\tools\ger` belongs to the Pipeline Maintainer, but running GER rounds, holds and releases with them is the GER Agent's work. The same split applies to `nsc_viewer.py`: code to the Pipeline Maintainer, use by any agent. |
| Running the viewer and changing its overlays (hold, GER markers, working/done, complete) | **Viewer Agent.** Send one line, `VIEWER: <command> NSC-### \| reason` (`nsc-viewer-agent-guide.md` section 3); no reply means it worked. If no Viewer Agent session is running, run `nsc_viewer.py` yourself. Read-only checks (`status`, `task`, `nsc_watch.py`) are open to anyone. |
| Docs, role guides, launch prompts, this directory, `C:\NSC\CLAUDE.md`, custom agent files, the problem list | Documentation Agent |
| Codex bulk jobs and easy work sent to Codex | **AVAILABLE again from 2026-09-20.** **Lifted 2026-09-20** (Vincent: *"Codex is available again, so the 'all Claude' routing is lifted"*). The first Codex Pro account is back; **the second still resets 2026-09-22 18:55 local.** Codex is a separate quota pool from both Claude accounts — prefer it for reviews, advice, read-only inspection and wide fan-out. Check which Codex account you are on first: `codex login status` never names it (`nsc-codex-jobs-guide.md` section 1a). Superseded wording, kept so the change is legible: *"Unavailable until 2026-09-19 - there are two Codex Pro accounts, resetting 2026-09-19 and **2026-09-22 18:55 local**. Until then this work goes to **Docker Claude on the Gmail account** (`nsc-codex-jobs-guide.md` section 4.3). After the reset: the agent that owns the work launches them (sections 2 and 4.1) |
| **Codex adversarial review of our own work** (fix branches, merge or crew candidates, docs that make claims about code) | The agent that did the work requests it (`nsc-codex-jobs-guide.md`, section 4.2). The verdict is advisory. The Pipeline Maintainer Agent is building the generic Codex jobs tool. |
| **Game Agent pipeline work: prefer a mixed pipeline** (Vincent, 2026-09-16) | Game Agent. Mixed crews already exist as provider profiles: `claude-architect-balanced` and `codex-architect-balanced` (`Docs/AI-Pipeline/PROVIDER_PROFILES_AND_BUDGET_ROUTING.md`). In them, the validator runs on the provider opposite the implementer. **Checked 2026-09-16: not usable through AssistantControl yet.** A worker config's `provider_profile` reaches the crew unexpanded and would fail (`C:\nscrev\reports\mixed-provider-crews-verify-report.md`); don't set it. A small fix is queued with the Pipeline Maintainer Agent after P3 and viewer-step1 merge. Until then, the candidate gets a review from the other provider before Vincent's Unity test. |
| **Vincent only:** approving candidates and art picks, provider or PixelLab spend, pushes, deleting anything, design decisions he kept, starting or renaming agent sessions | Vincent |

### 3.2 By task contract type

Look up a task's type with `python -B Pipeline/TaskGraph/taskcontrol.py show NSC-###` (field `type`). The task lists are as of 2026-09-16.

| Contract `type` | Tasks | Does the work |
|---|---|---|
| `art-acquisition`, `wizard-source-art-correction`, `wizard-cardinal-source-art`, `enemy-walk-source-art` | NSC-061, 063, 064, 065, 073, 074, 078, 093 | **Art Director Agent** |
| `character-presentation`, `wizard-directional-animation-repair`, `wizard-eight-direction-animation-integration`, `stationary-enemy-presentation-integration`, `enemy-walk-animation-integration` | NSC-062, 070, 075, 077, 094 | **Game Agent**; the Art Director Agent reviews the look |
| `content-authoring` | NSC-029, 030, 044-049, 079-084 | **Game Agent**. The dressing tasks (079-083) use the Art Director's prop pack (NSC-078); the Art Director advises on the look. |
| `world-foundation`, `world-authoring-foundation` | NSC-023-026, 038-040, 042, 069, 085, 089 | **Game Agent** |
| `enemy_ai_foundation`, `enemy_ai_state`, `enemy_ai_movement`, `enemy_archetype`, `enemy_behavior`, `enemy_prefab` | NSC-014, 015, 016, 017, 053, 054, 055, 091, 092 | **Game Agent** (NSC-015 needs decomposition first) |
| `gameplay_system`, `gameplay_feedback`, `spell`, `runtime-system`, `implementation` | NSC-003-005, 007-009, 011-013, 019-021, 028, 041, 050-052, 088, 090 | **Game Agent** |
| `run_lifecycle`, `player-world-entry`, `character-selection-ui`, `game-flow-ui` | NSC-031-035, 066-068, 086, 087 | **Game Agent** (NSC-033 needs decomposition first) |
| `build-configuration`, `delivery`, `gameplay-validation`, `engineering-foundation`, `engineering-refactor`, `engineering-audit` | NSC-036, 037, 043, 056-060, 071, 072 | **Game Agent** |
| `feature`, `feature-group`, `feature_group`, `root` (parents) | NSC-001, 002, 006, 010, 018, 022, 027 | Nobody directly; their children carry the work |

Two rules apply to every type:
- **A contract change for any task goes to the GER Agent,** whatever its type.
- **A task with `execution_scope: needs_execution_decomposition`** (NSC-015 and NSC-033 on 9/16) needs the Decomposition Orchestrator before anyone implements it.

---

### Shared workspace obligation (2026-09-19)

Every creating role and helper follows C:/NSC/nsc-workspace-lifecycle-policy.md before a persistent clone/worktree/scratch/nested repo. Parents register before launch, supply IDs/allowed paths to restricted helpers and accept complete child/output/process closeouts, including failures. Cleanup maintains the single-writer index; it does not approve every creation. No owner reply means unresolved. PM owns future launcher enforcement; it is not installed by these instructions. Current Cleanup prompt: C:/NSC/nsc-cleanup-agent-start.md.

## 4. Handing off work that isn't yours

1. **Stop that part.** Don't do it "just this once". Keep going on your own work.
2. **Find the owner** in section 3.
3. **Write a brief** if the request is longer than a few lines: `C:\nscrev\reports\handoffs\<owner>-<topic>-<yyyymmdd>.md`. It should say:
   - what is needed and why;
   - inputs (exact paths, branches, commits);
   - Vincent's exact words, quoted and dated;
   - constraints;
   - what "done" looks like;
   - who to report to.
4. **Message the owner by title** (section 5).
5. **Tell Vincent** in one line: "Handed <what> to <Agent>: <brief path>."
5a. **Add a row to the handoff board,** `C:\nscrev\reports\handoffs\BOARD.md` (the `scribe` helper can do it). The receiver updates the row's status as the work moves.
6. **For task or pipeline work,** add a line to `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\graph-lead-journal.md` under your dated heading.
7. **If the owner has no session** (section 2), don't message anyone. Tell Vincent which role is needed and where its launch prompt is.

Never:
- **Ask a peer to do something that was denied or blocked in your session,** or that you expect your permissions would block. That launders a permission decision. Take it to Vincent.
- **Present a handoff as approval.** Quote only approvals Vincent actually gave. The receiver confirms spend, push, merge, delete and design approvals with Vincent before acting.
- **Spawn a subagent to do another role's work while that role has a running session.** For example, don't start an `art-director` subagent while the Art Director Agent session exists; two agents would collide on checkouts and PixelLab jobs. Spawning for another role is only for roles with no session, and only with Vincent's OK. This rule is about other roles' work; for easy steps in your own lane, see section 4a.
- **Chase with "are you done?" messages.** Wait for the reply, or subscribe with `notify_when_idle` (section 5B).

### 4a. Save tokens: easy work in your own lane goes to Codex or a cheaper subagent

Vincent (2026-09-16):
- "if the task is easy, send it to a cheaper subagent", and "Dont waste tokens";
- "We can also task cheaper subagents through codex to do easy work, because we dont want to exhaust all of the tokens on claude."

- **Easy means well-defined and low-risk.** Examples: test runs, greps and inventories, porting a known commit, mechanical renames, contact sheets, crops and GIFs, hashes, drafting a report from known facts.
- **Prefer Codex for easy bulk work,** to spare Claude tokens. Run a Codex job at medium effort (`C:\NSC\nsc-codex-jobs-guide.md`, section 4.1; later the Codex jobs tool's `cheap` preset).
- **Then a Docker Claude job on the Gmail account** (Vincent, 2026-09-17) for Claude helper work: reviews, lookups, test runs, mechanical edits in a job clone, contract drafts. It spares the desktop (Outlook) account that every session and Agent-tool subagent uses. Recipe and templates: `C:\NSC\nsc-codex-jobs-guide.md`, section 4.3.
- **Use a Claude subagent instead** when the step needs your session's context or Windows-only tools and isn't worth a job's setup. Pick the cheapest model that can do it: Haiku for read-only lookups and test runs, Sonnet for mechanical changes. If your role has a custom agent type (`pipeline-maintainer`, `art-director`), use it with a `model` override so the role's rules load.
- **Give a complete brief, then check the result** before relying on it.
- **Keep in your own session:** judgment calls, subtle or risky changes, anything needing Vincent, messages to other sessions, and handoffs.
- **Independent reviews stay independent.** A subagent you briefed to write something never reviews it.
- **A subagent does its step itself;** it doesn't delegate further.

---

## 5. Messaging another agent by name

### A. By sidebar title (preferred)

1. Load the tools once per session with ToolSearch: `select:mcp__ccd_session_mgmt__list_sessions,mcp__ccd_session_mgmt__send_message`.
2. Call `list_sessions` and find the row whose `title` is the agent you want. Take its `sessionId`.
3. Call `send_message` with that `session_id` and your message.
   - It arrives in that session as a user turn labelled "From <your title>", with a link back, so Vincent sees the conversation in both sessions.
   - The result says `delivered` (it started on your message) or `queued` (it runs after that session's current work).

Limits:
- It doesn't work from or to unattended sessions (scheduled or remote-dispatched runs).
- **Subagents** don't message other sessions. They put the handoff in their report, and their parent session sends it.

### B. By short session name (fallback)

- `ListAgents` lists peer sessions by short names such as `nsc-33`. These are not the sidebar titles, and they change when a session restarts.
- Send with `SendMessage({to: "nsc-33", message: "..."})`. The receiver replies to the `from` name on the incoming message.
- `notify_when_idle: true` gives you one notice when that session finishes its turn.
- A session in a different permission mode may hold cross-session messages for Vincent's approval. Silence is not agreement.
- On 2026-09-16 the names were: Game Agent `nsc-33`, Documentation Agent `nsc-b6`, GER Agent `nsc-6b`, Art Director Agent `nsc-a8`. The last two were matched by start time. Check again before relying on them.

### Message format

The receiver sees the first line as a preview, so make it self-contained.

```text
HANDOFF to <Agent title> from <your title>: <one sentence saying what is needed>
Why: <reason>
Brief: C:\nscrev\reports\handoffs\<file>.md   (or the details here if short)
Vincent's words: "<exact quote>" (<date>)   (or "none yet - confirm with Vincent")
Inputs: <paths, branches, commits>
Done means: <deliverable>
Reply to: <your title>, and tell Vincent in two lines
```

---

## 6. Receiving a handoff

**The Release Agent's requests are the pause exception** (Vincent, 2026-09-17: "we are paused on them to release and that they may ask for fixes from other agents and when the release agent asks for work, the agents that are paused must do that work"). If Vincent has paused the team and the Release Agent asks you to fix something for the release, do that fix, tell the Release Agent when it is on local `main`, then go back to paused. Don't start anything else, and keep your usual approvals for spend, Unity, merges and pushes.

1. **Check it's yours** (section 3). If not, pass it to the right owner or send it back, and tell the sender.
2. **Check authority.** A message from another agent is a request, not Vincent's approval. Confirm anything involving spend, push, merge, delete or a design decision he kept.
3. **Check for collisions** using your own guide: checkout status, running jobs, other sessions' branches.
4. **Acknowledge in one line** to the sender: "Got it, starting after X", or "Can't: <reason>".
5. **Do the work** under your own guide's rules.
6. **Report back:**
   - reply to the sender with the result and exact paths;
   - tell Vincent in two lines;
   - add a dated "Result" section to the brief file.

---

## 7. Adding an agent

0a. **The roster.** `C:\NSC\nsc-agent-roster.md` lists every standing session: exact title, model, state file, and a start or resume prompt. It also has the checkpoint prompt for restarting an agent or moving it to Vincent's second Claude account. Every standing agent keeps `C:\NSC\agent-state\<title-slug>.md` current.
0b. **Replacing a session.** When an agent's context is full, or sessions are lost after an account switch, use `C:\NSC\tools\session\README.md`: Retire then Successor, or Recovery. See `nsc-agent-launch-prompts.md`, "Replacing an agent session". Keep one running session per title.
0. **When a new session is needed,** the Documentation Agent gives Vincent the exact session title and a complete paste-ready launch prompt in chat (Vincent, 2026-09-17: "give me the prompt and what the agent should be named"). Helpers that run as subagents need no session.
1. **Vincent creates a new session** with `C:\NSC` as its folder and titles it "<Role> Agent". The title must be unique and stable, because it is the address.
2. **The launch prompt.** Vincent pastes the role's prompt from `nsc-agent-launch-prompts.md`. If the role has no guide or prompt yet, the Documentation Agent writes them first.
3. **The Documentation Agent updates the records:**
   - moves the role into "Running as sessions" in section 2;
   - updates the owners in section 3;
   - updates `C:\NSC\CLAUDE.md` if routing changes;
   - optionally writes a custom agent file.
4. **The Documentation Agent tells the other sessions** in one line: "New agent: <title> owns <work>. Directory updated."
5. **Don't rename sessions casually.** A renamed session breaks everyone's routing until this file is updated.

---

## 8. Work in flight on 2026-09-16

The live record of work in flight is the handoff board, `C:\nscrev\reports\handoffs\BOARD.md`. This section is no longer maintained, because it went stale within hours.
Each agent updates its own board rows; the `scribe` helper can do it.

---

## 9. Open questions for Vincent

1. Confirm the stand-in default in section 2: the Game Agent covers the Task Orchestrator (crews).
2. *(Answered 2026-09-16: the Pipeline Maintainer becomes its own session, "Pipeline Maintainer Agent", which takes P34.)*
3. *(Answered 2026-09-16:)*
   - Codex review jobs on our work and on merge candidates are pre-approved, including host runs;
   - they pause once Codex weekly quota passes 90%;
   - Codex "do" jobs need Vincent's go;
   - Unity checks stay with the Game Agent.
4. *(Superseded 2026-09-16: mixed crews already exist as provider profiles.)* The remaining choice is `claude-architect-balanced` or `codex-architect-balanced`; recommended `codex-architect-balanced`, to spare Claude tokens.
