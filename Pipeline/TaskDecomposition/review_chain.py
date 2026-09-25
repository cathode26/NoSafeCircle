"""Verify the review chain of an opt-in three-call decomposition run.

A two-call run has one shape: an author, then an independent PASS. With a
three-call budget there is a second successful shape: an author, a reviewer
revision, then an independent PASS of that revision by the other provider.
The revision's author is the reviewer, so the final approval must come from
a different provider than the revision's author; that is the independence
rule ADR-035 already states (independence from the latest candidate author).

Nothing here is taken from summaries alone. Every candidate is re-validated
and re-planned from its retained bytes and bound to the chain's links; every
round is authenticated against its retained AgentRuntime request and result
(invocation id, role, provider, model, outcome, timeout and the exact payload
it produced); every review is replayed through the existing review policy.
All consumed files are hashed.

The module is pure: it never invokes a provider, approves or applies. It
returns the verified chain or raises ReviewChainError with a code:

    D3_ACCOUNTING              calls, corrections, rounds or history disagree
    D3_ROUND                   a round has the wrong role, provider or status
    D3_PROVIDER_IDENTITY       the round's runtime evidence is not that round's
    D3_CANDIDATE_LINK          a reviewer did not review the preceding candidate
    D3_CANDIDATE               a candidate's bytes do not validate to its summary
    D3_REVISION                a revision's payload, digest, version or author is wrong
    D3_PASS_MUTATES_CANDIDATE  the final PASS published a replacement
    D3_SELF_APPROVAL           the final approver authored the approved candidate
    D3_FINDING_RESOLUTION      the reviews' findings and resolutions do not replay
    D3_TIMEOUT                 a round ran with a timeout other than the recorded one
    D3_FINAL_ARTIFACTS         the approved candidate is not the run's result

The spec is C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md,
section 3.A.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION
from TaskDecomposition.review_contracts import DecompositionReviewResult
from TaskDecomposition.review_policy import validate_decomposition_review
from TaskDecomposition.run_diagnosis import (
    DiagnosisEvidenceError,
    confined,
    expected_invocation_id,
    parse_json_object,
)

PROVIDER_IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}
AUTHOR_ROLE = "task_decomposer"
REVIEWER_ROLE = "decomposition_reviewer"
RUNTIME_RESULT_SCHEMA_VERSION = "1.0"

# (raw candidate) -> (candidate sha256, graph delta plan id or None when the
# candidate is not a decomposition), or raises. It must normalise and validate
# exactly as the producer does, so a candidate is compared by what it means.
CandidateDigest = Callable[[Mapping[str, Any]], tuple[str, "str | None"]]


class ReviewChainError(ValueError):
    """The retained run does not prove an admissible three-call review chain."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise ReviewChainError(code, detail)


def _exact_int(value: Any) -> bool:
    return type(value) is int


class _Evidence:
    """Reads retained files under the run directory, hashing each once."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.hashes: dict[str, str] = {}

    def json(self, relative: str, code: str) -> dict[str, Any]:
        try:
            path = confined(self.run_dir, relative)
            if not path.is_file():
                raise DiagnosisEvidenceError(f"{relative} is missing")
            data = path.read_bytes()
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
            return parse_json_object(data, relative)
        except DiagnosisEvidenceError as exc:
            raise ReviewChainError(code, str(exc)) from exc


def _check_round(entry: Any, *, number: int, role: str, provider: str, status: str,
                 correction_of_round: int | None) -> Mapping[str, Any]:
    _require(isinstance(entry, Mapping), "D3_ROUND", f"round {number} is not an object")
    _require(_exact_int(entry.get("round_number")), "D3_ROUND", f"round {number} number is not an integer")
    wanted = {
        "round_number": number, "role": role, "requested_provider": provider,
        "agent_status": "succeeded", "status": status, "correction_of_round": correction_of_round,
    }
    for field, value in wanted.items():
        _require(entry.get(field) == value, "D3_ROUND",
                 f"round {number} {field} is {entry.get(field)!r}, expected {value!r}")
    actual = entry.get("actual_provider")
    _require(actual == PROVIDER_IDENTIFIERS[provider], "D3_PROVIDER_IDENTITY",
             f"round {number} ran on {actual!r}, not {PROVIDER_IDENTIFIERS[provider]!r} for {provider!r}")
    return entry


def _authenticate_execution(evidence: _Evidence, run_result: Mapping[str, Any], entry: Mapping[str, Any], *,
                            timeouts: Mapping[str, float] | None) -> Any:
    """Bind a round to its retained AgentRuntime request and result; return its output."""

    number, role = entry["round_number"], entry["role"]
    correction = entry.get("correction_of_round") is not None
    invocation = expected_invocation_id(
        run_result["task_id"], run_result["run_id"], number, role, correction=correction)
    directory = f"{number:02d}" + ("-correction" if correction else "")
    base = f"rounds/{directory}/agent_runtime/{invocation}"
    request = evidence.json(f"{base}/request.json", "D3_PROVIDER_IDENTITY")
    result = evidence.json(f"{base}/result.json", "D3_PROVIDER_IDENTITY")
    expected_provider = PROVIDER_IDENTIFIERS[entry["requested_provider"]]
    checks = {
        "request schema_version": (request.get("schema_version"), AGENT_INVOCATION_REQUEST_SCHEMA_VERSION),
        "request run_id": (request.get("run_id"), invocation),
        "request role": (request.get("role"), role),
        "result schema_version": (result.get("schema_version"), RUNTIME_RESULT_SCHEMA_VERSION),
        "result run_id": (result.get("run_id"), invocation),
        "result role": (result.get("role"), role),
        "result provider": (result.get("provider"), expected_provider),
        "result model": (result.get("model"), entry.get("actual_model")),
        "result status": (result.get("status"), "succeeded"),
        "summary result path": (entry.get("agent_runtime_result_path"), f"{base}/result.json"),
    }
    for name, (got, wanted) in checks.items():
        _require(got == wanted, "D3_PROVIDER_IDENTITY",
                 f"round {number}{' correction' if correction else ''} {name} is {got!r}, expected {wanted!r}")
    if timeouts is not None:
        budgets = request.get("budgets") if isinstance(request.get("budgets"), Mapping) else {}
        _require(budgets.get("timeout_seconds") == timeouts[role], "D3_TIMEOUT",
                 f"round {number} {role} ran with timeout {budgets.get('timeout_seconds')!r}, "
                 f"the run recorded {timeouts[role]!r}")
    return result.get("structured_output")


def _published_candidate(evidence: _Evidence, directory: str, summary: Mapping[str, Any],
                         digest: CandidateDigest, *, label: str) -> dict[str, Any]:
    """The round's published candidate, re-validated and bound to its summary."""

    raw = evidence.json(f"rounds/{directory}/candidate.json", "D3_CANDIDATE")
    identity = evidence.json(f"rounds/{directory}/candidate_identity.json", "D3_CANDIDATE")
    _require(dict(identity) == dict(summary), "D3_CANDIDATE",
             f"{label} identity file {identity!r} differs from the summary {summary!r}")
    sha, plan_id = _digest(digest, raw, "D3_CANDIDATE", label)
    _require(sha == summary.get("sha256") and plan_id == summary.get("graph_delta_plan_id"),
             "D3_CANDIDATE",
             f"{label} bytes validate to {sha}/{plan_id}, not the summary's "
             f"{summary.get('sha256')}/{summary.get('graph_delta_plan_id')}")
    graph_relative = f"rounds/{directory}/candidate_graph_delta.json"
    if plan_id is None:
        # A proposal that is not a decomposition publishes no graph plan.
        _require(not confined(evidence.run_dir, graph_relative).exists(), "D3_CANDIDATE",
                 f"{label} is not a decomposition but carries {graph_relative}")
    else:
        graph = evidence.json(graph_relative, "D3_CANDIDATE")
        _require(graph.get("plan_id") == plan_id, "D3_CANDIDATE",
                 f"{graph_relative} plan {graph.get('plan_id')!r} is not {plan_id!r}")
    return raw


def _digest(digest: CandidateDigest, raw: Any, code: str, label: str) -> tuple[str, str | None]:
    try:
        return digest(raw)
    except Exception as exc:  # the validator's own refusal, whatever its type
        raise ReviewChainError(code, f"{label} does not validate: {exc}") from exc


def _parsed_review(value: Any, label: str) -> dict[str, Any]:
    """A review in the form the schema parser gives it (e.g. trimmed text)."""

    try:
        return DecompositionReviewResult.from_dict(value).to_dict()
    except Exception as exc:  # the contract's own refusal, whatever its type
        raise ReviewChainError("D3_PROVIDER_IDENTITY", f"{label} is not a valid review: {exc}") from exc


def _candidate_summary(value: Any, *, label: str) -> Mapping[str, Any]:
    plan_id = value.get("graph_delta_plan_id") if isinstance(value, Mapping) else None
    _require(isinstance(value, Mapping) and isinstance(value.get("sha256"), str)
             and _exact_int(value.get("version")) and isinstance(value.get("author_provider"), str)
             and isinstance(value.get("decision"), str)
             and (isinstance(plan_id, str) if value.get("decision") == "decomposed" else plan_id is None),
             "D3_CANDIDATE_LINK", f"{label} is not a published candidate summary")
    return value


def verify_three_call_chain(
    *, run_dir: Path, run_result: Mapping[str, Any], providers: tuple[str, str],
    candidate_digest: CandidateDigest, timeouts: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return the verified chain of a budget-3 run, or raise ReviewChainError.

    `candidate_digest` validates and plans a raw candidate against the
    committed graph and returns its (sha256, plan id). `timeouts` maps each
    role to the timeout the host recorded for this run, when it recorded one.
    """

    first, second = providers
    _require(first != second and {first, second} <= set(PROVIDER_IDENTIFIERS), "D3_ROUND",
             f"a three-call chain needs two distinct providers, not {providers!r}")
    calls = run_result.get("calls_used")
    corrections = run_result.get("author_corrections_used")
    rounds = run_result.get("rounds")
    _require(_exact_int(calls) and calls in (2, 3) and _exact_int(corrections) and corrections in (0, 1)
             and _exact_int(run_result.get("max_calls")) and run_result.get("max_calls") == 3
             and isinstance(rounds, list) and len(rounds) == calls + corrections,
             "D3_ACCOUNTING",
             f"calls_used={calls!r} corrections={corrections!r} max_calls={run_result.get('max_calls')!r} "
             f"with {len(rounds) if isinstance(rounds, list) else rounds!r} rounds")
    history = run_result.get("finding_history")
    _require(isinstance(history, list) and len(history) == calls - 1, "D3_ACCOUNTING",
             f"finding_history has {len(history) if isinstance(history, list) else history!r} entries")

    evidence = _Evidence(run_dir)
    ordinary = list(rounds)
    if corrections:
        initial = ordinary.pop(0)
        _check_round(initial, number=1, role=AUTHOR_ROLE, provider=first, status="rejected",
                     correction_of_round=None)
        reasons = initial.get("rejection_reasons")
        _require(initial.get("candidate_after") is None and isinstance(reasons, list) and bool(reasons)
                 and all(isinstance(reason, str) and reason for reason in reasons), "D3_ROUND",
                 "the corrected round 1 does not retain its rejection")
        _authenticate_execution(evidence, run_result, initial, timeouts=timeouts)
    author = _check_round(
        ordinary[0], number=1, role=AUTHOR_ROLE, provider=first,
        status="correction_candidate_valid" if corrections else "candidate_valid",
        correction_of_round=1 if corrections else None)
    author_output = _authenticate_execution(evidence, run_result, author, timeouts=timeouts)
    latest = _candidate_summary(author.get("candidate_after"), label="round 1 candidate")
    _require(latest.get("author_provider") == first and latest.get("version") == 1, "D3_REVISION",
             f"round 1 candidate names author {latest.get('author_provider')!r} version {latest.get('version')!r}")
    _published_candidate(
        evidence, "01-correction" if corrections else "01", latest, candidate_digest, label="round 1 candidate")
    _require(_digest(candidate_digest, author_output, "D3_PROVIDER_IDENTITY", "round 1 runtime output")
             == (latest["sha256"], latest["graph_delta_plan_id"]), "D3_PROVIDER_IDENTITY",
             "round 1's runtime output is not the published candidate")

    unresolved: dict[str, Any] = {}
    seen_ids: set[str] = set()
    approver = None
    for number in range(2, calls + 1):
        provider = providers[(number - 1) % 2]
        final = number == calls
        entry = ordinary[number - 1]
        # Self-approval is checked before the rotation, so a record that
        # swaps the final reviewer is refused for the rule it actually breaks.
        if final and isinstance(entry, Mapping):
            actual = entry.get("actual_provider")
            requested = entry.get("requested_provider")
            _require(requested != latest["author_provider"]
                     and actual != PROVIDER_IDENTIFIERS.get(latest["author_provider"]),
                     "D3_SELF_APPROVAL",
                     f"final approver {requested!r} ({actual!r}) equals candidate author "
                     f"{latest['author_provider']!r} of version {latest['version']}")
        relative = f"rounds/{number:02d}/review.json"
        raw_review = evidence.json(relative, "D3_FINDING_RESOLUTION")
        if final:
            _require(isinstance(entry, Mapping) and entry.get("candidate_after") is None
                     and entry.get("verdict") == "pass"
                     and raw_review.get("verdict") == "pass"
                     and raw_review.get("revised_decomposition") is None,
                     "D3_PASS_MUTATES_CANDIDATE",
                     f"the final round {number} did not pass the candidate unchanged")
        entry = _check_round(entry, number=number, role=REVIEWER_ROLE, provider=provider,
                             status="independent_pass" if final else "revised_candidate_valid",
                             correction_of_round=None)
        _require(entry.get("candidate_before") == latest, "D3_CANDIDATE_LINK",
                 f"round {number} reviewed {entry.get('candidate_before')!r}, not the preceding candidate")
        output = _authenticate_execution(evidence, run_result, entry, timeouts=timeouts)
        _require(_parsed_review(output, f"round {number} runtime output")
                 == _parsed_review(raw_review, relative), "D3_PROVIDER_IDENTITY",
                 f"round {number}'s runtime output is not {relative}")
        try:
            review, unresolved = validate_decomposition_review(
                raw_review,
                expected_candidate_sha256=latest["sha256"],
                round_number=number,
                prior_unresolved_findings=unresolved,
                all_prior_finding_ids=frozenset(seen_ids),
            )
        except Exception as exc:  # the policy's own refusal, whatever its type
            raise ReviewChainError("D3_FINDING_RESOLUTION", f"{relative}: {exc}") from exc
        seen_ids.update(finding.finding_id for finding in review.findings)
        recorded = history[number - 2]
        retained_entry = evidence.json(f"rounds/{number:02d}/review_history_entry.json", "D3_FINDING_RESOLUTION")
        expected_entry = {
            "round_number": number, "reviewer_provider": provider, "verdict": review.verdict,
            "reviewed_candidate_sha256": latest["sha256"],
            "findings": raw_review.get("findings"),
            "prior_finding_resolutions": raw_review.get("prior_finding_resolutions"),
        }
        for field, value in expected_entry.items():
            _require(isinstance(recorded, Mapping) and recorded.get(field) == value
                     and retained_entry.get(field) == value, "D3_FINDING_RESOLUTION",
                     f"finding_history[{number - 2}] {field} does not match {relative}")
        _require(entry.get("verdict") == review.verdict, "D3_FINDING_RESOLUTION",
                 f"round {number} verdict {entry.get('verdict')!r} differs from {relative}")

        if final:
            _require(not unresolved, "D3_FINDING_RESOLUTION",
                     f"blocking findings remain unresolved at the final PASS: {sorted(unresolved)}")
            approver = provider
        else:
            _require(review.verdict == "revise", "D3_REVISION", f"{relative} is not a revision")
            revised = _candidate_summary(entry.get("candidate_after"), label=f"round {number} revision")
            _require(revised.get("sha256") != latest["sha256"]
                     and revised.get("version") == latest["version"] + 1
                     and revised.get("author_provider") == provider, "D3_REVISION",
                     f"round {number} revision {revised!r} does not follow {latest!r} as {provider!r}")
            _published_candidate(
                evidence, f"{number:02d}", revised, candidate_digest, label=f"round {number} revision")
            _require(_digest(candidate_digest, raw_review.get("revised_decomposition"), "D3_REVISION",
                             f"{relative} replacement")
                     == (revised["sha256"], revised["graph_delta_plan_id"]), "D3_REVISION",
                     f"{relative}'s replacement is not the published round {number} candidate")
            latest = revised

    _require(latest.get("decision") == "decomposed", "D3_FINAL_ARTIFACTS",
             f"the approved candidate is {latest.get('decision')!r}, not a decomposition")
    _require(run_result.get("latest_candidate") == latest, "D3_FINAL_ARTIFACTS",
             "latest_candidate is not the candidate the chain approved")
    _require(run_result.get("independent_approver_provider") == approver, "D3_FINAL_ARTIFACTS",
             f"independent_approver_provider is {run_result.get('independent_approver_provider')!r}, "
             f"the chain's approver is {approver!r}")
    return {
        "approved_candidate": dict(latest),
        "approver_provider": approver,
        "calls_used": calls,
        "author_corrections_used": corrections,
        "models": [entry.get("actual_model") for entry in rounds],
        "evidence_sha256": dict(evidence.hashes),
    }
