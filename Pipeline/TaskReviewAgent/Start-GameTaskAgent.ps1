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

    [string]$RunId,

    [string]$AdmissionSourceHead,

    [string]$TaskContractSha256,

    [int]$AdmissionIssueNumber,

    [string]$Model,

    [ValidateSet('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')]
    [string]$SupervisorReasoningEffort,

    [string]$ExecutionModel,

    [ValidateSet('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')]
    [string]$ExecutionReasoningEffort,

    [ValidateSet('lean', 'standard', 'full')]
    [string]$CrewProfile,

    [ValidateSet('targeted', 'task_specific', 'full_relevant')]
    [string]$ValidationProfile,

    [switch]$EnableExecutionSessionPool,

    [string]$Source,

    [ValidateRange(4, 160)]
    [int]$MaxTurns = 120,

    [ValidateRange(0, 1440)]
    [int]$HumanActionWaitMinutes = 60,

    [ValidateRange(1, 300)]
    [int]$HumanActionPollSeconds = 60
)

$ErrorActionPreference = 'Stop'
if (
    [string]::IsNullOrWhiteSpace($CrewProfile) -ne
    [string]::IsNullOrWhiteSpace($ValidationProfile)
) {
    throw 'CrewProfile and ValidationProfile must be supplied together.'
}
$NativeCommandPath = Join-Path $PSScriptRoot 'NativeCommand.ps1'
if (-not (Test-Path -LiteralPath $NativeCommandPath -PathType Leaf)) {
    throw "Native command helper is missing: $NativeCommandPath"
}
. $NativeCommandPath

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

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $CheckoutParent = Split-Path -Parent $RepositoryRoot
    $OutputRoot = Join-Path $CheckoutParent '.task-review-agent\outputs'
}
if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}
$OutputRoot = (Resolve-Path -LiteralPath $OutputRoot).Path

foreach ($CommandName in @('git', 'gh', 'python')) {
    if ($null -eq (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        if ($CommandName -eq 'gh') {
            throw 'GitHub CLI is required but is not installed. Install it with: winget install --id GitHub.cli'
        }
        throw "Required command is not installed or not on PATH: $CommandName"
    }
}

$GitHubAuth = Invoke-NscNativeCommand `
    -FilePath 'gh' `
    -ArgumentList @('auth', 'status', '--hostname', 'github.com')
if ($GitHubAuth.ExitCode -ne 0) {
    $GitHubAuth.Output | ForEach-Object { Write-Host $_ }
    throw 'GitHub CLI must be authenticated. Run: gh auth login'
}

if (
    $Mode -eq 'openai' -and
    -not [string]::IsNullOrWhiteSpace($TaskId)
) {
    $Admission = Invoke-NscNativeCommand `
        -FilePath 'python' `
        -ArgumentList @(
            'Pipeline/TaskReviewAgent/launcher_preflight.py',
            '--task-id', $TaskId,
            '--source', $Source,
            '--worker-id', $WorkerId
        )
    if ($Admission.ExitCode -ne 0) {
        $Admission.Output | ForEach-Object { Write-Host $_ }
        throw "Task $TaskId failed deterministic admission before Docker startup."
    }
}

if ($null -eq (Get-Command 'docker' -ErrorAction SilentlyContinue)) {
    throw 'Required command is not installed or not on PATH: docker'
}

$ComposeVersion = Invoke-NscNativeCommand `
    -FilePath 'docker' `
    -ArgumentList @('compose', 'version')
if ($ComposeVersion.ExitCode -ne 0) {
    $ComposeVersion.Output | ForEach-Object { Write-Host $_ }
    throw 'Docker Desktop and Docker Compose must be available.'
}

$SupervisorVolume = $null
if ($Mode -eq 'openai') {
    # Codex CLI login is already stored in a Docker volume. The supervisor uses
    # that login directly; it never requests or copies OPENAI_API_KEY.
    $VolumeList = Invoke-NscNativeCommand `
        -FilePath 'docker' `
        -ArgumentList @('volume', 'ls', '--format', '{{.Name}}')
    if ($VolumeList.ExitCode -ne 0) {
        $VolumeList.Output | ForEach-Object { Write-Host $_ }
        throw 'Unable to enumerate Docker volumes.'
    }
    $AllVolumes = @(
        $VolumeList.Output |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )

    $Candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($env:NSC_TASK_SUPERVISOR_CODEX_VOLUME)) {
        $Candidates += $env:NSC_TASK_SUPERVISOR_CODEX_VOLUME
    }
    foreach ($Preferred in @(
        'nosafecircle-m2a_codex-config',
        'nosafecircle_codex-config'
    )) {
        if ($AllVolumes -contains $Preferred) {
            $Candidates += $Preferred
        }
    }
    $Candidates += @(
        $AllVolumes |
            Where-Object { $_ -match 'codex-config$' } |
            Sort-Object
    )
    $Candidates = @($Candidates | Select-Object -Unique)

    if ($Candidates.Count -eq 0) {
        throw 'No persisted Codex CLI configuration volume was found. Authenticate Codex once through an existing Compose project.'
    }

    $SupervisorBuild = Invoke-NscNativeCommand `
        -FilePath 'docker' `
        -ArgumentList @(
            'compose', '-p', 'nosafecircle',
            'build', 'codex-supervisor'
        ) `
        -StreamOutput
    if ($SupervisorBuild.ExitCode -ne 0) {
        throw 'The codex-supervisor Docker image could not be built.'
    }

    foreach ($Candidate in $Candidates) {
        $env:NSC_TASK_SUPERVISOR_CODEX_VOLUME = $Candidate
        $LoginStatus = Invoke-NscNativeCommand `
            -FilePath 'docker' `
            -ArgumentList @(
                'compose', '-p', 'nosafecircle',
                'run', '--rm', '-T',
                'codex-supervisor',
                'codex', 'login', 'status'
            )
        if ($LoginStatus.ExitCode -eq 0) {
            $SupervisorVolume = $Candidate
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($SupervisorVolume)) {
        throw @"
Persisted Codex volumes were found, but none reported an authenticated CLI session.
Checked: $($Candidates -join ', ')
No API key is required. Re-authenticate the intended volume with Codex CLI instead.
"@
    }
    $env:NSC_TASK_SUPERVISOR_CODEX_VOLUME = $SupervisorVolume

    $ExecutionService = "$ExecutionProvider-exec"
    $ProviderVolume = "nosafecircle_$ExecutionProvider-config"
    $ProviderConfigPath = if ($ExecutionProvider -eq 'claude') {
        '/home/agent/.claude'
    }
    else {
        '/home/agent/.codex'
    }

    $ProviderVolumeCheck = Invoke-NscNativeCommand `
        -FilePath 'docker' `
        -ArgumentList @('volume', 'inspect', $ProviderVolume)
    if ($ProviderVolumeCheck.ExitCode -ne 0) {
        $ProviderVolumeCheck.Output | ForEach-Object { Write-Host $_ }
        throw "The shared ExecutionCrew provider volume is missing: $ProviderVolume"
    }

    $ExecutionOutputRoot = Join-Path $RepositoryRoot 'Pipeline\ExecutionCrew\outputs'
    if (-not (Test-Path -LiteralPath $ExecutionOutputRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $ExecutionOutputRoot -Force | Out-Null
    }
    $ProbeName = "permission-probe-$([Guid]::NewGuid().ToString('N')).txt"
    $HostProbePath = Join-Path $ExecutionOutputRoot $ProbeName
    $ProbeScript = @"
set -eu
if touch '/workspace/$ProbeName' 2>/dev/null; then
  rm -f '/workspace/$ProbeName'
  echo 'ERROR: /workspace is writable but must be read-only.' >&2
  exit 41
fi
test -d '$ProviderConfigPath'
test -r '$ProviderConfigPath'
test -w '$ProviderConfigPath'
printf 'task-review-agent-permission-ok\n' > '/execution-output/$ProbeName'
"@

    try {
        $PermissionProbe = Invoke-NscNativeCommand `
            -FilePath 'docker' `
            -ArgumentList @(
                'compose', '-p', 'nosafecircle',
                'run', '--rm', '-T',
                $ExecutionService,
                'bash', '-lc', $ProbeScript
            ) `
            -StreamOutput
        if ($PermissionProbe.ExitCode -ne 0) {
            throw "Docker permission preflight failed for $ExecutionService."
        }
        if (-not (Test-Path -LiteralPath $HostProbePath -PathType Leaf)) {
            throw 'Docker reported success but the host did not receive the ExecutionCrew output probe.'
        }
        $ProbeValue = (Get-Content -LiteralPath $HostProbePath -Raw).Trim()
        if ($ProbeValue -ne 'task-review-agent-permission-ok') {
            throw 'Docker ExecutionCrew output probe had unexpected contents.'
        }
    }
    finally {
        Remove-Item -LiteralPath $HostProbePath -Force -ErrorAction SilentlyContinue
    }
}

$Arguments = @(
    'Pipeline/TaskReviewAgent/run_pipeline_agent.py',
    '--mode', $Mode,
    '--source', $Source,
    '--worker-id', $WorkerId,
    '--execution-provider', $ExecutionProvider,
    '--max-turns', $MaxTurns.ToString(),
    '--output-root', $OutputRoot
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
if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $Arguments += @('--model', $Model)
}
if (-not [string]::IsNullOrWhiteSpace($SupervisorReasoningEffort)) {
    $Arguments += @('--supervisor-reasoning-effort', $SupervisorReasoningEffort)
}
if (-not [string]::IsNullOrWhiteSpace($ExecutionModel)) {
    $Arguments += @('--execution-model', $ExecutionModel)
}
if (-not [string]::IsNullOrWhiteSpace($ExecutionReasoningEffort)) {
    $Arguments += @('--execution-reasoning-effort', $ExecutionReasoningEffort)
}
if (-not [string]::IsNullOrWhiteSpace($CrewProfile)) {
    $Arguments += @('--crew-profile', $CrewProfile)
}
if (-not [string]::IsNullOrWhiteSpace($ValidationProfile)) {
    $Arguments += @('--validation-profile', $ValidationProfile)
}
if ($EnableExecutionSessionPool) {
    $Arguments += '--enable-execution-session-pool'
}
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    if (
        [string]::IsNullOrWhiteSpace($AdmissionSourceHead) -or
        [string]::IsNullOrWhiteSpace($TaskContractSha256)
    ) {
        throw 'Scheduler run identity requires run ID, source HEAD, and task-contract hash.'
    }
    $Arguments += @(
        '--run-id', $RunId,
        '--admission-source-head', $AdmissionSourceHead,
        '--task-contract-sha256', $TaskContractSha256
    )
    if ($AdmissionIssueNumber -gt 0) {
        $Arguments += @('--admission-issue-number', $AdmissionIssueNumber)
    }
}
elseif ($AdmissionIssueNumber -gt 0) {
    throw 'Scheduler admission Issue number requires scheduler run identity.'
}

Write-Host "Worker: $WorkerId"
if ([string]::IsNullOrWhiteSpace($TaskId)) {
    Write-Host 'Task: resume existing actionable work, otherwise start one safe fresh implementation task (retries another candidate after ordinary claim contention)'
}
else {
    Write-Host "Task: $TaskId"
}
Write-Host 'Goal supervisor: OpenAI Codex CLI in Docker (no API key)'
if ($SupervisorVolume) {
    Write-Host "Codex credential volume: $SupervisorVolume"
}
Write-Host "Execution provider: $ExecutionProvider"
Write-Host "Durable output root: $OutputRoot"
Write-Host 'Host Python UTF-8 mode: enabled'
Write-Host 'Pipeline phase: selected automatically from the durable Issue state'

$PreviousPythonUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
$AgentExitCode = 1
try {
    # Python must enter UTF-8 mode at interpreter startup. This makes every
    # text=True GitHub/Git subprocess decode deterministic on Windows instead
    # of using the machine's legacy ANSI code page.
    $env:PYTHONUTF8 = '1'
    while ($true) {
        & python @Arguments
        $AgentExitCode = $LASTEXITCODE
        if (
            $AgentExitCode -ne 0 -or
            $Mode -ne 'openai' -or
            [string]::IsNullOrWhiteSpace($TaskId) -or
            -not [string]::IsNullOrWhiteSpace($RunId) -or
            $HumanActionWaitMinutes -eq 0
        ) {
            break
        }

        $WaitArguments = @(
            'Pipeline/TaskReviewAgent/human_action_wait.py',
            '--task-id', $TaskId,
            '--source', $Source,
            '--worker-id', $WorkerId,
            '--timeout-seconds', ($HumanActionWaitMinutes * 60).ToString(),
            '--poll-seconds', $HumanActionPollSeconds.ToString()
        )
        & python @WaitArguments
        $WaitExitCode = $LASTEXITCODE
        if ($WaitExitCode -eq 0) {
            Write-Host "Validated human result observed for $TaskId; resuming in this launcher session."
            continue
        }
        if ($WaitExitCode -in @(3, 4)) {
            Write-Host "No automatic resume was performed for $TaskId."
            break
        }
        $AgentExitCode = 2
        break
    }
}
finally {
    if ($null -eq $PreviousPythonUtf8) {
        Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONUTF8 = $PreviousPythonUtf8
    }
}
if ($AgentExitCode -ne 0) {
    [Console]::Error.WriteLine("Game Task Agent stopped with exit code $AgentExitCode.")
}
exit $AgentExitCode
