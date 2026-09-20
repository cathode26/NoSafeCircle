# Fast-forward local main to the NSC-069 delivery evidence commit. Nothing is pushed.
$ErrorActionPreference = 'Stop'
$repo = 'C:\NSC\NSC\NoSafeCircle'
Set-Location $repo
if ((git rev-parse --abbrev-ref HEAD) -ne 'main') { Write-Host 'ABORT: not on main'; exit 1 }
if (@(git status --porcelain).Count -ne 0) { Write-Host 'ABORT: worktree not clean'; exit 1 }
Write-Host "main before: $(git rev-parse --short HEAD)"

git fetch -q C:\nscrev\branch-verify HEAD:refs/remotes/verify/nsc069-evidence -f
$parent = (git rev-parse refs/remotes/verify/nsc069-evidence^)
if ($parent -ne (git rev-parse HEAD)) { Write-Host 'ABORT: not a clean fast-forward; main moved'; exit 1 }

git merge --ff-only refs/remotes/verify/nsc069-evidence
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: fast-forward failed'; exit 1 }
Write-Host "main after: $(git rev-parse --short HEAD)"
git log -1 --format='%h %s'
Write-Host '--- NSC-069 state on canonical main ---'
python -B Pipeline/TaskGraph/taskcontrol.py state NSC-069
Write-Host '--- the five rooms ---'
foreach ($t in 'NSC-044','NSC-045','NSC-046','NSC-047','NSC-048') {
  python -B Pipeline/TaskGraph/taskcontrol.py state $t | Select-String 'derived_state'
}
