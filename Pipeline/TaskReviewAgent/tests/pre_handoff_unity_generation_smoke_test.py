#!/usr/bin/env python3
"""Regression coverage for DoorPrototype generation before Unity handoff."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.candidate_integration import (  # noqa: E402
    CandidateIntegrationError,
    CandidateIntegrator,
)
from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    ExecutionScopePlan,
    TaskReviewContractError,
    semantic_sha256,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewReceipt  # noqa: E402
from Pipeline.TaskReviewAgent.pipeline_scope import RepositoryScopeAuthority  # noqa: E402
from Pipeline.TaskReviewAgent.pre_handoff_unity_generation import (  # noqa: E402
    DOOR_PROTOTYPE_BUILDER_METHOD,
    discover_unity_executable,
    door_prototype_builder_required,
)
from Pipeline.TaskReviewAgent.production_pipeline import (  # noqa: E402
    ProductionTaskController,
    _completed_integration_resume_candidate,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.Testing.unity_workspace_hygiene import (  # noqa: E402
    HygieneError,
    normalize_preserved_unity_eol,
    snapshot_payload,
)


TASK_ID = "NSC-777"
BRANCH = "nsc-777-pre-handoff-unity"
LEASE_ID = "7" * 64
RUN_ID = "nsc-777-pre-handoff-unity"
BUILDER = "Assets/NoSafeCircle/DoorPrototype/Editor/DoorPrototypeSceneBuilder.cs"
TEST = "Assets/NoSafeCircle/DoorPrototype/Tests/Editor/DoorPrototypeSceneBuilderTests.cs"
SCENE = "Assets/Scenes/DoorPrototype.unity"
TILE_ROOT = "Assets/NoSafeCircle/DoorPrototype/Generated/ArchitecturalTiles"
WALL = f"{TILE_ROOT}/WallTile.asset"
FLOOR = f"{TILE_ROOT}/FloorTile.asset"
BORDER = f"{TILE_ROOT}/ArchitecturalBorderTile.asset"
UNAUTHORIZED = f"{TILE_ROOT}/WizardSprite.asset"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed ({completed.returncode}): {' '.join(args)}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    return completed


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.strip()


def git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def write_bytes(root: Path, relative: str, content: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def taskcontrol_source() -> str:
    return """from __future__ import annotations
import sys
if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    raise SystemExit(0)
raise SystemExit(2)
"""


def candidate_patch() -> bytes:
    return f"""diff --git a/{BUILDER} b/{BUILDER}
--- a/{BUILDER}
+++ b/{BUILDER}
@@ -1 +1 @@
-namespace NoSafeCircle.DoorPrototype.Editor {{ public static class DoorPrototypeSceneBuilder {{ public const int Revision = 1; }} }}
+namespace NoSafeCircle.DoorPrototype.Editor {{ public static class DoorPrototypeSceneBuilder {{ public const int Revision = 2; }} }}
diff --git a/{TEST} b/{TEST}
--- a/{TEST}
+++ b/{TEST}
@@ -1 +1 @@
-namespace NoSafeCircle.DoorPrototype.Tests {{ public sealed class DoorPrototypeSceneBuilderTests {{ public const int Revision = 1; }} }}
+namespace NoSafeCircle.DoorPrototype.Tests {{ public sealed class DoorPrototypeSceneBuilderTests {{ public const int Revision = 2; }} }}
""".encode("utf-8")


class FakeExecution:
    def __init__(self, receipt: SimpleNamespace) -> None:
        self.receipt = receipt

    def require(self, run_id: str) -> SimpleNamespace:
        require(run_id == self.receipt.run_id, "integrator requested the wrong run")
        return self.receipt


class Fixture:
    def __init__(self, root: Path, *, generated_resources: bool = True) -> None:
        self.root = root
        self.remote = root / "remote.git"
        self.seed = root / "seed"
        self.checkout = root / "operator" / TASK_ID
        run("git", "init", "--bare", str(self.remote), cwd=root)
        run("git", "init", "-b", "main", str(self.seed), cwd=root)
        git(self.seed, "config", "user.name", "Pre-Handoff Smoke")
        git(self.seed, "config", "user.email", "pre-handoff@example.invalid")
        git(self.seed, "config", "core.autocrlf", "false")

        resources = [f"repo-file:{BUILDER}", f"repo-file:{TEST}"]
        if generated_resources:
            resources.extend((f"repo-file:{WALL}", f"unity-scene:{SCENE}"))
        self.contract = {
            "schema_version": "2.0",
            "id": TASK_ID,
            "title": "Pre-Handoff DoorPrototype Generation",
            "contract_revision": 1,
            "contract_disposition": "active",
            "kind": "implementation",
            "type": "world-foundation",
            "execution_scope": "single_agent",
            "decomposition_state": "concrete",
            "depends_on": [],
            "exclusive_resources": resources,
            "acceptance_criteria": [],
            "completion_gates": [],
            "downstream_integration_obligations": [],
        }
        write_bytes(
            self.seed,
            BUILDER,
            b"namespace NoSafeCircle.DoorPrototype.Editor { public static class DoorPrototypeSceneBuilder { public const int Revision = 1; } }\n",
        )
        write_bytes(
            self.seed,
            TEST,
            b"namespace NoSafeCircle.DoorPrototype.Tests { public sealed class DoorPrototypeSceneBuilderTests { public const int Revision = 1; } }\n",
        )
        write_bytes(self.seed, SCENE, b"%YAML 1.1\nSceneRevision: 1\n")
        write_bytes(self.seed, WALL, b"%YAML 1.1\nTileRevision: 1\n")
        write_bytes(self.seed, FLOOR, b"%YAML 1.1\nFloorRevision: 1\n")
        write_bytes(self.seed, BORDER, b"%YAML 1.1\nBorderRevision: 1\n")
        write_bytes(
            self.seed,
            "ProjectSettings/ProjectVersion.txt",
            b"m_EditorVersion: 6000.1.12f1\n",
        )
        write_bytes(
            self.seed,
            f"Tasks/{TASK_ID}.yaml",
            (json.dumps(self.contract, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        write_bytes(
            self.seed,
            "Pipeline/TaskGraph/taskcontrol.py",
            taskcontrol_source().encode("utf-8"),
        )
        hygiene_target = self.seed / "Pipeline/Testing/unity_workspace_hygiene.py"
        hygiene_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            ROOT / "Pipeline/Testing/unity_workspace_hygiene.py",
            hygiene_target,
        )
        write_bytes(self.seed, ".gitattributes", b"* -text\n")
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-m", "Create pre-handoff generation fixture")
        git(self.seed, "remote", "add", "origin", str(self.remote))
        git(self.seed, "push", "-u", "origin", "main")
        run(
            "git",
            "--git-dir",
            str(self.remote),
            "symbolic-ref",
            "HEAD",
            "refs/heads/main",
            cwd=root,
        )
        self.checkout.parent.mkdir(parents=True)
        run("git", "clone", str(self.remote), str(self.checkout), cwd=root)
        git(self.checkout, "config", "core.autocrlf", "false")
        git(self.checkout, "switch", "-c", BRANCH)
        self.source_head = git(self.checkout, "rev-parse", "HEAD")
        contract_blob = git_bytes(self.checkout, "show", f"HEAD:Tasks/{TASK_ID}.yaml")
        self.task = {
            **self.contract,
            "task_id": TASK_ID,
            "contract_path": f"Tasks/{TASK_ID}.yaml",
            "task_contract_sha256": hashlib.sha256(contract_blob).hexdigest(),
        }
        self.scope = RepositoryScopeAuthority(
            checkout=self.checkout,
            task=self.task,
            lease_id=LEASE_ID,
            expected_branch=BRANCH,
        )
        accepted = self.scope.validate(
            ExecutionScopePlan((BUILDER,), (), (TEST,), ())
        )
        require(accepted.accepted and accepted.plan_id is not None, str(accepted))
        self.plan_id = str(accepted.plan_id)
        self.patch_path = root / "candidate.patch"
        self.patch_path.write_bytes(candidate_patch())
        self.fake_receipt = SimpleNamespace(
            crew_status="review_ready",
            candidate_path=str(self.patch_path),
            candidate_sha256=hashlib.sha256(self.patch_path.read_bytes()).hexdigest(),
            final_actual_changed_paths=tuple(sorted((BUILDER, TEST), key=str.casefold)),
            source_head=self.source_head,
            task_contract_sha256=self.task["task_contract_sha256"],
            task_id=TASK_ID,
            lease_id=LEASE_ID,
            plan_id=self.plan_id,
            run_id=RUN_ID,
            provider="claude",
        )
        self.execution = FakeExecution(self.fake_receipt)
        self.unity = root / "Unity.exe"
        self.unity.write_bytes(b"synthetic executable")
        self.output_root = root / "unity-output"

    def integrator(self, runner, *, explicit_unity: bool = True, environment=None) -> CandidateIntegrator:
        return CandidateIntegrator(
            checkout=self.checkout,
            branch=BRANCH,
            task_title=self.task["title"],
            scope=self.scope,
            execution=self.execution,
            unity_executable=self.unity if explicit_unity else None,
            unity_output_root=self.output_root,
            unity_command_runner=runner,
            unity_environment=environment,
        )

    def persist_execution_receipt(self) -> None:
        result_path = self.root / "crew_result.json"
        result_path.write_bytes(b"{\"crew_status\":\"review_ready\"}\n")
        receipt = ExecutionCrewReceipt(
            run_id=RUN_ID,
            task_id=TASK_ID,
            lease_id=LEASE_ID,
            plan_id=self.plan_id,
            provider="claude",
            execution_model=None,
            execution_reasoning_effort=None,
            source_head=self.source_head,
            task_contract_sha256=self.task["task_contract_sha256"],
            crew_status="review_ready",
            result_path=str(result_path),
            result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
            candidate_path=str(self.patch_path),
            candidate_sha256=self.fake_receipt.candidate_sha256,
            final_actual_changed_paths=self.fake_receipt.final_actual_changed_paths,
            returncode=0,
            rejection_reasons=(),
        )
        payload = receipt.to_dict()
        payload["receipt_sha256"] = semantic_sha256(payload)
        state_path = self.checkout.parent / ".task-review-agent" / f"{TASK_ID}.execution.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def standard_builder_runner(
    fixture: Fixture,
    events: list[str],
    *,
    unauthorized: bool = False,
    mutate_candidate: bool = False,
):
    def runner(command, cwd: Path, timeout: float):
        _ = timeout
        events.append("builder")
        require(Path(cwd).resolve() == fixture.checkout.resolve(), "builder used wrong checkout")
        require(command[0] == str(fixture.unity.resolve()), "explicit Unity executable was lost")
        require(
            command[command.index("-executeMethod") + 1] == DOOR_PROTOTYPE_BUILDER_METHOD,
            "builder executeMethod was wrong",
        )
        require(
            Path(command[command.index("-projectPath") + 1]).resolve()
            == fixture.checkout.resolve(),
            "builder projectPath was not canonical task checkout",
        )
        require(
            b"Revision = 2" in (fixture.checkout / BUILDER).read_bytes(),
            "builder ran before candidate application",
        )
        require(
            git(fixture.checkout, "rev-parse", "HEAD") == fixture.source_head,
            "candidate was committed before builder",
        )
        log_path = Path(command[command.index("-logFile") + 1])
        snapshot_path = log_path.parent / "workspace-snapshot.json"
        require(snapshot_path.is_file(), "hygiene snapshot did not precede builder")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        require(snapshot["task_id"] == TASK_ID, "snapshot omitted --task-id authority")
        require(BUILDER in snapshot["baseline_status"], "candidate source was not protected baseline")
        write_bytes(fixture.checkout, SCENE, b"%YAML 1.1\r\nSceneRevision: 2\r\n")
        write_bytes(fixture.checkout, WALL, b"%YAML 1.1\r\nTileRevision: 2\r\n")
        write_bytes(fixture.checkout, FLOOR, b"%YAML 1.1\r\nFloorRevision: 999\r\n")
        write_bytes(fixture.checkout, BORDER, b"%YAML 1.1\r\nBorderRevision: 999\r\n")
        if unauthorized:
            write_bytes(fixture.checkout, UNAUTHORIZED, b"%YAML 1.1\nWizard: 1\n")
        if mutate_candidate:
            write_bytes(
                fixture.checkout,
                BUILDER,
                b"namespace NoSafeCircle.DoorPrototype.Editor { public static class DoorPrototypeSceneBuilder { public const int Revision = 1; } }\n",
            )
        log_path.write_text("synthetic builder log\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    return runner


def test_builder_order_hygiene_eol_provenance_and_restart() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-success-") as temporary:
        fixture = Fixture(Path(temporary))
        events: list[str] = []
        integrator = fixture.integrator(standard_builder_runner(fixture, events))
        receipt = integrator.integrate(RUN_ID)
        require(events == ["builder"], "builder-required task did not run builder exactly once")
        require((fixture.checkout / FLOOR).read_bytes() == b"%YAML 1.1\nFloorRevision: 1\n", "FloorTile churn survived")
        require((fixture.checkout / BORDER).read_bytes() == b"%YAML 1.1\nBorderRevision: 1\n", "border churn survived")
        require((fixture.checkout / SCENE).read_bytes() == b"%YAML 1.1\nSceneRevision: 2\n", "scene semantics/EOL wrong")
        require((fixture.checkout / WALL).read_bytes() == b"%YAML 1.1\nTileRevision: 2\n", "wall semantics/EOL wrong")
        expected_candidate = tuple(sorted((BUILDER, TEST), key=str.casefold))
        expected_generated = tuple(sorted((SCENE, WALL), key=str.casefold))
        expected_final = tuple(sorted((*expected_candidate, *expected_generated), key=str.casefold))
        require(receipt.candidate_changed_paths == expected_candidate, "candidate provenance changed")
        require(receipt.generated_changed_paths == expected_generated, "generated provenance changed")
        require(receipt.changed_paths == expected_final, "final path union changed")
        receipt_payload = receipt.to_dict()
        require(receipt_payload["candidate_changed_paths"] == list(expected_candidate), "receipt candidate paths missing")
        require(receipt_payload["generated_changed_paths"] == list(expected_generated), "receipt generated paths missing")
        require(receipt_payload["changed_paths"] == list(expected_final), "receipt final paths missing")
        require(receipt.unity_builder_ran, "receipt omitted builder completion")
        require(git(fixture.checkout, "status", "--porcelain=v1", "--untracked-files=all") == "", "handoff commit is dirty")
        require(
            tuple(sorted(git(fixture.checkout, "diff", "--name-only", f"{fixture.source_head}..HEAD", "--").splitlines(), key=str.casefold))
            == expected_final,
            "commit paths do not equal candidate plus authorized generated output",
        )

        fixture.persist_execution_receipt()
        integrator.state_path.unlink()

        def must_not_run(*_args):
            raise AssertionError("restart reran Unity builder")

        class ResumeWorkflow:
            task_id = TASK_ID
            worker_id = "pre-handoff-resume-worker"

            def observe_goal_state(self):
                return {
                    "task": fixture.task,
                    "checkout": {
                        "status": "conflict",
                        "clean": True,
                        "branch": BRANCH,
                        "expected_branch": BRANCH,
                        "path": str(fixture.checkout),
                        "reasons": [
                            f"checkout HEAD {receipt.commit!r} does not match workflow head {fixture.source_head!r}",
                            "fresh checkout tree does not match observed source tree",
                        ],
                    },
                    "coordination": {
                        "status": "claimed_by_worker",
                        "workflow_state": {
                            "state": "agent_working",
                            "worker_id": self.worker_id,
                            "lease_id": LEASE_ID,
                        },
                    },
                }

            def publish_human_handoff(self, **values):
                require(values["head_commit"] == receipt.commit, "restart handoff changed commit")
                return {"head_commit": values["head_commit"]}

        resumed_controller = ProductionTaskController(
            workflow=ResumeWorkflow(),
            execution_provider="claude",
            unity_executable=str(fixture.unity),
            unity_output_root=fixture.output_root,
            unity_command_runner=must_not_run,
        )
        resumed_observation = resumed_controller.observe()
        require(resumed_observation["completed_integration_resume"], "launcher did not recognize completed integration")
        require(
            resumed_observation["production_pipeline"]["next_action"]
            == "integrate_commit_push_and_handoff",
            "launcher did not route restart to idempotent handoff",
        )
        resumed_result = resumed_controller.integrate_commit_push_and_handoff(
            run_id=RUN_ID,
            implementation_summary="Resume the exact generated commit.",
            human_steps=["Open the committed DoorPrototype scene and enter Play Mode."],
            expected_result="The committed generated wall state is visible.",
        )
        resumed = resumed_result["integration"]
        require(resumed["commit"] == receipt.commit, "restart created a second integration commit")
        require(tuple(resumed["generated_changed_paths"]) == expected_generated, "restart lost generated provenance")


def test_unrelated_task_does_not_run_builder() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-unrelated-") as temporary:
        fixture = Fixture(Path(temporary), generated_resources=False)

        def must_not_run(*_args):
            raise AssertionError("unrelated task invoked Unity")

        receipt = fixture.integrator(must_not_run).integrate(RUN_ID)
        require(not receipt.unity_builder_required and not receipt.unity_builder_ran, "unrelated receipt claimed builder")
        require(receipt.generated_changed_paths == (), "unrelated task gained generated paths")


def test_trigger_uses_accepted_builder_scope_plus_declared_output() -> None:
    task = {"exclusive_resources": [f"repo-file:{WALL}"]}
    require(
        door_prototype_builder_required(
            task=task,
            candidate_changed_paths=(TEST,),
            accepted_changed_paths=(BUILDER, TEST),
        ),
        "accepted builder scope plus generated resource did not trigger",
    )
    require(
        not door_prototype_builder_required(
            task={"exclusive_resources": [f"repo-file:{BUILDER}"]},
            candidate_changed_paths=(BUILDER,),
            accepted_changed_paths=(BUILDER,),
        ),
        "builder-only task triggered without generated output authority",
    )


def test_builder_failure_prevents_commit_push_and_handoff() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-failure-") as temporary:
        fixture = Fixture(Path(temporary))
        published: list[dict] = []

        def failing_runner(command, cwd, timeout):
            _ = (cwd, timeout)
            return subprocess.CompletedProcess(command, 19, b"", b"synthetic Unity failure")

        integrator = fixture.integrator(failing_runner)

        class Workflow:
            task_id = TASK_ID

            def publish_human_handoff(self, **values):
                published.append(values)
                return values

        controller = ProductionTaskController(workflow=Workflow(), execution_provider="claude")
        controller.integrator = integrator
        try:
            controller.integrate_commit_push_and_handoff(
                run_id=RUN_ID,
                implementation_summary="Synthetic builder failure.",
                human_steps=["Enter Play Mode."],
                expected_result="Synthetic result.",
            )
        except CandidateIntegrationError as exc:
            require("before commit/push/handoff" in str(exc), "builder failure boundary was unclear")
        else:
            raise AssertionError("builder failure was accepted")
        require(git(fixture.checkout, "rev-parse", "HEAD") == fixture.source_head, "builder failure created commit")
        require(not published, "builder failure published human handoff")
        remote_branch = run(
            "git",
            "--git-dir",
            str(fixture.remote),
            "rev-parse",
            f"refs/heads/{BRANCH}",
            cwd=fixture.root,
            check=False,
        )
        require(remote_branch.returncode != 0, "builder failure pushed task branch")


def test_unexpected_generated_path_blocks() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-unauthorized-") as temporary:
        fixture = Fixture(Path(temporary))
        integrator = fixture.integrator(
            standard_builder_runner(fixture, [], unauthorized=True)
        )
        try:
            integrator.integrate(RUN_ID)
        except CandidateIntegrationError as exc:
            require("without task resource or accepted-scope authority" in str(exc), str(exc))
            require(UNAUTHORIZED in str(exc), "unauthorized path was not identified")
        else:
            raise AssertionError("unauthorized generated path was committed")
        require(git(fixture.checkout, "rev-parse", "HEAD") == fixture.source_head, "unauthorized output created commit")


def test_builder_cannot_erase_protected_candidate_baseline() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-baseline-") as temporary:
        fixture = Fixture(Path(temporary))
        integrator = fixture.integrator(
            standard_builder_runner(fixture, [], mutate_candidate=True)
        )
        try:
            integrator.integrate(RUN_ID)
        except CandidateIntegrationError as exc:
            require("workspace inspection" in str(exc), str(exc))
        else:
            raise AssertionError("builder erased a candidate path without blocking")
        require(git(fixture.checkout, "rev-parse", "HEAD") == fixture.source_head, "baseline mutation created commit")


def test_handoff_uses_clean_post_generation_commit_without_rebuild_instruction() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-pre-handoff-handoff-") as temporary:
        fixture = Fixture(Path(temporary))
        integrator = fixture.integrator(standard_builder_runner(fixture, []))
        receipt = integrator.integrate(RUN_ID)
        published: list[dict] = []

        class Workflow:
            task_id = TASK_ID

            def publish_human_handoff(self, **values):
                require(values["head_commit"] == receipt.commit, "handoff used pre-generation commit")
                require(git(fixture.checkout, "status", "--porcelain=v1", "--untracked-files=all") == "", "handoff used dirty tree")
                published.append(values)
                return {"head_commit": values["head_commit"]}

        controller = ProductionTaskController(workflow=Workflow(), execution_provider="claude")
        controller.integrator = integrator
        result = controller.integrate_commit_push_and_handoff(
            run_id=RUN_ID,
            implementation_summary="Updated the DoorPrototype wall tile convention.",
            human_steps=["Open DoorPrototype.unity and enter Play Mode.", "Inspect the long walls."],
            expected_result="The generated walls are continuous in Play Mode.",
        )
        require(result["handoff"]["head_commit"] == receipt.commit, "handoff result commit changed")
        require(len(published) == 1, "handoff did not publish exactly once")
        summary = published[0]["implementation_summary"]
        require("already contains the generated DoorPrototype" in summary, "handoff omitted materialized output notice")
        require("Rebuilding is not required" in summary, "handoff told Vincent to materialize output")


def test_explicit_and_default_unity_discovery() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unity-discovery-") as temporary:
        root = Path(temporary)
        write_bytes(root, "ProjectSettings/ProjectVersion.txt", b"m_EditorVersion: 6000.1.12f1\n")
        explicit = root / "explicit" / "Unity.exe"
        explicit.parent.mkdir(parents=True)
        explicit.write_bytes(b"explicit")
        require(discover_unity_executable(root, explicit) == explicit.resolve(), "explicit Unity discovery changed")
        program_files = root / "Program Files"
        discovered = program_files / "Unity/Hub/Editor/6000.1.12f1/Editor/Unity.exe"
        discovered.parent.mkdir(parents=True)
        discovered.write_bytes(b"default")
        require(
            discover_unity_executable(root, environment={"ProgramFiles": str(program_files)})
            == discovered.resolve(),
            "default Unity Hub discovery no longer matches run_unity_tests_clean.ps1",
        )


def test_launcher_wires_unity_executable_into_implementation_controller() -> None:
    starter = (ROOT / "Pipeline/TaskReviewAgent/Start-GameTaskAgent.ps1").read_text(
        encoding="utf-8-sig"
    )
    worker = (ROOT / "Pipeline/TaskReviewAgent/run_pipeline_agent.py").read_text(
        encoding="utf-8"
    )
    require("'--unity-executable', $UnityExecutable" in starter, "host launcher lost Unity executable")
    require(
        '"unity_executable": args.unity_executable' in worker,
        "implementation controller lost --unity-executable plumbing",
    )


def _unsafe_eol_fixture(root: Path, relative: str, baseline: bytes, current: bytes) -> tuple[Path, dict]:
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "EOL Smoke")
    git(root, "config", "user.email", "eol@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    write_bytes(root, ".gitattributes", b"* -text\n")
    write_bytes(
        root,
        "Tasks/NSC-999.yaml",
        json.dumps({"id": "NSC-999", "exclusive_resources": [f"repo-file:{relative}"]}).encode("utf-8"),
    )
    write_bytes(root, relative, baseline)
    git(root, "add", ".")
    git(root, "commit", "-m", "baseline")
    committed = git_bytes(root, "show", f"HEAD:{relative}")
    require(
        committed == baseline,
        f"EOL fixture did not commit exact bytes for {relative}: "
        f"expected {baseline!r}, got {committed!r}",
    )
    snapshot = snapshot_payload(root, "NSC-999", ())
    write_bytes(root, relative, current)
    return root, snapshot


def test_mixed_and_binary_preserved_resources_fail_without_mutation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-unsafe-eol-") as temporary:
        parent = Path(temporary)
        mixed_current = b"A\r\nChanged\r\n"
        mixed_root, mixed_snapshot = _unsafe_eol_fixture(
            parent / "mixed",
            "Assets/Mixed.unity",
            b"A\r\nB\n",
            mixed_current,
        )
        try:
            normalize_preserved_unity_eol(mixed_root, mixed_snapshot)
        except HygieneError as exc:
            require("mixed line endings" in str(exc), str(exc))
        else:
            raise AssertionError("mixed committed EOL convention was guessed")
        require((mixed_root / "Assets/Mixed.unity").read_bytes() == mixed_current, "mixed-EOL resource was mutated")

        binary_current = b"A\x00Changed\n"
        binary_root, binary_snapshot = _unsafe_eol_fixture(
            parent / "binary",
            "Assets/Binary.asset",
            b"A\x00Base\n",
            binary_current,
        )
        try:
            normalize_preserved_unity_eol(binary_root, binary_snapshot)
        except HygieneError as exc:
            require("binary path" in str(exc), str(exc))
        else:
            raise AssertionError("binary preserved resource was normalized")
        require((binary_root / "Assets/Binary.asset").read_bytes() == binary_current, "binary resource was mutated")


def test_eol_only_preserved_resource_becomes_clean() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-eol-only-") as temporary:
        root, snapshot = _unsafe_eol_fixture(
            Path(temporary) / "repo",
            "Assets/EolOnly.asset",
            b"A\nB\n",
            b"A\r\nB\r\n",
        )
        normalized = normalize_preserved_unity_eol(root, snapshot)
        require(normalized == ["Assets/EolOnly.asset"], "EOL-only resource was not normalized")
        require((root / "Assets/EolOnly.asset").read_bytes() == b"A\nB\n", "EOL-only bytes differ from HEAD")
        require(git(root, "status", "--porcelain=v1", "--untracked-files=all") == "", "EOL-only resource remained dirty")


def test_consistent_preserved_resource_eol_normalization() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-consistent-eol-") as temporary:
        parent = Path(temporary)
        lf_root, lf_snapshot = _unsafe_eol_fixture(
            parent / "lf",
            "Assets/PureLf.asset",
            b"A\nB\n",
            b"A\r\nChanged\r\n",
        )
        normalized_lf = normalize_preserved_unity_eol(lf_root, lf_snapshot)
        require(normalized_lf == ["Assets/PureLf.asset"], "pure-LF resource was not normalized")
        require(
            (lf_root / "Assets/PureLf.asset").read_bytes() == b"A\nChanged\n",
            "pure-LF normalization changed semantics or retained CRLF",
        )

        crlf_root, crlf_snapshot = _unsafe_eol_fixture(
            parent / "crlf",
            "Assets/PureCrlf.unity",
            b"A\r\nB\r\n",
            b"A\nChanged\n",
        )
        normalized_crlf = normalize_preserved_unity_eol(crlf_root, crlf_snapshot)
        require(
            normalized_crlf == ["Assets/PureCrlf.unity"],
            "CRLF-only committed resource was misclassified as mixed",
        )
        require(
            (crlf_root / "Assets/PureCrlf.unity").read_bytes() == b"A\r\nChanged\r\n",
            "pure-CRLF normalization changed semantics or retained bare LF",
        )


def test_no_newline_preserved_resource_fails_without_mutation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-no-newline-eol-") as temporary:
        current = b"Changed without newline"
        root, snapshot = _unsafe_eol_fixture(
            Path(temporary) / "repo",
            "Assets/NoNewline.asset",
            b"Baseline without newline",
            current,
        )
        try:
            normalize_preserved_unity_eol(root, snapshot)
        except HygieneError as exc:
            require("no unambiguous line-ending convention" in str(exc), str(exc))
        else:
            raise AssertionError("no-newline committed resource was normalized without an EOL convention")
        require(
            (root / "Assets/NoNewline.asset").read_bytes() == current,
            "no-newline resource was mutated",
        )


def test_downstream_dirty_checkout_guard_is_unchanged() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-dirty-handoff-guard-") as temporary:
        fixture = Fixture(Path(temporary), generated_resources=False)
        (fixture.checkout / "Unexpected.tmp").write_text("dirty\n", encoding="utf-8")
        workflow = object.__new__(RealTaskReviewWorkflow)
        workflow.last_observation = {}
        workflow.checkout_manager = SimpleNamespace(checkout_path=fixture.checkout)
        try:
            workflow._verify_pushed_handoff(BRANCH, fixture.source_head)
        except TaskReviewContractError as exc:
            require("completely clean committed checkout" in str(exc), str(exc))
        else:
            raise AssertionError("dirty human handoff checkout was accepted")


def test_production_resume_detection_requires_only_exact_clean_ahead_state() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-resume-detection-") as temporary:
        fixture = Fixture(Path(temporary), generated_resources=False)
        fixture.persist_execution_receipt()
        checkout = {
            "status": "conflict",
            "clean": True,
            "branch": BRANCH,
            "expected_branch": BRANCH,
            "path": str(fixture.checkout),
            "reasons": [
                "checkout HEAD abc does not match workflow head def",
                "fresh checkout tree does not match observed source tree",
            ],
        }
        require(_completed_integration_resume_candidate(checkout, TASK_ID), "clean integration restart was not recognized")
        checkout["clean"] = False
        require(not _completed_integration_resume_candidate(checkout, TASK_ID), "dirty restart bypassed checkout protection")


def main() -> int:
    tests = (
        test_builder_order_hygiene_eol_provenance_and_restart,
        test_unrelated_task_does_not_run_builder,
        test_trigger_uses_accepted_builder_scope_plus_declared_output,
        test_builder_failure_prevents_commit_push_and_handoff,
        test_unexpected_generated_path_blocks,
        test_builder_cannot_erase_protected_candidate_baseline,
        test_handoff_uses_clean_post_generation_commit_without_rebuild_instruction,
        test_explicit_and_default_unity_discovery,
        test_launcher_wires_unity_executable_into_implementation_controller,
        test_mixed_and_binary_preserved_resources_fail_without_mutation,
        test_eol_only_preserved_resource_becomes_clean,
        test_consistent_preserved_resource_eol_normalization,
        test_no_newline_preserved_resource_fails_without_mutation,
        test_downstream_dirty_checkout_guard_is_unchanged,
        test_production_resume_detection_requires_only_exact_clean_ahead_state,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"pre_handoff_unity_generation smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
