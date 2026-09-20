# Agent operations: tracked source index

This repository is the maintained source for the guidance and utility source indexed here. The 2026-09-20 import records previously untracked host files so they can be reviewed and recovered through Git. Future maintained guidance belongs in this repository; the exact originals below remain historical evidence.

## Current scope

This landing tracks source only. It does not authorize cleanup, deletion, provider calls, task execution, publication by a launcher, or changes to running task records. Existing host files and runtime paths remain in place. The task undo feature is not implemented by this import.

Use the root [AGENTS.md](../../../AGENTS.md) and the current [graph-team startup](../GRAPH_TEAM_STARTUP.md), [AssistantControl documentation](../../../Pipeline/AssistantControl/README.md), and [operator handoff rules](../OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md) for current work. Session instructions and explicit user authorization control the work being performed.

## Preserved sources

- [Host-guide originals and their status](host-guides/README.md): checkpoint/handoff, cleanup, and workspace lifecycle documents copied exactly as found on 2026-09-20.
- [Assistant utility source](../../../Tools/Host/assistant-utilities/README.md): two reusable source candidates and three task-specific historical scripts, with their effects and limitations recorded.
- [Source hashes and original paths](source-map.json): exact byte identity for all eight imported files.
- [Remaining authored host documents](host-documents-20260920/README.md): indexed guides, reports, handoffs and prompts from the top level of `C:/NSC`, including exact-copy mappings to previously preserved guides.
- [Authored guides and durable reports import](../TRACKING_GUIDES_REPORTS_20260920.md): the follow-up import and its scope, report indexes, exclusions and verification boundary.

The cleanup and lifecycle originals already say that their capture/archive architecture was superseded. Their archive repositories, second-copy requirements, retirement steps, historical approvals, and scheduling language do not become active because the files are now tracked. The checkpoint guide also contains dated roles, tool names, usage thresholds, and handoff examples; those are recorded history, not fresh instructions for another agent.

## State kept outside Git

Live task state under `C:/NSC/NoSafeCircle-AssistantCheckouts/.assistant-control` and its adjacent `.task-review-agent`, provider configuration, credentials, session history, and machine caches are not imported. Task undo will need explicit checkpoint and restore rules for the selected task's state and must prevent old workers from publishing. Committing guidance and utility source alone does not provide those guarantees.
