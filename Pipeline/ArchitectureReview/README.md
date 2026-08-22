# No Safe Circle Adversarial Architecture Review

This tool evaluates the autonomous-development architecture before the project commits to the next major pipeline direction.

It answers two questions in order:

1. Is the architecture fundamentally sound for autonomous Unity game development?
2. If it is sound, does it create enough near-term leverage to materially accelerate No Safe Circle development?

The review does **not** assume that the current milestone order, persistent work graph, `Tasks/*.yaml`, `taskcontrol`, reconciliation strategy, or verification strategy are correct merely because they already exist.

## Current Provider

The active review path uses **OpenAI Codex CLI authenticated with the user's ChatGPT account**.

The original Claude runner remains in `architecture_review.py` because the shared schemas, prompts, role definitions, and output contract live there. `architecture_review_codex.py` swaps in Codex and delegates stage execution to the resumable orchestrator in `architecture_review_resume.py`.

Run the Codex path through the Docker `codex-review` service. Docker is the security boundary: the repository is mounted read-only, while only `Pipeline/ArchitectureReview/outputs/` is writable. Codex therefore runs with its nested sandbox disabled (`danger-full-access`) so container sandbox restrictions do not block repository inspection.

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

The target is not architectural elegance by itself. The system must be both technically sound and capable of increasing real gameplay-development throughput.

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

Run the shared-contract and Codex-provider tests:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex_smoke_test.py
```

Run the deterministic resume/reuse test:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/architecture_review_resume_smoke_test.py
```

Run the small live structured-output test:

```powershell
docker compose run --rm codex-review python3 Pipeline/ArchitectureReview/codex_provider_live_smoke_test.py
```

## Run the Full Review

The recommended first production run uses four concurrent reviewers. It still runs all eight roles, in two waves, reducing the chance that a burst failure loses progress:

```powershell
docker compose run --rm -e ARCH_REVIEW_MAX_WORKERS=4 codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py
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

Resume with the run ID printed in the failure message or visible under `Pipeline/ArchitectureReview/outputs/runs/`:

```powershell
docker compose run --rm -e ARCH_REVIEW_MAX_WORKERS=4 codex-review python3 Pipeline/ArchitectureReview/architecture_review_codex.py --resume-run <run-id>
```

The resume command:

- reuses valid completed reviewer outputs;
- reruns only missing or invalid reviewers;
- reuses a completed synthesis;
- reruns only the adversarial critique if that is the missing stage;
- refuses to resume if the checked-out Git commit differs from the run's frozen commit;
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

Each run creates immutable output under:

```text
Pipeline/ArchitectureReview/outputs/runs/<run-id>/
```

Contents include:

```text
manifest.json
model_assignments.json
failure_history.json            # only when a stage has failed
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
