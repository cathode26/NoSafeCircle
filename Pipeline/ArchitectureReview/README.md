# No Safe Circle Adversarial Architecture Review

This tool evaluates the autonomous-development architecture before the project commits to the next major pipeline direction.

It is designed to answer two questions in order:

1. Is the architecture fundamentally sound for autonomous Unity game development?
2. If it is sound, does it create enough near-term leverage to materially accelerate No Safe Circle development?

The review does **not** assume that the current milestone order, Work Graph Seeder, `Tasks/*.yaml`, `taskcontrol`, reconciliation strategy, or verification strategy are correct merely because they already exist.

## Current Provider

The active review path uses **OpenAI Codex CLI authenticated with the user's ChatGPT account**.

The original Claude runner remains in `architecture_review.py` because the shared review schemas, prompts, role definitions, synthesis logic, and output orchestration live there. `architecture_review_codex.py` imports that shared contract and swaps only the model/provider invocation.

Run the Codex path through the Docker `codex-review` service. Docker is the security boundary: the repository is mounted read-only, while only `Pipeline/ArchitectureReview/outputs/` is writable. Codex therefore runs with its nested sandbox disabled (`danger-full-access`) so Linux bubblewrap/user-namespace restrictions inside Docker do not block repository inspection.

## Review Stages

A run uses three stages:

1. Eight independent reviewers run in parallel.
2. A synthesis agent evaluates the arguments without majority voting.
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
- `Tasks/*.yaml` / `taskcontrol` and the persistent work graph;
- reconciliation and verification as currently framed;
- state and authority boundaries;
- whether the GDD's iterative nature requires a different synchronization model;
- whether infrastructure is solving observed failures or hypothetical failures;
- whether a materially different architecture would be better;
- whether the pipeline will actually increase game-development throughput enough to justify its cost.

The target outcome is not architectural elegance by itself. The desired system must be both technically sound and capable of increasing real gameplay-development throughput.

## Docker Setup

Build the review service from the repository root:

```powershell
docker compose build codex-review
```

Codex authentication is persisted in the shared `codex-config` Docker volume. If login is required:

```powershell
docker compose run --rm codex codex login --device-auth
```

Check authentication:

```powershell
docker compose run --rm codex codex login status
```

## Smoke Tests

The original shared-contract smoke test remains available:

```powershell
docker compose run --rm codex-review python Pipeline/ArchitectureReview/architecture_review_smoke_test.py
```

Run the Codex-provider smoke test:

```powershell
docker compose run --rm codex-review python Pipeline/ArchitectureReview/architecture_review_codex_smoke_test.py
```

These tests are deterministic and do not spend model tokens.

## Small Codex Repository Test

Before a large review, this command verifies that Codex can inspect the read-only repository from inside Docker:

```powershell
docker compose run --rm codex-review codex exec --ephemeral --sandbox danger-full-access "Read AI_PIPELINE.md and summarize the goal of this repository's AI pipeline in one sentence."
```

`danger-full-access` here disables Codex's nested Linux sandbox only. Docker still mounts the project repository read-only for the `codex-review` service.

## Run the Full Review

From the repository root:

```powershell
docker compose run --rm codex-review python Pipeline/ArchitectureReview/architecture_review_codex.py
```

The runner requires a clean working tree by default so every reviewer evaluates one frozen commit. To deliberately override that protection:

```powershell
docker compose run --rm codex-review python Pipeline/ArchitectureReview/architecture_review_codex.py --allow-dirty
```

A fixed model-assignment seed can be supplied for reproducibility:

```powershell
docker compose run --rm codex-review python Pipeline/ArchitectureReview/architecture_review_codex.py --seed 12345
```

## Model and Reasoning Configuration

Default independent-review model pool:

```text
gpt-5.6-sol
```

Default synthesis model:

```text
gpt-5.6-sol
```

Default adversarial-critique model:

```text
gpt-5.6-sol
```

Reasoning defaults are intentionally stronger than a casual Codex invocation:

```text
independent reviewers: high
synthesis:             xhigh
adversarial critique:  xhigh
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

Example PowerShell configuration:

```powershell
$env:ARCH_REVIEW_REASONING_EFFORT="high"; $env:ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT="xhigh"; $env:ARCH_REVIEW_ADVERSARY_REASONING_EFFORT="xhigh"; docker compose run --rm -e ARCH_REVIEW_REASONING_EFFORT -e ARCH_REVIEW_SYNTHESIS_REASONING_EFFORT -e ARCH_REVIEW_ADVERSARY_REASONING_EFFORT codex-review python Pipeline/ArchitectureReview/architecture_review_codex.py
```

The original Claude `--max-turns` controls do not have a direct Codex equivalent. Codex runs are bounded by the runner's subprocess timeout and by ChatGPT/Codex usage limits.

## Outputs

Each run creates immutable output under:

```text
Pipeline/ArchitectureReview/outputs/runs/<run-id>/
```

Contents include:

```text
manifest.json
model_assignments.json
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

The latest completed synthesis and critique are copied to:

```text
Pipeline/ArchitectureReview/outputs/current/
```

Each Codex result also records the provider, selected model, reasoning effort, and duration.

## Interpreting the Verdict

The structured verdict classes are:

- `sound_high_leverage`
- `sound_overbuilt`
- `partially_unsound`
- `fundamentally_wrong_approach`
- `insufficient_evidence`

These are not votes. The synthesis is instructed to weigh evidence and arguments, including strong minority arguments.

The final adversarial critic then classifies the synthesis as:

- `synthesis_holds`
- `synthesis_needs_revision`
- `synthesis_is_unsafe`

Human judgment remains the final architectural authority.
