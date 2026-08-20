# 24-Turn Minimum for Parallel Reconciliation

This patch raises every normal parallel reconciliation domain worker budget to
24 turns.

## Why

Lowering max-turn budgets did not create the parallel speedup. Concurrency did.

`--max-turns` is a ceiling, not a target. A worker that can finish in 10 turns
still finishes in 10 turns even when its ceiling is 24. Reducing a worker from
24 turns to 14/16/18/20 therefore saves nothing when the worker finishes early,
but it can cause an otherwise healthy worker to fail at the artificial ceiling.

That happened to `Doors and Interaction` at 16 turns.

A max-turn recovery is still useful as a safety net, but a normal 24-turn floor
reduces the chance that the pipeline enters a serial recovery phase after the
nine-way parallel wave.

## New policy

All nine domains start with:

- normal budget: 24 turns;
- max-turn recovery bonus: +12 turns;
- recovery budget when needed: 36 turns.

Successful workers stop whenever they finish; they do not consume all 24 turns
just because the ceiling is higher.

## Safety

Only `Pipeline/Reconciliation/parallel_reconciliation_agent.py` changes.

The nine-domain split, 9-way concurrency, complete routing-key registry,
deterministic merge, max-turn recovery, prompts, GDD, outputs, and
`Tasks/*.yaml` remain unchanged.
