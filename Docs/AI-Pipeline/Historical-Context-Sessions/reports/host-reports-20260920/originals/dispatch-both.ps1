# Dispatch NSC-046 and NSC-007 back to back on one pinned commit, so both appear together.
$ErrorActionPreference = 'Continue'
$S   = 'C:\NSC\NSC\NoSafeCircle'
$R   = 'C:\NSC\NoSafeCircle-AssistantCheckouts'
$REC = "$R\.assistant-control"
Set-Location $S
$head = (git rev-parse HEAD)
Write-Host "PINNED SOURCE: $head"

foreach ($t in @(
    @{ id = 'NSC-046'; plan = 'nsc046-scope-plan.json'; run = 'task-orch-nsc046-20260917-2'; lease = 'task-orch-nsc046-20260917b' },
    @{ id = 'NSC-007'; plan = 'nsc007-scope-plan.json'; run = 'task-orch-nsc007-20260917-2'; lease = 'task-orch-nsc007-20260917b' }
)) {
    Write-Host "=========== $($t.id) ==========="
    Copy-Item "C:\nscrev\reports\$($t.plan)" "$REC\$($t.plan)" -Force

    # The prepared checkout is pinned to an older commit after tonight's merges.
    python -m Pipeline.AssistantControl --source $S --checkout-root $R refresh-prepared $($t.id) --source-commit $head *>&1 |
        Select-String -Pattern '"refreshed_to"|error' | Select-Object -First 2

    python -m Pipeline.AssistantControl --source $S --checkout-root $R prepare $($t.id) --source-commit $head *>&1 |
        Select-String -Pattern '"status"|error' | Select-Object -First 2
    python -m Pipeline.AssistantControl --source $S --checkout-root $R scope $($t.id) --plan "$REC\$($t.plan)" --lease-id $($t.lease) *>&1 |
        Select-String -Pattern '"accepted"|error' | Select-Object -First 2
    python -m Pipeline.AssistantControl --source $S --checkout-root $R reserve $($t.id) --run-id $($t.run) --capacity 4 *>&1 |
        Select-String -Pattern '"admitted"|dependencies_satisfied|blocked_dependencies|error' | Select-Object -First 3
    python -m Pipeline.AssistantControl --source $S --checkout-root $R start-worker $($t.id) --run-id $($t.run) --lease-id $($t.lease) --config "$REC\worker-claude-sonnet-high.json" --authorize-provider-spend *>&1 |
        Select-String -Pattern '"started"|"pid"|error' | Select-Object -First 3
}
Write-Host "=========== containers ==========="
docker ps --format '{{.Names}} | {{.Status}}'
