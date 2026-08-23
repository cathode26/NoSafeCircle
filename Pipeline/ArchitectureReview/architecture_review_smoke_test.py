from __future__ import annotations

import json
import hashlib
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import architecture_review as review
import architecture_review_resume as resume


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    assert len(review.ROLE_SPECS) == 8

    keys = [role["key"] for role in review.ROLE_SPECS]
    names = [role["name"] for role in review.ROLE_SPECS]
    assert len(keys) == len(set(keys))
    assert len(names) == len(set(names))

    required_roles = {
        "game_technical_director",
        "workflow_systems_architect",
        "llm_reliability_engineer",
        "unity_production_engineer",
        "yagni_complexity_critic",
        "autonomous_agent_architect",
        "adversarial_qa",
        "game_producer",
    }
    assert set(keys) == required_roles

    with tempfile.TemporaryDirectory(prefix="atomic-json-") as temp_text:
        destination = Path(temp_text) / "LATEST.json"
        writer_count = 32
        start = threading.Barrier(writer_count)
        payloads = [
            {
                "writer": index,
                "marker": f"writer-{index}-\u2603",
                "content": [f"payload-{index}"] * 4096,
            }
            for index in range(writer_count)
        ]

        def write_payload(payload: dict[str, object]) -> None:
            start.wait()
            review.safe_write_json(destination, payload)

        with ThreadPoolExecutor(max_workers=writer_count) as executor:
            futures = [executor.submit(write_payload, payload) for payload in payloads]
            for future in futures:
                future.result()

        final_payload = json.loads(destination.read_text(encoding="utf-8"))
        assert final_payload in payloads
        assert list(Path(temp_text).iterdir()) == [destination]
        assert destination.read_bytes().endswith(b"\n")

    assert "Docs/AI-Pipeline/CURRENT_STATE.md" in review.ARCHITECTURE_DOCS
    assert "Docs/AI-Pipeline/DECISIONS.md" in review.ARCHITECTURE_DOCS
    assert "Docs/AI-Pipeline/01_MILESTONE_TASK_GRAPH.md" in review.ARCHITECTURE_DOCS

    sample = review.common_review_prompt(
        role_name="Smoke Test Reviewer",
        role_focus="Test the review contract.",
        frozen_head="deadbeef",
    )

    assert "You may reject them" in sample
    assert "Do NOT assume `Tasks/*.yaml`" in sample
    assert "GDD is iterative" in sample
    assert "fundamentally sound" in sample
    assert "days instead of weeks" in sample
    assert "materially different architecture" in sample
    assert "do not inspect prior ArchitectureReview reviewer" in sample
    assert "Pipeline/ArchitectureReview/outputs/" in sample
    assert "primary repository evidence" in sample
    assert "sibling reviewer outputs" in sample
    assert "architecture or current-state documents" in sample
    assert "prior ArchitectureReview\nverdicts" in sample
    assert "reviewer recommendations" in sample
    assert "synthesis conclusions" in sample
    assert "adversarial critique\nconclusions" in sample
    assert "reviewer vote/count summaries" in sample
    assert "current implementation" in sample
    assert "accepted ADR decisions" in sample
    assert "current documented architecture facts" in sample
    assert "independently decide whether they are\ngood or bad" in sample

    synthesis = review.synthesis_prompt(
        frozen_head="deadbeef", review_dir=review.REVIEW_ROOT / "temporary" / "reviews"
    )
    assert "eight human-facing review files from this current run" in synthesis
    assert "Do not read prior-run or other-provider" in synthesis
    assert "provider/AgentRuntime logs" in synthesis
    adversary = review.adversary_prompt(
        frozen_head="deadbeef",
        synthesis_path=review.REVIEW_ROOT / "temporary" / "synthesis.json",
        review_dir=review.REVIEW_ROOT / "temporary" / "reviews",
    )
    assert "eight current-run human-facing reviews" in adversary
    assert "Ignore all prior-run or other-provider" in adversary

    original_root = review.OUTPUT_ROOT
    original_namespace = review.PROVIDER_NAMESPACE
    evidence_root = review.REVIEW_ROOT / "evidence"
    evidence_before = tree_digest(evidence_root)
    with tempfile.TemporaryDirectory(prefix="output-layout-", dir=review.REVIEW_ROOT) as temp_text:
        review.OUTPUT_ROOT = Path(temp_text)
        try:
            review.configure_provider_namespace("claude")
            assert review.provider_output_root() == Path(temp_text) / "claude"
            original_dirty, original_head = review.git_dirty, review.git_head
            review.git_dirty = lambda: False
            review.git_head = lambda: "deadbeef"
            try:
                claude_new_dir, claude_manifest = resume.create_new_run(
                    SimpleNamespace(seed=1, allow_dirty=False)
                )
                assert claude_manifest["provider_namespace"] == "claude"
                assert claude_new_dir.parent == Path(temp_text) / "claude" / "runs"
            finally:
                review.git_dirty, review.git_head = original_dirty, original_head

            review.configure_provider_namespace("codex")
            assert review.provider_output_root() == Path(temp_text) / "codex"
            original_dirty, original_head = review.git_dirty, review.git_head
            review.git_dirty = lambda: False
            review.git_head = lambda: "deadbeef"
            try:
                codex_new_dir, codex_manifest = resume.create_new_run(
                    SimpleNamespace(seed=2, allow_dirty=False)
                )
                assert codex_manifest["provider_namespace"] == "codex"
                assert codex_new_dir.parent == Path(temp_text) / "codex" / "runs"
            finally:
                review.git_dirty, review.git_head = original_dirty, original_head

            run_dir = review.provider_output_root() / "runs" / "complete-codex"
            run_dir.mkdir(parents=True)
            review.safe_write_json(run_dir / "manifest.json", {
                "provider_namespace": "codex", "status": "partial_review_failure"
            })
            global_latest = review.OUTPUT_ROOT / "latest" / "LATEST.json"
            try:
                review.publish_latest(run_dir=run_dir, run_id="complete-codex",
                    frozen_head="deadbeef", synthesis={"agent": "s"}, adversary={"agent": "a"})
            except RuntimeError:
                pass
            else:
                raise AssertionError("partial runs must not publish latest")
            assert not global_latest.exists()

            review.safe_write_json(run_dir / "manifest.json", {
                "provider_namespace": "codex", "status": "complete"
            })
            review.publish_latest(run_dir=run_dir, run_id="complete-codex",
                frozen_head="deadbeef", synthesis={"agent": "s"}, adversary={"agent": "a"})
            codex_latest_dir = review.OUTPUT_ROOT / "codex" / "latest"
            codex_latest = json.loads((codex_latest_dir / "LATEST.json").read_text(encoding="utf-8"))
            assert codex_latest["provider_namespace"] == "codex"
            assert codex_latest["run_id"] == "complete-codex"
            assert codex_latest["frozen_head"] == "deadbeef"
            assert codex_latest["run_path"].endswith("/codex/runs/complete-codex")
            assert {path.name for path in codex_latest_dir.iterdir()} == {
                "LATEST.json", "synthesis.json", "adversarial_critique.json"
            }
            global_latest_dir = review.OUTPUT_ROOT / "latest"
            assert {path.name for path in global_latest_dir.iterdir()} == {"LATEST.json"}
            global_before_partial = global_latest.read_bytes()

            failed_run = review.provider_output_root() / "runs" / "failed-codex"
            failed_run.mkdir(parents=True)
            review.safe_write_json(failed_run / "manifest.json", {
                "provider_namespace": "codex", "status": "adversary_failure"
            })
            try:
                review.publish_latest(run_dir=failed_run, run_id="failed-codex",
                    frozen_head="badc0de", synthesis={"agent": "bad"}, adversary={"agent": "bad"})
            except RuntimeError:
                pass
            else:
                raise AssertionError("failed runs must not publish latest")
            assert global_latest.read_bytes() == global_before_partial

            review.configure_provider_namespace("claude")
            claude_run = review.provider_output_root() / "runs" / "complete-claude"
            claude_run.mkdir(parents=True)
            review.safe_write_json(claude_run / "manifest.json", {
                "provider_namespace": "claude", "status": "complete"
            })
            review.publish_latest(run_dir=claude_run, run_id="complete-claude",
                frozen_head="cafebabe", synthesis={"agent": "s2"}, adversary={"agent": "a2"})
            claude_latest = json.loads((review.OUTPUT_ROOT / "claude" / "latest" / "LATEST.json").read_text(encoding="utf-8"))
            global_record = json.loads(global_latest.read_text(encoding="utf-8"))
            assert claude_latest == global_record
            assert global_record["provider_namespace"] == "claude"
            assert global_record["run_path"].endswith("/claude/runs/complete-claude")
            assert {path.name for path in global_latest_dir.iterdir()} == {"LATEST.json"}
        finally:
            review.OUTPUT_ROOT = original_root
            review.configure_provider_namespace(original_namespace)
    assert evidence_root.is_dir()
    assert tree_digest(evidence_root) == evidence_before

    assignments = review.assign_models(12345)
    assert set(assignments) == required_roles
    assert all(model in review.MODEL_POOL for model in assignments.values())

    verdict_enum = review.REVIEW_SCHEMA["properties"]["overall_verdict"]["enum"]
    assert "fundamentally_wrong_approach" in verdict_enum
    assert "sound_high_leverage" in verdict_enum

    print("architecture_review_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
