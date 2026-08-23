# ADR-040 — OpenAI/Codex AgentRuntime and ArchitectureReview migration

**Accepted:** 2026-08-23.

## Decision

OpenAI/Codex is implemented as `OpenAICodexProvider` behind generic AgentRuntime. ArchitectureReview is the first existing non-task pipeline consumer migrated to `AgentInvocationRequest -> AgentRunner -> OpenAICodexProvider`.

The active OpenAI ArchitectureReview path no longer owns Codex subprocess supervision, structured-output parsing, usage parsing, timeout translation, or provider failure normalization. AgentRuntime owns those mechanics and remains unaware of reviewer roles, synthesis, resumability, NSC task identity, and ArchitectureReview authority.

Repository read/search is enabled only by an explicit provider construction profile. For production ArchitectureReview runs, containment relies on the existing `codex-review` Docker service: the repository mount is externally read-only and only ArchitectureReview outputs are writable. This is a practical trusted-local-development boundary, not a claim that Codex exposes a fine-grained Read/Glob/Grep security boundary. Context paths are guidance.

Repository writing, approved command execution, non-null token limits, and provider fallback remain unsupported. TaskExecution is not involved. AgentRuntime invocation artifacts are retained beneath each ArchitectureReview run but remain audit records, not architecture truth or project authority.

Generated ArchitectureReview output is explicitly provider-scoped: the direct historical/default Claude integration owns `outputs/claude/`, the active OpenAI integration owns `outputs/codex/`, and each provider's `latest/` contains convenience copies of its completed synthesis and critique. Global `outputs/latest/` contains only one atomically replaced `LATEST.json` pointer to the most recently completed provider-scoped run regardless of provider. Manifests record `provider_namespace`; resume may not cross namespaces; partial or failed runs do not publish latest. Accepted evidence remains separate under `evidence/`.

Independent reviewers must form conclusions from primary repository evidence without reading prior ArchitectureReview outputs or preserved evidence merely to learn earlier conclusions. They also ignore prior review verdicts, recommendations, synthesis/adversarial conclusions, and vote/count summaries embedded in normal architecture or current-state documentation, while retaining access to implemented architecture, accepted decisions, and current documented facts and judging them independently. Synthesis and adversarial critique are limited to the human-facing products of their own current run plus primary evidence. This experimental-independence boundary preserves provenance and permits later Claude-versus-Codex comparison without creating a comparison pipeline now. Both provider paths retain all eight independent reviewer roles.

## Consequence

This migration proves provider-neutral orchestration on a real pipeline consumer. It does not implement ExecutionCrew, migrate Reconciliation, authorize game-task execution, or establish delivery, conformance, readiness, test, or integration authority.
