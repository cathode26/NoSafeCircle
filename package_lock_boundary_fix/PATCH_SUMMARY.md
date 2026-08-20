# Package Lock Boundary Fix

## Why this patch exists

The reconciliation run `20260820T081341Z-98a24515` produced valid package
evidence for `navigation-package-configuration`, including:

- `Packages/manifest.json`: `com.unity.ai.navigation` is not directly declared.
- `Packages/packages-lock.json`: `com.unity.ai.navigation` is not present in the
  resolved lock graph.

The deterministic validator rejected the second path because the reconciliation
boundary allowed only `Packages/manifest.json`.

That is a boundary-policy mismatch, not a bad evidence claim.

## Changes

- Allow exactly `Packages/packages-lock.json` as current package-resolution
  evidence in `reconciliation_agent.py`.
- Keep arbitrary `Packages/` files disallowed.
- Update `reconcile.md` to distinguish direct declaration evidence
  (`manifest.json`) from resolved package graph evidence (`packages-lock.json`).
- Update the Repository Evidence Auditor to use the same two-file boundary.
- Update the verification smoke test so it positively checks both approved
  package files and still rejects an arbitrary package-side file.

## Intentionally unchanged

- GDD canon.
- Dependency rules.
- Exclusive resource rules.
- AgentCrew/DynamicContentPipeline hard deny rules.
- Persistent Tasks graph.
- Existing immutable reconciliation outputs.
