#!/usr/bin/env python3
"""Deterministic standalone-clone tests for the real TaskReviewAgent checkout boundary."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.contracts import (  # noqa: E402
    TASK_REVIEW_SCHEMA_VERSION,
    semantic_sha256,
)
from Pipeline.TaskReviewAgent.coordination import StaticCoordinationObserver  # noqa: E402
from Pipeline.TaskReviewAgent.durable_checkout import DurableTaskCheckoutManager  # noqa: E402
from Pipeline.TaskReviewAgent.goal_loop import GoalAction, assess_goal_state  # noqa: E402
from Pipeline.TaskReviewAgent import real_checkout as real_checkout_subject  # noqa: E402
from Pipeline.TaskReviewAgent import real_observation as real_observation_subject  # noqa: E402
from Pipeline.TaskReviewAgent.real_checkout import (  # noqa: E402
    RealTaskCheckoutManager,
    branch_name,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402


TASK_ID = "NSC-777"
WORKER_ID = "task-review-agent-smoke"


def run(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def git(root: Path, *args: str, check: bool = True) -> str:
    return run("git", "-C", str(root), *args, cwd=root, check=check).stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def taskcontrol_source() -> str:
    return """from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def git(*args: str) -> str:
    return subprocess.check_output(("git", "-C", str(ROOT), *args), text=True).strip()

if sys.argv[1:] == ["validate"]:
    print("taskcontrol validate: PASS")
    print("Task contract schema: 2.0")
    raise SystemExit(0)

if len(sys.argv) == 4 and sys.argv[1] == "state" and sys.argv[3] == "--json":
    task_id = sys.argv[2]
    print(json.dumps({
        "task_id": task_id,
        "title": "Synthetic Checkout Task",
        "state": "not_delivered",
        "head_commit": git("rev-parse", "HEAD"),
        "head_tree": git("rev-parse", "HEAD^{tree}"),
        "selected_record_id": None,
        "findings": [],
        "dirty_worktree": False,
    }, sort_keys=True))
    raise SystemExit(0)

raise SystemExit(2)
"""


def create_fixture(root: Path) -> tuple[Path, Path, str]:
    remote = root / "remote.git"
    seed = root / "seed"
    controller = root / "controller"

    run("git", "init", "--bare", str(remote), cwd=root)
    run("git", "init", "-b", "main", str(seed), cwd=root)
    git(seed, "config", "user.name", "TaskReviewAgent Smoke")
    git(seed, "config", "user.email", "task-review-agent@example.invalid")

    (seed / "Tasks").mkdir(parents=True)
    (seed / "Pipeline" / "TaskGraph").mkdir(parents=True)
    contract = {
        "schema_version": "2.0",
        "id": TASK_ID,
        "title": "Synthetic Checkout Task",
        "contract_revision": 1,
        "contract_disposition": "active",
        "kind": "implementation",
        "type": "gameplay_system",
        "execution_scope": "single_agent",
        "execution_reason": "Synthetic checkout boundary test.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Already bounded.",
        "depends_on": [],
        "exclusive_resources": [],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
    }
    (seed / "Tasks" / f"{TASK_ID}.yaml").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (seed / "Pipeline" / "TaskGraph" / "taskcontrol.py").write_text(
        taskcontrol_source(),
        encoding="utf-8",
        newline="\n",
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "Create synthetic checkout fixture")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "main")
    run(
        "git",
        "--git-dir",
        str(remote),
        "symbolic-ref",
        "HEAD",
        "refs/heads/main",
        cwd=root,
    )
    run("git", "clone", str(remote), str(controller), cwd=root)
    git(controller, "config", "user.name", "TaskReviewAgent Smoke")
    git(controller, "config", "user.email", "task-review-agent@example.invalid")
    return controller, remote, git(controller, "rev-parse", "HEAD")


def workflow(
    *,
    controller: Path,
    checkout_root: Path,
    coordination_status: str,
) -> RealTaskReviewWorkflow:
    return RealTaskReviewWorkflow(
        source=controller,
        task_id=TASK_ID,
        checkout_root=checkout_root,
        worker_id=WORKER_ID,
        coordination_observer=StaticCoordinationObserver(
            worker_id=WORKER_ID,
            status=coordination_status,
        ),
        allow_local_remote_for_tests=True,
    )


def test_real_checkout_create_resume_and_conflict() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-checkout-") as temporary:
        root = Path(temporary)
        controller, _, source_head = create_fixture(root)
        checkout_root = root / "operator"
        subject = workflow(
            controller=controller,
            checkout_root=checkout_root,
            coordination_status="claimed_by_worker",
        )

        before_tree = git(controller, "rev-parse", "HEAD^{tree}")
        before_status = git(
            controller,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )

        first = subject.observe_goal_state()
        require(
            assess_goal_state(first).action is GoalAction.PREPARE_CHECKOUT,
            "eligible claimed task did not advance to checkout preparation",
        )
        require(first["checkout"]["status"] == "missing", "missing checkout was not observed")

        created = subject.prepare_task_checkout()
        require(created["status"] == "created", f"checkout was not created: {created}")
        second = subject.observe_goal_state()
        require(second["checkout"]["status"] == "ready", "created checkout was not ready")
        require(
            assess_goal_state(second).action is GoalAction.VALIDATE_SCOPE,
            "ready checkout did not advance to path planning",
        )

        checkout = checkout_root / TASK_ID
        require(checkout.is_dir(), "canonical task directory was not created")
        require(checkout.parent == checkout_root, "checkout is not the exact canonical child path")
        require(git(checkout, "rev-parse", "HEAD") == source_head, "checkout HEAD changed")
        require(
            git(checkout, "branch", "--show-current")
            == "nsc-777-synthetic-checkout-task",
            "checkout branch is not deterministic",
        )
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "created checkout is dirty",
        )
        manifest = checkout_root / ".task-review-agent" / f"{TASK_ID}.json"
        require(manifest.is_file(), "external checkout identity manifest is missing")
        require(
            not (checkout / ".task-review-agent").exists(),
            "manifest dirtied task checkout",
        )

        resumed = subject.prepare_task_checkout()
        require(resumed["status"] == "resumed", "exact managed checkout was not resumed")

        (checkout / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
        conflict = subject.observe_goal_state()
        require(conflict["checkout"]["status"] == "conflict", "dirty checkout was accepted")
        require(
            assess_goal_state(conflict).action is GoalAction.NEEDS_HUMAN,
            "checkout conflict did not stop at human reconciliation",
        )

        require(git(controller, "rev-parse", "HEAD") == source_head, "controller HEAD changed")
        require(
            git(controller, "rev-parse", "HEAD^{tree}") == before_tree,
            "controller tree changed",
        )
        require(
            git(controller, "status", "--porcelain=v1", "--untracked-files=all")
            == before_status,
            "checkout preparation dirtied the controller",
        )


def test_real_checkout_requires_github_claim() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-claim-") as temporary:
        root = Path(temporary)
        controller, _, _ = create_fixture(root)
        checkout_root = root / "operator"
        subject = workflow(
            controller=controller,
            checkout_root=checkout_root,
            coordination_status="available_unassigned",
        )
        observation = subject.observe_goal_state()
        assessment = assess_goal_state(observation)
        require(assessment.action is GoalAction.CLAIM_TASK, "unclaimed task bypassed claim gate")
        result = subject.prepare_task_checkout()
        require(result["status"] == "blocked", "checkout manager ignored missing claim")
        require(not (checkout_root / TASK_ID).exists(), "unclaimed task checkout was created")


def test_clean_committed_observation_is_cached_and_invalidated_by_head_change() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-observation-cache-") as temporary:
        root = Path(temporary)
        controller, _, first_head = create_fixture(root)
        subject = workflow(
            controller=controller,
            checkout_root=root / "operator",
            coordination_status="available_unassigned",
        )
        observer = subject.base_observer
        taskcontrol_calls: list[tuple[str, ...]] = []
        original_taskcontrol = observer._taskcontrol

        def counting_taskcontrol(*args: str, check: bool = True):
            taskcontrol_calls.append(args)
            return original_taskcontrol(*args, check=check)

        with mock.patch.object(observer, "_taskcontrol", side_effect=counting_taskcontrol):
            first = subject.observe_goal_state()
            second = subject.observe_goal_state()
            require(first["task"] == second["task"], "cached task observation changed")
            require(
                taskcontrol_calls == [("validate",), ("state", TASK_ID, "--json")],
                f"identical clean observation repeated taskcontrol: {taskcontrol_calls}",
            )

            (controller / "README.md").write_text("new committed input\n", encoding="utf-8")
            dirty = subject.observe_goal_state()
            require(
                dirty["environment"]["controller_clean"] is False,
                "cache hid a dirty controller",
            )
            subject.observe_goal_state()
            require(
                taskcontrol_calls
                == [
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                ],
                f"dirty controller observation was cached: {taskcontrol_calls}",
            )

            git(controller, "add", "README.md")
            git(controller, "commit", "-m", "Advance controller HEAD")
            second_head = git(controller, "rev-parse", "HEAD")
            require(second_head != first_head, "fixture HEAD did not advance")

            changed = subject.observe_goal_state()
            require(
                changed["environment"]["source_head"] == second_head,
                "cache hid the new controller HEAD",
            )
            require(
                taskcontrol_calls
                == [
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                    ("validate",),
                    ("state", TASK_ID, "--json"),
                ],
                f"HEAD change did not invalidate taskcontrol cache: {taskcontrol_calls}",
            )


def test_clean_cached_source_identity_uses_two_git_processes_per_observation() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-task-review-git-identity-") as temporary:
        root = Path(temporary)
        controller, _, _ = create_fixture(root)
        subject = workflow(
            controller=controller,
            checkout_root=root / "operator",
            coordination_status="available_unassigned",
        )
        observer = subject.base_observer
        calls: list[tuple[str, ...]] = []
        original_run = real_observation_subject._run

        def counting_run(args, **values):
            command = tuple(args)
            if command and command[0] == "git":
                calls.append(command)
            return original_run(args, **values)

        with mock.patch.object(real_observation_subject, "_run", side_effect=counting_run):
            subject.observe_goal_state()
            after_first = len(calls)
            subject.observe_goal_state()

        require(after_first == 3, f"initial source observation used {after_first} Git calls")
        second_calls = calls[after_first:]
        require(
            len(second_calls) == 2,
            f"cached source observation used {len(second_calls)} Git calls: {second_calls}",
        )
        require(
            second_calls[0][-4:]
            == ("rev-parse", "HEAD", "HEAD^{tree}", "refs/remotes/origin/main"),
            f"source revisions were not read coherently: {second_calls[0]}",
        )
        require(
            second_calls[1][-4:]
            == ("status", "--porcelain=v1", "--branch", "--untracked-files=all"),
            f"branch and dirty state were not read together: {second_calls[1]}",
        )


_REPO_BINDING_TASK_ID = "NSC-778"
_REPO_BINDING_CONTRACT_PATH = f"Tasks/{_REPO_BINDING_TASK_ID}.yaml"
_REPO_BINDING_TITLE = "Repository Binding Fixture"
_REPO_BINDING_BRANCH = branch_name(_REPO_BINDING_TASK_ID, _REPO_BINDING_TITLE)


def _build_local_checkout(path: Path, *, origin_url: str) -> tuple[str, str]:
    """A standalone local Git checkout with a fake 'origin' -- never cloned,
    fetched, or pushed, so no network call is ever made for a github.com URL.
    `refs/remotes/origin/main` is created with a local ref update instead of
    a real fetch, which is exactly what inspect() reads."""

    path.mkdir(parents=True)
    run("git", "init", "--quiet", "-b", _REPO_BINDING_BRANCH, str(path), cwd=path.parent)
    git(path, "config", "user.name", "Repo Binding Smoke")
    git(path, "config", "user.email", "repo-binding@example.invalid")
    (path / "Tasks").mkdir()
    (path / "Pipeline" / "TaskGraph").mkdir(parents=True)
    contract_bytes = json.dumps({"id": _REPO_BINDING_TASK_ID}, sort_keys=True).encode("utf-8")
    (path / _REPO_BINDING_CONTRACT_PATH).write_bytes(contract_bytes)
    (path / "Pipeline" / "TaskGraph" / "taskcontrol.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    git(path, "add", ".")
    git(path, "commit", "-m", "Synthetic repository-binding fixture")
    head = git(path, "rev-parse", "HEAD")
    tree = git(path, "rev-parse", "HEAD^{tree}")
    git(path, "remote", "add", "origin", origin_url)
    git(path, "update-ref", "refs/remotes/origin/main", head)
    return head, hashlib.sha256(contract_bytes).hexdigest()


def _repo_binding_observation(*, source_head: str, source_tree: str, contract_sha256: str, controller_remote: str) -> dict:
    task = {
        "task_id": _REPO_BINDING_TASK_ID,
        "title": _REPO_BINDING_TITLE,
        "contract_path": _REPO_BINDING_CONTRACT_PATH,
        "contract_revision": 1,
        "task_contract_sha256": contract_sha256,
    }
    environment = {
        "ready": True,
        "controller_clean": True,
        "taskgraph_valid": True,
        "source_head": source_head,
        "source_tree": source_tree,
        "origin_main": source_head,
        "remote_url": controller_remote,
    }
    coordination = {"status": "claimed_by_worker", "worker_id": WORKER_ID}
    identity = {"environment": environment, "task": task, "coordination": coordination}
    return {
        "schema_version": TASK_REVIEW_SCHEMA_VERSION,
        "observation_authority": "real_read_only",
        "observation_sha256": semantic_sha256(identity),
        **identity,
    }


def _repo_binding_manager(checkout_root: Path, *, allow_local: bool = False) -> RealTaskCheckoutManager:
    return RealTaskCheckoutManager(
        source_root=checkout_root,
        task_id=_REPO_BINDING_TASK_ID,
        checkout_root=checkout_root,
        worker_id=WORKER_ID,
        allow_local_remote_for_tests=allow_local,
    )


def test_repo_binding_production_controller_allows_production_checkout() -> None:
    """Case A: NoSafeCircle controller origin -> NoSafeCircle task checkout allowed."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-a-") as temporary:
        checkout_root = Path(temporary)
        origin = "https://github.com/cathode26/NoSafeCircle.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head, source_tree=tree, contract_sha256=contract_sha, controller_remote=origin
        )
        manager = _repo_binding_manager(checkout_root)
        result = manager.inspect(observation)
        require(
            result["status"] in ("unmanaged_exact", "ready"),
            f"matching production origin was rejected: {result}",
        )


def test_durable_checkout_inspection_consolidates_git_identity() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-checkout-git-identity-") as temporary:
        checkout_root = Path(temporary)
        origin = "https://github.com/cathode26/NoSafeCircle.git"
        checkout = checkout_root / _REPO_BINDING_TASK_ID
        head, contract_sha = _build_local_checkout(checkout, origin_url=origin)
        tree = git(checkout, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head,
            source_tree=tree,
            contract_sha256=contract_sha,
            controller_remote=origin,
        )
        manager = DurableTaskCheckoutManager(
            source_root=checkout_root,
            task_id=_REPO_BINDING_TASK_ID,
            checkout_root=checkout_root,
            worker_id=WORKER_ID,
        )
        calls: list[tuple[str, ...]] = []
        original_run = real_checkout_subject._run

        def counting_run(args, **values):
            command = tuple(args)
            if command and command[0] == "git":
                calls.append(command)
            return original_run(args, **values)

        with mock.patch.object(real_checkout_subject, "_run", side_effect=counting_run):
            result = manager.inspect(observation)

        require(
            result["status"] in ("unmanaged_exact", "ready"),
            f"consolidated checkout inspection changed the result: {result}",
        )
        require(len(calls) == 6, f"checkout inspection used {len(calls)} Git calls: {calls}")
        require(
            calls[1][-4:]
            == ("rev-parse", "HEAD", "HEAD^{tree}", "refs/remotes/origin/main"),
            f"checkout revisions were not read coherently: {calls[1]}",
        )
        require(
            calls[2][-4:]
            == ("status", "--porcelain=v1", "--branch", "--untracked-files=all"),
            f"checkout branch and dirty state were not read together: {calls[2]}",
        )


def test_repo_binding_disposable_controller_allows_matching_disposable_checkout() -> None:
    """Case B: a disposable Gauntlet controller origin allows the SAME disposable checkout."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-b-") as temporary:
        checkout_root = Path(temporary)
        origin = "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head, source_tree=tree, contract_sha256=contract_sha, controller_remote=origin
        )
        manager = _repo_binding_manager(checkout_root)
        result = manager.inspect(observation)
        require(
            result["status"] in ("unmanaged_exact", "ready"),
            f"matching disposable origin was rejected: {result}",
        )


def test_repo_binding_disposable_controller_rejects_production_checkout() -> None:
    """Case C: a disposable Gauntlet controller origin rejects a NoSafeCircle checkout."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-c-") as temporary:
        checkout_root = Path(temporary)
        checkout_origin = "https://github.com/cathode26/NoSafeCircle.git"
        controller_origin = "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=checkout_origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head,
            source_tree=tree,
            contract_sha256=contract_sha,
            controller_remote=controller_origin,
        )
        manager = _repo_binding_manager(checkout_root)
        result = manager.inspect(observation)
        require(result["status"] == "conflict", f"cross-repository checkout was accepted: {result}")
        require(
            any("differs from the observed controller origin" in reason for reason in result["reasons"]),
            f"unexpected rejection reasons: {result['reasons']}",
        )


def test_repo_binding_production_controller_rejects_other_github_checkout() -> None:
    """Case D: a NoSafeCircle controller origin rejects an unrelated GitHub checkout."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-d-") as temporary:
        checkout_root = Path(temporary)
        checkout_origin = "https://github.com/someone-else/other-repo.git"
        controller_origin = "https://github.com/cathode26/NoSafeCircle.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=checkout_origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head,
            source_tree=tree,
            contract_sha256=contract_sha,
            controller_remote=controller_origin,
        )
        manager = _repo_binding_manager(checkout_root)
        result = manager.inspect(observation)
        require(result["status"] == "conflict", f"unrelated GitHub checkout was accepted: {result}")
        require(
            any("differs from the observed controller origin" in reason for reason in result["reasons"]),
            f"unexpected rejection reasons: {result['reasons']}",
        )


def test_repo_binding_rejects_after_controller_origin_changes() -> None:
    """Case E: if the controller's origin changes after a prior observation, a
    previously-valid managed checkout must fail closed on the next inspection
    rather than silently trusting stale binding."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-e-") as temporary:
        checkout_root = Path(temporary)
        original_origin = "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=original_origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        manager = _repo_binding_manager(checkout_root)

        first_observation = _repo_binding_observation(
            source_head=head,
            source_tree=tree,
            contract_sha256=contract_sha,
            controller_remote=original_origin,
        )
        first = manager.inspect(first_observation)
        require(first["status"] == "unmanaged_exact", f"initial binding was rejected: {first}")
        manager._write_manifest(first_observation, original_origin)
        managed = manager.inspect(first_observation)
        require(managed["status"] == "ready", f"checkout could not become managed: {managed}")

        changed_origin = "https://github.com/cathode26/NoSafeCircle.git"
        second_observation = _repo_binding_observation(
            source_head=head,
            source_tree=tree,
            contract_sha256=contract_sha,
            controller_remote=changed_origin,
        )
        second = manager.inspect(second_observation)
        require(
            second["status"] == "conflict",
            f"checkout was not rejected after the controller origin changed: {second}",
        )


def test_repo_binding_local_remote_allowed_only_via_test_flag() -> None:
    """Case F: a local/bare remote is accepted only through the explicit
    test-only allow_local_remote_for_tests escape hatch, never by default."""

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-f-") as temporary:
        checkout_root = Path(temporary)
        local_origin = str((checkout_root / "bare-remote.git").resolve())
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=local_origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head, source_tree=tree, contract_sha256=contract_sha, controller_remote=local_origin
        )

        strict_manager = _repo_binding_manager(checkout_root, allow_local=False)
        strict_result = strict_manager.inspect(observation)
        require(
            strict_result["status"] == "conflict",
            f"local remote was accepted without the test-only flag: {strict_result}",
        )

        permissive_manager = _repo_binding_manager(checkout_root, allow_local=True)
        permissive_result = permissive_manager.inspect(observation)
        require(
            permissive_result["status"] in ("unmanaged_exact", "ready"),
            f"local remote was rejected even with the test-only flag: {permissive_result}",
        )


def test_repo_binding_missing_expected_remote_fails_closed() -> None:
    """Fable M1: a missing/unobserved controller origin must fail closed in

    inspect() rather than silently skip the repository-equality invariant
    (e.g. after RealTaskReviewWorkflow._remote_url() returns None following
    an OSError/TimeoutExpired).
    """

    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-m1-") as temporary:
        checkout_root = Path(temporary)
        origin = "https://github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head, source_tree=tree, contract_sha256=contract_sha, controller_remote=""
        )
        manager = _repo_binding_manager(checkout_root)
        result = manager.inspect(observation)
        require(
            result["status"] == "conflict",
            f"missing expected controller remote did not fail closed: {result}",
        )
        require(
            "controller origin remote URL was not observed" in result["reasons"],
            f"unexpected rejection reasons: {result['reasons']}",
        )


def test_repo_binding_credential_bearing_origin_rejected_without_leaking_secret() -> None:
    """Fable M2: a credential-bearing checkout/controller origin must be

    rejected, and the embedded credential must never appear in any returned
    inspect()/_preparation_reasons() reason string.
    """

    secret = "ghs_faketokenvalue"
    origin = f"https://x-access-token:{secret}@github.com/cathode26/orchestrator-gauntlet-stage4-test.git"
    with tempfile.TemporaryDirectory(prefix="nsc-repo-binding-m2-") as temporary:
        checkout_root = Path(temporary)
        head, contract_sha = _build_local_checkout(
            checkout_root / _REPO_BINDING_TASK_ID, origin_url=origin
        )
        tree = git(checkout_root / _REPO_BINDING_TASK_ID, "rev-parse", "HEAD^{tree}")
        observation = _repo_binding_observation(
            source_head=head, source_tree=tree, contract_sha256=contract_sha, controller_remote=origin
        )
        manager = _repo_binding_manager(checkout_root)

        inspected = manager.inspect(observation)
        require(inspected["status"] == "conflict", f"credential-bearing origin was accepted: {inspected}")
        for reason in inspected["reasons"]:
            require(secret not in reason, f"credential leaked into inspect() reason: {reason}")

        preparation_reasons = manager._preparation_reasons(observation)
        for reason in preparation_reasons:
            require(secret not in reason, f"credential leaked into preparation reason: {reason}")


def main() -> int:
    tests = (
        test_real_checkout_create_resume_and_conflict,
        test_real_checkout_requires_github_claim,
        test_clean_committed_observation_is_cached_and_invalidated_by_head_change,
        test_clean_cached_source_identity_uses_two_git_processes_per_observation,
        test_repo_binding_production_controller_allows_production_checkout,
        test_durable_checkout_inspection_consolidates_git_identity,
        test_repo_binding_disposable_controller_allows_matching_disposable_checkout,
        test_repo_binding_disposable_controller_rejects_production_checkout,
        test_repo_binding_production_controller_rejects_other_github_checkout,
        test_repo_binding_rejects_after_controller_origin_changes,
        test_repo_binding_local_remote_allowed_only_via_test_flag,
        test_repo_binding_missing_expected_remote_fails_closed,
        test_repo_binding_credential_bearing_origin_rejected_without_leaking_secret,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent real checkout smoke tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
