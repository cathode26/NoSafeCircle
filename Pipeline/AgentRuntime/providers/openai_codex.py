"""Fail-closed OpenAI Codex CLI adapter for generic AgentRuntime invocations."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ..contracts import AgentInvocationRequest, Usage
from ..json_values import thaw_json
from ..process_runner import ProcessResult, ProcessRunner, ProcessTimeoutError, StandardProcessRunner
from .base import (
    ProviderFailure, ProviderInvocationResponse, ProviderOutputInvalid,
    ProviderRequestRejected, ProviderTimeout, ProviderTransportError,
)

OPENAI_SECONDS_PER_TURN = 30
_REPOSITORY_CAPABILITIES = frozenset({"repository_read", "repository_search"})
_FORBIDDEN_CAPABILITIES = frozenset({"repository_write", "approved_command_execution"})
_VALID_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MISSING = object()


class OpenAICodexProvider:
    def __init__(
        self,
        *,
        reasoning_effort: str = "high",
        externally_enforced_read_only_repository: bool = False,
        executable: str = "codex",
        process_runner: ProcessRunner | None = None,
        temporary_directory_parent: Path | None = None,
        repository_root: Path | None = None,
    ) -> None:
        if type(executable) is not str or not executable:
            raise ValueError("executable must be a non-empty string")
        if reasoning_effort not in _VALID_REASONING_EFFORTS:
            raise ValueError("unsupported Codex reasoning effort")
        if type(externally_enforced_read_only_repository) is not bool:
            raise ValueError("read-only repository profile must be boolean")
        self.executable = executable
        self.reasoning_effort = reasoning_effort
        self.externally_enforced_read_only_repository = externally_enforced_read_only_repository
        self.process_runner = StandardProcessRunner() if process_runner is None else process_runner
        self.temporary_directory_parent = temporary_directory_parent
        self.repository_root = (
            _SOURCE_REPOSITORY_ROOT if repository_root is None else Path(repository_root)
        ).resolve()

    @property
    def provider_identifier(self) -> str:
        return "openai-codex"

    def invoke(self, request: AgentInvocationRequest, model: str) -> ProviderInvocationResponse:
        self._validate_request_policy(request)
        self._validate_model(model)
        parent = self._temporary_parent()
        try:
            with tempfile.TemporaryDirectory(prefix="agent-runtime-codex-", dir=parent) as text:
                temporary = Path(text)
                schema_path = temporary / "output-schema.json"
                final_path = temporary / "final-output.json"
                schema_path.write_text(
                    json.dumps(thaw_json(request.output_schema), allow_nan=False,
                               ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                    encoding="utf-8",
                )
                cwd = self.repository_root if request.allowed_capabilities else temporary
                argv = self._argv(model, schema_path, final_path)
                result = self._run(
                    argv, self._prompt(request), cwd,
                    min(request.budgets.timeout_seconds,
                        request.budgets.turn_limit * OPENAI_SECONDS_PER_TURN),
                )
                return self._response(result, final_path)
        except (ProviderFailure, ProviderOutputInvalid, ProviderTimeout,
                ProviderRequestRejected, ProviderTransportError):
            raise
        except Exception as exc:
            raise ProviderTransportError(
                f"Codex local temporary-file transport failed: {type(exc).__name__}"
            ) from exc

    def _validate_request_policy(self, request: AgentInvocationRequest) -> None:
        capabilities = frozenset(request.allowed_capabilities)
        if capabilities & _FORBIDDEN_CAPABILITIES:
            raise ProviderRequestRejected(
                "Codex does not support repository writing or approved command execution"
            )
        if not capabilities <= _REPOSITORY_CAPABILITIES:
            raise ProviderRequestRejected("Codex capability set is unsupported")
        if request.context_paths and not capabilities:
            raise ProviderRequestRejected("Codex requires repository capability for context_paths")
        if capabilities and not self.externally_enforced_read_only_repository:
            raise ProviderRequestRejected(
                "Codex repository access requires an explicit externally read-only profile"
            )
        if request.budgets.token_limit is not None:
            raise ProviderRequestRejected("Codex currently requires token_limit to be null")

    @staticmethod
    def _validate_model(model: str) -> None:
        if type(model) is not str or not model or model != model.strip():
            raise ProviderTransportError("Codex requires a concrete configured model identifier")

    def _argv(self, model: str, schema_path: Path, final_path: Path) -> tuple[str, ...]:
        return (
            self.executable, "exec", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--strict-config", "--skip-git-repo-check",
            "--sandbox", "danger-full-access", "--model", model,
            "-c", f"model_reasoning_effort={self.reasoning_effort}",
            "--output-schema", str(schema_path), "--json",
            "--output-last-message", str(final_path), "--color", "never", "-",
        )

    def _prompt(self, request: AgentInvocationRequest) -> bytes:
        prompt = request.prompt
        if request.allowed_capabilities:
            hints = ""
            if request.context_paths:
                hints = "\nRelevant repository paths:\n" + "\n".join(
                    f"- {path}" for path in request.context_paths
                )
            prompt += (
                "\n\nRepository context:\n"
                f"Repository root: {self.repository_root.as_posix()}\n"
                "The surrounding environment mounts this repository read-only. "
                "Inspect it with ordinary read-only file and search commands. "
                "Context paths are guidance, not an access allowlist."
                f"{hints}"
            )
        try:
            return prompt.encode("utf-8")
        except UnicodeError as exc:
            raise ProviderTransportError("Codex prompt could not be encoded as UTF-8") from exc

    def _temporary_parent(self) -> str:
        parent = Path(tempfile.gettempdir()) if self.temporary_directory_parent is None else Path(self.temporary_directory_parent)
        try:
            resolved = parent.resolve(strict=True)
            if not resolved.is_dir() or resolved == self.repository_root or resolved.is_relative_to(self.repository_root):
                raise ProviderTransportError("temporary directory parent must be outside the repository")
        except ProviderTransportError:
            raise
        except (OSError, RuntimeError) as exc:
            raise ProviderTransportError("temporary directory parent could not be inspected") from exc
        return str(resolved)

    def _run(self, argv: tuple[str, ...], stdin: bytes, cwd: Path, timeout: float) -> ProcessResult:
        try:
            result = self.process_runner.run(argv, stdin=stdin, cwd=cwd, timeout_seconds=timeout)
        except ProcessTimeoutError as exc:
            if type(exc.result) is not ProcessResult or exc.result.argv != argv:
                raise ProviderTransportError("Codex timeout returned invalid local metadata") from exc
            raise ProviderTimeout(
                "Codex invocation exceeded its external timeout",
                raw_log=_decode_stdout(exc.result.stdout),
            ) from exc
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as exc:
            raise ProviderTransportError(f"Codex process transport failed: {type(exc).__name__}") from exc
        if type(result) is not ProcessResult or result.argv != argv:
            raise ProviderTransportError("Codex process transport returned invalid local metadata")
        return result

    @staticmethod
    def _response(result: ProcessResult, final_path: Path) -> ProviderInvocationResponse:
        raw_log = _decode_stdout(result.stdout)
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            raise ProviderFailure(
                f"Codex exited with status {result.returncode}" + (f": {stderr}" if stderr else ""),
                raw_log=raw_log,
            )
        if result.stderr:
            raise ProviderTransportError(
                f"Codex exited successfully with unexpected stderr: {stderr or 'non-empty stderr'}",
                raw_log=raw_log,
            )
        events = _parse_jsonl(raw_log)
        completed = [event for event in events if event.get("type") == "turn.completed"]
        if not completed:
            raise ProviderOutputInvalid("Codex transcript has no completed turn", raw_log=raw_log)
        usage = _normalize_usage(completed[-1], raw_log)
        if not final_path.is_file():
            raise ProviderOutputInvalid("Codex final structured output file is missing", raw_log=raw_log)
        try:
            candidate = _strict_json(final_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ProviderOutputInvalid("Codex final structured output is invalid JSON", raw_log=raw_log) from exc
        return ProviderInvocationResponse(candidate, raw_log, (), usage, False, ())


def _decode_stdout(stdout: bytes) -> str:
    try:
        return stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ProviderTransportError("Codex stdout was not valid UTF-8") from exc


def _strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=reject_duplicates)


def _parse_jsonl(raw_log: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        for line in raw_log.splitlines():
            if not line.strip():
                raise ValueError("blank JSONL record")
            event = _strict_json(line)
            if type(event) is not dict or type(event.get("type")) is not str:
                raise ValueError("event must be an object with a string type")
            events.append(event)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ProviderOutputInvalid("Codex stdout was malformed JSONL", raw_log=raw_log) from exc
    if not events:
        raise ProviderOutputInvalid("Codex stdout was empty", raw_log=raw_log)
    return events


def _normalize_usage(event: Mapping[str, Any], raw_log: str) -> Usage | None:
    usage = event.get("usage", _MISSING)
    if usage is _MISSING:
        return None
    if type(usage) is not dict:
        raise ProviderTransportError("Codex completed-turn usage must be an object", raw_log=raw_log)
    def token(name: str) -> int:
        value = usage.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ProviderTransportError(f"Codex usage.{name} must be a non-negative integer", raw_log=raw_log)
        return value
    input_tokens = token("input_tokens")
    output_tokens = token("output_tokens") + token("reasoning_output_tokens")
    total = input_tokens + output_tokens
    reported_total = usage.get("total_tokens", total)
    if isinstance(reported_total, bool) or not isinstance(reported_total, int) or reported_total < 0:
        raise ProviderTransportError("Codex usage.total_tokens is invalid", raw_log=raw_log)
    return Usage(input_tokens, output_tokens, total, None)
