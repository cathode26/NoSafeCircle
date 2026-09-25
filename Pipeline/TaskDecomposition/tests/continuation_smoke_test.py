"""Continuing a stopped D1B.2 run from its last revised candidate.

Real engine runs with production-identity test providers: a three-call run
that stops right after a revision, then continuation runs that review the
same candidate further, verified end to end from retained bytes.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.context_builder import DecompositionPreflightError  # noqa: E402
from TaskDecomposition.continuation import run_continuation  # noqa: E402
from TaskDecomposition.review_chain import (  # noqa: E402
    ReviewChainError,
    verify_continuation_chain,
    verify_three_call_chain,
)
from TaskDecomposition.round_robin_decomposition import candidate_sha256, run_round_robin_decomposition  # noqa: E402
from TaskDecomposition.tests.review_chain_smoke_test import TIMEOUTS, digest_for, factory  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    revise_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result  # noqa: E402

ORDER = ("claude", "codex")


def resolved(*ids: str) -> list[dict[str, str]]:
    return [{"finding_id": finding_id, "status": "resolved", "explanation": "Replaced."} for finding_id in ids]


class Chain:
    """A stopped three-call run: claude authors, codex revises (r2), claude revises (r3)."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.source = base / "source"
        self.tasks = create_repository(self.source)
        self.parent = self.tasks["NSC-010"]
        self.output = base / "output"
        self.versions = [decomposed_result(self.parent)]
        for index in range(1, 7):
            revised = deepcopy(self.versions[0])
            revised["children"][0]["notes"] = f"Reviewer revision {index}."
            self.versions.append(revised)
        self.hashes = [candidate_sha256(validated_candidate(v, self.parent, self.tasks)) for v in self.versions]
        outputs = {
            "claude": [self.versions[0], revise_review(self.hashes[1], self.versions[2], round_number=3,
                                                       suffix="b", resolutions=resolved("round-02-a"))],
            "codex": [revise_review(self.hashes[0], self.versions[1], round_number=2, suffix="a")],
        }
        self.prior = run_round_robin_decomposition(
            source=self.source, output_root=self.output, task_id="NSC-010", provider_order=ORDER, max_calls=3,
            run_id="prior-run", provider_factory=factory({k: QueueProvider(v) for k, v in outputs.items()}),
            _require_physical_read_only_source=False)

    def continue_with(self, run_id: str, prior_id: str, outputs: dict[str, list[Any]], max_calls: int = 4) -> dict:
        return run_continuation(
            source=self.source, output_root=self.output, task_id="NSC-010", continue_from=prior_id,
            provider_order=ORDER, max_calls=max_calls, run_id=run_id,
            provider_factory=factory({name: QueueProvider(outputs.get(name, [])) for name in ORDER}),
            _require_physical_read_only_source=False)

    def run_bytes_sha(self, run_id: str) -> str:
        return hashlib.sha256((self.output / run_id / "decomposition_run_result.json").read_bytes()).hexdigest()

    def verify_prior(self) -> dict:
        return verify_three_call_chain(
            run_dir=self.output / "prior-run", run_result=self.prior, providers=ORDER,
            candidate_digest=digest_for(self.source), timeouts=TIMEOUTS, open_end=True)

    def verify(self, run_id: str, result: dict, prior: dict, prior_id: str, *, open_end: bool = False) -> dict:
        return verify_continuation_chain(
            run_dir=self.output / run_id, run_result=result, prior=prior,
            prior_run_result_sha256=self.run_bytes_sha(prior_id), providers=ORDER,
            candidate_digest=digest_for(self.source), timeouts={"decomposition_reviewer": 1200.0}, open_end=open_end)


def test_a_stopped_run_continues_to_an_independent_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        assert chain.prior["run_status"] == "needs_human", chain.prior["rejection_reasons"]
        result = chain.continue_with("cont-1", "prior-run", {
            "codex": [pass_review(chain.hashes[2], resolutions=resolved("round-03-b"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert [r["round_number"] for r in result["rounds"]] == [4]
        assert result["rounds"][0]["requested_provider"] == "codex"
        assert result["independent_approver_provider"] == "codex"
        assert (chain.output / "cont-1" / "decomposition_result.json").is_file()
        chained = chain.verify("cont-1", result, chain.verify_prior(), "prior-run")
        assert chained["approver_provider"] == "codex" and chained["calls_used"] == 1


def test_a_continuation_that_stops_converging_stops_itself() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        result = chain.continue_with("cont-stall", "prior-run", {
            "codex": [revise_review(chain.hashes[2], chain.versions[3], round_number=4, suffix="c",
                                    resolutions=resolved("round-03-b"))],
            "claude": [revise_review(chain.hashes[3], chain.versions[4], round_number=5, suffix="d",
                                     resolutions=resolved("round-04-c"))],
        })
        assert result["run_status"] == "needs_human" and result["calls_used"] == 2
        assert result["open_blocking_counts"] == [1, 1, 1]
        assert any("not converging" in reason for reason in result["rejection_reasons"])


def test_a_continuation_can_itself_be_continued_and_the_whole_chain_verifies() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        first = chain.continue_with("cont-a", "prior-run", {
            "codex": [revise_review(chain.hashes[2], chain.versions[3], round_number=4, suffix="c",
                                    resolutions=resolved("round-03-b"))]}, max_calls=1)
        assert first["run_status"] == "needs_human"
        second = chain.continue_with("cont-b", "cont-a", {
            "claude": [pass_review(chain.hashes[3], resolutions=resolved("round-04-c"))]})
        assert second["run_status"] == "review_ready", second["rejection_reasons"]
        assert [r["round_number"] for r in second["rounds"]] == [5]
        middle = chain.verify("cont-a", first, chain.verify_prior(), "prior-run", open_end=True)
        final = chain.verify("cont-b", second, middle, "cont-a")
        assert final["approver_provider"] == "claude"


def test_a_continuation_bound_to_another_prior_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        result = chain.continue_with("cont-1", "prior-run", {
            "codex": [pass_review(chain.hashes[2], resolutions=resolved("round-03-b"))]})
        try:
            verify_continuation_chain(
                run_dir=chain.output / "cont-1", run_result=result, prior=chain.verify_prior(),
                prior_run_result_sha256="0" * 64, providers=ORDER, candidate_digest=digest_for(chain.source))
        except ReviewChainError as exc:
            assert exc.code == "D3_CANDIDATE_LINK", exc
        else:
            raise AssertionError("a continuation bound to other prior bytes was accepted")


def test_only_a_run_that_stopped_after_a_revision_can_be_continued() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        passed = chain.continue_with("cont-1", "prior-run", {
            "codex": [pass_review(chain.hashes[2], resolutions=resolved("round-03-b"))]})
        assert passed["run_status"] == "review_ready"
        try:
            chain.continue_with("cont-2", "cont-1", {})
        except DecompositionPreflightError as exc:
            assert "only a run that stopped after a revision continues" in str(exc), exc
        else:
            raise AssertionError("a review_ready run was continued")


def test_a_newer_commit_on_top_of_the_prior_source_still_continues() -> None:
    import subprocess
    with tempfile.TemporaryDirectory(prefix="nsc-cont-") as text:
        chain = Chain(Path(text))
        (chain.source / "Docs").mkdir(exist_ok=True)
        (chain.source / "Docs" / "note.md").write_text("A pipeline change landed after the stopped run.",
                                                       encoding="utf-8")
        for args in (("add", "--", "Docs/note.md"),
                     ("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "-m", "later")):
            subprocess.run(["git", "-C", str(chain.source), *args], check=True)
        result = chain.continue_with("cont-1", "prior-run", {
            "codex": [pass_review(chain.hashes[2], resolutions=resolved("round-03-b"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert result["source_identity"]["head_commit"] != chain.prior["source_identity"]["head_commit"]


TESTS = (
    test_a_newer_commit_on_top_of_the_prior_source_still_continues,
    test_a_stopped_run_continues_to_an_independent_pass,
    test_a_continuation_that_stops_converging_stops_itself,
    test_a_continuation_can_itself_be_continued_and_the_whole_chain_verifies,
    test_a_continuation_bound_to_another_prior_is_refused,
    test_only_a_run_that_stopped_after_a_revision_can_be_continued,
)

if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition continuation smoke tests: PASS ({len(TESTS)} tests)")
