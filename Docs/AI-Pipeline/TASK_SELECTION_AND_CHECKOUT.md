# Task Selection and Checkout for Parallel ChatGPT Orchestrators

## Purpose

This is mandatory operating guidance for any ChatGPT instance choosing real No Safe Circle work while multiple orchestrators may be active.

Use TaskGraph to discover plausible work, the committed task contract for scope/resources, GitHub Issues for shared claim state, and the appropriate bounded pipeline for the selected work type.

The canonical Windows task-path rule is:

```text
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
```

A generic instruction such as **"Go pick a task and start on it"** authorizes selection of one bounded work unit. The human does not need to preselect an NSC ID.

## Canonical task directories

Shared operator/main checkout:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

Claimed task checkout:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Examples:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Preserve the hyphenated TaskGraph ID. Do not create `NoSafeCircle-NSC...`, `-DECOMP`, or timestamped checkout-name variants as the normal task path.

## Selectable work types

1. **fresh implementation work** — implement an existing concrete TaskGraph contract that has not yet been delivered;
2. **decomposition work** — run Stage D1B.1 against an existing decomposition-relevant parent and produce review-ready artifacts.

`decomposition` is an orchestrator work type, not a TaskGraph `kind`.

Read the detailed retry/decomposition policy:

```text
Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md
```

## 1. Build the fresh-implementation candidate pool

Run:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

For machine-readable inspection:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered --json
```

`not_delivered` is a candidate-discovery signal only. It does not establish dependency readiness or execution authorization.

`needs_testing` is not fresh implementation work; it means prior completed/evidenced work may need revalidation after later tracked changes.

Full state semantics:

```text
Pipeline/TaskGraph/TASK_STATES.md
```

## 2. Build the decomposition candidate pool

Inspect active contracts:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
```

Inspect plausible parents:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

High-confidence decomposition candidates commonly have:

```text
execution_scope: needs_execution_decomposition
```

Production eligibility is determined by `Pipeline/TaskDecomposition/context_builder.py::validate_task_selection`.

Decomposition remains progressive and just-in-time. Do not decompose the entire backlog speculatively.

## 3. Inspect candidate contracts

For every plausible candidate:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

Confirm relevant properties:

- `contract_disposition`;
- `kind`;
- `execution_scope`;
- `decomposition_state`;
- dependencies;
- acceptance criteria;
- completion gates;
- `exclusive_resources`;
- title/purpose.

The contract, not Issue prose, owns task meaning.

TaskGraph inspection alone does **not** establish dependency readiness, execution authorization, merge authority, or autonomous dispatch authority.

## 4. Check GitHub operational state

Search GitHub Issues for the exact candidate ID.

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create before claiming |
| open + unassigned | available / released |
| open + assigned | claimed; skip |
| closed | orchestration finished; skip |

For a generic request, if the first candidate is assigned or closed, continue to the next sensible candidate.

## 5. Check shared-resource conflicts

Compare the candidate's `exclusive_resources` with current claimed tasks.

Tasks sharing a Unity scene, builder/generator, prefab, project setting, or logical gameplay surface may be unsafe in parallel even when their tickets differ.

A material conflict is a skip reason under a generic task request.

## 6. Claim before execution

Once a work unit is selected:

1. create the GitHub Issue if absent;
2. populate it from the committed TaskGraph contract;
3. assign it to `cathode26`;
4. post **Claim / Planned Approach** with worker ID;
5. record `work_type: implementation` or `work_type: decomposition`;
6. record the intended canonical checkout path;
7. only then create/enter the task checkout and start the selected pipeline.

Detailed Issue rules:

```text
Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md
Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md
```

## 7. Implementation checkout

Implementation work uses the canonical task directory.

When using the Supervisor helper, pass the canonical path explicitly:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Before running it, require that the intended path does not already exist unless its ownership/state has been reconciled.

The checkout must:

- clone from `https://github.com/cathode26/NoSafeCircle.git`;
- use a standalone clone;
- start from current remote `main`;
- enable Git long-path support;
- create the task branch;
- validate TaskGraph;
- remain clean before provider work.

Do not clone the local shared repository and do not use a Git worktree for Docker-backed execution.

Then follow the normal real-task delivery process:

- Contract Locality Auditor;
- ExecutionCrew when appropriate;
- human candidate review;
- Unity/runtime/human validation;
- authoritative clean validation evidence;
- TaskDelivery review/finalize;
- committed evidence;
- TaskGraph-derived conformance;
- human merge authority.

Implementation closeout example:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

## 8. Decomposition checkout/execution

Decomposition uses the **same canonical task directory**, not a `-DECOMP` directory:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

Authoritative D1B.1 output uses the Downloads task root and per-run child directory:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\<RunId>
```

Read:

```text
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
Pipeline/TaskDecomposition/README.md
```

The production CLI is:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <claude|codex>
```

Use the documented Docker-backed flow so source is physically read-only and output is filesystem-disjoint.

D1B.1 outputs are `review_only_not_applied`; generic task selection does not authorize graph-delta application.

`review_ready` means the model result passed the Stage D1A structural/semantic contract and the proposed overlay validator when applicable. It does **not** mean the human should automatically approve or apply the graph delta. Human review must still check execution locality, especially whether any proposed child completion gate depends on future authored content or a downstream task that itself depends on the parent. Treat that as a semantic completion cycle and request correction before graph application even when `proposed_graph_validation.result` is `valid`.

If `review_ready`, post a Decomposition Closeout with worker ID, parent ID/revision/source commit, canonical checkout/output paths, provider/run ID, semantic decision, result identities, proposed-child/blocker summary, explicit review-only status, and required next action.

## 9. Generic retry loop

For a generic request, do not stop after the first unsuitable candidate.

```text
refresh current main + TaskGraph + GitHub claims
        ↓
build implementation + decomposition pools
        ↓
rank sensible available work
        ↓
try best candidate
        ↓
viable?
   yes → claim + enter canonical task checkout + execute
   no  → record skip/release reason
          ↓
        refresh if needed
          ↓
        try next candidate
```

### Skip before claim

Typical skip reasons:

- assigned/closed Issue;
- material exclusive-resource conflict;
- inactive/invalid contract;
- already delivered work when seeking fresh implementation;
- decomposition preflight rejection;
- plainly unavailable prerequisite.

Do not add noisy GitHub comments for candidates merely inspected and skipped before claim.

### Release after claim

Do not task-hop because normal implementation is difficult. Compilation failures, test failures, implementation bugs, and bounded repair stay inside the selected work unit.

Release and retry only for a real hard blocker outside bounded authority/budget, such as:

- `CONTRACT_REVIEW_REQUIRED` for missing design/nonlocal scope;
- unauthorized scope expansion;
- unavoidable resource conflict;
- exhausted decomposition rejection/failure;
- unresolved external prerequisite.

Preserve useful task checkout/output/log artifacts when releasing.

A `review_ready` decomposition is successful decomposition work, not a retry failure.

## 10. Existing checkout rule

Never overwrite, delete, reset, or casually reuse an existing canonical task directory:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Inspect it and reconcile its ownership/state. Do not create a differently named duplicate checkout as the normal collision workaround.

## 11. Explicit-task exception

Automatic substitution applies only to generic requests.

If the human says:

```text
Work on NSC-042.
```

then a blocker must be reported for NSC-042 rather than silently selecting another task unless the human separately authorizes substitution.

## Fresh ChatGPT selection algorithm

```text
read current repo + mandatory orchestration/path docs
        ↓
taskcontrol states --state not_delivered
        +
taskcontrol list --disposition active
        ↓
taskcontrol show <candidate>
        ↓
inspect dependencies/resources/work type
        ↓
search GitHub Issue
        ↓
skip assigned/closed/conflicted candidates and KEEP TRYING
        ↓
claim chosen Issue + planned approach
        ↓
enter C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
        ↓
implementation → normal delivery
OR
decomposition → D1B.1 + Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>
        ↓
closeout/review boundary
```

Do not ask the human to repeat this process when it is already committed in the repository.
