$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Checking orchestrator syntax..." -ForegroundColor Cyan
docker compose run --rm claude python3 -m py_compile AgentCrew/orchestrator.py
if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed."
}

Write-Host ""
Write-Host "Starting the four-agent Claude Code pipeline..." -ForegroundColor Cyan
docker compose run --rm claude python3 AgentCrew/orchestrator.py
if ($LASTEXITCODE -ne 0) {
    throw "Agent pipeline failed. Review AgentCrew/outputs/crew_run_log.json."
}

Write-Host ""
Write-Host "Pipeline completed. Open Unity for compilation and Play Mode testing." -ForegroundColor Green
