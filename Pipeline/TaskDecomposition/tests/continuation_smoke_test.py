"""Continuing a stopped D1B.2 run from its last revised candidate.

Real engine runs with production-identity test providers: a three-call run
that stops right after a revision, then continuation runs that review the
same candidate further, verified end to end from retained bytes.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.json_values import thaw_json  # noqa: E402
from TaskDecomposition.context_builder import DecompositionPreflightError  # noqa: E402
from TaskDecomposition.continuation import continuable_problem, run_continuation  # noqa: E402
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

from TaskDecomposition.tests.designer_bookkeeper_smoke_test import (  # noqa: E402
    BOOKKEEPER_MODEL, RevisionRun, blank_reference, retain_unmarked_v2, sheet_review,
)
from TaskDecomposition.bookkeeping_skeleton import impose_skeleton, result_skeleton  # noqa: E402
from TaskDecomposition.review_schemas import OWNERSHIP_SHEET_REVIEW_SCHEMA  # noqa: E402

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


class BookkeeperChain:
    """Pure/component regression fixture; all contracts and evidence are disposable."""

    def __init__(self, base: Path, *, author_checklist: str | None = None) -> None:
        self.initial = RevisionRun(base, revisions=2, max_calls=3, author_checklist=author_checklist)
        self.source, self.parent = self.initial.source, self.initial.parent
        self.output = self.initial.run_dir.parent
        self.prior = self.initial.result
        self.run_id = self.initial.run_id
        self.sheet = self.initial.sheets[-1]
        self.candidate = self.initial.candidates[-1]
        self.sha256 = self.initial.hashes[-1]
        self.providers = {}

    def revision(self, *, number: int = 4, candidate=None, sheet=None, identical=False):
        candidate = candidate or self.candidate
        sheet = sheet or self.sheet
        revised_sheet = deepcopy(sheet)
        raw = deepcopy(candidate)
        if not identical:
            revised_sheet["children"][0]["purpose"] += f" Continued prefab check {number}."
            raw["children"][0]["notes"] += f" Continued prefab notes {number}."
        compiled = impose_skeleton(result_skeleton(revised_sheet), raw)
        digest = candidate_sha256(validated_candidate(candidate, self.parent, self.initial.tasks))
        compiled_digest = candidate_sha256(validated_candidate(compiled, self.parent, self.initial.tasks))
        review = sheet_review(digest, sheet, revised=revised_sheet, round_number=number,
                              verdict="revise", resolutions=resolved(f"round-{number - 1:02d}-prose"))
        return review, raw, revised_sheet, compiled, compiled_digest

    def continue_with(self, run_id: str, outputs: dict[str, list[Any]], *, prior_id=None, max_calls=4):
        self.providers = {name: QueueProvider(outputs.get(name, [])) for name in ORDER}
        return run_continuation(
            source=self.source, output_root=self.output, task_id="NSC-010", continue_from=prior_id or self.run_id,
            provider_order=ORDER, max_calls=max_calls, run_id=run_id, provider_factory=factory(self.providers),
            _require_physical_read_only_source=False)

    def verify_prior(self):
        return verify_three_call_chain(
            run_dir=self.output / self.run_id, run_result=self.prior, providers=ORDER,
            candidate_digest=digest_for(self.source), timeouts=TIMEOUTS, parent_contract=self.parent, open_end=True)

    def verify(self, run_id, result, *, prior=None, prior_id=None, open_end=False, timeouts=TIMEOUTS):
        prior_id = prior_id or self.run_id
        return verify_continuation_chain(
            run_dir=self.output / run_id, run_result=result, prior=prior or self.verify_prior(),
            prior_run_result_sha256=hashlib.sha256(
                (self.output / prior_id / "decomposition_run_result.json").read_bytes()).hexdigest(),
            providers=ORDER, candidate_digest=digest_for(self.source), timeouts=timeouts,
            parent_contract=self.parent, open_end=open_end)


def test_bookkeeper_round_three_continues_to_round_four_pass_without_compilation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        assert continuable_problem(chain.prior) is None
        result = chain.continue_with("sheet-pass", {"codex": [sheet_review(
            chain.sha256, chain.sheet, round_number=4, resolutions=resolved("round-03-prose"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert [entry["round_number"] for entry in result["rounds"]] == [4]
        assert result["independent_approver_provider"] == "codex"
        metadata = result["designer_bookkeeper"]
        assert metadata["compilations"] == [] and metadata["bookkeeping_calls_used"] == 0
        assert metadata["latest_sheet"] == chain.prior["designer_bookkeeper"]["latest_sheet"]
        assert result["continued_from"]["seed_sheet"] == metadata["latest_sheet"]
        assert chain.providers["claude"].calls == 0
        assert thaw_json(chain.providers["codex"].requests[0].output_schema) == OWNERSHIP_SHEET_REVIEW_SCHEMA
        chain.verify("sheet-pass", result)


def test_bookkeeper_continued_revision_uses_pinned_configuration_then_other_provider_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        review, raw, revised_sheet, _, digest = chain.revision()
        with patch.dict(os.environ, {"NSC_TASK_DECOMPOSER_TIMEOUT_SECONDS": "7",
                                     "NSC_DECOMPOSITION_REVIEWER_TIMEOUT_SECONDS": "9"}):
            result = chain.continue_with("sheet-revise", {
                "codex": [review], "claude": [raw, sheet_review(
                    digest, revised_sheet, round_number=5, resolutions=resolved("round-04-prose"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert result["latest_candidate"]["author_provider"] == "codex"
        assert result["latest_candidate"]["version"] == chain.prior["latest_candidate"]["version"] + 1
        assert result["independent_approver_provider"] == "claude"
        record = result["designer_bookkeeper"]
        assert record["bookkeeper_provider"] == "claude" and record["bookkeeper_model"] == BOOKKEEPER_MODEL
        assert record["bookkeeping_calls_used"] == 1
        assert record["notes_rule"] == chain.prior["designer_bookkeeper"]["notes_rule"] == "additions-1"
        attempt = record["compilations"][0]["attempts"][0]
        assert attempt["actual_model"] == BOOKKEEPER_MODEL and attempt["requested_provider"] == "claude"
        request = json.loads((chain.output / "sheet-revise" / "decomposition_request.json").read_text())
        assert request["notes_rule"] == record["notes_rule"]
        assert request["author_timeout_seconds"] == TIMEOUTS["task_decomposer"]
        assert request["reviewer_timeout_seconds"] == TIMEOUTS["decomposition_reviewer"]
        assert chain.providers["claude"].requests[0].budgets.timeout_seconds == TIMEOUTS["task_decomposer"]
        assert chain.providers["codex"].requests[0].budgets.timeout_seconds == TIMEOUTS["decomposition_reviewer"]
        chain.verify("sheet-revise", result)


def test_bookkeeper_continuation_of_continuation_keeps_sheet_and_finding_history() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        review, raw, revised_sheet, _, digest = chain.revision()
        first = chain.continue_with("sheet-first", {"codex": [review], "claude": [raw]}, max_calls=1)
        assert first["run_status"] == "needs_human" and first["calls_used"] == 1
        assert any("call limit ended immediately after a revision" in value for value in first["rejection_reasons"])
        assert not (chain.output / "sheet-first" / "decomposition_result.json").exists()
        second = chain.continue_with("sheet-second", {"claude": [sheet_review(
            digest, revised_sheet, round_number=5, resolutions=resolved("round-04-prose"))]}, prior_id="sheet-first")
        assert second["run_status"] == "review_ready", second["rejection_reasons"]
        assert second["continued_from"]["seed_sheet"] == first["designer_bookkeeper"]["latest_sheet"]
        assert second["rounds"][0]["round_number"] == 5
        proof = chain.verify("sheet-first", first, open_end=True)
        chain.verify("sheet-second", second, prior=proof, prior_id="sheet-first")


def test_bookkeeper_failed_and_identical_continuation_compilations_keep_accepted_seed() -> None:
    for identical in (False, True):
        with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
            chain = BookkeeperChain(Path(text))
            review, raw, _, _, _ = chain.revision(identical=identical)
            attempts = [raw] if identical else [blank_reference(raw), blank_reference(raw)]
            result = chain.continue_with("sheet-refused", {"codex": [review], "claude": attempts})
            assert result["run_status"] == "rejected", result["rejection_reasons"]
            assert result["latest_candidate"] == chain.prior["latest_candidate"]
            assert result["unresolved_findings"] == chain.prior["unresolved_findings"]
            assert result["open_blocking_counts"] == [1]
            metadata = result["designer_bookkeeper"]
            assert metadata["latest_sheet"] == chain.prior["designer_bookkeeper"]["latest_sheet"]
            assert metadata["compilations"][0]["accepted_candidate"] is None
            assert metadata["compilations"][0]["status"] == (
                "identical_candidate" if identical else "compilation_failed")
            assert metadata["bookkeeping_calls_used"] == (1 if identical else 2)
            assert not (chain.output / "sheet-refused" / "decomposition_result.json").exists()


def test_bookkeeper_two_accepted_continuation_revisions_stop_non_convergence() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        review4, raw4, sheet4, candidate4, _ = chain.revision()
        review5, raw5, _, _, _ = chain.revision(number=5, candidate=candidate4, sheet=sheet4)
        result = chain.continue_with("sheet-stall", {"codex": [review4], "claude": [raw4, review5, raw5]})
        assert result["run_status"] == "needs_human" and result["calls_used"] == 2
        assert result["open_blocking_counts"] == [1, 1, 1]
        assert len(result["designer_bookkeeper"]["compilations"]) == 2
        assert any("not converging" in value for value in result["rejection_reasons"])
        chain.verify("sheet-stall", result, open_end=True)


def test_bookkeeper_seed_sheet_and_configuration_tampering_stop_before_provider_spend() -> None:
    for kind in ("sheet", "configuration", "compilation", "finding_history"):
        with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
            chain = BookkeeperChain(Path(text))
            if kind == "sheet":
                path = chain.initial.run_dir / chain.prior["designer_bookkeeper"]["latest_sheet"]["sheet_path"]
                payload = json.loads(path.read_text())
                payload["children"][0]["purpose"] += " Tampered prefab."
            elif kind == "configuration":
                path = chain.initial.run_dir / "decomposition_request.json"
                payload = json.loads(path.read_text())
                payload["author_timeout_seconds"] += 1
            elif kind == "compilation":
                path = chain.initial.run_dir / "rounds/03/bookkeeping_input.json"
                payload = json.loads(path.read_text())
                payload["revision_input"]["review"]["summary"] += " Tampered feedback."
            else:
                path = chain.initial.run_dir / "decomposition_run_result.json"
                payload = json.loads(path.read_text())
                payload["finding_history"][-1]["summary"] += " Unauthenticated inherited review instructions."
                history_path = chain.initial.run_dir / "rounds/03/review_history_entry.json"
                history = json.loads(history_path.read_text())
                history["summary"] = payload["finding_history"][-1]["summary"]
                history_path.write_text(json.dumps(history), encoding="utf-8")
            path.write_text(json.dumps(payload), encoding="utf-8")
            calls = []
            try:
                run_continuation(source=chain.source, output_root=chain.output, task_id="NSC-010",
                                 continue_from=chain.run_id, provider_order=ORDER, max_calls=1,
                                 run_id="must-not-start", provider_factory=lambda *a, **kw: calls.append(a),
                                 _require_physical_read_only_source=False)
            except DecompositionPreflightError:
                pass
            else:
                raise AssertionError(f"tampered {kind} seed was admitted")
            assert not calls and not (chain.output / "must-not-start").exists()


def test_bookkeeper_continuation_verifier_refuses_changed_seed_sheet_and_settings() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        result = chain.continue_with("sheet-pass", {"codex": [sheet_review(
            chain.sha256, chain.sheet, round_number=4, resolutions=resolved("round-03-prose"))]})
        for kind in ("seed_sheet", "model", "request_timeout", "coherent_model", "coherent_timeout"):
            altered = deepcopy(result)
            request_path = chain.output / "sheet-pass/decomposition_request.json"
            request_bytes = request_path.read_bytes()
            if kind == "seed_sheet":
                altered["continued_from"]["seed_sheet"]["sheet_sha256"] = "0" * 64
            elif kind in ("model", "coherent_model"):
                altered["designer_bookkeeper"]["bookkeeper_model"] = "other-model"
                if kind == "coherent_model":
                    request = json.loads(request_bytes)
                    request["bookkeeper_model"] = "other-model"
                    request_path.write_text(json.dumps(request), encoding="utf-8")
            else:
                request = json.loads(request_bytes)
                timeout_key = "author_timeout_seconds" if kind == "coherent_timeout" else "reviewer_timeout_seconds"
                request[timeout_key] += 1
                request_path.write_text(json.dumps(request), encoding="utf-8")
            try:
                chain.verify("sheet-pass", altered, timeouts=None if kind.startswith("coherent_") else TIMEOUTS)
            except ReviewChainError:
                pass
            else:
                raise AssertionError(f"continuation accepted changed {kind}")
            finally:
                request_path.write_bytes(request_bytes)


def test_bookkeeper_checklist_is_inherited_and_marker_tampering_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text), author_checklist="parent-contract-v1")
        result = chain.continue_with("checklist-pass", {"codex": [sheet_review(
            chain.sha256, chain.sheet, round_number=4, resolutions=resolved("round-03-prose"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert result["author_checklist"] == "parent-contract-v1"
        assert "BEGIN AUTHOR CHECKLIST parent-contract-v1" in chain.providers["codex"].requests[0].prompt
        context = json.loads((chain.output / "checklist-pass/context.json").read_text())
        assert context["author_checklist"]["version"] == "parent-contract-v1"
        chain.verify("checklist-pass", result)
        for marker in (None, "other-checklist"):
            altered = deepcopy(result)
            if marker is None:
                del altered["author_checklist"]
            else:
                altered["author_checklist"] = marker
            try:
                chain.verify("checklist-pass", altered)
            except ReviewChainError as exc:
                assert "checklist" in str(exc), exc
            else:
                raise AssertionError("continuation accepted a changed author checklist marker")
        # Removing only the prior result marker cannot erase its retained checklist.
        prior = deepcopy(chain.prior)
        del prior["author_checklist"]
        (chain.initial.run_dir / "decomposition_run_result.json").write_text(json.dumps(prior), encoding="utf-8")
        calls = []
        try:
            run_continuation(source=chain.source, output_root=chain.output, task_id="NSC-010",
                             continue_from=chain.run_id, provider_order=ORDER, max_calls=1,
                             run_id="must-not-start", provider_factory=lambda *a, **kw: calls.append(a),
                             _require_physical_read_only_source=False)
        except DecompositionPreflightError as exc:
            assert "checklist" in str(exc), exc
        else:
            raise AssertionError("a stopped run with its checklist marker removed was admitted")
        assert not calls and not (chain.output / "must-not-start").exists()


def test_notes_rule_eligibility_preserves_absence_and_refuses_mismatch() -> None:
    """Pure/component regression: no files, Unity assets, or provider calls."""
    candidate = {"sha256": "a" * 64}
    metadata = {"schema_version": "2.0", "bookkeeper_provider": "claude", "bookkeeper_model": "fixture",
                "compilations": [{"round_number": 3, "status": "candidate_accepted",
                                  "accepted_candidate": candidate}],
                "latest_sheet": {"candidate_sha256": candidate["sha256"]}}
    prior = {"designer_bookkeeper": metadata, "run_status": "needs_human", "latest_candidate": candidate,
             "rounds": [{"round_number": 3, "status": "revised_candidate_valid", "candidate_after": candidate}],
             "unresolved_findings": [{"finding_id": "round-03-prose"}]}
    request = {"designer_bookkeeper_version": "2.0", "ownership_sheet_review_version": "1.1",
               "bookkeeper_provider": "claude", "bookkeeper_model": "fixture"}
    assert continuable_problem(prior, request=request) is None
    metadata["notes_rule"] = "additions-1"
    assert continuable_problem(prior, request=request) is not None
    request["notes_rule"] = "additions-1"
    assert continuable_problem(prior, request=request) is None
    for marker in (None, "other-rule"):
        metadata["notes_rule"] = request["notes_rule"] = marker
        assert continuable_problem(prior, request=request) is not None


def test_unmarked_v2_continuation_inherits_the_old_notes_rule() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        retain_unmarked_v2(chain.initial)
        assert "notes_rule" not in chain.verify_prior()["settings"]
        review, raw, sheet, _, digest = chain.revision()
        result = chain.continue_with("unmarked-revision", {"codex": [review], "claude": [raw, sheet_review(
            digest, sheet, round_number=5, resolutions=resolved("round-04-prose"))]})
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        request = json.loads((chain.output / "unmarked-revision/decomposition_request.json").read_text())
        assert "notes_rule" not in request and "notes_rule" not in result["designer_bookkeeper"]
        assert "keep the designer's notes that are already there" in chain.providers["claude"].requests[0].prompt
        chain.verify("unmarked-revision", result)


def test_bookkeeper_notes_rule_is_inherited_and_mixed_chain_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-cont-bk-") as text:
        chain = BookkeeperChain(Path(text))
        assert chain.prior["designer_bookkeeper"]["notes_rule"] == "additions-1"
        review, raw, _, _, _ = chain.revision()
        first = chain.continue_with("notes-first", {"codex": [review], "claude": [raw]}, max_calls=1)
        assert first["run_status"] == "needs_human", first["rejection_reasons"]
        assert first["designer_bookkeeper"]["notes_rule"] == "additions-1"
        request_path = chain.output / "notes-first/decomposition_request.json"
        request = json.loads(request_path.read_text())
        assert request["notes_rule"] == "additions-1"
        proof = chain.verify("notes-first", first, open_end=True)
        assert proof["settings"]["notes_rule"] == "additions-1"
        # Even changing both retained markers cannot switch the rule midway through a chain.
        del request["notes_rule"]
        del first["designer_bookkeeper"]["notes_rule"]
        request_path.write_text(json.dumps(request), encoding="utf-8")
        (chain.output / "notes-first/decomposition_run_result.json").write_text(json.dumps(first), encoding="utf-8")
        try:
            chain.verify("notes-first", first, open_end=True)
        except ReviewChainError as exc:
            assert "settings" in str(exc) or "notes_rule" in str(exc), exc
        else:
            raise AssertionError("continuation accepted a mixed notes-rule chain")
        calls = []
        try:
            run_continuation(source=chain.source, output_root=chain.output, task_id="NSC-010",
                             continue_from="notes-first", provider_order=ORDER, max_calls=1,
                             run_id="must-not-start", provider_factory=lambda *a, **kw: calls.append(a),
                             _require_physical_read_only_source=False)
        except DecompositionPreflightError as exc:
            assert "notes_rule" in str(exc), exc
        else:
            raise AssertionError("a mixed notes-rule seed chain was admitted")
        assert not calls and not (chain.output / "must-not-start").exists()


TESTS = (
    test_notes_rule_eligibility_preserves_absence_and_refuses_mismatch,
    test_bookkeeper_notes_rule_is_inherited_and_mixed_chain_refused,
    test_unmarked_v2_continuation_inherits_the_old_notes_rule,
    test_bookkeeper_checklist_is_inherited_and_marker_tampering_is_refused,
    test_bookkeeper_round_three_continues_to_round_four_pass_without_compilation,
    test_bookkeeper_continued_revision_uses_pinned_configuration_then_other_provider_pass,
    test_bookkeeper_continuation_of_continuation_keeps_sheet_and_finding_history,
    test_bookkeeper_failed_and_identical_continuation_compilations_keep_accepted_seed,
    test_bookkeeper_two_accepted_continuation_revisions_stop_non_convergence,
    test_bookkeeper_seed_sheet_and_configuration_tampering_stop_before_provider_spend,
    test_bookkeeper_continuation_verifier_refuses_changed_seed_sheet_and_settings,
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
