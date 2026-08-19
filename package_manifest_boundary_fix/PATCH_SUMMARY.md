# Package Manifest Evidence Boundary Fix

## Problem

The multi-model verification Refiner correctly used `Packages/manifest.json` as
current Unity configuration evidence while refining the world/tilemap work item,
but deterministic reconciliation validation did not permit that path.

The result was rejected after the expensive pass-1 auditors and Refiner had
already completed.

## Fix

- permit exactly `Packages/manifest.json` as current-project configuration evidence;
- do **not** permit the rest of `Packages/`;
- keep current exact paths and historical evidence paths in separate sets so the
  package manifest cannot accidentally be classified as historical evidence;
- update generator, evidence-auditor, and Refiner prompts to match the validator;
- add regression tests for the exact package boundary.

## Recovery

The failed verification run is reusable. After applying this patch and passing
the smoke test, resume:

docker compose run --rm claude python3 Pipeline/Reconciliation/recover_verification.py --source-run-id 20260819T072941Z-1a10b837 --verification-run-id 20260819T080021Z-460045d5

This reuses completed pass 1 and the completed Refiner output and proceeds to the
missing pass-2 verification.
