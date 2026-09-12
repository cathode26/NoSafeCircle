"""One deterministic report over the durable evidence of a finished graph run.

The ten-task gauntlet asks a specific question about a completed autonomous
graph run: what actually happened, proven from artifacts that outlived the
process, not from a scheduler still holding the answer in memory. This module
answers exactly that question and nothing else. It starts no task, invokes no
provider, contacts no GitHub, and writes only the report files it is told to
write.

Evidence it reads, all durable and all written by the run itself:

``manifest.json``
    The immutable run scope: run identity, source repository, the exact
    ``initial_source_commit``/``initial_source_tree``, the target task IDs,
    the excluded task IDs, the maximum capacity, and the exact provider and
    model binding for architect and execution.
``progress.json``
    Lifetime counters for the run: poll cycles, architect invocations, worker
    launches, synthetic pump calls, fallback waits, wakeups.
``graph-complete.json``
    The graph-complete receipt. Its presence, and only its presence, proves
    the run reached strict graph completion, and it carries the exact source
    commit and tree that completion was proven against.
``events.jsonl``
    The scheduler's append-only journal. Every record carries
    ``timestamp_utc``, so this is the timing spine for everything the
    scheduler does: every worker launch and finish, architect activity,
    retries, blocks, drains, withdrawals, and correlated local resume-hint
    send/consume outcomes. It accumulates across restarts, which is what makes
    an interrupted and resumed run reportable.

    It does not bracket the run. An autonomous graph run drives the scheduler
    through ``poll_capacity_batch``, never through ``PollingOrchestrator.run``,
    and the ``scheduler_started``/``scheduler_stopped`` pair is emitted only
    by the latter. So in a real autonomous run this journal has no start or
    stop record, and the earliest and latest events bound only the scheduler's
    observed activity, not the run.
``run_timeline.jsonl``
    The controller's own run-lifecycle journal (see
    :mod:`Pipeline.TaskReviewAgent.run_timeline`). This is the only durable
    record of when the run began and when graph completion was proven: the
    receipt carries no timestamp, and for the reason above the scheduler
    journal never brackets the run. When this file is absent the report falls
    back to the scheduler's first and last observed activity and says so in
    ``start_source``/``finish_source``, and reports the graph-complete moment
    as unavailable rather than guessing it from a file modification time.
worker run directories
    ``<output-root>/<task-id>/<run-id>/run.json`` records the worker's
    ``started_at_utc``; ``run_result.json`` records its ``finished_at_utc``,
    ``terminal_status``, ``exit_code``, ``source_head`` and Issue number.

    This output root is shared by every autonomous run against one checkout,
    so a task ID is not a run-local key: the same task attempted by an earlier
    run owns a directory that looks exactly like this run's. A directory is
    therefore read only when its exact ``<task-id>/<run-id>`` pair appears in
    this run's own ``worker_launched`` records. Everything else under the root
    belongs to another run and is counted as foreign, never merged in.
AgentRuntime invocation directories
    ``**/agent_runtime/<run-id>/result.json`` records one provider call each:
    role, provider, model, status, duration, and ``usage`` (input, output and
    total tokens) when the provider exposes it.

    These roots are shared and long-lived in exactly the same way, and a
    ``result.json`` carries no run identity of its own. A call is attributed to
    this run only when the run's own journal names its AgentRuntime run ID --
    see ``agent_runtime_run_id`` below. Neither a role name, nor a task name,
    nor a wall-clock range is accepted as a substitute, because all three
    match another run's call whenever two runs touch the same task.
``agent_runtime_run_id`` on scheduler events
    The run-owned provider-call index. Any journal record that carries this
    field claims that exact AgentRuntime invocation for this run;
    ``architect_provider_call`` is the record
    :meth:`PollingOrchestrator._emit_architect_provider_call` writes for every
    architect batch. A run whose journal names no provider call at all has no
    join key, and its provider-call section is reported as unavailable rather
    than filled in from whatever happens to sit under the shared roots.

    Only the scheduler's own architect calls are indexed today. A crew call
    made inside a worker's task checkout is durable, but nothing the scheduler
    owns names its invocation ID, so it is counted as unattributed and its
    tokens are not claimed by this run. That is a deliberately visible gap in
    ``claimed_call_count`` versus ``unattributed_result_count``, not a silent
    omission, and it is the opposite of adopting a neighbouring run's calls.
``runtime_configuration`` and worker launch argv
    The provider binding. The manifest is the configured selection and every
    ``worker_launched`` record carries the exact command the scheduler ran, so
    argv is the run's own statement of what it actually launched. The
    supervisor must agree across both; a disagreement is refused rather than
    resolved by preference. No role is ever filled in from what this pipeline
    usually runs.

Three rules govern every number in the output.

Nothing is inferred. A field the evidence does not contain is reported as
``unavailable`` with the reason, never filled in from a plausible neighbour.
A provider that does not publish token counts produces
``"tokens": "unavailable"``, which is a different fact from zero tokens.

Nothing is counted twice. A task that was interrupted and resumed appears
once per worker run ID. Provider calls are deduplicated by their AgentRuntime
run ID, so re-reading a directory or a resumed crew cannot inflate the count.

Nothing is mixed. Every artifact must belong to the one run being reported.
An artifact naming a different run ID, an unreadable or schema-invalid
artifact, and a receipt whose manifest hash does not match the manifest on
disk are all refusals, not warnings. Where an artifact root is legitimately
shared between runs, membership is proven from this run's own journal and the
remainder is reported as foreign or unattributed, never absorbed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

from .contracts import TASK_ID_RE
from .provider_policy import DEFAULT_SUPERVISOR_PROVIDER, SUPERVISOR_PROVIDERS

RUN_EVIDENCE_REPORT_SCHEMA_VERSION = "1.2"
UNAVAILABLE = "unavailable"

# The one approved bounded task-ID rule. Production code must never define a
# second one, because a locally invented pattern is how task-ID width policy
# drifts between modules.
_TASK_ID_RE = TASK_ID_RE
_RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Worker lifecycle in the scheduler journal. A launch opens a bounded
# interval; any of the terminal events closes it. Utilization is computed only
# from intervals that are closed by one of these, so an interval the evidence
# never closes is reported rather than assumed to have run to the end.
_LAUNCH_EVENT = "worker_launched"
_WORKER_TERMINAL_EVENTS = frozenset(
    {"worker_finished", "worker_failed", "worker_blocked", "worker_idle"}
)
# The one field a scheduler event uses to claim an AgentRuntime invocation for
# its run. It is the only accepted join key between this run and a shared
# provider-call root, so a report can never be widened by adding a heuristic
# here: an event either names the exact invocation or it does not.
_PROVIDER_CALL_IDENTITY_FIELD = "agent_runtime_run_id"
# Worker argv flags whose values are exact run bindings rather than tuning.
# The scheduler writes the complete worker command into every launch record,
# which makes argv the run's own durable statement of what it launched.
_SUPERVISOR_PROVIDER_FLAG = "--supervisor-provider"
_EXECUTION_PROVIDER_FLAG = "--execution-provider"
_EXECUTION_MODEL_FLAG = "--execution-model"
_SUPERVISOR_MODEL_FLAG = "--model"
_RESUME_HINT_SEND_EVENT = "local_resume_hint_send_completed"
_RESUME_HINT_CONSUME_EVENT = "local_resume_hint_consumed"
_HINT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# Events that mean something went wrong, stalled, or was retried. Reported
# verbatim with their timestamps; this module classifies, it does not judge.
_INCIDENT_EVENTS = frozenset(
    {
        "worker_failed",
        "worker_blocked",
        "worker_poll_failed",
        "scheduler_blocked",
        "scheduler_drain_timeout",
        "scheduler_drain_wait",
        "scheduler_locked_out",
        "scheduler_wait_observation_failure",
        "scheduler_observation_recovered",
        "scheduler_source_refresh_recovered",
        "architect_batch_discarded",
        "architect_batch_candidate_withdrawn",
        "architect_batch_capacity_truncated",
        "decomposition_policy_unprovable",
        "execution_route_wait",
        "candidate_wait_unknown_surface",
        "active_checkout_surface_unknown",
        "architect_wake_listener_unavailable",
    }
)
# A worker that stops for a human is not a failure and must never be shown as
# a pass. These are surfaced as their own category.
_HUMAN_ACTION_STATUSES = frozenset({"human_action_required"})
_SUCCESS_STATUSES = frozenset({"delivered", "completed", "graph_complete"})


class RunEvidenceError(RuntimeError):
    """Raised when the durable evidence cannot be trusted as one exact run."""


# --------------------------------------------------------------------------
# Reading and validating durable artifacts
# --------------------------------------------------------------------------


def _read_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunEvidenceError(f"{label} is missing: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunEvidenceError(f"{label} is unreadable or malformed: {path}") from exc


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    """Read an append-only journal, refusing any malformed record."""

    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RunEvidenceError(f"{label} is unreadable: {path}") from exc
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunEvidenceError(
                f"{label} line {number} is malformed JSON: {path}"
            ) from exc
        if not isinstance(value, dict):
            raise RunEvidenceError(f"{label} line {number} is not a JSON object: {path}")
        records.append(value)
    return records


def parse_utc(value: Any, *, field_name: str) -> dt.datetime:
    """Parse one exact UTC timestamp; anything else is a refusal."""

    if type(value) is not str or not value:
        raise RunEvidenceError(f"{field_name} must be exact UTC text")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise RunEvidenceError(f"{field_name} is not an ISO-8601 UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _elapsed_seconds(start: dt.datetime, finish: dt.datetime, *, label: str) -> float:
    seconds = (finish - start).total_seconds()
    if seconds < 0:
        raise RunEvidenceError(f"{label} finished before it started")
    return round(seconds, 3)


@dataclass(frozen=True)
class WorkerRun:
    """One bounded worker run, proven by its own durable directory."""

    task_id: str
    run_id: str
    worker_id: str | None
    started_at_utc: str
    finished_at_utc: str | None
    terminal_status: str | None
    exit_code: int | None
    source_head: str | None
    issue_number: int | None
    result_path: str | None

    @property
    def elapsed_seconds(self) -> float | None:
        if self.finished_at_utc is None:
            return None
        return _elapsed_seconds(
            parse_utc(self.started_at_utc, field_name="started_at_utc"),
            parse_utc(self.finished_at_utc, field_name="finished_at_utc"),
            label=f"worker run {self.run_id}",
        )


@dataclass(frozen=True)
class WorkerLaunch:
    """One worker attempt this exact run launched, proven by its journal.

    The scheduler run ID is the only run-local key a worker directory has, so
    this record is what makes ``<output-root>/<task-id>/<run-id>`` readable as
    "an attempt of this run" instead of "an attempt of some run".
    """

    task_id: str
    run_id: str
    worker_id: str | None
    launched_at_utc: str
    argv: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, str | None, tuple[str, ...]]:
        return (self.task_id, self.worker_id, self.argv)


@dataclass(frozen=True)
class ProviderCallReference:
    """This run's own claim on one AgentRuntime invocation."""

    agent_run_id: str
    event: str
    timestamp_utc: str
    role: str | None
    provider: str | None
    model: str | None
    task_id: str | None
    analysis_id: str | None

    @property
    def declared_identity(self) -> tuple[str | None, str | None, str | None]:
        return (self.role, self.provider, self.model)


@dataclass(frozen=True)
class ProviderCall:
    """One AgentRuntime provider invocation, proven by its own result.json."""

    agent_run_id: str
    role: str
    provider: str
    model: str | None
    status: str | None
    duration_seconds: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    tokens_available: bool
    path: str

    @property
    def token_report(self) -> Any:
        if not self.tokens_available:
            return UNAVAILABLE
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class RunEvidence:
    """Every durable artifact of one exact run, already validated together."""

    run_root: Path
    run_id: str
    manifest: Mapping[str, Any]
    progress: Mapping[str, Any] | None
    receipt: Mapping[str, Any] | None
    scheduler_events: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    worker_launches: list[WorkerLaunch] = field(default_factory=list)
    worker_runs: list[WorkerRun] = field(default_factory=list)
    provider_call_references: dict[str, ProviderCallReference] = field(default_factory=dict)
    provider_calls: list[ProviderCall] = field(default_factory=list)
    foreign_worker_run_count: int = 0
    unattributed_provider_call_count: int = 0
    missing_provider_call_ids: list[str] = field(default_factory=list)
    worker_output_root_supplied: bool = False
    provider_call_roots_supplied: bool = False
    notes: list[str] = field(default_factory=list)


def load_manifest(run_root: Path) -> Mapping[str, Any]:
    payload = _read_json(run_root / "manifest.json", label="run manifest")
    if not isinstance(payload, dict):
        raise RunEvidenceError("run manifest must be a JSON object")
    for key in ("run_id", "target_task_ids", "excluded_task_ids", "runtime_configuration"):
        if key not in payload:
            raise RunEvidenceError(f"run manifest is missing required field {key!r}")
    run_id = payload["run_id"]
    if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
        raise RunEvidenceError("run manifest run_id is invalid")
    return payload


def load_receipt(run_root: Path, manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The graph-complete receipt, refused when it belongs to another run."""

    path = run_root / "graph-complete.json"
    if not path.is_file():
        return None
    payload = _read_json(path, label="graph-complete receipt")
    if not isinstance(payload, dict):
        raise RunEvidenceError("graph-complete receipt must be a JSON object")
    receipt_manifest = payload.get("manifest_sha256")
    if type(receipt_manifest) is not str or _SHA256_RE.fullmatch(receipt_manifest) is None:
        raise RunEvidenceError("graph-complete receipt manifest_sha256 is invalid")
    expected = manifest.get("sha256") or manifest.get("manifest_sha256")
    if isinstance(expected, str) and expected and expected != receipt_manifest:
        raise RunEvidenceError(
            "graph-complete receipt belongs to a different run manifest"
        )
    return payload


def _validate_run_scoped(records: Sequence[Mapping[str, Any]], *, run_id: str, label: str) -> None:
    """Refuse a journal that mixes runs."""

    for index, record in enumerate(records, start=1):
        observed = record.get("run_id")
        if observed is not None and type(observed) is str and observed != run_id:
            # Worker run IDs legitimately differ from the graph run ID; only a
            # record that names the graph run must agree with it.
            if record.get("event") in {"scheduler_started", "scheduler_stopped"}:
                raise RunEvidenceError(
                    f"{label} record {index} belongs to run {observed!r}, not {run_id!r}"
                )


def load_scheduler_events(run_root: Path, *, run_id: str) -> list[dict[str, Any]]:
    records = _read_jsonl(run_root / "events.jsonl", label="scheduler event journal")
    for index, record in enumerate(records, start=1):
        if "event" not in record:
            raise RunEvidenceError(f"scheduler event {index} has no event name")
        parse_utc(record.get("timestamp_utc"), field_name=f"scheduler event {index} timestamp_utc")
    _validate_run_scoped(records, run_id=run_id, label="scheduler event journal")
    return records


def load_timeline(run_root: Path, *, run_id: str) -> list[dict[str, Any]]:
    records = _read_jsonl(run_root / "run_timeline.jsonl", label="run timeline journal")
    for index, record in enumerate(records, start=1):
        parse_utc(record.get("timestamp_utc"), field_name=f"run timeline {index} timestamp_utc")
        observed = record.get("run_id")
        if type(observed) is str and observed != run_id:
            raise RunEvidenceError(
                f"run timeline record {index} belongs to run {observed!r}, not {run_id!r}"
            )
    return records


def _completion_scope_task_ids(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any] | None
) -> tuple[str, ...] | None:
    """Return the receipt-proven final run scope when completion exists.

    A run manifest is intentionally immutable, while a targeted decomposition
    may add descendants after that manifest was written.  The graph-complete
    receipt is the controller's durable authority for the final transitive
    scope.  Do not require an incidental scheduler event to repeat the child
    IDs: production D1C application does not currently emit the synthetic
    ``child_task_ids`` field used by older report fixtures.
    """

    if receipt is None:
        return None
    raw = receipt.get("relevant_task_ids")
    if type(raw) is not list or not raw:
        raise RunEvidenceError(
            "graph-complete receipt relevant_task_ids must be a non-empty list"
        )
    task_ids: list[str] = []
    for value in raw:
        if type(value) is not str or _TASK_ID_RE.fullmatch(value) is None:
            raise RunEvidenceError(
                "graph-complete receipt relevant_task_ids contains an invalid task ID"
            )
        task_ids.append(value)
    if task_ids != sorted(set(task_ids)):
        raise RunEvidenceError(
            "graph-complete receipt relevant_task_ids must be sorted and unique"
        )

    targets = manifest.get("target_task_ids")
    excluded = manifest.get("excluded_task_ids")
    if type(targets) is not list or any(
        type(value) is not str or _TASK_ID_RE.fullmatch(value) is None
        for value in targets
    ):
        raise RunEvidenceError("run manifest target_task_ids is invalid")
    if type(excluded) is not list or any(
        type(value) is not str or _TASK_ID_RE.fullmatch(value) is None
        for value in excluded
    ):
        raise RunEvidenceError("run manifest excluded_task_ids is invalid")
    if not set(targets).issubset(task_ids):
        raise RunEvidenceError(
            "graph-complete receipt omits a target task from the final run scope"
        )
    overlap = sorted(set(task_ids).intersection(excluded))
    if overlap:
        raise RunEvidenceError(
            "graph-complete receipt includes an excluded task: " + ", ".join(overlap)
        )
    return tuple(task_ids)


def worker_launches(events: Sequence[Mapping[str, Any]]) -> list[WorkerLaunch]:
    """Exactly the worker attempts this run launched, in journal order.

    This is the run-local attempt authority. A task attempted by an earlier or
    later autonomous run against the same checkout has its own launch records
    in its own journal and therefore cannot appear here, which is what keeps a
    shared worker output root from inflating this run's attempt counts.

    Two launches that share a scheduler run ID but disagree about the task,
    the worker, or the exact worker command are contradictory durable
    identities and are refused. A verbatim repeat of one launch record is the
    same attempt and is counted once.
    """

    launches: dict[str, WorkerLaunch] = {}
    order: list[str] = []
    for index, record in enumerate(events, start=1):
        if record.get("event") != _LAUNCH_EVENT:
            continue
        run_id = record.get("run_id")
        task_id = record.get("task_id")
        if type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None:
            raise RunEvidenceError(f"worker_launched event {index} has no exact run_id")
        if type(task_id) is not str or _TASK_ID_RE.fullmatch(task_id) is None:
            raise RunEvidenceError(f"worker_launched event {index} has no exact task_id")
        argv = record.get("argv")
        if argv is not None and (
            type(argv) is not list or any(type(item) is not str for item in argv)
        ):
            raise RunEvidenceError(f"worker_launched event {index} argv is malformed")
        worker_id = record.get("worker_id")
        launch = WorkerLaunch(
            task_id=task_id,
            run_id=run_id,
            worker_id=worker_id if type(worker_id) is str and worker_id else None,
            launched_at_utc=record["timestamp_utc"],
            argv=tuple(argv or ()),
        )
        existing = launches.get(run_id)
        if existing is None:
            launches[run_id] = launch
            order.append(run_id)
        elif existing.identity != launch.identity:
            raise RunEvidenceError(
                f"two worker_launched events share run_id {run_id!r} with different identities"
            )
    return [launches[run_id] for run_id in order]


def launch_flag_values(launches: Sequence[WorkerLaunch], flag: str) -> list[str]:
    """Every distinct value the run's own worker commands gave one flag."""

    values: set[str] = set()
    for launch in launches:
        argv = launch.argv
        for position, item in enumerate(argv):
            if item != flag:
                continue
            if position + 1 >= len(argv):
                raise RunEvidenceError(
                    f"worker launch {launch.run_id} recorded {flag} without a value"
                )
            values.add(argv[position + 1])
    return sorted(values)


def supervisor_binding(
    runtime: Mapping[str, Any], launches: Sequence[WorkerLaunch]
) -> dict[str, Any]:
    """The exact supervisor this run configured, never a house default.

    Two durable statements exist and both are used. The immutable manifest
    records ``runtime_configuration.supervisor_provider`` for any run that
    selected one, and every worker command this run launched carries
    ``--supervisor-provider`` because the scheduler refuses to let a worker
    resolve an ambient default. When both exist they must agree; disagreement
    is a contradictory durable identity and is refused rather than resolved by
    preference order.

    A manifest written before the supervisor became selectable names none. That
    omission is not silence: ``AutonomousRuntimeConfiguration`` loads it as the
    historical Codex supervisor, so it is reported as exactly that, labelled as
    the historical default rather than as a recorded selection.
    """

    if runtime.get("provider_topology") is not None:
        from .provider_profiles import ProviderTopology
        topology = ProviderTopology.from_dict(runtime["provider_topology"])
        if topology.mixed:
            for launch in launches:
                implementers = launch_flag_values([launch], _EXECUTION_PROVIDER_FLAG)
                supervisors = launch_flag_values([launch], _SUPERVISOR_PROVIDER_FLAG)
                if not implementers and not supervisors:
                    continue  # A decomposition worker has no task-supervisor role.
                if (len(implementers) != 1 or implementers != supervisors
                        or implementers[0] not in topology.provider_allowlist):
                    raise RunEvidenceError("profile worker supervisor differs from its assigned implementer")
            launched = launch_flag_values(launches, _SUPERVISOR_PROVIDER_FLAG)
            return dict(supervisor_provider="follow_implementer", supervisor_provider_source="run_manifest_provider_topology",
                supervisor_provider_basis="immutable mixed profile; each exact launch must bind supervisor to its implementer",
                supervisor_provider_confirmed_by_launch_argv=bool(launched), launched_supervisor_providers=launched)
    declared = runtime.get("supervisor_provider")
    if declared is not None and (
        type(declared) is not str or declared not in SUPERVISOR_PROVIDERS
    ):
        raise RunEvidenceError(
            "run manifest supervisor_provider is not an exact supervisor provider"
        )
    launched = launch_flag_values(launches, _SUPERVISOR_PROVIDER_FLAG)
    for value in launched:
        if value not in SUPERVISOR_PROVIDERS:
            raise RunEvidenceError(
                f"a worker launch of this run named supervisor provider {value!r}"
            )
    if len(launched) > 1:
        raise RunEvidenceError(
            "this run's worker launches name more than one supervisor provider: "
            + ", ".join(launched)
        )
    observed = launched[0] if launched else None
    if declared is not None and observed is not None and declared != observed:
        raise RunEvidenceError(
            f"the run manifest names supervisor provider {declared!r} but this run's "
            f"worker launches name {observed!r}"
        )
    if declared is not None:
        provider = declared
        source = "run_manifest"
        basis = (
            "the immutable run manifest records "
            "runtime_configuration.supervisor_provider"
            + (
                "; every worker launch argv of this run agrees"
                if observed is not None
                else ""
            )
        )
    elif observed is not None:
        provider = observed
        source = "worker_launch_argv"
        basis = (
            "the run manifest records no supervisor selection; every worker command "
            "this run launched carries --supervisor-provider with this exact value"
        )
    else:
        provider = DEFAULT_SUPERVISOR_PROVIDER
        source = "historical_default"
        basis = (
            "neither the run manifest nor any worker launch argv names a supervisor; "
            "a manifest written before the supervisor became selectable loads as the "
            "historical default supervisor"
        )
    return {
        "supervisor_provider": provider,
        "supervisor_provider_source": source,
        "supervisor_provider_basis": basis,
        "supervisor_provider_confirmed_by_launch_argv": observed is not None,
    }


def run_owned_provider_calls(
    events: Sequence[Mapping[str, Any]]
) -> dict[str, ProviderCallReference]:
    """The AgentRuntime invocations this run's own journal claims.

    Any record carrying ``agent_runtime_run_id`` claims that exact invocation.
    A record whose field is present but null states that the call happened
    without a recoverable identity, which is a different fact from silence and
    is deliberately not treated as an identity.
    """

    owned: dict[str, ProviderCallReference] = {}
    for index, record in enumerate(events, start=1):
        if _PROVIDER_CALL_IDENTITY_FIELD not in record:
            continue
        value = record[_PROVIDER_CALL_IDENTITY_FIELD]
        if value is None:
            continue
        if type(value) is not str or _RUN_ID_RE.fullmatch(value) is None:
            raise RunEvidenceError(
                f"scheduler event {index} has an invalid {_PROVIDER_CALL_IDENTITY_FIELD}"
            )
        reference = ProviderCallReference(
            agent_run_id=value,
            event=str(record.get("event")),
            timestamp_utc=record["timestamp_utc"],
            role=record.get("role") if type(record.get("role")) is str else None,
            provider=record.get("provider") if type(record.get("provider")) is str else None,
            model=record.get("model") if type(record.get("model")) is str else None,
            task_id=record.get("task_id") if type(record.get("task_id")) is str else None,
            analysis_id=(
                record.get("analysis_id") if type(record.get("analysis_id")) is str else None
            ),
        )
        existing = owned.get(value)
        if existing is None:
            owned[value] = reference
        elif existing.declared_identity != reference.declared_identity:
            raise RunEvidenceError(
                f"two scheduler events claim provider call {value!r} with different identities"
            )
    return owned


def load_worker_runs(output_root: Path, *, launches: Sequence[WorkerLaunch]) -> tuple[list[WorkerRun], int]:
    """The durable worker run directories this exact run launched.

    A directory is keyed ``<task-id>/<run-id>``, so an interrupted task that
    was resumed contributes one entry per run ID and is never merged into a
    single inflated interval. The output root is shared across autonomous runs,
    so only the pairs this run's journal launched are read; the count of
    directories belonging to other runs is returned so the report can say how
    many it deliberately left out.
    """

    selected = {(launch.task_id, launch.run_id) for launch in launches}
    owned_run_ids = {launch.run_id: launch.task_id for launch in launches}
    if not output_root.is_dir():
        return [], 0
    runs: list[WorkerRun] = []
    seen: set[tuple[str, str]] = set()
    foreign = 0
    for task_dir in sorted(p for p in output_root.iterdir() if p.is_dir()):
        task_id = task_dir.name
        if _TASK_ID_RE.fullmatch(task_id) is None:
            continue
        for run_dir in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            if (task_id, run_dir.name) not in selected:
                owner = owned_run_ids.get(run_dir.name)
                if owner is not None:
                    # The same scheduler run ID under two task directories is a
                    # contradictory durable identity, not a foreign run.
                    raise RunEvidenceError(
                        f"worker run directory {task_id}/{run_dir.name} claims a run ID this "
                        f"run launched for {owner}"
                    )
                foreign += 1
                continue
            metadata_path = run_dir / "run.json"
            if not metadata_path.is_file():
                continue
            metadata = _read_json(metadata_path, label=f"worker run metadata for {task_id}")
            if not isinstance(metadata, dict):
                raise RunEvidenceError(f"worker run metadata is not an object: {metadata_path}")
            run_id = metadata.get("run_id")
            recorded_task = metadata.get("task_id")
            if type(run_id) is not str or type(recorded_task) is not str:
                raise RunEvidenceError(f"worker run metadata is incomplete: {metadata_path}")
            if recorded_task != task_id:
                raise RunEvidenceError(
                    f"worker run metadata task {recorded_task!r} contradicts its directory {task_id!r}"
                )
            if run_dir.name != run_id:
                raise RunEvidenceError(
                    f"worker run directory {run_dir.name!r} contradicts its run_id {run_id!r}"
                )
            key = (task_id, run_id)
            if key in seen:
                raise RunEvidenceError(f"duplicate worker run directory for {task_id}/{run_id}")
            seen.add(key)
            started = metadata.get("started_at_utc")
            parse_utc(started, field_name=f"{task_id}/{run_id} started_at_utc")

            result_path = run_dir / "run_result.json"
            finished = terminal_status = None
            exit_code = source_head = issue_number = None
            if result_path.is_file():
                result = _read_json(result_path, label=f"worker result for {task_id}")
                if not isinstance(result, dict):
                    raise RunEvidenceError(f"worker result is not an object: {result_path}")
                for name, expected in (("run_id", run_id), ("task_id", task_id)):
                    observed = result.get(name)
                    if type(observed) is not str or observed != expected:
                        raise RunEvidenceError(
                            f"worker result {name} {observed!r} contradicts its directory {expected!r}"
                        )
                finished = result.get("finished_at_utc")
                parse_utc(finished, field_name=f"{task_id}/{run_id} finished_at_utc")
                terminal_status = result.get("terminal_status")
                exit_code = result.get("exit_code")
                source_head = result.get("source_head")
                issue_number = result.get("issue_number")
            runs.append(
                WorkerRun(
                    task_id=task_id,
                    run_id=run_id,
                    worker_id=metadata.get("worker_id") if type(metadata.get("worker_id")) is str else None,
                    started_at_utc=started,
                    finished_at_utc=finished,
                    terminal_status=terminal_status if type(terminal_status) is str else None,
                    exit_code=exit_code if type(exit_code) is int else None,
                    source_head=source_head if type(source_head) is str else None,
                    issue_number=issue_number if type(issue_number) is int else None,
                    result_path=str(result_path) if result_path.is_file() else None,
                )
            )
    return runs, foreign


def load_provider_calls(
    roots: Sequence[Path], *, owned: Mapping[str, ProviderCallReference]
) -> tuple[list[ProviderCall], int, list[str]]:
    """The AgentRuntime invocations this run claims, found under the roots.

    Calls are deduplicated by AgentRuntime run ID, so scanning overlapping
    roots, or re-reading a resumed crew's directory, cannot inflate the count.

    A ``result.json`` whose AgentRuntime run ID this run's journal does not
    claim belongs to another run, another role, or another tool that happens
    to share the root. It is counted as unattributed and read no further:
    matching it on role, task name, or wall-clock proximity is exactly the
    guess that let a previous run's architect call be reported as this one's.

    Returns the attributed calls, the number of unattributed ones, and the
    claimed invocations whose artifact was not found under any supplied root.
    """

    calls: dict[str, ProviderCall] = {}
    unattributed = 0
    for root in roots:
        if not root.is_dir():
            continue
        for result_path in sorted(root.rglob("agent_runtime/*/result.json")):
            # The directory name is the invocation identity the producer wrote
            # and is cross-checked against the payload below, so it is a safe
            # membership test that never parses another run's artifact.
            if result_path.parent.name not in owned:
                unattributed += 1
                continue
            payload = _read_json(result_path, label="AgentRuntime result")
            if not isinstance(payload, dict):
                raise RunEvidenceError(f"AgentRuntime result is not an object: {result_path}")
            agent_run_id = payload.get("run_id")
            role = payload.get("role")
            provider = payload.get("provider")
            if type(agent_run_id) is not str or type(role) is not str or type(provider) is not str:
                raise RunEvidenceError(
                    f"AgentRuntime result is missing run_id/role/provider: {result_path}"
                )
            if agent_run_id != result_path.parent.name:
                raise RunEvidenceError(
                    f"AgentRuntime result run_id contradicts its directory: {result_path}"
                )
            usage = payload.get("usage")
            tokens_available = isinstance(usage, dict)
            input_tokens = output_tokens = total_tokens = None
            if tokens_available:
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                total_tokens = usage.get("total_tokens")
                if not all(type(v) is int for v in (input_tokens, output_tokens, total_tokens)):
                    # Present but not integral is malformed evidence, which is
                    # a refusal rather than a silent "unavailable".
                    raise RunEvidenceError(
                        f"AgentRuntime usage is present but not integral: {result_path}"
                    )
            existing = calls.get(agent_run_id)
            call = ProviderCall(
                agent_run_id=agent_run_id,
                role=role,
                provider=provider,
                model=payload.get("model") if type(payload.get("model")) is str else None,
                status=payload.get("status") if type(payload.get("status")) is str else None,
                duration_seconds=(
                    float(payload["duration_seconds"])
                    if isinstance(payload.get("duration_seconds"), (int, float))
                    and not isinstance(payload.get("duration_seconds"), bool)
                    else None
                ),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                tokens_available=tokens_available,
                path=str(result_path),
            )
            if existing is not None and existing != call:
                raise RunEvidenceError(
                    f"two different AgentRuntime results share run_id {agent_run_id!r}"
                )
            reference = owned[agent_run_id]
            for name, claimed, observed in (
                ("role", reference.role, call.role),
                ("provider", reference.provider, call.provider),
                ("model", reference.model, call.model),
            ):
                if claimed is not None and claimed != observed:
                    raise RunEvidenceError(
                        f"this run claims provider call {agent_run_id!r} with {name} "
                        f"{claimed!r}, but its result.json records {observed!r}"
                    )
            calls[agent_run_id] = call
    missing = sorted(set(owned) - set(calls))
    return [calls[key] for key in sorted(calls)], unattributed, missing


def load_run_evidence(
    *,
    run_root: Path | str,
    worker_output_root: Path | str | None = None,
    provider_call_roots: Sequence[Path | str] = (),
) -> RunEvidence:
    """Load and cross-validate every durable artifact of one exact run."""

    root = Path(run_root).resolve()
    if not root.is_dir():
        raise RunEvidenceError(f"run root does not exist: {root}")
    manifest = load_manifest(root)
    run_id = manifest["run_id"]
    progress_path = root / "progress.json"
    progress = _read_json(progress_path, label="run progress") if progress_path.is_file() else None
    if progress is not None and not isinstance(progress, dict):
        raise RunEvidenceError("run progress must be a JSON object")
    receipt = load_receipt(root, manifest)
    events = load_scheduler_events(root, run_id=run_id)
    timeline = load_timeline(root, run_id=run_id)

    targets = tuple(manifest.get("target_task_ids") or ())
    launches = worker_launches(events)
    # Decomposition children are legitimate task IDs that are not in the
    # manifest's target set, so the scope check allows any task the run's own
    # evidence attributes to it.
    completion_scope = _completion_scope_task_ids(manifest, receipt)
    known = (
        set(completion_scope)
        if completion_scope is not None
        else set(targets) | _decomposition_children(events, timeline)
    )
    if known:
        for launch in launches:
            if launch.task_id not in known:
                raise RunEvidenceError(
                    f"this run launched {launch.task_id}, which is not in the run scope"
                )

    worker_runs: list[WorkerRun] = []
    foreign_worker_runs = 0
    notes: list[str] = []
    if worker_output_root is not None:
        output_root = Path(worker_output_root).resolve()
        worker_runs, foreign_worker_runs = load_worker_runs(output_root, launches=launches)
        if foreign_worker_runs:
            notes.append(
                f"{foreign_worker_runs} worker run directory(ies) under the shared output "
                "root belong to other autonomous runs and were excluded"
            )
        missing_directories = len(launches) - len(worker_runs)
        if missing_directories > 0:
            notes.append(
                f"{missing_directories} worker launch(es) of this run have no durable run "
                "directory under the supplied output root"
            )
    else:
        notes.append("worker output root was not supplied; per-task timing is unavailable")

    owned = run_owned_provider_calls(events)
    roots = [Path(item).resolve() for item in provider_call_roots]
    provider_calls, unattributed_calls, missing_calls = load_provider_calls(roots, owned=owned)
    if not roots:
        notes.append("no provider-call roots were supplied; provider calls are unavailable")
    elif not owned:
        notes.append(
            "this run's journal claims no AgentRuntime invocation, so provider calls under "
            "the shared roots cannot be attributed to it"
        )
    if unattributed_calls:
        notes.append(
            f"{unattributed_calls} AgentRuntime result(s) under the supplied roots are not "
            "claimed by this run and were excluded"
        )
    if missing_calls:
        notes.append(
            f"{len(missing_calls)} provider call(s) this run claims have no result.json under "
            "the supplied roots"
        )

    return RunEvidence(
        run_root=root,
        run_id=run_id,
        manifest=manifest,
        progress=progress,
        receipt=receipt,
        scheduler_events=events,
        timeline=timeline,
        worker_launches=launches,
        worker_runs=worker_runs,
        provider_call_references=owned,
        provider_calls=provider_calls,
        foreign_worker_run_count=foreign_worker_runs,
        unattributed_provider_call_count=unattributed_calls,
        missing_provider_call_ids=missing_calls,
        worker_output_root_supplied=worker_output_root is not None,
        provider_call_roots_supplied=bool(roots),
        notes=notes,
    )


def _decomposition_children(
    events: Sequence[Mapping[str, Any]], timeline: Sequence[Mapping[str, Any]]
) -> set[str]:
    """Task IDs the run's own evidence says were created by decomposition."""

    children: set[str] = set()
    for record in list(events) + list(timeline):
        for key in ("child_task_ids", "created_task_ids", "children"):
            value = record.get(key)
            if isinstance(value, list):
                children.update(item for item in value if type(item) is str and _TASK_ID_RE.fullmatch(item))
    return children


# --------------------------------------------------------------------------
# Derivations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    start: dt.datetime
    finish: dt.datetime
    label: str


def worker_intervals(events: Sequence[Mapping[str, Any]]) -> tuple[list[Interval], list[dict[str, Any]]]:
    """Bounded worker occupancy intervals from the scheduler journal.

    A launch opens an interval keyed by the worker's run ID; the first
    terminal event for that run ID closes it. An interval the journal never
    closes is returned separately as unclosed rather than being extended to
    the end of the run, because the evidence does not say when it ended.
    """

    open_runs: dict[str, tuple[dt.datetime, str, str]] = {}
    intervals: list[Interval] = []
    unclosed: list[dict[str, Any]] = []
    for record in events:
        name = record.get("event")
        moment = parse_utc(record.get("timestamp_utc"), field_name="event timestamp_utc")
        run_id = record.get("run_id")
        task_id = record.get("task_id")
        if type(run_id) is not str or type(task_id) is not str:
            continue
        if name == _LAUNCH_EVENT:
            # A repeated launch for one run ID would double count; the first
            # launch is authoritative and the repeat is ignored.
            open_runs.setdefault(run_id, (moment, task_id, str(record.get("worker_id") or "")))
        elif name in _WORKER_TERMINAL_EVENTS and run_id in open_runs:
            start, opened_task, worker_id = open_runs.pop(run_id)
            intervals.append(
                Interval(start=start, finish=moment, label=f"{opened_task}/{run_id}/{worker_id}")
            )
    for run_id, (start, task_id, worker_id) in sorted(open_runs.items()):
        unclosed.append(
            {
                "task_id": task_id,
                "run_id": run_id,
                "worker_id": worker_id or None,
                "launched_at_utc": start.isoformat().replace("+00:00", "Z"),
                "closed": False,
                "reason": "the scheduler journal records no terminal event for this worker",
            }
        )
    intervals.sort(key=lambda item: (item.start, item.finish, item.label))
    return intervals, unclosed


def occupancy_profile(intervals: Sequence[Interval]) -> list[tuple[dt.datetime, dt.datetime, int]]:
    """Concurrent worker count over time as (start, finish, count) segments."""

    if not intervals:
        return []
    edges = sorted({moment for item in intervals for moment in (item.start, item.finish)})
    segments: list[tuple[dt.datetime, dt.datetime, int]] = []
    for left, right in zip(edges, edges[1:]):
        if right <= left:
            continue
        count = sum(1 for item in intervals if item.start <= left and item.finish >= right)
        segments.append((left, right, count))
    return segments


def utilization(
    intervals: Sequence[Interval], *, window_seconds: float | None, max_capacity: int | None
) -> dict[str, Any]:
    """Peak and time-weighted worker utilization from bounded intervals.

    ``peak_active_workers`` is the largest number of workers whose intervals
    overlap. ``active_worker_seconds`` is the sum of interval lengths, so two
    workers running for ten seconds each contribute twenty. ``busy_seconds``
    is wall-clock time with at least one worker active, which is what makes
    scheduler idle time meaningful.

    Time-weighted utilization is ``active_worker_seconds / (max_capacity x
    window_seconds)``. It is reported as unavailable when the run window or
    the capacity is not proven, never defaulted to a capacity of one.
    """

    segments = occupancy_profile(intervals)
    active_worker_seconds = round(
        sum((item.finish - item.start).total_seconds() for item in intervals), 3
    )
    busy_seconds = round(
        sum((right - left).total_seconds() for left, right, count in segments if count > 0), 3
    )
    peak = max((count for _l, _r, count in segments), default=0)
    report: dict[str, Any] = {
        "peak_active_workers": peak,
        "active_worker_seconds": active_worker_seconds,
        "busy_wall_seconds": busy_seconds,
        "max_capacity": max_capacity if isinstance(max_capacity, int) else UNAVAILABLE,
        "formula": (
            "time_weighted = active_worker_seconds / (max_capacity * run_elapsed_seconds); "
            "peak = max overlapping bounded worker intervals"
        ),
    }
    if window_seconds is None or not isinstance(max_capacity, int) or max_capacity <= 0:
        report["time_weighted_utilization"] = UNAVAILABLE
        report["time_weighted_unavailable_reason"] = (
            "the run window or the manifest capacity is not proven by durable evidence"
        )
        report["peak_utilization"] = UNAVAILABLE
    else:
        denominator = max_capacity * window_seconds
        report["time_weighted_utilization"] = (
            round(active_worker_seconds / denominator, 6) if denominator > 0 else UNAVAILABLE
        )
        report["peak_utilization"] = round(peak / max_capacity, 6)
    if window_seconds is None:
        report["scheduler_idle_seconds"] = UNAVAILABLE
        report["scheduler_idle_unavailable_reason"] = "the run window is not proven"
    else:
        report["scheduler_idle_seconds"] = round(max(window_seconds - busy_seconds, 0.0), 3)
    return report


def _first_last(
    events: Sequence[Mapping[str, Any]], names: Iterable[str] | None = None
) -> tuple[str | None, str | None]:
    """Earliest and latest timestamps, ordered by time rather than by line.

    The journal is append-only, but several processes append to it and a
    resumed run appends after an earlier session, so file order is not a
    reliable proxy for chronology. Every boundary this report publishes is
    therefore taken from the timestamps themselves.
    """

    matching = [
        record
        for record in events
        if names is None or record.get("event") in set(names)
    ]
    if not matching:
        return None, None
    ordered = sorted(
        matching, key=lambda record: parse_utc(record.get("timestamp_utc"), field_name="timestamp_utc")
    )
    return ordered[0].get("timestamp_utc"), ordered[-1].get("timestamp_utc")


def resume_hint_telemetry(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Correlate durable local-hint sender and scheduler-consumer outcomes."""

    sends: dict[str, Mapping[str, Any]] = {}
    consumes: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(events, start=1):
        event = record.get("event")
        if event not in {_RESUME_HINT_SEND_EVENT, _RESUME_HINT_CONSUME_EVENT}:
            continue
        hint_id = record.get("hint_id")
        task_id = record.get("task_id")
        if type(hint_id) is not str or _HINT_ID_RE.fullmatch(hint_id) is None:
            raise RunEvidenceError(
                f"resume-hint scheduler event {index} has no exact hint_id"
            )
        if type(task_id) is not str or _TASK_ID_RE.fullmatch(task_id) is None:
            raise RunEvidenceError(
                f"resume-hint scheduler event {index} has no exact task_id"
            )
        target = sends if event == _RESUME_HINT_SEND_EVENT else consumes
        if hint_id in target:
            raise RunEvidenceError(
                f"resume-hint event {event} is duplicated for hint_id {hint_id}"
            )
        target[hint_id] = record

    success_ids: set[str] = set()
    failure_ids: set[str] = set()
    for hint_id, record in sends.items():
        result = record.get("sender_result")
        if result == "success":
            success_ids.add(hint_id)
        elif result == "failure":
            failure_ids.add(hint_id)
        else:
            raise RunEvidenceError(
                f"resume-hint send {hint_id} has unsupported sender_result {result!r}"
            )

    disposition_counts: dict[str, int] = {}
    for hint_id, record in consumes.items():
        disposition = record.get("scheduler_disposition")
        if type(disposition) is not str or not disposition:
            raise RunEvidenceError(
                f"resume-hint consumption {hint_id} has no scheduler disposition"
            )
        disposition_counts[disposition] = disposition_counts.get(disposition, 0) + 1

    correlated = set(sends) & set(consumes)
    return {
        "send_count": len(sends),
        "send_success_count": len(success_ids),
        "send_failure_count": len(failure_ids),
        "consume_count": len(consumes),
        "correlated_count": len(correlated),
        "scheduler_dispositions": dict(sorted(disposition_counts.items())),
        "successful_unconsumed_hint_ids": sorted(success_ids - set(consumes)),
        "consumed_without_send_record_hint_ids": sorted(set(consumes) - set(sends)),
        "failed_hint_ids": sorted(failure_ids),
    }


def build_report(evidence: RunEvidence) -> dict[str, Any]:
    """Derive the complete machine-readable report from validated evidence."""

    manifest = evidence.manifest
    runtime = manifest.get("runtime_configuration") or {}
    events = evidence.scheduler_events
    targets = tuple(manifest.get("target_task_ids") or ())
    excluded = tuple(manifest.get("excluded_task_ids") or ())

    # ---- overall window -------------------------------------------------
    scheduler_start, scheduler_stop = _first_last(events, {"scheduler_started"})
    _ignored, scheduler_last_stop = _first_last(events, {"scheduler_stopped"})
    first_event, last_event = _first_last(events)
    timeline_start = next(
        (r.get("timestamp_utc") for r in evidence.timeline if r.get("event") == "autonomous_run_started"),
        None,
    )
    timeline_complete = next(
        (
            r.get("timestamp_utc")
            for r in reversed(evidence.timeline)
            if r.get("event") == "graph_complete_receipt_written"
        ),
        None,
    )
    started = timeline_start or scheduler_start or first_event
    finished = timeline_complete or scheduler_last_stop or last_event
    if started is not None and finished is not None:
        window_seconds: float | None = _elapsed_seconds(
            parse_utc(started, field_name="run start"),
            parse_utc(finished, field_name="run finish"),
            label="run window",
        )
    else:
        window_seconds = None
    run_window = {
        "started_at_utc": started or UNAVAILABLE,
        "finished_at_utc": finished or UNAVAILABLE,
        "elapsed_seconds": window_seconds if window_seconds is not None else UNAVAILABLE,
        "start_source": (
            "controller run timeline"
            if timeline_start
            else "scheduler journal" if scheduler_start else "first scheduler event" if first_event else UNAVAILABLE
        ),
        "finish_source": (
            "controller run timeline graph-complete record"
            if timeline_complete
            else "scheduler journal" if scheduler_last_stop else "last scheduler event" if last_event else UNAVAILABLE
        ),
    }
    if started is None or finished is None:
        run_window["unavailable_reason"] = (
            "no durable run-lifecycle record and no scheduler events were found"
        )

    # ---- graph completion ------------------------------------------------
    receipt = evidence.receipt
    graph_complete = {
        "graph_complete": receipt is not None,
        "receipt_present": receipt is not None,
        "completed_at_utc": timeline_complete or UNAVAILABLE,
    }
    if receipt is not None:
        graph_complete.update(
            {
                "source_commit": receipt.get("source_commit", UNAVAILABLE),
                "source_tree": receipt.get("source_tree", UNAVAILABLE),
                "relevant_task_ids": list(receipt.get("relevant_task_ids") or ()),
                "receipt_sha256": receipt.get("receipt_sha256", UNAVAILABLE),
                "lifetime_counters": receipt.get("lifetime_counters", UNAVAILABLE),
            }
        )
        if timeline_complete is None:
            graph_complete["completed_at_unavailable_reason"] = (
                "the receipt proves completion but carries no timestamp; "
                "no controller run timeline record was found"
            )
    else:
        graph_complete["reason"] = "no graph-complete receipt exists in the run root"

    # ---- per task --------------------------------------------------------
    completion_scope = _completion_scope_task_ids(manifest, receipt)
    children = sorted(
        set(completion_scope).difference(targets)
        if completion_scope is not None
        else _decomposition_children(events, evidence.timeline)
    )
    by_task: dict[str, list[WorkerRun]] = {}
    for run in evidence.worker_runs:
        by_task.setdefault(run.task_id, []).append(run)
    # This run's own launch count per task. It bounds every attempt number the
    # report publishes: a task attempted by another autonomous run against the
    # same output root has its launches in that run's journal, not this one.
    launches_by_task: dict[str, list[WorkerLaunch]] = {}
    for launch in evidence.worker_launches:
        launches_by_task.setdefault(launch.task_id, []).append(launch)

    def task_entry(task_id: str, *, origin: str) -> dict[str, Any]:
        runs = sorted(by_task.get(task_id, []), key=lambda r: r.started_at_utc)
        launched = launches_by_task.get(task_id, [])
        receipt_proves_complete = (
            completion_scope is not None and task_id in completion_scope
        )
        if not runs:
            return {
                "task_id": task_id,
                "origin": origin,
                "observed": False,
                "launched_attempt_count": len(launched),
                "started_at_utc": UNAVAILABLE,
                "finished_at_utc": UNAVAILABLE,
                "elapsed_seconds": UNAVAILABLE,
                "unavailable_reason": (
                    "this run launched no worker for this task"
                    if not launched
                    else "no durable worker run directory exists for this run's "
                    "launch(es) of this task"
                ),
                "terminal_status": (
                    "graph_complete" if receipt_proves_complete else UNAVAILABLE
                ),
                "terminal_status_source": (
                    "strict graph-complete receipt"
                    if receipt_proves_complete
                    else UNAVAILABLE
                ),
                "human_action_stop": False,
                "historical_human_action_stop": False,
                "succeeded": receipt_proves_complete,
            }
        # Interrupted and resumed tasks contribute one attempt per run ID.
        attempts = [
            {
                "run_id": r.run_id,
                "worker_id": r.worker_id,
                "started_at_utc": r.started_at_utc,
                "finished_at_utc": r.finished_at_utc or UNAVAILABLE,
                "elapsed_seconds": r.elapsed_seconds if r.elapsed_seconds is not None else UNAVAILABLE,
                "terminal_status": r.terminal_status or UNAVAILABLE,
                "exit_code": r.exit_code if r.exit_code is not None else UNAVAILABLE,
                "source_head": r.source_head or UNAVAILABLE,
                "issue_number": r.issue_number if r.issue_number is not None else UNAVAILABLE,
            }
            for r in runs
        ]
        finished = [r for r in runs if r.finished_at_utc is not None]
        total_active = round(sum(r.elapsed_seconds or 0.0 for r in finished), 3)
        last = finished[-1] if finished else None
        statuses = [r.terminal_status for r in runs if r.terminal_status]
        latest_attempt_status = statuses[-1] if statuses else UNAVAILABLE
        historical_human_stop = any(
            status in _HUMAN_ACTION_STATUSES for status in statuses
        )
        terminal_status = (
            "graph_complete" if receipt_proves_complete else latest_attempt_status
        )
        return {
            "task_id": task_id,
            "origin": origin,
            "observed": True,
            "attempts": attempts,
            "attempt_count": len(attempts),
            "launched_attempt_count": len(launched),
            "retry_count": max(len(attempts) - 1, 0),
            "started_at_utc": runs[0].started_at_utc,
            "finished_at_utc": (last.finished_at_utc if last else UNAVAILABLE),
            "elapsed_seconds": (
                _elapsed_seconds(
                    parse_utc(runs[0].started_at_utc, field_name="task start"),
                    parse_utc(last.finished_at_utc, field_name="task finish"),
                    label=f"task {task_id}",
                )
                if last
                else UNAVAILABLE
            ),
            "active_worker_seconds": total_active,
            # A worker result describes one attempt.  The immutable receipt is
            # stronger final authority: it can exist only after every scoped
            # TaskGraph item is conformant and every managed Issue workflow is
            # complete.  Preserve the latest attempt result separately so a
            # historical stop or failure remains visible without being called
            # the task's final outcome.
            "terminal_status": terminal_status,
            "terminal_status_source": (
                "strict graph-complete receipt"
                if receipt_proves_complete
                else "latest durable worker attempt"
            ),
            "latest_attempt_terminal_status": latest_attempt_status,
            "human_action_stop": (
                terminal_status in _HUMAN_ACTION_STATUSES
            ),
            "historical_human_action_stop": historical_human_stop,
            "succeeded": (
                receipt_proves_complete
                or (
                    isinstance(latest_attempt_status, str)
                    and latest_attempt_status in _SUCCESS_STATUSES
                )
            ),
            "source_head": (last.source_head if last and last.source_head else UNAVAILABLE),
            "produced_branch": UNAVAILABLE,
            "produced_commit": UNAVAILABLE,
            "produced_unavailable_reason": (
                "the produced branch and delivered commit are recorded in the managed "
                "GitHub Issue state, which this report does not read"
            ),
        }

    tasks = [task_entry(task_id, origin="target") for task_id in targets]
    tasks.extend(task_entry(task_id, origin="decomposition_child") for task_id in children)
    unexpected = sorted(set(by_task) - set(targets) - set(children))
    for task_id in unexpected:
        tasks.append(task_entry(task_id, origin="unattributed"))

    # ---- provider calls --------------------------------------------------
    by_role: dict[str, dict[str, Any]] = {}
    for call in evidence.provider_calls:
        key = f"{call.role}:{call.provider}"
        bucket = by_role.setdefault(
            key,
            {
                "role": call.role,
                "provider": call.provider,
                "models": set(),
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "calls_without_token_data": 0,
            },
        )
        bucket["calls"] += 1
        if call.model:
            bucket["models"].add(call.model)
        if call.tokens_available:
            bucket["input_tokens"] += call.input_tokens or 0
            bucket["output_tokens"] += call.output_tokens or 0
            bucket["total_tokens"] += call.total_tokens or 0
        else:
            bucket["calls_without_token_data"] += 1
    provider_rollup = []
    for key in sorted(by_role):
        bucket = dict(by_role[key])
        bucket["models"] = sorted(bucket.pop("models"))
        reported = {
            name: bucket.pop(name)
            for name in ("input_tokens", "output_tokens", "total_tokens")
        }
        missing = bucket["calls_without_token_data"]
        complete = missing == 0
        # This follows the repository's established token-usage contract
        # (ExecutionCrew.run_crew.aggregate_token_usage and
        # Pipeline/TaskGraph/token_usage_metrics.py): the partial sums that
        # were actually reported are always published, a total is published
        # only when every call in the bucket reported one, and an incomplete
        # bucket is named rather than silently summed into a smaller number.
        bucket["status"] = "complete" if complete else "incomplete"
        bucket["complete"] = complete
        bucket["usage_available_invocation_count"] = bucket["calls"] - missing
        bucket["missing_usage_invocation_count"] = missing
        for name, value in reported.items():
            bucket[f"reported_{name}"] = value
        if missing == bucket["calls"]:
            # No call in this bucket exposed tokens at all.
            bucket["tokens"] = UNAVAILABLE
            bucket["tokens_unavailable_reason"] = (
                "this provider did not expose token usage for any call in this role"
            )
        elif complete:
            bucket["tokens"] = dict(reported)
        else:
            bucket["tokens"] = UNAVAILABLE
            bucket["tokens_unavailable_reason"] = (
                f"{missing} of {bucket['calls']} call(s) in this role exposed no token "
                "usage, so a total for the role cannot be proven; the reported_* fields "
                "carry the sums that were actually published"
            )
        provider_rollup.append(bucket)

    # Attribution is published as its own arithmetic so a reader can see what
    # the report refused to count. ``claimed_call_count`` is what this run's
    # journal says it invoked, ``total_calls`` is how many of those were found,
    # and the unattributed count is how many result.json files under the shared
    # roots belong to some other run, role, or tool. They are never added
    # together, because that sum is exactly the earlier defect.
    claimed = len(evidence.provider_call_references)
    if not evidence.provider_call_roots_supplied:
        attribution_reason: str | None = (
            "no AgentRuntime result root was supplied, so this run's provider calls "
            "were not read"
        )
    elif claimed == 0:
        attribution_reason = (
            "this run's journal claims no AgentRuntime invocation, so provider calls "
            "under the shared roots cannot be attributed to it; a run recorded before "
            "the provider-call index existed reports unavailable rather than adopting "
            "another run's calls"
        )
    elif not evidence.provider_calls:
        attribution_reason = (
            "this run claims provider calls, but no matching result.json was found "
            "under the supplied roots"
        )
    else:
        attribution_reason = None
    provider_call_report = {
        "total_calls": len(evidence.provider_calls),
        "claimed_call_count": claimed,
        "unattributed_result_count": evidence.unattributed_provider_call_count,
        "missing_claimed_call_ids": list(evidence.missing_provider_call_ids),
        "attribution_basis": (
            "an AgentRuntime result.json names no run, so a call is counted only when "
            "this run's own journal names its exact agent_runtime_run_id; role, task "
            "name, and wall-clock proximity are never accepted as a substitute"
        ),
        "by_role_and_provider": provider_rollup,
        "unavailable_reason": attribution_reason,
    }

    # ---- utilization and incidents ---------------------------------------
    intervals, unclosed = worker_intervals(events)
    max_capacity = manifest.get("max_capacity")
    utilization_report = utilization(
        intervals, window_seconds=window_seconds, max_capacity=max_capacity
    )
    utilization_report["bounded_intervals"] = len(intervals)
    utilization_report["unclosed_intervals"] = unclosed

    incidents = [
        {
            "event": r.get("event"),
            "timestamp_utc": r.get("timestamp_utc"),
            "task_id": r.get("task_id"),
            "run_id": r.get("run_id"),
            "reason": r.get("reason"),
            "returncode": r.get("returncode"),
        }
        for r in events
        if r.get("event") in _INCIDENT_EVENTS
    ]
    historical_human_stops = [
        {
            "task_id": entry["task_id"],
            "run_id": attempt["run_id"],
            "finished_at_utc": attempt["finished_at_utc"],
            "terminal_status": attempt["terminal_status"],
            "resolved_by_graph_completion": entry.get("terminal_status")
            == "graph_complete",
        }
        for entry in tasks
        if entry.get("observed")
        for attempt in entry.get("attempts", [])
        if attempt.get("terminal_status") in _HUMAN_ACTION_STATUSES
    ]
    human_stops = [
        stop
        for stop in historical_human_stops
        if not stop["resolved_by_graph_completion"]
    ]

    # ---- scope proofs -----------------------------------------------------
    scope = {
        "target_task_ids": list(targets),
        "target_task_count": len(targets),
        "excluded_task_ids": list(excluded),
        "nsc_042_excluded": "NSC-042" in excluded,
        "nsc_042_absent_from_targets": "NSC-042" not in targets,
        "nsc_042_never_ran": all(run.task_id != "NSC-042" for run in evidence.worker_runs),
        "decomposition_children": children,
        "initial_source_commit": manifest.get("initial_source_commit", UNAVAILABLE),
        "initial_source_tree": manifest.get("initial_source_tree", UNAVAILABLE),
        "scale_proof": {
            "observed_target_count": len(targets),
            "is_ten_task_scope": len(targets) == 10,
            "eighty_task_run_observed": len(targets) >= 80,
            "thousand_task_run_observed": len(targets) >= 1000,
            "basis": (
                "the immutable run manifest names the complete target set; a run "
                "cannot silently widen its own scope because the manifest is created "
                "once and any later difference is refused"
            ),
        },
    }

    # ---- providers and models ---------------------------------------------
    # The configured binding comes from the immutable manifest, and the launched
    # binding comes from this run's own worker commands. Both are published,
    # neither is invented: a model the evidence does not name stays unavailable,
    # and a role no artifact binds is never filled in from a sibling role or
    # from what this pipeline usually runs.
    launches = evidence.worker_launches
    runtime_report: dict[str, Any] = {
        "architect_provider": runtime.get("architect_provider") or UNAVAILABLE,
        "architect_model": runtime.get("architect_model") or UNAVAILABLE,
        "execution_provider": runtime.get("execution_provider") or UNAVAILABLE,
        "execution_model": runtime.get("execution_model") or UNAVAILABLE,
        "launched_execution_providers": (
            launch_flag_values(launches, _EXECUTION_PROVIDER_FLAG) or UNAVAILABLE
        ),
        "launched_execution_models": (
            launch_flag_values(launches, _EXECUTION_MODEL_FLAG) or UNAVAILABLE
        ),
        "launched_supervisor_models": (
            launch_flag_values(launches, _SUPERVISOR_MODEL_FLAG) or UNAVAILABLE
        ),
        "launched_binding_basis": (
            "every worker_launched record of this run carries the exact worker "
            "command the scheduler ran, so argv is the run's own statement of what "
            "it launched; a run that launched no worker reports no launched binding"
        ),
        "provider_allowlist": list(runtime.get("provider_allowlist") or ()) or UNAVAILABLE,
        "max_capacity": max_capacity if isinstance(max_capacity, int) else UNAVAILABLE,
    }
    runtime_report.update(supervisor_binding(runtime, launches))
    provider_budget_report = UNAVAILABLE
    if runtime.get("provider_topology") is not None:
        from .provider_profiles import ProviderTopology
        from .provider_budget import read_budget_report
        topology = ProviderTopology.from_dict(runtime["provider_topology"])
        runtime_report["provider_topology"] = topology.to_dict()
        scheduler_id = "autonomous-" + hashlib.sha256(
            f"{manifest['github_repository'].casefold()}:{evidence.run_id}".encode("utf-8")
        ).hexdigest()[:20]
        try:
            provider_budget_report = read_budget_report(evidence.run_root / "provider-budget.json",
                topology=topology, scheduler_id=scheduler_id) or UNAVAILABLE
        except (ValueError, KeyError, TypeError) as exc:
            raise RunEvidenceError("provider budget is not valid evidence for this run") from exc

    return {
        "schema_version": RUN_EVIDENCE_REPORT_SCHEMA_VERSION,
        "run_id": evidence.run_id,
        "run_root": str(evidence.run_root),
        "evidence_notes": list(evidence.notes),
        "run_window": run_window,
        "graph_completion": graph_complete,
        "scope": scope,
        "runtime": runtime_report,
        "lifetime_counters": dict(evidence.progress) if evidence.progress else UNAVAILABLE,
        "resume_hint_telemetry": resume_hint_telemetry(events),
        "tasks": tasks,
        "provider_calls": provider_call_report,
        "provider_budget": provider_budget_report,
        "utilization": utilization_report,
        "incidents": incidents,
        "human_action_stops": human_stops,
        "historical_human_action_stops": historical_human_stops,
    }


# --------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------


def _value(value: Any) -> str:
    if value is None:
        return UNAVAILABLE
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _join(value: Any) -> str:
    """Render a list field without turning an empty list into a false absence."""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or UNAVAILABLE
    return _value(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    """A concise operator-readable summary of the same evidence."""

    window = report["run_window"]
    graph = report["graph_completion"]
    scope = report["scope"]
    runtime = report["runtime"]
    util = report["utilization"]
    hints = report["resume_hint_telemetry"]
    lines: list[str] = []
    lines.append(f"# Autonomous run evidence: {report['run_id']}")
    lines.append("")
    lines.append(f"Run root: `{report['run_root']}`")
    lines.append("")
    lines.append("## Run window")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Started | {_value(window['started_at_utc'])} |")
    lines.append(f"| Finished | {_value(window['finished_at_utc'])} |")
    lines.append(f"| Elapsed seconds | {_value(window['elapsed_seconds'])} |")
    lines.append(f"| Graph complete | {_value(graph['graph_complete'])} |")
    lines.append(f"| Completed at | {_value(graph['completed_at_utc'])} |")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Target tasks ({scope['target_task_count']}): {', '.join(scope['target_task_ids']) or UNAVAILABLE}")
    lines.append(f"- Decomposition children: {', '.join(scope['decomposition_children']) or 'none'}")
    lines.append(f"- NSC-042 excluded by manifest: {_value(scope['nsc_042_excluded'])}")
    lines.append(f"- NSC-042 never ran: {_value(scope['nsc_042_never_ran'])}")
    lines.append(
        f"- Ten-task scope: {_value(scope['scale_proof']['is_ten_task_scope'])}; "
        f"80-task run observed: {_value(scope['scale_proof']['eighty_task_run_observed'])}; "
        f"1000-task run observed: {_value(scope['scale_proof']['thousand_task_run_observed'])}"
    )
    lines.append("")
    lines.append("## Providers")
    lines.append("")
    lines.append(f"- Architect: {_value(runtime['architect_provider'])} / {_value(runtime['architect_model'])}")
    lines.append(f"- Execution: {_value(runtime['execution_provider'])} / {_value(runtime['execution_model'])}")
    lines.append(
        f"- Supervisor: {_value(runtime['supervisor_provider'])} "
        f"(source: {_value(runtime['supervisor_provider_source'])})"
    )
    lines.append(f"- Launched execution providers: {_join(runtime['launched_execution_providers'])}")
    lines.append(f"- Launched execution models: {_join(runtime['launched_execution_models'])}")
    lines.append(f"- Launched supervisor models: {_join(runtime['launched_supervisor_models'])}")
    budget = report.get("provider_budget")
    if isinstance(budget, dict):
        lines.extend(("", "## Provider budget", "",
            f"- Profile: {budget['identity']['topology']['profile']}",
            f"- Scope: {budget['snapshot']['accounting_scope']}",
            "- Metric: consumed total tokens / configured token budget; cached input is a subset of input.",
            "", "| Provider | Input | Cached input | Output | Total | Budget | Normalized pressure |",
            "| --- | --- | --- | --- | --- | --- | --- |"))
        for provider, row in budget["snapshot"]["providers"].items():
            columns = [provider] + [_value(row[key]) for key in ("input_tokens", "cached_input_tokens",
                "output_tokens", "total_tokens", "configured_token_budget", "normalized_utilization")]
            lines.append("| " + " | ".join(str(value) for value in columns) + " |")
    lines.append("")
    lines.append("## Tasks")
    lines.append("")
    lines.append("| Task | Origin | Final status | Started | Finished | Elapsed s | Attempts | Current human stop |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for task in report["tasks"]:
        lines.append(
            "| {task_id} | {origin} | {status} | {started} | {finished} | {elapsed} | {attempts} | {human} |".format(
                task_id=task["task_id"],
                origin=task["origin"],
                status=_value(task.get("terminal_status", UNAVAILABLE)),
                started=_value(task["started_at_utc"]),
                finished=_value(task["finished_at_utc"]),
                elapsed=_value(task["elapsed_seconds"]),
                attempts=_value(task.get("attempt_count", UNAVAILABLE)),
                human=_value(task.get("human_action_stop", False)),
            )
        )
    lines.append("")
    lines.append("## Provider calls")
    lines.append("")
    calls = report["provider_calls"]
    if not calls["by_role_and_provider"]:
        lines.append(f"No provider call evidence: {_value(calls.get('unavailable_reason'))}")
    else:
        lines.append("| Role | Provider | Models | Calls | Tokens |")
        lines.append("| --- | --- | --- | --- | --- |")
        for bucket in calls["by_role_and_provider"]:
            tokens = bucket["tokens"]
            rendered = (
                UNAVAILABLE
                if tokens == UNAVAILABLE
                else f"in {tokens['input_tokens']} / out {tokens['output_tokens']} / total {tokens['total_tokens']}"
            )
            lines.append(
                f"| {bucket['role']} | {bucket['provider']} | {', '.join(bucket['models']) or UNAVAILABLE} "
                f"| {bucket['calls']} | {rendered} |"
            )
    lines.append("")
    lines.append(
        f"- Calls this run claims: {_value(calls['claimed_call_count'])}; "
        f"attributed: {_value(calls['total_calls'])}; "
        f"excluded as another run's or another tool's: "
        f"{_value(calls['unattributed_result_count'])}"
    )
    if calls["missing_claimed_call_ids"]:
        lines.append(
            "- Claimed calls with no result.json under the supplied roots: "
            + ", ".join(calls["missing_claimed_call_ids"])
        )
    lines.append("")
    lines.append("## Utilization")
    lines.append("")
    lines.append(f"- Peak active workers: {_value(util['peak_active_workers'])} of {_value(util['max_capacity'])}")
    lines.append(f"- Active worker seconds: {_value(util['active_worker_seconds'])}")
    lines.append(f"- Busy wall seconds: {_value(util['busy_wall_seconds'])}")
    lines.append(f"- Scheduler idle seconds: {_value(util['scheduler_idle_seconds'])}")
    lines.append(f"- Time-weighted utilization: {_value(util['time_weighted_utilization'])}")
    lines.append(f"- Formula: {util['formula']}")
    if util["unclosed_intervals"]:
        lines.append(f"- Unclosed worker intervals: {len(util['unclosed_intervals'])}")
    lines.append("")
    lines.append("## Local resume hints")
    lines.append("")
    lines.append(
        f"- Sends: {hints['send_count']} "
        f"({hints['send_success_count']} successful, {hints['send_failure_count']} failed)"
    )
    lines.append(
        f"- Consumed: {hints['consume_count']}; correlated: {hints['correlated_count']}"
    )
    lines.append(
        "- Scheduler dispositions: "
        + (
            ", ".join(
                f"{name}={count}"
                for name, count in hints["scheduler_dispositions"].items()
            )
            or "none"
        )
    )
    if hints["successful_unconsumed_hint_ids"]:
        lines.append(
            "- Successful sends without consumption: "
            + ", ".join(hints["successful_unconsumed_hint_ids"])
        )
    if hints["failed_hint_ids"]:
        lines.append("- Failed sends: " + ", ".join(hints["failed_hint_ids"]))
    lines.append("")
    lines.append("## Incidents and human stops")
    lines.append("")
    if not report["incidents"]:
        lines.append("- No incident events recorded.")
    for incident in report["incidents"]:
        lines.append(
            f"- {incident['timestamp_utc']} {incident['event']} "
            f"task={_value(incident.get('task_id'))} reason={_value(incident.get('reason'))}"
        )
    if report["human_action_stops"]:
        lines.append("")
        for stop in report["human_action_stops"]:
            lines.append(
                f"- HUMAN ACTION REQUIRED: {stop['task_id']} at {stop['finished_at_utc']} "
                "(this is a stop, not a pass)"
            )
    resolved_stops = [
        stop
        for stop in report.get("historical_human_action_stops", [])
        if stop.get("resolved_by_graph_completion")
    ]
    for stop in resolved_stops:
        lines.append(
            f"- Historical human-action stop: {stop['task_id']} at "
            f"{stop['finished_at_utc']} (later resolved; strict graph completion "
            "is the final authority)"
        )
    if report["evidence_notes"]:
        lines.append("")
        lines.append("## Evidence notes")
        lines.append("")
        for note in report["evidence_notes"]:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report one finished autonomous graph run from its durable evidence. "
            "Read-only: starts no task, invokes no provider, contacts no GitHub."
        )
    )
    parser.add_argument("--run-root", required=True, help="directory holding manifest.json")
    parser.add_argument("--worker-output-root", default=None, help="scheduler worker output root")
    parser.add_argument(
        "--provider-call-root",
        action="append",
        default=[],
        help="a root to scan for AgentRuntime result.json files (repeatable)",
    )
    parser.add_argument("--output-json", default=None, help="write the machine-readable report here")
    parser.add_argument("--output-markdown", default=None, help="write the Markdown report here")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        evidence = load_run_evidence(
            run_root=args.run_root,
            worker_output_root=args.worker_output_root,
            provider_call_roots=args.provider_call_root,
        )
        report = build_report(evidence)
    except RunEvidenceError as exc:
        print(f"[run-evidence] refused: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    if args.output_json:
        path = Path(args.output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8", newline="\n")
    if args.output_markdown:
        path = Path(args.output_markdown)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8", newline="\n")
    if not args.output_json and not args.output_markdown:
        print(payload, end="")
    else:
        print(markdown, end="")
    return 0


__all__ = [
    "RUN_EVIDENCE_REPORT_SCHEMA_VERSION",
    "UNAVAILABLE",
    "Interval",
    "ProviderCall",
    "ProviderCallReference",
    "RunEvidence",
    "RunEvidenceError",
    "WorkerLaunch",
    "WorkerRun",
    "build_report",
    "launch_flag_values",
    "load_provider_calls",
    "load_run_evidence",
    "load_worker_runs",
    "main",
    "occupancy_profile",
    "parse_utc",
    "render_markdown",
    "run_owned_provider_calls",
    "supervisor_binding",
    "utilization",
    "worker_intervals",
    "worker_launches",
]


if __name__ == "__main__":
    raise SystemExit(main())
