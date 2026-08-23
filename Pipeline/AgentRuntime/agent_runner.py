"""Immutable run artifact publisher and provider outcome normalizer."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

from .config import ProviderSelection, RuntimeConfiguration
from .contracts import (
    AGENT_RESULT_SCHEMA_VERSION,
    AgentInvocationRequest,
    AgentResult,
    ContractValidationError,
)
from .json_values import JsonValueError, freeze_json, validate_json, validate_text
from .providers.base import (
    ProviderBudgetExhausted,
    ProviderFailure,
    ProviderInvocationError,
    ProviderInvocationResponse,
    ProviderOutputInvalid,
    ProviderPermissionDenied,
    ProviderRequestRejected,
    ProviderTransportError,
    ProviderTimeout,
)
from .schema_validation import SchemaValidationError, validate_instance


class RunAlreadyExistsError(FileExistsError):
    pass


def _safe_exception_message(exception: BaseException) -> str:
    try:
        message = str.__str__(str(exception))
        validate_text(message, path="exception diagnostic")
    except Exception:
        try:
            detail = repr(exception)
        except Exception:
            detail = f"<{type(exception).__name__}>"
        message = detail.encode("ascii", "backslashreplace").decode("ascii")
    if not message.strip():
        return type(exception).__name__
    return message


def _valid_raw_log(value: Any) -> tuple[str, str | None]:
    if not isinstance(value, str):
        return "", "provider raw_log was rejected: it must be text"
    try:
        validate_text(value, path="provider raw_log")
    except JsonValueError:
        return "", "provider raw_log was rejected: it must be valid UTF-8"
    return value, None


def _publish(path: Path, content: str) -> None:
    if not isinstance(content, str):
        raise TypeError("artifact content must be text")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _json(value: Any) -> str:
    validate_json(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


class AgentRunner:
    def __init__(
        self,
        run_root: Path,
        configuration: RuntimeConfiguration,
        registry: Mapping[str, Any],
    ) -> None:
        self.run_root = Path(run_root)
        if type(configuration) is not RuntimeConfiguration:
            raise ContractValidationError(
                "configuration must be an exact RuntimeConfiguration"
            )
        self.configuration = configuration
        self.registry = dict(registry)

    def run(self, request: AgentInvocationRequest) -> AgentResult:
        if type(request) is not AgentInvocationRequest:
            raise ContractValidationError("request must be an exact AgentInvocationRequest")

        run_dir = self._create_run_directory(request)
        try:
            _publish(run_dir / "request.json", _json(AgentInvocationRequest.to_dict(request)))
        except BaseException:
            try:
                run_dir.rmdir()
            except OSError:
                pass
            raise

        try:
            selection = self.configuration.resolve(
                request.provider_configuration_key,
                request.model_capability_class,
                self.registry,
            )
        except Exception as exc:
            return self._publish_failure(
                request, run_dir, None, "invalid_request",
                _safe_exception_message(exc), "", 0.0,
            )

        provider = self.registry[selection.provider]
        try:
            provider_identifier = provider.provider_identifier
        except Exception as exc:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                f"invalid provider identity metadata: {_safe_exception_message(exc)}", "", 0.0,
            )
        if provider_identifier != selection.provider:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                "provider registry identity mismatch", "", 0.0,
            )

        return self._invoke_and_publish(request, run_dir, selection, provider)

    def _create_run_directory(self, request: AgentInvocationRequest) -> Path:
        self.run_root.mkdir(parents=True, exist_ok=True)
        run_dir = self.run_root / request.run_id
        try:
            run_dir.mkdir()
        except FileExistsError as exc:
            raise RunAlreadyExistsError(
                f"run directory already exists: {request.run_id}"
            ) from exc
        return run_dir

    def _invoke_and_publish(
        self,
        request: AgentInvocationRequest,
        run_dir: Path,
        selection: ProviderSelection,
        provider: Any,
    ) -> AgentResult:
        started = time.monotonic()
        try:
            response = provider.invoke(request, selection.model)
        except ProviderTimeout as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "timeout", exc, started
            )
        except ProviderPermissionDenied as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "permission_denied", exc, started
            )
        except ProviderBudgetExhausted as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "budget_exhausted", exc, started
            )
        except ProviderOutputInvalid as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "schema_error", exc, started
            )
        except ProviderRequestRejected as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "invalid_request", exc, started
            )
        except ProviderTransportError as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "internal_error", exc, started
            )
        except (ProviderFailure, ProviderInvocationError) as exc:
            return self._provider_exception_result(
                request, run_dir, selection, "provider_error", exc, started
            )
        except Exception as exc:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                f"provider raised {type(exc).__name__}: {_safe_exception_message(exc)}", "",
                time.monotonic() - started,
            )

        duration = time.monotonic() - started
        if type(response) is not ProviderInvocationResponse:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                "provider returned an invalid response container", "", duration,
            )
        structured_output, raw_log_owned, changed_owned, usage, execution, tests_owned = (
            response.structured_output,
            response.raw_log,
            response.claimed_changed_paths,
            response.usage,
            response.claims_execution_occurred,
            response.claimed_test_commands,
        )
        raw_log, raw_log_error = _valid_raw_log(raw_log_owned)
        if raw_log_error is not None:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                raw_log_error, "", duration,
            )

        try:
            if not isinstance(changed_owned, (list, tuple)):
                raise ContractValidationError("claimed_changed_paths must be an array")
            if not isinstance(tests_owned, (list, tuple)):
                raise ContractValidationError("claimed_test_commands must be an array")
            changed = tuple(changed_owned)
            tests = tuple(tests_owned)
            metadata_result = AgentResult(
                AGENT_RESULT_SCHEMA_VERSION, request.run_id, selection.provider, selection.model,
                request.role, "failed", "schema_error", "structured output rejected",
                None, changed, duration, usage, "provider.log", execution, tests,
            )
        except Exception as exc:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                f"invalid provider response metadata: {_safe_exception_message(exc)}",
                raw_log, duration,
            )

        try:
            frozen_output = freeze_json(structured_output, path="$.structured_output")
            validate_instance(frozen_output, request.output_schema)
        except (JsonValueError, SchemaValidationError) as exc:
            return self._publish_result(
                request, run_dir,
                AgentResult(
                    AGENT_RESULT_SCHEMA_VERSION, request.run_id, selection.provider,
                    selection.model, request.role, "failed", "schema_error",
                    _safe_exception_message(exc), None,
                    metadata_result.claimed_changed_paths, duration,
                    metadata_result.usage, "provider.log",
                    metadata_result.claims_execution_occurred,
                    metadata_result.claimed_test_commands,
                ),
                raw_log,
            )

        try:
            result = AgentResult(
                AGENT_RESULT_SCHEMA_VERSION, request.run_id, selection.provider,
                selection.model, request.role, "succeeded", "none", None,
                frozen_output, metadata_result.claimed_changed_paths,
                duration, metadata_result.usage, "provider.log",
                metadata_result.claims_execution_occurred,
                metadata_result.claimed_test_commands,
            )
        except Exception as exc:
            return self._publish_failure(
                request, run_dir, selection, "internal_error",
                f"invalid provider response metadata: {_safe_exception_message(exc)}",
                raw_log, duration,
            )
        return self._publish_result(request, run_dir, result, raw_log)

    def _provider_exception_result(
        self,
        request: AgentInvocationRequest,
        run_dir: Path,
        selection: ProviderSelection,
        classification: str,
        exception: ProviderInvocationError,
        started: float,
    ) -> AgentResult:
        raw_log, raw_log_error = _valid_raw_log(exception.raw_log)
        message = _safe_exception_message(exception)
        if raw_log_error is not None:
            classification = "internal_error"
            message = raw_log_error
        return self._publish_failure(
            request, run_dir, selection, classification, message, raw_log,
            time.monotonic() - started,
        )

    def _publish_failure(
        self,
        request: AgentInvocationRequest,
        run_dir: Path,
        selection: ProviderSelection | None,
        classification: str,
        message: str,
        raw_log: str,
        duration: float,
    ) -> AgentResult:
        result = AgentResult(
            AGENT_RESULT_SCHEMA_VERSION, request.run_id,
            None if selection is None else selection.provider,
            None if selection is None else selection.model,
            request.role, "failed", classification, message, None, (),
            duration, None, "provider.log", False, (),
        )
        return self._publish_result(request, run_dir, result, raw_log)

    def _publish_result(
        self,
        request: AgentInvocationRequest,
        run_dir: Path,
        result: AgentResult,
        raw_log: str,
    ) -> AgentResult:
        _publish(run_dir / "provider.log", raw_log)
        self._validate_result_identity(request, result, run_dir)
        _publish(run_dir / "result.json", _json(result.to_dict()))
        return result

    @staticmethod
    def _validate_result_identity(
        request: AgentInvocationRequest,
        result: AgentResult,
        run_dir: Path,
    ) -> None:
        if result.run_id != request.run_id or result.role != request.role:
            raise ContractValidationError("result identity does not match request")
        target = (run_dir / result.raw_log_reference).resolve()
        try:
            target.relative_to(run_dir.resolve())
        except ValueError as exc:
            raise ContractValidationError(
                "raw_log_reference escapes run directory"
            ) from exc
