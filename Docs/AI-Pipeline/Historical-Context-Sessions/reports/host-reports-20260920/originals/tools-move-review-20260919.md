# Tools move review - 2026-09-19

Reviewer: fresh pipeline-reviewer (read-only). Brief: `tools-move-review-brief.md`. Git 2.45.1.windows.1, system `core.autocrlf=true`.
Everything marked **reproduced** was run on disk; scratch repos lived only in the reviewer temp folder.

```text
THE MOVE:          SOUND - with the junctions in place. Do NOT take the junctions out yet (section 2, item 5).
COMMIT READINESS:  FIX FIRST - two small files (.gitattributes, .gitignore) and one decision; about ten minutes.
ask_astra FIX:     Right shape, guard not weakened - APPROVE, with a missing regression test and an un-updated README.
Blocking findings: 2
```

---

## 1. Findings, most severe first

### Blocking

**B1. Tracking content *through* a junction loses data on any git write operation. Reproduced.**
This does not affect `C:\NSC\tools` (real directories inside the work tree). It does affect (a) the proposed
`C:\NSC\linked\agents` and `C:\NSC\linked\memory` junctions in `repo-topology-20260918.md`, and (b) any repo ever
rooted at `C:\nscrev` while the six tool junctions exist.
- Read side is fine: `git add/commit/status` walk a junction as a plain directory.
- Write side is not. With a file tracked at `linked/agents/a.md` (junction -> real dir), each of
  `git checkout HEAD~1 -- linked/agents/a.md`, `git reset --hard`, `git stash`, `git switch <branch>` printed
  `error: unable to create file linked/agents/a.md: File exists`, exited non-zero, and **left the real `a.md` deleted**.
  Git unlinks the old file through the junction, then treats the junction as a symlink in the leading path and
  refuses to write back through it. Same result with `core.symlinks` true and false.
- In the `reset --hard` case the deleted file held an **uncommitted** edit: unrecoverable. In the others the blob
  is still in the object store, but the live file is gone until someone notices.
- Failure scenario: nsc-fleet tracks `linked/agents`; anyone runs stash/checkout/reset/pull on a day an agent
  definition changed -> that `.md` vanishes from `~\.claude\agents` and the agent type stops loading.
- Also reproduced: a fresh clone restores `linked/agents` as an ordinary directory, not a junction, so a restore
  does not put the files back where Claude reads them.
- Fix: do not track through junctions. Copy-in (a sync step that copies the 14 + 108 files into a real
  `C:\NSC\linked\...` before commit) or a second small repo at the real location. A verb allow-list that permits
  only add/commit/status/log/diff/push would avoid the trigger, but one `git stash` outside the wrapper is enough.

**B2. With `core.autocrlf=true` on this machine, a restore from the repo changes the bytes of most tools. Reproduced.**
- The tree is mixed: 128 files LF, 43 CRLF (21 `art`, 21 `ger`, `viewer/nsc_viewer.py`), 1 mixed (`ger/issue127/recent-comments.txt`).
- Scratch copy of `C:\NSC\tools`, committed, then cloned with the machine defaults: **128 of 176 files differ by sha256**.
  `astra/primer.md` went from `b3e8e6b9...` to `55c40c39...`; `thread.json` pins `b3e8e6b9...`, so after a restore
  `ask_astra.py status` reports `primer: CHANGED since init`. The astra and run_job tools also assert LF output.
- Same class of problem as P18 in the game repo, and the fleet repo will also hold art whose sha256 is pinned by contracts.
- Fix, reproduced: a root `.gitattributes` containing `* -text` -> the clone differs in **0** files. Add it in the first
  commit; adding it later means a renormalising commit.

### Major

**M1. Two of the three "split" tools import through the junction.**
`C:\nscrev\ger-contract-revisions-20260916\new_task_commit.py:32` and `policy_entry_commit.py:24` do
`sys.path.insert(0, r"C:\nscrev\ger-tools")` then `import apply_contract`, `import main_write`. That folder has no
`apply_contract.py`, so both die with `ModuleNotFoundError` the moment the `ger-tools` junction goes. Verified by inspection,
not executed (live GER area). The list of 13 references in the brief missed these because they are outside `C:\NSC\tools`.
This is the most important junction breakage: it stops new-task and policy commits.

**M2. `viewer\audit_evidence_debt.py:168` writes its output to `C:\nscrev\viewer-tools\audit_raw.json`.**
Today that lands, via the junction, in `C:\NSC\tools\viewer\` - a tool writing under `C:\NSC`, into the tree about to be
tracked. Without the junction it raises `FileNotFoundError` at the end of a full audit. Not run by me (it writes under
`C:\NSC`). Fix: write to `C:\nscrev\reports\...` or take `--out`.

**M3. The doc sweep is clean, but it did not cover everything that is live.**
Verified: 0 stale references in the `C:\NSC\nsc-*.md` guides (the only hits are dated `nsc-handoff-20260918-*` files) and 0 in
`~\.claude\agents`. All 89 new `C:\NSC\tools\...` references in docs, agent-state, agents and memory resolve on disk, except
`tools\ger\new_task.py`, which is a planned tool (pipeline-maintainer-agent.md:148) - not an error. No wrong mapping
(`tools\job`, `tools\viewers`...) anywhere; no write target (clone, TEMP, `--out`) was redirected under `C:\NSC\tools`;
no frozen handoff was swept. **Still on the junction paths:**
- the READMEs shipped with the tools: `jobs\README.md` (9), `session\README.md` (7), `astra\README.md` (4). `session\README.md`
  is cited by 6 docs as the source of the successor prompt, and the prompt text inside it tells the new session to run
  `C:\nscrev\session-tools\...` - so every replacement agent is handed junction paths;
- agent memory: 24 references in 11 files, including `nsc-session-recovery-tool.md:13-14` and `ger-queue-state.md` (10);
- `C:\NSC\agent-state`: 29 references in 12 files (the brief says deliberate; they are still live instructions to their owners);
- tracked in the game repo: `Pipeline/TaskDesignGER/GER_AUTOMATION.md` lines 9, 67, 126, 127.

**M4. The `ask_astra` fix shipped with no test and no doc update.**
`tests\test_ask_astra.py` is unchanged since 9/18 06:33 and still sets `NSC_ASTRA_HOME` in every case, so the exact defect
(default `HOME` refused by the guard) would pass 62/62 again. `astra\README.md` still says "Vincent reads the history here"
with `log/`, `answers/`, `thread.json` - those are now in `%LOCALAPPDATA%\nsc-astra`; the folders beside the tool are empty.
See section 5 for the missing test.

**M5. `astra\tests\mutation_check.py:140,154` mutates the live `ask_astra.py` in place** (`TOOL.write_text(...)`, restored at the
end). That is a write under `C:\NSC`, and for roughly 13 x 30 s the shared tool has one guard disabled while other agents may
call it; a killed run leaves it that way. `jobs\tests\review_mutation_check.py` already does this properly on a copy
(`WORKDIR`). I did not run the astra harness for this reason, so **"13/13 mutations caught" is not confirmed by this review.**
### Minor

- **The "13 hardcoded references" in the brief undercounts. Every `nscrev` hit in non-backup `.py` files, classified:**
  - Not defects (the target did not move): `run_job.py:56` `NSCREV` workspace root, `:81` comment, `:353` prompt text;
    `nsc_session_digest.py:33` `DEFAULT_OUT = C:\nscrev\reports\agent-recovery`; test scratch under `C:\nscrev\tmp`
    (`test_run_job.py:26`, `review_mutation_check.py:29,188`, `astra\tests\mutation_check.py:119`).
  - Cosmetic (docstring, usage, comment): `nsc_watch.py:6-7`, `nsc_viewer.py:28`, `ask_astra.py:8-10`,
    `too_hard_benchmark.py:15`, `hold_ger_task.py:15,40`, `main_write.py:8`, `test_run_job.py:9`.
    `nsc_session_digest.py:395` is cosmetic but is emitted into every digest as the provenance line, so it keeps
    producing new stale references.
  - Real, break without the junction, but one-shot historic scripts from 9/14 - archive rather than fix:
    `ger\apply_runbook_update.py:14,97`, `ger\salvage_ger.py:21`, `ger\next\test_*.py` (3 files, `TOOLS=`),
    `ger\patches\upgrade_*.py` (7 files, `TOOLS=` / `TARGET=`).
  - Real and live: M1 and M2 above.
- `ask_astra.py:67`: if `LOCALAPPDATA` is unset (a scrubbed-env subprocess), `expandvars` leaves the literal text and `HOME`
  becomes the relative path `%LOCALAPPDATA%\nsc-astra` under the current directory. Reproduced: from `C:\nscrev\...` the
  guard passes and `status` reports "thread: none"; from `C:\NSC` the guard refuses. Fail closed when the variable is missing.
- `hold_ger_task.py --help` exits 1 from both paths (`No module named Pipeline`): it needs the current directory to be a
  repo checkout. Pre-existing, not caused by the move; worth one line in its docstring.
- `%LOCALAPPDATA%\nsc-astra` holds `thread-20260919T220020Z.json`: `init --new` was run at 22:00Z, retiring the 13:40 thread
  during testing. Note only.
- `ger\patches\nsc044-dryrun.txt` is not valid UTF-8 (cp1252 bytes). Harmless with `* -text`.

---

## 2. Question 1 - was the move correct?

1. **Every tool runs, from both paths. Reproduced.** `--help` for all 13 argparse tools exits 0 from `C:\NSC\tools\...` and
   from the `C:\nscrev\...` junction (except `hold_ger_task.py`, above, identical on both). `ask_astra.py status` rc 0 both
   ways with the same thread id; `nsc_session_digest.py list` works both ways; `python -m art_review --help` works both ways.
   Suites from the real path: astra 62/62 (also 62/62 via the junction), run_job 112/112, propagation_check 93/93,
   ArtReview 38/38. After all of that, nothing under `C:\NSC\tools` had a new mtime.
2. **Duplicates.** The move created none: six junctions, six real folders, no reparse points inside `C:\NSC\tools`.
   Pre-existing copies elsewhere, all non-authoritative: `C:\nscrev\ger-tools-dev\g15*` (review rounds; `g15b\new` matches the
   installed `apply_contract`, `apply_followup_revision`, `contract_commit`, `main_write`), `C:\nscrev\tmp\rj-mutation-copy` and
   `tmp\r6\...` (harness copies), `claude-jobs\propagation-check\propagation_check.py` (older, 9/17), and
   `ger-contract-revisions-20260916\main_write.py` (`25a6f08a`, older than the installed `8f2da4f9`; dead code, because the two
   tools put `ger-tools` first on `sys.path`). **Authoritative = `C:\NSC\tools`.**
3. **Doc sweep:** clean; see M3 for what it did not cover.
4. **Left behind / wrongly taken:** nothing lost. Taken but should not be tracked: `session\digests\` (two session
   transcripts, 140 KB, machine-written) and 15 `.pyc` files. `MOVE-TOOLS-IN.ps1` is fine to keep as a record. Correctly
   left: `claude-jobs`, `codex-jobs`, `reports`, `ger-contract-revisions-20260916`.
5. **What breaks the moment the junctions go** - the real definition of done:
   - new-task and policy commits (M1);
   - `audit_evidence_debt.py` output (M2);
   - every successor prompt pasted from `session\README.md`, plus the other two tool READMEs (M3);
   - 24 memory references and 29 agent-state references that agents follow literally (M3);
   - `GER_AUTOMATION.md` commands in the game repo (M3);
   - the 9/14 one-shot GER scripts and `ger\next` tests (minor; archive);
   - any live session that already has a junction path in its context. Keep the junctions until the fleet has rolled over once.

## 3. Question 2 - can we commit?

1. **Committable state:** yes, after ignore rules. Tested on a scratch copy: 192 files -> 176 tracked, 1.78 MB.
   Recommended `C:\NSC\tools\.gitignore`:
   ```gitignore
   __pycache__/
   *.py[cod]
   *.log
   *.tmp[0-9]*
   /session/digests/
   /viewer/audit_raw.json
   # ask_astra data must never be here; ignored so a bad NSC_ASTRA_HOME cannot be committed
   /astra/log/
   /astra/answers/
   /astra/tmp/
   /astra/thread*.json
   /astra/last.json
   /astra/astra.lock
   ```
   The 17 `*.bak.py` files (433 KB) are hand-made version history. Commit them once so the history is kept, untrack them in
   the next commit, and stop making them - the repo replaces them.
2. **The junction question - tested, not reasoned:**
   - Fleet repo with work tree `C:\NSC` tracking `tools/`: `C:\nscrev\ger-tools` is outside the work tree and is not recorded.
     An edit made through the junction path shows up as ` M tools/ger/tool.py` in the fleet repo. Nothing is committed twice.
   - A repo (or backup) rooted at `C:\nscrev`: git walks the junction and commits the same bytes again as `ger-tools/...` -
     identical blob id in both repos. Taking the junction away then shows ` D ger-tools/...` there while the real files survive.
     `git clean -fdx` on an *untracked* junction took away only the link; the files in the target survived. But once tracked
     through the junction, checkout/reset/stash/switch delete the real tool files in `C:\NSC\tools` (B1).
   - So: never root a repo at `C:\nscrev` while the junctions exist, or ignore the six names there first. For file-copy
     backups use `robocopy /XJ`, otherwise the tools are copied twice.
3. **Secrets:** re-checked the tools subtree. Zero token-shaped strings (the regex hits are words like `task-contract-...`
   and `ask-astra-...`), zero key or password assignments. Two real addresses, both functional: `cathode26@gmail.com`
   (the run_job account guard, its tests and README) and `Vincent.J.Liguori@outlook.com` (`ger\branch_prs.py:23`).
   A private repo is sufficient. The session digests are transcripts and are the one thing I would keep out regardless.
4. **Size:** 192 files, 2,084,114 bytes (2.0 MB, not 3). Largest file 69 KB. No binaries except the 15 `.pyc` (ignored).
5. **Split tools:** does not block. Commit what is there. Later, when the GER Agent is between revisions, *copy* the three
   into `tools\ger`, change the `sys.path` line from M1 to `Path(__file__).resolve().parent`, and leave stubs behind.
6. **First thing tomorrow:** create the repo and commit - but only real directories (docs, `agent-state`, `tools`), with
   `.gitattributes` and `.gitignore` in the first commit, and prove it by cloning to a temp folder and comparing the sha256
   of every file (expect 0 differences). Hold `linked\` until B1 is redesigned.

## 4. Do this before committing, in order

1. Root `.gitattributes` with `* -text` (B2).
2. `tools\.gitignore` as above; relocate `session\digests\*` to `C:\nscrev\reports\agent-recovery\`.
3. Leave the `linked\` junctions out of the first commit; decide copy-in vs a second repo (B1).
4. Commit; clone to temp; hash-compare; only then call it a backup.
5. Then, in any order, before taking out a single junction: M1, M2, the three READMEs, memory and agent-state references,
   `GER_AUTOMATION.md`, and the `ask_astra` follow-ups (M4, M5, the `LOCALAPPDATA` fallback).

## 5. The `ask_astra.py` fix

- **Shape: correct.** Code location and data location are different things; `TOOL_DIR = Path(__file__).resolve().parent`
  for the primer and a separate data `HOME` is the standard split. `resolve()` also means the tool behaves the same through
  the junction (reproduced: same thread id from both paths).
- **Guard: not weakened. Reproduced.** `_assert_home_safe`, `_under_forbidden_root` and `FORBIDDEN_TEMP_ROOT` are untouched.
  `NSC_ASTRA_HOME=C:\NSC\astra-review-probe` -> rc 3, nothing created. `NSC_ASTRA_HOME=C:\nscrev\astra` (the old default) ->
  rc 3, because the guard resolves the junction - which also confirms the root cause in the brief is real, not theoretical.
  `PRIMER_FILE` under `C:\NSC` is only read, so it does not touch the purpose of the guard.
- **`%LOCALAPPDATA%`:** per-user and not roaming, which is right for a lock file and a thread id tied to the Codex install
  on this machine. Costs: the log and answers - the part Vincent reads - are now outside every backup and outside the
  proposed repo; a second Windows user gets a separate thread (acceptable; Codex is per-user too). I would rather see
  `C:\nscrev\astra-data`, so the history sits beside the other job records; or keep LOCALAPPDATA and say so in the README.
  Plus the unset-variable case above.
- **Should the tests have caught it? Yes.** Missing test: run `ask_astra.py status` in a subprocess with **every
  `NSC_ASTRA_*` variable stripped** from the environment; assert rc 0, assert the default `HOME` is not under
  `FORBIDDEN_TEMP_ROOT`, and assert `PRIMER_FILE` exists next to the tool. It fails at the old default and passes now.
  General rule for this tool set: one test per tool that runs the shipped defaults, because overrides hide exactly this.
- Not confirmed by me: the 13/13 mutation result (M5) and the live round trip (a provider call). `thread.json` and
  `last.json` do show an answered question at 22:00:56Z.

## 6. Reviewer scope check

Commands run: `--help` on every tool from both paths; astra, run_job, propagation_check and ArtReview suites with `-B` and
`TEMP`/`TMP` under `C:\nscrev\review-tmp\tools-move` (the run_job suite also uses its own hardcoded `C:\nscrev\tmp\run-job`);
scratch git repos only under the reviewer temp folder. Nothing under `C:\NSC` was written (checked by mtime after the
runs). No Unity, Docker, provider or paid call; `ask_astra status` runs only `codex --version`. Not run:
`audit_evidence_debt.py`, astra `mutation_check.py`, `nsc_viewer` / `nsc_watch` against the live viewer.