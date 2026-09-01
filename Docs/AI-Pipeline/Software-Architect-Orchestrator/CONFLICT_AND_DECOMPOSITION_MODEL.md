# Conflict and Decomposition Model

Design guidance. Not game-design canon and not evidence of repository state. Status
language follows [`README.md`](./README.md).

## 1. Change-surface model

A candidate and every in-flight piece of work are compared as change surfaces:

```text
exact_paths              repository-relative files the work will likely modify
path_patterns            advisory globs; never used as deterministic proof
unity_serialized_assets  .unity, .prefab, .asset, .inputactions (+ .meta implications)
symbols_or_components    classes, MonoBehaviours, methods
shared_systems           named managers, registries, signal families, catalogs
exclusive_resources      committed TaskGraph resource tokens
```

## 2. Evidence hierarchy

Actual beats predicted. Committed beats inferred. Observed beats assumed.

```text
1. committed exclusive_resources on the task contract        (deterministic)
2. actual changed paths in a checkout or on a branch          (deterministic)
3. actual Unity serialized assets among those paths           (deterministic)
4. architect-predicted exact paths vs another task's actual   (deterministic comparison
                                                               of a predicted input)
5. architect-predicted vs architect-predicted                 (weakest; only blocks when
                                                               one side is actively running)
6. path patterns, shared systems, narrative reasoning         (advisory only)
```

Levels 1-4 are enforced by `detect_deterministic_conflict` without asking a model. The
model's contribution is producing level 4's prediction and explaining levels 5-6. It never
overrides levels 1-3: an architect that says `start` while committed resources overlap is
still blocked.

A task never conflicts with its own durable reservation. The unfinished work Stage 2 wants
to resume is the same work, not a competitor; only a *locally active* assignment for the
same task blocks (that would be a double launch).

That self-skip applies only on the reservation/competitor side. Before comparison, the
scheduler unions the resume task's own observed `actual_paths` and observed Unity
serialized assets into its effective candidate surface. Actual branch evidence therefore
dominates an architect prediction that names only unrelated remaining work. The effective
surface is then compared against every *other* reservation. Asset paths and their `.meta`
companions share one conservative collision identity.

## 3. Uncertainty ⇒ WAIT

The scheduler optimizes for clean parallelism, not worker utilization. All of the following
are WAIT:

- `integration_risk` is `medium`, `high`, or `unknown`;
- architect confidence is below the configured minimum;
- the architect cannot establish enough repository evidence to call the candidate low risk;
- the architect invocation fails or returns unusable output, including an advisory whose
  identity does not match the candidate;
- an in-flight integration surface is unknown and parallel safety cannot be established;
- predicted path or system overlap is ambiguous and cannot be confidently ruled safe;
- the architect asks for human review without naming a design/canon question;
- any other uncertainty specifically about parallel merge/integration safety.

A WAIT:

- is not an error and is not a failure exit;
- mutates no TaskGraph, GDD, Issue, claim, or lease state;
- excludes that candidate for the current scheduling pass only;
- lets deterministic Stage 2 offer the next ranked candidate;
- is reconsidered when source or in-flight state changes.

A START requires all of: Stage 2 says runnable; no deterministic hard conflict; no
unresolved unknown surface; `parallel_recommendation == start`; risk `none` or `low`;
confidence at or above the threshold.

### Not a global deadlock

The decision is made per candidate/reservation **pair**, not globally. One partially
observable human-held branch does not make all repository work impossible:

```text
for each reservation R with surface_unknown:
    if R is the candidate itself                        -> ignore
    if candidate and R both declare committed exclusive
       resources AND those declarations are disjoint    -> the architect may justify
                                                            disjointness; ask it
    otherwise                                            -> WAIT this pair
```

A pair reaching the second branch still waits unless the architect positively names that
reservation in `unknown_surface_disjointness` with a justification, and does not also list
it as conflicting. Silence means wait. Self-contradiction means wait. The conservative rule
is preserved; the deadlock is not.

### Never a blacklist

WAIT/HUMAN_REVIEW decisions may be cached to avoid paying for an identical model call
every poll. The cache key binds:

```text
task_id + task_contract_sha256 + source_head + stable in-flight identity fingerprint
```

The stable integration fingerprint includes reservation membership, task ID, committed
exclusive resources, local-active/unknown flags, workflow state/phase, branch/head
identity, and launch-time predictions. It deliberately excludes the ever-growing exact
`actual_paths` inventory as a cache-churn trigger. Current actual paths are still re-read
and deterministically compared on every poll *before* cached or cooldown advice can affect
admission. A newly observed hard overlap therefore blocks immediately.

START is never cached, because launching is a mutation and must be re-decided against
current state. Failed architect invocations are never cached. WAIT/HUMAN_REVIEW also set a
per-task cooldown keyed by task + contract + source HEAD; v1 defaults to 300 seconds before
repurchasing analysis after other stable inputs change. The cache and cooldown are bounded
to scheduler-process lifetime.

A per-poll architect invocation budget (default 3) bounds paid model calls when many
candidates wait in one pass. A cumulative per-session cap (default 12) is a second hard
bound. Exhausting the per-poll cap ends that poll; exhausting the session cap stops new
admissions with `scheduler_blocked` and a non-success result. The operator must explicitly
start another supervised session if more spend is authorized.

## 4. HUMAN_REVIEW is narrow

Only a named design/canon escalation reaches a human:

| Category | Meaning |
| --- | --- |
| `design_or_canon_ambiguity` | requirements admit multiple incompatible architectures and choosing one changes intended design/canon |
| `task_scope_or_contract_change` | the work needs a scope, requirement, or dependency change that is not already authorized |
| `decomposition_required` | the task should be decomposed or contractually changed before implementation, and that cannot remain advisory |

The category must come with the specific question a human must answer. A category without
a question is unusable output and waits. `parallel_recommendation: human_review` without a
category also waits, with an explicit reason saying that merge and integration uncertainty
is a wait, not a human question. Because merge uncertainty has no category to name, the
architect cannot route it to a human even by trying.

## 5. Unity hot spots

Weighted highest when predicting risk and when choosing decomposition boundaries:

- scenes (`.unity`) and prefabs (`.prefab`) — non-merge-safe YAML with GUID references;
- ScriptableObject assets (`.asset`) and their `.meta` identity;
- `ProjectSettings/`, `Packages/manifest.json`, `Packages/packages-lock.json`;
- Input Actions assets;
- central managers, registries, signal contract files, and content catalogs;
- shared builder/editor scripts that regenerate scenes or prefabs;
- assembly definition files that change dependency direction.

Two tasks that only add separate C# components are usually safely parallel. Two tasks that
both touch one scene, one prefab, or one manager are usually not, regardless of how small
each change looks.

## 6. Decomposition decision policy

The architect proposes decomposition when a candidate is not safely completable as one
assignment. Concrete triggers:

- the predicted change surface spans several unrelated systems or several Unity hot spots;
- acceptance criteria describe work that cannot be validated as one coherent deliverable;
- the task would necessarily serialize behind itself (a single worker touching a surface
  that blocks everything else for a long time);
- the task mixes authored-content work with runtime-behavior work whose proofs differ.

It does **not** propose decomposition merely to create parallelism, and it never sacrifices
canonical requirement coverage to get smaller children.

## 7. Decomposing for parallel-safe boundaries

Requirement coverage decides *whether* a decomposition is valid. Engineering boundaries
decide whether it is *useful*. A decomposition whose three children all edit one manager
and one prefab is canonically complete and operationally worthless.

The proposal must therefore carry, as advisory evidence:

- predicted change surface per child;
- likely Unity serialized assets per child;
- shared systems and interfaces per child;
- an inter-child overlap matrix (which pairs collide, on what);
- suggested interfaces or seams that would remove a collision;
- the final integration seam or task, when one is unavoidable;
- an explicit flag when children should still be **serialized** despite being separate
  TaskGraph nodes.
- the number of child pairs whose predicted change surfaces overlap;
- the count of children predicted to touch each Unity serialized asset.

Deterministic requirement coverage and graph semantics remain authoritative. None of the
above can make an invalid decomposition acceptable; it only tells a human and the scheduler
whether a valid one is worth applying.

The overlap pair/asset counts are cheap advisory decomposition-quality counters. They are
HUMAN_REVIEW evidence only: they do not weaken exact requirement coverage, replace the
inter-child explanation, or become graph-validity gates.

Child completion gates must remain locally provable. When a child's real proof depends on
downstream authored content, that proof becomes a downstream integration obligation, per
`Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`. A decomposition that creates a
semantic completion cycle is rejected even if the proposed graph is structurally acyclic.

## 8. Proposal must not be self-authorizing

The architect may propose a decomposition. It must not be the sole reviewer and sole
authority for its own graph rewrite.

**Planned flow:**

```text
architect proposes (D1B.1 / D1B.2 machinery, unchanged)
        |
        v
deterministic validation  (D1A contracts/policy, graph_delta, decomposition graph
                           semantics, exact requirement coverage)
        |
        v
independent challenge     (a reviewer model that is not the proposing architect run,
                           and/or explicit human authorization by risk policy)
        |
        v
human authorization binds the EXACT reviewed plan hash
        |
        v
D1C applies that exact authorized GraphDeltaPlan, or fails closed
```

No class of decomposition is currently exempt from independent review. If a future
mechanically-provable low-risk class is proposed — for example, a delta that only splits
one parent into children with byte-identical aggregated requirement coverage, no dependency
edits, no resource edits, and no contract rewrites of existing tasks — it must be defined
by a deterministic predicate and justified separately. Proposer and reviewer authority must
not collapse silently.

## 9. Affected contracts and the graph-mutation critical section

Applying a delta rewrites existing contracts (at minimum the parent, plus any dependent
whose edges are rewritten). Before mutating (**planned**):

```text
1. the architect enters its graph-mutation critical section
2. it launches no new workers for the duration
3. it re-observes current HEAD, durable workflow state, and integration reservations
4. it computes the exact affected-contract set from the GraphDeltaPlan
5. for each affected contract:
       actively owned by a live worker            -> WAIT
       durable workflow incomplete/unmerged work  -> WAIT
       surface unknown                            -> WAIT
6. it requires a clean source checkout
7. it revalidates the authorized plan against current HEAD
       stale -> fail closed; do not silently reallocate IDs
8. it applies with the deterministic D1C primitive and re-observes the result
```

An open managed Issue whose contract is rewritten by the exact authorized/applied D1C
plan is included in this affected-contract WAIT/reconciliation scope even when it still
records the pre-delta `task_contract_sha256`. A4 must distinguish that expected transition
from an unexplained Issue/HEAD contract mismatch. It must not hard-stop immediately after
a valid D1C commit solely because the Issue has not yet reconciled its old hash; unknown or
unbound mismatches still fail closed.

WAIT here is the same cheap verdict as everywhere else: no state changes, and the
decomposition is retried when the affected work is inactive or integrated.

The single-scheduler singleton plus this critical section is the normal serialization. A
cheap global logical resource token on the existing single-task claim path is retained as
defense in depth against a manual or second-host apply. Atomic multi-task claims across
every affected contract are **not** adopted: with one scheduler, the architect already
knows the affected set and stops admitting work, and the residual race — a human manually
starting work on an affected contract inside the window between re-observation and commit —
degrades to a detected fail-closed replan, because durable workflow state carries
`task_contract_sha256` and a changed contract is already rejected as stale. If the project
ever runs more than one scheduler or routinely allows concurrent manual starts, that
decision must be revisited before live use.

## 10. Stale plans

A reviewed plan is bound to the HEAD and contract hashes it was computed against. If HEAD
moved in a way that changes the delta — new task IDs allocated, parent contract rewritten,
dependent edges changed — the plan is stale. Stale plans fail closed and are re-proposed.
They are never "fixed up" by reallocating IDs at apply time, because the human authorized a
specific graph, not an intent.

## 11. Where decomposition output lives

Unchanged from existing policy: authoritative decomposition run output stays filesystem-
disjoint from the source checkout, under the documented Downloads run layout, and remains
`review_only_not_applied` until an authorized D1C application commits it.
