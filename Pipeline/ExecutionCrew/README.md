# Stage 5B - Minimum Production ExecutionCrew

A human selects one eligible committed `NSC-###` task, one provider, explicit production implementation paths, and explicit Unity test paths. The crew runs fresh task-associated invocations through `TaskExecutionRunner -> AgentRunner -> provider`:

```text
Contract Locality Auditor -> deterministic locality-audit consistency check
Implementer -> deterministic incremental Git scope check
Unity Test Author -> deterministic incremental Git scope check
Validator -> optional one repair cycle -> human review
```

The selected task must be `active`, `implementation`, `single_agent`, and `concrete`. This is eligibility, not dependency readiness or authorization. All roles use one human-selected provider (`claude` or `codex`); mixed-provider orchestration is not implemented.

## Contract Locality Auditor (mandatory, before the Implementer)

Every normal run and human-review retry runs one mandatory, read-only, `high_reasoning` Contract Locality Auditor immediately after source/task/graph preflight and before the Implementer. It has only `repository_read` and `repository_search`, empty `WriteBoundaries`, and reads the physically read-only committed source directly (no disposable clone exists yet at this point). It never edits the task contract, GDD, graph, source, or tests, and it never commits, stages, or otherwise touches Git. Its context includes the exact selected task contract, the full canonical GDD, source `HEAD`/tree, direct dependency contracts, direct dependent contracts, a deterministic id-sorted catalog of every committed task, and the task's execution/decomposition metadata.

It classifies every current acceptance-criterion (`AC-###`) and completion-gate (`VAL-###`) ID on the selected task exactly once:

| Classification | Meaning | Required action |
| --- | --- | --- |
| `local_to_task` | Provable using this task's own owned behavior/state/interfaces, or a dependency already declared on this task | `keep` |
| `requires_declared_dependency` | Needs another existing task's already-integrated behavior that is not (or not correctly) declared as a dependency | `add_dependency` |
| `downstream_integration` | This task can be completed and proven locally, but the item actually verifies a future consumer/orchestrator using it correctly | `move_to_downstream_integration` |
| `missing_design` | The committed GDD/task contract lacks the approved design authority needed to implement or prove the item | `clarify_design` |
| `ambiguous` | Committed evidence is insufficient to classify the item safely | `human_review` |

This audit judges locality only, never dependency-completion or dispatch readiness: it does not ask whether a declared dependency has actually been delivered, only whether the declared dependency set is the correct one. A completion gate awaiting Unity/runtime execution is still `local_to_task`; missing runtime execution is a Validator `runtime_not_executed` concern, not a locality defect.

The crew deterministically re-checks the auditor's structured output before trusting it: exactly one result per current AC/VAL ID with no unknown or duplicate IDs, correct `entry_type`, exact classification/`recommended_action` pairing, every `related_task_ids` value naming a real committed task, `status=pass` only when every entry is `local_to_task` with zero `blocking_findings`, `status=contract_review_required` only when at least one entry is nonlocal, and every nonlocal entry paired with exactly one matching `blocking_findings` entry (never a `blocking_findings` entry on a `local_to_task` entry). An internally inconsistent auditor output stops the run as `rejected` before the Implementer; it is never silently treated as a pass.

When the audit is nonlocal, the crew publishes `contract_locality_audit.json` (schema `1.0`), binding the run ID, task ID, provider, source `HEAD`/tree, exact task-contract identity, and the validated audit result, and stops with `crew_status=contract_review_required` before the Implementer: `attempts_used` is `0`, the Implementer/Test Author/Validator are never invoked, no `candidate.patch` or `workspace_diagnostic.patch` is produced, and the source is untouched. `crew_result.json` also carries `contract_locality_status`, `contract_locality_audit_path`, and `contract_locality_audit_host_path` for every run (including a passing audit). This never grants readiness or dispatch authority and never edits the task contract, GDD, or graph automatically; TaskGraph and human review remain authoritative for repairing the contract. See the `CONTRACT_REVIEW_REQUIRED` footer below.

A Validator that later reports `blocked_by_design` with a `criteria_results` `reason_code` of `missing_integration_dependency` or `design_ambiguity` is treated as the same locality-defect class caught after writers already ran (the audit passed, but the defect only became apparent once the candidate was built). That fallback also routes the crew to `contract_review_required`, but by then a `workspace_diagnostic.patch` may already exist from retained tracked-file movement; it is diagnostic only, never an approved candidate, and never applyable.

The Implementer has `repository_read`, `repository_search`, and `repository_write`, model class `standard`, and may modify only `--implementation-path` values. The fresh Unity Test Author has the same capabilities, model class `low_cost`, and may modify only `--test-path` values. Requested role paths must be distinct existing tracked files, with implementation and test sets disjoint under conservative case-insensitive path comparison. Its prompt includes the committed Unity testing policy and exact implementation diff. The fresh Validator is `high_reasoning` with only `repository_read` and `repository_search`; it reads the physically read-only committed source checkout as baseline context and semantically evaluates the candidate state represented by that baseline plus the exact candidate patch and actual changed paths. The baseline is intentionally unchanged, so absence of candidate edits there is not a defect and the Validator must not require them to be committed or applied before review. A pass is semantic review only, never a Unity, delivery, readiness, integration, or conformance claim. The source remains unchanged until a human approves and manually applies `candidate.patch`.

The Validator must report exactly once on every task AC/VAL ID, and every `criteria_results` item requires a structured `reason_code` alongside its `status`, with deterministic status/`reason_code` agreement enforced by the crew: `status=pass` requires `reason_code=proved`; `status=fail` requires `reason_code=criterion_failed`; `status=not_proven` requires exactly one of `runtime_not_executed`, `missing_integration_dependency`, `missing_required_artifact`, `insufficient_evidence`, `design_ambiguity`. An overall Validator `pass` may carry a `not_proven` item only when its `reason_code` is `runtime_not_executed` (runtime/Unity evidence that genuinely was not executed yet, coexisting with an otherwise-proved semantic pass); any other `not_proven` reason_code on an overall `pass` is deterministically invalid and rejects the run. `missing_integration_dependency` and `design_ambiguity` must never coexist with `pass` and require overall `status=blocked_by_design`; the crew further routes that case to `contract_review_required` rather than a generic `blocked`, because it identifies the same kind of locality defect the mandatory audit exists to catch. `missing_required_artifact` and `insufficient_evidence` also cannot coexist with `pass`, and a `criterion_failed` result cannot coexist with `pass`.

One independent clone outside `/workspace` accumulates both write roles and, if needed, one repair cycle. An immutable snapshot captured immediately after checkout is the baseline for final clone HEAD/index/untracked/path checks, including tracked additions, deletions, and byte changes; clone bytes are never compared to source working-tree bytes. Before and after each write invocation the crew records clone HEAD, exact index entries, untracked paths, and SHA-256 for every tracked working-tree file. Incremental byte changes must pass that role's `AgentInvocationRequest.is_path_writable`; claims never establish scope. Changed HEAD/index, untracked files, deletion/rename/copy effects, or out-of-bound byte changes reject the run. Source HEAD/tree/status is independently revalidated after every invocation and at finalization.

Windows bind-mounted source repositories can appear under different ownership inside Linux containers. For cloning only, the crew creates a run-scoped temporary `GIT_CONFIG_GLOBAL`, registers the exact resolved source root and its resolved `.git` directory as `safe.directory` values, and uses `git clone --no-local --no-checkout`. The protected config lives outside the source checkout and disappears with the disposable run workspace; the user's normal global Git config is not changed.

Validation permits at most two passes. `pass` emits review-only `candidate.patch`; `blocked_by_design` stops; first-pass `needs_changes` runs one repair cycle with exact findings; a non-pass second validation ends `needs_human` or rejected with no candidate patch. Role blockers stop safely. Other tracked changes may be retained only as `workspace_diagnostic.patch`.

A human rejection of a `review_ready` candidate starts a new run; it never resumes or mutates the prior run. `--retry-run` recovers the task ID, provider, exact task-contract identity, exact requested Implementer/Test Author WriteBoundaries, and the prior `candidate.patch` from the prior immutable artifacts. New-format results carry `requested_implementation_paths`, `requested_test_paths`, and `candidate_patch_sha256`; legacy results recover authority from persisted TaskExecution requests and may omit the candidate hash, but the candidate artifact itself is still required. A changed task-contract identity is not a review retry: it fails closed and requires a new normal ExecutionCrew run.

The normal clean-source preflight captures current committed `HEAD` and tree as the new final-patch baseline, and the prior source commit must still be an ancestor. After the mandatory current Contract Locality Auditor passes, ExecutionCrew creates its disposable clone and verifies candidate lineage on the inherited implementation/test paths. If those paths are unchanged from the prior source, the rejected candidate is seeded into the disposable clone before either writer runs (`retry_seed_mode=applied`). If the current committed source already contains the exact rejected candidate post-image, that is proven in the disposable clone and the current state is retained (`retry_seed_mode=already_present`). If candidate-owned paths have otherwise diverged—even when Git could mechanically apply non-overlapping hunks—the retry fails closed rather than silently layering stale reviewed work. The real source checkout is never modified; historical already-present verification may temporarily reconstruct/reset only the disposable clone to the prior source commit and restores it exactly before writer execution.

The required UTF-8 feedback file must be a non-empty regular file of at most 64 KiB underneath the configured output root. Its exact bytes are copied to the new run as `human_review_feedback.txt`, hashed with SHA-256, and supplied to Implementer, Test Author, and Validator. Telemetry records only the prior run ID and hashes, not feedback text. Feedback is review evidence: it cannot override the task contract or GDD and cannot widen write authority. During a seeded retry, either writer may legitimately make no incremental change when the human correction belongs only to the other role; the retry still requires at least one net deterministic writer correction before the Validator, and the final accepted state must remain different from the seeded candidate after any repair cycle. If neither writer changes the seeded candidate, the run stops as `needs_human`; if a later repair cycle erases the correction and returns to the seed, finalization rejects the run. If a correction needs another path, the crew blocks; the human must start a new explicitly scoped normal run.

During a human-review retry, the Implementer and Test Author keep their normal disjoint scopes. Human feedback commonly mixes a production correction with a regression-test requirement; regression tests, test coverage, and other Test Author-owned work mentioned in that feedback are explicitly **not** Implementer blockers. The Implementer must not modify test files; if the production correction can be completed within its approved implementation `WriteBoundaries`, it must make that correction and continue, optionally noting required regression coverage for the Test Author. The Implementer should report a blocker only when the production correction itself cannot be completed within its approved implementation paths or is blocked by task/canon/design. The Test Author continues to receive the exact human feedback and explicitly owns any regression/test requirement in it, adding coverage where possible within its approved test paths and reporting a blocker only if the required test correction actually cannot be made there. The Validator continues to receive the same feedback and evaluates the candidate as a whole — both the production correction and appropriate regression coverage — and must not pass while the human rejection remains unresolved. Human feedback still never expands the TaskContract, GDD, or either role's write authority, and the existing single Validator-driven repair cycle is unchanged.

In `claude-exec` and `codex-exec`, the source is mounted only as `/workspace:ro`; host `Pipeline/ExecutionCrew/outputs` is mounted separately at `/execution-output:rw` and selected by `NSC_EXECUTION_OUTPUT_ROOT`. There is no writable nested mount beneath `/workspace`. Local deterministic development falls back to `Pipeline/ExecutionCrew/outputs` when that environment variable is absent.

ExecutionCrew prints flushed, human-readable progress to stderr while reserving stdout for the final machine-readable result JSON. Blocking role invocations emit a heartbeat every 15 seconds by default; deterministic tests may set the positive finite `NSC_EXECUTION_HEARTBEAT_SECONDS` override. Each run also writes and immediately flushes `progress.jsonl`. This file is supplemental operational telemetry only and has no authority over changed paths, validation, delivery, or readiness; it never contains prompts, raw provider output, credentials, or model reasoning.

```text
outputs/<run-id>/
  crew_result.json
  progress.jsonl                      # supplemental operational telemetry
  human_review_feedback.txt           # retry only; exact accepted feedback bytes
  contract_locality_audit.json        # every run whose audit reaches a valid pass/contract_review_required result
  candidate.patch                    # review_ready only
  workspace_diagnostic.patch         # diagnostic only, when applicable
  role_results/<role>_<attempt>.json  # includes contract_locality_auditor_1.json
  task_execution/<invocation-id>/task_request.json
  agent_runtime/<invocation-id>/{request.json,provider.log,result.json}
```

## Human-facing result

`crew_result.json` remains the authoritative machine-readable record; every existing field, including `candidate_patch_path` and `workspace_diagnostic_patch_path` (both container paths, valid for machine/container use), is unchanged. It additionally carries a stable, additive `human_result` object so a human never has to inspect `role_results`, output directories, or `rejection_reasons` by hand to answer "what happened, why, what file do I open, what do I do next":

```json
"human_result": {
  "status": "REVIEW_READY | BLOCKED | REJECTED | NEEDS_HUMAN | CONTRACT_REVIEW_REQUIRED",
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

`status` mirrors `crew_status`. `reason` clearly states the candidate passed semantic crew review and awaits human review when `review_ready`; otherwise it is the first entry of `rejection_reasons` when that entry is a deterministic orchestration-generated reason, or a fixed structural summary (for example "The Implementer reported a blocker.") when that entry would otherwise embed raw agent-authored blocker text, which during a human-review retry could quote the human feedback itself; the full, authoritative reason always remains available in `rejection_reasons` and the role artifacts. `reason` is `null`, never fabricated, when no rejection/blocking reason was recorded. `artifact_path` points at `candidate.patch` when `review_ready`, at `contract_locality_audit.json` when the mandatory pre-Implementer audit itself caught the defect, otherwise at `workspace_diagnostic.patch` when one exists (including the Validator fallback path described above), otherwise `null`; when a HOST output root is supplied (see below) it prefers the full host-drive-qualified path. `next_action` never implies automatic apply/commit/merge behavior.

`commands` is a stable, additive structure so tooling can consume the exact same copy/paste-ready PowerShell instructions as the stderr footer below, quoted with `pathlib`-free single-quote escaping (embedded `'` becomes `''`) so the result is safe to paste directly into PowerShell even when the path contains spaces. When `status` is `REVIEW_READY`, all four commands operate on the exact `candidate.patch` path (host path when available, otherwise the container path). When `status` is `CONTRACT_REVIEW_REQUIRED` and the mandatory audit itself is the artifact, `commands` instead has only `find`/`inspect` (never `check`/`apply`, since a read-only audit is never a patch). For any diagnostic artifact (`workspace_diagnostic.patch`), only `find` is populated; `check` and `apply` are always `null`, because a diagnostic patch is never an approved candidate. When there is no artifact at all, every command is `null`.

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

When the mandatory pre-Implementer Contract Locality Auditor itself stops the run, the footer identifies `contract_locality_audit.json` with find/inspect-only commands — there is no patch of any kind in this result, so the footer never prints patch or diagnostic-patch wording:

```text
RESULT: CONTRACT_REVIEW_REQUIRED
WHY: The committed task contract contains one or more AC/VAL items that are not locally implementable/provable under its current scope or dependencies.
ARTIFACT: C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json

FIND AUDIT:
Get-Item -LiteralPath 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json'

INSPECT AUDIT:
Get-Content -LiteralPath 'C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json'

NEXT: Review the audit, repair the task contract through normal human-reviewed TaskGraph workflow, validate the graph, and rerun ExecutionCrew.
```

If instead the Validator caught the same defect class after writers already ran (the mandatory audit passed, but the Validator later reported `blocked_by_design` with `reason_code=missing_integration_dependency` or `design_ambiguity`), `CONTRACT_REVIEW_REQUIRED` uses the diagnostic-patch footer shape instead (`FIND DIAGNOSTIC PATCH:` / `DO NOT APPLY:`), since a `workspace_diagnostic.patch` may exist in that case; it remains non-applyable exactly like any other diagnostic patch.

When there is no artifact at all (no candidate, audit, or diagnostic patch), the footer keeps the existing `RESULT`/`WHY`/`ARTIFACT`/`NEXT` lines with `ARTIFACT: none` and prints no `FIND`/`CHECK`/`APPLY` block.

This summary never includes prompts, raw provider output, credentials, hidden reasoning, or feedback text.

## Host artifact paths

Inside Docker, `candidate_patch_path` and `workspace_diagnostic_patch_path` are container paths (for example `/execution-output/<run-id>/candidate.patch`), which is poor UX when the human is on a Windows host. Passing `--host-output-root <WINDOWS_ABSOLUTE_PATH>` (or the `NSC_EXECUTION_HOST_OUTPUT_ROOT` environment variable as a fallback; the CLI flag takes precedence when both are set) adds `candidate_patch_host_path` and `workspace_diagnostic_patch_host_path` with the equivalent full drive-qualified host path, for example:

```text
C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch
```

This is a purely lexical, HOST-facing display path (`pathlib.PureWindowsPath`); it is never resolved as a filesystem path inside the Linux container. An empty, relative, traversal-containing, or malformed drive-relative value is rejected before the run starts. `human_result.artifact_path` prefers the host path when one is available, and the stderr footer and `human_result.commands` are built from that exact same path. Omitting `--host-output-root` preserves full backward compatibility: the host-path fields are `null`, `human_result.artifact_path` falls back to the existing container path, and the footer/`commands` use that container path instead of inventing a Windows path.

There is no Planner, Unity execution, general GER, global selection/readiness/dispatch, automatic patch application, commit/merge, evidence publication, conformance record, provider fallback, mixed providers, or parallel task workers. The Contract Locality Auditor does not change this: it never grants readiness, dispatch authority, or dependency-completion approval, and it never edits the task contract, GDD, or graph itself — `CONTRACT_REVIEW_REQUIRED` always routes back through the normal human-reviewed TaskGraph workflow. It is also distinct from, and does not replace, the separate deterministic heuristic `Pipeline/TaskGraph/task_contract_quality_audit.py` pattern audit, which runs outside ExecutionCrew against committed contract text without a model in the loop.

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
