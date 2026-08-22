# Production GDD RAG integrity boundary

`gddctl validate`, `gddctl search`, and every direct `GDDRetriever` instance use
`integrity.validate_current_knowledge_base` before serving canon.

A production index is accepted only when:

- the complete canonical GDD SHA-256 matches;
- every chunk is canonical `game_design` content;
- every source path and line range points inside the canonical GDD;
- every chunk's text exactly equals its declared source lines;
- character counts and chunk SHA-256 values match the indexed text; and
- the complete index exactly equals a deterministic rebuild from current canon.

The last check covers chunk order, heading metadata, chunk parts, document
metadata, and unexpected fields. Direct imports of `GDDRetriever` enforce the
same boundary as the CLI, so future task-context code cannot accidentally serve
stale or altered canon by bypassing `gddctl`.

The historical Assignment 4 project under `DynamicContentPipeline/` remains
unchanged and is not part of this production trust path.
