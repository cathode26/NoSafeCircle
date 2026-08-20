# Final Graph-Edge Hardening

Based on current `main` after commit
`938e6ded7233547d6be8e3462e62cf39378653fa`
(`Harden verification semantics and coverage`).

## Files patched

- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

## Changes

- Prevent Door Lifecycle from depending on Door Open merely because they share
  a door implementation/integration surface.
- Keep shared write collisions as `exclusive_resources`, not fake dependencies.
- Extract/preserve a concrete shared `doorway-crossing-state` implementation
  owner consumed by close/lock progression and final victory.
- Require Final Escape/Victory to depend on concrete gameplay-input owners it
  disables: movement, door interaction, Fireball, Frost Field, Force Wave, and
  doorway-crossing state.
- Require Player Movement to own an external movement-restriction/modifier
  interface needed by charged Fireball.
- Require Fireball to depend on Player Movement while that specific interface
  remains unfinished.
- Re-run dependency-kind, cycle, lock, and execution-scope closure after repair.

## GDD safety

The apply script does **not** read, copy, move, replace, or modify any GDD file.
