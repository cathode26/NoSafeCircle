# Merge the NSC-095 wizard art into local main. Self-verifying: it recomputes the merge,
# refuses on conflicts, refuses if anything would be modified or deleted rather than added,
# and refuses on a dirty worktree. Nothing is pushed.
$ErrorActionPreference = 'Stop'
$repo   = 'C:\NSC\NSC\NoSafeCircle'
$branch = 'nsc095-wizard-128-art'
$tip    = 'c634c6496'
$msg    = 'C:\nscrev\reports\nsc095-merge-message.txt'

Set-Location $repo

$before = (git rev-parse --short HEAD)
Write-Host "main before: $before"

if ((git rev-parse --abbrev-ref HEAD) -ne 'main') { Write-Host 'ABORT: canonical is not on main'; exit 1 }
if (@(git status --porcelain).Count -ne 0) { Write-Host 'ABORT: canonical worktree is not clean'; exit 1 }
if ((git rev-parse --short $branch) -ne $tip) { Write-Host "ABORT: $branch is not at $tip"; exit 1 }

$tree = (git merge-tree --write-tree main $branch)
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: merge has conflicts'; exit 1 }

$changed = @(git diff --name-status main $tree | Where-Object { $_ -notmatch '^A' })
if ($changed.Count -ne 0) {
  Write-Host "ABORT: merge would modify or delete $($changed.Count) path(s), expected additions only"
  $changed | Select-Object -First 5 | ForEach-Object { Write-Host "  $_" }
  exit 1
}

$env:GIT_AUTHOR_NAME     = 'No Safe Circle Game Agent'
$env:GIT_AUTHOR_EMAIL    = 'game-agent@nosafecircle.invalid'
$env:GIT_COMMITTER_NAME  = 'No Safe Circle Game Agent'
$env:GIT_COMMITTER_EMAIL = 'game-agent@nosafecircle.invalid'

$merge = (git commit-tree $tree -p HEAD -p $branch -F $msg)
git merge --ff-only $merge
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: fast-forward failed'; exit 1 }

Write-Host "main after: $(git rev-parse --short HEAD)"
git log -1 --format='%h %s'
Write-Host '--- taskcontrol validate ---'
python Pipeline/TaskGraph/taskcontrol.py validate
