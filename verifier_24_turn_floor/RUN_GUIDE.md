# Run Guide

Install from the NoSafeCircle repository root:

```powershell
python .\NoSafeCircle_parallel_verification_24_turn_floor\apply_verifier_24_turn_floor.py
```

Then run the verifier with all 15 auditor slots:

```powershell
docker compose run --rm -e RECONCILIATION_PARALLEL_VERIFY_MAX_WORKERS=15 claude python3 Pipeline/Reconciliation/parallel_verification_crew.py
```

Or verify a specific reconciliation run:

```powershell
docker compose run --rm -e RECONCILIATION_PARALLEL_VERIFY_MAX_WORKERS=15 claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id YOUR_RUN_ID
```
