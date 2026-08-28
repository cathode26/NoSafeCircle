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
$ProbeFile = Join-Path `
    ([System.IO.Path]::GetTempPath()) `
    "nsc-native-argument-$([Guid]::NewGuid().ToString('N')).py"
$ProbeProgram = @'
import sys
value = sys.argv[1]
print(f"contains-cr={chr(13) in value}")
print(f"lf-count={value.count(chr(10))}")
'@

try {
    [System.IO.File]::WriteAllText(
        $ProbeFile,
        $ProbeProgram,
        [System.Text.UTF8Encoding]::new($false)
    )

    $LineEndingProbe = Invoke-NscNativeCommand `
        -FilePath 'python' `
        -ArgumentList @($ProbeFile, $WindowsMultilinePayload)
}
finally {
    Remove-Item -LiteralPath $ProbeFile -Force -ErrorAction SilentlyContinue
}

if ($LineEndingProbe.ExitCode -ne 0) {
    $LineEndingProbe.Output | ForEach-Object { Write-Host $_ }
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
