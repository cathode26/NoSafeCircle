# ADR-043: Generic Selection Retry and Decomposition as Orchestrator Work

- Status: Accepted
- Date: 2026-08-25
- Scope: Human-authorized ChatGPT task selection/orchestration

## Context

The repository now contains enough committed task-state, task-contract, GitHub Issue coordination, and checkout/delivery guidance that a human can reasonably say:

> Go pick a task and start on it.

The previous selection documentation explained how to discover `not_delivered` implementation work and how to release a claimed task, but it did not explicitly require a generic task-picking orchestrator to continue trying other candidates when its first choice was unavailable or genuinely blocked.

The persistent graph also already distinguishes fully designed but oversized work through `execution_scope: needs_execution_decomposition` and other decomposition-relevant execution states. Stage D1B.1 can safely produce read-only review artifacts for such parents, but generic task-selection guidance treated only implementation as selectable work.

## Decision

A generic human instruction to pick/start work authorizes the orchestrator to select one bounded unit of work from two operational work types:

1. **fresh implementation work** against an existing undelivered concrete executable TaskGraph contract;
2. **decomposition work** against an existing active decomposition-relevant TaskGraph parent using the existing Progressive Decomposer.

`decomposition` is an orchestrator work type, not a new TaskGraph `kind`. Durable TaskGraph kinds remain `feature`, `artifact`, and `implementation`. The act of decomposing an existing parent does not receive a fabricated `NSC-###` product-work ID.

For generic selection, the orchestrator uses a retry loop. If a candidate is unavailable or unsuitable before claim, it records/skips the reason and tries the next sensible candidate. If a claimed candidate reaches a genuine hard blocker that cannot be resolved within its bounded authority/repair budget, the orchestrator follows the release procedure, refreshes current state, and tries another candidate.

Ordinary implementation difficulty is not a reason to task-hop. Compilation failures, test failures, and bounded repair remain part of the selected task's normal execution/GER/validation loop.

A successful Stage D1B.1 `review_ready` result completes the **decomposition work unit** even when the semantic result is `needs_artifact` or `needs_human`. It does not mean the parent implementation is delivered.

## Decomposition authority boundary

Generic task-picking authorization permits choosing and running an eligible D1B.1 decomposition proposal. It does not expand D1B.1 authority:

- source remains read-only;
- outputs remain review-only and immutable;
- proposed child contracts / `graph_delta.json` are not automatically applied;
- Stage D1C reusable graph application remains unimplemented;
- decomposition does not establish dependency readiness, dispatch authority, delivery, conformance, or merge authority;
- missing design still routes to `needs_artifact` / `needs_human` rather than silent invention.

Eligibility remains governed by the production decomposition preflight (`Pipeline/TaskDecomposition/context_builder.py::validate_task_selection`), not by prose alone.

## GitHub coordination

Decomposition work claims the GitHub Issue for the existing parent NSC contract and identifies `work_type: decomposition` in the Claim / Planned Approach. No fake TaskGraph ID is created merely for decomposition.

Review-ready decomposition output is recorded in a Decomposition Closeout comment with the parent contract/source identity, run/provider identity, decision, artifact paths, proposal summary, and explicit review-only/no-apply statement.

## Retry termination

For a generic task-picking instruction, candidate selection continues until either:

1. a viable work unit is successfully started; or
2. the sensible safe candidate pool is exhausted and concrete blockers requiring human intervention are reported.

The retry/substitution rule does not apply when the human explicitly names the task to work on. An explicit request such as `Work on NSC-042` must not silently switch to another NSC task.

## Consequences

- A fresh ChatGPT instance can recover from a poor first candidate without requiring another human prompt.
- Progressive decomposition becomes productive selectable work instead of a separate manually remembered activity.
- The pipeline still prefers just-in-time decomposition rather than decomposing the entire backlog speculatively.
- Existing TaskGraph schema and product-work kinds remain unchanged.
- Human review/application boundaries for decomposition remain unchanged.
- Generic task selection is still human-directed: the human authorizes the selection policy at the work-category level even when the orchestrator chooses the concrete NSC candidate.
