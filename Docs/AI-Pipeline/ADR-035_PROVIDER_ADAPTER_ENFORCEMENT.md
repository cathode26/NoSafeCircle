# ADR-035 - Provider-Adapter Enforcement

## Status

Accepted — 2026-08-23.

## Context

ADR-034 established a provider-neutral `AgentRuntime` and reserved deterministic authority to Git, Unity, TaskGraph, and humans. Stage 3 implemented the shared contracts and fake provider. Stage 4 must translate one `AgentRequest` into Claude Code and OpenAI/Codex CLI mechanics without presenting unlike or unproven controls as equivalent.

Opt-in, non-production-write probes of Claude Code 2.1.222 and Codex CLI 0.149.0 established structured-output success paths, transcript shapes, and partial usage data. They did not establish repository-write safety, command allowlisting, token-budget enforcement, equivalent turn limits, provider failure envelopes, or production role readiness. The evidence and exact mappings are recorded in `07_PROVIDER_ADAPTER_CAPABILITY_MAPPING.md`.

## Decision

Stage 4 will follow these rules:

1. Adapters translate provider mechanics but never weaken or reinterpret `AgentRequest`.
2. Unsupported capability or budget combinations fail closed.
3. After fixtures prove them, initial Claude support may include only the mapped structured-output/read/search combinations; initial Codex support is the empty capability set only, with empty `context_paths`, in a newly created empty temporary working directory with no repository working directory or repository context.
4. Production model mappings use explicit concrete provider model identifiers and no automatic fallback.
5. `repository_write` and `approved_command_execution` remain unsupported.
6. A non-null `token_limit` remains unsupported and fails closed.
7. `timeout_seconds` is hard-enforced externally by the adapter subprocess timeout.
8. Adapter implementation is blocked on a separately reviewed AgentRuntime request-schema bump that makes `turn_limit` optional: null requests no provider-internal hard turn limit, while non-null requires proven hard enforcement or rejection. Initial adapters accept only null `turn_limit` and null `token_limit`.
9. Live smoke tests are opt-in and perform no production writes.
10. Both adapters must pass shared fixture conformance before Stage 5 begins.
11. Deterministic Git, Unity, TaskGraph, evidence, readiness, dispatch, and human authority remain unchanged. Provider output establishes only invocation results and provider/agent claims.
12. `provider.log` is exact machine-readable stdout. Successful exit requires empty stderr; exit zero with non-empty stderr is `internal_error` until a fixture proves that exact stderr is benign. Nonzero exit preserves stdout as the raw log and uses safely decoded stderr for the normalized provider diagnostic.
13. Stage 4 adds a provider-neutral `ProviderOutputInvalid` exception, or equivalent name, mapped to `schema_error`; `AgentRunner` retains responsibility for validating a parsed candidate against `AgentRequest.output_schema`.
14. Normalized usage is provider-local audit data. Claude/Codex cache and reasoning categories remain unreconciled, so token totals are not yet directly comparable provider efficiency, quality, or cost measurements.

## Consequences

Positive consequences:

- provider differences become explicit, reviewable mappings rather than hidden assumptions;
- unsupported restrictions cannot silently degrade into broader provider access;
- structured output, usage, raw logs, and failures can be tested through one provider-neutral boundary;
- production execution authority and deterministic evidence boundaries remain intact;
- later capability expansion requires evidence and a reviewed enforcement decision.

Costs and constraints:

- the initial adapters cannot execute production implementation roles;
- non-null token budgets and all requests whose turn-limit requirements cannot be honestly enforced remain blocked;
- Codex repository read/search remains unsupported pending a separately approved containment decision proving filesystem, command, credential, and network restrictions;
- provider-specific failure fixtures and operational model mappings add work before Stage 5;
- capability differences may prevent identical requests from being supported by both adapters.

## Rejected alternatives

### Best-effort capability weakening

Reject unsupported flags, permissions, or budgets instead of dropping them and continuing. Best-effort weakening would violate the request contract and make provider comparisons misleading.

### Treat prompts or `context_paths` as security enforcement

Reject prompt-only restrictions and path hints as substitutes for containment. `context_paths` identify relevant task context; they are not a read allowlist, and prompt compliance is not deterministic enforcement.

### Enable writes using claimed write boundaries

Reject initial write support. Neither observed CLI has proven native path-level enforcement of the provider-neutral `write_boundaries`, so repository-write requests must fail closed.

### Enable general command execution from provider tool controls

Reject initial command execution. No provider-neutral command allowlist and enforcement mapping has been proven.

### Infer token or turn equivalence

Reject estimates as hard-budget enforcement. Neither CLI exposed observed native token-limit enforcement; Claude's accepted `--max-turns 1` run reported `num_turns=2`, and Codex exposed no observed turn-limit flag.

`ExecutionCrew` invocation/attempt limits and GER repair limits remain separate later orchestration policy and do not satisfy a provider-internal hard turn budget.

### Automatic model or provider fallback

Reject automatic fallback because it silently changes the approved model mapping and may change capabilities, behavior, cost, or containment assumptions.

### Treat live probe success as production readiness

Reject this inference. A successful structured-output probe does not establish failure normalization, capability enforcement, real-role correctness, Unity success, delivery, conformance, readiness, or authorization.

## Immediate implementation prerequisite

The separately reviewed AgentRuntime request-schema revision is an accepted prerequisite that has not yet been implemented. It must bump the request schema, make `turn_limit` optional, define null as no requested hard provider-internal limit, and require proven enforcement or rejection for non-null values. Adapter implementation remains blocked until that code change is implemented and reviewed.

## Remaining unresolved decisions

- Which approved external read-only and network-restricted containment profile enables Codex repository read/search.
- Whether and how either provider can enforce path-level writes before `repository_write` is added.
- The provider-neutral design and deterministic enforcement of approved command allowlisting.
- Exact mappings for provider-specific failure envelopes after representative fixtures exist.
- Explicit concrete model identifiers approved for every provider and model capability class.

## Stage 4 entry criteria

Adapter implementation may begin only after:

- a later, separately reviewed AgentRuntime code change bumps the request schema and makes `turn_limit` optional, with null meaning no hard provider-internal limit requested and non-null requiring proven hard enforcement or rejection;
- the initial fixture contract requires both `turn_limit=null` and `token_limit=null`, while retaining externally hard-enforced `timeout_seconds`;
- the initial capability boundary is fixed as the mapped Claude combinations and empty-capability-only Codex execution with empty `context_paths` in a newly created empty temporary working directory.

## Stage 4 exit criteria

Stage 4 is complete only when all of the following are true:

- before adapter implementation begins, the separately reviewed AgentRuntime schema revision makes `turn_limit` optional with the semantics above;
- Claude Code implements only the approved structured-output/read/search boundary, while OpenAI/Codex accepts only empty capabilities and empty `context_paths` in a newly created empty temporary working directory with no repository context;
- every accepted capability combination is explicitly mapped and every unsupported combination fails closed;
- concrete production model IDs exist for every supported capability-class mapping, with no aliases or fallback;
- timeout, rejection of non-null token and turn limits, and acceptance of null token and turn limits are covered by shared fixtures;
- structured-output success and failure, `ProviderOutputInvalid` mapping, usage normalization, exact raw-log preservation, empty successful stderr, zero-exit non-empty-stderr failure, safely decoded nonzero-exit stderr diagnostics, permission denial, provider error, timeout, budget exhaustion, schema error, and internal error are covered by shared fixtures, including provider-specific failure-envelope fixtures;
- Codex repository read/search remains unsupported until a separate human-approved containment decision and later implementation slice;
- opt-in live smoke tests succeed without production writes and their limited evidentiary meaning is documented;
- the repository contains no production provider writes, approved command execution, automatic fallback, `ExecutionCrew` orchestration, real gameplay execution, or changes to deterministic Git, Unity, TaskGraph, or human authority.

Only after these criteria are established may Stage 5 provider-neutral role orchestration be proposed.
