# Streaming Verification Refinement — Run Guide

This patch changes the existing parallel verification flow so completed pass-1 auditors may immediately launch isolated repair proposals while slower auditors continue running.

Safety rules preserved by the patch:

- the reconciliation candidate remains immutable during pass 1;
- early repair workers produce proposed deltas only;
- no early repair delta is applied directly;
- after all auditors complete, a final conflict/synthesis arbiter reads the complete finding union plus all early repair proposals;
- only the arbiter's consolidated delta is applied;
- the existing selective Pass 2 verifier checks the resulting candidate;
- `Tasks/*.yaml` is never mutated by verification.

## Install

From the NoSafeCircle repository root on this branch:

```powershell
python .\streaming_verification_refinement_patch\apply_streaming_verification_refinement.py
```

The installer is idempotent. Running it again after successful installation will report that the streaming refinement is already installed.

## Syntax check

```powershell
docker compose run --rm claude python3 -m py_compile Pipeline/Reconciliation/parallel_verification_crew.py
```

## Run against the current reconciliation snapshot

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id 20260821T041756Z-cfed7174
```

## What you should see

When a pass-1 auditor returns refiner-relevant findings, output similar to this should appear before every verifier has finished:

```text
[STREAM] coverage_wizard_combat produced refiner-relevant findings; starting an isolated repair proposal now.
```

When an early proposal completes:

```text
[STREAM] Isolated repair proposal complete: coverage_wizard_combat
```

After all pass-1 auditors and outstanding early repairs finish, the pipeline runs:

```text
STREAMING REPAIR CONFLICT / SYNTHESIS GATE
```

The final arbiter then creates the single delta used to produce the refined candidate. Selective Pass 2 proceeds using the existing changed-field routing.

## New verification artifacts

Each verification run may additionally contain:

```text
stream_repairs/<audit-key>/REFINER_FINDINGS.json
stream_repairs/<audit-key>/PROPOSED_REPAIR_DELTA.json
STREAM_REPAIR_MANIFEST.json
STREAM_CONFLICT_REPORT.json
STREAM_CONFLICT_ARBITER.json
```

`STREAM_CONFLICT_REPORT.json` performs a deterministic first check for multiple proposals touching the same durable record. The final arbiter also checks semantic conflicts that cannot be detected by record-key overlap alone, including dependency cycles, ownership contradictions, incompatible resource locks, duplicated responsibility, and execution-scope inconsistencies.

## Configuration

Optional environment variables:

```text
RECONCILIATION_STREAM_REPAIR_MAX_WORKERS=6
RECONCILIATION_STREAM_REPAIR_MODEL=sonnet
```

The normal verifier/refiner environment variables continue to apply.
