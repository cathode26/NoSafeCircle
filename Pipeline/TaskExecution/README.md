# TaskExecution

`TaskExecution` owns No Safe Circle task identity while delegating one bounded provider-neutral invocation to `AgentRuntime`. `TaskExecutionRequest` composes an exact `AgentInvocationRequest` with `task_id` and `TaskContractIdentity`; it validates the `NSC-###` form, positive contract revision, lowercase SHA-256, and exact `Tasks/<task_id>.yaml` path.

`TaskExecutionRunner` publishes immutable `task_request.json` audit data under its caller-supplied task-run root before delegating the exact contained invocation to `AgentRunner`. The generic runtime independently publishes task-neutral `request.json`, `provider.log`, and `result.json` under its configured invocation root.

These artifacts bind task identity to an invocation for audit. They do not establish delivery, readiness, conformance, authorization, approval, integration, evidence publication, or completion. ExecutionCrew orchestration, task selection, Unity execution, GER, and Git operations remain outside this layer.
