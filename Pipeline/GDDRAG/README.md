# GDD RAG — Production GDD Retrieval

`Pipeline/GDDRAG` is the deterministic, hash-verified production retrieval layer for the current canonical GDD at `Docs/GDD/No_Safe_Circle_GDD.md`. It is separate from the historical Assignment 4 knowledge base and never falls back to that older data.

## Current production state

The current canonical GDD was revised August 25, 2026. Rebuilding the production index from that document yields **78 deterministic chunks**. The chunk count is emergent from the Markdown structure and may change again when the canonical GDD changes.

The index is written to:

```text
Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json
```

The currently reviewed source SHA-256 is:

```text
c26d5077ccdc2e8408129fef2d3571758777b29f99241d8aed1b39d73ea3e1a6
```

Do not treat that hash or the 78-chunk count as permanent constants. `gddctl.py status` and `validate` are the authority for freshness.

## Commands

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py status
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/gddctl.py search "<query>"
python Pipeline/GDDRAG/gddctl.py search "<query>" --json
```

No GDDRAG command calls an LLM or external API. Retrieval and index construction are deterministic local computation over the canonical Markdown.

## Required rebuild workflow after a GDD change

After any committed change to `Docs/GDD/No_Safe_Circle_GDD.md`:

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/tests/gdd_rag_smoke_test.py
python Pipeline/GDDRAG/tests/integrity_regression_test.py
python Pipeline/GDDRAG/tests/retrieval_regression_test.py
```

A normal retrieval-regression failure immediately after a legitimate GDD change does **not** automatically mean the retriever is defective. The strict regression test pins reviewed top hits from the previous canonical GDD state so retrieval drift cannot be silently accepted.

If the strict retrieval test reports changed pinned results, inspect all drift at once:

```text
python Pipeline/GDDRAG/tests/retrieval_regression_test.py --review-baseline
```

That inspection mode is read-only. It prints every pinned query with its previous and current top hit, source lines, top-three chunk IDs, and full current top-hit text. Review every changed result against current canon. If and only if the new hits are semantically correct, deliberately update `EXPECTED_TOP_HITS` in `tests/retrieval_regression_test.py` and rerun the strict test.

Never automatically rewrite pinned expectations merely because `rebuild` changed chunk IDs. See `Pipeline/GDDRAG/BASELINE_REVIEW.md` for the full operator rule.

Commit the regenerated knowledge-base JSON and any deliberately reviewed baseline update together with, or immediately after, the canonical GDD revision that caused them.

## Freshness and integrity boundary

`gddctl.py status` reports the canonical GDD path, current source SHA-256, indexed source SHA-256, chunk count, and `CURRENT`, `STALE`, or `MISSING` state.

`gddctl.py validate` fails when the index is stale or structurally invalid, including source-hash mismatch, invalid chunk counts/IDs, bad source ranges, wrong source paths, missing required fields, or indexed text that no longer matches the canonical source lines.

`search` performs the same freshness/integrity validation before retrieval and refuses to serve a stale index.

## Chunking

`index_builder.py` uses deterministic Markdown heading/table/list structure. Each chunk records a source line range into the canonical GDD. Large content is split only at deterministic structural boundaries; tables are not split through rows and list items are not split internally. There is no hand-authored entity or keyword metadata in the production index.

Two rebuilds from identical canonical input produce byte-identical index output. No timestamps or provider-generated metadata are written into the index.

## Retriever

`retrieval.py` uses deterministic tokenization/stemming, weighted field scoring over title/section/subsection/text, phrase matching, query-coverage scoring, and stable `(-score, chunk_id)` result ordering.

The production retriever intentionally has no LLM ranking stage. A broad ownership table can sometimes outrank a narrower prose section when it contains the relevant terms at higher density. The pinned regression suite exists so those ranking outcomes are reviewed deliberately when canon changes.

## Current reviewed regression baseline

Against the August 25, 2026 canonical GDD, the reviewed top hits are:

| Query | Reviewed top hit |
|---|---|
| mouse-directed movement and cursor-to-gameplay-plane projection | `nsc-gdd-007` |
| Charged Fireball movement restriction ownership | `nsc-gdd-063` |
| Frost Field cursor placement and Ranged Enemy limitation | `nsc-gdd-062` |
| door click-to-approach and automatic five-second timer | `nsc-gdd-062` |
| locked-door break and forward enemy pursuit | `nsc-gdd-055` |
| floor restart owner-controlled reset entry points | `nsc-gdd-074` |
| victory suspend/re-enable ownership | `nsc-gdd-064` |
| Active Enemy Registry fifteen-enemy cap | `nsc-gdd-056` |
| fixed isometric camera requirements | `nsc-gdd-071` |
| Windows build and canonical scene registration | `nsc-gdd-076` |

These IDs are a reviewed regression baseline for the current canonical GDD, not permanent semantic identifiers.

## D1B.2 reviewer-context experiment

The opt-in D1B.2 GDDRAG A/B path uses this production index only after freshness/integrity validation succeeds. In the experiment mode, the decomposition generator retains the normal full context while reviewer rounds omit the embedded full-GDD text and receive bounded, deduplicated, source-attributed GDDRAG navigation hints instead.

RAG results remain navigation hints, not independent authority. The canonical GDD remains authoritative; a missing retrieved chunk is never proof that a rule does not exist. Reviewer repository read/search remains available when retrieved hints are insufficient.

The default full-context D1B.2 path remains unchanged so token cost, duration, findings, and semantic output can be compared directly.

## Historical Assignment 4 relationship

`DynamicContentPipeline` is a completed historical course project whose older manually curated knowledge base came from a prior GDD revision. Production GDDRAG reuses the proven deterministic retrieval approach but builds its own index directly from current canonical Markdown. It does not import or read the historical knowledge base at runtime.
