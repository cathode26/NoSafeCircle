# Agent Job Directory Standard

This document defines the canonical writable scratch/output boundary for Claude and Codex jobs used by NoSafeCircle operator runners.

It is durable operating guidance. Read it together with:

- `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`;
- `Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md`;
- `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`.

The purpose is simple: an agent frequently needs somewhere legitimate to write test fixtures, temporary scripts, caches, intermediate reports, or provider-owned job artifacts even when the repository under review must remain physically read-only. A writable scratch requirement must not be solved by making the repository broadly writable.

## 1. Canonical provider job roots

The canonical Windows host roots are:

```text
Claude: C:\NSC\NSC\.claude-jobs
Codex:  C:\NSC\NSC\.codex-jobs
```

Inside the provider container, mount the selected provider root at:

```text
/agent-jobs
```

These directories are intentionally outside the `NoSafeCircle` repository checkout. They are provider working areas, not repository source and not TaskGraph evidence.

### REQUIRED: provider isolation

A Claude job uses `.claude-jobs`.

A Codex job uses `.codex-jobs`.

Do not casually share one provider's writable job root with the other provider. Cross-provider review should use the reviewing provider's own root.

## 2. Every substantial provider run gets a dedicated subdirectory

Do not treat the provider root itself as one undifferentiated scratch directory.

Create a bounded job subdirectory for the run, for example:

```text
C:\NSC\NSC\.claude-jobs\decomposition-authorization-correction-v1
C:\NSC\NSC\.codex-jobs\decomposition-authorization-rereview-v1
```

The container sees those as:

```text
/agent-jobs/decomposition-authorization-correction-v1
/agent-jobs/decomposition-authorization-rereview-v1
```

Use a work-specific stable name when one run is expected, or include a run ID/timestamp when repeated attempts must remain distinct.

### REQUIRED: no-overwrite/recovery awareness

A previous provider run may have left useful evidence in its job directory even when the enclosing runner failed.

Do not automatically delete, empty, or reuse a non-empty job directory after a provider failure. Inspect the current state first. Prefer a fresh run-specific subdirectory when a clean retry is required.

## 3. Review boundary

For an independent read-only review, the preferred filesystem authority is:

```text
/workspace   -> repository mounted read-only
/agent-jobs  -> reviewing provider's job root mounted read/write
```

The reviewer may use `/agent-jobs/<job>/` for approved scratch/test artifacts while the source tree remains physically immutable.

Examples of legitimate job-directory content include:

- Python caches;
- temporary deterministic test fixtures;
- disposable Git repositories created solely for adversarial tests;
- reviewer-created reproduction scripts;
- intermediate machine-readable reports;
- provider stream/debug output when a task-specific runner chooses to preserve it.

### REQUIRED: command permission is a separate authority

A writable `/agent-jobs` mount does not itself authorize shell commands, Python execution, network access, GitHub mutation, or repository edits.

The runner/prompt must separately grant only the tools/commands needed by that job.

Likewise, granting Bash/Python execution does not make `/workspace` writable when Docker mounted it read-only.

## 4. Bounded implementation/correction boundary

For an implementation or targeted correction, repository writes may be authorized when the job explicitly requires them, but the job directory is still the preferred location for scratch and generated temporary material.

The prompt must state the exact repository write boundary.

The host runner must verify the actual changed path set after the agent exits.

A typical authority shape is:

```text
/workspace   -> writable only because this implementation job is authorized to edit source
/agent-jobs  -> provider scratch/output
host runner  -> verifies exact tracked + untracked repository path boundary
```

Do not use a writable job directory as an excuse to broaden repository writes, and do not use repository write authority as an excuse to place scratch files in the source tree.

## 5. What does NOT belong in provider job directories

Provider job directories are not replacements for authoritative project locations.

Do not relocate these merely to fit `/agent-jobs`:

- committed source, tests, contracts, or documentation;
- TaskGraph evidence;
- Git commits/refs/branches;
- authoritative ExecutionCrew output roots and `AgentRunner` provider logs when the production pipeline defines their location;
- hash-bound Unity validation artifacts;
- durable GitHub Issue/PR state;
- human-facing handoff files whose canonical destination is `Downloads\NoSafeCircleOutput\<WorkId>\<RunId>\`.

The practical split is:

```text
provider scratch / adversarial fixtures / temporary scripts -> provider job directory
human-transferred reusable handoff -> Downloads\NoSafeCircleOutput\<WorkId>\<RunId>\
repository/pipeline authority -> its required canonical location
```

## 6. Docker mount construction

For `docker compose run`, use Compose's supported `-v` / `--volume` option. Do not use the `docker run --mount` form with `docker compose run`; Compose's `run` command does not expose `--mount`.

For a Claude job, a runner may construct a mount equivalent to:

```powershell
$ClaudeJobs = "C:\NSC\NSC\.claude-jobs"
$JobName = "example-job"
$JobHostPath = Join-Path $ClaudeJobs $JobName
New-Item -ItemType Directory -Force -Path $JobHostPath | Out-Null

$DockerArgs = @(
    "compose",
    "-p",
    "nosafecircle",
    "run",
    "--rm",
    "-T",
    "-v",
    ($ClaudeJobs + ":/agent-jobs:rw")
)
```

For Codex, use `C:\NSC\NSC\.codex-jobs` instead.

The exact provider service/arguments remain task-specific. This document standardizes the writable job boundary, not the provider invocation itself.

## 7. Direct intentional scratch should prefer the job directory

When a provider job deliberately creates scratch artifacts, test fixtures, reproduction scripts, or caches, prefer:

```text
/agent-jobs/<job>/...
```

over writing them into `/workspace`.

System/runtime tools may still use container `/tmp` internally when unavoidable, but operator-authored prompts and runners should direct intentional inspectable scratch to the provider job directory so the host can locate it after the container exits.

When configuring Python for a provider-backed job, a suitable pattern is:

```text
PYTHONPYCACHEPREFIX=/agent-jobs/<job>/pycache
```

## 8. Final log disclosure is mandatory

Every substantial Claude/Codex runner that mounts a provider job directory MUST print the exact host and container job paths at the end of its successful report.

Use these exact labels:

```text
[JOB-DIRECTORY] Host: <absolute Windows host job path>
[JOB-DIRECTORY] Container: /agent-jobs/<job>
```

Example:

```text
[JOB-DIRECTORY] Host: C:\NSC\NSC\.claude-jobs\decomposition-authorization-correction-v1
[JOB-DIRECTORY] Container: /agent-jobs/decomposition-authorization-correction-v1
```

This requirement exists so the operator never has to infer where an agent wrote its scratch/output from Docker arguments or conversation memory.

### REQUIRED: failure output should disclose the directory when practical

If a provider run fails after the job directory has been established, the runner should print or preserve the same host/container path in its recovery output when practical so evidence can be inspected before any retry.

Do not claim that a directory was unused or safe to delete merely because the provider returned nonzero.

## 9. Host-side repository validation remains authoritative

A provider job directory is not repository authority.

After a provider exits, host-side validation must still establish the relevant repository facts, such as:

- current branch and HEAD;
- empty/non-empty index;
- exact tracked changed paths;
- exact untracked paths;
- expected frozen-file hashes when used;
- required deterministic tests;
- commit/push state.

Provider-created reports under `/agent-jobs` are diagnostic inputs to that validation, not substitutes for it.

## 10. Canonical rule summary

```text
Claude scratch root  = C:\NSC\NSC\.claude-jobs
Codex scratch root   = C:\NSC\NSC\.codex-jobs
container mount      = /agent-jobs
compose run mount    = -v <host-root>:/agent-jobs:rw
one substantial run  = one dedicated job subdirectory
read-only review     = /workspace:ro + /agent-jobs:rw
implementation       = exact source-write boundary + /agent-jobs:rw
intentional scratch  = /agent-jobs/<job>
human handoff        = Downloads\NoSafeCircleOutput\<WorkId>\<RunId>\
end-of-run log       = print [JOB-DIRECTORY] Host and Container
```

If a future task needs a different writable scratch location for a concrete technical reason, that exception must be explicit in the task-specific runner/prompt. Do not silently fall back to broad repository write access.
