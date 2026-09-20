# Codex task: build the 1,000-task autonomous rehearsal gauntlet

You are implementing the next scale stage of the No Safe Circle Game Task Agent. Build and commit the tooling and deterministic acceptance coverage for an exhaustive **1,000-task private-rehearsal gauntlet**. Do not start the live paid/provider run in this task.

## Repository and base

- Read `AGENTS.md` completely, then read and follow `Docs/AI-Pipeline/GAME_TASK_AGENT_RUNBOOK.md`, the TaskGraph documentation, decomposition documentation, reset/undo documentation, and all instructions those files route you to.
- Use a fresh standalone checkout or worktree. Do not edit any existing controller, rehearsal, task, or review checkout.
- Base exactly on commit `09ae41eaba2d2b102f48b7dd30567840d22bd43c` from private branch `review/orchestration-gauntlet-followup-integration` in `cathode26/NoSafeCircle`.
- Create a focused branch named `codex/thousand-task-autonomous-gauntlet`.
- Do not use Claude. Do not invoke live Codex/OpenAI provider calls either; this task is deterministic implementation and testing.
- Do not access or mutate GitHub Issues, claims, branches, PRs, rehearsal main, Docker, Unity, or any live provider state.
- Never touch `C:\NSC\NSC\NSC-042`.
- Do not add a global `safe.directory` exception.
- Preserve unrelated work. If the exact base is unavailable or the chosen checkout is dirty, stop and report the exact state.
- Commit with `No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>`.

## Outcome

Extend the existing canonical synthetic-gauntlet system so, after the current 10-worker stage passes, an operator can materialize and run an explicitly confirmed private-rehearsal workload containing **exactly 1,000 initial synthetic task contracts**, with dense but acyclic dependencies, interleaved decomposition work, a maximum of ten workers, automated evidence, durable resume, whole-run cleanup, and measurable graph-complete termination.

The implementation must preserve the existing 80-task profile and its behavior. Do not create a second competing generator or scheduler. Generalize `Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py` and reuse the production autonomous-graph controller, architect, decomposition, approval/evidence, reset, and receipt paths.

The eventual live target is only the exact private repository `cathode26/NoSafeCircle-Homework-Rehearsal`. Production must be rejected. NSC-042 must remain the only preserved legitimate active task and must always be explicitly excluded from synthetic automation.

## Workload design

Implement a named deterministic profile, such as `thousand`, while retaining the current 80-task default/profile without behavior drift.

The profile must:

1. Create exactly 1,000 initial synthetic contracts in a collision-free numeric range discovered and validated against the repository. Prefer a clearly reserved range such as `NSC-2000` through `NSC-2999` only if the audit proves it unused. Never silently overwrite or reinterpret an existing contract.
2. Preserve the structural root and NSC-042. Preserve historical contracts on disk and cancel/supersede them through the committed schema rather than deleting history, matching the current 80-task tool's policy.
3. Use 100 dependency waves of width ten so capacity ten is meaningful. Add deterministic cross-wave column edges, periodic diagonal edges, fan-out/fan-in diamonds, and periodic barriers. The graph must remain connected where required and provably acyclic.
4. Keep enough independent work ready in most waves to exercise parallel admission. Resource conflicts should serialize only the affected lanes, not the whole wave.
5. Interleave decomposition throughout the graph. At least one task in every bounded group of waves must require decomposition while other implementation tasks are ready, proving the architect can choose decomposition before the implementation queue is empty.
6. Define the exact expected number and identity rules for dynamically created decomposition children. Initial-contract count and post-decomposition total must be reported separately; never describe a graph with more than 1,000 post-decomposition nodes as “exactly 1,000 tasks.”
7. Use unique, deterministic, narrow output paths under already committed directories. Ordinary implementation tasks should be extremely fast C# plus `.meta` changes with deterministic GUIDs and no scene rebuild. Avoid 1,000 expensive Unity invocations.
8. Keep the scaling workload predominantly fast/lean/targeted. The existing focused fast/standard/deep acceptance suite already proves rigor routing. If you include standard/deep sentinels, keep them few, explicit, and outside critical throughput assertions.
9. Include declared resource groups that deliberately create local contention without overlapping undeclared paths. Never create two concurrently admissible tasks that both write the same file.
10. Generate deterministic manifests containing seed/profile/schema, ID range, contract count, expected dynamic-child count, wave/resource/dependency statistics, source HEAD/tree, repository identity, and hashes of every generated artifact.

## Architect and continuous scheduling behavior

Use the production architect-managed controller. The deterministic scale acceptance must prove:

- maximum active implementation workers never exceeds ten;
- the architect receives a batch/portfolio and does not require one paid decision per task;
- runnable implementation and decomposition candidates can both be selected in the same admission era;
- decomposition is not artificially deferred until no implementation work remains;
- dependencies and resource reservations prevent only unsafe launches;
- when no task is ready but workers/decomposition are active, the controller waits without declaring graph complete;
- a completion/Issue state transition wakes the owning controller, which immediately admits newly ready work;
- the architect/controller continues admitting work until the scoped graph is terminal;
- graph completion requires no active workers, no pending transitions, no unsettled decomposition, no ready/runnable scoped tasks, and verified durable final states;
- after a valid `graph-complete.json` receipt, resume performs no GitHub, Docker, architect, or worker work;
- no polling loop or provider session continues after graph completion;
- a restarted controller resumes the same immutable run scope and capacity and does not steal or duplicate leases;
- shared Git/Issue/TaskGraph observations are bounded and cached per admission. Add instrumentation assertions that catch an O(tasks × candidates) reservation scan or per-candidate Git-history scan;
- session pooling remains identity-bound and rotates/quarantines according to policy rather than growing context without bound.

The live operator command ultimately must support explicit all-OpenAI routing with both `-ExecutionProvider codex` and `-ArchitectProvider codex`, `-MaxWorkers 10`, `-EnableSyntheticEvidence`, exact targets/exclusions, an immutable RunId, and the normal canonical PowerShell launcher. Do not hard-code a provider into the generator.

## Automated evidence and Git integration invariants

- Synthetic evidence remains opt-in and restricted to the exact private rehearsal repository.
- It must never write a human PASS or `human_result`.
- Every automated transition must be hash/identity bound to the exact Issue state, branch, head commit, test evidence, worker/run identity, and task contract.
- Before testing, a task branch incorporates current main. If main advances, it incorporates main again after evidence and before final integration.
- A successful unchanged post-test state must not require a redundant second approval.
- GitHub checks are waited on through the canonical bounded path, not bypassed.
- Completion is proven by durable Issue, branch, commit, integration, evidence, TaskGraph, and graph receipt state—not by process exit code alone.

## Decomposition and undo requirements

Exercise the production decomposition author/reviewer flow and its pooled sessions. Add deterministic scale coverage proving:

- each decomposition plan is identity-bound and applied exactly once;
- retries/resume do not duplicate children or commits;
- downstream dependencies are rewired consistently;
- dynamically created children join the active run scope safely;
- child Issues/branches/checkouts/claims/state prevent unsafe undo;
- an unconsumed decomposition can be undone through the one canonical undo algorithm;
- interrupted published-undo recovery resumes without a second undo commit;
- later main movement, later protected-path edits, wrong plan identity, dirty controller, forged state, linked worktrees, and consumed children all fail closed.

Do not weaken or duplicate the existing undo implementation. Extend its manifest/whole-gauntlet coordination only where the 1,000-task profile requires it.

## Whole-gauntlet preparation and cleanup

The apply path must remain fail-closed:

- dry-run by default;
- `--apply` requires exact expected HEAD and explicit repository confirmation;
- clean, attached, synchronized main only;
- exact private rehearsal repository only;
- atomic materialization or in-process rollback;
- collision detection before writes;
- `taskcontrol validate` before and after materialization;
- no commit or push performed by the generator itself.

Add a canonical, resumable whole-gauntlet cleanup/reset plan or extend the existing reset orchestration. It must use additive commits/reverts, never force-push or rewind history, and must preserve delivered code that later work depends on. It must support dry-run, expected-old-value publication guards, interruption receipts, exact hash validation, and partial-success resume. It must not manually delete arbitrary checkouts, Issues, branches, or files.

## Deterministic test suite

Add a dedicated scale acceptance suite and register it in the appropriate deterministic CI workflow. It must use disposable repositories and in-memory/fake GitHub/provider boundaries; no network, Docker, Unity, GitHub, or paid model calls.

At minimum cover:

1. Exact deterministic generation of 1,000 initial contracts.
2. Existing 80-task generation remains byte/behavior compatible unless a documented schema migration is required.
3. Unique IDs, slugs, GUIDs, files, contracts, and resource declarations.
4. Expected task/dependency/resource/decomposition counts.
5. Acyclic dependency graph and valid parent hierarchy.
6. Maximum ready width and maximum active worker count of ten.
7. Architect admits both decomposition and implementation while both are available.
8. Fair progress across lanes; no starvation.
9. Controller waits during temporary no-ready states and resumes immediately after durable completion.
10. Mid-run process interruption and exact resume with no duplicate Issue, lease, worker, child, commit, evidence, or merge.
11. Transient GitHub observation inconsistency, stale lease, worker crash, provider-invalid response, merge-main movement, and pending-transition recovery.
12. Decomposition apply, retry, child scheduling, safe undo, and interrupted undo recovery.
13. Synthetic evidence never fabricates human PASS.
14. Graph-complete receipt identity and no-op completed resume.
15. Whole-gauntlet dry-run/apply/cleanup and partial cleanup resume.
16. Production repository, NSC-042 inclusion, dirty checkout, detached head, moved origin/main, ID collision, corrupt manifest, cyclic graph, and unsupported schema all fail before mutation.
17. Instrumented upper bounds for Git commands, Issue list/view calls, TaskGraph loads, architect calls, worker launches, sleeps, and scheduler polls. Bounds must scale by documented O(N), O(waves), or O(active workers) relationships—not arbitrary enormous constants that cannot catch regressions.
18. A test that proves the controller does not launch 1,000 workers at once and does not serialize every task to one worker.

For every new behavioral regression, demonstrate that it fails against the pre-change implementation (or state clearly when it is genuinely new capability and use a mutation test proving the assertion is load-bearing). Do not add vacuous source-string-only tests where behavioral execution is possible.

Keep hosted CI practical. Separate quick schema/generation checks from the heavier 1,000-node scheduler simulation, give the scale job an explicit justified timeout, and report measured local runtime and process counts. Do not weaken existing tests or production guards to meet the timeout.

## Documentation and operator runbook

Document:

- profile selection and exact task counts;
- expected dynamic decomposition expansion;
- dry-run/apply commands;
- the later live 10-worker launch command;
- pause/resume and graph-complete behavior;
- automated evidence semantics;
- timing and telemetry locations;
- safe cleanup/reset and interruption recovery;
- explicit prohibition on production and NSC-042 synthetic execution;
- staged rollout: deterministic 1,000-node simulation, current 10-worker live wave, 80-task live graph, then 1,000-task live graph.

Do not claim live success. This task prepares and validates the tooling only.

## Required final report

Return:

- checkout, branch, exact base, exact commit, parent, and identity;
- every changed path and why;
- generated profile statistics: initial tasks, expected dynamic children, waves, dependencies, resource groups, maximum theoretical ready width;
- pre-fix/new-capability failure or mutation evidence;
- every test command, count, result, duration, and process-count metric;
- CI workflow registration and timeout;
- proof the tree is clean and `git diff --check` passes;
- proof no network, GitHub, Docker, Unity, live provider, rehearsal state, production state, or NSC-042 checkout was touched;
- all uncertainties, scaling limits, and anything deliberately left for the live staged run.

Commit the focused implementation, but do not push or merge it.
