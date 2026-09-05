[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$')]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$ConfirmRepository,

    [ValidatePattern('^NSC-[0-9]{3,}$')]
    [string[]]$TargetTaskId,

    [ValidatePattern('^NSC-[0-9]{3,}$')]
    [string[]]$ExcludeTaskId,

    [ValidateRange(0, 10)]
    [int]$MaxWorkers = 0,

    [ValidateSet('claude', 'codex')]
    [string]$ExecutionProvider,

    [ValidateSet('claude', 'codex')]
    [string]$ArchitectProvider,

    [string]$Model,

    [string]$ArchitectModel,

    [ValidateRange(1, 160)]
    [int]$MaxTurns,

    [ValidateRange(1, 160)]
    [int]$ArchitectMaxTurns,

    [ValidateRange(1, 1000)]
    [int]$ArchitectMaxInvocationsPerPoll,

    [ValidateRange(1, 300)]
    [int]$FallbackSeconds,

    [switch]$EnableSyntheticEvidence,

    [string]$CheckoutRoot,

    [string]$Source
)

$ErrorActionPreference = 'Stop'
$NativeCommandPath = Join-Path $PSScriptRoot 'NativeCommand.ps1'
if (-not (Test-Path -LiteralPath $NativeCommandPath -PathType Leaf)) {
    throw "Native command helper is missing: $NativeCommandPath"
}
. $NativeCommandPath

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $RepositoryRoot
$ResolvedSource = if ([string]::IsNullOrWhiteSpace($Source)) {
    $RepositoryRoot
}
else {
    (Resolve-Path -LiteralPath $Source).Path
}

foreach ($CommandName in @('git', 'python')) {
    if ($null -eq (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Required command is not installed or not on PATH: $CommandName"
    }
}

$Arguments = @(
    'Pipeline/TaskReviewAgent/run_autonomous_graph.py',
    '--source', $ResolvedSource,
    '--run-id', $RunId,
    '--confirm-repository', $ConfirmRepository
)
foreach ($TaskId in @($TargetTaskId)) {
    if ([string]::IsNullOrWhiteSpace($TaskId)) {
        continue
    }
    $Arguments += @('--target-task-id', $TaskId)
}
foreach ($TaskId in @($ExcludeTaskId)) {
    if ([string]::IsNullOrWhiteSpace($TaskId)) {
        continue
    }
    $Arguments += @('--exclude-task-id', $TaskId)
}
if ($PSBoundParameters.ContainsKey('MaxWorkers') -and $MaxWorkers -gt 0) {
    $Arguments += @('--max-workers', $MaxWorkers.ToString())
}
if ($PSBoundParameters.ContainsKey('ExecutionProvider')) {
    $Arguments += @('--execution-provider', $ExecutionProvider)
}
if ($PSBoundParameters.ContainsKey('ArchitectProvider')) {
    $Arguments += @('--architect-provider', $ArchitectProvider)
}
if ($PSBoundParameters.ContainsKey('Model')) {
    $Arguments += @('--model', $Model)
}
if ($PSBoundParameters.ContainsKey('ArchitectModel')) {
    $Arguments += @('--architect-model', $ArchitectModel)
}
if ($PSBoundParameters.ContainsKey('MaxTurns')) {
    $Arguments += @('--max-turns', $MaxTurns.ToString())
}
if ($PSBoundParameters.ContainsKey('ArchitectMaxTurns')) {
    $Arguments += @('--architect-max-turns', $ArchitectMaxTurns.ToString())
}
if ($PSBoundParameters.ContainsKey('ArchitectMaxInvocationsPerPoll')) {
    $Arguments += @(
        '--architect-max-invocations-per-poll',
        $ArchitectMaxInvocationsPerPoll.ToString()
    )
}
if ($PSBoundParameters.ContainsKey('FallbackSeconds')) {
    $Arguments += @('--fallback-seconds', $FallbackSeconds.ToString())
}
if ($PSBoundParameters.ContainsKey('CheckoutRoot')) {
    $Arguments += @('--checkout-root', $CheckoutRoot)
}
if ($PSBoundParameters.ContainsKey('EnableSyntheticEvidence')) {
    if ($EnableSyntheticEvidence) {
        $Arguments += '--enable-synthetic-evidence'
    }
    else {
        $Arguments += '--disable-synthetic-evidence'
    }
}
$CompletionProbeArguments = @($Arguments) + '--completion-probe'
$CompletionProbe = Invoke-NscNativeCommand `
    -FilePath 'python' `
    -ArgumentList $CompletionProbeArguments `
    -StreamOutput
if ($CompletionProbe.ExitCode -eq 0) {
    exit 0
}
if ($CompletionProbe.ExitCode -ne 10) {
    exit $CompletionProbe.ExitCode
}

foreach ($CommandName in @('gh', 'docker')) {
    if ($null -eq (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
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

$ComposeVersion = Invoke-NscNativeCommand `
    -FilePath 'docker' `
    -ArgumentList @('compose', 'version')
if ($ComposeVersion.ExitCode -ne 0) {
    $ComposeVersion.Output | ForEach-Object { Write-Host $_ }
    throw 'Docker Desktop and Docker Compose must be available.'
}

$RequiredProviderNames = @()
if ($PSBoundParameters.ContainsKey('ArchitectProvider')) {
    $RequiredProviderNames += $ArchitectProvider
}
else {
    # A resume may load either provider from its immutable run manifest.
    $RequiredProviderNames += @('claude', 'codex')
}
if (-not [string]::IsNullOrWhiteSpace($ExecutionProvider)) {
    $RequiredProviderNames += $ExecutionProvider
}
else {
    # Architect routing is allowed to choose either provider.
    $RequiredProviderNames += @('claude', 'codex')
}
foreach ($ProviderName in @($RequiredProviderNames | Select-Object -Unique)) {
    $Volume = "nosafecircle_${ProviderName}-config"
    $VolumeCheck = Invoke-NscNativeCommand `
        -FilePath 'docker' `
        -ArgumentList @('volume', 'inspect', $Volume)
    if ($VolumeCheck.ExitCode -ne 0) {
        $VolumeCheck.Output | ForEach-Object { Write-Host $_ }
        throw "The persisted Docker provider volume is missing: $Volume"
    }
}

$Run = Invoke-NscNativeCommand `
    -FilePath 'python' `
    -ArgumentList $Arguments `
    -StreamOutput
exit $Run.ExitCode
