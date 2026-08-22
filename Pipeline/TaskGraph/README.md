# Persistent Task Graph and Task Contracts

This directory contains deterministic tooling for the No Safe Circle persistent work graph.

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
- `TASK_CONTRACT_V2_QUALITY_REVIEW.md`
- `Docs/AI-Pipeline/ADR-031_TASK_STATUS_ADVISORY.md`
- `Docs/AI-Pipeline/ADR-032_TASK_CONTRACT_SCHEMA_V2.md`

Phase 3A adds committed delivery, historical-adoption baseline, and revalidation records plus a deterministic current-conformance evaluator. Evidence-derived current-state inspection now exists. No production evidence record is introduced by this extension, and dependency-readiness and dispatch authorization policy remain disabled. State inspection alone never authorizes execution; zero tasks may be autonomously dispatched. See `CONFORMANCE_RECORDS.md` and `Docs/AI-Pipeline/ADR-033_EVIDENCE_DERIVED_CONFORMANCE.md`.

Inspect committed-HEAD conformance for one schema-v2 task:

```powershell
python3 Pipeline/TaskGraph/taskcontrol.py state NSC-003
```

```powershell
python3 Pipeline/TaskGraph/taskcontrol.py state NSC-003 --json
```

Run the synthetic Phase 3A Git-object regression suite:

```powershell
python3 Pipeline/TaskGraph/conformance_evaluator_smoke_test.py
```

## Phase 2 files

- `task_contract_schema.py` — shared schema constants and deterministic entry normalization.
- `task_contract_migration.py` — idempotent v1-to-v2 task conversion plus explicit human-reviewed migration rules.
- `migrate_task_contracts_v2.py` — repository migration planner/checker/applicator.
- `migrate_task_contracts_v2_smoke_test.py` — end-to-end synthetic migration, validation, quality-audit, recovery, and idempotence test.
- `task_contract_quality_audit.py` — heuristic post-migration review for duplicate acceptance criteria and completion gates that may actually be downstream obligations.
- `task_contract_quality_audit_smoke_test.py` — deterministic audit regression test.
- `work_graph_validate.py` — validates a uniform v1 graph during transition or the final v2 graph; mixed live graphs fail closed.
- `persistent_work_graph.py` — loads one uniform live schema and rejects interrupted mixed state.
- `taskcontrol.py` — inspection CLI; readiness and execution authority remain disabled.

## Reviewed migration corrections

The first real migration quality audit found two candidates, and manual inspection found two additional duplicate pairs that the heuristic did not flag.

The final migration rules therefore:

- merge NSC-003's duplicate gameplay-suspend acceptance criteria;
- move NSC-003's future pointer-consumer validation from a completion gate to a downstream integration obligation;
- merge NSC-019's duplicate gameplay-suspend acceptance criteria;
- merge NSC-019's duplicate reset acceptance criteria;
- preserve NSC-023's future visual-foundation compatibility check as a downstream integration obligation.

The reviewed migration identity is:

```text
task-contract-schema-v2-20260822-r2
```

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
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit_smoke_test.py
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

The `codex-review` service mounts the repository read-only. Use the writable `codex` service for `--apply`:

```powershell
docker compose run --rm codex python3 Pipeline/TaskGraph/migrate_task_contracts_v2.py --apply
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

Run the quality audit after migration:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/task_contract_quality_audit.py --strict
```

Expected result:

```text
Total review findings:                  0
```

Readiness intentionally remains unavailable:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py ready
```

This command does not derive a dependency-ready frontier. Current-state inspection is available, but the dependency-readiness and dispatch policy is not enabled.

Authorization intentionally remains denied:

```powershell
docker compose run --rm codex-review python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-003
```

The authorization command intentionally returns exit code `2`; Docker Desktop may offer Gordon because the process is nonzero, but the denial is expected.
Its reason code is `evidence_derived_dispatch_policy_not_enabled`. A derived state, including `conformant`, is inspection output only and never grants execution authority.

## Replacing an uncommitted first migration

If the earlier migration identity `task-contract-schema-v2-20260822` was applied locally but not committed, discard only those generated outputs before running the reviewed migration:

```powershell
git restore -- Tasks
```

```powershell
Remove-Item Pipeline/TaskGraph/TASK_CONTRACT_V2_MIGRATION.json
```

Then pull the reviewed migration tooling, run `--check`, and apply again.

## Historical bootstrap boundary

Do not rerun the one-time bootstrap on this repository.

The old reconciliation, verification, approval, and bootstrap records remain immutable history. Schema 2.0 migrates the living task contracts; it does not rewrite the evidence that originally produced them.

## Next phase

Use the Phase 3A model for separately reviewed real evidence so production delivery/baseline/revalidation evidence can be proven on a real task. Do not derive dependency readiness or enable dispatch authority until the broader evidence-backed dispatch policy is explicitly designed and approved.
