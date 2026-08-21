# No Safe Circle Adversarial Architecture Review

This tool evaluates the autonomous-development architecture before the project commits to the next infrastructure milestone.

It is designed to answer two questions in order:

1. Is the architecture fundamentally sound for autonomous Unity game development?
2. If it is sound, does it create enough near-term leverage to materially accelerate No Safe Circle development?

The review does **not** assume that the current milestone order, Work Graph Seeder, `Tasks/*.yaml`, or `taskcontrol` are correct next steps.

## Review Stages

A run uses three stages:

1. Eight independent read-only reviewers run in parallel.
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

All first-pass reviewers are read-only and can inspect the repository with Claude Code `Read`, `Glob`, and `Grep` tools. They cannot edit files, run Bash, or use web tools.

## Important Review Framing

Architecture documents are treated as claims to verify, not authoritative answers.

Every reviewer is explicitly told to challenge:

- the current milestone order;
- the Work Graph Seeder / `Tasks/*.yaml` / `taskcontrol` proposal;
- reconciliation and verification as currently framed;
- state and authority boundaries;
- whether the GDD's iterative nature requires a different synchronization model;
- whether infrastructure is solving observed failures or hypothetical failures;
- whether a materially different architecture would be better.

The target outcome is not architectural elegance by itself. The desired system must be both sound and capable of increasing real gameplay-development throughput.

## Run

From the repository root:

```powershell
python Pipeline/ArchitectureReview/architecture_review.py
```

The runner requires a clean working tree by default so every reviewer evaluates a frozen commit. To override that protection deliberately:

```powershell
python Pipeline/ArchitectureReview/architecture_review.py --allow-dirty
```

A fixed model-assignment seed can be supplied for reproducibility:

```powershell
python Pipeline/ArchitectureReview/architecture_review.py --seed 12345
```

## Model Configuration

Default independent-review model pool:

```text
opus,sonnet
```

Default synthesis model:

```text
opus
```

Default adversarial-critique model:

```text
opus
```

Environment variables:

```text
ARCH_REVIEW_MODELS
ARCH_REVIEW_SYNTHESIS_MODEL
ARCH_REVIEW_ADVERSARY_MODEL
ARCH_REVIEW_MAX_WORKERS
ARCH_REVIEW_TIMEOUT_SECONDS
ARCH_REVIEW_MAX_TURNS
ARCH_REVIEW_SYNTHESIS_MAX_TURNS
ARCH_REVIEW_ADVERSARY_MAX_TURNS
```

Example PowerShell configuration:

```powershell
$env:ARCH_REVIEW_MODELS="opus,sonnet"; $env:ARCH_REVIEW_SYNTHESIS_MODEL="opus"; $env:ARCH_REVIEW_ADVERSARY_MODEL="opus"; python Pipeline/ArchitectureReview/architecture_review.py
```

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

The manifest records the exact Git commit, model pool, model assignments, seed, timestamps, and review roles.

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
