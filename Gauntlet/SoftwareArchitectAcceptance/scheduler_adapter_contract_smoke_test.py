#!/usr/bin/env python3
"""Deterministic constructor-contract check for the production scheduler adapter.

Classification: pure structural regression. No fixture, Git, provider, Docker,
network, Issue, process, or Unity operation is performed.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Gauntlet.SoftwareArchitectAcceptance import scheduler_adapter  # noqa: E402
from Pipeline.TaskReviewAgent.polling_orchestrator import PollingOrchestrator  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_adapter_passes_only_current_scheduler_constructor_keywords() -> None:
    source = inspect.getsource(scheduler_adapter.RealPollingArchitectAdapter._ensure_orchestrator)
    tree = ast.parse(source.lstrip())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "PollingOrchestrator"
    ]
    require(len(calls) == 1, f"expected one scheduler construction, found {len(calls)}")
    supplied = {item.arg for item in calls[0].keywords if item.arg is not None}
    accepted = set(inspect.signature(PollingOrchestrator).parameters)
    unknown = sorted(supplied - accepted)
    require(not unknown, f"acceptance adapter passes removed scheduler arguments: {unknown}")
    require(
        "max_architect_invocations_per_session" not in supplied,
        "acceptance adapter retained the removed cumulative attempt cap",
    )


def test_real_adapter_translates_resume_portfolio_diagnostics_without_losing_launch() -> None:
    """Exercise the exact event translator without creating a Git fixture.

    This is a production-shaped resume portfolio: source refresh, resume
    ordering, architect batch execution, and the resulting launch. Removing
    any required diagnostic from the exact allow-list makes `_canonical_records`
    fail closed, while a broad ignore rule would violate the exact canonical
    event assertion below.
    """

    adapter = scheduler_adapter.RealPollingArchitectAdapter()
    produced = (
        {"event": "poll_started"},
        {
            "event": "source_main_refreshed",
            "before": "1" * 40,
            "after": "1" * 40,
            "changed": False,
        },
        {
            "event": "resume_priority_applied",
            "task_id": "NSC-906",
            "resume_phase": "resume",
            "deferred_fresh_candidate_count": 0,
            "same_batch_fresh_candidate_count": 1,
        },
        {
            "event": "architect_started",
            "source_head": "1" * 40,
            "portfolio_size": 2,
            "eligible_pairs": [],
        },
        {
            "event": "architect_completed",
            "analysis_id": "architect-portfolio-fixture",
            "portfolio_size": 2,
            "admission_count": 1,
        },
        {
            "event": "worker_launched",
            "task_id": "NSC-906",
            "worker_id": "worker-fixture",
            "argv": ["worker", "--task-id", "NSC-906"],
        },
    )
    records = adapter._canonical_records(
        produced,
        poll_id="acceptance-poll-0001",
        poll_index=1,
        result=SimpleNamespace(
            status="worker_launched",
            fatal=False,
            task_id="NSC-906",
            worker_id="worker-fixture",
        ),
    )
    require(
        [record["event"] for record in records]
        == ["poll_started", "worker_launched", "poll_finished"],
        f"resume portfolio produced unexpected canonical evidence: {records}",
    )
    require(
        records[-1]["outcome"] == "start" and records[-1]["task_id"] == "NSC-906",
        f"resume launch identity was lost during translation: {records[-1]}",
    )


def main() -> int:
    test_adapter_passes_only_current_scheduler_constructor_keywords()
    test_real_adapter_translates_resume_portfolio_diagnostics_without_losing_launch()
    print("scheduler_adapter_contract_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
