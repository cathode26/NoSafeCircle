# OPERATOR FILE-HANDOFF AND DOWNLOADS PREFERENCE

This is durable operating guidance for every AI context and developer working in this repository. It was derived from the locality-audit/postmortem after repeated failures caused by manually transferring prompts, paths, patches, logs, JSON, and branch state between ChatGPT, PowerShell, Docker, Git, Unity, and parallel agent windows.

Read this file before producing operational commands or human-facing handoff artifacts.

## Canonical user preferences

Vincent prefers durable file handoffs over large inline prompts, patches, JSON, or terminal transcripts.

When an assistant gives a command that creates an ad hoc file for the human to keep, inspect, upload, reuse, or pass to another agent/context, save that file directly in the Windows Downloads folder by default:

```text
C:\Users\VincentLiguori\Downloads
```

Use the portable PowerShell form:

```powershell
$Downloads = Join-Path $env:USERPROFILE "Downloads"
```

Human-facing external files should normally be built from `$Downloads`:

```powershell
$PromptPath = Join-Path $Downloads "NSC-039-ExecutionCrew-Prompt.txt"
$FeedbackPath = Join-Path $Downloads "NSC-039-review-feedback.txt"
$PatchPath = Join-Path $Downloads "NSC-039-review.patch"
$TranscriptPath = Join-Path $Downloads "NSC-039-execution-output.txt"
$ReviewPath = Join-Path $Downloads "NSC-039-delivery-review-001.json"
$DeliverySpecPath = Join-Path $Downloads "NSC-039-delivery-spec-001.json"
```

Do not default these files to the repository root, an arbitrary current directory, `$env:TEMP` when an explicit external output path is supported, a container-only path, the Documents folder, or an unspecified location that forces Vincent to find or move the file later.

The final user preference is authoritative: use **Downloads** as the default external handoff folder.

## Critical task-start rule: setup and provider execution are separate phases

A normal gameplay-task start should use **two separate copy/paste blocks**:

```text
PHASE 1 — deterministic task setup
    update main
    create standalone clone
    create branch
    validate TaskGraph
    inspect dependency/task state
    inspect task contract
    verify exact writer paths
    verify clean tree
    print READY

HUMAN SEES READY

PHASE 2 — provider-backed ExecutionCrew run
    recheck checkout/branch/clean state
    select provider
    run ExecutionCrew
    show live output on screen
    save the same output to Downloads
    print exact next handoff
```

**Do not put Claude, Codex, or any other provider invocation inside the task-setup block.**

This separation is intentional:

- deterministic setup can fail without spending a provider call;
- the human can inspect the prepared task checkout before execution starts;
- provider execution cannot accidentally run merely because clone/setup commands succeeded;
- a later provider retry does not require recreating the checkout;
- execution output and provider failures are easier to diagnose independently from setup failures;
- the setup phase has one clear success condition: `READY`.

## What should normally be written directly to Downloads

The Downloads default applies to human-facing, external, reusable handoff files, including:

- long implementation/review prompts;
- human-review feedback text;
- exported Git patches or diffs;
- zipped review bundles;
- copied terminal transcripts or command logs;
- delivery-review JSON;
- delivery-spec JSON;
- human-validation notes created outside the repository;
- generated summaries intended for another ChatGPT/Claude/Codex context;
- temporary helper files the human must later upload, inspect, or reuse.

When ChatGPT itself generates one of these files, provide it as a downloadable artifact with a descriptive filename. Subsequent PowerShell commands should target the exact Downloads path rather than asking Vincent to save or move it manually.

## Important exceptions — do not move authoritative or tool-owned files

The Downloads preference does not mean every pipeline artifact should be relocated.

1. **Repository source, tests, contracts, documentation, and committed evidence** stay at their exact repository paths.
2. **ExecutionCrew run artifacts** remain in the configured ExecutionCrew output root. Use the exact full Windows host path printed by the pipeline.
3. **Unity clean-validation artifacts** (`validation-manifest.json`, `test-results.xml`, and `unity.log`) are hash-bound to one another. Leave them where the runner created them until TaskDelivery finalization and `record_delivery.py` finish.
4. **TaskGraph evidence produced by `record_delivery.py`** belongs under `Pipeline/TaskGraph/evidence/...`.
5. If a tool requires a specific output location for correctness, keep the authoritative file there. When a separate human handoff copy is safe and useful, create an explicitly labelled copy in Downloads without altering the authoritative original.

The practical rule is:

```text
human-authored or human-transferred external file -> Downloads
pipeline-owned/hash-bound/repository-authoritative file -> required authoritative location
```

## Transfer problems observed in the locality-audit history

A fresh agent should actively prevent these recurring failure modes.

### 1. Large inline prompts exceeded or destabilized the chat UI

Long prompts were repeatedly moved through chat and PowerShell, and one context hit the UI text limit.

**Rule:** create long prompts as UTF-8 files in Downloads and load them with:

```powershell
$Prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath $PromptPath
```

### 2. PowerShell here-string and quote errors corrupted prompts

The history records the conclusion: “The prompt quotes is wrong. this has happened before so maybe we are better off using a file.”

**Rule:** use a downloaded prompt file for long or quote-heavy content. Avoid giant `@' ... '@` blocks when a file handoff is possible.

### 3. Commands were accidentally concatenated

Observed failures included forms such as:

```text
git diff --cached --statgit commit ...
git rev-parse HEADgit commit ...
git commit ...git commit ...
```

**Rule:** provide one complete guarded PowerShell block per phase, or clearly separated commands. Never place executable commands adjacent without a newline or explicit separator. Stop after a failed precondition.

### 4. Host and container paths were confused

Container paths such as `/execution-output/...` were useful inside Docker but poor human handoff paths on Windows.

**Rule:** whenever the human must open or upload a file, prefer the exact Windows host path. Use `--host-output-root` where supported and never invent a Windows path from a container path.

### 5. Files landed in unexpected locations and then had to be moved

**Rule:** choose the final Downloads filename first. Commands should write directly there and verify it before use:

```powershell
if (-not (Test-Path -LiteralPath $PromptPath -PathType Leaf)) {
    throw "Required file does not exist: $PromptPath"
}
```

### 6. Literal placeholders were copied into real commands

A placeholder such as:

```text
<paste the newly printed validation-manifest.json path>
```

was executed as though it were a real path.

**Rule:** runnable command blocks must contain real values or derive values programmatically. Do not put `<PLACEHOLDER>` text in a block Vincent is expected to paste.

### 7. State was manually carried across agents, windows, commands, and branches

Manual transfer included task IDs, branch names, checkout paths, run IDs, candidate paths, feedback paths, commit SHAs, manifest paths, and evidence paths.

**Rule:** every substantial block should establish and verify its own critical state rather than relying on conversation memory.

### 8. Wrong checkout or stale context made otherwise valid commands unsafe

Several parallel clones and branches can exist at once.

**Rule:** every substantial block should begin with an explicit checkout path, branch check, HEAD/base check when relevant, and clean-tree check.

### 9. Ordinary `git diff` omitted untracked files

Brand-new files can be missing from a normal unstaged diff.

**Rule:** inspect:

```powershell
git status --short --untracked-files=all
```

When a complete staged review patch is appropriate, stage only the exact approved files and export directly to Downloads:

```powershell
$PatchPath = Join-Path $Downloads "descriptive-complete-review.patch"
git diff --cached --binary --output=$PatchPath
```

Never use `git add .` or `git add -A` merely to make a patch complete.

### 10. Windows/Linux line endings and Git stat markers looked like content changes

**Rule:** preserve the established Git compatibility settings for Windows bind mounts. For suspected stat-only Unity markers, prove normalized equality before restoring the exact file:

```powershell
git diff --quiet -- $ExactPath
if ($LASTEXITCODE -eq 0) {
    git restore -- $ExactPath
} else {
    throw "Real normalized content change exists: $ExactPath"
}
```

Never blanket-restore unrelated files.

### 11. Hash-bound evidence could be invalidated by editing or relocating it

**Rule:** do not edit raw evidence for style. Do not move manifest-bound XML/log files before closeout. Treat exact artifact bytes and paths as authority-bearing data.

### 12. Long output was difficult to transfer through chat

Save verbose output to Downloads while displaying it:

```powershell
$TranscriptPath = Join-Path $Downloads "NSC-039-execution-output.txt"
& <command> 2>&1 | Tee-Object -LiteralPath $TranscriptPath
```

Then upload the saved file instead of pasting thousands of lines into chat.

**Important:** `Tee-Object` can only display output after the upstream process flushes it. For Python-driven provider execution under Docker without a TTY, force unbuffered output with both:

```text
-e PYTHONUNBUFFERED=1
python3 -u
```

Without unbuffered Python, a command may be actively running while the screen appears silent for a long time.

### 13. External output inside the repository broke clean-tree preconditions

**Rule:** use Downloads for external prompt/review/spec/transcript files. Only source-controlled project files and authoritative evidence belong in the repository.

### 14. No-overwrite tools failed when old external filenames were reused

TaskDelivery intentionally refuses to overwrite review/spec outputs.

**Rule:** use descriptive, unique Downloads filenames, usually including task ID plus sequence or timestamp:

```powershell
$ReviewPath = Join-Path $Downloads "NSC-039-delivery-review-001.json"
$DeliverySpecPath = Join-Path $Downloads "NSC-039-delivery-spec-001.json"
```

On a redo, increment the suffix instead of expecting overwrite.

# Canonical successful task-start pattern

The following NSC-039 workflow is the reference-quality task-start handoff. A fresh context should reproduce this **two-phase shape** for later tasks after deriving and verifying task-specific values from current repository reality.

Do not cargo-cult NSC-039-specific IDs, paths, dependencies, branch names, or provider choice into another task.

If a selected write path is intentionally absent, use the approved exact-new ExecutionCrew flags and their corresponding preflight rules instead of scaffolding the file.

## Phase 1 — deterministic task setup only

This block prepares the task and **does not invoke any provider**.

```powershell
$ErrorActionPreference = "Stop"

$Root = "C:\UnityProjects\NoSafeCircleAgentCrew"
$MainDir = Join-Path $Root "NoSafeCircle"
$TaskDir = Join-Path $Root "NoSafeCircle-NSC039"
$Branch = "nsc-039-world-sprite-prefab-sorting"
$Downloads = Join-Path $env:USERPROFILE "Downloads"

$ImplementationPath = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
$TestPath = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "STOP: Root directory does not exist: $Root"
}

if (-not (Test-Path -LiteralPath $MainDir -PathType Container)) {
    throw "STOP: Main repository does not exist: $MainDir"
}

if (-not (Test-Path -LiteralPath $Downloads -PathType Container)) {
    throw "STOP: Downloads directory does not exist: $Downloads"
}

if (Test-Path -LiteralPath $TaskDir) {
    throw "STOP: Task directory already exists: $TaskDir`nDo not delete it. Show me this message and we will inspect it."
}

Write-Host ""
Write-Host "=== UPDATE PRIMARY MAIN ==="
Write-Host ""

$MainDirty = git -C $MainDir status --porcelain
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not inspect the primary repository."
}

if ($MainDirty) {
    $MainDirty
    throw "STOP: Primary NoSafeCircle checkout has uncommitted changes."
}

git -C $MainDir switch main
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not switch primary checkout to main."
}

git -C $MainDir pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not fast-forward main from GitHub."
}

$MainHead = (git -C $MainDir rev-parse HEAD).Trim()
Write-Host "Current main HEAD: $MainHead"
git -C $MainDir log -1 --oneline

Write-Host ""
Write-Host "=== CREATE STANDALONE NSC-039 CLONE ==="
Write-Host ""

Set-Location $Root

git clone https://github.com/cathode26/NoSafeCircle.git $TaskDir
if ($LASTEXITCODE -ne 0) {
    throw "STOP: GitHub clone failed."
}

Set-Location $TaskDir

$CloneHead = (git rev-parse HEAD).Trim()
$OriginMain = (git rev-parse origin/main).Trim()

if ($CloneHead -ne $OriginMain) {
    throw "STOP: Fresh clone HEAD does not match origin/main."
}

git switch -c $Branch
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not create feature branch $Branch."
}

$ActualBranch = (git branch --show-current).Trim()
if ($ActualBranch -ne $Branch) {
    throw "STOP: Wrong branch. Expected '$Branch', got '$ActualBranch'."
}

$TaskDirty = git status --porcelain
if ($TaskDirty) {
    $TaskDirty
    throw "STOP: Fresh NSC-039 checkout is unexpectedly dirty."
}

Write-Host ""
Write-Host "=== VERIFY TASKGRAPH ==="
Write-Host ""

python Pipeline/TaskGraph/taskcontrol.py validate
if ($LASTEXITCODE -ne 0) {
    throw "STOP: TaskGraph validation failed."
}

Write-Host ""
Write-Host "=== NSC-038 DEPENDENCY STATE ==="
python Pipeline/TaskGraph/taskcontrol.py state NSC-038 --json
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not inspect NSC-038."
}

Write-Host ""
Write-Host "=== NSC-039 CURRENT STATE ==="
python Pipeline/TaskGraph/taskcontrol.py state NSC-039 --json
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not inspect NSC-039."
}

Write-Host ""
Write-Host "=== NSC-039 CONTRACT ==="
python Pipeline/TaskGraph/taskcontrol.py show NSC-039
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Could not inspect NSC-039 contract."
}

Write-Host ""
Write-Host "=== VERIFY EXECUTIONCREW WRITE PATHS ==="
Write-Host ""

if (-not (Test-Path -LiteralPath $ImplementationPath -PathType Leaf)) {
    throw "STOP: Implementation path is missing: $ImplementationPath"
}

if (-not (Test-Path -LiteralPath $TestPath -PathType Leaf)) {
    throw "STOP: Test path is missing: $TestPath"
}

git ls-files --error-unmatch $ImplementationPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Implementation path is not tracked: $ImplementationPath"
}

git ls-files --error-unmatch $TestPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Test path is not tracked: $TestPath"
}

$TaskDirty = git status --porcelain
if ($TaskDirty) {
    $TaskDirty
    throw "STOP: Repository became dirty during preflight."
}

Write-Host ""
Write-Host "==============================================="
Write-Host "NSC-039 SETUP COMPLETE"
Write-Host "==============================================="
Write-Host "Checkout:       $TaskDir"
Write-Host "Branch:         $Branch"
Write-Host "HEAD:           $CloneHead"
Write-Host "Implementation: $ImplementationPath"
Write-Host "Test:           $TestPath"
Write-Host ""
Write-Host "READY: Review this setup output, then run ExecutionCrew separately."
```

A successful setup block stops there. It must not silently continue into Claude, Codex, or another provider.

## Phase 2 — provider-backed ExecutionCrew run

After Phase 1 reports `READY` and the human wants to proceed, use a separate execution block. This block re-establishes critical state instead of assuming Phase 1 variables still exist.

For the NSC-039 reference run, Claude is the selected provider:

```powershell
$ErrorActionPreference = "Stop"

$TaskDir = "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle-NSC039"
$Branch = "nsc-039-world-sprite-prefab-sorting"
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$ExecutionOutputRoot = Join-Path $TaskDir "Pipeline\ExecutionCrew\outputs"
$ImplementationPath = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
$TestPath = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TranscriptPath = Join-Path $Downloads "NSC-039-execution-$Stamp.txt"

if (-not (Test-Path -LiteralPath $TaskDir -PathType Container)) {
    throw "STOP: Task checkout does not exist: $TaskDir"
}

if (-not (Test-Path -LiteralPath $Downloads -PathType Container)) {
    throw "STOP: Downloads directory does not exist: $Downloads"
}

Set-Location $TaskDir

$ActualBranch = (git branch --show-current).Trim()
if ($ActualBranch -ne $Branch) {
    throw "STOP: Wrong branch. Expected '$Branch', got '$ActualBranch'."
}

$Head = (git rev-parse HEAD).Trim()
$Dirty = git status --porcelain
if ($Dirty) {
    $Dirty
    throw "STOP: Task checkout is not clean."
}

if (-not (Test-Path -LiteralPath $ImplementationPath -PathType Leaf)) {
    throw "STOP: Implementation path is missing: $ImplementationPath"
}

if (-not (Test-Path -LiteralPath $TestPath -PathType Leaf)) {
    throw "STOP: Test path is missing: $TestPath"
}

git ls-files --error-unmatch $ImplementationPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Implementation path is not tracked: $ImplementationPath"
}

git ls-files --error-unmatch $TestPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "STOP: Test path is not tracked: $TestPath"
}

Write-Host ""
Write-Host "=== START EXECUTIONCREW FOR NSC-039 ==="
Write-Host "Branch:      $Branch"
Write-Host "HEAD:        $Head"
Write-Host "Transcript:  $TranscriptPath"
Write-Host "Output root: $ExecutionOutputRoot"
Write-Host ""

docker compose -p nosafecircle run --rm -T `
    -e PYTHONUNBUFFERED=1 `
    claude-exec python3 -u Pipeline/ExecutionCrew/run_crew.py `
    --task-id NSC-039 `
    --provider claude `
    --implementation-path $ImplementationPath `
    --test-path $TestPath `
    --host-output-root $ExecutionOutputRoot `
    2>&1 | Tee-Object -LiteralPath $TranscriptPath

$CrewExit = $LASTEXITCODE

Write-Host ""
Write-Host "=== EXECUTIONCREW FINISHED ==="
Write-Host "Exit code:  $CrewExit"
Write-Host "Transcript: $TranscriptPath"
Write-Host "Authoritative ExecutionCrew output root: $ExecutionOutputRoot"
Write-Host ""

if (-not (Test-Path -LiteralPath $TranscriptPath -PathType Leaf)) {
    throw "STOP: Expected transcript was not created."
}

if ((Get-Item -LiteralPath $TranscriptPath).Length -eq 0) {
    throw "STOP: Transcript was created but is empty."
}

if ($CrewExit -ne 0) {
    throw "ExecutionCrew returned a non-zero exit code. Upload the transcript from Downloads and we will diagnose it."
}

Write-Host "DONE: Upload the NSC-039 execution transcript from Downloads to ChatGPT."
```

The two unbuffering controls are deliberate:

```text
-e PYTHONUNBUFFERED=1
python3 -u
```

They make provider/pipeline progress visible as it happens while `Tee-Object` writes the same stream to the Downloads transcript. A future agent should preserve this behavior unless the execution path is changed to another mechanism that is independently proven to flush live output.

## Why this two-phase pattern is the preferred task-start experience

The desired operator experience is:

```text
paste setup block
    -> either STOP with an exact reason
    -> or READY with verified task state

human chooses to proceed

paste execution block
    -> watch Contract Locality Auditor / Implementer / Test Author / Validator progress live
    -> same output is saved to Downloads
    -> receive one exact next handoff
```

This is preferable to a monolithic block that immediately launches a provider after setup and preferable to many small commands that force Vincent to shuttle state manually between turns.

# Required command style for future agents

When giving Vincent commands that create or consume handoff files:

1. Define `$Downloads` once per block.
2. Define every file path with `Join-Path` and a descriptive filename.
3. Write directly to the final path.
4. Use `-LiteralPath` for PowerShell file operations.
5. Use UTF-8 explicitly for text.
6. Verify human-handoff files exist and are nonempty before consuming them.
7. Print the final full path.
8. Avoid runnable placeholders.
9. Guard checkout, branch, HEAD, and clean-tree state before destructive or authority-changing steps.
10. Stop immediately after a failed precondition.
11. Preserve tool-owned/hash-bound files in their authoritative location.
12. Save large output to Downloads and ask Vincent to upload the file instead of pasting the output.
13. For a normal task start, use the two-phase canonical pattern above: deterministic setup first, provider execution second.
14. Never embed a provider invocation in the canonical setup block.
15. Provider execution must recheck its critical state instead of relying on variables or assumptions from the setup shell.
16. For Python-driven provider runs under Docker `-T`, use unbuffered output so progress remains visible while being teed to the transcript.

Preferred reusable PowerShell preamble:

```powershell
$Downloads = Join-Path $env:USERPROFILE "Downloads"
if (-not (Test-Path -LiteralPath $Downloads -PathType Container)) {
    throw "Downloads directory does not exist: $Downloads"
}
```

Preferred prompt-file pattern:

```powershell
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$PromptPath = Join-Path $Downloads "Descriptive-Prompt.txt"

if (-not (Test-Path -LiteralPath $PromptPath -PathType Leaf)) {
    throw "Prompt file does not exist: $PromptPath"
}

$Prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath $PromptPath
if ([string]::IsNullOrWhiteSpace($Prompt)) {
    throw "Prompt file is empty: $PromptPath"
}

Write-Host "Prompt file: $PromptPath"
Write-Host "Prompt characters: $($Prompt.Length)"
```

Preferred external JSON output pattern:

```powershell
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$ReviewPath = Join-Path $Downloads "NSC-039-delivery-review-001.json"
$DeliverySpecPath = Join-Path $Downloads "NSC-039-delivery-spec-001.json"
```

Preferred patch-export pattern:

```powershell
$Downloads = Join-Path $env:USERPROFILE "Downloads"
$PatchPath = Join-Path $Downloads "NSC-039-complete-review.patch"
git diff --cached --binary --output=$PatchPath
if (-not (Test-Path -LiteralPath $PatchPath -PathType Leaf)) {
    throw "Patch was not created: $PatchPath"
}
Write-Host "Patch: $PatchPath"
```

# Fresh-context instruction

A fresh AI context should not ask Vincent to reconstruct old file paths or manually transfer large text when the repository, project files, or this document can supply the state.

Before producing operational commands, the fresh context should:

- inspect current Git/repository/TaskGraph state;
- read current repository onboarding and runbook files;
- treat the Downloads preference as durable;
- use the canonical **two-phase** task-start pattern for a normal selected gameplay task;
- stop Phase 1 at `READY` and wait for the human before invoking a provider;
- create downloadable prompt/support files when content is long;
- use exact Windows host paths for human-facing files;
- show execution progress live while also saving verbose execution output to Downloads;
- distinguish external handoff files from authoritative tool-owned artifacts;
- minimize the number of times Vincent has to copy, rename, move, retype, or translate data between systems.

The goal is not merely correct commands. The goal is a reliable handoff with as little human data shuttling as possible.

---

## Source note

The original long-form locality-audit transcript is historical analysis, not current repository authority. Current task, pipeline, and workflow state must be read from `Docs/AI-Pipeline/START_HERE.md`, `Docs/AI-Pipeline/CURRENT_STATE.md`, the real-task runbook, current task contracts, committed evidence, and the actual Git tree. This document preserves the durable operator-preference and transfer-safety conclusions extracted from that audit.
