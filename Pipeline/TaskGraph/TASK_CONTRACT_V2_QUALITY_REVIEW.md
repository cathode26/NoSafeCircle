# Task Contract Schema 2.0 Quality Review

## Purpose

Schema validation proves that migrated task contracts are structurally valid. It does not prove that every acceptance criterion is non-duplicated or that every completion gate can be satisfied when its owning task is delivered.

The first real migration was therefore audited before commit with:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit.py
```

## Audit result before correction

The heuristic audit reported:

- 37 contracts reviewed;
- one duplicate/near-duplicate acceptance-criteria candidate;
- one future-dependent completion-gate candidate.

Reported candidates:

1. `NSC-003 / VAL-002` — validating pointer consumption by a spell or Door/Interaction only once those systems exist.
2. `NSC-019 / AC-006 + AC-010` — duplicate gameplay-enable/suspend obligations for door interaction.

Manual inspection also found two duplicate pairs that the heuristic did not report:

3. `NSC-003 / AC-005 + AC-006` — duplicate gameplay-enable/suspend obligations for movement.
4. `NSC-019 / AC-007 + AC-009` — duplicate reset-entry-point obligations for door interaction.

## Human-reviewed decisions

### NSC-003

- Merge the two movement gameplay-enable/suspend criteria into one complete criterion.
- Keep Player Movement responsible for producing and exposing the shared world-space pointer target.
- Move proof that a later spell or Door/Interaction consumer integrates with that target from `completion_gates` to `downstream_integration_obligations`.

Reason: NSC-003 can prove that the shared target exists and behaves correctly, but it cannot require an as-yet-unimplemented consumer to exist before movement itself can be delivered.

### NSC-019

- Merge the duplicate door gameplay-enable/suspend criteria into one criterion covering cancellation of active approach/timing, command rejection while suspended, and Game Flow/Victory ownership.
- Merge the duplicate reset criteria into one criterion covering all owned interaction/opening state and Floor Run/Restart ownership.

Reason: duplicate criteria create ambiguity about whether two separate implementations or validations are required when the GDD defines one ownership obligation.

### NSC-023

Retain the existing reviewed decision:

- fixed projection and no-free-rotation tests remain completion gates;
- future Tilemap/SpriteRenderer framing compatibility remains a downstream integration obligation.

## Final migration identity

The reviewed migration uses:

```text
task-contract-schema-v2-20260822-r2
```

Changing the migration identity prevents an earlier uncommitted migration report from being mistaken for the reviewed final output.

## Expected post-correction audit

After restoring the generated first-pass task files, pulling the reviewed migration rules, and reapplying the migration, run:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit.py --strict
```

Expected:

```text
Duplicate/near-duplicate AC findings:   0
Future-dependent gate candidates:       0
Total review findings:                  0
```

A zero heuristic finding count does not prove perfect semantic quality. It confirms that the known migration findings were resolved and no remaining contract matches the current deterministic review rules.
