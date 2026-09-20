# Land the NSC-089, NSC-090, NSC-091 and NSC-092 delivery evidence on canonical local main.
#
# Four commits, fifteen files, all additions under Pipeline/TaskGraph/evidence/. No source, no
# contracts, no Unity assets. A clean fast-forward: the branch is built directly on the current
# main, so nothing is rewritten.
#
# Run it from anywhere:
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\nscrev\reports\delivery\land-nsc089-nsc091-evidence.ps1
#
# It pushes nothing and refuses rather than guessing: a dirty canonical tree, a main that has moved,
# a changed branch tip, or an unexpected file count each abort with no change made.

$ErrorActionPreference = "Stop"

$Canonical   = "C:\NSC\NSC\NoSafeCircle"
$Source      = "C:\nscrev\branch-verify"
$Branch      = "evidence/nsc-089-091-20260918"
$ExpectedMain = "2559514826e919bea243e1bf6fda4ad73462ac62"
$ExpectedTip  = "39a8d17e8d3645b948e68e89c92c28517134eef3"
$ExpectedFileCount = 15

function Fail($message) { Write-Host "ABORTED: $message" -ForegroundColor Red; exit 1 }

$mainNow = (git -C $Canonical rev-parse main).Trim()
if ($mainNow -ne $ExpectedMain) {
    Fail "canonical main is $mainNow, expected $ExpectedMain. Main moved after this was prepared; tell the Game Agent to rebuild the branch."
}

$dirty = git -C $Canonical status --porcelain --untracked-files=all
if ($dirty) {
    Write-Host ($dirty | Select-Object -First 10)
    Fail "canonical working tree is not clean. Nothing was changed."
}

$currentBranch = (git -C $Canonical rev-parse --abbrev-ref HEAD).Trim()
if ($currentBranch -ne "main") { Fail "canonical HEAD is on '$currentBranch', not main." }

# C:\nscrev\branch-verify is a WORKTREE of canonical, not a clone: it shares canonical's object
# store and ref namespace, so $Branch is already a canonical ref and no fetch is needed. The fetch
# below stays only as a fallback for the case where someone has this branch in a real clone.
# Written this way deliberately - disk cleanup is moving scratch directories right now, and this
# script must not depend on one surviving.
$fetched = (git -C $Canonical rev-parse --verify --quiet "refs/heads/$Branch")
if ($fetched) {
    $fetched = $fetched.Trim()
    Write-Host "Using canonical's own ref refs/heads/$Branch (no fetch needed)."
} elseif (Test-Path -LiteralPath $Source) {
    $tipNow = (git -C $Source rev-parse $Branch).Trim()
    if ($tipNow -ne $ExpectedTip) {
        Fail "$Branch is at $tipNow in $Source, expected $ExpectedTip. The branch changed after verification."
    }
    git -C $Canonical fetch $Source "${Branch}:refs/remotes/evidence-land/$Branch" --force | Out-Null
    $fetched = (git -C $Canonical rev-parse "refs/remotes/evidence-land/$Branch").Trim()
} else {
    Fail "canonical has no $Branch and $Source is gone. The evidence commits are objects in canonical; recover the ref with: git -C `"$Canonical`" branch $Branch $ExpectedTip"
}
if ($fetched -ne $ExpectedTip) { Fail "resolved $fetched, expected $ExpectedTip." }

$files = git -C $Canonical diff --name-only "$ExpectedMain..$fetched"
$count = ($files | Measure-Object).Count
if ($count -ne $ExpectedFileCount) {
    Write-Host $files
    Fail "expected $ExpectedFileCount changed files, found $count."
}
$outside = $files | Where-Object { $_ -notlike "Pipeline/TaskGraph/evidence/*" }
if ($outside) {
    Write-Host $outside
    Fail "the branch touches files outside Pipeline/TaskGraph/evidence/."
}

Write-Host "Fast-forwarding main $ExpectedMain -> $ExpectedTip ($count evidence files, 4 commits)."
git -C $Canonical merge --ff-only $fetched
if ($LASTEXITCODE -ne 0) { Fail "fast-forward refused by git." }

Write-Host ""
Write-Host "main is now $((git -C $Canonical rev-parse main).Trim())"
Write-Host "Nothing was pushed."
Write-Host ""
foreach ($task in @("NSC-089", "NSC-090", "NSC-091", "NSC-092", "NSC-014")) {
    Write-Host "--- $task ---"
    python -B "$Canonical\Pipeline\TaskGraph\taskcontrol.py" state $task
}
