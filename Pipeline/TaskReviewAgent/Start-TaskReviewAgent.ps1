[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^NSC-[0-9]{3}$')]
    [string]$TaskId,

    [ValidateSet('scripted', 'openai-fake')]
    [string]$Mode = 'scripted',

    [string]$Model,

    [ValidateRange(4, 100)]
    [int]$MaxTurns = 24
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepositoryRoot

if ($Mode -eq 'openai-fake') {
    if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        throw 'OPENAI_API_KEY is required for -Mode openai-fake.'
    }

    & python -c "import agents"
    if ($LASTEXITCODE -ne 0) {
        throw 'OpenAI Agents SDK is missing. Run: python -m pip install -r Pipeline/TaskReviewAgent/requirements.txt'
    }
}

$Arguments = @(
    'Pipeline/TaskReviewAgent/run_agent.py',
    '--task-id', $TaskId,
    '--mode', $Mode,
    '--max-turns', $MaxTurns.ToString()
)

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $Arguments += @('--model', $Model)
}

& python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "TaskReviewAgent stopped with exit code $LASTEXITCODE."
}
