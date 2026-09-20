# Reliability audit — No Safe Circle Game Task Agent orchestrator
Frozen commit `03ec56e13398f158dfe04d10e232f24dbd9e8c7a` · inventory SHA-256 `c43605a8…2c69db` · 79 primary paths

## Executive verdict

The orchestrator's core design is strong: hash-chained Issue events, exact-commit binding everywhere, fail-closed verification after every GitHub write, disposable-clone candidate validation, and deterministic host authority over every side effect. Most of the layered patch modules genuinely close real gaps and are well tested with realistic Git fixtures.

However, **unattended real-task use should not continue until one confirmed false-authority defect is fixed**: the agent-authored handoff and delivery-review comments embed copyable result templates that the GitHub label Action itself parses as *human* results. Adding the `nsc-state:agent-ready` label without posting a result comment — the exact operator mistake the Action was built to reject — fabricates a hash-bound human PASS or, worse, a delivery **APPROVE with the correct proposal SHA**, after which the pipeline can autonomously commit evidence, open a PR, and merge to main. A second operational defect — every crash while `agent_working` orphans the lease because default worker IDs are random per run and only some failure paths release it — makes unattended operation fragile even when nothing malicious happens.

**Attended use (Vincent running and watching, never adding `nsc-state:agent-ready` without first posting the result comment) may continue.** Unattended/scheduled use is blocked on findings F1 and F2 below.

## Audit completeness statement

All **79 of 79** primary inventory paths were read in full (52 runtime/config/doc files, 27 tests). Additionally reviewed from the integration seed set: all four GitHub workflows, `compose.yaml`, `compose.override.yaml`, `Dockerfile`, the TaskGraph migration ledger, and the Game Task Agent runbook; the transitive authority scripts (`taskcontrol.py`, `record_delivery.py`, `generate_delivery_spec.py`, `run_unity_tests_clean.ps1`, `run_crew.py`, AgentRuntime Codex provider) were verified to exist and their CLI/output contracts checked against the orchestrator's invocations (all match, including the `Validation manifest:` stdout line and the `--retry-run/--review-feedback-file` pairing). Remaining seed docs were reviewed by targeted search only; none are runtime-bearing. **Not INCOMPLETE_AUDIT.**

## Actual system and authority map

- **Entry points.** `Start-GameTaskAgent.ps1` → `run_pipeline_agent.py` (production path). `Start-TaskReviewAgent.ps1` → `run_agent.py` (legacy dev slices; `openai-*` modes need the OpenAI Agents SDK, otherwise fail closed). `issue_state_action.py` runs inside `nsc-issue-workflow.yml` on every `nsc-state:agent-ready` label add and is the only human-transition authority. `issue_queue.py` is a read-only queue lister.
- **Model discretion vs deterministic authority.** Codex CLI (in Docker, credential volume, no API key) chooses one action name + arguments per turn; host Python validates action membership, argument shape, and all content. Every Git/GitHub/Unity/file side effect is host code. `downstream_determinism` narrows the action menu to the deterministic next action; `downstream_action_grounding` enum-constrains proposal surfaces/gates/artifact IDs to host-verified inventories.
- **Patch stack (installed in `__init__.py`, order-sensitive):** mainline_reintegration → downstream_resilience → downstream_determinism → (schema restore) → action_grounding → operator_logging → git_identity_guard → merge_closeout_check_repoll → pull_request_check_authority → completed_issue_guard. Order dependencies are asserted by `merge_closeout_check_repoll_smoke_test` and `pull_request_check_authority_smoke_test`.
- **Human authority stops (must remain):** Unity PASS/FAIL on the exact handoff commit; delivery-evidence APPROVE/REQUEST_CHANGES bound to the proposal SHA; unblocking a `blocked` Issue. Merge is agent-executed but only after human delivery approval plus green latest-effective PR checks and `--match-head-commit`.
- **Container boundaries:** supervisor and exec services mount the repo read-only; only `Pipeline/ExecutionCrew/outputs` (exec) and the decomposition/review outputs are writable; the launcher probes read-only-ness and output write-through before running.
- **Git provenance:** all automated commits forced to `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`; GitHub-user-noreply namespaces rejected; CI scans workflows for attributable identities.

## State / phase / action / durable-artifact map

- **Issue states:** `agent_ready → agent_working → human_action_required → agent_ready(repair|delivery_evidence)`; `agent_working → blocked|complete`; `blocked → agent_ready`; plus `task_contract_migrated` (any non-complete → agent_ready). Enforced by a fixed transition table; events are SHA-256 hash-chained with contiguous sequences, prev-event links, state/phase continuity, and migration-hash rollover; `state_version` must equal event count and `last_event_id` the final event.
- **Phases:** implementation, repair, unity_runtime_validation, delivery_evidence, merge_closeout. Phase in the validated Issue routes `run_pipeline_agent` to the implementation controller (`ProductionTaskController`) or downstream controller (`ResumableDownstreamTaskController`), with a fail-closed recheck if the phase changed between selection and routing.
- **Durable artifacts:** Issue body state block + event comments (authoritative); external per-task files under `<checkout-root>/.task-review-agent/`: checkout manifest (`NSC-###.json`), scope (`.scope.json`, lease/head-bound), execution receipt (`.execution.json`), integration receipt (`.integration.json`), downstream state (`.downstream.json`, self-hashed); delivery outputs under the output root (`delivery-<commit12>/`: human-validation.txt, draft, proposal-NN, approved review, spec, validation manifests); ExecutionCrew `crew_result.json` + `candidate.patch`; progress logs per run. All JSON writes are tmp+`os.replace`; delivery_review artifacts additionally fsync and refuse overwrite.

## Reconstructed end-to-end lifecycles (stress results)

- **Fresh start:** eligibility gates (active/implementation/single_agent/concrete/not_delivered/deps-conformant, clean controller at origin/main) → resource-conflict scan → Issue init + lease (verified after write) → staged clone → validate → atomic rename → manifest → scope → ExecutionCrew (Docker) → disposable-clone apply check → canonical apply/commit/push (idempotent via commit trailer) → verified pushed handoff → `human_action_required`. Solid; the only unverified atomicity is push→handoff-publish (F4).
- **Generic resume:** queue of chain-valid `agent_ready` Issues (open only, post-guard); oldest selected; no contract-hash staleness check at selection (dead `durable_selection` has one — F10); routing by phase; checkout resumed bound to the exact recorded branch/head, with narrow allowlisted recoveries (stale origin/main refresh, three ProjectSettings churn files, verified clerical-migration fast-forward).
- **PASS/FAIL:** label Action validates actor/state, requires the exact tested commit, appends the hash-bound event — but the "no result comment" guard is defeated by the agent's own template (F1).
- **Delivery evidence:** policy-pinned Unity platform/filters, manifest bound to exact commit+tree, TaskDelivery draft on a pinned main base, hash-bound proposal, human review via BLOCKED event; approval → evidence commit → conformance rederived → push (remote-head compare-and-check) → PR → release lease while checks pend → repoll live checks each new run, latest-effective-only check authority → merge `--match-head-commit` → fresh-clone post-merge conformance → COMPLETE → close Issue (closed COMPLETE stays discoverable, blocking duplicates).
- **Main advanced:** deterministic `integrate_current_main` merge with drift classification (automation-only allowlist vs runtime-sensitive re-handoff), blob-identity re-verification, restore-on-failure, receipt + state invalidation. Crash windows around its push are the sharpest partial-side-effect risk (F4).
- **Intentionally unsupported flow (fail-closed proof):** generic resume with no valid agent-ready Issue stops with "Pass an explicit -TaskId… generic resume never silently invents a new task" (`generic_selection.py:24-28`); recovery is explicit (rerun with `-TaskId`). Likewise a conformant task without a managed Issue never re-initializes (workflow_runtime gate), and a completed task can never re-lease (completed_issue_guard). All verified in code and tests.

## Confirmed defects

**F1 — P1, confirmed. Agent-authored templates forge human authority through the label Action.**
- Where: `issue_state_action.py:37-45,104-138` (and dead twin `issue_workflow_action.py:159-233`); templates at `issue_workflow_store.py:570-587` (handoff `Result: PASS` + exact commit) and `downstream_issue.py:163-171` (`Decision: APPROVE` + **the exact proposal SHA**); permissive regexes `issue_workflow.py:34-38`, `downstream_issue.py:24-28`.
- Trigger: Issue is `human_action_required` (or `blocked/delivery_evidence`); a human adds `nsc-state:agent-ready` **without** posting a result comment (fat-finger, or "resume" misunderstanding — the precise mistake the guard exists for).
- Sequence: `_latest_matching_comment` scans comments newest-first; the latest parseable comment is the agent's own handoff/request event comment because its fenced template matches the result regex with the correct commit/SHA → `apply_human_result`/`apply_delivery_review` succeeds → a hash-bound HUMAN_VALIDATION_PASSED or UNBLOCKED-approve event is created, with `human_comment_sha256` pointing at the template comment, so `downstream_determinism._authoritative_human_validation` later treats it as fully authoritative.
- Impact: forged Unity PASS routes to delivery_evidence with a false "human validated" artifact; forged delivery APPROVE grants the full autonomous path to evidence commit → PR → **merge to main**.
- Existing guard/test gap: `downstream_determinism` fixed only the *read* path; `test_human_authority_ignores_agent_template` proves that and nothing about event *creation*. No test executes `issue_state_action.main` at all.
- Smallest safe fix: in both `_latest_matching_comment` and `_latest_human_result`, skip any comment containing `EVENT_MARKER` ("nsc-workflow-event") — agent event comments can never be human results. Defense in depth: make the rendered templates non-parseable (placeholder commit/decision).
- Regression test: build a Memory/REST-fixture Issue containing only the handoff (and separately only the delivery request), simulate the labeled event, and assert the Action fails with "No Human validation result comment was found" / "No Human delivery evidence review was found"; repeat with a real human comment posted after the template and assert it is selected.

**F2 — P1, confirmed. Orphaned `agent_working` lease after any hard failure; no expiry, takeover, or documented recovery.**
- Where: `run_pipeline_agent.py:64-69` and `Start-GameTaskAgent.ps1:45-48` (worker ID = machine + fresh UUID per run); `downstream_resilience._wrap_run:1114-1143` releases only on KeyboardInterrupt and "exhausted" messages; nothing releases on `CodexSupervisorError`, `IssueWorkflowStoreError`, `OSError`, timeout, process kill, or reboot; the transition table has no lease expiry and `GhIssueBackend._run` can even raise a raw `subprocess.TimeoutExpired` (F14) mid-lease.
- Sequence: provider outage on turn N → run dies with the Issue `agent_working` → every later run observes `agent_working_by_other` and stops "blocked … Resolve the GitHub Issue coordination conflict" with no instructions.
- Recovery exists but is undocumented and non-obvious: rerun with `-WorkerId <worker_id recorded in the Issue state block>` resumes the lease. The runbook and state-machine doc say only "the recorded worker may continue."
- Smallest safe fix: (a) make the default worker ID stable per machine (drop the UUID) so crash-resume is automatic; (b) add a catch-all `release_for_pipeline_failure(reason="run_failed")` best-effort in `run_pipeline_agent.main`'s exception handler; (c) document the `-WorkerId` recovery.
- Fault-injection test: FakeDecisionProvider that raises on turn 2 after lease acquisition; assert the lease is released (or, with a stable worker ID, that a second run resumes).

**F3 — P2, confirmed. Stale downstream local state after a repair cycle livelocks delivery_evidence.**
- Where: `downstream_pipeline.py:423-434` ("stored validation manifest is stale" raised instead of invalidating), `_next_action:313-325` (stale manifests/draft/proposal satisfy the presence checks); `_invalidate_downstream_receipt` (`mainline_reintegration.py:415-424`) runs only on `integrate_current_main`.
- Trigger: FAIL → repair → new handoff commit B → PASS, with main unchanged (so no integration step purges state). `.downstream.json` still holds commit-A manifests/draft/proposal.
- Sequence: `_next_action` sees platforms "complete" → routes to `publish_delivery_review` → rejected ("branch/commit differs from the human-tested state") → repeated-rejection breaker releases lease → next run repeats forever until a human deletes the state file.
- Fix: in `_assert_human_tested_head` (or observe), when `state["implementation_commit"]`/manifest commits differ from the workflow head, purge `_STALE_RECEIPT_KEYS` exactly as `_invalidate_downstream_receipt` does.
- Regression: fixture with commit-A state, workflow head B; assert next_action returns `run_authoritative_unity_tests` and the stale entries are gone.

**F4 — P2, confirmed. Push-then-Issue-advance crash windows leave the remote branch ahead of the Issue with no automated reconciliation.**
- Sites: `mainline_reintegration._integrate_current_main` (push at 945-966, Issue advance at 999-1030); evidence push (`downstream_pipeline.py:760-781`) vs `release_for_pending_checks` (`downstream_runtime.py:560-585`); implementation push (`candidate_integration.integrate`) vs `publish_human_handoff` (`production_pipeline.py:231-259`). Candidate integration itself resumes cleanly (`_existing_commit_for_run`), but the Issue transition after it does not.
- Sequence: crash or GitHub API failure between push and the Issue write → remote branch = new commit, Issue head = old commit → resumed checkout is a permanent conflict ("recorded handoff commit is not the pushed remote task branch") → breaker releases lease → cross-run loop until manual repair. `downstream_determinism._automation_receipt_from_issue` only helps after the event exists, i.e. not in this window.
- Fix (transactional): persist a durable "pending Issue advance" intent (target commit + transition kind) in `.downstream.json` **before** pushing; on resume, when the remote/local head equals the intent's commit and its parent is the Issue head, complete the recorded Issue transition deterministically before checkout inspection. Minimum fix: detect the exact conflict signature and emit operator instructions naming the pushed commit and the missing transition.
- Fault-injection test: command runner that succeeds `git push` then raises on the next `gh`/backend call; restart the controller and assert deterministic completion (or the explicit operator message).

**F5 — P2, confirmed. Resource-conflict scan is fail-open on transient errors and mis-scoped after the completed-Issue guard.**
- Where: `issue_workflow_store._resource_conflicts:330-336` (`except IssueWorkflowStoreError: continue` — a failed comment fetch silently drops that Issue from mutual exclusion); with `completed_issue_guard` installed, `list_issues` now returns closed Issues too, so (a) a manually-closed Issue stuck in `agent_working/blocked` state permanently blocks overlapping resources, and (b) every closed Issue's comments are fetched on every lease attempt.
- Fix: skip closed issues in `_resource_conflicts`; convert the `except: continue` into a recorded conflict reason ("could not verify …") so it fails closed.
- Test: backend whose `get_comments` raises for the conflicting Issue; assert the lease is blocked, not granted.

**F6 — P2, confirmed. No-progress breaker trips on a legitimately redundant `prepare_task_checkout`.**
- Where: `goal_loop_guard.py:123-146` with fingerprint `53-79`. In the implementation pipeline there is no action narrowing, so the model may re-call prepare on an already-ready checkout; result "resumed" changes nothing → guard declares no progress, releases the lease, and poisons the run. Each occurrence costs a full run and appends two events; can recur across runs.
- Fix: treat `status in {"resumed","ready","adopted","created"}` as progress regardless of fingerprint (the breaker's real target is blocked/no-op loops); or include the prepare result status in the fingerprint.
- Test: guard fixture where observe already reports checkout ready and prepare returns "resumed"; assert the lease is kept (current `goal_loop_guard_smoke_test` only covers status-changing or blocked fakes).

**F7 — P2, confirmed. Concurrent Issue writers can permanently invalidate the event chain; recovery undocumented.**
- Where: `nsc-issue-workflow.yml` has no `concurrency:` group; all service transitions are two-phase (add_comment then update_issue, e.g. `issue_workflow_store.py:485-506`). Two near-simultaneous label events (redelivery, fast toggling) or two agents racing the same Issue both append events with the same sequence; every later validation then fails ("duplicate sequences") — fail-closed by design, but the Issue stays bricked until someone deletes a comment, and no runbook covers it. A crash between add_comment and update_issue produces the same `state_version != event count` brick.
- Fix: add `concurrency: { group: nsc-issue-${{ github.event.issue.number }}, cancel-in-progress: false }` to the workflow; document the "delete the duplicate event comment, restore the body from the surviving event" repair.

**F8 — P3, confirmed.** `verify_post_merge_and_complete` (`downstream_pipeline.py:900-910`) passes `str(None)` → the durable COMPLETED event can record `conformant_record_id: "None"`. Guard with an explicit check before `str()`.

**F9 — P3, confirmed. Doc/config drift.** Runbook prerequisites (`GAME_TASK_AGENT_RUNBOOK.md:53-61`) still demand `OPENAI_API_KEY` + Agents SDK and a pip install, but `requirements.txt` is intentionally empty and the supervisor is API-key-free Codex CLI; `README.md` "Current real command"/"Next boundary" sections describe superseded slices and claim capabilities ("cannot yet … commit, push") that now exist.

**F10 — P3, confirmed. Dead/duplicated authority code.** `durable_selection.py` has zero callers, yet it is the only selection that verifies the Issue's contract hash against the committed contract — the live `generic_selection.py` lacks that check (staleness surfaces later, less legibly, at lease time). `issue_workflow_action.main` is superseded by `issue_state_action` but retains the outdated (and F1-vulnerable) logic; only its `GitHubRestBackend` is used. `coordination.GhCoordinationObserver` is a legacy claim convention kept alive only for old modes.

## Probable defects and high-value risks

- **F11 — P2, probable. Merge-closeout is machine-bound despite "any later generic agent can resume".** Draft/proposal/approved-review files and `.downstream.json` live outside Git/GitHub; on a different machine (or after state loss) post-approval, `_next_action` demands `finalize_delivery_evidence`, which requires the local proposal (`downstream_pipeline.py:659-680`) and there is no route back to delivery_evidence from merge_closeout → stuck until manual event surgery or file restoration. Recommend at minimum documenting the constraint and adding a deterministic "restart delivery review" transition (merge_closeout → delivery_evidence) gated on missing local artifacts.
- **F12 — P3, probable.** Exclusive-resource TOCTOU across *different* tasks: two agents can pass `_resource_conflicts` concurrently and both lease overlapping resources (`issue_workflow_store.py:414-421`); the event chain only serializes same-Issue races. Low likelihood single-operator; verify-after-write of the conflict set would close it.
- **F13 — P3, probable.** `ResumableTaskCheckoutManager.inspect` (`resumable_checkout.py:48-66`) masks a stale-origin/main conflict without evaluating manifest conflict; the subsequent unmanaged-adopt path can silently overwrite a conflicting external manifest that strict inspection would have escalated.
- **F14 — P3, probable.** `GhIssueBackend._run` (`issue_workflow_store.py:791-815`) passes `timeout=180` but doesn't catch `TimeoutExpired`; a slow `gh` raises an exception type most callers don't handle → process death mid-lease (feeds F2).
- **F15 — P3, hypothesis.** `_recover_safe_resume_state` restores allowlisted dirty files and fetches before concluding recovery is impossible — mutation-before-decision; harmless for the current allowlist but a fragile pattern.
- **F16 — P3, probable.** Migration carry-forward is gated on the exact string "exact human PASS for checkout HEAD is missing" (`downstream_resilience.py:735-742`); any wording change silently disables carry-forward (fails closed, confusing). Use a typed error or sentinel.

## Reliability improvements ranked by failure-reduction per complexity

1. Skip event-marker comments in the label Action's result search (F1) — ~5 lines, removes the only reachable false-human-authority path.
2. Stable default worker ID + catch-all lease release on run failure + documented `-WorkerId` recovery (F2) — small, converts every crash from "manual surgery" to "rerun".
3. Purge downstream state when the workflow head changes (F3) — one guarded call to the existing invalidator; removes a whole livelock class.
4. `concurrency` group on `nsc-issue-workflow.yml` (F7) — one YAML block.
5. Closed-issue skip + fail-closed error handling in `_resource_conflicts` (F5).
6. Treat resumed/ready prepare results as progress in the guard (F6).
7. Durable pre-push intent record + resume completion for the three push→Issue windows (F4) — the only medium-complexity item; highest recovery-cost reduction.
8. Adopt `durable_selection`'s contract-hash check into `generic_selection`, then delete the dead module and `issue_workflow_action.main` (F10).

## Tests giving false confidence or leaving dangerous gaps

- `downstream_determinism_smoke_test.test_human_authority_ignores_agent_template` proves the *read* path ignores templates but implies the class is fixed; the *event-creation* path (`issue_state_action`) is the actual vulnerability and is completely untested — no test anywhere drives `issue_state_action.main`/`issue_workflow_action.main` with a `GITHUB_EVENT_PATH` fixture.
- `goal_loop_guard_smoke_test` fakes only blocked/progress/no-op-"ready" prepares; the realistic "resumed on already-ready checkout" false trip (F6) is unexercised.
- `downstream_smoke_test` stubs `_require_lease`, `_assert_human_tested_head`, and `_persist`, so state-file/lifecycle interactions (F3, F11) are never tested against the real code path.
- No fault injection exists for any push→Issue window (F4) nor for GitHub-write failure between add_comment and update_issue (F7).
- `issue_workflow_smoke_test` covers tampering but not an interleaved two-service acquire on the memory backend (the race the README advertises as safe).
- Mock fidelity elsewhere is good: checkout, migration, reintegration, and integration tests use real temp Git remotes/clones/pushes; the ExecutionCrew fake reproduces the real `crew_result.json` schema faithfully.

## Observability and recovery improvements

- Progress logs are genuinely good (operator/debug views, heartbeats, secret-safe field filtering, JSONL journal). Gaps: when a run stops on `agent_working_by_other`, print the recorded `worker_id` and the exact resume command; when a checkout conflict matches the F4 signature, name the pushed commit and the pending transition; document the duplicate-event repair (F7) and the merge-closeout machine binding (F11) in the runbook.
- Add an operator utility that appends a *valid* `AGENT_LEASE_RELEASED` event for a dead worker (the hash-chain makes manual comment authoring effectively impossible today).

## Minimal prioritized patch plan

1. **F1** marker-skip in `issue_state_action._latest_matching_comment` + `issue_workflow_action._latest_human_result`; new Action-level regression tests (blocks unattended use).
2. **F2** stable worker ID, catch-all release in `run_pipeline_agent`, runbook note (blocks unattended use).
3. **F7** workflow concurrency group. 4. **F3** stale-state purge on head change. 5. **F5** closed-skip/fail-closed conflicts. 6. **F6** progress-status whitelist in the guard. 7. **F4** pre-push intent + resume completion. 8. **F8/F9/F10/F16** cleanups.

## Required regression and fault-injection gate

- Action forgery: label-add with template-only comments must fail closed (both Unity and delivery variants); real human comment posted after templates must be selected.
- Lease survivability: kill the loop after lease acquisition (provider exception, SIGINT already covered); assert release or same-worker resume.
- Stale-state repair cycle: commit-A artifacts + head-B workflow → re-run tests, not livelock.
- Push-crash windows: runner fails immediately after `git push` in integrate_current_main, evidence finalize, and candidate integrate→handoff; restart must reconcile or emit the documented operator message.
- Concurrency: interleaved double `acquire_agent_lease` and double label-Action application on one Issue; assert single winner and a recoverable (not silently corrupted) chain.
- Keep the existing suite (all 27 currently wired into the two deterministic workflows) as-is.

## Improvements considered but not recommended

- **Lease TTL/auto-expiry:** stealing a lease from a possibly-alive worker risks split-brain on the checkout; stable worker IDs + explicit release tooling are safer.
- **Making Issue transitions "atomic" by moving state into the comment stream only:** the dual body+comments design is what makes tampering detectable; better to keep two-phase writes and document repair.
- **Rebuilding delivery drafts/proposals from GitHub:** they are intentionally hash-bound local artifacts under human review; a deterministic "restart delivery review" transition is cheaper and preserves the authority model.
- **Replacing the monkey-patch stack with a refactor now:** the stack is ugly but its ordering is asserted by tests; a rewrite would churn verified authority code for elegance, contrary to the audit's goal.

## Explicit answers

- **May real-task use continue?** Attended: yes, with the operator briefed never to add `nsc-state:agent-ready` without first posting the result/decision comment. Unattended: no.
- **Blocks the next unattended run:** F1, F2.
- **Near-term but nonblocking:** F3–F7 (each has a manual workaround), then F4's transactional fix.
- **Human-authority stops that must remain:** exact-commit Unity PASS/FAIL; proposal-SHA-bound delivery approval; unblock decisions; wrong/dirty-checkout conflicts must stay human (never auto-reset).
- **All 79 primary paths reviewed?** Yes — every row below was read in full.

COVERAGE_LEDGER_START
path|depth|role|important callers/callees|finding IDs or none
Pipeline/TaskReviewAgent/__init__.py|deep|patch-stack installer, order-sensitive|installs all extension modules; schema restore for AgentRuntime subset|none
Pipeline/TaskReviewAgent/authoritative_validation_policy.json|deep|contract-hash-pinned Unity platform/filter policy (NSC-020)|read by downstream_resilience.validation_plan_for|none
Pipeline/TaskReviewAgent/candidate_integration.py|deep|verify/apply/commit/push candidate; idempotent resume via commit trailer|production_pipeline; execution_bridge; git_identity_guard patches identity|F4
Pipeline/TaskReviewAgent/codex_supervisor.py|deep|decision schema, strict decision parsing, Docker Codex turn provider, prompt renderer|openai_pipeline/openai_downstream; patched by determinism/grounding/operator_logging|none
Pipeline/TaskReviewAgent/codex_supervisor_turn.py|deep|in-container one-turn adapter; strict-schema conversion; bounded provider diagnostics|AgentRuntime OpenAICodexProvider; invoked via compose codex-supervisor|none
Pipeline/TaskReviewAgent/completed_issue_guard.py|deep|closed-COMPLETE discovery; duplicate-Issue prevention; open-only queue|patches issue_workflow_store._find_candidates/GhIssueBackend.list_issues/list_agent_ready|F5
Pipeline/TaskReviewAgent/contracts.py|deep|strict value contracts (task IDs, SHAs, scope plans, proofs, outcomes)|used by all modules|none
Pipeline/TaskReviewAgent/coordination.py|deep|legacy read-only gh claim-convention observer|only run_agent legacy modes/tests|F10
Pipeline/TaskReviewAgent/delivery_review.py|deep|hash-bound proposal/approved-review creation; fsync + no-overwrite publishing|downstream_pipeline create/finalize|none
Pipeline/TaskReviewAgent/downstream_action_grounding.py|deep|proposal inventory grounding; enum-constrained schema; lease-first routing|patches allowed_actions_for, summarize_result, render prompt, decision_schema|none
Pipeline/TaskReviewAgent/downstream_determinism.py|deep|event-hash-bound human-result reads; receipt rebuild from Issue events; action narrowing; same-state breaker|patches controller/_next_action/search/validate_arguments/provider.decide|F1
Pipeline/TaskReviewAgent/downstream_issue.py|deep|delivery review request/apply, pending-check release, complete transitions|IssueWorkflowService; used by downstream controllers and issue_state_action|F1
Pipeline/TaskReviewAgent/downstream_pipeline.py|deep|core downstream controller: Unity tests, draft/proposal, evidence commit/push, PR, merge, post-merge verify, durable state|downstream_runtime subclass; gh/git/TaskDelivery/TaskGraph subprocesses|F3,F4,F8,F11
Pipeline/TaskReviewAgent/downstream_resilience.py|deep|PASS carry-forward via migration ledger; validation policy; rejection breakers; run wrappers|patches controller + GuardedTaskController + run loops|F2,F16
Pipeline/TaskReviewAgent/downstream_runtime.py|deep|resumable downstream controller: pinned delivery base, evidence-head release, relaxed post-merge, bounded reads|run_pipeline_agent; extends downstream_pipeline|F3,F4
Pipeline/TaskReviewAgent/durable_checkout.py|deep|workflow-head-bound clone/resume manager, hashed manifest|resumable_checkout base; real_workflow|F13
Pipeline/TaskReviewAgent/durable_selection.py|deep|dead: agent-ready selection with contract-hash staleness check|no callers|F10
Pipeline/TaskReviewAgent/execution_bridge.py|deep|Docker ExecutionCrew invocation; stdout/persisted-result equality; receipt persistence|production_pipeline; compose exec services|none
Pipeline/TaskReviewAgent/fake_tools.py|deep|deterministic fake tool surface for legacy vertical slice|goal_loop, run_agent scripted/openai-fake|none
Pipeline/TaskReviewAgent/generic_selection.py|deep|live generic agent-ready selection (no contract-hash check)|run_pipeline_agent|F10
Pipeline/TaskReviewAgent/git_identity_guard.py|deep|non-attributable .invalid commit identity, always overrides checkout config|patches CandidateIntegrator/DownstreamTaskController _ensure_git_identity|none
Pipeline/TaskReviewAgent/goal_loop.py|deep|deterministic goal assessment + scripted fake loop|run_agent, openai_agent/checkout|none
Pipeline/TaskReviewAgent/goal_loop_guard.py|deep|checkout no-progress circuit breaker; lease release; terminal observations|wraps controllers in run_pipeline_agent; extended by resilience/determinism|F6
Pipeline/TaskReviewAgent/issue_queue.py|deep|CLI agent-ready queue lister|GhIssueBackend/IssueWorkflowService (guard-patched)|none
Pipeline/TaskReviewAgent/issue_state_action.py|deep|GitHub Action: validates human label transitions (Unity result + delivery review)|GitHubRestBackend; IssueWorkflowService; DownstreamIssueCoordinator|F1,F7
Pipeline/TaskReviewAgent/issue_workflow.py|deep|state machine, hash-chained events, chain validation, body/dashboard render, result regexes|everything|F1
Pipeline/TaskReviewAgent/issue_workflow_action.py|deep|REST backend (live) + superseded main() with outdated transition guard|issue_state_action imports backend; main dead|F1,F10
Pipeline/TaskReviewAgent/issue_workflow_store.py|deep|Issue persistence service: lease/handoff/result/queue; Memory + gh backends; templates|all workflow writers; guard patches|F1,F5,F7,F12,F14
Pipeline/TaskReviewAgent/mainline_reintegration.py|deep|integrate_current_main merge/classify/push/Issue-advance; receipts; state invalidation|patches controller/openai_downstream; determinism rebuild hook|F4
Pipeline/TaskReviewAgent/merge_closeout_check_repoll.py|deep|checks_pending terminal only after live inspection in same run|patches inspect_or_merge, terminal_outcome, run loop|none
Pipeline/TaskReviewAgent/NativeCommand.ps1|deep|PS5.1-safe native exec with CRLF→LF argument normalization|Start-GameTaskAgent|none
Pipeline/TaskReviewAgent/openai_agent.py|deep|legacy OpenAI-SDK fake/observe agents with deterministic cross-checks|run_agent|none
Pipeline/TaskReviewAgent/openai_checkout.py|deep|legacy OpenAI-SDK lease+checkout agent with deterministic cross-checks|run_agent|none
Pipeline/TaskReviewAgent/openai_downstream.py|deep|downstream Codex goal loop, terminal outcomes, action dispatch|run_pipeline_agent; heavily patched by extensions|F2
Pipeline/TaskReviewAgent/openai_pipeline.py|deep|implementation Codex goal loop; turn-budget blocker recording|run_pipeline_agent|none
Pipeline/TaskReviewAgent/operator_logging.py|deep|presentation-only operator wording, sanitized args, usage counters, hints|patches provider.decide + ProgressLog emit/heartbeat|none
Pipeline/TaskReviewAgent/pipeline_scope.py|deep|read-only repo tools + exact write-scope minting/validation, durable scope state|production_pipeline; execution_bridge; repository_scope facade|none
Pipeline/TaskReviewAgent/production_pipeline.py|deep|implementation controller: observe/status/scope/crew/integrate/blocker|run_pipeline_agent; wraps workflow+scope+bridge+integrator|F4,F6
Pipeline/TaskReviewAgent/progress.py|deep|durable per-run journal, heartbeats, secret-safe summaries|all loops; operator_logging patches|none
Pipeline/TaskReviewAgent/pull_request_check_authority.py|deep|latest-effective-only check classification; breaker terminal outcome|patches _check_state + terminal_outcome (outermost)|none
Pipeline/TaskReviewAgent/README.md|deep|package overview and commands (partially superseded)|—|F9
Pipeline/TaskReviewAgent/real_checkout.py|deep|original strict checkout manager; shared git helpers; staging clone/rename|durable_checkout imports helpers; legacy modes|none
Pipeline/TaskReviewAgent/real_observation.py|deep|read-only Git/TaskGraph observation with identity hash|real_workflow base observer|none
Pipeline/TaskReviewAgent/real_workflow.py|deep|composed workflow: observe/lease/checkout/verified pushed handoff|controllers; DurableIssue/Downstream subclasses|none
Pipeline/TaskReviewAgent/repository_scope.py|deep|facade fixing revision-qualified git-grep parsing; installs on base class|production controller scope|none
Pipeline/TaskReviewAgent/requirements.txt|deep|intentionally empty (no host SDK)|referenced by outdated docs|F9
Pipeline/TaskReviewAgent/resumable_checkout.py|deep|resume policy: stale-main masking, Unity-churn allowlist restore, migration fast-forward|real_workflow default manager|F13,F15
Pipeline/TaskReviewAgent/run_agent.py|deep|legacy CLI entry for dev slices|Start-TaskReviewAgent; CI observe-real|none
Pipeline/TaskReviewAgent/run_pipeline_agent.py|deep|production CLI: selection, routing, guard wrap, progress, exits|Start-GameTaskAgent|F2
Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1|deep|launcher: preflights, Codex volume selection, Docker probes, UTF-8, worker ID|run_pipeline_agent; NativeCommand|F2
Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1|deep|legacy launcher for run_agent modes|run_agent|none
Pipeline/TaskReviewAgent/tests/codex_supervisor_smoke_test.py|deep|proves decision contract, Docker envelope, full fake production loop, model-free terminal|fake providers/controllers|none
Pipeline/TaskReviewAgent/tests/codex_supervisor_turn_smoke_test.py|deep|proves strict-schema conversion, bounded provider errors, host UTF-8|real subprocess probe|none
Pipeline/TaskReviewAgent/tests/completed_issue_guard_smoke_test.py|deep|proves closed-COMPLETE terminality, duplicate prevention, state=all listing|Memory backend + patched store|none
Pipeline/TaskReviewAgent/tests/compose_supervisor_volume_smoke_test.py|deep|proves external credential volume declaration text|compose.override.yaml|none
Pipeline/TaskReviewAgent/tests/contract_migration_checkout_smoke_test.py|deep|proves clerical-migration fast-forward + manifest rekey on real Git|ResumableTaskCheckoutManager|none
Pipeline/TaskReviewAgent/tests/delivery_review_smoke_test.py|deep|proves hash-bound proposal/approval and fail-closed invalid proposals|delivery_review|none
Pipeline/TaskReviewAgent/tests/downstream_action_grounding_smoke_test.py|deep|proves lease-first routing, bounded history IDs, enum-grounded schema|grounding + AgentRuntime schema validation|none
Pipeline/TaskReviewAgent/tests/downstream_determinism_smoke_test.py|deep|proves read-path template immunity, receipt rebuild, narrowing, breakers; misses Action write path|determinism internals|gap:F1
Pipeline/TaskReviewAgent/tests/downstream_issue_smoke_test.py|deep|proves approve/request-changes/evidence-head resume transitions|Memory backend|none
Pipeline/TaskReviewAgent/tests/downstream_resilience_smoke_test.py|deep|proves carry-forward accept/reject on real Git, policy, rejection breaker; stubs persist|migration fixtures|gap:F3,F4
Pipeline/TaskReviewAgent/tests/downstream_smoke_test.py|deep|proves Issue lifecycle, pinned base, newer-main post-merge, review materialization; heavy stubbing|Memory backend + real git|gap:F3,F11
Pipeline/TaskReviewAgent/tests/durable_checkout_smoke_test.py|deep|proves cross-worker resume of pushed handoff, unpushed-handoff rejection (real Git)|DurableTaskCheckoutManager|none
Pipeline/TaskReviewAgent/tests/git_identity_guard_smoke_test.py|deep|proves .invalid identity, noreply rejection, stale-config override, workflow scan|git_identity_guard|none
Pipeline/TaskReviewAgent/tests/goal_loop_guard_smoke_test.py|deep|proves blocked/no-op release + progress keeps lease; misses resumed-on-ready false trip|GuardedTaskController fakes|gap:F6
Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py|deep|proves round-trip, chain tamper rejection, service handoff/result/resume, resource conflict; no true concurrency|Memory backend|gap:F7
Pipeline/TaskReviewAgent/tests/mainline_reintegration_smoke_test.py|deep|proves classifier, automation-only preserve-PASS, sensitive re-handoff on real Git; no crash injection|integrate_current_main|gap:F4
Pipeline/TaskReviewAgent/tests/merge_closeout_check_repoll_smoke_test.py|deep|proves wrapper order + fresh-run repoll semantics|repoll internals|none
Pipeline/TaskReviewAgent/tests/native_command_smoke_test.ps1|deep|proves PS5.1 stderr safety, exit codes, CRLF normalization|NativeCommand|none
Pipeline/TaskReviewAgent/tests/production_controller_smoke_test.py|deep|proves full Issue→scope→fake-crew→commit/push→handoff on real Git|ProductionTaskController|none
Pipeline/TaskReviewAgent/tests/production_pipeline_smoke_test.py|deep|proves scope validation, bridge verification, idempotent integrate/push|scope/bridge/integrator|none
Pipeline/TaskReviewAgent/tests/progress_logging_smoke_test.py|deep|proves operator/debug views, sanitized args, secret filtering, JSONL journal|ProgressLog + operator_logging|none
Pipeline/TaskReviewAgent/tests/pull_request_check_authority_smoke_test.py|deep|proves latest-only check selection, ambiguity fail-closed, breaker terminal, install-last|check authority|none
Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py|deep|proves create/resume/dirty-conflict and claim gate on real Git; shared fixture factory|RealTaskCheckoutManager|none
Pipeline/TaskReviewAgent/tests/resumable_checkout_smoke_test.py|deep|proves stale-main resume + exact Unity-churn recovery on real Git|ResumableTaskCheckoutManager|none
Pipeline/TaskReviewAgent/tests/scene_path_contract_migration_smoke_test.py|deep|proves scene policy, missing-blob identity, migration event chain append-only|issue_workflow + reintegration helper|none
Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py|deep|proves contracts, fake slice, forged-proof rejection, real read-only observation|contracts/goal_loop/real_observation|none
Pipeline/TaskReviewAgent/tests/workflow_runtime_smoke_test.py|deep|proves conformant-task managed-Issue restoration (two-pass observation)|DurableIssueTaskReviewWorkflow|none
Pipeline/TaskReviewAgent/workflow_runtime.py|deep|managed-Issue observation after task leaves not_delivered|run_pipeline_agent downstream workflow base|none
COVERAGE_LEDGER_END
