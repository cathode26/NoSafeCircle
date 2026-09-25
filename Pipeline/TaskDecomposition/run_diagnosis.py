"""Read-only diagnosis of a finished D1B.2 decomposition run.

A failed run's retained artifacts already say why it stopped, but in several
places and in engine wording. This module reads them once, byte-exact, and
routes the run to exactly one primary cause so the next attempt is chosen on
purpose instead of repeated unchanged:

    STOP      evidence or source integrity problems, or nothing recognisable
    SETUP     launch/provider configuration (capacity, model, auth, quota)
    CONTRACT  the output asked for human or design authority; this means
              "needs contract review", never "the contract is defective"
    BUDGET    a valid reviewer revision used the last permitted call
    AUTHOR    a candidate or revision failed deterministic validation

Routing matches only the engine's own fixed wording and runtime failure text,
never model prose, and follows the ordered rounds rather than the first
rejection reason (the engine can list an earlier author error before the
terminal one). It grants nothing: every diagnosis carries
``retry_authorized: false``. The spec is
C:/nscrev/reports/handoffs/three-call-budget-SPEC-20260924.md, Part C.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

DIAGNOSIS_SCHEMA_VERSION = "decomposition-diagnosis/v1"
CLASSIFIER_VERSION = "1"
RUN_RESULT_NAME = "decomposition_run_result.json"

ROUTES = ("STOP", "SETUP", "CONTRACT", "BUDGET", "AUTHOR")

# Engine-authored reason text (round_robin_decomposition.py). Each is matched
# as a fixed substring of an engine rejection reason.
_SOURCE_FRESHNESS = (
    "source HEAD changed during provider invocation",
    "source tree changed during provider invocation",
    "source working tree changed during provider invocation",
)
_SESSION_UNPROVEN = "provider session identity unproven"
_BUDGET_STOP = "call limit ended immediately after a revision"
_UNRESOLVED_QUESTIONS = "may not contain unsupported assumptions or unresolved questions"
_AUTHOR_VALIDATION = (
    "initial candidate deterministic validation failed:",
    "review/revision deterministic validation failed:",
)
# Runtime failure text. Only read inside the engine's provider-failure reasons,
# so words that merely appear in a finding or a candidate cannot trigger them.
_PROVIDER_FAILURE_PREFIXES = ("AgentResult failed (", "task-associated invocation failed:")
_SETUP_SIGNATURES = (
    ("capacity_refused_before_call", "PromptCapacityError"),
    ("prompt_too_long", "Prompt is too long"),
    ("unrecognized_model", "unrecognized_model"),
    ("unsupported_model_version", "does not support this model"),
    ("usage_limit", "hit your usage limit"),
    ("authentication", "authentication_error"),
    ("authentication", "Invalid API key"),
)
_ROUND_PREFIX = re.compile(r"^round (\d+)( correction)?: ")


class DiagnosisEvidenceError(ValueError):
    """The retained run evidence is missing, malformed or unsafe to read."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DiagnosisEvidenceError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class RunSnapshot:
    """The exact bytes and parsed form of one run's result, read once."""

    run_dir: Path
    result: Mapping[str, Any]
    manifest: Mapping[str, str]


def load_run_snapshot(run_dir: Path) -> RunSnapshot:
    """Read a run's result file once, refusing links and malformed JSON."""

    run_dir = Path(run_dir)
    path = run_dir / RUN_RESULT_NAME
    for candidate in (run_dir, path):
        if candidate.is_symlink():
            raise DiagnosisEvidenceError(f"refusing a symbolic link: {candidate}")
    if not path.is_file():
        raise DiagnosisEvidenceError(f"run result is missing: {path}")
    data = path.read_bytes()
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiagnosisEvidenceError(f"run result is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise DiagnosisEvidenceError("run result is not a JSON object")
    return RunSnapshot(run_dir, result, {RUN_RESULT_NAME: hashlib.sha256(data).hexdigest()})


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _terminal_reasons(result: Mapping[str, Any]) -> list[str]:
    """Reasons from the last stage reached, plus run-level reasons.

    A correction of round N is the stage after round N, so a correction's
    failure is terminal even though the engine lists round N's error first.
    """

    reasons = _strings(result.get("rejection_reasons"))
    staged = []
    for text in reasons:
        match = _ROUND_PREFIX.match(text)
        if match:
            staged.append(((int(match.group(1)), 1 if match.group(2) else 0), text))
    run_level = [text for text in reasons if not _ROUND_PREFIX.match(text)]
    if not staged:
        return run_level
    last = max(stage for stage, _ in staged)
    return [_ROUND_PREFIX.sub("", text) for stage, text in staged if stage == last] + run_level


def _evidence(field: str, quote: str) -> dict[str, str]:
    return {"artifact": RUN_RESULT_NAME, "field": field, "quote": quote}


def _setup_code(reasons: list[str]) -> tuple[str, str] | None:
    for text in reasons:
        if not text.startswith(_PROVIDER_FAILURE_PREFIXES):
            continue
        for code, signature in _SETUP_SIGNATURES:
            if signature in text:
                return code, text
    return None


def _reviewer_findings(result: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for entry in result.get("finding_history") or []:
        if not isinstance(entry, Mapping):
            continue
        for finding in entry.get("findings") or []:
            if isinstance(finding, Mapping) and finding.get("severity", "blocking") == "blocking":
                finding_id = finding.get("finding_id")
                if isinstance(finding_id, str):
                    ids.append(finding_id)
    return ids


def classify_run_snapshot(snapshot: RunSnapshot) -> dict[str, Any]:
    """Route one finished run to a single primary cause, with secondary causes."""

    result = snapshot.result
    status = result.get("run_status")
    rounds = [entry for entry in result.get("rounds") or [] if isinstance(entry, Mapping)]
    reasons = _strings(result.get("rejection_reasons"))
    terminal = _terminal_reasons(result)
    secondary: list[dict[str, Any]] = []

    def diagnosis(route: str, code: str, evidence: list[dict[str, str]]) -> dict[str, Any]:
        findings = _reviewer_findings(result)
        if route != "AUTHOR" and findings:
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

    if result.get("mode") != "round_robin_d1b2" or not isinstance(status, str) or not rounds:
        return diagnosis("STOP", "unrecognised_run_evidence", [])
    if status == "review_ready":
        return diagnosis("STOP", "not_a_failure", [_evidence("run_status", status)])

    for text in reasons:
        if _SESSION_UNPROVEN in text:
            return diagnosis("STOP", "provider_session_unproven", [_evidence("rejection_reasons", text)])
    for text in terminal:
        if any(signature in text for signature in _SOURCE_FRESHNESS):
            return diagnosis("STOP", "source_changed_during_run", [_evidence("rejection_reasons", text)])

    setup = _setup_code(terminal)
    if setup is not None:
        code, text = setup
        initial = [_ROUND_PREFIX.sub("", text) for text in reasons
                   if text.startswith("round 1: initial candidate")]
        if initial and not any(text in terminal for text in initial):
            secondary.append({"route": "AUTHOR", "reason_code": "initial_candidate_invalid",
                              "evidence": [_evidence("rejection_reasons", initial[0])]})
        return diagnosis("SETUP", code, [_evidence("rejection_reasons", text)])
    if any(text.startswith(_PROVIDER_FAILURE_PREFIXES) for text in terminal):
        text = next(text for text in terminal if text.startswith(_PROVIDER_FAILURE_PREFIXES))
        return diagnosis("STOP", "unrecognised_provider_failure", [_evidence("rejection_reasons", text)])

    for text in terminal:
        if _UNRESOLVED_QUESTIONS in text:
            return diagnosis("CONTRACT", "output_requested_authority", [_evidence("rejection_reasons", text)])
    last = rounds[-1]
    if last.get("verdict") == "needs_human" or (
            result.get("decision") == "needs_human" and last.get("status") != "revised_candidate_valid"):
        return diagnosis("CONTRACT", "provider_requested_human_decision",
                         [_evidence("decision", str(result.get("decision")))])

    for text in terminal:
        if _BUDGET_STOP in text and last.get("status") == "revised_candidate_valid":
            return diagnosis("BUDGET", "revision_used_last_call", [_evidence("rejection_reasons", text)])

    for text in terminal:
        if text.startswith(_AUTHOR_VALIDATION):
            code = ("initial_candidate_invalid" if text.startswith(_AUTHOR_VALIDATION[0])
                    else "revision_invalid")
            return diagnosis("AUTHOR", code, [_evidence("rejection_reasons", text)])

    return diagnosis("STOP", "unrecognised_failure", [_evidence("rejection_reasons", text) for text in terminal])


def diagnose_run(run_dir: Path) -> dict[str, Any]:
    """Load and classify one retained run directory."""

    return classify_run_snapshot(load_run_snapshot(run_dir))
