#!/usr/bin/env python3
"""Deterministic decomposition-authorization binder tests (A2 v1).

Classification: pure/component tests. Every fixture is built in memory from the
current D1B.2 round-robin run shape, a real ``DecompositionResult`` validated by
``TaskDecomposition.policy``, and a real ``GraphDeltaPlan`` produced by
``plan_graph_delta``. No repository file, Git ref, GitHub object, Unity asset, or
provider is touched.

These tests prove pipeline infrastructure invariants. They do not claim a Unity
task acceptance criterion or a completion gate.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.decomposition_authorization import (  # noqa: E402
    DECOMPOSITION_AUTHORIZATION_REASON_CODES,
    DECOMPOSITION_AUTHORIZATION_SCHEMA_VERSION,
    D1B2_DECOMPOSITION_RESULT_FILENAME,
    D1B2_GRAPH_DELTA_FILENAME,
    RECORD_AUTHORITY_FIELDS,
    RUNTIME_PROVIDER_IDENTIFIERS,
    DecompositionAuthorizationContractError,
    DecompositionAuthorizationDecision,
    DecompositionAuthorizationRecord,
    DecompositionAuthorizationStatus,
    authorization_record_sha256,
    validate_decomposition_authorization,
)
from TaskDecomposition.policy import validate_decomposition_result  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    _round_invocation_id,
    candidate_sha256,
)
from graph_delta import GraphDeltaPlan, plan_graph_delta  # noqa: E402
from graph_delta_smoke_test import (  # noqa: E402
    make_plan,
    replace_parent,
    validated_result,
)


MODULE_PATH = PIPELINE_ROOT / "TaskReviewAgent" / "decomposition_authorization.py"
LIVE_DECOMPOSITION_PATH = (
    PIPELINE_ROOT / "TaskDecomposition" / "live_decomposition.py"
)

TASK_ID = "NSC-042"
SOURCE_HEAD = "4a" * 20
EXACT_CONTRACT_SHA256 = hashlib.sha256(
    b"Tasks/NSC-042.yaml exact committed bytes"
).hexdigest()
RUN_ID = "nsc-042-d1b2-20260901t090000z-3f1c2ab49d70"
AUTHOR_PROVIDER = "codex"
REVIEWER_PROVIDER = "claude"
AUTHORIZER_LOGIN = "cathode26"
ALLOWLIST = ("cathode26",)
ARTIFACT_LOCATOR = (
    "C:\\Users\\VincentLiguori\\Downloads\\NoSafeCircleOutput\\NSC-042\\20260901-090000"
)
AUTHORIZED_AT = "2026-09-01T09:31:07Z"

DECOMPOSER_INVOCATION_ID = _round_invocation_id(TASK_ID, RUN_ID, 1, "task_decomposer")
REVIEWER_INVOCATION_ID = _round_invocation_id(
    TASK_ID, RUN_ID, 2, "decomposition_reviewer"
)
ROUND_THREE_INVOCATION_ID = _round_invocation_id(
    TASK_ID, RUN_ID, 3, "decomposition_reviewer"
)

# A round reports the AgentRuntime identity its logical provider actually runs
# as, never the logical D1B.2 name.
AUTHOR_RUNTIME_PROVIDER = RUNTIME_PROVIDER_IDENTIFIERS[AUTHOR_PROVIDER]
REVIEWER_RUNTIME_PROVIDER = RUNTIME_PROVIDER_IDENTIFIERS[REVIEWER_PROVIDER]

_PLAN = make_plan()
RESULT = validated_result(_PLAN)
GRAPH_DELTA = plan_graph_delta(_PLAN, RESULT.parent_task, RESULT)
CANDIDATE_SHA256 = candidate_sha256(RESULT)
PLAN_ID = GRAPH_DELTA.plan_id
PLAN_CANONICAL_SHA256 = hashlib.sha256(
    GRAPH_DELTA.canonical_json().encode("utf-8")
).hexdigest()
SEMANTIC_PARENT_SHA256 = RESULT.parent_task.contract_sha256


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def alternate_result() -> Any:
    """A second deterministically valid candidate with a different canonical SHA."""

    raw = RESULT.to_dict()
    raw["children"][0]["notes"] = "Alternate bounded implementation note."
    parent = next(task for task in _PLAN.tasks if task["id"] == TASK_ID)
    revised = validate_decomposition_result(
        raw, parent_task=parent, existing_reconciliation_keys=_PLAN.id_map
    )
    require(
        candidate_sha256(revised) != CANDIDATE_SHA256,
        "the alternate candidate must not share the reviewed candidate SHA",
    )
    return revised


def candidate_summary(**overrides: Any) -> dict[str, Any]:
    summary = {
        "version": 1,
        "author_provider": AUTHOR_PROVIDER,
        "sha256": CANDIDATE_SHA256,
        "decision": "decomposed",
        "graph_delta_plan_id": PLAN_ID,
    }
    summary.update(overrides)
    return summary


def round_artifact_paths(round_number: int, invocation_id: str) -> dict[str, str]:
    """The exact per-round artifact references the producer emits."""

    return {
        "task_execution_request_path": (
            f"rounds/{round_number:02d}/task_execution/{invocation_id}"
            "/task_request.json"
        ),
        "agent_runtime_result_path": (
            f"rounds/{round_number:02d}/agent_runtime/{invocation_id}/result.json"
        ),
    }


def advisory_finding() -> dict[str, Any]:
    return {
        "finding_id": "round-02-child-notes-wording",
        "severity": "advisory",
        "category": "task_granularity",
        "affected_contracts": ["runtime-integration"],
        "problem": "The integration child's notes could name the Unity component directly.",
        "required_resolution": "Optional wording improvement; not blocking.",
    }


def blocking_finding() -> dict[str, Any]:
    return {
        "finding_id": "round-02-completion-locality",
        "severity": "blocking",
        "category": "completion_locality",
        "affected_contracts": ["runtime-integration"],
        "problem": "The child completion gate requires a downstream authored scene.",
        "required_resolution": "Move the downstream proof to an integration obligation.",
    }


def history_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "round_number": 2,
        "reviewer_provider": REVIEWER_PROVIDER,
        "reviewed_candidate_sha256": CANDIDATE_SHA256,
        "verdict": "pass",
        "summary": "Independent reviewer confirms both children are locally completable.",
        "findings": [advisory_finding()],
        "prior_finding_resolutions": [],
    }
    entry.update(overrides)
    return entry


REVIEW_EVIDENCE_SHA256 = semantic_sha256(history_entry())


def decomposer_round(**overrides: Any) -> dict[str, Any]:
    summary = {
        "schema_version": "1.0",
        "round_number": 1,
        "role": "task_decomposer",
        "requested_provider": AUTHOR_PROVIDER,
        "actual_provider": AUTHOR_RUNTIME_PROVIDER,
        "actual_model": "gpt-5-codex",
        "agent_status": "succeeded",
        "agent_failure_classification": None,
        "duration_seconds": 412.51,
        "candidate_before": None,
        "candidate_after": candidate_summary(),
        "verdict": None,
        "new_finding_ids": [],
        "unresolved_finding_ids": [],
        **round_artifact_paths(1, DECOMPOSER_INVOCATION_ID),
        "status": "candidate_valid",
        "authority": "review_only_not_applied",
        "rejection_reasons": [],
    }
    summary.update(overrides)
    return summary


def reviewer_round(**overrides: Any) -> dict[str, Any]:
    summary = {
        "schema_version": "1.0",
        "round_number": 2,
        "role": "decomposition_reviewer",
        "requested_provider": REVIEWER_PROVIDER,
        "actual_provider": REVIEWER_RUNTIME_PROVIDER,
        "actual_model": "claude-opus-5",
        "agent_status": "succeeded",
        "agent_failure_classification": None,
        "duration_seconds": 288.04,
        "candidate_before": candidate_summary(),
        "candidate_after": None,
        "verdict": "pass",
        "new_finding_ids": ["round-02-child-notes-wording"],
        "unresolved_finding_ids": [],
        **round_artifact_paths(2, REVIEWER_INVOCATION_ID),
        "status": "independent_pass",
        "authority": "review_only_not_applied",
        "rejection_reasons": [],
    }
    summary.update(overrides)
    return summary


def d1b2_run(**overrides: Any) -> dict[str, Any]:
    run = {
        "schema_version": "1.0",
        "mode": "round_robin_d1b2",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "provider_order": [AUTHOR_PROVIDER, REVIEWER_PROVIDER],
        "max_calls": 4,
        "calls_used": 2,
        "source_identity": {
            "head_commit": SOURCE_HEAD,
            "head_tree": "7b" * 20,
            "branch": "main",
        },
        "task_execution_contract_identity": {
            "path": "Tasks/NSC-042.yaml",
            "revision": 3,
            "sha256": EXACT_CONTRACT_SHA256,
        },
        "d1a_semantic_parent_identity": {
            "task_id": TASK_ID,
            "contract_revision": 3,
            "contract_sha256": SEMANTIC_PARENT_SHA256,
        },
        "context_sha256": hashlib.sha256(b"synthetic context package").hexdigest(),
        "run_status": "review_ready",
        "decision": "decomposed",
        "latest_candidate": candidate_summary(),
        "independent_approver_provider": REVIEWER_PROVIDER,
        "decomposition_result_path": "decomposition_result.json",
        "graph_delta_path": "graph_delta.json",
        "rounds": [decomposer_round(), reviewer_round()],
        "finding_history": [history_entry()],
        "unresolved_findings": [],
        "rejection_reasons": [],
        "human_next_step": (
            "Review decomposition_result.json, graph_delta.json when present, and the "
            "per-round review history. No graph change has been applied."
        ),
        "duration_seconds": 701.92,
        "authority": "review_only_not_applied",
    }
    run.update(overrides)
    return run


def d1b1_run() -> dict[str, Any]:
    """Current D1B.1 single-provider proposal shape: no independent review."""

    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "requested_provider": AUTHOR_PROVIDER,
        "actual_provider": AUTHOR_PROVIDER,
        "actual_model": "gpt-5-codex",
        "source_identity": {
            "head_commit": SOURCE_HEAD,
            "head_tree": "7b" * 20,
            "branch": "main",
        },
        "task_execution_contract_identity": {
            "path": "Tasks/NSC-042.yaml",
            "revision": 3,
            "sha256": EXACT_CONTRACT_SHA256,
        },
        "d1a_semantic_parent_identity": {
            "task_id": TASK_ID,
            "contract_revision": 3,
            "contract_sha256": SEMANTIC_PARENT_SHA256,
        },
        "context_sha256": hashlib.sha256(b"synthetic context package").hexdigest(),
        "run_status": "review_ready",
        "agent_result_status": "succeeded",
        "agent_failure_classification": None,
        "decision": "decomposed",
        "decomposition_result_path": "decomposition_result.json",
        "graph_delta_path": "graph_delta.json",
        "task_execution_request_path": (
            f"task_execution/{DECOMPOSER_INVOCATION_ID}/task_request.json"
        ),
        "agent_runtime_result_path": (
            f"agent_runtime/{DECOMPOSER_INVOCATION_ID}/result.json"
        ),
        "rejection_reasons": [],
        "human_next_step": (
            "Review decomposition_result.json and graph_delta.json. No graph change "
            "has been applied."
        ),
        "duration_seconds": 402.7,
        "authority": "review_only_not_applied",
    }


def record_fields(**overrides: Any) -> dict[str, Any]:
    fields = {
        "schema_version": DECOMPOSITION_AUTHORIZATION_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "task_contract_sha256": EXACT_CONTRACT_SHA256,
        "source_head": SOURCE_HEAD,
        "decomposition_run_id": RUN_ID,
        "decomposition_result_sha256": CANDIDATE_SHA256,
        "graph_delta_plan_id": PLAN_ID,
        "graph_delta_canonical_sha256": PLAN_CANONICAL_SHA256,
        "reviewed_candidate_sha256": CANDIDATE_SHA256,
        "reviewer_kind": "independent_provider_review",
        "reviewer_provider": REVIEWER_PROVIDER,
        "reviewer_invocation_id": REVIEWER_INVOCATION_ID,
        "review_evidence_sha256": REVIEW_EVIDENCE_SHA256,
        "authorizer_login": AUTHORIZER_LOGIN,
        "authorization_state": "authorized",
        "authorized_at_utc": AUTHORIZED_AT,
        "artifact_locator": ARTIFACT_LOCATOR,
    }
    fields.update(overrides)
    return fields


def record(**overrides: Any) -> dict[str, Any]:
    """Build a self-consistent record; ``record_sha256`` is always recomputed."""

    fields = record_fields(**overrides)
    return {**fields, "record_sha256": authorization_record_sha256(fields)}


def decide(**kwargs: Any) -> DecompositionAuthorizationDecision:
    arguments: dict[str, Any] = {
        "record": record(),
        "d1b_run_result": d1b2_run(),
        "decomposition_result": RESULT,
        "graph_delta": GRAPH_DELTA,
        "authorized_authorizers": ALLOWLIST,
    }
    arguments.update(kwargs)
    decision = validate_decomposition_authorization(**arguments)
    require(
        type(decision) is DecompositionAuthorizationDecision,
        "the binder must return a typed decision",
    )
    require(
        all(
            code in DECOMPOSITION_AUTHORIZATION_REASON_CODES
            for code in decision.reason_codes
        ),
        f"reason codes must stay in the closed vocabulary: {decision.reason_codes}",
    )
    require(
        decision.task_id == arguments["record"]["task_id"],
        "decision must carry the record task ID",
    )
    require(
        decision.plan_id == arguments["graph_delta"].plan_id,
        "decision must carry the supplied plan ID",
    )
    return decision


def expect_status(
    status: DecompositionAuthorizationStatus,
    *,
    reason: str | None = None,
    **kwargs: Any,
) -> DecompositionAuthorizationDecision:
    decision = decide(**kwargs)
    require(
        decision.status is status,
        f"expected {status.value}, got {decision.status.value} {decision.reason_codes}",
    )
    if reason is not None:
        require(
            reason in decision.reason_codes,
            f"expected reason {reason!r} in {decision.reason_codes}",
        )
    return decision


def expect_contract_error(message: str, **kwargs: Any) -> None:
    try:
        decide(**kwargs)
    except DecompositionAuthorizationContractError:
        return
    raise AssertionError(message)


# ---------------------------------------------------------------------------
# 1. exact valid D1B.2 independent PASS plus an authorized human
# ---------------------------------------------------------------------------


def test_exact_independent_pass_and_human_authorizer_authorizes() -> None:
    decision = expect_status(DecompositionAuthorizationStatus.AUTHORIZED)
    require(decision.is_authorized, "authorized decision must report is_authorized")
    require(decision.reason_codes == (), "an authorized decision carries no reason code")
    require(
        decision.to_dict()
        == {
            "status": "authorized",
            "task_id": TASK_ID,
            "plan_id": PLAN_ID,
            "reason_codes": [],
        },
        "authorized decision payload must be exact",
    )


# ---------------------------------------------------------------------------
# 2-4. record schema and self-consistency
# ---------------------------------------------------------------------------


def test_missing_record_field_is_a_contract_error() -> None:
    for field in RECORD_AUTHORITY_FIELDS:
        broken = record()
        del broken[field]
        expect_contract_error(
            f"a record missing {field} must raise a contract error", record=broken
        )
    broken = record()
    del broken["record_sha256"]
    expect_contract_error(
        "a record missing record_sha256 must raise a contract error", record=broken
    )


def test_extra_record_field_is_a_contract_error() -> None:
    broken = record()
    broken["approved_by_architect"] = "yes"
    expect_contract_error(
        "an extra record field must raise a contract error", record=broken
    )


def test_record_sha256_tamper_is_a_contract_error() -> None:
    tampered = record()
    tampered["record_sha256"] = "0" * 64
    expect_contract_error(
        "a tampered record digest must raise a contract error", record=tampered
    )

    for field in ("task_id", "graph_delta_plan_id", "authorizer_login"):
        mutated = record()
        mutated[field] = (
            "NSC-041"
            if field == "task_id"
            else ("GDP-" + "c" * 64 if field == "graph_delta_plan_id" else "someone-else")
        )
        expect_contract_error(
            f"mutating {field} without recomputing the digest must fail closed",
            record=mutated,
        )

    malformed = record()
    malformed["authorized_at_utc"] = "2026-13-45T99:99:99Z"
    expect_contract_error(
        "a malformed UTC timestamp must raise a contract error", record=malformed
    )
    non_string = record()
    non_string["task_id"] = 42
    expect_contract_error(
        "a non-string authority field must raise a contract error", record=non_string
    )
    expect_contract_error("a non-mapping record must raise", record=["not", "a", "record"])


# ---------------------------------------------------------------------------
# 5-7. human authorizer
# ---------------------------------------------------------------------------


def test_proposal_only_state_is_not_authorized() -> None:
    expect_status(
        DecompositionAuthorizationStatus.NOT_AUTHORIZED,
        reason="authorization_state_not_authorized",
        record=record(authorization_state="proposed"),
    )
    expect_status(
        DecompositionAuthorizationStatus.NOT_AUTHORIZED,
        reason="authorization_state_not_authorized",
        record=record(authorization_state="revoked"),
    )
    expect_contract_error(
        "an unknown authorization_state must raise a contract error",
        record=record(authorization_state="approved-ish"),
    )


def test_authorizer_outside_the_allowlist_is_not_authorized() -> None:
    expect_status(
        DecompositionAuthorizationStatus.NOT_AUTHORIZED,
        reason="authorizer_not_in_allowlist",
        record=record(authorizer_login="someone-else"),
    )
    # Case folding is the only normalization: the same login still authorizes.
    expect_status(
        DecompositionAuthorizationStatus.AUTHORIZED,
        record=record(authorizer_login="CatHode26"),
    )
    expect_status(
        DecompositionAuthorizationStatus.NOT_AUTHORIZED,
        reason="authorizer_is_not_a_human_authority",
        record=record(authorizer_login="claude"),
        authorized_authorizers=("claude",),
    )
    expect_status(
        DecompositionAuthorizationStatus.NOT_AUTHORIZED,
        reason="authorizer_is_not_a_human_authority",
        record=record(authorizer_login="github-actions[bot]"),
        authorized_authorizers=("github-actions[bot]",),
    )


def test_empty_or_malformed_allowlist_cannot_authorize() -> None:
    expect_contract_error(
        "an empty allowlist must fail closed", authorized_authorizers=()
    )
    expect_contract_error(
        "a string allowlist must fail closed", authorized_authorizers="cathode26"
    )
    expect_contract_error(
        "a non-string allowlist entry must fail closed", authorized_authorizers=(1,)
    )
    expect_contract_error(
        "a duplicate allowlist identity must fail closed",
        authorized_authorizers=("cathode26", "CATHODE26"),
    )


# ---------------------------------------------------------------------------
# 8-11. exact task, source, and contract-byte identity
# ---------------------------------------------------------------------------


def test_task_identity_drift_is_stale() -> None:
    expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="task_identity_drift",
        record=record(task_id="NSC-041"),
    )


def test_source_head_drift_is_stale() -> None:
    expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="source_head_drift",
        record=record(source_head="9c" * 20),
    )
    expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="decomposition_run_identity_drift",
        record=record(decomposition_run_id="nsc-042-d1b2-some-other-run"),
    )


def test_exact_task_contract_byte_drift_is_stale() -> None:
    expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="exact_task_contract_bytes_drift",
        record=record(task_contract_sha256="d" * 64),
    )


def test_semantic_parent_hash_cannot_substitute_for_exact_contract_bytes() -> None:
    decision = expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="semantic_parent_hash_substituted_for_exact_contract_bytes",
        record=record(task_contract_sha256=SEMANTIC_PARENT_SHA256),
    )
    require(not decision.is_authorized, "a semantic parent hash must never authorize")


# ---------------------------------------------------------------------------
# 12-17. D1B.2 independent-review contract
# ---------------------------------------------------------------------------


def test_d1b1_proposal_cannot_be_authorized() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="d1b1_proposal_not_independently_reviewed",
        d1b_run_result=d1b1_run(),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="d1b_run_identity_unprovable",
        d1b_run_result={"mode": "round_robin_d1b2"},
    )


def test_unresolved_findings_are_review_invalid() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="unresolved_review_findings",
        d1b_run_result=d1b2_run(unresolved_findings=[blocking_finding()]),
    )
    # A final PASS that introduces a blocking finding contradicts the producer's
    # own review policy, whatever the run's top-level unresolved list claims.
    unresolved_history = history_entry(findings=[blocking_finding()])
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        d1b_run_result=d1b2_run(finding_history=[unresolved_history]),
    )


def test_non_review_ready_run_is_review_invalid() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="d1b_run_status_not_review_ready",
        d1b_run_result=d1b2_run(run_status="needs_human"),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="d1b_run_reported_rejection_reasons",
        d1b_run_result=d1b2_run(
            rejection_reasons=["round 2: review deterministic validation failed"]
        ),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="d1b_run_authority_marker_invalid",
        d1b_run_result=d1b2_run(authority="applied"),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="independent_pass_round_missing",
        d1b_run_result=d1b2_run(
            rounds=[decomposer_round(), reviewer_round(status="revised_candidate_valid")]
        ),
    )


def test_candidate_author_may_not_be_its_own_reviewer() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_is_latest_candidate_author",
        d1b_run_result=d1b2_run(
            latest_candidate=candidate_summary(author_provider=REVIEWER_PROVIDER),
            rounds=[
                decomposer_round(),
                reviewer_round(
                    candidate_before=candidate_summary(
                        author_provider=REVIEWER_PROVIDER
                    )
                ),
            ],
        ),
    )


def test_missing_reviewer_identity_is_review_invalid() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="independent_reviewer_identity_missing",
        d1b_run_result=d1b2_run(independent_approver_provider=None),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_provider_binding_mismatch",
        record=record(reviewer_provider=AUTHOR_PROVIDER),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_invocation_identity_mismatch",
        record=record(reviewer_invocation_id="nsc-042-d1b2-r02-decomposition-reviewer-0"),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_invocation_identity_mismatch",
        d1b_run_result=d1b2_run(
            rounds=[
                decomposer_round(),
                reviewer_round(
                    agent_runtime_result_path="rounds/02/agent_runtime/foreign-run/result.json"
                ),
            ]
        ),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_evidence_identity_mismatch",
        record=record(review_evidence_sha256="e" * 64),
    )
    expect_contract_error(
        "an unsupported reviewer_kind must raise a contract error",
        record=record(reviewer_kind="human_review"),
    )


def test_reviewed_candidate_identity_drift_is_classified_consistently() -> None:
    # A record that names a different reviewed candidate is an artifact identity
    # failure; a D1B history entry that does not bind the latest candidate is a
    # review-contract failure.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="reviewed_candidate_sha256_mismatch",
        record=record(reviewed_candidate_sha256="b" * 64),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_does_not_bind_reviewed_candidate",
        d1b_run_result=d1b2_run(
            finding_history=[history_entry(reviewed_candidate_sha256="b" * 64)]
        ),
    )


# ---------------------------------------------------------------------------
# 18-23. artifact identity
# ---------------------------------------------------------------------------


def test_wrong_decomposition_result_hash_is_artifact_mismatch() -> None:
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_result_sha256_mismatch",
        record=record(decomposition_result_sha256="a" * 64),
    )


def test_supplied_result_object_must_be_the_reviewed_candidate() -> None:
    decision = expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_result_sha256_mismatch",
        decomposition_result=alternate_result(),
    )
    require(
        "d1b_candidate_sha256_mismatch" in decision.reason_codes,
        "the D1B reviewed candidate SHA must also be reported as mismatched",
    )
    expect_contract_error(
        "an untyped decomposition_result must raise a contract error",
        decomposition_result=RESULT.to_dict(),
    )


def test_graph_delta_plan_id_must_match() -> None:
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_plan_id_mismatch",
        record=record(graph_delta_plan_id="GDP-" + "c" * 64),
    )
    expect_contract_error(
        "an untyped graph_delta must raise a contract error",
        graph_delta=GRAPH_DELTA.to_dict(),
    )


def test_graph_delta_canonical_hash_must_match() -> None:
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_canonical_sha256_mismatch",
        record=record(graph_delta_canonical_sha256="f" * 64),
    )
    require(
        PLAN_CANONICAL_SHA256 != PLAN_ID[4:],
        "plan_id and the canonical plan digest are different identities",
    )


def test_d1b_candidate_plan_id_must_match_the_supplied_plan() -> None:
    # The run consistently names a different plan in every place the producer
    # publishes the candidate summary, so only the plan identity is wrong.
    other_plan = candidate_summary(graph_delta_plan_id="GDP-" + "0" * 64)
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="d1b_graph_delta_plan_id_mismatch",
        d1b_run_result=d1b2_run(
            latest_candidate=other_plan,
            rounds=[
                decomposer_round(candidate_after=other_plan),
                reviewer_round(candidate_before=other_plan),
            ],
        ),
    )


def test_artifact_locator_is_operational_only() -> None:
    # Changing the locator without recomputing the digest invalidates the record.
    stale_digest = record()
    stale_digest["artifact_locator"] = "C:\\Users\\VincentLiguori\\Downloads\\elsewhere"
    expect_contract_error(
        "an unrecomputed locator change must fail closed", record=stale_digest
    )
    # A correctly recomputed locator change is accepted but grants no authority.
    expect_status(
        DecompositionAuthorizationStatus.AUTHORIZED,
        record=record(artifact_locator="C:\\Users\\VincentLiguori\\Downloads\\elsewhere"),
    )
    # A locator naming a plausible run directory cannot rescue a mismatched plan.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_plan_id_mismatch",
        record=record(
            graph_delta_plan_id="GDP-" + "c" * 64,
            artifact_locator=ARTIFACT_LOCATOR,
        ),
    )


# ---------------------------------------------------------------------------
# 24-27. purity, immutability, and determinism
# ---------------------------------------------------------------------------


def test_input_mappings_are_never_mutated() -> None:
    cases = (
        (record(), d1b2_run()),
        (record(authorization_state="proposed"), d1b2_run()),
        (record(task_id="NSC-041"), d1b2_run()),
        (record(), d1b1_run()),
        (record(graph_delta_plan_id="GDP-" + "c" * 64), d1b2_run()),
    )
    for authorization_record, run in cases:
        record_before = copy.deepcopy(authorization_record)
        run_before = copy.deepcopy(run)
        decide(record=authorization_record, d1b_run_result=run)
        require(
            authorization_record == record_before,
            "the authorization record mapping must never be mutated",
        )
        require(run == run_before, "the D1B run mapping must never be mutated")


def test_typed_artifacts_are_never_mutated() -> None:
    result_before = json.dumps(RESULT.to_dict(), sort_keys=True)
    delta_before = GRAPH_DELTA.canonical_json()
    for _ in range(3):
        decide()
        decide(record=record(authorization_state="proposed"))
    require(
        json.dumps(RESULT.to_dict(), sort_keys=True) == result_before,
        "the DecompositionResult must remain unchanged",
    )
    require(
        GRAPH_DELTA.canonical_json() == delta_before,
        "the GraphDeltaPlan must remain unchanged",
    )
    require(
        candidate_sha256(RESULT) == CANDIDATE_SHA256,
        "the reviewed candidate digest must remain stable",
    )


FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "subprocess",
        "socket",
        "ssl",
        "http",
        "urllib",
        "requests",
        "ftplib",
        "smtplib",
        "shutil",
        "tempfile",
        "webbrowser",
    }
)
FORBIDDEN_CALL_NAMES = frozenset(
    {
        "open",
        "Popen",
        "system",
        "urlopen",
        "check_output",
        "check_call",
        "call",
        "write_text",
        "write_bytes",
        "read_text",
        "read_bytes",
        "mkdir",
        "unlink",
        "rmtree",
        "remove",
        "rename",
        "connect",
        "exec",
        "eval",
    }
)


def test_no_side_effect_call_paths_exist() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if type(node) is ast.Import:
            for alias in node.names:
                root = alias.name.split(".")[0]
                require(
                    root not in FORBIDDEN_IMPORT_ROOTS,
                    f"the binder must not import {alias.name}",
                )
        elif type(node) is ast.ImportFrom and node.module is not None:
            root = node.module.split(".")[0]
            require(
                root not in FORBIDDEN_IMPORT_ROOTS,
                f"the binder must not import from {node.module}",
            )
        elif type(node) is ast.Call:
            function = node.func
            name = (
                function.attr
                if type(function) is ast.Attribute
                else (function.id if type(function) is ast.Name else "")
            )
            require(
                name not in FORBIDDEN_CALL_NAMES,
                f"the binder must not call {name}()",
            )

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the binder must not touch the filesystem or network")

    import socket
    import subprocess

    with patch.object(subprocess, "run", refuse), patch.object(
        subprocess, "Popen", refuse
    ), patch.object(socket, "socket", refuse), patch(
        "builtins.open", refuse
    ):
        decision = decide()
    require(
        decision.status is DecompositionAuthorizationStatus.AUTHORIZED,
        "the binder must still authorize with every side-effect path disabled",
    )


def test_repeated_evaluation_is_byte_identical() -> None:
    for kwargs in (
        {},
        {"record": record(authorization_state="proposed")},
        {"record": record(task_id="NSC-041")},
        {"d1b_run_result": d1b1_run()},
        {"decomposition_result": alternate_result()},
    ):
        first = decide(**copy.deepcopy(kwargs) if not kwargs else kwargs)
        second = decide(**kwargs)
        require(first == second, "repeat evaluation must produce an equal decision")
        require(
            json.dumps(first.to_dict(), sort_keys=True)
            == json.dumps(second.to_dict(), sort_keys=True),
            "repeat evaluation must produce a byte-identical payload",
        )


def test_record_round_trips_through_its_typed_contract() -> None:
    parsed = DecompositionAuthorizationRecord.from_dict(record())
    require(parsed.to_dict() == record(), "the typed record must round-trip exactly")
    require(
        parsed.record_sha256 == authorization_record_sha256(parsed.authority_fields()),
        "record_sha256 must bind exactly the authority-bearing fields",
    )
    require(
        json.loads(parsed.canonical_json()) == record(),
        "canonical record JSON must preserve every field",
    )


# ---------------------------------------------------------------------------
# C1. logical reviewer identity versus AgentRuntime provider identity
# ---------------------------------------------------------------------------


def producer_runtime_provider_map() -> dict[str, str]:
    """The logical->runtime provider map ``live_decomposition`` actually owns."""

    tree = ast.parse(LIVE_DECOMPOSITION_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if type(node) is not ast.Assign:
            continue
        if not any(
            type(target) is ast.Name and target.id == "expected_identifier"
            for target in node.targets
        ):
            continue
        value = node.value
        mapping = value.value if type(value) is ast.Subscript else value
        if type(mapping) is ast.Dict:
            return ast.literal_eval(mapping)
    raise AssertionError(
        "live_decomposition no longer declares a logical->runtime provider map"
    )


def test_runtime_provider_identities_match_the_producer() -> None:
    require(
        RUNTIME_PROVIDER_IDENTIFIERS == producer_runtime_provider_map(),
        "the binder must compare the exact runtime identities the producer maps",
    )
    require(
        set(RUNTIME_PROVIDER_IDENTIFIERS) == {"claude", "codex"},
        "the accepted provider set must not widen beyond D1B.2 support",
    )


def test_claude_reviewer_runs_as_claude_code() -> None:
    require(
        reviewer_round()["actual_provider"] == "claude-code",
        "a claude reviewer round must report the claude-code runtime provider",
    )
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED)


def mirrored_rotation() -> dict[str, Any]:
    """The same exact circuit with claude authoring and codex reviewing."""

    author, reviewer = REVIEWER_PROVIDER, AUTHOR_PROVIDER
    author_summary = candidate_summary(author_provider=author)
    entry = history_entry(reviewer_provider=reviewer)
    return {
        "record": record(
            reviewer_provider=reviewer,
            review_evidence_sha256=semantic_sha256(entry),
        ),
        "d1b_run_result": d1b2_run(
            provider_order=[author, reviewer],
            latest_candidate=author_summary,
            independent_approver_provider=reviewer,
            rounds=[
                decomposer_round(
                    requested_provider=author,
                    actual_provider=RUNTIME_PROVIDER_IDENTIFIERS[author],
                    candidate_after=author_summary,
                ),
                reviewer_round(
                    requested_provider=reviewer,
                    actual_provider=RUNTIME_PROVIDER_IDENTIFIERS[reviewer],
                    candidate_before=author_summary,
                ),
            ],
            finding_history=[entry],
        ),
    }


def test_codex_reviewer_runs_as_openai_codex() -> None:
    mirrored = mirrored_rotation()
    require(
        mirrored["d1b_run_result"]["rounds"][1]["actual_provider"] == "openai-codex",
        "a codex reviewer round must report the openai-codex runtime provider",
    )
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED, **mirrored)


def test_logical_and_runtime_provider_cross_wiring_fails() -> None:
    # A reviewer round that names the other provider's runtime identity.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(
            rounds=[
                decomposer_round(),
                reviewer_round(actual_provider=AUTHOR_RUNTIME_PROVIDER),
            ]
        ),
    )
    # The logical D1B.2 name is never an AgentRuntime provider identity.
    for logical in ("claude", "codex"):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(),
                    reviewer_round(actual_provider=logical),
                ]
            ),
        )
    # The author round is bound at the same identity layer.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(
            rounds=[
                decomposer_round(actual_provider=AUTHOR_PROVIDER),
                reviewer_round(),
            ]
        ),
    )


def test_arbitrary_runtime_provider_strings_fail() -> None:
    # ``fake`` is the producer's injected-test escape, never a production
    # authorization shortcut.
    for provider in ("fake", "claude-code-2", "openai", "", None):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(),
                    reviewer_round(actual_provider=provider),
                ]
            ),
        )


# ---------------------------------------------------------------------------
# C2. ordered review-history resolution semantics
# ---------------------------------------------------------------------------


REVISED_RESULT = alternate_result()
REVISED_GRAPH_DELTA = plan_graph_delta(
    _PLAN, REVISED_RESULT.parent_task, REVISED_RESULT
)
REVISED_SHA256 = candidate_sha256(REVISED_RESULT)
REVISED_PLAN_ID = REVISED_GRAPH_DELTA.plan_id
REVISED_PLAN_CANONICAL_SHA256 = hashlib.sha256(
    REVISED_GRAPH_DELTA.canonical_json().encode("utf-8")
).hexdigest()
BLOCKING_FINDING_ID = blocking_finding()["finding_id"]


def revised_candidate_summary(**overrides: Any) -> dict[str, Any]:
    summary = {
        "version": 2,
        "author_provider": REVIEWER_PROVIDER,
        "sha256": REVISED_SHA256,
        "decision": "decomposed",
        "graph_delta_plan_id": REVISED_PLAN_ID,
    }
    summary.update(overrides)
    return summary


def revise_history_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "round_number": 2,
        "reviewer_provider": REVIEWER_PROVIDER,
        "reviewed_candidate_sha256": CANDIDATE_SHA256,
        "verdict": "revise",
        "summary": "The integration child's completion gate needs a later authored scene.",
        "findings": [blocking_finding()],
        "prior_finding_resolutions": [],
    }
    entry.update(overrides)
    return entry


def prior_resolution(**overrides: Any) -> dict[str, Any]:
    value = {
        "finding_id": BLOCKING_FINDING_ID,
        "status": "resolved",
        "explanation": "The revision moved the downstream proof to an integration obligation.",
    }
    value.update(overrides)
    return value


def pass_history_entry(**overrides: Any) -> dict[str, Any]:
    entry = {
        "round_number": 3,
        "reviewer_provider": AUTHOR_PROVIDER,
        "reviewed_candidate_sha256": REVISED_SHA256,
        "verdict": "pass",
        "summary": "Both revised children are locally completable.",
        "findings": [],
        "prior_finding_resolutions": [prior_resolution()],
    }
    entry.update(overrides)
    return entry


def revise_round(**overrides: Any) -> dict[str, Any]:
    summary = reviewer_round(
        verdict="revise",
        new_finding_ids=[BLOCKING_FINDING_ID],
        candidate_after=revised_candidate_summary(),
        unresolved_finding_ids=[BLOCKING_FINDING_ID],
        status="revised_candidate_valid",
    )
    summary.update(overrides)
    return summary


def final_pass_round(**overrides: Any) -> dict[str, Any]:
    summary = {
        "schema_version": "1.0",
        "round_number": 3,
        "role": "decomposition_reviewer",
        "requested_provider": AUTHOR_PROVIDER,
        "actual_provider": AUTHOR_RUNTIME_PROVIDER,
        "actual_model": "gpt-5-codex",
        "agent_status": "succeeded",
        "agent_failure_classification": None,
        "duration_seconds": 244.18,
        "candidate_before": revised_candidate_summary(),
        "candidate_after": None,
        "verdict": "pass",
        "new_finding_ids": [],
        "unresolved_finding_ids": [],
        **round_artifact_paths(3, ROUND_THREE_INVOCATION_ID),
        "status": "independent_pass",
        "authority": "review_only_not_applied",
        "rejection_reasons": [],
    }
    summary.update(overrides)
    return summary


def revise_then_pass(**overrides: Any) -> dict[str, Any]:
    """A producer-shaped revise -> independent PASS circuit over three calls."""

    history = overrides.pop(
        "finding_history", [revise_history_entry(), pass_history_entry()]
    )
    run = d1b2_run(
        calls_used=3,
        latest_candidate=revised_candidate_summary(),
        independent_approver_provider=AUTHOR_PROVIDER,
        rounds=[decomposer_round(), revise_round(), final_pass_round()],
        finding_history=history,
    )
    run.update(overrides)
    return {
        "record": record(
            decomposition_result_sha256=REVISED_SHA256,
            reviewed_candidate_sha256=REVISED_SHA256,
            graph_delta_plan_id=REVISED_PLAN_ID,
            graph_delta_canonical_sha256=REVISED_PLAN_CANONICAL_SHA256,
            reviewer_provider=AUTHOR_PROVIDER,
            reviewer_invocation_id=ROUND_THREE_INVOCATION_ID,
            review_evidence_sha256=semantic_sha256(history[-1]),
        ),
        "d1b_run_result": run,
        "decomposition_result": REVISED_RESULT,
        "graph_delta": REVISED_GRAPH_DELTA,
    }


def test_producer_shaped_revise_then_pass_authorizes() -> None:
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED, **revise_then_pass())


def test_fabricated_resolution_field_is_not_authority() -> None:
    # The old wrong shape: a ``resolution`` key instead of the emitted ``status``.
    fabricated = pass_history_entry(
        prior_finding_resolutions=[
            {
                "finding_id": BLOCKING_FINDING_ID,
                "resolution": "resolved",
                "explanation": "Fabricated resolution evidence.",
            }
        ]
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(
            finding_history=[revise_history_entry(), fabricated]
        ),
    )
    # A producer-shaped resolution carrying an extra ``resolution`` field is not
    # the contract the producer emits either.
    smuggled = pass_history_entry(
        prior_finding_resolutions=[prior_resolution(resolution="resolved")]
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(finding_history=[revise_history_entry(), smuggled]),
    )
    # A still_blocking status never clears the finding.
    blocked = pass_history_entry(
        prior_finding_resolutions=[prior_resolution(status="still_blocking")]
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(finding_history=[revise_history_entry(), blocked]),
    )


def test_resolving_a_finding_that_is_not_outstanding_fails() -> None:
    # A resolution for a finding that was never raised.
    unknown = pass_history_entry(
        prior_finding_resolutions=[
            prior_resolution(finding_id="round-02-never-raised")
        ]
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(finding_history=[revise_history_entry(), unknown]),
    )
    # A resolution in a run where nothing is outstanding at all.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        d1b_run_result=d1b2_run(
            finding_history=[
                history_entry(prior_finding_resolutions=[prior_resolution()])
            ]
        ),
    )
    # A review that ignores an outstanding blocking finding entirely.
    ignored = pass_history_entry(prior_finding_resolutions=[])
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(finding_history=[revise_history_entry(), ignored]),
    )


def test_final_pass_may_not_introduce_a_blocking_finding() -> None:
    late_blocker = dict(blocking_finding(), finding_id="round-03-late-blocker")
    introducing = pass_history_entry(findings=[late_blocker])
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(
            finding_history=[revise_history_entry(), introducing]
        ),
    )


def test_unresolved_blocking_findings_never_authorize() -> None:
    # The producer's own unresolved list.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="unresolved_review_findings",
        **revise_then_pass(unresolved_findings=[blocking_finding()]),
    )
    # A history that never resolves the blocking finding it raised.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(
            finding_history=[
                revise_history_entry(),
                pass_history_entry(
                    prior_finding_resolutions=[
                        prior_resolution(status="still_blocking")
                    ],
                ),
            ]
        ),
    )
    # A finding raised under a foreign round prefix is not this circuit's.
    foreign = revise_history_entry(
        findings=[dict(blocking_finding(), finding_id="round-07-foreign")]
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="review_history_resolution_semantics_invalid",
        **revise_then_pass(
            finding_history=[
                foreign,
                pass_history_entry(
                    prior_finding_resolutions=[
                        prior_resolution(finding_id="round-07-foreign")
                    ]
                ),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# C3. incomplete or self-contradictory review_ready run shapes
# ---------------------------------------------------------------------------


def test_missing_reviewer_artifact_paths_never_authorize() -> None:
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_artifact_paths_missing",
        d1b_run_result=d1b2_run(
            rounds=[
                decomposer_round(),
                reviewer_round(
                    task_execution_request_path=None,
                    agent_runtime_result_path=None,
                ),
            ]
        ),
    )
    for field in ("task_execution_request_path", "agent_runtime_result_path"):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="reviewer_artifact_paths_missing",
            d1b_run_result=d1b2_run(
                rounds=[decomposer_round(), reviewer_round(**{field: None})]
            ),
        )
    # A path for a different round is not this round's evidence.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="reviewer_artifact_paths_missing",
        d1b_run_result=d1b2_run(
            rounds=[
                decomposer_round(),
                reviewer_round(
                    **{
                        "agent_runtime_result_path": (
                            f"rounds/03/agent_runtime/{REVIEWER_INVOCATION_ID}"
                            "/result.json"
                        )
                    }
                ),
            ]
        ),
    )


def test_contradictory_latest_candidate_decision_never_authorizes() -> None:
    # The run's own approving round reviewed the real candidate summary.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="independent_pass_round_invalid",
        d1b_run_result=d1b2_run(
            latest_candidate=candidate_summary(decision="not_decomposed")
        ),
    )
    # A consistently rewritten not_decomposed candidate still has no plan to
    # authorize.
    not_decomposed = candidate_summary(decision="not_decomposed")
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_decision_not_decomposed",
        d1b_run_result=d1b2_run(
            latest_candidate=not_decomposed,
            rounds=[
                decomposer_round(candidate_after=not_decomposed),
                reviewer_round(candidate_before=not_decomposed),
            ],
        ),
    )
    # A latest candidate that is not the producer's own summary shape.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="latest_candidate_identity_unprovable",
        d1b_run_result=d1b2_run(
            latest_candidate={"sha256": CANDIDATE_SHA256, "decision": "decomposed"}
        ),
    )


def test_impossible_bounded_call_accounting_never_authorizes() -> None:
    for max_calls, calls_used in ((1, 99), (4, 99), (4, 1), (2, 3), (0, 0), (4, -1)):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="bounded_call_accounting_invalid",
            d1b_run_result=d1b2_run(max_calls=max_calls, calls_used=calls_used),
        )
    # Round and review-history counts must match the calls the run reports.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="bounded_call_accounting_invalid",
        d1b_run_result=d1b2_run(calls_used=3),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="bounded_call_accounting_invalid",
        d1b_run_result=d1b2_run(
            finding_history=[history_entry(), history_entry()]
        ),
    )


def test_provider_rotation_must_be_the_producers_own() -> None:
    for order in ([AUTHOR_PROVIDER], [AUTHOR_PROVIDER, AUTHOR_PROVIDER], [], "codex"):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="provider_rotation_inconsistent",
            d1b_run_result=d1b2_run(provider_order=order),
        )
    # A valid rotation that the emitted rounds do not actually follow.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(provider_order=[REVIEWER_PROVIDER, AUTHOR_PROVIDER]),
    )
    # Round roles and numbers must follow the producer's own sequence.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(
            rounds=[decomposer_round(role="decomposition_reviewer"), reviewer_round()]
        ),
    )
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(
            rounds=[decomposer_round(), reviewer_round(round_number=5)]
        ),
    )
    # A round that never succeeded cannot be part of a review_ready circuit.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        d1b_run_result=d1b2_run(
            rounds=[decomposer_round(agent_status="failed"), reviewer_round()]
        ),
    )


# ---------------------------------------------------------------------------
# C3-A. exact producer artifact names for a review_ready run
# ---------------------------------------------------------------------------


ROUND_ROBIN_SOURCE = (
    PIPELINE_ROOT / "TaskDecomposition" / "round_robin_decomposition.py"
).read_text(encoding="utf-8")


def test_review_ready_artifact_names_are_pinned_to_the_producer() -> None:
    """The binder's expected file names are the ones the producer publishes."""

    require(
        'decomposition_result_path = "decomposition_result.json"' in ROUND_ROBIN_SOURCE,
        "the producer must publish decomposition_result.json for a review_ready run",
    )
    require(
        'graph_delta_path = "graph_delta.json"' in ROUND_ROBIN_SOURCE,
        "the producer must publish graph_delta.json for a decomposed candidate",
    )
    require(
        (D1B2_DECOMPOSITION_RESULT_FILENAME, D1B2_GRAPH_DELTA_FILENAME)
        == ("decomposition_result.json", "graph_delta.json"),
        "the binder must expect the producer's exact artifact names",
    )


def test_review_ready_artifact_paths_must_be_the_producers_own() -> None:
    # A review_ready run wrote decomposition_result.json. Absent, empty, or
    # differently named is not that artifact.
    for path in ("", "   ", None, "decomposition_result", "run/decomposition_result.json"):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="review_ready_artifacts_missing",
            d1b_run_result=d1b2_run(decomposition_result_path=path),
        )
    # The latest candidate declares a plan, so the run wrote graph_delta.json.
    for path in ("", "   ", None, "graph_delta", "run/graph_delta.json"):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="review_ready_artifacts_missing",
            d1b_run_result=d1b2_run(graph_delta_path=path),
        )


def test_a_candidate_without_a_plan_is_not_a_missing_artifact() -> None:
    """A not_decomposed candidate published no graph delta and never could.

    That shape is classified by the artifact stage it actually fails, not as a
    review_ready run whose artifacts went missing.
    """

    no_plan = candidate_summary(decision="not_decomposed", graph_delta_plan_id=None)
    decision = expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_decision_not_decomposed",
        d1b_run_result=d1b2_run(
            decision="not_decomposed",
            latest_candidate=no_plan,
            graph_delta_path=None,
            rounds=[
                decomposer_round(candidate_after=no_plan),
                reviewer_round(candidate_before=no_plan),
            ],
        ),
    )
    require(
        "review_ready_artifacts_missing" not in decision.reason_codes,
        "a candidate with no plan must not be reported as a missing artifact",
    )


# ---------------------------------------------------------------------------
# C3-B. exact producer round-transition semantics
# ---------------------------------------------------------------------------


def test_initial_round_must_publish_the_authored_candidate() -> None:
    # The producer's round 1 always emits candidate_after on success; a round 1
    # without one never reached candidate_valid.
    for candidate_after in (None, {}, {"sha256": CANDIDATE_SHA256}):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(candidate_after=candidate_after),
                    reviewer_round(),
                ]
            ),
        )
    # Round 1 authors version 1 under the first provider in the rotation.
    for published in (
        candidate_summary(version=2),
        candidate_summary(author_provider=REVIEWER_PROVIDER),
    ):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(candidate_after=published),
                    reviewer_round(candidate_before=published),
                ]
            ),
        )


def test_impossible_initial_round_status_never_authorizes() -> None:
    # Round 1 authors a candidate. It cannot approve, revise, or reject itself.
    for status in (
        "independent_pass",
        "revised_candidate_valid",
        "needs_human",
        "rejected",
        None,
    ):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[decomposer_round(status=status), reviewer_round()]
            ),
        )
    # Round 1 carries no verdict and raises no finding.
    for overrides in (
        {"verdict": "pass"},
        {"new_finding_ids": ["round-01-something"]},
        {"unresolved_finding_ids": ["round-01-something"]},
    ):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[decomposer_round(**overrides), reviewer_round()]
            ),
        )


def test_revision_round_must_publish_the_next_reviewed_candidate() -> None:
    # A revise that publishes nothing is not the producer's revised_candidate_valid.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        **revise_then_pass(
            rounds=[
                decomposer_round(),
                revise_round(candidate_after=None),
                final_pass_round(candidate_before=None),
            ]
        ),
    )
    # The revised candidate is what the next round reviews.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        **revise_then_pass(
            rounds=[
                decomposer_round(),
                revise_round(),
                final_pass_round(candidate_before=candidate_summary()),
            ]
        ),
    )
    # The revision is authored by the reviewing provider and bumps the version.
    for published in (
        revised_candidate_summary(version=1),
        revised_candidate_summary(author_provider=AUTHOR_PROVIDER),
        candidate_summary(version=2),
    ):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            **revise_then_pass(
                rounds=[
                    decomposer_round(),
                    revise_round(candidate_after=published),
                    final_pass_round(candidate_before=published),
                ]
            ),
        )
    # A revise that leaves nothing outstanding is not a revise the producer emits.
    expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        **revise_then_pass(
            rounds=[
                decomposer_round(),
                revise_round(unresolved_finding_ids=[]),
                final_pass_round(),
            ]
        ),
    )


def test_final_independent_pass_may_not_publish_a_candidate() -> None:
    for candidate_after in (candidate_summary(), revised_candidate_summary()):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(),
                    reviewer_round(candidate_after=candidate_after),
                ]
            ),
        )


def test_final_independent_pass_may_not_carry_unresolved_findings() -> None:
    for unresolved in ([BLOCKING_FINDING_ID], ["round-02-child-notes-wording"]):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="round_sequence_inconsistent",
            d1b_run_result=d1b2_run(
                rounds=[
                    decomposer_round(),
                    reviewer_round(unresolved_finding_ids=unresolved),
                ]
            ),
        )


def test_no_round_may_follow_an_independent_pass() -> None:
    """The producer breaks on review_ready, so independent_pass is terminal."""

    trailing_pass = reviewer_round(
        round_number=3,
        requested_provider=AUTHOR_PROVIDER,
        actual_provider=AUTHOR_RUNTIME_PROVIDER,
        actual_model="gpt-5-codex",
        new_finding_ids=[],
        **round_artifact_paths(3, ROUND_THREE_INVOCATION_ID),
    )
    trailing_history = history_entry(
        round_number=3, reviewer_provider=AUTHOR_PROVIDER, findings=[]
    )
    # Everything downstream of the extra round is made self-consistent, so the
    # middle independent_pass followed by a later round is the only defect.
    decision = expect_status(
        DecompositionAuthorizationStatus.REVIEW_INVALID,
        reason="round_sequence_inconsistent",
        record=record(
            reviewer_provider=AUTHOR_PROVIDER,
            reviewer_invocation_id=ROUND_THREE_INVOCATION_ID,
            review_evidence_sha256=semantic_sha256(trailing_history),
        ),
        d1b_run_result=d1b2_run(
            calls_used=3,
            independent_approver_provider=AUTHOR_PROVIDER,
            rounds=[decomposer_round(), reviewer_round(), trailing_pass],
            finding_history=[history_entry(), trailing_history],
        ),
    )
    require(
        not decision.is_authorized,
        "a run continuing past an independent_pass can never authorize",
    )


# ---------------------------------------------------------------------------
# C3-C. malformed aligned reviewer identity fails closed rather than raising
# ---------------------------------------------------------------------------


def test_unsupported_aligned_logical_approver_fails_closed() -> None:
    """An approver outside the supported logical vocabulary has no runtime map.

    The aligned form is the dangerous one: the approving round names the same
    unsupported provider, so nothing short-circuits before the logical to
    AgentRuntime lookup.
    """

    for provider in ("gemini", "fake", "claude-code", "openai-codex", "CLAUDE", ""):
        decision = expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="independent_reviewer_identity_missing",
            d1b_run_result=d1b2_run(
                independent_approver_provider=provider,
                rounds=[
                    decomposer_round(),
                    reviewer_round(
                        requested_provider=provider,
                        actual_provider=provider,
                    ),
                ],
                finding_history=[history_entry(reviewer_provider=provider)],
            ),
        )
        require(
            not decision.is_authorized,
            f"an unsupported logical approver must never authorize: {provider!r}",
        )


def test_non_string_aligned_logical_approver_fails_closed() -> None:
    for provider in ([REVIEWER_PROVIDER], {"provider": REVIEWER_PROVIDER}, 7, None, True):
        decision = expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="independent_reviewer_identity_missing",
            d1b_run_result=d1b2_run(
                independent_approver_provider=provider,
                rounds=[
                    decomposer_round(),
                    reviewer_round(
                        requested_provider=provider,
                        actual_provider=provider,
                    ),
                ],
                finding_history=[history_entry(reviewer_provider=provider)],
            ),
        )
        require(
            not decision.is_authorized,
            f"a non-string logical approver must never authorize: {provider!r}",
        )


# ---------------------------------------------------------------------------
# C3. valid producer-shaped controls for both review_ready round chains
# ---------------------------------------------------------------------------


def test_both_producer_round_chains_still_authorize() -> None:
    # Initial candidate -> independent PASS.
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED)
    # Initial candidate -> revise -> resolved -> independent PASS.
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED, **revise_then_pass())


# ---------------------------------------------------------------------------
# C4. the exact D1A -> DecompositionResult -> GraphDeltaPlan parent chain
# ---------------------------------------------------------------------------


PARENT_REVISION = RESULT.parent_task.contract_revision
DRIFTED_PLAN = replace_parent(
    _PLAN, lambda task: task.update({"contract_revision": PARENT_REVISION + 1})
)
DRIFTED_RESULT = validated_result(DRIFTED_PLAN)
DRIFTED_GRAPH_DELTA = plan_graph_delta(
    DRIFTED_PLAN, DRIFTED_RESULT.parent_task, DRIFTED_RESULT
)


def semantic_parent_identity(**overrides: Any) -> dict[str, Any]:
    identity = {
        "task_id": TASK_ID,
        "contract_revision": PARENT_REVISION,
        "contract_sha256": SEMANTIC_PARENT_SHA256,
    }
    identity.update(overrides)
    return identity


def tampered_plan(**payload_overrides: Any) -> Any:
    """A GraphDeltaPlan whose payload was edited after planning."""

    payload = copy.deepcopy(GRAPH_DELTA.to_dict())
    for key, value in payload_overrides.items():
        if key == "parent_before_summary":
            payload["parent_before_summary"].update(value)
        else:
            payload[key] = value
    return GraphDeltaPlan.from_payload(payload)


def with_recomputed_plan_digest(plan: Any, **record_overrides: Any) -> dict[str, Any]:
    """Supply a plan plus a record whose plan digest was honestly recomputed."""

    canonical = plan.canonical_json()
    return {
        "graph_delta": plan,
        "record": record(
            graph_delta_plan_id=plan.plan_id,
            graph_delta_canonical_sha256=hashlib.sha256(
                canonical.encode("utf-8")
            ).hexdigest(),
            **record_overrides,
        ),
    }


def drifted_parent_case(**run_overrides: Any) -> dict[str, Any]:
    """A complete valid circuit built on the next parent contract revision."""

    sha256 = candidate_sha256(DRIFTED_RESULT)
    plan_id = DRIFTED_GRAPH_DELTA.plan_id
    summary = candidate_summary(sha256=sha256, graph_delta_plan_id=plan_id)
    entry = history_entry(reviewed_candidate_sha256=sha256)
    run = d1b2_run(
        latest_candidate=summary,
        rounds=[
            decomposer_round(candidate_after=summary),
            reviewer_round(candidate_before=summary),
        ],
        finding_history=[entry],
    )
    run.update(run_overrides)
    return {
        "record": record(
            decomposition_result_sha256=sha256,
            reviewed_candidate_sha256=sha256,
            graph_delta_plan_id=plan_id,
            graph_delta_canonical_sha256=hashlib.sha256(
                DRIFTED_GRAPH_DELTA.canonical_json().encode("utf-8")
            ).hexdigest(),
            review_evidence_sha256=semantic_sha256(entry),
        ),
        "d1b_run_result": run,
        "decomposition_result": DRIFTED_RESULT,
        "graph_delta": DRIFTED_GRAPH_DELTA,
    }


def test_d1a_semantic_parent_revision_drift_fails() -> None:
    decision = expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_result_parent_revision_mismatch",
        d1b_run_result=d1b2_run(
            d1a_semantic_parent_identity=semantic_parent_identity(
                contract_revision=PARENT_REVISION + 1
            )
        ),
    )
    require(
        "graph_delta_parent_revision_mismatch" in decision.reason_codes,
        "the GraphDelta parent revision must be bound to the same chain",
    )
    # An unstatable D1A parent identity makes the whole run unprovable.
    for identity in ({}, {"task_id": TASK_ID}, semantic_parent_identity(contract_revision="3")):
        expect_status(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            reason="d1b_run_identity_unprovable",
            d1b_run_result=d1b2_run(d1a_semantic_parent_identity=identity),
        )
    # A parent identity naming a different task is task identity drift.
    expect_status(
        DecompositionAuthorizationStatus.STALE_BINDING,
        reason="task_identity_drift",
        d1b_run_result=d1b2_run(
            d1a_semantic_parent_identity=semantic_parent_identity(task_id="NSC-041")
        ),
    )


def test_d1a_semantic_parent_hash_drift_fails() -> None:
    decision = expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_result_parent_hash_mismatch",
        d1b_run_result=d1b2_run(
            d1a_semantic_parent_identity=semantic_parent_identity(
                contract_sha256="d" * 64
            )
        ),
    )
    require(
        "graph_delta_parent_before_hash_mismatch" in decision.reason_codes,
        "the GraphDelta parent_before_hash must be bound to the same chain",
    )


def test_decomposition_result_parent_task_must_match_the_bound_parent() -> None:
    # The supplied result and plan are internally consistent and their digests
    # all recompute, but they were built against a different parent revision.
    decision = expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="decomposition_result_parent_revision_mismatch",
        **drifted_parent_case(),
    )
    for code in (
        "decomposition_result_parent_hash_mismatch",
        "graph_delta_parent_revision_mismatch",
        "graph_delta_parent_before_hash_mismatch",
    ):
        require(
            code in decision.reason_codes,
            f"expected {code} in {decision.reason_codes}",
        )
    # The same artifacts authorize once the run's bound parent is the one they
    # were actually planned against.
    expect_status(
        DecompositionAuthorizationStatus.AUTHORIZED,
        **drifted_parent_case(
            d1a_semantic_parent_identity=DRIFTED_RESULT.parent_task.to_dict()
        ),
    )


def test_graph_delta_parent_drift_fails_after_digest_recomputation() -> None:
    # parent_before_hash drift, with the record's plan digest honestly recomputed.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_parent_before_hash_mismatch",
        **with_recomputed_plan_digest(tampered_plan(parent_before_hash="f" * 64)),
    )
    # parent task drift.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_parent_task_mismatch",
        **with_recomputed_plan_digest(
            tampered_plan(parent_before_summary={"task_id": "NSC-041"})
        ),
    )
    # parent revision drift.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_parent_revision_mismatch",
        **with_recomputed_plan_digest(
            tampered_plan(
                parent_before_summary={"contract_revision": PARENT_REVISION + 5}
            )
        ),
    )
    # A recomputed canonical digest never rescues a plan built elsewhere.
    expect_status(
        DecompositionAuthorizationStatus.ARTIFACT_MISMATCH,
        reason="graph_delta_authority_marker_invalid",
        **with_recomputed_plan_digest(tampered_plan(authority="applied")),
    )


def test_the_exact_parent_chain_authorizes() -> None:
    run = d1b2_run()
    parent = RESULT.parent_task
    require(
        run["d1a_semantic_parent_identity"] == parent.to_dict(),
        "the fixture must bind the run identity to the result parent identity",
    )
    require(
        GRAPH_DELTA.to_dict()["parent_before_hash"] == parent.contract_sha256,
        "the plan must be built on the same semantic parent hash",
    )
    require(
        GRAPH_DELTA.to_dict()["parent_before_summary"]["contract_revision"]
        == parent.contract_revision,
        "the plan must be built on the same parent contract revision",
    )
    expect_status(DecompositionAuthorizationStatus.AUTHORIZED)


def main() -> int:
    tests = (
        test_exact_independent_pass_and_human_authorizer_authorizes,
        test_missing_record_field_is_a_contract_error,
        test_extra_record_field_is_a_contract_error,
        test_record_sha256_tamper_is_a_contract_error,
        test_proposal_only_state_is_not_authorized,
        test_authorizer_outside_the_allowlist_is_not_authorized,
        test_empty_or_malformed_allowlist_cannot_authorize,
        test_task_identity_drift_is_stale,
        test_source_head_drift_is_stale,
        test_exact_task_contract_byte_drift_is_stale,
        test_semantic_parent_hash_cannot_substitute_for_exact_contract_bytes,
        test_d1b1_proposal_cannot_be_authorized,
        test_unresolved_findings_are_review_invalid,
        test_non_review_ready_run_is_review_invalid,
        test_candidate_author_may_not_be_its_own_reviewer,
        test_missing_reviewer_identity_is_review_invalid,
        test_reviewed_candidate_identity_drift_is_classified_consistently,
        test_wrong_decomposition_result_hash_is_artifact_mismatch,
        test_supplied_result_object_must_be_the_reviewed_candidate,
        test_graph_delta_plan_id_must_match,
        test_graph_delta_canonical_hash_must_match,
        test_d1b_candidate_plan_id_must_match_the_supplied_plan,
        test_artifact_locator_is_operational_only,
        test_input_mappings_are_never_mutated,
        test_typed_artifacts_are_never_mutated,
        test_no_side_effect_call_paths_exist,
        test_repeated_evaluation_is_byte_identical,
        test_record_round_trips_through_its_typed_contract,
        test_runtime_provider_identities_match_the_producer,
        test_claude_reviewer_runs_as_claude_code,
        test_codex_reviewer_runs_as_openai_codex,
        test_logical_and_runtime_provider_cross_wiring_fails,
        test_arbitrary_runtime_provider_strings_fail,
        test_producer_shaped_revise_then_pass_authorizes,
        test_fabricated_resolution_field_is_not_authority,
        test_resolving_a_finding_that_is_not_outstanding_fails,
        test_final_pass_may_not_introduce_a_blocking_finding,
        test_unresolved_blocking_findings_never_authorize,
        test_missing_reviewer_artifact_paths_never_authorize,
        test_contradictory_latest_candidate_decision_never_authorizes,
        test_impossible_bounded_call_accounting_never_authorizes,
        test_provider_rotation_must_be_the_producers_own,
        test_review_ready_artifact_names_are_pinned_to_the_producer,
        test_review_ready_artifact_paths_must_be_the_producers_own,
        test_a_candidate_without_a_plan_is_not_a_missing_artifact,
        test_initial_round_must_publish_the_authored_candidate,
        test_impossible_initial_round_status_never_authorizes,
        test_revision_round_must_publish_the_next_reviewed_candidate,
        test_final_independent_pass_may_not_publish_a_candidate,
        test_final_independent_pass_may_not_carry_unresolved_findings,
        test_no_round_may_follow_an_independent_pass,
        test_unsupported_aligned_logical_approver_fails_closed,
        test_non_string_aligned_logical_approver_fails_closed,
        test_both_producer_round_chains_still_authorize,
        test_d1a_semantic_parent_revision_drift_fails,
        test_d1a_semantic_parent_hash_drift_fails,
        test_decomposition_result_parent_task_must_match_the_bound_parent,
        test_graph_delta_parent_drift_fails_after_digest_recomputation,
        test_the_exact_parent_chain_authorizes,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Decomposition authorization tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
