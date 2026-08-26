# Task Checkout Path Convention

## Status

This is the authoritative Windows path convention for No Safe Circle task-orchestrator checkouts.

## Canonical paths

The shared operator/main checkout remains:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

Every claimed NSC task uses a standalone GitHub clone directly under the crew root, named by the exact TaskGraph ID with its hyphen preserved:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>
```

Examples:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-040
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Do **not** use checkout names such as:

```text
NoSafeCircle-NSC021
NoSafeCircle-NSC021-DECOMP
NoSafeCircle-NSC021-Decomposition-<timestamp>
```

The task ID itself is the human-visible coordination label. Work type, worker identity, branch, run ID, and status belong in GitHub orchestration records and pipeline artifacts rather than being encoded into the checkout directory name.

## Clone source and long-path rule

Task checkouts must be standalone clones from GitHub, never clones of the local shared checkout and never Git worktrees for Docker-backed work.

Use Git long-path support during the clone because the repository contains deeply nested historical pipeline artifacts:

```powershell
$TaskId = "NSC-021"
$CrewRoot = "C:\UnityProjects\NoSafeCircleAgentCrew"
$Checkout = Join-Path $CrewRoot $TaskId

if (Test-Path -LiteralPath $Checkout) {
    throw "Task checkout already exists: $Checkout"
}

git -c core.longpaths=true clone --branch main --single-branch https://github.com/cathode26/NoSafeCircle.git $Checkout
if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

Set-Location $Checkout
git config core.longpaths true

git branch --show-current
git rev-parse HEAD
git status --short
python Pipeline/TaskGraph/taskcontrol.py validate
```

A successful new task checkout should be on current remote `main`, clean, and TaskGraph-valid before task-specific work begins.

## Implementation work

After the GitHub Issue is claimed, implementation work uses the task directory above and then creates the task branch inside that clone.

When using the Supervisor helper, pass the canonical path explicitly:

```powershell
python Pipeline/Supervisor/task_checkout.py checkout NSC-044 --worker-id chatgpt-1 --checkout C:\UnityProjects\NoSafeCircleAgentCrew\NSC-044
```

Do not rely on an older helper/default/example that produces a `NoSafeCircle-NSC...` checkout name. This document is the path authority.

## Decomposition work

Decomposition uses the same task checkout convention:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

It does not add `-DECOMP` to the checkout directory. The GitHub Issue records `work_type: decomposition`.

D1B.1 source remains read-only. Authoritative decomposition outputs must remain filesystem-disjoint from the source checkout. The normal task-identifying sibling output path is:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021-Outputs
```

Example:

```powershell
$TaskId = "NSC-021"
$CrewRoot = "C:\UnityProjects\NoSafeCircleAgentCrew"
$Checkout = Join-Path $CrewRoot $TaskId
$Output = Join-Path $CrewRoot "$TaskId-Outputs"
$env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT = $Output
```

Do not put authoritative decomposition outputs inside `C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021`.

## Existing checkout rule

Never overwrite, delete, reset, or casually reuse an existing `C:\UnityProjects\NoSafeCircleAgentCrew\<TASK-ID>` directory merely because a new orchestrator wants that task.

Before creating the checkout:

1. inspect the GitHub Issue claim state;
2. test whether the canonical path already exists;
3. if it exists, inspect it and reconcile ownership/state rather than creating a differently named duplicate checkout;
4. if another orchestrator owns the task, do not start duplicate work.

A differently named duplicate checkout is not the normal collision workaround. The GitHub claim and canonical task path should make the conflict visible.

## Closeout

Claim and closeout records should use the canonical checkout path verbatim, for example:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NSC-021
```

Human-facing report copies may still use the documented Downloads handoff convention. Repository-authoritative or hash-bound pipeline outputs remain wherever their owning pipeline requires them.
