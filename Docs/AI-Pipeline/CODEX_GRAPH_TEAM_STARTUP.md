# Codex graph team startup

Read [the shared startup sequence](GRAPH_TEAM_STARTUP.md) first. This page pins
the Codex graph-management roles and the Codex check command. Primary Sol is a
separate overall orchestrator; the Sol below is Graph Sol. These agents
manage AssistantControl; task implementation crews are separate and may use
Claude or another explicitly configured provider.

| Role | Codex model | Effort | Assignment |
| --- | --- | --- | --- |
| Graph Sol | `gpt-5.6-sol` | ultra | Persistent graph lead and sole normal graph-controller authority. |
| Luna | `gpt-5.6-luna` | medium | One fresh bounded `--delegate-safe` setup pass. |
| Spark | `gpt-5.3-codex-spark` | high | Read-only observer and evidence-based escalation. |

This is the proven September 11 Codex Gauntlet mapping. Use the Codex agent
platform to start Luna and Spark with these explicit models, efforts and role
limits; verify the actual sessions before Graph Sol starts normal `run-graph`. The
script prints the expected roster but cannot create or verify the sessions.

For the currently recorded real-game Source and Claude implementation-crew
config, run this read-only check from PowerShell 5.1:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\NSC\NSC\NoSafeCircle\Pipeline\AssistantControl\CodexGraphTeamStartup.ps1 -Source C:\NSC\NSC\NoSafeCircle -CheckoutRoot C:\NSC\NoSafeCircle-AssistantCheckouts -WorkerConfig C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\worker-claude-sonnet-high.json -ExpectedBranch main
```

The worker config names the per-task crew provider; it does not select the
three Codex graph-management agents. Replace paths if the current Source,
checkout root or crew config changed. The checked branch and clean Source
must be the intended graph Source, not an arbitrary agent worktree. Then
follow every step in the shared startup sequence, including the separate
delegated and normal `graph-preflight` bindings.
