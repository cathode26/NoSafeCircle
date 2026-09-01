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

## Wiring the real scheduler later

The polling orchestrator already exposes every injection point this adapter
needs, so `RealPollingArchitectAdapter` is a translation shim and nothing more:

```text
ScenarioWorld.source_root         -> PollingOrchestrator(source=...)
ScenarioWorld.checkout_root       -> PollingOrchestrator(checkout_root=...)
ScenarioWorld.candidate_queue()   -> plan_builder=...       (fresh Stage-2 rank)
ScenarioWorld.resume_candidate()  -> resume_source=...      (durable resume claim)
ScenarioWorld.task(...)           -> task_loader=...
ScenarioWorld.reservation_dicts() -> reservation_observer=...
ScenarioWorld.advisory(...)       -> architect_runner=...   (injected advisory;
                                      no provider call, no network)
launch capture                    -> process_factory=...    (records argv only)
scheduler events                  -> event_emitter=...      (structured records)
```

Three rules govern that shim when it is written:

1. It must not reimplement any scheduling decision. It translates inputs and
   records outputs. If the shim ever contains a `wait` branch of its own, the
   acceptance result is measuring the shim.
2. `process_factory` must record the exact argv and never start a process. A
   real worker launch belongs to the live proof, not to this harness.
3. It must populate `CycleObservation.events` from the scheduler's own emitter,
   with **exactly the events that cycle produced**. Acceptance is derived from
   those structured events plus Git state, never from a returned decision
   string.
4. Every emitted event must carry the required fields listed in
   `ACCEPTANCE_EVENT_FIELDS`, including a `poll_id` that correlates one poll's
   `poll_started`, decision, and `poll_finished` records. A cycle that cannot
   produce that lifecycle is not acceptance evidence; the scenario stays
   `PENDING_CAPABILITY` instead.

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

from acceptance_lib import OUTCOMES, canonical_json
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
# The real adapter (deliberately not wired yet)
# ---------------------------------------------------------------------------

WIRING_BLOCKER = (
    "The polling Software Architect scheduler is not committed to this branch. "
    "Wire this adapter only after Pipeline/TaskReviewAgent/polling_orchestrator.py "
    "and architect_preflight.py are reviewed and merged, then implement "
    "observe_cycle() as a translation shim over the orchestrator's existing "
    "plan_builder, task_loader, reservation_observer, architect_runner, "
    "process_factory and event_emitter injection points. Until then this "
    "adapter fails closed rather than returning a stub answer that a report "
    "could mistake for acceptance evidence."
)


class RealPollingArchitectAdapter:
    """The one adapter the acceptance path is allowed to construct.

    It is instantiated by `verify_acceptance.py` itself, never handed in by a
    caller, so nothing outside this module can substitute a lookalike. It fails
    closed until the scheduler exists.
    """

    def __init__(self, *, orchestrator_factory: Any = None) -> None:
        self.orchestrator_factory = orchestrator_factory

    def capabilities(self) -> frozenset[str]:
        raise AdapterNotWired(WIRING_BLOCKER)

    def observe_cycle(self, world: ScenarioWorld) -> CycleObservation:
        raise AdapterNotWired(WIRING_BLOCKER)

    def observe_singleton_contest(self, world: ScenarioWorld) -> SingletonObservation:
        raise AdapterNotWired(WIRING_BLOCKER)


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
