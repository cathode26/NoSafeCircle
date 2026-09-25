"""Replay retained designer sheets and every v2 reviewer-sheet compilation.

Historical round-1-only evidence keeps its own reader. New evidence binds the
sheet, revision feedback, prompt, runtime invocation and imposed result of
all accepted compilations. Every consumed file is hashed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION
from Pipeline.AgentRuntime.schema_validation import validate_instance
from TaskDecomposition.bookkeeper_prompts import (
    _sheet_json, build_bookkeeper_prompt, build_bookkeeper_retry_prompt,
    build_bookkeeper_revision_prompt, build_bookkeeper_revision_retry_prompt,
)
from TaskDecomposition.context_builder import ContextPackage
from TaskDecomposition.contracts import DecompositionResult
from TaskDecomposition.schemas import DECOMPOSITION_RESULT_SCHEMA
from TaskDecomposition.bookkeeping_skeleton import impose_skeleton, result_skeleton, structural_slips
from TaskDecomposition.ownership_sheet import (
    OWNERSHIP_SHEET_SCHEMA,
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


def _verify_legacy_bookkeeping(
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
        output = impose_skeleton(skeleton, result.get("structured_output"), legacy_notes=True)
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


def _read_only(request: Mapping[str, Any], result: Mapping[str, Any], label: str) -> None:
    _require(request.get("allowed_capabilities") == ["repository_read", "repository_search"]
             and request.get("write_boundaries") == {"allowed_paths": [], "denied_paths": []},
             f"{label} request does not retain read-only execution boundaries")
    _require(result.get("claimed_changed_paths") == [] and result.get("claimed_test_commands") == []
             and result.get("claims_execution_occurred") is False,
             f"{label} result does not prove read-only execution")


def _schema(value: Any, schema: Mapping[str, Any], label: str) -> None:
    try:
        validate_instance(value, schema)
    except Exception as exc:
        raise BookkeepingEvidenceError(f"{label} does not match its structural schema: {exc}") from exc


def _sheet_review(value: Any, label: str) -> dict[str, Any]:
    from TaskDecomposition.review_contracts import OwnershipSheetReviewResult

    try:
        return OwnershipSheetReviewResult.from_dict(value).to_dict()
    except Exception as exc:
        raise BookkeepingEvidenceError(f"{label} is not a structurally valid sheet review: {exc}") from exc


def sheet_review_protocol(run_dir: Path, run_result: Mapping[str, Any]) -> bool:
    """Select v2 only from a consistent retained request and result."""

    files = _Files(Path(run_dir))
    request = files.json("decomposition_request.json", "decomposition request")
    record = run_result.get("designer_bookkeeper")
    markers = ("designer_bookkeeper_version", "ownership_sheet_review_version", "bookkeeper_provider")
    marked = any(key in request for key in markers)
    versioned = isinstance(record, Mapping) and "schema_version" in record
    if not marked and not versioned:
        _require(not request.get("bookkeeper_model") or isinstance(record, Mapping),
                 "the pinned bookkeeper run has no designer_bookkeeper evidence")
        return False
    _require(request.get("designer_bookkeeper_version") == "2.0"
             and request.get("ownership_sheet_review_version") == "1.1"
             and isinstance(record, Mapping) and record.get("schema_version") == "2.0",
             "the request/result designer_bookkeeper protocol markers are missing or inconsistent")
    _require(request.get("bookkeeper_provider") == record.get("bookkeeper_provider")
             and request.get("bookkeeper_model") == record.get("bookkeeper_model"),
             "the pinned bookkeeper provider/model differs from designer_bookkeeper")
    return True


def _verify_plan(
    payload: Mapping[str, Any], parent_contract: Mapping[str, Any],
    candidate: DecompositionResult, expected_plan_id: str,
) -> None:
    from graph_delta import plan_graph_delta
    from work_graph_transform import WorkGraphPlan

    # The overlay retains source order and the exact values each rewrite replaced.
    overlay = deepcopy(payload["proposed_graph_overlay"])
    allocation = payload["allocated_local_key_to_task_id"]
    added_ids = set(allocation.values())
    tasks = [task for task in overlay["tasks"] if task["id"] not in added_ids]
    changes = {change["dependent_task_id"]: change for change in payload["inbound_dependency_changes"]}
    for index, task in enumerate(tasks):
        if task["id"] == parent_contract["id"]:
            tasks[index] = deepcopy(dict(parent_contract))
        elif task["id"] in changes:
            change = changes[task["id"]]
            task["contract_revision"] = change["before_contract_revision"]
            task["depends_on"] = deepcopy(change["before_dependencies"])
    resource_changes = {change["resource_key"]: change for change in payload["resource_group_changes"]}
    groups = []
    for group in overlay["resource_groups"]:
        change = resource_changes.get(group["resource_key"])
        if change is None:
            groups.append(group)
        elif change["before"] is not None:
            groups.append(deepcopy(change["before"]))
    source = WorkGraphPlan(
        id_map={key: value for key, value in overlay["id_map"].items() if key not in allocation},
        tasks=tuple(tasks), resource_groups=tuple(groups),
        project_requirements=tuple(overlay["project_requirements"]))
    replayed = plan_graph_delta(source, candidate.parent_task, candidate)
    _require(replayed.plan_id == expected_plan_id and _canonical(replayed.to_dict()) == _canonical(payload),
             "the candidate graph plan differs from deterministic replay")


def _verify_compilation(
    *, run_dir: Path, run_result: Mapping[str, Any], compilation: Mapping[str, Any],
    source_entry: Mapping[str, Any], first_provider: str, parent_contract: Mapping[str, Any],
    candidate_digest: CandidateDigest, designer_timeout: float | None = None,
    prior_unresolved_findings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay one v2 sheet compilation without treating a failed result as a candidate."""

    files = _Files(Path(run_dir))
    record = run_result["designer_bookkeeper"]
    number = source_entry.get("round_number")
    _require(type(number) is int and number >= 1, "compilation source round is invalid")
    corrected = source_entry.get("correction_of_round") is not None
    directory = f"{number:02d}" + ("-correction" if corrected else "")
    role = DESIGNER_ROLE if number == 1 else "decomposition_reviewer"
    source_provider = source_entry.get("requested_provider")
    _require(source_provider in PROVIDER_IDENTIFIERS and source_entry.get("role") == role
             and isinstance(source_entry.get("actual_model"), str) and bool(source_entry["actual_model"]),
             "compilation source role/provider/model is invalid")
    invocation = expected_invocation_id(run_result["task_id"], run_result["run_id"], number, role,
                                        correction=corrected)
    sheet_path = f"rounds/{directory}/{SHEET_NAME}"
    input_path = f"rounds/{directory}/bookkeeping_input.json"
    expected = {"round_number": number, "source_role": role, "source_directory": directory,
                "source_invocation_id": invocation,
                "source_output_field": None if number == 1 else "revised_sheet",
                "sheet_path": sheet_path, "bookkeeping_input_path": input_path,
                "candidate_before": source_entry.get("candidate_before")}
    for key, value in expected.items():
        _require(compilation.get(key) == value, f"round {number} compilation {key} is not {value!r}")
    sheet = files.json(sheet_path, f"round {number} ownership sheet")
    _require(sheet_sha256(sheet) == compilation.get("sheet_sha256"),
             "the ownership sheet does not hash to the recorded sheet_sha256")
    _schema(sheet, OWNERSHIP_SHEET_SCHEMA, "ownership sheet")
    try:
        validate_sheet(sheet, parent_contract)
    except OwnershipSheetError as exc:
        raise BookkeepingEvidenceError(f"the ownership sheet is not a complete split: {exc}") from exc
    pinned = files.json("decomposition_request.json", "decomposition request")
    source_timeout = designer_timeout if number == 1 else pinned.get("reviewer_timeout_seconds")
    _require(isinstance(source_timeout, (int, float)) and not isinstance(source_timeout, bool) and source_timeout > 0,
             f"round {number} source has no pinned timeout")
    request, source = _runtime(files, directory, invocation, role=role, provider=source_provider,
                               model=source_entry.get("actual_model"), label=f"round {number} source",
                               timeout=source_timeout)
    _read_only(request, source, f"round {number} source")
    _require(source.get("schema_version") == "1.0" and source.get("failure_classification") == "none"
             and source_entry.get("actual_provider") == source.get("provider")
             and source_entry.get("agent_status") == "succeeded"
             and source_entry.get("agent_failure_classification") == "none",
             f"round {number} source runtime status/provider differs")
    _require(source_entry.get("agent_runtime_result_path")
             == f"rounds/{directory}/agent_runtime/{invocation}/result.json",
             f"round {number} source runtime result path differs")
    source_output = source.get("structured_output")
    if number == 1:
        _schema(source_output, OWNERSHIP_SHEET_SCHEMA, "designer output")
        _require(request.get("output_schema") == OWNERSHIP_SHEET_SCHEMA,
                 "the designer request selected a different sheet schema")
    else:
        from TaskDecomposition.review_schemas import OWNERSHIP_SHEET_REVIEW_SCHEMA
        _require(request.get("output_schema") == OWNERSHIP_SHEET_REVIEW_SCHEMA,
                 f"round {number} source request selected a different review schema")
        source_output = _sheet_review(source_output, f"round {number} source output")
        retained_review = files.json(f"rounds/{directory}/review.json", f"round {number} review")
        _require(source_output == _sheet_review(retained_review, f"round {number} retained review"),
                 f"round {number} runtime output is not its retained review")
    raw_sheet = source_output if number == 1 else source_output.get("revised_sheet")
    _require(_canonical(raw_sheet) == _canonical(sheet),
             f"round {number} source runtime output is not {sheet_path}")
    context_payload = files.json("context.json", "committed context")
    _require(context_payload.get("selected_task", {}).get("contract") == parent_contract,
             "the retained context has a different parent contract")
    context = ContextPackage.from_payload(context_payload)
    _require(context.semantic_sha256 == pinned.get("context_sha256") == run_result.get("context_sha256"),
             "the retained context does not match its pinned context_sha256")
    _require(request.get("context_paths") == context_payload.get("context_paths"),
             f"round {number} source context paths differ")
    inputs = files.json(input_path, f"round {number} bookkeeping input")
    _require(set(inputs) == {"sheet", "revision_input"} and inputs.get("sheet") == sheet,
             f"round {number} bookkeeping input does not contain its exact sheet")
    revision = inputs.get("revision_input")
    if number == 1:
        _require(revision is None and compilation.get("candidate_before") is None,
                 "initial compilation must not carry revision input")
    else:
        before = compilation.get("candidate_before")
        _require(isinstance(before, Mapping) and isinstance(revision, Mapping)
                 and set(revision) == {"previous_candidate", "review", "unresolved_findings"},
                 f"round {number} compilation lacks revision input")
        previous = revision["previous_candidate"]
        try:
            previous_digest = candidate_digest(previous)
        except Exception as exc:
            raise BookkeepingEvidenceError(f"round {number} previous candidate is invalid: {exc}") from exc
        _require(previous_digest == (before.get("sha256"), before.get("graph_delta_plan_id")),
                 f"round {number} revision input has a different previous candidate")
        _require(revision["review"] == source_output, f"round {number} revision feedback differs from its review")
        if prior_unresolved_findings is not None:
            findings = [value.to_dict() if hasattr(value, "to_dict") else value
                        for key, value in sorted(prior_unresolved_findings.items())]
            _require(revision["unresolved_findings"] == findings,
                     f"round {number} revision input has different unresolved findings")
    attempts = compilation.get("attempts")
    _require(isinstance(attempts, list) and 1 <= len(attempts) <= MAX_ATTEMPTS,
             f"round {number} compilation must have one or two attempts")
    model = record["bookkeeper_model"]
    skeleton = result_skeleton(sheet)
    rejected: Any = None
    problems: list[str] = []
    compiled = None
    final_output = None
    for index, attempt in enumerate(attempts, start=1):
        label = f"round {number} bookkeeping attempt {index}"
        attempt_directory = f"{number:02d}-bookkeeper-{index}"
        attempt_invocation = expected_invocation_id(run_result["task_id"], run_result["run_id"], number,
                                                    BOOKKEEPER_ROLE, correction=False,
                                                    bookkeeping_attempt=index)
        base = f"rounds/{attempt_directory}/agent_runtime/{attempt_invocation}"
        _require(isinstance(attempt, Mapping) and type(attempt.get("attempt")) is int and attempt["attempt"] == index
                 and attempt.get("directory") == attempt_directory
                 and attempt.get("invocation_id") == attempt_invocation
                 and attempt.get("requested_provider") == first_provider
                 and attempt.get("actual_provider") == PROVIDER_IDENTIFIERS[first_provider]
                 and attempt.get("actual_model") == model,
                 f"{label} is not recorded as invocation {attempt_invocation} on {first_provider} at {model}")
        retained = files.json(f"rounds/{attempt_directory}/bookkeeping_attempt.json", f"{label} record")
        _require(retained == attempt, f"{label} record differs from the run result")
        request, result = _runtime(files, attempt_directory, attempt_invocation, role=BOOKKEEPER_ROLE,
                                   provider=first_provider, model=model, label=label, timeout=designer_timeout)
        _read_only(request, result, label)
        _require(result.get("schema_version") == "1.0" and result.get("failure_classification") == "none"
                 and attempt.get("agent_failure_classification") == "none"
                 and attempt.get("agent_status") == "succeeded"
                 and attempt.get("agent_runtime_result_path") == f"{base}/result.json",
                 f"{label} runtime status/path differs from its record")
        _require(request.get("output_schema") == DECOMPOSITION_RESULT_SCHEMA
                 and request.get("context_paths") == context_payload.get("context_paths"),
                 f"{label} request schema/context paths differ")
        if revision is None:
            prompt = (build_bookkeeper_prompt(context, sheet) if index == 1
                      else build_bookkeeper_retry_prompt(sheet, rejected, problems))
        else:
            prompt = (build_bookkeeper_revision_prompt(context, sheet, **revision) if index == 1
                      else build_bookkeeper_revision_retry_prompt(context, sheet, rejected, problems, **revision))
        _require(request.get("prompt") == prompt, f"{label} prompt differs from its recorded sheet/revision input")
        raw = result.get("structured_output")
        _schema(raw, DECOMPOSITION_RESULT_SCHEMA, label)
        _require(attempt.get("structural_slips_corrected") == structural_slips(sheet, raw),
                 f"{label} structural corrections differ from deterministic replay")
        rejected = impose_skeleton(skeleton, raw)
        problems = conformance_problems(sheet, rejected)
        digest = None
        if not problems:
            try:
                digest = candidate_digest(rejected)
            except Exception as exc:
                problems = [f"deterministic validation failed: {exc}"]
        _require(attempt.get("problems") == problems, f"{label} problems differ from deterministic replay")
        if problems:
            _require(attempt.get("status") == "rejected" and attempt.get("candidate_after") is None,
                     f"{label} failed deterministic replay but is recorded as successful")
        else:
            before = compilation.get("candidate_before")
            from TaskDecomposition.round_robin_decomposition import _normalize_empty_artifact_placeholder
            candidate = DecompositionResult.from_dict(_normalize_empty_artifact_placeholder(rejected))
            compiled = {"sha256": digest[0], "version": 1 if number == 1 else before["version"] + 1,
                        "author_provider": source_provider, "decision": candidate.decision,
                        "graph_delta_plan_id": digest[1]}
            _require(index == len(attempts) and attempt.get("status") == "conformed"
                     and attempt.get("candidate_after") == compiled,
                     f"{label} candidate/version/author does not match deterministic replay")
            final_output = candidate.to_dict()
    _require(compilation.get("compiled_candidate") == compiled,
             f"round {number} compiled candidate differs from the bookkeeping result")
    accepted = compilation.get("accepted_candidate")
    status = compilation.get("status")
    if status == "candidate_accepted":
        _require(compiled is not None and accepted == compiled and source_entry.get("candidate_after") == accepted,
                 f"round {number} accepted candidate differs from its compilation")
        before = compilation.get("candidate_before")
        _require(before is None or accepted["sha256"] != before["sha256"],
                 f"round {number} accepted an identical candidate")
        published = files.json(f"rounds/{directory}/candidate.json", f"round {number} candidate")
        identity = files.json(f"rounds/{directory}/candidate_identity.json", f"round {number} candidate identity")
        _require(published == final_output and identity == accepted,
                 f"round {number} published candidate/identity differs from the compiled candidate")
        plan = files.json(f"rounds/{directory}/candidate_graph_delta.json", f"round {number} candidate graph")
        _verify_plan(plan, parent_contract, candidate, accepted["graph_delta_plan_id"])
    elif status == "identical_candidate":
        _require(compiled is not None and accepted is None and source_entry.get("candidate_after") is None
                 and compiled["sha256"] == compilation["candidate_before"]["sha256"],
                 f"round {number} is not an identical compiled candidate")
    else:
        _require(status == "compilation_failed" and compiled is None and accepted is None
                 and source_entry.get("candidate_after") is None and len(attempts) == MAX_ATTEMPTS and problems,
                 f"round {number} does not prove an exhausted bookkeeping compilation")
    return {"round_number": number, "sheet_sha256": compilation["sheet_sha256"],
            "accepted_candidate": accepted, "attempts": len(attempts), "evidence_sha256": files.hashes}


def _verify_bookkeeping(
    *, run_dir: Path, run_result: Mapping[str, Any], author_entry: Mapping[str, Any],
    first_provider: str, parent_contract: Mapping[str, Any], candidate_digest: CandidateDigest,
    designer_timeout: float | None = None,
) -> dict[str, Any]:
    """Verify historical round-1 evidence or the complete pinned v2 compilation set."""

    if not sheet_review_protocol(run_dir, run_result):
        return _verify_legacy_bookkeeping(
            run_dir=run_dir, run_result=run_result, author_entry=author_entry, first_provider=first_provider,
            parent_contract=parent_contract, candidate_digest=candidate_digest, designer_timeout=designer_timeout)
    files = _Files(Path(run_dir))
    request = files.json("decomposition_request.json", "decomposition request")
    record = run_result["designer_bookkeeper"]
    order = request.get("provider_order")
    _require(first_provider in PROVIDER_IDENTIFIERS and record.get("bookkeeper_provider") == first_provider
             and isinstance(order, list) and bool(order) and order[0] == first_provider,
             "the bookkeeper provider is not provider_order[0]")
    _require(isinstance(record.get("bookkeeper_model"), str) and bool(record["bookkeeper_model"]),
             "the bookkeeper model is not recorded")
    if designer_timeout is not None:
        _require(request.get("author_timeout_seconds") == designer_timeout,
                 "the pinned author timeout differs from the host timeout")
    else:
        designer_timeout = request.get("author_timeout_seconds")
    compilations = record.get("compilations")
    _require(isinstance(compilations, list)
             and all(isinstance(item, Mapping) and type(item.get("round_number")) is int for item in compilations),
             "the v2 compilation list is missing or contains an invalid round")
    sources = [entry for entry in run_result.get("rounds", [])
               if entry.get("candidate_after") is not None]
    _require(len(compilations) == len(sources) and sources and sources[0] == author_entry,
             "the ordered compilation set does not match every candidate-producing round")
    latest_sheet = None
    verified = []
    unresolved: dict[str, Any] = {}
    seen: set[str] = set()
    prior_states: dict[int, dict[str, Any]] = {}
    by_round = {item.get("round_number"): item for item in compilations if isinstance(item, Mapping)}
    _require(1 in by_round, "the initial accepted compilation is missing")
    latest_candidate = author_entry.get("candidate_after")
    reviewed_sheet_sha = by_round[1].get("sheet_sha256")
    reviewer_entries = [entry for entry in run_result["rounds"] if entry.get("role") == "decomposition_reviewer"]
    from TaskDecomposition.review_policy import validate_ownership_sheet_review
    for number, entry in enumerate(reviewer_entries, start=2):
        _require(entry.get("round_number") == number and entry.get("candidate_before") == latest_candidate
                 and entry.get("requested_provider") != latest_candidate.get("author_provider"),
                 f"round {number} does not independently review the current compiled candidate")
        prior_states[number] = dict(unresolved)
        review = files.json(f"rounds/{number:02d}/review.json", f"round {number} sheet review")
        try:
            parsed, unresolved = validate_ownership_sheet_review(
                review, expected_candidate_sha256=latest_candidate["sha256"],
                expected_sheet_sha256=reviewed_sheet_sha, round_number=number,
                prior_unresolved_findings=unresolved, all_prior_finding_ids=frozenset(seen))
        except Exception as exc:
            raise BookkeepingEvidenceError(f"round {number} sheet review is invalid: {exc}") from exc
        seen.update(finding.finding_id for finding in parsed.findings)
        if parsed.verdict == "revise":
            _require(number in by_round and entry.get("candidate_after") is not None,
                     f"round {number} revision has no accepted compilation")
            latest_candidate = entry["candidate_after"]
            reviewed_sheet_sha = by_round[number].get("sheet_sha256")
        else:
            _require(number not in by_round and entry.get("candidate_after") is None,
                     f"round {number} non-revision has a compilation")
    for compilation, source in zip(compilations, sources):
        _require(isinstance(compilation, Mapping) and compilation.get("status") == "candidate_accepted",
                 "a candidate-producing round must have one accepted compilation")
        proof = verify_compilation(
            run_dir=run_dir, run_result=run_result, compilation=compilation, source_entry=source,
            first_provider=first_provider, parent_contract=parent_contract, candidate_digest=candidate_digest,
            designer_timeout=designer_timeout, prior_unresolved_findings=prior_states.get(source["round_number"], {}))
        files.hashes.update(proof.pop("evidence_sha256"))
        verified.append(proof)
        latest_sheet = {"run_id": run_result["run_id"], "round_number": source["round_number"],
                        "sheet_path": compilation["sheet_path"], "sheet_sha256": compilation["sheet_sha256"],
                        "candidate_sha256": source["candidate_after"]["sha256"]}
    attempts = sum(item["attempts"] for item in verified)
    _require(type(record.get("bookkeeping_calls_used")) is int and record["bookkeeping_calls_used"] == attempts,
             "bookkeeping_calls_used differs from the recorded attempts")
    _require(record.get("latest_sheet") == latest_sheet,
             "latest_sheet does not identify the accepted latest candidate's compilation")
    return {"schema_version": "2.0", "bookkeeper_provider": first_provider,
            "bookkeeper_model": record["bookkeeper_model"], "attempts": attempts,
            "bookkeeping_calls_used": attempts, "compilations": verified, "latest_sheet": latest_sheet,
            "sheet_sha256": latest_sheet["sheet_sha256"], "candidate_sha256": latest_sheet["candidate_sha256"],
            "conformed": True, "evidence_sha256": files.hashes}


def verify_compilation(
    *, run_dir: Path, run_result: Mapping[str, Any], compilation: Mapping[str, Any],
    source_entry: Mapping[str, Any], first_provider: str, parent_contract: Mapping[str, Any],
    candidate_digest: CandidateDigest, designer_timeout: float | None = None,
    prior_unresolved_findings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        return _verify_compilation(
            run_dir=run_dir, run_result=run_result, compilation=compilation, source_entry=source_entry,
            first_provider=first_provider, parent_contract=parent_contract, candidate_digest=candidate_digest,
            designer_timeout=designer_timeout, prior_unresolved_findings=prior_unresolved_findings)
    except BookkeepingEvidenceError:
        raise
    except Exception as exc:
        raise BookkeepingEvidenceError(f"invalid compilation evidence: {exc}") from exc


def verify_bookkeeping(
    *, run_dir: Path, run_result: Mapping[str, Any], author_entry: Mapping[str, Any],
    first_provider: str, parent_contract: Mapping[str, Any], candidate_digest: CandidateDigest,
    designer_timeout: float | None = None,
) -> dict[str, Any]:
    try:
        return _verify_bookkeeping(
            run_dir=run_dir, run_result=run_result, author_entry=author_entry, first_provider=first_provider,
            parent_contract=parent_contract, candidate_digest=candidate_digest, designer_timeout=designer_timeout)
    except BookkeepingEvidenceError:
        raise
    except Exception as exc:
        raise BookkeepingEvidenceError(f"invalid bookkeeping evidence: {exc}") from exc
