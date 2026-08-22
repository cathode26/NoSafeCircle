# ADR-031 — Legacy task YAML status is advisory, not execution authority

**Status:** Accepted for Architecture Correction Phase 1

## Decision

The existing `status: open|complete` field in `Tasks/*.yaml` is retained temporarily as legacy human-planning metadata, but it is not execution authority and does not prove current completion.

During Phase 1:

- `taskcontrol ready` is explicitly advisory;
- the old ambiguous `ready_tasks()` Python API fails closed;
- human-facing code may call `advisory_ready_tasks()` only for inspection;
- `taskcontrol authorize <task>` denies every legacy task with exit code `2`;
- no autonomous dispatcher may launch a worker from YAML status or the advisory ready frontier.

## Reason

The adversarial architecture review identified that a one-line YAML edit can mark a dependency complete and unlock downstream work without proving that:

- implementation exists on the integrated branch;
- the tested tree is the integrated tree;
- required deterministic, Unity, or runtime validation passed;
- the governing GDD requirement is still current;
- later changes did not invalidate the result.

The persistent graph remains useful as a task-contract and dependency-planning structure, but mutable status cannot safely own implementation truth.

## Consequences

Phase 1 deliberately blocks autonomous dispatch until a later evidence-derived conformance model exists.

Phase 2 is expected to separate:

- task contract definitions;
- active attempt/run state;
- immutable delivery/revalidation evidence;
- current integrated Git state;
- GDD requirement revisions;
- derived states such as `ready`, `blocked`, `needs_replan`, `needs_revalidation`, and `complete`.

A historical delivery receipt will be necessary but not permanently sufficient: relevant later GDD or implementation changes must be able to invalidate or require revalidation.

## Clarifications to earlier decisions

- ADR-007 (`Done means merged`) remains necessary but is no longer sufficient. Merged code must also have matching validation/conformance evidence.
- ADR-029's `taskcontrol ready` semantics are transitional. Until evidence-derived conformance exists, its frontier is advisory and non-autonomous.
