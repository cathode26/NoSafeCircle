# State and plan review - 2026-09-18 (night)

Independent adversarial review. Brief: `adversarial-review-brief.md` (scratchpad of session 15411044).
Everything in Half 1 was checked on disk by running it. "Reproduced" means I ran it and saw it;
"read" means verified in the file but not executed; "theoretical" means reasoned only.

```text
STATE VERDICT: FIX FIRST   (4 blocking; no data has been lost tonight, but two things are broken now
                            and two more will lose data while reporting success)
PLAN  VERDICT: FIX FIRST   (3 blocking; the v2 closures of B1/B3/B4 are genuine, but v2 was written
                            75 minutes before the tools move and is already stale against it, and
                            the topology document does not exist)
```

`repo-topology-20260918.md` **does not exist.** Its job log (`repo-topology-job-20260918.log`) is
0 bytes. Half 2 reviews v2 alone, as the brief instructs.

---

## Half 1 - the state

### Blocking

**S1. `RESTORE.ps1` moves the folder, then crashes before it logs. The "empty RESTORES.md = nothing
was needed" proof is therefore always green. REPRODUCED.**
`C:\NSC-History-20260918\RESTORE.ps1:95`. The file is UTF-8 **without** a BOM and line 95 contains
two em dashes (bytes `E2 80 94`). Windows PowerShell 5.1 (the only PowerShell on this machine;
`pwsh` is not installed) reads a BOM-less script as Windows-1252, where byte `0x94` is a right
double quote, which PowerShell accepts as a string terminator. The string ends early and the rest
becomes stray arguments. The parser reports 0 errors, so nothing warns you.
- Sequence I ran: `RESTORE.ps1 -Name nscarch_work -Reason "..." -Apply`
- Result: `Move-Item` succeeded (folder landed at `C:\nscarch_work`, exactly where the manifest
  says), then the script threw `A positional parameter cannot be found that accepts argument`
  (naming the backtick-quoted folder name) and exited with an error. `RESTORES.md` sha256
  unchanged (`798E5CA2...`), LastWriteTime unchanged (21:00:07).
- Wrong outcome 1: the operator sees a red error and believes the restore failed. It did not.
  A second attempt then throws "Destination already exists".
- Wrong outcome 2 (the false green): on 2026-10-09 `RESTORES.md` is empty by construction, no
  matter how many restores happened, and README and RESTORES.md both say an empty list means
  "delete wholesale without an audit".
- Same family as the manifest BOM bug found tonight, in the mirror direction: there a BOM that
  only PowerShell tolerated; here a missing BOM that only PowerShell mis-reads.
- Fix is one line (replace the two em dashes with `-`, or save the script with a BOM). Then
  re-run the round trip; nobody has ever seen this script succeed end to end.

**S2. `ask_astra.py` refuses every command since the tools move, while its 62 unit tests pass.
REPRODUCED.** "Nothing broke" is false.
`C:\NSC\tools\astra\ask_astra.py:56` `HOME = C:\nscrev\astra`; `:73` `FORBIDDEN_TEMP_ROOT = C:\NSC`;
`:447-459` `_under_forbidden_root(HOME)` calls `HOME.resolve()`, which now follows the junction
to `C:\NSC\tools\astra`; `:791` runs that guard before every subcommand.
- `python -B C:\nscrev\astra\ask_astra.py status` -> `astra: refusing to work under C:\NSC:
  NSC_ASTRA_HOME=C:\nscrev\astra`, exit 3. Same via `C:\NSC\tools\astra\ask_astra.py`.
- `python -B C:\NSC\tools\astra\tests\test_ask_astra.py` -> `Ran 62 tests ... OK` (the tests set
  `NSC_ASTRA_HOME` to scratch, so they never see the live path). Green suite, dead tool.
- Any agent that follows its guide and asks Astra gets exit 3 and the fallback message. The
  guard is deliberate and correct; the move put the state of the tool (thread, answers, log,
  tmp) inside the tree the tool is written to refuse.
- Fix options: move `astra` back out of `C:\NSC` (its state is not a tool), or split code from
  state and point `NSC_ASTRA_HOME` at a folder under `C:\nscrev`. Do not weaken the guard.

**S3. The two pending Cleanup scripts write manifest entries `RESTORE.ps1` cannot restore, and one
re-introduces the BOM bug. READ (scripts not applied yet: no `from-NSC` or `from-nscrev` exists).**
- `MOVE-NSC-FOLDERS.ps1:48` says "RESTORE.ps1 covers this script's moves too without any change".
  It does not. `RESTORE.ps1:43` looks for `<HistoryRoot>\<Name>`; these scripts put things at
  `<HistoryRoot>\from-NSC\<Name>` (`:68`) and `<HistoryRoot>\from-nscrev\<Name>`
  (`MOVE-NSCREV.ps1:35`). Every restore of the planned 416 directories (~100 GB) would throw
  "Not found in the history folder". The manifest `Dest` field is recorded and never read.
- `RESTORE.ps1:44` requires `-PathType Container`: the 138 planned **file** moves can never be
  restored by it.
- `RESTORE.ps1:53` takes the first manifest entry with a matching `Name`. `tmp`, `scratch`,
  `test-temp`, `TestTemp` are on the C:\NSC list and the same names are plausible under
  `C:\nscrev`; a collision restores to the wrong `Source`.
- `MOVE-NSC-FOLDERS.ps1:839` and `:868` write the manifest with `Set-Content -Encoding utf8`,
  which is exactly the BOM bug "found and fixed in two scripts" tonight. This third script was
  saved at 21:07, after the fix. First `-Apply` puts the BOM back and python readers break
  again. The claim "fixed" is true of `MOVE-TO-HISTORY.ps1:163`, `MOVE-STRAGGLERS.ps1:200` and
  `MOVE-NSCREV.ps1:226` only.
- robocopy `/MOVE` is copy-then-delete, not a rename. A run that exits >= 8 leaves a directory
  split across source and destination with **no manifest entry**, and every re-run says
  "SKIP (destination exists)". For a git clone that is a stuck, unrecorded half-repo.
- Do not run either script with `-Apply` until `RESTORE.ps1` reads `Dest`, handles files, and a
  round trip of one `from-NSC` item has been seen to work.

**S4. "Whatever is still here on 2026-10-09 is junk by construction" is false for 19 of the 28
quarantined clones. REPRODUCED (read-only git queries).**
For every `Type=clone` entry I asked the canonical repo (`C:\NSC\NSC\NoSafeCircle`) whether it has
each local branch tip:
- 19 clones hold at least one branch tip that is **absent from the canonical object store**
  (e.g. `nscfixrace fix/coherent-snapshot-apply-race 45cc192`, `nscwarm
  fix/warm-unity-library 3f92ff4` and `fix/ilpp-pid-minimal 63b5712`, `nscfixeol`, `nscfixsnap`,
  `nscdel`, `nscmerge integration/verify-20260905`). These are clones of
  `NoSafeCircle-Homework-Rehearsal` or of each other; the fix branches have no upstream.
  I did not query GitHub, so "exists nowhere else" is unproven, but nothing on this machine
  outside the history folder has them.
- 3 clones were moved dirty, as the manifest itself records: `nscint` (1), `nscrev911` (7),
  `nscrev911c` (7).
- Several `origin` URLs are other quarantined folders (`nscdel -> file:///C:/nscarch`), so the
  chain only works while all of them are restored together.
- Only 9 of 28 clones are clean with every tip known to canonical.
- Failure sequence: nobody opens the folder for three weeks (or someone does and hits S1) ->
  `RESTORES.md` empty -> folder deleted "without an audit" -> two weeks of rehearsal-era fix
  branches and 15 uncommitted changes are gone, and the record says nothing was needed.
- These may well be worthless. That is a call for the owner, and the scheme as written makes it
  for him. Cheapest fix: one `git bundle create --all` per clone into the step-1 OneDrive
  folder before the review date, or change the README from "delete without an audit" to "delete
  after reading the MANIFEST.json State column and this list".

### Major

**S5. `robocopy /MOVE /E` without `/XJ` run against a junction moves the contents of the junction
*target* away. REPRODUCED in a throwaway sandbox.** `MOVE-NSCREV.ps1:208` uses exactly that form
(no `/XJ`; the other two robocopy scripts do pass `/XJ`). Sandbox results:

| Operation on a junction (or its parent) | Target files after |
|---|---|
| PS 5.1 recursive forced delete of the parent, or of the junction | intact (safe) |
| cmd recursive quiet rmdir of the parent | intact (safe) |
| python 3.13 `shutil.rmtree` on the parent | intact; on the junction itself it refuses |
| `Move-Item` on the junction | intact; the junction moves as a junction |
| `robocopy /MOVE /E /XJ` on the parent | intact; junction left behind, script reports PARTIAL |
| **`robocopy /MOVE /E` (no /XJ), junction as source** | **0 files left in target** |
| **`robocopy /MOVE /E` (no /XJ), parent containing junction** | **0 files left in target** |

Today the six junction names are on the `$Keep` list in `MOVE-NSCREV.ps1` (`:45-67`), and that
list is the only thing between the Cleanup Agent and `C:\NSC\tools` being emptied into the history
folder. One renamed junction, one trimmed list entry, or a junction nested inside any other
`C:\nscrev` folder, and the live tools move out from under six sessions with robocopy exit code 1
(which the script counts as success). Add `/XJ` to line 208 and refuse any candidate whose
`LinkType` is set.
Reboot survival, recursive delete and "a tool resolving its own path" are **not** hazards
(junctions are persistent NTFS reparse points; `resolve()` returns the `C:\NSC\tools` path, which
only matters for S2). Double counting **is** real: git follows junctions (tested: `git add -A` in
a tree containing a junction staged `linked-tools/tool.py`), see P1.

**S6. Tools that did not move depend on the junctions, in code the doc sweep cannot see.**
Removing the junctions "after the doc sweep" breaks all of these:
- `C:\nscrev\ger-contract-revisions-20260916\new_task_commit.py:32`, `policy_entry_commit.py:24`,
  `validate_in_memory.py:17` - each inserts `C:\nscrev\ger-tools` at the front of `sys.path`.
  These are the only copies of the tools that create tasks and policy entries on `main`.
  Inserting a missing folder into `sys.path` is silent; `new_task_commit.py` then imports its
  **local, divergent** `main_write.py` (58 lines, 09-17 01:00) instead of the installed 114-line
  one, and fails later on `import apply_contract`. Loud, but only at the moment the GER Agent
  needs it.
- `C:\NSC\tools\ger\next\test_live_prompts.py:14`, `test_recommendation_parser.py:12`,
  `test_staged_prompts.py:14` - `TOOLS = C:\nscrev\ger-tools`. If anyone later recreates that
  folder with a stale copy, these tests pass against the stale copy.
- `C:\NSC\tools\ger\salvage_ger.py:21`, `apply_runbook_update.py:14,97`, seven files under
  `ger\patches` - read and **write** under `C:\nscrev\ger-tools` through the junction.
- `C:\NSC\tools\viewer\audit_evidence_debt.py:168` writes `audit_raw.json` to
  `C:\nscrev\viewer-tools`, i.e. silently into `C:\NSC\tools\viewer`.
- Not broken, verified: `run_job.py:56` (`NSCREV`, `claude-jobs` did not move; its test file
  runs OK), `nsc_session_digest.py:33` (`reports\agent-recovery` did not move),
  `propagation_check.py`, `nsc_viewer.py`, `ger_node.py` (`--help` works by both paths).
  `hold_ger_task.py --help` fails with a missing `Pipeline` module, but that is cwd-dependence
  (line 29), not the move.

**S7. The fleet rules now contradict the location of the tools.**
`pipeline-reviewer.md:35,43` ("nothing under `C:\NSC` was written"), `pipeline-maintainer.md:85`,
`test-runner.md:24` ("Never write under `C:\NSC`") against `pipeline-maintainer.md:18` ("the helper
scripts under `C:\NSC\tools\viewer` and `C:\NSC\tools\ger`"). Every future fix to a helper script
is a write under `C:\NSC`. Either the reviewer fails every such fix on scope, or reviewers learn
to wave the rule through, which is how a guard dies. Python cache folders already exist in
`C:\NSC\tools\viewer` and under `art\ArtReview\art_review`. The rule needs an explicit carve-out
or the tools need a different home; that is a topology decision (P3).

**S8. Divergent copies (brief Q5).** `main_write.py` exists twice and differs (58 vs 114 lines);
`C:\NSC\tools\ger\main_write.py` is authoritative (its header says it was ported from the other).
The other eight `.py` in `ger-contract-revisions-20260916` exist only there, as claimed.
`C:\nscrev\ger-tools-dev` (57 files) is a third partial copy, labelled a rollback copy. No tool
exists at both ends of a junction as separate files - a junction is one copy, confirmed.

### Minor

- `MANIFEST.json` `SizeMB` is null in all 45 entries; README line 33 says size is recorded.
- README line 28 says "empty (or absent)" `RESTORES.md` is proof; `RESTORES.md` itself says an
  absent file proves nothing. Pick one.
- PROVENANCE says `.assistant-control` "is now under version control". It is not: no `.git`, and
  `git -C C:\NSC rev-parse` fails. v2 only proposes it.
- "The manifest now parses in python **and jq**": python yes (45 entries, first bytes `5B 0D 0A`,
  no BOM). `jq` is not installed on this machine, so the jq half was never tested by anyone.
- `nscmin_work` came by robocopy: directory timestamps were reset to 2026-09-18 20:19 and ACLs
  are not carried by default `/COPY:DAT`. No pre-move hash exists, so equality with the original
  is unprovable. The cleanup log also records that a concurrent read-only scan broke the first
  move attempt - "scan inline while someone else moves" already collided once tonight.
- `nscaudit_main` worktree link is broken until `git worktree repair` (documented in both
  scripts; fine).
- `MOVE-NSC-FOLDERS.ps1:80` reference-grep list names `game-tools` (does not exist) and omits
  `job-tools` and `art-tools`, while its header says "the six tool folders".
- 24 old-path references remain in the `.claude` project memory folder (11 files, including
  `MEMORY.md`, which is loaded into every session) and about 28 in `agent-state`. They resolve
  only through the junctions. The brief calls the leftovers "dated handoffs and other agents
  state files"; memory is neither.

### Sound - checked and fine

- **Accounting:** 46 directories, 45 manifest entries, the 46th has its PROVENANCE file. Every
  `Source` is a folder directly under the C: root, none of them exists there today, all on the
  same volume: a restore would work against each. The C: root holds only `NSC`, `nscrev`,
  `NSC-History-20260918`.
- **Round trip, data half:** 51 files / 1.4 MB, sha256 of every file identical before, after
  restore, and after moving back; directory timestamp preserved (same-volume rename). Dry run
  moves nothing; `-Apply` without `-Reason` refuses before moving.
- **`.assistant-control`:** 58 MB. Quarantined clone HEAD `f7cb0f478` is an ancestor of `main` and
  of `origin/main`; `main` and `origin/main` are level (0/0); `NSC-074-current` still on disk; no
  non-`Library` changes, no stash, no branch off main. Every claim in PROVENANCE holds except the
  "under version control" sentence.
- **Doc sweep:** every distinct `C:\NSC\tools` path cited in the 80 docs, 14 agent
  definitions, memory and agent-state exists, except `C:\NSC\tools\ger\new_task.py`, which is a
  to-be-built tool (`pipeline-maintainer-agent.md:148`). No `tools\job`, no old folder name
  under `tools`. 0 stale references in non-handoff docs and agent definitions. No dated handoff
  was modified tonight except `nsc-handoff-20260918-night-pipeline-maintainer.md` (21:33, newly
  written).
- Junctions: all six resolve; survive reboot by construction; safe under every delete I tested.

### What cannot be undone

1. **The doc sweep.** 75 replacements across 21 files, none under version control, no pre-image
   kept that I could find. It is reversible only by a reverse substitution, and only because the
   mapping happens to be one-to-one.
2. **The original of `nscmin_work`.** Copy-then-delete: original gone, directory timestamps and
   ACLs not preserved, no hash to prove the copy equals it.
3. **Recency evidence in every quarantined clone.** The scans tonight ran `git status` in them,
   which rewrites the git index file. "Last touched" can no longer be read from the filesystem
   for any of them. (My own review added `for-each-ref` and `stash list` in 28 clones and one
   `git status` in `nsc074-unity-validation-f7cb0f47`.)
4. **Nothing else.** The 44 `Move-Item` moves, the Recycle Bin recovery and the six tool moves are
   same-volume renames and are reversible today; I proved one. They stop being reversible on
   2026-10-09 if the folder is deleted on the strength of an empty `RESTORES.md` (S1, S4).
5. **Not yet done, and irreversible in practice once done:** `MOVE-NSC-FOLDERS.ps1 -Apply` and
   `MOVE-NSCREV.ps1 -Apply` (S3). About 100 GB by copy-then-delete with a restore script that
   cannot find any of it.

### Exactly what I changed on this machine

- Ran `RESTORE.ps1 -Name nscarch_work -Reason "REVIEWER ROUND-TRIP TEST ..." -Apply`; it moved
  `C:\NSC-History-20260918\nscarch_work` to `C:\nscarch_work` and crashed before logging. I moved
  it back with `Move-Item`. Verified byte-identical; `MANIFEST.json` and `RESTORES.md` hashes
  unchanged. **The round trip left no trace in `RESTORES.md`, which is finding S1.**
- Wrote and then deleted a sandbox under `C:\nscrev\review-tmp\junction-sandbox-20260918`
  (throwaway files and junctions pointing only at themselves). Kept
  `C:\nscrev\review-tmp\roundtrip-before.txt` (the hash list).
- Ran the astra and run_job unit tests (fakes only, `TEMP` under `C:\nscrev\review-tmp`). They
  write their usual scratch under `C:\nscrev\tmp`.
- Read-only git queries as listed in item 3 above. Nothing written under `C:\NSC`. No Unity,
  Docker, provider or paid call.

---

## Half 2 - the plan (v2 alone)

### Does v2 close the v1 blockers? Yes for the three I sampled, against real source

- **B1** - closed by refusal, not by restating. The C7 hook moves to `main-write end`; the
  protocol is real (`C:\NSC\tools\ger\main_write.py:105-114` `start` and `end`;
  `contract_commit.py:305,314` already call them). "Empty ledger but `main` names the task =
  exit 2" is the right answer to the false green the first review found. Residual: the hook
  lives in unversioned helper scripts until step 7 ("weeks"), and step 8 correctly says so.
- **B3** - closed. Undo-edit as revision N+1 is compatible with the rule the tool enforces
  (`contract_commit.py:196`: revision must be current + 1) and its flags (`--task --revised
  --reason --policy-filters-file --commit` exist). `cancelled` is a real disposition
  (`current_conformance.py:361`). Section 3.5 states the cost honestly.
- **B4** - closed. `reset_task.py` really does have the three guards v2 lists (`:125` status,
  `:142` branch prefix, `:181-182` remote), `pre_task_commit` really is a local name for
  the `source_commit` record field (`:134`), and `main_write.py` really is in no ref of the game
  repo. The re-estimate to a new module and six branches is the honest one.
- Also verified as cited: `publication.py:194`, `source_update.py:366`, `main` = `255951482`,
  138 registered worktrees.

### Blocking

**P1. The v2 whitelists are stale against the tools move, and the failure is a green status.
READ + one sandbox test.**
v2 (20:04) tracks tools as "`nsc-reports`, work-tree `C:\nscrev`, scripts of `ger-tools`,
`job-tools`, `viewer-tools`, `astra`, `session-tools`" (section 1). At about 21:15 those became
junctions into `C:\NSC\tools`, and `nsc-ops` (work-tree `C:\NSC`) whitelists only top-level `.md`,
`agent-state` and top-level scripts - not `tools`. Git follows junctions (tested), so step 4
would work today by accident. Sequence: step 4 ships -> docs finish migrating -> junctions are
removed as planned -> the whitelisted paths no longer exist -> `git add` adds nothing, nothing is
"unknown", "skipped" or "oversize" (section 2.3), `ls-remote` shas match -> **`Backup 6 min`
stays green while the tools have silently left every repo.** The reverse mistake (adding `tools`
to `nsc-ops` while the junctions still exist) tracks the same 191 files in two repos, which is
the "stale second copy" section 1 says it avoids. Fix: whitelist the real path, and add a rule
that a whitelisted path which is missing, or has become a reparse point, turns the run red.

**P2. The plan and the Cleanup Agent are working the same directories with opposite intent.
REPRODUCED for the bundles.**
- v2 "new fact 2" and Q10: the 24 top-level `.bundle` files "may hold commits that exist nowhere
  else; the hub fetches from each". `MOVE-NSC-FOLDERS.ps1` lists **22 of those 24** for the
  history folder. I checked each bundle head against canonical: **6 hold a head commit canonical
  does not have** (`ThirdGauntletBootstrapCrossAudit` x2, `retire-abandoned-gate-waiter`,
  `run-evidence-scope-fix-ce23ce2`, `runner-drift-fix-6b4c141`, `supreview-6a6e615`); all 6 are on
  the move list. After `-Apply` the hub finds nothing to fetch (no error: roots are enumerated
  on every run), and on 2026-10-09 they are deleted.
- v2 puts every archive git dir and `status.json` under `C:\nscrev\backup`. `MOVE-NSCREV.ps1`
  classifies every `C:\nscrev` folder at run time and `backup` is not on its `$Keep` list. It is
  not a repo at its top level, so the only guard is "modified in the last 3 days". A backup job
  that has been dead for 3 days - the exact case the plan exists for - makes its own git dirs
  eligible to be moved by `robocopy /MOVE`. Theoretical, one line to fix, but it has to be written
  into whichever document ships second.
- The v2 hub fetches from "fix branches in `C:\nscrev` clones" while those clones are being
  classified and moved. A clone moved mid-fetch is a failed fetch at best.
- Neither document mentions the other. Someone has to own the order. Suggested: steps 1 and 2
  first, then freeze Cleanup `-Apply` on `C:\NSC` top-level files until the hub has fetched the
  bundles, then let Cleanup proceed.

**P3. There is no topology decision, and the tools move already made one that contradicts v2.**
The topology document does not exist. v2 D3 says tools belong in the game repo, held in
`nsc-reports` over `C:\nscrev` in the interim. Tonight they went to `C:\NSC\tools`, a third place
that is in no v2 whitelist, breaks one tool (S2), contradicts three agent definitions (S7) and
is, like the place they left, unversioned. "Is the topology implementable" cannot be answered
for a document that is not there; what can be said is that the machine is now ahead of the
paper, in a direction the paper did not choose. Write the topology note before moving anything
else, and have it say explicitly: where tools live until step 7, whether `C:\NSC\tools` is
exempt from the no-write rule, and when the junctions come out (S6 lists what breaks).

### Major

**P4. Step 1 has still not been done.** No `.bundle` anywhere under the OneDrive folder of the
user profile (checked). An evening of moves, a Recycle Bin recovery and a 75-edit doc sweep all
happened on a machine whose only copy of 133 local branches, the tools, the agents and the memory
is this drive. v2 says "do this first, today" twice; it is right, and it was not what was done
first.

**P5. What the plan does not protect (brief Q4).** Beyond the `.claude` agents and memory folders,
which v2 now covers:
- `C:\NSC\tools` (191 files) - in no whitelist (P1).
- The `.py` files in `C:\nscrev\ger-contract-revisions-20260916` - the only copies of
  `new_task_commit.py`, `policy_entry_commit.py`, `verify_filter.py` and five more; not in the
  `nsc-reports` whitelist, not in the step 2 zip list. `ger-tools-dev` likewise.
- The local-only branches and dirty trees inside `C:\NSC-History-20260918` (S4).
- `.claude.json` and `.codex\config.toml` in the user profile (both exist): MCP server and Codex
  configuration. They probably contain tokens, so they do not belong in git; they need a line in
  step 2 (an encrypted copy, or a written "how to rebuild").
- Session transcripts (v2 already asks).
- There are no NSC scheduled tasks today, so nothing to export yet.

**P6. Contact with this machine (brief Q3).**
- Long paths: `LongPathsEnabled=1` and `core.longpaths=true` are both set, so git and robocopy
  are fine; `Move-Item` and any .NET Framework call are not, which is why `nscmin_work` failed.
  The v2 job is git-only, so it survives. Deepest path I measured in a quarantined folder: 219.
- 788 top-level directories under `C:\NSC`: an ignore-everything excludes file keeps git from
  descending, so cost is fine, **but** git cannot re-include a path whose parent directory is
  excluded. The `nsc-control` whitelist (named folders two levels down, inside each
  `.assistant-control`) needs the whole parent chain un-ignored explicitly. v2 does not say
  this; a first implementation that misses it produces an empty commit and, through the same gap
  as P1, a green status. Opinion-grade until someone writes the excludes file; listed because
  the failure would be silent.
- 138 worktrees: v2 never moves one, and `MOVE-NSCREV.ps1:126` keeps them. Fine.
  `MOVE-NSC-FOLDERS.ps1` **does** move clean worktrees and only prints a note afterwards
  (`:873`); the branch stays "checked out" in a dead path until `git worktree prune`.
- Junctions: P1.

### Brief Q5 - the one thing tomorrow

**Step 1, exactly as v2 says, widened by three lines** - so the plan and I agree on what, and
disagree only on scope:
1. `git bundle create --all` for the game repo (v2 step 1), **plus** one bundle per quarantined
   clone that S4 lists, **plus** a copy of the 6 top-level bundles from P2.
2. The v2 step 2 zip, with `C:\NSC\tools`, the `.py` files of `ger-contract-revisions-20260916`
   and `claude-jobs\templates` added.
3. Confirm OneDrive shows them synced.

Before that, two minutes: fix `RESTORE.ps1:95` and re-run one restore (S1). And one instruction:
no `-Apply` of `MOVE-NSC-FOLDERS.ps1` or `MOVE-NSCREV.ps1` until S3 is fixed.

---

## Findings index

| # | Severity | Where | Status |
|---|---|---|---|
| S1 | blocking | `RESTORE.ps1:95` | reproduced |
| S2 | blocking | `tools\astra\ask_astra.py:56,73,447-459,791` | reproduced |
| S3 | blocking | `RESTORE.ps1:43,44,53`; `MOVE-NSC-FOLDERS.ps1:48,68,839,868`; `MOVE-NSCREV.ps1:35` | read; scripts not yet applied |
| S4 | blocking | history folder, 19 of 28 clones; README and RESTORES.md rule | reproduced (local check; GitHub not queried) |
| P1 | blocking | v2 section 1 whitelists, section 2.3 green rule | read + junction-follow tested |
| P2 | blocking | v2 sections 1-2 vs `MOVE-NSC-FOLDERS.ps1` file list, `MOVE-NSCREV.ps1:43-91` | bundles reproduced; `backup` dir theoretical |
| P3 | blocking | topology doc missing | verified absent |
| S5 | major | `MOVE-NSCREV.ps1:208` | reproduced in sandbox; guarded today by a name list only |
| S6 | major | files listed in S6 | read; breaks on junction removal |
| S7 | major | `pipeline-reviewer.md:35,43`, `pipeline-maintainer.md:18,85`, `test-runner.md:24` | read |
| S8 | major | `main_write.py` x2 | reproduced (hash) |
| P4 | major | OneDrive | verified absent |
| P5 | major | list in P5 | verified present and uncovered |
| P6 | major / opinion | v2 sections 1, 2.2 | partly theoretical, marked |

Blocking: 7 (state 4, plan 3).
