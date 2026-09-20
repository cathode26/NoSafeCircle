# Art Director historical reports and attachments

This collection preserves reports from `C:/nscrev/reports/art-director` as inert
historical evidence. Original files remain in place. No source script, patch,
provider request, Unity test, file cleanup, or recorded instruction was executed.
Historical approvals and test claims remain historical claims; importing them
does not approve assets, spend, delivery or new work.

[Report index](report-index.md) links the retained Markdown reports.
[source-map.json](source-map.json) accounts for every enumerated source file,
its original relative and absolute path, exact SHA-256, byte count, disposition,
and repository destination.

## Selection and duplicate handling

Durable reports, plans, findings, provenance, measurements, patches and evidence
scripts are retained alongside supporting NSC-generated art, review sheets, GIFs,
comparison renders and generation records. These include unselected candidates:
they explain historical decisions and are not promoted into runtime Assets.

Existing byte-identical Git blobs are referenced instead of copied. Identical
sources inside this import share one copied destination. For already-tracked destinations, hashes
refer to Git blob bytes; a Windows checkout may use different line endings.
New original copies retain their source bytes both on disk and in Git. Each
source has its own map entry. `duplicate-in-import` with `deduplicated: true` means a shared
copied destination, not a separate file. Long output paths use `originals/_long-path/<sha256>.<ext>`
to remain practical on Windows; the source map retains their original names.

The original Markdown files contain no relative Markdown links. Their prose,
code examples and absolute historical paths remain unchanged. Use the source
map to locate a mentioned attachment; the imported directories are not promised
to be runnable reconstructions of historical staging trees. The generated report
index links only verified retained destinations.

Held files are generated Python caches and reproducible synthetic collision-test
fixtures. They remain at their original paths and are fully enumerated and
hashed. The corresponding probe scripts and result summaries are retained.
No deletion or disposition of the originals is authorized by this collection.

## Provenance and validation

The inspected art provenance describes NSC PixelLab generations, committed project
art and locally rendered review figures. The NSC-064 `reference` images are
authored wall-projection comparisons, not external ReferenceProjects assets. No
raw third-party reference source was identified or imported from external
reference projects.

Source hashes were checked before and after copying. Copies and existing Git
blobs were verified against the source SHA-256. This proves preserved bytes, not
art correctness, historical test results or permission to run the scripts.

One scanner match at `nsc015-death-looks-20260917/fetch.py:9` was classified as a
false positive: it is a PixelLab asset object UUID used as an `object_id`, not an
API credential. The classification is recorded without the matched value in
the source map.
