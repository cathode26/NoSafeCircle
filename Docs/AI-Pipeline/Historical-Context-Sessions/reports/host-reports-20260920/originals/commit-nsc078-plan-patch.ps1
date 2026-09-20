# Apply and commit the NSC-078 plan meter-caveat patch on local main. Nothing is pushed.
$ErrorActionPreference = 'Stop'
$repo = 'C:\NSC\NSC\NoSafeCircle'
$patch = 'C:\nscrev\reports\art-director\nsc078-plan-fix-20260917\nsc078-plan-meter-caveat.patch'
$file = 'Docs/Art/Environment/NSC-078_ART_PLAN.md'
$expectedHash = '5a68a8fd6e10ca9fd7760a6c10418a00cc1bd91037181bed970086aa4c696229'

Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD) -ne 'main') { Write-Host 'ABORT: not on main'; exit 1 }
if (@(git status --porcelain).Count -ne 0) { Write-Host 'ABORT: worktree not clean'; exit 1 }
Write-Host "main before: $(git rev-parse --short HEAD)"

git -c core.autocrlf=false apply --check $patch
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: patch does not apply'; exit 1 }
git -c core.autocrlf=false apply $patch

git add -- $file
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 1) { Write-Host "ABORT: expected 1 staged file, got $($staged.Count)"; $staged; exit 1 }

git -c user.name="No Safe Circle Game Agent" -c user.email="game-agent@nosafecircle.invalid" `
    commit -q -F 'C:\nscrev\reports\nsc078-plan-patch-message.txt'

# The gate hashes the committed LF blob, never the CRLF worktree file.
$actual = (git show "HEAD:$file" | Out-String)
$bytes = [System.Text.Encoding]::UTF8.GetBytes($actual -replace "`r`n", "`n")
Write-Host "main after: $(git rev-parse --short HEAD)"
git log -1 --format='%h %s'
Write-Host "--- confirm the gate hash with git itself ---"
git show "HEAD:$file" | & 'C:\Program Files\Git\usr\bin\sha256sum.exe'
Write-Host "expected: $expectedHash"
python -B Pipeline/TaskGraph/taskcontrol.py validate
