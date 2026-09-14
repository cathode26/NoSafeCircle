# Graph-management team startup

This is the restart instruction for the conversational Sol/Luna/Spark graph
team. The team manages graph work directly through the existing task workflow;
the former autonomous AssistantControl controller process is retired. These
agents are separate from the implementation crews used inside individual game
tasks.

## Authority and roles

Orchestrator Sol is Vincent's overall orchestrator. It receives Graph Sol's
reports about task problems, tells Vincent, coordinates diagnosis and repair
with him, and tells Graph Sol when a task may be reconsidered. Orchestrator Sol
does not select each graph task or provide a fresh exact task list for every
session.

Graph Sol runs eligible graph tasks. It reads the durable current graph and
task status, applies Vincent's current priorities and limits, coordinates Luna
and Spark, and keeps independent eligible work moving. Graph Sol may make
ordinary task and sequencing decisions within those priorities and limits. It
escalates genuinely missing or conflicting authority to Orchestrator Sol.

Luna performs bounded setup and preparation work assigned by Graph Sol. Spark
observes task, worker and evidence records with read-only access and reports
changes, stalls or identity concerns to Graph Sol. Neither agent approves
candidate commits, authorizes provider spending, changes graph authority or
performs repair. Task implementation crews remain separate from all three
graph-management roles.

## Starting or resuming Graph Sol

Read `AGENTS.md`, this guide, the matching provider page, the current task and
owner journal, and the relevant AssistantControl documentation. Inspect the
durable Source, checkout root, branch, graph, task status, active work,
priorities, limits, worker configuration and evidence. Use the provider page's
read-only identity diagnostic only when useful for investigating an existing
legacy record; it is optional and is not clearance to start a controller.

Select work from current graph state and readiness evidence. Respect claims,
dependencies, exclusive resources, the foreground agenda and provider-spend
limits. Record the selected task IDs, capacity, target branch, review needs,
provider settings and any other scope that matters to the current work. Do not
reuse an old example task list or infer readiness from viewer colors.
For a live port 8828 graph view, use the Source and checkout root shared with
the active workers. Follow the viewer command and held-task overlay notes in
[AssistantControl's viewer guide](../../Pipeline/AssistantControl/README.md);
an isolated viewer copy can display the
contracts and GER holds while showing zero live workers. Check the worker
record in the live checkout root before treating that count as a task stall.
Prefer retained unfinished candidates before fresh work. In general, establish
an object's visual identity before scheduling detailed work on its speed,
health, or behavior. Prefer its visual task first when both are available; this
is a sequencing preference, not an added dependency or hard gate.
An outdated clean contract record or an undeclared new script/test path is not
by itself a reason to stop implementation. Refresh clean metadata, let the
worker add needed files in its task checkout, and preserve any dirty candidate.

Start one bounded Luna setup agent and one read-only Spark observer through the
agent platform, with the exact scope and role limits Graph Sol assigned. Graph
Sol then runs graph tasks through the existing approved task workflow. The
exact execution entry point follows that workflow and current repository
guidance; this guide does not authorize a retired controller command. Record
the actual model, effort, scope and outcome for each agent. Keep task crews
isolated in their owned checkouts and never treat a graph candidate as approved
without Vincent's exact tested-commit decision relayed by Orchestrator Sol.

When Graph Sol resumes in a fresh session, it should read the durable current
graph, task status, priorities, limits and owner journal before acting. It may
derive the eligible task set from those records. It does not need an exact task
list from Orchestrator Sol. If those records conflict or omit authority needed
for a consequential action, pause that action and escalate to Orchestrator Sol.

## Task problems and repair

For a task-local bug, Graph Sol stops all work on the affected task, preserves
the checkout and evidence, and reports a packet to Orchestrator Sol containing
the task and run identifiers, Source revision, candidate revision if any,
observed failure, current work state and evidence paths. Graph Sol records the
task as unavailable in the existing task/owner journal process. Maintain an
explicit unavailable-task list there (for example, the
`.assistant-control/graph-lead-journal.md` operating note); refresh and
reconcile it with live task records before relying on it. Exclude each listed
task and its affected dependents from every manual task selection, and check
that list before every start. A journal entry does not make the CLI exclude a
task automatically. If exclusion cannot be guaranteed, escalate the affected
work and do not start it. Do not invent a CLI hold command, edit controller
JSON, or use `cancelled` or `superseded` as a temporary pause state.

If an active worker or background job has an existing safe, exact per-task stop
path, use that path and verify exit and settlement. If safe exclusion or stop
cannot be established, escalate the affected work and continue only with tasks
whose independence is demonstrated by the current graph and evidence. Use the
individual inspect, dependencies, readiness, reserve and worker commands
documented in `Pipeline/AssistantControl/README.md` as the direct task
workflow. Do not retry the affected task, give it another setup pass, erase its
records or kill an unverified process.

Orchestrator Sol owns diagnosis and repair with Vincent. A repair uses an
independent checkout and bounded validation. The task is reconsidered only
after Vincent and Orchestrator Sol resolve the problem, Orchestrator Sol tells
Graph Sol to reconsider it, and Graph Sol verifies fresh graph and readiness
evidence. A Source, policy or worker-configuration change requires fresh
Source and task-readiness checks before starting more work.

Stop the whole graph only for a major shared fault affecting graph integrity,
task admission safety, ownership, Source binding or multiple tasks. Otherwise,
Graph Sol keeps demonstrably independent eligible work moving while the
affected task is repaired.

The external historical staffing and real-game prompt files preserve earlier
runs. Their task IDs and command examples are historical evidence, not current
startup authority.
