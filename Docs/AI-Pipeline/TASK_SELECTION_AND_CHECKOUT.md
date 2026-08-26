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
2. **decomposition work** — run the bounded decomposition pipeline against an existing decomposition-relevant parent and produce review-ready or explicit needs-human artifacts.

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

Authoritative decomposition output uses the Downloads task root and per-run child directory:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\<RunId>
```

Read:

```text
Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md
Pipeline/TaskDecomposition/README.md
Docs/AI-Pipeline/ADR-035_ROUND_ROBIN_DECOMPOSITION_REVIEW.md
```

For normal new provider-backed decomposition, use Stage D1B.2:

```bash
python3 Pipeline/TaskDecomposition/run_round_robin_decomposition.py \
  --task-id <TASK-ID> \
  --providers codex,claude \
  --max-calls 4
```

Use the documented `round-robin-decompose` Docker service so source is physically read-only, output is filesystem-disjoint, and both provider configuration volumes are available.

D1B.2 alternates candidate authorship and independent semantic review. Every generated/revised candidate passes deterministic D1A validation before another provider reviews it. The latest candidate author may never approve its own candidate. The run stops on:

- independent `pass` -> `review_ready`;
- explicit `needs_human` authority boundary;
- deterministic rejection;
- provider failure;
- bounded call limit.

If the call limit ends immediately after a revision, the result is `needs_human`; an unreviewed final revision cannot become `review_ready`.

D1B.1 remains the compatible one-provider proposal/diagnosis command:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <claude|codex>
```

Use D1B.1 only when the human explicitly requests a one-provider run, for bounded diagnostics, or when the second provider is unavailable and that limitation is disclosed.

All decomposition outputs are `review_only_not_applied`; generic task selection does not authorize graph-delta application.

D1B.2 `review_ready` means:

- the candidate passed deterministic schema/policy/graph validation;
- a provider other than its latest author independently passed it;
- no blocking semantic finding remains unresolved.

It still does **not** mean the human should automatically approve or apply the graph delta. Human review/application authority remains separate.

A D1B.2 `needs_human` result is a successful bounded diagnosis, not a provider failure. Preserve the unresolved findings and ask for the required authority decision.

If `review_ready` or `needs_human`, post a Decomposition Closeout with worker ID, parent ID/revision/source commit, canonical checkout/output paths, mode/provider order/run ID, semantic decision, final candidate/approver identities when present, proposed-child or blocker summary, unresolved findings when present, explicit review-only status, and required next action.

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

A `review_ready` decomposition is successful decomposition work. A D1B.2 `needs_human` result is also successful bounded decomposition work at the human-authority boundary. Neither authorizes graph application.

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
decomposition → D1B.2 + Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>
        ↓
closeout/review/application boundary
```

Do not ask the human to repeat this process when it is already committed in the repository.
