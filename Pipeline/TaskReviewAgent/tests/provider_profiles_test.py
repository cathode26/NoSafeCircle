"""Pure/component profile regressions; disposable Git and fake provider/process boundaries.

These are orchestration regressions, not Unity acceptance evidence. Run with
python -m unittest Pipeline.TaskReviewAgent.tests.provider_profiles_test -v.
"""
from dataclasses import replace, FrozenInstanceError
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import hashlib
import io
import json
import os
import subprocess
import tempfile
import sys
import unittest
from unittest.mock import patch

from Pipeline.TaskReviewAgent.execution_routing import ExecutionRecommendation, load_execution_routing_policy

PROFILES = ("all-claude", "all-codex", "claude-architect-balanced", "codex-architect-balanced")
CONTROL = '["-c","sandbox_mode=\\"danger-full-access\\""]'


class ProfileTests(unittest.TestCase):
    def topology(self, profile="claude-architect-balanced", budgets=None):
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
        return expand_profile(profile, token_budgets=budgets)

    def ledger(self, directory, **kwargs):
        from Pipeline.TaskReviewAgent.provider_budget import ProviderBudgetLedger
        return ProviderBudgetLedger(Path(directory)/"budget.json", topology=self.topology(**kwargs), repository="fixture/repo", run_id="fixture")

    def recommendation(self, preference="no_preference", basis="no_preference"):
        return ExecutionRecommendation("standard", preference, "Task requires the established provider-specific compiler diagnostic capability.", basis)

    def assign(self, ledger, number=100, recommendation=None, **snapshot):
        return ledger.assign(task_id=f"NSC-{number}", contract_sha256="a"*64,
            recommendation=recommendation or self.recommendation(), snapshot=ledger.snapshot(**snapshot))

    def test_frozen_topology_roundtrip_and_tamper(self):
        from Pipeline.TaskReviewAgent.provider_profiles import ProviderTopology
        for name in PROFILES:
            topology = self.topology(name)
            self.assertEqual(topology, ProviderTopology.from_json(topology.to_json()))
            with self.assertRaises(FrozenInstanceError): topology.architect="codex"
            bad=topology.to_dict(); bad["validator_relationship"]="self_review"
            with self.assertRaises(ValueError): ProviderTopology.from_dict(bad)

    def test_composition_expands_once_and_resume_is_exact(self):
        from Pipeline.TaskReviewAgent.run_autonomous_graph import build_parser, _runtime_configuration
        from Pipeline.TaskReviewAgent.autonomous_graph_run import AutonomousRuntimeConfiguration
        args=build_parser().parse_args(["--run-id","fixture","--confirm-repository","fixture/repo","--provider-profile","all-claude"])
        runtime=_runtime_configuration(args,None)
        self.assertEqual(runtime, AutonomousRuntimeConfiguration.from_dict(runtime.to_dict()))
        with patch("Pipeline.TaskReviewAgent.run_autonomous_graph.expand_profile", side_effect=AssertionError("expanded twice")):
            self.assertEqual(runtime,_runtime_configuration(args,runtime))
        args.provider_profile="all-codex"
        with self.assertRaises(ValueError): _runtime_configuration(args,runtime)

    def test_contradictory_flags_rejected_by_composition(self):
        from Pipeline.TaskReviewAgent.run_autonomous_graph import build_parser, _runtime_configuration
        for name in PROFILES:
            args=build_parser().parse_args(["--run-id","fixture","--confirm-repository","fixture/repo","--provider-profile",name,
                "--provider-allowlist","codex" if name=="all-claude" else "claude"])
            with self.assertRaises(ValueError): _runtime_configuration(args,None)

    def test_single_provider_policy_does_not_read_other_configuration(self):
        class GuardedEnvironment(dict):
            def get(self,key,default=None):
                if self.forbidden in key: raise AssertionError("resolved forbidden provider: "+key)
                return super().get(key,default)
        for name,allowed,forbidden in (("all-claude","claude","OPENAI"),("all-codex","codex","CLAUDE")):
            env=GuardedEnvironment(); env.forbidden=forbidden
            policy=load_execution_routing_policy(env, provider_allowlist=(allowed,),supervisor_provider=allowed,
                default_provider_override=allowed,resolve_only_permitted=True)
            self.assertIsNone(getattr(policy.standard,"openai_model" if allowed=="claude" else "claude_model"))
            self.assertEqual(policy.standard.allowed_execution_providers,{allowed})

    def test_codex_preflight_is_required_and_claude_never_reads_control(self):
        from Pipeline.TaskReviewAgent.provider_profiles import preflight_topology
        with patch("Pipeline.TaskReviewAgent.supervisor_session_pool.codex_resume_activation_from_environment",side_effect=AssertionError("Codex resolved")):
            preflight_topology(self.topology("all-claude"))
        with patch.dict("os.environ",{},clear=True):
            for name in PROFILES[1:]:
                with self.assertRaises(ValueError): preflight_topology(self.topology(name))

    def test_unknown_is_null_and_round_robin_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory)
            snapshot=ledger.snapshot()
            for row in snapshot["providers"].values():
                for field in ("input_tokens","cached_input_tokens","total_tokens","normalized_utilization","warm_compatible_sessions","available"):
                    self.assertIsNone(row[field])
            self.assertEqual(self.assign(ledger)["provider"],"claude")
            restarted=self.ledger(directory)
            self.assertEqual(self.assign(restarted)["provider"],"claude")
            self.assertEqual(self.assign(restarted,101)["provider"],"codex")

    def test_pressure_uses_normalized_budgets_and_fixed_architect(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory,profile="codex-architect-balanced",budgets={"claude":100,"codex":1000})
            ledger.observe(invocation_id="architect",provider="codex",role="polling_architect",usage=dict(input_tokens=800,cached_input_tokens=700,output_tokens=100,total_tokens=900))
            ledger.observe(invocation_id="crew",provider="claude",role="implementer",usage=dict(input_tokens=10,cached_input_tokens=0,output_tokens=10,total_tokens=20))
            row=ledger.snapshot()["providers"]["codex"]
            self.assertEqual(row["normalized_utilization"],.9)
            self.assertEqual(row["cached_input_tokens"],700)
            self.assertEqual(self.assign(ledger)["provider"],"claude")
            ledger.observe(invocation_id="more",provider="claude",role="validator",usage=dict(total_tokens=100))
            self.assertEqual(self.assign(ledger,101)["provider"],"codex")

    def test_capability_override_records_basis_and_rationale(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory,budgets={"claude":100,"codex":100})
            for p,total in (("claude",1),("codex",90)):
                ledger.observe(invocation_id=p,provider=p,role="implementer",usage=dict(total_tokens=total))
            result=self.assign(ledger,recommendation=self.recommendation("openai","capability"))
            self.assertEqual((result["provider"],result["reason"]),("codex","architect_capability_advantage"))
            self.assertEqual(result["rationale"],self.recommendation().rationale)

    def test_advisory_balance_preference_cannot_override_pressure(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory,budgets={"claude":100,"codex":100})
            for p,total in (("claude",1),("codex",90)):
                ledger.observe(invocation_id=p,provider=p,role="implementer",usage=dict(total_tokens=total))
            self.assertEqual(self.assign(ledger,recommendation=self.recommendation("openai","balance"))["provider"],"claude")

    def test_availability_precedes_capability_and_does_not_reassign_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory)
            self.assertEqual(self.assign(ledger,recommendation=self.recommendation("openai","capability"),availability={"codex":False})["provider"],"claude")
            with self.assertRaises(ValueError): self.assign(ledger,availability={"claude":False})

    def test_equal_pressure_warm_sessions_then_persisted_tie(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory,budgets={"claude":100,"codex":1000})
            for p,total in (("claude",10),("codex",100)):
                ledger.observe(invocation_id=p,provider=p,role="implementer",usage=dict(total_tokens=total))
            self.assertEqual(self.assign(ledger,warm={"claude":1,"codex":2})["provider"],"codex")
            self.assertEqual(self.assign(ledger,101,warm={"claude":2,"codex":2})["provider"],"claude")
            self.assertEqual(self.assign(self.ledger(directory,budgets={"claude":100,"codex":1000}),102)["provider"],"codex")

    def test_replay_deduplicates_and_conflicting_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger=self.ledger(directory)
            call=dict(invocation_id="exact",provider="claude",role="polling_architect",usage=dict(total_tokens=30))
            ledger.observe(**call); ledger.observe(**call)
            self.assertEqual(ledger.snapshot()["providers"]["claude"]["total_tokens"],30)
            with self.assertRaises(ValueError): ledger.observe(**{**call,"usage":dict(total_tokens=31)})

    def test_role_map_keeps_repairs_and_reviews_on_assigned_providers(self):
        from Pipeline.TaskReviewAgent.provider_profiles import crew_role_routes,validate_crew_routes
        for name in PROFILES:
            topology=self.topology(name)
            for primary in topology.provider_allowlist:
                tier=load_execution_routing_policy({},provider_allowlist=topology.provider_allowlist,
                    supervisor_provider=topology.architect,resolve_only_permitted=True).standard
                routes=crew_role_routes(topology,primary,tier)
                self.assertEqual(routes["implementer"]["provider"],primary)
                self.assertEqual(routes["validator"]["provider"],topology.reviewer_for(primary))
                self.assertEqual(routes["lead_developer"]["provider"],topology.reviewer_for(primary))
                bad={**routes,"validator":routes["implementer"]}
                if topology.mixed:
                    with self.assertRaises(ValueError): validate_crew_routes(topology,primary,bad)

    def test_codex_test_author_uses_bounded_low_cost_reasoning(self):
        from Pipeline.TaskReviewAgent.provider_profiles import crew_role_routes
        topology = self.topology("all-codex")
        expected = {"fast": "low", "standard": "low", "deep": "medium"}
        policy = load_execution_routing_policy({}, provider_allowlist=topology.provider_allowlist,
            supervisor_provider=topology.architect, resolve_only_permitted=True)
        for tier_name, test_author_effort in expected.items():
            tier = getattr(policy, tier_name)
            routes = crew_role_routes(topology, "codex", tier)
            self.assertEqual(routes["test_author"]["reasoning_effort"], test_author_effort)
            for role in ("implementer", "validator", "contract_locality_auditor", "lead_developer"):
                self.assertEqual(routes[role]["reasoning_effort"], tier.openai_reasoning_effort)

    def test_decomposition_strategy_is_independent_of_implementer(self):
        from Pipeline.TaskReviewAgent.polling_orchestrator import build_decomposition_worker_command
        for name in PROFILES:
            topology=self.topology(name)
            for primary in topology.provider_allowlist:
                argv=build_decomposition_worker_command(task_id="NSC-100",worker_id="fixture",source=Path.cwd(),
                    checkout_root=Path.cwd(),output_root=Path.cwd(),run_id="fixture",enable_session_pool=True,
                    scheduler_output_root=Path.cwd(),admission_source_head="a"*40,task_contract_sha256="b"*64,
                    provider_allowlist=topology.provider_allowlist,decomposition_strategy=topology.decomposition_strategy)
                order=argv[argv.index("--providers")+1].split(",")
                self.assertEqual(set(order),set(topology.provider_allowlist))
                self.assertEqual(len(order),2)
                if not topology.mixed: self.assertEqual(argv[argv.index("--max-calls")+1],"2")


class DecompositionProfileTests(unittest.TestCase):
    def exercise(self,provider):
        root=Path(__file__).resolve().parents[3]
        with patch.object(sys, "path", [str(root/"Pipeline"),str(root/"Pipeline"/"TaskGraph"),*sys.path]):
            from Pipeline.TaskDecomposition.tests import pooled_decomposition_smoke_test as f
        from Pipeline.TaskReviewAgent.decomposition_authorization import _validated_provider_order
        from copy import deepcopy
        with f.fixture() as text:
            fx=f.Fixture(Path(text))
            raw,digest=fx.candidate(); fx.outputs[provider]=[raw,f.pass_review(digest)]
            assignment,result,settled=fx.run("profile-pair",order=(provider,provider))
            self.assertEqual(result["run_status"],"review_ready",result["rejection_reasons"])
            self.assertEqual(result["review_independence"],"same_provider_separate_sessions")
            self.assertEqual(len({v["confirmed_session_id"] for v in fx.log}),2)
            self.assertIsNotNone(settled)
            self.assertEqual(_validated_provider_order(result),(provider,provider))
            from Pipeline.TaskReviewAgent import provider_budget as budget
            from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
            topology=expand_profile("all-"+provider)
            ledger=budget.ProviderBudgetLedger(Path(text)/"budget.json",topology=topology,repository=f.REPOSITORY,run_id="fixture")
            ledger.register_decomposition_worker(worker_run_id="profile-pair",task_id=f.TASK,contract_sha256="a"*64)
            old=budget._WORKER_BUDGET.get()
            try:
                with patch.dict(os.environ,{"NSC_CODEX_RESUME_SANDBOX_ARGUMENT":CONTROL}):
                    budget.bind_decomposition_budget(ledger.path,task_id=f.TASK,run_id="profile-pair",contract_sha256="a"*64,
                        provider_order=(provider,provider),permitted=topology.provider_allowlist)
                budget.observe_decomposition_result(fx.output_root/"profile-pair")
                budget.observe_decomposition_result(fx.output_root/"profile-pair")
                self.assertEqual(ledger.snapshot()["providers"][provider]["invocation_count"],2)
            finally:
                budget._WORKER_BUDGET.set(old)
            forged=deepcopy(result); forged["pooled_sessions"]=None
            self.assertIsNone(_validated_provider_order(forged))
            forged=deepcopy(result)
            forged["pooled_sessions"][provider+":decomposition_reviewer"]["confirmed_session"]["session_id"]=fx.log[0]["confirmed_session_id"]
            self.assertIsNone(_validated_provider_order(forged))

    def test_all_claude_pooled_author_reviewer(self): self.exercise("claude")
    def test_all_codex_pooled_author_reviewer_label(self): self.exercise("codex")


class SchedulerProfileTests(unittest.TestCase):
    def exercise(self,profile,failed=False):
        from Pipeline.TaskReviewAgent.tests import polling_orchestrator_smoke_test as f
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
        from Pipeline.TaskReviewAgent.provider_budget import ProviderBudgetLedger, load_worker_profile
        topology=expand_profile(profile,token_budgets={p:1000 for p in ("claude","codex") if p in profile or "balanced" in profile})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{"NSC_CODEX_RESUME_SANDBOX_ARGUMENT":CONTROL}):
            source,head=f.create_source(Path(directory))
            ids=(f.TASK_A,f.TASK_B)
            tasks={task_id:f.task(task_id) for task_id in ids}
            contexts=[]
            class Architect(f.FakeArchitect):
                def __call__(self,**values):
                    contexts.append(values["candidates"][0]["capacity_context"])
                    if failed:
                        raise f.ArchitectPreflightError("fixture transport failed without a usage receipt")
                    result=super().__call__(**values)
                    return replace(result,invocation_metadata=dict(agent_runtime_run_id="architect-fixture-1",
                        provider=topology.architect,model="fixture",usage=dict(input_tokens=9,output_tokens=1,total_tokens=10)))
            architect=Architect({task_id:f.advisory(task_id,head,exact_paths=(f"Assets/{task_id}.cs",)) for task_id in ids})
            processes=f.ProcessFactory()
            # Existing fixture provides exact immutable source and reservation observations.
            scheduler,stream=f.make_orchestrator(source=source,planner=f.SequencePlanner([f.candidate_plan(head,*ids)]),
                architect=architect,processes=processes,tasks=tasks,max_workers=2)
            scheduler.provider_topology=topology
            scheduler.provider_allowlist=topology.provider_allowlist
            scheduler.supervisor_provider=topology.architect
            scheduler.execution_provider=None if topology.mixed else topology.architect
            scheduler.provider_budget=ProviderBudgetLedger(Path(directory)/"budget.json",topology=topology,repository="fixture/repo",run_id="fixture")
            result=scheduler.poll_capacity_batch()
            self.assertFalse(result.fatal)
            if failed:
                self.assertEqual(processes.calls,[])
                row=scheduler.provider_budget.snapshot()["providers"][topology.architect]
                self.assertIsNone(row["total_tokens"])
                self.assertFalse(row["available"])
                self.assertEqual(len(row["recent_failures"]),1)
                return
            self.assertEqual(len(processes.calls),2,stream.getvalue())
            self.assertEqual(len(contexts),1)
            self.assertIn("provider_budget_snapshot",contexts[0])
            rows=scheduler.provider_budget.snapshot()["providers"]
            self.assertEqual(rows[topology.architect]["total_tokens"],10)
            self.assertEqual(rows[topology.architect]["invocation_count"],1)
            providers=[]
            for call in processes.calls:
                argv=call[0] if isinstance(call,tuple) else call
                if isinstance(argv,dict): argv=argv["argv"]
                def option(name): return argv[argv.index(name)+1]
                primary=option("--execution-provider"); providers.append(primary)
                value=load_worker_profile(Path(option("--provider-assignment-path")),task_id=option("--task-id"),
                    worker_run_id=option("--run-id"),contract_sha256=option("--task-contract-sha256"),
                    provider=primary,model=option("--execution-model"),supervisor=option("--supervisor-provider"))
                self.assertEqual(value["role_routes"]["validator"]["provider"],topology.reviewer_for(primary))
            self.assertEqual(set(providers),set(topology.provider_allowlist))

    def test_all_claude_real_poll(self): self.exercise("all-claude")
    def test_all_codex_real_poll(self): self.exercise("all-codex")
    def test_claude_architect_real_poll(self): self.exercise("claude-architect-balanced")
    def test_codex_architect_real_poll(self): self.exercise("codex-architect-balanced")
    def test_failed_architect_real_poll_preserves_unknown_cost(self): self.exercise("all-codex",True)


class CrewProfileTests(unittest.TestCase):
    def test_execution_crew_profile_preflight_uses_committed_blob_under_autocrlf(self):
        """A real CRLF checkout must retain the LF Git-blob task identity."""
        from Pipeline.ExecutionCrew import run_crew as crew_cli
        from Pipeline.TaskReviewAgent.provider_profiles import (
            crew_role_routes,
            expand_profile,
            profile_runtime_binding,
        )

        def git(root, *args):
            completed = subprocess.run(
                ("git", "-C", str(root), *args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", "replace"),
            )
            return completed.stdout

        with tempfile.TemporaryDirectory(prefix="nsc-profile-autocrlf-") as directory:
            root = Path(directory)
            origin = root / "origin"
            checkout = root / "checkout"
            origin.mkdir()
            git(origin, "init", "--quiet")
            git(origin, "config", "user.name", "Provider Profile Regression")
            git(origin, "config", "user.email", "provider-profile@example.invalid")
            git(origin, "config", "core.autocrlf", "false")
            (origin / "Tasks").mkdir()
            task_id = "NSC-100"
            contract = {
                "schema_version": "2.0",
                "id": task_id,
                "title": "Profile CRLF regression",
                "exclusive_resources": [],
            }
            lf_bytes = (json.dumps(contract, indent=2) + "\n").encode("utf-8")
            (origin / "Tasks" / f"{task_id}.yaml").write_bytes(lf_bytes)
            git(origin, "add", "Tasks")
            git(origin, "commit", "--quiet", "-m", "Add LF task contract")
            subprocess.run(
                (
                    "git", "-c", "core.autocrlf=true", "clone", "--quiet",
                    str(origin), str(checkout),
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            worktree_bytes = (checkout / "Tasks" / f"{task_id}.yaml").read_bytes()
            self.assertIn(b"\r\n", worktree_bytes)
            self.assertNotEqual(worktree_bytes, lf_bytes)
            committed_bytes = git(checkout, "show", f"HEAD:Tasks/{task_id}.yaml")
            self.assertEqual(committed_bytes, lf_bytes)
            committed_hash = hashlib.sha256(committed_bytes).hexdigest()
            self.assertNotEqual(committed_hash, hashlib.sha256(worktree_bytes).hexdigest())

            topology = expand_profile("all-claude")
            tier = load_execution_routing_policy(
                {},
                provider_allowlist=topology.provider_allowlist,
                supervisor_provider=topology.architect,
                resolve_only_permitted=True,
            ).standard
            routes = crew_role_routes(topology, "claude", tier)
            profile_path = root / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "topology": topology.to_dict(),
                        "role_routes": routes,
                        "runtime_binding": profile_runtime_binding(topology, "fixture"),
                        "run_id": "profile-autocrlf",
                        "task_id": task_id,
                        "task_contract_sha256": committed_hash,
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                "run_crew.py", "--source", str(checkout), "--task-id", task_id,
                "--provider", "claude", "--implementation-path", "Fixture.cs",
                "--test-path", "FixtureTests.cs", "--run-id", "profile-autocrlf",
                "--role-session-leases", str(root / "leases.json"),
                "--scheduler-repository-identity", "fixture/repo",
                "--checkout-identity-manifest", str(root / "manifest.json"),
                "--provider-role-profile", str(profile_path),
            ]
            fake_result = {"crew_status": "review_ready"}
            with patch.object(sys, "argv", argv), \
                    patch.object(crew_cli, "load_role_session_lease_bundle", return_value={}), \
                    patch.object(crew_cli, "run_crew", return_value=fake_result) as invoked, \
                    patch.object(crew_cli, "print_human_summary"), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(crew_cli.main(), 0)
            invoked.assert_called_once()

            changed = {**contract, "title": "Changed committed contract"}
            (checkout / "Tasks" / f"{task_id}.yaml").write_text(
                json.dumps(changed, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            git(checkout, "config", "user.name", "Provider Profile Regression")
            git(checkout, "config", "user.email", "provider-profile@example.invalid")
            git(checkout, "add", "Tasks")
            git(checkout, "commit", "--quiet", "-m", "Alter committed task contract")
            with patch.object(sys, "argv", argv), \
                    patch.object(crew_cli, "load_role_session_lease_bundle", return_value={}), \
                    patch.object(crew_cli, "run_crew", side_effect=AssertionError("stale profile reached crew")), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as rejected:
                    crew_cli.main()
            self.assertEqual(rejected.exception.code, 2)
            self.assertIn("different committed contract", stderr.getvalue())

    def exercise(self,profile,primary,scenario="repair"):
        from Pipeline.ExecutionCrew.tests import pooled_run_crew_smoke_test as f
        from Pipeline.ExecutionCrew.session_pool import SessionCompatibility,DurableAssignmentResult
        from Pipeline.ExecutionCrew.run_crew import run_crew,PROFILE_ROLE_CAPABILITY_CLASSES
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile,crew_role_routes
        topology=expand_profile(profile)
        tier=load_execution_routing_policy({},provider_allowlist=topology.provider_allowlist,
            supervisor_provider=topology.architect,resolve_only_permitted=True).standard
        routes=crew_role_routes(topology,primary,tier)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{"NSC_CODEX_RESUME_SANDBOX_ARGUMENT":CONTROL}):
            root=Path(directory); source=f.fixture(root); head,checkout=f.source_identity(source)
            pool=f.new_pool(); run_id="profile-crew"; state=f.State(scenario); calls=[]
            leases={role:pool.checkout(compatibility=SessionCompatibility(
                "claude-code" if route["provider"]=="claude" else "openai-codex",route["model"],route["reasoning_effort"],
                role,PROFILE_ROLE_CAPABILITY_CLASSES[role],f.REPOSITORY),
                worker_slot_id="fixture",task_id=f.TASK,worker_run_id=run_id,source_commit=head,checkout_identity=checkout,now=f.BASE)
                for role,route in routes.items()}
            def factory(provider,repo,writable,role,session,ledger):
                calls.append((role,provider,session.mode,session.session_id))
                identifier="claude-code" if provider=="claude" else "openai-codex"
                key,config,registry=f.factory(state,provider_identity=identifier,model=routes[role]["model"])(provider,repo,writable,role,session,ledger)
                if scenario == "failed_repair" and role == "validator":
                    fake=registry[identifier]
                    fake.role_output=lambda attempt: f.PooledFakeProvider.role_output(fake,1)
                    state.scenario="repair"
                return key,config,registry
            result=run_crew(source=source,output_root=root/"outputs",task_id=f.TASK,provider_name=primary,
                implementation_paths=(f.IMPL,),test_paths=(f.TEST,),run_id=run_id,
                execution_model=routes["implementer"]["model"],openai_reasoning_effort=routes["implementer"]["reasoning_effort"],
                provider_factory=factory,_require_physical_read_only_source=False,role_session_leases=leases,
                scheduler_repository_identity=f.REPOSITORY,provider_allowlist=topology.provider_allowlist,
                provider_topology=topology.to_dict(),role_routes=routes)
            self.assertEqual(result["crew_status"],"needs_human" if scenario=="failed_repair" else "review_ready",result["rejection_reasons"])
            impl=[x for x in calls if x[0]=="implementer"]; val=[x for x in calls if x[0]=="validator"]
            self.assertEqual([x[1] for x in impl],[primary,primary])
            self.assertEqual([x[1] for x in val],[topology.reviewer_for(primary)]*2)
            self.assertEqual([x[2] for x in impl],["start","resume"])
            self.assertEqual([x[2] for x in val],["start","resume"])
            self.assertNotEqual(impl[1][3],val[1][3])
            self.assertEqual(result["role_routes"],routes)
            from Pipeline.TaskReviewAgent import provider_budget as budget
            ledger=budget.ProviderBudgetLedger(root/"budget.json",topology=topology,repository=f.REPOSITORY,run_id="fixture")
            ledger.assign(task_id=f.TASK,contract_sha256="a"*64,
                recommendation=ExecutionRecommendation("standard","openai" if primary=="codex" else "claude",
                    "Fixture requires this concrete provider capability.","capability"),snapshot=ledger.snapshot())
            ledger.register_worker(worker_run_id=run_id,task_id=f.TASK,contract_sha256="a"*64,provider=primary)
            old_binding=budget._WORKER_BUDGET.get()
            try:
                budget.bind_worker_budget(ledger.path,topology=topology,worker_run_id=run_id,
                    task_id=f.TASK,contract_sha256="a"*64,provider=primary)
                receipt=root/"outputs"/run_id/"crew_result.json"
                budget.observe_crew_result(receipt)
                budget.observe_crew_result(receipt)
                rows=ledger.snapshot()["providers"]
                self.assertEqual(sum(row["invocation_count"] for row in rows.values()),len(calls))
                artifact=receipt.parent/result["provider_invocation_artifacts"][0]["path"]
                original=artifact.read_bytes()
                try:
                    artifact.write_bytes(original+b" ")
                    with self.assertRaisesRegex(ValueError,"bytes differ"):
                        budget.observe_crew_result(receipt)
                finally:
                    artifact.write_bytes(original)
            finally:
                budget._WORKER_BUDGET.set(old_binding)
            if scenario=="failed_repair":
                lead=[x for x in calls if x[0]=="lead_developer"]
                self.assertEqual(len(lead),1)
                self.assertEqual(lead[0][1],topology.reviewer_for(primary))
                self.assertIsNone(result["candidate_patch_sha256"])
            for role,value in result["durable_assignment_results"].items():
                pool.check_in(lease=leases[role],result=DurableAssignmentResult.from_dict(value),evidence_root=root/"outputs"/run_id)
            self.assertEqual(f.cmd(source,"status","--porcelain"),"")

    def test_claude_repairs_codex_revalidates(self): self.exercise("claude-architect-balanced","claude")
    def test_codex_repairs_claude_revalidates(self): self.exercise("codex-architect-balanced","codex")
    def test_all_claude_never_invokes_codex(self): self.exercise("all-claude","claude")
    def test_all_codex_never_invokes_claude(self): self.exercise("all-codex","codex")
    def test_failed_repair_gets_one_opposite_pooled_lead_diagnosis(self): self.exercise("claude-architect-balanced","claude","failed_repair")

    def test_host_pool_persists_role_routes_and_isolates_runtime_controls(self):
        from Pipeline.TaskReviewAgent.tests import execution_session_pool_smoke_test as f
        from Pipeline.TaskReviewAgent.execution_session_pool import ExecutionCrewSessionPoolOwner
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile,crew_role_routes,profile_runtime_binding
        with f.scratch("profile-owner-") as directory, patch.dict(os.environ,{"NSC_CODEX_RESUME_SANDBOX_ARGUMENT":CONTROL}):
            checkout,manifest,head,_=f.fixture(Path(directory))
            topology=expand_profile("codex-architect-balanced")
            tier=load_execution_routing_policy({},supervisor_provider="codex").standard
            routes=crew_role_routes(topology,"codex",tier)
            binding=profile_runtime_binding(topology,"fixture")
            owner=ExecutionCrewSessionPoolOwner(checkout=checkout,runtime_binding=binding)
            f._OWNERS.append(owner)
            assignment=owner.prepare(run_id="profile-owner",task_id=f.TASK_ID,worker_slot_id=f.WORKER_SLOT_ID,
                source_commit=head,task_contract_sha256="a"*64,model=routes["implementer"]["model"],
                reasoning_effort=routes["implementer"]["reasoning_effort"],role_routes=routes)
            self.assertEqual(len(assignment["leases"]),5)
            self.assertEqual(len({v["record_id"] for v in assignment["leases"].values()}),5)
            for role,lease in assignment["leases"].items():
                self.assertEqual(lease["provider_identifier"],"claude-code" if routes[role]["provider"]=="claude" else "openai-codex")
            restarted=ExecutionCrewSessionPoolOwner(checkout=checkout,runtime_binding=binding)
            state,_,_=restarted._load()
            self.assertEqual(state["assignments"]["profile-owner"]["role_routes"],routes)
            from Pipeline.TaskReviewAgent.provider_budget import compatible_crew_sessions
            self.assertEqual(compatible_crew_sessions(checkout_root=checkout.parent,repository=owner.repository_identity,
                topology=topology,policy=load_execution_routing_policy({},supervisor_provider="codex"),
                compose_project="fixture"),{"claude":0,"codex":0})
            changed=ExecutionCrewSessionPoolOwner(checkout=checkout,runtime_binding={**binding,"codex_resume_control":["--config",'sandbox_mode="danger-full-access"']})
            self.assertNotEqual(owner.root,changed.root)
            owner.cancel_unstarted(run_id="profile-owner")


class LauncherProfileTests(unittest.TestCase):
    def exercise(self,name):
        from Pipeline.TaskReviewAgent.tests import architect_managed_launcher_smoke_test as f
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile,routing_table
        topology=expand_profile(name)
        payload=dict(status="work_remains",run_id="profile-launcher",provider_topology=topology.to_dict(),routing_table=routing_table(topology))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); capture=root/"capture.json"; log=root/"calls.jsonl"
            stub=f.STUB_SOURCE.replace("if ($Arguments -contains '--completion-probe') {", """
if ($Arguments -contains '--resolved-provider-topology-file') {
    $Index = [Array]::IndexOf([string[]]$Arguments, '--resolved-provider-topology-file')
    Write-ExactUtf8 -Path $env:NSC_PROFILE_CAPTURE -Text ([System.IO.File]::ReadAllText([string]$Arguments[$Index + 1]))
}
if ($Arguments -contains '--completion-probe') {
    $Index = [Array]::IndexOf([string[]]$Arguments, '--completion-probe-output')
    if ($Index -lt 0) { throw 'profile probe output path is missing' }
    Write-ExactUtf8 -Path ([string]$Arguments[$Index + 1]) -Text $env:NSC_PROFILE_PAYLOAD
    [Console]::Error.WriteLine('diagnostic text must never be parsed as JSON')
""")
            for tool in ("git","gh","docker","python"):
                (root/(tool+".ps1")).write_text(stub.replace("@TOOL@",repr(tool)),encoding="utf-8",newline="\r\n")
            completed,records=f._run(root,log,["-TaskId",f.TASK,"-ProviderProfile",name,
                "-AutonomousRunId","profile-launcher","-ConfirmRepository",f.REPOSITORY],
                NSC_PROFILE_PAYLOAD=json.dumps(payload),NSC_PROFILE_CAPTURE=str(capture),
                NSC_CODEX_RESUME_SANDBOX_ARGUMENT="malformed-unused-control" if name=="all-claude" else CONTROL)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
            calls=f._calls(records,f.AUTONOMOUS_SCRIPT)
            self.assertEqual(len(calls),2,records)
            for argv in calls:
                self.assertEqual(argv[argv.index("--provider-profile")+1],name)
            self.assertEqual(json.loads(capture.read_text()),payload)
            self.assertFalse(f._calls(records,f.DIRECT_SCRIPT))
            volumes=[record["argv"][2] for record in records if record["tool"]=="docker" and record["argv"][:2]==["volume","inspect"]]
            self.assertEqual(set(volumes),{f"nosafecircle_{p}-config" for p in topology.provider_allowlist})

    def test_all_claude_two_launcher_handoff(self): self.exercise("all-claude")
    def test_all_codex_two_launcher_handoff(self): self.exercise("all-codex")
    def test_claude_balanced_two_launcher_handoff(self): self.exercise("claude-architect-balanced")
    def test_codex_balanced_two_launcher_handoff(self): self.exercise("codex-architect-balanced")

    def test_neutral_progress_label(self):
        from Pipeline.TaskReviewAgent.operator_logging import action_display_name
        label=action_display_name("run_execution_crew")
        self.assertNotIn("Claude",label)
        self.assertNotIn("Codex",label)


class BudgetBoundaryTests(unittest.TestCase):
    def test_bridge_mounts_only_profile_credentials_and_forwards_role_bundle(self):
        from types import SimpleNamespace
        from Pipeline.TaskReviewAgent.execution_bridge import ExecutionCrewBridge
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile,crew_role_routes
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{"NSC_CODEX_RESUME_SANDBOX_ARGUMENT":CONTROL}):
            root=Path(directory)
            accepted=SimpleNamespace(task_id="NSC-100",plan=SimpleNamespace(existing_implementation_paths=(),
                new_implementation_paths=("Assets/Fixture.cs",),existing_test_paths=(),new_test_paths=()))
            for name in PROFILES:
                topology=expand_profile(name)
                tier=load_execution_routing_policy({},supervisor_provider=topology.architect,
                    provider_allowlist=topology.provider_allowlist,resolve_only_permitted=True).standard
                for primary in topology.provider_allowlist:
                    routes=crew_role_routes(topology,primary,tier)
                    bridge=ExecutionCrewBridge(checkout=root,scope=SimpleNamespace(task_id="NSC-100"),
                        execution_model=routes["implementer"]["model"],provider_allowlist=topology.provider_allowlist,
                        provider_profile=dict(topology=topology.to_dict(),role_routes=routes,provider=primary))
                    argv=bridge._command(accepted,provider=primary,retry_run_id=None,feedback_file=None,
                        pool_assignment=dict(run_id="fixture",repository_identity="fixture/repo",
                            manifest_path=str(root/"manifest.json"),lease_bundle_path=str(root/"leases.json"),
                            profile_path=str(root/"profile.json")))
                    self.assertIn(primary+"-exec",argv)
                    for other in ("claude","codex"):
                        credential=any(f"nosafecircle_{other}-config:" in item for item in argv)
                        self.assertEqual(credential,other in topology.provider_allowlist and other!=primary)
                    self.assertEqual(argv[argv.index("--provider-role-profile")+1],"/nsc-pool/profile.json")

    def test_claude_decomposition_owner_never_resolves_codex_controls(self):
        from Pipeline.TaskReviewAgent import host_decomposition_launcher as host
        real_configuration=host.provider_configuration
        def only_claude(provider):
            self.assertEqual(provider,"claude")
            return real_configuration(provider)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(host,"_git",return_value="fixture/repo"), \
                patch.object(host,"provider_configuration",side_effect=only_claude), \
                patch.object(host,"codex_resume_activation_from_environment",side_effect=AssertionError("Codex resolved")):
            owner=host._decomposition_pool_owner(workspace=Path(directory)/"NSC-100",compose_project="fixture",
                providers=("claude","claude"))
            self.assertEqual(set(owner.provider_models),{"claude"})
            self.assertIsNone(owner.codex_resume_activation)
            owner.close()

    def test_supervisor_actual_turn_accounts_success_and_unknown_failure(self):
        from Pipeline.TaskReviewAgent.tests import supervisor_session_pool_smoke_test as f
        from Pipeline.TaskReviewAgent import provider_budget as budget
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
        topology=expand_profile("all-codex",token_budgets={"codex":10000})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ledger=budget.ProviderBudgetLedger(root/"budget.json",topology=topology,repository=f.REPOSITORY,run_id="fixture")
            ledger.assign(task_id=f.TASK,contract_sha256="a"*64,
                recommendation=ExecutionRecommendation("standard","no_preference","Fixture usage accounting.","no_preference"),
                snapshot=ledger.snapshot())
            ledger.register_worker(worker_run_id="run-1",task_id=f.TASK,contract_sha256="a"*64,provider="codex")
            harness=f.Harness(root)
            old=budget._WORKER_BUDGET.get()
            try:
                budget.bind_worker_budget(ledger.path,topology=topology,worker_run_id="run-1",
                    task_id=f.TASK,contract_sha256="a"*64,provider="codex")
                harness.decide(1)
                self.assertEqual(ledger.snapshot()["providers"]["codex"]["total_tokens"],1250)
                harness.fake.behavior="fail"
                with self.assertRaises(f.CodexSupervisorError): harness.decide(2)
                row=ledger.snapshot()["providers"]["codex"]
                self.assertEqual(row["invocation_count"],2)
                self.assertIsNone(row["total_tokens"])
                self.assertFalse(row["available"])
            finally:
                harness.close()
                budget._WORKER_BUDGET.set(old)

    def test_report_recomputes_tokens_read_only_and_refuses_foreign_ledger(self):
        from Pipeline.TaskReviewAgent.tests import run_evidence_report_smoke_test as f
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
        from Pipeline.TaskReviewAgent.provider_budget import ProviderBudgetLedger
        from Pipeline.TaskReviewAgent.run_autonomous_graph import _scheduler_id
        with tempfile.TemporaryDirectory() as directory:
            run,workers,providers=f.build_fixture(Path(directory))
            evidence=f.load_run_evidence(run_root=run,worker_output_root=workers,provider_call_roots=[providers])
            topology=expand_profile("codex-architect-balanced",token_budgets={"claude":100,"codex":1000})
            evidence.manifest["runtime_configuration"]["provider_topology"]=topology.to_dict()
            ledger=ProviderBudgetLedger(run/"provider-budget.json",topology=topology,repository="fixture/repo",
                run_id=_scheduler_id(evidence.manifest["github_repository"],evidence.run_id))
            ledger.snapshot()
            ledger.observe(invocation_id="last-call",provider="codex",role="polling_architect",
                usage=dict(input_tokens=80,cached_input_tokens=40,output_tokens=20,total_tokens=100))
            before={path.relative_to(run):path.read_bytes() for path in run.rglob("*") if path.is_file()}
            report=f.build_report(evidence)
            self.assertEqual(report["provider_budget"]["snapshot"]["providers"]["codex"]["total_tokens"],100)
            self.assertIn("| codex | 80 | 40 | 20 | 100 | 1000 | 0.1 |",f.render_markdown(report))
            self.assertEqual(before,{path.relative_to(run):path.read_bytes() for path in run.rglob("*") if path.is_file()})
            evidence.run_id="foreign-run"
            with self.assertRaises(f.RunEvidenceError): f.build_report(evidence)

    def test_profile_preflight_refuses_before_mutating_composition(self):
        from Pipeline.TaskReviewAgent import run_autonomous_graph as cli
        root=Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True), \
                patch.object(cli,"repo_root",return_value=root), \
                patch.object(cli,"resolve_issue_backend_repository",return_value="fixture/repo"), \
                patch.object(cli,"_load_or_create_manifest",side_effect=AssertionError("manifest mutation")), \
                patch.object(cli,"build_production_orchestrator",side_effect=AssertionError("provider construction")):
            for flags in (["--provider-profile","all-codex"],
                          ["--provider-profile","all-claude","--execution-provider","codex"]):
                self.assertEqual(cli.main(["--run-id","fixture","--source",str(root),
                    "--checkout-root",directory,"--confirm-repository","fixture/repo",*flags]),cli.EXIT_ADAPTER_FAILURE)
            self.assertEqual(list(Path(directory).rglob("*")),[])

    def test_probe_file_is_consumed_without_second_expansion(self):
        from Pipeline.TaskReviewAgent import run_autonomous_graph as cli
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile,routing_table
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"probe.json"
            topology=expand_profile("all-claude")
            payload=dict(status="work_remains",run_id="fixture",provider_topology=topology.to_dict(),routing_table=routing_table(topology))
            path.write_text(json.dumps(payload),encoding="utf-8")
            args=cli.build_parser().parse_args(["--run-id","fixture","--confirm-repository","fixture/repo",
                "--provider-profile","all-claude","--resolved-provider-topology-file",str(path)])
            with patch.object(cli,"expand_profile",side_effect=AssertionError("expanded twice")):
                self.assertEqual(cli._runtime_configuration(args,None).provider_topology,topology)
            payload["routing_table"]["architect"]="codex"
            path.write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(ValueError): cli._runtime_configuration(args,None)

    def test_mixed_evidence_checks_each_worker_supervisor_binding(self):
        from Pipeline.TaskReviewAgent.run_evidence_report import WorkerLaunch,supervisor_binding,RunEvidenceError
        from Pipeline.TaskReviewAgent.provider_profiles import expand_profile
        topology=expand_profile("claude-architect-balanced")
        runtime=dict(supervisor_provider="claude",provider_topology=topology.to_dict())
        launches=[WorkerLaunch("NSC-100",p,None,"2026-09-07T00:00:00Z",
            ("python","worker","--execution-provider",p,"--supervisor-provider",p)) for p in ("claude","codex")]
        self.assertEqual(supervisor_binding(runtime,launches)["launched_supervisor_providers"],["claude","codex"])
        launches[1]=replace(launches[1],argv=(*launches[1].argv[:-1],"claude"))
        with self.assertRaises(RunEvidenceError): supervisor_binding(runtime,launches)


if __name__=="__main__": unittest.main()
