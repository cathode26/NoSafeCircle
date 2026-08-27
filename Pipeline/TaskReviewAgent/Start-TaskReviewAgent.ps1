[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^NSC-[0-9]{3}$')]
    [string]$TaskId,

    [ValidateSet('scripted', 'openai-fake', 'observe-real', 'openai-observe-real')]
    [string]$Mode = 'scripted',

    [string]$Model,

    [string]$Source,

    [ValidateRange(4, 100)]
    [int]$MaxTurns = 24
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepositoryRoot

if ($Mode -like 'openai-*') {
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        throw "OPENAI_API_KEY is required for -Mode $Mode."
    }

    & python -c "import agents"
    if ($LASTEXITCODE -ne 0) {
        throw 'OpenAI Agents SDK is missing. Run: python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt'
    }
}

if ([string]::IsNullOrWhiteSpace($Source)) {
    $Source = $RepositoryRoot
}
else {
    $Source = (Resolve-Path $Source).Path
}

$Arguments = @(
    'Pipeline/TaskReviewAgent/run_agent.py',
    '--task-id', $TaskId,
    '--mode', $Mode,
    '--source', $Source,
    '--max-turns', $MaxTurns.ToString()
)

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $Arguments += @('--model', $Model)
}

& python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "TaskReviewAgent stopped with exit code $LASTEXITCODE."
}
