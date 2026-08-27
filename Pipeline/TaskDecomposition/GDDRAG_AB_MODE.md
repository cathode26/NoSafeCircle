# D1B.2 GDDRAG Reviewer A/B Mode

This document describes the opt-in reviewer-context experiment implemented by `run_round_robin_decomposition_rag.py`.

## Purpose

The normal D1B.2 runner remains the production baseline and embeds the full current committed GDD in both generator and reviewer context. The GDDRAG A/B runner changes only the reviewer's GDD payload so reviewer token/context cost and semantic output can be compared without changing generator behavior at the same time.

## A/B behavior

In GDDRAG A/B mode:

- the task decomposer/generator receives the same full deterministic D1B.2 context as the baseline runner;
- before any provider call, the committed production GDDRAG index must validate as current against `Docs/GDD/No_Safe_Circle_GDD.md`;
- reviewer retrieval queries are derived deterministically from parent AC/VAL/INT requirements, the current candidate's children, inbound dependency rewrites, and unresolved findings;
- retrieved chunks are deduplicated and bounded by configured chunk/text caps;
- the reviewer receives authoritative non-GDD decomposition context plus the bounded current GDDRAG navigation hints instead of embedding the entire GDD text;
- retrieval hits retain canonical source-line attribution and text hashes;
- retrieval is advisory navigation, not independent authority: a missing top-k hit is never proof that canon contains no relevant rule;
- repository read/search access remains available to the reviewer when the bounded hints are insufficient;
- each reviewer round publishes an immutable `NN-gdd-rag-review-context.json` artifact and the run publishes `gdd_rag_ab_manifest.json`;
- all decomposition output remains `review_only_not_applied` and Stage D1C graph application remains separate.

The default non-RAG D1B.2 runner is intentionally unchanged.

## Production RAG freshness

The committed index is:

`Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`

After any canonical GDD change, rebuild and validate it before using A/B mode:

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/tests/retrieval_regression_test.py
```

If pinned retrieval expectations change after a legitimate GDD edit, inspect every changed result in one pass before updating the strict baseline:

```text
python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline
```

Do not automatically accept new chunk IDs. Review the returned canonical text and source lines first, then deliberately update the pinned regression baseline.

A stale or invalid index causes the A/B runner to fail before any provider call so a Codex generation call is not wasted.

## A/B command

For a Windows orchestration checkout, set the canonical host output root exactly as for normal D1B.2, then run through the existing dual-provider Compose service:

```text
docker compose -p nosafecircle-m2a run --rm -T round-robin-decompose python3 Pipeline/TaskDecomposition/run_round_robin_decomposition_rag.py --task-id NSC-016 --providers codex,claude --max-calls 4
```

The same Claude and Codex authentication volumes used by normal D1B.2 are mounted by `round-robin-decompose`.

## Comparison metrics

For an A/B proving task, compare the full-context baseline and RAG-assisted run on:

- calls used and final status/verdict;
- proposed children and inbound dependency rewrites;
- findings and semantic conclusions;
- reviewer request size;
- provider token accounting and cache usage when surfaced;
- duration and provider-reported cost when surfaced;
- retrieved chunk count/text size and source coverage;
- whether known cross-task ownership/locality conclusions remain correct.

The experiment is useful only if semantic quality is preserved. Token reduction alone is not sufficient justification for replacing the full-context reviewer mode.
