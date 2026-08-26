# Decomposition Checkout Isolation

## Purpose

This is mandatory operating guidance for any orchestrator that selects or runs `work_type: decomposition` for No Safe Circle.

The human operator may have many task-orchestrator terminals open at once. The visible Windows/PowerShell working-directory path is part of the operator's coordination UI: it must identify which task that terminal is working on. Decomposition is therefore **not exempt** from isolated task-specific checkout rules merely because D1B.1 is read-only.

## Mandatory rule

The shared repository root:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle
```

may be used to refresh `main`, inspect TaskGraph state, discover candidates, and coordinate/claim GitHub Issues. It must **not** remain the working directory once a decomposition work unit has been selected and claimed.

After claiming `work_type: decomposition`, and **before any decomposition provider invocation**, the orchestrator must:

1. create a fresh standalone clone from `https://github.com/cathode26/NoSafeCircle.git` at current remote `main`;
2. place it in a sibling directory whose name visibly identifies both the parent NSC task and decomposition work;
3. `Set-Location` / `cd` into that directory;
4. run the D1B.1 decomposition workflow from that directory;
5. keep decomposition outputs filesystem-disjoint from the source checkout.

Canonical Windows naming:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC021-DECOMP
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC021-DECOMP-Outputs
```

Replace `NSC021` with the selected parent task ID without the hyphen in the directory-name segment, matching the existing task-checkout naming style.

The shell prompt for an active decomposition should therefore look like:

```text
PS C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC021-DECOMP>
```

and **not**:

```text
PS C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle>
```

The task-specific checkout path is a required human-visible coordination signal, not cosmetic naming.

## Checkout constraints

- Clone from the GitHub remote, not from the local shared repository.
- Use a standalone clone, not a Git worktree.
- Start from current remote `main`.
- Decomposition source work is read-only; no task branch is required merely to run D1B.1.
- Require a completely clean source checkout before the decomposition preflight.
- Do not overwrite or casually reuse an existing decomposition checkout.
- If the canonical task path already exists and cannot be proven to belong to the same active claimed work/source identity, create a distinct task-identifying path by appending the worker ID, for example `NoSafeCircle-NSC021-DECOMP-chatgpt-2`.
- Never fall back to running decomposition from the shared `NoSafeCircle` root because checkout creation failed. Treat inability to create/enter the isolated directory as an execution blocker.

## PowerShell pattern

After the parent Issue is claimed:

```powershell
$taskId = "NSC-021"
$taskDirId = $taskId -replace '-', ''
$crewRoot = "C:\UnityProjects\NoSafeCircleAgentCrew"
$checkout = Join-Path $crewRoot "NoSafeCircle-$taskDirId-DECOMP"
$output = Join-Path $crewRoot "NoSafeCircle-$taskDirId-DECOMP-Outputs"
if (Test-Path $checkout) { throw "Decomposition checkout already exists: $checkout" }
git clone --branch main --single-branch https://github.com/cathode26/NoSafeCircle.git $checkout
Set-Location $checkout
$env:NSC_DECOMPOSITION_HOST_OUTPUT_ROOT = $output
git branch --show-current
git rev-parse HEAD
git status --short
```

Only after the prompt visibly shows the task-specific decomposition directory should the orchestrator run the documented Docker-backed D1B.1 command from `Pipeline/TaskDecomposition/README.md`.

The output directory may use another explicit task-identifying sibling path when necessary, but it must remain outside the source checkout.

## Closeout visibility

The Decomposition Closeout must record:

- the task-specific source checkout path;
- the external decomposition output path;
- the parent task ID and source commit;
- the existing D1B.1 run/result identities required by the decomposition policy.

This rule changes operator checkout isolation only. It does not change decomposition authority: outputs remain `review_only_not_applied`, and decomposition still grants no readiness, delivery, conformance, graph-application, or merge authority.
