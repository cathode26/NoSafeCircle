# Continuation Fix: Typed Non-Code + Encounter Refinement

The original patch partially succeeded and then stopped while trying to
rewrite the tail of `build_refiner_findings()`.

This continuation does not revert the successful partial edits.

It finishes the patch by:

- repairing `build_refiner_findings()` as one bounded function replacement;
- allowing selected structural warnings to trigger refinement;
- updating the Refiner runtime instruction to resolve every supplied finding;
- validating typed non-code records and requiring unique mapping titles;
- preserving typed non-code/delivery/pipeline records in proposed graph deltas;
- requiring coverage auditors to map typed non-code requirements to exact
  stored record titles;
- making hidden-known-runtime/deferred-authoring bundling an
  `under_decomposition` error;
- explicitly checking the encounter activation/cap split;
- updating the Refiner prompt with the same split invariant;
- updating smoke tests and README documentation.

After applying, run:

docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py
