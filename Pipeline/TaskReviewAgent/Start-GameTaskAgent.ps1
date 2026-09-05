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

    # Architect-managed top-level execution. A top-level explicit task runs
    # through the existing autonomous graph controller unless -DirectManual
    # selects the conservative direct worker, or the caller is the scheduler
    # itself, which is proved by a non-empty -RunId.
    [switch]$DirectManual,

    [ValidatePattern('^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$')]
    [string]$AutonomousRunId,

    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$ConfirmRepository,

    [ValidateRange(1, 10)]
    [int]$MaxWorkers = 1,

    [switch]$EnableSyntheticEvidence,

    [string]$Source,

    [ValidateRange(4, 160)]
    [int]$MaxTurns = 120,

    [ValidateRange(0, 1440)]
    [int]$HumanActionWaitMinutes = 60,

    [ValidateRange(1, 300)]
    [int]$HumanActionPollSeconds = 60,

    # Exact operator-verified argv fragment that reproduces the supervisor's
    # pinned `--sandbox danger-full-access` policy on `codex exec resume`,
    # for example: -CodexResumeSandboxArgument '-c','sandbox_mode="danger-full-access"'
    # Supplying it activates durable supervisor session pooling; omitting it
    # leaves the Codex resume gate off and every supervisor turn ephemeral.
    # It is exported as NSC_CODEX_RESUME_SANDBOX_ARGUMENT so the architect
    # controller and its scheduler-spawned workers inherit the same decision.
    [string[]]$CodexResumeSandboxArgument,

    # Explicit context window of the supervisor model. Only used to derive
    # known context utilization from the exact input token count Codex
    # reports; omitted means unknown and never retires a conversation.
    [ValidateRange(1000, 100000000)]
    [int]$SupervisorContextWindowTokens
)

$ErrorActionPreference = 'Stop'

function Test-NscCodexResumeControl {
    # The control is an allowlist: `-c`/`--config` flag and `sandbox...=value`
    # pairs only. `--sandbox` is not accepted by codex exec resume, recency
    # selectors are never exact, and any other flag would widen what the
    # resumed turn may do beyond what the pinned start had. The worker applies
    # the same rule again before it pools anything. $Source names the exact
    # channel the caller supplied the control through (the parameter or the
    # inherited environment variable) so a rejection is actionable.
    param([string[]]$Fragments, [string]$Source)
    if ($null -eq $Fragments -or $Fragments.Count -eq 0) {
        throw "$Source must name at least one exact argv fragment."
    }
    foreach ($Fragment in $Fragments) {
        if ([string]::IsNullOrWhiteSpace($Fragment) -or $Fragment -ne $Fragment.Trim()) {
            throw "$Source fragments must be non-empty and unpadded."
        }
    }
    if (($Fragments.Count % 2) -ne 0) {
        throw "$Source must be -c/--config flag and sandbox...=value pairs, for example: -CodexResumeSandboxArgument '-c','sandbox_mode=""danger-full-access""'."
    }
    for ($Index = 0; $Index -lt $Fragments.Count; $Index += 2) {
        $Flag = $Fragments[$Index]
        $Value = $Fragments[$Index + 1]
        if (@('-c', '--config') -notcontains $Flag) {
            throw "$Source may not contain $Flag; only -c/--config sandbox overrides reproduce the pinned sandbox policy through an option codex exec resume accepts."
        }
        if ($Value -notmatch '^sandbox[a-z0-9_.]*=.+$') {
            throw "$Source value '$Value' must be one sandbox...=value configuration override."
        }
    }
}

if ($PSBoundParameters.ContainsKey('CodexResumeSandboxArgument')) {
    Test-NscCodexResumeControl -Fragments $CodexResumeSandboxArgument -Source '-CodexResumeSandboxArgument'
    # -InputObject keeps a single fragment as a JSON array; piping would
    # collapse it to a bare string the worker must refuse. The control travels
    # to every child only through this environment variable: Windows PowerShell
    # 5.1 does not escape embedded quotes in native arguments, so a JSON array
    # passed on python's command line would arrive corrupted.
    $env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT = ConvertTo-Json -InputObject @($CodexResumeSandboxArgument) -Compress
}
elseif (-not [string]::IsNullOrWhiteSpace($env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT)) {
    # An inherited control is validated exactly like a supplied one; the
    # launcher never reports ACTIVE for a value the worker would refuse.
    $InheritedControl = $null
    try {
        # Windows PowerShell 5.1 note: wrapping the ConvertFrom-Json call
        # itself in @(...) can collapse a multi-element result into one
        # nested array element. Capture the parsed value to a variable
        # first, then apply @() to that variable, which reliably yields one
        # array element per JSON array entry for both one- and many-element
        # arrays.
        $ParsedInheritedControl = ConvertFrom-Json -InputObject $env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT
        $InheritedControl = @($ParsedInheritedControl)
    }
    catch {
        throw "NSC_CODEX_RESUME_SANDBOX_ARGUMENT is not a JSON array of argv strings: $($_.Exception.Message)"
    }
    foreach ($Item in $InheritedControl) {
        if ($Item -isnot [string]) {
            throw 'NSC_CODEX_RESUME_SANDBOX_ARGUMENT must be a JSON array of strings.'
        }
    }
    Test-NscCodexResumeControl -Fragments ([string[]]$InheritedControl) -Source 'NSC_CODEX_RESUME_SANDBOX_ARGUMENT'
}
if ($PSBoundParameters.ContainsKey('SupervisorContextWindowTokens')) {
    $env:NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS = $SupervisorContextWindowTokens.ToString()
}
$SupervisorPoolActivation = if ($Mode -ne 'openai') {
    'OFF (no supervisor turns run in this mode)'
}
elseif ([string]::IsNullOrWhiteSpace($env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT)) {
    'OFF (ephemeral supervisor turns; supply -CodexResumeSandboxArgument or NSC_CODEX_RESUME_SANDBOX_ARGUMENT only after live verification of codex exec resume)'
}
else {
    'ACTIVE (operator-verified Codex resume control: ' + $env:NSC_CODEX_RESUME_SANDBOX_ARGUMENT + ')'
}
if (
    [string]::IsNullOrWhiteSpace($CrewProfile) -ne
    [string]::IsNullOrWhiteSpace($ValidationProfile)
) {
    throw 'CrewProfile and ValidationProfile must be supplied together.'
}

# ---------------------------------------------------------------------------
# Top-level routing
#
# The autonomous graph controller starts its workers through this same script,
# so the two callers must be distinguished structurally rather than by
# heuristic. A scheduler-spawned worker always carries a non-empty -RunId with
# its admission source HEAD and task-contract hash; an operator launch never
# does. That single fact is what keeps delegation non-recursive.
# ---------------------------------------------------------------------------
$IsSchedulerWorker = -not [string]::IsNullOrWhiteSpace($RunId)
$ArchitectOptionNames = @(
    'AutonomousRunId',
    'ConfirmRepository',
    'MaxWorkers',
    'EnableSyntheticEvidence'
)
$SuppliedArchitectOptions = @(
    $ArchitectOptionNames |
        Where-Object { $PSBoundParameters.ContainsKey($_) }
)

if ($IsSchedulerWorker -and $DirectManual) {
    throw 'DirectManual is an operator escape hatch and must not be combined with a scheduler RunId.'
}
if ($IsSchedulerWorker -and $SuppliedArchitectOptions.Count -gt 0) {
    throw "A scheduler worker RunId cannot carry architect-managed options: $($SuppliedArchitectOptions -join ', ')."
}
if ($DirectManual -and $SuppliedArchitectOptions.Count -gt 0) {
    throw "DirectManual cannot carry architect-managed options: $($SuppliedArchitectOptions -join ', ')."
}
if ($DirectManual -and $EnableExecutionSessionPool) {
    throw 'DirectManual is ephemeral and holds no scheduler-issued pool authority; remove EnableExecutionSessionPool.'
}

$UseArchitectManaged = (
    -not $IsSchedulerWorker -and
    -not $DirectManual -and
    -not [string]::IsNullOrWhiteSpace($TaskId) -and
    $Mode -eq 'openai'
)
if (-not $UseArchitectManaged -and $SuppliedArchitectOptions.Count -gt 0) {
    throw "Architect-managed options require a top-level explicit -TaskId in openai mode: $($SuppliedArchitectOptions -join ', ')."
}
if ($UseArchitectManaged) {
    # Every one of these is resolved per task by the architect, owned by the
    # scheduler, or has no architect-managed equivalent. Silently dropping one
    # would let an operator believe a decision was honoured when it was not, so
    # the launch fails before either pipeline starts.
    $DirectOnlyOptionNames = @(
        'CrewProfile',
        'ValidationProfile',
        'Model',
        'SupervisorReasoningEffort',
        'ExecutionReasoningEffort',
        'AdmissionSourceHead',
        'TaskContractSha256',
        'AdmissionIssueNumber',
        'WorkerId',
        'OutputRoot',
        'UnityExecutable',
        'HumanActionWaitMinutes',
        'HumanActionPollSeconds'
    )
    $SuppliedDirectOnly = @(
        $DirectOnlyOptionNames |
            Where-Object { $PSBoundParameters.ContainsKey($_) }
    )
    if ($SuppliedDirectOnly.Count -gt 0) {
        throw "Architect-managed execution owns these decisions; rerun with -DirectManual to set them yourself: $($SuppliedDirectOnly -join ', ')."
    }
    if ($EnableExecutionSessionPool) {
        throw 'Architect-managed execution owns the scheduler session pools; remove EnableExecutionSessionPool.'
    }
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

# The autonomous controller runs its own completed-receipt probe before it
# touches GitHub or Docker, so the delegated path must not force a GitHub or
# Docker call ahead of that probe.
$RequiredCommandNames = if ($UseArchitectManaged) {
    @('git', 'python')
}
else {
    @('git', 'gh', 'python')
}
foreach ($CommandName in $RequiredCommandNames) {
    if ($null -eq (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        if ($CommandName -eq 'gh') {
            throw 'GitHub CLI is required but is not installed. Install it with: winget install --id GitHub.cli'
        }
        throw "Required command is not installed or not on PATH: $CommandName"
    }
}

if ($UseArchitectManaged) {
    # Delegate exactly once to the existing autonomous graph controller. This
    # launcher deliberately implements none of the architect difficulty scoring,
    # execution-route or rigor resolution, architect/ExecutionCrew session
    # pooling, Issue-state wake-up, continuous worker supervision, or
    # graph-complete receipt semantics. Start-AutonomousGraphRun.ps1 and
    # run_autonomous_graph.py already own all of it.
    $ControllerLauncher = Join-Path $PSScriptRoot 'Start-AutonomousGraphRun.ps1'
    if (-not (Test-Path -LiteralPath $ControllerLauncher -PathType Leaf)) {
        throw "Autonomous graph launcher is missing: $ControllerLauncher"
    }

    $ResolvedRepository = $ConfirmRepository
    if ([string]::IsNullOrWhiteSpace($ResolvedRepository)) {
        # The controller requires an explicit repository assertion. Reuse the one
        # committed authority rather than parsing a Git remote here, and receive
        # the answer through a file so a combined stdout/stderr stream is never
        # treated as machine data.
        $RepositoryFile = Join-Path `
            ([System.IO.Path]::GetTempPath()) `
            ("nsc-issue-repository-" + [Guid]::NewGuid().ToString('N') + ".txt")
        try {
            $Resolve = Invoke-NscNativeCommand `
                -FilePath 'python' `
                -ArgumentList @(
                    'Pipeline/TaskReviewAgent/resolve_issue_repository.py',
                    '--source', $Source,
                    '--output', $RepositoryFile
                )
            if ($Resolve.ExitCode -ne 0) {
                $Resolve.Output | ForEach-Object { Write-Host $_ }
                throw 'The source checkout origin could not be resolved to a GitHub repository.'
            }
            if (-not (Test-Path -LiteralPath $RepositoryFile -PathType Leaf)) {
                throw 'The repository resolver reported success but wrote no result.'
            }
            $ResolvedRepository = (
                Get-Content -LiteralPath $RepositoryFile -Raw -Encoding UTF8
            ).Trim()
        }
        finally {
            Remove-Item -LiteralPath $RepositoryFile -Force -ErrorAction SilentlyContinue
        }
    }
    if ([string]::IsNullOrWhiteSpace($ResolvedRepository)) {
        throw 'A repository assertion is required for architect-managed execution.'
    }

    $ControllerRunId = $AutonomousRunId
    if ([string]::IsNullOrWhiteSpace($ControllerRunId)) {
        # The project's established run-identity shape -- lower-case task ID plus
        # a compact UTC stamp -- with a short discriminator so two launches in
        # the same second cannot silently adopt each other's durable run.
        $Now = [DateTime]::UtcNow
        $Invariant = [System.Globalization.CultureInfo]::InvariantCulture
        $ControllerRunId = (
            $TaskId.ToLowerInvariant() + '-' +
            $Now.ToString('yyyyMMdd', $Invariant) + 't' +
            $Now.ToString('HHmmss', $Invariant) + 'z-' +
            [Guid]::NewGuid().ToString('N').Substring(0, 6)
        )
    }

    $ControllerArguments = @(
        '-RunId', $ControllerRunId,
        '-ConfirmRepository', $ResolvedRepository,
        '-TargetTaskId', $TaskId,
        '-MaxWorkers', $MaxWorkers.ToString(),
        '-Source', $Source
    )
    if ($PSBoundParameters.ContainsKey('ExecutionProvider')) {
        $ControllerArguments += @('-ExecutionProvider', $ExecutionProvider)
    }
    if ($PSBoundParameters.ContainsKey('ExecutionModel')) {
        $ControllerArguments += @('-Model', $ExecutionModel)
    }
    if ($PSBoundParameters.ContainsKey('MaxTurns')) {
        $ControllerArguments += @('-MaxTurns', $MaxTurns.ToString())
    }
    if ($PSBoundParameters.ContainsKey('CheckoutRoot')) {
        $ControllerArguments += @('-CheckoutRoot', $CheckoutRoot)
    }
    if (
        $PSBoundParameters.ContainsKey('EnableSyntheticEvidence') -and
        $EnableSyntheticEvidence.IsPresent
    ) {
        $ControllerArguments += '-EnableSyntheticEvidence'
    }

    Write-Host 'Execution mode: architect-managed autonomous graph run'
    Write-Host "Target task: $TaskId plus its committed decomposition-children closure"
    Write-Host "Autonomous run ID: $ControllerRunId"
    Write-Host "Repository: $ResolvedRepository"
    Write-Host "Maximum worker capacity: $MaxWorkers"
    Write-Host 'Rigor, validation, crew sizing, provider and model: resolved per task by the Software Architect'
    Write-Host "Supervisor session pool: warm Codex resume $SupervisorPoolActivation"
    Write-Host "Resume this exact run with: -TaskId $TaskId -AutonomousRunId $ControllerRunId"

    $PreviousPythonUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')
    $ControllerExitCode = 1
    try {
        $env:PYTHONUTF8 = '1'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass `
            -File $ControllerLauncher @ControllerArguments
        $ControllerExitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $PreviousPythonUtf8) {
            Remove-Item Env:PYTHONUTF8 -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONUTF8 = $PreviousPythonUtf8
        }
    }
    if ($ControllerExitCode -ne 0) {
        [Console]::Error.WriteLine(
            "Architect-managed run $($ControllerRunId) stopped with exit code $ControllerExitCode."
        )
    }
    exit $ControllerExitCode
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
# The resume control is deliberately NOT forwarded as a native argument: the
# worker reads NSC_CODEX_RESUME_SANDBOX_ARGUMENT, which this process exported
# or inherited and validated above.
if (-not [string]::IsNullOrWhiteSpace($env:NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS)) {
    $Arguments += @('--supervisor-context-window-tokens', $env:NSC_TASK_SUPERVISOR_CONTEXT_WINDOW_TOKENS)
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
Write-Host "Supervisor session pool: warm Codex resume $SupervisorPoolActivation"
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
