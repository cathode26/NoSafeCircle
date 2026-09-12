# Conversation-operated task tools

For the operating role, read
[Assistant Software Architect operating guide](../../Docs/AI-Pipeline/ASSISTANT_SOFTWARE_ARCHITECT.md).
For a short handoff, read [CURRENT.md](CURRENT.md). Historical test details are in
`STATUS.md`.

Vincent talks to the assistant to select work, start or stop workers, request
changes, and approve a tested result. The visualizer displays the same task
records. It does not start work or grant approval.

Before creating or revising a game task, read [Game Task Lessons Learned](../../Docs/AI-Pipeline/GAME_TASK_LESSONS_LEARNED.md). Keep new visual-bug lessons there so the next task benefits from previous investigations.

## Available now

From the repository root, `python -m Pipeline.AssistantControl.inspect_project`
returns JSON with the checkout, branch, commit, local edits, and committed task
definitions. Add `--task NSC-042` for its complete contract. `--source` can name
another checkout. These commands do not start providers, contact GitHub, refresh
the Git index, or modify files. A dirty Unity project remains inspectable.

The inventory does **not** claim tasks are ready to run or delivered. It reports
exact file conflicts for declared scene/file resources, including rename sources.
Worker liveness and dependency evidence are available through the separate
commands below.

`python -m Pipeline.AssistantControl dependencies NSC-042` separately reads the
existing TaskGraph conformance evaluator at one committed HEAD. It reports the
task's evidence and each dependency's evidence, rather than inferring delivery
from a green viewer node or an Issue label. This is not permission to execute:
resource ownership, worker capacity and scope still need to be checked.

`python -m Pipeline.AssistantControl readiness NSC-042` performs those remaining
checks without reserving capacity or starting anything. It reports a compact list
of blockers covering dependency evidence, owned checkout and scope state, worker
capacity, resource reservations, and conflicting local Source edits. A ready
result still grants no execution authority; an explicit `reserve` and authorized
worker launch remain separate actions.

The common interface is `python -m Pipeline.AssistantControl`. Its `status`
command is read-only. `prepare` accepts a task ID and a required `--source-commit`
copied from inspection, plus global `--source` and `--checkout-root` arguments.
It creates a standalone clone under `<checkout-root>/<TASK-ID>` and records its
starting commit outside Source. It never starts a worker or copies uncommitted
changes. `checkout <TASK-ID>` reports the current branch, commit and edits.
These are assistant-facing commands; Vincent does not need to paste them.

Preparation is idempotent: reopening an owned checkout preserves worker edits.
An existing unowned folder is refused, never overwritten. Interrupted staging
is preserved for inspection; publication completed before its receipt can be
recovered only if the checkout still matches the exact clean starting commit.
Preparation alone neither admits nor launches work; a prepared project is not
reported as running.

`refresh-prepared TASK --source-commit SHA` updates only a clean, never-started
owned checkout to the inspected Source commit. It refuses work or admission
history, clears the previous scope, and retains preparation history. Source's
working edits are not copied. A task that has actually run uses the candidate
revision/synchronization workflow instead.

The `viewer` subcommand serves the existing Gauntlet graph on localhost (port
8813 by default). It requires `--checkout-root`. It starts no workers, and all
POST/PUT/PATCH/DELETE requests are refused. The task panel shows each owned
checkout's current commit and folder. Broken task records remain visible as
blocked. Verified candidates show human review, approval pending integration,
or requested changes. Approval alone never means locally accepted. Worker and
launch records supply task status, including exact process-identity checks.
When any candidate needs Vincent's test, the page headline changes to
`🐴 Vincent needed` and lists the waiting task IDs.
The viewer has been HTTP-tested and its conversation-control idle state checked
in a browser. It does not replace or stop an
already running viewer.

`review` records Vincent's explicit approve/reject message and exact tested
commit; a changed or dirty candidate cannot reuse that approval. `integrate`
requires an approved registered candidate, the expected Source commit, and the
target branch. It performs a local fast-forward only, never pushes, and refuses
to overwrite local edits. If Source has diverged, the candidate must be updated
and reviewed again. Rejection keeps the task checkout and feedback. A crash
after Git finishes but before the integration record is saved is recoverable.

GitHub publication remains a separate explicit boundary. `publish-approved TASK
--candidate-commit SHA [--base-branch main]` accepts only Vincent's exact human
approval; synthetic Gauntlet approval is insufficient. It pushes that literal
commit to the recorded `assistant/TASK` branch with an exact remote-head lease,
then creates or reuses the sole matching pull request. Source `origin` is the
only repository authority, and `--repo owner/name` is only a matching assertion.
It never uses Issues, integrates Source, pushes the base branch, or merges.

`inspect-ci TASK --candidate-commit SHA [--base-branch main]` verifies the
remote task branch and pull-request head still equal that approved commit before
classifying GitHub's check rollup. Empty, ambiguous, and unknown checks remain
pending. Both commands retain a hash-chained, atomic receipt at
`.assistant-control/publications/TASK.json`; interrupted branch or PR operations
must reconcile their exact remote result before another mutation.

`sync-candidate TASK --candidate-commit SHA --source-commit SHA` handles a clean
merge when Source advanced after this candidate was created. An unreviewed
`awaiting_human` candidate may be synchronized before Vincent's first test, and
an exactly approved candidate may be synchronized before integration. It
merges only the inspected committed Source version in staging, verifies Git's
merge tree and original task paths, then fast-forwards the owned task checkout.
Source's working files stay untouched. The original candidate and approval are
retained as history; the new commit is marked mechanically synchronized and must
be tested and explicitly approved again. It has no new crew review. Conflicts
retain staging and leave the original task checkout unchanged. An interrupted
publication can be recovered by repeating the exact original command.

Rejecting a synchronized candidate now preserves that merged version as the next
worker's base. A fresh scoped crew receives the exact rejection notes through
`revision_feedback_file`; it does not replay the old candidate patch or inherit
old scope/provider settings. Its result must bind the saved feedback bytes before
candidate registration. Every crew run keeps its own commit receipt, and observing
an already registered result preserves Vincent's existing decision.

Fresh-feedback execution requires a checkout with the updated ExecutionCrew
runtime. Older prepared checkouts do not understand the new CLI option; they have
not been silently edited or upgraded. Repeated clean synchronizations retain each
prior candidate and require approval again. Replaying an old completed operation
does not roll back newer work. Merge conflicts remain retained for inspection
rather than auto-resolved.

`candidate TASK --run-id CREW_RUN --config FILE` verifies an existing crew receipt
and commits it for human review. Recovery after commit-before-registration uses
a disposable base clone and real bridge/committer checks. This passed fixture
artifact integration tests, not a paid-provider run. Other gate tests install
fixture candidate records explicitly. Neither fixture grants real human
approval; the assistant must never invent Vincent's test result to call `review`.

For a Door Prototype result, `materialize-candidate TASK --candidate-commit SHA`
runs `DoorPrototypeSceneBuilder.Build` in that owned checkout, accepts only the
Unity-generated paths registered by the task scope, commits those exact outputs,
and runs the task's committed Unity tests against the resulting clean commit. It
launches no model and grants no approval. A failing test is retained as feedback
for another crew. The failed commit cannot be approved; `revise` converts its
exact validation error into a fresh-feedback worker baseline. A passing result
still needs Vincent's visual inspection.

`post-crew TASK --run-id CREW_RUN --config FILE [--unity-executable PATH]` is the
one bounded command for the Windows orchestrator to use right after a crew run
ends. It calls the existing `candidate` step. When the task's scope registers a
Unity-serialized DoorPrototype output, it calls the existing
`materialize-candidate` step; otherwise it runs the committed task validation
directly against the exact clean code candidate. It adds no new Git, scope,
receipt or Unity-builder logic of its own. It returns one compact
JSON result: task ID, checkout path, the crew's original candidate commit, the
materialized candidate commit (`null` when no Unity builder applies), the
generated paths, the Unity log path, focused test results, `status:
awaiting_human`, and exact visual reproduction instructions. If Unity cannot be
resolved before launch, it retains the crew-reviewed candidate untouched and
reports `status: NEEDS_MATERIALIZATION` with the exact error and
`materialize-candidate` command to rerun once Unity is available — this is never
treated as a source defect. A failure after materialization starts is retained
as `status: materialization_failed` for inspection and is never shown as ready
for human review. If the focused Unity tests fail, it reports `status: validation_failed`
with the failure text and the exact `revise` command; it never calls `revise`
itself. Re-running the same task/run-id after a crash recovers the same
candidate or materialization outcome instead of creating a duplicate commit or
relaunching Unity on an already-retained failure. It never approves,
integrates, pushes, publishes, or starts another crew.

`python -m Pipeline.AssistantControl --source SOURCE --checkout-root ROOT
register-restored-candidate TASK --base-commit SHA --candidate-commit SHA --candidate-tree SHA
--task-contract-sha256 SHA --changed-paths FILE --evidence FILE
--reference-provenance FILE` registers a committed assistant-restored Unity
candidate for Vincent's review. The owned checkout must be clean, on its recorded
branch, based exactly on the pinned commit, and have no active reservation or
unsettled worker. The supplied changed paths must match the committed diff and
the registered scope. The record marks `kind: assistant_restored` and
`crew_review: false`, retains worker history, clears approval, and enters
`awaiting_human`. Evidence and reference provenance are recorded as claims for
Vincent to inspect; they do not grant approval, admit a worker, or publish to
GitHub. This path is separate from the authenticated crew receipt adapter.

Use `scope TASK --plan FILE --lease-id ID` to validate an explicit JSON
ExecutionScopePlan for an owned clean checkout. This reuses the existing scope
validator; it does not admit or launch a worker.

Pass `--checkout-root` before `dependencies TASK` to include assistant-approved
local integrations. A candidate must be integrated into Source, match its
receipt and current task contract, and have the exact human approval. This
does not claim production delivery or Unity conformance.

Current implementation status and delegated work are recorded in `STATUS.md`.

## Fresh local Gauntlet replay

`gauntlet-replay --branch gauntlet-replay/NAME` creates the one fixed eight-task
replay family for local visual testing. Run it only in a clean local clone whose
current branch has that exact name and which has no Git remote. It creates fresh
root contracts for NSC-998, NSC-1101, NSC-1103, NSC-1104, NSC-1105, NSC-1107,
NSC-1108 and NSC-1110, plus separate replay tests and validation policy. It does
not create implementation scripts or decomposition children; the architect
allocates child IDs later. NSC-042 and NSC-899 are deliberately excluded. The
command has no custom task mapping and runs `taskcontrol validate` before it
reports success.

`reserve TASK --run-id ID --capacity 1` checks dependencies, scope and resource
ownership without launching a provider. `run-worker TASK --run-id ID --lease-id
LEASE --config FILE --authorize-provider-spend` runs the admitted crew in the
foreground by waiting for a dedicated contained child. Ctrl-C sends that run a
cooperative stop request. Use only after Vincent has authorized that provider work. Model and
provider and `credential_volume` (existing named Docker volume) must be explicit
in the JSON configuration. A per-run Compose override maps the provider to that
external volume without reading credentials or changing the shared Compose
project. Codex effort can be set
with `execution_reasoning_effort`; this existing bridge does not support a
Claude effort argument. No provider work has been launched in verification.

`worker-status TASK` checks the retained worker and Windows process identity.

## Small maintenance tickets

Maintenance is for looking at work that already exists. Create one ticket with
`maintenance-plan TASK --action inspect-worker|verify-candidate|settle-worker|cleanup-worker-docker --run-id ID`,
then run it with `maintenance-run TICKET.json`. Tickets are tied to this source,
checkout, branch, commit, task contract, worker and run. They cannot launch an
agent, change Git, run Unity, approve work, or remove volumes. Docker cleanup is
allowed only after the worker is terminal, capacity is released, and its host
and job are confirmed finished. A completed ticket can be run again safely; it
returns the saved receipt.
`inspect-result TASK [--run-id ASSISTANT_RUN]` is read-only. It re-hashes the
retained `crew_result.json` and candidate patch, verifies their task/run/source/
contract identities, and returns a bounded summary plus the exact artifact paths.
It does not trust a test name or worker label as proof that the bytes still match.
`stop-worker TASK --run-id ID` writes a cooperative stop request for that exact
run. A request is not an exit confirmation. Neither command releases capacity,
deletes work, or claims Docker child cleanup. `start-worker` accepts the same
arguments as `run-worker` and launches a hidden dedicated process after saving
a bound readiness receipt. Before that receipt is published, the child is assigned
to a Windows Job Object so its future host descendants can be stopped together.
`stop-worker --force` stops that owned process tree and only run-bound containers,
preserving files. `settle-worker TASK --run-id ID` releases capacity after host,
contained-tree and container exit checks; succeeded crews also require unchanged
result artifacts. Failed/stopped runs require a contained tree. A launch that
never created a child can settle from its explicit spawn-failure record; a
pre-readiness child failure requires confirmed exit through its retained handle.
After settlement a different run can retry, retaining the previous attempt and
all task files. Existing edits must still satisfy admission; retry never resets
the checkout. Both `start-worker` and `run-worker` use the same contained launcher.
The complete live provider/Unity workflow still needs verification.

After approved integration, `preserve-success` keeps a standalone Git/Unity
project at `C:\NSC\SuccessfullTasks\<TASK-ID>` (override with `--success-root`
for tests). It clones the exact approved commit, retaining Git history while
leaving the worker's project in place; ignored Unity Library/cache files are
not copied. It refuses any pre-existing unowned destination. In particular the
working `SuccessfullTasks\NSC-042` Vincent found must not be overwritten or
automatically adopted. The viewer shows the saved folder only after checking
its commit and the corresponding approved integration in Source.

## Bounded graph controller

`graph-plan` reads the selected committed task graph and reports the next
deterministic actions without changing files, reserving capacity, or starting a
provider. Repeat `--task` to select several roots; committed descendants are
included automatically, transitive prerequisites are brought into scope, and
dependencies are rechecked after every Source change.

```powershell
python -m Pipeline.AssistantControl `
  --source C:\NSC\TenTaskFinalIntegration-20260905 `
  --checkout-root C:\NSC\AssistantGauntletPublishRetry `
  graph-plan --task NSC-898 --task NSC-1008 --auto-approve-gauntlet
```

`run-graph` resumes those actions from durable AssistantControl records. Provider
work requires both a worker configuration and `--authorize-provider-spend`.
`--auto-approve-gauntlet` applies only to authenticated synthetic Gauntlet tasks;
NSC-042 always stops at exact-commit human review. The controller never pushes.

For cheaper delegated help, add `--delegate-safe`. That mode may prepare or
refresh checkouts and create exact scopes. It returns `handoff_required` before
reservation, provider or Docker interaction, worker waiting/settlement,
post-crew processing, decomposition, candidate synchronization, approval, or
integration. This lets a small agent perform portable setup without giving it
authority over the graph or final results. Delegated mode does not require a
worker config and rejects `--authorize-provider-spend`.

`worker-haiku.example.json` is the checked-in, non-secret worker configuration
used by the examples. It names the existing Docker credential volume but contains
no credential bytes. The graph controller adds execution authority only at an
explicitly authorized provider launch.

The detailed policy and examples are in
[ASSISTANT_AUTONOMOUS_GRAPH.md](../../Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md).

## Workflow

1. Inspect committed tasks, delivery evidence, active workers and resource use.
   The assistant chooses work with Vincent. No background architect chooses it.
2. Create an isolated, complete Git/Unity checkout, plan its scope, then reserve
   the task. The checkout is named
   exactly for its task ID. Pin the source commit and task contract. Existing
   edits in Vincent's project remain untouched; they are never silently copied
   into a worker's starting point.
3. Launch the existing ExecutionCrew against an explicit approved scope. Record
   the provider/model/effort, process identity, checkout, output paths and result.
   Stop must reach the worker and its child processes. A stale PID is not proof
   that a worker is alive or permission to kill another process.
4. Inspect the durable crew result and patch, verify permitted changes and Unity
   .meta companions, then commit the reviewed code candidate in its task checkout.
   Run any registered Unity builder and focused tests before human review.
   Neither crew review nor task completion grants human approval.
5. Show the exact folder and commit in the read-only visualizer. Vincent opens
   that Unity project, tests it, and approves or requests changes in conversation.
6. Record approval against that exact commit. Integrate approved work locally
   only when the target can be updated without overwriting Vincent's edits.
   A changed candidate requires another approval. If changes are needed to
   resolve integration conflicts, present the resulting version for testing.
7. Update dependency evidence after integration. Decomposition children retain
   their parent and go through the same checkout, review and approval path.

## Implementation boundaries

- Reuse `ExecutionCrewBridge`, scope validation, patch validation and the Git
  identity guard where their preconditions apply. Do not invent legacy Issue
  leases just to pass an old controller check.
- `LocalTaskCheckoutManager` currently requires a LocalRunContext and its lease
  history. Extract or adapt the isolated-clone mechanics rather than running an
  autonomous scheduler to obtain those records.
- Persist assistant-owned task records outside the Unity Source directory.
  Commands and the viewer must read one source of state, surviving chat restarts.
- A read-only viewer must refuse mutation routes on the server, not just hide
  buttons. Keep existing modes available until this replacement is proven.
- GitHub publication is an explicit operation, not a side effect of local review.
- Tests use disposable Git repositories and fixture workers. They must exercise
  failure, restart and changed-commit approval cases. Paid-provider and Unity
  testing remain separate and require an authorized live demonstration.

## Completion evidence still required

Focused tests cover capacity/resource reservations, worker launch/stop/retry,
validated candidate commit, exact approval/rejection, integration recovery,
and viewer projection. A fixture demonstration covers candidate verification
through approval, local integration and successful-project preservation.

`revise TASK --candidate-commit SHA` preserves an exactly rejected candidate as
the new starting commit, retains prior review/worker records, and clears approval.
It requires settled worker capacity and a fresh scope/admission. The revision
state and approval boundaries are fixture-tested. For an ordinary candidate the
worker passes exact rejection notes through ExecutionCrew's existing retry path.
A synchronized candidate uses the separate fresh-feedback path described above.
A real-Git component
test exercises that retry with fixture provider responses and verifies the notes
in implementer, test-author and validator prompts. The previous candidate is
verified as already present; Source remains unchanged. Retry currently requires
compatible scope and the same provider/model/effort configuration. This proves
feedback delivery to provider requests, not paid-provider behavior or Unity visuals.

Still pending: broader live demonstrations with Vincent's actual test decisions.
Existing child contracts can be inspected and processed as tasks. AssistantControl
also supports an explicit decomposition boundary: `decompose` runs one bounded
cross-provider author/reviewer pair against read-only Source,
`inspect-decomposition` rechecks its exact durable artifacts, and
`apply-decomposition` creates the canonical local D1C commit only while the reviewed
source, contract and plan are still exact. These commands never push.
No fixture result is evidence that NSC-042's gameplay works.
