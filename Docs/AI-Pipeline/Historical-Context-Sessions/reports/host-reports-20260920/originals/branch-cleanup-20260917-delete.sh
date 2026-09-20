#!/usr/bin/env bash
# Branch cleanup planned by the Game Agent, 2026-09-17. Run from anywhere with Git Bash.
# Each branch below has every commit in local main already (ancestry or patch-equivalent).
# Step 1 saves the tip under refs/archive/<branch>, step 2 deletes the local branch.
# Remote branches are NOT touched here: deleting those is a push, which the Release Agent owns.
set -u
R=C:/NSC/NSC/NoSafeCircle

git -C "$R" update-ref "refs/archive/adversarial-architecture-review" "adversarial-architecture-review" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/adversarial-architecture-review-resume-temp" "adversarial-architecture-review-resume-temp" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assignment-4-RAG" "assignment-4-RAG" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assignment-5-goal-oriented-agent" "assignment-5-goal-oriented-agent" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assignment-6-GER" "assignment-6-GER" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assignment-7-style-guide-agent" "assignment-7-style-guide-agent" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assignment3-agent-crew" "assignment3-agent-crew" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant-control-main-20260912" "assistant-control-main-20260912" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/assistantcontrol-preparation" "assistant/assistantcontrol-preparation" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/d4-final-room-opening-hotfix" "assistant/d4-final-room-opening-hotfix" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/d4-grounding-hotfix" "assistant/d4-grounding-hotfix" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/door-ui-sorting-hotfix" "assistant/door-ui-sorting-hotfix" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/enemy-eight-direction-contract" "assistant/enemy-eight-direction-contract" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/five-room-wizard-review" "assistant/five-room-wizard-review" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/fix-exact-worker-scope" "assistant/fix-exact-worker-scope" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/game-wizard-room-candidate" "assistant/game-wizard-room-candidate" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/graph-team-startup-20260913" "assistant/graph-team-startup-20260913" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/integrate-background-throughput" "assistant/integrate-background-throughput" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/operator-stack-integration" "assistant/operator-stack-integration" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/review-five-rooms" "assistant/review-five-rooms" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/review-wizard-rooms" "assistant/review-wizard-rooms" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/room-composition-a" "assistant/room-composition-a" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/room-composition-b" "assistant/room-composition-b" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/taskreview-graph-preparation" "assistant/taskreview-graph-preparation" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/viewer-external-active" "assistant/viewer-external-active" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/wizard-cardinal-walk-graph" "assistant/wizard-cardinal-walk-graph" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/assistant/world-multiscene-graph" "assistant/world-multiscene-graph" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/ci/fix-stale-viewer-test-ids" "ci/fix-stale-viewer-test-ids" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/claude-decomposition-guidance-main-20260914" "codex/claude-decomposition-guidance-main-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/conformance-cherry-pick-content-20260914" "codex/conformance-cherry-pick-content-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/enemy-eight-direction-integration-20260914" "codex/enemy-eight-direction-integration-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/ger-active-viewer-20260914" "codex/ger-active-viewer-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/ger-held-viewer-20260914" "codex/ger-held-viewer-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/missing-validation-policy-review-20260914" "codex/missing-validation-policy-review-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/nsc-new-file-scope-repair" "codex/nsc-new-file-scope-repair" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/parallel-scene-reservation-20260914" "codex/parallel-scene-reservation-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/proved-decomp-guidance-main-20260914" "codex/proved-decomp-guidance-main-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/remove-blocking-audits" "codex/remove-blocking-audits" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/codex/viewer-instructions-20260914" "codex/viewer-instructions-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/contracts/rerun-door-and-ranged-decompositions" "contracts/rerun-door-and-ranged-decompositions" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/delivery-evidence-packager" "delivery-evidence-packager" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/design/stage5-decomposition-audit" "design/stage5-decomposition-audit" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs-game-task-fast-start" "docs-game-task-fast-start" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/agent-job-directory-standard" "docs/agent-job-directory-standard" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/agent-prompt-runner-rules" "docs/agent-prompt-runner-rules" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/canonical-mutation-api-precedence" "docs/canonical-mutation-api-precedence" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/context-2026-09-01-architect-integration" "docs/context-2026-09-01-architect-integration" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/current-pipeline-after-d1b2" "docs/current-pipeline-after-d1b2" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/fix-agent-job-directory-compose-volume" "docs/fix-agent-job-directory-compose-volume" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/ger-agent-runbook-20260914" "docs/ger-agent-runbook-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/mandatory-parallel-chatgpt-orchestration" "docs/mandatory-parallel-chatgpt-orchestration" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/needs-testing-nonblocking-dependencies" "docs/needs-testing-nonblocking-dependencies" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/operator-command-template" "docs/operator-command-template" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/orchestrator-use-taskcontrol-states" "docs/orchestrator-use-taskcontrol-states" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/retry-and-decomposition-work" "docs/retry-and-decomposition-work" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/task-checkout-path-convention" "docs/task-checkout-path-convention" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/taskgraph-github-state-sync" "docs/taskgraph-github-state-sync" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/docs/unity-programmer-language" "docs/unity-programmer-language" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/document-current-task-acceleration-state" "document-current-task-acceleration-state" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/draft-evidence-validator" "draft-evidence-validator" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/executioncrew-approved-new-files" "executioncrew-approved-new-files" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/executioncrew-footer" "executioncrew-footer" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix-codex-jsonl-blank-lines" "fix-codex-jsonl-blank-lines" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix-codex-jsonl-web-search-duplicate-id" "fix-codex-jsonl-web-search-duplicate-id" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix-live-claude-visibility" "fix-live-claude-visibility" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/builder-tests-spawn-camera-20260917" "fix/builder-tests-spawn-camera-20260917" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/ci-134" "fix/ci-134" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/codex-supervisor-cli-model-and-diagnostics" "fix/codex-supervisor-cli-model-and-diagnostics" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/docker-permission-probe-lf" "fix/docker-permission-probe-lf" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/github-read-after-write-verification" "fix/github-read-after-write-verification" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/historical-context-policy-exclusions" "fix/historical-context-policy-exclusions" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/historical-context-scene-policy" "fix/historical-context-scene-policy" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/historical-context-scene-policy-regression" "fix/historical-context-scene-policy-regression" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/host-controller-worker-boundary-v1" "fix/host-controller-worker-boundary-v1" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/latest-effective-pr-checks" "fix/latest-effective-pr-checks" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/stage2-state-observation-scaling" "fix/stage2-state-observation-scaling" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/stub-meta-texture" "fix/stub-meta-texture" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/task-agent-checkout-recovery-circuit-breaker" "fix/task-agent-checkout-recovery-circuit-breaker" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/task-agent-host-python-utf8" "fix/task-agent-host-python-utf8" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/task-agent-live-progress-logging" "fix/task-agent-live-progress-logging" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/task-supervisor-external-codex-volume" "fix/task-supervisor-external-codex-volume" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/taskreviewagent-read-after-write-completion" "fix/taskreviewagent-read-after-write-completion" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/unity-generated-whitespace" "fix/unity-generated-whitespace" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/fix/windows-powershell-native-stderr" "fix/windows-powershell-native-stderr" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/generic-get-work-stage0-safety" "generic-get-work-stage0-safety" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/generic-get-work-stage1-atomic-claims" "generic-get-work-stage1-atomic-claims" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/generic-get-work-stage2-dispatch-plan" "generic-get-work-stage2-dispatch-plan" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/generic-get-work-stage3-fresh-dispatch" "generic-get-work-stage3-fresh-dispatch" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/generic-get-work-stage4-contention-retry" "generic-get-work-stage4-contention-retry" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/history-migration-executor-one-shot" "history-migration-executor-one-shot" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/homework/webgl-setup" "homework/webgl-setup" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/integration/graph-team-startup-20260914" "integration/graph-team-startup-20260914" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/integration/public-orchestration-final-20260908" "integration/public-orchestration-final-20260908" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/milestone-1-task-graph" "milestone-1-task-graph" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/milestone-2a-current-gdd-rag" "milestone-2a-current-gdd-rag" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/origin" "origin" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/phase-3-evidence-derived-conformance" "phase-3-evidence-derived-conformance" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/canonical-scene-paths" "pipeline/canonical-scene-paths" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/canonical-short-windows-root" "pipeline/canonical-short-windows-root" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/ci-impact-routing" "pipeline/ci-impact-routing" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/conformance-canon-granularity" "pipeline/conformance-canon-granularity" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/d1b2-gddrag-review-context" "pipeline/d1b2-gddrag-review-context" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/d1b2-round-robin-decomposition" "pipeline/d1b2-round-robin-decomposition" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/decomposition-aggregate-semantics" "pipeline/decomposition-aggregate-semantics" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/github-ticket-orchestration-mvp" "pipeline/github-ticket-orchestration-mvp" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/history-identity-migration-v2" "pipeline/history-identity-migration-v2" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/mainline-reintegration-conditional-revalidation" "pipeline/mainline-reintegration-conditional-revalidation" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/narrow-doorprototype-builder-commit-20260902-025121" "pipeline/narrow-doorprototype-builder-commit-20260902-025121" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/narrow-doorprototype-builder-commit-20260902-025607" "pipeline/narrow-doorprototype-builder-commit-20260902-025607" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/pre-handoff-unity-generation-hygiene-20260902-004901" "pipeline/pre-handoff-unity-generation-hygiene-20260902-004901" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/task-review-agent-vertical-slice" "pipeline/task-review-agent-vertical-slice" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/task-review-agent-vertical-slice-v1" "pipeline/task-review-agent-vertical-slice-v1" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/task-to-test-stage1" "pipeline/task-to-test-stage1" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/taskcontrol-states" "pipeline/taskcontrol-states" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/pipeline/taskreview-ci-split" "pipeline/taskreview-ci-split" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/provider-adapters" "provider-adapters" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/provider-neutral-execution-crew" "provider-neutral-execution-crew" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/release-ci/main-40a596c" "release-ci/main-40a596c" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/release-ci/main-46dd7cd09" "release-ci/main-46dd7cd09" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/release/public-policy-scope-731" "release/public-policy-scope-731" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/review/orchestration-gauntlet-followup-integration" "review/orchestration-gauntlet-followup-integration" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/stage-d1-task-decomposition" "stage-d1-task-decomposition" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/stage-d1b-live-decomposition" "stage-d1b-live-decomposition" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/stage3-ci-routing-regression" "stage3-ci-routing-regression" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/stage4-repository-binding-safety" "stage4-repository-binding-safety" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/streaming-verification-refinement" "streaming-verification-refinement" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/task-contract-schema-v2" "task-contract-schema-v2" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/taskgraph-resource-group-repair" "taskgraph-resource-group-repair" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/validation-manifest-delivery-spec" "validation-manifest-delivery-spec" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/verify/door-crossing-20260915" "verify/door-crossing-20260915" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/verify/wave3-pipeline-20260915" "verify/wave3-pipeline-20260915" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/viewer-held-overlay" "viewer-held-overlay" 2>/dev/null || true
git -C "$R" update-ref "refs/archive/wizard-art/codex-20260915" "wizard-art/codex-20260915" 2>/dev/null || true

git -C "$R" branch -D "adversarial-architecture-review"
git -C "$R" branch -D "assignment-4-RAG"
git -C "$R" branch -D "assignment-5-goal-oriented-agent"
git -C "$R" branch -D "assignment-6-GER"
git -C "$R" branch -D "assignment-7-style-guide-agent"
git -C "$R" branch -D "assignment3-agent-crew"
git -C "$R" branch -D "assistant-control-main-20260912"
git -C "$R" branch -D "assistant/assistantcontrol-preparation"
git -C "$R" branch -D "assistant/d4-final-room-opening-hotfix"
git -C "$R" branch -D "assistant/d4-grounding-hotfix"
git -C "$R" branch -D "assistant/door-ui-sorting-hotfix"
git -C "$R" branch -D "assistant/enemy-eight-direction-contract"
git -C "$R" branch -D "assistant/five-room-wizard-review"
git -C "$R" branch -D "assistant/fix-exact-worker-scope"
git -C "$R" branch -D "assistant/game-wizard-room-candidate"
git -C "$R" branch -D "assistant/graph-team-startup-20260913"
git -C "$R" branch -D "assistant/integrate-background-throughput"
git -C "$R" branch -D "assistant/operator-stack-integration"
git -C "$R" branch -D "assistant/review-five-rooms"
git -C "$R" branch -D "assistant/review-wizard-rooms"
git -C "$R" branch -D "assistant/room-composition-a"
git -C "$R" branch -D "assistant/room-composition-b"
git -C "$R" branch -D "assistant/taskreview-graph-preparation"
git -C "$R" branch -D "assistant/viewer-external-active"
git -C "$R" branch -D "assistant/wizard-cardinal-walk-graph"
git -C "$R" branch -D "assistant/world-multiscene-graph"
git -C "$R" branch -D "codex/claude-decomposition-guidance-main-20260914"
git -C "$R" branch -D "codex/conformance-cherry-pick-content-20260914"
git -C "$R" branch -D "codex/enemy-eight-direction-integration-20260914"
git -C "$R" branch -D "codex/ger-active-viewer-20260914"
git -C "$R" branch -D "codex/ger-held-viewer-20260914"
git -C "$R" branch -D "codex/missing-validation-policy-review-20260914"
git -C "$R" branch -D "codex/nsc-new-file-scope-repair"
git -C "$R" branch -D "codex/parallel-scene-reservation-20260914"
git -C "$R" branch -D "codex/proved-decomp-guidance-main-20260914"
git -C "$R" branch -D "codex/remove-blocking-audits"
git -C "$R" branch -D "codex/viewer-instructions-20260914"
git -C "$R" branch -D "delivery-evidence-packager"
git -C "$R" branch -D "design/stage5-decomposition-audit"
git -C "$R" branch -D "docs/ger-agent-runbook-20260914"
git -C "$R" branch -D "draft-evidence-validator"
git -C "$R" branch -D "executioncrew-footer"
git -C "$R" branch -D "fix/builder-tests-spawn-camera-20260917"
git -C "$R" branch -D "fix/ci-134"
git -C "$R" branch -D "fix/github-read-after-write-verification"
git -C "$R" branch -D "fix/historical-context-scene-policy"
git -C "$R" branch -D "fix/latest-effective-pr-checks"
git -C "$R" branch -D "fix/stub-meta-texture"
git -C "$R" branch -D "generic-get-work-stage0-safety"
git -C "$R" branch -D "generic-get-work-stage1-atomic-claims"
git -C "$R" branch -D "generic-get-work-stage2-dispatch-plan"
git -C "$R" branch -D "generic-get-work-stage3-fresh-dispatch"
git -C "$R" branch -D "generic-get-work-stage4-contention-retry"
git -C "$R" branch -D "homework/webgl-setup"
git -C "$R" branch -D "integration/graph-team-startup-20260914"
git -C "$R" branch -D "milestone-1-task-graph"
git -C "$R" branch -D "milestone-2a-current-gdd-rag"
git -C "$R" branch -D "phase-3-evidence-derived-conformance"
git -C "$R" branch -D "pipeline/canonical-short-windows-root"
git -C "$R" branch -D "pipeline/ci-impact-routing"
git -C "$R" branch -D "pipeline/history-identity-migration-v2"
git -C "$R" branch -D "pipeline/narrow-doorprototype-builder-commit-20260902-025121"
git -C "$R" branch -D "pipeline/narrow-doorprototype-builder-commit-20260902-025607"
git -C "$R" branch -D "pipeline/taskreview-ci-split"
git -C "$R" branch -D "provider-adapters"
git -C "$R" branch -D "provider-neutral-execution-crew"
git -C "$R" branch -D "release/public-policy-scope-731"
git -C "$R" branch -D "stage-d1-task-decomposition"
git -C "$R" branch -D "stage3-ci-routing-regression"
git -C "$R" branch -D "stage4-repository-binding-safety"
git -C "$R" branch -D "streaming-verification-refinement"
git -C "$R" branch -D "task-contract-schema-v2"
git -C "$R" branch -D "taskgraph-resource-group-repair"
git -C "$R" branch -D "verify/door-crossing-20260915"
git -C "$R" branch -D "verify/wave3-pipeline-20260915"
git -C "$R" branch -D "viewer-held-overlay"
git -C "$R" branch -D "wizard-art/codex-20260915"

echo "remaining local branches: $(git -C "$R" branch --format=%(refname:short) | wc -l)"
