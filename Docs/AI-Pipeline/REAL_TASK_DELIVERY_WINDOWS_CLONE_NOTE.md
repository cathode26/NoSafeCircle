# Windows Standalone-Clone and Docker Compose Correction

This note is the authoritative Windows-specific correction for creating isolated No Safe Circle checkouts and running provider-backed Docker Compose commands from them.

The canonical task path convention is defined in:

```text
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
```

## Rule

On this development machine, create every isolated NSC task checkout from the GitHub remote, **not** by cloning the local `NoSafeCircle` checkout and not by using a Git worktree.

The shared operator/main checkout remains:

```text
C:\NSC\NSC\NoSafeCircle
```

A claimed NSC task checkout is:

```text
C:\NSC\NSC\<TASK-ID>
```

Examples:

```text
C:\NSC\NSC\NSC-021
C:\NSC\NSC\NSC-044
```

Preserve the hyphenated TaskGraph ID. Do not use `NoSafeCircle-NSC021`, `NoSafeCircle-NSC021-DECOMP`, or timestamped task-directory variants as the normal task path.

## General standalone-clone and branch recipe

For implementation work:

```powershell
$TaskId = "NSC-044"
$ParentDirectory = "C:\NSC\NSC"
$CheckoutPath = Join-Path $ParentDirectory $TaskId
$BranchName = "nsc-044-ruined-entry-spatial-blockout"

if (Test-Path -LiteralPath $CheckoutPath) {
    throw "Checkout path already exists: $CheckoutPath"
}

git -c core.longpaths=true clone --branch main --single-branch https://github.com/cathode26/NoSafeCircle.git $CheckoutPath
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

Set-Location $CheckoutPath
git config core.longpaths true

git switch -c $BranchName
if ($LASTEXITCODE -ne 0) { throw "git switch failed" }

git status --short
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

Expected result:

- `git status --short` prints nothing;
- the task branch is active;
- `origin` points at `https://github.com/cathode26/NoSafeCircle.git`;
- the clone started from current remote `main`;
- `taskcontrol.py validate` passes.

Git long-path support is required during clone because the repository contains deeply nested historical pipeline artifacts.

## Supervisor helper

When using the implementation checkout helper, pass the canonical path explicitly:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\NSC\NSC\NSC-044
```

The path convention document is authoritative if an older helper default or example disagrees.

## Decomposition

Decomposition uses the same task checkout directory rather than adding a `-DECOMP` suffix:

```text
C:\NSC\NSC\NSC-021
```

Read `Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md` before running D1B.1. Its authoritative output must remain outside the source checkout, normally:

```text
C:\NSC\NSC\NSC-021-Outputs
```

## Do not clone the local checkout

Do not use:

```powershell
git clone .\NoSafeCircle .\NSC-###
```

Git for Windows can reject local-source clones because the source `.git` ownership metadata differs from the interactive user. Do not add broad global `safe.directory` exceptions merely to create task clones.

## Do not use Git worktrees for Docker execution

A Windows Git worktree uses a linked `.git` file that can point to a Windows-only worktree Git directory. Linux Docker containers may then fail to resolve repository identity.

Use a standalone GitHub clone for ExecutionCrew, TaskDelivery, decomposition, ArchitectureReview, and other provider-backed work.

## Docker Compose project name

Provider authentication/configuration should be shared even though Git checkouts are isolated.

For ordinary provider-backed work, pin the Compose project name documented by the owning subsystem. The normal implementation services use:

```powershell
docker compose -p nosafecircle run --rm -T <service> <command>
```

The decomposition services use the decomposition runbook's project name, currently:

```powershell
docker compose -p nosafecircle-m2a run --rm -T <decomposition-service> <command>
```

Do not substitute a clone-directory-derived Compose project name, because that can create fresh unauthenticated provider volumes.

## PowerShell 5.1 stderr handling

When copying a native Docker command whose stderr must be captured with `Tee-Object`, put `2>&1` inside the command executed by `cmd.exe` rather than attaching it to the PowerShell native invocation while `$ErrorActionPreference = "Stop"`.

Example:

```powershell
$DockerCommand = "docker compose -p nosafecircle-m2a run --rm -T codex-decompose <command> 2>&1"
& cmd.exe /d /s /c $DockerCommand | Tee-Object -FilePath $ProviderLog
$ProviderExit = $LASTEXITCODE
```

Docker Compose writes normal progress text to stderr; PowerShell-side merging can otherwise surface harmless progress as `NativeCommandError`.

## Verification after cloning

Run:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

The working tree should be clean, the intended branch/work mode should be correct, origin should point at GitHub, and TaskGraph validation must pass.

## Cleanup after merge or completed review work

Do not delete a task checkout automatically merely because a command failed or a work unit ended. Preserve useful task state until the human decides it is safe to remove. When cleanup is approved, close Unity/IDEs/terminals/file explorers using the directory before removing it.
