#!/usr/bin/env python3
"""Regression: one concurrent decomposition apply must not kill the scheduler.

Classification: pure/component tests over disposable temporary Git repositories.
Real Git plumbing runs against a throwaway bare origin and its clone; the
TaskGraph payload, managed-Issue batch, dispatch policy, and scheduler are
injected. No GitHub, provider, Docker, Unity asset, canonical checkout, or
tracked repository state is read or mutated.

Contract mapping: explicit regression-only invariant.

Stage D1C apply workers share the scheduler's controller checkout. A legitimate
apply creates a local commit, moves HEAD, and pushes origin/main, and that lands
inside the coherent snapshot construction the scheduler is running at the same
time. The before/after coherence proof correctly refused the torn observation,
but the refusal was raised as a terminal adapter failure, so the whole
autonomous run exited with status ``adapter_failure`` after the apply worker had
already succeeded and an operator had to restart the run by hand.

The proof here is behavioral, at base semantics: real ``git commit`` and
``git push`` move the real shared checkout underneath the real observation.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any, Iterator
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.production_graph_snapshot as snapshot_module  # noqa: E402
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    AutonomousGraphController,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    MemoryProgressStore,
    MemoryReceiptStore,
)
from Pipeline.TaskReviewAgent.git_identity_guard import (  # noqa: E402
    DEFAULT_AGENT_GIT_EMAIL,
    DEFAULT_AGENT_GIT_NAME,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    DurableWorkflowObservation,
)
from Pipeline.TaskReviewAgent.production_graph_snapshot import (  # noqa: E402
    ProductionCoherentSnapshotter,
    ProductionGraphSnapshotError,
)


TASK = "NSC-901"
WORKER = "coherent-snapshot-apply-race-worker"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"fixture command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout.strip()


def git(root: Path, *args: str) -> str:
    return run("git", "-C", str(root), *args, cwd=root)


def controller_checkout(root: Path) -> Path:
    """Create the shared controller checkout: clean attached main with an origin."""

    origin = root / "origin.git"
    run("git", "init", "--bare", "-b", "main", str(origin), cwd=root)
    source = root / "controller"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", DEFAULT_AGENT_GIT_NAME)
    git(source, "config", "user.email", DEFAULT_AGENT_GIT_EMAIL)
    git(source, "config", "commit.gpgsign", "false")
    git(source, "remote", "add", "origin", str(origin))
    (source / "graph.json").write_text("{}\n", encoding="utf-8")
    git(source, "add", "graph.json")
    git(source, "commit", "-m", "controller base")
    git(source, "push", "-u", "origin", "main")
    return source


def apply_decomposition(source: Path, marker: str) -> str:
    """Model one D1C apply worker mutating the shared controller checkout."""

    (source / f"{marker}.json").write_text("{}\n", encoding="utf-8")
    git(source, "add", f"{marker}.json")
    git(source, "commit", "-m", f"taskgraph: apply {marker}")
    git(source, "push", "origin", "main")
    return git(source, "rev-parse", "HEAD")


def manifest(source: Path) -> AutonomousRunManifest:
    return AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id="coherent-snapshot-apply-race",
        source_repository=str(source),
        github_repository="fixture-owner/pipeline-rehearsal",
        runtime_configuration=AutonomousRuntimeConfiguration(
            execution_provider="claude",
            execution_model=None,
            execution_max_turns=120,
            architect_provider="claude",
            architect_model=None,
            architect_max_turns=24,
            architect_min_confidence=0.7,
            architect_max_invocations_per_poll=3,
            architect_min_reanalysis_seconds=300.0,
            max_consecutive_observation_failures=3,
            fatal_drain_seconds=1800.0,
            fallback_seconds=300.0,
            synthetic_evidence_enabled=False,
        ),
        initial_source_commit=git(source, "rev-parse", "HEAD"),
        initial_source_tree=git(source, "rev-parse", "HEAD^{tree}"),
        target_task_ids=(TASK,),
        excluded_task_ids=(),
        max_capacity=10,
    )


class FixtureScheduler:
    """The exact scheduler surface this controller and adapter actually use."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.max_workers = 10
        self.excluded_task_ids: frozenset[str] = frozenset()
        self.active_assignments: dict[str, object] = {}
        self.architect_invocations_this_poll = 0
        self.worker_launches_this_poll = 0
        self.poll_calls = 0
        self.waits: list[float] = []
        self.allowlists: list[tuple[str, ...]] = []
        self.drain_calls = 0

    def set_admission_allowlist(self, task_ids: Any) -> None:
        self.allowlists.append(tuple(sorted(task_ids)))

    def reconcile_interrupted_architect_session(self, *, lock: Any) -> bool:
        require(lock.held, "architect recovery ran without scheduler ownership")
        return False

    def start_activity_listener(self) -> bool:
        return True

    def close_activity_listener(self) -> None:
        return None

    def drain_active_workers(self, *, poll_seconds: float, stop_reason: str) -> bool:
        self.drain_calls += 1
        return True

    def poll_capacity_batch(self) -> SimpleNamespace:
        self.poll_calls += 1
        return SimpleNamespace(status="idle", fatal=False)

    def _wait_for_architect_activity(self, poll_seconds: float) -> str:
        self.waits.append(poll_seconds)
        return "fallback_elapsed"


class FixtureLock:
    def __init__(self) -> None:
        self.held = False

    def acquire(self) -> None:
        self.held = True

    def release(self) -> None:
        self.held = False


@contextlib.contextmanager
def injected_graph_payload(
    source: Path,
    *,
    apply_during: frozenset[int],
    observations: list[str],
) -> Iterator[None]:
    """Serve the TaskGraph/Issue payload and race the requested observations.

    ``taskcontrol_states_snapshot`` is the exact call the production adapter
    makes between its two source-identity captures, so applying there reproduces
    the live interleaving instead of simulating it. Git, the source refresh, both
    identity captures, and both ancestry proofs stay real.
    """

    def rows(*_args: Any, **_kwargs: Any) -> dict[str, dict[str, Any]]:
        observations.append("observation")
        if len(observations) in apply_during:
            apply_decomposition(source, f"apply-{len(observations)}")
        return {
            TASK: {
                "task_id": TASK,
                "state": "not_delivered",
                "decomposition_children": [],
                "head_commit": git(source, "rev-parse", "HEAD"),
            }
        }

    with (
        patch.object(
            snapshot_module, "list_committed_task_ids", return_value=(TASK,)
        ),
        patch.object(
            snapshot_module, "taskcontrol_states_snapshot", side_effect=rows
        ),
        patch.object(
            snapshot_module,
            "load_dispatch_policy",
            return_value=SimpleNamespace(
                known_dependency_states={"not_delivered", "aggregate", "conformant"}
            ),
        ),
        patch.object(
            snapshot_module,
            "observe_durable_workflows",
            return_value=DurableWorkflowObservation((), ()),
        ),
    ):
        yield


def snapshotter(
    source: Path,
    scheduler: FixtureScheduler,
    run_manifest: AutonomousRunManifest,
) -> ProductionCoherentSnapshotter:
    return ProductionCoherentSnapshotter(
        manifest=run_manifest,
        scheduler=scheduler,
        checkout_root=source.parent / "checkouts",
        worker_id=WORKER,
        backend_factory=lambda _root: MemoryIssueBackend(),
    )


def test_apply_race_settles_into_a_snapshot_at_the_new_coherent_state() -> None:
    """A mid-observation apply costs one discarded attempt, not the run."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = controller_checkout(root)
        base = git(source, "rev-parse", "HEAD")
        run_manifest = manifest(source)
        scheduler = FixtureScheduler(source)
        observations: list[str] = []
        with injected_graph_payload(
            source, apply_during=frozenset({1}), observations=observations
        ):
            observed = snapshotter(source, scheduler, run_manifest)()

        applied = git(source, "rev-parse", "HEAD")
        require(applied != base, "the fixture apply never moved the shared checkout")
        require(
            len(observations) == 2,
            f"expected one discarded and one coherent observation: {observations}",
        )
        require(
            observed.source_head == applied,
            f"snapshot did not settle at the applied commit: {observed.source_head}",
        )
        require(
            observed.origin_main_head == applied,
            f"snapshot did not settle at the pushed origin/main: {observed}",
        )
        require(
            observed.source_branch == "main"
            and observed.source_attached
            and observed.source_clean,
            f"snapshot was accepted from an unsafe source state: {observed}",
        )
        require(
            observed.observation_revision == 1,
            f"a discarded attempt was counted as an observation: {observed}",
        )


def test_autonomous_run_survives_an_apply_that_moves_the_shared_checkout() -> None:
    """The run keeps going: the apply worker succeeded and so must the scheduler."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = controller_checkout(root)
        run_manifest = manifest(source)
        scheduler = FixtureScheduler(source)
        controller = AutonomousGraphController(
            manifest=run_manifest,
            scheduler=scheduler,
            scheduler_lock=FixtureLock(),
            snapshotter=snapshotter(source, scheduler, run_manifest),
            progress_store=MemoryProgressStore(),
            receipt_store=MemoryReceiptStore(),
            fallback_seconds=0.01,
            transition_settle_seconds=0.01,
        )
        observations: list[str] = []
        with injected_graph_payload(
            source, apply_during=frozenset({1}), observations=observations
        ):
            result = controller.run(max_steps=1)

        require(
            result.evaluation.classification == "actionable",
            f"the raced step did not classify normally: {result.evaluation}",
        )
        require(scheduler.poll_calls == 1, f"the step never polled: {scheduler}")
        require(
            result.progress.baseline_verified,
            f"the raced preflight never verified its baseline: {result.progress}",
        )


def test_a_source_that_never_settles_still_fails_closed_after_the_bound() -> None:
    """Re-observation is bounded and still refuses to publish a torn snapshot."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = controller_checkout(root)
        run_manifest = manifest(source)
        scheduler = FixtureScheduler(source)
        observations: list[str] = []
        attempts = snapshot_module.MAX_COHERENT_OBSERVATION_ATTEMPTS
        every_attempt = frozenset(range(1, attempts + 1))
        with injected_graph_payload(
            source, apply_during=every_attempt, observations=observations
        ):
            try:
                snapshotter(source, scheduler, run_manifest)()
            except ProductionGraphSnapshotError as exc:
                require(
                    "moved during coherent snapshot construction" in str(exc),
                    f"unexpected fail-closed reason: {exc}",
                )
            else:
                raise AssertionError(
                    "an endlessly moving source produced a coherent snapshot"
                )
        require(
            len(observations) == attempts,
            f"re-observation was not bounded at the exact attempt limit: {observations}",
        )


def test_the_re_observation_bound_cannot_be_configured_away() -> None:
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        source = controller_checkout(root)
        scheduler = FixtureScheduler(source)
        try:
            ProductionCoherentSnapshotter(
                manifest=manifest(source),
                scheduler=scheduler,
                checkout_root=root / "checkouts",
                worker_id=WORKER,
                backend_factory=lambda _root: MemoryIssueBackend(),
                max_observation_attempts=0,
            )
        except ProductionGraphSnapshotError as exc:
            require(
                "max_observation_attempts must be a positive integer" in str(exc),
                f"unexpected guard message: {exc}",
            )
        else:
            raise AssertionError("a non-positive re-observation bound was accepted")


def main() -> int:
    tests = (
        test_apply_race_settles_into_a_snapshot_at_the_new_coherent_state,
        test_autonomous_run_survives_an_apply_that_moves_the_shared_checkout,
        test_a_source_that_never_settles_still_fails_closed_after_the_bound,
        test_the_re_observation_bound_cannot_be_configured_away,
    )
    for test in tests:
        test()
    print(f"coherent_snapshot_apply_race_smoke_test: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
