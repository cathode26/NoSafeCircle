"""Future provider structured-output schema for Stage D1A decomposition."""

from __future__ import annotations


def _entry_schema(id_field: str) -> dict:
    return {
        "type": "object",
        "properties": {
            id_field: {"type": "string"},
            "reference": {"type": "string"},
            "requirement": {"type": "string"},
        },
        "required": [id_field, "reference", "requirement"],
        "additionalProperties": False,
    }


PARENT_ENTRY_TYPES = [
    "acceptance_criteria",
    "completion_gates",
    "downstream_integration_obligations",
]

DECOMPOSITION_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": ["1.1"]},
        "parent_task": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "contract_revision": {"type": "integer", "minimum": 1},
                "contract_sha256": {"type": "string"},
            },
            "required": ["task_id", "contract_revision", "contract_sha256"],
            "additionalProperties": False,
        },
        "decision": {
            "type": "string",
            "enum": ["already_concrete", "decomposed", "needs_artifact", "needs_human"],
        },
        "gap_type": {
            "type": "string",
            "enum": ["none", "execution", "design", "uncertain"],
        },
        "reason": {"type": "string"},
        "children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "local_key": {"type": "string"},
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": ["implementation"]},
                    "type": {"type": "string"},
                    "execution_scope": {"type": "string", "enum": ["single_agent"]},
                    "execution_reason": {"type": "string"},
                    "decomposition_state": {"type": "string", "enum": ["concrete"]},
                    "decomposition_reason": {"type": "string"},
                    "existing_task_dependencies": {"type": "array", "items": {"type": "string"}},
                    "local_dependencies": {"type": "array", "items": {"type": "string"}},
                    "exclusive_resources": {"type": "array", "items": {"type": "string"}},
                    "acceptance_criteria": {"type": "array", "items": _entry_schema("criterion_id")},
                    "completion_gates": {"type": "array", "items": _entry_schema("gate_id")},
                    "downstream_integration_obligations": {"type": "array", "items": _entry_schema("obligation_id")},
                    "gdd_evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference": {"type": "string"},
                                "requirement": {"type": "string"},
                            },
                            "required": ["reference", "requirement"],
                            "additionalProperties": False,
                        },
                    },
                    "basis": {"type": "string"},
                    "source_scope": {"type": "string"},
                    "confidence": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": [
                    "local_key", "title", "kind", "type", "execution_scope",
                    "execution_reason", "decomposition_state", "decomposition_reason",
                    "existing_task_dependencies", "local_dependencies", "exclusive_resources",
                    "acceptance_criteria", "completion_gates",
                    "downstream_integration_obligations", "gdd_evidence", "basis",
                    "source_scope", "confidence", "notes",
                ],
                "additionalProperties": False,
            },
        },
        "parent_requirement_coverage": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parent_entry_type": {"type": "string", "enum": PARENT_ENTRY_TYPES},
                    "parent_entry_id": {"type": "string"},
                    "disposition": {
                        "type": "string",
                        "enum": [
                            "retained_by_parent", "assigned_to_child", "shared_integration",
                            "blocked_by_artifact", "blocked_by_human",
                        ],
                    },
                    "child_targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "local_key": {"type": "string"},
                                "child_entry_type": {"type": "string", "enum": PARENT_ENTRY_TYPES},
                                "child_entry_id": {"type": "string"},
                            },
                            "required": ["local_key", "child_entry_type", "child_entry_id"],
                            "additionalProperties": False,
                        },
                    },
                    "reason": {"type": "string"},
                    "integration_rationale": {"type": "string"},
                },
                "required": [
                    "parent_entry_type", "parent_entry_id", "disposition",
                    "child_targets", "reason", "integration_rationale",
                ],
                "additionalProperties": False,
            },
        },
        "inbound_dependency_rewrites": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dependent_task_id": {"type": "string"},
                    "replacement_local_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "reason": {"type": "string"},
                },
                "required": ["dependent_task_id", "replacement_local_keys", "reason"],
                "additionalProperties": False,
            },
        },
        "unsupported_assumptions": {"type": "array", "items": {"type": "string"}},
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        "artifact_proposal": {
            "type": ["object", "null"],
            "properties": {
                "title": {"type": "string"},
                "purpose": {"type": "string"},
                "source_parent_obligations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "parent_entry_type": {"type": "string", "enum": PARENT_ENTRY_TYPES},
                            "parent_entry_id": {"type": "string"},
                        },
                        "required": ["parent_entry_type", "parent_entry_id"],
                        "additionalProperties": False,
                    },
                },
                "authorized_decisions_needed": {"type": "array", "items": {"type": "string"}},
                "out_of_scope": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "title", "purpose", "source_parent_obligations",
                "authorized_decisions_needed", "out_of_scope",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "schema_version", "parent_task", "decision", "gap_type", "reason",
        "children", "parent_requirement_coverage", "inbound_dependency_rewrites",
        "unsupported_assumptions", "unresolved_questions", "artifact_proposal",
    ],
    "additionalProperties": False,
}
