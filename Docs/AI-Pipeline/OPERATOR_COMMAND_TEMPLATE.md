# Operator Command Template

This file defines the canonical shape for substantial human-run operator commands generated for this repository.

It is operating guidance, not game-design canon and not evidence of repository state.

The template is intentionally conservative. It exists because this project has repeatedly paid for avoidable command failures involving Windows PowerShell 5.1 parsing, native stderr semantics, CRLF crossing into Linux, stale working directories, brittle multiline text replacement, stale SHA assumptions after partial mutation, unexpected changed-file scope, and commands that appeared hung while still running.

This template does not replace task-specific runbooks. It defines the execution skeleton that task-specific commands should instantiate.

## When this template is required

Use this shape for any substantial operator block that can:

- create, modify, move, or delete repository files;
- create commits, branches, tags, claims, Issues, PRs, or other durable state;
- push, merge, or otherwise change remote state;
- create or modify task checkouts;
- run a multi-step validation/delivery sequence where a partial prior run may have succeeded;
- invoke a long-running provider or external tool whose exit status and progress must be visible.

A one-line read-only command such as `git status --short` does not need the full skeleton.

## Compatibility baseline

Unless the operator explicitly says otherwise, generated commands must be compatible with **Windows PowerShell 5.1**.

Do not use Bash-only syntax, PowerShell-7-only syntax, or shell behavior that depends on the current terminal being anything other than Windows PowerShell 5.1.

## Required command phases

A substantial mutating command should have these conceptual phases:

```text
IDENTITY
    define exact repository/work item/expected authority

PREFLIGHT
    prove paths, tools, repository, branch, HEAD and working-tree assumptions

OBSERVE CURRENT STATE
    detect whether an earlier attempt already completed one or more mutations

PLAN NEXT MUTATION
    decide the next missing authorized step from current state

WORK
    cross the smallest intended mutation boundary

VALIDATE
    prove exact scope, tests, identities and remote state

POSTCONDITIONS
    prove the intended resulting state and a clean/understood tree

FINAL REPORT
    state exactly what happened, what did not happen, current authority and next action
```

`OBSERVE CURRENT STATE` is mandatory for a runner that could be rerun after a commit, push, Issue mutation, PR creation, merge, or other durable mutation. A runner must not assume that failure means nothing happened.

## Canonical substantial PowerShell block

The following is a **template, not a paste-ready command**. Agents must replace the example identity values with values derived from current repository reality before giving the block to the operator. A paste-ready block must never contain literal `<PLACEHOLDER>`, `REPLACE_ME`, or similar sentinel text.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY - ALL CRITICAL STATE IS DEFINED INSIDE THIS BLOCK
    # ============================================================

    $Root = "C:\NSC\NSC\NoSafeCircle"
    $ExpectedBranch = "main"
    $ExpectedStartingHead = "0000000000000000000000000000000000000000"

    # Use a concrete expected remote/repository identity when the operation
    # can affect remote state. Do not infer authority from conversation text.
    $ExpectedOrigin = "https://github.com/cathode26/NoSafeCircle.git"

    # Record durable mutations only AFTER each mutation is independently
    # observed to have succeeded. These flags make a partial failure legible.
    $MutationState = [ordered]@{
        FilesModified = $false
        CommitCreated = $false
        BranchPushed = $false
        PullRequestCreated = $false
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

    function Get-NativeText {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0)
        )

        $Result = Invoke-NscNativeCommand `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList

        if ($AllowedExitCodes -notcontains $Result.ExitCode) {
            throw (
                $FilePath + " " +
                ($ArgumentList -join " ") +
                " failed with exit code " +
                $Result.ExitCode +
                "."
            )
        }

        return (($Result.Output -join "`n").Trim())
    }

    function Invoke-NativeChecked {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0),

            [switch]$StreamOutput
        )

        $Result = Invoke-NscNativeCommand `
            -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -StreamOutput:$StreamOutput

        if ($AllowedExitCodes -notcontains $Result.ExitCode) {
            throw (
                $FilePath + " " +
                ($ArgumentList -join " ") +
                " failed with exit code " +
                $Result.ExitCode +
                "."
            )
        }

        return $Result
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

        if (Test-Path -LiteralPath $Root -PathType Container) {
            $Previous = Get-Location

            try {
                Set-Location $Root

                $BranchResult = Invoke-NscNativeCommand `
                    -FilePath "git" `
                    -ArgumentList @("branch", "--show-current")

                if ($BranchResult.ExitCode -eq 0) {
                    Write-Host (
                        "[RECOVERY] Current branch: " +
                        (($BranchResult.Output -join "`n").Trim())
                    )
                }

                $HeadResult = Invoke-NscNativeCommand `
                    -FilePath "git" `
                    -ArgumentList @("rev-parse", "HEAD")

                if ($HeadResult.ExitCode -eq 0) {
                    Write-Host (
                        "[RECOVERY] Current HEAD: " +
                        (($HeadResult.Output -join "`n").Trim())
                    )
                }

                $StatusResult = Invoke-NscNativeCommand `
                    -FilePath "git" `
                    -ArgumentList @(
                        "status",
                        "--porcelain=v1",
                        "--untracked-files=all"
                    )

                if ($StatusResult.ExitCode -eq 0) {
                    $StatusText = ($StatusResult.Output -join "`n").Trim()

                    if ([string]::IsNullOrWhiteSpace($StatusText)) {
                        Write-Host "[RECOVERY] Working tree: CLEAN"
                    }
                    else {
                        Write-Host "[RECOVERY] Working tree: NOT CLEAN"
                        $StatusResult.Output | ForEach-Object {
                            Write-Host ("  " + $_)
                        }
                    }
                }
            }
            finally {
                Set-Location $Previous
            }
        }
    }

    try {
        # ========================================================
        # PREFLIGHT
        # ========================================================

        $CurrentPhase = "preflight"
        Write-Phase -Name "VERIFY" -Message "Operator environment"

        if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
            throw "Repository root does not exist: $Root"
        }

        Set-Location $Root

        $NativeHelper = Join-Path `
            $Root `
            "Pipeline\TaskReviewAgent\NativeCommand.ps1"

        if (-not (Test-Path -LiteralPath $NativeHelper -PathType Leaf)) {
            throw "Native command helper is missing: $NativeHelper"
        }

        . $NativeHelper

        $RepositoryRoot = Get-NativeText `
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

        $Origin = Get-NativeText `
            -FilePath "git" `
            -ArgumentList @("remote", "get-url", "origin")

        if ($Origin -ne $ExpectedOrigin) {
            throw (
                "Wrong origin. Expected " +
                $ExpectedOrigin +
                ", found " +
                $Origin +
                "."
            )
        }

        $Branch = Get-NativeText `
            -FilePath "git" `
            -ArgumentList @("branch", "--show-current")

        if ($Branch -ne $ExpectedBranch) {
            throw (
                "Wrong branch. Expected " +
                $ExpectedBranch +
                ", found " +
                $Branch +
                "."
            )
        }

        $StartingHead = Get-NativeText `
            -FilePath "git" `
            -ArgumentList @("rev-parse", "HEAD")

        if ($StartingHead -ne $ExpectedStartingHead) {
            throw (
                "Starting HEAD moved. Expected " +
                $ExpectedStartingHead +
                ", found " +
                $StartingHead +
                "."
            )
        }

        $StatusText = Get-NativeText `
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

        Write-Host "[PASS] Repository identity verified"
        Write-Host "[PASS] Branch and starting HEAD verified"
        Write-Host "[PASS] Working tree clean"

        # ========================================================
        # OBSERVE CURRENT STATE
        # ========================================================

        $CurrentPhase = "observe-current-state"
        Write-Phase -Name "READ" -Message "Current durable state"

        # Inspect every durable object that an earlier attempt could already
        # have created: target branch, patch commit, remote ref, Issue, PR,
        # merge, claim, output file, etc. Use typed/structured queries or
        # documented native exit codes. Do not infer state from an old console
        # transcript or conversation.
        #
        # Examples of predicate commands whose exit code 1 may mean FALSE,
        # not operational failure:
        #
        # $Exists = Invoke-NativeChecked `
        #     -FilePath "git" `
        #     -ArgumentList @(
        #         "show-ref",
        #         "--verify",
        #         "--quiet",
        #         "refs/heads/example"
        #     ) `
        #     -AllowedExitCodes @(0, 1)
        #
        # if ($Exists.ExitCode -eq 0) {
        #     Write-Host "[STATE] Existing branch detected"
        # }

        # ========================================================
        # PLAN NEXT MUTATION
        # ========================================================

        $CurrentPhase = "plan-next-mutation"
        Write-Phase -Name "PLAN" -Message "Resolve next missing authorized step"

        # Decide from CURRENT state whether the next step is create, reuse,
        # continue, validate, or stop. If an earlier attempt already completed
        # a step, verify and reuse it. Never create a duplicate merely because
        # the original runner did not reach its final [DONE] message.

        # ========================================================
        # WORK - CROSS THE SMALLEST MUTATION BOUNDARY
        # ========================================================

        $CurrentPhase = "work"
        Write-Phase -Name "WORK" -Message "Perform bounded mutation"

        # Perform only the next authorized mutation(s). After each durable
        # mutation, independently observe its result before setting the matching
        # MutationState flag to $true.
        #
        # Example after a successful verified commit:
        # $MutationState.CommitCreated = $true
        #
        # Example after a successful verified push:
        # $MutationState.BranchPushed = $true

        # ========================================================
        # VALIDATE
        # ========================================================

        $CurrentPhase = "validate"
        Write-Phase -Name "TEST" -Message "Exact resulting state"

        # Validate exact changed-file scope. For bounded reviewed work, compare
        # the actual path set against an explicit expected path set.
        # Do not substitute a changed-file count for path identity.
        #
        # Run task-specific deterministic tests.
        #
        # For Git predicates, use documented exit-code semantics instead of
        # parsing stderr or relying on output count.

        # ========================================================
        # POSTCONDITIONS
        # ========================================================

        $CurrentPhase = "postconditions"
        Write-Phase -Name "VERIFY" -Message "Postconditions"

        # Re-read resulting branch/HEAD/remote/PR/Issue authority as applicable.
        # Verify the final working-tree state is exactly what the operation
        # promises: normally CLEAN, otherwise an explicitly documented bounded
        # set of expected paths.

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
        Write-Host "[STATE] Branch:     <resolved current branch>"
        Write-Host "[STATE] HEAD:       <resolved current HEAD>"
        Write-Host "[STATE] Tree:       <CLEAN or exact bounded state>"
        Write-Host "[NEXT] <one concrete next action>"
    }
    catch {
        Write-Host ""
        Write-Host "============================================================"
        Write-Host "[BLOCKED] OPERATION DID NOT REACH DONE"
        Write-Host "============================================================"
        Write-Host "[ERROR] $($_.Exception.Message)"

        Show-RecoveryState

        Write-Host ""
        Write-Host (
            "[RECOVERY] Do not assume nothing happened. " +
            "Inspect the state above before rerunning."
        )

        throw
    }
}
```

## Why the mutation ledger exists

A runner that creates a commit and then fails while creating a PR did **not** fail in the same way as a parser error that prevented any line from executing.

The operator must be able to distinguish at least:

```text
parse failure
    no block execution occurred

precondition failure
    runner stopped before the intended mutation boundary

expected predicate false
    exit code such as 1 represented FALSE, not a broken command

runtime failure before mutation
    tools ran but durable authority was not changed

partial mutation
    one or more durable changes may already exist

transient operational failure
    retry is allowed only when positively classified as transient
```

The mutation ledger is not authority by itself. It is an operator-visible hint. Current Git, GitHub, TaskGraph, Issues, refs, files and deterministic checks remain authoritative and must be re-read before recovery.

## Text-editing subtemplate

Do not patch repository files with an unchecked newline-sensitive multiline `String.Replace()`.

For text that is not parsed through a structured editor, normalize line endings first and require an exact anchor count before mutation:

```powershell
$Path = "Docs/example.md"
$Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$Text = $Text.Replace("`r`n", "`n").Replace("`r", "`n")

$Anchor = "exact stable anchor"
$Matches = [regex]::Matches(
    $Text,
    [regex]::Escape($Anchor)
)

if ($Matches.Count -ne 1) {
    throw (
        "Expected exactly one edit anchor in " +
        $Path +
        "; found " +
        $Matches.Count +
        "."
    )
}

$Replacement = "replacement text"
$Text = $Text.Replace($Anchor, $Replacement)

[System.IO.File]::WriteAllText(
    (Join-Path $Root $Path),
    ($Text.TrimEnd("`n") + "`n"),
    (New-Object System.Text.UTF8Encoding($false))
)
```

Prefer a structured parser/editor or line-based mutation when the file format makes that safer.

After every automated text mutation, verify the exact changed-file set and run the relevant parser/test before staging.

## Native command rules represented by the template

The repository's canonical native helper is:

```text
Pipeline/TaskReviewAgent/NativeCommand.ps1
```

Use it rather than treating native stderr as a PowerShell exception signal. Native success/failure is determined from the process exit code.

Every native predicate must declare the exit codes that are valid data. Examples include:

```text
git diff --quiet                  0 = equal, 1 = different
git show-ref --verify --quiet    0 = exists, 1 = absent
git merge-base --is-ancestor     0 = yes, 1 = no
```

Do not merge stderr into an array and then use array length as factual authority about changed files, refs, or other repository state.

## Cross-OS multiline arguments

Any multiline textual argument passed from Windows PowerShell to a Linux container/process must be normalized from CRLF/CR to LF before crossing the boundary.

`Invoke-NscNativeCommand` already performs this normalization for its argument list. Do not bypass it with a raw multiline argument unless the caller performs equivalent normalization deliberately.

## Long-running operation variant

Long-running provider execution is normally a separate operator phase from deterministic setup. Follow `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`.

A long-running command must:

- identify the exact checkout/branch/commit before provider invocation;
- stream human-readable progress when the underlying tool supports it;
- use unbuffered outer Python execution where needed;
- write a durable readable transcript when output will be needed later;
- print the authoritative run/output location;
- check the native exit code explicitly;
- avoid launching an open-ended interactive shell as the automation target;
- stop/clean up containers or subprocesses according to their intended lifecycle.

## Commands that modify Git state

For bounded reviewed changes:

- stage exact paths only;
- never use `git add -A` or `git add .` merely for convenience;
- inspect the exact staged path set before commit;
- run `git diff --cached --check` with the repository's required whitespace compatibility settings;
- distinguish starting/base SHA from created patch SHA;
- verify a push by re-reading the remote ref;
- distinguish PR head SHA from merge SHA and current `main` SHA;
- never force-push, reset, clean or rewrite history as an implicit recovery action.

## Output-volume rule

A technically correct command that floods the console with thousands of irrelevant lines is not a good operator command.

Prefer:

- scoped search roots;
- filenames instead of full matches when enough;
- counts plus a concise sample;
- filtered human-readable progress;
- detailed output written to a durable log when needed.

The operator should not need to scroll through a giant dump to determine success, failure or the next action.

## Final-report rule

A successful substantial command must end with enough concrete state that another context can continue without reconstructing the run from terminal history.

At minimum, print the applicable values from this set:

```text
repository
branch
starting/base SHA
created/patch SHA
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

A failed command that crossed any possible mutation boundary must print a recovery report and explicitly warn against blind rerun.

## Related operating guidance

Read these together when applicable:

- `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`
- `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`
- `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`
- `Pipeline/TaskReviewAgent/NativeCommand.ps1`

This template should remain focused on command construction and recovery semantics. Task-specific authority belongs in the task/runbook that instantiates it.
