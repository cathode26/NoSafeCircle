$ErrorActionPreference = 'Stop'
$env:PYTHONUNBUFFERED = '1'
$env:GIT_CONFIG_COUNT = '2'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'C:/NSC/NSC/NoSafeCircle'
$env:GIT_CONFIG_KEY_1 = 'safe.directory'
$env:GIT_CONFIG_VALUE_1 = 'C:/NSC/NSC/NoSafeCircle/.git'
Set-Location -LiteralPath 'C:\NSC\NSC\NoSafeCircle'

python -u -m Pipeline.AssistantControl `
  --source 'C:\NSC\NSC\NoSafeCircle' `
  --checkout-root 'C:\NSC\NoSafeCircle-AssistantCheckouts' `
  run-graph `
  --task NSC-066 `
  --worker-config 'C:\NSC\NoSafeCircle-AssistantCheckouts\.assistant-control\worker-codex-sol-high.json' `
  --authorize-provider-spend `
  --capacity 1 `
  --target-branch main

exit $LASTEXITCODE
