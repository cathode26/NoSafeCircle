# Task Selection and Checkout for Parallel ChatGPT Orchestrators

## Purpose

This is mandatory operating guidance for any ChatGPT instance choosing a real No Safe Circle task while multiple orchestrators may be active.

Use the repository's deterministic TaskGraph state inspection to discover plausible unfinished work first, then use the committed task contract for scope/resource details, GitHub Issues for shared claim state, and `task_checkout.py` for the isolated Windows checkout.

The intended flow is:

```text
TaskGraph bulk state inspection
        ↓
inspect candidate task contracts
        ↓
check GitHub Issue claim state
        ↓
check exclusive-resource conflicts
        ↓
claim Issue
        ↓
create isolated checkout
        ↓
normal ExecutionCrew / Unity / TaskDelivery workflow
        ↓
structured GitHub closeout
```

## 1. Start with evidence-derived TaskGraph states

Do not scan task numbers blindly and do not treat `contract_disposition: active` as meaning unfinished.

Run:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states
```

For normal new implementation work, the most useful first filter is:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

For machine-readable inspection:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered --json
```

`not_delivered` means no usable committed evidence currently proves that task at `HEAD`. It is a candidate-discovery signal, not a readiness or authorization decision.

Other states such as `conformant`, `needs_replan`, `needs_human`, `needs_revalidation`, `invalid_evidence`, `ambiguous_evidence`, and `aggregate` should be treated according to their TaskGraph meaning rather than casually selected as fresh implementation work.

Full state semantics are documented in:

```text
Pipeline/TaskGraph/TASK_STATES.md
```

### Authority boundary

`taskcontrol states` does **not** establish:

- dependency readiness;
- execution authorization;
- merge authority;
- autonomous dispatch authority.

Dependency readiness remains intentionally unimplemented. A human/orchestrator must still inspect the candidate's dependencies and use judgment rather than claiming the bulk-state command made it ready.

## 2. Inspect each candidate's actual contract

For every plausible candidate from the bulk state list, run:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show NSC-044
```

Confirm at minimum:

- `contract_disposition: active`;
- `kind: implementation`;
- `execution_scope: single_agent`;
- `decomposition_state: concrete`;
- dependencies;
- acceptance criteria;
- completion gates;
- `exclusive_resources`;
- title and task purpose.

The contract, not the GitHub Issue prose, is authoritative for what the task means.

## 3. Check GitHub operational claim state

Search GitHub Issues for the exact candidate NSC ID before choosing it.

Current MVP convention:

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create the ticket before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / being worked; do not pick |
| closed | orchestration finished; do not pick |

For the current MVP, assignment is the claim marker. Simultaneous duplicate claims are not atomically prevented; the human will correct them if they occur.

## 4. Check shared-resource conflicts

An unassigned Issue does not guarantee that the task is sensible to run in parallel.

Compare the candidate's `exclusive_resources` with currently claimed tasks. If two tasks both own the same Unity scene, builder/generator, prefab, project setting, or logical gameplay surface, surface that conflict before starting parallel work.

Do not hide a likely merge/integration conflict merely because the tickets have different task IDs.

## 5. Claim before checkout

Once a task is selected:

1. create its GitHub Issue if absent;
2. populate the Issue from the committed TaskGraph contract;
3. assign the Issue to `cathode26`;
4. post the required **Claim / Planned Approach** comment, including the ChatGPT worker ID;
5. only then create the isolated checkout.

The detailed Issue and claim format is documented in:

```text
Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md
Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md
```

## 6. Create the checkout with the Supervisor helper

Use:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1
```

Before running it, check whether the intended checkout already exists. Do not overwrite or reuse an unexplained existing checkout.

The helper follows the authoritative Windows rule:

- clone from `https://github.com/cathode26/NoSafeCircle.git`;
- start from current remote `main`;
- create a standalone isolated clone;
- create the task branch;
- validate TaskGraph;
- do not clone the local repository;
- do not use a Git worktree for Docker-backed execution.

For provider-backed Docker work inside the clone, continue using:

```text
docker compose -p nosafecircle ...
```

## 7. Normal implementation and closeout still apply

The selection/claim/checkout flow does not replace the real task-delivery pipeline.

Continue through the applicable existing process:

- Contract Locality Auditor;
- ExecutionCrew;
- human candidate review;
- Unity/runtime/human validation;
- authoritative clean validation evidence;
- TaskDelivery review/finalize;
- committed evidence;
- TaskGraph-derived conformance;
- human merge authority.

Before closing the GitHub Issue, generate and complete the structured closeout report:

```powershell
python Pipeline/Supervisor/task_checkout.py draft-closeout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC044
```

The closeout must record what changed, how the task was accomplished, material implementation choices, missing/underspecified information, additions beyond the original task, validation, remaining risks/follow-ups, final Git identities, and the actual TaskGraph-derived closeout state.

## Fresh ChatGPT selection algorithm

When the human asks to pick/start/work on another task, use this order:

```text
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
        ↓
choose plausible candidates by title/purpose
        ↓
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
        ↓
inspect dependencies + exclusive resources
        ↓
search GitHub Issue for exact NSC ID
        ↓
skip assigned/closed tickets
        ↓
choose one sensible available task
        ↓
claim Issue + post planned approach
        ↓
python Pipeline/Supervisor/task_checkout.py checkout ...
```

Do not ask the human to repeat this process when it is already committed in the repository.
