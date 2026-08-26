"""Immutable structured contracts for D1B.2 decomposition cross-review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from TaskDecomposition.contracts import (
    DecompositionContractError,
    DecompositionResult,
    SHA256_RE,
    _list,
    _object,
    _snapshot,
    _string_tuple,
    _text,
)


REVIEW_RESULT_SCHEMA_VERSION = "1.0"
REVIEW_VERDICTS = frozenset({"pass", "revise", "needs_human"})
FINDING_SEVERITIES = frozenset({"blocking", "advisory"})
FINDING_CATEGORIES = frozenset(
    {
        "duplicate_responsibility",
        "hidden_integration",
        "unnecessary_integration",
        "completion_locality",
        "dependency_mapping",
        "requirement_coverage",
        "task_granularity",
        "authority_conflict",
        "candidate_correctness",
        "other",
    }
)
FINDING_RESOLUTION_STATUSES = frozenset(
    {"resolved", "still_blocking", "withdrawn"}
)
FINDING_ID_RE = re.compile(
    r"^round-[0-9]{2}-[a-z0-9]+(?:-[a-z0-9]+)*$"
)


class DecompositionReviewContractError(ValueError):
    """Raised when untrusted D1B.2 review output is structurally invalid."""


def _review_object(
    value: Any,
    label: str,
    required: set[str],
    optional: set[str] = frozenset(),
) -> dict[str, Any]:
    try:
        return _object(value, label, required, optional)
    except DecompositionContractError as exc:
        raise DecompositionReviewContractError(str(exc)) from exc


def _review_text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    try:
        return _text(value, label, allow_empty=allow_empty)
    except DecompositionContractError as exc:
        raise DecompositionReviewContractError(str(exc)) from exc


def _review_list(value: Any, label: str) -> list[Any]:
    try:
        return _list(value, label)
    except DecompositionContractError as exc:
        raise DecompositionReviewContractError(str(exc)) from exc


def _review_string_tuple(value: Any, label: str) -> tuple[str, ...]:
    try:
        return _string_tuple(value, label)
    except DecompositionContractError as exc:
        raise DecompositionReviewContractError(str(exc)) from exc


@dataclass(frozen=True)
class ReviewFinding:
    finding_id: str
    severity: str
    category: str
    affected_contracts: tuple[str, ...]
    problem: str
    required_resolution: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "ReviewFinding":
        value = _review_object(
            raw,
            label,
            {
                "finding_id",
                "severity",
                "category",
                "affected_contracts",
                "problem",
                "required_resolution",
            },
        )
        finding_id = _review_text(value["finding_id"], f"{label}.finding_id")
        if not FINDING_ID_RE.fullmatch(finding_id):
            raise DecompositionReviewContractError(
                f"{label}.finding_id must match {FINDING_ID_RE.pattern!r}."
            )
        severity = _review_text(value["severity"], f"{label}.severity")
        if severity not in FINDING_SEVERITIES:
            raise DecompositionReviewContractError(
                f"{label}.severity must be one of {sorted(FINDING_SEVERITIES)}."
            )
        category = _review_text(value["category"], f"{label}.category")
        if category not in FINDING_CATEGORIES:
            raise DecompositionReviewContractError(
                f"{label}.category must be one of {sorted(FINDING_CATEGORIES)}."
            )
        affected_contracts = _review_string_tuple(
            value["affected_contracts"], f"{label}.affected_contracts"
        )
        if not affected_contracts:
            raise DecompositionReviewContractError(
                f"{label}.affected_contracts must contain at least one existing or proposed contract identity."
            )
        return cls(
            finding_id,
            severity,
            category,
            affected_contracts,
            _review_text(value["problem"], f"{label}.problem"),
            _review_text(
                value["required_resolution"], f"{label}.required_resolution"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "category": self.category,
            "affected_contracts": list(self.affected_contracts),
            "problem": self.problem,
            "required_resolution": self.required_resolution,
        }


@dataclass(frozen=True)
class PriorFindingResolution:
    finding_id: str
    status: str
    explanation: str

    @classmethod
    def from_dict(cls, raw: Any, label: str) -> "PriorFindingResolution":
        value = _review_object(
            raw,
            label,
            {"finding_id", "status", "explanation"},
        )
        finding_id = _review_text(value["finding_id"], f"{label}.finding_id")
        if not FINDING_ID_RE.fullmatch(finding_id):
            raise DecompositionReviewContractError(
                f"{label}.finding_id must match {FINDING_ID_RE.pattern!r}."
            )
        status = _review_text(value["status"], f"{label}.status")
        if status not in FINDING_RESOLUTION_STATUSES:
            raise DecompositionReviewContractError(
                f"{label}.status must be one of {sorted(FINDING_RESOLUTION_STATUSES)}."
            )
        return cls(
            finding_id,
            status,
            _review_text(value["explanation"], f"{label}.explanation"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "status": self.status,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class DecompositionReviewResult:
    schema_version: str
    reviewed_candidate_sha256: str
    verdict: str
    summary: str
    findings: tuple[ReviewFinding, ...]
    prior_finding_resolutions: tuple[PriorFindingResolution, ...]
    revised_decomposition: DecompositionResult | None

    @classmethod
    def from_dict(cls, raw: Any) -> "DecompositionReviewResult":
        try:
            value = _snapshot(raw)
        except DecompositionContractError as exc:
            raise DecompositionReviewContractError(str(exc)) from exc
        value = _review_object(
            value,
            "decomposition_review",
            {
                "schema_version",
                "reviewed_candidate_sha256",
                "verdict",
                "summary",
                "findings",
                "prior_finding_resolutions",
                "revised_decomposition",
            },
        )
        schema_version = _review_text(
            value["schema_version"], "decomposition_review.schema_version"
        )
        if schema_version != REVIEW_RESULT_SCHEMA_VERSION:
            raise DecompositionReviewContractError(
                f"Unsupported decomposition review schema_version: {schema_version!r}."
            )
        candidate_sha = _review_text(
            value["reviewed_candidate_sha256"],
            "decomposition_review.reviewed_candidate_sha256",
        )
        if not SHA256_RE.fullmatch(candidate_sha):
            raise DecompositionReviewContractError(
                "decomposition_review.reviewed_candidate_sha256 must be lowercase SHA-256."
            )
        verdict = _review_text(value["verdict"], "decomposition_review.verdict")
        if verdict not in REVIEW_VERDICTS:
            raise DecompositionReviewContractError(
                f"decomposition_review.verdict must be one of {sorted(REVIEW_VERDICTS)}."
            )
        findings = tuple(
            ReviewFinding.from_dict(
                item, f"decomposition_review.findings[{index}]"
            )
            for index, item in enumerate(
                _review_list(value["findings"], "decomposition_review.findings")
            )
        )
        finding_ids = [finding.finding_id for finding in findings]
        if len(finding_ids) != len(set(finding_ids)):
            raise DecompositionReviewContractError(
                "decomposition_review.findings contains duplicate finding_id values."
            )
        resolutions = tuple(
            PriorFindingResolution.from_dict(
                item,
                f"decomposition_review.prior_finding_resolutions[{index}]",
            )
            for index, item in enumerate(
                _review_list(
                    value["prior_finding_resolutions"],
                    "decomposition_review.prior_finding_resolutions",
                )
            )
        )
        resolution_ids = [resolution.finding_id for resolution in resolutions]
        if len(resolution_ids) != len(set(resolution_ids)):
            raise DecompositionReviewContractError(
                "decomposition_review.prior_finding_resolutions contains duplicate finding_id values."
            )
        raw_revised = value["revised_decomposition"]
        if raw_revised is None:
            revised = None
        else:
            try:
                revised = DecompositionResult.from_dict(raw_revised)
            except DecompositionContractError as exc:
                raise DecompositionReviewContractError(
                    f"decomposition_review.revised_decomposition is invalid: {exc}"
                ) from exc
        return cls(
            schema_version,
            candidate_sha,
            verdict,
            _review_text(value["summary"], "decomposition_review.summary"),
            findings,
            resolutions,
            revised,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reviewed_candidate_sha256": self.reviewed_candidate_sha256,
            "verdict": self.verdict,
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
            "prior_finding_resolutions": [
                resolution.to_dict()
                for resolution in self.prior_finding_resolutions
            ],
            "revised_decomposition": (
                self.revised_decomposition.to_dict()
                if self.revised_decomposition is not None
                else None
            ),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
