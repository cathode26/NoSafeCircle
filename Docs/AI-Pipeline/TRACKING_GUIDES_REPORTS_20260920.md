# Authored guides and durable reports: source import

This follow-up to the [first tracking import](TRACKING_IMPORT_20260920.md)
preserves the remaining authored Markdown at `C:/NSC` and durable evidence under
`C:/nscrev/reports`. Vincent requested this work before cleanup or task undo.
Original files remain in place. No cleanup, deletion, deployment, task execution,
or live task-state migration is part of this change.

## Coverage

| Collection | Inventoried | New copies | Already in Git | Same-import duplicates | Held |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Host guides, reports, handoffs and prompts](Agent-Operations/host-documents-20260920/README.md) | 84 | 81 | 3 | 0 | 0 |
| [Host reports and supporting evidence](Historical-Context-Sessions/reports/host-reports-20260920/README.md) | 691 | 645 | 26 | 17 | 3 |
| [Art reports and supporting figures](Historical-Context-Sessions/reports/art-reports-20260920/README.md) | 3,292 | 1,041 | 1,750 | 490 | 11 |
| Total | 4,067 | 1,767 | 1,779 | 507 | 14 |

The 1,767 new original files contain 107,914,658 bytes. Every inventoried file has
a recorded disposition. Exact duplicates point to preserved repository files;
they are not removed from their original folders. Each collection has a source
map with original paths, repository destinations, byte counts and SHA-256 hashes.
The report indexes make deduplicated attachments findable.

The 14 held files are caches, synthetic collision-probe fixtures and one live
coordination board. Their reasons are recorded in the source maps. They remain
on disk. Exclusion from this import is not permission to delete them.

## How to use the preserved material

All originals are dated historical evidence. Role guides, launch prompts,
cleanup commands, old approvals, status reports, test results and candidate
patches retain their original wording and dates. Importing them does not renew
their authority or prove their claims against today's project state. In
particular, superseded backup/archive plans remain superseded, and old baseline
commit IDs remain accurate historical context rather than being rewritten.

The external `C:/NSC/CLAUDE.md` is preserved as an original under the host-document
collection. It does not replace the repository's active instructions. Use
[Agent Operations](Agent-Operations/README.md), root `AGENTS.md`, and current
maintained repository documentation to locate active guidance.

Preserved scripts and patches are evidence only. Many still name live host paths;
do not run or apply them merely because they are committed. Unity scenes, assets,
images and logs here are report attachments, not replacements for production
content or fresh delivery evidence. Historical PASS text is not a new test run.

Future maintained guides and settled reports should be authored or deliberately
landed in the repository. Keep these exact originals immutable; make subsequent
guidance changes in a maintained document and link it from the current index.
There is no automatic synchronization with the external copies. Live credentials,
leases, task approvals, worker records and process state remain outside this
source import; task undo still needs explicit checkpoint and restore behavior.

## Validation

This is evidence-preservation verification: source hashes, copied bytes,
repository blob identity, complete inventory coverage and new index links.
No historical script, provider job or Unity validation was rerun. The existing
Git identity-guard smoke test passed for the publication identity.

Gitleaks 8.30.1 scans use full redaction and archive traversal. The initial source
scan found one generic-key match in the art death-look download script: review
identified a PixelLab object UUID used in an object-download URL, not an
authentication credential. The finding is recorded rather than hidden by a broad
allowlist. The authored-host-document scan found no leaks. Final selected-file
and commit scans and byte-verification receipts are retained with this run's
handoff.

The reviewed starting commit is `c90a1ec22d6fc9f3289aa29fa4ae8b2e813f4c9a`.
This change stays in documentation plus narrow ignore/attribute rules; it does
not change `Tasks/`, `Pipeline/TaskGraph/`, or the authoritative validation policy.
Publication receipts and final remote verification belong in
`Downloads/NoSafeCircleOutput/Track-Guides-Reports/20260920-025406/`.
