# ADR-037 — Initial Claude Code Provider Boundary

## Status

Accepted — 2026-08-23.

Implemented by:

```text
ae046fd828f168dac6c87c49878fe1812f6c1fd7
```

## Context

ADR-034 established the provider-neutral `AgentRuntime`. ADR-035 defined fail-closed provider-adapter enforcement, and ADR-036 rejected adopting `agent-mux` or `agent-shell` as the production transport layer.

The first Claude Code adapter needed a boundary that could be proven without assuming that Claude's working directory, prompt instructions, or ordinary read tools provide deterministic repository-only containment.

The isolated CLI discovery probe proved structured-output mechanics, explicit model selection, native `--max-turns`, usage fields, and empty-stderr success. It did not prove repository read/search containment, repository writing, command allowlisting, or production execution authority.

## Decision

The initial `ClaudeCodeProvider` is accepted with these restrictions:

1. Only an empty capability set is supported.
2. `context_paths` must be empty.
3. `token_limit` must be null.
4. Every invocation runs in a new empty temporary workspace outside the repository.
5. Claude is invoked directly with no shell and receives its prompt through stdin.
6. Built-in tools are disabled with an explicit empty tool set; shell, file modification, notebook, and web tools are explicitly denied.
7. Safe mode and no-session-persistence are required.
8. The configured concrete model is used without alias substitution or automatic fallback.
9. `turn_limit` maps to Claude's native `--max-turns`; `timeout_seconds` remains the independent hard wall-clock ceiling.
10. Provider stdout is preserved exactly as the provider log when valid.
11. Provider output and usage are parsed strictly and fail closed.
12. Unsupported request combinations are rejected before provider launch and normalize to `invalid_request`.
13. Malformed provider output that cannot produce a structured candidate normalizes to `schema_error`.
14. Local process or transcript defects normalize to `internal_error`.
15. Provider output remains an invocation result and set of claims, never project authority.

## Process-lifecycle decision

A launched provider process is not considered safely complete merely because its root process returned.

`StandardProcessRunner` therefore owns bounded cleanup of the original process group after:

- external timeout;
- interruption or other post-launch `BaseException`;
- successful root-process exit.

Cleanup first requests graceful termination where appropriate and then performs a final hard process-group cleanup so a same-group descendant cannot survive the invocation unnoticed.

This behavior is covered by real bounded child-process regressions, including interrupt cleanup, timeout cleanup, a SIGTERM-ignoring descendant, and a descendant left behind by a successful root process.

## Consequences

Positive:

- the first live-provider adapter has a narrow, provable containment boundary;
- provider execution cannot silently broaden into repository or command access;
- Claude and the later Codex adapter can share one tested process-supervision layer;
- malformed requests, transport defects, provider failures, and schema failures remain distinguishable;
- no provider result can establish delivery, conformance, readiness, authorization, approval, or Unity success.

Constraints:

- the initial Claude adapter cannot inspect the repository;
- it cannot yet run full Reconciliation or an implementation role;
- repository read/search requires a later containment or frozen-evidence-package decision;
- live use remains opt-in and non-production-write;
- compatibility with future Claude Code CLI versions remains the project's responsibility.

## Rejected alternatives

### Enable `Read`, `Glob`, or `Grep` in the repository immediately

Rejected because the discovery work did not prove that those tools are confined to the repository or approved context paths. A working directory and prompt hint are not a deterministic read boundary.

### Depend on prompt instructions for isolation

Rejected. Prompt compliance is not filesystem or capability enforcement.

### Accept a successful root exit without descendant cleanup

Rejected. A provider or tool descendant could otherwise continue consuming resources or holding files after the invocation was reported complete.

### Treat deterministic fixtures as production authority

Rejected. Passing adapter tests proves the transport and normalization behavior under tested conditions; it does not prove a gameplay task, Reconciliation result, Unity behavior, delivery, conformance, readiness, or authorization.

## Exit criteria for capability expansion

Repository read/search may be proposed only after a separate reviewed implementation proves one of:

- externally enforced read-only containment with no broader credential, filesystem, command, or network access than approved;
- a deterministic frozen evidence/context package supplied in an isolated temporary workspace;
- another mechanism with equivalent fail-closed evidence.

Any expansion must add deterministic fixtures and an opt-in live non-production-write smoke test before production role use.
