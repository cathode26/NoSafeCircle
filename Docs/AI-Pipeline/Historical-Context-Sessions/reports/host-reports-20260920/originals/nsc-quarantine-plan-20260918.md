# NSC quarantine plan - C:\NSC top level - 2026-09-18

Standing rule: `C:/NSC/nsc-cleanup-agent-guide.md`. Destination scheme: `C:\NSC-History-20260918`,
extending the pass already run against 45 `C:\nsc*` drive-root directories. This agent never moves
or deletes anything itself; it only writes the inventory below and the ready-to-run, dry-run-by-default
script at `C:\NSC-History-20260918\MOVE-NSC-FOLDERS.ps1`. Vincent reviews and runs it.

Vincent's rule for the whole scheme: *"if we go into the history folder and find something of value,
it needs to come out of the history folder"* - the folder is a waiting room, `RESTORE.ps1` is the
mechanism, and nothing here is deleted by this pass.

## 1. Summary

`C:\NSC` has 787 top-level directories and 300 top-level files.

| | Directories | Files |
|---|---|---|
| **move** | 416 | 138 |
| **keep** (hard guard) | 41 | 89 |
| **ask** (needs Vincent's decision) | 330 | 73 |

Total size that would move: **100.34 GB** (directories: 100.18 GB, files: 158.2 MB).

This is a **conservative first pass**. 330 of 787 directories (42%) landed on `ask` rather than
`move` or `keep` - mostly single-experiment git clones/worktrees whose branch tip could not be
confirmed as an ancestor of `main` in the canonical repo (257 dirs), plus a smaller number with
real uncommitted changes (55, overlapping) or a folder/file touched in the last 7 days (65,
including folders that are empty right now but whose own folder entry was created or changed
within 7 days). A short `ask` list would have been nicer; a long one that is honest about what
could not be confirmed is the safer failure mode for a pass this risky, so it was left long rather
than trimmed by guesswork.

## 2. Method

For every one of the 787 top-level directories:
1. a fast, non-recursive pass recorded git-repo/worktree markers, an immediate `.assistant-control`
   check, Unity markers (`Library`/`Assets`/`ProjectSettings`), and top-level child recency;
2. a single recursive file walk (excluding the four exact-path hard guards, which are skipped for
   speed since they can never be moved) recorded newest-file date, total size and `Library`-subtree
   size for every other directory - one filesystem pass, not 783 separate recursive walks;
3. every git repo/worktree found (277) was checked against the **canonical** repo
   (`C:\NSC\NSC\NoSafeCircle`) with `git -C canonical cat-file -e <sha>` then
   `git -C canonical merge-base --is-ancestor <sha> main` - not against the clone's own,
   possibly-stale local `main`. A sha canonical has never seen counts as **not** an ancestor:
   conservative by construction. Working-tree status was also checked, ignoring changes confined to
   `Library/`, `Temp/`, `Logs/`, `obj/`, `.vs/` or `*.tmp` (Unity/IDE churn, not real work);
4. a **second, independent recursive search for every `.assistant-control` folder anywhere under
   `C:\NSC`** (268 found, not just the ones sitting directly under a top-level name) was run and
   cross-checked against step 2's verdicts. It caught one directory (`AssistantControlRuns`,
   1.4 GB) that the top-level-only check had missed and that step 2 had provisionally marked
   `move` - its live-looking record sits two levels down. That directory is now `keep`. This is
   the check the brief specifically asked for ("at least three such checkout roots, not one") and
   it is why this report trusts the recursive scan over the top-level one;
5. the 300 top-level files were classified by extension, last-write date, and (for the 147 that were
   neither a `.md` doc nor touched in the last 7 days) a reference grep against the ~80 top-level
   `.md` docs, `C:\NSC\agent-state`, and the six `C:\nscrev` tool folders 
   (`ger-tools`, `viewer-tools`, `session-tools`, `astra`, `reports`; `game-tools` does not
   exist on this machine).

## 3. Never-move hard guards enforced

By exact path (never entered into the move set regardless of anything else):
- `C:\NSC\NSC` (canonical repo)
- `C:\NSC\NoSafeCircle-AssistantCheckouts` (live, 37 records - see checkout roots below)
- `C:\NSC\agent-state`
- `C:\NSC\SuccessfullTasks`
- every top-level `*.md` file (80 files; see file section)

## 4. Checkout roots found (`.assistant-control` holding `NSC-*.json` records)

The brief warned there are "at least three" such roots and asked this pass to detect them rather
than trust a list. **A full recursive search under `C:\NSC` found 268 `.assistant-control`
folders in total, of which 40 (under 38 distinct top-level directories) hold at
least one `NSC-*.json` record.** All 38 are hard-guarded to `keep` here,
including several the brief's own example list did not name (`AssistantControlRuns`,
`AssistantControlEvidence`, `assistant-background-test-temp`).

| Top-level directory | nested .assistant-control dirs | total NSC-*.json records |
|---|---|---|
| `assistant-background-test-temp` | 1 | 1 |
| `AssistantControlEvidence` | 3 | 3 |
| `AssistantControlRuns` | 1 | 1 |
| `AssistantGauntletOne` | 1 | 1 |
| `AssistantGauntletPublish` | 1 | 5 |
| `AssistantGauntletPublishRetry` | 1 | 21 |
| `AssistantGauntletSimple` | 1 | 5 |
| `AssistantGauntletSimpleFresh` | 1 | 5 |
| `Gauntlet1120Wet-20260911-2-Checkouts` | 1 | 5 |
| `Gauntlet1120Wet-20260911-3-Checkouts` | 1 | 3 |
| `Gauntlet1120Wet-20260911-Checkouts` | 1 | 1 |
| `Gauntlet1120Wet-20260912-1-Checkouts` | 1 | 8 |
| `GauntletDecompositionWet-20260911-2-Checkouts` | 1 | 6 |
| `GauntletDecompositionWet-20260911-3-Checkouts` | 1 | 1 |
| `GauntletFresh1130Run-20260912-1-Checkouts` | 1 | 12 |
| `GauntletFresh1140-20260912-1-Checkouts` | 1 | 1 |
| `GauntletFresh1140-20260912-1-Checkouts-2` | 1 | 6 |
| `GauntletFresh1140-20260912-1-Checkouts-3` | 1 | 6 |
| `GauntletFresh1140-20260912-1-Checkouts-4` | 1 | 15 |
| `GauntletFresh1140-20260912-1-Checkouts-5` | 1 | 28 |
| `GauntletFresh1140-20260912-1-Checkouts-6` | 1 | 40 |
| `GauntletFresh1160-FixesRun-20260913-Checkouts` | 1 | 38 |
| `GauntletFresh1160-Reviewed-Standalone-Checkouts` | 1 | 32 |
| `GauntletReplayWet-20260911-2-Checkouts` | 1 | 7 |
| `GauntletReplayWet-20260911-3-Checkouts` | 1 | 3 |
| `GauntletReplayWet-20260911-4-Checkouts` | 1 | 3 |
| `GauntletReplayWet-20260911-5-Checkouts` | 1 | 10 |
| `NoSafeCircle-AssistantCheckouts` | 16 | 37 |
| `NoSafeCircle-Game-Checkouts-2` | 2 | 1 |
| `NoSafeCircle-Game-Checkouts-3` | 11 | 14 |
| `NoSafeCircle-Multiscene-Checkouts` | 2 | 1 |
| `NoSafeCircle-Sorting-Checkouts` | 2 | 1 |
| `NoSafeCircle-Sorting-Checkouts-2` | 2 | 1 |
| `NSCDemoGauntlet-20260916-Checkouts` | 9 | 18 |
| `TenTaskFinalIntegration-20260905-AssistantCheckouts` | 1 | 4 |
| `TenTaskFinalIntegration-20260905-AssistantCheckouts-Current` | 1 | 5 |
| `TenTaskFinalIntegration-20260905-DemoRun` | 1 | 1 |
| `TenTaskFinalIntegration-DemoCopy-Run` | 1 | 1 |

A further 54 top-level directories contain a `.assistant-control` folder with
**no** records right now - mostly single task-named worktrees (`NoSafeCircle-Room-NSC-044`,
`NoSafeCircle-Foreground-NSC-062-Fix`, and similar). None of these were placed in `move`: either
their git branch could not be confirmed merged (the common case) or, as a second-layer guard, this
pass refuses to auto-move anything shaped like a task/worker checkout even with 0 records today.
They are listed in the `ask` directory table (section 6) with their own reasons, not repeated here.
Per the cleanup guide, task-named worktrees wait for Vincent's own archive decision regardless.

## 5. Git repos and worktrees (277 found)

| | count |
|---|---|
| Confirmed ancestor of canonical `main`, clean, not recently touched -> **move** | 2 |
| Branch tip not confirmed as an ancestor of canonical `main` -> **ask** | 257 |
| Real (non-Unity-noise) uncommitted changes -> **ask** | 55 (overlaps with the row above) |

The 257 unmerged figure is expected for this tree: most of these directories are one-off dated
experiment/candidate branches (`Astra*`, `Codex*`, `Gauntlet*` fix attempts, etc.) that were
never merged, exactly as the brief's context describes. This pass checked exact-sha ancestry only,
not squash/cherry-pick patch-equivalence (the cleanup guide's `git cherry main <branch>` check) -
some of the 257 may in fact be patch-equivalent to something already on `main`. That check was not
run here (277 repos x a cherry-pick diff each is expensive and this pass already had a safe,
cheap answer: leave them `ask`). A follow-up pass could shrink the `ask` list with it if wanted.

The two directories confirmed safe to move as git content:
| Name | type | branch | head | notes |
|---|---|---|---|---|
| `ProviderSmokeVerify-20260906` | worktree | worktree branch=HEAD head=73fae3818d ancestorOfMain=True realChanges=0 noiseChanges=0 |  |
| `PublicPipelineBaseVerification-20260907` | repo | repo branch=main head=73fae3818d ancestorOfMain=True realChanges=0 noiseChanges=0 |  |

`ProviderSmokeVerify-20260906` is a **worktree**. Moving a worktree with robocopy does not clean up
its admin entry in the repo it belongs to; after the move, whoever owns that repo should run
`git worktree prune` there. The script below prints this reminder when it moves a worktree-type
directory.

## 6. Full `move` list - 416 directories, 100.18 GB

| Name | Size (MB) | Type | Newest file (UTC) |
|---|---|---|---|
| `.codex-test-temp` | 0.1 | plain-dir | 2026-09-04T09:31:26Z |
| `.codex-test-tmp-nsc915-reset-rehearsal` | 0 | plain-dir |  |
| `.codex-test-tmp-nsc915-reset-task` | 0 | plain-dir |  |
| `.codex-test-tmp-published-undo` | 0.5 | plain-dir | 2026-09-06T02:15:44Z |
| `.codex-test-tmp-reset-rehearsal` | 0 | plain-dir |  |
| `.task-agent-tests` | 0 | plain-dir |  |
| `.task-fix-tests` | 0 | plain-dir | 2026-09-03T05:03:24Z |
| `.task-review-agent` | 0 | plain-dir | 2026-09-08T01:44:23Z |
| `.task-review-agent-test-temp` | 0 | plain-dir |  |
| `.task-review-test-temp` | 0 | plain-dir |  |
| `.task-review-test-tmp` | 0 | plain-dir |  |
| `.task-test-temp` | 0 | plain-dir |  |
| `.test-temp` | 2.5 | plain-dir | 2026-09-07T09:54:11Z |
| `.test-temp-abandoned-waiter` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-checkouts` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-elevated` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-elevated-2` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-existing` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-final` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-green` | 0 | plain-dir |  |
| `.test-temp-abandoned-waiter-green-2` | 0 | plain-dir |  |
| `.test-temp-execution-crew` | 0 | plain-dir |  |
| `.test-temp-git-identity` | 0 | plain-dir |  |
| `.test-temp-git-identity-escalated` | 0 | plain-dir |  |
| `.test-temp-reset-script` | 0 | plain-dir |  |
| `.test-tmp` | 0 | plain-dir | 2026-09-07T20:12:49Z |
| `.tmp-architect-tests` | 0 | plain-dir |  |
| `.tmp-gate-resume-e34` | 0 | plain-dir |  |
| `.tmp-gate-resume-e34-host` | 0 | plain-dir |  |
| `.tmp-gate-resume-fixed` | 0 | plain-dir |  |
| `.tmp-gate-resume-suite` | 0 | plain-dir |  |
| `.tmp-muff-profiler` | 0 | plain-dir |  |
| `.tmp-muff-standard` | 0 | plain-dir |  |
| `.tmp-observation-suite` | 0 | plain-dir |  |
| `.tmp-post-poll-suite` | 0 | plain-dir |  |
| `.tmp-pristine-gate-fixed` | 0 | plain-dir |  |
| `.tmp-real-checkout` | 0 | plain-dir |  |
| `.tmp-rehearsal-sync-tests` | 0 | plain-dir |  |
| `.tmp-reset-suite` | 0 | plain-dir |  |
| `.tmp-snapshot-correction` | 0 | plain-dir |  |
| `aa13f3548d` | 0.2 | plain-dir | 2026-09-09T06:56:39Z |
| `aa25f5e571` | 0.1 | plain-dir | 2026-09-09T06:47:30Z |
| `aa36b675ce` | 0.1 | plain-dir | 2026-09-09T06:50:54Z |
| `aa5ee7ac97` | 0.1 | plain-dir | 2026-09-09T07:38:31Z |
| `aa8e58701c` | 0.2 | plain-dir | 2026-09-09T07:39:21Z |
| `aa9a0cf844` | 0 | plain-dir | 2026-09-09T07:33:21Z |
| `aa9cb47697` | 0.1 | plain-dir | 2026-09-09T06:48:45Z |
| `aaa052720b` | 0 | plain-dir | 2026-09-09T07:33:21Z |
| `aaaa40682e` | 0.1 | plain-dir | 2026-09-09T06:55:59Z |
| `aac7f66049` | 0.1 | plain-dir | 2026-09-09T07:34:54Z |
| `aaca050c75` | 0.2 | plain-dir | 2026-09-09T07:35:40Z |
| `aacd3f37b7` | 0.2 | plain-dir | 2026-09-09T06:48:06Z |
| `aafcfef848` | 0.2 | plain-dir | 2026-09-09T06:49:52Z |
| `acceptance-resume-test-temp-elevated-0904` | 0 | plain-dir | 2026-09-04T12:16:02Z |
| `AgentTestTemp` | 268.9 | plain-dir | 2026-09-08T15:14:03Z |
| `architect-autonomous-test-temp-elevated-0904` | 0 | plain-dir |  |
| `architect-owner-test-temp` | 0.1 | plain-dir | 2026-09-04T12:01:20Z |
| `architect-owner-test-temp-elevated-0904` | 0 | plain-dir |  |
| `architect-owner-test-temp-final-0904` | 0 | plain-dir |  |
| `architect-polling-test-temp-elevated-0904` | 0 | plain-dir |  |
| `architect-preflight-test-temp-elevated-0904` | 0 | plain-dir |  |
| `ArchitectPromptSimulation-20260909-055000` | 0.1 | plain-dir | 2026-09-09T05:49:58Z |
| `ArchitectRecoveryTests20260905` | 0 | plain-dir | 2026-09-05T02:33:34Z |
| `AstraConvergenceRepairTests-20260908` | 0.9 | plain-dir | 2026-09-09T00:54:41Z |
| `AstraReviewEvidence-42339d179` | 2.3 | plain-dir | 2026-09-08T09:16:05Z |
| `AstraTLSValidation-20260908` | 0 | plain-dir |  |
| `Audit-3cde7094035373eb` | 35.4 | plain-dir | 2026-09-08T17:15:09Z |
| `Audit-ab0183c44c2262db` | 35.5 | plain-dir | 2026-09-08T16:56:37Z |
| `BranchlessPushedReset-TestTemp-20260908` | 0 | plain-dir |  |
| `CheckoutRaceLeaseRelease-BaseTestTemp` | 0 | plain-dir |  |
| `CheckoutRaceLeaseRelease-BaseTestTemp2` | 0 | plain-dir |  |
| `CheckoutRaceLeaseRelease-TestTemp` | 0 | plain-dir |  |
| `CheckoutRaceLeaseRelease-TestTemp2` | 0 | plain-dir |  |
| `ClaudeA85` | 33.8 | plain-dir | 2026-09-04T00:20:22Z |
| `ClaudeActorAuth` | 34 | plain-dir | 2026-09-04T02:56:14Z |
| `ClaudeArchitectManaged` | 69.4 | plain-dir | 2026-09-05T00:34:44Z |
| `ClaudeBulkReview` | 35.2 | plain-dir | 2026-09-05T14:22:57Z |
| `ClaudeCrewPool` | 33.8 | plain-dir | 2026-09-04T09:13:34Z |
| `ClaudeCrewPoolCorrective` | 35.9 | plain-dir | 2026-09-04T11:31:36Z |
| `ClaudeDecompositionPolicy` | 58.7 | plain-dir | 2026-09-04T22:26:16Z |
| `ClaudeEvidenceFix-20260905` | 35.9 | plain-dir | 2026-09-05T20:46:31Z |
| `ClaudeIssueConsistency-20260905` | 47.6 | plain-dir | 2026-09-05T22:07:28Z |
| `ClaudeLocalFour-20260908t1855z` | 1793.9 | plain-dir | 2026-09-09T06:38:28Z |
| `ClaudeNsc911LauncherFix-20260905` | 49.3 | plain-dir | 2026-09-06T00:54:24Z |
| `ClaudePendingTransition` | 41.3 | plain-dir | 2026-09-08T02:23:38Z |
| `ClaudePoolRecovery` | 35.6 | plain-dir | 2026-09-04T21:26:27Z |
| `ClaudePromptContext` | 66.9 | plain-dir | 2026-09-04T22:05:01Z |
| `ClaudeProviderNeutralSupervisor-20260905` | 39.3 | plain-dir | 2026-09-05T17:35:07Z |
| `ClaudeProviderSessions` | 33.8 | plain-dir | 2026-09-04T08:34:37Z |
| `ClaudePublicationFence-20260907` | 87.8 | plain-dir | 2026-09-07T07:06:46Z |
| `ClaudePumpLatency` | 69.6 | plain-dir | 2026-09-06T02:16:03Z |
| `ClaudeReview` | 44.3 | plain-dir | 2026-09-08T02:23:36Z |
| `ClaudeRigorPolicy` | 72.8 | plain-dir | 2026-09-04T19:50:02Z |
| `ClaudeRouteReview-20260905` | 0 | plain-dir |  |
| `ClaudeRouteReview2-20260905` | 93.5 | plain-dir | 2026-09-05T14:42:20Z |
| `ClaudeSemiAutonomous-20260905` | 48.3 | plain-dir | 2026-09-05T22:32:41Z |
| `ClaudeSessionPooling` | 77.3 | plain-dir | 2026-09-08T02:23:41Z |
| `ClaudeSonnetEvidence-20260909` | 0 | plain-dir | 2026-09-09T01:51:16Z |
| `ClaudeSupervisorReview-20260905` | 39.4 | plain-dir | 2026-09-05T18:35:20Z |
| `ClaudeSyntheticRunnerDriftFix-20260906` | 44.7 | plain-dir | 2026-09-06T13:12:08Z |
| `ClaudeUndoDecomposition` | 34.3 | plain-dir | 2026-09-04T00:46:24Z |
| `ClaudeUnityReuse` | 71.2 | plain-dir | 2026-09-06T02:16:10Z |
| `ClaudeValidationReuse` | 0 | plain-dir |  |
| `ClaudeValidationReuse2` | 35 | plain-dir | 2026-09-05T01:22:33Z |
| `ClaudeWakeFix-20260905` | 31.8 | plain-dir | 2026-09-05T20:46:43Z |
| `CodexArchitectSessionEvidence` | 0.1 | plain-dir | 2026-09-05T10:40:16Z |
| `codex-crew-profile-test` | 0 | plain-dir |  |
| `CodexFixReview-t1855` | 48.8 | plain-dir | 2026-09-09T02:31:05Z |
| `CodexLocalBootstrapTestTemp-20260908` | 0 | plain-dir |  |
| `CodexNSC915TransferFix` | 80.9 | plain-dir | 2026-09-05T08:29:20Z |
| `CodexPooledSessionFix` | 81.4 | plain-dir | 2026-09-05T08:27:17Z |
| `CodexQuotaFailoverEvidence` | 0.2 | plain-dir | 2026-09-05T10:39:39Z |
| `CodexRunEvidenceScopeFix-20260906` | 46.7 | plain-dir | 2026-09-06T11:45:08Z |
| `CodexTestTemp` | 0 | plain-dir | 2026-09-06T15:06:29Z |
| `codex-test-temp` | 0 | plain-dir |  |
| `codex-test-temp-20260904a` | 0 | plain-dir |  |
| `CodexVincentStyleCrossProvider` | 102.7 | plain-dir | 2026-09-05T11:10:28Z |
| `CombinedRecoveryIdentityTemp` | 0 | plain-dir |  |
| `CombinedRecoveryVerify-A` | 0 | plain-dir |  |
| `CombinedRecoveryVerify-B` | 0 | plain-dir |  |
| `CombinedRecoveryVerify-C` | 0 | plain-dir |  |
| `CombinedTestTemp` | 0 | plain-dir |  |
| `crew-isolate-akhpv8x0` | 0 | plain-dir |  |
| `CrewPoolIntegration` | 37.8 | plain-dir | 2026-09-04T12:54:32Z |
| `CrossProviderRetryCorrection` | 0 | plain-dir |  |
| `CrossProviderRetryCorrection2` | 84.1 | plain-dir | 2026-09-06T02:16:19Z |
| `CrossProviderRetryIntegration-TestTemp` | 0 | plain-dir |  |
| `D1CRaceTmp` | 0 | plain-dir |  |
| `D1CWakeTmp` | 0 | plain-dir |  |
| `DependencyBlockedPortfolioTestTemp` | 0 | plain-dir |  |
| `DurableIntegrationGateEvidence` | 0.4 | plain-dir | 2026-09-06T22:56:22Z |
| `FableConvergenceEvidence-20260908` | 1.6 | plain-dir | 2026-09-09T09:51:53Z |
| `FailedQuiescentOwnerRestore-FinalFocused` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-FinalGate` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-FinalWindow` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-SuiteTemp` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-TestTemp` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-TestTemp-Elevated` | 0 | plain-dir |  |
| `FailedQuiescentOwnerRestore-WindowTemp` | 0 | plain-dir |  |
| `FC-20260909-042249` | 301.7 | plain-dir | 2026-09-09T04:48:11Z |
| `fenced-autoaccept-audit-48e1511e490942bcb9f00ca6fb53ffd7` | 0.1 | plain-dir | 2026-09-09T06:45:29Z |
| `FourGauntlet-20260908-185642` | 0 | plain-dir |  |
| `FourGauntlet-20260908-185659` | 626.1 | plain-dir | 2026-09-09T00:03:08Z |
| `FourGauntlet-20260908-190515` | 1016.1 | plain-dir | 2026-09-09T03:08:39Z |
| `FourProfileFixPatches-20260908` | 0.1 | plain-dir | 2026-09-08T06:06:16Z |
| `FourProfileGauntlet-20260908` | 33998.4 | plain-dir | 2026-09-08T18:16:06Z |
| `FourProfileGauntletFresh-20260908-1812Z` | 20647.9 | plain-dir | 2026-09-09T04:50:23Z |
| `FullGauntletAfterMeta-t20260909-052000z` | 591.4 | plain-dir | 2026-09-09T06:58:58Z |
| `G02Recovery` | 0.4 | plain-dir | 2026-09-09T06:57:53Z |
| `G02WorkerFixtures` | 0.4 | plain-dir | 2026-09-09T06:59:09Z |
| `G095CleanupFixtures` | 0 | plain-dir |  |
| `G095CleanupFixturesRetry1` | 0 | plain-dir |  |
| `G095Recovery` | 0.4 | plain-dir | 2026-09-09T08:10:42Z |
| `G095WorkerFixtures` | 0.4 | plain-dir | 2026-09-09T08:10:19Z |
| `G6dProviderFixtures` | 0 | plain-dir |  |
| `G6dRecovery` | 0.4 | plain-dir | 2026-09-09T06:12:04Z |
| `G6dWorkerFixtures` | 0.4 | plain-dir | 2026-09-09T06:09:13Z |
| `G8-0650` | 666 | plain-dir | 2026-09-09T08:02:45Z |
| `G8-NextPrepared-20260909` | 0 | plain-dir | 2026-09-09T07:55:59Z |
| `GateFixBundles-20260907` | 16.7 | plain-dir | 2026-09-07T01:23:15Z |
| `gate-resume-diagnosis-0368a49d4bf4482690510c56d2a18ea4` | 0 | plain-dir |  |
| `gate-resume-diagnosis-5908623c74f947b3ae4bfeb76040e877` | 0 | plain-dir |  |
| `gate-resume-diagnosis-da7f893940ff425791791310f6b1d051` | 0 | plain-dir |  |
| `gate-resume-exact-d5e25c7b5fdd4a00beda9702144b5a7d` | 0 | plain-dir |  |
| `gate-resume-green-d5b639b2dcc74328b80ae5a1a3b1234a` | 0 | plain-dir |  |
| `gate-resume-suite-cbb41b0b87524ede99b9fb63506f8f27` | 0 | plain-dir |  |
| `GateResumeTestTemp-20260907` | 0 | plain-dir |  |
| `GateWaiterArchitectEvidence` | 0.7 | plain-dir | 2026-09-07T01:20:18Z |
| `GauntletActivityProof` | 0.4 | plain-dir | 2026-09-07T11:52:02Z |
| `GauntletActivityTestTemp` | 0 | plain-dir |  |
| `GauntletConvergenceEvidence-20260908` | 0.6 | plain-dir | 2026-09-08T23:52:36Z |
| `GauntletReviewPacketPrep-20260909` | 0 | plain-dir | 2026-09-09T07:54:41Z |
| `GauntletViewInheritedGateQueue-TestTemp` | 0 | plain-dir |  |
| `GauntletViewInheritedGateQueue-ValidationTemp` | 0 | plain-dir |  |
| `GauntletViewInheritedGateQueue-ValidationTemp2` | 0 | plain-dir |  |
| `GauntletViewInheritedGateQueue-ValidationTemp3` | 0 | plain-dir |  |
| `GauntletViewRuntime-20260907` | 0 | plain-dir | 2026-09-07T20:05:27Z |
| `GauntletViewRuntime-20260907-1240` | 0.8 | plain-dir | 2026-09-07T13:29:27Z |
| `GauntletViewScopeLayout-TestTemp` | 0 | plain-dir |  |
| `GauntletViewTerminalTestTemp` | 0 | plain-dir |  |
| `GauntletViewTerminalTruth-TestTemp` | 0 | plain-dir |  |
| `GauntletWorkerRevisionFixtures-20260909` | 0.4 | plain-dir | 2026-09-09T03:44:02Z |
| `generated-child-scope-7n36nfw5` | 0 | plain-dir |  |
| `generated-child-scope-dv2dn2we` | 0 | plain-dir |  |
| `generated-child-scope-g53i50xd` | 0 | plain-dir |  |
| `generated-child-scope-z81k9wvp` | 0 | plain-dir |  |
| `Historical-Context-Sessions` | 1.7 | plain-dir | 2026-08-30T22:29:03Z |
| `HomeworkMainControls-20260909-004240Z` | 97.1 | plain-dir | 2026-09-09T00:55:57Z |
| `HomeworkRehearsalRecoveryCheck-20260909` | 0 | plain-dir | 2026-09-09T01:14:49Z |
| `identity-final-temp` | 0 | plain-dir |  |
| `IlppPidIntegration-20260906` | 46.9 | plain-dir | 2026-09-06T11:25:47Z |
| `immutable-crew-real-olmysr0v` | 0 | plain-dir |  |
| `IndependentDecompPendingTmp` | 0 | plain-dir |  |
| `IndependentRevisionRaceBaselineTmp` | 0 | plain-dir |  |
| `IndependentRevisionRaceBaselineTmp2` | 0 | plain-dir |  |
| `IndependentRevisionRaceBaselineTmp3` | 0 | plain-dir |  |
| `IndependentRevisionRaceElevatedTmp` | 0 | plain-dir |  |
| `IndependentRevisionRaceTmp` | 0 | plain-dir |  |
| `local-candidate-commit-test-06f1b4d83a6145dba4cc6c4463bbf474` | 0 | plain-dir |  |
| `local-candidate-commit-test-078ddec6dc5e4c0ea9d301bf07549bfa` | 0 | plain-dir |  |
| `local-candidate-commit-test-1806e82154514e60a28ba449bc03a44a` | 0 | plain-dir |  |
| `local-candidate-commit-test-39bf476c226944f2af7b1a6d25295c97` | 0 | plain-dir | 2026-09-09T06:36:18Z |
| `local-candidate-commit-test-634c18f81ef04839bf21d6c84541a76e` | 0 | plain-dir |  |
| `local-candidate-commit-test-690d5012caad4638be83ce8ed83c76be` | 0 | plain-dir |  |
| `local-candidate-commit-test-69e71e9e076341128f463e5811ff403b` | 0 | plain-dir |  |
| `local-candidate-commit-test-808bdbc934f94b7694e1560a9fe8fd6d` | 0 | plain-dir | 2026-09-09T05:25:27Z |
| `local-candidate-commit-test-88565aca9e9a47e5956ee994ffdf5bf8` | 0 | plain-dir |  |
| `local-candidate-commit-test-92e131688ddf485089f810d047f38fb1` | 0 | plain-dir | 2026-09-09T05:25:34Z |
| `local-candidate-commit-test-960ebb7c3c2343219f7e1df33f315295` | 0 | plain-dir |  |
| `local-candidate-commit-test-9fcc243361e24c2fb58455971a779e42` | 0 | plain-dir |  |
| `local-candidate-commit-test-b341adf2c00e431ea52be583285efdac` | 0 | plain-dir | 2026-09-09T06:34:12Z |
| `local-candidate-commit-test-cdafdaa382ee49b9a06d4ffc41a395e9` | 0 | plain-dir | 2026-09-09T05:25:33Z |
| `local-candidate-commit-test-d3559480e6db4294b4b40f9bf3e556c8` | 0 | plain-dir | 2026-09-09T05:25:28Z |
| `local-candidate-commit-test-dc23321a35b9468ca32018a66ed3bed1` | 0 | plain-dir |  |
| `local-candidate-commit-test-dc85eb94374644b48d7a33cc151aa0a4` | 0 | plain-dir |  |
| `local-candidate-commit-test-e2f6ddb276cb4b6fa3cd49ee761224f5` | 0 | plain-dir |  |
| `local-candidate-commit-test-fe4d80b2d9c6448eb4132b09fbb62423` | 0 | plain-dir | 2026-09-09T05:25:35Z |
| `local-source-integration-test-25bdc5956c6748c39921a37f69eb8402` | 0.1 | plain-dir | 2026-09-09T05:46:13Z |
| `local-source-integration-test-4e69d1730a59401b9920f1ef0635de62` | 0 | plain-dir |  |
| `local-source-integration-test-a87b54bc5cd14551a32ed343ba8c35b1` | 0 | plain-dir |  |
| `local-source-integration-test-b7970bda560a41c8a26368721eb8a27d` | 0 | plain-dir |  |
| `local-source-integration-test-d0064a5641f543c0858c0e3f65555799` | 0 | plain-dir |  |
| `local-source-integration-test-f0b28783b802467bb7c756adfd1a6b7b` | 0 | plain-dir |  |
| `local-source-integration-test-faad17d023094e3f8cca336469736856` | 0 | plain-dir |  |
| `MermaidToReadme` | 0 | plain-dir | 2026-08-05T02:22:11Z |
| `MuffcabbageDeepEvidence` | 0.5 | plain-dir | 2026-09-05T08:53:05Z |
| `NoSafeCircle_TargetedHumanRepair` | 0 | plain-dir | 2026-08-05T00:14:44Z |
| `NoSafeCirclePayload` | 0 | plain-dir | 2026-08-04T23:48:57Z |
| `nsc local decomp ys8gec9a` | 0 | plain-dir |  |
| `nsc-auth-observe-ehybg3th` | 0 | plain-dir |  |
| `nsc-auth-observe-gqq9x0si` | 0 | plain-dir |  |
| `nsc-gauntlet-view` | 0.7 | plain-dir | 2026-09-06T09:39:34Z |
| `nsc-local-human-bnv8m1q4` | 0 | plain-dir |  |
| `nsc-pooled-decomposition-2dl6vcsy` | 0 | plain-dir |  |
| `nsc-pooled-decomposition-uvt_5mbs` | 0 | plain-dir |  |
| `nsc-profile-autocrlf-v_4gqd2z` | 0 | plain-dir |  |
| `PerfAudit20260909` | 0 | plain-dir | 2026-09-09T04:32:58Z |
| `PerfTmp` | 0 | plain-dir |  |
| `PipelinePauseTestTmp` | 0 | plain-dir |  |
| `profile-owner-ri698pak` | 0 | plain-dir |  |
| `ProviderBoundaryBootstrapFollowonAuthoredTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryBootstrapFollowonFullTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryBootstrapFollowonIdentityTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryBootstrapFollowonOriginalTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryBootstrapFollowonStrictTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherAuditEvidence-20260908` | 0.6 | plain-dir | 2026-09-08T22:55:08Z |
| `ProviderBoundaryLauncherAuditTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherAuditTempNative-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherD59IdentityTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherD59IndependentTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherD59Temp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherD59Temp2-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherIdentityTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherIdentityTemp2-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherIndependentTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherProfileCoreTemp-20260908` | 0 | plain-dir |  |
| `ProviderBoundaryLauncherProfilesTemp-20260908` | 0 | plain-dir |  |
| `ProviderCheckpointAEvidence` | 0.1 | plain-dir | 2026-09-05T10:50:06Z |
| `ProviderProfilesRoutingEvidence-20260907` | 4.9 | plain-dir | 2026-09-07T03:20:44Z |
| `ProviderProfilesTestTemp-20260907` | 0 | plain-dir |  |
| `ProviderProfilesTestTemp-Auto` | 0 | plain-dir |  |
| `ProviderProfilesTestTemp-Evidence` | 0 | plain-dir |  |
| `ProviderProfilesTestTemp-Final` | 0 | plain-dir |  |
| `ProviderProfilesTestTemp-Gate` | 0 | plain-dir |  |
| `ProviderProfilesTestTemp-Poll` | 0 | plain-dir |  |
| `provider-session-test-temp-elevated-0904` | 0 | plain-dir |  |
| `ProviderSmokeVerify-20260906` | 25.6 | worktree | 2026-09-06T10:43:14Z |
| `PublicGateAdversarialAudit-20260907T033720Z-evidence` | 132.9 | plain-dir | 2026-09-07T03:55:42Z |
| `PublicIntegrationAuthorityTestTemp-20260907` | 0 | plain-dir |  |
| `PublicIntegrationF16-Final-20260907` | 0 | plain-dir | 2026-09-07T04:08:21Z |
| `PublicIntegrationF1-Base-20260907` | 0 | plain-dir | 2026-09-07T04:09:27Z |
| `PublicIntegrationF235-Final-20260907` | 0 | plain-dir | 2026-09-07T04:07:51Z |
| `PublicIntegrationF2-Final-20260907` | 0 | plain-dir | 2026-09-07T04:08:15Z |
| `PublicIntegrationF3-Discovery-Base-20260907` | 0 | plain-dir | 2026-09-07T04:10:29Z |
| `PublicIntegrationF3-Discovery-BaseCompatible-20260907` | 0 | plain-dir | 2026-09-07T04:11:04Z |
| `PublicIntegrationF3-Discovery-Final-20260907` | 0 | plain-dir | 2026-09-07T04:10:28Z |
| `PublicIntegrationF3-Discovery-FinalCompatible-20260907` | 0 | plain-dir | 2026-09-07T04:11:39Z |
| `PublicIntegrationF4-Final-20260907` | 0 | plain-dir | 2026-09-07T04:08:23Z |
| `PublicIntegrationF5-Base-20260907` | 0 | plain-dir | 2026-09-07T04:07:55Z |
| `PublicIntegrationF7-Final-20260907` | 0 | plain-dir | 2026-09-07T04:08:12Z |
| `PublicPipelineBaseAcceptanceDiagnostic-20260907` | 1.4 | plain-dir | 2026-09-07T03:53:53Z |
| `PublicPipelineBasePolicyValidation-20260907` | 0 | plain-dir | 2026-09-07T03:20:06Z |
| `PublicPipelineBaseValidation-20260907` | 0 | plain-dir | 2026-09-07T03:06:35Z |
| `PublicPipelineBaseVerification-20260907` | 36.9 | repo | 2026-09-07T03:06:33Z |
| `PublicPipelineCanonicalTempValidation-20260907` | 0 | plain-dir | 2026-09-07T03:07:52Z |
| `PublicPipelineFinalAcceptanceDiagnostic-20260907` | 1.5 | plain-dir | 2026-09-07T03:53:31Z |
| `PublicPipelineFinalValidation-20260907` | 0.4 | plain-dir | 2026-09-07T04:03:27Z |
| `PublicPipelineFixtureTemp-20260907` | 1.1 | plain-dir | 2026-09-07T04:09:27Z |
| `PublicPipelineFixtureValidation-20260907` | 0 | plain-dir | 2026-09-07T03:31:43Z |
| `PublicPipelineObservationPoolValidation-20260907` | 0 | plain-dir | 2026-09-07T03:39:16Z |
| `PublicPipelineObservationValidation-20260907` | 0.1 | plain-dir | 2026-09-07T03:42:28Z |
| `PublicPipelineSmallFollowupValidation-20260907` | 0 | plain-dir | 2026-09-07T04:17:15Z |
| `PublicPipelineValidation-20260907` | 0.4 | plain-dir | 2026-09-07T03:23:34Z |
| `PublicWorkflowRecoveryFix-20260907-evidence` | 2 | plain-dir | 2026-09-07T05:29:10Z |
| `red-6pwy2bpn` | 0 | plain-dir |  |
| `Rehearsal` | 31676.5 | plain-dir | 2026-09-09T10:20:55Z |
| `RehearsalAuditFixMatrixTemp` | 0 | plain-dir |  |
| `RehearsalAuditFixTestTemp` | 0 | plain-dir |  |
| `RehearsalAuditFixTestTemp2` | 0 | plain-dir |  |
| `RehearsalAuditFixTestTemp3` | 0 | plain-dir |  |
| `RehearsalAuditFixTestTemp4` | 0 | plain-dir |  |
| `RehearsalAuditFixTestTemp5` | 0 | plain-dir |  |
| `RehearsalDecompAuditTemp` | 0 | plain-dir |  |
| `RehearsalDecompAuditTemp2` | 0 | plain-dir |  |
| `RehearsalDecompAuditTemp3` | 0 | plain-dir |  |
| `RehearsalDecompAuditTemp4` | 0 | plain-dir |  |
| `RehearsalDecompAuditTemp5` | 0 | plain-dir |  |
| `RehearsalEvidenceBindingEvidence` | 0 | plain-dir | 2026-09-05T11:01:51Z |
| `RehearsalGauntletFixtureFinalTemp` | 0 | plain-dir |  |
| `RehearsalGauntletGeneratorTemp` | 0 | plain-dir |  |
| `RehearsalMuffAcceptanceTemp` | 0 | plain-dir |  |
| `RehearsalPrepareGauntletTemp2` | 0 | plain-dir |  |
| `RehearsalPrepareGauntletTemp3` | 0 | plain-dir |  |
| `RehearsalRunnerBoundaryTemp` | 0 | plain-dir |  |
| `RehearsalThousandDecompositionTemp` | 0 | plain-dir |  |
| `RehearsalThousandDecompositionTemp2` | 0 | plain-dir |  |
| `RehearsalThousandDecompositionTemp3` | 0 | plain-dir |  |
| `RehearsalThousandGenerationTemp2` | 0 | plain-dir |  |
| `RehearsalThousandSchedulerTemp` | 0 | plain-dir |  |
| `RepropagateRetryTests` | 0 | plain-dir |  |
| `ResetFastForwardTestTemp` | 0 | plain-dir |  |
| `ResetTaskFullSuite-20260908-full-reset-suite` | 0 | plain-dir |  |
| `ResetTempRootHarnessFix` | 81.9 | plain-dir | 2026-09-05T13:11:46Z |
| `ResetTestTemp` | 0 | plain-dir |  |
| `RetiredCompletionFix` | 31.4 | plain-dir | 2026-09-05T12:26:31Z |
| `ReviewCrossProviderCrew-cc75a2b6` | 136.1 | plain-dir | 2026-09-06T02:17:49Z |
| `review-reset-tests` | 70.7 | plain-dir | 2026-09-04T18:08:39Z |
| `ReviewTemp` | 0.9 | plain-dir | 2026-09-05T13:21:14Z |
| `review-temp-471-elevated` | 0 | plain-dir |  |
| `review-temp-a264` | 0 | plain-dir |  |
| `review-temp-a264-elevated` | 0 | plain-dir |  |
| `review-temp-crewpool` | 0 | plain-dir |  |
| `review-temp-crewpool-303` | 0.2 | plain-dir | 2026-09-06T02:18:06Z |
| `review-temp-crewpool-c0dd` | 0 | plain-dir |  |
| `review-temp-crewpool-c0dd-escalated` | 2 | plain-dir | 2026-09-06T02:18:12Z |
| `review-temp-crewpool-d52` | 0 | plain-dir |  |
| `review-temp-crewpool-escalated` | 0 | plain-dir |  |
| `ReviewTRA-Adversarial-Temp-20260908` | 0 | plain-dir |  |
| `ReviewTRA-Adversarial-Temp-Elevated-20260908` | 0 | plain-dir |  |
| `ReviewTRA-Adversarial-Workflow-Temp-20260908` | 0 | plain-dir |  |
| `ReviewTRA-Evidence-20260908` | 8.8 | plain-dir | 2026-09-08T08:36:30Z |
| `rp23-fixtures-20260909` | 0 | plain-dir |  |
| `RunEvidenceTestTemp-20260906` | 0 | plain-dir |  |
| `SchedulerObservationEvidence-20260907` | 0.4 | plain-dir | 2026-09-07T03:12:49Z |
| `SchedulerWaitTestTmp` | 0 | plain-dir |  |
| `scratch` | 0 | plain-dir |  |
| `SD-20260909-040642` | 554.5 | plain-dir | 2026-09-09T04:48:07Z |
| `SolLocalAutoApprovalCandidate2-20260909` | 0.6 | plain-dir | 2026-09-09T06:35:55Z |
| `StartupHistoryUncommitted-20260909` | 73.2 | plain-dir | 2026-09-09T02:47:00Z |
| `StrandedGateOwnerRecoveryEvidence-20260908` | 0.1 | plain-dir | 2026-09-08T11:27:18Z |
| `synthetic-approver-z4bsm8a9` | 0 | plain-dir |  |
| `SyntheticDecompPumpFixTemp` | 0 | plain-dir |  |
| `SyntheticPumpOne` | 31.1 | plain-dir | 2026-09-04T13:41:40Z |
| `TargetedControls` | 0 | plain-dir | 2026-08-05T00:24:51Z |
| `TaskAgentTestTemp-20260905` | 0 | plain-dir | 2026-09-05T23:20:36Z |
| `TaskControlCurrentState-evidence` | 278.3 | plain-dir | 2026-09-07T14:20:56Z |
| `TaskControlCurrentState-test-temp` | 0 | plain-dir |  |
| `TaskGraphPerf` | 34.9 | plain-dir | 2026-09-05T15:10:38Z |
| `TaskReviewAgentTemp` | 0 | plain-dir |  |
| `TaskReviewTemp` | 0 | plain-dir |  |
| `TaskReviewTempEscalated` | 0 | plain-dir |  |
| `taskreview-test-temp` | 0 | plain-dir |  |
| `taskreview-test-temp-rehearsal` | 0 | plain-dir |  |
| `tc-temp` | 0 | plain-dir | 2026-09-07T14:18:52Z |
| `TempEvidenceTests` | 0 | plain-dir |  |
| `TempEvidenceTests2` | 0 | plain-dir |  |
| `temp-probe-locality` | 0 | plain-dir |  |
| `TempRuns` | 0 | plain-dir | 2026-09-05T22:32:48Z |
| `TempWakeTests` | 0 | plain-dir |  |
| `TempWakeTests2` | 0 | plain-dir |  |
| `TenTaskFinalIntegration-20260905-Checkouts` | 5548.4 | plain-dir | 2026-09-11T05:55:33Z |
| `TenTaskFinalIntegration-20260905-Runs` | 104.7 | plain-dir | 2026-09-10T14:46:58Z |
| `TenWorkerReadinessEvidence` | 10 | plain-dir | 2026-09-05T11:31:49Z |
| `TestTemp` | 3.1 | plain-dir | 2026-09-05T12:02:04Z |
| `test-temp` | 0 | plain-dir |  |
| `test-temp-codex-author` | 0 | plain-dir |  |
| `TestTempCrossProvider` | 0 | plain-dir |  |
| `TestTemp-SyntheticPreverification` | 0 | plain-dir |  |
| `testtmp` | 0 | plain-dir |  |
| `testtmp-locality` | 0 | plain-dir |  |
| `testtmp-locality2` | 0 | plain-dir |  |
| `ThirdActivityShapeDynamicAudit-20260908` | 0 | plain-dir | 2026-09-08T22:41:16Z |
| `ThirdGauntletActivityAuditTemp-20260908` | 0 | plain-dir |  |
| `ThirdGauntletBootstrapCrossAuditTemp-20260908` | 0 | plain-dir |  |
| `ThirdGauntletBootstrapCrossAuditTemp-3fa7c9b8-20260908` | 0 | plain-dir |  |
| `ThirdGauntletEvidence-20260908` | 143.5 | plain-dir | 2026-09-09T08:08:58Z |
| `ThousandGauntletTests` | 0.1 | plain-dir | 2026-09-06T02:18:00Z |
| `ThousandReadinessEvidence` | 88.1 | plain-dir | 2026-09-06T02:18:01Z |
| `thousand-scheduler-bzseet5p` | 0 | plain-dir |  |
| `tmp` | 0 | plain-dir |  |
| `tmp19uvh05d` | 0 | plain-dir |  |
| `tmp2veqlt77` | 0 | plain-dir |  |
| `tmp4ajxh8_5` | 0 | plain-dir |  |
| `tmp75r5o_6p` | 0 | plain-dir |  |
| `tmp7a2k_y2s` | 0 | plain-dir |  |
| `tmpabp3ftbt` | 0 | plain-dir |  |
| `tmpbmcoxw2f` | 0 | plain-dir |  |
| `tmpgibqfj3g` | 0 | plain-dir |  |
| `tmpign31vk9` | 0 | plain-dir |  |
| `tmpmef00z5_` | 0 | plain-dir |  |
| `tmpnt5dlb68` | 0 | plain-dir |  |
| `tmpp3qh8c09` | 0 | plain-dir |  |
| `TmpPerf` | 0 | plain-dir |  |
| `tmpq4kijqav` | 0 | plain-dir |  |
| `tmpqpgwc6dh` | 0 | plain-dir |  |
| `tmprcn8h_sf` | 0 | plain-dir |  |
| `tmprcp57a16` | 0 | plain-dir |  |
| `tmp-sol-fable-tests` | 0.1 | plain-dir | 2026-09-09T03:42:45Z |
| `tmpvj482l1j` | 0 | plain-dir |  |
| `tmpx4bhs402` | 0 | plain-dir |  |
| `tmpz1b8svto` | 0 | plain-dir |  |
| `tmpzpsy50h_` | 0 | plain-dir |  |
| `TwoLocalGauntletDemo-t20260909-015701z` | 850 | plain-dir | 2026-09-09T10:21:39Z |
| `ViewerIntegrityAudit-20260908-claudehistory` | 606.8 | plain-dir | 2026-09-08T22:06:37Z |
| `W1AuditTemp` | 0 | plain-dir |  |
| `W1AuditTemp65d` | 0 | plain-dir |  |

## 7. Full `ask` list - 330 directories, needs Vincent's per-item (or per-batch) decision

| Name | Size (MB) | Reason |
|---|---|---|
| `.assistant-test-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T03:44:48Z (folder itself was created/changed recently, even if empty now)) |
| `.claude` | 0 | modified within last 7 days (folder's own last-write 2026-09-18T19:10:49Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T06:55:03Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-assistant-ci-tests` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:42:02Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-assistant-ci-tests-elevated` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:42:23Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-assistant-tests` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T22:47:27Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-compat` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:00:58Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-decomp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:44:03Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-decomp-final` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:13:35Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-extracted-decomp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:12:31Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-full` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:48:11Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-postcrew` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:44:05Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-provider` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:08:40Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-provider-2` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:09:14Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-provider-3` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:09:41Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-provider-profiles` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:16:06Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-publication` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:45:16Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-pycache-release` | 12.6 | modified within last 7 days (newest file 2026-09-14T07:09:51Z) |
| `.tmp-ci-taskdecomp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:02:49Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-taskdecomp-2` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:04:28Z (folder itself was created/changed recently, even if empty now)) |
| `.tmp-ci-viewer` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T08:44:06Z (folder itself was created/changed recently, even if empty now)) |
| `.unity-runs` | 5.8 | modified within last 7 days (newest file 2026-09-14T12:08:18Z) |
| `__pycache__` | 0 | modified within last 7 days (newest file 2026-09-13T04:53:45Z) |
| `_bg_reverse_merge` | 0.7 | modified within last 7 days (newest file 2026-09-12T10:16:27Z) |
| `_worktrees` | 57437.7 | modified within last 7 days (newest file 2026-09-14T14:29:31Z) |
| `ActiveWorkerArchitectSpend-20260908` | 39 | git: branch 'fix/active-worker-architect-spend' @ 73b693935e463ef01ea7e6035bf03210b2660e27 not confirmed merged into canonical main |
| `ActiveWorkerArchitectSpend-Red-20260908` | 38.4 | git: branch 'HEAD' @ 02ddf7ccd2733559f43002e6528217b2a6ff7756 not confirmed merged into canonical main |
| `AgentBranchFixesMerge-20260909` | 37.1 | git: branch 'integration/agent-branch-fixes-20260909' @ 02fa080a96b302f7e40fb7b6e251165fc5b4d28d not confirmed merged into canonical main |
| `ArchitectCapacityCooldown-20260908` | 39.6 | git: branch 'fix/architect-capacity-cooldown' @ 250a21d7d1e30a6661e3bf1cffd1f635974845db not confirmed merged into canonical main |
| `assistant-background-focused-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:32:46Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-background-real-stop-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:33:15Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-background-regression-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:36:49Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-ci-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:22:17Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-ci-temp-external` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:23:00Z (folder itself was created/changed recently, even if empty now)) |
| `AssistantControlAuditTemp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T12:31:44Z (folder itself was created/changed recently, even if empty now)) |
| `AssistantControlCloneProbeBundle-20260912` | 7.9 | git: 1374 uncommitted non-Unity-noise change(s) |
| `AssistantControlFocusedTemp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T12:59:42Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-controller-stop-temp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:33:30Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-controller-stop-temp-2` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:34:10Z (folder itself was created/changed recently, even if empty now)) |
| `assistant-controller-stop-temp-3` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:35:01Z (folder itself was created/changed recently, even if empty now)) |
| `AssistantControlSteeringGuard-20260912` | 37.3 | git: branch 'assistant-control/action-boundary-steering' @ 7942a768f992a05fd94106a509faa311a78bf597 not confirmed merged into canonical main |
| `AssistantControlTestTemp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T12:56:08Z (folder itself was created/changed recently, even if empty now)) |
| `AssistantControl-TestTemp` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T09:58:50Z (folder itself was created/changed recently, even if empty now)) |
| `AssistantControlViewerRegression-20260913` | 142.6 | git: branch 'assistant/viewer-regression-suite-20260913' @ c12f70287bad1b97e66e8e5fbee1710aaa70c33c not confirmed merged into canonical main |
| `assistant-integration-patches` | 0.1 | modified within last 7 days (newest file 2026-09-12T09:21:25Z) |
| `AstraAutomaticDecompStateCandidate-20260909` | 39.3 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 6 uncommitted non-Unity-noise change(s) |
| `AstraCandidateCloneAudit-20260909` | 37.1 | git: branch 'HEAD' @ 02fa080a96b302f7e40fb7b6e251165fc5b4d28d not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `AstraChildProvenanceReadCandidate-20260909` | 36.9 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `AstraCleanupDurableWorkers-20260909` | 36.6 | git: branch 'fix/local-cleanup-durable-workers-20260909' @ 7420b448a17ee19db3b46fbb730ed74591444397 not confirmed merged into canonical main |
| `AstraConvergenceCombined-20260909` | 36.6 | git: branch 'audit/astra-convergence-combined-20260909' @ 8ae32cf7638cbbd4af15fcbd6af0a7485a8b7ed4 not confirmed merged into canonical main |
| `AstraConvergenceFreshSeed-20260909` | 36.5 | git: branch 'fix/convergence-fresh-seed-20260909' @ b87bc7e2517362380a38b68c2ca3d66b3586216a not confirmed merged into canonical main |
| `AstraConvergenceLauncherCombined-20260909` | 36.6 | git: branch 'audit/astra-convergence-launcher-20260909' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main |
| `AstraConvergenceRepair-20260908` | 154.9 | git: branch 'fix/astra-convergence-20260908' @ 38c96e205c58beaf3fed971eff141ceee04c5af4 not confirmed merged into canonical main |
| `AstraDecompHarvestCandidate-20260909` | 47.6 | git: branch 'HEAD' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `AstraDecompRaceCandidate-20260909` | 36.7 | git: branch 'HEAD' @ bc3b7c6e6f72deccb3f00f613d7786e38002d980 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `AstraDecompWakeCandidate-20260909` | 38.8 | git: branch 'HEAD' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `AstraLocalContractBatch-20260909` | 36.6 | git: branch 'HEAD' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main; also: 5 uncommitted non-Unity-noise change(s) |
| `AstraLocalDecompIntegration-20260909` | 36.8 | git: branch 'audit/single-decomposition-20260909-040642' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main |
| `AstraLocalRevisionReadRaceCandidate-20260909` | 39.3 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `AstraReview-42339d179` | 35.7 | git: branch 'HEAD' @ 42339d179439638a309197de4a557890a846ca51 not confirmed merged into canonical main |
| `AstraReviewBase-ac2a93fdf` | 35.2 | git: branch 'HEAD' @ ac2a93fdf7fd457d2c6f26c02071127c110b1df0 not confirmed merged into canonical main |
| `AstraSourceWaitLoopCandidate-20260909` | 37.1 | git: branch 'HEAD' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `AstraTaskcontrolHistoryCandidate-20260909` | 36.6 | git: branch 'HEAD' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main; also: 5 uncommitted non-Unity-noise change(s) |
| `AuthenticatedGddRagDecomposition-20260912` | 37.4 | git: branch 'codex/authenticated-gdd-rag-decomposition' @ 21c59bec42fd025acaa58170fe15e68c2c1a48a7 not confirmed merged into canonical main |
| `AutomatedGateOwnerResume-20260908` | 39.7 | git: branch 'fix/automated-gate-owner-resume' @ d7dc6258959bfafa4f89f6bd6ee55cccf69fe493 not confirmed merged into canonical main |
| `BoundPrRepoll-20260908` | 51.7 | git: branch 'fix/bounded-merge-closeout-repoll' @ ac2a93fdf7fd457d2c6f26c02071127c110b1df0 not confirmed merged into canonical main |
| `BranchlessPushedReset-20260908` | 38.2 | git: branch 'fix/branchless-pushed-rehearsal-reset' @ 401a7c87b98454cf212783a3aaecf77217442a61 not confirmed merged into canonical main |
| `BulkRetirementFilter` | 31.7 | git: branch 'codex/bulk-retired-completion-filter' @ 0e8a06392ac5751bdb6ae68d01a382824cd6aa20 not confirmed merged into canonical main |
| `BulkRetirementTests` | 79.3 | git: branch 'codex/test-bulk-retirement-filter' @ 1ce149360492891567e926b99e1288dccb578c22 not confirmed merged into canonical main |
| `CandidateGateAbsoluteFifo-20260908` | 51.7 | git: branch 'fix/candidate-gate-absolute-fifo' @ 7dae2fa5d3a6bd4f30dc2b16e5b025007b299708 not confirmed merged into canonical main |
| `CheckoutRaceLeaseRelease-20260908` | 38.9 | git: branch 'fix/checkout-race-lease-release' @ 233df51d8ffc04f883808c04c16f3405f068fe19 not confirmed merged into canonical main |
| `CheckoutRaceLeaseRelease-Base-20260908` | 37.7 | git: branch 'HEAD' @ 0d5af9cf1d08c0fc9991b04dad45061667d345e0 not confirmed merged into canonical main |
| `CheckoutRootExactHead-20260908` | 35.4 | git: branch 'fix/checkout-root-exact-pr-head' @ 98c9bac41fb411f84113c4b23a753d07ea85191d not confirmed merged into canonical main |
| `ClaudeAdmissionSnapshot-20260905` | 73.9 | modified within last 7 days (newest file 2026-09-18T23:26:25Z) |
| `ClaudeForcedTestAuthorBenchmark-20260907` | 46.7 | git: branch 'HEAD' @ ce6fbc28eb3e1a2d835d3af4a082a8cd4eaacbaa not confirmed merged into canonical main |
| `ClaudeGuidanceDriver-20260914` | 0 | modified within last 7 days (folder's own last-write 2026-09-14T05:07:13Z (folder itself was created/changed recently, even if empty now)) |
| `ClaudeIntegBench-20260908t1855z` | 177.5 | modified within last 7 days (newest file 2026-09-18T23:26:26Z) |
| `ClaudeReconcileOnConvergence-20260908` | 39.4 | git: branch 'fix/local-decomp-reconcile-on-convergence-20260908' @ 9bf6ee5d92e2d9c0466ebf00f2d00d7a3ae66d20 not confirmed merged into canonical main |
| `ClaudeSessionRecovery-20260908` | 152.5 | git: branch 'fix/claude-stale-pooled-session-recovery-20260908' @ 49a3e00a8d95df46fe79aa2f3209cf6502fcf3dd not confirmed merged into canonical main |
| `ClaudeSonnetCodexMcpAudit-20260909` | 156.8 | git: branch 'fix/claude-sonnet-codex-mcp-transport-20260909' @ 23c37bc5d7d39e6e7a282e2ddf53e136d7902ed2 not confirmed merged into canonical main |
| `ClaudeSonnetConvergenceAudit-20260908` | 156.2 | git: branch 'audit/claude-sonnet-tls-polluted-seed-20260908' @ ea6ca75ef87304d28945638a9bcdd96e41f77f9e not confirmed merged into canonical main |
| `ClaudeSonnetDecompAudit-20260909` | 49.5 | git: branch 'audit/claude-sonnet-decomposition-apply-20260909' @ 85f44af2854af3d7f000a9a1a1943274f7acfe06 not confirmed merged into canonical main |
| `ClaudeViewerDiag-20260908` | 36.6 | git: branch 'HEAD' @ eda47e0f4cf6fb64c91e4ed5d7ef72b81148a7ea not confirmed merged into canonical main |
| `CodexArchitectSessionFix` | 82.5 | git: branch 'codex/architect-quota-handoff' @ ec738da52f90532b60063453b6975a63060bf22e not confirmed merged into canonical main |
| `CodexGauntletFixIntegration-20260908` | 39.6 | git: branch 'integration/codex-gauntlet-fixes-20260908' @ f376359ba9981a4432132849c3195073f2d34bff not confirmed merged into canonical main |
| `CodexLeaseDeadlock-20260908` | 36.4 | git: branch 'fix/codex-local-lease-eddeadlk-20260908' @ 7f5e646c9907573acc8884aac11ca82cac906782 not confirmed merged into canonical main |
| `CodexLeaseDeadlock-ClaudeCrossTest-20260908` | 36.4 | git: branch 'HEAD' @ 7838e9463461c0330c14198969f1bdb680701cb7 not confirmed merged into canonical main |
| `CodexLocalBootstrapApplyCheck-20260908` | 49.8 | git: branch 'HEAD' @ 69348cbf2e75c77fd32bb371a600567ff391f559 not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `CodexLocalBootstrapFix-20260908-v2` | 10.5 | git: branch 'main' @ 151454913401e9c137d09969986d89fd57909064 not confirmed merged into canonical main; also: 1544 uncommitted non-Unity-noise change(s) |
| `CodexLocalBootstrapFix-Archive-20260908` | 53 | git: branch 'fix/local-codex-bootstrap-20260908' @ cba8f240f8a12fb8a33533a73d892a41b9bbd77d not confirmed merged into canonical main |
| `CodexProviderRestriction` | 82.7 | git: branch 'codex/persist-provider-restrictions' @ 110d28337d9fefa55924d9c76da31689dca16164 not confirmed merged into canonical main |
| `CodexQuotaFailover` | 80.6 | git: branch 'codex/claude-quota-failover' @ d2f06c0f00719ae93aad44e0b45a03bf816c690f not confirmed merged into canonical main |
| `CodexRetryRoleModels-20260908` | 50.4 | git: branch 'fix/committed-role-model-retry' @ 8809f51d951354a89accdea539461a654c6eaa11 not confirmed merged into canonical main |
| `CoherentSnapshotAdapter` | 37.1 | git: branch 'codex/production-coherent-snapshot' @ 61832b61fa99141fda6abfaee2aceeee83d07901 not confirmed merged into canonical main |
| `CombinedScale-20260905-18c867c` | 31.2 | git: branch 'codex/combine-orchestration-scale' @ 2bc1a29636f33edcaa78775c2cfcfff189156447 not confirmed merged into canonical main |
| `CrossProviderRetryIntegration-20260905-18c867c` | 40.6 | git: branch 'codex/integrate-cross-provider-retry' @ 1a7b748cb3d6bf5e4030ac1992564d1e90247c5a not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `CrossProviderRetryRedBefore` | 28.2 | git: branch 'HEAD' @ 9be53e8a1ba1ab87ad0713b098df063033b101e2 not confirmed merged into canonical main |
| `DecompositionPolicyShapeTests-20260912` | 37.5 | git: branch 'test/decomposition-policy-shape-20260912' @ 0f49de4f299c919f2e75af2a91b227a6e5e4357c not confirmed merged into canonical main |
| `DecompositionResumeRouteFix` | 31.4 | git: branch 'codex/fix-required-decomposition-resume-route' @ 18c867c33ee9aba27c9c68c1c0b05b2a37eb1321 not confirmed merged into canonical main |
| `DecompPendingTmp` | 0 | modified within last 7 days (folder's own last-write 2026-09-13T22:44:54Z (folder itself was created/changed recently, even if empty now)) |
| `DeliveryProposalDefaults-20260905` | 32.2 | git: branch 'fix/delivery-review-proposal-defaults' @ 213d3cbed3d471d9941fe46497ee50802af5b286 not confirmed merged into canonical main |
| `DependencyBlockedPortfolioCandidate-20260909` | 40.6 | git: branch 'fix/dependency-blocked-portfolio-20260909' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `DownstreamIssueLocality-20260908` | 39.1 | git: branch 'fix/downstream-issue-locality' @ dcb4e313fb3b26503f72e93eca362d117b0574b2 not confirmed merged into canonical main |
| `DurableIntegrationCommitGate-20260906` | 69.8 | git: branch 'fix/durable-integration-commit-gate' @ 28d428ab99a183f4c82fc43c1ab4e24314864d8e not confirmed merged into canonical main |
| `DurableIntegrationGateBase-20260906` | 65.4 | git: branch 'HEAD' @ 7749a37dd606621515bc2ed25048558f026660d2 not confirmed merged into canonical main |
| `FableAuditCand-38c96e2` | 38.6 | git: branch 'HEAD' @ 38c96e205c58beaf3fed971eff141ceee04c5af4 not confirmed merged into canonical main |
| `FableAuditCand-eda47e0` | 36.6 | git: branch 'HEAD' @ eda47e0f4cf6fb64c91e4ed5d7ef72b81148a7ea not confirmed merged into canonical main |
| `FableAuditCombined` | 36.6 | git: branch 'audit/fable-combined-20260908' @ cbf713c4502052dbcc6bb863fec6eb0cdb78f6a2 not confirmed merged into canonical main |
| `FableAuditMix-parentprod` | 36.5 | git: branch 'HEAD' @ 971e1b002301097bcfb38611ee70037a9cfa6412 not confirmed merged into canonical main |
| `FableConvergenceAudit-20260908` | 157.2 | git: branch 'audit/fable-convergence-20260908' @ 971e1b002301097bcfb38611ee70037a9cfa6412 not confirmed merged into canonical main |
| `FableDecompApply-20260909` | 36.7 | git: branch 'fix/fable-local-decomposition-apply-20260909' @ 69efedd7499ecf03df1e4bbaaadca7553e208e65 not confirmed merged into canonical main |
| `FableDecompHarden-20260909` | 37 | git: branch 'fix/fable-local-decomposition-hardening-20260909' @ 095f1347103bc86af135a81d1070b11513f87d25 not confirmed merged into canonical main |
| `FableDecomposeDesign-20260909` | 37 | git: branch 'fable/decompose-design-20260909' @ 8f61ce22c10ebffd99195eec0b09be328f8c4429 not confirmed merged into canonical main |
| `FableMergeAgentDesign-20260909` | 37.1 | git: branch 'fable/merge-agent-design-20260909' @ 0b918a9f4829fd017297e47af065be7dd1938ce1 not confirmed merged into canonical main |
| `FableMergeProbe` | 38.7 | git: branch 'probe/rebased-on-tip' @ 85f44af2854af3d7f000a9a1a1943274f7acfe06 not confirmed merged into canonical main |
| `FailedQuiescentOwnerRestore-20260908` | 38.9 | git: branch 'fix/failed-quiescent-owner-restore' @ 02ddf7ccd2733559f43002e6528217b2a6ff7756 not confirmed merged into canonical main |
| `FixMainlineReintegration-20260905` | 42.6 | git: branch 'fix/synthetic-mainline-authority-live-gauntlet' @ de6083fd8b9f785535b8df38e1cfd3a6a0de6b61 not confirmed merged into canonical main |
| `FixMergedTaskRecovery-20260905` | 41.2 | git: branch 'fix/merged-task-closeout-recovery' @ 6c97e3fcb7038ca02dbb33c8c7818b1ea7dcd4af not confirmed merged into canonical main |
| `FixSyntheticPreVerificationProvenance-20260908` | 38.2 | git: branch 'fix/synthetic-preverification-provenance' @ 08c97902bc2a29d64da5d4019f204c38d4820578 not confirmed merged into canonical main |
| `FourDigitTaskId-20260905-09ae41ea-v6` | 39.3 | git: branch 'codex/four-digit-task-ids' @ c13d1956577b4a57ffe28ff7dacae38b6a184673 not confirmed merged into canonical main |
| `FourProfileFixIntegration-20260908` | 39.1 | git: branch 'integration/four-profile-fixes' @ 3b82da303cd1ad1d90a6c9a387b306a8bba4710f not confirmed merged into canonical main |
| `FourProfileIntegration-20260908` | 57.3 | git: branch 'integration/recovery-fixes-codex2-20260908' @ 0d5af9cf1d08c0fc9991b04dad45061667d345e0 not confirmed merged into canonical main |
| `G8FixAssembly-20260909` | 39.5 | git: branch 'HEAD' @ 0c6e79e9854891431c56b07c0636d115e252016e not confirmed merged into canonical main |
| `GateCleanupFix-20260908` | 39.3 | git: branch 'fix/post-settlement-gate-cleanup' @ 678c1019adfb327d4bcdd4e7745e7d6760cdb000 not confirmed merged into canonical main |
| `GateEligibleQueueFix-20260907` | 38.7 | git: branch 'fix/gate-eligible-queue-liveness' @ 4a10fb1a27231976b8733227aa0f96c67b36b95b not confirmed merged into canonical main |
| `GateEligibleQueueFixBase-20260907` | 38.2 | git: branch 'HEAD' @ 57aa2300b6c2a01aaf5b0d432fbe57dd56174fe4 not confirmed merged into canonical main |
| `GatePrecheckoutReservationFix-20260907` | 38.6 | git: branch 'fix/precheckout-reservation-proof' @ 3d69051b3465ba1241c97b4164e8ce81100549f4 not confirmed merged into canonical main |
| `GateResumeBase-20260907` | 66.3 | git: branch 'HEAD' @ 120ec005304508383db651985bceeb975d10bba2 not confirmed merged into canonical main |
| `GateResumeIntegration-20260907` | 33.2 | git: branch 'fix/gate-resume-cost-and-wake' @ bb560d0e56b77156b0d59cd1f60b1ac2fb02a371 not confirmed merged into canonical main |
| `GateWaiterArchitectBypass-20260907` | 66.9 | git: branch 'fix/gate-waiter-deterministic-resume' @ 5df5b7575fa857c259a054cfaa2121d16d7db132 not confirmed merged into canonical main |
| `GateWakeControllerFix-20260907` | 65 | git: branch 'fix/autonomous-gate-wake-contract' @ 58f30d2db4d4ddaf203e02d28d38f1d421b8eee4 not confirmed merged into canonical main |
| `GauntletAcceptedCombinedAudit-20260909` | 152.9 | git: branch 'audit/astra-convergence-combined-20260909' @ 8ae32cf7638cbbd4af15fcbd6af0a7485a8b7ed4 not confirmed merged into canonical main |
| `GauntletAssemblyRecoveryAudit-20260909` | 154.9 | git: branch 'HEAD' @ 02fa080a96b302f7e40fb7b6e251165fc5b4d28d not confirmed merged into canonical main |
| `GauntletCleanupAlternative-20260909` | 36.6 | git: branch 'audit/cleanup-context-ownership-20260909' @ 19bdd704411af2e3d79ca1145313868eac23abf9 not confirmed merged into canonical main |
| `GauntletCleanupFollowonAudit-20260909` | 152.9 | git: branch 'audit/cleanup-followon-20260909' @ 6461ae3dd7ea99f950daac8c882d2d80ed1f0ccf not confirmed merged into canonical main |
| `GauntletCleanupPausedAudit-20260909` | 152.9 | git: branch 'audit/cleanup-paused-20260909' @ 7420b448a17ee19db3b46fbb730ed74591444397 not confirmed merged into canonical main |
| `GauntletCodexMcpCandidateAudit-20260909` | 153.1 | git: branch 'audit/codex-mcp-candidate-20260909' @ b29a5e607cde922bd727aa37a0a5f2221b3cf53c not confirmed merged into canonical main |
| `GauntletCodexMcpFollowonAudit-20260909` | 153.1 | git: branch 'audit/codex-mcp-followon-20260909' @ e146b13d4571e915522c4b27367b484be4b92ec6 not confirmed merged into canonical main |
| `GauntletCodexRolePromptAudit-20260909` | 153.1 | git: branch 'HEAD' @ 23c37bc5d7d39e6e7a282e2ddf53e136d7902ed2 not confirmed merged into canonical main |
| `GauntletConvergenceIntegration-20260908` | 40.2 | git: branch 'integration/gauntlet-convergence-20260908' @ a64a147f00a47facbb52a047ea95e74f9edaf1a3 not confirmed merged into canonical main |
| `GauntletDecompositionCandidateAudit-20260909` | 153.5 | git: branch 'audit/decomposition-candidate-20260909' @ bc3b7c6e6f72deccb3f00f613d7786e38002d980 not confirmed merged into canonical main |
| `GauntletDecompositionWet-20260911-1` | 37.2 | git: branch 'gauntlet-replay/decomp-wet-20260911-1' @ 3b0396676b485208bb1ff2c2c44636813618b071 not confirmed merged into canonical main |
| `GauntletDecompositionWet-20260911-1-Checkouts` | 0 | modified within last 7 days (newest file 2026-09-12T02:43:36Z) |
| `GauntletDecompositionWet-20260911-2` | 49.9 | git: branch 'gauntlet-replay/decomp-wet-20260911-2' @ faac76ac524e93f2cae14edec65e9fd76a1a291c not confirmed merged into canonical main |
| `GauntletDecompositionWet-20260911-3` | 50.5 | git: branch 'gauntlet-replay/decomp-wet-20260911-3' @ 35eddc3549d1d60fcd657a3b703596387cf63fb0 not confirmed merged into canonical main |
| `GauntletDecompositionWet-20260911-4` | 52 | git: branch 'gauntlet-replay/decomp-wet-20260911-4' @ 4fca0d1ef64e572f96ea7e156e3f23cf3c1c785b not confirmed merged into canonical main |
| `GauntletDirectLaunchAudit-20260909` | 152.8 | git: branch 'audit/claude-sonnet-tls-polluted-seed-20260908' @ 563bea1e12d8c2c255e705b3a469ee7e3ea91593 not confirmed merged into canonical main |
| `GauntletDirectLaunchCases-20260909` | 152.8 | git: branch 'audit/direct-launch-cases-20260909' @ 563bea1e12d8c2c255e705b3a469ee7e3ea91593 not confirmed merged into canonical main |
| `GauntletDirectLaunchParentCases-20260909` | 152.8 | git: branch 'audit/direct-launch-parent-cases-20260909' @ 0daf0d623cff2038a02672579ceeda47aa2de8a7 not confirmed merged into canonical main |
| `GauntletFresh1130-20260912-1` | 37.7 | git: branch 'gauntlet-replay/fresh-1130-20260912' @ 73e0f067713ef74d9cf490b9d5175e2b55be3d8f not confirmed merged into canonical main |
| `GauntletFresh1130-20260912-1-Checkouts` | 0 | modified within last 7 days (newest file 2026-09-12T07:37:05Z) |
| `GauntletFresh1130Run-20260912-1` | 51 | git: branch 'gauntlet-replay/fresh-1130-20260912' @ 919eb1610b2cd58a30a6e66b98be0ce167944e9e not confirmed merged into canonical main |
| `GauntletFresh1140-20260912-1` | 52.7 | git: branch 'gauntlet-replay/fresh-1160-20260913' @ 62b2af516cdb849942023879e039c3355c6c40c8 not confirmed merged into canonical main |
| `GauntletFresh1160-FixesRun-20260913` | 53.2 | git: branch 'gauntlet-test/fixes-ade5bca-1160' @ a31fcef5914fc85724b93a18fe1ed4f794f996af not confirmed merged into canonical main |
| `GauntletFresh1160-Reviewed-20260913` | 38.5 | git: branch 'gauntlet-test/reviewed-async-1160' @ ff5e328be8aa53813b87ad17f0b9c5334dbb3b6e not confirmed merged into canonical main |
| `GauntletFresh1160-Reviewed-20260913-Checkouts` | 0 | modified within last 7 days (newest file 2026-09-13T10:32:18Z) |
| `GauntletFresh1160-Reviewed-Standalone` | 51.7 | git: branch 'gauntlet-test/reviewed-async-1160' @ 22ca5cf073fae5f674a384f0752966603e800a7c not confirmed merged into canonical main |
| `GauntletHardeningRecoveryAudit-20260909` | 154.8 | git: branch 'HEAD' @ 095f1347103bc86af135a81d1070b11513f87d25 not confirmed merged into canonical main |
| `GauntletIntegratedRecoveryAudit-20260909` | 154.2 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main |
| `GauntletLauncherCombinedAudit-20260909` | 153 | git: branch 'audit/astra-convergence-launcher-20260909' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main |
| `GauntletOperatorUX-20260907` | 39.6 | git: branch 'fix/gauntlet-operator-ux' @ 35e14ffb14e6eb81077ffd875c808f7772eed7e5 not confirmed merged into canonical main |
| `GauntletPipelineActivity-20260907` | 136.5 | git: branch 'gauntlet-pipeline-activity' @ 3dd52b162f5ec9dc9b876dc966e811d341e23471 not confirmed merged into canonical main |
| `GauntletPipelinePauseCandidate-20260909` | 40.4 | git: branch 'feature/gauntlet-pipeline-pause-20260909' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 8 uncommitted non-Unity-noise change(s) |
| `GauntletRecoveryAudit-20260909` | 153.3 | git: branch 'audit/cleanup-exact-20260909' @ eda47e0f4cf6fb64c91e4ed5d7ef72b81148a7ea not confirmed merged into canonical main |
| `GauntletRecoveryAuditEvidence-20260909` | 5.2 | modified within last 7 days (newest file 2026-09-16T19:00:06Z) |
| `GauntletRecoveryCombined-20260909` | 36.6 | git: branch 'audit/recovery-combined-20260909' @ 3a97e09e90c46ce130a37f22ac4a9ac175395213 not confirmed merged into canonical main |
| `GauntletReplacementTasks-20260907` | 70.4 | git: branch 'main' @ 68de75ee545c70dc887639c9ba5a932cc15e10a9 not confirmed merged into canonical main |
| `GauntletReplayWet-20260911-2` | 71.8 | git: branch 'gauntlet-replay/wet-20260911' @ b343b11b87fdd6c68c7ac299bfe2ee290d69ea92 not confirmed merged into canonical main |
| `GauntletReplayWet-20260911-3` | 49.8 | git: branch 'gauntlet-replay/wet-20260911-3' @ 91266cd2e8e59bf822f3112d70b6822c7b4c2e2d not confirmed merged into canonical main |
| `GauntletReplayWet-20260911-4` | 49.5 | git: branch 'gauntlet-replay/wet-20260911-4' @ 12652036073662dbf01a19898ff0f77342fbfd99 not confirmed merged into canonical main |
| `GauntletReplayWet-20260911-5` | 50.5 | git: branch 'gauntlet-replay/wet-20260911-5' @ 33538995391609c22cfdb880eb59742b1aada746 not confirmed merged into canonical main |
| `GauntletViewCIRegistration-20260908` | 35.4 | git: branch 'fix/gauntlet-view-ci-registration-20260908' @ 6175e3be8f1ac1fef4df3a326d6db7f2bb20e291 not confirmed merged into canonical main |
| `GauntletViewCurrentRunIntegration-20260907` | 48.2 | git: branch 'main' @ 57aa2300b6c2a01aaf5b0d432fbe57dd56174fe4 not confirmed merged into canonical main |
| `GauntletViewGitHubLinks-20260907` | 37.9 | git: branch 'fix/gauntlet-view-github-links' @ 4024531b4f9ea38a5cef6d25d3eae63a0bfa56d9 not confirmed merged into canonical main |
| `GauntletViewInheritedGateQueue-20260908` | 38.4 | git: branch 'fix/gauntlet-view-inherited-gate-queue' @ 3e7e10d821449744880b90621c93b23672332b10 not confirmed merged into canonical main |
| `GauntletViewInheritedHumanAction-20260908` | 38.4 | git: branch 'fix/gauntlet-view-inherited-human-action' @ fd463fb539c76b1c7f5ee61557df7d1cfb01414b not confirmed merged into canonical main |
| `GauntletViewIntegration-20260908` | 39.2 | git: branch 'integration/gauntlet-view-queue-causal' @ 99964d712419cfee0327574f0f52f0b9c80b0f48 not confirmed merged into canonical main |
| `GauntletViewRequestDecompositionCandidate-20260909` | 36.9 | git: branch 'feature/gauntletview-request-decomposition-20260909' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `GauntletViewScopeLayout-20260907` | 34.9 | git: branch 'fix/gauntlet-display-scope-panels' @ 2ad759aaabfd84ed3945f4fd50c7996dee9e5595 not confirmed merged into canonical main |
| `GauntletViewScopeLayout-BaseCheck` | 34.4 | git: branch 'HEAD' @ 57aa2300b6c2a01aaf5b0d432fbe57dd56174fe4 not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `GauntletViewTerminalRecovery-20260908` | 47.3 | git: branch 'fix/gauntletview-recovered-terminal-precedence' @ c987b85f831bfbf6f8368ac0ab2356793a058b3e not confirmed merged into canonical main |
| `GauntletViewTerminalTruth-20260908` | 38.4 | git: branch 'fix/gauntlet-view-terminal-truth' @ e476932718b42185b8c7b72fa8a1fd252623eac5 not confirmed merged into canonical main |
| `generated-child-scope-tests` | 0 | modified within last 7 days (folder's own last-write 2026-09-14T06:44:25Z (folder itself was created/changed recently, even if empty now)) |
| `GER-NSC044-20260914-fresh` | 0 | modified within last 7 days (newest file 2026-09-14T08:25:15Z) |
| `GER-NSC044-20260914-resume` | 0 | modified within last 7 days (newest file 2026-09-14T08:57:45Z) |
| `GitHubCommentBatch-20260908` | 38.3 | git: branch 'fix/github-comment-rest-batch' @ c37c7ca7acf519550eef1ea55eaccb38ef377f7f not confirmed merged into canonical main |
| `GraphReviewState-20260913` | 0 | modified within last 7 days (newest file 2026-09-15T23:47:39Z) |
| `HomeworkRehearsal-MainRepair-20260908` | 40.3 | git: branch 'integration/repaired-main-0ca58f0-20260908' @ fc92bbcf2304c4076af6e5c2e9cde8c72213630f not confirmed merged into canonical main |
| `ImmutableCrewManifestCandidate-20260909` | 40 | git: branch 'fix/immutable-crew-manifest-20260909' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `IndependentRevisionRaceBaseline-20260909` | 39.3 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 1 uncommitted non-Unity-noise change(s) |
| `LocalCandidateAcceptedScopeCandidate-20260909` | 39.5 | git: branch 'fix/local-candidate-accepted-scope-20260909' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `LocalCrewViewTmp` | 0 | modified within last 7 days (folder's own last-write 2026-09-17T21:03:38Z (folder itself was created/changed recently, even if empty now)) |
| `LocalIssueSnapshot-20260908` | 52.1 | git: branch 'fix/local-issue-observation-snapshot' @ 03c9ce8f6162d364183aee3acb56e091e282c952 not confirmed merged into canonical main |
| `LocalIssueSnapshot-Base-20260908` | 38.3 | git: branch 'HEAD' @ 85c1eeff02562b5797338e8396ae287d024a9488 not confirmed merged into canonical main |
| `MergeAgent-20260909` | 39.8 | git: branch 'feature/event-driven-merge-agent-20260909' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 6 uncommitted non-Unity-noise change(s) |
| `MuffcabbageCandidateGateFixture-20260908` | 35.6 | git: branch 'fix/muffcabbage-candidate-gate-fixture' @ a43100e30bb927e11749a3e3c8da58407ecd2d2a not confirmed merged into canonical main |
| `MuffcabbageDeepAcceptance` | 86.1 | git: branch 'codex/muffcabbage-deep-acceptance' @ 7e58c995c6c52a66c69ed053abe5764d2518decd not confirmed merged into canonical main |
| `NoSafeCircle-AssistantControl-SpeedIntegration` | 36.6 | git: branch 'assistant/integrate-background-plus-decomp' @ 8d8ae6cd09d581c1535fd4ff5053782b0c883321 not confirmed merged into canonical main |
| `NoSafeCircle-Cardinal-Staging` | 1348.3 | git: branch 'assistant/cardinal-staging' @ b1e70b5ec2c2e8e1d179a9eda030cee3e58d0b01 not confirmed merged into canonical main |
| `NoSafeCircle-ClaudeGuidancePort-20260914` | 48.8 | git: 4 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-D4-Grounding-Hotfix` | 1352.7 | git: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-D4-Opening-Hotfix` | 1345.3 | git: 39 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Door-UI-Sorting-Hotfix` | 1347 | git: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Enemy-Stationary-Graph` | 138 | modified within last 7 days (newest file 2026-09-13T19:09:21Z) |
| `NoSafeCircle-EnvironmentContent` | 140.2 | modified within last 7 days (newest file 2026-09-13T20:07:05Z) |
| `NoSafeCircle-FiveRoom-Wizard-Review` | 1344.9 | git: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Foreground-NSC-062-Fix` | 1345 | git: branch 'assistant/foreground-nsc-062-materialization' @ 3f99eff7d7057ddf11fe17e8fe59f9898ac21228 not confirmed merged into canonical main; also: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Foreground-NSC-066` | 1339.3 | git: branch 'assistant/foreground-nsc-066-title-screen' @ 1be73b24cd3c9f35c62a1a75ac0aa4e4e7771116 not confirmed merged into canonical main |
| `NoSafeCircle-Foreground-NSC-067` | 1352 | git: branch 'assistant/foreground-nsc-067-selection' @ edc2526bbdf16f34bcecb8221c0e17db30a881b7 not confirmed merged into canonical main; also: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-FullGraphViewer` | 140.6 | git: branch 'assistant/full-graph-viewer' @ 570c6bd1d8a4b57d6495871611018868e5b3183c not confirmed merged into canonical main |
| `NoSafeCircle-Game-Candidate` | 1345.5 | git: 1 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-GraphViewerReviewAlarm-Assistant` | 140.5 | git: branch 'assistant/graph-viewer-youtube-origin-fallback' @ 8916784de5a9080dd285e9104179108d683fae36 not confirmed merged into canonical main |
| `NoSafeCircle-MainIntegration` | 1470.7 | modified within last 7 days (newest file 2026-09-13T22:00:42Z) |
| `NoSafeCircle-NSC-004-ScopeFix` | 46.8 | git: branch 'assistant/fix-nsc-004-scope' @ de16840db76818c88996c6abe245bc517ccad294 not confirmed merged into canonical main |
| `NoSafeCircle-NSC049-RoomComposition` | 1356.1 | modified within last 7 days (newest file 2026-09-13T08:11:40Z) |
| `NoSafeCircle-NSC069-LaunchScope` | 35.2 | git: 19 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-NSC069-Review` | 1331.5 | git: branch 'HEAD' @ 3d27c447fd97d4bde20103ffd93eb7e7d27d99cd not confirmed merged into canonical main; also: 179 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-NSC070-Integration` | 36.7 | git: branch 'assistant/integrate-nsc-070' @ 16ecdb2f422759a8c783b3d66ec80e4f5375f52c not confirmed merged into canonical main |
| `NoSafeCircle-NSC073-PixelLab` | 34.7 | git: branch 'assistant/nsc-073-pixellab' @ be3ac95489e6279c967baa11497e59fb4b1e4e9b not confirmed merged into canonical main |
| `NoSafeCircle-NSC074-CardinalArt` | 1344.8 | git: branch 'assistant/nsc-074-cardinal-art' @ a0602783f2eae4736ce23d3735bb8ce3df2acdea not confirmed merged into canonical main |
| `NoSafeCircle-NSC075-BuilderPrep` | 1345.9 | modified within last 7 days (newest file 2026-09-13T09:13:07Z) |
| `NoSafeCircle-NSC075-IntegrationPrep` | 1346.2 | modified within last 7 days (newest file 2026-09-13T08:54:03Z) |
| `NoSafeCircle-NSC089-ManagedRecovery` | 50.2 | modified within last 7 days (newest file 2026-09-14T08:07:50Z) |
| `NoSafeCircle-Restored-Meta-Fix` | 38 | git: branch 'assistant/restored-meta-companion-fix' @ 807bd7b86a303a95af8ea66f5fd9a74f710d12f5 not confirmed merged into canonical main |
| `NoSafeCircle-Review-Wizard-Lobby` | 1343.2 | git: branch 'assistant/review-wizard-lobby' @ 651fd62981575d8499c51e774a26f93de5df9587 not confirmed merged into canonical main; also: 39 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Room-Composition-B` | 1345.5 | git: branch 'assistant/room-composition-b' @ 5279e1ae2f2787c505e97e95c13a0ee573dfc5d1 not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `NoSafeCircle-Room-Materialization-Fix` | 141.2 | git: branch 'assistant/room-scene-materialization' @ d201f5d90a9eec9971c66c473b054c8c82205058 not confirmed merged into canonical main |
| `NoSafeCircle-Room-NSC-044` | 1328.8 | git: branch 'assistant/room-nsc-044' @ 61514b006d6c7b1f405645a7274b737bb0752573 not confirmed merged into canonical main |
| `NoSafeCircle-Room-NSC-045` | 36.2 | git: branch 'assistant/room-nsc-045' @ 678a5148fd8626c345a3e4f28362c47aeae21b79 not confirmed merged into canonical main |
| `NoSafeCircle-Room-NSC-046` | 1337.2 | git: branch 'assistant/nsc-046-chapel' @ c6cad1cabc5b26627dc782a091f5844faf746f6c not confirmed merged into canonical main |
| `NoSafeCircle-Room-NSC-047` | 1336.8 | git: branch 'assistant/nsc-047-vault' @ 6bc4ccae344e53f906e924c68851fe4b623930a7 not confirmed merged into canonical main |
| `NoSafeCircle-Room-NSC-048` | 1344.8 | git: branch 'assistant/nsc-048-final' @ 389e4e525ca13070972388df50d5e0f576180423 not confirmed merged into canonical main |
| `NoSafeCircle-Sorting-Revalidation-Proof` | 36 | git: branch 'HEAD' @ acd664998ff091d45faa0232699ba8eefd7e69e6 not confirmed merged into canonical main |
| `NoSafeCircle-Sorting-Source` | 1447.3 | git: branch 'assistant/sorting-foundation-revalidation' @ fedac8dd6da5e587825e8c014eaacf7d1c808e24 not confirmed merged into canonical main |
| `NoSafeCircle-Wizard-Audit-Graph` | 36.8 | git: branch 'assistant/task-nsc-070-wizard-animation-audit' @ f14404e921db0ffb21e0f70ef56711450303a322 not confirmed merged into canonical main |
| `NoSafeCircle-Wizard-Runtime-Stability` | 1346.2 | git: branch 'assistant/nsc-070-runtime-stability' @ 899af1c60dfc0e4d5ad746dfb13e4d0daadf2a7e not confirmed merged into canonical main |
| `NSC-042-BuildComparison` | 1327.3 | git: branch 'HEAD' @ 1fdb2918af4daaf478232b9790b39fa8bb7989cd not confirmed merged into canonical main; also: 6 uncommitted non-Unity-noise change(s) |
| `NSC-066-Validation-Edit-v2` | 1332 | git: branch 'assistant/foreground-nsc-066-title-screen' @ d17d07aa22327a209ac9ef10dc12ecef65dc712e not confirmed merged into canonical main; also: 179 uncommitted non-Unity-noise change(s) |
| `NSC-066-Validation-Play-v2` | 1332.2 | git: branch 'assistant/foreground-nsc-066-title-screen' @ d17d07aa22327a209ac9ef10dc12ecef65dc712e not confirmed merged into canonical main; also: 179 uncommitted non-Unity-noise change(s) |
| `Nsc911DecompositionRecovery-20260905` | 41.6 | git: branch 'fix/fresh-decomposition-main-advance-recovery' @ 531a14852c2d5e6ed198e8412b7d0a7acda87a95 not confirmed merged into canonical main |
| `NSCDemoGauntlet-20260916` | 1491.5 | git: branch 'demo/gauntlet-20260916' @ 717d175c4b63d5677a3cf27fa65c7b5a57685816 not confirmed merged into canonical main |
| `OpenAIResetRecovery57594d` | 37.6 | git: branch 'review/reset-recovery-corrections' @ 70144022aaf0d9a2ca69a39516b02bc50f7a5a7d not confirmed merged into canonical main |
| `OrchestratorCrewPreflight-20260913` | 36.4 | modified within last 7 days (newest file 2026-09-14T00:26:35Z) |
| `PolicyReplayExactFix` | 37.7 | git: branch 'fix/exact-repin-replay-diff' @ 5e23243b11d4788e2de550a96582d23571e8f179 not confirmed merged into canonical main |
| `PretestAcceptedFixesCandidate-20260909` | 40.2 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 15 uncommitted non-Unity-noise change(s) |
| `PreVerificationMergeGate-20260908` | 54.1 | git: branch 'fix/pre-verification-merge-gate' @ b30b4f9e6b8a956d8b3ba0967dce5f9676cdfbc3 not confirmed merged into canonical main |
| `PristineEightNodeBenchmark-20260908` | 49.9 | git: branch 'benchmark/pristine-eight-node-infrastructure-20260908' @ fcd0226e65941b1142aa0bf4c0319bb7f5d024df not confirmed merged into canonical main |
| `PristineSeedCoreRepairs-20260908` | 40.1 | git: branch 'fix/pristine-seed-core-repairs' @ 3c3ba519c8a0b38ad758074ac27396dafc900a62 not confirmed merged into canonical main |
| `PristineSeedRedFixes-20260908` | 38.8 | git: branch 'fix/pristine-seed-red-tests' @ e0494c12382fb34a74d06fd2e4415423592fddfd not confirmed merged into canonical main |
| `PropagatePrBound-AllClaude-20260908` | 50 | git: branch 'main' @ d43f1262dab977b263bbced0248577a65b16a3dd not confirmed merged into canonical main |
| `PropagatePrBound-ClaudeBalanced-20260908` | 53.3 | git: branch 'main' @ 29a6e0fe5fffa032c0c35b40c8fee32a21647f21 not confirmed merged into canonical main |
| `PropagatePrBound-CodexBalanced-20260908` | 53.8 | git: branch 'main' @ b5436a16f38b7c8176afc1c462cca0e199766593 not confirmed merged into canonical main |
| `PropagateRetryRole-Primary-20260908` | 51.6 | git: branch 'main' @ dc94cb7ab5f41c5abb459d8e057bbe8e5e565c27 not confirmed merged into canonical main |
| `ProviderBoundaryBootstrapFollowonAuditWorktree-20260908-3fa7` | 36.4 | git: branch 'HEAD' @ 3fa7c9b825213e672b14f23bccc5c932fdc1fd8b not confirmed merged into canonical main |
| `ProviderBoundaryConflictAudit-20260905` | 27.9 | git: branch 'HEAD' @ b06194dca40227beb3a695e39b932edbe8ec4c1d not confirmed merged into canonical main |
| `ProviderBoundaryLauncherAuditWorktree-20260908-49f6` | 36.4 | git: branch 'HEAD' @ 49f6c6c73d0fee3900d158af8b9c5dba60117900 not confirmed merged into canonical main |
| `ProviderBoundaryLauncherAuditWorktree-20260908-d59b` | 36.4 | git: branch 'HEAD' @ d59babcab41d737303b45e2013beccc33bf4d217 not confirmed merged into canonical main |
| `ProviderBoundaryReview-20260905-09ae41ea` | 127.2 | git: branch 'HEAD' @ 4d62f534d79f66f53cf10ccb72b6d3bee6ab10dd not confirmed merged into canonical main |
| `ProviderCheckpointA` | 83.3 | git: branch 'codex/provider-checkpoint-a' @ 435f6866bf7f4ff5522eac52efe45e3da5b72ee4 not confirmed merged into canonical main |
| `ProviderProfilesBalancedRouting-20260907` | 90.2 | git: branch 'fix/provider-profiles-balanced-routing' @ 90b2f8dc98c099d3c73d98d0c2960e7045325b58 not confirmed merged into canonical main |
| `ProviderProfilesRoutingBaseline-20260907` | 81 | git: branch 'HEAD' @ bb560d0e56b77156b0d59cd1f60b1ac2fb02a371 not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `PublicGateAdversarialAudit-20260907T033720Z` | 41.5 | git: branch 'audit/public-gate-adversarial' @ eb3353fc76630ebcfcdaa73626ef78b7b0c8273e not confirmed merged into canonical main |
| `PublicPipelineIntegration-Astra-20260907` | 53.5 | git: branch 'integration/public-orchestration-final-20260908' @ 6273fe9a6b8286bf1fbd323b304d539b07b815e8 not confirmed merged into canonical main |
| `PublicWorkflowRecoveryFix-20260907` | 42.1 | git: branch 'fix/pending-workflow-consumers' @ 6462ffb07e2993a92317664ce8af51a7a7888813 not confirmed merged into canonical main |
| `PublicWorkflowRecoveryFix-20260907-baseline` | 41.8 | git: branch 'HEAD' @ 837eb4f0fa0ba8d619bbb78b500e73ccfd229792 not confirmed merged into canonical main |
| `QueueVisualizerIntegration-20260907` | 36.6 | git: branch 'integration/queue-visualizer-20260907' @ 4ca148850a54326ee29fd4c35fcc51d918c278ff not confirmed merged into canonical main |
| `RehearsalEvidenceBindingFix` | 80.1 | git: branch 'codex/rehearsal-evidence-read-binding' @ 7e58c995c6c52a66c69ed053abe5764d2518decd not confirmed merged into canonical main |
| `ReleaseBaseF560` | 50 | modified within last 7 days (newest file 2026-09-14T07:09:57Z) |
| `ReleasePolicyFix40a` | 48 | git: branch 'release/policy-nsc071-40a' @ 814c1f66fc8d9fb0d17cd6d9a18711188042393d not confirmed merged into canonical main |
| `ReleasePublish40a` | 50 | modified within last 7 days (newest file 2026-09-14T07:43:09Z) |
| `RetireAbandonedGateWaiter-20260907` | 138.3 | git: branch 'codex/retire-abandoned-gate-waiter' @ a40319dc2cc8e4853bbaf2ecc91ac397fff4fd6b not confirmed merged into canonical main |
| `review-91a0b0d-b6002f4b99384de08341e16d92375891` | 0 | modified within last 7 days (folder's own last-write 2026-09-12T18:10:34Z (folder itself was created/changed recently, even if empty now)) |
| `ReviewTRA-20260908` | 149.1 | git: branch 'review/taskreviewagent-adversarial-20260908' @ cb8d4e9b946b5e4db5b7fd4f08dd9d6a2973c285 not confirmed merged into canonical main |
| `RevisionRaceTmp` | 0 | modified within last 7 days (folder's own last-write 2026-09-13T21:39:28Z (folder itself was created/changed recently, even if empty now)) |
| `ScalePrereqIntegration-20260905-0e8a-wt` | 31.2 | git: branch 'codex/integrate-scale-prereqs-0e8a' @ ebaa5e5bb054b4dab85062fbe5f04ad266792d5f not confirmed merged into canonical main |
| `SchedulerFactoryExtraction` | 29.3 | git: branch 'review/extract-production-scheduler-factory' @ c552a62b758091807c633daf2a476bbfa7011744 not confirmed merged into canonical main |
| `SchedulerObservationFix-20260907` | 43.4 | git: branch 'fix/bounded-close-observation-930' @ 11dcd130665d531d556af48756d4d5291cd3991e not confirmed merged into canonical main |
| `SingleDecompViewer-20260909` | 39.1 | git: branch 'HEAD' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `SingletonMediumAdmission-20260908` | 39.4 | git: branch 'fix/singleton-medium-admission' @ 39c2ce9fd1b30c767f63a271f550e237ce8a4c21 not confirmed merged into canonical main |
| `SnapshotProductionCorrection-20260905` | 36.5 | git: branch 'codex/fix-source-snapshot-production-path' @ 37aa1497460210f371ec9e58d526a3cdc7f6e5be not confirmed merged into canonical main |
| `SolCodexArchitectEffortCandidate-20260909` | 39.9 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `SolCodexPluginPolicy-20260909` | 37.3 | git: branch 'HEAD' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main; also: 5 uncommitted non-Unity-noise change(s) |
| `SolDecompositionVisualizerTransitionCandidate-20260909` | 39.8 | git: branch 'HEAD' @ 6d62f0a85bc52c8c0014fb8d4800b7726ec0ea09 not confirmed merged into canonical main; also: 6 uncommitted non-Unity-noise change(s) |
| `SolGeneratedChildScopeCandidate-20260909` | 36.9 | git: branch 'HEAD' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `SolLocalAutoApprovalCandidate-20260909` | 37.6 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 17 uncommitted non-Unity-noise change(s) |
| `SolLocalAutoApprovalCandidate3-20260909` | 37.6 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 17 uncommitted non-Unity-noise change(s) |
| `SolLocalAutoApprovalCandidate4-20260909` | 37.1 | git: branch 'HEAD' @ 02fa080a96b302f7e40fb7b6e251165fc5b4d28d not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `SolMergeAgentUnit6Candidate-20260908` | 36.6 | git: branch 'sol/merge-agent-unit6-candidate' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main |
| `SolMergeQueueCandidate-20260909` | 38.6 | git: branch 'sol/event-driven-merge-queue' @ 4d9e523a51b4933f2247deba742ed4c25a469166 not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `SolObservePerfCandidate-20260909` | 39.2 | git: branch 'HEAD' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `SolReservationCoalesceCandidate-20260909` | 39.9 | git: branch 'HEAD' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `SolSchedulerBeforeWaitCandidate-20260909` | 50.1 | git: branch 'fix/scheduler-reconcile-before-wait' @ 6d913be0a1ef6f5ae787bbea8affc0099728afed not confirmed merged into canonical main; also: 3 uncommitted non-Unity-noise change(s) |
| `SolScopePromptCandidate-20260909` | 38.7 | git: branch 'HEAD' @ bda10773353c42e3322aa81b3d4b3be78d90a1ba not confirmed merged into canonical main; also: 2 uncommitted non-Unity-noise change(s) |
| `SourceAdmissionSnapshot-20260905-2fef` | 28.2 | git: branch 'codex/source-admission-snapshot-perf' @ 2fef3dc6832346f33ee829eea849fa4244d691fe not confirmed merged into canonical main |
| `SpaceInvaders` | 917.2 | git: branch 'main' @ f7f09483cc2ed76d31c71aa2e2690744170f36f1 not confirmed merged into canonical main; also: 1 uncommitted non-Unity-noise change(s) |
| `StrandedGateOwnerRecovery-20260908` | 49.4 | git: branch 'fix/stranded-gate-owner-recovery' @ 17e13c6d184cb095083d6b3d47d9fdf5cdbaa874 not confirmed merged into canonical main |
| `SyntheticDecompPumpFix-20260908` | 38.6 | git: branch 'fix/synthetic-decomposition-pump' @ d94c937b7293a58851a71975ce29d35620f57099 not confirmed merged into canonical main |
| `SyntheticReintegrationFix-20260905` | 40.8 | git: branch 'fix/synthetic-mainline-reintegration-authority' @ 902a24b78c007f5e9707e42f465dc536d22954ea not confirmed merged into canonical main |
| `TaskControlCIAuthority-20260907` | 138.8 | git: branch 'infra/taskcontrol-ci-authority-20260907' @ 4c06cf6e67946e9c125ccce42eb99579496ada42 not confirmed merged into canonical main |
| `TaskControlCurrentState-20260907` | 36.1 | git: branch 'taskcontrol-current-state' @ 420665fa1be2d1c5415df42daef19b1b3eefc782 not confirmed merged into canonical main |
| `TaskGraph-NSC-068-20260912` | 32.5 | git: branch 'assistant/taskgraph-nsc-068' @ c95d97af8f88c12c52de31119743912711addeae not confirmed merged into canonical main |
| `Temp` | 0.2 | modified within last 7 days (folder's own last-write 2026-09-12T08:43:23Z (folder itself was created/changed recently, even if empty now)) |
| `TenTaskEvidence-20260905` | 41.3 | git: branch 'claude/ten-task-run-evidence' @ be21a49128b7e86013bc090399ba02d7c8346423 not confirmed merged into canonical main |
| `TenTaskFinalIntegration-20260905` | 1375.4 | git: branch 'demo/run-20260916' @ 4ecf3fabef8ead749ab299eddaf036d2bfee22d2 not confirmed merged into canonical main |
| `TenTaskFinalIntegration-20260905-Review` | 1378.5 | git: branch 'main' @ b5f3e9832b778a582d139447684f05b46acd3da4 not confirmed merged into canonical main; also: 1 uncommitted non-Unity-noise change(s) |
| `TenTaskFinalIntegration-DemoCopy` | 68 | git: branch 'demo/run-20260916' @ 4ab9336f5650360c0c3423b4179c682b888cf9cb not confirmed merged into canonical main |
| `TenTaskRehearsalReseed-20260909` | 47.6 | git: branch 'rehearsal/ten-task-reseed-20260909' @ 3c3ba519c8a0b38ad758074ac27396dafc900a62 not confirmed merged into canonical main |
| `TenTaskRunnerDriftIntegration-20260906` | 89.7 | git: branch 'main' @ aac323d23a183631cf2850909b770d9db9f313fa not confirmed merged into canonical main |
| `ThirdGauntletActivityShapeFix-20260908` | 36.4 | git: branch 'fix/third-local-activity-shape-20260908' @ a98a6e3dbcec3f2fa1c561fa7597f652c7b922bc not confirmed merged into canonical main |
| `ThirdGauntletActivityTransportFix-20260908` | 36.4 | git: branch 'fix/third-local-activity-transport-20260908' @ a712383cb8ce56053af56006b0b24a3a5bc67aea not confirmed merged into canonical main |
| `ThirdGauntletBaseTest-20260908` | 151.7 | git: branch 'HEAD' @ 69348cbf2e75c77fd32bb371a600567ff391f559 not confirmed merged into canonical main |
| `ThirdGauntletBootstrapAudit-20260908` | 152 | git: branch 'fix/third-immutable-provider-bootstrap-20260908' @ 3fa7c9b825213e672b14f23bccc5c932fdc1fd8b not confirmed merged into canonical main |
| `ThirdGauntletBootstrapCrossAudit-20260908` | 48.3 | git: branch 'HEAD' @ 2394e543d80fe8dc4a512a32aed1ed7dc788c636 not confirmed merged into canonical main |
| `ThirdGauntletBootstrapCrossAudit-3fa7c9b8-20260908` | 48.3 | git: branch 'HEAD' @ 3fa7c9b825213e672b14f23bccc5c932fdc1fd8b not confirmed merged into canonical main |
| `ThirdGauntletCrossTest-20260908` | 151.7 | git: branch 'HEAD' @ 5e683853641f79d9806b6a050fd20a1ed28bb2c0 not confirmed merged into canonical main |
| `ThirdGauntletLauncherAudit-20260908` | 151.5 | git: branch 'audit/third-launcher-20260908' @ 400a23caf734486ec9866b70df48e0e50534baa3 not confirmed merged into canonical main |
| `ThirdGauntletLauncherFix-20260908` | 152 | git: branch 'audit/third-launcher-prerequisites-20260908' @ fa8d1fddf7d7d28e21799ce0c34cec16c2b7abb0 not confirmed merged into canonical main |
| `ThirdGauntletLockWait-20260908` | 151.8 | git: branch 'fix/third-local-lock-wait-20260908' @ eda5993056e4a6379a59b4c4677543b3bf1947a4 not confirmed merged into canonical main |
| `ThirdGauntletNetworkCleanup-20260908` | 36.6 | git: branch 'fix/local-run-network-shutdown-20260908' @ eda47e0f4cf6fb64c91e4ed5d7ef72b81148a7ea not confirmed merged into canonical main |
| `ThirdGauntletReferee-20260908` | 154.2 | git: branch 'audit/third-gauntlet-convergence-20260908' @ f8fd8e3a7e16f95bd05d8dc6521e35aa2d2859a9 not confirmed merged into canonical main |
| `ThirdGauntletRunDetails-20260909` | 153 | git: branch 'fix/local-viewer-run-details-20260909' @ 9ed1a4305e868d2b692ead7aaa6e6625779276e3 not confirmed merged into canonical main; also: 4 uncommitted non-Unity-noise change(s) |
| `ThousandScaleIntegration-20260905-ebaa` | 28.2 | git: branch 'codex/integrate-thousand-readiness-ebaa' @ 827cf453905e02635ad97fcb9cd8ea304d62bc65 not confirmed merged into canonical main |
| `ThousandScaleIntegration-20260905-ebaa-v2` | 28.2 | git: branch 'codex/integrate-thousand-readiness-ebaa-v2' @ 2fef3dc6832346f33ee829eea849fa4244d691fe not confirmed merged into canonical main |
| `ThousandTaskAutonomousGauntlet` | 35.7 | git: branch 'codex/thousand-task-autonomous-gauntlet' @ dda75234f27c75162e4edf2f58abbdc46b2e6edb not confirmed merged into canonical main |
| `ThousandTaskReadinessIntegration` | 84.4 | git: branch 'codex/thousand-task-readiness-integration' @ 9db133b83e2683bec7463a104383edfe6ebbd2a5 not confirmed merged into canonical main |
| `viewer-logs` | 0.4 | modified within last 7 days (newest file 2026-09-13T22:49:41Z) |
| `VincentInboxBootstrap-20260907` | 38.5 | git: branch 'fix/nsc-vincent-inbox-bootstrap' @ c1aa9b068844f9894e045f27840c2288ff2316b0 not confirmed merged into canonical main |
| `W1Audit65d` | 36.4 | git: branch 'HEAD' @ 65d6bd24ccbe9469606e555c88b9a32390534199 not confirmed merged into canonical main |
| `W1Audit981d` | 36.1 | git: branch 'HEAD' @ 981d49cebadd2ee8697e2e08ad6883df18aa5709 not confirmed merged into canonical main |
| `Wizard-073-Repair` | 1357.2 | git: branch 'master' @ 6e07737a9870404496385591642aa57bacacda57 not confirmed merged into canonical main |

## 8. `keep` directories (hard guard) - 41

| Name | Reason |
|---|---|
| `agent-state` | exact-path hard guard |
| `assistant-background-test-temp` | modified within last 7 days (newest file 2026-09-12T09:31:31Z); nested .assistant-control (1 dir(s) deeper in the tree) holds 1 NSC-*.json record(s) total - hard guard |
| `AssistantControlEvidence` | modified within last 7 days (newest file 2026-09-14T14:28:27Z); nested .assistant-control (3 dir(s) deeper in the tree) holds 3 NSC-*.json record(s) total - hard guard |
| `AssistantControlRuns` | no guard triggered: not recent, not live-record checkout, git merged+clean (or non-git); nested .assistant-control (1 dir(s) deeper in the tree) holds 1 NSC-*.json record(s) total - hard guard |
| `AssistantGauntletOne` | .assistant-control holds 1 NSC-*.json record(s) |
| `AssistantGauntletPublish` | .assistant-control holds 5 NSC-*.json record(s) |
| `AssistantGauntletPublishRetry` | .assistant-control holds 21 NSC-*.json record(s) |
| `AssistantGauntletSimple` | .assistant-control holds 5 NSC-*.json record(s) |
| `AssistantGauntletSimpleFresh` | .assistant-control holds 5 NSC-*.json record(s) |
| `Gauntlet1120Wet-20260911-2-Checkouts` | .assistant-control holds 5 NSC-*.json record(s) |
| `Gauntlet1120Wet-20260911-3-Checkouts` | .assistant-control holds 3 NSC-*.json record(s) |
| `Gauntlet1120Wet-20260911-Checkouts` | .assistant-control holds 1 NSC-*.json record(s) |
| `Gauntlet1120Wet-20260912-1-Checkouts` | .assistant-control holds 8 NSC-*.json record(s) |
| `GauntletDecompositionWet-20260911-2-Checkouts` | .assistant-control holds 6 NSC-*.json record(s) |
| `GauntletDecompositionWet-20260911-3-Checkouts` | .assistant-control holds 1 NSC-*.json record(s) |
| `GauntletFresh1130Run-20260912-1-Checkouts` | .assistant-control holds 12 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts` | .assistant-control holds 1 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts-2` | .assistant-control holds 6 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts-3` | .assistant-control holds 6 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts-4` | .assistant-control holds 15 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts-5` | .assistant-control holds 28 NSC-*.json record(s) |
| `GauntletFresh1140-20260912-1-Checkouts-6` | .assistant-control holds 40 NSC-*.json record(s) |
| `GauntletFresh1160-FixesRun-20260913-Checkouts` | .assistant-control holds 38 NSC-*.json record(s) |
| `GauntletFresh1160-Reviewed-Standalone-Checkouts` | .assistant-control holds 32 NSC-*.json record(s) |
| `GauntletReplayWet-20260911-2-Checkouts` | .assistant-control holds 7 NSC-*.json record(s) |
| `GauntletReplayWet-20260911-3-Checkouts` | .assistant-control holds 3 NSC-*.json record(s) |
| `GauntletReplayWet-20260911-4-Checkouts` | .assistant-control holds 3 NSC-*.json record(s) |
| `GauntletReplayWet-20260911-5-Checkouts` | .assistant-control holds 10 NSC-*.json record(s) |
| `NoSafeCircle-AssistantCheckouts` | exact-path hard guard |
| `NoSafeCircle-Game-Checkouts-2` | .assistant-control holds 1 NSC-*.json record(s) |
| `NoSafeCircle-Game-Checkouts-3` | .assistant-control holds 14 NSC-*.json record(s) |
| `NoSafeCircle-Multiscene-Checkouts` | .assistant-control holds 1 NSC-*.json record(s) |
| `NoSafeCircle-Sorting-Checkouts` | .assistant-control holds 1 NSC-*.json record(s) |
| `NoSafeCircle-Sorting-Checkouts-2` | .assistant-control holds 1 NSC-*.json record(s) |
| `NSC` | exact-path hard guard |
| `NSCDemoGauntlet-20260916-Checkouts` | .assistant-control holds 18 NSC-*.json record(s) |
| `SuccessfullTasks` | exact-path hard guard |
| `TenTaskFinalIntegration-20260905-AssistantCheckouts` | .assistant-control holds 4 NSC-*.json record(s) |
| `TenTaskFinalIntegration-20260905-AssistantCheckouts-Current` | .assistant-control holds 5 NSC-*.json record(s) |
| `TenTaskFinalIntegration-20260905-DemoRun` | .assistant-control holds 1 NSC-*.json record(s) |
| `TenTaskFinalIntegration-DemoCopy-Run` | .assistant-control holds 1 NSC-*.json record(s) |

## 9. Top-level files (300)

Never proposed for moving in this pass: all 89 top-level `.md`/referenced files
(80 `.md` docs + 9 non-md files whose name is cited by path in the doc set,
`agent-state`, or a `C:\nscrev` tool-folder report - listed below).

### 9.1 Referenced non-md files kept
| Name | Cited in |
|---|---|
| `public_pipeline_base_race_fixture.py` | /c/NSC/PublicIntegrationAuditReproduction-20260907.md, /c/nscrev/reports/cleanup-cited-dirs-20260918.txt |
| `public_pipeline_final_manifest.json` | /c/NSC/PublicPipelineIntegrationReport-20260907.md, /c/nscrev/reports/cleanup-cited-dirs-20260918.txt |
| `public_pipeline_reproduce_audit.py` | /c/NSC/PublicIntegrationAuditReproduction-20260907.md, /c/nscrev/reports/cleanup-cited-dirs-20260918.txt |
| `public_pipeline_source_audit.json` | /c/NSC/PublicPipelineIntegrationReport-20260907.md, /c/nscrev/reports/cleanup-cited-dirs-20260918.txt |
| `PublicPipelineSmallFollowupAssertions-20260907.json` | /c/NSC/PublicPipelineIntegrationReport-20260907.md |
| `TaskControlCurrentState-red-basis.txt` | /c/NSC/TaskControlCurrentState-report.md |
| `TaskControlCurrentState-red-scheduler.txt` | /c/NSC/TaskControlCurrentState-report.md |
| `TaskControlCurrentState-red-v2-progress.txt` | /c/NSC/TaskControlCurrentState-report.md |
| `verified-core-6e912.bundle` | /c/NSC/CLAUDE_RIGOR_PIPELINE_POLICY_REVIEW.md, /c/nscrev/reports/cleanup-cited-dirs-20260918.txt |

### 9.2 `ask` files - 73, modified in the last 7 days

Not individually listed (all share the same reason: self last-write within 7 days of 2026-09-18).
Extension breakdown:
| Extension | count |
|---|---|
| .log | 27 |
| .py | 22 |
| .xml | 7 |
| .json | 6 |
| .diff | 2 |
| .patch | 2 |
| .png | 1 |
| .txt | 1 |
| .tar | 1 |
| .bundle | 1 |
| .js | 1 |
| .stackdump | 1 |
| .ps1 | 1 |

### 9.3 `move` files - 138, not .md, not recent, no reference found

Grouped by category per the brief (not listed individually - 138 is a lot of one-off
scratch output: build/test logs, exit-code stubs, git bundles and patches from dated experiment runs,
and one-off Python/shell helper scripts that nothing in the doc set, agent-state, or the tool folders
names):

| Extension | count | total size | typical content |
|---|---|---|---|
| .py | 56 | 212 KB | one-off experiment/fixture scripts (e.g. provider-profile-*, public_pipeline_*, TaskControlCurrentState-*) |
| .txt | 29 | 201 KB | exit-code stubs and small text dumps (e.g. *.exit.txt, *-progress.txt) |
| .bundle | 22 | 157.3 MB | git bundles from dated experiment pushes/pulls |
| .json | 16 | 213 KB | scratch state/audit JSON from experiment runs |
| .sh | 5 | 3 KB | one-off shell helpers (Linux-flavoured acceptance/compat scripts) |
| .log | 5 | 40 KB | console/test logs from dated experiment runs |
| .patch | 4 | 234 KB | one-off diffs from dated experiments |
| .ps1 | 1 | 1 KB | one-off PowerShell helper, unreferenced |

One name is worth flagging on its own: a top-level file literally named
`Go to the current NoSafeCircle main branch, pick a task, and start working on it. Follow the
repository's task-selection and orchestration instructions..txt` - looks like a stray prompt string
that got written out as a filename by some tool. Not referenced anywhere searched; verdict `move`
like the rest of its category, but calling it out since the name itself is unusual.

## 10. RESTORE.ps1 compatibility

`RESTORE.ps1` in `C:\NSC-History-20260918` looks up a moved item by `-Name` in `MANIFEST.json`
and restores it to the `Source` path recorded there - it does not care whether that source was
originally under `C:\` or `C:\NSC\`, so **no change to RESTORE.ps1 is needed** for items this pass
moves. One thing worth knowing: names are not guaranteed unique across the two passes (root-level
`C:\nsc*` vs this `C:\NSC\*` pass could in principle collide on a common short name); this pass's
script keeps NSC-level items under a `from-NSC\` subfolder specifically so their destination paths
never collide with the root-level ones already sitting directly under `C:\NSC-History-20260918`,
but if `RESTORE.ps1` is ever handed a `-Name` that exists in both places it will restore whichever
`MANIFEST.json` entry it finds first for that name. Flagging this rather than editing RESTORE.ps1
silently, per the brief.

## 11. Risks and follow-ups

- **This is a big first move: ~100.34 GB across 416 directories.** All of it is retired
  gauntlet/experiment/candidate output per the brief's own framing, and every item was checked
  individually against the guards above, but Vincent may still want to sample a few of the largest
  ones (`FourProfileGauntlet-20260908` 33 GB, `Rehearsal` 31 GB,
  `FourProfileGauntletFresh-20260908-1812Z` 20 GB) before running `-Apply` on the full list.
- **The 330-item `ask` list is long on purpose.** Most of it (257) is unmerged-branch git clones;
  a follow-up patch-equivalence (`git cherry`) pass could safely convert some of those to `move`
  without loosening the guard logic itself.
- **`_worktrees` (89 nested `.assistant-control` dirs, ~58 GB per the cleanup guide) is in the
  `ask` list**, not touched by name here - it is the Game Agent's/cleanup guide's own worktree
  triage territory (section 6 of the guide), not a blind quarantine candidate.
- **`ProviderSmokeVerify-20260906` is a worktree**; moving it needs a `git worktree prune` in its
  parent repo afterward (the script prints this reminder when it happens).
- Sizes and dates reflect a scan taken 2026-09-18 late evening; if Vincent waits more than a few days
  to run the script, re-running the classification (or at minimum the recency guard) is cheap
  insurance against something having changed underneath.

## 12. Script

`C:\NSC-History-20260918\MOVE-NSC-FOLDERS.ps1`. Dry run by default; `-Apply` to act. Destination
`C:\NSC-History-20260918\from-NSC\<name>`. Uses `robocopy /MOVE /E /XJ` like the existing
`MOVE-STRAGGLERS.ps1`. Re-checks every guard (exact path, nested `.assistant-control` record
count, git ancestor-of-main + clean, 7-day recency) against the live filesystem/git state at run
time - not from this inventory - and skips with a logged reason on any mismatch. Appends to the
existing `MANIFEST.json` after each item. Refuses any path outside `C:\NSC`, any hard-guard path,
any destination that already exists, any cross-volume move.
