[CmdletBinding()]
param(
    [ValidatePattern('^NSC-[0-9]{3}$')]
    [string]$TaskId,

    [ValidateSet('claude', 'codex')]
    [string]$ExecutionProvider = 'claude',

    [ValidateSet('openai', 'observe')]
    [string]$Mode = 'openai',

    [string]$WorkerId,

    [string]$CheckoutRoot,

    [string]$UnityExecutable,

    [string]$OutputRoot,

    [string]$Model,

    [string]$Source,

    [ValidateRange(12, 160)]
    [int]$MaxTurns = 120
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepositoryRoot

if ([string]::IsNullOrWhiteSpace($Source)) {
    $Source = $RepositoryRoot
}
else {
    $Source = (Resolve-Path $Source).Path
}

if ([string]::IsNullOrWhiteSpace($WorkerId)) {
    $machine = ([Environment]::MachineName.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
    $WorkerId = "task-review-agent-$machine-$([Guid]::NewGuid().ToString('N').Substring(0, 10))"
}

& git --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Git is required.'
}

& gh auth status --hostname github.com | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'GitHub CLI must be authenticated. Run: gh auth login'
}

& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop and Docker Compose must be available.'
}

if ($Mode -eq 'openai') {
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        throw 'OPENAI_API_KEY is required for the goal-oriented OpenAI supervisor.'
    }
    & python -c "import agents"
    if ($LASTEXITCODE -ne 0) {
        throw 'OpenAI Agents SDK is missing. Run: python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt'
    }
}

$Arguments = @(
    'Pipeline/TaskReviewAgent/run_pipeline_agent.py',
    '--mode', $Mode,
    '--source', $Source,
    '--worker-id', $WorkerId,
    '--execution-provider', $ExecutionProvider,
    '--max-turns', $MaxTurns.ToString()
)

if (-not [string]::IsNullOrWhiteSpace($TaskId)) {
    $Arguments += @('--task-id', $TaskId)
}
if (-not [string]::IsNullOrWhiteSpace($CheckoutRoot)) {
    $Arguments += @('--checkout-root', $CheckoutRoot)
}
if (-not [string]::IsNullOrWhiteSpace($UnityExecutable)) {
    $UnityExecutable = (Resolve-Path -LiteralPath $UnityExecutable).Path
    $Arguments += @('--unity-executable', $UnityExecutable)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    }
    $OutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
    $Arguments += @('--output-root', $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $Arguments += @('--model', $Model)
}

Write-Host "Worker: $WorkerId"
if ([string]::IsNullOrWhiteSpace($TaskId)) {
    Write-Host 'Task: resume first validated agent-ready Issue'
}
else {
    Write-Host "Task: $TaskId"
}
Write-Host "Execution provider: $ExecutionProvider"
Write-Host 'Pipeline phase: selected automatically from the durable Issue state'

& python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Game Task Agent stopped with exit code $LASTEXITCODE."
}
