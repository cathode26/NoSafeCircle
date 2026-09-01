"""Verify acceptance scenarios in three clearly separated entry points.

```text
verify_fixtures()    LAYER 1  no adapter, no scheduler, runs today
                     Does the built Git fixture actually model the integration
                     risk the scenario claims? Reservation surfaces are
                     re-observed with ordinary Git commands, disjointness is
                     recomputed from committed data, and both are compared to
                     the declared facts.

run_harness()        LAYER 2H accepts a caller-supplied adapter
                     Exercises fixture construction, transitions, durable-state
                     snapshots and every check. Can only ever report
                     HARNESS_PASS, HARNESS_FAIL, FIXTURE_* or
                     PENDING_CAPABILITY.

run_acceptance()     LAYER 2A accepts NO adapter argument
                     Constructs RealPollingArchitectAdapter itself, collects one
                     immutable evidence record per manifest step, and derives
                     acceptance from each step's own scheduler events plus Git
                     state. The only path that can emit PASS or FAIL.
```

## Why acceptance is graded per step

A later audit reproduced two ways a real ``PASS`` could still be manufactured
without any matching scheduler event:

- scenario D returned the expected WAIT summary with ``events=()``;
- scenario A omitted the first launch event entirely, and the second step's
  event was reused to satisfy the first, because one mutable
  ``adapter.last_observation`` graded every step.

The fix is architectural. ``_execute_steps`` records the adapter's event-stream
position before each operation, invokes exactly one operation, freezes only the
events that operation produced into a ``StepExecutionEvidence`` record, and
grades that step against nothing else. Decision events are consumed: an event
that graded one step is refused for another. A step whose slice lacks its own
complete poll lifecycle and its own matching decision event fails, and a real
adapter that cannot emit that lifecycle leaves the scenario PENDING rather than
passing.

## Why acceptance provenance is verifier-owned

An earlier draft let the caller hand in any adapter object and then decided
what the result meant by reading a public adapter-kind string off that object.
An independent audit reproduced the obvious consequence: a scripted stub that
declared every capability, set that string to the real value and returned the
expected decision string produced a real ``PASS``.

The fix is structural rather than another check:

- there is no adapter-kind string anywhere in the package;
- ``run_harness`` accepts an adapter and has no code path to ``STATUS_PASS``;
- ``run_acceptance`` has no adapter parameter, so there is nothing to inject;
- acceptance is derived by ``_verify_real_evidence`` from the scheduler's own
  structured events and the fixture's Git state, not from the returned
  ``outcome`` string alone;
- missing evidence, especially a missing worker ID, is a failure and is never
  filled in by the harness.

`test_only_the_acceptance_path_can_emit_pass` enforces the first four points as
a static scan of this file, so the property survives future edits.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import manifest as manifest_module
import scenario_world as sw
import synthetic_repository as sr
from acceptance_lib import (
    FAILING_STATUSES,
    LAUNCH_OUTCOMES,
    MANIFEST_PATH,
    STATUS_FAIL,
    STATUS_FIXTURE_FAIL,
    STATUS_FIXTURE_PASS,
    STATUS_HARNESS_FAIL,
    STATUS_HARNESS_PASS,
    STATUS_PASS,
    STATUS_PENDING,
    FixtureRoot,
    create_disposable_parent,
    create_fixture_root,
    destroy_disposable_parent,
    normalize_tokens,
    unity_asset_identity,
)
from scheduler_adapter import (
    ACCEPTANCE_EVENT_FIELDS,
    DECISION_EVENTS,
    EVENT_CANDIDATE_WAITED,
    EVENT_HUMAN_REVIEW,
    EVENT_LOCK_ACQUIRED,
    EVENT_LOCK_REJECTED,
    EVENT_POLL_FINISHED,
    EVENT_POLL_STARTED,
    EVENT_WORKER_LAUNCHED,
    AdapterNotWired,
    CycleObservation,
    RealPollingArchitectAdapter,
    SchedulerEvent,
    ScriptedAdapter,
    SingletonObservation,
    UnsupportedScenario,
    freeze_events,
)

EVIDENCE_AUTHORITY_REAL = "real_scheduler"
EVIDENCE_AUTHORITY_HARNESS = "harness_adapter"
"""Explicit capability stamp on every evidence record.

``_execute_steps`` is shared by the harness and the acceptance path, so the
record itself says which one produced it. Only ``EVIDENCE_AUTHORITY_REAL``
records can contribute to PASS, and only the verifier-owned path - which accepts
no adapter argument - can produce them.
"""


@dataclass(frozen=True)
class StepExecutionEvidence:
    """One manifest step's immutable execution record.

    ``events`` holds exactly what this step's single adapter operation produced.
    Nothing here is shared with, or recomputed from, another step.
    """

    scenario_id: str
    step_index: int
    operation: str
    authority: str
    decision: CycleObservation
    events: tuple[SchedulerEvent, ...]
    reused_decision_digests: tuple[str, ...]
    before_state_fingerprint: str
    after_state_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "step_index": self.step_index,
            "operation": self.operation,
            "authority": self.authority,
            "decision": self.decision.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "reused_decision_digests": list(self.reused_decision_digests),
            "before_state_fingerprint": self.before_state_fingerprint,
            "after_state_fingerprint": self.after_state_fingerprint,
        }


@dataclass(frozen=True)
class Check:
    layer: str
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ScenarioResult:
    scenario_id: str
    letter: str
    title: str
    readiness: str
    status: str
    answered_by: str
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "letter": self.letter,
            "title": self.title,
            "readiness": self.readiness,
            "status": self.status,
            "answered_by": self.answered_by,
            "checks": [check.to_dict() for check in self.checks],
            "notes": list(self.notes),
        }


def _result(scenario: Mapping[str, Any], *, status: str, answered_by: str) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=str(scenario["id"]),
        letter=str(scenario["letter"]),
        title=str(scenario["title"]),
        readiness=str(scenario["readiness"]),
        status=status,
        answered_by=answered_by,
    )


# ---------------------------------------------------------------------------
# Layer 1: fixture verification
# ---------------------------------------------------------------------------

def verify_fixture(
    scenario: Mapping[str, Any], world: sw.ScenarioWorld
) -> list[Check]:
    checks: list[Check] = []
    facts = scenario.get("fixture_facts") or {}
    world_spec = scenario.get("world") or {}
    observed = {item.task_id: item for item in world.reservations()}

    declared_reservations = {
        str(item.get("task_id")) for item in (world_spec.get("reservations") or ())
    }
    checks.append(
        Check(
            "fixture",
            "reservations_built",
            set(observed) == declared_reservations,
            f"observed {sorted(observed)} declared {sorted(declared_reservations)}",
        )
    )

    for task_id, expected_paths in (
        facts.get("reservation_actual_paths") or {}
    ).items():
        reservation = observed.get(task_id)
        expected = tuple(sorted(expected_paths))
        actual = reservation.actual_paths if reservation is not None else ()
        checks.append(
            Check(
                "fixture",
                f"actual_paths[{task_id}]",
                reservation is not None and actual == expected,
                f"git reported {list(actual)}; scenario declared {list(expected)}",
            )
        )

    for task_id in facts.get("reservation_surface_unknown") or ():
        reservation = observed.get(task_id)
        unknown = reservation is not None and reservation.surface_unknown
        empty = reservation is not None and not reservation.actual_paths
        checks.append(
            Check(
                "fixture",
                f"surface_unknown[{task_id}]",
                bool(unknown and empty),
                (
                    "an unreadable surface must be recorded as UNKNOWN with no "
                    "asserted paths; got surface_unknown="
                    f"{reservation.surface_unknown if reservation else 'missing'}"
                ),
            )
        )

    for pair in facts.get("disjoint_pairs") or ():
        left, right = pair
        overlap = sw.surface_overlap(
            _task_or_reservation_surface(world, observed, left),
            _task_or_reservation_surface(world, observed, right),
        )
        checks.append(
            Check(
                "fixture",
                f"disjoint[{left},{right}]",
                not overlap,
                f"unexpected overlap on {list(overlap)}" if overlap else "disjoint",
            )
        )

    for entry in facts.get("overlapping_pairs") or ():
        left, right = entry["tasks"]
        expected = tuple(sorted(entry.get("on", ())))
        overlap = sw.surface_overlap(
            sw.declared_surface(world, left), sw.declared_surface(world, right)
        )
        checks.append(
            Check(
                "fixture",
                f"overlap[{left},{right}]",
                set(expected) <= set(overlap),
                f"declared overlap {list(expected)}; computed {list(overlap)}",
            )
        )

    for entry in facts.get("candidate_reservation_overlap") or ():
        candidate = entry["candidate"]
        reservation_id = entry["reservation"]
        expected = tuple(sorted(entry.get("on", ())))
        reservation = observed.get(reservation_id)
        overlap = (
            sw.surface_overlap(
                sw.declared_surface(world, candidate),
                sw.reservation_surface(reservation),
            )
            if reservation is not None
            else ()
        )
        checks.append(
            Check(
                "fixture",
                f"candidate_overlap[{candidate},{reservation_id}]",
                set(expected) <= set(overlap),
                f"declared {list(expected)}; observed {list(overlap)}",
            )
        )

    checks.extend(_verify_meta_companions(facts, world))
    checks.extend(_verify_disjointness_evidence(facts, world))
    checks.extend(_verify_resume_is_not_queue_order(facts, world))

    checks.append(
        Check(
            "fixture",
            "source_repository_deterministic_head",
            len(world.source.head) == 40,
            f"HEAD={world.source.head} tree={world.source.tree}",
        )
    )
    return checks


def _verify_meta_companions(
    facts: Mapping[str, Any], world: sw.ScenarioWorld
) -> list[Check]:
    """Prove the fixture really contains both halves of a Unity asset identity."""

    checks: list[Check] = []
    for entry in facts.get("unity_meta_companion_pairs") or ():
        asset = str(entry["asset"])
        meta = str(entry["meta"])
        asset_exists = sr.fixture_relative(world.source, asset).is_file()
        meta_exists = sr.fixture_relative(world.source, meta).is_file()
        same_identity = unity_asset_identity(meta) == unity_asset_identity(asset)
        checks.append(
            Check(
                "fixture",
                f"unity_meta_companion[{asset}]",
                asset_exists and meta_exists and same_identity,
                (
                    f"asset present={asset_exists} meta present={meta_exists} "
                    f"shared identity={same_identity}"
                ),
            )
        )
    return checks


def _verify_disjointness_evidence(
    facts: Mapping[str, Any], world: sw.ScenarioWorld
) -> list[Check]:
    """Recompute every disjointness verdict from committed structured data.

    Scenario G2's START eligibility rests on this check, not on the architect's
    prose. If the committed exclusive-resource tokens stop proving disjointness,
    the fixture fails here regardless of how persuasive the advisory reads.
    """

    checks: list[Check] = []
    for entry in facts.get("disjointness_evidence") or ():
        candidate = str(entry["candidate_task_id"])
        other = str(entry["reservation_task_id"])
        declared = str(entry["verdict"])
        computed = world.compute_disjointness(candidate, other)
        checks.append(
            Check(
                "fixture",
                f"disjointness[{candidate},{other}]",
                computed.verdict == declared,
                (
                    f"declared {declared!r}; computed {computed.verdict!r} from "
                    f"candidate resources {list(computed.candidate_resources)} and "
                    f"reservation resources {list(computed.reservation_resources)}; "
                    f"contracts {computed.candidate_contract_sha256[:12]}/"
                    f"{computed.reservation_contract_sha256[:12]}"
                ),
            )
        )
    return checks


def _verify_resume_is_not_queue_order(
    facts: Mapping[str, Any], world: sw.ScenarioWorld
) -> list[Check]:
    """Prove resume priority is not encoded as a queue position."""

    entry = facts.get("resume_is_not_queue_order")
    if not entry:
        return []
    resume_task_id = str(entry["resume_task_id"])
    tempting = str(entry["tempting_fresh_task_id"])
    queue = world.candidate_queue()
    resume = world.resume_candidate()
    separated = resume == resume_task_id and resume_task_id not in queue
    contested = bool(queue) and queue[0] == tempting
    return [
        Check(
            "fixture",
            "resume_is_not_queue_order",
            separated and contested,
            (
                f"resume authority={resume!r}; fresh queue={list(queue)}; the resume "
                f"task must be absent from the fresh ranking and {tempting} must "
                "head it, so selecting the resume task cannot be queue order"
            ),
        )
    ]


def _task_or_reservation_surface(
    world: sw.ScenarioWorld,
    observed: Mapping[str, sw.Reservation],
    task_id: str,
) -> tuple[str, ...]:
    """Prefer a task's declared surface; fall back to a reservation's surface.

    A disjointness fact can legitimately name a task that only appears as an
    in-flight reservation, which has no candidate contract in this scenario.
    """

    if task_id in world.tasks:
        return sw.declared_surface(world, task_id)
    reservation = observed.get(task_id)
    return sw.reservation_surface(reservation) if reservation is not None else ()


# ---------------------------------------------------------------------------
# Layer 2: scheduling checks, shared by both entry points
# ---------------------------------------------------------------------------

def verify_scheduling(
    scenario: Mapping[str, Any],
    world: sw.ScenarioWorld,
    adapter: Any,
) -> list[Check]:
    """Summary-level scheduling checks. Never an acceptance claim by itself."""

    return _execute_steps(scenario, world, adapter)[0]


def collect_step_evidence(
    scenario: Mapping[str, Any],
    world: sw.ScenarioWorld,
    adapter: Any,
) -> list[StepExecutionEvidence]:
    """Drive one scenario and return one frozen evidence record per step.

    HARNESS-CALLABLE AND STATUS-FREE. It returns evidence, never a status, and
    every record it produces from a caller-supplied adapter is stamped
    ``EVIDENCE_AUTHORITY_HARNESS``. Only ``run_acceptance_scenario`` - which
    takes no adapter - can turn records into an acceptance status, and it
    refuses any record that is not stamped ``EVIDENCE_AUTHORITY_REAL``.
    """

    return _execute_steps(scenario, world, adapter)[1]


def _event_stream_position(adapter: Any) -> int | None:
    """Read the adapter's cumulative event-stream length, when it exposes one."""

    log = getattr(adapter, "event_log", None)
    if not callable(log):
        return None
    return len(tuple(log()))


def _events_produced_by_step(
    adapter: Any, observation: CycleObservation, position: int | None
) -> tuple[SchedulerEvent, ...]:
    """Return only the events this one operation produced.

    With a cumulative stream, that is the slice appended after the position
    recorded before the call. Without one, it is the cycle's own event tuple.
    Either way a step is graded on its own records; the final observation is
    never reused for an earlier step.
    """

    if position is None:
        return observation.events
    stream = freeze_events(adapter.event_log())
    if len(stream) < position:
        raise UnsupportedScenario(
            "the adapter's event stream shrank during a step; acceptance "
            "requires an append-only stream"
        )
    return stream[position:]


def _execute_steps(
    scenario: Mapping[str, Any],
    world: sw.ScenarioWorld,
    adapter: Any,
) -> tuple[list[Check], list[StepExecutionEvidence]]:
    """Run every step once, returning summary checks and per-step evidence."""

    checks: list[Check] = []
    evidence: list[StepExecutionEvidence] = []
    # Only the adapter this module constructs for itself can carry real
    # authority. Anything handed in - including a subclass or a lookalike - is
    # harness evidence and can never reach PASS.
    authority = (
        EVIDENCE_AUTHORITY_REAL
        if type(adapter) is RealPollingArchitectAdapter
        else EVIDENCE_AUTHORITY_HARNESS
    )
    consumed_decisions: set[str] = set()
    for step in scenario.get("steps") or ():
        index = int(step["step"])
        prefix = f"step{index}"
        fingerprint_before = world.integration_fingerprint()
        durable_before = world.durable_state_fingerprint()
        world.apply_transition(step.get("transition"))
        fingerprint_after_transition = world.integration_fingerprint()
        durable_after_transition = world.durable_state_fingerprint()
        launches_before = len(world.launched)

        stream_position = _event_stream_position(adapter)
        observation = adapter.observe_cycle(world)
        durable_after_observation = world.durable_state_fingerprint()
        produced = _events_produced_by_step(adapter, observation, stream_position)
        reused = tuple(
            sorted(
                {
                    event.digest
                    for event in produced
                    if event.name in DECISION_EVENTS
                }
                & consumed_decisions
            )
        )
        consumed_decisions.update(
            event.digest for event in produced if event.name in DECISION_EVENTS
        )
        evidence.append(
            StepExecutionEvidence(
                scenario_id=world.scenario_id,
                step_index=index,
                operation="observe_cycle",
                authority=authority,
                decision=observation,
                events=produced,
                reused_decision_digests=reused,
                before_state_fingerprint=durable_after_transition,
                after_state_fingerprint=durable_after_observation,
            )
        )
        expected = step["expected"]

        checks.append(
            Check(
                "scheduling",
                f"{prefix}.outcome",
                observation.outcome == expected["outcome"],
                f"expected {expected['outcome']!r}, observed {observation.outcome!r}",
            )
        )

        if "task_id" in expected:
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.task_id",
                    observation.task_id == expected["task_id"],
                    f"expected {expected['task_id']}, observed {observation.task_id}",
                )
            )

        if expected.get("require_worker_id"):
            worker_id = str(observation.worker_id or "").strip()
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.require_worker_id",
                    bool(worker_id),
                    (
                        "a launch must carry an observed non-empty worker ID; the "
                        f"harness never invents one. observed={observation.worker_id!r}"
                    ),
                )
            )

        if "waited_task_ids" in expected:
            expected_waits = tuple(sorted(normalize_tokens(expected["waited_task_ids"])))
            observed_waits = tuple(sorted(set(observation.waited_task_ids)))
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.waited_task_ids",
                    observed_waits == expected_waits,
                    f"expected {list(expected_waits)}, observed {list(observed_waits)}",
                )
            )

        for conflict in expected.get("conflicts", ()):
            checks.append(_verify_conflict(prefix, conflict, observation))

        if expected.get("forbid_launch"):
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.forbid_launch",
                    observation.outcome not in LAUNCH_OUTCOMES
                    and not observation.worker_id,
                    f"outcome={observation.outcome} worker_id={observation.worker_id}",
                )
            )

        if expected.get("no_human_escalation"):
            category = observation.escalation_category
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.no_human_escalation",
                    category in (None, "none") and observation.outcome != "human_review",
                    (
                        "merge and integration uncertainty must never reach a "
                        f"human; category={category} outcome={observation.outcome}"
                    ),
                )
            )

        if "fingerprint_changed" in expected:
            changed = fingerprint_before != fingerprint_after_transition
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.fingerprint_changed",
                    changed == bool(expected["fingerprint_changed"]),
                    (
                        f"expected changed={expected['fingerprint_changed']}, "
                        f"observed changed={changed}"
                    ),
                )
            )

        if observation.outcome == "start" and observation.task_id:
            worker_id = str(observation.worker_id or "").strip()
            if worker_id:
                world.record_launch(observation.task_id, worker_id)
            else:
                # The world refuses to invent an identity, so an unidentified
                # launch is recorded as a failure rather than being completed
                # with a placeholder the report could later quote.
                checks.append(
                    Check(
                        "scheduling",
                        f"{prefix}.launch_identity",
                        False,
                        (
                            f"{observation.task_id} was launched without an "
                            "observed worker ID, so the assignment cannot be "
                            "recorded; missing evidence is never synthesized"
                        ),
                    )
                )

        if expected.get("distinct_assignment"):
            launched_ids = [entry["task_id"] for entry in world.launched]
            worker_ids = [entry["worker_id"] for entry in world.launched]
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.distinct_assignment",
                    len(launched_ids) == len(set(launched_ids))
                    and len(worker_ids) == len(set(worker_ids))
                    and all(worker_ids),
                    f"assignments={launched_ids} workers={worker_ids}",
                )
            )

        if expected.get("forbid_durable_mutation"):
            durable_after_cycle = world.durable_state_fingerprint()
            checks.append(
                Check(
                    "scheduling",
                    f"{prefix}.forbid_durable_mutation",
                    len(world.launched) == launches_before
                    and durable_after_cycle == durable_after_transition,
                    (
                        "a WAIT must not launch, claim, or change any durable state. "
                        f"launches before={launches_before} after={len(world.launched)}; "
                        f"durable state {durable_after_transition[:12]} -> "
                        f"{durable_after_cycle[:12]} (source HEAD/tree/branches, every "
                        "checkout's status, launched assignments, resume claim and "
                        "observed reservations)"
                    ),
                )
            )
    return checks, evidence


def _verify_conflict(
    prefix: str, expected: Mapping[str, Any], observation: CycleObservation
) -> Check:
    candidate = expected["candidate_task_id"]
    other = expected["conflicting_task_id"]
    name = f"{prefix}.conflict[{candidate}->{other}]"
    matches = [
        conflict
        for conflict in observation.conflicts
        if conflict.candidate_task_id == candidate
        and conflict.conflicting_task_id == other
    ]
    if not matches:
        return Check(
            "scheduling",
            name,
            False,
            "no conflict was reported between the declared pair; observed "
            + str([conflict.to_dict() for conflict in observation.conflicts]),
        )
    conflict = matches[0]
    if conflict.kind != expected["kind"]:
        return Check(
            "scheduling",
            name,
            False,
            f"expected kind {expected['kind']!r}, observed {conflict.kind!r}",
        )
    expected_on = set(normalize_tokens(expected["on"]))
    observed_on = set(conflict.overlapping_values)
    return Check(
        "scheduling",
        name,
        expected_on <= observed_on,
        f"expected overlap {sorted(expected_on)}; observed {sorted(observed_on)}",
    )


# ---------------------------------------------------------------------------
# Layer 2A: acceptance evidence, derived not declared
# ---------------------------------------------------------------------------

def verify_step_evidence(
    scenario: Mapping[str, Any], evidence: Sequence[StepExecutionEvidence]
) -> list[Check]:
    """Grade every manifest step against ONLY that step's own frozen events.

    This is what makes an acceptance PASS mean something. A ``CycleObservation``
    summary is a convenience; the authority is the event slice that one
    ``observe_cycle`` call produced. Three properties matter and each is checked
    here rather than assumed:

    - a step with no matching event proves nothing, so a correct-looking
      decision summary with an empty slice fails;
    - an event belongs to exactly one step, so a later launch can never satisfy
      an earlier one;
    - a poll is graded only when its own lifecycle is complete, so a truncated
      or interleaved record is a failure rather than a partial credit.

    The function is pure: it takes frozen records and returns checks. It cannot
    emit a status, so exposing it for tests grants no acceptance authority.
    """

    checks: list[Check] = []
    steps = list(scenario.get("steps") or ())
    scenario_tasks = set(manifest_module.scenario_task_ids(scenario))
    by_index = {record.step_index: record for record in evidence}
    checks.append(
        Check(
            "acceptance",
            "evidence.step_coverage",
            len(evidence) == len(steps)
            and sorted(by_index) == [int(step["step"]) for step in steps],
            (
                f"a real acceptance run must produce one evidence record per "
                f"manifest step; expected {[int(s['step']) for s in steps]}, "
                f"observed {sorted(by_index)}"
            ),
        )
    )

    seen_polls: set[str] = set()
    seen_poll_indexes: set[Any] = set()
    scheduler_ids: set[str] = set()
    for step in steps:
        index = int(step["step"])
        expected = step["expected"]
        prefix = f"step{index}.evidence"
        record = by_index.get(index)
        if record is None:
            checks.append(
                Check(
                    "acceptance",
                    f"{prefix}.present",
                    False,
                    "no evidence record was captured for this step; missing "
                    "evidence is never synthesized",
                )
            )
            continue

        checks.extend(_verify_event_shape(prefix, record))
        poll_id, lifecycle_checks = _verify_poll_lifecycle(
            prefix, record, expected, seen_polls, seen_poll_indexes
        )
        checks.extend(lifecycle_checks)
        checks.extend(
            _verify_event_binding(prefix, record, scenario_tasks, scheduler_ids, poll_id)
        )
        checks.extend(_verify_step_decision(prefix, record, expected))

        checks.append(
            Check(
                "acceptance",
                f"{prefix}.events_are_this_step's",
                not record.reused_decision_digests,
                (
                    "a decision event that already graded an earlier step cannot "
                    "prove this one; reused "
                    f"{[digest[:12] for digest in record.reused_decision_digests]}"
                ),
            )
        )
        if expected.get("forbid_durable_mutation"):
            checks.append(
                Check(
                    "acceptance",
                    f"{prefix}.durable_state_unchanged",
                    record.before_state_fingerprint == record.after_state_fingerprint,
                    (
                        "the observed cycle changed durable state: "
                        f"{record.before_state_fingerprint[:12]} -> "
                        f"{record.after_state_fingerprint[:12]}"
                    ),
                )
            )
    return checks


def _verify_event_shape(prefix: str, record: StepExecutionEvidence) -> list[Check]:
    """Fail closed on an unknown event type or a missing required field."""

    unknown = sorted(
        {event.name for event in record.events if event.name not in ACCEPTANCE_EVENT_FIELDS}
    )
    incomplete = [
        f"{event.name}{list(event.missing_fields())}"
        for event in record.events
        if event.missing_fields()
    ]
    return [
        Check(
            "acceptance",
            f"{prefix}.known_events",
            not unknown,
            f"unknown event types {unknown}; allowed {sorted(ACCEPTANCE_EVENT_FIELDS)}",
        ),
        Check(
            "acceptance",
            f"{prefix}.required_event_fields",
            not incomplete,
            f"events missing required fields: {incomplete}",
        ),
    ]


def _verify_poll_lifecycle(
    prefix: str,
    record: StepExecutionEvidence,
    expected: Mapping[str, Any],
    seen_polls: set[str],
    seen_poll_indexes: set[Any],
) -> tuple[str | None, list[Check]]:
    """Require one complete, uniquely identified poll inside this step's slice."""

    started = [event for event in record.events if event.name == EVENT_POLL_STARTED]
    finished = [event for event in record.events if event.name == EVENT_POLL_FINISHED]
    complete = (
        len(started) == 1
        and len(finished) == 1
        and started[0].get("poll_id")
        and started[0].get("poll_id") == finished[0].get("poll_id")
        and started[0].get("poll_index") == finished[0].get("poll_index")
    )
    checks = [
        Check(
            "acceptance",
            f"{prefix}.poll_lifecycle",
            bool(complete),
            (
                "a graded step needs exactly one poll_started and one matching "
                f"terminal poll_finished; observed {len(started)} started and "
                f"{len(finished)} finished"
            ),
        )
    ]
    poll_id = str(started[0].get("poll_id")) if complete else None
    poll_index = started[0].get("poll_index") if complete else None
    checks.append(
        Check(
            "acceptance",
            f"{prefix}.distinct_poll",
            bool(complete)
            and poll_id not in seen_polls
            and poll_index not in seen_poll_indexes,
            (
                f"each step must be a different poll; poll_id={poll_id!r} "
                f"poll_index={poll_index!r} already graded an earlier step"
            ),
        )
    )
    if complete:
        seen_polls.add(str(poll_id))
        seen_poll_indexes.add(poll_index)
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.terminal_outcome",
                finished[0].get("outcome") == expected["outcome"]
                and record.decision.outcome == expected["outcome"],
                (
                    f"the terminal poll event must record the observed outcome; "
                    f"expected {expected['outcome']!r}, poll_finished recorded "
                    f"{finished[0].get('outcome')!r}, summary said "
                    f"{record.decision.outcome!r}"
                ),
            )
        )
    return poll_id, checks


def _verify_event_binding(
    prefix: str,
    record: StepExecutionEvidence,
    scenario_tasks: set[str],
    scheduler_ids: set[str],
    poll_id: str | None,
) -> list[Check]:
    """Bind every event in the slice to one scheduler, one poll, one scenario."""

    observed_schedulers = {
        str(event.get("scheduler_id"))
        for event in record.events
        if event.get("scheduler_id")
    }
    scheduler_ids.update(observed_schedulers)
    foreign_tasks = sorted(
        {
            str(event.get("task_id"))
            for event in record.events
            if event.get("task_id") and str(event.get("task_id")) not in scenario_tasks
        }
    )
    mismatched_polls = sorted(
        {
            f"{event.name}:{event.get('poll_id')!r}"
            for event in record.events
            if "poll_id" in ACCEPTANCE_EVENT_FIELDS.get(event.name, frozenset())
            and str(event.get("poll_id")) != str(poll_id)
        }
    )
    return [
        Check(
            "acceptance",
            f"{prefix}.one_scheduler_identity",
            len(observed_schedulers) == 1 and len(scheduler_ids) == 1,
            (
                "every event in a step must come from one scheduler session; this "
                f"step observed {sorted(observed_schedulers)} and the run so far "
                f"observed {sorted(scheduler_ids)}"
            ),
        ),
        Check(
            "acceptance",
            f"{prefix}.scenario_task_binding",
            not foreign_tasks,
            (
                f"events named {foreign_tasks}, which this scenario never declares; "
                f"declared tasks are {sorted(scenario_tasks)}"
            ),
        ),
        Check(
            "acceptance",
            f"{prefix}.poll_correlation",
            poll_id is not None and not mismatched_polls,
            f"events outside this step's poll {poll_id!r}: {mismatched_polls}",
        ),
    ]


def _verify_step_decision(
    prefix: str, record: StepExecutionEvidence, expected: Mapping[str, Any]
) -> list[Check]:
    """Require the exact decision event this step's expectation implies."""

    checks: list[Check] = []
    launches = [
        event for event in record.events if event.name == EVENT_WORKER_LAUNCHED
    ]
    waits = [event for event in record.events if event.name == EVENT_CANDIDATE_WAITED]
    escalations = [event for event in record.events if event.name == EVENT_HUMAN_REVIEW]
    outcome = str(expected["outcome"])

    if outcome == "start":
        task_id = str(expected.get("task_id", ""))
        matching = [event for event in launches if str(event.get("task_id")) == task_id]
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.launch_event",
                len(launches) == 1 and len(matching) == 1,
                (
                    f"a START must emit exactly one worker_launched event for "
                    f"{task_id} inside this step; observed "
                    f"{[str(event.get('task_id')) for event in launches]}"
                ),
            )
        )
        for event in matching:
            worker_id = str(event.get("worker_id", "")).strip()
            argv = [str(item) for item in event.get("argv", ()) or ()]
            checks.append(
                Check(
                    "acceptance",
                    f"{prefix}.launch_identity[{task_id}]",
                    bool(worker_id),
                    (
                        "a launch must carry an observed non-empty worker ID; "
                        "missing identity is UNPROVEN, never synthesized. "
                        f"worker_id={event.get('worker_id')!r}"
                    ),
                )
            )
            checks.append(
                Check(
                    "acceptance",
                    f"{prefix}.launch_argv[{task_id}]",
                    _argv_binds(argv, "--task-id", task_id)
                    and _argv_binds(argv, "--worker-id", worker_id),
                    f"argv must carry the exact task and worker IDs; got {argv}",
                )
            )
    else:
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.no_contradictory_launch",
                not launches,
                (
                    f"a {outcome} step must emit no worker_launched event; observed "
                    f"{[str(event.get('task_id')) for event in launches]}"
                ),
            )
        )

    for task_id in expected.get("waited_task_ids", ()) or ():
        matching = [
            event for event in waits if str(event.get("task_id")) == str(task_id)
        ]
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.wait_event[{task_id}]",
                len(matching) >= 1,
                (
                    f"a WAIT for {task_id} must emit a structured candidate_waited "
                    "event inside this step. A decision summary alone is never "
                    f"sufficient; observed waits "
                    f"{[str(event.get('task_id')) for event in waits]}"
                ),
            )
        )

    for conflict in expected.get("conflicts", ()) or ():
        candidate = str(conflict["candidate_task_id"])
        other = str(conflict["conflicting_task_id"])
        declared = set(normalize_tokens(conflict["on"]))
        matching = [
            event
            for event in waits
            if str(event.get("task_id")) == candidate
            and str(event.get("conflicting_task_id")) == other
            and str(event.get("wait_kind")) == str(conflict["kind"])
        ]
        observed_values = {
            str(value)
            for event in matching
            for value in (event.get("overlapping_values") or ())
        }
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.wait_conflict[{candidate}->{other}]",
                bool(matching) and declared <= observed_values,
                (
                    f"the wait event must name kind {conflict['kind']!r} and the "
                    f"exact overlapping values {sorted(declared)}; observed "
                    f"{sorted(observed_values)} across {len(matching)} matching "
                    "wait events"
                ),
            )
        )

    if outcome == "human_review":
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.escalation_event",
                len(escalations) == 1,
                (
                    "a HUMAN_REVIEW step must emit exactly one structured "
                    f"escalation event; observed {len(escalations)}"
                ),
            )
        )
    else:
        checks.append(
            Check(
                "acceptance",
                f"{prefix}.no_unexpected_escalation",
                not escalations,
                (
                    f"a {outcome} step must not escalate; observed "
                    f"{[str(event.get('escalation_category')) for event in escalations]}"
                ),
            )
        )
    return checks


def _verify_evidence_authority(
    evidence: Sequence[StepExecutionEvidence],
) -> list[Check]:
    """Refuse to grade anything that did not come from the real adapter."""

    foreign = sorted(
        {
            f"step{record.step_index}:{record.authority}"
            for record in evidence
            if record.authority != EVIDENCE_AUTHORITY_REAL
        }
    )
    return [
        Check(
            "acceptance",
            "evidence.authority",
            bool(evidence) and not foreign,
            (
                "acceptance may only be derived from evidence the verifier "
                f"collected from the real adapter; observed {foreign or 'none'}"
            ),
        )
    ]


def _argv_binds(argv: Sequence[str], flag: str, value: str) -> bool:
    if not value:
        return False
    for index, item in enumerate(argv[:-1]):
        if item == flag and argv[index + 1] == value:
            return True
    return False


def _verify_singleton_operation(
    scenario: Mapping[str, Any],
    world: sw.ScenarioWorld,
    observation: SingletonObservation,
) -> list[Check]:
    """Require a real, correlated two-scheduler contest, not two lock strings.

    Two schedulers that merely reported different identities prove nothing. The
    contest must be one event pair: the same lock identity, path and checkout
    root on both sides, one correlating contest ID, exactly one acquisition, at
    least one rejection that names the actual holder, and a loser that launched
    nothing.
    """

    expected = scenario["operation"]["expected"]
    acquired = [
        event for event in observation.events if event.name == EVENT_LOCK_ACQUIRED
    ]
    rejected = [
        event for event in observation.events if event.name == EVENT_LOCK_REJECTED
    ]
    contest_ids = {
        str(event.get("contest_id"))
        for event in (*acquired, *rejected)
        if event.get("contest_id")
    }
    lock_facts = {
        (
            str(event.get("lock_identity")),
            str(event.get("lock_path")),
            str(event.get("checkout_root")),
        )
        for event in (*acquired, *rejected)
    }
    checks = [
        Check(
            "acceptance",
            "singleton.contest_events",
            len(acquired) == 1 and len(rejected) >= 1,
            (
                "a singleton proof needs the contest's own records: exactly one "
                f"{EVENT_LOCK_ACQUIRED} and at least one {EVENT_LOCK_REJECTED}; "
                f"observed {len(acquired)} and {len(rejected)}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.one_lock_authority",
            len(lock_facts) == 1,
            (
                "both schedulers must contest the same lock identity, path and "
                f"checkout root; observed {sorted(lock_facts)}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.correlated_contest",
            len(contest_ids) == 1,
            (
                "the acquisition and the rejection must carry one correlating "
                f"contest ID; observed {sorted(contest_ids)}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.holder_matches_events",
            bool(acquired)
            and str(acquired[0].get("scheduler_id")) == observation.holder_scheduler_id
            and all(
                str(event.get("holder_scheduler_id")) == observation.holder_scheduler_id
                and str(event.get("scheduler_id")) != observation.holder_scheduler_id
                for event in rejected
            ),
            (
                "the reported holder must be the scheduler the events show "
                f"acquiring the lock; holder={observation.holder_scheduler_id!r} "
                f"acquired_by="
                f"{[str(event.get('scheduler_id')) for event in acquired]} "
                f"rejected="
                f"{[str(event.get('scheduler_id')) for event in rejected]}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.lock_covers_this_world",
            bool(observation.checkout_root)
            and Path(observation.checkout_root) == world.checkout_root,
            (
                "the contested lock must be the one keyed by this world's checkout "
                f"root {world.checkout_root}; observed "
                f"{observation.checkout_root!r}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.distinct_scheduler_ids",
            bool(observation.holder_scheduler_id)
            and bool(observation.rejected_scheduler_id)
            and observation.holder_scheduler_id != observation.rejected_scheduler_id,
            (
                f"holder={observation.holder_scheduler_id!r} "
                f"rejected={observation.rejected_scheduler_id!r} on lock "
                f"{observation.lock_identity!r}"
            ),
        ),
        Check(
            "acceptance",
            "singleton.rejected_launched_nothing",
            not observation.rejected_launched_task_ids
            and not [
                event
                for event in observation.events
                if event.name == EVENT_WORKER_LAUNCHED
                and str(event.get("scheduler_id"))
                in {str(item.get("scheduler_id")) for item in rejected}
            ],
            (
                "the rejected scheduler referenced "
                f"{list(observation.rejected_launched_task_ids)} and must emit no "
                "launch event of its own"
            ),
        ),
    ]
    if expected.get("forbid_durable_mutation"):
        checks.append(
            Check(
                "acceptance",
                "singleton.forbid_durable_mutation",
                observation.durable_state_before == observation.durable_state_after,
                (
                    f"durable state {observation.durable_state_before[:12]} -> "
                    f"{observation.durable_state_after[:12]}"
                ),
            )
        )
    return checks


# ---------------------------------------------------------------------------
# Scenario drivers
# ---------------------------------------------------------------------------

def _capability_gap(scenario: Mapping[str, Any], adapter: Any) -> list[str]:
    capabilities = set(adapter.capabilities())
    return sorted(set(scenario.get("required_capabilities") or ()) - capabilities)


def run_fixture_scenario(
    scenario: Mapping[str, Any],
    manifest_data: Mapping[str, Any],
    *,
    fixture_root: FixtureRoot,
) -> ScenarioResult:
    """Layer 1 only. Claims nothing about any scheduler."""

    result = _result(scenario, status=STATUS_FIXTURE_PASS, answered_by="fixture")
    world = sw.build_world(scenario, manifest_data, fixture_root)
    try:
        result.checks.extend(verify_fixture(scenario, world))
        if result.failed_checks:
            result.status = STATUS_FIXTURE_FAIL
        else:
            result.notes.append(
                "fixture verified; no scheduler was run, so nothing is claimed "
                "about scheduling behavior"
            )
        return result
    finally:
        sw.destroy_world(world)


def run_harness_scenario(
    scenario: Mapping[str, Any],
    manifest_data: Mapping[str, Any],
    *,
    adapter: Any,
    fixture_root: FixtureRoot,
) -> ScenarioResult:
    """Layer 2H. A caller-supplied adapter can never reach an acceptance status."""

    result = _result(scenario, status=STATUS_FIXTURE_PASS, answered_by="harness")
    world = sw.build_world(scenario, manifest_data, fixture_root)
    try:
        result.checks.extend(verify_fixture(scenario, world))
        if result.failed_checks:
            result.status = STATUS_FIXTURE_FAIL
            return result

        if "operation" in scenario:
            result.status = STATUS_PENDING
            result.notes.append(
                "this scenario is a dedicated multi-scheduler operation. A single "
                "scripted cycle cannot prove an OS lock, so the harness reports "
                "PENDING rather than agreeing with itself"
            )
            return result

        missing = _capability_gap(scenario, adapter)
        if missing:
            result.status = STATUS_PENDING
            result.notes.append(
                "adapter does not provide required capabilities: " + ", ".join(missing)
            )
            return result

        try:
            result.checks.extend(verify_scheduling(scenario, world, adapter))
        except (UnsupportedScenario, sw.AcceptanceFixtureError) as exc:
            result.status = STATUS_HARNESS_FAIL
            result.notes.append(str(exc))
            return result

        result.status = (
            STATUS_HARNESS_FAIL if result.failed_checks else STATUS_HARNESS_PASS
        )
        result.notes.append(
            "answered by a harness adapter. This exercises the fixture, the "
            "transitions and the checks; it is not architect acceptance and no "
            "capability or identity an adapter declares can change that"
        )
        return result
    finally:
        sw.destroy_world(world)


def run_acceptance_scenario(
    scenario: Mapping[str, Any],
    manifest_data: Mapping[str, Any],
    *,
    fixture_root: FixtureRoot,
) -> ScenarioResult:
    """Layer 2A. The only path that can emit an acceptance status.

    It takes no adapter parameter. The production adapter type is selected here,
    internally, so there is nothing for a caller to substitute.
    """

    adapter = RealPollingArchitectAdapter()
    result = _result(scenario, status=STATUS_FIXTURE_PASS, answered_by="real_scheduler")
    world = sw.build_world(scenario, manifest_data, fixture_root)
    try:
        result.checks.extend(verify_fixture(scenario, world))
        if result.failed_checks:
            result.status = STATUS_FIXTURE_FAIL
            return result

        try:
            missing = _capability_gap(scenario, adapter)
        except AdapterNotWired as exc:
            result.status = STATUS_PENDING
            result.notes.append(str(exc))
            return result
        if missing:
            result.status = STATUS_PENDING
            result.notes.append(
                "the real scheduler does not yet provide: " + ", ".join(missing)
            )
            return result

        try:
            if "operation" in scenario:
                observation = adapter.observe_singleton_contest(world)
                result.checks.extend(
                    _verify_singleton_operation(scenario, world, observation)
                )
            else:
                scheduling_checks, evidence = _execute_steps(
                    scenario, world, adapter
                )
                result.checks.extend(scheduling_checks)
                result.checks.extend(_verify_evidence_authority(evidence))
                result.checks.extend(verify_step_evidence(scenario, evidence))
        except AdapterNotWired as exc:
            result.status = STATUS_PENDING
            result.notes.append(str(exc))
            return result
        except (UnsupportedScenario, sw.AcceptanceFixtureError) as exc:
            result.status = STATUS_FAIL
            result.notes.append(str(exc))
            return result

        result.status = STATUS_FAIL if result.failed_checks else STATUS_PASS
        return result
    finally:
        sw.destroy_world(world)


# ---------------------------------------------------------------------------
# Harness adapter construction
# ---------------------------------------------------------------------------

class _ManifestReplayAdapter(ScriptedAdapter):
    """Replays a scenario's own declared expectations.

    Agreement is tautological by construction and is reported as HARNESS_PASS
    for exactly that reason. Its value is coverage: it drives fixture
    construction, transitions, durable-state snapshots and every check in
    ``verify_scheduling`` end to end, so a break in the plumbing is caught here
    rather than during a live proof.
    """

    def __init__(self, scenario: Mapping[str, Any]) -> None:
        super().__init__(
            _scripted_observations(scenario),
            capabilities=set(scenario.get("required_capabilities") or ()),
        )

    # There is deliberately no `last_observation` here. An earlier draft kept
    # one and graded every step from it, which let a single late launch event
    # stand in for an earlier step that emitted nothing at all.


def _scripted_observations(
    scenario: Mapping[str, Any]
) -> list[CycleObservation]:
    from scheduler_adapter import ConflictObservation

    observations: list[CycleObservation] = []
    for step in scenario.get("steps") or ():
        expected = step["expected"]
        task_id = expected.get("task_id")
        worker_id = (
            f"harness-worker-{task_id}-{step['step']}"
            if expected.get("outcome") == "start"
            else None
        )
        observations.append(
            CycleObservation(
                outcome=expected["outcome"],
                task_id=task_id,
                worker_id=worker_id,
                waited_task_ids=tuple(expected.get("waited_task_ids", ())),
                conflicts=tuple(
                    ConflictObservation(
                        kind=conflict["kind"],
                        candidate_task_id=conflict["candidate_task_id"],
                        conflicting_task_id=conflict["conflicting_task_id"],
                        overlapping_values=tuple(conflict["on"]),
                        reason="scripted replay of the declared expectation",
                    )
                    for conflict in expected.get("conflicts", ())
                ),
            )
        )
    return observations


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def _select(
    manifest_data: Mapping[str, Any], scenario_ids: Sequence[str] | None
) -> list[dict[str, Any]]:
    selected = [
        scenario
        for scenario in manifest_module.scenarios(manifest_data)
        if not scenario_ids or scenario["id"] in set(scenario_ids)
    ]
    if scenario_ids and len(selected) != len(set(scenario_ids)):
        known = {scenario["id"] for scenario in selected}
        raise SystemExit(
            "unknown scenario ids: " + ", ".join(sorted(set(scenario_ids) - known))
        )
    return selected


def _run(
    mode: str,
    *,
    manifest_path: Path | str,
    scenario_ids: Sequence[str] | None,
) -> tuple[list[ScenarioResult], int]:
    manifest_data = manifest_module.load_manifest(manifest_path)
    selected = _select(manifest_data, scenario_ids)
    results: list[ScenarioResult] = []
    parent = create_disposable_parent()
    try:
        for index, scenario in enumerate(selected):
            # Each scenario builds its own fixture root so no scenario can
            # depend on state another scenario left behind.
            fixture_root = create_fixture_root(parent, f"{index:02d}-scenario")
            if mode == "fixtures":
                results.append(
                    run_fixture_scenario(
                        scenario, manifest_data, fixture_root=fixture_root
                    )
                )
            elif mode == "harness":
                results.append(
                    run_harness_scenario(
                        scenario,
                        manifest_data,
                        adapter=_ManifestReplayAdapter(scenario),
                        fixture_root=fixture_root,
                    )
                )
            elif mode == "acceptance":
                results.append(
                    run_acceptance_scenario(
                        scenario, manifest_data, fixture_root=fixture_root
                    )
                )
            else:  # pragma: no cover - guarded by the CLI
                raise SystemExit(f"unknown mode: {mode}")
    finally:
        # Each scenario destroys its own fixture root; the opt-in here only
        # covers a root left registered by a scenario that raised before its own
        # cleanup ran, and each child still goes through the full ownership
        # proof in destroy_fixture_root.
        destroy_disposable_parent(parent, destroy_registered_children=True)
    exit_code = 1 if any(item.status in FAILING_STATUSES for item in results) else 0
    return results, exit_code


def verify_fixtures(
    *,
    manifest_path: Path | str = MANIFEST_PATH,
    scenario_ids: Sequence[str] | None = None,
) -> tuple[list[ScenarioResult], int]:
    return _run("fixtures", manifest_path=manifest_path, scenario_ids=scenario_ids)


def run_harness(
    *,
    manifest_path: Path | str = MANIFEST_PATH,
    scenario_ids: Sequence[str] | None = None,
) -> tuple[list[ScenarioResult], int]:
    return _run("harness", manifest_path=manifest_path, scenario_ids=scenario_ids)


def run_acceptance(
    *,
    manifest_path: Path | str = MANIFEST_PATH,
    scenario_ids: Sequence[str] | None = None,
) -> tuple[list[ScenarioResult], int]:
    return _run("acceptance", manifest_path=manifest_path, scenario_ids=scenario_ids)


def print_report(results: Iterable[ScenarioResult]) -> None:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        print(f"[{result.status}] {result.letter}  {result.scenario_id}")
        print(f"          {result.title}")
        print(f"          readiness: {result.readiness}  answered by: {result.answered_by}")
        for check in result.failed_checks:
            print(f"          [X] {check.layer}/{check.name}: {check.detail}")
        for note in result.notes:
            print(f"          note: {note}")
    print("")
    print(
        "[SUMMARY] "
        + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    )
    if counts.get(STATUS_PASS):
        print(
            "[SUMMARY] PASS was produced by the verifier-owned acceptance path "
            "from structured scheduler events."
        )
    if counts.get(STATUS_HARNESS_PASS):
        print(
            "[SUMMARY] HARNESS_PASS exercises the harness only. It is not "
            "architect acceptance."
        )
    if counts.get(STATUS_PENDING):
        print(
            "[SUMMARY] PENDING_CAPABILITY is not a pass. The capability does not "
            "exist yet."
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Software Architect acceptance scenarios. Fixture "
            "verification runs today; acceptance needs the real scheduler."
        )
    )
    parser.add_argument("--manifest", default=str(MANIFEST_PATH))
    parser.add_argument(
        "--mode",
        default="fixtures",
        choices=["fixtures", "harness", "acceptance"],
        help=(
            "fixtures = layer 1 only; harness = replay the manifest through the "
            "harness plumbing (HARNESS_* only); acceptance = the real scheduler "
            "(PENDING until the adapter is wired)"
        ),
    )
    parser.add_argument("--scenario", action="append", dest="scenarios", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results, exit_code = _run(
        args.mode, manifest_path=args.manifest, scenario_ids=args.scenarios
    )
    if args.json:
        print(
            json.dumps(
                {"mode": args.mode, "results": [item.to_dict() for item in results]},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_report(results)
    return exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
