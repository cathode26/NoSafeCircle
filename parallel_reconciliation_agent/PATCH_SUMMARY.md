# Parallel Reconciliation v2 — Previous-Output-Driven Domains

This supersedes the earlier five-worker draft.

The worker split is now derived from the actual previous refined reconciliation
rather than from an arbitrary division of the GDD.

## Nine workers

1. Player Core Systems
2. Wizard Combat and Spells
3. Enemy State, Persistence, and Shared Effects
4. Enemy Pursuit and Attack Behavior
5. Doors and Interaction
6. World and Unity Foundations
7. Floor Content and Encounters
8. Run Lifecycle and Victory
9. Delivery, Validation, and Pipeline Constraints

The immediately previous refined graph had 37 work items. These nine domains
cover all 37 existing responsibilities without overlap.

## Previous output is routing, not truth

Stable previous keys are supplied to each worker only as routing hints.

Workers must still:

- read the entire current GDD;
- inspect current repository evidence;
- omit a routed item if it is no longer supported;
- add newly required same-domain work;
- never cite reconciliation output as GDD/repository evidence.

## Faster architecture

v1:

five workers -> deterministic union -> full LLM closure -> validation

v2:

nine focused workers -> deterministic merge -> existing semantic validation

There is no full closure-agent call.

Cross-domain dependencies use the stable keys where current canon still supports
them. The existing bounded dangling-dependency repair remains available if a
worker references a concrete key that another worker failed to emit.

## Global validation overlays

The Global Pipeline worker does not recreate other systems.

It may emit GDD-backed acceptance/validation overlays for existing owners, such
as Player Experience Success Criteria. Python attaches those to the emitted
owner after all domains finish.

## Safety

The installer creates or upgrades only:

`Pipeline/Reconciliation/parallel_reconciliation_agent.py`

It does not modify:

- `reconciliation_agent.py`
- `reconcile.md`
- verification prompts
- GDD files
- previous output snapshots
- `Tasks/*.yaml`
