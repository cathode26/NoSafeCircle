from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
ROOT = PIPELINE.parent
for module_root in (str(ROOT), str(PIPELINE), str(HERE)):
    if module_root not in sys.path:
        sys.path.insert(0, module_root)

import apply_graph_delta as apply_module
from TaskDecomposition.policy import validate_decomposition_result
from TaskDecomposition.tests.decomposition_contracts_smoke_test import (
    decomposed_result,
)
from apply_graph_delta import (
    GraphApplyInputError,
    GraphApplyRepositoryError,
    GraphApplyRollbackError,
    GraphApplyValidationSummary,
    apply_graph_delta,
    inspect_graph_delta_replay,
)
from decomposition_graph_semantics import validate_decomposition_graph_semantics
from graph_apply_materialize import (
    GraphApplyPublicationBoundary,
    materialize_graph_apply,
)
from graph_apply_materialize_smoke_test import EXPECTED_PUBLICATION_ORDER
from graph_delta import GraphDeltaPlan, plan_graph_delta, semantic_json_sha256
from graph_delta_smoke_test import make_plan, task, validated_result
from persistent_work_graph import PersistentWorkGraph, load_persistent_work_graph
from work_graph_persist import canonical_json_text, persist_work_graph, sha256_bytes
from work_graph_transform import WorkGraphPlan
from work_graph_validate import validate_work_graph_plan


APPROVED_NAME = "No Safe Circle TaskReviewAgent"
APPROVED_EMAIL = "task-review-agent@nosafecircle.invalid"
FIXTURE_NAME = "D1C Disposable Fixture"
FIXTURE_EMAIL = "d1c-fixture@nosafecircle.invalid"
UNRELATED_TRACKED_PATH = "FixtureUnrelated.txt"
_GIT_CONFIG_COMMAND_OVERRIDE_RE = re.compile(
    r"^GIT_CONFIG_(?:KEY|VALUE)_[0-9]+$"
)


@dataclass(frozen=True)
class Fixture:
    root: Path
    source: PersistentWorkGraph
    decomposition_result: object
    selector: object
    stored_plan: GraphDeltaPlan
    initial_head: str


def git(
    root: Path,
    *args: str,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> str:
    effective_environment = sanitized_test_environment()
    if environment is not None:
        effective_environment.update(environment)
    for name in tuple(effective_environment):
        if (
            name in {"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
            or _GIT_CONFIG_COMMAND_OVERRIDE_RE.fullmatch(name) is not None
        ):
            effective_environment.pop(name, None)
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=effective_environment,
    )
    stdout = result.stdout.decode("utf-8", "replace").strip()
    stderr = result.stderr.decode("utf-8", "replace").strip()
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed with exit {result.returncode}\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
    return stdout


def commit_count(root: Path) -> int:
    return int(git(root, "rev-list", "--count", "HEAD"))


def status(root: Path) -> str:
    return git(root, "status", "--short", "--untracked-files=all")


def index_paths(root: Path) -> tuple[str, ...]:
    output = git(root, "diff", "--cached", "--name-only")
    return tuple(line for line in output.splitlines() if line)


def worktree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def repository_bytes_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    assert type(value) is dict, path
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(canonical_json_text(value), encoding="utf-8", newline="\n")


def graph_snapshot(graph: PersistentWorkGraph) -> str:
    plan = graph.plan
    return json.dumps(
        {
            "id_map": plan.id_map,
            "tasks": list(plan.tasks),
            "resource_groups": list(plan.resource_groups),
            "project_requirements": list(plan.project_requirements),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def initialize_repository(root: Path, source_plan: WorkGraphPlan) -> str:
    git(root, "init")
    # Fixture commands run with command-scope GIT_CONFIG_* overrides removed, so
    # this disposable repo's LF-only intent cannot be superseded by the container.
    git(root, "config", "core.autocrlf", "false")
    git(root, "config", "user.name", FIXTURE_NAME)
    git(root, "config", "user.email", FIXTURE_EMAIL)
    inputs = SimpleNamespace(
        approved_by="Synthetic Slice 3 fixture",
        source_reconciliation_run_id="synthetic-reconciliation",
        verification_run_id="synthetic-verification",
    )
    (root / "Pipeline" / "TaskGraph").mkdir(parents=True)
    persist_work_graph(source_plan, inputs, root=root)
    (root / UNRELATED_TRACKED_PATH).write_text(
        "Disposable repository control file.\n",
        encoding="utf-8",
        newline="\n",
    )
    git(
        root,
        "add",
        "--",
        "Tasks",
        "Pipeline/TaskGraph",
        UNRELATED_TRACKED_PATH,
    )
    git(root, "commit", "--no-gpg-sign", "-m", "fixture: persistent graph source")
    assert status(root) == ""
    assert index_paths(root) == ()
    return git(root, "rev-parse", "HEAD")


def create_fixture(
    root: Path,
    *,
    source_plan: WorkGraphPlan | None = None,
) -> Fixture:
    plan = source_plan or make_plan()
    validate_work_graph_plan(plan)
    validate_decomposition_graph_semantics(plan)
    initial_head = initialize_repository(root, plan)
    source = load_persistent_work_graph(root)
    result = validated_result(source.plan)
    selector = result.parent_task
    stored = plan_graph_delta(source, selector, result)
    return Fixture(
        root=root,
        source=source,
        decomposition_result=result,
        selector=selector,
        stored_plan=stored,
        initial_head=initial_head,
    )


def commit_fixture_change(root: Path, message: str, *paths: str) -> str:
    git(root, "add", "--", *paths)
    git(root, "commit", "--no-gpg-sign", "-m", message)
    assert status(root) == ""
    assert index_paths(root) == ()
    return git(root, "rev-parse", "HEAD")


def apply_fixture(fixture: Fixture, **seams):
    return apply_graph_delta(
        fixture.root,
        fixture.selector,
        fixture.decomposition_result,
        fixture.stored_plan,
        **seams,
    )


def assert_no_new_commit(root: Path, expected_head: str, expected_count: int) -> None:
    assert git(root, "rev-parse", "HEAD") == expected_head
    assert commit_count(root) == expected_count


def assert_rejected_before_mutation(callable_, root: Path, expected_head: str) -> None:
    count = commit_count(root)
    before = worktree_snapshot(root)
    try:
        callable_()
    except GraphApplyRepositoryError:
        pass
    else:
        raise AssertionError("Expected GraphApplyRepositoryError.")
    assert_no_new_commit(root, expected_head, count)
    assert worktree_snapshot(root) == before


def approved_identity_environment():
    environment = sanitized_test_environment()
    environment.pop("NSC_AGENT_GIT_NAME", None)
    environment.pop("NSC_AGENT_GIT_EMAIL", None)
    return patch.dict(os.environ, environment, clear=True)


def sanitized_test_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name in {"GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"}
            or _GIT_CONFIG_COMMAND_OVERRIDE_RE.fullmatch(name) is not None
        ):
            environment.pop(name, None)
    return environment


def sanitized_git_config_environment():
    return patch.dict(os.environ, sanitized_test_environment(), clear=True)


def verify_fresh_apply_and_exact_replay() -> tuple[str, tuple[str, ...], dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-fresh-") as temporary:
        fixture = create_fixture(Path(temporary))
        initial_count = commit_count(fixture.root)
        source_before = graph_snapshot(fixture.source)
        result_before = fixture.decomposition_result.canonical_json()
        selector_before = fixture.selector.to_dict()
        stored_before = fixture.stored_plan.canonical_json()
        real_planner = apply_module.plan_graph_apply

        with (
            approved_identity_environment(),
            patch.object(
                apply_module,
                "plan_graph_apply",
                wraps=real_planner,
            ) as planner,
        ):
            applied = apply_fixture(fixture)

        assert applied.status == "applied"
        assert applied.failure_phase == "none"
        assert applied.plan_id == fixture.stored_plan.plan_id
        assert applied.parent_task_id == "NSC-042"
        assert applied.old_head == fixture.initial_head
        assert applied.current_head == applied.new_commit_sha
        assert applied.failed_commit_sha is None
        assert applied.committed_paths == EXPECTED_PUBLICATION_ORDER
        assert applied.published_paths == EXPECTED_PUBLICATION_ORDER
        assert applied.failed_authorities == ()
        assert applied.validation is not None
        assert applied.validation.head_commit == applied.new_commit_sha
        assert applied.validation.exact_reviewed_plan
        assert applied.validation.decomposition_semantics == "valid"
        assert applied.validation.clean_worktree
        assert planner.call_count == 1
        assert planner.call_args.args[1] is fixture.selector
        assert planner.call_args.args[2] is fixture.decomposition_result
        assert planner.call_args.args[3] is fixture.stored_plan

        new_commit = applied.new_commit_sha
        assert new_commit is not None
        assert commit_count(fixture.root) == initial_count + 1
        assert git(fixture.root, "rev-list", "--count", f"{fixture.initial_head}..{new_commit}") == "1"
        assert git(fixture.root, "rev-parse", f"{new_commit}^") == fixture.initial_head
        committed = tuple(
            line
            for line in git(
                fixture.root,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                new_commit,
            ).splitlines()
            if line
        )
        assert set(committed) == set(EXPECTED_PUBLICATION_ORDER)

        identity = git(
            fixture.root,
            "show",
            "-s",
            "--format=%an%n%ae%n%cn%n%ce%n%B",
            new_commit,
        ).splitlines()
        assert identity[:4] == [
            APPROVED_NAME,
            APPROVED_EMAIL,
            APPROVED_NAME,
            APPROVED_EMAIL,
        ]
        assert identity[4] == (
            f"taskgraph: apply NSC-042 decomposition {fixture.stored_plan.plan_id}"
        )
        assert APPROVED_EMAIL.endswith(".invalid")
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()

        committed_graph = load_persistent_work_graph(fixture.root)
        summary = validate_work_graph_plan(committed_graph.plan)
        validate_decomposition_graph_semantics(committed_graph.plan)
        assert summary.task_count == 7
        assert applied.validation.task_count == summary.task_count
        children = fixture.stored_plan.proposed_child_contracts
        for expected_child in children:
            current_child = committed_graph.tasks_by_id[expected_child["id"]]
            assert current_child["provenance"]["graph_delta_plan_id"] == applied.plan_id
            assert current_child["provenance"]["parent_task_id"] == "NSC-042"

        assert graph_snapshot(fixture.source) == source_before
        assert fixture.decomposition_result.canonical_json() == result_before
        assert fixture.selector.to_dict() == selector_before
        assert fixture.stored_plan.canonical_json() == stored_before

        before_replay = worktree_snapshot(fixture.root)
        before_replay_repository_bytes = repository_bytes_snapshot(fixture.root)
        replay_count = commit_count(fixture.root)
        with (
            approved_identity_environment(),
            patch.object(
                apply_module,
                "plan_graph_apply",
                side_effect=AssertionError(
                    "already-applied replay reached normal Slice 1 preflight"
                ),
            ) as forbidden_planner,
        ):
            replay = apply_fixture(fixture)
        forbidden_planner.assert_not_called()
        assert replay.status == "already_applied"
        assert replay.plan_id == fixture.stored_plan.plan_id
        assert replay.current_head == new_commit
        assert replay.old_head == new_commit
        assert replay.new_commit_sha is None
        assert replay.committed_paths == ()
        assert replay.published_paths == ()
        assert commit_count(fixture.root) == replay_count
        assert worktree_snapshot(fixture.root) == before_replay
        assert repository_bytes_snapshot(fixture.root) == before_replay_repository_bytes
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()

        hashes = {
            path: sha256_bytes((fixture.root / path).read_bytes())
            for path in EXPECTED_PUBLICATION_ORDER
        }
        return (
            git(fixture.root, "rev-parse", "HEAD^{tree}"),
            applied.committed_paths,
            hashes,
        )


def mutate_applied_fixture(
    root: Path,
    mutation: str,
) -> tuple[Fixture, str, int]:
    fixture = create_fixture(root)
    with approved_identity_environment():
        applied = apply_fixture(fixture)
    assert applied.status == "applied"
    assert applied.new_commit_sha is not None

    first_child = fixture.stored_plan.proposed_child_contracts[0]["id"]
    if mutation == "missing_child":
        relative = f"Tasks/{first_child}.yaml"
        (root / relative).unlink()
        changed = (relative,)
    elif mutation == "wrong_plan_id":
        relative = f"Tasks/{first_child}.yaml"
        child = json_object(root / relative)
        child["provenance"]["graph_delta_plan_id"] = "GDP-" + ("f" * 64)
        write_json(root / relative, child)
        changed = (relative,)
    elif mutation == "incomplete_parent_children":
        relative = "Tasks/NSC-042.yaml"
        parent = json_object(root / relative)
        parent["decomposition_children"] = parent["decomposition_children"][1:]
        write_json(root / relative, parent)
        changed = (relative,)
    elif mutation == "dependent_retains_parent":
        relative = "Tasks/NSC-030.yaml"
        dependent = json_object(root / relative)
        dependent["depends_on"] = ["NSC-042"]
        write_json(root / relative, dependent)
        changed = (relative,)
    else:
        raise AssertionError(f"Unknown mutation: {mutation}")
    head = commit_fixture_change(root, f"fixture: {mutation}", *changed)
    return fixture, head, commit_count(root)


def verify_incomplete_replays_never_report_success() -> None:
    expected_outcomes = {
        "missing_child": ("source_graph_invalid", "replay_validation"),
        "wrong_plan_id": ("stale_proposal", "fresh_preflight"),
        "incomplete_parent_children": (
            "source_graph_invalid",
            "replay_validation",
        ),
        "dependent_retains_parent": (
            "source_graph_invalid",
            "replay_validation",
        ),
    }
    for mutation, expected in expected_outcomes.items():
        with tempfile.TemporaryDirectory(prefix=f"d1c-slice3-{mutation}-") as temporary:
            fixture, head, count = mutate_applied_fixture(Path(temporary), mutation)
            with (
                approved_identity_environment(),
                patch.object(
                    apply_module,
                    "plan_graph_apply",
                    side_effect=AssertionError(
                        "partial/stale replay reached normal Slice 1 preflight"
                    ),
                ) as forbidden_planner,
            ):
                result = apply_fixture(fixture)
            forbidden_planner.assert_not_called()
            assert (result.status, result.failure_phase) == expected, mutation
            assert_no_new_commit(fixture.root, head, count)


def verify_invalid_source_graph_is_distinct() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-source-invalid-") as temporary:
        fixture = create_fixture(Path(temporary))
        id_map_path = fixture.root / "Pipeline" / "TaskGraph" / "WORK_ID_MAP.json"
        id_map_path.write_text("{ invalid current graph\n", encoding="utf-8", newline="\n")
        invalid_head = commit_fixture_change(
            fixture.root,
            "fixture: invalid committed persistent graph",
            "Pipeline/TaskGraph/WORK_ID_MAP.json",
        )
        count = commit_count(fixture.root)
        before = worktree_snapshot(fixture.root)
        with (
            approved_identity_environment(),
            patch.object(
                apply_module,
                "materialize_graph_apply",
                side_effect=AssertionError("invalid source reached materialization"),
            ) as forbidden_materialize,
        ):
            result = apply_fixture(fixture)
        forbidden_materialize.assert_not_called()
        assert result.status == "source_graph_invalid"
        assert result.failure_phase == "replay_validation"
        assert "no fresh preflight or mutation ran" in result.reason
        assert_no_new_commit(fixture.root, invalid_head, count)
        assert worktree_snapshot(fixture.root) == before
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()


def verify_stale_and_recompute_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-stale-") as temporary:
        fixture = create_fixture(Path(temporary))
        parent_path = fixture.root / "Tasks" / "NSC-042.yaml"
        parent = json_object(parent_path)
        parent["title"] = "Changed after independent review"
        write_json(parent_path, parent)
        changed_head = commit_fixture_change(
            fixture.root,
            "fixture: stale reviewed parent",
            "Tasks/NSC-042.yaml",
        )
        count = commit_count(fixture.root)
        with (
            approved_identity_environment(),
            patch.object(
                apply_module,
                "plan_graph_apply",
                side_effect=AssertionError("stale source reached Slice 1 recomputation"),
            ) as forbidden_planner,
        ):
            stale = apply_fixture(fixture)
        forbidden_planner.assert_not_called()
        assert stale.status == "stale_proposal"
        assert "neither the original reviewed source" in stale.reason
        assert_no_new_commit(fixture.root, changed_head, count)
        assert status(fixture.root) == ""

        current_graph = load_persistent_work_graph(fixture.root)
        current_parent = current_graph.tasks_by_id["NSC-042"]
        reconstructed_selector = {
            "task_id": current_parent["id"],
            "contract_revision": current_parent["contract_revision"],
            "contract_sha256": semantic_json_sha256(current_parent),
        }
        try:
            apply_graph_delta(
                fixture.root,
                reconstructed_selector,
                fixture.decomposition_result,
                fixture.stored_plan,
            )
        except GraphApplyInputError as exc:
            assert "planning-time selector" in str(exc)
        else:
            raise AssertionError("Current-parent selector bypassed stored selector authority.")
        assert_no_new_commit(fixture.root, changed_head, count)

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-mismatch-") as temporary:
        fixture = create_fixture(Path(temporary))
        payload = fixture.stored_plan.to_dict()
        payload["parent_after_hash"] = "f" * 64
        tampered = GraphDeltaPlan.from_payload(payload)
        count = commit_count(fixture.root)
        with approved_identity_environment():
            mismatch = apply_graph_delta(
                fixture.root,
                fixture.selector,
                fixture.decomposition_result,
                tampered,
            )
        assert mismatch.status == "recompute_mismatch"
        assert mismatch.failed_authorities == ("graph_delta_canonical_json",)
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert status(fixture.root) == ""


def verify_expected_head_fence() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-expected-head-") as temporary:
        fixture = create_fixture(Path(temporary))
        with approved_identity_environment():
            applied = apply_fixture(fixture, expected_head=fixture.initial_head)
        assert applied.status == "applied"
        assert applied.old_head == fixture.initial_head

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-head-mismatch-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)
        before = worktree_snapshot(fixture.root)
        try:
            with approved_identity_environment():
                apply_fixture(fixture, expected_head="0" * 40)
        except GraphApplyRepositoryError as exc:
            assert "expected_head" in str(exc)
            assert fixture.initial_head in str(exc)
        else:
            raise AssertionError("Mismatched expected_head was accepted.")
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert worktree_snapshot(fixture.root) == before

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-head-moved-") as temporary:
        fixture = create_fixture(Path(temporary))
        unrelated = fixture.root / UNRELATED_TRACKED_PATH
        unrelated.write_text(
            "Docs-only unrelated evolution.\n",
            encoding="utf-8",
            newline="\n",
        )
        moved_head = commit_fixture_change(
            fixture.root,
            "docs: unrelated repository evolution",
            UNRELATED_TRACKED_PATH,
        )
        count = commit_count(fixture.root)
        before = worktree_snapshot(fixture.root)
        try:
            with approved_identity_environment():
                apply_fixture(fixture, expected_head=fixture.initial_head)
        except GraphApplyRepositoryError as exc:
            assert fixture.initial_head in str(exc)
            assert moved_head in str(exc)
        else:
            raise AssertionError("Moved HEAD bypassed caller authorization.")
        assert_no_new_commit(fixture.root, moved_head, count)
        assert worktree_snapshot(fixture.root) == before

        with approved_identity_environment():
            standalone = apply_fixture(fixture)
        assert standalone.status == "applied"
        assert standalone.old_head == moved_head


def verify_git_preconditions() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-dirty-tracked-") as temporary:
        fixture = create_fixture(Path(temporary))
        path = fixture.root / "Tasks" / "NSC-010.yaml"
        path.write_bytes(path.read_bytes() + b"\n")
        assert_rejected_before_mutation(
            lambda: apply_fixture(fixture),
            fixture.root,
            fixture.initial_head,
        )

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-untracked-") as temporary:
        fixture = create_fixture(Path(temporary))
        (fixture.root / "unexpected.txt").write_text(
            "untracked\n", encoding="utf-8", newline="\n"
        )
        assert_rejected_before_mutation(
            lambda: apply_fixture(fixture),
            fixture.root,
            fixture.initial_head,
        )

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-staged-") as temporary:
        fixture = create_fixture(Path(temporary))
        path = fixture.root / "Tasks" / "NSC-010.yaml"
        task_payload = json_object(path)
        task_payload["title"] = "Staged unrelated edit"
        write_json(path, task_payload)
        git(fixture.root, "add", "--", "Tasks/NSC-010.yaml")
        assert index_paths(fixture.root) == ("Tasks/NSC-010.yaml",)
        assert_rejected_before_mutation(
            lambda: apply_fixture(fixture),
            fixture.root,
            fixture.initial_head,
        )
        assert index_paths(fixture.root) == ("Tasks/NSC-010.yaml",)


def verify_materialization_failures_never_commit() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-prepublish-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)

        def fail_before_publication(slice1_result, root):
            def hook(boundary: GraphApplyPublicationBoundary) -> None:
                if boundary.phase == "before_publication":
                    raise RuntimeError("injected Slice 2 pre-publication failure")

            return materialize_graph_apply(
                slice1_result,
                root,
                publication_boundary_hook=hook,
            )

        with approved_identity_environment():
            result = apply_fixture(
                fixture,
                materialize_operation=fail_before_publication,
            )
        assert result.status == "materialization_failed"
        assert result.failure_phase == "materialization"
        assert result.published_paths == ()
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-midpublish-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)

        def fail_after_first_replacement(slice1_result, root):
            def hook(boundary: GraphApplyPublicationBoundary) -> None:
                if (
                    boundary.phase == "after_replacement"
                    and boundary.replacements_completed == 1
                ):
                    raise RuntimeError("injected Slice 2 mid-publication failure")

            return materialize_graph_apply(
                slice1_result,
                root,
                publication_boundary_hook=hook,
            )

        with approved_identity_environment():
            result = apply_fixture(
                fixture,
                materialize_operation=fail_after_first_replacement,
            )
        first_path = EXPECTED_PUBLICATION_ORDER[0]
        assert result.status == "materialization_failed"
        assert result.failure_phase == "materialization"
        assert result.published_paths == (first_path,)
        assert (fixture.root / first_path).is_file()
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert first_path in status(fixture.root)
        assert index_paths(fixture.root) == ()


def verify_false_validator_authority_rolls_back() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-false-validator-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)

        def false_authority_summary(
            root: Path,
            stored: GraphDeltaPlan,
            commit: str,
        ) -> GraphApplyValidationSummary:
            assert stored is fixture.stored_plan
            assert git(root, "rev-parse", "HEAD") == commit
            return GraphApplyValidationSummary(
                head_commit=commit,
                graph_semantic_hash="0" * 64,
                task_count=0,
                parent_edge_count=0,
                dependency_edge_count=0,
                resource_group_count=0,
                project_requirement_count=0,
                task_schema_version="fabricated",
                decomposition_semantics="invalid",
                exact_reviewed_plan=False,
                clean_worktree=False,
            )

        with approved_identity_environment():
            result = apply_fixture(
                fixture,
                post_commit_validator=false_authority_summary,
            )
        assert result.status == "post_commit_validation_failed"
        assert result.failure_phase == "post_commit_validation"
        assert "contradicts required D1C authority" in result.reason
        assert "exact_reviewed_plan=False" in result.reason
        assert "clean_worktree=False" in result.reason
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()
        for child_id in ("NSC-043", "NSC-044"):
            assert not (fixture.root / "Tasks" / f"{child_id}.yaml").exists()

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-forged-validator-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)

        def forged_success_summary(
            root: Path,
            stored: GraphDeltaPlan,
            commit: str,
        ) -> GraphApplyValidationSummary:
            return GraphApplyValidationSummary(
                head_commit=commit,
                graph_semantic_hash=stored.to_dict()["proposed_graph_semantic_hash"],
                task_count=-1,
                parent_edge_count=-1,
                dependency_edge_count=-1,
                resource_group_count=-1,
                project_requirement_count=-1,
                task_schema_version="fabricated",
                decomposition_semantics="valid",
                exact_reviewed_plan=True,
                clean_worktree=True,
            )

        with approved_identity_environment():
            result = apply_fixture(
                fixture,
                post_commit_validator=forged_success_summary,
            )
        assert result.status == "post_commit_validation_failed"
        assert "differs from independent default" in result.reason
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert status(fixture.root) == ""


def verify_concurrent_work_refuses_destructive_rollback() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-rollback-tracked-") as temporary:
        fixture = create_fixture(Path(temporary))
        initial_count = commit_count(fixture.root)
        unrelated = fixture.root / UNRELATED_TRACKED_PATH
        concurrent_bytes = b"Concurrent actor tracked edit.\r\nPreserve exactly.\r\n"

        def fail_after_tracked_edit(
            root: Path,
            stored: GraphDeltaPlan,
            commit: str,
        ) -> GraphApplyValidationSummary:
            assert stored is fixture.stored_plan
            assert git(root, "rev-parse", "HEAD") == commit
            unrelated.write_bytes(concurrent_bytes)
            raise RuntimeError("injected failure after concurrent tracked edit")

        try:
            with approved_identity_environment():
                apply_fixture(
                    fixture,
                    post_commit_validator=fail_after_tracked_edit,
                )
        except GraphApplyRollbackError as exc:
            assert exc.pre_apply_head == fixture.initial_head
            assert exc.failed_commit_sha != fixture.initial_head
            assert fixture.initial_head in str(exc)
            assert exc.failed_commit_sha in str(exc)
            assert "SEVERE" in str(exc)
            assert "concurrent" in str(exc).lower()
            assert UNRELATED_TRACKED_PATH in exc.diagnostics
            assert git(fixture.root, "rev-parse", "HEAD") == exc.failed_commit_sha
            assert commit_count(fixture.root) == initial_count + 1
            assert unrelated.read_bytes() == concurrent_bytes
            assert UNRELATED_TRACKED_PATH in status(fixture.root)
            assert index_paths(fixture.root) == ()
        else:
            raise AssertionError("Concurrent tracked work did not block destructive rollback.")

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-rollback-untracked-") as temporary:
        fixture = create_fixture(Path(temporary))
        concurrent = fixture.root / "ConcurrentUntracked.txt"
        concurrent_bytes = b"Concurrent actor untracked work.\n"

        def fail_after_untracked_write(
            root: Path,
            stored: GraphDeltaPlan,
            commit: str,
        ) -> GraphApplyValidationSummary:
            concurrent.write_bytes(concurrent_bytes)
            raise RuntimeError("injected failure after concurrent untracked write")

        try:
            with approved_identity_environment():
                apply_fixture(
                    fixture,
                    post_commit_validator=fail_after_untracked_write,
                )
        except GraphApplyRollbackError as exc:
            assert git(fixture.root, "rev-parse", "HEAD") == exc.failed_commit_sha
            assert concurrent.read_bytes() == concurrent_bytes
            assert "ConcurrentUntracked.txt" in status(fixture.root)
        else:
            raise AssertionError("Concurrent untracked work did not block rollback.")


def verify_post_commit_rollback_and_severe_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-rollback-") as temporary:
        fixture = create_fixture(Path(temporary))
        count = commit_count(fixture.root)
        observed_failed_commit: list[str] = []

        def fail_validation(root: Path, stored: GraphDeltaPlan, commit: str):
            assert stored is fixture.stored_plan
            assert git(root, "rev-parse", "HEAD") == commit
            assert git(root, "rev-parse", f"{commit}^") == fixture.initial_head
            observed_failed_commit.append(commit)
            raise RuntimeError("injected post-commit validation failure")

        with approved_identity_environment():
            result = apply_fixture(
                fixture,
                post_commit_validator=fail_validation,
            )
        assert result.status == "post_commit_validation_failed"
        assert result.failure_phase == "post_commit_validation"
        assert result.failed_commit_sha == observed_failed_commit[0]
        assert result.new_commit_sha is None
        assert result.current_head == fixture.initial_head
        assert_no_new_commit(fixture.root, fixture.initial_head, count)
        assert status(fixture.root) == ""
        assert index_paths(fixture.root) == ()
        for child_id in ("NSC-043", "NSC-044"):
            assert not (fixture.root / "Tasks" / f"{child_id}.yaml").exists()
        git(
            fixture.root,
            "cat-file",
            "-e",
            f"{result.failed_commit_sha}^{{commit}}",
        )

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-rollback-fail-") as temporary:
        fixture = create_fixture(Path(temporary))

        def fail_validation(root: Path, stored: GraphDeltaPlan, commit: str):
            raise RuntimeError("injected committed validation failure")

        def fail_rollback(root: Path, old_head: str, failed_commit: str) -> None:
            assert old_head == fixture.initial_head
            assert git(root, "rev-parse", "HEAD") == failed_commit
            raise RuntimeError("injected rollback mechanism failure")

        try:
            with approved_identity_environment():
                apply_fixture(
                    fixture,
                    post_commit_validator=fail_validation,
                    rollback_operation=fail_rollback,
                )
        except GraphApplyRollbackError as exc:
            assert exc.pre_apply_head == fixture.initial_head
            assert exc.failed_commit_sha != fixture.initial_head
            assert "SEVERE" in str(exc)
            assert "rollback" in str(exc).lower()
            assert exc.diagnostics
            assert git(fixture.root, "rev-parse", "HEAD") == exc.failed_commit_sha
            assert status(fixture.root) == ""
            assert index_paths(fixture.root) == ()
        else:
            raise AssertionError("Rollback failure was not surfaced distinctly.")


def two_parent_plan() -> WorkGraphPlan:
    base = make_plan()
    second_parent = task(
        "NSC-040",
        "second-parent",
        "implementation",
        "NSC-001",
        "needs_execution_decomposition",
        "concrete",
    )
    second_dependent = task(
        "NSC-041",
        "second-consumer",
        "implementation",
        "NSC-001",
        "single_agent",
        "concrete",
        dependencies=("NSC-040",),
    )
    tasks = tuple((*deepcopy(base.tasks), second_parent, second_dependent))
    plan = WorkGraphPlan(
        id_map={task_payload["reconciliation_key"]: task_payload["id"] for task_payload in tasks},
        tasks=tasks,
        resource_groups=deepcopy(base.resource_groups),
        project_requirements=deepcopy(base.project_requirements),
    )
    validate_work_graph_plan(plan)
    validate_decomposition_graph_semantics(plan)
    return plan


def second_parent_result(plan: WorkGraphPlan):
    parent = next(task_payload for task_payload in plan.tasks if task_payload["id"] == "NSC-040")
    raw = decomposed_result(parent)
    rename = {
        "runtime-core": "second-runtime-core",
        "runtime-integration": "second-runtime-integration",
    }
    for child in raw["children"]:
        child["local_key"] = rename[child["local_key"]]
        child["local_dependencies"] = [
            rename[value] for value in child["local_dependencies"]
        ]
    for coverage in raw["parent_requirement_coverage"]:
        for target in coverage["child_targets"]:
            target["local_key"] = rename[target["local_key"]]
    raw["inbound_dependency_rewrites"] = [
        {
            "dependent_task_id": "NSC-041",
            "replacement_local_keys": ["second-runtime-integration"],
            "reason": "The second consumer needs the integrated child capability.",
        }
    ]
    return validate_decomposition_result(
        raw,
        parent_task=parent,
        existing_reconciliation_keys=plan.id_map,
    )


def verify_collision_and_fresh_next_id_authority() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-collision-") as temporary:
        fixture = create_fixture(Path(temporary), source_plan=two_parent_plan())
        stale_result_b = second_parent_result(fixture.source.plan)
        stale_plan_b = plan_graph_delta(
            fixture.source,
            stale_result_b.parent_task,
            stale_result_b,
        )
        assert stale_plan_b.allocated_local_key_to_task_id == {
            "second-runtime-core": "NSC-043",
            "second-runtime-integration": "NSC-044",
        }

        with approved_identity_environment():
            applied_a = apply_fixture(fixture)
        assert applied_a.status == "applied"
        assert fixture.stored_plan.allocated_local_key_to_task_id == {
            "runtime-core": "NSC-043",
            "runtime-integration": "NSC-044",
        }
        after_a = load_persistent_work_graph(fixture.root)

        fresh_result_b = second_parent_result(after_a.plan)
        fresh_plan_b = plan_graph_delta(
            after_a,
            fresh_result_b.parent_task,
            fresh_result_b,
        )
        assert fresh_plan_b.allocated_local_key_to_task_id == {
            "second-runtime-core": "NSC-045",
            "second-runtime-integration": "NSC-046",
        }
        assert fresh_plan_b.plan_id != stale_plan_b.plan_id

        head_after_a = git(fixture.root, "rev-parse", "HEAD")
        count_after_a = commit_count(fixture.root)
        with (
            approved_identity_environment(),
            patch.object(
                apply_module,
                "plan_graph_apply",
                side_effect=AssertionError("stale plan B was silently reallocated"),
            ) as forbidden_planner,
        ):
            stale_b = apply_graph_delta(
                fixture.root,
                stale_result_b.parent_task,
                stale_result_b,
                stale_plan_b,
            )
        forbidden_planner.assert_not_called()
        assert stale_b.status == "stale_proposal"
        assert stale_plan_b.allocated_local_key_to_task_id == {
            "second-runtime-core": "NSC-043",
            "second-runtime-integration": "NSC-044",
        }
        assert_no_new_commit(fixture.root, head_after_a, count_after_a)
        assert status(fixture.root) == ""


def verify_no_network_or_remote_git_operation() -> None:
    source = Path(apply_module.__file__).read_text(encoding="utf-8")
    forbidden_import = re.compile(r"^\s*(?:from|import)\s+(?:requests|urllib|http|socket)\b", re.MULTILINE)
    forbidden_git_command = re.compile(
        r"[\"'](?:push|fetch|pull|ls-remote|remote)[\"']"
    )
    assert forbidden_import.search(source) is None
    assert forbidden_git_command.search(source) is None
    assert "github" not in source.casefold()


def verify_read_only_exact_replay_inspection() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-replay-inspection-") as temporary:
        fixture = create_fixture(Path(temporary))
        initial_count = commit_count(fixture.root)
        before = worktree_snapshot(fixture.root)
        fresh = inspect_graph_delta_replay(
            fixture.root,
            fixture.selector,
            fixture.stored_plan,
            expected_head=fixture.initial_head,
        )
        assert fresh.status == "fresh_source"
        assert fresh.current_head == fixture.initial_head
        assert_no_new_commit(fixture.root, fixture.initial_head, initial_count)
        assert worktree_snapshot(fixture.root) == before

        with approved_identity_environment():
            applied = apply_fixture(fixture)
        assert applied.status == "applied"
        applied_head = git(fixture.root, "rev-parse", "HEAD")
        applied_count = commit_count(fixture.root)
        applied_before = worktree_snapshot(fixture.root)
        replay = inspect_graph_delta_replay(
            fixture.root,
            fixture.selector,
            fixture.stored_plan,
            expected_head=applied_head,
        )
        assert replay.status == "already_applied"
        assert replay.plan_id == fixture.stored_plan.plan_id
        assert_no_new_commit(fixture.root, applied_head, applied_count)
        assert worktree_snapshot(fixture.root) == applied_before

        (fixture.root / UNRELATED_TRACKED_PATH).write_text(
            "Later unrelated committed evolution.\n",
            encoding="utf-8",
            newline="\n",
        )
        later_head = commit_fixture_change(
            fixture.root,
            "fixture: unrelated later evolution",
            UNRELATED_TRACKED_PATH,
        )
        later_count = commit_count(fixture.root)
        later_before = worktree_snapshot(fixture.root)
        later = inspect_graph_delta_replay(
            fixture.root,
            fixture.selector,
            fixture.stored_plan,
            expected_head=later_head,
        )
        assert later.status == "already_applied"
        assert_no_new_commit(fixture.root, later_head, later_count)
        assert worktree_snapshot(fixture.root) == later_before

    with tempfile.TemporaryDirectory(prefix="d1c-replay-unrelated-") as temporary:
        fixture = create_fixture(Path(temporary))
        (fixture.root / UNRELATED_TRACKED_PATH).write_text(
            "Unrelated movement before application.\n",
            encoding="utf-8",
            newline="\n",
        )
        moved_head = commit_fixture_change(
            fixture.root,
            "fixture: unrelated movement before D1C",
            UNRELATED_TRACKED_PATH,
        )
        moved_count = commit_count(fixture.root)
        moved_before = worktree_snapshot(fixture.root)
        moved = inspect_graph_delta_replay(
            fixture.root,
            fixture.selector,
            fixture.stored_plan,
            expected_head=moved_head,
        )
        assert moved.status == "fresh_source"
        assert_no_new_commit(fixture.root, moved_head, moved_count)
        assert worktree_snapshot(fixture.root) == moved_before


def verify_exact_default_identity_is_required() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-identity-") as temporary:
        fixture = create_fixture(Path(temporary))
        before = worktree_snapshot(fixture.root)
        with patch.dict(
            os.environ,
            {
                "NSC_AGENT_GIT_NAME": "Different Safe Automation",
                "NSC_AGENT_GIT_EMAIL": "different@nosafecircle.invalid",
            },
            clear=False,
        ):
            try:
                apply_fixture(fixture)
            except GraphApplyRepositoryError as exc:
                assert "exact repository-approved automation identity" in str(exc)
            else:
                raise AssertionError("Non-default commit identity was accepted.")
        assert git(fixture.root, "rev-parse", "HEAD") == fixture.initial_head
        assert worktree_snapshot(fixture.root) == before
        assert status(fixture.root) == ""


def install_executable_hook(fixture: Fixture, hook_name: str) -> Path:
    marker = fixture.root / f"{hook_name}-executed.txt"
    hooks_directory = Path(git(fixture.root, "rev-parse", "--git-path", "hooks"))
    if not hooks_directory.is_absolute():
        hooks_directory = fixture.root / hooks_directory
    hooks_directory.mkdir(parents=True, exist_ok=True)
    hook = hooks_directory / hook_name
    hook.write_text(
        f"#!/bin/sh\nprintf executed > '{marker.as_posix()}'\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    return marker


def verify_commit_stage_hook_detection() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-slice3-no-hooks-") as temporary:
        fixture = create_fixture(Path(temporary))
        with approved_identity_environment():
            result = apply_fixture(fixture)
        assert result.status == "applied"

    for hook_name in ("pre-commit", "post-commit"):
        with tempfile.TemporaryDirectory(
            prefix=f"d1c-slice3-{hook_name}-"
        ) as temporary:
            fixture = create_fixture(Path(temporary))
            marker = install_executable_hook(fixture, hook_name)
            count = commit_count(fixture.root)
            before = worktree_snapshot(fixture.root)
            try:
                with approved_identity_environment():
                    apply_fixture(fixture)
            except GraphApplyRepositoryError as exc:
                assert hook_name in str(exc)
                assert "commit-stage" in str(exc)
            else:
                raise AssertionError(f"Executable {hook_name} hook was bypassed.")
            assert_no_new_commit(fixture.root, fixture.initial_head, count)
            assert worktree_snapshot(fixture.root) == before
            assert not marker.exists()
            assert status(fixture.root) == ""
            assert index_paths(fixture.root) == ()

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-configured-hooks-") as temporary:
        fixture = create_fixture(Path(temporary))
        git(fixture.root, "config", "core.hooksPath", ".git/fixture-policy-hooks")
        marker = install_executable_hook(fixture, "pre-commit")
        try:
            with approved_identity_environment():
                apply_fixture(fixture)
        except GraphApplyRepositoryError as exc:
            assert "pre-commit" in str(exc)
            assert "fixture-policy-hooks" in str(exc)
        else:
            raise AssertionError("Configured core.hooksPath was not inspected.")
        assert git(fixture.root, "rev-parse", "HEAD") == fixture.initial_head
        assert not marker.exists()
        assert status(fixture.root) == ""

    with tempfile.TemporaryDirectory(prefix="d1c-slice3-pre-push-") as temporary:
        fixture = create_fixture(Path(temporary))
        marker = install_executable_hook(fixture, "pre-push")
        with approved_identity_environment():
            result = apply_fixture(fixture)
        assert result.status == "applied"
        assert not marker.exists()
        assert status(fixture.root) == ""


def run_tests() -> int:
    first_signature = verify_fresh_apply_and_exact_replay()
    second_signature = verify_fresh_apply_and_exact_replay()
    assert first_signature == second_signature

    verify_incomplete_replays_never_report_success()
    verify_invalid_source_graph_is_distinct()
    verify_stale_and_recompute_mismatch()
    verify_expected_head_fence()
    verify_git_preconditions()
    verify_materialization_failures_never_commit()
    verify_false_validator_authority_rolls_back()
    verify_concurrent_work_refuses_destructive_rollback()
    verify_post_commit_rollback_and_severe_failure()
    verify_collision_and_fresh_next_id_authority()
    verify_read_only_exact_replay_inspection()
    verify_no_network_or_remote_git_operation()
    verify_exact_default_identity_is_required()
    verify_commit_stage_hook_detection()

    print("graph_apply_smoke_test: PASS")
    return 0


def main() -> int:
    with sanitized_git_config_environment():
        return run_tests()


if __name__ == "__main__":
    raise SystemExit(main())
