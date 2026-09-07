#!/usr/bin/env python3
"""No-network safeguards for the private synthetic gauntlet approver."""

from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.synthetic_gauntlet_approver as approver  # noqa: E402
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    SyntheticEvidencePumpResult,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


RUNNER_RELATIVE = Path("Pipeline/Testing/run_unity_tests_clean.ps1")


def _write_unity_manifest(
    root: Path,
    *,
    commit: str,
    tree: str,
    test_filter: str,
    runner: dict[str, str],
    schema_version: str,
) -> Path:
    """Write one internally consistent fake Unity result without running Unity."""

    root.mkdir(parents=True, exist_ok=True)
    xml = b'<test-run result="Passed" total="1" passed="1" failed="0" skipped="0" />\n'
    log = b"Unity test log\n"
    (root / "test-results.xml").write_bytes(xml)
    (root / "unity.log").write_bytes(log)
    manifest = {
        "schema_version": schema_version,
        "manifest_type": "unity_test_validation",
        "status": "passed",
        "validated_state": {
            "commit": commit,
            "tree": tree,
            "post_commit": commit,
            "post_tree": tree,
            "repository_clean_before": True,
            "repository_clean_after": True,
        },
        "unity": {
            "version": "6000.0.test",
            "executable": "C:/Unity/Unity.exe",
            "exit_code": 0,
            "test_platform": "EditMode",
            "test_filter": test_filter,
        },
        "test_run": {
            "result": "Passed",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
        },
        "artifacts": {
            "xml": {
                "relative_path": "test-results.xml",
                "sha256": hashlib.sha256(xml).hexdigest(),
                "size_bytes": len(xml),
            },
            "log": {
                "relative_path": "unity.log",
                "sha256": hashlib.sha256(log).hexdigest(),
                "size_bytes": len(log),
            },
        },
        "runner": runner,
    }
    path = root / "validation-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _runner_identity(path: Path, *, commit: str, tree: str) -> dict[str, str]:
    return {
        "path": RUNNER_RELATIVE.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_commit": commit,
        "source_tree": tree,
    }


def _patch_optional(name: str, value):
    """Install a production seam that is intentionally absent on the red parent."""

    existed = hasattr(approver, name)
    previous = getattr(approver, name, None)
    setattr(approver, name, value)
    return existed, previous


def _restore_optional(name: str, state) -> None:
    existed, previous = state
    if existed:
        setattr(approver, name, previous)
    else:
        delattr(approver, name)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _initialize_repository(root: Path) -> None:
    root.mkdir(parents=True)
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    _git(root, "config", "user.name", "Synthetic Runner Fixture")
    _git(root, "config", "user.email", "synthetic-runner@example.invalid")


def test_only_exact_direct_gauntlet_provenance_is_accepted() -> None:
    exact = {
        "provenance": {
            "origin": "human_approved_synthetic_gauntlet",
            "gauntlet_id": approver.GAUNTLET_ID,
        }
    }
    require(approver._direct_gauntlet_task(exact), str(exact))
    wrong = json.loads(json.dumps(exact))
    wrong["provenance"]["gauntlet_id"] = "different"
    require(not approver._direct_gauntlet_task(wrong), str(wrong))


def test_private_rehearsal_preflight_refuses_public_and_production() -> None:
    original = approver._run_text

    def public(command, **_values):
        if command[0] == "git":
            if "get-url" in command:
                return "https://github.com/fixture-owner/pipeline-rehearsal.git"
            if "branch" in command:
                return "main"
            if "status" in command or "fetch" in command:
                return ""
            if "rev-parse" in command:
                return "a" * 40
            raise AssertionError(command)
        return json.dumps(
            {
                "nameWithOwner": "fixture-owner/pipeline-rehearsal",
                "isPrivate": False,
                "defaultBranchRef": {"name": "main"},
            }
        )

    approver._run_text = public
    try:
        try:
            approver._require_private_rehearsal(
                ROOT, "fixture-owner/pipeline-rehearsal"
            )
        except approver.SyntheticApprovalError as exc:
            require("private rehearsal" in str(exc), str(exc))
        else:
            raise AssertionError("public rehearsal was accepted")

        def private(command, **values):
            if command[0] == "gh":
                return json.dumps(
                    {
                        "nameWithOwner": "fixture-owner/pipeline-rehearsal",
                        "isPrivate": True,
                        "defaultBranchRef": {"name": "main"},
                    }
                )
            return public(command, **values)

        approver._run_text = private
        require(
            approver._require_private_rehearsal(
                ROOT, "fixture-owner/pipeline-rehearsal"
            )
            == "fixture-owner/pipeline-rehearsal",
            "exact private rehearsal was rejected",
        )

        repository = "fixture-owner/agent-rehearsal"

        def new_private(command, **values):
            return private(command, **values).replace(
                "fixture-owner/pipeline-rehearsal", repository
            )

        approver._run_text = new_private
        require(
            approver._require_private_rehearsal(ROOT, repository) == repository,
            "the explicitly authorized new private rehearsal was rejected",
        )

        approver._run_text = lambda *_args, **_values: (
            "https://github.com/cathode26/NoSafeCircle.git"
        )
        try:
            approver._require_private_rehearsal(ROOT, "cathode26/NoSafeCircle")
        except approver.SyntheticApprovalError as exc:
            require("refuses production" in str(exc), str(exc))
        else:
            raise AssertionError("production repository was accepted")

        def private_lookalike(command, **_values):
            if command[0] == "git":
                if "get-url" in command:
                    return "https://github.com/cathode26/My-Rehearsal.git"
                raise AssertionError(command)
            return json.dumps(
                {
                    "nameWithOwner": "cathode26/My-Rehearsal",
                    "isPrivate": True,
                    "defaultBranchRef": {"name": "main"},
                }
            )

        approver._run_text = private_lookalike
        try:
            approver._require_private_rehearsal(ROOT, "cathode26/My-Rehearsal")
        except approver.SyntheticApprovalError as exc:
            require("exact canonical rehearsal" in str(exc), str(exc))
        else:
            raise AssertionError("private rehearsal lookalike was accepted")
    finally:
        approver._run_text = original


def test_exact_editmode_filter_is_used_before_approval() -> None:
    with tempfile.TemporaryDirectory(prefix="synthetic-approver-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        runner_relative = Path("Pipeline/Testing/run_unity_tests_clean.ps1")
        (source / runner_relative).parent.mkdir(parents=True)
        (source / runner_relative).write_text("runner\n", encoding="utf-8")
        checkout = checkout_root / "NSC-912"
        (checkout / runner_relative).parent.mkdir(parents=True)
        (checkout / runner_relative).write_text("runner\n", encoding="utf-8")
        commit = "a" * 40
        tree = "c" * 40
        contract_hash = "b" * 64
        state = SimpleNamespace(
            checkout_path=str(checkout),
            head_commit=commit,
            human_handoff_commit=commit,
            task_contract_sha256=contract_hash,
            last_event_id="d" * 64,
            branch="nsc-912-fast-task",
        )
        snapshot = SimpleNamespace(state=state)
        expected_filter = approver._test_filter(912)
        task = {
            "id": "NSC-912",
            "task_contract_sha256": contract_hash,
            "execution_scope": "single_agent",
            "provenance": {
                "origin": "human_approved_synthetic_gauntlet",
                "gauntlet_id": approver.GAUNTLET_ID,
                "expected_value": 912,
            },
        }
        calls: list[tuple[str, ...]] = []
        original_plan = approver.validation_plan_for
        original_run = approver.subprocess.run
        original_run_text = approver._run_text
        original_trust = approver._trusted_handoff_runner_identity
        original_controller_identity = approver._controller_runner_identity
        approver.validation_plan_for = lambda *_args: {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": expected_filter},
            "authority": "committed_private_synthetic_gauntlet_validation_policy",
            "policy_sha256": "e" * 64,
        }

        artifact_root = root / "artifacts"
        artifact_root.mkdir()
        xml = b'<test-run result="Passed" total="1" passed="1" failed="0" skipped="0" />\n'
        log = b"Unity test log\n"
        (artifact_root / "test-results.xml").write_bytes(xml)
        (artifact_root / "unity.log").write_bytes(log)
        runner_identity = {
            "path": runner_relative.as_posix(),
            "sha256": hashlib.sha256((source / runner_relative).read_bytes()).hexdigest(),
            "source_commit": commit,
            "source_tree": tree,
        }
        manifest = {
            "schema_version": "1.1",
            "manifest_type": "unity_test_validation",
            "status": "passed",
            "validated_state": {
                "commit": commit,
                "tree": tree,
                "post_commit": commit,
                "post_tree": tree,
                "repository_clean_before": True,
                "repository_clean_after": True,
            },
            "unity": {
                "version": "6000.0.test",
                "executable": "C:/Unity/Unity.exe",
                "exit_code": 0,
                "test_platform": "EditMode",
                "test_filter": expected_filter,
            },
            "test_run": {
                "result": "Passed",
                "total": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
            },
            "artifacts": {
                "xml": {
                    "relative_path": "test-results.xml",
                    "sha256": hashlib.sha256(xml).hexdigest(),
                    "size_bytes": len(xml),
                },
                "log": {
                    "relative_path": "unity.log",
                    "sha256": hashlib.sha256(log).hexdigest(),
                    "size_bytes": len(log),
                },
            },
            "runner": runner_identity,
        }
        manifest_path = artifact_root / "validation-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        def fake_git(command, **_values):
            if "status" in command:
                return ""
            if "branch" in command:
                return state.branch
            if "HEAD^{tree}" in command:
                return tree
            if "HEAD" in command:
                return commit
            raise AssertionError(command)

        def record(command, **_values):
            calls.append(tuple(command))
            return SimpleNamespace(
                returncode=0,
                stdout=f"Validation manifest: {manifest_path}\n",
            )

        approver.subprocess.run = record
        approver._run_text = fake_git
        approver._trusted_handoff_runner_identity = lambda **_values: runner_identity
        approver._controller_runner_identity = lambda _source: runner_identity
        try:
            result = approver._run_unity_validation(
                source=source,
                checkout_root=checkout_root,
                repository="fixture-owner/pipeline-rehearsal",
                snapshot=snapshot,
                task=task,
            )
            (artifact_root / "test-results.xml").write_bytes(xml + b"tampered")
            try:
                approver._run_unity_validation(
                    source=source,
                    checkout_root=checkout_root,
                    repository="fixture-owner/pipeline-rehearsal",
                    snapshot=snapshot,
                    task=task,
                )
            except approver.SyntheticApprovalError as exc:
                require("size_bytes" in str(exc) or "sha256" in str(exc), str(exc))
            else:
                raise AssertionError("tampered Unity XML artifact was accepted")
            (artifact_root / "test-results.xml").write_bytes(xml)
            empty_manifest = json.loads(json.dumps(manifest))
            empty_manifest["test_run"].update({"total": 0, "passed": 0})
            manifest_path.write_text(json.dumps(empty_manifest), encoding="utf-8")
            try:
                approver._run_unity_validation(
                    source=source,
                    checkout_root=checkout_root,
                    repository="fixture-owner/pipeline-rehearsal",
                    snapshot=snapshot,
                    task=task,
                )
            except approver.SyntheticApprovalError as exc:
                require("non-empty passing run" in str(exc), str(exc))
            else:
                raise AssertionError("zero-test Unity manifest was accepted")
        finally:
            approver.validation_plan_for = original_plan
            approver.subprocess.run = original_run
            approver._run_text = original_run_text
            approver._trusted_handoff_runner_identity = original_trust
            approver._controller_runner_identity = original_controller_identity
        require(result["status"].endswith("passed"), str(result))
        evidence = result["evidence"]
        require(evidence["commit"] == commit and evidence["tree"] == tree, str(evidence))
        require(evidence["handoff_event_id"] == "d" * 64, str(evidence))
        require(evidence["unity_validations"][0]["passed"] == 1, str(evidence))
        require(evidence["unity_validations"][0]["xml_sha256"] == hashlib.sha256(xml).hexdigest(), str(evidence))
        command = calls[0]
        require(command[command.index("-TestPlatform") + 1] == "EditMode", str(command))
        require(command[command.index("-TestFilter") + 1] == expected_filter, str(command))


def test_historical_runner_evidence_survives_controller_runner_drift_without_execution() -> None:
    """Runner A evidence remains exact authority after trusted controller main reaches B."""

    with tempfile.TemporaryDirectory(prefix="synthetic-runner-drift-reuse-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        checkout = checkout_root / "NSC-912"
        source_script = source / RUNNER_RELATIVE
        checkout_script = checkout / RUNNER_RELATIVE
        source_script.parent.mkdir(parents=True)
        checkout_script.parent.mkdir(parents=True)
        source_script.write_text("trusted controller runner B\n", encoding="utf-8")
        checkout_script.write_text("trusted historical runner A\n", encoding="utf-8")

        commit = "a" * 40
        tree = "b" * 40
        source_commit = "c" * 40
        source_tree = "d" * 40
        runner_a_commit = "e" * 40
        runner_a_tree = "f" * 40
        expected_filter = approver._test_filter(912)
        artifact_root = root / "artifacts"
        manifest_path = _write_unity_manifest(
            artifact_root,
            commit=commit,
            tree=tree,
            test_filter=expected_filter,
            runner={"path": RUNNER_RELATIVE.as_posix()},
            schema_version="1.0",
        )
        imported = approver.import_validation_manifest(
            manifest_path,
            controller_root=artifact_root,
            expected_commit=commit,
            expected_tree=tree,
            expected_test_platform="EditMode",
            expected_test_filter=expected_filter,
        )
        state = SimpleNamespace(
            checkout_path=str(checkout),
            head_commit=commit,
            human_handoff_commit=commit,
            task_contract_sha256="1" * 64,
            last_event_id="2" * 64,
            branch="nsc-912-runner-drift",
        )
        task = {"id": "NSC-912", "task_contract_sha256": "1" * 64}
        plan = {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": expected_filter},
            "authority": "committed_private_synthetic_gauntlet_validation_policy",
            "policy_sha256": "3" * 64,
        }
        find_calls: list[dict] = []
        execution_calls: list[dict] = []

        def fake_git(command, **_values):
            exact_root = Path(command[command.index("-C") + 1]).resolve()
            if "status" in command:
                return ""
            if "branch" in command:
                return state.branch
            if command[-1] == "HEAD^{tree}":
                return source_tree if exact_root == source.resolve() else tree
            if command[-1] == "HEAD":
                return source_commit if exact_root == source.resolve() else commit
            raise AssertionError(command)

        historical_identity = _runner_identity(
            checkout_script, commit=runner_a_commit, tree=runner_a_tree
        )
        originals = (
            approver.validation_plan_for,
            approver._expected_implementation_filter,
            approver._run_text,
            approver.find_pre_handoff_validation,
            approver._execute_synthetic_unity_validation,
        )
        trust_patch = _patch_optional(
            "_trusted_handoff_runner_identity",
            lambda *_args, **_values: historical_identity,
        )
        approver.validation_plan_for = lambda *_args: plan
        approver._expected_implementation_filter = lambda *_args: expected_filter
        approver._run_text = fake_git
        approver.find_pre_handoff_validation = lambda **values: (
            find_calls.append(values) or imported
        )
        approver._execute_synthetic_unity_validation = lambda **values: (
            execution_calls.append(values)
            or (_ for _ in ()).throw(
                AssertionError("historical exact evidence triggered a hidden Unity run")
            )
        )
        try:
            result = approver._run_unity_validation(
                source=source,
                checkout_root=checkout_root,
                repository="fixture-owner/pipeline-rehearsal",
                snapshot=SimpleNamespace(state=state),
                task=task,
            )
        finally:
            (
                approver.validation_plan_for,
                approver._expected_implementation_filter,
                approver._run_text,
                approver.find_pre_handoff_validation,
                approver._execute_synthetic_unity_validation,
            ) = originals
            _restore_optional("_trusted_handoff_runner_identity", trust_patch)

        require(source_script.read_bytes() != checkout_script.read_bytes(), "fixture did not drift")
        require(len(find_calls) == 1, f"trusted historical evidence was not consulted: {find_calls}")
        require(execution_calls == [], f"Unity unexpectedly ran: {execution_calls}")
        require(result["evidence_source"] == "reused_pre_handoff_validation", str(result))
        require(result["commit"] == commit, str(result))


def test_controller_runner_tree_is_derived_from_the_captured_commit() -> None:
    """A concurrent HEAD move cannot create a mixed runner commit/tree identity."""

    with tempfile.TemporaryDirectory(prefix="synthetic-runner-head-race-") as temporary:
        source = Path(temporary) / "source"
        script = source / RUNNER_RELATIVE
        script.parent.mkdir(parents=True)
        script.write_text("trusted controller runner B\n", encoding="utf-8")
        commit = "1" * 40
        tree = "2" * 40
        blob = "3" * 40
        calls: list[tuple[str, ...]] = []

        def moving_head(command, **_values):
            values = tuple(str(value) for value in command)
            calls.append(values)
            if values[-2:] == ("rev-parse", "HEAD"):
                return commit
            if values[-2:] == ("rev-parse", f"{commit}^{{tree}}"):
                return tree
            if values[-2:] == (
                "rev-parse",
                f"{commit}:{RUNNER_RELATIVE.as_posix()}",
            ):
                return blob
            if "hash-object" in values:
                return blob
            if values[-2:] == ("rev-parse", "HEAD^{tree}"):
                raise AssertionError("runner tree was sampled from moving HEAD")
            raise AssertionError(values)

        original = approver._run_text
        approver._run_text = moving_head
        try:
            identity = approver._controller_runner_identity(source)
        finally:
            approver._run_text = original

        require(identity["source_commit"] == commit, str(identity))
        require(identity["source_tree"] == tree, str(identity))
        require(
            any(call[-1] == f"{commit}^{{tree}}" for call in calls),
            str(calls),
        )


def test_runner_drift_fallback_executes_controller_b_and_binds_its_source_identity() -> None:
    """A fresh run uses B as executable code while A remains the validated project."""

    with tempfile.TemporaryDirectory(prefix="synthetic-runner-drift-fresh-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        checkout = checkout_root / "NSC-912"
        source_script = source / RUNNER_RELATIVE
        checkout_script = checkout / RUNNER_RELATIVE
        source_script.parent.mkdir(parents=True)
        checkout_script.parent.mkdir(parents=True)
        source_script.write_text("trusted controller runner B\n", encoding="utf-8")
        checkout_script.write_text("trusted historical runner A\n", encoding="utf-8")

        commit = "4" * 40
        tree = "5" * 40
        source_commit = "6" * 40
        source_tree = "7" * 40
        expected_filter = approver._test_filter(912)
        runner_b = _runner_identity(
            source_script, commit=source_commit, tree=source_tree
        )
        manifest_path = _write_unity_manifest(
            root / "fresh-artifacts",
            commit=commit,
            tree=tree,
            test_filter=expected_filter,
            runner=runner_b,
            schema_version="1.1",
        )
        state = SimpleNamespace(
            checkout_path=str(checkout),
            head_commit=commit,
            human_handoff_commit=commit,
            task_contract_sha256="8" * 64,
            last_event_id="9" * 64,
            branch="nsc-912-runner-drift",
        )
        task = {"id": "NSC-912", "task_contract_sha256": "8" * 64}
        plan = {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": expected_filter},
            "authority": "committed_private_synthetic_gauntlet_validation_policy",
            "policy_sha256": "a" * 64,
        }
        commands: list[tuple[str, ...]] = []

        def fake_git(command, **_values):
            exact_root = Path(command[command.index("-C") + 1]).resolve()
            if "status" in command:
                return ""
            if "branch" in command:
                return state.branch
            if command[-1] == "HEAD^{tree}":
                return source_tree if exact_root == source.resolve() else tree
            if command[-1] == "HEAD":
                return source_commit if exact_root == source.resolve() else commit
            raise AssertionError(command)

        def fake_unity(command, **_values):
            commands.append(tuple(str(value) for value in command))
            return SimpleNamespace(
                returncode=0,
                stdout=f"Validation manifest: {manifest_path}\n",
            )

        runner_a = _runner_identity(
            checkout_script, commit="b" * 40, tree="c" * 40
        )
        originals = (
            approver.validation_plan_for,
            approver._expected_implementation_filter,
            approver._run_text,
            approver.find_pre_handoff_validation,
            approver.subprocess.run,
        )
        trust_patch = _patch_optional(
            "_trusted_handoff_runner_identity", lambda *_args, **_values: runner_a
        )
        controller_patch = _patch_optional(
            "_controller_runner_identity", lambda *_args, **_values: runner_b
        )
        approver.validation_plan_for = lambda *_args: plan
        approver._expected_implementation_filter = lambda *_args: expected_filter
        approver._run_text = fake_git
        approver.find_pre_handoff_validation = lambda **_values: None
        approver.subprocess.run = fake_unity
        rejected_runner_identities: list[str] = []
        try:
            result = approver._run_unity_validation(
                source=source,
                checkout_root=checkout_root,
                repository="fixture-owner/pipeline-rehearsal",
                snapshot=SimpleNamespace(state=state),
                task=task,
            )
            valid_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for label, field, forged in (
                ("mismatched SHA", "sha256", "0" * 64),
                ("mismatched source commit", "source_commit", "1" * 40),
                ("mismatched source tree", "source_tree", "2" * 40),
                ("malformed SHA", "sha256", "not-a-sha"),
                ("missing SHA", "sha256", None),
            ):
                bad_manifest = json.loads(json.dumps(valid_manifest))
                if forged is None:
                    bad_manifest["runner"].pop(field)
                else:
                    bad_manifest["runner"][field] = forged
                manifest_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
                try:
                    approver._run_unity_validation(
                        source=source,
                        checkout_root=checkout_root,
                        repository="fixture-owner/pipeline-rehearsal",
                        snapshot=SimpleNamespace(state=state),
                        task=task,
                    )
                except approver.SyntheticApprovalError as exc:
                    require(
                        "runner" in str(exc).casefold()
                        or "manifest" in str(exc).casefold(),
                        f"{label}: {exc}",
                    )
                    rejected_runner_identities.append(label)
                else:
                    raise AssertionError(f"fresh manifest accepted {label}")
            manifest_path.write_text(json.dumps(valid_manifest), encoding="utf-8")
        finally:
            (
                approver.validation_plan_for,
                approver._expected_implementation_filter,
                approver._run_text,
                approver.find_pre_handoff_validation,
                approver.subprocess.run,
            ) = originals
            _restore_optional("_trusted_handoff_runner_identity", trust_patch)
            _restore_optional("_controller_runner_identity", controller_patch)

        require(
            len(commands) == 6,
            f"expected one valid and five forged-manifest executions: {commands}",
        )
        command = commands[0]
        require(Path(command[command.index("-File") + 1]).resolve() == source_script.resolve(), str(command))
        require(Path(command[command.index("-ProjectPath") + 1]).resolve() == checkout.resolve(), str(command))
        require(str(checkout_script) not in command, f"historical runner A was executed: {command}")
        require(all(item == command for item in commands), f"fresh runner command drifted: {commands}")
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(raw_manifest["schema_version"] == "1.1", str(raw_manifest))
        require(raw_manifest["runner"] == runner_b, str(raw_manifest["runner"]))
        require(result["evidence_source"] == "fresh_synthetic_unity_execution", str(result))
        require(
            rejected_runner_identities
            == [
                "mismatched SHA",
                "mismatched source commit",
                "mismatched source tree",
                "malformed SHA",
                "missing SHA",
            ],
            str(rejected_runner_identities),
        )


def test_wrong_actual_checkout_branch_is_rejected_before_reuse_or_execution() -> None:
    """Copying the Issue branch text into evidence is not proof of the Git branch."""

    with tempfile.TemporaryDirectory(prefix="synthetic-wrong-branch-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        checkout = checkout_root / "NSC-912"
        for script in (source / RUNNER_RELATIVE, checkout / RUNNER_RELATIVE):
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("same trusted runner\n", encoding="utf-8")
        commit = "d" * 40
        tree = "e" * 40
        expected_filter = approver._test_filter(912)
        manifest_path = _write_unity_manifest(
            root / "artifacts",
            commit=commit,
            tree=tree,
            test_filter=expected_filter,
            runner={"path": RUNNER_RELATIVE.as_posix()},
            schema_version="1.0",
        )
        imported = approver.import_validation_manifest(
            manifest_path,
            controller_root=manifest_path.parent,
            expected_commit=commit,
            expected_tree=tree,
            expected_test_platform="EditMode",
            expected_test_filter=expected_filter,
        )
        state = SimpleNamespace(
            checkout_path=str(checkout),
            head_commit=commit,
            human_handoff_commit=commit,
            task_contract_sha256="f" * 64,
            last_event_id="0" * 64,
            branch="nsc-912-expected",
        )
        plan = {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": expected_filter},
            "authority": "committed_private_synthetic_gauntlet_validation_policy",
            "policy_sha256": "1" * 64,
        }
        touched: list[str] = []

        def fake_git(command, **_values):
            if "status" in command:
                return ""
            if "branch" in command:
                return "nsc-912-wrong"
            if command[-1] == "HEAD^{tree}":
                return tree
            if command[-1] == "HEAD":
                return commit
            raise AssertionError(command)

        identity = _runner_identity(
            checkout / RUNNER_RELATIVE, commit="2" * 40, tree="3" * 40
        )
        originals = (
            approver.validation_plan_for,
            approver._expected_implementation_filter,
            approver._run_text,
            approver.find_pre_handoff_validation,
            approver._execute_synthetic_unity_validation,
        )
        trust_patch = _patch_optional(
            "_trusted_handoff_runner_identity", lambda *_args, **_values: identity
        )
        approver.validation_plan_for = lambda *_args: plan
        approver._expected_implementation_filter = lambda *_args: expected_filter
        approver._run_text = fake_git
        approver.find_pre_handoff_validation = lambda **_values: (
            touched.append("reused") or imported
        )
        approver._execute_synthetic_unity_validation = lambda **_values: (
            touched.append("executed")
        )
        try:
            try:
                approver._run_unity_validation(
                    source=source,
                    checkout_root=checkout_root,
                    repository="fixture-owner/pipeline-rehearsal",
                    snapshot=SimpleNamespace(state=state),
                    task={"id": "NSC-912", "task_contract_sha256": "f" * 64},
                )
            except approver.SyntheticApprovalError as exc:
                require("branch" in str(exc).casefold(), str(exc))
            else:
                raise AssertionError("checkout attached to the wrong Git branch was accepted")
        finally:
            (
                approver.validation_plan_for,
                approver._expected_implementation_filter,
                approver._run_text,
                approver.find_pre_handoff_validation,
                approver._execute_synthetic_unity_validation,
            ) = originals
            _restore_optional("_trusted_handoff_runner_identity", trust_patch)
        require(touched == [], f"wrong branch reached validation evidence: {touched}")


def test_task_local_runner_edit_cannot_forge_historical_runner_provenance() -> None:
    """A self-consistent receipt cannot call a task-edited runner an inherited one."""

    with tempfile.TemporaryDirectory(prefix="synthetic-runner-forgery-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        checkout = checkout_root / "NSC-912"
        _initialize_repository(source)
        source_script = source / RUNNER_RELATIVE
        source_script.parent.mkdir(parents=True)
        source_script.write_text("trusted controller runner B\n", encoding="utf-8")
        _git(source, "add", ".")
        _git(source, "commit", "-qm", "controller runner B")

        _initialize_repository(checkout)
        checkout_script = checkout / RUNNER_RELATIVE
        checkout_script.parent.mkdir(parents=True)
        checkout_script.write_text("trusted historical runner A\n", encoding="utf-8")
        _git(checkout, "add", ".")
        _git(checkout, "commit", "-qm", "trusted base with runner A")
        base = _git(checkout, "rev-parse", "HEAD")
        branch = "nsc-912-runner-forgery"
        _git(checkout, "checkout", "-qb", branch)
        asset = checkout / "Assets" / "Thing.cs"
        asset.parent.mkdir(parents=True)
        asset.write_text("public class Thing { }\n", encoding="utf-8")
        checkout_script.write_text("task-local forged runner\n", encoding="utf-8")
        _git(checkout, "add", ".")
        _git(checkout, "commit", "-qm", "task changes asset and runner")
        commit = _git(checkout, "rev-parse", "HEAD")
        tree = _git(checkout, "rev-parse", "HEAD^{tree}")

        # This models a forged controller-state body whose own semantic checksum
        # has been recomputed. The immutable base/commit runner blobs must still
        # expose that the task changed the runner rather than inheriting it.
        body = {
            "schema_version": "1.2",
            "task_id": "NSC-912",
            "lease_id": "lease-1",
            "plan_id": "plan-1",
            "run_id": "run-1",
            "provider": "claude",
            "branch": branch,
            "base_head": base,
            "commit": commit,
            "commit_tree": tree,
            "task_contract_sha256": "4" * 64,
            "candidate_sha256": "5" * 64,
            "changed_paths": ["Assets/Thing.cs"],
            "pre_handoff_validations": [],
            "completed_checks": ["candidate_applied"],
        }
        state_root = checkout_root / ".task-review-agent"
        state_root.mkdir()
        (state_root / "NSC-912.integration.json").write_text(
            json.dumps({**body, "receipt_sha256": semantic_sha256(body)}),
            encoding="utf-8",
        )
        resolver = getattr(approver, "_trusted_handoff_runner_identity", None)
        require(callable(resolver), "trusted handoff runner resolver is missing")
        try:
            resolver(
                source=source,
                checkout=checkout,
                task_id="NSC-912",
                branch=branch,
                commit=commit,
                tree=tree,
            )
        except approver.SyntheticApprovalError as exc:
            require("runner" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError("task-local Unity runner edit forged inherited provenance")


def test_reintegrated_handoff_runner_is_proven_from_its_ordered_main_parent() -> None:
    """The live NSC-917 shape proves B and rejects a rehashed task-authored runner."""

    with tempfile.TemporaryDirectory(prefix="synthetic-reintegrated-runner-") as temporary:
        root = Path(temporary)
        source = root / "source"
        checkout_root = root / "checkouts"
        checkout = checkout_root / "NSC-917"
        _initialize_repository(source)
        source_runner = source / RUNNER_RELATIVE
        source_runner.parent.mkdir(parents=True)
        source_runner.write_text("trusted historical runner A\n", encoding="utf-8")
        _git(source, "add", ".")
        _git(source, "commit", "-qm", "trusted main A")
        _git(source, "branch", "-M", "main")

        subprocess.run(
            ("git", "clone", "-q", str(source), str(checkout)),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _git(checkout, "config", "user.name", "Reintegration Fixture")
        _git(checkout, "config", "user.email", "reintegrated@example.invalid")
        branch = "nsc-917-reintegrated-runner"
        _git(checkout, "checkout", "-qb", branch)
        asset = checkout / "Assets/Thing.cs"
        asset.parent.mkdir(parents=True)
        asset.write_text("public class Thing { }\n", encoding="utf-8")
        _git(checkout, "add", ".")
        _git(checkout, "commit", "-qm", "task change")
        prior_task_head = _git(checkout, "rev-parse", "HEAD")

        source_runner.write_text("trusted current runner B\n", encoding="utf-8")
        _git(source, "add", ".")
        _git(source, "commit", "-qm", "trusted main B")
        main_head = _git(source, "rev-parse", "HEAD")
        _git(checkout, "fetch", "-q", "origin", "main")
        _git(checkout, "merge", "--no-ff", "-m", "integrate current main", "origin/main")
        commit = _git(checkout, "rev-parse", "HEAD")
        tree = _git(checkout, "rev-parse", "HEAD^{tree}")

        reintegration_payload = {
            "schema_version": "1.0",
            "task_id": "NSC-917",
            "branch": branch,
            "prior_task_head": prior_task_head,
            "main_head": main_head,
            "integrated_commit": commit,
            "authority": "deterministic_mainline_reintegration",
        }
        reintegration = {
            **reintegration_payload,
            "receipt_sha256": semantic_sha256(reintegration_payload),
        }
        downstream_payload = {
            "schema_version": "1.0",
            "task_id": "NSC-917",
            "mainline_reintegration": reintegration,
            "validation_manifests": [],
        }
        state_root = checkout_root / ".task-review-agent"
        state_root.mkdir()
        (state_root / "NSC-917.downstream.json").write_text(
            json.dumps(
                {
                    **downstream_payload,
                    "receipt_sha256": semantic_sha256(downstream_payload),
                }
            ),
            encoding="utf-8",
        )

        identity = approver._trusted_handoff_runner_identity(
            source=source,
            checkout=checkout,
            task_id="NSC-917",
            branch=branch,
            commit=commit,
            tree=tree,
        )
        require(identity["path"] == RUNNER_RELATIVE.as_posix(), str(identity))
        require(
            identity["sha256"] == hashlib.sha256((checkout / RUNNER_RELATIVE).read_bytes()).hexdigest(),
            str(identity),
        )
        require(identity["source_commit"] == commit, str(identity))
        require(identity["source_tree"] == tree, str(identity))
        require(
            _git(checkout, "show", "-s", "--format=%P", commit).split()
            == [prior_task_head, main_head],
            "fixture did not reproduce the live ordered-parent contract",
        )

        # Preserve the receipt's ordered parents but amend the merge tree so the
        # task checkout authors different runner bytes. Rehashing both JSON
        # layers must not turn that self-consistent forgery into provenance.
        (checkout / RUNNER_RELATIVE).write_text(
            "task-authored merge runner\n", encoding="utf-8"
        )
        _git(checkout, "add", RUNNER_RELATIVE.as_posix())
        _git(checkout, "commit", "--amend", "--no-edit", "-q")
        forged_commit = _git(checkout, "rev-parse", "HEAD")
        forged_tree = _git(checkout, "rev-parse", "HEAD^{tree}")
        forged_reintegration_payload = {
            **reintegration_payload,
            "integrated_commit": forged_commit,
        }
        forged_reintegration = {
            **forged_reintegration_payload,
            "receipt_sha256": semantic_sha256(forged_reintegration_payload),
        }
        forged_downstream_payload = {
            **downstream_payload,
            "mainline_reintegration": forged_reintegration,
        }
        (state_root / "NSC-917.downstream.json").write_text(
            json.dumps(
                {
                    **forged_downstream_payload,
                    "receipt_sha256": semantic_sha256(forged_downstream_payload),
                }
            ),
            encoding="utf-8",
        )
        require(
            _git(checkout, "show", "-s", "--format=%P", forged_commit).split()
            == [prior_task_head, main_head],
            "forged fixture did not retain the receipt's ordered parents",
        )
        try:
            approver._trusted_handoff_runner_identity(
                source=source,
                checkout=checkout,
                task_id="NSC-917",
                branch=branch,
                commit=forged_commit,
                tree=forged_tree,
            )
        except approver.SyntheticApprovalError as exc:
            require("inherited" in str(exc).casefold(), str(exc))
        else:
            raise AssertionError(
                "rehashing the reintegration receipt authorized a task-authored runner"
            )


def test_decomposition_requires_fresh_exact_disjoint_partition() -> None:
    with tempfile.TemporaryDirectory(prefix="synthetic-decomposition-review-") as temporary:
        artifact_root = Path(temporary)
        (artifact_root / "graph_delta.json").write_text("{}\n", encoding="utf-8")
        (artifact_root / "decomposition_result.json").write_text(
            "{}\n", encoding="utf-8"
        )
        plan_id = "GDP-" + ("a" * 64)
        paths = [
            "Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs",
            "Assets/Gauntlet/MuffcabbageGauntlet911Alpha.cs.meta",
            "Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs",
            "Assets/Gauntlet/MuffcabbageGauntlet911Beta.cs.meta",
        ]
        task = {
            "schema_version": "2.0",
            "id": "NSC-911",
            "contract_revision": 1,
            "task_contract_sha256": "f" * 64,
            "exclusive_resources": [f"repo-file:{path}" for path in paths],
            "provenance": {
                "origin": "human_approved_synthetic_gauntlet",
                "gauntlet_id": approver.GAUNTLET_ID,
                "requires_decomposition": True,
                "expected_paths": paths,
            },
        }
        parent_hash = approver.semantic_json_sha256(
            {key: value for key, value in task.items() if key != "task_contract_sha256"}
        )

        def child(task_id: str, resources: list[str], suffix: str) -> dict:
            return {
                "id": task_id,
                "parent": task["id"],
                "execution_scope": "single_agent",
                "decomposition_state": "concrete",
                "exclusive_resources": resources,
                "completion_gates": [
                    {
                        "requirement": (
                            f"Run {approver._test_filter(911, suffix)} for this exact commit."
                        )
                    }
                ],
                "provenance": {
                    "origin": "progressive_decomposition",
                    "parent_contract_sha256": parent_hash,
                    "graph_delta_plan_id": plan_id,
                },
            }

        contracts = [
            child("NSC-991", [f"repo-file:{path}" for path in paths[:2]], "Alpha"),
            child("NSC-992", [f"repo-file:{path}" for path in paths[2:]], "Beta"),
        ]
        graph = SimpleNamespace(
            plan_id=plan_id,
            proposed_child_contracts=contracts,
            to_dict=lambda: {"parent_before_hash": parent_hash},
            canonical_json=lambda: "{}",
        )
        decomposition = SimpleNamespace(
            decision="decomposed",
            children=(object(), object()),
            unsupported_assumptions=(),
            unresolved_questions=(),
            parent_task=SimpleNamespace(
                task_id=task["id"], contract_sha256=parent_hash
            ),
        )
        event = SimpleNamespace(
            event_type=approver.WorkflowEventType.DECOMPOSITION_HANDOFF_CREATED,
            event_id="d" * 64,
            details={
                "artifact_root": str(artifact_root),
                "graph_delta_plan_id": plan_id,
                "graph_delta_sha256": hashlib.sha256(b"{}").hexdigest(),
                "head_commit": "a" * 40,
                "branch": "main",
            },
        )
        snapshot = SimpleNamespace(
            issue_number=91,
            events=(event,),
            state=SimpleNamespace(
                head_commit="a" * 40,
                human_handoff_commit="a" * 40,
                branch="main",
                last_event_id="d" * 64,
                task_contract_sha256="f" * 64,
            ),
        )

        originals = (
            approver.GraphDeltaPlan,
            approver.DecompositionResult,
            approver.load_persistent_work_graph,
            approver.plan_graph_apply,
            approver.decomposition_validation_policy_for,
            approver._run_text,
        )
        approver.GraphDeltaPlan = SimpleNamespace(from_payload=lambda _payload: graph)
        approver.DecompositionResult = SimpleNamespace(
            from_dict=lambda _payload: decomposition
        )
        approver.load_persistent_work_graph = lambda _source: object()
        approver.plan_graph_apply = lambda *_args: SimpleNamespace(
            status="fresh",
            recomputed_plan_id=plan_id,
            reason="exact deterministic match",
        )
        approver.decomposition_validation_policy_for = lambda *_args, **_values: {
            "policy_sha256": "e" * 64
        }
        approver._run_text = lambda *_args, **_values: "b" * 40
        try:
            result = approver.review_decomposition_plan(ROOT, snapshot, task)
            require(result["child_ids"] == ["NSC-991", "NSC-992"], str(result))
            evidence = result["evidence"]
            require(evidence["graph_delta_plan_id"] == plan_id, str(evidence))
            require(
                evidence["decomposition_result_sha256"]
                == hashlib.sha256(
                    (artifact_root / "decomposition_result.json").read_bytes()
                ).hexdigest(),
                str(evidence),
            )
            require([item["task_id"] for item in evidence["children"]] == ["NSC-991", "NSC-992"], str(evidence))
            contracts[1]["exclusive_resources"] = contracts[0][
                "exclusive_resources"
            ]
            try:
                approver.review_decomposition_plan(ROOT, snapshot, task)
            except approver.SyntheticApprovalError as exc:
                require("resource ownership" in str(exc), str(exc))
            else:
                raise AssertionError("overlapping child resources were approved")
        finally:
            (
                approver.GraphDeltaPlan,
                approver.DecompositionResult,
                approver.load_persistent_work_graph,
                approver.plan_graph_apply,
                approver.decomposition_validation_policy_for,
                approver._run_text,
            ) = originals


def test_decomposition_uses_agent_evidence_and_pokes_the_architect() -> None:
    commit = "a" * 40
    calls: list[dict] = []
    state = SimpleNamespace(
        phase=approver.WorkflowPhase.DECOMPOSITION_APPLY,
        human_result=None,
        human_handoff_commit=commit,
        state_version=9,
        last_event_id="c" * 64,
    )

    class Service:
        def apply_automated_decomposition_result(self, **values):
            calls.append(values)
            return {"status": "agent_ready", "issue_number": 91}

        def find(self, task_id):
            require(task_id == "NSC-911", task_id)
            return SimpleNamespace(valid=True, state=state)

        def clear_vincent_notification_after_automated_evidence(self, task_id):
            require(task_id == "NSC-911", task_id)
            return "deleted"

    original_hint = approver.publish_resume_hint
    hints: list[dict] = []
    approver.publish_resume_hint = lambda source, **values: (
        hints.append({"source": source, **values}) or source / "resume.json"
    )
    evidence = {"source_commit": commit}
    try:
        result = approver._apply_automated_decomposition(
            source=ROOT,
            service=Service(),
            task_id="NSC-911",
            evidence=evidence,
        )
    finally:
        approver.publish_resume_hint = original_hint
    require(calls == [{
        "task_id": "NSC-911",
        "evidence": evidence,
        "actor_id": "synthetic-gauntlet-approver",
    }], str(calls))
    require(result["vincent_notification"] == "deleted", str(result))
    require(hints[0]["event_id"] == "c" * 64, str(hints))
    require(hints[0]["to_phase"] == "decomposition_apply", str(hints))
    source = inspect.getsource(approver)
    require("pass_and_resume_task.py" not in source, source)
    require("apply_human_result" not in source, source)


def test_implementation_uses_agent_evidence_and_pokes_the_architect() -> None:
    commit = "a" * 40
    calls: list[dict] = []
    state = SimpleNamespace(
        phase=approver.WorkflowPhase.DELIVERY_EVIDENCE,
        human_result=None,
        human_handoff_commit=commit,
        state_version=7,
        last_event_id="b" * 64,
    )

    class Service:
        def apply_automated_validation(self, **values):
            calls.append(values)
            return {"status": "agent_ready", "issue_number": 91}

        def find(self, task_id):
            require(task_id == "NSC-912", task_id)
            return SimpleNamespace(valid=True, state=state)

        def clear_vincent_notification_after_automated_evidence(self, task_id):
            require(task_id == "NSC-912", task_id)
            return "deleted"

    original_hint = approver.publish_resume_hint
    hints: list[dict] = []
    approver.publish_resume_hint = lambda source, **values: (
        hints.append({"source": source, **values}) or source / "resume.json"
    )
    evidence = {"commit": commit}
    try:
        result = approver._apply_automated_validation(
            source=ROOT,
            service=Service(),
            task_id="NSC-912",
            evidence=evidence,
        )
    finally:
        approver.publish_resume_hint = original_hint
    require(calls == [{
        "task_id": "NSC-912",
        "evidence": evidence,
        "actor_id": "synthetic-gauntlet-approver",
    }], str(calls))
    require(result["vincent_notification"] == "deleted", str(result))
    require(hints[0]["event_id"] == "b" * 64, str(hints))
    require(hints[0]["to_phase"] == "delivery_evidence", str(hints))
    source = inspect.getsource(approver._apply_automated_validation)
    require("apply_human_result" not in source and "human_result=pass" not in source, source)


def test_main_processes_every_current_synthetic_issue_serially() -> None:
    task_ids = ("NSC-911", "NSC-912")
    snapshots = {
        "NSC-911": SimpleNamespace(
            valid=True,
            issue_number=91,
            state=SimpleNamespace(
                state=approver.WorkflowState.HUMAN_ACTION_REQUIRED,
                phase=approver.WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION,
                head_commit="a" * 40,
            ),
        ),
        "NSC-912": SimpleNamespace(
            valid=True,
            issue_number=92,
            state=SimpleNamespace(
                state=approver.WorkflowState.HUMAN_ACTION_REQUIRED,
                phase=approver.WorkflowPhase.UNITY_RUNTIME_VALIDATION,
                head_commit="b" * 40,
            ),
        ),
    }
    order: list[str] = []

    class Service:
        def __init__(self, **_kwargs):
            pass

        def list_human_action_required(self):
            return [
                {"workflow_state": {"task_id": task_id}}
                for task_id in task_ids
            ]

        def find(self, task_id):
            order.append(f"find:{task_id}")
            return snapshots[task_id]

    originals = (
        approver.repo_root,
        approver._require_private_rehearsal,
        approver.GhIssueBackend,
        approver.IssueWorkflowService,
        approver._require_gauntlet_task,
        approver.review_decomposition_plan,
        approver._apply_automated_decomposition,
        approver._run_unity_validation,
        approver._apply_automated_validation,
    )
    approver.repo_root = lambda source: source
    approver._require_private_rehearsal = lambda *_args: "fixture/rehearsal"
    approver.GhIssueBackend = lambda **_kwargs: object()
    approver.IssueWorkflowService = Service
    approver._require_gauntlet_task = lambda _source, task_id: {"id": task_id}
    approver.review_decomposition_plan = lambda _source, _snapshot, task, **_options: (
        order.append(f"review:{task['id']}")
        or {"evidence": {"task_id": task["id"]}}
    )
    approver._apply_automated_decomposition = lambda **values: (
        order.append(f"apply-decomposition:{values['task_id']}")
        or {
            "status": "ok",
            "automated_decomposition_event_id": "d" * 64,
            "last_event_id": "d" * 64,
            "workflow_state": {
                "task_id": values["task_id"],
                "human_result": None,
            },
        }
    )
    approver._run_unity_validation = lambda **values: (
        order.append(f"validate:{values['task']['id']}")
        or {"evidence": {"task_id": values["task"]["id"]}}
    )
    approver._apply_automated_validation = lambda **values: (
        order.append(f"apply-validation:{values['task_id']}")
        or {
            "status": "ok",
            "automated_validation_event_id": "e" * 64,
            "last_event_id": "e" * 64,
            "workflow_state": {
                "task_id": values["task_id"],
                "human_result": None,
            },
        }
    )
    try:
        result = approver.main(
            (
                "--source",
                str(ROOT),
                "--checkout-root",
                str(ROOT.parent),
                "--confirm-repository",
                "fixture/rehearsal",
                "--apply",
            )
        )
    finally:
        (
            approver.repo_root,
            approver._require_private_rehearsal,
            approver.GhIssueBackend,
            approver.IssueWorkflowService,
            approver._require_gauntlet_task,
            approver.review_decomposition_plan,
            approver._apply_automated_decomposition,
            approver._run_unity_validation,
            approver._apply_automated_validation,
        ) = originals
    require(result == 0, str(result))
    require(
        order
        == [
            "find:NSC-911",
            "review:NSC-911",
            "apply-decomposition:NSC-911",
            "find:NSC-912",
            "validate:NSC-912",
            "apply-validation:NSC-912",
        ],
        str(order),
    )


def test_process_one_returns_exact_implementation_event_identity() -> None:
    task_id = "NSC-912"
    event_id = "e" * 64
    evidence = {"task_id": task_id, "commit": "a" * 40, "kind": "unity"}
    calls: list[str] = []
    snapshot = SimpleNamespace(
        valid=True,
        issue_number=92,
        state=SimpleNamespace(
            state=approver.WorkflowState.HUMAN_ACTION_REQUIRED,
            phase=approver.WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            head_commit="a" * 40,
        ),
    )

    class Service:
        def __init__(self, **_kwargs):
            calls.append("service-created")

        def find(self, selected_task_id):
            calls.append(f"find:{selected_task_id}")
            return snapshot

    originals = (
        approver.repo_root,
        approver._require_private_rehearsal,
        approver.GhIssueBackend,
        approver.IssueWorkflowService,
        approver._require_gauntlet_task,
        approver._run_unity_validation,
        approver._apply_automated_validation,
    )
    approver.repo_root = lambda source: source
    approver._require_private_rehearsal = lambda *_args: (
        calls.append("repository-verified") or approver.AUTOMATED_VALIDATION_REPOSITORY
    )
    approver.GhIssueBackend = lambda **_kwargs: object()
    approver.IssueWorkflowService = Service
    approver._require_gauntlet_task = lambda _source, selected_task_id: {
        "id": selected_task_id
    }
    approver._run_unity_validation = lambda **values: (
        calls.append(f"validate:{values['task']['id']}")
        or {"evidence": evidence, "status": "passed"}
    )
    approver._apply_automated_validation = lambda **values: (
        calls.append(f"apply:{values['task_id']}")
        or {
            "automated_validation_event_id": event_id,
            "last_event_id": event_id,
            "workflow_state": {"task_id": task_id, "human_result": None},
        }
    )
    try:
        result = approver.process_one_synthetic_handoff(
            task_id,
            source=ROOT,
            checkout_root=ROOT.parent,
            confirm_repository=approver.AUTOMATED_VALIDATION_REPOSITORY,
        )
    finally:
        (
            approver.repo_root,
            approver._require_private_rehearsal,
            approver.GhIssueBackend,
            approver.IssueWorkflowService,
            approver._require_gauntlet_task,
            approver._run_unity_validation,
            approver._apply_automated_validation,
        ) = originals
    require(type(result) is SyntheticEvidencePumpResult, repr(result))
    require(result.task_id == task_id, repr(result))
    require(result.event_id == event_id, repr(result))
    require(result.evidence_sha256 == semantic_sha256(evidence), repr(result))
    require(
        calls
        == [
            "repository-verified",
            "service-created",
            f"find:{task_id}",
            f"validate:{task_id}",
            "repository-verified",
            f"apply:{task_id}",
        ],
        str(calls),
    )


def test_process_one_returns_exact_decomposition_event_identity() -> None:
    task_id = "NSC-911"
    event_id = "d" * 64
    evidence = {"task_id": task_id, "source_commit": "a" * 40, "kind": "split"}
    calls: list[str] = []
    snapshot = SimpleNamespace(
        valid=True,
        issue_number=91,
        state=SimpleNamespace(
            state=approver.WorkflowState.HUMAN_ACTION_REQUIRED,
            phase=approver.WorkflowPhase.DECOMPOSITION_APPLY_AUTHORIZATION,
        ),
    )

    class Service:
        def __init__(self, **_kwargs):
            pass

        def find(self, selected_task_id):
            require(selected_task_id == task_id, selected_task_id)
            return snapshot

    originals = (
        approver.repo_root,
        approver._require_private_rehearsal,
        approver.GhIssueBackend,
        approver.IssueWorkflowService,
        approver._require_gauntlet_task,
        approver.review_decomposition_plan,
        approver._apply_automated_decomposition,
    )
    approver.repo_root = lambda source: source
    approver._require_private_rehearsal = lambda *_args: (
        calls.append("repository-verified")
        or approver.AUTOMATED_VALIDATION_REPOSITORY
    )
    approver.GhIssueBackend = lambda **_kwargs: object()
    approver.IssueWorkflowService = Service
    approver._require_gauntlet_task = lambda _source, selected_task_id: {
        "id": selected_task_id
    }
    approver.review_decomposition_plan = lambda _source, _snapshot, _task, **_options: (
        calls.append("review") or {"evidence": evidence, "status": "passed"}
    )
    approver._apply_automated_decomposition = lambda **_values: (
        calls.append("apply")
        or {
            "automated_decomposition_event_id": event_id,
            "last_event_id": event_id,
            "workflow_state": {"task_id": task_id, "human_result": None},
        }
    )
    try:
        result = approver.process_one_synthetic_handoff(
            task_id,
            source=ROOT,
            checkout_root=ROOT.parent,
            confirm_repository=approver.AUTOMATED_VALIDATION_REPOSITORY,
        )
    finally:
        (
            approver.repo_root,
            approver._require_private_rehearsal,
            approver.GhIssueBackend,
            approver.IssueWorkflowService,
            approver._require_gauntlet_task,
            approver.review_decomposition_plan,
            approver._apply_automated_decomposition,
        ) = originals
    require(type(result) is SyntheticEvidencePumpResult, repr(result))
    require(result.task_id == task_id, repr(result))
    require(result.event_id == event_id, repr(result))
    require(result.evidence_sha256 == semantic_sha256(evidence), repr(result))
    require(
        calls == ["repository-verified", "review", "repository-verified", "apply"],
        str(calls),
    )


def test_source_move_after_validation_prevents_issue_mutation() -> None:
    task_id = "NSC-912"
    selected_head = approver._run_text(
        ("git", "-C", str(ROOT), "rev-parse", "HEAD"), cwd=ROOT
    )
    calls: list[str] = []
    snapshot = SimpleNamespace(
        valid=True,
        issue_number=92,
        state=SimpleNamespace(
            state=approver.WorkflowState.HUMAN_ACTION_REQUIRED,
            phase=approver.WorkflowPhase.UNITY_RUNTIME_VALIDATION,
            head_commit="a" * 40,
        ),
    )

    class Service:
        def __init__(self, **_kwargs):
            pass

        def find(self, _task_id):
            calls.append("find")
            return snapshot

    def preflight(*args):
        calls.append("preflight")
        if len(calls) > 3:
            raise approver.SyntheticApprovalError(
                "synthetic approval source HEAD differs from the selected graph snapshot"
            )
        return approver.AUTOMATED_VALIDATION_REPOSITORY

    originals = (
        approver.repo_root,
        approver._require_private_rehearsal,
        approver.GhIssueBackend,
        approver.IssueWorkflowService,
        approver._require_gauntlet_task,
        approver._run_unity_validation,
        approver._apply_automated_validation,
    )
    approver.repo_root = lambda source: source
    approver._require_private_rehearsal = preflight
    approver.GhIssueBackend = lambda **_kwargs: object()
    approver.IssueWorkflowService = Service
    approver._require_gauntlet_task = lambda _source, _task_id: {"id": task_id}
    approver._run_unity_validation = lambda **_values: (
        calls.append("validate") or {"evidence": {"task_id": task_id}}
    )
    approver._apply_automated_validation = lambda **_values: calls.append("MUTATED")
    try:
        try:
            approver.process_one_synthetic_handoff(
                task_id,
                source=ROOT,
                checkout_root=ROOT.parent,
                confirm_repository=approver.AUTOMATED_VALIDATION_REPOSITORY,
                expected_source_head=selected_head,
            )
        except approver.SyntheticApprovalError as exc:
            require("selected graph snapshot" in str(exc), str(exc))
        else:
            raise AssertionError("source move did not stop the Issue transition")
    finally:
        (
            approver.repo_root,
            approver._require_private_rehearsal,
            approver.GhIssueBackend,
            approver.IssueWorkflowService,
            approver._require_gauntlet_task,
            approver._run_unity_validation,
            approver._apply_automated_validation,
        ) = originals
    require(calls == ["preflight", "find", "validate", "preflight"], str(calls))


def test_process_one_repository_refusal_precedes_issue_access() -> None:
    touched: list[str] = []
    original_root = approver.repo_root
    original_preflight = approver._require_private_rehearsal
    original_backend = approver.GhIssueBackend
    approver.repo_root = lambda source: source
    approver._require_private_rehearsal = lambda *_args: (_ for _ in ()).throw(
        approver.SyntheticApprovalError("synthetic approval requires the exact private rehearsal")
    )
    approver.GhIssueBackend = lambda **_kwargs: touched.append("backend")
    try:
        try:
            approver.process_one_synthetic_handoff(
                "NSC-912",
                source=ROOT,
                checkout_root=ROOT.parent,
                confirm_repository="cathode26/lookalike",
            )
        except approver.SyntheticApprovalError as exc:
            require("exact private rehearsal" in str(exc), str(exc))
        else:
            raise AssertionError("lookalike repository reached Issue access")
    finally:
        approver.repo_root = original_root
        approver._require_private_rehearsal = original_preflight
        approver.GhIssueBackend = original_backend
    require(touched == [], str(touched))


def test_process_one_refuses_nsc_042_before_repository_or_issue_access() -> None:
    touched: list[str] = []
    original_root = approver.repo_root
    original_preflight = approver._require_private_rehearsal
    original_backend = approver.GhIssueBackend
    approver.repo_root = lambda source: touched.append("repo-root") or source
    approver._require_private_rehearsal = lambda *_args: (
        touched.append("repository-preflight") or approver.AUTOMATED_VALIDATION_REPOSITORY
    )
    approver.GhIssueBackend = lambda **_kwargs: touched.append("backend")
    try:
        try:
            approver.process_one_synthetic_handoff(
                "NSC-042",
                source=ROOT,
                checkout_root=ROOT.parent,
                confirm_repository=approver.AUTOMATED_VALIDATION_REPOSITORY,
            )
        except approver.SyntheticApprovalError as exc:
            require("requires Vincent's real validation" in str(exc), str(exc))
        else:
            raise AssertionError("NSC-042 reached synthetic evidence processing")
    finally:
        approver.repo_root = original_root
        approver._require_private_rehearsal = original_preflight
        approver.GhIssueBackend = original_backend
    require(touched == [], str(touched))


def test_cli_process_all_delegates_transitions_to_one_item_api() -> None:
    source = inspect.getsource(approver.main)
    require("process_one_synthetic_handoff(" in source, source)
    require("_apply_automated_validation(" not in source, source)
    require("_apply_automated_decomposition(" not in source, source)


def test_reusable_processor_opens_one_session_and_keeps_one_item_boundary() -> None:
    opened: list[dict[str, object]] = []
    processed: list[dict[str, object]] = []
    session = object()
    original_open = approver._open_synthetic_approver_session
    original_process = approver.process_one_synthetic_handoff

    def fake_open(**values):
        opened.append(values)
        return session

    def fake_process(task_id, **values):
        processed.append({"task_id": task_id, **values})
        return SyntheticEvidencePumpResult(task_id, "d" * 64, "e" * 64)

    approver._open_synthetic_approver_session = fake_open
    approver.process_one_synthetic_handoff = fake_process
    try:
        processor = approver.SyntheticHandoffProcessor(
            source=ROOT,
            checkout_root=ROOT.parent,
            confirm_repository=approver.AUTOMATED_VALIDATION_REPOSITORY,
        )
        first = processor.process_one("NSC-911")
        second = processor.process_one("NSC-912")
    finally:
        approver._open_synthetic_approver_session = original_open
        approver.process_one_synthetic_handoff = original_process

    require(len(opened) == 1, f"repository session was reopened: {opened}")
    require([item["task_id"] for item in processed] == ["NSC-911", "NSC-912"], str(processed))
    require(all(item["_session"] is session for item in processed), str(processed))
    require(all(item["apply"] is True for item in processed), str(processed))
    require(first.task_id == "NSC-911" and second.task_id == "NSC-912", "wrong result")


def main() -> int:
    tests = (
        test_only_exact_direct_gauntlet_provenance_is_accepted,
        test_private_rehearsal_preflight_refuses_public_and_production,
        test_exact_editmode_filter_is_used_before_approval,
        test_historical_runner_evidence_survives_controller_runner_drift_without_execution,
        test_controller_runner_tree_is_derived_from_the_captured_commit,
        test_runner_drift_fallback_executes_controller_b_and_binds_its_source_identity,
        test_wrong_actual_checkout_branch_is_rejected_before_reuse_or_execution,
        test_task_local_runner_edit_cannot_forge_historical_runner_provenance,
        test_reintegrated_handoff_runner_is_proven_from_its_ordered_main_parent,
        test_decomposition_requires_fresh_exact_disjoint_partition,
        test_decomposition_uses_agent_evidence_and_pokes_the_architect,
        test_implementation_uses_agent_evidence_and_pokes_the_architect,
        test_main_processes_every_current_synthetic_issue_serially,
        test_process_one_returns_exact_implementation_event_identity,
        test_process_one_returns_exact_decomposition_event_identity,
        test_source_move_after_validation_prevents_issue_mutation,
        test_process_one_repository_refusal_precedes_issue_access,
        test_process_one_refuses_nsc_042_before_repository_or_issue_access,
        test_cli_process_all_delegates_transitions_to_one_item_api,
        test_reusable_processor_opens_one_session_and_keeps_one_item_boundary,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"synthetic gauntlet approver tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    raise SystemExit(run_with_synthetic_authority(main))
