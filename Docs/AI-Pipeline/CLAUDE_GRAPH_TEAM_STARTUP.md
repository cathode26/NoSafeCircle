# Claude graph team startup

Read [the shared startup sequence](GRAPH_TEAM_STARTUP.md) first. This page pins
the Claude graph-management roles and an optional legacy identity diagnostic.
Orchestrator Sol is separate; the Opus lead below is Graph Sol. These agents
coordinate graph tasks through the individual task workflow; implementation
crews inside game tasks are separate.

| Role | Claude model | Effort | Assignment |
| --- | --- | --- | --- |
| Graph Sol (Sol equivalent) | Opus 5 | xhigh | Persistent graph lead; runs eligible graph tasks within current priorities and limits. |
| Luna equivalent | Sonnet 5 | medium | Bounded setup and preparation pass assigned by Graph Sol. |
| Spark equivalent | Haiku 4.5 | medium | Read-only observer and evidence-based escalation. |

Start Graph Sol as the parent Claude Code session for its graph team. It starts the setup and
observer agents with explicit model, effort, prompt and tool permissions. The
observer must have read-only tools. Verify the actual sessions before graph
work; the diagnostic cannot create them or test model availability.

For the currently recorded real-game Source and Claude implementation-crew
config, this optional read-only identity diagnostic may be run from PowerShell
5.1 when investigating legacy records:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\NSC\NSC\NoSafeCircle\Pipeline\AssistantControl\Check-ClaudeGraphTeamStartup.ps1 -Source C:\NSC\NSC\NoSafeCircle -CheckoutRoot C:\NSC\NoSafeCircle-AssistantCheckouts -WorkerConfig C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\worker-claude-sonnet-high.json -ExpectedBranch main
```

It also checks that the selected implementation-crew config is Claude-only and
the local Claude Code CLI responds. Replace paths if the current Source,
checkout root or crew config changed. The checked branch and clean Source
must be the intended graph Source. This diagnostic is not permission or
clearance to start a retired controller; follow the conversational startup
sequence in the shared guide. No provider spend or candidate approval follows
from this check.
