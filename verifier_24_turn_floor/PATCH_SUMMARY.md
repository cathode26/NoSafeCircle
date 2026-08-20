# 24-Turn Minimum for Parallel Verification

This patch raises every normal parallel verification auditor category to a
24-turn ceiling.

## Why

Parallelism is what creates the wall-clock speedup. Lowering `--max-turns`
does not make an auditor that finishes early run faster; it only increases the
chance of an artificial max-turn failure.

The previous verifier had mixed ceilings:

- coverage: 16
- evidence: 24
- dependency/resource structure: 18
- execution scope: 16

The new policy is simpler and safer:

- coverage: 24
- evidence: 24
- structure/resources: 24
- execution scope: 24

All 15 Pass 1 auditors can still run concurrently.

## Recovery

The existing bounded max-turn recovery remains in place.

With the current +12 recovery bonus:

- normal ceiling: 24 turns
- recovery ceiling: 36 turns

Successful auditors stop whenever they finish; they do not consume all 24 turns
just because the ceiling is higher.

## Safety

Only:

`Pipeline/Reconciliation/parallel_verification_crew.py`

changes.

The 15-auditor split, model diversity, union-not-vote policy, max-turn recovery,
Refiner, selective Pass 2, semantic validation, prompts, GDD, outputs, and
`Tasks/*.yaml` remain unchanged.
