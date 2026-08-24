# Windows Standalone-Clone and Docker Compose Correction

This note is the authoritative Windows-specific correction for creating isolated No Safe Circle checkouts and running provider-backed Docker Compose commands from them.

## Rule

On this development machine, create every isolated gameplay-task or pipeline checkout from the GitHub remote, **not** by cloning the local `NoSafeCircle` checkout and not by using a Git worktree.

The Git checkout should be isolated. The existing authenticated Claude/Codex configuration volumes should be shared.

## General standalone-clone and branch recipe

Use this procedure for either a gameplay task or a parallel pipeline slice:

```powershell
$ParentDirectory = "C:\UnityProjects\NoSafeCircleAgentCrew"
$CheckoutName = "NoSafeCircle-TaskDelivery"
$BranchName = "validation-manifest-delivery-spec"
$CheckoutPath = Join-Path $ParentDirectory $CheckoutName

if (Test-Path -LiteralPath $CheckoutPath) {
    throw "Checkout path already exists: $CheckoutPath"
}

git clone https://github.com/cathode26/NoSafeCircle.git $CheckoutPath
if ($LASTEXITCODE -ne 0) {
    throw "git clone failed"
}

Set-Location $CheckoutPath

git switch -c $BranchName
if ($LASTEXITCODE -ne 0) {
    throw "git switch failed"
}

git status --short
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

The expected result is:

- `git status --short` prints nothing;
- the new feature branch is checked out;
- `origin` points at `https://github.com/cathode26/NoSafeCircle.git`;
- the clone starts from the current remote `main` history;
- `taskcontrol.py validate` passes.

Do not develop directly on the clone's local `main` branch.

For an NSC task, use names such as:

```text
CheckoutName: NoSafeCircle-NSC038
BranchName:   nsc-038-isometric-tilemap-visual-layer
```

For a pipeline slice, use descriptive names such as:

```text
CheckoutName: NoSafeCircle-TaskDelivery
BranchName:   validation-manifest-delivery-spec
```

## Do not clone the local checkout

Do not use this local-source form on this machine:

```powershell
git clone .\NoSafeCircle .\NoSafeCircle-NSC###
```

Git for Windows has rejected local-source clones because the source `.git` directory can have ownership metadata that differs from the interactive user. Do not add broad global `safe.directory` exceptions merely to create task clones.

Cloning from GitHub avoids that ownership ambiguity and gives the isolated checkout a normal `.git` directory suitable for Docker-based pipeline work.

## Do not use a Git worktree for Docker execution

A Windows Git worktree uses a linked `.git` file that can point to a Windows-only worktree Git directory. Linux Docker containers may then fail to resolve repository identity and report errors such as:

```text
source repository identity could not be resolved
```

Use a standalone GitHub clone for Docker ExecutionCrew, TaskDelivery, decomposition, ArchitectureReview, and other provider-backed work.

## Docker Compose project name is fixed for every standalone clone

Docker Compose normally derives its project name from the checkout-directory name. A checkout such as `NoSafeCircle-TaskDelivery` would otherwise create clone-specific resources such as:

```text
nosafecircle-taskdelivery_codex-config
nosafecircle-taskdelivery_claude-config
```

Those new volumes are empty. Provider calls can then fail before modifying any files, commonly with `401 Unauthorized`, even though the repository and task preflight are valid.

The normal authenticated project owns these existing volumes:

```text
nosafecircle_codex-config
nosafecircle_claude-config
```

Therefore, when running any provider-backed Docker Compose command from any standalone clone on this development machine, **always pin the Compose project name explicitly**:

```powershell
docker compose -p nosafecircle run --rm -T <service> <command>
```

Generic Codex implementation example:

```powershell
$Prompt | docker compose -p nosafecircle run --rm -T codex codex exec --ephemeral --sandbox danger-full-access -
```

Generic Claude implementation example:

```powershell
$Prompt | docker compose -p nosafecircle run --rm -T claude claude -p --safe-mode --model claude-sonnet-5 --permission-mode dontAsk --input-format text --output-format text --no-session-persistence --setting-sources user,project
```

The explicit `-p nosafecircle` does **not** change which checkout is mounted at `/workspace`. Compose still mounts the current standalone clone. It only reuses the normal project namespace and its existing authenticated provider volumes.

The optional shell-level equivalent is:

```powershell
$env:COMPOSE_PROJECT_NAME = "nosafecircle"
```

The explicit `-p nosafecircle` form is preferred in copied commands because it is visible and cannot be lost when a new PowerShell window is opened.

## ExecutionCrew example

```powershell
docker compose -p nosafecircle run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py `
  --task-id NSC-### `
  --provider claude `
  --implementation-path <tracked-production-path> `
  --test-path <tracked-test-path> `
  --host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC###\Pipeline\ExecutionCrew\outputs"
```

The operational parameters that must not be accidentally omitted are:

- `-p nosafecircle` — reuses the existing provider authentication/configuration volumes instead of creating clone-specific empty volumes;
- `--host-output-root "C:\...\Pipeline\ExecutionCrew\outputs"` — gives ExecutionCrew the Windows host path corresponding to its mounted output root so the human footer contains complete copy/paste-ready paths to `candidate.patch` or diagnostic artifacts;
- `--rm -T` — removes the disposable run container and disables pseudo-TTY allocation for the machine-readable execution path.

The Git checkout should be isolated; provider authentication/configuration should be shared.

## Verification after cloning

Run:

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

The working tree should be clean, the intended feature branch should be active, the clone should be on current remote `main` history, `origin` should point at GitHub, and TaskGraph validation must pass.

## Cleanup after merge

After the branch is merged and pushed, close Unity, IDEs, terminals, and file explorers using the clone, then remove the isolated directory from the parent folder.

This note fixes the clone-source and Docker Compose project-name requirements for every standalone gameplay-task or pipeline clone. The remaining feature implementation, Unity validation, evidence, conformance, and merge workflow remains governed by the normal runbook and subsystem documentation.
