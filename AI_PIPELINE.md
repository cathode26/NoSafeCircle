# No Safe Circle AI Pipeline

If you are an AI assistant or developer continuing work on the autonomous game-development pipeline, start here:

`Docs/AI-Pipeline/START_HERE.md`

**Mandatory for any ChatGPT instance that will pick, claim, start, orchestrate, release, or close real work while multiple orchestrator windows may be active:** read these before selecting work:

`Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md`

`Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`

`Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md`

The canonical Windows convention is: shared operator checkout `C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle`; claimed task checkout `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>`, preserving the exact hyphenated ID (for example `C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021`).

For generic requests such as **"Go pick a task and start on it"**, also follow:

`Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`

Then read the detailed GitHub Issue coordination guide:

`Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`

**If the human asks to sync, reconcile, or update GitHub Issues from current TaskGraph states**, read and follow this before modifying any Issue:

`Docs/AI-Pipeline/TASKGRAPH_GITHUB_ISSUE_STATE_SYNC.md`

A short request such as **"Sync TaskGraph states to the GitHub Issues"** is sufficient. The sync is one-way: current committed TaskGraph state is authoritative and GitHub only mirrors it. Existing matching Issues must be checked whether open or closed, and a current `needs_testing` state must replace an older `conformant` mirror even on an Issue whose historical implementation orchestration is already closed. Pure state sync does not reopen/close or assign/unassign Issues.

A generic task-picking instruction may select one of two bounded orchestrator work types:

- **fresh implementation work** against a suitable `not_delivered` concrete executable contract;
- **decomposition work** against an eligible decomposition-relevant parent using the existing read-only Progressive Decomposer.

Decomposition is an orchestrator work type, not a new TaskGraph `kind`, and its D1B.1 outputs remain `review_only_not_applied`.

Do not select a task from TaskGraph IDs by inspection alone. Start fresh-implementation candidate discovery with the evidence-derived bulk state command:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

Also inspect active contracts for decomposition-relevant work:

```powershell
python Pipeline/TaskGraph/taskcontrol.py list --disposition active
```

Use `taskcontrol.py show <TASK-ID>` to inspect each plausible candidate's actual scope, dependencies, gates, execution/decomposition state, and exclusive resources. `not_delivered` is only a candidate-discovery signal; it does not establish dependency readiness or execution authorization.

After narrowing the TaskGraph candidates, search GitHub Issues for the exact NSC IDs, skip assigned or closed tickets, inspect exclusive-resource conflicts, claim the chosen Issue before starting the appropriate pipeline, enter the canonical task checkout path, and publish the required planned-approach and closeout reports. GitHub is the shared operational dashboard; TaskGraph and committed evidence remain authoritative.

For a **generic** task-picking request, do not stop because the first candidate is assigned, closed, resource-conflicted, rejected by deterministic preflight, or genuinely blocked outside its bounded authority. Record/release the unsuitable candidate as appropriate, refresh current state, and try the next sensible implementation or decomposition candidate. Continue until viable work is started or the safe candidate pool is exhausted and human intervention is required.

Do not silently substitute another task when the human explicitly named the task to work on.

For full bulk-state semantics, read:

`Pipeline/TaskGraph/TASK_STATES.md`

For decomposition eligibility, checkout isolation, review-only outputs, and production commands, read:

`Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`

`Pipeline/TaskDecomposition/README.md`

For the proven end-to-end workflow for one real gameplay implementation task — isolated clone, contract audit, ExecutionCrew, Unity validation, evidence packaging, TaskGraph conformance, and merge — read:

`Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`

**Windows task-clone correction:** on this development machine, create standalone task clones from the GitHub remote rather than cloning the local `NoSafeCircle` checkout. Read this authoritative addendum before following the runbook's clone command:

`Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md`

Do not rely on a previous chat transcript as the project source of truth. Read the repository state and the routed milestone context first.
