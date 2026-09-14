<#
.SYNOPSIS
Read-only Claude-specific check before the three-role graph startup.
.DESCRIPTION
Runs the shared Source/controller identity check, verifies the selected
implementation worker config is Claude-only, and checks the local Claude Code
CLI. It does not create Claude sessions, invoke a model, or start the graph.
#>
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$CheckoutRoot,
    [Parameter(Mandatory = $true)][string]$WorkerConfig,
    [Parameter(Mandatory = $true)][string]$ExpectedBranch
)

$ErrorActionPreference = 'Stop'
$sharedCheck = Join-Path $PSScriptRoot 'Check-GraphTeamStartup.ps1'
if (-not (Test-Path -LiteralPath $sharedCheck -PathType Leaf)) {
    throw "Shared startup check is missing: $sharedCheck"
}

$checkArgs = @{
    Source = $Source
    CheckoutRoot = $CheckoutRoot
    WorkerConfig = $WorkerConfig
    ExpectedBranch = $ExpectedBranch
}
$identity = @(& $sharedCheck @checkArgs)

$workerPath = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $WorkerConfig).Path)
$config = Get-Content -LiteralPath $workerPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$config.provider -ne 'claude') {
    throw "Worker config provider must be 'claude': $workerPath"
}
if ([string]$config.execution_model -notmatch '^claude-[a-z0-9-]+$') {
    throw "Worker config must select an explicit Claude model: $workerPath"
}
$allowlist = @($config.provider_allowlist)
if ($allowlist.Count -ne 1 -or [string]$allowlist[0] -ne 'claude') {
    throw "Worker config provider_allowlist must contain only 'claude': $workerPath"
}

$claudeCommand = Get-Command claude -ErrorAction SilentlyContinue
if ($null -eq $claudeCommand) { throw 'Claude Code CLI is not on PATH.' }
$cliVersion = & claude --version 2>$null
if ($LASTEXITCODE -ne 0 -or -not $cliVersion) {
    throw 'Claude Code CLI did not return a version.'
}

$identity | Write-Output
Write-Output "Claude Code CLI: $($cliVersion.Trim())"
Write-Output "Claude implementation model: $($config.execution_model)"
Write-Output 'Graph lead (Sol equivalent): Claude Opus 5, xhigh; sole normal run-graph authority.'
Write-Output 'Setup (Luna equivalent): Claude Sonnet 5, medium; one delegate-safe pass.'
Write-Output 'Observer (Spark equivalent): Claude Haiku 4.5, medium; read-only.'
Write-Output 'Verify the actual three session models, efforts, tool permissions, handoff, and live controller lock before normal run-graph.'
Write-Output 'This check does not authenticate Claude, test model availability, or authorize provider spending.'
