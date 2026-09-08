# Accept the scheduler's integration-gate wake in the outer controller

The independent defect is a wait-result contract mismatch. A successful poll can be followed by a valid gate wake that the outer controller rejects. It does not require a synthetic-evidence race or a malformed receipt.

## Exact causal chain at base 120ec005304508383db651985bceeb975d10bba2

1. `PollingOrchestrator._wait_for_architect_activity()` (`polling_orchestrator.py:2091`) checks active workers, clears the worker event and checks the gate listener's pending flag. When set, it clears that flag and returns `integration_gate_released` (`:2104`). This return precedes `architect_wait_started`, so the journal need not contain a wait-start event.
2. `AutonomousGraphController._step_in_refresh_scope()` (`autonomous_graph_run.py:2006`) calls that method after a quiet successful poll. Its accepted wake set (`:2007`) contains only `worker_returned` and `issue_state_changed`; `fallback_elapsed` is handled separately. The else branch (`:2023`) raises `AutonomousGraphRunError: scheduler returned unsupported wait reason: 'integration_gate_released'`.
3. `run()` catches `BaseException` (`:2100`), enters `drain_active_workers()` (`:2106`) and only then re-raises. It emits no exception event first. The active worker survives, while admissions remain stopped during the drain. Later successful worker completion, gate release and another valid wake cannot undo the already-selected exception path.

An earlier gate notification can remain pending until the first quiet step.
Deterministic regressions exercise this ordering without using live run artifacts.

## Every post-poll operation before another step

References below are to the same exact base, in `autonomous_graph_run.py` unless stated otherwise.

| Operation | Location and possible failure |
| --- | --- |
| Finalize poll counters | `_poll():1818` always calls `_persist_poll_accounting():1793` in `finally`; malformed counters, a regressing counter or progress-store failure can raise after the scheduler's completed event. |
| Validate poll result | `_step_in_refresh_scope():1931` reads status and requires a boolean fatal flag. Invalid shape raises. |
| Re-observe and evaluate | `:1935`, `_snapshot():1569`, `_evaluate_snapshot():1597`; snapshotter/backend failures and wrong snapshot type can raise. Unsafe graph state becomes blocked, including inconsistent active assignments. |
| Terminal result | `_terminal_result():1859` saves progress and, for completion, constructs the exact receipt. Store/receipt failures can raise. A blocked state itself is a terminal classification. |
| Check and run post-poll pump | `:1959`, `_eligible_synthetic_handoffs():1663`, `_pump_and_reobserve():1735`; only if no pre-poll mutation and eligible handoffs exist. Pump exceptions or invalid result types propagate. A returned mutation is checked against a fresh snapshot, event ID, state version and evidence hash; unproven progress becomes blocked. Admission scope is then refreshed. |
| Progress/deadlock handling | `:1970` compares fingerprints, detects repeated internal stall, replaces progress and calls `_save():1524`. Store failures and counter regression can raise. A mutation, launch or changed fingerprint returns immediately for another observation. |
| Choose wait budget | `_progress_wait_budget():1708` uses pending transitions to select bounded settling or fallback. This does not authorize a transition. |
| Wait and interpret result | `:2006-2025`; this is the proven mismatch. `integration_gate_released` raises despite representing a successful notification. |
| Save post-wait counters | `:2026` calls `_save()` and returns the step result. |
| Leave refresh scope | `_step():1891`, its `finally` at `:1911` ends the bounded source-refresh scope. Errors here also propagate. |
| Outer terminal handling | `run():2036` may drain a terminal stop, save a completion receipt and record the completion timeline. None is required before the next ordinary nonterminal step. |

The production synthetic pump already excludes locally active workers and gate owners. The regression invokes the real outer controller and real scheduler wait while the real integration-window fixture reports `automated_exact_commit_validation` with an active Unity operation. It confirms the pump does not seize that worker's handoff. The worker fixture then finishes exact-commit validation and releases its gate. No recoverable-transition exception handler is needed for this defect.

## Separate fix and regression

The controller now treats `integration_gate_released` as a wake: increment the wake count, clear the fallback fingerprint, then re-observe normally. The notification grants no admission, ownership, completion or PASS authority. Unknown wait strings still raise, drain and re-raise. Worker drain behavior is unchanged.

Before an exceptional drain, `autonomous_run_error` records the exception type, bounded/redacted message and stage to the run timeline and scheduler event journal. Existing best-effort timeline writes and narrow event-write error handling preserve the original exception and worker supervision if telemetry storage fails. No operational exception is swallowed. Storage failure can still make a journal unavailable; the implementation does not claim guaranteed durability on an unwritable disk.

`tests/autonomous_gate_wake_smoke_test.py` uses `NSC_GATE_WAKE_SOURCE` to run unchanged expectations against the exact base. It exercises the real controller/wait path, the integrated-main -> revalidation-pending -> active exact-validation sequence, an unexpected snapshot failure with a durable error before drain and exact exception re-raise, unknown wait results, message redaction/bounding and a journal-write failure. These are component/regression tests using local Git and deterministic worker/Unity boundaries, not Unity acceptance tests.

This patch has no implementation-file overlap with the architect-resume change. One concerns the scheduler's admission decision; the other concerns the controller's interpretation of a wait result. They should remain separate commits. Live artifacts were read only; no live checkout, Issue, PR, claim, gate, container or process was changed.
