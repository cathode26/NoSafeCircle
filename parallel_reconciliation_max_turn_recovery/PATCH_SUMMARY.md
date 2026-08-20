# Parallel Reconciliation Max-Turn Recovery

The nine-way run exposed the same fail-fast orchestration problem found in the
parallel verifier:

- eight workers completed;
- `Doors and Interaction` reached its 16-turn ceiling;
- the first failed future aborted the collection loop;
- the completed worker payloads were therefore not persisted;
- the immutable run directory survived, but `workers/` was empty.

## Changes

- make 9 the default parallel-worker count;
- do not fail-fast when one independent reconciliation worker errors;
- continue collecting all completed worker futures;
- save every successful worker result immediately;
- save per-attempt failure records for failed workers;
- detect max-turn failures explicitly;
- after the first wave, retry only max-turn failures;
- add 12 turns to the recovery attempt by default;
- never rerun successful reconciliation workers during recovery;
- merge only after all nine domains have a successful result;
- record max-turn recovery statistics in `PARALLEL_MERGE_DIAGNOSTICS.json`;
- if bounded recovery still fails, preserve all successful worker artifacts and
  fail with a clear incomplete-phase summary.

## Environment controls

- `RECONCILIATION_PARALLEL_WORKERS` default: `9`
- `RECONCILIATION_WORKER_RECOVERY_TURN_BONUS` default: `12`
- `RECONCILIATION_WORKER_MAX_TURN_RECOVERY_ATTEMPTS` default: `1`
- `RECONCILIATION_WORKER_TIMEOUT_SECONDS` remains unchanged.

A worker such as Doors with a 16-turn normal budget therefore receives:

- attempt 1: 16 turns;
- recovery attempt: 28 turns.

## What remains unchanged

- nine domain ownership split;
- complete routing-key registry;
- GDD/repository authority;
- worker read-only tools;
- deterministic merge;
- global overlays;
- dangling-dependency repair;
- semantic validation;
- immutable output layout;
- reconciliation prompts;
- GDD files;
- `Tasks/*.yaml`.

Only `Pipeline/Reconciliation/parallel_reconciliation_agent.py` changes.
