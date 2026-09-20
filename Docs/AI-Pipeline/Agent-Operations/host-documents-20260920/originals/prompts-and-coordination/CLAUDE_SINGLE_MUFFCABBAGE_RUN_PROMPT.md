# Run one private muffcabbage task with Claude wherever the current pipeline permits

You are the Windows operator for one measured, provider-backed rehearsal task. Read and follow the repository's `AGENTS.md`, `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`, `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`, `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`, `Docs/AI-Pipeline/TASK_SELECTION_AND_CHECKOUT.md`, and `Docs/AI-Pipeline/GITHUB_TICKET_ORCHESTRATION_MVP.md` completely before doing anything.

## Goal

Run exactly `NSC-914` in the private `cathode26/NoSafeCircle-Homework-Rehearsal` repository through the canonical autonomous Game Task Agent lifecycle. Measure wall-clock time from launcher start through graph-complete, including the implementation commit and synthetic rehearsal validation/closeout. Use Claude for the software architect and ExecutionCrew. Preserve exact evidence for every provider invocation, token count, worker start/finish, test, commit, Issue transition, retry, and wait.

This is a synthetic private rehearsal task. Automated synthetic validation evidence is authorized, but you must never create or claim a human PASS. Do not touch production/public main or `C:\NSC\NSC\NSC-042`.

## Current provider limitation — do not hide it

The current canonical `Start-GameTaskAgent.ps1` worker path hard-requires `codex` to be present in `ProviderAllowlist` because its TaskReviewAgent supervisor is currently Codex-only. Therefore a literal Claude-only allowlist is expected to fail preflight.

Use:

- `ArchitectProvider = claude`
- `ExecutionProvider = claude`
- `ProviderAllowlist = claude,codex` only because the launcher requires the supervisor provider to be represented

The deterministic short-circuit should eliminate paid supervisor calls for host-forced actions on this simple task. Do not assume that it did. Inspect the durable provider/session/token evidence afterward. If an actual Codex/OpenAI provider call occurs, preserve all state and evidence, stop before retrying or starting another task, and report the exact phase, reason, invocation ID, input/output token counts, and whether the call was avoidable. Never silently fall back from Claude to Codex for the architect, Implementer, Test Author, Validator, or repair role.

## Hard preconditions

Use the canonical controller checkout:

`C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal`

Before any mutation or provider invocation:

1. Verify the configured GitHub remote is exactly the private repository `cathode26/NoSafeCircle-Homework-Rehearsal`.
2. Verify the checkout is on `main`, clean, attached, and has no staged/untracked changes.
3. Fetch `origin main` normally and fast-forward only. Do not merge, rebase, reset, clean, restore, stash, force, or overwrite anything.
4. Require local `HEAD == origin/main` after the fast-forward.
5. Require commit `71793c52edc13a4e20c3ef3a1abc8cb07b57f35e` to be an ancestor of the exact `origin/main`. If it is absent, STOP WITHOUT RUNNING THE TASK and report: `REHEARSAL_FIXES_NOT_PUBLISHED`.
6. Run `python Pipeline/TaskGraph/taskcontrol.py validate` and require PASS.
7. Inspect `NSC-914` with `taskcontrol.py show NSC-914`; require the expected synthetic muffcabbage task contract and a non-terminal authoritative state.
8. Inspect GitHub for any existing managed `NSC-914` Issue, task branch, claim, checkout, or reservation. Resume only if the Issue state machine proves an exact resumable run. Otherwise require fresh availability. Do not guess around stale or conflicting state.
9. Explicitly prove `NSC-042` is absent from the target set and add it to the autonomous exclusion set. Never inspect, modify, clean, reset, delete, or overwrite `C:\NSC\NSC\NSC-042`.
10. Verify GitHub CLI, Docker Compose, persisted `nosafecircle_claude-config`, and Unity availability through the canonical launcher preflight. Do not log in interactively or alter unrelated repositories.

If any precondition fails, stop with the exact observed state. Do not repair it by destructive cleanup.

## Canonical measured launch

Use `Start-AutonomousGraphRun.ps1` directly so the exact target and exclusion are explicit. Build the PowerShell argument arrays in-process; do not use `powershell.exe -File` for the string-array parameters.

Use a fresh run ID generated as:

`single-claude-nsc914-` plus the current UTC timestamp in `yyyyMMdd-HHmmss` form.

Use a fresh checkout root below:

`C:\NSC\Rehearsal\SingleClaudeMuffcabbage-<same timestamp>`

Launch with these exact semantic options:

- `TargetTaskId @('NSC-914')`
- `ExcludeTaskId @('NSC-042')`
- `MaxWorkers 1` (a capacity ceiling; the architect may admit zero or one)
- `ExecutionProvider claude`
- `ArchitectProvider claude`
- `ProviderAllowlist 'claude,codex'` only for the supervisor compatibility limitation explained above
- `EnableSyntheticEvidence`
- `ConfirmRepository 'cathode26/NoSafeCircle-Homework-Rehearsal'`
- `Source 'C:\NSC\Rehearsal\NoSafeCircle-Homework-Rehearsal'`
- the fresh checkout root and run ID

Save a readable, timestamped transcript under:

`C:\Users\VincentLiguori\Downloads\NoSafeCircleOutput\NSC-914\<timestamp>\execution.txt`

Use the repository's native-command handling rules. Determine success only from process exit code plus durable graph-complete/Issue/Git evidence, never from the presence or absence of stderr text. Show concise live progress while teeing the full diagnostic stream to the transcript.

## Monitoring and terminal proof

Monitor the exact launcher process and durable run artifacts continuously. Do not restart because observation times out. If interrupted, inspect the saved manifest/progress/Issue state and resume the exact run ID only when the repository proves that is safe.

Successful completion requires all of the following:

- graph-complete receipt for the exact run;
- exact `NSC-914` implementation commit and parent;
- exact changed paths limited to the authorized `.cs` and `.cs.meta` pair;
- targeted Unity EditMode validation for the exact commit;
- synthetic automated evidence that leaves `human_result` null;
- private Issue final state and URL;
- task branch and remote commit verification;
- no NSC-042 touch or admission;
- clean controller and task checkouts;
- no unresolved worker, lease, claim, reservation, or container;
- exact provider-call/token/session evidence.

## Final report

Report:

1. Start/end UTC and total elapsed wall time.
2. A per-phase timeline: preflight, architect, checkout, ExecutionCrew roles, Unity test, implementation commit/push, synthetic evidence, downstream integration/closeout, and graph-complete.
3. Every worker/provider role, actual provider, model, session reuse/new-session disposition, input/output/cache tokens, retries, and duration.
4. Issue number/URL, branch, implementation commit, final private-main commit if the canonical lifecycle merges it, and exact changed paths.
5. Architect rigor/profile decision and why.
6. All test commands/results and exact tested commit.
7. Peak worker count, idle/wait time, Git subprocess counts if recorded, and any anomalies.
8. Explicit confirmation that no human PASS was fabricated and NSC-042 was untouched.
9. Exact evidence of whether any Codex/OpenAI provider call actually occurred. If one occurred, classify why deterministic short-circuiting did not eliminate it.

Do not claim success if any required artifact is missing. Do not run another task.
