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
$Repo = "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle"
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

Instead, TaskGraph conformance will be taught to resolve a recorded old commit through an approved repository-history migration record and then prove:

- the translated commit exists;
- the translated commit has the exact recorded tree;
- recorded task-contract, canon, surface-blob, gate-artifact, and ancestry checks still pass against the translated commit.

If tree equivalence is not exact, the migration must fail closed and require new validation/evidence.

### 3. TaskReviewAgent GitHub Issue event history

Existing `nsc-workflow-event` comments remain append-only. Old event comments must not be edited because their event IDs hash their original contents.

A new repository-history migration event will be appended for affected managed Issues. For a completed Issue this is a `complete -> complete` identity migration, not a reopening of gameplay work. The live Issue dashboard/state may then point at translated commit identities while the original historical events remain intact.

Issue migration is allowed only after the repository migration record proves the relevant old/new tree identities.

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

## Force-push boundary

Do not force-update GitHub until all of these are available and reviewed:

- a fresh dry-run report from exact current `origin/main`;
- the complete old/new SHA/ref map;
- deterministic TaskGraph migration compatibility tests;
- deterministic completed-Issue migration tests;
- GitHub Issue/PR reference audit;
- an explicit list of refs that will be force-updated or closed/superseded;
- a rollback ref or immutable backup of the pre-migration heads.

The destructive step is deliberately separate from the tooling added by this document.
