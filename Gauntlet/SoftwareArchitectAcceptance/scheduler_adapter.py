"""The adapter boundary between this harness and a real polling scheduler.

The acceptance harness must be able to drive the **real** Software Architect
scheduler later without copying its implementation into this branch. That
requires exactly one narrow seam:

```text
observe one scheduling cycle against a prepared world  ->  CycleObservation
```

Everything else the harness needs (the fixture, the manifest, the verifier, the
evidence checks) is independent of who answers that question.

## Adapters have no acceptance authority

This module deliberately contains **no** adapter-kind string, no
self-description, and no way for an adapter to say what its own answer means.
An adapter returns observations; `verify_acceptance.py` decides what they are
worth. Concretely:

- an adapter object handed in by a caller can only ever reach a `HARNESS_*` or
  `PENDING_CAPABILITY` result;
- the acceptance path in `verify_acceptance.py` accepts no adapter parameter at
  all and constructs `RealPollingArchitectAdapter` itself;
- `capabilities()` can only make a scenario *skip*, never *pass*.

There is also no reference implementation of scheduler policy here. An earlier
draft carried one, and an independent audit was right that a second copy of the
WAIT rule is a liability: it invites the harness to grade the scheduler against
the harness author's opinion instead of against the manifest.

## The real adapter is a translation shim over the committed scheduler

`RealPollingArchitectAdapter` drives the committed
`Pipeline/TaskReviewAgent/polling_orchestrator.PollingOrchestrator` through the
injection points that module already exposes:

```text
ScenarioWorld.source_root         -> PollingOrchestrator(source=...)
ScenarioWorld.checkout_root       -> PollingOrchestrator(checkout_root=...)
ScenarioWorld.candidate_queue()   -> plan_builder=...  (fresh Stage-2 rank)
ScenarioWorld.resume_candidate()  -> plan_builder=...  (DispatchPlan.resume)
ScenarioWorld.task(...)           -> task_loader=...
ScenarioWorld.reservations()      -> reservation_observer=...
ScenarioWorld.advisory(...)       -> architect_runner=... (injected advisory;
                                     no provider call, no network)
launch capture                    -> process_factory=... (records argv only)
scheduler events                  -> event_emitter=...  (production records)
```

The scheduler has one plan seam and no separate `resume_source` constructor, so
the injected `plan_builder` is the single place both durable resume authority
and fresh Stage-2 ranking are translated - exactly as Stage 2 hands them over.

Four rules govern the shim:

1. It reimplements no scheduling decision. Every START, WAIT, conflict,
   unknown-surface verdict and admission gate is computed inside
   `PollingOrchestrator` and `architect_preflight`. The shim translates inputs
   and records outputs; it never reads a scenario's expectation. If it ever
   grows a `wait` branch of its own, the acceptance result is measuring the
   shim.
2. `process_factory` records the exact argv and never starts a process. A real
   worker launch belongs to the live proof, not to this harness.
3. `CycleObservation.events` comes from the scheduler's own emitter, with
   **exactly the records that cycle produced**, renamed into this package's
   canonical vocabulary and correlated by `poll_id`. Acceptance is derived from
   those structured events plus Git state, never from a returned decision
   string.
4. Every emitted event carries the required fields listed in
   `ACCEPTANCE_EVENT_FIELDS`, including a `poll_id` that correlates one poll's
   `poll_started`, decision, and `poll_finished` records. A cycle that cannot
   produce that lifecycle is not acceptance evidence; the scenario stays
   `PENDING_CAPABILITY` instead.

Scenario J stays deliberately unwired: `observe_singleton_contest` fails closed
and `capabilities()` never advertises `scheduler_singleton`, because a single
in-process poll cannot prove a two-scheduler OS lock contest.

An adapter may additionally expose `event_log()` returning its cumulative,
append-only event stream. When it does, the acceptance path reads the stream
position before each operation and grades the step on the slice that operation
appended, rather than trusting the adapter's own per-cycle bookkeeping.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from acceptance_lib import OUTCOMES, ROOT, canonical_json, unity_asset_identity
from scenario_world import ScenarioWorld


class AdapterNotWired(RuntimeError):
    """Raised when a real scheduler adapter is requested but unavailable."""


class UnsupportedScenario(RuntimeError):
    """Raised when an adapter cannot answer a scenario at all."""


class EventEvidenceError(RuntimeError):
    """Raised when an emitted event cannot be frozen into step evidence."""


# ---------------------------------------------------------------------------
# Structured observations
# ---------------------------------------------------------------------------

EVENT_POLL_STARTED = "poll_started"
EVENT_POLL_FINISHED = "poll_finished"
EVENT_WORKER_LAUNCHED = "worker_launched"
EVENT_CANDIDATE_WAITED = "candidate_waited"
EVENT_HUMAN_REVIEW = "architect_human_review"
EVENT_RESERVATIONS_OBSERVED = "integration_reservations_observed"
EVENT_LOCK_ACQUIRED = "scheduler_lock_acquired"
EVENT_LOCK_REJECTED = "scheduler_already_active"

ACCEPTANCE_EVENT_FIELDS: dict[str, frozenset[str]] = {
    # event name -> fields the acceptance path requires before it will grade a
    # step from this event. The names match the live-evidence envelope schema so
    # an in-process proof and a recorded live proof describe the same facts.
    EVENT_POLL_STARTED: frozenset({"poll_id", "poll_index", "scheduler_id"}),
    EVENT_POLL_FINISHED: frozenset(
        {"poll_id", "poll_index", "scheduler_id", "outcome"}
    ),
    EVENT_WORKER_LAUNCHED: frozenset(
        {"poll_id", "scheduler_id", "task_id", "worker_id", "argv"}
    ),
    EVENT_CANDIDATE_WAITED: frozenset(
        {"poll_id", "scheduler_id", "task_id", "wait_kind"}
    ),
    EVENT_HUMAN_REVIEW: frozenset(
        {
            "poll_id",
            "scheduler_id",
            "task_id",
            "escalation_category",
            "escalation_question",
        }
    ),
    EVENT_RESERVATIONS_OBSERVED: frozenset(
        {"poll_id", "scheduler_id", "reservations"}
    ),
    EVENT_LOCK_ACQUIRED: frozenset(
        {"scheduler_id", "lock_identity", "lock_path", "checkout_root", "contest_id"}
    ),
    EVENT_LOCK_REJECTED: frozenset(
        {
            "scheduler_id",
            "lock_identity",
            "lock_path",
            "checkout_root",
            "contest_id",
            "holder_scheduler_id",
        }
    ),
}

DECISION_EVENTS = frozenset(
    {EVENT_WORKER_LAUNCHED, EVENT_CANDIDATE_WAITED, EVENT_HUMAN_REVIEW}
)
"""Events that carry a scheduling decision.

These are the records a step is graded against, so they are also the records the
acceptance path refuses to see twice: an event that already proved one step can
never prove another.
"""


@dataclass(frozen=True)
class SchedulerEvent:
    """One immutable, snapshotted record emitted by a scheduler.

    The payload is a private deep copy behind a read-only mapping. Once a step's
    evidence is frozen, nothing the adapter does afterwards - including
    rewriting the object it originally handed back - can change what that step
    was graded on.
    """

    name: str
    payload: Mapping[str, Any]
    digest: str

    @classmethod
    def from_raw(cls, raw: Any) -> "SchedulerEvent":
        if isinstance(raw, SchedulerEvent):
            return raw
        if not isinstance(raw, Mapping):
            raise EventEvidenceError(f"a scheduler event must be a mapping: {raw!r}")
        try:
            snapshot = json.loads(canonical_json(dict(raw)))
        except (TypeError, ValueError) as exc:
            raise EventEvidenceError(
                f"a scheduler event must be JSON-representable: {exc}"
            ) from exc
        name = str(snapshot.get("event", "")).strip()
        if not name:
            raise EventEvidenceError(
                f"a scheduler event must name its type in 'event': {snapshot!r}"
            )
        return cls(
            name=name,
            payload=MappingProxyType(snapshot),
            digest=hashlib.sha256(
                canonical_json(snapshot).encode("utf-8")
            ).hexdigest(),
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.payload[key]

    def __contains__(self, key: object) -> bool:
        return key in self.payload

    def missing_fields(self) -> tuple[str, ...]:
        """Required fields this event does not carry, for its own event type."""

        required = ACCEPTANCE_EVENT_FIELDS.get(self.name)
        if required is None:
            return ()
        return tuple(
            sorted(
                field_name
                for field_name in required
                if field_name not in self.payload
                or self.payload[field_name] in (None, "", [])
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def freeze_events(events: Iterable[Any]) -> tuple[SchedulerEvent, ...]:
    """Snapshot an emitted event sequence into immutable evidence records."""

    return tuple(SchedulerEvent.from_raw(event) for event in events)


@dataclass(frozen=True)
class ConflictObservation:
    """A structured conflict: which pair, on which exact tokens, and why."""

    kind: str
    candidate_task_id: str
    conflicting_task_id: str
    overlapping_values: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "candidate_task_id": self.candidate_task_id,
            "conflicting_task_id": self.conflicting_task_id,
            "overlapping_values": list(self.overlapping_values),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CycleObservation:
    """The structured result of exactly one scheduling cycle.

    ``events`` is the scheduler's own emitted record **for this cycle only**.
    The acceptance path grades each manifest step against that step's own event
    slice, so an adapter that returns the right ``outcome`` string without
    emitting a matching launch event cannot be accepted, and a later cycle's
    event can never be borrowed to satisfy an earlier step.
    """

    outcome: str
    task_id: str | None = None
    worker_id: str | None = None
    launch_argv: tuple[str, ...] = ()
    waited_task_ids: tuple[str, ...] = ()
    conflicts: tuple[ConflictObservation, ...] = ()
    reasons: tuple[str, ...] = ()
    escalation_category: str | None = None
    escalation_question: str | None = None
    events: tuple[SchedulerEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise UnsupportedScenario(f"unknown scheduling outcome: {self.outcome!r}")
        # Accept raw mappings for convenience, but store only frozen snapshots.
        object.__setattr__(self, "events", freeze_events(self.events))

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "launch_argv": list(self.launch_argv),
            "waited_task_ids": list(self.waited_task_ids),
            "conflicts": [item.to_dict() for item in self.conflicts],
            "reasons": list(self.reasons),
            "escalation_category": self.escalation_category,
            "escalation_question": self.escalation_question,
            "events": [item.to_dict() for item in self.events],
        }


@dataclass(frozen=True)
class SingletonObservation:
    """The result of a two-scheduler contest for one checkout-root lock.

    A single ``observe_cycle()`` answer can never prove an OS lock, so scenario
    J uses this dedicated operation instead. An adapter that cannot actually run
    two schedulers must not implement it; the scenario then stays PENDING.
    """

    lock_identity: str
    holder_scheduler_id: str
    rejected_scheduler_id: str
    rejected_launched_task_ids: tuple[str, ...]
    durable_state_before: str
    durable_state_after: str
    lock_path: str = ""
    checkout_root: str = ""
    contest_id: str = ""
    events: tuple[SchedulerEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", freeze_events(self.events))

    def to_dict(self) -> dict[str, Any]:
        return {
            "lock_identity": self.lock_identity,
            "holder_scheduler_id": self.holder_scheduler_id,
            "rejected_scheduler_id": self.rejected_scheduler_id,
            "rejected_launched_task_ids": list(self.rejected_launched_task_ids),
            "durable_state_before": self.durable_state_before,
            "durable_state_after": self.durable_state_after,
            "lock_path": self.lock_path,
            "checkout_root": self.checkout_root,
            "contest_id": self.contest_id,
            "events": [item.to_dict() for item in self.events],
        }


@runtime_checkable
class SchedulerAdapter(Protocol):
    """The only thing the acceptance harness asks of a scheduler."""

    def capabilities(self) -> frozenset[str]:
        """Capabilities this adapter genuinely provides."""

    def observe_cycle(self, world: ScenarioWorld) -> CycleObservation:
        """Observe exactly one scheduling cycle. Must not mutate the world."""


@runtime_checkable
class EventStreamAdapter(Protocol):
    """Optional: an adapter that exposes its cumulative event stream.

    The stream is append-only. The acceptance path records its length before an
    operation and treats everything appended afterwards as that operation's
    evidence, which is why an adapter must never rewrite or reorder it.
    """

    def event_log(self) -> Sequence[Any]: ...


@runtime_checkable
class SingletonCapableAdapter(Protocol):
    """Optional: an adapter that can actually run a two-scheduler contest.

    A conforming implementation must run two real schedulers against one
    checkout root and return the contest's own records: one `lock_acquired`, one
    `lock_rejected`, the same lock identity, path and checkout root on both
    sides, one correlating `contest_id`, and proof that the loser mutated
    nothing. Anything less leaves scenario J `PENDING_CAPABILITY`.
    """

    def observe_singleton_contest(
        self, world: ScenarioWorld
    ) -> SingletonObservation: ...


# ---------------------------------------------------------------------------
# The real adapter: a translation shim over the production polling scheduler
# ---------------------------------------------------------------------------

PRODUCTION_IMPORT_BLOCKER = (
    "The committed polling Software Architect scheduler could not be imported "
    "from Pipeline/TaskReviewAgent, so there is no production behavior to "
    "observe. This adapter fails closed rather than returning a stub answer "
    "that a report could mistake for acceptance evidence."
)

SINGLETON_CONTEST_BLOCKER = (
    "Scenario J is not wired. A singleton contest requires two real schedulers "
    "racing for one checkout-root lock and returning one acquisition, one "
    "rejection, a shared contest identity, proof the loser launched nothing, "
    "and unchanged durable state. The ordinary-cycle adapter observes a single "
    "in-process poll and cannot establish any of that, so scenario J stays "
    "PENDING_CAPABILITY instead of being answered from one cycle."
)

ORDINARY_CYCLE_CAPABILITIES = frozenset(
    {
        "stage2_candidate_selection",
        "integration_reservation_observation",
        "deterministic_conflict_detection",
        "unity_serialized_asset_conflict",
        "unknown_surface_policy",
        "wait_admission_policy",
        "exact_task_id_launch",
        "resume_priority",
        "architect_failure_tolerance",
    }
)
"""Exactly what real production polling answers for one ordinary cycle.

`scheduler_singleton` is deliberately absent: it is the one capability this
slice does not implement, and advertising it would turn scenario J from an
honest PENDING into a fabricated answer.
"""

ACCEPTANCE_SCHEDULER_ID = "software-architect-acceptance-scheduler"

ADAPTER_MAX_WORKERS = 8
"""Local child capacity, set above anything the manifest needs.

The manifest measures admission policy, not queue capacity: scenario A alone
requires two simultaneously active assignments. Leaving capacity generous means
`capacity_full` is never the reason for a decision, so every observed WAIT or
START comes from conflict/admission reasoning.
"""

ADAPTER_MAX_ARCHITECT_INVOCATIONS_PER_POLL = 64
"""Per-poll architect budget, set above anything the manifest needs."""

ADVISORY_ARTIFACT_DIRECTORY = "architect-advisories"
"""Where production advisory artifacts are persisted for a scenario.

It lives directly under the fixture root, which is deliberately *outside* the
synthetic source repository and outside the checkout root. `ScenarioWorld`
snapshots durable state from those two trees only, so writing a real advisory
artifact cannot make a WAIT look like a durable mutation, and the artifacts are
destroyed with the fixture.
"""

POLL_STATUS_OUTCOMES: dict[str, str] = {
    # PollCycleResult.status -> this package's outcome vocabulary. The mapping
    # is total on purpose: an untranslated status raises instead of silently
    # becoming "idle".
    "worker_launched": "start",
    "idle": "idle",
    "capacity_full": "no_launch",
    "architect_budget_exhausted": "no_launch",
    "reservation_observation_wait": "no_launch",
    "dry_run_candidate": "no_launch",
    "worker_failed": "blocked",
    "worker_launch_failed": "blocked",
    "reservation_observation_failed": "blocked",
    "blocked_invalid_state": "blocked",
    "unsupported_plan": "blocked",
    "missing_candidate": "blocked",
    "duplicate_planned_candidate": "blocked",
    "candidate_verification_failed": "blocked",
    "candidate_bound_exceeded": "blocked",
}

PRODUCTION_CONFLICT_KINDS: dict[str, str] = {
    # DeterministicConflict.kind -> manifest.VALID_CONFLICT_KINDS. Pure
    # renaming: the pair, the tokens and the verdict are all production's.
    "exclusive_resource": "exclusive_resource",
    "exact_path_actual": "exact_path_actual",
    "active_predicted_exact_path": "exact_path_predicted",
    "unity_serialized_asset": "unity_asset_identity",
    "active_task_id": "active_task_id",
}

PRODUCTION_DIAGNOSTIC_EVENTS = frozenset(
    {
        # Production events this adapter deliberately does not translate,
        # because each one's scheduling meaning is already carried by a record
        # that *is* translated. The list is exhaustive and narrow on purpose:
        # there is no prefix rule and no wildcard, so a newly added safety,
        # conflict, escalation or lock event is not covered by it and fails
        # closed instead of vanishing from acceptance evidence.
        #
        # "scheduler_blocked" carries the human-readable reason for a non-start
        # poll; the decision itself is `PollCycleResult.status`, which becomes
        # `poll_finished.outcome`.
        "scheduler_blocked",
        # "plan_idle" is the reason for an `idle` status, which is translated.
        "plan_idle",
        # Architect progress markers. The verdict is `architect_wait`,
        # `architect_human_review` or the launch, all of which are translated.
        "architect_started",
        "architect_completed",
        # Resume ordering is already carried by the selected task identity in
        # `worker_launched` and `PollCycleResult`. This marker only explains
        # why production selected that task ahead of fresh candidates.
        "resume_priority_applied",
        # Observability notes about an active assignment's checkout. What the
        # conflict policy actually consumes is the reservation's
        # `surface_unknown` flag and its paths, which reach evidence through
        # `integration_reservations_observed`.
        "active_checkout_observation_pending",
        "active_checkout_surface_unknown",
        # Bounded reservation-observation failure/recovery bookkeeping. The
        # scheduling consequence is the `reservation_observation_wait` or
        # `reservation_observation_failed` status.
        "scheduler_wait_observation_failure",
        "scheduler_observation_recovered",
        # The fixture pins a clean source HEAD through its injected read-only
        # refresher; this record confirms that observation and has no separate
        # admission meaning beyond the later poll result.
        "source_main_refreshed",
        # Worker reaping records. A worker this harness launched is passive and
        # never exits, and a failed launch is reported by the poll status.
        "worker_finished",
        "worker_failed",
    }
)
"""Production events that are intentionally diagnostic, not evidence.

`scheduler_started`, `scheduler_stopped` and `scheduler_locked_out` are
deliberately **absent**. They belong to `PollingOrchestrator.run()` rather than
`poll_once()`, and `scheduler_locked_out` is the singleton record scenario J
would need. Seeing any of them from an ordinary cycle means this adapter is
observing something it does not model, so it must fail closed rather than be
excused by a broad rule.
"""

UNKNOWN_PRODUCTION_EVENT_BLOCKER = (
    "The scheduler emitted a production event this adapter neither translates "
    "into canonical evidence nor names in PRODUCTION_DIAGNOSTIC_EVENTS. "
    "Discarding it would let a new safety, conflict, escalation or lock record "
    "disappear from acceptance evidence while every evidence check still "
    "passed, so the adapter fails closed and the scenario cannot reach PASS."
)

PRODUCTION_LAUNCH_STATUS = "worker_launched"
"""The `PollCycleResult.status` that must accompany exactly one launch record."""

LAUNCH_ARGV_TASK_FLAG = "--task-id"
LAUNCH_ARGV_WORKER_FLAG = "--worker-id"

PRODUCTION_WAIT_EVENTS: dict[str, str | None] = {
    # production event -> wait_kind, or None when the kind comes from the
    # event's own conflict_kind field.
    "candidate_skipped_hard_conflict": None,
    "candidate_skipped_resource_conflict": None,
    "candidate_wait_unknown_surface": "unknown_surface_not_provably_disjoint",
    "architect_wait": "architect_unusable",
    # The reviewed live-evidence wait vocabulary does not yet name a routing
    # wait. It is surfaced under an explicit kind rather than dropped, so a
    # routing wait can never be mistaken for "no candidate waited".
    "execution_route_wait": "execution_route_unusable",
}


class _EventCaptureStream:
    """Collect the production emitter's own JSON lines instead of printing them.

    The scheduler is given a real `JsonEventEmitter`, so every record graded
    here is byte-for-byte the record production would have written to stdout.
    """

    def __init__(self) -> None:
        self.text = ""

    def write(self, value: str) -> int:
        text = str(value)
        self.text += text
        return len(text)

    def flush(self) -> None:
        return None

    def records(self) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in self.text.split("\n") if line.strip()
        ]


class _PassiveWorkerProcess:
    """The smallest object the scheduler's own reaping code accepts.

    It is not a process. `pid` is `None` because there is no process to name,
    and `poll()` reports "still running" so the assignment stays active for the
    rest of the scenario exactly as a real worker's would.
    """

    pid = None
    returncode = None

    def poll(self) -> None:
        return None


class _PassiveProcessFactory:
    """Record the exact argv production tried to launch; start nothing."""

    def __init__(self) -> None:
        self.launches: list[dict[str, Any]] = []

    def __call__(self, command: Any, **options: Any) -> _PassiveWorkerProcess:
        if options.get("shell"):
            raise UnsupportedScenario(
                "the acceptance adapter refuses a shell launch request"
            )
        self.launches.append(
            {
                "argv": tuple(str(item) for item in command),
                "cwd": str(options.get("cwd", "")),
            }
        )
        return _PassiveWorkerProcess()


def _agreed_identity(subject: str, claims: Mapping[str, Any]) -> str:
    """The one identity every production claim agrees on, or fail closed.

    Every claim must be present and non-empty: a missing identity is UNPROVEN,
    never filled in from a sibling record. Two different values are a
    contradiction, and this function has no tie-breaker by design.
    """

    observed: dict[str, str] = {}
    for where, value in claims.items():
        text = "" if value is None else str(value).strip()
        if not text:
            raise EventEvidenceError(
                f"a production launch carries no {subject} identity in {where}; "
                "a missing identity is UNPROVEN and is never synthesized"
            )
        observed[where] = text
    distinct = sorted(set(observed.values()))
    if len(distinct) != 1:
        raise EventEvidenceError(
            f"production launch {subject} identity disagrees across its own "
            f"records: {observed}"
        )
    return distinct[0]


def _argv_flag_values(argv: Sequence[str], flag: str) -> tuple[str, ...]:
    """Every value production bound to ``flag``, in argv order.

    All occurrences are returned rather than the first, so an argv that binds
    one flag twice is visible as a contradiction instead of quietly resolving
    to whichever value happens to come first.
    """

    items = [str(item) for item in argv]
    return tuple(
        items[index + 1] for index in range(len(items) - 1) if items[index] == flag
    )


@dataclass(frozen=True)
class _ProductionScheduler:
    """The committed modules this adapter observes."""

    orchestrator: Any
    preflight: Any
    dispatch: Any


_PRODUCTION: dict[str, _ProductionScheduler] = {}


def _production() -> _ProductionScheduler:
    """Import the committed scheduler, or fail closed.

    The import is lazy so that a missing or broken production module leaves the
    acceptance path PENDING instead of breaking the fixture and harness layers,
    which make no claim about the scheduler at all.
    """

    cached = _PRODUCTION.get("modules")
    if cached is not None:
        return cached
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from Pipeline.TaskReviewAgent import architect_preflight
        from Pipeline.TaskReviewAgent import dispatch_plan
        from Pipeline.TaskReviewAgent import polling_orchestrator
    except Exception as exc:  # pragma: no cover - environment failure path
        raise AdapterNotWired(
            f"{PRODUCTION_IMPORT_BLOCKER} ({type(exc).__name__}: {exc})"
        ) from exc
    modules = _ProductionScheduler(
        orchestrator=polling_orchestrator,
        preflight=architect_preflight,
        dispatch=dispatch_plan,
    )
    _PRODUCTION["modules"] = modules
    return modules


class RealPollingArchitectAdapter:
    """The one adapter the acceptance path is allowed to construct.

    It is instantiated by `verify_acceptance.py` itself, never handed in by a
    caller, and it takes no constructor argument: there is deliberately no seam
    through which a caller could substitute a scheduler. Every scheduling
    decision it reports is computed by `PollingOrchestrator` and
    `architect_preflight`; this class only translates a `ScenarioWorld` into the
    inputs those modules already accept and translates their emitted records
    back into this package's canonical evidence shapes.
    """

    def __init__(self) -> None:
        self.scheduler_id = ACCEPTANCE_SCHEDULER_ID
        self.orchestrator: Any = None
        self.process_factory = _PassiveProcessFactory()
        self.events = _EventCaptureStream()
        self._world: ScenarioWorld | None = None
        self._artifact_root: Path | None = None
        self._canonical_events: list[dict[str, Any]] = []
        self._production_events: list[dict[str, Any]] = []
        self._validated_advisories: dict[str, Any] = {}
        # Retained launch identity. Once a worker ID has been observed bound to
        # a task ID and an argv, that binding is permanent for this adapter: a
        # later poll may not re-bind the same worker to different work.
        self._launch_task_by_worker: dict[str, str] = {}
        self._launch_argv_by_worker: dict[str, tuple[str, ...]] = {}
        self._captured_launch_count = 0
        self._poll_index = 0
        self._analysis_index = 0
        self._clock = 0.0

    # -- adapter protocol ------------------------------------------------

    def capabilities(self) -> frozenset[str]:
        _production()
        return ORDINARY_CYCLE_CAPABILITIES

    def observe_cycle(self, world: ScenarioWorld) -> CycleObservation:
        production = _production()
        orchestrator = self._ensure_orchestrator(world, production)
        self._poll_index += 1
        poll_index = self._poll_index
        poll_id = f"{self.scheduler_id}-poll-{poll_index:04d}"
        # A deterministic monotonic clock keeps the architect re-analysis
        # interval reproducible; it advances one unit per poll, which is
        # conservative because it can only keep a cooldown active.
        self._clock += 1.0
        before = len(self.events.records())
        result = orchestrator.poll_once()
        produced = self.events.records()[before:]
        self._production_events.extend(produced)
        records = self._canonical_records(
            produced, poll_id=poll_id, poll_index=poll_index, result=result
        )
        # Cross-bind before anything downstream can read the stream, so a poll
        # whose launch identity contradicts itself never becomes evidence.
        self._bind_launch_identity(records, produced=produced, result=result)
        self._canonical_events.extend(records)
        return self._observation(records, result)

    def observe_singleton_contest(self, world: ScenarioWorld) -> SingletonObservation:
        raise AdapterNotWired(SINGLETON_CONTEST_BLOCKER)

    def event_log(self) -> Sequence[Any]:
        """The cumulative, append-only canonical event stream."""

        return list(self._canonical_events)

    def production_event_log(self) -> Sequence[Any]:
        """Every production record, including the ones with no canonical name.

        Diagnostics only. The acceptance path never reads this, but a record
        that has no canonical counterpart is kept here rather than discarded.
        """

        return list(self._production_events)

    # -- production construction -----------------------------------------

    def _ensure_orchestrator(
        self, world: ScenarioWorld, production: _ProductionScheduler
    ) -> Any:
        if self.orchestrator is not None:
            if self._world is not world:
                raise UnsupportedScenario(
                    "one adapter observes exactly one world; scheduler state "
                    "from another scenario is never reused"
                )
            return self.orchestrator
        self._world = world
        self._artifact_root = world.fixture_root.path / ADVISORY_ARTIFACT_DIRECTORY
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        self.orchestrator = production.orchestrator.PollingOrchestrator(
            source=world.source_root,
            checkout_root=world.checkout_root,
            scheduler_id=self.scheduler_id,
            execution_provider=None,
            model=None,
            max_turns=None,
            max_workers=ADAPTER_MAX_WORKERS,
            architect_min_confidence=(
                production.preflight.DEFAULT_ARCHITECT_MIN_CONFIDENCE
            ),
            architect_runner=self._architect_runner,
            routing_policy=production.orchestrator.load_execution_routing_policy(
                environment={}
            ),
            max_architect_invocations_per_poll=(
                ADAPTER_MAX_ARCHITECT_INVOCATIONS_PER_POLL
            ),
            plan_builder=self._build_plan,
            task_loader=self._load_task,
            reservation_observer=self._observe_reservations,
            source_refresher=lambda _source: {
                "before": world.source_head(),
                "after": world.source_head(),
                "changed": False,
            },
            process_factory=self.process_factory,
            event_emitter=production.orchestrator.JsonEventEmitter(self.events),
            monotonic_clock=lambda: self._clock,
        )
        return self.orchestrator

    # -- input translation -----------------------------------------------

    def _require_world(self) -> ScenarioWorld:
        world = self._world
        if world is None:
            raise UnsupportedScenario("no scenario world is bound to this adapter")
        return world

    def _load_task(self, task_id: str) -> dict[str, Any]:
        return self._require_world().task(str(task_id))

    def _build_plan(
        self,
        *,
        source: Any = None,
        worker_id: str = "",
        excluded_task_ids: Iterable[str] | None = None,
        **_unused: Any,
    ) -> Any:
        """Translate the world's Stage-2 authority into a `DispatchPlan`.

        Both halves live here because the scheduler has one plan seam and no
        separate resume source: `resume_candidate()` becomes `DispatchPlan.resume`
        and `candidate_queue()` becomes the fresh ranked pool, in the exact order
        the manifest declares. Ranking is Stage-2's answer, not this adapter's.
        """

        production = _production()
        world = self._require_world()
        excluded = {str(task_id) for task_id in (excluded_task_ids or ())}
        resume_task_id = world.resume_candidate()
        resume: dict[str, Any] | None = None
        if resume_task_id is not None and resume_task_id not in excluded:
            authority = world.resume_authority
            resume = {
                "task_id": resume_task_id,
                "issue_number": None,
                "issue_url": None,
                "phase": authority.phase if authority else None,
                "branch": None,
                "commit": None,
                "human_result": None,
            }
        ranked = tuple(
            self._candidate_record(world, task_id)
            for task_id in world.candidate_queue()
            if task_id not in excluded
        )
        if resume is not None:
            decision = "resume_existing"
        elif ranked:
            decision = "fresh_candidate"
        else:
            decision = "no_safe_work"
        return production.dispatch.DispatchPlan(
            schema_version=production.dispatch.DISPATCH_PLAN_SCHEMA_VERSION,
            source_commit=world.source_head(),
            mode="read_only_plan",
            autonomous_dispatch=False,
            decision=decision,
            resume=resume,
            selected_fresh_candidate=dict(ranked[0]) if ranked else None,
            ranked_eligible_candidates=ranked,
            skipped_candidates=(),
            agent_ready_count=1 if resume is not None else 0,
            claim_observation={"status": "not_consulted"},
            reasons=(),
            excluded_task_ids=tuple(sorted(excluded)),
        )

    @staticmethod
    def _candidate_record(world: ScenarioWorld, task_id: str) -> dict[str, Any]:
        task = world.task(task_id)
        return {
            "task_id": task_id,
            "eligible": True,
            "reason_codes": [],
            "title": task.get("title"),
            "derived_state": None,
            "kind": None,
            "execution_scope": None,
            "decomposition_state": None,
            "contract_disposition": None,
            "exclusive_resources": list(task.get("exclusive_resources") or ()),
            "depends_on": [],
            "dependency_observations": [],
            "task_contract_sha256": task.get("task_contract_sha256"),
        }

    def _observe_reservations(self) -> tuple[Any, ...]:
        """Translate observed fixture reservations into scheduler reservations.

        Every conflict-relevant field survives: actual paths, predicted paths,
        exclusive-resource tokens, Unity serialized assets, human-held branch
        identity and `surface_unknown`. An unobservable surface stays UNKNOWN
        rather than becoming "no paths".

        Assignments this scheduler launched itself are skipped, because the
        orchestrator already contributes them from its own `ActiveAssignment`
        records; passing them again would double-count one reservation.
        """

        production = _production()
        world = self._require_world()
        owned = set(getattr(self.orchestrator, "active_assignments", {}) or {})
        return tuple(
            production.orchestrator.IntegrationReservation(
                task_id=reservation.task_id,
                workflow_state=reservation.workflow_state,
                phase=reservation.phase,
                branch=reservation.branch,
                head=reservation.head,
                checkout_path=reservation.checkout_path,
                exclusive_resources=reservation.exclusive_resources,
                predicted_paths=reservation.predicted_paths,
                actual_paths=reservation.actual_paths,
                unity_serialized_assets=reservation.unity_serialized_assets,
                shared_systems=(),
                confidence=reservation.confidence,
                evidence_type=reservation.evidence_type,
                surface_unknown=reservation.surface_unknown,
                local_active=reservation.local_active,
            )
            for reservation in world.reservations()
            if reservation.task_id not in owned
        )

    # -- architect translation -------------------------------------------

    def _architect_runner(
        self,
        *,
        task: Mapping[str, Any] | None = None,
        candidates: Sequence[Mapping[str, Any]] | None = None,
        source_head: str,
        reservations: Sequence[Any],
        scheduler_id: str,
        admission_limit: int | None = None,
    ) -> Any:
        """Turn the scenario's architect answer into a validated advisory.

        No provider is contacted, no model is invoked and no socket is opened.
        The fixture answer is fed through the production advisory schema and
        identity checks unchanged, so an unavailable or structurally malformed
        answer fails exactly where a real provider's would - which is what
        scenarios H1 and H2 grade.
        """

        production = _production()
        world = self._require_world()
        if (task is None) == (candidates is None):
            raise production.preflight.ArchitectPreflightError(
                "acceptance architect requires exactly one task or portfolio"
            )
        if candidates is not None:
            # The manifest observes one scheduling decision per step. Returning
            # the first safe portfolio admission is a valid architect answer
            # and keeps each production launch bound to exactly one step's
            # evidence without reducing the scheduler's worker capacity.
            limit = min(1, len(candidates) if admission_limit is None else admission_limit)
            considerations = []
            admissions = []
            for entry in candidates:
                candidate_task = entry["task"]
                advisory = self._validated_advisory(
                    world,
                    production,
                    task=candidate_task,
                    source_head=source_head,
                )
                gate = production.preflight.evaluate_architect_policy(advisory)
                for work_type in entry["eligible_work_types"]:
                    matches = work_type == advisory.work_type_recommendation
                    disposition = (
                        "admit"
                        if matches
                        and gate.decision == "start"
                        and len(admissions) < limit
                        else (
                            gate.decision
                            if matches and gate.decision in {"wait", "human_review"}
                            else "wait"
                        )
                    )
                    considerations.append(
                        production.preflight.ArchitectBatchConsideration(
                            task_id=advisory.task_id,
                            work_type=work_type,
                            disposition=disposition,
                            rationale=(
                                "Acceptance fixture translated through the production "
                                f"{disposition} gate."
                            ),
                        )
                    )
                    if disposition == "admit":
                        admissions.append(advisory)
            self._analysis_index += 1
            analysis_id = f"architect-portfolio-acceptance-{self._analysis_index:04d}"
            artifact_path = self._artifact_root / f"{analysis_id}.json"
            batch = production.preflight.ArchitectBatch(
                source_head=source_head,
                batch_rationale=(
                    "Acceptance fixture portfolio translated through production policy."
                ),
                considered=tuple(considerations),
                admissions=tuple(admissions),
            )
            metadata = {
                "provider": "none",
                "model": None,
                "invocation": "deterministic_scenario_fixture",
                "scenario_id": world.scenario_id,
                "network_access": False,
            }
            production.preflight._safe_write_json(
                artifact_path,
                {
                    "schema_version": production.preflight.ARCHITECT_BATCH_SCHEMA_VERSION,
                    "analysis_id": analysis_id,
                    "structured_architect_output": batch.to_dict(),
                    "invocation": metadata,
                },
            )
            return production.preflight.ArchitectBatchAnalysis(
                analysis_id=analysis_id,
                batch=batch,
                artifact_path=artifact_path,
                active_surface_fingerprint=(
                    production.preflight.active_surface_fingerprint(reservations)
                ),
                invocation_metadata=metadata,
            )

        assert task is not None
        advisory = self._validated_advisory(
            world,
            production,
            task=task,
            source_head=source_head,
        )
        task_id = advisory.task_id
        self._analysis_index += 1
        analysis_id = (
            f"architect-{task_id.casefold()}-acceptance-{self._analysis_index:04d}"
        )
        metadata = {
            "provider": "none",
            "model": None,
            "invocation": "deterministic_scenario_fixture",
            "scenario_id": world.scenario_id,
            "network_access": False,
        }
        artifact_path = production.preflight.persist_architect_advisory(
            artifact_root=self._artifact_root,
            analysis_id=analysis_id,
            scheduler_id=scheduler_id,
            task=task,
            source_head=source_head,
            reservations=reservations,
            advisory=advisory,
            invocation_metadata=metadata,
        )
        self._validated_advisories[task_id] = advisory
        return production.preflight.ArchitectAnalysis(
            analysis_id=analysis_id,
            advisory=advisory,
            artifact_path=artifact_path,
            active_surface_fingerprint=(
                production.preflight.active_surface_fingerprint(reservations)
            ),
            invocation_metadata=metadata,
        )

    def _validated_advisory(
        self,
        world: ScenarioWorld,
        production: _ProductionScheduler,
        *,
        task: Mapping[str, Any],
        source_head: str,
    ) -> Any:
        """Validate one fixture answer through the production advisory contract."""

        task_id = str(task.get("id", ""))
        declared = world.advisory(task_id)
        if declared is None:
            raise production.preflight.ArchitectPreflightError(
                "the architect produced no usable advisory for "
                f"{task_id}: the invocation is unavailable"
            )
        advisory = production.preflight.ArchitectAdvisory.from_dict(
            _production_advisory_payload(
                declared, task=task, source_head=source_head
            )
        )
        if advisory.task_id != task_id:
            raise production.preflight.ArchitectPreflightError(
                "architect changed candidate task identity"
            )
        if advisory.source_head != source_head:
            raise production.preflight.ArchitectPreflightError(
                "architect changed source HEAD identity"
            )
        if advisory.task_contract_sha256 != task.get("task_contract_sha256"):
            raise production.preflight.ArchitectPreflightError(
                "architect changed task-contract hash identity"
            )
        self._validated_advisories[task_id] = advisory
        return advisory

    # -- output translation ----------------------------------------------

    def _canonical_records(
        self,
        produced: Sequence[Mapping[str, Any]],
        *,
        poll_id: str,
        poll_index: int,
        result: Any,
    ) -> list[dict[str, Any]]:
        """Translate one poll's production records into canonical evidence.

        The event contract is total and fails closed. Every production record
        is either translated into a canonical record or explicitly named in
        `PRODUCTION_DIAGNOSTIC_EVENTS`; anything else raises. There is no
        catch-all branch, no prefix rule and no wildcard, so a production event
        added later - a new safety, conflict, escalation or lock record - stops
        the cycle instead of silently disappearing from the evidence a step is
        graded on.
        """

        records: list[dict[str, Any]] = []
        for record in produced:
            name = str(record.get("event", ""))
            if name == EVENT_POLL_STARTED:
                records.append(
                    self._envelope(record, EVENT_POLL_STARTED, poll_id, poll_index)
                )
            elif name == EVENT_RESERVATIONS_OBSERVED:
                # An empty observation names no reservation and is therefore not
                # evidence about one. The production record is still kept in the
                # diagnostic log.
                if record.get("reservations"):
                    records.append(
                        self._envelope(
                            record, EVENT_RESERVATIONS_OBSERVED, poll_id, poll_index
                        )
                    )
            elif name == EVENT_WORKER_LAUNCHED:
                records.append(
                    self._envelope(record, EVENT_WORKER_LAUNCHED, poll_id, poll_index)
                )
            elif name == EVENT_HUMAN_REVIEW:
                records.append(self._escalation(record, poll_id, poll_index))
            elif name in PRODUCTION_WAIT_EVENTS:
                records.append(self._wait(record, poll_id, poll_index))
            elif name not in PRODUCTION_DIAGNOSTIC_EVENTS:
                raise EventEvidenceError(
                    f"{UNKNOWN_PRODUCTION_EVENT_BLOCKER} Event: {name!r}."
                )
        records.append(
            {
                "event": EVENT_POLL_FINISHED,
                "poll_id": poll_id,
                "poll_index": poll_index,
                "scheduler_id": self.scheduler_id,
                "outcome": self._outcome(result, records),
                "poll_status": str(result.status),
                "fatal": bool(result.fatal),
                "task_id": result.task_id,
            }
        )
        return records

    def _bind_launch_identity(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        produced: Sequence[Mapping[str, Any]],
        result: Any,
    ) -> None:
        """Fail closed unless every production launch identity agrees.

        A launch is described by several independent production artefacts: the
        returned `PollCycleResult`, the raw `worker_launched` record, its
        canonical translation, the argv production built, the argv the passive
        `process_factory` was actually handed, and whatever this adapter already
        retained for that worker. Each one is read as its own claim. They must
        all be present and identical; the adapter never trusts one source over
        another, never overwrites one with another, and never synthesizes a
        missing identity to make them agree. Any contradiction raises here, so
        it can never become a `CycleObservation` that a step might grade as
        START.
        """

        canonical = [
            record for record in records if record["event"] == EVENT_WORKER_LAUNCHED
        ]
        raw = [
            record
            for record in produced
            if str(record.get("event", "")) == EVENT_WORKER_LAUNCHED
        ]
        if len(canonical) != len(raw):
            raise EventEvidenceError(
                f"the poll translated {len(canonical)} launch records from "
                f"{len(raw)} production launch records"
            )
        launched = str(result.status) == PRODUCTION_LAUNCH_STATUS
        if launched != (len(canonical) == 1):
            raise EventEvidenceError(
                f"PollCycleResult.status is {result.status!r} but the poll "
                f"emitted {len(canonical)} worker_launched records"
            )
        captured = self.process_factory.launches
        if not canonical:
            if len(captured) != self._captured_launch_count:
                raise EventEvidenceError(
                    "the process factory captured a launch attempt for a poll "
                    "that reported no worker_launched record"
                )
            return

        record = canonical[0]
        source = raw[0]
        argv = tuple(str(item) for item in (record.get("argv") or ()))
        raw_argv = tuple(str(item) for item in (source.get("argv") or ()))
        if not argv:
            raise EventEvidenceError(
                "a production launch record carried no argv, so the launch is "
                "UNPROVEN"
            )
        if argv != raw_argv:
            raise EventEvidenceError(
                "the canonical launch argv is not the production launch argv: "
                f"canonical {list(argv)}, production {list(raw_argv)}"
            )
        if len(captured) != self._captured_launch_count + 1:
            raise EventEvidenceError(
                "exactly one worker_launched record must correspond to exactly "
                f"one captured process launch; the factory holds {len(captured)} "
                f"captures after {self._captured_launch_count}"
            )
        captured_argv = tuple(str(item) for item in captured[-1]["argv"])
        if captured_argv != argv:
            raise EventEvidenceError(
                "the argv the scheduler actually tried to launch is not the "
                f"argv it reported: captured {list(captured_argv)}, reported "
                f"{list(argv)}"
            )

        task_claims: dict[str, Any] = {
            "worker_launched.task_id (canonical)": record.get("task_id"),
            "worker_launched.task_id (production)": source.get("task_id"),
            "PollCycleResult.task_id": result.task_id,
        }
        worker_claims: dict[str, Any] = {
            "worker_launched.worker_id (canonical)": record.get("worker_id"),
            "worker_launched.worker_id (production)": source.get("worker_id"),
            "PollCycleResult.worker_id": result.worker_id,
        }

        worker_values = _argv_flag_values(argv, LAUNCH_ARGV_WORKER_FLAG)
        if len(worker_values) != 1:
            raise EventEvidenceError(
                f"a production launch argv must bind exactly one "
                f"{LAUNCH_ARGV_WORKER_FLAG}; it bound {list(worker_values)}"
            )
        worker_claims[f"argv {LAUNCH_ARGV_WORKER_FLAG}"] = worker_values[0]

        # The task flag is checked where it exists rather than required here:
        # the verifier separately proves the argv binds the step's exact task
        # ID, and this adapter must not invent an argument production omitted.
        task_values = _argv_flag_values(argv, LAUNCH_ARGV_TASK_FLAG)
        if len(task_values) > 1:
            raise EventEvidenceError(
                f"a production launch argv bound {LAUNCH_ARGV_TASK_FLAG} more "
                f"than once: {list(task_values)}"
            )
        if task_values:
            task_claims[f"argv {LAUNCH_ARGV_TASK_FLAG}"] = task_values[0]

        task_id = _agreed_identity("task", task_claims)
        worker_id = _agreed_identity("worker", worker_claims)

        remembered_task = self._launch_task_by_worker.get(worker_id)
        if remembered_task is not None and remembered_task != task_id:
            raise EventEvidenceError(
                f"worker {worker_id} was already observed launched for "
                f"{remembered_task} and is now reported launched for {task_id}"
            )
        remembered_argv = self._launch_argv_by_worker.get(worker_id)
        if remembered_argv is not None and remembered_argv != argv:
            raise EventEvidenceError(
                f"worker {worker_id} was already observed launched with a "
                f"different argv: retained {list(remembered_argv)}, now "
                f"{list(argv)}"
            )
        self._launch_task_by_worker[worker_id] = task_id
        self._launch_argv_by_worker[worker_id] = argv
        self._captured_launch_count = len(captured)

    def _envelope(
        self,
        record: Mapping[str, Any],
        name: str,
        poll_id: str,
        poll_index: int,
    ) -> dict[str, Any]:
        payload = {key: value for key, value in record.items() if key != "event"}
        payload["production_event"] = str(record.get("event", ""))
        payload["event"] = name
        payload["poll_id"] = poll_id
        payload["poll_index"] = poll_index
        payload["scheduler_id"] = self.scheduler_id
        return payload

    def _wait(
        self, record: Mapping[str, Any], poll_id: str, poll_index: int
    ) -> dict[str, Any]:
        payload = self._envelope(record, EVENT_CANDIDATE_WAITED, poll_id, poll_index)
        declared = PRODUCTION_WAIT_EVENTS[str(record.get("event", ""))]
        if declared is None:
            production_kind = str(record.get("conflict_kind", ""))
            declared = PRODUCTION_CONFLICT_KINDS.get(production_kind)
            if declared is None:
                raise EventEvidenceError(
                    "the scheduler reported an untranslated conflict kind: "
                    f"{production_kind!r}"
                )
        payload["wait_kind"] = declared
        values = [str(item) for item in (record.get("overlapping_values") or ())]
        if values:
            # A Unity `.meta` companion and its asset are one non-merge-safe
            # identity, which is exactly why the scheduler collided on them.
            # Both names are reported so the evidence says which files and which
            # asset identity overlapped.
            payload["overlapping_values"] = sorted(
                {*values, *(unity_asset_identity(value) for value in values)}
            )
        return payload

    def _escalation(
        self, record: Mapping[str, Any], poll_id: str, poll_index: int
    ) -> dict[str, Any]:
        payload = self._envelope(record, EVENT_HUMAN_REVIEW, poll_id, poll_index)
        advisory = self._validated_advisories.get(str(record.get("task_id", "")))
        if advisory is not None:
            payload["escalation_category"] = advisory.escalation.category
            payload["escalation_question"] = advisory.escalation.question
        return payload

    def _outcome(self, result: Any, records: Sequence[Mapping[str, Any]]) -> str:
        outcome = POLL_STATUS_OUTCOMES.get(str(result.status))
        if outcome is None:
            raise UnsupportedScenario(
                "the scheduler returned an untranslated poll status: "
                f"{result.status!r}"
            )
        escalated = any(
            record["event"] == EVENT_HUMAN_REVIEW for record in records
        )
        if escalated and outcome not in {"start", "blocked"}:
            # The scheduler has no `human_review` poll status; it expresses the
            # decision by emitting the escalation record. Naming that outcome
            # here is a vocabulary translation, not a second admission policy.
            return "human_review"
        return outcome

    def _observation(
        self, records: Sequence[Mapping[str, Any]], result: Any
    ) -> CycleObservation:
        finished = records[-1]
        launches = [
            record for record in records if record["event"] == EVENT_WORKER_LAUNCHED
        ]
        waits = [
            record for record in records if record["event"] == EVENT_CANDIDATE_WAITED
        ]
        escalations = [
            record for record in records if record["event"] == EVENT_HUMAN_REVIEW
        ]
        reasons: list[str] = []
        for record in waits:
            reason = record.get("reason")
            if reason:
                reasons.append(str(reason))
            reasons.extend(str(item) for item in (record.get("reasons") or ()))
        task_id = result.task_id
        if task_id is None and escalations:
            task_id = str(escalations[0].get("task_id")) or None
        return CycleObservation(
            outcome=str(finished["outcome"]),
            task_id=task_id,
            worker_id=result.worker_id,
            launch_argv=(
                tuple(str(item) for item in (launches[0].get("argv") or ()))
                if launches
                else ()
            ),
            waited_task_ids=tuple(
                sorted(
                    {
                        str(record.get("task_id"))
                        for record in waits
                        if record.get("task_id")
                    }
                )
            ),
            conflicts=tuple(
                ConflictObservation(
                    kind=str(record["wait_kind"]),
                    candidate_task_id=str(record.get("task_id", "")),
                    conflicting_task_id=str(record.get("conflicting_task_id", "")),
                    overlapping_values=tuple(
                        str(item) for item in (record.get("overlapping_values") or ())
                    ),
                    reason=str(record.get("reason", "")),
                )
                for record in waits
                if record.get("conflicting_task_id")
            ),
            reasons=tuple(reasons),
            escalation_category=(
                str(escalations[0].get("escalation_category"))
                if escalations
                else None
            ),
            escalation_question=(
                str(escalations[0].get("escalation_question"))
                if escalations
                else None
            ),
            events=tuple(records),
        )


def _production_advisory_payload(
    declared: Mapping[str, Any],
    *,
    task: Mapping[str, Any],
    source_head: str,
) -> dict[str, Any]:
    """Shape a scenario's architect answer as a production advisory payload.

    This fills only the transport fields the fixture vocabulary does not model
    and renames `disjointness_claims` to the production field. It never repairs
    a declared defect: a wrong task ID, a missing predicted change surface, an
    unknown structured field, a foreign scenario binding and a non-numeric
    confidence all survive into the payload and are rejected by production
    validation, which is what scenario H2 grades.
    """

    payload = dict(declared)
    claims = payload.pop("disjointness_claims", ())
    payload.setdefault("source_head", source_head)
    payload.setdefault("task_contract_sha256", task.get("task_contract_sha256"))
    payload.setdefault("conflict_reasons", [])
    payload.setdefault("evidence", [])
    payload.setdefault("assumptions", [])
    payload.setdefault("work_type_recommendation", "implementation")
    payload.setdefault(
        "unknown_surface_disjointness",
        [
            {
                "task_id": str(claim),
                "justification": (
                    "the scenario's architect answer asserts a surface disjoint "
                    f"from {claim}"
                ),
            }
            for claim in claims
        ],
    )
    payload.setdefault(
        "execution_recommendation",
        {
            "capability_tier": "standard",
            "provider_preference": "no_preference",
            "rationale": (
                "the acceptance manifest declares no capability tier, so the "
                "deterministic routing tier default is used"
            ),
        },
    )
    payload.setdefault(
        "design_advice",
        {
            "implementation_summary": (
                "deterministic acceptance advisory for "
                f"{task.get('id', 'the candidate')}"
            ),
            "recommended_interfaces": [],
            "sequencing_notes": [],
            "suggested_exclusive_resources": [],
            "suggested_taskgraph_changes": [],
            "suggested_decomposition": [],
        },
    )
    surface = payload.get("predicted_change_surface")
    if isinstance(surface, Mapping):
        payload["predicted_change_surface"] = {
            "exact_paths": list(surface.get("exact_paths", ())),
            "path_patterns": [],
            "unity_serialized_assets": list(
                surface.get("unity_serialized_assets", ())
            ),
            "symbols_or_components": [],
            "shared_systems": [],
        }
    return payload

# ---------------------------------------------------------------------------
# Harness adapter
# ---------------------------------------------------------------------------

class ScriptedAdapter:
    """Harness-only adapter that replays a fixed list of observations.

    Two uses, both about the harness rather than the scheduler:

    1. replaying the manifest's own expectations exercises fixture
       construction, transitions, durable-state snapshots and every check code
       path end to end;
    2. replaying a deliberately wrong answer proves the verifier discriminates.

    Its agreement with the manifest in case (1) is tautological and is reported
    as `HARNESS_PASS` for exactly that reason. It does not implement
    `observe_singleton_contest`, because replaying a scripted string cannot
    prove an OS lock.
    """

    def __init__(
        self,
        observations: Sequence[CycleObservation],
        *,
        capabilities: Iterable[str] = (),
    ) -> None:
        self.observations = list(observations)
        self._capabilities = frozenset(capabilities)
        self.index = 0

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def observe_cycle(self, world: ScenarioWorld) -> CycleObservation:
        if self.index >= len(self.observations):
            raise UnsupportedScenario(
                f"scripted adapter exhausted for scenario {world.scenario_id}"
            )
        observation = self.observations[self.index]
        self.index += 1
        return observation
