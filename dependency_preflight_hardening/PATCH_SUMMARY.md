# Dependency Preflight Hardening

This patch hardens only the Reconciliation Agent generator prompt.

The latest reconciliation was otherwise coherent, but it returned:

`dungeon-encounter-content-authoring -> five-room-content-authoring`

as a formal dependency even though both targets are `kind: feature`.

The graph contract already said dependencies may target only `implementation`
or `artifact`, but that rule was not prominent enough to survive a long,
complex reconciliation run.

The patch adds a mandatory final pre-return audit that:

- resolves every dependency key;
- verifies every target exists;
- verifies every dependency target is `implementation` or `artifact`;
- explicitly rejects `feature -> feature` dependencies;
- explains how deferred-content feature relationships should instead remain in
  decomposition metadata until executable descendants exist;
- requires the audit to run again after any correction;
- includes the exact five-room / dungeon-encounter example that caused the
  latest failure.

No Python validator or graph schema is changed. The goal is for the model to
produce a valid candidate itself before returning JSON.
