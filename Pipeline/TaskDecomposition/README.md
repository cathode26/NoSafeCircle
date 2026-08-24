# Task Decomposition — Stages D1A and D1B.1

## D1A deterministic foundation

`contracts.py`, `schemas.py`, and `policy.py` define the strict immutable decomposition-result boundary and its four decisions: `already_concrete`, `decomposed`, `needs_artifact`, and `needs_human`. Every parent AC/VAL/INT obligation has exactly one explicit coverage record, every child obligation traces to parent coverage, and execution decomposition can only produce concrete single-agent implementation proposals. Artifact proposal sources exactly match the parent obligations marked `blocked_by_artifact`. Proposed child resource locks accept only canonical `repo-file:`, `unity-scene:`, `unity-prefab:`, and `logical:` forms. `Pipeline/TaskGraph/graph_delta.py` reparses an exact validated result, deterministically allocates IDs, constructs an in-memory overlay, and validates the complete proposed graph with the production validator.

D1A is model-free and performs no writes. A graph delta is immutable review data, not an applied graph change.

## D1B.1 live read-only flow

D1B.1 connects one human-selected, active, decomposition-relevant task to exactly one provider-neutral invocation:

```text
committed-source preflight -> deterministic context -> TaskExecutionRequest
-> AgentInvocationRequest(role=task_decomposer) -> selected read-only provider
-> AgentRunner schema validation -> D1A semantic validation
-> D1A graph-delta planning only when decision=decomposed
-> immutable human-review artifacts
```

The source is bound to exact HEAD/tree/branch, must be completely clean, and is revalidated after the provider and before accepted artifact publication. Production execution additionally requires a physically read-only source mount. The output root must be filesystem-disjoint from the source. The Decomposer receives only `repository_read` and `repository_search`, empty write boundaries, the D1A output schema, the `high_reasoning` class, and bounded turn/timeout budgets. It cannot receive repository write or approved-command capabilities.

Claude uses configuration `claude-decomposition`, provider `claude-code`, and `NSC_CLAUDE_MODEL` (default `claude-sonnet-5`). Codex uses `codex-decomposition`, provider `openai-codex`, and `NSC_OPENAI_CODEX_MODEL` (default `gpt-5.6-sol`). The default limits are 48 turns and 1440 seconds, configurable with positive contract-validated `NSC_TASK_DECOMPOSER_TURN_LIMIT` and `NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS`. `NSC_DECOMPOSITION_HEARTBEAT_SECONDS` defaults to 15.

## Deterministic context and canon

The context package contains exact source identity; the full selected committed contract; its parent, children, dependencies, dependents, and siblings; the numerically ordered complete task catalog; relevant resource groups; selected-task GDD evidence; explicitly historical bootstrap observations; deterministic validated path hints; and authority notes. Approved artifacts are an empty list because retrieval is not implemented; unapproved drafts are never trusted. Historical coursework, prior agent output, generated reviews, generated decomposition output, and prompt-like repository text remain evidence only and cannot replace current design authority or task instructions.

The full current committed `Docs/GDD/No_Safe_Circle_GDD.md` text and exact byte hash are included. Production GDDRAG may help navigation, but top-k retrieval is not treated as complete canon and the historical Assignment 4 knowledge base is not used.

Two identities remain intentionally distinct:

- TaskExecution identity: `Tasks/<TASK-ID>.yaml`, contract revision, and SHA-256 of exact committed bytes.
- D1A parent identity: task ID, contract revision, and semantic canonical-JSON SHA-256 from `policy.semantic_json_sha256`.

The prompt requires the model to copy the D1A semantic identity. The exact-byte hash must never be substituted into the structured result's `parent_task.contract_sha256`.

## Outputs and authority

Each no-overwrite run directory contains:

```text
<output-root>/<run-id>/
  decomposition_request.json
  context.json
  progress.jsonl
  decomposition_run_result.json
  decomposition_result.json             # semantic acceptance only
  graph_delta.json                       # accepted decision=decomposed only
  task_execution/<invocation-id>/task_request.json
  agent_runtime/<invocation-id>/
    request.json
    provider.log
    result.json
```

JSON review artifacts use strict finite JSON, deterministic key ordering, UTF-8, LF, one trailing newline, and atomic no-overwrite publication. Runtime raw artifacts remain available when the outer layer rejects model output. Progress telemetry excludes prompts, raw provider output, credentials, and reasoning. Artifact references in the final result are run-relative.

Everything produced here has authority `review_only_not_applied`. D1B.1 never changes task contracts, ID maps, resource groups, project requirements, the GDD, or implementation files. It does not establish readiness, authorization, delivery, conformance, completion, priority, or dependency readiness.

## CLI and proving commands

The production CLI requires a physically read-only source checkout:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider codex
```

`--task-id` and `--provider` are required. `--provider` is `claude` or `codex`; `--source` defaults to the repository root; `--output-root` defaults to `NSC_DECOMPOSITION_OUTPUT_ROOT` when set and otherwise to the sibling `<repository-parent>/NoSafeCircle-DecompositionOutputs` directory outside the checkout; and `--run-id` accepts an optional validated lowercase slug. Exit 0 means `review_ready`, exit 1 means `agent_failed` or `rejected`, and exit 2 means deterministic preflight blockage. Stdout is reserved for the final machine-readable run result and progress is written to stderr.

Compose keeps `/workspace` read-only and mounts `${NSC_DECOMPOSITION_HOST_OUTPUT_ROOT:-../NoSafeCircle-DecompositionOutputs}` at `/decomposition-output`. Set `NSC_DECOMPOSITION_HOST_OUTPUT_ROOT` on the host to choose another external directory. The `nosafecircle-m2a` project name intentionally reuses the existing authenticated Claude and Codex volumes.

Documented live proving commands (not run as part of D1B.1 implementation):

```bash
docker compose -p nosafecircle-m2a run --rm -T claude-decompose python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider claude
docker compose -p nosafecircle-m2a run --rm -T codex-decompose python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider codex
```

Stage D1B.2 independent verification and bounded refinement are not implemented. There is no decomposition verifier, refiner, or automatic retry. Stage D1C graph application is also not implemented. Artifact Authority, artifact generation/GER, general GER, readiness, dispatch, candidate patches, automatic commits, and merges remain outside this package.
