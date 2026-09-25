"""Deterministic tests for owned background jobs in the graph controller.

Fixture tickets complete at controlled fixture-clock times; no provider, Unity,
Docker or GitHub is contacted (a fixture Docker CLI stands in for the exact
container inspect/remove calls). Windows-only tests launch the real detached
child with the test-only ``fixture`` ticket kind to prove the process identity
handshake, receipt binding, Job Object containment, restart adoption and exact
tree termination end to end.
"""
from __future__ import annotations

import contextlib
import errno
import hashlib
import io
import json
import os
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from Pipeline.AssistantControl import background_jobs
from Pipeline.AssistantControl import decomposition as decomposition_module
from Pipeline.AssistantControl import review as review_module
from Pipeline.AssistantControl import test_graph_controller as _graph_tests
from Pipeline.AssistantControl.background_jobs import BackgroundJobError
from Pipeline.AssistantControl.checkouts import write_record
from Pipeline.AssistantControl.graph_controller import (
    BACKGROUND_ACTION_KINDS,
    LOCK_DEFERRABLE_ACTION_KINDS,
    LOCK_DEFERRAL_LIMIT,
    LOCK_DEFERRAL_WAIT_SECONDS,
    SOURCE_LANE_ACTION_KINDS,
    STOP_REQUEST_SCHEMA,
    GraphController,
    GraphPolicy,
    request_stop,
)
from Pipeline.AssistantControl.review import _source_integration_lock
from Pipeline.TaskReviewAgent.execution_session_pool import _exclusive_file_lock



def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class FixtureClock:
    """Monotonic fixture time; ``sleep`` advances it and runs due fixture children."""

    def __init__(self):
        self.now = 0.0
        self.listeners = []

    def __call__(self) -> float:
        return self.now

    def utc(self) -> datetime:
        """Fixture wall clock: the tombstones and timestamps follow the fixture time."""
        return datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=self.now)

    def sleep(self, seconds: float) -> None:
        self.now += float(seconds)
        for listener in self.listeners:
            listener()


class FixtureDocker:
    """A Docker CLI stand-in that knows only the containers a test created.

    ``create(..., at=)`` lands a container at a later fixture time, so a create
    that races a stop can be scheduled exactly; every call is retained.
    ``expect(...)`` registers a ticket's provider container so ``create`` stamps
    exactly the job and checkout labels that ticket's child would, the way the
    real ``docker compose run --label`` does; pass ``labels=`` explicitly to
    create an unlabelled container or another checkout's.
    """

    def __init__(self, clock):
        self.clock = clock
        self.containers: dict[str, dict] = {}
        self.scheduled: list[tuple[float, dict]] = []
        self.calls: list[list[str]] = []
        self.removed: list[str] = []
        self.stopped: list[str] = []
        self.available = True
        self.tickets: dict[str, dict] = {}
        self.on_call = None  # runs during every Docker call, before it is answered

    def expect(self, container) -> None:
        """Register one ticket's provider container so create() labels it exactly."""
        if isinstance(container, dict) and container.get("name"):
            self.tickets[str(container["name"])] = dict(container.get("labels") or {})

    def create(self, name: str, project: str = "nosafecircle", *,
               service: str = "round-robin-decompose", at: float | None = None,
               labels: dict | None = None) -> str:
        container = {
            "id": hashlib.sha256(f"{name}:{project}:{len(self.calls)}:{at}".encode()).hexdigest(),
            "name": name, "project": project, "service": service, "running": True,
            "labels": dict(self.tickets.get(name, {})) if labels is None else dict(labels),
        }
        if at is None or at <= self.clock():
            self.containers[name] = container
        else:
            self.scheduled.append((at, container))
        return container["id"]

    def _materialize(self) -> None:
        for item in [item for item in self.scheduled if item[0] <= self.clock()]:
            self.scheduled.remove(item)
            self.containers[item[1]["name"]] = item[1]

    def __call__(self, arguments: list[str]) -> tuple[int, str, str]:
        self.calls.append(list(arguments))
        if self.on_call is not None:
            self.on_call(list(arguments))
        if not self.available:
            return 1, "", "error during connect: Docker Desktop is not running"
        self._materialize()
        if arguments[:3] == ["container", "inspect", "--format"] and len(arguments) == 5:
            found = self.containers.get(arguments[4])
            if found is None:
                return 1, "[]\n", f"Error: No such container: {arguments[4]}"
            labels = found.get("labels") or {}
            return 0, json.dumps({
                "id": found["id"], "name": "/" + found["name"], "running": found["running"],
                "project": found["project"], "service": found["service"],
                # A missing label reads empty, exactly as `index .Config.Labels`
                # does for a key the container does not carry.
                "job": labels.get(background_jobs.CONTAINER_JOB_LABEL, ""),
                "checkout": labels.get(background_jobs.CONTAINER_CHECKOUT_LABEL, ""),
            }) + "\n", ""
        if arguments[:2] == ["rm", "-f"] and len(arguments) == 3:
            for name, found in list(self.containers.items()):
                if found["id"] == arguments[2]:
                    del self.containers[name]
                    self.removed.append(arguments[2])
                    return 0, arguments[2] + "\n", ""
            return 1, "", f"Error response from daemon: No such container: {arguments[2]}"
        if arguments[:3] == ["stop", "--time", "10"] and len(arguments) == 4:
            # A stopped container stays present and inspectable, as Docker's does.
            for found in self.containers.values():
                if found["id"] == arguments[3]:
                    found["running"] = False
                    self.stopped.append(arguments[3])
                    return 0, arguments[3] + "\n", ""
            return 1, "", f"Error response from daemon: No such container: {arguments[3]}"
        raise AssertionError(f"unexpected docker command {arguments}")


class FixtureHost:
    """Stands in for the contained detached child: each ticket ends at a scheduled fixture time.

    A ``cooperative`` child notices its bound stop request on the next liveness
    poll and retains its own ``stopped`` receipt; any other child keeps running
    until ``stop`` terminates its exact Job Object name. ``docker_cli`` is the
    fixture Docker the exact container reconciliation talks to.
    """

    def __init__(self, clock: FixtureClock):
        self.clock = clock
        self.clock.listeners.append(self.run_due)
        self.launches: list[dict] = []
        self.plans: dict[tuple[str, str], list] = {}
        self.children: dict[int, dict] = {}
        self.adopted: list[tuple[dict, str]] = []
        self.docker_cli = FixtureDocker(clock)
        self.next_pid = 5000

    def schedule(self, kind: str, task_id: str, duration: float, on_complete, *,
                 cooperative: bool = False) -> None:
        self.plans.setdefault((kind, task_id), []).append((duration, on_complete, cooperative))

    def identify_self(self) -> dict:
        return {"pid": 1, "created_ticks": 1, "image": "fixture-controller"}

    def spawn(self, run_root: Path, request: dict) -> dict:
        key = (request["kind"], request["task_id"])
        if not self.plans.get(key):
            raise BackgroundJobError(f"fixture has no scheduled child for {key}")
        duration, on_complete, cooperative = self.plans[key].pop(0)
        self.launches.append({"at": self.clock(), **request})
        # The real child stamps its ticket's labels on the container it creates.
        self.docker_cli.expect(request.get("provider_container"))
        pid = self.next_pid
        self.next_pid += 1
        identity = {"pid": pid, "created_ticks": 7, "image": "fixture-child"}
        write_record(run_root / "child.identity.json", {
            "job_id": request["job_id"], "pid": pid, "process_identity": identity,
            "request_sha256": hashlib.sha256((run_root / "launch.request.json").read_bytes()).hexdigest(),
        })
        self.children[pid] = {
            "run_root": run_root, "request": request, "identity": identity,
            "job_name": request["job_name"], "handoff": None, "stopped": None,
            "cooperative": cooperative, "complete_at": self.clock() + duration,
            "on_complete": on_complete, "done": False, "completed_at": None,
        }
        return {"pid": pid, "process_identity": identity}

    def handoff(self, run_root: Path, process_identity: dict, job_name: str) -> None:
        child = self.children.get(process_identity.get("pid"))
        if (child is None or child["identity"] != process_identity
                or child["job_name"] != job_name):
            raise BackgroundJobError("fixture handoff is not bound to the exact child")
        child["handoff"] = job_name
        write_record(run_root / "job.opened.json", {
            "job_id": child["request"]["job_id"], "job_name": job_name,
            "pid": process_identity["pid"], "process_identity": process_identity,
        })

    def alive(self, identity: dict) -> bool | None:
        self.run_due()
        child = self.children.get(identity.get("pid"))
        if child is None or child["identity"] != identity:
            return False
        if (not child["done"] and child["cooperative"]
                and Path(child["request"]["stop_request"]).is_file()):
            child["done"] = True
            child["completed_at"] = self.clock()
            write_receipt(child["run_root"], child["request"], child["identity"],
                          status="stopped", error="fixture child stopped cooperatively")
        return not child["done"]

    def tree_active(self, job_name: str) -> int:
        return sum(1 for child in self.children.values()
                   if child["job_name"] == job_name and not child["done"])

    def adopt(self, identity: dict, job_name: str) -> None:
        child = self.children.get(identity.get("pid"))
        if child is None or child["identity"] != identity or child["done"]:
            raise BackgroundJobError("fixture adoption names no live child")
        if child["job_name"] != job_name:
            raise BackgroundJobError("fixture adoption names another Job Object")
        self.adopted.append((dict(identity), job_name))

    def docker(self, arguments: list[str]) -> tuple[int, str, str]:
        return self.docker_cli(arguments)

    def stop(self, identity: dict, job_name: str) -> dict:
        child = self.children.get(identity.get("pid"))
        if child is None or child["identity"] != identity:
            return {"host_exited": True, "tree_active": 0, "job_name": job_name}
        if child["job_name"] != job_name:
            raise BackgroundJobError("fixture stop names another Job Object")
        child["done"] = True
        child["completed_at"] = self.clock()
        child["stopped"] = job_name
        return {"host_exited": True, "tree_active": 0, "job_name": job_name}

    def run_due(self) -> None:
        for child in self.children.values():
            if not child["done"] and self.clock() >= child["complete_at"]:
                child["done"] = True
                child["completed_at"] = self.clock()
                child["on_complete"](child["run_root"], child["request"], child["identity"])

    def kill(self, task_id: str) -> None:
        """Simulate a crashed child: gone without a receipt."""
        for child in self.children.values():
            if child["request"]["task_id"] == task_id and not child["done"]:
                child["done"] = True
                child["on_complete"] = None

    def running(self) -> list[str]:
        return [child["request"]["task_id"] for child in self.children.values() if not child["done"]]


def write_receipt(run_root: Path, request: dict, identity: dict, *, status: str = "succeeded",
                  result=None, error: str | None = None) -> None:
    write_record(run_root / "receipt.json", {
        "schema_version": background_jobs.RECEIPT_SCHEMA, "job_id": request["job_id"],
        "kind": request["kind"], "task_id": request["task_id"],
        "request_sha256": hashlib.sha256((run_root / "launch.request.json").read_bytes()).hexdigest(),
        "pid": identity["pid"], "process_identity": identity,
        "started_at_utc": "fixture", "completed_at_utc": "fixture",
        "status": status, "result": result, "error": error,
    })


class BackgroundJobLoopTests(unittest.TestCase):
    """Loop-level proofs on the real planner with fixture children and a fixture clock."""

    git = _graph_tests.GraphControllerTests.git
    write_task = _graph_tests.GraphControllerTests.write_task

    def setUp(self):
        _graph_tests.GraphControllerTests.setUp(self)
        # A childless decomposition parent keeps the bounded graph exact.
        self.commit_task("NSC-1200", execution_scope="needs_execution_decomposition")
        self.clock = FixtureClock()
        self.host = FixtureHost(self.clock)
        wall = patch.object(background_jobs, "_utc_now", self.clock.utc, create=True)
        wall.start()
        self.addCleanup(wall.stop)
        self.foreground: list[dict] = []
        self.records = self.manager.records
        self.records.mkdir(parents=True, exist_ok=True)

    def pass_tombstone(self) -> None:
        """Let the Docker operation bound of every tombstone pass on the fixture clock."""
        self.clock.sleep(background_jobs.CONTAINER_TOMBSTONE_SECONDS + 1.0)

    def controller(self, *targets: str, limit: int = 4) -> GraphController:
        controller = GraphController(
            self.manager,
            GraphPolicy(targets=targets, auto_approve_gauntlet=True, target_branch="master",
                        background_job_limit=limit),
            {"provider": "claude", "execution_model": "fixture", "timeout_seconds": 900},
            execution_authorized=True, sleep=self.clock.sleep, clock=self.clock,
            job_host=self.host,
        )
        return controller

    # -- record fixtures ---------------------------------------------------

    def commit_task(self, task_id: str, **kwargs) -> str:
        self.write_task(task_id, origin="human_approved_synthetic_gauntlet", **kwargs)
        self.git("add", f"Tasks/{task_id}.yaml")
        self.git("commit", "-m", f"add {task_id}")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        return self.head

    def task_record(self, task_id: str, *, worker_status: str | None, run_id: str) -> Path:
        path = self.records / f"{task_id}.json"
        record = {
            "schema_version": "assistant-checkout/v1", "task_id": task_id,
            "source": str(self.manager.source), "checkout": str(self.manager.root / task_id),
            "source_commit": self.head, "task_contract_sha256": "fixture-contract",
            "branch": f"assistant/{task_id}", "status": "prepared", "approval": None,
        }
        if worker_status is not None:
            record["worker"] = {
                "status": worker_status, "task_id": task_id, "run_id": run_id,
                "lease_id": f"{run_id}-lease", "capacity_released": False,
                "crew_run_id": f"crew-{task_id}",
                "process_identity": {"pid": 77, "created_ticks": 1, "image": "worker"},
                "config": {"provider": "claude", "execution_model": "fixture"},
            }
        write_record(path, record)
        return path

    def approved_candidate(self, task_id: str) -> None:
        """A record the planner turns into a ready, Source-moving `integrate`."""
        self.task_record(task_id, worker_status=None, run_id=f"run-{task_id}")
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.mutate(
            task_id, status="approved", source_commit=self.head,
            candidate={"commit": self.head, "tree": tree, "run_id": f"crew-{task_id}",
                       "authoritative_validations": [{"fixture": True}]},
            approval={"decision": "approve", "commit": self.head},
        )

    def held_events(self, controller: GraphController) -> list[dict]:
        return [event for event in _events(controller.event_path)
                if event["event"] == "source_lane_held"]

    def held_facts(self, controller: GraphController) -> list[tuple]:
        return [(event["task_id"], event["kind"], event["reason"],
                 event["blocking_task_id"], event["blocking_job_id"])
                for event in self.held_events(controller)]

    def mutate(self, task_id: str, **fields) -> None:
        path = self.records / f"{task_id}.json"
        record = _read(path)
        for key, value in fields.items():
            if key == "worker":
                if not isinstance(record.get("worker"), dict):
                    record["worker"] = {}
                record["worker"].update(value)
            else:
                record[key] = value
        write_record(path, record)

    # -- fixture children --------------------------------------------------

    def decomposition_result(self, status: str):
        def on_complete(run_root, request, identity):
            record = {
                "schema_version": "assistant-decomposition/v1", "task_id": request["task_id"],
                "run_id": request["identity"]["run_id"], "source": str(self.manager.source),
                "source_commit": request["identity"]["source_commit"], "status": status,
                "error": "fixture provider failure" if status == "failed" else None,
            }
            write_record(self.records / f"{request['task_id']}.decomposition.json", record)
            write_receipt(run_root, request, identity, result=record)
        return on_complete

    def validated_candidate(self, run_root, request, identity):
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.mutate(request["task_id"], status="awaiting_human", candidate={
            "commit": self.head, "tree": tree, "run_id": request["identity"]["crew_run_id"],
            "authoritative_validations": [{"fixture": True}],
        })
        write_receipt(run_root, request, identity, result={"status": "awaiting_human"})

    def crashed_child(self, run_root, request, identity):
        write_receipt(run_root, request, identity, status="failed",
                      error="PostCrewWorkflowError: fixture registration failure")

    # -- foreground fake ---------------------------------------------------

    def fake_foreground(self, controller: GraphController, *, real_kinds=(),
                        on_source_move=None, before=None):
        real = controller._execute_foreground

        def execute(action):
            kind, task_id = action["kind"], action["task_id"]
            self.foreground.append({
                "kind": kind, "task_id": task_id, "at": self.clock(),
                "jobs_running": sorted(self.host.running()),
                "lane_busy": controller._source_lane_busy,
            })
            # A seam for whatever the real foreground step would do first, such
            # as taking `checkouts.lock`; it may raise like the real step does.
            if before is not None:
                before(action)
            if kind in real_kinds:
                return real(action)
            if kind == "settle_worker":
                self.mutate(task_id, worker={"capacity_released": True})
                return {"capacity_released": True}
            if kind == "start_worker":
                self.mutate(task_id, worker={
                    "status": "running", "task_id": task_id, "run_id": action["run_id"],
                    "lease_id": action["lease_id"], "capacity_released": False,
                    "process_identity": {"pid": 88, "created_ticks": 1, "image": "worker"},
                })
                return {"started": True}
            if kind == "auto_approve":
                self.mutate(task_id, status="approved", approval={
                    "decision": "approve", "commit": action["candidate_commit"],
                })
                return {"status": "approved"}
            if kind in {"integrate", "apply_decomposition", "sync_candidate"}:
                # A fixture Source move lands only what the test asks it to.
                if on_source_move is not None:
                    on_source_move(kind, task_id)
                return {"status": f"{kind}_fixture"}
            raise AssertionError(f"unexpected foreground action {kind}")

        return patch.object(controller, "_execute_foreground", side_effect=execute)

    def worker_exits_at(self, exits: dict[str, float]):
        """Fixture worker liveness: a worker exits at its scheduled fixture time."""
        def status(manager, task_id):
            record = _read(self.records / f"{task_id}.json")
            worker = record.get("worker") or {}
            alive = self.clock() < exits.get(task_id, float("inf"))
            if not alive and worker.get("status") == "running":
                self.mutate(task_id, worker={"status": "succeeded",
                                             "crew_run_id": f"crew-{task_id}"})
                worker = _read(self.records / f"{task_id}.json")["worker"]
            return {"task_id": task_id, "worker": worker, "host_identity_alive": alive,
                    "capacity_released": worker.get("capacity_released") is True}
        return patch("Pipeline.AssistantControl.worker_control.status", side_effect=status)

    # -- tests -------------------------------------------------------------

    def test_five_second_decomposition_does_not_block_worker_settlement(self):
        controller = self.controller("NSC-1200", "NSC-899")
        self.task_record("NSC-899", worker_status="running", run_id="run-899")
        self.host.schedule("decompose", "NSC-1200", 5.0, self.decomposition_result("failed"))
        self.host.schedule("post_crew", "NSC-899", 3.0, self.validated_candidate)

        with self.fake_foreground(controller), self.worker_exits_at({"NSC-899": 2.0}):
            result = controller.run(max_actions=6)

        kinds = [item["action"]["kind"] for item in result["completed_actions"]]
        self.assertEqual(
            ["decompose", "wait_worker", "settle_worker", "post_crew", "wait_job", "auto_approve"],
            kinds,
        )
        self.assertEqual("worker_exited", result["completed_actions"][1]["result"]["progress"])
        settle = next(item for item in self.foreground if item["kind"] == "settle_worker")
        self.assertEqual(2.0, settle["at"])
        self.assertEqual(["NSC-1200"], settle["jobs_running"])
        decompose = self.host.children[5000]
        self.assertEqual(5.0, decompose["completed_at"])
        harvested = {item["task_id"]: item for item in result["harvested_jobs"]}
        self.assertEqual(["NSC-899", "NSC-1200"], list(harvested))
        self.assertEqual("failed", harvested["NSC-1200"]["result_status"])
        self.assertEqual("awaiting_human", harvested["NSC-899"]["result_status"])
        launched = [event for event in _events(controller.event_path)
                    if event["event"] == "job_launched"]
        self.assertEqual(["decompose", "post_crew"], [event["kind"] for event in launched])
        self.assertEqual(5000, launched[0]["pid"])
        self.assertEqual({"pid": 5000, "created_ticks": 7, "image": "fixture-child"},
                         launched[0]["process_identity"])
        self.assertEqual(self.head, launched[0]["identity"]["source_commit"])
        blocked = {item["task_id"]: item for item in result["blocked"]}
        self.assertEqual("decomposition_failed", blocked["NSC-1200"]["reason"])

    def test_unrelated_task_is_prepared_reserved_and_started_while_decomposition_runs(self):
        controller = self.controller("NSC-1200", "NSC-899")
        self.host.schedule("decompose", "NSC-1200", 5.0, self.decomposition_result("failed"))

        with self.fake_foreground(controller, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({}):
            result = controller.run(max_actions=6)

        kinds = [item["action"]["kind"] for item in result["completed_actions"]]
        self.assertEqual(
            ["decompose", "prepare", "scope", "reserve", "start_worker", "wait_worker"], kinds,
        )
        start = next(item for item in self.foreground if item["kind"] == "start_worker")
        self.assertEqual(0.0, start["at"])
        self.assertEqual(["NSC-1200"], start["jobs_running"])
        self.assertEqual(["NSC-899"], sorted(controller._reservations()))
        self.assertEqual("running", _read(self.records / "NSC-899.json")["worker"]["status"])
        self.assertEqual(5.0, self.host.children[5000]["completed_at"])
        self.assertEqual("job_ended", result["completed_actions"][-1]["result"]["progress"])

    def test_multiple_post_crew_jobs_overlap_with_settlement_and_admission(self):
        for task_id in ("NSC-1101", "NSC-1102", "NSC-1103"):
            self.commit_task(task_id)
        controller = self.controller("NSC-899", "NSC-1101", "NSC-1102", "NSC-1103")
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.task_record("NSC-1102", worker_status="succeeded", run_id="run-1102")
        self.task_record("NSC-1103", worker_status="running", run_id="run-1103")
        for task_id in ("NSC-1101", "NSC-1102", "NSC-1103"):
            self.host.schedule("post_crew", task_id, 10.0, self.validated_candidate)

        with self.fake_foreground(controller, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({"NSC-1103": 3.0}):
            result = controller.run(max_actions=12)

        kinds = [(item["action"]["kind"], item["action"]["task_id"])
                 for item in result["completed_actions"]]
        self.assertEqual([
            ("settle_worker", "NSC-1101"), ("settle_worker", "NSC-1102"),
            ("post_crew", "NSC-1101"), ("post_crew", "NSC-1102"),
            ("prepare", "NSC-899"), ("scope", "NSC-899"), ("reserve", "NSC-899"),
            ("start_worker", "NSC-899"), ("wait_worker", "NSC-899"),
            ("settle_worker", "NSC-1103"), ("post_crew", "NSC-1103"), ("wait_worker", "NSC-899"),
        ], kinds)
        start = next(item for item in self.foreground if item["kind"] == "start_worker")
        self.assertEqual((0.0, ["NSC-1101", "NSC-1102"]), (start["at"], start["jobs_running"]))
        late_settle = next(item for item in self.foreground
                           if item["kind"] == "settle_worker" and item["task_id"] == "NSC-1103")
        self.assertEqual((3.0, ["NSC-1101", "NSC-1102"]),
                         (late_settle["at"], late_settle["jobs_running"]))
        self.assertEqual([0.0, 0.0, 3.0], [item["at"] for item in self.host.launches])
        # All three validations overlapped between t=3 and t=10; the run
        # returned when the first two ended while the third was still live.
        self.assertEqual([10.0, 10.0, None],
                         [child["completed_at"] for child in self.host.children.values()])
        self.assertEqual(["NSC-1103"], self.host.running())
        self.assertEqual(10.0, self.clock())
        self.assertEqual("job_ended", result["completed_actions"][-1]["result"]["progress"])

    def test_source_lane_actions_are_foreground_serialized_and_never_jobs(self):
        self.assertEqual(frozenset({"decompose", "post_crew"}), BACKGROUND_ACTION_KINDS)
        self.assertEqual(
            frozenset({"apply_decomposition", "sync_candidate", "auto_approve", "integrate"}),
            SOURCE_LANE_ACTION_KINDS,
        )
        self.assertFalse(BACKGROUND_ACTION_KINDS & SOURCE_LANE_ACTION_KINDS)
        controller = self.controller("NSC-899")
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.host.schedule("post_crew", "NSC-1101", 50.0, self.validated_candidate)
        nested: list[str] = []

        def execute(action):
            self.foreground.append({"kind": action["kind"], "lane_busy": controller._source_lane_busy,
                                    "jobs_running": sorted(self.host.running())})
            if action["kind"] == "apply_decomposition":
                try:
                    controller.execute({"kind": "integrate", "task_id": "NSC-899",
                                        "source_commit": self.head, "target_branch": "master"})
                except RuntimeError as exc:
                    nested.append(str(exc))
            return {"status": "fixture"}

        plans = [
            {"status": "actionable", "next_actions": [
                {"kind": "post_crew", "task_id": "NSC-1101", "crew_run_id": "crew-NSC-1101"},
            ]},
            {"status": "actionable", "next_actions": [
                {"kind": "apply_decomposition", "task_id": "NSC-1200", "run_id": "r", "source_commit": self.head},
                {"kind": "integrate", "task_id": "NSC-899", "source_commit": self.head, "target_branch": "master"},
            ]},
            {"status": "actionable", "next_actions": [
                {"kind": "integrate", "task_id": "NSC-899", "source_commit": self.head, "target_branch": "master"},
            ]},
            {"status": "complete", "next_actions": []},
        ]
        with patch.object(controller, "plan", side_effect=plans), \
                patch.object(controller, "_execute_foreground", side_effect=execute), \
                patch.object(controller, "_reservations", return_value={}):
            result = controller.run(max_actions=4)
        self.assertEqual("complete", result["status"])
        self.assertEqual(["post_crew", "apply_decomposition", "integrate"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertEqual(["Source-moving graph actions must not overlap"], nested)
        for item in self.foreground:
            self.assertTrue(item["lane_busy"], item)
            self.assertEqual(["NSC-1101"], item["jobs_running"], item)
        self.assertFalse(controller._source_lane_busy)

    # -- Source lane held around a decomposition proposal ------------------

    def launched_proposal(self, *targets: str, duration: float = 50.0,
                          status: str = "failed") -> str:
        """Put exactly one decomposition proposal in flight and return its job id."""
        launcher = self.controller(*targets)
        self.host.schedule("decompose", "NSC-1200", duration,
                           self.decomposition_result(status))
        with self.fake_foreground(launcher):
            launched = launcher.run(max_actions=1)
        self.assertEqual(["decompose"], [item["action"]["kind"]
                                         for item in launched["completed_actions"]])
        return launched["completed_actions"][0]["result"]["job_id"]

    def test_every_other_action_continues_while_the_source_lane_is_held(self):
        for task_id in ("NSC-1101", "NSC-1102"):
            self.commit_task(task_id)
        targets = ("NSC-899", "NSC-1101", "NSC-1102", "NSC-1200")
        self.launched_proposal(*targets)

        self.approved_candidate("NSC-899")
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.host.schedule("post_crew", "NSC-1101", 10.0, self.validated_candidate)
        controller = self.controller(*targets)

        with self.fake_foreground(controller, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({}):
            result = controller.run(max_actions=8)

        kinds = [(item["action"]["kind"], item["action"]["task_id"])
                 for item in result["completed_actions"]]
        self.assertEqual([
            ("settle_worker", "NSC-1101"), ("post_crew", "NSC-1101"),
            ("prepare", "NSC-1102"), ("scope", "NSC-1102"), ("reserve", "NSC-1102"),
            ("start_worker", "NSC-1102"), ("wait_job", "NSC-1101"),
            ("auto_approve", "NSC-1101"),
        ], kinds)
        # Settlement, a post-crew launch, setup, admission and `auto_approve`
        # all ran with the proposal in flight; only the Source move waited.
        self.assertNotIn("integrate", [kind for kind, _ in kinds])
        self.assertEqual(["NSC-1200"], self.host.running())
        self.assertEqual([("NSC-899", "integrate", "decomposition_proposal_in_flight")],
                         [facts[:3] for facts in self.held_facts(controller)])
        # `auto_approve` left a second approved candidate, and the final plan
        # holds that integration too while the proposal is still in flight.
        self.assertEqual([("NSC-899", "integrate"), ("NSC-1101", "integrate")],
                         [(item["task_id"], item["kind"]) for item in result["held"]])

    def test_integrate_is_held_while_a_decomposition_proposal_is_in_flight(self):
        # NSC-1145: a correct proposal was thrown away because an unrelated
        # integration moved Source 81 seconds into an 87-second provider call.
        job_id = self.launched_proposal("NSC-1200", "NSC-899")

        # The candidate becomes ready while the proposal is still running.
        self.approved_candidate("NSC-899")
        controller = self.controller("NSC-1200", "NSC-899")
        plan = controller.plan()
        integrate = next(item for item in plan["next_actions"]
                         if item["kind"] == "integrate")
        self.assertEqual(
            {"task_id": "NSC-899", "kind": "integrate",
             "reason": "decomposition_proposal_in_flight",
             "blocking_task_id": "NSC-1200", "blocking_job_id": job_id},
            integrate["held"],
        )
        self.assertEqual([integrate["held"]], plan["held"])

        with self.fake_foreground(controller), self.worker_exits_at({}):
            result = controller.run(max_actions=2)

        self.assertEqual(["wait_job", "integrate"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        # The integration ran the moment the proposal ended, not before it.
        moved = next(item for item in self.foreground if item["kind"] == "integrate")
        self.assertEqual((50.0, []), (moved["at"], moved["jobs_running"]))
        self.assertEqual([], result["held"])
        self.assertEqual(
            [("NSC-899", "integrate", "decomposition_proposal_in_flight",
              "NSC-1200", job_id)],
            self.held_facts(controller),
        )

    def test_second_decomposition_waits_for_the_first_proposal_and_its_apply(self):
        self.commit_task("NSC-1201", execution_scope="needs_execution_decomposition")
        controller = self.controller("NSC-1200", "NSC-1201")
        self.host.schedule("decompose", "NSC-1200", 20.0,
                           self.decomposition_result("review_ready"))
        self.host.schedule("decompose", "NSC-1201", 20.0,
                           self.decomposition_result("failed"))

        def applied(kind, task_id):
            record = _read(self.records / f"{task_id}.decomposition.json")
            write_record(self.records / f"{task_id}.decomposition.json",
                         {**record, "status": "applied"})

        with self.fake_foreground(controller, on_source_move=applied):
            result = controller.run(max_actions=5)

        self.assertEqual([
            ("decompose", "NSC-1200"), ("wait_job", "NSC-1200"),
            ("apply_decomposition", "NSC-1200"), ("decompose", "NSC-1201"),
            ("wait_job", "NSC-1201"),
        ], [(item["action"]["kind"], item["action"]["task_id"])
            for item in result["completed_actions"]])
        # Exactly one proposal was ever in flight, and the second started only
        # after the first proposal's apply had landed.
        self.assertEqual([("decompose", 0.0), ("decompose", 20.0)],
                         [(item["kind"], item["at"]) for item in self.host.launches])
        self.assertEqual(20.0, next(item["at"] for item in self.foreground
                                    if item["kind"] == "apply_decomposition"))
        self.assertEqual(
            [("NSC-1201", "decompose", "decomposition_proposal_in_flight"),
             ("NSC-1201", "decompose", "decomposition_apply_pending")],
            [facts[:3] for facts in self.held_facts(controller)],
        )

    def test_held_actions_become_eligible_when_the_proposal_ends(self):
        self.commit_task("NSC-1201", execution_scope="needs_execution_decomposition")
        targets = ("NSC-899", "NSC-1200", "NSC-1201")
        job_id = self.launched_proposal(*targets)
        self.approved_candidate("NSC-899")
        self.host.schedule("decompose", "NSC-1201", 20.0, self.decomposition_result("failed"))
        controller = self.controller(*targets)

        # Both the Source move and the second proposal are held by the one
        # proposal in flight.
        self.assertEqual(
            [("NSC-899", "integrate", "decomposition_proposal_in_flight",
              "NSC-1200", job_id),
             ("NSC-1201", "decompose", "decomposition_proposal_in_flight",
              "NSC-1200", job_id)],
            [(item["task_id"], item["kind"], item["reason"],
              item["blocking_task_id"], item["blocking_job_id"])
             for item in controller.plan()["held"]],
        )

        def integrated(kind, task_id):
            self.mutate(task_id, status="integrated")

        with self.fake_foreground(controller, on_source_move=integrated), \
                self.worker_exits_at({}):
            result = controller.run(max_actions=4)

        # The proposal ends, the Source move goes first, and the second
        # proposal launches on the next cycle.
        self.assertEqual([
            ("wait_job", "NSC-1200"), ("integrate", "NSC-899"),
            ("decompose", "NSC-1201"), ("wait_job", "NSC-1201"),
        ], [(item["action"]["kind"], item["action"]["task_id"])
            for item in result["completed_actions"]])
        self.assertEqual(50.0, next(item["at"] for item in self.foreground
                                    if item["kind"] == "integrate"))
        self.assertEqual([("decompose", 0.0), ("decompose", 50.0)],
                         [(item["kind"], item["at"]) for item in self.host.launches])
        self.assertEqual([
            ("NSC-899", "integrate", "decomposition_proposal_in_flight"),
            ("NSC-1201", "decompose", "decomposition_proposal_in_flight"),
            ("NSC-1201", "decompose", "source_lane_action_ready"),
        ], [facts[:3] for facts in self.held_facts(controller)])

    def test_ready_integrate_goes_first_and_the_decomposition_launches_next_cycle(self):
        controller = self.controller("NSC-1200", "NSC-899")
        self.approved_candidate("NSC-899")
        self.host.schedule("decompose", "NSC-1200", 20.0, self.decomposition_result("failed"))

        def integrated(kind, task_id):
            self.mutate(task_id, status="integrated")

        with self.fake_foreground(controller, on_source_move=integrated):
            result = controller.run(max_actions=2)

        self.assertEqual([("integrate", "NSC-899"), ("decompose", "NSC-1200")],
                         [(item["action"]["kind"], item["action"]["task_id"])
                          for item in result["completed_actions"]])
        # The integration did not wait minutes for a proposal that had not
        # started, and the proposal started on the very next cycle.
        moved = next(item for item in self.foreground if item["kind"] == "integrate")
        self.assertEqual((0.0, []), (moved["at"], moved["jobs_running"]))
        self.assertEqual([0.0], [item["at"] for item in self.host.launches])
        self.assertEqual(
            [("NSC-1200", "decompose", "source_lane_action_ready", "NSC-899", None)],
            self.held_facts(controller),
        )

    def test_restarted_controller_rebuilds_the_hold_from_the_durable_index(self):
        self.commit_task("NSC-1102")
        targets = ("NSC-899", "NSC-1102", "NSC-1200")
        job_id = self.launched_proposal(*targets)
        self.approved_candidate("NSC-899")
        first = self.controller(*targets)
        held = first.plan()["held"]

        # A different controller instance, holding nothing in memory, derives
        # the same hold from the job index and the records alone.
        restarted = self.controller(*targets)
        self.assertEqual(held, restarted.plan()["held"])
        self.assertEqual(
            [{"task_id": "NSC-899", "kind": "integrate",
              "reason": "decomposition_proposal_in_flight",
              "blocking_task_id": "NSC-1200", "blocking_job_id": job_id}],
            held,
        )

        with self.fake_foreground(restarted, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({}):
            result = restarted.run(max_actions=4)

        self.assertEqual(
            [("prepare", "NSC-1102"), ("scope", "NSC-1102"),
             ("reserve", "NSC-1102"), ("start_worker", "NSC-1102")],
            [(item["action"]["kind"], item["action"]["task_id"])
             for item in result["completed_actions"]],
        )
        # Four cycles planned the same unchanged hold; it is journaled once for
        # this invocation, not once per cycle.
        invocation = _read(restarted.owner_path)["invocation_id"]
        events = self.held_events(restarted)
        self.assertEqual([invocation], [event["invocation_id"] for event in events])
        self.assertEqual(
            [("NSC-899", "integrate", "decomposition_proposal_in_flight",
              "NSC-1200", job_id)],
            self.held_facts(restarted),
        )
        self.assertEqual(["NSC-899"], [item["task_id"] for item in result["held"]])

    def test_apply_decomposition_shares_the_source_integration_lock(self):
        write_record(self.records / "NSC-1200.decomposition.json", {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-1200",
            "run_id": "fixture-review", "source": str(self.manager.source),
            "source_commit": self.head, "status": "review_ready",
        })
        original = review_module._exclusive_file_lock

        def short_lock(path, *, timeout_seconds=300.0):
            return original(path, timeout_seconds=min(timeout_seconds, 0.3))

        with _source_integration_lock(self.manager.source), \
                patch.object(review_module, "_exclusive_file_lock", side_effect=short_lock):
            with self.assertRaises(TimeoutError):
                decomposition_module.apply(
                    self.manager, "NSC-1200", run_id="fixture-review",
                    expected_source_commit=self.head, target_branch="master",
                )
        self.assertEqual(self.head, self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual("review_ready",
                         _read(self.records / "NSC-1200.decomposition.json")["status"])

    def test_restart_observes_live_job_then_harvests_receipt_without_relaunch(self):
        first = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 10.0, self.decomposition_result("review_ready"))
        with self.fake_foreground(first):
            launched = first.run(max_actions=1)
        self.assertEqual(["decompose"], [item["action"]["kind"] for item in launched["completed_actions"]])
        job_id = launched["completed_actions"][0]["result"]["job_id"]
        self.assertEqual(1, len(self.host.launches))

        second = self.controller("NSC-1200")
        with self.fake_foreground(second):
            waited = second.run(max_actions=1)
        self.assertEqual("wait_job", waited["completed_actions"][0]["action"]["kind"])
        self.assertEqual(job_id, waited["completed_actions"][0]["action"]["job_id"])
        self.assertEqual(10.0, self.clock())
        self.assertEqual(1, len(self.host.launches))

        third = self.controller("NSC-1200")
        with self.fake_foreground(third):
            harvested = third.run(max_actions=1)
        self.assertEqual("apply_decomposition", harvested["completed_actions"][0]["action"]["kind"])
        self.assertEqual([job_id], [item["job_id"] for item in harvested["harvested_jobs"]])
        self.assertEqual("review_ready", harvested["harvested_jobs"][0]["result_status"])
        self.assertEqual(1, len(self.host.launches))
        index = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual(("completed", harvested["completed_actions"][0]["action"]["task_id"]),
                         (index["status"], index["task_id"]))
        self.assertEqual(_read(third.owner_path)["invocation_id"], index["harvest_invocation_id"])
        by_invocation = {}
        for event in _events(first.event_path):
            if event["event"].startswith("job_"):
                by_invocation.setdefault(event["invocation_id"], []).append(event["event"])
        self.assertEqual([["job_launched"], ["job_adopted"], ["job_completed"]],
                         list(by_invocation.values()))
        self.assertEqual([(index["process_identity"], index["job_name"])], self.host.adopted)

    def test_restart_harvests_receipt_completed_while_no_controller_ran(self):
        first = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 4.0, self.decomposition_result("review_ready"))
        with self.fake_foreground(first):
            first.run(max_actions=1)
        self.clock.sleep(30.0)  # The child finished while no controller owned the graph.
        second = self.controller("NSC-1200")
        with self.fake_foreground(second):
            result = second.run(max_actions=1)
        self.assertEqual("apply_decomposition", result["completed_actions"][0]["action"]["kind"])
        self.assertEqual(1, len(result["harvested_jobs"]))
        self.assertEqual(1, len(self.host.launches))
        self.assertEqual(30.0, self.clock())
        # The startup harvest reconciled exactly the ticket's container: one
        # inspect of the recorded name, verified absent, nothing removed.
        index = background_jobs.read_index(self.manager, "NSC-1200")
        cleanup = index["provider_container_cleanup"]
        self.assertEqual(("verified_absent", []), (cleanup["status"], cleanup["removed"]))
        self.assertEqual([["container", "inspect", "--format", background_jobs._CONTAINER_INSPECT_FORMAT,
                           index["provider_container"]["name"]]], self.host.docker_cli.calls)
        events = [event for event in _events(second.event_path) if event["event"] == "job_completed"]
        self.assertEqual([_read(second.owner_path)["invocation_id"]],
                         [event["invocation_id"] for event in events])
        self.assertEqual("verified_absent", events[0]["provider_container_cleanup"]["status"])

    def test_died_or_failed_job_blocks_only_its_task(self):
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1200", "NSC-899", "NSC-1101")
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.host.schedule("decompose", "NSC-1200", 100.0, self.decomposition_result("review_ready"))
        self.host.schedule("post_crew", "NSC-1101", 2.0, self.crashed_child)
        with self.fake_foreground(controller, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({}):
            first = controller.run(max_actions=3)
        self.assertEqual(["settle_worker", "post_crew", "decompose"],
                         [item["action"]["kind"] for item in first["completed_actions"]])
        self.host.kill("NSC-1200")
        self.clock.sleep(2.0)

        resumed = self.controller("NSC-1200", "NSC-899", "NSC-1101")
        with self.fake_foreground(resumed, real_kinds=("prepare", "scope", "reserve")), \
                self.worker_exits_at({}):
            result = resumed.run(max_actions=5)
        self.assertEqual(["prepare", "scope", "reserve", "start_worker", "wait_worker"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        blocked = {item["task_id"]: item for item in result["blocked"]}
        self.assertEqual("background_job_died", blocked["NSC-1200"]["reason"])
        self.assertEqual("background_job_failed", blocked["NSC-1101"]["reason"])
        self.assertIn("fixture registration failure", blocked["NSC-1101"]["error"])
        self.assertEqual(2, len(self.host.launches))
        events = [event["event"] for event in _events(resumed.event_path)
                  if event["event"].startswith("job_")]
        self.assertEqual(["job_launched", "job_launched", "job_failed", "job_died"], events)

        fresh = self.controller("NSC-1200", "NSC-899", "NSC-1101")
        with self.fake_foreground(fresh, real_kinds=()), self.worker_exits_at({}):
            again = fresh.run(max_actions=1)
        self.assertEqual("wait_worker", again["completed_actions"][0]["action"]["kind"])
        self.assertEqual(2, len(self.host.launches))

    def test_spawn_failure_blocks_only_its_task_and_is_journaled(self):
        # No fixture child is scheduled for the decomposition, so the host
        # refuses to spawn: the ticket is retained as spawn_failed, the task is
        # blocked, and the unrelated task keeps moving in the same invocation.
        controller = self.controller("NSC-1200", "NSC-899")
        with self.fake_foreground(controller, real_kinds=("prepare", "scope", "reserve")),                 self.worker_exits_at({}):
            result = controller.run(max_actions=3)
        self.assertEqual(["decompose", "prepare", "scope"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertEqual("spawn_failed", result["completed_actions"][0]["result"]["status"])
        self.assertEqual([], self.host.launches)
        blocked = {item["task_id"]: item for item in result["blocked"]}
        self.assertEqual("background_job_spawn_failed", blocked["NSC-1200"]["reason"])
        self.assertIn("no scheduled child", blocked["NSC-1200"]["error"])
        index = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual("spawn_failed", index["status"])
        # A child that failed its handoff may have started Docker before its
        # tree was ended, so the loop verifies the ticket's exact container name
        # (absent here) and keeps its tombstone pending until the bound passes.
        self.assertEqual(["job_spawn_failed", "job_cleanup_pending"],
                         [event["event"] for event in _events(controller.event_path)
                          if event["event"].startswith("job_")])
        cleanup = index["provider_container_cleanup"]
        self.assertEqual(("verified_absent", []), (cleanup["status"], cleanup["removed"]))
        self.assertTrue(background_jobs.tombstone_active(index))
        self.assertEqual([["container", "inspect", "--format", background_jobs._CONTAINER_INSPECT_FORMAT,
                           index["provider_container"]["name"]]],
                         [call for call in self.host.docker_cli.calls][:1])

    # -- `checkouts.lock` contention defers an action, it never fails the run --

    def hold_checkouts_lock(self):
        """Hold this root's real `checkouts.lock` from another thread until released."""
        lock_path = self.records / "checkouts.lock"
        holding, release = threading.Event(), threading.Event()

        def hold() -> None:
            with _exclusive_file_lock(lock_path, timeout_seconds=30.0):
                holding.set()
                release.wait(60.0)

        holder = threading.Thread(target=hold, name="checkouts-lock-holder", daemon=True)
        self.addCleanup(holder.join, 60.0)
        self.addCleanup(release.set)
        holder.start()
        self.assertTrue(holding.wait(30.0), "the fixture never took checkouts.lock")
        return release, holder

    def watch_deferrals(self, controller: GraphController, *, free_lock=None):
        """Record the durable facts at every deferral; optionally free the lock at the first.

        The loop's bounded pause after a deferral is the one call that passes
        exactly ``LOCK_DEFERRAL_WAIT_SECONDS``, so it is where a test can see the
        controller state and the (absent) durable residue of the deferred action.
        """
        observed: list[dict] = []
        inner = controller.sleep
        root = background_jobs.jobs_root(self.manager)

        def sleep(seconds: float) -> None:
            if seconds == LOCK_DEFERRAL_WAIT_SECONDS:
                observed.append({
                    "state": _read(controller.state_path),
                    "indexes": sorted(background_jobs.list_indexes(self.manager)),
                    "job_roots": sorted(str(path.relative_to(root))
                                        for path in root.glob("*/*")) if root.exists() else [],
                    "launches": len(self.host.launches),
                })
                if free_lock is not None and len(observed) == 1:
                    release, holder = free_lock
                    release.set()
                    holder.join(60.0)
            inner(seconds)

        controller.sleep = sleep
        return observed

    def settled_worker_record(self, task_id: str) -> None:
        """A record whose settled successful worker makes `post_crew` the next action."""
        self.task_record(task_id, worker_status="succeeded", run_id=f"run-{task_id}")
        self.mutate(task_id, worker={"capacity_released": True})

    def validated_awaiting_human(self, task_id: str, *, source_commit: str | None = None) -> None:
        """A validated synthetic candidate: `auto_approve`, or `sync_candidate` when stale."""
        self.task_record(task_id, worker_status=None, run_id=f"run-{task_id}")
        tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.mutate(
            task_id, status="awaiting_human",
            source_commit=source_commit if source_commit is not None else self.head,
            candidate={"commit": self.head, "tree": tree, "run_id": f"crew-{task_id}",
                       "authoritative_validations": [{"fixture": True}]},
        )

    def action_events(self, controller: GraphController) -> list[str]:
        return [event["event"] for event in _events(controller.event_path)
                if event["event"].startswith("action_")]

    def test_a_lock_contended_launch_is_deferred_and_launches_on_the_next_cycle(self):
        """A launch that cannot take `checkouts.lock` is re-planned, not fatal.

        The 20260913 Gauntlet run lost invocation dce6aae6 exactly here: a
        `post_crew` launch for NSC-1163 started 1.1 s after the NSC-1162 child
        took the lock to register its candidate, waited its 10 s and raised
        TimeoutError, which blocked the task and ended the invocation with exit 1.
        """
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.settled_worker_record("NSC-1101")
        self.host.schedule("post_crew", "NSC-1101", 5.0, self.validated_candidate)
        deferrals = self.watch_deferrals(controller, free_lock=self.hold_checkouts_lock())

        with self.fake_foreground(controller), self.worker_exits_at({}), \
                patch.object(background_jobs, "LAUNCH_LOCK_TIMEOUT_SECONDS", 0.25):
            result = controller.run(max_actions=2)

        self.assertEqual(["post_crew", "wait_job"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertNotIn("action_failed", self.action_events(controller))
        self.assertEqual(["action_started", "action_deferred", "action_started",
                          "action_completed", "action_started", "action_completed"],
                         self.action_events(controller))
        # The run result reports the deferral, and the journal repeats it exactly.
        journaled = [event for event in _events(controller.event_path)
                     if event["event"] == "action_deferred"]
        self.assertEqual(1, len(journaled))
        self.assertEqual(result["lock_deferrals"],
                         [{key: event[key] for key in result["lock_deferrals"][0]}
                          for event in journaled])
        deferral = result["lock_deferrals"][0]
        self.assertEqual(
            ("NSC-1101", "post_crew", "lock_contention",
             str(self.records / "checkouts.lock"), 1, LOCK_DEFERRAL_LIMIT),
            (deferral["task_id"], deferral["kind"], deferral["reason"],
             deferral["lock_path"], deferral["deferrals"], deferral["limit"]),
        )
        self.assertGreaterEqual(deferral["seconds_waited"], 0.2)
        self.assertIn("timed out after 0.25s waiting for exclusive file lock",
                      deferral["error"])
        # Nothing was blocked, nothing durable was written, and the child that
        # finally started is the only one: the deferral did not duplicate it.
        self.assertEqual([], [item for item in result["blocked"]
                              if item["task_id"] == "NSC-1101"])
        self.assertEqual(1, len(self.host.launches))
        self.assertEqual(1, len(deferrals))
        self.assertEqual(
            ("running", None, [], [], 0),
            (deferrals[0]["state"]["status"], deferrals[0]["state"]["last_error"],
             deferrals[0]["indexes"], deferrals[0]["job_roots"], deferrals[0]["launches"]),
        )
        self.assertIsNone(_read(controller.state_path)["last_error"])

    def test_lock_contention_beyond_the_bound_fails_with_the_original_error(self):
        """The bound keeps a wedged lock loud: exactly today's failure after N deferrals."""
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.settled_worker_record("NSC-1101")
        self.host.schedule("post_crew", "NSC-1101", 5.0, self.validated_candidate)
        self.hold_checkouts_lock()
        deferrals = self.watch_deferrals(controller)

        with self.fake_foreground(controller), self.worker_exits_at({}), \
                patch.object(background_jobs, "LAUNCH_LOCK_TIMEOUT_SECONDS", 0.1):
            with self.assertRaises(TimeoutError) as raised:
                controller.run(max_actions=4)

        self.assertEqual(errno.ETIMEDOUT, raised.exception.errno)
        self.assertEqual(str(self.records / "checkouts.lock"), raised.exception.filename)
        self.assertEqual(LOCK_DEFERRAL_LIMIT, len(deferrals))
        # Under the bound the invocation never blocks the task or records an error.
        self.assertEqual([("running", None)] * LOCK_DEFERRAL_LIMIT,
                         [(item["state"]["status"], item["state"]["last_error"])
                          for item in deferrals])
        self.assertEqual(["action_started", "action_deferred"] * LOCK_DEFERRAL_LIMIT
                         + ["action_started", "action_failed"],
                         self.action_events(controller))
        state = _read(controller.state_path)
        self.assertEqual("blocked", state["status"])
        self.assertTrue(state["last_error"].startswith("TimeoutError: [Errno "),
                        state["last_error"])
        self.assertIn("timed out after 0.1s waiting for exclusive file lock",
                      state["last_error"])
        self.assertEqual([], self.host.launches)

    def test_an_action_kind_outside_the_allowlist_still_fails_on_the_same_timeout(self):
        """Only proven pre-mutation kinds are deferrable; everything else is unchanged.

        `apply_decomposition` stands in for the whole excluded set here: it never
        takes `checkouts.lock` in production (it takes the Source integration lock
        and writes under it), and the wait kinds reach the lock only inside
        `harvest` and the container-cleanup recorders, which persist work that has
        already happened. The gate is the action kind, so one timeout proves it.
        """
        self.assertEqual(frozenset({
            "decompose", "post_crew", "prepare", "refresh_prepared", "scope", "reserve",
            "start_worker", "settle_worker", "sync_candidate", "auto_approve", "integrate",
        }), LOCK_DEFERRABLE_ACTION_KINDS)
        self.assertEqual(frozenset(), LOCK_DEFERRABLE_ACTION_KINDS & frozenset({
            "apply_decomposition", "wait_job", "wait_worker",
        }))
        controller = self.controller("NSC-1200")
        self.hold_checkouts_lock()
        deferrals = self.watch_deferrals(controller)
        plan = {"status": "actionable", "next_actions": [
            {"kind": "apply_decomposition", "task_id": "NSC-1200", "run_id": "r",
             "source_commit": self.head},
        ]}

        def lose_the_lock(action):
            with _exclusive_file_lock(self.records / "checkouts.lock", timeout_seconds=0.1):
                raise AssertionError("the fixture must never take the held lock")

        with patch.object(controller, "plan", side_effect=[plan] * 4), \
                patch.object(controller, "_reservations", return_value={}), \
                self.fake_foreground(controller, before=lose_the_lock):
            with self.assertRaises(TimeoutError):
                controller.run(max_actions=4)

        self.assertEqual([], deferrals)
        self.assertEqual(["action_started", "action_failed"], self.action_events(controller))
        state = _read(controller.state_path)
        self.assertEqual("blocked", state["status"])
        self.assertIn("timed out after 0.1s waiting for exclusive file lock",
                      state["last_error"])

    def test_a_deferred_launch_leaves_no_ticket_index_or_run_root(self):
        """Every deferral, and the fatal attempt after the bound, wrote nothing."""
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.settled_worker_record("NSC-1101")
        self.host.schedule("post_crew", "NSC-1101", 5.0, self.validated_candidate)
        record_path = self.records / "NSC-1101.json"
        before = record_path.read_bytes()
        self.hold_checkouts_lock()
        deferrals = self.watch_deferrals(controller)

        with self.fake_foreground(controller), self.worker_exits_at({}), \
                patch.object(background_jobs, "LAUNCH_LOCK_TIMEOUT_SECONDS", 0.1):
            with self.assertRaises(TimeoutError):
                controller.run(max_actions=4)

        self.assertEqual(LOCK_DEFERRAL_LIMIT, len(deferrals))
        self.assertEqual([([], [], 0)] * LOCK_DEFERRAL_LIMIT,
                         [(item["indexes"], item["job_roots"], item["launches"])
                          for item in deferrals])
        self.assertEqual({}, background_jobs.list_indexes(self.manager))
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-1101"))
        self.assertFalse((background_jobs.jobs_root(self.manager) / "NSC-1101").exists())
        self.assertFalse((self.records / "candidate-receipts").exists())
        self.assertEqual([], self.host.launches)
        self.assertEqual(before, record_path.read_bytes())

    def test_a_lock_contended_sync_candidate_is_deferred_not_fatal(self):
        """A foreground Source-lane action is deferred too (20260913, 02:50:47Z)."""
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.validated_awaiting_human("NSC-1101", source_commit="0" * 40)
        self.assertEqual(["sync_candidate"],
                         [item["kind"] for item in controller.plan()["next_actions"]])
        self.deferred_foreground_action(controller, "sync_candidate")

    def test_a_lock_contended_auto_approve_is_deferred_not_fatal(self):
        """The other observed foreground casualty (20260913, 02:51:32Z)."""
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.validated_awaiting_human("NSC-1101")
        self.assertEqual(["auto_approve"],
                         [item["kind"] for item in controller.plan()["next_actions"]])
        self.deferred_foreground_action(controller, "auto_approve")

    def deferred_foreground_action(self, controller: GraphController, kind: str) -> None:
        """One foreground action loses a real `checkouts.lock` wait, then runs next cycle.

        The production step for each of these kinds takes `checkouts.lock` as its
        first effect (see LOCK_DEFERRABLE_ACTION_KINDS), so the fixture reproduces
        that acquisition, with its exact exception, from the fixture foreground.
        """
        attempts: list[str] = []
        deferrals = self.watch_deferrals(controller, free_lock=self.hold_checkouts_lock())

        def lose_the_lock_once(action):
            attempts.append(action["kind"])
            if len(attempts) == 1:
                with _exclusive_file_lock(self.records / "checkouts.lock", timeout_seconds=0.2):
                    raise AssertionError("the fixture must never take the held lock")

        with self.fake_foreground(controller, before=lose_the_lock_once), \
                self.worker_exits_at({}):
            result = controller.run(max_actions=1)

        self.assertEqual([kind, kind], attempts)
        self.assertEqual([kind], [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertNotIn("action_failed", self.action_events(controller))
        self.assertEqual(1, len(deferrals))
        self.assertEqual(("running", None),
                         (deferrals[0]["state"]["status"], deferrals[0]["state"]["last_error"]))
        self.assertEqual(
            (kind, "lock_contention", 1),
            (result["lock_deferrals"][0]["kind"], result["lock_deferrals"][0]["reason"],
             result["lock_deferrals"][0]["deferrals"]),
        )
        self.assertEqual([], [item for item in result["blocked"]
                              if item["task_id"] == "NSC-1101"])

    def test_a_childs_own_lock_timeout_stays_a_harvested_job_failure(self):
        """The child side keeps its own path: a failed job, not a deferral.

        Three of the four 20260913 lock timeouts were controller actions and
        ended their invocations with status `blocked` and exit 1; the fourth was a
        post-crew *child* losing the same lock, which is journaled `job_failed`
        from its receipt, blocks only its task and lets the invocation continue.
        The deferral must not touch that path.
        """
        self.commit_task("NSC-1101")
        controller = self.controller("NSC-1101")
        self.settled_worker_record("NSC-1101")
        error = (f"TimeoutError: [Errno {errno.ETIMEDOUT}] timed out after 10s waiting for "
                 f"exclusive file lock: {str(self.records / 'checkouts.lock')!r}")

        def child_lost_the_lock(run_root, request, identity):
            write_receipt(run_root, request, identity, status="failed", error=error)

        self.host.schedule("post_crew", "NSC-1101", 3.0, child_lost_the_lock)
        deferrals = self.watch_deferrals(controller)

        with self.fake_foreground(controller), self.worker_exits_at({}):
            result = controller.run(max_actions=3)

        self.assertEqual(["post_crew", "wait_job"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertEqual([], deferrals)
        self.assertEqual([], result["lock_deferrals"])
        self.assertNotIn("action_deferred", [event["event"] for event
                                             in _events(controller.event_path)])
        self.assertNotIn("action_failed", self.action_events(controller))
        self.assertEqual(["job_launched", "job_failed"],
                         [event["event"] for event in _events(controller.event_path)
                          if event["event"].startswith("job_")])
        blocked = {item["task_id"]: item for item in result["blocked"]}
        self.assertEqual("background_job_failed", blocked["NSC-1101"]["reason"])
        self.assertEqual(error, blocked["NSC-1101"]["error"])
        self.assertEqual("failed", background_jobs.read_index(self.manager, "NSC-1101")["status"])
        # The invocation returned instead of raising, and recorded no last_error.
        self.assertIsNone(_read(controller.state_path)["last_error"])

    def test_keyboard_interrupt_cancels_all_active_jobs_and_they_are_never_relaunched(self):
        for task_id in ("NSC-1101", "NSC-1102"):
            self.commit_task(task_id)
        controller = self.controller("NSC-1101", "NSC-1102")
        controller.stop_grace_seconds = 0.0
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.task_record("NSC-1102", worker_status="succeeded", run_id="run-1102")
        for task_id in ("NSC-1101", "NSC-1102"):
            self.host.schedule("post_crew", task_id, 100.0, self.validated_candidate)
        real_plan = controller.plan
        plans: list[dict] = []

        def plan():
            result = real_plan()
            plans.append(result)
            if len(plans) == 5:  # both workers settled, both validations launched
                raise KeyboardInterrupt()
            return result

        with self.fake_foreground(controller), self.worker_exits_at({}), \
                patch.object(controller, "plan", side_effect=plan):
            with self.assertRaises(KeyboardInterrupt):
                controller.run(max_actions=10)

        self.assertEqual(["NSC-1101", "NSC-1102"],
                         sorted(item["task_id"] for item in self.host.launches))
        for task_id in ("NSC-1101", "NSC-1102"):
            index = background_jobs.read_index(self.manager, task_id)
            self.assertEqual("cancelled", index["status"])
            self.assertEqual("operator interrupted graph controller", index["stop"]["reason"])
            self.assertEqual(index["job_name"], self.host.children[index["pid"]]["stopped"])
            self.assertIn("without a receipt", index["error"])
            payload = _read(Path(index["stop_request"]))
            self.assertEqual((index["job_id"], index["pid"], index["process_identity"], index["job_name"]),
                             (payload["job_id"], payload["pid"], payload["process_identity"], payload["job_name"]))
        state = _read(controller.state_path)
        self.assertEqual("interrupted", state["status"])
        self.assertEqual(["cancelled", "cancelled"],
                         [item["status"] for item in state["background_stops"]])
        stopped_events = [event for event in _events(controller.event_path) if event["event"] == "job_stopped"]
        self.assertEqual(["NSC-1101", "NSC-1102"], [event["task_id"] for event in stopped_events])
        released = _read(controller.owner_path)
        self.assertEqual(("controller_released", "interrupted"), (released["status"], released["outcome"]))

        # A later invocation neither relaunches the stopped tickets nor mistakes
        # the operator stop for a provider failure.
        resumed = self.controller("NSC-1101", "NSC-1102")
        with self.fake_foreground(resumed), self.worker_exits_at({}):
            result = resumed.run(max_actions=1)
        self.assertEqual("blocked", result["status"])
        self.assertEqual({"NSC-1101": "background_job_cancelled", "NSC-1102": "background_job_cancelled"},
                         {item["task_id"]: item["reason"] for item in result["blocked"]})
        self.assertEqual(2, len(self.host.launches))
        self.assertEqual([], result["harvested_jobs"])

    def test_stop_background_jobs_cli_refuses_while_a_controller_owns_the_graph(self):
        from Pipeline.AssistantControl import __main__ as assistant_cli
        from Pipeline.TaskReviewAgent.execution_session_pool import (
            _acquire_liveness_lock,
            _release_liveness_lock,
        )
        arguments = ["--source", str(self.source), "--checkout-root", str(self.manager.root),
                     "stop-background-jobs", "--grace-seconds", "0"]
        held = _acquire_liveness_lock(self.records / "graph-controller.lock")
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = assistant_cli.main(arguments)
        finally:
            _release_liveness_lock(held)
        self.assertEqual(1, code)
        self.assertIn("interrupt it instead", json.loads(output.getvalue())["error"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = assistant_cli.main(arguments)
        self.assertEqual(0, code)
        self.assertEqual({"status": "stopped", "jobs": [], "cleanup_pending": [],
                          "retry_after_utc": [], "unreadable_indexes": []},
                         json.loads(output.getvalue()))

    def _bound_stop(self, controller: GraphController, **fields) -> dict:
        return {
            "schema_version": STOP_REQUEST_SCHEMA,
            "invocation_id": controller._active_invocation_id, "pid": os.getpid(),
            "process_identity": controller._process_identity, "reason": "fixture stop",
            "grace_seconds": 0, "requested_at_utc": "fixture", **fields,
        }

    def test_bound_stop_request_stops_the_controller_and_cancels_its_jobs(self):
        for task_id in ("NSC-1101", "NSC-1102"):
            self.commit_task(task_id)
        controller = self.controller("NSC-1101", "NSC-1102")
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.task_record("NSC-1102", worker_status="succeeded", run_id="run-1102")
        for task_id in ("NSC-1101", "NSC-1102"):
            self.host.schedule("post_crew", task_id, 100.0, self.validated_candidate)
        written: list[float] = []

        def request_stop_at_two_seconds():
            if self.clock() >= 2.0 and not written and controller._active_invocation_id:
                write_record(controller.stop_path, self._bound_stop(controller))
                written.append(self.clock())

        self.clock.listeners.append(request_stop_at_two_seconds)
        with self.fake_foreground(controller), self.worker_exits_at({}):
            result = controller.run(max_actions=20)

        self.assertEqual("stopped", result["status"])
        self.assertEqual([2.0], written)
        self.assertEqual(["settle_worker", "settle_worker", "post_crew", "post_crew", "wait_job"],
                         [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertEqual("stop_requested", result["completed_actions"][-1]["result"]["status"])
        self.assertEqual(["cancelled", "cancelled"], [item["status"] for item in result["background_stops"]])
        self.assertEqual([False, False], [item["cleanup_pending"] for item in result["background_stops"]])
        self.assertEqual([], result["cleanup_pending"])
        self.assertEqual("fixture stop", result["stop_request"]["reason"])
        self.assertTrue(Path(result["stop_request"]["archived"]).is_file())
        self.assertFalse(controller.stop_path.exists())
        for task_id in ("NSC-1101", "NSC-1102"):
            index = background_jobs.read_index(self.manager, task_id)
            self.assertEqual(("cancelled", "fixture stop"), (index["status"], index["stop"]["reason"]))
            self.assertEqual(index["job_name"], self.host.children[index["pid"]]["stopped"])
        events = [event["event"] for event in _events(controller.event_path)]
        self.assertEqual(1, events.count("controller_stopped"))
        self.assertEqual(2, events.count("job_stopped"))
        state = _read(controller.state_path)
        self.assertEqual(("stopped", 2), (state["status"], len(state["background_stops"])))
        released = _read(controller.owner_path)
        self.assertEqual(("controller_released", "returned"), (released["status"], released["outcome"]))
        # Nothing is relaunched afterwards and the stop does not read as a failure.
        again = self.controller("NSC-1101", "NSC-1102")
        with self.fake_foreground(again), self.worker_exits_at({}):
            after = again.run(max_actions=1)
        self.assertEqual({"NSC-1101": "background_job_cancelled", "NSC-1102": "background_job_cancelled"},
                         {item["task_id"]: item["reason"] for item in after["blocked"]})
        self.assertEqual(2, len(self.host.launches))

    def test_unbound_or_stale_stop_requests_are_archived_and_ignored(self):
        controller = self.controller("NSC-899")
        write_record(controller.stop_path, {
            "schema_version": STOP_REQUEST_SCHEMA, "invocation_id": "not-this-invocation",
            "pid": os.getpid(), "process_identity": {"pid": os.getpid()}, "reason": "stale",
        })
        with self.fake_foreground(controller, real_kinds=("prepare",)), self.worker_exits_at({}):
            result = controller.run(max_actions=1)
        self.assertEqual("action_limit_reached", result["status"])
        self.assertEqual(["prepare"], [item["action"]["kind"] for item in result["completed_actions"]])
        self.assertFalse(controller.stop_path.exists())
        self.assertEqual(1, len(list(self.records.glob("graph-controller.stop.stale-*.json"))))
        ignored = [event for event in _events(controller.event_path) if event["event"] == "stop_request_ignored"]
        self.assertEqual(["not-this-invocation"], [event["request_invocation_id"] for event in ignored])

        # Binding is exact: invocation, pid and full process identity must all match.
        controller._active_invocation_id = "live"
        controller._process_identity = {"pid": os.getpid(), "created_ticks": 5, "image": "fixture"}
        bound = {"schema_version": STOP_REQUEST_SCHEMA, "invocation_id": "live", "pid": os.getpid(),
                 "process_identity": dict(controller._process_identity), "reason": "x"}
        write_record(controller.stop_path, bound)
        self.assertIsNotNone(controller._bound_stop_request())
        for field, value in (("invocation_id", "other"), ("pid", os.getpid() + 1),
                             ("process_identity", {**bound["process_identity"], "created_ticks": 6}),
                             ("schema_version", "assistant-graph-controller-stop/v0")):
            write_record(controller.stop_path, {**bound, field: value})
            self.assertIsNone(controller._bound_stop_request(), field)
        controller.stop_path.unlink()

    def test_stop_graph_cli_refuses_without_a_live_owner_and_binds_to_a_live_one(self):
        from Pipeline.AssistantControl import __main__ as assistant_cli
        from Pipeline.TaskReviewAgent.execution_session_pool import (
            _acquire_liveness_lock,
            _release_liveness_lock,
        )
        arguments = ["--source", str(self.source), "--checkout-root", str(self.manager.root),
                     "stop-graph", "--wait-seconds", "0", "--grace-seconds", "0", "--reason", "fixture"]

        def run_cli() -> tuple[int, dict]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = assistant_cli.main(arguments)
            return code, json.loads(output.getvalue())

        code, payload = run_cli()
        self.assertEqual(1, code)
        self.assertIn("nothing to stop", payload["error"])

        owner_path = self.records / "graph-controller-owner.json"
        identity = {"pid": os.getpid(), "created_ticks": 9, "image": "fixture"}
        write_record(owner_path, {"status": "controller_started", "invocation_id": "live-owner",
                                  "pid": os.getpid(), "process_identity": identity})
        code, payload = run_cli()
        self.assertEqual(1, code)
        self.assertIn("stale", payload["error"])
        self.assertFalse((self.records / "graph-controller.stop.json").exists())

        held = _acquire_liveness_lock(self.records / "graph-controller.lock")
        try:
            code, payload = run_cli()
            self.assertEqual((0, "stop_requested", False), (code, payload["status"], payload["repeated"]))
            request = _read(self.records / "graph-controller.stop.json")
            # Repeating the request reuses the bound request instead of rewriting it.
            code, payload = run_cli()
            self.assertEqual((0, "stop_requested", True), (code, payload["status"], payload["repeated"]))
            self.assertEqual(request, _read(self.records / "graph-controller.stop.json"))
            self.assertEqual(request["requested_at_utc"], payload["request"]["requested_at_utc"])
        finally:
            _release_liveness_lock(held)
        self.assertEqual((STOP_REQUEST_SCHEMA, "live-owner", os.getpid(), identity, "fixture", 0.0),
                         (request["schema_version"], request["invocation_id"], request["pid"],
                          request["process_identity"], request["reason"], request["grace_seconds"]))

        # A released owner has nothing left to stop: repeating stop-graph reports
        # the retained outcome instead of failing.
        write_record(owner_path, {"status": "controller_released", "invocation_id": "live-owner",
                                  "outcome": "returned"})
        write_record(self.records / "graph-controller.json", {"status": "stopped", "background_stops": []})
        result = request_stop(self.manager, wait_seconds=0, grace_seconds=0)
        self.assertEqual(("already_released", "stopped", "returned", "live-owner"),
                         (result["status"], result["controller_status"], result["outcome"],
                          result["invocation_id"]))
        code, payload = run_cli()
        self.assertEqual((0, "already_released"), (code, payload["status"]))

    def test_abruptly_killed_controller_is_reconciled_on_restart_without_relaunch(self):
        first = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 1000.0, self.decomposition_result("review_ready"))
        with self.fake_foreground(first):
            launched = first.run(max_actions=1)
        self.assertEqual(["decompose"], [item["action"]["kind"] for item in launched["completed_actions"]])
        index = background_jobs.read_index(self.manager, "NSC-1200")
        container = index["provider_container"]
        # The ticket fixed the exact container, and the labels binding it to
        # this checkout, before Docker could start.
        self.assertEqual({"name": background_jobs.container_name_for(index["job_id"]),
                          "compose_project": "nosafecircle",
                          "labels": background_jobs.container_labels_for(
                              index["job_id"], self.manager.source, self.manager.root)},
                         container)
        self.assertEqual(container, _read(Path(index["request"]))["provider_container"])
        self.host.docker_cli.create(container["name"], "nosafecircle")
        # The controller process died without releasing: its owner record still
        # says started while its lock is free; the child and its container live on.
        write_record(first.owner_path, {**_read(first.owner_path), "status": "controller_started"})

        second = self.controller("NSC-1200")
        with self.fake_foreground(second):
            adopted = second.run(max_actions=1, allowed_actions=frozenset({"prepare"}))
        self.assertEqual("handoff_required", adopted["status"])
        self.assertEqual("wait_job", adopted["handoff_action"]["kind"])
        self.assertEqual([(index["process_identity"], index["job_name"])], self.host.adopted)
        self.assertEqual(1, len(self.host.launches))
        self.assertEqual([], self.host.docker_cli.calls)  # a live job's container is its own
        second_events = [event["event"] for event in _events(second.event_path)
                         if event["invocation_id"] == _read(second.owner_path)["invocation_id"]
                         and event["event"].startswith("job_")]
        self.assertEqual(["job_adopted"], second_events)

        # The child's identity handshake names other ticket bytes: the live
        # child is quarantined with a bound stop, its exact tree and container
        # ended (the ticket itself still authenticates, so its container may be).
        child_path = Path(index["run_root"]) / "child.identity.json"
        write_record(child_path, {**_read(child_path), "request_sha256": "0" * 64})
        third = self.controller("NSC-1200")
        third.stop_grace_seconds = 0.0
        with self.fake_foreground(third):
            result = third.run(max_actions=1)
        self.assertEqual("blocked", result["status"])
        blocked = result["blocked"][0]
        self.assertEqual(("NSC-1200", "background_job_cancelled"), (blocked["task_id"], blocked["reason"]))
        self.assertEqual("quarantined", blocked["reconciliation"]["outcome"])
        self.assertEqual(["child identity handshake names other ticket bytes"],
                         blocked["reconciliation"]["problems"])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual(index["job_name"], self.host.children[index["pid"]]["stopped"])
        self.assertEqual("restart reconciliation: child identity handshake names other ticket bytes",
                         current["stop"]["reason"])
        self.assertTrue(background_jobs.cleanup_final(current))
        payload = _read(Path(index["stop_request"]))
        self.assertEqual((index["job_id"], index["pid"], index["process_identity"], index["job_name"]),
                         (payload["job_id"], payload["pid"], payload["process_identity"], payload["job_name"]))
        cleanup = current["provider_container_cleanup"]
        self.assertEqual(("verified_absent", self.host.docker_cli.removed), (cleanup["status"], cleanup["removed"]))
        self.assertEqual(1, len(cleanup["removed"]))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.assertEqual(1, len(self.host.launches))
        third_events = [event for event in _events(third.event_path)
                        if event["invocation_id"] == _read(third.owner_path)["invocation_id"]
                        and event["event"].startswith("job_")]
        self.assertEqual(["job_quarantined"], [event["event"] for event in third_events])
        self.assertEqual("verified_absent", third_events[0]["provider_container_cleanup"]["status"])

    def test_dead_decomposition_child_refuses_startup_until_its_container_is_verified_absent(self):
        first = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 100.0, self.decomposition_result("review_ready"))
        with self.fake_foreground(first):
            first.run(max_actions=1)
        index = background_jobs.read_index(self.manager, "NSC-1200")
        name = index["provider_container"]["name"]
        self.host.kill("NSC-1200")  # crashed without a receipt; its container is still there
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.available = False

        second = self.controller("NSC-1200")
        with self.fake_foreground(second), \
                self.assertRaisesRegex(background_jobs.StartupRefused, "not verified absent"):
            second.run(max_actions=1)
        self.assertEqual("blocked", _read(second.state_path)["status"])
        self.assertIn("not verified absent", _read(second.state_path)["last_error"])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual(("died", "refused"), (current["status"], current["provider_container_cleanup"]["status"]))
        self.assertIn("Docker Desktop is not running", current["provider_container_cleanup"]["error"])
        self.assertEqual({name}, set(self.host.docker_cli.containers))
        events = [event["event"] for event in _events(second.event_path)
                  if event["invocation_id"] == _read(second.owner_path)["invocation_id"]]
        self.assertEqual(["controller_started", "job_died", "startup_refused", "controller_released"], events)
        self.assertEqual(("controller_released", "exception"),
                         (_read(second.owner_path)["status"], _read(second.owner_path)["outcome"]))
        self.assertEqual(1, len(self.host.launches))

        # Docker is back: startup re-verifies the pending cleanup, removes
        # exactly that container, and only then plans; the task stays blocked
        # by its died ticket until an operator clears it.
        self.host.docker_cli.available = True
        before_third = self.clock()
        third = self.controller("NSC-1200")
        with self.fake_foreground(third):
            result = third.run(max_actions=1)
        self.assertEqual("blocked", result["status"])
        self.assertEqual([("NSC-1200", "background_job_died")],
                         [(item["task_id"], item["reason"]) for item in result["blocked"]])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        cleanup = current["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 1), (cleanup["status"], len(cleanup["removed"])))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.assertEqual(1, len(self.host.launches))
        third_events = [event["event"] for event in _events(third.event_path)
                        if event["invocation_id"] == _read(third.owner_path)["invocation_id"]
                        and event["event"].startswith("job_")]
        self.assertEqual(["job_container_verified"], third_events)
        # Startup waited the Docker operation bound out and recorded the final
        # recheck before it planned: the cleanup is final, not merely verified.
        self.assertTrue(background_jobs.cleanup_final(current))
        self.assertIsNotNone(cleanup["final_recheck_at_utc"])
        self.assertGreaterEqual(self.clock() - before_third, background_jobs.CONTAINER_TOMBSTONE_SECONDS)
        cleared = background_jobs.clear(self.manager, "NSC-1200", job_id=index["job_id"], host=self.host,
                                        clock=self.clock, sleep=self.clock.sleep)
        self.assertTrue(cleared["cleared"])

    def test_superseded_cleanup_generation_rereads_durable_state_instead_of_failing_the_controller(self):
        controller = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 1000.0, self.decomposition_result("review_ready"))
        killed: list[float] = []

        def kill_at_five():
            if self.clock() >= 5.0 and not killed:
                self.host.kill("NSC-1200")
                killed.append(self.clock())

        self.clock.listeners.append(kill_at_five)
        superseded: list[dict] = []

        def concurrent_clear_took_the_cleanup_over(arguments):
            # While the controller's reconciliation is running unlocked, a
            # concurrent clear-background-job (whose process then died) took
            # the cleanup over with a newer generation.
            if superseded:
                return
            current = background_jobs.read_index(self.manager, "NSC-1200")
            cleanup = current["provider_container_cleanup"]
            self.assertEqual(("in_progress", 1), (cleanup["status"], cleanup["generation"]))
            current["provider_container_cleanup"] = {
                **cleanup, "generation": 2,
                "owner": {"pid": 4000000000,
                          "process_identity": {"pid": 4000000000, "created_ticks": 1, "image": "gone"}},
            }
            write_record(background_jobs.index_path(self.manager, "NSC-1200"), current)
            superseded.append(dict(cleanup))

        self.host.docker_cli.on_call = concurrent_clear_took_the_cleanup_over
        with self.fake_foreground(controller):
            result = controller.run(max_actions=3)
        self.assertEqual([5.0], killed)
        self.assertEqual(["decompose", "wait_job"], [item["action"]["kind"] for item in result["completed_actions"]])
        # The controller kept going: the superseded result was discarded and the
        # durable state reread; the died ticket blocks only its task.
        self.assertEqual("blocked", result["status"])
        self.assertEqual([("NSC-1200", "background_job_died")],
                         [(item["task_id"], item["reason"]) for item in result["blocked"]])
        state = _read(controller.state_path)
        self.assertEqual(("blocked", None), (state["status"], state["last_error"]))
        events = [event["event"] for event in _events(controller.event_path)]
        self.assertIn("job_died", events)
        self.assertNotIn("startup_refused", events)
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual(("died", "in_progress", 2), (current["status"], current["provider_container_cleanup"]["status"],
                                                      current["provider_container_cleanup"]["generation"]))
        self.assertEqual(1, len(superseded))

        # The next controller takes the abandoned generation over (its owner is
        # gone), verifies the exact name, waits the bound out and finalizes.
        self.host.docker_cli.on_call = None
        again = self.controller("NSC-1200")
        with self.fake_foreground(again):
            second = again.run(max_actions=1)
        self.assertEqual("blocked", second["status"])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertTrue(background_jobs.cleanup_final(current))
        self.assertEqual("verified_absent", current["provider_container_cleanup"]["status"])
        again_events = [event["event"] for event in _events(again.event_path)
                        if event["invocation_id"] == _read(again.owner_path)["invocation_id"]
                        and event["event"].startswith("job_")]
        self.assertEqual(["job_container_verified"], again_events)
        self.assertEqual(1, len(self.host.launches))

    def test_repeated_stop_graph_after_release_reports_incomplete_cleanup_with_exit_1(self):
        from Pipeline.AssistantControl import __main__ as assistant_cli
        controller = self.controller("NSC-1200")
        controller.stop_grace_seconds = 0.0
        self.host.schedule("decompose", "NSC-1200", 1000.0, self.decomposition_result("review_ready"))
        written: list[float] = []

        def request_stop_at_two_seconds():
            if self.clock() >= 2.0 and not written and controller._active_invocation_id:
                write_record(controller.stop_path, self._bound_stop(controller))
                written.append(self.clock())

        self.clock.listeners.append(request_stop_at_two_seconds)
        self.host.docker_cli.available = False  # Docker unreachable while the stop runs
        with self.fake_foreground(controller):
            result = controller.run(max_actions=5)
        self.assertEqual(("stopped", ["NSC-1200"]), (result["status"], result["cleanup_pending"]))
        self.assertTrue(result["background_stops"][0]["cleanup_pending"])
        self.assertEqual("refused", result["background_stops"][0]["provider_container_cleanup"]["status"])

        # Repeating stop-graph after the release does not claim success.
        outcome = request_stop(self.manager, wait_seconds=0, grace_seconds=0)
        self.assertEqual(("already_released_cleanup_pending", ["NSC-1200"]),
                         (outcome["status"], outcome["cleanup_pending"]))
        self.assertIn("stop-background-jobs", outcome["note"])
        arguments = ["--source", str(self.source), "--checkout-root", str(self.manager.root)]

        def run_cli(*command: str) -> tuple[int, dict]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), \
                    patch.object(background_jobs, "DetachedHost", lambda: self.host), \
                    patch.object(background_jobs, "CONTAINER_WINDOW_SECONDS", 0.0), \
                    patch.object(background_jobs, "CONTAINER_SETTLE_SECONDS", 0.0):
                code = assistant_cli.main([*arguments, *command])
            return code, json.loads(output.getvalue())

        code, payload = run_cli("stop-graph", "--wait-seconds", "0", "--grace-seconds", "0")
        self.assertEqual((1, "already_released_cleanup_pending", ["NSC-1200"]),
                         (code, payload["status"], payload["cleanup_pending"]))

        # stop-background-jobs finishes it once Docker answers: exact retry,
        # the bound passed, the final recheck recorded, exit 0.
        self.host.docker_cli.available = True
        self.pass_tombstone()
        code, payload = run_cli("stop-background-jobs", "--grace-seconds", "0")
        self.assertEqual((0, "stopped", []), (code, payload["status"], payload["cleanup_pending"]))
        self.assertEqual([("NSC-1200", "cancelled", False)],
                         [(item["task_id"], item["status"], item["cleanup_pending"]) for item in payload["jobs"]])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertTrue(background_jobs.cleanup_final(current))
        self.assertEqual("already_released", request_stop(self.manager, wait_seconds=0, grace_seconds=0)["status"])
        self.assertEqual(1, len(self.host.launches))

    def test_concurrent_clear_during_cleanup_does_not_abort_the_controller(self):
        """Finding 3: a clear that lands while the controller's final cleanup recheck
        runs unlocked must be journaled and skipped, never raised into the loop."""
        controller = self.controller("NSC-1200")
        self.host.schedule("decompose", "NSC-1200", 1000.0, self.decomposition_result("review_ready"))
        killed: list[float] = []

        def kill_at_five():
            if self.clock() >= 5.0 and not killed:
                self.host.kill("NSC-1200")
                killed.append(self.clock())

        self.clock.listeners.append(kill_at_five)
        with self.fake_foreground(controller):
            first = controller.run(max_actions=3)
        self.assertEqual("blocked", first["status"])
        current = background_jobs.read_index(self.manager, "NSC-1200")
        self.assertEqual(("died", True), (current["status"], background_jobs.cleanup_pending(current)))
        self.pass_tombstone()

        # A concurrent clear-background-job archives the index while the next
        # controller's exact look runs without the lock.
        index_file = background_jobs.index_path(self.manager, "NSC-1200")

        def clear_during_the_unlocked_look(arguments):
            self.host.docker_cli.on_call = None
            index_file.unlink()

        self.host.docker_cli.on_call = clear_during_the_unlocked_look
        # NSC-1200 is not a target of this controller, so nothing relaunches it.
        again = self.controller("NSC-899")
        with self.fake_foreground(again, real_kinds=("prepare",)), self.worker_exits_at({}):
            second = again.run(max_actions=1)
        state = _read(again.state_path)
        self.assertIsNone(state["last_error"])  # no exception reached the loop
        self.assertNotEqual("command_failed", second["status"])
        invocation = _read(again.owner_path)["invocation_id"]
        events = [event["event"] for event in _events(again.event_path)
                  if event["invocation_id"] == invocation]
        self.assertIn("job_cleanup_superseded", events)
        self.assertNotIn("startup_refused", events)
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-1200"))
        self.assertEqual(1, len(self.host.launches))

    def test_unreadable_pending_index_never_reports_a_released_stop_graph_as_finished(self):
        """Finding 4: an unreadable, truncated or malformed background-job index must
        never read as "nothing remains". stop-graph and stop-background-jobs fail
        closed with a nonzero exit and the exact diagnostics, a controller start
        refuses, and nothing is deleted or repaired automatically."""
        from Pipeline.AssistantControl import __main__ as assistant_cli
        controller = self.controller("NSC-1200")
        controller.stop_grace_seconds = 0.0
        self.host.schedule("decompose", "NSC-1200", 1000.0, self.decomposition_result("review_ready"))
        written: list[float] = []

        def request_stop_at_two_seconds():
            if self.clock() >= 2.0 and not written and controller._active_invocation_id:
                write_record(controller.stop_path, self._bound_stop(controller))
                written.append(self.clock())

        self.clock.listeners.append(request_stop_at_two_seconds)
        with self.fake_foreground(controller):
            self.assertEqual("stopped", controller.run(max_actions=5)["status"])
        arguments = ["--source", str(self.source), "--checkout-root", str(self.manager.root)]

        def run_cli(*command: str) -> tuple[int, dict]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), \
                    patch.object(background_jobs, "DetachedHost", lambda: self.host), \
                    patch.object(background_jobs, "CONTAINER_WINDOW_SECONDS", 0.0), \
                    patch.object(background_jobs, "CONTAINER_SETTLE_SECONDS", 0.0):
                code = assistant_cli.main([*arguments, *command])
            return code, json.loads(output.getvalue())

        # Finish the container cleanup first, so only the record itself is at issue.
        self.pass_tombstone()
        code, payload = run_cli("stop-background-jobs", "--grace-seconds", "0")
        self.assertEqual((0, "stopped"), (code, payload["status"]))
        self.assertEqual("already_released",
                         request_stop(self.manager, wait_seconds=0, grace_seconds=0)["status"])

        index_file = background_jobs.index_path(self.manager, "NSC-1200")
        genuine = index_file.read_bytes()
        for label, payload in (
                ("empty", b""),
                ("truncated", genuine[: len(genuine) // 2]),
                ("not an object", b"[]"),
                ("other identity", b'{"schema_version": "assistant-background-job/v1"}'),
        ):
            with self.subTest(index=label):
                index_file.write_bytes(payload)
                outcome = request_stop(self.manager, wait_seconds=0, grace_seconds=0)
                self.assertEqual("already_released_cleanup_pending", outcome["status"])
                self.assertEqual([("NSC-1200", str(index_file))],
                                 [(item["task_id"], item["path"])
                                  for item in outcome["unreadable_indexes"]])
                self.assertIn("cannot be read or authenticated", outcome["note"])
                self.assertIn(str(index_file), outcome["note"])

                code, reported = run_cli("stop-graph", "--wait-seconds", "0", "--grace-seconds", "0")
                self.assertEqual((1, "already_released_cleanup_pending"), (code, reported["status"]))
                self.assertEqual(str(index_file), reported["unreadable_indexes"][0]["path"])

                code, reported = run_cli("stop-background-jobs", "--grace-seconds", "0")
                self.assertEqual((1, "cleanup_pending"), (code, reported["status"]))
                self.assertEqual(("NSC-1200", str(index_file)),
                                 (reported["unreadable_indexes"][0]["task_id"],
                                  reported["unreadable_indexes"][0]["path"]))
                self.assertTrue(reported["unreadable_indexes"][0]["error"])
                self.assertEqual([("NSC-1200", "unreadable_index", True)],
                                 [(item["task_id"], item["status"], item["cleanup_pending"])
                                  for item in reported["jobs"]])
                # Nothing was deleted, rewritten or "repaired".
                self.assertEqual(payload, index_file.read_bytes())

        # A controller start refuses to plan beside a record it cannot authenticate.
        refused = self.controller("NSC-1200")
        with self.fake_foreground(refused), self.assertRaises(background_jobs.StartupRefused):
            refused.run(max_actions=1)
        startup = [event for event in _events(refused.event_path)
                   if event["event"] == "startup_refused"]
        self.assertIn(str(index_file), startup[-1]["error"])
        self.assertEqual(b'{"schema_version": "assistant-background-job/v1"}',
                         index_file.read_bytes())

        # Repaired by hand, the same commands report finished again.
        index_file.write_bytes(genuine)
        self.assertEqual("already_released",
                         request_stop(self.manager, wait_seconds=0, grace_seconds=0)["status"])
        code, payload = run_cli("stop-background-jobs", "--grace-seconds", "0")
        self.assertEqual((0, "stopped", [], []),
                         (code, payload["status"], payload["cleanup_pending"],
                          payload["unreadable_indexes"]))
        code, payload = run_cli("stop-graph", "--wait-seconds", "0", "--grace-seconds", "0")
        self.assertEqual((0, "already_released"), (code, payload["status"]))
        self.assertEqual(1, len(self.host.launches))

    def test_background_job_limit_and_worker_capacity_remain_enforced(self):
        for task_id in ("NSC-1101", "NSC-1102"):
            self.commit_task(task_id)
        controller = self.controller("NSC-1101", "NSC-1102", limit=1)
        self.task_record("NSC-1101", worker_status="succeeded", run_id="run-1101")
        self.task_record("NSC-1102", worker_status="succeeded", run_id="run-1102")
        for task_id in ("NSC-1101", "NSC-1102"):
            self.host.schedule("post_crew", task_id, 10.0, self.validated_candidate)
        with self.fake_foreground(controller), self.worker_exits_at({}):
            result = controller.run(max_actions=5)
        self.assertEqual([
            ("settle_worker", "NSC-1101"), ("settle_worker", "NSC-1102"),
            ("post_crew", "NSC-1101"), ("wait_job", "NSC-1101"), ("post_crew", "NSC-1102"),
        ], [(item["action"]["kind"], item["action"]["task_id"])
            for item in result["completed_actions"]])
        self.assertEqual([0.0, 10.0], [item["at"] for item in self.host.launches])

        capacity = self.controller("NSC-899")
        reservation = {"task_id": "NSC-1010"}
        plan = {"next_actions": [
            {"kind": "reserve", "task_id": "NSC-899", "run_id": "new-run"},
            {"kind": "wait_job", "task_id": "NSC-1101", "job_id": "j", "job_kind": "post_crew"},
        ]}
        with patch.object(capacity, "_reservations", return_value={"NSC-1010": reservation}), \
                patch.object(capacity, "_resource_overlap_action", return_value=None):
            self.assertEqual("wait_job", capacity._next_run_action(plan)["kind"])

    def test_legacy_synchronous_state_reads_and_plans_safely(self):
        write_record(self.records / "graph-controller.json", {
            "schema_version": "assistant-graph-controller/v1", "status": "running",
            "invocation_id": "legacy", "targets": ["NSC-1200"], "human_review_tasks": ["NSC-042"],
            "auto_approve_gauntlet": True,
            "current_action": {"kind": "decompose", "task_id": "NSC-1200"},
            "last_error": None, "history": [{"legacy": True}], "updated_at": "legacy",
        })
        write_record(self.records / "NSC-1200.decomposition.json", {
            "schema_version": "assistant-decomposition/v1", "task_id": "NSC-1200",
            "run_id": "legacy-run", "source": str(self.manager.source),
            "source_commit": self.head, "status": "running",
        })
        controller = self.controller("NSC-1200")
        plan = controller.plan()
        self.assertEqual([], plan["background_jobs"])
        self.assertEqual([{"task_id": "NSC-1200", "reason": "decomposition_already_running"}],
                         plan["blocked"])
        with self.fake_foreground(controller):
            result = controller.run(max_actions=1)
        self.assertEqual("blocked", result["status"])
        self.assertEqual([], result["harvested_jobs"])
        self.assertEqual(0, len(self.host.launches))
        state = _read(controller.state_path)
        self.assertEqual([{"legacy": True}], state["history"])
        self.assertEqual([], state["background_jobs"])


class BackgroundJobMechanismTests(unittest.TestCase):
    """Ticket, receipt, liveness and clearing semantics of the job records."""

    setUp = _graph_tests.GraphControllerTests.setUp
    git = _graph_tests.GraphControllerTests.git
    write_task = _graph_tests.GraphControllerTests.write_task

    def prepare(self):
        self.clock = FixtureClock()
        self.host = FixtureHost(self.clock)
        self.manager.records.mkdir(parents=True, exist_ok=True)
        wall = patch.object(background_jobs, "_utc_now", self.clock.utc, create=True)
        wall.start()
        self.addCleanup(wall.stop)

    def pass_tombstone(self) -> None:
        """Let the Docker operation bound of every tombstone pass on the fixture clock."""
        self.clock.sleep(background_jobs.CONTAINER_TOMBSTONE_SECONDS + 1.0)

    def launch(self, kind="post_crew", task_id="NSC-899", duration=5.0, on_complete=None, **overrides):
        self.host.schedule(kind, task_id, duration, on_complete or (
            lambda run_root, request, identity: write_receipt(run_root, request, identity, result={"status": "ok"})
        ))
        arguments = dict(
            kind=kind, task_id=task_id, identity={"crew_run_id": "crew", "candidate_commit": None},
            config={"provider": "claude"}, invocation_id="inv-1",
            provider_spend_authorized=kind == "decompose", host=self.host,
        )
        arguments.update(overrides)
        return background_jobs.launch(self.manager, **arguments)

    def test_second_live_job_for_a_task_is_refused_and_attempts_are_counted(self):
        self.prepare()
        index = self.launch()
        self.assertEqual(("running", 1), (index["status"], index["attempt"]))
        request = _read(Path(index["request"]))
        self.assertEqual(hashlib.sha256(Path(index["request"]).read_bytes()).hexdigest(),
                         index["request_sha256"])
        self.assertEqual(request["job_id"], index["job_id"])
        self.assertTrue((Path(index["run_root"]) / "ready.receipt.json").is_file())
        with self.assertRaisesRegex(BackgroundJobError, "already has an active background job"):
            self.launch()
        self.clock.sleep(5.0)
        observed = background_jobs.observe(index, self.host)
        self.assertEqual("completed", observed["status"])
        harvested = background_jobs.harvest(self.manager, index, observed, invocation_id="inv-2")
        self.assertEqual(("completed", "ok", "inv-2"),
                         (harvested["status"], harvested["result_status"], harvested["harvest_invocation_id"]))
        self.assertEqual(harvested, background_jobs.harvest(self.manager, index, observed, invocation_id="inv-3"))
        second = self.launch()
        self.assertEqual((2, "running"), (second["attempt"], second["status"]))
        self.assertNotEqual(index["job_id"], second["job_id"])
        self.assertEqual(index["job_id"], second["history"][-1]["job_id"])

    def test_receipt_must_bind_to_the_exact_ticket(self):
        self.prepare()
        index = self.launch(duration=1.0)
        run_root = Path(index["run_root"])
        self.clock.sleep(1.0)
        receipt = _read(run_root / "receipt.json")
        receipt["request_sha256"] = "0" * 64
        write_record(run_root / "receipt.json", receipt)
        self.assertEqual("unverifiable", background_jobs.observe(index, self.host)["status"])
        with self.assertRaisesRegex(BackgroundJobError, "not harvestable"):
            background_jobs.harvest(self.manager, index, background_jobs.observe(index, self.host),
                                    invocation_id="inv")

    def test_forged_receipt_with_correct_ticket_hash_but_wrong_child_identity_is_rejected(self):
        self.prepare()
        index = self.launch(duration=1.0)
        run_root = Path(index["run_root"])
        self.clock.sleep(1.0)
        genuine = _read(run_root / "receipt.json")
        self.assertEqual(index["request_sha256"], genuine["request_sha256"])
        forgeries = (
            {**genuine, "pid": genuine["pid"] + 1},
            {**genuine, "process_identity": {**genuine["process_identity"], "created_ticks": 99}},
            {**genuine, "process_identity": {**genuine["process_identity"], "image": "impostor"}},
            {**genuine, "pid": genuine["pid"] + 1,
             "process_identity": {**genuine["process_identity"], "pid": genuine["pid"] + 1}},
        )
        for forged in forgeries:
            write_record(run_root / "receipt.json", forged)
            observed = background_jobs.observe(index, self.host)
            self.assertEqual("unverifiable", observed["status"], forged)
            self.assertIn("exact child process identity", observed["detail"])
            with self.assertRaisesRegex(BackgroundJobError, "not harvestable"):
                background_jobs.harvest(self.manager, index, observed, invocation_id="inv")
        self.assertEqual("running", background_jobs.read_index(self.manager, "NSC-899")["status"])
        write_record(run_root / "receipt.json", genuine)
        self.assertEqual("completed", background_jobs.observe(index, self.host)["status"])

    def test_stop_request_is_exactly_bound_and_cancels_only_that_job(self):
        self.prepare()
        first = self.launch(task_id="NSC-899", duration=100.0)
        second = self.launch(task_id="NSC-1010", duration=100.0)
        self.assertEqual(background_jobs.job_name_for(Path(first["run_root"])), first["job_name"])
        self.assertNotEqual(first["job_name"], second["job_name"])
        self.assertEqual(first["job_name"], self.host.children[first["pid"]]["handoff"])

        stopped = background_jobs.cancel(
            self.manager, first, host=self.host, reason="fixture operator stop",
            grace_seconds=0, invocation_id="stop-invocation",
        )
        self.assertEqual(("cancelled", "stop-invocation"),
                         (stopped["status"], stopped["harvest_invocation_id"]))
        self.assertIn("without a receipt: fixture operator stop", stopped["error"])
        self.assertEqual("fixture operator stop", stopped["stop"]["reason"])
        self.assertEqual(first["job_name"], self.host.children[first["pid"]]["stopped"])
        payload = _read(Path(first["stop_request"]))
        self.assertEqual({
            "schema_version": background_jobs.STOP_SCHEMA, "task_id": "NSC-899",
            "kind": "post_crew", "job_id": first["job_id"],
            "request_sha256": first["request_sha256"], "pid": first["pid"],
            "process_identity": first["process_identity"], "job_name": first["job_name"],
            "reason": "fixture operator stop",
        }, {key: payload[key] for key in payload if key != "requested_at_utc"})

        # The other job is untouched and still running.
        self.assertEqual("running", background_jobs.observe(second, self.host)["status"])
        self.assertFalse(Path(second["stop_request"]).exists())
        self.assertIsNone(self.host.children[second["pid"]]["stopped"])
        # A stop request carrying another child's identity is refused, not acted on.
        write_record(Path(second["stop_request"]), {**payload, "job_id": second["job_id"],
                                                    "task_id": "NSC-1010",
                                                    "request_sha256": second["request_sha256"],
                                                    "job_name": second["job_name"]})
        with self.assertRaisesRegex(BackgroundJobError, "different identity"):
            background_jobs.request_stop(self.manager, second, reason="again")
        self.assertEqual("running", background_jobs.observe(second, self.host)["status"])
        # A cancelled ticket is terminal and may be cleared, never relaunched by itself.
        cleared = background_jobs.clear(self.manager, "NSC-899", job_id=first["job_id"], host=self.host)
        self.assertTrue(cleared["cleared"])

    def test_cooperative_stop_harvests_the_child_receipt_without_termination(self):
        self.prepare()
        self.host.schedule("post_crew", "NSC-899", 100.0, lambda *_: None, cooperative=True)
        index = background_jobs.launch(
            self.manager, kind="post_crew", task_id="NSC-899",
            identity={"crew_run_id": "crew", "candidate_commit": None},
            config={"provider": "claude"}, invocation_id="inv-1",
            provider_spend_authorized=False, host=self.host,
        )
        stopped = background_jobs.cancel(
            self.manager, index, host=self.host, reason="cooperative", grace_seconds=2.0,
            invocation_id="stop",
        )
        self.assertEqual(("cancelled", "fixture child stopped cooperatively"),
                         (stopped["status"], stopped["error"]))
        self.assertIsNone(self.host.children[index["pid"]]["stopped"])
        self.assertIsNotNone(stopped["receipt_sha256"])
        self.assertEqual("stopped", _read(Path(index["run_root"]) / "receipt.json")["status"])

    def test_child_side_stop_request_must_bind_to_the_exact_child(self):
        self.prepare()
        stop_path = self.manager.records / "fixture.stop.request.json"
        request = {"stop_request": str(stop_path), "task_id": "NSC-899", "kind": "fixture",
                   "job_id": "job", "job_name": "assistant-job-" + "0" * 64}
        identity = {"pid": os.getpid(), "created_ticks": 1, "image": "fixture"}
        self.assertFalse(background_jobs._stop_requested(request, "hash", identity))
        bound = {
            "schema_version": background_jobs.STOP_SCHEMA, "task_id": "NSC-899",
            "kind": "fixture", "job_id": "job", "request_sha256": "hash",
            "pid": os.getpid(), "process_identity": identity,
            "job_name": request["job_name"], "reason": "test",
        }
        write_record(stop_path, bound)
        self.assertTrue(background_jobs._stop_requested(request, "hash", identity))
        for field, value in (("pid", os.getpid() + 1), ("request_sha256", "other"),
                             ("process_identity", {**identity, "created_ticks": 2}),
                             ("job_name", "assistant-job-" + "1" * 64)):
            write_record(stop_path, {**bound, field: value})
            with self.assertRaisesRegex(BackgroundJobError, "not bound to this child"):
                background_jobs._stop_requested(request, "hash", identity)

    def test_child_gone_without_receipt_is_died_and_unbound_child_is_died(self):
        self.prepare()
        index = self.launch(duration=100.0)
        self.host.kill("NSC-899")
        self.assertEqual("died", background_jobs.observe(index, self.host)["status"])
        unbound = {**index, "status": "launched", "process_identity": None}
        self.assertEqual("died", background_jobs.observe(unbound, self.host)["status"])
        harvested = background_jobs.harvest(self.manager, index,
                                            background_jobs.observe(index, self.host), invocation_id="inv")
        self.assertEqual("died", harvested["status"])
        self.assertIn("gone without a receipt", harvested["error"])

    def test_clear_refuses_a_live_job_and_archives_an_ended_one(self):
        self.prepare()
        index = self.launch(duration=3.0)
        with self.assertRaisesRegex(BackgroundJobError, "still running"):
            background_jobs.clear(self.manager, "NSC-899", job_id=index["job_id"], host=self.host)
        self.clock.sleep(3.0)
        background_jobs.harvest(self.manager, index, background_jobs.observe(index, self.host),
                                invocation_id="inv")
        cleared = background_jobs.clear(self.manager, "NSC-899", job_id=index["job_id"], host=self.host)
        self.assertTrue(cleared["cleared"])
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-899"))
        self.assertTrue(Path(cleared["archived"]).is_file())
        self.assertTrue((Path(index["run_root"]) / "receipt.json").is_file())
        relaunched = self.launch()
        self.assertEqual(2, relaunched["attempt"])

    def test_decomposition_ticket_requires_spend_authorization(self):
        self.prepare()
        with self.assertRaisesRegex(BackgroundJobError, "provider-spend authorization"):
            self.launch(kind="decompose", task_id="NSC-898",
                        identity={"run_id": "r", "source_commit": self.head, "providers": ["claude", "codex"],
                                  "compose_project": "p"},
                        provider_spend_authorized=False)
        self.assertEqual([], self.host.launches)
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-898"))

    DECOMPOSE_IDENTITY = {"run_id": "r", "source_commit": "abc123", "providers": ["claude", "codex"],
                          "compose_project": "nosafecircle"}

    def test_stop_during_delayed_container_creation_removes_it_and_verifies_absence(self):
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        self.assertEqual(background_jobs.container_name_for(index["job_id"]), name)
        self.assertEqual({"name": name, "compose_project": "nosafecircle",
                          "labels": background_jobs.container_labels_for(
                              index["job_id"], self.manager.source, self.manager.root)},
                         _read(Path(index["request"]))["provider_container"])
        # Docker lands the container one second after the stop began: after the
        # tree is dead and after the first look at the name.
        self.host.docker_cli.create(name, "nosafecircle", at=self.clock() + 1.0)

        stopped = background_jobs.cancel(
            self.manager, index, host=self.host, reason="race", grace_seconds=0,
            invocation_id="stop", clock=self.clock, sleep=self.clock.sleep,
        )
        self.assertEqual(("cancelled", index["job_name"]),
                         (stopped["status"], self.host.children[index["pid"]]["stopped"]))
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual("verified_absent", cleanup["status"])
        self.assertEqual(name, cleanup["container_name"])
        presence = [item["present"] for item in cleanup["observations"]]
        self.assertEqual([False, False, True], presence[:3])
        self.assertTrue(all(present is False for present in presence[3:]))
        self.assertEqual(1, len(cleanup["removed"]))
        self.assertEqual(cleanup["removed"], self.host.docker_cli.removed)
        self.assertEqual({}, self.host.docker_cli.containers)
        # Absence was held for the whole settle window after the removal.
        removed_at = cleanup["observations"][2]["at"]
        self.assertGreaterEqual(cleanup["observations"][-1]["at"] - removed_at,
                                background_jobs.CONTAINER_SETTLE_SECONDS)
        self.assertLessEqual(cleanup["observations"][-1]["at"], background_jobs.CONTAINER_WINDOW_SECONDS)
        for call in self.host.docker_cli.calls:
            self.assertIn(call[:2], (["container", "inspect"], ["rm", "-f"]))
            self.assertIn(call[-1], {name, *cleanup["removed"]})
        # Repeating the stop while the bound is active takes one exact look and
        # stays pending; after the bound it records the final recheck and is idempotent.
        calls = len(self.host.docker_cli.calls)
        again = background_jobs.cancel(
            self.manager, index, host=self.host, reason="race", grace_seconds=0,
            invocation_id="stop-again", clock=self.clock, sleep=self.clock.sleep,
        )
        self.assertEqual(calls + 1, len(self.host.docker_cli.calls))
        self.assertTrue(background_jobs.cleanup_pending(again))
        self.assertEqual(cleanup["removed"], again["provider_container_cleanup"]["removed"])
        self.pass_tombstone()
        final = background_jobs.cancel(
            self.manager, index, host=self.host, reason="race", grace_seconds=0,
            invocation_id="stop-final", clock=self.clock, sleep=self.clock.sleep,
        )
        self.assertTrue(background_jobs.cleanup_final(final))
        calls = len(self.host.docker_cli.calls)
        self.assertEqual(final, background_jobs.cancel(
            self.manager, index, host=self.host, reason="race", grace_seconds=0,
            invocation_id="stop-again", clock=self.clock, sleep=self.clock.sleep,
        ))
        self.assertEqual(calls, len(self.host.docker_cli.calls))

    def _cancel(self, index, *, reason="stop", invocation_id="stop"):
        return background_jobs.cancel(
            self.manager, index, host=self.host, reason=reason, grace_seconds=0,
            invocation_id=invocation_id, clock=self.clock, sleep=self.clock.sleep,
        )

    def test_container_created_after_the_old_three_second_boundary_is_still_removed(self):
        self.prepare()
        window = background_jobs.CONTAINER_WINDOW_SECONDS
        settle = background_jobs.CONTAINER_SETTLE_SECONDS
        # A create landing at second 4, after three seconds of absence, is
        # inside the monitored window: removed, and the window still ends absent.
        late = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                           identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = late["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle", at=self.clock() + 4.0)
        stopped = self._cancel(late)
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 1), (cleanup["status"], len(cleanup["removed"])))
        self.assertEqual(cleanup["removed"], self.host.docker_cli.removed)
        self.assertEqual({}, self.host.docker_cli.containers)
        presence = [(item["at"], item["present"]) for item in cleanup["observations"]]
        self.assertIn((4.0, True), presence)
        self.assertTrue(all(present is False for at, present in presence if at != 4.0))
        self.assertEqual(window, cleanup["observations"][-1]["at"])
        self.assertGreaterEqual(cleanup["watched_seconds"], window)
        self.assertTrue(background_jobs.tombstone_active(stopped))
        self.assertTrue(background_jobs.cleanup_pending(stopped))  # the final recheck is still owed
        self.assertFalse(background_jobs.cleanup_final(stopped))

        # A sighting late in the window extends the watch until the final
        # stability interval is absent.
        latest = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                             identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        self.host.docker_cli.create(latest["provider_container"]["name"], "nosafecircle",
                                    at=self.clock() + window - 0.5)
        cleanup = self._cancel(latest)["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 1), (cleanup["status"], len(cleanup["removed"])))
        self.assertGreaterEqual(cleanup["observations"][-1]["at"], window - 0.5 + settle)
        self.assertLessEqual(cleanup["observations"][-1]["at"], window + 3 * settle)
        self.assertEqual({}, self.host.docker_cli.containers)

        # A name that keeps reappearing never verifies: bounded, retained as
        # unverified, and still stop work for the next attempt.
        churn = self.launch(kind="decompose", task_id="NSC-1011", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        churn_name = churn["provider_container"]["name"]
        for offset in range(1, 40, 2):
            self.host.docker_cli.create(churn_name, "nosafecircle", at=self.clock() + offset)
        cleanup = self._cancel(churn)["provider_container_cleanup"]
        self.assertEqual("unverified", cleanup["status"])
        self.assertGreaterEqual(len(cleanup["removed"]), 5)
        self.assertLessEqual(cleanup["watched_seconds"], window + 3 * settle + 1.0)
        self.assertTrue(background_jobs.cleanup_pending(background_jobs.read_index(self.manager, "NSC-1011")))

    def test_docker_unavailable_on_first_stop_is_retried_by_the_repeated_stop(self):
        from Pipeline.AssistantControl import __main__ as assistant_cli
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.available = False

        first = self._cancel(index, reason="first")
        cleanup = first["provider_container_cleanup"]
        self.assertEqual(("cancelled", "refused", 1, 1),
                         (first["status"], cleanup["status"], cleanup["generation"], cleanup["attempt"]))
        self.assertIn("Docker Desktop is not running", cleanup["error"])
        self.assertTrue(background_jobs.cleanup_pending(first))
        self.assertFalse(background_jobs.stop_complete([background_jobs._stop_result(first)]))
        self.assertEqual({name}, set(self.host.docker_cli.containers))

        # The CLI reports the incomplete stop, exit 1, while Docker is still down.
        arguments = ["--source", str(self.source), "--checkout-root", str(self.manager.root),
                     "stop-background-jobs", "--grace-seconds", "0"]

        def run_cli() -> tuple[int, dict]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), \
                    patch.object(background_jobs, "DetachedHost", lambda: self.host), \
                    patch.object(background_jobs, "CONTAINER_WINDOW_SECONDS", 0.0), \
                    patch.object(background_jobs, "CONTAINER_SETTLE_SECONDS", 0.0):
                code = assistant_cli.main(arguments)
            return code, json.loads(output.getvalue())

        code, payload = run_cli()
        self.assertEqual((1, "cleanup_pending", ["NSC-898"]), (code, payload["status"], payload["cleanup_pending"]))
        self.assertEqual(("cancelled", "refused", 2), (payload["jobs"][0]["status"],
                                                       payload["jobs"][0]["provider_container_cleanup"]["status"],
                                                       payload["jobs"][0]["provider_container_cleanup"]["generation"]))

        # Docker is back: the repeated stop performs the exact cleanup itself.
        self.host.docker_cli.available = True
        second = self._cancel(index, reason="second")
        cleanup = second["provider_container_cleanup"]
        self.assertEqual(("cancelled", "verified_absent", 3, 3, "refused"),
                         (second["status"], cleanup["status"], cleanup["generation"], cleanup["attempt"],
                          cleanup["previous_status"]))
        self.assertEqual((1, self.host.docker_cli.removed), (len(cleanup["removed"]), cleanup["removed"]))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.assertEqual("first", second["stop"]["reason"])  # the bound request is not rewritten
        self.assertTrue(background_jobs.cleanup_pending(second))  # verified, tombstone unfinished
        result = background_jobs._stop_result(second)
        self.assertEqual(cleanup["tombstone_until_utc"], result["retry_after_utc"])
        self.assertFalse(background_jobs.stop_complete([result]))

        # Repeating while the tombstone is active takes exactly one more look.
        calls = len(self.host.docker_cli.calls)
        third = self._cancel(index, reason="third")
        self.assertEqual(calls + 1, len(self.host.docker_cli.calls))
        self.assertEqual(("verified_absent", 1, True),
                         (third["provider_container_cleanup"]["status"],
                          len(third["provider_container_cleanup"]["removed"]),
                          background_jobs.cleanup_pending(third)))
        # After the bound the repeated stop records the final recheck; then it is idempotent.
        self.pass_tombstone()
        fourth = self._cancel(index, reason="fourth")
        self.assertTrue(background_jobs.cleanup_final(fourth))
        self.assertFalse(background_jobs.cleanup_pending(fourth))
        calls = len(self.host.docker_cli.calls)
        self.assertEqual(fourth, self._cancel(index, reason="fifth"))
        self.assertEqual([], background_jobs.cancel_all(
            self.manager, host=self.host, reason="again", grace_seconds=0,
            clock=self.clock, sleep=self.clock.sleep, finalize=True))
        code, payload = run_cli()
        self.assertEqual((0, "stopped", [], []), (code, payload["status"], payload["jobs"], payload["cleanup_pending"]))
        self.assertEqual(calls, len(self.host.docker_cli.calls))

        # cancel_all also retries a terminal ticket left pending by a refused cleanup.
        other = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        self.host.docker_cli.create(other["provider_container"]["name"], "nosafecircle")
        self.host.docker_cli.available = False
        self.assertTrue(background_jobs.cleanup_pending(self._cancel(other)))
        self.host.docker_cli.available = True
        results = background_jobs.cancel_all(self.manager, host=self.host, reason="retry", grace_seconds=0,
                                             clock=self.clock, sleep=self.clock.sleep, finalize=True)
        self.assertEqual([("NSC-1010", "cancelled", False)],
                         [(item["task_id"], item["status"], item["cleanup_pending"]) for item in results])
        self.assertTrue(background_jobs.stop_complete(results))
        self.assertEqual({}, self.host.docker_cli.containers)

    def test_slow_docker_reconciliation_does_not_hold_the_checkouts_lock(self):
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        lock_path = self.manager.records / "checkouts.lock"
        unrelated = self.manager.records / "NSC-1010.json"
        seen: list[tuple] = []

        def unrelated_checkout_work(arguments):
            # Another checkout transaction (admission, settlement, a post-crew
            # child persisting its validation) runs while Docker is slow.
            with _exclusive_file_lock(lock_path, timeout_seconds=0.5):
                write_record(unrelated, {"fixture": "unrelated", "during": arguments[:2]})
            on_disk = background_jobs.read_index(self.manager, "NSC-898")
            cleanup = on_disk.get("provider_container_cleanup") or {}
            seen.append((arguments[:2], on_disk["status"], cleanup.get("status"), cleanup.get("generation")))

        self.host.docker_cli.on_call = unrelated_checkout_work
        stopped = self._cancel(index)
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 1, 1), (cleanup["status"], len(cleanup["removed"]), cleanup["generation"]))
        self.assertGreaterEqual(len(seen), 3)
        self.assertEqual({("cancelled", "in_progress", 1)}, {(item[1], item[2], item[3]) for item in seen})
        self.assertEqual("unrelated", _read(unrelated)["fixture"])
        self.assertIsNotNone(cleanup["finished_at_utc"])

        # A stale writer cannot record over a newer generation: the result is discarded.
        stale = {**stopped, "provider_container_cleanup": {**cleanup, "generation": cleanup["generation"] - 1,
                                                          "status": "in_progress"}}
        durable = background_jobs._finish_cleanup(self.manager, stale, {"status": "verified_absent", "removed": []})
        self.assertEqual(cleanup, durable["provider_container_cleanup"])
        self.assertEqual(cleanup, background_jobs.read_index(self.manager, "NSC-898")["provider_container_cleanup"])

    def test_clear_and_relaunch_wait_for_the_tombstone_then_recheck_once(self):
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        stopped = self._cancel(index)
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual("verified_absent", cleanup["status"])
        self.assertTrue(background_jobs.tombstone_active(stopped))
        self.assertFalse(background_jobs.cleanup_final(stopped))
        until = background_jobs._parse_utc(cleanup["tombstone_until_utc"])
        self.assertGreater(until, background_jobs._parse_utc(cleanup["started_at_utc"]))

        # Until the Docker operation bound has passed, neither clear nor a retry may run.
        with self.assertRaisesRegex(BackgroundJobError, "late create could still land until"):
            background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                  clock=self.clock, sleep=self.clock.sleep)
        with self.assertRaisesRegex(BackgroundJobError, "not finally verified absent; clear it first"):
            self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                        identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        self.assertEqual(1, len(self.host.launches))
        self.assertIsNotNone(background_jobs.read_index(self.manager, "NSC-898"))

        # After the tombstone a create had landed: the next look removes it,
        # watches the full window again and starts a fresh bound; only after
        # that bound and one more clean look does the index clear.
        self.pass_tombstone()
        self.host.docker_cli.create(name, "nosafecircle")
        with self.assertRaisesRegex(BackgroundJobError, "late create could still land until"):
            background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                  clock=self.clock, sleep=self.clock.sleep)
        current = background_jobs.read_index(self.manager, "NSC-898")
        cleanup = current["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 2), (cleanup["status"], len(cleanup["removed"])))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.assertTrue(background_jobs.tombstone_active(current))
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.pass_tombstone()
        cleared = background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                        clock=self.clock, sleep=self.clock.sleep)
        self.assertTrue(cleared["cleared"])
        archived = _read(Path(cleared["archived"]))["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 2), (archived["status"], len(archived["removed"])))
        self.assertEqual(self.host.docker_cli.removed, archived["removed"])
        self.assertIsNotNone(archived["final_recheck_at_utc"])
        self.assertEqual({}, self.host.docker_cli.containers)
        relaunched = self.launch(kind="decompose", task_id="NSC-898", duration=1.0,
                                 identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        self.assertEqual((2, "running"), (relaunched["attempt"], relaunched["status"]))
        self.assertNotEqual(name, relaunched["provider_container"]["name"])

    def test_unfinished_tombstone_keeps_cleanup_pending_until_the_final_recheck(self):
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        stopped = self._cancel(index)  # nothing there during the window
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual(("verified_absent", []), (cleanup["status"], cleanup["removed"]))
        self.assertTrue(background_jobs.tombstone_active(stopped))
        self.assertTrue(background_jobs.cleanup_pending(stopped))
        self.assertFalse(background_jobs.cleanup_final(stopped))
        result = background_jobs._stop_result(stopped)
        self.assertEqual((True, cleanup["tombstone_until_utc"]), (result["cleanup_pending"], result["retry_after_utc"]))
        self.assertFalse(background_jobs.stop_complete([result]))

        # A create that lands after the window but inside the Docker operation
        # bound is caught by the repeated stop's exact look, which starts a
        # fresh bound from the removal.
        self.clock.sleep(5.0)
        self.host.docker_cli.create(name, "nosafecircle")
        again = self._cancel(index)
        cleanup = again["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 1), (cleanup["status"], len(cleanup["removed"])))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.assertTrue(background_jobs.cleanup_pending(again))
        self.assertGreater(background_jobs._parse_utc(cleanup["tombstone_until_utc"]),
                           background_jobs._parse_utc(stopped["provider_container_cleanup"]["tombstone_until_utc"]))

        # Startup owes the same: it retries the exact look, waits the bound out
        # and records the final recheck before it would plan.
        before = self.clock()
        outcomes = background_jobs.reconcile_startup(self.manager, self.host, invocation_id="restart",
                                                     clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(["container_verified"], [item["outcome"] for item in outcomes])
        current = background_jobs.read_index(self.manager, "NSC-898")
        self.assertTrue(background_jobs.cleanup_final(current))
        self.assertIsNotNone(current["provider_container_cleanup"]["final_recheck_at_utc"])
        self.assertGreaterEqual(self.clock.utc(), background_jobs._parse_utc(cleanup["tombstone_until_utc"]))
        self.assertGreater(self.clock(), before)
        self.assertTrue(background_jobs.stop_complete([background_jobs._stop_result(current)]))
        calls = len(self.host.docker_cli.calls)
        self.assertEqual(current, self._cancel(index))
        self.assertEqual(calls, len(self.host.docker_cli.calls))

    def test_cleanup_retry_reauthenticates_the_immutable_ticket_before_removing_anything(self):
        self.prepare()
        victim = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                             identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        attacker = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                               identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        victim_name = victim["provider_container"]["name"]
        attacker_name = attacker["provider_container"]["name"]
        victim_id = self.host.docker_cli.create(victim_name, "nosafecircle")
        self.host.docker_cli.create(attacker_name, "nosafecircle")
        self.host.docker_cli.available = False
        for index in (victim, attacker):
            self.assertTrue(background_jobs.cleanup_pending(self._cancel(index)))
        self.host.docker_cli.available = True
        genuine = background_jobs.read_index(self.manager, "NSC-898")

        def removals() -> list[list[str]]:
            return [call for call in self.host.docker_cli.calls if call[:2] == ["rm", "-f"]]

        # 1. An index rewritten to carry the other job's ticket and container
        #    removes nothing: the run root, request bytes and container identity
        #    are reauthenticated before Docker is asked.
        tampered = {**genuine, "job_id": victim["job_id"], "run_root": victim["run_root"],
                    "request": victim["request"], "request_sha256": victim["request_sha256"],
                    "job_name": victim["job_name"], "stop_request": victim["stop_request"],
                    "provider_container": dict(victim["provider_container"])}
        write_record(background_jobs.index_path(self.manager, "NSC-898"), tampered)
        result = self._cancel(tampered)
        cleanup = result["provider_container_cleanup"]
        self.assertEqual(("refused", True), (cleanup["status"], cleanup["authentication_failed"]))
        self.assertIn("run root differs from the owned job path", cleanup["error"])
        self.assertEqual({victim_name, attacker_name}, set(self.host.docker_cli.containers))
        self.assertEqual([], removals())
        self.assertTrue(background_jobs.cleanup_pending(self._cancel(tampered)))
        # cancel_all retries both: the genuine victim ticket removes its own
        # container (the only removal), the tampered one is refused again.
        results = background_jobs.cancel_all(self.manager, host=self.host, reason="all", grace_seconds=0,
                                             clock=self.clock, sleep=self.clock.sleep, finalize=True)
        self.assertEqual([("NSC-898", True), ("NSC-1010", False)],
                         [(item["task_id"], item["cleanup_pending"]) for item in results])
        self.assertEqual([["rm", "-f", victim_id]], removals())
        self.assertEqual({attacker_name}, set(self.host.docker_cli.containers))
        with self.assertRaisesRegex(background_jobs.StartupRefused, "does not authenticate"):
            background_jobs.reconcile_startup(self.manager, self.host, invocation_id="restart",
                                              clock=self.clock, sleep=self.clock.sleep)
        with self.assertRaisesRegex(BackgroundJobError, "does not authenticate"):
            background_jobs.clear(self.manager, "NSC-898", job_id=victim["job_id"], host=self.host,
                                  clock=self.clock, sleep=self.clock.sleep)
        self.assertFalse(background_jobs.cleanup_retry_due(background_jobs.read_index(self.manager, "NSC-898")))
        self.assertEqual([["rm", "-f", victim_id]], removals())
        self.assertEqual({attacker_name}, set(self.host.docker_cli.containers))

        # 2. A container name that is not derived from the job id is refused the same way.
        write_record(background_jobs.index_path(self.manager, "NSC-898"),
                     {**genuine, "provider_container": {"name": victim_name, "compose_project": "nosafecircle"}})
        result = self._cancel(background_jobs.read_index(self.manager, "NSC-898"))
        self.assertEqual("refused", result["provider_container_cleanup"]["status"])
        self.assertIn("provider container identity is not derived from the ticket",
                      result["provider_container_cleanup"]["error"])
        self.assertEqual([["rm", "-f", victim_id]], removals())

        # 3. Altered ticket bytes are refused before Docker is asked at all.
        write_record(background_jobs.index_path(self.manager, "NSC-898"), genuine)
        request_path = Path(genuine["request"])
        request_path.write_bytes(request_path.read_bytes() + b"\n")
        calls = len(self.host.docker_cli.calls)
        result = self._cancel(genuine)
        self.assertIn("launch request bytes differ from the recorded ticket hash",
                      result["provider_container_cleanup"]["error"])
        self.assertEqual(calls, len(self.host.docker_cli.calls))
        self.assertEqual({attacker_name}, set(self.host.docker_cli.containers))
        self.assertEqual([["rm", "-f", victim_id]], removals())

    def test_cleanup_in_progress_under_a_live_owner_is_awaited_not_superseded(self):
        from Pipeline.AssistantControl.process_identity import identify
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.available = False
        self.assertTrue(background_jobs.cleanup_pending(self._cancel(index)))
        self.host.docker_cli.available = True

        # Another live process owns the cleanup: this one waits (bounded) and
        # rereads the durable record instead of starting a competing generation.
        parent = identify(os.getppid()) if os.name == "nt" else None
        if parent is not None:
            current = background_jobs.read_index(self.manager, "NSC-898")
            current["provider_container_cleanup"] = {
                **current["provider_container_cleanup"], "status": "in_progress", "generation": 7,
                "owner": {"pid": os.getppid(), "process_identity": parent},
            }
            write_record(background_jobs.index_path(self.manager, "NSC-898"), current)
            self.assertTrue(background_jobs.cleanup_owner_alive(current))
            self.assertFalse(background_jobs.cleanup_retry_due(current))
            calls = len(self.host.docker_cli.calls)
            before = self.clock()
            waited = self._cancel(index)
            self.assertEqual(("in_progress", 7), (waited["provider_container_cleanup"]["status"],
                                                  waited["provider_container_cleanup"]["generation"]))
            self.assertEqual(calls, len(self.host.docker_cli.calls))
            self.assertGreaterEqual(self.clock() - before, background_jobs._coalesce_wait_seconds() - 1.0)
            self.assertEqual({name}, set(self.host.docker_cli.containers))

        # A generation whose owner is gone is taken over, not waited for.
        current = background_jobs.read_index(self.manager, "NSC-898")
        current["provider_container_cleanup"] = {
            **current["provider_container_cleanup"], "status": "in_progress", "generation": 8,
            "owner": {"pid": 4000000000,
                      "process_identity": {"pid": 4000000000, "created_ticks": 1, "image": "gone"}},
        }
        write_record(background_jobs.index_path(self.manager, "NSC-898"), current)
        self.assertFalse(background_jobs.cleanup_owner_alive(current))
        self.assertTrue(background_jobs.cleanup_retry_due(current))
        taken = self._cancel(index)
        cleanup = taken["provider_container_cleanup"]
        self.assertEqual(("verified_absent", 9, 8, 1), (cleanup["status"], cleanup["generation"],
                                                        cleanup["took_over_from"]["generation"],
                                                        len(cleanup["removed"])))
        self.assertEqual({}, self.host.docker_cli.containers)
        # An in-progress record left by this very process after a crash reads as abandoned too.
        current = background_jobs.read_index(self.manager, "NSC-898")
        current["provider_container_cleanup"] = {
            **current["provider_container_cleanup"], "status": "in_progress", "generation": 10,
            "owner": {"pid": os.getpid(), "process_identity": identify(os.getpid()) if os.name == "nt" else None},
        }
        write_record(background_jobs.index_path(self.manager, "NSC-898"), current)
        self.assertFalse(background_jobs.cleanup_owner_alive(current))

    def test_docker_failure_after_a_late_sighting_keeps_the_removal_and_the_renewed_bound(self):
        """Finding 1: a Docker failure after the exact container was seen and removed
        must keep the removal durable, restart the operation bound from it, owe the
        final recheck again and stay pending. It must never restore an older
        deadline or read as complete."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        unrelated = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                                identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        other_name = unrelated["provider_container"]["name"]
        self.host.docker_cli.create(other_name, "nosafecircle")

        stopped = self._cancel(index)  # nothing there during the window
        cleanup = stopped["provider_container_cleanup"]
        self.assertEqual(("verified_absent", []), (cleanup["status"], cleanup["removed"]))
        first_bound = cleanup["tombstone_until_utc"]
        self.assertTrue(background_jobs.tombstone_active(stopped))

        # A create lands after the window but inside the bound; the repeated stop
        # removes it and Docker then fails on the very next call.
        self.clock.sleep(5.0)
        container_id = self.host.docker_cli.create(name, "nosafecircle")
        seen = {"removed": False}

        def docker_fails_right_after_the_removal(arguments):
            if seen["removed"]:
                self.host.docker_cli.available = False
            elif arguments[:2] == ["rm", "-f"]:
                seen["removed"] = True

        self.host.docker_cli.on_call = docker_fails_right_after_the_removal
        failed = self._cancel(index)
        cleanup = failed["provider_container_cleanup"]
        self.assertEqual(("refused", [container_id]), (cleanup["status"], cleanup["removed"]))
        self.assertTrue(cleanup["container_sighted"])
        self.assertIn("Docker Desktop is not running", cleanup["error"])
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        renewed = cleanup["tombstone_until_utc"]
        self.assertGreater(background_jobs._parse_utc(renewed),
                           background_jobs._parse_utc(first_bound))
        self.assertTrue(background_jobs.cleanup_pending(failed))
        self.assertFalse(background_jobs.cleanup_final(failed))
        result = background_jobs._stop_result(failed)
        self.assertEqual((True, renewed), (result["cleanup_pending"], result["retry_after_utc"]))
        self.assertFalse(background_jobs.stop_complete([result]))
        self.assertEqual([container_id], self.host.docker_cli.removed)
        self.assertEqual({other_name}, set(self.host.docker_cli.containers))

        # A further failure never restores the older deadline nor completes it.
        self.host.docker_cli.on_call = None
        self.clock.sleep(1.0)
        again = self._cancel(index)
        cleanup = again["provider_container_cleanup"]
        self.assertEqual(("refused", [container_id], renewed),
                         (cleanup["status"], cleanup["removed"], cleanup["tombstone_until_utc"]))
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.assertTrue(background_jobs.cleanup_pending(again))

        # Docker back: the exact window ends absent, the renewed bound still stands,
        # and only after it does the final recheck make the cleanup complete.
        self.host.docker_cli.available = True
        recovered = self._cancel(index)
        cleanup = recovered["provider_container_cleanup"]
        self.assertEqual(("verified_absent", [container_id], renewed),
                         (cleanup["status"], cleanup["removed"], cleanup["tombstone_until_utc"]))
        self.assertTrue(background_jobs.cleanup_pending(recovered))
        self.pass_tombstone()
        final = self._cancel(index)
        self.assertTrue(background_jobs.cleanup_final(final))
        self.assertIsNotNone(final["provider_container_cleanup"]["final_recheck_at_utc"])
        self.assertTrue(background_jobs.stop_complete([background_jobs._stop_result(final)]))

        # Nothing unrelated was ever inspected or removed, and repeating is a no-op.
        self.assertEqual([container_id], self.host.docker_cli.removed)
        self.assertEqual({other_name}, set(self.host.docker_cli.containers))
        for call in self.host.docker_cli.calls:
            self.assertIn(call[:2], (["container", "inspect"], ["rm", "-f"]))
            self.assertIn(call[-1], {name, container_id})
        calls = len(self.host.docker_cli.calls)
        self.assertEqual(final, self._cancel(index))
        self.assertEqual(calls, len(self.host.docker_cli.calls))

    def test_interrupted_cleanup_keeps_its_removal_durable_and_never_completes(self):
        """Finding 1: an exception between beginning and finishing a cleanup
        generation must leave the removal, the renewed bound and the pending
        state durable, and must leave the generation retryable."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        container_id = self.host.docker_cli.create(name, "nosafecircle")
        seen = {"removed": False}

        def interrupt_right_after_the_removal(arguments):
            if seen["removed"]:
                raise KeyboardInterrupt("operator interrupted the stop")
            if arguments[:2] == ["rm", "-f"]:
                seen["removed"] = True

        self.host.docker_cli.on_call = interrupt_right_after_the_removal
        with self.assertRaises(KeyboardInterrupt):
            self._cancel(index)
        self.host.docker_cli.on_call = None

        current = background_jobs.read_index(self.manager, "NSC-898")
        cleanup = current["provider_container_cleanup"]
        self.assertEqual(("cancelled", "refused", [container_id]),
                         (current["status"], cleanup["status"], cleanup["removed"]))
        self.assertTrue(cleanup["container_sighted"])
        self.assertIn("interrupted", cleanup["error"])
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.assertTrue(background_jobs.tombstone_active(current))
        self.assertTrue(background_jobs.cleanup_pending(current))
        self.assertFalse(background_jobs.cleanup_owner_alive(current))  # retryable, not wedged
        self.assertEqual(([container_id], {}),
                         (self.host.docker_cli.removed, self.host.docker_cli.containers))

        retried = self._cancel(index)
        cleanup = retried["provider_container_cleanup"]
        self.assertEqual(("verified_absent", [container_id]), (cleanup["status"], cleanup["removed"]))
        self.assertTrue(background_jobs.cleanup_pending(retried))
        self.pass_tombstone()
        self.assertTrue(background_jobs.cleanup_final(self._cancel(index)))

    def test_empty_or_malformed_launch_request_never_authenticates_a_cleanup(self):
        """Finding 2: a missing, empty, truncated or malformed request file must fail
        closed on the recorded hash, record authentication_failed, and inspect,
        remove, retry and clear nothing."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        victim = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                             identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        victim_name = victim["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.create(victim_name, "nosafecircle")
        self.host.docker_cli.available = False
        self.assertTrue(background_jobs.cleanup_pending(self._cancel(index)))
        self.host.docker_cli.available = True
        request_path = Path(index["request"])
        genuine = request_path.read_bytes()

        for label, payload, expected in (
                ("missing", None, "launch request is missing"),
                ("empty", b"", "launch request is empty"),
                ("truncated", genuine[: len(genuine) // 2], "launch request is unreadable"),
                ("malformed", b"[]", "launch request is not an object"),
        ):
            with self.subTest(request=label):
                if payload is None:
                    request_path.unlink()
                else:
                    request_path.write_bytes(payload)
                calls = len(self.host.docker_cli.calls)
                refused = self._cancel(index)
                cleanup = refused["provider_container_cleanup"]
                self.assertEqual("refused", cleanup["status"])
                self.assertIn(expected, cleanup["error"])
                self.assertIn("launch request bytes differ from the recorded ticket hash",
                              cleanup["error"])
                self.assertTrue(cleanup["authentication_failed"])
                self.assertEqual("authentication_failed", refused["authentication"]["status"])
                self.assertTrue(background_jobs.cleanup_pending(refused))
                self.assertFalse(background_jobs.cleanup_retry_due(
                    background_jobs.read_index(self.manager, "NSC-898")))
                with self.assertRaisesRegex(background_jobs.StartupRefused, "does not authenticate"):
                    background_jobs.reconcile_startup(self.manager, self.host, invocation_id="restart",
                                                      clock=self.clock, sleep=self.clock.sleep)
                with self.assertRaisesRegex(BackgroundJobError, "does not authenticate"):
                    background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"],
                                          host=self.host, clock=self.clock, sleep=self.clock.sleep)
                # Nothing was inspected, removed or repaired on any of those paths.
                self.assertEqual(calls, len(self.host.docker_cli.calls))
                self.assertEqual([], self.host.docker_cli.removed)
                self.assertEqual({name, victim_name}, set(self.host.docker_cli.containers))
                self.assertEqual("running", background_jobs.observe(victim, self.host)["status"])

        # The exact ticket bytes restored, the same cleanup proceeds again.
        request_path.write_bytes(genuine)
        recovered = self._cancel(index)
        cleanup = recovered["provider_container_cleanup"]
        self.assertEqual("verified_absent", cleanup["status"])
        self.assertEqual(self.host.docker_cli.removed, cleanup["removed"])
        self.assertEqual({victim_name}, set(self.host.docker_cli.containers))

    def test_process_identity_mismatch_refuses_every_destructive_path(self):
        """Finding 2: an index whose recorded PID and complete process identity do not
        match the artifacts its own run wrote must stop, terminate, inspect and remove
        nothing, and must record authentication_failed."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        victim = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                             identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        victim_name = victim["provider_container"]["name"]
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.create(victim_name, "nosafecircle")
        genuine = background_jobs.read_index(self.manager, "NSC-898")

        # Its own ticket, run root, Job Object name and container, but the other
        # job's live child as its process identity.
        forged = {**genuine, "pid": victim["pid"], "process_identity": victim["process_identity"]}
        write_record(background_jobs.index_path(self.manager, "NSC-898"), forged)
        auth = background_jobs.authenticate_index(self.manager, forged)
        self.assertEqual((False, False), (auth["authenticated"], auth["identity_bound"]))
        self.assertEqual(["launcher identity differs from the index",
                          "child identity handshake differs from the index",
                          "Job Object acknowledgement differs from the index"], auth["problems"])

        calls = len(self.host.docker_cli.calls)
        with self.assertRaisesRegex(BackgroundJobError, "does not authenticate"):
            self._cancel(forged)
        with self.assertRaisesRegex(BackgroundJobError, "nothing was terminated"):
            background_jobs._enforce_stop(self.manager, forged, host=self.host, reason="forged",
                                          invocation_id="forged", clock=self.clock,
                                          sleep=self.clock.sleep)
        # No unrelated process was signalled or terminated and no container touched.
        self.assertEqual("running", background_jobs.observe(victim, self.host)["status"])
        self.assertIsNone(self.host.children[victim["pid"]]["stopped"])
        self.assertIsNone(self.host.children[index["pid"]]["stopped"])
        self.assertFalse(Path(genuine["stop_request"]).exists())
        self.assertFalse(Path(victim["stop_request"]).exists())
        self.assertEqual(calls, len(self.host.docker_cli.calls))
        self.assertEqual([], self.host.docker_cli.removed)
        self.assertEqual({name, victim_name}, set(self.host.docker_cli.containers))
        refused = background_jobs.read_index(self.manager, "NSC-898")
        self.assertEqual(("authentication_failed", auth["problems"]),
                         (refused["authentication"]["status"], refused["authentication"]["problems"]))
        self.assertEqual(("refused", True),
                         (refused["provider_container_cleanup"]["status"],
                          refused["provider_container_cleanup"]["authentication_failed"]))

        # The same mismatch on a terminal ticket refuses its cleanup and retries
        # nothing automatically, instead of removing a container in its name.
        write_record(background_jobs.index_path(self.manager, "NSC-898"), genuine)
        self.host.docker_cli.available = False
        self.assertTrue(background_jobs.cleanup_pending(self._cancel(genuine)))
        self.host.docker_cli.available = True
        terminal = background_jobs.read_index(self.manager, "NSC-898")
        write_record(background_jobs.index_path(self.manager, "NSC-898"),
                     {**terminal, "pid": victim["pid"],
                      "process_identity": victim["process_identity"]})
        calls = len(self.host.docker_cli.calls)
        result = self._cancel(background_jobs.read_index(self.manager, "NSC-898"))
        cleanup = result["provider_container_cleanup"]
        self.assertEqual(("refused", True), (cleanup["status"], cleanup["authentication_failed"]))
        self.assertIn("launcher identity differs from the index", cleanup["error"])
        self.assertEqual(calls, len(self.host.docker_cli.calls))
        self.assertEqual([], self.host.docker_cli.removed)
        self.assertEqual({name, victim_name}, set(self.host.docker_cli.containers))
        self.assertFalse(background_jobs.cleanup_retry_due(
            background_jobs.read_index(self.manager, "NSC-898")))
        self.assertEqual("running", background_jobs.observe(victim, self.host)["status"])

    def test_a_concurrent_clear_is_a_cleanup_outcome_not_a_failure(self):
        """Finding 3: an index cleared or superseded while the unlocked Docker work
        runs is an expected concurrency outcome, never an exception."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        stopped = self._cancel(index)
        self.assertTrue(background_jobs.cleanup_pending(stopped))
        index_file = background_jobs.index_path(self.manager, "NSC-898")
        archived = index_file.read_bytes()

        # 1. Cleared by another owner during the unlocked exact look.
        def clear_during_the_unlocked_look(arguments):
            self.host.docker_cli.on_call = None
            index_file.unlink()

        self.host.docker_cli.on_call = clear_during_the_unlocked_look
        outcome = background_jobs.settle_cleanup(self.manager, stopped, self.host,
                                                 clock=self.clock, sleep=self.clock.sleep)
        self.assertFalse(background_jobs.cleanup_pending(outcome))
        self.assertEqual(("cleared", None), (outcome["cleanup_concurrency"],
                                             outcome["provider_container"]))
        self.assertTrue(background_jobs.stop_complete([background_jobs._stop_result(outcome)]))
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-898"))

        # 2. Superseded by a newer ticket: reported, and nothing is inspected.
        index_file.write_bytes(archived)
        stale = {**background_jobs.read_index(self.manager, "NSC-898"), "job_id": "0" * 64}
        calls = len(self.host.docker_cli.calls)
        superseded = background_jobs._run_cleanup(self.manager, stale, self.host,
                                                  clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual("superseded", superseded["cleanup_concurrency"])
        self.assertFalse(background_jobs.cleanup_pending(superseded))
        self.assertEqual("superseded",
                         background_jobs._record_final_recheck(self.manager, stale)["cleanup_concurrency"])
        index_file.unlink()
        self.assertEqual("cleared",
                         background_jobs._record_final_recheck(self.manager, stale)["cleanup_concurrency"])
        self.assertEqual(calls, len(self.host.docker_cli.calls))

    def _other_checkout(self, name: str, *, source: Path | None = None):
        """A second checkout root (optionally of a second clone of Source)."""
        from Pipeline.AssistantControl.checkouts import Checkouts
        root = Path(str(self.manager.root)).parent
        if source is None:
            source = self.source
        other = Checkouts(source, root / name)
        other.records.mkdir(parents=True, exist_ok=True)
        host = FixtureHost(self.clock)
        host.docker_cli = self.host.docker_cli  # one Docker daemon, two checkouts
        return other, host

    def test_a_decompose_ticket_asking_for_an_author_checklist_is_refused(self):
        self.prepare()
        identity = dict(self.DECOMPOSE_IDENTITY, author_checklist="parent-contract-v1")
        with self.assertRaisesRegex(background_jobs.BackgroundJobError, "does not support author_checklist"):
            background_jobs.launch(
                self.manager, kind="decompose", task_id="NSC-898", identity=identity,
                config=None, invocation_id="inv-checklist", provider_spend_authorized=True,
                host=self.host,
            )

    def test_two_checkouts_of_the_same_task_never_share_a_container_identity(self):
        """Finding 1: two checkouts (or two clones) running the same task with the
        same identity must derive different job ids and container names, and a stop
        in one must never reach the other's container or child."""
        self.prepare()
        identity = dict(self.DECOMPOSE_IDENTITY)
        mine = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                           identity=dict(identity), config=None)

        clone = Path(str(self.manager.root)).parent / "source-b"
        self.git("clone", "--quiet", str(self.source), str(clone))
        for label, (manager, host) in (
                ("other checkout root", self._other_checkout("checkouts-b")),
                ("other Source clone", self._other_checkout("checkouts-c", source=clone)),
        ):
            with self.subTest(checkout=label):
                host.schedule("decompose", "NSC-898", 100.0, lambda *_: None)
                theirs = background_jobs.launch(
                    manager, kind="decompose", task_id="NSC-898", identity=dict(identity),
                    config=None, invocation_id="inv-other", provider_spend_authorized=True,
                    host=host,
                )
                # The identities are checkout-exact: nothing derived is shared.
                self.assertNotEqual(mine["job_id"], theirs["job_id"])
                self.assertNotEqual(mine["provider_container"]["name"],
                                    theirs["provider_container"]["name"])
                self.assertNotEqual(mine["provider_container"]["labels"],
                                    theirs["provider_container"]["labels"])
                self.assertNotEqual(mine["job_name"], theirs["job_name"])

                my_name = mine["provider_container"]["name"]
                their_name = theirs["provider_container"]["name"]
                my_id = self.host.docker_cli.create(my_name, "nosafecircle")
                self.host.docker_cli.create(their_name, "nosafecircle")
                self.host.docker_cli.removed.clear()
                inspected = len(self.host.docker_cli.calls)
                before = list((background_jobs.read_index(self.manager, "NSC-898").get(
                    "provider_container_cleanup") or {}).get("removed") or [])

                # A stop in this checkout removes only its own container and
                # never touches the other checkout's container or child.
                stopped = self._cancel(mine)
                self.assertEqual(before + [my_id], stopped["provider_container_cleanup"]["removed"])
                self.assertEqual({their_name}, set(self.host.docker_cli.containers))
                self.assertEqual([my_id], self.host.docker_cli.removed)
                names = {call[-1] for call in self.host.docker_cli.calls[inspected:]}
                self.assertEqual({my_name, my_id}, names)
                self.assertEqual("running", background_jobs.observe(theirs, host)["status"])
                self.assertIsNone(host.children[theirs["pid"]]["stopped"])
                self.assertFalse(Path(theirs["stop_request"]).exists())

                # And the other checkout can still finish its own cleanup.
                self.host.docker_cli.removed.clear()
                theirs_stopped = background_jobs.cancel(
                    manager, theirs, host=host, reason="stop", grace_seconds=0,
                    invocation_id="stop", clock=self.clock, sleep=self.clock.sleep)
                self.assertEqual("verified_absent",
                                 theirs_stopped["provider_container_cleanup"]["status"])
                self.assertEqual({}, self.host.docker_cli.containers)

        # The derivation itself: the checkout is part of the ticket id, the
        # container name and the labels.
        variants = {
            "this checkout": (self.manager.source, self.manager.root),
            "other checkout root": (self.manager.source, Path(str(self.manager.root) + "-b")),
            "other Source": (clone, self.manager.root),
        }
        ids = {label: background_jobs.job_id_for("decompose", "NSC-898", identity, 1,
                                                 source=source, checkout_root=root)
               for label, (source, root) in variants.items()}
        self.assertEqual(3, len(set(ids.values())))
        self.assertEqual(3, len({background_jobs.container_name_for(item) for item in ids.values()}))
        self.assertEqual(3, len({background_jobs.checkout_digest_for(source, root)
                                 for source, root in variants.values()}))
        self.assertEqual(ids["this checkout"], mine["job_id"])

    def test_a_container_without_this_tickets_labels_is_never_removed(self):
        """Finding 1: the ticket's name alone proves nothing. A container under it
        that does not carry this ticket's job and checkout labels belongs to another
        run and is refused exactly like a compose-project mismatch."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        labels = dict(index["provider_container"]["labels"])
        stopped = self._cancel(index)  # nothing there yet
        self.assertEqual("verified_absent", stopped["provider_container_cleanup"]["status"])

        for label, wrong in (
                ("unlabelled", {}),
                ("another checkout", {**labels, background_jobs.CONTAINER_CHECKOUT_LABEL: "0" * 64}),
                ("another job", {**labels, background_jobs.CONTAINER_JOB_LABEL: "0" * 64}),
        ):
            with self.subTest(container=label):
                self.host.docker_cli.containers.clear()
                self.host.docker_cli.create(name, "nosafecircle", labels=wrong)
                refused = self._cancel(index)
                cleanup = refused["provider_container_cleanup"]
                self.assertEqual("refused", cleanup["status"])
                self.assertIn("carries other identity", cleanup["error"])
                self.assertIn("job label", cleanup["error"])
                self.assertEqual([], self.host.docker_cli.removed)
                self.assertEqual({name}, set(self.host.docker_cli.containers))
                self.assertTrue(background_jobs.cleanup_pending(refused))
                self.assertFalse(background_jobs.cleanup_final(refused))

        # A ticket whose own recorded labels are not derived from this checkout
        # is refused before Docker is asked at all.
        forged = {**index, "provider_container": {
            **index["provider_container"],
            "labels": {**labels, background_jobs.CONTAINER_CHECKOUT_LABEL: "0" * 64}}}
        calls = len(self.host.docker_cli.calls)
        with self.assertRaisesRegex(BackgroundJobError, "labels differ from its ticket"):
            background_jobs.reconcile_provider_container(
                forged, self.host, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(calls, len(self.host.docker_cli.calls))
        self.assertIn("provider container labels are not derived from this checkout and ticket",
                      background_jobs.authenticate_index(self.manager, forged)["problems"])

        # The ticket's own labelled container is removed normally.
        self.host.docker_cli.containers.clear()
        mine = self.host.docker_cli.create(name, "nosafecircle")
        done = self._cancel(index)
        self.assertEqual([mine], done["provider_container_cleanup"]["removed"])
        self.assertEqual(([mine], {}), (self.host.docker_cli.removed, self.host.docker_cli.containers))

    def test_authentication_refusal_never_erases_cleanup_progress_or_shortens_the_bound(self):
        """Finding 2: a refusal landing while a generation runs unlocked must not
        discard its removal, sighting or renewed deadline, must land the generation
        as refused (never verified), and must never shorten the bound."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        name = index["provider_container"]["name"]
        stopped = self._cancel(index)  # nothing there; verified with a bound
        first_bound = stopped["provider_container_cleanup"]["tombstone_until_utc"]
        self.assertTrue(background_jobs.tombstone_active(stopped))

        # A create lands inside the bound. While the exact look runs without the
        # lock, another process records an authentication refusal on the ticket.
        self.clock.sleep(5.0)
        container_id = self.host.docker_cli.create(name, "nosafecircle")
        observed: list[dict] = []

        def refuse_while_the_generation_runs(arguments):
            if observed:
                return
            self.host.docker_cli.on_call = None
            with _exclusive_file_lock(self.manager.records / "checkouts.lock", timeout_seconds=10):
                current = background_jobs.read_index(self.manager, "NSC-898")
                observed.append(dict(current["provider_container_cleanup"]))
                background_jobs._refuse_authentication(
                    self.manager, current, ["launch request bytes differ from the recorded ticket hash"])

        self.host.docker_cli.on_call = refuse_while_the_generation_runs
        result = self._cancel(index)
        cleanup = result["provider_container_cleanup"]
        self.assertEqual("in_progress", observed[0]["status"])  # the refusal hit a live generation
        # Its progress is durable and its bound renewed from the removal.
        self.assertEqual([container_id], cleanup["removed"])
        self.assertTrue(cleanup["container_sighted"])
        self.assertEqual(([container_id], {}),
                         (self.host.docker_cli.removed, self.host.docker_cli.containers))
        renewed = cleanup["tombstone_until_utc"]
        self.assertGreater(background_jobs._parse_utc(renewed),
                           background_jobs._parse_utc(first_bound))
        # And it can never read as verified or complete.
        self.assertEqual(("refused", True), (cleanup["status"], cleanup["authentication_failed"]))
        self.assertIsNone(cleanup["verified_at_utc"])
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.assertTrue(background_jobs.cleanup_pending(result))
        self.assertFalse(background_jobs.cleanup_final(result))
        self.assertEqual(renewed, background_jobs._stop_result(result)["retry_after_utc"])
        self.assertFalse(background_jobs.cleanup_retry_due(
            background_jobs.read_index(self.manager, "NSC-898")))

        # The ticket itself still authenticates (the refusal was another
        # process's), so a retry runs a clean generation - but it cannot finish
        # before the renewed bound the refusal could not shorten.
        retried = self._cancel(index)
        cleanup = retried["provider_container_cleanup"]
        self.assertEqual(("verified_absent", [container_id], renewed),
                         (cleanup["status"], cleanup["removed"], cleanup["tombstone_until_utc"]))
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.assertTrue(background_jobs.cleanup_pending(retried))

        # A refusal with no generation in flight preserves every progress field
        # and the recorded deadline.
        before = dict(background_jobs.read_index(
            self.manager, "NSC-898")["provider_container_cleanup"])
        self.assertNotEqual("in_progress", before["status"])
        with _exclusive_file_lock(self.manager.records / "checkouts.lock", timeout_seconds=10):
            current = background_jobs.read_index(self.manager, "NSC-898")
            background_jobs._refuse_authentication(self.manager, current, ["launch request is empty"])
        after = background_jobs.read_index(self.manager, "NSC-898")["provider_container_cleanup"]
        self.assertEqual(("refused", True), (after["status"], after["authentication_failed"]))
        for field in ("generation", "removed", "observations", "container_sighted",
                      "tombstone_until_utc", "final_recheck_at_utc", "tombstone_seconds"):
            self.assertEqual(before[field], after[field], field)

        # A refusing process that cannot see the owner as alive marks the
        # generation refused in flight; that owner's removal and renewed bound
        # are still recorded rather than discarded.
        self.clock.sleep(5.0)
        second_id = self.host.docker_cli.create(name, "nosafecircle")
        marked: list[dict] = []

        def refuse_without_seeing_the_owner(arguments):
            if marked:
                return
            self.host.docker_cli.on_call = None
            active = set(background_jobs._ACTIVE_CLEANUPS)
            background_jobs._ACTIVE_CLEANUPS.clear()  # the owner reads as gone
            try:
                with _exclusive_file_lock(self.manager.records / "checkouts.lock", timeout_seconds=10):
                    background_jobs._refuse_authentication(
                        self.manager, background_jobs.read_index(self.manager, "NSC-898"),
                        ["launch request is empty"])
                marked.append(dict(background_jobs.read_index(
                    self.manager, "NSC-898")["provider_container_cleanup"]))
            finally:
                background_jobs._ACTIVE_CLEANUPS.update(active)

        self.host.docker_cli.on_call = refuse_without_seeing_the_owner
        landed = self._cancel(index)
        cleanup = landed["provider_container_cleanup"]
        self.assertEqual(("refused", None), (marked[0]["status"], marked[0].get("finished_at_utc")))
        self.assertEqual([container_id, second_id], cleanup["removed"])
        self.assertEqual(("refused", True), (cleanup["status"], cleanup["authentication_failed"]))
        self.assertIsNone(cleanup["final_recheck_at_utc"])
        self.assertGreater(background_jobs._parse_utc(cleanup["tombstone_until_utc"]),
                           background_jobs._parse_utc(renewed))
        self.assertEqual({}, self.host.docker_cli.containers)

        # Once the bound has passed the exact final recheck still completes it.
        self.pass_tombstone()
        final = self._cancel(index)
        self.assertTrue(background_jobs.cleanup_final(final))
        self.assertEqual([container_id, second_id], final["provider_container_cleanup"]["removed"])

    def test_cooperative_stop_verifies_ownership_before_stopping_any_container(self):
        """Finding: the child's cooperative stop is destructive, so it must prove the
        container under its ticket's name is its own before stopping it, and must stop
        it by exact id, never by name. Anything else stops nothing, records why, and
        never fails the child."""
        self.prepare()
        index = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        other = self.launch(kind="decompose", task_id="NSC-1010", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        request = _read(Path(index["request"]))
        name = index["provider_container"]["name"]
        labels = dict(index["provider_container"]["labels"])
        record_path = Path(index["run_root"]) / "cooperative-stop.json"
        inspect_call = ["container", "inspect", "--format",
                        background_jobs._CONTAINER_INSPECT_FORMAT, name]
        another_checkout = background_jobs.container_labels_for(
            index["job_id"], self.manager.source, Path(str(self.manager.root) + "-b"))

        # 1. A same-named container that is not this ticket's own is inspected
        #    and never stopped, whatever makes it foreign.
        for label, kwargs in (
                ("no labels", {"labels": {}}),
                ("another checkout", {"labels": another_checkout}),
                ("another job", {"labels": {**labels,
                                            background_jobs.CONTAINER_JOB_LABEL: "0" * 64}}),
                ("another compose project", {"project": "someone-else"}),
                ("another service", {"service": "round-robin-review"}),
        ):
            with self.subTest(container=label):
                self.host.docker_cli.containers.clear()
                project = kwargs.pop("project", "nosafecircle")
                foreign = self.host.docker_cli.create(name, project, **kwargs)
                calls = len(self.host.docker_cli.calls)
                decision = background_jobs.cooperative_stop(request, docker=self.host.docker_cli)
                self.assertEqual(("refused", "other_identity"),
                                 (decision["decision"], decision["reason"]))
                self.assertIn("carries other identity", decision["error"])
                self.assertIn("not stopped", decision["error"])
                self.assertIsNone(decision["stopped_id"])
                # Exactly one call, the inspect by name; nothing was stopped.
                self.assertEqual([inspect_call], self.host.docker_cli.calls[calls:])
                self.assertEqual([], self.host.docker_cli.stopped)
                self.assertTrue(self.host.docker_cli.containers[name]["running"])
                self.assertEqual(foreign, self.host.docker_cli.containers[name]["id"])
                self.assertEqual(decision, _read(record_path))

        # 2. The ticket's own container is stopped by its exact id, never by name.
        self.host.docker_cli.containers.clear()
        mine = self.host.docker_cli.create(name, "nosafecircle")
        calls = len(self.host.docker_cli.calls)
        decision = background_jobs.cooperative_stop(request, docker=self.host.docker_cli)
        self.assertEqual(("stopped", None, mine),
                         (decision["decision"], decision["reason"], decision["stopped_id"]))
        self.assertEqual([inspect_call, ["stop", "--time", "10", mine]],
                         self.host.docker_cli.calls[calls:])
        self.assertEqual([mine], self.host.docker_cli.stopped)
        self.assertFalse(self.host.docker_cli.containers[name]["running"])
        self.assertEqual(labels, decision["expected_labels"])
        self.assertEqual(decision, _read(record_path))

        # 3. An absent container stops nothing.
        self.host.docker_cli.containers.clear()
        calls = len(self.host.docker_cli.calls)
        decision = background_jobs.cooperative_stop(request, docker=self.host.docker_cli)
        self.assertEqual(("absent", "no_such_container", None),
                         (decision["decision"], decision["reason"], decision["stopped_id"]))
        self.assertEqual([inspect_call], self.host.docker_cli.calls[calls:])
        self.assertEqual([mine], self.host.docker_cli.stopped)

        # 3b. A container that goes away between the inspect and the stop
        #     stops nothing and says so.
        vanishing = self.host.docker_cli.create(name, "nosafecircle")

        def remove_it_before_the_stop(arguments):
            if arguments[:1] == ["stop"]:
                self.host.docker_cli.containers.pop(name, None)

        self.host.docker_cli.on_call = remove_it_before_the_stop
        decision = background_jobs.cooperative_stop(request, docker=self.host.docker_cli)
        self.host.docker_cli.on_call = None
        self.assertEqual(("absent", "gone_before_stop", None),
                         (decision["decision"], decision["reason"], decision["stopped_id"]))
        self.assertEqual(vanishing, decision["inspected"]["id"])
        self.assertEqual([mine], self.host.docker_cli.stopped)

        # 4. A Docker failure stops nothing and says why.
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.available = False
        decision = background_jobs.cooperative_stop(request, docker=self.host.docker_cli)
        self.assertEqual(("refused", "docker_cannot_answer"),
                         (decision["decision"], decision["reason"]))
        self.assertIn("Docker Desktop is not running", decision["error"])
        self.assertEqual([mine], self.host.docker_cli.stopped)
        self.host.docker_cli.available = True

        # 5. A ticket whose own labels are not derived from this checkout is
        #    refused before Docker is asked at all.
        forged = {**request, "provider_container": {**request["provider_container"],
                                                    "labels": another_checkout}}
        calls = len(self.host.docker_cli.calls)
        decision = background_jobs.cooperative_stop(forged, docker=self.host.docker_cli)
        self.assertEqual(("refused", "ticket_does_not_authenticate", None),
                         (decision["decision"], decision["reason"], decision["container_name"]))
        self.assertIn("labels are not derived", decision["error"])
        self.assertEqual(calls, len(self.host.docker_cli.calls))
        self.assertEqual([mine], self.host.docker_cli.stopped)

        # 6. The child's wiring routes through exactly this decision and never
        #    raises, so a refused stop cannot turn its stopped receipt into a
        #    failure; the receipt path itself is untouched.
        self.host.docker_cli.containers.clear()
        self.host.docker_cli.create(name, "nosafecircle", labels=another_checkout)
        with patch.object(background_jobs, "_run_docker", self.host.docker_cli):
            interrupt = background_jobs._interrupt_for(request)
            decision = interrupt()  # a refusal is recorded and returned, never raised
        self.assertEqual(("refused", "other_identity"),
                         (decision["decision"], decision["reason"]))
        self.assertEqual(decision, _read(record_path))
        self.assertEqual([mine], self.host.docker_cli.stopped)
        self.assertFalse((Path(index["run_root"]) / "receipt.json").exists())

        # Nothing but this ticket's own name, and ids found under that name,
        # was ever named to Docker.
        named = {call[-1] for call in self.host.docker_cli.calls}
        self.assertNotIn(other["provider_container"]["name"], named)
        self.assertEqual(set(), named - {name, mine, vanishing})

    def test_forged_identity_cannot_reach_an_unrelated_process_or_container(self):
        self.prepare()
        first = self.launch(kind="decompose", task_id="NSC-898", duration=100.0,
                            identity=dict(self.DECOMPOSE_IDENTITY), config=None)
        second = self.launch(task_id="NSC-899", duration=100.0)
        name = first["provider_container"]["name"]

        # 1. A container under the exact name but another compose project is never removed.
        self.host.docker_cli.create(name, "someone-else")
        with self.assertRaisesRegex(BackgroundJobError, "carries other identity"):
            background_jobs.reconcile_provider_container(
                first, self.host, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual([], self.host.docker_cli.removed)
        self.assertEqual([["container", "inspect"]], [call[:2] for call in self.host.docker_cli.calls])

        # 2. A container name that is not derived from the ticket is refused before Docker is asked.
        forged_name = {**first, "provider_container": {
            "name": "nsc-decompose-000000000000000000000000", "compose_project": "nosafecircle"}}
        with self.assertRaisesRegex(BackgroundJobError, "differs from its ticket"):
            background_jobs.reconcile_provider_container(
                forged_name, self.host, clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual(1, len(self.host.docker_cli.calls))

        # 3. An index carrying the other job's process identity and Job Object
        #    name cannot stop that job: the name is not derived from this run.
        forged = {**first, "pid": second["pid"], "process_identity": second["process_identity"],
                  "job_name": second["job_name"]}
        write_record(background_jobs.index_path(self.manager, "NSC-898"), forged)
        auth = background_jobs.authenticate_index(self.manager, forged)
        self.assertFalse(auth["identity_bound"])
        self.assertIn("Job Object name is not derived from the owned run root", auth["problems"])
        with self.assertRaisesRegex(BackgroundJobError, "not derived from its owned run"):
            background_jobs.cancel(self.manager, forged, host=self.host, reason="forged",
                                   grace_seconds=0, clock=self.clock, sleep=self.clock.sleep)
        with self.assertRaisesRegex(background_jobs.StartupRefused, "nothing was stopped"):
            background_jobs.reconcile_startup(self.manager, self.host, invocation_id="restart",
                                              clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual("running", background_jobs.observe(second, self.host)["status"])
        self.assertIsNone(self.host.children[second["pid"]]["stopped"])
        self.assertFalse(Path(second["stop_request"]).exists())
        self.assertFalse(Path(first["stop_request"]).exists())

        # 4. A forged process identity alone (own Job Object name) is refused
        #    before the host is asked to stop anything: the recorded pid and the
        #    complete process identity do not match this run's own artifacts.
        forged = {**first, "pid": second["pid"], "process_identity": second["process_identity"]}
        write_record(background_jobs.index_path(self.manager, "NSC-898"), forged)
        self.assertFalse(background_jobs.authenticate_index(self.manager, forged)["identity_bound"])
        with self.assertRaisesRegex(BackgroundJobError, "does not authenticate"):
            background_jobs.cancel(self.manager, forged, host=self.host, reason="forged",
                                   grace_seconds=0, clock=self.clock, sleep=self.clock.sleep)
        refused = background_jobs.read_index(self.manager, "NSC-898")
        self.assertEqual("authentication_failed", refused["authentication"]["status"])
        self.assertEqual("launcher identity differs from the index",
                         refused["authentication"]["problems"][0])
        self.assertTrue(refused["provider_container_cleanup"]["authentication_failed"])
        self.assertFalse(Path(first["stop_request"]).exists())
        with self.assertRaisesRegex(background_jobs.StartupRefused, "nothing was stopped"):
            background_jobs.reconcile_startup(self.manager, self.host, invocation_id="restart",
                                              clock=self.clock, sleep=self.clock.sleep)
        self.assertEqual("running", background_jobs.observe(second, self.host)["status"])
        self.assertIsNone(self.host.children[second["pid"]]["stopped"])
        self.assertIsNone(self.host.children[first["pid"]]["stopped"])
        self.assertEqual([], self.host.docker_cli.removed)
        self.assertEqual({name}, set(self.host.docker_cli.containers))

    def test_clear_refuses_until_the_exact_container_is_verified_absent(self):
        self.prepare()
        index = self.launch(
            kind="decompose", task_id="NSC-898", duration=1.0, identity=dict(self.DECOMPOSE_IDENTITY),
            config=None, on_complete=lambda run_root, request, identity: write_receipt(
                run_root, request, identity, status="failed", error="fixture provider failure"),
        )
        name = index["provider_container"]["name"]
        self.clock.sleep(1.0)
        observed = background_jobs.observe(index, self.host)
        self.assertEqual("failed", observed["status"])
        harvested = background_jobs.harvest(self.manager, index, observed, invocation_id="h")
        self.assertTrue(background_jobs.cleanup_pending(harvested))  # harvested without a host
        self.host.docker_cli.create(name, "nosafecircle")
        self.host.docker_cli.available = False
        with self.assertRaisesRegex(BackgroundJobError, "not verified absent"):
            background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                  clock=self.clock, sleep=self.clock.sleep)
        retained = background_jobs.read_index(self.manager, "NSC-898")
        self.assertEqual(("failed", "refused"), (retained["status"], retained["provider_container_cleanup"]["status"]))
        self.host.docker_cli.available = True
        with self.assertRaisesRegex(BackgroundJobError, "late create could still land until"):
            background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                  clock=self.clock, sleep=self.clock.sleep)
        verified = background_jobs.read_index(self.manager, "NSC-898")
        self.assertEqual(("verified_absent", 1, 2), (verified["provider_container_cleanup"]["status"],
                                                     len(verified["provider_container_cleanup"]["removed"]),
                                                     verified["provider_container_cleanup"]["generation"]))
        self.assertEqual({}, self.host.docker_cli.containers)
        self.pass_tombstone()
        cleared = background_jobs.clear(self.manager, "NSC-898", job_id=index["job_id"], host=self.host,
                                        clock=self.clock, sleep=self.clock.sleep)
        self.assertTrue(cleared["cleared"])
        archived = _read(Path(cleared["archived"]))
        self.assertEqual(("verified_absent", 1), (archived["provider_container_cleanup"]["status"],
                                                  len(archived["provider_container_cleanup"]["removed"])))
        self.assertIsNotNone(archived["provider_container_cleanup"]["final_recheck_at_utc"])
        self.assertIsNone(background_jobs.read_index(self.manager, "NSC-898"))

    @unittest.skipUnless(os.name == "nt", "detached child identity is Windows-only")
    def test_real_restart_adopts_a_live_tree_then_quarantines_and_ends_it_with_its_container(self):
        from Pipeline.AssistantControl.process_identity import identify
        from Pipeline.AssistantControl.windows_job import active_count, is_assigned
        self.manager.records.mkdir(parents=True, exist_ok=True)
        docker = FixtureDocker(time.monotonic)
        launcher = background_jobs.DetachedHost(docker_runner=docker)
        index = background_jobs.launch(
            self.manager, kind="fixture", task_id="NSC-899",
            identity={"fixture": uuid.uuid4().hex, "delay_seconds": 120, "ignore_stop": True,
                      "spawn_sleeper": True, "simulate_container": True},
            config=None, invocation_id="real", provider_spend_authorized=False, host=launcher,
        )
        name = index["provider_container"]["name"]
        self.assertEqual({"name": background_jobs.container_name_for(index["job_id"]),
                          "compose_project": "fixture",
                          "labels": background_jobs.container_labels_for(
                              index["job_id"], self.manager.source, self.manager.root)},
                         index["provider_container"])
        run_root = Path(index["run_root"])
        marker_path = run_root / "fixture.marker.json"
        deadline = time.monotonic() + 30
        while not marker_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.1)
        sleeper = _read(marker_path)["sleeper"]
        self.assertEqual(sleeper["process_identity"], identify(sleeper["pid"]))
        self.assertGreaterEqual(active_count(index["job_name"]), 2)
        del launcher  # the launching controller process is gone

        # A restarted controller adopts the live, contained, authenticated tree.
        restarted = background_jobs.DetachedHost(docker_runner=docker)
        outcomes = background_jobs.reconcile_startup(
            self.manager, restarted, invocation_id="restart-1", grace_seconds=0.5)
        self.assertEqual([("adopted", index["job_id"])], [(item["outcome"], item["job_id"]) for item in outcomes])
        self.assertEqual([index["job_name"]], list(restarted._adopted))
        self.assertTrue(is_assigned(index["job_name"], index["process_identity"]))
        self.assertEqual("running", background_jobs.observe(index, restarted)["status"])
        self.assertEqual([], docker.calls)

        # The provider container exists now, and the child's handshake names
        # other ticket bytes: the next restart quarantines exactly this tree and
        # container (the ticket itself still authenticates).
        container_id = docker.create(
            name, "fixture", service="fixture",
            labels=background_jobs.container_labels_for(
                index["job_id"], self.manager.source, self.manager.root))
        child_path = run_root / "child.identity.json"
        write_record(child_path, {**_read(child_path), "request_sha256": "0" * 64})
        again = background_jobs.DetachedHost(docker_runner=docker)
        try:
            with patch.object(background_jobs, "CONTAINER_TOMBSTONE_SECONDS", 2.0):
                outcomes = background_jobs.reconcile_startup(
                    self.manager, again, invocation_id="restart-2", grace_seconds=0.5)
        finally:
            for job in restarted._adopted.values():
                job.close()
        self.assertEqual([("quarantined", index["job_id"])], [(item["outcome"], item["job_id"]) for item in outcomes])
        current = background_jobs.read_index(self.manager, "NSC-899")
        self.assertEqual("cancelled", current["status"])
        self.assertEqual(("quarantined", ["child identity handshake names other ticket bytes"]),
                         (current["reconciliation"]["outcome"], current["reconciliation"]["problems"]))
        self.assertIn("restart reconciliation: child identity handshake names other ticket bytes",
                      current["error"])
        self.assertFalse(again.alive(index["process_identity"]))
        self.assertNotEqual(sleeper["process_identity"], identify(sleeper["pid"]))
        self.assertEqual(0, active_count(index["job_name"]))
        self.assertFalse((run_root / "receipt.json").exists())
        cleanup = current["provider_container_cleanup"]
        self.assertEqual(("verified_absent", [container_id]), (cleanup["status"], cleanup["removed"]))
        self.assertEqual({}, docker.containers)
        # The quarantine waited the (shortened) bound out and recorded the final recheck.
        self.assertTrue(background_jobs.cleanup_final(current))
        self.assertIsNotNone(cleanup["final_recheck_at_utc"])
        self.assertGreaterEqual(cleanup["attempt"], 2)
        # Nothing was relaunched; a further restart finds nothing to reconcile.
        self.assertEqual([], background_jobs.reconcile_startup(
            self.manager, background_jobs.DetachedHost(docker_runner=docker), invocation_id="restart-3"))
        self.assertEqual(1, len(list((background_jobs.jobs_root(self.manager) / "NSC-899").iterdir())))

    @unittest.skipUnless(os.name == "nt", "detached child identity is Windows-only")
    def test_real_detached_child_completes_a_fixture_ticket(self):
        self.manager.records.mkdir(parents=True, exist_ok=True)
        host = background_jobs.DetachedHost()
        index = background_jobs.launch(
            self.manager, kind="fixture", task_id="NSC-899", identity={"fixture": uuid.uuid4().hex},
            config=None, invocation_id="real", provider_spend_authorized=False, host=host,
        )
        self.assertEqual("running", index["status"])
        self.assertIsInstance(index["process_identity"]["created_ticks"], int)
        deadline = time.monotonic() + 60
        observed = background_jobs.observe(index, host)
        while observed["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.1)
            observed = background_jobs.observe(index, host)
        stderr = (Path(index["run_root"]) / "stderr.log").read_text(encoding="utf-8", errors="replace")
        self.assertEqual("completed", observed["status"], stderr)
        receipt = observed["receipt"]
        self.assertEqual(index["process_identity"], receipt["process_identity"])
        self.assertEqual("fixture_completed", receipt["result"]["status"])
        self.assertTrue((Path(index["run_root"]) / "fixture.marker.json").is_file())
        self.assertTrue((Path(index["run_root"]) / "child.identity.json").is_file())
        harvested = background_jobs.harvest(self.manager, index, observed, invocation_id="real")
        self.assertEqual(("completed", "fixture_completed"),
                         (harvested["status"], harvested["result_status"]))
        deadline = time.monotonic() + 10
        while host.alive(index["process_identity"]) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(host.alive(index["process_identity"]))
        opened = _read(Path(index["run_root"]) / "job.opened.json")
        self.assertEqual((index["job_id"], index["job_name"], index["pid"], index["process_identity"]),
                         (opened["job_id"], opened["job_name"], opened["pid"], opened["process_identity"]))

    @unittest.skipUnless(os.name == "nt", "detached child identity is Windows-only")
    def test_real_detached_child_proves_job_object_handoff_and_cooperative_stop(self):
        from Pipeline.AssistantControl.windows_job import active_count, is_assigned
        self.manager.records.mkdir(parents=True, exist_ok=True)
        host = background_jobs.DetachedHost()
        index = background_jobs.launch(
            self.manager, kind="fixture", task_id="NSC-899",
            identity={"fixture": uuid.uuid4().hex, "delay_seconds": 120},
            config=None, invocation_id="real", provider_spend_authorized=False, host=host,
        )
        run_root = Path(index["run_root"])
        # launch() returned only after the exact child acknowledged the named
        # Job Object; the parent then released its own handle.
        opened = _read(run_root / "job.opened.json")
        self.assertEqual((index["job_id"], index["job_name"], index["pid"], index["process_identity"]),
                         (opened["job_id"], opened["job_name"], opened["pid"], opened["process_identity"]))
        self.assertEqual({}, host._job_handles)
        self.assertTrue(is_assigned(index["job_name"], index["process_identity"]))
        self.assertGreaterEqual(active_count(index["job_name"]), 1)
        self.assertEqual("running", background_jobs.observe(index, host)["status"])

        stopped = background_jobs.cancel(
            self.manager, index, host=host, reason="real cooperative stop",
            grace_seconds=10.0, invocation_id="real",
        )
        self.assertEqual(("cancelled", "operator stopped background job"),
                         (stopped["status"], stopped["error"]))
        receipt = _read(run_root / "receipt.json")
        self.assertEqual(("stopped", "fixture_stopped", index["process_identity"]),
                         (receipt["status"], receipt["result"]["status"], receipt["process_identity"]))
        deadline = time.monotonic() + 10
        while (host.alive(index["process_identity"]) or active_count(index["job_name"])) \
                and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(host.alive(index["process_identity"]))
        self.assertEqual(0, active_count(index["job_name"]))

    @unittest.skipUnless(os.name == "nt", "detached child identity is Windows-only")
    def test_real_detached_child_tree_is_terminated_on_forced_stop(self):
        from Pipeline.AssistantControl.process_identity import identify
        from Pipeline.AssistantControl.windows_job import active_count
        self.manager.records.mkdir(parents=True, exist_ok=True)
        host = background_jobs.DetachedHost()
        index = background_jobs.launch(
            self.manager, kind="fixture", task_id="NSC-899",
            identity={"fixture": uuid.uuid4().hex, "delay_seconds": 120,
                      "ignore_stop": True, "spawn_sleeper": True},
            config=None, invocation_id="real", provider_spend_authorized=False, host=host,
        )
        run_root = Path(index["run_root"])
        marker_path = run_root / "fixture.marker.json"
        deadline = time.monotonic() + 30
        while not marker_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.1)
        sleeper = _read(marker_path)["sleeper"]
        self.assertEqual(sleeper["process_identity"], identify(sleeper["pid"]))
        self.assertGreaterEqual(active_count(index["job_name"]), 2)

        stopped = background_jobs.cancel(
            self.manager, index, host=host, reason="real forced stop",
            grace_seconds=0.5, invocation_id="real",
        )
        self.assertEqual("cancelled", stopped["status"])
        self.assertIn("without a receipt: real forced stop", stopped["error"])
        self.assertFalse(host.alive(index["process_identity"]))
        self.assertNotEqual(sleeper["process_identity"], identify(sleeper["pid"]))
        self.assertEqual(0, active_count(index["job_name"]))
        self.assertFalse((run_root / "receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
