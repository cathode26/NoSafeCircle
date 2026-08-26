# ADR-035 — Round-Robin Decomposition Verification and Refinement

## Status

Accepted for implementation on `pipeline/d1b2-round-robin-decomposition`.

## Context

Stage D1B.1 invokes one read-only `task_decomposer`, validates its structured result deterministically, and emits review-only artifacts. The deterministic layers can prove schema validity, complete parent requirement coverage, dependency existence, graph acyclicity, aggregate semantics, and source immutability.

Those checks cannot reliably decide semantic ownership questions such as:

- whether a proposed child duplicates work already owned by another contract;
- whether integration work is hidden or unnecessarily split into a bookkeeping task;
- whether a completion gate depends on downstream authored content;
- whether an inbound dependency was rewritten to the correct child capability;
- whether the proposed child set is minimal, bounded, and collectively sufficient to complete the parent feature.

The NSC-016 decomposition runs demonstrated this gap. Structurally valid proposals still required human semantic review to identify questionable Chapel-validation ownership and task boundaries.

## Decision

Add Stage D1B.2 as a separate, bounded round-robin decomposition review/refinement circuit. Preserve D1B.1 unchanged as the one-provider proposal command.

D1B.2 uses two or more provider positions, with the initial production default:

```text
Codex authors
    ↓
deterministic validation
    ↓
Claude reviews or revises
    ↓
deterministic validation after any revision
    ↓
Codex reviews or revises
    ↓
...
```

The control rule is:

> The provider that most recently authored or revised the current candidate may not approve that candidate.

An independent reviewer has exactly three verdicts:

- `pass` — accept the current candidate without changing it;
- `revise` — emit structured findings plus a complete replacement decomposition candidate;
- `needs_human` — stop because approved contracts or canon do not support a safe correction.

If a reviewer revises, that reviewer becomes the latest candidate author. The next provider in the rotation must independently review the new candidate.

## Deterministic validation between every model call

Every generated or revised decomposition candidate must pass the existing deterministic D1A boundaries before it becomes the current candidate:

- decomposition-result structural contract;
- decomposition semantic policy;
- complete parent AC/VAL/INT coverage;
- graph-delta planning when `decision=decomposed`;
- full proposed TaskGraph validation;
- decomposed-aggregate semantic validation;
- exact source identity revalidation.

A model never reviews an accepted current candidate that failed those deterministic checks. A reviewer revision that fails them is rejected and never replaces the prior candidate.

## Structured findings and resolution history

Review findings are immutable artifacts with:

- a globally unique round-owned finding ID;
- severity (`blocking` or `advisory`);
- semantic category;
- affected existing/proposed contracts;
- a concrete problem statement;
- the required resolution.

Each later review must explicitly address every unresolved blocking finding as one of:

- `resolved`;
- `withdrawn`;
- `still_blocking`.

A persistent defect keeps its original finding ID. Reviewers must not manufacture a duplicate new finding merely because the same issue remains blocking after another revision.

`pass` is valid only when:

- the reviewer is not the current candidate author;
- the candidate passes all deterministic validation;
- no new blocking finding is introduced;
- every prior blocking finding is resolved or withdrawn.

The system does not use majority voting. The acceptance condition is one independent PASS on the current, deterministically valid candidate with no unresolved blocking findings.

## Bounded circuit breaker

The default maximum is four AI calls:

```text
1. initial author
2. independent reviewer/reviser
3. independent reviewer/reviser
4. independent reviewer/reviser
```

The run stops earlier on independent PASS or `needs_human`.

If the call limit ends immediately after a revision, the result is `needs_human`. The latest author cannot approve its own candidate, and an unreviewed final revision cannot become `review_ready`.

The maximum is configurable within deterministic bounds, but the loop must never run indefinitely.

## Provider-neutral rotation

The runner accepts an ordered provider list while initially supporting the existing `codex` and `claude` adapters. Adjacent positions, including the cycle boundary, must be distinct. Provider bundles are validated before a run directory is published.

The production Compose service mounts both provider configuration volumes while preserving:

- `/workspace` as physically read-only;
- a filesystem-disjoint external decomposition output as the only task-associated writable mount;
- no repository-write or command-execution capability for any round.

## Artifacts

D1B.2 produces one immutable no-overwrite run directory containing:

- exact source/context identity;
- one TaskExecution/AgentRuntime result per round;
- each candidate and deterministic graph delta;
- each structured review and finding-resolution record;
- round summaries and progress telemetry;
- a final run result.

Root-level `decomposition_result.json` and `graph_delta.json` are published only after independent PASS. `needs_human`, `rejected`, and `agent_failed` runs retain diagnostic round artifacts but publish no approved root candidate.

All artifacts remain:

```text
review_only_not_applied
```

## Authority boundary

D1B.2 does not apply TaskGraph changes, create implementation authority, prove delivery/conformance, or replace human graph-application authority. D1C persistent graph application remains a separate stage.

A `review_ready` D1B.2 result means:

- the current candidate passed deterministic validation;
- a provider other than its latest author independently passed it;
- no blocking finding remains unresolved.

It is still a review artifact requiring the existing human/application boundary.

## Compatibility

The D1B.1 CLI and artifact layout remain supported and unchanged for one-provider diagnosis/proposal work. D1B.2 uses a separate CLI and run mode so prior immutable D1B.1 artifacts remain interpretable and are never silently upgraded.
