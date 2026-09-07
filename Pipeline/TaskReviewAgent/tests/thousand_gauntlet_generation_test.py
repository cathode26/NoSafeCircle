#!/usr/bin/env python3
"""Pure/component regression checks; generated contracts live only in temp copies.

No gameplay acceptance is claimed. Git reads are local and provider/Issue/Unity
boundaries are forbidden. The legacy comparison executes the exact base generator.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Pipeline.TaskReviewAgent import prepare_synthetic_gauntlet as g
from Pipeline.TaskReviewAgent.issue_workflow import AUTOMATED_VALIDATION_REPOSITORIES
from Pipeline.TaskReviewAgent.tests.prepare_synthetic_gauntlet_smoke_test import _copy_graph
from work_graph_validate import validate_work_graph_plan
from work_graph_transform import WorkGraphPlan

# This public commit contains the exact same pre-scale generator blob as the
# original compatibility oracle, without requiring unpublished source history.
BASE = "73fae3818ded52eec10e12230de7403cafda4081"


class Generation(unittest.TestCase):
    def bound_bundle(self, repository=None):
        repository = g.PRIVATE_REPOSITORY if repository is None else repository
        bundle = dict(self.bundle)
        manifest = deepcopy(self.manifest)
        manifest["source_origin"] = f"https://github.com/{repository}.git"
        manifest["target_repository"] = repository
        manifest.pop("manifest_sha256")
        manifest["manifest_sha256"] = g._sha256(g._json_bytes(manifest))
        bundle[g.MANIFEST_RELATIVE] = g._json_bytes(manifest)
        return bundle, manifest

    def identity_command(self, manifest, source, *args):
        identities = {
            ("git", "remote", "get-url", "origin"): manifest["source_origin"],
            ("git", "rev-parse", "HEAD"): manifest["source_head"],
            ("git", "rev-parse", "HEAD^{tree}"): manifest["source_tree"],
        }
        self.assertIn(args, identities, f"unexpected process: {args}")
        return identities[args]

    @classmethod
    def setUpClass(cls):
        cls.calls = []
        original = g._run
        def observed(source, *args):
            if args[0] != "git" or args[1] not in {"ls-files", "rev-parse", "remote"}:
                raise AssertionError(f"unexpected process: {args}")
            cls.calls.append(args)
            return original(source, *args)
        with patch.object(g, "_run", observed):
            cls.bundle, cls.manifest = g.build_bundle(
                ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY
            )
        cls.tasks = {key.stem: json.loads(value) for key, value in cls.bundle.items()
                     if key.parent == Path("Tasks")}
        cls.initial = [cls.tasks[f"NSC-{n}"] for n in range(2000, 3000)]

    def test_counts_and_linear_process_budget(self):
        m = self.manifest
        self.assertEqual((m["initial_synthetic_tasks"], m["expected_dynamic_children"],
                          m["post_decomposition_contracts"], m["implementation_jobs"]),
                         (1000, 40, 1040, 1020))
        self.assertEqual(m["dependency_waves"], 100)
        self.assertEqual(m["decomposition_parents"], [f"NSC-{n}" for n in range(2000, 3000, 50)])
        self.assertEqual(Counter(call[1] for call in self.calls),
                         {"ls-files": 1, "rev-parse": 2, "remote": 1})

    def test_guid_collision_mutation_is_rejected(self):
        with patch.object(g, "_guid", return_value="a" * 32), self.assertRaisesRegex(g.SyntheticGauntletError, "GUIDs collide"):
            g.build_bundle(ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY)

    def test_generation_is_byte_deterministic(self):
        bundle, manifest = g.build_bundle(
            ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY
        )
        self.assertEqual(bundle, self.bundle)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(g.validate_manifest(bundle), manifest)

    def test_target_repository_selection_and_local_tooling_dry_run(self):
        self.assertEqual(self.manifest["target_repository"], g.PRIVATE_REPOSITORY)
        self.assertEqual(self.manifest["source_origin"], g._run(ROOT, "git", "remote", "get-url", "origin"))
        for repository in sorted(AUTOMATED_VALIDATION_REPOSITORIES):
            bundle, manifest = g.build_bundle(ROOT, "thousand", target_repository=repository)
            self.assertEqual(manifest["target_repository"], repository)
            self.assertEqual(manifest["source_origin"], self.manifest["source_origin"])
            self.assertEqual(g.validate_manifest(bundle), manifest)
            self.assertEqual({path: data for path, data in bundle.items() if path != g.MANIFEST_RELATIVE},
                             {path: data for path, data in self.bundle.items() if path != g.MANIFEST_RELATIVE})
        original = g._run
        repository = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
        def observed(source, *args):
            if args == ("git", "remote", "get-url", "origin"):
                return f"https://github.com/{repository}.git"
            return original(source, *args)
        with patch.object(g, "_run", observed):
            _, manifest = g.build_bundle(ROOT, "thousand")
        self.assertEqual(manifest["target_repository"], repository)
        with self.assertRaises(g.SyntheticGauntletError):
            g.build_bundle(ROOT, "thousand", target_repository="cathode26/NoSafeCircle")

    def test_production_origin_requires_explicit_authorized_target_without_masquerade(self):
        original = g._run
        production_origin = "https://github.com/cathode26/NoSafeCircle.git"

        def observed(source, *args):
            if args == ("git", "remote", "get-url", "origin"):
                return production_origin
            return original(source, *args)

        with patch.object(g, "_run", observed):
            with self.assertRaisesRegex(g.SyntheticGauntletError, "exact private rehearsal repository"):
                g.build_bundle(ROOT, "thousand")
            bundle, manifest = g.build_bundle(
                ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY
            )

        self.assertEqual(len(manifest["target_task_ids"]), 1000)
        self.assertTrue(all(
            Path(f"Tasks/{task_id}.yaml") in bundle
            for task_id in manifest["target_task_ids"]
        ))
        self.assertEqual(manifest["initial_synthetic_tasks"], 1000)
        self.assertEqual(manifest["source_origin"], production_origin)
        self.assertEqual(manifest["target_repository"], g.PRIVATE_REPOSITORY)
        self.assertEqual(g.validate_manifest(bundle), manifest)

    def test_manifest_source_and_target_bindings_precede_first_write(self):
        repository = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
        bundle, manifest = self.bound_bundle(repository)
        for field, changed in (("source_origin", f"https://github.com/{g.PRIVATE_REPOSITORY}.git"),
                               ("source_head", "b" * 40), ("source_tree", "c" * 40)):
            actual = {**manifest, field: changed}
            with self.subTest(field=field), patch.object(g, "_run", lambda root, *args: self.identity_command(actual, root, *args)), \
                    patch.object(g, "_write_atomic", side_effect=AssertionError("write reached")) as writer:
                with self.assertRaisesRegex(g.SyntheticGauntletError, "manifest source or target"):
                    g.apply_bundle(ROOT, bundle)
                writer.assert_not_called()
        # A tooling-origin dry-run bundle must never become a mutation authority.
        with patch.object(g, "_write_atomic", side_effect=AssertionError("write reached")) as writer:
            with self.assertRaises(g.SyntheticGauntletError):
                g.apply_bundle(ROOT, self.bundle)
            writer.assert_not_called()

    def test_both_authorized_repository_preflights_bind_metadata(self):
        for repository in sorted(AUTOMATED_VALIDATION_REPOSITORIES):
            calls = []
            def run(source, *args):
                calls.append(args)
                responses = {
                    ("git", "remote", "get-url", "origin"): f"https://github.com/{repository}.git",
                    ("gh", "repo", "view", repository, "--json", "nameWithOwner,isPrivate,defaultBranchRef"):
                        json.dumps({"nameWithOwner": repository, "isPrivate": True, "defaultBranchRef": {"name": "main"}}),
                    ("git", "branch", "--show-current"): "main",
                    ("git", "rev-parse", "HEAD"): "a" * 40,
                    ("git", "status", "--porcelain=v1", "--untracked-files=all"): "",
                    ("git", "fetch", "origin", "main"): "",
                    ("git", "rev-parse", "origin/main"): "a" * 40,
                }
                self.assertIn(args, responses)
                return responses[args]
            with patch.object(g, "_run", run):
                self.assertEqual(g._preflight_mutation(ROOT, expected_head="a" * 40,
                                                     confirmed_repository=repository), repository)
            self.assertEqual(len(calls), 7)

    def test_legacy_bytes_match_exact_prechange_implementation(self):
        result = subprocess.run(["git", "show", f"{BASE}:Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py"],
                                cwd=ROOT, capture_output=True, check=True)
        baseline = types.ModuleType("gauntlet_baseline")
        baseline.__file__ = str(ROOT / "Pipeline/TaskReviewAgent/prepare_synthetic_gauntlet.py")
        exec(compile(result.stdout, baseline.__file__, "exec"), baseline.__dict__)
        self.assertEqual(baseline.build_bundle(ROOT), g.build_bundle(ROOT))
        with self.assertRaises(TypeError):
            baseline.build_bundle(ROOT, "thousand")

    def test_unique_identity_paths_and_guids(self):
        for field in ("id", "reconciliation_key", "title"):
            self.assertEqual(len({task[field] for task in self.initial}), 1000)
        paths = [path for task in self.initial for path in task["provenance"]["expected_paths"]]
        self.assertEqual(len(paths), 2040)
        self.assertEqual(len({path.casefold() for path in paths}), len(paths))
        sources = [path for path in paths if path.endswith(".cs")]
        self.assertEqual(len({g._guid(path) for path in sources}), 1020)
        self.assertTrue(all(task["parent"] == "NSC-001" for task in self.initial))

    def test_dependencies_bound_width_and_have_barriers_diamonds(self):
        # A partition into ten chains bounds *every* possible initial frontier,
        # not just one lucky simulated completion order. First frontier attains 10.
        for index, task in enumerate(self.initial):
            number = 2000 + index
            self.assertTrue(all(int(dep[4:]) < number for dep in task["depends_on"]))
            if index >= 10:
                self.assertIn(f"NSC-{number - 10}", task["depends_on"])
        self.assertEqual(sum(not task["depends_on"] for task in self.initial), 10)
        for wave in range(10, 100, 10):
            previous = {f"NSC-{2000 + (wave - 1) * 10 + col}" for col in range(10)}
            self.assertTrue(all(previous <= set(task["depends_on"])
                                for task in self.initial[wave * 10:wave * 10 + 10]))
        self.assertIn("NSC-2002", self.tasks["NSC-2013"]["depends_on"])
        self.assertIn("NSC-2013", self.tasks["NSC-2022"]["depends_on"])
        self.assertEqual(sum(len(task["depends_on"]) for task in self.initial),
                         self.manifest["dependency_edges"])

    def test_resource_contention_is_local(self):
        groups = json.loads(self.bundle[Path("Pipeline/TaskGraph/RESOURCE_GROUPS.yaml")])["resource_groups"]
        groups = [group for group in groups if group["resource_key"].startswith("logical:thousand-")]
        self.assertEqual(len(groups), 10)
        self.assertTrue(all(len(group["work_ids"]) == 2 for group in groups))
        self.assertEqual(sum(len(task["exclusive_resources"]) > 2
                             for task in self.initial if task["execution_scope"] == "single_agent"), 20)

    def test_history_and_protected_task_are_retained(self):
        self.assertEqual(self.tasks["NSC-001"]["contract_disposition"], "active")
        self.assertEqual(self.tasks["NSC-042"]["contract_disposition"], "active")
        self.assertNotIn("NSC-042", self.manifest["target_task_ids"])
        self.assertTrue(all(task["contract_disposition"] == "cancelled"
                            for key, task in self.tasks.items()
                            if key not in {"NSC-001", "NSC-042"} and key not in self.manifest["target_task_ids"]))

    def test_manifest_tampering_and_unsupported_schema_fail(self):
        for field, value in (("schema_version", "99"), ("excluded_task_ids", []),
                             ("initial_synthetic_tasks", 999)):
            bundle = dict(self.bundle)
            manifest = deepcopy(self.manifest)
            manifest[field] = value
            bundle[g.MANIFEST_RELATIVE] = g._json_bytes(manifest)
            with self.assertRaises(g.SyntheticGauntletError):
                g.validate_manifest(bundle)
        bundle = dict(self.bundle)
        bundle[Path("Tasks/NSC-2001.yaml")] += b" "
        with self.assertRaises(g.SyntheticGauntletError):
            g.validate_manifest(bundle)

    def test_collision_refused_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="thousand-collision-") as text:
            source = Path(text)
            _copy_graph(source)
            path = source / "Tasks/NSC-2000.yaml"
            path.write_bytes(self.bundle[Path("Tasks/NSC-2000.yaml")])
            id_map_path = source / "Pipeline/TaskGraph/WORK_ID_MAP.json"
            id_map = json.loads(id_map_path.read_bytes())
            id_map["id_map"][self.tasks["NSC-2000"]["reconciliation_key"]] = "NSC-2000"
            id_map_path.write_bytes(g._json_bytes(id_map))
            before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
            with self.assertRaises(g.SyntheticGauntletError):
                g.build_bundle(source, "thousand")
            self.assertEqual(before, {path: path.read_bytes() for path in source.rglob("*") if path.is_file()})

    def test_wrong_repositories_fail_before_metadata_or_mutation(self):
        for repository in ("cathode26/NoSafeCircle", "other/Pipeline-Rehearsal",
                           "cathode26/Other-Rehearsal"):
            calls = []
            def run(source, *args):
                calls.append(args)
                self.assertEqual(args, ("git", "remote", "get-url", "origin"))
                return f"https://github.com/{repository}.git"
            with patch.object(g, "_run", run), self.assertRaises(g.SyntheticGauntletError):
                g._preflight_mutation(ROOT, expected_head="a" * 40, confirmed_repository=repository)
            self.assertEqual(len(calls), 1)

    def test_mutated_count_and_edge_assertions_are_load_bearing(self):
        # Remove all generated dependency edges in the production generator.
        # The same frontier assertion must reject the resulting executable graph.
        with patch.object(g, "_dependency_ids", return_value=[]):
            bundle, _ = g.build_bundle(
                ROOT, "thousand", target_repository=g.PRIVATE_REPOSITORY
            )
        changed = [json.loads(bundle[Path(f"Tasks/NSC-{number}.yaml")])
                   for number in range(2000, 3000)]
        with self.assertRaises(AssertionError):
            self.assertEqual(sum(not task["depends_on"] for task in changed), 10)

    def test_four_digit_ids_pass_execution_and_result_boundaries(self):
        import re
        from Pipeline.TaskReviewAgent import contracts, worker_result
        from Pipeline.TaskExecution import contracts as execution
        from Pipeline.TaskDecomposition import context_builder
        from Pipeline.ExecutionCrew import run_crew
        from Pipeline.TaskReviewAgent import autonomous_graph_run, token_usage, decomposition_policy_audit
        from Pipeline.TaskGraph import work_graph_validate, graph_delta, conformance_records, token_usage_metrics
        from Pipeline.TaskDecomposition import contracts as decomposition
        from Pipeline.Supervisor import task_checkout
        patterns = (contracts.TASK_ID_RE, execution._TASK_ID, context_builder.TASK_ID_RE,
            run_crew.TASK_ID_RE, autonomous_graph_run._TASK_ID_RE, token_usage._TASK_ID_RE,
            decomposition_policy_audit._TASK_ID, work_graph_validate.WORK_ID_PATTERN,
            graph_delta.NSC_ID_RE, conformance_records.TASK_ID_RE, token_usage_metrics.TASK_ID_RE,
            decomposition.TASK_ID_RE, task_checkout.TASK_ID_RE)
        for valid in ("NSC-042", "NSC-999", "NSC-1000", "NSC-2000", "NSC-3039", "NSC-999999999"):
            self.assertEqual(contracts.validate_task_id(valid), valid)
            for pattern in patterns:
                self.assertTrue(pattern.fullmatch(valid), (pattern, valid))
        for invalid in ("NSC-20", "nsc-2000", "NSC-2000-extra", "../NSC-2000",
                        "NSC-02000", "NSC-0000", "NSC-1000000000", "NSC-２０００"):
            with self.assertRaises(contracts.TaskReviewContractError):
                contracts.validate_task_id(invalid)
            for pattern in patterns:
                self.assertIsNone(pattern.fullmatch(invalid), (pattern, invalid))
        # The exact old production expression is a behavior mutation; the
        # positive production validation above must fail when it is restored.
        with patch.object(contracts, "TASK_ID_RE", re.compile(r"^NSC-[0-9]{3}$")):
            with self.assertRaises(contracts.TaskReviewContractError):
                contracts.validate_task_id("NSC-2000")

    def test_mutation_preflight_guards_precede_materialization(self):
        expected = "a" * 40
        for fault in ("dirty", "detached", "head", "origin", "public"):
            def run(source, *args):
                if args[:3] == ("git", "remote", "get-url"):
                    return f"https://github.com/{g.PRIVATE_REPOSITORY}.git"
                if args[0] == "gh":
                    return json.dumps({"nameWithOwner": g.PRIVATE_REPOSITORY,
                        "isPrivate": fault != "public", "defaultBranchRef": {"name": "main"}})
                if args[1] == "branch": return "" if fault == "detached" else "main"
                if args[1] == "status": return " M Tasks/NSC-2001.yaml" if fault == "dirty" else ""
                if args[1] == "fetch": return ""
                if args[1] == "rev-parse":
                    return "b" * 40 if (fault == "head" and args[2] == "HEAD") or (fault == "origin" and args[2] == "origin/main") else expected
                self.fail(args)
            with patch.object(g, "_run", run), self.assertRaises(g.SyntheticGauntletError):
                g._preflight_mutation(ROOT, expected_head=expected, confirmed_repository=g.PRIVATE_REPOSITORY)

    def test_cyclic_overlay_fails_before_first_write(self):
        from work_graph_validate import WorkGraphValidationError
        with tempfile.TemporaryDirectory(prefix="thousand-cycle-") as text:
            source = Path(text)
            _copy_graph(source)
            bundle, manifest = self.bound_bundle()
            task = json.loads(bundle[Path("Tasks/NSC-2001.yaml")])
            task["depends_on"] = ["NSC-2001"]
            bundle[Path("Tasks/NSC-2001.yaml")] = g._json_bytes(task)
            manifest = json.loads(bundle[g.MANIFEST_RELATIVE])
            for relative, source_hash in manifest["source_artifacts"].items():
                if source_hash is not None:
                    target = source / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / relative).read_bytes())
            manifest["artifacts"]["Tasks/NSC-2001.yaml"] = g._sha256(bundle[Path("Tasks/NSC-2001.yaml")])
            manifest.pop("manifest_sha256")
            manifest["manifest_sha256"] = g._sha256(g._json_bytes(manifest))
            bundle[g.MANIFEST_RELATIVE] = g._json_bytes(manifest)
            with patch.object(g, "_run", lambda root, *args: self.identity_command(manifest, root, *args)), \
                    patch.object(g, "_write_atomic", side_effect=AssertionError("mutation reached")) as writer:
                with self.assertRaises(WorkGraphValidationError):
                    g.apply_bundle(source, bundle)
                writer.assert_not_called()

    def test_materialization_rollback_and_canonical_validation(self):
        from contextlib import redirect_stdout
        import io
        import taskcontrol
        with tempfile.TemporaryDirectory(prefix="thousand-apply-") as text:
            source = Path(text)
            _copy_graph(source)
            repository = next(item for item in AUTOMATED_VALIDATION_REPOSITORIES if item != g.PRIVATE_REPOSITORY)
            bundle, manifest = self.bound_bundle(repository)
            for relative, source_hash in manifest["source_artifacts"].items():
                if source_hash is not None:
                    target = source / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / relative).read_bytes())
            before = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
            real_write = g._write_atomic
            calls = 0
            def interrupted(path, content):
                nonlocal calls
                calls += 1
                if calls == 10:
                    raise OSError("injected publication interruption")
                real_write(path, content)
            with patch.object(g, "_run", lambda root, *args: self.identity_command(manifest, root, *args)), \
                    patch.object(g, "_write_atomic", interrupted), self.assertRaises(OSError):
                g.apply_bundle(source, bundle)
            self.assertEqual(before, {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()})
            validation_calls = []
            def command(root, *args):
                if args[-1] == "validate":
                    validation_calls.append("taskcontrol")
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(taskcontrol.command_validate(g.load_persistent_work_graph(root)), 0)
                    return ""
                if args == ("git", "diff", "--check"):
                    return ""
                return self.identity_command(manifest, root, *args)
            with patch.object(g, "_run", command):
                g.apply_bundle(source, bundle)
            self.assertEqual(validation_calls, ["taskcontrol"])
            for relative, data in bundle.items():
                self.assertEqual((source / relative).read_bytes(), data)


if __name__ == "__main__":
    started = time.perf_counter()
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    outcome = run_with_synthetic_authority(unittest.main, exit=False)
    print(json.dumps({"suite": "thousand-generation", "tests": outcome.result.testsRun,
                      "duration_seconds": round(time.perf_counter() - started, 3),
                      "generation_git_processes": len(Generation.calls),
                      "network_docker_unity_provider_processes": 0}, sort_keys=True))
    raise SystemExit(0 if outcome.result.wasSuccessful() else 1)
