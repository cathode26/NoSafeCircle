#!/usr/bin/env python3
"""Run one structured goal-supervisor decision through authenticated Codex CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    Budgets,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.json_values import thaw_json  # noqa: E402
from Pipeline.AgentRuntime.providers.base import ProviderInvocationError  # noqa: E402
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider  # noqa: E402


TURN_REQUEST_SCHEMA_VERSION = "1.0"
TURN_RESPONSE_SCHEMA_VERSION = "1.0"
_EXPECTED_FIELDS = {
    "schema_version",
    "run_id",
    "prompt",
    "output_schema",
    "model",
    "reasoning_effort",
    "provider_turn_limit",
    "timeout_seconds",
}


class SupervisorTurnError(ValueError):
    """Raised when the host-to-container turn request is malformed."""


def _object(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SupervisorTurnError(f"{field} must be one JSON object")
    return dict(value)


def _text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise SupervisorTurnError(f"{field} must be a non-empty string")
    return value.strip()


def _integer(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SupervisorTurnError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise SupervisorTurnError(f"{field} must be from {minimum} through {maximum}")
    return value


def _number(value: Any, *, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SupervisorTurnError(f"{field} must be a number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise SupervisorTurnError(f"{field} must be from {minimum} through {maximum}")
    return result


def _request() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SupervisorTurnError("stdin must contain valid UTF-8 JSON") from exc
    request = _object(value, field="turn request")
    if set(request) != _EXPECTED_FIELDS:
        raise SupervisorTurnError(
            "turn request fields mismatch; "
            f"missing={sorted(_EXPECTED_FIELDS-set(request))}, "
            f"extras={sorted(set(request)-_EXPECTED_FIELDS)}"
        )
    if request.get("schema_version") != TURN_REQUEST_SCHEMA_VERSION:
        raise SupervisorTurnError("unsupported turn request schema_version")
    request["run_id"] = _text(request.get("run_id"), field="run_id")
    request["prompt"] = _text(request.get("prompt"), field="prompt")
    request["output_schema"] = _object(
        request.get("output_schema"),
        field="output_schema",
    )
    request["model"] = _text(request.get("model"), field="model")
    request["reasoning_effort"] = _text(
        request.get("reasoning_effort"),
        field="reasoning_effort",
    )
    request["provider_turn_limit"] = _integer(
        request.get("provider_turn_limit"),
        field="provider_turn_limit",
        minimum=1,
        maximum=100,
    )
    request["timeout_seconds"] = _number(
        request.get("timeout_seconds"),
        field="timeout_seconds",
        minimum=1.0,
        maximum=3600.0,
    )
    return request


def main() -> int:
    try:
        raw = _request()
        invocation = AgentInvocationRequest(
            schema_version=AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
            run_id=raw["run_id"],
            role="task_supervisor",
            prompt=raw["prompt"],
            context_paths=(),
            allowed_capabilities=(),
            write_boundaries=WriteBoundaries((), ()),
            output_schema=raw["output_schema"],
            model_capability_class="high_reasoning",
            budgets=Budgets(
                turn_limit=raw["provider_turn_limit"],
                timeout_seconds=raw["timeout_seconds"],
                token_limit=None,
            ),
            provider_configuration_key="codex-task-supervisor",
        )
        provider = OpenAICodexProvider(
            reasoning_effort=raw["reasoning_effort"],
            executable="codex",
            repository_root=ROOT,
        )
        response = provider.invoke(invocation, raw["model"])
        result = {
            "schema_version": TURN_RESPONSE_SCHEMA_VERSION,
            "structured_output": thaw_json(response.structured_output),
            "usage": None if response.usage is None else response.usage.to_dict(),
        }
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        return 0
    except (SupervisorTurnError, ValueError, ProviderInvocationError) as exc:
        print(f"CODEX SUPERVISOR TURN: STOP\n{exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
