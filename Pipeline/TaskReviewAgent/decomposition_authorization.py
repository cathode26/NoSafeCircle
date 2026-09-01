#!/usr/bin/env python3
"""Pure exact fail-closed decomposition-authorization binding (A2, v1).

The Software Architect may recommend ``decomposition_required`` and D1B.2 can
already emit an independently reviewed ``review_ready`` candidate plus a
validated ``GraphDeltaPlan``. Those artifacts remain ``review_only_not_applied``
and ``apply_graph_delta()`` correctly refuses to read them as permission.

This module answers exactly one question, deterministically and without side
effects:

    Does this exact human authorization record bind the exact independently
    reviewed D1B.2 candidate, the exact task/source identity, the exact
    ``DecompositionResult`` bytes, and the exact ``GraphDeltaPlan`` bytes?

Only an exact positive answer yields ``authorized``. Nothing here persists a
record, mutates a GitHub Issue, runs the decomposer, calls D1C, or schedules
work: a caller obtains the authoritative human login and durable record
elsewhere and passes them in.

Authority boundary
------------------
* The record's ``artifact_locator`` is operational only. Artifact identity comes
  from recomputed hashes and the structured D1B data supplied by the caller,
  never from a path the record happens to name.
* Only a D1B.2 round-robin run whose independent reviewer is not the latest
  candidate author can reach ``authorized``. A D1B.1 single-provider proposal is
  never independently reviewed in v1 and returns ``review_invalid`` even when a
  record claims otherwise.
* A malformed record, allowlist, or typed artifact raises
  ``DecompositionAuthorizationContractError``. A syntactically valid record that
  simply is not usable returns a typed decision instead of throwing.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.TaskReviewAgent.actor_policy import normalize_login  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    GIT_SHA_RE,
    SHA256_RE,
    TASK_ID_RE,
    TaskReviewContractError,
    canonical_json,
    semantic_sha256,
)
from TaskDecomposition.context_builder import (  # noqa: E402
    DecompositionPreflightError,
)
from TaskDecomposition.contracts import DecompositionResult  # noqa: E402
from TaskDecomposition.review_contracts import (  # noqa: E402
    FINDING_ID_RE,
    FINDING_RESOLUTION_STATUSES,
    FINDING_SEVERITIES,
)

# The authoritative D1B.2 identities are imported, never re-implemented:
# ``candidate_sha256`` is the exact reviewed-candidate digest and
# ``_round_invocation_id`` is the exact per-round invocation identity that
# D1B.2 itself issues. ``Pipeline/TaskDecomposition/tests/
# round_invocation_id_smoke_test.py`` establishes the same import convention.
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION,
    SUPPORTED_PROVIDERS,
    _round_invocation_id,
    candidate_sha256,
    round_robin_call_limit,
    validate_provider_order,
)
from graph_apply_plan import _canonical_json_sha256  # noqa: E402
from graph_delta import GraphDeltaPlan  # noqa: E402


DECOMPOSITION_AUTHORIZATION_SCHEMA_VERSION = "1.0"

# D1B.2 run-shape constants this binder re-proves against.
D1B2_RUN_MODE = "round_robin_d1b2"
D1B2_REVIEW_READY_STATUS = "review_ready"
D1B2_INDEPENDENT_PASS_ROUND_STATUS = "independent_pass"
D1B2_INITIAL_CANDIDATE_ROUND_STATUS = "candidate_valid"
D1B2_REVISED_CANDIDATE_ROUND_STATUS = "revised_candidate_valid"
D1B2_REVIEWER_ROLE = "decomposition_reviewer"
D1B2_DECOMPOSER_ROLE = "task_decomposer"
REVIEW_ONLY_AUTHORITY = "review_only_not_applied"

# The exact run-relative names ``round_robin_decomposition`` publishes for a
# review_ready run. A run that reached review_ready wrote
# ``decomposition_result.json``, and it wrote ``graph_delta.json`` exactly when
# its latest candidate carries a GraphDeltaPlan. Any other value, including an
# empty string, is not something the producer can have emitted.
D1B2_DECOMPOSITION_RESULT_FILENAME = "decomposition_result.json"
D1B2_GRAPH_DELTA_FILENAME = "graph_delta.json"
DECOMPOSED_DECISION = "decomposed"
RESOLVED_FINDING_RESOLUTIONS = frozenset({"resolved", "withdrawn"})

# A logical D1B.2 provider name is not an AgentRuntime provider identity.
# ``live_decomposition._validated_provider_bundle`` owns this mapping, so a
# round's ``actual_provider`` (an ``AgentResult.provider``) is compared at the
# runtime layer while the reviewer contract keeps its logical name. The test
# suite pins this table to that producer source; the producer's own ``"fake"``
# test escape is deliberately not accepted as production authorization.
RUNTIME_PROVIDER_IDENTIFIERS = {
    "claude": "claude-code",
    "codex": "openai-codex",
}

# Exact per-round artifact references the producer emits for a round it really
# executed: (round-summary field, run-relative directory, file name).
ROUND_ARTIFACT_REFERENCES = (
    ("task_execution_request_path", "task_execution", "task_request.json"),
    ("agent_runtime_result_path", "agent_runtime", "result.json"),
)

# Exact producer payload shapes: ``CandidateSnapshot.summary()``,
# ``round_robin_decomposition``'s review-history entry, ``ReviewFinding``, and
# ``PriorFindingResolution``.
CANDIDATE_SUMMARY_FIELDS = frozenset(
    {"version", "author_provider", "sha256", "decision", "graph_delta_plan_id"}
)
REVIEW_HISTORY_ENTRY_FIELDS = frozenset(
    {
        "round_number",
        "reviewer_provider",
        "reviewed_candidate_sha256",
        "verdict",
        "summary",
        "findings",
        "prior_finding_resolutions",
    }
)
REVIEW_FINDING_FIELDS = frozenset(
    {
        "finding_id",
        "severity",
        "category",
        "affected_contracts",
        "problem",
        "required_resolution",
    }
)
PRIOR_FINDING_RESOLUTION_FIELDS = frozenset(
    {"finding_id", "status", "explanation"}
)

# Closed record vocabularies.
AUTHORIZATION_STATES = ("proposed", "authorized", "revoked")
AUTHORIZED_STATE = "authorized"
REVIEWER_KINDS = ("independent_provider_review",)

# Identities that can never be the human authorizer. The binder performs no I/O,
# so this is a closed constant set rather than a committed policy file read.
NON_HUMAN_AUTHORITY_LOGINS = frozenset(
    {
        "architect",
        "software-architect",
        "task-decomposer",
        "decomposition-reviewer",
        "github-actions",
    }
    | {provider.casefold() for provider in SUPPORTED_PROVIDERS}
)

MAX_REASON_CODES = 8

RECORD_AUTHORITY_FIELDS = (
    "schema_version",
    "task_id",
    "task_contract_sha256",
    "source_head",
    "decomposition_run_id",
    "decomposition_result_sha256",
    "graph_delta_plan_id",
    "graph_delta_canonical_sha256",
    "reviewed_candidate_sha256",
    "reviewer_kind",
    "reviewer_provider",
    "reviewer_invocation_id",
    "review_evidence_sha256",
    "authorizer_login",
    "authorization_state",
    "authorized_at_utc",
    "artifact_locator",
)
RECORD_FIELDS = RECORD_AUTHORITY_FIELDS + ("record_sha256",)

DECOMPOSITION_AUTHORIZATION_REASON_CODES = frozenset(
    {
        # not_authorized
        "authorization_state_not_authorized",
        "authorizer_not_in_allowlist",
        "authorizer_is_not_a_human_authority",
        # stale_binding
        "task_identity_drift",
        "source_head_drift",
        "decomposition_run_identity_drift",
        "exact_task_contract_bytes_drift",
        "semantic_parent_hash_substituted_for_exact_contract_bytes",
        # review_invalid
        "d1b_run_identity_unprovable",
        "d1b1_proposal_not_independently_reviewed",
        "d1b_run_authority_marker_invalid",
        "d1b_run_status_not_review_ready",
        "d1b_run_reported_rejection_reasons",
        "unresolved_review_findings",
        "bounded_call_accounting_invalid",
        "provider_rotation_inconsistent",
        "round_sequence_inconsistent",
        "reviewer_artifact_paths_missing",
        "review_history_resolution_semantics_invalid",
        "latest_candidate_identity_unprovable",
        "review_ready_artifacts_missing",
        "independent_reviewer_identity_missing",
        "reviewer_is_latest_candidate_author",
        "reviewer_provider_binding_mismatch",
        "independent_pass_round_missing",
        "independent_pass_round_invalid",
        "reviewer_invocation_identity_mismatch",
        "review_history_does_not_bind_reviewed_candidate",
        "review_evidence_identity_mismatch",
        # artifact_mismatch
        "decomposition_result_sha256_mismatch",
        "reviewed_candidate_sha256_mismatch",
        "record_candidate_identity_inconsistent",
        "d1b_candidate_sha256_mismatch",
        "decomposition_result_parent_task_mismatch",
        "decomposition_result_parent_revision_mismatch",
        "decomposition_result_parent_hash_mismatch",
        "decomposition_decision_not_decomposed",
        "graph_delta_plan_id_mismatch",
        "graph_delta_canonical_sha256_mismatch",
        "d1b_graph_delta_plan_id_mismatch",
        "graph_delta_parent_task_mismatch",
        "graph_delta_parent_revision_mismatch",
        "graph_delta_parent_before_hash_mismatch",
        "graph_delta_authority_marker_invalid",
    }
)


_RUN_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_PLAN_ID_RE = re.compile(r"^GDP-[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\[bot\])?$")
_ARTIFACT_LOCATOR_MAX_LENGTH = 512


class DecompositionAuthorizationContractError(TaskReviewContractError):
    """Raised when authorization inputs violate their exact API contract."""


class DecompositionAuthorizationStatus(str, Enum):
    AUTHORIZED = "authorized"
    NOT_AUTHORIZED = "not_authorized"
    STALE_BINDING = "stale_binding"
    REVIEW_INVALID = "review_invalid"
    ARTIFACT_MISMATCH = "artifact_mismatch"


DECOMPOSITION_AUTHORIZATION_STATUSES = tuple(
    status.value for status in DecompositionAuthorizationStatus
)


def _error(message: str) -> DecompositionAuthorizationContractError:
    return DecompositionAuthorizationContractError(message)


def _text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise _error(f"{field} must be an exact non-empty string")
    return value


def _pattern(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    text = _text(value, field=field)
    if not pattern.fullmatch(text):
        raise _error(f"{field} has an invalid identity")
    return text


def _member(value: Any, *, field: str, allowed: Iterable[str]) -> str:
    text = _text(value, field=field)
    if text not in tuple(allowed):
        raise _error(f"{field} is not a supported value")
    return text


def _utc_timestamp(value: Any, *, field: str) -> str:
    text = _pattern(value, field=field, pattern=_UTC_RE)
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise _error(f"{field} is not a real UTC calendar timestamp") from exc
    return text


def _artifact_locator(value: Any, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) > _ARTIFACT_LOCATOR_MAX_LENGTH:
        raise _error(f"{field} exceeds {_ARTIFACT_LOCATOR_MAX_LENGTH} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise _error(f"{field} contains a control character")
    return text


def _detached_json_object(value: Any, *, field: str) -> dict[str, Any]:
    """Return an exact detached JSON snapshot so callers' data is never touched."""

    if not isinstance(value, Mapping):
        raise _error(f"{field} must be an object")
    try:
        detached = json.loads(canonical_json(dict(value)))
    except (TypeError, ValueError, RecursionError) as exc:
        raise _error(f"{field} must contain exact finite JSON values") from exc
    if type(detached) is not dict:
        raise _error(f"{field} must remain an object")
    return detached


def authorization_record_sha256(fields: Mapping[str, Any]) -> str:
    """Canonical digest over the authority-bearing fields, excluding the digest.

    Any mutation of any authority-bearing field, including ``artifact_locator``,
    changes this digest and therefore invalidates the record.
    """

    detached = _detached_json_object(fields, field="authorization_record")
    actual = set(detached)
    expected = set(RECORD_AUTHORITY_FIELDS)
    if actual != expected:
        missing = sorted(expected - actual)
        extras = sorted(actual - expected)
        raise _error(
            "authorization_record authority fields do not match contract; "
            f"missing={missing}, extras={extras}"
        )
    for field in RECORD_AUTHORITY_FIELDS:
        if type(detached[field]) is not str:
            raise _error(f"authorization_record.{field} must be an exact string")
    return semantic_sha256(detached)


@dataclass(frozen=True)
class DecompositionAuthorizationRecord:
    """Immutable strict-schema human authorization record."""

    schema_version: str
    task_id: str
    task_contract_sha256: str
    source_head: str
    decomposition_run_id: str
    decomposition_result_sha256: str
    graph_delta_plan_id: str
    graph_delta_canonical_sha256: str
    reviewed_candidate_sha256: str
    reviewer_kind: str
    reviewer_provider: str
    reviewer_invocation_id: str
    review_evidence_sha256: str
    authorizer_login: str
    authorization_state: str
    authorized_at_utc: str
    artifact_locator: str
    record_sha256: str

    @classmethod
    def from_dict(cls, value: Any) -> "DecompositionAuthorizationRecord":
        detached = _detached_json_object(value, field="authorization_record")
        actual = set(detached)
        expected = set(RECORD_FIELDS)
        if actual != expected:
            missing = sorted(expected - actual)
            extras = sorted(actual - expected)
            raise _error(
                "authorization_record keys do not match contract; "
                f"missing={missing}, extras={extras}"
            )

        schema_version = _member(
            detached["schema_version"],
            field="authorization_record.schema_version",
            allowed=(DECOMPOSITION_AUTHORIZATION_SCHEMA_VERSION,),
        )
        record = cls(
            schema_version=schema_version,
            task_id=_pattern(
                detached["task_id"],
                field="authorization_record.task_id",
                pattern=TASK_ID_RE,
            ),
            task_contract_sha256=_pattern(
                detached["task_contract_sha256"],
                field="authorization_record.task_contract_sha256",
                pattern=SHA256_RE,
            ),
            source_head=_pattern(
                detached["source_head"],
                field="authorization_record.source_head",
                pattern=GIT_SHA_RE,
            ),
            decomposition_run_id=_pattern(
                detached["decomposition_run_id"],
                field="authorization_record.decomposition_run_id",
                pattern=_RUN_ID_RE,
            ),
            decomposition_result_sha256=_pattern(
                detached["decomposition_result_sha256"],
                field="authorization_record.decomposition_result_sha256",
                pattern=SHA256_RE,
            ),
            graph_delta_plan_id=_pattern(
                detached["graph_delta_plan_id"],
                field="authorization_record.graph_delta_plan_id",
                pattern=_PLAN_ID_RE,
            ),
            graph_delta_canonical_sha256=_pattern(
                detached["graph_delta_canonical_sha256"],
                field="authorization_record.graph_delta_canonical_sha256",
                pattern=SHA256_RE,
            ),
            reviewed_candidate_sha256=_pattern(
                detached["reviewed_candidate_sha256"],
                field="authorization_record.reviewed_candidate_sha256",
                pattern=SHA256_RE,
            ),
            reviewer_kind=_member(
                detached["reviewer_kind"],
                field="authorization_record.reviewer_kind",
                allowed=REVIEWER_KINDS,
            ),
            reviewer_provider=_member(
                detached["reviewer_provider"],
                field="authorization_record.reviewer_provider",
                allowed=sorted(SUPPORTED_PROVIDERS),
            ),
            reviewer_invocation_id=_pattern(
                detached["reviewer_invocation_id"],
                field="authorization_record.reviewer_invocation_id",
                pattern=_RUN_ID_RE,
            ),
            review_evidence_sha256=_pattern(
                detached["review_evidence_sha256"],
                field="authorization_record.review_evidence_sha256",
                pattern=SHA256_RE,
            ),
            authorizer_login=_pattern(
                detached["authorizer_login"],
                field="authorization_record.authorizer_login",
                pattern=_LOGIN_RE,
            ),
            authorization_state=_member(
                detached["authorization_state"],
                field="authorization_record.authorization_state",
                allowed=AUTHORIZATION_STATES,
            ),
            authorized_at_utc=_utc_timestamp(
                detached["authorized_at_utc"],
                field="authorization_record.authorized_at_utc",
            ),
            artifact_locator=_artifact_locator(
                detached["artifact_locator"],
                field="authorization_record.artifact_locator",
            ),
            record_sha256=_pattern(
                detached["record_sha256"],
                field="authorization_record.record_sha256",
                pattern=SHA256_RE,
            ),
        )

        expected_digest = authorization_record_sha256(record.authority_fields())
        if record.record_sha256 != expected_digest:
            raise _error(
                "authorization_record.record_sha256 does not bind its authority "
                "fields; the record was mutated after it was authorized"
            )
        return record

    def authority_fields(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in RECORD_AUTHORITY_FIELDS}

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in RECORD_FIELDS}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True)
class DecompositionAuthorizationDecision:
    """Immutable typed outcome. Carries identities only, never artifact bodies."""

    status: DecompositionAuthorizationStatus
    task_id: str
    plan_id: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.status) is not DecompositionAuthorizationStatus:
            raise _error("decision status must be a DecompositionAuthorizationStatus")
        if type(self.reason_codes) is not tuple:
            raise _error("decision reason_codes must be an exact tuple")
        if len(self.reason_codes) > MAX_REASON_CODES:
            raise _error("decision reason_codes exceeded its bounded length")
        unknown = [
            code
            for code in self.reason_codes
            if code not in DECOMPOSITION_AUTHORIZATION_REASON_CODES
        ]
        if unknown:
            raise _error(f"decision reason_codes are not in the closed vocabulary: {unknown}")
        if (self.status is DecompositionAuthorizationStatus.AUTHORIZED) != (
            not self.reason_codes
        ):
            raise _error(
                "authorized decisions carry no reason code and every other status "
                "must name at least one"
            )

    @property
    def is_authorized(self) -> bool:
        return self.status is DecompositionAuthorizationStatus.AUTHORIZED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "reason_codes": list(self.reason_codes),
        }


def _bounded(codes: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for code in codes:
        if code not in ordered:
            ordered.append(code)
    return tuple(ordered[:MAX_REASON_CODES])


def _normalized_allowlist(authorized_authorizers: Any) -> frozenset[str]:
    if isinstance(authorized_authorizers, (str, bytes)) or not isinstance(
        authorized_authorizers, Iterable
    ):
        raise _error("authorized_authorizers must be an iterable of login strings")
    normalized: list[str] = []
    for entry in authorized_authorizers:
        if type(entry) is not str:
            raise _error("authorized_authorizers entries must be exact strings")
        identity = normalize_login(entry)
        if not identity:
            raise _error("authorized_authorizers contains an empty identity")
        if identity in normalized:
            raise _error(f"authorized_authorizers contains duplicate identity {identity!r}")
        normalized.append(identity)
    if not normalized:
        # Fail closed: an empty allowlist is a caller contract error, never an
        # implicit "anyone may authorize".
        raise _error("authorized_authorizers must contain at least one human login")
    return frozenset(normalized)


def _require_typed_artifacts(
    decomposition_result: Any, graph_delta: Any
) -> tuple[dict[str, Any], str, str]:
    if type(decomposition_result) is not DecompositionResult:
        raise _error("decomposition_result must be an exact DecompositionResult")
    if type(graph_delta) is not GraphDeltaPlan:
        raise _error("graph_delta must be an exact GraphDeltaPlan")

    canonical = graph_delta.canonical_json()
    if type(canonical) is not str or not canonical:
        raise _error("graph_delta canonical JSON must be a non-empty string")
    payload = _detached_json_object(json.loads(canonical), field="graph_delta")
    if GraphDeltaPlan.from_payload(payload).canonical_json() != canonical:
        raise _error("graph_delta serialization is not canonical JSON")
    plan_id = _pattern(
        payload.get("plan_id"), field="graph_delta.plan_id", pattern=_PLAN_ID_RE
    )
    # Same identity semantics plan_graph_apply() uses for a stored reviewed plan.
    return payload, plan_id, _canonical_json_sha256(canonical)


def _nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if type(current) is not dict or key not in current:
            return None
        current = current[key]
    return current


def _matched(value: Any, pattern: re.Pattern[str]) -> str | None:
    if type(value) is not str or not pattern.fullmatch(value):
        return None
    return value


def _in_vocabulary(value: Any, allowed: frozenset[str]) -> bool:
    """Closed-vocabulary membership that fails closed for any non-string value.

    Untrusted D1B data can hold a list or object where a provider, severity, or
    status belongs. Plain ``in`` would raise on an unhashable value, and this
    module owes its caller a typed decision rather than a ``TypeError``.
    """

    return type(value) is str and value in allowed


@dataclass(frozen=True)
class _RunIdentity:
    """The exact identity chain the D1B run itself declares."""

    task_id: str
    run_id: str
    head_commit: str
    exact_contract_sha256: str
    semantic_parent_task_id: str
    semantic_parent_revision: int
    semantic_parent_sha256: str


def _run_identity(run: Mapping[str, Any]) -> _RunIdentity | None:
    task_id = _matched(run.get("task_id"), TASK_ID_RE)
    run_id = _matched(run.get("run_id"), _RUN_ID_RE)
    head_commit = _matched(_nested(run, "source_identity", "head_commit"), GIT_SHA_RE)
    exact_contract = _matched(
        _nested(run, "task_execution_contract_identity", "sha256"), SHA256_RE
    )
    # The D1A semantic parent identity is the head of the parent chain the
    # supplied DecompositionResult and GraphDeltaPlan must both be built on, so
    # a run that cannot state it is unprovable rather than merely stale.
    parent_task_id = _matched(
        _nested(run, "d1a_semantic_parent_identity", "task_id"), TASK_ID_RE
    )
    parent_revision = _nested(run, "d1a_semantic_parent_identity", "contract_revision")
    parent_sha256 = _matched(
        _nested(run, "d1a_semantic_parent_identity", "contract_sha256"), SHA256_RE
    )
    if None in (task_id, run_id, head_commit, exact_contract, parent_task_id, parent_sha256):
        return None
    if type(parent_revision) is not int or parent_revision < 1:
        return None
    return _RunIdentity(
        task_id=task_id,
        run_id=run_id,
        head_commit=head_commit,
        exact_contract_sha256=exact_contract,
        semantic_parent_task_id=parent_task_id,
        semantic_parent_revision=parent_revision,
        semantic_parent_sha256=parent_sha256,
    )


def _not_authorized_reasons(
    record: DecompositionAuthorizationRecord, allowlist: frozenset[str]
) -> list[str]:
    reasons: list[str] = []
    if record.authorization_state != AUTHORIZED_STATE:
        reasons.append("authorization_state_not_authorized")
    authorizer = normalize_login(record.authorizer_login)
    if authorizer not in allowlist:
        reasons.append("authorizer_not_in_allowlist")
    if (
        authorizer in NON_HUMAN_AUTHORITY_LOGINS
        or authorizer.endswith("[bot]")
        or authorizer == normalize_login(record.reviewer_provider)
    ):
        # The reviewing provider and pipeline automation can never supply the
        # human authorization this binder requires.
        reasons.append("authorizer_is_not_a_human_authority")
    return reasons


def _stale_binding_reasons(
    record: DecompositionAuthorizationRecord, identity: _RunIdentity
) -> list[str]:
    reasons: list[str] = []
    if (
        record.task_id != identity.task_id
        or record.task_id != identity.semantic_parent_task_id
    ):
        reasons.append("task_identity_drift")
    if record.source_head != identity.head_commit:
        reasons.append("source_head_drift")
    if record.decomposition_run_id != identity.run_id:
        reasons.append("decomposition_run_identity_drift")
    if record.task_contract_sha256 != identity.exact_contract_sha256:
        reasons.append("exact_task_contract_bytes_drift")
        if record.task_contract_sha256 == identity.semantic_parent_sha256:
            # The D1A semantic parent hash is a different identity and never
            # substitutes for the exact task-contract bytes.
            reasons.append("semantic_parent_hash_substituted_for_exact_contract_bytes")
    return reasons


def _approving_round(run: Mapping[str, Any]) -> dict[str, Any] | None:
    rounds = run.get("rounds")
    if type(rounds) is not list or not rounds:
        return None
    final = rounds[-1]
    if type(final) is not dict:
        return None
    if final.get("status") != D1B2_INDEPENDENT_PASS_ROUND_STATUS:
        return None
    return final


def _invocation_ids_in_round(
    approving_round: Mapping[str, Any], round_number: int
) -> list[str | None]:
    """The invocation identity each exact producer artifact reference names.

    ``round_robin_decomposition`` records
    ``rounds/NN/task_execution/<invocation_id>/task_request.json`` and
    ``rounds/NN/agent_runtime/<invocation_id>/result.json`` only for a round whose
    artifacts it actually observed on disk, and stores ``None`` otherwise. An
    entry is ``None`` here whenever the recorded value is absent or does not match
    that exact shape, so a run carrying no reviewer artifacts cannot authorize.
    """

    identities: list[str | None] = []
    for field, directory, filename in ROUND_ARTIFACT_REFERENCES:
        value = approving_round.get(field)
        identity: str | None = None
        if type(value) is str:
            parts = value.split("/")
            if (
                len(parts) == 5
                and parts[0] == "rounds"
                and parts[1] == f"{round_number:02d}"
                and parts[2] == directory
                and parts[4] == filename
                and _RUN_ID_RE.fullmatch(parts[3])
            ):
                identity = parts[3]
        identities.append(identity)
    return identities


def _validated_provider_order(run: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The exact rotation the producer validated, or ``None`` when impossible."""

    order = run.get("provider_order")
    if type(order) is not list:
        return None
    try:
        return validate_provider_order(order)
    except DecompositionPreflightError:
        return None


def _call_accounting_valid(run: Mapping[str, Any], rounds: Any) -> bool:
    """Bounded-run accounting the producer guarantees for a review_ready run.

    Every executed round appends exactly one round summary, rounds 2..N are the
    reviewer rounds and each appends exactly one review-history entry, so an
    impossible shape such as ``max_calls=1`` with ``calls_used=99`` is rejected
    before any of its self-reported review evidence is read.
    """

    max_calls = run.get("max_calls")
    calls_used = run.get("calls_used")
    if type(max_calls) is not int or type(calls_used) is not int:
        return False
    try:
        round_robin_call_limit(max_calls)
    except DecompositionPreflightError:
        return False
    if not 2 <= calls_used <= max_calls:
        return False
    if type(rounds) is not list or len(rounds) != calls_used:
        return False
    history = run.get("finding_history")
    return type(history) is list and len(history) == calls_used - 1


def _candidate_summary_snapshot(value: Any) -> dict[str, Any] | None:
    """A complete producer ``CandidateSnapshot.summary()`` payload, or ``None``.

    ``round_robin_decomposition`` publishes a candidate only through this exact
    five-field summary, so anything else is not a candidate this binder can bind.
    """

    if type(value) is not dict or set(value) != CANDIDATE_SUMMARY_FIELDS:
        return None
    if _matched(value.get("sha256"), SHA256_RE) is None:
        return None
    if not _in_vocabulary(value.get("author_provider"), SUPPORTED_PROVIDERS):
        return None
    version = value.get("version")
    if type(version) is not int or version < 1:
        return None
    return value


def _reviewer_round_consistent_with_history(
    entry: Mapping[str, Any], history: Any, round_number: int
) -> bool:
    """True when a reviewer round reports the review its history entry recorded.

    The producer copies ``verdict`` and ``new_finding_ids`` out of the same
    validated review it appends to ``finding_history``, so a round claiming an
    outcome the history never recorded is not a producer shape. A malformed
    history entry is deferred to the ordered replay in
    ``_blocking_findings_resolved`` rather than being judged twice here.
    """

    if type(history) is not list:
        return False
    index = round_number - 2
    if not 0 <= index < len(history):
        return False
    review = history[index]
    if type(review) is not dict:
        return True
    if entry.get("verdict") != review.get("verdict"):
        return False
    findings = review.get("findings")
    if type(findings) is not list or any(
        type(finding) is not dict or type(finding.get("finding_id")) is not str
        for finding in findings
    ):
        return True
    return entry.get("new_finding_ids") == [
        finding["finding_id"] for finding in findings
    ]


def _round_chain_invalid(
    rounds: list[Any], order: tuple[str, ...], history: Any
) -> bool:
    """True when the rounds are not a producer-valid ``review_ready`` circuit.

    ``round_robin_decomposition`` emits exactly one round chain for a run that
    reaches ``review_ready``:

    * round 1 authors version 1 and is ``candidate_valid``; it never carries a
      verdict, a finding, or an approval, and if the call limit ends there the
      producer returns ``needs_human`` instead;
    * every middle round is a reviewer ``revise`` that publishes the next
      candidate version as ``revised_candidate_valid`` and leaves at least one
      blocking finding outstanding, and the revised candidate becomes the
      candidate the next round reviews;
    * the final round is a reviewer ``pass`` recorded as ``independent_pass``,
      which publishes no candidate and leaves nothing unresolved.

    The producer's loop breaks as soon as ``run_status`` becomes ``review_ready``,
    so an ``independent_pass`` is terminal and no later round can exist. Rounds
    also take the next provider in the validated rotation and report the
    AgentRuntime identity that provider actually runs as.
    """

    if len(rounds) < 2:
        return True

    last_index = len(rounds) - 1
    previous_candidate: dict[str, Any] | None = None

    for index, entry in enumerate(rounds):
        round_number = index + 1
        is_author_round = round_number == 1
        if type(entry) is not dict:
            return True
        expected_role = (
            D1B2_DECOMPOSER_ROLE if is_author_round else D1B2_REVIEWER_ROLE
        )
        expected_provider = order[(round_number - 1) % len(order)]
        if type(entry.get("round_number")) is not int:
            return True
        if (
            entry.get("round_number") != round_number
            or entry.get("role") != expected_role
            or entry.get("requested_provider") != expected_provider
            or entry.get("actual_provider")
            != RUNTIME_PROVIDER_IDENTIFIERS[expected_provider]
            or entry.get("agent_status") != "succeeded"
            or entry.get("rejection_reasons") != []
            or entry.get("authority") != REVIEW_ONLY_AUTHORITY
        ):
            return True

        # Each round opens on the candidate the previous round published.
        if entry.get("candidate_before") != previous_candidate:
            return True

        candidate_after = entry.get("candidate_after")
        unresolved = entry.get("unresolved_finding_ids")

        if is_author_round:
            if (
                entry.get("status") != D1B2_INITIAL_CANDIDATE_ROUND_STATUS
                or entry.get("verdict") is not None
                or entry.get("new_finding_ids") != []
                or unresolved != []
            ):
                return True
            published = _candidate_summary_snapshot(candidate_after)
            if (
                published is None
                or published["version"] != 1
                or published["author_provider"] != expected_provider
            ):
                return True
            previous_candidate = published
            continue

        if not _reviewer_round_consistent_with_history(entry, history, round_number):
            return True

        if index == last_index:
            if (
                entry.get("status") != D1B2_INDEPENDENT_PASS_ROUND_STATUS
                or entry.get("verdict") != "pass"
                or candidate_after is not None
                or unresolved != []
            ):
                return True
            continue

        # A non-terminal reviewer round of a review_ready circuit can only be
        # the producer's revision outcome; a pass or needs_human would have
        # ended the run here.
        if (
            entry.get("status") != D1B2_REVISED_CANDIDATE_ROUND_STATUS
            or entry.get("verdict") != "revise"
            or type(unresolved) is not list
            or not unresolved
        ):
            return True
        published = _candidate_summary_snapshot(candidate_after)
        if (
            published is None
            or previous_candidate is None
            or published["version"] != previous_candidate["version"] + 1
            or published["sha256"] == previous_candidate["sha256"]
            or published["author_provider"] != expected_provider
        ):
            return True
        previous_candidate = published
    return False


def _review_invalid_reasons(
    record: DecompositionAuthorizationRecord,
    run: Mapping[str, Any],
    identity: _RunIdentity,
) -> list[str]:
    reasons: list[str] = []

    if (
        run.get("mode") != D1B2_RUN_MODE
        or run.get("schema_version") != ROUND_ROBIN_RUN_RESULT_SCHEMA_VERSION
    ):
        # A D1B.1 single-provider proposal is never independently reviewed.
        return ["d1b1_proposal_not_independently_reviewed"]

    if run.get("authority") != REVIEW_ONLY_AUTHORITY:
        reasons.append("d1b_run_authority_marker_invalid")
    if run.get("run_status") != D1B2_REVIEW_READY_STATUS:
        reasons.append("d1b_run_status_not_review_ready")
    if run.get("rejection_reasons") != []:
        reasons.append("d1b_run_reported_rejection_reasons")
    if run.get("unresolved_findings") != []:
        reasons.append("unresolved_review_findings")

    latest_summary = _candidate_summary_snapshot(run.get("latest_candidate"))
    candidate_sha = latest_summary["sha256"] if latest_summary is not None else None
    author_provider = (
        latest_summary["author_provider"] if latest_summary is not None else None
    )
    if latest_summary is None:
        reasons.append("latest_candidate_identity_unprovable")

    # The producer names the artifacts it actually published, so the exact file
    # names are the evidence. A graph delta exists exactly when the latest
    # candidate declares a plan ID; a candidate that declares none published no
    # graph_delta.json and cannot yield an authorizable plan here either.
    expects_graph_delta = latest_summary is not None and (
        _matched(latest_summary.get("graph_delta_plan_id"), _PLAN_ID_RE) is not None
    )
    expected_graph_delta_path = (
        D1B2_GRAPH_DELTA_FILENAME if expects_graph_delta else None
    )
    if (
        run.get("decomposition_result_path") != D1B2_DECOMPOSITION_RESULT_FILENAME
        or run.get("graph_delta_path") != expected_graph_delta_path
    ):
        reasons.append("review_ready_artifacts_missing")

    # A bounded circuit that could not have run this way cannot authorize, even
    # when its top-level fields claim review_ready.
    order = _validated_provider_order(run)
    rounds = run.get("rounds")
    if order is None:
        reasons.append("provider_rotation_inconsistent")
    if not _call_accounting_valid(run, rounds):
        reasons.append("bounded_call_accounting_invalid")
    elif order is not None and _round_chain_invalid(
        rounds, order, run.get("finding_history")
    ):
        reasons.append("round_sequence_inconsistent")

    # The logical reviewer vocabulary and type are proven before any runtime
    # provider mapping is attempted, so a malformed approver produces a typed
    # fail-closed decision rather than a KeyError or TypeError.
    approver = run.get("independent_approver_provider")
    approver_supported = _in_vocabulary(approver, SUPPORTED_PROVIDERS)
    if not approver_supported:
        reasons.append("independent_reviewer_identity_missing")
    else:
        if approver == author_provider:
            reasons.append("reviewer_is_latest_candidate_author")
        if approver != record.reviewer_provider:
            reasons.append("reviewer_provider_binding_mismatch")

    approving_round = _approving_round(run)
    if approving_round is None:
        reasons.append("independent_pass_round_missing")
    else:
        round_number = approving_round.get("round_number")
        approver_bound_to_round = (
            approver_supported
            and approving_round.get("requested_provider") == approver
            and approving_round.get("actual_provider")
            == RUNTIME_PROVIDER_IDENTIFIERS[approver]
        )
        if (
            type(round_number) is not int
            or round_number < 2
            or approving_round.get("role") != D1B2_REVIEWER_ROLE
            or approving_round.get("verdict") != "pass"
            or approving_round.get("agent_status") != "succeeded"
            or approving_round.get("rejection_reasons") != []
            or approving_round.get("authority") != REVIEW_ONLY_AUTHORITY
            or approving_round.get("candidate_after") is not None
            or approving_round.get("unresolved_finding_ids") != []
            or not approver_bound_to_round
            or latest_summary is None
            or approving_round.get("candidate_before") != latest_summary
        ):
            # The reviewer contract keeps the logical provider name, while the
            # round reports the AgentRuntime identity that reviewer really ran
            # as. A PASS round also reviews the exact latest candidate, so its
            # complete candidate_before summary is that candidate.
            reasons.append("independent_pass_round_invalid")
        else:
            expected_invocation_id = _round_invocation_id(
                identity.task_id, identity.run_id, round_number, D1B2_REVIEWER_ROLE
            )
            observed = _invocation_ids_in_round(approving_round, round_number)
            if any(observed_id is None for observed_id in observed):
                reasons.append("reviewer_artifact_paths_missing")
            if record.reviewer_invocation_id != expected_invocation_id or any(
                observed_id != expected_invocation_id for observed_id in observed
            ):
                reasons.append("reviewer_invocation_identity_mismatch")

        history = run.get("finding_history")
        entry = history[-1] if type(history) is list and history else None
        if (
            type(entry) is not dict
            or entry.get("verdict") != "pass"
            or entry.get("round_number") != round_number
            or entry.get("reviewer_provider") != approver
            or entry.get("reviewed_candidate_sha256") != candidate_sha
            or candidate_sha is None
        ):
            reasons.append("review_history_does_not_bind_reviewed_candidate")
        elif not _blocking_findings_resolved(history):
            reasons.append("review_history_resolution_semantics_invalid")
        elif semantic_sha256(entry) != record.review_evidence_sha256:
            reasons.append("review_evidence_identity_mismatch")

    return reasons


def _blocking_findings_resolved(history: list[Any]) -> bool:
    """Replay the producer's own ordered review semantics over the history.

    ``review_policy.validate_decomposition_review`` is the authority. Each review
    resolves exactly the findings that are outstanding when it runs, may only
    raise new findings under its own round prefix, and may only PASS once nothing
    is outstanding. Replaying that sequence means a fabricated resolution cannot
    clear a finding that was never validly raised, a resolution cannot address a
    finding that is not outstanding, and a final PASS cannot introduce a blocking
    finding. Resolution status is read from the emitted ``status`` field, which is
    the only field ``PriorFindingResolution`` publishes.
    """

    outstanding: set[str] = set()
    known_finding_ids: set[str] = set()
    for index, entry in enumerate(history):
        round_number = index + 2  # rounds 1 authors; 2..N review.
        if type(entry) is not dict or set(entry) != REVIEW_HISTORY_ENTRY_FIELDS:
            return False
        if type(entry["round_number"]) is not int:
            return False
        if entry["round_number"] != round_number:
            return False
        if not _in_vocabulary(entry["reviewer_provider"], SUPPORTED_PROVIDERS):
            return False
        findings = entry["findings"]
        resolutions = entry["prior_finding_resolutions"]
        if type(findings) is not list or type(resolutions) is not list:
            return False

        addressed: set[str] = set()
        cleared: set[str] = set()
        for resolution in resolutions:
            if (
                type(resolution) is not dict
                or set(resolution) != PRIOR_FINDING_RESOLUTION_FIELDS
            ):
                return False
            finding_id = resolution["finding_id"]
            status = resolution["status"]
            if type(finding_id) is not str or not _in_vocabulary(
                status, FINDING_RESOLUTION_STATUSES
            ):
                return False
            if finding_id in addressed:
                return False
            addressed.add(finding_id)
            if status in RESOLVED_FINDING_RESOLUTIONS:
                cleared.add(finding_id)
        if addressed != outstanding:
            # A review must cover exactly the outstanding blocking findings.
            return False
        outstanding -= cleared

        introduced: set[str] = set()
        for finding in findings:
            if type(finding) is not dict or set(finding) != REVIEW_FINDING_FIELDS:
                return False
            finding_id = finding["finding_id"]
            severity = finding["severity"]
            if type(finding_id) is not str or not FINDING_ID_RE.fullmatch(finding_id):
                return False
            if not _in_vocabulary(severity, FINDING_SEVERITIES):
                return False
            if finding_id in introduced or finding_id in known_finding_ids:
                return False
            if not finding_id.startswith(f"round-{round_number:02d}-"):
                return False
            introduced.add(finding_id)
            if severity == "blocking":
                outstanding.add(finding_id)
        known_finding_ids |= introduced

        verdict = entry["verdict"]
        if verdict == "pass":
            # A PASS ends the circuit, so it is the final entry and leaves and
            # introduces nothing blocking.
            if outstanding or index != len(history) - 1:
                return False
        elif verdict == "revise":
            if not outstanding:
                return False
        else:
            # needs_human ends a bounded run without a review_ready candidate.
            return False
    return not outstanding


def _artifact_mismatch_reasons(
    record: DecompositionAuthorizationRecord,
    run: Mapping[str, Any],
    identity: _RunIdentity,
    decomposition_result: DecompositionResult,
    plan_payload: Mapping[str, Any],
    plan_id: str,
    plan_canonical_sha256: str,
) -> list[str]:
    reasons: list[str] = []

    # Recomputed from the typed object; a caller-supplied hash is never trusted.
    recomputed_candidate = candidate_sha256(decomposition_result)
    if record.decomposition_result_sha256 != recomputed_candidate:
        reasons.append("decomposition_result_sha256_mismatch")
    if record.reviewed_candidate_sha256 != recomputed_candidate:
        reasons.append("reviewed_candidate_sha256_mismatch")
    if record.decomposition_result_sha256 != record.reviewed_candidate_sha256:
        reasons.append("record_candidate_identity_inconsistent")
    if _nested(run, "latest_candidate", "sha256") != recomputed_candidate:
        reasons.append("d1b_candidate_sha256_mismatch")

    # One exact parent chain: the D1B run's D1A semantic parent identity, the
    # supplied DecompositionResult's parent_task, and the GraphDeltaPlan the
    # record names must all describe the same parent contract revision and the
    # same semantic parent hash. ``plan_graph_delta`` computes parent_before_hash
    # with the same canonical semantic hash the D1A identity carries, so a plan
    # built against a different parent revision or hash cannot authorize even
    # after its own canonical digest is recomputed.
    parent = decomposition_result.parent_task
    if (
        parent.task_id != record.task_id
        or parent.task_id != identity.semantic_parent_task_id
    ):
        reasons.append("decomposition_result_parent_task_mismatch")
    if parent.contract_revision != identity.semantic_parent_revision:
        reasons.append("decomposition_result_parent_revision_mismatch")
    if parent.contract_sha256 != identity.semantic_parent_sha256:
        reasons.append("decomposition_result_parent_hash_mismatch")
    if (
        decomposition_result.decision != DECOMPOSED_DECISION
        or run.get("decision") != DECOMPOSED_DECISION
        or _nested(run, "latest_candidate", "decision") != DECOMPOSED_DECISION
    ):
        # Only a decomposed candidate produces a GraphDeltaPlan to authorize.
        reasons.append("decomposition_decision_not_decomposed")

    if record.graph_delta_plan_id != plan_id:
        reasons.append("graph_delta_plan_id_mismatch")
    if record.graph_delta_canonical_sha256 != plan_canonical_sha256:
        reasons.append("graph_delta_canonical_sha256_mismatch")
    if _nested(run, "latest_candidate", "graph_delta_plan_id") != plan_id:
        reasons.append("d1b_graph_delta_plan_id_mismatch")
    if (
        _nested(plan_payload, "parent_before_summary", "task_id")
        != identity.semantic_parent_task_id
    ):
        reasons.append("graph_delta_parent_task_mismatch")
    if (
        _nested(plan_payload, "parent_before_summary", "contract_revision")
        != identity.semantic_parent_revision
    ):
        reasons.append("graph_delta_parent_revision_mismatch")
    if plan_payload.get("parent_before_hash") != identity.semantic_parent_sha256:
        reasons.append("graph_delta_parent_before_hash_mismatch")
    if plan_payload.get("authority") != REVIEW_ONLY_AUTHORITY:
        reasons.append("graph_delta_authority_marker_invalid")
    return reasons


def validate_decomposition_authorization(
    *,
    record: Mapping[str, Any],
    d1b_run_result: Mapping[str, Any],
    decomposition_result: DecompositionResult,
    graph_delta: GraphDeltaPlan,
    authorized_authorizers: Iterable[str],
) -> DecompositionAuthorizationDecision:
    """Decide whether one exact record authorizes one exact reviewed plan.

    The function is pure: it reads detached snapshots of its inputs, mutates
    nothing, and performs no file, Git, GitHub, subprocess, network, or model
    access. Classification precedence is deterministic:

    1. malformed record/allowlist/typed artifact -> contract error;
    2. record not authorized, or authorizer not an allowed human -> ``not_authorized``;
    3. task/source/run/exact-contract identity drift -> ``stale_binding``;
    4. D1B.2 independent-review contract unproven -> ``review_invalid``;
    5. artifact identity mismatch -> ``artifact_mismatch``;
    6. every exact check passes -> ``authorized``.

    Identity that cannot be extracted from ``d1b_run_result`` at all is reported
    as ``review_invalid``, because an unprovable run cannot be shown to be stale.
    """

    parsed = DecompositionAuthorizationRecord.from_dict(record)
    allowlist = _normalized_allowlist(authorized_authorizers)
    run = _detached_json_object(d1b_run_result, field="d1b_run_result")
    plan_payload, plan_id, plan_canonical_sha256 = _require_typed_artifacts(
        decomposition_result, graph_delta
    )

    def decide(
        status: DecompositionAuthorizationStatus, reasons: Iterable[str]
    ) -> DecompositionAuthorizationDecision:
        return DecompositionAuthorizationDecision(
            status=status,
            task_id=parsed.task_id,
            plan_id=plan_id,
            reason_codes=_bounded(reasons),
        )

    not_authorized = _not_authorized_reasons(parsed, allowlist)
    if not_authorized:
        return decide(DecompositionAuthorizationStatus.NOT_AUTHORIZED, not_authorized)

    identity = _run_identity(run)
    if identity is None:
        return decide(
            DecompositionAuthorizationStatus.REVIEW_INVALID,
            ["d1b_run_identity_unprovable"],
        )

    stale = _stale_binding_reasons(parsed, identity)
    if stale:
        return decide(DecompositionAuthorizationStatus.STALE_BINDING, stale)

    review = _review_invalid_reasons(parsed, run, identity)
    if review:
        return decide(DecompositionAuthorizationStatus.REVIEW_INVALID, review)

    mismatch = _artifact_mismatch_reasons(
        parsed,
        run,
        identity,
        decomposition_result,
        plan_payload,
        plan_id,
        plan_canonical_sha256,
    )
    if mismatch:
        return decide(DecompositionAuthorizationStatus.ARTIFACT_MISMATCH, mismatch)

    return decide(DecompositionAuthorizationStatus.AUTHORIZED, ())


__all__ = [
    "AUTHORIZATION_STATES",
    "AUTHORIZED_STATE",
    "DECOMPOSITION_AUTHORIZATION_REASON_CODES",
    "DECOMPOSITION_AUTHORIZATION_SCHEMA_VERSION",
    "DECOMPOSITION_AUTHORIZATION_STATUSES",
    "D1B2_DECOMPOSITION_RESULT_FILENAME",
    "D1B2_GRAPH_DELTA_FILENAME",
    "RECORD_AUTHORITY_FIELDS",
    "RECORD_FIELDS",
    "REVIEWER_KINDS",
    "DecompositionAuthorizationContractError",
    "DecompositionAuthorizationDecision",
    "DecompositionAuthorizationRecord",
    "DecompositionAuthorizationStatus",
    "authorization_record_sha256",
    "validate_decomposition_authorization",
]
