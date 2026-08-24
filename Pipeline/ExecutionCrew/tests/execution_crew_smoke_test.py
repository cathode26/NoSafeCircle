#!/usr/bin/env python3
"""Deterministic three-role ExecutionCrew smoke; no Unity or live provider calls."""
from __future__ import annotations
import hashlib, io, json, os, shutil, subprocess, sys, tempfile, time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import Usage
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse
from Pipeline.ExecutionCrew.run_crew import CrewBlocked, Snapshot, changed_paths, clone_exact, construct_real_provider, main as crew_main, run_crew, runtime_configuration

TASK="NSC-005"; IMPL="Assets/Scripts/PlayerMana.cs"; TEST="Assets/Tests/PlayerManaTests.cs"; OTHER="Assets/Scripts/Other.cs"; SECRET="FULL_ROLE_PROMPT_SENTINEL_SECRET"
def cmd(root,*args): return subprocess.run(("git","-C",str(root),*args),check=True,stdout=subprocess.PIPE,text=True).stdout.strip()
def write(path,text): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")
def fixture(parent):
    root=parent/"source"; root.mkdir(); subprocess.run(("git","init","-q",str(root)),check=True); cmd(root,"config","user.name","Crew Smoke"); cmd(root,"config","user.email","crew@example.invalid")
    write(root/IMPL,"public class PlayerMana { }\n"); write(root/TEST,"public class PlayerManaTests { }\n"); write(root/OTHER,"public class Other { }\n"); write(root/".gitignore","*.ignored\n")
    task={"schema_version":"2.0","id":TASK,"contract_revision":3,"contract_disposition":"active","title":"Mana","kind":"implementation","execution_scope":"single_agent","decomposition_state":"concrete","acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Mana behavior is implemented."}],"completion_gates":[{"gate_id":"VAL-001","reference":"fixture","requirement":"Unity behavior is verified."}],"downstream_integration_obligations":[],"provenance":{"origin":"fixture"}}
    write(root/f"Tasks/{TASK}.yaml",json.dumps(task)+"\n"); write(root/"Docs/GDD/No_Safe_Circle_GDD.md",f"# GDD\n{SECRET}\n"); write(root/"Docs/Engineering/UNITY_TESTING_POLICY.md","# Policy\nNever claim tests passed.\n")
    cmd(root,"add","."); cmd(root,"commit","-qm","baseline"); return root

class State:
    def __init__(self,scenario,source,feedback=None): self.scenario=scenario; self.source=source; self.feedback=feedback; self.calls=[]; self.clone=None

class FakeProvider:
    provider_identifier="fake"
    def __init__(self,state,repo,writable,role): self.state=state; self.repo=repo; self.writable=writable; self.role=role
    def invoke(self,request,model):
        s=self.state; attempt=sum(1 for r,_,_ in s.calls if r==self.role)+1; s.calls.append((self.role,request,model))
        assert request.role==self.role
        if s.feedback:
            assert "HUMAN REVIEW REJECTION FROM PRIOR REVIEW-READY CANDIDATE" in request.prompt
            assert s.feedback in request.prompt
            if self.role=="implementer":
                assert "presence is NOT evidence that the task is complete" in request.prompt and "report a blocker" in request.prompt
            elif self.role=="test_author":
                assert "Add regression coverage" in request.prompt and "approved test paths" in request.prompt
            else:
                assert "A Validator pass must not ignore an unresolved human-review rejection" in request.prompt
        if s.scenario=="slow" and self.role=="implementer": time.sleep(.06)
        if self.role=="validator":
            assert not self.writable and self.repo.resolve()==s.source.resolve(); assert "repository_write" not in request.allowed_capabilities; assert not request.write_boundaries.allowed_paths
            exact=subprocess.run(("git","-C",str(s.clone),"diff","--binary","--full-index","--no-ext-diff","--no-renames",cmd(s.source,"rev-parse","HEAD")),check=True,stdout=subprocess.PIPE,text=True).stdout
            assert f"EXACT FULL CANDIDATE GIT PATCH\n---\n{exact}\n---" in request.prompt and "public int Mana" in request.prompt
            for required in ("baseline repository is intentionally unchanged", "authoritative proposed delta", "Absence of candidate changes from the baseline source is not a failure reason", "Do not request that the candidate be committed or applied to the real source before semantic validation", "Runtime or Unity evidence that was not executed remains not_proven"):
                assert required in request.prompt
            if s.scenario=="needs_twice": status="needs_changes"
            elif s.scenario in ("repair","no_op_repair") and attempt==1: status="needs_changes"
            elif s.scenario=="design": status="blocked_by_design"
            else: status="pass"
            criteria=[{"id":"AC-001","status":"pass","evidence":"source review"},{"id":"VAL-001","status":"not_proven","evidence":"Unity was not run"}]
            if s.scenario=="criteria_missing": criteria=criteria[:1]
            elif s.scenario=="criteria_duplicate": criteria=[criteria[0],criteria[0],criteria[1]]
            elif s.scenario=="criteria_unknown": criteria.append({"id":"AC-999","status":"pass","evidence":"unknown"})
            elif s.scenario=="pass_fail": criteria[0]={"id":"AC-001","status":"fail","evidence":"defect"}
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
            else:
                if attempt==2: assert "fix mana" in request.prompt
                if not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/IMPL,"public class PlayerMana { public int Mana;"+(" public int HumanReviewFixed;" if s.feedback else "")+(" public int Repaired;" if attempt==2 else "")+" }\n")
            output={"summary":"implementation","claimed_changed_paths":["claim-impl.cs"],"blockers":(["cannot implement"] if s.scenario=="blocker" else []),"notes":[]}
        else:
            assert self.writable and request.model_capability_class=="low_cost"; assert request.is_path_writable(TEST) and not request.is_path_writable(IMPL); assert "public int Mana" in request.prompt and "Never claim tests passed" in request.prompt
            if attempt==2: assert "fix mana" in request.prompt and ("Repaired" in request.prompt or s.scenario=="no_op_repair")
            if s.scenario=="test_impl": write(self.repo/IMPL,"public class PlayerMana { public int Rewritten; }\n")
            elif not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/TEST,"public class PlayerManaTests { public void ManaTest() {}"+(" public void HumanReviewRegression() {}" if s.feedback else "")+(" public void RepairTest() {}" if attempt==2 else "")+" }\n")
            output={"summary":"tests","claimed_changed_paths":["claim-test.cs"],"test_cases_added_or_updated":["ManaTest"],"blockers":[],"known_limitations":["not run"],"proposed_unity_test_scope":"Play Mode"}
        return ProviderInvocationResponse(output,"fake log\n",("runtime-claim.cs",),Usage(1,1,2),True,())

def factory(state):
    def create(provider,repo,writable,role):
        assert provider in ("fake","claude","codex")
        key=f"{provider}-crew"
        config=RuntimeConfiguration({key:{"provider":"fake","models":{"low_cost":"fake-low","standard":"fake-standard","high_reasoning":"fake-high"}}})
        return key,config,{"fake":FakeProvider(state,repo,writable,role)}
    return create

def execute(source,outputs,scenario,index,*,provider="fake",implementation_paths=(IMPL,),test_paths=(TEST,)):
    run_id=f"smoke-{scenario}-{index}"; state=State(scenario,source)
    result=run_crew(source=source,output_root=outputs,task_id=TASK,provider_name=provider,implementation_paths=implementation_paths,test_paths=test_paths,run_id=run_id,provider_factory=factory(state),_require_physical_read_only_source=False)
    return result,state,outputs/run_id

def retry_execute(source,outputs,scenario,index,prior_run_id,feedback_path,feedback_text):
    run_id=f"retry-{scenario}-{index}"; state=State(scenario,source,feedback_text)
    result=run_crew(source=source,output_root=outputs,run_id=run_id,retry_run_id=prior_run_id,review_feedback_file=feedback_path,provider_factory=factory(state),_require_physical_read_only_source=False)
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
    assert passed["crew_status"]=="review_ready" and (d/"candidate.patch").read_bytes(); assert [x[0] for x in state.calls]==["implementer","test_author","validator"]
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
    assert len({x[1].run_id for x in state.calls})==3; assert not state.clone.exists(); assert passed["implementation_actual_changed_paths"]==[IMPL] and passed["test_actual_changed_paths"]==[TEST]
    assert len(list((d/"task_execution").glob("*/task_request.json")))==3 and len(list((d/"agent_runtime").glob("*/result.json")))==3
    impl_record=json.loads((d/"role_results/implementer_1.json").read_text()); assert impl_record["role_claimed_paths"]==["claim-impl.cs"] and impl_record["agent_runtime_claimed_paths"]==["runtime-claim.cs"] and impl_record["deterministic_incremental_actual_changed_paths"]==[IMPL]
    with patch.dict(os.environ,{"NSC_EXECUTION_HEARTBEAT_SECONDS":"0.01"},clear=False), redirect_stderr(io.StringIO()): slow,state,d=execute(source,outputs,"slow",61)
    slow_events=[json.loads(line) for line in (d/"progress.jsonl").read_text().splitlines()]; heartbeats=[i for i,event in enumerate(slow_events) if event["event"]=="role_heartbeat"]
    assert slow["crew_status"]=="review_ready" and heartbeats
    for index in heartbeats:
        role=slow_events[index]["role"]; attempt=slow_events[index]["attempt"]
        completed=next(i for i,event in enumerate(slow_events) if event["event"]=="role_completed" and event["role"]==role and event["attempt"]==attempt)
        assert index < completed and not any(event["event"]=="role_heartbeat" and event["role"]==role and event["attempt"]==attempt for event in slow_events[completed+1:])
    repaired,state,d=execute(source,outputs,"repair",2); assert repaired["crew_status"]=="review_ready" and repaired["attempts_used"]==2; assert [x[0] for x in state.calls]==["implementer","test_author","validator"]*2
    no_op,state,d=execute(source,outputs,"no_op_repair",6); assert no_op["crew_status"]=="needs_human" and [x[0] for x in state.calls]==["implementer","test_author","validator","implementer","test_author"]
    assert "repair cycle made no deterministic changes" in no_op["rejection_reasons"] and not (d/"candidate.patch").exists()
    twice,state,d=execute(source,outputs,"needs_twice",3); assert twice["crew_status"]=="needs_human" and not (d/"candidate.patch").exists() and (d/"workspace_diagnostic.patch").is_file(); assert len(state.calls)==6
    design,state,d=execute(source,outputs,"design",4); assert design["crew_status"]=="blocked" and len(state.calls)==3 and not (d/"candidate.patch").exists()
    blocked,state,d=execute(source,outputs,"blocker",5); assert blocked["crew_status"]=="blocked" and len(state.calls)==1 and (d/"workspace_diagnostic.patch").is_file() and not state.clone.exists()
    for i,scenario in enumerate(("impl_test","test_impl","untracked","ignored_untracked","deleted","renamed","copied","staged","head"),10):
        rejected,state,d=execute(source,outputs,scenario,i); assert rejected["crew_status"]=="rejected",scenario; assert not (d/"candidate.patch").exists(),scenario
        if scenario=="test_impl": assert any("outside role WriteBoundaries" in x for x in rejected["rejection_reasons"])
        if scenario=="ignored_untracked": assert "untracked file: bad.ignored" in rejected["rejection_reasons"]
    for i,scenario in enumerate(("criteria_missing","criteria_duplicate","criteria_unknown","pass_fail"),50):
        rejected,state,d=execute(source,outputs,scenario,i); assert rejected["crew_status"]=="rejected" and len(state.calls)==3 and not (d/"candidate.patch").exists()
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
    assert [role for role,_,_ in retry_state.calls]==["implementer","test_author","validator"]
    retry_telemetry=(retry_dir/"progress.jsonl").read_text()+retry_stderr.getvalue()
    assert feedback_text.strip() not in retry_telemetry and feedback_sha in retry_telemetry and prior["run_id"] in retry_telemetry
    assert any(json.loads(line)["event"]=="human_review_retry_loaded" for line in (retry_dir/"progress.jsonl").read_text().splitlines())
    assert cmd(source,"rev-parse","HEAD")==current_head and cmd(source,"status","--porcelain=v1","--untracked-files=all")==""

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
    assert legacy_state.calls[0][1].write_boundaries.allowed_paths==(IMPL,OTHER)

    # Retry CLI has no duplicated task/provider/scope arguments.
    retry_cli_stdout=io.StringIO(); retry_cli_stderr=io.StringIO()
    with patch("Pipeline.ExecutionCrew.run_crew.run_crew",return_value=fake_result) as retry_cli_run, patch.object(sys,"argv",["run_crew.py","--retry-run",prior["run_id"],"--review-feedback-file",str(feedback_path),"--output-root",str(outputs)]), redirect_stdout(retry_cli_stdout), redirect_stderr(retry_cli_stderr):
        assert crew_main()==0
    retry_kwargs=retry_cli_run.call_args.kwargs
    assert retry_kwargs["task_id"] is None and retry_kwargs["provider_name"] is None
    assert retry_kwargs["implementation_paths"]==() and retry_kwargs["test_paths"]==()
    assert retry_kwargs["retry_run_id"]==prior["run_id"] and retry_kwargs["review_feedback_file"]==feedback_path

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
    assert cmd(source,"status","--porcelain=v1","--untracked-files=all")==""
  print("execution crew smoke: PASS (fake providers only; Unity not invoked)"); return 0
if __name__=="__main__": raise SystemExit(main())
