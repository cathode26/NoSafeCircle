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

The Implementer has `repository_read`, `repository_search`, and `repository_write`, model class `standard`, and may edit existing `--implementation-path` values or create exact `--new-implementation-path` values. The fresh Unity Test Author has the same capabilities, model class `low_cost`, and equivalent test-path authority. Requested role paths and pipeline sidecars are disjoint under conservative case-insensitive comparison. Its prompt includes the committed Unity testing policy and exact implementation diff. The fresh Validator is `high_reasoning` with only `repository_read` and `repository_search`; it reads the physically read-only committed source checkout as baseline context and semantically evaluates the candidate state represented by that baseline plus the exact candidate patch and actual changed paths. The baseline is intentionally unchanged, so absence of candidate edits there is not a defect and the Validator must not require them to be committed or applied before review. A pass is semantic review only, never a Unity, delivery, readiness, integration, or conformance claim. The source remains unchanged until a human approves and manually applies `candidate.patch`.

## Optional role-scoped provider sessions

`run_crew(..., role_session_bindings=...)` is opt-in plumbing for a future
worker pool. Each entry maps one ExecutionCrew role to one
`ProviderSessionBinding`, and that binding is handed to that role's provider
invocation so a compatible conversation can be resumed instead of restarted.
Supplying nothing leaves every role exactly ephemeral, so existing runs,
retries, and provider factories are unchanged; a binding supplied alongside a
`provider_factory` is refused rather than silently ignored.

Sessions are role-specific and provider-specific. `resolve_role_session` refuses
a binding filed under one role but naming another, and one naming another
provider, before any adapter sees it; the adapters independently enforce the
same two facts against `request.role`. A role that asked for a session but whose
provider transcript proved no identity stops the run rather than being reported
as a successful ephemeral invocation. `crew_result.json` gains
`provider_sessions`, the confirmed role/provider/mode/UUID receipts a later
compatible assignment could resume. Session reuse changes nothing about
authority: every role still receives its current task, capabilities, and write
boundaries, and the deterministic incremental changed-path check still decides
what the run produced.

Codex resume additionally requires `codex_resume_sandbox_argument`, an
operator-verified fragment reproducing the start-time sandbox policy, because
`codex exec resume` does not accept `--sandbox`. Without it the resume is
refused rather than run under a different permission policy.

## Role-scoped session pool

`session_pool.py` is the ExecutionCrew side of a reusable work-crew pool. It
records which provider conversations exist, which assignment currently owns one,
and which are no longer safe to reuse. It starts nothing, waits on nothing, and
terminates nothing: worker process lifetime stays with whoever launched it, and
pooling means a resumable conversation, not a live process or container.

`contract_locality_auditor`, `implementer`, `test_author`, and `validator` keep
separate pools. A conversation is offered back only for the exact stable
identity that created it: provider, exact model, reasoning effort, session class,
role, capability class, repository identity, and crew/session protocol version.
Task ID, source commit, checkout, allowed paths, and the assignment itself are
deliberately excluded from that key because they are refreshed every assignment
and are never continuing authority. Anything uncertain starts a fresh session. A
protocol version other than `CREW_SESSION_PROTOCOL_VERSION` is refused outright,
at construction and again when durable state, a lease, or a durable result is
restored, so a payload cannot claim the supported protocol at the top level while
carrying a conversation that learned another one.

`SessionPool.checkout` reserves one conversation for one assignment and returns
an `AssignmentLease` carrying the pool schema version, lease ID, session
identity and mode, provider, model, reasoning effort, session class, role,
capability class, repository identity, protocol version, worker-slot ID, task ID,
worker run ID, source commit, checkout identity, checkout timestamp, and prior
completed assignment count. A checked-out session is invisible to every other
assignment, sessions are created lazily, and the pool supports at least ten
concurrent assignments. Claude accepts a pool-chosen `--session-id`, so the identity is
known at checkout; Codex names its own thread, so a cold Codex lease carries no
identity and adopts the one its transcript confirms.

`check_in` requires a `DurableAssignmentResult` and the crew run directory that
proves it. Every identity must equal the lease -- pool schema, protocol, lease,
session record, crew run, task, worker run, worker slot, session class, role,
capability class, provider, model, reasoning effort, repository, source commit,
checkout, and the provider-confirmed session -- and the compatibility it states
must equal the pooled conversation's. The result names the exact persisted role
artifact (`role_results/<role>_<attempt>.json`) and its SHA-256; the pool re-reads
that file, rehashes it, and requires it to record the same role, the same agent
status, and the same deterministic changed-path and semantic decisions the result
claims. A process exit code, a caller assertion, or a bare session ID proves
nothing. Anything else quarantines: missing or malformed session identity,
transport failure, uncertain timeout, mismatched fields, a missing durable result,
missing or tampered role evidence, rejected changed paths, rejected semantics,
corrupt state, or an unknown protocol version. Quarantine, probation, retirement,
and expiry only stop the pool selecting a session; they never delete provider
history or credentials and never touch a running worker.

The role artifact is not merely consistent with its result: it carries the
assignment itself. `pooled_assignment_evidence` writes a strict
`pooled_assignment_evidence` block into the persisted role result whose exact
field set is `ROLE_EVIDENCE_FIELDS` -- role evidence schema, pool schema,
protocol, crew run ID, lease ID, session record ID, task ID, worker run ID,
worker slot ID, session class, role, capability class, repository identity,
source commit, checkout identity, provider, model, reasoning effort, the exact
provider confirmation, role status, assignment outcome, semantic decision,
changed-path decision, and the artifact path itself. At check-in
`DurableAssignmentResult.evidence_reason` rebuilds that block from the already
lease-proven result and compares every field, refusing an extra field, a missing
field, or any disagreement. A perfectly valid successful artifact copied from
another crew run, lease, task, or source checkout therefore fails closed instead
of proving this assignment.

An unproven provider confirmation never becomes an identity. A pre-bound
conversation keeps the identity the pool chose, whatever a mismatched
confirmation asserts; a provider-named cold conversation adopts the identity its
transcript confirmed only when the confirmation matches the lease exactly and the
role artifact proves the assignment. Otherwise the quarantined record and its
lifecycle state retain no adopted identity at all.

Session lifetime is the committed policy in
`Pipeline/AgentRuntime/session_lifecycle.py`; the pool applies it and owns no
second copy of those numbers. A worker session spends 48 weighted units
(`low_cost` -> fast = 1, `standard` -> standard = 3, `high_reasoning` -> deep = 6),
so a session retires after exactly 48 fast, 16 standard, or 8 deep completed
assignments; an architect session retires after exactly 100 completed admission
cycles. Waiting and idling through `SessionPool.observe` cost nothing.
Incompatibility and identity failure retire immediately, two consecutive
provider/output failures retire, a known context-window utilization of 70% or
more retires, and three comparable latency samples at or above twice their
baseline retire. Every one of those decisions is applied at an assignment
boundary only: an active assignment is never interrupted, expired, stolen, or
retired, and a conversation whose next assignment would overflow the budget
retires at checkout instead of starting work it cannot finish.

The failure streak is reachable through the pool rather than only in theory. A
first exactly proven provider/output failure is counted by the committed policy
and the conversation is placed in `probation`: it is never advertised, never
reusable, and invisible to `checkout`. Only `offer_probation_retry`, naming that
exact record and restating the identical stable compatibility, may offer it one
controlled retry, and that retry is an ordinary assignment whose own durable
result decides what happens next -- a fully evidenced success resets the streak
and returns the conversation to `idle`, while a second consecutive counted
failure retires it for `consecutive_provider_output_failures`. A failed role is
never returned as a successful reusable result, and an active retry is never
interrupted. Anything unproven -- a missing durable result, a mismatched lease, a
missing or borrowed artifact -- still quarantines rather than earning probation.

An idle session stays reusable for one hour after a successful check-in, a
half-open window: reusable below 3600 seconds, expired at exactly 3600. Only
conversations on that clock -- `idle` and `probation` -- expire, so a stale
probation is never offered a retry an hour later. An active lease is never
expired or stolen however long its worker runs, because a slow worker may still
own it.

`SessionPoolStore` persists pool state at a caller-supplied path outside the
repository; mutable scheduler state is not repository content. Writes are
atomic, and loading rejects duplicate JSON keys, unknown schema or protocol
versions, malformed UUIDs, duplicate session identities, duplicate active
leases, and impossible state combinations. The future architect scheduler is the
authoritative writer; nothing here mutates an Issue or makes a scheduling
decision.

`run_crew(..., role_session_leases=..., scheduler_repository_identity=...)` gives
each role's lease to that role's provider invocation. Pooled leases fail closed
unless every identity this execution can prove independently matches: task,
worker run, role, provider, routed model and reasoning effort, the exact captured
source commit, the exact source checkout, the scheduler-proven repository, the
capability class the role is actually invoked with, and the crew/session protocol
version. The repository is read from the checkout's own configured origin and
must equal both the scheduler-proven value and every lease, so neither the caller
nor a lease can assert a repository the checkout does not confirm. The complete
check runs before any provider work and again at the real invocation boundary,
where the routed capability class first exists. A human-review retry, another
task, another checkout, another repository, or a re-routed role can never inherit
a warm conversation.

At that same real invocation boundary the crew resolves the provider
configuration this role will actually be invoked through -- with the one runtime
resolver, not a second copy of it -- and requires the resolved provider and model
to equal the lease's provider and routed model. The returned `AgentResult` is
held to the same identity. An injected `provider_factory` is bound by exactly
this rule, so a fake or a misconfigured route can never run a pooled role under a
provider or model its lease did not authorize; the run fails closed before the
provider is invoked and publishes no evidence at all.

A reused session's first invocation is prefixed with `assignment_capsule`, which
closes the previous assignment, revokes every authorization it carried, and
restates the current role, task, source commit, checkout root, capabilities,
allowed and denied write paths, and evidence obligations. A role's repair attempt
continues that same conversation rather than opening a second one, and no role is
skipped because its session is warm.

`crew_result.json` gains `provider_sessions` receipts, `pooled_role_leases`,
`durable_assignment_results`, and `reusable_role_sessions`, and each pooled role
result under `role_results/` gains its `pooled_assignment_evidence` binding. A
role publishes durable evidence only after it actually ran and its AgentRuntime
result, semantic validation, and deterministic changed-path validation have all
been decided, and
only an outcome all three accepted appears in `reusable_role_sessions`. A role
that was never invoked -- because the contract-locality audit stopped the run, or
an earlier role failed -- appears in `pooled_role_leases` with `invoked: false`
and no durable result, so its lease is returned deliberately rather than
recycled on this run's silence. Supplying no pool arguments leaves every run
exactly as it was.

## Exact approved new files

**Migration/operator note: Do not scaffold absent files just to make them tracked.** Select the flag from the path state:

| Path state | Flag |
| --- | --- |
| existing tracked regular production file | `--implementation-path` |
| absent exact production file | `--new-implementation-path` |
| existing tracked regular test file | `--test-path` |
| absent exact test file | `--new-test-path` |

Existing tracked files retain the backward-compatible repeatable flags `--implementation-path` and `--test-path`. Exact absent files use repeatable `--new-implementation-path` and `--new-test-path`. Normal mode requires at least one implementation path and one test path across each role's existing/new pair; either role may use only existing files, only new files, or a mixture.

New authority is one exact repository-relative file path, never its parent directory. Preflight requires a canonical path whose suffix is not `.meta` in any casing, that is absent and untracked, nonignored, collision-free under conservative case-insensitive comparison, underneath the repository root, and whose existing ordinary parent ancestry contains no symlink. Except for the repository root, the parent must also be a Git tree in the captured source commit; an empty source-only directory grants no authority. Existing flags require both tracked identity and regular-file type. Implementation/test paths and their implicit sidecars must be disjoint. Missing directories are never created.

For every successfully created approved file under `Assets/`, ExecutionCrew creates `<path>.meta` after the role's deterministic incremental scope check. Providers never receive `.meta` write authority. Sidecar bytes are UTF-8/ASCII with LF and a final newline:

```text
fileFormatVersion: 2
guid: <sha256("NoSafeCircle.ExecutionCrew.UnityMeta/v1\0" + casefolded POSIX path)[:32]>
```

Snapshots record HEAD, exact index bytes, tracked/untracked identity, entry type, and regular-file SHA-256. This prevents a later role from changing an earlier role's untracked new file or a pipeline sidecar. Candidate and diagnostic patches contain the ordinary binary/full-index tracked diff followed in stable path order by `git diff --no-index -- /dev/null <new-file>` fragments for approved new files and sidecars. Nothing is staged. A review-ready candidate must pass `git apply --check` against the unchanged captured baseline.

For an approved candidate, the human applies `candidate.patch` normally; it creates both the approved new file and its deterministic `.meta` sidecar. Do not create or regenerate the sidecar separately. The sidecar is pipeline-owned and is never a model write path.

Result compatibility fields `requested_implementation_paths` and `requested_test_paths` remain the sorted total authority. Additive fields are `requested_existing_implementation_paths`, `requested_new_implementation_paths`, `requested_existing_test_paths`, `requested_new_test_paths`, and `pipeline_generated_paths`. Role actual-path fields contain model-authored changes and exclude sidecars; `final_actual_changed_paths` includes the complete candidate surface.

Human-review retry still forbids every explicit task/provider/path flag. New-format runs verify both the total against immutable TaskExecution WriteBoundaries and each existing/new classification against the already-validated prior `source_head`: a regular blob is prior-existing, absence is prior-new, and another Git object type blocks. Only then may a prior-new path that is a regular blob at current HEAD become existing authority; one still absent remains exact new authority. A missing prior-existing path blocks. Historical runs without new-path metadata retain legacy recovery and treat recovered scope as existing.

All-new example:

```text
python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-### --provider claude \
  --new-implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/EnemyHealth.cs \
  --new-test-path Assets/NoSafeCircle/DoorPrototype/Tests/EnemyHealthPlayModeTests.cs
```

Mixed example:

```text
python3 Pipeline/ExecutionCrew/run_crew.py --task-id NSC-### --provider codex \
  --implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/ActiveEnemyRegistry.cs \
  --new-implementation-path Assets/NoSafeCircle/DoorPrototype/Scripts/EnemyHealth.cs \
  --test-path Assets/NoSafeCircle/DoorPrototype/Tests/ActiveEnemyRegistryPlayModeTests.cs \
  --new-test-path Assets/NoSafeCircle/DoorPrototype/Tests/EnemyHealthPlayModeTests.cs
```

The Validator must report exactly once on every task AC/VAL ID, and every `criteria_results` item requires a structured `reason_code` alongside its `status`, with deterministic status/`reason_code` agreement enforced by the crew: `status=pass` requires `reason_code=proved`; `status=fail` requires `reason_code=criterion_failed`; `status=not_proven` requires exactly one of `runtime_not_executed`, `missing_integration_dependency`, `missing_required_artifact`, `insufficient_evidence`, `design_ambiguity`. An overall Validator `pass` may carry a `not_proven` item only when its `reason_code` is `runtime_not_executed` (runtime/Unity evidence that genuinely was not executed yet, coexisting with an otherwise-proved semantic pass); any other `not_proven` reason_code on an overall `pass` is deterministically invalid and rejects the run. `missing_integration_dependency` and `design_ambiguity` must never coexist with `pass` and require overall `status=blocked_by_design`; the crew further routes that case to `contract_review_required` rather than a generic `blocked`, because it identifies the same kind of locality defect the mandatory audit exists to catch. `missing_required_artifact` and `insufficient_evidence` also cannot coexist with `pass`, and a `criterion_failed` result cannot coexist with `pass`.

One independent clone outside `/workspace` accumulates both write roles and, if needed, one repair cycle. An immutable snapshot captured immediately after checkout is the baseline for final clone HEAD/index/untracked/path checks, including tracked additions, deletions, and byte changes; clone bytes are never compared to source working-tree bytes. Before and after each write invocation the crew records clone HEAD, exact index entries, untracked paths, and SHA-256 for every tracked working-tree file. Incremental byte changes must pass that role's `AgentInvocationRequest.is_path_writable`; claims never establish scope. Changed HEAD/index, untracked files, deletion/rename/copy effects, or out-of-bound byte changes reject the run. Source HEAD/tree/status is independently revalidated after every invocation and at finalization.

Windows bind-mounted source repositories can appear under different ownership inside Linux containers. For cloning only, the crew creates a run-scoped temporary `GIT_CONFIG_GLOBAL`, registers the exact resolved source root and its resolved `.git` directory as `safe.directory` values, and uses `git clone --no-local --no-checkout`. The protected config lives outside the source checkout and disappears with the disposable run workspace; the user's normal global Git config is not changed.

Validation permits at most two passes. `pass` emits review-only `candidate.patch`; `blocked_by_design` stops; first-pass `needs_changes` runs one repair cycle with exact findings; a non-pass second validation ends `needs_human` or rejected with no candidate patch. Role blockers stop safely. Other tracked changes may be retained only as `workspace_diagnostic.patch`.

A human rejection of a `review_ready` candidate starts a new run; it never resumes or mutates the prior run. `--retry-run` recovers the task ID, provider, exact task-contract identity, exact requested Implementer/Test Author WriteBoundaries, and the prior `candidate.patch` from the prior immutable artifacts. New-format results carry `requested_implementation_paths`, `requested_test_paths`, and `candidate_patch_sha256`; legacy results recover authority from persisted TaskExecution requests and may omit the candidate hash, but the candidate artifact itself is still required. A changed task-contract identity is not a review retry: it fails closed and requires a new normal ExecutionCrew run.

The normal clean-source preflight captures current committed `HEAD` and tree as the new final-patch baseline, and the prior source commit must still be an ancestor. After the mandatory current Contract Locality Auditor passes, ExecutionCrew creates its disposable clone and verifies candidate lineage on the inherited implementation/test paths plus only the deterministic sidecars derived from prior-new `Assets` paths. If that surface is unchanged from the prior source, the rejected candidate—including approved untracked new files and sidecars—is seeded into the disposable clone before either writer runs (`retry_seed_mode=applied`); the sidecars remain outside both model WriteBoundaries. If the current committed source already contains the complete exact rejected candidate post-image, regular-file type/content equivalence is proven using a separate prior-HEAD disposable reconstruction while deliberately ignoring only the formerly-new files' trackedness, and the current state is retained (`retry_seed_mode=already_present`). Partial integration, missing or altered sidecars, and any other candidate-surface divergence fail closed even when Git could mechanically apply non-overlapping hunks. The real source checkout and current writer clone remain unchanged by this verification.

The required UTF-8 feedback file must be a non-empty regular file of at most 64 KiB underneath the configured output root. Its exact bytes are copied to the new run as `human_review_feedback.txt`, hashed with SHA-256, and supplied to Implementer, Test Author, and Validator. Telemetry records only the prior run ID and hashes, not feedback text. Feedback is review evidence: it cannot override the task contract or GDD and cannot widen write authority. During a seeded retry, either writer may legitimately make no incremental change when the human correction belongs only to the other role; the retry still requires at least one net deterministic writer correction before the Validator, and the final accepted state must remain different from the seeded candidate after any repair cycle. If neither writer changes the seeded candidate, the run stops as `needs_human`; if a later repair cycle erases the correction and returns to the seed, finalization rejects the run. If a correction needs another path, the crew blocks; the human must start a new explicitly scoped normal run.

During a human-review retry, the Implementer and Test Author keep their normal disjoint scopes. Human feedback commonly mixes a production correction with a regression-test requirement; regression tests, test coverage, and other Test Author-owned work mentioned in that feedback are explicitly **not** Implementer blockers. The Implementer must not modify test files; if the production correction can be completed within its approved implementation `WriteBoundaries`, it must make that correction and continue, optionally noting required regression coverage for the Test Author. The Implementer should report a blocker only when the production correction itself cannot be completed within its approved implementation paths or is blocked by task/canon/design. The Test Author continues to receive the exact human feedback and explicitly owns any regression/test requirement in it, adding coverage where possible within its approved test paths and reporting a blocker only if the required test correction actually cannot be made there. The Validator continues to receive the same feedback and evaluates the candidate as a whole — both the production correction and appropriate regression coverage — and must not pass while the human rejection remains unresolved. Human feedback still never expands the TaskContract, GDD, or either role's write authority, and the existing single Validator-driven repair cycle is unchanged.

In `claude-exec` and `codex-exec`, the source is mounted only as `/workspace:ro`; host `Pipeline/ExecutionCrew/outputs` is mounted separately at `/execution-output:rw` and selected by `NSC_EXECUTION_OUTPUT_ROOT`. There is no writable nested mount beneath `/workspace`. Local deterministic development falls back to `Pipeline/ExecutionCrew/outputs` when that environment variable is absent.

ExecutionCrew prints flushed, human-readable progress to stderr while reserving stdout for the final machine-readable result JSON. Blocking role invocations emit a heartbeat every 15 seconds by default; deterministic tests may set the positive finite `NSC_EXECUTION_HEARTBEAT_SECONDS` override. Each run also writes and immediately flushes `progress.jsonl`. This file is supplemental operational telemetry only and has no authority over changed paths, validation, delivery, or readiness; it never contains prompts, raw provider output, credentials, or model reasoning.

For real Claude-backed roles, `construct_real_provider` always attaches a `ClaudeLiveRenderer` (`Pipeline/AgentRuntime/providers/claude_code.py`) as the provider's `live_observer`, independent of the writable/read-only profile. The Claude Code adapter always invokes the CLI with `--output-format stream-json --verbose --include-partial-messages`, and the renderer streams concise, human-safe activity to stderr as it happens: assistant `text_delta` text inline, and `[Claude tool] <Name>` lines for tool use. It never writes `thinking_delta` content, `signature_delta`/signature values, raw `tool_result` payloads, or a duplicate full assistant message. This live view is presentation-only: the completed NDJSON transcript is always independently reparsed and strictly validated (the terminal `type=result` event must be the last nonblank line of the stream, with no other event before or after it in that position) regardless of what the renderer did or whether it failed, so a rendering bug can never weaken or replace that check or otherwise become provider truth. The `--json-schema` structured-output contract, capability/tool restrictions, and write isolation are unchanged by streaming.

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
ARTIFACT: C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch

FIND PATCH:
Get-Item -LiteralPath 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

CHECK PATCH:
git apply --check 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

APPLY PATCH:
git apply 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch'

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
ARTIFACT: C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\workspace_diagnostic.patch

FIND DIAGNOSTIC PATCH:
Get-Item -LiteralPath 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\workspace_diagnostic.patch'

DO NOT APPLY:
This is diagnostic work from a non-review-ready run, not an approved candidate.

NEXT: Inspect the diagnostic patch and blocking reason; no candidate was approved.
```

**`workspace_diagnostic.patch` must not be applied.** It is retained tracked-file movement from a run that did not reach `review_ready`, never an approved candidate; the footer and `human_result.commands` intentionally omit any apply/check command for it.

When the mandatory pre-Implementer Contract Locality Auditor itself stops the run, the footer identifies `contract_locality_audit.json` with find/inspect-only commands — there is no patch of any kind in this result, so the footer never prints patch or diagnostic-patch wording:

```text
RESULT: CONTRACT_REVIEW_REQUIRED
WHY: The committed task contract contains one or more AC/VAL items that are not locally implementable/provable under its current scope or dependencies.
ARTIFACT: C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json

FIND AUDIT:
Get-Item -LiteralPath 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json'

INSPECT AUDIT:
Get-Content -LiteralPath 'C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-012-example\contract_locality_audit.json'

NEXT: Review the audit, repair the task contract through normal human-reviewed TaskGraph workflow, validate the graph, and rerun ExecutionCrew.
```

If instead the Validator caught the same defect class after writers already ran (the mandatory audit passed, but the Validator later reported `blocked_by_design` with `reason_code=missing_integration_dependency` or `design_ambiguity`), `CONTRACT_REVIEW_REQUIRED` uses the diagnostic-patch footer shape instead (`FIND DIAGNOSTIC PATCH:` / `DO NOT APPLY:`), since a `workspace_diagnostic.patch` may exist in that case; it remains non-applyable exactly like any other diagnostic patch.

When there is no artifact at all (no candidate, audit, or diagnostic patch), the footer keeps the existing `RESULT`/`WHY`/`ARTIFACT`/`NEXT` lines with `ARTIFACT: none` and prints no `FIND`/`CHECK`/`APPLY` block.

This summary never includes prompts, raw provider output, credentials, hidden reasoning, or feedback text.

## Host artifact paths

Inside Docker, `candidate_patch_path` and `workspace_diagnostic_patch_path` are container paths (for example `/execution-output/<run-id>/candidate.patch`), which is poor UX when the human is on a Windows host. Passing `--host-output-root <WINDOWS_ABSOLUTE_PATH>` (or the `NSC_EXECUTION_HOST_OUTPUT_ROOT` environment variable as a fallback; the CLI flag takes precedence when both are set) adds `candidate_patch_host_path` and `workspace_diagnostic_patch_host_path` with the equivalent full drive-qualified host path, for example:

```text
C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs\nsc-005-example\candidate.patch
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
docker compose run --rm -T claude-exec python3 Pipeline/ExecutionCrew/run_crew.py --retry-run nsc-005-20260823t222010z --review-feedback-file /execution-output/feedback/nsc-005-mana-feedback.txt --host-output-root "C:\NSC\NSC\NoSafeCircle\Pipeline\ExecutionCrew\outputs"
```

The retry inherits `NSC-005`, `claude`, and both prior role scopes, but works from the current clean committed source `HEAD`—which may contain the manually integrated rejected candidate. If the repair cannot be made within inherited authority, do not widen the retry; start a suitably scoped explicit run after human review.

The equivalent initial command may select `--provider codex` and run in `codex-exec`. Defaults are `claude-sonnet-5` and `gpt-5.6-sol`; environment overrides remain available.
