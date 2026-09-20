# Merged non-task worktrees and their branches, planned by the Game Agent 2026-09-17.
# Every branch below has all of its commits in local main. Tips are archived first.
# `git worktree remove` runs without --force: a worktree with uncommitted work is reported, not destroyed.
$R = "C:\NSC\NSC\NoSafeCircle"
$ErrorActionPreference = "Continue"
$failed = @()

git -C $R update-ref "refs/archive/codex/conformance-cherry-pick-content-20260914" "codex/conformance-cherry-pick-content-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/enemy-eight-direction-integration-20260914" "codex/enemy-eight-direction-integration-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/ger-active-viewer-20260914" "codex/ger-active-viewer-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/missing-validation-policy-review-20260914" "codex/missing-validation-policy-review-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/parallel-scene-reservation-20260914" "codex/parallel-scene-reservation-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/viewer-instructions-20260914" "codex/viewer-instructions-20260914" 2>$null
git -C $R update-ref "refs/archive/assistant/graph-team-startup-20260913" "assistant/graph-team-startup-20260913" 2>$null
git -C $R update-ref "refs/archive/integration/graph-team-startup-20260914" "integration/graph-team-startup-20260914" 2>$null
git -C $R update-ref "refs/archive/assistant/enemy-eight-direction-contract" "assistant/enemy-eight-direction-contract" 2>$null
git -C $R update-ref "refs/archive/assistant/viewer-external-active" "assistant/viewer-external-active" 2>$null
git -C $R update-ref "refs/archive/assistant-control-main-20260912" "assistant-control-main-20260912" 2>$null
git -C $R update-ref "refs/archive/codex/claude-decomposition-guidance-main-20260914" "codex/claude-decomposition-guidance-main-20260914" 2>$null
git -C $R update-ref "refs/archive/assistant/review-wizard-rooms" "assistant/review-wizard-rooms" 2>$null
git -C $R update-ref "refs/archive/assistant/d4-grounding-hotfix" "assistant/d4-grounding-hotfix" 2>$null
git -C $R update-ref "refs/archive/assistant/d4-final-room-opening-hotfix" "assistant/d4-final-room-opening-hotfix" 2>$null
git -C $R update-ref "refs/archive/assistant/door-ui-sorting-hotfix" "assistant/door-ui-sorting-hotfix" 2>$null
git -C $R update-ref "refs/archive/assistant/five-room-wizard-review" "assistant/five-room-wizard-review" 2>$null
git -C $R update-ref "refs/archive/assistant/game-wizard-room-candidate" "assistant/game-wizard-room-candidate" 2>$null
git -C $R update-ref "refs/archive/codex/proved-decomp-guidance-main-20260914" "codex/proved-decomp-guidance-main-20260914" 2>$null
git -C $R update-ref "refs/archive/codex/nsc-new-file-scope-repair" "codex/nsc-new-file-scope-repair" 2>$null
git -C $R update-ref "refs/archive/codex/remove-blocking-audits" "codex/remove-blocking-audits" 2>$null
git -C $R update-ref "refs/archive/assistant/room-composition-a" "assistant/room-composition-a" 2>$null
git -C $R update-ref "refs/archive/assistant/room-composition-b" "assistant/room-composition-b" 2>$null
git -C $R update-ref "refs/archive/assistant/review-five-rooms" "assistant/review-five-rooms" 2>$null
git -C $R update-ref "refs/archive/assistant/wizard-cardinal-walk-graph" "assistant/wizard-cardinal-walk-graph" 2>$null
git -C $R update-ref "refs/archive/assistant/fix-exact-worker-scope" "assistant/fix-exact-worker-scope" 2>$null
git -C $R update-ref "refs/archive/assistant/world-multiscene-graph" "assistant/world-multiscene-graph" 2>$null
git -C $R update-ref "refs/archive/pipeline/narrow-doorprototype-builder-commit-20260902-025121" "pipeline/narrow-doorprototype-builder-commit-20260902-025121" 2>$null
git -C $R update-ref "refs/archive/release/public-policy-scope-731" "release/public-policy-scope-731" 2>$null
git -C $R update-ref "refs/archive/codex/ger-held-viewer-20260914" "codex/ger-held-viewer-20260914" 2>$null
git -C $R update-ref "refs/archive/viewer-held-overlay" "viewer-held-overlay" 2>$null
git -C $R update-ref "refs/archive/assistant/assistantcontrol-preparation" "assistant/assistantcontrol-preparation" 2>$null
git -C $R update-ref "refs/archive/docs/ger-agent-runbook-20260914" "docs/ger-agent-runbook-20260914" 2>$null

git -C $R worktree remove "C:\NSC\_worktrees\conformance-cherrypick-content-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\conformance-cherrypick-content-20260914" } else { git -C $R branch -D "codex/conformance-cherry-pick-content-20260914" }
git -C $R worktree remove "C:\NSC\_worktrees\enemy-eight-direction-integration-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\enemy-eight-direction-integration-20260914" } else { git -C $R branch -D "codex/enemy-eight-direction-integration-20260914" }
git -C $R worktree remove "C:\NSC\_worktrees\ger-active-viewer"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\ger-active-viewer" } else { git -C $R branch -D "codex/ger-active-viewer-20260914" }
git -C $R worktree remove "C:\NSC\_worktrees\missing-validation-policy-review"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\missing-validation-policy-review" } else { git -C $R branch -D "codex/missing-validation-policy-review-20260914" }
git -C $R worktree remove "C:\NSC\_worktrees\parallel-scene-reservation-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\parallel-scene-reservation-20260914" } else { git -C $R branch -D "codex/parallel-scene-reservation-20260914" }
git -C $R worktree remove "C:\NSC\_worktrees\viewer-instructions-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\_worktrees\viewer-instructions-20260914" } else { git -C $R branch -D "codex/viewer-instructions-20260914" }
git -C $R worktree remove "C:\NSC\GraphTeamStartup-20260913"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\GraphTeamStartup-20260913" } else { git -C $R branch -D "assistant/graph-team-startup-20260913" }
git -C $R worktree remove "C:\NSC\GraphTeamStartupIntegration-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\GraphTeamStartupIntegration-20260914" } else { git -C $R branch -D "integration/graph-team-startup-20260914" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-AssistantCheckouts\enemy-eight-direction-contract"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-AssistantCheckouts\enemy-eight-direction-contract" } else { git -C $R branch -D "assistant/enemy-eight-direction-contract" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-AssistantCheckouts\viewer-external-active"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-AssistantCheckouts\viewer-external-active" } else { git -C $R branch -D "assistant/viewer-external-active" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-AssistantControl-CI-20260912"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-AssistantControl-CI-20260912" } else { git -C $R branch -D "assistant-control-main-20260912" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-ClaudeGuidancePort-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-ClaudeGuidancePort-20260914" } else { git -C $R branch -D "codex/claude-decomposition-guidance-main-20260914" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Combined-Review"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Combined-Review" } else { git -C $R branch -D "assistant/review-wizard-rooms" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-D4-Grounding-Hotfix"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-D4-Grounding-Hotfix" } else { git -C $R branch -D "assistant/d4-grounding-hotfix" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-D4-Opening-Hotfix"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-D4-Opening-Hotfix" } else { git -C $R branch -D "assistant/d4-final-room-opening-hotfix" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Door-UI-Sorting-Hotfix"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Door-UI-Sorting-Hotfix" } else { git -C $R branch -D "assistant/door-ui-sorting-hotfix" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-FiveRoom-Wizard-Review"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-FiveRoom-Wizard-Review" } else { git -C $R branch -D "assistant/five-room-wizard-review" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Game-Candidate"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Game-Candidate" } else { git -C $R branch -D "assistant/game-wizard-room-candidate" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-GuidanceIntegration-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-GuidanceIntegration-20260914" } else { git -C $R branch -D "codex/proved-decomp-guidance-main-20260914" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-NewFileScopeRepair"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-NewFileScopeRepair" } else { git -C $R branch -D "codex/nsc-new-file-scope-repair" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-RemoveAudits"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-RemoveAudits" } else { git -C $R branch -D "codex/remove-blocking-audits" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Room-Composition-A"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Room-Composition-A" } else { git -C $R branch -D "assistant/room-composition-a" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Room-Composition-B"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Room-Composition-B" } else { git -C $R branch -D "assistant/room-composition-b" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Rooms-Combined-Candidate"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Rooms-Combined-Candidate" } else { git -C $R branch -D "assistant/review-five-rooms" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-Wizard-Cardinal-Graph"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-Wizard-Cardinal-Graph" } else { git -C $R branch -D "assistant/wizard-cardinal-walk-graph" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-WorkerScope-Enforcement"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-WorkerScope-Enforcement" } else { git -C $R branch -D "assistant/fix-exact-worker-scope" }
git -C $R worktree remove "C:\NSC\NoSafeCircle-World-Multiscene-Graph"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NoSafeCircle-World-Multiscene-Graph" } else { git -C $R branch -D "assistant/world-multiscene-graph" }
git -C $R worktree remove "C:\NSC\NSC\NarrowDoorPrototypeBuilder-20260902-025121"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\NSC\NarrowDoorPrototypeBuilder-20260902-025121" } else { git -C $R branch -D "pipeline/narrow-doorprototype-builder-commit-20260902-025121" }
git -C $R worktree remove "C:\NSC\ReleasePublicPolicyFix731"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\ReleasePublicPolicyFix731" } else { git -C $R branch -D "release/public-policy-scope-731" }
git -C $R worktree remove "C:\NSC\viewer-held-live"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\viewer-held-live" } else { git -C $R branch -D "codex/ger-held-viewer-20260914" }
git -C $R worktree remove "C:\NSC\viewer-held-overlay"
if ($LASTEXITCODE -ne 0) { $failed += "C:\NSC\viewer-held-overlay" } else { git -C $R branch -D "viewer-held-overlay" }
git -C $R worktree remove "C:\nscrev\AssistantControlPreparation-20260913"
if ($LASTEXITCODE -ne 0) { $failed += "C:\nscrev\AssistantControlPreparation-20260913" } else { git -C $R branch -D "assistant/assistantcontrol-preparation" }
git -C $R worktree remove "C:\nscrev\ger-agent-runbook-20260914"
if ($LASTEXITCODE -ne 0) { $failed += "C:\nscrev\ger-agent-runbook-20260914" } else { git -C $R branch -D "docs/ger-agent-runbook-20260914" }

git -C $R worktree prune
"worktrees left: {0}" -f (git -C $R worktree list | Measure-Object -Line).Lines
"local branches left: {0}" -f (git -C $R branch --format="%(refname:short)" | Measure-Object -Line).Lines
if ($failed.Count) { "NOT removed (uncommitted work or in use):"; $failed | ForEach-Object { "  $_" } }
