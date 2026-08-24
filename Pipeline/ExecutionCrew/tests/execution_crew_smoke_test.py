#!/usr/bin/env python3
"""Deterministic four-role ExecutionCrew smoke; no Unity or live provider calls."""
from __future__ import annotations
import hashlib, io, json, os, shutil, subprocess, sys, tempfile, time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import Usage
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse
from Pipeline.ExecutionCrew.run_crew import CrewBlocked, Snapshot, audit_commands, changed_paths, clone_exact, construct_real_provider, full_patch, main as crew_main, patch_commands, powershell_single_quote, print_human_summary, run_crew, runtime_configuration, safe_human_reason, validate_host_output_root

TASK="NSC-005"; IMPL="Assets/Scripts/PlayerMana.cs"; TEST="Assets/Tests/PlayerManaTests.cs"; OTHER="Assets/Scripts/Other.cs"; SECRET="FULL_ROLE_PROMPT_SENTINEL_SECRET"
RELATED_TASK="NSC-010"
def cmd(root,*args): return subprocess.run(("git","-C",str(root),*args),check=True,stdout=subprocess.PIPE,text=True).stdout.strip()
def write(path,text): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")

def root_task():
    """Minimal valid persistent-graph root (NSC-001); required by load_persistent_work_graph."""
    return {"schema_version":"2.0","id":"NSC-001","contract_revision":1,"contract_disposition":"active","title":"No Safe Circle","reconciliation_key":"no-safe-circle","kind":"feature","execution_scope":"not_applicable","execution_reason":"Project root.","decomposition_state":"needs_decomposition","decomposition_reason":"Project root.","parent":"","depends_on":[],"exclusive_resources":[],"acceptance_criteria":[],"completion_gates":[],"downstream_integration_obligations":[],"provenance":{"origin":"fixture"}}

def related_task():
    """A second, unrelated fixture task usable as a real requires_declared_dependency target."""
    return {"schema_version":"2.0","id":RELATED_TASK,"contract_revision":1,"contract_disposition":"active","title":"Related Fixture Dependency","reconciliation_key":"related-fixture-dependency","kind":"implementation","execution_scope":"single_agent","execution_reason":"Bounded fixture component usable as a related dependency target.","decomposition_state":"concrete","decomposition_reason":"Fixture requires no missing design.","parent":"NSC-001","depends_on":[],"exclusive_resources":[],"acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Related behavior is implemented."}],"completion_gates":[{"gate_id":"VAL-001","reference":"fixture","requirement":"Related behavior is verified."}],"downstream_integration_obligations":[],"provenance":{"origin":"fixture"}}

def write_persistent_graph(root,tasks):
    """Write a complete, load_persistent_work_graph-valid graph: every Tasks/*.yaml plus the
    Pipeline/TaskGraph bootstrap marker, ID map, project requirements, and resource groups."""
    for task in tasks: write(root/f"Tasks/{task['id']}.yaml",json.dumps(task)+"\n")
    id_map={task["reconciliation_key"]:task["id"] for task in tasks}
    write(root/"Pipeline/TaskGraph/WORK_ID_MAP.json",json.dumps({"id_map":id_map})+"\n")
    write(root/"Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml",json.dumps({"requirements":[]})+"\n")
    write(root/"Pipeline/TaskGraph/RESOURCE_GROUPS.yaml",json.dumps({"resource_groups":[]})+"\n")
    write(root/"Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json",json.dumps({"schema_version":"1.0","bootstrap_status":"complete","serialization_format":"yaml_1_2_json_subset","output_sha256":{"Tasks/NSC-001.yaml":"fixture"}})+"\n")

def fixture(parent):
    root=parent/"source"; root.mkdir(); subprocess.run(("git","init","-q",str(root)),check=True); cmd(root,"config","user.name","Crew Smoke"); cmd(root,"config","user.email","crew@example.invalid")
    write(root/IMPL,"public class PlayerMana { }\n"); write(root/TEST,"public class PlayerManaTests { }\n"); write(root/OTHER,"public class Other { }\n"); write(root/".gitignore","*.ignored\n")
    task={"schema_version":"2.0","id":TASK,"contract_revision":3,"contract_disposition":"active","title":"Mana","reconciliation_key":"player-mana","kind":"implementation","execution_scope":"single_agent","execution_reason":"Bounded fixture component that owns its own mana state.","decomposition_state":"concrete","decomposition_reason":"Fixture requires no missing design.","parent":"NSC-001","depends_on":[],"exclusive_resources":[],"acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Mana behavior is implemented."}],"completion_gates":[{"gate_id":"VAL-001","reference":"fixture","requirement":"Unity behavior is verified."}],"downstream_integration_obligations":[],"provenance":{"origin":"fixture"}}
    write_persistent_graph(root,[root_task(),task,related_task()])
    write(root/"Docs/GDD/No_Safe_Circle_GDD.md",f"# GDD\n{SECRET}\n"); write(root/"Docs/Engineering/UNITY_TESTING_POLICY.md","# Policy\nNever claim tests passed.\n")
    cmd(root,"add","."); cmd(root,"commit","-qm","baseline"); return root

class State:
    def __init__(self,scenario,source,feedback=None): self.scenario=scenario; self.source=source; self.feedback=feedback; self.calls=[]; self.clone=None

class FakeProvider:
    provider_identifier="fake"
    def __init__(self,state,repo,writable,role): self.state=state; self.repo=repo; self.writable=writable; self.role=role
    def invoke(self,request,model):
        s=self.state; attempt=sum(1 for r,_,_ in s.calls if r==self.role)+1; s.calls.append((self.role,request,model))
        assert request.role==self.role
        if s.feedback and self.role!="contract_locality_auditor":
            assert "HUMAN REVIEW REJECTION FROM PRIOR REVIEW-READY CANDIDATE" in request.prompt
            assert s.feedback in request.prompt
            if self.role=="implementer":
                assert "presence is NOT evidence that the task is complete" in request.prompt
                assert "not Implementer blockers" in request.prompt and "Do not modify test files" in request.prompt
                assert "Report a blocker only when the production correction itself cannot be completed" in request.prompt
            elif self.role=="test_author":
                assert "Add regression coverage" in request.prompt and "approved test paths" in request.prompt
                assert "explicitly your responsibility" in request.prompt
            else:
                assert "A Validator pass must not ignore an unresolved human-review rejection" in request.prompt
                assert "both the production correction and appropriate regression" in request.prompt
        if s.scenario=="slow" and self.role=="implementer": time.sleep(.06)
        if self.role=="contract_locality_auditor":
            assert not self.writable and self.repo.resolve()==s.source.resolve()
            assert "repository_write" not in request.allowed_capabilities
            assert not request.write_boundaries.allowed_paths and not request.write_boundaries.denied_paths
            assert request.model_capability_class=="high_reasoning"
            for required in ("Contract Locality Auditor", "QUESTION YOU MUST ANSWER", "DETERMINISTIC TASK CATALOG", "local_to_task"):
                assert required in request.prompt
            if s.feedback: assert s.feedback not in request.prompt
            def local(entry_id,entry_type): return {"id":entry_id,"entry_type":entry_type,"classification":"local_to_task","evidence":"owned locally by this task","related_task_ids":[],"recommended_action":"keep"}
            entries=[local("AC-001","acceptance_criterion"),local("VAL-001","completion_gate")]
            blocking=[]; audit_status="pass"
            if s.scenario=="locality_review_required":
                entries[1]={"id":"VAL-001","entry_type":"completion_gate","classification":"requires_declared_dependency","evidence":"cannot be proven without another task's already-integrated behavior","related_task_ids":[RELATED_TASK],"recommended_action":"add_dependency"}
                blocking=[{"entry_id":"VAL-001","reason_code":"requires_declared_dependency","issue":"needs a declared dependency","recommended_action":"add_dependency","related_task_ids":[RELATED_TASK]}]
                audit_status="contract_review_required"
            elif s.scenario=="locality_add_dependency_empty_related":
                entries[1]={"id":"VAL-001","entry_type":"completion_gate","classification":"requires_declared_dependency","evidence":"cannot be proven without another task's already-integrated behavior","related_task_ids":[],"recommended_action":"add_dependency"}
                blocking=[{"entry_id":"VAL-001","reason_code":"requires_declared_dependency","issue":"needs a declared dependency","recommended_action":"add_dependency","related_task_ids":[]}]
                audit_status="contract_review_required"
            elif s.scenario=="locality_add_dependency_mismatch":
                entries[1]={"id":"VAL-001","entry_type":"completion_gate","classification":"requires_declared_dependency","evidence":"cannot be proven without another task's already-integrated behavior","related_task_ids":[RELATED_TASK],"recommended_action":"add_dependency"}
                blocking=[{"entry_id":"VAL-001","reason_code":"requires_declared_dependency","issue":"needs a declared dependency","recommended_action":"add_dependency","related_task_ids":[]}]
                audit_status="contract_review_required"
            elif s.scenario=="locality_invalid":
                entries[1]={"id":"VAL-001","entry_type":"completion_gate","classification":"downstream_integration","evidence":"verifies a future consumer","related_task_ids":[],"recommended_action":"move_to_downstream_integration"}
                audit_status="pass"
            elif s.scenario=="nsc012_like":
                entries=[local("AC-001","acceptance_criterion"),
                         {"id":"VAL-001","entry_type":"completion_gate","classification":"downstream_integration",
                          "evidence":"pursuit/attack-controller shutdown and leaving play is verified by the enemy's own pursuit/attack controller system, a downstream consumer of this task's defeat state, not owned by this health/defeat task",
                          "related_task_ids":[],"recommended_action":"move_to_downstream_integration"},
                         {"id":"VAL-002","entry_type":"completion_gate","classification":"requires_declared_dependency",
                          "evidence":"target-loss/search behavior across room crossings is owned by other enemies' pursuit/search AI and the navigation layer, not this task",
                          "related_task_ids":["NSC-014"],"recommended_action":"add_dependency"}]
                blocking=[{"entry_id":"VAL-001","reason_code":"downstream_integration","issue":"verifies a future pursuit/attack controller consumer, not owned by this task","recommended_action":"move_to_downstream_integration","related_task_ids":[]},
                          {"entry_id":"VAL-002","reason_code":"requires_declared_dependency","issue":"requires other enemies' target-loss/search behavior across room crossings","recommended_action":"add_dependency","related_task_ids":["NSC-014"]}]
                audit_status="contract_review_required"
            output={"status":audit_status,"summary":"locality audit","entry_results":entries,"blocking_findings":blocking,"files_reviewed":[IMPL,TEST]}
        elif self.role=="validator":
            assert not self.writable and self.repo.resolve()==s.source.resolve(); assert "repository_write" not in request.allowed_capabilities; assert not request.write_boundaries.allowed_paths
            exact=full_patch(s.clone,cmd(s.source,"rev-parse","HEAD")).decode("utf-8","replace")
            assert f"EXACT FULL CANDIDATE GIT PATCH\n---\n{exact}\n---" in request.prompt and "public int Mana" in request.prompt
            for required in ("baseline repository is intentionally unchanged", "authoritative proposed delta", "Absence of candidate changes from the baseline source is not a failure reason", "Do not request that the candidate be committed or applied to the real source before semantic validation", "Runtime or Unity evidence that was not executed remains not_proven"):
                assert required in request.prompt
            if s.scenario=="needs_twice": status="needs_changes"
            elif s.scenario in ("repair","no_op_repair") and attempt==1: status="needs_changes"
            elif s.scenario in ("design","validator_missing_integration_dependency","validator_design_ambiguity"): status="blocked_by_design"
            else: status="pass"
            criteria=[{"id":"AC-001","status":"pass","reason_code":"proved","evidence":"source review"},{"id":"VAL-001","status":"not_proven","reason_code":"runtime_not_executed","evidence":"Unity was not run"}]
            if s.scenario=="criteria_missing": criteria=criteria[:1]
            elif s.scenario=="criteria_duplicate": criteria=[criteria[0],criteria[0],criteria[1]]
            elif s.scenario=="criteria_unknown": criteria.append({"id":"AC-999","status":"pass","reason_code":"proved","evidence":"unknown"})
            elif s.scenario=="pass_fail": criteria[0]={"id":"AC-001","status":"fail","reason_code":"criterion_failed","evidence":"defect"}
            elif s.scenario=="reason_code_pass_invalid": criteria[1]={"id":"VAL-001","status":"not_proven","reason_code":"missing_integration_dependency","evidence":"needs registry integration"}
            elif s.scenario=="reason_code_mismatch": criteria[0]={"id":"AC-001","status":"pass","reason_code":"criterion_failed","evidence":"mismatched reason code"}
            elif s.scenario=="reason_code_fail_invalid": criteria[0]={"id":"AC-001","status":"fail","reason_code":"proved","evidence":"wrong reason for fail"}
            elif s.scenario=="validator_missing_integration_dependency": criteria[1]={"id":"VAL-001","status":"not_proven","reason_code":"missing_integration_dependency","evidence":"needs registry integration"}
            elif s.scenario=="validator_design_ambiguity": criteria[1]={"id":"VAL-001","status":"not_proven","reason_code":"design_ambiguity","evidence":"GDD does not define this behavior"}
            if s.scenario=="final_staged": cmd(s.clone,"add",IMPL)
            output={"status":status,"summary":"review","criteria_results":criteria,"blocking_issues":([{"path":IMPL,"issue":"fix mana","required_fix":"add repaired marker"}] if status=="needs_changes" else []),"risks":[],"files_reviewed":[IMPL,TEST]}
        elif self.role=="implementer":
            assert self.writable and request.model_capability_class=="standard"; assert request.is_path_writable(IMPL) and not request.is_path_writable(TEST)
            s.clone=self.repo.resolve()
            if s.scenario=="impl_test": write(self.repo/TEST,"bad\n")
            elif s.scenario=="untracked": write(self.repo/"bad.tmp","bad\n")
            elif s.scenario=="ignored_untracked": write(self.repo/"bad.ignored","bad\n")
            elif s.scenario=="deleted": (self.repo/IMPL).unlink()
            elif s.scenario=="renamed": (self.repo/IMPL).replace(self.repo/OTHER)
            elif s.scenario=="copied": write(self.repo/"Assets/Scripts/Copy.cs",(self.repo/IMPL).read_text())
            elif s.scenario=="staged": write(self.repo/IMPL,"staged\n"); cmd(self.repo,"add",IMPL)
            elif s.scenario=="head": cmd(self.repo,"config","user.name","Bad"); cmd(self.repo,"config","user.email","bad@example.invalid"); cmd(self.repo,"commit","--allow-empty","-qm","bad head")
            elif s.scenario=="source_mutation": write(self.repo/IMPL,"public class PlayerMana { public int Mana; }\n"); write(s.source/OTHER,"mutated\n")
            elif s.scenario=="blocker_no_artifact": pass
            else:
                if attempt==2: assert "fix mana" in request.prompt
                if not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/IMPL,"public class PlayerMana { public int Mana;"+(" public int HumanReviewFixed;" if s.feedback else "")+(" public int Repaired;" if attempt==2 else "")+" }\n")
            if s.scenario in ("blocker","blocker_no_artifact"): blockers=["cannot implement"]
            elif s.scenario=="blocker_leak": blockers=[f"implementer blocked, quoting reviewer verbatim: {s.feedback}"]
            else: blockers=[]
            output={"summary":"implementation","claimed_changed_paths":["claim-impl.cs"],"blockers":blockers,"notes":[]}
        else:
            assert self.writable and request.model_capability_class=="low_cost"; assert request.is_path_writable(TEST) and not request.is_path_writable(IMPL); assert "public int Mana" in request.prompt and "Never claim tests passed" in request.prompt
            if attempt==2: assert "fix mana" in request.prompt and ("Repaired" in request.prompt or s.scenario=="no_op_repair")
            if s.scenario=="test_impl": write(self.repo/IMPL,"public class PlayerMana { public int Rewritten; }\n")
            elif not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/TEST,"public class PlayerManaTests { public void ManaTest() {}"+(" public void HumanReviewRegression() {}" if s.feedback else "")+(" public void RepairTest() {}" if attempt==2 else "")+" }\n")
            test_blockers=[f"test author blocked, quoting reviewer verbatim: {s.feedback}"] if s.scenario=="test_blocker_leak" else []
            output={"summary":"tests","claimed_changed_paths":["claim-test.cs"],"test_cases_added_or_updated":["ManaTest"],"blockers":test_blockers,"known_limitations":["not run"],"proposed_unity_test_scope":"Play Mode"}
        return ProviderInvocationResponse(output,"fake log\n",("runtime-claim.cs",),Usage(1,1,2),True,())

def factory(state):
    def create(provider,repo,writable,role):
        assert provider in ("fake","claude","codex")
        key=f"{provider}-crew"
        config=RuntimeConfiguration({key:{"provider":"fake","models":{"low_cost":"fake-low","standard":"fake-standard","high_reasoning":"fake-high"}}})
        return key,config,{"fake":FakeProvider(state,repo,writable,role)}
    return create

def execute(source,outputs,scenario,index,*,provider="fake",implementation_paths=(IMPL,),test_paths=(TEST,),host_output_root=None):
    run_id=f"smoke-{scenario}-{index}"; state=State(scenario,source)
    result=run_crew(source=source,output_root=outputs,task_id=TASK,provider_name=provider,implementation_paths=implementation_paths,test_paths=test_paths,run_id=run_id,provider_factory=factory(state),_require_physical_read_only_source=False,host_output_root=host_output_root)
    return result,state,outputs/run_id

def retry_execute(source,outputs,scenario,index,prior_run_id,feedback_path,feedback_text,*,host_output_root=None):
    run_id=f"retry-{scenario}-{index}"; state=State(scenario,source,feedback_text)
    result=run_crew(source=source,output_root=outputs,run_id=run_id,retry_run_id=prior_run_id,review_feedback_file=feedback_path,provider_factory=factory(state),_require_physical_read_only_source=False,host_output_root=host_output_root)
    return result,state,outputs/run_id

def main():
  with tempfile.TemporaryDirectory(prefix="crew-smoke-") as td:
    root=Path(td); source=fixture(root); outputs=root/"outputs"; baseline=(cmd(source,"rev-parse","HEAD"),cmd(source,"status","--porcelain=v1","--untracked-files=all"),(source/IMPL).read_bytes())
    cmd(source,"config","core.autocrlf","true")
    with tempfile.TemporaryDirectory(prefix="clone-proof-") as clone_parent:
        clone_parent=Path(clone_parent); fake_home=clone_parent/"home"; fake_home.mkdir(); normal_config=fake_home/".gitconfig"; normal_config.write_text("[user]\n\tname = Untouched\n")
        calls=[]
        def recording_runner(argv,**kwargs):
            calls.append((tuple(argv),dict(kwargs))); return subprocess.run(argv,**kwargs)
        with patch.dict(os.environ,{"HOME":str(fake_home)},clear=False):
            exact=clone_exact(source,cmd(source,"rev-parse","HEAD"),clone_parent,_runner=recording_runner)
        assert cmd(exact,"config","--local","--get","core.autocrlf")=="false"
        assert cmd(exact,"config","--local","--get","core.filemode")=="false"
        assert cmd(exact,"rev-parse","HEAD")==cmd(source,"rev-parse","HEAD")
        assert subprocess.run(("git","-C",str(exact),"diff","--quiet","HEAD","--"),check=False).returncode==0
        clone_calls=[call for call in calls if call[0][:2]==("git","clone")]; assert len(clone_calls)==1
        assert "--no-local" in clone_calls[0][0] and "--local" not in clone_calls[0][0]
        protected_config=clone_parent/"clone.gitconfig"; assert clone_calls[0][1]["env"]["GIT_CONFIG_GLOBAL"]==str(protected_config)
        safe_values=subprocess.run(("git","config","--file",str(protected_config),"--get-all","safe.directory"),check=True,stdout=subprocess.PIPE,text=True).stdout.splitlines()
        assert safe_values==[str(source.resolve()),str((source/".git").resolve())]
        assert normal_config.read_text()=="[user]\n\tname = Untouched\n"
        assert all(call[1]["env"]["GIT_CONFIG_GLOBAL"]==str(protected_config) for call in calls)
        def failing_runner(argv,**kwargs):
            if tuple(argv[:2])==("git","clone"): return subprocess.CompletedProcess(argv,128,"","fatal: useful forced clone failure\n")
            return subprocess.run(argv,**kwargs)
        failure_parent=clone_parent/"failure"; failure_parent.mkdir()
        try: clone_exact(source,cmd(source,"rev-parse","HEAD"),failure_parent,_runner=failing_runner)
        except CrewBlocked as exc: assert "git clone" in str(exc) and "exit code 128" in str(exc) and "useful forced clone failure" in str(exc)
        else: raise AssertionError("forced clone failure was not preserved")
    with patch.dict(os.environ,{"NSC_OPENAI_CODEX_MODEL":"codex-override","NSC_CODEX_MODEL":"retired-name"},clear=False):
        _,codex_override=runtime_configuration("codex")
        assert codex_override.provider_configurations["codex-crew"]["models"]["standard"]=="codex-override"
    # Construction-only profile coverage: no provider invoke method is called.
    codex_write=construct_real_provider("codex",root,True); codex_validator=construct_real_provider("codex",source,False)
    assert codex_write.externally_isolated_writable_repository and not codex_write.externally_enforced_read_only_repository
    assert not codex_validator.externally_isolated_writable_repository and codex_validator.externally_enforced_read_only_repository
    claude_write=construct_real_provider("claude",root,True); claude_validator=construct_real_provider("claude",source,False)
    assert claude_write.externally_isolated_writable_repository and not claude_validator.externally_isolated_writable_repository
    # Source checkout representation is deliberately irrelevant to clone-baseline comparison.
    clone_base=Snapshot("head",b"index",(),{"same":"clone-bytes","changed":"old"})
    source_representation=Snapshot("head",b"other-index",(),{"same":"windows-bytes","changed":"old"})
    clone_final=Snapshot("head",b"index",(),{"same":"clone-bytes","changed":"new"})
    assert source_representation.tracked["same"] != clone_base.tracked["same"] and changed_paths(clone_base,clone_final)==["changed"]
    try: run_crew(source=source,output_root=outputs,task_id=TASK,provider_name="fake",implementation_paths=(IMPL,),test_paths=(TEST,),run_id="readonly",provider_factory=factory(State("pass",source)))
    except CrewBlocked as exc: assert "physically mounted read-only" in str(exc)
    else: raise AssertionError("writable production source accepted")
    for index,(implementation_paths,test_paths,message) in enumerate((
        ((IMPL,),(IMPL,),"disjoint"),
        (("Assets/Scripts/Missing.cs",),(TEST,),"implementation role path"),
        ((IMPL,),("Assets/Tests/Missing.cs",),"test role path"),
    ),40):
        state=State("pass",source)
        try: run_crew(source=source,output_root=outputs,task_id=TASK,provider_name="fake",implementation_paths=implementation_paths,test_paths=test_paths,run_id=f"preflight-{index}",provider_factory=factory(state),_require_physical_read_only_source=False)
        except CrewBlocked as exc: assert message in str(exc)
        else: raise AssertionError(message)
        assert not state.calls
    for field,value in (("contract_disposition","cancelled"),("kind","artifact"),("execution_scope","needs_execution_decomposition"),("decomposition_state","needs_decomposition")):
        clone=root/f"bad-{field}"; subprocess.run(("git","clone","-q",str(source),str(clone)),check=True); cmd(clone,"config","user.name","Crew Smoke"); cmd(clone,"config","user.email","crew@example.invalid"); task=json.loads((clone/f"Tasks/{TASK}.yaml").read_text()); task[field]=value; write(clone/f"Tasks/{TASK}.yaml",json.dumps(task)); cmd(clone,"add","."); cmd(clone,"commit","-qm","bad")
        try: execute(clone,outputs,"pass",len(list(outputs.glob("*")))+20)
        except CrewBlocked as exc: assert field in str(exc)
        else: raise AssertionError(field)
    progress_stderr=io.StringIO(); progress_stdout=io.StringIO()
    with redirect_stderr(progress_stderr), redirect_stdout(progress_stdout): passed,state,d=execute(source,outputs,"pass",1)
    assert passed["crew_status"]=="review_ready" and (d/"candidate.patch").read_bytes(); assert [x[0] for x in state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    assert passed["contract_locality_status"]=="pass" and passed["contract_locality_audit_path"] is not None
    assert Path(passed["contract_locality_audit_path"]).samefile(d/"contract_locality_audit.json")
    audit_artifact=json.loads((d/"contract_locality_audit.json").read_text())
    assert audit_artifact["schema_version"]=="1.0" and audit_artifact["task_id"]==TASK and audit_artifact["result"]["status"]=="pass"
    assert audit_artifact["source_head"]==passed["source_head"] and audit_artifact["task_contract_identity"]==passed["task_contract_identity"]
    assert progress_stdout.getvalue()=="" and "ExecutionCrew started" in progress_stderr.getvalue() and "ExecutionCrew completed: review_ready" in progress_stderr.getvalue()
    events=[json.loads(line) for line in (d/"progress.jsonl").read_text().splitlines() if line]
    names=[event["event"] for event in events]; assert names[0]=="run_started" and names[-1]=="run_completed"
    assert names.index("run_started") < names.index("role_started") < names.index("role_completed")
    telemetry=(d/"progress.jsonl").read_text()+progress_stderr.getvalue(); assert SECRET not in telemetry and "EXACT COMMITTED TASK CONTRACT" not in telemetry
    assert passed["requested_implementation_paths"]==[IMPL] and passed["requested_test_paths"]==[TEST]
    assert passed["review_origin"] is None
    fake_result={"crew_status":"review_ready","machine":"parseable"}; cli_stdout=io.StringIO(); cli_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as normal_cli_run, patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), redirect_stdout(cli_stdout), redirect_stderr(cli_stderr):
        assert crew_main()==0
    assert json.loads(cli_stdout.getvalue())==fake_result and cli_stderr.getvalue()==""
    normal_kwargs=normal_cli_run.call_args.kwargs
    assert normal_kwargs["task_id"]==TASK and normal_kwargs["provider_name"]=="claude"
    assert normal_kwargs["implementation_paths"]==(IMPL,) and normal_kwargs["test_paths"]==(TEST,)
    assert normal_kwargs["retry_run_id"] is None and normal_kwargs["review_feedback_file"] is None
    assert json.loads((d/"role_results/validator_1.json").read_text())["structured_output"]["criteria_results"][1]["status"]=="not_proven"
    assert json.loads((d/"role_results/validator_1.json").read_text())["structured_output"]["criteria_results"][1]["reason_code"]=="runtime_not_executed"
    assert len({x[1].run_id for x in state.calls})==4; assert not state.clone.exists(); assert passed["implementation_actual_changed_paths"]==[IMPL] and passed["test_actual_changed_paths"]==[TEST]
    assert len(list((d/"task_execution").glob("*/task_request.json")))==4 and len(list((d/"agent_runtime").glob("*/result.json")))==4
    impl_record=json.loads((d/"role_results/implementer_1.json").read_text()); assert impl_record["role_claimed_paths"]==["claim-impl.cs"] and impl_record["agent_runtime_claimed_paths"]==["runtime-claim.cs"] and impl_record["deterministic_incremental_actual_changed_paths"]==[IMPL]
    with patch.dict(os.environ,{"NSC_EXECUTION_HEARTBEAT_SECONDS":"0.01"},clear=False), redirect_stderr(io.StringIO()): slow,state,d=execute(source,outputs,"slow",61)
    slow_events=[json.loads(line) for line in (d/"progress.jsonl").read_text().splitlines()]; heartbeats=[i for i,event in enumerate(slow_events) if event["event"]=="role_heartbeat"]
    assert slow["crew_status"]=="review_ready" and heartbeats
    for index in heartbeats:
        role=slow_events[index]["role"]; attempt=slow_events[index]["attempt"]
        completed=next(i for i,event in enumerate(slow_events) if event["event"]=="role_completed" and event["role"]==role and event["attempt"]==attempt)
        assert index < completed and not any(event["event"]=="role_heartbeat" and event["role"]==role and event["attempt"]==attempt for event in slow_events[completed+1:])
    repaired,state,d=execute(source,outputs,"repair",2); assert repaired["crew_status"]=="review_ready" and repaired["attempts_used"]==2; assert [x[0] for x in state.calls]==["contract_locality_auditor"]+["implementer","test_author","validator"]*2
    no_op,state,d=execute(source,outputs,"no_op_repair",6); assert no_op["crew_status"]=="needs_human" and [x[0] for x in state.calls]==["contract_locality_auditor","implementer","test_author","validator","implementer","test_author"]
    assert "repair cycle made no deterministic changes" in no_op["rejection_reasons"] and not (d/"candidate.patch").exists()
    twice,state,d=execute(source,outputs,"needs_twice",3); assert twice["crew_status"]=="needs_human" and not (d/"candidate.patch").exists() and (d/"workspace_diagnostic.patch").is_file(); assert len(state.calls)==7
    design,state,d=execute(source,outputs,"design",4); assert design["crew_status"]=="blocked" and len(state.calls)==4 and not (d/"candidate.patch").exists()
    blocked,state,d=execute(source,outputs,"blocker",5); assert blocked["crew_status"]=="blocked" and len(state.calls)==2 and (d/"workspace_diagnostic.patch").is_file() and not state.clone.exists()
    for i,scenario in enumerate(("impl_test","test_impl","untracked","ignored_untracked","deleted","renamed","copied","staged","head"),10):
        rejected,state,d=execute(source,outputs,scenario,i); assert rejected["crew_status"]=="rejected",scenario; assert not (d/"candidate.patch").exists(),scenario
        if scenario=="test_impl": assert any("outside role WriteBoundaries" in x for x in rejected["rejection_reasons"])
        if scenario=="ignored_untracked": assert "untracked file: bad.ignored" in rejected["rejection_reasons"]
    for i,scenario in enumerate(("criteria_missing","criteria_duplicate","criteria_unknown","pass_fail"),50):
        rejected,state,d=execute(source,outputs,scenario,i); assert rejected["crew_status"]=="rejected" and len(state.calls)==4 and not (d/"candidate.patch").exists()
        assert any("validator" in reason for reason in rejected["rejection_reasons"])
    rejected,state,d=execute(source,outputs,"final_staged",60); assert rejected["crew_status"]=="rejected" and not (d/"candidate.patch").exists() and (d/"workspace_diagnostic.patch").is_file()
    assert any("clone baseline index" in reason for reason in rejected["rejection_reasons"])
    mutated,state,d=execute(source,outputs,"source_mutation",30); assert mutated["crew_status"]=="rejected" and any("source working tree changed" in x for x in mutated["rejection_reasons"]); write(source/OTHER,"public class Other { }\n")
    assert (cmd(source,"rev-parse","HEAD"),cmd(source,"status","--porcelain=v1","--untracked-files=all"),(source/IMPL).read_bytes())==baseline

    # A future-format prior run records requested authority separately from actual changes.
    prior,prior_state,prior_dir=execute(source,outputs,"pass",70,provider="claude")
    assert prior["crew_status"]=="review_ready" and prior["review_origin"] is None
    assert prior["requested_implementation_paths"]==[IMPL] and prior["requested_test_paths"]==[TEST]
    prior_source_head=prior["source_head"]
    write(source/IMPL,"public class PlayerMana { public int Mana; }\n")
    write(source/TEST,"public class PlayerManaTests { public void ManaTest() {} }\n")
    cmd(source,"add",IMPL,TEST); cmd(source,"commit","-qm","human applied rejected candidate")
    current_head=cmd(source,"rev-parse","HEAD"); assert current_head!=prior_source_head
    assert subprocess.run(("git","-C",str(source),"merge-base","--is-ancestor",prior_source_head,current_head),check=False).returncode==0
    feedback_bytes="HUMAN_FEEDBACK_SECRET: zero mana pixels are invisible.\n".encode()
    feedback_text=feedback_bytes.decode(); feedback_dir=outputs/"feedback"; feedback_dir.mkdir()
    feedback_path=feedback_dir/"mana.txt"; feedback_path.write_bytes(feedback_bytes)

    retry_stderr=io.StringIO()
    with redirect_stderr(retry_stderr): retried,retry_state,retry_dir=retry_execute(source,outputs,"pass",71,prior["run_id"],feedback_path,feedback_text)
    assert retried["crew_status"]=="review_ready" and retried["task_id"]==TASK and retried["provider"]=="claude"
    assert retried["requested_implementation_paths"]==[IMPL] and retried["requested_test_paths"]==[TEST]
    assert retried["source_head"]==current_head and retried["source_head"]!=prior_source_head
    assert (retry_dir/"human_review_feedback.txt").read_bytes()==feedback_bytes
    feedback_sha=hashlib.sha256(feedback_bytes).hexdigest()
    assert retried["review_origin"]=={"prior_run_id":prior["run_id"],"result":"human_rejected","feedback_artifact":"human_review_feedback.txt","feedback_sha256":feedback_sha}
    assert [role for role,_,_ in retry_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    retry_telemetry=(retry_dir/"progress.jsonl").read_text()+retry_stderr.getvalue()
    assert feedback_text.strip() not in retry_telemetry and feedback_sha in retry_telemetry and prior["run_id"] in retry_telemetry
    assert any(json.loads(line)["event"]=="human_review_retry_loaded" for line in (retry_dir/"progress.jsonl").read_text().splitlines())
    assert cmd(source,"rev-parse","HEAD")==current_head and cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    # Fix 1: a feedback item mixing a production defect with a regression-test requirement must not make
    # the Implementer block merely because test paths are outside its authority; Test Author must still run.
    mixed_feedback_text=("Production defect: PlayerManaUI never shows feedback when a cast is denied.\n"
                          "Regression requirement: add a regression test asserting denied casts show feedback.\n")
    mixed_feedback_path=feedback_dir/"mixed.txt"; mixed_feedback_path.write_bytes(mixed_feedback_text.encode("utf-8"))
    mixed,mixed_state,mixed_dir=retry_execute(source,outputs,"pass",75,prior["run_id"],mixed_feedback_path,mixed_feedback_text)
    assert mixed["crew_status"]=="review_ready"
    assert [role for role,_,_ in mixed_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    mixed_impl_record=json.loads((mixed_dir/"role_results/implementer_1.json").read_text())
    assert mixed_impl_record["structured_output"]["blockers"]==[]
    mixed_impl_request=next(request for role,request,_ in mixed_state.calls if role=="implementer")
    assert "not Implementer blockers" in mixed_impl_request.prompt and "Do not modify test files" in mixed_impl_request.prompt
    assert mixed_feedback_text in mixed_impl_request.prompt

    # A genuine production-scope blocker must still stop the crew before the Test Author runs.
    blocked_retry,blocked_retry_state,blocked_retry_dir=retry_execute(source,outputs,"blocker",76,prior["run_id"],mixed_feedback_path,mixed_feedback_text)
    assert blocked_retry["crew_status"]=="blocked"
    assert [role for role,_,_ in blocked_retry_state.calls]==["contract_locality_auditor","implementer"]
    assert any("cannot implement" in reason for reason in blocked_retry["rejection_reasons"])

    # Fix 2: stable additive human-facing result, derived from existing information, never fabricated.
    mixed_expected_commands=patch_commands(mixed["candidate_patch_path"],applyable=True)
    assert mixed["human_result"]=={"status":"REVIEW_READY","reason":"The candidate passed semantic crew review and awaits human review.","artifact_path":mixed["candidate_patch_path"],"next_action":"Review candidate.patch; apply manually only if approved.","commands":mixed_expected_commands}
    assert mixed["candidate_patch_path"] is not None and Path(mixed["candidate_patch_path"]).samefile(mixed_dir/"candidate.patch")
    assert blocked_retry["human_result"]["status"]=="BLOCKED"
    # The authoritative rejection_reasons entry is preserved verbatim; the human-facing reason is a
    # fixed structural summary rather than the raw (potentially agent-authored) blocker text.
    assert blocked_retry["rejection_reasons"][0]=="implementer blocker: cannot implement"
    assert blocked_retry["human_result"]["reason"]=="The Implementer reported a blocker."
    assert blocked_retry["human_result"]["artifact_path"]==blocked_retry["workspace_diagnostic_patch_path"]
    assert Path(blocked_retry["workspace_diagnostic_patch_path"]).samefile(blocked_retry_dir/"workspace_diagnostic.patch")
    assert blocked_retry["human_result"]["next_action"]=="Inspect the diagnostic patch and blocking reason; no candidate was approved."
    blocked_retry_expected_commands=patch_commands(blocked_retry["workspace_diagnostic_patch_path"],applyable=False)
    assert blocked_retry["human_result"]["commands"]==blocked_retry_expected_commands
    assert blocked_retry_expected_commands["check"] is None and blocked_retry_expected_commands["apply"] is None

    # Fix 2/19: neither the progress telemetry nor the concise human summary leaks raw feedback text.
    mixed_summary_stderr=io.StringIO()
    with redirect_stderr(mixed_summary_stderr): print_human_summary(mixed)
    mixed_summary_text=mixed_summary_stderr.getvalue()
    assert mixed_feedback_text.strip() not in mixed_summary_text
    assert "RESULT: REVIEW_READY" in mixed_summary_text and "WHY:" not in mixed_summary_text
    assert f"ARTIFACT: {mixed['human_result']['artifact_path']}" in mixed_summary_text
    assert "NEXT: Review candidate.patch; apply manually only if approved." in mixed_summary_text
    # REVIEW_READY footer: copy/paste-ready find/check/apply/verify commands for the exact candidate path.
    assert "FIND PATCH:" in mixed_summary_text and mixed_expected_commands["find"] in mixed_summary_text
    assert "CHECK PATCH:" in mixed_summary_text and mixed_expected_commands["check"] in mixed_summary_text
    assert "APPLY PATCH:" in mixed_summary_text and mixed_expected_commands["apply"] in mixed_summary_text
    assert "VERIFY:" in mixed_summary_text and "git status --short" in mixed_summary_text and "git diff --check" in mixed_summary_text
    assert "Get-Item -LiteralPath" in mixed_summary_text

    blocked_summary_stderr=io.StringIO()
    with redirect_stderr(blocked_summary_stderr): print_human_summary(blocked_retry)
    blocked_summary_text=blocked_summary_stderr.getvalue()
    assert mixed_feedback_text.strip() not in blocked_summary_text
    assert "RESULT: BLOCKED" in blocked_summary_text
    assert f"WHY: {blocked_retry['human_result']['reason']}" in blocked_summary_text
    assert f"ARTIFACT: {blocked_retry['human_result']['artifact_path']}" in blocked_summary_text
    # Diagnostic footer: find-only, and absolutely never an apply/check command for workspace_diagnostic.patch.
    assert "FIND DIAGNOSTIC PATCH:" in blocked_summary_text and blocked_retry_expected_commands["find"] in blocked_summary_text
    assert "DO NOT APPLY:" in blocked_summary_text
    assert "This is diagnostic work from a non-review-ready run, not an approved candidate." in blocked_summary_text
    assert "git apply" not in blocked_summary_text

    # Fix (human-review retries): a blocker that literally quotes the human-review feedback back must
    # not leak that feedback into human_result.reason or the stderr summary, even though the detailed
    # rejection_reasons entry (the authoritative record) preserves it verbatim.
    assert safe_human_reason([])is None
    assert safe_human_reason(["implementer blocker: leak this text"])=="The Implementer reported a blocker."
    assert safe_human_reason(["test author blocker: leak this text"])=="The Test Author reported a blocker."
    assert safe_human_reason(["validator blocked_by_design"])=="validator blocked_by_design"
    impl_leak_retry,impl_leak_state,impl_leak_dir=retry_execute(source,outputs,"blocker_leak",77,prior["run_id"],feedback_path,feedback_text)
    assert impl_leak_retry["crew_status"]=="blocked"
    assert [role for role,_,_ in impl_leak_state.calls]==["contract_locality_auditor","implementer"]
    assert any(feedback_text.strip() in reason for reason in impl_leak_retry["rejection_reasons"])
    assert impl_leak_retry["human_result"]["reason"]=="The Implementer reported a blocker."
    impl_leak_summary_stderr=io.StringIO()
    with redirect_stderr(impl_leak_summary_stderr): print_human_summary(impl_leak_retry)
    assert feedback_text.strip() not in impl_leak_summary_stderr.getvalue()
    assert "WHY: The Implementer reported a blocker." in impl_leak_summary_stderr.getvalue()

    test_leak_retry,test_leak_state,test_leak_dir=retry_execute(source,outputs,"test_blocker_leak",78,prior["run_id"],feedback_path,feedback_text)
    assert test_leak_retry["crew_status"]=="blocked"
    assert [role for role,_,_ in test_leak_state.calls]==["contract_locality_auditor","implementer","test_author"]
    assert any(feedback_text.strip() in reason for reason in test_leak_retry["rejection_reasons"])
    assert test_leak_retry["human_result"]["reason"]=="The Test Author reported a blocker."
    test_leak_summary_stderr=io.StringIO()
    with redirect_stderr(test_leak_summary_stderr): print_human_summary(test_leak_retry)
    assert feedback_text.strip() not in test_leak_summary_stderr.getvalue()
    assert "WHY: The Test Author reported a blocker." in test_leak_summary_stderr.getvalue()

    # Fix (human-review retries): no fabricated reason. When no rejection/blocking reason was recorded,
    # human_result.reason is null and the stderr summary omits the WHY line entirely.
    no_reason_fake={"crew_status":"blocked","human_result":{"status":"BLOCKED","reason":None,"artifact_path":"/execution-output/z/workspace_diagnostic.patch","next_action":"Inspect the blocking reason; no diagnostic patch was produced."}}
    no_reason_stderr=io.StringIO()
    with redirect_stderr(no_reason_stderr): print_human_summary(no_reason_fake)
    assert "RESULT: BLOCKED" in no_reason_stderr.getvalue() and "WHY:" not in no_reason_stderr.getvalue()
    assert "ARTIFACT: /execution-output/z/workspace_diagnostic.patch" in no_reason_stderr.getvalue()
    assert "NEXT: Inspect the blocking reason; no diagnostic patch was produced." in no_reason_stderr.getvalue()

    # Fix 3: an explicit HOST output root produces exact drive-qualified host paths without disturbing
    # the existing container-path fields, and the human-facing artifact prefers the host path.
    write(source/IMPL,"public class PlayerMana { public int Mana; public int PreHostMarker; }\n")
    write(source/TEST,"public class PlayerManaTests { public void PreHostMarkerTest() {} }\n")
    cmd(source,"add",IMPL,TEST); cmd(source,"commit","-qm","pre host-root fixture state")
    HOST_ROOT=r"C:\UnityProjects\NoSafeCircleAgentCrew\NoSafeCircle\Pipeline\ExecutionCrew\outputs"
    assert validate_host_output_root(HOST_ROOT) is not None
    host_pass,host_pass_state,host_pass_dir=execute(source,outputs,"pass",90,provider="claude",host_output_root=HOST_ROOT)
    assert host_pass["crew_status"]=="review_ready"
    expected_host_candidate=f"{HOST_ROOT}\\{host_pass['run_id']}\\candidate.patch"
    assert host_pass["candidate_patch_host_path"]==expected_host_candidate
    assert host_pass["workspace_diagnostic_patch_host_path"] is None
    assert Path(host_pass["candidate_patch_path"]).samefile(host_pass_dir/"candidate.patch")
    assert host_pass["human_result"]["artifact_path"]==expected_host_candidate

    host_blocked,host_blocked_state,host_blocked_dir=execute(source,outputs,"blocker",91,provider="claude",host_output_root=HOST_ROOT)
    assert host_blocked["crew_status"]=="blocked"
    expected_host_diagnostic=f"{HOST_ROOT}\\{host_blocked['run_id']}\\workspace_diagnostic.patch"
    assert host_blocked["workspace_diagnostic_patch_host_path"]==expected_host_diagnostic
    assert host_blocked["candidate_patch_host_path"] is None
    assert Path(host_blocked["workspace_diagnostic_patch_path"]).samefile(host_blocked_dir/"workspace_diagnostic.patch")
    assert host_blocked["human_result"]["artifact_path"]==expected_host_diagnostic

    # Missing --host-output-root preserves full backward compatibility.
    no_host,_,no_host_dir=execute(source,outputs,"pass",92,provider="claude")
    assert no_host["candidate_patch_host_path"] is None and no_host["workspace_diagnostic_patch_host_path"] is None
    assert Path(no_host["candidate_patch_path"]).samefile(no_host_dir/"candidate.patch")
    assert no_host["human_result"]["artifact_path"]==no_host["candidate_patch_path"]

    # Malformed/relative Windows host roots fail closed when explicitly supplied; no run is created.
    for bad_index,bad_root in enumerate(("", "   ", "relative\\path", "C:\\Foo\\..\\Bar", "C:foo"),95):
        try: execute(source,outputs,"pass",bad_index,provider="claude",host_output_root=bad_root)
        except CrewBlocked as exc: assert "--host-output-root" in str(exc),bad_root
        else: raise AssertionError(f"invalid host-output-root accepted: {bad_root!r}")
        assert not (outputs/f"smoke-pass-{bad_index}").exists()

    # End-of-run PowerShell footer: REVIEW_READY with --host-output-root prints copy/paste-ready
    # find/check/apply/verify commands using the exact host candidate path (spec items 1-7).
    host_pass_stderr=io.StringIO()
    with redirect_stderr(host_pass_stderr): print_human_summary(host_pass)
    host_pass_footer=host_pass_stderr.getvalue()
    host_quoted=powershell_single_quote(expected_host_candidate)
    assert "RESULT: REVIEW_READY" in host_pass_footer and f"ARTIFACT: {expected_host_candidate}" in host_pass_footer
    assert "<RUN-ID>" not in host_pass_footer and host_pass["run_id"] in host_pass_footer
    assert f"FIND PATCH:\nGet-Item -LiteralPath {host_quoted}" in host_pass_footer
    assert f"CHECK PATCH:\ngit apply --check {host_quoted}" in host_pass_footer
    assert f"APPLY PATCH:\ngit apply {host_quoted}" in host_pass_footer
    assert "VERIFY:\ngit status --short\ngit diff --check" in host_pass_footer
    assert host_pass["human_result"]["commands"]=={"find":f"Get-Item -LiteralPath {host_quoted}","check":f"git apply --check {host_quoted}","apply":f"git apply {host_quoted}","verify":"git status --short; git diff --check"}

    # Blocked run with a diagnostic artifact prints FIND DIAGNOSTIC PATCH and never an apply/check
    # command for workspace_diagnostic.patch (spec items 11-14).
    host_blocked_stderr=io.StringIO()
    with redirect_stderr(host_blocked_stderr): print_human_summary(host_blocked)
    host_blocked_footer=host_blocked_stderr.getvalue()
    host_diag_quoted=powershell_single_quote(expected_host_diagnostic)
    assert "RESULT: BLOCKED" in host_blocked_footer and f"ARTIFACT: {expected_host_diagnostic}" in host_blocked_footer
    assert f"FIND DIAGNOSTIC PATCH:\nGet-Item -LiteralPath {host_diag_quoted}" in host_blocked_footer
    assert "DO NOT APPLY:" in host_blocked_footer
    assert "git apply" not in host_blocked_footer and "git apply --check" not in host_blocked_footer
    assert host_blocked["human_result"]["commands"]=={"find":f"Get-Item -LiteralPath {host_diag_quoted}","check":None,"apply":None,"verify":None}

    # Without --host-output-root, commands fall back to candidate_patch_path rather than inventing a
    # Windows path (spec item 10).
    no_host_quoted=powershell_single_quote(no_host["candidate_patch_path"])
    assert no_host["human_result"]["commands"]["find"]==f"Get-Item -LiteralPath {no_host_quoted}"
    assert no_host["human_result"]["commands"]["apply"]==f"git apply {no_host_quoted}"
    assert HOST_ROOT not in no_host["human_result"]["commands"]["find"]
    no_host_stderr=io.StringIO()
    with redirect_stderr(no_host_stderr): print_human_summary(no_host)
    assert no_host["candidate_patch_path"] in no_host_stderr.getvalue()

    # A host path containing spaces is quoted correctly, and single quotes are escaped by doubling
    # them so the result is safe to paste directly into PowerShell (spec items 8-9).
    SPACE_ROOT=r"C:\Some Folder\outputs"
    space_pass,_,space_pass_dir=execute(source,outputs,"pass",96,provider="claude",host_output_root=SPACE_ROOT)
    assert space_pass["crew_status"]=="review_ready"
    space_path=f"{SPACE_ROOT}\\{space_pass['run_id']}\\candidate.patch"
    assert space_pass["candidate_patch_host_path"]==space_path
    space_quoted=powershell_single_quote(space_path)
    assert space_quoted==f"'{space_path}'"
    assert space_pass["human_result"]["commands"]["find"]==f"Get-Item -LiteralPath {space_quoted}"
    space_stderr=io.StringIO()
    with redirect_stderr(space_stderr): print_human_summary(space_pass)
    assert f"Get-Item -LiteralPath {space_quoted}" in space_stderr.getvalue()

    QUOTE_ROOT=r"C:\Some Folder\Vincent's Project"
    quote_pass,_,quote_pass_dir=execute(source,outputs,"pass",97,provider="claude",host_output_root=QUOTE_ROOT)
    assert quote_pass["crew_status"]=="review_ready"
    quote_path=f"{QUOTE_ROOT}\\{quote_pass['run_id']}\\candidate.patch"
    assert quote_pass["candidate_patch_host_path"]==quote_path
    expected_escaped=quote_path.replace("'","''")
    assert powershell_single_quote(quote_path)==f"'{expected_escaped}'"
    assert "Vincent''s Project" in powershell_single_quote(quote_path)
    assert quote_pass["human_result"]["commands"]["apply"]==f"git apply '{expected_escaped}'"
    quote_stderr=io.StringIO()
    with redirect_stderr(quote_stderr): print_human_summary(quote_pass)
    assert f"git apply '{expected_escaped}'" in quote_stderr.getvalue()

    # A run with no artifact at all produces no apply/check/find command anywhere (spec item 15).
    no_artifact,no_artifact_state,no_artifact_dir=execute(source,outputs,"blocker_no_artifact",98)
    assert no_artifact["crew_status"]=="blocked"
    assert no_artifact["candidate_patch_path"] is None and no_artifact["workspace_diagnostic_patch_path"] is None
    assert not (no_artifact_dir/"candidate.patch").exists() and not (no_artifact_dir/"workspace_diagnostic.patch").exists()
    assert no_artifact["human_result"]["artifact_path"] is None
    assert no_artifact["human_result"]["commands"]=={"find":None,"check":None,"apply":None,"verify":None}
    no_artifact_stderr=io.StringIO()
    with redirect_stderr(no_artifact_stderr): print_human_summary(no_artifact)
    no_artifact_footer=no_artifact_stderr.getvalue()
    assert "RESULT: BLOCKED" in no_artifact_footer and "ARTIFACT: none" in no_artifact_footer
    assert "FIND" not in no_artifact_footer and "git apply" not in no_artifact_footer and "Get-Item" not in no_artifact_footer

    # stdout stays exactly one machine-readable JSON object; the footer lives only on stderr (spec 16-17).
    footer_cli_stdout=io.StringIO(); footer_cli_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=host_pass), patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), redirect_stdout(footer_cli_stdout), redirect_stderr(footer_cli_stderr):
        assert crew_main()==0
    assert json.loads(footer_cli_stdout.getvalue())==host_pass
    assert "FIND PATCH:" not in footer_cli_stdout.getvalue()
    assert "FIND PATCH:" in footer_cli_stderr.getvalue()

    # Retry repair attempt two retains human evidence and the separate Validator findings.
    repaired_retry,repaired_state,_=retry_execute(source,outputs,"repair",72,prior["run_id"],feedback_path,feedback_text)
    assert repaired_retry["crew_status"]=="review_ready" and repaired_retry["attempts_used"]==2
    for role,request,_ in repaired_state.calls:
        if role in ("implementer","test_author") and request.run_id.split("-")[-2]=="2":
            assert feedback_text in request.prompt and "VALIDATOR BLOCKING FINDINGS FROM THE PRIOR PASS" in request.prompt and "fix mana" in request.prompt

    # Legacy recovery must preserve exact granted authority, including an unchanged allowed path.
    write(source/IMPL,"public class PlayerMana { public int Mana; public int RejectedAgain; }\n")
    write(source/TEST,"public class PlayerManaTests { public void RejectedAgain() {} }\n")
    cmd(source,"add",IMPL,TEST); cmd(source,"commit","-qm","second rejected candidate fixture")
    legacy,_,legacy_dir=execute(source,outputs,"pass",73,provider="claude",implementation_paths=(IMPL,OTHER))
    assert legacy["implementation_actual_changed_paths"]==[IMPL] and legacy["requested_implementation_paths"]==[IMPL,OTHER]
    legacy_result_path=legacy_dir/"crew_result.json"; legacy_json=json.loads(legacy_result_path.read_text())
    del legacy_json["requested_implementation_paths"]; del legacy_json["requested_test_paths"]
    legacy_result_path.write_text(json.dumps(legacy_json,indent=2,sort_keys=True)+"\n")
    legacy_retry,legacy_state,_=retry_execute(source,outputs,"pass",74,legacy["run_id"],feedback_path,feedback_text)
    assert legacy_retry["requested_implementation_paths"]==[IMPL,OTHER]
    assert legacy_retry["requested_test_paths"]==[TEST]
    assert legacy_retry["implementation_actual_changed_paths"]==[IMPL]
    assert legacy_state.calls[1][1].write_boundaries.allowed_paths==(IMPL,OTHER)

    # Retry CLI has no duplicated task/provider/scope arguments.
    retry_cli_stdout=io.StringIO(); retry_cli_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as retry_cli_run, patch.object(sys,"argv",["run_crew.py","--retry-run",prior["run_id"],"--review-feedback-file",str(feedback_path),"--output-root",str(outputs)]), redirect_stdout(retry_cli_stdout), redirect_stderr(retry_cli_stderr):
        assert crew_main()==0
    retry_kwargs=retry_cli_run.call_args.kwargs
    assert retry_kwargs["task_id"] is None and retry_kwargs["provider_name"] is None
    assert retry_kwargs["implementation_paths"]==() and retry_kwargs["test_paths"]==()
    assert retry_kwargs["retry_run_id"]==prior["run_id"] and retry_kwargs["review_feedback_file"]==feedback_path
    assert retry_kwargs["host_output_root"] is None

    # --host-output-root takes precedence over the environment fallback; env is used when the CLI flag is absent.
    saved_host_env=os.environ.pop("NSC_EXECUTION_HOST_OUTPUT_ROOT",None)
    try:
        cli_host_stdout=io.StringIO(); cli_host_stderr=io.StringIO()
        with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as cli_host_run, \
             patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST,"--host-output-root","C:\\CliRoot"]), \
             patch.dict(os.environ,{"NSC_EXECUTION_HOST_OUTPUT_ROOT":"C:\\EnvRoot"},clear=False), \
             redirect_stdout(cli_host_stdout), redirect_stderr(cli_host_stderr):
            assert crew_main()==0
        assert cli_host_run.call_args.kwargs["host_output_root"]=="C:\\CliRoot"

        env_host_stdout=io.StringIO(); env_host_stderr=io.StringIO()
        with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as env_host_run, \
             patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), \
             patch.dict(os.environ,{"NSC_EXECUTION_HOST_OUTPUT_ROOT":"C:\\EnvRoot"},clear=False), \
             redirect_stdout(env_host_stdout), redirect_stderr(env_host_stderr):
            assert crew_main()==0
        assert env_host_run.call_args.kwargs["host_output_root"]=="C:\\EnvRoot"

        os.environ.pop("NSC_EXECUTION_HOST_OUTPUT_ROOT",None)
        default_host_stdout=io.StringIO(); default_host_stderr=io.StringIO()
        with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as default_host_run, \
             patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), \
             redirect_stdout(default_host_stdout), redirect_stderr(default_host_stderr):
            assert crew_main()==0
        assert default_host_run.call_args.kwargs["host_output_root"] is None
    finally:
        if saved_host_env is not None: os.environ["NSC_EXECUTION_HOST_OUTPUT_ROOT"]=saved_host_env

    # Fix 2: stdout stays exactly one parseable machine-readable JSON object; the concise human summary
    # goes only to stderr, and its shape differs for review_ready versus a blocked/rejected result.
    review_ready_fake={"crew_status":"review_ready","human_result":{"status":"REVIEW_READY","reason":"The candidate passed semantic crew review and awaits human review.","artifact_path":"/execution-output/x/candidate.patch","next_action":"Review candidate.patch; apply manually only if approved."}}
    rr_stdout=io.StringIO(); rr_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=review_ready_fake), patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), redirect_stdout(rr_stdout), redirect_stderr(rr_stderr):
        assert crew_main()==0
    assert json.loads(rr_stdout.getvalue())==review_ready_fake
    assert "RESULT:" not in rr_stdout.getvalue()
    try: json.loads(rr_stderr.getvalue())
    except json.JSONDecodeError: pass
    else: raise AssertionError("stderr summary must not itself be parseable result JSON")
    assert "RESULT: REVIEW_READY" in rr_stderr.getvalue() and "WHY:" not in rr_stderr.getvalue()
    assert "ARTIFACT: /execution-output/x/candidate.patch" in rr_stderr.getvalue()
    assert "NEXT: Review candidate.patch; apply manually only if approved." in rr_stderr.getvalue()

    blocked_fake={"crew_status":"blocked","human_result":{"status":"BLOCKED","reason":"implementer blocker: cannot implement","artifact_path":"/execution-output/y/workspace_diagnostic.patch","next_action":"Inspect the diagnostic patch and blocking reason; no candidate was approved."}}
    bl_stdout=io.StringIO(); bl_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=blocked_fake), patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), redirect_stdout(bl_stdout), redirect_stderr(bl_stderr):
        assert crew_main()==1
    assert json.loads(bl_stdout.getvalue())==blocked_fake
    assert "RESULT: BLOCKED" in bl_stderr.getvalue() and "WHY: implementer blocker: cannot implement" in bl_stderr.getvalue()
    assert "ARTIFACT: /execution-output/y/workspace_diagnostic.patch" in bl_stderr.getvalue()
    assert "NEXT: Inspect the diagnostic patch and blocking reason; no candidate was approved." in bl_stderr.getvalue()

    # Preflight/orchestration failures raised before any crew_result exists (dirty checkout, invalid
    # retry artifacts, clone/preflight failure, invalid --host-output-root, source identity failure, ...)
    # must still end with the human-facing footer: no candidate/diagnostic artifact ever exists here.
    for exc in (
        CrewBlocked("source working tree must be completely clean, including untracked files"),
        ValueError("boom"),
        OSError("disk exploded"),
        subprocess.CalledProcessError(1, ["git", "clone"]),
    ):
        exc_stdout=io.StringIO(); exc_stderr=io.StringIO()
        with patch("Pipeline.ExecutionCrew.run_crew.run_crew",side_effect=exc), patch.object(sys,"argv",["run_crew.py","--task-id",TASK,"--provider","claude","--implementation-path",IMPL,"--test-path",TEST]), redirect_stdout(exc_stdout), redirect_stderr(exc_stderr):
            assert crew_main()==2
        assert exc_stdout.getvalue()==""
        exc_stderr_text=exc_stderr.getvalue()
        assert f"ExecutionCrew blocked: {exc}" in exc_stderr_text
        assert "RESULT: BLOCKED" in exc_stderr_text
        assert f"WHY: {exc}" in exc_stderr_text
        assert "ARTIFACT: none" in exc_stderr_text
        assert "NEXT: Resolve the blocking condition and rerun ExecutionCrew." in exc_stderr_text
        assert "FIND" not in exc_stderr_text and "CHECK PATCH" not in exc_stderr_text and "APPLY PATCH" not in exc_stderr_text and "git apply" not in exc_stderr_text

    def copied_prior(new_id, mutate):
        destination=outputs/new_id; shutil.copytree(prior_dir,destination)
        value=json.loads((destination/"crew_result.json").read_text()); value["run_id"]=new_id; mutate(value)
        (destination/"crew_result.json").write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
        return destination

    def expect_retry_blocked(prior_id, feedback, run_id, expected):
        blocked_state=State("pass",source,feedback_text)
        try: run_crew(source=source,output_root=outputs,run_id=run_id,retry_run_id=prior_id,review_feedback_file=feedback,provider_factory=factory(blocked_state),_require_physical_read_only_source=False)
        except CrewBlocked as exc: assert expected in str(exc),str(exc)
        else: raise AssertionError(f"retry unexpectedly accepted: {run_id}")
        assert not blocked_state.calls

    copied_prior("prior-not-ready",lambda value:value.__setitem__("crew_status","needs_human"))
    expect_retry_blocked("prior-not-ready",feedback_path,"fail-status","review_ready")
    copied_prior("prior-bad-validator",lambda value:value.__setitem__("validator_status","needs_changes"))
    expect_retry_blocked("prior-bad-validator",feedback_path,"fail-validator","validator_status pass")
    copied_prior("prior-bad-scope",lambda value:value.__setitem__("requested_implementation_paths",[IMPL,OTHER]))
    expect_retry_blocked("prior-bad-scope",feedback_path,"fail-scope","does not match authoritative")
    copied_prior("prior-bad-tree",lambda value:value.__setitem__("source_tree","0"*40))
    expect_retry_blocked("prior-bad-tree",feedback_path,"fail-tree","cannot be proven")
    copied_prior("prior-bad-provider",lambda value:value.__setitem__("provider","mixed"))
    expect_retry_blocked("prior-bad-provider",feedback_path,"fail-provider","invalid provider")
    invalid_json=outputs/"prior-invalid-json"; invalid_json.mkdir(); (invalid_json/"crew_result.json").write_text("[]\n")
    expect_retry_blocked("prior-invalid-json",feedback_path,"fail-json","JSON object")
    missing_result=outputs/"prior-missing-result"; missing_result.mkdir()
    expect_retry_blocked("prior-missing-result",feedback_path,"fail-result-missing","crew_result.json")
    expect_retry_blocked("prior-missing",feedback_path,"fail-missing","prior run")
    for index,bad_id in enumerate(("../escape","nested/run","/absolute",".."),80):
        expect_retry_blocked(bad_id,feedback_path,f"fail-id-{index}","single conservative run ID")

    orphan_head=cmd(source,"commit-tree",cmd(source,"rev-parse","HEAD^{tree}"),"-m","unrelated prior")
    copied_prior("prior-unrelated",lambda value:(value.__setitem__("source_head",orphan_head),value.__setitem__("source_tree",cmd(source,"rev-parse",f"{orphan_head}^{{tree}}"))))
    expect_retry_blocked("prior-unrelated",feedback_path,"fail-ancestor","must be an ancestor")

    outside_feedback=root/"outside-feedback.txt"; outside_feedback.write_text("outside\n")
    expect_retry_blocked(prior["run_id"],outside_feedback,"fail-feedback-outside","strictly underneath")
    expect_retry_blocked(prior["run_id"],feedback_dir/"missing.txt","fail-feedback-missing","does not exist")
    empty_feedback=feedback_dir/"empty.txt"; empty_feedback.write_bytes(b"")
    expect_retry_blocked(prior["run_id"],empty_feedback,"fail-feedback-empty","non-empty")
    invalid_feedback=feedback_dir/"invalid.txt"; invalid_feedback.write_bytes(b"\xff")
    expect_retry_blocked(prior["run_id"],invalid_feedback,"fail-feedback-utf8","valid UTF-8")
    oversized_feedback=feedback_dir/"oversized.txt"; oversized_feedback.write_bytes(b"x"*(64*1024+1))
    expect_retry_blocked(prior["run_id"],oversized_feedback,"fail-feedback-size","at most 65536")
    feedback_directory=feedback_dir/"directory"; feedback_directory.mkdir()
    expect_retry_blocked(prior["run_id"],feedback_directory,"fail-feedback-regular","regular file")
    try:
        escaped_feedback=feedback_dir/"escaped.txt"; escaped_feedback.symlink_to(outside_feedback)
        expect_retry_blocked(prior["run_id"],escaped_feedback,"fail-feedback-symlink","strictly underneath")
        outside_prior=root/"outside-prior"; shutil.copytree(prior_dir,outside_prior)
        (outputs/"escaped-prior").symlink_to(outside_prior,target_is_directory=True)
        expect_retry_blocked("escaped-prior",feedback_path,"fail-prior-symlink","strictly underneath")
    except (OSError, NotImplementedError):
        pass

    # Contract Locality Auditor: mandatory, read-only, runs before the Implementer. When it reports
    # contract_review_required, no Implementer/Test Author/Validator invocation ever happens.
    locality_required,locality_state,locality_dir=execute(source,outputs,"locality_review_required",100)
    assert locality_required["crew_status"]=="contract_review_required"
    assert [role for role,_,_ in locality_state.calls]==["contract_locality_auditor"]
    assert locality_required["attempts_used"]==0 and locality_required["validator_status"] is None
    assert locality_required["candidate_patch_path"] is None and locality_required["workspace_diagnostic_patch_path"] is None
    assert not (locality_dir/"candidate.patch").exists() and not (locality_dir/"workspace_diagnostic.patch").exists()
    assert locality_required["contract_locality_status"]=="contract_review_required"
    assert locality_required["contract_locality_audit_path"] is not None
    assert Path(locality_required["contract_locality_audit_path"]).samefile(locality_dir/"contract_locality_audit.json")
    locality_audit=json.loads((locality_dir/"contract_locality_audit.json").read_text())
    assert locality_audit["schema_version"]=="1.0" and locality_audit["result"]["status"]=="contract_review_required"
    assert [f["entry_id"] for f in locality_audit["result"]["blocking_findings"]]==["VAL-001"]
    assert locality_audit["result"]["blocking_findings"][0]["reason_code"]=="requires_declared_dependency"
    assert locality_audit["result"]["blocking_findings"][0]["related_task_ids"]==[RELATED_TASK]
    assert locality_required["human_result"]["status"]=="CONTRACT_REVIEW_REQUIRED"
    assert locality_required["human_result"]["reason"]==("The committed task contract contains one or more AC/VAL items that are not locally "
                                                           "implementable/provable under its current scope or dependencies.")
    assert locality_required["human_result"]["next_action"]==("Review the audit, repair the task contract through normal human-reviewed TaskGraph "
                                                                "workflow, validate the graph, and rerun ExecutionCrew.")
    assert locality_required["human_result"]["artifact_path"]==locality_required["contract_locality_audit_path"]
    assert locality_required["human_result"]["commands"]==audit_commands(locality_required["contract_locality_audit_path"])
    assert locality_required["human_next_step"]==locality_required["human_result"]["next_action"]
    locality_footer=io.StringIO()
    with redirect_stderr(locality_footer): print_human_summary(locality_required)
    locality_footer_text=locality_footer.getvalue()
    assert "RESULT: CONTRACT_REVIEW_REQUIRED" in locality_footer_text
    assert f"WHY: {locality_required['human_result']['reason']}" in locality_footer_text
    assert f"ARTIFACT: {locality_required['human_result']['artifact_path']}" in locality_footer_text
    assert "FIND AUDIT:" in locality_footer_text and "INSPECT AUDIT:" in locality_footer_text
    assert audit_commands(locality_required["contract_locality_audit_path"])["find"] in locality_footer_text
    assert audit_commands(locality_required["contract_locality_audit_path"])["inspect"] in locality_footer_text
    assert f"NEXT: {locality_required['human_result']['next_action']}" in locality_footer_text
    # No patch exists in this result: never print patch or diagnostic-patch wording.
    for forbidden in ("FIND PATCH:", "CHECK PATCH:", "APPLY PATCH:", "FIND DIAGNOSTIC PATCH:", "DO NOT APPLY:", "git apply"):
        assert forbidden not in locality_footer_text
    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    # requires_declared_dependency deterministically requires a nonempty, actionable related_task_ids
    # naming a task that exists in the validated persistent graph, and the matching blocking finding
    # must repeat the exact same related_task_ids. An empty array, or a mismatch between the
    # entry_results and blocking_findings related_task_ids, is an invalid (rejected) audit result.
    empty_related,empty_related_state,empty_related_dir=execute(source,outputs,"locality_add_dependency_empty_related",104)
    assert empty_related["crew_status"]=="rejected"
    assert [role for role,_,_ in empty_related_state.calls]==["contract_locality_auditor"]
    assert empty_related["contract_locality_status"] is None and empty_related["contract_locality_audit_path"] is None
    assert not (empty_related_dir/"contract_locality_audit.json").exists()
    assert empty_related["candidate_patch_path"] is None
    assert any("requires a nonempty related_task_ids" in reason for reason in empty_related["rejection_reasons"])
    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    mismatch_related,mismatch_related_state,mismatch_related_dir=execute(source,outputs,"locality_add_dependency_mismatch",105)
    assert mismatch_related["crew_status"]=="rejected"
    assert [role for role,_,_ in mismatch_related_state.calls]==["contract_locality_auditor"]
    assert mismatch_related["contract_locality_status"] is None and mismatch_related["contract_locality_audit_path"] is None
    assert not (mismatch_related_dir/"contract_locality_audit.json").exists()
    assert mismatch_related["candidate_patch_path"] is None
    assert any("related_task_ids must match entry related_task_ids" in reason for reason in mismatch_related["rejection_reasons"])
    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    # An internally inconsistent (invalid) auditor output stops the run before the Implementer as a
    # rejected/invalid audit, not silently as contract_review_required and not as a passthrough pass.
    locality_invalid,locality_invalid_state,locality_invalid_dir=execute(source,outputs,"locality_invalid",101)
    assert locality_invalid["crew_status"]=="rejected"
    assert [role for role,_,_ in locality_invalid_state.calls]==["contract_locality_auditor"]
    assert locality_invalid["contract_locality_status"] is None and locality_invalid["contract_locality_audit_path"] is None
    assert not (locality_invalid_dir/"contract_locality_audit.json").exists()
    assert locality_invalid["candidate_patch_path"] is None
    assert any(reason.startswith("contract locality auditor: ") for reason in locality_invalid["rejection_reasons"])
    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    # A locally provable task contract passes the audit and continues through the normal crew flow.
    locality_pass,locality_pass_state,locality_pass_dir=execute(source,outputs,"pass",102)
    assert locality_pass["crew_status"]=="review_ready"
    assert [role for role,_,_ in locality_pass_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    assert locality_pass["contract_locality_status"]=="pass"

    # An NSC-012-like contract: single_agent/concrete/self-contained wording that explicitly disclaims
    # pursuit, attacks, search, and navigation, yet BOTH of its completion gates actually require
    # nonlocal behavior: real pursuit/attack-controller shutdown and leaving play (owned by the
    # enemy's own pursuit/attack controller, a downstream consumer of this task's defeat state) and
    # real target-loss/search/room-crossing behavior (owned by NSC-014, Enemy Pursuit/Search
    # Foundation). The mandatory pre-Implementer audit must catch both before any writer role runs,
    # identify both exact nonlocal gate IDs, and route to CONTRACT_REVIEW_REQUIRED.
    nsc012_clone=root/"nsc012-like"; subprocess.run(("git","clone","-q",str(source),str(nsc012_clone)),check=True)
    cmd(nsc012_clone,"config","user.name","Crew Smoke"); cmd(nsc012_clone,"config","user.email","crew@example.invalid")
    (nsc012_clone/f"Tasks/{RELATED_TASK}.yaml").unlink()
    nsc012_task={
        "schema_version":"2.0","id":TASK,"contract_revision":4,"contract_disposition":"active",
        "title":"Enemy Health/Defeat","reconciliation_key":"enemy-health-damage-defeat","kind":"implementation",
        "type":"implementation","execution_scope":"single_agent",
        "execution_reason":"A cohesive, bounded, self-contained component that one agent can implement and validate without needing to also implement pursuit, attacks, search, or navigation.",
        "decomposition_state":"concrete",
        "decomposition_reason":"The GDD fully specifies health/damage/defeat ownership and reset participation; no missing design blocks a bounded implementation item.",
        "parent":"NSC-001","depends_on":[],"exclusive_resources":[],
        "acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Health/damage/defeat state is owned and tracked locally by this task."}],
        "completion_gates":[
            {"gate_id":"VAL-001","reference":"fixture","requirement":"Verify a defeated enemy's own pursuit/attack controller shuts down immediately and the enemy leaves active play following the defeat transition."},
            {"gate_id":"VAL-002","reference":"fixture","requirement":"Verify that once this enemy is defeated, other active enemies correctly register target-loss and resume search behavior across room crossings."},
        ],
        "downstream_integration_obligations":[],"provenance":{"origin":"fixture"},
    }
    nsc014_task={
        "schema_version":"2.0","id":"NSC-014","contract_revision":1,"contract_disposition":"active",
        "title":"Enemy Pursuit/Search Foundation","reconciliation_key":"enemy-pursuit-search-foundation","kind":"implementation",
        "type":"implementation","execution_scope":"single_agent",
        "execution_reason":"Owns pursuit and target-loss/search behavior across room crossings for enemies.",
        "decomposition_state":"concrete","decomposition_reason":"GDD specifies pursuit/search ownership.",
        "parent":"NSC-001","depends_on":[],"exclusive_resources":[],
        "acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Pursuit/search behavior is implemented."}],
        "completion_gates":[{"gate_id":"VAL-001","reference":"fixture","requirement":"Pursuit/search behavior is verified."}],
        "downstream_integration_obligations":[],"provenance":{"origin":"fixture"},
    }
    write_persistent_graph(nsc012_clone,[root_task(),nsc012_task,nsc014_task])
    cmd(nsc012_clone,"add","."); cmd(nsc012_clone,"commit","-qm","nsc-012-like fixture")
    nsc012_head=cmd(nsc012_clone,"rev-parse","HEAD")
    nsc012,nsc012_state,nsc012_dir=execute(nsc012_clone,outputs,"nsc012_like",103)
    assert nsc012["crew_status"]=="contract_review_required"
    assert [role for role,_,_ in nsc012_state.calls]==["contract_locality_auditor"]
    assert sum(1 for role,_,_ in nsc012_state.calls if role=="implementer")==0
    assert sum(1 for role,_,_ in nsc012_state.calls if role=="test_author")==0
    assert sum(1 for role,_,_ in nsc012_state.calls if role=="validator")==0
    assert nsc012["attempts_used"]==0 and nsc012["validator_status"] is None
    assert nsc012["candidate_patch_path"] is None and nsc012["workspace_diagnostic_patch_path"] is None
    assert not (nsc012_dir/"candidate.patch").exists() and not (nsc012_dir/"workspace_diagnostic.patch").exists()
    assert nsc012["contract_locality_status"]=="contract_review_required"
    nsc012_audit=json.loads((nsc012_dir/"contract_locality_audit.json").read_text())
    nsc012_entries={entry["id"]:entry for entry in nsc012_audit["result"]["entry_results"]}
    assert nsc012_entries["VAL-001"]["classification"]!="local_to_task"
    assert nsc012_entries["VAL-002"]["classification"]!="local_to_task"
    assert nsc012_entries["VAL-001"]["classification"] in ("downstream_integration","requires_declared_dependency")
    assert nsc012_entries["VAL-002"]["classification"] in ("downstream_integration","requires_declared_dependency")
    blocking_ids=[f["entry_id"] for f in nsc012_audit["result"]["blocking_findings"]]
    assert set(blocking_ids)=={"VAL-001","VAL-002"}
    assert nsc012["human_result"]["status"]=="CONTRACT_REVIEW_REQUIRED"
    assert cmd(nsc012_clone,"rev-parse","HEAD")==nsc012_head
    assert cmd(nsc012_clone,"status","--porcelain=v1","--untracked-files=all")==""

    # Validator structured reason_code is a second safety boundary. An overall pass may only carry a
    # not_proven item whose reason_code is runtime_not_executed; any other not_proven reason_code is a
    # rejected (invalid) validator output, never a silent pass.
    reason_pass_invalid,rpi_state,rpi_dir=execute(source,outputs,"reason_code_pass_invalid",110)
    assert reason_pass_invalid["crew_status"]=="rejected"
    assert [role for role,_,_ in rpi_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    assert any("reason_code" in reason for reason in reason_pass_invalid["rejection_reasons"])
    assert not (rpi_dir/"candidate.patch").exists()

    reason_mismatch,rm_state,rm_dir=execute(source,outputs,"reason_code_mismatch",111)
    assert reason_mismatch["crew_status"]=="rejected"
    assert any("incompatible with reason_code" in reason for reason in reason_mismatch["rejection_reasons"])

    # status=fail requires reason_code=criterion_failed; any other reason_code on a fail item is rejected.
    reason_fail_invalid,rfi_state,rfi_dir=execute(source,outputs,"reason_code_fail_invalid",114)
    assert reason_fail_invalid["crew_status"]=="rejected"
    assert any("incompatible with reason_code" in reason for reason in reason_fail_invalid["rejection_reasons"])
    assert not (rfi_dir/"candidate.patch").exists()

    # blocked_by_design with reason_code=missing_integration_dependency or design_ambiguity routes the
    # crew to CONTRACT_REVIEW_REQUIRED (fallback safety boundary), not a generic BLOCKED result, even
    # though the mandatory pre-Implementer audit already passed and writers already ran.
    for index,scenario,expected_reason_code in ((112,"validator_missing_integration_dependency","missing_integration_dependency"),(113,"validator_design_ambiguity","design_ambiguity")):
        fallback,fallback_state,fallback_dir=execute(source,outputs,scenario,index)
        assert fallback["crew_status"]=="contract_review_required",scenario
        assert [role for role,_,_ in fallback_state.calls]==["contract_locality_auditor","implementer","test_author","validator"],scenario
        assert fallback["validator_status"]=="blocked_by_design",scenario
        assert fallback["contract_locality_status"]=="pass",scenario
        validator_record=json.loads((fallback_dir/"role_results/validator_1.json").read_text())
        assert validator_record["structured_output"]["criteria_results"][1]["reason_code"]==expected_reason_code,scenario
        assert fallback["candidate_patch_path"] is None,scenario
        assert fallback["workspace_diagnostic_patch_path"] is not None,scenario
        assert Path(fallback["workspace_diagnostic_patch_path"]).samefile(fallback_dir/"workspace_diagnostic.patch"),scenario
        assert fallback["human_result"]["status"]=="CONTRACT_REVIEW_REQUIRED",scenario
        # Fallback artifact is the diagnostic patch (writers already ran), not the (already-passed) audit.
        assert fallback["human_result"]["artifact_path"]==fallback["workspace_diagnostic_patch_path"],scenario
        assert fallback["human_result"]["commands"]==patch_commands(fallback["workspace_diagnostic_patch_path"],applyable=False),scenario
        fallback_footer=io.StringIO()
        with redirect_stderr(fallback_footer): print_human_summary(fallback)
        fallback_footer_text=fallback_footer.getvalue()
        assert "RESULT: CONTRACT_REVIEW_REQUIRED" in fallback_footer_text,scenario
        assert "FIND DIAGNOSTIC PATCH:" in fallback_footer_text and "DO NOT APPLY:" in fallback_footer_text,scenario
        assert "git apply" not in fallback_footer_text,scenario
        assert "FIND AUDIT:" not in fallback_footer_text and "INSPECT AUDIT:" not in fallback_footer_text,scenario

    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

    # The persistent task graph: production behavior loads and validates the real, authoritative
    # persistent work graph (BOOTSTRAP_PERSISTED.json, WORK_ID_MAP.json, PROJECT_REQUIREMENTS.yaml,
    # RESOURCE_GROUPS.yaml, parent hierarchy, dependency graph, resource-group symmetry) via
    # load_persistent_work_graph, strictly before the Contract Locality Auditor is ever invoked.
    def task_catalog_from_disk(graph_root):
        catalog={}
        for path in sorted((graph_root/"Tasks").glob("NSC-*.yaml")):
            catalog[json.loads(path.read_text(encoding="utf-8-sig"))["id"]]=json.loads(path.read_text(encoding="utf-8-sig"))
        return catalog
    graph_loader_calls=[]; graph_loader_state=State("pass",source)
    def recording_graph_loader(graph_root):
        assert not graph_loader_state.calls, "persistent graph loader must run before any provider role invocation"
        graph_loader_calls.append(graph_root)
        return SimpleNamespace(tasks_by_id=task_catalog_from_disk(graph_root))
    with patch("Pipeline.ExecutionCrew.run_crew.load_persistent_work_graph",side_effect=recording_graph_loader):
        graph_default_result=run_crew(source=source,output_root=outputs,task_id=TASK,provider_name="fake",implementation_paths=(IMPL,),test_paths=(TEST,),run_id="graph-loader-default-120",provider_factory=factory(graph_loader_state),_require_physical_read_only_source=False)
    assert graph_default_result["crew_status"]=="review_ready"
    assert graph_loader_calls==[source.resolve()]
    assert [role for role,_,_ in graph_loader_state.calls][0]=="contract_locality_auditor"

    # A persistent-graph validation failure (here: a missing bootstrap completion marker) blocks
    # before any provider role is invoked, using the real production default loader (not mocked),
    # and no audit artifact or patch is ever produced for a graph-preflight failure.
    broken_graph_clone=root/"broken-persistent-graph"; subprocess.run(("git","clone","-q",str(source),str(broken_graph_clone)),check=True)
    cmd(broken_graph_clone,"config","user.name","Crew Smoke"); cmd(broken_graph_clone,"config","user.email","crew@example.invalid")
    (broken_graph_clone/"Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json").unlink()
    cmd(broken_graph_clone,"add","."); cmd(broken_graph_clone,"commit","-qm","corrupt persistent graph")
    broken_graph_head=cmd(broken_graph_clone,"rev-parse","HEAD")
    broken_graph_state=State("pass",broken_graph_clone); broken_graph_run_id="graph-preflight-fail-121"
    try:
        run_crew(source=broken_graph_clone,output_root=outputs,task_id=TASK,provider_name="fake",implementation_paths=(IMPL,),test_paths=(TEST,),run_id=broken_graph_run_id,provider_factory=factory(broken_graph_state),_require_physical_read_only_source=False)
    except CrewBlocked as exc:
        assert "persistent work graph" in str(exc)
    else:
        raise AssertionError("invalid persistent graph was accepted")
    assert not broken_graph_state.calls
    broken_graph_dir=outputs/broken_graph_run_id
    assert not (broken_graph_dir/"contract_locality_audit.json").exists()
    assert not (broken_graph_dir/"candidate.patch").exists()
    assert not (broken_graph_dir/"workspace_diagnostic.patch").exists()
    assert cmd(broken_graph_clone,"rev-parse","HEAD")==broken_graph_head
    assert cmd(broken_graph_clone,"status","--porcelain=v1","--untracked-files=all")==""

    # Pre-feature human-review retries: a review_ready prior run created before the Contract Locality
    # Auditor existed (no auditor TaskExecution request/result, no contract_locality_* crew_result
    # fields, no contract_locality_audit.json) must still recover scope and retry successfully. The
    # prior Validator TaskExecution and prior Implementer/Test Author WriteBoundaries remain
    # authoritative and required; a prior auditor is optional; the retry never trusts a prior audit
    # and always runs the mandatory current auditor before the Implementer.
    pre_feature_prior,pre_feature_state,pre_feature_dir=execute(source,outputs,"pass",130,provider="claude")
    assert pre_feature_prior["crew_status"]=="review_ready"
    assert [role for role,_,_ in pre_feature_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    auditor_request_dirs=[p.parent for p in (pre_feature_dir/"task_execution").glob("*/task_request.json")
                           if json.loads(p.read_text())["invocation"]["role"]=="contract_locality_auditor"]
    assert len(auditor_request_dirs)==1
    auditor_agent_runtime_dir=None
    for candidate in (pre_feature_dir/"agent_runtime").glob("*"):
        request_json=candidate/"request.json"
        if request_json.is_file() and json.loads(request_json.read_text()).get("role")=="contract_locality_auditor":
            auditor_agent_runtime_dir=candidate; break
    shutil.rmtree(auditor_request_dirs[0])
    (pre_feature_dir/"role_results/contract_locality_auditor_1.json").unlink()
    if auditor_agent_runtime_dir is not None: shutil.rmtree(auditor_agent_runtime_dir)
    pre_feature_result_path=pre_feature_dir/"crew_result.json"
    pre_feature_json=json.loads(pre_feature_result_path.read_text())
    for field in ("contract_locality_status","contract_locality_audit_path","contract_locality_audit_host_path"):
        pre_feature_json.pop(field,None)
    pre_feature_json["role_results"]=[p for p in pre_feature_json["role_results"] if p!="role_results/contract_locality_auditor_1.json"]
    pre_feature_result_path.write_text(json.dumps(pre_feature_json,indent=2,sort_keys=True)+"\n")
    (pre_feature_dir/"contract_locality_audit.json").unlink(missing_ok=True)
    assert not (pre_feature_dir/"contract_locality_audit.json").exists()

    pre_feature_head=pre_feature_json["source_head"]
    write(source/IMPL,"public class PlayerMana { public int Mana; public int PreFeatureMarker; }\n")
    write(source/TEST,"public class PlayerManaTests { public void PreFeatureMarkerTest() {} }\n")
    cmd(source,"add",IMPL,TEST); cmd(source,"commit","-qm","pre-feature retry fixture state")
    pre_feature_current_head=cmd(source,"rev-parse","HEAD"); assert pre_feature_current_head!=pre_feature_head
    assert subprocess.run(("git","-C",str(source),"merge-base","--is-ancestor",pre_feature_head,pre_feature_current_head),check=False).returncode==0
    pre_feature_feedback_text="PRE_FEATURE_FEEDBACK_SECRET: mana regen was too slow.\n"
    pre_feature_feedback_path=feedback_dir/"pre-feature.txt"; pre_feature_feedback_path.write_bytes(pre_feature_feedback_text.encode("utf-8"))

    pre_feature_retry,pre_feature_retry_state,pre_feature_retry_dir=retry_execute(source,outputs,"pass",131,pre_feature_json["run_id"],pre_feature_feedback_path,pre_feature_feedback_text)
    assert pre_feature_retry["crew_status"]=="review_ready"
    assert [role for role,_,_ in pre_feature_retry_state.calls]==["contract_locality_auditor","implementer","test_author","validator"]
    assert pre_feature_retry["requested_implementation_paths"]==[IMPL] and pre_feature_retry["requested_test_paths"]==[TEST]
    assert pre_feature_retry["contract_locality_status"]=="pass" and pre_feature_retry["contract_locality_audit_path"] is not None
    assert Path(pre_feature_retry["contract_locality_audit_path"]).samefile(pre_feature_retry_dir/"contract_locality_audit.json")

    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""
  print("execution crew smoke: PASS (fake providers only; Unity not invoked)"); return 0
if __name__=="__main__": raise SystemExit(main())
