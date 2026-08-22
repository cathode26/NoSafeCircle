[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("EditMode", "PlayMode")]
    [string]$TestPlatform,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$TestFilter,

    [string]$UnityExecutable,

    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"
$ExitPrecondition = 10
$ExitUnity = 20
$ExitResult = 30
$ExitMutation = 40

function Invoke-Git {
    param([string]$RepositoryRoot, [string[]]$Arguments)

    $output = & git -C $RepositoryRoot @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Git command failed: git -C `"$RepositoryRoot`" $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return ($output | Out-String).Trim()
}

function Get-WorkingTreeStatus {
    param([string]$RepositoryRoot)
    return Invoke-Git $RepositoryRoot @("status", "--porcelain=v1", "--untracked-files=all")
}

function Stop-WithCode {
    param([int]$Code, [string]$Message)
    Write-Error $Message
    exit $Code
}

try {
    if ([string]::IsNullOrWhiteSpace($ProjectPath)) {
        $ProjectPath = Join-Path $PSScriptRoot "..\.."
    }
    $resolvedProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path
    $repositoryRoot = (& git -C $resolvedProjectPath rev-parse --show-toplevel 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repositoryRoot)) {
        Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: ProjectPath is not inside a Git repository: $resolvedProjectPath"
    }
    $repositoryRoot = (Resolve-Path -LiteralPath $repositoryRoot).Path

    $projectSettings = Join-Path $resolvedProjectPath "ProjectSettings\ProjectVersion.txt"
    if (-not (Test-Path -LiteralPath $projectSettings -PathType Leaf)) {
        Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: ProjectPath is not a Unity project: $resolvedProjectPath"
    }

    $preStatus = Get-WorkingTreeStatus $repositoryRoot
    if (-not [string]::IsNullOrWhiteSpace($preStatus)) {
        Write-Host "Working tree paths present before test run:"
        Write-Host $preStatus
        Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: Git working tree must be completely clean, including untracked files."
    }

    $preHead = Invoke-Git $repositoryRoot @("rev-parse", "HEAD")
    $preTree = Invoke-Git $repositoryRoot @("rev-parse", "HEAD^{tree}")
    $versionLine = Get-Content -LiteralPath $projectSettings | Where-Object { $_ -match '^m_EditorVersion:\s*(.+)$' } | Select-Object -First 1
    if (-not $versionLine -or $versionLine -notmatch '^m_EditorVersion:\s*(.+)$') {
        Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: Could not read m_EditorVersion from $projectSettings"
    }
    $unityVersion = $Matches[1].Trim()

    if ([string]::IsNullOrWhiteSpace($UnityExecutable)) {
        $UnityExecutable = Join-Path ${env:ProgramFiles} "Unity\Hub\Editor\$unityVersion\Editor\Unity.exe"
    }
    if (-not (Test-Path -LiteralPath $UnityExecutable -PathType Leaf)) {
        Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: Unity executable does not exist: $UnityExecutable"
    }

    $artifactDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("NoSafeCircle-UnityTests-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $artifactDirectory | Out-Null
    $xmlPath = Join-Path $artifactDirectory "test-results.xml"
    $logPath = Join-Path $artifactDirectory "unity.log"
    Write-Host "Temporary artifacts will be preserved at: $artifactDirectory"

    $unityExitCode = $null
    $invocationFailure = $null
    try {
        & $UnityExecutable `
            -batchmode `
            -projectPath $resolvedProjectPath `
            -runTests `
            -testPlatform $TestPlatform `
            -testFilter $TestFilter `
            -testResults $xmlPath `
            -logFile $logPath
        $unityExitCode = $LASTEXITCODE
    }
    catch {
        $invocationFailure = $_.Exception.Message
        $unityExitCode = -1
    }
    finally {
        $postCheckFailure = $null
        try {
            $postHead = Invoke-Git $repositoryRoot @("rev-parse", "HEAD")
            $postTree = Invoke-Git $repositoryRoot @("rev-parse", "HEAD^{tree}")
            $postStatus = Get-WorkingTreeStatus $repositoryRoot
        }
        catch {
            $postCheckFailure = $_.Exception.Message
        }
    }

    if ($postCheckFailure) {
        Stop-WithCode $ExitMutation "REPOSITORY CHECK FAILURE: Post-run Git checks could not complete: $postCheckFailure"
    }
    if ($postHead -ne $preHead) {
        Stop-WithCode $ExitMutation "REPOSITORY MUTATION FAILURE: HEAD changed from $preHead to $postHead. No changes were restored."
    }
    if ($postTree -ne $preTree) {
        Stop-WithCode $ExitMutation "REPOSITORY MUTATION FAILURE: Git tree changed from $preTree to $postTree. No changes were restored."
    }
    if (-not [string]::IsNullOrWhiteSpace($postStatus)) {
        Write-Host "Working tree paths changed or created during the test run:"
        Write-Host $postStatus
        Stop-WithCode $ExitMutation "REPOSITORY MUTATION FAILURE: Passing assertions plus a dirty repository is failure. No changes were restored."
    }

    if ($invocationFailure) {
        Stop-WithCode $ExitUnity "UNITY FAILURE: Unity could not be invoked: $invocationFailure`nXML: $xmlPath`nLog: $logPath"
    }
    if ($unityExitCode -ne 0) {
        Stop-WithCode $ExitUnity "UNITY FAILURE: Unity exited with code $unityExitCode.`nXML: $xmlPath`nLog: $logPath"
    }
    if (-not (Test-Path -LiteralPath $xmlPath -PathType Leaf)) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity did not create the required XML result file: $xmlPath"
    }

    try {
        [xml]$resultDocument = Get-Content -LiteralPath $xmlPath -Raw
        $testRun = $resultDocument.SelectSingleNode("/test-run")
        if ($null -eq $testRun) {
            throw "Missing test-run root element."
        }
        $countValues = @{}
        foreach ($attributeName in @("total", "passed", "failed", "skipped")) {
            $attributeValue = $testRun.GetAttribute($attributeName)
            $parsedValue = 0
            if (-not [int]::TryParse($attributeValue, [ref]$parsedValue) -or $parsedValue -lt 0) {
                throw "The test-run $attributeName attribute is missing or invalid."
            }
            $countValues[$attributeName] = $parsedValue
        }
        $total = $countValues["total"]
        $passed = $countValues["passed"]
        $failed = $countValues["failed"]
        $skipped = $countValues["skipped"]
        $result = $testRun.GetAttribute("result")
        if ([string]::IsNullOrWhiteSpace($result)) {
            throw "The test-run result attribute is missing."
        }
    }
    catch {
        Stop-WithCode $ExitResult "RESULT FAILURE: XML is missing required test-run data or is malformed: $($_.Exception.Message)"
    }

    Write-Host "Git HEAD: $preHead"
    Write-Host "Git tree: $preTree"
    Write-Host "Post-run tree: $postTree"
    Write-Host "Unity version: $unityVersion"
    Write-Host "Unity executable: $UnityExecutable"
    Write-Host "Unity exit code: $unityExitCode"
    Write-Host "Result: $result (total=$total passed=$passed failed=$failed skipped=$skipped)"
    Write-Host "XML: $xmlPath"
    Write-Host "Log: $logPath"

    if ($failed -ne 0) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Test result reports $failed failed test(s)."
    }
    if ($result -ne "Passed") {
        Stop-WithCode $ExitResult "RESULT FAILURE: Test-run result is '$result', expected 'Passed'."
    }

    Write-Host "VALIDATION PASSED: assertions passed and the repository remained clean."
    exit 0
}
catch {
    Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: $($_.Exception.Message)"
}
