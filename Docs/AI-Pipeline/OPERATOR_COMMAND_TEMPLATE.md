# Operator Command Template

This file defines the canonical shape for substantial human-run operator commands generated for this repository.

It is operating guidance, not game-design canon and not evidence of repository state.

Use it with `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`. The standards define the rules; this file shows the execution skeleton.

The template is intentionally conservative because this project has repeatedly paid for avoidable failures involving Windows PowerShell 5.1 parsing, execution policy, native stderr semantics, stdout contamination, CRLF crossing into Linux, stale working directories, brittle multiline text edits, stale SHA assumptions after partial mutation, unexpected changed-file scope, and long-running commands that appeared hung.

## When this template is required

Use this shape for a substantial operator block that can:

- create, modify, move, or delete repository files;
- create commits, branches, refs, claims, stashes, Issues, PRs, or other durable state;
- push or merge;
- create or modify task checkouts;
- run a multi-step validation/delivery sequence that may need to resume;
- invoke a long-running provider or external tool.

A one-line read-only command such as `git status --short` does not need the full skeleton.

## Compatibility baseline

Unless the operator explicitly says otherwise, generated commands must be compatible with **Windows PowerShell 5.1**.

Do not use Bash-only syntax, PowerShell-7-only syntax, or shell behavior that depends on another terminal.

Avoid continuation backticks when arrays, splats, parentheses, or natural PowerShell continuation can express the same call.

## Execution-policy rule

A paste-ready `& { ... }` block must be self-contained. It must **not** depend on dot-sourcing a repository `.ps1` helper, because the current interactive PowerShell process may use an execution policy that rejects script loading.

If a checked-in or downloaded trusted `.ps1` runner is the right delivery form, launch it in a bounded child process:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath
if ($LASTEXITCODE -ne 0) {
    throw "Runner failed with exit code $LASTEXITCODE."
}
```

Do not change `CurrentUser` or `LocalMachine` execution policy merely to run repository automation.

`Pipeline/TaskReviewAgent/NativeCommand.ps1` remains the repository helper for checked-in PowerShell scripts that need diagnostic/streaming native behavior. Its `Output` collection combines stdout and stderr and therefore must not be parsed as machine authority.

## Required command phases

A substantial mutating runner uses these conceptual phases:

```text
IDENTITY
    define exact repository/work item/base authority

PREFLIGHT
    prove paths, tools, repository, branch and working-tree assumptions

OBSERVE CURRENT STATE
    read current HEAD/refs/Issues/PRs/files and determine whether earlier mutations already happened

PLAN NEXT MUTATION
    choose the next missing authorized step

WORK
    cross the smallest intended mutation boundary

VALIDATE
    prove exact scope, tests, identities and remote state

POSTCONDITIONS
    prove the intended resulting state and clean/understood tree

FINAL REPORT
    state exactly what happened, current authority and the next action
```

`OBSERVE CURRENT STATE` is mandatory when a prior attempt could already have created durable state.

A resume-safe runner must **not** blindly require `HEAD == base` before observation. The base SHA is an authority anchor; current `HEAD` may legitimately be an exact patch/merge created by an earlier partial run.

## Diagnostic native output versus machine data

The canonical block uses two separate native execution paths.

### Diagnostic path

Use when output is for a human and stdout/stderr may safely be combined:

```text
fetch
push
provider progress
Docker progress
verbose tests
```

### Machine-data path

Use when stdout will be parsed as authority:

```text
filenames
SHAs
refs
JSON
exact paths
counts
branch names
```

Machine-data capture keeps stdout and stderr separate. Healthy Git warnings must never be interpreted as filenames or other data.

## Canonical substantial PowerShell block

The following is a **template, not a paste-ready command**. Agents must instantiate it from current repository reality before handing it to the operator.

A paste-ready block must never contain literal `<PLACEHOLDER>`, `REPLACE_ME`, `SET_ME`, fake SHAs, or similar sentinel values.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY
    # ============================================================

    $Root = "C:\NSC\NSC\NoSafeCircle"
    $ExpectedOrigin = "https://github.com/cathode26/NoSafeCircle.git"
    $ExpectedBaseHead = "SET_FROM_VERIFIED_CURRENT_STATE"
    $AllowedBranches = @("main", "target-operation-branch")

    $MutationState = [ordered]@{
        FilesModified = $false
        CommitCreated = $false
        BranchPushed = $false
        IssueUpdated = $false
        PullRequestCreated = $false
        StashCreated = $false
        MergeCompleted = $false
    }

    $CurrentPhase = "identity"

    # ============================================================
    # LOCAL HELPERS
    # ============================================================

    function Write-Phase {
        param(
            [Parameter(Mandatory = $true)]
            [string]$Name,

            [Parameter(Mandatory = $true)]
            [string]$Message
        )

        Write-Host ""
        Write-Host "[$Name] $Message"
    }

    function Get-NormalizedNativeArguments {
        param(
            [Parameter()]
            [string[]]$ArgumentList = @()
        )

        $Normalized = New-Object 'System.Collections.Generic.List[string]'

        foreach ($Argument in $ArgumentList) {
            if ($null -eq $Argument) {
                throw "Native command arguments must not be null."
            }

            [void]$Normalized.Add(
                $Argument.Replace("`r`n", "`n").Replace("`r", "`n")
            )
        }

        return $Normalized.ToArray()
    }

    function Invoke-NativeDiagnostic {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0),

            [switch]$StreamOutput
        )

        $NativeArguments = @(
            Get-NormalizedNativeArguments -ArgumentList $ArgumentList
        )

        $PreviousErrorActionPreference = $ErrorActionPreference
        $Lines = New-Object 'System.Collections.Generic.List[string]'
        $ExitCode = 1

        try {
            # Windows PowerShell 5.1 can convert native stderr to ErrorRecord.
            # Diagnostic mode deliberately merges streams for human display.
            $ErrorActionPreference = "Continue"

            & $FilePath @NativeArguments 2>&1 |
                ForEach-Object {
                    $Text = $_.ToString()
                    [void]$Lines.Add($Text)

                    if ($StreamOutput) {
                        Write-Host $Text
                    }
                }

            $ExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }

        if ($AllowedExitCodes -notcontains $ExitCode) {
            if (-not $StreamOutput) {
                $Lines | ForEach-Object {
                    Write-Host $_
                }
            }

            throw (
                $FilePath +
                " failed with exit code " +
                $ExitCode +
                "."
            )
        }

        return [pscustomobject]@{
            ExitCode = [int]$ExitCode
            Output = @($Lines)
        }
    }

    function Invoke-NativeCapture {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0)
        )

        $NativeArguments = @(
            Get-NormalizedNativeArguments -ArgumentList $ArgumentList
        )

        $StdOutPath = [System.IO.Path]::GetTempFileName()
        $StdErrPath = [System.IO.Path]::GetTempFileName()
        $PreviousErrorActionPreference = $ErrorActionPreference
        $ExitCode = 1

        try {
            try {
                $ErrorActionPreference = "Continue"

                & $FilePath @NativeArguments 1> $StdOutPath 2> $StdErrPath
                $ExitCode = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $PreviousErrorActionPreference
            }

            # PowerShell owns the redirected files, so Get-Content can read
            # the encoding that this host wrote while keeping channels separate.
            $StdOut = @(
                Get-Content -LiteralPath $StdOutPath
            )

            $StdErr = @(
                Get-Content -LiteralPath $StdErrPath
            )

            if ($AllowedExitCodes -notcontains $ExitCode) {
                $StdErr | ForEach-Object {
                    Write-Host ("[STDERR] " + $_)
                }

                throw (
                    $FilePath +
                    " failed with exit code " +
                    $ExitCode +
                    "."
                )
            }

            return [pscustomobject]@{
                ExitCode = [int]$ExitCode
                StdOut = @($StdOut)
                StdErr = @($StdErr)
            }
        }
        finally {
            Remove-Item -LiteralPath $StdOutPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $StdErrPath -Force -ErrorAction SilentlyContinue
        }
    }

    function Get-NativeMachineText {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0)
        )

        $Result = Invoke-NativeCapture `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -AllowedExitCodes $AllowedExitCodes

        if ($Result.StdErr.Count -gt 0) {
            $Result.StdErr | ForEach-Object {
                Write-Host ("[DIAG] " + $_)
            }
        }

        return (($Result.StdOut -join "`n").Trim())
    }

    function Show-RecoveryState {
        Write-Host ""
        Write-Host "[RECOVERY] Phase: $CurrentPhase"

        foreach ($Entry in $MutationState.GetEnumerator()) {
            Write-Host (
                "[RECOVERY] " +
                $Entry.Key +
                ": " +
                $Entry.Value
            )
        }

        if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
            Write-Host "[RECOVERY] Repository root unavailable."
            return
        }

        try {
            Set-Location $Root

            $Branch = Get-NativeMachineText `
                -FilePath "git" `
                -ArgumentList @("branch", "--show-current")

            $Head = Get-NativeMachineText `
                -FilePath "git" `
                -ArgumentList @("rev-parse", "HEAD")

            $Status = Get-NativeMachineText `
                -FilePath "git" `
                -ArgumentList @(
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all"
                )

            Write-Host "[RECOVERY] Branch: $Branch"
            Write-Host "[RECOVERY] HEAD:   $Head"

            if ([string]::IsNullOrWhiteSpace($Status)) {
                Write-Host "[RECOVERY] Tree:   CLEAN"
            }
            else {
                Write-Host "[RECOVERY] Tree:   NOT CLEAN"
                Write-Host $Status
            }
        }
        catch {
            Write-Host (
                "[RECOVERY] State inspection failed: " +
                $_.Exception.Message
            )
        }
    }

    try {
        # ========================================================
        # TEMPLATE INSTANTIATION CHECK
        # ========================================================

        if ($ExpectedBaseHead -notmatch "^[0-9a-fA-F]{40}$") {
            throw "Template was not instantiated with a real 40-character base SHA."
        }

        if ($AllowedBranches.Count -eq 0) {
            throw "Template requires at least one allowed branch."
        }

        # ========================================================
        # PREFLIGHT
        # ========================================================

        $CurrentPhase = "preflight"
        Write-Phase -Name "VERIFY" -Message "Operator environment"

        if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
            throw "Repository root does not exist: $Root"
        }

        Set-Location $Root

        $RepositoryRoot = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("rev-parse", "--show-toplevel")

        $ResolvedExpectedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
        $ResolvedActualRoot = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\")

        if ($ResolvedActualRoot -ne $ResolvedExpectedRoot) {
            throw (
                "Wrong repository root. Expected " +
                $ResolvedExpectedRoot +
                ", found " +
                $ResolvedActualRoot +
                "."
            )
        }

        $Origin = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("remote", "get-url", "origin")

        $AllowedOrigins = @(
            $ExpectedOrigin,
            $ExpectedOrigin.TrimEnd(".git")
        )

        if ($AllowedOrigins -notcontains $Origin) {
            throw (
                "Wrong origin. Expected repository authority " +
                $ExpectedOrigin +
                ", found " +
                $Origin +
                "."
            )
        }

        $CurrentBranch = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("branch", "--show-current")

        if ($AllowedBranches -notcontains $CurrentBranch) {
            throw "Unexpected branch: $CurrentBranch"
        }

        $StatusText = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @(
                "status",
                "--porcelain=v1",
                "--untracked-files=all"
            )

        if (-not [string]::IsNullOrWhiteSpace($StatusText)) {
            throw (
                "Working tree is not clean before the operation:`n" +
                $StatusText
            )
        }

        $CurrentHead = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("rev-parse", "HEAD")

        $BaseAncestor = Invoke-NativeCapture `
            -FilePath "git" `
            -ArgumentList @(
                "merge-base",
                "--is-ancestor",
                $ExpectedBaseHead,
                $CurrentHead
            ) `
            -AllowedExitCodes @(0, 1)

        if ($BaseAncestor.ExitCode -ne 0) {
            throw (
                "Current HEAD is not descended from expected base " +
                $ExpectedBaseHead +
                "."
            )
        }

        Write-Host "[PASS] Repository identity verified"
        Write-Host "[PASS] Allowed branch verified: $CurrentBranch"
        Write-Host "[PASS] Working tree clean"
        Write-Host "[STATE] Expected base: $ExpectedBaseHead"
        Write-Host "[STATE] Current HEAD:  $CurrentHead"

        # ========================================================
        # OBSERVE CURRENT STATE
        # ========================================================

        $CurrentPhase = "observe-current-state"
        Write-Phase -Name "READ" -Message "Current durable state"

        # Task-specific code belongs here.
        # Inspect every durable object an earlier attempt could already have
        # created: commit, branch, remote ref, Issue, PR, merge, claim, stash,
        # checkout, output file, etc.
        #
        # Current HEAD is deliberately NOT required to equal the base SHA.
        # Verify exact parent/base, changed-file scope, commit identity and
        # remote state before reusing prior work.

        # ========================================================
        # PLAN NEXT MUTATION
        # ========================================================

        $CurrentPhase = "plan-next-mutation"
        Write-Phase -Name "PLAN" -Message "Resolve next missing authorized step"

        # Choose create/reuse/continue/validate/stop from CURRENT state.
        # Never duplicate work merely because an earlier run missed [DONE].

        # ========================================================
        # WORK
        # ========================================================

        $CurrentPhase = "work"
        Write-Phase -Name "WORK" -Message "Perform bounded mutation"

        # Perform only the next authorized mutation(s).
        # After every durable mutation, independently re-observe the result
        # before setting its MutationState field to $true.

        # For human-readable native work:
        #
        # Invoke-NativeDiagnostic `
        #     -FilePath "git" `
        #     -ArgumentList @("push", "origin", "HEAD:refs/heads/example") `
        #     -StreamOutput | Out-Null
        #
        # For machine data:
        #
        # $RemoteHead = Get-NativeMachineText `
        #     -FilePath "git" `
        #     -ArgumentList @("rev-parse", "origin/example")

        # ========================================================
        # VALIDATE
        # ========================================================

        $CurrentPhase = "validate"
        Write-Phase -Name "TEST" -Message "Exact resulting state"

        # Compare exact changed/staged path sets to explicit authorized paths.
        # Do not substitute a file count for path identity.
        # Run task-specific tests and whitespace checks.
        # Use stdout-only machine capture for data and exit-code predicates for
        # factual yes/no checks.

        # ========================================================
        # POSTCONDITIONS
        # ========================================================

        $CurrentPhase = "postconditions"
        Write-Phase -Name "VERIFY" -Message "Postconditions"

        $FinalBranch = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("branch", "--show-current")

        $FinalHead = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @("rev-parse", "HEAD")

        $FinalStatus = Get-NativeMachineText `
            -FilePath "git" `
            -ArgumentList @(
                "status",
                "--porcelain=v1",
                "--untracked-files=all"
            )

        $FinalTreeState = if ([string]::IsNullOrWhiteSpace($FinalStatus)) {
            "CLEAN"
        }
        else {
            "NOT CLEAN"
        }

        # ========================================================
        # FINAL REPORT
        # ========================================================

        $CurrentPhase = "done"

        Write-Host ""
        Write-Host "============================================================"
        Write-Host "[DONE] OPERATION COMPLETE"
        Write-Host "============================================================"
        Write-Host ""
        Write-Host "[STATE] Repository: $Root"
        Write-Host "[STATE] Base:       $ExpectedBaseHead"
        Write-Host "[STATE] Branch:     $FinalBranch"
        Write-Host "[STATE] HEAD:       $FinalHead"
        Write-Host "[STATE] Tree:       $FinalTreeState"
        Write-Host "[NEXT] Print one concrete task-specific next action here."
    }
    catch {
        Write-Host ""
        Write-Host "============================================================"
        Write-Host "[BLOCKED] OPERATION DID NOT REACH DONE"
        Write-Host "============================================================"
        Write-Host "[ERROR] $($_.Exception.Message)"

        Show-RecoveryState

        Write-Host ""
        Write-Host "[RECOVERY] Do not assume nothing happened. Re-observe authority before rerunning."
        throw
    }
}
```

## Why the template has two native helpers

`Invoke-NativeDiagnostic` deliberately combines stdout/stderr for human visibility. It is useful for progress and errors, but its `Output` is not machine authority.

`Invoke-NativeCapture` keeps `StdOut` and `StdErr` separate. `Get-NativeMachineText` returns only `StdOut` while still printing stderr as `[DIAG]` lines. Use this path for filenames, branch names, SHAs, refs, JSON, exact paths and counts.

This separation prevents harmless diagnostics such as:

```text
warning: LF will be replaced by CRLF ...
```

from becoming fake filenames in an exact-scope check.

## Mutation ledger semantics

The mutation ledger exists because these are different situations:

```text
parse failure
    PowerShell never executed the block

precondition failure
    runner stopped before the intended mutation

expected predicate false
    exit 1 represented FALSE, not tool failure

runtime failure before mutation
    tools ran but durable state did not change

partial mutation
    one or more durable changes may already exist

transient operational failure
    retry is allowed only when positively classified as transient
```

The ledger itself is not authority. Re-read Git, GitHub, TaskGraph, files and deterministic checks before recovery.

## Resume-state rule

A commit/push/PR/merge runner should distinguish states such as:

```text
base exists, patch absent
patch commit already exists and verifies exactly
remote branch already points to patch
PR already exists for exact head
PR already merged
current main already contains merge
```

If current state matches a previously completed authorized step, reuse it. If it cannot be verified exactly, stop.

## Text-editing subtemplate

Do not patch repository files with unchecked newline-sensitive multiline `.Replace()` logic.

Prefer:

1. structured parser/editor;
2. line-based edit with an exact anchor count;
3. normalized text plus exact-count scripted replacement.

Example:

```powershell
$Path = "Docs/example.md"
$Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$Text = $Text.Replace("`r`n", "`n").Replace("`r", "`n")

$Anchor = "exact stable anchor"
$Matches = [regex]::Matches($Text, [regex]::Escape($Anchor))

if ($Matches.Count -ne 1) {
    throw (
        "Expected exactly one edit anchor in " +
        $Path +
        "; found " +
        $Matches.Count +
        "."
    )
}

$Text = $Text.Replace($Anchor, "replacement text")

[System.IO.File]::WriteAllText(
    (Join-Path $Root $Path),
    ($Text.TrimEnd("`n") + "`n"),
    (New-Object System.Text.UTF8Encoding($false))
)
```

After mutation, immediately verify the exact changed-file set and run the relevant parser/test.

## Generated `.ps1` parser preflight

When the operator command is saved to a `.ps1` file, parse it before running:

```powershell
$Tokens = $null
$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref]$Tokens,
    [ref]$Errors
) | Out-Null

if ($Errors.Count -ne 0) {
    $Errors | ForEach-Object {
        Write-Host ("[PARSE] " + $_.Message)
    }

    throw "Generated PowerShell did not pass parser preflight."
}
```

Then run the bounded trusted file through a child PowerShell with `-ExecutionPolicy Bypass -File` rather than assuming the interactive process can load it.

## Commands that modify Git state

For bounded reviewed changes:

- stage exact paths only;
- do not use `git add .` or `git add -A` merely for convenience;
- inspect exact staged path identity before commit;
- run the required whitespace check;
- distinguish reviewed base from patch commit;
- verify a push by re-reading the remote ref;
- distinguish PR head from merge SHA and current `main`;
- never force-push, reset, clean or rewrite history as implicit recovery.

## Long-running operation variant

Long-running provider work is normally a separate operator phase from deterministic setup.

A long-running runner must:

- identify exact checkout/branch/commit before invocation;
- show progress/heartbeat where supported;
- persist a readable transcript when needed later;
- print the authoritative output location;
- check the native exit code;
- avoid open-ended interactive shells for bounded work;
- clean up subprocesses/containers according to intended lifecycle.

## Final-report rule

A successful substantial command must leave enough concrete state for another context to continue without reconstructing terminal history.

Print applicable values from:

```text
repository
branch
base SHA
patch/result SHA
remote branch SHA
Issue number/state
PR number/head SHA
merge SHA
current main SHA
working-tree state
validation result
output/log path
next action
```

A failed command that may have crossed a durable mutation boundary must print recovery state and warn against blind rerun.
