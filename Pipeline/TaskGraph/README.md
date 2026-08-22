# Persistent Task Graph and Task Contracts

This directory contains the deterministic tooling for the No Safe Circle persistent work graph.

## Current architecture correction

The initial bootstrap successfully established stable `NSC-###` identities, dependencies, parent hierarchy, and exclusive-resource coordination. The adversarial architecture review then found that schema-v1 task files incorrectly combined work definitions with mutable completion claims.

Phase 1 disabled autonomous execution authority.

Phase 2 introduces **task-contract schema 2.0**:

```text
Tasks/*.yaml = approved definition of work
```

not:

```text
Tasks/*.yaml = definition + running state + validation state + completion truth
```

See:

- `TASK_CONTRACT_SCHEMA_V2.md`
- `Docs/AI-Pipeline/ADR-031_TASK_STATUS_ADVISORY.md`
- `Docs/AI-Pipeline/ADR-032_TASK_CONTRACT_SCHEMA_V2.md`

## Phase 2 files

- `task_contract_schema.py` — shared schema constants and deterministic entry normalization.
- `task_contract_migration.py` — idempotent v1-to-v2 task conversion plus explicit reviewed migration rules.
- `migrate_task_contracts_v2.py` — repository migration planner/checker/applicator.
- `migrate_task_contracts_v2_smoke_test.py` — end-to-end synthetic migration, validation, recovery, and idempotence test.
- `work_graph_validate.py` — validates a uniform v1 graph during transition or the final v2 graph; mixed live graphs fail closed.
- `persistent_work_graph.py` — loads one uniform live schema and rejects interrupted mixed state.
- `taskcontrol.py` — inspection CLI; execution authority remains disabled.

## Run the Phase 2 checks

From the repository root:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_transform_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_validate_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/work_graph_persist_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py
```

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2_smoke_test.py
```

## Check the real migration

This validates all real tasks and prints the exact migration summary without writing:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2.py --check
```

Review the task count, historical status-observation counts, completion-gate count, and downstream-obligation count.

## Apply the real migration

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/migrate_task_contracts_v2.py --apply
```

The migrator:

1. reads every `Tasks/NSC-*.yaml` file;
2. converts v1 or preserves already-valid v2 contracts;
3. validates the complete target graph before writing;
4. checks source hashes immediately before publication;
5. atomically replaces each task file;
6. publishes `TASK_CONTRACT_V2_MIGRATION.json` last;
7. supports safe rerun after interruption.

Then run:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py validate
```

Expected task schema:

```text
2.0
```

Readiness intentionally remains unavailable:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py ready
```

Authorization intentionally remains denied:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-003
```

## Historical bootstrap boundary

Do not rerun the one-time bootstrap on this repository.

The old reconciliation, verification, approval, and bootstrap records remain immutable history. Schema 2.0 migrates the living task contracts; it does not rewrite the evidence that originally produced them.

## Next phase

After the real v2 migration is committed, introduce the minimum delivery/revalidation evidence model needed to derive current conformance for one real task. Do not enable autonomous dispatch until that evidence is bound to current canon and the exact integrated Git tree.
