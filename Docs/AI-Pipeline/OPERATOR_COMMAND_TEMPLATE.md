# Operator Command Template

This file defines the canonical shape for substantial human-run operator commands generated for this repository.

It is operating guidance, not game-design canon and not evidence of repository state.

The template is intentionally conservative. This project has repeatedly paid for avoidable command failures involving Windows PowerShell 5.1 parsing, native stderr semantics, CRLF crossing into Linux, stale working directories, brittle multiline text replacement, stale SHA assumptions after partial mutation, unexpected changed-file scope, and commands that appeared hung while still running.

This template does not replace task-specific runbooks. It defines the execution skeleton that task-specific commands should instantiate.

## When this template is required

Use this shape for a substantial operator block that can:

- create, modify, move, or delete repository files;
- create commits, branches, tags, claims, Issues, PRs, or other durable state;
- push, merge, or otherwise change remote state;
- create or modify task checkouts;
- run a multi-step validation/delivery sequence where a prior attempt may have partially succeeded;
- invoke a long-running provider or external tool whose progress and exit status must be visible.

A one-line read-only command such as `git status --short` does not need the full skeleton.

## Compatibility baseline

Unless the operator explicitly says otherwise, generated commands must be compatible with **Windows PowerShell 5.1**.

Do not use Bash-only syntax, PowerShell-7-only syntax, or shell behavior that depends on a different terminal.

Avoid backtick line continuation in generated operator commands when a one-line invocation, array, hashtable splat, or natural PowerShell continuation can express the same call. A trailing space after a continuation backtick is invisible and brittle.

If a generated command is saved as a `.ps1` file rather than pasted directly:

- keep executable source ASCII-safe when practical, or save it with an encoding Windows PowerShell 5.1 reads correctly;
- parse the file before execution with `System.Management.Automation.Language.Parser`;
- treat any parser error as **no execution occurred** and correct the script before retrying.

## Required command phases

A substantial mutating command should have these conceptual phases:

```text
IDENTITY
    define exact repository/work item/base authority

PREFLIGHT
    prove paths, tools, repository, allowed branch and working-tree assumptions

OBSERVE CURRENT STATE
    read current HEAD/refs/Issues/PRs/files and determine whether prior mutations already happened

PLAN NEXT MUTATION
    choose the next missing authorized step from current state

WORK
    cross the smallest intended mutation boundary

VALIDATE
    prove exact scope, tests, identities and remote state

POSTCONDITIONS
    prove the intended resulting state and a clean/understood tree

FINAL REPORT
    state exactly what happened, current authority and the next action
```

`OBSERVE CURRENT STATE` is mandatory for a runner that could be rerun after a commit, push, Issue mutation, PR creation, merge, or other durable mutation.

A resume-safe runner must **not** blindly require `HEAD == base` before observation. The base SHA is an authority anchor, but current `HEAD` may legitimately be a previously created patch/merge commit from an earlier partial run. Current state must be inspected and classified before deciding whether to continue, reuse, or stop.

## Canonical substantial PowerShell block

The following is a **template, not a paste-ready command**. Agents must instantiate it with values derived from current repository reality before giving it to the operator.

A paste-ready block must never contain literal `<PLACEHOLDER>`, `REPLACE_ME`, `SET_ME`, fake SHAs, or similar sentinel values.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY - DEFINE ALL CRITICAL STATE INSIDE THIS BLOCK
    # ============================================================

    $Root = "C:\NSC\NSC\NoSafeCircle"
    $ExpectedOrigin = "https://github.com/cathode26/NoSafeCircle.git"
    $ExpectedBaseHead = "SET_FROM_VERIFIED_CURRENT_STATE"
    $AllowedBranches = @("main", "target-operation-branch")

    # These flags are operator-visible hints only. They are set to $true only
    # after the corresponding mutation is independently re-observed.
    $MutationState = [ordered]@{
        FilesModified = $false
        CommitCreated = $false
        BranchPushed = $false
        PullRequestCreated = $false
        MergeCompleted = $false
    }

    $CurrentPhase = "identity"
    $NativeHelperLoaded = $false

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

    function Invoke-CheckedNative {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0),

            [switch]$StreamOutput
        )

        $Result = Invoke-NscNativeCommand -FilePath $FilePath -ArgumentList $ArgumentList -StreamOutput:$StreamOutput

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

    function Get-NativeText {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0)
        )

        $Result = Invoke-CheckedNative -FilePath $FilePath -ArgumentList $ArgumentList -AllowedExitCodes $AllowedExitCodes
        return (($Result.Output -join "`n").Trim())
    }

    function Show-RecoveryState {
        Write-Host ""
        Write-Host "[RECOVERY] Phase: $CurrentPhase"

        foreach ($Entry in $MutationState.GetEnumerator()) {
            Write-Host ("[RECOVERY] " + $Entry.Key + ": " + $Entry.Value)
        }

        if (-not $NativeHelperLoaded) {
            Write-Host "[RECOVERY] Native helper was not loaded; Git recovery snapshot skipped."
            return
        }

        if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
            Write-Host "[RECOVERY] Repository root is unavailable; Git recovery snapshot skipped."
            return
        }

        try {
            Set-Location $Root

            $BranchResult = Invoke-NscNativeCommand -FilePath "git" -ArgumentList @("branch", "--show-current")
            if ($BranchResult.ExitCode -eq 0) {
                Write-Host ("[RECOVERY] Current branch: " + (($BranchResult.Output -join "`n").Trim()))
            }

            $HeadResult = Invoke-NscNativeCommand -FilePath "git" -ArgumentList @("rev-parse", "HEAD")
            if ($HeadResult.ExitCode -eq 0) {
                Write-Host ("[RECOVERY] Current HEAD: " + (($HeadResult.Output -join "`n").Trim()))
            }

            $StatusResult = Invoke-NscNativeCommand -FilePath "git" -ArgumentList @("status", "--porcelain=v1", "--untracked-files=all")
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
        catch {
            Write-Host ("[RECOVERY] Recovery inspection itself failed: " + $_.Exception.Message)
        }
    }

    try {
        # ========================================================
        # TEMPLATE INSTANTIATION CHECK
        # ========================================================

        $CurrentPhase = "identity"

        if ($ExpectedBaseHead -notmatch "^[0-9a-fA-F]{40}$") {
            throw "Template was not instantiated with a real 40-character base SHA."
        }

        if ($AllowedBranches.Count -eq 0) {
            throw "Template was not instantiated with at least one allowed branch."
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

        $NativeHelper = Join-Path $Root "Pipeline\TaskReviewAgent\NativeCommand.ps1"
        if (-not (Test-Path -LiteralPath $NativeHelper -PathType Leaf)) {
            throw "Native command helper is missing: $NativeHelper"
        }

        . $NativeHelper
        $NativeHelperLoaded = $true

        $RepositoryRoot = Get-NativeText -FilePath "git" -ArgumentList @("rev-parse", "--show-toplevel")
        $ResolvedExpectedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
        $ResolvedActualRoot = [System.IO.Path]::GetFullPath($RepositoryRoot).TrimEnd("\")

        if ($ResolvedActualRoot -ne $ResolvedExpectedRoot) {
            throw ("Wrong repository root. Expected " + $ResolvedExpectedRoot + ", found " + $ResolvedActualRoot + ".")
        }

        $Origin = Get-NativeText -FilePath "git" -ArgumentList @("remote", "get-url", "origin")
        if ($Origin -ne $ExpectedOrigin) {
            throw ("Wrong origin. Expected " + $ExpectedOrigin + ", found " + $Origin + ".")
        }

        $CurrentBranch = Get-NativeText -FilePath "git" -ArgumentList @("branch", "--show-current")
        if ($AllowedBranches -notcontains $CurrentBranch) {
            throw ("Unexpected branch: " + $CurrentBranch)
        }

        $StatusText = Get-NativeText -FilePath "git" -ArgumentList @("status", "--porcelain=v1", "--untracked-files=all")
        if (-not [string]::IsNullOrWhiteSpace($StatusText)) {
            throw ("Working tree is not clean before the operation:`n" + $StatusText)
        }

        $CurrentHead = Get-NativeText -FilePath "git" -ArgumentList @("rev-parse", "HEAD")

        $BaseAncestor = Invoke-CheckedNative -FilePath "git" -ArgumentList @("merge-base", "--is-ancestor", $ExpectedBaseHead, $CurrentHead) -AllowedExitCodes @(0, 1)
        if ($BaseAncestor.ExitCode -ne 0) {
            throw ("Current HEAD is not descended from expected base " + $ExpectedBaseHead + ".")
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

        # Task-specific runner code belongs here.
        #
        # Inspect every durable object an earlier attempt could already have
        # created: target branch, patch commit, remote ref, Issue, PR, merge,
        # claim, output file, etc.
        #
        # IMPORTANT: Current HEAD is deliberately NOT required to equal the
        # base SHA. If it differs, verify whether it is an authorized result of
        # this operation (for example exact parent/base, exact commit message,
        # exact changed-file set and exact remote branch) before reusing it.
        #
        # Git predicates whose exit code 1 represents FALSE must declare both
        # codes as accepted data:
        #
        # $Exists = Invoke-CheckedNative -FilePath "git" -ArgumentList @(
        #     "show-ref",
        #     "--verify",
        #     "--quiet",
        #     "refs/heads/example"
        # ) -AllowedExitCodes @(0, 1)
        #
        # if ($Exists.ExitCode -eq 0) {
        #     Write-Host "[STATE] Existing branch detected"
        # }

        # ========================================================
        # PLAN NEXT MUTATION
        # ========================================================

        $CurrentPhase = "plan-next-mutation"
        Write-Phase -Name "PLAN" -Message "Resolve next missing authorized step"

        # Decide from CURRENT deterministic state whether the next action is
        # create, reuse, continue, validate, or stop.
        #
        # Never create a duplicate merely because a previous invocation did not
        # reach its final [DONE] message.

        # ========================================================
        # WORK - CROSS THE SMALLEST MUTATION BOUNDARY
        # ========================================================

        $CurrentPhase = "work"
        Write-Phase -Name "WORK" -Message "Perform bounded mutation"

        # Perform only the next authorized mutation(s).
        #
        # After every durable mutation, independently re-observe the resulting
        # Git/GitHub/filesystem state before setting the matching MutationState
        # flag to $true.
        #
        # Example:
        #   create commit
        #   re-read HEAD and verify exact commit identity
        #   $MutationState.CommitCreated = $true
        #
        # Example:
        #   push branch
        #   re-read remote branch SHA
        #   $MutationState.BranchPushed = $true

        # ========================================================
        # VALIDATE
        # ========================================================

        $CurrentPhase = "validate"
        Write-Phase -Name "TEST" -Message "Exact resulting state"

        # Validate exact changed-file/staged-file scope against explicit paths.
        # Do not substitute a file COUNT for path identity.
        #
        # Run task-specific deterministic tests and whitespace checks.
        #
        # Use exit-code predicates for factual checks instead of parsing stderr
        # or counting captured output lines.

        # ========================================================
        # POSTCONDITIONS
        # ========================================================

        $CurrentPhase = "postconditions"
        Write-Phase -Name "VERIFY" -Message "Postconditions"

        # Re-read resulting branch/HEAD/remote/Issue/PR authority as applicable.
        # Verify the final working-tree state is exactly what the operation
        # promises: normally CLEAN, otherwise an explicitly documented bounded
        # set of paths.

        $FinalBranch = Get-NativeText -FilePath "git" -ArgumentList @("branch", "--show-current")
        $FinalHead = Get-NativeText -FilePath "git" -ArgumentList @("rev-parse", "HEAD")
        $FinalStatus = Get-NativeText -FilePath "git" -ArgumentList @("status", "--porcelain=v1", "--untracked-files=all")
        $FinalTreeState = if ([string]::IsNullOrWhiteSpace($FinalStatus)) { "CLEAN" } else { "NOT CLEAN" }

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
        Write-Host "[RECOVERY] Do not assume nothing happened. Inspect current authority before rerunning."
        throw
    }
}
```

## Mutation ledger semantics

The mutation ledger exists because these are different failures:

```text
parse failure
    PowerShell never executed the block

precondition failure
    runner stopped before the intended mutation boundary

expected predicate false
    an exit code such as 1 represented FALSE, not an operational failure

runtime failure before mutation
    tools ran but durable authority was not changed

partial mutation
    one or more durable changes may already exist

transient operational failure
    retry is allowed only when positively classified as transient
```

The ledger is not authority. Current Git, GitHub, TaskGraph, Issues, refs, files and deterministic checks remain authoritative and must be re-read before recovery.

## Resume-state rule

A substantial runner that can create durable state must be designed around **state observation**, not a linear assumption that every invocation starts from zero.

For example, a commit/push/PR/merge runner should distinguish at least:

```text
base exists, patch absent
patch commit already exists and verifies exactly
remote branch already points to verified patch
PR already exists for exact head
PR already merged
current main already contains the patch/merge
```

If current state matches a previously completed authorized step, reuse it. If it is incompatible or cannot be verified exactly, stop.

## Text-editing subtemplate

Do not patch repository files with an unchecked newline-sensitive multiline `String.Replace()`.

Prefer, in this order:

1. a structured parser/editor for structured formats;
2. a line-based edit with an exact anchor count;
3. normalized text plus an exact-count regex/string edit.

For a normalized text edit:

```powershell
$Path = "Docs/example.md"
$Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
$Text = $Text.Replace("`r`n", "`n").Replace("`r", "`n")

$Anchor = "exact stable anchor"
$Matches = [regex]::Matches($Text, [regex]::Escape($Anchor))

if ($Matches.Count -ne 1) {
    throw ("Expected exactly one edit anchor in " + $Path + "; found " + $Matches.Count + ".")
}

$Text = $Text.Replace($Anchor, "replacement text")

[System.IO.File]::WriteAllText(
    (Join-Path $Root $Path),
    ($Text.TrimEnd("`n") + "`n"),
    (New-Object System.Text.UTF8Encoding($false))
)
```

After every automated text mutation, verify the exact changed-file set and run the relevant parser/test before staging.

If the target is an executable Windows PowerShell `.ps1` file and contains non-ASCII text, use an encoding compatible with Windows PowerShell 5.1 and parser-preflight the resulting file before execution.

## PowerShell parser preflight for generated scripts

When the operator command is written to a `.ps1` file, parse it before running it:

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

    throw "Generated PowerShell did not pass parser preflight. No execution should be attempted."
}
```

## Native command rules represented by the template

The repository's canonical native helper is:

```text
Pipeline/TaskReviewAgent/NativeCommand.ps1
```

Use it rather than treating native stderr as a PowerShell exception signal. Native success/failure is determined from the process exit code.

Every native predicate must declare exit codes that are valid data. Examples:

```text
git diff --quiet                  0 = equal, 1 = different
git show-ref --verify --quiet    0 = exists, 1 = absent
git merge-base --is-ancestor     0 = yes, 1 = no
```

Do not merge stderr into an array and then use array length as factual authority about changed files, refs, or repository state.

## Cross-OS multiline arguments

Any multiline textual argument passed from Windows PowerShell to a Linux container/process must be normalized from CRLF/CR to LF before crossing the boundary.

`Invoke-NscNativeCommand` already performs this normalization for its argument list. Do not bypass it with a raw multiline argument unless the caller performs equivalent normalization deliberately.

## Long-running operation variant

Long-running provider execution is normally a separate operator phase from deterministic setup. Follow `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`.

A long-running command must:

- identify the exact checkout/branch/commit before provider invocation;
- stream human-readable progress when supported;
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
- distinguish base SHA from created patch SHA;
- verify a push by re-reading the remote ref;
- distinguish PR head SHA from merge SHA and current `main` SHA;
- never force-push, reset, clean or rewrite history as an implicit recovery action.

## Output-volume rule

A technically correct command that floods the console with thousands of irrelevant lines is not a good operator command.

Prefer scoped search roots, filenames instead of full matches when enough, counts plus a concise sample, filtered progress, and a durable detailed log when needed.

The operator should not need to scroll through a giant dump to determine success, failure or the next action.

## Final-report rule

A successful substantial command must end with enough concrete state that another context can continue without reconstructing the run from terminal history.

Print the applicable values from this set:

```text
repository
branch
base SHA
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
