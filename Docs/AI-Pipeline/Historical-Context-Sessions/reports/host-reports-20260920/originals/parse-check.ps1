param([string]$ScriptPath = "C:\nscrev\reports\operator-runner-4-1.ps1")
$Tokens = $null
$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($ScriptPath, [ref]$Tokens, [ref]$Errors) | Out-Null
if ($Errors.Count -ne 0) {
    $Errors | ForEach-Object { Write-Host ("[PARSE] " + $_.Message) }
    exit 1
}
Write-Host ("[PARSE] OK " + $ScriptPath)
exit 0
