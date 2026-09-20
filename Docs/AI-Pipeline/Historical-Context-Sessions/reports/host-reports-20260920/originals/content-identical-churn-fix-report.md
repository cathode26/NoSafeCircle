# P18: content-identical line-ending churn refresh

**Problem:** P18. `git status --porcelain` on the canonical checkout
(`C:\NSC\NSC\NoSafeCircle`) shows 35 modified files, which blocks NSC-015
decomposition's `_require_clean_source` check ("Source must be clean before
decomposition").

**Status:** Reproduced (not theoretical). The exact stale-index-stat-size
phantom was reproduced in an isolated fixture repo and the fix was proven
against a real captured instance of it, then run read-only against the
canonical checkout.

## Root cause

`Pipeline/AssistantControl/decomposition.py:82-84` (`_require_clean_source`)
refuses whenever `Pipeline/AssistantControl/inspect_project.py:94`
(`changes()`, i.e. `git status --porcelain=v1 -z --untracked-files=all`)
reports anything. 33 of the 35 entries are generated Unity `.anim` files
under `Assets/NoSafeCircle/DoorPrototype/Art/Wizard/Generated/`:

- checked out with `core.autocrlf=true`, so Git smudged CRLF onto disk at
  checkout time and cached that larger CRLF size in the index's stat entry;
- Unity later rewrote each file with byte-identical LF content;
- Git's `ce_modified` fast path (`read-cache.c`) compares the cached stat
  `SIZE` first; a size mismatch alone is classified `DATA_CHANGED` and
  reported as a worktree modification **without re-hashing** the file;
- `git diff`, `git hash-object`, and `git status --porcelain=v2` all confirm
  the worktree blob equals the index blob equals HEAD; only the cached stat
  size is stale. `git update-index --refresh` and `git checkout --` do not
  clear this, but `git add -- <path>` rewrites the index entry's stat data
  (same object id) and makes status clean.

The other 2 entries
(`Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset`,
`WallTile.asset`) have real content edits and must never be touched.

## Fix

**Clone:** `C:/nscrev/churn-refresh-fix` (standalone, `--push` disabled).
**Branch:** `fix/content-identical-churn`.
**Base:** `4d4f25db18c587fa8718eaca0adc9c62644c3763`.
**Head:** `23860228f2224a3e7a292e99031b0a5fb337186f`.

Commits:
1. `72462e136` — Test: reproduce P18 stale-index-stat-size churn phantom
   (fails on import before commit 2 exists).
2. `23860228f` — Fix P18: refresh-identical churn tool, unblock NSC-015
   decomposition.

New module: `Pipeline/TaskReviewAgent/refresh_identical_churn.py`. A path
qualifies to be refreshed only when **all** of:
- tracked (present in `git ls-files -s -z`);
- worktree-modified and not staged (`git status` code exactly `" M"`);
- a regular file, not a submodule/symlink (index mode `100644`/`100755`,
  worktree entry is a real file, not a symlink);
- `git hash-object --path=<p> <worktree file>` equals the index blob.

Applying runs `git add -- <exact qualifying paths>` in one call, then
verifies: every refreshed path's index oid is unchanged, HEAD is unchanged,
no non-qualifying path's index entry moved, and none of the refreshed paths
remain in `git status`. Any check failing raises
`RefreshIdenticalChurnError` without resetting anything. Every `git`
subprocess uses `CREATE_NO_WINDOW` (mirroring `inspect_project.git()`'s
`os.name == "nt"` guard).

**Why a sibling module, not an extension of `safe_unity_churn.py`:** that
module restores a small, curated, named list of ProjectSettings/scene paths
from an exact source commit (`restore --source=<head>`). This fix has no
curated path list — any tracked file anywhere qualifies by proof — and it
never restores from source; it only stages already-identical content to
refresh the index's cached stat data. Different precondition model, different
action, so it is its own module (one primary responsibility each), wired into
the existing CLI as a subcommand for a single, discoverable entry point:

```
python -B -m Pipeline.TaskReviewAgent.safe_unity_churn refresh-identical --repo <path> [--apply]
```

`safe_unity_churn.py`'s `main()` now dispatches `argv[0] == "refresh-identical"`
to the new module before falling through to its original
`--repository/--expected-head/--apply` parsing, so the pre-existing CLI is
unchanged (verified manually against a fixture repo; see Tests).

**Refusal hint:** `Pipeline/AssistantControl/decomposition.py:_require_clean_source`
now appends one sentence naming the refresh command to the "Source must be
clean before decomposition" `ValueError`. The check's logic is untouched —
it still refuses on any `changes()` entry; only the message grew a pointer to
the fix.

## Tests

All commands run from `C:/nscrev/churn-refresh-fix` with
`TEMP=TMP=C:\nscrev\tmp\churn-refresh`. Fixture repos live under a
`tempfile.TemporaryDirectory` inside that TEMP, never under `C:\NSC`.

| # | Test | Failing-before | Passing-after |
|---|---|---|---|
| 1 | `test_status_flags_content_identical_crlf_churn_as_modified` (reproduces the exact phantom: autocrlf repo, LF commit, re-checkout smudges CRLF + caches its size, overwrite with identical LF bytes, `git status` still flags `" M"` while `git diff`/`hash-object` prove no content change) | `ImportError: cannot import name 'refresh_identical_churn'` (whole module import fails) | pass |
| 2 | `test_dry_run_lists_it_and_changes_nothing` | same import failure | pass; `.git/index` bytes identical before/after |
| 3 | `test_apply_makes_status_clean_and_index_oid_unchanged` | same import failure | pass; HEAD and index oid unchanged, status clean |
| 4 | `test_real_edit_stays_modified_and_is_reported_as_content_differs` | same import failure | pass; real edit untouched, reported `content differs`, nothing staged |
| 5 | `test_staged_change_is_left_alone` | same import failure | pass; staged path untouched, reported `staged` |
| 6 | `test_unsafe_repository_raises_without_touching_anything` | same import failure | pass; non-repo path raises `RefreshIdenticalChurnError` |
| 7 | `test_every_git_subprocess_uses_create_no_window` | same import failure | pass; every `subprocess.run` call in the module carries `CREATE_NO_WINDOW` |

Commands:
```
# failing-before (implementation module temporarily removed, verified 1 test run):
python -B -m Pipeline.TaskReviewAgent.tests.refresh_identical_churn_smoke_test
  -> ImportError, exit 1

# passing-after (commit 23860228f):
python -B -m Pipeline.TaskReviewAgent.tests.refresh_identical_churn_smoke_test
  -> PASS (7 tests), exit 0
```

**Existing suite, unaffected:**
```
python -B -m Pipeline.TaskReviewAgent.tests.safe_unity_churn_smoke_test
  -> PASS (1 test) at base and at head
```

**Decomposition refusal-message caller, unaffected:**
```
python -B -m unittest Pipeline.AssistantControl.test_decomposition
  -> Ran 14 tests, OK, at base (4d4f25db1) and at head (23860228f)
```
(No test in the repository asserts the exact old refusal string; grep for
`"Source must be clean before decomposition"` only matches the raise site
itself.)

**Static checks:**
```
python -B -m compileall -q Pipeline/TaskReviewAgent Pipeline/AssistantControl   -> exit 0
git diff --check 4d4f25db18c587fa8718eaca0adc9c62644c3763                       -> exit 0 (no whitespace errors)
git ls-files --eol -- <4 changed/new files>                                     -> all i/lf (worktree w/crlf here only because this Windows clone has core.autocrlf=true; the committed blobs are LF)
```
Clone ends clean (`git status --porcelain` empty at head).

**CLI smoke (manual, fixture repo, not part of the automated suite):**
- `refresh-identical --repo <fixture>` (dry run) → correct JSON, no `--apply`.
- Legacy `--repository <fixture> --expected-head <sha>` still parses and runs
  unchanged (`{"status": "recoverable", "paths": [...]}`).
- The `RuntimeWarning: '...safe_unity_churn' found in sys.modules...` printed
  by both invocations pre-dates this fix — reproduced identically with
  `python -B -m Pipeline.TaskReviewAgent.safe_unity_churn --help` on the
  unmodified canonical checkout. Cosmetic only; exit code is unaffected.

## Canonical dry-run (read-only, no `--apply`)

```
python -B -m Pipeline.TaskReviewAgent.safe_unity_churn refresh-identical --repo C:\NSC\NSC\NoSafeCircle
```

Result: **33 refreshable**, **2 content differs**
(`Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/FloorTile.asset`,
`.../WallTile.asset`), **0 untracked_ignored** — matches the diagnosis exactly.

`C:\NSC\NSC\NoSafeCircle\.git\index` mtime/size were read before and after
the dry run and are byte-for-byte identical (`1789626709.2431698`, `391833`
bytes both times): the dry run wrote nothing.

Full JSON (mode, repository, refreshed[33], left_modified[2], untracked_ignored[0])
was captured in this session's tool output; omitted here to keep the report
short per Vincent's token guidance — the Game Agent can reproduce it in one
command.

## Command for the Game Agent

Once this branch is approved and merged, clear the canonical checkout with:

```
python -B -m Pipeline.TaskReviewAgent.safe_unity_churn refresh-identical --repo C:\NSC\NSC\NoSafeCircle --apply
```

Expect the JSON report to list the same 33 paths under `refreshed`, the same
2 under `left_modified` (`content differs`), and `git status --porcelain` to
drop from 35 entries to 2 (the two real edits, untouched). NSC-015
decomposition's `_require_clean_source` will still correctly refuse until
those 2 real edits are separately resolved (committed or reverted) — this
tool does not and must not clear them.

## Risks

- The qualifying-path proof (`hash-object` equals index blob) is exactly the
  same identity check Git itself uses to decide what `git add` would stage;
  there is no path where `--apply` can change tree content, only stat cache
  data. The apply-time re-verification (oid/HEAD/other-paths/status) turns
  any unexpected divergence into a raised error rather than a silent partial
  stage.
- `--apply` stages the 33 refreshed paths, so `git status` will show a clean
  worktree for them; nothing is committed. The 2 real edits remain untouched
  and dirty — the decomposition refusal will still (correctly) fire on them.
- Not tested: behavior on a rename/copy status line (`R `/`C `) reaching the
  qualifying path — the parser skips the rename's original-path record but
  such entries never have status `" M"`, so they always fall to
  `left_modified`; not exercised by a dedicated test.

## Review fix round (2026-09-17)

The fresh `pipeline-reviewer` and a Codex adversarial review both reproduced
three real defects in `23860228f`. Fixed in `974643ff8` on the same branch
(`fix/content-identical-churn`), same clone, same push-disabled setup.

**Blocking:**
1. **Pathspec magic.** `git add -- <refreshable paths>` at line ~172 passed
   qualifying paths as pathspecs, not literal paths. A tracked
   `data[1].txt` that qualified would expand as a glob pathspec and could
   stage a sibling `data1.txt`'s real, unverified edit instead of (or as
   well as) the intended file — reproduced directly: with `data[1].txt`
   unmodified and `data1.txt` carrying a real edit, plain `git add --
   "data[1].txt"` staged `data1.txt`. Fixed by running every `git add` of
   the qualifying-path list with `GIT_LITERAL_PATHSPECS=1`.
2. **Race without rollback.** A file could change between the qualifying
   hash and `git add`; the add would stage the new real content, post-verify
   would raise, and the staged mutation was left behind. Fixed:
   `refresh_identical_churn()` now refuses to start if `index.lock` exists,
   re-hashes every qualifying path immediately before staging (dropping any
   that changed as `"changed during refresh"`), saves the exact `.git/index`
   bytes read via `git rev-parse --git-path index` immediately before the
   add, and on any post-verify failure or a failing `git add` itself,
   atomically restores those bytes (temp file + `os.replace`, then a sha256
   byte-verify) before re-raising with a message noting the restore.

**Minor:**
3. **Hash failures.** `_hash_object` used to return `None` on a non-zero
   `git hash-object` exit, which `find_identical_churn` classified as
   `"content differs"` -- hiding real Git errors such as a broken required
   clean filter. `_hash_object` now raises `RefreshIdenticalChurnError` with
   the git stderr, and the caller lets it propagate instead of swallowing it.
4. **Intent-to-add mislabeled.** A `git add -N` path (porcelain status
   `" A"`) was falling into the generic `"content differs"` branch. It is
   now recognized before that branch and labeled `"intent-to-add"`.
5. **Report inaccuracies (this file), corrected:**
   - The root-cause section above claimed `git checkout -- <path>` does not
     clear the phantom. That was wrong: in the reproduction fixture,
     `checkout --` **does** clear it, by rewriting the worktree bytes back to
     CRLF (a real worktree mutation). `git update-index --refresh` is the one
     that does not clear it. This tool's advantage over `checkout --` is not
     that it succeeds where checkout fails, but that it refreshes only the
     index's cached stat data and never rewrites worktree files -- files
     Unity is actively watching and would reimport on a rewrite.
   - The canonical dry-run numbers below are from a fresh run against
     `C:\NSC\NSC\NoSafeCircle` at this branch's head, since the Game Agent
     restored the two previously-real-edited tile assets in the meantime.

**Tests added** to `refresh_identical_churn_smoke_test.py` (all 12 pass at
`974643ff8`; the 5 new ones fail at `23860228f`):
`test_pathspec_magic_path_does_not_stage_sibling_real_edit`,
`test_race_change_before_add_is_dropped_and_index_untouched`,
`test_forced_post_verify_failure_restores_index_byte_identical`,
`test_hash_object_failure_is_reported_as_error_not_content_differs`,
`test_intent_to_add_path_is_labeled_intent_to_add`.

**Failing-before, confirmed by isolating just the fix commit:**
```
git stash push --keep-index -- Pipeline/TaskReviewAgent/refresh_identical_churn.py
python -B -m Pipeline.TaskReviewAgent.tests.refresh_identical_churn_smoke_test
  -> fails at test_pathspec_magic_path_does_not_stage_sibling_real_edit:
     RefreshIdenticalChurnError: non-qualifying path's index entry changed: data1.txt
     (6/12 tests ran before the failure; exit 1)
git stash pop
```

**Passing-after (974643ff8):**
```
python -B -m Pipeline.TaskReviewAgent.tests.refresh_identical_churn_smoke_test
  -> PASS (12 tests), exit 0
python -B -m Pipeline.TaskReviewAgent.tests.safe_unity_churn_smoke_test
  -> PASS (1 test)
python -B -m unittest Pipeline.AssistantControl.test_decomposition
  -> Ran 14 tests, OK
python -B -m compileall -q Pipeline/TaskReviewAgent
  -> exit 0
git diff --check 4d4f25db18c587fa8718eaca0adc9c62644c3763
  -> exit 0 (no whitespace errors)
git ls-files --eol -- Pipeline/TaskReviewAgent/refresh_identical_churn.py Pipeline/TaskReviewAgent/tests/refresh_identical_churn_smoke_test.py
  -> both i/lf (committed blobs are LF)
```
Clone ends clean (`git status --porcelain` empty at head `974643ff8`).

**Canonical dry-run, re-run at this head (read-only, no `--apply`):**
```
python -B -m Pipeline.TaskReviewAgent.safe_unity_churn refresh-identical --repo C:\NSC\NSC\NoSafeCircle
```
Result: **33 refreshable**, **0 left_modified**, **0 untracked_ignored** --
the two previously-real-edited tile assets
(`.../ArchitecturalTiles/FloorTile.asset`, `WallTile.asset`) are no longer
present in either list, consistent with the Game Agent having restored them.
`C:\NSC\NSC\NoSafeCircle\.git\index` sha256 was read before and after this
dry run and is byte-for-byte identical
(`171a0cf37a15d76b15cd6d2c7c81911abbb85b75ad343e48300b46a40b7204b9`, 391833
bytes both times): the dry run wrote nothing.

## Follow-up (not done, Vincent's decision)

To prevent this class of churn recurring, consider adding `.gitattributes`
`eol=lf` rules for the Unity YAML asset types that Unity always writes as LF
(`*.anim`, generated `*.asset` under `Generated/`, etc.). The blobs already
in the repository are LF, so no renormalization commit would be needed if
this is adopted — it would only stop `core.autocrlf=true` from smudging CRLF
onto these paths at checkout time in the first place, removing the cached
CRLF-size trap. This is a repository-attributes change outside the current
tool's scope, offered as a follow-up rather than done here.
