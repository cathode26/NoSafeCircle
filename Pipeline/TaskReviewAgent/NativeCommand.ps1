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
    $ExitCode = 1

    try {
        # Windows PowerShell 5.1 converts native stderr into ErrorRecord objects.
        # With ErrorActionPreference=Stop, ordinary Docker progress on stderr can
        # terminate a successful command before LASTEXITCODE can be inspected.
        $ErrorActionPreference = 'Continue'

        & $FilePath @ArgumentList 2>&1 | ForEach-Object {
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
