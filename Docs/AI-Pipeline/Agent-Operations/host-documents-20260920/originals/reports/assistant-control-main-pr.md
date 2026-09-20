The current game repository lacks the direct AssistantControl orchestration proven in the Gauntlet branch. This integrates the final pipeline, viewer, worker, decomposition, candidate, reset, and publication controls as one commit on the current NoSafeCircle main.

The integration preserves the real game boundary: there are no changes under `Tasks`, `Assets`, `Packages`, or `ProjectSettings`. It includes Windows Job Object cancellation for task workers, exact receipt/process identity binding, injective decomposition-obligation validation, execution-stage viewer details, a safe task-reset adapter, and exact-head Windows CI.

The experimental detached background execution of decomposition and post-crew validation is deliberately excluded. Astra's adversarial review found that a forced stop could leave a provider container running and that abrupt controller loss lacked orphan cleanup. The proven synchronous controller remains in this PR; the throughput work stays isolated until those two issues are fixed and tested.

Validation:

- `Pipeline/TaskGraph/taskcontrol.py validate` passes with all 60 active game tasks, 59 parent edges, and 106 dependency edges.
- `python -m compileall` passes for AssistantControl, TaskDecomposition, ExecutionCrew, and TaskReviewAgent.
- All 178 top-level AssistantControl and TaskReviewAgent modules import successfully.
- The focused graph-controller suite passes 28/28; focused decomposition, CLI-worker, and post-crew suites pass 16/16.
- The exact synchronized-candidate Windows regression passes.
- `git diff --check` passes.
- The branch is exactly one commit ahead of `main`.

Claude's separate `plan()` optimization is intentionally excluded pending a disposable Gauntlet timing test.
