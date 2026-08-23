#!/usr/bin/env python3
"""Run the minimum production ExecutionCrew for one human-selected task."""
from __future__ import annotations

import argparse, hashlib, json, os, re, subprocess, sys, tempfile, time
from dataclasses import dataclass
from pathlib import Path
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
GDD_PATH = "Docs/GDD/No_Safe_Circle_GDD.md"
POLICY_PATH = "Docs/Engineering/UNITY_TESTING_POLICY.md"

class CrewBlocked(RuntimeError): pass

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

def run_crew(*, source: Path, output_root: Path, task_id: str, provider_name: str,
             implementation_paths: tuple[str,...], test_paths: tuple[str,...], run_id: str|None=None,
             provider_factory: ProviderFactory|None=None, _require_physical_read_only_source: bool=True):
    started=time.monotonic()
    if not TASK_ID_RE.fullmatch(task_id): raise CrewBlocked("task ID must match NSC-###")
    if not implementation_paths: raise CrewBlocked("at least one --implementation-path is required")
    if not test_paths: raise CrewBlocked("at least one --test-path is required for Stage 5B")
    impl_bounds, test_bounds = WriteBoundaries(implementation_paths, test_paths), WriteBoundaries(test_paths, implementation_paths)
    identity=capture_source(source); source_root=Path(identity.root).resolve(strict=True)
    if _require_physical_read_only_source and not (os.statvfs(source_root).f_flag & os.ST_RDONLY): raise CrewBlocked("production source checkout must be physically mounted read-only")
    task_raw=committed_bytes(source_root,identity.head,f"Tasks/{task_id}.yaml")
    task, contract_identity=parse_task(task_raw,task_id)
    expected_requirement_ids=tuple(
        [item["criterion_id"] for item in task["acceptance_criteria"]]
        + [item["gate_id"] for item in task["completion_gates"]]
    )
    task_text=task_raw.decode("utf-8-sig"); gdd=committed_bytes(source_root,identity.head,GDD_PATH).decode("utf-8-sig"); policy=committed_bytes(source_root,identity.head,POLICY_PATH).decode("utf-8-sig")
    run_id=run_id or f"{task_id.lower()}-{time.strftime('%Y%m%dt%H%M%Sz',time.gmtime())}"
    run_dir=output_root/run_id; run_dir.mkdir(parents=True,exist_ok=False)
    (run_dir/"role_results").mkdir()
    role_records=[]; reasons=[]; impl_actual=set(); test_actual=set(); validator_status=None; attempts=0
    latest_impl={}; latest_test={}; candidate_path=None; diagnostic_path=None; accepted_candidate=None
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
        result=TaskExecutionRunner(run_dir/"task_execution",AgentRunner(run_dir/"agent_runtime",config,registry)).run(req)
        return inv,result
    with tempfile.TemporaryDirectory(prefix="nsc-execution-crew-") as temporary:
        clone=clone_exact(source_root,identity.head,Path(temporary))
        baseline_clone=snapshot(clone)
        preflight_role_paths(baseline_clone, implementation_paths, test_paths)
        stop=False
        for attempt in (1,2):
            attempts=attempt
            repair_actual=set()
            findings=None if attempt==1 else latest_validator.get("blocking_issues",[])
            before=snapshot(clone)
            inv,res=invoke("implementer",attempt,clone,True,implementer_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,implementation_paths=implementation_paths,findings=findings),IMPLEMENTER_OUTPUT_SCHEMA,"standard",impl_bounds)
            after=snapshot(clone); actual,scope=incremental_check(before,after,inv,require_change=(attempt==1)); scope+=source_revalidation(source_root,identity)
            output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; blockers=list(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
            record={"role":"implementer","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":list(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/implementer_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/implementer_{attempt}.json"); impl_actual.update(actual); latest_impl=output
            if attempt==2: repair_actual.update(actual)
            if blockers or scope: reasons += [*(f"implementer blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
            impl_patch=paths_patch(clone,identity.head,implementation_paths).decode("utf-8","replace")
            before=snapshot(clone)
            inv,res=invoke("test_author",attempt,clone,True,test_author_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,policy=policy,implementation_patch=impl_patch,implementation_paths=implementation_paths,implementation_actual_paths=sorted(impl_actual),test_paths=test_paths,findings=findings),TEST_AUTHOR_OUTPUT_SCHEMA,"low_cost",test_bounds)
            after=snapshot(clone); actual,scope=incremental_check(before,after,inv,require_change=(attempt==1)); scope+=source_revalidation(source_root,identity)
            output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; blockers=list(output.get("blockers",[])); scope += ([] if res.status=="succeeded" else [f"AgentResult failed: {res.failure_classification}"])
            record={"role":"test_author","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":list(output.get("claimed_changed_paths",[])),"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":actual,"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/test_author_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/test_author_{attempt}.json"); test_actual.update(actual); latest_test=output
            if attempt==2: repair_actual.update(actual)
            if blockers or scope: reasons += [*(f"test author blocker: {x}" for x in blockers),*scope]; crew_status="blocked" if blockers else "rejected"; stop=True; break
            if attempt==2 and not repair_actual:
                reasons.append("repair cycle made no deterministic changes"); crew_status="needs_human"; stop=True; break
            candidate=full_patch(clone,identity.head); final_paths=changed_paths(baseline_clone,snapshot(clone))
            inv,res=invoke("validator",attempt,source_root,False,validator_prompt(task_id=task_id,title=task["title"],task_contract=task_text,gdd=gdd,candidate_patch=candidate.decode("utf-8","replace"),changed_paths=final_paths,implementer_output=latest_impl,test_author_output=latest_test),VALIDATOR_OUTPUT_SCHEMA,"high_reasoning",WriteBoundaries((),()))
            scope=source_revalidation(source_root,identity); output=thaw_json(res.structured_output) if res.status=="succeeded" else {}; validator_status=output.get("status")
            if res.status!="succeeded": scope.append(f"AgentResult failed: {res.failure_classification}")
            else: scope += validator_semantic_reasons(output, expected_requirement_ids)
            record={"role":"validator","attempt":attempt,"agent_status":res.status,"failure_classification":res.failure_classification,"structured_output":output,"role_claimed_paths":[],"agent_runtime_claimed_paths":list(res.claimed_changed_paths),"deterministic_incremental_actual_changed_paths":[],"scope_check_reasons":scope,"duration_seconds":res.duration_seconds,"model":res.model,"provider":res.provider}
            (run_dir/f"role_results/validator_{attempt}.json").write_text(json.dumps(record,indent=2,sort_keys=True)+"\n"); role_records.append(f"role_results/validator_{attempt}.json"); latest_validator=output
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
    result={"schema_version":"1.0","run_id":run_id,"task_id":task_id,"task_contract_identity":contract_identity.to_dict(),"source_head":identity.head,"source_tree":identity.tree,"source_branch":identity.branch,"provider":provider_name,"crew_status":crew_status,"attempts_used":attempts,"implementation_actual_changed_paths":sorted(impl_actual),"test_actual_changed_paths":sorted(test_actual),"final_actual_changed_paths":final_paths,"role_results":role_records,"candidate_patch_path":candidate_path,"workspace_diagnostic_patch_path":diagnostic_path,"rejection_reasons":reasons,"validator_status":validator_status,"human_next_step":"Review candidate.patch; apply manually only if approved." if crew_status=="review_ready" else "Inspect diagnostics and role artifacts; no review-ready patch was emitted.","duration_seconds":time.monotonic()-started}
    (run_dir/"crew_result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def main():
    default_output_root=Path(os.environ["NSC_EXECUTION_OUTPUT_ROOT"]) if os.getenv("NSC_EXECUTION_OUTPUT_ROOT") else ROOT/"Pipeline/ExecutionCrew/outputs"
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--task-id",required=True); parser.add_argument("--provider",required=True,choices=("claude","codex")); parser.add_argument("--implementation-path",action="append",required=True); parser.add_argument("--test-path",action="append",required=True); parser.add_argument("--source",type=Path,default=ROOT); parser.add_argument("--output-root",type=Path,default=default_output_root)
    args=parser.parse_args()
    try: result=run_crew(source=args.source,output_root=args.output_root,task_id=args.task_id,provider_name=args.provider,implementation_paths=tuple(args.implementation_path),test_paths=tuple(args.test_path))
    except (CrewBlocked,ValueError,OSError,subprocess.CalledProcessError) as exc: print(f"ExecutionCrew blocked: {exc}",file=sys.stderr); return 2
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["crew_status"]=="review_ready" else 1
if __name__=="__main__": raise SystemExit(main())
