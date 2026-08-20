# No Safe Circle — Reconciliation Retry Hardening

This package updates the GDD and hardens the four reconciliation/verification prompts that most directly influence the remaining semantic graph findings.

## GDD changes

- Defines shared doorway-crossing state as owned by Door and Interaction.
- Makes close/lock and final victory consume the same crossing state.
- Makes Melee and Ranged attacks consume the shared Player Health damage interface.
- Defines a reusable Active Enemy Registry and separates persistent bookkeeping from encounter-admission policy.
- Assigns registry bookkeeping to Enemy Pursuit and makes Dungeon Encounter consume the registry.
- Defines a shared gameplay navigation/locomotion layer as a prerequisite for locomotion-dependent enemy work.
- Keeps the concrete Unity navigation technology as a human-approved technical choice.
- Separates the reusable Tilemap/SpriteRenderer visual foundation from five-room content authoring.
- Adds Development Agent Ownership Invariants as explicit mandatory process constraints.
- Clarifies dependency-versus-shared-write semantics in the GDD's agent ownership rules.
- Keeps door cursor-drift accessibility/cancellation wording internally consistent.

## Prompt hardening

Updates:

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/execution_scope_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

The added rules emphasize:

- dependencies represent true behavioral prerequisites, not file collisions;
- shared write collisions belong in `exclusive_resources`;
- shared runtime capabilities have one authoritative owner;
- consumers must depend on missing required foundations;
- navigation human-integration state must block locomotion work when unresolved;
- reusable runtime foundations stay separate from deferred room content;
- Development Agent Ownership Invariants must survive as typed `pipeline_constraint` records;
- refiner repairs should follow the GDD's canonical ownership model instead of inventing alternate architecture.

## Apply

Extract this package into a temporary folder under the repository and run from the repository root:

`python <extracted-folder>/apply_reconciliation_retry_hardening.py`

Then run:

`docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py`

If the smoke test passes, run a fresh reconciliation and verification.
