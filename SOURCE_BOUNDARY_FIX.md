# Reconciliation Agent Source-Boundary Fix

## Problem

Claude referenced `AgentCrew/outputs/feature_contract.json`, which is outside
the allowed reconciliation source boundary. Python correctly rejected the
result, but the whole run should not fail when the forbidden source was only
supplemental evidence.

## Fix

1. `prompts/reconcile.md` now explicitly forbids all `AgentCrew/` and
   `DynamicContentPipeline/` reads/globs/greps.
2. `reconciliation_agent.py` now defensively removes evidence from those
   forbidden paths before semantic validation.
3. The raw unsanitized Claude result is still preserved in
   `reconciliation.raw.json`.
4. The sanitized final result receives a warning and is downgraded from
   `ready` to `ready_with_warnings` if necessary.
5. Normal semantic validation still runs after sanitation. If removing a
   forbidden source leaves an implemented/partial item without valid evidence,
   the run still fails.

This keeps the source boundary strict without wasting a long Claude run over
non-essential forbidden corroboration.
