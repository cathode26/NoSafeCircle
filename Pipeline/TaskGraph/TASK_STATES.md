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

- `conformant` — current committed evidence proves the current task contract, canon, conformance surfaces, gates, and artifacts;
- `not_delivered` — no usable committed evidence currently proves the task;
- `needs_replan` — the task contract changed after prior evidence;
- `needs_human` — required human approval is missing;
- `needs_revalidation` — prior evidence exists but is stale for current `HEAD`;
- `invalid_evidence` — committed evidence is structurally or semantically invalid;
- `ambiguous_evidence` — more than one maximal current-valid record exists.

Feature or non-`single_agent` contracts report `aggregate`. Cancelled and superseded contracts report their dispositions as their derived states.

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
