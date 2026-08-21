Refiner Delta Fix

Changes:
- Parallel evidence auditors now default to 36 turns instead of 24.
- Their max-turn recovery remains +12, so a failed evidence auditor retries at 48 turns.
- The Refiner now returns a bounded delta instead of regenerating the full reconciliation JSON.
- Python deterministically applies the delta to the frozen candidate and then runs the existing semantic validation.
- Every supplied Refiner finding must be resolved exactly once.
- The prompt explicitly forbids inventing canon from GDD silence.
- Adds a resume_parallel_refinement.py script so the preserved failed verification can continue without rerunning all 15 pass-1 auditors.
- Adds smoke coverage for the delta applier.

From the NoSafeCircle repository root, apply:
python C:\path\to\apply_refiner_delta_fix.py

Then run the smoke test:
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py

Then resume the preserved failed verification run:
docker compose run --rm claude python3 Pipeline/Reconciliation/resume_parallel_refinement.py --source-run-id 20260820T235538Z-f86ed98d --verification-run-id 20260821T000302Z-b256b233
