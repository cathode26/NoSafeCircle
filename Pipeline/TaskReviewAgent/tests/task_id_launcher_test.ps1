# Execute the production parameter validators without invoking launcher bodies.
$ErrorActionPreference = 'Stop'
$Directory = Split-Path -Parent $PSScriptRoot
$Count = 0
foreach ($Name in @('Start-GameTaskAgent.ps1', 'Start-TaskReviewAgent.ps1', 'Start-AutonomousGraphRun.ps1')) {
    $Tokens = $null
    $Errors = $null
    $Ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Directory $Name), [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -ne 0) { throw "Launcher parse failed: $Name" }
    foreach ($Parameter in $Ast.ParamBlock.Parameters) {
        foreach ($Attribute in $Parameter.Attributes) {
            if ($Attribute.TypeName.FullName -ne 'ValidatePattern') { continue }
            $Pattern = $Attribute.PositionalArguments[0].Value
            if (-not $Pattern.Contains('^NSC-')) { continue }
            $Probe = [scriptblock]::Create("param([ValidatePattern('$Pattern')][string]`$TaskId) `$TaskId")
            foreach ($Id in @('NSC-042', 'NSC-1000', 'NSC-2000', 'NSC-3039')) {
                if ((& $Probe $Id) -cne $Id) { throw "Canonical ID rejected by $Name : $Id" }
                $Count++
            }
            foreach ($Id in @('NSC-20', 'nsc-2000', 'NSC-02000', 'NSC-0000', 'NSC-1000000000', '../NSC-2000', 'NSC-2000-extra')) {
                $Rejected = $false
                try { & $Probe $Id | Out-Null } catch [System.Management.Automation.ParameterBindingException] { $Rejected = $true }
                if (-not $Rejected) { throw "Malformed ID accepted by $Name : $Id" }
                $Count++
            }
        }
    }
}
if ($Count -ne 44) { throw "Expected four production validators and forty-four binding cases, got $Count" }
Write-Host "Task ID launcher validation: PASS ($Count cases; zero launcher bodies executed)"
