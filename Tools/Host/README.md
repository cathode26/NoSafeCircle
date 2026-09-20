# Host tool source snapshots

These files preserve the current authored host tooling in the main repository.
The original deployment folders remain in place. This import does not deploy,
synchronize, start, approve, repair, or change the behavior of any tool.

The copied files retain their original bytes and family-relative paths. The
local `.gitattributes` disables line-ending normalization for these snapshots.
Source and destination SHA-256 hashes and every excluded file disposition are
recorded in the tracked [source map](source-map.json). The original validation
copy is also retained under
`C:/Users/VincentLiguori/Downloads/NoSafeCircleOutput/Track-Unversioned/20260920-023734/`.

| Repository directory | Original deployment root | Purpose |
| --- | --- | --- |
| `art/` | `C:/NSC/tools/art/` | Art-review CLI, tests, README and existing provenance |
| `astra/` | `C:/NSC/tools/astra/` | Advice-session helper, primer and tests |
| `ger/` | `C:/NSC/tools/ger/` | GER runners, contract helpers, addenda and related source |
| `jobs/` | `C:/NSC/tools/jobs/` | Job launcher, propagation checker, helper scripts and tests |
| `jobs/templates/` | `C:/nscrev/claude-jobs/templates/` | Authored job prompt templates used by the job workflow |
| `session/` | `C:/NSC/tools/session/` | Session digest utility and operating documentation |
| `viewer/` | `C:/NSC/tools/viewer/` | Viewer process, overlay and evidence-inspection helpers |

Historical `C:/nscrev/art-tools`, `astra`, `ger-tools`, `job-tools`,
`session-tools` and `viewer-tools` paths may be deployment junctions. Existing
source and documentation still contain those paths. No paths were rewritten by
this import, and running a copied script can still reach its configured live
repositories, services, records or output folders.

## Scope and limitations

- These are source snapshots, not a new launch interface. Existing operating
  authority, paused-work restrictions, review holds and task approvals still
  apply. Copying a script does not authorize its actions.
- Some GER scripts are dated one-off operations, including
  `apply_room_decisions.py`, `apply_runbook_update.py`,
  `merge_all_branches.py` and `salvage_ger.py`. They are preserved as authored
  source, not instructions to rerun them. The runbook draft and dated feedback
  files keep their original names and status.
- `ger/main_write.py` records journal markers. It does not implement an
  operating-system mutex or the generation check needed to reject an old
  worker after undo.
- The art export keeps its original `PROVENANCE.md`, including the accepted
  numeric-edge limitation. Historical acceptance and test results in imported
  documentation were not rerun by this import.
- External dependencies such as Git, provider CLIs, Docker, the canonical
  `Pipeline` modules and live configuration remain external requirements.
  Credentials, active sessions, task state, output directories and processes
  are not recreated by checking out these source files.
- Python files were parsed with `ast.parse` without importing or running them.
  This checks syntax only. Functional, provider, Docker and Unity tests were
  not run. The existing invalid-escape warning in
  `jobs/tests/test_run_job.py:885` is preserved unchanged.

## Material retained outside this source import

Nothing was deleted or moved. The evidence map records exact paths and reasons
for excluded material:

- Python caches remain generated local files.
- `*.bak.py` files retain historical pre-fix implementations beside the live
  tools. Their exclusion does not assert semantic equivalence or authorize
  deletion.
- `ger/next/` contains staged alternative source and its staging tests; it is
  not adopted as current deployed code.
- `ger/patches/` contains dated migration scripts, task-specific candidate
  inputs and run outputs. `ger/issue127/` contains historical comment bodies
  and mutable issue-watching state.
- `ger/addenda/generated/` contains generated per-task prompts; reusable
  addenda and authored notes are included.
- `session/digests/` contains generated session evidence. It remains in its
  original location for a separate evidence-retention decision.

Versioning these tools makes their source recoverable. Task undo still needs
explicit checkpoints for the external state that a task owns and coordination
with workers and every publication path.
