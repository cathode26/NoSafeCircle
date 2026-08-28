#!/usr/bin/env python3
"""Deterministic tests for the live Codex supervisor turn boundary."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.providers.base import ProviderFailure  # noqa: E402
from Pipeline.AgentRuntime.schema_validation import validate_schema  # noqa: E402
from Pipeline.TaskReviewAgent.codex_supervisor import decision_schema  # noqa: E402
from Pipeline.TaskReviewAgent.codex_supervisor_turn import (  # noqa: E402
    SupervisorTurnError,
    _provider_failure_detail,
    _strict_output_schema,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def schema_types(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise AssertionError(f"invalid schema type: {value!r}")


def assert_strict_objects(schema: Mapping[str, Any], path: str = "$") -> None:
    kinds = schema_types(schema.get("type"))
    if "object" in kinds:
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        require(
            set(required) == set(properties),
            f"{path} did not require every declared property",
        )
        for name, child in properties.items():
            assert_strict_objects(child, f"{path}.{name}")
    if "array" in kinds:
        assert_strict_objects(schema["items"], f"{path}[]")


def test_decision_schema_becomes_strict() -> None:
    source = decision_schema(
        (
            "acquire_agent_lease",
            "prepare_task_checkout",
            "validate_execution_scope",
        )
    )
    require(
        "required" not in source["properties"]["arguments"],
        "source contract unexpectedly stopped modeling nullable optional arguments",
    )
    strict = _strict_output_schema(source)
    validate_schema(strict)
    assert_strict_objects(strict)
    arguments = strict["properties"]["arguments"]
    require(
        set(arguments["required"]) == set(arguments["properties"]),
        "strict arguments object omitted a property",
    )
    require(
        "null" in schema_types(arguments["properties"]["plan_id"]["type"]),
        "unused action arguments must remain nullable",
    )


def test_nonnullable_optional_property_is_rejected() -> None:
    invalid = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"value": {"type": "string"}},
        "required": [],
    }
    try:
        _strict_output_schema(invalid)
    except SupervisorTurnError as exc:
        require("optional but does not allow null" in str(exc), str(exc))
    else:
        raise AssertionError("nonnullable optional property was silently made required")


def test_provider_error_event_is_visible_without_raw_prompt() -> None:
    error = ProviderFailure(
        "Codex exited with status 1",
        raw_log=(
            '{"type":"thread.started","thread_id":"thread-1"}\n'
            '{"type":"turn.failed","error":{"code":"invalid_json_schema",'
            '"message":"Every object property must be required."}}\n'
        ),
    )
    detail = _provider_failure_detail(error)
    require("invalid_json_schema" in detail, detail)
    require("Every object property must be required." in detail, detail)
    require("thread-1" not in detail, "non-error transcript content leaked")


def main() -> int:
    tests = (
        test_decision_schema_becomes_strict,
        test_nonnullable_optional_property_is_rejected,
        test_provider_error_event_is_visible_without_raw_prompt,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Codex supervisor turn smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
