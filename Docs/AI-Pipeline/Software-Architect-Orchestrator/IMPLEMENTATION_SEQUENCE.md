# Implementation Sequence

Recommendation document. Not game-design canon, not authorization, and not evidence that
any slice is merged. It replaces the post-Slice-3 plan in
[`../Stage5-Decomposition-Design/IMPLEMENTATION_SEQUENCE.md`](../Stage5-Decomposition-Design/IMPLEMENTATION_SEQUENCE.md).

Every slice keeps existing operating rules: `AGENTS.md`, `CLAUDE.md`,
`Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`, human merge/approval authority, and
required Unity runtime validation are unchanged. ADR-045's explicitly operator-started
polling session is the bounded autonomous-dispatch model under review; no slice enables a
decentralized background worker swarm or autonomous decomposition application.

## 1. Where we are

| Item | Status |
| --- | --- |
| Stage-5 Slice 1 — deterministic D1C planner/preflight | **Implemented locally elsewhere; pending integration.** Not present in this checkout at `fa5da9f0`. |
| Stage-5 Slice 2 — local transactional materialization | **Implemented locally / in review; pending integration**, subject to its current review fixes. Not present in this checkout. |
| Stage-5 Slice 3 — standalone `apply_graph_delta()` | **Planned next.** |
| Polling Orchestrator + read-only architect v1 | **Implemented now**, uncommitted on `orchestrator/polling-architect-v1`. |
| Uncertainty ⇒ WAIT admission policy | **Implemented now**, same branch. |
| Execution capability/provider/model routing v1 | **Implemented for independent review** on `orchestrator/execution-routing-v1`. |
| 10-worker decentralized self-selection wave | **Retired.** |

## 2. Reassessment of the old Stage-5 slices

| Old slice | Verdict | Reason |
| --- | --- | --- |
| 1 — deterministic D1C planner/preflight | **KEEP AS-IS** | A central architect does not remove the need to revalidate a stored `GraphDeltaPlan` against current HEAD. It is the stale-plan gate the new critical section depends on. |
| 2 — local transactional materialization | **KEEP AS-IS** | Partial-write safety and orphaned-child rejection are independent of who schedules. Still the only safe way to write a multi-file graph change. |
| 3 — standalone `apply_graph_delta()` | **KEEP AS-IS, new role** | Becomes the single primitive the architect calls inside its graph-mutation critical section, and stays hand-runnable by an operator. Typed `applied / already_applied / stale_proposal / post_commit_validation_failed` results are exactly what the architect needs to resume safely. |
| 4 — decomposition-specific durable Issue phases | **KEEP BUT SIMPLIFY** | A five-phase distributed state machine existed to coordinate competing workers. That need is gone. What remains genuinely non-reconstructible from Git is *who authorized which exact plan*, so keep a minimal durable record with `work_type: decomposition` and three observable states: `proposal_recorded`, `human_authorized(plan_hash)`, `applied(commit)`. Backward compatibility for existing implementation Issues is still mandatory. |
| 5 — generic decomposition dispatcher/resume | **DELETE / REPLACE** | Workers no longer self-select decomposition, so a dispatch/claim/resume integration for it is machinery for a problem that no longer exists. Replace with architect-side resume that reads the durable record in §1 of its own poll loop. |
| 6a — global D1C logical resource claim | **KEEP BUT SIMPLIFY** | The singleton plus the critical section is the normal serialization. Retain the logical resource token as cheap defense in depth against a manual or second-host apply; it is a string through the existing resource-claim path and needs no new primitive. |
| 6b — atomic multi-task affected-contract claim | **REPLACE** | With one scheduler, the architect computes the affected set, stops admissions, re-observes durable/integration state immediately before mutating, and WAITs if any affected contract is active or unmerged. The residual race (a human manually starting affected work inside the re-observe→commit window) degrades to a detected fail-closed replan, because durable state carries `task_contract_sha256` and a changed contract is already rejected as stale. No failure sequence found that survives the single-architect model and needs a new claim primitive. **Revisit before any multi-scheduler or routinely-concurrent-manual-start use.** |
| 7 — live single decomposition proof | **KEEP BUT REDESIGN** | Still required, but as one end-to-end single-architect proof: observe → propose → validate → independent review → human authorize → apply → resume polling → children become ordinary candidates. |
| 8 — distributed decomposition race proof | **DELETE / REPLACE** | It proves contention between schedulers that the new model does not create. Replace with (a) a deterministic two-actor test that the retained 6a token blocks a manual concurrent apply, and (b) the live proof in Slice 7. |
| 9 — decentralized/background decomposition enablement | **UNCHANGED — out of scope** | ADR-045 authorizes only an explicitly started supervised implementation scheduler session. Autonomous decomposition application or a background worker swarm still requires separate authority. |

## 3. New sequence

Each slice is one reviewable change with its own deterministic tests.

### A0 — Finish Stage-5 Slice 3
- **Scope:** land `apply_graph_delta()` as a standalone deterministic, network-free,
  GitHub-free tool over Slices 1-2, with idempotency, one local Git commit recording the
  plan hash, post-commit TaskGraph validation, and local rollback on validation failure.
- **Depends on:** Slices 1-2 landing.
- **Tests:** double-apply idempotency; stale-plan rejection; ID-collision avoidance;
  post-commit validation failure rolls back and leaves the branch pointer unchanged.
- **Not in scope:** any `Pipeline/TaskReviewAgent/` wiring.

### A1 — WAIT policy and advisory schema (**implemented now**, this branch)
- Uncertainty ⇒ WAIT; narrow design/canon HUMAN_REVIEW; per-pair unknown-surface rule;
  one poll-scoped Stage-2 plan (resume first, then its ranked fresh pool); effective resume
  surface includes its own actual branch paths; stable bounded WAIT cache; 300-second
  per-task re-analysis cooldown; per-poll (3) and cumulative session (12) architect-call
  caps; 60-second polling default; bounded transient reservation-observation retry.
- **Tests:** in the two smoke suites on this branch.
- **Remaining:** review and merge.

### A1B — Execution capability/provider/model routing v1 (**implemented for review**)
- The read-only architect recommends only `fast`, `standard`, or `deep`, an `openai`,
  `claude`, or `no_preference` provider preference, and explanatory rationale. The
  recommendation remains advisory: it cannot bypass START/WAIT/HUMAN_REVIEW policy.
- Deterministic, operator-controlled Python routing owns the actual ExecutionCrew
  provider/model, OpenAI reasoning effort, task-supervisor model/reasoning effort, and
  supervisor turn budget. Model names are operational configuration; they are never
  written into TaskGraph contracts and never become game-design or canon authority.
- The architect's own model remains independently configured by the polling session or
  operator in v1. Worker routing does not change the architect model and is independent
  from decomposition proposal, review, or apply work.
- One route is resolved after deterministic START admission and is held through the worker
  command and any compatible ExecutionCrew retry. V1 does not automatically escalate or
  downgrade FAST/STANDARD/DEEP after validation or worker failure and does not spend more
  by retrying with a stronger route.
- A future Acceptance Gauntlet must prove the complete identity chain: architect
  recommendation → deterministic resolved route → exact worker argv →
  `run_pipeline_agent.py` → production controller → ExecutionCrew command → actual
  AgentRuntime provider/model result. Scheduler launch evidence alone is insufficient.
- **Tests:** strict recommendation parsing, policy resolution/fallback, route-blocked
  no-launch behavior, exact argv/event evidence, worker parsing and propagation,
  supervisor reasoning propagation, ExecutionCrew model/reasoning configuration, and
  retry identity mismatch rejection use local fakes only.

### A2 — Minimal durable decomposition authorization record
- **Scope:** `work_type` on the managed state block plus the three states from slice 4's
  simplification. Additive vocabulary only; existing implementation Issues must parse and
  validate identically.
- **Depends on:** A0.
- **Tests:** decomposition-record fixtures; a regression test proving every existing
  implementation-Issue fixture still validates byte-identically; hash-chain verification
  unchanged.

#### A2 authorization binder (**implemented locally**, branch `orchestrator/decomposition-authorization-v1`)

`Pipeline/TaskReviewAgent/decomposition_authorization.py` is the first A2 slice: one pure
deterministic function, `validate_decomposition_authorization()`, plus its frozen
`DecompositionAuthorizationRecord` / `DecompositionAuthorizationDecision` types. It is not
merged and is not production-authoritative.

- **Boundary:** pure. It writes no file, runs no Git, touches no GitHub Issue, calls no
  provider, and never invokes the decomposer, D1C, or the scheduler. Persistence and the
  authoritative human login stay with the caller.
- **Binding:** a decomposition reaches `authorized` only when one record binds all of the
  exact D1B.2 independently reviewed candidate (recomputed `candidate_sha256`), the exact
  task-contract bytes from `task_execution_contract_identity.sha256`, the exact source
  HEAD and run ID, the exact `GraphDeltaPlan.plan_id`, the canonical SHA-256 of the
  complete plan JSON, the reviewer/evidence identity, and an allow-listed human authorizer
  in the `authorized` state. `artifact_locator` is operational only and grants nothing.
- **D1B.1:** a single-provider D1B.1 proposal is never independently reviewed and returns
  `review_invalid` even when a record claims authorization.
- **Statuses:** `authorized`, `not_authorized`, `stale_binding`, `review_invalid`,
  `artifact_mismatch`; malformed inputs raise `DecompositionAuthorizationContractError`.
- **Tests:** `Pipeline/TaskReviewAgent/tests/decomposition_authorization_smoke_test.py`,
  wired into the Core deterministic workflow.
- **Next slice:** durable Issue persistence and readback of this record. No D1C scheduler
  apply path may be wired until an authorization can survive a restart and be re-observed
  from durable state.

### A3 — Architect decomposition proposal path
- **Scope:** the architect may emit a decomposition proposal for a candidate it judges too
  broad; the proposal carries the per-child parallelism evidence from
  `CONFLICT_AND_DECOMPOSITION_MODEL.md` §7. Reuse existing D1B.1/D1B.2 proposal and review
  machinery — do not build a second proposer.
- **Depends on:** A1, A2.
- **Tests:** proposal artifacts remain `review_only_not_applied`; a proposal alone mutates
  nothing; the independent reviewer/human authorization step is required before any apply
  path is reachable.

### A4 — Graph-mutation critical section
- **Scope:** in the scheduler: stop admissions, re-observe HEAD/durable/integration state,
  compute the exact affected-contract set, WAIT on any active or unmerged affected
  contract, require a clean source checkout, revalidate the authorized plan, call
  `apply_graph_delta()`, re-observe the result, resume polling. Add the retained 6a logical
  resource token as defense in depth.
- **Depends on:** A0, A2, A3.
- **Tests:** affected contract active ⇒ WAIT and no mutation; stale plan ⇒ fail closed with
  no ID reallocation; crash injected before/during/after commit resolves correctly on the
  next poll; a concurrent manual apply loses on the logical resource token; applying does
  not launch workers.
- **Required contract-hash reconciliation exception:** a valid local D1C commit may rewrite
  a parent/dependent contract while an open managed Issue still records the pre-delta
  `task_contract_sha256`. Include that Issue in the affected-contract WAIT/reconciliation
  set and prove that its mismatch is bound to this exact authorized/applied plan. Do not
  stop immediately after a valid apply solely for that expected old hash; unexplained or
  unbound mismatches still fail closed.
- **Advisory decomposition-quality evidence:** record the count of child pairs with
  overlapping predicted change surfaces and the number of children touching each Unity
  serialized asset. These counters are HUMAN_REVIEW evidence only and never replace exact
  requirement coverage or become graph validity gates.

### A5 — Live single-architect proof
- **Scope:** one human-authorized, single-scheduler, real-repository run covering both
  paths: an ordinary implementation assignment and one decomposition end to end, ending
  with the new children appearing as ordinary Stage-2 candidates and being handed out only
  when conflict preflight says parallel execution is safe.
- **Depends on:** A0-A4.
- **Acceptance:** the applied graph passes `taskcontrol validate`/`states`; the human
  authorization is traceable to the exact plan hash; every failure is diagnosable from Git
  and Issue history alone; no destructive recovery was needed.
- The first live proof must use `max_workers=1`. Increasing the worker count above 1 is not
  authorized until this acceptance proof explicitly accepts the conflict model.
- A worker exit 2 caused by a benign exact-task admission decline is a safe-but-fragile
  scheduler stop, not data corruption. Before retry semantics exist, a separate follow-up
  must add a typed "declined before mutation" worker result/exit contract in
  `run_pipeline_agent.py`; stderr string matching is prohibited.
- Any defect found produces a deterministic regression test before the fix is considered
  complete.

## 4. Explicitly retired

- The 10-worker decentralized self-selection wave.
- Decomposition as a competing work type in a generic distributed dispatch queue.
- D1C-vs-D1C global distributed contention as a normal operating mode.
- Atomic multi-task claims for every affected contract (deferred with a stated trigger, not
  deleted from the record).
- Live distributed decomposition race proofs.

## 5. Open questions for independent review

1. Whether A2's three-state durable record is sufficient, or whether human authorization
   should instead be an in-repository signed artifact committed with the delta.
2. Whether the deterministic precondition for clearing an unknown surface — both sides
   declaring disjoint committed exclusive resources — is too strict in practice, given how
   many current contracts declare none.
3. Whether the v1 defaults (3 calls per poll, 12 per session, 300-second re-analysis
   cooldown) are appropriately conservative in the live proof.
4. Whether scheduler adoption of orphaned child processes after restart should be added
   before A5.
5. How HUMAN_REVIEW advisory state should be persisted durably before live use without
   granting it Issue/TaskGraph authority.
6. The public read-only Stage-2/Issue snapshot seam that can remove the remaining duplicate
   Issue observation without changing Stage-2 ranking or invalid-state behavior.
