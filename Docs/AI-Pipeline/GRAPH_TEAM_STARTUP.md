# Graph-management team startup

This is the restart instruction for the conversational AssistantControl graph.
It preserves the three graph-management jobs proved in the September 11–12
Sol/Luna/Spark runs. These agents manage the graph; AssistantControl launches
separate execution crews for individual game tasks. `--capacity 3` counts
execution slots and does not create this team.

## One authority, three jobs

| Role | Job | Allowed graph activity |
| --- | --- | --- |
| Sol (lead) | Choose eligible targets, own decisions and the one normal controller, handle candidate/recovery handoffs, report to Vincent. | Sole authority for normal `run-graph`, approvals, integration and recovery decisions. |
| Luna (setup) | Check the exact selection and perform one bounded setup pass, then hand off. | `graph-plan` and one identically scoped `run-graph --delegate-safe` after Sol has bound its preflight. No provider spend, approval, integration or retry. |
| Spark (observer) | Watch durable controller, task and worker records; report changes, stalls and identity drift to Sol. | Read-only inspection. No graph mutation or repair. |

The agent platform may be Codex or Claude. Use its native agent launch and tool
permissions; a shell script cannot prove that three independent agent sessions
exist. The proven Codex Gauntlet mapping was Sol `gpt-5.6-sol` ultra, Luna
`gpt-5.6-luna` medium, and Spark `gpt-5.3-codex-spark` high. The Claude mapping
was Opus 5 xhigh / Sonnet 5 medium / Haiku 4.5 medium. Record the actual model
and effort chosen for each new run; do not silently substitute one. Model names
are not the authority boundary: the role, tool access, and sole-controller
rule are. Do not repurpose an Implementer, Test Author or Validator in a task
execution crew as one of these graph roles.

Paste this compact handoff into a fresh orchestrator session:

> Read `AGENTS.md` and `Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md` before graph
> work. You are Sol, the sole graph lead. Run the startup identity check, select
> current eligible targets, and follow the numbered sequence exactly. Start one
> bounded Luna setup agent and one read-only Spark observer through the agent
> platform. Keep task execution crews separate. Stop on controller identity
> ambiguity; never infer approval or provider-spend authority.

## Startup sequence (Sol owns it)

1. Read `AGENTS.md`, `Pipeline/AssistantControl/README.md`, this file, and the
   current task/owner journal. Inspect current Source, checkout root, branch,
   HEAD, worker configuration, controller records, and active processes. Run
   `Pipeline/AssistantControl/Check-GraphTeamStartup.ps1` with the exact Source,
   checkout root and worker config. Its output is an identity check, **not**
   permission to start a second controller.

   For the current real-game paths, the read-only check is:

   ```powershell
   & powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\NSC\NSC\NoSafeCircle\Pipeline\AssistantControl\Check-GraphTeamStartup.ps1 -Source C:\NSC\NSC\NoSafeCircle -CheckoutRoot C:\NSC\NoSafeCircle-AssistantCheckouts -WorkerConfig C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\worker-claude-sonnet-high.json -ExpectedBranch main
   ```

   The lead must replace these paths if the active Source or worker config has
   changed. A checked-out worktree may have a different branch and is never an
   implicit substitute for the real-game Source.
2. Select current targets from TaskGraph and real readiness evidence. Respect
   task claims, dependencies, exclusive resources and the separate foreground
   agenda. Record exact task IDs, capacity, target branch, human-review tasks,
   decomposition providers, background-job limit, compose project, scope path,
   worker config and provider-spend authority. Never reuse an old example task
   list or interpret viewer colors as readiness.
3. Sol runs `graph-preflight` for Luna's exact delegated policy: same Source,
   checkout root, targets, capacity and other applicable policy flags, with no
   worker config and no `--authorize-provider-spend`. This persists the binding
   now required by `run-graph`.
4. Launch one Luna with the exact identity and policy. Luna runs `graph-plan`,
   then the identically scoped `run-graph --delegate-safe` once. Luna returns
   the full result and changed checkout/record inventory. Stop at
   `handoff_required` or the first error. Sol verifies the handoff, durable
   records and released controller owner/lock before proceeding.
5. Sol runs a **new** `graph-preflight` for the normal run, including the exact
   worker config, provider settings, human-review settings and
   `--authorize-provider-spend` only when Vincent has authorized that spending.
   The normal `run-graph` command must use the same settings. A changed Source
   commit, config bytes or policy requires another preflight.
6. Launch one Spark with read-only tools and the same Source/checkout identity.
   Sol alone runs the normal `run-graph` attached to its session. Spark reports
   evidence to Sol; Sol reports to Vincent. Keep independent eligible work
   moving when another task awaits Unity review. Never turn a candidate into an
   approval without Vincent's exact tested-commit decision.

If an earlier controller, job, checkout or owner identity is ambiguous, stop
before step 3 and reconcile it using the AssistantControl recovery commands and
durable evidence. Do not erase records, infer a dead process from a PID alone,
or start a second controller. The viewer is read-only. For real game work, never
use `--auto-approve-gauntlet`; GitHub publication requires separate authority.

The external `C:\NSC\AssistantControlEvidence\CLAUDE_GAUNTLET_STAFFING_GUIDE.md`
and `RUN_REAL_GAME_GRAPH_WITH_CLAUDE_TEAM.md` preserve historical prompts and
runs. Their old task IDs and command examples are not current startup authority;
the current AssistantControl preflight gate and this sequence govern new runs.
