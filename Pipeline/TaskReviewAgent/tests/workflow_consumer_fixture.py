"""Invented ordinary-human workflow histories for consumer regressions.

Test-only in-memory data. No synthetic approval policy, historical Issue data,
filesystem, GitHub, provider, or Unity execution is used. Import this fixture
after selecting the application checkout on sys.path for paired baseline runs.
"""

from __future__ import annotations

import datetime as dt

from Pipeline.TaskReviewAgent import issue_workflow_store as store
from Pipeline.TaskReviewAgent.issue_workflow import (
    STATE_LABELS,
    WorkflowActor as Actor,
    WorkflowEventType as Event,
    WorkflowPhase as Phase,
    WorkflowState as State,
    initial_state,
    render_event_comment,
    transition,
    update_issue_body,
)

BASE = dt.datetime(2026, 9, 7, tzinfo=dt.timezone.utc)


def stamp(seconds):
    return (BASE + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


class HumanFixture:
    def __init__(self, *, backend=None, task="NSC-701", closed=False,
                 label_first=False, coherent=False, closed_prefix_length=2):
        self.backend = backend or store.MemoryIssueBackend(now=lambda: stamp(0))
        self.task = task
        self.events = []
        self.state = initial_state(task_id=task, task_contract_sha256="7" * 64, now=stamp(0))
        self.step(Event.AGENT_LEASE_ACQUIRED, State.AGENT_WORKING, 10,
                  details={"worker_id": "workflow-consumer-fixture", "lease_id": "1" * 64})
        self.implementation_state = self.state
        self.step(Event.HUMAN_HANDOFF_CREATED, State.HUMAN_ACTION_REQUIRED, 60,
                  phase=Phase.UNITY_RUNTIME_VALIDATION,
                  details={"branch": task.lower() + "-consumer-fixture", "head_commit": "b" * 40,
                           "checkout_path": "C:/offline-fixture/" + task})
        self.handoff_state = self.state
        if not label_first:
            self.step(Event.HUMAN_VALIDATION_PASSED, State.AGENT_READY, 120, actor=Actor.HUMAN,
                      phase=Phase.DELIVERY_EVIDENCE, details={"tested_commit": "b" * 40})
        self.body_state = self.state
        if closed:
            if closed_prefix_length not in (1, 2):
                raise ValueError("closed_prefix_length must be one or two canonical events")
            self.step(Event.AGENT_LEASE_ACQUIRED, State.AGENT_WORKING, 130,
                      phase=Phase.MERGE_CLOSEOUT,
                      details={"worker_id": "workflow-consumer-fixture", "lease_id": "2" * 64})
            self.working_state = self.state
            if closed_prefix_length == 1:
                self.body_state = self.state
            self.step(Event.COMPLETED, State.COMPLETE, 140, phase=Phase.MERGE_CLOSEOUT,
                      details={"pull_request_url": "https://example.invalid/pull/7",
                               "pull_request_number": 7, "merged_commit": "d" * 40,
                               "conformant_record_id": "DEL-" + task + "-fixture"})
        if coherent:
            self.body_state = self.state
        created = self.backend.create_issue(
            title=task + " — Workflow consumer fixture",
            body=update_issue_body("", self.body_state), labels=[], assignees=["cathode26"],
        )
        self.number = created["number"]
        self.issue = self.backend.issues[self.number]
        for event in self.events:
            self.backend.add_comment(self.number, render_event_comment(event, "Invented fixture history."))
        self.issue["state"] = "CLOSED" if closed else "OPEN"
        self.backend.issue_events[self.number] = []
        if label_first:
            self.issue["labels"] = [{"name": STATE_LABELS[State.AGENT_READY.value]}]
            self.record("labeled", 121, label=STATE_LABELS[State.AGENT_READY.value])
        elif coherent:
            self.issue["labels"] = [{"name": STATE_LABELS[self.state.state.value]}]
        else:
            self.record("unlabeled", 141 if closed else 121,
                        label=STATE_LABELS[State.AGENT_WORKING.value if closed else State.HUMAN_ACTION_REQUIRED.value])
            if closed:
                self.record("closed", 143)

    def step(self, kind, target, seconds, *, phase=None, details=None, actor=Actor.AGENT):
        self.state, event = transition(
            self.state, event_type=kind, to_state=target, to_phase=phase,
            actor_type=actor,
            actor_id="cathode26" if actor is Actor.HUMAN else "workflow-consumer-fixture",
            details=details or {}, now=stamp(seconds),
        )
        self.events.append(event)

    def record(self, kind, seconds, *, label=None, actor="cathode26"):
        history = self.backend.issue_events[self.number]
        value = {"id": 1000 + self.number * 10 + len(history), "event": kind,
                 "created_at": stamp(seconds), "actor": {"login": actor}}
        if label is not None:
            value["label"] = {"name": label}
        history.append(value)
        return value

    def snapshot(self):
        return store._snapshot(self.backend, self.backend.get_issue(self.number))

    def task_data(self):
        return {"id": self.task, "task_contract_sha256": "7" * 64,
                "exclusive_resources": ["unity-scene:Assets/Scenes/ConsumerFixture.unity"]}
