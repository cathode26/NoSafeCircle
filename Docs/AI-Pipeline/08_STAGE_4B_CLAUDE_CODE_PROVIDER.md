# Stage 4B — Claude Code Provider

Status: **COMPLETE AND COMMITTED**

Implementation commit:

```text
ae046fd828f168dac6c87c49878fe1812f6c1fd7
```

Branch:

```text
provider-adapters
```

## Purpose

Stage 4B implements the first live-provider adapter against the provider-neutral `AgentRuntime` contract without granting the provider repository, command, evidence, readiness, or dispatch authority.

The implemented provider is:

```text
Pipeline/AgentRuntime/providers/claude_code.py
```

The shared bounded subprocess transport is:

```text
Pipeline/AgentRuntime/process_runner.py
```

## Initial accepted capability boundary

The initial `ClaudeCodeProvider` supports only:

```text
allowed_capabilities = ()
context_paths = ()
token_limit = null
```

Every invocation runs in a newly created empty temporary workspace outside the repository.

The provider currently rejects, before process launch:

- `repository_read`;
- `repository_search`;
- `repository_write`;
- `approved_command_execution`;
- any nonempty capability set;
- any nonempty `context_paths`;
- any non-null `token_limit`.

Repository read/search remains deferred until a separately reviewed containment design proves that Claude cannot read outside the intended evidence surface.

## Claude invocation boundary

The adapter invokes Claude Code directly without a shell and sends the prompt through stdin.

The command includes the reviewed controls:

- `--safe-mode`;
- explicit configured model selection;
- `--max-turns <AgentRequest.turn_limit>`;
- `--permission-mode dontAsk`;
- `--input-format text`;
- `--output-format json`;
- `--json-schema <compact schema argument>`;
- `--no-session-persistence`;
- `--tools ""`;
- explicit write, shell, notebook, and web-tool denial.

The adapter also applies the independent hard wall-clock limit from:

```text
AgentRequest.budgets.timeout_seconds
```

No automatic model or provider fallback is implemented.

## Structured-output and failure handling

A successful Claude result requires a strict result envelope with:

```text
type = result
is_error = false
subtype = success
terminal_reason = completed
structured_output present
```

`stop_reason=tool_use` is not treated as failure because it occurred during the successful structured-output discovery probe.

The adapter preserves exact valid machine-readable stdout as `provider.log`, normalizes usage conservatively, and returns only provider/agent claims.

Provider-neutral outcomes include:

- unsupported request policy -> `invalid_request`;
- provider output that cannot yield a structured candidate -> `schema_error`;
- local transport/transcript defect -> `internal_error`;
- external deadline -> `timeout`;
- recognized provider failure -> `provider_error`;
- central schema rejection of a parsed candidate -> `schema_error`.

These outcomes do not establish delivery, conformance, readiness, authorization, approval, integration, repository changes, command execution, or test success.

## Shared process supervision

`StandardProcessRunner` now provides bounded direct process execution with:

- `shell=False`;
- prompt delivery through stdin;
- exact stdout/stderr capture;
- process-group/session creation;
- hard external timeout enforcement;
- graceful then forced whole-process-group cleanup;
- partial-output preservation on timeout;
- cleanup on `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, and other post-launch `BaseException` paths;
- cleanup of same-group descendants after timeout, interruption, and successful root-process exit.

The transport writes no project artifacts and is provider-neutral so the later OpenAI/Codex adapter can reuse it.

## Deterministic validation

The following suites passed before commit:

```text
Pipeline/AgentRuntime/tests/agent_runtime_smoke_test.py
Pipeline/AgentRuntime/tests/process_runner_smoke_test.py
Pipeline/AgentRuntime/tests/claude_code_provider_smoke_test.py
```

Observed results:

```text
AgentRuntime smoke test: PASS
StandardProcessRunner smoke test: PASS
ClaudeCodeProvider smoke test: PASS
```

The process-runner suite uses real bounded child processes and verifies that no long-running test children remain.

No live `ClaudeCodeProvider` invocation has yet been performed through `AgentRunner`; Stage 4B validation to date consists of the earlier isolated CLI discovery probe plus deterministic injected-process fixtures.

## Reconciliation implications

This implementation is not yet sufficient to rerun full Reconciliation through `AgentRuntime` because the accepted Claude provider currently has no repository-read or repository-search capability.

Reconciliation migration still requires:

- a separately reviewed read-containment or frozen-evidence-package design;
- extension of the AgentRuntime JSON Schema subset for the Reconciliation schemas where needed;
- a provider-neutral Reconciliation workflow wrapper above individual AgentRuntime invocations;
- provider-aware assignment and lineage for generator, auditor, refiner, and verification roles.

## Next bounded stage

The next provider implementation slice is:

**Stage 4C — OpenAI/Codex Provider**

It should reuse `StandardProcessRunner`, preserve the same fail-closed output and authority boundaries, and initially support only empty capabilities and empty context in a fresh temporary workspace.

The approved Codex turn-budget mapping remains:

```text
OPENAI_SECONDS_PER_TURN = 30

effective_timeout_seconds =
    min(timeout_seconds, turn_limit * OPENAI_SECONDS_PER_TURN)
```

That mapping is a bounded-execution policy, not a claim that 30 seconds equals one provider model turn.

After both providers pass their shared deterministic fixtures, the next steps are opt-in non-production-write live smoke tests and then the Stage 5 `ExecutionCrew` role layer.
