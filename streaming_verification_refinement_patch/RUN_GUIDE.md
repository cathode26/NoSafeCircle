# Streaming Verification Refinement — Run Guide

This branch combines two changes:

1. approved reconciliation/verification closure fixes from verification run `20260821T043304Z-571ad814`;
2. streaming verification refinement, where completed pass-1 auditors may immediately launch isolated repair proposals while slower auditors continue running.

## Approved closure fixes included

The installer updates the working tree so the next reconciliation/verification run uses the agreed rules:

- clarify locked-door attacks: enemies still tracking/pursuing the player attack a locked door that blocks their route; no separate `witnessed escape` state exists;
- preserve all five named room requirements, including Ruined Entry and Final Room;
- require actual enemy pursuit through open/broken doorways, not merely target retention across a doorway crossing;
- honor the GDD's explicit Player Movement ownership of shared cursor-to-gameplay-plane projection and use a dependency while that specific owner-side capability is unfinished;
- preserve current prototype scene-builder/scene locks for Fireball, Frost Field, and Force Wave when those tasks actually integrate through those write surfaces;
- make Melee Enemy and Ranged Enemy work own/deliver usable assembled prefab archetypes unless a later concrete architecture establishes a separate composition owner;
- split runtime behavior from Development Agent Ownership process invariants during coverage classification;
- allow `requirement_representation_problem` warnings into bounded refinement so required representation gaps can be repaired in pass 1;
- remove stale reconciliation/coverage/refiner instructions that contradicted the current GDD's explicit shared-pointer ownership.

## Streaming-refinement safety rules

- the reconciliation candidate remains immutable during pass 1;
- early repair workers produce proposed deltas only;
- no early repair delta is applied directly;
- after all auditors complete, a final conflict/synthesis arbiter reads the complete finding union plus all early repair proposals;
- only the arbiter's consolidated delta is applied;
- the existing selective Pass 2 verifier checks the resulting candidate;
- `Tasks/*.yaml` is never mutated by verification.

## Install everything

From the NoSafeCircle repository root on this branch:

```powershell
python .\streaming_verification_refinement_patch\apply_all.py
```

The component installers are idempotent. The combined installer applies the approved closure fixes and then installs streaming refinement.

## Syntax check

```powershell
docker compose run --rm claude python3 -m py_compile Pipeline/Reconciliation/verification_crew.py Pipeline/Reconciliation/parallel_verification_crew.py
```

## Important: create a new reconciliation snapshot

Do **not** use the old `20260821T041756Z-cfed7174` snapshot as the test input after these changes. That immutable snapshot was produced before the clarified GDD/prompt rules.

Run a fresh reconciliation:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_reconciliation_agent.py
```

Then verify the new latest reconciliation with the streaming verifier:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py
```

The verifier defaults to `outputs/LATEST.json`, so no run ID is required unless you deliberately want to verify a specific snapshot.

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
