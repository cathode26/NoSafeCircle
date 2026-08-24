# Stage D1A Task Decomposition

This package is the deterministic, model-free contract boundary that must exist before a live Progressive Decomposer can be connected.

It accepts four decisions: `already_concrete`, `decomposed`, `needs_artifact`, and `needs_human`. An execution gap may split only already-approved implementation responsibilities into concrete, single-agent children. A design gap may propose the smallest missing artifact, but this package neither authorizes nor generates it. Uncertainty is escalated to a human.

Every parent `AC-###`, `VAL-###`, and `INT-###` entry must have exactly one explicit coverage record. Every proposed child has at least one acceptance criterion and one completion gate, must be targeted by parent coverage, and every proposed child entry must trace back through an exact ID mapping. Text similarity is not evidence of coverage. `shared_integration` always has a target; a single target also requires an integration rationale, while two or more exact targets are sufficient.

Blocking decisions may retain obligations that are not blocked, but `needs_artifact` must identify at least one `blocked_by_artifact` obligation and `needs_human` must identify at least one `blocked_by_human` obligation. Artifact sources must name exact parent obligations whose coverage is blocked by that artifact.

Children use proposal-local lowercase keys. They never choose `NSC-###` IDs or depend on the selected aggregate parent. The pure graph-delta planner accepts only the exact decomposition snapshot type and reparses it through the contract and complete semantic policy against the selected parent plus current reconciliation keys before using any child data. It then deterministically allocates IDs above the greatest existing numeric ID, resolves dependencies, builds an in-memory graph overlay, and validates that complete overlay with the production TaskGraph validator.

The result is immutable review data only. D1A performs no file writes and has no apply operation; it does not establish approval, readiness, execution authority, delivery, conformance, or completion.

Future D1B may connect a live decomposer invocation to these contracts and add verification/refinement. Future D1C may introduce a separately authorized review/application boundary. Artifact Authority, artifact generation/GER, readiness, and dispatch remain outside this package.
