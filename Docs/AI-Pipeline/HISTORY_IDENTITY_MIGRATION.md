# Git History Identity Sanitization Migration

## Purpose

This migration removes accidentally account-attributable automation commit emails from canonical Git history without changing any committed file tree.

Known unsafe automation identities currently targeted are:

- `resilience@users.noreply.github.com` -> `resilience-fix@nosafecircle.invalid`
- `reintegration-bridge@users.noreply.github.com` -> `reintegration-bridge@nosafecircle.invalid`
- `pipeline@users.noreply.github.com` -> `pipeline@nosafecircle.invalid`

The first identity is currently associated by GitHub with the real `resilience` account. The third is currently associated with the real `pipeline` account. The migration therefore treats this as repository-identity correction, not a cosmetic author-name change.

## Safety boundary

The migration is intentionally split into phases.

The current `Pipeline/HistoryMigration/history_identity.py dry-run` command:

- requires a completely clean source worktree;
- creates a new no-overwrite disposable mirror outside the repository;
- rewrites commit objects only inside that mirror;
- preserves each rewritten commit's exact tree;
- rewrites descendants only because their parent identity changed;
- removes invalidated `gpgsig` headers from rewritten commits rather than preserving a false signature;
- records every old/new commit identity and every branch/tag ref translation;
- proves the original and rewritten `main` commits have the same tree;
- never pushes and never updates the source repository.

A dry-run report does **not** authorize a force-push.

## Canonical first dry run

Use the normal external handoff hierarchy. The output directory must not already exist.

```powershell
$ErrorActionPreference = "Stop"
$Repo = "C:\NSC\NSC\NoSafeCircle"
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$WorkId = "History-Identity-Migration"
$RunId = Get-Date -Format "yyyyMMdd-HHmmss"
$RunDir = Join-Path $Downloads (Join-Path "NoSafeCircleOutput" (Join-Path $WorkId $RunId))

Set-Location -LiteralPath $Repo

git fetch origin --prune
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

$Branch = (git branch --show-current).Trim()
if ($Branch -ne "main") { throw "Expected main, found $Branch" }

$Head = (git rev-parse HEAD).Trim()
$OriginMain = (git rev-parse origin/main).Trim()
if ($Head -ne $OriginMain) { throw "Local main is not exact origin/main" }

$Dirty = @(git status --porcelain --untracked-files=all)
if ($Dirty.Count -ne 0) { throw "Repository is not clean" }

python Pipeline/HistoryMigration/history_identity.py dry-run --source . --output $RunDir
if ($LASTEXITCODE -ne 0) { throw "History identity dry run failed" }

Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $RunDir "history-identity-dry-run.json")
```

The authoritative dry-run outputs for human review are:

```text
<RunDir>\history-identity-dry-run.json
<RunDir>\mirror.git\
```

The mirror is disposable proof material. It is not a replacement working checkout and must not be pushed merely because the rewrite completed.

## What the report must prove before any destructive step

The report must establish all of the following:

1. `trees_preserved` is `true`.
2. `source_main_tree` equals `target_main_tree`.
3. Every targeted unsafe identity has a `.invalid` replacement.
4. Every descendant rewritten solely because its parent changed retains the exact old tree.
5. All branch/tag ref movements are explicitly listed.
6. Every rewritten signed commit is listed through `signature_removed=true`; rewritten commits cannot retain a signature over their old payload.
7. No unexpected GitHub user-noreply identity is silently rewritten.

## Required migration layers after the dry run

The final repository migration must cover four separate authorities.

### 1. Git commit and ref identities

The approved old/new SHA map becomes the only allowed translation. `main` and every live branch/ref selected for migration must be updated together. Stale branches must be explicitly classified as migrated, closed/superseded, or intentionally retained before the force-update.

### 2. TaskGraph evidence

Committed delivery evidence is immutable historical evidence. It must not be edited just to replace old SHA strings.

Instead, TaskGraph conformance resolves a recorded old commit through an approved `repository-history-identity-*.json` migration manifest and then proves:

- the translated commit exists;
- the translated commit has the exact recorded tree;
- the translated commit belongs to rewritten canonical history;
- recorded task-contract, canon, surface-blob, gate-artifact, and ancestry checks still pass against the translated commit.

`Pipeline/TaskGraph/history_identity_migrations.py` owns the strict manifest contract. `Pipeline/TaskGraph/history_aware_repository.py` applies that authority to exact historical Git-object reads. The current conformance evaluator uses this repository layer while leaving evidence bytes unchanged.

If tree equivalence is not exact, the migration fails closed and requires new validation/evidence.

### 3. TaskReviewAgent GitHub Issue event history

Existing `nsc-workflow-event` comments remain append-only. Old event comments must not be edited because their event IDs hash their original contents.

`repository_history_migrated` is the dedicated maintenance event for this case. It is allowed only as:

```text
complete / merge_closeout
        -> repository_history_migrated (human)
complete / merge_closeout
```

The event records the committed migration ID/path, rewrite-report SHA-256, old/new live workflow commit, preserved tree, and old/new human-handoff commit. The task-contract hash, PASS/FAIL result, branch, and completed state are preserved.

`Pipeline/HistoryMigration/issue_migration.py` requires the committed TaskGraph migration resolver before it can append the event. It then updates only the live Issue dashboard/state block and proves all older Issue comments remain byte-for-byte unchanged.

### 4. GitHub PR/Issue metadata

The dry-run SHA map must be searched across GitHub Issues, Issue comments, pull requests, review comments, and live branch refs.

Historical merged PR records cannot be rewritten into different GitHub merge events. They should receive an explicit migration note when necessary. Obsolete open PRs based on abandoned affected history should be closed as superseded rather than merged.

## NSC-020 requirement

NSC-020 is already merged and complete. Its committed delivery record and Issue #64 contain exact historical commit identities. The final migration must preserve that evidence rather than fabricating a second human PASS.

The acceptance boundary is:

- the rewritten repository contains the same delivered NSC-020 files;
- the approved old/new commit translation proves exact tree equality;
- TaskGraph still derives NSC-020 as `conformant` on the rewritten repository;
- Issue #64's existing event chain still validates unchanged;
- a new repository-history migration event updates only the live identity view;
- the completed Issue remains `complete`.

## Current verified dry-run snapshot

This snapshot is informational evidence from exact `origin/main` at `03ec56e13398f158dfe04d10e232f24dbd9e8c7a`. If `main` changes, regenerate the reports before using any value in this section for execution.

The dedicated migration CI proved:

- source `main`: `03ec56e13398f158dfe04d10e232f24dbd9e8c7a`;
- hypothetical rewritten `main`: `8754f82cb15eda4b45c8c800c70bb5310cce7b88`;
- preserved source/target tree: `289e9f6d6124f95e43d308fa7dde32c1dfa3c599`;
- rewrite-report SHA-256: `240437b6d7a508451bf0733053a88e99f491125abea25dd8c7f2eed5b63d7959`;
- all four known unsafe commits are covered by the configured replacements;
- the full remote-branch audit currently finds nineteen affected refs, including `main`, the NSC-020 branch, recovery branches, merged fix branches, and migration-development branches;
- only four tracked files on current `main` contain translated commit identities, all under `Pipeline/TaskGraph/evidence/NSC-020/`;
- the accidental `0bd52993...` / `2ebcc99a...` empty-file create/remove pair is a contiguous net tree-neutral range and is only a candidate for omission, not silently removed by the current identity rewriter.

Important NSC-020 translations in this snapshot are:

```text
df1abc741c8cda5ce4a79f7dacf312c9311bb008 -> 1eceab1dc2b330d433ec5de7f08169a400eac8a8
5827effabf6093d88310792b97dc1880fb7ba738 -> 10bfb8c9ea02b2277ded8f0cf550b02459cddb08
3453167774fd6d428896d52bf69f91565e12da91 -> 627af4a900279b370f3c07cbeee8d0f68ecb2196
```

The original human-tested commit `5bf787a7f74aafd282ac770e4d736f4e7ea9e408` is not rewritten.

The disposable rewritten-history proof committed a synthetic migration manifest on top of rewritten `main` and then ran the real migration-aware TaskGraph evaluator. Without editing any NSC-020 evidence file, it selected `DEL-NSC-020-5827effabf60` and derived `conformant`.

## Current GitHub metadata classification

The external GitHub audit currently classifies the relevant NSC-020 objects as follows:

- **Issue #64** — canonical closed `complete` workflow. Its live head is `df1abc...` and will be translated to `1eceab1...` under the current map. Its human-tested commit `5bf787...` remains unchanged. The current 37 historical workflow events stay untouched; the migration appends event 38 and updates only the live state.
- **Issue #83** — already closed as `duplicate`. It was created by the completed-Issue discovery defect fixed by PR #84. Its historical comments may contain old commit IDs, but it is not workflow authority and receives no complete-state migration event.
- **PR #77** — merged NSC-020 delivery PR. GitHub's historical merge record remains historical; after canonical history changes it receives a migration note identifying the translated canonical commit IDs.
- **PR #73** — still open, stale, non-mergeable, and based on obsolete affected history. It is classified for close-as-superseded before the destructive phase.

Historical PRs/issues/comments may continue to contain truthful old SHA text. The migration does not edit those records merely to make every old SHA disappear; instead it distinguishes historical GitHub records from the new canonical repository history.

## Force-push boundary

Do not force-update GitHub until all of these are available and reviewed:

- a fresh dry-run report from exact current `origin/main`;
- the complete old/new SHA/ref map;
- deterministic TaskGraph migration compatibility tests;
- deterministic completed-Issue migration tests;
- GitHub Issue/PR reference audit;
- an explicit list of refs that will be force-updated or closed/superseded;
- a rollback mirror of the pre-migration heads outside the remote repository.

The destructive step is deliberately separate from the tooling added by this document.
