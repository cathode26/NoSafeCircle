# Exclusive Resource Scheduling Metadata

## Why

The verification crew exposed a fourth independent question:

1. Is the work required?
2. Is the design concrete enough?
3. Is the work bounded enough for one implementation agent?
4. Can two otherwise-ready tasks safely execute concurrently?

`execution_scope: single_agent` answers #3, not #4.

Two bounded tasks may both need to modify the same Unity scene, prefab, editor
builder, or source file. They can both be ready while still requiring sequential
dispatch.

## Added field

Every reconciliation work item now carries an `exclusive_resources` list with:

- a canonical lock `key`;
- a `reason`;
- evidence/basis.

Canonical key forms:

- `repo-file:<repo-relative path>`
- `unity-scene:<Assets/... path>`
- `unity-prefab:<Assets/... path>`
- `logical:<stable-lowercase-slug>`

Shared lock keys are scheduling constraints, not dependency edges.

## Pipeline changes

- reconciliation schema requires `exclusive_resources`;
- legacy candidates default to an empty list;
- deterministic validation checks canonical resource keys;
- proposed graph deltas carry lock keys and shared lock groups;
- human Markdown output displays lock metadata;
- structure and execution-scope auditors verify the distinction;
- the Refiner can correct missing/overbroad lock metadata;
- verification findings gain `exclusive_resource_problem`;
- smoke tests cover shared locks and feature-node lock rejection;
- README documents future `taskcontrol` lock semantics.

## Future taskcontrol behavior

`taskcontrol ready` may expose two tasks that share a lock. The dispatcher,
rather than readiness calculation, must acquire all exclusive resources before
starting an agent. Two tasks whose lock sets intersect cannot run concurrently.
