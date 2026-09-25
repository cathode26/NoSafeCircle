"""Decomposition failure diagnosis routes real retained runs to their cause.

The fixtures are unmodified ``decomposition_run_result.json`` files from real
runs (see fixtures/failure_diagnosis/MANIFEST.json for their origin and hashes).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.run_diagnosis import (  # noqa: E402
    RUN_RESULT_NAME,
    DiagnosisEvidenceError,
    diagnose_run,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "failure_diagnosis"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def diagnose(result: dict | bytes) -> dict:
    with tempfile.TemporaryDirectory(prefix="nsc-diagnosis-") as text:
        run_dir = Path(text)
        data = result if isinstance(result, bytes) else json.dumps(result).encode("utf-8")
        (run_dir / RUN_RESULT_NAME).write_bytes(data)
        return diagnose_run(run_dir)


def route(result: dict) -> tuple[str, str]:
    primary = diagnose(result)["primary"]
    return primary["route"], primary["reason_code"]


def test_the_fixtures_are_the_recorded_bytes() -> None:
    manifest = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, entry in manifest["fixtures"].items():
        data = (FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == entry["sha256_lf"], f"{name} changed after it was recorded"


def test_real_runs_route_to_their_known_cause() -> None:
    expected = {
        "decomp-nsc007-20260918a": ("AUTHOR", "initial_candidate_invalid"),
        "decomp-nsc007-20260918c": ("AUTHOR", "revision_invalid"),
        "decomp-nsc007-20260922a": ("STOP", "source_changed_during_run"),
        "decomp-nsc015-20260917c": ("STOP", "source_changed_during_run"),
        "nsc015-d1b2-20260915b": ("CONTRACT", "output_requested_authority"),
        "decomp-nsc066-20260924c": ("STOP", "not_a_failure"),
        "decomp-nsc088-clone-20260924a": ("SETUP", "prompt_too_long"),
        "decomp-nsc088-clone-20260924b": ("SETUP", "unrecognized_model"),
        "decomp-nsc088-clone-20260924c": ("BUDGET", "revision_used_last_call"),
    }
    for name, want in expected.items():
        got = route(fixture(name))
        assert got == want, f"{name}: {got} != {want}"


def test_a_budget_stop_keeps_the_reviewer_findings_as_a_secondary_cause() -> None:
    result = diagnose(fixture("decomp-nsc088-clone-20260924c"))
    assert result["retry_authorized"] is False
    secondary = result["secondary"]
    assert [entry["route"] for entry in secondary] == ["AUTHOR"], secondary
    assert "round-02-builder-facade-edit-authority" in secondary[0]["finding_ids"], secondary


def test_setup_words_inside_findings_never_route_to_setup() -> None:
    budget = fixture("decomp-nsc088-clone-20260924c")
    budget["finding_history"][0]["findings"][0]["problem"] = (
        "Prompt is too long; unrecognized_model; PromptCapacityError; hit your usage limit")
    assert route(budget) == ("BUDGET", "revision_used_last_call")
    author = fixture("decomp-nsc007-20260918a")
    author["rejection_reasons"] = [
        author["rejection_reasons"][0] + " (the child notes mention Prompt is too long)"]
    assert route(author) == ("AUTHOR", "initial_candidate_invalid")


def test_a_setup_failure_never_routes_to_contract() -> None:
    for name in ("decomp-nsc088-clone-20260924a", "decomp-nsc088-clone-20260924b"):
        result = fixture(name)
        result["decision"] = "needs_human"
        assert route(result)[0] == "SETUP", name


def test_a_correction_refused_for_capacity_is_setup_with_the_author_error_kept() -> None:
    result = fixture("decomp-nsc007-20260918a")
    initial = result["rejection_reasons"][0]
    result["rejection_reasons"] = [
        initial,
        "round 1 correction: task-associated invocation failed: PromptCapacityError: "
        "provider_started=false: prompt is 900000 bytes",
    ]
    result["author_corrections_used"] = 1
    diagnosis = diagnose(result)
    assert (diagnosis["primary"]["route"], diagnosis["primary"]["reason_code"]) == (
        "SETUP", "capacity_refused_before_call"), diagnosis["primary"]
    assert [(e["route"], e["reason_code"]) for e in diagnosis["secondary"]] == [
        ("AUTHOR", "initial_candidate_invalid")], diagnosis["secondary"]


def test_unknown_provider_failures_and_unrecognised_runs_stop() -> None:
    result = fixture("decomp-nsc088-clone-20260924a")
    result["rejection_reasons"] = ["round 1: AgentResult failed (provider_error): something new"]
    assert route(result) == ("STOP", "unrecognised_provider_failure")
    result = fixture("decomp-nsc007-20260918a")
    result["rejection_reasons"] = ["round 1: a reason this classifier has never seen"]
    assert route(result) == ("STOP", "unrecognised_failure")
    result["mode"] = "d1b1"
    assert route(result) == ("STOP", "unrecognised_run_evidence")


def test_an_explicit_reviewer_stop_is_contract_review_not_budget() -> None:
    result = fixture("decomp-nsc088-clone-20260924c")
    result["rounds"][-1]["verdict"] = "needs_human"
    result["rounds"][-1]["status"] = "needs_human"
    result["rejection_reasons"] = ["reviewer requested a human decision"]
    assert route(result) == ("CONTRACT", "provider_requested_human_decision")


def test_an_unproven_session_stops_before_anything_else() -> None:
    result = fixture("decomp-nsc088-clone-20260924c")
    result["rejection_reasons"] = [
        "round 2: provider session identity unproven: round 2 asked for a session",
        "call limit ended immediately after a revision; the latest author may not approve its own candidate",
    ]
    assert route(result) == ("STOP", "provider_session_unproven")


def test_malformed_or_unsafe_evidence_is_refused() -> None:
    for data, fragment in (
        (b'{"run_status": "rejected", "run_status": "review_ready"}', "duplicate JSON key"),
        (b"[]", "not a JSON object"),
        (b"\xff\xfe", "not valid UTF-8 JSON"),
    ):
        try:
            diagnose(data)
        except DiagnosisEvidenceError as exc:
            assert fragment in str(exc), str(exc)
        else:
            raise AssertionError(f"expected refusal containing {fragment!r}")
    with tempfile.TemporaryDirectory(prefix="nsc-diagnosis-") as text:
        try:
            diagnose_run(Path(text))
        except DiagnosisEvidenceError as exc:
            assert "missing" in str(exc), str(exc)
        else:
            raise AssertionError("a missing run result must be refused")


def test_the_manifest_binds_the_bytes_read() -> None:
    raw = (FIXTURES / "decomp-nsc088-clone-20260924b.json").read_bytes()
    diagnosis = diagnose(raw)
    assert diagnosis["input_manifest"] == {RUN_RESULT_NAME: hashlib.sha256(raw).hexdigest()}
    changed = deepcopy(json.loads(raw))
    changed["duration_seconds"] = 0
    assert diagnose(changed)["input_manifest"] != diagnosis["input_manifest"]


TESTS = (
    test_the_fixtures_are_the_recorded_bytes,
    test_real_runs_route_to_their_known_cause,
    test_a_budget_stop_keeps_the_reviewer_findings_as_a_secondary_cause,
    test_setup_words_inside_findings_never_route_to_setup,
    test_a_setup_failure_never_routes_to_contract,
    test_a_correction_refused_for_capacity_is_setup_with_the_author_error_kept,
    test_unknown_provider_failures_and_unrecognised_runs_stop,
    test_an_explicit_reviewer_stop_is_contract_review_not_budget,
    test_an_unproven_session_stops_before_anything_else,
    test_malformed_or_unsafe_evidence_is_refused,
    test_the_manifest_binds_the_bytes_read,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition run diagnosis smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
