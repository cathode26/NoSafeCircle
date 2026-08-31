$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$NativeCommandPath = Join-Path $Root 'Pipeline\TaskReviewAgent\NativeCommand.ps1'
$StandardsPath = Join-Path $Root 'Docs\AI-Pipeline\OPERATOR_COMMAND_STANDARDS.md'
$TemplatePath = Join-Path $Root 'Docs\AI-Pipeline\OPERATOR_COMMAND_TEMPLATE.md'
$AgentsPath = Join-Path $Root 'AGENTS.md'
$ClaudePath = Join-Path $Root 'CLAUDE.md'

function Require-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Value,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Value) {
        throw $Message
    }
}

function Parse-PowerShellText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $Tokens = $null
    $Errors = $null
    $Ast = [System.Management.Automation.Language.Parser]::ParseInput(
        $Text,
        [ref]$Tokens,
        [ref]$Errors
    )

    return [pscustomobject]@{
        Ast = $Ast
        Errors = @($Errors)
    }
}

function Get-PSScriptRootParameterDefaults {
    param(
        [Parameter(Mandatory = $true)]
        [System.Management.Automation.Language.Ast]$Ast
    )

    $Findings = New-Object 'System.Collections.Generic.List[string]'
    $Parameters = @(
        $Ast.FindAll(
            {
                param($Node)
                $Node -is [System.Management.Automation.Language.ParameterAst]
            },
            $true
        )
    )

    foreach ($Parameter in $Parameters) {
        if ($null -eq $Parameter.DefaultValue) {
            continue
        }

        $UsesScriptRoot = @(
            $Parameter.DefaultValue.FindAll(
                {
                    param($Node)
                    $Node -is [System.Management.Automation.Language.VariableExpressionAst] -and
                        $Node.VariablePath.UserPath -ieq 'PSScriptRoot'
                },
                $true
            )
        )

        if ($UsesScriptRoot.Count -gt 0) {
            $Name = $Parameter.Name.VariablePath.UserPath
            [void]$Findings.Add($Name)
        }
    }

    return @($Findings)
}

function Get-NormalizedNativeArguments {
    param(
        [Parameter()]
        [string[]]$ArgumentList = @()
    )

    $Normalized = New-Object 'System.Collections.Generic.List[string]'

    foreach ($Argument in $ArgumentList) {
        if ($null -eq $Argument) {
            throw 'Native command arguments must not be null.'
        }

        [void]$Normalized.Add(
            $Argument.Replace("`r`n", "`n").Replace("`r", "`n")
        )
    }

    return $Normalized.ToArray()
}

function Invoke-SeparatedNativeCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter()]
        [string[]]$ArgumentList = @(),

        [Parameter()]
        [int[]]$AllowedExitCodes = @(0)
    )

    $NativeArguments = @(
        Get-NormalizedNativeArguments -ArgumentList $ArgumentList
    )

    $StdOutPath = [System.IO.Path]::GetTempFileName()
    $StdErrPath = [System.IO.Path]::GetTempFileName()
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ExitCode = 1

    try {
        try {
            $ErrorActionPreference = 'Continue'
            & $FilePath @NativeArguments 1> $StdOutPath 2> $StdErrPath
            $ExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }

        $StdOut = @(Get-Content -LiteralPath $StdOutPath)
        $StdErr = @(Get-Content -LiteralPath $StdErrPath)

        if ($AllowedExitCodes -notcontains $ExitCode) {
            $StdErr | ForEach-Object { Write-Host ("[STDERR] " + $_) }
            throw "$FilePath failed with exit code $ExitCode."
        }

        return [pscustomobject]@{
            ExitCode = [int]$ExitCode
            StdOut = @($StdOut)
            StdErr = @($StdErr)
        }
    }
    finally {
        Remove-Item -LiteralPath $StdOutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $StdErrPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host '[TEST] Required operator-command policy files'
foreach ($Path in @(
    $NativeCommandPath,
    $StandardsPath,
    $TemplatePath,
    $AgentsPath,
    $ClaudePath
)) {
    Require-True `
        -Value (Test-Path -LiteralPath $Path -PathType Leaf) `
        -Message "Required operator-command policy file is missing: $Path"
}
Write-Host '[PASS] Required operator-command policy files'

Write-Host '[TEST] Mandatory AGENTS.md and CLAUDE.md pointers'
$AgentsText = Get-Content -LiteralPath $AgentsPath -Raw -Encoding UTF8
$ClaudeText = Get-Content -LiteralPath $ClaudePath -Raw -Encoding UTF8

foreach ($RequiredReference in @(
    'Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md',
    'Docs/AI-Pipeline/OPERATOR_COMMAND_TEMPLATE.md'
)) {
    Require-True `
        -Value ($AgentsText.Contains($RequiredReference)) `
        -Message "AGENTS.md is missing required operator-command reference: $RequiredReference"
}

foreach ($RequiredImport in @(
    '@Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md',
    '@Docs/AI-Pipeline/OPERATOR_COMMAND_TEMPLATE.md'
)) {
    Require-True `
        -Value ($ClaudeText.Contains($RequiredImport)) `
        -Message "CLAUDE.md is missing required operator-command import: $RequiredImport"
}
Write-Host '[PASS] Mandatory AGENTS.md and CLAUDE.md pointers'

Write-Host '[TEST] Standards encode execution-policy and machine-data boundaries'
$StandardsText = Get-Content -LiteralPath $StandardsPath -Raw -Encoding UTF8
$TemplateText = Get-Content -LiteralPath $TemplatePath -Raw -Encoding UTF8

foreach ($RequiredStandardText in @(
    '-ExecutionPolicy Bypass',
    'CurrentUser',
    'LocalMachine',
    'Invoke-NscNativeCommand.Output',
    'machine data must come from stdout only'
)) {
    Require-True `
        -Value ($StandardsText.IndexOf($RequiredStandardText, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) `
        -Message "Operator standards are missing required reliability rule: $RequiredStandardText"
}

foreach ($RequiredTemplateText in @(
    '-ExecutionPolicy Bypass',
    'Invoke-NativeCapture',
    'Get-NativeMachineText',
    'StdOut',
    'StdErr'
)) {
    Require-True `
        -Value ($TemplateText.Contains($RequiredTemplateText)) `
        -Message "Operator template is missing required reliability mechanism: $RequiredTemplateText"
}

Require-True `
    -Value (-not $TemplateText.Contains('. $NativeHelper')) `
    -Message 'Canonical paste-ready template must not dot-source NativeCommand.ps1.'

Require-True `
    -Value (-not $TemplateText.Contains('Set-ExecutionPolicy -Scope CurrentUser')) `
    -Message 'Canonical template must not weaken CurrentUser execution policy.'

Require-True `
    -Value (-not $TemplateText.Contains('Set-ExecutionPolicy -Scope LocalMachine')) `
    -Message 'Canonical template must not weaken LocalMachine execution policy.'

Require-True `
    -Value (-not $TemplateText.Contains('return (($Result.Output -join')) `
    -Message 'Canonical machine-data helper must not return the combined diagnostic Output collection.'

Write-Host '[PASS] Standards encode execution-policy and machine-data boundaries'

Write-Host '[TEST] Policy detector self-tests'
$ValidFixture = Parse-PowerShellText -Text 'param([string]$Path) Write-Output $Path'
Require-True `
    -Value ($ValidFixture.Errors.Count -eq 0) `
    -Message 'PowerShell parser rejected the valid control fixture.'

$BashRedirectionFixture = Parse-PowerShellText -Text 'Get-Content < input.txt'
Require-True `
    -Value ($BashRedirectionFixture.Errors.Count -gt 0) `
    -Message 'PowerShell parser unexpectedly accepted Bash-style input redirection.'

$ScriptRootFixture = Parse-PowerShellText -Text 'param([string]$PromptPath = (Join-Path $PSScriptRoot "prompt.txt"))'
Require-True `
    -Value ($ScriptRootFixture.Errors.Count -eq 0) `
    -Message 'PowerShell parser rejected the PSScriptRoot-default detector fixture.'

$ScriptRootFixtureFindings = @(
    Get-PSScriptRootParameterDefaults -Ast $ScriptRootFixture.Ast
)
Require-True `
    -Value ($ScriptRootFixtureFindings.Count -eq 1) `
    -Message 'PSScriptRoot parameter-default detector did not catch its regression fixture.'
Write-Host '[PASS] Policy detector self-tests'

Write-Host '[TEST] Native machine-data stdout/stderr separation'
$ChannelFixture = Invoke-SeparatedNativeCapture `
    -FilePath 'powershell.exe' `
    -ArgumentList @(
        '-NoProfile',
        '-Command',
        "[Console]::Out.WriteLine('MACHINE_STDOUT'); [Console]::Error.WriteLine('DIAGNOSTIC_STDERR'); exit 0"
    )

$StdOutText = ($ChannelFixture.StdOut -join "`n")
$StdErrText = ($ChannelFixture.StdErr -join "`n")

Require-True `
    -Value ($ChannelFixture.ExitCode -eq 0) `
    -Message 'Channel-separation fixture returned a nonzero exit code.'

Require-True `
    -Value ($StdOutText.Contains('MACHINE_STDOUT')) `
    -Message 'Machine stdout fixture was not captured on stdout.'

Require-True `
    -Value (-not $StdOutText.Contains('DIAGNOSTIC_STDERR')) `
    -Message 'Native stderr contaminated machine stdout.'

Require-True `
    -Value ($StdErrText.Contains('DIAGNOSTIC_STDERR')) `
    -Message 'Native stderr fixture was not retained separately.'
Write-Host '[PASS] Native machine-data stdout/stderr separation'

Write-Host '[TEST] Tracked TaskReviewAgent PowerShell scripts parse in Windows PowerShell'
$Tracked = Invoke-SeparatedNativeCapture `
    -FilePath 'git' `
    -ArgumentList @(
        '-C',
        $Root,
        'ls-files',
        '--',
        'Pipeline/TaskReviewAgent'
    )

$PowerShellFiles = @(
    $Tracked.StdOut |
        Where-Object {
            -not [string]::IsNullOrWhiteSpace($_) -and
            $_.EndsWith('.ps1', [System.StringComparison]::OrdinalIgnoreCase)
        } |
        Sort-Object -Unique
)

Require-True `
    -Value ($PowerShellFiles.Count -gt 0) `
    -Message 'No tracked TaskReviewAgent PowerShell files were discovered.'

$ParseFailures = New-Object 'System.Collections.Generic.List[string]'
$ScriptRootDefaultFailures = New-Object 'System.Collections.Generic.List[string]'

foreach ($RelativePath in $PowerShellFiles) {
    $AbsolutePath = Join-Path $Root $RelativePath
    $Tokens = $null
    $Errors = $null
    $Ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $AbsolutePath,
        [ref]$Tokens,
        [ref]$Errors
    )

    if ($Errors.Count -gt 0) {
        foreach ($ParseError in $Errors) {
            [void]$ParseFailures.Add(
                "$($RelativePath):$($ParseError.Extent.StartLineNumber): $($ParseError.Message)"
            )
        }
        continue
    }

    $BadDefaults = @(Get-PSScriptRootParameterDefaults -Ast $Ast)
    foreach ($ParameterName in $BadDefaults) {
        [void]$ScriptRootDefaultFailures.Add(
            "$RelativePath parameter '$ParameterName' uses PSScriptRoot in its default value"
        )
    }
}

if ($ParseFailures.Count -gt 0) {
    Write-Host '[FAIL] Windows PowerShell parse errors:'
    $ParseFailures | ForEach-Object { Write-Host "  $_" }
    throw 'Tracked TaskReviewAgent PowerShell parsing failed.'
}
Write-Host "[PASS] Parsed $($PowerShellFiles.Count) tracked TaskReviewAgent PowerShell scripts"

if ($ScriptRootDefaultFailures.Count -gt 0) {
    Write-Host '[FAIL] Unsafe PSScriptRoot parameter defaults:'
    $ScriptRootDefaultFailures | ForEach-Object { Write-Host "  $_" }
    throw 'Tracked TaskReviewAgent PowerShell contains unsafe PSScriptRoot parameter defaults.'
}
Write-Host '[PASS] No tracked TaskReviewAgent parameter default depends on PSScriptRoot'

Write-Host 'TaskReviewAgent operator command policy smoke tests: PASS'
