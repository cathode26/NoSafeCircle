$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$paths = @(
    "AgentCrew\outputs\feature_contract.json",
    "AgentCrew\outputs\implementation_summary.md",
    "AgentCrew\outputs\validation_report.json",
    "AgentCrew\outputs\run_report.md",
    "AgentCrew\outputs\submission_checklist.md",
    "Docs\architecture.mmd"
)

foreach ($path in $paths) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor Cyan
    Write-Host $path -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor Cyan

    if (Test-Path $path) {
        Get-Content $path
    }
    else {
        Write-Host "Not created yet." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Git status:" -ForegroundColor Cyan
git status --short
