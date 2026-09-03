#!/usr/bin/env python3
"""Deterministic tests for the private 80-task gauntlet bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet as gauntlet  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import unity_meta_bytes  # noqa: E402
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    GAUNTLET_FIRST_ID,
    GAUNTLET_TASK_COUNT,
    PRESERVED_TASK_ID,
    POLICY_RELATIVE,
    ROOT_TASK_ID,
    TEST_FILTER,
    _test_filter,
    apply_bundle,
    build_bundle,
    build_validation_repair_bundle,
)
from persistent_work_graph import load_persistent_work_graph  # noqa: E402
from graph_delta import semantic_json_sha256  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def task(bundle, task_id: str) -> dict:
    return json.loads(bundle[Path("Tasks") / f"{task_id}.yaml"])


def test_bundle_has_eight_dependency_waves_and_mixed_work() -> None:
    bundle, summary = build_bundle(ROOT)
    require(summary["initial_synthetic_tasks"] == 80, str(summary))
    require(summary["dependency_waves"] == 8, str(summary))
    require(len(summary["decomposition_parents"]) == 8, str(summary))
    require(summary["concrete_tasks"] == 72, str(summary))
    first_wave = [task(bundle, f"NSC-{number:03d}") for number in range(911, 921)]
    require(
        sum(item["execution_scope"] == "needs_execution_decomposition" for item in first_wave)
        == 1,
        str(first_wave),
    )
    require(
        sum(item["execution_scope"] == "single_agent" for item in first_wave) == 9,
        str(first_wave),
    )
    require(all(not item["depends_on"] for item in first_wave), str(first_wave))
    second_wave = [task(bundle, f"NSC-{number:03d}") for number in range(921, 931)]
    require(all(item["depends_on"] for item in second_wave), str(second_wave))


def test_old_active_work_is_cancelled_but_root_and_42_remain_active() -> None:
    bundle, _ = build_bundle(ROOT)
    require(task(bundle, ROOT_TASK_ID)["contract_disposition"] == "active", "root inactive")
    preserved = task(bundle, PRESERVED_TASK_ID)
    require(preserved["contract_disposition"] == "active", str(preserved))
    require(preserved["depends_on"] == ["NSC-990"], str(preserved["depends_on"]))
    old = task(bundle, "NSC-002")
    require(old["contract_disposition"] == "cancelled", str(old))
    require("synthetic_gauntlet_retirement" in old["provenance"], str(old))


def test_validation_policy_binds_every_concrete_initial_contract() -> None:
    bundle, summary = build_bundle(ROOT)
    policy = json.loads(bundle[POLICY_RELATIVE])
    expected = {PRESERVED_TASK_ID}
    decomposition = set(summary["decomposition_parents"])
    for number in range(GAUNTLET_FIRST_ID, GAUNTLET_FIRST_ID + GAUNTLET_TASK_COUNT):
        task_id = f"NSC-{number:03d}"
        if task_id not in decomposition:
            expected.add(task_id)
    require(set(policy["tasks"]) == expected, str(set(policy["tasks"]) ^ expected))
    for task_id, entry in policy["tasks"].items():
        data = bundle[Path("Tasks") / f"{task_id}.yaml"]
        require(entry["task_contract_sha256"] == hashlib.sha256(data).hexdigest(), task_id)
        if task_id == PRESERVED_TASK_ID:
            require(entry["test_filters"]["EditMode"] != TEST_FILTER, task_id)
        else:
            require(
                entry["test_filters"]["EditMode"]
                == _test_filter(int(task_id.split("-")[1])),
                task_id,
            )
    require(
        set(policy["decomposition_child_templates"]) == decomposition,
        str(set(policy["decomposition_child_templates"]) ^ decomposition),
    )
    for task_id, entry in policy["decomposition_child_templates"].items():
        require(
            entry["parent_task_contract_sha256"]
            == semantic_json_sha256(task(bundle, task_id)),
            task_id,
        )
        number = int(task_id.split("-")[1])
        variants = entry["validation_variants"]
        require(len(variants) == 2, task_id)
        require(
            {item["test_filters"]["EditMode"] for item in variants}
            == {_test_filter(number, "Alpha"), _test_filter(number, "Beta")},
            task_id,
        )


def test_test_source_has_one_exact_method_per_implementation_child() -> None:
    bundle, _ = build_bundle(ROOT)
    source = bundle[gauntlet.TEST_RELATIVE].decode("utf-8")
    require(source.count("        [Test]") == 88, "expected 88 exact test methods")
    require(_test_filter(912).split(".")[-1] in source, "NSC-912 test missing")
    require(_test_filter(911, "Alpha").split(".")[-1] in source, "Alpha test missing")
    require(_test_filter(911, "Beta").split(".")[-1] in source, "Beta test missing")
    require("EveryPublishedGauntletClass" not in source, "fleet-wide test remains")


def test_every_concrete_task_owns_a_disjoint_source_and_meta_pair() -> None:
    bundle, summary = build_bundle(ROOT)
    seen: set[str] = set()
    decomposition = set(summary["decomposition_parents"])
    for number in range(GAUNTLET_FIRST_ID, GAUNTLET_FIRST_ID + GAUNTLET_TASK_COUNT):
        task_id = f"NSC-{number:03d}"
        current = task(bundle, task_id)
        resources = current["exclusive_resources"]
        expected_count = 4 if task_id in decomposition else 2
        require(len(resources) == expected_count, f"{task_id}: {resources}")
        require(not seen.intersection(resources), f"resource collision at {task_id}")
        seen.update(resources)


def test_task_contract_guids_match_execution_crew_sidecars() -> None:
    bundle, summary = build_bundle(ROOT)
    decomposition = set(summary["decomposition_parents"])
    for number in range(GAUNTLET_FIRST_ID, GAUNTLET_FIRST_ID + GAUNTLET_TASK_COUNT):
        task_id = f"NSC-{number:03d}"
        current = task(bundle, task_id)
        sources = [
            resource.removeprefix("repo-file:")
            for resource in current["exclusive_resources"]
            if resource.endswith(".cs")
        ]
        requirements = "\n".join(
            item["requirement"] for item in current["acceptance_criteria"]
        )
        for source in sources:
            expected_guid = unity_meta_bytes(source).decode("ascii").split("guid: ", 1)[1].strip()
            require(expected_guid in requirements, f"{task_id}: {source}: {requirements}")


def _copy_graph(destination: Path) -> None:
    shutil.copytree(ROOT / "Tasks", destination / "Tasks")
    target = destination / "Pipeline" / "TaskGraph"
    target.mkdir(parents=True)
    for name in (
        "BOOTSTRAP_PERSISTED.json",
        "WORK_ID_MAP.json",
        "PROJECT_REQUIREMENTS.yaml",
        "RESOURCE_GROUPS.yaml",
    ):
        shutil.copy2(ROOT / "Pipeline" / "TaskGraph" / name, target / name)


def test_materialization_validates_and_failure_rolls_back() -> None:
    bundle, _ = build_bundle(ROOT)
    with tempfile.TemporaryDirectory(prefix="synthetic-gauntlet-") as text:
        target = Path(text)
        _copy_graph(target)
        original_run = gauntlet._run
        gauntlet._run = lambda _source, *_command: ""
        try:
            apply_bundle(target, bundle)
            graph = load_persistent_work_graph(target)
            active = {
                item["id"]
                for item in graph.plan.tasks
                if item["contract_disposition"] == "active"
            }
            require(ROOT_TASK_ID in active and PRESERVED_TASK_ID in active, str(active))
            require("NSC-911" in active and "NSC-990" in active, str(active))

            stale_path = target / "Tasks" / "NSC-912.yaml"
            stale = json.loads(stale_path.read_text(encoding="utf-8"))
            stale["acceptance_criteria"][1]["requirement"] = (
                stale["acceptance_criteria"][1]["requirement"].split("guid ", 1)[0]
                + "guid 00000000000000000000000000000000; do not modify any other task's value file."
            )
            stale_path.write_text(
                json.dumps(stale, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            repair, summary = build_validation_repair_bundle(target)
            require(summary["repaired_task_contracts"] == 80, str(summary))
            require(summary["test_methods"] == 88, str(summary))
            apply_bundle(target, repair)
            repaired = json.loads((target / "Tasks" / "NSC-912.yaml").read_text())
            require(repaired["contract_revision"] == 2, str(repaired))
            require(_test_filter(912) in repaired["completion_gates"][0]["requirement"], str(repaired))
            expected_guid = unity_meta_bytes(
                "Assets/NoSafeCircle/DoorPrototype/Scripts/MuffcabbageGauntlet912.cs"
            ).decode("ascii").split("guid: ", 1)[1].strip()
            require(
                expected_guid in repaired["acceptance_criteria"][1]["requirement"],
                str(repaired["acceptance_criteria"]),
            )

            root_path = target / "Tasks" / "NSC-001.yaml"
            before = root_path.read_bytes()
            created = Path("Tasks/NSC-999.yaml")
            try:
                apply_bundle(
                    target,
                    {
                        Path("Tasks/NSC-001.yaml"): b"{}\n",
                        created: b"{}\n",
                    },
                )
            except Exception:
                pass
            else:
                raise AssertionError("invalid graph bundle did not fail")
            require(root_path.read_bytes() == before, "rollback changed an existing file")
            require(not (target / created).exists(), "rollback left a created file")
        finally:
            gauntlet._run = original_run


def test_public_or_production_repository_is_refused_before_mutation() -> None:
    original_run = gauntlet._run

    def public_run(_source, *command):
        if command[:4] == ("git", "remote", "get-url", "origin"):
            return "https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal.git"
        if command[:3] == ("gh", "repo", "view"):
            return json.dumps(
                {
                    "nameWithOwner": "cathode26/NoSafeCircle-Homework-Rehearsal",
                    "isPrivate": False,
                    "defaultBranchRef": {"name": "main"},
                }
            )
        raise AssertionError(command)

    gauntlet._run = public_run
    try:
        try:
            gauntlet._preflight_mutation(
                ROOT,
                expected_head="a" * 40,
                confirmed_repository="cathode26/NoSafeCircle-Homework-Rehearsal",
            )
        except gauntlet.SyntheticGauntletError as exc:
            require("private" in str(exc), str(exc))
        else:
            raise AssertionError("public rehearsal repository was accepted")

        gauntlet._run = lambda _source, *command: (
            "https://github.com/cathode26/NoSafeCircle.git"
            if command[:4] == ("git", "remote", "get-url", "origin")
            else ""
        )
        try:
            gauntlet._preflight_mutation(
                ROOT,
                expected_head="a" * 40,
                confirmed_repository="cathode26/NoSafeCircle",
            )
        except gauntlet.SyntheticGauntletError as exc:
            require("production" in str(exc), str(exc))
        else:
            raise AssertionError("production repository was accepted")
    finally:
        gauntlet._run = original_run


def main() -> int:
    tests = (
        test_bundle_has_eight_dependency_waves_and_mixed_work,
        test_old_active_work_is_cancelled_but_root_and_42_remain_active,
        test_validation_policy_binds_every_concrete_initial_contract,
        test_test_source_has_one_exact_method_per_implementation_child,
        test_every_concrete_task_owns_a_disjoint_source_and_meta_pair,
        test_task_contract_guids_match_execution_crew_sidecars,
        test_materialization_validates_and_failure_rolls_back,
        test_public_or_production_repository_is_refused_before_mutation,
    )
    for current in tests:
        current()
        print(f"PASS {current.__name__}")
    print(f"synthetic gauntlet setup tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
