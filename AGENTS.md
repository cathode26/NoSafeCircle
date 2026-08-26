# Repository Agent Guidance

This file is operating guidance, not GDD canon.

Any agent creating, modifying, reviewing, or running tests must first read `Docs/Engineering/UNITY_TESTING_POLICY.md`.

Any ChatGPT instance that selects, claims, starts, orchestrates, releases, or closes a real task while multiple task-orchestrator windows may be active must first read `Docs/AI-Pipeline/PARALLEL_CHATGPT_TASK_ORCHESTRATOR_RULES.md`, `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`, and `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md`. Start candidate discovery with `python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered`, then inspect plausible candidates with `taskcontrol.py show <TASK-ID>`. `not_delivered` is an evidence-derived candidate signal only; it does not establish dependency readiness or execution authorization. Before selecting work, search GitHub Issues for each candidate NSC ID, skip assigned or closed tickets, inspect exclusive-resource conflicts, claim the chosen Issue before creating the task checkout, and publish the required planned-approach and closeout reports. GitHub Issue state is operational coordination only; TaskGraph and committed evidence remain authoritative.

All claimed NSC work must follow `Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md`. The shared operator checkout is `C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle`; a claimed task checkout is `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>` with the exact hyphenated ID preserved, for example `C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021`. Do not invent `NoSafeCircle-NSC...` task-directory variants.

Any orchestrator that selects or runs `work_type: decomposition` must also read and follow `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`. Decomposition uses the same canonical task checkout path, while its host output root follows the external Downloads hierarchy from `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`: `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>`, with each no-overwrite run stored below it as `<RunId>` (for example `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\20260825-195246`). Do not use a task-sibling `...\<TASK-ID>-Outputs` directory as the normal operator path.

Before producing operational commands or human-facing handoff artifacts, read `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`. Human-facing external files default to the Windows Downloads folder; repository-authoritative, pipeline-owned, and hash-bound files remain at their required locations.

Any work involving Unity build targets, platform-dependent APIs or plugins, WebGL/browser compatibility, deployment, or release packaging must also read `Design/Approved/Platform/Desktop_WebGL_Publishing_Target.md`. Desktop WebGL is a human-approved additional publication target; it does not remove the canonical Windows Standalone requirement.

Task meaning comes from the selected task contract and current approved canon. Deterministic tools, not agent claims, establish test results and clean-tree state.

Do not duplicate the complete testing, handoff, orchestration, or approved-artifact policies here; use the canonical documents above.
