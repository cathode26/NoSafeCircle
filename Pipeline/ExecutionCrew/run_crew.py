#!/usr/bin/env python3
"""Run the minimum production ExecutionCrew for one human-selected task."""
from __future__ import annotations

import argparse, hashlib, json, math, os, re, stat, subprocess, sys, tempfile, threading, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[2]
for module_root in (ROOT, ROOT / "Pipeline/TaskGraph"):
    if str(module_root) not in sys.path: sys.path.insert(0, str(module_root))

from Pipeline.AgentRuntime.agent_runner import AgentRunner
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import AGENT_INVOCATION_REQUEST_SCHEMA_VERSION, AgentInvocationRequest, Budgets, WriteBoundaries, validate_repository_path
from Pipeline.AgentRuntime.providers.claude_code import ClaudeCodeProvider
from Pipeline.AgentRuntime.providers.openai_codex import OpenAICodexProvider
from Pipeline.AgentRuntime.json_values import thaw_json
from Pipeline.TaskExecution.contracts import TASK_EXECUTION_REQUEST_SCHEMA_VERSION, TaskContractIdentity, TaskExecutionRequest
from Pipeline.TaskExecution.task_runner import TaskExecutionRunner
from Pipeline.ExecutionCrew.prompts import implementer_prompt, test_author_prompt, validator_prompt
from Pipeline.ExecutionCrew.schemas import IMPLEMENTER_OUTPUT_SCHEMA, TEST_AUTHOR_OUTPUT_SCHEMA, VALIDATOR_OUTPUT_SCHEMA, SourceIdentity
from work_graph_validate import WorkGraphValidationError, _validate_v2_task

TASK_ID_RE = re.compile(r"^NSC-[0-9]{3}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
GDD_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
POLICY_PATH = "Docs/Engineering/UNITY_TESTING_POLICY.md"
MAX_REVIEW_FEEDBACK_BYTES = 64 * 1024

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
    task_id: str
    provider: str
    implementation_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    feedback_bytes: bytes
    feedback_text: str
    feedback_sha256: str

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
    validator_count = 0
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
        elif invocation.role != "validator":
            raise CrewBlocked(f"unexpected prior TaskExecution role: {invocation.role}")
        elif invocation.write_boundaries.allowed_paths or invocation.write_boundaries.denied_paths:
            raise CrewBlocked("prior Validator unexpectedly had write authority")
        else:
            validator_count += 1
    if not validator_count:
        raise CrewBlocked("prior Validator TaskExecution request artifact is missing")
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
    source_head = prior.get("source_head")
    source_tree = prior.get("source_tree")
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        raise CrewBlocked("prior crew_result.json has an invalid task_id")
    if provider not in ("claude", "codex"):
        raise CrewBlocked("prior crew_result.json has an invalid provider")
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
        prior_run_id, task_id, provider, implementation_paths, test_paths,
        feedback_bytes, feedback_text, hashlib.sha256(feedback_bytes).hexdigest()
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

def runtime_configuration(provider: str):
    if provider == "claude": key, identifier, model = "claude-crew", "claude-code", os.getenv("NSC_CLAUDE_MODEL", "claude-sonnet-5")
    elif provider == "codex": key, identifier, model = "codex-crew", "openai-codex", os.getenv("NSC_OPENAI_CODEX_MODEL", "gpt-5.6-sol")
    else: raise CrewBlocked("provider must be claude or codex")
    return key, RuntimeConfiguration({key:{"provider":identifier,"models":{"low_cost":model,"standard":model,"high_reasoning":model}}})

@dataclass(frozen=True)
class Snapshot:
    head: str; index: bytes; untracked: tuple[str, ...]; tracked: Mapping[str, str]

def snapshot(root: Path) -> Snapshot:
    paths = [p.decode("utf-8", "surrogateescape") for p in git(root, "ls-files", "-z", text=False).stdout.split(b"\0") if p]
    tracked = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths if (root / p).is_file()}
    index = git(root, "ls-files", "--stage", "-z", text=False).stdout
    untracked = tuple(sorted(p.decode("utf-8", "surrogateescape") for p in git(root, "ls-files", "--others", "-z", text=False).stdout.split(b"\0") if p))
    return Snapshot(git(root, "rev-parse", "HEAD").stdout.strip(), index, untracked, tracked)

def incremental_check(before: Snapshot, after: Snapshot, invocation: AgentInvocationRequest, *, require_change: bool):
    reasons=[]
    if after.head != before.head: reasons.append("clone HEAD changed")
    if after.index != before.index: reasons.append("Git index changed")
    for path in sorted(set(after.untracked)-set(before.untracked)): reasons.append(f"untracked file: {path}")
    deleted=sorted(set(before.tracked)-set(after.tracked))
    reasons += [f"tracked file deleted/renamed: {p}" for p in deleted]
    actual=sorted(p for p in set(before.tracked)&set(after.tracked) if before.tracked[p] != after.tracked[p])
    actual += sorted(set(after.tracked)-set(before.tracked))
    actual=sorted(set(actual))
    for path in actual:
        if not invocation.is_path_writable(path): reasons.append(f"incremental changed path outside role WriteBoundaries: {path}")
    if require_change and not actual: reasons.append("role made no required tracked-file modification")
    return actual, reasons

def changed_paths(baseline: Snapshot, final: Snapshot) -> list[str]:
    """Return tracked additions, deletions, and byte changes relative to one clone baseline."""
    return sorted(path for path in set(baseline.tracked) | set(final.tracked)
                  if baseline.tracked.get(path) != final.tracked.get(path))

def preflight_role_paths(baseline: Snapshot, implementation_paths: tuple[str, ...], test_paths: tuple[str, ...]) -> None:
    def folded(path: str) -> tuple[str, ...]:
        return tuple(part.casefold() for part in path.split("/"))
    implementation_keys = [folded(path) for path in implementation_paths]
    test_keys = [folded(path) for path in test_paths]
    if len(set(implementation_keys)) != len(implementation_keys):
        raise CrewBlocked("duplicate implementation role path")
    if len(set(test_keys)) != len(test_keys):
        raise CrewBlocked("duplicate test role path")
    overlap = set(implementation_keys) & set(test_keys)
    if overlap:
        raise CrewBlocked("implementation and test role paths must be disjoint")
    tracked_keys = {folded(path) for path in baseline.tracked}
    for role, paths in (("implementation", implementation_paths), ("test", test_paths)):
        for path in paths:
            if folded(path) not in tracked_keys:
                raise CrewBlocked(f"{role} role path must be an existing tracked file: {path}")

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
    blocking = bool(output.get("blocking_issues"))
    if status == "pass" and failed: reasons.append("validator pass contains a failed criterion")
    if status == "pass" and blocking: reasons.append("validator pass contains blocking issues")
    if status == "needs_changes" and not (failed or blocking):
        reasons.append("validator needs_changes requires a failed criterion or blocking issue")
    return reasons

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

def source_revalidation(source: Path, identity: SourceIdentity):
    reasons=[]
    try:
        if git(source,"rev-parse","HEAD").stdout.strip()!=identity.head: reasons.append("source HEAD changed during provider execution")
        if git(source,"rev-parse","HEAD^{tree}").stdout.strip()!=identity.tree: reasons.append("source tree changed during provider execution")
        if git(source,"status","--porcelain=v1","--untracked-files=all").stdout: reasons.append("source working tree changed during provider execution")
    except (OSError, subprocess.CalledProcessError): reasons.append("source identity could not be revalidated")
    return reasons

def full_patch(clone: Path, head: str) -> bytes:
    return git(clone,"diff","--binary","--full-index","--no-ext-diff","--no-renames",head,text=False,check=False).stdout

def diff_paths(clone: Path, head: str) -> list[str]:
    raw = git(clone,"diff","--name-only","--no-ext-diff","--no-renames","-z",head,text=False,check=False).stdout
    return sorted(path.decode("utf-8", "surrogateescape") for path in raw.split(b"\0") if path)

def paths_patch(clone: Path, head: str, paths: tuple[str, ...]) -> bytes:
    return git(clone,"diff","--binary","--full-index","--no-ext-diff","--no-renames",head,"--",*paths,text=False,check=False).stdout

ProviderFactory = Callable[[str, Path, bool, str], tuple[str, RuntimeConfiguration, Mapping[str, Any]]]

def construct_real_provider(provider_name: str, repository_root: Path, writable: bool):
    if provider_name == "claude":
        return ClaudeCodeProvider(repository_root=repository_root,
                                  externally_isolated_writable_repository=writable)
    if provider_name == "codex":
        return OpenAICodexProvider(
            repository_root=repository_root,
            externally_isolated_writable_repository=writable,
            externally_enforced_read_only_repository=not writable,
        )
    raise CrewBlocked("provider must be claude or codex")

def run_crew(*, source: Path, output_root: Path, task_id: str|None=None, provider_name: str|None=None,
             implementation_paths: tuple[str,...]=(), test_paths: tuple[str,...]=(), run_id: str|None=None,
             retry_run_id: str|None=None, review_feedback_file: Path|None=None, host_output_root: str|None=None,
             provider_factory: ProviderFactory|None=None, _require_physical_read_only_source: bool=True):
    started=time.monotonic()
    host_root_path = validate_host_output_root(host_output_root) if host_output_root is not None else None
    retry_mode = retry_run_id is not None
    if retry_mode and any((task_id is not None, provider_name is not None, implementation_paths, test_paths)):
        raise CrewBlocked("retry mode inherits task, provider, and write paths; do not supply them explicitly")
    if not retry_mode and review_feedback_file is not None:
        raise CrewBlocked("--review-feedback-file is valid only with --retry-run")
    if retry_mode and review_feedback_file is None:
        raise CrewBlocked("--review-feedback-file is required with --retry-run")
    if not retry_mode and (not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id)):
        raise CrewBlocked("task ID must match NSC-###")
    identity=capture_source(source); source_root=Path(identity.root).resolve(strict=True)
    if _require_physical_read_only_source and not (os.statvfs(source_root).f_flag & os.ST_RDONLY):
        raise CrewBlocked("production source checkout must be physically mounted read-only")
    output_root = output_root.resolve()
    retry_context = None
    if retry_mode:
        assert retry_run_id is not None and review_feedback_file is not None
        retry_context = load_retry_context(
            source=source_root, identity=identity, output_root=output_root,
            prior_run_id=retry_run_id, feedback_file=review_feedback_file
        )
        task_id = retry_context.task_id
        provider_name = retry_context.provider
        implementation_paths = retry_context.implementation_paths
        test_paths = retry_context.test_paths
    assert task_id is not None
    if not TASK_ID_RE.fullmatch(task_id): raise CrewBlocked("task ID must match NSC-###")
    if not isinstance(provider_name, str): raise CrewBlocked("provider is required")
    if not implementation_paths: raise CrewBlocked("at least one --implementation-path is required")
    if not test_paths: raise CrewBlocked("at least one --test-path is required for Stage 5B")
    impl_bounds, test_bounds = WriteBoundaries(implementation_paths, test_paths), WriteBoundaries(test_paths, implementation_paths)
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
    expected_requirement_ids=tuple(
        [item["criterion_id"] for item in task["acceptance_criteria"]]
        + [item["gate_id"] for item in task["completion_gates"]]
    )
    task_text=task_raw.decode("utf-8-sig"); gdd=committed_bytes(source_root,identity.head,GDD_PATH).decode("utf-8-sig"); policy=committed_bytes(source_root,identity.head,POLICY_PATH).decode("utf-8-sig")
    role_records=[]; reasons=[]; impl_actual=set(); test_actual=set(); validator_status=None; attempts=0
    latest_impl={}; latest_test={}; candidate_path=None; diagnostic_path=None; accepted_candidate=None
    human_review_feedback = retry_context.feedback_text if retry_context is not None else None
    def invoke(role:str, attempt:int, repo:Path, writable:bool, prompt:str, schema:Mapping[str,Any], capability_class:str, boundaries:WriteBoundaries):
        invocation_id=f"{task_id.lower()}-{role.replace('_','-')}-{attempt}-{hashlib.sha256(run_id.encode()).hexdigest()[:12]}"
        caps=("repository_read","repository_search","repository_write") if writable else ("repository_read","repository_search")
        if provider_factory: key,config,registry=provider_factory(provider_name,repo,writable,role)
        else:
            key,config=runtime_configuration(provider_name)
            provider=construct_real_provider(provider_name,repo,writable)
            registry={provider.provider_identifier:provider}
        inv=AgentInvocationRequest(AGENT_INVOCATION_REQUEST_SCHEMA_VERSION,invocation_id,role,prompt,
            tuple(dict.fromkeys((f"Tasks/{task_id}.yaml",GDD_PATH,POLICY_PATH,*implementation_paths,*test_paths))),caps,boundaries,schema,capability_class,
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
        progress.emit("role_completed",f"{display} {attempt} completed: {result.status} ({duration:.1f}s)",role=role,attempt=attempt,status=result.status,duration_seconds=duration)
        return inv,result
    with tempfile.TemporaryDirectory(prefix="nsc-execution-crew-") as temporary:
        clone=clone_exact(source_root,identity.head,Path(temporary))
        progress.emit("clone_completed","Disposable clone ready",status="passed")
        baseline_clone=snapshot(clone)
        preflight_role_paths(baseline_clone, implementation_paths, test_paths)
        stop=False
        for attempt in (1,2):
            attempts=attempt
            progress.emit("attempt_started",f"Attempt {attempt}/2 started",attempt=attempt)
            if attempt==2: progress.emit("repair_cycle_started","Repair cycle started",attempt=attempt)
            repair_actual=set()
            findings=None if attempt==1 else latest_validator.get("blocking_issues",[])
            before=snapshot(clone)
            inv,res=invoke("implementer",attempt,clone,True,implementer_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,implementation_paths=implementation_paths,findings=findings,human_review_feedback=human_review_feedback),IMPLEMENTER_OUTPUT_SCHEMA,"standard",impl_bounds)
            after=snapshot(clone); actual,scope=incremental_check(before,after,inv,require_change=(attempt==1)); scope+=source_revalidation(source_root,identity)
            output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; blockers=list(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
            record={"role":"implementer","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":list(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/implementer_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/implementer_{attempt}.json"); impl_actual.update(actual); latest_impl=output
            progress.emit("scope_check_completed",f"Implementer {attempt} scope check {'passed' if not scope else 'failed'}: {len(actual)} changed paths",role="implementer",attempt=attempt,status="passed" if not scope else "failed",changed_paths=actual,changed_path_count=len(actual))
            if attempt==2: repair_actual.update(actual)
            if blockers or scope: reasons += [*(f"implementer blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
            impl_patch=paths_patch(clone,identity.head,implementation_paths).decode("utf-8","replace")
            before=snapshot(clone)
            inv,res=invoke("test_author",attempt,clone,True,test_author_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,policy=policy,implementation_patch=impl_patch,implementation_paths=implementation_paths,implementation_actual_paths=sorted(impl_actual),test_paths=test_paths,findings=findings,human_review_feedback=human_review_feedback),TEST_AUTHOR_OUTPUT_SCHEMA,"low_cost",test_bounds)
            after=snapshot(clone); actual,scope=incremental_check(before,after,inv,require_change=(attempt==1)); scope+=source_revalidation(source_root,identity)
            output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; blockers=list(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
            record={"role":"test_author","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":list(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/test_author_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/test_author_{attempt}.json"); test_actual.update(actual); latest_test=output
            progress.emit("scope_check_completed",f"Test Author {attempt} scope check {'passed' if not scope else 'failed'}: {len(actual)} changed paths",role="test_author",attempt=attempt,status="passed" if not scope else "failed",changed_paths=actual,changed_path_count=len(actual))
            if attempt==2: repair_actual.update(actual)
            if blockers or scope: reasons += [*(f"test author blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
            if attempt==2 and not repair_actual:
                reasons.append("repair cycle made no deterministic changes"); crew_status="needs_human"; stop=True; break
            candidate=full_patch(clone,identity.head); final_paths=changed_paths(baseline_clone,snapshot(clone))
            inv,res=invoke("validator",attempt,source_root,False,validator_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,candidate_patch=candidate.decode("utf-8","replace"),changed_paths=final_paths,implementer_output=latest_impl,test_author_output=latest_test,human_review_feedback=human_review_feedback),VALIDATOR_OUTPUT_SCHEMA,"high_reasoning",WriteBoundaries((),()))
            scope=source_revalidation(source_root,identity); output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; validator_status=output.get("status")
            if res.status!="succeeded": scope.append(f"AgentResult failed: {res.failure_classification}")
            else: scope += validator_semantic_reasons(output, expected_requirement_ids)
            record={"role":"validator","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":[],"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":[],"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/validator_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/validator_{attempt}.json"); latest_validator=output
            progress.emit("validator_completed",f"Validator {attempt} completed: {validator_status or res.status}",role="validator",attempt=attempt,status=validator_status or res.status)
            if scope: reasons+=scope; crew_status="rejected"; stop=True; break
            if validator_status=="pass": crew_status="review_ready"; accepted_candidate=candidate; stop=True; break
            if validator_status=="blocked_by_design": reasons.append("validator blocked_by_design"); crew_status="blocked"; stop=True; break
            if validator_status!="needs_changes": reasons.append("validator returned invalid status"); crew_status="rejected"; stop=True; break
            if attempt==2: reasons.append("second validator pass still needs changes"); crew_status="needs_human"; stop=True; break
        final_snap=snapshot(clone); final_paths=changed_paths(baseline_clone,final_snap)
        final_reasons=[]
        if final_snap.head!=baseline_clone.head or final_snap.head!=identity.head: final_reasons.append("final clone HEAD differs from clone/source baseline HEAD")
        if final_snap.index!=baseline_clone.index: final_reasons.append("final clone index differs from clone baseline index")
        if final_snap.untracked!=baseline_clone.untracked: final_reasons.append("final clone untracked state differs from clone baseline")
        allowed=set(implementation_paths)|set(test_paths)
        final_reasons += [f"final changed path outside crew boundaries: {p}" for p in final_paths if p not in allowed]
        if crew_status=="review_ready" and not (set(final_paths)&set(implementation_paths)): final_reasons.append("final candidate has no implementation change")
        if crew_status=="review_ready" and not (set(final_paths)&set(test_paths)): final_reasons.append("final candidate has no test change")
        if crew_status=="review_ready" and not accepted_candidate: final_reasons.append("final candidate patch is empty")
        if crew_status=="review_ready" and diff_paths(clone,identity.head)!=final_paths: final_reasons.append("final Git diff paths differ from deterministic changed paths")
        final_reasons += source_revalidation(source_root,identity)
        if final_reasons:
            reasons+=final_reasons; crew_status="rejected"
        if crew_status=="review_ready":
            if accepted_candidate is None: raise CrewBlocked("review-ready result has no accepted candidate bytes")
            (run_dir/"candidate.patch").write_bytes(accepted_candidate); candidate_path=str(run_dir/"candidate.patch")
        if crew_status!="review_ready":
            diagnostic=full_patch(clone,identity.head)
            if diagnostic: (run_dir/"workspace_diagnostic.patch").write_bytes(diagnostic); diagnostic_path=str(run_dir/"workspace_diagnostic.patch")
    review_origin = None if retry_context is None else {
        "prior_run_id":retry_context.prior_run_id,
        "result":"human_rejected",
        "feedback_artifact":"human_review_feedback.txt",
        "feedback_sha256":retry_context.feedback_sha256,
    }
    host_candidate_path = str(host_root_path/run_id/"candidate.patch") if host_root_path is not None and candidate_path else None
    host_diagnostic_path = str(host_root_path/run_id/"workspace_diagnostic.patch") if host_root_path is not None and diagnostic_path else None
    human_status = {"review_ready":"REVIEW_READY","blocked":"BLOCKED","rejected":"REJECTED","needs_human":"NEEDS_HUMAN"}[crew_status]
    if crew_status=="review_ready":
        human_reason = "The candidate passed semantic crew review and awaits human review."
        human_artifact = host_candidate_path or candidate_path
        human_next_action = "Review candidate.patch; apply manually only if approved."
    else:
        human_reason = safe_human_reason(reasons)
        if diagnostic_path:
            human_artifact = host_diagnostic_path or diagnostic_path
            human_next_action = "Inspect the diagnostic patch and blocking reason; no candidate was approved."
        else:
            human_artifact = None
            human_next_action = "Inspect the blocking reason; no diagnostic patch was produced."
    human_result = {"status":human_status,"reason":human_reason,"artifact_path":human_artifact,"next_action":human_next_action}
    result={"schema_version":"1.0","run_id":run_id,"task_id":task_id,"task_contract_identity":contract_identity.to_dict(),"source_head":identity.head,"source_tree":identity.tree,"source_branch":identity.branch,"provider":provider_name,"crew_status":crew_status,"attempts_used":attempts,"requested_implementation_paths":list(implementation_paths),"requested_test_paths":list(test_paths),"implementation_actual_changed_paths":sorted(impl_actual),"test_actual_changed_paths":sorted(test_actual),"final_actual_changed_paths":final_paths,"role_results":role_records,"candidate_patch_path":candidate_path,"workspace_diagnostic_patch_path":diagnostic_path,"candidate_patch_host_path":host_candidate_path,"workspace_diagnostic_patch_host_path":host_diagnostic_path,"rejection_reasons":reasons,"validator_status":validator_status,"review_origin":review_origin,"human_next_step":"Review candidate.patch; apply manually only if approved." if crew_status=="review_ready" else "Inspect diagnostics and role artifacts; no review-ready patch was emitted.","human_result":human_result,"duration_seconds":time.monotonic()-started}
    (run_dir/"crew_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    progress.emit("run_completed",f"ExecutionCrew completed: {crew_status}",status=crew_status,duration_seconds=round(result["duration_seconds"],3))
    return result

def print_human_summary(result: Mapping[str, Any]) -> None:
    """Concise human-facing summary on stderr; stdout stays reserved for machine-readable result JSON."""
    human = result.get("human_result")
    if not isinstance(human, Mapping):
        return
    lines = [f"RESULT: {human.get('status')}"]
    if human.get("status") != "REVIEW_READY" and human.get("reason") is not None:
        lines.append(f"WHY: {human.get('reason')}")
    lines.append(f"ARTIFACT: {human.get('artifact_path') or 'none'}")
    lines.append(f"NEXT: {human.get('next_action')}")
    print("\n".join(lines), file=sys.stderr, flush=True)

def main():
    default_output_root=Path(os.environ["NSC_EXECUTION_OUTPUT_ROOT"]) if os.getenv("NSC_EXECUTION_OUTPUT_ROOT") else ROOT/"Pipeline/ExecutionCrew/outputs"
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id")
    parser.add_argument("--provider",choices=("claude","codex"))
    parser.add_argument("--implementation-path",action="append")
    parser.add_argument("--test-path",action="append")
    parser.add_argument("--retry-run")
    parser.add_argument("--review-feedback-file",type=Path)
    parser.add_argument("--source",type=Path,default=ROOT)
    parser.add_argument("--output-root",type=Path,default=default_output_root)
    parser.add_argument("--host-output-root",help="Human-facing HOST (e.g. Windows) absolute path mirroring --output-root, for display only")
    args=parser.parse_args()
    host_output_root=args.host_output_root if args.host_output_root is not None else os.getenv("NSC_EXECUTION_HOST_OUTPUT_ROOT")
    if args.retry_run:
        if any((args.task_id, args.provider, args.implementation_path, args.test_path)):
            parser.error("--retry-run inherits task, provider, and write paths; do not supply them")
        if args.review_feedback_file is None:
            parser.error("--review-feedback-file is required with --retry-run")
    else:
        missing = [name for name, value in (
            ("--task-id", args.task_id), ("--provider", args.provider),
            ("--implementation-path", args.implementation_path), ("--test-path", args.test_path)
        ) if not value]
        if missing:
            parser.error("normal mode requires " + ", ".join(missing))
        if args.review_feedback_file is not None:
            parser.error("--review-feedback-file requires --retry-run")
    try: result=run_crew(source=args.source,output_root=args.output_root,task_id=args.task_id,provider_name=args.provider,implementation_paths=tuple(args.implementation_path or ()),test_paths=tuple(args.test_path or ()),retry_run_id=args.retry_run,review_feedback_file=args.review_feedback_file,host_output_root=host_output_root)
    except (CrewBlocked,ValueError,OSError,subprocess.CalledProcessError) as exc: print(f"ExecutionCrew blocked: {exc}",file=sys.stderr); return 2
    print(json.dumps(result,indent=2,sort_keys=True))
    print_human_summary(result)
    return 0 if result["crew_status"]=="review_ready" else 1
if __name__=="__main__": raise SystemExit(main())
