#!/usr/bin/env python3
"""Pure/component regressions for local rehearsal display, never task delivery.

Disposable durable state is read through the real local backend. Browser
presentation functions execute in Node with a small in-memory DOM. No provider,
GitHub, container or canonical Unity asset is touched.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


VIEW_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEW_ROOT.parents[2]))
from Pipeline.TaskReviewAgent.git_identity_guard import validated_agent_git_identity
from Pipeline.TaskReviewAgent.local_rehearsal import LocalRunContext, LocalRehearsalError
from Pipeline.TaskReviewAgent.tests.gauntlet_end_to_end_smoke_test import FAST, STANDARD, TASKCONTROL_STUB

SOURCE_VIEW = Path(os.environ.get("NSC_GAUNTLET_VIEW_SOURCE_ROOT", str(VIEW_ROOT)))
SPEC = importlib.util.spec_from_file_location("local_rehearsal_view_server", SOURCE_VIEW / "server.py")
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def render_in_node(snapshot: dict, *, html_path: Path | None = None,
                   checked: dict[str, bool] | None = None) -> dict:
    """Execute the shipped view's graph-label, legend and detail functions."""
    html = (html_path or SOURCE_VIEW / "index.html").read_text(encoding="utf-8")
    states = re.search(r"^const STATES = \{.*?^\};", html, re.MULTILINE | re.DOTALL)
    assert states is not None
    names = (
        "esc", "escAttr", "duration", "labelFor", "visible", "buildElements",
        "updateLegend", "githubIssueNavigation", "githubPullRequestNavigation",
        "tokenCostDetail", "humanApprovalControl", "showDetail",
    )
    functions = []
    for name in names:
        match = re.search(rf"^function {name}\b.*?^\}}", html, re.MULTILINE | re.DOTALL)
        assert match is not None, name
        functions.append(match.group(0))
    # The shipped view carries module-level state the extracted functions read.
    # Take every single-line declaration verbatim so a new one added upstream
    # cannot silently turn this into a ReferenceError instead of a real result.
    # Excluded: names this harness defines itself, and `cy`, whose multi-line
    # cytoscape() construction cannot run outside a browser.
    provided = {"snapshot", "mode", "elements", "document", "makeElement", "input", "cy", "checkedById"}
    declarations = [
        declaration
        for declaration, name in re.findall(
            r"^((?:const|let) ([A-Za-z_][A-Za-z0-9_]*) = [^\n]*;)$", html, re.MULTILINE
        )
        if name not in provided
    ]
    code = r"""
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const checkedById = input.checked;
const elements = new Map();
const makeElement = () => ({innerHTML:'', textContent:'', hidden:true, checked:false,
  children:[], style:{}, classList:{toggle(){}},
  appendChild(child){this.children.push(child);}, addEventListener(){}});
const document = {getElementById(id) {
  // Filter checkboxes default to unchecked; a caller can switch one on to
  // isolate a filter from the state gate that would otherwise mask it.
  if (!elements.has(id)) {
    const element = makeElement();
    if (id in checkedById) element.checked = checkedById[id];
    elements.set(id, element);
  }
  return elements.get(id);
},
// The shipped detail pane looks up its own optional controls to bind handlers,
// after it has already written innerHTML. Both call sites are null-guarded, so
// reporting "control absent" exercises the rendered output without a DOM.
querySelector() { return null; },
querySelectorAll() { return []; },
createElement: makeElement};
const mode = 'deps';
let snapshot = input.snapshot;
""" + states.group(0) + "\n" + "\n".join(declarations) + "\n" + "\n".join(functions) + r"""
updateLegend(snapshot);
showDetail(snapshot.tasks[0].id);
process.stdout.write(JSON.stringify({
  markerVisible: !document.getElementById('mode-marker').hidden,
  detail: document.getElementById('detail').innerHTML,
  runstats: document.getElementById('runstats').innerHTML,
  legend: document.getElementById('legend').children.map(child => ({
    text: child.textContent, html: child.innerHTML, title: child.title || '',
  })),
  graph: buildElements(snapshot.tasks),
  issue: githubIssueNavigation(snapshot.tasks[0]),
  pullRequest: githubPullRequestNavigation(snapshot.tasks[0]),
}));
"""
    result = subprocess.run(
        [os.environ.get("NSC_NODE", "node"), "-e", code],
        input=json.dumps({"snapshot": snapshot, "checked": checked or {}}),
        text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


class LocalRehearsalViewTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get("NSC_GAUNTLET_VIEW_TEST_TEMP", tempfile.gettempdir())).resolve()
        self.root = parent / ("local-view-" + uuid.uuid4().hex)
        self.source = self.root / "source"
        self.source.mkdir(parents=True)
        (self.source / "Tasks").mkdir()
        task = FAST.contract()
        self.task_id = task["id"]
        (self.source / "Tasks" / f"{self.task_id}.yaml").write_text(
            json.dumps(task, indent=2) + "\n", encoding="utf-8", newline="\n",
        )
        graph = self.source / "Pipeline" / "TaskGraph"
        graph.mkdir(parents=True)
        (graph / "taskcontrol.py").write_text(TASKCONTROL_STUB, encoding="utf-8", newline="\n")
        self.git("init", "--initial-branch=fixture")
        name, email = validated_agent_git_identity()
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        self.git("config", "core.autocrlf", "true")
        self.git("add", "--", f"Tasks/{self.task_id}.yaml", "Pipeline/TaskGraph/taskcontrol.py")
        self.git("commit", "-m", "Commit disposable local-view contract")
        self.context = self.create_run("view-a")

    def tearDown(self):
        # Only the exact UUID directory created by this fixture may be removed.
        if self.root.name.startswith("local-view-") and self.root.is_dir():
            def remove_readonly(function, path, error):
                resolved = Path(path).resolve()
                if not resolved.is_relative_to(self.root.resolve()) or not isinstance(error, PermissionError):
                    raise error
                # Git objects are read-only on Windows even in a disposable repo.
                resolved.chmod(resolved.stat().st_mode | stat.S_IWRITE)
                function(path)
            shutil.rmtree(self.root, onexc=remove_readonly)

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.source), *args], capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def create_run(self, run_id, task_ids=None):
        return LocalRunContext.open(
            source=self.source, checkout_root=self.root / "runs", run_id=run_id,
            task_ids=task_ids or [self.task_id], provider_profile="all-claude", create=True,
        )

    def view(self, context=None):
        context = context or self.context
        if os.environ.get("NSC_GAUNTLET_VIEW_SOURCE_ROOT") and "local_run_root" not in inspect.signature(server.Snapshot).parameters:
            # Paired base proof: exercise the old observable reader against the
            # same durable artifacts, so failures reveal missing local behavior
            # rather than stopping at an unsupported constructor argument.
            return server.Snapshot(self.source / "Tasks", self.root / "runs")
        return server.Snapshot(self.source / "Tasks", self.root / "runs", local_run_root=context.run_root)

    def start(self, context=None, worker="view-worker"):
        context = context or self.context
        context.record_stage(self.task_id, "architect_admission")
        result = context.workflow_service(worker).acquire_agent_lease(
            task=context.manifest["contracts"][self.task_id], source_head=context.source_head,
            branch="local/view-fixture", checkout_path=str(context.checkout_root / self.task_id),
            planned_approach="Exercise the local view with a committed fixture contract.",
            expected_validation="Deterministic local visualizer regression.",
        )
        self.assertEqual(result["status"], "acquired")
        lease = context.task_state(self.task_id)["lease_id"]
        context.record_stage(
            self.task_id, "implementation", worker_id=worker, lease_id=lease,
            provider="claude", action="run_execution_crew", elapsed_seconds=7,
            stage_elapsed_seconds=5,
        )
        return lease

    def graph_states(self, rendered):
        return {node["data"]["id"]: node["data"]["state"] for node in rendered["graph"]["nodes"]}

    def test_local_run_states_reach_the_graph_and_only_hidden_keeps_one_out(self):
        view = self.view()
        # Every state a local run actually passes through must produce a node.
        self.assertEqual(self.graph_states(render_in_node(view.build())), {self.task_id: "ready"})
        lease = self.start()
        self.assertEqual(self.graph_states(render_in_node(view.build())), {self.task_id: "active"})
        self.context.finish(self.task_id, "view-worker", lease, {"crew_status": "review_ready"})
        terminal = view.build()
        self.assertEqual(terminal["tasks"][0]["state"], "local_review_ready")
        self.assertEqual(self.graph_states(render_in_node(terminal)),
                         {self.task_id: "local_review_ready"})
        # A retired contract stays out on the shipped `hidden` set alone: the
        # cancelled filter is switched on, so nothing else can exclude it.
        terminal["tasks"].append(dict(terminal["tasks"][0], id=f"{self.task_id}-retired",
                                      state="cancelled", depends_on=[]))
        rendered = render_in_node(terminal, checked={"f-cancelled": True})
        self.assertEqual(self.graph_states(rendered), {self.task_id: "local_review_ready"})

    def test_applied_decomposition_parent_rolls_up_available_children(self):
        view = self.view()
        local = json.loads(json.dumps(self.context.snapshot()))
        child_id = "NSC-932"
        parent = local["contracts"][self.task_id]
        parent.update(
            kind="feature",
            execution_scope="not_applicable",
            decomposition_state="decomposed",
            decomposition_children=[child_id],
        )
        child = json.loads(json.dumps(parent))
        child.update(
            id=child_id,
            title="Generated available child",
            kind="implementation",
            execution_scope="direct_implementation",
            decomposition_state="not_applicable",
            decomposition_children=[],
            parent=self.task_id,
        )
        local["contracts"][child_id] = child
        parent_record = local["tasks"][self.task_id]
        parent_record.update(state="local_review_ready", pipeline_stage="decomposition_applied")
        child_record = json.loads(json.dumps(parent_record))
        child_record.update(
            task_id=child_id,
            state="available",
            pipeline_stage="available",
            worker_id=None,
            lease_id=None,
        )
        local["tasks"][child_id] = child_record

        with mock.patch.object(view, "local_snapshot", return_value=local):
            snapshot = view.build()
        by_id = {task["id"]: task for task in snapshot["tasks"]}
        aggregate = by_id[self.task_id]
        self.assertEqual(aggregate["state"], "aggregate")
        self.assertEqual(aggregate["local_state"], "local_review_ready")
        self.assertEqual(aggregate["progress"]["phase"], "decomposition_children")
        self.assertEqual(aggregate["progress"]["children_total"], 1)
        self.assertEqual(aggregate["progress"]["children_by_state"], {"ready": 1})
        self.assertEqual(by_id[child_id]["state"], "ready")
        rendered = render_in_node(snapshot)
        parent_node = next(
            node for node in rendered["graph"]["nodes"] if node["data"]["id"] == self.task_id
        )
        self.assertIn("DECOMPOSED · CHILDREN IN PROGRESS", parent_node["data"]["label"])
        self.assertIn("1 unstarted", parent_node["data"]["label"])
        self.assertNotIn("WORK TYPE UNAVAILABLE", parent_node["data"]["label"])
        self.assertTrue(any("Decomposed Parent" in item["html"] for item in rendered["legend"]))

        local["tasks"][self.task_id]["state"] = "failed"
        with mock.patch.object(view, "local_snapshot", return_value=local):
            failed = view.build()
        failed_parent = next(task for task in failed["tasks"] if task["id"] == self.task_id)
        self.assertEqual(failed_parent["state"], "failed")

    def test_task_working_is_rendered_before_local_review_ready(self):
        view = self.view()
        self.assertEqual(view.build()["tasks"][0]["state"], "ready")
        lease = self.start()
        working = view.build()
        self.assertEqual(working["tasks"][0]["state"], "active")
        with mock.patch.object(view, "taskgraph_states", side_effect=AssertionError("No local conformance")), \
             mock.patch.object(server, "newest_autonomous_run", side_effect=AssertionError("No production discovery")):
            working = view.build()
            self.assertEqual(working["tasks"][0]["state"], "active")
            self.assertEqual(working["scheduler"]["active"], [self.task_id])
            self.assertFalse(working["run"]["complete"])
            self.assertIsNone(working["tasks"][0]["taskgraph"])
            rendered = render_in_node(working)
            self.assertTrue(rendered["markerVisible"])
            self.assertIn("Task Working", rendered["detail"])
            label = rendered["graph"]["nodes"][0]["data"]["label"]
            self.assertNotIn("LOCAL REHEARSAL", label)
            self.assertIn(working["tasks"][0]["title"], label)
            self.assertIn("[IMPLEMENTATION]", label)
            for text in ("view-worker", "all-claude", "claude", "implementation", "7s"):
                self.assertIn(text, rendered["detail"])
            self.context.finish(self.task_id, "view-worker", lease, {"crew_status": "review_ready"})
            terminal = view.build()
        self.assertEqual(terminal["tasks"][0]["state"], "local_review_ready")
        self.assertFalse(terminal["run"]["complete"])
        self.assertEqual(terminal["scheduler"]["active"], [])
        rendered = render_in_node(terminal)
        self.assertIn("Local Review Ready", rendered["detail"])
        self.assertNotIn("Task Complete", rendered["detail"])
        self.assertNotIn("graph complete", rendered["runstats"])

    def test_selected_run_cannot_consume_other_run_events(self):
        other = self.create_run("view-b")
        view = self.view()
        initial = view.fingerprint()
        self.start(other, worker="other-worker")
        self.assertEqual(view.fingerprint(), initial)
        self.assertEqual(view.build()["tasks"][0]["state"], "ready")
        second = self.view(other).build()
        self.assertIsInstance(second["tasks"][0]["worker"], dict)
        self.assertEqual(second["tasks"][0]["worker"]["worker_id"], "other-worker")
        self.assertEqual(second["tasks"][0]["state"], "active")
        self.assertNotIn("other-worker", json.dumps(view.build()))
        self.start(worker="own-worker")
        self.assertNotEqual(view.fingerprint(), initial)

    def test_local_navigation_rejects_even_plausible_issue_and_pr_identity(self):
        self.start()
        snapshot = self.view().build()
        self.assertIsNone(snapshot["run"]["repository"])
        worker = snapshot["tasks"][0]["worker"]
        self.assertIsInstance(worker, dict)
        for key in ("issue_url", "issue_number", "pull_request_url", "pull_request_number"):
            self.assertIsNone(worker[key])
        # Prove the browser fence independently from the backend projection.
        snapshot["run"]["repository"] = "cathode26/NoSafeCircle-Homework-Rehearsal"
        worker.update(issue_number=112, pull_request_number=116,
            issue_url="https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/112",
            pull_request_url="https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/pull/116")
        rendered = render_in_node(snapshot)
        self.assertIn("No GitHub Issue — local rehearsal", rendered["issue"])
        self.assertEqual(rendered["pullRequest"], "")
        self.assertNotIn("href=", rendered["detail"])

    def test_usage_comes_from_selected_validated_local_event(self):
        self.start()
        self.context.record_stage(
            self.task_id, "implementation", worker_id="view-worker", turn=1,
            provider="claude", model="recorded-model", role="implementer",
            provider_usage={"total_tokens": 31, "input_tokens": 21, "output_tokens": 10, "estimated_cost_usd": 0.25},
        )
        self.context.record_stage(
            self.task_id, "implementation", worker_id="view-worker", turn=1,
            provider="claude", model="recorded-model", role="validator",
            provider_usage={"total_tokens": 17, "input_tokens": 12, "output_tokens": 5, "estimated_cost_usd": 0.15},
        )
        view = self.view()
        snapshot = view.build()
        self.assertEqual(snapshot["tasks"][0]["token_cost"]["recorded_total_tokens"], 48)
        self.assertEqual(snapshot["tasks"][0]["token_cost"]["recorded_cost_usd"], 0.40)
        self.assertEqual(view.build()["tasks"][0]["token_cost"]["recorded_total_tokens"], 48)
        rendered = render_in_node(snapshot)
        self.assertIn("$0.25", rendered["detail"])
        self.assertIn("$0.15", rendered["detail"])
        self.assertIn("Tokens used so far: 48", rendered["detail"])

    def test_tampered_durable_state_fails_closed(self):
        view = self.view()
        state = json.loads(self.context.state_path.read_text(encoding="utf-8"))
        state["tasks"][self.task_id]["state"] = "agent_working"
        self.context.state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(LocalRehearsalError):
            view.build()

    def test_shared_architect_usage_is_allocated_once_across_exact_named_tasks(self):
        second = STANDARD.contract()
        second_path = self.source / "Tasks" / f"{second['id']}.yaml"
        second_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
        self.git("add", "--", f"Tasks/{second['id']}.yaml")
        self.git("commit", "-m", "Add second disposable task for shared usage")
        task_ids = sorted([self.task_id, second["id"]])
        context = self.create_run("shared-view", task_ids)
        fields = dict(task_ids=task_ids, agent_runtime_run_id="architect-batch-1", provider="claude",
                      model="recorded-model", role="polling_architect", provider_call_status="succeeded",
                      provider_usage={"total_tokens": 17, "estimated_cost_usd": 0.12})
        context.record_event("architect_provider_call", **fields)
        context.record_event("architect_provider_call", **fields)  # Duplicate observation, same real call.
        other = self.create_run("unselected-shared-view", task_ids)
        other.record_event("architect_provider_call", **{**fields, "provider_usage": {"total_tokens": 9999}})
        snapshot = self.view(context).build()
        usages = [task["token_cost"] for task in snapshot["tasks"]]
        self.assertEqual([usage["recorded_total_tokens"] for usage in usages], [9, 8])
        self.assertEqual(sum(usage["recorded_cost_usd"] for usage in usages), 0.12)
        self.assertTrue(all(usage["total_calls"] == 1 for usage in usages))
        self.assertTrue(all(len(usage["shared_calls"]) == 1 for usage in usages))
        rendered = render_in_node(snapshot)
        self.assertIn("Shared call architect-batch-1", rendered["detail"])
        self.assertIn("polling_architect", rendered["detail"])
        self.assertIn("claude", rendered["detail"])

    def test_missing_shared_architect_usage_remains_unavailable(self):
        self.context.record_event("architect_provider_call", task_ids=[self.task_id],
                                  agent_runtime_run_id="architect-missing-usage", provider="claude",
                                  role="polling_architect", provider_usage=None)
        usage = self.view().build()["tasks"][0]["token_cost"]
        self.assertEqual(usage["total_calls"], 1)
        self.assertEqual(usage["missing_usage_calls"], 1)
        self.assertIsNone(usage["recorded_total_tokens"])
        self.assertIsNone(usage["recorded_cost_usd"])
        self.assertFalse(usage["usage_complete"])
        self.assertEqual(usage["cost_label"], "unavailable")

    def test_token_only_receipt_does_not_invent_cost(self):
        self.context.record_stage(
            self.task_id, "execution_crew", turn=1, provider="claude", role="execution_crew",
            provider_usage={"total_tokens": 48},
        )
        usage = self.view().build()["tasks"][0]["token_cost"]
        self.assertEqual(usage["recorded_total_tokens"], 48)
        self.assertIsNone(usage["recorded_cost_usd"])
        self.assertEqual(usage["cost_label"], "unavailable")

    def test_changed_source_contract_makes_view_stale(self):
        view = self.view()
        task_path = self.source / "Tasks" / f"{self.task_id}.yaml"
        task = json.loads(task_path.read_text(encoding="utf-8"))
        task["title"] = "Changed contract after admission"
        task_path.write_text(json.dumps(task) + "\n", encoding="utf-8")
        self.git("add", "--", f"Tasks/{self.task_id}.yaml")
        self.git("commit", "-m", "Change disposable source identity")
        with self.assertRaises(LocalRehearsalError):
            view.build()


if __name__ == "__main__":
    unittest.main()
