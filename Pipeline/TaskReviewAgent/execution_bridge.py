"""Invoke real ExecutionCrew from a validated task checkout and verify its artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import TaskReviewContractError, semantic_sha256, validate_task_id
from .pipeline_scope import AcceptedExecutionScope, RepositoryScopeAuthority
from .execution_routing import OPENAI_REASONING_EFFORTS


EXECUTION_RECEIPT_SCHEMA_VERSION = "1.0"
_RUN_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_PROVIDER = {"claude", "codex"}


class ExecutionBridgeError(TaskReviewContractError):
    """Raised when ExecutionCrew cannot be invoked or its result is not authoritative."""


CommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


def _decode(data: bytes, *, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExecutionBridgeError(f"{label} was not valid UTF-8") from exc


def _default_runner(
    args: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    """Capture stdout while streaming ExecutionCrew progress from stderr."""

    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    try:
        process = subprocess.Popen(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ExecutionBridgeError(
            f"ExecutionCrew command could not start: {' '.join(args)}"
        ) from exc

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        for chunk in iter(lambda: process.stdout.read(65536), b""):
            stdout_chunks.append(chunk)

    def read_stderr() -> None:
        assert process.stderr is not None
        for chunk in iter(lambda: process.stderr.read(4096), b""):
            stderr_chunks.append(chunk)
            try:
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
            except (AttributeError, OSError):
                sys.stderr.write(chunk.decode("utf-8", errors="replace"))
                sys.stderr.flush()

    threads = [
        threading.Thread(target=read_stdout, daemon=True),
        threading.Thread(target=read_stderr, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise ExecutionBridgeError(
            f"ExecutionCrew exceeded {timeout_seconds:.0f} seconds"
        ) from exc
    finally:
        for thread in threads:
            thread.join(timeout=10.0)
    return subprocess.CompletedProcess(
        args=tuple(args),
        returncode=returncode,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
    )


def _last_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ExecutionBridgeError("ExecutionCrew stdout did not contain result JSON")
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    candidate: dict[str, Any] | None = None
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and not text[index + end :].strip():
            candidate = value
    if candidate is None:
        raise ExecutionBridgeError("ExecutionCrew stdout ended without one JSON object")
    return candidate


def _safe_json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


@dataclass(frozen=True)
class ExecutionCrewReceipt:
    run_id: str
    task_id: str
    lease_id: str
    plan_id: str
    provider: str
    execution_model: str | None
    execution_reasoning_effort: str | None
    source_head: str
    task_contract_sha256: str
    crew_status: str
    result_path: str
    result_sha256: str
    candidate_path: str | None
    candidate_sha256: str | None
    final_actual_changed_paths: tuple[str, ...]
    returncode: int
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_RECEIPT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "lease_id": self.lease_id,
            "plan_id": self.plan_id,
            "provider": self.provider,
            "execution_model": self.execution_model,
            "execution_reasoning_effort": self.execution_reasoning_effort,
            "source_head": self.source_head,
            "task_contract_sha256": self.task_contract_sha256,
            "crew_status": self.crew_status,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "candidate_path": self.candidate_path,
            "candidate_sha256": self.candidate_sha256,
            "final_actual_changed_paths": list(self.final_actual_changed_paths),
            "returncode": self.returncode,
            "rejection_reasons": list(self.rejection_reasons),
        }


class ExecutionCrewBridge:
    """Translate an accepted scope into the existing Docker ExecutionCrew CLI."""

    def __init__(
        self,
        *,
        checkout: Path | str,
        scope: RepositoryScopeAuthority,
        execution_model: str | None = None,
        execution_reasoning_effort: str | None = None,
        command_runner: CommandRunner | None = None,
        timeout_seconds: float | None = None,
        compose_project: str = "nosafecircle",
    ) -> None:
        self.checkout = Path(checkout).resolve()
        self.scope = scope
        self.execution_model = (
            str(execution_model).strip() if execution_model else None
        )
        self.execution_reasoning_effort = (
            str(execution_reasoning_effort).strip().casefold()
            if execution_reasoning_effort
            else None
        )
        if self.execution_reasoning_effort is not None and (
            self.execution_reasoning_effort not in OPENAI_REASONING_EFFORTS
        ):
            raise ExecutionBridgeError(
                "ExecutionCrew reasoning effort is unsupported"
            )
        self.command_runner = command_runner or _default_runner
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("NSC_TASK_AGENT_EXECUTION_TIMEOUT_SECONDS", "7200")
        )
        if not self.timeout_seconds > 0:
            raise ExecutionBridgeError("ExecutionCrew timeout must be positive")
        self.compose_project = str(compose_project).strip()
        if not self.compose_project:
            raise ExecutionBridgeError("Docker Compose project name must be non-empty")
        self.output_root = self.checkout / "Pipeline" / "ExecutionCrew" / "outputs"
        self.state_root = self.checkout.parent / ".task-review-agent"
        self.state_path = self.state_root / f"{self.scope.task_id}.execution.json"
        self._receipt: ExecutionCrewReceipt | None = None
        self._load_current()

    @property
    def receipt(self) -> ExecutionCrewReceipt | None:
        return self._receipt

    def _preflight_docker(self) -> None:
        if self.command_runner is not _default_runner:
            return
        if shutil.which("docker") is None:
            raise ExecutionBridgeError("Docker is not installed or not on PATH")
        check = subprocess.run(
            ("docker", "compose", "version"),
            cwd=str(self.checkout),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60.0,
        )
        if check.returncode != 0:
            raise ExecutionBridgeError(
                "Docker Compose is unavailable: "
                + _decode(check.stderr or check.stdout, label="docker compose version").strip()
            )
        compose = self.checkout / "compose.yaml"
        if not compose.is_file():
            raise ExecutionBridgeError("task checkout is missing compose.yaml")

    def _command(
        self,
        accepted: AcceptedExecutionScope,
        *,
        provider: str,
        retry_run_id: str | None,
        feedback_file: Path | None,
    ) -> list[str]:
        service = f"{provider}-exec"
        command = [
            "docker",
            "compose",
            "-p",
            self.compose_project,
            "run",
            "--rm",
            "-T",
            service,
            "python3",
            "Pipeline/ExecutionCrew/run_crew.py",
            "--source",
            "/workspace",
            "--host-output-root",
            str(self.output_root),
        ]
        if self.execution_model is not None:
            command.extend(("--model", self.execution_model))
        if self.execution_reasoning_effort is not None:
            command.extend(
                ("--openai-reasoning-effort", self.execution_reasoning_effort)
            )
        if retry_run_id is not None:
            command.extend(("--retry-run", retry_run_id))
            command.extend(("--expected-provider", provider))
            if feedback_file is None:
                raise ExecutionBridgeError("ExecutionCrew retry requires a feedback file")
            relative = feedback_file.resolve().relative_to(self.checkout)
            command.extend(("--review-feedback-file", "/workspace/" + relative.as_posix()))
            return command

        command.extend(("--task-id", accepted.task_id, "--provider", provider))
        for path in accepted.plan.existing_implementation_paths:
            command.extend(("--implementation-path", path))
        for path in accepted.plan.new_implementation_paths:
            command.extend(("--new-implementation-path", path))
        for path in accepted.plan.existing_test_paths:
            command.extend(("--test-path", path))
        for path in accepted.plan.new_test_paths:
            command.extend(("--new-test-path", path))
        return command

    def run(
        self,
        *,
        plan_id: str,
        provider: str,
        retry_run_id: str | None = None,
        feedback_file: Path | str | None = None,
    ) -> ExecutionCrewReceipt:
        provider = str(provider).strip().casefold()
        if provider not in _PROVIDER:
            raise ExecutionBridgeError("ExecutionCrew provider must be claude or codex")
        if self.execution_reasoning_effort is not None and provider != "codex":
            raise ExecutionBridgeError(
                "ExecutionCrew reasoning effort is supported only for codex"
            )
        accepted = self.scope.require(plan_id)
        if retry_run_id is not None and not _RUN_ID.fullmatch(str(retry_run_id)):
            raise ExecutionBridgeError("retry_run_id has an invalid identity")
        feedback = Path(feedback_file).resolve() if feedback_file is not None else None
        if feedback is not None:
            try:
                feedback.relative_to(self.checkout)
            except ValueError as exc:
                raise ExecutionBridgeError(
                    "review feedback must be a regular file inside the task checkout"
                ) from exc
            if not feedback.is_file():
                raise ExecutionBridgeError("review feedback file does not exist")

        self._preflight_docker()
        self.output_root.mkdir(parents=True, exist_ok=True)
        command = self._command(
            accepted,
            provider=provider,
            retry_run_id=retry_run_id,
            feedback_file=feedback,
        )
        completed = self.command_runner(command, self.checkout, self.timeout_seconds)
        stdout = _decode(completed.stdout or b"", label="ExecutionCrew stdout")
        parsed = _last_json_object(stdout)
        run_id = parsed.get("run_id")
        if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
            raise ExecutionBridgeError("ExecutionCrew result has an invalid run_id")
        result_path = self.output_root / run_id / "crew_result.json"
        if not result_path.is_file():
            raise ExecutionBridgeError(
                f"ExecutionCrew did not persist its authoritative result: {result_path}"
            )
        result_bytes = result_path.read_bytes()
        try:
            persisted = json.loads(result_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExecutionBridgeError("crew_result.json is not valid UTF-8 JSON") from exc
        if not isinstance(persisted, dict) or persisted != parsed:
            raise ExecutionBridgeError(
                "ExecutionCrew stdout result does not match persisted crew_result.json"
            )
        self._validate_result(persisted, accepted=accepted, provider=provider)

        candidate_path: Path | None = None
        candidate_sha: str | None = None
        if persisted.get("crew_status") == "review_ready":
            candidate_path = self.output_root / run_id / "candidate.patch"
            if not candidate_path.is_file():
                raise ExecutionBridgeError("review_ready run is missing candidate.patch")
            candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            if candidate_sha != persisted.get("candidate_patch_sha256"):
                raise ExecutionBridgeError("candidate.patch hash differs from crew_result.json")
        elif persisted.get("candidate_patch_path") is not None or persisted.get(
            "candidate_patch_sha256"
        ) is not None:
            raise ExecutionBridgeError(
                "non-review-ready ExecutionCrew result exposed candidate identity"
            )

        receipt = ExecutionCrewReceipt(
            run_id=run_id,
            task_id=accepted.task_id,
            lease_id=accepted.lease_id,
            plan_id=accepted.plan_id,
            provider=provider,
            execution_model=(
                str(persisted["execution_model"])
                if persisted.get("execution_model") is not None
                else None
            ),
            execution_reasoning_effort=(
                str(persisted["execution_reasoning_effort"])
                if persisted.get("execution_reasoning_effort") is not None
                else None
            ),
            source_head=accepted.source_head,
            task_contract_sha256=accepted.task_contract_sha256,
            crew_status=str(persisted.get("crew_status") or ""),
            result_path=str(result_path),
            result_sha256=hashlib.sha256(result_bytes).hexdigest(),
            candidate_path=str(candidate_path) if candidate_path is not None else None,
            candidate_sha256=candidate_sha,
            final_actual_changed_paths=tuple(
                sorted(
                    {
                        str(item)
                        for item in persisted.get("final_actual_changed_paths") or []
                        if type(item) is str and item
                    },
                    key=str.casefold,
                )
            ),
            returncode=int(completed.returncode),
            rejection_reasons=tuple(
                str(item)
                for item in persisted.get("rejection_reasons") or []
                if str(item).strip()
            ),
        )
        expected_return = 0 if receipt.crew_status == "review_ready" else 1
        if completed.returncode not in (expected_return,):
            raise ExecutionBridgeError(
                f"ExecutionCrew exit code {completed.returncode} disagrees with "
                f"crew_status={receipt.crew_status!r}"
            )
        self._persist(receipt)
        self._receipt = receipt
        return receipt

    def _validate_result(
        self,
        result: Mapping[str, Any],
        *,
        accepted: AcceptedExecutionScope,
        provider: str,
    ) -> None:
        fixed = {
            "task_id": accepted.task_id,
            "provider": provider,
            "source_head": accepted.source_head,
        }
        for field, expected in fixed.items():
            if result.get(field) != expected:
                raise ExecutionBridgeError(
                    f"ExecutionCrew changed {field}: {result.get(field)!r} != {expected!r}"
                )
        if (
            self.execution_model is not None
            and result.get("execution_model") != self.execution_model
        ):
            raise ExecutionBridgeError(
                "ExecutionCrew used a different execution model"
            )
        if (
            self.execution_reasoning_effort is not None
            and result.get("execution_reasoning_effort")
            != self.execution_reasoning_effort
        ):
            raise ExecutionBridgeError(
                "ExecutionCrew used a different execution reasoning effort"
            )
        identity = result.get("task_contract_identity")
        if not isinstance(identity, Mapping):
            raise ExecutionBridgeError("ExecutionCrew omitted task_contract_identity")
        if identity.get("sha256") != accepted.task_contract_sha256:
            raise ExecutionBridgeError("ExecutionCrew used a different task contract hash")
        if identity.get("path") != f"Tasks/{accepted.task_id}.yaml":
            raise ExecutionBridgeError("ExecutionCrew used a different task contract path")

        path_checks = {
            "requested_existing_implementation_paths": accepted.plan.existing_implementation_paths,
            "requested_new_implementation_paths": accepted.plan.new_implementation_paths,
            "requested_existing_test_paths": accepted.plan.existing_test_paths,
            "requested_new_test_paths": accepted.plan.new_test_paths,
        }
        for field, expected in path_checks.items():
            actual = tuple(sorted(result.get(field) or (), key=str.casefold))
            if actual != tuple(expected):
                raise ExecutionBridgeError(
                    f"ExecutionCrew result changed validated {field}: {actual} != {expected}"
                )
        status = result.get("crew_status")
        if status not in (
            "review_ready",
            "blocked",
            "rejected",
            "needs_human",
            "contract_review_required",
        ):
            raise ExecutionBridgeError(f"unsupported ExecutionCrew crew_status: {status!r}")

    def require(self, run_id: str) -> ExecutionCrewReceipt:
        if self._receipt is None or self._receipt.run_id != run_id:
            raise ExecutionBridgeError("candidate integration requires the current run_id")
        result_path = Path(self._receipt.result_path)
        if not result_path.is_file():
            raise ExecutionBridgeError("persisted ExecutionCrew result disappeared")
        if hashlib.sha256(result_path.read_bytes()).hexdigest() != self._receipt.result_sha256:
            raise ExecutionBridgeError("persisted ExecutionCrew result changed after verification")
        if self._receipt.candidate_path is not None:
            candidate = Path(self._receipt.candidate_path)
            if not candidate.is_file():
                raise ExecutionBridgeError("verified candidate.patch disappeared")
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != self._receipt.candidate_sha256:
                raise ExecutionBridgeError("verified candidate.patch changed after verification")
        return self._receipt

    def _persist(self, receipt: ExecutionCrewReceipt) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = receipt.to_dict()
        payload["receipt_sha256"] = semantic_sha256(payload)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.state_path)

    def _load_current(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            identity = dict(raw)
            receipt_hash = identity.pop("receipt_sha256")
            receipt = ExecutionCrewReceipt(
                run_id=identity["run_id"],
                task_id=validate_task_id(identity["task_id"]),
                lease_id=identity["lease_id"],
                plan_id=identity["plan_id"],
                provider=identity["provider"],
                execution_model=identity.get("execution_model"),
                execution_reasoning_effort=identity.get(
                    "execution_reasoning_effort"
                ),
                source_head=identity["source_head"],
                task_contract_sha256=identity["task_contract_sha256"],
                crew_status=identity["crew_status"],
                result_path=identity["result_path"],
                result_sha256=identity["result_sha256"],
                candidate_path=identity["candidate_path"],
                candidate_sha256=identity["candidate_sha256"],
                final_actual_changed_paths=tuple(identity["final_actual_changed_paths"]),
                returncode=identity["returncode"],
                rejection_reasons=tuple(identity["rejection_reasons"]),
            )
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return
        if receipt_hash != semantic_sha256(identity):
            return
        accepted = self.scope.accepted
        if accepted is None:
            return
        if (
            receipt.task_id != accepted.task_id
            or receipt.lease_id != accepted.lease_id
            or receipt.plan_id != accepted.plan_id
            or receipt.source_head != accepted.source_head
            or receipt.task_contract_sha256 != accepted.task_contract_sha256
            or (
                self.execution_model is not None
                and receipt.execution_model != self.execution_model
            )
            or (
                self.execution_reasoning_effort is not None
                and receipt.execution_reasoning_effort
                != self.execution_reasoning_effort
            )
        ):
            return
        try:
            self._receipt = receipt
            self.require(receipt.run_id)
        except ExecutionBridgeError:
            self._receipt = None
