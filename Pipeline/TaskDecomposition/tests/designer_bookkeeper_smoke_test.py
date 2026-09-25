"""The opt-in designer/bookkeeper split of the D1B.2 author round.

Real engine runs with test providers that report production identities. The
designer returns an ownership sheet; the bookkeeper, on the designer's
provider at its own model, writes the result; reviewers revise ownership sheets.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.json_values import thaw_json  # noqa: E402
from TaskDecomposition.bookkeeper_context import cited_gdd_lines, compact_bookkeeper_context, gdd_excerpt  # noqa: E402
from TaskDecomposition.bookkeeping_evidence import BookkeepingEvidenceError, verify_bookkeeping  # noqa: E402
from TaskDecomposition.bookkeeping_skeleton import impose_skeleton, result_skeleton  # noqa: E402
from TaskDecomposition.ownership_sheet import sheet_from_result, sheet_sha256  # noqa: E402
from TaskDecomposition.review_chain import ReviewChainError, verify_three_call_chain  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    _round_directory_name,
    _round_invocation_id,
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.review_chain_smoke_test import TIMEOUTS, digest_for, factory  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result
from TaskDecomposition.continuation import continuable_problem, run_continuation
from TaskDecomposition.context_builder import ContextPackage, DecompositionPreflightError
from TaskDecomposition.review_contracts import DecompositionReviewContractError, OwnershipSheetReviewResult
from TaskDecomposition.review_policy import DecompositionReviewPolicyError, validate_ownership_sheet_review
from TaskDecomposition.review_schemas import OWNERSHIP_SHEET_REVIEW_SCHEMA
from TaskDecomposition.run_diagnosis import expected_invocation_id  # noqa: E402

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
        self.codex = QueueProvider([sheet_review(good_hash, self.sheet)])
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



def sheet_review(candidate_hash: str, sheet: dict, *, revised: dict | None = None,
                 round_number: int = 2, verdict: str = "pass", resolutions=()) -> dict:
    review = pass_review(candidate_hash, resolutions=resolutions)
    review.update(schema_version="1.1", reviewed_sheet_sha256=sheet_sha256(sheet),
                  verdict=verdict, revised_sheet=revised)
    del review["revised_decomposition"]
    if verdict != "pass":
        review["findings"] = [{
            "finding_id": f"round-{round_number:02d}-prose", "severity": "blocking",
            "category": "candidate_correctness", "affected_contracts": ["NSC-010"],
            "problem": "The child's notes do not explain its prefab check.",
            "required_resolution": "State the child's prefab check in its notes.",
        }]
    return review


class RevisionRun:
    def __init__(self, base: Path, *, attempts: tuple[str, ...] = ("good",),
                 same_sheet: bool = False, refused_sheet: bool = False,
                 initial_correction: bool = False, identical: bool = False,
                 revisions: int = 1, max_calls: int = 3, terminal: str = "pass") -> None:
        self.source = base / "source"
        self.tasks = create_repository(self.source)
        self.parent = self.tasks["NSC-010"]
        good = decomposed_result(self.parent)
        self.sheet = sheet_from_result(good)
        self.sheets = [self.sheet]
        initial = impose_skeleton(result_skeleton(self.sheet), good)
        self.candidates = [initial]
        self.hashes = [candidate_sha256(validated_candidate(initial, self.parent, self.tasks))]
        outputs: dict[str, list[Any]] = {"claude": [], "codex": []}
        if initial_correction:
            invalid = deepcopy(self.sheet)
            invalid["children"][0]["exclusive_resources"].append("repo-file:Assets/Outside.cs")
            outputs["claude"].append(invalid)
        outputs["claude"].extend([self.sheet, good])
        resolutions = []
        for index in range(revisions):
            round_number = index + 2
            reviewer = ("claude", "codex")[(round_number - 1) % 2]
            sheet = deepcopy(self.sheets[-1])
            if not same_sheet and not identical:
                sheet["children"][0]["purpose"] += f" Revised prefab check {index + 1}."
            if refused_sheet:
                sheet["children"][0]["exclusive_resources"].append("repo-file:Assets/Outside.cs")
            review = sheet_review(self.hashes[-1], self.sheets[-1], revised=sheet,
                                  verdict="revise", round_number=round_number, resolutions=resolutions)
            outputs[reviewer].append(review)
            raw = deepcopy(self.candidates[-1])
            if not identical:
                raw["children"][0]["notes"] += f" Revised prefab prose {index + 1}."
            for kind in attempts:
                outputs["claude"].append(blank_reference(raw) if kind == "prose" else
                                         dropped_entry(raw) if kind == "structural" else deepcopy(raw))
            compiled = impose_skeleton(result_skeleton(sheet), raw)
            self.candidates.append(compiled)
            self.hashes.append(self.hashes[-1] if refused_sheet else
                               candidate_sha256(validated_candidate(compiled, self.parent, self.tasks)))
            self.sheets.append(sheet)
            resolutions = [{"finding_id": f"round-{round_number:02d}-prose",
                            "status": "resolved", "explanation": "The prefab check is explicit."}]
        last_round = revisions + 2
        reviewer = ("claude", "codex")[(last_round - 1) % 2]
        outputs[reviewer].append(sheet_review(self.hashes[-1], self.sheets[-1],
                                             round_number=last_round, verdict=terminal,
                                             resolutions=resolutions))
        self.providers = {name: QueueProvider(items) for name, items in outputs.items()}
        self.run_id = "revision-run"
        self.result = run_round_robin_decomposition(
            source=self.source, output_root=base / "output", task_id="NSC-010",
            provider_order=("claude", "codex"), max_calls=max_calls, run_id=self.run_id,
            provider_factory=factory(self.providers), _require_physical_read_only_source=False,
            bookkeeper_model=BOOKKEEPER_MODEL,
        )
        self.run_dir = base / "output" / self.run_id

    @property
    def compilations(self) -> list[dict]:
        return self.result["designer_bookkeeper"]["compilations"]

    def verify(self, run_result: dict | None = None) -> dict:
        return verify_three_call_chain(
            run_dir=self.run_dir, run_result=run_result or self.result,
            providers=("claude", "codex"), candidate_digest=digest_for(self.source),
            timeouts=TIMEOUTS, parent_contract=self.parent,
        )


def refused(action: Callable[[], Any], text: str) -> None:
    try:
        action()
    except (BookkeepingEvidenceError, ReviewChainError, DecompositionReviewContractError,
            DecompositionReviewPolicyError) as exc:
        assert text in str(exc), f"expected {text!r}, got {exc}"
    else:
        raise AssertionError(f"expected a refusal mentioning {text!r}")


def test_a_conforming_bookkeeper_reaches_the_independent_review() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["good"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert run.result["calls_used"] == 2 and run.result["author_corrections_used"] == 0
        record = run.result["designer_bookkeeper"]
        assert record["bookkeeper_model"] == BOOKKEEPER_MODEL and len(record["compilations"][0]["attempts"]) == 1
        assert record["compilations"][0]["attempts"][0]["actual_model"] == BOOKKEEPER_MODEL
        assert run.result["rounds"][0]["actual_model"] == "fixture-model"
        designer_prompt = run.claude.requests[0].prompt
        bookkeeper_prompt = run.claude.requests[1].prompt
        assert "DESIGN MODE" in designer_prompt and "BOOKKEEPING MODE" in bookkeeper_prompt
        # The designer reads the whole committed context; the bookkeeper a reduced copy of it.
        for marker in ("full_committed_utf8_text", "\"graph_neighborhood\"", "sibling_contracts"):
            assert marker in designer_prompt and marker not in bookkeeper_prompt, marker
        for marker in ("canonical_gdd_excerpt", "graph_neighborhood_summary", "task_catalog"):
            assert marker in bookkeeper_prompt, marker
        verified = run.verify()
        assert verified["attempts"] == 1 and verified["conformed"]
        assert "rounds/01/ownership_sheet.json" in verified["evidence_sha256"]


def test_a_structural_slip_is_corrected_by_the_skeleton_without_a_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["structural"])
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        attempts = run.result["designer_bookkeeper"]["compilations"][0]["attempts"]
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
        attempts = run.result["designer_bookkeeper"]["compilations"][0]["attempts"]
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
        assert run.result["author_corrections_used"] == 1 and not run.result["designer_bookkeeper"]["compilations"]
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
        refused(lambda: run.verify(changed), "pinned bookkeeper provider/model differs")
        changed = deepcopy(run.result)
        changed["designer_bookkeeper"]["compilations"][0]["attempts"] = changed["designer_bookkeeper"]["compilations"][0]["attempts"][1:]
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
        assert run.result["designer_bookkeeper"]["compilations"][0]["sheet_path"] == "rounds/01-correction/ownership_sheet.json"
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


def test_the_bookkeeper_gets_only_the_cited_gdd_lines() -> None:
    path = "Docs/GDD/No_Safe_Circle_GDD.md"
    text = "\n".join(["# Title", *[f"line {n}" for n in range(2, 30)], "## Section", "line 31"])
    ranges = cited_gdd_lines([f"see {path}:5-6,20", f"{path}:31", "Docs/Other.md:9"])
    assert ranges == [(5, 6), (20, 20), (31, 31)], ranges
    excerpt = gdd_excerpt(text, ranges)
    lines = excerpt["cited_lines"].splitlines()
    assert lines[0] == "3: line 3" and "8: line 8" in lines and "9: line 9" not in lines
    assert "..." in lines and "22: line 22" in lines and "31: line 31" in lines
    assert excerpt["headings"] == ["1: # Title", "30: ## Section"]
    assert gdd_excerpt(text, [])["cited_lines"] == ""



def test_revision_sheet_is_compiled_before_next_review() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text))
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert len(run.compilations) == 2
        assert run.result["rounds"][2]["candidate_before"]["sha256"] == run.hashes[1]
        assert run.result["designer_bookkeeper"]["latest_sheet"]["round_number"] == 2
        assert OWNERSHIP_SHEET_REVIEW_SCHEMA == thaw_json(run.providers["codex"].requests[0].output_schema)
        run.verify()


def test_revision_bookkeeper_uses_fixed_provider_and_model() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text))
        attempt = run.compilations[1]["attempts"][0]
        assert attempt["requested_provider"] == "claude" and attempt["actual_model"] == BOOKKEEPER_MODEL
        assert run.providers["claude"].calls == 4 and run.providers["codex"].calls == 1
        assert run.result["calls_used"] == 3
        assert run.result["designer_bookkeeper"]["bookkeeping_calls_used"] == 2


def test_revision_candidate_author_is_revising_reviewer() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text))
        latest = run.result["latest_candidate"]
        assert latest["author_provider"] == "codex" and latest["version"] == 2
        assert run.result["independent_approver_provider"] == "claude"
        assert run.compilations[1]["accepted_candidate"] == latest


def test_revision_structural_slip_is_imposed_without_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("structural",))
        attempts = run.compilations[1]["attempts"]
        assert len(attempts) == 1 and attempts[0]["structural_slips_corrected"]
        assert run.result["latest_candidate"]["sha256"] == run.hashes[1]
        run.verify()


def test_revision_prose_slip_gets_exactly_one_retry() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("prose", "good"))
        assert [a["status"] for a in run.compilations[1]["attempts"]] == ["rejected", "conformed"]
        retry = run.providers["claude"].requests[3].prompt
        for marker in ("REVISION RETRY", "Previous full candidate", "Authenticated reviewer output",
                       "Prior unresolved blocking findings", "must be a non-blank string"):
            assert marker in retry, marker
        run.verify()


def test_two_revision_bookkeeping_failures_keep_previous_candidate() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("prose", "prose"))
        assert run.result["run_status"] == "rejected"
        assert run.result["latest_candidate"]["sha256"] == run.hashes[0]
        assert run.compilations[1]["status"] == "compilation_failed"
        assert run.compilations[1]["compiled_candidate"] is None
        assert run.compilations[1]["accepted_candidate"] is None
        assert run.result["designer_bookkeeper"]["latest_sheet"]["round_number"] == 1
        assert run.result["designer_bookkeeper"]["bookkeeping_calls_used"] == 3
        assert run.result["decomposition_result_path"] is None
        assert run.providers["claude"].calls == 4


def test_refused_reviewer_sheet_gets_no_correction_or_bookkeeping() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), refused_sheet=True)
        assert run.result["run_status"] == "rejected"
        assert run.result["author_corrections_used"] == 0 and len(run.compilations) == 1
        assert run.providers["claude"].calls == 2 and run.providers["codex"].calls == 1
        assert run.result["latest_candidate"]["sha256"] == run.hashes[0]
        assert (run.run_dir / "rounds/02/review.json").is_file()
        assert not (run.run_dir / "rounds/02-bookkeeper-1").exists()


def test_initial_correction_then_revision_has_distinct_sheet_origins() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), initial_correction=True)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert [c["sheet_path"] for c in run.compilations] == [
            "rounds/01-correction/ownership_sheet.json", "rounds/02/ownership_sheet.json"]
        assert [c["attempts"][0]["directory"] for c in run.compilations] == [
            "01-bookkeeper-1", "02-bookkeeper-1"]
        assert run.result["author_corrections_used"] == 1
        run.verify()


def test_same_sheet_can_repair_candidate_prose() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), same_sheet=True)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        assert run.compilations[0]["sheet_sha256"] == run.compilations[1]["sheet_sha256"]
        assert run.hashes[0] != run.hashes[1]
        run.verify()


def test_identical_recompiled_candidate_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), identical=True)
        assert run.result["run_status"] == "rejected"
        compilation = run.compilations[1]
        assert compilation["status"] == "identical_candidate"
        assert compilation["compiled_candidate"]["sha256"] == run.hashes[0]
        assert compilation["accepted_candidate"] is None
        assert run.result["latest_candidate"]["version"] == 1
        assert run.result["designer_bookkeeper"]["latest_sheet"]["round_number"] == 1
        assert run.providers["claude"].calls == 3
        assert not (run.run_dir / "rounds/02/candidate.json").exists()


def test_last_call_revision_compiles_then_stops_needs_human() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), max_calls=2)
        assert run.result["run_status"] == "needs_human", run.result["rejection_reasons"]
        assert run.result["latest_candidate"]["sha256"] == run.hashes[1]
        assert run.result["designer_bookkeeper"]["latest_sheet"]["round_number"] == 2
        assert run.compilations[1]["status"] == "candidate_accepted"
        assert run.result["decomposition_result_path"] is None
        assert run.providers["claude"].calls == 3


def test_pass_and_needs_human_do_not_run_bookkeeper() -> None:
    for verdict, status in (("pass", "review_ready"), ("needs_human", "needs_human")):
        with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
            run = RevisionRun(Path(text), revisions=0, max_calls=2, terminal=verdict)
            assert run.result["run_status"] == status, run.result["rejection_reasons"]
            assert len(run.compilations) == 1 and run.providers["claude"].calls == 2
            assert run.result["designer_bookkeeper"]["bookkeeping_calls_used"] == 1
            assert run.result["latest_candidate"]["sha256"] == run.hashes[0]


def test_repeated_revisions_have_unique_attempt_ids_and_directories() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), revisions=2, attempts=("prose", "good"), max_calls=4)
        assert run.result["run_status"] == "review_ready", run.result["rejection_reasons"]
        attempts = [a for c in run.compilations for a in c["attempts"]]
        assert len({a["invocation_id"] for a in attempts}) == 5
        assert len({a["directory"] for a in attempts}) == 5
        for compilation in run.compilations:
            for attempt in compilation["attempts"]:
                number, index = compilation["round_number"], attempt["attempt"]
                expected = _round_invocation_id("NSC-010", run.run_id, number, "decomposition_bookkeeper",
                                                bookkeeping_attempt=index)
                assert expected == expected_invocation_id(
                    "NSC-010", run.run_id, number, "decomposition_bookkeeper",
                    correction=False, bookkeeping_attempt=index)
                assert attempt["invocation_id"] == expected
                assert attempt["directory"] == _round_directory_name(number, bookkeeping_attempt=index)
        run.verify()


def test_revision_context_includes_citations_from_review_feedback() -> None:
    path = "Docs/GDD/No_Safe_Circle_GDD.md"
    context = ContextPackage.from_payload({"selected_task": {"d1a_semantic_parent_identity": {},
                                                           "task_execution_identity": {}},
                                           "canonical_gdd": {
        "full_committed_utf8_text": "\n".join(f"line {n}" for n in range(1, 61)),
        "exact_byte_sha256": "0" * 64}})
    previous = {"children": [{"notes": f"Use {path}:15."}]}
    review = {"findings": [{"required_resolution": f"Cite {path}:40-41."}]}
    compact = compact_bookkeeper_context(context, {}, citation_sources=(previous, review)).to_dict()
    lines = compact["canonical_gdd_excerpt"]["cited_lines"]
    assert "15: line 15" in lines and "40: line 40" in lines and "41: line 41" in lines
    assert "25: line 25" not in lines
    assert compact_bookkeeper_context(context, {}).to_dict()["canonical_gdd_excerpt"]["cited_lines"] == ""
    from TaskDecomposition.bookkeeper_prompts import (
        build_bookkeeper_revision_prompt, build_bookkeeper_revision_retry_prompt,
    )
    sheet = {"schema_version": "1", "rationale": "Split prefab checks.",
             "children": [], "inbound_dependency_rewrites": []}
    inputs = dict(previous_candidate=previous, review=review, unresolved_findings=[])
    prompt = build_bookkeeper_revision_prompt(context, sheet, **inputs)
    retry = build_bookkeeper_revision_retry_prompt(context, sheet, {}, ["Reference is blank"], **inputs)
    for rendered in (prompt, retry):
        assert "15: line 15" in rendered and "40: line 40" in rendered
        assert "Previous full candidate" in rendered and "Authenticated reviewer output" in rendered


def test_sheet_review_schema_and_policy_refuse_invalid_reviews() -> None:
    sheet = {"schema_version": "1", "rationale": "Split prefab checks.",
             "children": [], "inbound_dependency_rewrites": []}
    raw = sheet_review("0" * 64, sheet)

    def validate(value: dict, **overrides):
        arguments = dict(expected_candidate_sha256="0" * 64, expected_sheet_sha256=sheet_sha256(sheet),
                         round_number=2, prior_unresolved_findings={}, all_prior_finding_ids=frozenset())
        arguments.update(overrides)
        return validate_ownership_sheet_review(value, **arguments)

    parsed, unresolved = validate(raw)
    assert parsed.to_dict() == raw and not unresolved
    assert OwnershipSheetReviewResult.from_dict(json.loads(parsed.canonical_json())) == parsed
    invalid = []
    for key, value in (("reviewed_candidate_sha256", "1" * 64), ("reviewed_sheet_sha256", "2" * 64),
                       ("revised_decomposition", None), ("schema_version", "1.0"), ("revised_sheet", sheet)):
        changed = deepcopy(raw)
        changed[key] = value
        invalid.append(changed)
    revise = sheet_review("0" * 64, sheet, verdict="revise", revised=sheet)
    changed = deepcopy(revise)
    changed["revised_sheet"] = None
    invalid.append(changed)
    changed = deepcopy(revise)
    changed["findings"] = []
    invalid.append(changed)
    changed = deepcopy(revise)
    changed["revised_sheet"]["children"] = [{"entries": "malformed"}]
    invalid.append(changed)
    changed = deepcopy(revise)
    changed["verdict"] = "needs_human"
    invalid.append(changed)
    changed = deepcopy(raw)
    changed["verdict"] = "needs_human"
    invalid.append(changed)
    for value in invalid:
        try:
            validate(value)
        except (DecompositionReviewContractError, DecompositionReviewPolicyError):
            pass
        else:
            raise AssertionError(f"invalid review accepted: {value}")
    blocked_pass = deepcopy(raw)
    blocked_pass["findings"] = revise["findings"]
    try:
        validate(blocked_pass)
    except DecompositionReviewPolicyError:
        pass
    else:
        raise AssertionError("PASS introduced a blocking finding")
    result, unresolved = validate(revise)
    finding = result.findings[0]
    for value, overrides in ((revise, {"all_prior_finding_ids": {finding.finding_id}}),
                             (raw, {"prior_unresolved_findings": unresolved})):
        try:
            validate(value, **overrides)
        except DecompositionReviewPolicyError:
            pass
        else:
            raise AssertionError("finding reuse or unresolved finding accepted")
    later = sheet_review("0" * 64, sheet, round_number=3, verdict="revise", revised=sheet,
                         resolutions=[{"finding_id": finding.finding_id, "status": "still_blocking",
                                       "explanation": "The prefab check is still missing."}])
    later["findings"] = []
    assert validate(later, round_number=3, prior_unresolved_findings=unresolved,
                    all_prior_finding_ids={finding.finding_id})[1] == unresolved
    later["verdict"], later["revised_sheet"] = "pass", None
    try:
        validate(later, round_number=3, prior_unresolved_findings=unresolved,
                 all_prior_finding_ids={finding.finding_id})
    except DecompositionReviewPolicyError:
        pass
    else:
        raise AssertionError("PASS accepted a still-blocking finding")


def test_bookkeeper_continuation_protocol_requires_a_fresh_run() -> None:
    candidate = {"sha256": "0" * 64}
    ordinary = {"run_status": "needs_human", "latest_candidate": candidate,
                "rounds": [{"status": "revised_candidate_valid", "candidate_after": candidate}],
                "unresolved_findings": [{"finding_id": "round-02-prefab"}]}
    assert continuable_problem(ordinary) is None
    for metadata in ({"designer_bookkeeper": None}, {"designer_bookkeeper": {"schema_version": "2.0"}},
                     {"designer_bookkeeper": {"attempts": []}}):
        assert "fresh run" in continuable_problem({**ordinary, **metadata})
    for key, value in (("bookkeeper_model", "compiler"), ("bookkeeper_provider", "claude"),
                       ("designer_bookkeeper_version", "2.0"), ("ownership_sheet_review_version", "1.1")):
        assert "fresh run" in continuable_problem(ordinary, request={key: value})


def test_bookkeeper_continuation_is_refused_before_provider_spend() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), max_calls=2)
        called = []
        try:
            run_continuation(
                source=run.source, output_root=run.run_dir.parent, task_id="NSC-010",
                continue_from=run.run_id, provider_order=("claude", "codex"), max_calls=1,
                run_id="must-not-start", provider_factory=lambda *args, **kwargs: called.append(args),
                _require_physical_read_only_source=False,
            )
        except DecompositionPreflightError as exc:
            assert "fresh run" in str(exc), exc
        else:
            raise AssertionError("bookkeeper continuation was admitted")
        assert called == [] and not (run.run_dir.parent / "must-not-start").exists()


def test_compilation_record_tampering_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("prose", "good"))
        run.verify()
        mutations = [
            lambda r: r["designer_bookkeeper"]["compilations"].pop(),
            lambda r: r["designer_bookkeeper"]["compilations"].append(deepcopy(r["designer_bookkeeper"]["compilations"][1])),
            lambda r: r["designer_bookkeeper"]["compilations"].reverse(),
            lambda r: r["designer_bookkeeper"].update(bookkeeping_calls_used=1),
            lambda r: r["designer_bookkeeper"].update(bookkeeper_provider="codex"),
            lambda r: r["designer_bookkeeper"].update(bookkeeper_model="another-model"),
            lambda r: r["designer_bookkeeper"].pop("schema_version"),
            lambda r: r.pop("designer_bookkeeper"),
            lambda r: r["designer_bookkeeper"]["latest_sheet"].update(round_number=1),
        ]
        for field, value in (("sheet_path", "rounds/01/ownership_sheet.json"),
                             ("source_directory", "01"), ("source_invocation_id", "other"),
                             ("source_role", "task_decomposer"), ("source_output_field", None),
                             ("sheet_sha256", "0" * 64), ("status", "identical_candidate")):
            mutations.append(lambda r, field=field, value=value:
                             r["designer_bookkeeper"]["compilations"][1].update({field: value}))
        for field, value in (("version", 3), ("author_provider", "claude"), ("sha256", "0" * 64),
                             ("graph_delta_plan_id", "another-plan")):
            mutations.append(lambda r, field=field, value=value:
                             r["designer_bookkeeper"]["compilations"][1]["accepted_candidate"].update({field: value}))
        for mutate in mutations:
            changed = deepcopy(run.result)
            mutate(changed)
            refused(lambda: run.verify(changed), "")
        for mutate in (lambda a: a.reverse(), lambda a: a.append(deepcopy(a[-1])),
                       lambda a: a[0].update(attempt=2), lambda a: a[0].update(status="conformed"),
                       lambda a: a[0].update(agent_runtime_result_path="rounds/01/other.json")):
            changed = deepcopy(run.result)
            mutate(changed["designer_bookkeeper"]["compilations"][1]["attempts"])
            refused(lambda: run.verify(changed), "")


def test_compilation_file_tampering_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("prose", "good"))
        attempt = run.compilations[1]["attempts"][0]
        base = f"rounds/{attempt['directory']}/agent_runtime/{attempt['invocation_id']}"
        second = run.compilations[1]["attempts"][1]
        retry = f"rounds/{second['directory']}/agent_runtime/{second['invocation_id']}/request.json"
        review_base = f"rounds/02/agent_runtime/{run.compilations[1]['source_invocation_id']}"
        mutations = [
            ("rounds/02/ownership_sheet.json", lambda r: r.update(rationale="Tampered sheet")),
            ("rounds/02/bookkeeping_input.json", lambda r: r["revision_input"]["review"].update(summary="Changed")),
            (f"{base}/request.json", lambda r: r.update(prompt=r["prompt"] + " changed")),
            (retry, lambda r: r.update(prompt=r["prompt"].replace("REVISION RETRY", "changed"))),
            (f"{base}/request.json", lambda r: r["budgets"].update(timeout_seconds=1)),
            (f"{base}/request.json", lambda r: r.update(role="task_decomposer")),
            (f"{base}/result.json", lambda r: r.update(provider="openai-codex")),
            (f"{base}/result.json", lambda r: r.update(model="another-model")),
            (f"{review_base}/result.json", lambda r: r["structured_output"]["revised_sheet"].update(rationale="Changed")),
            ("rounds/02/candidate.json", lambda r: r["children"][0].update(notes="Changed")),
            ("rounds/02/candidate_graph_delta.json",
             lambda r: r["parent_after_summary"].update(contract_revision=999)),
            ("rounds/02/candidate_graph_delta.json",
             lambda r: r["proposed_child_contracts"][0].update(title="Changed")),
            ("rounds/02/candidate_graph_delta.json",
             lambda r: r["proposed_graph_overlay"]["tasks"][0].update(title="Changed")),
            ("rounds/02/candidate_graph_delta.json",
             lambda r: r["proposed_graph_overlay"]["resource_groups"][0].update(work_ids=[])),
            ("rounds/03/review.json", lambda r: r.update(revised_sheet=run.sheets[0])),
            ("rounds/03/review.json", lambda r: r.update(reviewed_candidate_sha256=run.hashes[0])),
            ("decomposition_request.json", lambda r: r.pop("ownership_sheet_review_version")),
            ("decomposition_request.json", lambda r: r.update(designer_bookkeeper_version="1.0")),
        ]
        for relative, change in mutations:
            path = run.run_dir / relative
            original = path.read_bytes()
            changed = json.loads(original)
            change(changed)
            path.write_text(json.dumps(changed), encoding="utf-8")
            try:
                refused(run.verify, "")
            finally:
                path.write_bytes(original)
        run.verify()


def test_legacy_round_one_bookkeeping_evidence_remains_readable() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = Run(Path(text), ["prose", "good"])
        result = deepcopy(run.result)
        compilation = result["designer_bookkeeper"]["compilations"][0]
        result["designer_bookkeeper"] = {"bookkeeper_model": BOOKKEEPER_MODEL,
                                        "sheet_path": compilation["sheet_path"],
                                        "sheet_sha256": compilation["sheet_sha256"],
                                        "attempts": compilation["attempts"]}
        request_path = run.run_dir / "decomposition_request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        for key in ("designer_bookkeeper_version", "ownership_sheet_review_version", "bookkeeper_provider"):
            request.pop(key)
        request_path.write_text(json.dumps(request), encoding="utf-8")
        assert run.verify(result)["attempts"] == 2



def _non_bookkeeper_bytes() -> dict[str, str]:
    from TaskDecomposition.context_builder import SourceIdentity
    from TaskDecomposition.contracts import DecompositionResult
    from TaskDecomposition.prompts import build_decomposer_prompt
    from TaskDecomposition.review_contracts import DecompositionReviewResult
    from TaskDecomposition.review_prompts import build_decomposition_reviewer_prompt
    from TaskDecomposition.review_schemas import DECOMPOSITION_REVIEW_SCHEMA
    from TaskDecomposition.round_robin_decomposition import (
        CandidateSnapshot, _json, _round_request, _round_summary, _run_request,
    )
    from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA
    from TaskDecomposition.tests.test_support import parent_identity, task

    parent = task("NSC-010", "selected-parent", "implementation", "NSC-002",
                  "needs_execution_decomposition", "concrete", dependencies=("NSC-003",),
                  resources=("repo-file:Assets/Shared.cs", "unity-scene:Assets/Synthetic.unity"))
    context = ContextPackage.from_payload({"selected_task": {
        "contract": parent, "task_execution_identity": {"path": "Tasks/NSC-010.json",
                                                        "revision": 2, "sha256": "1" * 64},
        "d1a_semantic_parent_identity": parent_identity(parent)}})
    candidate = DecompositionResult.from_dict(decomposed_result(parent))
    snapshot = CandidateSnapshot(1, "codex", candidate, None, candidate_sha256(candidate))
    request = _round_request(round_number=2, role="decomposition_reviewer", provider="claude",
                             invocation_id="fixed-invocation", candidate=snapshot, unresolved_findings={})
    summary = _round_summary(
        run_dir=Path(__file__).parent / "absent-golden-run", round_directory="02", round_number=2,
        role="decomposition_reviewer", provider="claude", invocation_id="fixed-invocation",
        agent_result=None, duration_seconds=2.0, candidate_before=snapshot, unresolved_findings={})
    return {
        "author_prompt": build_decomposer_prompt(context),
        "review_prompt": build_decomposition_reviewer_prompt(
            context=context, candidate=candidate, candidate_sha256=snapshot.sha256,
            candidate_author_provider="codex", reviewer_provider="claude", round_number=2,
            graph_delta=None, review_history=[], unresolved_findings=[]),
        "author_schema": _json(DECOMPOSITION_RESULT_SCHEMA),
        "review_schema": _json(DECOMPOSITION_REVIEW_SCHEMA),
        "run_request": _json(_run_request(
            run_id="fixed-run", task_id="NSC-010", provider_order=("codex", "claude"), max_calls=3,
            source=SourceIdentity(Path("unused"), "2" * 40, "3" * 40, "fixture"), context=context)),
        "round_request": _json(request),
        "round_result": _json(summary),
        "review": _json(DecompositionReviewResult.from_dict(pass_review(snapshot.sha256)).to_dict()),
        "candidate_artifact": _json(candidate.to_dict()),
    }


def test_non_bookkeeper_bytes_match_legacy_goldens() -> None:
    expected = {
        "author_prompt": "f8d1b355954366768cb709045f20027c037a410fc7e79119c94ec267dbe55456",
        "review_prompt": "ba082b37745fb481536c2d11248ff8ec53d086d1dfa0dfc349c27f367eb765ff",
        "author_schema": "23258e412a1ef64ad6f75b3b25f797d2ee4b2c5fa5ab83f546d0d7910957db07",
        "review_schema": "9860f0f97c951ea20d9d8491141bc5c6610ed19229eabb341fabd90205ebd364",
        "run_request": "76b2a424613f6e9baedfff206d296a76ea06a316ef5fa591abc664f735f35a18",
        "round_request": "14172286eb24183e3c68f9187ebd9c279e13cf104506dfb36db3db8e3b2368d0",
        "round_result": "98f1326c10d1775af134846778e7b54300255055c56f63c231dce20663583069",
        "review": "bb9fd022f250a3ce5ae101cec928a46b91a01cf9e66a2f50da88df218c16a69a",
        "candidate_artifact": "d24d6ad193624a2d9f3932767e804c2d76db42b2479efd6fec795f2e95a94922",
    }
    actual = {name: hashlib.sha256(value.encode("utf-8")).hexdigest()
              for name, value in _non_bookkeeper_bytes().items()}
    assert actual == expected, actual



def test_rejected_attempt_cannot_be_relabelled_successful() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-bk-") as text:
        run = RevisionRun(Path(text), attempts=("prose", "good"))
        changed = deepcopy(run.result)
        attempt = changed["designer_bookkeeper"]["compilations"][1]["attempts"][0]
        attempt["status"] = "conformed"
        path = run.run_dir / "rounds" / attempt["directory"] / "bookkeeping_attempt.json"
        path.write_text(json.dumps(attempt), encoding="utf-8")
        refused(lambda: run.verify(changed), "failed deterministic replay")


TESTS = (
    test_bookkeeper_continuation_protocol_requires_a_fresh_run,
    test_non_bookkeeper_bytes_match_legacy_goldens,
    test_revision_context_includes_citations_from_review_feedback,
    test_sheet_review_schema_and_policy_refuse_invalid_reviews,
    test_the_bookkeeper_gets_only_the_cited_gdd_lines,
    test_rejected_attempt_cannot_be_relabelled_successful,
    test_revision_sheet_is_compiled_before_next_review,
    test_revision_bookkeeper_uses_fixed_provider_and_model,
    test_revision_candidate_author_is_revising_reviewer,
    test_revision_structural_slip_is_imposed_without_retry,
    test_revision_prose_slip_gets_exactly_one_retry,
    test_two_revision_bookkeeping_failures_keep_previous_candidate,
    test_refused_reviewer_sheet_gets_no_correction_or_bookkeeping,
    test_initial_correction_then_revision_has_distinct_sheet_origins,
    test_same_sheet_can_repair_candidate_prose,
    test_identical_recompiled_candidate_is_refused,
    test_last_call_revision_compiles_then_stops_needs_human,
    test_pass_and_needs_human_do_not_run_bookkeeper,
    test_repeated_revisions_have_unique_attempt_ids_and_directories,
    test_bookkeeper_continuation_is_refused_before_provider_spend,
    test_compilation_record_tampering_is_refused,
    test_compilation_file_tampering_is_refused,
    test_legacy_round_one_bookkeeping_evidence_remains_readable,
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
