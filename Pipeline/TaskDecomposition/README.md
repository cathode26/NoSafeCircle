# Task Decomposition — Stages D1A and D1B.1

## D1A deterministic foundation

`contracts.py`, `schemas.py`, and `policy.py` define the strict immutable decomposition-result boundary and its four decisions: `already_concrete`, `decomposed`, `needs_artifact`, and `needs_human`. Every parent AC/VAL/INT obligation has exactly one explicit coverage record, every child obligation traces to parent coverage, and execution decomposition can only produce concrete single-agent implementation proposals. Artifact proposal sources exactly match the parent obligations marked `blocked_by_artifact`. Proposed child resource locks accept only canonical `repo-file:`, `unity-scene:`, `unity-prefab:`, and `logical:` forms. `Pipeline/TaskGraph/graph_delta.py` reparses an exact validated result, deterministically allocates IDs, constructs an in-memory overlay, and validates the complete proposed graph with the production validator plus strict decomposition-aggregate semantics.

New provider output uses decomposition-result schema `1.1`. A `decomposed` result must include `inbound_dependency_rewrites`: exactly one review-only rewrite for every active direct dependent that currently names the selected parent in `depends_on`, and no extras. Each rewrite identifies one or more proposed child `local_key` values whose concrete capability replaces the aggregate dependency. The structural provider schema intentionally stays within AgentRuntime's fail-closed JSON-Schema subset; non-empty rewrite targets, child existence, exact dependent coverage, and other graph semantics are enforced by the immutable contract/policy/planner layers.

A successful new graph delta transitions the selected parent into a non-executable aggregate feature. It records the complete active direct-child set in `decomposition_children`, records `decomposition_requirement_sha256` for the parent AC/VAL/INT obligations that were actually decomposed, clears executable parent resource locks, rewrites active inbound dependencies to concrete children, and increments affected dependent contract revisions. If the parent requirements later change, child-derived aggregate conformance reports `needs_replan` rather than silently proving newer requirements.

D1A is model-free and performs no writes. A graph delta is immutable review data, not an applied graph change.

## D1B.1 live read-only flow

D1B.1 connects one **human-authorized**, active, decomposition-relevant task to exactly one provider-neutral invocation:

```text
committed-source preflight -> deterministic context -> TaskExecutionRequest
-> AgentInvocationRequest(role=task_decomposer) -> selected read-only provider
-> AgentRunner schema validation -> D1A semantic validation
-> D1A graph-delta planning only when decision=decomposed
-> immutable human-review artifacts
```

Human authorization may be specific (`Decompose NSC-021`) or generic (`Go pick a task and start on it`) when the generic selection request is being handled under `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md` and `Docs/AI-Pipeline/GENERIC_TASK_SELECTION_RETRY_AND_DECOMPOSITION.md`. Under a generic request, the orchestrator may select an eligible decomposition parent as the bounded work unit. This does not weaken the deterministic task-selection preflight or any review/application boundary.

The source is bound to exact HEAD/tree/branch, must be completely clean, and is revalidated after the provider and before accepted artifact publication. Production execution additionally requires a physically read-only source mount. The output root must be filesystem-disjoint from the source. For real task orchestration on the Windows operator machine, `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` and `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md` additionally require the host output root to be `Downloads\NoSafeCircleOutput\<TASK-ID>` so each D1B.1 run lands at `Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>`. The Decomposer receives only `repository_read` and `repository_search`, empty write boundaries, the D1A output schema, the `high_reasoning` class, and bounded turn/timeout budgets. It cannot receive repository write or approved-command capabilities.

Claude uses configuration `claude-decomposition`, provider `claude-code`, and `NSC_CLAUDE_MODEL` (default `claude-sonnet-5`). Codex uses `codex-decomposition`, provider `openai-codex`, and `NSC_OPENAI_CODEX_MODEL` (default `gpt-5.6-sol`). The default limits are 48 turns and 1440 seconds, configurable with positive contract-validated `NSC_TASK_DECOMPOSER_TURN_LIMIT` and `NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS`. `NSC_DECOMPOSITION_HEARTBEAT_SECONDS` defaults to 15.

## Decomposition as an orchestrator work type

Decomposition is now a selectable **orchestrator work type** for generic task-picking requests. It is not a new TaskGraph `kind` and does not create a fake `NSC-###` task for the act of decomposition.

A fresh orchestrator should discover active decomposition-relevant parents alongside fresh implementation candidates. The production eligibility authority is `context_builder.validate_task_selection()`.

That preflight rejects, among other invalid selections:

- malformed/non-schema-v2 task identity;
- inactive contracts;
- the project root;
- tasks already marked `decomposition_state: decomposed`;
- already concrete `single_agent` work;
- concrete work whose execution scope is not meaningfully decomposition-relevant.

Common decomposition-relevant execution scopes are:

```text
needs_execution_decomposition
human_integration_required
unknown
```

subject to the full production preflight and current `decomposition_state`.

A concrete task with `execution_scope: needs_execution_decomposition` is the clearest case: the design is approved/concrete, but the work bundles too many independently verifiable responsibilities for one implementation agent.

Decomposition remains progressive and just-in-time. Generic selection authority must not be used to decompose the entire backlog speculatively. Prefer near-frontier decomposition that unlocks useful work.

## Generic retry interaction

When decomposition was selected under a generic task-picking request:

- failure of one **candidate selection** does not end the overall generic selection attempt;
- deterministic preflight rejection, an unavailable/claimed parent, or an exhausted blocked/rejected decomposition attempt may release that candidate and return the orchestrator to the next sensible implementation/decomposition candidate;
- normal provider/runtime difficulties should respect existing bounded retry/circuit-breaker policy rather than causing immediate task-hopping;
- a `review_ready` result is a **successful decomposition work unit**, including semantic decisions `needs_artifact` or `needs_human`, because the useful output is the reviewed diagnosis/proposal.

Do not treat `review_ready` decomposition as a failure merely because it stops at a human/artifact/application boundary.

If the human explicitly named the parent (`Decompose NSC-021`), do not silently substitute a different parent if it is blocked.

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

On the Windows operator machine, the canonical task-associated form is:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>\
```

For example:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\20260825-195246\
```

The parent `<TASK-ID>` folder is the host output root. D1B.1 creates the `<RunId>` directory itself and fails closed if that run directory already exists; do not pre-create the run directory.

JSON review artifacts use strict finite JSON, deterministic key ordering, UTF-8, LF, one trailing newline, and atomic no-overwrite publication. Runtime raw artifacts remain available when the outer layer rejects model output. Progress telemetry excludes prompts, raw provider output, credentials, and reasoning. Artifact references in the final result are run-relative.

Everything produced here has authority `review_only_not_applied`. D1B.1 never changes task contracts, ID maps, resource groups, project requirements, the GDD, or implementation files. It does not establish readiness, authorization, delivery, conformance, completion, priority, or dependency readiness.

A generic task-picking instruction authorizes the orchestrator to **select and run** an eligible D1B.1 proposal. It does **not** authorize applying the proposal. `graph_delta.json` remains review-only. Stage D1C reusable graph application remains unimplemented.

### Human review after `review_ready`

`review_ready` means D1A accepted the structured result and, for `decision=decomposed`, the proposed graph overlay is structurally valid. It is not automatic graph-application approval.

Before applying a reviewed proposal, the human/orchestrator must still check execution locality and dependency realism. In particular, reject or revise a proposal when a proposed child completion gate requires downstream authored content or a downstream task that itself depends on the parent being decomposed. That creates a semantic completion cycle even if the explicit dependency graph remains acyclic.

Use `downstream_integration_obligations` for such deferred cross-system proofs when appropriate. Keep the child locally provable with representative/test-owned fixtures, and preserve parent requirement coverage by mapping the parent obligation to the downstream integration entry instead of falsely making unavailable future content a child completion prerequisite.

## GitHub coordination and decomposition closeout

When decomposition is selected as orchestrator work, use the GitHub Issue for the existing parent `NSC-###` contract. The Claim / Planned Approach must explicitly say:

```text
work_type: decomposition
```

Do not create a synthetic TaskGraph ID for decomposition activity.

If the run reaches `review_ready`, post a **Decomposition Closeout** with:

- worker ID;
- parent task ID/revision/source commit;
- canonical task checkout path;
- exact Downloads run path;
- provider and run ID;
- semantic decision;
- paths/identities of `decomposition_result.json` and `graph_delta.json` when present;
- concise proposed-child or blocker summary;
- explicit `review_only_not_applied` statement;
- required human/review/application next action.

A successful decomposition closeout does not mark the parent implementation delivered or conformant. While review-ready output awaits human review/application, keep the parent clearly reserved/marked so another generic orchestrator does not rerun the same parent contract/hash.

## CLI and proving commands

The production CLI requires a physically read-only source checkout:

```bash
python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider codex
```

`--task-id` and `--provider` are required. `--provider` is `claude` or `codex`; `--source` defaults to the repository root; `--output-root` defaults to `NSC_DECOMPOSITION_OUTPUT_ROOT` when set and otherwise to the sibling `<repository-parent>/NoSafeCircle-DecompositionOutputs` directory outside the checkout; and `--run-id` accepts an optional validated lowercase slug. That generic CLI default exists for tool-level use, but **real Windows task orchestration must not rely on it**. Set the host decomposition output root to `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\<TASK-ID>` before invoking Docker-backed D1B.1. Exit 0 means `review_ready`, exit 1 means `agent_failed` or `rejected`, and exit 2 means deterministic preflight blockage. Stdout is reserved for the final machine-readable run result and progress is written to stderr.

Compose keeps `/workspace` read-only and mounts `${NSC_DECOMPOSITION_HOST_OUTPUT_ROOT:-../NoSafeCircle-DecompositionOutputs}` at `/decomposition-output`. The fallback is a tool-level default, not the canonical operator path. For real task orchestration set `NSC_DECOMPOSITION_HOST_OUTPUT_ROOT` on the host to `Downloads\NoSafeCircleOutput\<TASK-ID>`. The `nosafecircle-m2a` project name intentionally reuses the existing authenticated Claude and Codex volumes.

Windows host setup example:

```powershell
$TaskId = "NSC-021"
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$OutputRoot = Join-Path $Downloads (Join-Path "NoSafeCircleOutput" $TaskId)
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT = $OutputRoot
```

Documented live proving commands (not run as part of D1B.1 implementation):

```bash
docker compose -p nosafecircle-m2a run --rm -T claude-decompose python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider claude
docker compose -p nosafecircle-m2a run --rm -T codex-decompose python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider codex
```

Stage D1B.2 independent verification and bounded refinement are not implemented. There is no decomposition verifier, refiner, or automatic provider retry inside D1B.1. Stage D1C graph application is also not implemented. Artifact Authority, artifact generation/GER, general GER, readiness, dispatch, candidate patches, automatic commits, and merges remain outside this package.
