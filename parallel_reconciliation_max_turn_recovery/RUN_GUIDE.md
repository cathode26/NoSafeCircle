# Run Guide

Install from the NoSafeCircle repository root:

```powershell
python .\NoSafeCircle_parallel_reconciliation_max_turn_recovery\apply_parallel_reconciliation_max_turn_recovery.py
```

Then rerun:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_reconciliation_agent.py
```

Nine workers are now the default, so the environment override is no longer
required.

The failed run `20260820T233700Z-fa5f8f73` cannot be resumed because the previous
fail-fast version did not persist the successful worker payloads. Future runs
will preserve successful domain outputs even if another worker needs recovery.
