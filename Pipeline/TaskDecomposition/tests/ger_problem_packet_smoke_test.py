"""A CONTRACT diagnosis renders an evidence-only GER problem packet, and nothing else.

Runs are real engine runs with test providers that report production-shaped
identities (claude-code, openai-codex), so every emitted value is checked
against the same retained runtime evidence a live run leaves.
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

from TaskDecomposition.ger_problem_packet import (  # noqa: E402
    ProblemPacketError,
    build_problem_packet,
    publish_problem_packet,
)
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.run_diagnosis import diagnose_run, load_run_snapshot  # noqa: E402
from TaskDecomposition.tests.review_chain_smoke_test import factory  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    needs_human_review,
    pass_review,
    revise_review,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result  # noqa: E402


def run(base: Path, author_outputs, reviewer_outputs, *, max_calls: int = 2) -> Path:
    run_round_robin_decomposition(
        source=base / "source", output_root=base / "output", task_id="NSC-010",
        provider_order=("codex", "claude"), max_calls=max_calls, run_id="packet-run",
        provider_factory=factory({"codex": QueueProvider(author_outputs),
                                  "claude": QueueProvider(reviewer_outputs)}),
        _require_physical_read_only_source=False,
    )
    return base / "output" / "packet-run"


def reviewer_stop(base: Path) -> Path:
    tasks = create_repository(base / "source")
    parent = tasks["NSC-010"]
    raw = decomposed_result(parent)
    review = needs_human_review(candidate_sha256(validated_candidate(raw, parent, tasks)))
    review["findings"][0]["affected_contracts"] = ["NSC-010 AC-001", "NSC-010", "NSC-012", "proposed:child"]
    return run(base, [raw], [review])


def packet_for(run_dir: Path) -> dict[str, Any]:
    return build_problem_packet(run_dir, diagnose_run(run_dir), load_run_snapshot(run_dir).result)


def rewrite(path: Path, change: Callable[[dict], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    change(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def runtime_result(run_dir: Path, directory: str) -> Path:
    return next((run_dir / "rounds" / directory / "agent_runtime").glob("*/result.json"))


def refused(action: Callable[[], Any], fragment: str) -> None:
    try:
        action()
    except ProblemPacketError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected a refusal containing {fragment!r}")


def test_a_reviewer_stop_renders_quoted_evidence_only() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        base = Path(text)
        run_dir = reviewer_stop(base)
        assert diagnose_run(run_dir)["primary"]["route"] == "CONTRACT"
        packet = packet_for(run_dir)
        assert packet["authority"] == "diagnostic_only_not_applied" and packet["retry_authorized"] is False
        assert "does not establish that the contract is defective" in packet["meaning"]
        finding = packet["reviews"][0]["findings"][0]
        quoted = {clause["reference"]: clause for clause in finding["quoted_parent_clauses"]}
        assert quoted["NSC-010 AC-001"]["requirement"] == "selected-parent acceptance.", quoted
        assert quoted["NSC-010"]["entry_id"] is None
        assert {item["reference"] for item in finding["unresolved_references"]} == {"NSC-012", "proposed:child"}
        assert any(key.endswith("/result.json") for key in packet["input_sha256"])

        out = base / "packet"
        hashes = publish_problem_packet(out, packet)
        markdown = (out / "GER_PROBLEM.md").read_text(encoding="utf-8")
        assert markdown.startswith("# Unapproved decomposition diagnostic - evidence only")
        assert "> **NSC-010 AC-001** (acceptance_criteria): selected-parent acceptance." in markdown
        assert "No replacement contract text, approval or GER decision is proposed here." in markdown
        manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["ger_problem_md_sha256"] == hashes["GER_PROBLEM.md"]
        for forbidden in ("revised_contract", "patch", "approval", "decision_record"):
            assert forbidden not in manifest, forbidden
        refused(lambda: publish_problem_packet(out, packet), "refusing to overwrite")


def test_questions_from_rejected_outputs_reach_the_packet() -> None:
    # The run stops because outputs raised questions: the questions are the point.
    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        base = Path(text)
        tasks = create_repository(base / "source")
        parent = tasks["NSC-010"]
        asking = decomposed_result(parent)
        asking["unresolved_questions"] = ["Which child owns the builder wiring?"]
        asking_again = deepcopy(asking)
        asking_again["unresolved_questions"] = ["Still: which child owns the builder wiring?"]
        run_dir = run(base, [asking, asking_again], [])
        diagnosis = diagnose_run(run_dir)
        assert diagnosis["primary"]["route"] == "CONTRACT", diagnosis["primary"]
        packet = packet_for(run_dir)
        stages = {(e["stage"], tuple(e["unresolved_questions"])) for e in packet["questions_and_assumptions_raised"]}
        assert ("author", ("Which child owns the builder wiring?",)) in stages, stages
        assert ("correction", ("Still: which child owns the builder wiring?",)) in stages, stages
        publish_problem_packet(base / "packet", packet)
        markdown = (base / "packet" / "GER_PROBLEM.md").read_text(encoding="utf-8")
        assert "Question: Still: which child owns the builder wiring?" in markdown

    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        base = Path(text)
        tasks = create_repository(base / "source")
        parent = tasks["NSC-010"]
        raw = decomposed_result(parent)
        replacement = deepcopy(raw)
        replacement["children"][0]["notes"] = "Reviewer replacement."
        replacement["unresolved_questions"] = ["Does the parent allow a shared test fixture?"]
        review = revise_review(candidate_sha256(validated_candidate(raw, parent, tasks)), replacement,
                               round_number=2, suffix="a")
        run_dir = run(base, [raw], [review])
        assert diagnose_run(run_dir)["primary"]["reason_code"] == "output_requested_authority"
        packet = packet_for(run_dir)
        replacement_questions = [e for e in packet["questions_and_assumptions_raised"]
                                 if e["stage"] == "reviewer replacement"]
        assert replacement_questions and replacement_questions[0]["unresolved_questions"] == [
            "Does the parent allow a shared test fixture?"], packet["questions_and_assumptions_raised"]


def test_a_malformed_earlier_output_does_not_lose_the_later_questions() -> None:
    for field in ("unresolved_questions", "unsupported_assumptions"):
        for bad in (42, "a bare string", {"q": 1}):
            with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
                base = Path(text)
                tasks = create_repository(base / "source")
                parent = tasks["NSC-010"]
                # A normal two-stage run: the author is rejected for asking,
                # the correction asks again. The runtime schema would refuse a
                # malformed field, so it is placed in the author's retained
                # output afterwards, as a provider with a laxer schema could
                # leave it: the packet must not depend on that enforcement.
                first = decomposed_result(parent)
                first["unresolved_questions"] = ["An earlier question."]
                asking = decomposed_result(parent)
                asking["unresolved_questions"] = ["Which child owns the builder wiring?"]
                run_dir = run(base, [first, asking], [])
                rewrite(runtime_result(run_dir, "01"),
                        lambda r, field=field, bad=bad: r["structured_output"].update({field: bad}))
                diagnosis = diagnose_run(run_dir)
                assert diagnosis["primary"]["route"] == "CONTRACT", (field, bad, diagnosis["primary"])
                packet = packet_for(run_dir)
                entries = {e["stage"]: e for e in packet["questions_and_assumptions_raised"]}
                label = (field, bad)
                assert entries["correction"]["unresolved_questions"] == [
                    "Which child owns the builder wiring?"], label
                assert entries["author"]["malformed_fields"] == [
                    {"field": field, "value": json.dumps(bad, sort_keys=True, ensure_ascii=False)}], label
                assert entries["author"][field] == [], label
                publish_problem_packet(base / "packet", packet)
                assert "Malformed `" + field + "`" in (base / "packet" / "GER_PROBLEM.md").read_text(encoding="utf-8")


def test_only_a_contract_diagnosis_gets_a_packet() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        base = Path(text)
        tasks = create_repository(base / "source")
        parent = tasks["NSC-010"]
        raw = decomposed_result(parent)
        run_dir = run(base, [raw], [pass_review(candidate_sha256(validated_candidate(raw, parent, tasks)))])
        refused(lambda: packet_for(run_dir), "only built for a CONTRACT diagnosis")


def test_every_emitted_value_is_bound_to_its_source() -> None:
    cases = (
        ("runtime output differs from review.json",
         lambda d: rewrite(d / "rounds" / "02" / "review.json", lambda r: r["findings"][0].update(problem="x")),
         "runtime output is not its review.json"),
        ("history summary altered",
         lambda d: rewrite(d / "rounds" / "02" / "review_history_entry.json", lambda r: r.update(summary="x")),
         "summary differs between the result and retained files"),
        ("reviewer provider altered",
         lambda d: rewrite(d / "rounds" / "02" / "review_history_entry.json",
                           lambda r: r.update(reviewer_provider="codex")),
         "reviewer_provider differs"),
        ("runtime provider altered",
         lambda d: rewrite(runtime_result(d, "02"), lambda r: r.update(provider="claude-code-x")),
         "result provider"),
        ("published candidate edited",
         lambda d: rewrite(d / "rounds" / "01" / "candidate.json",
                           lambda c: c["children"][0].update(notes="edited after publication")),
         "does not hash to its identity"),
        ("published candidate missing",
         lambda d: (d / "rounds" / "01" / "candidate.json").unlink(),
         "candidate.json is missing"),
        ("context edited",
         lambda d: rewrite(d / "context.json", lambda c: c["selected_task"]["contract"].update(notes="edited")),
         "does not hash to the run's context_sha256"),
    )
    for label, tamper, fragment in cases:
        with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
            run_dir = reviewer_stop(Path(text))
            diagnosis = diagnose_run(run_dir)
            result = deepcopy(load_run_snapshot(run_dir).result)
            packet_for(run_dir)
            tamper(run_dir)
            try:
                build_problem_packet(run_dir, diagnosis, result)
            except ProblemPacketError as exc:
                assert fragment in str(exc), f"{label}: {exc}"
            else:
                raise AssertionError(f"{label}: expected {fragment!r}")


TESTS = (
    test_a_reviewer_stop_renders_quoted_evidence_only,
    test_questions_from_rejected_outputs_reach_the_packet,
    test_a_malformed_earlier_output_does_not_lose_the_later_questions,
    test_only_a_contract_diagnosis_gets_a_packet,
    test_every_emitted_value_is_bound_to_its_source,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition GER problem packet smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
