# Parallel ChatGPT Task Orchestrator Rules

## Status

This document is **mandatory operating guidance** for any ChatGPT instance that selects, claims, starts, orchestrates, releases, or closes real No Safe Circle work while multiple ChatGPT task-orchestrator windows may be active.

Read it with:

- `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`;
- `Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md`;
- `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`;
- `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`;
- `Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md`;
- `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`;
- `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`;
- `Pipeline/ExecutionCrew/README.md`;
- `Pipeline/TaskDelivery/README.md`;
- `Pipeline/TaskDecomposition/README.md` when decomposition is selected.

## Core rule

**Do not choose or start work from TaskGraph alone.** TaskGraph owns durable work truth; GitHub Issues own shared operational coordination.

A generic human instruction such as **"Go pick a task and start on it"** authorizes one bounded work unit under the committed selection policy. The human does not need to preselect an NSC ID.

## Canonical Windows task path

The shared operator checkout is:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

Every claimed NSC task uses:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Example:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

The hyphenated TaskGraph ID is preserved. Do not invent `NoSafeCircle-NSC...`, `-DECOMP`, or timestamped checkout directory variants as the normal task path. The authoritative rule is `Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md`.

For `work_type: decomposition`, use:

```text
source checkout:
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>

host output root:
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>

actual immutable run:
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>
```

Do not use a task-sibling `...\<TASK-ID>-Outputs` directory as the normal operator output path. Do not pre-create `<RunId>`; the pipeline creates it with no-overwrite semantics.

## Selectable work types

A generic task request may select:

1. **`work_type: implementation`** — fresh implementation of an undelivered concrete executable TaskGraph contract;
2. **`work_type: decomposition`** — read-only decomposition of an existing active decomposition-relevant parent contract, normally through Stage D1B.2 round-robin review/refinement.

`decomposition` is an orchestrator work type, not a TaskGraph `kind` and not a fabricated NSC task.

## Issue-state convention

For the Issue whose title begins with the exact `NSC-###` ID:

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create the ticket before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / being worked or deliberately reserved for review; do not pick |
| closed | orchestration finished; do not pick |

Assignment is the current claim/reservation marker. Simultaneous duplicate claims are not atomically prevented; the human may correct them manually.

## Mandatory pre-selection procedure

Before selecting work, every orchestrator must:

1. identify itself with a worker ID such as `chatgpt-1` through `chatgpt-5`;
2. refresh current `main` and read the mandatory orchestration docs;
3. inspect current TaskGraph rather than relying on conversation memory;
4. build plausible fresh-implementation candidates from evidence-derived current state;
5. also inspect active contracts for decomposition candidates accepted by the production decomposer preflight;
6. search GitHub Issues for every plausible candidate's exact NSC ID;
7. exclude assigned and closed candidates;
8. compare candidate `exclusive_resources` with currently claimed work;
9. never infer dependency readiness merely from contract shape, TaskGraph state, or Issue state.

An unclaimed ticket does **not** imply that two tasks sharing a Unity scene, builder, project setting, or logical gameplay surface are safe in parallel.

For a generic request, an unavailable first candidate is not a reason to stop. Continue to the next sensible candidate.

## Mandatory ticket contents

If a selected task has no Issue, create it before execution. The title must begin with the exact task ID:

```text
NSC-044 — Ruined Entry Spatial Blockout
```

The Issue body should include task purpose, dependencies, acceptance criteria, completion gates, downstream obligations, execution/decomposition state, exclusive resources, canon evidence/references, scope notes, and TaskGraph contract identity.

The Issue is a human-facing operational mirror; the TaskGraph contract remains authoritative.

## Mandatory claim procedure

When an available work unit is chosen:

1. assign the Issue to `cathode26`;
2. post a **Claim / Planned Approach** comment with worker ID;
3. explicitly record `work_type: implementation` or `work_type: decomposition`;
4. record exact base/source `main` commit;
5. record the canonical task checkout;
6. for decomposition, record the Downloads output root and provider order/mode;
7. only after the claim exists, create/enter the canonical task checkout and start the selected pipeline.

### Implementation checkout

Use the Supervisor helper with an explicit canonical path:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Do not rely on an older default/example that produces a `NoSafeCircle-NSC...` directory.

### Decomposition checkout

Decomposition uses the same task directory, for example:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

and the external Downloads output root:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021
```

with each run stored as:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\<RunId>
```

Read `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` and `Pipeline/TaskDecomposition/README.md` before provider-backed decomposition.

## Claim / Planned Approach content

Record information applicable to the work type:

```text
Worker
work_type: implementation | decomposition
Exact base/source main commit
Canonical checkout path
Branch                           # implementation
Mode + provider order + output root  # decomposition
Planned approach
Expected validation/review boundary
Assumptions / risks
```

The planned approach must describe the intended method, not merely restate acceptance criteria.

## Implementation decisions and missing information

During implementation, distinguish between:

1. legitimate implementation choice;
2. missing or underspecified design requiring authority;
3. necessary supporting addition;
4. unauthorized scope expansion.

Do not silently invent canon to finish a ticket.

## Normal implementation delivery workflow

An implementation claim does not bypass the existing delivery process. Continue through the applicable path:

- canonical isolated task checkout;
- Contract Locality Auditor;
- ExecutionCrew when appropriate;
- human candidate review;
- Unity/runtime/human validation;
- authoritative clean validation evidence;
- TaskDelivery review/finalize;
- committed evidence;
- TaskGraph-derived current conformance;
- human merge authority.

## Decomposition remains review-only

For `work_type: decomposition`, follow `Pipeline/TaskDecomposition/README.md` and `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`.

Normal new provider-backed decomposition uses Stage D1B.2:

```text
initial provider authors candidate
        ↓
deterministic D1A validation
        ↓
other provider independently reviews
        ├─ pass -> review_ready
        ├─ revise -> reviewer becomes latest author; rotate
        └─ needs_human -> bounded human-authority stop
```

Mandatory D1B.2 properties:

- the latest candidate author may not approve its own candidate;
- every generated/revised candidate passes deterministic validation before another provider reviews it;
- unresolved blocking findings carry forward with explicit resolution status;
- the loop has a deterministic call limit;
- a final unreviewed revision becomes `needs_human`, never `review_ready`;
- source remains physically read-only;
- output remains external and no-overwrite;
- no graph delta is automatically applied.

D1B.1 remains a compatible one-provider proposal/diagnosis path. Use it only when explicitly requested, for bounded diagnostics, or when a second provider is unavailable and the limitation is disclosed.

A D1B.2 `review_ready` run is successful completion of the decomposition work unit with independent semantic PASS. It remains `review_only_not_applied`.

A D1B.2 `needs_human` run is also a successful bounded diagnosis at the authority boundary. Preserve unresolved findings and request the decision.

Post a **Decomposition Closeout** containing worker ID, parent task/revision/source commit, canonical checkout and Downloads run paths, mode/provider order/run ID, semantic decision/final status, final candidate author/independent approver when present, artifact identities, concise proposal/blocker summary, unresolved findings when present, explicit `review_only_not_applied`, and required human next action.

Do not claim the parent implementation is delivered merely because decomposition succeeded.

## Deterministic setup and provider execution are separate phases

For provider-backed work, split the operator flow:

### Phase 1 — deterministic setup

- inspect exact checkout path;
- verify correct branch/HEAD/clean tree;
- refresh or fast-forward from current `main` when allowed;
- validate TaskGraph;
- validate work-type preflight;
- create/verify the external output parent;
- print exact source/output identity;
- do not invoke a provider.

### Phase 2 — provider run

- reverify exact source identity;
- invoke the documented Docker service;
- preserve live transcript and immutable run artifacts;
- revalidate source after every provider call;
- stop at `review_ready`, `needs_human`, rejection, or failure.

Do not hide provider execution inside a large setup block whose early failure makes it unclear whether a provider was spent.

## Checkout creation rules

Implementation/decomposition task checkouts must:

- be standalone clones from GitHub, not local clones of the shared checkout;
- start from current remote `main`;
- enable `core.longpaths`;
- remain clean before provider work;
- stay on `main` for decomposition source checkouts unless a documented later stage explicitly creates an implementation branch;
- use task-specific implementation branches for implementation work.

Do not use Git worktrees for Docker-backed provider execution unless the repository explicitly approves that workflow.

## Existing checkout collisions

If the canonical task directory already exists:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

stop and inspect it.

Do not:

- delete it automatically;
- reset it automatically;
- overwrite it;
- create a differently named duplicate as the normal workaround.

Reconcile ownership/state first.

## Validation and clean-tree authority

- Deterministic tools, not model claims, establish test results.
- A provider result does not prove the source remained unchanged.
- Revalidate HEAD/tree/status after every provider call.
- Authoritative Unity validation must use the repository clean-test runner when Unity tests apply.
- Review-only pipeline infrastructure work may use pure Python/component smoke tests when no Unity runtime behavior changes.
- Raw hash-bound validation artifacts must not be edited for formatting.

Read:

```text
Docs/Engineering/UNITY_TESTING_POLICY.md
Docs/AI-Pipeline/TASK_ITERATION_AND_CLOSEOUT_PLAYBOOK.md
```

## Mandatory implementation closeout

Generate the closeout draft using the canonical task path:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

The final Issue closeout must explicitly cover:

1. Outcome;
2. What changed;
3. How the task was accomplished;
4. Decisions and choices made;
5. Missing or underspecified items;
6. Additions beyond the original task;
7. Validation performed;
8. Remaining follow-ups / risks;
9. actual TaskGraph closeout state;
10. final branch/commit/merge identity.

If a section has nothing to report, write `None.`.

Close the Issue as completed only after the normal delivery/merge path and closeout report are finished. Issue closure does not create TaskGraph conformance.

## Generic retry behavior

For a generic task request, skip and keep trying before claim when a candidate is assigned, closed, materially resource-conflicted, inactive/invalid, already delivered when seeking fresh implementation, rejected by decomposition preflight, or plainly unsuitable from current repository evidence.

After claim, do not abandon merely because execution is difficult. Compilation errors, test failures, implementation bugs, and ordinary bounded repair belong inside the selected work unit.

Release and retry only for a genuine hard blocker outside bounded authority/budget, such as missing design/nonlocal contract, unauthorized scope expansion, unavoidable resource conflict, exhausted decomposition rejection/failure, or an unresolved external prerequisite.

On release:

1. comment the blocker and useful state;
2. preserve useful task checkout/output/log artifacts;
3. unassign/release the Issue as appropriate;
4. refresh `main`, TaskGraph, and GitHub claims;
5. continue to the next sensible candidate under a generic request.

A D1B.2 `review_ready` or explicit `needs_human` result is not a retry failure; stop at the human review/application boundary.

## Existing task directory rule

Never overwrite, delete, reset, or casually reuse an existing `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>` directory. Inspect it and reconcile ownership/state. Do not create a differently named duplicate checkout as the normal collision workaround.

## Explicit-task exception

Automatic substitution applies only to generic requests. If the human explicitly names a task, report blockers for that task rather than silently switching to another NSC task.

## Forbidden behaviors

- working directly in the shared primary checkout;
- relying on chat titles as claim state;
- starting provider work before GitHub claim;
- using stale local `main` without refresh;
- running duplicate decomposition on the same parent/hash concurrently;
- automatically applying a decomposition graph delta;
- treating D1B.1 structural `review_ready` as independent semantic approval;
- allowing a D1B.2 candidate author to approve its own candidate;
- treating an unreviewed final revision as `review_ready`;
- using task-sibling `-Outputs` as the normal Windows output path;
- inventing alternate task checkout names to bypass collisions;
- task-hopping after ordinary implementation/test failure;
- claiming conformance without committed TaskGraph evidence;
- merging without human merge authority.

## Fresh ChatGPT behavior

For an unspecified task request:

```text
read current repo + mandatory orchestration/path docs
        ↓
inspect TaskGraph state + active decomposition candidates
        ↓
inspect candidate contract/dependencies/resources
        ↓
search GitHub Issues
        ↓
exclude assigned/closed/conflicted candidates
        ↓
choose viable work
        ↓
claim Issue + planned approach + work_type + canonical paths
        ↓
enter C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
        ↓
implementation → normal delivery workflow
OR
decomposition → D1B.2 read-only workflow + Downloads output root
        ↓
closeout/review boundary
```

Do not ask the human to repeat this protocol when it is already committed in the repository.
