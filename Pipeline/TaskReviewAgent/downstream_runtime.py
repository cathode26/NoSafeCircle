"""Production wrappers that keep downstream state resumable across agent runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .delivery_review import file_sha256
from .downstream_issue import DownstreamIssueCoordinator, DownstreamIssueError, _meaningful
from .downstream_pipeline import (
    _SHA40,
    _VALID_PLATFORMS,
    DownstreamPipelineError,
    DownstreamTaskController,
    _copy,
    _decode,
    _file_fact,
    _git,
    _git_text,
    _json_object,
    _manifest,
    _required_platforms,
    _run,
)
from .issue_workflow import (
    WorkflowActor,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    labels_for_state,
    render_event_comment,
    transition,
    update_issue_body,
    utc_now,
)
from .issue_workflow_store import IssueWorkflowStoreError
from .real_workflow import RealTaskReviewWorkflow


_READ_PREFIXES = (
    "Assets/",
    "Tasks/",
    "Docs/GDD/",
    "Docs/Engineering/",
    "Docs/AI-Pipeline/UNITY_PROGRAMMER_LANGUAGE.md",
)
_DOWNSTREAM_DERIVED_STATES = frozenset(
    {
        "not_delivered",
        "needs_testing",
        "conformant",
    }
)


def _safe_prefix(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DownstreamPipelineError("repository prefix must be non-empty")
    value = value.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise DownstreamPipelineError("repository prefix must be a safe relative path")
    check = value if value.endswith("/") else value + "/"
    if not any(
        check.casefold().startswith(prefix.casefold())
        or prefix.casefold().startswith(check.casefold())
        for prefix in _READ_PREFIXES
    ):
        raise DownstreamPipelineError("repository prefix is outside downstream read roots")
    return value


class DownstreamTaskReviewWorkflow(RealTaskReviewWorkflow):
    """Permit a known managed downstream Issue to resume after evidence exists.

    This workflow class is only selected after the durable Issue has already proved
    that its phase is delivery_evidence or merge_closeout. It deliberately does not
    change the ordinary implementation workflow's dispatch policy.
    """

    def _task_ready_for_coordination(
        self,
        environment: dict[str, Any],
        task: dict[str, Any],
    ) -> bool:
        return (
            environment.get("ready") is True
            and environment.get("controller_clean") is True
            and environment.get("taskgraph_valid") is True
            and task.get("contract_disposition") == "active"
            and task.get("kind") == "implementation"
            and task.get("execution_scope") == "single_agent"
            and task.get("decomposition_state") == "concrete"
            and task.get("derived_state") in _DOWNSTREAM_DERIVED_STATES
            and task.get("dependencies_conformant") is True
        )


class ResumableDownstreamIssueCoordinator(DownstreamIssueCoordinator):
    """Advance the managed checkout identity when an evidence commit is published."""

    def release_for_pending_checks(
        self,
        *,
        task_id: str,
        pull_request_url: str,
        head_commit: str,
        reason: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        snapshot = self.service.find(task_id)
        if snapshot is None or not snapshot.valid or snapshot.state is None:
            raise DownstreamIssueError("lease release requires a valid Issue")
        state = snapshot.state
        if (
            state.state is not WorkflowState.AGENT_WORKING
            or state.worker_id != self.worker_id
            or state.phase is not WorkflowPhase.MERGE_CLOSEOUT
        ):
            raise DownstreamIssueError(
                "pending-check release requires this worker's merge_closeout lease"
            )
        exact_head = _meaningful(head_commit, "head_commit")
        if not _SHA40.fullmatch(exact_head):
            raise DownstreamIssueError("head_commit must be a lowercase 40-character SHA")
        next_state, event = transition(
            state,
            event_type=WorkflowEventType.AGENT_LEASE_RELEASED,
            actor_type=WorkflowActor.AGENT,
            actor_id=self.worker_id,
            to_state=WorkflowState.AGENT_READY,
            to_phase=WorkflowPhase.MERGE_CLOSEOUT,
            details={
                "reason": _meaningful(reason, "reason"),
                "pull_request_url": _meaningful(
                    pull_request_url, "pull_request_url"
                ),
                "head_commit": exact_head,
            },
            now=now or utc_now(),
        )
        # Keep Vincent's original human_handoff_commit intact while advancing the
        # exact branch head that the next generic agent must resume.
        next_state = replace(next_state, head_commit=exact_head)
        self.service.backend.add_comment(
            snapshot.issue_number,
            render_event_comment(
                event,
                "The evidence commit and pull request are published. The agent "
                "released its lease so any later generic agent can resume merge "
                f"closeout at `{exact_head}` from {pull_request_url}.",
            ),
        )
        self.service.backend.update_issue(
            snapshot.issue_number,
            body=update_issue_body(
                snapshot.body,
                next_state,
                next_action=(
                    "Resume merge closeout at the recorded evidence commit, inspect "
                    "pull-request checks, and merge only after they pass."
                ),
            ),
            labels=labels_for_state(next_state.state, snapshot.labels),
            assignees=[self.service.assignee],
        )
        verified = self.service.find(task_id)
        if verified is None or not verified.valid or verified.state != next_state:
            raise IssueWorkflowStoreError(
                "evidence-head lease release could not be verified"
            )
        return {"status": "agent_ready", **verified.to_dict()}


class ResumableDownstreamTaskController(DownstreamTaskController):
    """Connected controller used by the generic launcher."""

    def __init__(self, **values: Any) -> None:
        super().__init__(**values)
        if self.workflow.issue_workflow is not None:
            self.issue = ResumableDownstreamIssueCoordinator(
                self.workflow.issue_workflow
            )

    def _next_action(
        self,
        observation: Mapping[str, Any],
        state: Mapping[str, Any] | None,
    ) -> str:
        action = super()._next_action(observation, state)
        if (
            state is not None
            and state.get("state") == WorkflowState.AGENT_WORKING.value
            and state.get("worker_id") == self.workflow.worker_id
            and state.get("phase") == WorkflowPhase.DELIVERY_EVIDENCE.value
        ):
            approval = self._latest_delivery_approval()
            if (
                approval is not None
                and approval.get("decision") == "request_changes"
                and approval.get("proposal_sha256")
                == self.state.get("proposal_sha256")
            ):
                return "create_delivery_review_proposal"
        return action

    def list_repository_files(
        self,
        *,
        prefix: str = "Assets/",
        limit: int = 300,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise DownstreamPipelineError(
                "repository file limit must be 1 through 1000"
            )
        prefix = _safe_prefix(prefix)
        raw = _git_text(
            self.command_runner,
            self.checkout,
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            prefix,
        )
        paths = [line for line in raw.splitlines() if line]
        return {
            "prefix": prefix,
            "count": min(len(paths), limit),
            "truncated": len(paths) > limit,
            "paths": paths[:limit],
        }

    def search_repository(
        self,
        *,
        query: str,
        prefixes: Iterable[str] = ("Assets/",),
        limit: int = 100,
    ) -> dict[str, Any]:
        self._assert_checkout()
        if not isinstance(query, str) or not query.strip() or len(query) > 160:
            raise DownstreamPipelineError(
                "search query must be 1 through 160 characters"
            )
        if any(ord(character) < 32 or ord(character) == 127 for character in query):
            raise DownstreamPipelineError("search query contains a control character")
        if not isinstance(limit, int) or not 1 <= limit <= 300:
            raise DownstreamPipelineError("search limit must be 1 through 300")
        approved = [_safe_prefix(value) for value in prefixes]
        result = _git(
            self.command_runner,
            self.checkout,
            "grep",
            "-n",
            "-I",
            "-F",
            "--",
            query,
            "HEAD",
            "--",
            *approved,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise DownstreamPipelineError("git grep failed")
        matches: list[dict[str, Any]] = []
        for line in _decode(result.stdout, "git grep output").splitlines():
            rendered = line[5:] if line.startswith("HEAD:") else line
            try:
                path, line_number, text = rendered.split(":", 2)
                matches.append(
                    {
                        "path": path,
                        "line": int(line_number),
                        "text": text[:500],
                    }
                )
            except (TypeError, ValueError):
                continue
            if len(matches) >= limit:
                break
        return {
            "query": query,
            "prefixes": approved,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "matches": matches,
        }

    def _assert_human_tested_head(self, state: Mapping[str, Any]) -> None:
        super()._assert_human_tested_head(state)
        base_commit = _git_text(
            self.command_runner,
            self.checkout,
            "rev-parse",
            "origin/main",
        )
        if not _SHA40.fullmatch(base_commit):
            raise DownstreamPipelineError("origin/main did not resolve to a commit")
        if base_commit == state.get("head_commit"):
            raise DownstreamPipelineError(
                "human-tested task branch contains no commits beyond current main"
            )
        existing = self.state.get("delivery_base_commit")
        if existing is not None and existing != base_commit:
            raise DownstreamPipelineError(
                "origin/main changed after authoritative downstream work began. "
                "Integrate current main and repeat the human validation handoff."
            )
        if existing is None:
            self.state["delivery_base_commit"] = base_commit
            self._persist()

    def run_authoritative_unity_test(
        self,
        *,
        test_platform: str,
        test_filter: str,
    ) -> dict[str, Any]:
        _, workflow_state = self._require_lease(WorkflowPhase.DELIVERY_EVIDENCE)
        if test_platform not in _VALID_PLATFORMS:
            raise DownstreamPipelineError(
                "test_platform must be EditMode or PlayMode"
            )
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
            timeout_seconds=float(
                os.getenv("NSC_TASK_AGENT_UNITY_TIMEOUT_SECONDS", "3600")
            ),
            check=False,
        )
        stdout = _decode(result.stdout or b"", "Unity runner stdout")
        stderr = _decode(result.stderr or b"", "Unity runner stderr")
        if result.returncode != 0:
            raise DownstreamPipelineError(
                f"authoritative Unity test failed ({result.returncode})\n"
                f"{stdout}\n{stderr}"
            )
        match = re.search(
            r"(?im)^Validation manifest:\s*(.+?)\s*$",
            stdout,
        )
        if match is None:
            raise DownstreamPipelineError(
                "Unity runner did not print a validation manifest path"
            )
        source_manifest = Path(match.group(1).strip()).resolve(strict=True)
        source_fact = _manifest(source_manifest)
        if source_fact["commit"] != workflow_state["head_commit"]:
            raise DownstreamPipelineError(
                "Unity test validated a different commit"
            )
        expected_tree = _git_text(
            self.command_runner,
            self.checkout,
            "rev-parse",
            "HEAD^{tree}",
        )
        if source_fact["tree"] != expected_tree:
            raise DownstreamPipelineError(
                "Unity test validated a different Git tree"
            )

        output = self._output_root(workflow_state["head_commit"])
        destination = output / "validation" / (
            f"{test_platform}-"
            f"{hashlib.sha256(test_filter.encode('utf-8')).hexdigest()[:12]}"
        )
        if destination.exists() or destination.is_symlink():
            raise DownstreamPipelineError(
                "validation destination already exists with unknown identity: "
                f"{destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
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
        manifests.sort(
            key=lambda item: (item["test_platform"], item["test_filter"])
        )
        self.state["validation_manifests"] = manifests
        self.state["implementation_commit"] = workflow_state["head_commit"]
        self.state["implementation_tree"] = expected_tree
        self._persist()
        return _copy(manifest)

    def create_delivery_review_draft(self) -> dict[str, Any]:
        observation, workflow_state = self._require_lease(
            WorkflowPhase.DELIVERY_EVIDENCE
        )
        self._assert_human_tested_head(workflow_state)
        required = set(_required_platforms(observation["task"]))
        manifests = [
            _manifest(Path(item["path"]))
            for item in self.state.get("validation_manifests") or []
            if isinstance(item, Mapping) and isinstance(item.get("path"), str)
        ]
        platforms = {item["test_platform"] for item in manifests}
        if not required.issubset(platforms):
            raise DownstreamPipelineError(
                "missing required authoritative platforms: "
                f"{sorted(required - platforms)}"
            )
        for item in manifests:
            if item["commit"] != workflow_state["head_commit"]:
                raise DownstreamPipelineError(
                    "validation manifest is stale for the human-tested commit"
                )

        human = self._human_validation_artifact(
            workflow_state["head_commit"]
        )
        output_root = self._output_root(workflow_state["head_commit"])
        draft_path = output_root / "delivery-review-draft.json"
        if draft_path.exists():
            stored = self.state.get("draft_path")
            if (
                stored == str(draft_path)
                and self.state.get("draft_sha256")
                == file_sha256(draft_path)
            ):
                return self.delivery_review_facts()
            raise DownstreamPipelineError(
                "delivery draft path already exists with unknown identity"
            )
        base_commit = self.state.get("delivery_base_commit")
        if not isinstance(base_commit, str) or not _SHA40.fullmatch(base_commit):
            raise DownstreamPipelineError(
                "stable delivery base commit is unavailable"
            )
        if (
            _git(
                self.command_runner,
                self.checkout,
                "merge-base",
                "--is-ancestor",
                base_commit,
                workflow_state["head_commit"],
                check=False,
            ).returncode
            != 0
        ):
            raise DownstreamPipelineError(
                "delivery base is not an ancestor of the human-tested commit"
            )
        script = (
            self.checkout
            / "Pipeline"
            / "TaskDelivery"
            / "generate_delivery_spec.py"
        )
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
            "--human-validation",
            human["path"],
            "--output",
            str(draft_path),
        ]
        for manifest in manifests:
            command.extend(("--validation-manifest", manifest["path"]))
        _run(
            self.command_runner,
            command,
            cwd=self.checkout,
            timeout_seconds=900.0,
        )
        draft = _json_object(
            draft_path.read_bytes(),
            "delivery review draft",
        )
        if (
            draft.get("review_status") != "needs_human"
            or draft.get("validated_commit")
            != workflow_state["head_commit"]
            or draft.get("base_commit") != base_commit
        ):
            raise DownstreamPipelineError(
                "TaskDelivery draft identity is invalid"
            )
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
        self._persist()
        return self.delivery_review_facts()

    def finalize_delivery_evidence_and_open_pr(self) -> dict[str, Any]:
        result = super().finalize_delivery_evidence_and_open_pr()
        if self.issue is None:
            raise DownstreamPipelineError("Issue workflow is unavailable")
        evidence_commit = self.state.get("evidence_commit")
        pull_request_url = self.state.get("pull_request_url")
        if not isinstance(evidence_commit, str) or not isinstance(
            pull_request_url, str
        ):
            raise DownstreamPipelineError(
                "delivery finalization did not persist PR/evidence identities"
            )
        release = self.issue.release_for_pending_checks(
            task_id=self.task_id,
            pull_request_url=pull_request_url,
            head_commit=evidence_commit,
            reason=(
                "Delivery evidence was committed, TaskGraph derived conformant, and "
                "the pull request was opened. Resume after its checks finish."
            ),
        )
        return {
            **_copy(result),
            "status": "checks_pending",
            "lease_release": release,
        }

    def verify_post_merge_and_complete(self) -> dict[str, Any]:
        _, _ = self._require_lease(WorkflowPhase.MERGE_CLOSEOUT)
        merge_commit = self.state.get("merged_commit")
        if not isinstance(merge_commit, str) or not _SHA40.fullmatch(
            merge_commit
        ):
            raise DownstreamPipelineError("merge commit is unavailable")
        with tempfile.TemporaryDirectory(
            prefix=f"{self.task_id.casefold()}-post-merge-"
        ) as temporary:
            clone = Path(temporary) / "main"
            remote = _git_text(
                self.command_runner,
                self.checkout,
                "remote",
                "get-url",
                "origin",
            )
            _run(
                self.command_runner,
                (
                    "git",
                    "clone",
                    "--branch",
                    "main",
                    "--single-branch",
                    remote,
                    str(clone),
                ),
                cwd=self.checkout.parent,
                timeout_seconds=900.0,
            )
            main_head = _git_text(
                self.command_runner,
                clone,
                "rev-parse",
                "HEAD",
            )
            if (
                _git(
                    self.command_runner,
                    clone,
                    "merge-base",
                    "--is-ancestor",
                    merge_commit,
                    main_head,
                    check=False,
                ).returncode
                != 0
            ):
                raise DownstreamPipelineError(
                    f"merged commit {merge_commit} is not contained in "
                    f"origin/main {main_head}"
                )
            validation = _run(
                self.command_runner,
                (
                    sys.executable,
                    "Pipeline/TaskGraph/taskcontrol.py",
                    "validate",
                ),
                cwd=clone,
                timeout_seconds=900.0,
            )
            if "taskcontrol validate: PASS" not in _decode(
                validation.stdout,
                "taskcontrol validate",
            ):
                raise DownstreamPipelineError(
                    "post-merge TaskGraph validation did not pass"
                )
            state = self._task_state(clone, self.task_id)
            if state.get("state") != "conformant":
                raise DownstreamPipelineError(
                    "post-merge TaskGraph state is not conformant: "
                    f"{state}"
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
                    "cathode26/NoSafeCircle",
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
            "main_head": main_head,
            "post_merge_state": state,
            "issue": result,
        }
