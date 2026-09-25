"""Verify the designer/bookkeeper evidence of an opted-in D1B.2 run.

A run with a bookkeeper is admissible only if its retained bytes prove:

- round 1's own runtime output is the published ownership sheet, and the
  sheet hashes to the recorded digest and is a complete split of the parent;
- every bookkeeping attempt is that attempt's retained runtime invocation, on
  the designer's provider, at the recorded bookkeeper model, and was sent the
  frozen sheet;
- every attempt but the last really departed from the sheet or failed
  validation, and the last states the sheet exactly and is the round 1
  candidate the reviewer saw.

Nothing is taken from the run result's summaries alone. The module is pure
and raises BookkeepingEvidenceError; it returns the hashes of every file read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION
from TaskDecomposition.bookkeeper_prompts import _sheet_json
from TaskDecomposition.bookkeeping_skeleton import impose_skeleton, result_skeleton
from TaskDecomposition.ownership_sheet import (
    OwnershipSheetError,
    conformance_problems,
    sheet_sha256,
    validate_sheet,
)
from TaskDecomposition.run_diagnosis import (
    DiagnosisEvidenceError,
    confined,
    expected_invocation_id,
    parse_json_object,
)

PROVIDER_IDENTIFIERS = {"claude": "claude-code", "codex": "openai-codex"}
DESIGNER_ROLE = "task_decomposer"
BOOKKEEPER_ROLE = "decomposition_bookkeeper"
SHEET_NAME = "ownership_sheet.json"
MAX_ATTEMPTS = 2

CandidateDigest = Callable[[Mapping[str, Any]], tuple[str, "str | None"]]


class BookkeepingEvidenceError(ValueError):
    """The retained run does not prove its designer/bookkeeper split."""


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise BookkeepingEvidenceError(detail)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class _Files:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.hashes: dict[str, str] = {}

    def json(self, relative: str, label: str) -> dict[str, Any]:
        try:
            path = confined(self.run_dir, relative)
            _require(path.is_file(), f"{label} is missing: {relative}")
            data = path.read_bytes()
            self.hashes[relative] = hashlib.sha256(data).hexdigest()
            return parse_json_object(data, label)
        except DiagnosisEvidenceError as exc:
            raise BookkeepingEvidenceError(f"{label}: {exc}") from exc


def _runtime(files: _Files, directory: str, invocation: str, *, role: str, provider: str,
             model: str | None, label: str, timeout: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = f"rounds/{directory}/agent_runtime/{invocation}"
    request = files.json(f"{base}/request.json", f"{label} request")
    result = files.json(f"{base}/result.json", f"{label} result")
    checks = {
        "request schema_version": (request.get("schema_version"), AGENT_INVOCATION_REQUEST_SCHEMA_VERSION),
        "request run_id": (request.get("run_id"), invocation),
        "request role": (request.get("role"), role),
        "result run_id": (result.get("run_id"), invocation),
        "result role": (result.get("role"), role),
        "result provider": (result.get("provider"), PROVIDER_IDENTIFIERS[provider]),
        "result status": (result.get("status"), "succeeded"),
    }
    if model is not None:
        checks["result model"] = (result.get("model"), model)
    for name, (got, wanted) in checks.items():
        _require(got == wanted, f"{label} {name} is {got!r}, expected {wanted!r}")
    if timeout is not None:
        budgets = request.get("budgets") if isinstance(request.get("budgets"), Mapping) else {}
        _require(budgets.get("timeout_seconds") == timeout,
                 f"{label} ran with timeout {budgets.get('timeout_seconds')!r}, the run recorded {timeout!r}")
    return request, result


def verify_bookkeeping(
    *, run_dir: Path, run_result: Mapping[str, Any], author_entry: Mapping[str, Any],
    first_provider: str, parent_contract: Mapping[str, Any], candidate_digest: CandidateDigest,
    designer_timeout: float | None = None,
) -> dict[str, Any]:
    """Return the verified bookkeeping summary and the hashes of every file read."""

    record = run_result.get("designer_bookkeeper")
    _require(isinstance(record, Mapping), "the run records no designer_bookkeeper evidence")
    model = record.get("bookkeeper_model")
    attempts = record.get("attempts")
    _require(isinstance(model, str) and model, "the bookkeeper model is not recorded")

    _require(isinstance(attempts, list) and 1 <= len(attempts) <= MAX_ATTEMPTS,
             f"the run records {len(attempts) if isinstance(attempts, list) else attempts!r} bookkeeping attempts")
    _require(first_provider in PROVIDER_IDENTIFIERS, f"unknown designer provider {first_provider!r}")
    corrected = author_entry.get("correction_of_round") is not None
    _require(author_entry.get("round_number") == 1 and author_entry.get("role") == DESIGNER_ROLE
             and author_entry.get("correction_of_round") in (None, 1)
             and author_entry.get("status") == ("correction_candidate_valid" if corrected else "candidate_valid"),
             "round 1 is not the designer round that produced the candidate")
    designer_directory = "01-correction" if corrected else "01"
    sheet_path = f"rounds/{designer_directory}/{SHEET_NAME}"
    _require(record.get("sheet_path") == sheet_path,
             f"the sheet path is {record.get('sheet_path')!r}, expected {sheet_path!r}")
    files = _Files(Path(run_dir))
    task_id, run_id = run_result.get("task_id"), run_result.get("run_id")

    sheet = files.json(sheet_path, "ownership sheet")
    _require(sheet_sha256(sheet) == record.get("sheet_sha256"),
             "the ownership sheet does not hash to the recorded sheet_sha256")
    try:
        validate_sheet(sheet, parent_contract)
    except OwnershipSheetError as exc:
        raise BookkeepingEvidenceError(f"the ownership sheet is not a complete split: {exc}") from exc
    designer_invocation = expected_invocation_id(task_id, run_id, 1, DESIGNER_ROLE, correction=corrected)
    _, designer = _runtime(files, designer_directory, designer_invocation, role=DESIGNER_ROLE, provider=first_provider,
                           model=author_entry.get("actual_model"), label="round 1 designer",
                           timeout=designer_timeout)
    _require(_canonical(designer.get("structured_output")) == _canonical(sheet),
             f"the designer's runtime output is not {sheet_path}")

    sheet_text = _sheet_json(sheet)
    skeleton = result_skeleton(sheet)
    final_output: Any = None
    for index, attempt in enumerate(attempts, start=1):
        label = f"bookkeeping attempt {index}"
        last = index == len(attempts)
        directory = f"01-bookkeeper-{index}"
        invocation = expected_invocation_id(task_id, run_id, 1, BOOKKEEPER_ROLE, correction=False,
                                            bookkeeping_attempt=index)
        _require(isinstance(attempt, Mapping) and attempt.get("attempt") == index
                 and attempt.get("directory") == directory and attempt.get("invocation_id") == invocation
                 and attempt.get("requested_provider") == first_provider
                 and attempt.get("actual_model") == model,
                 f"{label} is not recorded as invocation {invocation} on {first_provider} at {model}")
        retained = files.json(f"rounds/{directory}/bookkeeping_attempt.json", f"{label} record")
        _require(_canonical(retained) == _canonical(attempt), f"{label} record differs from the run result")
        request, result = _runtime(files, directory, invocation, role=BOOKKEEPER_ROLE, provider=first_provider,
                                   model=model, label=label, timeout=designer_timeout)
        prompt = request.get("prompt")
        _require(isinstance(prompt, str) and sheet_text in prompt, f"{label} was not sent the frozen sheet")
        # The candidate is the model's prose on the code's structure, so the
        # imposition is recomputed here from the retained runtime output.
        output = impose_skeleton(skeleton, result.get("structured_output"))
        problems = conformance_problems(sheet, output)
        digest: tuple[str, str | None] | None = None
        if not problems:
            try:
                digest = candidate_digest(output)
            except Exception as exc:  # the validator's own refusal, whatever its type
                problems = [f"deterministic validation failed: {exc}"]
        if last:
            summary = author_entry.get("candidate_after")
            _require(attempt.get("status") == "conformed" and attempt.get("problems") == [] and not problems,
                     f"the last {label} does not state the sheet: {problems[:3]}")
            _require(isinstance(summary, Mapping) and attempt.get("candidate_after") == summary
                     and digest == (summary.get("sha256"), summary.get("graph_delta_plan_id")),
                     f"the last {label}'s output is not the round 1 candidate")
            final_output = output
        else:
            _require(attempt.get("status") == "rejected" and problems and attempt.get("problems"),
                     f"{label} is recorded as rejected but its output states the sheet")
    return {
        "bookkeeper_model": model,
        "sheet_sha256": record["sheet_sha256"],
        "attempts": len(attempts),
        "candidate_sha256": author_entry["candidate_after"]["sha256"],
        "conformed": final_output is not None,
        "evidence_sha256": dict(files.hashes),
    }
