# Run Guide

Install from the NoSafeCircle repo root:

```powershell
python .\NoSafeCircle_parallel_verification\apply_parallel_verification.py
```

Run parallel verification against the latest successful reconciliation:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py
```

Verify a specific reconciliation run:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id YOUR_RUN_ID
```

Force a full 15-auditor pass 2 instead of selective re-verification:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --full-pass2
```

The original verifier remains available:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_crew.py
```
