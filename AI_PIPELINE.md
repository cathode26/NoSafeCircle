# No Safe Circle AI Pipeline

If you are an AI assistant or developer continuing work on the autonomous game-development pipeline, start here:

`Docs/AI-Pipeline/START_HERE.md`

For the concise architecture that exists **now**, read:

`Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`

For the live routing/status snapshot, read:

`Docs/AI-Pipeline/CURRENT_STATE.md`

Do not rely on an old chat transcript as project authority. Read current repository state first.

## Mandatory task-orchestration reading

Any ChatGPT instance that will pick, claim, start, orchestrate, release, or close real work while multiple orchestrator windows may be active must read:

```text
Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md
Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md
```

For generic requests such as **"Go pick a task and start on it"**, also read:

`Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`

The canonical Windows convention is:

```text
shared operator checkout:
C:\NSC\NSC\NoSafeCircle

claimed task checkout:
C:\NSC\NSC\<TASK-ID>
```

Preserve the exact hyphenated task ID.

## Current selectable work types

A generic task-picking instruction may select one bounded work unit of either type:

- **fresh implementation work** against a suitable `not_delivered`, concrete executable contract;
- **decomposition work** against an eligible decomposition-relevant parent.

Decomposition is an orchestrator work type, not a TaskGraph `kind`.

For fresh implementation candidate discovery:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

For decomposition candidates:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

TaskGraph state inspection is candidate information only. It does not grant dependency readiness, execution authorization, merge authority, or autonomous dispatch.

After narrowing candidates, search GitHub Issues for the exact NSC IDs, skip assigned/closed/conflicted work, claim the selected Issue, and publish the required planned approach before execution.

## Current decomposition mode: D1B.2 round robin

Stage D1B.2 is implemented and merged. It is now the normal mode for new production decomposition work.

Default circuit:

```text
Codex authors candidate
        ↓
deterministic D1A validation
        ↓
Claude independently reviews
        ├─ PASS → review_ready
        ├─ NEEDS_HUMAN → needs_human
        └─ REVISE → Claude becomes latest candidate author
                         ↓
                  deterministic validation
                         ↓
                  Codex independently reviews
                         └─ continue within circuit breaker
```

The latest candidate author may never approve its own candidate.

The normal CLI is:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

Default provider order is `codex,claude`; default maximum calls is 4.

Canonical Docker-backed production invocation:

```bash
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py --task-id <TASK-ID>
```

The canonical Windows host output root is:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>
```

Each run creates its own `<RunId>` child directory. Do not pre-create that child directory.

D1B.2 output remains:

```text
review_only_not_applied
```

`review_ready` means deterministic validation plus independent semantic PASS. It does **not** authorize graph application.

`needs_human` is also a bounded useful decomposition outcome when the review circuit reaches an authority/circuit-breaker boundary.

Read the complete decomposition contract/usage documentation here:

```text
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
Pipeline/TaskDecomposition/README.md
Docs/AI-Pipeline/ADR-035_ROUND_ROBIN_DECOMPOSITION_REVIEW.md
Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md
```

## Compatible D1B.1 mode

The one-provider path remains available when specifically needed for diagnostics, comparison, or compatibility:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <codex|claude>
```

It should no longer be treated as the normal new-production decomposition path because it lacks independent semantic cross-review.

## Decomposed parents are aggregate features

A successful new decomposition proposal transitions the selected parent into a non-executable aggregate feature. All real implementation work lives in explicit descendants.

If components require a later assembly/sewing pass, that pass must itself be an explicit child task. No hidden "finish the parent" implementation pass exists.

Ordinary downstream dependency edges must be rewritten from the decomposed aggregate to the concrete child capability they actually consume.

See:

`Docs/AI-Pipeline/ADR-034_DECOMPOSED_AGGREGATE_FEATURES.md`

## GDDRAG and decomposition

`Pipeline/GDDRAG` exists as a deterministic, hash-verified production search index over the current canonical GDD.

It is **not currently connected to D1B.2**.

Current decomposition context still includes the full committed GDD. We are deliberately testing live D1B.2 quality, latency, context pressure, and token behavior before adding retrieval complexity.

Possible future direction, only if measurements justify it:

```text
parent/candidate/rewrites/findings
        ↓
deterministic review queries
        ↓
validated GDDRAG retrieval
        ↓
deduplicated + capped current-canon chunks
        ↓
reviewer navigation hints
        + existing authoritative context
```

GDDRAG would remain a navigation aid rather than authority. A missing top-k result could never prove that a canon requirement does not exist.

The current and possible-future designs are documented in:

`Docs/AI-Pipeline/CURRENT_PIPELINE_DESIGN.md`

## Implementation delivery path

For one real gameplay implementation task, follow:

```text
Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md
Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md
Pipeline/ExecutionCrew/README.md
Pipeline/TaskDelivery/README.md
```

The normal path remains:

```text
isolated task checkout
        ↓
Contract Locality Auditor
        ↓
ExecutionCrew
        ↓
Unity/runtime/human validation
        ↓
TaskDelivery review
        ↓
committed evidence
        ↓
TaskGraph-derived conformance
        ↓
human merge authority
```

## GitHub TaskGraph state sync

If the human asks to sync/reconcile GitHub Issues from TaskGraph state, follow:

`Docs/AI-Pipeline/TASKGRAPH_GITHUB_ISSUE_STATE_SYNC.md`

TaskGraph is authoritative. GitHub only mirrors operational state. A pure sync does not itself reopen/close or assign/unassign Issues.

## Current intentional gaps

The following are not yet production authority:

```text
D1C reusable reviewed graph application
Artifact Authority / production artifact-generation GER
Dependency readiness policy
Autonomous dispatch
Automatic merge authority
GDDRAG-assisted D1B.2 review
```

## Development rule

Advance the pipeline by using it on the actual game:

```text
real near-frontier work
        ↓
use current infrastructure
        ↓
measure the failure/cost/ambiguity
        ↓
add only the next bounded infrastructure slice justified by evidence
```

Do not add later autonomous layers or RAG complexity merely because they are architecturally possible.
