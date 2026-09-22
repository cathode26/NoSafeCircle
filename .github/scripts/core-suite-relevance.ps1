# The Core relevance classifier, defined ONCE and called by every
# windows-smoke job's `scope` step.
#
# It used to be copy-pasted into each job by the four-way rebalance: four
# identical allowlists to keep in sync by hand, and a regression test that
# mutates the delivery-evidence prefix could no longer find exactly one to
# mutate. A script rather than a separate scope job, so there is no extra
# checkout, no runner dependency, and none of `needs:`'s skip semantics.
#
# Writes run_full_core to GITHUB_OUTPUT exactly as before, so every step's
# `if: steps.scope.outputs.run_full_core == 'true'` is unaffected.
param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$BaseSha)

# Files owned exclusively by Supervisor or Delivery Validation.
# Kept identical to their paths: blocks in
# task-review-agent-supervisor.yml / task-review-agent-delivery.yml.
# A future/unknown file is never in this list, so it fails safe by
# keeping the full Core suite selected.
$ownedByOtherSuites = @(
  "Pipeline/TaskReviewAgent/codex_supervisor.py",
  "Pipeline/TaskReviewAgent/codex_supervisor_turn.py",
  "Pipeline/TaskReviewAgent/goal_loop_guard.py",
  "Pipeline/TaskReviewAgent/operator_logging.py",
  "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1",
  "Pipeline/TaskReviewAgent/NativeCommand.ps1",
  "Pipeline/TaskReviewAgent/openai_downstream.py",
  "Pipeline/TaskReviewAgent/openai_pipeline.py",
  "Pipeline/TaskReviewAgent/delivery_review.py",
  "Pipeline/TaskReviewAgent/downstream_action_grounding.py",
  "Pipeline/TaskReviewAgent/downstream_determinism.py",
  "Pipeline/TaskReviewAgent/downstream_issue.py",
  "Pipeline/TaskReviewAgent/downstream_pipeline.py",
  "Pipeline/TaskReviewAgent/downstream_resilience.py",
  "Pipeline/TaskReviewAgent/downstream_runtime.py",
  "Pipeline/TaskReviewAgent/mainline_reintegration.py",
  "Pipeline/TaskReviewAgent/merge_closeout_check_repoll.py",
  "Pipeline/TaskReviewAgent/production_pipeline.py",
  "Pipeline/TaskReviewAgent/candidate_integration.py",
  "Pipeline/TaskReviewAgent/execution_bridge.py",
  "Pipeline/TaskReviewAgent/pipeline_scope.py",
  "Pipeline/TaskReviewAgent/pull_request_check_authority.py",
  "Pipeline/TaskReviewAgent/tests/codex_supervisor_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/codex_supervisor_turn_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/compose_supervisor_volume_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/progress_logging_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/goal_loop_guard_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/native_command_smoke_test.ps1",
  "Pipeline/TaskReviewAgent/tests/delivery_review_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/downstream_action_grounding_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/downstream_determinism_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/downstream_issue_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/downstream_resilience_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/downstream_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/mainline_reintegration_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/merge_closeout_check_repoll_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/production_controller_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/production_pipeline_smoke_test.py",
  "Pipeline/TaskReviewAgent/tests/scene_path_contract_migration_smoke_test.py"
)

# Ordinary task delivery changes game/content surfaces plus immutable
# TaskGraph evidence, not the TaskReviewAgent implementation. The
# always-on split-regression, compile, and whitespace steps below
# still run, and D1B.2 independently validates persistent TaskGraph
# evidence. Keep this prefix list narrow: Tasks/**, pipeline code,
# workflow changes, and every unknown path still select full Core.
$ordinaryDeliveryPrefixes = @(
  "Assets/",
  "Pipeline/TaskGraph/evidence/"
)

$baseSha = $BaseSha
if ([string]::IsNullOrWhiteSpace($baseSha)) {
  Write-Host "No PR base SHA (e.g. workflow_dispatch); running the full Core suite."
  $runFullCore = $true
} else {
  $changed = git diff --name-only "$baseSha...HEAD"
  if ($LASTEXITCODE -ne 0) {
    # A classifier that could not read the diff must not conclude
    # 'nothing here is Core-relevant'.
    #
    # This changes no outcome today, and the honest version of
    # that is worth writing down: $LASTEXITCODE is still non-zero
    # at the end of this step, so the runner's trailing
    # `exit $LASTEXITCODE` (actions/runner ADR 0277, appended to
    # every builtin pwsh script) fails the job whichever way this
    # branch sets $runFullCore. That is why a failed diff was
    # never the silent skip it was reported to be -- measured, by
    # running this step under the runner's wrapper with a git
    # stub that exits 128.
    #
    # It is stated here because that protection is implicit and
    # ends the moment a native command runs below this line and
    # resets $LASTEXITCODE to 0. Splitting this job would do that.
    Write-Host "git diff against base SHA $baseSha failed (exit $LASTEXITCODE); selecting the full Core suite."
    $runFullCore = $true
  } else {
    $runFullCore = $false
    foreach ($path in $changed) {
      $ordinaryDelivery = $false
      foreach ($prefix in $ordinaryDeliveryPrefixes) {
        if ($path.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
          $ordinaryDelivery = $true
          break
        }
      }
      if (
        $ownedByOtherSuites -notcontains $path -and
        -not $ordinaryDelivery
      ) {
        Write-Host "Core-relevant change: $path"
        $runFullCore = $true
      }
    }
  }
}

if ($runFullCore) {
  Write-Host "Running the full Core regression suite."
} else {
  Write-Host "Every changed file is suite-owned or ordinary task delivery; skipping the expensive Core suite cheaply."
}
"run_full_core=$($runFullCore.ToString().ToLower())" | Out-File -FilePath $env:GITHUB_OUTPUT -Append
