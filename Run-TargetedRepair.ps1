$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$feedback = "AgentCrew\inputs\human_playtest_feedback.md"
if (-not (Test-Path $feedback)) {
    throw "Human playtest feedback file was not found: $feedback"
}

Write-Host "Checking targeted repair script syntax..." -ForegroundColor Cyan
docker compose run --rm claude `
    python3 -m py_compile AgentCrew/targeted_repair.py
if ($LASTEXITCODE -ne 0) {
    throw "Targeted repair script syntax check failed."
}

Write-Host ""
Write-Host "Starting targeted implementation repair and validation..." `
    -ForegroundColor Cyan

docker compose run --rm claude `
    python3 AgentCrew/targeted_repair.py

if ($LASTEXITCODE -ne 0) {
    throw "Targeted repair failed. Review the latest validation report and crew run log."
}

Write-Host ""
Write-Host "Targeted repair passed static validation." -ForegroundColor Green
Write-Host "Return to Unity for the required human retest."
