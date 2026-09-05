"""Deterministic downstream pipeline from human PASS to merged conformant task."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from Pipeline.Testing.validation_manifest import (
    ValidationManifestError,
    load_validation_manifest,
)

from .contracts import TaskReviewContractError, semantic_sha256
from .delivery_review import (
    DeliveryReviewError,
    create_delivery_review_proposal,
    file_sha256,
    materialize_automated_review,
    materialize_approved_review,
)
from .downstream_issue import DownstreamIssueCoordinator, DownstreamIssueError
from .issue_workflow import (
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_human_validation_result,
)
from .issue_workflow_store import GhIssueBackend, resolve_issue_backend_repository
from .real_workflow import RealTaskReviewWorkflow
from .token_usage import build_task_token_usage, write_task_token_usage


DOWNSTREAM_SCHEMA_VERSION = "1.0"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_VALID_PLATFORMS = {"EditMode", "PlayMode"}


class DownstreamPipelineError(TaskReviewContractError):
    """Raised when delivery evidence or closeout cannot advance safely."""


CommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]


def _decode(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DownstreamPipelineError(f"{label} was not valid UTF-8") from exc


def _default_runner(
    args: Sequence[str],
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DownstreamPipelineError(
            f"downstream command could not run: {' '.join(args)}"
        ) from exc


def _run(
    runner: CommandRunner,
    args: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float = 1800.0,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    result = runner(tuple(args), cwd, timeout_seconds)
    if check and result.returncode != 0:
        detail = "\n".join(
            item
            for item in (
                _decode(result.stdout or b"", "stdout").strip(),
                _decode(result.stderr or b"", "stderr").strip(),
            )
            if item
        )
        raise DownstreamPipelineError(
            f"downstream command failed ({result.returncode}): {' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _git(
    runner: CommandRunner,
    root: Path,
    *args: str,
    check: bool = True,
    timeout_seconds: float = 600.0,
) -> subprocess.CompletedProcess[bytes]:
    return _run(
        runner,
        ("git", "-C", str(root), *args),
        cwd=root,
        timeout_seconds=timeout_seconds,
        check=check,
    )


def _git_text(
    runner: CommandRunner,
    root: Path,
    *args: str,
    check: bool = True,
) -> str:
    return _decode(
        _git(runner, root, *args, check=check).stdout,
        "git stdout",
    ).strip()


def _json_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownstreamPipelineError(f"{label} was not valid JSON") from exc
    if not isinstance(value, dict):
        raise DownstreamPipelineError(f"{label} must be a JSON object")
    return value


def _meaningful(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DownstreamPipelineError(f"{field} must be non-empty")
    return value.strip()


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _safe_slug(value: str) -> str:
    return "".join(
        character.casefold() if character.isalnum() else "-"
        for character in value
    ).strip("-") or "item"


def _file_fact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise DownstreamPipelineError(f"required artifact is missing: {path}")
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _external_root(task_id: str, commit: str, explicit: Path | None) -> Path:
    if explicit is not None:
        base = explicit.expanduser().resolve()
    elif os.getenv("NSC_TASK_AGENT_OUTPUT_ROOT"):
        base = Path(os.environ["NSC_TASK_AGENT_OUTPUT_ROOT"]).expanduser().resolve()
    else:
        base = Path.home() / "Downloads" / "NoSafeCircleOutput"
    root = base / task_id / f"delivery-{commit[:12]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _workflow_state(observation: Mapping[str, Any]) -> dict[str, Any] | None:
    coordination = observation.get("coordination")
    if not isinstance(coordination, Mapping):
        return None
    state = coordination.get("workflow_state")
    return dict(state) if isinstance(state, Mapping) else None


def _required_platforms(task: Mapping[str, Any]) -> tuple[str, ...]:
    text = "\n".join(
        str(item.get("requirement") or "")
        for item in task.get("completion_gates") or []
        if isinstance(item, Mapping)
    ).casefold()
    values: list[str] = []
    if "edit mode" in text or "editmode" in text:
        values.append("EditMode")
    if "play mode" in text or "playmode" in text:
        values.append("PlayMode")
    return tuple(values or ("EditMode", "PlayMode"))


def _manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = load_validation_manifest(path)
    except (OSError, ValidationManifestError) as exc:
        raise DownstreamPipelineError(f"validation manifest is invalid: {exc}") from exc
    return {
        "path": str(manifest.path),
        "sha256": file_sha256(manifest.path),
        "commit": manifest.validated_state.commit,
        "tree": manifest.validated_state.tree,
        "test_platform": manifest.unity.test_platform,
        "test_filter": manifest.unity.test_filter,
    }


class DownstreamTaskController:
    """Advance an Issue after human Unity PASS through verified closeout."""

    def __init__(
        self,
        *,
        workflow: RealTaskReviewWorkflow,
        unity_executable: str | None = None,
        output_root: Path | str | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self.workflow = workflow
        self.task_id = workflow.task_id
        self.command_runner = command_runner or _default_runner
        self.unity_executable = str(unity_executable).strip() if unity_executable else None
        self.explicit_output_root = Path(output_root) if output_root is not None else None
        self.issue = (
            DownstreamIssueCoordinator(workflow.issue_workflow)
            if workflow.issue_workflow is not None
            else None
        )
        self.checkout = workflow.checkout_manager.checkout_path
        self.state_root = self.checkout.parent / ".task-review-agent"
        self.state_path = self.state_root / f"{self.task_id}.downstream.json"
        self.state: dict[str, Any] = self._load_state()
        self.last_observation: dict[str, Any] | None = None

    def observe(self) -> dict[str, Any]:
        observation = self.workflow.observe_goal_state()
        observation = self._recover_persisted_evidence_checkout(observation)
        state = _workflow_state(observation)
        observation["downstream"] = {
            "schema_version": DOWNSTREAM_SCHEMA_VERSION,
            "required_test_platforms": list(_required_platforms(observation["task"])),
            "receipt": _copy(self.state) if self.state else None,
            "next_action": self._next_action(observation, state),
            "authority": "delivery_evidence_and_merge_closeout",
        }
        self.last_observation = _copy(observation)
        return _copy(observation)

    def _recover_persisted_evidence_checkout(
        self,
        observation: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Recognize an exact evidence commit left by an interrupted PR-open step."""

        value = _copy(observation)
        workflow_state = _workflow_state(value)
        checkout = value.get("checkout")
        evidence_commit = self.state.get("evidence_commit")
        implementation_commit = self.state.get("implementation_commit")
        evidence_tree = self.state.get("evidence_tree")
        created_paths = self.state.get("created_paths")
        if (
            workflow_state is None
            or workflow_state.get("phase") != WorkflowPhase.MERGE_CLOSEOUT.value
            or not isinstance(checkout, Mapping)
            or checkout.get("status") == "ready"
            or not isinstance(evidence_commit, str)
            or not _SHA40.fullmatch(evidence_commit)
            or not isinstance(implementation_commit, str)
            or not _SHA40.fullmatch(implementation_commit)
            or workflow_state.get("head_commit") != implementation_commit
            or checkout.get("head_commit") != evidence_commit
            or checkout.get("branch") != workflow_state.get("branch")
            or checkout.get("clean") is not True
            or not isinstance(evidence_tree, str)
            or not _SHA40.fullmatch(evidence_tree)
            or not isinstance(created_paths, list)
            or not created_paths
            or any(not isinstance(path, str) or not path for path in created_paths)
        ):
            return value
        if not self.checkout.is_dir():
            return value
        if (
            _git(
                self.command_runner,
                self.checkout,
                "merge-base",
                "--is-ancestor",
                implementation_commit,
                evidence_commit,
                check=False,
            ).returncode
            != 0
        ):
            return value
        actual_tree = _git_text(
            self.command_runner,
            self.checkout,
            "rev-parse",
            f"{evidence_commit}^{{tree}}",
            check=False,
        )
        if actual_tree != evidence_tree:
            return value
        actual_paths = _git_text(
            self.command_runner,
            self.checkout,
            "diff",
            "--name-only",
            implementation_commit,
            evidence_commit,
            "--",
            check=False,
        ).splitlines()
        if sorted(actual_paths, key=str.casefold) != sorted(created_paths, key=str.casefold):
            return value
        remote = _git_text(
            self.command_runner,
            self.checkout,
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{workflow_state.get('branch')}",
            check=False,
        ).split()
        if not remote or remote[0] != evidence_commit:
            return value

        original_reasons = list(checkout.get("reasons") or [])
        recovered = dict(checkout)
        recovered.update(
            {
                "status": "ready",
                "managed": True,
                "expected_head": evidence_commit,
                "reasons": [],
                "persisted_evidence_recovery": {
                    "status": "recovered",
                    "implementation_commit": implementation_commit,
                    "evidence_commit": evidence_commit,
                    "evidence_tree": evidence_tree,
                    "created_paths": list(created_paths),
                    "authority": "persisted_downstream_receipt_and_exact_git_identity",
                },
            }
        )
        value["checkout"] = recovered
        environment = value.get("environment")
        if isinstance(environment, Mapping):
            normalized_environment = dict(environment)
            errors = [
                item
                for item in list(normalized_environment.get("errors") or [])
                if item not in original_reasons
            ]
            normalized_environment["errors"] = errors
            if (
                not errors
                and normalized_environment.get("controller_clean") is True
                and normalized_environment.get("taskgraph_valid") is True
            ):
                normalized_environment["ready"] = True
            value["environment"] = normalized_environment
        return value

    def _next_action(
        self,
        observation: Mapping[str, Any],
        state: Mapping[str, Any] | None,
    ) -> str:
        if state is None:
            return "use_implementation_pipeline"
        current = state.get("state")
        phase = state.get("phase")
        if current == WorkflowState.BLOCKED.value and phase == WorkflowPhase.DELIVERY_EVIDENCE.value:
            if (
                state.get("human_result") == "pass"
                and self.state.get("proposal_path")
                and self.state.get("proposal_sha256")
            ):
                return "publish_delivery_review"
            return "vincent_reviews_delivery_proposal"
        if current == WorkflowState.COMPLETE.value:
            return "complete"
        if current == WorkflowState.AGENT_READY.value and phase in (
            WorkflowPhase.DELIVERY_EVIDENCE.value,
            WorkflowPhase.MERGE_CLOSEOUT.value,
        ):
            return "acquire_agent_lease"
        if current != WorkflowState.AGENT_WORKING.value:
            return "inspect_workflow_state"
        if state.get("worker_id") != self.workflow.worker_id:
            return "another_agent_owns_lease"
        checkout = observation.get("checkout")
        if not isinstance(checkout, Mapping) or checkout.get("status") != "ready":
            return "prepare_task_checkout"
        if phase == WorkflowPhase.DELIVERY_EVIDENCE.value:
            platforms = {
                item.get("test_platform")
                for item in self.state.get("validation_manifests") or []
                if isinstance(item, Mapping)
            }
            if not set(_required_platforms(observation["task"])).issubset(platforms):
                return "run_authoritative_unity_tests"
            if not self.state.get("draft_path"):
                return "create_delivery_review_draft"
            if not self.state.get("proposal_path"):
                return "create_delivery_review_proposal"
            return "publish_delivery_review"
        if phase == WorkflowPhase.MERGE_CLOSEOUT.value:
            if not self._latest_delivery_approval():
                return "verify_delivery_approval"
            if not self.state.get("evidence_commit"):
                return "finalize_delivery_evidence"
            if not self.state.get("pull_request_number"):
                return "open_pull_request"
            if not self.state.get("merged_commit"):
                return "inspect_or_merge_pull_request"
            return "verify_post_merge_and_complete"
        return "use_implementation_pipeline"

    def acquire_agent_lease(
        self,
        *,
        planned_approach: str,
        expected_validation: str,
    ) -> dict[str, Any]:
        result = self.workflow.acquire_agent_lease(
            planned_approach=planned_approach,
            expected_validation=expected_validation,
        )
        return result

    def prepare_task_checkout(self) -> dict[str, Any]:
        observation = self.last_observation or {}
        checkout = observation.get("checkout")
        checkout = checkout if isinstance(checkout, Mapping) else {}
        recovery = checkout.get("persisted_evidence_recovery")
        if isinstance(recovery, Mapping) and recovery.get("status") == "recovered":
            state = _workflow_state(observation)
            branch = state.get("branch") if isinstance(state, Mapping) else None
            evidence_commit = recovery.get("evidence_commit")
            if (
                not isinstance(branch, str)
                or not branch.strip()
                or not isinstance(evidence_commit, str)
                or not _SHA40.fullmatch(evidence_commit)
                or checkout.get("head_commit") != evidence_commit
                or checkout.get("status") != "ready"
                or checkout.get("clean") is not True
            ):
                raise DownstreamPipelineError(
                    "persisted evidence ref refresh requires an exact recovered checkout"
                )
            _git(
                self.command_runner,
                self.checkout,
                "fetch",
                "origin",
                "+refs/heads/main:refs/remotes/origin/main",
                f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            )
            refreshed = self.observe()
            refreshed_checkout = refreshed.get("checkout")
            refreshed_checkout = (
                refreshed_checkout if isinstance(refreshed_checkout, Mapping) else {}
            )
            refreshed_recovery = refreshed_checkout.get(
                "persisted_evidence_recovery"
            )
            if (
                refreshed_checkout.get("status") != "ready"
                or refreshed_checkout.get("head_commit") != evidence_commit
                or refreshed_checkout.get("clean") is not True
                or not isinstance(refreshed_recovery, Mapping)
                or refreshed_recovery.get("status") != "recovered"
                or refreshed_recovery.get("evidence_commit") != evidence_commit
            ):
                raise DownstreamPipelineError(
                    "persisted evidence checkout changed while refreshing remote refs"
                )
            result = {
                **dict(refreshed_checkout),
                "origin_main_refreshed": True,
                "recovery_authority": (
                    "persisted_downstream_receipt_and_exact_git_identity"
                ),
            }
            self.workflow.last_checkout_result = _copy(result)
            return _copy(result)
        return self.workflow.prepare_task_checkout()

    def read_issue_log(self) -> dict[str, Any]:
        service = self.workflow.issue_workflow
        if service is None:
            raise DownstreamPipelineError("Issue workflow is unavailable")
        snapshot = service.find(self.task_id)
        if snapshot is None:
            raise DownstreamPipelineError("managed Issue is missing")
        comments = service.backend.get_comments(snapshot.issue_number)
        return {
            "issue_number": snapshot.issue_number,
            "issue_url": snapshot.issue_url,
            "workflow_state": snapshot.state.to_dict() if snapshot.state else None,
            "events": [event.to_dict() for event in snapshot.events],
            "comments": [
                {"id": item.get("id"), "body": item.get("body")}
                for item in comments
                if isinstance(item, Mapping) and isinstance(item.get("body"), str)
            ],
        }

    def read_repository_file(
        self,
        *,
        path: str,
        start_line: int = 1,
        end_line: int = 500,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") or ".." in Path(path).parts:
            raise DownstreamPipelineError("read path must be repository-relative")
        allowed = (
            "Assets/",
            "Tasks/",
            "Docs/GDD/",
            "Docs/Engineering/",
            "Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md",
        )
        if not any(path.casefold().startswith(prefix.casefold()) for prefix in allowed):
            raise DownstreamPipelineError("read path is outside downstream read roots")
        if not isinstance(start_line, int) or not isinstance(end_line, int) or start_line < 1 or end_line < start_line or end_line - start_line > 999:
            raise DownstreamPipelineError("read line range is invalid")
        result = _git(
            self.command_runner,
            self.checkout,
            "show",
            f"HEAD:{path}",
            check=False,
        )
        if result.returncode != 0:
            raise DownstreamPipelineError(f"committed file is missing: {path}")
        lines = _decode(result.stdout, path).splitlines()
        selected = lines[start_line - 1 : end_line]
        return {
            "path": path,
            "start_line": start_line,
            "end_line": start_line + len(selected) - 1,
            "content": "\n".join(selected),
        }

    def run_authoritative_unity_test(
        self,
        *,
        test_platform: str,
        test_filter: str,
    ) -> dict[str, Any]:
        observation, workflow_state = self._require_lease(WorkflowPhase.DELIVERY_EVIDENCE)
        if test_platform not in _VALID_PLATFORMS:
            raise DownstreamPipelineError("test_platform must be EditMode or PlayMode")
        test_filter = _meaningful(test_filter, "test_filter")
        self._assert_human_tested_head(workflow_state)
        existing = [
            item
            for item in self.state.get("validation_manifests") or []
            if isinstance(item, Mapping)
            and item.get("test_platform") == test_platform
            and item.get("test_filter") == test_filter
        ]
        if existing:
            manifest = _manifest(Path(existing[0]["path"]))
            if manifest["commit"] != workflow_state["head_commit"]:
                raise DownstreamPipelineError("stored validation manifest is stale")
            return manifest

        script = self.checkout / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1"
        if not script.is_file():
            raise DownstreamPipelineError("clean Unity test runner is missing")
        shell = "powershell.exe" if os.name == "nt" else "pwsh"
        command = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-TestPlatform",
            test_platform,
            "-TestFilter",
            test_filter,
            "-ProjectPath",
            str(self.checkout),
        ]
        if self.unity_executable:
            command.extend(("-UnityExecutable", self.unity_executable))
        result = _run(
            self.command_runner,
            command,
            cwd=self.checkout,
            timeout_seconds=float(os.getenv("NSC_TASK_AGENT_UNITY_TIMEOUT_SECONDS", "3600")),
            check=False,
        )
        stdout = _decode(result.stdout or b"", "Unity runner stdout")
        stderr = _decode(result.stderr or b"", "Unity runner stderr")
        if result.returncode != 0:
            raise DownstreamPipelineError(
                f"authoritative Unity test failed ({result.returncode})\n{stdout}\n{stderr}"
            )
        match = re.search(r"(?im)^Validation manifest:\s*(.+?)\s*$", stdout)
        if match is None:
            raise DownstreamPipelineError("Unity runner did not print a validation manifest path")
        source_manifest = Path(match.group(1).strip()).resolve(strict=True)
        source_fact = _manifest(source_manifest)
        if source_fact["commit"] != workflow_state["head_commit"]:
            raise DownstreamPipelineError("Unity test validated a different commit")
        expected_tree = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD^{tree}")
        if source_fact["tree"] != expected_tree:
            raise DownstreamPipelineError("Unity test validated a different Git tree")

        output = self._output_root(workflow_state["head_commit"])
        destination = output / "validation" / (
            f"{test_platform}-{hashlib.sha256(test_filter.encode('utf-8')).hexdigest()[:12]}"
        )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_manifest.parent, destination)
        manifest = _manifest(destination / source_manifest.name)
        manifests = [
            item
            for item in self.state.get("validation_manifests") or []
            if not (
                isinstance(item, Mapping)
                and item.get("test_platform") == test_platform
                and item.get("test_filter") == test_filter
            )
        ]
        manifests.append(manifest)
        manifests.sort(key=lambda item: (item["test_platform"], item["test_filter"]))
        self.state["validation_manifests"] = manifests
        self.state["implementation_commit"] = workflow_state["head_commit"]
        self.state["implementation_tree"] = expected_tree
        self._persist()
        return _copy(manifest)

    def create_delivery_review_draft(self) -> dict[str, Any]:
        observation, workflow_state = self._require_lease(WorkflowPhase.DELIVERY_EVIDENCE)
        self._assert_human_tested_head(workflow_state)
        authority = self._latest_validation_authority()
        if authority is None:
            raise DownstreamPipelineError("exact validation authority is unavailable")
        validation_label = (
            "validated" if authority.get("kind") == "automated" else "human-tested"
        )
        required = set(_required_platforms(observation["task"]))
        manifests = [
            _manifest(Path(item["path"]))
            for item in self.state.get("validation_manifests") or []
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)
        ]
        platforms = {item["test_platform"] for item in manifests}
        if not required.issubset(platforms):
            raise DownstreamPipelineError(
                f"missing required authoritative platforms: {sorted(required - platforms)}"
            )
        for item in manifests:
            if item["commit"] != workflow_state["head_commit"]:
                raise DownstreamPipelineError(
                    f"validation manifest is stale for the {validation_label} commit"
                )

        human = (
            self._human_validation_artifact(workflow_state["head_commit"])
            if authority.get("kind") == "human"
            else None
        )
        output_root = self._output_root(workflow_state["head_commit"])
        draft_path = output_root / "delivery-review-draft.json"
        if draft_path.exists():
            stored = self.state.get("draft_path")
            if stored == str(draft_path) and self.state.get("draft_sha256") == file_sha256(draft_path):
                return self.delivery_review_facts()
            raise DownstreamPipelineError("delivery draft path already exists with unknown identity")
        base_commit = _git_text(
            self.command_runner,
            self.checkout,
            "rev-parse",
            f"{workflow_state['head_commit']}^",
        )
        script = self.checkout / "Pipeline" / "TaskDelivery" / "generate_delivery_spec.py"
        command = [
            sys.executable,
            str(script),
            "draft",
            "--root",
            str(self.checkout),
            "--task-id",
            self.task_id,
            "--base-commit",
            base_commit,
        ]
        if human is not None:
            command.extend(("--human-validation", human["path"]))
        command.extend(("--output", str(draft_path)))
        for manifest in manifests:
            command.extend(("--validation-manifest", manifest["path"]))
        _run(self.command_runner, command, cwd=self.checkout, timeout_seconds=900.0)
        draft = _json_object(draft_path.read_bytes(), "delivery review draft")
        if draft.get("review_status") != "needs_human" or draft.get("validated_commit") != workflow_state["head_commit"]:
            raise DownstreamPipelineError("TaskDelivery draft identity is invalid")
        self.state.update(
            {
                "implementation_commit": workflow_state["head_commit"],
                "base_commit": base_commit,
                "human_validation": human,
                "draft_path": str(draft_path),
                "draft_sha256": file_sha256(draft_path),
                "proposal_path": None,
                "proposal_sha256": None,
            }
        )
        if authority.get("kind") == "automated":
            self.state["validation_authority"] = authority
        self._persist()
        return self.delivery_review_facts()

    def delivery_review_facts(self) -> dict[str, Any]:
        draft_path = self.state.get("draft_path")
        if not isinstance(draft_path, str):
            raise DownstreamPipelineError("delivery review draft has not been created")
        path = Path(draft_path)
        if not path.is_file() or file_sha256(path) != self.state.get("draft_sha256"):
            raise DownstreamPipelineError("delivery review draft identity changed")
        draft = _json_object(path.read_bytes(), "delivery review draft")
        return {
            "task_id": self.task_id,
            "draft_path": str(path),
            "draft_sha256": self.state["draft_sha256"],
            "validated_commit": draft.get("validated_commit"),
            "surface_candidates": draft.get("surface_candidates"),
            "artifacts": draft.get("artifacts"),
            "gates": draft.get("gates"),
            "proposal_path": self.state.get("proposal_path"),
            "proposal_sha256": self.state.get("proposal_sha256"),
        }

    def create_delivery_review_proposal(
        self,
        *,
        selected_surfaces: Iterable[Mapping[str, Any]],
        gate_mappings: Iterable[Mapping[str, Any]],
        approval_notes: str,
    ) -> dict[str, Any]:
        _, workflow_state = self._require_lease(WorkflowPhase.DELIVERY_EVIDENCE)
        facts = self.delivery_review_facts()
        output_root = self._output_root(workflow_state["head_commit"])
        revision = 1
        while (output_root / f"delivery-proposal-{revision:02d}.json").exists():
            revision += 1
        result = create_delivery_review_proposal(
            draft_path=Path(facts["draft_path"]),
            output_path=output_root / f"delivery-proposal-{revision:02d}.json",
            task_id=self.task_id,
            branch=workflow_state["branch"],
            selected_surfaces=selected_surfaces,
            gate_mappings=gate_mappings,
            approval_notes=approval_notes,
            created_by=self.workflow.worker_id,
        )
        self.state.update(
            {
                "proposal_path": result["proposal_path"],
                "proposal_sha256": result["proposal_sha256"],
                "proposal_revision": revision,
            }
        )
        self._persist()
        return result

    def publish_delivery_review(self) -> dict[str, Any]:
        if self.issue is None:
            raise DownstreamPipelineError("Issue workflow is unavailable")
        observation = self.observe()
        workflow_state = _workflow_state(observation)
        if workflow_state is None:
            raise DownstreamPipelineError("managed delivery workflow state is unavailable")
        active_delivery = (
            workflow_state.get("state") == WorkflowState.AGENT_WORKING.value
            and workflow_state.get("worker_id") == self.workflow.worker_id
            and workflow_state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
        )
        legacy_review = (
            workflow_state.get("state") == WorkflowState.BLOCKED.value
            and workflow_state.get("current_actor") == "human"
            and workflow_state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
        )
        if not active_delivery and not legacy_review:
            raise DownstreamPipelineError(
                "delivery acceptance requires this worker's lease or a legacy review blocker"
            )
        checkout = observation.get("checkout")
        if not isinstance(checkout, Mapping) or checkout.get("status") != "ready":
            raise DownstreamPipelineError(
                "delivery acceptance requires a clean canonical checkout"
            )
        self._assert_checkout()
        validation_authority = None
        if active_delivery:
            self._assert_human_tested_head(workflow_state)
            validation_authority = self._latest_validation_authority()
            if validation_authority is None:
                raise DownstreamPipelineError("exact validation authority is unavailable")
        facts = self.delivery_review_facts()
        proposal_path = self.state.get("proposal_path")
        proposal_sha = self.state.get("proposal_sha256")
        if not isinstance(proposal_path, str) or not isinstance(proposal_sha, str):
            raise DownstreamPipelineError("delivery proposal has not been created")
        proposal = _json_object(Path(proposal_path).read_bytes(), "delivery proposal")
        if proposal.get("validated_commit") != workflow_state.get("head_commit"):
            raise DownstreamPipelineError(
                "delivery proposal does not target the unchanged "
                + (
                    "validated commit"
                    if validation_authority is not None
                    and validation_authority.get("kind") == "automated"
                    else "human-tested commit"
                )
            )
        return self.issue.accept_unchanged_delivery_after_human_pass(
            task_id=self.task_id,
            branch=workflow_state["branch"],
            head_commit=workflow_state["head_commit"],
            checkout_path=str(self.checkout),
            draft_path=facts["draft_path"],
            draft_sha256=facts["draft_sha256"],
            proposal_path=proposal_path,
            proposal_sha256=proposal_sha,
            validation_authority=validation_authority,
        )

    def finalize_delivery_evidence_and_open_pr(self) -> dict[str, Any]:
        observation, workflow_state = self._require_lease(WorkflowPhase.MERGE_CLOSEOUT)
        approval = self._latest_delivery_approval()
        if approval is None or approval.get("decision") != "approve":
            automated = (
                isinstance(self.state.get("validation_authority"), Mapping)
                and self.state["validation_authority"].get("kind") == "automated"
            )
            raise DownstreamPipelineError(
                "current delivery proposal has not been "
                + ("machine-accepted" if automated else "human-approved")
            )
        proposal_path = self.state.get("proposal_path")
        proposal_sha = self.state.get("proposal_sha256")
        if not isinstance(proposal_path, str) or proposal_sha != approval.get("proposal_sha256"):
            raise DownstreamPipelineError("approved proposal identity differs from local downstream state")
        self._assert_human_tested_head(workflow_state)
        output_root = self._output_root(workflow_state["head_commit"])
        approved_review = output_root / "delivery-review-approved.json"
        if not approved_review.exists():
            if approval.get("approval_basis") == "unchanged_automated_validated_commit":
                authority = self._latest_validation_authority()
                if (
                    authority is None
                    or authority.get("kind") != "automated"
                    or authority.get("event_id")
                    != approval.get("automated_validation_event_id")
                    or authority.get("policy_sha256")
                    != approval.get("validation_policy_sha256")
                ):
                    raise DownstreamPipelineError(
                        "automated delivery acceptance no longer matches validation authority"
                    )
                materialized = materialize_automated_review(
                    proposal_path=Path(proposal_path),
                    expected_proposal_sha256=proposal_sha,
                    output_path=approved_review,
                    validation_event_id=authority["event_id"],
                    validation_policy_sha256=authority["policy_sha256"],
                )
            else:
                materialized = materialize_approved_review(
                    proposal_path=Path(proposal_path),
                    expected_proposal_sha256=proposal_sha,
                    output_path=approved_review,
                    approved_by=approval.get("actor_id") or "Vincent",
                )
            self.state.update(materialized)
        elif self.state.get("approved_review_sha256") != file_sha256(approved_review):
            raise DownstreamPipelineError("approved delivery review identity changed")

        spec_path = output_root / "delivery-spec.json"
        if not spec_path.exists():
            script = self.checkout / "Pipeline" / "TaskDelivery" / "generate_delivery_spec.py"
            _run(
                self.command_runner,
                (
                    sys.executable,
                    str(script),
                    "finalize",
                    "--root",
                    str(self.checkout),
                    "--review",
                    str(approved_review),
                    "--output",
                    str(spec_path),
                ),
                cwd=self.checkout,
                timeout_seconds=900.0,
            )
        self.state["delivery_spec_path"] = str(spec_path)
        self.state["delivery_spec_sha256"] = file_sha256(spec_path)

        if not self.state.get("evidence_commit"):
            token_usage_path = output_root / "token-usage.json"
            token_usage = build_task_token_usage(
                task_id=self.task_id,
                supervisor_output_root=self._task_agent_output_root(),
                checkout_root=self.checkout,
            )
            write_task_token_usage(token_usage_path, token_usage)
            self.state["token_usage_path"] = str(token_usage_path)
            self.state["token_usage_sha256"] = file_sha256(token_usage_path)
            record_script = self.checkout / "Pipeline" / "TaskGraph" / "record_delivery.py"
            package = _run(
                self.command_runner,
                (
                    sys.executable,
                    str(record_script),
                    str(spec_path),
                    "--root",
                    str(self.checkout),
                    "--token-usage",
                    str(token_usage_path),
                    "--json",
                ),
                cwd=self.checkout,
                timeout_seconds=900.0,
            )
            delivery = _json_object(package.stdout, "record_delivery result")
            created = delivery.get("created_paths")
            if not isinstance(created, list) or not created or any(not isinstance(item, str) for item in created):
                raise DownstreamPipelineError("record_delivery returned an invalid created path set")
            _git(self.command_runner, self.checkout, "add", "-f", "--", *created)
            validate = delivery.get("validate_command")
            if not isinstance(validate, list) or not validate:
                raise DownstreamPipelineError("record_delivery omitted draft validation command")
            _run(
                self.command_runner,
                tuple(str(item) for item in validate),
                cwd=self.checkout,
                timeout_seconds=900.0,
            )
            self._validate_staged_whitespace(created)
            staged = _git_text(
                self.command_runner,
                self.checkout,
                "diff",
                "--cached",
                "--name-only",
                "--",
            ).splitlines()
            if tuple(sorted(staged, key=str.casefold)) != tuple(sorted(created, key=str.casefold)):
                raise DownstreamPipelineError("staged evidence paths differ from record_delivery output")
            self._ensure_git_identity()
            _git(
                self.command_runner,
                self.checkout,
                "commit",
                "-m",
                f"Record {self.task_id} delivery evidence",
            )
            evidence_commit = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD")
            if not _SHA40.fullmatch(evidence_commit):
                raise DownstreamPipelineError("evidence commit identity is invalid")
            conformance = self._task_state(self.checkout, self.task_id)
            if conformance.get("state") != "conformant":
                raise DownstreamPipelineError(
                    f"TaskGraph did not derive conformant after evidence commit: {conformance}"
                )
            self._push_evidence_commit(
                branch=workflow_state["branch"],
                prior_commit=workflow_state["head_commit"],
                evidence_commit=evidence_commit,
            )
            self.state.update(
                {
                    "record_id": delivery.get("record_id"),
                    "record_path": delivery.get("record_path"),
                    "created_paths": created,
                    "evidence_commit": evidence_commit,
                    "evidence_tree": _git_text(
                        self.command_runner,
                        self.checkout,
                        "rev-parse",
                        "HEAD^{tree}",
                    ),
                    "conformance_record_id": conformance.get("selected_record_id")
                    or delivery.get("record_id"),
                }
            )
            self._persist()

        pull_request = self._ensure_pull_request(observation)
        self.state.update(
            {
                "pull_request_number": pull_request["number"],
                "pull_request_url": pull_request["url"],
                "pull_request_head": pull_request["headRefOid"],
            }
        )
        self._persist()
        return {
            "status": "pull_request_open",
            "task_id": self.task_id,
            "evidence_commit": self.state["evidence_commit"],
            "record_id": self.state.get("record_id"),
            "record_path": self.state.get("record_path"),
            "pull_request": pull_request,
        }

    def inspect_or_merge_pull_request(self) -> dict[str, Any]:
        _, workflow_state = self._require_lease(WorkflowPhase.MERGE_CLOSEOUT)
        number = self.state.get("pull_request_number")
        if not isinstance(number, int) or number <= 0:
            raise DownstreamPipelineError("pull request has not been created")
        pull_request = self._view_pr(number)
        if pull_request.get("headRefOid") != self.state.get("evidence_commit"):
            raise DownstreamPipelineError("pull-request head differs from evidence commit")
        if pull_request.get("state") == "MERGED":
            merged = pull_request.get("mergeCommit") or {}
            oid = merged.get("oid") if isinstance(merged, Mapping) else None
            if not isinstance(oid, str) or not _SHA40.fullmatch(oid):
                raise DownstreamPipelineError("merged pull request omitted merge commit")
            self.state["merged_commit"] = oid
            self._persist()
            return {"status": "merged", "pull_request": pull_request}
        checks = self._check_state(pull_request.get("statusCheckRollup"))
        if checks["failed"]:
            raise DownstreamPipelineError(
                "pull-request checks failed: " + ", ".join(checks["failed"])
            )
        if checks["pending"] or str(pull_request.get("mergeable") or "").upper() == "UNKNOWN":
            if self.issue is None:
                raise DownstreamPipelineError("Issue workflow is unavailable")
            release = self.issue.release_for_pending_checks(
                task_id=self.task_id,
                pull_request_url=pull_request["url"],
                head_commit=self.state["evidence_commit"],
                reason=(
                    "Pending checks: " + ", ".join(checks["pending"])
                    if checks["pending"]
                    else "GitHub mergeability is still being calculated"
                ),
            )
            return {
                "status": "checks_pending",
                "pull_request": pull_request,
                "release": release,
            }
        if str(pull_request.get("mergeable") or "").upper() not in ("MERGEABLE", "TRUE"):
            raise DownstreamPipelineError(
                f"pull request is not mergeable: {pull_request.get('mergeable')}"
            )
        command = (
            "gh",
            "pr",
            "merge",
            str(number),
            "--repo",
            self._bound_repository(),
            "--merge",
            "--match-head-commit",
            self.state["evidence_commit"],
        )
        _run(self.command_runner, command, cwd=self.checkout, timeout_seconds=900.0)
        merged_pr = self._view_pr(number)
        if merged_pr.get("state") != "MERGED":
            raise DownstreamPipelineError("GitHub did not report the pull request merged")
        merge_commit = (merged_pr.get("mergeCommit") or {}).get("oid")
        if not isinstance(merge_commit, str) or not _SHA40.fullmatch(merge_commit):
            raise DownstreamPipelineError("merged pull request omitted merge commit")
        self.state["merged_commit"] = merge_commit
        self._persist()
        return {"status": "merged", "pull_request": merged_pr}

    def verify_post_merge_and_complete(self) -> dict[str, Any]:
        _, _ = self._require_lease(WorkflowPhase.MERGE_CLOSEOUT)
        merge_commit = self.state.get("merged_commit")
        if not isinstance(merge_commit, str) or not _SHA40.fullmatch(merge_commit):
            raise DownstreamPipelineError("merge commit is unavailable")
        with tempfile.TemporaryDirectory(prefix=f"{self.task_id.casefold()}-post-merge-") as temporary:
            clone = Path(temporary) / "main"
            remote = _git_text(self.command_runner, self.checkout, "remote", "get-url", "origin")
            _run(
                self.command_runner,
                ("git", "clone", "--branch", "main", "--single-branch", remote, str(clone)),
                cwd=self.checkout.parent,
                timeout_seconds=900.0,
            )
            main_head = _git_text(self.command_runner, clone, "rev-parse", "HEAD")
            if main_head != merge_commit:
                raise DownstreamPipelineError(
                    f"origin/main {main_head} differs from merged commit {merge_commit}"
                )
            validation = _run(
                self.command_runner,
                (sys.executable, "Pipeline/TaskGraph/taskcontrol.py", "validate"),
                cwd=clone,
                timeout_seconds=900.0,
            )
            if "taskcontrol validate: PASS" not in _decode(validation.stdout, "taskcontrol validate"):
                raise DownstreamPipelineError("post-merge TaskGraph validation did not pass")
            state = self._task_state(clone, self.task_id)
            if state.get("state") != "conformant":
                raise DownstreamPipelineError(
                    f"post-merge TaskGraph state is not conformant: {state}"
                )
        if self.issue is None:
            raise DownstreamPipelineError("Issue workflow is unavailable")
        result = self.issue.complete(
            task_id=self.task_id,
            pull_request_url=self.state["pull_request_url"],
            pull_request_number=self.state["pull_request_number"],
            merged_commit=merge_commit,
            conformant_record_id=str(
                state.get("selected_record_id")
                or self.state.get("conformance_record_id")
                or self.state.get("record_id")
            ),
        )
        service = self.workflow.issue_workflow
        assert service is not None
        snapshot = service.find(self.task_id)
        if snapshot is not None:
            _run(
                self.command_runner,
                (
                    "gh",
                    "issue",
                    "close",
                    str(snapshot.issue_number),
                    "--repo",
                    self._bound_repository(),
                    "--reason",
                    "completed",
                ),
                cwd=self.checkout,
                timeout_seconds=300.0,
                check=False,
            )
        return {
            "status": "complete",
            "merged_commit": merge_commit,
            "post_merge_state": state,
            "issue": result,
        }

    def _require_lease(
        self,
        phase: WorkflowPhase,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        observation = self.observe()
        state = _workflow_state(observation)
        if (
            state is None
            or state.get("state") != WorkflowState.AGENT_WORKING.value
            or state.get("phase") != phase.value
            or state.get("worker_id") != self.workflow.worker_id
        ):
            raise DownstreamPipelineError(
                f"downstream action requires this worker's {phase.value} lease"
            )
        checkout = observation.get("checkout")
        if not isinstance(checkout, Mapping) or checkout.get("status") != "ready":
            raise DownstreamPipelineError("canonical task checkout is not ready")
        self._assert_checkout()
        return observation, state

    def _assert_checkout(self) -> None:
        if not self.checkout.is_dir():
            raise DownstreamPipelineError("canonical task checkout is missing")
        top = _git_text(
            self.command_runner,
            self.checkout,
            "rev-parse",
            "--show-toplevel",
            check=False,
        )
        if not top or Path(top).resolve() != self.checkout.resolve():
            raise DownstreamPipelineError("checkout is not its standalone Git root")
        status = _git_text(
            self.command_runner,
            self.checkout,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        if status:
            raise DownstreamPipelineError("downstream pipeline requires a clean checkout")

    def _bound_repository(self) -> str:
        """The one repository identity every downstream gh PR/Issue command targets.

        Reuses the durable Issue backend's already-resolved repository (bound
        to the controller source checkout's Git origin -- see
        issue_workflow_store.resolve_issue_backend_repository) and requires it
        to match the task checkout's OWN current Git origin before any gh
        PR/Issue mutation runs. A controller/checkout mismatch fails closed
        here instead of silently reaching a hardcoded repository, and there is
        never a second, independently-configurable repository source.
        """

        service = self.workflow.issue_workflow
        backend = getattr(service, "backend", None) if service is not None else None
        if not isinstance(backend, GhIssueBackend):
            raise DownstreamPipelineError(
                "downstream GitHub PR/Issue commands require a real GhIssueBackend-bound "
                "Issue workflow; no repository authority is available"
            )
        checkout_repository = resolve_issue_backend_repository(self.checkout)
        if checkout_repository.casefold() != backend.repository.casefold():
            raise DownstreamPipelineError(
                f"task checkout {self.checkout} resolves to repository "
                f"{checkout_repository!r} but the durable Issue backend is bound to "
                f"{backend.repository!r}; refusing to run a downstream GitHub PR/Issue "
                "command against a mismatched repository"
            )
        return backend.repository

    def _assert_human_tested_head(self, state: Mapping[str, Any]) -> None:
        head = _git_text(self.command_runner, self.checkout, "rev-parse", "HEAD")
        branch = _git_text(self.command_runner, self.checkout, "branch", "--show-current")
        if head != state.get("head_commit") or branch != state.get("branch"):
            raise DownstreamPipelineError(
                "checkout differs from the exact branch/commit recorded in the human result"
            )
        human = self._latest_human_validation()
        if human is None or human["result"] != "pass" or human["tested_commit"] != head:
            raise DownstreamPipelineError("exact human PASS for checkout HEAD is missing")
        _git(self.command_runner, self.checkout, "fetch", "origin", "main", timeout_seconds=900.0)
        current_main = _git_text(self.command_runner, self.checkout, "rev-parse", "origin/main")
        ancestry = _git(
            self.command_runner,
            self.checkout,
            "merge-base",
            "--is-ancestor",
            current_main,
            head,
            check=False,
        )
        if ancestry.returncode != 0:
            raise DownstreamPipelineError(
                "origin/main advanced beyond the human-tested branch. Integrate current main "
                "and repeat the human validation handoff before packaging evidence."
            )

    def _latest_human_validation(self) -> dict[str, Any] | None:
        service = self.workflow.issue_workflow
        if service is None:
            return None
        snapshot = service.find(self.task_id)
        if snapshot is None:
            return None
        for comment in reversed(service.backend.get_comments(snapshot.issue_number)):
            body = comment.get("body") if isinstance(comment, Mapping) else None
            if not isinstance(body, str):
                continue
            result = parse_human_validation_result(body)
            if result is not None:
                return {
                    "result": result.result,
                    "tested_commit": result.tested_commit,
                    "body": result.body,
                    "comment_id": comment.get("id"),
                }
        return None

    def _latest_validation_authority(self) -> dict[str, Any] | None:
        """Return the legacy human authority unless an installed extension adds more."""

        human = self._latest_human_validation()
        return {"kind": "human", **human} if human is not None else None

    def _human_validation_artifact(self, commit: str) -> dict[str, Any]:
        current = self.state.get("human_validation")
        if isinstance(current, Mapping):
            path = Path(str(current.get("path") or ""))
            if path.is_file() and file_sha256(path) == current.get("sha256"):
                return dict(current)
        human = self._latest_human_validation()
        if human is None or human["result"] != "pass" or human["tested_commit"] != commit:
            raise DownstreamPipelineError("human PASS artifact is unavailable")
        service = self.workflow.issue_workflow
        assert service is not None
        snapshot = service.find(self.task_id)
        assert snapshot is not None
        output = self._output_root(commit) / "human-validation.txt"
        if output.exists():
            raise DownstreamPipelineError("human-validation output exists with unknown identity")
        text = "\n".join(
            (
                f"Task: {self.task_id}",
                f"Issue: {snapshot.issue_url}",
                f"Tested commit: {commit}",
                "Result: PASS",
                "",
                human["body"].strip(),
                "",
            )
        )
        output.write_text(text, encoding="utf-8", newline="\n")
        fact = _file_fact(output)
        return fact

    def _latest_delivery_approval(self) -> dict[str, Any] | None:
        service = self.workflow.issue_workflow
        if service is None:
            return None
        snapshot = service.find(self.task_id)
        if snapshot is None:
            return None
        for event in reversed(snapshot.events):
            if (
                event.event_type in (
                    WorkflowEventType.UNBLOCKED,
                    WorkflowEventType.AGENT_LEASE_RELEASED,
                )
                and event.details.get("review_kind") == "delivery_spec"
                and event.details.get("decision") in ("approve", "request_changes")
            ):
                approval = {
                    "decision": event.details.get("decision"),
                    "proposal_sha256": event.details.get("proposal_sha256"),
                    "actor_id": event.details.get("authorized_by") or event.actor_id,
                    "event_id": event.event_id,
                    "comment_body": event.details.get("human_comment_body"),
                }
                if (
                    event.details.get("approval_basis")
                    == "unchanged_automated_validated_commit"
                ):
                    approval.update(
                        {
                            "approval_basis": event.details["approval_basis"],
                            "automated_validation_event_id": event.details.get(
                                "automated_validation_event_id"
                            ),
                            "validation_policy_sha256": event.details.get(
                                "validation_policy_sha256"
                            ),
                        }
                    )
                return approval
        return None

    def _validate_staged_whitespace(self, created: list[str]) -> None:
        result = _git(
            self.command_runner,
            self.checkout,
            "diff",
            "--cached",
            "--check",
            "--",
            *created,
            check=False,
        )
        if result.returncode != 0:
            output = _decode(result.stdout + result.stderr, "staged whitespace check")
            raise DownstreamPipelineError(
                "staged evidence failed whitespace validation; Unity logs must be "
                "normalized before their validation manifest is created:\n" + output
            )

    def _ensure_git_identity(self) -> None:
        if not _git_text(self.command_runner, self.checkout, "config", "user.name", check=False):
            _git(
                self.command_runner,
                self.checkout,
                "config",
                "user.name",
                os.getenv("NSC_AGENT_GIT_NAME", "No Safe Circle TaskReviewAgent"),
            )
        if not _git_text(self.command_runner, self.checkout, "config", "user.email", check=False):
            _git(
                self.command_runner,
                self.checkout,
                "config",
                "user.email",
                os.getenv("NSC_AGENT_GIT_EMAIL", "task-review-agent@users.noreply.github.com"),
            )

    def _task_state(self, root: Path, task_id: str) -> dict[str, Any]:
        result = _run(
            self.command_runner,
            (
                sys.executable,
                "Pipeline/TaskGraph/taskcontrol.py",
                "state",
                task_id,
                "--json",
            ),
            cwd=root,
            timeout_seconds=900.0,
        )
        return _json_object(result.stdout, "taskcontrol state")

    def _push_evidence_commit(
        self,
        *,
        branch: str,
        prior_commit: str,
        evidence_commit: str,
    ) -> None:
        remote = _git_text(
            self.command_runner,
            self.checkout,
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
            check=False,
        ).split()
        remote_head = remote[0] if remote else None
        if remote_head not in (prior_commit, evidence_commit):
            raise DownstreamPipelineError(
                f"remote task branch moved unexpectedly to {remote_head}"
            )
        if remote_head != evidence_commit:
            _git(
                self.command_runner,
                self.checkout,
                "push",
                "origin",
                f"HEAD:refs/heads/{branch}",
                timeout_seconds=900.0,
            )
        verified = _git_text(
            self.command_runner,
            self.checkout,
            "ls-remote",
            "--heads",
            "origin",
            f"refs/heads/{branch}",
        ).split()[0]
        if verified != evidence_commit:
            raise DownstreamPipelineError("remote branch does not equal evidence commit")

    def _ensure_pull_request(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        branch = (_workflow_state(observation) or {}).get("branch")
        if not isinstance(branch, str):
            branch = _git_text(self.command_runner, self.checkout, "branch", "--show-current")
        listed = _run(
            self.command_runner,
            (
                "gh",
                "pr",
                "list",
                "--repo",
                self._bound_repository(),
                "--head",
                branch,
                "--base",
                "main",
                "--state",
                "open",
                "--json",
                "number,url,state,headRefOid,isDraft,mergeable,statusCheckRollup,mergeCommit",
            ),
            cwd=self.checkout,
            timeout_seconds=300.0,
        )
        values = json.loads(_decode(listed.stdout, "gh pr list"))
        if not isinstance(values, list):
            raise DownstreamPipelineError("gh pr list did not return an array")
        matches = [item for item in values if isinstance(item, Mapping)]
        if len(matches) > 1:
            raise DownstreamPipelineError("multiple open pull requests use the task branch")
        if matches:
            pull_request = dict(matches[0])
        else:
            task = observation["task"]
            body = "\n".join(
                (
                    f"## {self.task_id} delivery",
                    "",
                    f"Implements `{task.get('title')}` and records validated TaskGraph delivery evidence.",
                    "",
                    f"- Human-tested implementation commit: `{self.state.get('implementation_commit')}`",
                    f"- Evidence commit: `{self.state.get('evidence_commit')}`",
                    f"- Delivery record: `{self.state.get('record_path')}`",
                    f"- Derived branch state before PR: `conformant`",
                    "",
                    "The merge must preserve history. Post-merge TaskGraph conformance is verified before the managed Issue is completed.",
                )
            )
            created = _run(
                self.command_runner,
                (
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    self._bound_repository(),
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    f"{self.task_id}: {task.get('title')}",
                    "--body",
                    body,
                ),
                cwd=self.checkout,
                timeout_seconds=300.0,
            )
            url = _decode(created.stdout, "gh pr create").strip()
            if not url:
                raise DownstreamPipelineError("gh pr create did not return a URL")
            number_match = re.search(r"/(\d+)$", url)
            if number_match is None:
                raise DownstreamPipelineError("gh pr create returned an invalid URL")
            pull_request = self._view_pr(int(number_match.group(1)))
        if pull_request.get("headRefOid") != self.state.get("evidence_commit"):
            raise DownstreamPipelineError("pull request does not point to the evidence commit")
        return pull_request

    def _view_pr(self, number: int) -> dict[str, Any]:
        result = _run(
            self.command_runner,
            (
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                self._bound_repository(),
                "--json",
                "number,url,state,headRefOid,baseRefName,isDraft,mergeable,mergeStateStatus,statusCheckRollup,mergeCommit",
            ),
            cwd=self.checkout,
            timeout_seconds=300.0,
        )
        value = json.loads(_decode(result.stdout, "gh pr view"))
        if not isinstance(value, dict):
            raise DownstreamPipelineError("gh pr view did not return an object")
        return value

    def _check_state(self, raw: Any) -> dict[str, list[str]]:
        pending: list[str] = []
        failed: list[str] = []
        passed: list[str] = []
        if raw is None:
            return {"pending": pending, "failed": failed, "passed": passed}
        if not isinstance(raw, list):
            raise DownstreamPipelineError("pull-request statusCheckRollup is invalid")
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or item.get("context") or f"check-{index + 1}")
            status = str(item.get("status") or "").upper()
            conclusion = str(item.get("conclusion") or item.get("state") or "").upper()
            if status not in ("COMPLETED", "") or conclusion in ("PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS", ""):
                pending.append(name)
            elif conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                passed.append(name)
            else:
                failed.append(name)
        return {"pending": pending, "failed": failed, "passed": passed}

    def _output_root(self, commit: str) -> Path:
        return _external_root(self.task_id, commit, self.explicit_output_root)

    def _task_agent_output_root(self) -> Path:
        explicit = getattr(self, "explicit_output_root", None)
        if explicit is not None:
            return Path(explicit).expanduser().resolve()
        configured = os.getenv("NSC_TASK_AGENT_OUTPUT_ROOT")
        if configured:
            return Path(configured).expanduser().resolve()
        return (self.checkout.parent / ".task-review-agent" / "outputs").resolve()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict) or raw.get("schema_version") != DOWNSTREAM_SCHEMA_VERSION:
            return {}
        identity = dict(raw)
        receipt_hash = identity.pop("receipt_sha256", None)
        if receipt_hash != semantic_sha256(identity):
            return {}
        if raw.get("task_id") != self.task_id:
            return {}
        return raw

    def _persist(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = {
            **self.state,
            "schema_version": DOWNSTREAM_SCHEMA_VERSION,
            "task_id": self.task_id,
        }
        identity = dict(payload)
        identity.pop("receipt_sha256", None)
        payload["receipt_sha256"] = semantic_sha256(identity)
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.state_path)
        self.state = payload
