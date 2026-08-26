"""Fail-closed AgentRuntime schema for D1B.2 decomposition reviews."""

from __future__ import annotations

from copy import deepcopy

from TaskDecomposition.review_contracts import (
    FINDING_CATEGORIES,
    FINDING_RESOLUTION_STATUSES,
    FINDING_SEVERITIES,
    REVIEW_RESULT_SCHEMA_VERSION,
    REVIEW_VERDICTS,
)
from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA


_nullable_decomposition = deepcopy(DECOMPOSITION_RESULT_SCHEMA)
_nullable_decomposition["type"] = ["object", "null"]

DECOMPOSITION_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {
            "type": "string",
            "enum": [REVIEW_RESULT_SCHEMA_VERSION],
        },
        "reviewed_candidate_sha256": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": sorted(REVIEW_VERDICTS),
        },
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": sorted(FINDING_SEVERITIES),
                    },
                    "category": {
                        "type": "string",
                        "enum": sorted(FINDING_CATEGORIES),
                    },
                    "affected_contracts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "problem": {"type": "string"},
                    "required_resolution": {"type": "string"},
                },
                "required": [
                    "finding_id",
                    "severity",
                    "category",
                    "affected_contracts",
                    "problem",
                    "required_resolution",
                ],
                "additionalProperties": False,
            },
        },
        "prior_finding_resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": sorted(FINDING_RESOLUTION_STATUSES),
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["finding_id", "status", "explanation"],
                "additionalProperties": False,
            },
        },
        "revised_decomposition": _nullable_decomposition,
    },
    "required": [
        "schema_version",
        "reviewed_candidate_sha256",
        "verdict",
        "summary",
        "findings",
        "prior_finding_resolutions",
        "revised_decomposition",
    ],
    "additionalProperties": False,
}
