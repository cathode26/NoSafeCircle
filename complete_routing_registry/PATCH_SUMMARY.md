# Complete Routing-Key Registry for Parallel Reconciliation

This patch gives **every parallel reconciliation worker the same complete
37-key routing registry up front**.

The registry was derived from the previous refined/parallel graph shape and
contains, for each stable routed key:

- exact key;
- owning parallel domain;
- kind (`feature` / `implementation`);
- parent key.

It is explicitly treated as **naming/ownership metadata only**. It is not GDD
evidence and is not repository evidence. Current GDD + current repository remain
authoritative.

## Why

The first parallel reconciliation completed much faster, but independent
workers guessed near-synonym cross-domain dependency keys such as:

- `enemy-health-defeat`
- `enemy-status-displacement`
- `gameplay-navigation-locomotion-layer`

The actual stable routed keys were:

- `enemy-health-damage-defeat`
- `enemy-status-effect-displacement`
- `gameplay-navigation-locomotion`

That forced the post-merge dangling-dependency repair to resolve naming mistakes.

## New worker rules

Every worker now sees the full registry before it emits work.

When a cross-domain prerequisite corresponds to a listed responsibility, the
worker MUST use the exact registered key.

Workers are explicitly forbidden from:

- inventing shortened/synonym/`*-layer` aliases for listed responsibilities;
- creating an unresolved question whose only uncertainty is the stable key of a
  listed responsibility;
- targeting feature keys with `depends_on`;
- treating the registry itself as proof that work is still required/current.

If a truly new cross-domain responsibility is required and no registered key
matches, the worker must preserve the uncertainty instead of guessing a key.

## Deterministic guard

Each worker output is checked immediately.

A dependency key is accepted when it is either:

1. emitted by that worker itself; or
2. present in the complete routed-key registry.

An invented cross-domain alias therefore fails at the worker boundary instead of
surviving until the final merged candidate.

## Safety

Only:

`Pipeline/Reconciliation/parallel_reconciliation_agent.py`

is changed.

No GDD, prompt, previous output, verification prompt, or `Tasks/*.yaml` file is
modified.
