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
from Pipeline.AgentRuntime.provider_sessions import (  # noqa: E402
    ProviderSessionBinding,
    ProviderSessionError,
    ProviderSessionLedger,
)
from Pipeline.AgentRuntime.providers.base import ProviderInvocationError  # noqa: E402
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider  # noqa: E402


TURN_REQUEST_SCHEMA_VERSION = "1.0"
# 1.1 adds the optional ``provider_session`` block: the host's exact start or
# resume binding for a pooled supervisor conversation. A 1.0 request is the
# historical ephemeral turn, byte for byte.
POOLED_TURN_REQUEST_SCHEMA_VERSION = "1.1"
TURN_RESPONSE_SCHEMA_VERSION = "1.1"
SUPERVISOR_ROLE = "task_supervisor"
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
_POOLED_FIELDS = _EXPECTED_FIELDS | {"provider_session"}
_SESSION_FIELDS = {"mode", "session_id", "resume_sandbox_argument"}


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


def _schema_types(value: Any, *, field: str) -> tuple[str, ...]:
    if type(value) is str and value:
        return (value,)
    if (
        isinstance(value, list)
        and value
        and all(type(item) is str and item for item in value)
        and len(set(value)) == len(value)
    ):
        return tuple(value)
    raise SupervisorTurnError(f"{field}.type must be a string or unique string array")


def _strict_output_schema(value: Any, *, path: str = "$") -> dict[str, Any]:
    """Convert nullable optional fields into strict required nullable fields.

    Codex ``--output-schema`` uses OpenAI Structured Outputs. Every declared
    object property must therefore appear in that object's ``required`` array.
    The host decision contract models unused action arguments as nullable, so
    making those fields required preserves the intended semantics: an unused
    argument is emitted as JSON null and is filtered by the host validator.
    """

    try:
        result = json.loads(
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise SupervisorTurnError(f"{path} must be finite JSON") from exc
    if not isinstance(result, dict):
        raise SupervisorTurnError(f"{path} must be a JSON Schema object")

    kinds = _schema_types(result.get("type"), field=path)
    if "object" in kinds:
        properties = result.get("properties", {})
        if not isinstance(properties, dict) or any(
            type(name) is not str for name in properties
        ):
            raise SupervisorTurnError(f"{path}.properties must be an object")
        required = result.get("required", [])
        if (
            not isinstance(required, list)
            or any(type(name) is not str for name in required)
            or len(set(required)) != len(required)
            or any(name not in properties for name in required)
        ):
            raise SupervisorTurnError(
                f"{path}.required must contain unique declared property names"
            )
        for name, child in properties.items():
            child_path = f"{path}.properties.{name}"
            properties[name] = _strict_output_schema(child, path=child_path)
            if name not in required:
                child_types = _schema_types(
                    properties[name].get("type"),
                    field=child_path,
                )
                if "null" not in child_types:
                    raise SupervisorTurnError(
                        f"{child_path} is optional but does not allow null"
                    )
        result["properties"] = properties
        result["required"] = list(properties)
    if "array" in kinds:
        if "items" not in result:
            raise SupervisorTurnError(f"{path}.items is required for arrays")
        result["items"] = _strict_output_schema(
            result["items"],
            path=f"{path}.items",
        )
    return result


def _error_text(value: Any) -> list[str]:
    if type(value) is str and value.strip():
        return [value.strip()]
    if isinstance(value, Mapping):
        messages: list[str] = []
        for key in ("message", "error", "detail", "reason", "code"):
            if key in value:
                messages.extend(_error_text(value[key]))
        return messages
    if isinstance(value, list):
        messages: list[str] = []
        for item in value:
            messages.extend(_error_text(item))
        return messages
    return []


def _provider_failure_detail(exc: ProviderInvocationError) -> str:
    """Return bounded provider diagnostics without echoing prompts or credentials."""

    messages: list[str] = []
    event_types: list[str] = []
    raw_log = getattr(exc, "raw_log", "")
    if isinstance(raw_log, str):
        for line in raw_log.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, Mapping):
                continue
            event_type = event.get("type")
            if type(event_type) is str and event_type:
                event_types.append(event_type)
            if (
                type(event_type) is str
                and ("error" in event_type.casefold() or "fail" in event_type.casefold())
            ):
                messages.extend(_error_text(event))
    unique_messages = list(dict.fromkeys(messages))[:8]
    if unique_messages:
        return str(exc) + "\nCodex error events:\n- " + "\n- ".join(unique_messages)
    unique_types = list(dict.fromkeys(event_types))[-12:]
    if unique_types:
        return str(exc) + "\nCodex JSONL event types: " + ", ".join(unique_types)
    return str(exc)


def _request() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SupervisorTurnError("stdin must contain valid UTF-8 JSON") from exc
    request = _object(value, field="turn request")
    version = request.get("schema_version")
    if version == TURN_REQUEST_SCHEMA_VERSION:
        expected = _EXPECTED_FIELDS
    elif version == POOLED_TURN_REQUEST_SCHEMA_VERSION:
        expected = _POOLED_FIELDS
    else:
        raise SupervisorTurnError("unsupported turn request schema_version")
    if set(request) != expected:
        raise SupervisorTurnError(
            "turn request fields mismatch; "
            f"missing={sorted(expected-set(request))}, "
            f"extras={sorted(set(request)-expected)}"
        )
    if version == POOLED_TURN_REQUEST_SCHEMA_VERSION:
        request["provider_session"] = _provider_session(request.get("provider_session"))
    request["run_id"] = _text(request.get("run_id"), field="run_id")
    request["prompt"] = _text(request.get("prompt"), field="prompt")
    request["output_schema"] = _strict_output_schema(
        _object(
            request.get("output_schema"),
            field="output_schema",
        )
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


def _provider_session(value: Any) -> dict[str, Any]:
    """Validate the host's exact pooled-session binding without guessing.

    The host names the mode and, for a resume, the exact UUID. A start binds
    no identity because Codex assigns its thread UUID itself; the adapter
    captures that identity from the transcript and this script reports it
    back. The resume control is the operator-verified argv fragment the
    adapter requires before it will run ``codex exec resume`` at all.
    """

    session = _object(value, field="provider_session")
    if set(session) != _SESSION_FIELDS:
        raise SupervisorTurnError(
            "provider_session fields mismatch; "
            f"missing={sorted(_SESSION_FIELDS-set(session))}, "
            f"extras={sorted(set(session)-_SESSION_FIELDS)}"
        )
    mode = session.get("mode")
    session_id = session.get("session_id")
    if mode == "start":
        if session_id is not None:
            raise SupervisorTurnError(
                "a pooled Codex start must not bind a session_id; Codex assigns it"
            )
    elif mode == "resume":
        if type(session_id) is not str or not session_id:
            raise SupervisorTurnError("a pooled resume requires the exact session_id")
    else:
        raise SupervisorTurnError("provider_session.mode must be exactly 'start' or 'resume'")
    argument = session.get("resume_sandbox_argument")
    if argument is not None and (
        not isinstance(argument, list)
        or not argument
        or any(type(item) is not str or not item for item in argument)
    ):
        raise SupervisorTurnError(
            "provider_session.resume_sandbox_argument must be null or a non-empty list of strings"
        )
    try:
        binding = ProviderSessionBinding("openai-codex", SUPERVISOR_ROLE, mode, session_id)
    except ProviderSessionError as exc:
        raise SupervisorTurnError(f"provider_session binding is invalid: {exc}") from exc
    return {
        "binding": binding,
        "resume_sandbox_argument": None if argument is None else tuple(argument),
    }


def _emit_failure(
    classification: str,
    detail: str,
    ledger: ProviderSessionLedger | None,
) -> None:
    """Report a failed turn on both channels.

    stderr keeps the bounded human-readable diagnostic. stdout carries one
    machine-readable failure envelope so the host can settle a pooled
    conversation from durable proof: the exact classification and whichever
    identity the transcript confirmed before the turn failed, or null.
    """

    print(f"CODEX SUPERVISOR TURN: STOP\n{detail}", file=sys.stderr, flush=True)
    envelope = {
        "schema_version": TURN_RESPONSE_SCHEMA_VERSION,
        "failure": {"classification": classification, "detail": detail},
        "provider_session_confirmation": (
            None if ledger is None else ledger.to_dict()
        ),
    }
    print(
        json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )


def main() -> int:
    ledger: ProviderSessionLedger | None = None
    try:
        raw = _request()
        session = raw.get("provider_session")
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
        provider_options: dict[str, Any] = {
            "reasoning_effort": raw["reasoning_effort"],
            "executable": "codex",
            "repository_root": ROOT,
        }
        if session is not None:
            # A pooled turn is the ephemeral turn plus exactly one difference:
            # the adapter binds the host's session and proves the identity it
            # actually used. Every other control (schema, model, effort,
            # budgets, empty capabilities) is restated on every turn.
            ledger = ProviderSessionLedger()
            provider_options["session"] = session["binding"]
            provider_options["session_ledger"] = ledger
            provider_options["resume_sandbox_argument"] = session["resume_sandbox_argument"]
        provider = OpenAICodexProvider(**provider_options)
        response = provider.invoke(invocation, raw["model"])
        result = {
            "schema_version": TURN_RESPONSE_SCHEMA_VERSION,
            "structured_output": thaw_json(response.structured_output),
            "usage": None if response.usage is None else response.usage.to_dict(),
            "provider_session_confirmation": (
                None if ledger is None else ledger.to_dict()
            ),
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
    except ProviderInvocationError as exc:
        _emit_failure(type(exc).__name__, _provider_failure_detail(exc), ledger)
        return 2
    except (SupervisorTurnError, ValueError) as exc:
        _emit_failure(type(exc).__name__, str(exc), ledger)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
