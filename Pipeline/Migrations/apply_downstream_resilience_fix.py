#!/usr/bin/env python3
"""One-shot bootstrap that materializes the downstream resilience change."""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".bootstrap" / "downstream-resilience"


def decode_parts(group: str, destination: Path) -> None:
    parts = sorted((BOOTSTRAP / group).glob("part-*"))
    if not parts:
        raise RuntimeError(f"missing bootstrap chunks for {group}")
    encoded = "".join(path.read_text(encoding="ascii") for path in parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(encoded, validate=True))


def patch_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{label}: expected source block missing in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    decode_parts(
        "module",
        ROOT / "Pipeline" / "TaskReviewAgent" / "downstream_resilience.py",
    )
    decode_parts(
        "test",
        ROOT
        / "Pipeline"
        / "TaskReviewAgent"
        / "tests"
        / "downstream_resilience_smoke_test.py",
    )

    policy = {
        "schema_version": "1.0",
        "tasks": {
            "NSC-020": {
                "task_contract_sha256": "f8c9e326646e16e2c4bcf5eba4a6505494a5044491bc70127d5b0a1603150a3b",
                "required_test_platforms": ["PlayMode"],
                "test_filters": {
                    "PlayMode": "NoSafeCircle.DoorPrototype.Tests.DoorInteractionPlayModeTests"
                },
                "authority": "committed_task_specific_authoritative_validation_policy",
            }
        },
    }
    policy_path = (
        ROOT
        / "Pipeline"
        / "TaskReviewAgent"
        / "authoritative_validation_policy.json"
    )
    policy_path.write_text(
        json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    init_path = ROOT / "Pipeline" / "TaskReviewAgent" / "__init__.py"
    patch_once(
        init_path,
        "from .mainline_reintegration import install_mainline_reintegration\n",
        "from .mainline_reintegration import install_mainline_reintegration\n"
        "from .downstream_resilience import install_downstream_resilience\n",
        "resilience import",
    )
    patch_once(
        init_path,
        "# Install the deterministic downstream transition before run_pipeline_agent imports\n"
        "# the controller and Codex action table. The installer is idempotent.\n"
        "install_mainline_reintegration()\n",
        "# Install deterministic downstream extensions before run_pipeline_agent imports\n"
        "# the controller and Codex action table. Both installers are idempotent and the\n"
        "# resilience layer intentionally wraps the already-installed reintegration layer.\n"
        "install_mainline_reintegration()\n"
        "install_downstream_resilience()\n",
        "resilience installation",
    )
    patch_once(
        init_path,
        '    "install_mainline_reintegration",\n',
        '    "install_mainline_reintegration",\n'
        '    "install_downstream_resilience",\n',
        "resilience export",
    )

    workflow = ROOT / ".github" / "workflows" / "task-review-agent-deterministic.yml"
    anchor = (
        "      - name: Run canonical scene path and contract migration smoke tests\n"
        "        run: python Pipeline/TaskReviewAgent/tests/scene_path_contract_migration_smoke_test.py\n\n"
    )
    step = (
        "      - name: Run downstream PASS carry-forward and rejection guard tests\n"
        "        run: python Pipeline/TaskReviewAgent/tests/downstream_resilience_smoke_test.py\n\n"
    )
    patch_once(workflow, anchor, anchor + step, "resilience CI step")

    print("Downstream resilience files materialized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
