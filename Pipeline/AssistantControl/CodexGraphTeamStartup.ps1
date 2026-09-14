<#
.SYNOPSIS
Read-only Codex graph-team startup check.
.DESCRIPTION
Runs the shared Source/controller identity check and prints the proven Codex
Sol/Luna/Spark role assignments. The worker config describes per-task execution
crews, which may use a different provider. No agents or providers are launched.
#>
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$CheckoutRoot,
    [Parameter(Mandatory = $true)][string]$WorkerConfig,
    [Parameter(Mandatory = $true)][string]$ExpectedBranch
)

$ErrorActionPreference = 'Stop'
$sharedCheck = Join-Path $PSScriptRoot 'Check-GraphTeamIdentity.ps1'
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
$identity | Write-Output
Write-Output 'Graph lead (Sol): gpt-5.6-sol, ultra; sole normal run-graph authority.'
Write-Output 'Setup (Luna): gpt-5.6-luna, medium; one delegate-safe pass.'
Write-Output 'Observer (Spark): gpt-5.3-codex-spark, high; read-only.'
Write-Output 'Verify the actual three agent sessions, model/effort, tool permissions, handoff, and live controller lock before normal run-graph.'
Write-Output 'This check does not launch Codex agents or authorize provider spending.'
