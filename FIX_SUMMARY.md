# Reconciliation Agent Validator Fix

## Problem

The first reconciliation run completed successfully in Claude, but the local
semantic validator rejected:

`Feature node 'cross-room-persistent-pursuit-state' must not have executable dependencies.`

The prompt already allowed dependencies to originate from a feature as long as
the dependency target was concrete `artifact` or `implementation` work. The
validator was stricter than the prompt/architecture.

## Fix

1. Feature nodes may now declare real dependencies.
2. Dependency targets are still forbidden from being `feature` nodes.
3. Feature nodes remain non-executable and should never be returned by
   `taskctl ready`.
4. Claude's structured output is now saved to
   `outputs/reconciliation.raw.json` before semantic validation so future
   validator bugs do not discard a several-minute model run.
