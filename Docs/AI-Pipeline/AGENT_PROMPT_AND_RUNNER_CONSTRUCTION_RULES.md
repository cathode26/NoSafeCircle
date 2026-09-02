# Agent Prompt and Runner Construction Rules

This document is durable operating guidance for assistants, agent authors, and operator-runner authors working in NoSafeCircle.

It complements `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`. That file governs human-facing file handoff and operator-locality conventions. This file governs how to construct **agent assignments, generated PowerShell runners, native-command wrappers, verification code, long-running provider jobs, and recovery paths** so that an otherwise-correct task is not made unsafe by the wrapper around it.

The rules below come from repeated concrete failures in the live orchestrator work, including the command-governance backlog in GitHub Issue #103. Treat them as engineering constraints, not stylistic preferences.

## 1. Governing principles

A generated runner is part of the system being tested. It must be held to the same fail-closed standard as production code.

The default principles are:

```text
current committed repository state > remembered prose
explicit authority > implied authority
one semantic argument > clever inline expression
machine-readable producer schema > guessed consumer shape
native exit code > presence/absence of stderr
exact machine bytes > convenience trimming
verified durable state > assumption after a failed runner
bounded mutation > broad cleanup
observable long-running work > silent black box
```

When a command or prompt can mutate durable state, prefer boring, explicit, independently verifiable construction.

## 2. Failure classes

Classify failures before deciding how to recover.

| Class | Meaning | Default recovery |
| --- | --- | --- |
| `PARSE` | Script could not be parsed; no command body ran. | Fix parser defect and rerun only after confirming no mutation occurred. |
| `PRECONDITION` | Guard or verifier rejected current state before intended mutation. | Inspect current state; correct the guard or underlying state. |
| `EXPECTED_PREDICATE_FALSE` | A read-only predicate legitimately returned false/nonzero. | Handle the predicate explicitly; do not treat it as an operational crash. |
| `RUNTIME_BEFORE_DURABLE_MUTATION` | Runner began but failed before authoritative state changed. | Continue from current verified state; do not reset by reflex. |
| `PARTIAL_MUTATION` | Some durable state changed before failure. | Inspect exact external state first; continue forward from what actually happened. |
| `TRANSIENT_OPERATIONAL` | Provider/network/service timing failure without semantic mismatch. | Retry only the read/operation that is safe to repeat, within a bound. |

Never assume a failed script means "nothing happened." The failure location determines recovery.

## 3. Prompt construction: define authority before instructions

Every substantial agent prompt should make these boundaries explicit before asking the model to do work:

1. **Repository identity** — exact repository and, when relevant, exact base commit.
2. **Job scope** — what problem this run solves and what it deliberately does not solve.
3. **Read authority** — what the agent may inspect.
4. **Write authority** — exact allowed paths or an explicit statement that the run is read-only.
5. **Command authority** — whether shell/tests/builds are allowed. Repository search/read is not the same thing as approved command execution.
6. **Git authority** — whether the model may commit, push, create branches, merge, reset, rebase, or force-push.
7. **GitHub authority** — whether the model may mutate Issues/PRs or only inspect local state.
8. **Live-system authority** — whether workers, bootstrap, live tests, or durable leases may be touched.
9. **Finish condition** — exact expected artifacts, tests, diff state, and final report.
10. **Failure behavior** — fail closed and preserve the working state instead of weakening an invariant.

A useful prompt shape is:

```text
GOAL
CURRENT AUTHORITY / BASE
READ BEFORE EDITING
ALLOWED WRITES
FORBIDDEN MUTATIONS
ARCHITECTURAL INVARIANTS
REQUIRED TESTS
FINISH CONDITION
FAILURE / RECOVERY RULE
```

Do not bury mutation authority in the middle of a long prose prompt.

## 4. Do not one-shot an unnecessarily large lifecycle

A coding agent can inspect, edit, test, and iterate internally, but that does not mean every architectural boundary belongs in one job.

Split work when each half can be independently proven. Prefer:

```text
Job 1: deterministic mechanism + local proof
review / merge
Job 2: wire proven mechanism into durable orchestration
```

over:

```text
one prompt: implementation + durable workflow + evidence + integration + closeout + concurrency
```

A good split has a stable API boundary and lets the second job depend on the first job's **actual reviewed interface**, not a guessed future interface.

Do not use the unfinished orchestration layer under test as the sole mechanism for implementing that same layer when an isolated coding job is safer.

## 5. Long prompts belong in files, not shell quoting

For long, quote-heavy, or reusable prompts:

- write a UTF-8 prompt file;
- hash it;
- have the launcher verify the hash before execution;
- copy the exact prompt into the run's durable output folder;
- pass it to the provider through stdin or a file path.

Avoid giant PowerShell here-strings and Bash input-redirection assumptions crossing Windows/Linux boundaries.

Recommended operator pattern:

```powershell
$ExpectedHash = "<sha256>"
$ActualHash = (Get-FileHash -LiteralPath $PromptPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedHash) {
    throw "Prompt SHA-256 mismatch."
}
```

For generated `.ps1` files, run a Windows PowerShell parser preflight before any mutation.

## 6. Generated PowerShell: parser preflight is mandatory

A generated PowerShell runner that can mutate state must be parsed before it runs.

Representative parser check:

```powershell
$Tokens = $null
$Errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref]$Tokens,
    [ref]$Errors
)
if ($Errors.Count -ne 0) {
    $Errors | ForEach-Object { Write-Host ("[PARSE] " + $_.Message) }
    throw "PowerShell parser preflight failed."
}
```

This catches deterministic failures before they become operational incidents.

### 6.1 Variable interpolation before `:`

**PROHIBITED:**

```powershell
"$Label: failed"
"$TaskId: blocked"
```

Windows PowerShell can parse the colon as part of the variable reference.

**REQUIRED:**

```powershell
"$($Label): failed"
"${TaskId}: blocked"
```

This failure was observed during generated-runner parser preflight and correctly stopped before mutation.

## 7. Native-command argument construction

PowerShell syntax that looks like one expression does not guarantee the child process receives one argument.

### 7.1 Precompute every semantically single compound argument

**PROHIBITED:**

```powershell
$Args = @(
    "fetch",
    $Remote,
    "refs/heads/main:refs/remotes/" + $Remote + "/main"
)
```

This shape was observed to split the intended refspec into multiple child arguments.

**REQUIRED:**

```powershell
$TrackingRefspec = "refs/heads/main:refs/remotes/$Remote/main"
$Args = @("fetch", $Remote, $TrackingRefspec)
```

The same rule applies to refspecs, path expressions, `-c` configuration strings, JSON fragments, URLs, and provider arguments.

### 7.2 Avoid quote-bearing native mini-languages

Windows PowerShell argument passing can corrupt embedded quotes in native mini-languages. An intended `join(",")` expression was observed by the child as `join(,)`.

Prefer quote-free selectors and multiple simple reads:

```text
.[].number
.title
.url
.labels[].name
```

instead of constructing TSV/CSV inside `jq` or another native mini-language.

If quotes are unavoidable, add a deterministic argv-shape smoke test.

### 7.3 Do not append infix operators to an unparenthesized command invocation

**PROHIBITED:**

```powershell
Get-MachineText -FilePath gh -ArgumentList $Args -split "\r?\n"
```

PowerShell may interpret `-split` as a named parameter.

**REQUIRED:**

```powershell
$Text = Get-MachineText -FilePath gh -ArgumentList $Args
$Lines = @($Text -split "\r?\n")
```

The same rule applies to `-replace`, comparisons, and other operators.

## 8. Machine data: preserve the producer's semantics

### 8.1 Do not trim whitespace-sensitive formats

A helper that returned:

```powershell
(($Result.StdOut -join "`n").Trim())
```

corrupted the first `git status --porcelain=v1` record by removing its meaningful leading space.

Separate helpers by contract:

- **scalar helper** — may trim an isolated SHA/count/login when the producer contract permits it;
- **exact-output helper** — preserves leading/trailing whitespace and record shape.

Prefer a purpose-specific producer when possible. If only filenames are authority, use `git diff --name-only` rather than parsing porcelain status columns.

### 8.2 Do not guess JSON schema paths

A live verifier incorrectly expected:

```text
dispatch_plan.resume.workflow_state.phase
```

while the committed producer deliberately exposes:

```text
dispatch_plan.resume.phase
```

A verifier must bind to the producer's **committed serializer/schema**, not to a structure that seems plausible from adjacent APIs.

Before writing a mutation-gating verifier:

1. inspect the producer implementation or committed schema;
2. capture a real deterministic example when practical;
3. test the exact consumer path.

### 8.3 Do not infer cardinality from PowerShell pipeline shape

Under Windows PowerShell 5.1:

```powershell
@($Json | ConvertFrom-Json).Count
```

can report `1` for JSON `[]` because the empty JSON array may remain one array object rather than enumerate to an empty pipeline.

**PROHIBITED** as machine-authority cardinality.

Prefer native scalar calculation when available:

```powershell
gh ... --json number --jq length
```

If object parsing is required, explicitly normalize null / array / single-object shapes before counting.

### 8.4 Empty collections must be valid when zero is valid

A mandatory PowerShell collection parameter rejects an actual empty array unless the contract permits it.

If zero items are a legitimate precondition, use an appropriate binding contract such as `[AllowEmptyCollection()]` or avoid a mandatory binding shape that rejects the valid empty state.

Test zero-item behavior explicitly.

## 9. Stdout, stderr, and exit-code authority

Do not infer failure from stderr text alone.

Docker Compose, Claude live rendering, and many healthy native tools write progress to stderr. With `$ErrorActionPreference = "Stop"`, merging stderr into a pipeline can also trigger `NativeCommandError` behavior even when the native process is healthy.

Rules:

- native **exit code is authoritative** for native command success/failure unless a stronger tool-specific contract exists;
- capture `$LASTEXITCODE` immediately after the native pipeline;
- do not use combined stdout/stderr as machine-readable authority;
- combined output is diagnostic/presentation only;
- keep machine stdout and diagnostic stderr separate when parsing JSON, SHAs, refs, counts, or paths.

`Pipeline/TaskReviewAgent/NativeCommand.ps1` may expose combined diagnostic output; do not feed that combined channel into machine parsing just because it is convenient.

Expected nonzero predicates such as `git diff --quiet`, `git show-ref --verify --quiet`, or absence checks must explicitly allow their documented nonzero result.

## 10. State-blind reruns are prohibited

A previous command may have partially succeeded even if the enclosing runner failed.

Before rerunning a mutating operation, inspect:

- current branch;
- current HEAD;
- clean/dirty/staged/untracked state;
- remote branch/ref state;
- GitHub Issue state when relevant;
- claim refs;
- whether a commit/push/PR/Issue mutation already occurred.

Recovery must continue from **current durable state**, not from the script author's expected phase.

Do not reflexively recommend:

```text
git reset --hard
git clean -fd
force-push
delete/recreate Issue
rerun bootstrap
```

Those destroy evidence and can convert a recoverable partial mutation into data loss.

### 10.1 Two-strike runner escalation

When an assistant-authored runner, validation harness, recovery script, or operator wrapper fails twice before successfully exercising the intended system behavior, stop generating incremental runner variants.

After the second wrapper/harness failure:

1. preserve the current repository, Git/GitHub, checkout, provider-job, and external-artifact state;
2. determine whether either attempt crossed a durable mutation boundary;
3. do not generate or recommend a third incremental variant by guesswork;
4. launch one bounded read-only engineering agent to inspect the failed runners, current repository authority, relevant standards, and underlying task;
5. require the agent to classify the failures and recommend the smallest correct path forward;
6. resume mutation only after that independent diagnosis is reviewed against current authority.

This rule applies to failures in the **assistant-authored wrapper or proof mechanism**. It does not count a successful runner that reaches the intended system and reveals a genuine product, pipeline, test, or repository defect; investigate that real defect normally.

The escalation shape is:

```text
Attempt 1 wrapper/proof failure
    -> inspect evidence
    -> make one targeted correction

Attempt 2 wrapper/proof failure
    -> STOP generating variants
    -> preserve state
    -> read-only engineering agent investigation
    -> agent-supported correction or existing approved mechanism
```

Do not use the escalation agent as permission to mutate. Its default role is diagnosis and recommendation unless a later, separately authorized step grants write authority.

## 11. Separate deterministic setup from provider execution

For substantial operator jobs, keep these phases distinct:

```text
Phase 1: deterministic setup / clone / branch / preflight / READY
Phase 2: provider execution
Phase 3: host-side deterministic validation
Phase 4: host-owned commit/push/PR, if authorized
```

Do not invoke Claude/Codex merely because clone/setup succeeded.

For coding-agent jobs, the safest pattern is often:

```text
host creates disposable clone and branch
    -> agent edits/tests only
    -> host validates exact changed path set
    -> host reruns authoritative tests
    -> host commits exact validated files
    -> host verifies base did not move
    -> host pushes review branch
    -> host opens PR
```

This keeps Git/GitHub mutation authority out of the model's implementation turn unless there is a specific reason to grant it.

### 11.1 Reuse canonical mutation APIs before generating new mutation code

Before generating a commit, push, pull-request, merge, or closeout runner, inspect the current repository for an existing production API or approved runner that already owns that lifecycle operation. Reuse that mechanism when the current lifecycle satisfies its preconditions.

The precedence is:

```text
existing production API
    >
existing approved runner
    >
small wrapper around an existing API
    >
new bespoke mutation runner
```

For a normal Game Task Agent implementation candidate, the canonical implementation commit/push path is `Pipeline/TaskReviewAgent/candidate_integration.py` through `CandidateIntegrator.integrate()`, normally invoked by `ProductionTaskController.integrate_commit_push_and_handoff()` in `Pipeline/TaskReviewAgent/production_pipeline.py`. That path already verifies the `review_ready` ExecutionCrew receipt and candidate identity, validates the patch in a disposable clone, proves the exact changed-path set, runs `git diff --check` and TaskGraph validation, stages only the verified paths, configures the guarded automation identity, creates the implementation commit, verifies its parent/path set, performs a guarded exact push, verifies the remote commit, persists the integration receipt, and binds the human handoff to the committed SHA. Do not replace this path with a bespoke implementation commit/push runner.

For delivery evidence, pull-request creation, merge closeout, and post-merge conformance, use the existing downstream TaskReviewAgent lifecycle (`DownstreamTaskController` and the production downstream actions) rather than constructing parallel Git/GitHub mutation code.

These APIs are lifecycle-bound. Do **not** fabricate a task lease, ExecutionCrew receipt, delivery approval, or other authority merely to force unrelated infrastructure/repository maintenance through a task-specific API. Infrastructure or review work outside those lifecycles remains host-owned exact-path mutation: validate the bounded diff, use the repository's guarded automation identity (`Pipeline/TaskReviewAgent/git_identity_guard.py`), stage only the exact validated paths, recheck the base/ref before publication, then commit/push only within the explicitly authorized infrastructure boundary.

When in doubt, stop and document the missing reusable capability rather than silently creating a second production mutation path.

## 12. Write-boundary enforcement must happen twice

A prompt-level write boundary is necessary but not sufficient.

For an isolated coding agent:

1. tell the model the exact allowed/denied paths;
2. after the model exits, compute the actual tracked + untracked changed path set;
3. reject any path outside the allowed boundary;
4. rerun the path-set check after tests, because tests can generate files;
5. stage only the exact validated paths;
6. verify the staged set exactly matches the validated set.

Never use `git add .` or `git add -A` as a substitute for an explicit changed-file contract.

## 13. Base/ref binding and TOCTOU checks

Long-running agent jobs can outlive the base commit they were designed against.

Before the agent starts, verify:

- source clone clean;
- exact expected `origin/main`;
- review branch absent if the job requires a fresh branch;
- expected remote/repository identity.

After the agent and host-side tests finish, recheck the base **before commit/push**.

If production/private main moved while the job ran, stop before publishing and re-evaluate. Do not silently rebase a reviewed/generated result onto a new base.

For native refspecs, precompute the full scalar refspec before passing it to Git.

## 14. Repository and credential isolation

Prefer a disposable clone outside the controller/source repository for agent writes.

A model writing inside the same controller checkout can contaminate:

- branch state;
- dirty-tree preconditions;
- Docker bind mounts;
- generated output directories;
- source-vs-agent authority checks.

When credentials are needed inside Docker, mount only the provider credential volume required for that job. Do not automatically expose host GitHub credentials to an implementation agent if the host can retain push/PR authority.

Repository identity must be derived from actual origin configuration, not trusted merely because a directory name contains `Gauntlet`, `NSC`, or another expected token.

## 15. GitHub write-after-read / read-after-write rules

Durable GitHub mutation and verification are separate operations.

When a workflow performs a GitHub mutation and then verifies it:

- never replay the mutation merely because an immediate read is stale;
- retry **reads only**, within a bounded schedule;
- accept only the exact expected state;
- fail closed on conflicting same/newer state;
- preserve durable state for recovery.

Do not assume one immediate `find()`/GET after `add_comment`/Issue update is sufficient on a live API.

This rule applies to leases, releases, state transitions, and closeout verification.

## 16. Long-running provider jobs must be observable

A long provider job must not look dead merely because the provider is still reasoning.

A production-quality runner should provide both:

1. **durable full stream logging**; and
2. **human-readable live presentation** or heartbeat.

### Claude

Claude Code can emit `stream-json` with partial messages. A renderer can display concise assistant/tool activity while the raw stream is tee'd to a durable log.

### Codex

`codex exec --json` emits discrete JSONL events rather than Claude-style token deltas. Do not simply invoke it through a silent wrapper and wait for `final.txt`.

A good Codex runner should:

- tee the complete JSONL stream to `codex-stream.log`;
- render useful event summaries to the operator when possible;
- emit a periodic heartbeat if no human-readable event has arrived for a bounded interval;
- preserve `final.txt` separately;
- treat raw JSONL as diagnostic provenance, not as a replacement for host-side validation.

Silence is an operator-experience defect even when the process is healthy.

## 17. Docker image/service lookup must be deterministic

Do not assume a Compose subcommand will return an image ID merely because a build succeeded.

A live runner observed:

```text
Compose build succeeded
-> compose images -q <service> returned empty
-> runner stopped before provider execution
```

When using an explicit Compose project name and service with the default image naming convention, compute the expected image name once and verify it with `docker image inspect`.

Example:

```powershell
$ComposeProject = "gauntlet-codex-job1-evidence"
$Image = "$($ComposeProject)-codex"
docker compose -p $ComposeProject -f $ComposeFile build codex
if ($LASTEXITCODE -ne 0) { throw "Build failed." }
docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) { throw "Expected image is missing: $Image" }
```

If the Compose file specifies an explicit `image:` value, use that committed value instead of guessing the default name.

## 18. Provider-internal access is not workflow command authority

Prompts and documentation must distinguish these concepts:

- repository read/search tools available inside Claude/Codex;
- repository write/edit tools inside an explicitly isolated writable clone;
- approved workflow command execution;
- host-side test execution;
- Git/GitHub mutation authority.

Granting repository search does not imply shell authority. Granting Edit/Write in a disposable clone does not imply permission to run project commands, commit, push, mutate Issues, launch workers, or merge.

State each independently.

## 19. Verifiers should prove what matters, not parse convenient surrogates

Examples:

- If filenames are authority, compare a filename set, not formatted porcelain text.
- If Issue count is authority, request a scalar count from the producer.
- If a branch head is authority, resolve the exact ref SHA.
- If a producer's JSON field is authority, consume the committed serializer's exact field.
- If a task branch must be absent, query that exact branch ref.

Avoid broad `grep`, display-formatted output, terminal wrapping, or human presentation strings as machine authority.

## 20. Recovery output is part of the runner contract

On failure, a substantial runner should print enough state for the next operator/assistant to continue safely:

```text
[RECOVERY] phase
[RECOVERY] branch
[RECOVERY] HEAD
[RECOVERY] committed? pushed? PR-created?
[RECOVERY] unstaged paths
[RECOVERY] staged paths
[RECOVERY] relevant durable Issue/ref state when safe to read
[RECOVERY] explicit DO NOT RESET/CLEAN/FORCE-PUSH instruction
```

Do not print a generic "failed" message that forces the next context to rediscover whether the mutation occurred.

## 21. Runner severity vocabulary

Use these labels in design/review when helpful:

- `REQUIRED` — omission makes the operation insufficiently safe or observable.
- `DISCOURAGED` — allowed only with a reason and compensating verification.
- `PROHIBITED` — known-bad construction or authority violation.

Examples:

| Pattern | Severity |
| --- | --- |
| Parser preflight for generated mutating `.ps1` | REQUIRED |
| Exact base/branch/clean-tree checks | REQUIRED |
| Provider prompt file + hash for long prompt | REQUIRED for long generated jobs |
| Host validation of agent changed-path set | REQUIRED for bounded agent jobs |
| `@($Json | ConvertFrom-Json).Count` as cardinality authority | PROHIBITED |
| `.Trim()` on Git porcelain/protocol records | PROHIBITED |
| Inline compound native argument without full parenthesization | PROHIBITED |
| Guessing JSON nesting from adjacent APIs | PROHIBITED |
| Broad reset/clean after an uncertain partial mutation | PROHIBITED |
| `git add .` for bounded review job | PROHIBITED |
| Full-stream log + live rendering/heartbeat for long provider job | REQUIRED |
| Giant quote-heavy inline prompt | DISCOURAGED |
| Quote-bearing `jq` in Windows PowerShell | DISCOURAGED; require argv proof if unavoidable |

## 22. Preflight checklist for an agent-job launcher

Before provider execution:

- [ ] exact source repository exists;
- [ ] source repository identity/origin is correct;
- [ ] source/controller clone is clean;
- [ ] expected base SHA is exact;
- [ ] remote base is still exact;
- [ ] target branch/path collision policy is explicit;
- [ ] prompt file exists and SHA-256 matches;
- [ ] generated PowerShell parses under the target PowerShell version;
- [ ] provider credential volume is explicitly selected and authenticated;
- [ ] Docker image/service identity is verified;
- [ ] live Issue/claim invariants are checked only if the job actually depends on them;
- [ ] agent write boundary is explicit;
- [ ] Git/GitHub mutation authority is explicit;
- [ ] durable output/log directory is known;
- [ ] operator will see live progress or heartbeat.

After provider execution:

- [ ] agent did not change branch/HEAD unexpectedly;
- [ ] changed tracked + untracked path set is exact and allowed;
- [ ] host-side authoritative tests rerun;
- [ ] changed path set rechecked after tests;
- [ ] `git diff --check` passes;
- [ ] base/main rechecked before commit/push;
- [ ] stage exact paths only;
- [ ] staged set equals validated set;
- [ ] commit parent is the expected base;
- [ ] push uses an explicit precomputed refspec;
- [ ] PR is opened only if authorized;
- [ ] no live worker/bootstrap/Issue mutation occurred unless explicitly authorized;
- [ ] recovery state is printed if any step fails.

## 23. Relationship to Issue #103

GitHub Issue #103 remains the durable backlog for command-governance follow-up work discovered after the earlier command standards. This document incorporates its observed classes, including:

1. PowerShell 5.1 JSON cardinality/pipeline-shape trap;
2. quote-bearing native mini-language corruption;
3. mandatory empty-array binding failure;
4. operator tokens parsed as parameters after command expressions;
5. trimming whitespace-sensitive machine data;
6. variable interpolation immediately before `:`;
7. compound native expressions splitting into multiple argv elements;
8. verifier assumptions that do not match the producer's committed JSON schema.

Later incidents should be added here when they establish a reusable construction rule, rather than remaining only in chat history.

## 24. Final rule

The purpose of these constraints is not to make runners elaborate. It is to move complexity out of recovery.

Prefer the smallest runner that can prove:

```text
I know where I am.
I know what I am allowed to change.
I know what the producer actually returned.
I know whether the mutation happened.
I know what durable state exists now.
I preserved enough evidence to continue safely.
```

If a generated runner cannot answer those questions, it is not ready to mutate production or live-test state.
