# ADR-039 — AgentRuntime / TaskExecution Separation

## Status

Accepted — 2026-08-23.

## Context

AgentRuntime was intended to be the provider-neutral layer for one bounded AI invocation. Its initial `AgentRequest` accidentally required an `NSC-###` task ID, `TaskContractIdentity`, and a matching `Tasks/<task_id>.yaml` path. Generic workflows such as ArchitectureReview, Reconciliation, architecture synthesis, and GDD audits could not honestly use that contract without pretending to be game-task execution.

This correction is made before broader production adoption so the pipeline does not accumulate workflow-specific AgentRunner entry points or fake task identities. Stage 4B.2 practical Claude repository read/search remains complete and unchanged.

## Decision

AgentRuntime owns generic bounded invocation only. Its immutable `AgentInvocationRequest` contains `schema_version`, `run_id`, `role`, `prompt`, `context_paths`, `allowed_capabilities`, `write_boundaries`, `output_schema`, `model_capability_class`, `budgets`, and `provider_configuration_key`. AgentRuntime owns provider selection, invocation, structured output, normalized failures, usage, logs, and immutable generic artifacts. It has no knowledge of NSC task naming or `Tasks/*.yaml`.

`Pipeline/TaskExecution` owns `TaskContractIdentity` and immutable `TaskExecutionRequest`, composed from `schema_version`, `task_id`, `task_contract_identity`, and an exact `AgentInvocationRequest`. `TaskExecutionRunner` publishes a deterministic immutable task-level request artifact and delegates the exact invocation to `AgentRunner`, which publishes a task-neutral `request.json`.

The dependency direction is:

```text
ExecutionCrew -> TaskExecution -> AgentRuntime -> provider adapter
generic workflow -------------> AgentRuntime -> provider adapter
```

AgentRuntime never imports TaskExecution. ExecutionCrew must use TaskExecution rather than bypass task semantics. Higher-level generic workflows may use AgentRuntime directly. Providers remain interchangeable behind AgentRuntime.

## Consequences

Task identity remains auditable without contaminating generic provider requests. TaskExecution artifacts do not establish delivery, conformance, readiness, authorization, approval, integration, or completion. Historical AgentRuntime artifacts remain unchanged historical truth and are not reinterpreted as the new request type.

ArchitectureReview is not migrated in this slice. No OpenAI/Codex provider, ExecutionCrew orchestration, repository-write support, command execution, provider fallback, TaskGraph authority, Unity execution, GER integration, or Git automation is added. The next useful proof is migrating ArchitectureReview through generic AgentRuntime using Claude.
