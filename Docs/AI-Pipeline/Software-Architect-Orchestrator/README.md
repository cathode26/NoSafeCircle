# Software Architect Orchestrator

**Status:** Design packet for the current operating model. Design guidance only — not
game-design canon, not TaskGraph authority, and not evidence that any described behavior
is merged.

**Base commit:** `fa5da9f03343e457af042598bfb83526926123e5` (branch
`orchestrator/polling-architect-v1`). The Polling Orchestrator + Architect implementation
described as "implemented now" exists as uncommitted files on that branch.

## Executive summary

One explicitly operator-started, supervised polling **software architect** is the chosen
bounded scheduler for No Safe Circle work. The implementation remains uncommitted and
under review on this branch. It observes deterministic TaskGraph and durable workflow
state, reasons about integration conflicts, decides when a task is too broad to hand to
one worker, and launches workers with exact explicit task IDs.

Workers execute assigned work. They do not normally self-select.

```text
OLD MODEL (retired)                     NEW MODEL (current)
-------------------                     -------------------
N generic workers                       1 supervised polling architect
each polls Stage 2 itself               Stage 2 answers only the architect
each claims fresh work by Git CAS       architect assigns exact --task-id
conflicts resolved by racing            conflicts avoided before launch
decomposition = another work type       decomposition = an architect decision
  competing in the same queue             inside one graph-mutation section
10-worker self-selection wave            single-architect live proof
```

Git CAS claims, exclusive-resource claims, and durable Issue authority are **kept**. They
stop being the normal way fresh work is allocated and become defense in depth against a
second scheduler, a stale or manual worker, another machine, or operator error.

## Why the model changed

- Stages 1-4 already proved deterministic eligibility, claims, and durable Issue
  authority, and the private Gauntlet proved both resume/human-hold behavior (Phase A) and
  a real simultaneous fresh-claim race with at most one winner, a typed loser, safe
  replan, no duplicate Issues, and no leaked claims (Phase B). Racing works. It is simply
  not the cheapest way to get *clean* parallelism.
- A won race still produces two branches that must merge. Unity scenes, prefabs, and
  ScriptableObjects are not merge-safe integration surfaces
  (`CLAUDE.md`, `Docs/Engineering/ENGINEERING_STANDARDS.md`), so the expensive failure is
  not "two workers claimed the same task"; it is "two workers each edited the same scene."
- Avoiding that requires reasoning about likely change surfaces *before* launch. That is a
  judgment, and it belongs to one component that can see all in-flight work — not to N
  independent self-selecting workers that each see only their own candidate.

The scheduling objective is therefore **clean parallelism, not worker utilization**. An
idle slot costs nothing durable. A merge conflict in `Assets/Scenes/*.unity` costs a human.

## The WAIT rule

If there is meaningful uncertainty about whether a candidate can run concurrently without
causing a merge or integration conflict: **WAIT**.

A WAIT is not an error and not a human question. It excludes one candidate for one
scheduling pass and mutates nothing. Current actual paths are still re-read and checked on
every poll. Paid re-analysis is reused for an identical stable input and is additionally
bounded by the per-task cooldown; reservation membership/identity changes invalidate the
fingerprint, while irrelevant growth of an active worker's exact changed-path set does
not.

HUMAN_REVIEW is reserved for genuine design/canon authority ambiguity that the architect
names explicitly. Ordinary merge-conflict uncertainty, low confidence, unknown risk, and
insufficient evidence never reach a human.

Full policy, including the per-pair rule that prevents one partially observable branch
from deadlocking the repository, is in
[`CONFLICT_AND_DECOMPOSITION_MODEL.md`](./CONFLICT_AND_DECOMPOSITION_MODEL.md).

## Current implementation status

Status language in this packet is deliberate. "Implemented now" means the code exists on
this branch; it does not mean merged, reviewed, or live-proven.

| Capability | Status |
| --- | --- |
| Polling scheduler singleton (OS-backed non-blocking lock, no TTL stealing) | **Implemented now** (uncommitted, this branch) |
| One poll-scoped Stage-2 authority observation: resume first, then Stage-2-ranked fresh candidates | **Implemented now** |
| Integration reservation observation (scheduler children + durable incomplete workflows) | **Implemented now** |
| Read-only architect preflight through AgentRuntime with `WriteBoundaries((), ())` | **Implemented now** |
| Deterministic hard-conflict detection (resources, actual paths, Unity serialized assets) | **Implemented now** |
| Uncertainty ⇒ WAIT, narrow HUMAN_REVIEW, stable WAIT cache, per-task cooldown | **Implemented now** |
| Per-poll and cumulative per-session architect invocation caps | **Implemented now** |
| Bounded transient reservation-observation retry | **Implemented now** |
| Shared-checkout-root singleton lock across source clones | **Implemented now** |
| Exact `--task-id` / unique `--worker-id` worker launch, one per poll, argv `shell=False` | **Implemented now** |
| Stage-5 Slice 1 deterministic D1C planner/preflight | **Implemented locally elsewhere; pending integration** — not present in this checkout |
| Stage-5 Slice 2 local transactional materialization | **Implemented locally elsewhere / in review; pending integration** — not present in this checkout |
| Stage-5 Slice 3 standalone `apply_graph_delta()` | **Planned next** |
| Architect-driven decomposition (propose → validate → authorize → apply) | **Planned next** |
| 10-worker decentralized self-selection wave | **Retired design** |
| Distributed decomposition dispatcher/queue and multi-task atomic claims | **Retired/deferred design** — see the slice reassessment |

## What stays deterministic

The LLM architect never becomes authority. These remain deterministic Python and Git:

- TaskGraph contracts and `task_contract_sha256` identity;
- Stage-2 eligibility, ranking, and resume-first priority;
- durable Issue workflow state and its hash-chained events;
- claim and lease state;
- source HEAD and actual changed paths;
- `GraphDeltaPlan` hashes, decomposition validators, and D1C application;
- the admission decision itself: START, WAIT, and HUMAN_REVIEW are computed by Python from
  the advisory, not chosen by the model.

## What the LLM architect does

Advisory only, inside a read-only repository boundary:

- predicts the likely change surface (paths, Unity serialized assets, symbols, systems);
- estimates integration risk and states honest confidence;
- suggests interfaces and seams that would reduce coupling;
- proposes decomposition when one assignment is too broad or architecturally unsafe;
- names a design/canon question when one genuinely exists.

Its suggestions for resources, dependencies, TaskGraph changes, and decomposition are
recorded as `advisory_only_not_applied` artifacts. Nothing is applied by the scheduler.

## V1 operating bounds and known limitation

- Default `max_workers` is **1**. The first live acceptance proof must keep it at 1;
  raising it requires that proof to accept the Software Architect conflict gates.
- Default polling interval is **60 seconds**, matching the cost of GitHub/TaskGraph/Git
  observation rather than pretending it is a five-second local check.
- Default architect provider is `claude`; absent an explicit `--architect-model`, the
  configured ArchitectureReview synthesis model is used (currently
  `ARCH_REVIEW_SYNTHESIS_MODEL`, falling back to `claude-sonnet-5`). Codex may be selected
  explicitly and currently falls back to `gpt-5.6-sol` through the same setting.
- A nonzero worker process exit still stops the scheduler fail-closed. A benign exact-task
  admission race can currently make `run_pipeline_agent.py` exit 2, because that file has
  no distinct "declined before mutation" result/exit contract. V1 treats the stop as safe
  but fragile; it does not parse stderr or invent retry behavior. A future cross-file
  change must add the typed worker outcome before retry is considered.
- HUMAN_REVIEW decisions remain in-memory advisory state in v1. Durable persistence is a
  pre-live-proof follow-up, not authority added in this pass.

## Documents

```text
README.md                            — this file
ARCHITECTURE_AND_AUTHORITY.md        — control loop, authority split, restart/recovery
CONFLICT_AND_DECOMPOSITION_MODEL.md  — WAIT policy, change surfaces, decomposition flow
IMPLEMENTATION_SEQUENCE.md           — bounded slices after Stage-5 Slice 3
```

The historical Stage-5 packet remains at
[`../Stage5-Decomposition-Design/`](../Stage5-Decomposition-Design/README.md). Its Slices
1-3 remain the deterministic D1C foundation; its Slices 4-8 are reassessed here.
