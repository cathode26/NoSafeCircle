# No Safe Circle AI Pipeline

If you are an AI assistant or developer continuing work on the autonomous game-development pipeline, start here:

`Docs/AI-Pipeline/START_HERE.md`

**Mandatory for any ChatGPT instance that will pick, claim, start, orchestrate, release, or close a real task while multiple orchestrator windows may be active:** read these before selecting work:

`Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md`

`Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`

Then read the detailed GitHub Issue coordination guide:

`Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`

Do not select a task from TaskGraph IDs by inspection alone. Start candidate discovery with the evidence-derived bulk state command:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

Use `taskcontrol.py show <TASK-ID>` to inspect each plausible candidate's actual scope, dependencies, gates, and exclusive resources. `not_delivered` is only a candidate-discovery signal; it does not establish dependency readiness or execution authorization.

After narrowing the TaskGraph candidates, search GitHub Issues for the exact NSC IDs, skip assigned or closed tickets, inspect exclusive-resource conflicts, claim the chosen Issue before creating its checkout, and use `Pipeline/Supervisor/task_checkout.py checkout ...` for the isolated Windows clone. Publish the required planned-approach and closeout reports. GitHub is the shared operational dashboard; TaskGraph and committed evidence remain authoritative.

For full bulk-state semantics, read:

`Pipeline/TaskGraph/TASK_STATES.md`

For the proven end-to-end workflow for one real gameplay implementation task — isolated clone, contract audit, ExecutionCrew, Unity validation, evidence packaging, TaskGraph conformance, and merge — read:

`Docs/AI-Pipeline/REAL_TASK_DELIVERY_RUNBOOK.md`

**Windows task-clone correction:** on this development machine, create standalone task clones from the GitHub remote rather than cloning the local `NoSafeCircle` checkout. Read this authoritative addendum before following the runbook's clone command:

`Docs/AI-Pipeline/REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md`

Do not rely on a previous chat transcript as the project source of truth. Read the repository state and the routed milestone context first.