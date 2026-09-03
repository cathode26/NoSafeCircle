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

    # Windows PowerShell 5.1 can promote native stderr into terminating errors when
    # ErrorActionPreference=Stop, even when git exits 0. Invoke git through
    # Start-Process so stdout/stderr remain ordinary files and exit code is authoritative.
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $gitArguments = @(
            (ConvertTo-WindowsCommandLineArgument "-C"),
            (ConvertTo-WindowsCommandLineArgument $RepositoryRoot)
        )
        foreach ($argument in $Arguments) {
            $gitArguments += ConvertTo-WindowsCommandLineArgument $argument
        }

        $process = Start-Process `
            -FilePath "git.exe" `
            -ArgumentList $gitArguments `
            -Wait `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        $stdout = ""
        if (Test-Path -LiteralPath $stdoutPath -PathType Leaf) {
            $stdout = Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue
            if ($null -eq $stdout) { $stdout = "" }
        }

        $stderr = ""
        if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
            $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
            if ($null -eq $stderr) { $stderr = "" }
        }

        if ($process.ExitCode -ne 0) {
            $detailParts = @()
            if (-not [string]::IsNullOrWhiteSpace($stdout)) {
                $detailParts += $stdout.Trim()
            }
            if (-not [string]::IsNullOrWhiteSpace($stderr)) {
                $detailParts += $stderr.Trim()
            }

            throw "Git command failed: git -C `"$RepositoryRoot`" $($Arguments -join ' ')`n$($detailParts -join [Environment]::NewLine)"
        }

        # Successful stderr is intentionally ignored. Git for Windows can emit benign
        # line-ending warnings while still returning success.
        return $stdout.Trim()
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-WorkingTreeStatus {
    param([string]$RepositoryRoot)

    $porcelain = Invoke-Git $RepositoryRoot @("status", "--porcelain=v1", "--untracked-files=all")
    if ([string]::IsNullOrWhiteSpace($porcelain)) {
        return ""
    }

    # Unity can rewrite a tracked file without changing its Git-normalized content.
    # Only report real tracked content differences or real untracked files.
    $tracked = Invoke-Git $RepositoryRoot @("diff", "--name-status", "--no-ext-diff", "HEAD", "--")
    $untracked = Invoke-Git $RepositoryRoot @("ls-files", "--others", "--exclude-standard")

    $meaningful = @()

    if (-not [string]::IsNullOrWhiteSpace($tracked)) {
        $meaningful += $tracked
    }

    if (-not [string]::IsNullOrWhiteSpace($untracked)) {
        foreach ($item in ($untracked -split "\r?\n")) {
            if (-not [string]::IsNullOrWhiteSpace($item)) {
                $meaningful += "?? $item"
            }
        }
    }

    return ($meaningful -join [Environment]::NewLine)
}

function Stop-WithCode {
    param([int]$Code, [string]$Message)
    [Console]::Error.WriteLine($Message)
    exit $Code
}

function ConvertTo-WindowsCommandLineArgument {
    param([AllowEmptyString()][string]$Argument)

    # Start-Process in Windows PowerShell 5.1 joins ArgumentList into one command
    # line. Quote each value using the CommandLineToArgvW escaping rules.
    $quoted = New-Object System.Text.StringBuilder
    [void]$quoted.Append('"')
    $backslashes = 0
    foreach ($character in $Argument.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes++
            continue
        }
        if ($character -eq '"') {
            [void]$quoted.Append(('\' * (($backslashes * 2) + 1)))
            [void]$quoted.Append('"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void]$quoted.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$quoted.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$quoted.Append(('\' * ($backslashes * 2)))
    }
    [void]$quoted.Append('"')
    return $quoted.ToString()
}

function Wait-ForRepositoryQuiescence {
    param(
        [string]$RepositoryRoot,
        [int]$RequiredStableSamples = 4,
        [int]$SampleDelayMilliseconds = 500
    )

    # Unity can finish its test process before a package/settings writer has
    # released its final filesystem update.  A single immediate status read can
    # therefore produce a false-clean result.  Require the raw porcelain state
    # to remain identical across a bounded settling window before the
    # authoritative post-run checks are captured.
    $previous = $null
    $stable = 0
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $current = Invoke-Git $RepositoryRoot @(
            "status", "--porcelain=v1", "--untracked-files=all"
        )
        if ($null -ne $previous -and $current -eq $previous) {
            $stable++
        }
        else {
            $stable = 1
            $previous = $current
        }
        if ($stable -ge $RequiredStableSamples) {
            return
        }
        Start-Sleep -Milliseconds $SampleDelayMilliseconds
    }
    throw "Repository did not reach a stable post-Unity filesystem state."
}

function Invoke-PythonCapture {
    param([string[]]$Arguments)

    $captureRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("NoSafeCircle-Python-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $captureRoot | Out-Null
    $stdoutPath = Join-Path $captureRoot "stdout.txt"
    $stderrPath = Join-Path $captureRoot "stderr.txt"
    try {
        $quotedArguments = @($Arguments | ForEach-Object { ConvertTo-WindowsCommandLineArgument $_ })
        $process = Start-Process -FilePath "python.exe" -ArgumentList $quotedArguments -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $stdout = if (Test-Path -LiteralPath $stdoutPath) { Get-Content -LiteralPath $stdoutPath -Raw } else { "" }
        $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Raw } else { "" }
        $outputParts = @()
        if (-not [string]::IsNullOrWhiteSpace($stdout)) { $outputParts += $stdout.Trim() }
        if (-not [string]::IsNullOrWhiteSpace($stderr)) { $outputParts += $stderr.Trim() }
        return [PSCustomObject]@{
            ExitCode = $process.ExitCode
            Output = ($outputParts -join [Environment]::NewLine)
        }
    }
    finally {
        Remove-Item -LiteralPath $captureRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
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
    $UnityExecutable = (Resolve-Path -LiteralPath $UnityExecutable).Path

    $artifactDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("NoSafeCircle-UnityTests-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $artifactDirectory | Out-Null
    $xmlPath = Join-Path $artifactDirectory "test-results.xml"
    $logPath = Join-Path $artifactDirectory "unity.log"
    Write-Host "Temporary artifacts will be preserved at: $artifactDirectory"

    $unityExitCode = $null
    $invocationFailure = $null
    $xmlPublished = $false
    try {
        $unityArguments = @(
            "-batchmode",
            "-projectPath", (ConvertTo-WindowsCommandLineArgument $resolvedProjectPath),
            "-runTests",
            "-testPlatform", (ConvertTo-WindowsCommandLineArgument $TestPlatform),
            "-testFilter", (ConvertTo-WindowsCommandLineArgument $TestFilter),
            "-testResults", (ConvertTo-WindowsCommandLineArgument $xmlPath),
            "-logFile", (ConvertTo-WindowsCommandLineArgument $logPath)
        )
        $unityProcess = Start-Process -FilePath $UnityExecutable -ArgumentList $unityArguments -Wait -PassThru
        $unityExitCode = $unityProcess.ExitCode

        $xmlPublicationDeadline = [DateTime]::UtcNow.AddSeconds(5)
        do {
            $xmlPublished = Test-Path -LiteralPath $xmlPath -PathType Leaf
            if (-not $xmlPublished -and [DateTime]::UtcNow -lt $xmlPublicationDeadline) {
                Start-Sleep -Milliseconds 100
            }
        } while (-not $xmlPublished -and [DateTime]::UtcNow -lt $xmlPublicationDeadline)
    }
    catch {
        $invocationFailure = $_.Exception.Message
        $unityExitCode = -1
    }
    finally {
        $postCheckFailure = $null
        try {
            Wait-ForRepositoryQuiescence $repositoryRoot
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
    if (-not $xmlPublished) {
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
    if ($total -le 0) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity discovered zero tests for platform '$TestPlatform' and filter '$TestFilter'."
    }

    $manifestPath = Join-Path $artifactDirectory "validation-manifest.json"
    $manifestTemporaryPath = Join-Path $artifactDirectory (".validation-manifest-" + [Guid]::NewGuid().ToString("N") + ".tmp")

    # Unity batch logs regularly contain trailing spaces. Normalize them before
    # their SHA/size identities enter the authoritative validation manifest, so
    # the exact reviewed artifact is also safe for a later evidence commit.
    $logHygieneScript = Join-Path $resolvedProjectPath "Pipeline\Testing\unity_log_hygiene.py"
    if (-not (Test-Path -LiteralPath $logHygieneScript -PathType Leaf)) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log hygiene helper is missing: $logHygieneScript"
    }
    $normalization = Invoke-PythonCapture @($logHygieneScript, "normalize", "--path", $logPath, "--json")
    $normalizationOutput = $normalization.Output
    if ($normalization.ExitCode -ne 0) {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log normalization failed with exit code $($normalization.ExitCode).`n$normalizationOutput"
    }
    try {
        $logNormalization = $normalizationOutput | ConvertFrom-Json
    }
    catch {
        Stop-WithCode $ExitResult "RESULT FAILURE: Unity log normalizer returned invalid JSON.`n$normalizationOutput"
    }
    Write-Host "Unity log hygiene: $($logNormalization.status) (changed lines: $($logNormalization.changed_lines))"

    try {
        $xmlFile = Get-Item -LiteralPath $xmlPath -ErrorAction Stop
        $logFile = Get-Item -LiteralPath $logPath -ErrorAction Stop
        if ($xmlFile.PSIsContainer -or $logFile.PSIsContainer) {
            throw "Unity XML and log artifacts must be regular files."
        }
        $xmlHash = (Get-FileHash -LiteralPath $xmlPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $logHash = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $manifest = [ordered]@{
            schema_version = "1.0"
            manifest_type = "unity_test_validation"
            status = "passed"
            validated_state = [ordered]@{
                commit = $preHead
                tree = $preTree
                post_commit = $postHead
                post_tree = $postTree
                repository_clean_before = $true
                repository_clean_after = $true
            }
            unity = [ordered]@{
                version = $unityVersion
                executable = $UnityExecutable
                exit_code = [int]$unityExitCode
                test_platform = $TestPlatform
                test_filter = $TestFilter
            }
            test_run = [ordered]@{
                result = $result
                total = [int]$total
                passed = [int]$passed
                failed = [int]$failed
                skipped = [int]$skipped
            }
            artifacts = [ordered]@{
                xml = [ordered]@{
                    relative_path = "test-results.xml"
                    sha256 = $xmlHash
                    size_bytes = [long]$xmlFile.Length
                }
                log = [ordered]@{
                    relative_path = "unity.log"
                    sha256 = $logHash
                    size_bytes = [long]$logFile.Length
                }
            }
            runner = [ordered]@{
                path = "Pipeline/Testing/run_unity_tests_clean.ps1"
            }
        }
        $manifestJson = ($manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine
        $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
        $stream = New-Object System.IO.FileStream(
            $manifestTemporaryPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $bytes = $utf8WithoutBom.GetBytes($manifestJson)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        }
        finally {
            $stream.Dispose()
        }
        [System.IO.File]::Move($manifestTemporaryPath, $manifestPath)
    }
    catch {
        Remove-Item -LiteralPath $manifestTemporaryPath -Force -ErrorAction SilentlyContinue
        Stop-WithCode $ExitResult "RESULT FAILURE: Validation manifest could not be constructed or published: $($_.Exception.Message)"
    }

    Write-Host "Validation manifest: $manifestPath"
    Write-Host "VALIDATION PASSED: assertions passed and the repository remained clean."
    exit 0
}
catch {
    Stop-WithCode $ExitPrecondition "PRECONDITION FAILURE: $($_.Exception.Message)"
}
