# Parallel Verification Crew

This patch adds:

`Pipeline/Reconciliation/parallel_verification_crew.py`

It imports and reuses the existing verification schemas, model invocation,
finding merge, Refiner, semantic validation, immutable output layout, and current
verification prompts.

The original `verification_crew.py` is untouched.

## Pass 1: 15 focused independent auditors

### Nine domain coverage auditors

The coverage workload is split using the same ownership domains as parallel
reconciliation:

1. Player Core
2. Wizard Combat
3. Enemy State
4. Enemy Behavior
5. Doors
6. World Foundations
7. Content + Encounters
8. Run Lifecycle
9. Global Pipeline / Delivery

Each coverage auditor still reads the entire GDD so cross-section qualifiers are
available, but it emits requirement inventory/findings only for its assigned
domain.

### Three repository-evidence auditors

Repository evidence is split into:

- Player + Combat + Doors
- Enemies + Encounters
- World + Run + Delivery

### Two structural auditors

The previous combined Dependency/Decomposition auditor is split into:

- Dependency + ownership + decomposition
- Exclusive-resource / shared-writer safety

This specifically keeps dependency semantics separate from resource-lock
semantics.

### One execution-scope auditor

Execution scope remains a dedicated independent check.

## Concurrency

Default parallel slots: 8

Environment override:

`RECONCILIATION_PARALLEL_VERIFY_MAX_WORKERS`

The existing model pool is reused and assigned across auditors in a reproducible
round-robin after shuffling with the saved random seed.

Findings are still unioned. There is no majority voting.

## Refinement

For safety, this first parallel-verification version keeps the existing bounded
Opus Refiner unchanged.

That avoids introducing a new patch-mutation format at the same time we change
audit parallelism.

## Selective Pass 2

After refinement, Python compares the original and refined candidate by field.

It reruns:

- every auditor that reported a pass-1 finding;
- coverage auditors for domains whose GDD/acceptance/validation fields changed, plus the global coverage auditor because project-wide validation/process mappings may point at those owners;
- evidence auditors for domains whose repository status/evidence changed;
- dependency auditor when parents/dependencies/decomposition changed;
- resource auditor when exclusive_resources changed;
- execution auditor when execution_scope changed.

Clean pass-1 auditors outside the Refiner's changed territory are reused rather
than rerunning the same expensive audit.

Use `--full-pass2` to force all 15 auditors to rerun.

## Safety

This patch does NOT modify:

- `verification_crew.py`
- any verification prompt
- reconciliation scripts/prompts
- GDD files
- existing immutable outputs
- `Tasks/*.yaml`
