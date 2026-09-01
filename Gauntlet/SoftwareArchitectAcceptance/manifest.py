"""Strict loader and validator for the acceptance scenario manifest.

The manifest is **test-expectation data only**. It is never a second source of
truth about the scheduler.

Validation is closed, not advisory. Every authority-bearing object declares its
exact allowed keys, and an unknown key is an error rather than something to
ignore. That matters more here than in ordinary configuration loading: a
silently ignored field is a scenario that looks stricter than it is, and this
gauntlet exists to be harder to fool than the system it tests.

Enforced here:

- exact allowed keys for the root, source identity, task, change surface,
  scenario, world, reservation, checkout, resume authority, advisory, malformed
  advisory, fixture-fact, step, transition, expected result, conflict,
  operation and live-evidence objects;
- closed vocabularies for readiness gates, capabilities, outcomes, reservation
  kinds, transition kinds, advisory defects, disjointness verdicts, conflict
  kinds and live-evidence check names;
- every referenced task exists, and every task exists to be referenced;
- expected task IDs belong to the scenario's own candidate, resume, or
  reservation sets;
- expected conflicts name a declared candidate and a declared reservation or
  candidate, and their overlap values are declared paths or declared exclusive
  resources;
- a scenario declares steps or an operation, never both and never neither.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import scenario_world as sw
import synthetic_repository as sr
from acceptance_lib import (
    AcceptanceManifestError,
    CAPABILITIES,
    HARNESS_ONLY_GATE,
    LIVE_EVIDENCE_CHECKS,
    MANIFEST_PATH,
    MANIFEST_SCHEMA_VERSION,
    OUTCOMES,
    READINESS_GATES,
    SYNTHETIC_TASK_ID_RE,
    file_sha256,
    load_json,
    normalize_tokens,
)

RESERVED_UNDECLARED_TASK_ID = "NSC-999"
"""Never a declared task. Evidence naming it is provably fabricated."""

VALID_RESERVATION_KINDS = frozenset(sw.RESERVATION_KINDS)
VALID_ADVISORY_DEFECTS = frozenset(sw.ADVISORY_DEFECTS)
VALID_DISJOINTNESS_VERDICTS = frozenset(
    {sw.DISJOINT_PROVABLE, sw.DISJOINT_NOT_PROVABLE, sw.DISJOINT_OVERLAPPING}
)

VALID_INTEGRATION_RISKS = frozenset({"none", "low", "medium", "high", "unknown"})
VALID_RECOMMENDATIONS = frozenset({"start", "wait", "human_review"})
VALID_ESCALATION_CATEGORIES = frozenset(
    {"none", "design_or_canon_ambiguity", "task_scope_or_contract_change"}
)

VALID_CONFLICT_KINDS = frozenset(
    {
        "exclusive_resource",
        "exact_path_actual",
        "exact_path_predicted",
        "unity_asset_identity",
        "active_task_id",
    }
)

TRANSITION_SCHEMAS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # kind -> (required keys, optional keys); "kind" itself is always required.
    "worker_actual_change": (
        frozenset({"task_id"}),
        frozenset({"tracked_modified", "staged", "untracked"}),
    ),
    "integrate_reservation": (frozenset({"task_id"}), frozenset()),
    "worker_finished": (frozenset({"task_id"}), frozenset()),
    "architect_unavailable": (frozenset(), frozenset()),
    "architect_restored": (frozenset(), frozenset()),
}

VALID_OPERATION_KINDS = frozenset({"singleton_contest"})


# ---------------------------------------------------------------------------
# Closed-schema primitives
# ---------------------------------------------------------------------------

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceManifestError(message)


def _object(value: Any, *, where: str) -> Mapping[str, Any]:
    _require(isinstance(value, dict), f"{where}: expected an object, got {type(value).__name__}")
    return value


def _closed(
    value: Any,
    *,
    where: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> Mapping[str, Any]:
    """Validate an object against an exact allowed key set.

    Unknown keys are rejected. A field that is silently ignored is a scenario
    that claims more than it checks.
    """

    mapping = _object(value, where=where)
    required_keys = set(required)
    allowed = required_keys | set(optional)
    missing = sorted(required_keys - set(mapping))
    _require(not missing, f"{where}: missing required fields {missing}")
    unknown = sorted(set(mapping) - allowed)
    _require(
        not unknown,
        f"{where}: unknown fields {unknown}; allowed fields are {sorted(allowed)}",
    )
    return mapping


def _list(value: Any, *, where: str) -> list[Any]:
    _require(isinstance(value, list), f"{where}: expected a list")
    return list(value)


def _text(value: Any, *, where: str) -> str:
    _require(isinstance(value, str) and value.strip(), f"{where}: expected non-empty text")
    return value.strip()


def _bool(value: Any, *, where: str) -> bool:
    _require(isinstance(value, bool), f"{where}: expected true or false")
    return value


def _task_id(value: Any, *, where: str) -> str:
    _require(isinstance(value, str), f"{where}: task ID must be a string, got {value!r}")
    text = value.strip()
    _require(
        bool(SYNTHETIC_TASK_ID_RE.fullmatch(text)),
        f"{where}: task ID must be synthetic NSC-9##, got {value!r}",
    )
    _require(
        text != RESERVED_UNDECLARED_TASK_ID,
        f"{where}: {RESERVED_UNDECLARED_TASK_ID} is reserved as a never-declared ID",
    )
    return text


def _declared_task_id(value: Any, tasks: Mapping[str, Any], *, where: str) -> str:
    task_id = _task_id(value, where=where)
    _require(task_id in tasks, f"{where}: names undeclared task {task_id}")
    return task_id


def _resource_token(value: Any, *, where: str) -> str:
    text = _text(value, where=where)
    _require(
        ":" in text and not text.startswith(":") and not text.endswith(":"),
        f"{where}: an exclusive resource must be a namespaced token such as "
        f"'logical:enemy-tuning-data', got {text!r}",
    )
    return text


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def load_manifest(path: Path | str = MANIFEST_PATH) -> dict[str, Any]:
    manifest = load_json(path)
    _require(isinstance(manifest, dict), "manifest root must be an object")
    validate_manifest(manifest)
    return manifest


def manifest_sha256(path: Path | str = MANIFEST_PATH) -> str:
    """The identity a live evidence envelope must bind itself to."""

    return file_sha256(path)


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    root = _closed(
        manifest,
        where="manifest",
        required={
            "schema_version",
            "name",
            "purpose",
            "task_id_range",
            "source_identity",
            "tasks",
            "scenarios",
        },
    )
    _require(
        root["schema_version"] == MANIFEST_SCHEMA_VERSION,
        f"manifest schema_version must be {MANIFEST_SCHEMA_VERSION}",
    )
    _text(root["name"], where="manifest.name")
    _text(root["purpose"], where="manifest.purpose")
    _text(root["task_id_range"], where="manifest.task_id_range")
    _validate_source_identity(root["source_identity"])

    tasks = _object(root["tasks"], where="manifest.tasks")
    _require(bool(tasks), "manifest must declare at least one task")
    for task_id, task in tasks.items():
        _validate_task(_task_id(task_id, where="manifest.tasks"), task)

    scenarios = _list(root["scenarios"], where="manifest.scenarios")
    _require(bool(scenarios), "manifest must declare a non-empty scenario list")

    seen_ids: set[str] = set()
    for scenario in scenarios:
        scenario_id = _text(
            _object(scenario, where="manifest.scenarios[]").get("id"),
            where="scenario.id",
        )
        _require(scenario_id not in seen_ids, f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)
        _validate_scenario(scenario, tasks)

    unused = unused_task_ids(manifest)
    _require(
        not unused,
        "every declared task must be referenced by a scenario; unreferenced: "
        + ", ".join(unused),
    )


def _validate_source_identity(value: Any) -> None:
    identity = _closed(
        value,
        where="manifest.source_identity",
        required={
            "acceptance_branch",
            "acceptance_base_commit",
            "architect_reference_branch",
            "architect_reference_state",
            "note",
        },
    )
    for key in identity:
        _text(identity[key], where=f"manifest.source_identity.{key}")
    commit = identity["acceptance_base_commit"]
    _require(
        len(commit) == 40 and all(c in "0123456789abcdef" for c in commit.lower()),
        "manifest.source_identity.acceptance_base_commit must be a 40-character SHA",
    )


def _validate_task(task_id: str, value: Any) -> None:
    where = f"task {task_id}"
    task = _closed(
        value,
        where=where,
        required={"title", "summary", "exclusive_resources", "intended_change_surface"},
    )
    _text(task["title"], where=f"{where}.title")
    _text(task["summary"], where=f"{where}.summary")
    resources = _list(task["exclusive_resources"], where=f"{where}.exclusive_resources")
    for resource in resources:
        _resource_token(resource, where=f"{where}.exclusive_resources")
    _require(
        len(resources) == len(set(resources)),
        f"{where}: exclusive_resources must not repeat a token",
    )
    surface = _closed(
        task["intended_change_surface"],
        where=f"{where}.intended_change_surface",
        required={"exact_paths"},
    )
    paths = sr.validate_declared_paths(
        _list(surface["exact_paths"], where=f"{where}.intended_change_surface.exact_paths"),
        where=f"{where}.intended_change_surface.exact_paths",
    )
    _require(bool(paths), f"{where}: a task must intend to change at least one path")


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

def _validate_scenario(value: Any, tasks: Mapping[str, Any]) -> None:
    scenario_id = str(_object(value, where="scenario").get("id", "")).strip()
    where = f"scenario {scenario_id}"
    scenario = _closed(
        value,
        where=where,
        required={
            "id",
            "letter",
            "title",
            "purpose",
            "readiness",
            "required_capabilities",
            "world",
            "fixture_facts",
            "live_evidence",
        },
        optional={"steps", "operation", "pending_reason"},
    )
    _text(scenario["letter"], where=f"{where}.letter")
    _text(scenario["title"], where=f"{where}.title")
    _text(scenario["purpose"], where=f"{where}.purpose")

    readiness = _text(scenario["readiness"], where=f"{where}.readiness")
    _require(
        readiness in READINESS_GATES,
        f"{where}: unknown readiness gate {readiness!r}; allowed "
        f"{sorted(READINESS_GATES)}",
    )

    capabilities = _list(
        scenario["required_capabilities"], where=f"{where}.required_capabilities"
    )
    unknown = [name for name in capabilities if name not in CAPABILITIES]
    _require(not unknown, f"{where}: unknown capabilities {unknown}")
    _require(
        len(capabilities) == len(set(capabilities)),
        f"{where}: required_capabilities must not repeat",
    )
    if readiness != HARNESS_ONLY_GATE:
        _require(
            bool(capabilities),
            f"{where}: a non-harness scenario must name the capabilities it "
            "consumes so it can report PENDING honestly",
        )

    has_steps = "steps" in scenario
    has_operation = "operation" in scenario
    _require(
        has_steps != has_operation,
        f"{where}: a scenario declares exactly one of 'steps' or 'operation'",
    )

    candidates, reservations, resume_task_id = _validate_world(
        where, scenario["world"], tasks
    )
    scenario_tasks = set(candidates) | set(reservations)
    if resume_task_id:
        scenario_tasks.add(resume_task_id)

    _validate_fixture_facts(
        where, scenario["fixture_facts"], tasks, scenario_tasks, reservations, resume_task_id
    )

    if has_steps:
        _validate_steps(where, scenario["steps"], tasks, scenario_tasks, reservations)
        _require_resume_is_contested(
            where, scenario, candidates, resume_task_id
        )
    else:
        _validate_operation(where, scenario["operation"])

    _validate_live_evidence(where, scenario["live_evidence"], scenario_tasks, has_operation)


def _require_resume_is_contested(
    where: str,
    scenario: Mapping[str, Any],
    candidates: Sequence[str],
    resume_task_id: str | None,
) -> None:
    """A scenario that expects the resume task to win must make it earn that.

    Without this, "resume outranks fresh work" can be satisfied by a scheduler
    that simply takes the only task it was offered. The scenario must therefore
    also offer a genuinely launchable fresh candidate and declare the pairing as
    a fixture fact.
    """

    if resume_task_id is None:
        return
    expects_resume_start = any(
        step["expected"].get("outcome") == "start"
        and step["expected"].get("task_id") == resume_task_id
        for step in scenario.get("steps", ())
    )
    if not expects_resume_start:
        return
    _require(
        bool(candidates),
        f"{where}: this scenario expects the resume task {resume_task_id} to be "
        "selected, so it must also offer a fresh candidate to lose to it",
    )
    facts = scenario.get("fixture_facts") or {}
    _require(
        "resume_is_not_queue_order" in facts,
        f"{where}: a scenario expecting resume priority must declare "
        "fixture_facts.resume_is_not_queue_order naming the tempting fresh "
        "candidate, so the fixture proves the answer was not prearranged",
    )
    tempting = str(facts["resume_is_not_queue_order"]["tempting_fresh_task_id"])
    _require(
        tempting in set(candidates),
        f"{where}: the tempting fresh candidate {tempting} is not in fresh_queue",
    )


def _validate_world(
    where: str, value: Any, tasks: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    world = _closed(
        value,
        where=f"{where}.world",
        required={"fresh_queue", "reservations", "advisories"},
        optional={"malformed_advisories", "resume_authority"},
    )

    queue: list[str] = []
    for task_id in _list(world["fresh_queue"], where=f"{where}.world.fresh_queue"):
        queue.append(_declared_task_id(task_id, tasks, where=f"{where}.world.fresh_queue"))
    _require(
        len(queue) == len(set(queue)),
        f"{where}: fresh_queue must not repeat a task",
    )

    resume_task_id: str | None = None
    if "resume_authority" in world:
        resume = _closed(
            world["resume_authority"],
            where=f"{where}.world.resume_authority",
            required={"task_id", "workflow_state", "phase"},
        )
        resume_task_id = _declared_task_id(
            resume["task_id"], tasks, where=f"{where}.world.resume_authority"
        )
        _text(resume["workflow_state"], where=f"{where}.world.resume_authority.workflow_state")
        _text(resume["phase"], where=f"{where}.world.resume_authority.phase")
        # The whole point of scenario I1: resume priority must not be encoded as
        # queue position, or the scheduler can be right by accident.
        _require(
            resume_task_id not in queue,
            f"{where}: the resume task {resume_task_id} must not also appear in "
            "fresh_queue; resume authority is a durable fact, not a ranking",
        )

    reservation_ids: list[str] = []
    for reservation in _list(world["reservations"], where=f"{where}.world.reservations"):
        reservation_ids.append(_validate_reservation(where, reservation, tasks))
    _require(
        len(reservation_ids) == len(set(reservation_ids)),
        f"{where}: a task may declare at most one reservation",
    )

    advisory_ids = set()
    for task_id, advisory in _object(
        world["advisories"], where=f"{where}.world.advisories"
    ).items():
        advisory_id = _declared_task_id(task_id, tasks, where=f"{where}.world.advisories")
        _validate_advisory(where, advisory_id, advisory, tasks)
        advisory_ids.add(advisory_id)

    malformed_ids = set()
    for task_id, malformed in _object(
        world.get("malformed_advisories", {}), where=f"{where}.world.malformed_advisories"
    ).items():
        malformed_id = _declared_task_id(
            task_id, tasks, where=f"{where}.world.malformed_advisories"
        )
        entry = _closed(
            malformed,
            where=f"{where}.world.malformed_advisories[{malformed_id}]",
            required={"defects"},
        )
        defects = _list(
            entry["defects"],
            where=f"{where}.world.malformed_advisories[{malformed_id}].defects",
        )
        _require(
            bool(defects),
            f"{where}: a malformed advisory must name at least one defect",
        )
        unknown = [defect for defect in defects if defect not in VALID_ADVISORY_DEFECTS]
        _require(not unknown, f"{where}: unknown advisory defects {unknown}")
        malformed_ids.add(malformed_id)

    overlap = sorted(advisory_ids & malformed_ids)
    _require(
        not overlap,
        f"{where}: {overlap} declare both a well-formed and a malformed advisory",
    )

    considered = set(queue) | ({resume_task_id} if resume_task_id else set())
    missing_advisory = sorted(
        considered - advisory_ids - malformed_ids - set(reservation_ids)
    )
    _require(
        not missing_advisory,
        f"{where}: candidates {missing_advisory} have no advisory; a scenario must "
        "say what the architect returned for every task it expects to be considered",
    )
    stray = sorted((advisory_ids | malformed_ids) - considered)
    _require(
        not stray,
        f"{where}: advisories for {stray} are never considered by this scenario",
    )

    return tuple(queue), tuple(reservation_ids), resume_task_id


def _validate_reservation(where: str, value: Any, tasks: Mapping[str, Any]) -> str:
    reservation = _closed(
        value,
        where=f"{where}.world.reservations[]",
        required={"task_id", "reservation_kind", "confidence"},
        optional={
            "workflow_state",
            "phase",
            "branch_paths",
            "checkout",
            "predicted_paths",
        },
    )
    task_id = _declared_task_id(
        reservation["task_id"], tasks, where=f"{where}.world.reservations[]"
    )
    scope = f"{where}.world.reservations[{task_id}]"
    kind = _text(reservation["reservation_kind"], where=f"{scope}.reservation_kind")
    _require(
        kind in VALID_RESERVATION_KINDS,
        f"{scope}: unknown reservation kind {kind!r}; allowed "
        f"{sorted(VALID_RESERVATION_KINDS)}",
    )
    confidence = reservation["confidence"]
    _require(
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0.0 <= float(confidence) <= 1.0,
        f"{scope}: confidence must be a number in [0, 1]",
    )
    for key in ("workflow_state", "phase"):
        if key in reservation:
            _text(reservation[key], where=f"{scope}.{key}")

    branch_paths = sr.validate_declared_paths(
        _list(reservation.get("branch_paths", []), where=f"{scope}.branch_paths"),
        where=f"{scope}.branch_paths",
    )
    checkout_paths: list[str] = []
    if "checkout" in reservation:
        checkout = _closed(
            reservation["checkout"],
            where=f"{scope}.checkout",
            required=set(),
            optional={"tracked_modified", "staged", "untracked"},
        )
        _require(bool(checkout), f"{scope}.checkout: declare at least one change")
        for key in ("tracked_modified", "staged", "untracked"):
            checkout_paths.extend(
                sr.validate_declared_paths(
                    _list(checkout.get(key, []), where=f"{scope}.checkout.{key}"),
                    where=f"{scope}.checkout.{key}",
                )
            )
    sr.validate_declared_paths(
        _list(reservation.get("predicted_paths", []), where=f"{scope}.predicted_paths"),
        where=f"{scope}.predicted_paths",
    )

    if kind == "unobservable_surface":
        _require(
            bool(checkout_paths),
            f"{scope}: an unobservable surface must declare a checkout so it is "
            "genuinely unreadable rather than simply absent",
        )
    else:
        _require(
            bool(branch_paths) or bool(checkout_paths),
            f"{scope}: declares no observable surface; use reservation_kind "
            "'unobservable_surface' if that is intended",
        )
    return task_id


def _validate_advisory(
    where: str, task_id: str, value: Any, tasks: Mapping[str, Any]
) -> None:
    scope = f"{where}.world.advisories[{task_id}]"
    advisory = _closed(
        value,
        where=scope,
        required={
            "predicted_change_surface",
            "integration_risk",
            "parallel_recommendation",
            "confidence",
        },
        optional={"conflicting_task_ids", "escalation", "disjointness_claims"},
    )
    surface = _closed(
        advisory["predicted_change_surface"],
        where=f"{scope}.predicted_change_surface",
        required={"exact_paths"},
    )
    paths = sr.validate_declared_paths(
        _list(surface["exact_paths"], where=f"{scope}.predicted_change_surface.exact_paths"),
        where=f"{scope}.predicted_change_surface.exact_paths",
    )
    _require(bool(paths), f"{scope}: a well-formed advisory predicts at least one path")

    risk = _text(advisory["integration_risk"], where=f"{scope}.integration_risk")
    _require(
        risk in VALID_INTEGRATION_RISKS,
        f"{scope}: invalid integration_risk {risk!r}",
    )
    recommendation = _text(
        advisory["parallel_recommendation"], where=f"{scope}.parallel_recommendation"
    )
    _require(
        recommendation in VALID_RECOMMENDATIONS,
        f"{scope}: invalid parallel_recommendation {recommendation!r}",
    )
    confidence = advisory["confidence"]
    _require(
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0.0 <= float(confidence) <= 1.0,
        f"{scope}: confidence must be a number in [0, 1]",
    )
    for other in _list(
        advisory.get("conflicting_task_ids", []), where=f"{scope}.conflicting_task_ids"
    ):
        _declared_task_id(other, tasks, where=f"{scope}.conflicting_task_ids")
    if "escalation" in advisory:
        escalation = _closed(
            advisory["escalation"],
            where=f"{scope}.escalation",
            required={"category", "question"},
        )
        category = _text(escalation["category"], where=f"{scope}.escalation.category")
        _require(
            category in VALID_ESCALATION_CATEGORIES,
            f"{scope}: invalid escalation category {category!r}",
        )
        _require(
            isinstance(escalation["question"], str),
            f"{scope}.escalation.question must be a string",
        )
        if category != "none":
            _require(
                bool(escalation["question"].strip()),
                f"{scope}: an escalation category requires the specific "
                "design/canon question",
            )
    # disjointness_claims is a list of task IDs only. There is deliberately no
    # free-text justification field: prose can explain a verdict in a report but
    # must never be the thing that makes a candidate eligible to start.
    for other in _list(
        advisory.get("disjointness_claims", []), where=f"{scope}.disjointness_claims"
    ):
        _declared_task_id(other, tasks, where=f"{scope}.disjointness_claims")


# ---------------------------------------------------------------------------
# Fixture facts
# ---------------------------------------------------------------------------

def _validate_fixture_facts(
    where: str,
    value: Any,
    tasks: Mapping[str, Any],
    scenario_tasks: set[str],
    reservations: Sequence[str],
    resume_task_id: str | None,
) -> None:
    scope = f"{where}.fixture_facts"
    facts = _closed(
        value,
        where=scope,
        required=set(),
        optional={
            "reservation_actual_paths",
            "reservation_surface_unknown",
            "disjoint_pairs",
            "overlapping_pairs",
            "candidate_reservation_overlap",
            "unity_meta_companion_pairs",
            "disjointness_evidence",
            "resume_is_not_queue_order",
        },
    )

    for task_id, paths in _object(
        facts.get("reservation_actual_paths", {}), where=f"{scope}.reservation_actual_paths"
    ).items():
        observed = _declared_task_id(
            task_id, tasks, where=f"{scope}.reservation_actual_paths"
        )
        _require(
            observed in reservations,
            f"{scope}: {observed} declares actual paths but has no reservation",
        )
        sr.validate_declared_paths(
            _list(paths, where=f"{scope}.reservation_actual_paths[{observed}]"),
            where=f"{scope}.reservation_actual_paths[{observed}]",
        )

    for task_id in _list(
        facts.get("reservation_surface_unknown", []),
        where=f"{scope}.reservation_surface_unknown",
    ):
        unknown = _declared_task_id(
            task_id, tasks, where=f"{scope}.reservation_surface_unknown"
        )
        _require(
            unknown in reservations,
            f"{scope}: {unknown} is declared unknown but has no reservation",
        )

    for pair in _list(facts.get("disjoint_pairs", []), where=f"{scope}.disjoint_pairs"):
        entries = _list(pair, where=f"{scope}.disjoint_pairs[]")
        _require(len(entries) == 2, f"{scope}: disjoint_pairs entries are two task IDs")
        for task_id in entries:
            _require(
                _declared_task_id(task_id, tasks, where=f"{scope}.disjoint_pairs")
                in scenario_tasks,
                f"{scope}: disjoint_pairs names a task outside this scenario",
            )

    for entry in _list(
        facts.get("overlapping_pairs", []), where=f"{scope}.overlapping_pairs"
    ):
        pair = _closed(
            entry, where=f"{scope}.overlapping_pairs[]", required={"tasks", "on"}
        )
        entries = _list(pair["tasks"], where=f"{scope}.overlapping_pairs[].tasks")
        _require(len(entries) == 2, f"{scope}: overlapping_pairs needs exactly two tasks")
        for task_id in entries:
            _require(
                _declared_task_id(task_id, tasks, where=f"{scope}.overlapping_pairs")
                in scenario_tasks,
                f"{scope}: overlapping_pairs names a task outside this scenario",
            )
        overlap = sr.validate_declared_paths(
            _list(pair["on"], where=f"{scope}.overlapping_pairs[].on"),
            where=f"{scope}.overlapping_pairs[].on",
        )
        _require(bool(overlap), f"{scope}: an overlapping pair must name what it overlaps on")

    for entry in _list(
        facts.get("candidate_reservation_overlap", []),
        where=f"{scope}.candidate_reservation_overlap",
    ):
        overlap_entry = _closed(
            entry,
            where=f"{scope}.candidate_reservation_overlap[]",
            required={"candidate", "reservation", "on"},
        )
        candidate = _declared_task_id(
            overlap_entry["candidate"], tasks, where=f"{scope}.candidate_reservation_overlap"
        )
        reservation = _declared_task_id(
            overlap_entry["reservation"],
            tasks,
            where=f"{scope}.candidate_reservation_overlap",
        )
        _require(
            candidate in scenario_tasks,
            f"{scope}: candidate {candidate} is outside this scenario",
        )
        _require(
            reservation in reservations,
            f"{scope}: {reservation} has no reservation in this scenario",
        )
        sr.validate_declared_paths(
            _list(overlap_entry["on"], where=f"{scope}.candidate_reservation_overlap[].on"),
            where=f"{scope}.candidate_reservation_overlap[].on",
        )

    for entry in _list(
        facts.get("unity_meta_companion_pairs", []),
        where=f"{scope}.unity_meta_companion_pairs",
    ):
        companion = _closed(
            entry,
            where=f"{scope}.unity_meta_companion_pairs[]",
            required={"asset", "meta"},
        )
        asset = sr.validate_declared_path(
            companion["asset"], where=f"{scope}.unity_meta_companion_pairs[].asset"
        )
        meta = sr.validate_declared_path(
            companion["meta"], where=f"{scope}.unity_meta_companion_pairs[].meta"
        )
        _require(
            meta == asset + ".meta",
            f"{scope}: {meta} is not the .meta companion of {asset}",
        )

    for entry in _list(
        facts.get("disjointness_evidence", []), where=f"{scope}.disjointness_evidence"
    ):
        evidence = _closed(
            entry,
            where=f"{scope}.disjointness_evidence[]",
            required={"candidate_task_id", "reservation_task_id", "verdict"},
        )
        candidate = _declared_task_id(
            evidence["candidate_task_id"], tasks, where=f"{scope}.disjointness_evidence"
        )
        other = _declared_task_id(
            evidence["reservation_task_id"], tasks, where=f"{scope}.disjointness_evidence"
        )
        _require(
            candidate in scenario_tasks and other in scenario_tasks,
            f"{scope}: disjointness_evidence names a task outside this scenario",
        )
        verdict = _text(evidence["verdict"], where=f"{scope}.disjointness_evidence[].verdict")
        _require(
            verdict in VALID_DISJOINTNESS_VERDICTS,
            f"{scope}: unknown disjointness verdict {verdict!r}; allowed "
            f"{sorted(VALID_DISJOINTNESS_VERDICTS)}",
        )

    if "resume_is_not_queue_order" in facts:
        _require(
            resume_task_id is not None,
            f"{scope}: resume_is_not_queue_order requires world.resume_authority",
        )
        entry = _closed(
            facts["resume_is_not_queue_order"],
            where=f"{scope}.resume_is_not_queue_order",
            required={"resume_task_id", "tempting_fresh_task_id"},
        )
        declared_resume = _declared_task_id(
            entry["resume_task_id"], tasks, where=f"{scope}.resume_is_not_queue_order"
        )
        tempting = _declared_task_id(
            entry["tempting_fresh_task_id"],
            tasks,
            where=f"{scope}.resume_is_not_queue_order",
        )
        _require(
            declared_resume == resume_task_id,
            f"{scope}: resume_is_not_queue_order names {declared_resume} but the "
            f"scenario's resume authority is {resume_task_id}",
        )
        _require(
            tempting != resume_task_id,
            f"{scope}: the tempting fresh candidate must not be the resume task",
        )


# ---------------------------------------------------------------------------
# Steps and operations
# ---------------------------------------------------------------------------

VALID_EXPECTED_KEYS = frozenset(
    {
        "outcome",
        "task_id",
        "require_worker_id",
        "waited_task_ids",
        "conflicts",
        "fingerprint_changed",
        "forbid_launch",
        "forbid_durable_mutation",
        "distinct_assignment",
        "no_human_escalation",
        "note",
    }
)


def _validate_steps(
    where: str,
    value: Any,
    tasks: Mapping[str, Any],
    scenario_tasks: set[str],
    reservations: Sequence[str],
) -> None:
    steps = _list(value, where=f"{where}.steps")
    _require(bool(steps), f"{where}: a step-based scenario needs at least one step")
    for index, step in enumerate(steps, start=1):
        scope = f"{where}.steps[{index}]"
        entry = _closed(
            step, where=scope, required={"step", "expected"}, optional={"transition"}
        )
        _require(entry["step"] == index, f"{scope}: step numbers must be 1..n in order")
        if entry.get("transition") is not None:
            _validate_transition(scope, entry["transition"], tasks, scenario_tasks)
        _validate_expected(
            scope, entry["expected"], tasks, scenario_tasks, reservations
        )


def _validate_transition(
    where: str, value: Any, tasks: Mapping[str, Any], scenario_tasks: set[str]
) -> None:
    transition = _object(value, where=f"{where}.transition")
    kind = str(transition.get("kind", "")).strip()
    _require(
        kind in TRANSITION_SCHEMAS,
        f"{where}: unknown transition {kind!r}; allowed {sorted(TRANSITION_SCHEMAS)}",
    )
    required, optional = TRANSITION_SCHEMAS[kind]
    entry = _closed(
        transition,
        where=f"{where}.transition({kind})",
        required=required | {"kind"},
        optional=optional,
    )
    if "task_id" in entry:
        task_id = _declared_task_id(
            entry["task_id"], tasks, where=f"{where}.transition({kind}).task_id"
        )
        _require(
            task_id in scenario_tasks,
            f"{where}: transition names {task_id}, which is not in this scenario",
        )
    for key in ("tracked_modified", "staged", "untracked"):
        if key in entry:
            paths = sr.validate_declared_paths(
                _list(entry[key], where=f"{where}.transition({kind}).{key}"),
                where=f"{where}.transition({kind}).{key}",
            )
            _require(
                bool(paths),
                f"{where}: transition({kind}).{key} must name at least one path",
            )


def _validate_expected(
    where: str,
    value: Any,
    tasks: Mapping[str, Any],
    scenario_tasks: set[str],
    reservations: Sequence[str],
) -> None:
    scope = f"{where}.expected"
    expected = _closed(
        value, where=scope, required={"outcome"}, optional=VALID_EXPECTED_KEYS - {"outcome"}
    )
    outcome = _text(expected["outcome"], where=f"{scope}.outcome")
    _require(outcome in OUTCOMES, f"{scope}: unknown outcome {outcome!r}")

    if outcome == "start":
        _require(
            "task_id" in expected,
            f"{scope}: a START must always name the exact task it launches",
        )
        _require(
            expected.get("require_worker_id") is True,
            f"{scope}: a START must require an observed worker ID; a launch "
            "without one can never be acceptance evidence",
        )
        _require(
            not expected.get("forbid_launch"),
            f"{scope}: a START cannot also forbid a launch",
        )
    if "task_id" in expected:
        task_id = _declared_task_id(expected["task_id"], tasks, where=f"{scope}.task_id")
        _require(
            task_id in scenario_tasks,
            f"{scope}: expected task {task_id} is not a candidate, resume task, or "
            "reservation in this scenario",
        )
    for key in (
        "require_worker_id",
        "fingerprint_changed",
        "forbid_launch",
        "forbid_durable_mutation",
        "distinct_assignment",
        "no_human_escalation",
    ):
        if key in expected:
            _bool(expected[key], where=f"{scope}.{key}")
    if "note" in expected:
        _text(expected["note"], where=f"{scope}.note")

    waited = _list(expected.get("waited_task_ids", []), where=f"{scope}.waited_task_ids")
    for task_id in waited:
        waited_id = _declared_task_id(task_id, tasks, where=f"{scope}.waited_task_ids")
        _require(
            waited_id in scenario_tasks,
            f"{scope}: waited task {waited_id} is not part of this scenario",
        )

    for conflict in _list(expected.get("conflicts", []), where=f"{scope}.conflicts"):
        _validate_conflict(scope, conflict, tasks, scenario_tasks, reservations)


def _validate_conflict(
    where: str,
    value: Any,
    tasks: Mapping[str, Any],
    scenario_tasks: set[str],
    reservations: Sequence[str],
) -> None:
    scope = f"{where}.conflicts[]"
    conflict = _closed(
        value,
        where=scope,
        required={"candidate_task_id", "conflicting_task_id", "kind", "on"},
    )
    candidate = _declared_task_id(
        conflict["candidate_task_id"], tasks, where=f"{scope}.candidate_task_id"
    )
    other = _declared_task_id(
        conflict["conflicting_task_id"], tasks, where=f"{scope}.conflicting_task_id"
    )
    _require(
        candidate in scenario_tasks and other in scenario_tasks,
        f"{scope}: a conflict must name tasks that exist in this scenario",
    )
    _require(candidate != other, f"{scope}: a task cannot hard-conflict with itself")
    kind = _text(conflict["kind"], where=f"{scope}.kind")
    _require(
        kind in VALID_CONFLICT_KINDS,
        f"{scope}: unknown conflict kind {kind!r}; allowed {sorted(VALID_CONFLICT_KINDS)}",
    )
    values = _list(conflict["on"], where=f"{scope}.on")
    _require(
        bool(values),
        f"{scope}: a conflict must name the exact overlapping paths or resources; "
        "a prose reason is never sufficient",
    )
    if kind == "exclusive_resource":
        declared_resources = set(
            normalize_tokens(tasks[candidate].get("exclusive_resources", ()))
        ) & set(normalize_tokens(tasks[other].get("exclusive_resources", ())))
        for token in values:
            _resource_token(token, where=f"{scope}.on")
            _require(
                token in declared_resources,
                f"{scope}: {token!r} is not an exclusive resource declared by both "
                f"{candidate} and {other}",
            )
    else:
        sr.validate_declared_paths(values, where=f"{scope}.on")
    if kind != "active_task_id":
        _require(
            other in reservations or other in scenario_tasks,
            f"{scope}: {other} is neither a reservation nor a candidate here",
        )


def _validate_operation(where: str, value: Any) -> None:
    scope = f"{where}.operation"
    operation = _closed(value, where=scope, required={"kind", "expected"})
    kind = _text(operation["kind"], where=f"{scope}.kind")
    _require(
        kind in VALID_OPERATION_KINDS,
        f"{scope}: unknown operation kind {kind!r}; allowed {sorted(VALID_OPERATION_KINDS)}",
    )
    expected = _closed(
        operation["expected"],
        where=f"{scope}.expected",
        required={
            "distinct_scheduler_ids",
            "rejected_launched_nothing",
            "forbid_durable_mutation",
        },
        optional={"note"},
    )
    for key in (
        "distinct_scheduler_ids",
        "rejected_launched_nothing",
        "forbid_durable_mutation",
    ):
        _require(
            _bool(expected[key], where=f"{scope}.expected.{key}"),
            f"{scope}.expected.{key} must be true; a singleton operation that does "
            "not assert this proves nothing",
        )
    if "note" in expected:
        _text(expected["note"], where=f"{scope}.expected.note")


def _validate_live_evidence(
    where: str, value: Any, scenario_tasks: set[str], has_operation: bool
) -> None:
    scope = f"{where}.live_evidence"
    evidence = _closed(
        value,
        where=scope,
        required={"required_checks"},
        optional={"optional_checks", "wait_then_start_task_ids"},
    )
    checks = _list(evidence["required_checks"], where=f"{scope}.required_checks")
    _require(bool(checks), f"{scope}: name at least one required live-evidence check")
    # A check is optional only because the schema says so. An optional result is
    # never inferred from a check that happened to be absent or to pass.
    optional_checks = _list(
        evidence.get("optional_checks", []), where=f"{scope}.optional_checks"
    )
    for label, names in (("required", checks), ("optional", optional_checks)):
        unknown = [name for name in names if name not in LIVE_EVIDENCE_CHECKS]
        _require(
            not unknown,
            f"{scope}: unknown {label} live-evidence checks {unknown}; allowed "
            f"{sorted(LIVE_EVIDENCE_CHECKS)}",
        )
        _require(
            len(names) == len(set(names)),
            f"{scope}: {label}_checks must not repeat",
        )
    overlap = sorted(set(checks) & set(optional_checks))
    _require(
        not overlap,
        f"{scope}: {overlap} cannot be both required and optional",
    )
    if has_operation:
        _require(
            "singleton_lock_ownership" in checks,
            f"{scope}: a singleton operation must require singleton_lock_ownership",
        )
    wait_then_start = _list(
        evidence.get("wait_then_start_task_ids", []),
        where=f"{scope}.wait_then_start_task_ids",
    )
    for task_id in wait_then_start:
        _require(
            _task_id(task_id, where=f"{scope}.wait_then_start_task_ids") in scenario_tasks,
            f"{scope}: wait_then_start names a task outside this scenario",
        )
    if "wait_then_start_transition" in checks:
        _require(
            bool(wait_then_start),
            f"{scope}: wait_then_start_transition requires wait_then_start_task_ids",
        )
    else:
        _require(
            not wait_then_start,
            f"{scope}: wait_then_start_task_ids has no effect without the "
            "wait_then_start_transition check",
        )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def scenarios(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(dict(scenario) for scenario in manifest.get("scenarios", ()))


def scenario_by_id(manifest: Mapping[str, Any], scenario_id: str) -> dict[str, Any]:
    for scenario in scenarios(manifest):
        if scenario["id"] == scenario_id:
            return scenario
    raise AcceptanceManifestError(f"unknown scenario id: {scenario_id}")


def scenario_task_ids(scenario: Mapping[str, Any]) -> tuple[str, ...]:
    """Every task this scenario may legitimately name in evidence."""

    world = scenario.get("world") or {}
    referenced = set(world.get("fresh_queue") or ())
    referenced.update(
        str(item.get("task_id")) for item in (world.get("reservations") or ())
    )
    resume = world.get("resume_authority")
    if resume:
        referenced.add(str(resume.get("task_id")))
    return tuple(sorted(referenced))


def referenced_task_ids(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    referenced: set[str] = set()
    for scenario in scenarios(manifest):
        referenced.update(scenario_task_ids(scenario))
    return tuple(sorted(referenced))


def unused_task_ids(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    declared = set(manifest.get("tasks") or {})
    return tuple(sorted(declared - set(referenced_task_ids(manifest))))


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate the Software Architect acceptance scenario manifest."
    )
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument(
        "--list", action="store_true", help="List scenarios and readiness gates."
    )
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    print(f"[PASS] manifest is valid: {args.manifest}")
    print(f"[STATE] schema_version: {manifest['schema_version']}")
    print(f"[STATE] manifest_sha256: {manifest_sha256(args.manifest)}")
    print(f"[STATE] scenarios: {len(manifest['scenarios'])}")
    print(f"[STATE] declared tasks: {len(manifest['tasks'])}")
    if args.list:
        for scenario in scenarios(manifest):
            mode = "operation" if "operation" in scenario else "steps"
            print(
                f"  {scenario['letter']}  {scenario['id']}\n"
                f"      readiness: {scenario['readiness']} ({mode})\n"
                f"      {scenario['title']}"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
