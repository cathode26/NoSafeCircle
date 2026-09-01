# First Live Proof: Scope, Preconditions, Acceptance Gates, and Deferred Work

**Do not run any of this yet.** This document specifies the future proof. At
the time of writing, the polling architect implementation is uncommitted, the
real scheduler adapter is unwired, and no dedicated proof repository exists.

This is operating guidance for a future run. It is not game-design canon and it
is not evidence of anything.

---

## 1. Scope

The first live proof is deliberately small.

| Dimension | Value |
| --- | --- |
| Schedulers | 1, plus a second only for the scenario J contest |
| Workers | 2, maximum 3 |
| Scenarios | 5 to 8, chosen from §4 |
| Repository | one disposable private repository, cloned for the proof |
| Duration | bounded; stop on the first unclassified authority failure |

Explicitly **not** in scope:

- any ten-worker or wave-style contention run;
- any operation against production `cathode26/NoSafeCircle`;
- any destructive operation against any `main`;
- **anything in §7.** Decomposition proposal, graph-delta application, and
  independent authorization are deferred entirely;
- enabling automated review of anything the scheduler itself produced.

---

## 2. Preconditions

Every item must be true before the proof starts. Any false item stops the run.

### Code readiness

- [ ] `Pipeline/TaskReviewAgent/polling_orchestrator.py` and
      `architect_preflight.py` are reviewed, committed, and merged.
- [ ] Their smoke tests pass in a clean checkout.
- [ ] `RealPollingArchitectAdapter.observe_cycle` is implemented as a
      translation shim only, populating `CycleObservation.events` from the
      scheduler's own emitter.
- [ ] `verify_acceptance.py --mode acceptance` produces `PASS` for at least
      scenarios A, B, C, D, E, F, G1, G2, H1, H2, I1 and I2 against the local
      fixtures.
- [ ] `RealPollingArchitectAdapter.observe_singleton_contest` genuinely starts
      two schedulers against one checkout-root lock, or scenario J remains
      `PENDING_CAPABILITY` and is proven live instead.
- [ ] The whole adversarial block of `acceptance_smoke_test.py` still passes
      after the adapter is wired. In particular
      `test_spoofed_capabilities_and_identity_cannot_manufacture_a_pass`,
      `test_only_the_acceptance_path_can_emit_pass` and
      `test_missing_worker_id_cannot_reach_an_acceptance_pass`.

### Repository readiness

- [ ] A dedicated, private, disposable proof repository exists.
- [ ] `require_safe_target_repository` accepts it, and it is not a
      `cathode26/NoSafeCircle` lookalike.
- [ ] The proof checkout's `origin` resolves to exactly that repository. A path
      name is never authority.
- [ ] The checkout is on `main`, clean including untracked files, and local
      `HEAD` equals `origin/main`.
- [ ] No `refs/nsc/claims/**` refs exist before the run.

### Identity capture

Record and freeze before the first poll. These are exactly the fields the
evidence envelope's `run_metadata` record must carry, so capture them in the
form `verify_live_evidence.py` will re-read:

- [ ] `repository` as `owner/name`;
- [ ] proof checkout absolute path;
- [ ] `source_head` and `source_tree` of the proof repository;
- [ ] source commit of the No Safe Circle checkout the scheduler runs from;
- [ ] `scheduler_id`, provider, and model;
- [ ] `manifest_sha256`, from `manifest.py --list` or
      `manifest_module.manifest_sha256()`;
- [ ] `run_id` and `run_started_at`;
- [ ] the exact commit of this acceptance directory.

### Evidence capture

- [ ] The scheduler writes a JSON-lines envelope to a durable path **outside**
      both repositories, beginning with the `run_metadata` record.
- [ ] Every event carries `sequence`, `run_id` and `scenario_id`, and every
      wait carries structured conflicting identities and overlapping tokens.
- [ ] Architect advisory artifacts are retained and marked
      `advisory_only_not_applied`.
- [ ] The envelope path is recorded in the run record before the run starts,
      not after.

---

## 3. Sequence

Deterministic preparation and expensive provider work stay in separate operator
phases, per `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md` §11.

```text
PHASE 1  (deterministic, cheap, repeatable)
  1. verify every precondition in §2 and print the frozen identities
  2. run the local acceptance suite against the wired real adapter
  3. seed the proof repository's task graph and durable Issue state
  4. re-observe the seeded state and print READY

PHASE 2  (one scheduler, bounded)
  5. start the scheduler with --dry-run; confirm it observes Stage 2 and
     reservations, calls no model, and launches nothing
  6. start the scheduler for real with max_workers=1
  7. observe one START; let the worker finish or stop it deliberately
  8. raise max_workers to 2 and observe a second parallel-safe START
  9. introduce the conflict fixture and observe a WAIT with a named reason
 10. integrate the conflicting work and observe the WAIT become a START
 11. start a second scheduler for the same identity and observe it fail closed
 12. stop admitting; do not kill children; do not release leases

PHASE 3  (verification)
 13. run verify_live_evidence.py against the saved envelope, once per scenario
 14. record the result with the frozen identities from §2
```

Stop immediately, before step 13, on any of:

- an unclassified authority failure;
- a scheduler-blocked event whose reason is not one of the documented
  deterministic-defect reasons;
- any durable mutation the run did not intend;
- any observation the harness reports as `UNPROVEN` where the step claimed it
  was proven.

---

## 4. Candidate scenarios for the first run

Choose five to eight. The first four are strongly recommended because each one
fails in a different way.

| Priority | Scenario | Why it earns a live slot |
| --- | --- | --- |
| 1 | D — human-held unmerged reservation | The cheapest catastrophic bug: a scheduler that counts live workers instead of reserved surfaces will launch straight into a held scene. |
| 2 | E — actual change overrides prediction | The only scenario that proves the scheduler re-observes rather than trusting its own earlier prediction. |
| 3 | F — WAIT becomes START | Proves a WAIT is temporary. Without it, a conservative scheduler that deadlocks looks identical to a correct one. |
| 4 | J — scheduler singleton | The one failure that invalidates every other result if it is broken. Needs two real schedulers; it cannot be simulated. |
| 5 | A — parallel-safe assignments | Proves the scheduler can actually parallelize at all. |
| 6 | B — predicted exact-path conflict | Proves Stage 2 still offers another candidate after a WAIT. |
| 7 | G1 + G2 — unknown surface pair | Proves conservatism without deadlock. Run both or neither; one alone is misleading. |
| 8 | H1 + H2 — architect unavailable and malformed | Cheap to induce. H2 is the more interesting half: a plausible-looking but structurally invalid response must be rejected rather than parsed loosely. |

Scenarios C, I1 and I2 are well covered by the local fixtures and can stay
local for the first run.

---

## 5. Acceptance gates before any larger use

The proof is accepted only when all of these are true, in this order.

### Gate 1 — evidence completeness

`verify_live_evidence.py` exits 0 for every scenario the run claimed. That means
zero `FAILED` checks and zero `UNPROVEN` **required** checks. An optional check
reported `UNPROVEN` is informational; a required one is a failed run.

### Gate 2 — exact assignment

Every launch carried an exact `--task-id` and a unique `--worker-id` in its
argv. No task was assigned twice. No worker ID was reused. No launch is missing
its worker ID, and nothing supplied one after the fact.

### Gate 3 — explainable waits

Every WAIT carries a structured `wait_kind` with either the conflicting task
and the exact overlapping tokens, a `not_provably_disjoint` verdict, or the
named advisory defects. At least one WAIT is later followed by a START for the
same task, with a reservation snapshot before and after that genuinely differ,
and with the WAIT's recorded fingerprint matching the snapshot that produced it.

### Gate 4 — narrow human review

No human escalation occurred for merge or integration uncertainty. Any
escalation that did occur carried a design/canon category **and** the specific
question.

### Gate 5 — singleton and claim hygiene

Exactly one scheduler acquired the lock. The competitor was rejected against the
same lock identity, named the correct holder, and launched nothing. No
`refs/nsc/claims/**` refs remain in the local checkout, and both repositories
end clean. Note that the local ref check is a diagnostic: it does not establish
anything about the remote.

### Gate 6 — no unintended durable mutation

The proof repository's durable state differs from its recorded starting state
only in ways the run explicitly intended. Nothing was reset, cleaned, stashed,
force-pushed, or repaired to make a check pass.

### Gate 7 — human sign-off

A human reads the event envelope, not only the verifier summary, and confirms
the scheduler's reasoning is legible. A run that passes every mechanical gate
but whose WAIT reasons are unreadable has not proven the thing that matters:
that a human can tell why the repository is idle.

---

## 6. What a passing proof does and does not authorize

**Does authorize:**

- raising `max_workers` beyond 3 in the disposable repository;
- adding more scenarios from the manifest to the live set;
- planning the deferred work in §7.

**Does not authorize:**

- running the scheduler against production `cathode26/NoSafeCircle`;
- applying any graph delta;
- treating any architect advisory as authority;
- skipping human merge, closeout, or Unity runtime/visual validation, which
  remain required and unchanged.

---

## 7. Deferred: decomposition acceptance (the former K, L, and M)

Three scenarios were removed from the active manifest during the audit
correction. They were not merely gated; simulating them added fake proof,
because a harness that replays an expected string cannot distinguish a real
decomposition authority chain from a fabricated one. The earlier live-evidence
verifier demonstrated the risk: it accepted a chain in which the proposal was
validated under plan hash A and applied under plan hash B.

They are preserved here as **future specifications only**. They must not be
re-added to `scenarios.json`, and `verify_live_evidence.py` must not regain
decomposition event parsing, until every prerequisite in §7.4 holds. Today a
`decomposition_proposed`, `decomposition_authorized` or `graph_delta_applied`
event is rejected as an unknown event type, and
`test_live_evidence_rejects_decomposition_and_unknown_events` keeps it that way.

### 7.1 Future K — a broad feature task must be decomposed, not assigned

A task spanning a targeting interface, two runtime behaviors, a prefab, a
ScriptableObject and a scene placement must produce a decomposition proposal
rather than a launch.

Required to accept it:

- a real proposal artifact from the deterministic decomposition machinery,
  carrying per-child predicted surfaces and an inter-child overlap matrix;
- the artifact recorded as `review_only_not_applied`;
- no worker launched for the parent;
- the `decomposition_required` escalation accompanied by the specific named
  design question.

The expected child boundaries and the serialized integration seam must come
from that machinery. This document must never become a substitute decomposer,
and the manifest must never carry a pre-computed decomposition result.

Also carry forward the completion-locality rule from
`Docs/AI-Pipeline/DECOMPOSITION_CHECKOUT_ISOLATION.md`: a child's completion
gate must not require downstream content whose task depends on the parent.
A structurally acyclic proposal can still contain a semantic completion cycle.

### 7.2 Future L — exact graph-delta application and idempotency

Consume the real Stage-5 Slice 3 `apply_graph_delta()` primitive:

- the first authorized apply produces exactly one graph commit recording the
  exact authorized plan hash;
- an identical second apply is `already_applied` with zero commits;
- a plan bound to superseded identities is rejected with a typed reason and no
  ID reallocation;
- the resulting children then enter the normal candidate pool.

Commit accounting requires the real primitive. No harness value may satisfy it,
which is why the `commit_count` expectation was removed from the manifest
schema rather than left present and unsatisfiable.

### 7.3 Future M — decomposition is never self-authorizing

A decomposition may only be applied after deterministic validation, an
independent challenge by a reviewer that is provably not the proposing run, and
a human authorization bound to the exact reviewed plan.

The authority chain, in order:

```text
decomposition_proposed
decomposition_validated
decomposition_independently_reviewed
decomposition_authorized
graph_delta_application
```

Identity rules that must all hold:

- the reviewer identity differs from the proposer identity;
- the authorizing actor is a human, not the scheduler and not the architect;
- **one exact plan identity binds every plan-bearing stage.** Proposal,
  deterministic validation, independent review, human authorization and
  application must all carry the same plan identity. A mismatch anywhere fails
  closed. This is the specific weakness the audit found, and any future
  implementation must treat a hash that changes between stages as a failure
  rather than as a re-derivation.

Each of the following must fail closed: reviewer equal to proposer;
authorization recorded by a non-human actor; an applied plan identity different
from the authorized one; any missing step in the chain.

### 7.4 Prerequisites before any of §7 is re-enabled

- [ ] Stage-5 Slice 3 `apply_graph_delta()` is integrated, with idempotency and
      stale-plan rejection covered by its own tests.
- [ ] The architect can produce a real decomposition proposal artifact carrying
      per-child predicted surfaces and an inter-child overlap matrix.
- [ ] An independent challenge exists: a reviewer identity that is provably not
      the proposing architect run.
- [ ] Human authorization has a durable schema that binds the exact reviewed
      plan identity, and that identity is stable across all five stages.
- [ ] The graph-mutation critical section is implemented: no new launches for
      the duration, re-observation of HEAD and reservations, exact
      affected-contract computation, a clean source checkout, and plan
      revalidation against current HEAD.
- [ ] A dry rehearsal exists in which each of the self-authorization negatives
      fails as expected.

A decomposition applied without every item above is a graph rewrite authorized
by its own proposer, which future scenario M exists to forbid.
