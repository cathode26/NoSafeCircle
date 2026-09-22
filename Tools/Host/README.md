# Host tool source

**`Tools/Host/<family>/` is the source of record for host tooling. Edit here first.**
`C:/NSC/tools/<family>/` and the `C:/nscrev/<family>-tools` junctions are **deployments**, not
masters — see [maintained-locations.md](../../Docs/AI-Pipeline/Agent-Operations/maintained-locations.md).
When you change a tool, change the tracked source, then deploy, and record the source revision you
deployed from.

**That rule is the intent; the files below arrived as snapshots and some have not caught up yet.**
The original deployment folders remain in place. The import itself did not deploy, synchronize,
start, approve, repair, or change the behavior of any tool, so **a tracked file here is not
automatically the version a caller runs** — check before assuming.

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
| `ger-contract-revisions-20260916/` | `C:/nscrev/ger-contract-revisions-20260916/` | GER contract committers and helpers (`bbfca9253`, 2026-09-20). **Reconciled with their live copies in `9c8f91fa8`** — see the note below for what that drift was and why it is worth re-checking |
| `codex-jobs/` | `C:/nscrev/codex-jobs/` | Codex job runners and prompt templates (`c6f9c8e3b`, 2026-09-20) |
| `cleanup/` | `C:/NSC/tools/cleanup/` | Recursive-delete depth guard (runbook rule 26), its tests, and the only-copy sweep scripts. Tracked 2026-09-20 after the family was found to exist only at the deployment root |

> **`source-map.json` does not index the two families above, and must not be edited to.** It is a
> **receipt of the single 2026-09-20 02:37 import run** — its `destination_root` names that run's
> staging folder and every record carries that run's SHA-256 pair. Hand-adding later families would
> falsify a receipt. **This table is the index for readers;** a living source-to-deployment map, if
> one is wanted, is a separate artifact needing its own generator.

> **Preserved is not current — and the GER family is the worked example of catching it.** On
> 2026-09-20 the tracked `new_task_commit.py` and `policy_entry_commit.py` were older than their
> live copies: the tracked ones hardcoded `C:\nscrev\ger-tools` while the live ones had gained a
> preference block selecting `C:/NSC/tools/ger` first. **Reconciled in `9c8f91fa8`** — all three
> committers now hash-match their live copies, and the previously untracked
> `followups-20260917/`, `encounters/polish_rev4.py`, `briefs/encounters-030.md` and
> `cascade-015-017/decisions-applied.md` are tracked too. **Re-check before quoting this; the gap
> reappears the moment someone edits a deployed copy instead of the source.**

> **A snapshot does not retire its source, and neither folder is retirable yet.**
> `ger-contract-revisions-20260916/scratch/` **is its own Git repository, on `main`, with 53 dirty
> paths** — not a disposable cache, and not covered by anything here. Of `C:/nscrev/codex-jobs`,
> **20 files are tracked against 329 at the host top level**; the remainder is job evidence whose
> disposition nobody has decided. Deciding it is a separate inventory, not a consequence of this
> index — and recursive deletes at depth 1 or 2 from `C:\` are Vincent's to execute
> (`nsc-pipeline-runbook.md` rule 26).

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
- `ger/main_write.py` and `guarded_merge.py` share `main_write_lock.py` for
  exclusion in the actual mutation repository. See [MAIN_WRITE_LOCK.md](MAIN_WRITE_LOCK.md)
  for all five callers, explicit recovery, and the complete deployment set.
  This does not implement the generation check needed to reject an old worker
  after undo.
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
