#!/usr/bin/env python3
"""Deterministic end-to-end acceptance: muffcabbage tasks through the whole pipeline.

Three positive scenarios share one fixture and one lifecycle driver. The *fast*
scenario is one new script and its ``.meta`` companion: the architect asks for
``fast`` and deterministic routing keeps it lean/targeted. The *standard* scenario
is three new isolated scripts with their companions: six exact paths exceed the
lean bound but touch no scene, prefab, ProjectSettings, package, or pipeline
surface, so the deterministic minimum is exactly ``standard`` and the architect's
``standard`` request is honored as standard/task_specific. A focused guard proves
that a ``fast`` request for that same surface is raised to ``standard``.
The *deep* scenario creates one small Unity scene plus one value script and their
companions. Its four exact paths require deep/full/full_relevant because the scene
contains serialized GameObject/Transform data, not because the file count is large.

Classification: disposable-repository lifecycle test. Everything it touches lives in
one temporary directory: a bare Git remote, a controller source clone, task
checkouts, and the autonomous run artifacts. No real GitHub, Docker, Claude, Codex,
Unity, rehearsal checkout, Issue, claim, container, or provider session is ever
reached or mutated.

What runs for real (production objects, unmodified):

- ``AutonomousGraphController`` with the real ``JsonProgressStore`` /
  ``JsonReceiptStore`` / ``SchedulerLock`` and the production
  ``ProductionCoherentSnapshotter`` (``refresh_source_main``, ``taskcontrol states``,
  durable workflow observation).
- ``PollingOrchestrator`` with the real Stage 2 planner
  (``build_poll_dispatch_plan``), the real reservation observer, the real committed
  task loader, source refresher, execution routing, worker command construction,
  worker admission, and identity-bound worker result validation.
- The real ``IssueWorkflowService`` state machine on a ``MemoryIssueBackend``
  (lease, human handoff, Vincent notification, automated validation, delivery
  acceptance, pending-check release, completion).
- The real private synthetic evidence adapter (``run_autonomous_graph``'s pump and
  ``synthetic_gauntlet_approver.process_one_synthetic_handoff``) including its exact
  pre-handoff evidence reuse.
- The real ``RealTaskReviewWorkflow`` / ``DurableTaskCheckoutManager`` clone and
  branch lifecycle, and the real ``ResumableDownstreamTaskController`` driven by the
  production ``run_openai_downstream_pipeline`` loop with every downstream
  determinism/resilience patch installed.

What is a deterministic fixture stand-in (each named where it is defined):

- The architect model (``DeterministicArchitect``: the scenario's tier advisory).
- The worker *process* (``InProcessWorkers``: the exact ``host_worker_launcher``
  argv the scheduler builds is executed in-process instead of spawning Python).
- The ExecutionCrew's candidate/result (scenario files written directly; the real
  bridge validates and persists its execution receipt) and the
  ``run_unity_tests_clean.ps1`` runner committed in the fixture repository, which
  publishes a manifest without launching Unity and logs every execution.
- The TaskGraph/TaskDelivery command-line tools committed in the fixture repository
  (``taskcontrol.py``, ``generate_delivery_spec.py``, ``record_delivery.py``).
- GitHub itself: SSH transport is a local fake that serves the bare remote, the
  ``gh`` PR/Issue CLI is emulated against that remote, and ``GhIssueBackend`` is an
  isinstance-compatible subclass over the in-memory Issue store.
- The Codex downstream decision provider (``DeterministicDownstreamDecisions``: it
  only ever selects the single action the host state already permits).
- GitHub check results: the emulated pull request reports one completed,
  successful deterministic-workflow check for the evidence commit, so production's
  fail-closed check authority permits the merge without any in-process waiting.
"""

from __future__ import annotations

import faulthandler
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Pipeline.TaskReviewAgent  # noqa: E402,F401  (installs the production patches)
import Pipeline.TaskReviewAgent.dispatch_plan as dispatch_plan_module  # noqa: E402
import Pipeline.TaskReviewAgent.downstream_determinism as determinism  # noqa: E402
import Pipeline.TaskReviewAgent.polling_orchestrator as scheduler_module  # noqa: E402
import Pipeline.TaskReviewAgent.production_graph_snapshot as snapshot_module  # noqa: E402
import Pipeline.TaskReviewAgent.real_workflow as real_workflow_module  # noqa: E402
import Pipeline.TaskReviewAgent.run_autonomous_graph as run_autonomous_graph  # noqa: E402
import Pipeline.TaskReviewAgent.synthetic_gauntlet_approver as approver  # noqa: E402
from Pipeline.TaskReviewAgent.architect_preflight import (  # noqa: E402
    ArchitectAdvisory,
    ArchitectBatch,
    ArchitectBatchAnalysis,
    ArchitectBatchConsideration,
)
from Pipeline.TaskReviewAgent.autonomous_graph_run import (  # noqa: E402
    AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
    AutonomousGraphController,
    AutonomousGraphRunError,
    AutonomousRunManifest,
    AutonomousRuntimeConfiguration,
    JsonManifestStore,
    JsonProgressStore,
    JsonReceiptStore,
    autonomous_run_paths,
)
from Pipeline.TaskReviewAgent.candidate_integration import (  # noqa: E402
    CandidateIntegrator,
    CandidateIntegrationReceipt,
    load_integration_receipt,
)
from Pipeline.TaskReviewAgent.codex_supervisor import SupervisorDecision  # noqa: E402
from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.contracts import TaskReviewRequest, semantic_sha256  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_pipeline import _default_runner  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_resilience import validation_plan_for  # noqa: E402
from Pipeline.TaskReviewAgent.downstream_runtime import (  # noqa: E402
    DownstreamTaskReviewWorkflow,
    ResumableDownstreamTaskController,
)
from Pipeline.TaskReviewAgent.execution_routing import (  # noqa: E402
    RIGOR_PROFILE_BY_TIER,
    load_execution_routing_policy,
    resolve_task_rigor,
)
from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge  # noqa: E402
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    CREW_PROFILE_ROLES,
    CREW_VALIDATION_PROFILE_PAIRS,
)
from Pipeline.TaskReviewAgent.goal_loop_guard import GuardedTaskController  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow import (  # noqa: E402
    AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
    AUTOMATED_VALIDATION_GAUNTLET_ID,
    AUTOMATED_VALIDATION_REPOSITORY,
    WorkflowEventType,
    WorkflowPhase,
    WorkflowState,
    parse_human_validation_result,
)
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    VINCENT_INBOX_MARKER,
    VINCENT_INBOX_TITLE,
    GhIssueBackend,
    IssueWorkflowService,
    IssueWorkflowStoreError,
    MemoryIssueBackend,
    _parse_github_repository,
    resolve_issue_backend_repository,
)
from Pipeline.TaskReviewAgent.openai_downstream import run_openai_downstream_pipeline  # noqa: E402
from Pipeline.TaskReviewAgent.polling_orchestrator import (  # noqa: E402
    JsonEventEmitter,
    PollingOrchestrator,
    SchedulerLock,
    build_poll_dispatch_plan,
    observe_durable_integration_reservations,
    scheduler_lock_path,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    PRESERVED_TASK_ID,
    _acceptance,
    _concrete_task,
    _gate,
    _guid,
    _test_filter,
    _value_paths,
)
from Pipeline.TaskReviewAgent.production_graph_snapshot import (  # noqa: E402
    ProductionCoherentSnapshotter,
)
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.TaskReviewAgent.run_pipeline_agent import _worker_terminal_contract  # noqa: E402
from Pipeline.TaskReviewAgent.worker_result import (  # noqa: E402
    initialize_worker_run,
    write_worker_result,
)


REPOSITORY = AUTOMATED_VALIDATION_REPOSITORY
ORIGIN_URL = f"git@github.com:{REPOSITORY}.git"
RUN_ID = "muffcabbage-e2e-acceptance"
SCHEDULER_ID = "muffcabbage-e2e-scheduler"
APPROVER_WORKER_ID = approver._AUTOMATED_WORKER_ID


@dataclass(frozen=True)
class Scenario:
    """One synthetic muffcabbage task and the rigor the policy must resolve for it.

    ``suffixes`` names the isolated new scripts (``""`` is the gauntlet's own single
    value file). Each script brings its deterministic ``.cs.meta`` companion. An
    optional ``scene_path`` adds substantive serialized content and its companion.
    Every changed path stays under ``Assets/`` in the disposable repository.
    """

    name: str
    number: int
    architect_tier: str
    suffixes: tuple[str, ...]
    expected_tier: str
    # Pinned literally, never derived from production's rigor table: the acceptance
    # test must notice if that table ever maps a tier to a different crew or
    # validation profile.
    crew_profile: str
    validation_profile: str
    required_roles: tuple[str, ...]
    scene_path: str | None = None

    @property
    def task_id(self) -> str:
        return f"NSC-{self.number}"

    @property
    def test_filter(self) -> str:
        return _test_filter(self.number)

    @property
    def file_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(_value_paths(self.number, suffix) for suffix in self.suffixes)

    @property
    def exact_paths(self) -> tuple[str, ...]:
        return (
            *(path for pair in self.file_pairs for path in pair),
            *((self.scene_path, self.scene_path + ".meta") if self.scene_path else ()),
        )

    @property
    def class_names(self) -> tuple[str, ...]:
        return tuple(
            f"MuffcabbageGauntlet{self.number:03d}{suffix}" for suffix in self.suffixes
        )

    def contract(self) -> dict[str, Any]:
        """The committed task contract: the gauntlet's, widened to every script."""

        task = _concrete_task(self.number, 0)
        if self.suffixes == ("",) and self.scene_path is None:
            return task
        scripts = [source for source, _ in self.file_pairs]
        task["title"] = (
            f"Muffcabbage Gauntlet {self.number}: Publish Its "
            f"{len(scripts)} Isolated Values"
        )
        task["reconciliation_key"] = f"muffcabbage-gauntlet-{self.number}-values"
        task["execution_reason"] = (
            f"One agent creates {len(scripts)} uniquely named C# constants and their "
            "deterministic Unity .meta companions; no shared implementation file or "
            "design decision is involved."
        )
        task["decomposition_reason"] = (
            "Create " + ", ".join(scripts) + f", each with one public constant Value = "
            f"{self.number}, and create each specified .meta companion; no earlier "
            "gauntlet value is required."
        )
        task["exclusive_resources"] = [f"repo-file:{path}" for path in self.exact_paths]
        task["acceptance_criteria"] = [
            _acceptance(
                f"AC-{index:03d}",
                f"Create {source} in namespace NoSafeCircle.DoorPrototype with a public "
                f"static class {class_name} containing exactly public const int Value = "
                f"{self.number};, and create {meta} with fileFormatVersion 2 and guid "
                f"{_guid(source)}.",
            )
            for index, ((source, meta), class_name) in enumerate(
                zip(self.file_pairs, self.class_names), 1
            )
        ]
        task["completion_gates"] = [
            _gate(
                "VAL-001",
                f"Unity EditMode filter {self.test_filter} passes for the exact commit and "
                f"proves Value == {self.number} for " + ", ".join(self.class_names) + ".",
            )
        ]
        task["notes"] = (
            "Disposable private-repository gauntlet only. The three value files and their "
            ".meta companions are intentionally isolated new files: enough exact paths to "
            "exceed the lean bound, no shared or serialized content."
        )
        task["provenance"]["expected_paths"] = list(self.exact_paths)
        if self.scene_path:
            task["title"] = f"Muffcabbage Gauntlet {self.number}: Place the Scene Marker"
            task["execution_reason"] = (
                "One agent creates one isolated scene marker and its matching value constant; "
                "the serialized Transform requires review even though the change is small."
            )
            task["decomposition_reason"] = (
                f"Create {self.scene_path} with one root GameObject named MuffcabbageMarker "
                f"whose Transform local position is ({self.number}, 0, 0), matching "
                f"{self.class_names[0]}.Value. Create both deterministic import companions."
            )
            task["acceptance_criteria"].append(_acceptance(
                "AC-002", task["decomposition_reason"]
                + f" The scene companion guid is {_guid(self.scene_path)}.",
            ))
            task["completion_gates"] = [_gate(
                "VAL-001", f"Unity EditMode filter {self.test_filter} checks the exact "
                f"committed {self.scene_path}, its root marker Transform and matching "
                f"{self.class_names[0]}.Value == {self.number}, without saving the scene.",
            )]
            task["notes"] = (
                "Disposable regression fixture only. The scene contains real Unity YAML "
                "GameObject and Transform records. Machine fixture evidence is not a "
                "Unity Editor run or human visual verification."
            )
        return task

    def scene_text(self) -> str:
        return (
            "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
            "--- !u!1 &1000\nGameObject:\n"
            "  m_ObjectHideFlags: 0\n  m_CorrespondingSourceObject: {fileID: 0}\n"
            "  m_PrefabInstance: {fileID: 0}\n  m_PrefabAsset: {fileID: 0}\n"
            "  serializedVersion: 6\n  m_Component:\n  - component: {fileID: 1001}\n"
            "  m_Layer: 0\n  m_Name: MuffcabbageMarker\n  m_TagString: Untagged\n"
            "  m_Icon: {fileID: 0}\n  m_NavMeshLayer: 0\n"
            "  m_StaticEditorFlags: 0\n  m_IsActive: 1\n"
            "--- !u!4 &1001\nTransform:\n"
            "  m_ObjectHideFlags: 0\n  m_CorrespondingSourceObject: {fileID: 0}\n"
            "  m_PrefabInstance: {fileID: 0}\n  m_PrefabAsset: {fileID: 0}\n"
            "  m_GameObject: {fileID: 1000}\n  serializedVersion: 2\n"
            "  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}\n"
            f"  m_LocalPosition: {{x: {self.number}, y: 0, z: 0}}\n"
            "  m_LocalScale: {x: 1, y: 1, z: 1}\n  m_ConstrainProportionsScale: 0\n"
            "  m_Children: []\n  m_Father: {fileID: 0}\n"
            "  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}\n"
            "--- !u!1660057539 &9223372036854775807\nSceneRoots:\n"
            "  m_ObjectHideFlags: 0\n  m_Roots:\n  - {fileID: 1001}\n"
        )


FAST = Scenario(
    name="fast",
    number=931,
    architect_tier="fast",
    suffixes=("",),
    expected_tier="fast",
    crew_profile="lean",
    validation_profile="targeted",
    required_roles=("implementer", "validator"),
)
# Three isolated new scripts plus their import companions: six exact paths exceed
# the four-path lean bound, and nothing else in the surface raises the floor, so
# the deterministic minimum is exactly standard (crew standard, validation
# task_specific) and an honest standard request is honored.
STANDARD = Scenario(
    name="standard",
    number=941,
    architect_tier="standard",
    suffixes=("Alpha", "Beta", "Gamma"),
    expected_tier="standard",
    crew_profile="standard",
    validation_profile="task_specific",
    required_roles=("implementer", "test_author", "validator"),
)
DEEP = Scenario(
    name="deep",
    number=951,
    architect_tier="deep",
    suffixes=("",),
    expected_tier="deep",
    crew_profile="full",
    validation_profile="full_relevant",
    required_roles=("contract_locality_auditor", "implementer", "test_author", "validator"),
    scene_path="Assets/Scenes/MuffcabbageGauntlet951.unity",
)
# The negative cases exercise the fast scenario's fixture.
TASK_ID = FAST.task_id
TEST_FILTER = FAST.test_filter
RUNNER_LOG_VARIABLE = "NSC_MUFFCABBAGE_RUNNER_LOG"
# The production lifecycle shells out roughly a thousand times (Git identity
# checks, TaskGraph states, fetches, worker tooling); at Windows process-start
# latency that is a 40-60 second floor on a quiet machine. The budget therefore
# bounds wall clock generously; the real hang guard is the zero-wait proof below
# (no fallback wait, no wakeup, no architect wait event, no sleep on the path).
RUNTIME_BUDGET_SECONDS = 150.0
# A hang anywhere in the lifecycle must fail loudly with every thread's stack
# instead of stalling a CI job; this is far above the per-test runtime budget.
WATCHDOG_SECONDS = 240.0
# The only executables the whole acceptance run is allowed to start: Git, this
# Python, and Windows PowerShell for the committed fixture runner. Anything else
# (gh, docker, claude, codex, Unity) is a provider or GitHub reach and fails the run.
ALLOWED_EXECUTABLES = frozenset(
    {"git", "git.exe", "powershell.exe", Path(sys.executable).name.casefold()}
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action: Any, expected: type[BaseException], *, containing: str = "") -> BaseException:
    try:
        action()
    except expected as exc:
        require(containing in str(exc), f"{type(exc).__name__} lacked {containing!r}: {exc}")
        return exc
    raise AssertionError(f"expected {expected.__name__} containing {containing!r}")


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {root}: "
            f"{completed.stderr.decode('utf-8', 'replace').strip()}"
        )
    return completed.stdout.decode("utf-8", "replace").strip()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------------
# Fixture repository content. These files are committed into the disposable
# repository so the production code finds them where it expects them.
# --------------------------------------------------------------------------------

TASKCONTROL_STUB = r'''#!/usr/bin/env python3
"""Fixture TaskGraph taskcontrol: derives conformance from committed delivery records."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD_DIRECTORY = "Pipeline/TaskGraph/deliveries"


def git(*args, stdin=None):
    completed = subprocess.run(
        ("git", "-C", str(ROOT), *args),
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.returncode, completed.stdout.decode("utf-8", "replace")


def committed_blobs(paths):
    """Read every listed committed path in one cat-file batch; missing -> None."""
    request = "".join(f"HEAD:{path}\n" for path in paths).encode("utf-8")
    code, text = git("cat-file", "--batch", stdin=request)
    if code != 0:
        raise SystemExit("cat-file batch failed")
    blobs = {}
    position = 0
    for path in paths:
        end = text.index("\n", position)
        header = text[position:end].split()
        position = end + 1
        if header[-1] == "missing":
            blobs[path] = None
            continue
        size = int(header[2])
        blobs[path] = text[position:position + size]
        position += size + 1
    return blobs


def rows():
    _, identity = git("rev-parse", "HEAD", "HEAD^{tree}")
    head, tree = identity.split()
    _, names = git("ls-tree", "-r", "--name-only", "HEAD", "--", "Tasks")
    task_names = sorted(name for name in names.splitlines() if name.endswith(".yaml"))
    record_names = [f"{RECORD_DIRECTORY}/{Path(name).stem}.json" for name in task_names]
    blobs = committed_blobs([*task_names, *record_names])
    result = []
    for name, record_name in zip(task_names, record_names):
        task_id = Path(name).stem
        task = json.loads(blobs[name]) if blobs[name] else {}
        record = json.loads(blobs[record_name]) if blobs[record_name] else None
        conformant = (
            isinstance(record, dict)
            and record.get("task_id") == task_id
            and isinstance(record.get("record_id"), str)
            and record.get("record_id")
        )
        result.append(
            {
                "task_id": task_id,
                "title": task.get("title"),
                "state": "conformant" if conformant else "not_delivered",
                "head_commit": head,
                "head_tree": tree,
                "selected_record_id": record["record_id"] if conformant else None,
                "decomposition_children": [],
                "findings": [],
                "dirty_worktree": False,
            }
        )
    return result


def main(argv):
    if argv == ["validate"]:
        print("taskcontrol validate: PASS")
        return 0
    if argv == ["states", "--json"]:
        print(json.dumps(rows()))
        return 0
    if len(argv) == 3 and argv[0] == "state" and argv[2] == "--json":
        for row in rows():
            if row["task_id"] == argv[1]:
                print(json.dumps(row))
                return 0
        print(f"unknown task {argv[1]}", file=sys.stderr)
        return 1
    print(f"unsupported taskcontrol fixture command: {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

DELIVERY_SPEC_STUB = r'''#!/usr/bin/env python3
"""Fixture TaskDelivery generate_delivery_spec: draft/finalize in the production draft shape."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def git(root, *args):
    return subprocess.run(
        ("git", "-C", str(root), *args), check=True, stdout=subprocess.PIPE
    ).stdout


def text(root, *args):
    return git(root, *args).decode("utf-8").strip()


def publish(path, value):
    path = Path(path)
    if path.exists():
        raise SystemExit(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def draft(args):
    root = Path(args.root).resolve()
    head = text(root, "rev-parse", "HEAD")
    tree = text(root, "rev-parse", "HEAD^{tree}")
    if text(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise SystemExit("draft requires a clean repository")
    task_bytes = git(root, "show", f"HEAD:Tasks/{args.task_id}.yaml")
    task = json.loads(task_bytes.decode("utf-8-sig"))
    if task.get("id") != args.task_id or task.get("contract_disposition") != "active":
        raise SystemExit("task contract is missing or inactive")
    manifests = []
    artifacts = []
    for index, raw in enumerate(args.validation_manifest, 1):
        path = Path(raw).resolve()
        data = path.read_bytes()
        manifest = json.loads(data.decode("utf-8"))
        state = manifest["validated_state"]
        if state["commit"] != head or state["tree"] != tree:
            raise SystemExit("validation manifest does not match HEAD")
        unity = manifest["unity"]
        manifests.append(
            {
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "commit": state["commit"],
                "tree": state["tree"],
                "test_platform": unity["test_platform"],
                "test_filter": unity["test_filter"],
            }
        )
        label = f"Unity-{unity['test_platform']}-{index:02d}"
        for suffix, kind, key in (
            ("results", "unity_test_results", "xml"),
            ("log", "unity_log", "log"),
        ):
            fact = manifest["artifacts"][key]
            artifacts.append(
                {
                    "id": f"unity_{index:02d}_{suffix}",
                    "type": kind,
                    "source_path": str(path.parent / fact["relative_path"]),
                    "name": label,
                    "sha256": fact["sha256"],
                    "size_bytes": fact["size_bytes"],
                    "validation_manifest": str(path),
                }
            )
    if not manifests:
        raise SystemExit("at least one validation manifest is required")
    base = text(root, "rev-parse", "--verify", f"{args.base_commit}^{{commit}}")
    ancestry = subprocess.run(
        ("git", "-C", str(root), "merge-base", "--is-ancestor", base, head), check=False
    )
    if ancestry.returncode != 0:
        raise SystemExit("base commit is not an ancestor of the validated commit")
    diff = sorted(
        line for line in text(root, "diff", "--name-only", base, head, "--").splitlines() if line
    )
    candidates = [
        {
            "path": path,
            "sources": ["committed_diff"],
            "suggested_role": "implementation",
            "selected": True,
            "role": "",
        }
        for path in diff
    ]
    gates = [
        {
            "gate_id": gate["gate_id"],
            "reference": gate["reference"],
            "requirement": gate["requirement"],
            "evidence": [],
            "notes": "",
        }
        for gate in task["completion_gates"]
    ]
    publish(
        args.output,
        {
            "schema_version": "1.0",
            "review_kind": "delivery_spec_review",
            "review_status": "needs_human",
            "task": {
                "id": args.task_id,
                "title": task["title"],
                "contract_revision": task["contract_revision"],
                "contract_sha256": hashlib.sha256(task_bytes).hexdigest(),
            },
            "validated_commit": head,
            "validated_tree": tree,
            "base_commit": base,
            "candidate_commit": head,
            "base_source": "explicit_base_commit",
            "validation_manifests": manifests,
            "artifacts": artifacts,
            "committed_diff_paths": diff,
            "surface_candidates": candidates,
            "gates": gates,
            "human_approval": {"required": True, "decision": "", "approved_by": "", "notes": ""},
            "review_instructions": ["Fixture draft; production review text is not reproduced."],
        },
    )
    return 0


def finalize(args):
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    if review.get("review_status") != "approved":
        raise SystemExit("review is not approved")
    approval = review.get("human_approval") or {}
    if approval.get("decision") not in {"approved", "not_required"}:
        raise SystemExit("review carries no approval decision")
    surfaces = [
        {"path": item["path"], "role": item["role"]}
        for item in review["surface_candidates"]
        if item.get("selected")
    ]
    if not surfaces or any(not item["role"] for item in surfaces):
        raise SystemExit("approved review selected no surfaces or omitted a role")
    if any(not gate.get("evidence") or not gate.get("notes") for gate in review["gates"]):
        raise SystemExit("approved review left a gate unmapped")
    publish(
        args.output,
        {
            "schema_version": "1.0",
            "spec_kind": "fixture_delivery_spec",
            "task_id": review["task"]["id"],
            "validated_commit": review["validated_commit"],
            "validated_tree": review["validated_tree"],
            "base_commit": review["base_commit"],
            "surfaces": surfaces,
            "gates": review["gates"],
            "artifacts": review["artifacts"],
            "validation_manifests": review["validation_manifests"],
            "approval": approval,
        },
    )
    return 0


def main(argv):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    draft_parser = commands.add_parser("draft")
    draft_parser.add_argument("--root", required=True)
    draft_parser.add_argument("--task-id", required=True)
    draft_parser.add_argument("--base-commit", required=True)
    draft_parser.add_argument("--output", required=True)
    draft_parser.add_argument("--validation-manifest", action="append", default=[])
    draft_parser.add_argument("--human-validation", action="append", default=[])
    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("--root", required=True)
    finalize_parser.add_argument("--review", required=True)
    finalize_parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "draft":
        if args.human_validation:
            raise SystemExit("the fixture draft never accepts human validation artifacts")
        return draft(args)
    return finalize(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

RECORD_DELIVERY_STUB = r'''#!/usr/bin/env python3
"""Fixture TaskGraph record_delivery: writes the committed record taskcontrol derives from."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    parser.add_argument("--root", required=True)
    parser.add_argument("--token-usage", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    head = (
        subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"), check=True, stdout=subprocess.PIPE
        )
        .stdout.decode("utf-8")
        .strip()
    )
    if spec.get("validated_commit") != head:
        raise SystemExit("delivery spec does not describe the checked-out commit")
    task_id = spec["task_id"]
    record_id = f"{task_id}-delivery-{head[:12]}"
    relative = f"Pipeline/TaskGraph/deliveries/{task_id}.json"
    target = root / relative
    if target.exists():
        raise SystemExit(f"delivery record already exists: {relative}")
    token_usage = Path(args.token_usage).read_bytes()
    record = {
        "schema_version": "1.0",
        "record_kind": "fixture_delivery_record",
        "task_id": task_id,
        "record_id": record_id,
        "validated_commit": spec["validated_commit"],
        "validated_tree": spec["validated_tree"],
        "base_commit": spec["base_commit"],
        "surfaces": spec["surfaces"],
        "gates": [gate["gate_id"] for gate in spec["gates"]],
        "artifact_sha256s": sorted(item["sha256"] for item in spec["artifacts"]),
        "token_usage_sha256": hashlib.sha256(token_usage).hexdigest(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    result = {
        "record_id": record_id,
        "record_path": relative,
        "created_paths": [relative],
        "validate_command": [sys.executable, "Pipeline/TaskGraph/taskcontrol.py", "validate"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

# Committed at Pipeline/Testing/run_unity_tests_clean.ps1. It never starts Unity: it
# publishes one internally consistent manifest set for the exact clean checkout it
# was pointed at and appends one line per execution to the log the test counts.
UNITY_RUNNER_STUB = r'''param(
    [Parameter(Mandatory = $true)][string]$TestPlatform,
    [Parameter(Mandatory = $true)][string]$TestFilter,
    [string]$UnityExecutable,
    [Parameter(Mandatory = $true)][string]$ProjectPath
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath $ProjectPath).Path
$commit = (& git -C $project rev-parse HEAD).Trim()
$tree = (& git -C $project rev-parse 'HEAD^{tree}').Trim()
$status = & git -C $project status --porcelain=v1 --untracked-files=all
if ($status) { throw 'fixture Unity runner requires a clean checkout' }
$outputRoot = Join-Path (Split-Path -Parent $project) '.muffcabbage-unity-runner'
$directory = Join-Path $outputRoot ([Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$xmlPath = Join-Path $directory 'test-results.xml'
$logPath = Join-Path $directory 'unity.log'
$xml = "<?xml version=`"1.0`" encoding=`"utf-8`"?>`n<test-run result=`"Passed`" total=`"1`" passed=`"1`" failed=`"0`" skipped=`"0`" />`n"
$log = "Unity validation log`nFixture runner executed $TestPlatform filter $TestFilter for commit $commit.`nAll tests passed.`n"
[System.IO.File]::WriteAllText($xmlPath, $xml, $utf8)
[System.IO.File]::WriteAllText($logPath, $log, $utf8)
function Get-Sha256Hex([string]$Path) {
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        try {
            ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $stream.Dispose()
        }
    }
    finally {
        $algorithm.Dispose()
    }
}
$manifest = [ordered]@{
    schema_version = '1.0'
    manifest_type = 'unity_test_validation'
    status = 'passed'
    validated_state = [ordered]@{
        commit = $commit
        tree = $tree
        post_commit = $commit
        post_tree = $tree
        repository_clean_before = $true
        repository_clean_after = $true
    }
    unity = [ordered]@{
        version = 'fixture-0.0.0'
        executable = 'fixture://no-unity-editor'
        exit_code = 0
        test_platform = $TestPlatform
        test_filter = $TestFilter
    }
    test_run = [ordered]@{ result = 'Passed'; total = 1; passed = 1; failed = 0; skipped = 0 }
    artifacts = [ordered]@{
        xml = [ordered]@{
            relative_path = 'test-results.xml'
            sha256 = (Get-Sha256Hex $xmlPath)
            size_bytes = (Get-Item -LiteralPath $xmlPath).Length
        }
        log = [ordered]@{
            relative_path = 'unity.log'
            sha256 = (Get-Sha256Hex $logPath)
            size_bytes = (Get-Item -LiteralPath $logPath).Length
        }
    }
    runner = [ordered]@{ path = 'Pipeline/Testing/run_unity_tests_clean.ps1' }
}
$manifestPath = Join-Path $directory 'validation-manifest.json'
$json = (($manifest | ConvertTo-Json -Depth 8) -replace "`r`n", "`n") + "`n"
[System.IO.File]::WriteAllText($manifestPath, $json, $utf8)
if ($env:NSC_MUFFCABBAGE_RUNNER_LOG) {
    [System.IO.File]::AppendAllText(
        $env:NSC_MUFFCABBAGE_RUNNER_LOG, "$TestPlatform`t$TestFilter`t$commit`n", $utf8
    )
}
Write-Host "Validation manifest: $manifestPath"
'''

# Installed as core.sshCommand in the throwaway global Git config. Git believes the
# origin is git@github.com:<repository>.git; this serves that one path from the
# disposable bare repository and refuses every other host or repository.
FAKE_SSH_TEMPLATE = r'''import shlex
import subprocess
import sys

BARE = %(bare)r
REPOSITORY_PATH = %(repository_path)r


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("fake ssh refused: %%r\n" %% (argv,))
        return 255
    host, command = argv
    parts = shlex.split(command)
    if (
        host != "git@github.com"
        or len(parts) != 2
        or parts[0] not in ("git-upload-pack", "git-receive-pack")
        or parts[1] != REPOSITORY_PATH
    ):
        sys.stderr.write("fake ssh refused: %%r\n" %% (argv,))
        return 255
    return subprocess.call(("git", parts[0][len("git-"):], BARE))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


# --------------------------------------------------------------------------------
# Disposable repository fixture
# --------------------------------------------------------------------------------


class Fixture:
    """One disposable bare remote, controller source clone, and checkout root."""

    def __init__(self, root: Path, scenario: Scenario) -> None:
        self.root = root
        self.scenario = scenario
        self.remote = root / "remote.git"
        self.source = root / "source"
        self.checkout_root = root / "checkouts"
        self.runner_log = root / "unity-runner.log"
        self.gitconfig = root / "gitconfig"
        self.fake_ssh = root / "fake_ssh.py"
        self.merge_root = root / "github-merges"
        self.environment = {
            "GIT_CONFIG_GLOBAL": str(self.gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            RUNNER_LOG_VARIABLE: str(self.runner_log),
        }
        self.initial_head = ""
        self.initial_tree = ""
        self.task: dict[str, Any] = {}
        self.memory = MemoryIssueBackend()
        self.backend: DeterministicGhIssueBackend | None = None
        self.inbox_number = 0

    def write_host_files(self) -> None:
        python = Path(sys.executable).resolve().as_posix()
        write_text(
            self.fake_ssh,
            FAKE_SSH_TEMPLATE
            % {"bare": self.remote.as_posix(), "repository_path": f"{REPOSITORY}.git"},
        )
        write_text(
            self.gitconfig,
            "\n".join(
                (
                    "[user]",
                    "\tname = Muffcabbage Fixture",
                    "\temail = muffcabbage-fixture@nosafecircle.invalid",
                    "[core]",
                    "\tautocrlf = false",
                    "\tlongpaths = true",
                    f'\tsshCommand = "{python}" -S -E "{self.fake_ssh.as_posix()}"',
                    "\tfscache = true",
                    "\tpreloadindex = true",
                    "[gc]",
                    "\tauto = 0",
                    "[ssh]",
                    "\tvariant = simple",
                    "[init]",
                    "\tdefaultBranch = main",
                    "",
                )
            ),
        )

    def populate(self) -> None:
        git(self.root, "init", "-q", "--bare", str(self.remote))
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        seed = self.root / "seed"
        git(self.root, "init", "-q", "-b", "main", str(seed))
        task = self.scenario.contract()
        task_text = json.dumps(task, indent=2, sort_keys=True) + "\n"
        write_text(seed / "Tasks" / f"{self.scenario.task_id}.yaml", task_text)
        write_text(
            seed / "Pipeline" / "TaskReviewAgent" / "authoritative_validation_policy.json",
            json.dumps(
                {
                    "schema_version": "1.0",
                    "tasks": {
                        self.scenario.task_id: {
                            "task_contract_sha256": hashlib.sha256(
                                task_text.encode("utf-8")
                            ).hexdigest(),
                            "required_test_platforms": ["EditMode"],
                            "test_filters": {"EditMode": self.scenario.test_filter},
                            "authority": (
                                "committed_private_synthetic_gauntlet_validation_policy"
                            ),
                        }
                    },
                    "decomposition_child_templates": {},
                },
                indent=2,
            )
            + "\n",
        )
        write_text(seed / "Pipeline" / "TaskGraph" / "taskcontrol.py", TASKCONTROL_STUB)
        write_text(seed / "Pipeline" / "TaskGraph" / "record_delivery.py", RECORD_DELIVERY_STUB)
        write_text(
            seed / "Pipeline" / "TaskDelivery" / "generate_delivery_spec.py", DELIVERY_SPEC_STUB
        )
        write_text(seed / "Pipeline" / "Testing" / "run_unity_tests_clean.ps1", UNITY_RUNNER_STUB)
        write_text(
            seed / "README.md",
            "# Muffcabbage acceptance fixture\n\nDisposable repository; nothing here is real.\n",
        )
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "Muffcabbage acceptance fixture baseline")
        git(seed, "remote", "add", "origin", ORIGIN_URL)
        git(seed, "push", "-q", "-u", "origin", "main")
        git(self.root, "clone", "-q", ORIGIN_URL, str(self.source))
        self.checkout_root.mkdir()
        self.merge_root.mkdir()
        self.initial_head = git(self.source, "rev-parse", "HEAD")
        self.initial_tree = git(self.source, "rev-parse", "HEAD^{tree}")
        self.task = load_committed_task(self.source, self.scenario.task_id)
        # The production handoff notifies Vincent's inbox Issue and the automated
        # evidence path removes that notification again; both run for real here.
        inbox = self.memory.create_issue(
            title=VINCENT_INBOX_TITLE,
            body=f"{VINCENT_INBOX_MARKER}\n\nFixture inbox for human-action notifications.\n",
            labels=[],
            assignees=["cathode26"],
        )
        self.inbox_number = int(inbox["number"])
        self.backend = DeterministicGhIssueBackend(source_root=self.source, memory=self.memory)

    def remote_head(self, ref: str) -> str:
        return git(self.remote, "rev-parse", "--verify", f"{ref}^{{commit}}")

    def runner_executions(self) -> list[str]:
        if not self.runner_log.is_file():
            return []
        return [
            line
            for line in self.runner_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def service(self, worker_id: str) -> IssueWorkflowService:
        assert self.backend is not None
        return IssueWorkflowService(
            backend=self.backend,
            task_loader=lambda task_id: load_committed_task(self.source, task_id),
            worker_id=worker_id,
            vincent_inbox_title=VINCENT_INBOX_TITLE,
        )

    def issue(self):
        snapshot = self.service("acceptance-observer").find(self.scenario.task_id)
        require(snapshot is not None, "the managed muffcabbage Issue is missing")
        return snapshot


@contextmanager
def disposable_fixture(scenario: Scenario = FAST):
    with tempfile.TemporaryDirectory(
        prefix="muffcabbage-e2e-", ignore_cleanup_errors=True
    ) as text:
        fixture = Fixture(Path(text).resolve(), scenario)
        fixture.write_host_files()
        with patch.dict(os.environ, fixture.environment):
            fixture.populate()
            yield fixture


class DeterministicGhIssueBackend(GhIssueBackend):
    """The isinstance-compatible deterministic Issue backend.

    ``GhIssueBackend.__init__`` probes the gh CLI and its GitHub authentication,
    so it is deliberately not called. Repository binding still goes through the
    production ``resolve_issue_backend_repository`` against the checkout's origin;
    every Issue operation is served by the shared in-memory store.
    """

    def __init__(self, *, source_root: Path, memory: MemoryIssueBackend) -> None:
        self.source_root = Path(source_root).resolve()
        self.repository = resolve_issue_backend_repository(self.source_root)
        self.memory = memory

    def _run(self, *args: Any, **values: Any) -> Any:
        raise AssertionError("the gh CLI must never run in the muffcabbage acceptance run")

    def _json(self, *args: Any, **values: Any) -> Any:
        raise AssertionError("the gh CLI must never run in the muffcabbage acceptance run")

    def _paginated_api_objects(self, *args: Any, **values: Any) -> Any:
        raise AssertionError("the GitHub API must never be paged in the acceptance run")

    def list_issues(self) -> list[dict[str, Any]]:
        return self.memory.list_issues()

    def get_issue(self, issue_number: int) -> dict[str, Any] | None:
        return self.memory.get_issue(issue_number)

    def get_comments(self, issue_number: int) -> list[dict[str, Any]]:
        return self.memory.get_comments(issue_number)

    def get_issue_events(self, issue_number: int) -> list[dict[str, Any]]:
        return self.memory.get_issue_events(issue_number)

    def create_issue(self, **values: Any) -> dict[str, Any]:
        return self.memory.create_issue(**values)

    def update_issue(self, issue_number: int, **values: Any) -> dict[str, Any]:
        return self.memory.update_issue(issue_number, **values)

    def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        return self.memory.add_comment(issue_number, body)

    def delete_comment(self, issue_number: int, comment_id: Any) -> None:
        self.memory.delete_comment(issue_number, comment_id)

    def ensure_labels(self) -> None:
        self.memory.ensure_labels()

    def close_issue(self, issue_number: int) -> None:
        issue = self.memory.issues[issue_number]
        issue["state"] = "CLOSED"
        issue["updated_at"] = self.memory.now()


def _forbidden_github_backend(*args: Any, **values: Any) -> Any:
    raise AssertionError(
        "a real GhIssueBackend must never be constructed in the muffcabbage acceptance run"
    )


@contextmanager
def forbid_real_github_backends():
    with ExitStack() as stack:
        for module in (
            scheduler_module,
            dispatch_plan_module,
            snapshot_module,
            real_workflow_module,
        ):
            stack.enter_context(
                patch.object(module, "GhIssueBackend", _forbidden_github_backend)
            )
        yield


@contextmanager
def deterministic_synthetic_approver(fixture: Fixture):
    """Bind the production approver to the disposable repository without gh.

    The production preflight shells ``gh repo view`` to prove the repository is
    private and default-branch main. That single probe is the only part replaced;
    the origin binding, attached-main, and exact origin/main checks it also makes
    are performed here with Git, and the shared deterministic Issue backend is
    handed to the approver where it would construct ``GhIssueBackend``.
    """

    calls = {"rehearsal_checks": 0, "backend_requests": 0}

    def require_private_rehearsal(
        source: Path, confirmed_repository: str, expected_source_head: str | None = None
    ) -> str:
        calls["rehearsal_checks"] += 1
        exact = Path(source).resolve()
        require(exact == fixture.source.resolve(), f"approver pointed at {exact}")
        parsed = _parse_github_repository(git(exact, "remote", "get-url", "origin"))
        require(parsed is not None, "approver source origin is not a GitHub remote")
        repository = "/".join(parsed)
        require(
            repository.casefold() == confirmed_repository.casefold(),
            f"approver repository {repository!r} differs from {confirmed_repository!r}",
        )
        require(git(exact, "symbolic-ref", "--quiet", "--short", "HEAD") == "main", "not on main")
        head = git(exact, "rev-parse", "HEAD")
        if expected_source_head is not None:
            require(head == expected_source_head, "approver source HEAD moved")
        git(exact, "fetch", "-q", "origin", "main")
        require(head == git(exact, "rev-parse", "origin/main"), "source is not exact origin/main")
        return repository

    def backend_factory(*, source_root: Path, repository: str | None = None) -> Any:
        calls["backend_requests"] += 1
        require(
            Path(source_root).resolve() == fixture.source.resolve(),
            "approver requested an Issue backend for a different source",
        )
        return fixture.backend

    with patch.object(approver, "_require_private_rehearsal", require_private_rehearsal):
        with patch.object(approver, "GhIssueBackend", backend_factory):
            yield calls


class ExecutableAudit:
    """Record every executable the run starts; proves no provider/GitHub reach."""

    def __init__(self) -> None:
        self.launched: list[str] = []
        self._patch: Any = None

    def __enter__(self) -> "ExecutableAudit":
        audit = self
        original = subprocess.Popen

        class AuditedPopen(original):  # type: ignore[misc,valid-type]
            def __init__(self, args: Any, *positional: Any, **values: Any) -> None:
                first = args[0] if isinstance(args, (list, tuple)) else str(args)
                require(
                    Path(first).name.casefold() in ALLOWED_EXECUTABLES,
                    f"forbidden executable refused before launch: {first}",
                )
                audit.launched.append(str(first))
                super().__init__(args, *positional, **values)

        self._patch = patch.object(subprocess, "Popen", AuditedPopen)
        self._patch.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._patch.stop()

    def executables(self) -> set[str]:
        return {Path(item).name.casefold() for item in self.launched}

    def count(self, name: str) -> int:
        return sum(1 for item in self.launched if Path(item).name.casefold() == name)


# --------------------------------------------------------------------------------
# Deterministic architect
# --------------------------------------------------------------------------------


def scenario_advisory(
    scenario: Scenario,
    task: Mapping[str, Any],
    source_head: str,
    *,
    requested_tier: str | None = None,
) -> ArchitectAdvisory:
    """The architect's exact prediction for one scenario's isolated file surface.

    ``requested_tier`` overrides the scenario's honest tier so a guard can show what
    deterministic policy does with an architect that asks for too little.
    """

    scripts = [source for source, _ in scenario.file_pairs]
    return ArchitectAdvisory.from_dict(
        {
            "task_id": task["id"],
            "source_head": source_head,
            "task_contract_sha256": task["task_contract_sha256"],
            "predicted_change_surface": {
                "exact_paths": list(scenario.exact_paths),
                "path_patterns": [],
                "unity_serialized_assets": [scenario.scene_path] if scenario.scene_path else [],
                "symbols_or_components": list(scenario.class_names),
                "shared_systems": [],
            },
            # This is parallel-conflict risk, not task rigor. The scene is isolated;
            # its serialized contents still force deep under resolve_task_rigor.
            "integration_risk": "low",
            "parallel_recommendation": "start",
            "work_type_recommendation": "implementation",
            "execution_recommendation": {
                "capability_tier": requested_tier or scenario.architect_tier,
                "provider_preference": "no_preference",
                "rationale": (
                    f"One serialized scene marker in {scenario.scene_path}, with a matching constant."
                    if scenario.scene_path else
                    f"{len(scripts)} new constant file(s) with deterministic .meta "
                    "companions in isolated new files; no shared system or serialized "
                    "content is touched."
                ),
            },
            "conflicting_task_ids": [],
            "conflict_reasons": [],
            "escalation": {"category": "none", "question": ""},
            "unknown_surface_disjointness": [],
            "design_advice": {
                "implementation_summary": (
                    task["decomposition_reason"] if scenario.scene_path else
                    "Create " + ", ".join(scripts) + f" with Value = {scenario.number} "
                    "and the deterministic .meta sidecar of each."
                ),
                "recommended_interfaces": [],
                "sequencing_notes": [],
                "suggested_exclusive_resources": [],
                "suggested_taskgraph_changes": [],
                "suggested_decomposition": [],
            },
            "evidence": [],
            "confidence": 0.92,
            "assumptions": [],
        }
    )


class DeterministicArchitect:
    """Batch-mode architect stand-in: admits exactly the scenario task at its tier."""

    def __init__(self, fixture: Fixture, *, requested_tier: str | None = None) -> None:
        self.fixture = fixture
        self.requested_tier = requested_tier
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **values: Any) -> ArchitectBatchAnalysis:
        require("candidates" in values, "the scheduler must request a portfolio batch")
        admission_limit = int(values["admission_limit"])
        considered: list[ArchitectBatchConsideration] = []
        admissions: list[ArchitectAdvisory] = []
        portfolio: list[dict[str, Any]] = []
        for item in values["candidates"]:
            task = item["task"]
            portfolio.append(
                {
                    "task_id": task["id"],
                    "work_types": list(item["eligible_work_types"]),
                    "resume_phase": item.get("resume_phase"),
                }
            )
            for work_type in item["eligible_work_types"]:
                admit = (
                    task["id"] == self.fixture.scenario.task_id
                    and work_type == "implementation"
                    and len(admissions) < admission_limit
                )
                considered.append(
                    ArchitectBatchConsideration(
                        task_id=task["id"],
                        work_type=work_type,
                        disposition="admit" if admit else "wait",
                        rationale=(
                            "Deterministic fixture admits the isolated muffcabbage pair."
                            if admit
                            else "Deterministic fixture admits nothing else."
                        ),
                    )
                )
                if admit:
                    admissions.append(
                        scenario_advisory(
                            self.fixture.scenario,
                            task,
                            values["source_head"],
                            requested_tier=self.requested_tier,
                        )
                    )
        index = len(self.calls) + 1
        self.calls.append(
            {
                "portfolio": portfolio,
                "admission_limit": admission_limit,
                "source_head": values["source_head"],
                "admitted": [advisory.task_id for advisory in admissions],
            }
        )
        return ArchitectBatchAnalysis(
            analysis_id=f"analysis-batch-{index}",
            batch=ArchitectBatch(
                source_head=values["source_head"],
                batch_rationale="Deterministic fixture ordered admission batch.",
                considered=tuple(considered),
                admissions=tuple(admissions),
            ),
            artifact_path=self.fixture.root / "architect" / f"batch-{index}.json",
            active_surface_fingerprint="f" * 64,
            invocation_metadata={
                "provider": "deterministic-fixture",
                "model": "none",
                "paid": False,
            },
        )


# --------------------------------------------------------------------------------
# GitHub PR/Issue CLI emulation against the disposable bare remote
# --------------------------------------------------------------------------------


def _cli_options(tokens: Sequence[str]) -> tuple[list[str], dict[str, Any]]:
    positional: list[str] = []
    options: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                options[token] = tokens[index + 1]
                index += 2
            else:
                options[token] = True
                index += 1
        else:
            positional.append(token)
            index += 1
    return positional, options


class DisposableGitHub:
    """Emulate the exact gh PR/Issue commands downstream issues, on the bare remote."""

    def __init__(self, fixture: Fixture) -> None:
        self.fixture = fixture
        self.pull_requests: dict[int, dict[str, Any]] = {}
        self.next_number = 1
        self.commands: list[tuple[str, ...]] = []

    def _completed(
        self, args: Sequence[str], returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            tuple(args), returncode, stdout.encode("utf-8"), stderr.encode("utf-8")
        )

    def _branch_head(self, branch: str) -> str:
        return self.fixture.remote_head(f"refs/heads/{branch}")

    def _view(self, pull_request: Mapping[str, Any]) -> dict[str, Any]:
        merged = pull_request["state"] == "MERGED"
        head = pull_request["merged_head"] if merged else self._branch_head(pull_request["branch"])
        # Emulated CI: the deterministic workflow has already completed successfully
        # for this exact head. Production fails closed on an empty rollup and waits
        # in-process for pending checks, so the emulation must report a real result.
        check = {
            "__typename": "CheckRun",
            "name": "windows-smoke",
            "workflowName": "TaskReviewAgent Deterministic Validation",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "startedAt": pull_request["created_at"],
            "completedAt": pull_request["created_at"],
            "detailsUrl": (
                f"https://github.com/{REPOSITORY}/actions/runs/{pull_request['number']}"
                f"/job/{pull_request['number']}"
            ),
            "headSha": head,
        }
        return {
            "number": pull_request["number"],
            "url": pull_request["url"],
            "state": pull_request["state"],
            "headRefOid": head,
            "baseRefName": "main",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "statusCheckRollup": [check],
            "mergeCommit": {"oid": pull_request["merge_commit"]} if merged else None,
        }

    def __call__(self, args: Sequence[str], cwd: Path, timeout_seconds: float) -> Any:
        argv = tuple(str(item) for item in args)
        self.commands.append(argv)
        require(argv[0] == "gh", f"not a gh command: {argv}")
        group, verb = argv[1], argv[2]
        positional, options = _cli_options(argv[3:])
        require(
            str(options.get("--repo")).casefold() == REPOSITORY.casefold(),
            f"gh command targeted {options.get('--repo')!r}, not the bound repository",
        )
        if (group, verb) == ("pr", "list"):
            matches = [
                self._view(item)
                for item in self.pull_requests.values()
                if item["branch"] == options["--head"]
                and item["state"] == "OPEN"
                and options.get("--base") == "main"
            ]
            return self._completed(argv, stdout=json.dumps(matches))
        if (group, verb) == ("pr", "create"):
            require(options.get("--base") == "main", "pull requests must target main")
            branch = str(options["--head"])
            head = self._branch_head(branch)
            number = self.next_number
            self.next_number += 1
            self.pull_requests[number] = {
                "number": number,
                "url": f"https://github.com/{REPOSITORY}/pull/{number}",
                "branch": branch,
                "title": options.get("--title"),
                "body": options.get("--body"),
                "state": "OPEN",
                "created_at": utc_now(),
                "created_head": head,
                "merge_commit": None,
                "merged_head": None,
            }
            return self._completed(argv, stdout=self.pull_requests[number]["url"] + "\n")
        if (group, verb) == ("pr", "view"):
            pull_request = self.pull_requests[int(positional[0])]
            return self._completed(argv, stdout=json.dumps(self._view(pull_request)))
        if (group, verb) == ("pr", "merge"):
            pull_request = self.pull_requests[int(positional[0])]
            require(options.get("--merge") is True, "downstream must request a merge commit")
            expected_head = str(options["--match-head-commit"])
            actual_head = self._branch_head(pull_request["branch"])
            if actual_head != expected_head:
                return self._completed(
                    argv, returncode=1, stderr=f"head moved from {expected_head} to {actual_head}"
                )
            branch = pull_request["branch"]
            clone = self.fixture.merge_root / f"pr-{pull_request['number']}"
            git(
                self.fixture.merge_root,
                "clone", "-q", "--branch", "main", "--single-branch",
                str(self.fixture.remote), str(clone),
            )
            git(clone, "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
            git(
                clone, "merge", "-q", "--no-ff", "-m",
                f"Merge pull request #{pull_request['number']} from {branch}",
                f"origin/{branch}",
            )
            merge_commit = git(clone, "rev-parse", "HEAD")
            git(clone, "push", "-q", "origin", "HEAD:refs/heads/main")
            pull_request.update(
                state="MERGED", merge_commit=merge_commit, merged_head=expected_head
            )
            return self._completed(argv)
        if (group, verb) == ("issue", "close"):
            require(options.get("--reason") == "completed", "Issues close only as completed")
            assert self.fixture.backend is not None
            self.fixture.backend.close_issue(int(positional[0]))
            return self._completed(argv)
        raise AssertionError(f"unsupported gh command reached the emulator: {argv}")


def make_command_runner(github: DisposableGitHub):
    """Route downstream commands: gh -> emulator, git/python -> real, else refuse."""

    def command_runner(args: Sequence[str], cwd: Path, timeout_seconds: float) -> Any:
        first = str(args[0])
        if first == "gh":
            return github(args, cwd, timeout_seconds)
        if Path(first).name.casefold() in {"git", "git.exe"} or first == sys.executable:
            return _default_runner(args, cwd, timeout_seconds)
        raise AssertionError(f"downstream attempted a forbidden command: {tuple(args)!r}")

    return command_runner


# --------------------------------------------------------------------------------
# Deterministic downstream decisions and in-process workers
# --------------------------------------------------------------------------------


class DeterministicDownstreamDecisions:
    """Select only the single action the host's deterministic state permits.

    The production Codex provider is patched by ``downstream_determinism`` to do the
    same for zero-argument actions; this adapter extends that to the argument-bearing
    actions using facts the host already published (the committed test plan and the
    delivery-review draft facts). It never guesses: more than one permitted action is
    a failure, not a choice.
    """

    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.decisions: list[str] = []

    def decide(
        self, *, task_id: str, turn: int, prompt: str, allowed_actions: Sequence[str]
    ) -> SupervisorDecision:
        selected = determinism._ALLOWED_ACTION_CONTEXT.get()
        try:
            require(
                selected is not None and len(selected) == 1 and selected[0] in set(allowed_actions),
                f"turn {turn}: host state did not narrow to exactly one action: {selected!r}",
            )
            action = selected[0]
            arguments = self._arguments(action)
        finally:
            determinism._ALLOWED_ACTION_CONTEXT.set(None)
        self.decisions.append(action)
        return SupervisorDecision(
            task_id=task_id,
            action=action,
            arguments=arguments,
            rationale=f"Deterministic fixture adapter: host state permits exactly {action}.",
        )

    def _arguments(self, action: str) -> dict[str, Any]:
        if action == "acquire_agent_lease":
            return {
                "planned_approach": (
                    "Resume the exact validated synthetic handoff and advance delivery evidence."
                ),
                "expected_validation": (
                    "Reuse the exact pre-handoff EditMode manifest, then package, prove, and merge."
                ),
            }
        if action == "run_authoritative_unity_test":
            plan = self.controller.last_observation["downstream"]["authoritative_test_plan"]
            platform = plan["required_test_platforms"][0]
            return {"test_platform": platform, "test_filter": plan["test_filters"][platform]}
        if action == "create_delivery_review_proposal":
            facts = self.controller.delivery_review_facts()
            evidence = [item["id"] for item in facts["artifacts"]]
            return {
                "selected_surfaces": [
                    {"path": item["path"], "role": "implementation"}
                    for item in facts["surface_candidates"]
                    if item.get("selected")
                ],
                "gate_mappings": [
                    {
                        "gate_id": gate["gate_id"],
                        "evidence": evidence,
                        "notes": (
                            f"Gate {gate['gate_id']} is proven by the exact EditMode manifest "
                            "artifacts for the validated commit."
                        ),
                    }
                    for gate in facts["gates"]
                ],
                "approval_notes": (
                    "Deterministic fixture proposal bound to the exact validated commit."
                ),
            }
        return {}


class FakeWorkerProcess:
    def __init__(self, pid: int, returncode: int) -> None:
        self.pid = pid
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode

    def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:  # pragma: no cover - never expected
        raise AssertionError("the scheduler killed a finished fixture worker")

    def terminate(self) -> None:  # pragma: no cover - never expected
        raise AssertionError("the scheduler terminated a finished fixture worker")


def _parse_worker_argv(argv: Sequence[str]) -> dict[str, Any]:
    require(argv[0] == sys.executable and argv[1] == "-u", f"unexpected worker argv head: {argv[:2]}")
    require(
        Path(argv[2]).name == "host_worker_launcher.py",
        f"scheduler did not launch the host worker launcher: {argv[2]}",
    )
    positional, options = _cli_options(argv[3:])
    require(not positional, f"unexpected positional worker arguments: {positional}")
    return options


class InProcessWorkers:
    """Execute the scheduler's exact worker argv in-process, phase by Issue state."""

    def __init__(
        self,
        fixture: Fixture,
        command_runner: Any,
        *,
        forge_result_source_head: bool = False,
    ) -> None:
        self.fixture = fixture
        self.command_runner = command_runner
        self.forge_result_source_head = forge_result_source_head
        self.launches: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []
        self.failures: list[str] = []
        self.next_pid = 51000
        self.execution_bridges: list[ExecutionCrewBridge] = []
        self.crew_commands: list[tuple[str, ...]] = []
        self.validation_commands: list[tuple[str, ...]] = []

    def _record_execution(self, checkout: Path, options: Mapping[str, Any], lease_id: str):
        """Stand in for crew output; exercise real bridge validation and persistence.

        The accepted scope and role result are fixture data, like the code change.
        No Docker command is executed. The bridge's command builder, result checks,
        receipt serializer and reload are production code.
        """
        scenario = self.fixture.scenario
        accepted = SimpleNamespace(
            task_id=scenario.task_id,
            lease_id=lease_id,
            plan_id=f"fixture-plan-{options['--run-id']}",
            source_head=options["--admission-source-head"],
            task_contract_sha256=options["--task-contract-sha256"],
            plan=SimpleNamespace(
                existing_implementation_paths=(),
                new_implementation_paths=tuple(sorted(scenario.exact_paths, key=str.casefold)),
                existing_test_paths=("Pipeline/Testing/run_unity_tests_clean.ps1",),
                new_test_paths=(),
            ),
        )
        scope = SimpleNamespace(task_id=scenario.task_id, task=self.fixture.task, accepted=accepted)
        candidate = (git(checkout, "diff", "--cached", "--binary") + "\n").encode("utf-8")

        def crew_output(command, cwd, timeout_seconds):
            self.crew_commands.append(tuple(command))
            require(cwd == checkout, "crew command escaped its disposable checkout")
            result_dir = bridge.output_root / options["--run-id"]
            write_text(result_dir / "candidate.patch", candidate.decode("utf-8"))
            result = {
                "run_id": options["--run-id"],
                "task_id": scenario.task_id,
                "source_head": accepted.source_head,
                "provider": command[command.index("--provider") + 1],
                "crew_profile": command[command.index("--crew-profile") + 1],
                "validation_profile": command[command.index("--validation-profile") + 1],
                "required_roles": list(CREW_PROFILE_ROLES[bridge.crew_profile]),
                "execution_model": bridge.execution_model,
                "execution_reasoning_effort": bridge.execution_reasoning_effort,
                "task_contract_identity": {
                    "sha256": accepted.task_contract_sha256,
                    "path": f"Tasks/{scenario.task_id}.yaml",
                },
                **{f"requested_{key}": list(value) for key, value in vars(accepted.plan).items()},
                "crew_status": "review_ready",
                "candidate_patch_sha256": hashlib.sha256(candidate).hexdigest(),
                "final_actual_changed_paths": list(scenario.exact_paths),
                "rejection_reasons": [],
                "evidence_authority": "deterministic_fixture_crew_output",
            }
            payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
            write_text(result_dir / "crew_result.json", payload)
            return subprocess.CompletedProcess(command, 0, payload.encode("utf-8"), b"")

        bridge = ExecutionCrewBridge(
            checkout=checkout, scope=scope, command_runner=crew_output,
            execution_model=options.get("--execution-model"),
            execution_reasoning_effort=options.get("--execution-reasoning-effort"),
            crew_profile=options["--crew-profile"],
            validation_profile=options["--validation-profile"],
        )
        bridge.output_root = self.fixture.root / "crew-results"
        execution = bridge._run_prepared(
            accepted=accepted, provider=options["--execution-provider"],
            retry_run_id=None, feedback=None, pool_owner=None, pool_assignment=None,
        )
        self.execution_bridges.append(bridge)
        return bridge, execution

    def __call__(self, command: Sequence[str], **values: Any) -> FakeWorkerProcess:
        argv = tuple(str(item) for item in command)
        options = _parse_worker_argv(argv)
        pid = self.next_pid
        self.next_pid += 1
        launch = {
            "argv": argv,
            "options": options,
            "pid": pid,
            "phase": None,
            "exit_code": None,
            "seconds": None,
        }
        self.launches.append(launch)
        launched_at = time.perf_counter()
        run_dir = initialize_worker_run(
            output_root=Path(options["--output-root"]),
            task_id=options["--task-id"],
            run_id=options["--run-id"],
            worker_id=options["--worker-id"],
            started_at_utc=utc_now(),
        )
        try:
            exit_code = self._run(options, pid, run_dir, launch)
        except Exception as exc:  # noqa: BLE001 - reported through the worker contract
            self.failures.append(f"{type(exc).__name__}: {exc}")
            try:
                write_worker_result(
                    run_dir=run_dir,
                    run_id=options["--run-id"],
                    worker_id=options["--worker-id"],
                    task_id=options["--task-id"],
                    source_head=options["--admission-source-head"],
                    task_contract_sha256=options["--task-contract-sha256"],
                    terminal_status="error",
                    outcome_authority="muffcabbage_fixture_worker_exception",
                    issue_number=self._admission_issue_number(options),
                    exit_code=2,
                    pid=pid,
                )
            except Exception as nested:  # noqa: BLE001
                self.failures.append(f"result publication failed: {nested}")
            exit_code = 2
        launch["exit_code"] = exit_code
        launch["seconds"] = time.perf_counter() - launched_at
        return FakeWorkerProcess(pid, exit_code)

    @staticmethod
    def _admission_issue_number(options: Mapping[str, Any]) -> int | None:
        value = options.get("--admission-issue-number")
        return int(value) if value is not None else None

    def _run(self, options: Mapping[str, Any], pid: int, run_dir: Path, launch: dict[str, Any]) -> int:
        task_id = options["--task-id"]
        snapshot = self.fixture.service(options["--worker-id"]).find(task_id)
        if snapshot is None or snapshot.state is None or (
            snapshot.state.phase is WorkflowPhase.IMPLEMENTATION
        ):
            launch["phase"] = "implementation"
            return self._run_implementation(options, pid, run_dir)
        state = snapshot.state
        require(
            state.state is WorkflowState.AGENT_READY
            and state.phase in {WorkflowPhase.DELIVERY_EVIDENCE, WorkflowPhase.MERGE_CLOSEOUT},
            f"worker launched for an unexpected Issue state {state.state.value}/{state.phase.value}",
        )
        launch["phase"] = state.phase.value
        return self._run_downstream(options, pid, run_dir)

    def _run_implementation(self, options: Mapping[str, Any], pid: int, run_dir: Path) -> int:
        task_id = options["--task-id"]
        worker_id = options["--worker-id"]
        run_id = options["--run-id"]
        source_head = options["--admission-source-head"]
        contract = options["--task-contract-sha256"]
        source = Path(options["--source"])
        checkout_root = Path(options["--checkout-root"])
        scenario = self.fixture.scenario
        service = self.fixture.service(worker_id)
        workflow = RealTaskReviewWorkflow(
            source=source,
            task_id=task_id,
            checkout_root=checkout_root,
            worker_id=worker_id,
            issue_workflow_service=service,
            allow_local_remote_for_tests=True,
        )
        observation = workflow.observe_goal_state()
        require(
            observation["environment"]["ready"] is True,
            f"environment not ready: {observation['environment']['errors']}",
        )
        require(
            observation["environment"]["source_head"] == source_head,
            "admission source head differs from the observed controller main",
        )
        require(
            observation["task"]["task_contract_sha256"] == contract,
            "admission task contract differs from the committed contract",
        )
        lease = workflow.acquire_agent_lease(
            planned_approach=(
                f"Create {len(scenario.file_pairs)} isolated muffcabbage script(s) with "
                f"Value = {scenario.number} and their .meta companions, then hand off."
            ),
            expected_validation="The committed EditMode filter passes on the exact handoff commit.",
        )
        require(lease.get("status") not in {None, "blocked"}, f"lease was not granted: {lease}")
        workflow.observe_goal_state()
        prepared = workflow.prepare_task_checkout()
        require(prepared.get("status") == "created", f"checkout was not created: {prepared}")
        checkout = workflow.checkout_manager.checkout_path
        branch = str(prepared["branch"])

        # ExecutionCrew stand-in: the only implementation step this harness simulates.
        for (source_path, meta_path), class_name in zip(
            scenario.file_pairs, scenario.class_names
        ):
            write_text(
                checkout / source_path,
                "namespace NoSafeCircle.DoorPrototype\n{\n"
                f"    public static class {class_name}\n    {{\n"
                f"        public const int Value = {scenario.number};\n    }}\n}}\n",
            )
            write_text(
                checkout / meta_path,
                "fileFormatVersion: 2\n"
                f"guid: {_guid(source_path)}\n"
                "MonoImporter:\n  externalObjects: {}\n  serializedVersion: 2\n"
                "  defaultReferences: []\n  executionOrder: 0\n  icon: {instanceID: 0}\n"
                "  userData:\n  assetBundleName:\n  assetBundleVariant:\n",
            )
        if scenario.scene_path:
            write_text(checkout / scenario.scene_path, scenario.scene_text())
            write_text(
                checkout / (scenario.scene_path + ".meta"),
                f"fileFormatVersion: 2\nguid: {_guid(scenario.scene_path)}\n"
                "DefaultImporter:\n  externalObjects: {}\n  userData:\n"
                "  assetBundleName:\n  assetBundleVariant:\n",
            )
        git(checkout, "add", "--", *scenario.exact_paths)
        leased = service.find(task_id)
        assert leased is not None and leased.state is not None
        bridge, execution = self._record_execution(checkout, options, str(leased.state.lease_id))
        git(checkout, "commit", "-q", "-m", f"Implement {task_id}: {self.fixture.task['title']}")
        commit = git(checkout, "rev-parse", "HEAD")
        tree = git(checkout, "rev-parse", "HEAD^{tree}")

        # full_relevant does not select extra commands at this base: production's
        # planner uses the committed task policy for every crew profile. Exercise
        # the actual planner/runner and pin its entire command, not a guessed suite.
        plan = validation_plan_for(checkout, self.fixture.task)
        require(
            plan is not None
            and plan["required_test_platforms"] == ["EditMode"]
            and plan["test_filters"] == {"EditMode": scenario.test_filter},
            f"committed validation plan is not the exact muffcabbage filter: {plan}",
        )

        def validation_runner(command, cwd, timeout_seconds):
            self.validation_commands.append(tuple(command))
            require(cwd == checkout, "validation escaped the disposable checkout")
            require(tuple(command) == (
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(checkout / "Pipeline/Testing/run_unity_tests_clean.ps1"),
                "-TestPlatform", "EditMode", "-TestFilter", scenario.test_filter,
                "-ProjectPath", str(checkout),
            ), f"unexpected production validation command: {command}")
            return subprocess.run(
                command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=min(timeout_seconds, 300.0),
            )

        integrator = CandidateIntegrator(
            checkout=checkout, branch=branch, task_title=self.fixture.task["title"],
            scope=bridge.scope, execution=bridge, unity_command_runner=validation_runner,
        )
        (validation_fact,) = integrator._run_pre_handoff_validations(commit, execution)
        state_root = checkout_root / ".task-review-agent"
        git(checkout, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        leased = service.find(task_id)
        assert leased is not None and leased.state is not None
        receipt = CandidateIntegrationReceipt(
            task_id=task_id,
            lease_id=str(leased.state.lease_id),
            plan_id=f"fixture-plan-{run_id}",
            run_id=run_id,
            provider="codex",
            branch=branch,
            base_head=source_head,
            commit=commit,
            commit_tree=tree,
            task_contract_sha256=contract,
            candidate_sha256=execution.candidate_sha256,
            changed_paths=scenario.exact_paths,
            pre_handoff_validations=(validation_fact,),
            completed_checks=(
                f"Pre-handoff authoritative Unity EditMode validation passed on exact commit {commit}.",
                "Implementation and tests were committed on the canonical task branch.",
                "The exact commit was pushed as the remote task branch.",
            ),
        )
        payload = receipt.to_dict()
        payload["receipt_sha256"] = semantic_sha256(payload)
        write_text(
            state_root / f"{task_id}.integration.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        workflow.publish_human_handoff(
            branch=branch,
            head_commit=commit,
            implementation_summary=(
                "Created " + ", ".join(source for source, _ in scenario.file_pairs)
                + f" with Value = {scenario.number} and their .meta companions."
            ),
            completed_checks=list(receipt.completed_checks),
            human_steps=["Run the committed EditMode filter for the exact handoff commit."],
            expected_result=(
                f"{scenario.test_filter} passes and proves Value == {scenario.number}."
            ),
        )
        handed_off = service.find(task_id)
        assert handed_off is not None
        forged_head = ("f" * 39 + "e") if self.forge_result_source_head else source_head
        write_worker_result(
            run_dir=run_dir,
            run_id=run_id,
            worker_id=worker_id,
            task_id=task_id,
            source_head=forged_head,
            task_contract_sha256=contract,
            terminal_status="human_action_required",
            outcome_authority="muffcabbage_fixture_implementation_worker",
            issue_number=handed_off.issue_number,
            exit_code=0,
            pid=pid,
        )
        return 0

    def _run_downstream(self, options: Mapping[str, Any], pid: int, run_dir: Path) -> int:
        task_id = options["--task-id"]
        worker_id = options["--worker-id"]
        service = self.fixture.service(worker_id)
        workflow = DownstreamTaskReviewWorkflow(
            source=Path(options["--source"]),
            task_id=task_id,
            checkout_root=Path(options["--checkout-root"]),
            worker_id=worker_id,
            issue_workflow_service=service,
            allow_local_remote_for_tests=True,
        )
        controller = ResumableDownstreamTaskController(
            workflow=workflow,
            unity_executable=None,
            output_root=Path(options["--output-root"]),
            command_runner=self.command_runner,
        )
        guarded = GuardedTaskController(controller)
        provider = DeterministicDownstreamDecisions(guarded)
        outcome = run_openai_downstream_pipeline(
            TaskReviewRequest(task_id),
            guarded,
            max_turns=40,
            decision_provider=provider,
        )
        outcome = dict(outcome)
        outcome["decisions"] = list(provider.decisions)
        self.outcomes.append(outcome)
        terminal_status, exit_code = _worker_terminal_contract(str(outcome.get("status")))
        issue_number = self._admission_issue_number(options)
        if issue_number is None:
            snapshot = service.find(task_id)
            issue_number = snapshot.issue_number if snapshot is not None else None
        write_worker_result(
            run_dir=run_dir,
            run_id=options["--run-id"],
            worker_id=worker_id,
            task_id=task_id,
            source_head=options["--admission-source-head"],
            task_contract_sha256=options["--task-contract-sha256"],
            terminal_status=terminal_status,
            outcome_authority=str(outcome.get("authority") or "task_review_pipeline_terminal_result"),
            issue_number=issue_number,
            exit_code=exit_code,
            pid=pid,
        )
        return exit_code


class PumpRecorder:
    def __init__(self, pump: Any) -> None:
        self.pump = pump
        self.calls = 0
        self.results: list[Any] = []

    def __call__(self, snapshot: Any) -> Any:
        self.calls += 1
        result = self.pump(snapshot)
        self.results.append(result)
        return result


# --------------------------------------------------------------------------------
# Composition root mirroring run_autonomous_graph.main
# --------------------------------------------------------------------------------


def build_run(
    fixture: Fixture,
    *,
    forge_result_source_head: bool = False,
    requested_tier: str | None = None,
) -> SimpleNamespace:
    paths = autonomous_run_paths(
        checkout_root=fixture.checkout_root, github_repository=REPOSITORY, run_id=RUN_ID
    )
    manifest = JsonManifestStore(paths.manifest).create_or_load(
        AutonomousRunManifest(
            schema_version=AUTONOMOUS_GRAPH_RUN_SCHEMA_VERSION,
            run_id=RUN_ID,
            source_repository=str(fixture.source),
            github_repository=REPOSITORY,
            runtime_configuration=AutonomousRuntimeConfiguration(
                execution_provider="codex",
                execution_model=None,
                execution_max_turns=120,
                architect_provider="codex",
                architect_model=None,
                architect_max_turns=24,
                architect_min_confidence=0.7,
                architect_max_invocations_per_poll=3,
                architect_min_reanalysis_seconds=300.0,
                max_consecutive_observation_failures=3,
                fatal_drain_seconds=1800.0,
                fallback_seconds=300.0,
                synthetic_evidence_enabled=True,
            ),
            initial_source_commit=fixture.initial_head,
            initial_source_tree=fixture.initial_tree,
            target_task_ids=(fixture.scenario.task_id,),
            excluded_task_ids=(),
            max_capacity=1,
        )
    )
    github = DisposableGitHub(fixture)
    command_runner = make_command_runner(github)
    workers = InProcessWorkers(
        fixture, command_runner, forge_result_source_head=forge_result_source_head
    )
    architect = DeterministicArchitect(fixture, requested_tier=requested_tier)
    events = io.StringIO()
    orchestrator = PollingOrchestrator(
        source=fixture.source,
        checkout_root=fixture.checkout_root,
        scheduler_id=SCHEDULER_ID,
        execution_provider="codex",
        routing_policy=load_execution_routing_policy({}, default_provider_override="codex"),
        model=None,
        max_turns=120,
        max_workers=manifest.max_capacity,
        architect_min_confidence=0.7,
        architect_runner=architect,
        max_architect_invocations_per_poll=3,
        architect_min_reanalysis_seconds=300.0,
        max_consecutive_observation_failures=3,
        fatal_drain_seconds=1800.0,
        plan_builder=lambda *, source, worker_id, excluded_task_ids: build_poll_dispatch_plan(
            source=source,
            worker_id=worker_id,
            excluded_task_ids=excluded_task_ids,
            backend=fixture.backend,
        ),
        reservation_observer=lambda: observe_durable_integration_reservations(
            source=fixture.source,
            checkout_root=fixture.checkout_root,
            worker_id=SCHEDULER_ID,
            backend=fixture.backend,
            task_loader=lambda task_id: load_committed_task(fixture.source, task_id),
        ),
        process_factory=workers,
        event_emitter=JsonEventEmitter(events, journal_path=paths.events),
        excluded_task_ids=manifest.excluded_task_ids,
    )

    def refuse_wait(poll_seconds: float) -> str:
        raise AssertionError(
            "the autonomous controller fell back to waiting; the deterministic run must "
            "progress every cycle without sleeping or polling"
        )

    orchestrator._wait_for_architect_activity = refuse_wait  # type: ignore[method-assign]
    snapshotter = ProductionCoherentSnapshotter(
        manifest=manifest,
        scheduler=orchestrator,
        checkout_root=fixture.checkout_root,
        worker_id=SCHEDULER_ID,
        backend_factory=lambda root: fixture.backend,
    )
    pump = PumpRecorder(
        run_autonomous_graph._SyntheticEvidencePump(
            manifest=manifest,
            source=fixture.source,
            checkout_root=fixture.checkout_root,
            repository=REPOSITORY,
        )
    )
    lock = SchedulerLock(
        scheduler_lock_path(checkout_root=fixture.checkout_root, source=fixture.source)
    )
    controller = AutonomousGraphController(
        manifest=manifest,
        scheduler=orchestrator,
        scheduler_lock=lock,
        snapshotter=snapshotter,
        progress_store=JsonProgressStore(paths.progress),
        receipt_store=JsonReceiptStore(paths.receipt),
        synthetic_evidence_pump=pump,
        synthetic_excluded_task_ids=(PRESERVED_TASK_ID,),
        fallback_seconds=300.0,
    )
    return SimpleNamespace(
        fixture=fixture,
        paths=paths,
        manifest=manifest,
        github=github,
        workers=workers,
        architect=architect,
        events=events,
        orchestrator=orchestrator,
        snapshotter=snapshotter,
        pump=pump,
        lock=lock,
        controller=controller,
    )


def scheduler_events(run: SimpleNamespace, name: str | None = None) -> list[dict[str, Any]]:
    events = [json.loads(line) for line in run.events.getvalue().splitlines() if line.strip()]
    return events if name is None else [item for item in events if item["event"] == name]


def issue_events(fixture: Fixture, event_type: WorkflowEventType) -> list[Any]:
    return [event for event in fixture.issue().events if event.event_type is event_type]


def assert_completion_receipt(run: SimpleNamespace, result: Any) -> None:
    stored = JsonReceiptStore(run.paths.receipt).load()
    require(stored is not None, "graph-complete.json was not written")
    require(result.receipt is not None, "the controller reported completion without a receipt")
    require(stored == result.receipt, "graph-complete.json differs from the returned receipt")
    require(stored.manifest_sha256 == run.manifest.sha256, "receipt is bound to another manifest")
    require(
        stored.relevant_task_ids == (run.fixture.scenario.task_id,),
        f"receipt scope {stored.relevant_task_ids}",
    )
    counters = dict(stored.lifetime_counters)
    for field in ("poll_cycles_total", "architect_invocations_total", "worker_launches_total"):
        require(counters[field] == getattr(result.progress, field), f"receipt counter {field}")


@contextmanager
def acceptance_environment(fixture: Fixture):
    with ExitStack() as stack:
        audit = stack.enter_context(ExecutableAudit())
        stack.enter_context(patch.object(
            time, "sleep", side_effect=AssertionError("acceptance lifecycle must not sleep")
        ))
        stack.enter_context(forbid_real_github_backends())
        approver_calls = stack.enter_context(deterministic_synthetic_approver(fixture))
        yield audit, approver_calls


# --------------------------------------------------------------------------------
# The acceptance test
# --------------------------------------------------------------------------------


def assert_rigor_policy(route: Mapping[str, Any], scenario: Scenario) -> None:
    """The exact policy outcome one scenario requires, as the scheduler recorded it.

    ``route`` is the rigor portion of a ``worker_launched`` event (or of
    ``TaskRigorDecision.to_event_dict``): the architect's requested tier, the
    deterministic minimum, the effective tier, and the crew/validation/human
    policies that tier selects.
    """

    require(
        route["architect_capability_tier"] == scenario.architect_tier,
        f"architect tier {route['architect_capability_tier']!r} != {scenario.architect_tier!r}",
    )
    require(
        route["minimum_capability_tier"] == scenario.expected_tier,
        f"deterministic minimum tier {route['minimum_capability_tier']!r}",
    )
    require(
        route["capability_tier"] == scenario.expected_tier,
        f"effective tier {route['capability_tier']!r} != {scenario.expected_tier!r}",
    )
    require(route["crew_profile"] == scenario.crew_profile, f"crew profile {route['crew_profile']!r}")
    require(
        route["validation_profile"] == scenario.validation_profile,
        f"validation profile {route['validation_profile']!r}",
    )
    require(route["human_verification_policy"] == "required", "human verification policy")
    require(route["architect_recommendation_honored"] is True, "architect was overruled")
    require(route["rigor_override_reasons"] == [], f"overrides {route['rigor_override_reasons']}")
    require(
        RIGOR_PROFILE_BY_TIER[scenario.expected_tier]
        == (scenario.crew_profile, scenario.validation_profile),
        f"production rigor table maps {scenario.expected_tier} to "
        f"{RIGOR_PROFILE_BY_TIER[scenario.expected_tier]}, not the pinned "
        f"({scenario.crew_profile}, {scenario.validation_profile})",
    )
    require(
        CREW_PROFILE_ROLES[scenario.crew_profile] == scenario.required_roles,
        f"{scenario.name} crew roles {CREW_PROFILE_ROLES[scenario.crew_profile]}",
    )
    require(
        CREW_VALIDATION_PROFILE_PAIRS[scenario.crew_profile] == scenario.validation_profile,
        "ExecutionCrew crew/validation pairing changed",
    )


def run_positive_scenario(
    scenario: Scenario, *, requested_tier: str | None = None
) -> dict[str, Any]:
    """Drive one scenario through the whole lifecycle and prove every boundary.

    ``requested_tier`` is a deliberate mutation hook for out-of-tree demonstration
    only: the committed tests always pass ``None`` so the architect asks for the
    scenario's own tier, and any other value is refused by ``assert_rigor_policy``
    (the fast/standard mismatch surfaces as "architect tier ... != ..."), which is
    what proves that assertion is load-bearing.
    """

    task_id = scenario.task_id
    started = time.perf_counter()
    with disposable_fixture(scenario) as fixture, acceptance_environment(fixture) as (
        audit,
        approver_calls,
    ):
        run = build_run(fixture, requested_tier=requested_tier)
        result = run.controller.run()
        elapsed = time.perf_counter() - started
        require(
            not run.workers.failures,
            "fixture workers failed:\n" + "\n".join(run.workers.failures),
        )
        require(
            result.evaluation.classification == "complete",
            f"run ended {result.evaluation.classification}: {result.evaluation.reasons}",
        )

        launched = scheduler_events(run, "worker_launched")
        issue = fixture.issue()
        assert issue.state is not None
        progress = result.progress

        # (1) The explicit target entered the controller and nothing else did.
        require(run.manifest.target_task_ids == (task_id,), "manifest target differs")
        require(result.evaluation.relevant_task_ids == (task_id,), "run scope differs")
        first_architect = scheduler_events(run, "architect_started")[0]
        require(
            first_architect["eligible_pairs"]
            == [{"task_id": task_id, "work_types": ["implementation"]}],
            f"first architect portfolio was {first_architect['eligible_pairs']}",
        )

        # (2) The architect classified the task at the scenario's tier and deterministic
        # routing resolved exactly the scenario's crew/validation profiles with human
        # verification still required.
        implementation_launch = launched[0]
        require(implementation_launch["task_id"] == task_id, "wrong task launched")
        require(implementation_launch["work_type"] == "implementation", "wrong work type")
        assert_rigor_policy(implementation_launch, scenario)
        durable_launches = [
            item for item in (
                json.loads(line) for line in run.paths.events.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            if item["event"] == "worker_launched"
        ]
        require(durable_launches == launched, "durable routing journal differs from emitted routes")
        for route in durable_launches:
            assert_rigor_policy(route, scenario)
        require(run.architect.calls[0]["admitted"] == [task_id], "architect admitted wrongly")
        require(
            all(call["admission_limit"] == 1 for call in run.architect.calls),
            "capacity offered to the architect was not exactly one worker",
        )

        # (3) Exactly one worker was admitted for the implementation, never more than one
        # worker was alive, and every launch carried the exact worker argv.
        implementation_launches = [
            item for item in run.workers.launches if item["phase"] == "implementation"
        ]
        require(
            len(implementation_launches) == 1,
            f"{len(implementation_launches)} implementation workers",
        )
        require(
            all(item["active_worker_count"] <= 1 for item in scheduler_events(run, "poll_started")),
            "more than one worker was active",
        )
        for launch in run.workers.launches:
            options = launch["options"]
            require(
                options["--task-id"] == task_id and options["--execution-provider"] == "codex",
                "worker argv",
            )
            require(
                options["--crew-profile"] == scenario.crew_profile
                and options["--validation-profile"] == scenario.validation_profile,
                f"worker argv rigor {options['--crew-profile']}/{options['--validation-profile']}",
            )

        # (4) The worker produced an identity-bound successful result the scheduler
        # authenticated (run id, worker id, task, source head, contract hash, pid, exit code).
        finished = scheduler_events(run, "worker_finished")
        require(
            finished[0]["terminal_status"] == "human_action_required", f"first return {finished[0]}"
        )
        require(finished[0]["run_id"] == implementation_launch["run_id"], "run identity")
        recorded = read_json(Path(implementation_launch["result_artifact_path"]))
        require(recorded["source_head"] == fixture.initial_head, "result source head")
        require(
            recorded["task_contract_sha256"] == fixture.task["task_contract_sha256"],
            "result contract",
        )
        require(recorded["pid"] == implementation_launches[0]["pid"], "result pid")
        require(not scheduler_events(run, "worker_failed"), "a worker result was rejected")

        # (5) The task reached the committed/pushed handoff boundary.
        handoffs = issue_events(fixture, WorkflowEventType.HUMAN_HANDOFF_CREATED)
        require(len(handoffs) == 1, f"{len(handoffs)} handoffs")
        validations = issue_events(fixture, WorkflowEventType.AUTOMATED_VALIDATION_PASSED)
        require(len(validations) == 1, f"{len(validations)} automated validations")
        handoff_commit = validations[0].details["commit"]
        branch = validations[0].details["branch"]
        require(handoff_commit == issue.state.human_handoff_commit, "handoff commit identity")
        git(
            fixture.remote,
            "merge-base",
            "--is-ancestor",
            handoff_commit,
            fixture.remote_head("refs/heads/main"),
        )
        for path in scenario.exact_paths:
            require(
                git(fixture.remote, "ls-tree", "--name-only", handoff_commit, "--", path) == path,
                f"handoff commit does not carry {path}",
            )
        handoff_paths = tuple(
            sorted(
                git(
                    fixture.remote, "diff", "--name-only", fixture.initial_head, handoff_commit, "--"
                ).splitlines()
            )
        )
        require(
            handoff_paths == tuple(sorted(scenario.exact_paths)),
            f"handoff commit touched {handoff_paths}, not exactly the scenario surface",
        )
        if scenario.scene_path:
            scene = git(fixture.remote, "show", f"{handoff_commit}:{scenario.scene_path}")
            for record in (
                "--- !u!1 &1000\nGameObject:", "m_Name: MuffcabbageMarker",
                "component: {fileID: 1001}", "--- !u!4 &1001\nTransform:",
                "m_GameObject: {fileID: 1000}",
                f"m_LocalPosition: {{x: {scenario.number}, y: 0, z: 0}}",
                "m_Roots:\n  - {fileID: 1001}",
            ):
                require(record in scene, f"committed scene omitted substantive marker data: {record}")
            require(
                f"guid: {_guid(scenario.scene_path)}" in git(
                    fixture.remote, "show", f"{handoff_commit}:{scenario.scene_path}.meta"
                ), "scene companion identity changed",
            )
        require(
            bool(git(fixture.remote, "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}")),
            "task branch",
        )

        # (6) The private synthetic-evidence boundary advanced without any human result.
        require(run.pump.calls == progress.synthetic_pump_calls_total, "pump accounting")
        pump_results = [item for item in run.pump.results if item is not None]
        require(len(pump_results) == 1, f"{len(pump_results)} synthetic mutations")
        require(pump_results[0].event_id == validations[0].event_id, "pump event identity")
        require(
            pump_results[0].evidence_sha256 == semantic_sha256(validations[0].details),
            "pump evidence identity",
        )
        require(issue.state.human_result is None, "a human result was recorded")
        require(
            not issue_events(fixture, WorkflowEventType.HUMAN_VALIDATION_PASSED)
            and not issue_events(fixture, WorkflowEventType.HUMAN_VALIDATION_FAILED),
            "a human validation event was recorded",
        )
        for comments in fixture.memory.comments.values():
            for comment in comments:
                require(
                    parse_human_validation_result(str(comment.get("body") or "")) is None,
                    "a comment carries a human validation result",
                )
        require(
            all(event.details.get("human_result") is None for event in issue.events),
            "an event carried human_result",
        )
        require(approver_calls["rehearsal_checks"] >= 2, "approver preflight did not run twice")
        require(
            not fixture.memory.comments[fixture.inbox_number],
            "the Vincent inbox notification was not cleared after automated evidence",
        )

        # (7) The same run resumed the task and completed downstream delivery: one
        # downstream worker carried delivery evidence, the PR, the merge (after the
        # emulated checks reported success), and Issue completion.
        phases = [item["phase"] for item in run.workers.launches]
        require(phases == ["implementation", "delivery_evidence"], f"phases {phases}")
        exit_codes = [item["exit_code"] for item in run.workers.launches]
        require(exit_codes == [0, 0], f"exit codes {exit_codes}")
        (downstream,) = run.workers.outcomes
        require(downstream["status"] == "complete", f"downstream outcome {downstream['status']}")
        require(
            downstream["decisions"]
            == [
                "acquire_agent_lease",
                "run_authoritative_unity_test",
                "create_delivery_review_draft",
                "delivery_review_facts",
                "create_delivery_review_proposal",
                "publish_delivery_review",
                "acquire_agent_lease",
                "finalize_delivery_evidence_and_open_pr",
                "acquire_agent_lease",
                "inspect_or_merge_pull_request",
                "verify_post_merge_and_complete",
            ],
            f"downstream decisions {downstream['decisions']}",
        )
        require(
            [item[2] for item in run.github.commands]
            == ["list", "create", "view", "view", "view", "merge", "view", "close"],
            f"gh command sequence {[item[1:3] for item in run.github.commands]}",
        )
        for launch in run.workers.launches[1:]:
            require(
                int(launch["options"]["--admission-issue-number"]) == issue.issue_number,
                "resume admission was not bound to the managed Issue",
            )

        # (8) Merge and completion are proven in the disposable Git remote.
        require(len(run.github.pull_requests) == 1, "more than one pull request")
        pull_request = run.github.pull_requests[1]
        require(pull_request["state"] == "MERGED", "pull request not merged")
        main_head = fixture.remote_head("refs/heads/main")
        require(main_head == pull_request["merge_commit"], "remote main is not the merge commit")
        parents = git(fixture.remote, "rev-list", "--parents", "-n", "1", main_head).split()[1:]
        require(
            len(parents) == 2 and pull_request["merged_head"] in parents, "history not preserved"
        )
        require(fixture.initial_head in parents, "merge did not join the initial main")
        require(
            bool(
                git(
                    fixture.remote,
                    "ls-tree",
                    "--name-only",
                    main_head,
                    "--",
                    f"Pipeline/TaskGraph/deliveries/{task_id}.json",
                )
            ),
            "delivery record is not on main",
        )
        require(git(fixture.source, "rev-parse", "HEAD") == main_head, "controller main not synced")
        require(issue.state.state is WorkflowState.COMPLETE, f"issue {issue.state.state}")
        require(fixture.memory.issues[issue.issue_number]["state"] == "CLOSED", "issue not closed")
        completion = issue_events(fixture, WorkflowEventType.COMPLETED)
        require(
            len(completion) == 1 and completion[0].details["merged_commit"] == main_head,
            "completion event",
        )

        # (9) graph-complete.json is valid and authoritative.
        assert_completion_receipt(run, result)
        require(result.receipt.source_commit == main_head, "receipt source commit")
        replay = build_run(fixture)
        replayed = replay.controller.run()
        require(replayed.cycle_status == "already_complete", "receipt did not short-circuit a rerun")
        require(replay.workers.launches == [] and replay.architect.calls == [], "rerun did work")

        # (10) No active lease/claim/assignment, checkout mutation, or incomplete state remains.
        require(run.orchestrator.active_assignments == {}, "active assignments remain")
        final = run.snapshotter()
        require(final.active_assignment_task_ids == (), "active assignment observed")
        require(final.pending_transition_task_ids == (), "pending transition observed")
        require(final.reservation_task_ids == (), "reservation observed")
        require(final.source_clean and final.source_head == final.origin_main_head, "source state")
        checkout = fixture.checkout_root / task_id
        require(
            git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "checkout dirty",
        )
        probe = SchedulerLock(run.lock.path)
        probe.acquire()
        probe.release()
        require(
            not issue_events(fixture, WorkflowEventType.BLOCKED), "a blocked event was recorded"
        )

        # Exact counts.
        require(
            progress.architect_invocations_total == 2 == len(run.architect.calls),
            f"architect {progress.architect_invocations_total}",
        )
        require(
            progress.worker_launches_total == 2 == len(run.workers.launches),
            f"launches {progress.worker_launches_total}",
        )
        require(progress.poll_cycles_total == 4, f"poll cycles {progress.poll_cycles_total}")
        require(
            progress.synthetic_pump_calls_total == 5,
            f"pump calls {progress.synthetic_pump_calls_total}",
        )
        require(progress.fallback_waits_total == 0 and progress.wakeups_total == 0, "the run waited")
        require(not scheduler_events(run, "architect_wait_started"), "an architect wait started")
        executions = fixture.runner_executions()
        require(len(executions) == 1, f"Unity runner executions: {executions}")
        require(
            executions[0] == f"EditMode\t{scenario.test_filter}\t{handoff_commit}", executions[0]
        )
        require(
            audit.count("powershell.exe") == 1, f"powershell launches {audit.count('powershell.exe')}"
        )
        require(len(run.workers.validation_commands) == 1, "production validation ran again")
        require(len(run.workers.crew_commands) == 1, "hidden second crew invocation")
        (bridge,) = run.workers.execution_bridges
        execution = bridge.require(implementation_launch["run_id"])
        reloaded = ExecutionCrewBridge(
            checkout=bridge.checkout, scope=bridge.scope,
            crew_profile=scenario.crew_profile, validation_profile=scenario.validation_profile,
            execution_model=bridge.execution_model,
            execution_reasoning_effort=bridge.execution_reasoning_effort,
        )
        require(reloaded.require(execution.run_id) == execution, "execution receipt did not reload")
        require(
            execution.crew_profile == scenario.crew_profile
            and execution.validation_profile == scenario.validation_profile,
            "execution receipt lost the routed rigor pair",
        )
        require(
            read_json(Path(execution.result_path))["required_roles"] == list(scenario.required_roles),
            "persisted fixture crew result lost the selected role contract",
        )
        unexpected = audit.executables() - ALLOWED_EXECUTABLES
        require(not unexpected, f"forbidden executables were started: {sorted(unexpected)}")
        # Provider sessions: zero started, zero resumed. The routed argv asked for
        # Codex, and nothing but Git, Python, and PowerShell ever ran.
        require(
            all("--enable-execution-session-pool" not in item["argv"] for item in run.workers.launches),
            "Codex route unexpectedly requested a Claude session pool",
        )
        receipt_file = load_integration_receipt(
            fixture.checkout_root / ".task-review-agent" / f"{task_id}.integration.json"
        )
        assert receipt_file is not None
        recorded_validation = receipt_file.pre_handoff_validations[0]
        reused = validations[0].details["unity_validations"][0]
        for key in ("manifest_sha256", "xml_sha256", "log_sha256"):
            require(reused[key] == recorded_validation[key], f"automated evidence did not reuse {key}")
        downstream_state = read_json(
            fixture.checkout_root / ".task-review-agent" / f"{task_id}.downstream.json"
        )
        require(
            downstream_state["validation_manifests"][0]["sha256"]
            == recorded_validation["manifest_sha256"],
            "downstream authoritative validation did not reuse the exact manifest",
        )
        processes = {name: audit.count(name) for name in sorted(audit.executables())}
        print(
            f"muffcabbage acceptance [{scenario.name}]: {elapsed:.1f}s, "
            f"tier={implementation_launch['capability_tier']}, "
            f"crew={implementation_launch['crew_profile']}, "
            f"validation={implementation_launch['validation_profile']}, "
            f"roles={list(scenario.required_roles)}, "
            f"polls={progress.poll_cycles_total}, "
            f"architect={progress.architect_invocations_total}, "
            f"workers={progress.worker_launches_total}, "
            f"pump_calls={progress.synthetic_pump_calls_total}, "
            f"runner_executions={len(executions)}, "
            f"worker_seconds={[round(item['seconds'], 1) for item in run.workers.launches]}, "
            f"processes={processes}"
        )
        require(elapsed < RUNTIME_BUDGET_SECONDS, f"run took {elapsed:.1f}s")

        # Post-hoc negative demonstrations on the completed run: the receipt check is
        # load-bearing and a tampered receipt is refused by production.
        receipt_path = run.paths.receipt
        original = receipt_path.read_bytes()
        tampered = json.loads(original)
        tampered["lifetime_counters"]["worker_launches_total"] = 0
        receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
        rejects(
            JsonReceiptStore(receipt_path).load,
            AutonomousGraphRunError,
            containing="receipt identity is invalid",
        )
        receipt_path.unlink()
        rejects(lambda: assert_completion_receipt(run, result), AssertionError, containing="not written")
        receipt_path.write_bytes(original)
        return {
            "scenario": scenario.name,
            "elapsed_seconds": elapsed,
            "architect_capability_tier": implementation_launch["architect_capability_tier"],
            "minimum_capability_tier": implementation_launch["minimum_capability_tier"],
            "capability_tier": implementation_launch["capability_tier"],
            "crew_profile": implementation_launch["crew_profile"],
            "validation_profile": implementation_launch["validation_profile"],
            "required_roles": list(scenario.required_roles),
            "worker_argv_crew_profile": run.workers.launches[0]["options"]["--crew-profile"],
            "worker_argv_validation_profile": (
                run.workers.launches[0]["options"]["--validation-profile"]
            ),
            "processes": processes,
            "runner_executions": len(executions),
        }


def test_single_muffcabbage_task_reaches_verified_completion() -> None:
    run_positive_scenario(FAST)


def test_standard_rigor_muffcabbage_task_reaches_verified_completion() -> None:
    report = run_positive_scenario(STANDARD)
    require(report["capability_tier"] == "standard", report["capability_tier"])
    require(report["crew_profile"] == "standard", report["crew_profile"])
    require(report["validation_profile"] == "task_specific", report["validation_profile"])
    require(
        report["worker_argv_crew_profile"] == "standard"
        and report["worker_argv_validation_profile"] == "task_specific",
        "worker argv did not preserve the standard rigor pair",
    )
    # The fixture worker does not run ExecutionCrew, so this pins the committed crew
    # contract that the worker argv's --crew-profile selects in run_crew.py (and that
    # ProductionTaskController/ExecutionCrewBridge forward unchanged): the standard
    # crew is Implementer, Test Author, and Validator, with no Contract Locality
    # Auditor, and run_crew accepts it only paired with task_specific validation.
    roles = CREW_PROFILE_ROLES[report["worker_argv_crew_profile"]]
    require(roles == ("implementer", "test_author", "validator"), f"standard crew roles {roles}")
    require("contract_locality_auditor" not in roles, "standard crew must not audit locality")
    require(
        CREW_VALIDATION_PROFILE_PAIRS[report["worker_argv_crew_profile"]]
        == report["worker_argv_validation_profile"],
        "ExecutionCrew would refuse this crew/validation pair",
    )


def test_deep_rigor_muffcabbage_task_reaches_verified_completion() -> None:
    run_positive_scenario(DEEP)


def test_deep_serialized_surface_floor_and_load_bearing_guards() -> None:
    """The scene is the only deep trigger; a high architect request cannot hide its loss."""
    require(len(DEEP.exact_paths) == 4, "deep fixture must stay within the four-path lean bound")
    require(DEEP.scene_path == "Assets/Scenes/MuffcabbageGauntlet951.unity", "exact scene path")
    require(DEEP.contract()["execution_scope"] == "single_agent", "fixture must be single-agent")
    require(DEEP.contract()["decomposition_state"] == "concrete", "fixture must be concrete")

    def resolve(scenario: Scenario, tier: str, *, declare_import_companion: bool = False):
        task = scenario.contract()
        task["task_contract_sha256"] = "0" * 64
        advisory = scenario_advisory(scenario, task, "1" * 40, requested_tier=tier)
        surface = advisory.predicted_change_surface
        if declare_import_companion:
            surface = replace(surface, unity_serialized_assets=(scenario.file_pairs[0][1],))
        return resolve_task_rigor(
            advisory.execution_recommendation, task=task, predicted_change_surface=surface,
            committed_path_probe=lambda path: False,
        )

    for tier in ("fast", "standard", "deep"):
        decision = resolve(DEEP, tier)
        require(decision.architect_capability_tier == tier, str(decision))
        require(decision.minimum_capability_tier == "deep", str(decision))
        require(decision.effective_capability_tier == "deep", str(decision))
        require(decision.crew_profile == "full", str(decision))
        require(decision.validation_profile == "full_relevant", str(decision))
        require(decision.human_verification_policy == "required", str(decision))
        require(
            f"serialized or project-wide asset surface: {DEEP.scene_path}" in decision.reasons,
            f"scene path did not drive the floor: {decision.reasons}",
        )
        require(decision.architect_recommendation_honored == (tier == "deep"), str(decision))
        if tier != "deep":
            require(
                f"deterministic policy raised architect tier {tier} to deep" in decision.override_reasons,
                str(decision.override_reasons),
            )
        else:
            assert_rigor_policy(decision.to_event_dict(), DEEP)

    # Remove the scene AND its companion from contract/resources/prediction together.
    # Keep the deep request: effective deep alone would conceal a missing risk surface.
    without_scene = replace(DEEP, scene_path=None)
    removed = resolve(without_scene, "deep")
    require(removed.minimum_capability_tier == "fast", str(removed))
    require(removed.effective_capability_tier == "deep", str(removed))
    rejects(
        lambda: assert_rigor_policy(removed.to_event_dict(), DEEP), AssertionError,
        containing="deterministic minimum tier 'fast'",
    )
    # A new .cs.meta import companion with its script is not substantive content.
    # An orphan .meta is deliberately NOT exempt under production policy.
    companion = resolve(without_scene, "fast", declare_import_companion=True)
    require(companion.minimum_capability_tier == "fast", str(companion))
    require(companion.effective_capability_tier == "fast", str(companion))
    require(companion.crew_profile == "lean" and companion.validation_profile == "targeted", str(companion))

    wrongly_routed = resolve(DEEP, "deep").to_event_dict()
    wrongly_routed.update(capability_tier="standard", crew_profile="standard", validation_profile="task_specific")
    rejects(
        lambda: assert_rigor_policy(wrongly_routed, DEEP), AssertionError,
        containing="effective tier 'standard' != 'deep'",
    )
    print("deep load-bearing guards: removed scene -> minimum fast rejected; standard route rejected")


def test_policy_raises_a_fast_request_for_the_standard_surface_to_standard() -> None:
    """Guard: the same six-path surface never runs lean because an architect said fast."""

    task = STANDARD.contract()
    task["task_contract_sha256"] = "0" * 64
    require(len(STANDARD.exact_paths) == 6, str(STANDARD.exact_paths))
    require(
        all(path.startswith("Assets/") and path.endswith((".cs", ".cs.meta")) for path in STANDARD.exact_paths),
        "the standard surface must stay isolated C# files and companions",
    )

    def resolve(requested_tier: str):
        advisory = scenario_advisory(STANDARD, task, "1" * 40, requested_tier=requested_tier)
        return resolve_task_rigor(
            advisory.execution_recommendation,
            task=task,
            predicted_change_surface=advisory.predicted_change_surface,
            # Nothing in the surface is committed yet: every companion is new.
            committed_path_probe=lambda path: False,
        )

    # The complete deterministic narrative for this surface: the three symbols stay
    # confined, the three new sidecars are recognized as import companions, and the
    # lean bound is the one and only floor that fires. No full-profile rule (shared
    # system, logical resource, serialized asset, protected root) appears, so a scene
    # rebuild or protected surface is not what makes this task standard.
    companions = ", ".join(sorted(meta for _, meta in STANDARD.file_pairs))
    surface_reasons = (
        "named symbols or components are confined to the small exact path surface",
        "deterministic new C# script import companions are not substantive serialized "
        f"content: {companions}",
        "more than four exact paths exceed the lean-change bound",
    )

    raised = resolve("fast")
    require(raised.architect_capability_tier == "fast", str(raised))
    require(raised.minimum_capability_tier == "standard", str(raised))
    require(raised.effective_capability_tier == "standard", str(raised))
    require(raised.crew_profile == "standard", str(raised))
    require(raised.validation_profile == "task_specific", str(raised))
    require(raised.human_verification_policy == "required", str(raised))
    require(not raised.architect_recommendation_honored, "fast was honored for six paths")
    require(
        raised.reasons
        == (*surface_reasons, "deterministic policy raised architect tier fast to standard"),
        f"reasons {raised.reasons}",
    )
    require(
        raised.override_reasons
        == (
            "more than four exact paths exceed the lean-change bound",
            "deterministic policy raised architect tier fast to standard",
        ),
        f"override reasons {raised.override_reasons}",
    )
    # The scenario's own policy assertion refuses that mutated outcome exactly where
    # the honest run would report it.
    rejects(
        lambda: assert_rigor_policy(raised.to_event_dict(), STANDARD),
        AssertionError,
        containing="architect tier",
    )

    honest = resolve("standard")
    require(honest.architect_recommendation_honored, str(honest))
    require(honest.reasons == surface_reasons, f"reasons {honest.reasons}")
    require(honest.override_reasons == (), str(honest))
    assert_rigor_policy(honest.to_event_dict(), STANDARD)
    # And the fast scenario's two-path surface genuinely resolves to fast, so the two
    # scenarios sit on opposite sides of the lean bound.
    fast_task = FAST.contract()
    fast_task["task_contract_sha256"] = "0" * 64
    fast_advisory = scenario_advisory(FAST, fast_task, "1" * 40)
    fast_decision = resolve_task_rigor(
        fast_advisory.execution_recommendation,
        task=fast_task,
        predicted_change_surface=fast_advisory.predicted_change_surface,
        committed_path_probe=lambda path: False,
    )
    assert_rigor_policy(fast_decision.to_event_dict(), FAST)


def test_forged_worker_result_identity_stops_admission() -> None:
    with disposable_fixture() as fixture, acceptance_environment(fixture):
        run = build_run(fixture, forge_result_source_head=True)
        result = run.controller.run()
        require(not run.workers.failures, "\n".join(run.workers.failures))
        require(result.evaluation.classification == "blocked", result.evaluation.classification)
        require(result.scheduler_fatal, "forged identity did not stop the scheduler")
        require(
            "scheduler_fatal:worker_failed" in result.evaluation.reasons,
            f"reasons {result.evaluation.reasons}",
        )
        failed = scheduler_events(run, "worker_failed")
        require(
            len(failed) == 1 and "identity mismatch: source_head" in failed[0]["error"], str(failed)
        )
        issue = fixture.issue()
        assert issue.state is not None
        require(
            issue.state.state is WorkflowState.HUMAN_ACTION_REQUIRED,
            f"forged handoff was advanced to {issue.state.state}",
        )
        require(
            not issue_events(fixture, WorkflowEventType.AUTOMATED_VALIDATION_PASSED),
            "evidence applied",
        )
        require(len(run.workers.launches) == 1, "a second worker was admitted after the forgery")
        require(JsonReceiptStore(run.paths.receipt).load() is None, "a receipt was written")


def test_pre_handoff_boundary_refuses_stale_evidence_human_results_and_hidden_reexecution() -> None:
    with disposable_fixture() as fixture, acceptance_environment(fixture):
        run = build_run(fixture)
        first = run.controller.run(max_steps=1)
        require(not run.workers.failures, "\n".join(run.workers.failures))
        require(first.cycle_status == "worker_launched", first.cycle_status)
        issue = fixture.issue()
        assert issue.state is not None
        require(issue.state.state is WorkflowState.HUMAN_ACTION_REQUIRED, "no handoff")
        state_root = fixture.checkout_root / ".task-review-agent"
        receipt_path = state_root / f"{TASK_ID}.integration.json"
        receipt = load_integration_receipt(receipt_path)
        assert receipt is not None
        manifest_path = state_root / receipt.pre_handoff_validations[0]["manifest_relative_path"]
        xml_path = manifest_path.parent / "test-results.xml"

        def issue_unchanged() -> None:
            current = fixture.issue()
            assert current.state is not None
            require(current.state.state is WorkflowState.HUMAN_ACTION_REQUIRED, "Issue advanced")
            require(
                not issue_events(fixture, WorkflowEventType.AUTOMATED_VALIDATION_PASSED),
                "evidence applied",
            )

        # Stale/hash-mismatched evidence: a tampered artifact is refused, not re-run.
        original_xml = xml_path.read_bytes()
        xml_path.write_bytes(original_xml + b"\n")
        rejects(
            lambda: run.controller.run(max_steps=1),
            approver.SyntheticApprovalError,
            containing="pre-handoff Unity evidence is unusable",
        )
        xml_path.write_bytes(original_xml)
        issue_unchanged()

        # A receipt edited without re-hashing is corruption, never absence.
        original_receipt = receipt_path.read_bytes()
        edited = json.loads(original_receipt)
        edited["pre_handoff_validations"][0]["passed"] = 99
        receipt_path.write_text(
            json.dumps(edited, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        rejects(
            lambda: run.controller.run(max_steps=1),
            approver.SyntheticApprovalError,
            containing="hash does not match",
        )
        receipt_path.write_bytes(original_receipt)
        issue_unchanged()

        # Synthetic evidence that tries to create a human result is refused by the store.
        approver_service = fixture.service(APPROVER_WORKER_ID)
        plan = validation_plan_for(fixture.checkout_root / TASK_ID, fixture.task)
        assert plan is not None
        fact = receipt.pre_handoff_validations[0]
        honest = {
            "schema_version": "1.0",
            "authority": AUTOMATED_VALIDATION_EVIDENCE_AUTHORITY,
            "repository": REPOSITORY,
            "repository_private": True,
            "gauntlet_id": AUTOMATED_VALIDATION_GAUNTLET_ID,
            "task_id": TASK_ID,
            "handoff_event_id": issue.state.last_event_id,
            "branch": issue.state.branch,
            "commit": issue.state.head_commit,
            "tree": receipt.commit_tree,
            "task_contract_sha256": issue.state.task_contract_sha256,
            "validation_policy_authority": plan["authority"],
            "validation_policy_sha256": plan["policy_sha256"],
            "required_validations": [{"test_platform": "EditMode", "test_filter": TEST_FILTER}],
            "unity_validations": [
                {
                    "test_platform": "EditMode",
                    "test_filter": TEST_FILTER,
                    "manifest_sha256": fact["manifest_sha256"],
                    "xml_sha256": fact["xml_sha256"],
                    "log_sha256": fact["log_sha256"],
                    "commit": issue.state.head_commit,
                    "tree": receipt.commit_tree,
                    "post_commit": issue.state.head_commit,
                    "post_tree": receipt.commit_tree,
                    "repository_clean_before": True,
                    "repository_clean_after": True,
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                }
            ],
        }
        rejects(
            lambda: approver_service.apply_automated_validation(
                task_id=TASK_ID,
                evidence={**honest, "human_result": "pass"},
                actor_id=APPROVER_WORKER_ID,
            ),
            IssueWorkflowStoreError,
            containing="automated validation evidence is invalid",
        )
        rejects(
            lambda: approver_service.apply_human_result(
                task_id=TASK_ID,
                result_body=f"Result: PASS\nTested commit: {issue.state.head_commit}\n",
                actor_id=APPROVER_WORKER_ID,
            ),
            IssueWorkflowStoreError,
            containing="authorized human operator",
        )
        issue_unchanged()

        # Hidden re-execution: an adapter that ignores recorded evidence runs Unity
        # again. The acceptance run's "exactly one execution" assertion catches it.
        require(len(fixture.runner_executions()) == 1, "baseline execution count")
        with patch.object(approver, "find_pre_handoff_validation", lambda **values: None):
            pump_result = run.pump(run.snapshotter())
        require(pump_result is not None and pump_result.task_id == TASK_ID, "pump did not act")
        advanced = fixture.issue()
        assert advanced.state is not None
        require(advanced.state.phase is WorkflowPhase.DELIVERY_EVIDENCE, "handoff did not advance")
        executions = fixture.runner_executions()
        require(
            len(executions) == 2,
            f"a hidden second Unity execution must be observable; saw {len(executions)}",
        )


TESTS = (
    test_single_muffcabbage_task_reaches_verified_completion,
    test_standard_rigor_muffcabbage_task_reaches_verified_completion,
    test_deep_rigor_muffcabbage_task_reaches_verified_completion,
    test_deep_serialized_surface_floor_and_load_bearing_guards,
    test_policy_raises_a_fast_request_for_the_standard_surface_to_standard,
    test_forged_worker_result_identity_stops_admission,
    test_pre_handoff_boundary_refuses_stale_evidence_human_results_and_hidden_reexecution,
)


def main(argv: Sequence[str] | None = None) -> int:
    selected = tuple(sys.argv[1:] if argv is None else argv)
    failures = 0
    for test in TESTS:
        if selected and not any(fragment in test.__name__ for fragment in selected):
            continue
        started = time.perf_counter()
        faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - reported per test
            failures += 1
            print(
                f"FAIL {test.__name__} ({time.perf_counter() - started:.1f}s): "
                f"{type(exc).__name__}: {exc}"
            )
            import traceback

            traceback.print_exc()
        else:
            print(f"PASS {test.__name__} ({time.perf_counter() - started:.1f}s)")
        finally:
            faulthandler.cancel_dump_traceback_later()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
