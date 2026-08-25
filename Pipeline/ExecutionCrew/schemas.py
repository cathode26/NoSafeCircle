"""Structured-output schemas and immutable source identity for ExecutionCrew."""

from __future__ import annotations

from dataclasses import dataclass


CONTRACT_LOCALITY_AUDITOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["pass", "contract_review_required"]},
        "summary": {"type": "string"},
        "entry_results": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "entry_type": {"type": "string", "enum": ["acceptance_criterion", "completion_gate"]},
                "classification": {"type": "string", "enum": [
                    "local_to_task", "requires_declared_dependency", "downstream_integration",
                    "missing_design", "ambiguous",
                ]},
                "evidence": {"type": "string"},
                "related_task_ids": {"type": "array", "items": {"type": "string"}},
                "recommended_action": {"type": "string", "enum": [
                    "keep", "add_dependency", "move_to_downstream_integration", "clarify_design", "human_review",
                ]},
            },
            "required": ["id", "entry_type", "classification", "evidence", "related_task_ids", "recommended_action"],
            "additionalProperties": False,
        }},
        "blocking_findings": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string"},
                "reason_code": {"type": "string", "enum": [
                    "requires_declared_dependency", "downstream_integration", "missing_design", "ambiguous",
                ]},
                "issue": {"type": "string"},
                "recommended_action": {"type": "string", "enum": [
                    "add_dependency", "move_to_downstream_integration", "clarify_design", "human_review",
                ]},
                "related_task_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["entry_id", "reason_code", "issue", "recommended_action", "related_task_ids"],
            "additionalProperties": False,
        }},
        "files_reviewed": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "entry_results", "blocking_findings", "files_reviewed"],
    "additionalProperties": False,
}

IMPLEMENTER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claimed_changed_paths": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"},},
    },
    "required": ["summary", "claimed_changed_paths", "blockers", "notes"],
    "additionalProperties": False,
}

TEST_AUTHOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claimed_changed_paths": {"type": "array", "items": {"type": "string"}},
        "test_cases_added_or_updated": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "known_limitations": {"type": "array", "items": {"type": "string"}},
        "proposed_unity_test_scope": {"type": "string"},
    },
    "required": ["summary", "claimed_changed_paths", "test_cases_added_or_updated", "blockers", "known_limitations", "proposed_unity_test_scope"],
    "additionalProperties": False,
}

VALIDATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["pass", "needs_changes", "blocked_by_design"]},
        "summary": {"type": "string"},
        "criteria_results": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string", "enum": ["pass", "fail", "not_proven"]},
                "reason_code": {"type": "string", "enum": [
                    "proved", "criterion_failed", "runtime_not_executed", "missing_integration_dependency",
                    "missing_required_artifact", "insufficient_evidence", "design_ambiguity",
                ]},
                "evidence": {"type": "string"},
            },
            "required": ["id", "status", "reason_code", "evidence"],
            "additionalProperties": False,
        }},
        "blocking_issues": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "issue": {"type": "string"}, "required_fix": {"type": "string"},
        }, "required": ["path", "issue", "required_fix"], "additionalProperties": False}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "files_reviewed": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "criteria_results", "blocking_issues", "risks", "files_reviewed"],
    "additionalProperties": False,
}


# Deterministic status/reason_code agreement rules for VALIDATOR_OUTPUT_SCHEMA.criteria_results.
VALIDATOR_STATUS_REASON_CODES = {"pass": frozenset({"proved"}), "fail": frozenset({"criterion_failed"})}
VALIDATOR_NOT_PROVEN_REASON_CODES = frozenset({
    "runtime_not_executed", "missing_integration_dependency", "missing_required_artifact",
    "insufficient_evidence", "design_ambiguity",
})
VALIDATOR_STATUS_REASON_CODES["not_proven"] = VALIDATOR_NOT_PROVEN_REASON_CODES
# reason_codes that can never coexist with an overall Validator status=pass.
VALIDATOR_NON_PASS_REASON_CODES = VALIDATOR_NOT_PROVEN_REASON_CODES - {"runtime_not_executed"}
# reason_codes that must route the crew to CONTRACT_REVIEW_REQUIRED rather than generic review.
VALIDATOR_CONTRACT_REVIEW_REASON_CODES = frozenset({"missing_integration_dependency", "design_ambiguity"})


@dataclass(frozen=True)
class SourceIdentity:
    root: str
    head: str
    tree: str
    branch: str
