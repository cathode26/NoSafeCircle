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

Phase 3A adds committed delivery, historical-adoption baseline, and revalidation records plus a deterministic current-conformance evaluator. Phase 3B has now proven evidence-derived current conformance on the first real task: committed baseline `BASE-NSC-023-86af98f41ab5` selects as current for NSC-023 and derives `conformant`. No real production revalidation record exists yet.

A conformant result does not establish dependency readiness. Dependency-readiness policy and dispatch authorization policy have not been implemented or approved. `taskcontrol ready` remains unavailable, `taskcontrol authorize` remains denied, and state inspection and a conformant result never authorize autonomous execution. Zero tasks may be autonomously dispatched. See `CONFORMANCE_RECORDS.md` and `Docs/AI-Pipeline/ADR-033_EVIDENCE_DERIVED_CONFORMANCE.md`.

## Stage D1A graph-delta planning

`graph_delta.py` is a pure, deterministic proposal planner for validated execution decompositions. It requires the exact decomposition contract type and creates a fresh detached validation snapshot against the actual selected parent, current reconciliation keys, and complete decomposition policy before reading child proposals. It then allocates permanent IDs above the greatest existing numeric `NSC-###` ID, resolves existing-task and proposal-local dependencies, revises the aggregate parent in memory, updates copied ID-map/resource-group data, and validates the complete proposed overlay with `validate_work_graph_plan()`.

Its immutable `GraphDeltaPlan` is review data only. It never writes task or metadata files, has no apply command, and does not establish approval, readiness, execution authority, delivery, conformance, or completion. See `Pipeline/TaskDecomposition/README.md` for the decomposition-result contract boundary.

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

## Packaging delivery evidence

Producing valid delivery evidence used to be excessive manual clerical work (create
directories, copy the Unity XML/log, hand-write a human-validation file, compute every
hash and Git object identity, remember `git add -f` for gitignored artifacts like `*.log`,
then repair a delivery whose `.log` silently never got staged). `record_delivery.py` is
deterministic clerical automation for exactly that step — not another agent, and it grants
no completion authority:

```powershell
python3 Pipeline/TaskGraph/record_delivery.py $env:TEMP\NSC-005-delivery-spec.json
python3 Pipeline/TaskGraph/record_delivery.py $env:TEMP\NSC-005-delivery-spec.json --json
python3 Pipeline/TaskGraph/record_delivery_smoke_test.py
```

The delivery-spec JSON is input to the tool, not repository evidence. This tool requires
a completely clean working tree before packaging, so keep the spec file outside the Git
working tree entirely (for example `$env:TEMP\NSC-005-delivery-spec.json` on Windows) or in
a location already covered by `.gitignore`. Do not place an untracked spec file inside the
repository working tree — it will fail the clean-tree precondition, which is not weakened
to accommodate it.

It validates every precondition against the committed repository, copies and validates the
declared artifacts (rejecting a failing or malformed Unity test-results XML rather than
trusting a claim), computes every hash and Git blob identity itself, generates the delivery
record, and validates it with the existing `conformance_records.validate_record_shape()`.
It never stages, commits, pushes, merges, or edits a `Tasks/*.yaml` contract, and it never
claims the task conformant — it prints the exact `git add -f -- <files>` staging command
(enumerating precisely the files it generated, so a gitignored artifact such as `*.log`
cannot be silently dropped again) for a human to run, inspect, and commit. See
`CONFORMANCE_RECORDS.md` for the full delivery-spec format and generated-path layout.

## Validating the staged draft before committing

Postmortem improvement #4. Generating correct evidence bytes is not the same thing as
actually staging them correctly: NSC-005's `.log` file existed on disk but `*.log` was
gitignored, so a plain `git add`/`git commit` silently committed a record referencing a
`.log` blob that was never actually in the commit. `validate_draft_evidence.py` closes that
gap by inspecting the **Git index** — the would-be commit — before the human runs
`git commit`, deterministically, with no agents, no LLM, no Unity, and no staging/committing
of its own:

```powershell
python3 Pipeline/TaskGraph/validate_draft_evidence.py --record Pipeline/TaskGraph/evidence/NSC-005/records/DEL-NSC-005-12fad9358f63.json
python3 Pipeline/TaskGraph/validate_draft_evidence.py --record Pipeline/TaskGraph/evidence/NSC-005/records/DEL-NSC-005-12fad9358f63.json --json
python3 Pipeline/TaskGraph/validate_draft_evidence_smoke_test.py
```

The normal closeout workflow is:

1. validate the implementation/runtime behavior;
2. prepare the external delivery spec (Unity XML, log, human-validation text);
3. run `record_delivery.py` to generate the evidence record and artifacts;
4. run the exact `STAGE` command it prints (`git add -f -- <generated files>`);
5. run `validate_draft_evidence.py` on the staged record — this is the new step, printed by
   `record_delivery.py` itself between `STAGE` and `CHECK`;
6. inspect `git diff --cached --check` / `--stat`;
7. the human commits;
8. run `python Pipeline/TaskGraph/taskcontrol.py state <TASK-ID> --json`;
9. TaskGraph's evidence-derived evaluator determines conformance.

`record_delivery.py` validates the **generated bytes**. `validate_draft_evidence.py`
validates the **actual staged would-be commit** — the Git index, never a substitute
working-tree read — and is specifically what catches an artifact that exists on disk but
was never actually staged (gitignored or otherwise omitted), reports the exact missing path
plus a safe `git add -f -- '<path>'` fix (never `git add -A`/`git add .`/`git add -f
<directory>`), and also rejects any staged change outside the one task's evidence directory
(catching an accidental `git add -A` sweeping unrelated work into the same commit) and any
attempt to stage a modification, deletion, or replacement of an already-committed evidence
record or artifact. It never stages or commits anything itself. Committed TaskGraph
evaluation remains the sole authority for `conformant`, exactly as before, and only after
the evidence is actually committed.

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

This command does not derive a dependency-ready frontier. Evidence-derived current conformance has been proven on NSC-023, but a conformant result does not establish dependency readiness. Dependency-readiness and dispatch authorization policies have not been implemented or approved.

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

Stage D1A provides proposal contracts and in-memory graph-delta planning only. Live decomposition, verification/refinement, reviewed graph application, Artifact Authority/GER, dependency readiness, and dispatch remain later work. The first real production baseline has proven NSC-023 conformant; do not fabricate a gameplay, contract, GDD, or implementation change merely to create a revalidation record.
