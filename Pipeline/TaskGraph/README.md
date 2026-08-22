# Persistent Work Graph

This directory contains deterministic tooling for creating and inspecting the No Safe Circle `Tasks/*.yaml` work graph.

## Current safety boundary

The initial graph was bootstrapped from one human-approved, independently verified reconciliation snapshot. That bootstrap remains valuable for stable task identity, scope, dependencies, acceptance criteria, validation requirements, and exclusive-resource planning.

However, the adversarial architecture review identified an important Phase 1 defect:

> The mutable `status` field in `Tasks/*.yaml` is planning metadata, not evidence that implementation is currently integrated and valid.

A one-line edit from `open` to `complete` can change the legacy ready frontier. It cannot prove that:

- implementation exists on the current integrated branch;
- the tested tree is the integrated tree;
- required Unity/runtime validation passed;
- the governing GDD requirement is still current;
- a later change did not invalidate the result.

Until Phase 2 introduces evidence-derived conformance, **autonomous dispatch is disabled**.

## Phase 1 execution-authority guard

`taskcontrol ready` now prints an explicitly advisory human-planning list:

```powershell
python3 Pipeline/TaskGraph/taskcontrol.py ready
```

Its output is headed:

```text
ADVISORY READY WORK — NOT AUTHORIZED FOR AUTONOMOUS DISPATCH
```

The legacy Python API named `ready_tasks()` intentionally raises instead of returning candidates. Human-facing code must use the explicitly named `advisory_ready_tasks()` function.

Execution authority can be checked directly:

```powershell
python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-003
```

During Phase 1 this command always returns `DENIED` with exit code `2`, regardless of whether the task YAML says `open` or `complete`.

No current or future dispatcher may launch a worker solely from:

- a task's YAML `status` value;
- the output of `taskcontrol ready`;
- the `advisory_ready_tasks()` function.

## Useful commands

```powershell
python3 Pipeline/TaskGraph/taskcontrol.py validate
python3 Pipeline/TaskGraph/taskcontrol.py list
python3 Pipeline/TaskGraph/taskcontrol.py show NSC-003
python3 Pipeline/TaskGraph/taskcontrol.py ready
python3 Pipeline/TaskGraph/taskcontrol.py authorize NSC-003
python3 Pipeline/TaskGraph/taskcontrol.py graph
```

`validate`, `list`, `show`, `ready`, and `graph` may display the current legacy YAML status, but they label it as advisory. They do not establish completion truth.

## Regression tests

Run the existing persistent-graph smoke test:

```powershell
python3 Pipeline/TaskGraph/taskcontrol_smoke_test.py
```

Run the Phase 1 authority regression test:

```powershell
python3 Pipeline/TaskGraph/phase1_execution_authority_smoke_test.py
```

The Phase 1 regression proves all of the following:

1. changing a dependency's YAML status can change the advisory frontier;
2. the same edit does not create execution authority;
3. the old ambiguous `ready_tasks()` API fails closed;
4. `taskcontrol authorize` denies the candidate;
5. even changing the candidate itself to `complete` does not authorize it.

## Transitional manual delivery record

For the first real delivery slices, use:

```text
Pipeline/TaskGraph/MANUAL_DELIVERY_RECORD_TEMPLATE.md
```

This form captures task/GDD/base identities, commits, Unity evidence, human validation, integration details, and throughput measurements. It is an audit aid only and is not consumed as automatic completion authority.

## Bootstrap safety boundary

Reconciliation and verification never directly mutate `Tasks/*.yaml`.

The initial bootstrap proceeded through these stages:

1. Reconciliation created an immutable candidate and proposed graph delta.
2. Independent verification refined and re-verified the candidate.
3. A human approved one exact candidate/delta pair.
4. The deterministic Work Graph Seeder verified hashes and created the persistent graph.

The approval record binds immutable inputs by SHA-256:

```text
Pipeline/TaskGraph/APPROVED_BOOTSTRAP.json
```

Bootstrap completion is recorded in:

```text
Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json
```

The bootstrap is intentionally one-shot. Do not rerun `seed_work_graph.py --apply` against an already-bootstrapped repository.

## Phase 2 direction

Phase 2 will migrate task files toward pure work contracts and derive current state from separate evidence, including:

- task-contract revision/hash;
- governing requirement revision/hash;
- integrated Git tree;
- required validation evidence;
- human approval where required;
- invalidation or revalidation after relevant GDD/code changes.

That future model will replace mutable YAML completion claims with evidence-derived states such as `ready`, `in_progress`, `blocked`, `needs_replan`, `needs_revalidation`, and `complete`.

Phase 1 deliberately does not invent that full schema yet. It only prevents the current legacy status field from being mistaken for autonomous execution authority.
