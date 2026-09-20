# Claude task: provider-neutral TaskReviewAgent supervisor

Work only in the prepared Windows checkout:

`C:\NSC\ClaudeProviderNeutralSupervisor-20260905\NoSafeCircle`

Required branch: `claude/provider-neutral-task-review-supervisor`

Required starting HEAD: `2bc1a29636f33edcaa78775c2cfcfff189156447`

Before editing, read and follow `AGENTS.md`, `Docs/Engineering/UNITY_TESTING_POLICY.md`, `Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md`, `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`, `Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md`, `Pipeline/TaskReviewAgent/README.md`, `Pipeline/AgentRuntime/README.md`, and the supervisor/session-pool documentation and tests reached from those files. Verify the exact branch, HEAD, and clean tree. Stop if any precondition differs.

Do not clone, fetch, pull, push, access GitHub, switch branches, merge, rebase, reset, clean, restore, or stash. Do not run live Claude/Codex provider calls, Docker, Unity, or any rehearsal task. Do not touch `C:\NSC\Rehearsal`, production/public main, any Issue/claim/checkout/container, Unity content, or NSC-042. Use deterministic fake-provider tests only. Commit locally with `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>` and do not push.

## Root defect

The canonical Game Task Agent accepts Claude for the software architect and ExecutionCrew, but the TaskReviewAgent supervisor is structurally pinned to Codex. In `Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1`, any supplied `ProviderAllowlist` must contain `codex`:

```text
if ($AllowedProviders -notcontains 'codex') {
    throw 'The supervisor provider codex must be in ProviderAllowlist.'
}
```

That makes a true Claude-only autonomous task impossible. Even a run configured with `ArchitectProvider=claude` and `ExecutionProvider=claude` must authorize Codex, and any supervisor turn may consume the operator's OpenAI quota.

## Required end state

Make the TaskReviewAgent supervisor provider-neutral without weakening any deterministic host authority or provider boundary.

Add an explicit supervisor-provider selection, using repository naming conventions—prefer `SupervisorProvider` in PowerShell and `supervisor_provider`/`--supervisor-provider` in Python unless an existing generic abstraction provides a better name.

Supported values must be exactly `claude` and `codex`.

The selected supervisor provider must be:

1. validated against `ProviderAllowlist` before provider/Docker construction;
2. persisted in every immutable run/graph/session manifest needed for safe resume;
3. propagated from `Start-GameTaskAgent.ps1` through `Start-AutonomousGraphRun.ps1`, `run_autonomous_graph.py`, scheduler configuration, worker command construction, `run_pipeline_agent.py`, and the actual supervisor-provider factory;
4. bound to supervisor session compatibility/reuse identity so a session can never cross providers, models, repositories, tasks, or incompatible capability/authority settings;
5. present in durable events, receipts, diagnostics, progress output, and token/provider-call evidence;
6. honored on new work, resume, retry, human-action wake-up, worker reuse, and graph-controller reconstruction;
7. used for provider authentication-volume preflight so a Claude-only run does not inspect or require the Codex volume;
8. fail-closed if a persisted run requests a provider that is unavailable, outside the allowlist, mismatched to its prior session, or inconsistent with the current request.

The default for callers and old persisted artifacts that do not select a supervisor must remain the existing Codex behavior, but compatibility must be explicit and tested—do not silently rewrite a persisted Claude supervisor to Codex or vice versa.

When all three selectors are Claude:

- `SupervisorProvider=claude`
- `ArchitectProvider=claude`
- `ExecutionProvider=claude`
- `ProviderAllowlist=claude`

the canonical top-level and scheduler-worker launchers must accept the run, preflight only Claude authentication, construct no Codex provider/command/session, and ensure every paid model role is Claude. Deterministic host short-circuits remain provider-free and must continue to bypass both providers.

When the supervisor is Codex, existing behavior and command lines must remain compatible unless the new explicit field is emitted for durable identity. Existing Codex resume sandbox enforcement must remain intact and must apply only when the actual selected supervisor is Codex. Do not make Claude accept Codex-specific sandbox arguments. If Claude resume requires a distinct verified argument or capability, model it explicitly and fail closed rather than pretending pooling works.

Do not conflate these independent choices:

- software architect provider;
- TaskReviewAgent supervisor provider;
- ExecutionCrew default/provider route;
- per-role cross-provider validation or repair routes.

The architect may eventually choose some of these, but this task must first provide a deterministic, explicit, immutable operator/runtime selection that makes a Claude-only run possible.

## Provider adapter and prompt contract

Reuse `Pipeline/AgentRuntime` provider-neutral request/result/session contracts and the existing `ClaudeCodeProvider`; do not create a second Claude CLI adapter. Reuse the existing supervisor prompt/schema/action validation. Provider output remains advisory; deterministic host code owns checkout, Git, Issue, test, commit, readiness, and closeout authority.

If current supervisor code is named `openai_*`, prefer a narrow compatibility-preserving injection/factory seam over a sweeping rename. Existing imports and persisted artifacts must continue to work.

## Mandatory red-before / green-after tests

Add deterministic tests that demonstrably fail on the starting commit and pass after the fix. Every behavior-changing test must execute the real parameter/propagation/factory boundary rather than merely search source text.

At minimum prove:

1. A top-level explicit task accepts `SupervisorProvider=claude`, `ArchitectProvider=claude`, `ExecutionProvider=claude`, `ProviderAllowlist=claude` and forwards the exact values.
2. The autonomous graph launcher/manifest persists the Claude supervisor and rejects a changed supervisor on resume/reconstruction.
3. Scheduler-created worker commands carry the exact selected supervisor provider.
4. A Claude-only preflight inspects only `nosafecircle_claude-config`, never the Codex volume.
5. The actual supervisor factory constructs the existing Claude adapter and no Codex adapter/command for the Claude route.
6. A Claude supervisor outside the allowlist stops before any provider, worker, GitHub, or mutation call.
7. A Codex supervisor outside the allowlist behaves equivalently.
8. Architect, supervisor, and execution-provider selectors remain independent and cannot overwrite one another.
9. Durable provider evidence and token usage record the actual Claude supervisor identity.
10. Supervisor session pooling/reuse accepts compatible Claude sessions and rejects cross-provider/model/repository/task/authority reuse.
11. Claude transport failure, quota exhaustion, malformed output, missing result, and uncertain timeout remain typed failures and cannot fall back to Codex when the allowlist is Claude-only.
12. Existing default callers continue to select Codex and existing deterministic short-circuit tests still prove zero provider calls for host-forced actions.
13. `ProviderAllowlist=claude` never produces a command, environment variable, volume lookup, provider object, session receipt, or diagnostic that names Codex as an executable provider.
14. A mixed allowlist permits an explicitly selected provider but never changes providers during resume/retry without a separately persisted authorized handoff.

Include PowerShell launcher tests for exact argument forwarding and omitted/default compatibility. Preserve Windows PowerShell 5.1 support and the existing string-array forwarding protections.

For every new test, record concise red-before evidence by running it against the exact starting semantics or by loading exact base modules/scripts into the harness. A test that also passes before the fix is not evidence.

## Required validation

After focused tests pass, run every directly affected deterministic suite, including at least:

- architect-managed launcher;
- autonomous graph launcher/CLI/run;
- host worker launcher and execution routing;
- TaskReviewAgent supervisor/pipeline/action grounding/determinism;
- Claude and Codex provider adapter contracts;
- provider and supervisor session pooling;
- execution session pooling;
- provider policy and quota/failover tests;
- polling orchestrator and scheduler factory tests;
- task-review-agent smoke tests;
- compose/provider-volume tests;
- operator command policy and PowerShell parser preflight;
- Git identity guard;
- `python Pipeline/TaskGraph/taskcontrol.py validate`;
- `py_compile` for changed Python;
- `git diff --check`.

Do not weaken an assertion or expand an allowlist merely to make tests pass. Do not claim a live provider run; none is authorized for this implementation task.

## Commit and report

Stage only exact changed paths and verify them before committing. Produce one focused local commit if practical; otherwise use a small reviewable series and state why.

Report:

- checkout, branch, starting and ending HEADs;
- exact changed paths;
- end-to-end propagation path for supervisor identity;
- compatibility behavior for existing Codex callers/artifacts;
- Claude-only authentication, command, provider, and session proof;
- every red-before and green-after result;
- broad deterministic test results;
- any remaining Codex-only assumption or untested live-provider boundary;
- uncertainties and clean-tree status.

Do not push or start a muffcabbage task. The final live run will be a separate explicitly reviewed step after this commit is independently integrated and validated.
