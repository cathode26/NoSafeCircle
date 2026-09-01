# Session: Supervised Software Architect + D1C Integration Checkpoint

Date: 2026-09-01
Session/topic: Gauntlet acceptance, architecture pivot to one supervised Software Architect, D1C Slices 1-3, and the three remaining integration tracks

## Goal

Close out the live multi-worker Gauntlet, decide whether the decentralized generic-worker
architecture was still the system we intended to operate, and — after deciding it was not —
build the minimum deterministic foundation for a single supervised Software Architect that
assigns work, reasons about integration/merge risk, and can authorize decomposition safely.

The session deliberately ended by declaring a strategic stop rule:

```text
NO NEW PIPELINE FEATURE unless actual integration/game development proves it is needed.
```

## Starting state

Verified at the start of the session:

```text
production repository:  cathode26/NoSafeCircle
production main:        0596dea8258718208a968cb36c18a552d2366441
private Gauntlet repo:  cathode26/TaskOrchestratorGauntletLive-20260831
private Gauntlet main:  77b4fe4cc43968dc5f7a7b2abacb73081348d980 (NSC-601 accepted)
Stage 5 blueprint:      514c8842f479872699067a894db9cc543cdfb354 (merged design/audit only)
Stage 5 implementation: NOT STARTED
```

At that point the plan of record was still: small contention proof -> 10-worker decentralized
wave -> full 85-task completion proof -> then Stage 5. The preceding handoffs are listed under
*Historical/raw source*.

## Decisions made

### 1. Stage 2 bulk state observation was a real scaling defect, not a flake

The Gauntlet's larger runs exposed that a single Stage-2 planning observation could fan out to
roughly 34,000 Git subprocess invocations across ~85 tasks and ~98 history mappings, because each
task independently reconstructed repository/HEAD context. Multiplied by ten workers that would
have been hundreds of thousands of Git process launches contending for one machine. A second
defect was semantic: a failed bulk observation collapsed to an empty snapshot, every task became
`state_lookup_failed`, and the planner reported ordinary `no_safe_work` with a success exit — an
unknown graph state masquerading as an empty safe frontier.

The fix is a single pinned `ConformanceEvaluationContext` (root, pinned HEAD, pinned tree, dirty
status, one history-aware repository, one validated migration resolver, per-task memo) reused
across bulk evaluation and recursive aggregate/child evaluation, rather than a second state
algorithm. Merged to production as `fa5da9f03343e457af042598bfb83526926123e5`.

**This is the single most valuable thing the Gauntlet produced.** It found a scaling wall before
ten workers hit it.

### 2. The old Gauntlet is complete, accepted, and frozen; the 10-worker wave is retired

The private Gauntlet had already proven what it was built to prove: Stage 1 atomic claims,
Stage 2 deterministic selection, Stage 3 fresh dispatch, Stage 4 contention retry, resume
priority, human holds, repository binding, and real two-worker CAS claim contention.

Decision: close the book on it. Preserve its Issues, branches, logs, receipts, and evidence as
frozen regression history; do not mutate that repository absent a regression in those primitives.

```text
accepted old private main: 2fe8483d805c7071570a06f434c6912c9514dc4f
```

Phase A and Phase B are complete accepted evidence. **Never rerun Phase A.**

The 10-worker wave is **retired, not deferred**. It was the correct acceptance test for
decentralized generic self-selecting workers, which is no longer the architecture; running it
would prove a system we had decided not to operate. Retired with it: generic worker
self-selection as normal behavior, the Fibonacci/dice/hybrid synthetic mechanic, the 85-task
graph and its negative/shared-resource families, Phase A/Phase B naming, and the automated review
simulator.

### 3. One supervised polling Software Architect replaces decentralized self-selection

Recorded as **ADR-045 — one supervised polling architect owns bounded autonomous dispatch**
(authored on the local architect branch; not yet on production `main`).

Shape:

```text
human starts ONE architect session
        ↓
architect polls: TaskGraph state, durable Issue state, active branches/reservations
        ↓
architect reasons about integration/merge surfaces, design seams, decomposition need
        ↓
architect returns START / WAIT / HUMAN_REVIEW per candidate
        ↓
deterministic Python owns claims, leases, checkouts, launches, and all authority
        ↓
worker receives an EXPLICIT task ID (it never self-selects)
```

Key policy decisions:

- **Uncertainty means WAIT, not HUMAN_REVIEW.** Medium/high/unknown risk, low confidence,
  ambiguous architecture, insufficient conflict evidence, and failed model invocation all map to
  WAIT. WAIT does not mutate the TaskGraph, does not create a blocker, and is not permanent.
- **HUMAN_REVIEW is reserved for real authority ambiguity only** — design/canon ambiguity, task
  scope/contract change, or decomposition required — and requires both a named escalation
  category and a non-empty question. Merge/integration uncertainty has no category to name, so
  the architect structurally cannot route it to a human even by trying.
- A bounded decision cache keyed by `task_id + task_contract_sha256 + source_head +
  active_surface_fingerprint` reuses WAIT/HUMAN_REVIEW. **START is never cached; failed
  invocations are never cached.** No permanent blacklist. `max_architect_invocations_per_poll`
  (default 3) keeps an all-WAIT pass from spinning paid model calls.
- The architect's own model is configured at session start. It chooses the *worker's*
  intelligence, not its own. **Default worker count remains 1** until acceptance proves more is
  safe.
- A degraded-resume path exists: only `TaskcontrolStateObservationError` activates it, a valid
  resume candidate is retained, and the fresh pool becomes explicitly unavailable and empty. No
  task is ever fabricated.

### 4. D1C Slices 1-3 survive the redesign; old Slices 4-8 are simplified or retired

Slices 1-3 are deterministic, network-free, GitHub-free graph-mutation primitives. They are
useful regardless of who calls them, so they were finished.

| Old Stage-5 slice | Disposition |
| --- | --- |
| 1-3 D1C planner / materializer / tests | **KEEP** — completed as a deterministic subsystem |
| 4 decomposition-specific durable Issue phases | **SHRINK** — an audit/authorization artifact, not a second Issue state machine |
| 5 generic dispatcher/resume integration for decomposition | **RETIRE** — there are no self-selecting generic workers to teach |
| 6a global D1C-vs-D1C contention claim | **DEFENSE-IN-DEPTH ONLY** — one architect already serializes; keep a cheap CAS guard against a second architect process |
| 6b atomic multi-task affected-contract claim | **REPLACE** — singleton scheduler critical section plus affected-state re-observation |
| 8 distributed decomposition race proof | **RETIRE** — proves a decentralized model we no longer operate |

The architect gets one internal graph-mutation lane: it cannot assign a worker while it is
changing the graph.

### 5. Two final integration concerns were added

- **Execution routing.** The architect recommends a capability level and may express a provider
  preference; deterministic Python resolves the actual provider, model, reasoning effort,
  supervisor model/effort, and turn budget. The LLM never invents model names or budgets.
- **Decomposition authorization binding.** A human authorization is valid only when it binds the
  exact task contract bytes, source HEAD, D1B.2 reviewed candidate SHA, `DecompositionResult`
  SHA, `GraphDeltaPlan` plan ID, canonical `graph_delta` SHA, and independent reviewer evidence.
  Anything mismatched returns a typed non-authorized result.

Both are detailed as tracks B and C in `CURRENT_CONTEXT.md`.

### 6. We are partly rebuilding an existing wheel, and that is accepted

Symphony-style orchestrators and managed long-horizon agent products now exist; starting from a
blank repository today, a large custom agent runtime would not be the recommendation. What is
kept is the project-specific authority model — TaskGraph contracts, evidence-derived conformance,
exclusive resources, Unity non-merge-safe surfaces, and human design/merge authority. A generic
orchestrator does not supply those. This reinforces the strategic stop rule rather than
justifying more infrastructure.

## Work performed

### D1C Slices 1-3 (reviewed local chain)

```text
Slice 1  c082b66a6d0496ff737b16eedf894d46b2dff072
Slice 2  1219ada824a31a36d0a103450fa552de3aa7d357
Slice 3  67bc67c8340a8351c0ad2fe5299bc59e6183f5fe
```

Slice 3's correction round fenced forged validator success, made rollback refuse to destroy
concurrent work, checked commit hooks before neutralization, gave invalid source graphs their own
status, and added `expected_head` as a clean Git authority fence for the future architect.
Independent re-review returned no BLOCKER or IMPORTANT findings.

### Polling Software Architect v1

```text
commit  fe051e5f4dc7c3f2a73d185563ce7411df57fa35
branch  orchestrator/polling-architect-v1
files   11 (including new Docs/AI-Pipeline/Software-Architect-Orchestrator/ with 4 docs)
```

Independent final verification confirmed ADR-045 numbering did not collide (no prior ADR-045
existed; ADR-043/044 files remained byte-identical), the resume-only fallback catches only
`TaskcontrolStateObservationError`, and ranking still comes solely from the composed
`plan_dispatch` kernel with no second algorithm.

### Dedicated integration checkout

```text
checkout  C:\NSC\NSC\SoftwareArchitectIntegration-v2
branch    orchestrator/software-architect-integration
HEAD      c32ac5fe6de0e5f5d9bf440f4f045846c4a6dcdd
```

It starts from production `fa5da9f...`, fast-forwards the exact reviewed D1C chain, then merges
the exact reviewed Software Architect commit. It was not pushed.

### Software Architect Acceptance Gauntlet (new, replaces the old one)

Twelve files under `Gauntlet/SoftwareArchitectAcceptance/`, on branch
`test/software-architect-gauntlet-v1` in `C:\NSC\NSC\SoftwareArchitectGauntlet`, still
uncommitted at the session boundary.

Two deliberately separated verification layers plus a live-evidence verifier. The manifest
declares how to *construct* a reservation; the scenario world *observes* the result with ordinary
`git diff` / `git ls-files`, so actual changed paths are evidence rather than restated
expectations. Fixtures use real local Git with reproducible commit SHAs, proven deterministic by
building the whole fixture twice in separate temp directories.

The first shape declared 15 scenarios A-M (G and I split into blocking/non-blocking pairs) and
gated real PASS on `adapter_kind == "real_polling_architect"`. An adversarial audit rejected that
provenance model, and a bounded correction rewrote all twelve files:

- **`adapter_kind` was removed from the package entirely.** Identity claimed by an adapter is not
  evidence.
- `verify_acceptance.py` exposes `verify_fixtures()`, `run_harness(adapter)` — which has **no code
  path to `STATUS_PASS`** — and `run_acceptance()`, which **takes no adapter parameter** and
  constructs `RealPollingArchitectAdapter` internally. Arbitrary injected adapters are therefore
  harness-only by construction, not by convention.
- A regression test spoofs every capability, sets `adapter_kind`, and renames the class to
  `RealPollingArchitectAdapter`; it still reports only `HARNESS_PASS`. Another test statically
  scans for `adapter_kind` and confines `STATUS_PASS` assignment to `run_acceptance_scenario`.
- The **active manifest shrank to 13 scenarios (A-J), 12 tasks**. **K, L, and M were removed from
  both the active manifest and the verifier**; `decomposition_proposed` / `graph_delta_applied` are
  now rejected as unknown event types. Their specs are preserved as **future specs** in
  `LIVE_PROOF_CHECKLIST.md` §7, including the one-exact-plan-identity rule and §7.4 prerequisites.
- Live evidence gained a `run_metadata` envelope (schema version, run ID, scenario ID, manifest
  SHA-256, repository, source HEAD/tree, scheduler ID, start time), contiguous event sequencing,
  and closed field sets. Waits must carry structured `wait_kind` plus conflicting identity and
  overlapping tokens; prose alone no longer satisfies a check.
- Fixture cleanup was narrowed to `create_fixture_root` / `destroy_fixture_root`, which proves
  strict descendancy, temp-dir residency, non-symlink, marker/token match, and device/inode match
  before `rmtree`. There is no destroy-arbitrary-path primitive.

### Execution Routing v1 and Decomposition Authorization Binder v1

Both were prepared as isolated checkouts branched from integration HEAD `c32ac5f...` and their
implementation agents were launched. Neither had a final report at the session boundary.

## Validation / evidence

```text
production merge (Stage 2 scaling repair): fa5da9f03343e457af042598bfb83526926123e5
Stage-5 blueprint (merged, design only):   514c8842f479872699067a894db9cc543cdfb354
D1C Slice 3 independent re-review:         APPROVE_TO_COMMIT, no BLOCKER/IMPORTANT
Software Architect final verification:     APPROVED, "ready for one local commit; do not push"
architect test suites (reported):          47/47, 26/26, 53/53 PASS; compileall + diff --check 0
```

Latest **completed** Gauntlet baseline, measured after the audit correction and before the final
safety correction:

```text
manifest.py:                               13 scenarios, 12 tasks
verify_acceptance.py (layer 1):            FIXTURE_PASS = 13
--mode harness:                            HARNESS_PASS = 12, PENDING_CAPABILITY = 1
--mode acceptance:                         PENDING_CAPABILITY = 13 (adapter still unwired)
acceptance_smoke_test.py:                  56/56 PASS
compileall / git diff --check:             exit 0
```

The single remaining harness `PENDING_CAPABILITY` is scenario J: its `observe_singleton_contest`
operation has no implementation on either adapter, so the two-scheduler contest is unproven in
every mode.

Two caveats recorded at the time. First, harness-mode agreement is now **tautological by
construction** — the scripted adapter replays the manifest's own expectations — so `HARNESS_PASS`
is plumbing coverage, not scenario validation; only the verifier-owned acceptance path against the
real scheduler reveals divergence. Second, cross-platform SHA determinism is explicitly **not**
claimed; fixture determinism is claimed only for same-host, same-Git-version runs.

Not executed: any live architect invocation, worker launch, push, GitHub mutation, or graph
application.

## Ending state

All values below are **last-session-reported** and must be reverified against current Git,
GitHub, and the local checkouts before any mutation.

```text
production main:            fa5da9f03343e457af042598bfb83526926123e5
D1C Slice 1/2/3:            c082b66a... / 1219ada8... / 67bc67c8...   local, unpushed
Software Architect v1:      fe051e5f...   branch orchestrator/polling-architect-v1, unpushed
integration HEAD:           c32ac5fe...   branch orchestrator/software-architect-integration
old private Gauntlet main:  2fe8483d...   frozen accepted evidence
new acceptance Gauntlet:    uncommitted on test/software-architect-gauntlet-v1
Execution Routing v1:       implementation running, no final report
Decomposition Auth v1:      implementation running, no final report
```

Verification performed while writing this handoff (in the documentation clone at
`fa5da9f...`): `514c8842...` is present and is an ancestor of `main`; the D1C slice commits,
`fe051e5f...`, `c32ac5fe...`, and `2fe8483d...` are **not** objects in this clone. They live in
the other local checkouts and in the private repository, exactly as reported.

## Unresolved issues / known blockers

1. **Acceptance Gauntlet — three verifier/fixture-authenticity blockers** (per-step event
   evidence, grounded live evidence, forgeable fixture-cleanup ownership; detailed in
   `CURRENT_CONTEXT.md`). A final bounded correction was prepared/running; inspect its latest
   report before touching that branch.
2. Execution Routing v1 and Decomposition Authorization Binder v1 have no final reports.
3. `RealPollingArchitectAdapter.observe_cycle` is still unwired, so no scenario has been proven
   against the actual scheduler.
4. `Docs/AI-Pipeline/CURRENT_STATE.md` on `main` is stale (last updated 2026-08-26, before the
   pivot) and was outside this documentation task's authorized file boundary.
5. ADR-045 and `Docs/AI-Pipeline/Software-Architect-Orchestrator/` exist only on the local
   architect branch, not on production `main`.
6. The agent prompt/runner construction rulebook (PR #108) is still an open draft and has **not**
   reached production `main`. See *Outstanding command rulebook* below.

## Next action

> First determine which of the three parallel tracks (Acceptance Gauntlet correction, Execution
> Routing v1, Decomposition Authorization Binder v1) has produced a final report, and read that
> report. Review and commit each locally as it lands. Do not redesign the architecture.

The full ordered integration sequence that follows is in `CURRENT_CONTEXT.md`: merge Routing +
Authorization into the integration branch, persist authorization in durable managed-Issue
authority, wire Architect -> D1B.2 -> authorized plan ->
`apply_graph_delta(expected_head=freshly_reobserved_head)`, reconcile the pre-D1C Issue contract
hash, wire the real Gauntlet adapter, prove it small locally and then live at `max_workers=1`,
then make the game.

## Do not repeat

- Do not rerun old Gauntlet Phase A, run the retired 10-worker decentralized wave, or mutate the
  old private Gauntlet repository. All are complete/frozen accepted evidence.
- Do not rebuild the 85-task fixture, the Fibonacci/dice/hybrid mechanic, or the automated review
  simulator; do not implement old Stage-5 Slices 4-8 as originally designed.
- Do not redesign the Software Architect (ADR-045 is decided) or add a fourth architecture
  project. The three current tracks are the last foundations.
- Do not recommit D1C Slices 1-3 or the Software Architect commit; verify the existing SHAs first.
- Do not enable more than one worker until the acceptance Gauntlet passes with the real adapter.

## Working method for future agents

This workflow is itself part of the continuation context. It is not a style preference — it is the
method that caught the Stage-2 scaling wall, the D1C Slice 3 forged-validator hole, and the
Gauntlet's fake-PASS provenance defect, each time *before* the work was committed. **The next
instance should continue using it unless a concrete reason requires deviation.**

The loop that became the successful rhythm:

```text
bounded implementation
→ deterministic/host validation
→ independent adversarial review
→ targeted correction
→ revalidation
→ guarded commit
→ integration
→ move on
```

For multi-track work:

```text
ChatGPT / human architect
  defines boundaries + authority
        ↓
Claude/Codex implementation lane(s)
        ↓
independent reviewer
        ↓
ChatGPT synthesizes findings and decides the next operation
```

### 1. Re-read current deterministic authority before mutation

Branch, HEAD, origin `main`, working tree and index, relevant TaskGraph state, relevant GitHub
Issue/PR/claim state. Historical context — including this handoff — never substitutes for that
read. Every SHA in a document is last-reported state; current Git and GitHub are authority.

### 2. Define ONE bounded implementation slice

Explicit objective, exact invariants, exact allowed file boundary, explicit no-go files and
actions, and the expected tests. Avoid mixing unrelated fixes. The bounded boundary is what makes
the later diff reviewable and makes a partial failure recoverable.

### 3. Use an isolated branch/checkout for substantial work

Prefer a fresh standalone clone when ownership, EOL, or history risk exists. Never casually mutate
the canonical live Gauntlet or a production checkout. Parallel lanes are encouraged **only** when
their file/authority boundaries are genuinely disjoint — that disjointness is why the three tracks
could run in three PowerShell windows without stepping on each other.

### 4. Delegate implementation to one strong coding agent

Codex or Claude may implement. The prompt is file-based and hash-pinned; large prompts are piped
through stdin; Docker Compose runs with `-p nosafecircle`; do not install unnecessary host provider
CLIs. The implementation agent does **not** stage, commit, push, merge, or mutate live authority
unless the specific reviewed task explicitly requires that boundary.

### 5. Validate the surviving patch independently of the implementer's claims

Inspect the actual Git diff and status. Prove the exact changed-file boundary — a file count is not
path identity. Run deterministic focused tests. Run host-side validation when Docker and Windows
behavior differ; host Git is final authority for Windows bind-mount CRLF projection noise. An
agent's report of its own test results is a claim, not evidence.

### 6. Have an independent model review high-risk work

Do not let the implementer grade its own patch. Prefer a different provider/model family when
practical, and use read-only review containers. Ask for concrete BLOCKER/IMPORTANT findings rather
than speculative redesign. This is what produced the `REQUEST_CHANGES` rounds that mattered.

### 7. If review finds a real defect, correct — do not restart

Keep the good patch. Issue one bounded correction prompt addressing the exact findings. Do not
restart the entire implementation unless the architecture is actually wrong. Re-run only the tests
and review that the changed boundary requires.

### 8. Commit only after review and validation pass

Stage exact paths only; never `git add .` or `git add -A`. Use guarded/fenced commands. Use the
automation identity:

```text
No Safe Circle TaskReviewAgent <task-review-agent@nosafecircle.invalid>
```

Keep local foundation commits unpushed until the integration/release point is deliberately chosen.

### 9. Integrate reviewed commits deliberately

Re-check parent/HEAD before merge or cherry-pick. Preserve exact reviewed commit identities. Run
integration-specific validation after combining independently reviewed slices. Do **not** amend an
already-reviewed foundation commit merely to add a new concern; add a small separate integration
commit instead, so the reviewed identity survives.

### 10. Fail closed operationally

A runner that failed *before* mutation is a runner bug — fix the runner; do not infer repository
failure. If a runner may have crossed a durable boundary, do **not** rerun blindly; re-read durable
authority first. When resuming, preserve worker identity, lease identity, continuation/output
roots, and tested commit identity. Never delete claims, reset, clean, or repair durable state by
guesswork.

### 11. Use the project's command standards

Windows PowerShell 5.1-safe. Native exit code is authority, never stderr presence. For substantial
provider work, keep deterministic setup/preflight separate from the provider call. Use file-based
UTF-8 prompts piped via stdin — no Bash `<` syntax in PowerShell. Docker Compose project name
`nosafecircle`. No global `safe.directory` workaround. Exact-path staging and bounded destructive
operations only.

### 12. Keep architecture work subordinate to shipping the game

Parallelize independent work to save calendar time. Once a subsystem is reviewed and sufficient,
move on. Do not create another infrastructure phase for hypothetical future problems. The standing
project rule remains:

```text
NO NEW PIPELINE FEATURE unless actual integration/game development proves it is needed.
```

### Preferred ChatGPT operator handoff style

The workflow above says *what* to do; this says *how the work is handed to Vincent*. For any
substantial implementation, review, migration, validation, or recovery operation, ChatGPT prepares
a downloadable prompt/script artifact, publishes its exact SHA-256, and gives one guarded
PowerShell command that locates that exact artifact by hash and runs it safely. This interaction
style measurably reduced copy/paste mistakes and made long agent jobs repeatable, so future
instances should use it by default.

```text
ChatGPT defines bounded work
        ↓
ChatGPT creates a downloadable prompt/script artifact
        ↓
ChatGPT computes and displays the exact SHA-256
        ↓
Vincent downloads it (normally to Downloads)
        ↓
ChatGPT gives ONE paste-ready guarded PowerShell command
        ↓
the command locates the exact artifact by filename pattern AND hash
        ↓
the command verifies checkout / branch / HEAD / working-tree state
        ↓
the provider or runner executes
        ↓
Vincent returns the complete final report / [DONE] / [RECOVERY] block
```

Do not make Vincent manually reconstruct a long prompt from chat when a downloadable file is
possible.

**Prompt artifacts.** For a large provider task: create a `.md` prompt artifact, give a descriptive
download link, and state the exact SHA-256 directly under it. The PowerShell side locates the
downloaded file by filename pattern *and* hash, reads it with
`Get-Content -LiteralPath ... -Raw -Encoding UTF8`, and pipes it through stdin to the existing
Docker provider service with `docker compose -p nosafecircle` and the project-approved Claude/Codex
service and model settings. Bash `< prompt.md` redirection is never used in PowerShell. The
following is a documentation example of the shape, not a command to run:

```powershell
$ExpectedHash = "<sha256>";
$PromptFile = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" -Filter "<prompt>*.md" -File |
  Where-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -eq $ExpectedHash } |
  Sort-Object LastWriteTimeUtc -Descending |
  Select-Object -First 1;
if ($null -eq $PromptFile) { throw "Exact prompt not found." };
Set-Location "<exact checkout>";
$Prompt = Get-Content -LiteralPath $PromptFile.FullName -Raw -Encoding UTF8;
$Prompt | docker compose -p nosafecircle ...
```

The convention is the durable part. Do not freeze one provider CLI invocation into the
documentation forever.

**Runner artifacts.** When orchestration logic is too complex for a safe one-liner, create a
downloadable `.ps1` or `.py` runner, publish its SHA-256, and give a short wrapper that:

- finds the exact file by hash;
- parser/compile-preflights it where applicable —
  `[System.Management.Automation.Language.Parser]::ParseFile(...)` for PowerShell,
  `python -m py_compile` for Python when useful;
- runs it;
- treats the native exit code as authority;
- tells Vincent not to rerun blindly on failure.

Substantial deterministic setup and the expensive provider invocation stay separate phases wherever
`Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md` calls for that separation.

**Guard requirements.** The paste-ready command normally fences the important state before any
mutation: expected checkout, expected branch, expected HEAD/parent, clean working tree or the exact
expected dirty boundary, empty index when required, the exact prompt/runner hash, and the exact
allowed path boundary where practical. Do not invent those exact values from historical context —
re-read current authority when the command is written.

**User-visible style.** Vincent strongly prefers one clear next action; a downloadable file instead
of a giant inline prompt; the exact SHA-256 directly under the download; one paste-ready Windows
PowerShell 5.1-safe command; a clear expected `[READY]`, `[DONE]`, or `[RECOVERY]` ending; explicit
instruction about which output to send back; and an explicit "do not rerun blindly" warning when
durable mutation might have occurred. For small harmless read-only commands an artifact is
unnecessary — use judgment and do not create files for trivial commands.

**Failure handling.** If a downloaded runner fails, distinguish a runner/verifier bug from a
product defect. If no durable mutation occurred, fix the runner and continue. If mutation may have
occurred, re-read durable authority before any retry, and prefer a continuation/recovery runner
over replaying work that already succeeded.

This convention exists for the same reason as the rest of this method: it prevents long-prompt
corruption, makes provider instructions reproducible, pins exactly what Vincent ran, reduces
PowerShell quoting and parser mistakes, eases handoff and recovery, and reduces operator fatigue.

### What the next instance must not do

- Do not rebuild the whole design because a new idea looks attractive.
- Do not ask Vincent to restate the architecture already captured here.
- Do not rerun expensive accepted proof work without new evidence.
- Do not treat every reviewer nit as a new architecture project.

## Operator/command lessons worth carrying forward

Paste-ready operator commands target Windows PowerShell 5.1. Docker Compose uses project `-p
nosafecircle`, and prompts are piped into containers rather than redirected with Bash `<`. Host
Git is the final changed-file authority for a Windows bind-mounted checkout, so container CRLF
churn is noise (`git diff --ignore-cr-at-eol --stat` separates it). Stage exact paths, never `git
add .` / `git add -A`. Automation commits use an `.invalid` identity. Never use global
`safe.directory` as a generic ownership workaround. The complete operating list lives in
`CURRENT_CONTEXT.md` and `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md`.

### Outstanding command rulebook — PR #108 is open, not merged

Two different command-documentation efforts exist, and they must not be conflated:

```text
PR #100  MERGED      operator command reliability standards/template + smoke enforcement
PR #108  OPEN DRAFT  agent prompt and runner construction rules companion document
```

The **base** operator command standards and template — `OPERATOR_COMMAND_STANDARDS.md`,
`OPERATOR_COMMAND_TEMPLATE.md`, and their smoke enforcement — are **already on production `main`**
via merged PR #100. Nothing about that work is outstanding.

What remains outstanding is the **companion rulebook**, the document Vincent refers to in session
as the "command no-no's branch". Last independently observed by ChatGPT on 2026-09-01:

```text
PR:        cathode26/NoSafeCircle#108
title:     Docs: add agent prompt and runner construction rules
branch:    docs/agent-prompt-runner-rules
head:      24e81073e41303a93e9f4d8a374ff805e10b4854
state:     OPEN
draft:     YES
merged:    NO
mergeable: YES
files:     1
```

The single file is:

```text
Docs/AI-Pipeline/AGENT_PROMPT_AND_RUNNER_CONSTRUCTION_RULES.md
```

It is a durable companion rulebook for constructing agent prompts, PowerShell runners, native
argv, machine-data verifiers, long-running provider jobs, write boundaries, and recovery paths,
consolidating the concrete failures recorded in command-governance Issue #103.

Notes a future instance needs so it does not mishandle this:

- **Do not rebuild the rulebook.** It exists, is written, and is committed and pushed on its own
  branch. A future agent that cannot find the file on `main` should look at PR #108, not start a
  new authoring task.
- **Do not describe it as uncommitted local work.** Unlike the D1C chain, the architect commit, and
  the acceptance Gauntlet, this branch is already on GitHub. Only review and merge remain.
- **Do not assume it landed on `main`.** It has not.
- The original reason for holding it — waiting on a parallel Stage-5 design run — is **obsolete**,
  because that design work finished. The hold no longer applies.
- Before merging, re-read the current PR state, the current PR head, and current `main`, then
  independently review the one-file diff against the now-merged
  `Docs/AI-Pipeline/OPERATOR_COMMAND_STANDARDS.md` so the companion document does not contradict
  the base standard as it stands today.
- After the new historical-context PR is handled, this is one of the remaining documentation
  merges to finish.
- **Do not merge the old draft historical PR #110 as a substitute.** It is a different, stale
  documentation checkpoint and does not contain this rulebook.

## Historical/raw source

```text
raw/imported-2026-08-31-Build-Task-Orchestrator3.txt
raw/imported-2026-09-01-Gauntlet-PR-CI.txt

preceding handoffs, in order:
2026-08-30-stage4-repository-binding.md
2026-08-31-live-gauntlet-evidence-checkpoint.md
2026-08-31-pr9-exact-head-ci-recovered.md
2026-08-31-nsc601-live-lifecycle-accepted.md
```

Documentation PR #110 was a valid checkpoint but remained draft/unmerged and is stale as current
context. Its restored handoffs remain valuable immutable history; its `CURRENT_CONTEXT.md` state
is superseded by this branch after human review and merge.

## Authority reminder

This handoff is historical context. Every branch, SHA, checkout path, Issue, PR, and
working-tree claim above is last-session-reported, not authority. Before mutating anything,
re-read current Git, GitHub Issue/PR/Actions state, remote refs, local checkouts, and TaskGraph
conformance. Current deterministic project state wins if it disagrees with this file.
