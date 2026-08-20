# Verification False-Positive Closure Patch

This patch targets the **two final material findings** from verification
`20260820T165308Z-e270bcf1` against reconciliation
`20260820T162415Z-d82c8030`.

## Files patched

- `Pipeline/Reconciliation/prompts/verification/coverage_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

## Fix 1 — deferred feature prerequisite

The verifier incorrectly requested:

`dungeon-encounter-content-authoring -> five-room-content-authoring`

Both are `feature` nodes. The graph invariant permits a feature to HAVE
dependencies, but dependency TARGETS must remain `implementation` or `artifact`.

The patch explicitly distinguishes:

- valid: feature -> `world-visual-foundation` implementation;
- invalid: feature -> feature.

The room-before-encounter relationship remains durable as deferred
decomposition/authoring context until concrete descendants exist.

## Fix 2 — no runtime AI classification

The finished-build prohibition on runtime generative AI / external AI services
is explicitly classified as:

`required_non_code -> non_code_requirement`

rather than `required_gameplay -> non_code_requirement`.

This prevents the deterministic coverage checker from producing the R33 false
error when the existing typed non-code record is already correct.

## Scope

Verification prompts only. No reconciliation prompt, Python validator, task
graph, or GDD files are changed.

The apply script does not read, copy, move, replace, or modify the GDD.
