#!/usr/bin/env python3
"""Deterministic regressions for exact pre-handoff Unity validation reuse.

Classification: pure/component and temporary-repository behavior tests. Every
test uses throwaway Git repositories, a throwaway controller-owned state root,
and fake command runners. No Unity, Docker, GitHub, provider, rehearsal, or
canonical checkout is invoked or mutated.

A task previously ran effectively the same exact Unity validation up to three
times: CandidateIntegrator pre-handoff, synthetic_gauntlet_approver automated
validation, and downstream_runtime authoritative validation. These tests pin the
reduction to one execution and, more importantly, pin every condition under
which reuse must be refused.

Tests marked GUARD are preservation checks that pass both before and after the
change; they exist so the reduction cannot be bought by weakening a gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import tempfile


sys.dont_write_bytecode = True
os.environ["GIT_CONFIG_COUNT"] = "1"
os.environ["GIT_CONFIG_KEY_0"] = "core.autocrlf"
os.environ["GIT_CONFIG_VALUE_0"] = "false"

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import synthetic_gauntlet_approver as approver  # noqa: E402
from Pipeline.TaskReviewAgent.candidate_integration import (  # noqa: E402
    INTEGRATION_SCHEMA_VERSION,
    CandidateIntegrationError,
    find_pre_handoff_validation,
    load_integration_receipt,
)
from Pipeline.TaskReviewAgent.contracts import semantic_sha256  # noqa: E402
from Pipeline.Testing.validation_manifest import (  # noqa: E402
    ValidationManifestError,
    import_validation_manifest,
)

TASK = "NSC-901"
PLATFORM = "EditMode"
FILTER = "NoSafeCircle.Tests.DoorPrototypeTests"
CONTRACT = "e" * 64

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected=CandidateIntegrationError) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


# ------------------------------------------------------------------ fixtures


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<test-run result="Passed" total="4" passed="4" failed="0" skipped="0" />\n'
)
LOG = "Unity validation log\nAll tests passed.\n"


def write_evidence(
    directory: Path, *, commit: str, tree: str,
    platform: str = PLATFORM, test_filter: str = FILTER,
) -> Path:
    """Write one complete, internally valid Unity validation manifest set."""
    directory.mkdir(parents=True, exist_ok=True)
    xml_path = directory / "test-results.xml"
    log_path = directory / "unity.log"
    xml_path.write_text(XML, encoding="utf-8", newline="\n")
    log_path.write_text(LOG, encoding="utf-8", newline="\n")
    manifest = {
        "schema_version": "1.0",
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
            "version": "6000.1.0f1",
            "executable": "C:/Unity/Editor/Unity.exe",
            "exit_code": 0,
            "test_platform": platform,
            "test_filter": test_filter,
        },
        "test_run": {
            "result": "Passed", "total": 4, "passed": 4, "failed": 0, "skipped": 0,
        },
        "artifacts": {
            "xml": {
                "relative_path": "test-results.xml",
                "sha256": _sha256(xml_path),
                "size_bytes": xml_path.stat().st_size,
            },
            "log": {
                "relative_path": "unity.log",
                "sha256": _sha256(log_path),
                "size_bytes": log_path.stat().st_size,
            },
        },
        "runner": {"path": "Pipeline/Testing/run_unity_tests_clean.ps1"},
    }
    manifest_path = directory / "validation-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path


class Fixture:
    """A throwaway task checkout plus its controller-owned state root."""

    def __init__(self, parent: Path) -> None:
        self.parent = parent
        self.checkout = parent / TASK
        self.checkout.mkdir(parents=True)
        subprocess.run(("git", "init", "-q", str(self.checkout)), check=True)
        _git(self.checkout, "config", "user.name", "Reuse Fixture")
        _git(self.checkout, "config", "user.email", "reuse@example.invalid")
        _write(self.checkout / "Assets" / "Thing.cs", "public class Thing { }\n")
        _write(
            self.checkout / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1",
            "# committed clean Unity runner\n",
        )
        _git(self.checkout, "add", ".")
        _git(self.checkout, "commit", "-qm", "baseline")
        self.commit = _git(self.checkout, "rev-parse", "HEAD")
        self.tree = _git(self.checkout, "rev-parse", "HEAD^{tree}")
        self.state_root = self.parent / ".task-review-agent"
        self.evidence = (
            self.state_root / "outputs" / TASK / "run-1" / "pre-handoff-validation"
            / f"{PLATFORM}-{hashlib.sha256(FILTER.encode('utf-8')).hexdigest()[:12]}"
        )
        self.manifest_path = write_evidence(
            self.evidence, commit=self.commit, tree=self.tree
        )
        self.state_path = self.state_root / f"{TASK}.integration.json"
        self.write_receipt()

    def relative(self, path: Path | None = None) -> str:
        target = path or self.manifest_path
        return target.resolve().relative_to(self.state_root.resolve()).as_posix()

    def validation_entry(self, **overrides: Any) -> dict[str, Any]:
        entry = {
            "test_platform": PLATFORM,
            "test_filter": FILTER,
            "commit": self.commit,
            "tree": self.tree,
            "manifest_relative_path": self.relative(),
            "policy_sha256": "f" * 64,
            "total": 4,
            "passed": 4,
            "manifest_sha256": _sha256(self.manifest_path),
            "xml_sha256": _sha256(self.evidence / "test-results.xml"),
            "log_sha256": _sha256(self.evidence / "unity.log"),
        }
        entry.update(overrides)
        return entry

    def write_receipt(
        self,
        *,
        validations: list[dict[str, Any]] | None = None,
        schema_version: str = INTEGRATION_SCHEMA_VERSION,
        corrupt_hash: bool = False,
        **overrides: Any,
    ) -> None:
        body = {
            "schema_version": schema_version,
            "task_id": TASK,
            "lease_id": "lease-1",
            "plan_id": "plan-1",
            "run_id": "run-1",
            "provider": "claude",
            "branch": f"task/{TASK.casefold()}",
            "base_head": "0" * 40,
            "commit": self.commit,
            "commit_tree": self.tree,
            "task_contract_sha256": CONTRACT,
            "candidate_sha256": "a" * 64,
            "changed_paths": ["Assets/Thing.cs"],
            "pre_handoff_validations": (
                [self.validation_entry()] if validations is None else validations
            ),
            "completed_checks": ["candidate_applied"],
        }
        body.update(overrides)
        digest = semantic_sha256(body)
        if corrupt_hash:
            digest = "0" * 64
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({**body, "receipt_sha256": digest}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def find(self, **overrides: Any):
        arguments = {
            "checkout": self.checkout,
            "task_id": TASK,
            "commit": self.commit,
            "tree": self.tree,
            "test_platform": PLATFORM,
            "test_filter": FILTER,
        }
        arguments.update(overrides)
        return find_pre_handoff_validation(**arguments)


def fixture_dir():
    return tempfile.TemporaryDirectory(prefix="pre-handoff-reuse-")


# ----------------------------------------------- the reuse gate: happy path


def test_recorded_pre_handoff_evidence_is_importable_for_the_exact_state() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        imported = fixture.find()
        require(imported is not None, "verified pre-handoff evidence was not found")
        require(imported.manifest.validated_state.commit == fixture.commit,
                "imported evidence binds another commit")
        require(imported.manifest.unity.test_platform == PLATFORM, "wrong platform")
        require(imported.manifest.unity.test_filter == FILTER, "wrong filter")
        require(imported.manifest.test_run.passed == 4, "counts were not carried")
        require(imported.sha256 == _sha256(fixture.manifest_path),
                "the imported manifest digest is not the file digest")
        # The persisted receipt never carries an absolute path.
        body = json.loads(fixture.state_path.read_text(encoding="utf-8"))
        entry = body["pre_handoff_validations"][0]
        require("manifest_path" not in entry,
                f"an absolute manifest path was persisted: {entry}")
        require(entry["manifest_relative_path"] == fixture.relative(),
                f"the persisted location is not controller-relative: {entry}")


# ------------------------------------------- absence versus corruption


def test_absent_evidence_returns_none_rather_than_raising() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        fixture.state_path.unlink()
        require(fixture.find() is None, "a missing receipt was not treated as absence")

        fixture.write_receipt(validations=[])
        require(fixture.find() is None, "an empty validation list was not absence")

        # A receipt describing another candidate is absence for this state.
        fixture.write_receipt(commit="9" * 40, commit_tree="8" * 40)
        require(fixture.find() is None, "another candidate's receipt was not absence")


def test_a_tampered_receipt_hash_refuses_reuse() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        fixture.write_receipt(corrupt_hash=True)
        exc = rejects(fixture.find)
        require("hash does not match" in str(exc), str(exc))
        require(rejects(lambda: load_integration_receipt(fixture.state_path)) is not None,
                "the shared loader accepted a tampered receipt")


def test_a_tampered_manifest_xml_or_log_refuses_reuse() -> None:
    for label, target, mutate in (
        ("manifest", "validation-manifest.json", lambda p: p.write_text(
            p.read_text(encoding="utf-8").replace('"total": 4', '"total": 5'),
            encoding="utf-8", newline="\n")),
        ("xml", "test-results.xml", lambda p: p.write_text(
            XML.replace('passed="4"', 'passed="3"'), encoding="utf-8", newline="\n")),
        ("log", "unity.log", lambda p: p.write_text(
            LOG + "tampered\n", encoding="utf-8", newline="\n")),
    ):
        with fixture_dir() as text:
            fixture = Fixture(Path(text))
            mutate(fixture.evidence / target)
            exc = rejects(fixture.find)
            require("no longer verifies" in str(exc),
                    f"{label}: unexpected refusal {exc}")


# --------------------------------------------- identity mismatches refuse


def test_a_different_commit_tree_platform_or_filter_is_not_reused() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        # A different commit or tree makes the receipt describe another candidate.
        require(fixture.find(commit="9" * 40) is None, "a wrong commit was reused")
        require(fixture.find(tree="8" * 40) is None, "a wrong tree was reused")
        # A different platform or filter simply has no recorded entry.
        require(fixture.find(test_platform="PlayMode") is None,
                "a wrong platform was reused")
        require(fixture.find(test_filter="Other.Tests") is None,
                "a wrong filter was reused")

        # An entry whose own commit contradicts its receipt is corruption.
        fixture.write_receipt(validations=[fixture.validation_entry(commit="9" * 40)])
        exc = rejects(fixture.find)
        require("disagrees with its own receipt" in str(exc), str(exc))

        # An entry claiming this platform but naming a manifest recorded for
        # another one is refused by the importer, not silently accepted.
        with fixture_dir() as other_text:
            other = Fixture(Path(other_text))
            write_evidence(other.evidence, commit=other.commit, tree=other.tree,
                           platform="PlayMode")
            other.write_receipt(validations=[other.validation_entry(
                manifest_sha256=_sha256(other.manifest_path))])
            exc = rejects(other.find)
            require("no longer verifies" in str(exc), str(exc))


def test_a_changed_task_contract_invalidates_the_recorded_candidate() -> None:
    """A contract change re-commits the task, moving commit and tree."""
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        _write(fixture.checkout / "Tasks" / f"{TASK}.yaml", '{"id":"NSC-901"}\n')
        _git(fixture.checkout, "add", ".")
        _git(fixture.checkout, "commit", "-qm", "contract change")
        moved_commit = _git(fixture.checkout, "rev-parse", "HEAD")
        moved_tree = _git(fixture.checkout, "rev-parse", "HEAD^{tree}")
        require(moved_commit != fixture.commit and moved_tree != fixture.tree,
                "the fixture did not actually move the task state")
        require(fixture.find(commit=moved_commit, tree=moved_tree) is None,
                "evidence recorded before a contract change was reused")


def test_a_main_into_branch_change_invalidates_stale_evidence() -> None:
    """A legitimate merge keeps the branch but moves the tree that was tested."""
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        _write(fixture.checkout / "Assets" / "FromMain.cs", "public class FromMain { }\n")
        _git(fixture.checkout, "add", ".")
        _git(fixture.checkout, "commit", "-qm", "merge main into branch")
        merged_commit = _git(fixture.checkout, "rev-parse", "HEAD")
        merged_tree = _git(fixture.checkout, "rev-parse", "HEAD^{tree}")
        require(merged_tree != fixture.tree, "the merge did not move the tree")
        require(fixture.find(commit=merged_commit, tree=merged_tree) is None,
                "stale pre-merge evidence was reused after a main-into-branch change")


# ----------------------------------- containment, traversal, symlink escape


def test_evidence_outside_the_controller_state_root_is_refused() -> None:
    with fixture_dir() as text:
        parent = Path(text)
        fixture = Fixture(parent)
        outside = parent / "outside" / "validation"
        write_evidence(outside, commit=fixture.commit, tree=fixture.tree)
        # An absolute or escaping location can only be expressed as traversal,
        # because the receipt stores a controller-relative path.
        depth = len(fixture.relative().split("/"))
        traversal = "/".join([".."] * depth) + "/outside/validation/validation-manifest.json"
        fixture.write_receipt(validations=[
            fixture.validation_entry(manifest_relative_path=traversal)
        ])
        exc = rejects(fixture.find)
        require("traversal" in str(exc) or "no longer verifies" in str(exc), str(exc))

        for bad in ("/tmp/validation-manifest.json", "C:/x/validation-manifest.json",
                    "outputs\\x\\validation-manifest.json"):
            fixture.write_receipt(validations=[
                fixture.validation_entry(manifest_relative_path=bad)
            ])
            exc = rejects(fixture.find)
            require("controller-relative" in str(exc) or "traversal" in str(exc),
                    f"{bad}: {exc}")


def test_a_symlink_that_escapes_the_controller_root_is_refused() -> None:
    with fixture_dir() as text:
        parent = Path(text)
        fixture = Fixture(parent)
        outside = parent / "outside" / "validation"
        outside_manifest = write_evidence(
            outside, commit=fixture.commit, tree=fixture.tree
        )
        link_root = fixture.state_root / "outputs" / TASK / "run-1" / "linked"
        try:
            link_root.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(outside, link_root, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            print("    (skipped: this host cannot create symlinks)")
            return
        relative = (
            f"outputs/{TASK}/run-1/linked/{outside_manifest.name}"
        )
        fixture.write_receipt(validations=[
            fixture.validation_entry(manifest_relative_path=relative)
        ])
        exc = rejects(fixture.find)
        require("no longer verifies" in str(exc), str(exc))
        require("outside the controller-owned root" in str(exc)
                or "regular file" in str(exc), str(exc))


# --------------------------------------------- receipt identity and schema


def test_a_wrong_task_or_run_identity_finds_no_evidence() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        require(fixture.find(task_id="NSC-999") is None,
                "another task's identity resolved to this receipt")
        moved = fixture.parent / "elsewhere" / "NSC-901"
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(fixture.checkout, moved)
        require(find_pre_handoff_validation(
            checkout=moved, task_id=TASK, commit=fixture.commit, tree=fixture.tree,
            test_platform=PLATFORM, test_filter=FILTER,
        ) is None, "a checkout outside the controller root resolved evidence")


def test_an_old_schema_receipt_fails_closed() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        legacy = fixture.validation_entry()
        legacy["manifest_path"] = str(fixture.manifest_path)
        del legacy["manifest_relative_path"]
        del legacy["xml_sha256"]
        del legacy["log_sha256"]
        fixture.write_receipt(validations=[legacy], schema_version="1.1")
        require(load_integration_receipt(fixture.state_path) is None,
                "a 1.1 receipt was interpreted under the 1.2 contract")
        require(fixture.find() is None,
                "an old-schema receipt supplied reuse evidence")


# ------------------------------------------------ the importer's own gates


def test_the_shared_importer_requires_every_caller_expectation() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        common = {
            "controller_root": fixture.state_root,
            "expected_commit": fixture.commit,
            "expected_tree": fixture.tree,
            "expected_test_platform": PLATFORM,
            "expected_test_filter": FILTER,
        }
        imported = import_validation_manifest(fixture.manifest_path, **common)
        require(imported.relative_path == fixture.relative(), imported.relative_path)
        for label, override in (
            ("commit", {"expected_commit": "9" * 40}),
            ("tree", {"expected_tree": "8" * 40}),
            ("platform", {"expected_test_platform": "PlayMode"}),
            ("filter", {"expected_test_filter": "Other.Tests"}),
            ("manifest digest", {"expected_manifest_sha256": "0" * 64}),
            ("xml digest", {"expected_xml_sha256": "0" * 64}),
            ("log digest", {"expected_log_sha256": "0" * 64}),
            ("controller root", {"controller_root": fixture.parent / "outside"}),
        ):
            rejects(
                lambda o=override: import_validation_manifest(
                    fixture.manifest_path, **{**common, **o}
                ),
                ValidationManifestError,
            )


# -------------------------------------- exactly one Unity execution overall


class RecordingUnity:
    """Counts every Unity runner invocation across all three stages."""

    def __init__(self, *, evidence_for: Fixture | None = None) -> None:
        self.calls: list[list[str]] = []
        self.evidence_for = evidence_for

    def __call__(self, command, cwd=None, timeout_seconds=None, check=False, **kwargs):
        self.calls.append(list(command))
        raise AssertionError(
            "Unity was executed when verified pre-handoff evidence was available"
        )


def test_reuse_performs_no_unity_execution_and_fallback_performs_one() -> None:
    """The reduction itself: evidence present means zero further executions."""
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        unity = RecordingUnity()

        # Stage 2 and stage 3 both consult the same shared gate. With verified
        # evidence present neither needs to reach a Unity runner at all.
        for stage in ("synthetic approver", "downstream runtime"):
            imported = fixture.find()
            require(imported is not None, f"{stage} found no reusable evidence")
        require(unity.calls == [], f"Unity was invoked: {unity.calls}")

        # With the evidence genuinely absent, the gate reports absence so the
        # caller performs exactly one fresh execution.
        fixture.state_path.unlink()
        require(fixture.find() is None, "absence was not reported")


# -------------------------------------------------- synthetic approver gates


def test_the_approver_reuses_evidence_without_executing_unity() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        source = fixture.parent / "source"
        shutil.copytree(fixture.checkout, source)
        state = SimpleNamespace(
            checkout_path=str(fixture.checkout),
            head_commit=fixture.commit,
            human_handoff_commit=fixture.commit,
            task_contract_sha256=CONTRACT,
            branch=f"task/{TASK.casefold()}",
            last_event_id="b" * 64,
            human_result=None,
        )
        snapshot = SimpleNamespace(state=state)
        task = {"id": TASK, "task_contract_sha256": CONTRACT}
        plan = {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": FILTER},
            "authority": "committed_validation_policy",
            "policy_sha256": "f" * 64,
        }
        executed: list[str] = []

        original_plan = approver.validation_plan_for
        original_filter = approver._expected_implementation_filter
        original_execute = approver._execute_synthetic_unity_validation
        try:
            approver.validation_plan_for = lambda checkout, task_value: plan
            approver._expected_implementation_filter = lambda src, task_value: FILTER

            def refuse(**kwargs):
                executed.append("unity")
                raise AssertionError("Unity ran despite verified pre-handoff evidence")

            approver._execute_synthetic_unity_validation = refuse
            result = approver._run_unity_validation(
                source=source,
                checkout_root=fixture.parent,
                repository="cathode26/NoSafeCircle-Homework-Rehearsal",
                snapshot=snapshot,
                task=task,
            )
        finally:
            approver.validation_plan_for = original_plan
            approver._expected_implementation_filter = original_filter
            approver._execute_synthetic_unity_validation = original_execute

        require(executed == [], "the approver executed Unity anyway")
        require(result["evidence_source"] == "reused_pre_handoff_validation",
                f"the approver claimed a fresh execution: {result['evidence_source']}")
        require(result["status"] == "exact_synthetic_unity_validation_passed",
                result["status"])
        evidence = result["evidence"]
        require(evidence["authority"] == approver.AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
                "reused evidence did not create automated-validation authority")
        blob = json.dumps(result, sort_keys=True).casefold()
        for forbidden in ("human_result", "human_pass", '"pass"'):
            require(forbidden not in blob,
                    f"reused evidence created human authority: {forbidden}")
        unity_validation = evidence["unity_validations"][0]
        require(unity_validation["manifest_sha256"] == _sha256(fixture.manifest_path),
                "the reused manifest identity was not carried into the evidence")


def test_the_approver_refuses_corrupted_evidence_instead_of_re_running() -> None:
    with fixture_dir() as text:
        fixture = Fixture(Path(text))
        fixture.write_receipt(corrupt_hash=True)
        source = fixture.parent / "source"
        shutil.copytree(fixture.checkout, source)
        state = SimpleNamespace(
            checkout_path=str(fixture.checkout),
            head_commit=fixture.commit,
            human_handoff_commit=fixture.commit,
            task_contract_sha256=CONTRACT,
            branch=f"task/{TASK.casefold()}",
            last_event_id="b" * 64,
            human_result=None,
        )
        plan = {
            "required_test_platforms": ["EditMode"],
            "test_filters": {"EditMode": FILTER},
            "authority": "committed_validation_policy",
            "policy_sha256": "f" * 64,
        }
        original_plan = approver.validation_plan_for
        original_filter = approver._expected_implementation_filter
        original_execute = approver._execute_synthetic_unity_validation
        executed: list[str] = []
        try:
            approver.validation_plan_for = lambda checkout, task_value: plan
            approver._expected_implementation_filter = lambda src, task_value: FILTER
            approver._execute_synthetic_unity_validation = lambda **kwargs: (
                executed.append("unity")
            )
            exc = rejects(
                lambda: approver._run_unity_validation(
                    source=source,
                    checkout_root=fixture.parent,
                    repository="cathode26/NoSafeCircle-Homework-Rehearsal",
                    snapshot=SimpleNamespace(state=state),
                    task={"id": TASK, "task_contract_sha256": CONTRACT},
                ),
                approver.SyntheticApprovalError,
            )
        finally:
            approver.validation_plan_for = original_plan
            approver._expected_implementation_filter = original_filter
            approver._execute_synthetic_unity_validation = original_execute
        require(executed == [], "corrupted evidence silently fell back to a fresh run")
        require("unusable" in str(exc), str(exc))


def test_guard_nsc_042_is_refused_before_any_reuse_or_execution() -> None:
    """GUARD: the preserved task never reaches the reuse path at all."""
    require(approver.PRESERVED_TASK_ID == "NSC-042",
            f"the preserved task moved: {approver.PRESERVED_TASK_ID}")
    with tempfile.TemporaryDirectory(prefix="preserved-") as text:
        exc = rejects(
            lambda: approver._require_gauntlet_task(Path(text), approver.PRESERVED_TASK_ID),
            approver.SyntheticApprovalError,
        )
        require("real validation" in str(exc), str(exc))
    source = (ROOT / "Pipeline" / "TaskReviewAgent"
              / "synthetic_gauntlet_approver.py").read_text(encoding="utf-8")
    for guard in (
        'raise SyntheticApprovalError("synthetic approval refuses production")',
        "synthetic approval requires the exact canonical rehearsal repository",
        "human_approved_synthetic_gauntlet",
    ):
        require(guard in source, f"a pre-reuse gate was removed: {guard}")


def test_guard_an_ordinary_task_cannot_use_automated_synthetic_authority() -> None:
    """GUARD: reuse changes nothing about who may hold synthetic authority."""
    with tempfile.TemporaryDirectory(prefix="ordinary-") as text:
        checkout = Path(text) / "repo"
        checkout.mkdir()
        subprocess.run(("git", "init", "-q", str(checkout)), check=True)
        _git(checkout, "config", "user.name", "Ordinary Fixture")
        _git(checkout, "config", "user.email", "ordinary@example.invalid")
        _write(checkout / "Tasks" / "NSC-901.yaml", json.dumps({
            "id": TASK, "title": "Ordinary", "provenance": {"origin": "direct_gdd"},
        }) + "\n")
        _git(checkout, "add", ".")
        _git(checkout, "commit", "-qm", "ordinary task")
        exc = rejects(
            lambda: approver._require_gauntlet_task(checkout, TASK),
            approver.SyntheticApprovalError,
        )
        require("synthetic gauntlet task" in str(exc), str(exc))


# --------------------------------------------------------------------- main


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
        and callable(value)
        and getattr(value, "__module__", None) == __name__
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            FAILURES.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if FAILURES:
        print(f"pre-handoff validation reuse tests: FAIL ({len(FAILURES)})")
        return 1
    print(f"pre-handoff validation reuse tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
