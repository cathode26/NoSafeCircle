from __future__ import annotations

import json
import tempfile
from pathlib import Path

import architecture_review as base
import architecture_review_codex as codex
import architecture_review_resume as resume


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def main() -> int:
    assert base.invoke_read_only_agent is codex.invoke_codex_agent
    assert codex.REVIEW_REASONING_EFFORT == "high"
    assert codex.SYNTHESIS_REASONING_EFFORT == "max"
    assert codex.ADVERSARY_REASONING_EFFORT == "max"

    with tempfile.TemporaryDirectory(prefix="nsc-resume-smoke-") as temp_text:
        run_dir = Path(temp_text)
        review_dir = run_dir / "reviews"
        review_dir.mkdir()

        manifest = {
            "provider_namespace": "codex",
            "run_id": "smoke-run",
            "seed": 12345,
            "frozen_head": "deadbeef",
            "status": "started",
        }
        write_json(run_dir / "manifest.json", manifest)

        assignments = {
            role["key"]: codex.MODEL_POOL[index % len(codex.MODEL_POOL)]
            for index, role in enumerate(base.ROLE_SPECS)
        }
        write_json(run_dir / "model_assignments.json", assignments)

        for role in base.ROLE_SPECS:
            write_json(
                review_dir / f"{role['key']}.json",
                {
                    "agent": role["name"],
                    "provider": "smoke",
                    "model": assignments[role["key"]],
                    "duration_seconds": 0,
                    "result": {"ok": True},
                },
            )

        original_invoke = base.invoke_read_only_agent

        def fail_if_called(**_: object) -> dict[str, object]:
            raise AssertionError("Completed reviewers must not be invoked again.")

        base.invoke_read_only_agent = fail_if_called
        try:
            results = resume.run_reviews_resumable(
                run_dir=run_dir,
                frozen_head="deadbeef",
                seed=12345,
            )
        finally:
            base.invoke_read_only_agent = original_invoke

        assert len(results) == len(base.ROLE_SPECS)
        updated_manifest = json.loads(
            (run_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert updated_manifest["status"] == "reviews_complete"
        assert updated_manifest["completed_review_count"] == len(base.ROLE_SPECS)

        first_role = base.ROLE_SPECS[0]
        first_path = review_dir / f"{first_role['key']}.json"
        assert (
            resume.load_completed_result(
                first_path,
                expected_agent=first_role["name"],
            )
            is not None
        )

        first_path.write_text("{not-json", encoding="utf-8")
        assert (
            resume.load_completed_result(
                first_path,
                expected_agent=first_role["name"],
            )
            is None
        )

    original_output_root = base.OUTPUT_ROOT
    original_git_head = base.git_head
    with tempfile.TemporaryDirectory(prefix="resume-namespace-", dir=base.REVIEW_ROOT) as temp_text:
        base.OUTPUT_ROOT = Path(temp_text)
        base.configure_provider_namespace("codex")
        mismatch_dir = base.provider_output_root() / "runs" / "same-id"
        write_json(mismatch_dir / "manifest.json", {
            "provider_namespace": "claude", "frozen_head": "deadbeef"
        })
        base.git_head = lambda: "deadbeef"
        try:
            try:
                resume.open_resumed_run("same-id")
            except RuntimeError as exc:
                assert "different provider namespace" in str(exc)
            else:
                raise AssertionError("provider mismatch must refuse resume")
        finally:
            base.OUTPUT_ROOT = original_output_root
            base.git_head = original_git_head
            base.configure_provider_namespace("codex")

    print("architecture_review_resume_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
