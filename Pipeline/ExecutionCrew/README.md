# Stage 5B - Minimum Production ExecutionCrew

A human selects one eligible committed `NSC-###` task, one provider, explicit production implementation paths, and explicit Unity test paths. The crew runs fresh task-associated invocations through `TaskExecutionRunner -> AgentRunner -> provider`:

```text
Implementer -> deterministic incremental Git scope check
Unity Test Author -> deterministic incremental Git scope check
Validator -> optional one repair cycle -> human review
```

The selected task must be `active`, `implementation`, `single_agent`, and `concrete`. This is eligibility, not dependency readiness or authorization. All roles use one human-selected provider (`claude` or `codex`); mixed-provider orchestration is not implemented.

The Implementer has `repository_read`, `repository_search`, and `repository_write`, model class `standard`, and may modify only `--implementation-path` values. The fresh Unity Test Author has the same capabilities, model class `low_cost`, and may modify only `--test-path` values. Requested role paths must be distinct existing tracked files, with implementation and test sets disjoint under conservative case-insensitive path comparison. Its prompt includes the committed Unity testing policy and exact implementation diff. The fresh Validator is `high_reasoning` with only `repository_read` and `repository_search`; it runs against the physically read-only source checkout and receives the exact candidate patch, actual changed paths, and write-role outputs. It must report exactly once on every task AC/VAL ID; `not_proven` records runtime or Unity evidence that was not executed and may coexist with a semantic pass. A pass is semantic review only, never a Unity, delivery, readiness, integration, or conformance claim.

One independent clone outside `/workspace` accumulates both write roles and, if needed, one repair cycle. An immutable snapshot captured immediately after checkout is the baseline for final clone HEAD/index/untracked/path checks, including tracked additions, deletions, and byte changes; clone bytes are never compared to source working-tree bytes. Before and after each write invocation the crew records clone HEAD, exact index entries, untracked paths, and SHA-256 for every tracked working-tree file. Incremental byte changes must pass that role's `AgentInvocationRequest.is_path_writable`; claims never establish scope. Changed HEAD/index, untracked files, deletion/rename/copy effects, or out-of-bound byte changes reject the run. Source HEAD/tree/status is independently revalidated after every invocation and at finalization.

Windows bind-mounted source repositories can appear under different ownership inside Linux containers. For cloning only, the crew creates a run-scoped temporary `GIT_CONFIG_GLOBAL`, registers the exact resolved source root and its resolved `.git` directory as `safe.directory` values, and uses `git clone --no-local --no-checkout`. The protected config lives outside the source checkout and disappears with the disposable run workspace; the user's normal global Git config is not changed.

Validation permits at most two passes. `pass` emits review-only `candidate.patch`; `blocked_by_design` stops; first-pass `needs_changes` runs one repair cycle with exact findings; a non-pass second validation ends `needs_human` or rejected with no candidate patch. Role blockers stop safely. Other tracked changes may be retained only as `workspace_diagnostic.patch`.

In `claude-exec` and `codex-exec`, the source is mounted only as `/workspace:ro`; host `Pipeline/ExecutionCrew/outputs` is mounted separately at `/execution-output:rw` and selected by `NSC_EXECUTION_OUTPUT_ROOT`. There is no writable nested mount beneath `/workspace`. Local deterministic development falls back to `Pipeline/ExecutionCrew/outputs` when that environment variable is absent.

```text
outputs/<run-id>/
  crew_result.json
  candidate.patch                    # review_ready only
  workspace_diagnostic.patch         # diagnostic only, when applicable
  role_results/<role>_<attempt>.json
  task_execution/<invocation-id>/task_request.json
  agent_runtime/<invocation-id>/{request.json,provider.log,result.json}
```

There is no Planner, Unity execution, general GER, global selection/readiness/dispatch, automatic patch application, commit/merge, evidence publication, conformance record, provider fallback, mixed providers, or parallel task workers.

## NSC-005 proving commands (documented only)

Claude:

```bash
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-005 --provider claude --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs --test-path Assets/NoSafeCircle/DoorPrototype/Tests/PlayerManaPlayModeTests.cs
```

Codex:

```bash
docker compose run --rm -T codex-exec python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-005 --provider codex --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs --test-path Assets/NoSafeCircle/DoorPrototype/Tests/PlayerManaPlayModeTests.cs
```

Defaults are `claude-sonnet-5` and `gpt-5.6-sol`; environment overrides remain available. Do not run either proving command until this implementation is reviewed and committed.
