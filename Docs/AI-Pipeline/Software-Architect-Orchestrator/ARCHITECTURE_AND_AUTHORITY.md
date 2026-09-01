# Architecture and Authority

Design guidance for the supervised polling software architect. Not game-design canon and
not evidence of repository state. Status language follows
[`README.md`](./README.md): "implemented now" means present on branch
`orchestrator/polling-architect-v1`; everything else is explicitly marked.

## 1. Steady-state control loop

One scheduler process runs one loop. **Implemented now**, except where marked.

```text
[POLL]
  1. reap finished scheduler children
       nonzero child exit -> stop admitting; do not release durable authority
  2. observe integration reservations
       active scheduler children  -> actual tracked/staged/untracked paths
       durable incomplete workflows -> unmerged branch/checkout paths when observable
       transient observer exception -> WAIT this poll; stop after 3 consecutive failures
  3. build ONE poll-scoped Stage-2 authority observation
       resume candidate first, then Stage-2-produced ranked eligible fresh candidates
       no_safe_work          -> idle until the next poll
       blocked_invalid_state -> stop; this is a deterministic defect, not a wait
  4. compute the stable in-flight membership/identity fingerprint
       current exact actual paths are checked below, not used as cache churn
  5. re-verify each ordered candidate identity against committed HEAD
       task contract hash mismatch or moved HEAD -> fail closed
  6. union the candidate's own observed branch paths/assets over model prediction
  7. deterministic hard-conflict preflight using CURRENT actual paths (no model call)
       conflict -> WAIT this candidate, continue in the same ordered plan
  8. unknown-surface preflight (no model call)
       cannot establish disjointness -> WAIT this candidate, continue
  9. reuse cached/cooldown WAIT/HUMAN_REVIEW, or spend one architect call
       per-poll cap -> end this poll; cumulative session cap -> stop non-success
 10. deterministic admission from the advisory and effective candidate surface
       WAIT / HUMAN_REVIEW -> continue to the next Stage-2-ranked candidate
       START               -> launch exactly one worker, end the pass
[SLEEP]
```

Properties the loop must preserve:

- at most one new worker per poll;
- every launch carries an exact `--task-id` and a unique `--worker-id`, passed as argv with
  `shell=False`;
- the scheduler never calls the mutating generic dispatcher, never pre-acquires an Issue or
  claim lease, and never edits a Task, GDD, resource, or dependency;
- `--dry-run` observes Stage 2 and reservations only: no model call, no worker;
- Ctrl+C stops new admissions without killing children or releasing leases.

## 2. Scheduler singleton

The scheduler holds an OS-backed non-blocking lock (`fcntl.flock` / `msvcrt.locking`) at
`<checkout_root>/.task-review-agent/locks/scheduler-<digest>.lock`. Its identity is the
resolved checkout root, not the source clone, so two source clones using one checkout root
contend on the same file. A second scheduler exits immediately with
`scheduler_already_active`. There is no TTL and no lock stealing: a stale lock file with no
live holder carries no authority, and a live holder is never evicted on a timer.

The singleton is the *normal* mutual-exclusion mechanism. It is not the only one — see
§6 — because it protects only against a second scheduler on the same host.

## 3. Worker launch authority

Explicit assignment model:

- Stage 2 selects; the architect advises; deterministic Python admits; the scheduler
  launches one exact task.
- The worker receives the task ID it must do. It does not re-select, and the scheduler does
  not hand it a generic "go find work" entry point.
- The worker still performs its own claim/lease/Issue lifecycle inside its own checkout.
  The scheduler deliberately does not pre-acquire that authority, so a launch failure
  leaves no orphaned lease.
- V1 defaults `max_workers` to 1. Raising it above 1 requires the Software Architect
  acceptance proof. Capacity counts scheduler-owned live child processes only. Durable external or
  manual workflows are integration reservations, not capacity.

## 4. Durable versus ephemeral state

| State | Where it lives | Survives restart |
| --- | --- | --- |
| Task contracts, graph, resource groups | Git (`Tasks/`, `Pipeline/TaskGraph/`) | yes |
| Workflow phase, lease, human handoff | GitHub Issue managed state block + hash-chained events | yes |
| Claim/lease refs | Git refs | yes |
| Branch/checkout work in progress | task checkouts and pushed branches | yes |
| Architect advisory artifacts | `Pipeline/ArchitectureReview/outputs/orchestrator/architect/*.json` | yes (evidence only, `advisory_only_not_applied`) |
| Active assignment map, WAIT cache/cooldown, per-poll and cumulative session invocation budgets | scheduler process memory | **no, by design** |

Nothing in the ephemeral column is authority. Losing it costs at most one recomputation:
reservations are re-observed, WAIT decisions are recomputed, and exclusions are rebuilt
from current state.

## 5. Restart and recovery

On restart the scheduler reconstructs authority from Git, GitHub, and the filesystem. It
never trusts a previous process's memory.

| Failure point | What is durable | Recovery |
| --- | --- | --- |
| Crash while idle or mid-advisory | nothing | restart; re-observe; the advisory artifact, if written, is evidence only |
| Crash after launching a worker | the worker's own Issue lease and checkout | the worker continues independently; see the known gap below |
| Crash before decomposition apply (**planned**) | proposal artifact + durable authorization record | re-observe; a plan that no longer matches current HEAD fails closed as stale and must be re-proposed |
| Crash during D1C materialization (**planned**) | staged files only; no commit | Slice 1 revalidation plus the orphaned-child semantics check reject a half-applied graph; the source checkout must be clean before graph mutation is attempted again |
| Crash after the D1C commit, before the next poll (**planned**) | the commit itself | Git is authority; the commit records the plan hash, so re-apply resolves to `already_applied` and the durable record is updated idempotently |
| Ctrl+C with children running | children and their leases | children are not killed and leases are not released; the operator decides |
| Work parked at `human_action_required` | Issue state | never agent work; the scheduler refuses to route it and treats it as an integration reservation |

**Known gap (current, v1).** A restarted scheduler does not adopt child processes launched
by a previous scheduler. Those workers keep running and keep their own durable authority,
but the new scheduler will not count them in `max_workers` and will not reap them. Two
things bound the damage: a live agent lease is `agent_working`, which is not
`nsc-state:agent-ready`, so Stage-2 resume will not offer that task to a second worker; and
the task's own claim/lease remains held. The residual exposure is capacity accounting and
process supervision, not double assignment. Adoption of orphaned children is deliberately
out of scope until a live proof shows it matters.

**Known safe-but-fragile stop (current, v1).** `run_pipeline_agent.py` has no distinct
worker outcome for an exact-task admission race that declines before mutation; it may exit
2, and every nonzero child exit stops the scheduler. This remains fail-closed and does not
imply data corruption, but acceptance must record it as fragile. A future cross-file change
must add a typed "declined before mutation" result/exit contract. V1 does not string-match
stderr and does not retry it.

## 6. Claims as defense in depth

Git CAS claims and exclusive-resource claims are retained unchanged. Under the single-
architect model they are no longer the mechanism that allocates fresh work; they exist to
fail closed when an assumption breaks:

- a second scheduler started despite the singleton (different host, different checkout);
- a human ran a worker or a decomposition apply by hand;
- a stale process from a previous session is still alive;
- an operator pointed two checkouts at the same task.

Gauntlet Phase B evidence that a real simultaneous fresh-claim race yields at most one
winner, a typed loser, safe replan, no duplicate Issues, and no leaked claims is exactly
what makes it safe to demote this layer to defense in depth rather than delete it.

## 7. Integration reservation lifecycle

A reservation is an observation, never a lock.

```text
created   when a scheduler child is launched (prediction) or when a durable incomplete
          workflow is observed (branch/checkout evidence)
pending   while a newly launched worker prepares its checkout; prediction remains evidence
enriched  each poll, with actual tracked/staged/untracked and committed branch paths
graded    evidence_type + confidence + surface_unknown; actual paths outrank prediction
unknown   when a previously observable checkout becomes missing/unreadable; last actual
          evidence is retained and conservative unknown-surface rules apply
consumed  by deterministic conflict detection and by the architect prompt
released  when the child exits and the workflow reaches COMPLETE, or when the branch is
          merged so it no longer differs from main
```

`surface_unknown` is first-class: a durable workflow whose checkout or branch cannot be
read is recorded as unknown rather than as empty. Treating an unreadable surface as "no
paths" would be the single most dangerous silent failure in the design.

A resume task's own reservation is not a competitor on the reservation side, but its
actual paths and Unity serialized assets are unioned into that candidate's effective
surface before comparison with every other reservation. `.meta` companions normalize to
their asset path for conservative collision checks.

## 8. Authority split

### Deterministic authority (Python + Git + GitHub)

TaskGraph contracts; Stage-2 eligibility and ranking; durable workflow state; claim/lease
state; source HEAD; actual changed paths; `GraphDeltaPlan` hashes; decomposition
validators; D1C preflight, materialization, commit, and post-commit validation; and the
START/WAIT/HUMAN_REVIEW admission decision itself.

### LLM architect: advisory and decision support

Predicted change surface; predicted merge/integration risk with honest confidence;
suggested interfaces and seams; "this task is too broad"; decomposition proposals with
per-child surfaces; suggested dependencies and exclusive resources; architectural
sequencing; and naming a design/canon question.

The architect's `parallel_recommendation` is an input to a deterministic gate, not a
command. A `start` recommendation still loses to any deterministic hard conflict, to low
confidence, to unknown risk, and to an unresolved unknown surface.

### Human authority

Required:

- changing product or canon meaning;
- accepting a decomposition that changes task boundaries;
- adopting suggested TaskGraph dependency or resource changes that validated decomposition
  does not mechanically imply;
- resolving a named design/canon ambiguity;
- merge, closeout, and Unity runtime/visual validation, unchanged.

Not required:

- ordinary scheduling WAIT/START judgments;
- reordering which safe task runs first;
- the architect's advisory text itself.

This boundary is the point of the narrow HUMAN_REVIEW rule. If every uncertain schedule
asked a human, the human would become the scheduler and would stop reading the questions
that actually matter.

## 9. Follow-up seams: poll-scoped observation and workflow enumeration

The current implementation enumerates incomplete managed workflows through the read-only
`issue_workflow_store._snapshot` helper plus `IssueBackend.list_issues()`, because
`IssueWorkflowService` exposes no public "all incomplete managed workflows" API. This is a
deliberate, documented compromise: it reuses the existing Issue body/event parser instead
of writing a second one, and it calls no mutation method.

The refactoring seam is a public read-only enumeration on `IssueWorkflowService` that
returns validated snapshots for all incomplete managed Issues. Until it exists, the
fail-closed behavior must be preserved: an invalid, unmanaged, or unparsable durable
observation stops admission rather than being skipped.

The scheduler's poll-scoped Stage-2 composition also uses Stage 2's existing private
plan-scoped Issue/task-state caches because the public resume `DispatchPlan` intentionally
does not include the ranked fresh pool. Eligibility and ranking still come from
`dispatch_plan.plan_dispatch`; there is no second ranking algorithm. A future public
read-only Stage-2 snapshot API should return resume and ranked fresh data together.

V1 still performs a separate durable integration-reservation observation after the
Stage-2 Issue snapshot. This means two bounded Issue reads per poll, not one shared read.
Unifying them is a follow-up; it must preserve invalid-state fail-closed semantics and must
not create a large mutable workflow API.
