# Previously untracked material: first source import

Vincent authorized tracking the identified material first, before cleanup and
before task undo. This change copies useful source and historical evidence into
the canonical repository. It does not delete or move existing copies, deploy
tools, execute historical launchers, change live task state or implement undo.

## Included material

| Material | Files | Tracked destination and provenance |
| --- | ---: | --- |
| Host tools, tests, documentation and six job prompt templates | 85 | [Tools/Host](../../Tools/Host/README.md), [source map](../../Tools/Host/source-map.json) |
| Three host guides and five loose AssistantControl utility scripts | 8 | [Agent Operations](Agent-Operations/README.md), [source map](Agent-Operations/source-map.json) |
| Previously ignored architecture-review and execution-crew outputs | 278 | [Historical project outputs](Historical-Context-Sessions/reports/untracked-project-outputs-20260920/README.md), [provenance](Historical-Context-Sessions/reports/untracked-project-outputs-20260920/provenance.json) |

The import preserves 371 original files, plus indexes, provenance and tracking
guidance. All originals remain where they were. The file maps record the original
paths, SHA-256 hashes, copied bytes and excluded material. Git attributes preserve
the bytes of imported sources and historical evidence. A narrow ignore exception
admits the 50 retained evidence logs without changing live Unity/cache ignores.

The tool families are art, Astra advice, GER, jobs, session utilities and viewer
utilities. The loose scripts include two reusable source candidates and three
explicitly historical task scripts. Existing review holds, known limitations and
runtime dependencies are documented alongside the copies.

## Meaning of source ownership

Future maintained host-tool source belongs in the tracked location. Existing
external folders remain deployment copies until a deliberate, authorized update.
There is no automatic synchronization in either direction. Imported scripts still
contain their original host paths and can act on live state if run; this change
does not make them safe new entry points or endorse old commands.

Historical guides, generated reports, raw logs and candidate patches are evidence.
They do not grant current authority, establish task completion, or demonstrate
that a candidate patch has not already been incorporated. Superseded cleanup and
archive instructions remain superseded. Current instructions are indexed in
[Agent Operations](Agent-Operations/README.md).

## Material deliberately left outside this import

- Live controller records, approvals, worker leases, provider configuration,
  credentials, active sessions, process locks and machine caches remain external.
  A later undo task must define which task-owned state to checkpoint and how to
  invalidate old worker authority. Tracking source alone cannot do that.
- The host-tools map lists 98 excluded files and two cache directories. These
  include historical backup implementations, staged alternative GER source,
  generated prompts, issue-watching records and session digests. They remain in
  place; exclusion is not a claim that they are redundant or permission to delete.
- Other historical clones, branches, profile session folders and unrelated loose
  files were not swept. Vincent selected the already-identified material for this
  task; wider historical consolidation is a separate scope.
- The disposable undo-comparison prototype remains experimental. It is not
  installed as production undo code by this import.

## Validation boundary

Sources were copied with before/after SHA-256 checks. Python syntax was checked
without importing the copied programs. Gitleaks 8.30.1 scanned the imported tools,
guides and evidence with full redaction and archive traversal; its initial scans
reported no leaks. The existing Git identity-guard regression passed. No Unity,
provider, Docker or historical mutating tool run was used to validate this copy.

These checks establish preservation and bounded source hygiene, not functional
certification of the imported utilities. Final commit/publication and Git-blob
verification receipts belong to the task handoff under
`Downloads/NoSafeCircleOutput/Track-Unversioned/20260920-023734/`.
