# Feature Aggregate Repository-State Patch

## Failure

The reconciliation classified the organizational root `no-safe-circle` as
`repository_state: partial` because some represented child systems are
implemented while others are not.

The root correctly had no direct `repository_evidence`, because the actual
evidence belongs to child implementation items. The deterministic validator
nevertheless applied the executable-work evidence rule to every work kind and
rejected the reconciliation.

The same raw reconciliation also contains `player` and `doors` as partial
feature groups with empty direct evidence, so fixing only the root would expose
the same failure again.

## Contract

Feature nodes are aggregate/organizational records. They may summarize child
progress without duplicating child evidence.

Implementation and artifact nodes remain evidence-bearing current-state records.

## Changes

- Restrict mandatory direct evidence for `implemented`/`partial` states to
  `implementation` and `artifact` work.
- Explicitly document feature aggregate-state semantics in the reconciliation
  prompt.
- Add smoke coverage proving:
  - a partial feature with no direct repository evidence is valid;
  - a partial implementation with no repository evidence still fails.
- Document the distinction in the Reconciliation README.

This does not weaken evidence requirements for executable work.
