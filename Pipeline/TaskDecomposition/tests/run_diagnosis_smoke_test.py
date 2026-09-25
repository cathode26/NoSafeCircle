"""Decomposition failure diagnosis routes real retained runs to their cause.

The fixtures are unmodified retained files from real runs, laid out as run
directories (see fixtures/failure_diagnosis/MANIFEST.json for origin and
hashes). Negative cases start from a real run and change one thing.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.round_robin_decomposition import _round_invocation_id  # noqa: E402
from TaskDecomposition.run_diagnosis import (  # noqa: E402
    RUN_RESULT_NAME,
    DiagnosisEvidenceError,
    diagnose_run,
    expected_invocation_id,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "failure_diagnosis"
BUDGET_TEXT = "call limit ended immediately after a revision; the latest author may not approve its own candidate"
UNRESOLVED = ("initial candidate deterministic validation failed: Accepted decomposition output "
              "may not contain unsupported assumptions or unresolved questions.")


def diagnose(run: str, *, mutate: Callable[[dict], None] | None = None,
             runtime: Callable[[dict], None] | None = None,
             receipt: dict | None = None, raw: bytes | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nsc-diagnosis-") as text:
        run_dir = Path(text) / run
        shutil.copytree(FIXTURES / run, run_dir)
        result_path = run_dir / RUN_RESULT_NAME
        if raw is not None:
            result_path.write_bytes(raw)
        elif mutate is not None:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            mutate(result)
            result_path.write_text(json.dumps(result), encoding="utf-8")
        if runtime is not None:
            last = json.loads(result_path.read_text(encoding="utf-8"))["rounds"][-1]
            runtime_path = run_dir / last["agent_runtime_result_path"]
            value = json.loads(runtime_path.read_text(encoding="utf-8"))
            runtime(value)
            runtime_path.write_text(json.dumps(value), encoding="utf-8")
        return diagnose_run(run_dir, receipt=receipt)


def route(run: str, **kwargs) -> tuple[str, str]:
    primary = diagnose(run, **kwargs)["primary"]
    return primary["route"], primary["reason_code"]


def refused(action: Callable[[], Any], fragment: str) -> None:
    try:
        action()
    except DiagnosisEvidenceError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected a refusal containing {fragment!r}")


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
        "decomp-nsc088-clone-20260924a": ("SETUP", "prompt_too_long"),
        "decomp-nsc088-clone-20260924b": ("SETUP", "unrecognized_model"),
        "decomp-nsc088-clone-20260924c": ("BUDGET", "revision_used_last_call"),
    }
    for run, want in expected.items():
        got = route(run)
        assert got == want, f"{run}: {got} != {want}"


def test_an_engine_success_is_only_a_success_if_the_host_accepted_it() -> None:
    host_refused = {"status": "failed",
                    "error": "ValueError: Decomposition review history does not end with a clean pass"}
    assert route("decomp-nsc066-20260924b", receipt=host_refused) == ("STOP", "host_verification_failed")
    assert route("decomp-nsc066-20260924c", receipt={"status": "applied"}) == ("STOP", "not_a_failure")
    assert route("decomp-nsc066-20260924c") == ("STOP", "engine_review_ready_unverified")

    def reviewed_needs_human(result: dict) -> None:
        result["decision"] = "needs_human"
    assert route("decomp-nsc066-20260924c", mutate=reviewed_needs_human,
                 receipt={"status": "review_ready"}) == ("CONTRACT", "reviewed_decision_needs_human")


def test_a_setup_runtime_result_is_read_hashed_and_must_agree() -> None:
    result = diagnose("decomp-nsc088-clone-20260924a")
    runtime = [path for path in result["input_manifest"] if "agent_runtime" in path]
    assert len(runtime) == 1 and result["primary"]["evidence"][0]["artifact"] == runtime[0], result

    def disagree(value: dict) -> None:
        value["failure_classification"] = "timeout"
    refused(lambda: diagnose("decomp-nsc088-clone-20260924a", runtime=disagree), "AgentRuntime result failure_classification")


def test_model_text_in_a_provider_error_never_routes_to_setup() -> None:
    def appended(value: dict) -> None:
        value["failure_message"] += " -- and the model then wrote: Prompt is too long"
    assert route("decomp-nsc088-clone-20260924a", runtime=appended) == ("STOP", "unrecognised_provider_failure")

    def budget_with_quote(value: dict) -> None:
        value["failure_classification"] = "budget_exhausted"
        value["failure_message"] = "Claude Code reported: Prompt is too long"

    def budget_summary(result: dict) -> None:
        result["rounds"][-1]["agent_failure_classification"] = "budget_exhausted"
    assert route("decomp-nsc088-clone-20260924a", mutate=budget_summary,
                 runtime=budget_with_quote) == ("STOP", "unrecognised_provider_failure")

    def findings(result: dict) -> None:
        result["finding_history"][0]["findings"][0]["problem"] = (
            "Prompt is too long; unrecognized_model; PromptCapacityError")
    assert route("decomp-nsc088-clone-20260924c", mutate=findings) == ("BUDGET", "revision_used_last_call")


def test_the_runtime_result_must_be_this_rounds_own() -> None:
    for name, value in (("run_id", "another-invocation"), ("provider", "openai-codex"),
                        ("model", "claude-sonnet-5"), ("role", "decomposition_reviewer"),
                        ("status", "succeeded"), ("schema_version", "9")):
        def change(runtime: dict, name=name, value=value) -> None:
            runtime[name] = value
        refused(lambda change=change: diagnose("decomp-nsc088-clone-20260924a", runtime=change),
                f"AgentRuntime result {name}")

    def other_path(result: dict) -> None:
        result["rounds"][-1]["agent_runtime_result_path"] = (
            "rounds/01/agent_runtime/nsc-088-d1b2-r01-task-decomposer-000000000000/result.json")
    refused(lambda: diagnose("decomp-nsc088-clone-20260924a", mutate=other_path), "is not this round's")


def test_the_invocation_id_matches_the_engine() -> None:
    for round_number, role, correction in ((1, "task_decomposer", False), (1, "task_decomposer", True),
                                           (2, "decomposition_reviewer", False)):
        assert expected_invocation_id("NSC-088", "run-x", round_number, role, correction=correction) == (
            _round_invocation_id("NSC-088", "run-x", round_number, role, correction=correction))


def test_a_revised_request_for_human_authority_is_contract_not_budget() -> None:
    def revised_needs_human(result: dict) -> None:
        result["decision"] = "needs_human"
    assert route("decomp-nsc088-clone-20260924c", mutate=revised_needs_human) == (
        "CONTRACT", "revision_requests_human_decision")


def test_a_structured_quota_failure_is_setup() -> None:
    def quota(value: dict) -> None:
        value["failure_classification"] = "quota_exhausted"

    def quota_summary(result: dict) -> None:
        result["rounds"][-1]["agent_failure_classification"] = "quota_exhausted"
    assert route("decomp-nsc088-clone-20260924a", mutate=quota_summary, runtime=quota) == (
        "SETUP", "quota_exhausted")


def test_the_terminal_stage_is_the_last_round_reached() -> None:
    def corrected_then_budget(result: dict) -> None:
        author, reviewer = result["rounds"]
        rejected = deepcopy(author)
        rejected.update(status="rejected", rejection_reasons=[UNRESOLVED], candidate_after=None)
        correction = deepcopy(author)
        correction.update(correction_of_round=1, status="correction_candidate_valid", rejection_reasons=[])
        result["rounds"] = [rejected, correction, reviewer]
        result["decision"] = "decomposed"
        result["author_corrections_used"] = 1
        result["rejection_reasons"] = [f"round 1: {UNRESOLVED}", BUDGET_TEXT]
    assert route("decomp-nsc088-clone-20260924c", mutate=corrected_then_budget) == (
        "BUDGET", "revision_used_last_call")

    def failed_correction(result: dict) -> None:
        author = result["rounds"][0]
        correction = deepcopy(author)
        correction.update(correction_of_round=1, rejection_reasons=[
            "corrected candidate deterministic validation failed: still not injective"])
        result["rounds"] = [author, correction]
        result["author_corrections_used"] = 1
    assert route("decomp-nsc007-20260918a", mutate=failed_correction) == ("AUTHOR", "correction_invalid")


def test_a_correction_refused_for_capacity_is_setup_with_the_author_error_kept() -> None:
    def capacity_correction(result: dict) -> None:
        author = result["rounds"][0]
        correction = deepcopy(author)
        correction.update(
            correction_of_round=1, agent_status="failed", agent_failure_classification="internal_error",
            agent_runtime_result_path=None, rejection_reasons=[
                "task-associated invocation failed: PromptCapacityError: provider_started=false: "
                "prompt is 900000 bytes"])
        result["rounds"] = [author, correction]
        result["author_corrections_used"] = 1
    diagnosis = diagnose("decomp-nsc007-20260918a", mutate=capacity_correction)
    assert (diagnosis["primary"]["route"], diagnosis["primary"]["reason_code"]) == (
        "SETUP", "capacity_refused_before_call"), diagnosis["primary"]
    assert [(e["route"], e["reason_code"]) for e in diagnosis["secondary"]] == [
        ("AUTHOR", "initial_candidate_invalid")], diagnosis["secondary"]


def test_malformed_or_inconsistent_evidence_is_not_diagnosed_confidently() -> None:
    cases: dict[str, Callable[[dict], None]] = {
        "schema": lambda r: r.update(schema_version="999"),
        "scalar rounds": lambda r: r.update(rounds="many"),
        "scalar finding_history": lambda r: r.update(finding_history=7),
        "boolean calls": lambda r: r.update(calls_used=True),
        "rounds disagree with accounting": lambda r: r.update(calls_used=1),
        "list run_status": lambda r: r.update(run_status=["needs_human"]),
        "object run_status": lambda r: r.update(run_status={"x": 1}),
        "duplicate round 1": lambda r: r["rounds"][1].update(round_number=1),
        "round 99": lambda r: r["rounds"][0].update(round_number=99),
        "reviewer in round 1": lambda r: r["rounds"][0].update(role="decomposition_reviewer"),
    }
    for name, mutate in cases.items():
        got = route("decomp-nsc088-clone-20260924c", mutate=mutate)
        assert got == ("STOP", "malformed_evidence"), f"{name}: {got}"
    unspent = route("decomp-nsc088-clone-20260924c", mutate=lambda r: r.update(max_calls=3))
    assert unspent[0] != "BUDGET", f"a budget stop needs the last call spent: {unspent}"
    for raw, fragment in (
        (b'{"run_status": "rejected", "run_status": "review_ready"}', "duplicate JSON key"),
        (b"[]", "not a JSON object"),
        (b"\xff\xfe", "not valid UTF-8 JSON"),
    ):
        refused(lambda raw=raw: diagnose("decomp-nsc007-20260918a", raw=raw), fragment)


def test_unproven_sessions_and_unknown_failures_stop() -> None:
    def unproven(result: dict) -> None:
        result["rejection_reasons"] = ["round 2: provider session identity unproven: never confirmed",
                                       BUDGET_TEXT]
    assert route("decomp-nsc088-clone-20260924c", mutate=unproven) == ("STOP", "provider_session_unproven")

    def unknown(result: dict) -> None:
        result["rounds"][0]["rejection_reasons"] = ["a reason this classifier has never seen"]
        result["rejection_reasons"] = ["round 1: a reason this classifier has never seen"]
    assert route("decomp-nsc007-20260918a", mutate=unknown) == ("STOP", "unrecognised_failure")


def test_every_diagnosis_withholds_retry_authority_and_binds_its_inputs() -> None:
    result = diagnose("decomp-nsc088-clone-20260924b")
    assert result["retry_authorized"] is False
    raw = (FIXTURES / "decomp-nsc088-clone-20260924b" / RUN_RESULT_NAME).read_bytes()
    assert result["input_manifest"][RUN_RESULT_NAME] == hashlib.sha256(raw).hexdigest()


TESTS = (
    test_the_fixtures_are_the_recorded_bytes,
    test_real_runs_route_to_their_known_cause,
    test_an_engine_success_is_only_a_success_if_the_host_accepted_it,
    test_a_setup_runtime_result_is_read_hashed_and_must_agree,
    test_model_text_in_a_provider_error_never_routes_to_setup,
    test_the_runtime_result_must_be_this_rounds_own,
    test_the_invocation_id_matches_the_engine,
    test_a_revised_request_for_human_authority_is_contract_not_budget,
    test_a_structured_quota_failure_is_setup,
    test_the_terminal_stage_is_the_last_round_reached,
    test_a_correction_refused_for_capacity_is_setup_with_the_author_error_kept,
    test_malformed_or_inconsistent_evidence_is_not_diagnosed_confidently,
    test_unproven_sessions_and_unknown_failures_stop,
    test_every_diagnosis_withholds_retry_authority_and_binds_its_inputs,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition run diagnosis smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
