# Multi-Model Reconciliation Verification Design

## Goal

Reduce correlated semantic failures before reconciliation output becomes the
bootstrap source for the persistent No Safe Circle work graph.

## Principle

Different agents answer different questions. Different requested models add
interpretive diversity. Neither diversity nor consensus is treated as proof.

```text
                  immutable candidate
                         │
        ┌────────────────┼────────────────┐
        │                │                │
 Coverage A          Coverage B        Structure
  model X             model Y          model X/Y
        │                │                │
        └────────────┬───┴────────────┬───┘
                     │                │
                Evidence Auditor ─────┘
                  model X/Y
                     │
               union findings
                     │
              bounded Refiner
                     │
              independent pass 2
                     │
                 human gate
```

## Why two coverage auditors

Coverage is the hardest part to validate mechanically. A model can fail to
extract a requirement before any later Python rule has a chance to notice the
omission. Running two independent coverage passes with different requested
models reduces the chance that one model's conceptual compression becomes the
whole pipeline's blind spot.

## Why no voting

The agents have different roles and a rare finding may be the most important
one. Majority voting would incorrectly suppress findings that only the auditor
assigned to that failure mode could discover.

## Why randomized model assignment

Fixed role/model pairing can accumulate a systematic blind spot. Randomizing
assignments across verification runs varies which model interprets each audit
role. The exact assignment and seed are saved so the run remains auditable.

## Why model aliases are configurable

The default pool uses `opus` and `sonnet`. The environment can replace or
extend that pool with model names supported by the installed Claude Code
version without changing the verifier implementation.

## Human authority

The verification system can produce a refined candidate but cannot approve it
or create the persistent task graph. Human approval remains the bootstrap
authority boundary.
