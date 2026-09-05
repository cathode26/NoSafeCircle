#!/usr/bin/env python3
"""Run one exact TaskGraph scope to a durable graph-complete receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.architect_preflight import (  # noqa: E402
    DEFAULT_ARCHITECT_MAX_TURNS,
    DEFAULT_ARCHITECT_MIN_CONFIDENCE,
)
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    DEFAULT_FALLBACK_SECONDS,
    MAX_AUTONOMOUS_CAPACITY,
    AutonomousGraphController,
    AutonomousGraphRunError,
    AutonomousRunManifest,
    AutonomousRunPaths,
    AutonomousRuntimeConfiguration,
    JsonManifestStore,
    JsonProgressStore,
    JsonReceiptStore,
    autonomous_run_paths,
    evaluate_graph_state,
)
from Pipeline.TaskReviewAgent.contracts import validate_task_id  # noqa: E402
from Pipeline.TaskReviewAgent.provider_policy import parse_provider_allowlist  # noqa: E402
from Pipeline.TaskReviewAgent.issue_queue import repo_root  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import WorkflowState  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    resolve_issue_backend_repository,
)
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS,
    DEFAULT_FATAL_DRAIN_SECONDS,
    DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL,
    DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES,
    SchedulerLock,
    build_production_orchestrator,
    refresh_source_main,
    scheduler_lock_path,
)
from Pipeline.TaskReviewAgent.production_graph_snapshot import (  # noqa: E402
    ProductionCoherentSnapshotter,
)
from Pipeline.TaskReviewAgent.real_checkout import default_checkout_root  # noqa: E402
from Pipeline.TaskReviewAgent.synthetic_gauntlet_approver import (  # noqa: E402
    PRESERVED_TASK_ID,
    SyntheticHandoffProcessor,
)


EXIT_COMPLETE = 0
EXIT_BLOCKED = 2
EXIT_DEADLOCK = 3
EXIT_SCHEDULER_FATAL = 4
EXIT_ADAPTER_FAILURE = 5
EXIT_WORK_REMAINS = 10


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _capacity(value: str) -> int:
    parsed = _positive_int(value)
    if parsed > MAX_AUTONOMOUS_CAPACITY:
        raise argparse.ArgumentTypeError(
            f"capacity must be in 1..{MAX_AUTONOMOUS_CAPACITY}"
        )
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = _non_negative_float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _confidence(value: str) -> float:
    parsed = _non_negative_float(value)
    if parsed > 1:
        raise argparse.ArgumentTypeError("confidence must be in [0, 1]")
    return parsed


def _git_text(source: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(source), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60.0,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise AutonomousGraphRunError(
            "Git identity observation failed"
            + (f": {detail[:500]}" if detail else "")
        )
    try:
        value = result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise AutonomousGraphRunError("Git identity output was not UTF-8") from exc
    if not value:
        raise AutonomousGraphRunError("Git identity observation was empty")
    return value


def _sorted_task_ids(values: Sequence[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    normalized = tuple(sorted({validate_task_id(value) for value in values}))
    if len(normalized) != len(values):
        raise AutonomousGraphRunError("task ID arguments must be duplicate-free")
    return normalized


def _scheduler_id(repository: str, run_id: str) -> str:
    digest = hashlib.sha256(
        f"{repository.casefold()}:{run_id}".encode("utf-8")
    ).hexdigest()
    return f"autonomous-{digest[:20]}"


def _runtime_configuration(
    args: argparse.Namespace,
    existing: AutonomousRuntimeConfiguration | None,
) -> AutonomousRuntimeConfiguration:
    defaults = {
        "provider_allowlist": None,
        "execution_provider": None,
        "execution_model": None,
        "execution_max_turns": 120,
        "architect_provider": "claude",
        "architect_model": None,
        "architect_max_turns": DEFAULT_ARCHITECT_MAX_TURNS,
        "architect_min_confidence": DEFAULT_ARCHITECT_MIN_CONFIDENCE,
        "architect_max_invocations_per_poll": (
            DEFAULT_MAX_ARCHITECT_INVOCATIONS_PER_POLL
        ),
        "architect_min_reanalysis_seconds": (
            DEFAULT_ARCHITECT_MIN_REANALYSIS_SECONDS
        ),
        "max_consecutive_observation_failures": (
            DEFAULT_MAX_CONSECUTIVE_OBSERVATION_FAILURES
        ),
        "fatal_drain_seconds": DEFAULT_FATAL_DRAIN_SECONDS,
        "fallback_seconds": DEFAULT_FALLBACK_SECONDS,
        "synthetic_evidence_enabled": False,
    }
    arguments = {
        "provider_allowlist": args.provider_allowlist,
        "execution_provider": args.execution_provider,
        "execution_model": args.model,
        "execution_max_turns": args.max_turns,
        "architect_provider": args.architect_provider,
        "architect_model": args.architect_model,
        "architect_max_turns": args.architect_max_turns,
        "architect_min_confidence": args.architect_min_confidence,
        "architect_max_invocations_per_poll": (
            args.architect_max_invocations_per_poll
        ),
        "architect_min_reanalysis_seconds": args.architect_min_reanalysis_seconds,
        "max_consecutive_observation_failures": (
            args.max_consecutive_observation_failures
        ),
        "fatal_drain_seconds": args.fatal_drain_seconds,
        "fallback_seconds": args.fallback_seconds,
        "synthetic_evidence_enabled": args.synthetic_evidence_enabled,
    }
    if existing is not None:
        for field, requested in arguments.items():
            if requested is not None and requested != getattr(existing, field):
                raise AutonomousGraphRunError(
                    f"requested runtime setting {field} differs from the persisted run"
                )
        return existing
    return AutonomousRuntimeConfiguration(
        **{
            field: defaults[field] if value is None else value
            for field, value in arguments.items()
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--checkout-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--confirm-repository", required=True)
    parser.add_argument("--target-task-id", action="append")
    parser.add_argument("--exclude-task-id", action="append")
    parser.add_argument("--max-workers", type=_capacity)
    parser.add_argument("--execution-provider", choices=("claude", "codex"))
    parser.add_argument("--provider-allowlist", type=parse_provider_allowlist)
    parser.add_argument("--model")
    parser.add_argument("--max-turns", type=_positive_int)
    parser.add_argument("--architect-provider", choices=("claude", "codex"))
    parser.add_argument("--architect-model")
    parser.add_argument(
        "--architect-max-turns",
        type=_positive_int,
    )
    parser.add_argument(
        "--architect-min-confidence",
        type=_confidence,
    )
    parser.add_argument(
        "--architect-max-invocations-per-poll",
        type=_positive_int,
    )
    parser.add_argument(
        "--architect-min-reanalysis-seconds",
        type=_non_negative_float,
    )
    parser.add_argument(
        "--max-consecutive-observation-failures",
        type=_positive_int,
    )
    parser.add_argument(
        "--fatal-drain-seconds",
        type=_non_negative_float,
    )
    parser.add_argument(
        "--fallback-seconds",
        type=_positive_float,
    )
    synthetic = parser.add_mutually_exclusive_group()
    synthetic.add_argument(
        "--enable-synthetic-evidence",
        dest="synthetic_evidence_enabled",
        action="store_true",
        help=(
            "Advance only exact private rehearsal gauntlet handoffs with "
            "machine evidence; never fabricates human PASS."
        ),
    )
    synthetic.add_argument(
        "--disable-synthetic-evidence",
        dest="synthetic_evidence_enabled",
        action="store_false",
    )
    parser.set_defaults(synthetic_evidence_enabled=None)
    parser.add_argument(
        "--completion-probe",
        action="store_true",
        help="Return 0 only for an existing exact receipt, or 10 when work remains.",
    )
    return parser


def _load_or_create_manifest(
    *,
    source: Path,
    checkout_root: Path,
    repository: str,
    run_id: str,
    requested_targets: tuple[str, ...] | None,
    requested_exclusions: tuple[str, ...] | None,
    requested_capacity: int | None,
    runtime_configuration: AutonomousRuntimeConfiguration,
    existing: AutonomousRunManifest | None = None,
) -> tuple[AutonomousRunManifest, AutonomousRunPaths]:
    paths = autonomous_run_paths(
        checkout_root=checkout_root,
        github_repository=repository,
        run_id=run_id,
    )
    store = JsonManifestStore(paths.manifest)
    existing = store.load() if existing is None else existing
    if existing is not None:
        if Path(existing.source_repository).resolve() != source:
            raise AutonomousGraphRunError(
                "persisted manifest source differs from this exact checkout"
            )
        if existing.github_repository.casefold() != repository.casefold():
            raise AutonomousGraphRunError(
                "persisted manifest repository differs from the origin authority"
            )
        if existing.runtime_configuration != runtime_configuration:
            raise AutonomousGraphRunError(
                "requested runtime configuration differs from the persisted exact run"
            )
        checks = (
            (requested_targets, existing.target_task_ids, "target task IDs"),
            (requested_exclusions, existing.excluded_task_ids, "excluded task IDs"),
            (requested_capacity, existing.max_capacity, "maximum capacity"),
        )
        for requested, durable, label in checks:
            if requested is not None and requested != durable:
                raise AutonomousGraphRunError(
                    f"requested {label} differ from the persisted exact run"
                )
        return existing, paths

    if not requested_targets:
        raise AutonomousGraphRunError(
            "a new autonomous run requires at least one --target-task-id"
        )
    exclusions = requested_exclusions or ()
    capacity = requested_capacity or MAX_AUTONOMOUS_CAPACITY
    refresh_source_main(source)
    initial_commit = _git_text(source, "rev-parse", "--verify", "HEAD^{commit}")
    initial_tree = _git_text(
        source, "rev-parse", "--verify", f"{initial_commit}^{{tree}}"
    )
    manifest = AutonomousRunManifest(
        schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
        run_id=run_id,
        source_repository=str(source),
        github_repository=repository,
        runtime_configuration=runtime_configuration,
        initial_source_commit=initial_commit,
        initial_source_tree=initial_tree,
        target_task_ids=requested_targets,
        excluded_task_ids=exclusions,
        max_capacity=capacity,
    )
    return store.create_or_load(manifest), paths


def _write_result(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


class _SyntheticEvidencePump:
    """Lazily open the private-rehearsal adapter for one eligible handoff."""

    def __init__(
        self,
        *,
        manifest: AutonomousRunManifest,
        source: Path,
        checkout_root: Path,
        repository: str,
    ) -> None:
        self.manifest = manifest
        self.source = source
        self.checkout_root = checkout_root
        self.repository = repository
        self.processor: SyntheticHandoffProcessor | None = None

    def __call__(self, snapshot: Any) -> Any:
        # A failed-push D1C recovery owns the source-main divergence. The
        # synthetic adapter deliberately requires exact origin/main and must
        # not preflight or advance unrelated handoffs until recovery settles.
        if snapshot.authorized_local_ahead_recovery_task_id is not None:
            return None
        relevant = set(
            evaluate_graph_state(self.manifest, snapshot).relevant_task_ids
        )
        unavailable = set(snapshot.active_assignment_task_ids).union(
            snapshot.pending_transition_task_ids
        )
        candidates = sorted(
            issue.task_id
            for issue in snapshot.managed_issues
            if issue.task_id in relevant
            and issue.task_id not in unavailable
            and issue.task_id != PRESERVED_TASK_ID
            and issue.state is WorkflowState.HUMAN_ACTION_REQUIRED
        )
        if not candidates:
            return None
        if self.processor is None:
            self.processor = SyntheticHandoffProcessor(
                source=self.source,
                checkout_root=self.checkout_root,
                confirm_repository=self.repository,
            )
        return self.processor.process_one(
            candidates[0], expected_source_head=snapshot.source_head
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = repo_root(args.source.resolve())
        checkout_root = Path(args.checkout_root or default_checkout_root()).resolve()
        repository = resolve_issue_backend_repository(
            source, repository=args.confirm_repository
        )
        targets = _sorted_task_ids(args.target_task_id)
        exclusions = _sorted_task_ids(args.exclude_task_id)
        paths = autonomous_run_paths(
            checkout_root=checkout_root,
            github_repository=repository,
            run_id=args.run_id,
        )
        manifest_store = JsonManifestStore(paths.manifest)
        existing_manifest = manifest_store.load()
        runtime = _runtime_configuration(
            args,
            existing_manifest.runtime_configuration
            if existing_manifest is not None
            else None,
        )
        manifest: AutonomousRunManifest | None = None
        if existing_manifest is not None:
            manifest, _ = _load_or_create_manifest(
                source=source,
                checkout_root=checkout_root,
                repository=repository,
                run_id=args.run_id,
                requested_targets=targets,
                requested_exclusions=exclusions,
                requested_capacity=args.max_workers,
                runtime_configuration=runtime,
                existing=existing_manifest,
            )
        receipts = JsonReceiptStore(paths.receipt)
        completed = receipts.load()
        if completed is not None:
            if manifest is None:
                raise AutonomousGraphRunError(
                    "graph-complete receipt exists without its immutable run manifest"
                )
            if completed.manifest_sha256 != manifest.sha256:
                raise AutonomousGraphRunError(
                    "graph-complete receipt belongs to a different exact run manifest"
                )
            _write_result(
                {
                    "status": "already_complete",
                    "run_id": manifest.run_id,
                    "receipt": completed.to_dict(),
                }
            )
            return EXIT_COMPLETE

        if args.completion_probe:
            _write_result({"status": "work_remains", "run_id": args.run_id})
            return EXIT_WORK_REMAINS

        if manifest is None:
            manifest_lock = SchedulerLock(
                scheduler_lock_path(
                    checkout_root=checkout_root,
                    source=source,
                )
            )
            manifest_lock.acquire()
            try:
                manifest, _ = _load_or_create_manifest(
                    source=source,
                    checkout_root=checkout_root,
                    repository=repository,
                    run_id=args.run_id,
                    requested_targets=targets,
                    requested_exclusions=exclusions,
                    requested_capacity=args.max_workers,
                    runtime_configuration=runtime,
                )
            finally:
                manifest_lock.release()

        production = build_production_orchestrator(
            source=source,
            checkout_root=checkout_root,
            scheduler_id=_scheduler_id(repository, args.run_id),
            execution_provider=runtime.execution_provider,
            provider_allowlist=runtime.provider_allowlist,
            model=runtime.execution_model,
            max_turns=runtime.execution_max_turns,
            max_workers=manifest.max_capacity,
            architect_provider=runtime.architect_provider,
            architect_model=runtime.architect_model,
            architect_max_turns=runtime.architect_max_turns,
            architect_min_confidence=runtime.architect_min_confidence,
            max_architect_invocations_per_poll=(
                runtime.architect_max_invocations_per_poll
            ),
            architect_min_reanalysis_seconds=(
                runtime.architect_min_reanalysis_seconds
            ),
            max_consecutive_observation_failures=(
                runtime.max_consecutive_observation_failures
            ),
            fatal_drain_seconds=runtime.fatal_drain_seconds,
            excluded_task_ids=manifest.excluded_task_ids,
            event_journal_path=paths.events,
        )
        if (
            production.orchestrator.max_workers != manifest.max_capacity
            or getattr(production.orchestrator, "provider_allowlist", None) != runtime.provider_allowlist
            or production.orchestrator.excluded_task_ids
            != frozenset(manifest.excluded_task_ids)
        ):
            raise AutonomousGraphRunError(
                "scheduler construction differs from the exact run manifest"
            )
        snapshotter = ProductionCoherentSnapshotter(
            manifest=manifest,
            scheduler=production.orchestrator,
            checkout_root=checkout_root,
            worker_id=production.scheduler_id,
        )
        pump = (
            _SyntheticEvidencePump(
                manifest=manifest,
                source=source,
                checkout_root=checkout_root,
                repository=repository,
            )
            if runtime.synthetic_evidence_enabled
            else None
        )

        controller = AutonomousGraphController(
            manifest=manifest,
            scheduler=production.orchestrator,
            scheduler_lock=production.lock,
            snapshotter=snapshotter,
            progress_store=JsonProgressStore(paths.progress),
            receipt_store=receipts,
            synthetic_evidence_pump=pump,
            synthetic_excluded_task_ids=(PRESERVED_TASK_ID,),
            fallback_seconds=runtime.fallback_seconds,
        )
        result = controller.run()
        _write_result(
            {
                "status": result.evaluation.classification,
                "cycle_status": result.cycle_status,
                "run_id": manifest.run_id,
                "reasons": list(result.evaluation.reasons),
                "receipt": result.receipt.to_dict() if result.receipt else None,
            }
        )
        if result.receipt is not None:
            return EXIT_COMPLETE
        if result.scheduler_fatal:
            return EXIT_SCHEDULER_FATAL
        if result.evaluation.classification == "deadlock":
            return EXIT_DEADLOCK
        return EXIT_BLOCKED
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "adapter_failure",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:2000],
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_ADAPTER_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
