---
name: nsc-cleanup-agent
description: "Running session since 2026-09-18 (reinstated same evening after a decline): Cleanup Agent owns branch/worktree triage and disk cleanup; writes a plan plus dry-run script, guide C:/NSC/nsc-cleanup-agent-guide.md, Vincent runs the script"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7ac61a9b-fe91-45d1-81ef-52b5c8578408
  modified: 2026-09-19T02:20:12.926Z
---

**2026-09-18, running:** Vincent, asked whether to create the Cleanup Agent session, first answered `"no clean up agent"`. About an hour later, same evening, he reversed that again: `"We need a clean up agent. Please talk to the pipeline maintainer agent about what we found so when you create the agent we have it set up properly."` He then created the session; it announced itself: "Cleanup Agent is running: branch and worktree triage and disk cleanup are mine. I only write plans and scripts; Vincent runs them." The work is its own again — branch and worktree triage, disk cleanup — not reassigned to the Game Agent, which Vincent explicitly took it off on 2026-09-17. The guide, launch prompt and handover brief still apply: the session produces a plan plus a dry-run-by-default script for Vincent to run.

**2026-09-17, original approval (superseded above):** Vincent, to the Game Agent after it started repo hygiene by hand: "no That is not your job, we need a clean up agent." The Game Agent asked the Documentation Agent to set up the role.

**Why the role was proposed:** hygiene kept landing on the Integration Steward between merges. On 09-17 alone the Game Agent examined 272 branches, archived and deleted 133, classified 139 worktrees, and found about 56 GB under `C:\NSC\_worktrees`.

**How the guide still applies, run by whoever picks up the work:**
- **Never delete anything directly.** Write a plan and a dry-run-by-default PowerShell script; Vincent runs it.
- **Never:**
  - deleting or proposing deletion of an NSC-### branch;
  - uncommitted work without Vincent's per-item go;
  - other agents' live clones (check the board, journal and state files first);
  - main, records, SuccessfullTasks, remote branches (Release Agent), or Docker volumes.
- **Task-named worktrees** wait for Vincent's archive decision.
- **Recorded in:** the guide, the roster row, directory 3.1 (Cleanup Agent, not the Game Agent), the runbook index and role table, `CLAUDE.md`'s agent list.

Related: [[never-delete-nsc-task-branches]], [[nsc-agent-directory]], [[no-wipe-commands-for-healthy-runs]].
