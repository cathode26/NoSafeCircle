#!/usr/bin/env python3
"""Run the minimum production ExecutionCrew for one human-selected task."""
from __future__ import annotations

import argparse, hashlib, json, math, os, re, stat, subprocess, sys, tempfile, threading, time, unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for module_root in (ROOT, ROOT / "Pipeline/TaskGraph"):
    if str(module_root) not in sys.path: sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION, AgentInvocationRequest, Budgets, ContractValidationError, WriteBoundaries, validate_repository_path
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider, ClaudeLiveRenderer
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider
from Pipeline.AgentRuntime.provider_sessions import (
    ProviderSessionBinding,
    ProviderSessionConfirmation,
    ProviderSessionLedger,
)
from Pipeline.ExecutionCrew.session_pool import (
    CREW_SESSION_PROTOCOL_VERSION,
    DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
    POOL_SCHEMA_VERSION,
    AssignmentLease,
    DurableAssignmentResult,
    SessionPoolError,
    assignment_capsule,
    pooled_assignment_evidence,
)
from Pipeline.AgentRuntime.json_values import thaw_json
from Pipeline.TaskExecution.contracts import TASK_EXECUTION_REQUEST_SCHEMA_VERSION, TaskContractIdentity, TaskExecutionRequest
from Pipeline.TaskExecution.task_runner import TaskExecutionRunner
from Pipeline.ExecutionCrew.contract_locality import (
    CONTRACT_LOCALITY_AUDIT_SCHEMA_VERSION,
    ContractLocalityError,
    build_task_catalog,
    direct_dependency_contracts,
    direct_dependent_contracts,
    validate_locality_audit_output,
)
from Pipeline.ExecutionCrew.prompts import contract_locality_auditor_prompt, implementer_prompt, test_author_prompt, validator_prompt
from Pipeline.ExecutionCrew.schemas import (
    CONTRACT_LOCALITY_AUDITOR_OUTPUT_SCHEMA,
    IMPLEMENTER_OUTPUT_SCHEMA,
    TEST_AUTHOR_OUTPUT_SCHEMA,
    VALIDATOR_OUTPUT_SCHEMA,
    VALIDATOR_CONTRACT_REVIEW_REASON_CODES,
    VALIDATOR_NON_PASS_REASON_CODES,
    VALIDATOR_STATUS_REASON_CODES,
    ROLE_OUTPUT_NORMALIZATION,
    SourceIdentity,
)
from work_graph_validate import WorkGraphValidationError, _validate_v2_task
from persistent_work_graph import PersistentWorkGraph, PersistentWorkGraphError, load_persistent_work_graph

TASK_ID_RE = re.compile(r"^NSC-[0-9]{3}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
GDD_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
POLICY_PATH = "Docs/Engineering/UNITY_TESTING_POLICY.md"
ENGINEERING_STANDARDS_PATH = "Docs/Engineering/ENGINEERING_STANDARDS.md"
MAX_REVIEW_FEEDBACK_BYTES = 64 * 1024
MAX_RETRY_CANDIDATE_BYTES = 16 * 1024 * 1024
OPENAI_REASONING_EFFORTS = ("none","minimal","low","medium","high","xhigh","max")

class CrewBlocked(RuntimeError): pass

def validate_host_output_root(value: str) -> PureWindowsPath:
    """Lexically validate a HOST-facing Windows path; never resolved against this (Linux) filesystem."""
    if not isinstance(value, str) or not value.strip():
        raise CrewBlocked("--host-output-root must be a non-empty absolute Windows path")
    candidate = PureWindowsPath(value)
    if not candidate.drive or not candidate.is_absolute():
        raise CrewBlocked("--host-output-root must be an absolute drive-qualified Windows path")
    if ".." in candidate.parts or "." in candidate.parts:
        raise CrewBlocked("--host-output-root must not contain traversal components")
    return candidate

@dataclass(frozen=True)
class RetryContext:
    prior_run_id: str
    prior_source_head: str
    prior_contract_identity: TaskContractIdentity
    task_id: str
    provider: str
    execution_model: str | None
    execution_reasoning_effort: str | None
    implementation_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    new_implementation_paths: tuple[str, ...]
    new_test_paths: tuple[str, ...]
    candidate_bytes: bytes
    candidate_sha256: str
    candidate_paths: tuple[str, ...]
    candidate_sidecars: tuple[str, ...]
    feedback_bytes: bytes
    feedback_text: str
    feedback_sha256: str

@dataclass(frozen=True)
class RolePathPlan:
    existing_paths: tuple[str, ...]
    new_paths: tuple[str, ...]
    pipeline_generated_sidecars: tuple[str, ...]

    @property
    def requested_paths(self) -> tuple[str, ...]:
        return tuple(sorted((*self.existing_paths, *self.new_paths)))

class ProgressReporter:
    """Supplemental, non-authoritative operational telemetry for one crew run."""
    def __init__(self, path: Path, *, run_id: str, task_id: str, provider: str, started: float):
        self.path, self.run_id, self.task_id, self.provider, self.started = path, run_id, task_id, provider, started
        self._lock = threading.Lock()

    def emit(self, event: str, message: str, **fields: Any) -> None:
        record = {"schema_version":"1.0", "timestamp_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "elapsed_seconds":round(time.monotonic()-self.started,3), "event":event, "run_id":self.run_id,
                  "task_id":self.task_id, "provider":self.provider, **fields, "message":message}
        line=json.dumps(record,sort_keys=True,separators=(",",":"))
        with self._lock:
            with self.path.open("a",encoding="utf-8") as stream:
                stream.write(line+"\n"); stream.flush()
            print(f"[{record['timestamp_utc']}] {message}",file=sys.stderr,flush=True)

def heartbeat_interval() -> float:
    raw=os.getenv("NSC_EXECUTION_HEARTBEAT_SECONDS","15")
    try: value=float(raw)
    except ValueError as exc: raise CrewBlocked("NSC_EXECUTION_HEARTBEAT_SECONDS must be a positive finite number") from exc
    if not math.isfinite(value) or value<=0: raise CrewBlocked("NSC_EXECUTION_HEARTBEAT_SECONDS must be a positive finite number")
    return value

def git(root: Path, *args: str, text: bool = True, check: bool = True):
    return subprocess.run(("git", "-C", str(root), *args), check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)

def capture_source(source: Path) -> SourceIdentity:
    try:
        root = Path(git(source, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
        identity = SourceIdentity(str(root), git(root, "rev-parse", "--verify", "HEAD").stdout.strip(),
                                  git(root, "rev-parse", "HEAD^{tree}").stdout.strip(),
                                  git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip())
        if git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout:
            raise CrewBlocked("source working tree must be completely clean, including untracked files")
        return identity
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CrewBlocked("source repository identity could not be resolved") from exc

def _resolve_existing_under(root: Path, candidate: Path, *, field: str) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CrewBlocked(f"{field} does not exist or cannot be resolved") from exc
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise CrewBlocked(f"{field} must resolve strictly underneath the ExecutionCrew output root")
    return resolved

def _json_object(path: Path, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CrewBlocked(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise CrewBlocked(f"{field} must contain a JSON object")
    return value

def _read_regular_bytes(path: Path, *, field: str, max_bytes: int) -> bytes:
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise CrewBlocked(f"{field} must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            data = stream.read(max_bytes + 1)
    except OSError as exc:
        raise CrewBlocked(f"{field} could not be safely read as a regular file") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(data) > max_bytes:
        raise CrewBlocked(f"{field} must be at most {max_bytes} bytes")
    return data

def _requested_paths(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise CrewBlocked(f"prior {field} must be a non-empty path array")
    try:
        return WriteBoundaries(tuple(value), ()).allowed_paths
    except ValueError as exc:
        raise CrewBlocked(f"prior {field} is invalid: {exc}") from exc

def _legacy_requested_scope(prior_dir: Path, *, task_id: str, provider: str,
                            contract_identity: TaskContractIdentity) -> tuple[tuple[str, ...], tuple[str, ...]]:
    task_execution = _resolve_existing_under(
        prior_dir, prior_dir / "task_execution", field="prior task_execution directory"
    )
    if not task_execution.is_dir():
        raise CrewBlocked("prior task_execution artifact must be a directory")
    expected_configuration_key = {"claude":"claude-crew", "codex":"codex-crew"}[provider]
    by_role: dict[str, list[WriteBoundaries]] = {"implementer":[], "test_author":[]}
    read_only_role_counts = {"validator": 0, "contract_locality_auditor": 0}
    request_paths = sorted(task_execution.glob("*/task_request.json"))
    if not request_paths:
        raise CrewBlocked("prior TaskExecution request artifacts are missing")
    for request_path in request_paths:
        resolved = _resolve_existing_under(prior_dir, request_path, field="prior task_request.json")
        if not stat.S_ISREG(resolved.stat().st_mode):
            raise CrewBlocked("prior task_request.json must be a regular file")
        raw = _json_object(resolved, field="prior task_request.json")
        try:
            request = TaskExecutionRequest.from_dict(raw)
        except ValueError as exc:
            raise CrewBlocked(f"prior TaskExecution request is invalid: {exc}") from exc
        invocation = request.invocation
        if request.task_id != task_id:
            raise CrewBlocked("prior TaskExecution task ID does not match crew_result.json")
        if request.task_contract_identity != contract_identity:
            raise CrewBlocked("prior TaskExecution contract identity does not match crew_result.json")
        if invocation.provider_configuration_key != expected_configuration_key:
            raise CrewBlocked("prior TaskExecution provider does not match crew_result.json")
        if invocation.role in by_role:
            by_role[invocation.role].append(invocation.write_boundaries)
        elif invocation.role not in read_only_role_counts:
            raise CrewBlocked(f"unexpected prior TaskExecution role: {invocation.role}")
        elif invocation.write_boundaries.allowed_paths or invocation.write_boundaries.denied_paths:
            raise CrewBlocked(f"prior {invocation.role} unexpectedly had write authority")
        else:
            read_only_role_counts[invocation.role] += 1
    if not read_only_role_counts["validator"]:
        raise CrewBlocked("prior Validator TaskExecution request artifact is missing")
    # A prior Contract Locality Auditor is optional: this feature postdates many historical
    # review_ready runs. When absent, do not reject the retry; when present, the write-authority
    # check above already proved it had empty WriteBoundaries.
    recovered: dict[str, tuple[str, ...]] = {}
    for role, boundaries in by_role.items():
        if not boundaries:
            raise CrewBlocked(f"prior {role} TaskExecution request artifact is missing")
        variants = {item.allowed_paths for item in boundaries}
        if len(variants) != 1:
            raise CrewBlocked(f"prior {role} WriteBoundaries are inconsistent across attempts")
        recovered[role] = next(iter(variants))
        if not recovered[role]:
            raise CrewBlocked(f"prior {role} WriteBoundaries are empty")
    implementation_paths = recovered["implementer"]
    test_paths = recovered["test_author"]
    for boundaries in by_role["implementer"]:
        if boundaries.denied_paths != test_paths:
            raise CrewBlocked("prior Implementer denied paths do not match Test Author authority")
    for boundaries in by_role["test_author"]:
        if boundaries.denied_paths != implementation_paths:
            raise CrewBlocked("prior Test Author denied paths do not match Implementer authority")
    return implementation_paths, test_paths

def load_retry_context(*, source: Path, identity: SourceIdentity, output_root: Path,
                       prior_run_id: str, feedback_file: Path) -> RetryContext:
    if not isinstance(prior_run_id, str) or not RUN_ID_RE.fullmatch(prior_run_id):
        raise CrewBlocked("--retry-run must be a single conservative run ID without separators or traversal")
    try:
        resolved_output_root = output_root.resolve(strict=True)
    except OSError as exc:
        raise CrewBlocked("ExecutionCrew output root does not exist or cannot be resolved for retry") from exc
    prior_dir = _resolve_existing_under(
        resolved_output_root, resolved_output_root / prior_run_id, field="prior run"
    )
    if not prior_dir.is_dir():
        raise CrewBlocked("prior run must be a directory")
    result_path = _resolve_existing_under(
        prior_dir, prior_dir / "crew_result.json", field="prior crew_result.json"
    )
    if not stat.S_ISREG(result_path.stat().st_mode):
        raise CrewBlocked("prior crew_result.json must be a regular file")
    prior = _json_object(result_path, field="prior crew_result.json")
    if prior.get("schema_version") != "1.0":
        raise CrewBlocked("prior crew_result.json has an unsupported schema_version")
    if prior.get("run_id") != prior_run_id:
        raise CrewBlocked("prior crew_result.json run_id does not match --retry-run")
    if prior.get("crew_status") != "review_ready":
        raise CrewBlocked("prior ExecutionCrew run must have crew_status review_ready")
    if prior.get("validator_status") != "pass":
        raise CrewBlocked("prior review-ready run must have validator_status pass")
    task_id = prior.get("task_id")
    provider = prior.get("provider")
    execution_model = prior.get("execution_model")
    execution_reasoning_effort = prior.get("execution_reasoning_effort")
    source_head = prior.get("source_head")
    source_tree = prior.get("source_tree")
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        raise CrewBlocked("prior crew_result.json has an invalid task_id")
    if provider not in ("claude", "codex"):
        raise CrewBlocked("prior crew_result.json has an invalid provider")
    if execution_model is not None and (
            not isinstance(execution_model, str) or not execution_model.strip()
            or len(execution_model.strip()) > 200 or any(mark in execution_model for mark in ("\r","\n","\x00"))):
        raise CrewBlocked("prior crew_result.json has an invalid execution_model")
    if execution_model is not None:
        execution_model = execution_model.strip()
    if execution_reasoning_effort is not None and execution_reasoning_effort not in OPENAI_REASONING_EFFORTS:
        raise CrewBlocked("prior crew_result.json has an invalid execution_reasoning_effort")
    if provider == "claude" and execution_reasoning_effort is not None:
        raise CrewBlocked("prior Claude run must not record an execution reasoning effort")
    if not isinstance(source_head, str) or not GIT_OBJECT_RE.fullmatch(source_head):
        raise CrewBlocked("prior crew_result.json has an invalid source_head")
    if not isinstance(source_tree, str) or not GIT_OBJECT_RE.fullmatch(source_tree):
        raise CrewBlocked("prior crew_result.json has an invalid source_tree")
    if not isinstance(prior.get("source_branch"), str):
        raise CrewBlocked("prior crew_result.json is missing valid source branch metadata")
    try:
        contract_identity = TaskContractIdentity.from_dict(prior.get("task_contract_identity"))
    except (TypeError, ValueError) as exc:
        raise CrewBlocked(f"prior crew_result.json has invalid task contract identity: {exc}") from exc
    if contract_identity.path != f"Tasks/{task_id}.yaml":
        raise CrewBlocked("prior task contract identity does not match task_id")
    prior_tree = git(source, "rev-parse", "--verify", f"{source_head}^{{tree}}", check=False)
    if prior_tree.returncode or prior_tree.stdout.strip() != source_tree:
        raise CrewBlocked("prior source commit/tree metadata cannot be proven in the current repository")
    ancestor = git(source, "merge-base", "--is-ancestor", source_head, identity.head, check=False)
    if ancestor.returncode == 1:
        raise CrewBlocked("prior source HEAD must be an ancestor of the current source HEAD")
    if ancestor.returncode != 0:
        raise CrewBlocked("prior source ancestry could not be proven")
    implementation_paths, test_paths = _legacy_requested_scope(
        prior_dir, task_id=task_id, provider=provider, contract_identity=contract_identity
    )
    has_implementation = "requested_implementation_paths" in prior
    has_tests = "requested_test_paths" in prior
    if has_implementation != has_tests:
        raise CrewBlocked("prior crew_result.json has incomplete requested-scope metadata")
    if has_implementation:
        result_implementation = _requested_paths(
            prior["requested_implementation_paths"], field="requested_implementation_paths"
        )
        result_tests = _requested_paths(prior["requested_test_paths"], field="requested_test_paths")
        if result_implementation != implementation_paths or result_tests != test_paths:
            raise CrewBlocked("prior requested scope does not match authoritative TaskExecution WriteBoundaries")
    has_new_metadata = all(field in prior for field in (
        "requested_existing_implementation_paths", "requested_new_implementation_paths",
        "requested_existing_test_paths", "requested_new_test_paths",
    ))
    any_new_metadata = any(field in prior for field in (
        "requested_existing_implementation_paths", "requested_new_implementation_paths",
        "requested_existing_test_paths", "requested_new_test_paths",
    ))
    if any_new_metadata and not has_new_metadata:
        raise CrewBlocked("prior crew_result.json has incomplete existing/new path metadata")
    if has_new_metadata:
        prior_existing_impl = tuple(_requested_paths(prior["requested_existing_implementation_paths"], field="requested_existing_implementation_paths")) if prior["requested_existing_implementation_paths"] else ()
        prior_new_impl = tuple(_requested_paths(prior["requested_new_implementation_paths"], field="requested_new_implementation_paths")) if prior["requested_new_implementation_paths"] else ()
        prior_existing_test = tuple(_requested_paths(prior["requested_existing_test_paths"], field="requested_existing_test_paths")) if prior["requested_existing_test_paths"] else ()
        prior_new_test = tuple(_requested_paths(prior["requested_new_test_paths"], field="requested_new_test_paths")) if prior["requested_new_test_paths"] else ()
        if tuple(sorted((*prior_existing_impl, *prior_new_impl))) != implementation_paths or tuple(sorted((*prior_existing_test, *prior_new_test))) != test_paths:
            raise CrewBlocked("prior existing/new authority does not match authoritative TaskExecution WriteBoundaries")
        authoritative_existing_impl = tuple(path for path in implementation_paths if _commit_path_kind(source, source_head, path) == "regular")
        authoritative_new_impl = tuple(path for path in implementation_paths if _commit_path_kind(source, source_head, path) == "absent")
        authoritative_existing_test = tuple(path for path in test_paths if _commit_path_kind(source, source_head, path) == "regular")
        authoritative_new_test = tuple(path for path in test_paths if _commit_path_kind(source, source_head, path) == "absent")
        classified = set((*authoritative_existing_impl, *authoritative_new_impl, *authoritative_existing_test, *authoritative_new_test))
        unclassifiable = sorted(set((*implementation_paths, *test_paths)) - classified)
        if unclassifiable:
            raise CrewBlocked(f"prior role path is not a regular Git blob or absent at prior source HEAD: {unclassifiable[0]}")
        if (prior_existing_impl != authoritative_existing_impl or prior_new_impl != authoritative_new_impl
                or prior_existing_test != authoritative_existing_test or prior_new_test != authoritative_new_test):
            raise CrewBlocked("prior existing/new path metadata does not match prior source HEAD")
    else:
        prior_existing_impl, prior_new_impl = implementation_paths, ()
        prior_existing_test, prior_new_test = test_paths, ()
    for path in (*prior_existing_impl, *prior_existing_test):
        if _commit_path_kind(source, identity.head, path) != "regular":
            raise CrewBlocked(f"prior-existing path is absent at current HEAD: {path}")
    for path in (*prior_new_impl, *prior_new_test):
        if _commit_path_kind(source, identity.head, path) == "other":
            raise CrewBlocked(f"prior-new path is not a regular Git blob or absent at current HEAD: {path}")
    new_implementation_paths = tuple(path for path in prior_new_impl if _commit_path_kind(source, identity.head, path) == "absent")
    new_test_paths = tuple(path for path in prior_new_test if _commit_path_kind(source, identity.head, path) == "absent")
    implementation_paths = tuple(sorted((*prior_existing_impl, *(path for path in prior_new_impl if _commit_path_kind(source, identity.head, path) == "regular"))))
    test_paths = tuple(sorted((*prior_existing_test, *(path for path in prior_new_test if _commit_path_kind(source, identity.head, path) == "regular"))))

    candidate_path = _resolve_existing_under(
        prior_dir, prior_dir / "candidate.patch", field="prior candidate.patch"
    )
    candidate_bytes = _read_regular_bytes(
        candidate_path, field="prior candidate.patch", max_bytes=MAX_RETRY_CANDIDATE_BYTES
    )
    if not candidate_bytes:
        raise CrewBlocked("prior candidate.patch must be non-empty")
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    recorded_candidate_sha256 = prior.get("candidate_patch_sha256")
    if recorded_candidate_sha256 is not None:
        if not isinstance(recorded_candidate_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded_candidate_sha256):
            raise CrewBlocked("prior crew_result.json has an invalid candidate_patch_sha256")
        if recorded_candidate_sha256 != candidate_sha256:
            raise CrewBlocked("prior candidate.patch SHA-256 does not match crew_result.json")
    candidate_paths = _requested_paths(prior.get("final_actual_changed_paths"), field="final_actual_changed_paths")
    candidate_sidecars = tuple(sorted(filter(None, (_sidecar(path) for path in (*prior_new_impl, *prior_new_test)))))
    recorded_sidecars = prior.get("pipeline_generated_paths")
    if recorded_sidecars is not None:
        if not isinstance(recorded_sidecars, list) or any(not isinstance(path, str) for path in recorded_sidecars):
            raise CrewBlocked("prior crew_result.json has invalid pipeline_generated_paths")
        if tuple(sorted(recorded_sidecars)) != candidate_sidecars:
            raise CrewBlocked("prior pipeline-generated paths do not match authoritative prior-new paths")
    allowed_candidate_paths = set(implementation_paths) | set(new_implementation_paths) | set(test_paths) | set(new_test_paths) | set(candidate_sidecars)
    if not set(candidate_paths).issubset(allowed_candidate_paths):
        raise CrewBlocked("prior candidate changed paths exceed inherited ExecutionCrew WriteBoundaries and deterministic sidecar authority")
    if set(candidate_sidecars) - set(candidate_paths):
        raise CrewBlocked("prior candidate is missing a deterministic pipeline sidecar")
    feedback_candidate = feedback_file if feedback_file.is_absolute() else resolved_output_root / feedback_file
    feedback_path = _resolve_existing_under(
        resolved_output_root, feedback_candidate, field="human review feedback file"
    )
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(feedback_path, flags)
        feedback_stat = os.fstat(descriptor)
        if not stat.S_ISREG(feedback_stat.st_mode):
            raise CrewBlocked("human review feedback must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            feedback_bytes = stream.read(MAX_REVIEW_FEEDBACK_BYTES + 1)
        feedback_text = feedback_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise CrewBlocked("human review feedback must be valid UTF-8") from exc
    except OSError as exc:
        raise CrewBlocked("human review feedback could not be safely read as a regular file") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(feedback_bytes) > MAX_REVIEW_FEEDBACK_BYTES:
        raise CrewBlocked(f"human review feedback must be at most {MAX_REVIEW_FEEDBACK_BYTES} bytes")
    if not feedback_text.strip():
        raise CrewBlocked("human review feedback must be non-empty")
    return RetryContext(
        prior_run_id=prior_run_id,
        prior_source_head=source_head,
        prior_contract_identity=contract_identity,
        task_id=task_id,
        provider=provider,
        execution_model=execution_model,
        execution_reasoning_effort=execution_reasoning_effort,
        implementation_paths=implementation_paths,
        test_paths=test_paths,
        new_implementation_paths=new_implementation_paths,
        new_test_paths=new_test_paths,
        candidate_bytes=candidate_bytes,
        candidate_sha256=candidate_sha256,
        candidate_paths=candidate_paths,
        candidate_sidecars=candidate_sidecars,
        feedback_bytes=feedback_bytes,
        feedback_text=feedback_text,
        feedback_sha256=hashlib.sha256(feedback_bytes).hexdigest(),
    )

def committed_bytes(source: Path, head: str, path: str) -> bytes:
    validate_repository_path(path, field="committed path")
    result = git(source, "show", f"{head}:{path}", text=False, check=False)
    if result.returncode: raise CrewBlocked(f"committed path cannot be read: {path}")
    return result.stdout

def parse_task(raw: bytes, task_id: str):
    try: value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc: raise CrewBlocked("committed task contract is not valid UTF-8 JSON-subset YAML") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "2.0" or value.get("id") != task_id:
        raise CrewBlocked("committed schema-v2 task contract does not match selected task")
    try: _validate_v2_task(task_id, value)
    except WorkGraphValidationError as exc: raise CrewBlocked(f"committed task contract schema is invalid: {exc}") from exc
    for field, expected in {"contract_disposition":"active", "kind":"implementation", "execution_scope":"single_agent", "decomposition_state":"concrete"}.items():
        if value.get(field) != expected: raise CrewBlocked(f"committed task contract must have {field}={expected!r}")
    return value, TaskContractIdentity(f"Tasks/{task_id}.yaml", value["contract_revision"], hashlib.sha256(raw).hexdigest())

def clone_exact(source: Path, head: str, parent: Path, *, _runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> Path:
    source = source.resolve(strict=True)
    clone = parent / "crew-repository"
    protected_config = parent / "clone.gitconfig"
    clone_env = os.environ.copy()
    clone_env["GIT_CONFIG_GLOBAL"] = str(protected_config)
    for safe_directory in (source, (source / ".git").resolve(strict=True)):
        _runner(("git", "config", "--global", "--add", "safe.directory", str(safe_directory)),
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clone_env)
    clone_result = _runner(("git", "clone", "--no-local", "--no-checkout", str(source), str(clone)),
                           check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=clone_env)
    if clone_result.returncode:
        diagnostic = (clone_result.stderr or clone_result.stdout or "").strip()
        detail = f": {diagnostic}" if diagnostic else ""
        raise CrewBlocked(f"git clone failed with exit code {clone_result.returncode}{detail}")
    git(clone, "config", "--local", "core.autocrlf", "false")
    git(clone, "config", "--local", "core.filemode", "false")
    git(clone, "checkout", "--detach", head)
    if (git(clone, "rev-parse", "HEAD").stdout.strip() != head
            or git(clone, "status", "--porcelain=v1", "--untracked-files=all").stdout
            or clone.resolve().is_relative_to(source) or source.is_relative_to(clone.resolve())):
        raise CrewBlocked("disposable clone is not independent at the exact source HEAD")
    return clone

def runtime_configuration(provider: str, model_override: str|None=None):
    if model_override is not None and (
            not isinstance(model_override,str) or not model_override.strip()
            or len(model_override.strip())>200 or any(mark in model_override for mark in ("\r","\n","\x00"))):
        raise CrewBlocked("execution model override must be one non-empty safe identifier")
    if provider == "claude": key, identifier, model = "claude-crew", "claude-code", model_override.strip() if model_override else os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")
    elif provider == "codex": key, identifier, model = "codex-crew", "openai-codex", model_override.strip() if model_override else os.getenv("NSC_OPENAI_CODEX_MODEL", "gpt-5.6-sol")
    else: raise CrewBlocked("provider must be claude or codex")
    return key, RuntimeConfiguration({key:{"provider":identifier,"models":{"low_cost":model,"standard":model,"high_reasoning":model}}})

@dataclass(frozen=True)
class EntryState:
    kind: str
    sha256: str | None
    tracked: bool

@dataclass(frozen=True)
class Snapshot:
    head: str; index: bytes; entries: Mapping[str, EntryState]

    @property
    def tracked(self) -> Mapping[str, str]:
        return {path: entry.sha256 or "" for path, entry in self.entries.items() if entry.tracked and entry.kind == "regular"}

    @property
    def untracked(self) -> tuple[str, ...]:
        return tuple(sorted(path for path, entry in self.entries.items() if not entry.tracked))

def _entry_state(path: Path, *, tracked: bool) -> EntryState:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return EntryState("missing", None, tracked)
    if stat.S_ISREG(mode):
        return EntryState("regular", hashlib.sha256(path.read_bytes()).hexdigest(), tracked)
    if stat.S_ISLNK(mode):
        return EntryState("symlink", hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest(), tracked)
    if stat.S_ISDIR(mode):
        return EntryState("directory", None, tracked)
    return EntryState("special", None, tracked)

def snapshot(root: Path) -> Snapshot:
    tracked_paths = [p.decode("utf-8", "surrogateescape") for p in git(root, "ls-files", "-z", text=False).stdout.split(b"\0") if p]
    index = git(root, "ls-files", "--stage", "-z", text=False).stdout
    # --directory is intentionally omitted: every ignored/unignored filesystem entry is named.
    untracked_paths = [p.decode("utf-8", "surrogateescape") for p in git(
        root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", text=False
    ).stdout.split(b"\0") if p]
    ordinary_untracked = [p.decode("utf-8", "surrogateescape") for p in git(
        root, "ls-files", "--others", "--exclude-standard", "-z", text=False
    ).stdout.split(b"\0") if p]
    entries: dict[str, EntryState] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        for child in os.scandir(directory):
            if directory == root and child.name == ".git":
                continue
            relative = Path(child.path).relative_to(root).as_posix()
            entries[relative] = _entry_state(Path(child.path), tracked=False)
            if child.is_dir(follow_symlinks=False):
                pending.append(Path(child.path))
    entries.update({path: _entry_state(root / path, tracked=True) for path in tracked_paths})
    for path in set(untracked_paths) | set(ordinary_untracked):
        entries[path] = _entry_state(root / path, tracked=False)
    return Snapshot(git(root, "rev-parse", "HEAD").stdout.strip(), index, entries)

def incremental_check(before: Snapshot, after: Snapshot, invocation: AgentInvocationRequest, *, require_change: bool):
    reasons=[]
    if after.head != before.head: reasons.append("clone HEAD changed")
    if after.index != before.index: reasons.append("Git index changed")
    actual=sorted(path for path in set(before.entries) | set(after.entries)
                  if before.entries.get(path) != after.entries.get(path))
    for path in actual:
        before_entry, after_entry = before.entries.get(path), after.entries.get(path)
        if not invocation.is_path_writable(path):
            if before_entry is None and after_entry is not None and not after_entry.tracked:
                reasons.append(f"untracked file: {path}")
            else:
                reasons.append(f"incremental changed path outside role WriteBoundaries: {path}")
        elif after_entry is None:
            reasons.append(f"approved path deleted: {path}")
        elif after_entry.kind != "regular":
            reasons.append(f"approved path is not a regular file: {path} ({after_entry.kind})")
        elif before_entry is None and after_entry.tracked:
            reasons.append(f"new approved path unexpectedly became tracked: {path}")
    if require_change and not actual: reasons.append("role made no required file modification")
    return actual, reasons

def changed_paths(baseline: Snapshot, final: Snapshot) -> list[str]:
    """Return tracked additions, deletions, and byte changes relative to one clone baseline."""
    return sorted(path for path in set(baseline.entries) | set(final.entries)
                  if baseline.entries.get(path) != final.entries.get(path))

def _folded(path: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.split("/"))

def _sidecar(path: str) -> str | None:
    return f"{path}.meta" if path.startswith("Assets/") and not path.casefold().endswith(".meta") else None

def _commit_path_kind(root: Path, head: str, path: str) -> str:
    """Classify one exact path in a captured commit without consulting the worktree/index."""
    result = git(root, "ls-tree", "-z", head, "--", path, text=False, check=False)
    if result.returncode:
        raise CrewBlocked(f"Git tree path could not be inspected at captured HEAD: {path}")
    records = [record for record in result.stdout.split(b"\0") if record]
    exact = []
    for record in records:
        metadata, separator, raw_path = record.partition(b"\t")
        if separator and raw_path.decode("utf-8", "surrogateescape") == path:
            exact.append(metadata.split())
    if not exact:
        return "absent"
    if len(exact) != 1 or len(exact[0]) != 3:
        return "other"
    mode, object_type, _ = exact[0]
    return "regular" if object_type == b"blob" and mode in (b"100644", b"100755") else "other"

def _commit_parent_is_tree(root: Path, head: str, parent: str) -> bool:
    if not parent or parent == ".":
        return True
    result = git(root, "cat-file", "-t", f"{head}:{parent}", check=False)
    return result.returncode == 0 and result.stdout.strip() == "tree"

def unity_meta_bytes(path: str) -> bytes:
    normalized = "/".join(part.casefold() for part in path.split("/"))
    digest = hashlib.sha256(b"NoSafeCircle.ExecutionCrew.UnityMeta/v1\0" + normalized.encode("utf-8")).hexdigest()[:32]
    return f"fileFormatVersion: 2\nguid: {digest}\n".encode("ascii")

def preflight_role_paths(root: Path, head: str, existing_implementation: tuple[str, ...],
                         new_implementation: tuple[str, ...], existing_tests: tuple[str, ...],
                         new_tests: tuple[str, ...]) -> tuple[RolePathPlan, RolePathPlan]:
    groups = (("implementation", existing_implementation, new_implementation),
              ("test", existing_tests, new_tests))
    all_explicit: list[tuple[str, str, str]] = []
    for role, existing, new in groups:
        for kind, paths in (("existing", existing), ("new", new)):
            for path in paths:
                try: validate_repository_path(path, field=f"{role} {kind} path")
                except ValueError as exc: raise CrewBlocked(str(exc)) from exc
                all_explicit.append((role, kind, path))
    sidecars = [(role, path, _sidecar(path)) for role, _, path in all_explicit if _ == "new"]
    sidecars = [(role, path, sidecar) for role, path, sidecar in sidecars if sidecar is not None]
    surfaces = [(role, kind, path) for role, kind, path in all_explicit] + [
        (role, "sidecar", sidecar) for role, _, sidecar in sidecars
    ]
    keys: dict[tuple[str, ...], tuple[str, str, str]] = {}
    for item in surfaces:
        key = _folded(item[2])
        if key in keys:
            prior = keys[key]
            if prior[0] != item[0]: raise CrewBlocked("implementation and test role paths must be disjoint, including sidecars")
            raise CrewBlocked(f"duplicate or colliding {item[0]} role path: {item[2]}")
        keys[key] = item
    tracked_paths = [
        item.decode("utf-8", "surrogateescape")
        for item in git(root, "ls-files", "-z", text=False).stdout.split(b"\0") if item
    ]
    tracked_path_set = frozenset(tracked_paths)
    tracked_by_key: dict[tuple[str, ...], list[str]] = {}
    for tracked_path in tracked_paths:
        tracked_by_key.setdefault(_folded(tracked_path), []).append(tracked_path)
    root_resolved = root.resolve(strict=True)

    def sibling_aliases(path: str) -> tuple[str, ...]:
        target = root / path
        parent = target.parent
        try:
            return tuple(
                child.name for child in os.scandir(parent)
                if child.name.casefold() == target.name.casefold() and child.name != target.name
            )
        except (FileNotFoundError, NotADirectoryError):
            return ()

    for role, kind, path in all_explicit:
        key = _folded(path)
        target = root / path
        if kind == "existing":
            try: mode = target.lstat().st_mode
            except FileNotFoundError: mode = 0
            if path not in tracked_path_set or not stat.S_ISREG(mode) or _commit_path_kind(root, head, path) != "regular":
                raise CrewBlocked(f"{role} role path must be an existing tracked regular file: {path}")
            if len(tracked_by_key.get(key, ())) != 1 or sibling_aliases(path):
                raise CrewBlocked(f"{role} role path has a case-insensitive alias collision: {path}")
            continue
        if path.casefold().endswith(".meta"): raise CrewBlocked(f"new {role} path must not end in .meta: {path}")
        if key in tracked_by_key: raise CrewBlocked(f"new {role} path is already tracked: {path}")
        if _commit_path_kind(root, head, path) != "absent":
            raise CrewBlocked(f"new {role} path is not absent from captured Git tree: {path}")
        if os.path.lexists(target) or sibling_aliases(path): raise CrewBlocked(f"new {role} path already exists or has a case-insensitive sibling: {path}")
        parent = target.parent
        if not parent.exists() or not parent.is_dir(): raise CrewBlocked(f"new {role} path parent must be an existing ordinary directory: {path}")
        parent_path = Path(path).parent.as_posix()
        if not _commit_parent_is_tree(root, head, parent_path):
            raise CrewBlocked(f"new {role} path parent must exist as a directory in the captured Git tree: {path}")
        cursor = root
        for part in Path(path).parts[:-1]:
            cursor /= part
            if cursor.is_symlink(): raise CrewBlocked(f"new {role} path parent ancestry must not contain a symlink: {path}")
        try: resolved_parent = parent.resolve(strict=True)
        except OSError as exc: raise CrewBlocked(f"new {role} path parent cannot be resolved: {path}") from exc
        if not resolved_parent.is_relative_to(root_resolved):
            raise CrewBlocked(f"new {role} path must resolve underneath repository root: {path}")
        ignored = git(root, "check-ignore", "--no-index", "--quiet", "--", path, check=False)
        if ignored.returncode == 0: raise CrewBlocked(f"new {role} path is ignored by Git: {path}")
        if ignored.returncode not in (0, 1): raise CrewBlocked(f"Git ignore status could not be determined: {path}")
    for role, _, sidecar in sidecars:
        assert sidecar is not None
        if _folded(sidecar) in tracked_by_key or os.path.lexists(root / sidecar) or sibling_aliases(sidecar):
            raise CrewBlocked(f"generated sidecar path is not absent: {sidecar}")
        if _commit_path_kind(root, head, sidecar) != "absent":
            raise CrewBlocked(f"generated sidecar path is not absent from captured Git tree: {sidecar}")
        ignored = git(root, "check-ignore", "--no-index", "--quiet", "--", sidecar, check=False)
        if ignored.returncode == 0: raise CrewBlocked(f"generated sidecar path is ignored by Git: {sidecar}")
    for _, _, path in all_explicit:
        for _, kind2, other in all_explicit:
            if path != other and _folded(other)[:len(_folded(path))] == _folded(path):
                raise CrewBlocked(f"approved path may not be nested beneath another approved file path: {other}")
    def plan(existing: tuple[str, ...], new: tuple[str, ...]) -> RolePathPlan:
        generated = tuple(sorted(filter(None, (_sidecar(path) for path in new))))
        return RolePathPlan(tuple(sorted(existing)), tuple(sorted(new)), generated)
    return plan(existing_implementation, new_implementation), plan(existing_tests, new_tests)

def validator_semantic_reasons(output: Mapping[str, Any], expected_ids: tuple[str, ...]) -> list[str]:
    results = output.get("criteria_results", [])
    ids = [item.get("id") for item in results if isinstance(item, Mapping)]
    reasons: list[str] = []
    if len(ids) != len(set(ids)): reasons.append("validator criteria_results contains duplicate IDs")
    missing = sorted(set(expected_ids) - set(ids))
    unknown = sorted(set(ids) - set(expected_ids))
    if missing: reasons.append(f"validator criteria_results missing IDs: {', '.join(missing)}")
    if unknown: reasons.append(f"validator criteria_results contains unknown IDs: {', '.join(unknown)}")
    status = output.get("status")
    failed = any(item.get("status") == "fail" for item in results if isinstance(item, Mapping))
    blocking = bool(normalized_validator_blocking_issues(output.get("blocking_issues")))
    non_pass_reason_used = False
    contract_review_reason_used = False
    for item in results:
        if not isinstance(item, Mapping): continue
        item_status, reason_code = item.get("status"), item.get("reason_code")
        if reason_code not in VALIDATOR_STATUS_REASON_CODES.get(item_status, frozenset()):
            reasons.append(f"validator criteria_results item {item.get('id')!r} has status={item_status!r} incompatible with reason_code={reason_code!r}")
        if item_status == "not_proven" and reason_code in VALIDATOR_NON_PASS_REASON_CODES:
            non_pass_reason_used = True
        if reason_code in VALIDATOR_CONTRACT_REVIEW_REASON_CODES:
            contract_review_reason_used = True
    if status == "pass" and failed: reasons.append("validator pass contains a failed criterion")
    if status == "pass" and blocking: reasons.append("validator pass contains blocking issues")
    if status == "pass" and non_pass_reason_used:
        reasons.append("validator pass contains a not_proven item whose reason_code is not runtime_not_executed")
    if contract_review_reason_used and status != "blocked_by_design":
        reasons.append("validator reason_code missing_integration_dependency/design_ambiguity requires overall status=blocked_by_design")
    if status == "needs_changes" and not (failed or blocking):
        reasons.append("validator needs_changes requires a failed criterion or blocking issue")
    return reasons


def validator_requires_contract_review(output: Mapping[str, Any]) -> bool:
    """True when a not_proven item's reason_code identifies a locality defect the mandatory Contract
    Locality Auditor should have caught but did not; this fallback routes the crew to
    contract_review_required rather than a generic blocked_by_design rejection."""
    return any(
        isinstance(item, Mapping) and item.get("reason_code") in VALIDATOR_CONTRACT_REVIEW_REASON_CODES
        for item in output.get("criteria_results", [])
    )

def powershell_single_quote(path: str) -> str:
    """Quote a literal path for safe copy/paste into PowerShell, doubling embedded single quotes."""
    return "'" + path.replace("'", "''") + "'"

def patch_commands(path: str | None, *, applyable: bool) -> dict[str, str | None]:
    """Copy/paste-ready PowerShell commands for one artifact path, or all-null when there is none.
    Never emits git apply/--check commands for a non-applyable (diagnostic) artifact."""
    if not path:
        return {"find": None, "check": None, "apply": None, "verify": None}
    quoted = powershell_single_quote(path)
    find_command = f"Get-Item -LiteralPath {quoted}"
    if not applyable:
        return {"find": find_command, "check": None, "apply": None, "verify": None}
    return {
        "find": find_command,
        "check": f"git apply --check {quoted}",
        "apply": f"git apply {quoted}",
        "verify": "git status --short; git diff --check",
    }

def audit_commands(path: str | None) -> dict[str, str | None]:
    """Copy/paste-ready PowerShell find/inspect commands for the read-only contract_locality_audit.json
    artifact, or all-null when there is none. Distinct shape from patch_commands: an audit artifact is
    never applied, so it never has check/apply/verify commands."""
    if not path:
        return {"find": None, "inspect": None}
    quoted = powershell_single_quote(path)
    return {"find": f"Get-Item -LiteralPath {quoted}", "inspect": f"Get-Content -LiteralPath {quoted}"}


def safe_human_reason(reasons: list[str]) -> str | None:
    """First rejection reason, unless it embeds raw agent-authored blocker text (which may quote
    human-review feedback), in which case a fixed structural summary is used instead. None if no
    reason was recorded; never fabricate an explanation."""
    if not reasons:
        return None
    first = reasons[0]
    if first.startswith("implementer blocker: "):
        return "The Implementer reported a blocker."
    if first.startswith("test author blocker: "):
        return "The Test Author reported a blocker."
    return first


_EMPTY_AGENT_SENTINELS = frozenset(
    {
        "empty",
        "n/a",
        "na",
        "nil",
        "no blocker",
        "no blockers",
        "no blockers found",
        "no blockers identified",
        "no changes",
        "no changes were made",
        "no issues",
        "no issues found",
        "no",
        "none",
        "none - no changes were made",
        "none found",
        "none identified",
        "not applicable",
        "nothing",
        "nothing to report",
        "null",
    }
)


def _is_empty_agent_sentinel(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = unicodedata.normalize("NFKC", value).replace("\u00a0", " ").strip()
    if len(text) > 64:
        return False
    while len(text) >= 2 and (text[0], text[-1]) in {
        ("(", ")"),
        ("[", "]"),
        ("{", "}"),
        ('"', '"'),
        ("'", "'"),
    }:
        text = text[1:-1].strip()
    text = text.strip(" \t-–—•").rstrip(".!;,:…").strip()
    text = " ".join(text.split()).casefold()
    return text == "" or text in _EMPTY_AGENT_SENTINELS


def normalized_agent_blockers(value: Any) -> list[str]:
    """Return substantive agent blockers, ignoring explicit no-blocker sentinels.

    Providers occasionally serialize an empty semantic answer as ``["(none)"]``
    even though the schema asks for an empty array.  Treat only a small exact set
    of unambiguous sentinels as empty; preserve every other string verbatim so a
    genuine blocker cannot be silently discarded.
    """
    if not isinstance(value, list):
        return []
    blockers: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or _is_empty_agent_sentinel(text):
            continue
        blockers.append(text)
    return blockers


def normalized_agent_claimed_paths(value: Any) -> list[str]:
    """Preserve claimed paths except explicit prose meaning no changed paths."""

    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and not _is_empty_agent_sentinel(item)
    ]


def normalized_validator_blocking_issues(value: Any) -> list[Mapping[str, Any]]:
    """Ignore only validator issue objects whose every text field says none."""

    if not isinstance(value, list):
        return []
    issues: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        text_values = [item.get(name) for name in ("path", "issue", "required_fix")]
        if all(isinstance(text, str) for text in text_values) and all(
            _is_empty_agent_sentinel(text) for text in text_values
        ):
            continue
        issues.append(item)
    return issues


def normalize_role_structured_output(
    role: str, output: Any
) -> tuple[dict[str, Any], dict[str, list[Any]]]:
    """Normalize only declared ExecutionCrew empty sentinels, with audit evidence."""

    if not isinstance(output, Mapping):
        return {}, {}
    normalized = dict(output)
    discarded: dict[str, list[Any]] = {}
    for field_name, field_kind in ROLE_OUTPUT_NORMALIZATION.get(role, {}).items():
        original = output.get(field_name)
        if not isinstance(original, list):
            continue
        if field_kind in {"string_list", "path_list"}:
            kept = [
                item
                for item in original
                if isinstance(item, str) and not _is_empty_agent_sentinel(item)
            ]
        elif field_kind == "blocking_issue_list":
            kept = normalized_validator_blocking_issues(original)
        else:
            raise CrewBlocked(
                f"unsupported structured-output normalization kind {field_kind!r}"
            )
        normalized[field_name] = kept
        removed = [item for item in original if item not in kept]
        if removed:
            discarded[field_name] = removed
    return normalized, discarded


def _normalization_audit_fields(discarded: Mapping[str, list[Any]]) -> dict[str, Any]:
    return {
        f"normalized_discarded_{field_name}": list(values)
        for field_name, values in discarded.items()
    }

def source_revalidation(source: Path, identity: SourceIdentity):
    reasons=[]
    try:
        if git(source,"rev-parse","HEAD").stdout.strip()!=identity.head: reasons.append("source HEAD changed during provider execution")
        if git(source,"rev-parse","HEAD^{tree}").stdout.strip()!=identity.tree: reasons.append("source tree changed during provider execution")
        if git(source,"status","--porcelain=v1","--untracked-files=all").stdout: reasons.append("source working tree changed during provider execution")
    except (OSError, subprocess.CalledProcessError): reasons.append("source identity could not be revalidated")
    return reasons

def _new_file_patch(clone: Path, path: str) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(clone), "diff", "--no-index", "--binary", "--full-index", "--no-ext-diff",
         "--", "/dev/null", path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode not in (0, 1):
        raise CrewBlocked(f"could not construct new-file patch for {path}")
    return result.stdout

def full_patch(clone: Path, head: str, new_paths: tuple[str, ...] = ()) -> bytes:
    tracked = git(clone,"diff","--binary","--full-index","--no-ext-diff","--no-renames",head,text=False,check=False).stdout
    ordinary_diff_paths = set(diff_paths(clone, head))
    return tracked + b"".join(_new_file_patch(clone, path) for path in sorted(new_paths)
                                if path not in ordinary_diff_paths and _entry_state(clone/path, tracked=False).kind == "regular")

def diff_paths(clone: Path, head: str) -> list[str]:
    raw = git(clone,"diff","--name-only","--no-ext-diff","--no-renames","-z",head,text=False,check=False).stdout
    return sorted(path.decode("utf-8", "surrogateescape") for path in raw.split(b"\0") if path)

def paths_patch(clone: Path, head: str, paths: tuple[str, ...], new_paths: tuple[str, ...] = ()) -> bytes:
    existing = tuple(path for path in paths if path not in new_paths)
    tracked = (git(clone,"diff","--binary","--full-index","--no-ext-diff","--no-renames",head,"--",*existing,text=False,check=False).stdout
               if existing else b"")
    return tracked + b"".join(_new_file_patch(clone, path) for path in sorted(new_paths)
                                if _entry_state(clone/path, tracked=False).kind == "regular")

def verify_patch_applies(source: Path, patch: bytes) -> None:
    result = subprocess.run(("git", "-C", str(source), "apply", "--check", "--binary", "-"),
                            input=patch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise CrewBlocked(f"candidate patch does not apply cleanly to captured baseline: {detail}")

def _git_apply_bytes(root: Path, patch_bytes: bytes, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git", "-C", str(root), "apply", *args, "-"),
        input=patch_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )

def seed_retry_candidate(clone: Path, baseline: Snapshot, retry: RetryContext) -> str:
    # Seed only the disposable clone. baseline remains the clean current-source snapshot used
    # for the final full candidate; per-role snapshots are taken after this seed.
    expected_paths = sorted(retry.candidate_paths)
    allowed = (set(retry.implementation_paths) | set(retry.new_implementation_paths)
               | set(retry.test_paths) | set(retry.new_test_paths) | set(retry.candidate_sidecars))
    if not expected_paths or not set(expected_paths).issubset(allowed):
        raise CrewBlocked("prior candidate paths are invalid for inherited retry WriteBoundaries")

    current_head = baseline.head

    # A retry candidate is lineage-bound to the exact candidate-owned file state it was reviewed
    # against. If those paths are unchanged since the prior source HEAD, seed the rejected candidate.
    # If they changed, do not silently layer the old candidate even when Git could apply its hunks:
    # only an exact already-present candidate post-image is accepted below.
    preimage_comparison = git(
        clone, "diff", "--quiet", "--ignore-cr-at-eol",
        retry.prior_source_head, current_head, "--", *expected_paths, check=False
    )
    if preimage_comparison.returncode not in (0, 1):
        raise CrewBlocked("current source could not be compared to the prior candidate source state")

    if preimage_comparison.returncode == 0:
        forward_check = _git_apply_bytes(clone, retry.candidate_bytes, "--check")
        if forward_check.returncode != 0:
            raise CrewBlocked("prior candidate.patch does not apply cleanly to its unchanged candidate-owned source state")
        applied = _git_apply_bytes(clone, retry.candidate_bytes)
        if applied.returncode != 0:
            raise CrewBlocked("prior candidate.patch passed --check but could not be seeded into the disposable clone")
        seeded = snapshot(clone)
        actual_paths = changed_paths(baseline, seeded)
        if seeded.head != baseline.head or seeded.index != baseline.index:
            raise CrewBlocked("seeding prior candidate.patch changed clone HEAD/index state")
        if actual_paths != expected_paths:
            raise CrewBlocked("seeded prior candidate paths do not match prior final_actual_changed_paths")
        for path in expected_paths:
            entry = seeded.entries.get(path)
            if entry is None or entry.kind != "regular":
                raise CrewBlocked(f"seeded prior candidate path is not a regular file: {path}")
        return "applied"

    # Candidate-owned paths changed after the prior run. The only safe historical compatibility case
    # is that the rejected candidate itself was committed exactly. Reconstruct that exact post-image
    # in this disposable clone, compare it to current committed source, then restore the clone.
    with tempfile.TemporaryDirectory(prefix="nsc-execution-crew-prior-") as temporary:
        prior_clone = clone_exact(clone, retry.prior_source_head, Path(temporary))
        prior_clean = snapshot(prior_clone)
        if (prior_clean.head != retry.prior_source_head
                or git(prior_clone, "status", "--porcelain=v1", "--untracked-files=all").stdout):
            raise CrewBlocked("prior candidate source reconstruction did not produce a clean disposable clone")
        prior_check = _git_apply_bytes(prior_clone, retry.candidate_bytes, "--check")
        if prior_check.returncode != 0:
            raise CrewBlocked("prior candidate.patch does not apply to its recorded source HEAD")
        prior_apply = _git_apply_bytes(prior_clone, retry.candidate_bytes)
        if prior_apply.returncode != 0:
            raise CrewBlocked("prior candidate.patch could not reconstruct its recorded candidate post-image")
        candidate_postimage = snapshot(prior_clone)
        reconstructed_paths = changed_paths(prior_clean, candidate_postimage)
        postimage_entries = {path:candidate_postimage.entries.get(path) for path in expected_paths}

    if snapshot(clone) != baseline:
        raise CrewBlocked("already-present candidate verification changed the current disposable clone")
    if reconstructed_paths != expected_paths:
        raise CrewBlocked("reconstructed prior candidate paths do not match prior final_actual_changed_paths")
    current_entries = {path:baseline.entries.get(path) for path in expected_paths}
    equivalent = all(
        postimage_entries[path] is not None
        and current_entries[path] is not None
        and postimage_entries[path].kind == current_entries[path].kind == "regular"
        and postimage_entries[path].sha256 == current_entries[path].sha256
        for path in expected_paths
    )
    if not equivalent:
        raise CrewBlocked("prior candidate.patch neither applies cleanly nor is already present at the current source HEAD")
    return "already_present"

ProviderFactory = Callable[[str, Path, bool, str], tuple[str, RuntimeConfiguration, Mapping[str, Any]]]


def aggregate_token_usage(invocations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum normalized AgentRuntime usage without inferring any missing values."""

    available = [item["usage"] for item in invocations if item.get("usage") is not None]
    reported = {
        field: sum(getattr(usage, field) for usage in available)
        for field in ("input_tokens", "output_tokens", "total_tokens")
    }
    missing = len(invocations) - len(available)
    complete = missing == 0
    return {
        "schema_version": "1.0",
        "status": "complete" if complete else "incomplete",
        "complete": complete,
        **{
            field: reported[field] if complete else None
            for field in ("input_tokens", "output_tokens", "total_tokens")
        },
        **{
            f"reported_{field}": reported[field]
            for field in ("input_tokens", "output_tokens", "total_tokens")
        },
        "invocation_count": len(invocations),
        "usage_available_invocation_count": len(available),
        "missing_usage_invocation_count": missing,
    }

def resolve_role_session(role_session_bindings: Mapping[str, Any]|None, role: str,
                         provider_identifier: str) -> ProviderSessionBinding|None:
    """Return the exact opt-in session binding for this role, or None.

    Sessions are role-specific and provider-specific. A binding filed under one
    role but naming another, or naming another provider, is refused here rather
    than being handed to an adapter, so a pooled worker can never silently
    continue an Implementer conversation as a Validator or a Claude
    conversation through Codex.
    """

    if not role_session_bindings:
        return None
    binding = role_session_bindings.get(role)
    if binding is None:
        return None
    if type(binding) is not ProviderSessionBinding:
        raise CrewBlocked("provider session binding must be an exact ProviderSessionBinding")
    if binding.role != role:
        raise CrewBlocked(
            f"provider session is bound to role {binding.role!r} and cannot be used for role {role!r}"
        )
    if binding.provider_identifier != provider_identifier:
        raise CrewBlocked(
            f"provider session is bound to provider {binding.provider_identifier!r} "
            f"and cannot be used through {provider_identifier!r}"
        )
    return binding


ROLE_EVIDENCE_OBLIGATIONS = {
    "contract_locality_auditor": (
        "Classify every current AC-### and VAL-### exactly once; write nothing.",
    ),
    "implementer": (
        "Edit only the exact approved implementation paths for this assignment.",
        "ExecutionCrew validates this attempt's actual changed paths deterministically.",
    ),
    "test_author": (
        "Author Unity tests only within the exact approved test paths for this assignment.",
        "Follow the committed Unity testing policy; tests must not mutate tracked files.",
    ),
    "validator": (
        "Semantically review the supplied candidate only; write nothing.",
    ),
}


# The exact model capability class each role is invoked with. It is part of the
# pooled compatibility identity, so a lease that was minted for one class must
# never be handed to a role this run routes at another.
ROLE_CAPABILITY_CLASSES = {
    "contract_locality_auditor": "high_reasoning",
    "implementer": "standard",
    "test_author": "low_cost",
    "validator": "high_reasoning",
}
# AgentRuntime failure classifications, expressed in the committed session
# lifecycle's assignment-outcome vocabulary so the retirement policy stays in
# one module. A transport/timeout/permission failure is a provider failure; a
# schema failure is an output failure; the rest are neither and stay explicit.
FAILURE_ASSIGNMENT_OUTCOMES = {
    "provider_error": "provider_failure",
    "timeout": "provider_failure",
    "permission_denied": "provider_failure",
    "schema_error": "output_failure",
    "budget_exhausted": "other_failure",
    "invalid_request": "other_failure",
    "internal_error": "other_failure",
}


def crew_repository_identity(root: Path) -> str:
    """Return the repository this checkout actually points at.

    Pooled reuse crosses tasks and runs, so the repository identity may not be
    asserted by the caller alone: it is read from the checkout's configured
    origin and then required to equal both the scheduler-proven value and every
    lease. A checkout with no origin cannot prove which repository it is and is
    refused rather than assumed.
    """

    try:
        origin = git(root, "remote", "get-url", "origin", check=False).stdout.strip()
    except OSError as exc:
        raise CrewBlocked("source checkout repository identity could not be read") from exc
    if not origin:
        raise CrewBlocked(
            "pooled role session leases require a source checkout with a configured origin remote"
        )
    return origin


def validate_role_session_leases(role_session_leases: Mapping[str, Any]|None, *, task_id: str,
                                 run_id: str, provider_identifier: str, model: str|None,
                                 reasoning_effort: str|None, source_commit: str,
                                 checkout_identity: str, repository_identity: str,
                                 role_capability_classes: Mapping[str, str]|None=None,
                                 protocol_version: str=CREW_SESSION_PROTOCOL_VERSION,
                                 ) -> dict[str, AssignmentLease]:
    """Bind every supplied lease to this exact execution before any provider work.

    A lease is authority for one assignment only. Every identity this run can
    prove independently is required to match: task, worker run, role, provider,
    routed model and reasoning effort, the exact captured source commit, the
    exact source checkout, the scheduler-proven repository, the capability class
    this run will actually invoke that role with, and the crew/session protocol
    version. A human-review retry, another task, another checkout, another
    repository, a re-routed capability class, or a differently versioned crew can
    never silently inherit somebody else's warm conversation.
    """

    if not role_session_leases:
        return {}
    classes = ROLE_CAPABILITY_CLASSES if role_capability_classes is None else role_capability_classes
    leases: dict[str, AssignmentLease] = {}
    for role, lease in role_session_leases.items():
        if type(lease) is not AssignmentLease:
            raise CrewBlocked("role session lease must be an exact AssignmentLease")
        if lease.pool_schema_version != POOL_SCHEMA_VERSION:
            raise CrewBlocked("session lease pool schema version differs from this build")
        if lease.protocol_version != protocol_version:
            raise CrewBlocked(
                f"session lease speaks crew/session protocol {lease.protocol_version!r} "
                f"and cannot be used by protocol {protocol_version!r}"
            )
        if lease.role != role:
            raise CrewBlocked(
                f"session lease is bound to role {lease.role!r} and cannot be used for role {role!r}"
            )
        expected_class = classes.get(role)
        if expected_class is None:
            raise CrewBlocked(f"role {role!r} has no routed capability class for a pooled session")
        if lease.capability_class != expected_class:
            raise CrewBlocked(
                f"session lease is bound to capability class {lease.capability_class!r} "
                f"and cannot be used for {role!r}, which this run routes as {expected_class!r}"
            )
        if lease.task_id != task_id:
            raise CrewBlocked(
                f"session lease is bound to task {lease.task_id!r} and cannot be used for {task_id!r}"
            )
        if lease.worker_run_id != run_id:
            raise CrewBlocked(
                f"session lease is bound to worker run {lease.worker_run_id!r} and cannot be used for {run_id!r}"
            )
        if lease.provider_identifier != provider_identifier:
            raise CrewBlocked(
                f"session lease is bound to provider {lease.provider_identifier!r} "
                f"and cannot be used through {provider_identifier!r}"
            )
        if model is not None and lease.model != model:
            raise CrewBlocked("session lease model differs from this run's routed model")
        if lease.reasoning_effort != reasoning_effort:
            raise CrewBlocked("session lease reasoning effort differs from this run")
        if lease.source_commit != source_commit:
            raise CrewBlocked(
                f"session lease is bound to source commit {lease.source_commit} "
                f"and cannot be used at {source_commit}"
            )
        if lease.checkout_identity != checkout_identity:
            raise CrewBlocked(
                f"session lease is bound to source checkout {lease.checkout_identity!r} "
                f"and cannot be used from {checkout_identity!r}"
            )
        if lease.repository_identity != repository_identity:
            raise CrewBlocked(
                f"session lease is bound to repository {lease.repository_identity!r} "
                f"and cannot be used against {repository_identity!r}"
            )
        leases[role] = lease
    return leases


def role_result_artifact(role: str, attempt: int) -> str:
    """Return the exact run-relative path one role attempt's result is persisted at.

    The path is known before the bytes are written, so the durable assignment
    binding inside the artifact can name the artifact it lives in.
    """

    return f"role_results/{role}_{attempt}.json"


def write_role_result(run_dir: Path, role: str, attempt: int, record: Mapping[str, Any]) -> tuple[str, str]:
    """Persist one role result and return its exact run-relative path and SHA-256.

    Pooled reuse is decided against this artifact, so the bytes are written
    without newline translation and hashed exactly as written; a later reader on
    any platform must be able to recompute the same digest.
    """

    relative = role_result_artifact(role, attempt)
    payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (run_dir / relative).write_bytes(payload)
    return relative, hashlib.sha256(payload).hexdigest()


def role_assignment_decision(agent_status: str, failure_classification: str,
                             semantic_rejected: bool, changed_paths_rejected: bool
                             ) -> tuple[str, str]:
    """Return the exact (status, assignment_outcome) one role assignment reached.

    One definition serves both the binding written into the role artifact and the
    durable result the pool checks in, so the two can never disagree about what
    this assignment actually produced.
    """

    if agent_status != "succeeded":
        return "failed", FAILURE_ASSIGNMENT_OUTCOMES.get(failure_classification, "other_failure")
    if semantic_rejected or changed_paths_rejected:
        return "completed", "output_failure"
    return "completed", "completed"


def assert_pooled_provider_route(configuration: Any, registry: Mapping[str, Any], *, key: str,
                                 capability_class: str, lease: AssignmentLease) -> None:
    """Prove this invocation resolves exactly the lease's provider and routed model.

    A lease is authority for one conversation on one provider at one model, so the
    configuration this role is about to be invoked through is resolved by the one
    runtime resolver and required to name that exact provider and model. An
    injected provider factory is held to the identical rule: a pooled role can
    never be invoked through a provider or model its lease did not authorize.
    """

    if type(lease) is not AssignmentLease:
        raise CrewBlocked("a pooled invocation requires an exact AssignmentLease")
    resolve = getattr(configuration, "resolve", None)
    if resolve is None:
        raise CrewBlocked("pooled roles require an exact runtime configuration")
    try:
        selection = resolve(key, capability_class, registry)
    except ContractValidationError as exc:
        raise CrewBlocked(f"pooled provider configuration could not be resolved: {exc}") from exc
    if selection.provider != lease.provider_identifier:
        raise CrewBlocked(
            f"pooled {lease.role} configuration resolves provider {selection.provider!r}; "
            f"its lease authorizes {lease.provider_identifier!r}"
        )
    if selection.model != lease.model:
        raise CrewBlocked(
            f"pooled {lease.role} configuration resolves model {selection.model!r}; "
            f"its lease authorizes {lease.model!r}"
        )


def assert_pooled_result_identity(result: Any, *, lease: AssignmentLease) -> None:
    """Prove the AgentResult this pooled role produced names the lease's identity.

    ``AgentResult`` reports the provider and model AgentRuntime actually selected.
    Both must equal the lease. The single exception is the provider-neutral
    contract's pre-invocation ``invalid_request``, which reports no provider and
    no model precisely because nothing was invoked; that failure is recorded as a
    failure and can never become reusable evidence.
    """

    if (result.provider, result.model) in {
        (lease.provider_identifier, lease.model), (None, None),
    }:
        return
    raise CrewBlocked(
        f"pooled {lease.role} ran on provider {result.provider!r} model {result.model!r}; "
        f"its lease authorizes {lease.provider_identifier!r} {lease.model!r}"
    )


def assert_lease_invocation_identity(lease: AssignmentLease, *, role: str, capability_class: str,
                                     **identity: Any) -> None:
    """Re-prove one lease at the exact invocation that is about to use it.

    The routed capability class exists only at the invocation, so this is the
    boundary where the complete pooled identity is checked against the values
    the role is actually invoked with. It reuses the one lease validator rather
    than restating a second, drifting copy of those rules.
    """

    validate_role_session_leases(
        {role: lease}, role_capability_classes={role: capability_class}, **identity
    )


def durable_assignment_result(*, lease: AssignmentLease, confirmed: Any, crew_run_id: str,
                              artifact: str, artifact_sha256: str, agent_status: str,
                              failure_classification: str, semantic_rejected: bool,
                              changed_paths_rejected: bool) -> DurableAssignmentResult:
    """Return the durable evidence that this exact role assignment produced.

    A session becomes reusable only through this value. It repeats every lease
    identity, names the exact persisted role-result artifact and its SHA-256, and
    records both the deterministic changed-path decision and the semantic
    decision ExecutionCrew actually reached. A role whose AgentRuntime result
    failed, whose structured output was rejected, or whose actual changed paths
    were rejected can never report a reusable outcome from here.
    """

    if type(lease) is not AssignmentLease:
        raise CrewBlocked("durable role evidence requires an exact AssignmentLease")
    if type(confirmed) is not ProviderSessionConfirmation:
        raise CrewBlocked("durable role evidence requires an exact ProviderSessionConfirmation")
    status, outcome = role_assignment_decision(
        agent_status, failure_classification, semantic_rejected, changed_paths_rejected
    )
    try:
        return DurableAssignmentResult(
            schema_version=DURABLE_ASSIGNMENT_RESULT_SCHEMA_VERSION,
            pool_schema_version=lease.pool_schema_version,
            protocol_version=lease.protocol_version,
            lease_id=lease.lease_id,
            record_id=lease.record_id,
            crew_run_id=crew_run_id,
            task_id=lease.task_id,
            worker_run_id=lease.worker_run_id,
            worker_slot_id=lease.worker_slot_id,
            session_class=lease.session_class,
            role=lease.role,
            capability_class=lease.capability_class,
            provider_identifier=lease.provider_identifier,
            model=lease.model,
            reasoning_effort=lease.reasoning_effort,
            repository_identity=lease.repository_identity,
            source_commit=lease.source_commit,
            checkout_identity=lease.checkout_identity,
            status=status,
            assignment_outcome=outcome,
            semantic_validation="rejected" if semantic_rejected else "accepted",
            changed_path_validation="rejected" if changed_paths_rejected else "accepted",
            role_result_artifact=artifact,
            role_result_sha256=artifact_sha256,
            known_context_window_percent=None,
            latency_sample=None,
            confirmed_session=confirmed,
        )
    except SessionPoolError as exc:
        raise CrewBlocked(f"durable role evidence could not be built: {exc}") from exc


def repair_attempt_session(confirmed: Any) -> ProviderSessionBinding:
    """Return the binding this role's next attempt must invoke with.

    A repair attempt is the same assignment continuing, not a new one, so it
    resumes the exact conversation the previous attempt confirmed instead of
    opening a second provider session for the same role.
    """

    if type(confirmed) is not ProviderSessionConfirmation:
        raise CrewBlocked("repair continuity requires an exact ProviderSessionConfirmation")
    return confirmed.resume_binding()


def crew_provider_identifier(provider_name: str) -> str:
    if provider_name == "claude":
        return "claude-code"
    if provider_name == "codex":
        return "openai-codex"
    raise CrewBlocked("provider must be claude or codex")


def construct_real_provider(provider_name: str, repository_root: Path, writable: bool,
                            openai_reasoning_effort: str|None=None,
                            session: ProviderSessionBinding|None=None,
                            session_ledger: ProviderSessionLedger|None=None,
                            codex_resume_sandbox_argument: tuple[str,...]|None=None):
    if provider_name == "claude":
        # ExecutionCrew always wants live, human-readable Claude activity on
        # stderr while a real Claude-backed role is running. This is
        # ExecutionCrew-specific: other AgentRuntime callers that construct
        # ClaudeCodeProvider directly do not get an observer unless they ask.
        return ClaudeCodeProvider(repository_root=repository_root,
                                  externally_isolated_writable_repository=writable,
                                  live_observer=ClaudeLiveRenderer().feed,
                                  session=session, session_ledger=session_ledger)
    if provider_name == "codex":
        effort = openai_reasoning_effort or "high"
        if effort not in OPENAI_REASONING_EFFORTS:
            raise CrewBlocked("OpenAI reasoning effort is unsupported")
        return OpenAICodexProvider(
            repository_root=repository_root,
            externally_isolated_writable_repository=writable,
            externally_enforced_read_only_repository=not writable,
            reasoning_effort=effort,
            session=session, session_ledger=session_ledger,
            resume_sandbox_argument=codex_resume_sandbox_argument,
        )
    raise CrewBlocked("provider must be claude or codex")

def run_crew(*, source: Path, output_root: Path, task_id: str|None=None, provider_name: str|None=None,
             implementation_paths: tuple[str,...]=(), test_paths: tuple[str,...]=(),
             new_implementation_paths: tuple[str,...]=(), new_test_paths: tuple[str,...]=(), run_id: str|None=None,
             retry_run_id: str|None=None, review_feedback_file: Path|None=None, host_output_root: str|None=None,
             execution_model: str|None=None, openai_reasoning_effort: str|None=None,
             retry_expected_provider: str|None=None,
             provider_factory: ProviderFactory|None=None, _require_physical_read_only_source: bool=True,
             role_session_bindings: Mapping[str, ProviderSessionBinding]|None=None,
             role_session_leases: Mapping[str, AssignmentLease]|None=None,
             scheduler_repository_identity: str|None=None,
             codex_resume_sandbox_argument: tuple[str,...]|None=None,
             _persistent_work_graph_loader: Callable[[Path], PersistentWorkGraph]|None=None):
    started=time.monotonic()
    host_root_path = validate_host_output_root(host_output_root) if host_output_root is not None else None
    retry_mode = retry_run_id is not None
    if retry_mode and any((task_id is not None, provider_name is not None, implementation_paths, test_paths,
                           new_implementation_paths, new_test_paths)):
        raise CrewBlocked("retry mode inherits task, provider, and write paths; do not supply them explicitly")
    if not retry_mode and review_feedback_file is not None:
        raise CrewBlocked("--review-feedback-file is valid only with --retry-run")
    if not retry_mode and retry_expected_provider is not None:
        raise CrewBlocked("--expected-provider is valid only with --retry-run")
    if retry_mode and review_feedback_file is None:
        raise CrewBlocked("--review-feedback-file is required with --retry-run")
    if not retry_mode and (not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id)):
        raise CrewBlocked("task ID must match NSC-###")
    identity=capture_source(source); source_root=Path(identity.root).resolve(strict=True)
    if _require_physical_read_only_source:
        statvfs = getattr(os, "statvfs", None)
        st_rdonly = getattr(os, "ST_RDONLY", None)
        if statvfs is None or st_rdonly is None:
            raise CrewBlocked(
                "production source checkout must be physically mounted read-only; "
                "this platform cannot verify mount-level read-only state"
            )
        if not (statvfs(source_root).f_flag & st_rdonly):
            raise CrewBlocked("production source checkout must be physically mounted read-only")
    output_root = output_root.resolve()
    retry_context = None
    if retry_mode:
        assert retry_run_id is not None and review_feedback_file is not None
        retry_context = load_retry_context(
            source=source_root, identity=identity, output_root=output_root,
            prior_run_id=retry_run_id, feedback_file=review_feedback_file
        )
        if retry_expected_provider is not None and retry_expected_provider != retry_context.provider:
            raise CrewBlocked("routed retry provider differs from the prior run identity")
        if execution_model is not None:
            if retry_context.execution_model is None:
                raise CrewBlocked("prior run lacks execution model identity; routed retry cannot prove compatibility")
            if execution_model.strip() != retry_context.execution_model:
                raise CrewBlocked("routed retry model differs from the prior run identity")
        if openai_reasoning_effort is not None:
            if retry_context.execution_reasoning_effort is None:
                raise CrewBlocked("prior run lacks execution reasoning identity; routed retry cannot prove compatibility")
            if openai_reasoning_effort != retry_context.execution_reasoning_effort:
                raise CrewBlocked("routed retry reasoning effort differs from the prior run identity")
        task_id = retry_context.task_id
        provider_name = retry_context.provider
        execution_model = retry_context.execution_model or execution_model
        openai_reasoning_effort = retry_context.execution_reasoning_effort or openai_reasoning_effort
        implementation_paths = retry_context.implementation_paths
        test_paths = retry_context.test_paths
        new_implementation_paths = retry_context.new_implementation_paths
        new_test_paths = retry_context.new_test_paths
    assert task_id is not None
    if not TASK_ID_RE.fullmatch(task_id): raise CrewBlocked("task ID must match NSC-###")
    if not isinstance(provider_name, str): raise CrewBlocked("provider is required")
    if provider_name in ("claude","codex"):
        _, route_configuration = runtime_configuration(provider_name, execution_model)
        route_values = route_configuration.provider_configurations[
            "claude-crew" if provider_name=="claude" else "codex-crew"
        ]
        execution_model = route_values["models"]["standard"]
        if provider_name == "claude":
            if openai_reasoning_effort is not None: raise CrewBlocked("Claude execution does not support an explicit reasoning effort")
            execution_reasoning_effort = None
        else:
            execution_reasoning_effort = openai_reasoning_effort or "high"
            if execution_reasoning_effort not in OPENAI_REASONING_EFFORTS: raise CrewBlocked("OpenAI reasoning effort is unsupported")
    elif provider_factory is not None:
        execution_reasoning_effort = openai_reasoning_effort
    else:
        raise CrewBlocked("provider must be claude or codex")
    if role_session_bindings and role_session_leases:
        raise CrewBlocked("supply role session bindings or pooled leases, not both")
    if role_session_leases and run_id is None:
        raise CrewBlocked("pooled role session leases require the exact worker run ID")
    if role_session_leases and scheduler_repository_identity is None:
        raise CrewBlocked("pooled role session leases require the scheduler-proven repository identity")
    if scheduler_repository_identity is not None and not role_session_leases:
        raise CrewBlocked("a scheduler-proven repository identity is meaningful only with pooled leases")
    if not implementation_paths and not new_implementation_paths: raise CrewBlocked("at least one implementation path is required")
    if not test_paths and not new_test_paths: raise CrewBlocked("at least one test path is required for Stage 5B")
    interval=heartbeat_interval()
    run_id=run_id or f"{task_id.lower()}-{time.strftime('%Y%m%dt%H%M%Sz',time.gmtime())}"
    if not RUN_ID_RE.fullmatch(run_id): raise CrewBlocked("run ID must be one conservative path component")
    run_dir=output_root/run_id; run_dir.mkdir(parents=True,exist_ok=False)
    (run_dir/"role_results").mkdir()
    if retry_context is not None:
        (run_dir/"human_review_feedback.txt").write_bytes(retry_context.feedback_bytes)
    progress=ProgressReporter(run_dir/"progress.jsonl",run_id=run_id,task_id=task_id,provider=provider_name,started=started)
    progress.emit("run_started",f"ExecutionCrew started: {task_id} / {provider_name}")
    progress.emit("source_preflight_completed",f"Source preflight passed: HEAD {identity.head[:8]}",status="passed")
    if retry_context is not None:
        progress.emit(
            "human_review_retry_loaded", "Human-review retry evidence loaded",
            status="passed", prior_run_id=retry_context.prior_run_id,
            feedback_sha256=retry_context.feedback_sha256
        )
    task_raw=committed_bytes(source_root,identity.head,f"Tasks/{task_id}.yaml")
    task, contract_identity=parse_task(task_raw,task_id)
    if retry_context is not None and contract_identity != retry_context.prior_contract_identity:
        raise CrewBlocked(
            "current task contract identity differs from the prior review-ready candidate; "
            "start a new normal ExecutionCrew run"
        )
    expected_requirement_ids=tuple(
        [item["criterion_id"] for item in task["acceptance_criteria"]]
        + [item["gate_id"] for item in task["completion_gates"]]
    )
    task_text=task_raw.decode("utf-8-sig"); gdd=committed_bytes(source_root,identity.head,GDD_PATH).decode("utf-8-sig"); policy=committed_bytes(source_root,identity.head,POLICY_PATH).decode("utf-8-sig")
    graph_loader = _persistent_work_graph_loader or load_persistent_work_graph
    try:
        graph = graph_loader(source_root)
    except PersistentWorkGraphError as exc:
        raise CrewBlocked(f"persistent work graph: {exc}") from exc
    tasks_by_id=graph.tasks_by_id
    if tasks_by_id.get(task_id) != task:
        raise CrewBlocked("selected task contract is inconsistent with the validated persistent work graph")
    for dependency_id in task.get("depends_on") or ():
        if dependency_id not in tasks_by_id:
            raise CrewBlocked(f"selected task depends on a task missing from the persistent work graph: {dependency_id}")
    try:
        task_catalog=build_task_catalog(tasks_by_id)
    except ContractLocalityError as exc:
        raise CrewBlocked(str(exc)) from exc
    dependency_contracts=direct_dependency_contracts(task,tasks_by_id)
    dependent_contracts=direct_dependent_contracts(task_id,tasks_by_id)
    valid_task_ids=frozenset(tasks_by_id)
    impl_plan, test_plan = preflight_role_paths(
        source_root, identity.head, implementation_paths, new_implementation_paths,
        test_paths, new_test_paths,
    )
    implementation_paths, test_paths = impl_plan.requested_paths, test_plan.requested_paths
    impl_bounds = WriteBoundaries(implementation_paths, test_paths)
    test_bounds = WriteBoundaries(test_paths, implementation_paths)
    role_records=[]; reasons=[]; impl_actual=set(); test_actual=set(); pipeline_generated=set(); validator_status=None; attempts=0
    usage_invocations: list[dict[str, Any]] = []
    provider_session_records: list[dict[str, Any]] = []
    pooled_repository_identity = None
    if role_session_leases:
        # The repository is proven from the checkout itself and then required to
        # equal the scheduler's proven value, so neither the caller nor a lease
        # can assert an identity this execution cannot independently confirm.
        pooled_repository_identity = crew_repository_identity(source_root)
        if scheduler_repository_identity != pooled_repository_identity:
            raise CrewBlocked(
                f"scheduler-proven repository {scheduler_repository_identity!r} differs from "
                f"the source checkout's repository {pooled_repository_identity!r}"
            )
    pooled_leases = validate_role_session_leases(
        role_session_leases, task_id=task_id, run_id=run_id,
        provider_identifier=crew_provider_identifier(provider_name) if provider_name in ("claude","codex") else "",
        model=execution_model, reasoning_effort=execution_reasoning_effort,
        source_commit=identity.head, checkout_identity=identity.root,
        repository_identity=pooled_repository_identity or "",
    ) if role_session_leases else {}
    role_durable_results: dict[str, DurableAssignmentResult] = {}
    role_confirmations: dict[str, ProviderSessionConfirmation] = {}
    # One live binding per role. A pooled lease seeds it; every confirmed
    # invocation replaces it with a resume binding so the SAME role keeps the
    # SAME conversation across its repair attempt. No role is ever skipped
    # because its session happens to be warm.
    role_sessions: dict[str, ProviderSessionBinding] = {
        role: lease.session_binding() for role, lease in pooled_leases.items()
    }
    # A capsule is owed once per pooled assignment, on the first invocation that
    # actually reuses a warm conversation -- not on an intra-run repair attempt,
    # which is the same assignment continuing.
    capsule_owed: set[str] = {
        role for role, lease in pooled_leases.items() if lease.mode == "resume"
    }
    latest_impl={}; latest_test={}; candidate_path=None; diagnostic_path=None; accepted_candidate=None
    contract_locality_status=None; contract_locality_audit_path=None; contract_locality_audit_host_path=None
    crew_status=None; final_paths: list[str]=[]
    human_review_feedback = retry_context.feedback_text if retry_context is not None else None
    retry_seed_mode = None
    retry_seed_candidate_sha256 = retry_context.candidate_sha256 if retry_context is not None else None
    def record_role_result(role:str, attempt:int, record:dict, *, agent_status:str,
                           failure_classification:str, semantic_rejected:bool,
                           changed_paths_rejected:bool) -> tuple[str, str]:
        """Persist one role result and publish the durable evidence bound to it.

        A pooled role's artifact carries the complete assignment binding in its
        own persisted bytes -- crew run, lease, session record, task, worker run
        and slot, source commit, source checkout, repository, role, capability
        class, protocol, provider, routed model and reasoning, the exact provider
        confirmation, the outcome and both validation decisions, and the artifact
        path itself -- so durable evidence and its exact assignment are one
        object. Only a role that actually ran on a pooled lease publishes
        anything, and what it publishes always states its real AgentRuntime
        status and both validation decisions. A role that is never invoked --
        because the contract audit stopped the run, or an earlier role failed --
        leaves no evidence at all, so its lease can never be recycled on this
        run's word.
        """

        lease = pooled_leases.get(role)
        binding = None
        if lease is not None:
            confirmed = role_confirmations.get(role)
            if confirmed is None:
                raise CrewBlocked(
                    f"{role} ran on a pooled lease without a confirmed provider session identity"
                )
            status, outcome = role_assignment_decision(
                agent_status, failure_classification, semantic_rejected, changed_paths_rejected
            )
            try:
                binding = pooled_assignment_evidence(
                    lease=lease, confirmed=confirmed, crew_run_id=run_id,
                    artifact=role_result_artifact(role, attempt), status=status,
                    assignment_outcome=outcome,
                    semantic_validation="rejected" if semantic_rejected else "accepted",
                    changed_path_validation="rejected" if changed_paths_rejected else "accepted",
                )
            except SessionPoolError as exc:
                raise CrewBlocked(f"role assignment binding could not be built: {exc}") from exc
            record["pooled_assignment_evidence"] = binding
        artifact, artifact_sha256 = write_role_result(run_dir, role, attempt, record)
        if lease is None:
            return artifact, artifact_sha256
        result_value = durable_assignment_result(
            lease=lease, confirmed=role_confirmations[role], crew_run_id=run_id,
            artifact=artifact, artifact_sha256=artifact_sha256, agent_status=agent_status,
            failure_classification=failure_classification,
            semantic_rejected=semantic_rejected,
            changed_paths_rejected=changed_paths_rejected,
        )
        # The persisted binding and the durable result are built from the same
        # lease and the same decision, so any drift between the two constructions
        # is a defect here rather than an unprovable artifact at check-in.
        if result_value.role_evidence_binding() != binding:
            raise CrewBlocked(
                f"{role} durable evidence disagrees with the assignment binding it persisted"
            )
        role_durable_results[role] = result_value
        return artifact, artifact_sha256

    def invoke(role:str, attempt:int, repo:Path, writable:bool, prompt:str, schema:Mapping[str,Any], capability_class:str, boundaries:WriteBoundaries):
        invocation_id=f"{task_id.lower()}-{role.replace('_','-')}-{attempt}-{hashlib.sha256(run_id.encode()).hexdigest()[:12]}"
        caps=("repository_read","repository_search","repository_write") if writable else ("repository_read","repository_search")
        session_binding=None; session_ledger=None
        if provider_factory and role_session_bindings:
            raise CrewBlocked("provider session bindings require the real provider path")
        lease=pooled_leases.get(role)
        if lease is not None:
            # This is the real invocation boundary: the capability class is only
            # known here, so the complete pooled identity is re-proven against the
            # exact routed values this role is about to be invoked with.
            assert_lease_invocation_identity(
                lease, role=role, capability_class=capability_class, task_id=task_id,
                run_id=run_id, provider_identifier=crew_provider_identifier(provider_name),
                model=execution_model, reasoning_effort=execution_reasoning_effort,
                source_commit=identity.head, checkout_identity=identity.root,
                repository_identity=pooled_repository_identity or "",
            )
        if pooled_leases or role_session_bindings:
            session_binding=role_sessions.get(role) or resolve_role_session(
                role_session_bindings,role,crew_provider_identifier(provider_name)
            )
        if session_binding is not None:
            session_ledger=ProviderSessionLedger()
            if role in capsule_owed:
                # Remembered context must never widen current authority: the
                # capsule closes the previous assignment and restates the
                # complete authority this one actually has.
                capsule_owed.discard(role)
                try:
                    prompt = assignment_capsule(
                        pooled_leases[role], checkout_root=str(repo), capabilities=caps,
                        allowed_paths=boundaries.allowed_paths,
                        denied_paths=boundaries.denied_paths,
                        evidence_obligations=ROLE_EVIDENCE_OBLIGATIONS.get(role, ()),
                    ) + "\n\n" + prompt
                except SessionPoolError as exc:
                    raise CrewBlocked(f"assignment capsule could not be built: {exc}") from exc
        if provider_factory:
            # A four-argument factory keeps its historical ephemeral contract; a
            # pooled assignment must be handed the exact binding and ledger, so a
            # factory that cannot accept them is refused rather than silently
            # running the role without its conversation.
            if session_binding is None:
                key,config,registry=provider_factory(provider_name,repo,writable,role)
            else:
                try:
                    key,config,registry=provider_factory(
                        provider_name,repo,writable,role,session_binding,session_ledger
                    )
                except TypeError as exc:
                    raise CrewBlocked(
                        "pooled role sessions require a provider factory that accepts the "
                        f"session binding and ledger: {exc}"
                    ) from exc
        else:
            key,config=runtime_configuration(provider_name,execution_model)
            provider=construct_real_provider(
                provider_name,repo,writable,
                openai_reasoning_effort=execution_reasoning_effort,
                session=session_binding,session_ledger=session_ledger,
                codex_resume_sandbox_argument=codex_resume_sandbox_argument,
            )
            registry={provider.provider_identifier:provider}
        if lease is not None:
            # The real pooled invocation boundary. Whatever supplied the
            # configuration, the provider and model this role is about to be
            # invoked through must be exactly the ones its lease authorized.
            assert_pooled_provider_route(config,registry,key=key,
                                         capability_class=capability_class,lease=lease)
        inv=AgentInvocationRequest(AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,invocation_id,role,prompt,
            tuple(dict.fromkeys((f"Tasks/{task_id}.yaml",GDD_PATH,POLICY_PATH,ENGINEERING_STANDARDS_PATH,*implementation_paths,*test_paths))),caps,boundaries,schema,capability_class,
            Budgets(int(os.getenv(f"NSC_{role.upper()}_TURN_LIMIT","32")),float(os.getenv(f"NSC_{role.upper()}_TIMEOUT_SECONDS","1200"))),
            key)
        if key != inv.provider_configuration_key: raise CrewBlocked("provider factory configuration key changed")
        req=TaskExecutionRequest(TASK_EXECUTION_REQUEST_SCHEMA_VERSION,task_id,contract_identity,inv)
        display=role.replace("_"," ").title(); role_started=time.monotonic(); stopped=threading.Event()
        progress.emit("role_started",f"{display} {attempt} started",role=role,attempt=attempt)
        def heartbeat() -> None:
            while not stopped.wait(interval):
                elapsed=round(time.monotonic()-role_started,1)
                progress.emit("role_heartbeat",f"{display} {attempt} still running: {elapsed:g}s",role=role,attempt=attempt,duration_seconds=elapsed,status="running")
        thread=threading.Thread(target=heartbeat,name=f"execution-crew-{role}-heartbeat",daemon=True); thread.start()
        failure: BaseException|None=None; result=None
        try:
            result=TaskExecutionRunner(run_dir/"task_execution",AgentRunner(run_dir/"agent_runtime",config,registry)).run(req)
        except BaseException as exc:
            failure=exc
        finally:
            stopped.set(); thread.join()
        duration=round(time.monotonic()-role_started,3)
        if failure is not None:
            progress.emit("role_completed",f"{display} {attempt} completed: failed ({duration:.1f}s)",role=role,attempt=attempt,status="failed",duration_seconds=duration)
            raise failure
        assert result is not None
        if provider_factory is None and execution_model is not None and result.model != execution_model:
            raise CrewBlocked(
                f"AgentRuntime used model {result.model!r}; expected routed model {execution_model!r}"
            )
        if lease is not None:
            # The returned identity is proven against the lease as well, so the
            # provider and model this assignment reports are the ones it was
            # authorized to use rather than the ones it claims to have used.
            assert_pooled_result_identity(result,lease=lease)
        usage_invocations.append(
            {
                "role": role,
                "attempt": attempt,
                "run_id": result.run_id,
                "usage": result.usage,
            }
        )
        if session_ledger is not None:
            # The adapter records only an identity the provider transcript
            # actually proved, so a persistent role that reached here without a
            # confirmation is a contradiction rather than a silent ephemeral run.
            confirmed = session_ledger.confirmed
            if confirmed is None:
                raise CrewBlocked(
                    f"{role} requested a provider session but no confirmed session identity was proven"
                )
            provider_session_records.append(
                {
                    "role": role, "attempt": attempt, "run_id": result.run_id,
                    "lease_id": None if lease is None else lease.lease_id,
                    "worker_slot_id": None if lease is None else lease.worker_slot_id,
                    **confirmed.to_dict(),
                }
            )
            # A confirmed identity is not yet reusability: this role's durable
            # evidence is only published once its validations have been decided.
            # The assignment's own confirmation is the first one, which matches
            # the lease's start/resume decision; a repair attempt necessarily
            # resumes that same conversation and does not restate it.
            role_confirmations.setdefault(role, confirmed)
            # The same role's repair attempt must continue this exact
            # conversation rather than opening a second one.
            role_sessions[role] = repair_attempt_session(confirmed)
        progress.emit("role_completed",f"{display} {attempt} completed: {result.status} ({duration:.1f}s)",role=role,attempt=attempt,status=result.status,duration_seconds=duration)
        return inv,result
    locality_prompt=contract_locality_auditor_prompt(
        task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,
        execution_scope=str(task.get("execution_scope") or ""),execution_reason=str(task.get("execution_reason") or ""),
        decomposition_state=str(task.get("decomposition_state") or ""),decomposition_reason=str(task.get("decomposition_reason") or ""),
        dependency_contracts=dependency_contracts,dependent_contracts=dependent_contracts,
        task_catalog=task_catalog,source_head=identity.head,source_tree=identity.tree,
    )
    audit_inv,audit_res=invoke("contract_locality_auditor",1,source_root,False,locality_prompt,CONTRACT_LOCALITY_AUDITOR_OUTPUT_SCHEMA,"high_reasoning",WriteBoundaries((),()))
    audit_deterministic=source_revalidation(source_root,identity)
    audit_scope=list(audit_deterministic)
    audit_output=thaw_json(audit_res.structured_output) if audit_res.status=="succeeded" else {}
    audit_semantic=[]
    if audit_res.status!="succeeded": audit_scope.append(f"AgentResult failed: {audit_res.failure_classification}")
    else:
        audit_semantic=validate_locality_audit_output(audit_output,task=task,valid_task_ids=valid_task_ids)
        audit_scope += audit_semantic
    audit_record={"role":"contract_locality_auditor","attempt":1,"agent_status":audit_res.status,"failure_classification":audit_res.failure_classification,"structured_output":audit_output,"role_claimed_paths":[],"agent_runtime_claimed_paths":list(audit_res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":[],"scope_check_reasons":audit_scope,"deterministic_changed_path_validation":"rejected" if audit_deterministic else "accepted","semantic_validation":"rejected" if audit_semantic else "accepted","duration_seconds":audit_res.duration_seconds,"model":audit_res.model,"provider":audit_res.provider,"usage":None if audit_res.usage is None else audit_res.usage.to_dict()}
    record_role_result("contract_locality_auditor",1,audit_record,
                       agent_status=audit_res.status,failure_classification=audit_res.failure_classification,
                       semantic_rejected=bool(audit_semantic),changed_paths_rejected=bool(audit_deterministic))
    role_records.append("role_results/contract_locality_auditor_1.json")
    progress.emit("contract_locality_audit_completed",f"Contract Locality Auditor completed: {audit_output.get('status') if audit_res.status=='succeeded' else audit_res.status}",role="contract_locality_auditor",attempt=1,status=audit_output.get("status") if audit_res.status=="succeeded" else audit_res.status)
    if audit_scope:
        reasons += [f"contract locality auditor: {reason}" for reason in audit_scope]; crew_status="rejected"
    else:
        contract_locality_status=audit_output["status"]
        audit_artifact={"schema_version":CONTRACT_LOCALITY_AUDIT_SCHEMA_VERSION,"run_id":run_id,"task_id":task_id,"provider":provider_name,"source_head":identity.head,"source_tree":identity.tree,"task_contract_identity":contract_identity.to_dict(),"result":audit_output}
        (run_dir/"contract_locality_audit.json").write_text(json.dumps(audit_artifact,indent=2,sort_keys=True)+"\n")
        contract_locality_audit_path=str(run_dir/"contract_locality_audit.json")
        contract_locality_audit_host_path=str(host_root_path/run_id/"contract_locality_audit.json") if host_root_path is not None else None
        if contract_locality_status=="contract_review_required": crew_status="contract_review_required"
    if crew_status is None:
        with tempfile.TemporaryDirectory(prefix="nsc-execution-crew-") as temporary:
            clone=clone_exact(source_root,identity.head,Path(temporary))
            progress.emit("clone_completed","Disposable clone ready",status="passed")
            baseline_clone=snapshot(clone)
            retry_seed_snapshot = None
            if retry_context is not None:
                retry_seed_mode = seed_retry_candidate(clone, baseline_clone, retry_context)
                if retry_seed_mode == "applied":
                    pipeline_generated.update(retry_context.candidate_sidecars)
                retry_seed_snapshot = snapshot(clone)
                progress.emit(
                    "human_review_candidate_seeded",
                    f"Prior review-ready candidate seed verified: {retry_seed_mode}",
                    status="passed",
                    prior_run_id=retry_context.prior_run_id,
                    candidate_sha256=retry_context.candidate_sha256,
                    seed_mode=retry_seed_mode,
                )
            stop=False
            for attempt in (1,2):
                attempts=attempt
                progress.emit("attempt_started",f"Attempt {attempt}/2 started",attempt=attempt)
                if attempt==2: progress.emit("repair_cycle_started","Repair cycle started",attempt=attempt)
                repair_actual=set()
                findings=None if attempt==1 else latest_validator.get("blocking_issues",[])
                before=snapshot(clone)
                inv,res=invoke("implementer",attempt,clone,True,implementer_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,implementation_paths=impl_plan.existing_paths,new_implementation_paths=impl_plan.new_paths,pipeline_sidecars=impl_plan.pipeline_generated_sidecars,other_role_paths=test_paths,findings=findings,human_review_feedback=human_review_feedback),IMPLEMENTER_OUTPUT_SCHEMA,"standard",impl_bounds)
                after=snapshot(clone); actual,scope=incremental_check(before,after,inv,require_change=(attempt==1 and retry_context is None)); scope+=source_revalidation(source_root,identity)
                deterministic_scope=list(scope)
                raw_output=thaw_json(res.structured_output) if res.status=="succeeded" else {}
                output,normalized_discarded=normalize_role_structured_output("implementer",raw_output)
                blockers=normalized_agent_blockers(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
                generated=[]
                if not scope and not blockers:
                    for new_path, sidecar in zip(impl_plan.new_paths, (_sidecar(path) for path in impl_plan.new_paths)):
                        if before.entries.get(new_path) is None and after.entries.get(new_path) == _entry_state(clone/new_path, tracked=False) and sidecar:
                            (clone/sidecar).write_bytes(unity_meta_bytes(new_path)); generated.append(sidecar); pipeline_generated.add(sidecar)
                record={"role":"implementer","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":normalized_agent_claimed_paths(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"pipeline_generated_paths":generated,"scope_check_reasons":scope,"deterministic_changed_path_validation":"rejected" if deterministic_scope else "accepted","semantic_validation":"rejected" if blockers else "accepted","duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider,"usage":None if res.usage is None else res.usage.to_dict(),**_normalization_audit_fields(normalized_discarded)}
                record_role_result("implementer",attempt,record,agent_status=res.status,
                                   failure_classification=res.failure_classification,
                                   semantic_rejected=bool(blockers),changed_paths_rejected=bool(deterministic_scope))
                role_records.append(f"role_results/implementer_{attempt}.json"); impl_actual.update(actual); latest_impl=output
                progress.emit("scope_check_completed",f"Implementer {attempt} scope check {'passed' if not scope else 'failed'}: {len(actual)} changed paths",role="implementer",attempt=attempt,status="passed" if not scope else "failed",changed_paths=actual,changed_path_count=len(actual))
                if attempt==2: repair_actual.update(actual)
                if blockers or scope: reasons += [*(f"implementer blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
                impl_new_surface=tuple(sorted((*impl_plan.new_paths, *impl_plan.pipeline_generated_sidecars)))
                impl_patch=paths_patch(clone,identity.head,implementation_paths,impl_new_surface).decode("utf-8","replace")
                before=snapshot(clone)
                inv,res=invoke("test_author",attempt,clone,True,test_author_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,policy=policy,implementation_patch=impl_patch,implementation_paths=implementation_paths,implementation_actual_paths=sorted(impl_actual),test_paths=test_plan.existing_paths,new_test_paths=test_plan.new_paths,pipeline_sidecars=test_plan.pipeline_generated_sidecars,findings=findings,human_review_feedback=human_review_feedback),TEST_AUTHOR_OUTPUT_SCHEMA,"low_cost",test_bounds)
                # An existing authoritative test may already prove the new production
                # behavior.  The independent Test Author must inspect it, but should
                # not be forced to churn that file merely to satisfy a non-empty diff.
                # New test paths remain an explicit creation obligation.
                after=snapshot(clone); actual,scope=incremental_check(
                    before,
                    after,
                    inv,
                    require_change=(
                        attempt == 1
                        and retry_context is None
                        and bool(test_plan.new_paths)
                    ),
                ); scope+=source_revalidation(source_root,identity)
                deterministic_scope=list(scope)
                raw_output=thaw_json(res.structured_output) if res.status=="succeeded" else {}
                output,normalized_discarded=normalize_role_structured_output("test_author",raw_output)
                blockers=normalized_agent_blockers(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
                generated=[]
                if not scope and not blockers:
                    for new_path, sidecar in zip(test_plan.new_paths, (_sidecar(path) for path in test_plan.new_paths)):
                        if before.entries.get(new_path) is None and after.entries.get(new_path) == _entry_state(clone/new_path, tracked=False) and sidecar:
                            (clone/sidecar).write_bytes(unity_meta_bytes(new_path)); generated.append(sidecar); pipeline_generated.add(sidecar)
                record={"role":"test_author","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":normalized_agent_claimed_paths(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"pipeline_generated_paths":generated,"scope_check_reasons":scope,"deterministic_changed_path_validation":"rejected" if deterministic_scope else "accepted","semantic_validation":"rejected" if blockers else "accepted","duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider,"usage":None if res.usage is None else res.usage.to_dict(),**_normalization_audit_fields(normalized_discarded)}
                record_role_result("test_author",attempt,record,agent_status=res.status,
                                   failure_classification=res.failure_classification,
                                   semantic_rejected=bool(blockers),changed_paths_rejected=bool(deterministic_scope))
                role_records.append(f"role_results/test_author_{attempt}.json"); test_actual.update(actual); latest_test=output
                progress.emit("scope_check_completed",f"Test Author {attempt} scope check {'passed' if not scope else 'failed'}: {len(actual)} changed paths",role="test_author",attempt=attempt,status="passed" if not scope else "failed",changed_paths=actual,changed_path_count=len(actual))
                if attempt==2: repair_actual.update(actual)
                if blockers or scope: reasons += [*(f"test author blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
                if (retry_context is not None and attempt==1 and retry_seed_snapshot is not None
                        and not changed_paths(retry_seed_snapshot, snapshot(clone))):
                    reasons.append("human-review retry made no deterministic correction")
                    crew_status="needs_human"; stop=True; break
                if attempt==2 and not repair_actual:
                    reasons.append("repair cycle made no deterministic changes"); crew_status="needs_human"; stop=True; break
                new_surface=tuple(sorted((*impl_plan.new_paths, *test_plan.new_paths, *pipeline_generated)))
                candidate=full_patch(clone,identity.head,new_surface); final_paths=changed_paths(baseline_clone,snapshot(clone))
                inv,res=invoke("validator",attempt,source_root,False,validator_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,candidate_patch=candidate.decode("utf-8","replace"),changed_paths=final_paths,implementer_output=latest_impl,test_author_output=latest_test,human_review_feedback=human_review_feedback),VALIDATOR_OUTPUT_SCHEMA,"high_reasoning",WriteBoundaries((),()))
                scope=source_revalidation(source_root,identity)
                deterministic_scope=list(scope)
                raw_output=thaw_json(res.structured_output) if res.status=="succeeded" else {}
                output,normalized_discarded=normalize_role_structured_output("validator",raw_output)
                validator_status=output.get("status")
                validator_semantic=[]
                if res.status!="succeeded": scope.append(f"AgentResult failed: {res.failure_classification}")
                else:
                    validator_semantic=validator_semantic_reasons(output, expected_requirement_ids)
                    scope += validator_semantic
                record={"role":"validator","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":[],"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":[],"scope_check_reasons":scope,"deterministic_changed_path_validation":"rejected" if deterministic_scope else "accepted","semantic_validation":"rejected" if validator_semantic else "accepted","duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider,"usage":None if res.usage is None else res.usage.to_dict(),**_normalization_audit_fields(normalized_discarded)}
                record_role_result("validator",attempt,record,agent_status=res.status,
                                   failure_classification=res.failure_classification,
                                   semantic_rejected=bool(validator_semantic),changed_paths_rejected=bool(deterministic_scope))
                role_records.append(f"role_results/validator_{attempt}.json"); latest_validator=output
                progress.emit("validator_completed",f"Validator {attempt} completed: {validator_status or res.status}",role="validator",attempt=attempt,status=validator_status or res.status)
                if scope: reasons+=scope; crew_status="rejected"; stop=True; break
                if validator_status=="pass": crew_status="review_ready"; accepted_candidate=candidate; stop=True; break
                if validator_status=="blocked_by_design":
                    reasons.append("validator blocked_by_design")
                    crew_status="contract_review_required" if validator_requires_contract_review(output) else "blocked"
                    stop=True; break
                if validator_status!="needs_changes": reasons.append("validator returned invalid status"); crew_status="rejected"; stop=True; break
                if attempt==2: reasons.append("second validator pass still needs changes"); crew_status="needs_human"; stop=True; break
            final_snap=snapshot(clone); final_paths=changed_paths(baseline_clone,final_snap)
            final_reasons=[]
            if final_snap.head!=baseline_clone.head or final_snap.head!=identity.head: final_reasons.append("final clone HEAD differs from clone/source baseline HEAD")
            if final_snap.index!=baseline_clone.index: final_reasons.append("final clone index differs from clone baseline index")
            allowed=set(implementation_paths)|set(test_paths)|pipeline_generated
            final_reasons += [f"final changed path outside crew boundaries: {p}" for p in final_paths if p not in allowed]
            if (crew_status=="review_ready" and retry_context is None
                    and not (set(final_paths)&set(implementation_paths))):
                final_reasons.append("final candidate has no implementation change")
            if (crew_status=="review_ready" and retry_context is None
                    and test_plan.new_paths
                    and not (set(final_paths)&set(test_plan.new_paths))):
                final_reasons.append("final candidate has no test change")
            if crew_status=="review_ready" and retry_context is not None and not final_paths:
                final_reasons.append("final retry candidate has no change relative to current source HEAD")
            if (crew_status=="review_ready" and retry_context is not None
                    and retry_seed_snapshot is not None
                    and not changed_paths(retry_seed_snapshot, final_snap)):
                final_reasons.append(
                    "final human-review retry has no deterministic correction relative to seeded candidate"
                )
            if crew_status=="review_ready" and not accepted_candidate: final_reasons.append("final candidate patch is empty")
            present_new = {
                path for path in (*impl_plan.new_paths, *test_plan.new_paths, *pipeline_generated)
                if final_snap.entries.get(path) is not None and final_snap.entries[path].kind == "regular"
            }
            expected_diff_paths=sorted(set(diff_paths(clone,identity.head)) | present_new)
            if crew_status=="review_ready" and expected_diff_paths!=final_paths: final_reasons.append("final Git diff paths differ from deterministic changed paths")
            if crew_status=="review_ready" and accepted_candidate is not None:
                try: verify_patch_applies(source_root, accepted_candidate)
                except CrewBlocked as exc: final_reasons.append(str(exc))
            final_reasons += source_revalidation(source_root,identity)
            if final_reasons:
                reasons+=final_reasons; crew_status="rejected"
            if crew_status=="review_ready":
                if accepted_candidate is None: raise CrewBlocked("review-ready result has no accepted candidate bytes")
                (run_dir/"candidate.patch").write_bytes(accepted_candidate); candidate_path=str(run_dir/"candidate.patch")
            if crew_status!="review_ready":
                diagnostic=full_patch(clone,identity.head,tuple(sorted((*impl_plan.new_paths, *test_plan.new_paths, *pipeline_generated))))
                if diagnostic: (run_dir/"workspace_diagnostic.patch").write_bytes(diagnostic); diagnostic_path=str(run_dir/"workspace_diagnostic.patch")
    review_origin = None if retry_context is None else {
        "prior_run_id":retry_context.prior_run_id,
        "result":"human_rejected",
        "feedback_artifact":"human_review_feedback.txt",
        "feedback_sha256":retry_context.feedback_sha256,
    }
    host_candidate_path = str(host_root_path/run_id/"candidate.patch") if host_root_path is not None and candidate_path else None
    host_diagnostic_path = str(host_root_path/run_id/"workspace_diagnostic.patch") if host_root_path is not None and diagnostic_path else None
    human_status = {"review_ready":"REVIEW_READY","blocked":"BLOCKED","rejected":"REJECTED","needs_human":"NEEDS_HUMAN","contract_review_required":"CONTRACT_REVIEW_REQUIRED"}[crew_status]
    if crew_status=="review_ready":
        human_reason = "The candidate passed semantic crew review and awaits human review."
        human_artifact = host_candidate_path or candidate_path
        human_next_action = "Review candidate.patch; apply manually only if approved."
        human_commands = patch_commands(human_artifact, applyable=True)
    elif crew_status=="contract_review_required":
        human_reason = ("The committed task contract contains one or more AC/VAL items that are not locally "
                         "implementable/provable under its current scope or dependencies.")
        human_next_action = ("Review the audit, repair the task contract through normal human-reviewed TaskGraph "
                              "workflow, validate the graph, and rerun ExecutionCrew.")
        if contract_locality_status=="contract_review_required":
            # Primary path: the mandatory pre-Implementer audit itself caught the defect; no clone or
            # patch was ever produced, so the only artifact is the audit's own structured record.
            human_artifact = contract_locality_audit_host_path or contract_locality_audit_path
            human_commands = audit_commands(human_artifact)
        else:
            # Fallback path: the audit passed, but the Validator later caught the same defect class after
            # writers already ran; any retained tracked-file movement is diagnostic only, never a candidate.
            human_artifact = host_diagnostic_path or diagnostic_path
            human_commands = patch_commands(human_artifact, applyable=False)
    else:
        human_reason = safe_human_reason(reasons)
        if diagnostic_path:
            human_artifact = host_diagnostic_path or diagnostic_path
            human_next_action = "Inspect the diagnostic patch and blocking reason; no candidate was approved."
        else:
            human_artifact = None
            human_next_action = "Inspect the blocking reason; no diagnostic patch was produced."
        human_commands = patch_commands(human_artifact, applyable=False)
    human_result = {"status":human_status,"reason":human_reason,"artifact_path":human_artifact,"next_action":human_next_action,"commands":human_commands}
    # Every pooled lease this run held is reported, including roles that were
    # never invoked, so a scheduler can return an unused lease deliberately
    # instead of inferring anything from silence. Durable evidence exists only
    # for a role that actually ran, and only an outcome that AgentRuntime,
    # semantic validation, and the deterministic changed-path check all accepted
    # advertises a reusable conversation.
    pooled_lease_records = {
        role: {
            **lease.to_dict(),
            "invoked": role in role_durable_results,
            "durable_assignment_result": (
                None if role not in role_durable_results
                else role_durable_results[role].to_dict()
            ),
        }
        for role, lease in pooled_leases.items()
    }
    durable_result_records = {
        role: result_value.to_dict() for role, result_value in role_durable_results.items()
    }
    reusable_role_sessions = {
        role: result_value.confirmed_session.session_id
        for role, result_value in role_durable_results.items()
        if result_value.is_reusable
    }
    result={"schema_version":"1.0","run_id":run_id,"task_id":task_id,"task_contract_identity":contract_identity.to_dict(),"source_head":identity.head,"source_tree":identity.tree,"source_branch":identity.branch,"provider":provider_name,"execution_model":execution_model,"execution_reasoning_effort":execution_reasoning_effort,"crew_status":crew_status,"attempts_used":attempts,"requested_implementation_paths":list(implementation_paths),"requested_test_paths":list(test_paths),"requested_existing_implementation_paths":list(impl_plan.existing_paths),"requested_new_implementation_paths":list(impl_plan.new_paths),"requested_existing_test_paths":list(test_plan.existing_paths),"requested_new_test_paths":list(test_plan.new_paths),"pipeline_generated_paths":sorted(pipeline_generated),"implementation_actual_changed_paths":sorted(impl_actual-pipeline_generated),"test_actual_changed_paths":sorted(test_actual-pipeline_generated),"final_actual_changed_paths":final_paths,"role_results":role_records,"token_usage":aggregate_token_usage(usage_invocations),"provider_sessions":provider_session_records,"pooled_role_leases":pooled_lease_records,"durable_assignment_results":durable_result_records,"reusable_role_sessions":reusable_role_sessions,"candidate_patch_path":candidate_path,"candidate_patch_sha256":(hashlib.sha256(accepted_candidate).hexdigest() if crew_status=="review_ready" and accepted_candidate is not None else None),"retry_seed_candidate_sha256":retry_seed_candidate_sha256,"retry_seed_mode":retry_seed_mode,"workspace_diagnostic_patch_path":diagnostic_path,"candidate_patch_host_path":host_candidate_path,"workspace_diagnostic_patch_host_path":host_diagnostic_path,"contract_locality_status":contract_locality_status,"contract_locality_audit_path":contract_locality_audit_path,"contract_locality_audit_host_path":contract_locality_audit_host_path,"rejection_reasons":reasons,"validator_status":validator_status,"review_origin":review_origin,"human_next_step":human_next_action,"human_result":human_result,"duration_seconds":time.monotonic()-started}
    (run_dir/"crew_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    progress.emit("run_completed",f"ExecutionCrew completed: {crew_status}",status=crew_status,duration_seconds=round(result["duration_seconds"],3))
    return result

def print_human_summary(result: Mapping[str, Any]) -> None:
    """Concise human-facing summary on stderr; stdout stays reserved for machine-readable result JSON.
    REVIEW_READY gets copy/paste-ready find/check/apply/verify commands for the exact candidate patch
    path; a blocked/rejected diagnostic artifact only ever gets a find command, never apply/check."""
    human = result.get("human_result")
    if not isinstance(human, Mapping):
        return
    status = human.get("status")
    lines = [f"RESULT: {status}"]
    if status != "REVIEW_READY" and human.get("reason") is not None:
        lines.append(f"WHY: {human.get('reason')}")
    lines.append(f"ARTIFACT: {human.get('artifact_path') or 'none'}")
    commands = human.get("commands")
    find_command = commands.get("find") if isinstance(commands, Mapping) else None
    if status == "REVIEW_READY" and find_command:
        lines += ["", "FIND PATCH:", find_command]
        lines += ["", "CHECK PATCH:", commands.get("check")]
        lines += ["", "APPLY PATCH:", commands.get("apply")]
        verify_command = commands.get("verify")
        lines += ["", "VERIFY:", *(verify_command.split("; ") if verify_command else [])]
        lines.append("")
    elif status == "CONTRACT_REVIEW_REQUIRED" and find_command and isinstance(commands, Mapping) and commands.get("inspect") is not None:
        # No patch exists in this result: the mandatory pre-Implementer audit itself stopped the run.
        lines += ["", "FIND AUDIT:", find_command]
        lines += ["", "INSPECT AUDIT:", commands.get("inspect")]
        lines.append("")
    elif status != "REVIEW_READY" and find_command:
        lines += ["", "FIND DIAGNOSTIC PATCH:", find_command]
        lines += ["", "DO NOT APPLY:", "This is diagnostic work from a non-review-ready run, not an approved candidate."]
        lines.append("")
    lines.append(f"NEXT: {human.get('next_action')}")
    print("\n".join(lines), file=sys.stderr, flush=True)

def blocked_human_result(reason: str) -> dict[str, Any]:
    """Footer payload for an orchestration failure caught before any crew_result.json exists.
    There is never a candidate or diagnostic artifact on this path."""
    return {
        "status": "BLOCKED",
        "reason": reason,
        "artifact_path": None,
        "next_action": "Resolve the blocking condition and rerun ExecutionCrew.",
        "commands": patch_commands(None, applyable=False),
    }

def main():
    default_output_root=Path(os.environ["NSC_EXECUTION_OUTPUT_ROOT"]) if os.getenv("NSC_EXECUTION_OUTPUT_ROOT") else ROOT/"Pipeline/ExecutionCrew/outputs"
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id")
    parser.add_argument("--provider",choices=("claude","codex"))
    parser.add_argument("--expected-provider",choices=("claude","codex"))
    parser.add_argument("--model")
    parser.add_argument("--openai-reasoning-effort",choices=OPENAI_REASONING_EFFORTS)
    parser.add_argument("--implementation-path",action="append")
    parser.add_argument("--test-path",action="append")
    parser.add_argument("--new-implementation-path",action="append")
    parser.add_argument("--new-test-path",action="append")
    parser.add_argument("--retry-run")
    parser.add_argument("--review-feedback-file",type=Path)
    parser.add_argument("--source",type=Path,default=ROOT)
    parser.add_argument("--output-root",type=Path,default=default_output_root)
    parser.add_argument("--host-output-root",help="Human-facing HOST (e.g. Windows) absolute path mirroring --output-root, for display only")
    args=parser.parse_args()
    host_output_root=args.host_output_root if args.host_output_root is not None else os.getenv("NSC_EXECUTION_HOST_OUTPUT_ROOT")
    if args.retry_run:
        if any((args.task_id, args.provider, args.implementation_path, args.test_path,
                args.new_implementation_path, args.new_test_path)):
            parser.error("--retry-run inherits task, provider, and write paths; do not supply them")
        if args.review_feedback_file is None:
            parser.error("--review-feedback-file is required with --retry-run")
    else:
        if args.expected_provider is not None:
            parser.error("--expected-provider requires --retry-run")
        missing = [name for name, value in (
            ("--task-id", args.task_id), ("--provider", args.provider),
            ("implementation path", (args.implementation_path or []) + (args.new_implementation_path or [])),
            ("test path", (args.test_path or []) + (args.new_test_path or []))
        ) if not value]
        if missing:
            parser.error("normal mode requires " + ", ".join(missing))
        if args.review_feedback_file is not None:
            parser.error("--review-feedback-file requires --retry-run")
    try: result=run_crew(source=args.source,output_root=args.output_root,task_id=args.task_id,provider_name=args.provider,implementation_paths=tuple(args.implementation_path or ()),test_paths=tuple(args.test_path or ()),new_implementation_paths=tuple(args.new_implementation_path or ()),new_test_paths=tuple(args.new_test_path or ()),retry_run_id=args.retry_run,review_feedback_file=args.review_feedback_file,host_output_root=host_output_root,execution_model=args.model,openai_reasoning_effort=args.openai_reasoning_effort,retry_expected_provider=args.expected_provider)
    except (CrewBlocked,ValueError,OSError,subprocess.CalledProcessError) as exc:
        reason=str(exc)
        print(f"ExecutionCrew blocked: {reason}",file=sys.stderr)
        print_human_summary({"human_result":blocked_human_result(reason)})
        return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    print_human_summary(result)
    return 0 if result["crew_status"]=="review_ready" else 1
if __name__=="__main__": raise SystemExit(main())
