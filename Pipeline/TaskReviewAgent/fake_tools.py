"""Deterministic fake pipeline tools for the first TaskReviewAgent vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import (
    CrewStatus,
    ExecutionRunObservation,
    ExecutionScopePlan,
    HumanReviewProof,
    ScopeValidationResult,
    TaskReviewContractError,
    validate_task_id,
)


@dataclass(frozen=True)
class FakeTaskFixture:
    task_id: str = "NSC-050"
    source_head: str = "5" * 40
    task_contract_sha256: str = "a" * 64
    candidate_sha256: str = "c" * 64

    @property
    def checkout_path(self) -> str:
        return rf"C:\NSC\NSC\{self.task_id}"

    @property
    def branch(self) -> str:
        return f"{self.task_id.casefold()}-task-review-fixture"

    @property
    def run_id(self) -> str:
        return f"{self.task_id.casefold()}-fake-run"

    @property
    def candidate_patch_path(self) -> str:
        return (
            rf"{self.checkout_path}\Pipeline\ExecutionCrew\outputs"
            rf"\{self.run_id}\candidate.patch"
        )

    @property
    def expected_scope(self) -> ExecutionScopePlan:
        return ExecutionScopePlan(
            existing_implementation_paths=(
                "Assets/NoSafeCircle/DoorPrototype/Scripts/DoorInteractable.cs",
                "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs",
            ),
            new_implementation_paths=(),
            existing_test_paths=(),
            new_test_paths=(
                "Assets/NoSafeCircle/DoorPrototype/Tests/DoorLockBreakPlayModeTests.cs",
            ),
        )


class FakeTaskReviewTools:
    """Stateful fake implementation of the approved TaskReviewAgent tool surface.

    The fake environment deliberately starts without a checkout. It also provides enough
    repository facts for a correct scope plan while allowing tests to submit and reject an
    incorrect existing/new classification before recovery.
    """

    def __init__(self, fixture: FakeTaskFixture | None = None) -> None:
        self.fixture = fixture or FakeTaskFixture()
        validate_task_id(self.fixture.task_id)
        self.checkout_ready = False
        self.accepted_plan_id: str | None = None
        self.last_run: ExecutionRunObservation | None = None
        self._proofs: dict[str, HumanReviewProof] = {}
        self.action_log: list[str] = []

    def observe_goal_state(self) -> dict[str, Any]:
        self.action_log.append("observe_goal_state")
        return {
            "schema_version": "1.0",
            "environment": {
                "ready": True,
                "controller_clean": True,
                "taskgraph_valid": True,
                "provider_auth_available": True,
            },
            "task": {
                "task_id": self.fixture.task_id,
                "contract_disposition": "active",
                "kind": "implementation",
                "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "derived_state": "not_delivered",
                "dependencies_conformant": True,
                "source_head": self.fixture.source_head,
                "task_contract_sha256": self.fixture.task_contract_sha256,
            },
            "checkout": {
                "status": "ready" if self.checkout_ready else "missing",
                "path": self.fixture.checkout_path if self.checkout_ready else None,
                "branch": self.fixture.branch if self.checkout_ready else None,
                "clean": self.checkout_ready,
            },
            "repository_scope_facts": {
                "existing_implementation_paths": list(
                    self.fixture.expected_scope.existing_implementation_paths
                ),
                "absent_test_paths": list(self.fixture.expected_scope.new_test_paths),
                "warning": (
                    "The listed test path is absent at source HEAD and must use "
                    "new_test_paths, not existing_test_paths."
                ),
            },
            "accepted_plan_id": self.accepted_plan_id,
            "execution_run": self.last_run.to_dict() if self.last_run is not None else None,
        }

    def prepare_task_checkout(self) -> dict[str, Any]:
        self.action_log.append("prepare_task_checkout")
        if self.checkout_ready:
            return {
                "status": "resumed",
                "path": self.fixture.checkout_path,
                "branch": self.fixture.branch,
                "source_head": self.fixture.source_head,
            }
        self.checkout_ready = True
        return {
            "status": "created",
            "path": self.fixture.checkout_path,
            "branch": self.fixture.branch,
            "source_head": self.fixture.source_head,
        }

    def validate_execution_scope(self, plan: ExecutionScopePlan) -> ScopeValidationResult:
        self.action_log.append("validate_execution_scope")
        if not self.checkout_ready:
            return ScopeValidationResult(
                accepted=False,
                reasons=("canonical task checkout must be ready before scope validation",),
                plan_id=None,
            )

        expected = self.fixture.expected_scope
        reasons: list[str] = []
        expected_new_test = set(expected.new_test_paths)
        proposed_existing_test = set(plan.existing_test_paths)
        misclassified = sorted(expected_new_test & proposed_existing_test)
        if misclassified:
            reasons.append(
                "test path is absent at source HEAD and must move from "
                f"existing_test_paths to new_test_paths: {misclassified}"
            )

        if plan.to_dict() != expected.to_dict() and not reasons:
            reasons.append("proposed scope does not match the task-owned fake repository surface")

        if reasons:
            return ScopeValidationResult(False, tuple(reasons), None)

        plan_id = f"scope-{plan.semantic_sha256[:16]}"
        self.accepted_plan_id = plan_id
        return ScopeValidationResult(True, (), plan_id)

    def run_execution_crew(self, plan_id: str) -> ExecutionRunObservation:
        self.action_log.append("run_execution_crew")
        if not self.checkout_ready:
            raise TaskReviewContractError("cannot run ExecutionCrew without a ready checkout")
        if plan_id != self.accepted_plan_id:
            raise TaskReviewContractError("ExecutionCrew requires the current validated plan_id")
        run = ExecutionRunObservation(
            run_id=self.fixture.run_id,
            task_id=self.fixture.task_id,
            crew_status=CrewStatus.REVIEW_READY,
            source_head=self.fixture.source_head,
            task_contract_sha256=self.fixture.task_contract_sha256,
            candidate_patch_path=self.fixture.candidate_patch_path,
            candidate_sha256=self.fixture.candidate_sha256,
            reasons=(),
        )
        self.last_run = run
        return run

    def verify_human_review_ready(self, run_id: str) -> HumanReviewProof:
        self.action_log.append("verify_human_review_ready")
        run = self.last_run
        if run is None or run.run_id != run_id:
            raise TaskReviewContractError("requested ExecutionCrew run does not exist")
        if run.crew_status is not CrewStatus.REVIEW_READY:
            raise TaskReviewContractError("ExecutionCrew run is not review_ready")
        proof = HumanReviewProof.create(
            task_id=run.task_id,
            run_id=run.run_id,
            source_head=run.source_head,
            task_contract_sha256=run.task_contract_sha256,
            candidate_patch_path=run.candidate_patch_path,
            candidate_sha256=run.candidate_sha256,
            apply_check_passed=True,
            source_unchanged=True,
            authority="review_only_not_applied",
        )
        self._proofs[proof.proof_id] = proof
        return proof

    def require_known_proof(self, proof: HumanReviewProof) -> None:
        expected = self._proofs.get(proof.proof_id)
        if expected is None:
            raise TaskReviewContractError("agent outcome references an unknown proof_id")
        if expected != proof:
            raise TaskReviewContractError("agent outcome proof bytes do not match minted proof")
