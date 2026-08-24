# Stage 5B - Minimum Production ExecutionCrew

A human selects one eligible committed `NSC-###` task, one provider, explicit production implementation paths, and explicit Unity test paths. The crew runs fresh task-associated invocations through `TaskExecutionRunner -> AgentRunner -> provider`:

```text
Implementer -> deterministic incremental Git scope check
Unity Test Author -> deterministic incremental Git scope check
Validator -> optional one repair cycle -> human review
```

The selected task must be `active`, `implementation`, `single_agent`, and `concrete`. This is eligibility, not dependency readiness or authorization. All roles use one human-selected provider (`claude` or `codex`); mixed-provider orchestration is not implemented.

The Implementer has `repository_read`, `repository_search`, and `repository_write`, model class `standard`, and may modify only `--implementation-path` values. The fresh Unity Test Author has the same capabilities, model class `low_cost`, and may modify only `--test-path` values. Requested role paths must be distinct existing tracked files, with implementation and test sets disjoint under conservative case-insensitive path comparison. Its prompt includes the committed Unity testing policy and exact implementation diff. The fresh Validator is `high_reasoning` with only `repository_read` and `repository_search`; it reads the physically read-only committed source checkout as baseline context and semantically evaluates the candidate state represented by that baseline plus the exact candidate patch and actual changed paths. The baseline is intentionally unchanged, so absence of candidate edits there is not a defect and the Validator must not require them to be committed or applied before review. It must report exactly once on every task AC/VAL ID; `not_proven` records runtime or Unity evidence that was not executed and may coexist with a semantic pass. A pass is semantic review only, never a Unity, delivery, readiness, integration, or conformance claim. The source remains unchanged until a human approves and manually applies `candidate.patch`.

One independent clone outside `/workspace` accumulates both write roles and, if needed, one repair cycle. An immutable snapshot captured immediately after checkout is the baseline for final clone HEAD/index/untracked/path checks, including tracked additions, deletions, and byte changes; clone bytes are never compared to source working-tree bytes. Before and after each write invocation the crew records clone HEAD, exact index entries, untracked paths, and SHA-256 for every tracked working-tree file. Incremental byte changes must pass that role's `AgentInvocationRequest.is_path_writable`; claims never establish scope. Changed HEAD/index, untracked files, deletion/rename/copy effects, or out-of-bound byte changes reject the run. Source HEAD/tree/status is independently revalidated after every invocation and at finalization.

Windows bind-mounted source repositories can appear under different ownership inside Linux containers. For cloning only, the crew creates a run-scoped temporary `GIT_CONFIG_GLOBAL`, registers the exact resolved source root and its resolved `.git` directory as `safe.directory` values, and uses `git clone --no-local --no-checkout`. The protected config lives outside the source checkout and disappears with the disposable run workspace; the user's normal global Git config is not changed.

Validation permits at most two passes. `pass` emits review-only `candidate.patch`; `blocked_by_design` stops; first-pass `needs_changes` runs one repair cycle with exact findings; a non-pass second validation ends `needs_human` or rejected with no candidate patch. Role blockers stop safely. Other tracked changes may be retained only as `workspace_diagnostic.patch`.

A human rejection of a `review_ready` candidate starts a new run; it never resumes or mutates the prior run. `--retry-run` recovers the task ID, provider, and exact requested Implementer/Test Author WriteBoundaries from the prior immutable artifacts. New-format results carry `requested_implementation_paths` and `requested_test_paths`; legacy results recover the same authority from their persisted TaskExecution requests, never from actual changed paths. The normal clean-source preflight captures current committed `HEAD` and tree as the new baseline. The prior source commit must still be an ancestor, but the retry never checks it out or resets to it.

The required UTF-8 feedback file must be a non-empty regular file of at most 64 KiB underneath the configured output root. Its exact bytes are copied to the new run as `human_review_feedback.txt`, hashed with SHA-256, and supplied to Implementer, Test Author, and Validator. Telemetry records only the prior run ID and hash, not feedback text. Feedback is review evidence: it cannot override the task contract or GDD and cannot widen write authority. If a correction needs another path, the crew blocks; the human must start a new explicitly scoped normal run.

In `claude-exec` and `codex-exec`, the source is mounted only as `/workspace:ro`; host `Pipeline/ExecutionCrew/outputs` is mounted separately at `/execution-output:rw` and selected by `NSC_EXECUTION_OUTPUT_ROOT`. There is no writable nested mount beneath `/workspace`. Local deterministic development falls back to `Pipeline/ExecutionCrew/outputs` when that environment variable is absent.

ExecutionCrew prints flushed, human-readable progress to stderr while reserving stdout for the final machine-readable result JSON. Blocking role invocations emit a heartbeat every 15 seconds by default; deterministic tests may set the positive finite `NSC_EXECUTION_HEARTBEAT_SECONDS` override. Each run also writes and immediately flushes `progress.jsonl`. This file is supplemental operational telemetry only and has no authority over changed paths, validation, delivery, or readiness; it never contains prompts, raw provider output, credentials, or model reasoning.

```text
outputs/<run-id>/
  crew_result.json
  progress.jsonl                      # supplemental operational telemetry
  human_review_feedback.txt           # retry only; exact accepted feedback bytes
  candidate.patch                    # review_ready only
  workspace_diagnostic.patch         # diagnostic only, when applicable
  role_results/<role>_<attempt>.json
  task_execution/<invocation-id>/task_request.json
  agent_runtime/<invocation-id>/{request.json,provider.log,result.json}
```

There is no Planner, Unity execution, general GER, global selection/readiness/dispatch, automatic patch application, commit/merge, evidence publication, conformance record, provider fallback, mixed providers, or parallel task workers.

## Human-review workflow

Start the first run with an explicit task, provider, and role paths:

```bash
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-005 --provider claude --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs --test-path Assets/NoSafeCircle/DoorPrototype/Tests/PlayerManaPlayModeTests.cs
```

When it reaches `review_ready`, the human reviews `candidate.patch`. Approval continues through manual integration, required validation, and evidence workflow; ExecutionCrew does not apply or commit anything. On rejection, write the concrete review finding to a feedback file beneath the configured ExecutionCrew output root, then start a retry:

```bash
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --retry-run nsc-005-20260823t222010z --review-feedback-file /execution-output/feedback/nsc-005-mana-feedback.txt
```

The retry inherits `NSC-005`, `claude`, and both prior role scopes, but works from the current clean committed source `HEAD`—which may contain the manually integrated rejected candidate. If the repair cannot be made within inherited authority, do not widen the retry; start a suitably scoped explicit run after human review.

The equivalent initial command may select `--provider codex` and run in `codex-exec`. Defaults are `claude-sonnet-5` and `gpt-5.6-sol`; environment overrides remain available.
