"""Read-only diagnosis of a finished D1B.2 decomposition run.

A failed run's retained artifacts already say why it stopped, but in several
places and in engine wording. This module reads them byte-exact, validates
their shape, and routes the run to exactly one primary cause so the next
attempt is chosen on purpose instead of repeated unchanged:

    STOP      evidence or source integrity problems, host verification
              failures, success, or nothing recognisable
    SETUP     launch/provider configuration (capacity, model, quota)
    CONTRACT  the run asked for human or design authority; this means
              "needs contract review", never "the contract is defective"
    BUDGET    a valid reviewer revision used the last permitted call
    AUTHOR    a candidate, correction or revision failed deterministic
              validation

The terminal stage is the last round actually recorded, not the first
rejection reason. Provider failures are classified from the round's retained
AgentRuntime result, which must agree with the round summary, and only by
structured classifications or fully anchored runtime envelopes: model text a
provider appends to an error cannot match. Every file read is confined to the
run directory component by component, refusing links and junctions, and is
hashed into the diagnosis. It grants nothing: every diagnosis carries
``retry_authorized: false``. The spec is
C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md, Part C.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

DIAGNOSIS_SCHEMA_VERSION = "decomposition-diagnosis/v1"
CLASSIFIER_VERSION = "4"
RUN_RESULT_NAME = "decomposition_run_result.json"
RUN_RESULT_SCHEMA_VERSION = "1.0"
RUN_STATUSES = frozenset({"review_ready", "rejected", "needs_human", "agent_failed"})

ROUTES = ("STOP", "SETUP", "CONTRACT", "BUDGET", "AUTHOR")

# Engine-authored reason text (round_robin_decomposition.py).
_SOURCE_FRESHNESS = (
    "source HEAD changed during provider invocation",
    "source tree changed during provider invocation",
    "source working tree changed during provider invocation",
)
_SESSION_UNPROVEN = "provider session identity unproven"
_BUDGET_STOP = "call limit ended immediately after a revision"
_UNRESOLVED_QUESTIONS = "may not contain unsupported assumptions or unresolved questions"
_AUTHOR_VALIDATION = (
    ("initial candidate deterministic validation failed:", "initial_candidate_invalid"),
    ("corrected candidate deterministic validation failed:", "correction_invalid"),
    ("review/revision deterministic validation failed:", "revision_invalid"),
)
# Host-authored: the refusal happens before any provider starts, and every part
# of its text comes from the host (sizes, thresholds, configured model id).
_CAPACITY_REFUSAL = "task-associated invocation failed: PromptCapacityError: provider_started=false: "
# Fully anchored runtime envelopes. Anything appended by a model breaks them.
_RUNTIME_ENVELOPES = (
    ("prompt_too_long", re.compile(
        r"Claude Code exited with status \d+: Claude Code reported an unsuccessful result "
        r"\(is_error=True, subtype='[a-z_]+', terminal_reason='blocking_limit'\): Prompt is too long")),
    ("unrecognized_model", re.compile(
        r"Claude Code exited with status \d+: \[claude-code:unrecognized_model\] \{[^{}\n]*\}")),
)
_AUTHOR_ROLE = "task_decomposer"
_REVIEWER_ROLE = "decomposition_reviewer"
_BOOKKEEPER_ROLE = "decomposition_bookkeeper"
_ROUND_PREFIX = re.compile(r"^round \d+(?: correction)?: ")


class DiagnosisEvidenceError(ValueError):
    """The retained run evidence is missing, malformed or unsafe to read."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DiagnosisEvidenceError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def parse_json_object(data: bytes, label: str) -> dict[str, Any]:
    """Strict UTF-8 JSON object with no duplicate keys."""

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiagnosisEvidenceError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DiagnosisEvidenceError(f"{label} is not a JSON object")
    return value


def _is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def confined(root: Path, relative: str) -> Path:
    """`root/relative`, refusing any component that is a link or a junction.

    Every component beneath the trusted root is checked lexically before
    anything is resolved or read, so neither a linked run directory nor a
    redirected ancestor can move the read outside the root.
    """

    parts = Path(relative).parts
    if not parts or any(part in ("", ".", "..") or Path(part).is_absolute() for part in parts):
        raise DiagnosisEvidenceError(f"refusing an unsafe relative path: {relative!r}")
    current = Path(root)
    if _is_link(current):
        raise DiagnosisEvidenceError(f"refusing a linked directory: {current}")
    for part in parts:
        current = current / part
        if _is_link(current):
            raise DiagnosisEvidenceError(f"refusing a link or junction: {current}")
    return current


@dataclass
class RunSnapshot:
    """One run's result, and every other file read, with their byte hashes."""

    run_dir: Path
    result: Mapping[str, Any]
    manifest: dict[str, str] = field(default_factory=dict)

    def read_json(self, relative: str, label: str) -> dict[str, Any]:
        path = confined(self.run_dir, relative)
        if not path.is_file():
            raise DiagnosisEvidenceError(f"{label} is missing: {relative}")
        data = path.read_bytes()
        self.manifest[relative] = hashlib.sha256(data).hexdigest()
        return parse_json_object(data, label)


def load_run_snapshot(run_dir: Path) -> RunSnapshot:
    """Read a run's result file once, refusing links and malformed JSON."""

    run_dir = Path(run_dir)
    if _is_link(run_dir):
        raise DiagnosisEvidenceError(f"refusing a linked run directory: {run_dir}")
    snapshot = RunSnapshot(run_dir, {})
    snapshot.result = snapshot.read_json(RUN_RESULT_NAME, "run result")
    return snapshot


def _int(value: Any) -> bool:
    return type(value) is int


def expected_invocation_id(task_id: str, run_id: str, round_number: int, role: str,
                           *, correction: bool, bookkeeping_attempt: int | None = None) -> str:
    """The engine's deterministic invocation id (round_robin_decomposition._round_invocation_id)."""

    if bookkeeping_attempt is not None:
        scope = f"{round_number}-bookkeeper-{bookkeeping_attempt}"
        marker = f"b{bookkeeping_attempt}"
    else:
        scope = f"{round_number}-correction" if correction else f"{round_number}"
        marker = "c" if correction else ""
    suffix = hashlib.sha256(f"{run_id}:{scope}:{role}".encode("utf-8")).hexdigest()[:12]
    return f"{task_id.lower()}-d1b2-r{round_number:02d}{marker}-{role.replace('_', '-')}-{suffix}"


def _rounds_problem(rounds: list[dict[str, Any]], calls: int) -> str | None:
    """The engine's round sequence: author, optional correction of round 1, reviewers."""

    ordinary = [r for r in rounds if r.get("correction_of_round") is None]
    if [r.get("round_number") for r in ordinary] != list(range(1, calls + 1)):
        return "rounds are not numbered consecutively from 1"
    for entry in ordinary:
        wanted = _AUTHOR_ROLE if entry["round_number"] == 1 else _REVIEWER_ROLE
        if entry.get("role") != wanted:
            return f"round {entry['round_number']} has role {entry.get('role')!r}, expected {wanted!r}"
    corrections = [index for index, r in enumerate(rounds) if r.get("correction_of_round") is not None]
    if corrections:
        index = corrections[0]
        entry = rounds[index]
        if (index != 1 or entry.get("correction_of_round") != 1 or entry.get("round_number") != 1
                or entry.get("role") != _AUTHOR_ROLE or rounds[0].get("status") != "rejected"):
            return "an author correction must directly follow a rejected round 1 and correct it"
    return None


def _structure_problem(result: Mapping[str, Any]) -> str | None:
    """Why the run result cannot be diagnosed confidently, or None."""

    if result.get("schema_version") != RUN_RESULT_SCHEMA_VERSION:
        return f"unsupported run result schema {result.get('schema_version')!r}"
    if result.get("mode") != "round_robin_d1b2":
        return f"unsupported mode {result.get('mode')!r}"
    if not isinstance(result.get("run_status"), str) or result["run_status"] not in RUN_STATUSES:
        return f"unknown run status {result.get('run_status')!r}"
    for key in ("task_id", "run_id"):
        if not isinstance(result.get(key), str) or not result[key]:
            return f"{key} is not a nonempty string"
    rounds = result.get("rounds")
    if not isinstance(rounds, list) or not rounds or not all(isinstance(r, dict) for r in rounds):
        return "rounds is not a nonempty list of objects"
    for key in ("finding_history", "rejection_reasons"):
        if not isinstance(result.get(key), list):
            return f"{key} is not a list"
    if not all(isinstance(entry, dict) for entry in result["finding_history"]):
        return "finding_history contains a non-object"
    if not all(isinstance(text, str) for text in result["rejection_reasons"]):
        return "rejection_reasons contains a non-string"
    for key in ("calls_used", "max_calls", "author_corrections_used"):
        if not _int(result.get(key)):
            return f"{key} is not an integer"
    calls, limit, corrections = result["calls_used"], result["max_calls"], result["author_corrections_used"]
    if not 1 <= calls <= limit or corrections not in (0, 1):
        return f"inconsistent call accounting: calls_used={calls} max_calls={limit} corrections={corrections}"
    correction_rounds = [r for r in rounds if r.get("correction_of_round") is not None]
    if len(rounds) - len(correction_rounds) != calls or len(correction_rounds) != corrections:
        return (f"rounds do not match accounting: {len(rounds)} rounds, "
                f"{len(correction_rounds)} corrections, calls_used={calls}")
    for entry in rounds:
        if not _int(entry.get("round_number")) or not isinstance(entry.get("rejection_reasons"), list):
            return "a round lacks an integer round_number or a rejection_reasons list"
        if not all(isinstance(text, str) for text in entry["rejection_reasons"]):
            return "a round's rejection_reasons contains a non-string"
    problem = _rounds_problem(rounds, calls)
    if problem is not None:
        return problem
    bookkeeping = result.get("designer_bookkeeper")
    if isinstance(bookkeeping, Mapping) and bookkeeping.get("schema_version") == "2.0":
        return _bookkeeping_structure_problem(result, bookkeeping)
    return None


def _bookkeeping_structure_problem(result: Mapping[str, Any], record: Mapping[str, Any]) -> str | None:
    compilations = record.get("compilations")
    if not isinstance(compilations, list) or not all(isinstance(c, Mapping) for c in compilations):
        return "bookkeeping compilations is not a list of objects"
    numbers = [entry.get("round_number") for entry in compilations]
    if (not all(_int(number) and 1 <= number <= result["calls_used"] for number in numbers)
            or numbers != sorted(set(numbers))):
        return "bookkeeping compilations are not consecutive candidate-producing rounds"
    calls = 0
    accepted_rounds = []
    for compilation in compilations:
        attempts = compilation.get("attempts")
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= 2:
            return "a compilation must record one or two bookkeeping attempts"
        for index, attempt in enumerate(attempts, 1):
            if (not isinstance(attempt, Mapping) or not _int(attempt.get("attempt"))
                    or attempt["attempt"] != index):
                return "bookkeeping attempt numbers are not consecutive"
        calls += len(attempts)
        status = compilation.get("status")
        if status not in ("candidate_accepted", "compilation_failed", "identical_candidate"):
            return "a compilation records an unknown status"
        compiled = compilation.get("compiled_candidate")
        if status == "candidate_accepted":
            accepted_rounds.append(compilation["round_number"])
            if (not isinstance(compiled, Mapping) or not compiled.get("sha256")
                    or compiled != compilation.get("accepted_candidate")):
                return "an accepted compilation records no matching compiled candidate"
        elif compilation.get("accepted_candidate") is not None:
            return "a refused compilation records an accepted candidate"
        if status == "compilation_failed" and compiled is not None:
            return "failed bookkeeping records a compiled candidate"
        if status == "identical_candidate":
            before = compilation.get("candidate_before")
            if (not isinstance(compiled, Mapping) or not isinstance(before, Mapping)
                    or not isinstance(before.get("sha256"), str) or not before["sha256"]
                    or compiled.get("sha256") != before["sha256"] or before != result.get("latest_candidate")
                    or compilation is not compilations[-1]
                    or compilation["round_number"] != result["rounds"][-1]["round_number"]
                    or result.get("run_status") != "rejected"):
                return "identical bookkeeping is not the terminal compilation of the latest candidate"
    producing = [entry["round_number"] for entry in result["rounds"]
                 if entry.get("status") in ("candidate_valid", "correction_candidate_valid", "revised_candidate_valid")]
    if accepted_rounds != producing:
        return "accepted compilations do not match candidate-producing rounds"
    if not _int(record.get("bookkeeping_calls_used")) or record["bookkeeping_calls_used"] != calls:
        return "bookkeeping call accounting differs from its attempts"
    latest = record.get("latest_sheet")
    accepted = [entry for entry in compilations if entry.get("status") == "candidate_accepted"]
    if accepted:
        last = accepted[-1]
        expected = {
            "run_id": result["run_id"], "round_number": last["round_number"],
            "sheet_path": last.get("sheet_path"), "sheet_sha256": last.get("sheet_sha256"),
            "candidate_sha256": (last.get("accepted_candidate") or {}).get("sha256"),
        }
        if latest != expected or last.get("accepted_candidate") != result.get("latest_candidate"):
            return "latest accepted sheet and candidate disagree with the compilations"
    elif latest is not None:
        return "bookkeeping records a latest sheet without an accepted compilation"
    failed = [entry for entry in compilations if entry.get("status") == "compilation_failed"]
    if bool(failed) != (record.get("terminal_stage") is not None):
        return "failed bookkeeping lacks its exact terminal stage"
    if failed and (len(failed) != 1 or failed[0] is not compilations[-1]
                   or failed[0]["round_number"] != result["rounds"][-1]["round_number"]):
        return "failed bookkeeping is not the last recorded stage"
    return None


def _terminal_bookkeeping(snapshot: RunSnapshot, last: Mapping[str, Any]) -> Mapping[str, Any]:
    record = snapshot.result.get("designer_bookkeeper")
    if not isinstance(record, Mapping) or record.get("schema_version") != "2.0":
        return last
    stage = record.get("terminal_stage")
    if stage is None:
        return last
    compilation = record["compilations"][-1]
    attempt = compilation["attempts"][-1]
    number, index = compilation["round_number"], attempt["attempt"]
    invocation = expected_invocation_id(
        snapshot.result["task_id"], snapshot.result["run_id"], number, _BOOKKEEPER_ROLE,
        correction=False, bookkeeping_attempt=index)
    directory = f"{number:02d}-bookkeeper-{index}"
    relative = f"rounds/{directory}/agent_runtime/{invocation}/result.json"
    expected = {"round_number": number, "bookkeeping_attempt": index,
                "invocation_id": invocation, "agent_runtime_result_path": relative}
    if stage != expected:
        raise DiagnosisEvidenceError("terminal bookkeeping stage is not the last attempt")
    retained = snapshot.read_json(f"rounds/{directory}/bookkeeping_attempt.json", "terminal bookkeeping attempt")
    if (retained != attempt or attempt.get("directory") != directory
            or attempt.get("invocation_id") != invocation or attempt.get("agent_runtime_result_path") != relative
            or attempt.get("requested_provider") != record.get("bookkeeper_provider")
            or attempt.get("candidate_after") is not None or attempt.get("status") != "rejected"
            or not isinstance(attempt.get("problems"), list) or not attempt["problems"]):
        raise DiagnosisEvidenceError("terminal bookkeeping attempt contradicts its compilation")
    request = snapshot.read_json("decomposition_request.json", "decomposition request")
    pins = {"designer_bookkeeper_version": "2.0", "ownership_sheet_review_version": "1.1",
            "bookkeeper_provider": record.get("bookkeeper_provider"), "bookkeeper_model": record.get("bookkeeper_model")}
    if (any(request.get(key) != value for key, value in pins.items())
            or request.get("provider_order") != snapshot.result.get("provider_order")
            or record.get("bookkeeper_provider") != snapshot.result["provider_order"][0]
            or request.get("run_id") != snapshot.result["run_id"]):
        raise DiagnosisEvidenceError("terminal bookkeeping settings disagree with the retained request")
    if attempt.get("actual_model") is not None and attempt["actual_model"] != record.get("bookkeeper_model"):
        raise DiagnosisEvidenceError("terminal bookkeeping model differs from the pinned model")
    if attempt.get("actual_provider") is not None:
        provider = {"claude": "claude-code", "codex": "openai-codex"}.get(record.get("bookkeeper_provider"))
        if attempt["actual_provider"] != provider:
            raise DiagnosisEvidenceError("terminal bookkeeping provider differs from the pinned provider")
        invocation_request = snapshot.read_json(
            f"rounds/{directory}/agent_runtime/{invocation}/request.json", "terminal bookkeeping request")
        if (invocation_request.get("run_id") != invocation or invocation_request.get("role") != _BOOKKEEPER_ROLE
                or (invocation_request.get("budgets") or {}).get("timeout_seconds") != request.get("author_timeout_seconds")
                or invocation_request.get("allowed_capabilities") != ["repository_read", "repository_search"]
                or invocation_request.get("write_boundaries") != {"allowed_paths": [], "denied_paths": []}):
            raise DiagnosisEvidenceError("terminal bookkeeping request disagrees with the pinned read-only invocation")
    return {**attempt, "round_number": number, "bookkeeping_attempt": index, "role": _BOOKKEEPER_ROLE,
            "rejection_reasons": attempt["problems"], "correction_of_round": None}


def _evidence(field_name: str, quote: str, artifact: str = RUN_RESULT_NAME) -> dict[str, str]:
    return {"artifact": artifact, "field": field_name, "quote": quote}


def _reviewer_findings(result: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for entry in result.get("finding_history") or []:
        findings = entry.get("findings") if isinstance(entry, Mapping) else None
        for finding in findings if isinstance(findings, list) else []:
            if isinstance(finding, Mapping) and finding.get("severity", "blocking") == "blocking":
                finding_id = finding.get("finding_id")
                if isinstance(finding_id, str):
                    ids.append(finding_id)
    return ids


def _runtime_setup(snapshot: RunSnapshot, last: Mapping[str, Any]) -> tuple[str, dict[str, str]] | None:
    """SETUP cause proven by the last round's retained AgentRuntime result.

    The result must be exactly the one the engine would have written for this
    round: its path and run id are recomputed from the run, and its role,
    provider, model, status and classification must agree with the round.
    """

    relative = last.get("agent_runtime_result_path")
    if relative is None:
        return None
    correction = last.get("correction_of_round") is not None
    invocation = expected_invocation_id(
        snapshot.result["task_id"], snapshot.result["run_id"], last["round_number"],
        str(last.get("role")), correction=correction, bookkeeping_attempt=last.get("bookkeeping_attempt"))
    directory = f"{last['round_number']:02d}" + ("-correction" if correction else "")
    if last.get("bookkeeping_attempt") is not None:
        directory += f"-bookkeeper-{last['bookkeeping_attempt']}"
    expected = f"rounds/{directory}/agent_runtime/{invocation}/result.json"
    if relative != expected:
        raise DiagnosisEvidenceError(f"AgentRuntime result path {relative!r} is not this round's {expected!r}")
    runtime = snapshot.read_json(relative, "AgentRuntime result")
    bindings = {
        "schema_version": ("1.0", runtime.get("schema_version")),
        "run_id": (invocation, runtime.get("run_id")),
        "role": (last.get("role"), runtime.get("role")),
        "provider": (last.get("actual_provider"), runtime.get("provider")),
        "model": (last.get("actual_model"), runtime.get("model")),
        "status": ("failed", runtime.get("status")),
        "failure_classification": (last.get("agent_failure_classification"),
                                   runtime.get("failure_classification")),
    }
    for name, (wanted, got) in bindings.items():
        if got != wanted:
            raise DiagnosisEvidenceError(
                f"AgentRuntime result {name} is {got!r}, but the round records {wanted!r}")
    if last.get("bookkeeping_attempt") is not None and (
            runtime.get("claimed_changed_paths") != [] or runtime.get("claims_execution_occurred") is not False
            or runtime.get("claimed_test_commands") != []):
        raise DiagnosisEvidenceError("terminal bookkeeping runtime does not prove read-only execution")
    classification = runtime["failure_classification"]
    message = runtime.get("failure_message")
    if classification == "quota_exhausted":
        return "quota_exhausted", _evidence("failure_classification", classification, relative)
    if classification == "provider_error" and isinstance(message, str):
        for code, pattern in _RUNTIME_ENVELOPES:
            if pattern.fullmatch(message):
                return code, _evidence("failure_message", message, relative)
    return None


def classify_run_snapshot(
    snapshot: RunSnapshot, *, receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Route one finished run to a single primary cause, with secondary causes.

    `receipt` is the AssistantControl decomposition receipt when known: an
    engine `review_ready` run is only a success if the host accepted it too.
    """

    result = snapshot.result
    secondary: list[dict[str, Any]] = []
    problem = _structure_problem(result)
    rounds = result.get("rounds") if problem is None else []
    status = result.get("run_status")

    def diagnosis(route: str, code: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
        findings = _reviewer_findings(result) if problem is None else []
        if route not in ("AUTHOR", "STOP") and findings:
            secondary.append({
                "route": "AUTHOR", "reason_code": "reviewer_blocking_findings",
                "finding_ids": findings,
            })
        return {
            "schema_version": DIAGNOSIS_SCHEMA_VERSION,
            "classifier_version": CLASSIFIER_VERSION,
            "task_id": result.get("task_id"),
            "run_id": result.get("run_id"),
            "engine_run_status": status,
            "receipt_status": None if receipt is None else receipt.get("status"),
            "primary": {"route": route, "reason_code": code, "evidence": evidence},
            "secondary": secondary,
            "rounds": [
                {
                    "round_number": entry.get("round_number"),
                    "correction_of_round": entry.get("correction_of_round"),
                    "role": entry.get("role"),
                    "requested_provider": entry.get("requested_provider"),
                    "actual_model": entry.get("actual_model"),
                    "status": entry.get("status"),
                    "agent_failure_classification": entry.get("agent_failure_classification"),
                    "verdict": entry.get("verdict"),
                }
                for entry in rounds
            ],
            "calls_used": result.get("calls_used"),
            "max_calls": result.get("max_calls"),
            "input_manifest": dict(snapshot.manifest),
            "retry_authorized": False,
        }

    if problem is not None:
        return diagnosis("STOP", "malformed_evidence", [_evidence("run result", problem)])

    try:
        last = _terminal_bookkeeping(snapshot, rounds[-1])
    except DiagnosisEvidenceError as exc:
        return diagnosis("STOP", "malformed_evidence", [_evidence("terminal bookkeeping", str(exc))])
    run_level = [text for text in result["rejection_reasons"] if not _ROUND_PREFIX.match(text)]
    terminal = list(last["rejection_reasons"]) + run_level

    if status == "review_ready":
        if result.get("decision") == "needs_human":
            return diagnosis("CONTRACT", "reviewed_decision_needs_human",
                             [_evidence("decision", "needs_human")])
        if receipt is not None and receipt.get("status") not in ("review_ready", "applied"):
            error = receipt.get("error")
            return diagnosis("STOP", "host_verification_failed",
                             [_evidence("status", str(receipt.get("status")), "Assistant receipt"),
                              *([_evidence("error", error, "Assistant receipt")] if isinstance(error, str) else [])])
        return diagnosis("STOP", "not_a_failure" if receipt is not None else "engine_review_ready_unverified",
                         [_evidence("run_status", status)])

    for text in result["rejection_reasons"]:
        if _SESSION_UNPROVEN in text:
            return diagnosis("STOP", "provider_session_unproven", [_evidence("rejection_reasons", text)])
    for text in terminal:
        if any(signature in text for signature in _SOURCE_FRESHNESS):
            return diagnosis("STOP", "source_changed_during_run", [_evidence("rejection_reasons", text)])

    if last.get("role") == _BOOKKEEPER_ROLE and any("read-only Decomposer rejected" in text for text in terminal):
        return diagnosis("STOP", "bookkeeper_attempted_write", [_evidence("problems", text) for text in terminal])

    if last.get("agent_status") != "succeeded":
        for text in last["rejection_reasons"]:
            if (text.startswith(_CAPACITY_REFUSAL) or (last.get("role") == _BOOKKEEPER_ROLE
                    and text.startswith("bookkeeper invocation failed: PromptCapacityError: provider_started=false: "))):
                code, evidence = "capacity_refused_before_call", _evidence("rejection_reasons", text)
                break
        else:
            try:
                setup = _runtime_setup(snapshot, last)
            except DiagnosisEvidenceError as exc:
                if last.get("role") != _BOOKKEEPER_ROLE:
                    raise
                return diagnosis("STOP", "malformed_evidence", [_evidence("terminal bookkeeping", str(exc))])
            if setup is None:
                return diagnosis("STOP", "unrecognised_provider_failure",
                                 [_evidence("rejection_reasons", text) for text in last["rejection_reasons"]])
            code, evidence = setup
        if last.get("correction_of_round") is not None:
            initial = rounds[-2]["rejection_reasons"] if len(rounds) > 1 else []
            if initial:
                secondary.append({"route": "AUTHOR", "reason_code": "initial_candidate_invalid",
                                  "evidence": [_evidence("rejection_reasons", initial[0])]})
        return diagnosis("SETUP", code, [evidence])

    if last.get("role") == _BOOKKEEPER_ROLE:
        try:
            runtime = snapshot.read_json(last["agent_runtime_result_path"], "terminal bookkeeping result")
            if (runtime.get("run_id") != last["invocation_id"] or runtime.get("status") != "succeeded"
                    or runtime.get("role") != _BOOKKEEPER_ROLE or runtime.get("provider") != last.get("actual_provider")
                    or runtime.get("model") != last.get("actual_model")
                    or runtime.get("failure_classification") != "none"
                    or runtime.get("claimed_changed_paths") != [] or runtime.get("claims_execution_occurred") is not False
                    or runtime.get("claimed_test_commands") != []):
                raise DiagnosisEvidenceError("terminal bookkeeping runtime disagrees with its attempt")
        except DiagnosisEvidenceError as exc:
            return diagnosis("STOP", "malformed_evidence", [_evidence("terminal bookkeeping", str(exc))])
        return diagnosis("AUTHOR", "bookkeeping_validation_failed",
                         [_evidence("problems", text) for text in last["rejection_reasons"]])
    bookkeeping = result.get("designer_bookkeeper")
    if isinstance(bookkeeping, Mapping) and bookkeeping.get("schema_version") == "2.0":
        compilations = bookkeeping["compilations"]
        if compilations and compilations[-1].get("status") == "identical_candidate":
            return diagnosis("AUTHOR", "identical_candidate",
                             [_evidence("designer_bookkeeper.compilations", "identical_candidate")])

    for text in terminal:
        if _UNRESOLVED_QUESTIONS in text and text.startswith(tuple(p for p, _ in _AUTHOR_VALIDATION)):
            return diagnosis("CONTRACT", "output_requested_authority", [_evidence("rejection_reasons", text)])
    if last.get("verdict") == "needs_human":
        return diagnosis("CONTRACT", "reviewer_requested_human_decision",
                         [_evidence("verdict", "needs_human")])

    if last.get("status") == "revised_candidate_valid" and result.get("decision") == "needs_human":
        return diagnosis("CONTRACT", "revision_requests_human_decision",
                         [_evidence("decision", "needs_human")])
    for text in run_level:
        if (_BUDGET_STOP in text and last.get("status") == "revised_candidate_valid"
                and result["calls_used"] == result["max_calls"]):
            return diagnosis("BUDGET", "revision_used_last_call", [_evidence("rejection_reasons", text)])

    for text in terminal:
        for prefix, code in _AUTHOR_VALIDATION:
            if text.startswith(prefix):
                return diagnosis("AUTHOR", code, [_evidence("rejection_reasons", text)])

    return diagnosis("STOP", "unrecognised_failure", [_evidence("rejection_reasons", text) for text in terminal])


def diagnose_run(run_dir: Path, *, receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Load and classify one retained run directory."""

    return classify_run_snapshot(load_run_snapshot(run_dir), receipt=receipt)
