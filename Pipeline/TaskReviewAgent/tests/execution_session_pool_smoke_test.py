#!/usr/bin/env python3
"""Deterministic production-owner tests for ExecutionCrew session pooling.

Classification: pure/component and host-command integration tests. They use a
throwaway Git checkout, external manifest, pool state, and crew artifacts; no
provider, Docker daemon, GitHub Issue, Unity project, or tracked file is touched.
Every assertion is a regression-only orchestration invariant.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.provider_sessions import ProviderSessionConfirmation  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    CrewBlocked,
    checkout_manifest_identity,
    load_role_session_lease_bundle,
)
from Pipeline.ExecutionCrew.session_pool import (  # noqa: E402
    CREW_SESSION_ROLES,
    DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
    ROLE_EVIDENCE_FIELDS,
    ROLE_EVIDENCE_SCHEMA_VERSION,
    AssignmentLease,
    DurableAssignmentResult,
    pooled_assignment_evidence,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge  # noqa: E402
from Pipeline.TaskReviewAgent.real_checkout import RealTaskCheckoutManager  # noqa: E402
from Pipeline.TaskReviewAgent.execution_session_pool import (  # noqa: E402
    ExecutionCrewSessionPoolError,
    ExecutionCrewSessionPoolOwner,
    ExecutionCrewSessionPoolPersistenceError,
    POOL_CAPACITY,
)


TASK_ID = "NSC-900"
MODEL = "claude-pool-smoke"
WORKER_SLOT_ID = "pool-owner-worker"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=str(cwd), capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8").strip()


def fixture(root: Path) -> tuple[Path, Path, str, dict]:
    checkout = root / TASK_ID
    checkout.mkdir(parents=True)
    branch = "nsc-900-session-pool-fixture"
    run("git", "init", "-b", branch, cwd=checkout)
    run("git", "config", "user.name", "Pool Smoke", cwd=checkout)
    run("git", "config", "user.email", "pool-smoke@example.invalid", cwd=checkout)
    (checkout / "tracked.txt").write_text("fixture\n", encoding="utf-8", newline="\n")
    run("git", "add", "tracked.txt", cwd=checkout)
    run("git", "commit", "-m", "fixture", cwd=checkout)
    repository = "https://github.com/cathode26/NoSafeCircle.git"
    run("git", "remote", "add", "origin", repository, cwd=checkout)
    head = run("git", "rev-parse", "HEAD", cwd=checkout)
    observation = {
        "task": {
            "task_id": TASK_ID,
            "title": "Session pool fixture",
            "contract_path": f"Tasks/{TASK_ID}.yaml",
            "contract_revision": 1,
            "task_contract_sha256": "a" * 64,
        },
        "environment": {
            "source_head": head,
            "source_tree": run("git", "rev-parse", "HEAD^{tree}", cwd=checkout),
        },
    }
    manager = RealTaskCheckoutManager(
        source_root=checkout,
        task_id=TASK_ID,
        checkout_root=root,
        worker_id=WORKER_SLOT_ID,
        allow_local_remote_for_tests=True,
    )
    # Exercise the canonical producer rather than duplicating its JSON shape.
    manager._write_manifest(observation, repository)
    manifest = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    require(manifest["branch"] == branch, "real manifest branch differs from checkout")
    return checkout, manager.manifest_path, head, manifest


def crew_result(
    owner: ExecutionCrewSessionPoolOwner,
    assignment: dict,
    *,
    invoked: tuple[str, ...] = CREW_SESSION_ROLES,
    failed_role: str | None = None,
) -> Path:
    run_id = assignment["run_id"]
    run_dir = owner.output_root / run_id
    (run_dir / "role_results").mkdir(parents=True)
    pooled = {}
    durable = {}
    for role in CREW_SESSION_ROLES:
        lease = AssignmentLease.from_dict(assignment["leases"][role])
        if role not in invoked:
            pooled[role] = {
                **lease.to_dict(),
                "invoked": False,
                "durable_assignment_result": None,
            }
            continue
        failed = role == failed_role
        confirmation = ProviderSessionConfirmation(
            "claude-code", role, lease.mode, lease.session_id
        )
        relative = f"role_results/{role}_1.json"
        binding = pooled_assignment_evidence(
            lease=lease,
            confirmed=confirmation,
            crew_run_id=run_id,
            artifact=relative,
            status="failed" if failed else "completed",
            assignment_outcome="output_failure" if failed else "completed",
            semantic_validation="accepted",
            changed_path_validation="accepted",
        )
        require(tuple(binding) == ROLE_EVIDENCE_FIELDS, "binding schema drifted")
        record = {
            "role": role,
            "agent_status": "failed" if failed else "succeeded",
            "scope_check_reasons": ["fixture failure"] if failed else [],
            "deterministic_changed_path_validation": "accepted",
            "semantic_validation": "accepted",
            "pooled_assignment_evidence": binding,
        }
        payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (run_dir / relative).write_bytes(payload)
        value = DurableAssignmentResult(
            schema_version=DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
            pool_schema_version=lease.pool_schema_version,
            protocol_version=lease.protocol_version,
            lease_id=lease.lease_id,
            record_id=lease.record_id,
            crew_run_id=run_id,
            task_id=lease.task_id,
            worker_run_id=lease.worker_run_id,
            worker_slot_id=lease.worker_slot_id,
            session_class=lease.session_class,
            role=lease.role,
            capability_class=lease.capability_class,
            provider_identifier=lease.provider_identifier,
            model=lease.model,
            reasoning_effort=lease.reasoning_effort,
            repository_identity=lease.repository_identity,
            source_commit=lease.source_commit,
            checkout_identity=lease.checkout_identity,
            status="failed" if failed else "completed",
            assignment_outcome="output_failure" if failed else "completed",
            semantic_validation="accepted",
            changed_path_validation="accepted",
            role_result_artifact=relative,
            role_result_sha256=hashlib.sha256(payload).hexdigest(),
            known_context_window_percent=None,
            latency_sample=None,
            confirmed_session=confirmation,
        )
        durable[role] = value.to_dict()
        pooled[role] = {
            **lease.to_dict(),
            "invoked": True,
            "durable_assignment_result": value.to_dict(),
        }
    result = {
        "run_id": run_id,
        "task_id": TASK_ID,
        "source_head": next(iter(assignment["leases"].values()))["source_commit"],
        "provider": "claude",
        "execution_model": MODEL,
        "execution_reasoning_effort": None,
        "crew_profile": "full",
        "validation_profile": "full_relevant",
        "task_contract_identity": {
            "path": f"Tasks/{TASK_ID}.yaml",
            "revision": 1,
            "sha256": "a" * 64,
        },
        "pooled_role_leases": pooled,
        "durable_assignment_results": durable,
    }
    path = run_dir / "crew_result.json"
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def prepared(owner: ExecutionCrewSessionPoolOwner, head: str, suffix: str) -> dict:
    return owner.prepare(
        run_id=f"nsc-900-{suffix}",
        task_id=TASK_ID,
        worker_slot_id=WORKER_SLOT_ID,
        source_commit=head,
        task_contract_sha256="a" * 64,
        model=MODEL,
    )


def state(owner: ExecutionCrewSessionPoolOwner) -> dict:
    return json.loads(owner.state_path.read_text(encoding="utf-8"))


def test_exact_manifest_and_transport_bundle() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-manifest-") as text:
        checkout, manifest_path, head, manifest = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        assignment = prepared(owner, head, "manifest")
        docker_identity = checkout_manifest_identity(
            manifest_path,
            task_id=TASK_ID,
            repository_identity=owner.repository_identity,
            source_branch=manifest["branch"],
            source_commit=head,
            worker_slot_id=WORKER_SLOT_ID,
            task_contract_sha256="a" * 64,
        )
        require(docker_identity == assignment["checkout_identity"], "host/container identity differs")
        leases = load_role_session_lease_bundle(
            Path(assignment["lease_bundle_path"]), run_id=assignment["run_id"]
        )
        require(set(leases) == set(CREW_SESSION_ROLES), "bundle omitted a role")
        require(all(item.worker_run_id == assignment["run_id"] for item in leases.values()), "run not bound")
        try:
            load_role_session_lease_bundle(
                Path(assignment["lease_bundle_path"]), run_id="nsc-900-another-run"
            )
        except CrewBlocked:
            pass
        else:
            raise AssertionError("lease bundle was accepted for another run")
        tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
        tampered["worker_id"] = "another-worker"
        tampered_body = {
            key: value for key, value in tampered.items() if key != "manifest_sha256"
        }
        tampered["manifest_sha256"] = semantic_sha256(tampered_body)
        manifest_path.write_text(json.dumps(tampered), encoding="utf-8")
        try:
            owner.checkout_manifest_identity(
                task_id=TASK_ID,
                worker_slot_id=WORKER_SLOT_ID,
                source_commit=head,
            )
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("cross-worker manifest was accepted by the host owner")
        try:
            checkout_manifest_identity(
                manifest_path,
                task_id=TASK_ID,
                repository_identity=owner.repository_identity,
                source_branch=manifest["branch"],
                source_commit=head,
                worker_slot_id=WORKER_SLOT_ID,
                task_contract_sha256="a" * 64,
            )
        except CrewBlocked:
            pass
        else:
            raise AssertionError("cross-worker manifest was accepted in the container")


def test_success_reuse_unused_cancel_and_exact_once_replay() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-reuse-") as text:
        checkout, _, head, _ = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        first = prepared(owner, head, "first")
        first_result = crew_result(owner, first)
        require(owner.settle(run_id=first["run_id"], result_path=first_result) == "settled", "not settled")
        current = state(owner)
        idle = [x for x in current["pool"]["sessions"] if x["state"] == "idle"]
        require(len(idle) == 4, "four roles not idle")
        require(
            all(
                item["lifecycle"]["known_context_window_percent"] is None
                and item["lifecycle"]["latency_comparison_key"] is None
                for item in idle
            ),
            "unknown context or latency telemetry was synthesized",
        )
        second = prepared(owner, head, "second")
        require(all(value["mode"] == "resume" for value in second["leases"].values()), "warm roles not resumed")
        counts_before = {x["record_id"]: x["completed_assignment_count"] for x in state(owner)["pool"]["sessions"]}
        second_result = crew_result(owner, second, invoked=())
        owner.settle(run_id=second["run_id"], result_path=second_result)
        after = state(owner)
        counts_after = {x["record_id"]: x["completed_assignment_count"] for x in after["pool"]["sessions"]}
        require(counts_after == counts_before, "unused roles consumed assignment budget")
        generation = after["generation"]
        require(owner.settle(run_id=second["run_id"], result_path=second_result) == "already_settled", "replay not idempotent")
        require(state(owner)["generation"] == generation, "settlement replay wrote state")
        require(any(x["event"] == "assignment_cancelled" for x in after["lifecycle_telemetry"]), "cancel telemetry missing")


def test_first_failure_probation_is_offered_once() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-probation-") as text:
        checkout, _, head, _ = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        first = prepared(owner, head, "failure")
        owner.settle(
            run_id=first["run_id"],
            result_path=crew_result(owner, first, failed_role="implementer"),
        )
        failed_record = first["leases"]["implementer"]["record_id"]
        require(
            next(x for x in state(owner)["pool"]["sessions"] if x["record_id"] == failed_record)["state"] == "probation",
            "first provider/output failure was not held on probation",
        )
        retry = prepared(owner, head, "probation-retry")
        require(retry["leases"]["implementer"]["record_id"] == failed_record, "probation record not retried")
        require(retry["leases"]["implementer"]["mode"] == "resume", "probation retry did not resume")


def test_ten_concurrent_runs_reserve_exactly_forty_leases() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-concurrency-") as text:
        checkout, _, head, _ = fixture(Path(text))

        def reserve(index: int) -> dict:
            return prepared(
                ExecutionCrewSessionPoolOwner(checkout=checkout), head, f"parallel-{index}"
            )

        with ThreadPoolExecutor(max_workers=10) as workers:
            assignments = list(workers.map(reserve, range(10)))
        require(len({item["run_id"] for item in assignments}) == 10, "run identities collided")
        current = state(ExecutionCrewSessionPoolOwner(checkout=checkout))
        active = [x for x in current["pool"]["sessions"] if x["state"] == "active"]
        require(len(active) == POOL_CAPACITY == 40, f"wrong active capacity: {len(active)}")
        require(len({x["active_lease"]["lease_id"] for x in active}) == 40, "lease identity collided")


def test_restart_recovers_exact_terminal_result_and_never_steals_unknown() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-restart-") as text:
        checkout, _, head, _ = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        completed = prepared(owner, head, "crash-after-result")
        crew_result(owner, completed)
        restarted = ExecutionCrewSessionPoolOwner(checkout=checkout)
        recovered = prepared(restarted, head, "after-restart")
        require(all(x["mode"] == "resume" for x in recovered["leases"].values()), "terminal evidence was not recovered")
        restarted.settle(
            run_id=recovered["run_id"],
            result_path=crew_result(restarted, recovered, invoked=()),
        )
        unknown = prepared(restarted, head, "unknown-process")
        next_run = prepared(restarted, head, "beside-unknown")
        current = state(restarted)
        require(current["assignments"][completed["run_id"]]["status"] == "settled", "terminal run not settled")
        require(current["assignments"][unknown["run_id"]]["status"] == "active", "unknown process was stolen")
        unknown_records = {x["record_id"] for x in unknown["leases"].values()}
        next_records = {x["record_id"] for x in next_run["leases"].values()}
        require(unknown_records.isdisjoint(next_records), "unknown active conversation was reused")


def test_tampered_result_quarantines_and_terminal_missing_quarantines() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-tamper-") as text:
        checkout, _, head, _ = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        assignment = prepared(owner, head, "tamper")
        path = crew_result(owner, assignment, invoked=())
        value = json.loads(path.read_text(encoding="utf-8"))
        value["pooled_role_leases"]["implementer"]["task_id"] = "NSC-901"
        path.write_text(json.dumps(value), encoding="utf-8")
        try:
            owner.settle(run_id=assignment["run_id"], result_path=path)
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("cross-task lease echo was accepted")
        current = state(owner)
        require(current["assignments"][assignment["run_id"]]["status"] == "failed", "tamper not fenced")
        require(all(x["state"] in {"quarantined", "retired"} for x in current["pool"]["sessions"]), "tampered sessions remained reusable")
        failed_snapshot = current
        require(
            owner.settle(run_id=assignment["run_id"], result_path=path) == "already_failed",
            "exact failed-result replay was not a no-op",
        )
        require(state(owner) == failed_snapshot, "failed-result replay mutated durable state")
        changed = json.loads(path.read_text(encoding="utf-8"))
        changed["rejection_reasons"] = ["different terminal bytes"]
        path.write_text(json.dumps(changed), encoding="utf-8")
        try:
            owner.settle(run_id=assignment["run_id"], result_path=path)
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("different failed-result replay was accepted")
        require(state(owner) == failed_snapshot, "different failed replay mutated durable state")

        missing = prepared(owner, head, "missing")
        owner.terminal_without_result(run_id=missing["run_id"], reason="exit 2")
        current = state(owner)
        missing_records = {x["record_id"] for x in missing["leases"].values()}
        require(all(x["state"] in {"quarantined", "retired"} for x in current["pool"]["sessions"] if x["record_id"] in missing_records), "missing evidence remained reusable")
        missing_snapshot = current
        late_missing_result = crew_result(owner, missing, invoked=())
        try:
            owner.settle(run_id=missing["run_id"], result_path=late_missing_result)
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("missing-result terminal accepted a later result")
        require(state(owner) == missing_snapshot, "missing-result replay mutated durable state")

        cancelled = prepared(owner, head, "cancelled")
        owner.cancel_unstarted(run_id=cancelled["run_id"])
        cancelled_snapshot = state(owner)
        late_cancelled_result = crew_result(owner, cancelled, invoked=())
        try:
            owner.settle(run_id=cancelled["run_id"], result_path=late_cancelled_result)
        except ExecutionCrewSessionPoolError:
            pass
        else:
            raise AssertionError("cancelled assignment accepted a later result")
        require(state(owner) == cancelled_snapshot, "cancelled replay mutated durable state")


def test_bridge_supplies_exact_four_lease_transport_and_manual_path_is_ephemeral() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-bridge-") as text:
        checkout, _, head, _ = fixture(Path(text))
        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        assignment = prepared(owner, head, "bridge")
        accepted = type("Accepted", (), {
            "task_id": TASK_ID,
            "plan": type("Plan", (), {
                "existing_implementation_paths": ("Assets/A.cs",),
                "new_implementation_paths": (),
                "existing_test_paths": ("Assets/ATests.cs",),
                "new_test_paths": (),
            })(),
        })()
        scope = type("Scope", (), {"task_id": TASK_ID, "accepted": None})()
        bridge = ExecutionCrewBridge(
            checkout=checkout,
            scope=scope,
            execution_model=MODEL,
            command_runner=lambda *_: None,
        )
        pooled = bridge._command(
            accepted,
            provider="claude",
            retry_run_id=None,
            feedback_file=None,
            pool_assignment=assignment,
        )
        require(pooled[pooled.index("--run-id") + 1] == assignment["run_id"], "run id not transported")
        require(pooled.count("--volume") == 2, "manifest and lease mounts are not exact")
        require("--role-session-leases" in pooled, "lease bundle not transported")
        manual = bridge._command(
            accepted,
            provider="claude",
            retry_run_id=None,
            feedback_file=None,
        )
        require("--run-id" not in manual and "--role-session-leases" not in manual, "manual path stopped being ephemeral")


def test_full_manual_bridge_never_prepares_scheduler_owned_pool() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-manual-bridge-") as text:
        checkout, _, head, _ = fixture(Path(text))
        accepted = SimpleNamespace(
            task_id=TASK_ID,
            plan_id="plan-manual-bridge",
            lease_id="lease-manual-bridge",
            source_head=head,
            task_contract_sha256="a" * 64,
            plan=SimpleNamespace(
                existing_implementation_paths=("Assets/A.cs",),
                new_implementation_paths=(),
                existing_test_paths=("Assets/ATests.cs",),
                new_test_paths=(),
            ),
        )

        class Scope:
            task_id = TASK_ID

            def __init__(self) -> None:
                self.accepted = accepted

            def require(self, plan_id: str):
                require(plan_id == accepted.plan_id, "manual bridge changed plan identity")
                return accepted

        class SpyOwner:
            prepare_calls = 0

            def prepare(self, **_values):
                self.prepare_calls += 1
                raise AssertionError("manual bridge prepared a scheduler-owned pool")

        class RunnerReached(RuntimeError):
            pass

        commands: list[tuple[str, ...]] = []

        def manual_runner(args, _cwd, _timeout):
            commands.append(tuple(args))
            raise RunnerReached()

        for provider, model in (
            ("claude", None),
            ("claude", "manual-claude-model"),
            ("codex", "manual-codex-model"),
        ):
            owner = SpyOwner()
            # Construct exactly like a manual/default caller (no injected
            # runner), then replace only the subprocess seam before run so no
            # Docker daemon is touched by this deterministic regression.
            bridge = ExecutionCrewBridge(
                checkout=checkout,
                scope=Scope(),
                execution_model=model,
                worker_slot_id=WORKER_SLOT_ID,
                session_pool_owner=owner,
            )
            bridge.command_runner = manual_runner
            try:
                bridge.run(plan_id=accepted.plan_id, provider=provider)
            except RunnerReached:
                pass
            else:
                raise AssertionError("manual bridge did not reach the ephemeral runner")
            require(owner.prepare_calls == 0, f"manual {provider}/{model} prepared the pool")
            command = commands[-1]
            require(
                "--role-session-leases" not in command
                and "--checkout-identity-manifest" not in command
                and "--run-id" not in command,
                f"manual {provider}/{model} received pooled transport",
            )


def test_bridge_run_owns_full_pooled_call_and_degrades_only_the_optimization() -> None:
    with tempfile.TemporaryDirectory(prefix="execution-pool-full-call-") as text:
        checkout, _, head, _ = fixture(Path(text))
        task_hash = "a" * 64
        accepted = SimpleNamespace(
            task_id=TASK_ID,
            plan_id="plan-full-call",
            lease_id="issue-lease-full-call",
            source_head=head,
            task_contract_sha256=task_hash,
            plan=SimpleNamespace(
                existing_implementation_paths=("Assets/A.cs",),
                new_implementation_paths=(),
                existing_test_paths=("Assets/ATests.cs",),
                new_test_paths=(),
            ),
        )

        class Scope:
            task_id = TASK_ID

            def __init__(self, value):
                self.accepted = value

            def require(self, plan_id: str):
                require(plan_id == self.accepted.plan_id, "wrong plan identity")
                return self.accepted

        owner = ExecutionCrewSessionPoolOwner(checkout=checkout)
        observed_commands: list[tuple[str, ...]] = []

        def fake_runner(args, cwd, timeout):
            _ = (cwd, timeout)
            observed_commands.append(tuple(args))
            run_id = args[args.index("--run-id") + 1]
            lease_mount = args[args.index("--volume") + 3]
            suffix = ":/nsc-pool/leases.json:ro"
            require(lease_mount.endswith(suffix), f"wrong lease mount: {lease_mount}")
            bundle_path = Path(lease_mount[: -len(suffix)])
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            assignment = {"run_id": run_id, "leases": bundle["leases"]}
            result_path = crew_result(owner, assignment, invoked=())
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result.update(
                {
                    "schema_version": "1.0",
                    "task_contract_identity": {
                        "path": f"Tasks/{TASK_ID}.yaml",
                        "revision": 1,
                        "sha256": task_hash,
                    },
                    "source_tree": "c" * 40,
                    "source_branch": "main",
                    "crew_status": "blocked",
                    "requested_implementation_paths": ["Assets/A.cs"],
                    "requested_test_paths": ["Assets/ATests.cs"],
                    "requested_existing_implementation_paths": ["Assets/A.cs"],
                    "requested_new_implementation_paths": [],
                    "requested_existing_test_paths": ["Assets/ATests.cs"],
                    "requested_new_test_paths": [],
                    "final_actual_changed_paths": [],
                    "candidate_patch_path": None,
                    "candidate_patch_sha256": None,
                    "rejection_reasons": ["fixture stop"],
                }
            )
            payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
            result_path.write_bytes(payload)
            return subprocess.CompletedProcess(args=args, returncode=1, stdout=payload, stderr=b"")

        bridge = ExecutionCrewBridge(
            checkout=checkout,
            scope=Scope(accepted),
            execution_model=MODEL,
            command_runner=fake_runner,
            worker_slot_id=WORKER_SLOT_ID,
            session_pool_owner=owner,
            enable_session_pool=True,
        )
        receipt = bridge.run(plan_id=accepted.plan_id, provider="claude")
        require(receipt.crew_status == "blocked", "full bridge run changed crew status")
        command = observed_commands[0]
        require(command.count("--volume") == 2, "full bridge call omitted read-only identity mounts")
        require("--role-session-leases" in command and "--run-id" in command, "full bridge call was ephemeral")
        require(state(owner)["assignments"][receipt.run_id]["status"] == "settled", "bridge did not settle")

        class DegradedOwner:
            repository_identity = owner.repository_identity

            def prepare(self, **values):
                return owner.prepare(**values)

            @staticmethod
            def settle(**_values):
                raise ExecutionCrewSessionPoolPersistenceError("fixture persistence outage")

        def degraded_runner(args, cwd, timeout):
            completed = fake_runner(args, cwd, timeout)
            result = json.loads(completed.stdout.decode("utf-8"))
            run_id = result["run_id"]
            candidate = owner.output_root / run_id / "candidate.patch"
            candidate.write_bytes(b"fixture candidate\n")
            result["crew_status"] = "review_ready"
            result["candidate_patch_path"] = f"/execution-output/{run_id}/candidate.patch"
            result["candidate_patch_sha256"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
            result["rejection_reasons"] = []
            payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (owner.output_root / run_id / "crew_result.json").write_bytes(payload)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout=payload, stderr=b"")

        degraded_bridge = ExecutionCrewBridge(
            checkout=checkout,
            scope=Scope(accepted),
            execution_model=MODEL,
            command_runner=degraded_runner,
            worker_slot_id=WORKER_SLOT_ID,
            session_pool_owner=DegradedOwner(),
            enable_session_pool=True,
        )
        degraded = degraded_bridge.run(plan_id=accepted.plan_id, provider="claude")
        require(degraded.crew_status == "review_ready", "valid candidate was invalidated")
        evidence = owner.output_root / degraded.run_id / "pool_degraded.json"
        require(evidence.is_file(), "pool persistence failure invalidated candidate without evidence")
        require(json.loads(evidence.read_text(encoding="utf-8"))["sessions_available"] is False, "degraded sessions advertised")


def main() -> int:
    tests = (
        test_exact_manifest_and_transport_bundle,
        test_success_reuse_unused_cancel_and_exact_once_replay,
        test_first_failure_probation_is_offered_once,
        test_ten_concurrent_runs_reserve_exactly_forty_leases,
        test_restart_recovers_exact_terminal_result_and_never_steals_unknown,
        test_tampered_result_quarantines_and_terminal_missing_quarantines,
        test_bridge_supplies_exact_four_lease_transport_and_manual_path_is_ephemeral,
        test_full_manual_bridge_never_prepares_scheduler_owned_pool,
        test_bridge_run_owns_full_pooled_call_and_degrades_only_the_optimization,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"execution_session_pool_smoke_test: PASS ({len(tests)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
