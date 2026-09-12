#!/usr/bin/env python3
"""Regression-only component checks of local activity data and shipped rendering.

The already-validated snapshot boundary is replaced by ordinary in-memory data.
No Git fixture, provider, container, real run, or Unity asset is touched.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock


VIEW = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VIEW))
SPEC = importlib.util.spec_from_file_location("third_local_activity_server", VIEW / "server.py")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def local_payload(*states):
    ids = [f"NSC-{1001 + index}" for index in range(len(states))]
    return {
        "execution_mode": "local_rehearsal", "run_id": "activity-fixture",
        "source_commit": "a" * 40, "source_tree": "b" * 40,
        "provider_profile": "all-claude", "max_capacity": 7,
        "status": "blocked" if "blocked" in states else "running", "events": [],
        "contracts": {task_id: {"id": task_id, "title": "Inspect local candidate"} for task_id in ids},
        "tasks": {task_id: {"state": state} for task_id, state in zip(ids, states)},
    }


def project(payload):
    view = server.Snapshot(VIEW / "unused-contracts", VIEW / "unused-state",
                           local_run_root=VIEW / "unused-run")
    before = copy.deepcopy(payload)
    with mock.patch.object(view, "local_snapshot", return_value=payload) as read, \
            mock.patch.object(server.time, "time", return_value=1000):
        result = view.build()
    read.assert_called_once_with()
    if payload != before:
        raise AssertionError("Activity projection mutated its admitted input")
    return result


def render_activity(activity, *, then_missing=False, advance_ms=0):
    html = (VIEW / "index.html").read_text(encoding="utf-8")
    functions = []
    for name in ("esc", "pipelineDuration", "validPipelineActivity", "showActivityUnavailable", "renderPipelineActivity", "updatePipelineTimers"):
        match = re.search(rf"^function {name}\b.*?^\}}", html, re.MULTILINE | re.DOTALL)
        if match:
            functions.append(match.group(0))
        elif name != "validPipelineActivity":
            raise AssertionError(f"Missing shipped function: {name}")
    script = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let clock = 1000;
const performance = {now: () => clock};
const nodes = new Map();
let missing = false;
const document = {getElementById(id) {
  if (missing && !['pipeline-headline', 'pipeline-body'].includes(id)) {
    throw new Error('Timer accessed removed activity element: ' + id);
  }
  if (!nodes.has(id)) nodes.set(id, {textContent:'', innerHTML:'', classList:{toggle(){}}});
  return nodes.get(id);
}};
document.getElementById('pipeline-headline').textContent = 'Reading durable run artifacts…';
let pipelineSample = null;
let pipelineReceivedAt = 0;
""" + "\n".join(functions) + r"""
renderPipelineActivity(input.activity);
clock += input.advance_ms;
if (input.then_missing) {
  missing = true;
  renderPipelineActivity(undefined);
}
updatePipelineTimers();
process.stdout.write(JSON.stringify({
  headline: document.getElementById('pipeline-headline').textContent,
  body: document.getElementById('pipeline-body').innerHTML,
  sampleCleared: pipelineSample === null,
  stageElapsed: nodes.get('pipeline-stage-elapsed')?.textContent,
  runElapsed: nodes.get('pipeline-run-elapsed')?.textContent,
}));
"""
    result = subprocess.run(
        [os.environ.get("NSC_NODE", "node"), "-e", script],
        input=json.dumps({"activity": activity, "then_missing": then_missing, "advance_ms": advance_ms}),
        text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def load_sequence(failures):
    """Execute the shipped async loader with ordinary failed/successful requests."""
    html = (VIEW / "index.html").read_text(encoding="utf-8")
    functions = []
    for name in ("validPipelineActivity", "validateStateSnapshot", "loadInitialState"):
        match = re.search(rf"^(?:async )?function {name}\b.*?^\}}", html, re.MULTILINE | re.DOTALL)
        if match:
            functions.append(match.group(0))
    script = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const failures = input.failures;
const timers = new Map();
let nextTimer = 0, attempts = 0, renders = 0, streams = 0, snapshot = null;
const messages = [], live = [];
const setTimeout = (callback, delay) => {const id = ++nextTimer; timers.set(id, {callback, delay}); return id;};
const clearTimeout = id => timers.delete(id);
const showActivityUnavailable = message => messages.push(message);
const setLive = value => live.push(value);
const render = () => {renders++;};
const startStateStream = () => {streams++;};
const fetch = async (url, options) => {
  if (url !== '/api/state' || !options.signal) throw new Error('Missing bounded state request');
  const kind = failures[attempts++];
  if (kind === 'network') throw new TypeError('Failed to fetch');
  return {ok: kind !== 'http', status: kind === 'http' ? 503 : 200, json: async () => {
    if (kind === 'json') throw new SyntaxError('Unexpected response text');
    return kind === 'shape' ? {message:'unavailable'} : {tasks:[],run:{},pipeline_activity:input.activity};
  }};
};
""" + "\n".join(functions) + r"""
(async () => {
  await loadInitialState();
  while (timers.size) {
    const [id, timer] = timers.entries().next().value;
    if (timer.delay !== 3000) throw new Error('Request deadline not cleared');
    timers.delete(id);
    await timer.callback();
  }
  process.stdout.write(JSON.stringify({attempts,renders,streams,messages,live,hasSnapshot:snapshot !== null}));
})().catch(error => {console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [os.environ.get("NSC_NODE", "node"), "-e", script],
        input=json.dumps({"failures": failures, "activity": project(local_payload("agent_working"))["pipeline_activity"]}),
        text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def partial_activity():
    """A truthy response that used to render undefined values and live clocks."""
    return {
        "headline": "malformed but truthy", "counters": {}, "provider_call_open": False,
        "recent_activity": [], "stage_elapsed_seconds": 5, "run_elapsed_seconds": 10,
        "last_event_age_seconds": 0, "stale_after_seconds": 60,
    }


def activity_transition(valid_activity, replacement, *, transport, nonfinite_field=None,
                        http_activities=None, stale_callbacks=False):
    """Exercise shipped activity and HTTP/SSE callbacks with a detached fake DOM."""
    html = (VIEW / "index.html").read_text(encoding="utf-8")
    functions = []
    for name in ("esc", "pipelineDuration", "validPipelineActivity", "validateStateSnapshot", "showActivityUnavailable",
                 "renderPipelineActivity", "updatePipelineTimers", "loadInitialState", "startStateStream"):
        match = re.search(rf"^(?:async )?function {name}\b.*?^\}}", html, re.MULTILINE | re.DOTALL)
        if match:
            functions.append(match.group(0))
        elif name not in ("validPipelineActivity", "validateStateSnapshot"):
            raise AssertionError(f"Missing shipped function: {name}")
    script = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
let clock = 1000, pipelineSample = null, pipelineReceivedAt = 0, snapshot = null, stateStream = null;
let timerWrites = 0, stream = null, nextTimer = 0, requests = 0, renders = 0;
const performance = {now: () => clock};
const nodes = new Map(), timers = new Map(), live = [], errors = [], streams = [];
const timerIds = ['pipeline-stage-elapsed', 'pipeline-run-elapsed', 'pipeline-freshness'];
function makeNode(id) {
  let text = '', html = '';
  return {
    title: '', classList:{toggle(){}},
    get textContent() {return text;},
    set textContent(value) {text = String(value); if (timerIds.includes(id)) timerWrites++;},
    get innerHTML() {return html;},
    set innerHTML(value) {
      html = String(value);
      if (id === 'pipeline-body') {
        for (const timerId of timerIds) nodes.delete(timerId);
        for (const match of html.matchAll(/id="([^"]+)"/g)) nodes.set(match[1], makeNode(match[1]));
      }
    },
  };
}
for (const id of ['pipeline-headline', 'pipeline-body']) nodes.set(id, makeNode(id));
const document = {getElementById: id => nodes.get(id) || null};
document.getElementById('pipeline-headline').textContent = 'Reading durable run artifacts…';
const setTimeout = (callback, delay) => {const id = ++nextTimer; timers.set(id, {callback, due:clock + delay}); return id;};
const clearTimeout = id => timers.delete(id);
const setLive = value => live.push(value);
const render = snap => {
  renders++;
  if (input.transport === 'sse-render' && renders > 1) throw new Error('Synthetic render failure');
  renderPipelineActivity(snap.pipeline_activity);
};
const showDetail = () => {};
const cy = {$: () => ({nonempty: () => false})};
class EventSource {
  constructor(url) {
    if (url !== '/api/stream') throw new Error('Unexpected stream URL');
    this.closed = false; this.closeCalls = 0; stream = this; streams.push(this);
    setTimeout(() => {if (!this.closed && this.onopen) this.onopen();}, 0);
  }
  close() {this.closed = true; this.closeCalls++;}
}
const response = activity => ({tasks:[], run:{}, pipeline_activity:activity});
const httpActivities = input.http_activities || (input.transport === 'http'
  ? [input.replacement, input.replacement, input.replacement] : [input.valid_activity]);
const fetch = async url => {
  if (url !== '/api/state') throw new Error('Unexpected request URL');
  if (requests >= httpActivities.length) throw new Error('Unexpected additional HTTP request');
  const activity = httpActivities[requests++];
  return {ok:true, status:200, json:async () => response(activity)};
};
async function advanceClock(milliseconds) {
  const target = clock + milliseconds;
  for (let limit = 0; ; limit++) {
    const pending = [...timers.entries()].filter(([id, timer]) => timer.due <= target)
      .sort((a, b) => a[1].due - b[1].due)[0];
    if (!pending) break;
    if (limit >= 100) throw new Error('Unbounded callback scheduling');
    const [id, timer] = pending;
    timers.delete(id); clock = timer.due;
    await timer.callback();
  }
  clock = target;
  updatePipelineTimers();
}
""" + "\n".join(functions) + r"""
(async () => {
  if (input.nonfinite_field) input.replacement[input.nonfinite_field] = Infinity;
  if (input.transport === 'direct') renderPipelineActivity(input.valid_activity);
  else if (input.transport !== 'http') await loadInitialState();
  const initialSampleAccepted = input.transport === 'http' ? null : pipelineSample === input.valid_activity;
  try {
    if (input.transport === 'direct') {
      renderPipelineActivity(input.replacement);
    } else if (input.transport === 'http') {
      await loadInitialState();
    } else {
      stream.onopen();
      const data = input.transport === 'sse-json' ? '{invalid JSON'
        : JSON.stringify(input.transport === 'sse-shape' ? {message:'missing task/run data'} : response(input.replacement));
      stream.onmessage({data});
      if (input.stale_callbacks) {
        stream.onopen();
        stream.onmessage({data:JSON.stringify(response(input.valid_activity))});
      }
    }
  } catch (error) {errors.push(error.name + ': ' + error.message);}
  const writesBeforeAdvance = timerWrites;
  try {await advanceClock(12000);} catch (error) {errors.push(error.name + ': ' + error.message);}
  process.stdout.write(JSON.stringify({
    headline:document.getElementById('pipeline-headline').textContent,
    body:document.getElementById('pipeline-body').innerHTML,
    sampleCleared:pipelineSample === null, receivedAt:pipelineReceivedAt, initialSampleAccepted,
    timerWritesAfterAdvance:timerWrites - writesBeforeAdvance,
    stageElapsed:nodes.get('pipeline-stage-elapsed')?.textContent ?? null,
    runElapsed:nodes.get('pipeline-run-elapsed')?.textContent ?? null,
    live, errors, requests, renders, snapshotCleared:snapshot === null,
    streamsCreated:streams.length, streamsClosed:streams.filter(item => item.closed).length,
    streamCloseCalls:streams.reduce((total, item) => total + item.closeCalls, 0),
    currentStream:stateStream === null ? null : streams.indexOf(stateStream), pendingTimers:timers.size,
  }));
})().catch(error => {console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        [os.environ.get("NSC_NODE", "node"), "-e", script],
        input=json.dumps({"valid_activity": valid_activity, "replacement": replacement,
                          "transport": transport, "nonfinite_field": nonfinite_field,
                          "http_activities": http_activities, "stale_callbacks": stale_callbacks}),
        text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


class LocalPipelineActivityTests(unittest.TestCase):
    def test_blocked_tasks_outrank_ready_tasks_in_headline(self):
        activity = project(local_payload(
            "blocked", "blocked", "blocked", "blocked", "blocked",
            "agent_ready", "agent_ready", "agent_ready",
        ))["pipeline_activity"]
        self.assertEqual(activity["stage"], "local_attention")
        self.assertEqual(activity["headline"], "Local pipeline blocked")

    def test_active_workers_outrank_blocked_run_status(self):
        value = project(local_payload("agent_working", "blocked", "agent_ready", "local_review_ready"))
        self.assertEqual(value["run"]["status"], "blocked")
        activity = value["pipeline_activity"]
        self.assertEqual(activity["stage"], "local_working")
        self.assertFalse(activity["terminal"])
        self.assertEqual(activity["counters"]["active_workers"], 1)
        self.assertEqual(activity["counters"]["awaiting_worker"], 1)
        self.assertEqual(activity["counters"]["local_review_ready"], 1)
        self.assertEqual(activity["headline"], "Local task work in progress")
        rendered = render_activity(activity)
        self.assertNotIn("Reading durable", rendered["headline"])
        self.assertNotIn("Local review ready", rendered["body"])
        self.assertNotIn("Complete in scope", rendered["body"])

    def test_local_review_ready_is_not_graph_completion(self):
        activity = project(local_payload("local_review_ready", "local_review_ready"))["pipeline_activity"]
        self.assertEqual(activity["stage"], "local_review_ready")
        self.assertTrue(activity["terminal"])
        self.assertEqual(activity["counters"]["local_review_ready"], 2)
        self.assertIsNone(activity["counters"]["completed"])
        self.assertEqual(activity["headline"], "Local pipeline idle")
        self.assertNotIn("Graph complete", json.dumps(activity))
        self.assertFalse(project(local_payload("local_review_ready"))["run"]["complete"])

    def test_waiting_and_attention_states_do_not_claim_worker_activity(self):
        for states, expected in (
            (("available",), "local_waiting"),
            (("agent_ready", "blocked"), "local_attention"),
            (("blocked",), "local_attention"),
            (("failed", "human_action_required"), "local_attention"),
            ((), "unknown"),
        ):
            with self.subTest(states=states):
                activity = project(local_payload(*states))["pipeline_activity"]
                self.assertEqual(activity["stage"], expected)
                self.assertFalse(activity["terminal"])
                self.assertEqual(activity["counters"]["active_workers"], 0)

    def test_unknown_times_and_scheduler_counters_stay_unavailable(self):
        activity = project(local_payload("available"))["pipeline_activity"]
        for key in ("stage_elapsed_seconds", "run_elapsed_seconds", "last_event_age_seconds"):
            self.assertIsNone(activity[key], key)
        for key in ("completed", "dependency_blocked", "eligible_or_queued",
                    "architect_calls_completed", "worker_launches", "wakeups"):
            self.assertIsNone(activity["counters"][key], key)
        self.assertEqual(activity["provider_profile"], "all-claude")
        self.assertEqual(activity["provider"], "unavailable")
        self.assertEqual(activity["model"], "unavailable")

    def test_recent_local_events_supply_freshness_and_recorded_architect_identity(self):
        payload = local_payload("agent_working")
        payload["events"] = [{
            "event": "architect_provider_call", "task_id": None,
            "timestamp_utc": "1970-01-01T00:16:35Z",
            "fields": {"provider": "claude", "model": "fixture-model"},
        }]
        payload["tasks"]["NSC-1001"]["stage_elapsed_seconds"] = 12
        activity = project(payload)["pipeline_activity"]
        self.assertEqual(activity["last_event_age_seconds"], 5)
        self.assertEqual(activity["stage_elapsed_seconds"], 12)
        self.assertEqual(activity["provider"], "claude")
        self.assertEqual(activity["model"], "fixture-model")
        self.assertEqual(len(activity["recent_activity"]), 1)
        self.assertFalse(activity["provider_call_open"])

    def test_missing_activity_clears_initial_placeholder(self):
        rendered = render_activity(None)
        self.assertEqual(rendered["headline"], "Pipeline activity unavailable")
        self.assertTrue(rendered["sampleCleared"])
        self.assertNotIn("Reading durable", rendered["headline"])

    def test_missing_activity_after_valid_sample_stops_old_timers(self):
        activity = project(local_payload("agent_working"))["pipeline_activity"]
        rendered = render_activity(activity, then_missing=True)
        self.assertEqual(rendered["headline"], "Pipeline activity unavailable")
        self.assertTrue(rendered["sampleCleared"])

    def test_terminal_sample_does_not_advance_stage_or_run_clocks(self):
        activity = project(local_payload("local_review_ready"))["pipeline_activity"]
        activity.update(stage_elapsed_seconds=25, run_elapsed_seconds=40)
        rendered = render_activity(activity, advance_ms=12000)
        self.assertEqual(rendered["stageElapsed"], "0m 25s")
        self.assertEqual(rendered["runElapsed"], "0m 40s")

    def test_unavailable_stage_and_run_fragments_are_independently_omitted(self):
        base = self.valid_activity_with_clocks()
        cases = (
            (None, None, False, False, False),
            (25, None, True, False, False),
            (None, 40, False, True, False),
            (25, 40, True, True, True),
        )
        for stage, run, has_stage, has_run, has_separator in cases:
            with self.subTest(stage=stage, run=run):
                activity = copy.deepcopy(base)
                activity.update(stage_elapsed_seconds=stage, run_elapsed_seconds=run)
                result = activity_transition(activity, activity, transport="direct")
                self.assertEqual(result["errors"], [], result)
                self.assertEqual("Current stage:" in result["body"], has_stage, result)
                self.assertEqual("Run:" in result["body"], has_run, result)
                self.assertEqual(
                    '</span> · Run: <span id="pipeline-run-elapsed">' in result["body"],
                    has_separator, result,
                )
                self.assertNotIn("Current stage: unavailable", result["body"], result)
                self.assertNotIn("Run: unavailable", result["body"], result)
                self.assertEqual(result["stageElapsed"] is not None, has_stage, result)
                self.assertEqual(result["runElapsed"] is not None, has_run, result)
        missing = copy.deepcopy(base)
        missing.update(stage_elapsed_seconds=None, run_elapsed_seconds=None)
        appeared = activity_transition(missing, base, transport="direct")
        self.assertEqual(appeared["errors"], [], appeared)
        self.assertIn('id="pipeline-stage-elapsed"', appeared["body"])
        self.assertIn('id="pipeline-run-elapsed"', appeared["body"])

    def assert_activity_unavailable(self, result):
        if result["initialSampleAccepted"] is not None:
            self.assertTrue(result["initialSampleAccepted"], result)
        self.assertEqual(result["errors"], [], result)
        self.assertEqual(result["headline"], "Pipeline activity unavailable", result)
        self.assertTrue(result["sampleCleared"], result)
        self.assertEqual(result["receivedAt"], 0, result)
        self.assertNotIn("undefined", result["body"])
        self.assertNotIn("pipeline-stage-elapsed", result["body"])
        self.assertNotIn("pipeline-run-elapsed", result["body"])
        self.assertEqual(result["timerWritesAfterAdvance"], 0, result)
        self.assertIsNone(result["stageElapsed"], result)
        self.assertIsNone(result["runElapsed"], result)

    def valid_activity_with_clocks(self):
        activity = project(local_payload("agent_working"))["pipeline_activity"]
        activity.update(stage_elapsed_seconds=25, run_elapsed_seconds=40, last_event_age_seconds=0)
        return activity

    def test_truthy_partial_activity_replaces_valid_sample_without_running_clocks(self):
        result = activity_transition(self.valid_activity_with_clocks(), partial_activity(), transport="direct")
        self.assert_activity_unavailable(result)

    def test_invalid_sse_json_clears_valid_sample_and_stops_clocks(self):
        result = activity_transition(self.valid_activity_with_clocks(), None, transport="sse-json")
        self.assert_activity_unavailable(result)
        self.assertFalse(result["live"][-1], result)

    def test_malformed_sse_activity_clears_valid_sample_and_stops_clocks(self):
        result = activity_transition(self.valid_activity_with_clocks(), partial_activity(), transport="sse")
        self.assert_activity_unavailable(result)

    def test_initial_http_partial_activity_is_unavailable_without_clocks(self):
        result = activity_transition(None, partial_activity(), transport="http")
        self.assert_activity_unavailable(result)

    def test_initial_http_invalid_activity_retries_three_times_without_opening_stream(self):
        result = activity_transition(None, partial_activity(), transport="http")
        self.assert_activity_unavailable(result)
        self.assertEqual(result["requests"], 3, result)
        self.assertEqual(result["renders"], 0, result)
        self.assertEqual(result["streamsCreated"], 0, result)
        self.assertEqual(result["streamsClosed"], 0, result)
        self.assertIsNone(result["currentStream"], result)
        self.assertTrue(result["snapshotCleared"], result)
        self.assertFalse(result["live"][-1], result)
        self.assertEqual(result["pendingTimers"], 0, result)
        self.assertIn("Reload the page", result["body"])
        self.assertNotIn("Retrying", result["body"])

    def assert_stream_closed_until_reload(self, result):
        self.assert_activity_unavailable(result)
        self.assertEqual(result["requests"], 1, result)
        self.assertEqual(result["streamsCreated"], 1, result)
        self.assertEqual(result["streamsClosed"], 1, result)
        self.assertEqual(result["streamCloseCalls"], 1, result)
        self.assertIsNone(result["currentStream"], result)
        self.assertTrue(result["snapshotCleared"], result)
        self.assertFalse(result["live"][-1], result)
        self.assertEqual(result["pendingTimers"], 0, result)
        self.assertIn("Reload the page", result["body"])

    def test_invalid_sse_frames_close_stream_and_require_reload_after_twelve_seconds(self):
        for transport, replacement in (
            ("sse", partial_activity()), ("sse-json", None), ("sse-shape", None),
            ("sse-render", self.valid_activity_with_clocks()),
        ):
            with self.subTest(transport=transport):
                result = activity_transition(self.valid_activity_with_clocks(), replacement, transport=transport)
                self.assert_stream_closed_until_reload(result)
                self.assertEqual(result["renders"], 2 if transport == "sse-render" else 1, result)

    def test_closed_stream_callbacks_cannot_restore_live_state_or_activity(self):
        result = activity_transition(
            self.valid_activity_with_clocks(), None, transport="sse-json", stale_callbacks=True,
        )
        self.assert_stream_closed_until_reload(result)
        self.assertEqual(result["renders"], 1, result)

    def test_valid_http_and_sse_frames_keep_one_stream_and_update_activity(self):
        replacement = self.valid_activity_with_clocks()
        replacement.update(headline="Updated valid worker activity", stage_elapsed_seconds=5, run_elapsed_seconds=10)
        result = activity_transition(self.valid_activity_with_clocks(), replacement, transport="sse")
        self.assertEqual(result["errors"], [], result)
        self.assertTrue(result["initialSampleAccepted"], result)
        self.assertEqual(result["headline"], replacement["headline"], result)
        self.assertEqual(result["stageElapsed"], "0m 17s", result)
        self.assertEqual(result["runElapsed"], "0m 22s", result)
        self.assertFalse(result["sampleCleared"], result)
        self.assertFalse(result["snapshotCleared"], result)
        self.assertEqual((result["requests"], result["renders"]), (1, 2), result)
        self.assertEqual((result["streamsCreated"], result["streamsClosed"], result["currentStream"]), (1, 0, 0), result)
        self.assertTrue(result["live"][-1], result)
        self.assertEqual(result["pendingTimers"], 0, result)

    def test_initial_http_invalid_activity_recovers_on_second_valid_response(self):
        result = activity_transition(
            None, None, transport="http", http_activities=[partial_activity(), self.valid_activity_with_clocks()],
        )
        self.assertEqual(result["errors"], [], result)
        self.assertFalse(result["sampleCleared"], result)
        self.assertFalse(result["snapshotCleared"], result)
        self.assertEqual((result["requests"], result["renders"]), (2, 1), result)
        self.assertEqual((result["streamsCreated"], result["streamsClosed"], result["currentStream"]), (1, 0, 0), result)
        self.assertTrue(result["live"][-1], result)
        self.assertEqual(result["pendingTimers"], 0, result)
        self.assertEqual(result["stageElapsed"], "0m 34s", result)
        self.assertEqual(result["runElapsed"], "0m 49s", result)

    def test_production_activity_without_mode_keeps_valid_clock_rendering(self):
        activity = server.build_pipeline_activity(
            manifest={"run_id": "production-fixture", "max_capacity": 20}, progress={},
            receipt=None, events=[], timeline=[], worker_events=[], tasks=[], now=1000,
        )
        self.assertNotIn("mode", activity)
        activity.update(stage_elapsed_seconds=25, run_elapsed_seconds=40)
        rendered = render_activity(activity, advance_ms=12000)
        self.assertFalse(rendered["sampleCleared"], rendered)
        self.assertEqual(rendered["headline"], activity["headline"])
        self.assertNotIn("undefined", rendered["body"])
        self.assertEqual(rendered["stageElapsed"], "0m 37s")
        self.assertEqual(rendered["runElapsed"], "0m 52s")

    def test_missing_rendered_strings_clear_sample_and_timers(self):
        for key in ("headline", "description", "provider_profile", "provider", "provider_source",
                    "model", "model_source", "call_status", "liveness"):
            with self.subTest(missing=key):
                activity = self.valid_activity_with_clocks()
                del activity[key]
                self.assert_activity_unavailable(activity_transition(
                    self.valid_activity_with_clocks(), activity, transport="direct",
                ))

    def test_malformed_field_types_clear_sample_and_timers(self):
        replacements = (
            ("headline", {}), ("terminal", "false"), ("provider_call_open", 1),
            ("stage_elapsed_seconds", -1), ("run_elapsed_seconds", "10"),
            ("last_event_age_seconds", {}), ("stale_after_seconds", None),
            ("counters.capacity", -1), ("counters.active_workers", 1.5),
            ("counters.awaiting_worker", "2"), ("candidate_count", -1),
            ("candidates", None), ("candidates", [None]),
            ("candidates", [{"task_id": 1001, "work_types": []}]),
            ("candidates", [{"task_id": "NSC-1001", "work_types": None}]),
            ("candidates", [{"task_id": "NSC-1001", "work_types": [1]}]),
            ("recent_activity", None), ("recent_activity", [None]),
            ("recent_activity", [{"headline": True, "timestamp_utc": None}]),
            ("recent_activity", [{"headline": "Saved event", "timestamp_utc": []}]),
        )
        for key, value in replacements:
            with self.subTest(field=key, value=value):
                activity = self.valid_activity_with_clocks()
                target = activity
                parts = key.split(".")
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
                self.assert_activity_unavailable(activity_transition(
                    self.valid_activity_with_clocks(), activity, transport="direct",
                ))

    def test_nonfinite_clocks_clear_sample_and_timers(self):
        for key in ("stage_elapsed_seconds", "run_elapsed_seconds", "last_event_age_seconds", "stale_after_seconds"):
            with self.subTest(field=key):
                self.assert_activity_unavailable(activity_transition(
                    self.valid_activity_with_clocks(), self.valid_activity_with_clocks(),
                    transport="direct", nonfinite_field=key,
                ))

    def test_initial_http_failure_recovers_on_automatic_retry(self):
        result = load_sequence(["http", None])
        self.assertEqual((result["attempts"], result["renders"], result["streams"]), (2, 1, 1))
        self.assertTrue(result["hasSnapshot"])
        self.assertEqual(result["live"], [False])
        self.assertIn("HTTP 503", result["messages"][0])
        self.assertIn("Retrying", result["messages"][0])

    def test_bad_json_schema_and_network_failure_stop_after_three_attempts(self):
        result = load_sequence(["json", "shape", "network"])
        self.assertEqual((result["attempts"], result["renders"], result["streams"]), (3, 0, 0))
        self.assertFalse(result["hasSnapshot"])
        self.assertEqual(len(result["messages"]), 3)
        self.assertIn("task or run data", result["messages"][1])
        self.assertIn("Reload the page to retry", result["messages"][-1])


if __name__ == "__main__":
    unittest.main()
