# Merge the Unity clean-tree runner fix into local main. Self-verifying; nothing is pushed.
$ErrorActionPreference = 'Stop'
$repo = 'C:\NSC\NSC\NoSafeCircle'
$ref  = 'refs/remotes/maint/decompose'
$tip  = 'ac4a61b1f'
$msg  = 'C:\nscrev\reports\decompose-merge-message.txt'

Set-Location $repo
Write-Host "main before: $(git rev-parse --short HEAD)"
if ((git rev-parse --abbrev-ref HEAD) -ne 'main') { Write-Host 'ABORT: not on main'; exit 1 }
if (@(git status --porcelain).Count -ne 0) { Write-Host 'ABORT: worktree not clean'; exit 1 }
git fetch -q C:\nscrev\ci-134-fix fix/decompose-all-claude:$ref -f
if ((git rev-parse --short $ref) -ne $tip) { Write-Host "ABORT: branch is not at $tip"; exit 1 }

$tree = (git merge-tree --write-tree main $ref)
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: merge has conflicts'; exit 1 }
$touched = @(git diff --name-only main $tree)
if ($touched.Count -ne 8) { Write-Host "ABORT: expected 8 files, got $($touched.Count)"; $touched; exit 1 }

$env:GIT_AUTHOR_NAME='No Safe Circle Game Agent'; $env:GIT_AUTHOR_EMAIL='game-agent@nosafecircle.invalid'
$env:GIT_COMMITTER_NAME='No Safe Circle Game Agent'; $env:GIT_COMMITTER_EMAIL='game-agent@nosafecircle.invalid'
$merge = (git commit-tree $tree -p HEAD -p $ref -F $msg)
git merge --ff-only $merge
if ($LASTEXITCODE -ne 0) { Write-Host 'ABORT: fast-forward failed'; exit 1 }
Write-Host "main after: $(git rev-parse --short HEAD)"
git log -1 --format='%h %s'
python -B Pipeline/TaskGraph/taskcontrol.py validate
