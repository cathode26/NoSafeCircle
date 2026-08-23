"""Structured-output schemas and immutable source identity for ExecutionCrew."""

from __future__ import annotations

from dataclasses import dataclass


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
                "evidence": {"type": "string"},
            },
            "required": ["id", "status", "evidence"],
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


@dataclass(frozen=True)
class SourceIdentity:
    root: str
    head: str
    tree: str
    branch: str
