$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
. (Join-Path $Root 'Pipeline\TaskReviewAgent\NativeCommand.ps1')

$Success = Invoke-NscNativeCommand `
    -FilePath 'cmd.exe' `
    -ArgumentList @(
        '/d', '/s', '/c',
        'echo expected-success-stderr 1>&2 & exit /b 0'
    )

if ($Success.ExitCode -ne 0) {
    throw "Successful native stderr command returned $($Success.ExitCode)."
}
if (-not ($Success.Output -match 'expected-success-stderr')) {
    throw 'Successful native stderr output was not captured.'
}
if ($ErrorActionPreference -ne 'Stop') {
    throw 'Native command helper did not restore ErrorActionPreference.'
}

$Failure = Invoke-NscNativeCommand `
    -FilePath 'cmd.exe' `
    -ArgumentList @(
        '/d', '/s', '/c',
        'echo expected-failure-stderr 1>&2 & exit /b 7'
    )

if ($Failure.ExitCode -ne 7) {
    throw "Failing native command returned $($Failure.ExitCode), expected 7."
}
if (-not ($Failure.Output -match 'expected-failure-stderr')) {
    throw 'Failing native stderr output was not captured.'
}
if ($ErrorActionPreference -ne 'Stop') {
    throw 'Native command helper did not restore ErrorActionPreference after failure.'
}

$WindowsMultilinePayload = "set -eu`r`nprintf 'probe-ok\n'`r`n"
$LineEndingProbe = Invoke-NscNativeCommand `
    -FilePath 'python' `
    -ArgumentList @(
        '-c',
        'import sys; value=sys.argv[1]; print("contains-cr=" + str("\r" in value)); print("lf-count=" + str(value.count("\n")))',
        $WindowsMultilinePayload
    )

if ($LineEndingProbe.ExitCode -ne 0) {
    throw "Multiline argument probe returned $($LineEndingProbe.ExitCode)."
}
if (-not ($LineEndingProbe.Output -contains 'contains-cr=False')) {
    throw 'Native command helper left a carriage return in a multiline argument.'
}
if (-not ($LineEndingProbe.Output -contains 'lf-count=2')) {
    throw 'Native command helper did not preserve the expected LF line count.'
}
if ($ErrorActionPreference -ne 'Stop') {
    throw 'Native command helper did not restore ErrorActionPreference after multiline normalization.'
}

Write-Host 'TaskReviewAgent native command smoke tests: PASS'
