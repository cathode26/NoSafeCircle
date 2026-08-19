# Progressive Decomposition Pipeline Update

Prepared: 2026-08-18

This package contains proposed replacements for:

- `Docs/AI-Pipeline/START_HERE.md`
- `Docs/AI-Pipeline/CURRENT_STATE.md`
- `Docs/AI-Pipeline/00_MASTER_CONTEXT.md`
- `Docs/AI-Pipeline/DECISIONS.md`
- `Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md`
- `Docs/AI-Pipeline/02_RAG_SCANNER_CONTEXT.md`

## Architectural changes

1. Added progressive, just-in-time task decomposition.
2. Added three work kinds: `feature`, `artifact`, and `implementation`.
3. Kept Milestone 1 deterministic and LLM-free.
4. Moved the Progressive Decomposer into Milestone 2.
5. Added the Artifact Authority Gate before any AI-generated design/content.
6. Added approved artifacts as subordinate, trusted design state under the GDD.
7. Positioned Assignment 7 as a scored Style Evaluator inside Artifact GER.
8. Explicitly separated:
   - deciding that design is missing;
   - authorizing creation of new design;
   - generating it;
   - evaluating its quality;
   - using approved output to decompose implementation work.
9. Added ADR-021 through ADR-024.
10. Preserved Assignment 6 GER as the bounded repair mechanism for both implementation and generated artifacts.

## Important boundary

Milestone 1 does NOT implement Claude-powered decomposition.

Milestone 1 only establishes a truthful persistent work graph.

Milestone 2 introduces RAG/scanner context, progressive decomposition, artifact authority, and artifact generation/evaluation.
