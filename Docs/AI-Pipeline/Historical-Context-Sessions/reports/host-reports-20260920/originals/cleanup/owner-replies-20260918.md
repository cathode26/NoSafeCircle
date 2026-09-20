# Owner replies to the Cleanup Agent's 21:18 message (2026-09-18)

All eight agents answered (Art Director, Decomposition, Documentation, Game, GER, Pipeline Maintainer, Release, Viewer). Every reply is a keep or release **request**, not a removal order; nothing here authorises a move. Anything I marked "verified" was checked on disk at ~21:35 CDT.

## Nothing in `C:\NSC\_worktrees`
Release, Viewer, GER, Decomposition and Art Director each said they hold nothing there. **But** the Decomposition Agent's citation scan (`C:\nscrev\reports\cleanup-cited-dirs-20260918.txt`) lists `C:\NSC\_worktrees` as cited by committed contracts or agent definitions, so the folder as a whole is a live reference. Any `_worktrees` plan has to name individual worktrees, never the folder.

## KEEP list, merged (all C:\nscrev unless stated)
| folder | who | why |
|---|---|---|
| `reports` | Release, GER, Viewer, Decomp, PM | records, `handoffs\BOARD.md`, uncommitted art deliverables under `art-director\` with contract-pinned sha256s. Never narrow. |
| `ci-fix-executioncrew-coverage` | Release | dirty, uncommitted workflow edit |
| `ci-134-fix` | Release, PM | holds `fix/retired-auditor-test-debt` `ca13f7511`, and is a propagation-check fixture |
| `claude-jobs`, `codex-jobs`, `job-tools`, `session-tools` | Release, Decomp | job records and tools |
| `codex-jobs\codex-art-review-toolkit-20260917-0021` | Art Director | build clone with three review rounds. "Don't delete, moving is fine." |
| `art-tools` | Art Director | only working home of the approved art-review toolkit (`Pipeline/ArtReview` is on no branch of main) |
| `ger-contract-revisions-20260916`, `ger-tools`, `ger-tools-dev\g15b\live-backup-20260918` | GER | only copies of `new_task_commit.py`, `policy_entry_commit.py`, `verify_filter.py`; live committers; rollback copy |
| `viewer-tools`, `reports\viewer-agent`, `reports\viewer-agent-job-corpus.md` | Viewer | live tooling |
| `viewer-step1-fix` (**verified**: this is the clone holding `fix/viewer-step1` `389f119f3`; canonical already has the object), `viewer-step1-tmp` (plain directory, no `.git`), `viewer-stage-detail` (branch `fix/viewer-execution-crew-stage-detail`) | Viewer, PM | PM did not know which of the three held the commit; it is `viewer-step1-fix`. All three stay kept until PM says otherwise. |
| `decomp-snapshot`, `mixed-provider-env` | PM | `fix/decompose-on-a-snapshot` `65b8377de`; `fix/mixed-provider-model-env` `d79bc26a9` awaiting Vincent's go |
| `fixrepo` | PM | live |
| `branch-verify` | Game Agent | `evidence/nsc-089-091-20260918` `39a8d17e8`, four delivery records awaiting Vincent's fast-forward; disposable once main reaches `39a8d17e8` |
| `C:\NSC\NSC`, `C:\NSC\agent-state`, `C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control` | Decomp | live records; the unapplied NSC-007 decomposition plan freezes every GER contract commit, so nothing under `.assistant-control` moves until it is applied |
| `review-tmp` | PM, Decomp (`pipeline-reviewer` definition cites it) | **Release Agent listed it as removable; that conflicts** with the PM and Decomposition keeps. **Keep.** 2,354 MB, no `.git`. |
| `release-pages`, `release-webgl` | Release (via guide), Decomp | live |

## RELEASED (owner says disposable). I verified each on disk; nothing is planned yet
| folder | owner | size | state found |
|---|---|---|---|
| `ci-fix-stale-viewer-ids` | Release | 206 MB | clean, HEAD in main, branches all known to canonical |
| `ci-fix-unity-whitespace` | Release | 207 MB | clean, HEAD in main, all known |
| `cj-ws-advice` | Release | 219 MB | clean, detached at `255951482`, in main |
| `gdd-edit-20260917` | Documentation | 204 MB | clean, all 6 branches known to canonical. (My guide listed it as always-in-use; the Documentation Agent's word supersedes, since GDD edits always use a fresh clone.) |
| `gdd-edit-tmp` | Documentation | 2 MB | plain directory, no `.git` |
| `art-docfix-20260917` | Documentation, Art Director | 211 MB | clean, all 4 branches known; fix landed as `a7e684d20` |
| `art-rejects-078` | Art Director | 218 MB | clean; `art-rejects/NSC-078` known to canonical. **The branch must never be deleted** (GER: NSC-078 rev 4 contract text). Removing the clone only is fine. |

**Held back although the owner called it scratch:** `tmp-ga` (Release Agent). 1 MB, but it is on branch `master` at `dd975db1a9a6...`, **a commit canonical has never seen**, with 1 changed file. Cannot verify it is worthless, so it stays.

## Judgement calls
- The Pipeline Maintainer's message states `MOVE-NSCREV.ps1` and `MOVE-NSC-FOLDERS.ps1` "are yours now". So the lane overlap the Game, GER, Art Director and Decomposition agents each warned about is closed by that handover: one owner, and no move happens except through a script I write and Vincent runs.
- **Junctions.** The PM says Vincent approved moving `ger-tools`, `job-tools`, `viewer-tools`, `astra`, `session-tools`, `art-tools` to `C:\NSC\tools\` with a directory junction at each old path. Any walk of `C:\nscrev` must test `LinkType` and never follow or "clean up" a junction. **Verified 21:35: the move has already run.** All six are junctions now: `ger-tools` to `C:\NSC\tools\ger`, `job-tools` to `tools\jobs`, `viewer-tools` to `tools\viewer`, `astra` to `tools\astra`, `session-tools` to `tools\session`, `art-tools` to `tools\art`. The safety scan I ran at 21:25 was read-only and depth 1, so it counted them as directories but changed nothing; every later scan must skip them.
- **Standing rules repeated by four agents:** never delete an `NSC-###` branch, and never delete `art-rejects/NSC-078` or `art-rejects/NSC-095`. Both go into every branch script as hard skips.
- **Aged reports the GER Agent gives me:** `ger-20260914`, `ger-salvage-20260914`, `ger-agent-runbook-validation-20260914-nsc044`, `ger-packet-clone-20260917`, `g15-ger-tools-test`, `ger-preparer-fix` are "mine to decide". `ger-salvage-20260914` is cited by `nsc-ger-orchestrator-guide.md`; not planned until checked.
