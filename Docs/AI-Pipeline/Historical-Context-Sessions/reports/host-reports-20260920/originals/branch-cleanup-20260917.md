# Branch cleanup plan (2026-09-17)

Merged means main already holds every commit of the branch, by ancestry or as an equivalent
patch (`git cherry`). Main has moved on since most of these, so a file diff against main is
not a containment test and is not used here.

- branches examined (local or origin, excluding main): 272
- merged and NSC-### named: 96, covering 46 tasks
- merged, other names: 133
- not merged, keep: 43

## Merged NSC-### branches: archive the task, keep the branch

- **NSC-003**: `milestone-2a-nsc-003-context`
- **NSC-005**: `nsc-005-feedback-fix`
- **NSC-011**: `nsc-011-active-enemy-registry`
- **NSC-013**: `codex/nsc013-final-main-20260914`, `codex/nsc013-main-ready-20260914`, `codex/nsc013-provisional-20260914`, `codex/nsc013-validation-20260914`, `codex/nsc013-validation2-20260914`
- **NSC-016**: `taskgraph/nsc-016-audit-corrected-decomposition`
- **NSC-017**: `codex/nsc017-locked-door-attack-20260914`, `verify/nsc017-locked-door-20260915`
- **NSC-021**: `taskgraph/nsc-021-approved-decomposition`, `taskgraph/nsc-021-audit-corrected-decomposition`
- **NSC-024**: `nsc-024-tilemap-navigation-package-configuration`
- **NSC-025**: `taskgraph/nsc-025-canonical-scene-resource`
- **NSC-026**: `decompose-nsc-026-world-visual-foundation`
- **NSC-028**: `codex/nsc028-cap-recovery-20260914`, `nsc-028-encounter-admission-cap`
- **NSC-029**: `nsc-029-reviewed-room-decomposition`
- **NSC-032**: `codex/nsc032-current-main-recovery-20260914`
- **NSC-038**: `nsc-038-human-repair`
- **NSC-039**: `nsc-039-world-sprite-prefab-sorting`
- **NSC-042**: `codex/nsc042-delivery-20260914`, `codex/nsc042-evidence-handoff-20260914`, `docs/nsc042-wall-tiling-standard`
- **NSC-043**: `author-nsc-043-webgl-build-artifact`
- **NSC-044**: `assistant/room-nsc-044`, `codex/nsc044-capture-fix-stage-20260914`, `codex/nsc044-current-main-stage-20260914`, `codex/nsc044-ger-room-20260914`
- **NSC-046**: `assistant/nsc-046-chapel`
- **NSC-047**: `assistant/nsc-047-vault`
- **NSC-048**: `assistant/nsc-048-final`
- **NSC-049**: `assistant/nsc-049-room-composition`
- **NSC-050**: `assistant/NSC-050`, `codex/nsc050-052-current-main-integration-20260914`, `codex/nsc050-current-main-20260914`
- **NSC-051**: `codex/nsc051-door-passability-20260914`, `codex/nsc051-final-main-20260914`
- **NSC-052**: `codex/nsc052-current-main-stage-20260914`, `codex/nsc052-val003-20260914`, `codex/nsc052-verification-20260914`
- **NSC-053**: `codex/nsc053-keep-distance-20260914`, `verify/nsc053-keep-distance-20260915`
- **NSC-057**: `codex/nsc057-tooling-20260914`
- **NSC-058**: `codex/nsc058-hierarchy-fader-20260914`, `codex/nsc058-main-stage-20260914`
- **NSC-060**: `assistant/NSC-060`, `codex/nsc060-current-main-20260914`, `codex/nsc060-lifecycle-validation-20260914`, `codex/nsc060-main-integration-20260914`
- **NSC-061**: `nsc-061-pixellab-wizard-art-selection`
- **NSC-062**: `nsc-062-animated-wizard-unity-integration`
- **NSC-063**: `assistant/nsc063-nsc093-ne-single-cleaver-20260916`, `codex/nsc063-art-recovery-20260914`, `codex/nsc063-current-main-revision-20260914`, `codex/nsc063-delivery-evidence-20260914`, `codex/nsc063-final-main-stage-20260914`, `codex/nsc063-pixellab-revision-20260914`, `codex/nsc063-retained-art-review-20260914`
- **NSC-065**: `codex/nsc065-main-stage-20260914`, `codex/nsc065-retained-art-review-20260914`, `codex/nsc065-source-delivery-20260914`
- **NSC-068**: `assistant/taskgraph-nsc-068`
- **NSC-069**: `assistant/fix-nsc-069-launch-scope`
- **NSC-070**: `assistant/integrate-nsc-070`, `assistant/nsc-070-runtime-stability`
- **NSC-071**: `release/policy-nsc071-40a`
- **NSC-073**: `assistant/NSC-073-current`, `assistant/nsc-073-pixellab`, `codex/nsc073-alt-current-stage-20260914`, `codex/nsc073-main-validation-20260914`, `codex/nsc073-ne-alternate-20260914`, `codex/nsc073-reuse-alt-20260914`, `codex/nsc073-visual-stage-20260914`
- **NSC-074**: `assistant/NSC-074-current`
- **NSC-075**: `assistant/nsc-075-builder-prep`, `assistant/nsc-075-integration-prep`, `codex/nsc075-eight-direction-20260916`
- **NSC-077**: `assistant/nsc077-rev3-moving-enemy-art-20260916`, `codex/nsc077-moving-enemy-art-20260917`
- **NSC-089**: `assistant/NSC-089-editmode-path`, `codex/nsc089-main-validation-20260914`, `codex/nsc089-managed-recovery`, `nsc089-checkout-recovery`
- **NSC-090**: `codex/nsc090-main-ready-20260914`, `codex/nsc090-main-validation-20260914`
- **NSC-091**: `codex/nsc091-main-ready-20260914`, `codex/nsc091-provisional-20260914`
- **NSC-092**: `codex/nsc092-diagnostic-20260914`, `codex/nsc092-final-main-20260914`, `codex/nsc092-main-ready-20260914`, `codex/nsc092-obstacle-fix-20260914`, `codex/nsc092-provisional-20260914`
- **NSC-093**: `codex/nsc093-current-main-review-20260914`, `codex/nsc093-pixellab-walk-20260914`

## Merged, non-task branches: archive ref then delete

Script: `C:/nscrev/reports/branch-cleanup-20260917-delete.sh`

| branch | last commit | where |
|---|---|---|
| `adversarial-architecture-review` | 2026-08-21 | local+remote |
| `adversarial-architecture-review-resume-temp` | 2026-08-21 | +remote |
| `assignment-4-RAG` | 2026-08-06 | local+remote |
| `assignment-5-goal-oriented-agent` | 2026-08-13 | local+remote |
| `assignment-6-GER` | 2026-08-18 | local+remote |
| `assignment-7-style-guide-agent` | 2026-08-20 | local+remote |
| `assignment3-agent-crew` | 2026-08-04 | local+remote |
| `assistant-control-main-20260912` | 2026-09-12 | local |
| `assistant/assistantcontrol-preparation` | 2026-09-13 | local |
| `assistant/d4-final-room-opening-hotfix` | 2026-09-13 | local |
| `assistant/d4-grounding-hotfix` | 2026-09-13 | local |
| `assistant/door-ui-sorting-hotfix` | 2026-09-13 | local |
| `assistant/enemy-eight-direction-contract` | 2026-09-14 | local |
| `assistant/five-room-wizard-review` | 2026-09-13 | local |
| `assistant/fix-exact-worker-scope` | 2026-09-12 | local |
| `assistant/game-wizard-room-candidate` | 2026-09-13 | local |
| `assistant/graph-team-startup-20260913` | 2026-09-13 | local |
| `assistant/integrate-background-throughput` | 2026-09-12 | local |
| `assistant/operator-stack-integration` | 2026-09-13 | local |
| `assistant/review-five-rooms` | 2026-09-13 | local |
| `assistant/review-wizard-rooms` | 2026-09-13 | local |
| `assistant/room-composition-a` | 2026-09-13 | local |
| `assistant/room-composition-b` | 2026-09-13 | local |
| `assistant/taskreview-graph-preparation` | 2026-09-13 | local |
| `assistant/viewer-external-active` | 2026-09-14 | local |
| `assistant/wizard-cardinal-walk-graph` | 2026-09-13 | local |
| `assistant/world-multiscene-graph` | 2026-09-12 | local |
| `ci/fix-stale-viewer-test-ids` | 2026-09-17 | +remote |
| `codex/claude-decomposition-guidance-main-20260914` | 2026-09-13 | local |
| `codex/conformance-cherry-pick-content-20260914` | 2026-09-14 | local |
| `codex/enemy-eight-direction-integration-20260914` | 2026-09-14 | local |
| `codex/ger-active-viewer-20260914` | 2026-09-14 | local |
| `codex/ger-held-viewer-20260914` | 2026-09-14 | local |
| `codex/missing-validation-policy-review-20260914` | 2026-09-14 | local |
| `codex/nsc-new-file-scope-repair` | 2026-09-14 | local |
| `codex/parallel-scene-reservation-20260914` | 2026-09-14 | local |
| `codex/proved-decomp-guidance-main-20260914` | 2026-09-13 | local |
| `codex/remove-blocking-audits` | 2026-09-14 | local |
| `codex/viewer-instructions-20260914` | 2026-09-14 | local |
| `contracts/rerun-door-and-ranged-decompositions` | 2026-08-26 | +remote |
| `delivery-evidence-packager` | 2026-08-24 | local+remote |
| `design/stage5-decomposition-audit` | 2026-08-31 | local+remote |
| `docs-game-task-fast-start` | 2026-08-24 | +remote |
| `docs/agent-job-directory-standard` | 2026-09-01 | +remote |
| `docs/agent-prompt-runner-rules` | 2026-08-30 | +remote |
| `docs/canonical-mutation-api-precedence` | 2026-09-01 | +remote |
| `docs/context-2026-09-01-architect-integration` | 2026-09-01 | +remote |
| `docs/current-pipeline-after-d1b2` | 2026-08-26 | +remote |
| `docs/fix-agent-job-directory-compose-volume` | 2026-09-01 | +remote |
| `docs/ger-agent-runbook-20260914` | 2026-09-14 | local |
| `docs/mandatory-parallel-chatgpt-orchestration` | 2026-08-25 | +remote |
| `docs/needs-testing-nonblocking-dependencies` | 2026-08-25 | +remote |
| `docs/operator-command-template` | 2026-08-30 | +remote |
| `docs/orchestrator-use-taskcontrol-states` | 2026-08-25 | +remote |
| `docs/retry-and-decomposition-work` | 2026-08-25 | +remote |
| `docs/task-checkout-path-convention` | 2026-08-25 | +remote |
| `docs/taskgraph-github-state-sync` | 2026-08-25 | +remote |
| `docs/unity-programmer-language` | 2026-08-26 | +remote |
| `document-current-task-acceleration-state` | 2026-08-24 | +remote |
| `draft-evidence-validator` | 2026-08-24 | local+remote |
| `executioncrew-approved-new-files` | 2026-08-24 | +remote |
| `executioncrew-footer` | 2026-08-23 | local+remote |
| `fix-codex-jsonl-blank-lines` | 2026-08-24 | +remote |
| `fix-codex-jsonl-web-search-duplicate-id` | 2026-08-24 | +remote |
| `fix-live-claude-visibility` | 2026-08-25 | +remote |
| `fix/builder-tests-spawn-camera-20260917` | 2026-09-17 | local |
| `fix/ci-134` | 2026-09-17 | local |
| `fix/codex-supervisor-cli-model-and-diagnostics` | 2026-08-28 | +remote |
| `fix/docker-permission-probe-lf` | 2026-08-28 | +remote |
| `fix/github-read-after-write-verification` | 2026-08-30 | local+remote |
| `fix/historical-context-policy-exclusions` | 2026-08-30 | +remote |
| `fix/historical-context-scene-policy` | 2026-08-30 | local |
| `fix/historical-context-scene-policy-regression` | 2026-08-30 | +remote |
| `fix/host-controller-worker-boundary-v1` | 2026-09-01 | +remote |
| `fix/latest-effective-pr-checks` | 2026-08-29 | local |
| `fix/stage2-state-observation-scaling` | 2026-08-31 | +remote |
| `fix/stub-meta-texture` | 2026-09-17 | local |
| `fix/task-agent-checkout-recovery-circuit-breaker` | 2026-08-28 | +remote |
| `fix/task-agent-host-python-utf8` | 2026-08-28 | +remote |
| `fix/task-agent-live-progress-logging` | 2026-08-28 | +remote |
| `fix/task-supervisor-external-codex-volume` | 2026-08-28 | +remote |
| `fix/taskreviewagent-read-after-write-completion` | 2026-08-31 | +remote |
| `fix/unity-generated-whitespace` | 2026-09-17 | +remote |
| `fix/windows-powershell-native-stderr` | 2026-08-28 | +remote |
| `generic-get-work-stage0-safety` | 2026-08-29 | local+remote |
| `generic-get-work-stage1-atomic-claims` | 2026-08-30 | local+remote |
| `generic-get-work-stage2-dispatch-plan` | 2026-08-30 | local+remote |
| `generic-get-work-stage3-fresh-dispatch` | 2026-08-30 | local+remote |
| `generic-get-work-stage4-contention-retry` | 2026-08-30 | local+remote |
| `history-migration-executor-one-shot` | 2026-08-29 | +remote |
| `homework/webgl-setup` | 2026-09-02 | local+remote |
| `integration/graph-team-startup-20260914` | 2026-09-13 | local |
| `integration/public-orchestration-final-20260908` | 2026-09-07 | +remote |
| `milestone-1-task-graph` | 2026-08-21 | local+remote |
| `milestone-2a-current-gdd-rag` | 2026-08-21 | local+remote |
| `origin` | 2026-09-14 | +remote |
| `phase-3-evidence-derived-conformance` | 2026-08-22 | local+remote |
| `pipeline/canonical-scene-paths` | 2026-08-28 | +remote |
| `pipeline/canonical-short-windows-root` | 2026-08-29 | local+remote |
| `pipeline/ci-impact-routing` | 2026-08-29 | local+remote |
| `pipeline/conformance-canon-granularity` | 2026-08-25 | +remote |
| `pipeline/d1b2-gddrag-review-context` | 2026-08-27 | +remote |
| `pipeline/d1b2-round-robin-decomposition` | 2026-08-26 | +remote |
| `pipeline/decomposition-aggregate-semantics` | 2026-08-26 | +remote |
| `pipeline/github-ticket-orchestration-mvp` | 2026-08-25 | +remote |
| `pipeline/history-identity-migration-v2` | 2026-08-29 | local |
| `pipeline/mainline-reintegration-conditional-revalidation` | 2026-08-28 | +remote |
| `pipeline/narrow-doorprototype-builder-commit-20260902-025121` | 2026-09-01 | local |
| `pipeline/narrow-doorprototype-builder-commit-20260902-025607` | 2026-09-02 | local |
| `pipeline/pre-handoff-unity-generation-hygiene-20260902-004901` | 2026-09-02 | +remote |
| `pipeline/task-review-agent-vertical-slice` | 2026-08-27 | +remote |
| `pipeline/task-review-agent-vertical-slice-v1` | 2026-08-28 | +remote |
| `pipeline/task-to-test-stage1` | 2026-08-27 | +remote |
| `pipeline/taskcontrol-states` | 2026-08-25 | +remote |
| `pipeline/taskreview-ci-split` | 2026-08-29 | local+remote |
| `provider-adapters` | 2026-08-23 | local+remote |
| `provider-neutral-execution-crew` | 2026-08-22 | local+remote |
| `release-ci/main-40a596c` | 2026-09-14 | +remote |
| `release-ci/main-46dd7cd09` | 2026-09-17 | +remote |
| `release/public-policy-scope-731` | 2026-09-14 | local+remote |
| `review/orchestration-gauntlet-followup-integration` | 2026-09-05 | +remote |
| `stage-d1-task-decomposition` | 2026-08-23 | local+remote |
| `stage-d1b-live-decomposition` | 2026-08-24 | +remote |
| `stage3-ci-routing-regression` | 2026-08-30 | local+remote |
| `stage4-repository-binding-safety` | 2026-08-30 | local+remote |
| `streaming-verification-refinement` | 2026-08-21 | local+remote |
| `task-contract-schema-v2` | 2026-08-21 | local+remote |
| `taskgraph-resource-group-repair` | 2026-08-24 | local+remote |
| `validation-manifest-delivery-spec` | 2026-08-24 | +remote |
| `verify/door-crossing-20260915` | 2026-09-15 | local |
| `verify/wave3-pipeline-20260915` | 2026-09-15 | local |
| `viewer-held-overlay` | 2026-09-14 | local |
| `wizard-art/codex-20260915` | 2026-09-15 | local |

## Not merged: keep for triage

| branch | last commit | where |
|---|---|---|
| `assistant-ci-boundary-20260912` | 2026-09-12 | local+remote |
| `assistant/cardinal-staging` | 2026-09-13 | local+remote |
| `assistant/foreground-nsc-062-materialization` | 2026-09-12 | local+remote |
| `assistant/foreground-nsc-066-title-screen` | 2026-09-12 | local+remote |
| `assistant/foreground-nsc-067-selection` | 2026-09-12 | local+remote |
| `assistant/integrate-background-plus-decomp` | 2026-09-13 | local+remote |
| `assistant/nsc-074-cardinal-art` | 2026-09-13 | local+remote |
| `assistant/restored-meta-companion-fix` | 2026-09-13 | local+remote |
| `assistant/review-wizard-lobby` | 2026-09-12 | local+remote |
| `assistant/room-nsc-045` | 2026-09-12 | local+remote |
| `assistant/task-nsc-070-wizard-animation-audit` | 2026-09-12 | local+remote |
| `codex/batch-history-identity-validation` | 2026-09-05 | local |
| `codex/bulk-retired-completion-filter` | 2026-09-05 | local |
| `codex/combine-orchestration-scale` | 2026-09-05 | local |
| `codex/fix-required-decomposition-resume-route` | 2026-09-05 | local |
| `codex/integrate-scale-prereqs-0e8a` | 2026-09-05 | local |
| `codex/integrate-thousand-readiness-ebaa` | 2026-09-05 | local |
| `codex/integrate-thousand-readiness-ebaa-v2` | 2026-09-05 | local |
| `codex/nsc044-visual-tint-20260914` | 2026-09-14 | local+remote |
| `codex/nsc061-source-review-20260914` | 2026-09-14 | local+remote |
| `codex/nsc063-melee-ne-single-cleaver-20260914` | 2026-09-14 | local+remote |
| `codex/nsc064-connections-20260914` | 2026-09-14 | local+remote |
| `codex/nsc064-main-review-20260914` | 2026-09-14 | local+remote |
| `codex/nsc064-pixellab-20260914` | 2026-09-14 | local+remote |
| `codex/nsc070-validation-20260914` | 2026-09-14 | local+remote |
| `codex/nsc073-074-current-review-20260914` | 2026-09-14 | local+remote |
| `codex/nsc074-current-review-20260914` | 2026-09-14 | local+remote |
| `codex/nsc074-exact-unity-20260914` | 2026-09-14 | local+remote |
| `codex/nsc077-current-main-review-20260914` | 2026-09-14 | local+remote |
| `codex/nsc077-gameplay-visibility-20260914` | 2026-09-14 | local+remote |
| `codex/nsc077-stationary-enemies-20260914` | 2026-09-14 | local+remote |
| `codex/source-admission-snapshot-perf` | 2026-09-05 | local |
| `demo/gauntlet-20260916` | 2026-09-16 | local |
| `docs/context-2026-08-31-live-gauntlet` | 2026-08-31 | local+remote |
| `executioncrew-human-review-retry` | 2026-08-23 | local |
| `fix/ci-134b` | 2026-09-17 | local |
| `fix/retired-decomposition-completion` | 2026-09-05 | local |
| `fix/structured-synthetic-pump` | 2026-09-04 | local |
| `fix/viewer-step1` | 2026-09-17 | local |
| `fix/worker-final-write` | 2026-09-16 | local |
| `nsc-005-closeout` | 2026-08-23 | local+remote |
| `review/extract-production-scheduler-factory` | 2026-09-04 | local |
| `review/orchestration-gauntlet-followup` | 2026-09-04 | local+remote |
