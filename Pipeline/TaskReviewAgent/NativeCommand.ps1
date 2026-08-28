function Invoke-NscNativeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$FilePath,

        [Parameter()]
        [string[]]$ArgumentList = @(),

        [switch]$StreamOutput
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $Lines = New-Object 'System.Collections.Generic.List[string]'
    $NormalizedArguments = New-Object 'System.Collections.Generic.List[string]'
    $ExitCode = 1

    foreach ($Argument in $ArgumentList) {
        if ($null -eq $Argument) {
            throw 'Native command arguments must not be null.'
        }

        # Windows here-strings use CRLF. Passing one directly to Linux bash
        # leaves a carriage return on tokens such as `set -eu`, which Bash then
        # interprets as an invalid option. Native multiline payloads are textual
        # protocol values, so normalize them before crossing the OS boundary.
        $Normalized = $Argument.Replace("`r`n", "`n").Replace("`r", "`n")
        [void]$NormalizedArguments.Add($Normalized)
    }

    $NativeArgumentList = $NormalizedArguments.ToArray()

    try {
        # Windows PowerShell 5.1 converts native stderr into ErrorRecord objects.
        # With ErrorActionPreference=Stop, ordinary Docker progress on stderr can
        # terminate a successful command before LASTEXITCODE can be inspected.
        $ErrorActionPreference = 'Continue'

        & $FilePath @NativeArgumentList 2>&1 | ForEach-Object {
            $Text = $_.ToString()
            [void]$Lines.Add($Text)
            if ($StreamOutput) {
                Write-Host $Text
            }
        }

        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    [pscustomobject]@{
        ExitCode = [int]$ExitCode
        Output   = @($Lines)
    }
}
