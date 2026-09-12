"""Temporary fixture tests; no provider, Unity, or real Source mutation."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Pipeline.ExecutionCrew.run_crew import unity_meta_bytes
from Pipeline.AssistantControl.gauntlet_replay import (
    DECOMPOSITION_ROOTS, GauntletReplayError, REPLAY_MAP, _meta_guid, _preflight, generate,
)
from Pipeline.TaskReviewAgent.decomposition_policy_audit import audit_decomposition_policy
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task
from Pipeline.AssistantControl.graph_controller import _resolve_test_paths


def template(task_id):
    number = int(task_id.split("-")[1])
    decompose = task_id in {"NSC-898", "NSC-1007", "NSC-1008"}
    suffixes = ("Alpha", "Beta") if decompose else ("",)
    paths = [f"Assets/NoSafeCircle/DoorPrototype/Scripts/Gauntlet{number}{suffix}.cs{tail}"
             for suffix in suffixes for tail in ("", ".meta")]
    dependencies = {"NSC-1007": ["NSC-1001"], "NSC-1008": ["NSC-1007"],
                    "NSC-1010": ["NSC-1008"]}.get(task_id, [])
    criteria = [{"criterion_id": f"AC-{index:03d}", "reference": "fixture",
                 "requirement": f"Create {paths[(index - 1) * 2 + 1]} with guid {'a' * 32} and Value = {number}."}
                for index in range(1, len(suffixes) + 1)]
    gates = [{"gate_id": f"VAL-{index:03d}", "reference": "fixture",
              "requirement": ("Unity EditMode filter NoSafeCircle.DoorPrototype.Tests.Editor."
                              f"GauntletTests.Gauntlet{number}{suffix}HasExpectedValue passes")}
             for index, suffix in enumerate(suffixes, 1)]
    return {"schema_version": "2.0", "id": task_id, "contract_revision": 3,
            "contract_disposition": "active",
            "title": f"Gauntlet {number}: " + ("Split Alpha and Beta Values" if decompose else "Publish Its Isolated Value"),
            "reconciliation_key": f"gauntlet-{number}-" + ("pair" if decompose else "value"),
            "kind": "implementation", "type": "engineering-validation",
            "execution_scope": "needs_execution_decomposition" if decompose else "single_agent",
            "execution_reason": f"Fixture {number}", "decomposition_state": "concrete",
            "decomposition_reason": f"Fixture {number}", "parent": "NSC-001",
            "depends_on": dependencies, "exclusive_resources": ["repo-file:" + path for path in paths],
            "acceptance_criteria": criteria, "completion_gates": gates,
            "downstream_integration_obligations": [], "basis": "fixture", "source_scope": "engineering",
            "confidence": "high", "notes": f"Fixture NSC-{number}",
            "provenance": {"origin": "fixture", "gauntlet_id": "fixture", "expected_value": number,
                           "expected_values": [number, number] if decompose else [], "expected_paths": paths}}


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "Tasks").mkdir()
        (self.root / "Pipeline/TaskGraph").mkdir(parents=True)
        (self.root / "Pipeline/TaskReviewAgent").mkdir(parents=True)
        (self.root / "Pipeline/TaskGraph/WORK_ID_MAP.json").write_text(
            json.dumps({"schema_version": "1.0", "id_map": {"no-safe-circle": "NSC-001"}}))
        (self.root / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json").write_text(
            json.dumps({"schema_version": "1.0", "tasks": {}, "decomposition_child_templates": {}}))

    def tearDown(self):
        self.temp.cleanup()

    def generate(self, validation_code=0):
        completed = subprocess.CompletedProcess([], validation_code, "taskcontrol validate: PASS\n", "bad")
        with patch("Pipeline.AssistantControl.gauntlet_replay._preflight", return_value=self.root), \
             patch("Pipeline.AssistantControl.gauntlet_replay._load_template", side_effect=lambda _s, task: template(task)), \
             patch("Pipeline.AssistantControl.gauntlet_replay.read_committed_tasks", return_value={}), \
             patch("Pipeline.AssistantControl.gauntlet_replay.subprocess.run", return_value=completed) as run:
            result = generate(self.root, branch="gauntlet-replay/fixture")
        self.assertTrue(any(call.args[0][-2:] == ["diff", "--check"] for call in run.call_args_list))
        return result

    def test_generates_only_fixed_roots_tests_map_and_policy(self):
        result = self.generate()
        self.assertEqual(list(REPLAY_MAP.values()), result["task_ids"])
        created = sorted(path.stem for path in (self.root / "Tasks").glob("NSC-*.yaml"))
        self.assertEqual(sorted(REPLAY_MAP.values()), created)
        self.assertNotIn("NSC-042", created)
        self.assertNotIn("NSC-899", created)
        self.assertFalse(list((self.root / "Assets/NoSafeCircle/DoorPrototype/Scripts").glob("Gauntlet*")))
        task_1108 = json.loads((self.root / "Tasks/NSC-1108.yaml").read_text())
        task_1110 = json.loads((self.root / "Tasks/NSC-1110.yaml").read_text())
        contracts = {path.stem: json.loads(path.read_text()) for path in (self.root / "Tasks").glob("NSC-*.yaml")}
        expected_dependencies = {"NSC-998": [], "NSC-1101": [], "NSC-1103": [], "NSC-1104": [],
                                 "NSC-1105": [], "NSC-1107": ["NSC-1101"],
                                 "NSC-1108": ["NSC-1107"], "NSC-1110": ["NSC-1108"]}
        self.assertEqual(expected_dependencies, {task: value["depends_on"] for task, value in contracts.items()})
        rendered = json.dumps(contracts, sort_keys=True)
        for old_id in REPLAY_MAP:
            self.assertNotRegex(rendered, rf"(?<![A-Za-z0-9-]){old_id}(?!\d)")
        self.assertEqual("gauntlet-1108-pair", task_1108["reconciliation_key"])
        policy = json.loads((self.root / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json").read_text())
        self.assertEqual(DECOMPOSITION_ROOTS, set(policy["decomposition_child_templates"]))
        self.assertEqual(set(REPLAY_MAP.values()) - DECOMPOSITION_ROOTS, set(policy["tasks"]))
        audit = audit_decomposition_policy(self.root, document=policy, tasks=contracts)
        self.assertEqual(sorted(DECOMPOSITION_ROOTS),
                         [item["parent_task_id"] for item in audit["templates_audited"]])
        units = [(task_id, suffix) for task_id in REPLAY_MAP.values()
                 for suffix in (("Alpha", "Beta") if task_id in DECOMPOSITION_ROOTS else ("",))]
        test_root = self.root / "Assets/NoSafeCircle/DoorPrototype/Tests/Editor"
        expected_sources = {
            f"GauntletReplay{task_id.split('-')[1]}{suffix}Tests.cs"
            for task_id, suffix in units
        }
        self.assertEqual(expected_sources, {path.name for path in test_root.glob("*.cs")})
        self.assertEqual({name + ".meta" for name in expected_sources},
                         {path.name for path in test_root.glob("*.cs.meta")})
        for task_id, suffix in units:
            number = task_id.split("-")[1]
            class_name = f"GauntletReplay{number}{suffix}Tests"
            test_source = f"Assets/NoSafeCircle/DoorPrototype/Tests/Editor/{class_name}.cs"
            test_bytes = (self.root / test_source).read_bytes()
            self.assertIn(f"public class {class_name}".encode(), test_bytes)
            self.assertIn(f"Gauntlet{number}{suffix}HasExpectedValue".encode(), test_bytes)
            meta_path = self.root / (test_source + ".meta")
            self.assertEqual(unity_meta_bytes(test_source), meta_path.read_bytes())
            self.assertEqual(_meta_guid(test_source),
                             meta_path.read_text().split("guid: ", 1)[1].strip())
            resources = contracts[task_id]["exclusive_resources"]
            self.assertIn(f"repo-file:{test_source}", resources)
            self.assertIn(f"repo-file:{test_source}.meta", resources)
        for contract in contracts.values():
            for path in contract["provenance"]["expected_paths"]:
                if path.endswith(".meta"):
                    expected = unity_meta_bytes(path[:-len(".meta")]).decode().split("guid: ", 1)[1].strip()
                    self.assertIn(expected, json.dumps(contract))

        independent_filters = []
        for task_id in set(REPLAY_MAP.values()) - DECOMPOSITION_ROOTS:
            independent_filters.append(policy["tasks"][task_id]["test_filters"]["EditMode"])
        for task_id in DECOMPOSITION_ROOTS:
            variants = policy["decomposition_child_templates"][task_id]["validation_variants"]
            self.assertEqual(2, len(variants))
            independent_filters.extend(item["test_filters"]["EditMode"] for item in variants)
            for variant in variants:
                self.assertEqual(4, len(variant["required_exclusive_resources"]))
                test_resources = [item for item in variant["required_exclusive_resources"]
                                  if "/Tests/" in item and item.endswith(".cs")]
                self.assertEqual(1, len(test_resources))
        self.assertEqual(len(units), len(independent_filters))
        self.assertEqual(len(independent_filters), len(set(independent_filters)))

    def test_every_independent_scope_resolves_a_different_committed_test_file(self):
        self.generate()
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Replay Fixture"],
                       cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "replay@example.invalid"],
                       cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "replay fixture"],
                       cwd=self.root, check=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()
        policy = json.loads((self.root / "Pipeline/TaskReviewAgent/authoritative_validation_policy.json").read_text())
        resolved = []
        for task_id in set(REPLAY_MAP.values()) - DECOMPOSITION_ROOTS:
            task = load_committed_task(self.root, task_id, commit=head)
            paths = _resolve_test_paths(self.root, task, head)
            self.assertEqual(1, len(paths))
            resolved.extend(paths)
        for task_id in DECOMPOSITION_ROOTS:
            for variant in policy["decomposition_child_templates"][task_id]["validation_variants"]:
                test_filter = variant["test_filters"]["EditMode"]
                paths = _resolve_test_paths(
                    self.root,
                    {"id": task_id, "completion_gates": [{
                        "requirement": f"Unity EditMode filter {test_filter} passes",
                    }]},
                    head,
                )
                self.assertEqual(1, len(paths))
                resolved.extend(paths)
        self.assertEqual(11, len(resolved))
        self.assertEqual(len(resolved), len(set(resolved)))

    def test_refuses_contract_and_output_collisions(self):
        (self.root / "Tasks/NSC-998.yaml").write_text("collision")
        with self.assertRaisesRegex(GauntletReplayError, "collision"):
            self.generate()

    def test_validation_failure_rolls_back_every_generated_file(self):
        original_map = (self.root / "Pipeline/TaskGraph/WORK_ID_MAP.json").read_bytes()
        with self.assertRaisesRegex(GauntletReplayError, "taskcontrol"):
            self.generate(validation_code=1)
        self.assertEqual([], list((self.root / "Tasks").glob("NSC-*.yaml")))
        self.assertEqual([], list(self.root.glob("Assets/**/*.cs")))
        self.assertEqual([], list(self.root.glob("Assets/**/*.meta")))
        self.assertEqual(original_map, (self.root / "Pipeline/TaskGraph/WORK_ID_MAP.json").read_bytes())

    def test_preflight_refuses_wrong_branch_remote_and_dirty_tree(self):
        def responses(branch="gauntlet-replay/test", remote=b"", dirty=b""):
            def run(_source, *args):
                if args == ("rev-parse", "--show-toplevel"): return (str(self.root) + "\n").encode()
                if args == ("branch", "--show-current"): return (branch + "\n").encode()
                if args == ("remote",): return remote
                if args[0] == "status": return dirty
                raise AssertionError(args)
            return run
        for expected, kwargs in (("gauntlet-replay", {"branch": "main"}),
                                 ("no Git remote", {"remote": b"origin\n"}),
                                 ("clean", {"dirty": b"?? file\n"})):
            with self.subTest(expected=expected), patch(
                    "Pipeline.AssistantControl.gauntlet_replay._git", side_effect=responses(**kwargs)):
                with self.assertRaisesRegex(GauntletReplayError, expected):
                    _preflight(self.root, kwargs.get("branch", "gauntlet-replay/test"))


if __name__ == "__main__":
    unittest.main()
