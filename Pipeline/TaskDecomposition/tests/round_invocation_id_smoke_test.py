from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.contracts import (
    AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
    AgentInvocationRequest,
    Budgets,
    WriteBoundaries,
)
from TaskDecomposition.round_robin_decomposition import _round_invocation_id


MINIMAL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}


def prove_role(role: str, round_number: int, expected_fragment: str) -> None:
    invocation_id = _round_invocation_id(
        "NSC-010",
        "pass-first-review",
        round_number,
        role,
    )

    assert invocation_id.startswith(
        f"nsc-010-d1b2-r{round_number:02d}-{expected_fragment}-"
    )
    assert "_" not in invocation_id
    assert len(invocation_id) <= 64

    request = AgentInvocationRequest(
        AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,
        invocation_id,
        role,
        "Synthetic D1B.2 invocation-ID contract proof.",
        (),
        ("repository_read",),
        WriteBoundaries((), ()),
        MINIMAL_OUTPUT_SCHEMA,
        "high_reasoning",
        Budgets(1, 1, None),
        "codex-decomposition",
    )
    assert request.run_id == invocation_id
    assert request.role == role


def main() -> int:
    prove_role("task_decomposer", 1, "task-decomposer")
    prove_role("decomposition_reviewer", 2, "decomposition-reviewer")
    print("round_invocation_id_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
