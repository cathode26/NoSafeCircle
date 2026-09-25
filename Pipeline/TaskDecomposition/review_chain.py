"""Verify the review chain of an opt-in three-call decomposition run.

A two-call run has one shape: an author, then an independent PASS. With a
three-call budget there is a second successful shape: an author, a reviewer
revision, then an independent PASS of that revision by the other provider.
The revision's author is the reviewer, so the final approval must come from
a different provider than the revision's author; that is the independence
rule ADR-035 already states (independence from the latest candidate author).

This module is pure: it reads the run's retained artifacts, never invokes a
provider, never approves or applies anything, and either returns the
verified chain or raises a ReviewChainError whose code names the rule broken:

    D3_ACCOUNTING              calls, corrections and rounds disagree
    D3_ROUND                   a round has the wrong role, provider or status
    D3_PROVIDER_IDENTITY       the runtime provider is not the requested one
    D3_CANDIDATE_LINK          a reviewer did not review the preceding candidate
    D3_REVISION                a revision's digest, version or author is wrong
    D3_PASS_MUTATES_CANDIDATE  the final PASS published a replacement
    D3_SELF_APPROVAL           the final approver authored the approved candidate
    D3_FINDING_RESOLUTION      the reviews' finding resolutions do not replay
    D3_FINAL_ARTIFACTS         the approved candidate is not the run's result

The spec is C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md,
section 3.A.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from TaskDecomposition.review_policy import validate_decomposition_review
from TaskDecomposition.run_diagnosis import confined, parse_json_object

PROVIDER_IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}
AUTHOR_ROLE = "task_decomposer"
REVIEWER_ROLE = "decomposition_reviewer"


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


def _check_round(entry: Any, *, number: int, role: str, provider: str, status: str,
                 correction_of_round: int | None) -> Mapping[str, Any]:
    _require(isinstance(entry, Mapping), "D3_ROUND", f"round {number} is not an object")
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


def _candidate(value: Any, *, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping) and isinstance(value.get("sha256"), str)
             and _exact_int(value.get("version")) and isinstance(value.get("author_provider"), str),
             "D3_CANDIDATE_LINK", f"{label} is not a published candidate summary")
    return value


def verify_three_call_chain(
    *, run_dir: Path, run_result: Mapping[str, Any], providers: tuple[str, str],
) -> dict[str, Any]:
    """Return the verified chain of a budget-3 run, or raise ReviewChainError."""

    first, second = providers
    _require(first != second and {first, second} <= set(PROVIDER_IDENTIFIERS), "D3_ROUND",
             f"a three-call chain needs two distinct providers, not {providers!r}")
    calls = run_result.get("calls_used")
    corrections = run_result.get("author_corrections_used")
    rounds = run_result.get("rounds")
    _require(_exact_int(calls) and calls in (2, 3) and _exact_int(corrections) and corrections in (0, 1)
             and run_result.get("max_calls") == 3 and isinstance(rounds, list)
             and len(rounds) == calls + corrections, "D3_ACCOUNTING",
             f"calls_used={calls!r} corrections={corrections!r} max_calls={run_result.get('max_calls')!r} "
             f"with {len(rounds) if isinstance(rounds, list) else rounds!r} rounds")

    ordinary = list(rounds)
    if corrections:
        initial = ordinary.pop(0)
        _check_round(initial, number=1, role=AUTHOR_ROLE, provider=first, status="rejected",
                     correction_of_round=None)
        reasons = initial.get("rejection_reasons")
        _require(initial.get("candidate_after") is None and isinstance(reasons, list) and bool(reasons)
                 and all(isinstance(reason, str) and reason for reason in reasons), "D3_ROUND",
                 "the corrected round 1 does not retain its rejection")
    author = _check_round(
        ordinary[0], number=1, role=AUTHOR_ROLE, provider=first,
        status="correction_candidate_valid" if corrections else "candidate_valid",
        correction_of_round=1 if corrections else None)
    latest = _candidate(author.get("candidate_after"), label="round 1 candidate")
    _require(latest.get("author_provider") == first and latest.get("version") == 1, "D3_REVISION",
             f"round 1 candidate names author {latest.get('author_provider')!r} version {latest.get('version')!r}")

    manifest: dict[str, str] = {}
    unresolved: dict[str, Any] = {}
    seen_ids: set[str] = set()
    history = run_result.get("finding_history")
    _require(isinstance(history, list) and len(history) == calls - 1, "D3_ACCOUNTING",
             f"finding_history has {len(history) if isinstance(history, list) else history!r} entries")
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
        if final:
            _require(isinstance(entry, Mapping) and entry.get("candidate_after") is None
                     and entry.get("verdict") == "pass", "D3_PASS_MUTATES_CANDIDATE",
                     f"the final round {number} did not pass the candidate unchanged")
        entry = _check_round(entry, number=number, role=REVIEWER_ROLE, provider=provider,
                             status="independent_pass" if final else "revised_candidate_valid",
                             correction_of_round=None)
        _require(entry.get("candidate_before") == latest, "D3_CANDIDATE_LINK",
                 f"round {number} reviewed {entry.get('candidate_before')!r}, not the preceding candidate")

        relative = f"rounds/{number:02d}/review.json"
        path = confined(Path(run_dir), relative)
        _require(path.is_file(), "D3_FINDING_RESOLUTION", f"{relative} is missing")
        data = path.read_bytes()
        manifest[relative] = hashlib.sha256(data).hexdigest()
        try:
            review, unresolved = validate_decomposition_review(
                parse_json_object(data, relative),
                expected_candidate_sha256=latest["sha256"],
                round_number=number,
                prior_unresolved_findings=unresolved,
                all_prior_finding_ids=frozenset(seen_ids),
            )
        except Exception as exc:  # the policy's own refusal, whatever its type
            raise ReviewChainError("D3_FINDING_RESOLUTION", f"{relative}: {exc}") from exc
        seen_ids.update(finding.finding_id for finding in review.findings)
        recorded = history[number - 2]
        _require(isinstance(recorded, Mapping) and recorded.get("verdict") == review.verdict
                 and recorded.get("reviewed_candidate_sha256") == latest["sha256"],
                 "D3_FINDING_RESOLUTION", f"finding_history[{number - 2}] does not match {relative}")
        _require(entry.get("verdict") == review.verdict, "D3_FINDING_RESOLUTION",
                 f"round {number} verdict {entry.get('verdict')!r} differs from {relative}")

        if final:
            _require(review.verdict == "pass" and review.revised_decomposition is None,
                     "D3_PASS_MUTATES_CANDIDATE", f"{relative} is not a clean PASS")
            _require(not unresolved, "D3_FINDING_RESOLUTION",
                     f"blocking findings remain unresolved at the final PASS: {sorted(unresolved)}")
            approver = provider
        else:
            _require(review.verdict == "revise", "D3_REVISION", f"{relative} is not a revision")
            revised = _candidate(entry.get("candidate_after"), label=f"round {number} revision")
            _require(revised.get("sha256") != latest["sha256"]
                     and revised.get("version") == latest["version"] + 1
                     and revised.get("author_provider") == provider, "D3_REVISION",
                     f"round {number} revision {revised!r} does not follow {latest!r} as {provider!r}")
            latest = revised

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
        "review_sha256": manifest,
    }
