$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Checking targeted UI script syntax..." -ForegroundColor Cyan
docker compose run --rm claude `
    python3 -m py_compile AgentCrew/targeted_ui_pass.py

if ($LASTEXITCODE -ne 0) {
    throw "Targeted UI script syntax check failed."
}

Write-Host ""
Write-Host "Starting controls HUD implementation and validation..." `
    -ForegroundColor Cyan

docker compose run --rm claude `
    python3 AgentCrew/targeted_ui_pass.py

if ($LASTEXITCODE -ne 0) {
    throw "Targeted controls HUD pass failed. Review the latest validation report and crew run log."
}

Write-Host ""
Write-Host "Controls HUD passed static validation." -ForegroundColor Green
Write-Host "Return to Unity for compilation and human Play Mode testing."
