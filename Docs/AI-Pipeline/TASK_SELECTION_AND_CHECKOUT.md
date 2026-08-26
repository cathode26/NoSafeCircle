# Task Selection and Checkout for Parallel ChatGPT Orchestrators

## Purpose

This is mandatory operating guidance for any ChatGPT instance choosing real No Safe Circle work while multiple orchestrators may be active.

Use the repository's deterministic TaskGraph inspection to discover plausible work first, then use the committed task contract for scope/resource details, GitHub Issues for shared claim state, and the appropriate bounded pipeline for the selected work type.

A generic human instruction such as **"Go pick a task and start on it"** authorizes selection of one bounded unit of work under this policy. The human does not need to preselect an NSC ID.

There are two selectable orchestrator work types:

1. **fresh implementation work** — implement an existing concrete TaskGraph contract that has not yet been delivered;
2. **decomposition work** — run the existing Progressive Decomposer against an existing decomposition-relevant parent and produce review-ready decomposition artifacts.

`decomposition` is an orchestrator work type, not a new TaskGraph `kind`. Do not fabricate an NSC contract merely to represent the act of decomposing another task.

Read the detailed retry/decomposition policy:

```text
Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md
```

The intended generic flow is:

```text
refresh current main + TaskGraph
        ↓
build fresh-implementation candidates
        +
build decomposition-work candidates
        ↓
inspect candidate contracts
        ↓
check GitHub Issue claim state
        ↓
check exclusive-resource conflicts
        ↓
choose best viable work unit
        ↓
claim Issue + identify work_type
        ↓
execute implementation OR decomposition pipeline
        ↓
if genuinely blocked/released → refresh and try next candidate
        ↓
normal closeout / human review boundary
```

## 1. Build the fresh-implementation candidate pool

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

Other states such as `conformant`, `needs_replan`, `needs_human`, `needs_testing`, `invalid_evidence`, `ambiguous_evidence`, and `aggregate` should be treated according to their TaskGraph meaning rather than casually selected as fresh implementation work.

In particular, `needs_testing` means the task was previously completed/evidenced but later tracked changes mean current `HEAD` is no longer proven without another testing/revalidation pass. Do **not** select a `needs_testing` task as fresh implementation work unless the human explicitly asks to retest, repair, or revalidate it.

**Dependency invariant:** when that previously completed/evidenced task appears in another task's `depends_on`, `needs_testing` must **never block the downstream task solely because of that state**. It is revalidation debt on the dependency, not revocation of its integrated implementation. Do not generate or enforce a generic guard requiring every dependency to report exactly `conformant`. Inspect separate concrete dependency problems independently. See `Docs/AI-Pipeline/ADR-045_NEEDS_TESTING_NON_BLOCKING_DEPENDENCY.md`.

Full state semantics are documented in:

```text
Pipeline/TaskGraph/TASK_STATES.md
```

## 2. Build the decomposition-work candidate pool

A generic task-picking request may also select **decomposition work** when that is a sensible way to advance the near-term project frontier.

Inspect active contracts:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
```

Look for decomposition-relevant execution/decomposition states, especially:

```text
execution_scope: needs_execution_decomposition
```

and inspect plausible parents with:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

The authoritative eligibility check is the production Progressive Decomposer preflight in:

```text
Pipeline/TaskDecomposition/context_builder.py::validate_task_selection
```

In practical terms, a decomposition candidate must be an active schema-v2 non-root task, must not already be decomposed, must not already be concrete `single_agent` work, and must be meaningfully decomposition-relevant under the current execution/decomposition axes.

`human_integration_required` and `unknown` may also be decomposition-relevant, subject to the production preflight and current contract/canon.

Do **not** decompose the entire backlog merely because tasks can theoretically be split. Decomposition remains progressive and just-in-time. Prefer it when it unlocks important near-frontier work, when an approved task is explicitly too broad for one agent, or when no comparably useful fresh implementation candidate can safely proceed.

The decomposition pipeline may return `already_concrete`, `decomposed`, `needs_artifact`, or `needs_human`. Missing design must not be silently invented.

Read:

```text
Pipeline/TaskDecomposition/README.md
```

D1B.1 outputs are review-only. A generic task-picking instruction authorizes selecting and running an eligible decomposition proposal; it does **not** authorize silently applying `graph_delta.json` or proposed child contracts to the persistent TaskGraph.

## 3. Inspect each candidate's actual contract

For every plausible implementation or decomposition candidate, run:

```powershell
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
```

Confirm the properties relevant to its work type, including:

- `contract_disposition`;
- `kind`;
- `execution_scope`;
- `decomposition_state`;
- dependencies;
- acceptance criteria;
- completion gates;
- `exclusive_resources`;
- title and task purpose.

For fresh implementation, normal candidates are active, `single_agent`, concrete implementation/artifact work. For decomposition, use the production decomposition-selection preflight rather than pretending an aggregate/oversized parent is directly executable.

The contract, not the GitHub Issue prose, is authoritative for what the task means.

### Authority boundary

TaskGraph inspection does **not** establish:

- dependency readiness;
- execution authorization;
- merge authority;
- autonomous dispatch authority.

Dependency readiness remains intentionally unimplemented. A human/orchestrator must still inspect dependencies and use judgment rather than claiming the state/list command made a candidate ready. That judgment must preserve ADR-045: `needs_testing` on an already-delivered dependency is non-blocking by itself and must not be converted into a synthetic `state == conformant` readiness rule.

## 4. Check GitHub operational claim state

Search GitHub Issues for the exact candidate NSC ID before choosing it.

Current MVP convention:

| GitHub state | Operational meaning |
| --- | --- |
| no Issue | available; create the ticket before claiming |
| open + unassigned | available / released |
| open + assigned | claimed / being worked; do not pick |
| closed | orchestration finished; do not pick |

For the current MVP, assignment is the claim marker. Simultaneous duplicate claims are not atomically prevented; the human will correct them if they occur.

If the Issue is assigned or closed, **skip that candidate and continue to the next sensible candidate** when the human gave a generic task-picking request. Do not stop the entire attempt just because the first choice is unavailable.

## 5. Check shared-resource conflicts

An unassigned Issue does not guarantee that the work is sensible to run in parallel.

Compare the candidate's `exclusive_resources` with currently claimed tasks. If two tasks both own the same Unity scene, builder/generator, prefab, project setting, or logical gameplay surface, surface that conflict before starting parallel work.

Do not hide a likely merge/integration conflict merely because the tickets have different task IDs.

For a generic selection request, a material conflict that makes the candidate unsafe to start is a **skip reason**: record it in working notes and try the next sensible candidate.

## 6. Claim before execution

Once a work unit is selected:

1. create its GitHub Issue if absent;
2. populate the Issue from the committed TaskGraph contract;
3. assign the Issue to `cathode26`;
4. post the required **Claim / Planned Approach** comment, including the ChatGPT worker ID;
5. explicitly identify either `work_type: implementation` or `work_type: decomposition`;
6. only then start the selected pipeline.

The detailed Issue and claim format is documented in:

```text
Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md
Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md
```

## 7. Fresh implementation checkout

For `work_type: implementation`, create the isolated checkout with:

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

Then continue through the normal real-task delivery process:

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

## 8. Decomposition execution and closeout

For `work_type: decomposition`, use the existing Stage D1B.1 read-only flow documented in:

```text
Pipeline/TaskDecomposition/README.md
```

The production CLI is:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id <TASK-ID> --provider <claude|codex>
```

Use the documented Docker-backed authenticated command when running production decomposition so the source is physically read-only and outputs remain outside the checkout.

If the run reaches `review_ready`, post a **Decomposition Closeout** to the parent Issue with:

- worker ID;
- parent task ID, revision, and source commit;
- provider and run ID;
- semantic decision;
- decomposition-result and graph-delta artifact identities/paths when present;
- concise proposed-child or blocker summary;
- explicit `review_only_not_applied` statement;
- required human/review/application next action.

A review-ready decomposition is successful completion of the **decomposition work unit**. It does not mean the parent implementation is delivered or conformant. Do not close the parent as delivered merely because decomposition succeeded.

While a review-ready decomposition awaits human review/application, keep the parent operationally reserved or otherwise clearly marked so another orchestrator does not immediately rerun the same parent contract/hash.

## 9. Generic candidate retry loop

When the human gives a generic request such as **"Go pick a task and start on it"**, do not stop after the first unsuitable candidate.

Use this loop:

```text
refresh current main + TaskGraph + GitHub claims
        ↓
build implementation + decomposition candidate pools
        ↓
rank sensible available work
        ↓
try best candidate
        ↓
viable?
   yes → claim and execute correct work_type
   no  → record skip/release reason
          ↓
        refresh if state may have changed
          ↓
        try next candidate
```

Continue until either:

1. one viable work unit is successfully started; or
2. the sensible safe candidate pool is exhausted and concrete blockers requiring human intervention must be reported.

### Skip before claim

Typical skip-and-continue reasons include:

- Issue assigned or closed;
- material exclusive-resource conflict;
- inactive/invalid contract;
- already-delivered work when the intent is fresh implementation;
- candidate does not match the selected work type;
- decomposition-selection preflight rejects the parent;
- current repository evidence makes the candidate plainly unsuitable.

A dependency's `needs_testing` state is **not** a skip reason by itself. Do not cascade that revalidation debt into downstream blockage.

Do not create noisy Issue comments for candidates merely inspected and skipped before claim.

### Release after claim

Do **not** task-hop because implementation is simply difficult. Compilation errors, failing tests, implementation defects, and ordinary bounded repair belong to the normal selected-task execution/GER/validation loop.

Release and retry another candidate only for a genuine hard blocker outside the selected work unit's bounded authority or repair budget, such as:

- `CONTRACT_REVIEW_REQUIRED` because of missing design, undeclared required integration, or materially nonlocal scope;
- required unauthorized scope expansion;
- unavoidable resource conflict discovered after claim;
- deterministic decomposition preflight proves the parent is not eligible;
- decomposition is blocked/rejected and its bounded retry policy is exhausted;
- an external prerequisite cannot be resolved within the selected work unit.

Follow the release/abandonment procedure, preserve useful artifacts, unassign/release the Issue as appropriate, refresh current state, and try the next candidate.

### Successful decomposition is not a retry failure

If D1B.1 reaches `review_ready`, that decomposition work unit succeeded even when the decision is `needs_artifact` or `needs_human`. Stop at the existing human/review boundary rather than immediately selecting another candidate as though decomposition failed.

## 10. Explicit-task exception

Automatic substitution applies only to a generic task-picking instruction.

If the human explicitly says:

```text
Work on NSC-042.
```

then a blocker on NSC-042 must be reported for NSC-042. Do not silently switch to another NSC task unless the human separately authorizes substitution.

## Fresh ChatGPT selection algorithm

When the human asks to pick/start/work on an unspecified task, use this order:

```text
read current repo + mandatory orchestration docs
        ↓
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
        +
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
        ↓
build fresh implementation + decomposition candidate pools
        ↓
python Pipeline/TaskGraph/taskcontrol.py show <TASK-ID>
        ↓
inspect dependencies + execution/decomposition state + resources
        ↓
search GitHub Issue for exact NSC ID
        ↓
skip assigned/closed/conflicted candidates and KEEP TRYING
        ↓
choose best viable work unit
        ↓
claim Issue + post planned approach + work_type
        ↓
implementation → task_checkout.py + normal delivery workflow
OR
decomposition → D1B.1 read-only decomposition workflow
        ↓
hard blocker/release under generic request → refresh and KEEP TRYING
        ↓
review-ready decomposition OR viable implementation started → stop at appropriate next human/review boundary
```

Do not ask the human to repeat this process when it is already committed in the repository.
