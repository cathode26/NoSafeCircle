I've read the brief (`Pipeline/ArchitectureReview/outputs/targeted/generic-get-work-20260829-191512/00-problem-brief.md`) and inspected the selector, workflow store, lease path, execution authority, task contracts, resource groups, evidence records, and the pipeline docs. Here is my assessment.

**TLDR:** The resume half of "get work" already exists and is sound; the fresh-work half is deliberately fail-closed and needs three additions: a small committed dispatch policy file, an atomic claim implemented as creation of a deterministic Git ref on GitHub, and a distinct "no work" exit code. The current lease write on the Issue is read-then-write with a verify-after re-read (`issue_workflow_store.py:494-506`), which is *not* a compare-and-swap — two workers can interleave write/verify and both believe they hold the lease, so the claim must be linearized before the Issue is touched. Separately, the operator's two-concurrent-tasks goal is constrained less by orchestration than by the resource model: the `unity-scene:Assets/Scenes/DoorPrototype.unity` and `DoorPrototypeSceneBuilder.cs` exclusive groups each cover 26 of 55 tasks, so real concurrency comes from pairing one scene-touching task with one code-only task (e.g., the enemy-behavior group NSC-013/014/015/017/053-055 declares only `logical:enemy-locomotion-behavior-surface`).

## Desired operator contract

The operator contract should be exactly this, and nothing more:

```powershell
.\Pipeline\TaskReviewAgent\Start-GameTaskAgent.ps1
```

No arguments means: **resume the highest-priority validated agent-ready Issue; if none exists, deterministically select, claim, and start the highest-priority eligible fresh task; if neither exists, say precisely why and exit cleanly.** Opening a second terminal and running the same command must yield a different, non-conflicting task or a clean "no eligible work" result — never a duplicate.

`-TaskId NSC-###` stays as an explicit override (useful for repair and for forcing a specific task), but it must stop being the only way to start fresh work. The current stop message ("Pass an explicit -TaskId to begin fresh work", `generic_selection.py:26-28`) violates the brief's own prohibition and should disappear once fresh selection is policy-authorized.

Everything the operator needs at the end of a run is a short human summary: which task, which Issue, which branch/commit, what state it stopped in, and what (if anything) awaits their Unity Play Mode validation. The pipeline already produces most of this via the progress log and result JSON; it needs a final human-facing digest line more than new mechanism.

## Resume versus fresh-work ordering

Resume-first is correct and already encoded (`selection_priority: "resume_agent_ready_before_new_task"`). Keep it: an agent-ready Issue represents sunk implementation and often sunk *human validation* effort, and finishing it releases its exclusive resources for everyone else.

Two refinements:

1. **Rank resumes by phase, not by Issue number.** `list_agent_ready` currently sorts by `(issue_number, title)` (`completed_issue_guard.py:110`), which is creation-order — effectively task-number order, which the brief forbids as an accidental priority. Rank agent-ready Issues: `merge_closeout` → `delivery_evidence` → `repair` → `implementation`, then product priority (below), then Issue number only as the final deterministic tie-break. Closest-to-done first maximizes resource release and minimizes the window in which `main` advances under an open branch.

2. **A stale-contract resume candidate must not block the whole queue.** `durable_selection.py` already skips hash-mismatched Issues and reports them; the fresh-work path should receive the same courtesy: if all agent-ready Issues are stale, report them and *fall through to fresh selection* rather than stopping, because a stale Issue requires the human-reviewed contract-migration path, not an idle agent.

Resume-only mode is worth retaining as a flag (`-ResumeOnly`) for the operator who wants to drain WIP before starting anything new — it is one `if`, and it makes the WIP story below usable.

## Product-priority model

Today priority exists nowhere machine-readable. Task contracts (`Tasks/NSC-*.yaml`) have no priority field; the only priority signal in the repository is a dated prose line in `REAL_TASK_DELIVERY_RUNBOOK.md` ("the current human-selected next gameplay foundation is NSC-011") — which is already stale, since NSC-011 and NSC-012 have delivery records under `Pipeline/TaskGraph/evidence/`. If the generic command shipped today with "lowest NSC number wins," task numbering would silently become the product roadmap. The brief is right to forbid that.

The correct source is the GDD's **Six-Week Development Plan** (`Docs/GDD/No_Safe_Circle_GDD.md:727-735`), which is already reviewed canon: Weeks 1–2 core wizard/melee loop, Weeks 3–4 doors/pursuit/ranged enemy/floor construction, Weeks 5–6 escape/polish/build. Encode it as a committed, human-reviewed policy file — `Pipeline/TaskGraph/DISPATCH_POLICY.yaml` — containing:

- `schema_version`, `policy_revision`, and an explicit `enabled: true` (its absence or `enabled: false` keeps today's fail-closed behavior);
- an ordered list of **priority tiers**, each naming reconciliation keys or task IDs mapped from the development-plan windows (e.g., tier 1: remaining spell/enemy foundations NSC-007/008/009/013/014; tier 2: doors/rooms/ranged enemy; tier 3: escape/polish);
- eligibility rules stated explicitly: `contract_disposition: active`, `decomposition_state: concrete`, `kind: implementation`, `execution_scope: single_agent`, every `depends_on` entry `conformant` per `evaluate_current_conformance` at the pinned HEAD (this is the explicit policy statement the brief demands — conformant dependencies, not `not_delivered` on the task itself, define readiness);
- WIP limits (below).

Ordering within a tier: fewest unsatisfied dependents last / most-unblocking first is tempting, but for a 55-task solo project it is unjustified complexity. Within a tier, use lowest task ID as a **documented tie-break** — that is acceptable because the tiers, not the numbers, carry product intent, and the human edits the file to reorder. The policy file is small, diffable, and goes through the same PR review as everything else, which satisfies "committed, reviewable, versioned dispatch policy" without a database or scheduler.

`execution_authority.py` then changes from unconditional denial to: authorized **iff** a valid, enabled policy file at the evaluated HEAD names the task as eligible, with the policy revision and reason code in the `ExecutionAuthorization` receipt. An LLM never ranks or selects; the whole selection is deterministic host code over committed inputs.

## Concurrency and WIP behavior

**The linearization point should be atomic creation of a deterministic remote Git ref.** Evaluating the brief's options:

- **Claim-by-ref (chosen).** The worker builds a *claim commit* (a receipt blob: task ID, worker ID, lease nonce, base `main` SHA, task-contract SHA-256, policy revision, timestamp) and pushes it to a deterministic new ref, e.g. `refs/heads/claim/NSC-053`. Git's receive-pack on GitHub accepts a ref creation only if the ref does not exist; a second worker pushing a *different* claim commit to the same name is rejected as a non-fast-forward. Because each claim commit embeds a worker-unique nonce, two claims can never be byte-identical, so the "no-op push succeeds" hole is closed. This is a true server-side CAS using infrastructure the pipeline already trusts (Git remote, `gh` auth), it works across processes and machines, it leaves a durable inspectable receipt, and it is trivially testable against a local bare repository.
- **Serialized GitHub Actions dispatcher.** Real serialization, but adds minutes of latency to "run one command, get work," makes GitHub Actions availability a hard dependency for starting *local* work, and concurrency groups have cancel-in-progress semantics that are easy to misconfigure. Not justified by the failure model of a two-terminal solo operator.
- **Claim election via coordination-Issue comments.** Append-only comments do give a global order, but the election is two-step (write, then read back and see who was first), has no atomic reject, and pagination/deleted-comment edge cases move the correctness burden into parsing. Strictly worse than the ref.
- **Labels / Issue body writes** are already correctly disallowed by the brief; the existing lease verify-after-write in `acquire_agent_lease` (`issue_workflow_store.py:500-506`) narrows but does not close the window — A-write, A-verify, B-write, B-verify leaves B owning the state while A proceeds. With the claim ref serializing entrants *before* Issue initialization, that race disappears for fresh work; for resume the same claim-ref pattern (`claim/NSC-###` already existing and owned by you, or a per-lease nonce ref) can be added later if two-worker resume races are ever observed.

**Claim sequence:** enumerate eligible candidates in priority order → for the top candidate, re-check exclusive-resource conflicts against in-flight Issues *and existing claim refs* → attempt the ref push → on rejection, move to the next candidate (this is the concurrent-loser retry; bound it at, say, 5 attempts) → on success, initialize/lease the Issue recording the claim ref and nonce → create the task branch and checkout as today. The Issue remains the durable operational controller; the claim ref is only the entrance lock, and it is deleted at closeout alongside the task branch.

**Recovery at each boundary** (all deterministic, no automatic destruction of evidence): candidate selected but claim lost → retry next candidate. Claim won but crash before Issue creation → the claim ref plus its receipt identify the orphan; a `reclaim` step at selection time treats a claim ref with no managed Issue and receipt age beyond a TTL (e.g. 60 min) as resumable *by any worker*, which then creates the Issue from the receipt — the ref, not the process, owns the claim. Issue created but lease not acquired / lease acquired but checkout missing → existing resume path already handles this via the recorded branch/checkout state. `main` or the contract advancing during dispatch → the receipt pins base SHA and contract hash, and the existing hash-mismatch stop applies. Candidate becoming resource-conflicted mid-claim → the post-claim re-check releases (deletes) its own just-created ref and moves on; that deletion is safe because the worker provably owns the ref it created. Completed tasks → `completed_issue_guard` already prevents reinitialization; the eligibility filter additionally excludes any task with a closed COMPLETE Issue or a live delivery record.

**WIP:** set `max_agent_working: 2` in the policy file, counted from `agent_working` Issues at claim time, and additionally refuse *fresh* claims when more than `max_awaiting_human: 2` Issues sit in `human_action_required` — otherwise two productive terminals bury the one human who must Play Mode-test everything, and WIP just migrates to the human queue. Resume is exempt from the fresh-claim limits. Starvation of the second worker is handled by the retry-next-candidate loop plus resource-aware ordering: when the top candidate's resources are already reserved, the second worker naturally lands on the best candidate from a disjoint resource group (e.g., worker 1 takes a `DoorPrototype.unity` room task, worker 2 takes NSC-053 keep-distance movement).

## Human-boundary behavior

Change nothing structural. The two existing human stages — Unity Play Mode validation at `human_action_required` with a PASS/FAIL + tested-commit comment, and PR review/merge at closeout — are exactly right for a Unity project where scenes, prefab wiring, and input feel cannot be proven by assertions (this matches the Unity Testing Policy's human-runtime-validation requirement). The generic command must keep stopping at those boundaries and must keep writing the exact branch, commit, checkout path, and Play Mode checklist into the Issue so validation survives days of latency.

The one addition worth making: when a run ends (any exit path), print a two-line human queue summary — how many Issues await Unity validation and how many await merge, with Issue URLs. The operator's real scheduling decision is "should I run the agent again or go test things," and today they must open GitHub to answer it.

Do not add a human approval gate on fresh selection itself. The dispatch policy file *is* the human approval, reviewed once per revision instead of once per task; per-claim approval would reintroduce the `-TaskId` babysitting this feature exists to remove.

## Failure messages and exit codes

Distinguish "nothing to do" from "something is broken." Today everything non-zero is exit 2 with `GAME TASK AGENT: STOP`, and the PowerShell wrapper converts even benign emptiness into a thrown error. Recommended contract for `run_pipeline_agent.py` (wrapper passes codes through, throwing only on 1–2):

| Exit | Meaning | Message shape |
|---|---|---|
| 0 | Work advanced to a durable boundary (handoff, closeout, or completed phase) | Result JSON + queue summary |
| 2 | Real failure (contract error, invalid workflow state, Git/GitHub failure) | Current STOP behavior, unchanged |
| 3 | No eligible work | For each of the top ~5 candidates, one line: `NSC-046 blocked: depends_on NSC-044 not conformant`, `NSC-050 blocked: unity-scene:DoorPrototype.unity reserved by NSC-045 (Issue #81)`, `WIP limit reached (2 agent_working)` — the operator learns *why* the queue is empty without opening the TaskGraph |
| 4 | Dispatch policy absent, disabled, or invalid at HEAD | Names the policy path and revision; explicitly states fresh selection is fail-closed and resume still works |
| 5 | Lost every claim race (another worker took each candidate) | "Concurrent worker claimed all candidates; safe to rerun" — distinct from 3 because rerunning immediately is sensible |

Messages should follow the Unity-programmer language policy: name the task, the component/scene it concerns, the blocking task, and the Issue number — not abstract taxonomy.

## Minimal viable rollout

Prefer deterministic host code; no new model prompting is needed anywhere in this feature.

1. **`Pipeline/TaskGraph/DISPATCH_POLICY.yaml`** (new, human-authored, ~40 lines): enabled flag, tiers, eligibility rules, WIP limits. Seed tier 1 with only the handful of tasks the operator would pick manually this week (e.g., NSC-013/014 pursuit foundation, NSC-007/008/009 spells) — a deliberate allowlist, not "every active task."
2. **`Pipeline/TaskGraph/dispatch_policy.py`** (new): load/validate the policy at a pinned HEAD; pure functions `eligible_tasks(graph, conformance, policy)` and `rank(candidates, policy)`; every exclusion returns a machine reason code plus a Unity-language message. Rewire `execution_authority.assess_execution_authorization` to consult it, keeping the fail-closed denial (current reason code preserved) when the policy is absent/disabled.
3. **`Pipeline/TaskReviewAgent/fresh_claim.py`** (new): claim-receipt schema (canonical JSON, `semantic_sha256` ID, mirroring the lease-ID pattern), claim-ref push/verify/delete against the remote, orphan-claim TTL recovery, and the candidate-retry loop. Test seam: takes a remote URL, so tests use a local bare repository.
4. **`run_pipeline_agent.py`**: on empty agent-ready queue, fall through to `fresh_claim` instead of raising `GenericSelectionError`; add exit codes 3/4/5; add the phase-ranked resume ordering in `generic_selection.py` (or fold `durable_selection.py`'s stronger contract-hash checking into it — having two near-duplicate selectors is itself a small defect worth consolidating).
5. **`Start-GameTaskAgent.ps1`**: pass through exit codes 3/4/5 without throwing; print the queue summary.
6. **Tests** (extends the existing smoke-test suite; `MemoryIssueBackend` plus a temp bare Git remote): two workers from an empty queue race the same candidate list → distinct tasks claimed, one ref creation rejected, no duplicate Issues, no overlapping exclusive resources; two workers race a *single* eligible task → one gets it, the other exits 5; kill a worker after claim-ref creation but before Issue creation → second worker recovers the orphan after TTL from the receipt alone; contract hash changed between selection and claim → claim aborts and releases its ref; policy disabled → exit 4 and zero authorized tasks (preserving the current regression harness's fail-closed assertion); resume ordering prefers `merge_closeout` over `implementation`.

That is the whole rollout. A GitHub Actions dispatcher, heartbeat leases, a scheduler, or any database are not justified: the failure model is at most a handful of workers on one or two machines, and ref-creation CAS plus TTL'd receipts covers every failure the brief enumerates.

## Throughput risks

- **The exclusive-resource mega-groups are the real ceiling.** `RESOURCE_GROUPS.yaml` puts 26 tasks behind `unity-scene:Assets/Scenes/DoorPrototype.unity` and the shared scene builder. Two workers will only both be productive when a scene task can pair with a logical-group task (enemy behaviors, some pure-code systems). If the operator wants sustained 2-wide throughput, the highest-leverage change is not scheduler policy but resource-group refinement — e.g., whether every room-blockout task truly needs exclusive access to the whole scene builder — done through the normal reconciliation review, not by the dispatcher relaxing checks.
- **The human is the bottleneck by design.** Every task funnels through Play Mode validation and merge. Without the `max_awaiting_human` cap, the agent happily manufactures a review backlog; with it, "no eligible work, 2 Issues await your Unity validation" is the *correct* output and should be presented as success, not failure.
- **Claim-then-abandon churn**: a worker that claims, hits a Docker/Codex startup failure, and dies leaves a TTL'd orphan that blocks that task for the TTL window. Keep the TTL short (60 min) and make orphan recovery run at every selection so the next invocation self-heals.
- **`main` advancing under long-lived task branches** grows merge risk on the shared scene; closest-to-done-first resume ordering and the WIP cap are the mitigations, and both are already in the design.
- **Stale runbook priority prose**: once `DISPATCH_POLICY.yaml` exists, the runbook's "current human-selected next task" line should be deleted or pointed at the policy file, or the two will drift and an agent will someday cite the wrong one.

## Acceptance criteria for the feature

1. Running `Start-GameTaskAgent.ps1` with no arguments on a repository with a validated agent-ready Issue resumes the highest-ranked one (phase rank, then policy tier, then Issue number) and never creates a new Issue.
2. Running it with an empty agent-ready queue and an enabled policy claims exactly one policy-eligible task, creates its claim ref, managed Issue, lease, branch, and checkout, and proceeds to the normal implementation pipeline — with no `-TaskId` and no LLM involvement in selection.
3. A task is fresh-eligible only if: named by the enabled committed policy tier, `contract_disposition: active`, `decomposition_state: concrete`, `execution_scope: single_agent`, all `depends_on` conformant per committed evidence at the evaluated HEAD, no open managed Issue, no closed COMPLETE Issue, no exclusive-resource overlap with any in-flight Issue or live claim ref, and WIP limits unmet. Each exclusion is reportable with a reason naming the concrete blocker.
4. In a deterministic two-worker race test from an empty queue against a shared bare remote: both workers finish, they hold different task IDs, exactly one Issue exists per claimed task, no lease has two workers, and their claimed tasks share no exclusive resource. Repeatable and order-independent per the testing policy's isolation rules.
5. In a one-eligible-task race, exactly one worker acquires it and the other exits with the "lost claims" code and a message saying rerunning is safe.
6. A claim ref whose receipt is older than the TTL and has no managed Issue is recovered by the next invocation using only durable state (receipt + Issue query), with a workflow event recording the recovery; no claim, branch, or Issue is ever silently deleted with work attached.
7. With the policy file absent or `enabled: false`, fresh selection is denied with the versioned reason code, resume still works, and the exit code distinguishes "policy disabled" from "no work" and from real errors.
8. Task-number order affects selection only as the documented final tie-break within a policy tier; reordering tiers in `DISPATCH_POLICY.yaml` provably changes selection without touching code.
9. Every run ends by printing the task, Issue URL, branch, commit, stop state, and the count of Issues awaiting human Unity validation and merge, in concrete Unity-programmer language.
10. All existing invariants still hold under the new path: append-only event chains, contract-hash pinning, completed-Issue duplicate prevention, human PASS/FAIL gating, and the non-mutation invariant for every test added.

One caution for whoever implements this: the brief freezes analysis at commit `131cc63`, and the evidence directory shows deliveries through NSC-041 — re-derive the tier-1 seed list from live conformance at implementation time rather than copying any task list from this review.
