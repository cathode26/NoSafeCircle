# Branch containment against local main (2026-09-17)

`differing` = files the branch changed whose content at its tip is not what main has now.
`unique` = commits with no patch-equivalent in main (git cherry).

- unmerged branches examined: 115
- content fully in main, nothing to merge: 10
- still holding different content: 105

## Still holding different content

| branch | last commit | differing/changed | unique commits | Assets files |
|---|---|---|---|---|
| `assistant/foreground-nsc-062-materialization` | 2026-09-12 | 170/257 | 1 | 166 |
| `assistant/review-wizard-lobby` | 2026-09-12 | 170/264 | 1 | 166 |
| `assistant/foreground-nsc-067-selection` | 2026-09-12 | 140/280 | 1 | 136 |
| `codex/combine-orchestration-scale` | 2026-09-05 | 105/171 | 84 | 0 |
| `codex/integrate-thousand-readiness-ebaa` | 2026-09-05 | 105/170 | 76 | 0 |
| `codex/integrate-thousand-readiness-ebaa-v2` | 2026-09-05 | 105/170 | 80 | 0 |
| `codex/source-admission-snapshot-perf` | 2026-09-05 | 105/170 | 80 | 0 |
| `codex/nsc073-074-current-review-20260914` | 2026-09-14 | 99/214 | 2 | 98 |
| `codex/nsc074-current-review-20260914` | 2026-09-14 | 99/213 | 1 | 97 |
| `codex/nsc074-exact-unity-20260914` | 2026-09-14 | 99/213 | 1 | 97 |
| `codex/integrate-scale-prereqs-0e8a` | 2026-09-05 | 97/156 | 74 | 0 |
| `fix/retired-decomposition-completion` | 2026-09-05 | 97/140 | 68 | 0 |
| `codex/batch-history-identity-validation` | 2026-09-05 | 96/141 | 74 | 0 |
| `codex/bulk-retired-completion-filter` | 2026-09-05 | 96/140 | 70 | 0 |
| `codex/fix-required-decomposition-resume-route` | 2026-09-05 | 96/141 | 74 | 0 |
| `codex/nsc077-stationary-enemies-20260914` | 2026-09-14 | 75/135 | 3 | 72 |
| `review/orchestration-gauntlet-followup` | 2026-09-04 | 72/95 | 49 | 0 |
| `assistant-ci-boundary-20260912` | 2026-09-12 | 59/364 | 35 | 0 |
| `fix/structured-synthetic-pump` | 2026-09-04 | 55/63 | 19 | 0 |
| `review/extract-production-scheduler-factory` | 2026-09-04 | 55/63 | 19 | 0 |
| `assistant-control-main-20260912` | 2026-09-12 | 53/367 | 0 | 0 |
| `codex/nsc077-current-main-review-20260914` | 2026-09-14 | 53/53 | 3 | 53 |
| `codex/nsc077-gameplay-visibility-20260914` | 2026-09-14 | 53/53 | 4 | 53 |
| `demo/gauntlet-20260916` | 2026-09-16 | 43/43 | 5 | 24 |
| `pipeline/history-identity-migration-v2` | 2026-08-29 | 26/56 | 0 | 2 |
| `codex/nsc063-current-main-revision-20260914` | 2026-09-14 | 22/82 | 0 | 19 |
| `assistant/room-nsc-045` | 2026-09-12 | 21/28 | 3 | 10 |
| `codex/nsc063-art-recovery-20260914` | 2026-09-14 | 21/45 | 0 | 16 |
| `codex/nsc064-connections-20260914` | 2026-09-14 | 21/21 | 3 | 14 |
| `fix/latest-effective-pr-checks` | 2026-08-29 | 18/37 | 0 | 0 |
| `assignment3-agent-crew` | 2026-08-04 | 17/67 | 0 | 14 |
| `assistant/room-nsc-044` | 2026-09-12 | 15/21 | 0 | 4 |
| `assistant/NSC-060` | 2026-09-14 | 12/76 | 0 | 10 |
| `assistant/world-multiscene-graph` | 2026-09-12 | 11/13 | 0 | 0 |
| `codex/nsc064-main-review-20260914` | 2026-09-14 | 11/11 | 1 | 8 |
| `codex/nsc064-pixellab-20260914` | 2026-09-14 | 11/11 | 1 | 8 |
| `fix/viewer-step1` | 2026-09-17 | 10/10 | 13 | 0 |
| `assistant/cardinal-staging` | 2026-09-13 | 9/13 | 2 | 5 |
| `codex/nsc057-tooling-20260914` | 2026-09-14 | 9/70 | 0 | 7 |
| `codex/nsc093-pixellab-walk-20260914` | 2026-09-14 | 8/102 | 0 | 7 |
| `fix/worker-final-write` | 2026-09-16 | 8/8 | 2 | 0 |
| `assignment-5-goal-oriented-agent` | 2026-08-13 | 6/21 | 0 | 4 |
| `assistant/nsc-074-cardinal-art` | 2026-09-13 | 6/10 | 4 | 2 |
| `nsc-005-closeout` | 2026-08-23 | 6/6 | 3 | 2 |
| `streaming-verification-refinement` | 2026-08-21 | 6/169 | 0 | 0 |
| `assistant/enemy-eight-direction-contract` | 2026-09-14 | 5/6 | 0 | 0 |
| `assistant/review-wizard-rooms` | 2026-09-13 | 5/6 | 0 | 5 |
| `assistant/room-composition-b` | 2026-09-13 | 5/9 | 0 | 5 |
| `assignment-6-GER` | 2026-08-18 | 4/41 | 0 | 4 |
| `assistant/nsc-048-final` | 2026-09-13 | 4/8 | 0 | 4 |
| `assistant/room-composition-a` | 2026-09-13 | 4/6 | 0 | 4 |
| `assistant/task-nsc-070-wizard-animation-audit` | 2026-09-12 | 4/4 | 1 | 0 |
| `codex/ger-active-viewer-20260914` | 2026-09-14 | 4/6 | 0 | 0 |
| `codex/nsc013-provisional-20260914` | 2026-09-14 | 4/10 | 0 | 4 |
| `codex/nsc060-current-main-20260914` | 2026-09-14 | 4/7 | 0 | 4 |
| `codex/nsc063-melee-ne-single-cleaver-20260914` | 2026-09-14 | 4/4 | 1 | 0 |
| `codex/nsc063-pixellab-revision-20260914` | 2026-09-14 | 4/64 | 0 | 1 |
| `codex/nsc092-provisional-20260914` | 2026-09-14 | 4/10 | 0 | 4 |
| `nsc-061-pixellab-wizard-art-selection` | 2026-09-12 | 4/140 | 0 | 3 |
| `nsc-062-animated-wizard-unity-integration` | 2026-09-12 | 4/140 | 0 | 3 |
| `assistant/NSC-073-current` | 2026-09-14 | 3/4 | 0 | 2 |
| `assistant/fix-exact-worker-scope` | 2026-09-12 | 3/7 | 0 | 0 |
| `assistant/integrate-nsc-070` | 2026-09-12 | 3/5 | 0 | 0 |
| `assistant/nsc-046-chapel` | 2026-09-13 | 3/8 | 0 | 3 |
| `assistant/nsc-047-vault` | 2026-09-13 | 3/8 | 0 | 3 |
| `assistant/nsc-073-pixellab` | 2026-09-13 | 3/4 | 0 | 2 |
| `codex/ger-held-viewer-20260914` | 2026-09-14 | 3/4 | 0 | 0 |
| `codex/missing-validation-policy-review-20260914` | 2026-09-14 | 3/4 | 0 | 0 |
| `codex/nsc073-main-validation-20260914` | 2026-09-14 | 3/4 | 0 | 2 |
| `codex/nsc073-ne-alternate-20260914` | 2026-09-14 | 3/4 | 0 | 2 |
| `codex/remove-blocking-audits` | 2026-09-14 | 3/8 | 0 | 0 |
| `fix/ci-134b` | 2026-09-17 | 3/3 | 1 | 0 |
| `milestone-2a-current-gdd-rag` | 2026-08-21 | 3/11 | 0 | 0 |
| `viewer-held-overlay` | 2026-09-14 | 3/4 | 0 | 0 |
| `assignment-4-RAG` | 2026-08-06 | 2/31 | 0 | 0 |
| `assistant/foreground-nsc-066-title-screen` | 2026-09-12 | 2/9 | 1 | 2 |
| `assistant/integrate-background-plus-decomp` | 2026-09-13 | 2/2 | 1 | 0 |
| `assistant/nsc-070-runtime-stability` | 2026-09-13 | 2/2 | 0 | 2 |
| `assistant/restored-meta-companion-fix` | 2026-09-13 | 2/2 | 1 | 0 |
| `assistant/taskgraph-nsc-068` | 2026-09-12 | 2/4 | 0 | 0 |
| `assistant/viewer-external-active` | 2026-09-14 | 2/2 | 0 | 0 |
| `codex/nsc-new-file-scope-repair` | 2026-09-14 | 2/7 | 0 | 0 |
| `codex/nsc044-visual-tint-20260914` | 2026-09-14 | 2/2 | 1 | 2 |
| `codex/nsc060-lifecycle-validation-20260914` | 2026-09-14 | 2/7 | 0 | 2 |
| `codex/nsc070-validation-20260914` | 2026-09-14 | 2/2 | 2 | 2 |
| `codex/nsc073-alt-current-stage-20260914` | 2026-09-14 | 2/4 | 0 | 1 |
| `codex/nsc091-provisional-20260914` | 2026-09-14 | 2/8 | 0 | 2 |
| `codex/parallel-scene-reservation-20260914` | 2026-09-14 | 2/6 | 0 | 0 |
| `codex/viewer-instructions-20260914` | 2026-09-14 | 2/2 | 0 | 0 |
| `docs/context-2026-08-31-live-gauntlet` | 2026-08-31 | 2/6 | 4 | 0 |
| `docs/ger-agent-runbook-20260914` | 2026-09-14 | 2/2 | 0 | 0 |
| `executioncrew-human-review-retry` | 2026-08-23 | 2/2 | 1 | 2 |
| `pipeline/narrow-doorprototype-builder-commit-20260902-025607` | 2026-09-02 | 2/2 | 0 | 0 |
| `assistant/NSC-089-editmode-path` | 2026-09-14 | 1/6 | 0 | 1 |
| `codex/nsc013-validation-20260914` | 2026-09-14 | 1/4 | 0 | 1 |
| `codex/nsc050-current-main-20260914` | 2026-09-14 | 1/3 | 0 | 1 |
| `codex/nsc052-val003-20260914` | 2026-09-14 | 1/1 | 0 | 1 |
| `codex/nsc061-source-review-20260914` | 2026-09-14 | 1/1 | 1 | 0 |
| `codex/nsc065-retained-art-review-20260914` | 2026-09-14 | 1/12 | 0 | 0 |
| `codex/nsc090-main-validation-20260914` | 2026-09-14 | 1/4 | 0 | 1 |
| `codex/nsc091-main-ready-20260914` | 2026-09-14 | 1/4 | 0 | 1 |
| `codex/nsc092-diagnostic-20260914` | 2026-09-14 | 1/6 | 0 | 1 |
| `codex/nsc092-main-ready-20260914` | 2026-09-14 | 1/6 | 0 | 1 |
| `codex/nsc092-obstacle-fix-20260914` | 2026-09-14 | 1/7 | 0 | 1 |
| `release/policy-nsc071-40a` | 2026-09-14 | 1/1 | 0 | 0 |

## Fully contained in main

- `assignment-7-style-guide-agent` (2026-08-20, 41 files, 0 unique commits)
- `codex/conformance-cherry-pick-content-20260914` (2026-09-14, 2 files, 0 unique commits)
- `codex/nsc013-main-ready-20260914` (2026-09-14, 4 files, 0 unique commits)
- `codex/nsc013-validation2-20260914` (2026-09-14, 4 files, 0 unique commits)
- `codex/nsc042-delivery-20260914` (2026-09-14, 5 files, 0 unique commits)
- `codex/nsc042-evidence-handoff-20260914` (2026-09-14, 5 files, 0 unique commits)
- `codex/nsc044-ger-room-20260914` (2026-09-14, 8 files, 0 unique commits)
- `codex/nsc058-hierarchy-fader-20260914` (2026-09-14, 11 files, 0 unique commits)
- `codex/nsc065-source-delivery-20260914` (2026-09-14, 6 files, 0 unique commits)
- `docs/nsc042-wall-tiling-standard` (2026-09-14, 3 files, 0 unique commits)
