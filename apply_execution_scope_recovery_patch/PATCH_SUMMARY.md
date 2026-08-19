# Execution-Scope Consistency + Failed-Run Recovery

The failed run contained an open executable `player-health-resource` with
`execution_scope: not_applicable`. That is a contradictory model output.

The dangling `fixed-isometric-camera` dependency merely caused structural
repair to run first. The later semantic validation would still have failed on
the player-health item.

This patch adds deterministic normalization:

- feature -> `not_applicable`
- complete work with future-execution classification -> `not_applicable`
- open executable + `not_applicable` -> `unknown`

`unknown` is conservative and leaves the real handoff-size decision to
verification/human review.

It also adds a recovery utility so the preserved failed run can be finalized
without rerunning the full Sonnet reconciliation.
