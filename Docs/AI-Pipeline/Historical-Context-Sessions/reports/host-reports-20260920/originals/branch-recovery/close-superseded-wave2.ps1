# Close the superseded NSC-051, NSC-052 and NSC-032 branches. Local only.
# This script never contacts GitHub: no fetch, no push, no remote deletion.
# Every branch tip is saved under refs/archive/ before its branch ref is deleted,
# so any of them can be restored with: git branch <name> refs/archive/<name>

$ErrorActionPreference = "Continue"

$Repo = "C:\NSC\NSC\NoSafeCircle"

# Branch name -> exact tip verified on 2026-09-15. A moved tip means skip, not delete.
$Branches = [ordered]@{
    "codex/nsc051-final-main-20260914"                   = "a6f3b562fdc70bd1fd84be0d6e1476829f6a91b9"
    "codex/nsc051-door-passability-20260914"             = "9fa5c63e6c9b483886fde631d749610ef3dd29b8"
    "codex/nsc052-current-main-stage-20260914"           = "f31afaff1255a7f95ea0b8f8eb6170ab59c0f30a"
    "codex/nsc052-verification-20260914"                 = "3ebc60e4cead365c5f32c0f5ff37c8201370f15f"
    "codex/nsc032-051-combined-20260914"                 = "3b83a2a5ec81892139b75fad82910a10546a79e9"
    "codex/nsc032-051-main-stage-20260914"               = "ab0e2f37152ad677046bd577bb14bcd880fbe22d"
    "codex/nsc032-current-main-recovery-20260914"        = "5eb645e33b3f2ac6b08e9c025f61cedebab980e2"
    "codex/nsc032-index-refresh-20260914"                = "b314022ec8a8a8847dc9567b60d82b7b08c14c4d"
    "codex/nsc032-materialization-policy-recovery-20260914" = "026fe2ce2af601c71e161f70925598bead8adee8"
    "codex/nsc032-meta-materialization-recovery-20260914"   = "e72afcffc49e90e74c5631da6a962bb5ce7bcf9a"
}

# Worktrees belonging to those branches, including detached validation checkouts.
# The nsc052-val003 pair is deliberately absent: that branch was not reviewed.
$Worktrees = @(
    "C:\NSC\_worktrees\nsc051-combined-unity-validation-20260914",
    "C:\NSC\_worktrees\nsc051-door-passability-20260914",
    "C:\NSC\_worktrees\nsc051-final-main-20260914",
    "C:\NSC\_worktrees\nsc052-current-main-stage-20260914",
    "C:\NSC\_worktrees\nsc052-play-exact-20260914",
    "C:\NSC\_worktrees\nsc052-test-exact-20260914",
    "C:\NSC\_worktrees\nsc052-unity-check-20260914",
    "C:\NSC\_worktrees\nsc052-verification-20260914",
    "C:\NSC\_worktrees\nsc032-051-combined-20260914",
    "C:\NSC\_worktrees\nsc032-051-combined-exact-unity-20260914",
    "C:\NSC\_worktrees\nsc032-051-combined-unity-20260914",
    "C:\NSC\_worktrees\nsc032-051-final-main-stage-20260914",
    "C:\NSC\_worktrees\nsc032-current-main-recovery-20260914",
    "C:\NSC\_worktrees\nsc032-index-refresh-20260914",
    "C:\NSC\_worktrees\nsc032-materialization-policy-recovery-20260914",
    "C:\NSC\_worktrees\nsc032-meta-materialization-recovery-20260914",
    "C:\NSC\_worktrees\nsc032-unity-validation-20260914"
)

function Invoke-GitText {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $text = (& git -C $Repo @Arguments 2>$null | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous

    return [pscustomobject]@{ ExitCode = $code; Text = $text.Trim() }
}

function Write-Phase {
    param([string]$Name, [string]$Message)
    Write-Host ""
    Write-Host "[$Name] $Message"
}

# ============================================================
# PREFLIGHT
# ============================================================

Write-Phase -Name "VERIFY" -Message "Repository and branch tips"

if (-not (Test-Path -LiteralPath $Repo -PathType Container)) {
    Write-Host "[BLOCKED] Repository root does not exist: $Repo"
    exit 10
}

$topLevel = Invoke-GitText -Arguments @("rev-parse", "--show-toplevel")
if ($topLevel.ExitCode -ne 0) {
    Write-Host "[BLOCKED] Not a Git repository: $Repo"
    exit 10
}

$currentBranch = (Invoke-GitText -Arguments @("branch", "--show-current")).Text
$mainHead = (Invoke-GitText -Arguments @("rev-parse", "HEAD")).Text
Write-Host "[STATE] Checkout branch: $currentBranch"
Write-Host "[STATE] HEAD:            $mainHead"

$verified = [ordered]@{}
foreach ($entry in $Branches.GetEnumerator()) {
    $actual = (Invoke-GitText -Arguments @("rev-parse", "--verify", "--quiet", ("refs/heads/" + $entry.Key))).Text
    if ([string]::IsNullOrWhiteSpace($actual)) {
        Write-Host ("[SKIP] already gone: " + $entry.Key)
        continue
    }
    if ($actual -ne $entry.Value) {
        Write-Host ("[SKIP] tip moved, not deleting: " + $entry.Key + " is " + $actual)
        continue
    }
    $verified[$entry.Key] = $entry.Value
}
Write-Host ("[PASS] branches verified at their expected tips: " + $verified.Count)

# ============================================================
# ARCHIVE
# ============================================================

Write-Phase -Name "WORK" -Message "Save every tip under refs/archive/"

$archived = New-Object System.Collections.ArrayList
foreach ($entry in $verified.GetEnumerator()) {
    $ref = "refs/archive/" + $entry.Key
    $update = Invoke-GitText -Arguments @("update-ref", $ref, $entry.Value)
    if ($update.ExitCode -ne 0) {
        Write-Host ("[BLOCKED] could not archive " + $entry.Key)
        exit 20
    }
    $check = (Invoke-GitText -Arguments @("rev-parse", "--verify", "--quiet", $ref)).Text
    if ($check -ne $entry.Value) {
        Write-Host ("[BLOCKED] archive ref mismatch for " + $entry.Key)
        exit 20
    }
    [void]$archived.Add($entry.Value)
    Write-Host ("[DONE] archived " + $entry.Key)
}

# ============================================================
# WORKTREE SAFETY
# ============================================================

Write-Phase -Name "VERIFY" -Message "Worktree contents before removal"

$toRemove = New-Object System.Collections.ArrayList
foreach ($path in $Worktrees) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        Write-Host ("[SKIP] missing: " + $path)
        continue
    }

    $head = (& git -C $path rev-parse HEAD 2>$null | Out-String).Trim()
    $leaf = Split-Path -Leaf $path

    $reachable = $false
    foreach ($tip in $archived) {
        & git -C $Repo merge-base --is-ancestor $head $tip 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $reachable = $true; break }
    }
    if (-not $reachable) {
        $extraRef = "refs/archive/worktree/" + $leaf
        & git -C $Repo update-ref $extraRef $head 2>$null | Out-Null
        Write-Host ("[DONE] archived detached commit " + $head.Substring(0, 9) + " as " + $extraRef)
    }

    $untracked = @(& git -C $path ls-files --others --exclude-standard 2>$null)
    $dirty = @(& git -C $path status --porcelain=v1 --untracked-files=all 2>$null)
    if ($untracked.Count -gt 0) {
        Write-Host ("[NOTE] " + $leaf + " has " + $untracked.Count + " untracked files that will be discarded:")
        foreach ($file in $untracked) { Write-Host ("        " + $file) }
    }
    [void]$toRemove.Add([pscustomobject]@{ Path = $path; Leaf = $leaf; Dirty = ($dirty.Count -gt 0) })
}

# ============================================================
# REMOVE WORKTREES
# ============================================================

Write-Phase -Name "WORK" -Message "Remove worktrees (this deletes their Unity Library caches)"

$removed = 0
foreach ($item in $toRemove) {
    if ($item.Dirty) {
        & git -C $Repo worktree remove --force $item.Path 2>$null | Out-Null
    }
    else {
        & git -C $Repo worktree remove $item.Path 2>$null | Out-Null
    }
    if ($LASTEXITCODE -eq 0) {
        $removed = $removed + 1
        Write-Host ("[DONE] removed worktree " + $item.Leaf)
    }
    else {
        Write-Host ("[WARN] could not remove worktree " + $item.Leaf + "; leaving it in place")
    }
}

# ============================================================
# DELETE LOCAL BRANCHES
# ============================================================

Write-Phase -Name "WORK" -Message "Delete the local branch refs"

$deleted = 0
foreach ($entry in $verified.GetEnumerator()) {
    & git -C $Repo branch -D $entry.Key 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $deleted = $deleted + 1
        Write-Host ("[DONE] deleted " + $entry.Key)
    }
    else {
        Write-Host ("[WARN] could not delete " + $entry.Key)
    }
}

# ============================================================
# FINAL REPORT
# ============================================================

Write-Phase -Name "DONE" -Message "Cleanup complete"

$leftBranches = @()
foreach ($name in $Branches.Keys) {
    $still = (Invoke-GitText -Arguments @("rev-parse", "--verify", "--quiet", ("refs/heads/" + $name))).Text
    if (-not [string]::IsNullOrWhiteSpace($still)) { $leftBranches += $name }
}
$archiveCount = @(Invoke-GitText -Arguments @("for-each-ref", "--format=%(refname)", "refs/archive") | ForEach-Object { $_.Text -split "`n" }).Count
$worktreeCount = @((Invoke-GitText -Arguments @("worktree", "list")).Text -split "`n").Count
$treeState = (Invoke-GitText -Arguments @("status", "--porcelain=v1")).Text

Write-Host "[STATE] Repository:        $Repo"
Write-Host "[STATE] HEAD:              $mainHead"
Write-Host ("[STATE] Branches deleted:  " + $deleted + " of " + $verified.Count)
Write-Host ("[STATE] Worktrees removed: " + $removed + " of " + $toRemove.Count)
Write-Host ("[STATE] Worktrees left:    " + $worktreeCount)
if ($leftBranches.Count -gt 0) {
    Write-Host ("[STATE] Branches left:     " + ($leftBranches -join ", "))
}
if ([string]::IsNullOrWhiteSpace($treeState)) {
    Write-Host "[STATE] Main worktree:     CLEAN"
}
else {
    Write-Host "[STATE] Main worktree:     NOT CLEAN"
    Write-Host $treeState
}
Write-Host "[STATE] GitHub:            untouched, nothing pushed or deleted"
Write-Host "[NEXT] Tell Claude it ran, and it will verify and record the result."
