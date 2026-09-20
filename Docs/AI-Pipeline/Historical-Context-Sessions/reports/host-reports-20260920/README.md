# Historical host reports and supporting evidence

This collection preserves durable reports and necessary attachments found under
`C:/nscrev/reports/` on 2026-09-20. The `art-director/` subtree belongs to a
separate import. Existing source files remain untouched.

These are historical records, not current operating guidance or new approvals.
They include agent reviews and recovery digests, Unity logs and XML results,
validation manifests, screenshots, patches, script source, and dated work
inventories. Generated responses can contain obsolete or incorrect advice.
Dated PASS claims are preserved as recorded; this import does not rerun or
endorse those checks, infer human approval, or establish task delivery.

Do not execute copied scripts, apply patches, launch providers, follow cleanup
commands, or restore task state merely because the evidence is now tracked.
The source copies can still name live absolute host paths. Current repository
guidance and explicit task authorization control any future work.

## Coverage and exact-byte deduplication

| Disposition | Source files | Meaning |
| --- | ---: | --- |
| Copied | 645 | Unique historical reports or supporting snapshots copied below `originals/` |
| Already tracked | 26 | Exact bytes already present in the base Git tree and checked-out tracked file |
| Duplicate in this import | 17 | Exact bytes preserved once by another row in this collection |
| Held | 3 | Two generated Python bytecode files and the live `handoffs/BOARD.md` |
| Inventoried total | 691 | All scoped source files have a recorded disposition |

The inventory covers 95,984,123 source bytes; newly copied original files total
83,578,930 bytes. SHA-256 equality determines byte identity; filename similarity
does not. No originals were deleted or consolidated on the host.

Use [FILES.md](FILES.md) to find each source path and its preserved file. The
[source map](source-map.json) records original absolute and source-relative
paths, repository-relative destinations, byte counts, hashes, source modification
times, before/after source hashes, and hold reasons. Duplicated attachments may
live at another mapped destination instead of their old relative location.
Original report links and file contents were left byte-identical; the index and
source map resolve these historical references without altering their evidence.

## Capture and exclusions

Each copied source was checked for stable bytes before capture and again after
copying; the destination SHA-256 matched the source. No changing source was
observed. Existing-file deduplication also required an identical base Git blob
and identical bytes in the checked-out file.

The active coordination board remains at its live location. Python bytecode is
a reproducible cache; its authored script source is preserved where selected.
The two dated workspace-registry receipts are retained as immutable historical
evidence, not installed as live registry entries. A registry receipt or inventory
in this collection does not authorize removal or certify any workspace safe to
delete.

A preliminary known-token/private-key signature screen found no potential
credential matches. The preservation change has a separate secret scan before
publication. This inventory does not import credential stores or run historical
scripts, tests, providers, cleanup actions, or task controllers.
