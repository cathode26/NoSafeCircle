#!/usr/bin/env python3
"""Regression tests for the TaskReviewAgent Core/Supervisor/Delivery CI split.

Branch protection references the Core workflow by its exact name and job id,
so both must survive the split unchanged, and the Core workflow's `paths:`
trigger must fire for every PR touching Pipeline/TaskReviewAgent/** -- the
legacy check must never simply fail to appear. Whether Core's *expensive*
regression steps actually run is a separate, runtime decision made by its
"Determine Core suite relevance" step. It skips them only when every changed
file is Supervisor-owned, Delivery-owned, or a narrow ordinary task-delivery
surface (Assets/** or immutable TaskGraph evidence). Pipeline code, task
contracts, workflow changes, and unknown paths continue to select full Core.

Every substantive validation step from the pre-split monolith must still be
represented in exactly one (or, for genuinely cross-cutting cases, more than
one) of the three targeted workflows. Known Supervisor/Delivery-owned paths
must not leak into the other targeted suite, and unknown TaskReviewAgent
files must still trigger Core's check and select its full suite.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE_WORKFLOW = ROOT / ".github/workflows/task-review-agent-deterministic.yml"
SUPERVISOR_WORKFLOW = ROOT / ".github/workflows/task-review-agent-supervisor.yml"
DELIVERY_WORKFLOW = ROOT / ".github/workflows/task-review-agent-delivery.yml"

CORE_WORKFLOW_NAME = "TaskReviewAgent Deterministic Validation"
WINDOWS_SMOKE_JOB = "windows-smoke:"

# Every "python <path>" / "powershell.exe ... -File <path>" style test command
# that ran in the pre-split monolith. Each must appear in at least one of the
# three split workflows below.
MONOLITH_TEST_COMMANDS = (
    "Pipeline/TaskReviewAgent/tests/git_identity_guard_smoke_test.py",
    "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1",
    "Pipeline/TaskReviewAgent/tests/native_command_smoke_test.ps1",
    "Pipeline/TaskReviewAgent/tests/compose_supervisor_volume_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/codex_supervisor_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/codex_supervisor_turn_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/progress_logging_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/goal_loop_guard_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/mainline_reintegration_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/scene_path_contract_migration_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/downstream_resilience_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/downstream_determinism_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/downstream_action_grounding_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/merge_closeout_check_repoll_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/completed_issue_guard_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/actor_authorization_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/committed_task_loader_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/resource_reservation_smoke_test.py",
    "Pipeline/Testing/unity_log_hygiene_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/task_review_agent_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/issue_workflow_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/downstream_issue_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/delivery_review_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/real_checkout_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/durable_checkout_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/resumable_checkout_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/contract_migration_checkout_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/production_pipeline_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/production_controller_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/downstream_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/workflow_runtime_smoke_test.py",
    "Pipeline/TaskReviewAgent/run_agent.py",
    "Pipeline/TaskReviewAgent/tests/dispatch_plan_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/fresh_dispatch_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/contention_retry_smoke_test.py",
)

# TaskGraph review Issue materialization and the Stage 2-4 dispatch tests are
# Core-owned: they must run inside Core's windows-smoke job, gated exactly like
# every other Core regression step, so removal from Core is caught
# deterministically. The three dispatch tests also appear in
# MONOLITH_TEST_COMMANDS above.
CORE_ONLY_STEP_COMMANDS = (
    "Pipeline/TaskReviewAgent/tests/taskgraph_review_issue_materialization_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/synthetic_gauntlet_approver_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/architect_session_owner_smoke_test.py",
    "Gauntlet/SoftwareArchitectAcceptance/scheduler_adapter_contract_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/polling_orchestrator_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/autonomous_graph_run_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/execution_routing_smoke_test.py",
    "Pipeline/ExecutionCrew/tests/session_pool_smoke_test.py",
    "Pipeline/ExecutionCrew/tests/pooled_run_crew_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/execution_session_pool_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/dispatch_plan_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/fresh_dispatch_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/contention_retry_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/pending_transition_label_event_smoke_test.py",
    "Pipeline/TaskReviewAgent/tests/human_action_wait_smoke_test.py",
)
CORE_FULL_SUITE_GATE = "if: steps.scope.outputs.run_full_core == 'true'"

REPRESENTATIVE_SUPERVISOR_ONLY_PATHS = (
    "Pipeline/TaskReviewAgent/codex_supervisor_turn.py",
    "Pipeline/TaskReviewAgent/tests/codex_supervisor_smoke_test.py",
)
REPRESENTATIVE_DELIVERY_ONLY_PATHS = (
    "Pipeline/TaskReviewAgent/downstream_pipeline.py",
    "Pipeline/TaskReviewAgent/tests/delivery_review_smoke_test.py",
)
UNKNOWN_FUTURE_PATH = "Pipeline/TaskReviewAgent/claim_refs.py"
REPRESENTATIVE_ORDINARY_DELIVERY_PATHS = (
    "Assets/NoSafeCircle/DoorPrototype/Scripts/MuffcabbageGauntlet914.cs",
    "Assets/NoSafeCircle/DoorPrototype/Scripts/MuffcabbageGauntlet914.cs.meta",
    "Pipeline/TaskGraph/evidence/NSC-914/records/DEL-NSC-914-example.json",
    "Pipeline/TaskGraph/evidence/NSC-914/artifacts/Unity-EditMode-01-example.xml",
)
REPRESENTATIVE_POOL_CORE_PATHS = (
    "Pipeline/ExecutionCrew/session_pool.py",
    "Pipeline/ExecutionCrew/run_crew.py",
    "Pipeline/AgentRuntime/session_lifecycle.py",
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    tokens = re.split(r"(\*\*|\*)", pattern)
    parts = []
    for token in tokens:
        if token == "**":
            parts.append(".*")
        elif token == "*":
            parts.append("[^/]*")
        else:
            parts.append(re.escape(token))
    return re.compile("^" + "".join(parts) + "$")


def _extract_paths_block(workflow_text: str) -> list[str]:
    lines = workflow_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "paths:")
    entries = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        entries.append(stripped[2:].strip().strip('"').strip("'"))
    require(bool(entries), "paths: block must not be empty")
    return entries


def _triggers(paths_patterns: Sequence[str], changed_path: str) -> bool:
    triggered = False
    for raw in paths_patterns:
        negate = raw.startswith("!")
        pattern = raw[1:] if negate else raw
        if _glob_to_regex(pattern).match(changed_path):
            triggered = not negate
    return triggered


def _extract_core_scope_allowlist(core_workflow_text: str) -> list[str]:
    """Pull the $ownedByOtherSuites array out of Core's scope-detection step.

    This is the runtime allowlist of Supervisor/Delivery-owned files that
    lets Core's windows-smoke job skip its expensive steps cheaply. It is a
    plain quoted-string PowerShell array, one entry per line.
    """
    match = re.search(
        r"\$ownedByOtherSuites\s*=\s*@\((.*?)\)",
        core_workflow_text,
        re.DOTALL,
    )
    require(match is not None, "Core workflow must define $ownedByOtherSuites for its scope check")
    entries = re.findall(r'"([^"]+)"', match.group(1))
    require(bool(entries), "$ownedByOtherSuites must not be empty")
    return entries


def _extract_core_delivery_prefixes(core_workflow_text: str) -> list[str]:
    """Read Core's narrow ordinary task-delivery prefix list."""
    match = re.search(
        r"\$ordinaryDeliveryPrefixes\s*=\s*@\((.*?)\)",
        core_workflow_text,
        re.DOTALL,
    )
    require(
        match is not None,
        "Core workflow must define $ordinaryDeliveryPrefixes",
    )
    entries = re.findall(r'"([^"]+)"', match.group(1))
    require(bool(entries), "$ordinaryDeliveryPrefixes must not be empty")
    return entries


def _core_selects_full_suite(
    scope_allowlist: Sequence[str],
    changed_path: str,
    *,
    ordinary_delivery_prefixes: Sequence[str] = (),
) -> bool:
    """Mirror Core's fail-safe runtime path classification."""
    return not (
        changed_path in scope_allowlist
        or any(changed_path.startswith(prefix) for prefix in ordinary_delivery_prefixes)
    )


def test_core_workflow_identity_is_preserved() -> None:
    text = CORE_WORKFLOW.read_text(encoding="utf-8")
    require(
        text.splitlines()[0] == f"name: {CORE_WORKFLOW_NAME}",
        "Core workflow name must remain exactly "
        f"'{CORE_WORKFLOW_NAME}' for branch protection.",
    )
    require(
        WINDOWS_SMOKE_JOB in text,
        "Core workflow must still define the windows-smoke job for branch protection.",
    )


def test_every_monolith_command_is_still_represented() -> None:
    combined = "\n".join(
        workflow.read_text(encoding="utf-8")
        for workflow in (CORE_WORKFLOW, SUPERVISOR_WORKFLOW, DELIVERY_WORKFLOW)
    )
    missing = [cmd for cmd in MONOLITH_TEST_COMMANDS if cmd not in combined]
    require(
        not missing,
        "pre-split monolith commands missing from the split workflows: "
        + ", ".join(missing),
    )


def test_supervisor_only_paths_do_not_route_to_delivery() -> None:
    supervisor_paths = _extract_paths_block(SUPERVISOR_WORKFLOW.read_text(encoding="utf-8"))
    delivery_paths = _extract_paths_block(DELIVERY_WORKFLOW.read_text(encoding="utf-8"))
    for changed in REPRESENTATIVE_SUPERVISOR_ONLY_PATHS:
        require(
            _triggers(supervisor_paths, changed),
            f"{changed} must trigger Supervisor Validation",
        )
        require(
            not _triggers(delivery_paths, changed),
            f"{changed} must not trigger Delivery Validation",
        )


def test_delivery_only_paths_do_not_route_to_supervisor() -> None:
    supervisor_paths = _extract_paths_block(SUPERVISOR_WORKFLOW.read_text(encoding="utf-8"))
    delivery_paths = _extract_paths_block(DELIVERY_WORKFLOW.read_text(encoding="utf-8"))
    for changed in REPRESENTATIVE_DELIVERY_ONLY_PATHS:
        require(
            _triggers(delivery_paths, changed),
            f"{changed} must trigger Delivery Validation",
        )
        require(
            not _triggers(supervisor_paths, changed),
            f"{changed} must not trigger Supervisor Validation",
        )


def test_supervisor_only_change_keeps_legacy_check_but_skips_full_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    for changed in REPRESENTATIVE_SUPERVISOR_ONLY_PATHS:
        require(
            _triggers(core_paths, changed),
            f"{changed} must still trigger the legacy Core check (windows-smoke must exist)",
        )
        require(
            not _core_selects_full_suite(scope_allowlist, changed),
            f"{changed} is Supervisor-owned and must not select the full Core regression suite",
        )


def test_delivery_only_change_keeps_legacy_check_but_skips_full_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    for changed in REPRESENTATIVE_DELIVERY_ONLY_PATHS:
        require(
            _triggers(core_paths, changed),
            f"{changed} must still trigger the legacy Core check (windows-smoke must exist)",
        )
        require(
            not _core_selects_full_suite(scope_allowlist, changed),
            f"{changed} is Delivery-owned and must not select the full Core regression suite",
        )


def test_ordinary_task_delivery_keeps_required_check_but_skips_full_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    delivery_prefixes = _extract_core_delivery_prefixes(core_text)
    require(
        _triggers(
            core_paths,
            "Pipeline/TaskGraph/evidence/NSC-914/records/DEL-NSC-914-example.json",
        ),
        "ordinary delivery evidence must keep the required Core check present",
    )
    for changed in REPRESENTATIVE_ORDINARY_DELIVERY_PATHS:
        require(
            not _core_selects_full_suite(
                scope_allowlist,
                changed,
                ordinary_delivery_prefixes=delivery_prefixes,
            ),
            f"{changed} is an ordinary task-delivery surface and must skip full Core",
        )


def test_task_contract_pipeline_workflow_and_unknown_paths_still_fail_safe() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    delivery_prefixes = _extract_core_delivery_prefixes(core_text)
    for changed in (
        "Tasks/NSC-914.yaml",
        "Pipeline/TaskGraph/task_loader.py",
        ".github/workflows/task-review-agent-deterministic.yml",
        UNKNOWN_FUTURE_PATH,
        "assets/incorrect-case.cs",
    ):
        require(
            _core_selects_full_suite(
                scope_allowlist,
                changed,
                ordinary_delivery_prefixes=delivery_prefixes,
            ),
            f"{changed} must continue to select the full Core regression suite",
        )


def test_core_owned_change_selects_full_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    changed = "Pipeline/TaskReviewAgent/real_checkout.py"
    require(_triggers(core_paths, changed), f"{changed} must trigger the legacy Core check")
    require(
        _core_selects_full_suite(scope_allowlist, changed),
        f"{changed} is Core-owned and must select the full Core regression suite",
    )


def test_pool_and_runtime_changes_trigger_full_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    for changed in REPRESENTATIVE_POOL_CORE_PATHS:
        require(
            _triggers(core_paths, changed),
            f"{changed} must trigger the Core workflow that owns pool regressions",
        )
        require(
            _core_selects_full_suite(scope_allowlist, changed),
            f"{changed} must select the full Core regression suite",
        )


def _core_steps(core_workflow_text: str) -> list[str]:
    """Split Core's job body into per-step blocks (one per `- name:` entry)
    so a step's `if:` gating can be checked independently of every other
    step's text."""
    lines = core_workflow_text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^\s{6}- name:", line)]
    require(bool(starts), "Core workflow must define at least one step")
    starts.append(len(lines))
    return ["\n".join(lines[starts[i] : starts[i + 1]]) for i in range(len(starts) - 1)]


def test_core_owned_tests_run_in_core_gated_like_other_core_tests() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    for command in CORE_ONLY_STEP_COMMANDS:
        steps = [step for step in _core_steps(core_text) if command in step]
        require(
            bool(steps),
            f"Core workflow must run {command}: removing it from Core must be caught here",
        )
        for step in steps:
            require(
                CORE_FULL_SUITE_GATE in step,
                f"{command} must be gated exactly like the other Core "
                f"regression tests ('{CORE_FULL_SUITE_GATE}'): {step}",
            )


def test_unknown_task_review_agent_file_routes_to_core() -> None:
    core_text = CORE_WORKFLOW.read_text(encoding="utf-8")
    core_paths = _extract_paths_block(core_text)
    scope_allowlist = _extract_core_scope_allowlist(core_text)
    supervisor_paths = _extract_paths_block(SUPERVISOR_WORKFLOW.read_text(encoding="utf-8"))
    delivery_paths = _extract_paths_block(DELIVERY_WORKFLOW.read_text(encoding="utf-8"))
    require(
        _triggers(core_paths, UNKNOWN_FUTURE_PATH),
        f"unknown file {UNKNOWN_FUTURE_PATH} must fail safe by triggering the legacy Core check",
    )
    require(
        _core_selects_full_suite(scope_allowlist, UNKNOWN_FUTURE_PATH),
        f"unknown file {UNKNOWN_FUTURE_PATH} must fail safe by selecting the full Core suite",
    )
    require(
        not _triggers(supervisor_paths, UNKNOWN_FUTURE_PATH),
        f"unknown file {UNKNOWN_FUTURE_PATH} must not be claimed by Supervisor",
    )
    require(
        not _triggers(delivery_paths, UNKNOWN_FUTURE_PATH),
        f"unknown file {UNKNOWN_FUTURE_PATH} must not be claimed by Delivery",
    )


def main() -> int:
    test_core_workflow_identity_is_preserved()
    test_every_monolith_command_is_still_represented()
    test_supervisor_only_paths_do_not_route_to_delivery()
    test_delivery_only_paths_do_not_route_to_supervisor()
    test_supervisor_only_change_keeps_legacy_check_but_skips_full_core()
    test_delivery_only_change_keeps_legacy_check_but_skips_full_core()
    test_core_owned_change_selects_full_core()
    test_pool_and_runtime_changes_trigger_full_core()
    test_core_owned_tests_run_in_core_gated_like_other_core_tests()
    test_unknown_task_review_agent_file_routes_to_core()
    print("ci_workflow_split_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
