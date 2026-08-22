# ADR-032 — Task YAML is a versioned contract, not completion state

**Status:** Accepted for Architecture Correction Phase 2

## Decision

Migrate `Tasks/*.yaml` from schema 1.0 to task-contract schema 2.0.

Schema 2.0:

- removes top-level mutable `status`;
- adds `contract_revision`;
- adds `contract_disposition` (`active`, `superseded`, `cancelled`);
- converts acceptance criteria and completion gates to deterministic local IDs;
- separates completion gates from downstream integration obligations;
- replaces `bootstrap_source` with per-contract `provenance`;
- preserves v1 bootstrap status only as a historical provenance observation;
- allows permanent non-contiguous task IDs and different per-task provenance;
- does not authorize execution or claim current conformance.

## Reason

The architecture review found that v1 combined two different concerns:

1. the approved definition of work;
2. a mutable assertion about whether work was complete.

A one-line status edit could change dependency readiness without proving integration, validation, canon freshness, or survival of later changes. Expanding the status enum would preserve the same authority error.

Task contracts should define what evidence would be required. Separate evidence and current repository/canon state must determine whether that contract is presently satisfied.

## Migration policy

The migration is deterministic, idempotent, and report-bound.

- Existing stable IDs and reconciliation keys are preserved.
- Existing parent, dependency, resource, acceptance, GDD, and repository evidence is preserved.
- Existing `validation_requirements` become `completion_gates` unless an explicit reviewed rule classifies them as future integration work.
- The camera's future visual-foundation compatibility check is explicitly migrated to a downstream obligation.
- A migration report binds source and target hashes for every task file.
- Immutable reconciliation and verification history is not rewritten.
- The historical bootstrap marker remains historical and continues to require original bootstrap paths to exist.

## Consequences

After migration, task readiness cannot be calculated from task files alone. `taskcontrol ready` must fail closed until delivery/revalidation evidence and derived conformance exist.

Phase 3 must add the smallest evidence model necessary to prove one real delivery slice. It must not recreate mutable completion truth under a different filename.
