# Typed Non-Code Storage + Encounter Refinement Visibility

This patch addresses two issues found in the latest reconciliation verification.

## 1. First-class delivery / pipeline storage

`non_code_requirements` records now include:

- `requirement_type: non_code_requirement`
- `requirement_type: delivery_requirement`
- `requirement_type: pipeline_constraint`

Coverage audit records gain `mapped_non_code_titles`, so a coverage auditor must
name the actual typed non-code record that represents a delivery/process
requirement.

Legacy non-code records default conservatively to `non_code_requirement`.

## 2. Known encounter runtime work is no longer hidden behind deferred authoring

The pipeline now explicitly separates:

- unknown/deferred encounter authoring:
  placements, trigger positions, exact compositions, durability values

from:

- already-specified runtime behavior:
  active-enemy ceiling enforcement that delays/reduces new encounter
  activation before removing any persistent pursuer.

The reconciliation and Refiner prompts both encode this invariant.

## 3. Structural warnings can reach the Refiner

The Refiner still receives every blocker/error, but now also receives warnings
only from these scheduler-relevant categories:

- `under_decomposition`
- `overgrouped_work`
- `shared_capability_hidden`

This avoids reopening all warnings while ensuring a fully specified runtime
capability cannot remain invisible merely because an auditor classified the
problem as a warning.

A structural warning alone can now trigger the bounded Refiner.

## 4. Auditor severity

The Dependency/Decomposition Auditor is instructed to treat a fully specified
runtime mechanism that becomes undispatchable solely because it is bundled
inside deferred authoring as an `under_decomposition` error.

## 5. Smoke tests

The smoke test now covers:

- mapped typed non-code requirements;
- legacy non-code type upgrade;
- selection of an under-decomposition warning for refinement;
- rejection of ordinary warnings from Refiner input.
