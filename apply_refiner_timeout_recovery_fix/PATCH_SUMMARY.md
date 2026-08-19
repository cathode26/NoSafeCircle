# Refiner Timeout / Recovery Fix

The reconciliation and all five pass-1 auditors completed successfully. The
verification stopped only because the randomly assigned Sonnet Refiner exceeded
the 1200-second timeout.

This patch:

- preserves randomized/model-diverse auditors;
- pins the synthesis Refiner to Opus by default;
- raises the default Refiner timeout to 1800 seconds;
- sends only blocker/error findings to the Refiner;
- preserves warnings/suggestions for pass-2 independent re-audit;
- lets recovery rerun only a missing/timed-out Refiner;
- continues to pass 2 without repeating pass 1;
- records recovery metadata;
- adds smoke-test coverage.

Recover this exact run with:

docker compose run --rm claude python3 Pipeline/Reconciliation/recover_verification.py --source-run-id 20260819T083840Z-7c4d3287 --verification-run-id 20260819T084512Z-15f7c570
