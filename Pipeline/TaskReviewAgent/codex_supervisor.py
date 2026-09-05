"""Host-side goal loop decisions backed by the existing authenticated Codex CLI volume."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .contracts import TaskReviewContractError, validate_task_id
from .supervisor_session_pool import (
    SupervisorSessionOwner,
    SupervisorSessionPoolError,
    SupervisorTurn,
    classify_turn_failure,
    external_conversation_store_binding,
    gate_off_activation_state,
    resolve_compose_project,
    resolve_supervisor_codex_volume,
)


SUPERVISOR_DECISION_SCHEMA_VERSION = "1.0"
SUPERVISOR_TURN_SCHEMA_VERSION = "1.0"
# A pooled turn sends the 1.1 request (adds ``provider_session``) and requires
# the 1.1 response (adds ``provider_session_confirmation``). An ephemeral turn
# keeps the 1.0 request and accepts either response version.
POOLED_SUPERVISOR_TURN_SCHEMA_VERSION = "1.1"
_RESPONSE_FIELDS = {"schema_version", "structured_output", "usage"}
_POOLED_RESPONSE_FIELDS = _RESPONSE_FIELDS | {"provider_session_confirmation"}
_FAILURE_RESPONSE_FIELDS = {"schema_version", "failure", "provider_session_confirmation"}
DEFAULT_SUPERVISOR_MODEL = "gpt-5.6-sol"
DEFAULT_SUPERVISOR_TIMEOUT_SECONDS = 240.0
MAX_SUPERVISOR_TIMEOUT_SECONDS = 240.0
SUPERVISOR_PROVIDER_TURN_LIMIT = 8
SUPERVISOR_DOCKER_TIMEOUT_ALLOWANCE_SECONDS = 30.0
_RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class CodexSupervisorError(TaskReviewContractError):
    """Raised when the bounded Codex decision runtime cannot continue safely."""


class DecisionProvider(Protocol):
    def decide(
        self,
        *,
        task_id: str,
        turn: int,
        prompt: str,
        allowed_actions: Sequence[str],
    ) -> "SupervisorDecision":
        ...


def _nullable(kind: str, **values: Any) -> dict[str, Any]:
    return {"type": [kind, "null"], **values}


def _string_array_schema() -> dict[str, Any]:
    return _nullable("array", items={"type": "string"})


def decision_schema(allowed_actions: Sequence[str]) -> dict[str, Any]:
    actions = tuple(dict.fromkeys(str(item) for item in allowed_actions if str(item)))
    if not actions:
        raise CodexSupervisorError("supervisor decision schema requires allowed actions")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "task_id",
            "action",
            "arguments",
            "rationale",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [SUPERVISOR_DECISION_SCHEMA_VERSION],
            },
            "task_id": {"type": "string"},
            "action": {"type": "string", "enum": list(actions)},
            "rationale": {"type": "string"},
            "arguments": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "planned_approach": _nullable("string"),
                    "expected_validation": _nullable("string"),
                    "prefix": _nullable("string"),
                    "limit": _nullable("integer", minimum=1, maximum=1000),
                    "query": _nullable("string"),
                    "prefixes": _string_array_schema(),
                    "path": _nullable("string"),
                    "start_line": _nullable("integer", minimum=1, maximum=1000000),
                    "end_line": _nullable("integer", minimum=1, maximum=1000000),
                    "existing_implementation_paths": _string_array_schema(),
                    "new_implementation_paths": _string_array_schema(),
                    "existing_test_paths": _string_array_schema(),
                    "new_test_paths": _string_array_schema(),
                    "plan_id": _nullable("string"),
                    "retry_run_id": _nullable("string"),
                    "feedback_file": _nullable("string"),
                    "run_id": _nullable("string"),
                    "implementation_summary": _nullable("string"),
                    "human_steps": _string_array_schema(),
                    "expected_result": _nullable("string"),
                    "summary": _nullable("string"),
                    "details": _string_array_schema(),
                    "test_platform": _nullable("string"),
                    "test_filter": _nullable("string"),
                    "selected_surfaces": _nullable(
                        "array",
                        items={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["path", "role"],
                            "properties": {
                                "path": {"type": "string"},
                                "role": {"type": "string"},
                            },
                        },
                    ),
                    "gate_mappings": _nullable(
                        "array",
                        items={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["gate_id", "evidence", "notes"],
                            "properties": {
                                "gate_id": {"type": "string"},
                                "evidence": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "notes": {"type": "string"},
                            },
                        },
                    ),
                    "approval_notes": _nullable("string"),
                },
            },
        },
    }


@dataclass(frozen=True)
class SupervisorDecision:
    task_id: str
    action: str
    arguments: dict[str, Any]
    rationale: str

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        expected_task_id: str,
        allowed_actions: Sequence[str],
    ) -> "SupervisorDecision":
        if not isinstance(value, Mapping):
            raise CodexSupervisorError("Codex supervisor output must be one object")
        expected = {
            "schema_version",
            "task_id",
            "action",
            "arguments",
            "rationale",
        }
        if set(value) != expected:
            raise CodexSupervisorError(
                "Codex supervisor output fields mismatch; "
                f"missing={sorted(expected-set(value))}, "
                f"extras={sorted(set(value)-expected)}"
            )
        if value.get("schema_version") != SUPERVISOR_DECISION_SCHEMA_VERSION:
            raise CodexSupervisorError("Codex supervisor changed schema_version")
        task_id = validate_task_id(value.get("task_id"))
        if task_id != expected_task_id:
            raise CodexSupervisorError(
                f"Codex supervisor changed task identity: {task_id} != {expected_task_id}"
            )
        action = value.get("action")
        if type(action) is not str or action not in set(allowed_actions):
            raise CodexSupervisorError(f"Codex supervisor chose unsupported action: {action!r}")
        arguments = value.get("arguments")
        if not isinstance(arguments, Mapping):
            raise CodexSupervisorError("Codex supervisor arguments must be an object")
        rationale = value.get("rationale")
        if type(rationale) is not str or not rationale.strip():
            raise CodexSupervisorError("Codex supervisor rationale must be non-empty")
        return cls(task_id, action, dict(arguments), rationale.strip())

    def validate_arguments(
        self,
        *,
        required: Sequence[str] = (),
        optional: Sequence[str] = (),
    ) -> dict[str, Any]:
        allowed = set(required) | set(optional)
        supplied = {key for key, value in self.arguments.items() if value is not None}
        extras = supplied - allowed
        missing = {key for key in required if self.arguments.get(key) is None}
        if extras or missing:
            raise CodexSupervisorError(
                f"action {self.action} arguments mismatch; "
                f"missing={sorted(missing)}, extras={sorted(extras)}"
            )
        return {key: self.arguments.get(key) for key in allowed if self.arguments.get(key) is not None}


def resolve_supervisor_model(model: Any = None) -> str:
    """Return the exact supervisor model the provider will use."""

    if model:
        return str(model).strip()
    return (
        os.getenv("NSC_TASK_SUPERVISOR_MODEL")
        or os.getenv("NSC_OPENAI_CODEX_MODEL")
        or DEFAULT_SUPERVISOR_MODEL
    )


def resolve_supervisor_reasoning_effort(reasoning_effort: Any = None) -> str:
    """Return the exact supervisor reasoning effort the provider will use."""

    if reasoning_effort:
        return str(reasoning_effort).strip()
    return os.getenv("NSC_TASK_SUPERVISOR_REASONING_EFFORT", "high")


class CodexDockerDecisionProvider:
    """Invoke one read-only Codex CLI decision through Docker Compose."""

    def __init__(
        self,
        *,
        source: Path | str,
        model: str | None = None,
        compose_project: str | None = None,
        service: str = "codex-supervisor",
        reasoning_effort: str | None = None,
        timeout_seconds: float | None = None,
        command_runner=None,
        session_owner: SupervisorSessionOwner | None = None,
    ) -> None:
        self.source = Path(source).resolve()
        self.model = resolve_supervisor_model(model)
        try:
            self.compose_project = resolve_compose_project(compose_project)
            self.conversation_store_volume = resolve_supervisor_codex_volume()
            self.conversation_store = external_conversation_store_binding(
                "codex", self.conversation_store_volume
            )[1]
        except SupervisorSessionPoolError as exc:
            raise CodexSupervisorError(str(exc)) from exc
        self.service = str(service).strip()
        self.reasoning_effort = resolve_supervisor_reasoning_effort(reasoning_effort)
        raw_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv(
                "NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS",
                str(DEFAULT_SUPERVISOR_TIMEOUT_SECONDS),
            )
        )
        if isinstance(raw_timeout, bool):
            raise CodexSupervisorError("Codex supervisor timeout must be a finite number")
        try:
            self.timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise CodexSupervisorError(
                "Codex supervisor timeout must be a finite number"
            ) from exc
        self.command_runner = command_runner or self._default_runner
        if not self.source.is_dir() or not (self.source / "compose.yaml").is_file():
            raise CodexSupervisorError("Codex supervisor source must contain compose.yaml")
        if not self.model or not self.compose_project or not self.service:
            raise CodexSupervisorError("Codex supervisor configuration is incomplete")
        if not math.isfinite(self.timeout_seconds):
            raise CodexSupervisorError("Codex supervisor timeout must be a finite number")
        if self.timeout_seconds <= 0:
            raise CodexSupervisorError("Codex supervisor timeout must be positive")
        if self.timeout_seconds > MAX_SUPERVISOR_TIMEOUT_SECONDS:
            raise CodexSupervisorError(
                "Codex supervisor timeout may not exceed "
                f"{MAX_SUPERVISOR_TIMEOUT_SECONDS:g} seconds"
            )
        self.last_usage: dict[str, Any] | None = None
        # Session pooling is opt-in. ``None`` keeps every turn exactly as it
        # was: one ephemeral Codex process per judgment turn.
        if session_owner is not None and type(session_owner) is not SupervisorSessionOwner:
            raise CodexSupervisorError("session_owner must be an exact SupervisorSessionOwner")
        self.session_owner = session_owner
        if session_owner is not None and (
            session_owner.model != self.model
            or session_owner.reasoning_effort != self.reasoning_effort
            or session_owner.compose_project != self.compose_project
            or session_owner.conversation_store != self.conversation_store
        ):
            raise CodexSupervisorError(
                "supervisor session owner model/reasoning effort/compose project/"
                "conversation store differ from this provider"
            )
        self.last_session: dict[str, Any] | None = None
        self._turn_observation: dict[str, Any] = {}

    @property
    def warm_pooling_active(self) -> bool:
        return self.session_owner is not None and self.session_owner.warm_pooling_active

    def bind_turn_observation(self, observation: Mapping[str, Any] | None) -> None:
        """Record the deterministic facts the next turn's authority capsule names.

        The pipelines call this immediately before ``decide`` with the exact
        observation the prompt was rendered from, so the capsule states the same
        phase, Issue state, and source identity the provider is about to see.
        A fake provider without this method is simply not pooled.
        """

        facts: dict[str, Any] = {}
        if isinstance(observation, Mapping):
            coordination = observation.get("coordination")
            state = coordination.get("workflow_state") if isinstance(coordination, Mapping) else None
            environment = observation.get("environment")
            checkout = observation.get("checkout")
            if isinstance(state, Mapping):
                facts["phase"] = _optional_text(state.get("phase"))
                facts["issue_state"] = _optional_text(state.get("state"))
                version = state.get("state_version")
                facts["issue_state_version"] = (
                    version if type(version) is int and not isinstance(version, bool) else None
                )
            if isinstance(environment, Mapping):
                facts["source_head"] = _optional_text(environment.get("source_head"))
                facts["source_tree"] = _optional_text(environment.get("source_tree"))
            if isinstance(checkout, Mapping):
                facts["checkout_status"] = _optional_text(checkout.get("status"))
        self._turn_observation = facts

    @staticmethod
    def _default_runner(
        command: Sequence[str],
        *,
        cwd: Path,
        input_bytes: bytes,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        try:
            return subprocess.run(
                tuple(command),
                cwd=str(cwd),
                env=environment,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CodexSupervisorError("Codex supervisor Docker turn could not run") from exc

    def decide(
        self,
        *,
        task_id: str,
        turn: int,
        prompt: str,
        allowed_actions: Sequence[str],
    ) -> SupervisorDecision:
        task_id = validate_task_id(task_id)
        if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
            raise CodexSupervisorError("supervisor turn must be a positive integer")
        try:
            current_store = external_conversation_store_binding(
                "codex", resolve_supervisor_codex_volume()
            )[1]
        except SupervisorSessionPoolError as exc:
            raise CodexSupervisorError(str(exc)) from exc
        if current_store != self.conversation_store:
            raise CodexSupervisorError(
                "supervisor conversation store changed after provider construction"
            )
        run_id = f"{task_id.casefold()}-supervisor-{turn:03d}"
        if not _RUN_ID.fullmatch(run_id):
            raise CodexSupervisorError("generated supervisor run_id is invalid")
        pooled: SupervisorTurn | None = None
        facts = self._turn_observation
        self._turn_observation = {}
        # Every decision event says truthfully whether a pooled conversation
        # took part: an ephemeral provider reports the gate as off.
        self.last_session = gate_off_activation_state(task_id)
        if self.session_owner is not None:
            if self.session_owner.task_id != task_id:
                raise CodexSupervisorError(
                    "supervisor session owner is bound to a different task than this decision"
                )
            if self.session_owner.warm_pooling_active:
                try:
                    pooled = self.session_owner.begin_turn(
                        turn=turn, allowed_actions=allowed_actions, **facts
                    )
                except SupervisorSessionPoolError as exc:
                    raise CodexSupervisorError(
                        f"supervisor session could not be checked out: {exc}"
                    ) from exc
            else:
                # The gate is off: say so on every turn instead of silently
                # running ephemeral turns under a pooled-looking configuration.
                self.last_session = self.session_owner.activation_state()
        try:
            request = {
                "schema_version": (
                    POOLED_SUPERVISOR_TURN_SCHEMA_VERSION
                    if pooled is not None
                    else SUPERVISOR_TURN_SCHEMA_VERSION
                ),
                "run_id": run_id,
                "prompt": prompt if pooled is None else pooled.capsule + "\n\n" + prompt,
                "output_schema": decision_schema(allowed_actions),
                "model": self.model,
                "reasoning_effort": self.reasoning_effort,
                "provider_turn_limit": SUPERVISOR_PROVIDER_TURN_LIMIT,
                "timeout_seconds": self.timeout_seconds,
            }
            if pooled is not None:
                request["provider_session"] = pooled.provider_session
            command = (
                "docker",
                "compose",
                "-p",
                self.compose_project,
                "run",
                "--rm",
                "-T",
                self.service,
                "python3",
                "Pipeline/TaskReviewAgent/codex_supervisor_turn.py",
            )
            input_bytes = (
                json.dumps(
                    request,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        except BaseException:
            # Nothing reached the provider, so the checked-out lease is
            # returned uncharged rather than left active or retired.
            self._cancel(pooled)
            raise
        try:
            completed = self.command_runner(
                command,
                cwd=self.source,
                input_bytes=input_bytes,
                timeout_seconds=(
                    self.timeout_seconds + SUPERVISOR_DOCKER_TIMEOUT_ALLOWANCE_SECONDS
                ),
            )
        except BaseException as exc:
            # The Docker turn did not return a result: the provider may or may
            # not have received the turn, so the conversation is uncertain.
            self._settle(pooled, outcome="uncertain", confirmation=None, usage=None,
                         detail=f"Docker turn did not complete: {type(exc).__name__}")
            raise
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            stdout = completed.stdout.decode("utf-8", errors="replace").strip()
            failure = _failure_envelope(completed.stdout)
            self._settle(
                pooled,
                outcome=(
                    "uncertain" if failure is None
                    else classify_turn_failure(failure["failure"].get("classification"))
                ),
                confirmation=None if failure is None else failure["provider_session_confirmation"],
                usage=None,
                detail=(
                    f"turn exited {completed.returncode} without a failure envelope"
                    if failure is None
                    else str(failure["failure"].get("classification"))
                ),
            )
            detail = "\n".join(item for item in (stderr, stdout) if item)
            raise CodexSupervisorError(
                f"Codex supervisor turn failed ({completed.returncode})"
                + (f":\n{detail}" if detail else "")
            )
        try:
            response = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._settle(pooled, outcome="uncertain", confirmation=None, usage=None,
                         detail="response was not valid JSON")
            raise CodexSupervisorError("Codex supervisor response was not valid JSON") from exc
        accepted_fields = (
            (_POOLED_RESPONSE_FIELDS,)
            if pooled is not None
            else (_RESPONSE_FIELDS, _POOLED_RESPONSE_FIELDS)
        )
        if not isinstance(response, Mapping) or set(response) not in accepted_fields:
            self._settle(pooled, outcome="output_failure", confirmation=None, usage=None,
                         detail="response envelope fields are invalid")
            raise CodexSupervisorError("Codex supervisor response envelope is invalid")
        version = response.get("schema_version")
        if version not in {SUPERVISOR_TURN_SCHEMA_VERSION, POOLED_SUPERVISOR_TURN_SCHEMA_VERSION} or (
            pooled is not None and version != POOLED_SUPERVISOR_TURN_SCHEMA_VERSION
        ):
            self._settle(pooled, outcome="output_failure", confirmation=None, usage=None,
                         detail="response envelope version is invalid")
            raise CodexSupervisorError("Codex supervisor response version is invalid")
        usage = response.get("usage")
        usage_value = dict(usage) if isinstance(usage, Mapping) else None
        try:
            decision = SupervisorDecision.from_dict(
                response.get("structured_output"),
                expected_task_id=task_id,
                allowed_actions=allowed_actions,
            )
        except CodexSupervisorError:
            # The provider answered, but not with a usable decision. The
            # conversation itself is proven by its confirmation and counts one
            # output failure; it is never resumed on an unproven identity.
            self._settle(pooled, outcome="output_failure",
                         confirmation=response.get("provider_session_confirmation"),
                         usage=usage_value, detail="structured decision was rejected")
            raise
        if pooled is not None:
            record = self._settle(
                pooled, outcome="completed",
                confirmation=response.get("provider_session_confirmation"),
                usage=usage_value, detail="decision accepted",
            )
            # The identity this turn ran under must have been proven exactly:
            # the record must carry a confirmed session and must not have been
            # withdrawn for an identity failure. A cold start that proved
            # nothing is quarantined; a resume whose confirmation named another
            # thread, another mode, or nothing at all is retired for
            # identity_failure. Neither may act on this decision, however the
            # container process exited. A budget or context retirement after a
            # proven turn is not an identity failure and is accepted.
            if (
                record is None
                or record.session_id is None
                or record.state == "quarantined"
                or record.retirement_reason == "identity_failure"
            ):
                detail = "unknown"
                if record is not None and record.quarantine_reason:
                    detail = record.quarantine_reason
                elif record is not None and record.retirement_reason:
                    detail = f"retired for {record.retirement_reason}"
                raise CodexSupervisorError(
                    "Codex supervisor turn did not prove its pooled session identity: " + detail
                )
        self.last_usage = usage_value
        return decision

    def _cancel(self, pooled: SupervisorTurn | None) -> None:
        """Return a checked-out lease that never reached the provider."""

        if pooled is None or self.session_owner is None:
            return
        try:
            self.session_owner.cancel_turn(pooled)
        except SupervisorSessionPoolError as exc:
            raise CodexSupervisorError(
                f"supervisor session could not be returned: {exc}"
            ) from exc
        self.last_session = None

    def _settle(
        self,
        pooled: SupervisorTurn | None,
        *,
        outcome: str,
        confirmation: Any,
        usage: Any,
        detail: str,
    ) -> Any:
        """Settle a pooled turn exactly once; an unpooled turn settles nothing."""

        if pooled is None or self.session_owner is None:
            return None
        try:
            record = self.session_owner.finish_turn(
                pooled, outcome=outcome, confirmation=confirmation, usage=usage, detail=detail,
            )
        except SupervisorSessionPoolError as exc:
            raise CodexSupervisorError(
                f"supervisor session could not be settled: {exc}"
            ) from exc
        self.last_session = {
            "warm_pooling_active": True,
            "mode": pooled.mode,
            "requested_session_id": pooled.session_id,
            "lease_id": pooled.lease.lease_id,
            "record_id": record.record_id,
            "confirmed_session_id": record.session_id,
            "outcome": outcome,
            "state": record.state,
            "completed_assignment_count": record.completed_assignment_count,
            "retirement_reason": record.retirement_reason,
            "quarantine_reason": record.quarantine_reason,
        }
        return record


def _optional_text(value: Any) -> str | None:
    return value if type(value) is str and value.strip() else None


def _failure_envelope(stdout: bytes) -> dict[str, Any] | None:
    """Parse the container's machine-readable failure envelope, if it sent one."""

    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping) or set(value) != _FAILURE_RESPONSE_FIELDS:
        return None
    if value.get("schema_version") != POOLED_SUPERVISOR_TURN_SCHEMA_VERSION:
        return None
    failure = value.get("failure")
    if not isinstance(failure, Mapping):
        return None
    return {
        "failure": dict(failure),
        "provider_session_confirmation": value.get("provider_session_confirmation"),
    }


def compact_history(history: Sequence[Mapping[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in history[-limit:]:
        snapshot = json.loads(json.dumps(dict(item), ensure_ascii=False, allow_nan=False))
        rendered = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
        if len(rendered) > 80000:
            snapshot = {
                "action": snapshot.get("action"),
                "rationale": snapshot.get("rationale"),
                "result_truncated": rendered[:80000],
            }
        values.append(snapshot)
    return values


def render_supervisor_prompt(
    *,
    task_id: str,
    goal_and_rules: str,
    observation: Mapping[str, Any],
    history: Sequence[Mapping[str, Any]],
    actions: Mapping[str, str],
) -> str:
    task_id = validate_task_id(task_id)
    action_lines = "\n".join(
        f"- {name}: {description}" for name, description in actions.items()
    )
    return (
        f"You are the No Safe Circle goal-oriented OpenAI Codex supervisor for {task_id}.\n\n"
        f"{goal_and_rules.strip()}\n\n"
        "CURRENT DETERMINISTIC OBSERVATION\n"
        + json.dumps(
            observation,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n\nRECENT ACTION RESULTS\n"
        + json.dumps(
            compact_history(history),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n\nALLOWED NEXT ACTIONS\n"
        + action_lines
        + "\n\nReturn exactly one structured decision. Choose one allowed action and supply only "
        "that action's arguments. Never invent task IDs, hashes, paths, plan IDs, run IDs, "
        "Issue state, commits, test results, or authority. The host validates and executes "
        "the action; you do not have direct shell, repository-write, GitHub, Unity, or tool "
        "authority in this decision turn."
    )


def describe_codex_runtime() -> dict[str, Any]:
    return {
        "runtime": "authenticated_codex_cli_docker_goal_loop",
        "api_key_required": False,
        "default_model": DEFAULT_SUPERVISOR_MODEL,
        "credential_source": "CODEX_HOME Docker volume",
    }
