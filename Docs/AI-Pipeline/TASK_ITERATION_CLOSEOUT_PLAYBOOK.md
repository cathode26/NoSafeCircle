# Task Iteration and Closeout Playbook

This operational playbook was distilled from the NSC-039 implementation and delivery closeout on 2026-08-25. It records the retry patterns that cost time during that task and the command patterns that eventually worked reliably. It is intended for future models and human operators working in Windows PowerShell 5.1 against the No Safe Circle repository.

This is pipeline/operator guidance, not GDD canon. Task contracts, the approved GDD, committed TaskGraph evidence, and the repository's deterministic tools remain authoritative.

## The golden path

Use this order unless the task has an explicit reason to differ:

1. Fetch current `origin/main` before beginning or resuming task work.
2. Preserve or reconcile an existing review-ready candidate instead of restarting ExecutionCrew merely because main advanced.
3. During interactive Unity iteration, snapshot the worktree before opening Unity, then inspect and clean with `unity_workspace_hygiene.py` after the human run.
4. After every failed edit script or stopped command, inspect the actual files and Git state on disk before preparing another edit. Never infer that a stopped script wrote nothing.
5. Run ordinary/non-authoritative Unity tests while iterating. Update tests together with representation changes; do not leave old invariants or helper references behind.
6. When the implementation is approved, remove only proven editor/stat churn, run `git diff --check`, stage exact task paths, and commit the implementation.
7. Fetch current `origin/main` again and integrate it **before** authoritative validation. If the implementation commit is rebased, the authoritative validation must happen afterward on the new SHA/tree.
8. From a completely clean committed checkout, run `Pipeline/Testing/run_unity_tests_clean.ps1`. Preserve the printed manifest/XML/log trio unchanged.
9. Generate the TaskDelivery review outside the repository, obtain explicit human approval, finalize, run the exact `record_delivery.py` command it prints, stage the exact evidence paths, run `validate_draft_evidence.py`, commit evidence, verify `taskcontrol.py state <TASK> --json` is `conformant`, then fast-forward main only if `origin/main` is still an ancestor.

## Windows PowerShell 5.1 command rules

### Prefer no-backtick operator blocks

Long copy/paste blocks using PowerShell line-continuation backticks repeatedly pasted badly during NSC-039. Prefer one command per line, argument arrays, and splatting.

Good:

```powershell
$Args = @(
    "Pipeline/TaskDelivery/generate_delivery_spec.py",
    "draft",
    "--task-id", "NSC-039",
    "--base-commit", $BaseCommit,
    "--validation-manifest", $Manifest,
    "--output", $ReviewPath
)
& python @Args
```

Avoid operator instructions that depend on a backtick being the final character on several lines.

### Native commands are authoritative by exit code, not stdout

`git merge-base --is-ancestor` succeeds silently. This is wrong:

```powershell
if (-not (git merge-base --is-ancestor origin/main HEAD)) { ... }
```

The successful command prints nothing, so the expression looks false. Use:

```powershell
git merge-base --is-ancestor origin/main HEAD
if ($LASTEXITCODE -ne 0) {
    throw "origin/main is not an ancestor of HEAD"
}
```

The same principle applies to other native tools whose success is communicated through their process exit code.

### Join multi-line native output before regex matching

`git show` returns an array of lines in PowerShell. `-match`/`-notmatch` operate element-by-element on arrays, which can produce surprising truthy results. This check failed even though the required text existed:

```powershell
$MapText = git show "origin/main:Pipeline/TaskGraph/WORK_ID_MAP.json"
if ($MapText -notmatch '...') { ... }
```

Use:

```powershell
$MapLines = git show "origin/main:Pipeline/TaskGraph/WORK_ID_MAP.json"
$MapText = $MapLines -join "`n"
if ($MapText -notmatch '...') { ... }
```

Or use a purpose-built command such as `Select-String -Quiet` when practical.

### Distinguish staged from unstaged state

Do not label `git status --short` output as "unstaged" after staging; it reports both index and worktree status. Use these exact views:

```powershell
git diff --name-status
```

for unstaged tracked changes, and:

```powershell
git diff --cached --name-status
```

for staged changes. Use `git status --short --untracked-files=all` only as the combined summary.

## Safe source-edit retry rules

### Inspect first; do not repeatedly guess old text

Several NSC-039 PowerShell edits searched for exact multi-line source strings. Once the file had moved even slightly, commands stopped with messages such as "expected block was not found." Reissuing another historical-state script created more uncertainty.

Before any retry, inspect the exact current method/block from disk. Build the next edit against that state. If using string or regex replacement, require an expected match count (normally exactly one) and stop before writing when the count is wrong.

Prefer semantic anchors such as method declarations or exact API calls over comments, whitespace, or long multi-line formatting. Comments changed more often than behavior and made poor insertion anchors.

### After a stopped script, verify the actual filesystem

During NSC-039 we incorrectly reasoned more than once that a script "could not have written anything" because the displayed stop occurred before the apparent write stage. Later inspection showed the on-disk builder was already in the newer state. The operational rule is simple: after any stopped/failed edit command, immediately inspect `git status`, `git diff`, and the relevant source block. Do not reason from the intended control flow of the failed script.

### Search all references before deleting helpers

The CustomAxis conversion removed Orthographic-depth helper methods while an older test still called them, producing compile errors. Before deleting or renaming a helper, search the full file/repository for every reference. Remove or migrate all callers in the same edit.

### Representation changes require an invariant sweep

When wall representation changed from two monolithic visual tiles to six independently sortable segments, inherited tests still asserted "2 tiles" and "one sprite width equals the entire 3-unit collider." Those were valid old invariants but invalid new ones.

Whenever a representation changes, search tests for old counts, sizes, paths, hierarchy names, sort assumptions, and helper semantics. Preserve the behavioral guarantee while rewriting the representation-specific assertion. For NSC-039, the correct replacement was "three visual segments collectively align with the same independent gameplay collider."

### Use approximate comparisons for Unity floating-point/rotation facts

An earlier NSC-039 test compared Quaternions with exact equality even though the printed values appeared identical. Use `Quaternion.Angle(expected, actual)` with a small tolerance for rotations. Similarly, Unity normalizes `Camera.transparencySortAxis`; tests should compare the stored axis to the normalized authored vector rather than raw component values.

## Unity iteration and workspace lessons

### Do not confuse a sorting-model problem with renderer granularity

Changing the camera to `TransparencySortMode.CustomAxis` was correct for the Isometric Z-as-Y setup, but it did not by itself fix a long wall represented by one oversized sortable sprite. Human validation exposed that one renderer could not provide independent depth behavior along its length. The eventual fix retained CustomAxis/Individual sorting and segmented the wall visual while preserving the independent gameplay collider.

The general lesson is to test the exact human-observed failure after changing a global sorting setting. If the same renderer must be simultaneously in front of and behind something at different points, the renderer itself may be too coarse.

### Unity scene YAML may need trailing-whitespace cleanup during iteration

Unity serialization repeatedly introduced trailing spaces in `Assets/Scenes/DoorPrototype.unity`, causing `git diff --check` to stop otherwise-good precommit/test scripts. It is acceptable during ordinary task iteration to remove **only** trailing spaces/tabs from a task-owned Unity text scene before `git diff --check`, provided the semantic YAML is unchanged.

Do not generalize this to evidence artifacts. Raw authoritative logs are integrity-bound bytes and must not be rewritten.

### Stat-only editor churn can block tools that require a clean checkout

`ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json` repeatedly appeared dirty after Unity even when `git diff --quiet HEAD -- <path>` reported no Git-normalized content difference. Before restoring a known churn file, prove that exact path has no normalized content change:

```powershell
$Path = "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
git diff --quiet HEAD -- $Path
if ($LASTEXITCODE -eq 0) {
    git restore --source=HEAD --worktree -- $Path
}
```

For interactive runs, prefer the committed workspace-hygiene helper because it captures the intended pre-Unity state and refuses unsafe cleanup.

## Task creation must preserve TaskGraph metadata symmetry

Creating `Tasks/NSC-042.yaml` by itself caused TaskDelivery to fail later with:

```text
ID map/task count mismatch: id_map=41, tasks=42
```

A task contract is not a standalone repository addition. New task creation must preserve all TaskGraph metadata required by the current graph, including `Pipeline/TaskGraph/WORK_ID_MAP.json` and resource-group metadata when the new task changes those relationships. Prefer the approved decomposition/graph-delta path when applicable instead of hand-adding a single task file.

Immediately after adding or integrating a task, run a graph-loading check such as:

```powershell
python Pipeline/TaskGraph/taskcontrol.py state NSC-042 --json
```

A new task may legitimately be `not_delivered`; the important check is that the persistent graph loads without schema, ID-map, or resource-symmetry failure.

## Rebase/validation ordering

### Integrate current main before authoritative validation

NSC-039 had to run authoritative Unity validation more than once because main advanced and the implementation was rebased afterward. A validation manifest binds the exact tested commit and tree. Rebasing changes those identities even if the implementation diff is textually identical.

Before the authoritative run:

```text
commit implementation -> fetch origin -> integrate current main -> verify clean -> run authoritative Unity validation
```

If HEAD/tree changes after authoritative validation for any reason that changes the validated implementation history, generate fresh validation evidence. Do not reuse a stale manifest.

### If main advances after evidence is committed, stop rather than rewriting validated history

Before pushing completed task history, fetch `origin/main` and check ancestry with `$LASTEXITCODE`. If `origin/main` is not an ancestor of the evidence commit, stop and reassess. Do not automatically rebase a validated implementation/evidence chain; the delivery record is bound to the validated commit/tree.

## TaskDelivery evidence lessons

### Keep delivery inputs outside the repository

The review JSON, delivery spec, and human-validation source should live under `%TEMP%` or `Downloads`, not inside the Git worktree. TaskDelivery requires a clean repository and refuses to overwrite existing review/spec outputs.

### Never mutate a manifest-bound Unity log to satisfy whitespace checks

NSC-039 `record_delivery.py` produced a valid staged evidence package, but `git diff --cached --check` reported trailing spaces in the copied Unity `.log`. Those spaces were present in the validated raw log and are part of the recorded hash. Editing the log would invalidate the evidence.

The safe sequence is:

1. stage exactly the paths printed by `record_delivery.py`;
2. run `validate_draft_evidence.py` and require `DRAFT EVIDENCE: VALID`;
3. if full `git diff --cached --check` fails **only** on the exact manifest-bound machine log, do not edit that log;
4. run `git diff --cached --check -- <record> <xml> <human-validation>` to ensure the structured/human-authored evidence is clean;
5. inspect the staged stat and commit the exact evidence paths.

This is an exception for immutable machine evidence, not permission to ignore whitespace errors in source, records, XML, human-authored files, or unrelated staged paths.

## NSC-039 retry postmortem

The major avoidable retries were:

- an accidental fresh ExecutionCrew start after usable prior candidate work existed; future operators should preserve/reconcile review-ready candidates instead of restarting by default;
- normal patch application failing after upstream NSC-041 changed the same builder file; `git apply --3way --check` was the successful reconciliation path, followed by explicit diff review;
- helper methods removed before all old test callers were migrated, causing compile errors;
- CustomAxis tests asserting raw `(0, 1, -0.26)` values even though Unity stores the normalized axis;
- assuming CustomAxis alone solved the wall issue without testing the oversized wall renderer at both ends;
- brittle exact multi-line PowerShell replacements failing as the source evolved;
- retry scripts being prepared from assumptions about what a failed prior script had or had not written instead of inspecting disk state;
- inherited tests still asserting two monolithic wall visuals after the implementation intentionally changed to six sorting segments;
- repeated `git diff --check` stops from Unity scene trailing whitespace;
- PowerShell copy/paste blocks using line-continuation backticks that pasted unreliably;
- treating `git merge-base --is-ancestor` stdout as a boolean instead of checking `$LASTEXITCODE`;
- applying `-notmatch` directly to the line array returned by `git show`, falsely reporting that an existing ID-map entry was absent;
- creating NSC-042 as a task contract without simultaneously maintaining TaskGraph metadata symmetry, which later blocked TaskDelivery;
- authoritative validation becoming stale after a subsequent rebase onto newer main;
- stat-only code-coverage settings churn making the checkout look dirty to TaskDelivery even though the normalized content was unchanged;
- full staged whitespace checking treating trailing spaces in the exact hash-bound Unity log like source formatting, when the correct action was to preserve the log and scope the formatting check to non-log evidence after staged-evidence validation passed.

The recurring theme is that fail-closed tooling was usually doing the right thing. Most wasted retries came from preparing the next command from an assumed state rather than querying the repository/tool state that actually existed. Future task closeout should bias heavily toward small read-only verification steps before each mutation, exact-path operations, exit-code checks, and preserving validated bytes.