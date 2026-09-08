"""Production admission obeys architect capacity decisions below the ceiling."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import hashlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as f
from Pipeline.TaskReviewAgent.architect_preflight import ArchitectBatch


class CapacityArchitect(f.FakeArchitect):
    desired = 10
    rationale = "Ready width, narrow paths and fast rigor permit this capacity; provider quota is unknown."

    def __call__(self, **values):
        context = values["candidates"][0]["capacity_context"]
        values["admission_limit"] = min(values["admission_limit"], max(0, self.desired - context["active_workers"]))
        result = super().__call__(**values)
        return replace(result, batch=replace(result.batch, desired_active_capacity=self.desired,
                                             capacity_rationale=self.rationale))


class CapacityTest(unittest.TestCase):
    def exercise(self, desired, *, active=0, conflict=False, dishonest=False):
        contracts = {f"NSC-{number:03d}": hashlib.sha256(str(number).encode()).hexdigest()
                     for number in (10, 11, 12, 13, 100, 101)}
        with tempfile.TemporaryDirectory(prefix="architect-capacity-") as directory, patch.dict(f.CONTRACTS, contracts):
            source, head = f.create_source(Path(directory))
            ids = ("NSC-010", "NSC-011", "NSC-012", "NSC-013")
            tasks = {key: f.task(key) for key in ids}
            architect = CapacityArchitect({key: f.advisory(key, head,
                exact_paths=("Assets/Shared.cs" if conflict else f"Assets/{key}.cs",)) for key in ids})
            architect.desired = desired
            if desired == 0:
                architect.rationale = "Health backoff: provider capacity is unproven; wait for recovery."
            processes = f.ProcessFactory()
            runner = architect
            if dishonest:
                def runner(**values):
                    result = f.FakeArchitect.__call__(architect, **values)
                    return replace(result, batch=replace(result.batch, desired_active_capacity=desired, capacity_rationale="Invalid over-admission fixture"))
            scheduler, stream = f.make_orchestrator(source=source,
                planner=f.SequencePlanner([f.candidate_plan(head, *ids)]), architect=runner,
                processes=processes, tasks=tasks, max_workers=4)
            for index in range(active):
                f.add_active(scheduler, task_id=f"NSC-{100 + index}", process=f.FakeProcess())
            scheduler.poll_once()
            events = [json.loads(line) for line in stream.getvalue().splitlines()]
            return len(processes.calls), len(scheduler.active_assignments), events

    def test_scale_up_and_underfill_are_decisions(self):
        self.assertEqual(self.exercise(2)[:2], (2, 2))
        self.assertEqual(self.exercise(4)[:2], (4, 4))

    def test_scale_down_drains_without_killing(self):
        self.assertEqual(self.exercise(1, active=2)[:2], (0, 2))

    def test_health_backoff_can_choose_zero(self):
        self.assertEqual(self.exercise(0)[:2], (0, 0))

    def test_health_recovery_reconsiders_same_head_without_stale_wait(self):
        with tempfile.TemporaryDirectory(prefix="capacity-recovery-") as directory:
            source, head = f.create_source(Path(directory))
            task_id = f.TASK_A
            architect = CapacityArchitect({task_id: f.advisory(task_id, head)})
            architect.desired = 0
            processes = f.ProcessFactory()
            scheduler, stream = f.make_orchestrator(source=source,
                planner=f.SequencePlanner([f.candidate_plan(head, task_id)]), architect=architect,
                processes=processes, tasks={task_id: f.task(task_id)}, max_workers=4)
            scheduler.poll_once()
            self.assertEqual(len(processes.calls), 0)
            architect.desired = 4
            scheduler.poll_once()
            self.assertEqual(len(processes.calls), 1)
            self.assertEqual(len(architect.calls), 2)

    def test_recent_observation_failure_reaches_capacity_decision(self):
        with tempfile.TemporaryDirectory(prefix="capacity-health-") as directory:
            source, head = f.create_source(Path(directory))
            task_id = f.TASK_A
            contexts = []
            class HealthArchitect(CapacityArchitect):
                def __call__(self, **values):
                    context = values["candidates"][0]["capacity_context"]
                    contexts.append(context)
                    self.desired = 0 if context["recent_failures"] else 4
                    return super().__call__(**values)
            observations = 0
            def reservations():
                nonlocal observations
                observations += 1
                if observations == 1:
                    raise OSError("transient observation failure")
                return ()
            architect = HealthArchitect({task_id: f.advisory(task_id, head)})
            processes = f.ProcessFactory()
            clock = f.MutableClock()
            scheduler, _ = f.make_orchestrator(source=source,
                planner=f.SequencePlanner([f.candidate_plan(head, task_id)]), architect=architect,
                processes=processes, tasks={task_id: f.task(task_id)}, max_workers=4,
                reservation_observer=reservations, monotonic_clock=clock)
            scheduler.poll_once()
            self.assertEqual(contexts, [])
            scheduler.poll_once()
            self.assertEqual(contexts[0]["recent_failures"][0]["kind"], "reservation_observation")
            self.assertEqual(len(processes.calls), 0)
            clock.advance(301)
            scheduler.poll_once()
            self.assertEqual(contexts[-1]["recent_failures"], [])
            self.assertEqual(len(processes.calls), 1)

    def test_conflicts_underfill_desired_capacity(self):
        self.assertEqual(self.exercise(4, conflict=True)[:2], (1, 1))

    def test_ceiling_and_overadmission_fail_before_launch(self):
        self.assertEqual(self.exercise(5)[:2], (0, 0))
        self.assertEqual(self.exercise(1, dishonest=True)[:2], (0, 0))

    def test_capacity_schema_roundtrip_is_bound(self):
        value = f.ArchitectBatch(source_head="a" * 40, batch_rationale="fixture", considered=(), admissions=(),
            desired_active_capacity=0, capacity_rationale="Backoff while health is unknown.")
        self.assertEqual(ArchitectBatch.from_dict(value.to_dict()), value)
        mutated = value.to_dict()
        mutated["desired_active_capacity"] = 11
        with self.assertRaises(ValueError):
            ArchitectBatch.from_dict(mutated)


if __name__ == "__main__":
    unittest.main()
