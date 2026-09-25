"""Render a GER problem packet from a decomposition run that needs contract review.

When a stopped decomposition run is diagnosed CONTRACT (the run asked for
human or design authority), the GER Agent needs the evidence in one place:
the reviewer findings, the questions and assumptions every author,
correction or replacement raised (including rejected ones), and the exact
parent-contract clauses the findings cite. This module builds that packet
deterministically from the run's retained artifacts. It makes no model call,
proposes no contract text, approves nothing and edits nothing.

Every emitted value is bound to its source: provider outputs to the round's
retained AgentRuntime request and result (invocation id, role, provider,
model), reviews to their retained files and history entries, published
candidates to their recorded identity. "CONTRACT" means the contract needs
review, not that it is defective: the packet says so, and a clause reference
is quoted only when it resolves against the retained parent contract the run
used; anything else is listed as unresolved rather than guessed from current
main. The spec is C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md,
Part C, as scoped in Astra round 20.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from TaskDecomposition.context_builder import ContextPackage
from TaskDecomposition.contracts import DecompositionResult
from TaskDecomposition.review_contracts import DecompositionReviewResult
from TaskDecomposition.round_robin_decomposition import candidate_sha256
from TaskDecomposition.run_diagnosis import (
    DiagnosisEvidenceError,
    confined,
    expected_invocation_id,
    parse_json_object,
)

PACKET_SCHEMA_VERSION = "decomposition-ger-problem/v1"
AUTHORITY = "diagnostic_only_not_applied"
PROVIDER_IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}
_CLAUSE_REFERENCE = re.compile(r"(NSC-\d+)\s+([A-Z]{2,4}-\d+)")
_TASK_REFERENCE = re.compile(r"NSC-\d+")
_ENTRY_COLLECTIONS = (
    ("acceptance_criteria", "criterion_id"),
    ("completion_gates", "gate_id"),
    ("downstream_integration_obligations", "obligation_id"),
)


class ProblemPacketError(ValueError):
    """The run cannot support a GER problem packet."""


class _Reader:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.hashes: dict[str, str] = {}

    def json(self, relative: str) -> dict[str, Any]:
        try:
            path = confined(self.run_dir, relative)
            if not path.is_file():
                raise DiagnosisEvidenceError(f"{relative} is missing")
            data = path.read_bytes()
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
            return parse_json_object(data, relative)
        except DiagnosisEvidenceError as exc:
            raise ProblemPacketError(str(exc)) from exc


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ProblemPacketError(detail)


def _round_directory(entry: Mapping[str, Any]) -> str:
    return f"{entry['round_number']:02d}" + ("-correction" if entry.get("correction_of_round") else "")


def _runtime_output(reader: _Reader, run_result: Mapping[str, Any], entry: Mapping[str, Any]) -> Any:
    """The round's provider output, bound to its retained AgentRuntime evidence."""

    number, role = entry.get("round_number"), entry.get("role")
    _require(type(number) is int and isinstance(role, str), "a round has no integer number or role")
    invocation = expected_invocation_id(
        run_result["task_id"], run_result["run_id"], number, role,
        correction=entry.get("correction_of_round") is not None)
    base = f"rounds/{_round_directory(entry)}/agent_runtime/{invocation}"
    request = reader.json(f"{base}/request.json")
    result = reader.json(f"{base}/result.json")
    checks = {
        "request run_id": (request.get("run_id"), invocation),
        "request role": (request.get("role"), role),
        "result run_id": (result.get("run_id"), invocation),
        "result role": (result.get("role"), role),
        "result provider": (result.get("provider"), entry.get("actual_provider")),
        "result model": (result.get("model"), entry.get("actual_model")),
        "result status": (result.get("status"), "succeeded"),
    }
    for name, (got, wanted) in checks.items():
        _require(got == wanted, f"round {number} {name} is {got!r}, expected {wanted!r}")
    _require(entry.get("actual_provider") == PROVIDER_IDENTIFIERS.get(entry.get("requested_provider")),
             f"round {number} ran on {entry.get('actual_provider')!r}, not its requested provider")
    return result.get("structured_output")


def _parsed_review(value: Any, label: str) -> dict[str, Any]:
    try:
        return DecompositionReviewResult.from_dict(value).to_dict()
    except Exception as exc:  # the contract's own refusal, whatever its type
        raise ProblemPacketError(f"{label} is not a valid review: {exc}") from exc


def _questions(candidate: Any) -> dict[str, list]:
    candidate = candidate if isinstance(candidate, Mapping) else {}
    return {
        "unresolved_questions": [str(q) for q in candidate.get("unresolved_questions") or []],
        "unsupported_assumptions": [
            q if isinstance(q, str) else json.dumps(q, sort_keys=True)
            for q in candidate.get("unsupported_assumptions") or []],
    }


def _parent_clauses(contract: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    clauses: dict[str, dict[str, str]] = {}
    for collection, id_field in _ENTRY_COLLECTIONS:
        for entry in contract.get(collection) or []:
            if isinstance(entry, Mapping) and isinstance(entry.get(id_field), str):
                clauses[entry[id_field]] = {
                    "collection": collection,
                    "requirement": str(entry.get("requirement", "")),
                }
    return clauses


def _resolve_references(references: Any, parent_id: str,
                        clauses: Mapping[str, Mapping[str, str]]) -> tuple[list, list]:
    quoted, unresolved = [], []
    for reference in references if isinstance(references, list) else []:
        text = str(reference)
        match = _CLAUSE_REFERENCE.fullmatch(text.strip())
        if match and match.group(1) == parent_id and match.group(2) in clauses:
            clause = clauses[match.group(2)]
            quoted.append({"reference": text, "entry_id": match.group(2), **clause})
        elif text.strip() == parent_id:
            quoted.append({"reference": text, "entry_id": None, "collection": "whole parent contract",
                           "requirement": "(the parent contract as a whole; no single clause cited)"})
        else:
            reason = ("names another task; not quoted from this run's retained context"
                      if _TASK_REFERENCE.match(text.strip()) else "not a clause of the retained parent contract")
            unresolved.append({"reference": text, "reason": reason})
    return quoted, unresolved


def build_problem_packet(run_dir: Path, diagnosis: Mapping[str, Any],
                         run_result: Mapping[str, Any]) -> dict[str, Any]:
    """The packet's structured content, from authenticated retained evidence."""

    if (diagnosis.get("primary") or {}).get("route") != "CONTRACT":
        raise ProblemPacketError(
            f"a GER problem packet is only built for a CONTRACT diagnosis, not "
            f"{(diagnosis.get('primary') or {}).get('route')!r}")
    reader = _Reader(run_dir)
    context = ContextPackage.from_payload(reader.json("context.json"))
    _require(context.semantic_sha256 == run_result.get("context_sha256"),
             "retained context does not hash to the run's context_sha256")
    payload = context.to_dict()
    selected = payload["selected_task"]
    _require(selected.get("d1a_semantic_parent_identity") == run_result.get("d1a_semantic_parent_identity"),
             "retained context names another parent identity than the run result")
    contract = selected["contract"]
    parent_id = contract["id"]
    clauses = _parent_clauses(contract)
    rounds = [entry for entry in run_result.get("rounds") or [] if isinstance(entry, Mapping)]

    raised = []
    for entry in rounds:
        stage = ("correction" if entry.get("correction_of_round") else
                 "author" if entry.get("role") == "task_decomposer" else "reviewer replacement")
        if entry.get("agent_status") != "succeeded":
            continue  # no provider output to quote
        output = _runtime_output(reader, run_result, entry)
        candidate = output if entry.get("role") == "task_decomposer" else (
            output.get("revised_decomposition") if isinstance(output, Mapping) else None)
        after = entry.get("candidate_after")
        if isinstance(after, Mapping):
            published = reader.json(f"rounds/{_round_directory(entry)}/candidate.json")
            identity = reader.json(f"rounds/{_round_directory(entry)}/candidate_identity.json")
            _require(dict(identity) == dict(after), f"round {entry['round_number']} candidate identity differs")
            try:
                digest = candidate_sha256(DecompositionResult.from_dict(published))
            except Exception as exc:  # the contract's own refusal
                raise ProblemPacketError(f"round {entry['round_number']} published candidate invalid: {exc}") from exc
            _require(digest == after.get("sha256"),
                     f"round {entry['round_number']} published candidate does not hash to its identity")
        found = _questions(candidate)
        if found["unresolved_questions"] or found["unsupported_assumptions"]:
            raised.append({"round_number": entry["round_number"], "stage": stage,
                           "round_status": entry.get("status"),
                           "decision": candidate.get("decision") if isinstance(candidate, Mapping) else None,
                           **found})

    reviews = []
    by_number = {entry["round_number"]: entry for entry in rounds
                 if entry.get("role") == "decomposition_reviewer" and entry.get("correction_of_round") is None}
    for entry in run_result.get("finding_history") or []:
        number = entry.get("round_number") if isinstance(entry, Mapping) else None
        _require(type(number) is int and number in by_number, "a finding_history entry names no reviewer round")
        round_entry = by_number[number]
        retained = reader.json(f"rounds/{number:02d}/review_history_entry.json")
        review = _parsed_review(reader.json(f"rounds/{number:02d}/review.json"), f"round {number} review.json")
        output = _parsed_review(_runtime_output(reader, run_result, round_entry), f"round {number} runtime output")
        _require(output == review, f"round {number} runtime output is not its review.json")
        for field in ("verdict", "summary", "findings", "prior_finding_resolutions", "reviewed_candidate_sha256"):
            _require(entry.get(field) == retained.get(field) == review.get(field),
                     f"round {number} {field} differs between the result and retained files")
        _require(entry.get("reviewer_provider") == retained.get("reviewer_provider")
                 == round_entry.get("requested_provider"),
                 f"round {number} reviewer_provider differs from the round that ran")
        findings = []
        for finding in entry.get("findings") or []:
            quoted, unresolved = _resolve_references(finding.get("affected_contracts"), parent_id, clauses)
            findings.append({
                "finding_id": finding.get("finding_id"),
                "severity": finding.get("severity"),
                "category": finding.get("category"),
                "problem": finding.get("problem"),
                "required_resolution": finding.get("required_resolution"),
                "quoted_parent_clauses": quoted,
                "unresolved_references": unresolved,
            })
        reviews.append({"round_number": number, "reviewer_provider": entry.get("reviewer_provider"),
                        "verdict": entry.get("verdict"), "summary": entry.get("summary"),
                        "findings": findings,
                        "prior_finding_resolutions": list(entry.get("prior_finding_resolutions") or [])})

    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "authority": AUTHORITY,
        "label": "Unapproved decomposition diagnostic - evidence only",
        "meaning": "The run asked for human or design authority: the contract requires review. "
                   "This does not establish that the contract is defective.",
        "task_id": run_result.get("task_id"),
        "run_id": run_result.get("run_id"),
        "parent_identity": selected.get("d1a_semantic_parent_identity"),
        "task_execution_identity": selected.get("task_execution_identity"),
        "source_identity": payload.get("source_identity"),
        "diagnosis": {"primary": diagnosis.get("primary"), "secondary": diagnosis.get("secondary"),
                      "classifier_version": diagnosis.get("classifier_version")},
        "reviews": reviews,
        "questions_and_assumptions_raised": raised,
        "input_sha256": {**dict(diagnosis.get("input_manifest") or {}), **reader.hashes},
        "retry_authorized": False,
    }


def render_problem_markdown(packet: Mapping[str, Any]) -> str:
    """GER_PROBLEM.md: the same content, for the GER Agent to read."""

    lines = [
        f"# {packet['label']}",
        "",
        f"**Task:** {packet['task_id']}  **Run:** {packet['run_id']}  **Authority:** {packet['authority']}",
        "",
        packet["meaning"],
        "No replacement contract text, approval or GER decision is proposed here.",
        "",
        f"**Parent identity:** `{json.dumps(packet['parent_identity'], sort_keys=True)}`",
        f"**Diagnosis:** {packet['diagnosis']['primary']['route']} / {packet['diagnosis']['primary']['reason_code']}",
        "",
    ]
    for entry in packet["questions_and_assumptions_raised"]:
        lines += [f"## Round {entry['round_number']} {entry['stage']} ({entry['round_status']}, "
                  f"decision {entry['decision']})", ""]
        lines += [f"- Question: {q}" for q in entry["unresolved_questions"]]
        lines += [f"- Unsupported assumption: {q}" for q in entry["unsupported_assumptions"]]
        lines.append("")
    for review in packet["reviews"]:
        lines += [f"## Round {review['round_number']} review ({review['reviewer_provider']}, {review['verdict']})",
                  "", str(review.get("summary") or ""), ""]
        for resolution in review["prior_finding_resolutions"]:
            lines.append(f"- Earlier finding {resolution.get('finding_id')}: {resolution.get('status')}")
        if review["prior_finding_resolutions"]:
            lines.append("")
        for finding in review["findings"]:
            lines += [f"### {finding['finding_id']} ({finding['severity']}, {finding['category']})", "",
                      f"**Problem:** {finding['problem']}", "",
                      f"**Required resolution (reviewer's words):** {finding['required_resolution']}", ""]
            for clause in finding["quoted_parent_clauses"]:
                lines += [f"> **{clause['reference']}** ({clause['collection']}): {clause['requirement']}", ""]
            for item in finding["unresolved_references"]:
                lines += [f"- Unresolved reference `{item['reference']}`: {item['reason']}"]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def publish_problem_packet(out_dir: Path, packet: Mapping[str, Any]) -> dict[str, str]:
    """Write GER_PROBLEM.md and MANIFEST.json into a directory that must not exist."""

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ProblemPacketError(f"refusing to overwrite an existing packet directory: {out_dir}")
    out_dir.mkdir(parents=True)
    markdown = render_problem_markdown(packet).encode("utf-8")
    (out_dir / "GER_PROBLEM.md").write_bytes(markdown)
    manifest = {**packet, "ger_problem_md_sha256": hashlib.sha256(markdown).hexdigest()}
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (out_dir / "MANIFEST.json").write_bytes(data)
    return {"GER_PROBLEM.md": hashlib.sha256(markdown).hexdigest(),
            "MANIFEST.json": hashlib.sha256(data).hexdigest()}
