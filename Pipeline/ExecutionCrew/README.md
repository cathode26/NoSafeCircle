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

During a human-review retry, the Implementer and Test Author keep their normal disjoint scopes. Human feedback commonly mixes a production correction with a regression-test requirement; regression tests, test coverage, and other Test Author-owned work mentioned in that feedback are explicitly **not** Implementer blockers. The Implementer must not modify test files; if the production correction can be completed within its approved implementation `WriteBoundaries`, it must make that correction and continue, optionally noting required regression coverage for the Test Author. The Implementer should report a blocker only when the production correction itself cannot be completed within its approved implementation paths or is blocked by task/canon/design. The Test Author continues to receive the exact human feedback and explicitly owns any regression/test requirement in it, adding coverage where possible within its approved test paths and reporting a blocker only if the required test correction actually cannot be made there. The Validator continues to receive the same feedback and evaluates the candidate as a whole — both the production correction and appropriate regression coverage — and must not pass while the human rejection remains unresolved. Human feedback still never expands the TaskContract, GDD, or either role's write authority, and the existing single Validator-driven repair cycle is unchanged.

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

## Human-facing result

`crew_result.json` remains the authoritative machine-readable record; every existing field, including `candidate_patch_path` and `workspace_diagnostic_patch_path` (both container paths, valid for machine/container use), is unchanged. It additionally carries a stable, additive `human_result` object so a human never has to inspect `role_results`, output directories, or `rejection_reasons` by hand to answer "what happened, why, what file do I open, what do I do next":

```json
"human_result": {
  "status": "REVIEW_READY | BLOCKED | REJECTED | NEEDS_HUMAN",
  "reason": "...",
  "artifact_path": "...",
  "next_action": "...",
  "commands": {
    "find": "Get-Item -LiteralPath '...'",
    "check": "git apply --check '...'",
    "apply": "git apply '...'",
    "verify": "git status --short; git diff --check"
  }
}
```

`status` mirrors `crew_status`. `reason` clearly states the candidate passed semantic crew review and awaits human review when `review_ready`; otherwise it is the first entry of `rejection_reasons` when that entry is a deterministic orchestration-generated reason, or a fixed structural summary (for example "The Implementer reported a blocker.") when that entry would otherwise embed raw agent-authored blocker text, which during a human-review retry could quote the human feedback itself; the full, authoritative reason always remains available in `rejection_reasons` and the role artifacts. `reason` is `null`, never fabricated, when no rejection/blocking reason was recorded. `artifact_path` points at `candidate.patch` when `review_ready`, otherwise at `workspace_diagnostic.patch` when one exists, otherwise `null`; when a HOST output root is supplied (see below) it prefers the full host-drive-qualified path. `next_action` never implies automatic apply/commit/merge behavior.

`commands` is a stable, additive structure so tooling can consume the exact same copy/paste-ready PowerShell instructions as the stderr footer below, quoted with `pathlib`-free single-quote escaping (embedded `'` becomes `''`) so the result is safe to paste directly into PowerShell even when the path contains spaces. When `status` is `REVIEW_READY`, all four commands operate on the exact `candidate.patch` path (host path when available, otherwise the container path). For any diagnostic artifact (`workspace_diagnostic.patch`), only `find` is populated; `check` and `apply` are always `null`, because a diagnostic patch is never an approved candidate. When there is no artifact at all, every command is `null`.

ExecutionCrew also prints a concise human-readable summary to stderr when it finishes, while stdout remains the single machine-readable result JSON only. For a review-ready candidate, the footer ends with copy/paste-ready commands built from the exact artifact path — never a placeholder like `<RUN-ID>`:

```text
RESULT: REVIEW_READY
ARTIFACT: C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch

FIND PATCH:
Get-Item -LiteralPath 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

CHECK PATCH:
git apply --check 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

APPLY PATCH:
git apply 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

VERIFY:
git status --short
git diff --check

NEXT: Review candidate.patch; apply manually only if approved.
```

A human can copy each command directly from that footer (or from `human_result.commands`) without reconstructing the path by hand. None of these commands run automatically; ExecutionCrew never applies, commits, merges, or pushes anything itself.

For a blocked or rejected run with a diagnostic artifact, the footer identifies `workspace_diagnostic.patch` for inspection but deliberately never prints a `git apply` or `git apply --check` command for it, because diagnostic output from a non-`review_ready` run is not an approved candidate:

```text
RESULT: BLOCKED
WHY: The Implementer reported a blocker.
ARTIFACT: C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\workspace_diagnostic.patch

FIND DIAGNOSTIC PATCH:
Get-Item -LiteralPath 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\workspace_diagnostic.patch'

DO NOT APPLY:
This is diagnostic work from a non-review-ready run, not an approved candidate.

NEXT: Inspect the diagnostic patch and blocking reason; no candidate was approved.
```

**`workspace_diagnostic.patch` must not be applied.** It is retained tracked-file movement from a run that did not reach `review_ready`, never an approved candidate; the footer and `human_result.commands` intentionally omit any apply/check command for it.

When there is no artifact at all (no candidate and no diagnostic patch), the footer keeps the existing `RESULT`/`WHY`/`ARTIFACT`/`NEXT` lines with `ARTIFACT: none` and prints no `FIND`/`CHECK`/`APPLY` block.

This summary never includes prompts, raw provider output, credentials, hidden reasoning, or feedback text.

## Host artifact paths

Inside Docker, `candidate_patch_path` and `workspace_diagnostic_patch_path` are container paths (for example `/execution-output/<run-id>/candidate.patch`), which is poor UX when the human is on a Windows host. Passing `--host-output-root <WINDOWS_ABSOLUTE_PATH>` (or the `NSC_EXECUTION_HOST_OUTPUT_ROOT` environment variable as a fallback; the CLI flag takes precedence when both are set) adds `candidate_patch_host_path` and `workspace_diagnostic_patch_host_path` with the equivalent full drive-qualified host path, for example:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch
```

This is a purely lexical, HOST-facing display path (`pathlib.PureWindowsPath`); it is never resolved as a filesystem path inside the Linux container. An empty, relative, traversal-containing, or malformed drive-relative value is rejected before the run starts. `human_result.artifact_path` prefers the host path when one is available, and the stderr footer and `human_result.commands` are built from that exact same path. Omitting `--host-output-root` preserves full backward compatibility: the host-path fields are `null`, `human_result.artifact_path` falls back to the existing container path, and the footer/`commands` use that container path instead of inventing a Windows path.

There is no Planner, Unity execution, general GER, global selection/readiness/dispatch, automatic patch application, commit/merge, evidence publication, conformance record, provider fallback, mixed providers, or parallel task workers.

## Human-review workflow

Start the first run with an explicit task, provider, and role paths:

```bash
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-005 --provider claude --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerMana.cs --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/PlayerManaUI.cs --test-path Assets/NoSafeCircle/DoorPrototype/Tests/PlayerManaPlayModeTests.cs
```

When it reaches `review_ready`, the human reviews `candidate.patch`. Approval continues through manual integration, required validation, and evidence workflow; ExecutionCrew does not apply or commit anything. On rejection, write the concrete review finding to a feedback file beneath the configured ExecutionCrew output root, then start a retry. Supply `--host-output-root` with the host (for example Windows) path that the mounted output root corresponds to, so `crew_result.json` and the final terminal summary show a full, drive-qualified path the human can open directly:

```bash
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --retry-run nsc-005-20260823t222010z --review-feedback-file /execution-output/feedback/nsc-005-mana-feedback.txt --host-output-root "C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs"
```

The retry inherits `NSC-005`, `claude`, and both prior role scopes, but works from the current clean committed source `HEAD`—which may contain the manually integrated rejected candidate. If the repair cannot be made within inherited authority, do not widen the retry; start a suitably scoped explicit run after human review.

The equivalent initial command may select `--provider codex` and run in `codex-exec`. Defaults are `claude-sonnet-5` and `gpt-5.6-sol`; environment overrides remain available.
