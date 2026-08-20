# Run Guide — Parallel Reconciliation v2

From the repository root, install/upgrade:

```powershell
python .\NoSafeCircle_parallel_reconciliation_v2\apply_parallel_reconciliation_v2.py
```

Run:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_reconciliation_agent.py
```

Then, after a successful reconciliation:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/verification_crew.py
```

## Runtime behavior

There are nine domain workers with six parallel slots by default.

That means the workers normally execute in roughly two waves rather than
starting nine Claude CLI processes simultaneously.

You can change the concurrency without editing code by setting:

`RECONCILIATION_PARALLEL_WORKERS`

Each worker has a domain-sized turn budget of 14–20 turns and a default timeout
of 720 seconds.

## Failure behavior

Every completed worker is saved immediately under the immutable run directory:

`Pipeline/Reconciliation/outputs/runs/<run-id>/workers/`

If a later worker fails, completed domain results remain available for diagnosis.

The run also writes:

- `PARALLEL_MERGED_CANDIDATE.raw.json`
- `PARALLEL_MERGE_DIAGNOSTICS.json`

before normal semantic validation/output generation.
