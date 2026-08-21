from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import parallel_verification_crew as parallel
import verification_crew as base


def check_turn_defaults() -> None:
    source = Path(parallel.__file__).read_text(encoding="utf-8")
    base_source = Path(base.__file__).read_text(encoding="utf-8")

    assert 'RECONCILIATION_PARALLEL_VERIFY_COVERAGE_TURNS", "32"' in source
    assert 'RECONCILIATION_PARALLEL_VERIFY_STRUCTURE_TURNS", "32"' in source
    assert 'RECONCILIATION_PARALLEL_VERIFY_EXECUTION_TURNS", "32"' in source
    assert 'RECONCILIATION_VERIFY_MAX_TURNS", "32"' in base_source

    # Evidence auditing already had a larger budget and should remain larger.
    assert 'RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS", "36"' in source


def check_shared_thread_safe_console() -> None:
    assert hasattr(base, "thread_safe_print")
    assert hasattr(base, "_CONSOLE_PRINT_LOCK")
    assert parallel.print is base.thread_safe_print


def check_immediate_retry_priority() -> None:
    calls: list[tuple[str, int]] = []
    failed_once = False

    original_invoke = base.invoke_read_only_agent
    original_prompt_builder = parallel.build_scoped_prompt
    original_parallel_workers = parallel.PARALLEL_MAX_WORKERS
    original_recovery_attempts = parallel.MAX_TURN_RECOVERY_ATTEMPTS
    original_recovery_bonus = parallel.RECOVERY_TURN_BONUS

    def fake_invoke_read_only_agent(
        *,
        agent_name: str,
        model: str,
        prompt: str,
        schema: dict[str, Any],
        timeout_seconds: int,
        max_turns: int,
    ) -> dict[str, Any]:
        nonlocal failed_once
        _ = model, prompt, schema, timeout_seconds
        calls.append((agent_name, max_turns))
        if agent_name == "Auditor A" and not failed_once:
            failed_once = True
            raise RuntimeError("error_max_turns: Reached maximum number of turns")
        return {
            "agent": agent_name,
            "requested_model": "sonnet",
            "duration_seconds": 0.0,
            "result": {
                "verdict": "pass",
                "findings": [],
                "notes": [],
            },
        }

    spec_a = parallel.AuditSpec(
        key="a",
        agent_name="Auditor A",
        prompt_file="coverage_auditor.md",
        schema={},
        kind="coverage",
        domain="test",
        scope="test",
        max_turns=32,
    )
    spec_b = parallel.AuditSpec(
        key="b",
        agent_name="Auditor B",
        prompt_file="coverage_auditor.md",
        schema={},
        kind="coverage",
        domain="test",
        scope="test",
        max_turns=32,
    )

    try:
        base.invoke_read_only_agent = fake_invoke_read_only_agent
        parallel.build_scoped_prompt = lambda **_: "test prompt"
        parallel.PARALLEL_MAX_WORKERS = 1
        parallel.MAX_TURN_RECOVERY_ATTEMPTS = 1
        parallel.RECOVERY_TURN_BONUS = 12

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "audit-output"
            results = parallel.run_specs(
                specs=[spec_a, spec_b],
                candidate_path=parallel.base.ROOT / "unused-test-candidate.json",
                source_run_id="test-source",
                pass_label="test-pass",
                output_dir=output_dir,
                assignments={"a": "sonnet", "b": "sonnet"},
            )

        assert [result["agent"] for result in results] == ["Auditor A", "Auditor B"]
        assert calls == [
            ("Auditor A", 32),
            ("Auditor A [recovery]", 44),
            ("Auditor B", 32),
        ], calls
    finally:
        base.invoke_read_only_agent = original_invoke
        parallel.build_scoped_prompt = original_prompt_builder
        parallel.PARALLEL_MAX_WORKERS = original_parallel_workers
        parallel.MAX_TURN_RECOVERY_ATTEMPTS = original_recovery_attempts
        parallel.RECOVERY_TURN_BONUS = original_recovery_bonus


def main() -> int:
    check_turn_defaults()
    check_shared_thread_safe_console()
    check_immediate_retry_priority()
    print("verifier_execution_hardening_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
