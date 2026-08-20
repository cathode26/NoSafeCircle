# Spell / Restart / Feedback Verification Closure

This patch addresses the three final material findings and the useful warnings
from verification run `20260820T192147Z-300fc01d` against reconciliation
`20260820T185344Z-1c243a16`.

## Files patched

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

## Material finding fixes

1. **Spell/reset ownership**
   - Player Mana owns mana and its own regeneration-delay state.
   - Force Wave owns its long cooldown reset.
   - Fireball owns its charge/cast reset state.
   - Frost Field owns its Wizard-Combat-side cast/active-field reset state.
   - Full persistent restart closure depends on unfinished required spell reset
     owners.
   - Enemy-side Frost slowdown remains Enemy Pursuit/status-effect owned.

2. **R6 process representation**
   - Development Agent Ownership Invariants are mapped as
     `required_process -> pipeline_constraint`.
   - Runtime Frost casting/slowdown acceptance criteria remain separate runtime
     representations instead of being misused as the process-row mapping.

3. **Frost Field feedback**
   - Frost Field requires readable player-facing cast/active-field feedback as
     acceptance behavior.
   - No unapproved VFX/audio/color/animation detail is invented.

## Useful warning hardening

- Fireball explicitly remains cursor-aimed.
- Ranged Enemy explicitly keeps moderate distance and fires a slow,
  telegraphed shot.
- Player Experience failure readability, including poor positioning, remains a
  validation obligation.
- Door Open/Interaction locks `PlayerInteractionController.cs` when modifying
  that input/selection implementation.
- Shared cursor targeting is not automatically assigned to Player Movement.
  Cursor use alone does not create Door/Frost/Fireball -> Player Movement
  dependencies.
- Charged Fireball's separate movement-restriction dependency on Player
  Movement remains valid while that interface is unfinished.
- A bounded staged/current-owner restart orchestrator may remain `single_agent`
  even though full persistent restart closure is broader.

## Safety

The apply script patches only the three prompt files above.

It does **not** read, copy, move, replace, or modify either GDD file.
It does not mutate `Tasks/*.yaml`.
