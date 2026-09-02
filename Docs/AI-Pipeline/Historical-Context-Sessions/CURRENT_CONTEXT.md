# Current Task Orchestrator Context

Last context update: 2026-09-02

> **Important:** Dynamic Git/GitHub/local-checkout facts below are last-verified or
> last-session-reported state, not standing authority. Before any mutation, re-read current Git,
> TaskGraph, GitHub Issue/workflow, remote refs, and relevant local checkout state.

## First action in the next window

Do **not** ask Vincent to reconstruct the Software Architect architecture.

1. Re-read live `main`.
2. Re-read the NSC-042 task branch/check-out and its managed Issue/workflow state.
3. Determine whether the revised **narrow DoorPrototype builder-output integration** was already
   run after this context was written.
4. If not, continue that exact bounded slice; then finish NSC-042 from an exact clean post-builder
   commit.

Primary handoff:

`Docs/AI-Pipeline/Historical-Context-Sessions/2026-09-02-software-architect-live-production-and-nsc-042.md`

Earlier architecture rationale:

`Docs/AI-Pipeline/Historical-Context-Sessions/2026-09-01-software-architect-integration.md`

## Current objective

The Software Architect infrastructure is in production and has already been exercised on real game
work. Stop building speculative infrastructure.

The immediate goal is to finish NSC-042 and make one narrow workflow correction proven necessary by
that real task:

```text
AI candidate changes DoorPrototypeSceneBuilder.cs
        ↓
run DoorPrototypeSceneBuilder.Build()
        ↓
capture intended builder-owned generated outputs
        ↓
automated validation
        ↓
commit/push exact clean task state
        ↓
Vincent validates that exact commit
        ↓
PASS → delivery/integration
```

Intended builder-owned output boundary selected at the end of the session:

```text
Assets/NoSafeCircle/DoorPrototype/**
Assets/Scenes/DoorPrototype.unity
```

Unity/editor side effects outside that boundary — especially `ProjectSettings/**` — are not
automatically part of the task commit unless they were already part of the verified AI candidate.

## Live GitHub state verified for this context update

```text
repository: cathode26/NoSafeCircle
main:       c7c37cd80436e0c7d8fabd0b80f36790a5c9de7c
main tip:   Materialize TaskGraph review work

NSC-042 remote:
  branch: nsc-042-seamless-scalable-wall-tiling-for-long-isometric-walls
  HEAD:   2a4861235e8ba363d4b85e8d0a77a807db5aec26

broad experimental branch:
  pipeline/pre-handoff-unity-generation-hygiene-20260902-004901
  HEAD: 473cf101502108b0844f7151f25c8255f30d8d45
```

Local checkout cleanliness is **not** verified here. The last session reported that the NSC-042
builder had run and left builder-generated files plus two unrelated ProjectSettings side effects
dirty. Re-read before restore/stage/commit.

## Production architecture that is already done

Do not reopen these as architecture projects:

- Software Architect Acceptance Gauntlet v1.
- Execution Routing v1.
- Decomposition Authorization Binder v1.
- Real `PollingOrchestrator` acceptance adapter for ordinary cycles.
- Windows GitHub UTF-8 Issue-read boundary.
- Windows-host Game Task Agent controller boundary.
- Canonical mutation API precedence.
- Two-strike runner/proof escalation rule.
- Vincent human-action notification.
- TaskGraph review-work materialization.

Key production milestones are recorded in the 2026-09-02 handoff.

The Software Architect model advises; deterministic Python owns task eligibility, claims, Issue
workflow, checkouts, routing, and mutation. Workers receive explicit task IDs.

## Strategic rules

```text
NO NEW PIPELINE FEATURE unless actual integration/game development proves it is needed.
```

- TaskGraph is structural/task authority.
- Managed GitHub Issues are durable operational/workflow authority.
- Git claims are short-lived race protection.
- START is never cached.
- Integration uncertainty fails closed as WAIT.
- HUMAN_REVIEW is only for real design/canon/task-authority ambiguity.
- Default live worker count remains conservative until real use justifies more.
- Scenario J remains deliberately pending; do not create a concurrency project just to make it
  green.

## NSC-042 specific context

`Tasks/NSC-042.yaml` is the active, concrete, single-agent task:
**Seamless Scalable Wall Tiling for Long Isometric Walls**.

The task implementation commit exists remotely at `2a486123...`. Human/runtime rebuilding exposed
that the generated Unity state is part of the deliverable. Delivery correctly stopped when the
validated checkout was dirty rather than falsely claiming the earlier commit was what Vincent
tested.

A larger reviewed branch at `473cf101...` implements generalized pre-handoff generation/hygiene,
but it grew to 11 files and is intentionally held. Do not merge it automatically.

The chosen next production change is the smaller builder-output capture rule above.

## Known operational hazards

- Historical context is never live authority.
- Do not `git add .` / `git add -A`; stage exact reviewed paths.
- Do not reset/clean a dirty task checkout by guesswork.
- Close Unity when deterministic Git validation/staging requires a stable workspace.
- Windows CRLF projection and exact-byte source tests have caused false failures before; use the
  repository's established CRLF-aware checks rather than editing unrelated files.
- GitHub CLI machine output is UTF-8 regardless of Windows locale.
- The orchestration controller runs on the Windows host; provider containers are bounded sub-jobs.
- Substantial provider jobs use the canonical `.claude-jobs` / `.codex-jobs` writable roots and
  print their job directory.
- After two failed runner/proof attempts, preserve state and switch to read-only diagnosis.
- Reuse canonical mutation APIs before inventing wrappers.

## Working method

```text
bounded implementation
-> deterministic/host validation
-> independent adversarial review
-> targeted correction
-> revalidation
-> guarded exact-path commit
-> deliberate integration
-> move on
```

Prefer one downloadable prompt/runner + exact SHA-256 + one PowerShell 5.1-safe guarded command +
a final `[DONE]`/`[RECOVERY]` report.

## Exact next action

> Verify current `main`, TaskGraph, NSC-042 branch/checkout, and managed Issue state. If the narrow
> builder-output integration is still pending, implement/review it from current `main` with the
> exact output boundary above. Then create/push the clean post-builder NSC-042 commit and validate
> that exact commit before delivery.

## Do not repeat

- Do not ask which of A/B/C finished; all three were integrated long ago in this session.
- Do not rerun old Gauntlet Phase A, the retired 10-worker wave, or old Stage-5 Slices 4-8.
- Do not redo accepted A/B/C reviews.
- Do not redo the resolved UTF-8, host-controller, CRLF-validation, or real-adapter investigations
  without new evidence.
- Do not merge the broad `473cf101...` branch by default.
- Do not use the superseded `Generated/ArchitecturalTiles/**`-only builder boundary.
