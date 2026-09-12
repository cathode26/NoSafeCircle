#!/usr/bin/env python3
"""Regression coverage for canonical NSC task IDs beyond three digits.

Classification: pure/component and temporary-repository behavior tests.
These tests exercise real pipeline entry points with deterministic fake providers
and disposable Git repositories. They never contact GitHub, Docker, Unity, or a
paid model provider, and they never mutate the source checkout.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Callable
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.contracts import (  # noqa: E402
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    Budgets,
    WriteBoundaries,
)
from Pipeline.AgentRuntime.providers.fake import FakeProvider  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import TASK_ID_RE as EXECUTION_CREW_TASK_ID_RE  # noqa: E402
from Pipeline.ExecutionCrew.tests import execution_crew_smoke_test as crew_smoke  # noqa: E402
from Pipeline.Supervisor import task_checkout as supervisor_task_checkout  # noqa: E402
from TaskDecomposition import contracts as decomposition_contracts  # noqa: E402
from TaskDecomposition import context_builder as decomposition_context  # noqa: E402
from TaskDecomposition.context_builder import (  # noqa: E402
    build_context,
    capture_clean_source,
)
from TaskDecomposition.live_decomposition import (  # noqa: E402
    run_live_decomposition,
)
from TaskDecomposition.policy import (  # noqa: E402
    semantic_json_sha256,
    validate_decomposition_result,
)
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.run_reviewer_replay_ab import (  # noqa: E402
    run_reviewer_replay_ab,
)
from TaskDecomposition.session_pool_support import (  # noqa: E402
    load_lease_bundle,
)
from TaskDecomposition.tests import reviewer_replay_smoke_test as replay_smoke  # noqa: E402
from TaskDecomposition.tests import round_robin_decomposition_smoke_test as round_smoke  # noqa: E402
from TaskDecomposition.tests.test_support import (  # noqa: E402
    create_repository,
    decomposed_result,
    fake_factory,
)
from Pipeline.TaskExecution.contracts import (  # noqa: E402
    TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
    TaskContractIdentity,
    TaskExecutionRequest,
)
from Pipeline.TaskExecution.contracts import _TASK_ID as TASK_EXECUTION_TASK_ID_RE  # noqa: E402
from Pipeline.TaskGraph.conformance_records import TASK_ID_RE as CONFORMANCE_TASK_ID_RE  # noqa: E402
from Pipeline.TaskGraph.token_usage_metrics import TASK_ID_RE as TOKEN_METRIC_TASK_ID_RE  # noqa: E402
from Pipeline.TaskGraph.token_usage_metrics import validate_token_usage_metric  # noqa: E402
from Pipeline.TaskGraph import work_graph_validate_smoke_test as work_graph_smoke  # noqa: E402
from Pipeline.TaskReviewAgent import autonomous_graph_run  # noqa: E402
from Pipeline.TaskReviewAgent import decomposition_policy_audit  # noqa: E402
from Pipeline.TaskReviewAgent import token_usage as task_review_token_usage  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TASK_ID_RE as TASK_REVIEW_TASK_ID_RE,
    TaskReviewRequest,
    validate_task_id,
)
from Pipeline.TaskReviewAgent.decomposition_policy_audit import (  # noqa: E402
    read_committed_tasks,
)
from Pipeline.TaskReviewAgent.decomposition_session_pool import (  # noqa: E402
    DecompositionSessionPoolOwner,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    LEGACY_PROFILE,
    POLICY_RELATIVE,
    build_bundle,
)
from Pipeline.TaskReviewAgent.reset_task import _committed_task_contracts  # noqa: E402
from Pipeline.TaskReviewAgent.reset_rehearsal_task import CommandRunner  # noqa: E402
from Pipeline.TaskReviewAgent.tests import automated_decomposition_event_smoke_test as event_smoke  # noqa: E402
from Pipeline.TaskReviewAgent.token_usage import build_task_token_usage  # noqa: E402
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    _TASK_ID_RE as WORKER_TASK_ID_RE,
    initialize_worker_run,
)
import graph_delta as graph_delta_module  # noqa: E402
import graph_delta_smoke_test as graph_delta_smoke  # noqa: E402
from decomposition_graph_semantics import (  # noqa: E402
    validate_decomposition_graph_semantics,
)
from graph_delta import GraphDeltaPlanningError, NSC_ID_RE, plan_graph_delta  # noqa: E402
from persistent_work_graph import load_persistent_work_graph  # noqa: E402
from work_graph_persist import persist_work_graph  # noqa: E402
from work_graph_transform import WorkGraphPlan, build_work_graph_plan  # noqa: E402
from work_graph_transform_smoke_test import make_inputs as make_bootstrap_inputs  # noqa: E402
from work_graph_validate import (  # noqa: E402
    WORK_ID_PATTERN,
    validate_work_graph_plan,
)


FOUR_DIGIT_TASK = "NSC-1000"
LAST_GAUNTLET_CHILD = "NSC-1006"
MAXIMUM_TASK_ID = "NSC-999999999"
EXAMPLE_REPOSITORY = "https://example.invalid/nosafecircle.git"
CANONICAL_TASK_ID_PATTERN = r"^NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})$"
CANONICAL_TASK_NUMBER_PATTERN = r"^NSC-([0-9]{3}|[1-9][0-9]{3,8})$"
CANONICAL_TASK_IDS = (
    "NSC-000",
    "NSC-001",
    "NSC-999",
    FOUR_DIGIT_TASK,
    MAXIMUM_TASK_ID,
)
NON_CANONICAL_TASK_IDS = (
    "NSC-99",
    "NSC-0000",
    "NSC-0001",
    "NSC-0123",
    "NSC-0999",
    "NSC-1000000000",
    "NSC-9999999999",
    "NSC-" + ("1" * 300),
    "NSC-١٠٠٠",
    "NSC-１０００",
    "NSC-+1000",
    "NSC--1000",
    "NSC- 1000",
    " NSC-1000",
    "NSC-1000 ",
    "NSC-1000\t",
    "NSC-1000\n",
    "nsc-1000",
    "NSC-1000x",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_rejected(label: str, operation: Callable[[], Any]) -> None:
    try:
        operation()
    except Exception:
        return
    raise AssertionError(f"{label} accepted a non-canonical task ID")


def _expect_rejected_at(
    label: str,
    operation: Callable[[], Any],
    expected_message: str,
) -> None:
    try:
        operation()
    except Exception as exc:
        require(
            expected_message.casefold() in str(exc).casefold(),
            f"{label} failed at the wrong boundary: {type(exc).__name__}: {exc}",
        )
        return
    raise AssertionError(f"{label} accepted a non-canonical task ID")


def test_active_python_patterns_use_one_bounded_ascii_contract() -> None:
    patterns = {
        "ExecutionCrew": (EXECUTION_CREW_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "Supervisor": (supervisor_task_checkout.TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "TaskDecomposition contracts": (
            decomposition_contracts.TASK_ID_RE,
            CANONICAL_TASK_ID_PATTERN,
        ),
        "TaskDecomposition context": (
            decomposition_context.TASK_ID_RE,
            CANONICAL_TASK_ID_PATTERN,
        ),
        "TaskExecution": (TASK_EXECUTION_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "TaskGraph conformance": (CONFORMANCE_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "TaskGraph delta": (NSC_ID_RE, CANONICAL_TASK_NUMBER_PATTERN),
        "TaskGraph token metrics": (TOKEN_METRIC_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "TaskGraph validation": (WORK_ID_PATTERN, CANONICAL_TASK_NUMBER_PATTERN),
        "TaskReview autonomous graph": (
            autonomous_graph_run._TASK_ID_RE,
            CANONICAL_TASK_ID_PATTERN,
        ),
        "TaskReview contracts": (TASK_REVIEW_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
        "TaskReview policy audit": (
            decomposition_policy_audit._TASK_ID,
            CANONICAL_TASK_ID_PATTERN,
        ),
        "TaskReview token usage": (
            task_review_token_usage._TASK_ID_RE,
            CANONICAL_TASK_ID_PATTERN,
        ),
        "TaskReview worker result": (WORKER_TASK_ID_RE, CANONICAL_TASK_ID_PATTERN),
    }
    failures: list[str] = []
    for label, (pattern, expected_source) in patterns.items():
        if pattern.pattern != expected_source:
            failures.append(
                f"{label}: pattern is {pattern.pattern!r}, expected {expected_source!r}"
            )
        for task_id in CANONICAL_TASK_IDS:
            if pattern.fullmatch(task_id) is None:
                failures.append(f"{label}: rejected canonical {task_id!r}")
        for task_id in NON_CANONICAL_TASK_IDS:
            if pattern.fullmatch(task_id) is not None:
                failures.append(f"{label}: accepted non-canonical {task_id!r}")
    require(not failures, "task ID pattern drift:\n" + "\n".join(failures))


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def temporary_directory(prefix: str) -> tempfile.TemporaryDirectory[str]:
    """Create a disposable fixture outside the production source checkout."""

    return tempfile.TemporaryDirectory(prefix=prefix)


def _invocation() -> AgentInvocationRequest:
    return AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        "four-digit-task-execution",
        "implementer",
        "Exercise the canonical four-digit task identity boundary.",
        ("Pipeline/TaskExecution",),
        ("repository_read",),
        WriteBoundaries((), ()),
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        "standard",
        Budgets(1, 1),
        "fake-default",
    )


def test_task_review_contract_accepts_four_digits() -> None:
    for task_id in CANONICAL_TASK_IDS:
        require(validate_task_id(task_id) == task_id, f"central task ID changed: {task_id}")
    require(
        TaskReviewRequest(LAST_GAUNTLET_CHILD).task_id == LAST_GAUNTLET_CHILD,
        "review request rejected four digits",
    )

    for malformed in NON_CANONICAL_TASK_IDS:
        _expect_rejected(
            f"central task review contract ({malformed!r})",
            lambda malformed=malformed: validate_task_id(malformed),
        )


def test_supervisor_rejects_aliases_instead_of_normalizing_them() -> None:
    for task_id in CANONICAL_TASK_IDS:
        require(
            supervisor_task_checkout._validate_task_id(task_id) == task_id,
            f"Supervisor changed canonical task ID {task_id!r}",
        )
    for malformed in NON_CANONICAL_TASK_IDS:
        _expect_rejected(
            f"Supervisor task checkout ({malformed!r})",
            lambda malformed=malformed: supervisor_task_checkout._validate_task_id(malformed),
        )


def test_decomposition_contract_and_context_reject_noncanonical_ids() -> None:
    for task_id in CANONICAL_TASK_IDS:
        identity = decomposition_contracts.ParentTaskIdentity.from_dict(
            {
                "task_id": task_id,
                "contract_revision": 1,
                "contract_sha256": "a" * 64,
            }
        )
        require(identity.task_id == task_id, f"decomposition identity changed {task_id!r}")
        require(
            decomposition_context._task_number({"id": task_id}) == int(task_id[4:]),
            f"context ordering changed {task_id!r}",
        )
    for malformed in NON_CANONICAL_TASK_IDS:
        _expect_rejected(
            f"decomposition parent identity ({malformed!r})",
            lambda malformed=malformed: decomposition_contracts.ParentTaskIdentity.from_dict(
                {
                    "task_id": malformed,
                    "contract_revision": 1,
                    "contract_sha256": "a" * 64,
                }
            ),
        )
        _expect_rejected(
            f"decomposition context ordering ({malformed!r})",
            lambda malformed=malformed: decomposition_context._task_number({"id": malformed}),
        )


def test_work_graph_rejects_each_noncanonical_identity_field_in_isolation() -> None:
    base = work_graph_smoke.make_plan()

    for malformed in NON_CANONICAL_TASK_IDS:
        tasks = list(deepcopy(base.tasks))
        tasks[2]["id"] = malformed
        _expect_rejected_at(
            f"work graph task ID ({malformed!r})",
            lambda tasks=tasks: validate_work_graph_plan(
                WorkGraphPlan(
                    deepcopy(base.id_map),
                    tuple(tasks),
                    deepcopy(base.resource_groups),
                    base.project_requirements,
                )
            ),
            "tasks[2].id must be a canonical NSC task ID",
        )

    alias = " NSC-010 "
    cases: tuple[tuple[str, Callable[..., Any], str], ...] = (
        (
            "parent",
            lambda tasks, _id_map, _groups: tasks[2].__setitem__("parent", " NSC-002 "),
            "NSC-010.parent must be a canonical NSC task ID",
        ),
        (
            "depends_on",
            lambda tasks, _id_map, _groups: tasks[3].__setitem__("depends_on", [alias]),
            "NSC-020.depends_on entry must be a canonical NSC task ID",
        ),
        (
            "superseded_by",
            lambda tasks, _id_map, _groups: (
                tasks[3].__setitem__("contract_disposition", "superseded"),
                tasks[3].__setitem__("superseded_by", alias),
            ),
            "NSC-020.superseded_by must be a canonical NSC task ID",
        ),
        (
            "resource group work_id",
            lambda _tasks, _id_map, groups: groups[0]["work_ids"].__setitem__(0, alias),
            "resource group repo-file:Input.inputactions.work_id must be a canonical NSC task ID",
        ),
        (
            "ID map work_id",
            lambda _tasks, id_map, _groups: id_map.__setitem__("player-movement", alias),
            "ID map mismatch for player-movement",
        ),
    )
    for label, mutate, expected_message in cases:
        tasks = list(deepcopy(base.tasks))
        id_map = deepcopy(base.id_map)
        resource_groups = list(deepcopy(base.resource_groups))
        mutate(tasks, id_map, resource_groups)
        _expect_rejected_at(
            label,
            lambda tasks=tasks, id_map=id_map, resource_groups=resource_groups: validate_work_graph_plan(
                WorkGraphPlan(
                    id_map,
                    tuple(tasks),
                    tuple(resource_groups),
                    base.project_requirements,
                )
            ),
            expected_message,
        )


def test_persistent_work_graph_rejects_raw_id_map_alias_before_normalization() -> None:
    with temporary_directory("nsc-task-id-map-alias-") as text:
        root = Path(text)
        inputs = make_bootstrap_inputs()
        persist_work_graph(build_work_graph_plan(inputs), inputs, root=root)
        path = root / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["id_map"]["player-movement"] = " NSC-003 "
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _expect_rejected_at(
            "persistent WORK_ID_MAP raw work_id alias",
            lambda: load_persistent_work_graph(root),
            "WORK_ID_MAP.json contains a non-canonical work ID alias",
        )


def test_decomposition_semantics_rejects_raw_parent_provenance_alias() -> None:
    source = graph_delta_smoke.make_plan()
    result = graph_delta_smoke.validated_result(source)
    overlay = plan_graph_delta(source, result.parent_task, result).proposed_graph_overlay
    child = next(
        task
        for task in overlay["tasks"]
        if task.get("provenance", {}).get("graph_delta_plan_id")
    )
    child["provenance"]["parent_task_id"] = " NSC-042 "
    aliased = WorkGraphPlan(
        overlay["id_map"],
        tuple(overlay["tasks"]),
        tuple(overlay["resource_groups"]),
        tuple(overlay["project_requirements"]),
    )
    _expect_rejected_at(
        "decomposition provenance.parent_task_id alias",
        lambda: validate_decomposition_graph_semantics(aliased),
        "provenance.parent_task_id must be an exact canonical NSC task ID",
    )


def test_decomposition_contract_task_id_fields_reject_aliases_directly() -> None:
    source = graph_delta_smoke.make_plan()
    parent = next(task for task in source.tasks if task["id"] == "NSC-042")
    child = graph_delta_smoke.decomposed_result(parent)["children"][0]
    child["existing_task_dependencies"] = [MAXIMUM_TASK_ID]
    parsed_child = decomposition_contracts.ChildProposal.from_dict(child, "child")
    require(
        parsed_child.existing_task_dependencies == (MAXIMUM_TASK_ID,),
        "ChildProposal changed the maximum canonical dependency ID",
    )
    child["existing_task_dependencies"] = [f" {MAXIMUM_TASK_ID} "]
    _expect_rejected_at(
        "ChildProposal.existing_task_dependencies alias",
        lambda: decomposition_contracts.ChildProposal.from_dict(child, "child"),
        "existing_task_dependencies contains invalid task ID",
    )

    rewrite = {
        "dependent_task_id": MAXIMUM_TASK_ID,
        "replacement_local_keys": ["bounded-child"],
        "reason": "Replace the aggregate dependency with its bounded child.",
    }
    parsed_rewrite = decomposition_contracts.InboundDependencyRewrite.from_dict(
        rewrite, "rewrite"
    )
    require(
        parsed_rewrite.dependent_task_id == MAXIMUM_TASK_ID,
        "InboundDependencyRewrite changed the maximum canonical dependent ID",
    )
    rewrite["dependent_task_id"] = f" {MAXIMUM_TASK_ID} "
    _expect_rejected_at(
        "InboundDependencyRewrite.dependent_task_id alias",
        lambda: decomposition_contracts.InboundDependencyRewrite.from_dict(
            rewrite, "rewrite"
        ),
        "dependent_task_id has invalid NSC identity",
    )


def test_task_execution_contract_accepts_four_digits() -> None:
    for task_id in CANONICAL_TASK_IDS:
        request = TaskExecutionRequest(
            TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
            task_id,
            TaskContractIdentity(f"Tasks/{task_id}.yaml", 1, "a" * 64),
            _invocation(),
        )
        require(
            TaskExecutionRequest.from_dict(request.to_dict()) == request,
            f"TaskExecution round trip changed {task_id!r}",
        )
    for malformed in NON_CANONICAL_TASK_IDS:
        _expect_rejected(
            f"TaskExecution ({malformed!r})",
            lambda malformed=malformed: TaskExecutionRequest(
                TASK_EXECUTION_REQUEST_SCHEMA_VERSION,
                malformed,
                TaskContractIdentity(f"Tasks/{malformed}.yaml", 1, "a" * 64),
                _invocation(),
            ),
        )


def test_worker_result_accepts_four_digits() -> None:
    with temporary_directory("nsc-task-id-metrics-") as text:
        base = Path(text)
        for index, task_id in enumerate(CANONICAL_TASK_IDS):
            run_id = f"bounded-worker-{index}"
            run_dir = initialize_worker_run(
                output_root=base / "worker-output",
                task_id=task_id,
                run_id=run_id,
                worker_id="worker-1",
                started_at_utc="2026-09-05T12:00:00Z",
            )
            require(run_dir.name == run_id, "worker run directory changed")
            require(run_dir.parent.name == task_id, "worker task directory was truncated")
        for index, malformed in enumerate(NON_CANONICAL_TASK_IDS):
            # Avoid asking Windows to materialize the deliberate 304-character ID
            # if a regression accepts it; the pattern sentinel covers that case.
            if len(malformed) > 100:
                continue
            _expect_rejected(
                f"worker result ({malformed!r})",
                lambda malformed=malformed, index=index: initialize_worker_run(
                    output_root=base / "invalid-worker-output",
                    task_id=malformed,
                    run_id=f"invalid-worker-{index}",
                    worker_id="worker-1",
                    started_at_utc="2026-09-05T12:00:00Z",
                ),
            )


def test_task_review_token_usage_accepts_four_digits() -> None:
    with temporary_directory("nsc-task-id-review-metrics-") as text:
        base = Path(text)
        for task_id in CANONICAL_TASK_IDS:
            metric = build_task_token_usage(
                task_id=task_id,
                supervisor_output_root=base / "supervisor-output",
                checkout_root=base / "checkouts",
            )
            require(metric["task_id"] == task_id, "task usage producer changed the task ID")
        for malformed in NON_CANONICAL_TASK_IDS:
            _expect_rejected(
                f"task review token usage ({malformed!r})",
                lambda malformed=malformed: build_task_token_usage(
                    task_id=malformed,
                    supervisor_output_root=base / "supervisor-output",
                    checkout_root=base / "checkouts",
                ),
            )


def test_taskgraph_token_usage_metric_accepts_four_digits() -> None:
    with temporary_directory("nsc-task-id-graph-metrics-") as text:
        base = Path(text)
        metric = build_task_token_usage(
            task_id="NSC-999",
            supervisor_output_root=base / "supervisor-output",
            checkout_root=base / "checkouts",
        )
        for task_id in CANONICAL_TASK_IDS:
            candidate = deepcopy(metric)
            candidate["task_id"] = task_id
            validated = validate_token_usage_metric(candidate, expected_task_id=task_id)
            require(validated["task_id"] == task_id, "TaskGraph metric task ID changed")
        for malformed in NON_CANONICAL_TASK_IDS:
            candidate = deepcopy(metric)
            candidate["task_id"] = malformed
            _expect_rejected(
                f"TaskGraph token metric ({malformed!r})",
                lambda candidate=candidate, malformed=malformed: validate_token_usage_metric(
                    candidate, expected_task_id=malformed
                ),
            )


def _powershell_launcher_result(
    relative_path: str, arguments: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    missing = ROOT / ".task-id-width-intentionally-missing"
    require(not missing.exists(), "launcher missing-path fixture unexpectedly exists")
    launcher = ROOT / relative_path
    return subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(launcher),
            *arguments,
            "-Source",
            str(missing),
        ),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _assert_powershell_launcher_binds(
    relative_path: str,
    arguments: tuple[str, ...],
    *,
    parameter: str,
) -> None:
    completed = _powershell_launcher_result(relative_path, arguments)
    combined = completed.stdout + completed.stderr
    normalized = " ".join(combined.split())
    require(completed.returncode != 0, f"missing source unexpectedly launched: {relative_path}")
    require(
        f"Cannot validate argument on parameter '{parameter}'" not in normalized
        and "does not match the" not in normalized,
        f"{relative_path} rejected a canonical task during parameter binding: {combined}",
    )


def _assert_powershell_launcher_rejects(
    relative_path: str,
    arguments: tuple[str, ...],
    *,
    parameter: str,
) -> None:
    completed = _powershell_launcher_result(relative_path, arguments)
    combined = completed.stdout + completed.stderr
    normalized = " ".join(combined.split())
    require(completed.returncode != 0, f"invalid task unexpectedly launched: {relative_path}")
    require(
        f"Cannot validate argument on parameter '{parameter}'" in normalized
        and "does not match the" in normalized,
        f"{relative_path} did not reject the invalid {parameter} during binding: {combined}",
    )


def test_task_agent_launchers_enforce_bounded_ids() -> None:
    launchers = (
        (
            "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1",
            "TaskId",
            lambda task_id: ("-TaskId", task_id, "-Mode", "observe"),
        ),
        (
            "Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1",
            "TaskId",
            lambda task_id: ("-TaskId", task_id, "-Mode", "scripted"),
        ),
    )
    for relative_path, parameter, arguments in launchers:
        for task_id in (FOUR_DIGIT_TASK, MAXIMUM_TASK_ID):
            _assert_powershell_launcher_binds(
                relative_path, arguments(task_id), parameter=parameter
            )
        for malformed in (
            "NSC-0000",
            "NSC-0001",
            "NSC-1000000000",
            "NSC-١٠٠٠",
            "NSC-+1000",
            " NSC-1000",
            "NSC-1000 ",
            "nsc-1000",
        ):
            _assert_powershell_launcher_rejects(
                relative_path, arguments(malformed), parameter=parameter
            )


def test_autonomous_graph_launcher_enforces_bounded_target_and_exclusion_ids() -> None:
    relative_path = "Pipeline/TaskReviewAgent/Start-AutonomousGraphRun.ps1"
    common = ("-RunId", "bounded-id-test", "-ConfirmRepository", "example/repository")
    for parameter in ("TargetTaskId", "ExcludeTaskId"):
        switch = f"-{parameter}"
        for task_id in (FOUR_DIGIT_TASK, MAXIMUM_TASK_ID):
            _assert_powershell_launcher_binds(
                relative_path,
                (*common, switch, task_id),
                parameter=parameter,
            )
        for malformed in (
            "NSC-0000",
            "NSC-0001",
            "NSC-1000000000",
            "NSC-١٠٠٠",
            "NSC-+1000",
            " NSC-1000",
            "NSC-1000 ",
            "nsc-1000",
        ):
            _assert_powershell_launcher_rejects(
                relative_path,
                (*common, switch, malformed),
                parameter=parameter,
            )


def _four_digit_decomposition_repository(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    tasks = create_repository(root)
    parent = deepcopy(tasks[FOUR_DIGIT_TASK])
    parent["execution_scope"] = "needs_execution_decomposition"
    parent["execution_reason"] = "Four-digit decomposition boundary fixture."
    (root / f"Tasks/{FOUR_DIGIT_TASK}.yaml").write_text(
        json.dumps(parent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    git(root, "add", f"Tasks/{FOUR_DIGIT_TASK}.yaml")
    git(root, "commit", "-m", "make four-digit task decomposable")
    tasks[FOUR_DIGIT_TASK] = parent
    validate_work_graph_plan(
        WorkGraphPlan(
            id_map={task["reconciliation_key"]: task["id"] for task in tasks.values()},
            tasks=tuple(tasks.values()),
            resource_groups=(
                {
                    "resource_key": "repo-file:Assets/Shared.cs",
                    "work_ids": ["NSC-003", "NSC-010"],
                    "reconciliation_keys": ["dependency-runtime", "selected-parent"],
                },
            ),
            project_requirements=(
                {
                    "title": "Human review",
                    "requirement_type": "pipeline_constraint",
                    "status": "confirmed",
                },
            ),
        )
    )
    return tasks, parent


def _four_digit_decomposition_result(parent: dict[str, Any]) -> dict[str, Any]:
    result = decomposed_result(parent)
    result["children"][0]["existing_task_dependencies"] = []
    result["children"][0]["exclusive_resources"] = []
    result["inbound_dependency_rewrites"] = []
    return result


def test_decomposition_entrypoints_reject_noncanonical_ids_before_source_access() -> None:
    missing = ROOT / ".task-id-width-missing-decomposition-source"
    require(not missing.exists(), "decomposition missing-path fixture unexpectedly exists")
    invocations: tuple[tuple[str, Callable[[str], Any]], ...] = (
        (
            "live decomposition",
            lambda task_id: run_live_decomposition(
                source=missing,
                output_root=missing / "live-output",
                task_id=task_id,
                provider_name="codex",
            ),
        ),
        (
            "round-robin decomposition",
            lambda task_id: run_round_robin_decomposition(
                source=missing,
                output_root=missing / "round-output",
                task_id=task_id,
                provider_order=("codex", "claude"),
            ),
        ),
        (
            "reviewer replay",
            lambda task_id: run_reviewer_replay_ab(
                source=missing,
                output_root=missing / "replay-output",
                task_id=task_id,
                candidate_path=missing / "candidate.json",
                expected_candidate_sha256="a" * 64,
            ),
        ),
    )
    for label, invocation in invocations:
        for malformed in (
            "NSC-0000",
            "NSC-0001",
            "NSC-1000000000",
            "NSC-١٠٠٠",
            "NSC-" + ("1" * 300),
        ):
            try:
                invocation(malformed)
            except Exception as exc:
                require(
                    "task id" in str(exc).casefold(),
                    f"{label} reached another boundary before rejecting {malformed!r}: {exc}",
                )
            else:
                raise AssertionError(f"{label} accepted {malformed!r}")


def test_decomposition_context_selects_four_digits() -> None:
    with temporary_directory("nsc-four-digit-context-") as text:
        source = Path(text) / "source"
        _four_digit_decomposition_repository(source)
        context, _ = build_context(capture_clean_source(source), FOUR_DIGIT_TASK)
        require(context.to_dict()["selected_task"]["contract"]["id"] == FOUR_DIGIT_TASK, "wrong context task")


def test_live_decomposition_accepts_four_digits() -> None:
    with temporary_directory("nsc-four-digit-live-") as text:
        base = Path(text)
        source = base / "source"
        _, parent = _four_digit_decomposition_repository(source)
        result = run_live_decomposition(
            source=source,
            output_root=base / "output",
            task_id=FOUR_DIGIT_TASK,
            provider_name="codex",
            run_id="four-digit-live",
            provider_factory=fake_factory(FakeProvider(structured_output=_four_digit_decomposition_result(parent))),
            _require_physical_read_only_source=False,
        )
        require(result["task_id"] == FOUR_DIGIT_TASK, "live decomposition task ID changed")
        require(result["run_status"] == "review_ready", str(result))


def test_round_robin_decomposition_accepts_four_digits() -> None:
    with temporary_directory("nsc-four-digit-round-robin-") as text:
        base = Path(text)
        source = base / "source"
        tasks, parent = _four_digit_decomposition_repository(source)
        raw = _four_digit_decomposition_result(parent)
        candidate = validate_decomposition_result(
            raw,
            parent_task=parent,
            existing_reconciliation_keys=(task["reconciliation_key"] for task in tasks.values()),
        )
        providers = {
            "codex": round_smoke.QueueProvider([raw]),
            "claude": round_smoke.QueueProvider([round_smoke.pass_review(candidate_sha256(candidate))]),
        }
        result = run_round_robin_decomposition(
            source=source,
            output_root=base / "output",
            task_id=FOUR_DIGIT_TASK,
            provider_order=("codex", "claude"),
            max_calls=2,
            run_id="four-digit-round-robin",
            provider_factory=round_smoke.provider_factory(providers),
            _require_physical_read_only_source=False,
        )
        require(result["task_id"] == FOUR_DIGIT_TASK, "round-robin task ID changed")
        require(result["run_status"] == "review_ready", str(result))


def test_reviewer_replay_accepts_four_digits() -> None:
    with temporary_directory("nsc-four-digit-replay-") as text:
        base = Path(text)
        source = base / "source"
        tasks, parent = _four_digit_decomposition_repository(source)
        raw = _four_digit_decomposition_result(parent)
        candidate = validate_decomposition_result(
            raw,
            parent_task=parent,
            existing_reconciliation_keys=(task["reconciliation_key"] for task in tasks.values()),
        )
        expected_hash = candidate_sha256(candidate)
        candidate_path = base / "candidate.json"
        candidate_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        provider = replay_smoke.QueueProvider(
            [replay_smoke.pass_review(expected_hash), replay_smoke.pass_review(expected_hash)]
        )
        result = run_reviewer_replay_ab(
            source=source,
            output_root=base / "output",
            task_id=FOUR_DIGIT_TASK,
            candidate_path=candidate_path,
            expected_candidate_sha256=expected_hash,
            candidate_author_provider="codex",
            reviewer_provider="claude",
            arm_order=("full", "rag"),
            run_id="four-digit-replay",
            provider_factory=replay_smoke.provider_factory(provider),
            retriever=replay_smoke.FakeRetriever(),
            _require_physical_read_only_source=False,
        )
        require(result["task_id"] == FOUR_DIGIT_TASK, "reviewer replay task ID changed")
        require(result["run_status"] == "comparison_ready", str(result))


def test_decomposition_session_bundle_accepts_four_digits() -> None:
    with temporary_directory("nsc-four-digit-session-") as text:
        base = Path(text)
        source = base / "checkouts" / "NSC-999"
        source.parent.mkdir(parents=True)
        create_repository(source)
        git(source, "remote", "add", "origin", EXAMPLE_REPOSITORY)
        manifest = source.parent / ".task-review-agent" / "NSC-999.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"schema_version": "2", "task_id": "NSC-999"}) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        owner = DecompositionSessionPoolOwner(
            checkout=source,
            repository_identity=EXAMPLE_REPOSITORY,
            provider_models={"claude": ("fake-model", None), "codex": ("fake-model", "high")},
            codex_resume_activation=None,
            compose_project="four-digit-session",
            host_identity="test-host",
        )
        try:
            assignment = owner.prepare(
                run_id="four-digit-session",
                task_id="NSC-999",
                decomposition_mode="round_robin_d1b2",
                provider_order=("claude", "codex"),
                max_calls=2,
                source_commit=git(source, "rev-parse", "HEAD"),
                worker_id="worker-1",
            )
            bundle_path = Path(assignment["lease_bundle_path"])
            four_digit_path = bundle_path.with_name("four-digit-leases.json")
            four_digit_path.write_text(
                bundle_path.read_text(encoding="utf-8").replace("NSC-999", FOUR_DIGIT_TASK),
                encoding="utf-8",
                newline="\n",
            )
            bundle = load_lease_bundle(
                four_digit_path, run_id="four-digit-session"
            )
            require(bundle.task_id == FOUR_DIGIT_TASK, "lease bundle task ID changed")
            for index, malformed in enumerate(
                (
                    "NSC-0000",
                    "NSC-0001",
                    "NSC-1000000000",
                    "NSC-١٠٠٠",
                    "NSC-" + ("1" * 300),
                )
            ):
                invalid_path = bundle_path.with_name(f"invalid-leases-{index}.json")
                invalid_path.write_text(
                    bundle_path.read_text(encoding="utf-8").replace("NSC-999", malformed),
                    encoding="utf-8",
                    newline="\n",
                )
                _expect_rejected(
                    f"decomposition lease bundle ({malformed!r})",
                    lambda invalid_path=invalid_path: load_lease_bundle(
                        invalid_path, run_id="four-digit-session"
                    ),
                )
        finally:
            owner.close()


def _commit_discovery_boundary_contracts(source: Path) -> tuple[str, ...]:
    noncanonical = (
        "NSC-0000",
        "NSC-0001",
        "NSC-1000000000",
        "NSC-١٠٠٠",
        "NSC-１０００",
    )
    for task_id in (MAXIMUM_TASK_ID, *noncanonical):
        (source / f"Tasks/{task_id}.yaml").write_text(
            json.dumps({"id": task_id}, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    git(source, "add", "Tasks")
    git(source, "commit", "-m", "add task ID discovery boundaries")
    return noncanonical


def test_policy_audit_discovery_enforces_bounded_ids() -> None:
    with temporary_directory("nsc-four-digit-policy-discovery-") as text:
        source = Path(text) / "source"
        create_repository(source)
        noncanonical = _commit_discovery_boundary_contracts(source)
        for audited in (
            read_committed_tasks(source),
            read_committed_tasks(source, commit=git(source, "rev-parse", "HEAD")),
        ):
            require(FOUR_DIGIT_TASK in audited, "policy audit skipped a four-digit contract")
            require(MAXIMUM_TASK_ID in audited, "policy audit skipped the maximum task ID")
            for malformed in noncanonical:
                require(
                    malformed not in audited,
                    f"policy audit discovered non-canonical contract {malformed!r}",
                )


def test_reset_and_undo_discovery_enforce_bounded_ids() -> None:
    with temporary_directory("nsc-four-digit-reset-discovery-") as text:
        source = Path(text) / "source"
        create_repository(source)
        noncanonical = _commit_discovery_boundary_contracts(source)
        reset_contracts = _committed_task_contracts(CommandRunner(), source)
        require(FOUR_DIGIT_TASK in reset_contracts, "reset/undo discovery skipped a four-digit contract")
        require(MAXIMUM_TASK_ID in reset_contracts, "reset/undo discovery skipped the maximum task ID")
        for malformed in noncanonical:
            require(
                malformed not in reset_contracts,
                f"reset/undo discovered non-canonical contract {malformed!r}",
            )


def test_automated_decomposition_approval_accepts_999_and_1000() -> None:
    service, _, evidence = event_smoke.waiting_service()
    evidence["children"][0]["task_id"] = FOUR_DIGIT_TASK
    evidence["children"][1]["task_id"] = "NSC-999"
    result = service.apply_automated_decomposition_result(
        task_id=event_smoke.TASK_ID,
        evidence=evidence,
        actor_id=event_smoke.WORKER_ID,
        now="2026-09-05T12:00:00Z",
    )
    require(result["decision"] == "approve", str(result))


def test_automated_decomposition_approval_rejects_noncanonical_children() -> None:
    for malformed in (
        "NSC-0000",
        "NSC-0001",
        "NSC-1000000000",
        "NSC-١٠٠٠",
    ):
        service, _, evidence = event_smoke.waiting_service()
        evidence["children"][0]["task_id"] = malformed
        try:
            result = service.apply_automated_decomposition_result(
                task_id=event_smoke.TASK_ID,
                evidence=evidence,
                actor_id=event_smoke.WORKER_ID,
                now="2026-09-05T12:00:00Z",
            )
        except Exception:
            continue
        require(
            result.get("decision") != "approve",
            f"automated decomposition approval accepted {malformed!r}: {result}",
        )


def test_execution_crew_accepts_four_digits() -> None:
    original_task = crew_smoke.TASK
    crew_smoke.TASK = FOUR_DIGIT_TASK
    try:
        with temporary_directory("nsc-four-digit-crew-") as text:
            base = Path(text)
            source = crew_smoke.fixture(base)
            result, _, _ = crew_smoke.execute(
                source,
                base / "output",
                "pass",
                1000,
                crew_profile="lean",
                validation_profile="targeted",
            )
            require(result["task_id"] == FOUR_DIGIT_TASK, "ExecutionCrew task ID changed")
            require(result["crew_status"] == "review_ready", str(result))
    finally:
        crew_smoke.TASK = original_task


_ISOLATED_GAUNTLET_SOURCE: list[tuple[Any, Path]] = []


def _isolated_gauntlet_source() -> Path:
    """Graph inputs with the synthetic range removed.

    The checkout now carries committed NSC-911..NSC-990 contracts, so generating
    the bundle against ROOT collides with real repository state. Build the
    fixture these tests need instead of depending on what the checkout holds.
    """
    if _ISOLATED_GAUNTLET_SOURCE:
        return _ISOLATED_GAUNTLET_SOURCE[0][1]

    def _synthetic(task_id: Any) -> bool:
        return (
            isinstance(task_id, str)
            and task_id.startswith("NSC-")
            and task_id[4:].isdigit()
            and int(task_id[4:]) >= LEGACY_PROFILE.first_id
        )

    handle = temporary_directory("task-id-width-gauntlet-")
    source = Path(handle.name)
    tasks = source / "Tasks"
    tasks.mkdir(parents=True)
    for path in sorted((ROOT / "Tasks").glob("NSC-*.yaml")):
        if _synthetic(path.stem):
            continue
        contract = json.loads(path.read_text(encoding="utf-8"))
        # Preserved contracts were rewired into the synthetic range; drop
        # those references so the pruned graph still validates.
        for field in ("depends_on", "decomposition_children"):
            values = contract.get(field)
            if isinstance(values, list):
                contract[field] = [item for item in values if not _synthetic(item)]
        (tasks / path.name).write_text(json.dumps(contract, indent=2), encoding="utf-8")

    taskgraph = source / "Pipeline" / "TaskGraph"
    taskgraph.mkdir(parents=True)
    for name in ("BOOTSTRAP_PERSISTED.json", "PROJECT_REQUIREMENTS.yaml", "RESOURCE_GROUPS.yaml"):
        (taskgraph / name).write_bytes((TASK_GRAPH_ROOT / name).read_bytes())

    id_map_payload = json.loads((TASK_GRAPH_ROOT / "WORK_ID_MAP.json").read_text(encoding="utf-8"))
    id_map_payload["id_map"] = {
        key: value
        for key, value in id_map_payload["id_map"].items()
        if not _synthetic(value)
    }
    (taskgraph / "WORK_ID_MAP.json").write_text(
        json.dumps(id_map_payload, indent=2), encoding="utf-8"
    )

    policy = source / POLICY_RELATIVE
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_bytes((ROOT / POLICY_RELATIVE).read_bytes())
    _ISOLATED_GAUNTLET_SOURCE.append((handle, source))
    return source


def _gauntlet_plan() -> WorkGraphPlan:
    bundle, summary = build_bundle(_isolated_gauntlet_source())
    require(summary["initial_synthetic_tasks"] == 80, str(summary))
    task_paths = sorted(
        path for path in bundle if path.parts and path.parts[0] == "Tasks"
    )
    tasks = tuple(json.loads(bundle[path].decode("utf-8")) for path in task_paths)
    id_map = json.loads(
        bundle[Path("Pipeline/TaskGraph/WORK_ID_MAP.json")].decode("utf-8")
    )["id_map"]
    resource_groups = json.loads(
        bundle[Path("Pipeline/TaskGraph/RESOURCE_GROUPS.yaml")].decode("utf-8")
    )["resource_groups"]
    requirements = json.loads(
        bundle[Path("Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml")].decode("utf-8")
    )["requirements"]
    plan = WorkGraphPlan(id_map, tasks, tuple(resource_groups), tuple(requirements))
    validate_work_graph_plan(plan)
    return plan


def _gauntlet_result(plan: WorkGraphPlan, parent: dict[str, Any]) -> Any:
    number = int(parent["id"].split("-", 1)[1])
    local_keys = (f"muffcabbage-{number}-alpha", f"muffcabbage-{number}-beta")
    resources = list(parent["exclusive_resources"])
    children = []
    for index, suffix in enumerate(("Alpha", "Beta")):
        children.append(
            {
                "local_key": local_keys[index],
                "title": f"Muffcabbage Gauntlet {number} {suffix} Value",
                "kind": "implementation",
                "type": "engineering-validation",
                "execution_scope": "single_agent",
                "execution_reason": f"Own the exact {suffix} source and meta pair.",
                "decomposition_state": "concrete",
                "decomposition_reason": "The committed parent specifies the exact file and value.",
                "existing_task_dependencies": list(parent["depends_on"]),
                "local_dependencies": [],
                "exclusive_resources": resources[index * 2 : index * 2 + 2],
                "acceptance_criteria": [
                    {
                        "criterion_id": "AC-001",
                        "reference": f"Parent AC-00{index + 1}",
                        "requirement": parent["acceptance_criteria"][index]["requirement"],
                    }
                ],
                "completion_gates": [
                    {
                        "gate_id": "VAL-001",
                        "reference": f"Parent VAL-00{index + 1}",
                        "requirement": parent["completion_gates"][index]["requirement"],
                    }
                ],
                "downstream_integration_obligations": [],
                "gdd_evidence": [],
                "basis": parent["basis"],
                "source_scope": parent["source_scope"],
                "confidence": parent["confidence"],
                "notes": "",
            }
        )
    coverage = []
    for entry_type, prefix, child_entry_type in (
        ("acceptance_criteria", "AC", "acceptance_criteria"),
        ("completion_gates", "VAL", "completion_gates"),
    ):
        for index in range(2):
            coverage.append(
                {
                    "parent_entry_type": entry_type,
                    "parent_entry_id": f"{prefix}-{index + 1:03d}",
                    "disposition": "assigned_to_child",
                    "child_targets": [
                        {
                            "local_key": local_keys[index],
                            "child_entry_type": child_entry_type,
                            "child_entry_id": f"{prefix}-001",
                        }
                    ],
                    "reason": f"The {index + 1} child owns the exact parent entry.",
                    "integration_rationale": "",
                }
            )
    active_dependents = [
        task
        for task in plan.tasks
        if task.get("contract_disposition") == "active"
        and parent["id"] in task.get("depends_on", [])
    ]
    raw = {
        "schema_version": "1.1",
        "parent_task": {
            "task_id": parent["id"],
            "contract_revision": parent["contract_revision"],
            "contract_sha256": semantic_json_sha256(parent),
        },
        "decision": "decomposed",
        "gap_type": "execution",
        "reason": "Split the exact Alpha and Beta source/meta pairs.",
        "children": children,
        "parent_requirement_coverage": coverage,
        "inbound_dependency_rewrites": [
            {
                "dependent_task_id": task["id"],
                "replacement_local_keys": list(local_keys),
                "reason": "The next wave requires both concrete values.",
            }
            for task in active_dependents
        ],
        "unsupported_assumptions": [],
        "unresolved_questions": [],
        "artifact_proposal": None,
    }
    return validate_decomposition_result(
        raw,
        parent_task=parent,
        existing_reconciliation_keys=plan.id_map,
    )


def _allocator_boundary_plan(high_water_task_id: str) -> WorkGraphPlan:
    base = graph_delta_smoke.make_plan()
    tasks = list(deepcopy(base.tasks))
    tasks.append(
        graph_delta_smoke.task(
            high_water_task_id,
            "allocator-high-water",
            "implementation",
            "NSC-001",
            "single_agent",
            "concrete",
            disposition="cancelled",
        )
    )
    id_map = deepcopy(base.id_map)
    id_map["allocator-high-water"] = high_water_task_id
    plan = WorkGraphPlan(
        id_map,
        tuple(tasks),
        deepcopy(base.resource_groups),
        deepcopy(base.project_requirements),
    )
    validate_work_graph_plan(plan)
    return plan


def _single_child_decomposition_result(plan: WorkGraphPlan) -> Any:
    parent = next(task for task in plan.tasks if task["id"] == "NSC-042")
    raw = graph_delta_smoke.decomposed_result(parent)
    child = raw["children"][1]
    child["local_dependencies"] = []
    child["exclusive_resources"] = list(parent.get("exclusive_resources") or ())
    raw["children"] = [child]
    for coverage in raw["parent_requirement_coverage"]:
        coverage["disposition"] = "assigned_to_child"
        coverage["child_targets"] = [
            target
            for target in coverage["child_targets"]
            if target["local_key"] == child["local_key"]
        ]
        coverage["integration_rationale"] = ""
    raw["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-030",
            "replacement_local_keys": [child["local_key"]],
            "reason": "The downstream consumer needs the finished bounded child.",
        }
    ]
    return validate_decomposition_result(
        raw,
        parent_task=parent,
        existing_reconciliation_keys=plan.id_map,
    )


def _serialized_plan_state(plan: WorkGraphPlan) -> str:
    return json.dumps(
        {
            "id_map": plan.id_map,
            "tasks": plan.tasks,
            "resource_groups": plan.resource_groups,
            "project_requirements": plan.project_requirements,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def test_graph_delta_allocator_exhaustion_is_bounded_and_atomic() -> None:
    max_minus_one = "NSC-999999998"
    boundary_source = _allocator_boundary_plan(max_minus_one)
    single = _single_child_decomposition_result(boundary_source)
    boundary_delta = plan_graph_delta(boundary_source, single.parent_task, single)
    require(
        tuple(boundary_delta.allocated_local_key_to_task_id.values())
        == (MAXIMUM_TASK_ID,),
        "the allocator did not assign the final canonical task ID",
    )

    two_children = graph_delta_smoke.validated_result(boundary_source)
    boundary_before = _serialized_plan_state(boundary_source)
    try:
        with patch.object(
            graph_delta_module,
            "_child_contract",
            side_effect=AssertionError(
                "allocator began constructing a partial graph after capacity was exhausted"
            ),
        ):
            plan_graph_delta(boundary_source, two_children.parent_task, two_children)
    except GraphDeltaPlanningError as exc:
        require(
            "task id allocator exhausted" in str(exc).casefold(),
            f"allocator reported the wrong capacity failure: {exc}",
        )
    else:
        raise AssertionError("allocator crossed the maximum task ID")
    require(
        _serialized_plan_state(boundary_source) == boundary_before,
        "allocator exhaustion mutated the source graph",
    )

    exhausted_source = _allocator_boundary_plan(MAXIMUM_TASK_ID)
    exhausted_single = _single_child_decomposition_result(exhausted_source)
    exhausted_before = _serialized_plan_state(exhausted_source)
    try:
        with patch.object(
            graph_delta_module,
            "_child_contract",
            side_effect=AssertionError(
                "allocator began constructing a graph after the maximum ID was occupied"
            ),
        ):
            plan_graph_delta(
                exhausted_source,
                exhausted_single.parent_task,
                exhausted_single,
            )
    except GraphDeltaPlanningError as exc:
        require(
            "task id allocator exhausted" in str(exc).casefold(),
            f"allocator reported the wrong maximum-ID failure: {exc}",
        )
    else:
        raise AssertionError("allocator created an ID beyond NSC-999999999")
    require(
        _serialized_plan_state(exhausted_source) == exhausted_before,
        "maximum-ID exhaustion mutated the source graph",
    )


def test_eight_decompositions_allocate_991_through_1006() -> None:
    plan = _gauntlet_plan()
    allocations: list[str] = []
    parent_ids = tuple(f"NSC-{number}" for number in range(911, 982, 10))
    for parent_id in parent_ids:
        parent = next(task for task in plan.tasks if task["id"] == parent_id)
        result = _gauntlet_result(plan, parent)
        delta = plan_graph_delta(plan, result.parent_task, result)
        allocations.extend(delta.allocated_local_key_to_task_id.values())
        overlay = delta.proposed_graph_overlay
        plan = WorkGraphPlan(
            overlay["id_map"],
            tuple(overlay["tasks"]),
            tuple(overlay["resource_groups"]),
            tuple(overlay["project_requirements"]),
        )
        validate_work_graph_plan(plan)
    expected = [f"NSC-{number}" for number in range(991, 1007)]
    require(allocations == expected, f"unexpected child allocation: {allocations}")
    relevant = {
        task["id"]
        for task in plan.tasks
        if 911 <= int(task["id"].split("-", 1)[1]) <= 1006
    }
    require(len(relevant) == 96, f"expected 96 gauntlet contracts, found {len(relevant)}")
    require(set(expected).issubset(relevant), "four-digit gauntlet children are missing")


def test_production_sources_use_only_the_bounded_ascii_task_id_rule() -> None:
    forbidden = (
        "NSC-[0-9]{3}",
        "NSC-[0-9]{3,}",
        r"NSC-\d",
        r"NSC-(\d",
        "NSC-([0-9]+)",
        "Tasks/NSC-[0-9]{3}\\.yaml",
    )
    roots = (
        ROOT / "Pipeline/ExecutionCrew",
        ROOT / "Pipeline/TaskDecomposition",
        ROOT / "Pipeline/TaskExecution",
        ROOT / "Pipeline/TaskGraph",
        ROOT / "Pipeline/TaskReviewAgent",
        ROOT / "Pipeline/Supervisor",
    )
    findings: list[str] = []
    for source_root in roots:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".ps1"} or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8-sig")
            for line_number, line in enumerate(text.splitlines(), 1):
                if any(pattern in line for pattern in forbidden):
                    findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_number}: {line.strip()}")
    require(not findings, "unsafe task ID regex boundaries remain:\n" + "\n".join(findings))

    canonical = "NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})"
    numeric_capture = "NSC-([0-9]{3}|[1-9][0-9]{3,8})"
    task_path = "Tasks/NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})\\.yaml"
    required_markers = {
        "Pipeline/ExecutionCrew/run_crew.py": (canonical,),
        "Pipeline/Supervisor/task_checkout.py": (canonical,),
        "Pipeline/TaskDecomposition/contracts.py": (canonical,),
        "Pipeline/TaskDecomposition/context_builder.py": (
            canonical,
            "TASK_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskDecomposition/live_decomposition.py": (
            "TASK_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskDecomposition/round_robin_decomposition.py": (
            "TASK_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskDecomposition/run_reviewer_replay_ab.py": (
            "TASK_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskDecomposition/session_pool_support.py": (
            "TASK_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskExecution/contracts.py": (canonical,),
        "Pipeline/TaskGraph/apply_graph_delta.py": ("NSC_ID_RE.fullmatch(value)",),
        "Pipeline/TaskGraph/conformance_records.py": (canonical,),
        "Pipeline/TaskGraph/graph_apply_materialize.py": (
            "NSC_ID_RE.fullmatch(task_id)",
        ),
        "Pipeline/TaskGraph/graph_delta.py": (numeric_capture,),
        "Pipeline/TaskGraph/token_usage_metrics.py": (canonical,),
        "Pipeline/TaskGraph/validate_draft_evidence.py": ("TASK_ID_PATTERN",),
        "Pipeline/TaskGraph/work_graph_validate.py": (numeric_capture,),
        "Pipeline/TaskReviewAgent/autonomous_graph_run.py": (canonical,),
        "Pipeline/TaskReviewAgent/contracts.py": (canonical,),
        "Pipeline/TaskReviewAgent/decomposition_policy_audit.py": (canonical,),
        "Pipeline/TaskReviewAgent/reset_task.py": (task_path,),
        "Pipeline/TaskReviewAgent/token_usage.py": (canonical,),
        "Pipeline/TaskReviewAgent/worker_result.py": (canonical,),
        "Pipeline/TaskReviewAgent/Start-AutonomousGraphRun.ps1": (
            canonical + r"\z",
        ),
        "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1": (canonical + r"\z",),
        "Pipeline/TaskReviewAgent/Start-TaskReviewAgent.ps1": (canonical + r"\z",),
    }
    missing: list[str] = []
    for relative_path, markers in required_markers.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
        for marker in markers:
            if marker not in source:
                missing.append(f"{relative_path}: missing {marker!r}")
    autonomous_launcher = (
        ROOT / "Pipeline/TaskReviewAgent/Start-AutonomousGraphRun.ps1"
    ).read_text(encoding="utf-8-sig")
    if autonomous_launcher.count(canonical + r"\z") != 2:
        missing.append(
            "Pipeline/TaskReviewAgent/Start-AutonomousGraphRun.ps1: "
            "target and exclusion validators must both use the canonical rule"
        )
    require(not missing, "canonical task ID sentinels are missing:\n" + "\n".join(missing))


def main() -> int:
    tests: tuple[Callable[[], None], ...] = (
        test_active_python_patterns_use_one_bounded_ascii_contract,
        test_task_review_contract_accepts_four_digits,
        test_supervisor_rejects_aliases_instead_of_normalizing_them,
        test_decomposition_contract_and_context_reject_noncanonical_ids,
        test_work_graph_rejects_each_noncanonical_identity_field_in_isolation,
        test_persistent_work_graph_rejects_raw_id_map_alias_before_normalization,
        test_decomposition_semantics_rejects_raw_parent_provenance_alias,
        test_decomposition_contract_task_id_fields_reject_aliases_directly,
        test_task_execution_contract_accepts_four_digits,
        test_worker_result_accepts_four_digits,
        test_task_review_token_usage_accepts_four_digits,
        test_taskgraph_token_usage_metric_accepts_four_digits,
        test_task_agent_launchers_enforce_bounded_ids,
        test_autonomous_graph_launcher_enforces_bounded_target_and_exclusion_ids,
        test_decomposition_entrypoints_reject_noncanonical_ids_before_source_access,
        test_decomposition_context_selects_four_digits,
        test_live_decomposition_accepts_four_digits,
        test_round_robin_decomposition_accepts_four_digits,
        test_reviewer_replay_accepts_four_digits,
        test_decomposition_session_bundle_accepts_four_digits,
        test_policy_audit_discovery_enforces_bounded_ids,
        test_reset_and_undo_discovery_enforce_bounded_ids,
        test_automated_decomposition_approval_accepts_999_and_1000,
        test_automated_decomposition_approval_rejects_noncanonical_children,
        test_execution_crew_accepts_four_digits,
        test_graph_delta_allocator_exhaustion_is_bounded_and_atomic,
        test_eight_decompositions_allocate_991_through_1006,
        test_production_sources_use_only_the_bounded_ascii_task_id_rule,
    )
    failures: list[str] = []
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - collect all fail-first boundaries.
            failures.append(f"{test.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
    if failures:
        raise AssertionError("task ID width regressions:\n" + "\n".join(failures))
    print(f"Task ID width smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    raise SystemExit(run_with_synthetic_authority(main))
