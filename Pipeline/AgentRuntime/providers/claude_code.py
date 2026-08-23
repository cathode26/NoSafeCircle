"""Fail-closed Claude Code adapter for the initial Stage 4B boundary."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ..contracts import AgentRequest, Usage
from ..json_values import thaw_json
from ..process_runner import (
    ProcessResult,
    ProcessRunner,
    ProcessTimeoutError,
    StandardProcessRunner,
)
from .base import (
    ProviderFailure,
    ProviderInvocationResponse,
    ProviderOutputInvalid,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderTransportError,
)


_DISALLOWED_TOOLS = "Bash,Edit,Write,NotebookEdit,WebSearch,WebFetch"
_MODEL_ALIASES = frozenset({"default", "haiku", "opus", "sonnet"})
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MISSING = object()


class ClaudeCodeProvider:
    def __init__(
        self,
        *,
        executable: str = "claude",
        process_runner: ProcessRunner | None = None,
        temporary_directory_parent: Path | None = None,
    ) -> None:
        if type(executable) is not str or not executable:
            raise ValueError("executable must be a non-empty string")
        self.executable = executable
        self.process_runner = (
            StandardProcessRunner() if process_runner is None else process_runner
        )
        self.temporary_directory_parent = (
            None
            if temporary_directory_parent is None
            else Path(temporary_directory_parent)
        )

    @property
    def provider_identifier(self) -> str:
        return "claude-code"

    def invoke(
        self,
        request: AgentRequest,
        model: str,
    ) -> ProviderInvocationResponse:
        self._validate_request_policy(request)
        self._validate_model(model)
        argv = self._build_argv(request, model)
        prompt = self._prompt(request)

        parent = self._temporary_parent()
        try:
            with tempfile.TemporaryDirectory(
                prefix="agent-runtime-claude-",
                dir=parent,
            ) as temporary:
                result = self._run(
                    argv,
                    prompt,
                    Path(temporary),
                    request.budgets.timeout_seconds,
                )
        except (ProviderTimeout, ProviderTransportError):
            raise
        except Exception as exc:
            raise ProviderTransportError(
                f"Claude Code temporary workspace setup failed: {type(exc).__name__}"
            ) from exc

        return self._response_from_result(result)

    @staticmethod
    def _validate_request_policy(request: AgentRequest) -> None:
        if request.allowed_capabilities:
            raise ProviderRequestRejected(
                "Claude Code currently requires an empty allowed_capabilities set"
            )
        if request.context_paths:
            raise ProviderRequestRejected(
                "Claude Code currently requires empty context_paths"
            )
        if request.budgets.token_limit is not None:
            raise ProviderRequestRejected(
                "Claude Code currently requires token_limit to be null"
            )

    @staticmethod
    def _validate_model(model: str) -> None:
        if (
            type(model) is not str
            or not model
            or model != model.strip()
            or model.casefold() in _MODEL_ALIASES
            or not model.startswith("claude-")
        ):
            raise ProviderTransportError(
                "Claude Code requires a concrete configured Claude model identifier"
            )

    def _build_argv(
        self,
        request: AgentRequest,
        model: str,
    ) -> tuple[str, ...]:
        try:
            schema = json.dumps(
                thaw_json(request.output_schema),
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except Exception as exc:
            raise ProviderTransportError(
                "Claude Code output schema serialization failed"
            ) from exc
        return (
            self.executable,
            "-p",
            "--safe-mode",
            "--model",
            model,
            "--max-turns",
            str(request.budgets.turn_limit),
            "--permission-mode",
            "dontAsk",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--json-schema",
            schema,
            "--no-session-persistence",
            "--tools",
            "",
            "--disallowedTools",
            _DISALLOWED_TOOLS,
        )

    @staticmethod
    def _prompt(request: AgentRequest) -> bytes:
        try:
            return request.prompt.encode("utf-8")
        except UnicodeError as exc:
            raise ProviderTransportError(
                "Claude Code prompt could not be encoded as UTF-8"
            ) from exc

    def _temporary_parent(self) -> str:
        parent = (
            Path(tempfile.gettempdir())
            if self.temporary_directory_parent is None
            else self.temporary_directory_parent
        )
        try:
            resolved_parent = parent.resolve(strict=True)
            if not resolved_parent.is_dir():
                raise ProviderTransportError(
                    "temporary_directory_parent must be an existing directory"
                )
            if resolved_parent == _SOURCE_REPOSITORY_ROOT or resolved_parent.is_relative_to(
                _SOURCE_REPOSITORY_ROOT
            ):
                raise ProviderTransportError(
                    "temporary_directory_parent must be outside the repository"
                )
        except ProviderTransportError:
            raise
        except (OSError, RuntimeError) as exc:
            raise ProviderTransportError(
                "temporary_directory_parent could not be inspected"
            ) from exc
        return str(resolved_parent)

    def _run(
        self,
        argv: tuple[str, ...],
        prompt: bytes,
        cwd: Path,
        timeout_seconds: float,
    ) -> ProcessResult:
        try:
            result = self.process_runner.run(
                argv,
                stdin=prompt,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
        except ProcessTimeoutError as exc:
            if type(exc.result) is not ProcessResult or exc.result.argv != argv:
                raise ProviderTransportError(
                    "Claude Code timeout transport returned invalid local metadata"
                ) from exc
            raw_log = _decode_stdout(exc.result.stdout)
            detail = _safe_stderr(exc.result.stderr)
            message = "Claude Code invocation exceeded its external timeout"
            if detail:
                message = f"{message}: {detail}"
            raise ProviderTimeout(message, raw_log=raw_log) from exc
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as exc:
            raise ProviderTransportError(
                f"Claude Code process transport failed: {type(exc).__name__}"
            ) from exc
        if type(result) is not ProcessResult or result.argv != argv:
            raise ProviderTransportError(
                "Claude Code process transport returned invalid local metadata"
            )
        return result

    @staticmethod
    def _response_from_result(result: ProcessResult) -> ProviderInvocationResponse:
        raw_log = _decode_stdout(result.stdout)
        stderr = _safe_stderr(result.stderr)
        if result.returncode != 0:
            detail = stderr or _nonzero_envelope_detail(raw_log)
            message = f"Claude Code exited with status {result.returncode}"
            if detail:
                message = f"{message}: {detail}"
            raise ProviderFailure(message, raw_log=raw_log)
        if result.stderr:
            detail = stderr or "non-empty stderr"
            raise ProviderTransportError(
                f"Claude Code exited successfully with unexpected stderr: {detail}",
                raw_log=raw_log,
            )

        envelope = _parse_envelope(raw_log)
        _require_success(envelope, raw_log)
        try:
            usage = _normalize_usage(envelope)
        except ProviderTransportError as exc:
            raise ProviderTransportError(str(exc), raw_log=raw_log) from exc
        return ProviderInvocationResponse(
            envelope["structured_output"],
            raw_log,
            (),
            usage,
            False,
            (),
        )


def _decode_stdout(stdout: bytes) -> str:
    try:
        return stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProviderTransportError(
            "Claude Code stdout was not valid UTF-8"
        ) from exc


def _safe_stderr(stderr: bytes) -> str:
    return stderr.decode("utf-8", errors="replace").strip()


def _strict_json_object(raw_log: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    value = json.loads(
        raw_log,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )
    if type(value) is not dict:
        raise ValueError("Claude Code output must be one JSON object")
    return value


def _parse_envelope(raw_log: str) -> dict[str, Any]:
    try:
        return _strict_json_object(raw_log)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ProviderOutputInvalid(
            "Claude Code stdout was not one valid JSON object",
            raw_log=raw_log,
        ) from exc


def _require_success(envelope: Mapping[str, Any], raw_log: str) -> None:
    required = ("type", "is_error", "subtype", "terminal_reason")
    if any(field not in envelope for field in required):
        raise ProviderOutputInvalid(
            "Claude Code result envelope is missing required fields",
            raw_log=raw_log,
        )
    expected_types = {
        "type": str,
        "is_error": bool,
        "subtype": str,
        "terminal_reason": str,
    }
    if any(type(envelope[field]) is not expected for field, expected in expected_types.items()):
        raise ProviderOutputInvalid(
            "Claude Code result envelope has malformed status metadata",
            raw_log=raw_log,
        )
    if envelope["type"] != "result":
        raise ProviderOutputInvalid(
            "Claude Code output did not contain a result envelope",
            raw_log=raw_log,
        )

    permission_denials = envelope.get("permission_denials", _MISSING)
    if permission_denials is not _MISSING and type(permission_denials) is not list:
        raise ProviderOutputInvalid(
            "Claude Code result envelope has malformed permission_denials metadata",
            raw_log=raw_log,
        )
    if permission_denials is not _MISSING and permission_denials:
        raise ProviderFailure(
            "Claude Code reported one or more permission denials",
            raw_log=raw_log,
        )

    if (
        envelope["is_error"] is not False
        or envelope["subtype"] != "success"
        or envelope["terminal_reason"] != "completed"
    ):
        raise ProviderFailure(_unsuccessful_detail(envelope), raw_log=raw_log)
    if "structured_output" not in envelope:
        raise ProviderOutputInvalid(
            "Claude Code result envelope has no structured_output candidate",
            raw_log=raw_log,
        )


def _unsuccessful_detail(envelope: Mapping[str, Any]) -> str:
    fields = (
        f"is_error={envelope.get('is_error')!r}",
        f"subtype={envelope.get('subtype')!r}",
        f"terminal_reason={envelope.get('terminal_reason')!r}",
    )
    result = envelope.get("result")
    suffix = f": {result}" if type(result) is str and result.strip() else ""
    return f"Claude Code reported an unsuccessful result ({', '.join(fields)}){suffix}"


def _nonzero_envelope_detail(raw_log: str) -> str:
    try:
        envelope = _strict_json_object(raw_log)
    except (json.JSONDecodeError, ValueError, RecursionError):
        return ""
    return _unsuccessful_detail(envelope)


def _normalize_usage(envelope: Mapping[str, Any]) -> Usage | None:
    model_usage = envelope.get("modelUsage", _MISSING)
    if model_usage is not _MISSING:
        if type(model_usage) is not dict:
            raise ProviderTransportError("Claude Code modelUsage must be an object")
        if not model_usage:
            raise ProviderTransportError("Claude Code modelUsage must not be empty")
        input_tokens = 0
        output_tokens = 0
        for model, entry in model_usage.items():
            if type(model) is not str or type(entry) is not dict:
                raise ProviderTransportError(
                    "Claude Code modelUsage entries must be named objects"
                )
            model_input = sum(
                _token(entry, field, where=f"modelUsage.{model}")
                for field in (
                    "inputTokens",
                    "cacheReadInputTokens",
                    "cacheCreationInputTokens",
                )
            )
            model_output = _token(entry, "outputTokens", where=f"modelUsage.{model}")
            _check_reported_total(
                entry,
                "totalTokens",
                model_input + model_output,
                where=f"modelUsage.{model}",
            )
            input_tokens += model_input
            output_tokens += model_output
        return Usage(
            input_tokens,
            output_tokens,
            input_tokens + output_tokens,
            _cost(envelope),
        )

    top_level = envelope.get("usage", _MISSING)
    if top_level is _MISSING:
        if "total_cost_usd" in envelope:
            _cost(envelope)
        return None
    if type(top_level) is not dict:
        raise ProviderTransportError("Claude Code usage must be an object")
    input_tokens = sum(
        _token(top_level, field, where="usage")
        for field in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
    )
    output_tokens = _token(top_level, "output_tokens", where="usage")
    _check_reported_total(
        top_level,
        "total_tokens",
        input_tokens + output_tokens,
        where="usage",
    )
    return Usage(
        input_tokens,
        output_tokens,
        input_tokens + output_tokens,
        _cost(envelope),
    )


def _token(value: Mapping[str, Any], field: str, *, where: str) -> int:
    token = value.get(field, _MISSING)
    if isinstance(token, bool) or not isinstance(token, int) or token < 0:
        raise ProviderTransportError(
            f"Claude Code {where}.{field} must be a non-negative integer"
        )
    return token


def _check_reported_total(
    value: Mapping[str, Any],
    field: str,
    expected: int,
    *,
    where: str,
) -> None:
    reported = value.get(field, _MISSING)
    if reported is _MISSING:
        return
    if (
        isinstance(reported, bool)
        or not isinstance(reported, int)
        or reported < 0
        or reported != expected
    ):
        raise ProviderTransportError(
            f"Claude Code {where}.{field} is internally inconsistent"
        )


def _cost(envelope: Mapping[str, Any]) -> float | None:
    cost = envelope.get("total_cost_usd", _MISSING)
    if cost is _MISSING:
        return None
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ProviderTransportError(
            "Claude Code total_cost_usd must be finite and non-negative"
        )
    return cost
