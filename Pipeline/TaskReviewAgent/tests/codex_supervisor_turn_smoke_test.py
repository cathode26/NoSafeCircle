#!/usr/bin/env python3
"""Deterministic tests for the live Codex supervisor turn boundary."""

from __future__ import annotations

import json
import os
import subprocess
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


def test_launcher_enables_host_python_utf8() -> None:
    launcher = (
        ROOT / "Pipeline" / "TaskReviewAgent" / "Start-GameTaskAgent.ps1"
    ).read_text(encoding="utf-8")
    require(
        "$env:PYTHONUTF8 = '1'" in launcher,
        "launcher does not enable Python UTF-8 mode before host orchestration",
    )
    require(
        "Remove-Item Env:PYTHONUTF8" in launcher,
        "launcher does not restore an unset process-level PYTHONUTF8 value",
    )

    probe = r'''
import json
import subprocess
import sys

if sys.flags.utf8_mode != 1:
    raise SystemExit("host Python did not enter UTF-8 mode")

payload = '{"message":"Issue \u2014 \u201cquoted\u201d"}'
producer = subprocess.run(
    [
        sys.executable,
        "-c",
        "import sys; sys.stdout.buffer.write(" + repr(payload.encode("utf-8")) + ")",
    ],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)
if producer.returncode != 0:
    raise SystemExit("UTF-8 producer failed: " + producer.stderr)
if producer.stdout != payload:
    raise SystemExit("text=True did not decode UTF-8 exactly: " + repr(producer.stdout))
if json.loads(producer.stdout)["message"] != "Issue \u2014 \u201cquoted\u201d":
    raise SystemExit("decoded GitHub-style JSON changed Unicode content")
print("host-python-utf8-ok")
'''.strip()
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        (sys.executable, "-c", probe),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout = result.stdout.decode("utf-8", errors="strict").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    require(result.returncode == 0, stderr or stdout)
    require(stdout == "host-python-utf8-ok", stdout)


def main() -> int:
    tests = (
        test_decision_schema_becomes_strict,
        test_nonnullable_optional_property_is_rejected,
        test_provider_error_event_is_visible_without_raw_prompt,
        test_launcher_enables_host_python_utf8,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Codex supervisor turn smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
