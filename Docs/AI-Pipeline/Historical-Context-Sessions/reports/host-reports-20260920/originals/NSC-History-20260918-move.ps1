<#
.SYNOPSIS
    Quarantines old C:\nsc* directories into C:\NSC-History-20260918. Idempotent - safe to
    re-run; it skips anything already moved and never overwrites an existing destination.

.DESCRIPTION
    Wrote this as the Cleanup Agent's brief deliverable (see
    C:\nscrev\reports\cleanup-quarantine-plan-20260918.md for the full report).

    NOTE ON CURRENT STATE (2026-09-18): by the time this script was finished, the actual move
    had already been carried out directly against the machine (not by this agent - this agent
    only reads and writes scripts/reports, never moves or deletes). A near-identical script,
    C:\NSC-History-20260918\MOVE-TO-HISTORY.ps1, already exists there and its MANIFEST.json
    already accounts for all 45 directories. Because of that, running THIS script right now
    should find nothing left to move (everything already has a destination folder) and do
    nothing except print that. Its purpose is: (a) the record of exactly what would have been
    moved, matching the brief, and (b) a working, idempotent tool for any *future* nsc* stragglers
    that show up later (this one adds the README.md / MANIFEST.md creation step that the folder's
    existing copy is missing).

    DRY RUN BY DEFAULT. Nothing moves until you pass -Apply.

    THE TRAP THIS GUARDS AGAINST:
    Windows path matching is case-insensitive, so the pattern 'nsc*' matches C:\NSC - the entire
    workspace - and it matches this history folder too. Both are excluded by exact name below,
    and the script refuses to run if either is ever in the move set.

.PARAMETER Apply
    Actually move. Without it you get a report and nothing changes.

.PARAMETER WithSize
    Measure each directory's size with Get-ChildItem -Recurse. Accurate but slow - several of
    these directories contain nested Unity clones with Library/ folders (hundreds of thousands
    of small files). Off by default so a dry run stays quick.

.EXAMPLE
    .\NSC-History-20260918-move.ps1
    .\NSC-History-20260918-move.ps1 -WithSize
    .\NSC-History-20260918-move.ps1 -Apply
#>

[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$WithSize
)

$ErrorActionPreference = 'Stop'

$HistoryRoot = 'C:\NSC-History-20260918'
$SourceRoot  = 'C:\'
$Pattern     = 'nsc*'

# Never moved. Compared case-insensitively against the full path (Windows paths already are).
$Excluded = @(
    'C:\NSC',                    # the workspace itself - matches 'nsc*' on Windows
    'C:\nscrev',                 # LIVE: review clones, all six tool folders, reports,
                                  #       and any open fix branches - never quarantine this
    'C:\NSC-History-20260918'    # this folder - also matches 'nsc*'
)

function Write-Head($text) { Write-Host ''; Write-Host $text -ForegroundColor Cyan }

Write-Head "Quarantine move -> $HistoryRoot"
if (-not $Apply) {
    Write-Host 'DRY RUN. Nothing will be moved. Re-run with -Apply to act.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- guards, re-checked at run time
if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "REFUSING TO RUN: source root '$SourceRoot' not found."
}
$sourceVolume = [System.IO.Path]::GetPathRoot($SourceRoot)
$destVolumeCheckPath = if (Test-Path -LiteralPath $HistoryRoot) { $HistoryRoot } else { Split-Path $HistoryRoot -Parent }
$destVolume = [System.IO.Path]::GetPathRoot($destVolumeCheckPath)
if ($sourceVolume -ne $destVolume) {
    throw "REFUSING TO RUN: destination '$HistoryRoot' is not on the same volume as '$SourceRoot' (would copy, not rename)."
}

# ---------------------------------------------------------------- collect
$candidates =
    Get-ChildItem -LiteralPath $SourceRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like $Pattern } |
    Where-Object { $Excluded -notcontains $_.FullName } |
    Sort-Object Name

# Fail closed: if an exclusion somehow survived the filter, stop rather than move it.
foreach ($ex in $Excluded) {
    if ($candidates.FullName -contains $ex) {
        throw "REFUSING TO RUN: excluded path '$ex' is in the move set. Aborting without changes."
    }
}

if (-not $candidates) {
    Write-Host 'Nothing to move (no C:\nsc* directories found outside the exclusions).' -ForegroundColor Green
    return
}

# ---------------------------------------------------------------- report
$rows = @()
foreach ($d in $candidates) {

    $type = 'plain-dir'
    if     (Test-Path -LiteralPath (Join-Path $d.FullName '.git') -PathType Container) { $type = 'clone' }
    elseif (Test-Path -LiteralPath (Join-Path $d.FullName '.git') -PathType Leaf)      { $type = 'worktree' }

    $branch = ''; $head = ''; $dirty = ''
    if ($type -ne 'plain-dir') {
        $branch = (& git -C $d.FullName rev-parse --abbrev-ref HEAD 2>$null)
        $head   = (& git -C $d.FullName rev-parse --short HEAD     2>$null)
        $st     = (& git -C $d.FullName status --porcelain          2>$null)
        $dirty  = if ($st) { "$(($st | Measure-Object).Count) changed" } else { 'clean' }
    }

    $sizeMB = ''
    if ($WithSize) {
        try {
            $bytes = (Get-ChildItem -LiteralPath $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
                      Measure-Object -Property Length -Sum).Sum
            $sizeMB = [math]::Round(($bytes / 1MB), 0)
        } catch { $sizeMB = 'n/a' }
    }

    $rows += [pscustomobject]@{
        Name = $d.Name; Type = $type; Branch = $branch; Head = $head
        State = $dirty; SizeMB = $sizeMB; Source = $d.FullName
        Dest = (Join-Path $HistoryRoot $d.Name)
    }
}

$rows | Format-Table Name, Type, Branch, Head, State, SizeMB -AutoSize | Out-Host
Write-Host ("{0} directories selected." -f $rows.Count) -ForegroundColor Cyan
if ($WithSize) {
    $tot = ($rows | Where-Object { $_.SizeMB -is [double] -or $_.SizeMB -is [int] } |
            Measure-Object -Property SizeMB -Sum).Sum
    Write-Host ("Total: {0:N0} MB" -f $tot) -ForegroundColor Cyan
}

if (-not $Apply) {
    Write-Host ''
    Write-Host 'Dry run complete. Nothing was moved.' -ForegroundColor Yellow
    return
}

# ---------------------------------------------------------------- move
if (-not (Test-Path -LiteralPath $HistoryRoot)) {
    New-Item -ItemType Directory -Path $HistoryRoot | Out-Null
}

# README.md and RESTORE.ps1: create once, never overwrite (this history folder may already
# have hand-maintained copies from an earlier run of this or an equivalent script).
$readmePath = Join-Path $HistoryRoot 'README.md'
if (-not (Test-Path -LiteralPath $readmePath)) {
    $readmeLines = @(
        '# C:\NSC-History-20260918 - read this before you browse',
        '',
        '## The one rule',
        '',
        '**This folder is a waiting room, never a home.** If you open something in here and',
        'find it is worth keeping, take it out - do not copy it, do not leave a note and walk',
        'away. Run:',
        '',
        '    C:\NSC-History-20260918\RESTORE.ps1 -Name <folder> -Reason "<why>" -Apply',
        '',
        'That moves the folder back to where it came from and logs the restore to RESTORES.md.',
        '',
        '## Why the rule matters',
        '',
        'On the review date, whatever is still sitting in here can be deleted without an audit,',
        'because under this rule anything still here was never asked for - an empty',
        'RESTORES.md is the proof.',
        '',
        '## What is in here',
        '',
        ('- Created: ' + (Get-Date -Format 'yyyy-MM-dd')),
        '- MANIFEST.json / MANIFEST.md - every folder''s source, destination, git type,',
        '  branch, head, dirty state and size at move time.',
        '- RESTORE.ps1 - the only sanctioned way to take something back out.',
        '- This move script - idempotent and safe to re-run for any later stragglers.'
    )
    $readmeLines -join "`r`n" | Set-Content -LiteralPath $readmePath -Encoding utf8
    Write-Host "wrote $readmePath" -ForegroundColor Green
}

$restorePath = Join-Path $HistoryRoot 'RESTORE.ps1'
if (-not (Test-Path -LiteralPath $restorePath)) {
    @'
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [string]$Reason,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$HistoryRoot  = $PSScriptRoot
$manifestPath = Join-Path $HistoryRoot 'MANIFEST.json'
$restoresPath = Join-Path $HistoryRoot 'RESTORES.md'
$source = Join-Path $HistoryRoot $Name
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Not found in the history folder: $Name" }
$dest = "C:\$Name"
$entry = $null
if (Test-Path -LiteralPath $manifestPath) {
    $entry = (Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json) | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($entry -and $entry.Source) { $dest = $entry.Source }
}
Write-Host "Restore: $Name  from: $source  to: $dest"
if (Test-Path -LiteralPath $dest) { throw "Destination already exists, refusing to overwrite: $dest" }
if (-not $Apply) { Write-Host 'DRY RUN. Nothing moved. Re-run with -Reason "..." -Apply to restore.' -ForegroundColor Yellow; return }
if ([string]::IsNullOrWhiteSpace($Reason)) { throw 'A -Reason is required when restoring.' }
Move-Item -LiteralPath $source -Destination $dest -ErrorAction Stop
Write-Host "restored -> $dest" -ForegroundColor Green
if (-not (Test-Path -LiteralPath $restoresPath)) {
    @('# Restores from this history folder', '', 'Anything listed here was found valuable and taken back out.', '') | Set-Content -LiteralPath $restoresPath -Encoding utf8
}
$stamp = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
Add-Content -LiteralPath $restoresPath -Encoding utf8 -Value ('- **' + $stamp + '** -- ' + $Name + ' restored to ' + $dest + ' -- ' + $Reason)
Write-Host "logged in $restoresPath" -ForegroundColor Green
'@ | Set-Content -LiteralPath $restorePath -Encoding utf8
    Write-Host "wrote $restorePath" -ForegroundColor Green
}

$manifestPath = Join-Path $HistoryRoot 'MANIFEST.json'
$manifest = @()
if (Test-Path -LiteralPath $manifestPath) {
    $existing = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($existing) { $manifest = @($existing) }
}

$movedCount = 0
foreach ($r in $rows) {

    if (-not (Test-Path -LiteralPath $r.Source)) {
        Write-Host "SKIP (gone since scan): $($r.Name)" -ForegroundColor DarkYellow; continue
    }
    if (Test-Path -LiteralPath $r.Dest) {
        Write-Host "SKIP (destination exists): $($r.Name)" -ForegroundColor DarkYellow; continue
    }
    if ([System.IO.Path]::GetPathRoot($r.Source) -ne [System.IO.Path]::GetPathRoot($HistoryRoot)) {
        Write-Host "SKIP (cross-volume, would copy): $($r.Name)" -ForegroundColor Red; continue
    }

    try {
        Move-Item -LiteralPath $r.Source -Destination $r.Dest -ErrorAction Stop
        $movedCount++
        Write-Host "moved  $($r.Name)" -ForegroundColor Green

        $manifest += [pscustomobject]@{
            Name = $r.Name; Source = $r.Source; Dest = $r.Dest; Type = $r.Type
            Branch = $r.Branch; Head = $r.Head; State = $r.State; SizeMB = $r.SizeMB
            MovedUtc = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
        }
        # written after every move, so an interrupted run still leaves a usable record
        $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    }
    catch {
        Write-Host "FAILED $($r.Name): $($_.Exception.Message)" -ForegroundColor Red
        Write-Host '  (if this is a locked-file / access-rights error under a Unity Library folder,' -ForegroundColor DarkYellow
        Write-Host '   close anything reading that folder and re-run - this script is safe to re-run)' -ForegroundColor DarkYellow
    }
}

Write-Host ''
Write-Host ("Moved {0} of {1}. Manifest: {2}" -f $movedCount, $rows.Count, $manifestPath) -ForegroundColor Cyan

# nscaudit_main is a worktree of nscaudit; its gitdir pointer is absolute and breaks on move.
if ($manifest.Name -contains 'nscaudit' -and $manifest.Name -contains 'nscaudit_main') {
    Write-Host ''
    Write-Host 'NOTE: nscaudit_main is a worktree of nscaudit and both moved, so its link is broken.' -ForegroundColor DarkYellow
    Write-Host ('      If you ever restore them, run:  git -C ' + $HistoryRoot + '\nscaudit worktree repair') -ForegroundColor DarkYellow
}

# Refresh MANIFEST.md whenever the manifest changed.
if ($movedCount -gt 0) {
    $mdPath = Join-Path $HistoryRoot 'MANIFEST.md'
    $mdLines = New-Object System.Collections.Generic.List[string]
    $mdLines.Add('# MANIFEST.md - human-readable index of ' + $HistoryRoot)
    $mdLines.Add('')
    $mdLines.Add(($manifest.Count).ToString() + ' directories quarantined here. Source of truth is MANIFEST.json.')
    $mdLines.Add('')
    $mdLines.Add('| Name | Type | Branch | Head | State | Moved (UTC) |')
    $mdLines.Add('|---|---|---|---|---|---|')
    foreach ($e in ($manifest | Sort-Object Name)) {
        $mdLines.Add('| ' + $e.Name + ' | ' + $e.Type + ' | ' + $e.Branch + ' | ' + $e.Head + ' | ' + $e.State + ' | ' + $e.MovedUtc + ' |')
    }
    ($mdLines -join "`r`n") | Set-Content -LiteralPath $mdPath -Encoding utf8
    Write-Host "refreshed $mdPath" -ForegroundColor Green
}
