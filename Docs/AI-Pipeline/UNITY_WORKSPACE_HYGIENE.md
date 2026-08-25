# Unity Workspace Hygiene for Interactive Task Iteration

This is operational pipeline guidance for cleaning predictable Unity/editor workspace churn between an interactive human validation pass and the next task action. It is **not** GDD canon and it is **not** authoritative validation evidence.

The helper is:

```text
Pipeline/Testing/unity_workspace_hygiene.py
```

It exists because opening Unity, running production scene builders, or performing human runtime validation can dirty files that are not part of the intended task change. Repeated examples include `ProjectSettings/EditorBuildSettings.asset`, code-coverage settings, generated architectural Tile assets, and newly-created generated sprite/prefab assets. Manually reconstructing exact cleanup lists is slow and error-prone.

## Authority boundary

Workspace hygiene is allowed only during ordinary interactive iteration, candidate rejection/retry cleanup, or preparation for a later authoritative validation run.

It must **never** be used to turn a dirty evidence-producing Unity test run into a passing run. `Pipeline/Testing/run_unity_tests_clean.ps1` remains fail-closed: if authoritative validation changes the repository, that run fails and the mutation must remain visible for diagnosis.

The hygiene helper therefore follows these rules:

- capture the intended pre-Unity worktree state before opening/running Unity;
- never restore or delete a path that was already changed/untracked in that captured task state;
- preserve declared task `repo-file:` and `unity-scene:` exclusive resources;
- automatically restore only narrow, known Unity churn that appeared after the snapshot, plus stat-only or whitespace-only tracked churn;
- retain new generated assets by default so successful task output is not silently discarded;
- remove newly-created generated assets only with an explicit `--remove-new-untracked` retry/rejection cleanup flag;
- stop on unexpected staged changes, unexpected semantic tracked changes, unexpected untracked files, changed HEAD, or mutation of a pre-Unity task path after the snapshot.

## Required interactive task step

For a gameplay task that will be opened/built/played in Unity, add this task to the operator flow:

```text
apply/review intended candidate changes
    ↓
capture Unity-workspace snapshot outside the repository
    ↓
open/build/play in Unity and perform human validation
    ↓
inspect workspace against the snapshot
    ↓
clean proven-safe Unity churn
    ↓
    ├── accepted candidate: keep task resources + generated task assets for review/commit
    └── rejected/retry candidate: explicitly remove new generated assets
    ↓
review remaining task diff
    ↓
commit implementation when approved
    ↓
start authoritative clean Unity validation from a completely clean committed checkout
```

### 1. Capture the pre-Unity task state

Use the normal Downloads run folder so the snapshot does not dirty the repository:

```powershell
$SnapshotPath = Join-Path $RunDir "unity-workspace-snapshot.json"
python Pipeline/Testing/unity_workspace_hygiene.py snapshot `
  --task-id NSC-039 `
  --output $SnapshotPath
```

The snapshot may be taken while intended candidate/source changes are present. Those paths become protected baseline task state and will not be silently restored by the hygiene helper.

Task `exclusive_resources` with `repo-file:` or `unity-scene:` keys are also automatically preserved. Additional exact paths can be protected with repeatable `--preserve` arguments when needed.

### 2. Inspect after interactive Unity work

```powershell
python Pipeline/Testing/unity_workspace_hygiene.py inspect `
  --snapshot $SnapshotPath
```

The report separates pre-Unity task state, task resources to preserve, safe stat-only/whitespace-only churn, known Unity/editor churn, new generated Unity assets, and unexpected changes. An unexpected or mutated task path produces a blocking exit code instead of being cleaned.

### 3. Clean safe churn after an accepted/continuing iteration

```powershell
python Pipeline/Testing/unity_workspace_hygiene.py clean `
  --snapshot $SnapshotPath
```

This restores only proven-safe tracked churn. New generated assets remain for human review because they may be intentional task output.

### 4. Clean a rejected candidate before ExecutionCrew retry

When the human rejects the candidate and the new generated files are disposable retry artifacts:

```powershell
python Pipeline/Testing/unity_workspace_hygiene.py clean `
  --snapshot $SnapshotPath `
  --remove-new-untracked
```

The removal flag is deliberately narrow: it applies only to new untracked paths beneath approved generated roots and never to tracked files or pre-snapshot task state.

## Known repo-local Unity churn

The first implementation recognizes these exact tracked editor/settings surfaces as known Unity churn when they were clean at snapshot time and are not task-preserved resources:

```text
ProjectSettings/EditorBuildSettings.asset
ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json
```

It also recognizes tracked reserialization beneath:

```text
Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles/
```

under the same safeguards. New untracked files beneath that generated root are reported and kept by default.

This is intentionally repo-local configuration, not a general claim that every Unity change beneath those paths is meaningless. Snapshot state and task-preserve authority take precedence over cleanup classification.

## Retry discipline after a stopped command

Do not infer workspace state from where a PowerShell script appeared to stop. During NSC-039, follow-up commands were prepared from the assumption that a failed script had not written anything, but later inspection showed the on-disk source was already in a newer state. After every stopped edit/build/cleanup command, re-read the truth from disk before the next mutation:

```powershell
git status --short --untracked-files=all
git diff --name-status
```

Then inspect the exact source block or asset that the next command intends to modify. This is especially important after brittle exact-text replacement commands: once a source method has evolved, do not keep issuing scripts written for an older version of that method.

When a tracked Unity/editor path looks dirty but is suspected to be stat-only or line-ending churn, prove the exact path has no normalized Git content change before restoring it:

```powershell
$Path = "ProjectSettings/Packages/com.unity.testtools.codecoverage/Settings.json"
git diff --quiet HEAD -- $Path
if ($LASTEXITCODE -eq 0) {
    git restore --source=HEAD --worktree -- $Path
}
```

Do not broaden this into a directory restore. Exact-path cleanup is part of the safety boundary.

## PowerShell copy/paste guidance

Human-facing operator blocks should prefer commands that do not depend on PowerShell line-continuation backticks. NSC-039 repeatedly lost time to long pasted blocks where continuation formatting did not survive cleanly. Prefer one-line commands or argument arrays/splatting for long invocations. Also remember that native Git commands communicate success through `$LASTEXITCODE`; do not use silent stdout as a boolean for commands such as `git merge-base --is-ancestor`.

The broader command/retry postmortem and closeout patterns are documented in:

```text
Docs/AI-Pipeline/TASK_ITERATION_CLOSEOUT_PLAYBOOK.md
```

## Testing the helper

The deterministic smoke test uses a temporary Git repository and does not touch the real game checkout:

```powershell
python Pipeline/Testing/unity_workspace_hygiene_smoke_test.py
```

It verifies that intended pre-Unity changes and task scene resources survive cleanup, known Unity churn is restored, approved generated untracked files can be removed explicitly, unexpected semantic tracked changes block, and stale snapshots fail after HEAD changes.
