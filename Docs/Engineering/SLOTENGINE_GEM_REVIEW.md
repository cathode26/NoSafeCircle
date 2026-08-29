# SlotEngine Gem Review

**Source reviewed:** `SlotEngine.zip`
**Review date:** August 29, 2026
**Repository role:** Supporting engineering evidence; not game-design canon and not authorization to copy proprietary source code.

This review is stored in ordered sections so repository agents can load only the evidence relevant to their task without losing the complete analysis. Read all sections in order when revising the engineering standards or making a broad architecture decision.

Any live inspection of a local SlotEngine snapshot must follow [`REFERENCE_PROJECTS.md`](./REFERENCE_PROJECTS.md). The default local source is an operator-approved `SlotEngine-Sanitized` tree mounted read-only; this review does not authorize exposing or publishing the full company project.

## Ordered sections

01. [Addressables Foundation](./SlotEngineGemReview/01_ADDRESSABLES_FOUNDATION.md) — Review context, selection method, content resolution, and Addressables fallback policy.
02. [Build And Pool Lifetime](./SlotEngineGemReview/02_BUILD_AND_POOL_LIFETIME.md) — Platform-aware Addressables builds, asset/pool lifetime ordering, and pool reset invariants.
03. [Platform Tooling And Assemblies](./SlotEngineGemReview/03_PLATFORM_TOOLING_AND_ASSEMBLIES.md) — Platform adapters, resource ownership, editor handoff tooling, frame budgets, extraction patterns, and assemblies.
04. [Style And Target Architecture](./SlotEngineGemReview/04_STYLE_AND_TARGET_ARCHITECTURE.md) — Resolved coding-style decisions and the proposed No Safe Circle Addressables architecture.
05. [Addressables Rules And Reuse Map](./SlotEngineGemReview/05_ADDRESSABLES_RULES_AND_REUSE_MAP.md) — Addressables standards, legacy patterns to ignore, and the exact reuse map.
06. [IP Boundary And Final Assessment](./SlotEngineGemReview/06_IP_BOUNDARY_AND_FINAL_ASSESSMENT.md) — Intellectual-property boundary and final engineering assessment.
- [`07_FADER_SIGNALS_AND_TOOL_SELECTION.md`](./SlotEngineGemReview/07_FADER_SIGNALS_AND_TOOL_SELECTION.md) — fader architecture, typed Signals, DOTween boundary, and agent reuse rules.

The active rules derived from this evidence live in [`ENGINEERING_STANDARDS.md`](./ENGINEERING_STANDARDS.md).
