# D1B.2 GDDRAG Reviewer A/B Mode

This document describes the opt-in D1B.2 reviewer-context experiments on this branch. They remain review-only and do not apply a decomposition to TaskGraph.

## Two experiment modes

### End-to-end exploratory mode

`run_round_robin_decomposition_rag.py` runs a fresh Codex generation and then uses bounded GDDRAG context for reviewer rounds. It is useful for proving that the complete D1B.2 loop works with RAG, but it is not a controlled efficiency benchmark because a fresh generator candidate can be easier or harder to review than an earlier baseline candidate.

### Controlled reviewer replay

`run_reviewer_replay_ab.py` removes generator variance. It loads one immutable, already-generated decomposition candidate, validates it against the current task contract and graph, and sends that exact candidate to the same reviewer model twice:

```text
same validated candidate
├── full committed GDD reviewer prompt
└── bounded current GDDRAG reviewer prompt
```

No Codex generator call occurs. Both arms use:

- the same candidate semantic SHA-256;
- the same current source checkout, TaskGraph, task contract, and canonical GDD;
- the same reviewer provider/model configuration;
- the same review schema, semantic rubric, round number, and empty prior-finding history;
- the same read-only repository capabilities and budgets.

Only the reviewer GDD context strategy differs.

The harness rejects the comparison if the two arms do not use the same actual provider, model, or candidate SHA.

## Controlled replay command

The original successful NSC-016 no-RAG run wrote its round-one candidate to:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-016\20260826-222752\rounds\01\candidate.json
```

Inside the Docker service, the same file is visible at:

```text
/decomposition-output/20260826-222752/rounds/01/candidate.json
```

Its expected semantic candidate SHA-256 is:

```text
6d7f99635650aa013461f75291f4591f0a08d8d6de9f93259e1e4417e03e11ce
```

Run the controlled replay from the RAG branch checkout through the existing dual-provider service:

```text
python3 Pipeline/TaskDecomposition/run_reviewer_replay_ab.py \
  --task-id NSC-016 \
  --candidate /decomposition-output/20260826-222752/rounds/01/candidate.json \
  --expected-candidate-sha256 6d7f99635650aa013461f75291f4591f0a08d8d6de9f93259e1e4417e03e11ce \
  --candidate-author-provider codex \
  --reviewer-provider claude \
  --arm-order full,rag
```

The Windows operator should invoke that through:

```text
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose <command above>
```

`NSC_DECOMPOSITION_HOST_OUTPUT_ROOT` must point to:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-016
```

The run creates a new immutable directory under that root and writes:

```text
reviewer_replay_result.json
replay_request.json
reviewed_candidate.json
reviewed_candidate_identity.json
reviewed_candidate_graph_delta.json
progress.jsonl
arms/full/review_request.json
arms/full/review.json
arms/full/arm_result.json
arms/full/rounds/02/...
arms/rag/review_request.json
arms/rag/gdd_rag_review_context.json
arms/rag/review.json
arms/rag/arm_result.json
arms/rag/rounds/02/...
```

The harness never emits `decomposition_result.json` or applies a graph delta. It is an experiment, not decomposition approval.

## Arm order and residual variance

The default arm order is `full,rag`. A sequential two-call replay still has possible provider stochasticity and cache/order effects. The result records the exact order and explicitly warns about this limitation.

For a stronger latency/cache check, run a second controlled replay with:

```text
--arm-order rag,full
```

The candidate, reviewer model, schema, and source context remain fixed in both runs.

## Comparison result

`reviewer_replay_result.json` records:

- candidate semantic SHA and input-file byte SHA;
- exact source and context identities;
- actual provider and model for each arm;
- prompt UTF-8 byte count and SHA-256;
- verdict, findings, unresolved findings, and any deterministically validated revised candidate;
- AgentResult aggregate input/output/total tokens and estimated cost when available;
- provider-reported duration, orchestration duration, and wall duration;
- absolute and percentage RAG-versus-full deltas;
- whether verdicts, finding categories, and revised candidate identities match.

Provider-specific cache-creation and cache-read detail remains available in each arm's raw AgentRuntime result/log artifacts even when the normalized AgentResult only exposes aggregate token usage.

## Production RAG freshness

The committed index is:

```text
Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json
```

Before either RAG experiment spends a provider call, the production index must be current and valid against `Docs/GDD/No_Safe_Circle_GDD.md`.

After a canonical GDD change:

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/tests/gdd_rag_smoke_test.py
python Pipeline/GDDRAG/tests/integrity_regression_test.py
python Pipeline/GDDRAG/tests/retrieval_regression_test.py
```

If pinned retrieval expectations move after a legitimate GDD edit, inspect all drift before updating the strict baseline:

```text
python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline
```

Do not automatically accept new chunk IDs.

## RAG authority boundary

The RAG arm receives:

- authoritative task contracts and TaskGraph context;
- the exact candidate and graph-delta review view;
- selected-task GDD evidence;
- canonical GDD path and committed hash;
- bounded current-index GDDRAG navigation hints;
- repository read/search access for unanswered blocking questions.

The full GDD text alone is omitted from the RAG prompt. Retrieved chunks are non-exhaustive navigation hints, not independent authority. A missing retrieval result never proves a canon rule does not exist.

All output remains:

```text
review_only_not_applied
```

The experiment is successful only if semantic quality is preserved. Token reduction alone is not sufficient justification for merging or adopting the RAG reviewer mode.
