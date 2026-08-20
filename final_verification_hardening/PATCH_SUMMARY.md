# Final Verification Hardening

This package addresses the four remaining material findings from verification run `20260820T060345Z-5723fb84`.

## GDD changes

1. **Full floor-restart ownership**
   - Defines a shared Floor Run/Restart Orchestrator.
   - Each run-persistent system owns a reset entry point for its own state.
   - Early prototype reset work is explicitly only a stage; full persistent-systems closure remains required until every implemented persistent owner participates.

2. **Door state -> navigation passability ownership**
   - Door and Interaction owns semantic `sealed/open/locked/broken` state.
   - The shared navigation/locomotion layer owns translating semantic door state into enemy walkability through a shared passability interface.
   - Pursuit/attack code consumes this result instead of independently manipulating NavMesh/passability.
   - The specific Unity mechanism underneath the interface remains an implementation choice.

3. **Victory feedback**
   - Final-door forward crossing triggers victory.
   - Normal gameplay input stops.
   - A simple player-facing `You Escaped` overlay is shown.
   - No additional post-victory progression, menu flow, or meta-progression is required.

4. **Minimal-context dispatch**
   - Explicitly makes narrow agent context a required pipeline constraint.
   - Agents receive the approved feature brief, acceptance criteria, relevant GDD rules, and only task-required files/scene/prefab context.

The GDD revision date is updated to August 20, 2026.

## Prompt hardening

`apply_final_verification_hardening.py` appends idempotent hardening blocks to:

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

The hardening requires the graph to preserve a durable restart-closure owner, represent the door-passability contract at the correct ownership boundary, map explicit victory feedback without ambiguity, and preserve minimal-context dispatch as a typed pipeline constraint.

No Python validator/schema code and no `Tasks/*.yaml` files are changed.
