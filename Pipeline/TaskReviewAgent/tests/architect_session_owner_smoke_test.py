#!/usr/bin/env python3
"""Pure component tests for the durable polling-architect session owner.

Classification: pure/component and temporary-filesystem regression tests.
These tests use fake architect calls and temporary lifecycle artifacts. They do
not contact a provider, Docker, GitHub, Git, Unity, or a live repository.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.session_lifecycle import SessionLifecycleState  # noqa: E402
from Pipeline.TaskReviewAgent.architect_session_owner import (  # noqa: E402
    ArchitectSessionCompatibility,
    ArchitectSessionIdentityError,
    ArchitectSessionInvocationError,
    ArchitectSessionOwner,
    ArchitectSessionOwnerError,
    JsonArchitectSessionStore,
)


PROVIDER = "claude-code"
ROLE = "polling_architect"
SESSION_A = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
SESSION_B = "9c858901-8a57-4791-81fe-4c455b099bc9"
COMPATIBILITY = ArchitectSessionCompatibility(
    PROVIDER,
    ROLE,
    "claude-sonnet-fixture",
    None,
    "architect-protocol-fixture-v1",
    ("repository_read", "repository_search"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException] = ArchitectSessionOwnerError) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


class FakeArchitectRunner:
    def __init__(
        self,
        actions: list[Any] | None = None,
        *,
        compatibility: ArchitectSessionCompatibility = COMPATIBILITY,
    ) -> None:
        self.actions = list(actions or [])
        self.bindings: list[Any] = []
        self.compatibility = compatibility

    def __call__(self, **values: Any) -> Any:
        binding = values.pop("session_binding")
        self.bindings.append(binding)
        action = self.actions.pop(0) if self.actions else {}
        if isinstance(action, BaseException):
            raise action
        confirmation = binding.confirm(binding.session_id)
        metadata = {
            "provider_session_confirmation": confirmation.to_dict(),
            "provider_session_compatibility": self.compatibility.to_dict(),
            **dict(action),
        }
        return SimpleNamespace(invocation_metadata=metadata, marker=len(self.bindings))


def owner(root: Path, runner: FakeArchitectRunner, ids: list[str] | None = None) -> ArchitectSessionOwner:
    values = iter(ids or [SESSION_A, SESSION_B])
    return ArchitectSessionOwner(
        architect_runner=runner,
        provider_identifier=PROVIDER,
        role=ROLE,
        store=JsonArchitectSessionStore(root),
        compatibility=COMPATIBILITY,
        session_id_factory=lambda: next(values),
    )


def test_ninety_nine_to_one_hundred_retires_after_returning_result_then_rotates() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        store = JsonArchitectSessionStore(root)
        store.save_initial(
            replace(
                SessionLifecycleState.create(
                    provider_identifier=PROVIDER,
                    role=ROLE,
                    session_id=SESSION_A,
                    session_class="architect",
                ),
                sequence=198,
                completed_assignments=99,
                architect_completed_admission_cycles=99,
            ),
            COMPATIBILITY,
        )
        runner = FakeArchitectRunner()
        managed = owner(root, runner, ids=[SESSION_B])
        last = managed(candidates=(), source_head="1" * 40)
        require(last.marker == 1, "the boundary result was not returned")
        require(managed.state is not None and managed.state.phase == "retired", "100th cycle did not retire")
        require(
            managed.state.architect_completed_admission_cycles == 100,
            "completed cycle count is wrong",
        )
        require(runner.bindings[0].session_id == SESSION_A, "session changed before retirement")

        next_result = managed(candidates=(), source_head="2" * 40)
        require(next_result.marker == 2, "new-session result was not returned")
        require(runner.bindings[-1].mode == "start", "replacement session did not start fresh")
        require(runner.bindings[-1].session_id == SESSION_B, "replacement identity is wrong")
        require(managed.state is not None and managed.state.architect_completed_admission_cycles == 1, "new budget did not restart")


def test_completed_wait_batch_counts_as_one_completed_cycle() -> None:
    with tempfile.TemporaryDirectory() as text:
        runner = FakeArchitectRunner()
        managed = owner(Path(text), runner)
        require(managed.state is None, "constructing an idle owner created budget state")
        result = managed(candidates=(), source_head="1" * 40)
        require(result.marker == 1, "valid WAIT-like result was lost")
        require(managed.state is not None and managed.state.architect_completed_admission_cycles == 1, "valid batch was not counted")


def test_failure_streak_resets_and_two_provider_or_output_failures_retire() -> None:
    with tempfile.TemporaryDirectory() as text:
        runner = FakeArchitectRunner(
            [
                ArchitectSessionInvocationError("provider_failure", "provider_error", None, "first"),
                {},
                ArchitectSessionInvocationError("output_failure", "schema_error", SESSION_A, "third"),
                ArchitectSessionInvocationError("provider_failure", "timeout", None, "fourth"),
            ]
        )
        managed = owner(Path(text), runner)
        rejects(lambda: managed(candidates=()), ArchitectSessionInvocationError)
        require(managed.state.consecutive_provider_output_failures == 1, "first failure not counted")
        managed(candidates=())
        require(managed.state.consecutive_provider_output_failures == 0, "success did not reset streak")
        rejects(lambda: managed(candidates=()), ArchitectSessionInvocationError)
        require(managed.state.phase == "between_assignments", "one output failure retired early")
        rejects(lambda: managed(candidates=()), ArchitectSessionInvocationError)
        require(managed.state.phase == "retired", "two consecutive failures did not retire")
        require(managed.state.architect_completed_admission_cycles == 1, "failed calls counted as completed cycles")


def test_identity_and_incompatibility_retire_immediately() -> None:
    for outcome in ("identity_failure", "session_incompatibility"):
        with tempfile.TemporaryDirectory() as text:
            runner = FakeArchitectRunner(
                [ArchitectSessionInvocationError(outcome, "schema_error", None, outcome)]
            )
            managed = owner(Path(text), runner)
            rejects(lambda: managed(candidates=()), ArchitectSessionInvocationError)
            require(managed.state.phase == "retired", f"{outcome} did not retire")
            require(managed.state.retirement_reason == outcome, f"wrong {outcome} reason")

    with tempfile.TemporaryDirectory() as text:
        class MismatchedRunner(FakeArchitectRunner):
            def __call__(self, **values: Any) -> Any:
                binding = values.pop("session_binding")
                self.bindings.append(binding)
                confirmation = {
                    **binding.confirm(binding.session_id).to_dict(),
                    "session_id": SESSION_B,
                }
                return SimpleNamespace(
                    invocation_metadata={
                        "provider_session_confirmation": confirmation,
                    }
                )

        runner = MismatchedRunner()
        managed = owner(Path(text), runner)
        rejects(lambda: managed(candidates=()), ArchitectSessionIdentityError)
        require(managed.state.phase == "retired", "mismatched success did not retire")
        require(managed.state.retirement_reason == "identity_failure", "wrong mismatch reason")


def test_context_is_unknown_unless_explicit_and_exact_threshold_retires() -> None:
    with tempfile.TemporaryDirectory() as text:
        runner = FakeArchitectRunner([{}, {"known_context_window_percent": 69}, {"known_context_window_percent": 70}])
        managed = owner(Path(text), runner)
        managed(candidates=())
        require(managed.state.known_context_window_percent is None, "unknown context was estimated")
        managed(candidates=())
        require(managed.state.phase == "between_assignments", "69 percent retired")
        managed(candidates=())
        require(managed.state.phase == "retired", "70 percent did not retire")


def test_latency_metadata_is_ignored_without_exact_comparable_sample_provider() -> None:
    with tempfile.TemporaryDirectory() as text:
        metadata = {
            "duration_seconds": 20.0,
            "latency_comparison_key": "portfolio",
            "latency_baseline_milliseconds": 1,
        }
        runner = FakeArchitectRunner([metadata, metadata, metadata])
        managed = owner(Path(text), runner)
        for _ in range(3):
            managed(candidates=())
        require(managed.state.phase == "between_assignments", "untrusted latency metadata retired")
        require(managed.state.latency_degraded_sample_count == 0, "untrusted latency formed a streak")


def test_persisted_assigned_or_corrupt_state_blocks_before_provider_call() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        store = JsonArchitectSessionStore(root)
        assigned = replace(
            SessionLifecycleState.create(
                provider_identifier=PROVIDER,
                role=ROLE,
                session_id=SESSION_A,
                session_class="architect",
            ),
            phase="assigned",
            sequence=1,
            active_assignment_id="architect-cycle-1",
            active_workload_class="admission_cycle",
        )
        store.save_initial(assigned, COMPATIBILITY)
        runner = FakeArchitectRunner()
        rejects(lambda: owner(root, runner))
        require(not runner.bindings, "assigned recovery invoked a provider")

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        root.mkdir(parents=True, exist_ok=True)
        (root / "state.json").write_text('{"broken":true}\n', encoding="utf-8")
        runner = FakeArchitectRunner()
        rejects(lambda: owner(root, runner))
        require(not runner.bindings, "corrupt recovery invoked a provider")

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        store = JsonArchitectSessionStore(root)
        managed = owner(root, FakeArchitectRunner())
        managed(candidates=())
        store.state_path.unlink()
        runner = FakeArchitectRunner()
        rejects(lambda: owner(root, runner))
        require(not runner.bindings, "orphaned lifecycle journal invoked a provider")


def test_durable_state_and_append_only_transition_journal_are_exact() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        runner = FakeArchitectRunner()
        managed = owner(root, runner, ids=[SESSION_B])
        managed(candidates=())
        managed(candidates=())
        stored = JsonArchitectSessionStore(root).load()
        require(stored == managed.state, "durable state round trip changed facts")
        lines = (root / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
        require(len(lines) == 4, "start/finish transitions were not append-only")
        records = [json.loads(line) for line in lines]
        require([item["telemetry"]["sequence"] for item in records] == [1, 2, 3, 4], "journal sequence is wrong")
        require(records[-1]["state"] == managed.state.to_dict(), "journal did not bind resulting state")


def test_finish_record_failure_poisons_owner_before_any_retry_call() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        store = JsonArchitectSessionStore(root)
        original_record = store.record

        def fail_finished_record(transition: Any) -> None:
            if transition.telemetry.event == "assignment_completed":
                raise ArchitectSessionOwnerError("injected finish persistence failure")
            original_record(transition)

        store.record = fail_finished_record  # type: ignore[method-assign]
        runner = FakeArchitectRunner()
        managed = ArchitectSessionOwner(
            architect_runner=runner,
            provider_identifier=PROVIDER,
            role=ROLE,
            store=store,
            compatibility=COMPATIBILITY,
            session_id_factory=lambda: SESSION_A,
        )
        rejects(lambda: managed(candidates=()))
        require(len(runner.bindings) == 1, "fixture did not reach exactly one paid call")
        rejects(lambda: managed(candidates=()))
        require(len(runner.bindings) == 1, "poisoned owner made a second paid call")


def test_journal_interior_deletion_or_reordering_fails_closed() -> None:
    for mutate in ("delete", "reorder"):
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            managed = owner(root, FakeArchitectRunner())
            managed(candidates=())
            managed(candidates=())
            path = root / "telemetry.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            changed = (
                [lines[0], *lines[2:]]
                if mutate == "delete"
                else [lines[1], lines[0], *lines[2:]]
            )
            path.write_text("\n".join(changed) + "\n", encoding="utf-8")
            rejects(lambda: owner(root, FakeArchitectRunner()))


def test_assigned_state_is_durable_before_the_paid_callable_starts() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)

        class InspectingRunner(FakeArchitectRunner):
            def __call__(self, **values: Any) -> Any:
                observed = JsonArchitectSessionStore(root).load()
                require(observed is not None, "paid call began before state existed")
                require(observed.phase == "assigned", "paid call began before assigned state was durable")
                require(
                    observed.active_workload_class == "admission_cycle",
                    "paid call was not bound to an admission cycle",
                )
                return super().__call__(**values)

        managed = owner(root, InspectingRunner())
        managed(candidates=())
        require(managed.state is not None and managed.state.phase == "between_assignments", "call did not finish")


def test_clean_process_restart_resumes_the_exact_durable_session() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        first_runner = FakeArchitectRunner()
        owner(root, first_runner)(candidates=())

        second_runner = FakeArchitectRunner()
        resumed = ArchitectSessionOwner(
            architect_runner=second_runner,
            provider_identifier=PROVIDER,
            role=ROLE,
            store=JsonArchitectSessionStore(root),
            compatibility=COMPATIBILITY,
            session_id_factory=lambda: (_ for _ in ()).throw(
                AssertionError("restart replaced a reusable exact session")
            ),
        )
        resumed(candidates=())
        require(second_runner.bindings[0].mode == "resume", "restart did not resume")
        require(second_runner.bindings[0].session_id == SESSION_A, "restart changed identity")


def test_restart_compatibility_changes_retire_before_a_fresh_paid_call() -> None:
    variants = (
        replace(COMPATIBILITY, model="claude-opus-fixture"),
        replace(COMPATIBILITY, reasoning_effort="high"),
        replace(COMPATIBILITY, protocol="architect-protocol-fixture-v2"),
        replace(COMPATIBILITY, capabilities=("repository_read",)),
    )
    for compatibility in variants:
        with tempfile.TemporaryDirectory() as text:
            root = Path(text)
            owner(root, FakeArchitectRunner())(candidates=())
            runner = FakeArchitectRunner(compatibility=compatibility)
            resumed = ArchitectSessionOwner(
                architect_runner=runner,
                provider_identifier=PROVIDER,
                role=ROLE,
                store=JsonArchitectSessionStore(root),
                compatibility=compatibility,
                session_id_factory=lambda: SESSION_B,
            )
            require(
                resumed.state is not None
                and resumed.state.phase == "retired"
                and resumed.state.retirement_reason == "session_incompatibility",
                "restart compatibility drift did not retire before the paid call",
            )
            resumed(candidates=())
            require(runner.bindings[0].mode == "start", "drift silently resumed")
            require(runner.bindings[0].session_id == SESSION_B, "drift reused old identity")


def test_returned_compatibility_mismatch_retires_the_bound_session() -> None:
    with tempfile.TemporaryDirectory() as text:
        runner = FakeArchitectRunner(
            compatibility=replace(COMPATIBILITY, model="claude-wrong-fixture")
        )
        managed = owner(Path(text), runner)
        rejects(lambda: managed(candidates=()))
        require(managed.state.phase == "retired", "returned compatibility drift did not retire")
        require(
            managed.state.retirement_reason == "session_incompatibility",
            "returned compatibility drift used the wrong retirement reason",
        )


def test_codex_fresh_pooling_fails_before_paid_call() -> None:
    with tempfile.TemporaryDirectory() as text:
        runner = FakeArchitectRunner()
        managed = ArchitectSessionOwner(
            architect_runner=runner,
            provider_identifier="openai-codex",
            role=ROLE,
            store=JsonArchitectSessionStore(Path(text)),
            compatibility=ArchitectSessionCompatibility(
                "openai-codex",
                ROLE,
                "gpt-fixture",
                "max",
                "architect-protocol-fixture-v1",
                ("repository_read", "repository_search"),
            ),
        )
        rejects(lambda: managed(candidates=()))
        require(not runner.bindings, "Codex started without a pre-call exact identity")


def test_session_rotation_keeps_the_same_scheduler_and_live_worker_table() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        store = JsonArchitectSessionStore(root)
        store.save_initial(
            replace(
                SessionLifecycleState.create(
                    provider_identifier=PROVIDER,
                    role=ROLE,
                    session_id=SESSION_A,
                    session_class="architect",
                ),
                sequence=198,
                completed_assignments=99,
                architect_completed_admission_cycles=99,
            ),
            COMPATIBILITY,
        )
        runner = FakeArchitectRunner()
        managed = owner(root, runner, ids=[SESSION_B])
        worker_process = object()
        active_assignments = {"NSC-901": worker_process}
        scheduler = SimpleNamespace(
            architect_runner=managed,
            active_assignments=active_assignments,
        )
        scheduler_identity = id(scheduler)
        assignment_identity = id(scheduler.active_assignments)
        scheduler.architect_runner(candidates=())
        scheduler.architect_runner(candidates=())
        require(id(scheduler) == scheduler_identity, "architect rotation replaced the scheduler")
        require(
            id(scheduler.active_assignments) == assignment_identity,
            "architect rotation replaced the live-worker table",
        )
        require(
            scheduler.active_assignments == {"NSC-901": worker_process},
            "architect rotation orphaned a live worker",
        )


TESTS = (
    test_ninety_nine_to_one_hundred_retires_after_returning_result_then_rotates,
    test_completed_wait_batch_counts_as_one_completed_cycle,
    test_failure_streak_resets_and_two_provider_or_output_failures_retire,
    test_identity_and_incompatibility_retire_immediately,
    test_context_is_unknown_unless_explicit_and_exact_threshold_retires,
    test_latency_metadata_is_ignored_without_exact_comparable_sample_provider,
    test_persisted_assigned_or_corrupt_state_blocks_before_provider_call,
    test_durable_state_and_append_only_transition_journal_are_exact,
    test_finish_record_failure_poisons_owner_before_any_retry_call,
    test_journal_interior_deletion_or_reordering_fails_closed,
    test_assigned_state_is_durable_before_the_paid_callable_starts,
    test_clean_process_restart_resumes_the_exact_durable_session,
    test_restart_compatibility_changes_retire_before_a_fresh_paid_call,
    test_returned_compatibility_mismatch_retires_the_bound_session,
    test_codex_fresh_pooling_fails_before_paid_call,
    test_session_rotation_keeps_the_same_scheduler_and_live_worker_table,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print("architect_session_owner_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
