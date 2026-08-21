# Streaming Verification Refinement — Run Guide

This branch combines approved reconciliation/verification closure fixes with streaming verification refinement v2.

## Approved closure fixes included

The installer updates the working tree so reconciliation/verification uses the agreed rules:

- locked-door attacks use current tracking/pursuit state; no separate `witnessed escape` state exists;
- all five named room requirements remain represented;
- pursuit explicitly traverses open/broken doorways;
- Player Movement owns shared cursor-to-gameplay-plane projection;
- Frost Field is placed at the shared cursor world-space target;
- spell casting consumes Unity Input System/Input Actions rather than direct hardware polling;
- current scene-builder/scene locks are represented for the work that actually writes those surfaces;
- Melee/Ranged Enemy work owns usable assembled archetype delivery;
- enemy restart repositioning remains owner-controlled by enemy pursuit/locomotion reset behavior;
- restart bootstrap/persistent closure share `logical:floor-run-restart-orchestrator`;
- runtime implementation requirements are kept separate from development-process constraints;
- requirement-representation warnings may enter bounded refinement.

## Streaming refinement v2

- pass-1 auditors launch field-level repair proposals as soon as they finish;
- early repairs are relative to the immutable original candidate;
- existing work items are edited with small typed operations (`set`, `append_unique`, `remove_unique`) instead of whole-record upserts;
- genuinely new records may use `upsert_record`;
- compatible field operations merge deterministically;
- `depends_on` and `exclusive_resources` list elements deduplicate by their durable `key`, so two auditors adding the same dependency/resource with different explanatory prose still produce one graph element;
- record removal/replacement conflicts with every field edit on that record;
- only connected incompatible field clusters invoke LLM arbiters, and independent clusters may arbitrate in parallel;
- failed local repair proposals are recovered independently;
- the projected candidate must pass the normal semantic validator before it is converted into the existing Refiner-delta contract;
- selective Pass 2 remains the final check;
- `Tasks/*.yaml` is never mutated by verification.

## Install/update everything

From the NoSafeCircle repository root:

```powershell
python .\streaming_verification_refinement_patch\apply_all.py
```

## Syntax check

```powershell
docker compose run --rm claude python3 -m py_compile Pipeline/Reconciliation/verification_crew.py Pipeline/Reconciliation/parallel_verification_crew.py Pipeline/Reconciliation/streaming_refinement_v2.py streaming_verification_refinement_patch/resume_streaming_verification.py
```

## Deterministic smoke test

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/streaming_refinement_v2_smoke_test.py
```

The smoke test covers immutable source behavior, field edits, compatible append merging, conflicting sets, record-remove conflicts, and semantic deduplication of repeated dependency/resource keys.

## Normal verifier run

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id <RECONCILIATION_RUN_ID>
```

Expected streaming telemetry includes submission and completion timing:

```text
[STREAM] coverage_wizard_combat produced refiner-relevant findings; field repair submitted now.
[STREAM] Field repair completed: coverage_wizard_combat (82.41s since submission)
```

At synthesis:

```text
STREAMING REPAIR CONFLICT / SYNTHESIS GATE
Early repair proposals: N
Mechanical field conflicts: M
```

Zero mechanical field conflicts means no LLM conflict arbiter should be required; deterministic projection still runs semantic validation.

## Resume a synthesis-stage failure without rerunning Pass 1

If all pass-1 auditors and local field repairs completed but synthesis/semantic validation failed, preserve that verification directory and resume from it after fixing deterministic merge logic:

```powershell
docker compose run --rm claude python3 streaming_verification_refinement_patch/resume_streaming_verification.py --source-run-id <RECONCILIATION_RUN_ID> --verification-run-id <FAILED_VERIFICATION_RUN_ID>
```

Resume behavior:

- creates a new immutable verification run;
- reuses all preserved pass-1 auditor outputs;
- reuses all preserved local field-repair proposals;
- does not rerun those expensive agents;
- reruns deterministic synthesis/conflict arbitration only as needed;
- runs selective Pass 2 against the newly projected candidate;
- leaves the failed verification and source reconciliation untouched.

## Verification artifacts

Streaming-v2 runs may contain:

```text
stream_repairs/<audit-key>/REFINER_FINDINGS.json
stream_repairs/<audit-key>/PROPOSED_FIELD_REPAIR.json
STREAM_REPAIR_MANIFEST.json
STREAM_CONFLICT_REPORT.json
STREAM_PREARBITER_CANDIDATE.json
stream_conflicts/cluster_*/CLUSTER_INPUT.json
stream_conflicts/cluster_*/ARBITRATED_FIELD_REPAIR.json
STREAM_CONFLICT_ARBITER.json
```

A resumed run stores reused repairs as `REUSED_FIELD_REPAIR.json` in the new verification directory.

## Configuration

```text
RECONCILIATION_STREAM_REPAIR_MAX_WORKERS=6
RECONCILIATION_STREAM_REPAIR_MODEL=sonnet
RECONCILIATION_STREAM_CONFLICT_MAX_WORKERS=4
```

The normal verifier/refiner environment variables continue to apply.
