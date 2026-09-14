# Graph-management team startup

This is the restart instruction for the conversational AssistantControl graph.
It preserves the three graph-management jobs proved in the September 11–12
Sol/Luna/Spark runs. These agents manage the graph; AssistantControl launches
separate execution crews for individual game tasks. `--capacity 3` counts
execution slots and does not create this team.

## Two Sols, one graph controller

Primary Sol is Vincent's overall orchestrator. It sets priorities, owns
task bugs and shared tooling repairs (directly or through a bounded repair
agent), decides the intended graph scope, and handles Vincent's decisions.
Graph Sol is a separate session and the lead of the three-agent graph team
below. Primary Sol may inspect graph records and ask Graph Sol to change
priorities or scope. It does not run a second controller or directly edit
Graph Sol's task checkouts or controller records. Graph Sol reports blockers,
candidates and progress to Primary Sol; Primary Sol reports to Vincent.

| Graph-team role | Job | Allowed graph activity |
| --- | --- | --- |
| Graph Sol (lead) | Keep eligible game tasks moving through the one normal controller; keep Luna's setup and Spark's observations useful across successive task batches. Send bugs to Primary Sol. | Sole authority for normal `run-graph` and graph decisions; delegates only Luna's bounded setup pass and conveys only Vincent's exact candidate decisions. |
| Luna (setup) | Prepare the next eligible batch in a bounded pass, then hand off. A new pass may be assigned at a later released-controller boundary. | `graph-plan` and one identically scoped `run-graph --delegate-safe` per handoff after Graph Sol has bound its preflight. No provider spend, approval, integration or retry. |
| Spark (observer) | Continuously watch durable controller, task and worker records; report changes, stalls and identity drift to Graph Sol. | Read-only inspection. No graph mutation or repair. |

The two Sol sessions may use the same model, but their authority and working
contexts are distinct. Primary Sol is outside the graph team. A task execution
crew is outside both roles.

Primary Sol starts the separate Graph Sol session with this short handoff:

> You are Graph Sol, owner of the one AssistantControl graph controller. Read
> `AGENTS.md`, `Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md`, and the matching
> provider startup page. I am Primary Sol and own priorities, scope decisions,
> and repair lanes.
> Use the exact Source, checkout root, current task priorities and authorization
> I give you. Launch Luna and Spark according to the startup sequence. Send me
> exact blocker evidence. For a task-local bug, stop all work on that task,
> record it as unavailable, verify the plan blocks it, and keep independent
> eligible tasks moving. Stop the whole graph for a major graph or controller
> fault. Do not take over my repair work or assume Vincent approved a candidate
> or new provider spend.

The agent platform may be Codex or Claude. Read the matching
`CODEX_GRAPH_TEAM_STARTUP.md` or `CLAUDE_GRAPH_TEAM_STARTUP.md` beside this
file for the exact model/effort mapping and check command. Use the platform's
native agent launch and tool permissions; a shell script cannot prove that
three independent agent sessions exist. Record each run's actual model and
effort. Do not repurpose an Implementer, Test Author or Validator in a task
execution crew as one of these graph roles.

When Graph Sol resumes in a fresh session without the Primary Sol message,
use this compact handoff:

> Read `AGENTS.md`, `Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md`, and the matching
> Claude or Codex startup page before graph work. You are Graph Sol, the sole
> graph-controller lead under Primary Sol. Run the startup identity check,
> select current eligible targets, and follow the numbered sequence exactly.
> Start one bounded Luna setup agent and one read-only Spark observer through
> the agent platform. For a task-local bug, stop that task, report it to
> Primary Sol, verify the plan blocks it, and keep independent eligible work
> moving. Stop the whole graph only for a major graph or controller fault.
> Keep task execution crews separate. Stop on controller identity ambiguity;
> never infer approval or provider-spend authority.

## Startup sequence (Graph Sol owns it)

1. Read `AGENTS.md`, `Pipeline/AssistantControl/README.md`, this file, the
   matching provider page, and the current task/owner journal. Inspect current
   Source, checkout root, branch, HEAD, worker configuration, controller
   records, and active processes. Run the matching provider startup script
   with the exact Source, checkout root, branch and worker config, as shown in
   its provider page. The shared identity
   check is **not** permission to start a second controller.
2. Select current targets from TaskGraph and real readiness evidence. Respect
   task claims, dependencies, exclusive resources and the separate foreground
   agenda. Record exact task IDs, capacity, target branch, human-review tasks,
   decomposition providers, background-job limit, compose project, scope path,
   worker config and provider-spend authority. Never reuse an old example task
   list or interpret viewer colors as readiness.
3. Graph Sol runs `graph-preflight` for Luna's exact delegated policy: same
   Source, checkout root, targets, capacity and other applicable policy flags,
   with no worker config and no `--authorize-provider-spend`. This persists
   the binding now required by `run-graph`.
4. Launch one Luna with the exact identity and policy. Luna runs `graph-plan`,
   then the identically scoped `run-graph --delegate-safe` once. Luna returns
   the full result and changed checkout/record inventory. Stop at
   `handoff_required` or the first error. Graph Sol verifies the handoff, durable
   records and released controller owner/lock before proceeding.
5. Graph Sol runs a **new** `graph-preflight` for the normal run, including
   the exact worker config, provider settings, human-review settings and
   `--authorize-provider-spend` only when Vincent has authorized that spending.
   The normal `run-graph` command must use the same settings. A changed Source
   commit, config bytes or policy requires another preflight.
6. Launch one Spark with read-only tools and the same Source/checkout identity.
   Graph Sol alone runs the normal `run-graph` attached to its session. Spark
   reports evidence to Graph Sol; Graph Sol reports to Primary Sol. Keep
   independent eligible work moving when another task awaits Unity review or
   a task-local repair. At a later released-controller boundary, Graph Sol may
   assign Luna another bounded setup pass for newly eligible work. Never turn
   a candidate into an approval without Vincent's exact tested-commit decision
   relayed by Primary Sol.

## Blocker and repair handoff

The rule is to stop **all work on the affected task**, mark it unavailable,
and continue other eligible tasks. Graph Sol owns the task stop and continued
graph operation; Primary Sol owns the repair and the decision to release that
task again. A whole-graph stop is reserved for a major graph or controller fault.

When one task hits a bug, Graph Sol records its exact task/run ID, Source
commit, candidate commit if any, controller state, evidence paths and observed
failure, then sends that packet to Primary Sol. Stop work on that task: do not
give it another Luna setup pass or start another implementation crew. If its
worker is still active, use the existing exact-run `stop-worker` path and
verify exit and settlement. Preserve the checkout and all evidence. A
task-owned background job without a safe per-task stop path requires a wider
decision with Primary Sol; never kill an unverified process or erase its record.

Primary Sol records the task as unavailable in the task/owner journal for the
repair period. Graph Sol checks that AssistantControl's durable state actually
blocks new actions for it (for example, a settled `worker_stopped` result or
terminal validation failure). Graph Sol checks `graph-plan` before continuing
with independent eligible tasks. Graph Sol never fabricates a retry, approval
or graph edit to hide the blocker.

Primary Sol owns diagnosis and the repair lane. Repair work happens in an
independent checkout with a bounded scope and validation. Primary Sol does not
edit the live graph's task checkout, clear controller records, or advance the
canonical Source while Graph Sol may be using it. A repair that must enter
Source is handed back as an exact reviewed commit. Graph Sol and Primary Sol
coordinate a safe controller boundary and single Source writer; after Source
advances, Graph Sol rechecks state, runs a new `graph-preflight` for the new
commit/policy, and resumes only work that is eligible.

## Task unavailability and the rare graph-wide stop

For a task-local failure, stop only that task when its exact worker and
background work can be safely stopped or settled. If `graph-plan` shows no
new action for it, Graph Sol continues unrelated eligible tasks while Primary
Sol repairs it. The task is reconsidered only after Primary Sol releases it
and a fresh plan/preflight establish that it is safe.

If a task is suspect but `graph-plan` still proposes new work for it, the
operating note alone has not made it unavailable. Today's CLI has no durable
temporary per-task hold. Graph Sol may continue with another bounded target
set only after verifying that dependency and descendant closure does not pull
the affected task back in. Do not edit controller JSON or use `cancelled` or
`superseded` as temporary pause switches. A direct live hold/release command
would be a later feature; no new implementation is part of this startup work.

Stop the whole graph only for a major fault that may affect controller
ownership, graph records, admission safety, Source binding, or multiple tasks.
Use the documented controlled stop path and let Primary Sol repair it. Primary
Sol still cannot approve a game candidate or authorize new provider spending
on Vincent's behalf without his explicit decision.

If an earlier controller, job, checkout or owner identity is ambiguous, stop
before step 3 and reconcile it using the AssistantControl recovery commands and
durable evidence. Do not erase records, infer a dead process from a PID alone,
or start a second controller. The viewer is read-only. For real game work, never
use `--auto-approve-gauntlet`; GitHub publication requires separate authority.

The external `C:\NSC\AssistantControlEvidence\CLAUDE_GAUNTLET_STAFFING_GUIDE.md`
and `RUN_REAL_GAME_GRAPH_WITH_CLAUDE_TEAM.md` preserve historical prompts and
runs. Their old task IDs and command examples are not current startup authority;
the current AssistantControl preflight gate and this sequence govern new runs.
