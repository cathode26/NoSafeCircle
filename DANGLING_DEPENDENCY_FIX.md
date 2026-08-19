# Reconciliation Agent Dangling-Dependency Fix

## Failure observed

The full reconciliation completed, but semantic validation found:

`'fireball' depends on missing work key 'player-mana'.`

The raw result actually referenced `player-mana` from Fireball, Frost Field,
and Force Wave while omitting the `player-mana` work item itself.

## Fix

1. The main reconciliation prompt now requires a dependency-closure check
   before returning structured output.
2. Python detects dangling `depends_on` references before full semantic
   validation.
3. Instead of discarding the completed full reconciliation, Python launches a
   small read-only structural Refiner.
4. The Refiner may add the omitted evidence-backed work item or remove an
   invalid/speculative dependency.
5. The repaired result is sanitized and run through the normal deterministic
   validator.
6. The repair is bounded by `RECONCILIATION_MAX_STRUCTURAL_REPAIRS`
   (default 2).

This turns a common structured-output defect into a bounded repair step rather
than another multi-minute full reconciliation run.
