# ADR-035 - Provider-Adapter Enforcement

## Status

Accepted — 2026-08-23.

Amended — 2026-08-23 after the provider-transport adopt-versus-build spike.

## Context

ADR-034 established a provider-neutral `AgentRuntime` and reserved deterministic authority to Git, Unity, TaskGraph, and humans. Stage 3 implemented the shared contracts and fake provider. Stage 4 must translate one `AgentRequest` into Claude Code and OpenAI/Codex CLI mechanics without presenting unlike or unproven controls as equivalent.

Opt-in, non-production-write probes of Claude Code 2.1.222 and Codex CLI 0.149.0 established structured-output success paths, transcript shapes, and partial usage data. They did not establish repository-write safety, command allowlisting, token-budget enforcement, equivalent native turn semantics, provider failure envelopes, or production role readiness. The evidence and exact mappings are recorded in `07_PROVIDER_ADAPTER_CAPABILITY_MAPPING.md`.

A subsequent adopt-versus-build spike evaluated the public `agent-mux` and `agent-shell` projects as possible shared transport layers. Neither is adopted. `agent-mux` required a local Linux build patch at the tested commit and its Claude/Codex invocation contracts omit or differ from several fail-closed controls required here. `agent-shell` is easier to embed but intentionally warns and continues for some unsupported capability restrictions rather than failing closed. The production pipeline therefore keeps its narrow provider adapters inside `Pipeline/AgentRuntime` while borrowing general implementation lessons such as process-group cleanup, concurrent stdout/stderr draining, external timeouts, and provider-event parsing.

The spike also confirmed that a single provider-internal definition of "turn" is not available across the two CLIs. Rather than bumping the request schema solely to remove the existing required `turn_limit`, this ADR now treats that field as the provider-neutral bounded-execution budget knob and defines an explicit provider-specific enforcement mapping.

## Decision

Stage 4 will follow these rules:

1. Adapters translate provider mechanics but never silently weaken an `AgentRequest` capability or containment requirement.
2. Unsupported capability or budget combinations fail closed unless this ADR explicitly defines a reviewed provider-specific enforcement translation.
3. After fixtures prove them, initial Claude support may include only the mapped structured-output/read/search combinations; initial Codex support is the empty capability set only, with empty `context_paths`, in a newly created empty temporary working directory with no repository working directory or repository context.
4. Production model mappings use explicit concrete provider model identifiers and no automatic fallback.
5. `repository_write` and `approved_command_execution` remain unsupported.
6. A non-null `token_limit` remains unsupported and fails closed.
7. `timeout_seconds` is hard-enforced externally by the adapter subprocess timeout for both providers.
8. `AgentRequest` remains schema 1.0 and keeps the required positive integer `turn_limit`. No request-schema bump is required for Stage 4.
9. Claude Code maps `turn_limit=N` to native `--max-turns N` and also remains subject to the independent external `timeout_seconds` ceiling. The native flag is used as the strongest available provider mechanism, but Claude-reported `num_turns` is not treated as cross-provider-comparable accounting because the discovery probe accepted `--max-turns 1` while reporting `num_turns=2`.
10. OpenAI/Codex has no observed native turn-limit option. The initial Codex adapter therefore uses the approved temporary wall-clock translation `OPENAI_SECONDS_PER_TURN = 30`, with `effective_timeout_seconds = min(timeout_seconds, turn_limit * 30)`. This is conservative execution-budget emulation, not a claim that 30 seconds equals one Codex model turn.
11. The Claude and Codex `turn_limit` mappings are operational bounds, not a provider benchmark. Equal `turn_limit` values must not be interpreted as equal reasoning steps, model calls, work, quality, cost, or latency across providers.
12. Live smoke tests are opt-in and perform no production writes.
13. Both adapters must pass shared fixture conformance before Stage 5 begins.
14. Deterministic Git, Unity, TaskGraph, evidence, readiness, dispatch, and human authority remain unchanged. Provider output establishes only invocation results and provider/agent claims.
15. `provider.log` is exact machine-readable stdout. Successful exit requires empty stderr; exit zero with non-empty stderr is `internal_error` until a fixture proves that exact stderr is benign. Nonzero exit preserves stdout as the raw log and uses safely decoded stderr for the normalized provider diagnostic.
16. Stage 4 adds a provider-neutral `ProviderOutputInvalid` exception, or equivalent name, mapped to `schema_error`; `AgentRunner` retains responsibility for validating a parsed candidate against `AgentRequest.output_schema`.
17. Normalized usage is provider-local audit data. Claude/Codex cache and reasoning categories remain unreconciled, so token totals are not yet directly comparable provider efficiency, quality, or cost measurements.
18. `agent-mux` and `agent-shell` are not production dependencies. Any later proposal to adopt a shared transport library requires a new reviewed decision demonstrating that the dependency preserves these fail-closed boundaries rather than weakening them.

## Consequences

Positive consequences:

- provider differences become explicit, reviewable mappings rather than hidden assumptions;
- unsupported restrictions cannot silently degrade into broader provider access;
- the existing AgentRequest schema remains stable for Stage 4;
- the project keeps one convenient required bounded-execution knob while using the strongest practical mechanism each CLI exposes;
- structured output, usage, raw logs, and failures can be tested through one provider-neutral boundary;
- production execution authority and deterministic evidence boundaries remain intact;
- later capability expansion requires evidence and a reviewed enforcement decision;
- no third-party transport dependency is introduced merely to wrap two already-understood CLI contracts.

Costs and constraints:

- `turn_limit` is not a cross-provider unit of work and must not be used for provider benchmarking;
- the Codex 30-seconds-per-unit translation is an explicit temporary policy that may need tuning or replacement after real Stage 4/5 evidence;
- the initial adapters cannot execute production implementation roles;
- non-null token budgets remain blocked;
- Codex repository read/search remains unsupported pending a separately approved containment decision proving filesystem, command, credential, and network restrictions;
- provider-specific failure fixtures and operational model mappings add work before Stage 5;
- capability differences may prevent identical requests from being supported by both adapters;
- maintaining our own narrow adapters means we own CLI compatibility updates, process supervision, and transcript parsing for Claude Code and Codex.

## Rejected alternatives

### Best-effort capability weakening

Reject unsupported flags, permissions, or budgets instead of dropping them and continuing. Best-effort weakening would violate the request contract and make provider comparisons misleading.

### Treat prompts or `context_paths` as security enforcement

Reject prompt-only restrictions and path hints as substitutes for containment. `context_paths` identify relevant task context; they are not a read allowlist, and prompt compliance is not deterministic enforcement.

### Enable writes using claimed write boundaries

Reject initial write support. Neither observed CLI has proven native path-level enforcement of the provider-neutral `write_boundaries`, so repository-write requests must fail closed.

### Enable general command execution from provider tool controls

Reject initial command execution. No provider-neutral command allowlist and enforcement mapping has been proven.

### Make `turn_limit` nullable solely because Codex lacks a native turn flag

Rejected for the current capstone stage. The field remains useful as a required bounded-execution budget knob. Claude uses its native turn flag plus the external timeout; Codex uses the explicitly approved 30-seconds-per-unit wall-clock translation capped by `timeout_seconds`. This avoids a request-schema bump while keeping execution bounded.

### Pretend the provider turn mappings are equivalent

Rejected. Claude native turns and Codex wall-clock emulation are different mechanisms. Equal request values do not establish equal provider work. The mapping exists to bound execution, not to create a scientifically comparable provider metric.

`ExecutionCrew` invocation/attempt limits and GER repair limits remain separate later orchestration policy. They will bound repeated provider invocations and repair cycles rather than redefining the per-invocation `turn_limit` mapping.

### Adopt `agent-mux` as the provider transport

Rejected after a bounded spike. The tested source commit required a Linux compatibility patch before it would build, and its built-in Claude/Codex invocation contracts do not expose several controls required by this ADR, including the exact structured-output and isolation flags proven in our discovery probes. Forking and maintaining those changes would erase much of the benefit of adoption.

### Adopt `agent-shell` as the provider transport

Rejected after source review. Its adapters deliberately warn-and-ignore some unsupported allowed/denied capability requests, and its defaults/invocation mechanics do not match this project's fail-closed contract. Its process-cleanup and streaming patterns remain useful reference material, but it is not an authority or production dependency.

### Automatic model or provider fallback

Reject automatic fallback because it silently changes the approved model mapping and may change capabilities, behavior, cost, or containment assumptions.

### Treat live probe success as production readiness

Reject this inference. A successful structured-output probe does not establish failure normalization, capability enforcement, real-role correctness, Unity success, delivery, conformance, readiness, or authorization.
