# ADR-034 - Provider-Neutral Agent Runtime

## Status

Proposed, pending human review.

## Context

Assignment 3 demonstrated useful execution-crew patterns through fresh agent invocations, artifact handoffs, structured schemas, role-specific permissions, implementation/validation separation, bounded repair, and required human Unity validation. Its runner is also tied directly to the Claude CLI, applies one global model to every role, gives test authorship to the Implementer, relies on static model validation, and overwrites latest outputs.

Assignment 6 reused parts of that runner and proved the broader GER lesson: concrete evaluator and human Unity findings can drive bounded repair, no-op repair is failed progress, and a worker's static pass is not completion evidence.

Production execution must support both Claude Code and OpenAI/Codex without duplicating task contracts, role semantics, validation policy, or evidence formats. This work must not interrupt Architecture Correction Phase 3B, which remains the immediate milestone.

## Decision

The proposed production architecture adopts these rules:

1. Production agent roles, task-facing request/result contracts, prompts, and schemas are provider-neutral.
2. Claude Code and OpenAI/Codex are interchangeable provider adapters behind one production `AgentRuntime` interface.
3. Both adapters consume the same conceptual `AgentRequest` and return the same conceptual `AgentResult`.
4. Provider adapters may translate permissions, context delivery, structured-output mechanisms, model names, timeouts, usage, logs, and provider failures. They may not change task meaning, validation policy, or evidence authority.
5. Model selection uses provider-neutral capability classes configured outside role prompts.
6. Historical coursework directories remain preserved: `AgentCrew/` is Assignment 3 evidence and `Assignment6GER/` is Assignment 6 evidence. Later compatibility uses wrappers or adapters rather than rewriting history.
7. Important correctness invariants are enforced deterministically rather than delegated to model intelligence. LLM output cannot establish Unity test success, a clean working tree, integrated delivery, current conformance, readiness, or dispatch authorization.
8. Implementation is staged. The canonical Unity testing policy and clean deterministic runner come first; provider runtime extraction begins only after Phase 3 is merged and does not interrupt Phase 3B.

The detailed staged plan and target layout are recorded in `Docs/AI-Pipeline/06_PROVIDER_NEUTRAL_EXECUTION_CREW_PLAN.md`.

## Consequences

Positive consequences:

- task contracts and evidence remain stable when providers or models change;
- all-Claude, all-OpenAI, mixed-provider, and cross-provider validation configurations can use the same role semantics;
- provider permission and response differences are isolated and testable;
- deterministic Git, Unity, and TaskGraph mechanisms retain correctness authority;
- historical course evidence remains truthful and auditable.

Costs and constraints:

- adapters require shared conformance fixtures and fail-closed capability mapping;
- provider feature differences must be normalized without pretending their behavior is identical;
- raw provider logs and normalized results require immutable run-scoped storage;
- role isolation, especially independent test authorship, adds orchestration steps;
- no runtime implementation may be treated as approved merely because this ADR is proposed.

## Deferred decisions

This ADR does not approve:

- concrete Python contract fields or JSON schemas;
- provider SDK/CLI choices or exact model mappings;
- automatic provider fallback;
- production role prompt wording;
- readiness, dispatch, task claiming, merging, or continuous autonomy;
- changes to Phase 3 evidence authority.

Those details require staged implementation, fixtures, real-task evidence, and human review.
