# Decomposition Checkout Isolation

## Purpose

This is mandatory operating guidance for any orchestrator that selects or runs `work_type: decomposition` for No Safe Circle.

The human operator may have many task-orchestrator terminals open at once. The visible Windows/PowerShell working-directory path is part of the operator coordination UI, so decomposition must use the same canonical task directory convention as implementation work.

The authoritative checkout path convention is:

```text
Docs/AI-Pipeline/TASK_CHECKOUT_PATH_CONVENTION.md
```

The authoritative external handoff/output convention is:

```text
Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md
```

## Mandatory rule

The shared repository root:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

may be used to refresh `main`, inspect TaskGraph state, discover candidates, and coordinate/claim GitHub Issues. It must **not** remain the working directory once decomposition work has been selected and claimed.

After claiming `work_type: decomposition`, and **before any decomposition provider invocation**, the orchestrator must:

1. create a fresh standalone clone from `https://github.com/cathode26/NoSafeCircle.git` at current remote `main`;
2. use the exact task-ID directory directly under the crew root;
3. `Set-Location` / `cd` into that task directory;
4. run D1B.1 from that directory;
5. keep decomposition outputs filesystem-disjoint from the source checkout;
6. place the host decomposition output root under `Downloads\NoSafeCircleOutput\<TASK-ID>` so each no-overwrite D1B.1 run lands at `Downloads\NoSafeCircleOutput\<TASK-ID>\<RunId>`.

For NSC-021, the canonical source checkout and a representative run output are:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\20260825-195246
```

The shell prompt for active NSC-021 decomposition should therefore look like:

```text
PS C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021>
```

and not like any of these:

```text
PS C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle>
PS C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC021-DECOMP>
PS C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC021-Decomposition-<timestamp>>
```

The task ID itself is the required human-visible coordination label. `work_type: decomposition`, worker ID, provider, and run ID belong in GitHub/pipeline records rather than the checkout directory name.

## Checkout constraints

- Clone from the GitHub remote, not from the local shared repository.
- Use a standalone clone, not a Git worktree.
- Start from current remote `main`.
- Use `git -c core.longpaths=true clone ...` because the repository contains deeply nested historical pipeline paths.
- After cloning, set `git config core.longpaths true` in the task checkout.
- Decomposition source work is read-only; no task implementation branch is required merely to run D1B.1.
- Require a completely clean source checkout before decomposition preflight.
- Do not overwrite or casually reuse an existing canonical task checkout.
- If `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>` already exists, inspect and reconcile it rather than creating a differently named duplicate directory.
- Never fall back to running decomposition from the shared `NoSafeCircle` root because checkout creation failed.
- Do not put authoritative decomposition output under the task checkout or elsewhere under the repository tree.

## PowerShell pattern

After the parent Issue is claimed:

```powershell
$TaskId = "NSC-021"
$CrewRoot = "C:\UnityProjects\NoSafeCircleAgentCrew"
$Checkout = Join-Path $CrewRoot $TaskId
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$OutputRoot = Join-Path $Downloads (Join-Path "NoSafeCircleOutput" $TaskId)

if (Test-Path -LiteralPath $Checkout) {
    throw "Task checkout already exists: $Checkout"
}

git -c core.longpaths=true clone --branch main --single-branch https://github.com/cathode26/NoSafeCircle.git $Checkout
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

Set-Location $Checkout
git config core.longpaths true
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT = $OutputRoot

git branch --show-current
git rev-parse HEAD
git status --short
python Pipeline/TaskGraph/taskcontrol.py validate
```

Only after the prompt visibly shows the canonical task directory should the orchestrator run the documented Docker-backed D1B.1 command from `Pipeline/TaskDecomposition/README.md`.

D1B.1 owns the no-overwrite run directory beneath `$OutputRoot`. When the orchestrator supplies a timestamp run ID such as `20260825-195246`, the authoritative host run directory is:

```text
C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\20260825-195246
```

Do not pre-create the run-ID directory itself; the pipeline creates it and fails closed on collisions.

## Docker / PowerShell 5.1 note

When a provider command needs stdout and stderr combined for `Tee-Object`, place `2>&1` **inside** the command executed by `cmd.exe`. Do not attach PowerShell-side `2>&1` to the native invocation while `$ErrorActionPreference = "Stop"`, because ordinary Docker Compose stderr progress can be promoted to `NativeCommandError`.

Example shape:

```powershell
$DockerCommand = "docker compose -p nosafecircle-m2a run --rm -T codex-decompose python3 Pipeline/TaskDecomposition/run_decomposition.py --task-id NSC-021 --provider codex --run-id $RunId 2>&1"
& cmd.exe /d /s /c $DockerCommand | Tee-Object -FilePath $ProviderLog
$ProviderExit = $LASTEXITCODE
```

## Closeout visibility

The Decomposition Closeout must record:

- canonical task source checkout path, e.g. `C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021`;
- exact external decomposition run path, e.g. `C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-021\20260825-195246`;
- parent task ID and source commit;
- provider, run ID, and existing D1B.1 result identities.

This rule changes operator checkout/output isolation only. It does not change decomposition authority: outputs remain `review_only_not_applied`, and decomposition grants no readiness, delivery, conformance, graph-application, or merge authority.
