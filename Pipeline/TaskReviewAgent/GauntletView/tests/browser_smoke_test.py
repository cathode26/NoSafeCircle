"""Offline browser component tests against the real server and vendored graph.

Run explicitly with Node + Playwright and a local Chromium installation.
Regression mapping: request A-D, invariants 1-10. No Unity runtime needed.
"""
import os
from pathlib import Path
import subprocess

from display_scope_smoke_test import artifact_hashes, display_snapshot, fixture_http, proof_fixture
from gauntlet_view_smoke_test import event, write_jsonl


def main():
    fixture = proof_fixture()
    try:
        write_jsonl(
            fixture.state / ".task-review-agent" / "outputs" / "NSC-1002" / "worker-run-a" / "progress.jsonl",
            [
                event("run_started", timestamp="2026-09-07T00:59:00Z"),
                event("state_observed", {"phase": "waiting"}, timestamp="2026-09-07T01:00:00Z"),
                event("state_observed", {"phase": "checkout_preparation"}, timestamp="2026-09-07T01:01:00Z"),
                event("state_observed", {"phase": "implementation"}, timestamp="2026-09-07T01:02:00Z"),
                event("pipeline_action_started", {"action": "run_execution_crew"}, timestamp="2026-09-07T01:02:00Z"),
            ],
        )
        before = artifact_hashes(fixture.root)
        with fixture_http(display_snapshot(fixture)) as url:
            result = subprocess.run(
                ["node", "--test", str(Path(__file__).with_suffix(".cjs"))],
                env={**os.environ, "NSC_VIEW_TEST_URL": url,
                     "NSC_VIEW_TEST_PROGRESS": str(fixture.run / "progress.json")},
                check=False,
            )
        after = artifact_hashes(fixture.root)
        # Only the test's explicit SSE stimulus is allowed to change.
        progress = str((fixture.run / "progress.json").relative_to(fixture.root))
        before.pop(progress)
        after.pop(progress)
        assert before == after, "Browser/server mutated fixture artifacts"
        return result.returncode
    finally:
        fixture.close()


if __name__ == "__main__":
    raise SystemExit(main())
