"""The opt-in designer/bookkeeper split of the D1B.2 author round.

Real engine runs with test providers that report production identities. The
designer returns an ownership sheet; the bookkeeper, on the designer's
provider at its own model, writes the result; the reviewer is unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.bookkeeping_evidence import BookkeepingEvidenceError, verify_bookkeeping  # noqa: E402
from TaskDecomposition.bookkeeping_skeleton import impose_skeleton, result_skeleton  # noqa: E402
from TaskDecomposition.ownership_sheet import sheet_from_result  # noqa: E402
from TaskDecomposition.review_chain import verify_three_call_chain  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.review_chain_smoke_test import TIMEOUTS, digest_for, factory  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result  # noqa: E402

BOOKKEEPER_MODEL = "fixture-bookkeeper"


def dropped_entry(result: dict) -> dict:
    """A structural slip: the first child's first acceptance criterion is reworded."""
    slipped = deepcopy(result)
    slipped["children"][0]["acceptance_criteria"][0]["requirement"] += " (reworded)"
    return slipped


def blank_reference(result: dict) -> dict:
    """A prose slip the skeleton cannot fix: an entry reference left blank."""
    slipped = deepcopy(result)
    slipped["children"][0]["acceptance_criteria"][0]["reference"] = ""
    return slipped


def dropped_notes(result: dict) -> dict:
    """The bookkeeper rewrites a child's notes without the designer's constraints."""
    slipped = deepcopy(result)
    slipped["children"][0]["notes"] = "Create another projectile pool."
    return slipped


class Run:
    def __init__(self, base: Path, bookkeeper_outputs: list[str], *, max_calls: int = 2,
                 sheet_change: Callable[[dict], None] | None = None, run_id: str = "bk-run",
                 corrected: bool = False) -> None:
        self.source = base / "source"
        self.tasks = create_repository(self.source)
        self.parent = self.tasks["NSC-010"]
        self.good = decomposed_result(self.parent)
        self.sheet = sheet_from_result(self.good)
        self.refused_sheet = None
        if sheet_change is not None:
            self.refused_sheet = deepcopy(self.sheet)
            sheet_change(self.refused_sheet)
        if corrected:
            designs = [self.refused_sheet, self.sheet]
        elif self.refused_sheet is not None:
            designs = [self.refused_sheet, self.refused_sheet]
        else:
            designs = [self.sheet]
        outputs = {"good": lambda: deepcopy(self.good), "structural": lambda: dropped_entry(self.good),
                   "prose": lambda: blank_reference(self.good), "notes": lambda: dropped_notes(self.good)}
        self.claude = QueueProvider([*designs, *(outputs[kind] for kind in bookkeeper_outputs)])
        # The reviewer passes the candidate the engine builds: the last output on the skeleton.
        last = outputs[bookkeeper_outputs[-1]]() if bookkeeper_outputs else self.good
        built = impose_skeleton(result_skeleton(self.sheet), last)
        try:
            good_hash = candidate_sha256(validated_candidate(built, self.parent, self.tasks))
        except Exception:
            good_hash = "0" * 64
        self.codex = QueueProvider([pass_review(good_hash)])
        self.run_id = run_id
        self.result = run_round_robin_decomposition(
            source=self.source, output_root=base / "output", task_id="NSC-010",
            provider_order=("claude", "codex"), max_calls=max_calls, run_id=run_id,
            provider_factory=factory({"claude": self.claude, "codex": self.codex}),
            _require_physical_read_only_source=False, bookkeeper_model=BOOKKEEPER_MODEL,
        )
        self.run_dir = base / "output" / run_id

    def verify(self, run_result: dict | None = None, *, author_index: int = 0) -> dict:
        run_result = run_result or self.result
        return verify_bookkeeping(
            run_dir=self.run_dir, run_result=run_result, author_entry=run_result["rounds"][author_index],
            first_provider="claude", parent_contract=self.parent,
            candidate_digest=digest_for(self.source), designer_timeout=TIMEOUTS["task_decomposer"])


def refused(action: Callable[[], Any], text: str) -> None:
    try:
        action()
    except BookkeepingEvidenceError as exc:
        assert text in str(exc), f"expected {text!r}, got {exc}"
    else:
        raise AssertionError(f"expected a refusal mentioning {text!r}")


def test_a_conforming_bookkeeper_reaches_the_independent_review() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["good"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert run.result["calls_used"] == 2 and run.result["author_corrections_used"] == 0
        record = run.result["designer_bookkeeper"]
        assert record["bookkeeper_model"] == BOOKKEEPER_MODEL and len(record["attempts"]) == 1
        assert record["attempts"][0]["actual_model"] == BOOKKEEPER_MODEL
        assert run.result["rounds"][0]["actual_model"] == "fixture-model"
        designer_prompt = run.claude.requests[0].prompt
        bookkeeper_prompt = run.claude.requests[1].prompt
        assert "DESIGN MODE" in designer_prompt and "BOOKKEEPING MODE" in bookkeeper_prompt
        verified = run.verify()
        assert verified["attempts"] == 1 and verified["conformed"]
        assert "rounds/01/ownership_sheet.json" in verified["evidence_sha256"]


def test_a_structural_slip_is_corrected_by_the_skeleton_without_a_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["structural"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        attempts = run.result["designer_bookkeeper"]["attempts"]
        assert [a["status"] for a in attempts] == ["conformed"]
        assert any("child entries differ" in slip for slip in attempts[0]["structural_slips_corrected"])
        assert run.verify()["attempts"] == 1


def test_designer_notes_survive_a_bookkeeper_that_drops_them() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["notes"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        published = json.loads((run.run_dir / "decomposition_result.json").read_text(encoding="utf-8"))
        notes = published["children"][0]["notes"]
        assert run.sheet["children"][0]["design_notes"] in notes and "Create another projectile pool." in notes
        run.verify()


def test_one_prose_slip_is_retried_with_its_problems() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["prose", "good"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        attempts = run.result["designer_bookkeeper"]["attempts"]
        assert [a["status"] for a in attempts] == ["rejected", "conformed"]
        assert any("must be a non-blank string" in problem for problem in attempts[0]["problems"])
        retry_prompt = run.claude.requests[2].prompt
        assert "must be a non-blank string" in retry_prompt and "BOOKKEEPING MODE" not in retry_prompt
        assert run.verify()["attempts"] == 2


def test_two_slips_stop_the_run_without_a_result() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["prose", "prose"])
        assert run.result["run_status"] == "rejected"
        assert run.result["decomposition_result_path"] is None and run.codex.calls == 0
        assert any("bookkeeping did not state the sheet after 2 attempts" in reason
                   for reason in run.result["rejection_reasons"]), run.result["rejection_reasons"]


def test_a_sheet_refused_twice_stops_before_any_bookkeeping() -> None:
    def uncover(sheet: dict) -> None:
        for child in sheet["children"]:
            for entry in child["entries"]:
                entry["covers"] = [ref for ref in entry["covers"] if ref != "acceptance_criteria:AC-001"]
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), [], sheet_change=uncover)
        assert run.result["run_status"] == "rejected" and run.claude.calls == 2
        assert run.result["author_corrections_used"] == 1 and run.result["designer_bookkeeper"] is None
        assert any("designer ownership sheet refused" in reason and "acceptance_criteria:AC-001" in reason
                   for reason in run.result["rejection_reasons"]), run.result["rejection_reasons"]


def test_tampered_bookkeeping_evidence_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["prose", "good"])
        sheet_path = run.run_dir / "rounds" / "01" / "ownership_sheet.json"
        original = sheet_path.read_bytes()
        sheet = json.loads(original)
        sheet["children"][0]["exclusive_resources"].append("repo-file:Assets/Extra.cs")
        sheet_path.write_text(json.dumps(sheet), encoding="utf-8")
        refused(run.verify, "does not hash to the recorded sheet_sha256")
        sheet_path.write_bytes(original)

        changed = deepcopy(run.result)
        changed["designer_bookkeeper"]["bookkeeper_model"] = "fixture-model"
        refused(lambda: run.verify(changed), "on claude at fixture-model")
        changed = deepcopy(run.result)
        changed["designer_bookkeeper"]["attempts"] = changed["designer_bookkeeper"]["attempts"][1:]
        refused(lambda: run.verify(changed), "is not recorded as invocation")

        first = run.run_dir / "rounds" / "01-bookkeeper-1" / "bookkeeping_attempt.json"
        record = json.loads(first.read_text(encoding="utf-8"))
        record["problems"] = []
        first.write_text(json.dumps(record), encoding="utf-8")
        refused(run.verify, "record differs from the run result")
        assert run.verify is not None


def test_the_three_call_chain_accepts_a_bookkeeper_run() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["good"], max_calls=3)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        chain = verify_three_call_chain(
            run_dir=run.run_dir, run_result=run.result, providers=("claude", "codex"),
            candidate_digest=digest_for(run.source), timeouts=TIMEOUTS, parent_contract=run.parent)
        assert chain["bookkeeping"]["attempts"] == 1


def test_a_refused_sheet_gets_one_designer_correction() -> None:
    def overlap(sheet: dict) -> None:
        sheet["children"][0]["exclusive_resources"].append("repo-file:Assets/NotTheParents.cs")
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["good"], sheet_change=overlap, corrected=True)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert run.result["author_corrections_used"] == 1
        assert run.result["designer_bookkeeper"]["sheet_path"] == "rounds/01-correction/ownership_sheet.json"
        correction_prompt = run.claude.requests[1].prompt
        assert "CORRECTION: your previous ownership sheet was refused" in correction_prompt
        assert "exactly partition" in correction_prompt and "NotTheParents.cs" in correction_prompt
        run.verify(author_index=1)


def test_the_three_call_chain_accepts_a_corrected_designer() -> None:
    def outside(sheet: dict) -> None:
        sheet["children"][0]["exclusive_resources"].append("repo-file:Assets/NotTheParents.cs")
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["good"], max_calls=3, sheet_change=outside, corrected=True)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        chain = verify_three_call_chain(
            run_dir=run.run_dir, run_result=run.result, providers=("claude", "codex"),
            candidate_digest=digest_for(run.source), timeouts=TIMEOUTS, parent_contract=run.parent)
        assert chain["author_corrections_used"] == 1 and chain["bookkeeping"]["attempts"] == 1


TESTS = (
    test_the_three_call_chain_accepts_a_corrected_designer,
    test_a_refused_sheet_gets_one_designer_correction,
    test_a_conforming_bookkeeper_reaches_the_independent_review,
    test_a_structural_slip_is_corrected_by_the_skeleton_without_a_retry,
    test_designer_notes_survive_a_bookkeeper_that_drops_them,
    test_one_prose_slip_is_retried_with_its_problems,
    test_two_slips_stop_the_run_without_a_result,
    test_a_sheet_refused_twice_stops_before_any_bookkeeping,
    test_tampered_bookkeeping_evidence_is_refused,
    test_the_three_call_chain_accepts_a_bookkeeper_run,
)

if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition designer/bookkeeper smoke tests: PASS ({len(TESTS)} tests)")
