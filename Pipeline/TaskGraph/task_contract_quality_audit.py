from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "Tasks"

FUTURE_GATE_PATTERNS = (
    re.compile(r"\bonce\b.{0,120}\b(exists?|implemented|available|completed?|created|added|integrated)\b", re.IGNORECASE),
    re.compile(r"\bwhen\b.{0,120}\b(exists?|implemented|available|completed?|created|added|integrated)\b", re.IGNORECASE),
    re.compile(r"\bafter\b.{0,120}\b(exists?|implemented|available|completed?|created|added|integrated)\b", re.IGNORECASE),
    re.compile(r"\bfuture\b", re.IGNORECASE),
    re.compile(r"\bdownstream\b", re.IGNORECASE),
    re.compile(r"\bwhen those systems exist\b", re.IGNORECASE),
)

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


class TaskContractQualityAuditError(RuntimeError):
    """Raised when task contracts cannot be audited safely."""


@dataclass(frozen=True)
class QualityFinding:
    finding_type: str
    task_id: str
    entry_ids: tuple[str, ...]
    message: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_type": self.finding_type,
            "task_id": self.task_id,
            "entry_ids": list(self.entry_ids),
            "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class QualityAudit:
    contract_count: int
    findings: tuple[QualityFinding, ...]

    @property
    def duplicate_acceptance_findings(self) -> tuple[QualityFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.finding_type == "duplicate_or_near_duplicate_acceptance_criteria"
        )

    @property
    def future_gate_findings(self) -> tuple[QualityFinding, ...]:
        return tuple(
            finding
            for finding in self.findings
            if finding.finding_type == "future_dependent_completion_gate"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "contract_count": self.contract_count,
            "finding_count": len(self.findings),
            "duplicate_acceptance_finding_count": len(self.duplicate_acceptance_findings),
            "future_gate_finding_count": len(self.future_gate_findings),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def _load_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskContractQualityAuditError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TaskContractQualityAuditError(f"Task contract must contain an object: {path}")
    if value.get("schema_version") != "2.0":
        raise TaskContractQualityAuditError(
            f"Quality audit requires uniform schema 2.0; {path.name} has {value.get('schema_version')!r}."
        )
    if value.get("id") != path.stem:
        raise TaskContractQualityAuditError(
            f"Task filename/id mismatch: {path.name} contains {value.get('id')!r}."
        )
    return value


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _meaningful_tokens(value: Any) -> set[str]:
    return {
        token
        for token in _normalize_text(value).split()
        if token not in STOP_WORDS and len(token) > 1
    }


def _entry_text(entry: dict[str, Any]) -> str:
    return str(entry.get("requirement") or "").strip()


def _entry_id(entry: dict[str, Any], field: str, fallback_index: int) -> str:
    value = entry.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"index-{fallback_index}"


def _acceptance_similarity(left: str, right: str) -> tuple[float, float]:
    left_normalized = _normalize_text(left)
    right_normalized = _normalize_text(right)
    sequence_ratio = SequenceMatcher(None, left_normalized, right_normalized).ratio()

    left_tokens = _meaningful_tokens(left)
    right_tokens = _meaningful_tokens(right)
    union = left_tokens | right_tokens
    token_jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    return sequence_ratio, token_jaccard


def _find_acceptance_duplicates(task: dict[str, Any]) -> list[QualityFinding]:
    task_id = str(task["id"])
    entries = task.get("acceptance_criteria")
    if not isinstance(entries, list):
        raise TaskContractQualityAuditError(f"{task_id}.acceptance_criteria must be a list.")

    findings: list[QualityFinding] = []
    for left_index, left in enumerate(entries):
        if not isinstance(left, dict):
            raise TaskContractQualityAuditError(
                f"{task_id}.acceptance_criteria[{left_index}] must be an object."
            )
        left_text = _entry_text(left)
        if not left_text:
            continue
        for right_index in range(left_index + 1, len(entries)):
            right = entries[right_index]
            if not isinstance(right, dict):
                raise TaskContractQualityAuditError(
                    f"{task_id}.acceptance_criteria[{right_index}] must be an object."
                )
            right_text = _entry_text(right)
            if not right_text:
                continue

            sequence_ratio, token_jaccard = _acceptance_similarity(left_text, right_text)
            exact = _normalize_text(left_text) == _normalize_text(right_text)
            near_duplicate = (
                len(_meaningful_tokens(left_text)) >= 6
                and len(_meaningful_tokens(right_text)) >= 6
                and sequence_ratio >= 0.78
                and token_jaccard >= 0.62
            )
            if not exact and not near_duplicate:
                continue

            left_id = _entry_id(left, "criterion_id", left_index)
            right_id = _entry_id(right, "criterion_id", right_index)
            findings.append(
                QualityFinding(
                    finding_type="duplicate_or_near_duplicate_acceptance_criteria",
                    task_id=task_id,
                    entry_ids=(left_id, right_id),
                    message=(
                        "Acceptance criteria appear to describe the same contract obligation; "
                        "review whether one should be removed or merged."
                    ),
                    evidence=(
                        left_text,
                        right_text,
                        f"sequence_ratio={sequence_ratio:.3f}",
                        f"token_jaccard={token_jaccard:.3f}",
                    ),
                )
            )
    return findings


def _find_future_dependent_gates(task: dict[str, Any]) -> list[QualityFinding]:
    task_id = str(task["id"])
    entries = task.get("completion_gates")
    if not isinstance(entries, list):
        raise TaskContractQualityAuditError(f"{task_id}.completion_gates must be a list.")

    findings: list[QualityFinding] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TaskContractQualityAuditError(
                f"{task_id}.completion_gates[{index}] must be an object."
            )
        gate_id = _entry_id(entry, "gate_id", index)
        requirement = _entry_text(entry)
        reference = str(entry.get("reference") or "").strip()
        searchable = f"{reference} {requirement}".strip()
        matched = sorted(
            {
                match.group(0)
                for pattern in FUTURE_GATE_PATTERNS
                for match in pattern.finditer(searchable)
            }
        )
        if not matched:
            continue
        findings.append(
            QualityFinding(
                finding_type="future_dependent_completion_gate",
                task_id=task_id,
                entry_ids=(gate_id,),
                message=(
                    "Completion gate may depend on a future/downstream system and therefore may "
                    "belong under downstream_integration_obligations instead. Human review is required."
                ),
                evidence=(reference, requirement, *matched),
            )
        )
    return findings


def audit_contracts(tasks_dir: Path = TASKS_DIR) -> QualityAudit:
    paths = sorted(tasks_dir.glob("NSC-*.yaml"))
    if not paths:
        raise TaskContractQualityAuditError(f"No task contracts found under {tasks_dir}.")

    findings: list[QualityFinding] = []
    for path in paths:
        task = _load_contract(path)
        findings.extend(_find_acceptance_duplicates(task))
        findings.extend(_find_future_dependent_gates(task))

    findings.sort(key=lambda finding: (finding.task_id, finding.finding_type, finding.entry_ids))
    return QualityAudit(contract_count=len(paths), findings=tuple(findings))


def _print_human(audit: QualityAudit) -> None:
    print("Task contract schema-v2 quality audit: PASS")
    print(f"Contracts:                              {audit.contract_count}")
    print(f"Duplicate/near-duplicate AC findings:   {len(audit.duplicate_acceptance_findings)}")
    print(f"Future-dependent gate candidates:       {len(audit.future_gate_findings)}")
    print(f"Total review findings:                  {len(audit.findings)}")

    if not audit.findings:
        print("No contract-quality review candidates found.")
        return

    print("\nREVIEW CANDIDATES (heuristic; do not auto-edit):")
    for finding in audit.findings:
        entry_ids = ", ".join(finding.entry_ids)
        print(f"\n- {finding.task_id} [{finding.finding_type}] {entry_ids}")
        print(f"  {finding.message}")
        for evidence in finding.evidence:
            if evidence:
                print(f"  evidence: {evidence}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Heuristically audit schema-v2 task contracts for duplicate acceptance criteria "
            "and completion gates that may actually be downstream integration obligations."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print the audit as JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 2 when review findings exist. Default remains exit 0 because findings require human judgment.",
    )
    args = parser.parse_args(argv)

    try:
        audit = audit_contracts()
    except TaskContractQualityAuditError as exc:
        print(f"Task contract schema-v2 quality audit: FAIL\n{exc}")
        return 1

    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_human(audit)
    if args.strict and audit.findings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
