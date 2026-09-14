# Codex graph team startup

Read [the shared startup sequence](GRAPH_TEAM_STARTUP.md) first. This page pins
the Codex graph-management roles and an optional legacy identity diagnostic.
Orchestrator Sol is separate; the Sol below is Graph Sol. These agents
coordinate graph tasks through the individual task workflow; implementation
crews are separate and may use Claude or another explicitly configured provider.

| Role | Codex model | Effort | Assignment |
| --- | --- | --- | --- |
| Graph Sol | `gpt-5.6-sol` | ultra | Persistent graph lead; runs eligible graph tasks within current priorities and limits. |
| Luna | `gpt-5.6-luna` | medium | Bounded setup and preparation pass assigned by Graph Sol. |
| Spark | `gpt-5.3-codex-spark` | high | Read-only observer and evidence-based escalation. |

This is the proven September 11 Codex Gauntlet mapping. Use the Codex agent
platform to start Luna and Spark with these explicit models, efforts and role
limits; verify the actual sessions before Graph Sol starts graph work. The
script prints the expected roster but cannot create or verify the sessions.

For the currently recorded real-game Source and Claude implementation-crew
config, this optional read-only identity diagnostic may be run from PowerShell
5.1 when investigating legacy records:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\NSC\NSC\NoSafeCircle\Pipeline\AssistantControl\CodexGraphTeamStartup.ps1 -Source C:\NSC\NSC\NoSafeCircle -CheckoutRoot C:\NSC\NoSafeCircle-AssistantCheckouts -WorkerConfig C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\worker-claude-sonnet-high.json -ExpectedBranch main
```

The worker config names the per-task crew provider; it does not select the
three Codex graph-management agents. Replace paths if the current Source,
checkout root or crew config changed. The checked branch and clean Source
must be the intended graph Source, not an arbitrary agent worktree. This
diagnostic is not permission or clearance to start a retired controller;
follow the conversational startup sequence in the shared guide.
