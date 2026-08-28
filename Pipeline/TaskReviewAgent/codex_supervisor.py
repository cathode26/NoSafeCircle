"""Host-side goal loop decisions backed by the existing authenticated Codex CLI volume."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .contracts import TaskReviewContractError, validate_task_id


SUPERVISOR_DECISION_SCHEMA_VERSION = "1.0"
SUPERVISOR_TURN_SCHEMA_VERSION = "1.0"
DEFAULT_SUPERVISOR_MODEL = "gpt-5.6-sol"
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
    ) -> None:
        self.source = Path(source).resolve()
        self.model = (
            str(model).strip()
            if model
            else os.getenv("NSC_TASK_SUPERVISOR_MODEL")
            or os.getenv("NSC_OPENAI_CODEX_MODEL")
            or DEFAULT_SUPERVISOR_MODEL
        )
        self.compose_project = (
            str(compose_project).strip()
            if compose_project
            else os.getenv("NSC_TASK_AGENT_COMPOSE_PROJECT", "nosafecircle")
        )
        self.service = str(service).strip()
        self.reasoning_effort = (
            str(reasoning_effort).strip()
            if reasoning_effort
            else os.getenv("NSC_TASK_SUPERVISOR_REASONING_EFFORT", "high")
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("NSC_TASK_SUPERVISOR_TIMEOUT_SECONDS", "1500")
        )
        self.command_runner = command_runner or self._default_runner
        if not self.source.is_dir() or not (self.source / "compose.yaml").is_file():
            raise CodexSupervisorError("Codex supervisor source must contain compose.yaml")
        if not self.model or not self.compose_project or not self.service:
            raise CodexSupervisorError("Codex supervisor configuration is incomplete")
        if not self.timeout_seconds > 0:
            raise CodexSupervisorError("Codex supervisor timeout must be positive")
        self.last_usage: dict[str, Any] | None = None

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
        run_id = f"{task_id.casefold()}-supervisor-{turn:03d}"
        if not _RUN_ID.fullmatch(run_id):
            raise CodexSupervisorError("generated supervisor run_id is invalid")
        request = {
            "schema_version": SUPERVISOR_TURN_SCHEMA_VERSION,
            "run_id": run_id,
            "prompt": prompt,
            "output_schema": decision_schema(allowed_actions),
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "provider_turn_limit": 40,
            "timeout_seconds": self.timeout_seconds,
        }
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
        completed = self.command_runner(
            command,
            cwd=self.source,
            input_bytes=(
                json.dumps(
                    request,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
            timeout_seconds=self.timeout_seconds + 120.0,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            stdout = completed.stdout.decode("utf-8", errors="replace").strip()
            detail = "\n".join(item for item in (stderr, stdout) if item)
            raise CodexSupervisorError(
                f"Codex supervisor turn failed ({completed.returncode})"
                + (f":\n{detail}" if detail else "")
            )
        try:
            response = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodexSupervisorError("Codex supervisor response was not valid JSON") from exc
        if not isinstance(response, Mapping) or set(response) != {
            "schema_version",
            "structured_output",
            "usage",
        }:
            raise CodexSupervisorError("Codex supervisor response envelope is invalid")
        if response.get("schema_version") != SUPERVISOR_TURN_SCHEMA_VERSION:
            raise CodexSupervisorError("Codex supervisor response version is invalid")
        usage = response.get("usage")
        self.last_usage = dict(usage) if isinstance(usage, Mapping) else None
        return SupervisorDecision.from_dict(
            response.get("structured_output"),
            expected_task_id=task_id,
            allowed_actions=allowed_actions,
        )


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
