# Run

Install from the NoSafeCircle repository root:

```powershell
python .\NoSafeCircle_parallel_verification_max_turn_recovery\apply_parallel_verification_max_turn_recovery.py
```

Then rerun verification:

```powershell
docker compose run --rm -e RECONCILIATION_PARALLEL_VERIFY_MAX_WORKERS=15 claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id 20260820T231704Z-7dc2d046
```

The failed verification run `20260820T232345Z-69d46d5b` cannot be resumed because
the old fail-fast implementation did not persist the successful auditor outputs.
The next run will preserve successful auditors even if another auditor needs a
max-turn recovery.
