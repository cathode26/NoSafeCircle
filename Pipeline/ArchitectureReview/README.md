# No Safe Circle Adversarial Architecture Review

This tool evaluates the autonomous-development architecture before the project commits to the next major pipeline direction.

It answers two questions in order:

1. Is the architecture fundamentally sound for autonomous Unity game development?
2. If it is sound, does it create enough near-term leverage to materially accelerate No Safe Circle development?

The review does **not** assume that the current milestone order, persistent work graph, `Tasks/*.yaml`, `taskcontrol`, reconciliation strategy, or verification strategy are correct merely because they already exist.

## Current Providers

Both Claude Code and OpenAI/Codex are active through generic AgentRuntime. Use `architecture_review_claude.py` for Claude and `architecture_review_codex.py` for Codex. Both paths map every reviewer, synthesis, and adversarial-critic invocation through `AgentInvocationRequest` and `AgentRunner`; the shared `architecture_review.py` owns schemas, exactly eight role definitions, prompts, and output helpers but does not launch a model directly.

Run these paths through `claude-review` and `codex-review`. Docker is the filesystem boundary: the repository is mounted read-only, while only `Pipeline/ArchitectureReview/outputs/` is writable. AgentRuntime grants neither provider repository-write nor approved-command-execution authority.

## Review Stages

A complete run uses three stages:

1. Eight independent reviewers run in parallel.
2. A synthesis agent evaluates their arguments without majority voting.
3. A fresh adversarial critic assumes the synthesis is wrong and tries to break it.

The independent roles are:

- Pragmatic Game Technical Director
- Workflow and Distributed-Systems Architect
- LLM Reliability Engineer
- Unity Production Engineer
- YAGNI and Complexity Critic
- Autonomous-Agent Architect
- Adversarial QA and Failure-Mode Reviewer
- Game Producer and Throughput Reviewer

## Important Review Framing

Architecture documents are treated as claims to verify, not authoritative answers.

Every reviewer is explicitly told to challenge:

- the current milestone order;
- `Tasks/*.yaml`, `taskcontrol`, and the persistent work graph;
- reconciliation and verification as currently framed;
- state and authority boundaries;
- whether the GDD's iterative nature requires a different synchronization model;
- whether infrastructure solves observed failures or hypothetical failures;
- whether a materially different architecture would be better;
- whether the pipeline will increase game-development throughput enough to justify its cost.

Reviewers are also told not to inspect prior or other-provider ArchitectureReview conclusions. When normal architecture or current-state documents contain historical review summaries, independent reviewers ignore the prior verdicts, recommendations, synthesis/adversarial conclusions, and vote/count summaries while still using implemented architecture, accepted decisions, and current primary evidence. They independently judge whether those facts and decisions are good or bad. Synthesis uses only its eight current-run reviews plus primary evidence; the adversarial critic uses only that current-run synthesis and reviews plus primary evidence. This preserves review provenance and supports a later Claude-versus-Codex comparison without implementing that comparison yet. Each provider retains all eight independent reviewer roles.

The target is not architectural elegance by itself. The system must be both technically sound and capable of increasing real gameplay-development throughput.

## Docker Setup

Build either review service from the repository root:

```powershell
docker compose build codex-review
```

```powershell
docker compose build claude-review
```

Codex authentication is persisted in the shared `codex-config` Docker volume. If login is required:

```powershell
docker compose run --rm codex codex login --device-auth
```

Check authentication:

```powershell
docker compose run --rm codex codex login status
```

Claude authentication uses the existing `claude-config` volume shared with the normal `claude` development service.

## Smoke Tests

Run the shared-contract and provider-adapter tests:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex_smoke_test.py
```

```powershell
docker compose run --rm claude-review python3 Pipeline/ArchitectureReview/architecture_review_claude_smoke_test.py
```

Run the deterministic resume/reuse test:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_resume_smoke_test.py
```

Run the small live structured-output test:

```powershell
docker compose run --rm -e NSC_RUN_OPENAI_CODEX_SMOKE=1 codex-review python3 Pipeline/ArchitectureReview/codex_provider_live_smoke_test.py
```

```powershell
docker compose run --rm -e NSC_RUN_ARCH_REVIEW_CLAUDE_SMOKE=1 claude-review python3 Pipeline/ArchitectureReview/claude_provider_live_smoke_test.py
```

## Run the Full Review

Each provider runs all eight independent reviewers. The default worker budget is eight; do not reduce it merely because a future launcher may run both providers concurrently:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py
```

```powershell
docker compose run --rm claude-review python3 Pipeline/ArchitectureReview/architecture_review_claude.py
```

The runner requires a clean working tree by default so every reviewer evaluates one frozen commit. To deliberately override that protection:

```powershell
docker compose run --rm -e ARCH_REVIEW_MAX_WORKERS=4 codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py --allow-dirty
```

A fixed model-assignment seed can be supplied for reproducibility:

```powershell
docker compose run --rm -e ARCH_REVIEW_MAX_WORKERS=4 codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py --seed 12345
```

## Resuming a Failed or Interrupted Run

Every completed reviewer is written immediately. If one reviewer, synthesis, or the final adversarial critique fails, successful work remains under the same run directory.

Resume with the run ID printed in the failure message or visible under `Pipeline/ArchitectureReview/outputs/codex/runs/`:

```powershell
docker compose run --rm -e ARCH_REVIEW_MAX_WORKERS=4 codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py --resume-run <run-id>
```

The resume command:

- reuses valid completed reviewer outputs;
- reruns only missing or invalid reviewers;
- reuses a completed synthesis;
- reruns only the adversarial critique if that is the missing stage;
- refuses to resume if the checked-out Git commit differs from the run's frozen commit;
- refuses to resume a run owned by a different provider namespace;
- preserves prior failures in `failure_history.json`.

Do not begin a new run after a partial failure unless a deliberately fresh independent review is desired.

## Model and Reasoning Configuration

Default model:

```text
gpt-5.6-sol
```

Reasoning defaults:

```text
independent reviewers: high
synthesis:             max
adversarial critique:  max
```

Environment variables:

```text
ARCH_REVIEW_MODELS
ARCH_REVIEW_SYNTHESIS_MODEL
ARCH_REVIEW_ADVERSARY_MODEL
ARCH_REVIEW_REASONING_EFFORT
ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT
ARCH_REVIEW_ADVERSARY_REASONING_EFFORT
ARCH_REVIEW_MAX_WORKERS
ARCH_REVIEW_TIMEOUT_SECONDS
```

Codex does not expose Claude's `--max-turns` control. Each agent is bounded by the runner's subprocess timeout and provider usage controls.

## Outputs

Each provider owns its run and latest-complete output under:

```text
Pipeline/ArchitectureReview/outputs/
  claude/
    runs/<run-id>/
    latest/
  codex/
    runs/<run-id>/
    latest/
  latest/
```

The AgentRuntime-backed Claude path uses `claude`; the AgentRuntime-backed OpenAI path uses `codex`. Every manifest records `provider_namespace`, and resume remains within that namespace. Comparison and dual-provider orchestration remain future work.

Contents include:

```text
manifest.json
model_assignments.json
failure_history.json            # only when a stage has failed
agent_runtime/
  <unique-invocation-id>/
    request.json
    provider.log
    result.json
reviews/
  adversarial_qa.json
  autonomous_agent_architect.json
  game_producer.json
  game_technical_director.json
  llm_reliability_engineer.json
  unity_production_engineer.json
  workflow_systems_architect.json
  yagni_complexity_critic.json
synthesis.json
adversarial_critique.json
```

Each provider's latest completed synthesis and critique are copied to its `latest/` directory. A single atomic pointer to the most recently completed run regardless of provider is published at:

```text
Pipeline/ArchitectureReview/outputs/latest/LATEST.json
```

Each provider-specific latest directory contains `LATEST.json`, `synthesis.json`, and `adversarial_critique.json`. The global `latest/` directory contains only `LATEST.json`, whose `provider_namespace`, `run_id`, `run_path`, and `frozen_head` identify one immutable provider-scoped completed run; consumers follow `run_path` for its synthesis and adversarial critique. Failed or partial runs never update these convenience views. Accepted historical evidence remains separately under `Pipeline/ArchitectureReview/evidence/` and is not moved with generated output.

Generated outputs are ignored by Git by default. Each result records the provider, selected model, reasoning effort, and duration.

## Interpreting the Verdict

The structured architecture verdict classes are:

- `sound_high_leverage`
- `sound_overbuilt`
- `partially_unsound`
- `fundamentally_wrong_approach`
- `insufficient_evidence`

These are not votes. The synthesis weighs evidence and arguments, including strong minority arguments.

The final adversarial critic then classifies the synthesis as:

- `synthesis_holds`
- `synthesis_needs_revision`
- `synthesis_is_unsafe`

Human judgment remains the final architectural authority.
