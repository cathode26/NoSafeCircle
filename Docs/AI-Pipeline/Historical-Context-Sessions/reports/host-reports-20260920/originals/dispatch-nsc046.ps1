# Dispatch NSC-046 Chapel of Ash Tilemap Blockout and Cover Routes: prepare -> scope -> reserve -> start-worker -> status.
# Claude Sonnet high in Docker on the Gmail account. Stops at the first failure.
$ErrorActionPreference = 'Stop'
$S   = 'C:\NSC\NSC\NoSafeCircle'
$R   = 'C:\NSC\NoSafeCircle-AssistantCheckouts'
$REC = "$R\.assistant-control"
$run   = 'task-orch-nsc046-20260917-1'
$lease = 'task-orch-nsc046-20260917'

Copy-Item 'C:\nscrev\reports\nsc046-scope-plan.json' "$REC\nsc046-scope-plan.json" -Force

Set-Location $S
$head = (git rev-parse HEAD)
Write-Host "source commit: $head"

Write-Host '--- prepare ---'
python -m Pipeline.AssistantControl --source $S --checkout-root $R prepare NSC-046 --source-commit $head
if ($LASTEXITCODE -ne 0) { Write-Host 'STOP: prepare failed'; exit 1 }

Write-Host '--- scope ---'
python -m Pipeline.AssistantControl --source $S --checkout-root $R scope NSC-046 --plan "$REC\nsc046-scope-plan.json" --lease-id $lease
if ($LASTEXITCODE -ne 0) { Write-Host 'STOP: scope failed'; exit 1 }

Write-Host '--- reserve ---'
python -m Pipeline.AssistantControl --source $S --checkout-root $R reserve NSC-046 --run-id $run --capacity 3
if ($LASTEXITCODE -ne 0) { Write-Host 'STOP: reserve failed'; exit 1 }

Write-Host '--- start-worker ---'
python -m Pipeline.AssistantControl --source $S --checkout-root $R start-worker NSC-046 --run-id $run --lease-id $lease --config "$REC\worker-claude-sonnet-high.json" --authorize-provider-spend
if ($LASTEXITCODE -ne 0) { Write-Host 'STOP: start-worker failed'; exit 1 }

Write-Host '--- worker-status ---'
python -m Pipeline.AssistantControl --source $S --checkout-root $R worker-status NSC-046
