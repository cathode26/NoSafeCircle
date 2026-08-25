# OPERATOR FILE-HANDOFF AND DOWNLOADS PREFERENCE

This is a durable operating instruction for every AI context and developer working in this repository. It was derived from the locality-audit/postmortem transcript after repeated failures caused by manually transferring prompts, paths, patches, logs, JSON, and branch state between ChatGPT, PowerShell, Docker, Git, Unity, and parallel agent windows.

Read this file before producing operational commands or human-facing handoff artifacts.

## Canonical user preference

Vincent prefers durable file handoffs over large inline prompts, patches, JSON, or terminal transcripts.

When an assistant gives a command that creates an ad hoc file for the human to keep, inspect, upload, reuse, or pass to another agent/context, the command must save that file directly in the Windows Downloads folder by default:

```text
C:\Users\VincentLiguori\Downloads
```

Use the portable PowerShell form in commands:

```powershell
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
```

Then build every human-facing file path from `$Downloads`:

```powershell
$PromptPath = Join-Path $Downloads 'NSC-039-ExecutionCrew-Prompt.txt'
$FeedbackPath = Join-Path $Downloads 'NSC-039-review-feedback.txt'
$PatchPath = Join-Path $Downloads 'NSC-039-review.patch'
$TranscriptPath = Join-Path $Downloads 'NSC-039-run-output.txt'
$ReviewPath = Join-Path $Downloads 'NSC-039-delivery-review-001.json'
$DeliverySpecPath = Join-Path $Downloads 'NSC-039-delivery-spec-001.json'
```

Do not default these files to:

- the repository root;
- an arbitrary current directory;
- `$env:TEMP` when the tool accepts an explicit external output path;
- a container-only path such as `/tmp` or `/execution-output`;
- the Documents folder;
- an unspecified location that forces Vincent to find or move the file later.

The final sentence of the user's preference is authoritative: use **Downloads** as the default external handoff folder.

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
- any temporary helper file the human must later upload, inspect, or reuse.

When ChatGPT itself generates one of these files, provide it as a downloadable artifact with a descriptive filename. All subsequent PowerShell commands must target the exact Downloads path, rather than asking Vincent to save or move it manually.

## Important exceptions — do not move authoritative or tool-owned files

The Downloads preference does not mean every pipeline artifact should be relocated.

1. **Repository source, tests, contracts, documentation, and committed evidence** must remain at their exact repository paths.
2. **ExecutionCrew run artifacts** remain in the configured ExecutionCrew output root. Use the exact full Windows host path printed by the pipeline. Do not move the run directory just to satisfy the Downloads preference.
3. **Unity clean-validation artifacts** (`validation-manifest.json`, `test-results.xml`, and `unity.log`) are hash-bound to one another. Leave them exactly where the runner created them until TaskDelivery finalization and `record_delivery.py` finish. Moving, renaming, editing, or deleting any member can invalidate the manifest.
4. **TaskGraph evidence produced by `record_delivery.py`** belongs under `Pipeline/TaskGraph/evidence/...` and must not be redirected to Downloads.
5. If a tool requires a specific output directory for correctness, keep the authoritative file there. When a separate human handoff copy is safe and useful, create an explicitly labelled copy in Downloads without altering the authoritative original.

The practical rule is:

```text
human-authored or human-transferred external file -> Downloads
pipeline-owned/hash-bound/repository-authoritative file -> required authoritative location
```

## Transfer problems observed in the locality-audit history

A fresh agent should actively prevent these recurring failure modes.

### 1. Large inline prompts exceeded or destabilized the chat UI

A prior context hit the UI's maximum text limit. Long prompts were also repeatedly pasted through chat and PowerShell.

**Rule:** for long prompts, create a UTF-8 file in Downloads and load it with:

```powershell
$Prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath $PromptPath
```

Do not prefer a giant inline response when a durable prompt file is more reliable.

### 2. PowerShell here-string and quote errors corrupted prompts

The locality-audit history records: “The prompt quotes is wrong. this has happened before so maybe we are better off using a file.”

**Rule:** use a downloaded prompt file for long or quote-heavy content. Avoid asking Vincent to paste a huge `@' ... '@` block unless a file handoff is genuinely impossible.

### 3. Commands were accidentally concatenated

Observed failures included forms such as:

```text
git diff --cached --statgit commit ...
git rev-parse HEADgit commit ...
git commit ...git commit ...
```

These produced confusing pathspec errors or skipped intended steps.

**Rule:** provide one complete guarded PowerShell block, or clearly separated commands. Never place two executable commands adjacent without a newline or explicit separator. After a failing command, stop instead of printing later “PASS” messages.

### 4. Host and container paths were confused

Container paths such as `/execution-output/...` were useful inside Docker but poor human handoff paths on Windows. This caused manual path translation and repeated clarification.

**Rule:** whenever the human must open or upload a file, prefer the exact Windows host path. Preserve the container path only as machine metadata. Use `--host-output-root` where supported and never invent a Windows path from a container path.

### 5. Files were downloaded to an unexpected subfolder and then had to be moved

The locality-audit history includes repeated “download this file,” “find where it landed,” and “move it to the expected location” steps.

**Rule:** choose the final Downloads filename first. Commands must use that exact final path. Verify it before use:

```powershell
if (-not (Test-Path -LiteralPath $PromptPath -PathType Leaf)) {
    throw "Required file does not exist: $PromptPath"
}
```

Do not create an extra move step when the file can be saved correctly the first time.

### 6. Temporary paths and literal placeholders were copied into real commands

A literal placeholder such as:

```text
<paste the newly printed validation-manifest.json path>
```

was executed as though it were a real path.

**Rule:** runnable commands must contain real values or derive them programmatically. Do not place `<PLACEHOLDER>` text in a command block that Vincent is expected to paste. Capture actual printed paths when possible, or stop and ask for the exact path before producing the next command.

### 7. State was manually carried across agents, windows, commands, and branches

The postmortem correctly concluded that Vincent had become the orchestration layer between otherwise useful tools. Manual transfer included task IDs, branch names, checkout paths, run IDs, candidate paths, feedback paths, commit SHAs, manifest paths, and evidence paths.

**Rule:** every command block should establish and verify its own critical state:

```powershell
$ExpectedBranch = 'nsc-039-world-sprite-prefab-sorting'
$ActualBranch = (git branch --show-current).Trim()
if ($ActualBranch -ne $ExpectedBranch) { throw "Wrong branch: $ActualBranch" }
```

Prefer reading authoritative values from Git/tool output over relying on conversation memory.

### 8. Wrong checkout or stale context could make a valid command unsafe

Several parallel clones and branches existed at once. Commands that were correct in one checkout were wrong in another.

**Rule:** every substantial block should begin with an explicit `cd`, branch check, HEAD/base check when relevant, and clean-tree check. A fresh agent must not infer the active checkout from old chat text.

### 9. Ordinary `git diff` omitted untracked files

A patch review initially appeared incomplete because brand-new files were untracked and therefore absent from normal `git diff` output.

**Rule:** before exporting a complete review patch, inspect:

```powershell
git status --short --untracked-files=all
```

When appropriate, stage the exact approved file set and export the complete staged patch directly to Downloads:

```powershell
$PatchPath = Join-Path $Downloads 'descriptive-complete-review.patch'
git diff --cached --binary --output=$PatchPath
```

Never use `git add .` or `git add -A` merely to make a patch complete.

### 10. Windows/Linux line endings and Git stat markers looked like content changes

Windows host checkouts, Linux containers, Unity, and Git's `core.autocrlf` produced repeated false dirty-tree signals and CRLF warnings.

**Rule:** preserve the established Git compatibility settings for Windows bind mounts. For a suspected stat-only Unity marker, prove normalized equality first:

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

The locality-audit history includes raw Unity logs with trailing whitespace and evidence records that bind exact bytes. “Cleaning up” those artifacts after hashing would invalidate the record.

**Rule:** do not edit raw evidence for style. Do not move manifest-bound XML/log files before closeout. Treat exact artifact bytes and paths as authority-bearing data.

### 12. Output was sometimes too long to transfer back through chat reliably

Long smoke-test runs and diffs were truncated by the interface.

**Rule:** save verbose output directly to Downloads while still displaying it:

```powershell
$TranscriptPath = Join-Path $Downloads 'NSC-039-execution-output.txt'
& <command> 2>&1 | Tee-Object -LiteralPath $TranscriptPath
```

Then upload the saved file instead of pasting thousands of lines into chat.

### 13. External output inside the repository broke clean-tree preconditions

TaskDelivery and evidence tooling require a clean repository. Saving prompts, review JSON, specs, or ad hoc transcripts inside the checkout creates needless failures.

**Rule:** use Downloads for external prompt/review/spec/transcript files. Only source-controlled project files and authoritative evidence belong in the repository.

### 14. No-overwrite tools failed when old external output filenames were reused

TaskDelivery intentionally refuses to overwrite review/spec output files.

**Rule:** use descriptive, unique Downloads filenames, usually including task ID and sequence or timestamp:

```powershell
$ReviewPath = Join-Path $Downloads 'NSC-039-delivery-review-001.json'
$DeliverySpecPath = Join-Path $Downloads 'NSC-039-delivery-spec-001.json'
```

On a redo, increment the suffix rather than expecting overwrite.

## Required command style for future agents

When giving Vincent commands that create or consume handoff files:

1. Define `$Downloads` once.
2. Define every file path with `Join-Path` and a descriptive filename.
3. Write directly to that path.
4. Use `-LiteralPath` for PowerShell file operations.
5. Use UTF-8 explicitly for text.
6. Verify the file exists and is nonempty before consuming it.
7. Print the final full path.
8. Avoid runnable placeholders.
9. Guard checkout, branch, HEAD, and clean-tree state before destructive or authority-changing steps.
10. Stop immediately after a failed precondition.
11. Preserve tool-owned/hash-bound files in their authoritative location.
12. When the output is large, save it to Downloads and ask Vincent to upload the file rather than paste the output.

Preferred reusable PowerShell preamble:

```powershell
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
if (-not (Test-Path -LiteralPath $Downloads -PathType Container)) {
    throw "Downloads directory does not exist: $Downloads"
}
```

Preferred prompt-file pattern:

```powershell
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$PromptPath = Join-Path $Downloads 'Descriptive-Prompt.txt'

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
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$ReviewPath = Join-Path $Downloads 'NSC-039-delivery-review-001.json'
$DeliverySpecPath = Join-Path $Downloads 'NSC-039-delivery-spec-001.json'
```

Preferred patch-export pattern:

```powershell
$Downloads = Join-Path $env:USERPROFILE 'Downloads'
$PatchPath = Join-Path $Downloads 'NSC-039-complete-review.patch'
git diff --cached --binary --output=$PatchPath
if (-not (Test-Path -LiteralPath $PatchPath -PathType Leaf)) {
    throw "Patch was not created: $PatchPath"
}
Write-Host "Patch: $PatchPath"
```

## Fresh-context instruction

A fresh AI context should not ask Vincent to reconstruct old file paths or manually transfer large text when the repository, project files, or this document can supply the state.

Before producing operational commands, the fresh context should:

- inspect current Git/repository/TaskGraph state;
- read the current repository onboarding and runbook files;
- treat this Downloads preference as durable;
- create downloadable prompt/support files when content is long;
- use exact Windows host paths for human-facing files;
- save large command output to Downloads for upload;
- distinguish external handoff files from authoritative tool-owned artifacts;
- minimize the number of times Vincent has to copy, rename, move, retype, or translate data between systems.

The goal is not merely correct commands. The goal is a reliable handoff with as little human data shuttling as possible.

---

## Source note

The original long-form locality-audit transcript is historical analysis, not current repository authority. Current task, pipeline, and workflow state must be read from `Docs/AI-Pipeline/START_HERE.md`, `Docs/AI-Pipeline/CURRENT_STATE.md`, the real-task runbook, current task contracts, committed evidence, and the actual Git tree. This document preserves the durable operator-preference and transfer-safety conclusions extracted from that audit.
