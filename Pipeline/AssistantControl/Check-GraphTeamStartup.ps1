<#
.SYNOPSIS
Read-only identity check before the Sol/Luna/Spark graph-management startup.
.DESCRIPTION
Checks the exact Source, checkout root, worker config, and recorded controller
owner. It does not start agents, mutate graph state, authorize provider spend,
or prove that no controller process owns the lock. Sol must inspect that identity.
#>
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$CheckoutRoot,
    [Parameter(Mandatory = $true)][string]$WorkerConfig,
    [Parameter(Mandatory = $true)][string]$ExpectedBranch
)

$ErrorActionPreference = 'Stop'

function Require-Directory([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label directory is missing: $Path"
    }
    return [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

$sourcePath = Require-Directory $Source 'Source'
$checkoutPath = Require-Directory $CheckoutRoot 'Checkout root'
if ($checkoutPath.Equals($sourcePath, [StringComparison]::OrdinalIgnoreCase) -or
    $checkoutPath.StartsWith($sourcePath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Checkout root must be outside Source.'
}
if (-not (Test-Path -LiteralPath $WorkerConfig -PathType Leaf)) {
    throw "Worker config is missing: $WorkerConfig"
}
$workerPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorkerConfig).Path)

$top = & git -C $sourcePath rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0 -or -not $top) { throw 'Could not identify Source Git root.' }
$topPath = [IO.Path]::GetFullPath($top.Trim())
if (-not $topPath.Equals($sourcePath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Source is not the Git root: $sourcePath (root: $topPath)"
}
$branch = & git -C $sourcePath branch --show-current 2>$null
if ($LASTEXITCODE -ne 0 -or $branch.Trim() -ne $ExpectedBranch) {
    throw "Source branch differs from expected '$ExpectedBranch': '$branch'"
}
$head = & git -C $sourcePath rev-parse HEAD 2>$null
if ($LASTEXITCODE -ne 0 -or $head.Trim() -notmatch '^[0-9a-f]{40}$') {
    throw 'Could not identify exact Source HEAD.'
}
$edits = @(& git -C $sourcePath status --porcelain=v1 2>$null)
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Source edits.' }
if ($edits.Count -gt 0) {
    throw ("Source has local edits; inspect them before graph startup:`n" + ($edits -join "`n"))
}

try {
    $config = Get-Content -LiteralPath $workerPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    throw "Worker config is not valid JSON: $workerPath"
}
if ($null -eq $config -or $config -isnot [pscustomobject]) {
    throw "Worker config must be a JSON object: $workerPath"
}
$configHash = (Get-FileHash -LiteralPath $workerPath -Algorithm SHA256).Hash.ToLowerInvariant()

$ownerPath = Join-Path (Join-Path $checkoutPath '.assistant-control') 'graph-controller-owner.json'
$ownerStatus = 'no owner record'
if (Test-Path -LiteralPath $ownerPath -PathType Leaf) {
    try {
        $owner = Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $ownerStatus = [string]$owner.status
    } catch {
        throw "Controller owner record is unreadable: $ownerPath"
    }
    if ($ownerStatus -ne 'controller_released') {
        throw "Controller owner is not recorded released ($ownerStatus): $ownerPath"
    }
}

Write-Output "Source: $sourcePath"
Write-Output "Branch: $branch"
Write-Output "HEAD: $head"
Write-Output "Checkout root: $checkoutPath"
Write-Output "Worker config: $workerPath"
Write-Output "Worker config SHA256: $configHash"
Write-Output "Recorded owner: $ownerStatus"
Write-Output 'Identity check passed. Sol must still verify live controller/lock and current task readiness.'
Write-Output 'Then follow Docs/AI-Pipeline/GRAPH_TEAM_STARTUP.md; this script launches no agents or providers.'
