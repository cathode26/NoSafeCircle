# Verification Graph / Writer-Lock Closure

This patch addresses the two final material findings from verification run:

- source reconciliation: `20260820T203258Z-3b04bcc8`
- verification: `20260820T205841Z-71029338`

## Files patched

Only:

- `Pipeline/Reconciliation/prompts/verification/structure_auditor.md`
- `Pipeline/Reconciliation/prompts/verification/refiner.md`

## Finding 1 — illegal feature-target dependency

The Dependency/Decomposition Auditor still contained older wording that treated:

`encounter content/placement -> five-room content`

as an expected current dependency.

That conflicts with the graph invariant because the current
`five-room-content-authoring` target is a `feature`.

The patch now requires:

- no dependency target may be a feature;
- the authored-room-before-encounter relationship remains durable
  decomposition/authoring context while both nodes are deferred features;
- once Progressive Decomposition creates concrete descendants, the real
  executable dependency may be placed between the concrete
  implementation/artifact nodes.

## Finding 2 — writer-lock overreach

The patch makes exclusive-resource findings evidence-based.

A task gets a scene/builder/file lock only when it is expected to modify,
regenerate, configure, or integrate through that exact resource.

It explicitly prevents blanket propagation of prototype-scene/builder locks to
registry, enemy-health, pursuit/search, status/displacement, and encounter-cap
work merely because those systems eventually exist in the scene.

It also preserves the high-confidence navigation/world collision:

- if `gameplay-navigation-locomotion` configures its navigation surface through
  the same prototype builder/scene as `world-visual-foundation`, the refiner
  normalizes the same locks across those two actual writers;
- if repository evidence shows otherwise, it does not invent the lock.

The refiner also removes overbroad locks from read-only consumers.

## Safety

This patch does NOT modify:

- `Pipeline/Reconciliation/prompts/reconcile.md`
- either GDD file
- reconciliation snapshots
- `Tasks/*.yaml`

The apply script contains no GDD installation/copy/move logic.
