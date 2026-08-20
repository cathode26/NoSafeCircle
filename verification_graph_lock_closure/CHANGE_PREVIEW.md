# Expected Prompt Changes

## structure_auditor.md

- Replaces the stale expected relationship that directly listed encounter
  content -> five-room content.
- Clarifies that authored-room dependency becomes an executable edge only after
  a concrete implementation/artifact target exists.
- Adds positive-write-evidence requirements for scene/builder locks.
- Adds a narrow navigation/world shared-writer check.

## refiner.md

- Rewrites the older encounter dependency repair rule so it cannot produce a
  feature-target edge.
- Adds evidence-based resource-lock repair.
- Normalizes navigation/world scene-builder locks only when both are actual
  writers.
- Removes overbroad locks from read-only consumers.
