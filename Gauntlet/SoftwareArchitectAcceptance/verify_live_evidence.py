"""Verify a live proof from a strictly bound, grounded scheduler evidence envelope.

The retired Gauntlet's most durable lesson was that prose is not evidence. A
run either produced machine-readable records that can be re-checked, or it
produced an opinion.

Two rounds of independent audit showed that field *shape* is not evidence
either. A file containing only `{"event":"poll_started"}` exited 0; so did a
scenario-A envelope with one launch instead of two, a fabricated source
HEAD/tree, a malformed repository identity, and a scheduler ID that matched
nothing; so did a scenario-D wait carrying an invented overlap token with no
reservation observation behind it; so did scenario J with two fabricated lock
strings. Each of those is now impossible, because the envelope is checked
against three independent authorities rather than against itself:

```text
1  the envelope's own binding    schema, run ID, scenario, manifest hash,
                                 contiguous sequence, complete poll lifecycle
2  the selected manifest scenario steps, tasks, declared surfaces, exclusive
                                 resources, advisories, transitions
3  the actual --source checkout   real HEAD, real tree, real repository identity
```

```text
line 1        run_metadata   schema, run ID, scenario, manifest hash,
                             repository identity, source HEAD/tree, scheduler
                             ID, start timestamp
lines 2..n    events         closed schema, contiguous sequence, every one bound
                             to the same run, scenario and poll
```

Everything fails closed:

- an unknown event type, an unknown field, or a missing required field is an
  error, not a shrug;
- every task ID an event names must exist in the selected manifest scenario, so
  `NSC-999` cannot be claimed;
- a mismatched manifest hash, run ID, scenario ID, sequence, poll, or timestamp
  form is an error;
- a poll that never finishes, or an event outside a poll, is an error;
- a wait must carry structured conflicting identities and overlapping tokens
  **that are grounded in both the scenario's contract facts and the observed
  reservation state**, so neither prose nor an invented token can satisfy a
  structured requirement;
- **REQUIRED `UNPROVEN` is non-success.** Exit 0 means every check the scenario
  declared required, plus every grounding check this verifier always applies,
  was PROVEN.

## `--source` is grounding, not decoration

`--source` names the checkout the run actually executed against. The recorded
`source_head`, `source_tree` and `repository` must equal what Git reports there
now. Without it nothing anchors the envelope to a real repository, so the
mandatory `source_identity_grounded` check is UNPROVEN and the run cannot pass.

Local claim refs and working-tree cleanliness remain **diagnostics**: one local
checkout says nothing about a frozen remote or a private repository's authority,
so those never gate the exit code.

## Deliberately absent: decomposition authority

An earlier draft parsed a five-step decomposition chain and could be satisfied
by fabricated hashes. Decomposition, graph-delta application, and the
independent-authorization boundary are removed from the active manifest and
from this verifier entirely; a `decomposition_proposed` event is now rejected as
an unknown event type. Their future specifications live in
`LIVE_PROOF_CHECKLIST.md` and must not be re-added here until real artifacts and
a durable authorization schema exist.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import manifest as manifest_module
import scenario_world as sw
from acceptance_lib import (
    EVIDENCE_SCHEMA_VERSION,
    MANDATORY_LIVE_GROUNDING_CHECKS,
    MANIFEST_PATH,
    AcceptanceSafetyError,
    canonical_sha256,
    git_lines,
    looks_like_production_repository,
    normalize_repository_identity,
    normalize_tokens,
    read_repository_identity,
    run_git,
)

STATUS_PROVEN = "PROVEN"
STATUS_FAILED = "FAILED"
STATUS_UNPROVEN = "UNPROVEN"

METADATA_EVENT = "run_metadata"
EVENT_POLL_STARTED = "poll_started"
EVENT_POLL_FINISHED = "poll_finished"
EVENT_RESERVATIONS = "integration_reservations_observed"
EVENT_WORKER_LAUNCHED = "worker_launched"
EVENT_CANDIDATE_WAITED = "candidate_waited"
EVENT_HUMAN_REVIEW = "architect_human_review"
EVENT_LOCK_ACQUIRED = "scheduler_lock_acquired"
EVENT_LOCK_REJECTED = "scheduler_already_active"

COMMON_EVENT_FIELDS = frozenset({"event", "sequence", "run_id", "scenario_id", "poll_id"})

EVENT_SCHEMAS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # event -> (extra required fields, extra optional fields)
    EVENT_POLL_STARTED: (frozenset({"poll_index", "scheduler_id"}), frozenset()),
    EVENT_POLL_FINISHED: (
        frozenset({"poll_index", "scheduler_id", "outcome"}),
        frozenset(),
    ),
    EVENT_RESERVATIONS: (frozenset({"scheduler_id", "reservations"}), frozenset()),
    EVENT_WORKER_LAUNCHED: (
        frozenset({"task_id", "worker_id", "scheduler_id", "argv"}),
        frozenset(),
    ),
    EVENT_CANDIDATE_WAITED: (
        frozenset({"task_id", "scheduler_id", "wait_kind", "reservation_fingerprint"}),
        frozenset(
            {
                "conflicting_task_id",
                "overlapping_values",
                "disjointness_verdict",
                "advisory_defects",
                "reason",
            }
        ),
    ),
    EVENT_HUMAN_REVIEW: (
        frozenset(
            {"task_id", "scheduler_id", "escalation_category", "escalation_question"}
        ),
        frozenset(),
    ),
    EVENT_LOCK_ACQUIRED: (
        frozenset(
            {
                "scheduler_id",
                "lock_identity",
                "lock_path",
                "checkout_root",
                "contest_id",
            }
        ),
        frozenset(),
    ),
    EVENT_LOCK_REJECTED: (
        frozenset(
            {
                "scheduler_id",
                "lock_identity",
                "lock_path",
                "checkout_root",
                "contest_id",
                "holder_scheduler_id",
            }
        ),
        frozenset(),
    ),
}

RESERVATION_FIELDS = (
    frozenset({"task_id", "actual_paths", "surface_unknown"}),
    frozenset({"predicted_paths", "exclusive_resources"}),
)

METADATA_FIELDS = frozenset(
    {
        "event",
        "schema_version",
        "run_id",
        "scenario_id",
        "manifest_sha256",
        "repository",
        "source_head",
        "source_tree",
        "scheduler_id",
        "run_started_at",
    }
)

CONFLICT_WAIT_KINDS = frozenset(manifest_module.VALID_CONFLICT_KINDS)
UNKNOWN_SURFACE_WAIT_KIND = "unknown_surface_not_provably_disjoint"
ARCHITECT_UNUSABLE_WAIT_KIND = "architect_unusable"
VALID_WAIT_KINDS = (
    CONFLICT_WAIT_KINDS
    | {UNKNOWN_SURFACE_WAIT_KIND, ARCHITECT_UNUSABLE_WAIT_KIND}
)

VALID_ESCALATION_CATEGORIES = frozenset(
    manifest_module.VALID_ESCALATION_CATEGORIES - {"none"}
)

ARCHITECT_INVOCATION_FAILED = "invocation_failed"

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,63}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")

LOCK_IDENTITY_KIND = "scheduler_singleton_lock"

STEP_ALIGNMENT_CHECK = "poll_step_alignment"

MANDATORY_GROUNDING_CHECKS = tuple(
    sorted(set(MANDATORY_LIVE_GROUNDING_CHECKS) - {STEP_ALIGNMENT_CHECK})
)
"""Checks this verifier always applies, in addition to the manifest's own.

They are not manifest-selectable, because a scenario must not be able to opt out
of being grounded in the source repository and in its own declared facts. Step
alignment is added on top for every step-based scenario; an operation scenario
such as J has no steps to align.
"""


class LiveEvidenceError(RuntimeError):
    """Raised when the evidence envelope itself cannot be trusted."""


@dataclass(frozen=True)
class EvidenceCheck:
    name: str
    status: str
    required: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "detail": self.detail,
        }


@dataclass
class EvidenceReport:
    events_path: str
    scenario_id: str
    run_id: str
    event_count: int
    checks: list[EvidenceCheck] = field(default_factory=list)
    diagnostics: list[EvidenceCheck] = field(default_factory=list)

    @property
    def required_checks(self) -> list[EvidenceCheck]:
        return [check for check in self.checks if check.required]

    @property
    def unsatisfied_required(self) -> list[EvidenceCheck]:
        return [
            check for check in self.required_checks if check.status != STATUS_PROVEN
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_path": self.events_path,
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "event_count": self.event_count,
            "checks": [check.to_dict() for check in self.checks],
            "diagnostics": [check.to_dict() for check in self.diagnostics],
        }


# ---------------------------------------------------------------------------
# Envelope parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Poll:
    """One complete, correlated poll execution."""

    poll_id: str
    poll_index: int
    outcome: str
    scheduler_id: str
    first_event_index: int
    last_event_index: int
    events: tuple[Mapping[str, Any], ...]

    def of_type(self, name: str) -> list[Mapping[str, Any]]:
        return [event for event in self.events if event["event"] == name]


@dataclass(frozen=True)
class Envelope:
    metadata: Mapping[str, Any]
    events: tuple[Mapping[str, Any], ...]
    polls: tuple[Poll, ...]
    manifest: Mapping[str, Any]
    scenario: Mapping[str, Any]
    scenario_task_ids: frozenset[str]

    @property
    def steps(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.scenario.get("steps") or ())

    @property
    def is_operation(self) -> bool:
        return "operation" in self.scenario


@dataclass(frozen=True)
class SourceGrounding:
    """What the actual `--source` checkout reports right now."""

    root: Path
    head: str
    tree: str
    repository_identity: str


def _fail(message: str) -> None:
    raise LiveEvidenceError(message)


def _closed_event(
    event: Mapping[str, Any],
    *,
    where: str,
    required: Iterable[str],
    optional: Iterable[str],
) -> None:
    required_keys = set(required)
    allowed = required_keys | set(optional)
    missing = sorted(required_keys - set(event))
    if missing:
        _fail(f"{where}: missing required fields {missing}")
    unknown = sorted(set(event) - allowed)
    if unknown:
        _fail(f"{where}: unknown fields {unknown}; allowed {sorted(allowed)}")


def _text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{where}: expected non-empty text, got {value!r}")
    return value.strip()


def _identifier(value: Any, *, where: str) -> str:
    text = _text(value, where=where)
    if not IDENTIFIER_RE.fullmatch(text):
        _fail(
            f"{where}: {text!r} is not a well-formed identifier "
            "([A-Za-z0-9][A-Za-z0-9._:-]{2,63})"
        )
    return text


def _timestamp(value: Any, *, where: str) -> str:
    text = _text(value, where=where)
    if not TIMESTAMP_RE.fullmatch(text):
        _fail(
            f"{where}: {text!r} is not an ISO-8601 UTC timestamp such as "
            "2026-09-01T00:00:00Z"
        )
    try:
        datetime.strptime(text.split(".")[0], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        _fail(f"{where}: {text!r} is not a real instant: {exc}")
    return text


def _sha40(value: Any, *, where: str) -> str:
    text = _text(value, where=where)
    if len(text) != 40 or any(c not in "0123456789abcdef" for c in text.lower()):
        _fail(f"{where}: expected a 40-character hex SHA, got {text!r}")
    return text


def _string_list(value: Any, *, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _fail(f"{where}: expected a list of strings, got {value!r}")
    return tuple(value)


def load_envelope(
    path: Path | str, *, manifest_path: Path | str = MANIFEST_PATH
) -> Envelope:
    """Parse and bind one evidence envelope, failing closed on anything unbound."""

    manifest_data = manifest_module.load_manifest(manifest_path)
    expected_manifest_sha = manifest_module.manifest_sha256(manifest_path)

    raw: list[tuple[int, dict[str, Any]]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                _fail(f"{path}:{number} is not valid JSON: {exc}")
            if not isinstance(payload, dict) or "event" not in payload:
                _fail(f"{path}:{number} is not a scheduler event object")
            raw.append((number, payload))

    if not raw:
        _fail(f"{path} contains no records")
    _, metadata = raw[0]
    if metadata.get("event") != METADATA_EVENT:
        _fail(
            f"{path}:1 must be a {METADATA_EVENT} record. An evidence file without "
            "run metadata is unbound and can never be acceptance evidence."
        )
    _closed_event(metadata, where=f"{path}:1", required=METADATA_FIELDS, optional=())

    if metadata["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        _fail(
            f"{path}:1 schema_version must be {EVIDENCE_SCHEMA_VERSION}, got "
            f"{metadata['schema_version']!r}"
        )
    run_id = _identifier(metadata["run_id"], where=f"{path}:1.run_id")
    scenario_id = _text(metadata["scenario_id"], where=f"{path}:1.scenario_id")
    _identifier(metadata["scheduler_id"], where=f"{path}:1.scheduler_id")
    _timestamp(metadata["run_started_at"], where=f"{path}:1.run_started_at")
    _sha40(metadata["source_head"], where=f"{path}:1.source_head")
    _sha40(metadata["source_tree"], where=f"{path}:1.source_tree")

    repository = _text(metadata["repository"], where=f"{path}:1.repository")
    try:
        normalize_repository_identity(repository, where=f"{path}:1.repository")
    except AcceptanceSafetyError as exc:
        _fail(str(exc))
    if looks_like_production_repository(repository):
        _fail(
            f"{path}:1 claims a live proof ran against production-looking "
            f"repository {repository!r}"
        )

    if metadata["manifest_sha256"] != expected_manifest_sha:
        _fail(
            f"{path}:1 manifest_sha256 {metadata['manifest_sha256']!r} does not "
            f"match {manifest_path} ({expected_manifest_sha}). The evidence was "
            "recorded against different expectations."
        )

    try:
        scenario = manifest_module.scenario_by_id(manifest_data, scenario_id)
    except Exception as exc:  # AcceptanceManifestError
        _fail(
            f"{path}:1 names scenario {scenario_id!r}, which is not in the active "
            f"manifest: {exc}"
        )
    task_ids = frozenset(manifest_module.scenario_task_ids(scenario))

    events: list[Mapping[str, Any]] = []
    for index, (number, payload) in enumerate(raw[1:], start=1):
        where = f"{path}:{number}"
        name = payload.get("event")
        if name == METADATA_EVENT:
            _fail(f"{where}: an envelope carries exactly one {METADATA_EVENT} record")
        if name not in EVENT_SCHEMAS:
            _fail(
                f"{where}: unknown event type {name!r}; allowed "
                f"{sorted(EVENT_SCHEMAS)}"
            )
        extra_required, extra_optional = EVENT_SCHEMAS[name]
        _closed_event(
            payload,
            where=where,
            required=COMMON_EVENT_FIELDS | extra_required,
            optional=extra_optional,
        )
        if payload["run_id"] != run_id:
            _fail(f"{where}: run_id {payload['run_id']!r} does not match the envelope")
        if payload["scenario_id"] != scenario_id:
            _fail(
                f"{where}: scenario_id {payload['scenario_id']!r} does not match the "
                "envelope"
            )
        if payload["sequence"] != index:
            _fail(
                f"{where}: sequence must be contiguous from 1; expected {index}, got "
                f"{payload['sequence']!r}"
            )
        _identifier(payload["poll_id"], where=f"{where}.poll_id")
        _identifier(payload["scheduler_id"], where=f"{where}.scheduler_id")
        _validate_event_payload(payload, where=where, task_ids=task_ids)
        events.append(payload)

    if not events:
        _fail(f"{path} contains run metadata but no scheduler events")
    polls = _parse_polls(events, path=str(path))
    return Envelope(
        metadata=metadata,
        events=tuple(events),
        polls=polls,
        manifest=manifest_data,
        scenario=scenario,
        scenario_task_ids=task_ids,
    )


def _parse_polls(
    events: Sequence[Mapping[str, Any]], *, path: str
) -> tuple[Poll, ...]:
    """Group the event stream into complete, non-interleaved poll executions.

    A poll is complete only when its own `poll_started` opened it, every event
    in between carries the same `poll_id`, and its own `poll_finished` closed
    it. Ordering alone is never treated as completeness, because a run may
    contain several polls and a truncated one must not borrow another's
    terminal record.
    """

    polls: list[Poll] = []
    seen_ids: set[str] = set()
    seen_indexes: set[int] = set()
    open_poll: dict[str, Any] | None = None
    for index, event in enumerate(events):
        name = event["event"]
        poll_id = str(event["poll_id"])
        if name == EVENT_POLL_STARTED:
            if open_poll is not None:
                _fail(
                    f"{path}: poll {poll_id!r} started while poll "
                    f"{open_poll['poll_id']!r} was still open"
                )
            if poll_id in seen_ids:
                _fail(f"{path}: poll_id {poll_id!r} is reused by a second poll")
            if event["poll_index"] in seen_indexes:
                _fail(
                    f"{path}: poll_index {event['poll_index']!r} is reused by a "
                    "second poll"
                )
            open_poll = {
                "poll_id": poll_id,
                "poll_index": event["poll_index"],
                "first": index,
                "events": [event],
                "scheduler_id": str(event["scheduler_id"]),
            }
            seen_ids.add(poll_id)
            seen_indexes.add(event["poll_index"])
            continue
        if open_poll is None:
            _fail(
                f"{path}: {name} at sequence {event['sequence']} is outside any poll. "
                "Every event must belong to a poll that started and finished."
            )
        if poll_id != open_poll["poll_id"]:
            _fail(
                f"{path}: {name} at sequence {event['sequence']} carries poll_id "
                f"{poll_id!r} inside open poll {open_poll['poll_id']!r}"
            )
        open_poll["events"].append(event)
        if name == EVENT_POLL_FINISHED:
            if event["poll_index"] != open_poll["poll_index"]:
                _fail(
                    f"{path}: poll {poll_id!r} finished with poll_index "
                    f"{event['poll_index']!r} but started with "
                    f"{open_poll['poll_index']!r}"
                )
            outcome = _text(event["outcome"], where=f"{path}: poll {poll_id} outcome")
            if outcome not in manifest_module.OUTCOMES:
                _fail(
                    f"{path}: poll {poll_id!r} finished with unknown outcome "
                    f"{outcome!r}; allowed {sorted(manifest_module.OUTCOMES)}"
                )
            polls.append(
                Poll(
                    poll_id=poll_id,
                    poll_index=int(open_poll["poll_index"]),
                    outcome=outcome,
                    scheduler_id=open_poll["scheduler_id"],
                    first_event_index=int(open_poll["first"]),
                    last_event_index=index,
                    events=tuple(open_poll["events"]),
                )
            )
            open_poll = None
    if open_poll is not None:
        _fail(
            f"{path}: poll {open_poll['poll_id']!r} never recorded a terminal "
            f"{EVENT_POLL_FINISHED}. An unfinished poll proves nothing."
        )
    if not polls:
        _fail(f"{path}: the run recorded no complete poll execution")
    return tuple(polls)


def _require_scenario_task(value: Any, task_ids: frozenset[str], *, where: str) -> str:
    task_id = _text(value, where=where)
    if task_id not in task_ids:
        _fail(
            f"{where}: task {task_id!r} is not part of this scenario. Declared tasks "
            f"are {sorted(task_ids)}."
        )
    return task_id


def _validate_event_payload(
    payload: Mapping[str, Any], *, where: str, task_ids: frozenset[str]
) -> None:
    name = payload["event"]
    if name in (EVENT_POLL_STARTED, EVENT_POLL_FINISHED):
        if not isinstance(payload["poll_index"], int) or payload["poll_index"] < 0:
            _fail(f"{where}: poll_index must be a non-negative integer")
        return

    if name == EVENT_RESERVATIONS:
        reservations = payload["reservations"]
        if not isinstance(reservations, list):
            _fail(f"{where}: reservations must be a list")
        required, optional = RESERVATION_FIELDS
        for entry in reservations:
            if not isinstance(entry, dict):
                _fail(f"{where}: each reservation must be an object")
            _closed_event(
                entry, where=f"{where}.reservations[]", required=required, optional=optional
            )
            _require_scenario_task(
                entry["task_id"], task_ids, where=f"{where}.reservations[].task_id"
            )
            _string_list(entry["actual_paths"], where=f"{where}.reservations[].actual_paths")
            for optional_key in ("predicted_paths", "exclusive_resources"):
                if optional_key in entry:
                    _string_list(
                        entry[optional_key],
                        where=f"{where}.reservations[].{optional_key}",
                    )
            if not isinstance(entry["surface_unknown"], bool):
                _fail(f"{where}.reservations[].surface_unknown must be true or false")
        return

    if name == EVENT_WORKER_LAUNCHED:
        _require_scenario_task(payload["task_id"], task_ids, where=f"{where}.task_id")
        _text(payload["worker_id"], where=f"{where}.worker_id")
        argv = _string_list(payload["argv"], where=f"{where}.argv")
        if not argv:
            _fail(f"{where}: a launch must record its exact argv")
        return

    if name == EVENT_CANDIDATE_WAITED:
        _require_scenario_task(payload["task_id"], task_ids, where=f"{where}.task_id")
        kind = _text(payload["wait_kind"], where=f"{where}.wait_kind")
        if kind not in VALID_WAIT_KINDS:
            _fail(
                f"{where}: unknown wait_kind {kind!r}; allowed {sorted(VALID_WAIT_KINDS)}"
            )
        _text(payload["reservation_fingerprint"], where=f"{where}.reservation_fingerprint")
        if kind in CONFLICT_WAIT_KINDS:
            _require_scenario_task(
                payload.get("conflicting_task_id"),
                task_ids,
                where=f"{where}.conflicting_task_id",
            )
            values = _string_list(
                payload.get("overlapping_values", []),
                where=f"{where}.overlapping_values",
            )
            if not values:
                _fail(
                    f"{where}: a {kind} wait must name the exact overlapping paths or "
                    "resources. A prose reason is not structured evidence."
                )
        elif kind == UNKNOWN_SURFACE_WAIT_KIND:
            _require_scenario_task(
                payload.get("conflicting_task_id"),
                task_ids,
                where=f"{where}.conflicting_task_id",
            )
            verdict = _text(
                payload.get("disjointness_verdict"), where=f"{where}.disjointness_verdict"
            )
            if verdict != sw.DISJOINT_NOT_PROVABLE:
                _fail(
                    f"{where}: an unknown-surface wait must record verdict "
                    f"{sw.DISJOINT_NOT_PROVABLE!r}, got {verdict!r}"
                )
        else:  # architect_unusable
            defects = _string_list(
                payload.get("advisory_defects", []), where=f"{where}.advisory_defects"
            )
            if not defects:
                _fail(
                    f"{where}: an architect_unusable wait must name the structural "
                    "defects that made the advisory unusable"
                )
            unknown = sorted(set(defects) - manifest_module.VALID_ADVISORY_DEFECTS
                             - {ARCHITECT_INVOCATION_FAILED})
            if unknown:
                _fail(f"{where}: unknown advisory defects {unknown}")
        return

    if name == EVENT_HUMAN_REVIEW:
        _require_scenario_task(payload["task_id"], task_ids, where=f"{where}.task_id")
        _text(payload["escalation_category"], where=f"{where}.escalation_category")
        _text(payload["escalation_question"], where=f"{where}.escalation_question")
        return

    if name in (EVENT_LOCK_ACQUIRED, EVENT_LOCK_REJECTED):
        _text(payload["lock_identity"], where=f"{where}.lock_identity")
        _text(payload["lock_path"], where=f"{where}.lock_path")
        _text(payload["checkout_root"], where=f"{where}.checkout_root")
        _identifier(payload["contest_id"], where=f"{where}.contest_id")
        if name == EVENT_LOCK_REJECTED:
            _identifier(
                payload["holder_scheduler_id"], where=f"{where}.holder_scheduler_id"
            )
        return


# ---------------------------------------------------------------------------
# Source grounding
# ---------------------------------------------------------------------------

def observe_source(source: Path | str) -> SourceGrounding:
    """Read what the actual checkout reports. Raises when it cannot be read."""

    root = Path(source)
    if not root.is_dir():
        raise LiveEvidenceError(f"--source {root} is not a directory")
    toplevel = run_git(root, "rev-parse", "--show-toplevel", check=False)
    if toplevel.returncode != 0 or not toplevel.stdout.strip():
        raise LiveEvidenceError(f"--source {root} is not a Git checkout")
    repository_root = Path(os.path.realpath(toplevel.stdout.strip()))
    head = run_git(repository_root, "rev-parse", "HEAD", check=False)
    tree = run_git(repository_root, "rev-parse", "HEAD^{tree}", check=False)
    if head.returncode != 0 or tree.returncode != 0:
        raise LiveEvidenceError(
            f"--source {repository_root} has no readable HEAD commit or tree"
        )
    try:
        identity = read_repository_identity(repository_root)
    except AcceptanceSafetyError as exc:
        raise LiveEvidenceError(str(exc)) from exc
    return SourceGrounding(
        root=repository_root,
        head=head.stdout.strip(),
        tree=tree.stdout.strip(),
        repository_identity=identity,
    )


def _check_source_identity_grounded(
    envelope: Envelope, grounding: SourceGrounding | None
) -> tuple[str, str]:
    if grounding is None:
        return (
            STATUS_UNPROVEN,
            "no --source checkout was supplied, so the recorded HEAD, tree and "
            "repository identity are anchored to nothing. Re-run with --source "
            "pointing at the checkout the scheduler actually used.",
        )
    metadata = envelope.metadata
    problems: list[str] = []
    if metadata["source_head"] != grounding.head:
        problems.append(
            f"source_head {metadata['source_head'][:12]} != actual "
            f"{grounding.head[:12]}"
        )
    if metadata["source_tree"] != grounding.tree:
        problems.append(
            f"source_tree {metadata['source_tree'][:12]} != actual "
            f"{grounding.tree[:12]}"
        )
    recorded = normalize_repository_identity(metadata["repository"])
    if recorded != grounding.repository_identity:
        problems.append(
            f"repository {recorded!r} != actual {grounding.repository_identity!r}"
        )
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems)
        or (
            f"metadata matches {grounding.root}: HEAD {grounding.head[:12]}, tree "
            f"{grounding.tree[:12]}, repository {grounding.repository_identity}"
        ),
    )


# ---------------------------------------------------------------------------
# Lifecycle and identity
# ---------------------------------------------------------------------------

def _check_run_poll_lifecycle(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    """One complete poll per required step; more or fewer is not the run claimed."""

    observed = len(envelope.polls)
    described = [
        f"{poll.poll_id}#{poll.poll_index}={poll.outcome}" for poll in envelope.polls
    ]
    if envelope.is_operation:
        return (
            STATUS_PROVEN if observed >= 1 else STATUS_FAILED,
            f"{observed} complete poll execution(s): {described}",
        )
    required = len(envelope.steps)
    if observed != required:
        return (
            STATUS_FAILED,
            f"this scenario requires {required} complete poll execution(s); the "
            f"envelope contains {observed}: {described}",
        )
    return STATUS_PROVEN, f"{observed} complete poll execution(s): {described}"


def _check_scheduler_identity_consistent(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    """Every event belongs to the scheduler that recorded the run.

    The one deliberate exception is a rejected competitor: it is by definition a
    different scheduler, and it must name this run's scheduler as the holder.
    """

    scheduler_id = str(envelope.metadata["scheduler_id"])
    problems: list[str] = []
    for event in envelope.events:
        observed = str(event.get("scheduler_id", ""))
        if event["event"] == EVENT_LOCK_REJECTED:
            if observed == scheduler_id:
                problems.append(
                    f"sequence {event['sequence']}: the rejected scheduler is this run"
                )
            if str(event["holder_scheduler_id"]) != scheduler_id:
                problems.append(
                    f"sequence {event['sequence']}: names holder "
                    f"{event['holder_scheduler_id']!r}, not {scheduler_id!r}"
                )
            continue
        if observed != scheduler_id:
            problems.append(
                f"sequence {event['sequence']} ({event['event']}): scheduler "
                f"{observed!r} != run scheduler {scheduler_id!r}"
            )
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems) or f"every event was emitted by {scheduler_id!r}",
    )


def _check_poll_step_alignment(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    """Bind poll k to manifest step k, decision event included."""

    steps = envelope.steps
    if not steps:
        return STATUS_UNPROVEN, "this scenario declares no steps to align"
    if len(envelope.polls) != len(steps):
        return (
            STATUS_FAILED,
            f"{len(steps)} step(s) require {len(steps)} poll(s); observed "
            f"{len(envelope.polls)}",
        )
    problems: list[str] = []
    for step, poll in zip(steps, envelope.polls):
        index = int(step["step"])
        expected = step["expected"]
        launches = poll.of_type(EVENT_WORKER_LAUNCHED)
        waits = poll.of_type(EVENT_CANDIDATE_WAITED)
        escalations = poll.of_type(EVENT_HUMAN_REVIEW)
        if poll.outcome != expected["outcome"]:
            problems.append(
                f"step{index}: poll {poll.poll_id} finished {poll.outcome!r}, "
                f"expected {expected['outcome']!r}"
            )
        if expected["outcome"] == "start":
            task_id = str(expected.get("task_id", ""))
            matching = [
                event for event in launches if str(event["task_id"]) == task_id
            ]
            if len(launches) != 1 or len(matching) != 1:
                problems.append(
                    f"step{index}: expected exactly one launch of {task_id} in poll "
                    f"{poll.poll_id}; observed "
                    f"{[str(event['task_id']) for event in launches]}"
                )
        elif launches:
            problems.append(
                f"step{index}: a {expected['outcome']} poll launched "
                f"{[str(event['task_id']) for event in launches]}"
            )
        for task_id in expected.get("waited_task_ids", ()) or ():
            if not [
                event for event in waits if str(event["task_id"]) == str(task_id)
            ]:
                problems.append(
                    f"step{index}: no candidate_waited for {task_id} in poll "
                    f"{poll.poll_id}"
                )
        for conflict in expected.get("conflicts", ()) or ():
            declared = set(normalize_tokens(conflict["on"]))
            matching = [
                event
                for event in waits
                if str(event["task_id"]) == str(conflict["candidate_task_id"])
                and str(event.get("conflicting_task_id"))
                == str(conflict["conflicting_task_id"])
                and str(event["wait_kind"]) == str(conflict["kind"])
            ]
            observed_values = {
                str(value)
                for event in matching
                for value in (event.get("overlapping_values") or ())
            }
            if not matching or not declared <= observed_values:
                problems.append(
                    f"step{index}: no {conflict['kind']} wait for "
                    f"{conflict['candidate_task_id']}->"
                    f"{conflict['conflicting_task_id']} naming "
                    f"{sorted(declared)}; observed {sorted(observed_values)}"
                )
        if expected["outcome"] == "human_review" and len(escalations) != 1:
            problems.append(
                f"step{index}: expected exactly one escalation event; observed "
                f"{len(escalations)}"
            )
        if expected.get("no_human_escalation") and escalations:
            problems.append(
                f"step{index}: escalated "
                f"{[str(event['escalation_category']) for event in escalations]} "
                "where the scenario forbids it"
            )
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems)
        or f"{len(steps)} step(s) each proven by their own complete poll",
    )


# ---------------------------------------------------------------------------
# Conflict grounding
# ---------------------------------------------------------------------------

def _candidate_surface(envelope: Envelope, task_id: str) -> tuple[str, ...]:
    """The paths this candidate is contractually entitled to be waiting over.

    Contract facts first: the task's declared intended change surface, plus the
    advisory surface this scenario injected for it. Nothing else counts, so an
    overlap token that appears in neither is not grounded.
    """

    task = (envelope.manifest.get("tasks") or {}).get(task_id) or {}
    declared = list(
        (task.get("intended_change_surface") or {}).get("exact_paths", ())
    )
    advisories = (envelope.scenario.get("world") or {}).get("advisories") or {}
    advisory = advisories.get(task_id) or {}
    declared.extend(
        (advisory.get("predicted_change_surface") or {}).get("exact_paths", ())
    )
    return tuple(sorted(set(declared)))


def _declared_resources(envelope: Envelope, task_id: str) -> tuple[str, ...]:
    task = (envelope.manifest.get("tasks") or {}).get(task_id) or {}
    return normalize_tokens(task.get("exclusive_resources", ()))


def _reservation_state(
    envelope: Envelope, index: int
) -> tuple[Mapping[str, Any] | None, str | None]:
    """The reservation observation in force at ``index``, and its fingerprint."""

    for event in reversed(envelope.events[: index + 1]):
        if event["event"] == EVENT_RESERVATIONS:
            return event, canonical_sha256(event["reservations"])
    return None, None


def _observed_reservation(
    snapshot: Mapping[str, Any], task_id: str
) -> Mapping[str, Any] | None:
    for entry in snapshot["reservations"]:
        if str(entry["task_id"]) == task_id:
            return entry
    return None


def _overlaps(value: str, surface: Iterable[str]) -> bool:
    """Unity-asset-identity-aware membership, reusing the fixture's own rule."""

    return bool(sw.surface_overlap((value,), surface))


def _check_conflict_evidence_grounded(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    """Every wait token must be grounded in contract facts AND observed state.

    A structurally valid `candidate_waited` record is not evidence on its own.
    The audit produced a scenario-D wait with an invented overlap token, no
    reservation observation behind it, and a fingerprint bound to nothing, and
    it passed. Each wait now has to survive three questions: what state was
    observed when it was made, does that state actually contain the conflicting
    work, and is the named token real on both sides.
    """

    waits = [
        (index, event)
        for index, event in enumerate(envelope.events)
        if event["event"] == EVENT_CANDIDATE_WAITED
    ]
    if not waits:
        return (
            STATUS_PROVEN,
            "the run recorded no candidate_waited events to ground",
        )
    problems: list[str] = []
    for index, event in waits:
        task_id = str(event["task_id"])
        kind = str(event["wait_kind"])
        label = f"{task_id}/{kind}"
        snapshot, fingerprint = _reservation_state(envelope, index)
        if kind != ARCHITECT_UNUSABLE_WAIT_KIND:
            if snapshot is None:
                problems.append(
                    f"{label}: no {EVENT_RESERVATIONS} observation precedes this "
                    "wait, so the state it claims to have seen was never recorded"
                )
                continue
            if str(event["reservation_fingerprint"]) != fingerprint:
                problems.append(
                    f"{label}: reservation_fingerprint "
                    f"{str(event['reservation_fingerprint'])[:12]} does not hash the "
                    f"observation that preceded it ({str(fingerprint)[:12]}); the "
                    "wait is not bound to the state that produced it"
                )
                continue
        problems.extend(
            _ground_one_wait(envelope, event, snapshot, task_id, kind, label)
        )
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems)
        or f"{len(waits)} wait(s) grounded in scenario facts and observed state",
    )


def _ground_one_wait(
    envelope: Envelope,
    event: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    task_id: str,
    kind: str,
    label: str,
) -> list[str]:
    problems: list[str] = []
    if kind == ARCHITECT_UNUSABLE_WAIT_KIND:
        return _ground_architect_wait(envelope, event, task_id, label)

    other = str(event.get("conflicting_task_id", ""))
    assert snapshot is not None  # the caller returns early when it is missing
    reservation = _observed_reservation(snapshot, other)
    if reservation is None:
        return [
            f"{label}: the observed reservation set contains no entry for {other}, "
            "so nothing in the run's own state supports this wait"
        ]
    actual = tuple(reservation.get("actual_paths", ()))
    predicted = tuple(reservation.get("predicted_paths", ()))
    resources = normalize_tokens(reservation.get("exclusive_resources", ()))

    if kind == UNKNOWN_SURFACE_WAIT_KIND:
        if not reservation.get("surface_unknown"):
            problems.append(
                f"{label}: {other} was observed with a readable surface "
                f"{list(actual)}, so 'not provably disjoint' is not what the run saw"
            )
        return problems

    candidate_surface = _candidate_surface(envelope, task_id)
    for value in event.get("overlapping_values", ()) or ():
        token = str(value)
        if kind == "exclusive_resource":
            if token not in _declared_resources(envelope, task_id):
                problems.append(f"{label}: {token!r} is not declared by {task_id}")
            if token not in _declared_resources(envelope, other):
                problems.append(f"{label}: {token!r} is not declared by {other}")
            if token not in resources:
                problems.append(
                    f"{label}: the observed reservation for {other} does not hold "
                    f"{token!r}; observed {list(resources)}"
                )
            continue
        if not _overlaps(token, candidate_surface):
            problems.append(
                f"{label}: {token!r} is outside {task_id}'s declared and predicted "
                f"surface {list(candidate_surface)}"
            )
        if kind == "exact_path_actual":
            observed_surface: tuple[str, ...] = actual
        elif kind == "exact_path_predicted":
            observed_surface = predicted
        else:  # unity_asset_identity and active_task_id
            observed_surface = (*actual, *predicted)
        if not _overlaps(token, observed_surface):
            problems.append(
                f"{label}: {token!r} is not in the observed {kind} surface of "
                f"{other} ({list(observed_surface)})"
            )
    return problems


def _ground_architect_wait(
    envelope: Envelope, event: Mapping[str, Any], task_id: str, label: str
) -> list[str]:
    """An unusable-advisory wait must match a defect this scenario really injected."""

    defects = set(str(item) for item in event.get("advisory_defects", ()) or ())
    world = envelope.scenario.get("world") or {}
    declared = set(
        (world.get("malformed_advisories") or {}).get(task_id, {}).get("defects", ())
    )
    unavailable = any(
        str((step.get("transition") or {}).get("kind", "")) == "architect_unavailable"
        for step in envelope.steps
    )
    if defects == {ARCHITECT_INVOCATION_FAILED}:
        if not unavailable:
            return [
                f"{label}: claims the architect invocation failed, but this scenario "
                "never makes the architect unavailable"
            ]
        return []
    unsupported = sorted(defects - declared)
    if unsupported:
        return [
            f"{label}: defects {unsupported} are not the ones this scenario injects "
            f"for {task_id} ({sorted(declared)})"
        ]
    return []


# ---------------------------------------------------------------------------
# Manifest-declared checks
# ---------------------------------------------------------------------------

def _by_event(events: Sequence[Mapping[str, Any]], name: str) -> list[Mapping[str, Any]]:
    return [event for event in events if event["event"] == name]


def _check_exact_task_id_launch(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    launches = _by_event(envelope.events, EVENT_WORKER_LAUNCHED)
    if not launches:
        return STATUS_UNPROVEN, "the run recorded no worker_launched events"
    # Envelope parsing already rejected an out-of-scenario task ID or an empty
    # worker ID, so reaching here means every launch is exactly identified.
    identified = [
        f"{event['task_id']}/{event['worker_id']}" for event in launches
    ]
    return STATUS_PROVEN, f"launches: {identified}"


def _check_unique_worker_ids(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    launches = _by_event(envelope.events, EVENT_WORKER_LAUNCHED)
    if not launches:
        return STATUS_UNPROVEN, "the run recorded no worker_launched events"
    task_ids = [event["task_id"] for event in launches]
    worker_ids = [event["worker_id"] for event in launches]
    unique = len(task_ids) == len(set(task_ids)) and len(worker_ids) == len(
        set(worker_ids)
    )
    return (
        STATUS_PROVEN if unique else STATUS_FAILED,
        f"tasks={task_ids} workers={worker_ids}",
    )


def _check_launch_argv_binding(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    launches = _by_event(envelope.events, EVENT_WORKER_LAUNCHED)
    if not launches:
        return STATUS_UNPROVEN, "the run recorded no worker_launched events"
    problems: list[str] = []
    for event in launches:
        argv = list(event["argv"])
        if not _argv_binds(argv, "--task-id", event["task_id"]):
            problems.append(f"{event['task_id']}: argv does not carry the exact task ID")
        if not _argv_binds(argv, "--worker-id", event["worker_id"]):
            problems.append(f"{event['task_id']}: argv does not carry the exact worker ID")
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems) or "every launch argv names its exact task and worker",
    )


def _argv_binds(argv: Sequence[str], flag: str, value: str) -> bool:
    for index, item in enumerate(argv[:-1]):
        if item == flag and argv[index + 1] == value:
            return True
    return False


def _check_structured_wait_evidence(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    waits = _by_event(envelope.events, EVENT_CANDIDATE_WAITED)
    if not waits:
        return STATUS_UNPROVEN, "the run recorded no candidate_waited events"
    # Structural requirements per wait_kind were enforced during parsing and the
    # tokens themselves are grounded by conflict_evidence_grounded, so a wait
    # that reaches here carries identities and real tokens rather than prose.
    described = [
        f"{event['task_id']}:{event['wait_kind']}"
        + (
            f"->{event['conflicting_task_id']}{list(event.get('overlapping_values', []))}"
            if event.get("conflicting_task_id")
            else ""
        )
        for event in waits
    ]
    return STATUS_PROVEN, f"{len(waits)} structured waits: {described}"


def _check_human_review_is_narrow(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    escalations = _by_event(envelope.events, EVENT_HUMAN_REVIEW)
    if not escalations:
        return (
            STATUS_PROVEN,
            "no human escalation was raised, and the envelope is a complete "
            "contiguous record of this run",
        )
    bad = [
        f"{event['task_id']}: category={event['escalation_category']!r}"
        for event in escalations
        if event["escalation_category"] not in VALID_ESCALATION_CATEGORIES
    ]
    return (
        STATUS_PROVEN if not bad else STATUS_FAILED,
        "; ".join(bad)
        or "every escalation named a design/canon category and a specific question",
    )


def _check_no_launch_recorded(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    launches = _by_event(envelope.events, EVENT_WORKER_LAUNCHED)
    if launches:
        return (
            STATUS_FAILED,
            f"this scenario requires no launch, but {[e['task_id'] for e in launches]} "
            "were launched",
        )
    return STATUS_PROVEN, "no worker was launched in this run"


def _check_wait_then_start(
    envelope: Envelope, _grounding: SourceGrounding | None
) -> tuple[str, str]:
    """Bind a WAIT and a later START for the same task to observed state change."""

    declared = list(
        (envelope.scenario.get("live_evidence") or {}).get(
            "wait_then_start_task_ids", ()
        )
    )
    if not declared:
        return STATUS_UNPROVEN, "the scenario named no wait-then-start task"
    details: list[str] = []
    for task_id in declared:
        wait_index = next(
            (
                index
                for index, event in enumerate(envelope.events)
                if event["event"] == EVENT_CANDIDATE_WAITED
                and event["task_id"] == task_id
            ),
            None,
        )
        launch_index = next(
            (
                index
                for index, event in enumerate(envelope.events)
                if event["event"] == EVENT_WORKER_LAUNCHED
                and event["task_id"] == task_id
            ),
            None,
        )
        if wait_index is None:
            return STATUS_UNPROVEN, f"{task_id}: no candidate_waited event was recorded"
        if launch_index is None:
            return STATUS_FAILED, f"{task_id}: waited but never started"
        if launch_index < wait_index:
            return STATUS_FAILED, f"{task_id}: the launch precedes the wait"
        wait_poll = _poll_of(envelope, wait_index)
        launch_poll = _poll_of(envelope, launch_index)
        if wait_poll is None or launch_poll is None or wait_poll is launch_poll:
            return (
                STATUS_FAILED,
                f"{task_id}: the wait and the start must be two separate correlated "
                "polls, not one",
            )
        _, before = _reservation_state(envelope, wait_index)
        _, after = _reservation_state(envelope, launch_index)
        if before is None or after is None:
            return (
                STATUS_UNPROVEN,
                f"{task_id}: no {EVENT_RESERVATIONS} record brackets the transition, "
                "so the state change cannot be shown",
            )
        declared_fingerprint = envelope.events[wait_index]["reservation_fingerprint"]
        if declared_fingerprint != before:
            return (
                STATUS_FAILED,
                f"{task_id}: the wait recorded fingerprint "
                f"{declared_fingerprint[:12]} but the reservation snapshot that "
                f"preceded it hashes to {before[:12]}; the WAIT is not bound to the "
                "state that produced it",
            )
        if before == after:
            return (
                STATUS_FAILED,
                f"{task_id}: started with no observable change in the reserved "
                "surface, which contradicts the WAIT rule",
            )
        details.append(
            f"{task_id}: poll {wait_poll.poll_id} {before[:12]} -> poll "
            f"{launch_poll.poll_id} {after[:12]}"
        )
    return STATUS_PROVEN, "; ".join(details)


def _poll_of(envelope: Envelope, index: int) -> Poll | None:
    for poll in envelope.polls:
        if poll.first_event_index <= index <= poll.last_event_index:
            return poll
    return None


def _check_singleton_lock_ownership(
    envelope: Envelope, grounding: SourceGrounding | None
) -> tuple[str, str]:
    """Require one real, correlated, grounded contest for one real lock.

    Two lock strings are not a contest. The acquisition and the rejection must
    name the same lock identity, path and checkout root, carry one contest ID,
    sit in one run, and the identity itself must be recomputable from the actual
    `--source` repository and the checkout root the events name.
    """

    acquired = _by_event(envelope.events, EVENT_LOCK_ACQUIRED)
    rejected = _by_event(envelope.events, EVENT_LOCK_REJECTED)
    if not acquired:
        return STATUS_UNPROVEN, "no scheduler_lock_acquired event was recorded"
    if not rejected:
        return (
            STATUS_UNPROVEN,
            "no competing scheduler was rejected, so a singleton was never contested",
        )
    if len(acquired) != 1:
        return (
            STATUS_FAILED,
            f"{len(acquired)} schedulers acquired the lock: "
            f"{[e['scheduler_id'] for e in acquired]}",
        )
    holder = acquired[0]
    problems: list[str] = []
    contest_ids = {str(event["contest_id"]) for event in (*acquired, *rejected)}
    if len(contest_ids) != 1:
        problems.append(
            f"the acquisition and rejection are not one contest: {sorted(contest_ids)}"
        )
    for event in rejected:
        for key in ("lock_identity", "lock_path", "checkout_root"):
            if event[key] != holder[key]:
                problems.append(
                    f"{event['scheduler_id']}: rejected on a different {key} "
                    f"{event[key]!r}"
                )
        if event["holder_scheduler_id"] != holder["scheduler_id"]:
            problems.append(
                f"{event['scheduler_id']}: names holder "
                f"{event['holder_scheduler_id']!r}, not {holder['scheduler_id']!r}"
            )
        if event["scheduler_id"] == holder["scheduler_id"]:
            problems.append("the rejected scheduler is the holder")
        if event["sequence"] <= holder["sequence"]:
            problems.append(
                f"{event['scheduler_id']}: was rejected before the lock was acquired"
            )
    lock_path = Path(str(holder["lock_path"]))
    checkout_root = Path(str(holder["checkout_root"]))
    if checkout_root not in lock_path.parents:
        problems.append(
            f"the lock file {lock_path} is not inside the contested checkout root "
            f"{checkout_root}"
        )
    if grounding is None:
        problems.append(
            "no --source checkout was supplied, so the lock identity cannot be "
            "recomputed and the contest is ungrounded"
        )
    else:
        expected = expected_lock_identity(grounding, str(holder["checkout_root"]))
        if str(holder["lock_identity"]) != expected:
            problems.append(
                f"lock_identity {str(holder['lock_identity'])[:24]!r} is not the "
                f"identity of this repository and checkout root ({expected[:24]!r})"
            )
    losers = {event["scheduler_id"] for event in rejected}
    stolen = [
        event["task_id"]
        for event in _by_event(envelope.events, EVENT_WORKER_LAUNCHED)
        if event["scheduler_id"] in losers
    ]
    if stolen:
        problems.append(f"a rejected scheduler launched {stolen}")
    return (
        STATUS_PROVEN if not problems else STATUS_FAILED,
        "; ".join(problems)
        or (
            f"lock {holder['lock_identity'][:24]}... held by "
            f"{holder['scheduler_id']!r} over {holder['checkout_root']}; rejected "
            f"{sorted(losers)} launched nothing"
        ),
    )


def expected_lock_identity(grounding: SourceGrounding, checkout_root: str) -> str:
    """The only lock identity this repository and checkout root can produce."""

    return "sha256:" + canonical_sha256(
        {
            "kind": LOCK_IDENTITY_KIND,
            "repository_identity": grounding.repository_identity,
            "source_root": str(grounding.root),
            "checkout_root": str(Path(checkout_root)),
        }
    )


CheckImplementation = Callable[
    [Envelope, "SourceGrounding | None"], "tuple[str, str]"
]

CHECK_IMPLEMENTATIONS: dict[str, CheckImplementation] = {
    "exact_task_id_launch": _check_exact_task_id_launch,
    "unique_worker_ids": _check_unique_worker_ids,
    "launch_argv_binding": _check_launch_argv_binding,
    "structured_wait_evidence": _check_structured_wait_evidence,
    "human_review_is_narrow": _check_human_review_is_narrow,
    "wait_then_start_transition": _check_wait_then_start,
    "singleton_lock_ownership": _check_singleton_lock_ownership,
    "no_launch_recorded": _check_no_launch_recorded,
    "source_identity_grounded": _check_source_identity_grounded,
    "run_poll_lifecycle": _check_run_poll_lifecycle,
    "scheduler_identity_consistent": _check_scheduler_identity_consistent,
    "conflict_evidence_grounded": _check_conflict_evidence_grounded,
    STEP_ALIGNMENT_CHECK: _check_poll_step_alignment,
}


def check_local_repository_state(source: Path | str) -> list[EvidenceCheck]:
    """Diagnostic only: one local checkout's leftover refs and dirty state.

    Local refs say nothing about a frozen remote or a private repository's
    authority, so these never gate the exit code. Readability of the checkout
    itself is a different question and *is* gating; it belongs to
    ``source_identity_grounded``.
    """

    root = Path(source)
    if not (root / ".git").exists():
        return [
            EvidenceCheck(
                "local_repository_state",
                STATUS_UNPROVEN,
                False,
                f"{root} is not a Git checkout",
            )
        ]
    leftover = git_lines(
        root, "for-each-ref", "--format=%(refname)", "refs/nsc/claims/"
    )
    dirty = [
        line
        for line in run_git(
            root, "status", "--porcelain=v1", "--untracked-files=all", check=False
        ).stdout.splitlines()
        if line.strip()
    ]
    return [
        EvidenceCheck(
            "local_no_leaked_claim_refs",
            STATUS_PROVEN if not leftover else STATUS_FAILED,
            False,
            f"local claim refs remaining: {list(leftover)}"
            if leftover
            else "no local claim refs remain (local checkout only)",
        ),
        EvidenceCheck(
            "local_clean_working_tree",
            STATUS_PROVEN if not dirty else STATUS_FAILED,
            False,
            f"{len(dirty)} dirty entries" if dirty else "local working tree is clean",
        ),
    ]


def verify(
    *,
    events_path: Path | str,
    manifest_path: Path | str = MANIFEST_PATH,
    source: Path | str | None = None,
) -> tuple[EvidenceReport, int]:
    """Verify one envelope against its scenario's checks and the grounding checks."""

    envelope = load_envelope(events_path, manifest_path=manifest_path)
    live_evidence = envelope.scenario.get("live_evidence") or {}
    required = set(live_evidence.get("required_checks", ()))
    optional = set(live_evidence.get("optional_checks", ()))
    required.update(MANDATORY_GROUNDING_CHECKS)
    if not envelope.is_operation:
        required.add(STEP_ALIGNMENT_CHECK)
    report = EvidenceReport(
        events_path=str(events_path),
        scenario_id=str(envelope.scenario["id"]),
        run_id=str(envelope.metadata["run_id"]),
        event_count=len(envelope.events),
    )

    grounding: SourceGrounding | None = None
    grounding_error: str | None = None
    if source is not None:
        try:
            grounding = observe_source(source)
        except LiveEvidenceError as exc:
            grounding_error = str(exc)

    # Only checks the scenario declared, plus the grounding checks this verifier
    # always applies, are evaluated. A check that is neither is not applicable to
    # this scenario, and reporting it would invite reading an inapplicable result
    # as a finding.
    for name in sorted(required | optional):
        if name == "source_identity_grounded" and grounding_error is not None:
            report.checks.append(
                EvidenceCheck(name, STATUS_FAILED, True, grounding_error)
            )
            continue
        status, detail = CHECK_IMPLEMENTATIONS[name](envelope, grounding)
        report.checks.append(
            EvidenceCheck(name, status, name in required, detail)
        )
    if source is not None and grounding_error is None:
        report.diagnostics.extend(check_local_repository_state(source))
    return report, (1 if report.unsatisfied_required else 0)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a Software Architect live proof from a bound evidence "
            "envelope. The scenario and its required checks come from the "
            "envelope and the manifest, not from the command line."
        )
    )
    parser.add_argument("--events", required=True)
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument(
        "--source",
        default=None,
        help=(
            "The checkout the run executed against. Required for a passing "
            "verification: the recorded HEAD, tree and repository identity are "
            "compared against what Git reports there."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report, exit_code = verify(
            events_path=args.events, manifest_path=args.manifest, source=args.source
        )
    except LiveEvidenceError as exc:
        print("[BLOCKED] the evidence envelope is not verifiable")
        print(f"[ERROR] {exc}")
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"[STATE] scenario: {report.scenario_id}")
        print(f"[STATE] run_id:   {report.run_id}")
        for check in report.checks:
            marker = "REQUIRED" if check.required else "optional"
            print(f"[{check.status}] ({marker}) {check.name}: {check.detail}")
        for check in report.diagnostics:
            print(f"[{check.status}] (diagnostic) {check.name}: {check.detail}")
        print("")
        unsatisfied = report.unsatisfied_required
        print(
            f"[SUMMARY] events={report.event_count} "
            f"required={len(report.required_checks)} "
            f"unsatisfied_required={len(unsatisfied)}"
        )
        if unsatisfied:
            print(
                "[SUMMARY] A REQUIRED check that is UNPROVEN is not a pass. Missing: "
                + ", ".join(f"{c.name}={c.status}" for c in unsatisfied)
            )
    return exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
