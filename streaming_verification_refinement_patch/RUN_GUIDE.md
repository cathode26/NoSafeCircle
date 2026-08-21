# Streaming Verification Refinement — Run Guide

This branch combines three related changes:

1. approved reconciliation/verification closure fixes from verification run `20260821T043304Z-571ad814`;
2. second-round closure fixes from verification run `20260821T060257Z-98087458`;
3. streaming verification refinement v2, where completed pass-1 auditors immediately launch small field-level repair proposals while slower auditors continue running.

## Approved closure fixes included

The installer updates the working tree so reconciliation/refinement uses the agreed rules:

- locked-door attacks use current tracking/pursuit state; no separate `witnessed escape` state exists;
- all five named-room requirements remain represented, including Ruined Entry and Final Room;
- pursuit explicitly traverses open/broken doorways;
- Player Movement owns shared cursor-to-gameplay-plane projection;
- Frost Field is explicitly placed at the current shared cursor world-space target;
- real pointer-projection dependencies are preserved while the owner-side capability is unfinished;
- Fireball, Frost Field, and Force Wave explicitly consume Unity Input System/Input Actions rather than direct hardware polling;
- current prototype builder/scene locks are preserved for spell integration;
- Player Movement carries current builder/scene locks while its generated scene integration is being changed;
- Melee/Ranged enemy work owns usable assembled archetype prefabs;
- enemy restart repositioning is performed through an enemy owner reset/reposition entry point, not by the restart orchestrator mutating enemy movement state;
- both restart stages share `logical:floor-run-restart-orchestrator`, and persistent restart closure carries the current builder/scene locks;
- runtime Input System behavior is classified as required implementation/gameplay behavior rather than required development process;
- `requirement_representation_problem` warnings may enter bounded refinement;
- stale prompt rules that conflict with current canon are removed/superseded.

## Streaming refinement v2

Pass-1 auditors still run independently in parallel. When one returns refiner-relevant findings, its repair worker starts immediately, but v2 no longer asks that worker to rewrite complete existing work-item records.

Early repair workers now emit small operations such as:

```text
set one field
append one acceptance criterion
append one validation requirement
append/remove one dependency
append/remove one exclusive-resource lock
remove an obsolete unresolved question
create a genuinely new durable record
```

The reconciliation snapshot remains immutable.

### Deterministic merge

Compatible operations are merged without an LLM arbiter. Examples:

- two independent `append_unique` operations on the same list are compatible;
- two identical field `set` operations are compatible;
- exact duplicate operations are deduplicated.

Incompatible edits to the same durable field form a conflict edge. Record removal/replacement conflicts with every field edit on that record.

Only connected conflict components invoke conflict arbiters. Independent conflict components may be arbitrated in parallel. The final projected candidate then runs the normal semantic validator before being converted back to the existing bounded Refiner-delta contract and sent to selective Pass 2.

## Safety rules

- the source reconciliation candidate is immutable;
- early repairs are operations against that immutable source only;
- existing records are edited with field operations rather than whole-record upserts;
- `upsert_record` is reserved for genuinely new durable records;
- compatible operations merge deterministically;
- only connected incompatible field clusters invoke an LLM arbiter;
- failed early repair proposals are recovered independently rather than forcing every auditor to rerun;
- the projected candidate must pass normal semantic validation;
- selective Pass 2 remains the final verification check;
- `Tasks/*.yaml` is never mutated.

## Install everything

From the NoSafeCircle repository root on this branch:

```powershell
python .\streaming_verification_refinement_patch\apply_all.py
```

The component installers are idempotent.

## Syntax and smoke checks

```powershell
docker compose run --rm claude python3 -m py_compile Pipeline/Reconciliation/verification_crew.py Pipeline/Reconciliation/parallel_verification_crew.py Pipeline/Reconciliation/streaming_refinement_v2.py
```

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/streaming_refinement_v2_smoke_test.py
```

## Verification run

For regression testing against the most recent clean reconciliation snapshot:

```powershell
docker compose run --rm claude python3 Pipeline/Reconciliation/parallel_verification_crew.py --run-id 20260821T055421Z-603b2192
```

The verifier also defaults to `outputs/LATEST.json` when no run ID is supplied.

## What v2 output should look like

A completed auditor with material/refiner-relevant findings should immediately show submission:

```text
[STREAM] coverage_wizard_combat produced refiner-relevant findings; field repair submitted now.
```

The completion message is emitted when that repair actually finishes rather than later during collection:

```text
[STREAM] Field repair completed: coverage_wizard_combat (84.2s since submission)
```

At synthesis you should see field-level conflict counts rather than whole-record conflicts:

```text
STREAMING REPAIR CONFLICT / SYNTHESIS GATE
Mechanical field conflicts: 2
Only connected incompatible field clusters invoke arbiters; the final projection still runs semantic validation.
```

If there are no incompatible field conflicts, no conflict arbiter should be needed. If conflicts exist, output reports how many connected clusters are being arbitrated.

## Verification artifacts

A v2 verification run may contain:

```text
stream_repairs/<audit-key>/REFINER_FINDINGS.json
stream_repairs/<audit-key>/PROPOSED_FIELD_REPAIR.json
stream_repairs/<audit-key>/RECOVERED_FIELD_REPAIR.json
STREAM_REPAIR_MANIFEST.json
STREAM_CONFLICT_REPORT.json
STREAM_PREARBITER_CANDIDATE.json
stream_conflicts/cluster_XX/CLUSTER_INPUT.json
stream_conflicts/cluster_XX/ARBITRATED_FIELD_REPAIR.json
STREAM_CONFLICT_ARBITER.json
```

`STREAM_CONFLICT_REPORT.json` now reports durable **field** conflicts and connected conflict components rather than treating every edit to the same work item as automatically conflicting.

## Configuration

Optional environment variables:

```text
RECONCILIATION_STREAM_REPAIR_MAX_WORKERS=6
RECONCILIATION_STREAM_REPAIR_MODEL=sonnet
RECONCILIATION_STREAM_CONFLICT_MAX_WORKERS=4
```

The normal verifier/refiner environment variables continue to apply.
