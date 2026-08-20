# Verification Semantics Hardening

This package implements the four changes selected after verification run
`20260820T091449Z-3fcb0593` against reconciliation
`20260820T085916Z-aba38aad`.

## 1. Reconciliation / Refiner hardening

The new prompt closure rules preserve the real omissions and useful findings
without blindly converting every interface interaction into a dependency.

They explicitly cover:

- currently-existing DoorInteractable run-persistent state in staged restart;
- a reset entry point on the current door-opening owner when that state exists;
- Player Health no-passive-regeneration / whole-run persistence;
- an observable zero-health/death transition for restart orchestration;
- Melee Enemy eventually closing distance against ordinary retreat;
- door breach feedback as implementation acceptance plus validation;
- Fireball/Frost Field spending through the shared Player Mana interface;
- dependency discipline when an owner-side interface already exists;
- `partial` repository-state precision for existing locomotion plus missing
  cursor movement/reset;
- existing mana-indicator evidence when present;
- camera and navigation foundation parenting under `world`;
- human final-integration authority as a pipeline constraint;
- camera compatibility / canonical scene path as integration-validation issues,
  not invented GDD ambiguity.

The Refiner also receives `Packages/packages-lock.json` as an approved package
resolution source, matching the reconciliation/evidence boundary already in
place.

## 2. `required_implementation` verification taxonomy

`verification_crew.py` now accepts the requirement classification:

`required_implementation`

Valid durable representations are:

- `work_item`
- `acceptance_criterion`
- `validation_requirement`
- `deferred_design`

This distinguishes required technical implementation/configuration from
`required_process`. Unity package configuration, runtime architecture
prerequisites, and concrete authoring prerequisites are implementation scope;
agent isolation/context/compile/handoff rules remain process scope.

The smoke test includes a positive `required_implementation -> work_item`
fixture while retaining the existing invalid process/gameplay cases.

## 3. Coverage auditor ambiguity hardening

The shared Coverage Auditor prompt now instructs both Coverage A and B to:

- classify approved Unity package/configuration requirements as
  `required_implementation`, not `required_process`;
- treat exact canonical `.unity` path selection as an implementation decision
  already owned by world/build registration, not missing game design;
- treat camera compatibility with the future Tilemap/SpriteRenderer foundation
  as a validation/integration obligation rather than a GDD ambiguity;
- avoid declaring a dependency solely because a consumer uses an interface
  whose required callable surface already exists;
- require implementation acceptance criteria when the GDD requires visible
  behavior (door breach feedback), even when validation criteria also exist.

## 4. Force Wave canon clarification

The GDD now states consistently in both the gameplay action table and Technical
Strategy that Force Wave is:

- player-centered;
- short-range radial knockback;
- not aimed by cursor direction;
- not selected by cursor target.

The general cursor-targeting wording now applies to cursor-aimed spells and
interactions, with Force Wave explicitly identified as the exception.

Both canonical GDD sources are included:

- `Docs/GDD/No_Safe_Circle_GDD.md`
- `Docs/GDD/No_Safe_Circle_GDD_Final.docx`

The formatted DOCX was rendered after the edits and all 17 pages were visually
checked for layout defects.

## Files changed by the apply script

- `Docs/GDD/No_Safe_Circle_GDD.md`
- `Docs/GDD/No_Safe_Circle_GDD_Final.docx`
- `Pipeline/Reconciliation/verification_crew.py`
- `Pipeline/Reconciliation/verification_smoke_test.py`
- `Pipeline/Reconciliation/prompts/reconcile.md`
- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

## Recommended next commands

1. `docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py`
2. Fresh reconciliation because GDD canon changed.
3. Inspect the fresh reconciliation before another full verification run.
