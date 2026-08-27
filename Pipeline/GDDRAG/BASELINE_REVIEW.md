# GDDRAG Retrieval Baseline Review

The production GDDRAG index is rebuilt deterministically from `Docs/GDD/No_Safe_Circle_GDD.md`. A legitimate GDD edit can change heading boundaries, chunk count, chunk IDs, and retrieval ranking even when the retriever itself is still correct.

`Pipeline/GDDRAG/tests/retrieval_regression_test.py` intentionally pins a small set of representative current-GDD queries. Its normal mode is strict: if any pinned top hit changes, the test fails. Do not weaken or automatically rewrite that baseline.

## After a canonical GDD change

Run:

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/tests/gdd_rag_smoke_test.py
python Pipeline/GDDRAG/tests/integrity_regression_test.py
python Pipeline/GDDRAG/tests/retrieval_regression_test.py
```

If only the pinned retrieval regression fails after the rebuilt index passes freshness, smoke, and integrity checks, inspect all pinned changes at once:

```text
python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline
```

For machine-readable output:

```text
python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline --json
```

The review mode is read-only. It prints the previous pinned chunk ID, current top chunk ID, source line range, top-three chunk IDs, and full current top-hit text for every changed query. It exits successfully so the operator can inspect the complete drift set without repeatedly failing one query at a time.

## Decision rule

For every changed pinned query:

1. Read the current top-hit text and source line range.
2. Confirm it is semantically appropriate for the query under the current canonical GDD.
3. Compare the next two hits when the top result is broad or surprising.
4. If the new ranking is correct, deliberately update `EXPECTED_TOP_HITS` in `retrieval_regression_test.py`.
5. If the new ranking is wrong, fix or tune the retriever/indexing behavior instead of changing the expected ID.
6. Rerun the normal strict regression test.

Never accept a new chunk ID solely because the GDD was rebuilt. Chunk renumbering is expected after structural GDD growth, but semantic relevance must still be reviewed.

## Commit boundary

When the baseline legitimately changes, commit these together:

- the canonical GDD change, when it is part of the same work;
- the rebuilt `Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`;
- the deliberately refreshed pinned retrieval baseline;
- any documentation that records a materially changed retrieval behavior.

The committed index must pass `gddctl validate`. A stale or invalid index must never be used by downstream RAG-assisted pipeline work.

## Why this is intentionally strict

The pinned regression is a semantic tripwire, not a claim that chunk IDs are permanent identities. It prevents a GDD edit from silently changing retrieval behavior. The review mode makes that tripwire operationally cheap by showing all drift in one pass rather than requiring fail-edit-rerun cycles.
