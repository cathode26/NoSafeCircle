"""Fail-closed OpenAI Codex CLI adapter for generic AgentRuntime invocations."""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
from typing import Any, Mapping

from ..contracts import AgentInvocationRequest, Usage
from ..json_values import thaw_json
from ..provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionError,
    ProviderSessionLedger,
    prompt_with_resumed_authority,
    require_compatible_binding,
)
from ..process_runner import ProcessResult, ProcessRunner, ProcessTimeoutError, StandardProcessRunner
from .base import (
    ProviderFailure, ProviderInvocationResponse, ProviderOutputInvalid,
    ProviderRequestRejected, ProviderTimeout, ProviderTransportError,
)

OPENAI_SECONDS_PER_TURN = 30
_READ_CAPABILITY_COMBINATIONS = frozenset({
    frozenset(), frozenset({"repository_read"}), frozenset({"repository_search"}),
    frozenset({"repository_read", "repository_search"}),
})
_WRITE_CAPABILITIES = frozenset(
    {"repository_read", "repository_search", "repository_write"}
)
_VALID_REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)
_SOURCE_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_MISSING = object()

# `codex exec` accepts `--sandbox <mode>`; `codex exec resume` does not expose
# that option at all. This adapter pins `--sandbox danger-full-access` on every
# start because the surrounding container, not the CLI, enforces isolation.
# Resuming without reproducing that exact policy would run the same role under a
# silently different permission policy, so a resume fails closed unless the
# operator supplies a verified equivalent for a channel resume does accept.
CODEX_RESUME_SANDBOX_BLOCKER = (
    "codex exec resume does not accept --sandbox, so the exact "
    "'--sandbox danger-full-access' permission policy pinned at session start "
    "cannot be reproduced on a resumed invocation. Resuming is refused rather "
    "than silently running under a different sandbox policy. Supply an "
    "operator-verified resume_sandbox_argument that reproduces that exact policy "
    "through an option `codex exec resume` does accept."
)


class OpenAICodexProvider:
    def __init__(
        self,
        *,
        reasoning_effort: str = "high",
        externally_enforced_read_only_repository: bool = False,
        externally_isolated_writable_repository: bool = False,
        executable: str = "codex",
        process_runner: ProcessRunner | None = None,
        temporary_directory_parent: Path | None = None,
        repository_root: Path | None = None,
        session: ProviderSessionBinding | None = None,
        session_ledger: ProviderSessionLedger | None = None,
        resume_sandbox_argument: tuple[str, ...] | None = None,
    ) -> None:
        if type(executable) is not str or not executable:
            raise ValueError("executable must be a non-empty string")
        if session is not None and type(session) is not ProviderSessionBinding:
            raise ValueError("session must be an exact ProviderSessionBinding")
        if session_ledger is not None and type(session_ledger) is not ProviderSessionLedger:
            raise ValueError("session_ledger must be an exact ProviderSessionLedger")
        if session_ledger is not None and session is None:
            raise ValueError("session_ledger requires an explicit provider session")
        if resume_sandbox_argument is not None and (
            type(resume_sandbox_argument) is not tuple
            or not resume_sandbox_argument
            or any(
                type(item) is not str or not item
                for item in resume_sandbox_argument
            )
        ):
            raise ValueError(
                "resume_sandbox_argument must be a non-empty tuple of non-empty strings"
            )
        if reasoning_effort not in _VALID_REASONING_EFFORTS:
            raise ValueError("unsupported Codex reasoning effort")
        if type(externally_enforced_read_only_repository) is not bool:
            raise ValueError("read-only repository profile must be boolean")
        if type(externally_isolated_writable_repository) is not bool:
            raise ValueError("isolated writable repository profile must be boolean")
        if externally_enforced_read_only_repository and externally_isolated_writable_repository:
            raise ValueError("read-only and isolated writable profiles are mutually exclusive")
        self.executable = executable
        self.reasoning_effort = reasoning_effort
        self.externally_enforced_read_only_repository = externally_enforced_read_only_repository
        self.externally_isolated_writable_repository = externally_isolated_writable_repository
        self.process_runner = StandardProcessRunner() if process_runner is None else process_runner
        self.temporary_directory_parent = temporary_directory_parent
        self.repository_root = (
            _SOURCE_REPOSITORY_ROOT if repository_root is None else Path(repository_root)
        ).resolve()
        # Opt-in only. ``None`` keeps the historical ephemeral invocation shape.
        self.session = session
        self.session_ledger = session_ledger
        self.resume_sandbox_argument = resume_sandbox_argument

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
        if "approved_command_execution" in capabilities:
            raise ProviderRequestRejected(
                "Codex does not support approved command execution"
            )
        if capabilities == _WRITE_CAPABILITIES:
            if not self.externally_isolated_writable_repository:
                raise ProviderRequestRejected(
                    "Codex repository writing requires an explicit externally isolated "
                    "writable repository profile"
                )
            self._validated_writable_repository_root()
        elif capabilities not in _READ_CAPABILITY_COMBINATIONS:
            raise ProviderRequestRejected("Codex capability set is unsupported")
        if request.context_paths and not capabilities:
            raise ProviderRequestRejected("Codex requires repository capability for context_paths")
        if capabilities and capabilities != _WRITE_CAPABILITIES and not self.externally_enforced_read_only_repository:
            raise ProviderRequestRejected(
                "Codex repository access requires an explicit externally read-only profile"
            )
        if capabilities != _WRITE_CAPABILITIES and self.externally_isolated_writable_repository:
            raise ProviderRequestRejected(
                "Codex isolated writable profile requires the exact read, search, "
                "and write capability combination"
            )
        if request.budgets.token_limit is not None:
            raise ProviderRequestRejected("Codex currently requires token_limit to be null")
        self._validate_session_policy(request)

    def _validate_session_policy(self, request: AgentInvocationRequest) -> None:
        """Bind the session to this exact provider and role, and fail closed on
        a resume whose safety-relevant controls cannot be reproduced."""

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
        if session.is_resume:
            if self.resume_sandbox_argument is None:
                raise ProviderRequestRejected(CODEX_RESUME_SANDBOX_BLOCKER)
        elif session.session_id is not None:
            raise ProviderRequestRejected(
                "Codex assigns its own thread UUID, so a persistent start must "
                "not bind a caller-chosen session_id; the assigned identity is "
                "captured from the transcript instead"
            )

    def _confirm_session(
        self,
        events: list[dict[str, Any]],
        raw_log: str,
    ) -> None:
        """Capture or verify the exact UUID from the pinned session-start event.

        The pinned JSONL transcript opens with one `thread.started` event
        carrying `thread_id`. A start adopts that exact UUID; a resume requires
        it to equal the UUID the invocation named. Missing, malformed,
        duplicated, and mismatched identities all fail closed, and a zero exit
        code alone is never accepted as proof.
        """

        session = self.session
        if session is None:
            return
        started = [event for event in events if event.get("type") == "thread.started"]
        if not started:
            raise ProviderOutputInvalid(
                "Codex persistent transcript has no thread.started session event",
                raw_log=raw_log,
            )
        if len(started) != 1:
            raise ProviderOutputInvalid(
                "Codex persistent transcript reported more than one thread.started "
                "session event",
                raw_log=raw_log,
            )
        try:
            confirmation = session.confirm(started[0].get("thread_id"))
        except ProviderSessionError as exc:
            raise ProviderOutputInvalid(
                f"Codex persistent session identity failed closed: {exc}",
                raw_log=raw_log,
            ) from exc
        if self.session_ledger is not None:
            self.session_ledger.record_confirmed(confirmation)

    def _capture_session(self, raw_log: str) -> None:
        """Record a transcript-proven thread before judging the turn outcome."""

        if self.session is None or self.session_ledger is None:
            return
        try:
            events = _parse_jsonl(raw_log)
            self._confirm_session(events, raw_log)
        except (ProviderOutputInvalid, ProviderSessionError):
            return

    @staticmethod
    def _validate_model(model: str) -> None:
        if type(model) is not str or not model or model != model.strip():
            raise ProviderTransportError("Codex requires a concrete configured model identifier")

    def _argv(self, model: str, schema_path: Path, final_path: Path) -> tuple[str, ...]:
        session = self.session
        if session is not None and session.is_resume:
            # `codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]`. The exact UUID
            # is always supplied positionally; `--last` is never emitted because
            # it names whichever recorded session happens to be newest. Options
            # absent from `codex exec resume` (--sandbox, --color) are handled by
            # _validate_session_policy rather than silently dropped here.
            return (
                self.executable, "exec", "resume", "--ignore-user-config",
                "--ignore-rules", "--strict-config", "--skip-git-repo-check",
                *(self.resume_sandbox_argument or ()), "--model", model,
                "-c", f"model_reasoning_effort={self.reasoning_effort}",
                "--output-schema", str(schema_path), "--json",
                "--output-last-message", str(final_path),
                str(session.session_id), "-",
            )
        # A persistent start is the ephemeral argv without `--ephemeral`, so the
        # session files the resume needs survive the invocation.
        ephemeral = () if session is not None else ("--ephemeral",)
        return (
            self.executable, "exec", *ephemeral, "--ignore-user-config",
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
                + (
                    "This is a disposable isolated writable repository. "
                    if "repository_write" in request.allowed_capabilities
                    else "The surrounding environment mounts this repository read-only. "
                )
                + "Inspect it with ordinary file and search mechanisms. "
                "Context paths are guidance, not an access allowlist."
                f"{hints}"
            )
            if "repository_write" in request.allowed_capabilities:
                allowed = "\n".join(f"- {path}" for path in request.write_boundaries.allowed_paths)
                denied = "\n".join(f"- {path}" for path in request.write_boundaries.denied_paths) or "- (none)"
                prompt += (
                    "\n\nAllowed write paths:\n" + allowed
                    + "\nDenied write paths:\n" + denied
                    + "\nDenied paths override allowed paths. A path is writable only "
                    "when request.is_path_writable(path) would return true. Limit work "
                    "to repository inspection and file edits within these exact semantic "
                    "boundaries; do not intentionally modify other paths. You may use the "
                    "minimum provider-local file-editing mechanism necessary to inspect and "
                    "edit the permitted files. Do not run project commands, tests, builds, "
                    "project scripts, package managers, Unity, or destructive/state-changing "
                    "Git operations. This does not grant AgentRuntime "
                    "approved_command_execution. These restrictions are semantic "
                    "instructions, not native path-level enforcement. Higher-level "
                    "deterministic Git diff validation decides acceptability."
                )
        # A resumed conversation already holds remembered instructions, so the
        # revocation must be read before the new assignment.
        prompt = prompt_with_resumed_authority(prompt, self.session)
        try:
            return prompt.encode("utf-8")
        except UnicodeError as exc:
            raise ProviderTransportError("Codex prompt could not be encoded as UTF-8") from exc

    def _validated_writable_repository_root(self) -> Path:
        try:
            root = self.repository_root.resolve(strict=True)
            source_root = _SOURCE_REPOSITORY_ROOT.resolve(strict=True)
            if not root.is_dir():
                raise ProviderRequestRejected(
                    "writable repository root must be an existing directory"
                )
            if (root == source_root or root.is_relative_to(source_root)
                    or source_root.is_relative_to(root)):
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
        parent = Path(tempfile.gettempdir()) if self.temporary_directory_parent is None else Path(self.temporary_directory_parent)
        try:
            resolved = parent.resolve(strict=True)
            repository_root = self.repository_root.resolve(strict=True)
            source_root = _SOURCE_REPOSITORY_ROOT.resolve(strict=True)
            if (
                not resolved.is_dir()
                or resolved == repository_root
                or resolved.is_relative_to(repository_root)
                or resolved == source_root
                or resolved.is_relative_to(source_root)
            ):
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
            raw_log = _decode_stdout(exc.result.stdout)
            self._capture_session(raw_log)
            raise ProviderTimeout(
                "Codex invocation exceeded its external timeout",
                raw_log=raw_log,
            ) from exc
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as exc:
            raise ProviderTransportError(f"Codex process transport failed: {type(exc).__name__}") from exc
        if type(result) is not ProcessResult or result.argv != argv:
            raise ProviderTransportError("Codex process transport returned invalid local metadata")
        return result

    def _response(self, result: ProcessResult, final_path: Path) -> ProviderInvocationResponse:
        raw_log = _decode_stdout(result.stdout)
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        self._capture_session(raw_log)
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
        self._confirm_session(events, raw_log)
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


def _provider_event_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant: {value}")
    def tolerate_web_search_duplicate_id(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        duplicate_keys: set[str] = set()
        id_values: list[Any] = []
        for key, value in pairs:
            if key in result:
                duplicate_keys.add(key)
            if key == "id":
                id_values.append(value)
            result[key] = value
        if not duplicate_keys:
            return result
        if (
            duplicate_keys == {"id"}
            and len(id_values) == 2
            and all(type(value) is str for value in id_values)
            and result.get("type") == "web_search"
        ):
            return result
        raise ValueError("duplicate JSON key in provider event")
    return json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=tolerate_web_search_duplicate_id,
    )


def _parse_jsonl(raw_log: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        for line in raw_log.splitlines():
            if not line.strip():
                continue
            event = _provider_event_json(line)
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
