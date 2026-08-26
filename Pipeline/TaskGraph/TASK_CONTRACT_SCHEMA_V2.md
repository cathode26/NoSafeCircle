# Task Contract Schema 2.0

## Purpose

`Tasks/*.yaml` defines approved work contracts. It does not store current execution, delivery, validation, or completion truth.

Schema 2.0 removes the v1 top-level `status` field because a mutable YAML value could previously unlock downstream work without proving that implementation was integrated, validated, current against canon, or still valid after later changes.

The files remain in the deterministic JSON-compatible YAML 1.2 subset used by the existing TaskGraph tooling.

## Authority boundary

A v2 task contract may define:

- stable `NSC-###` identity and `reconciliation_key`;
- contract revision and disposition;
- title, kind, type, parent, dependencies, and exclusive resources;
- execution/decomposition scope as properties of the work itself;
- acceptance criteria;
- completion gates;
- downstream integration obligations;
- GDD and repository evidence captured when the contract was created;
- per-contract provenance;
- `decomposition_children` and `decomposition_requirement_sha256` for a newly decomposed aggregate feature.

A v2 task contract may not claim:

- that work is currently ready;
- that a worker owns or is running the task;
- that implementation is currently complete;
- that validation passed;
- that a result is merged;
- that later GDD or code changes did not invalidate prior evidence.

Those states will be derived later from task contracts, current canon, attempt journals, integrated Git state, delivery/revalidation evidence, and human decisions.

## Required top-level fields

```json
{
  "schema_version": "2.0",
  "id": "NSC-003",
  "contract_revision": 1,
  "contract_disposition": "active",
  "title": "...",
  "reconciliation_key": "...",
  "kind": "implementation",
  "type": "...",
  "execution_scope": "single_agent",
  "execution_reason": "...",
  "decomposition_state": "concrete",
  "decomposition_reason": "...",
  "parent": "NSC-002",
  "depends_on": [],
  "exclusive_resources": [],
  "acceptance_criteria": [],
  "completion_gates": [],
  "downstream_integration_obligations": [],
  "gdd_evidence": [],
  "basis": "direct_gdd",
  "source_scope": "required",
  "confidence": "high",
  "notes": "",
  "repository_state_at_bootstrap": "missing",
  "repository_evidence_at_bootstrap": [],
  "provenance": {}
}
```

`decomposition_children` and `decomposition_requirement_sha256` are not universal required fields. They are added by the new decomposition transition when a previously executable contract becomes an explicit decomposed aggregate feature.

## Contract revision

`contract_revision` is a positive integer. Increase it only when the approved meaning of the work contract changes. Delivery/conformance evidence must eventually bind to an exact contract revision and hash.

## Contract disposition

Allowed values:

- `active` — the contract is still applicable;
- `superseded` — a newer active task contract replaces it; `superseded_by` is required;
- `cancelled` — human authority intentionally cancelled the contract.

Disposition describes the applicability of the contract. It is not implementation status.

## Numbered acceptance and validation entries

Acceptance criteria use stable contract-local IDs:

```json
{
  "criterion_id": "AC-001",
  "reference": "GDD section",
  "requirement": "Required behavior"
}
```

Completion gates use:

```json
{
  "gate_id": "VAL-001",
  "reference": "Validation source",
  "requirement": "Evidence required when this task is delivered"
}
```

Downstream integration obligations use:

```json
{
  "obligation_id": "INT-001",
  "reference": "Future integration source",
  "requirement": "Check owned by later integration work"
}
```

A completion gate must be achievable when the task is delivered. A check that can only occur after another future system exists belongs under `downstream_integration_obligations` and should later be assigned to the relevant integration task.

## Decomposed aggregate feature contracts

A successful new execution decomposition changes the role of the selected contract. The original NSC identity remains in the graph for hierarchy, requirement ownership, GDD traceability, and derived completion, but it is no longer an executable task.

The transitioned parent has this structural shape:

```json
{
  "kind": "feature",
  "execution_scope": "not_applicable",
  "decomposition_state": "decomposed",
  "decomposition_children": ["NSC-050", "NSC-051", "NSC-052"],
  "decomposition_requirement_sha256": "<sha256 of AC/VAL/INT obligations at decomposition>",
  "exclusive_resources": []
}
```

For contracts that contain `decomposition_children`, TaskGraph requires:

- the list is non-empty and contains unique task IDs;
- every listed child exists, is active, and directly names the aggregate as its `parent`;
- the list exactly equals the aggregate's complete active direct-child set;
- `decomposition_requirement_sha256` is a lowercase SHA-256 binding to the exact aggregate acceptance criteria, completion gates, and downstream integration obligations reviewed during decomposition;
- the aggregate is `kind: feature`, `execution_scope: not_applicable`, and `decomposition_state: decomposed`;
- the aggregate holds no executable exclusive-resource locks;
- no active contract keeps a `depends_on` edge to the aggregate.

The list is the machine-readable child completion set. Aggregate conformance is derived from the conformance of all listed children only while the current AC/VAL/INT requirement hash still equals `decomposition_requirement_sha256`. If those parent obligations change after decomposition, TaskGraph reports `needs_replan` rather than allowing old child completion to prove new requirements.

There is no later implementation or delivery pass on the aggregate itself.

If component children require a final assembly, wiring, or integration pass to make the parent capability usable, that work must be another explicit child task with dependencies on the component children. It cannot remain implicit work on the aggregate parent.

Historical decomposed contracts that predate `decomposition_children` remain readable for compatibility and are not silently migrated by the loader.

See `Docs/AI-Pipeline/ADR-034_DECOMPOSED_AGGREGATE_FEATURES.md`.

## Provenance

The initial migration records bootstrap history like this:

```json
{
  "origin": "verified_reconciliation_bootstrap",
  "source_schema_version": "1.0",
  "reconciliation_run_id": "...",
  "verification_run_id": "...",
  "bootstrap_status_observation": "open",
  "migration_id": "task-contract-schema-v2-20260822"
}
```

`bootstrap_status_observation` is historical context only. It is deliberately nested under provenance and cannot authorize execution or prove current conformance.

Future task contracts may have different provenance. Schema 2.0 no longer requires every task to come from one bootstrap run.

## Forbidden v1 operational fields

Schema-v2 tasks are invalid if they contain:

```text
status
validation_requirements
bootstrap_source
```

The migration converts these fields instead of carrying them forward unchanged.

## Camera migration correction

The v1 camera task mixed historical completion with contract scope:

- `execution_scope: not_applicable`;
- `decomposition_state: not_applicable`;
- one validation requirement that could only be checked after a future visual foundation existed.

The v2 migration corrects this by:

- restoring the bounded camera contract to `execution_scope: single_agent`;
- restoring `decomposition_state: concrete`;
- deriving its historical camera completion gates from the recorded Unity test evidence;
- moving the future Tilemap/SpriteRenderer compatibility check to `downstream_integration_obligations`.

## Migration commands

Check without writing:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2.py --check
```

Run deterministic smoke tests:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2_smoke_test.py
```

Apply the migration:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2.py --apply
```

The apply is idempotent. It writes task files atomically one at a time and publishes `TASK_CONTRACT_V2_MIGRATION.json` last. If interrupted before the report is published, rerun the same command; mixed v1/v2 task sets are recoverable by the migrator but rejected by the normal live graph loader.

## What schema 2.0 does not yet implement

Schema 2.0 does not create execution authority. After migration:

```text
taskcontrol ready
```

reports readiness as unavailable, and:

```text
taskcontrol authorize NSC-003
```

continues to deny execution.

The next phase must introduce delivery/revalidation records and derived current conformance before autonomous dispatch can be enabled.
