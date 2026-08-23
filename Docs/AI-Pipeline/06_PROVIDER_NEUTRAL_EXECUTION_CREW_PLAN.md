# Provider-Neutral Execution Crew Plan

## Purpose

This document plans how the useful generic architecture demonstrated by the Assignment 3 AgentCrew can be extracted into the production `Pipeline/` without tying production execution to one model vendor.

`AgentCrew/` remains preserved as historical Assignment 3 evidence. It is not the production runtime and will not be rewritten in place. Production work will extract its general orchestration lessons into new, provider-neutral components under `Pipeline/` after the current Phase 3 evidence work is complete.

This is a planning document, not architecture approval or runtime implementation.

## Existing reusable strengths

Assignment 3 demonstrated several ideas worth retaining:

- independent, fresh agent invocations instead of one long shared model session;
- explicit artifact handoffs between roles;
- structured output schemas for planning and validation results;
- role-specific tool restrictions, including read-only planning/validation and bounded write access for implementation;
- separation between implementation and validation;
- a bounded repair pass when validation reports concrete blockers;
- explicit human Unity compilation, test, play-mode, and visual validation after static agent review.

The historical implementation also has limits that production extraction must correct:

- the Claude CLI and its command-line permission vocabulary are embedded directly in the runner;
- one global model is used for every role;
- the implementation agent also authors the tests that judge its work;
- validation is static and currently lacks a blocking test-isolation policy;
- latest-output files are overwritten instead of being stored in immutable task/run directories;
- the packager role exists for homework submission and is not part of normal game delivery.

The extraction should preserve the strengths without treating the historical implementation or its output claims as current production authority.

## Provider-neutral rule

The following rule is non-negotiable:

> No task contract, role prompt, output schema, evidence record, or deterministic validation gate may depend on a specific LLM provider.

Provider-specific behavior belongs only behind provider adapters. Provider names, model identifiers, CLI flags, tool names, session identifiers, and API response shapes must not leak into task meaning or correctness policy.

## Proposed production structure

The target layout is:

```text
Pipeline/
  AgentRuntime/
    agent_runner.py
    contracts.py
    providers/
      base.py
      claude_code.py
      openai_codex.py
    config/
  TaskExecution/
    contracts.py
    task_runner.py
  ExecutionCrew/
    crew.py
    roles/
      implementer.md
      unity_test_author.md
      validator.md
    schemas/
  Testing/
    run_unity_tests_clean.ps1

Docs/Engineering/
  UNITY_TESTING_POLICY.md
```

This is a target layout. This documentation task creates none of those runtime, provider, role, schema, test-runner, or policy files.

The intended separation is:

- `AgentRuntime/` owns provider-neutral invocation contracts, budgets, adapter selection, and normalized results;
- `TaskExecution/` owns NSC task identity and delegates its contained generic invocation to `AgentRuntime`;
- `ExecutionCrew/` owns the bounded role sequence and role-specific schemas;
- `Testing/` owns deterministic test execution rather than delegating test truth to an agent;
- `Docs/Engineering/UNITY_TESTING_POLICY.md` will define the canonical isolation and evidence policy used by people, agents, and deterministic gates.

## Provider-neutral contracts

### Generic `AgentInvocationRequest`

Every provider consumes the same conceptual request. Its fields should cover:

- `run_id`: immutable execution-run identity;
- `role`: provider-neutral production role;
- `prompt`: role instructions and bounded task instructions;
- `context_paths`: explicit repository inputs available to the role;
- `allowed_capabilities`: semantic capabilities such as read repository, search, edit allowed paths, or execute approved commands;
- `write_boundaries`: allowed paths and prohibited paths, independent of provider permission syntax;
- `output_schema`: provider-neutral structured-output contract;
- `model_capability_class`: `low_cost`, `standard`, or `high_reasoning`, not a vendor model name;
- `turn_budget`, `time_budget`, and `token_budget`: bounded execution limits, with unsupported measurements reported explicitly;
- `provider_configuration_key`: reference to external configuration that selects an adapter and provider settings without changing the request's task meaning.

The request must not contain Claude-specific tool names, Codex-specific tools, or provider API payloads. Adapters translate the semantic capability and budget fields into the closest supported provider mechanisms and fail closed when a required restriction cannot be enforced.

It also must not contain NSC task identity. `TaskExecutionRequest` composes `schema_version`, `task_id`, `task_contract_identity`, and an exact `AgentInvocationRequest`. This keeps the dependency direction `ExecutionCrew -> TaskExecution -> AgentRuntime`; generic workflows such as ArchitectureReview and Reconciliation may call AgentRuntime directly.

### Conceptual `AgentResult`

Every provider returns the same conceptual result. Its fields should cover:

- `provider`: adapter/provider identity used for the invocation;
- `model`: actual provider model identifier used;
- `role`: requested production role;
- `status`: normalized invocation outcome, distinct from delivery or conformance;
- `structured_output`: schema-validated role output when available;
- `changed_paths`: paths observed or reported as changed, subject to independent Git verification;
- `duration`: measured wall-clock duration;
- `usage`: token/cost/turn usage when the provider exposes it;
- `raw_log_reference`: path to the immutable provider log, not embedded provider output;
- `failure_classification`: normalized timeout, provider, permission, schema, budget, or execution failure;
- `claims_execution_occurred`: whether the agent claims it ran commands or tests.

An agent's execution claim is only a claim. Deterministic tooling must independently establish whether commands ran, which files changed, and what Unity produced.

## Provider adapters

`ClaudeCodeProvider` and the future `OpenAICodexProvider` implement one provider interface. Both consume the same `AgentInvocationRequest` and return the same `AgentResult`.

Adapters are responsible for:

- translating allowed capabilities and write boundaries into provider tool permissions or sandbox controls;
- delivering prompts and context through the provider's supported mechanism;
- enforcing or validating structured output as strongly as the provider permits;
- mapping provider-neutral capability classes to configured model names;
- applying timeouts and reporting duration, turns, tokens, and cost when available;
- preserving raw provider logs beneath the current immutable run directory;
- normalizing provider-specific errors into common failure classifications.

Adapters may translate:

- allowed capabilities into provider tool permissions;
- prompt and context delivery;
- structured-output enforcement;
- model names;
- timeout and usage reporting.

Adapters may not change task meaning, validation policy, or evidence authority. They may not weaken acceptance criteria, reinterpret write boundaries, turn an agent claim into test evidence, or declare a task ready, conformant, integrated, or complete.

## Production roles

The initial production crew has three roles.

### Implementer

The Implementer receives one already-selected bounded schema-v2 task contract and approved context. It changes production implementation only within explicit write boundaries, reports changed paths and blockers, and does not declare delivery success. It may repair implementation from concrete validation or runtime findings within a bounded GER budget.

### Unity Test Author

The Unity Test Author independently translates the task contract's completion gates and relevant risks into tests. It is initially the `low_cost` proving role so the runtime can demonstrate role-specific model selection without placing low-cost reasoning on final semantic validation.

Its normal write authority is limited to:

- Unity test code;
- test assembly definitions;
- test artifacts produced or curated for the run.

It must not silently modify production code to make testing easier. If production testability requires a seam or design change, it returns a structured proposal to the Implementer. The Implementer then decides whether the bounded production change is valid under the task contract, after which tests and deterministic gates run again.

### Validator

The Validator is read-only and uses a stronger model, normally `high_reasoning`. It performs semantic review against the task contract, approved canon/context, implementation diff, authored tests, and deterministic findings. Its result can request changes or identify ambiguity; it cannot establish test success, conformance, readiness, or delivery.

### Planning-role change

The schema-v2 task contract replaces most of Assignment 3's per-run planning role. The production crew should not ask a fresh Planner to redefine already-approved scope on every run. If a selected contract is ambiguous or too broad, execution stops and returns a structured blocker for human review or later contract/decomposition work outside the crew.

The Assignment 3 packager has no normal production role. Phase 3 evidence tooling and the delivery workflow, not a homework packager, will eventually assemble committed delivery or revalidation records.

## Model selection

Role prompts name capability requirements, never vendor model names. Initial provider-neutral capability classes are:

- `low_cost` for cheap, bounded proving work;
- `standard` for ordinary implementation and repair;
- `high_reasoning` for difficult semantic validation and high-risk reasoning.

Configuration maps a capability class plus a provider configuration key to a provider adapter and concrete model. This permits:

- all-Claude crews;
- all-OpenAI crews;
- mixed-provider crews;
- cross-provider validation experiments in which a different provider reviews implementation output.

Model availability and exact names are operational configuration, not prompt or schema changes. Configuration must fail clearly when no approved model satisfies the requested capability class.

## Deterministic authority boundary

LLM output never establishes:

- Unity test success;
- a clean working tree;
- integrated delivery;
- current conformance;
- readiness;
- dispatch authorization.

Those remain deterministic Git, Unity, and TaskGraph decisions. In particular:

- a test-author or implementer claim does not replace the clean Unity test runner and its result artifacts;
- changed-path claims do not replace Git diff and scope checks;
- a Validator `pass` does not create a Phase 3 delivery, baseline, or revalidation record;
- a committed evidence record is evaluated by TaskGraph logic against committed Git objects;
- `taskcontrol ready` and `taskcontrol authorize` remain disabled until separately designed, proven, and approved.

## Run artifacts

Each execution uses an immutable task/run-scoped directory such as:

```text
Pipeline/ExecutionCrew/runs/<run-id>/
  request.json
  implementation_result.json
  test_author_result.json
  validation_result.json
  provider_logs/
  unity_results/
  runtime_feedback/
```

The run ID must be unique and immutable. A run directory is append-only after finalization; retries or repairs receive distinguishable attempt artifacts or a new run identity according to the later schema. Mutable convenience pointers may be considered separately, but they are never historical authority.

The directory preserves requests, normalized results, raw provider logs, deterministic Unity results, and human/runtime feedback. It does not by itself prove delivery.

After integration and exact-commit validation, selected committed artifacts may be referenced by Phase 3 delivery, historical-adoption baseline, or revalidation records. Those evidence records bind the relevant artifact Git blobs, task-contract identity, canon identity, completion gates, integrated commit/tree, and required human approval. Final evidence should reference only artifacts that are appropriate to preserve, not blindly commit every raw provider transcript.

## Relationship to GER

The responsibilities form this chain:

```text
Execution Crew produces bounded implementation/test/validation artifacts
  -> deterministic execution produces actual Git/Unity evidence
  -> GER may perform bounded repair from concrete findings
  -> Phase 3 evaluates committed delivery/baseline/revalidation evidence
  -> a human and deterministic policy decide subsequent action
```

GER may send concrete deterministic, Unity, runtime, or semantic findings back to the Implementer and, when appropriate, the Unity Test Author. Repair attempts have explicit budgets, no-op repair is failed progress, and exhaustion escalates. No worker, role, crew, adapter, or GER pass declares itself complete.

## Relationship to TaskGraph

Task selection remains human-approved for now. `taskcontrol ready` and `taskcontrol authorize` remain disabled.

The Execution Crew receives exactly one already-selected bounded task contract. It does not:

- mutate `Tasks/*.yaml`;
- select global priority;
- derive or grant readiness;
- authorize dispatch;
- absorb unrelated prerequisites or redesign the task.

Ambiguous scope, missing design, oversized work, or a substantial prerequisite becomes a structured blocker for human review or a future separately authorized contract/decomposition workflow.

## Historical compatibility

Preserve:

- `AgentCrew/` as Assignment 3 historical evidence;
- `Assignment6GER/` as Assignment 6 historical evidence.

Production extraction must not rewrite those directories to look as though they always used the new runtime. If later compatibility is useful, add adapters or wrappers that translate historical inputs/outputs at their boundary, or migrate callers to the new production interfaces. Historical schemas, logs, and behavior remain unchanged.

## Staged implementation plan

Each stage requires human review before its outputs become architecture or delivery authority.

### Stage 0 - Documentation and architecture approval

- **Entry criteria:** Phase 3A architecture is understood; the Assignment 3 and Assignment 6 historical boundaries have been reviewed; this plan and ADR are available for human review.
- **Output:** reviewed architecture comments and, only if the human accepts it, an approved or revised provider-neutral direction.
- **Tests:** documentation link/path checks, requirement checklist review, and diff-scope review proving only authorized documentation changed.
- **Non-goals:** no architecture-approval claim in this task; no runtime, adapter, crew, test runner, Unity, task-contract, or dispatch implementation.

### Stage 1 - Canonical Unity testing policy and deterministic clean runner

- **Entry criteria:** Stage 0 direction is human-approved; Phase 3B remains the active milestone; existing Unity test commands and isolation risks are inventoried.
- **Output:** `Docs/Engineering/UNITY_TESTING_POLICY.md`, `Pipeline/Testing/run_unity_tests_clean.ps1`, and deterministic policy tests.
- **Tests:** policy-schema/content checks; temporary-project or fixture checks for clean-copy/isolation behavior, exit codes, result/log preservation, and failure handling; an approved real Unity proving run when available.
- **Non-goals:** no provider runtime, agent execution, role prompts, automatic evidence record, readiness, dispatch, or Unity gameplay changes.

### Stage 2 - Complete NSC-023 Phase 3 baseline/revalidation proof

- **Entry criteria:** Stage 1's testing policy and runner are reviewed and passing; one exact integrated NSC-023 state is selected; required human Unity access is available.
- **Output:** committed, exact-identity NSC-023 baseline evidence and a justified revalidation proof when a real relevant change exists or a controlled exercise is explicitly approved.
- **Tests:** clean Unity gates; evidence-record schema validation; Git commit/tree, contract/canon hash, surface blob, artifact blob, ancestry, and current-conformance checks.
- **Non-goals:** no fabricated gameplay change solely for revalidation; no readiness/dispatch enablement; no provider runtime extraction; no claim that other tasks are conformant.

### Stage 3 - Extract provider-neutral `AgentRuntime`

- **Entry criteria:** Phase 3 is merged; Stage 2 has proven the evidence path; request/result semantics and authority boundaries are human-approved.
- **Output:** provider-neutral contracts, runner interface, configuration loading, immutable run-layout support, and a fake provider for deterministic fixtures.
- **Tests:** contract/schema fixtures; configuration validation; path/write-boundary rejection; budget/timeout normalization; immutable artifact behavior; fake-provider success and failure cases.
- **Non-goals:** no live Claude or OpenAI invocation; no Execution Crew orchestration; no Unity changes; no dispatch authorization.

### Stage 4 - Implement Claude and OpenAI adapters against the same fixtures

- **Entry criteria:** Stage 3 interface is stable; provider credentials/tools are configured outside contracts; approved provider-specific permission mappings are documented.
- **Output:** `ClaudeCodeProvider` and `OpenAICodexProvider`, both conforming to the same request/result interface and shared fixture suite.
- **Tests:** adapter contract tests; structured-output success/failure; permission and write-boundary translation; timeout, usage, raw-log, and failure normalization; opt-in live smoke tests with no production writes.
- **Non-goals:** no provider-specific role prompts or task schemas; no change to validation/evidence policy; no automatic provider fallback that changes task meaning; no crew execution on a real task.

### Stage 5 - Create provider-neutral ExecutionCrew roles

- **Entry criteria:** both adapters pass shared fixtures; canonical Unity testing policy is active; one selected schema-v2 fixture contract exists.
- **Output:** provider-neutral Implementer, Unity Test Author, and Validator prompts/schemas plus bounded crew orchestration.
- **Tests:** role schema tests; read/write-capability enforcement; test-author isolation tests; implementer-to-test-author proposal handoff; validator read-only checks; bounded-repair and circuit-breaker fixtures.
- **Non-goals:** no global planning role; no homework packager; no autonomous task selection, task mutation, merge, evidence publication, readiness, or dispatch.

### Stage 6 - Prove one task with a mixed or interchangeable provider configuration

- **Entry criteria:** Stage 5 fixtures pass; a human selects one safe bounded task and provider configuration; branch/worktree and rollback boundaries are explicit.
- **Output:** one immutable run demonstrating either mixed providers or provider interchangeability for the same role contracts, with deterministic results preserved.
- **Tests:** clean Git scope checks; clean Unity runner; shared schema validation; compare normalized results across provider configurations; human review of behavior and cost/quality findings.
- **Non-goals:** no claim that provider outputs are identical; no broad benchmark conclusion from one task; no automatic merge, readiness, dispatch, or continuous execution.

### Stage 7 - Connect execution outputs to GER and Phase 3 evidence

- **Entry criteria:** at least one real bounded crew run is reviewed; deterministic findings are normalized; the exact integrated validation workflow is established.
- **Output:** bounded repair handoffs from concrete findings and a reviewed mapping from selected committed run artifacts to Phase 3 delivery/baseline/revalidation evidence.
- **Tests:** failing-finding-to-repair fixtures; no-op repair detection; retry/cost/runtime circuit breaker; exact commit/tree and artifact blob checks; post-integration Unity revalidation where required; current-conformance regression.
- **Non-goals:** no worker-authored completion truth; no automatic evidence authority from agent logs; no readiness/dispatch; no unbounded repair.

### Stage 8 - Consider readiness/dispatch only after repeated successful real deliveries

- **Entry criteria:** multiple real tasks have completed the selected-task, crew, deterministic validation, integration, and Phase 3 evidence path; failure and recovery behavior is documented; humans judge the process trustworthy enough to review dispatch policy.
- **Output:** a separate proposal for evidence-derived dependency readiness and dispatch authorization, or an explicit decision to remain human-dispatched.
- **Tests:** adversarial policy tests; stale/ambiguous/invalid evidence; dependency and exclusive-resource cases; dirty-tree and unintegrated-result rejection; budget/circuit-breaker and fail-closed behavior; human approval workflows.
- **Non-goals:** this stage does not presume approval; no immediate continuous autonomy, parallel workers, automatic merge, or task-priority delegation.

## Branch strategy

- Current testing-safety and Phase 3 evidence work remains on `phase-3-evidence-derived-conformance`.
- Provider runtime extraction begins only after Phase 3 is merged.
- The proposed later implementation branch is `provider-neutral-execution-crew`.

This plan does not create, switch, merge, or approve either branch.

## Immediate next slice

The immediate implementation after this planning commit is limited to:

- `Docs/Engineering/UNITY_TESTING_POLICY.md`;
- `Pipeline/Testing/run_unity_tests_clean.ps1`;
- deterministic policy tests;
- no provider runtime yet.

Phase 3B remains the immediate milestone. The testing-safety slice supports its clean, exact-commit Unity evidence; it does not displace it.
