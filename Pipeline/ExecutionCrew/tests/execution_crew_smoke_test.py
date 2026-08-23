#!/usr/bin/env python3
"""Deterministic three-role ExecutionCrew smoke; no Unity or live provider calls."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from Pipeline.AgentRuntime.config import RuntimeConfiguration
from Pipeline.AgentRuntime.contracts import Usage
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse
from Pipeline.ExecutionCrew.run_crew import CrewBlocked, Snapshot, changed_paths, clone_exact, construct_real_provider, run_crew, runtime_configuration

TASK="NSC-005"; IMPL="Assets/Scripts/PlayerMana.cs"; TEST="Assets/Tests/PlayerManaTests.cs"; OTHER="Assets/Scripts/Other.cs"
def cmd(root,*args): return subprocess.run(("git","-C",str(root),*args),check=True,stdout=subprocess.PIPE,text=True).stdout.strip()
def write(path,text): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8")
def fixture(parent):
    root=parent/"source"; root.mkdir(); subprocess.run(("git","init","-q",str(root)),check=True); cmd(root,"config","user.name","Crew Smoke"); cmd(root,"config","user.email","crew@example.invalid")
    write(root/IMPL,"public class PlayerMana { }\n"); write(root/TEST,"public class PlayerManaTests { }\n"); write(root/OTHER,"public class Other { }\n"); write(root/".gitignore","*.ignored\n")
    task={"schema_version":"2.0","id":TASK,"contract_revision":3,"contract_disposition":"active","title":"Mana","kind":"implementation","execution_scope":"single_agent","decomposition_state":"concrete","acceptance_criteria":[{"criterion_id":"AC-001","reference":"fixture","requirement":"Mana behavior is implemented."}],"completion_gates":[{"gate_id":"VAL-001","reference":"fixture","requirement":"Unity behavior is verified."}],"downstream_integration_obligations":[],"provenance":{"origin":"fixture"}}
    write(root/f"Tasks/{TASK}.yaml",json.dumps(task)+"\n"); write(root/"Docs/GDD/No_Safe_Circle_GDD.md","# GDD\n"); write(root/"Docs/Engineering/UNITY_TESTING_POLICY.md","# Policy\nNever claim tests passed.\n")
    cmd(root,"add","."); cmd(root,"commit","-qm","baseline"); return root

class State:
    def __init__(self,scenario,source): self.scenario=scenario; self.source=source; self.calls=[]; self.clone=None

class FakeProvider:
    provider_identifier="fake"
    def __init__(self,state,repo,writable,role): self.state=state; self.repo=repo; self.writable=writable; self.role=role
    def invoke(self,request,model):
        s=self.state; attempt=sum(1 for r,_,_ in s.calls if r==self.role)+1; s.calls.append((self.role,request,model))
        assert request.role==self.role
        if self.role=="validator":
            assert not self.writable and self.repo.resolve()==s.source.resolve(); assert "repository_write" not in request.allowed_capabilities; assert not request.write_boundaries.allowed_paths
            exact=subprocess.run(("git","-C",str(s.clone),"diff","--binary","--full-index","--no-ext-diff","--no-renames",cmd(s.source,"rev-parse","HEAD")),check=True,stdout=subprocess.PIPE,text=True).stdout
            assert f"EXACT FULL CANDIDATE GIT PATCH\n---\n{exact}\n---" in request.prompt and "public int Mana" in request.prompt
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
                if not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/IMPL,"public class PlayerMana { public int Mana;"+(" public int Repaired;" if attempt==2 else "")+" }\n")
            output={"summary":"implementation","claimed_changed_paths":["claim-impl.cs"],"blockers":(["cannot implement"] if s.scenario=="blocker" else []),"notes":[]}
        else:
            assert self.writable and request.model_capability_class=="low_cost"; assert request.is_path_writable(TEST) and not request.is_path_writable(IMPL); assert "public int Mana" in request.prompt and "Never claim tests passed" in request.prompt
            if attempt==2: assert "fix mana" in request.prompt and ("Repaired" in request.prompt or s.scenario=="no_op_repair")
            if s.scenario=="test_impl": write(self.repo/IMPL,"public class PlayerMana { public int Rewritten; }\n")
            elif not (s.scenario=="no_op_repair" and attempt==2): write(self.repo/TEST,"public class PlayerManaTests { public void ManaTest() {}"+(" public void RepairTest() {}" if attempt==2 else "")+" }\n")
            output={"summary":"tests","claimed_changed_paths":["claim-test.cs"],"test_cases_added_or_updated":["ManaTest"],"blockers":[],"known_limitations":["not run"],"proposed_unity_test_scope":"Play Mode"}
        return ProviderInvocationResponse(output,"fake log\n",("runtime-claim.cs",),Usage(1,1,2),True,())

def factory(state):
    def create(provider,repo,writable,role):
        assert provider=="fake"
        config=RuntimeConfiguration({"fake-crew":{"provider":"fake","models":{"low_cost":"fake-low","standard":"fake-standard","high_reasoning":"fake-high"}}})
        return "fake-crew",config,{"fake":FakeProvider(state,repo,writable,role)}
    return create

def execute(source,outputs,scenario,index):
    state=State(scenario,source); result=run_crew(source=source,output_root=outputs,task_id=TASK,provider_name="fake",implementation_paths=(IMPL,),test_paths=(TEST,),run_id=f"smoke-{scenario}-{index}",provider_factory=factory(state),_require_physical_read_only_source=False); return result,state,outputs/f"smoke-{scenario}-{index}"

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
    passed,state,d=execute(source,outputs,"pass",1); assert passed["crew_status"]=="review_ready" and (d/"candidate.patch").read_bytes(); assert [x[0] for x in state.calls]==["implementer","test_author","validator"]
    assert json.loads((d/"role_results/validator_1.json").read_text())["structured_output"]["criteria_results"][1]["status"]=="not_proven"
    assert len({x[1].run_id for x in state.calls})==3; assert not state.clone.exists(); assert passed["implementation_actual_changed_paths"]==[IMPL] and passed["test_actual_changed_paths"]==[TEST]
    assert len(list((d/"task_execution").glob("*/task_request.json")))==3 and len(list((d/"agent_runtime").glob("*/result.json")))==3
    impl_record=json.loads((d/"role_results/implementer_1.json").read_text()); assert impl_record["role_claimed_paths"]==["claim-impl.cs"] and impl_record["agent_runtime_claimed_paths"]==["runtime-claim.cs"] and impl_record["deterministic_incremental_actual_changed_paths"]==[IMPL]
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
  print("execution crew smoke: PASS (fake providers only; Unity not invoked)"); return 0
if __name__=="__main__": raise SystemExit(main())
