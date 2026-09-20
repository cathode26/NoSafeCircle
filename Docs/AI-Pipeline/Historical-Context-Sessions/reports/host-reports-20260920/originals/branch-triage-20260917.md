# Branch triage against local main (2026-09-17)

Measure: `git cherry main <branch>`. A commit counts as already in main when main holds an
equivalent patch, whichever way it got there. A file diff against main is not a containment
test, because main has moved on since these branches.

- branches not merged into main: 131
- every commit already in main: 88
- still carrying unique commits: 43

## Still carrying unique commits

| branch | last commit | unique commits | files | Assets files |
|---|---|---|---|---|
| `codex/nsc073-074-current-review-20260914` | 2026-09-14 | 2 | 212 | 211 |
| `codex/nsc074-current-review-20260914` | 2026-09-14 | 1 | 213 | 211 |
| `codex/nsc074-exact-unity-20260914` | 2026-09-14 | 1 | 213 | 211 |
| `demo/gauntlet-20260916` | 2026-09-16 | 5 | 133 | 90 |
| `codex/nsc077-gameplay-visibility-20260914` | 2026-09-14 | 4 | 53 | 53 |
| `codex/nsc077-current-main-review-20260914` | 2026-09-14 | 3 | 53 | 53 |
| `codex/nsc077-stationary-enemies-20260914` | 2026-09-14 | 3 | 53 | 53 |
| `assistant/room-nsc-045` | 2026-09-12 | 3 | 15 | 15 |
| `codex/nsc064-connections-20260914` | 2026-09-14 | 3 | 21 | 14 |
| `assistant/foreground-nsc-066-title-screen` | 2026-09-12 | 1 | 9 | 8 |
| `codex/nsc064-main-review-20260914` | 2026-09-14 | 1 | 11 | 8 |
| `codex/nsc064-pixellab-20260914` | 2026-09-14 | 1 | 11 | 8 |
| `assistant/nsc-074-cardinal-art` | 2026-09-13 | 4 | 2 | 2 |
| `nsc-005-closeout` | 2026-08-23 | 3 | 6 | 2 |
| `assistant/cardinal-staging` | 2026-09-13 | 2 | 9 | 2 |
| `codex/nsc070-validation-20260914` | 2026-09-14 | 2 | 2 | 2 |
| `codex/nsc044-visual-tint-20260914` | 2026-09-14 | 1 | 2 | 2 |
| `executioncrew-human-review-retry` | 2026-08-23 | 1 | 2 | 2 |
| `codex/combine-orchestration-scale` | 2026-09-05 | 84 | 171 | 0 |
| `codex/integrate-thousand-readiness-ebaa-v2` | 2026-09-05 | 80 | 170 | 0 |
| `codex/source-admission-snapshot-perf` | 2026-09-05 | 80 | 170 | 0 |
| `codex/integrate-thousand-readiness-ebaa` | 2026-09-05 | 76 | 170 | 0 |
| `codex/batch-history-identity-validation` | 2026-09-05 | 74 | 141 | 0 |
| `codex/fix-required-decomposition-resume-route` | 2026-09-05 | 74 | 141 | 0 |
| `codex/integrate-scale-prereqs-0e8a` | 2026-09-05 | 74 | 156 | 0 |
| `codex/bulk-retired-completion-filter` | 2026-09-05 | 70 | 140 | 0 |
| `fix/retired-decomposition-completion` | 2026-09-05 | 68 | 140 | 0 |
| `review/orchestration-gauntlet-followup` | 2026-09-04 | 49 | 95 | 0 |
| `assistant-ci-boundary-20260912` | 2026-09-12 | 35 | 364 | 0 |
| `fix/structured-synthetic-pump` | 2026-09-04 | 19 | 63 | 0 |
| `review/extract-production-scheduler-factory` | 2026-09-04 | 19 | 63 | 0 |
| `fix/viewer-step1` | 2026-09-17 | 13 | 10 | 0 |
| `docs/context-2026-08-31-live-gauntlet` | 2026-08-31 | 4 | 6 | 0 |
| `fix/worker-final-write` | 2026-09-16 | 2 | 8 | 0 |
| `assistant/foreground-nsc-062-materialization` | 2026-09-12 | 1 | 5 | 0 |
| `assistant/foreground-nsc-067-selection` | 2026-09-12 | 1 | 5 | 0 |
| `assistant/integrate-background-plus-decomp` | 2026-09-13 | 1 | 2 | 0 |
| `assistant/restored-meta-companion-fix` | 2026-09-13 | 1 | 2 | 0 |
| `assistant/review-wizard-lobby` | 2026-09-12 | 1 | 5 | 0 |
| `assistant/task-nsc-070-wizard-animation-audit` | 2026-09-12 | 1 | 4 | 0 |
| `codex/nsc061-source-review-20260914` | 2026-09-14 | 1 | 1 | 0 |
| `codex/nsc063-melee-ne-single-cleaver-20260914` | 2026-09-14 | 1 | 4 | 0 |
| `fix/ci-134b` | 2026-09-17 | 1 | 3 | 0 |

## Already in main (branch pointer only)

- `assignment-4-RAG` (2026-08-06)
- `assignment-5-goal-oriented-agent` (2026-08-13)
- `assignment-6-GER` (2026-08-18)
- `assignment-7-style-guide-agent` (2026-08-20)
- `assignment3-agent-crew` (2026-08-04)
- `assistant-control-main-20260912` (2026-09-12)
- `assistant/NSC-060` (2026-09-14)
- `assistant/NSC-073-current` (2026-09-14)
- `assistant/NSC-089-editmode-path` (2026-09-14)
- `assistant/enemy-eight-direction-contract` (2026-09-14)
- `assistant/fix-exact-worker-scope` (2026-09-12)
- `assistant/integrate-nsc-070` (2026-09-12)
- `assistant/nsc-046-chapel` (2026-09-13)
- `assistant/nsc-047-vault` (2026-09-13)
- `assistant/nsc-048-final` (2026-09-13)
- `assistant/nsc-070-runtime-stability` (2026-09-13)
- `assistant/nsc-073-pixellab` (2026-09-13)
- `assistant/review-wizard-rooms` (2026-09-13)
- `assistant/room-composition-a` (2026-09-13)
- `assistant/room-composition-b` (2026-09-13)
- `assistant/room-nsc-044` (2026-09-12)
- `assistant/taskgraph-nsc-068` (2026-09-12)
- `assistant/viewer-external-active` (2026-09-14)
- `assistant/world-multiscene-graph` (2026-09-12)
- `codex/conformance-cherry-pick-content-20260914` (2026-09-14)
- `codex/ger-active-viewer-20260914` (2026-09-14)
- `codex/ger-held-viewer-20260914` (2026-09-14)
- `codex/missing-validation-policy-review-20260914` (2026-09-14)
- `codex/nsc-new-file-scope-repair` (2026-09-14)
- `codex/nsc013-main-ready-20260914` (2026-09-14)
- `codex/nsc013-provisional-20260914` (2026-09-14)
- `codex/nsc013-validation-20260914` (2026-09-14)
- `codex/nsc013-validation2-20260914` (2026-09-14)
- `codex/nsc032-current-main-recovery-20260914` (2026-09-14)
- `codex/nsc042-delivery-20260914` (2026-09-14)
- `codex/nsc042-evidence-handoff-20260914` (2026-09-14)
- `codex/nsc044-ger-room-20260914` (2026-09-14)
- `codex/nsc050-current-main-20260914` (2026-09-14)
- `codex/nsc051-door-passability-20260914` (2026-09-14)
- `codex/nsc051-final-main-20260914` (2026-09-14)
- `codex/nsc052-current-main-stage-20260914` (2026-09-14)
- `codex/nsc052-val003-20260914` (2026-09-14)
- `codex/nsc052-verification-20260914` (2026-09-14)
- `codex/nsc057-tooling-20260914` (2026-09-14)
- `codex/nsc058-hierarchy-fader-20260914` (2026-09-14)
- `codex/nsc060-current-main-20260914` (2026-09-14)
- `codex/nsc060-lifecycle-validation-20260914` (2026-09-14)
- `codex/nsc063-art-recovery-20260914` (2026-09-14)
- `codex/nsc063-current-main-revision-20260914` (2026-09-14)
- `codex/nsc063-pixellab-revision-20260914` (2026-09-14)
- `codex/nsc065-retained-art-review-20260914` (2026-09-14)
- `codex/nsc065-source-delivery-20260914` (2026-09-14)
- `codex/nsc073-alt-current-stage-20260914` (2026-09-14)
- `codex/nsc073-main-validation-20260914` (2026-09-14)
- `codex/nsc073-ne-alternate-20260914` (2026-09-14)
- `codex/nsc090-main-validation-20260914` (2026-09-14)
- `codex/nsc091-main-ready-20260914` (2026-09-14)
- `codex/nsc091-provisional-20260914` (2026-09-14)
- `codex/nsc092-diagnostic-20260914` (2026-09-14)
- `codex/nsc092-main-ready-20260914` (2026-09-14)
- `codex/nsc092-obstacle-fix-20260914` (2026-09-14)
- `codex/nsc092-provisional-20260914` (2026-09-14)
- `codex/nsc093-pixellab-walk-20260914` (2026-09-14)
- `codex/parallel-scene-reservation-20260914` (2026-09-14)
- `codex/remove-blocking-audits` (2026-09-14)
- `codex/viewer-instructions-20260914` (2026-09-14)
- `contracts/rerun-door-and-ranged-decompositions` (2026-08-26)
- `docs/canonical-mutation-api-precedence` (2026-09-01)
- `docs/ger-agent-runbook-20260914` (2026-09-14)
- `docs/needs-testing-nonblocking-dependencies` (2026-08-25)
- `docs/nsc042-wall-tiling-standard` (2026-09-14)
- `docs/unity-programmer-language` (2026-08-26)
- `fix/latest-effective-pr-checks` (2026-08-29)
- `fix/task-agent-live-progress-logging` (2026-08-28)
- `fix/unity-generated-whitespace` (2026-09-17)
- `integration/public-orchestration-final-20260908` (2026-09-07)
- `milestone-2a-current-gdd-rag` (2026-08-21)
- `nsc-005-feedback-fix` (2026-08-23)
- `nsc-061-pixellab-wizard-art-selection` (2026-09-12)
- `nsc-062-animated-wizard-unity-integration` (2026-09-12)
- `pipeline/history-identity-migration-v2` (2026-08-29)
- `pipeline/narrow-doorprototype-builder-commit-20260902-025607` (2026-09-02)
- `pipeline/pre-handoff-unity-generation-hygiene-20260902-004901` (2026-09-02)
- `release-ci/main-46dd7cd09` (2026-09-17)
- `release/policy-nsc071-40a` (2026-09-14)
- `review/orchestration-gauntlet-followup-integration` (2026-09-05)
- `streaming-verification-refinement` (2026-08-21)
- `viewer-held-overlay` (2026-09-14)
