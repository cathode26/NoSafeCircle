# Standalone Clone Quick Start

Use this procedure whenever you create an isolated No Safe Circle checkout for a gameplay task or a parallel pipeline slice on the Windows development machine.

## 1. Choose checkout and branch names

Gameplay example:

```powershell
$CheckoutName = "NSC-038"
$BranchName = "nsc-038-isometric-tilemap-visual-layer"
```

Pipeline example:

```powershell
$CheckoutName = "NoSafeCircle-TaskDelivery"
$BranchName = "validation-manifest-delivery-spec"
```

## 2. Clone from GitHub and create the branch

```powershell
$ParentDirectory = "C:\NSC\NSC"
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
```

Do not clone the local `NoSafeCircle` checkout and do not use a Windows Git worktree for provider-backed Docker execution.

## 3. Verify the checkout

```powershell
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
python Pipeline/TaskGraph/taskcontrol.py validate
```

Expected:

- working tree is clean;
- intended feature branch is active;
- `origin` points at GitHub;
- the clone starts from current remote `main`;
- TaskGraph validation passes.

## 4. Pin the Docker Compose project name

Every provider-backed Docker Compose command from a standalone clone must use:

```text
-p nosafecircle
```

Example:

```powershell
$Prompt | docker compose -p nosafecircle run --rm -T codex codex exec --ephemeral --sandbox danger-full-access -
```

This keeps the Git checkout isolated while reusing the already authenticated provider volumes:

```text
nosafecircle_codex-config
nosafecircle_claude-config
```

Without `-p nosafecircle`, Compose derives a new project name from the clone directory and can create empty clone-specific auth volumes, causing provider calls to fail with `401 Unauthorized`.

The explicit `-p nosafecircle` does not change the checkout mounted at `/workspace`; it only selects the shared Compose project namespace.

## 5. ExecutionCrew example

Choose each flag from the path state at captured `HEAD`:

| Path state | Flag |
| --- | --- |
| existing tracked production file | `--implementation-path` |
| absent exact production file | `--new-implementation-path` |
| existing tracked test file | `--test-path` |
| absent exact test file | `--new-test-path` |

```powershell
docker compose -p nosafecircle run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py `
  --task-id NSC-### `
  --provider claude `
  --implementation-path <tracked-production-path> `
  --test-path <tracked-test-path> `
  --host-output-root "C:\NSC\NSC\NSC-###\Pipeline\ExecutionCrew\outputs"
```

Mixed existing/new example:

```powershell
docker compose -p nosafecircle run --rm -T codex-exec python3 Pipeline/ExecutionCrew/run_crew.py `
  --task-id NSC-### `
  --provider codex `
  --implementation-path Assets/.../ExistingOwner.cs `
  --new-implementation-path Assets/.../NewHelper.cs `
  --new-test-path Assets/.../NewFeatureTests.cs `
  --host-output-root "C:\NSC\NSC\NSC-###\Pipeline\ExecutionCrew\outputs"
```

No empty scaffold commit is needed for an absent exact file. Do not pre-create or pass `.meta` for approved new `Assets/` files; ExecutionCrew creates the deterministic sidecar. Parent directories must already exist as committed Git trees. Exact-new authority covers only the named file, never the directory or helper files.

Use the full Windows `--host-output-root` so the final human footer prints complete copy/paste-ready paths to `candidate.patch` or diagnostics.

The `-p nosafecircle` project name remains mandatory for every provider-backed Compose command from a standalone clone.

## 6. Related documentation

Read:

- `REAL_TASK_DELIVERY_RUNBOOK.md` for the end-to-end task workflow;
- `REAL_TASK_DELIVERY_WINDOWS_CLONE_NOTE.md` for the detailed Windows rationale and failure modes.
