# Parallel Verification Max-Turn Recovery

The first 15-way verification run exposed an orchestration failure mode:

- all 15 independent auditors launched correctly;
- `Evidence — World Run Delivery` reached its 16-turn ceiling;
- the executor raised on that one failed future;
- other already-running auditors continued to completion;
- but the main collection loop had already aborted, so their successful structured
  results were not persisted.

The verification directory therefore preserved the run, but `pass1/` was empty.

## Changes

- raise the default repository-evidence audit budget from 16 to 24 turns;
- do not fail-fast when one independent auditor errors;
- continue collecting and immediately persist every successful auditor result;
- persist per-auditor failure records instead of discarding the wave;
- detect max-turn failures explicitly;
- after the first wave completes, retry only max-turn failures;
- give a recovery attempt an additional 12 turns by default;
- never rerun successful auditors during max-turn recovery;
- normalize recovered auditor names so deterministic finding merge and selective
  Pass 2 continue to work unchanged;
- fail the verification only after all independent results have been preserved and
  bounded recovery has been attempted.

## Environment controls

- `RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS` default: `24`
- `RECONCILIATION_PARALLEL_VERIFY_RECOVERY_TURN_BONUS` default: `12`
- `RECONCILIATION_PARALLEL_VERIFY_MAX_TURN_RECOVERY_ATTEMPTS` default: `1`

## What this does not change

- 15-way Pass 1 concurrency;
- model diversity;
- auditor scopes;
- union-not-vote finding policy;
- existing bounded Refiner;
- selective Pass 2;
- semantic validation;
- GDD or repository evidence rules;
- `Tasks/*.yaml`.

Only `Pipeline/Reconciliation/parallel_verification_crew.py` changes.
