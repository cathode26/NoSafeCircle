# Bulk Task State Inspection

Schema-v2 `Tasks/NSC-*.yaml` files define approved work contracts. They do not contain mutable completion status.

Use TaskGraph's evidence-derived conformance evaluator to inspect whether committed evidence currently proves each task at `HEAD`.

## All task states

```powershell
python Pipeline/TaskGraph/taskcontrol.py states
```

The command prints one row per task with:

- task ID;
- evidence-derived state;
- contract disposition;
- task kind;
- title.

It also prints counts by derived state.

A typical executable task may report states such as:

- `conformant` — current committed evidence proves the current task contract, conformance surfaces, gates, and artifacts, while the record's historical canon provenance remains valid;
- `not_delivered` — no usable committed evidence currently proves the task;
- `needs_replan` — the task contract changed after prior evidence;
- `needs_human` — required human approval is missing;
- `needs_revalidation` — prior evidence exists but a tracked conformance surface or other current-state invariant is stale for `HEAD`;
- `invalid_evidence` — committed evidence is structurally or semantically invalid;
- `ambiguous_evidence` — more than one maximal current-valid record exists.

Feature or non-`single_agent` contracts report `aggregate`. Cancelled and superseded contracts report their dispositions as their derived states.

## Canon granularity

Delivery/baseline/revalidation records retain the SHA-256 of the complete canonical GDD that existed at the validated commit. That hash is immutable **historical audit provenance**.

The evaluator verifies that the recorded GDD hash really matched the validated commit, but it does not require today's entire GDD file to remain byte-identical forever. Otherwise an unrelated design addition would invalidate every previously delivered task.

Current task-relevant canon is carried by the schema-v2 task contract. Therefore:

- an unrelated GDD edit with no task-contract or tracked-surface change preserves `conformant`;
- a relevant design change that is reconciled into a revised task contract produces `needs_replan`;
- a tracked implementation/conformance-surface change produces `needs_revalidation`;
- a false historical GDD hash remains `invalid_evidence`.

See `Docs/AI-Pipeline/ADR-033_EVIDENCE_DERIVED_CONFORMANCE.md` for the architecture decision.

## Show only one state

For example, list tasks currently proven conformant:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state conformant
```

Or list tasks with no current delivery evidence:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state not_delivered
```

## JSON output

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --json
```

Filtering and JSON can be combined:

```powershell
python Pipeline/TaskGraph/taskcontrol.py states --state conformant --json
```

## Authority boundary

`states` is inspection only. It evaluates committed `HEAD` through the same conformance authority used by single-task `taskcontrol state`.

A `conformant` result does **not** establish dependency readiness, execution authorization, merge authority, or autonomous dispatch authority.

Do not treat `contract_disposition: active` as meaning unfinished. Contract disposition and evidence-derived conformance answer different questions.
