#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[2] / "Testing"))
import generate_delivery_spec as delivery
from record_delivery import parse_delivery_spec


TASK_ID = "NSC-900"
TASK = {
    "schema_version": "2.0", "id": TASK_ID, "contract_revision": 1, "contract_disposition": "active",
    "title": "Synthetic Delivery", "exclusive_resources": ["repo-file:Config/unchanged.txt"],
    "completion_gates": [
        {"gate_id": "VAL-001", "reference": "Synthetic §1", "requirement": "Automated behavior is verified."},
        {"gate_id": "VAL-002", "reference": "Synthetic §2", "requirement": "Human behavior is verified."},
    ],
}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


class Fixture:
    def __init__(self, outer: Path):
        self.outer = outer; self.root = outer / "repo"; self.root.mkdir()
        git(self.root, "init", "-q"); git(self.root, "config", "user.email", "test@example.invalid"); git(self.root, "config", "user.name", "Human Tester")
        (self.root / "Tasks").mkdir(); (self.root / "Config").mkdir()
        (self.root / "Tasks" / f"{TASK_ID}.yaml").write_text(json.dumps(TASK), encoding="utf-8")
        (self.root / "Config" / "unchanged.txt").write_text("unchanged\n", encoding="utf-8")
        (self.root / "implementation.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "."); git(self.root, "commit", "-qm", "base"); self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "implementation.txt").write_text("implemented\n", encoding="utf-8")
        (self.root / "test.txt").write_text("test\n", encoding="utf-8")
        git(self.root, "add", "."); git(self.root, "commit", "-qm", "implementation"); self.head = git(self.root, "rev-parse", "HEAD")
        self.tree = git(self.root, "rev-parse", "HEAD^{tree}")
        self.manifest = self.make_manifest(outer / "validation")
        self.human = outer / "HumanValidation.txt"; self.human.write_text("Human Play Mode check passed.\n", encoding="utf-8")

    def graph(self, task=None):
        chosen = TASK if task is None else task
        return SimpleNamespace(tasks_by_id={} if chosen is False else {TASK_ID: chosen})

    def make_manifest(self, directory: Path, commit=None, tree=None, platform="PlayMode") -> Path:
        directory.mkdir(); xml = b'<test-run result="Passed" total="2" passed="2" failed="0" skipped="0" />\n'; log = b"log\n"
        (directory / "test-results.xml").write_bytes(xml); (directory / "unity.log").write_bytes(log)
        raw = {"schema_version":"1.0","manifest_type":"unity_test_validation","status":"passed",
               "validated_state":{"commit":commit or self.head,"tree":tree or self.tree,"post_commit":commit or self.head,"post_tree":tree or self.tree,
                                  "repository_clean_before":True,"repository_clean_after":True},
               "unity":{"version":"6000.0.55f1","executable":r"C:\Unity.exe","exit_code":0,"test_platform":platform,"test_filter":"Synthetic.Tests"},
               "test_run":{"result":"Passed","total":2,"passed":2,"failed":0,"skipped":0},
               "artifacts":{"xml":{"relative_path":"test-results.xml","sha256":hashlib.sha256(xml).hexdigest(),"size_bytes":len(xml)},
                            "log":{"relative_path":"unity.log","sha256":hashlib.sha256(log).hexdigest(),"size_bytes":len(log)}},
               "runner":{"path":"Pipeline/Testing/run_unity_tests_clean.ps1"}}
        path = directory / "validation-manifest.json"; path.write_text(json.dumps(raw), encoding="utf-8"); return path

    def draft(self, name="review.json", **kwargs):
        output = self.outer / name
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.graph()):
            delivery.create_draft(root=self.root, task_id=TASK_ID, manifest_paths=kwargs.pop("manifests", [self.manifest]),
                                  output=output, base_commit=kwargs.pop("base", self.base), **kwargs)
        return output, json.loads(output.read_text(encoding="utf-8"))

    def approve(self, review):
        review["review_status"] = "approved"
        for surface in review["surface_candidates"]:
            if surface["selected"]: surface["role"] = "Reviewed implementation or test surface"
        ids = [item["id"] for item in review["artifacts"]]
        for gate in review["gates"]:
            gate["evidence"] = [ids[0]]; gate["notes"] = f"Human reviewed {gate['gate_id']} against the named evidence."
        review["human_approval"].update(decision="approved", notes="I reviewed surfaces, mappings, and validation evidence.")

    def finalize(self, review, name="spec.json"):
        review_path = self.outer / "edited-review.json"; review_path.write_text(json.dumps(review), encoding="utf-8")
        output = self.outer / name
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.graph()):
            delivery.finalize_review(root=self.root, review_path=review_path, output=output)
        return output


class TaskDeliverySmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.fx = Fixture(Path(self.temp.name))
    def tearDown(self): self.temp.cleanup()

    def test_draft_happy_path_inventory_provenance_and_nonmutation(self):
        before = (git(self.fx.root, "status", "--porcelain"), git(self.fx.root, "rev-parse", "HEAD"), git(self.fx.root, "write-tree"))
        path, review = self.fx.draft(human_validation=[self.fx.human])
        self.assertEqual(review["review_status"], "needs_human")
        self.assertEqual(review["committed_diff_paths"], ["implementation.txt", "test.txt"])
        self.assertEqual([x["id"] for x in review["artifacts"]], ["unity_01_results", "unity_01_log", "human_validation_01"])
        self.assertEqual([x["evidence"] for x in review["gates"]], [[], []])
        unchanged = next(x for x in review["surface_candidates"] if x["path"] == "Config/unchanged.txt")
        self.assertFalse(unchanged["selected"]); self.assertIn("task.exclusive_resources", unchanged["sources"])
        self.assertTrue(all(x["role"] == "" for x in review["surface_candidates"]))
        self.assertEqual(before, (git(self.fx.root, "status", "--porcelain"), git(self.fx.root, "rev-parse", "HEAD"), git(self.fx.root, "write-tree")))
        self.assertFalse(str(path).startswith(str(self.fx.root)))

    def test_crew_base_override_and_candidate_deduplication(self):
        crew = self.fx.outer / "crew.json"
        crew.write_text(json.dumps({"schema_version":"1.0","task_id":TASK_ID,"crew_status":"review_ready","source_head":self.fx.base,
                                    "source_tree":git(self.fx.root,"rev-parse",f"{self.fx.base}^{{tree}}"),
                                    "implementation_actual_changed_paths":["implementation.txt"],"test_actual_changed_paths":["test.txt"],
                                    "final_actual_changed_paths":["implementation.txt","test.txt"]}), encoding="utf-8")
        output = self.fx.outer / "crew-review.json"
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=output, crew_result=crew)
        review = json.loads(output.read_text()); self.assertEqual(review["base_source"], "crew_result.source_head")
        implementation = next(x for x in review["surface_candidates"] if x["path"] == "implementation.txt")
        self.assertEqual(len(implementation["sources"]), 3); self.assertEqual(len({x["path"] for x in review["surface_candidates"]}), len(review["surface_candidates"]))
        output2 = self.fx.outer / "override.json"
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=output2, crew_result=crew, base_commit=self.fx.base)
        self.assertEqual(json.loads(output2.read_text())["base_source"], "explicit_base_commit_override")

    def test_multiple_manifests_and_identity_mismatch(self):
        second = self.fx.make_manifest(self.fx.outer / "validation2", platform="EditMode")
        _, review = self.fx.draft(manifests=[self.fx.manifest, second])
        self.assertEqual([x["id"] for x in review["artifacts"]], ["unity_01_results","unity_01_log","unity_02_results","unity_02_log"])
        bad = json.loads(second.read_text()); bad["validated_state"]["tree"] = bad["validated_state"]["post_tree"] = "a" * 40
        second.write_text(json.dumps(bad))
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest, second], output=self.fx.outer/"bad.json", base_commit=self.fx.base)

    def test_draft_fail_closed_inputs_and_paths(self):
        cases = []
        # Dirty repository/current identity mismatch.
        (self.fx.root / "dirty").write_text("x"); cases.append(("dirty", {})); (self.fx.root / "dirty").unlink()
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()):
            (self.fx.root / "dirty").write_text("x")
            with self.assertRaises(delivery.TaskDeliveryError): self.fx.draft(name="dirty.json")
            (self.fx.root / "dirty").unlink()
        old = git(self.fx.root, "rev-parse", "HEAD~1"); git(self.fx.root, "checkout", "-q", old)
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=self.fx.outer/"old.json", base_commit=old)
        git(self.fx.root, "checkout", "-q", self.fx.head)
        # Tampered artifact, missing/inactive task, inside output, overwrite.
        (self.fx.manifest.parent / "unity.log").write_text("tampered")
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError): self.fx.draft(name="tampered.json")
        self.fx.manifest = self.fx.make_manifest(self.fx.outer / "validation3")
        for graph in (self.fx.graph(False), self.fx.graph({**TASK, "contract_disposition":"cancelled"})):
            with patch.object(delivery, "load_persistent_work_graph", return_value=graph), self.assertRaises(delivery.TaskDeliveryError):
                delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=self.fx.outer/f"task-{id(graph)}.json", base_commit=self.fx.base)
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=self.fx.root/"inside.json", base_commit=self.fx.base)
        existing=self.fx.outer/"existing.json"; existing.write_text("x")
        with patch.object(delivery, "load_persistent_work_graph", return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
            delivery.create_draft(root=self.fx.root, task_id=TASK_ID, manifest_paths=[self.fx.manifest], output=existing, base_commit=self.fx.base)

    def test_crew_rejections(self):
        for update in ({"schema_version":"9"},{"task_id":"NSC-901"},{"crew_status":"blocked"},{"source_head":"x"*40},
                       {"final_actual_changed_paths":["../escape"]}):
            raw={"schema_version":"1.0","task_id":TASK_ID,"crew_status":"review_ready","source_head":self.fx.base}; raw.update(update)
            path=self.fx.outer/f"crew-{len(list(self.fx.outer.glob('crew-*')))}.json"; path.write_text(json.dumps(raw))
            with patch.object(delivery,"load_persistent_work_graph",return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
                delivery.create_draft(root=self.fx.root,task_id=TASK_ID,manifest_paths=[self.fx.manifest],output=self.fx.outer/f"out-{path.name}",crew_result=path)
        orphan_dir=self.fx.outer/"orphan"; orphan_dir.mkdir(); git(orphan_dir,"init","-q"); git(orphan_dir,"config","user.email","x@y"); git(orphan_dir,"config","user.name","x")
        (orphan_dir/"x").write_text("x"); git(orphan_dir,"add","."); git(orphan_dir,"commit","-qm","x"); orphan=git(orphan_dir,"rev-parse","HEAD")
        # syntactically valid but unknown/unrelated source fails commit resolution/ancestry.
        raw={"schema_version":"1.0","task_id":TASK_ID,"crew_status":"review_ready","source_head":orphan}; path=self.fx.outer/"orphan.json"; path.write_text(json.dumps(raw))
        with patch.object(delivery,"load_persistent_work_graph",return_value=self.fx.graph()), self.assertRaises(delivery.TaskDeliveryError):
            delivery.create_draft(root=self.fx.root,task_id=TASK_ID,manifest_paths=[self.fx.manifest],output=self.fx.outer/"orphan-out.json",crew_result=path)

    def test_finalize_happy_is_packager_compatible_atomic_and_nonmutating(self):
        _, review = self.fx.draft(human_validation=[self.fx.human]); self.fx.approve(review)
        before=(git(self.fx.root,"status","--porcelain"),git(self.fx.root,"rev-parse","HEAD"),git(self.fx.root,"write-tree"))
        output=self.fx.finalize(review); spec=json.loads(output.read_text()); parsed=parse_delivery_spec(spec)
        self.assertEqual(parsed.task_id,TASK_ID); self.assertEqual(set(spec),{"schema_version","task_id","validated_commit","base_commit","candidate_commit","surfaces","artifacts","gates","human_approval"})
        self.assertEqual(before,(git(self.fx.root,"status","--porcelain"),git(self.fx.root,"rev-parse","HEAD"),git(self.fx.root,"write-tree")))
        self.assertFalse((self.fx.root/"Pipeline/TaskGraph/evidence").exists())
        with self.assertRaises(delivery.TaskDeliveryError): self.fx.finalize(review,name=output.name)

    def test_finalize_accepts_explicit_non_required_human_approval(self):
        _, review = self.fx.draft()
        self.fx.approve(review)
        review["human_approval"] = {
            "required": False,
            "decision": "not_required",
            "approved_by": "",
            "notes": (
                f"Automated validation event {'e' * 64}; committed validation "
                f"policy {'d' * 64}."
            ),
        }
        output = self.fx.finalize(review, name="automated-spec.json")
        spec = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(spec["human_approval"], review["human_approval"])
        parsed = parse_delivery_spec(spec)
        self.assertFalse(parsed.human_approval.required)
        self.assertEqual(parsed.human_approval.decision, "not_required")
        self.assertEqual(parsed.human_approval.approved_by, "")

    def test_finalize_one_and_multiple_manifest_happy_paths(self):
        _, one = self.fx.draft(); self.fx.approve(one)
        self.assertTrue(self.fx.finalize(one, name="one-spec.json").is_file())
        second = self.fx.make_manifest(self.fx.outer / "validation2", platform="EditMode")
        _, multiple = self.fx.draft(name="multiple-review.json", manifests=[self.fx.manifest, second])
        self.fx.approve(multiple)
        self.assertTrue(self.fx.finalize(multiple, name="multiple-spec.json").is_file())

    def test_finalize_rejects_removed_duplicate_or_tampered_manifest_inventory(self):
        _, base = self.fx.draft(human_validation=[self.fx.human]); self.fx.approve(base)
        variants = []
        empty = json.loads(json.dumps(base)); empty["validation_manifests"] = []; variants.append(empty)
        removed = json.loads(json.dumps(base)); removed["validation_manifests"] = []
        removed["artifacts"] = [item for item in removed["artifacts"] if item["validation_manifest"] is None]
        removed_ids = {item["id"] for item in removed["artifacts"]}
        for gate in removed["gates"]: gate["evidence"] = list(removed_ids)
        variants.append(removed)
        duplicate = json.loads(json.dumps(base)); duplicate["validation_manifests"].append(dict(duplicate["validation_manifests"][0])); variants.append(duplicate)
        bad_commit = json.loads(json.dumps(base)); bad_commit["validation_manifests"][0]["commit"] = "a" * 40; variants.append(bad_commit)
        bad_tree = json.loads(json.dumps(base)); bad_tree["validation_manifests"][0]["tree"] = "b" * 40; variants.append(bad_tree)
        unbound = json.loads(json.dumps(base)); unbound["artifacts"][0]["validation_manifest"] = None; variants.append(unbound)
        for index, review in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(delivery.TaskDeliveryError):
                self.fx.finalize(review, name=f"manifest-fail-{index}.json")

    def test_finalize_rejects_unreviewed_surfaces_gates_and_approval(self):
        _, base = self.fx.draft()
        variants=[]
        variants.append(base)
        for mutate in (
            lambda r: [x.update(selected=False) for x in r["surface_candidates"]],
            lambda r: next(x for x in r["surface_candidates"] if x["selected"]).update(role=""),
            lambda r: r["surface_candidates"].append(dict(next(x for x in r["surface_candidates"] if x["selected"]))),
            lambda r: r["gates"][0].update(evidence=[]),
            lambda r: r["gates"][0].update(evidence=["unknown"]),
            lambda r: r["gates"][0].update(evidence=["unity_01_results","unity_01_results"]),
            lambda r: r["gates"][0].update(notes=""),
            lambda r: r["human_approval"].update(decision="",approved_by="",notes=""),
        ):
            candidate=json.loads(json.dumps(base)); self.fx.approve(candidate); mutate(candidate); variants.append(candidate)
        for index, review in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(delivery.TaskDeliveryError): self.fx.finalize(review,name=f"fail-{index}.json")

    def test_finalize_rejects_stale_source_task_and_artifact(self):
        _, review=self.fx.draft(); self.fx.approve(review)
        (self.fx.manifest.parent/"unity.log").write_text("tamper")
        with self.assertRaises(delivery.TaskDeliveryError): self.fx.finalize(review,name="tamper-spec.json")
        self.fx.manifest=self.fx.make_manifest(self.fx.outer/"validation4")
        _, review=self.fx.draft(name="fresh.json"); self.fx.approve(review)
        changed={**TASK,"contract_revision":2}; (self.fx.root/"Tasks"/f"{TASK_ID}.yaml").write_text(json.dumps(changed)); git(self.fx.root,"add","."); git(self.fx.root,"commit","-qm","task change")
        with self.assertRaises(delivery.TaskDeliveryError): self.fx.finalize(review,name="stale-task.json")

    def test_cli_prints_exact_safe_next_command(self):
        _, review=self.fx.draft(); self.fx.approve(review); review_path=self.fx.outer/"cli review.json"; review_path.write_text(json.dumps(review)); output=self.fx.outer/"Vincent's $delivery"/"final spec.json"; output.parent.mkdir()
        stream=io.StringIO()
        with patch.object(delivery,"load_persistent_work_graph",return_value=self.fx.graph()), contextlib.redirect_stdout(stream):
            code=delivery.main(["finalize","--root",str(self.fx.root),"--review",str(review_path),"--output",str(output)])
        self.assertEqual(code, 0)
        published_output = output.parent.resolve(strict=True) / output.name
        expected_command = (
            "python Pipeline/TaskGraph/record_delivery.py "
            f"{delivery._powershell_literal(str(published_output))}"
        )
        self.assertIn(expected_command, stream.getvalue())
        self.assertIn("Nothing was staged or committed",stream.getvalue())
        self.assertEqual(delivery._powershell_literal(r"C:\Temp\spec.json"), r"'C:\Temp\spec.json'")


if __name__ == "__main__":
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TaskDeliverySmokeTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful(): print("TaskDelivery smoke tests: PASS")
    raise SystemExit(0 if result.wasSuccessful() else 1)
