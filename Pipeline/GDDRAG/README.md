# GDD RAG — Production GDD Retrieval

This is Milestone 2A1: extracting the proven Assignment 4 GDD retrieval approach into a
standalone, hash-verified production tool that indexes the **current** canonical GDD
Markdown, not the historical Assignment 4 knowledge base.

## Why this was extracted

`DynamicContentPipeline` (Assignment 4) is a completed historical course project. Its
knowledge base (`DynamicContentPipeline/knowledge_base/No_Safe_Circle_GDD_RAG.json`) was
built from the **July 30, 2026** GDD and is stale relative to the current canonical
Markdown at `Docs/GDD/No_Safe_Circle_GDD.md` (revised August 21, 2026). Its 39 chunks were
also manually curated (hand-written titles, entities, and keywords), which is not
something the current pipeline can regenerate deterministically without an LLM.

Milestone 2 (`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`) calls for reusing the Assignment
4 retrieval approach rather than rebuilding RAG from scratch, and for local tools to answer
factual GDD questions without spending LLM tokens. This tool satisfies both: it copies and
adapts the proven deterministic tokenizer/scoring behavior from
`DynamicContentPipeline/retrieval.py`, but builds its own chunk index directly and
deterministically from the current canonical Markdown, so it always reflects the GDD that
is actually in the repository.

`DynamicContentPipeline` is left untouched. This tool never imports it and never reads its
knowledge base at runtime (`gdd_rag_smoke_test.py` asserts this).

## Commands

```text
python Pipeline/GDDRAG/gddctl.py rebuild
python Pipeline/GDDRAG/gddctl.py status
python Pipeline/GDDRAG/gddctl.py validate
python Pipeline/GDDRAG/gddctl.py search "<query>"
python Pipeline/GDDRAG/gddctl.py search "<query>" --json
```

`--knowledge-base <path>` (before the subcommand) points every command at an alternate
index file; it defaults to `Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`.

No command in this tool calls an LLM or any external API. Everything is deterministic
local computation over the canonical Markdown file.

## Rebuild workflow

Run `rebuild` after any change to `Docs/GDD/No_Safe_Circle_GDD.md`:

```text
python Pipeline/GDDRAG/gddctl.py rebuild
```

This reads the canonical Markdown, computes its SHA-256, parses it into deterministic
structural chunks, and writes
`Pipeline/GDDRAG/knowledge_base/No_Safe_Circle_GDD_RAG.json`. Two rebuilds from an
unchanged source produce byte-identical output (`gdd_rag_smoke_test.py` proves this) — no
timestamps or other nondeterministic values are written into the index.

Commit the regenerated `knowledge_base/No_Safe_Circle_GDD_RAG.json` alongside any GDD
change, the same way `DynamicContentPipeline` commits its own knowledge base.

## Chunking approach

`index_builder.py` parses the canonical Markdown's own heading structure (`#`, `##`,
`###`) rather than manually curating a fixed chunk count:

- Each heading's own content — the text before its next heading of any level — becomes one
  chunk, tagged with `title`, `section` (nearest `##` ancestor), `subsection` (the `###`
  heading itself, if any), and the full `heading_path` from the document title down.
- A chunk larger than `max_chunk_chars` (3200) is split, but only at deterministic
  paragraph/list-item boundaries:
  - **Tables** (contiguous `|`-prefixed lines) are never split, even if they exceed the
    size cap, so a table's rows are never left structurally broken. (`Development Agent
    Roles`, an ~5.4k-character table, is intentionally kept as one oversized chunk.)
  - **Lists** are split between bullet items, never through one — each split-off chunk
    holds whole bullets only.
  - A single physical paragraph line has no smaller deterministic boundary and is kept
    whole even if it exceeds the cap; this has not occurred with the current GDD.
- Rebuilding against the current GDD produces 41 chunks. This number is emergent from the
  document's own structure, not a target.

Each chunk records `source.start_line` / `source.end_line` (1-indexed, inclusive) into
`Docs/GDD/No_Safe_Circle_GDD.md`, so any result can be traced back to the exact canonical
text it came from.

## Schema (`schema_version: "2.0"`)

```json
{
  "schema_version": "2.0",
  "generator": {"name": "...", "version": "..."},
  "source": {"file": "Docs/GDD/No_Safe_Circle_GDD.md", "sha256": "<hex>"},
  "document": {
    "document_id": "...", "title": "...", "document_type": "...", "status": "...",
    "author": "...", "original_date": "...", "revised_date": "...", "source_docx": "...",
    "canonical_markdown": "Docs/GDD/No_Safe_Circle_GDD.md", "language": "en",
    "total_chunks": 41
  },
  "chunking": {"strategy": "...", "max_chunk_chars": 3200, "overlap": 0, "recommended_top_k": 4, "recommended_search_fields": [...]},
  "retrieval_guidance": {"canonicality_rule": "...", "default_filter": {"domain": "game_design", "canonical": true}},
  "chunks": [
    {
      "chunk_id": "nsc-gdd-001",
      "order": 1,
      "title": "...",
      "section": "... or null",
      "subsection": "... or null",
      "heading_path": ["No Safe Circle", "..."],
      "domain": "game_design",
      "canonical": true,
      "source": {"file": "Docs/GDD/No_Safe_Circle_GDD.md", "start_line": 21, "end_line": 36},
      "chunk_part": {"index": 1, "count": 2} ,
      "text": "...",
      "char_count": 1852,
      "sha256": "<hex>"
    }
  ]
}
```

`chunk_part` is `null` for chunks that are not part of a section split into multiple
pieces.

## Freshness behavior

`status` reports the canonical GDD path, the current source SHA-256, the indexed source
SHA-256, the chunk count, and `CURRENT` or `STALE` (or `MISSING` if no index has been built
yet).

`validate` fails (non-zero exit) when:

- the indexed source SHA-256 does not match the current GDD's SHA-256 (stale index);
- `document.total_chunks` does not match the actual chunk count;
- any `chunk_id` is duplicated;
- any chunk's `source.start_line`/`end_line` is missing, non-integer, or invalid
  (`end_line < start_line`, etc.);
- any chunk's `source.file` is not the canonical GDD path;
- any chunk is missing a required field (`chunk_id`, `title`, `text`, `domain`,
  `canonical`, `source`).

`search` runs the same validation before retrieving anything and refuses to return results
on a stale or structurally invalid index — it never falls back to the historical
Assignment 4 knowledge base.

## Retriever

`retrieval.py` is adapted from `DynamicContentPipeline/retrieval.py`: the same deterministic
stemmer/tokenizer, BM25-style weighted field scoring (`title`/`section`/`subsection`/`text`),
phrase (n-gram) matching, query-coverage scoring, and stable `(-score, chunk_id)` result
ordering. The historical `entities`/`keywords` fields and their scoring boosts were dropped
because this production chunker does not fabricate that metadata (see Known limitations).

## Retrieval checks against the current GDD

Run after rebuilding, `top_k=3`, against the August 21, 2026 canonical GDD:

| Query | Top result | Heading | Lines | Score |
|---|---|---|---|---|
| mouse-directed movement and cursor-to-gameplay-plane projection | nsc-gdd-007 | Player Actions and Systems | 62-69 | 47.20 |
| Charged Fireball movement restriction ownership | nsc-gdd-026 | Development Agent Ownership Invariants | 208-212 | 39.92 |
| Frost Field cursor placement and Ranged Enemy limitation | nsc-gdd-025 | Development Agent Roles | 197-204 | 31.83 |
| door click-to-approach and automatic five-second timer | nsc-gdd-025 | Development Agent Roles | 197-204 | 35.47 |
| locked-door break and forward enemy pursuit | nsc-gdd-018 | Door and Pursuit Rules | 151-153 | 33.98 |
| floor restart owner-controlled reset entry points | nsc-gdd-037 | Runtime Implementation | 300-304 | 44.78 |
| victory suspend/re-enable ownership | nsc-gdd-027 | Development Agent Ownership Invariants | 213-219 | 37.49 |
| Active Enemy Registry fifteen-enemy cap | nsc-gdd-019 | Active Enemy Registry and Encounter Admission | 157-161 | 41.47 |
| fixed isometric camera requirements | nsc-gdd-034 | 2.5D Isometric Visual and World Representation | 280-287 | 25.44 |
| Windows build and canonical scene registration | nsc-gdd-039 | Approved Unity Packages and Windows Build Configuration | 325-328 | 56.62 |

Two queries ("Frost Field cursor placement..." and "door click-to-approach...") rank the
`Development Agent Roles` table first because that table's per-agent cells directly
restate the relevant ownership/behavior text at high term density; the dedicated
`Spell and Enemy Interactions` and `Runtime Implementation` chunks that describe the same
behavior in gameplay terms rank close behind (2nd/3rd). This is the same class of
retrieval-tuning tradeoff documented in `DynamicContentPipeline/README.md`'s Frost Field
example — a real ranking behavior to be aware of, not a defect in the index. These ten
results are pinned as a regression baseline in `tests/retrieval_regression_test.py`.

## Known limitations

- **No curated `entities`/`keywords` metadata.** The Assignment 4 knowledge base had
  hand-authored entity/keyword lists per chunk, which boosted retrieval precision for
  known named concepts. This production chunker is fully deterministic and does not
  fabricate that metadata, so ranking relies on `title`/`section`/`subsection`/`text`
  alone. This is why a broad table chunk can occasionally outrank a more specific prose
  chunk, as shown above.
- **Oversized single-line paragraphs are not split.** If a future GDD edit introduces one
  very long paragraph written as a single physical Markdown line and it exceeds
  `max_chunk_chars`, it will be kept as one oversized chunk rather than invented a
  sub-paragraph boundary. Not currently triggered by the GDD.
- **Headings deeper than `###` are not chunk boundaries.** None exist in the current GDD;
  a `####+` heading would currently be treated as ordinary content of its nearest `###`
  ancestor.
- **Front matter parsing is intentionally minimal**: it only reads simple
  `key: "quoted value"` lines from the leading `---`-delimited YAML block, which is all the
  current GDD front matter uses.

## Relationship to Milestone 2

This slice implements only the RAG extraction/rebuild/freshness piece of Milestone 2
(`Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`). It intentionally does not implement NSC-003,
the task context pack, the project scanner, the Progressive Decomposer, Artifact Authority,
or the supervisor/GER integration — those remain separate bounded slices.
