# Operator Command Standards

This document defines the reliability and safety standards for human-run operator commands produced for this repository.

It is operating guidance, not game-design canon and not evidence of repository state.

These rules exist because this project has repeatedly encountered avoidable failures at the boundary between ChatGPT/Claude/Codex, Windows PowerShell 5.1, Git, GitHub CLI, Docker/Linux, Python, Unity, and multiple concurrent repository checkouts. The objective is not ceremony. The objective is that a command either succeeds with an explicit resulting state or stops safely with enough information to resume without guessing.

Use this document together with:

- `Docs/AI-Pipeline/OPERATOR_COMMAND_TEMPLATE.md` for the canonical substantial-command skeleton;
- `Pipeline/TaskReviewAgent/NativeCommand.ps1` for repository-owned native-process diagnostic/streaming behavior;
- `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md` for prompts, transcripts, logs, patches, and other human-facing handoffs;
- task-specific runbooks for the operation being performed.

The standards apply to commands produced by humans or agents. They especially apply to paste-ready PowerShell given to a human operator.

## Normative language

- **REQUIRED** — use this pattern unless a reviewed task-specific mechanism explicitly replaces it.
- **PROHIBITED** — do not use this pattern in a paste-ready operator command.
- **DISCOURAGED** — it can work, but a safer repository-approved form should normally be used.
- **READ-ONLY** — observes state without creating durable repository, GitHub, checkout, pipeline, or external state.
- **DURABLE MUTATION** — anything that can survive the current PowerShell process, including file edits, commits, refs, pushes, Issues, PRs, claims, checkouts, artifacts, stashes, or long-lived containers.

## 1. When the full standard applies

A clearly read-only one-liner such as:

```powershell
git status --short
```

does not need the full template.

A substantial command **must** follow `OPERATOR_COMMAND_TEMPLATE.md` when it can:

**REQUIRED: apply the two-strike runner escalation rule.** If an assistant-authored runner, validation harness, recovery script, or operator wrapper fails twice before successfully exercising its intended system behavior, stop producing incremental variants and follow `Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md` section 10.1. Preserve state, distinguish wrapper failure from a real system defect, and use a bounded read-only engineering agent before another mutation attempt.

- edit, create, move, or delete files;
- stage or commit Git changes;
- create, move, or delete branches, refs, tags, claims, or stashes;
- push or merge;
- create or update GitHub Issues or pull requests;
- create, modify, or remove a task checkout;
- execute a multi-step delivery/validation flow that may need resume logic;
- invoke a provider or other long-running external process;
- create an external artifact that later steps depend on.

## 2. Windows PowerShell compatibility and execution policy

### REQUIRED: assume Windows PowerShell 5.1

Unless the operator explicitly requests another shell, paste-ready PowerShell must run in Windows PowerShell 5.1.

### PROHIBITED: Bash-only syntax

Do not emit Bash constructs such as:

```text
< input.txt
VAR=value command
$(command) as Bash command substitution
```

inside a PowerShell runner.

### PROHIBITED: PowerShell-7-only syntax without an explicit PowerShell 7 requirement

Do not assume `&&`, `||`, or other newer conveniences merely because they work in `pwsh`.

### DISCOURAGED: continuation backticks

Prefer arrays, splats, parentheses, or natural PowerShell continuation. A trailing space after a backtick is nearly invisible and changes parsing.

### REQUIRED: keep compound syntax together

An `if`/`elseif`/`else`, `try`/`catch`/`finally`, loop, function definition, or here-string must be delivered as one complete syntactic unit. Do not split dependent syntax across multiple pastes.

### REQUIRED: separate adjacent commands explicitly

Every command must have a real PowerShell statement boundary. Review the final rendered command for accidental concatenation such as:

```text
git diff --cached --statgit commit ...
git rev-parse HEADgit push ...
```

### REQUIRED: disambiguate interpolation next to punctuation

Use:

```powershell
Write-Host "PR #$($PrNumber): $PrUrl"
```

rather than a bare variable immediately followed by punctuation that PowerShell may parse as part of the variable reference.

### PROHIBITED: `$PSScriptRoot`-dependent parameter defaults

Do not calculate a `param()` default from `$PSScriptRoot`.

Use:

```powershell
param(
    [string]$PromptPath
)

if ([string]::IsNullOrWhiteSpace($PromptPath)) {
    $PromptPath = Join-Path $PSScriptRoot "prompt.txt"
}
```

### REQUIRED: do not assume the current PowerShell process permits script execution

Interactive shells may use `Restricted` or another execution policy that blocks dot-sourcing or running repository `.ps1` files.

For a bounded trusted repository script, prefer a child process with an invocation such as:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath
if ($LASTEXITCODE -ne 0) {
    throw "Repository script failed with exit code $LASTEXITCODE."
}
```

`-ExecutionPolicy Bypass` here applies to that child PowerShell process; it is not a persistent machine/user policy change.

### PROHIBITED: weakening persistent execution-policy scopes for repository automation

Do not use `Set-ExecutionPolicy` on `CurrentUser` or `LocalMachine` merely to make a generated command run.

Do not instruct the operator to permanently weaken machine policy as a convenience workaround.

If Group Policy prevents the required bounded child process, fail closed and report that environmental restriction.

### REQUIRED: paste-ready blocks must not depend on dot-sourcing a repository helper

A paste-ready `& { ... }` block must not assume this succeeds:

```powershell
. $NativeHelper
```

If helper semantics are required inside an interactive paste-ready block, use a self-contained implementation or launch a checked-in bounded script through a child `powershell.exe -ExecutionPolicy Bypass` process.

## 3. Generated `.ps1` files must parse before execution

### REQUIRED: parser preflight

Generated PowerShell files must be parsed before execution:

```powershell
$Tokens = $null
$Errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref]$Tokens,
    [ref]$Errors
) | Out-Null

if ($Errors.Count -ne 0) {
    throw "Generated PowerShell script did not parse."
}
```

A parser failure means the script did not execute.

### REQUIRED: use PowerShell-5.1-safe source encoding

Executable `.ps1` source must be ASCII-safe when practical or saved using an encoding Windows PowerShell 5.1 reads correctly. Do not allow typographic punctuation plus the wrong UTF-8/BOM assumptions to turn source text into different PowerShell tokens.

Documentation files may use normal UTF-8; this rule is specifically about executable Windows PowerShell source.

## 4. Standalone commands own their critical state

A substantial paste-ready command must establish its own:

- repository root;
- expected origin/repository when remote authority matters;
- work item identity;
- expected branch or allowed branch set;
- reviewed/base SHA when applicable;
- target/patch/remote/merge SHA when already known;
- exact authorized paths;
- output/log path when external output matters.

### PROHIBITED: runnable placeholders

Do not ship a runnable block containing:

```text
<PASTE_SHA_HERE>
REPLACE_ME
SET_ME
<path from previous output>
```

Derive the value or stop and ask for the missing authority.

### REQUIRED: validate and set the working directory

Do not trust inherited CWD. A substantial block validates the expected root and then explicitly sets it before dependent commands run.

This protects against terminals left inside renamed, moved, or deleted checkouts.

### REQUIRED: repository authority comes from the checkout

When remote state can be changed, inspect the checkout's configured remote. Conversation text or a hard-coded repository may be used as an assertion, not as alternate authority.

## 5. Native executable semantics

Git, Docker, `gh`, Python, Unity command-line tools, and provider CLIs are native processes from PowerShell's perspective.

### REQUIRED: native success is determined from the process exit code

Do not infer native failure from stderr. Windows PowerShell 5.1 can surface ordinary native stderr as PowerShell `ErrorRecord` objects.

Capture `$LASTEXITCODE` immediately after the native command whose result it represents.

### REQUIRED: distinguish diagnostic output from machine data

This repository has two different native-output use cases:

1. **diagnostic/streaming output** — human-readable progress where stdout and stderr may be combined;
2. **machine data** — filenames, SHAs, refs, JSON, counts, exact paths, or other values used as authority.

They must not use the same capture semantics.

### REQUIRED: machine data must come from stdout only

When stdout is parsed as data, capture stdout and stderr separately. A Git warning such as an LF-to-CRLF message must never become a filename, SHA, JSON fragment, path, or count.

The following is prohibited for machine-data capture:

```powershell
$Output = @(& git diff --name-only 2>&1)
```

because stderr can contaminate `$Output`.

### IMPORTANT: `Invoke-NscNativeCommand.Output` is a combined diagnostic stream

`Pipeline/TaskReviewAgent/NativeCommand.ps1` intentionally merges native stderr and stdout into its `Output` collection so Windows PowerShell 5.1 does not treat ordinary stderr as a terminating error and so human-visible streaming remains coherent.

Therefore:

- `Invoke-NscNativeCommand` is appropriate for diagnostics, streaming, and exit-code checks;
- its `.Output` collection is **not** authoritative machine stdout;
- do not parse `.Output` as filenames, JSON, SHAs, refs, exact paths, or counts when stderr could exist;
- use a separate stdout/stderr capture path for machine-readable values.

### REQUIRED: every predicate declares valid exit codes

Commands such as:

```text
git diff --quiet
git show-ref --verify --quiet
git merge-base --is-ancestor
```

use nonzero exit codes as normal data. The caller must explicitly allow the documented result set, commonly `0` and `1`.

### PROHIBITED: captured line count as a predicate when diagnostics can enter the stream

Do not decide whether a file changed by counting arbitrary captured output. Prefer an exit-code predicate or parse stdout-only structured data.

### DISCOURAGED: `2>$null` as error handling

Suppressing stderr is not success checking. It can hide useful diagnostics and still does not establish the exit code.

### REQUIRED: structured machine output uses explicit encoding where relevant

When consuming JSON or other structured output, use UTF-8-aware tool options/decoding instead of relying on the Windows console code page.

## 6. Windows/Linux and host/container boundaries

### REQUIRED: normalize multiline arguments before Linux/Docker

Windows text may contain CRLF. Before textual arguments cross into Linux, normalize:

```powershell
$Normalized = $Value.Replace("`r`n", "`n").Replace("`r", "`n")
```

`Invoke-NscNativeCommand` already normalizes its argument list.

### REQUIRED: host Git is final changed-file authority for a Windows bind-mounted checkout

A Linux container can report mass CRLF/stat differences that Windows Git does not consider real content changes. For the actual Windows repository, host Git remains the final changed-file authority unless a task-specific policy explicitly establishes another authority.

## 7. Large and quote-heavy payloads belong in files

Use durable UTF-8 files for long prompts, JSON, patches, review packages, or quote-heavy nested-language content when practical.

This avoids:

- Windows command-line length limits;
- PowerShell quoting failures;
- nested `python -c` quote soup;
- chat/composer transport corruption;
- unreadable operator commands.

Load files explicitly, for example:

```powershell
$Prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath $PromptPath
```

Follow `OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md` for final handoff locations.

### DISCOURAGED: giant human-transferred here-strings

Here-strings are fine for short controlled literals. They are not the default transport for long prompts/documents that need inspection, reuse, upload, or audit.

## 8. Automated text editing

### PROHIBITED: unchecked newline-sensitive multiline replacement

Do not mutate a tracked file using a giant exact `.Replace()` whose match depends on unknown CRLF/LF representation.

Preferred order:

1. structured parser/editor;
2. line-based exact-anchor edit;
3. small Python/editor script with assertions;
4. normalized regex/text replacement with an exact expected match count.

### REQUIRED: prove the anchor count before mutation

For a one-location edit:

```text
0 matches  -> stop
1 match    -> continue
>1 matches -> stop
```

### REQUIRED: normalize before multiline textual matching when newline form matters

Normalize input before searching text whose exact newlines are relevant.

### REQUIRED: validate exact changed paths immediately after editing

If exactly two paths are authorized, compare actual path identity to those two paths. A file count alone is not sufficient.

### REQUIRED: preserve intentional encoding/newline behavior

Avoid incidental BOM or whole-file line-ending churn.

## 9. Git mutation safety

### REQUIRED: stage exact paths for bounded work

Use:

```powershell
git add -- path/one path/two
```

and verify the staged path set.

### PROHIBITED: convenience staging for bounded reviewed work

Do not use `git add .` or `git add -A` merely to gather the current tree. They can capture unrelated Unity churn, logs, generated files, or another agent's work.

### REQUIRED: give Git authority points distinct names

Use concepts such as:

```text
ReviewedBase
PatchCommit
RemoteBranchHead
PullRequestHead
MergeCommit
CurrentMain
```

Do not overload a generic `$ExpectedHead` across several different states.

### REQUIRED: rerunnable mutation is state-observing

A command that can create a commit, push, Issue, PR, merge, stash, checkout, or artifact must inspect current durable state before deciding the next action.

Do not assume:

```text
no [DONE] output -> nothing happened
```

### PROHIBITED: blind destructive recovery

Do not automatically use:

```text
git reset --hard
git clean -fd
force push
forced ref movement
```

as generic recovery.

If destructive recovery is genuinely required, it must be a separate reviewed action with an explicit statement of what will be discarded.

### PROHIBITED: blanket restore of unrelated paths

If one known generated/stat-only file is safe to restore, prove that exact path. Do not restore a whole directory merely to make the tree clean.

## 10. Path and checkout safety

### REQUIRED: use path APIs, not string slicing

Windows can expose equivalent paths using long names, 8.3 names, different separators, and different casing. Use `Join-Path`, `Path.GetFullPath`, Python `pathlib`, or Git-relative paths rather than substring arithmetic.

### REQUIRED: distinguish absolute and repository-relative paths

Do not prepend the repository root to a path that is already absolute.

### REQUIRED: use deliberately short Windows roots for deep repositories

Use established short roots such as `C:\NSC\NSC` and short disposable clone roots. Configure `core.longpaths` operation-locally when needed.

### PROHIBITED: global `safe.directory` as a generic fix

Correct the clone/source/ownership strategy rather than broadly weakening Git ownership checks.

## 11. Split deterministic preparation from expensive provider work

Normal provider-backed work should use two phases unless a reviewed pipeline entry point intentionally combines them:

```text
PHASE 1
    repository/task/checkout preparation
    deterministic validation
    print READY

PHASE 2
    re-observe prepared authority
    invoke provider
    stream progress
    persist transcript
    print result/handoff
```

This makes retries cheaper and prevents provider execution from beginning merely because deterministic setup succeeded.

## 12. Long-running visibility and lifecycle

### REQUIRED: announce phases

Use concise markers such as:

```text
[START]
[VERIFY]
[READ]
[PLAN]
[WORK]
[AGENT]
[TOOL]
[TEST]
[PASS]
[RETRY]
[BLOCKED]
[DONE]
```

### REQUIRED: show heartbeat or incremental activity for potentially long silent work

The operator should not have to guess whether a provider process is still active.

### REQUIRED: save verbose output when it may be needed later

Show concise live progress and save a durable transcript/log according to the handoff policy.

### PROHIBITED: open-ended interactive shells for bounded automation

Do not start an interactive Docker/provider shell and leave it running when the intended action is a one-shot command.

### REQUIRED: understand cleanup lifecycle

With `--rm`, a container disappearing after stop/exit is expected. A later `docker rm` saying "No such container" may mean cleanup already succeeded.

## 13. Output volume is part of correctness

Scope searches to relevant roots, filenames, bounded samples, or saved logs.

A command that floods the terminal with thousands of irrelevant lines is operationally poor even if technically correct.

Successful substantial commands end with concise authority:

```text
[DONE] <operation>
[STATE] Repository: ...
[STATE] Branch: ...
[STATE] Base: ...
[STATE] Patch/Result: ...
[STATE] Remote/PR/Merge: ...
[STATE] Working tree: CLEAN
[NEXT] <one concrete next action>
```

## 14. Failure classification and recovery

"Command failed" is too coarse. Recovery depends on where it stopped.

### Parse failure

The block/file did not parse.

Recovery:

- assume no execution occurred;
- correct syntax/encoding;
- parser-preflight before retry.

### Precondition failure

Repository/path/branch/authority/cleanliness checks stopped before the intended mutation.

Recovery:

- inspect why the precondition is false;
- do not force the expected state;
- revise the plan or authority.

### Expected predicate false

A documented result such as exit `1` means false/not-found/not-ancestor.

Recovery:

- treat it as data;
- do not report an operational failure.

### Runtime failure before durable mutation

Tools executed, but no durable mutation crossed its success boundary.

Recovery:

- diagnose;
- retry only when safe.

### Partial mutation

One or more durable steps succeeded before a later failure.

Examples:

```text
commit created, push failed
push succeeded, PR creation failed
PR exists, CI wait failed
merge succeeded, local update failed
file written, later validation failed
stash created, later switch failed
```

Recovery:

- do not blindly rerun;
- re-read Git/GitHub/filesystem state;
- verify and reuse completed work;
- continue from the next missing step.

### Transient operational failure

Retry only when the failure is positively classified by a narrow signature or typed outcome. Do not turn arbitrary operational failures into retry/contention behavior.

### Recovery output must not mask the original error

Recovery code may run before helpers, paths, or tools exist. It must be best-effort, defensive, and preserve the original exception.

## 15. Mutation ledger

For multi-boundary runners, a mutation ledger is recommended:

```text
FilesModified
CommitCreated
BranchPushed
IssueUpdated
PullRequestCreated
StashCreated
MergeCompleted
```

Set a field only after the durable result is independently re-observed.

The ledger is not authority. Current Git, GitHub, TaskGraph, files, and deterministic tests remain authoritative.

## 16. Quick do / do not reference

| Do | Do not |
| --- | --- |
| Assume Windows PowerShell 5.1 | Use Bash `< file` in a PowerShell block |
| Use child `powershell.exe -ExecutionPolicy Bypass -File` for a bounded trusted script | Change `CurrentUser` or `LocalMachine` execution policy just to run automation |
| Make paste-ready blocks self-contained | Dot-source a repository helper and assume the ambient policy permits it |
| Deliver complete syntactic blocks | Send `else`, `catch`, or dependent syntax separately |
| Resolve `$PSScriptRoot` defaults after `param()` | Use `$PSScriptRoot` in parameter-default evaluation |
| Define critical state inside the block | Depend on variables from a previous paste |
| Validate CWD, repo, branch, authority, and tree | Trust inherited shell state |
| Determine native success from exit code | Treat stderr as automatic failure |
| Keep stdout and stderr separate for machine data | Parse `2>&1` output as filenames/JSON/SHAs |
| Treat `Invoke-NscNativeCommand.Output` as diagnostics | Use its combined output as machine authority |
| Declare predicate exit codes | Treat every nonzero Git result as broken |
| Normalize CRLF before Linux | Pass raw Windows multiline text into Bash/Docker |
| Use exact-count structured/line-based edits | Use unchecked newline-sensitive multiline `.Replace()` |
| Compare exact changed paths | Trust only a file count |
| Stage exact approved paths | Use `git add .` or `git add -A` for bounded work |
| Observe current durable state before resume | Assume missing `[DONE]` means nothing happened |
| Give base/patch/remote/merge SHAs distinct names | Reuse one generic expected HEAD for all stages |
| Use path APIs | Derive relative paths by string slicing |
| Use short Windows roots | Create unnecessarily deep temp clones |
| Stream progress and save logs | Leave long-running commands apparently frozen |
| Launch bounded processes | Leave interactive shells/containers alive indefinitely |
| Print final/recovery authority | Make the operator infer state from raw output |

## 17. Agent pre-handoff checklist

Before an agent gives a human a substantial paste-ready command, review all relevant items.

### Syntax and shell

- Windows PowerShell 5.1 compatible?
- compound syntax complete?
- commands explicitly separated?
- unnecessary continuation backticks removed?
- interpolation unambiguous around punctuation?
- `$PSScriptRoot` defaults resolved after `param()`?
- generated `.ps1` parser-preflighted?
- does it avoid assuming ambient script execution is enabled?
- if running a trusted `.ps1`, is the bypass child-process-scoped rather than persistent?

### Identity and state

- establishes its own root and critical state?
- no literal placeholders?
- repository identity verified from checkout?
- correct branch/allowed branch set?
- base, patch, remote head, PR head, merge, and main distinguished where relevant?

### Resume behavior

- could an earlier run have partially succeeded?
- if yes, does it observe durable state before mutation?
- are existing commits/branches/PRs/stashes reused rather than duplicated?
- does failure output say what may already exist?

### Native processes

- success based on exit codes?
- expected predicate exits allowed?
- `$LASTEXITCODE` captured immediately when needed?
- is machine data captured from stdout only?
- can stderr contaminate any parsed filename/JSON/SHA/path/count?
- is combined `Invoke-NscNativeCommand.Output` limited to diagnostic use?

### Editing and Git scope

- edit anchors exact-count checked?
- newline format normalized before multiline matching?
- exact changed-file path set verified?
- exact staging used?
- destructive recovery absent unless separately reviewed?

### Cross-platform / paths / usability

- Linux/Docker multiline payloads LF-normalized?
- host/container authority kept distinct?
- path APIs used instead of string arithmetic?
- Windows path depth considered?
- large/quote-heavy payload should be a file instead?
- long work shows progress/heartbeat?
- verbose output saved if needed?
- terminal output bounded and readable?
- success ends with `[DONE]` and exact state?
- failure preserves original error and prints recovery state?

If a relevant answer is "no", correct the command before presenting it.

## 18. Machine-enforceable subset

Do not build a giant stylistic linter. Mechanical checks should target expensive, high-confidence failures.

Good checks include:

- parse repository-owned operator `.ps1` scripts with the Windows PowerShell parser;
- regression-test `Invoke-NscNativeCommand` stderr/exit-code and CRLF behavior;
- regression-test stdout/stderr separation for machine-data capture;
- ensure `AGENTS.md` and `CLAUDE.md` point to this standard/template;
- detect Bash input-redirection syntax in Windows PowerShell fixtures;
- detect `$PSScriptRoot` in parameter-default expressions;
- verify the template documents child-process execution-policy handling;
- verify the template does not dot-source `NativeCommand.ps1` as a paste-ready dependency;
- verify machine-data helpers use `StdOut` rather than the combined diagnostic `Output` collection;
- smoke-test reusable text editors against both CRLF and LF when such helpers exist.

## 19. Core principle

A good operator command does not merely work once under ideal conditions.

It should make these questions answerable from its text and output:

```text
Where am I?
What repository am I operating on?
What authority did I verify?
What already happened?
What is the next missing mutation?
What exactly changed?
Did the native tool actually succeed?
Did stderr contaminate any machine data?
What validation passed?
If it stopped, did anything durable already happen?
Is rerunning safe, or must state be re-observed first?
What should happen next?
```

Prefer a slightly longer command that answers those questions over a shorter command that leaves authority implicit.
