"""Publish one exact human-approved AssistantControl candidate for CI.

This adapter owns only the task branch, one pull request, and durable CI
observations.  It never uses managed Issues, integrates Source, merges a pull
request, starts a provider, or pushes the base branch.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Pipeline.AssistantControl.checkouts import Checkouts
from Pipeline.AssistantControl.inspect_project import git
from Pipeline.AssistantControl.review import ReviewGate
from Pipeline.TaskReviewAgent.contracts import semantic_sha256, validate_task_id
from Pipeline.TaskReviewAgent.issue_workflow_store import resolve_issue_backend_repository
from Pipeline.TaskReviewAgent.pull_request_check_authority import (
    latest_effective_check_state,
)


SCHEMA_VERSION = "assistant-publication/v1"
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_PR_URL = re.compile(r"/pull/(?P<number>[1-9][0-9]*)/?\Z")
_POLICY = {
    "approval_authority": "exact_human_review_only",
    "branch_update": "exact_recorded_head_compare_and_swap",
    "check_authority": "verified_pull_request_head",
    "issues": False,
    "auto_merge": False,
    "provider_calls": False,
}


class PublicationError(ValueError):
    """The publication boundary could not prove an exact safe continuation."""


CommandRunner = Callable[
    [Sequence[str], Path, float], subprocess.CompletedProcess[bytes]
]
RepositoryResolver = Callable[..., str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_runner(
    args: Sequence[str], cwd: Path, timeout_seconds: float,
) -> subprocess.CompletedProcess[bytes]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update({
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        return subprocess.run(
            tuple(args), cwd=str(cwd), env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=timeout_seconds, creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError("publication command could not run") from exc


def _decode(data: bytes | None, label: str) -> str:
    try:
        return (data or b"").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublicationError(f"{label} was not valid UTF-8") from exc


def _json(data: bytes | None, label: str) -> Any:
    try:
        return json.loads(_decode(data, label))
    except json.JSONDecodeError as exc:
        raise PublicationError(f"{label} was not valid JSON") from exc


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA40.fullmatch(value):
        raise PublicationError(f"{field} must be an exact 40-character Git SHA")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> str:
    """Flush, atomically replace, and read back one deterministic JSON value."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n").encode("utf-8")
    expected = hashlib.sha256(data).hexdigest()
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    replaced = False
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        replaced = True
    finally:
        if not replaced:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise PublicationError("publication receipt read-back hash differs")
    return expected


def _event_body(event: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "event_sha256"}


def _verify_ledger(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise PublicationError("publication receipt schema is invalid")
    if not isinstance(value.get("identity"), dict) or not isinstance(value.get("events"), list):
        raise PublicationError("publication receipt structure is invalid")
    previous = None
    for index, event in enumerate(value["events"], 1):
        if (not isinstance(event, dict) or event.get("sequence") != index
                or event.get("previous_sha256") != previous):
            raise PublicationError("publication receipt event chain is invalid")
        digest = semantic_sha256(_event_body(event))
        if event.get("event_sha256") != digest:
            raise PublicationError("publication receipt event hash differs")
        previous = digest
    return value


class PublicationAdapter:
    """Bounded task-branch publication and exact-head CI observation."""

    def __init__(
        self,
        checkouts: Checkouts,
        *,
        command_runner: CommandRunner | None = None,
        repository_resolver: RepositoryResolver | None = None,
    ) -> None:
        self.checkouts = checkouts
        self.command_runner = command_runner or _default_runner
        self.repository_resolver = repository_resolver or resolve_issue_backend_repository

    def _run(
        self, args: Sequence[str], *, cwd: Path, label: str,
        timeout_seconds: float = 300.0, check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        result = self.command_runner(tuple(args), cwd, timeout_seconds)
        if check and result.returncode != 0:
            detail = _decode(result.stderr, f"{label} stderr").strip()
            raise PublicationError(
                f"{label} failed ({result.returncode})" + (f": {detail}" if detail else "")
            )
        return result

    def _origin_url(self) -> str:
        result = self._run(
            ("git", "-C", str(self.checkouts.source), "remote", "get-url", "origin"),
            cwd=self.checkouts.source, label="source origin read",
        )
        value = _decode(result.stdout, "source origin").strip()
        if not value:
            raise PublicationError("Source origin is empty")
        return value

    def _binding(
        self, record: Mapping[str, Any], candidate_commit: str,
        base_branch: str, repository: str | None,
    ) -> tuple[dict[str, Any], str]:
        task_id = validate_task_id(record.get("task_id"))
        candidate = record.get("candidate")
        human = record.get("human_review")
        if not isinstance(candidate, Mapping) or not isinstance(human, Mapping):
            raise PublicationError("approved candidate identity is incomplete")
        _sha(candidate_commit, "candidate_commit")
        tree = _sha(candidate.get("tree"), "candidate_tree")
        branch = str(record.get("branch") or "")
        if not branch or not base_branch:
            raise PublicationError("task and base branches must be non-empty")
        if branch != f"assistant/{task_id}" or branch == base_branch:
            raise PublicationError("publication requires the owned AssistantControl task branch")
        git(self.checkouts.source, "check-ref-format", "--branch", branch)
        git(self.checkouts.source, "check-ref-format", "--branch", base_branch)
        origin_url = self._origin_url()
        resolved = self.repository_resolver(
            self.checkouts.source, repository=repository,
        )
        if not isinstance(resolved, str) or not resolved.strip():
            raise PublicationError("Source origin did not resolve a repository identity")
        if self._origin_url() != origin_url:
            raise PublicationError("Source origin changed during repository binding")
        policy_sha256 = semantic_sha256(_POLICY)
        identity = {
            "task_id": task_id,
            "source": str(self.checkouts.source),
            "checkout_root": str(self.checkouts.root),
            "checkout": str(Path(record["checkout"]).resolve()),
            "task_branch": branch,
            "base_branch": base_branch,
            "repository": resolved,
            "policy": dict(_POLICY),
            "policy_sha256": policy_sha256,
        }
        approval = {
            "candidate_commit": candidate_commit,
            "candidate_tree": tree,
            "candidate_parent": candidate.get("parent"),
            "task_contract_sha256": record.get("task_contract_sha256"),
            "human_review_sha256": semantic_sha256(dict(human)),
        }
        return {"identity": identity, "approval": approval}, origin_url

    def _receipt_path(self, task_id: str) -> Path:
        return self.checkouts.records / "publications" / f"{task_id}.json"

    def _load_ledger(self, identity: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
        path = self._receipt_path(str(identity["task_id"]))
        if path.exists():
            try:
                ledger = _verify_ledger(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PublicationError("publication receipt is unreadable") from exc
            if ledger["identity"] != dict(identity):
                raise PublicationError("publication receipt belongs to a different identity")
            return path, ledger
        return path, {
            "schema_version": SCHEMA_VERSION,
            "identity": dict(identity),
            "events": [],
        }

    def _append_event(
        self, path: Path, ledger: dict[str, Any], *, kind: str,
        approval: Mapping[str, Any], operation_id: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        events = ledger["events"]
        previous = events[-1]["event_sha256"] if events else None
        event = {
            "sequence": len(events) + 1,
            "utc": _utc_now(),
            "kind": kind,
            "operation_id": operation_id,
            "candidate_commit": approval["candidate_commit"],
            "candidate_tree": approval["candidate_tree"],
            "approval_sha256": approval["human_review_sha256"],
            "payload": dict(payload),
            "previous_sha256": previous,
        }
        event["event_sha256"] = semantic_sha256(event)
        events.append(event)
        _verify_ledger(ledger)
        _atomic_write_json(path, ledger)
        return event

    @staticmethod
    def _events(
        ledger: Mapping[str, Any], kind: str, candidate_commit: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            event for event in ledger["events"]
            if event.get("kind") == kind
            and (candidate_commit is None or event.get("candidate_commit") == candidate_commit)
        ]

    def _observe_ref(self, checkout: Path, origin_url: str, ref: str) -> tuple[str, str | None]:
        result = self._run(
            ("git", "-C", str(checkout), "ls-remote", "--heads", origin_url, ref),
            cwd=checkout, label="remote task-branch read", check=False,
        )
        if result.returncode != 0:
            return "unknown", None
        lines = [line for line in _decode(result.stdout, "remote task-branch read").splitlines()
                 if line.strip()]
        if not lines:
            return "absent", None
        if len(lines) != 1:
            return "unknown", None
        oid = lines[0].split(None, 1)[0]
        return ("present", oid) if _SHA40.fullmatch(oid) else ("unknown", None)

    def _publish_branch(
        self, *, checkout: Path, origin_url: str, path: Path,
        ledger: dict[str, Any], approval: Mapping[str, Any],
    ) -> None:
        identity = ledger["identity"]
        candidate = str(approval["candidate_commit"])
        ref = f"refs/heads/{identity['task_branch']}"
        operation_id = semantic_sha256({
            "identity": identity, "approval": dict(approval), "phase": "branch_publish",
        })[:32]
        status, remote_before = self._observe_ref(checkout, origin_url, ref)
        if status == "unknown":
            raise PublicationError("remote task-branch state is unknown")
        published = self._events(ledger, "branch_published")
        last_published = published[-1]["payload"].get("remote_head") if published else None
        if remote_before != candidate:
            allowed = status == "absent" and last_published is None
            allowed = allowed or (status == "present" and remote_before == last_published)
            if not allowed:
                raise PublicationError(
                    f"remote task branch has an unrecorded head {remote_before!r}"
                )
            if not self._events(ledger, "branch_publish_prepared", candidate):
                self._append_event(
                    path, ledger, kind="branch_publish_prepared", approval=approval,
                    operation_id=operation_id,
                    payload={"ref": ref, "remote_before": remote_before},
                )
            lease = f"--force-with-lease={ref}:{remote_before or ''}"
            result = self._run(
                ("git", "-C", str(checkout), "push", "--atomic", "--porcelain",
                 lease, origin_url, f"{candidate}:{ref}"),
                cwd=checkout, label="exact candidate push", check=False,
                timeout_seconds=900.0,
            )
            after_status, remote_after = self._observe_ref(checkout, origin_url, ref)
            if after_status != "present" or remote_after != candidate:
                self._append_event(
                    path, ledger, kind="branch_publish_uncertain", approval=approval,
                    operation_id=operation_id,
                    payload={"returncode": result.returncode,
                             "observed_status": after_status,
                             "observed_head": remote_after},
                )
                raise PublicationError("exact candidate push outcome requires reconciliation")
        if not self._events(ledger, "branch_published", candidate):
            self._append_event(
                path, ledger, kind="branch_published", approval=approval,
                operation_id=operation_id,
                payload={"ref": ref, "remote_head": candidate},
            )

    def _list_prs(self, checkout: Path, identity: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = self._run(
            ("gh", "pr", "list", "--repo", identity["repository"],
             "--head", identity["task_branch"], "--state", "all", "--limit", "100", "--json",
             "number,url,state,headRefName,baseRefName,headRefOid,isDraft"),
            cwd=checkout, label="pull-request list",
        )
        values = _json(result.stdout, "pull-request list")
        if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
            raise PublicationError("pull-request list must be an array of objects")
        return values

    def _view_pr(self, checkout: Path, repository: str, number: int) -> dict[str, Any]:
        result = self._run(
            ("gh", "pr", "view", str(number), "--repo", repository, "--json",
             "number,url,state,headRefName,baseRefName,headRefOid,isDraft,statusCheckRollup"),
            cwd=checkout, label="pull-request view",
        )
        value = _json(result.stdout, "pull-request view")
        if not isinstance(value, dict):
            raise PublicationError("pull-request view must be an object")
        return value

    @staticmethod
    def _require_pr(
        value: Mapping[str, Any], identity: Mapping[str, Any], candidate: str,
        expected_number: int | None = None,
    ) -> dict[str, Any]:
        number = value.get("number")
        reasons = []
        if not isinstance(number, int) or number <= 0:
            reasons.append("invalid number")
        if expected_number is not None and number != expected_number:
            reasons.append("number changed")
        if str(value.get("state") or "").upper() != "OPEN":
            reasons.append("not open")
        if value.get("headRefName") != identity["task_branch"]:
            reasons.append("head branch differs")
        if value.get("baseRefName") != identity["base_branch"]:
            reasons.append("base branch differs")
        if value.get("headRefOid") != candidate:
            reasons.append("head commit differs")
        if reasons:
            raise PublicationError("pull-request identity mismatch: " + ", ".join(reasons))
        return dict(value)

    def _ensure_pr(
        self, *, checkout: Path, path: Path, ledger: dict[str, Any],
        approval: Mapping[str, Any],
    ) -> dict[str, Any]:
        identity = ledger["identity"]
        candidate = str(approval["candidate_commit"])
        operation_id = semantic_sha256({
            "identity": identity, "approval": dict(approval), "phase": "pr_create",
        })[:32]
        prior = self._events(ledger, "pr_open")
        prior_number = prior[-1]["payload"].get("number") if prior else None
        adoption = "adopted"
        if prior_number is not None:
            value = self._require_pr(
                self._view_pr(checkout, identity["repository"], int(prior_number)),
                identity, candidate, int(prior_number),
            )
        else:
            matches = self._list_prs(checkout, identity)
            if len(matches) > 1:
                raise PublicationError("multiple pull requests use the task branch")
            if matches:
                value = self._require_pr(matches[0], identity, candidate)
            else:
                if not self._events(ledger, "pr_create_prepared", candidate):
                    self._append_event(
                        path, ledger, kind="pr_create_prepared", approval=approval,
                        operation_id=operation_id,
                        payload={"head": identity["task_branch"],
                                 "base": identity["base_branch"]},
                    )
                created = self._run(
                    ("gh", "pr", "create", "--repo", identity["repository"],
                     "--base", identity["base_branch"], "--head", identity["task_branch"],
                     "--title", f"{identity['task_id']}: approved candidate",
                     "--body", "Exact human-approved AssistantControl candidate submitted for CI."),
                    cwd=checkout, label="pull-request create", check=False,
                )
                match = _PR_URL.search(_decode(created.stdout, "pull-request create").strip())
                if created.returncode == 0 and match is not None:
                    number = int(match.group("number"))
                    value = self._require_pr(
                        self._view_pr(checkout, identity["repository"], number),
                        identity, candidate, number,
                    )
                    adoption = "created"
                else:
                    recovered = self._list_prs(checkout, identity)
                    if len(recovered) != 1:
                        self._append_event(
                            path, ledger, kind="pr_create_uncertain", approval=approval,
                            operation_id=operation_id,
                            payload={"returncode": created.returncode,
                                     "observed_matches": len(recovered)},
                        )
                        raise PublicationError("pull-request creation requires reconciliation")
                    value = self._require_pr(recovered[0], identity, candidate)
                    adoption = "recovered"
        if not self._events(ledger, "pr_open", candidate):
            self._append_event(
                path, ledger, kind="pr_open", approval=approval,
                operation_id=operation_id,
                payload={"number": value["number"], "url": value.get("url"),
                         "head_ref_oid": candidate, "adoption": adoption},
            )
        return value

    @staticmethod
    def _result(path: Path, ledger: Mapping[str, Any], **values: Any) -> dict[str, Any]:
        receipt_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            **values,
            "receipt_path": str(path),
            "receipt_sha256": receipt_sha256,
            "event_count": len(ledger["events"]),
        }

    def publish_approved(
        self, task_id: str, *, candidate_commit: str,
        base_branch: str = "main", repository: str | None = None,
    ) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        candidate_commit = _sha(candidate_commit, "candidate_commit")
        gate = ReviewGate(self.checkouts)
        with gate.human_approved_candidate(task_id, tested_commit=candidate_commit) as record:
            bound, origin_url = self._binding(
                record, candidate_commit, base_branch, repository,
            )
            path, ledger = self._load_ledger(bound["identity"])
            checkout = Path(record["checkout"]).resolve()
            self._publish_branch(
                checkout=checkout, origin_url=origin_url, path=path,
                ledger=ledger, approval=bound["approval"],
            )
            pull_request = self._ensure_pr(
                checkout=checkout, path=path, ledger=ledger,
                approval=bound["approval"],
            )
            return self._result(
                path, ledger, status="pull_request_open", task_id=task_id,
                candidate_commit=candidate_commit,
                task_branch=bound["identity"]["task_branch"],
                repository=bound["identity"]["repository"],
                pull_request={key: pull_request.get(key) for key in
                              ("number", "url", "state", "headRefName",
                               "baseRefName", "headRefOid")},
            )

    def inspect_ci(
        self, task_id: str, *, candidate_commit: str,
        base_branch: str = "main", repository: str | None = None,
    ) -> dict[str, Any]:
        task_id = validate_task_id(task_id)
        candidate_commit = _sha(candidate_commit, "candidate_commit")
        gate = ReviewGate(self.checkouts)
        with gate.human_approved_candidate(task_id, tested_commit=candidate_commit) as record:
            bound, origin_url = self._binding(
                record, candidate_commit, base_branch, repository,
            )
            path, ledger = self._load_ledger(bound["identity"])
            approval = bound["approval"]
            checkout = Path(record["checkout"]).resolve()
            ref = f"refs/heads/{bound['identity']['task_branch']}"
            ref_status, remote_head = self._observe_ref(checkout, origin_url, ref)
            if ref_status != "present" or remote_head != candidate_commit:
                raise PublicationError("remote task branch is not the exact approved candidate")
            branch_events = self._events(ledger, "branch_published", candidate_commit)
            pr_events = self._events(ledger, "pr_open", candidate_commit)
            if not branch_events or not pr_events:
                raise PublicationError("candidate has no completed publication receipt")
            number = pr_events[-1]["payload"].get("number")
            if not isinstance(number, int):
                raise PublicationError("publication receipt omitted the pull-request number")
            pull_request = self._require_pr(
                self._view_pr(checkout, bound["identity"]["repository"], number),
                bound["identity"], candidate_commit, number,
            )
            rollup = pull_request.get("statusCheckRollup")
            checks = latest_effective_check_state(rollup)
            status = (
                "checks_failed" if checks["failed"] else
                "checks_pending" if checks["pending"] else
                "checks_passed"
            )
            operation_id = semantic_sha256({
                "identity": bound["identity"], "approval": approval,
                "phase": "ci_observation", "pull_request": number,
                "rollup": rollup,
            })[:32]
            self._append_event(
                path, ledger, kind="ci_observed", approval=approval,
                operation_id=operation_id,
                payload={
                    "status": status,
                    "pull_request_number": number,
                    "pull_request_url": pull_request.get("url"),
                    "observed_head_sha": candidate_commit,
                    "rollup_sha256": semantic_sha256(rollup),
                    "checks": checks,
                },
            )
            return self._result(
                path, ledger, status=status, task_id=task_id,
                candidate_commit=candidate_commit,
                pull_request_number=number, pull_request_url=pull_request.get("url"),
                checks=checks,
            )


__all__ = ["PublicationAdapter", "PublicationError", "SCHEMA_VERSION"]
