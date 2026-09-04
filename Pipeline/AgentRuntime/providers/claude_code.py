"""Fail-closed Claude Code adapter for the initial Stage 4B boundary."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable, IO, Mapping

from ..contracts import AgentInvocationRequest, Usage
from ..json_values import thaw_json
from ..provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionError,
    ProviderSessionLedger,
    prompt_with_resumed_authority,
    require_compatible_binding,
)
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


_READ_ONLY_DISALLOWED_TOOLS = "Bash,Edit,Write,NotebookEdit,WebSearch,WebFetch"
_WRITE_DISALLOWED_TOOLS = "Bash,NotebookEdit,WebSearch,WebFetch"
_READ_CAPABILITY_COMBINATIONS = frozenset(
    {
        frozenset(),
        frozenset({"repository_read"}),
        frozenset({"repository_search"}),
        frozenset({"repository_read", "repository_search"}),
    }
)
_WRITE_CAPABILITIES = frozenset(
    {"repository_read", "repository_search", "repository_write"}
)
_MODEL_ALIASES = frozenset({"default", "haiku", "opus", "sonnet"})
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MISSING = object()


class ClaudeLiveRenderer:
    """Best-effort human-readable renderer for live Claude Code NDJSON events.

    Presentation-only: every failure here is swallowed so a rendering bug can
    never affect provider truth. The authoritative transcript is always
    reparsed independently and strictly by ``_parse_stream`` once the
    invocation completes; this renderer never gates or replaces that check.
    Thinking content, thinking signatures, raw tool_result payloads, and
    duplicate assistant text are intentionally never written here.
    """

    def __init__(self, *, stream: IO[str] | None = None, label: str = "Claude") -> None:
        self._stream: IO[str] = sys.stderr if stream is None else stream
        self._label = label
        self._buffer = b""
        self._inline_open = False

    def feed(self, chunk: bytes) -> None:
        try:
            self._buffer += chunk
            while b"\n" in self._buffer:
                raw_line, self._buffer = self._buffer.split(b"\n", 1)
                self._handle_line(raw_line)
        except Exception:
            pass

    def _handle_line(self, raw_line: bytes) -> None:
        text = raw_line.rstrip(b"\r").decode("utf-8", "replace").strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "stream_event":
            self._handle_stream_event(event)
        elif event_type == "result":
            self._handle_result(event)
        # assistant/user/system/rate_limit_event lines are intentionally not
        # rendered here: assistant text already streams via text_delta, tool
        # results/system/rate-limit metadata can be large or non-actionable,
        # and thinking content/signatures must never reach the operator.

    def _handle_stream_event(self, event: Mapping[str, Any]) -> None:
        inner = event.get("event")
        if not isinstance(inner, Mapping):
            return
        inner_type = inner.get("type")
        if inner_type == "content_block_start":
            block = inner.get("content_block")
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                name = block.get("name")
                if isinstance(name, str) and name:
                    self._write_line(f"[{self._label} tool] {name}")
        elif inner_type == "content_block_delta":
            delta = inner.get("delta")
            if isinstance(delta, Mapping) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    self._write_inline(text)
        elif inner_type in ("message_stop", "content_block_stop"):
            self._end_inline()

    def _handle_result(self, event: Mapping[str, Any]) -> None:
        self._end_inline()
        if event.get("is_error") is True:
            self._write_line(f"[{self._label}] finished with an error")
        else:
            self._write_line(f"[{self._label}] finished")

    def _write_inline(self, text: str) -> None:
        self._safe_write(text)
        self._inline_open = True

    def _end_inline(self) -> None:
        if self._inline_open:
            self._safe_write("\n")
            self._inline_open = False

    def _write_line(self, message: str) -> None:
        self._end_inline()
        self._safe_write(message + "\n")

    def _safe_write(self, text: str) -> None:
        try:
            self._stream.write(text)
            self._stream.flush()
        except Exception:
            pass


class ClaudeCodeProvider:
    def __init__(
        self,
        *,
        executable: str = "claude",
        process_runner: ProcessRunner | None = None,
        temporary_directory_parent: Path | None = None,
        repository_root: Path | None = None,
        externally_isolated_writable_repository: bool = False,
        live_observer: Callable[[bytes], None] | None = None,
        session: ProviderSessionBinding | None = None,
        session_ledger: ProviderSessionLedger | None = None,
    ) -> None:
        if type(executable) is not str or not executable:
            raise ValueError("executable must be a non-empty string")
        if type(externally_isolated_writable_repository) is not bool:
            raise ValueError("isolated writable repository profile must be boolean")
        if live_observer is not None and not callable(live_observer):
            raise ValueError("live_observer must be callable when provided")
        if session is not None and type(session) is not ProviderSessionBinding:
            raise ValueError("session must be an exact ProviderSessionBinding")
        if session_ledger is not None and type(session_ledger) is not ProviderSessionLedger:
            raise ValueError("session_ledger must be an exact ProviderSessionLedger")
        if session_ledger is not None and session is None:
            raise ValueError("session_ledger requires an explicit provider session")
        self.executable = executable
        self.process_runner = (
            StandardProcessRunner() if process_runner is None else process_runner
        )
        self.temporary_directory_parent = (
            None
            if temporary_directory_parent is None
            else Path(temporary_directory_parent)
        )
        self.repository_root = (
            _SOURCE_REPOSITORY_ROOT if repository_root is None else Path(repository_root)
        )
        self.externally_isolated_writable_repository = (
            externally_isolated_writable_repository
        )
        self.live_observer = live_observer
        # Opt-in only. ``None`` keeps the historical ephemeral invocation shape.
        self.session = session
        self.session_ledger = session_ledger

    @property
    def provider_identifier(self) -> str:
        return "claude-code"

    def invoke(
        self,
        request: AgentInvocationRequest,
        model: str,
    ) -> ProviderInvocationResponse:
        self._validate_request_policy(request)
        self._validate_model(model)
        argv = self._build_argv(request, model)
        prompt = self._prompt(request)

        if request.allowed_capabilities:
            repository_root = self._repository_root(request)
            result = self._run(
                argv,
                prompt,
                repository_root,
                request.budgets.timeout_seconds,
            )
            return self._response_from_result(result)

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

    def _validate_request_policy(self, request: AgentInvocationRequest) -> None:
        capabilities = frozenset(request.allowed_capabilities)
        if "approved_command_execution" in capabilities:
            raise ProviderRequestRejected(
                "Claude Code does not support approved command execution"
            )
        if capabilities == _WRITE_CAPABILITIES:
            if not self.externally_isolated_writable_repository:
                raise ProviderRequestRejected(
                    "Claude Code repository writing requires an explicit externally "
                    "isolated writable repository profile"
                )
            self._validated_writable_repository_root()
        elif capabilities not in _READ_CAPABILITY_COMBINATIONS:
            raise ProviderRequestRejected("Claude Code capability set is unsupported")
        elif self.externally_isolated_writable_repository:
            raise ProviderRequestRejected(
                "Claude Code isolated writable profile requires the exact read, "
                "search, and write capability combination"
            )
        if request.context_paths and not capabilities:
            raise ProviderRequestRejected(
                "Claude Code requires a repository capability for context_paths"
            )
        if request.budgets.token_limit is not None:
            raise ProviderRequestRejected(
                "Claude Code currently requires token_limit to be null"
            )
        self._validate_session_policy(request)

    def _validate_session_policy(self, request: AgentInvocationRequest) -> None:
        """Bind the session to this exact provider and this exact role.

        Compatibility is checked before any subprocess exists, so a Codex
        conversation or another role's conversation is refused as an invalid
        request rather than being handed to the Claude CLI.
        """

        session = self.session
        if session is None:
            return
        try:
            require_compatible_binding(
                session,
                provider_identifier=self.provider_identifier,
                role=request.role,
            )
        except ProviderSessionError as exc:
            raise ProviderRequestRejected(str(exc)) from exc
        if session.session_id is None:
            raise ProviderRequestRejected(
                "Claude Code names the conversation itself, so a persistent "
                "invocation requires an exact caller-chosen session UUID"
            )

    def _session_arguments(self) -> tuple[str, ...]:
        """Return the exact, mutually exclusive session argv fragment.

        No binding keeps the historical ``--no-session-persistence`` flag. A
        persistent start pins the caller-chosen UUID with ``--session-id``; a
        resume names that same exact UUID with ``--resume``. The two are never
        emitted together, ``--no-session-persistence`` is never emitted for a
        persistent invocation, and ``--resume`` is never emitted bare because a
        bare ``--resume`` opens the CLI's interactive picker instead of naming
        one exact conversation.
        """

        session = self.session
        if session is None:
            return ("--no-session-persistence",)
        if session.session_id is None:
            raise ProviderRequestRejected(
                "Claude Code persistent invocation requires an exact session UUID"
            )
        if session.is_resume:
            return ("--resume", session.session_id)
        return ("--session-id", session.session_id)

    def _confirm_session(
        self,
        envelope: Mapping[str, Any],
        raw_log: str,
    ) -> None:
        """Fail closed unless the transcript proves the exact bound conversation.

        A zero exit code is never on its own proof that the intended session was
        used. The pinned stream-json terminal result envelope exposes
        ``session_id``; a persistent invocation that omits or contradicts it is
        rejected instead of being reported as a successful resume.
        """

        session = self.session
        if session is None:
            return
        observed = envelope.get("session_id", _MISSING)
        if observed is _MISSING:
            raise ProviderOutputInvalid(
                "Claude Code persistent invocation omitted its terminal session_id",
                raw_log=raw_log,
            )
        try:
            confirmation = session.confirm(observed)
        except ProviderSessionError as exc:
            raise ProviderOutputInvalid(
                f"Claude Code persistent session identity failed closed: {exc}",
                raw_log=raw_log,
            ) from exc
        if self.session_ledger is not None:
            self.session_ledger.record_confirmed(confirmation)

    def _capture_session(self, raw_log: str) -> None:
        """Record the conversation the transcript proves, whatever the outcome.

        Identity and outcome are different facts. The terminal ``result`` event
        names the conversation the CLI actually used, and it names it whether the
        turn ended successfully, ran out of turns, emitted a malformed structured
        output, or exited non-zero. Confirming identity only on the success path
        discarded a conversation the provider had already proved, so a role that
        failed for an output-format reason lost the very context that made it
        cheap to repair.

        This is deliberately best effort and never widens what counts as proof.
        It records exactly what :meth:`_confirm_session` would accept and
        nothing else: an unparseable transcript, an absent ``session_id``, and
        an identity that contradicts the binding all leave the ledger untouched,
        so an unconfirmed conversation stays unconfirmed and fails closed
        upstream. It also never masks the real failure -- capturing raises
        nothing of its own.
        """

        if self.session is None or self.session_ledger is None:
            return
        try:
            envelope = _parse_stream(raw_log)
            self._confirm_session(envelope, raw_log)
        except (ProviderOutputInvalid, ProviderSessionError):
            return

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
        request: AgentInvocationRequest,
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
        tools = []
        if "repository_read" in request.allowed_capabilities:
            tools.append("Read")
        if "repository_search" in request.allowed_capabilities:
            tools.extend(("Glob", "Grep"))
        if "repository_write" in request.allowed_capabilities:
            tools.extend(("Edit", "Write"))
        disallowed = (
            _WRITE_DISALLOWED_TOOLS
            if "repository_write" in request.allowed_capabilities
            else _READ_ONLY_DISALLOWED_TOOLS
        )
        argv = (
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
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--json-schema",
            schema,
            *self._session_arguments(),
            "--setting-sources",
            "user,project",
            "--tools",
            ",".join(tools),
        )
        if tools:
            argv += ("--allowedTools", *tools)
        return argv + ("--disallowedTools", disallowed)

    def _prompt(self, request: AgentInvocationRequest) -> bytes:
        effective_prompt = request.prompt
        if request.allowed_capabilities:
            path_guidance = ""
            if request.context_paths:
                paths = "\n".join(f"- {path}" for path in request.context_paths)
                path_guidance = (
                    "\n\nRelevant repository paths:\n"
                    f"{paths}\n\n"
                    "These paths are the primary context for this task, but other "
                    "repository files may be inspected when needed to understand "
                    "dependencies."
                )
            repository_root = self._repository_root(request)
            effective_prompt = (
                f"{request.prompt}\n\n"
                "Repository context:\n"
                f"Repository root: {repository_root.as_posix()}\n"
                "Use repository tools only for the No Safe Circle project.\n"
                "Do not intentionally inspect /home, provider credentials, "
                "environment secrets, or unrelated filesystem locations."
                f"{path_guidance}"
            )
            if "repository_write" in request.allowed_capabilities:
                allowed = "\n".join(
                    f"- {path}" for path in request.write_boundaries.allowed_paths
                )
                denied = "\n".join(
                    f"- {path}" for path in request.write_boundaries.denied_paths
                ) or "- (none)"
                effective_prompt += (
                    "\n\nThis is a disposable isolated writable repository.\n"
                    "Allowed write paths:\n"
                    f"{allowed}\n"
                    "Denied write paths:\n"
                    f"{denied}\n"
                    "Denied paths override allowed paths. A path is writable only "
                    "when request.is_path_writable(path) would return true. Edit only "
                    "within these exact semantic boundaries and do not intentionally "
                    "modify any other path. Do not run commands, tests, or builds. "
                    "These path restrictions are semantic instructions, not native "
                    "path-level Claude enforcement. Higher-level deterministic Git "
                    "diff validation will decide whether this invocation is acceptable."
                )
        # A resumed conversation already holds remembered instructions, so the
        # revocation must be read before the new assignment.
        effective_prompt = prompt_with_resumed_authority(
            effective_prompt, self.session
        )
        try:
            return effective_prompt.encode("utf-8")
        except UnicodeError as exc:
            raise ProviderTransportError(
                "Claude Code prompt could not be encoded as UTF-8"
            ) from exc

    def _repository_root(self, request: AgentInvocationRequest) -> Path:
        if "repository_write" in request.allowed_capabilities:
            return self._validated_writable_repository_root()
        return _SOURCE_REPOSITORY_ROOT

    def _validated_writable_repository_root(self) -> Path:
        try:
            root = self.repository_root.resolve(strict=True)
            source_root = _SOURCE_REPOSITORY_ROOT.resolve(strict=True)
            if not root.is_dir():
                raise ProviderRequestRejected(
                    "writable repository root must be an existing directory"
                )
            if (
                root == source_root
                or root.is_relative_to(source_root)
                or source_root.is_relative_to(root)
            ):
                raise ProviderRequestRejected(
                    "writable repository root must be outside the source repository"
                )
        except ProviderRequestRejected:
            raise
        except (OSError, RuntimeError) as exc:
            raise ProviderRequestRejected(
                "writable repository root could not be resolved"
            ) from exc
        return root

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
        run_kwargs: dict[str, Any] = {}
        if self.live_observer is not None:
            run_kwargs["stdout_observer"] = self.live_observer
        try:
            result = self.process_runner.run(
                argv,
                stdin=prompt,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                **run_kwargs,
            )
        except ProcessTimeoutError as exc:
            if type(exc.result) is not ProcessResult or exc.result.argv != argv:
                raise ProviderTransportError(
                    "Claude Code timeout transport returned invalid local metadata"
                ) from exc
            raw_log = _decode_stdout(exc.result.stdout)
            # A timed-out invocation that still emitted its terminal event
            # proved which conversation it used; the conversation outlives the
            # turn that ran out of time.
            self._capture_session(raw_log)
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

    def _response_from_result(self, result: ProcessResult) -> ProviderInvocationResponse:
        raw_log = _decode_stdout(result.stdout)
        stderr = _safe_stderr(result.stderr)
        # Prove the conversation before judging the assignment. Every rejection
        # below describes work, not identity, and none of them is a reason to
        # forget which conversation the provider already named.
        self._capture_session(raw_log)
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

        envelope = _parse_stream(raw_log)
        _require_success(envelope, raw_log)
        self._confirm_session(envelope, raw_log)
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


def _parse_stream(raw_log: str) -> dict[str, Any]:
    """Strictly parse completed Claude Code NDJSON stream output, fail closed.

    Every nonblank line must be one JSON object with a string ``type``. The
    terminal ``type=result`` line must be the last nonblank line in the
    stream: it is rejected both if it repeats and if any further nonblank
    event follows it. Presentation-only live rendering never substitutes for
    this independent, authoritative parse.
    """
    result_envelope: dict[str, Any] | None = None
    for raw_line in raw_log.split("\n"):
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if not line.strip():
            continue
        if result_envelope is not None:
            raise ProviderOutputInvalid(
                "Claude Code stream contained an event after its terminal result event",
                raw_log=raw_log,
            )
        try:
            value = _strict_json_object(line)
        except (json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise ProviderOutputInvalid(
                "Claude Code stream contained a malformed NDJSON line",
                raw_log=raw_log,
            ) from exc
        event_type = value.get("type")
        if type(event_type) is not str or not event_type:
            raise ProviderOutputInvalid(
                "Claude Code stream event is missing a string type",
                raw_log=raw_log,
            )
        if event_type == "result":
            result_envelope = value
    if result_envelope is None:
        raise ProviderOutputInvalid(
            "Claude Code stream did not contain a terminal result event",
            raw_log=raw_log,
        )
    return result_envelope


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
        envelope = _parse_stream(raw_log)
    except ProviderOutputInvalid:
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
