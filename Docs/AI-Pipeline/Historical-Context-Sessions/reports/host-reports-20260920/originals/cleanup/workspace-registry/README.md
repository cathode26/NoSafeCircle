# Workspace registry bootstrap

Created 2026-09-19 as documentation/evidence infrastructure for the requested Cleanup-role revision. **No existing workspace has been inventoried, released or certified by this bootstrap.** An absent index is an unseeded registry, not an empty project.

Protocol: C:/NSC/nsc-workspace-lifecycle-policy.md, version 1. Producers create immutable JSON receipts in inbox/<workspace-id>--<event-id>.json before creating persistent workspaces. Cleanup alone maintains the derived index.md; creators do not wait for import. The first producer can create inbox when writing its first receipt. Never treat a template as evidence.

Seed active/protected roots and incoming jobs first; import historical inventory per partition. Preserve unknowns as holds. This root, future events/index, action receipts and all cleanup logs are protected evidence included in durability-source coverage.

Manual workflow only: no launcher hook, validator, scheduler or background process installed.
