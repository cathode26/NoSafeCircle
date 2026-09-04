#!/usr/bin/env python3
"""Behavioral tests for pooled ExecutionCrew leases driven through full `run_crew`.

Classification: in-memory/temporary-repository behavior tests. Every test runs
the real `run_crew` against throwaway Git repositories with a fake provider, so
no live provider, container, network call, Unity invocation, or tracked
repository file is involved. Each test proves an explicit regression-only
invariant of the pooled-session contract.

The load-bearing claims are: a lease is refused unless every identity matches
this exact execution, including the provider and routed model the role is really
invoked through; a role becomes reusable only when its AgentRuntime result, its
semantic validation, and the deterministic changed-path check all accepted the
work; the exact persisted role artifact -- hashed as the bytes on disk and bound
in those bytes to this exact assignment -- is what a later check-in verifies; a
role that never ran leaves no evidence and cannot be recycled; a proven failure
waits on non-advertised probation for at most one deliberate retry before the
committed streak policy retires it; and a repair attempt continues the same
conversation instead of opening a second one.

Every artifact this file writes or rewrites is written as exact bytes and hashed
from disk, so a Windows checkout cannot make an evidence regression pass or fail
for a newline-translation reason instead of the reason it states.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
# Throwaway repositories only: pin checkout conversion so a host autocrlf
# setting cannot change the bytes these fixtures commit.
os.environ["GIT_CONFIG_COUNT"] = "1"
os.environ["GIT_CONFIG_KEY_0"] = "core.autocrlf"
os.environ["GIT_CONFIG_VALUE_0"] = "false"

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from Pipeline.AgentRuntime.contracts import Usage  # noqa: E402
from Pipeline.AgentRuntime.providers.base import (  # noqa: E402
    ProviderFailure,
    ProviderInvocationResponse,
)
from Pipeline.ExecutionCrew.run_crew import (  # noqa: E402
    CrewBlocked,
    CrewSessionIdentityUnproven,
    checkout_manifest_identity,
    crew_repository_identity,
    run_crew,
    validate_role_session_leases,
)
from Pipeline.ExecutionCrew.session_pool import (  # noqa: E402
    CREW_SESSION_PROTOCOL_VERSION,
    AssignmentLease,
    DurableAssignmentResult,
    SessionCompatibility,
    SessionPool,
    SessionPoolError,
)
from Pipeline.TaskReviewAgent.real_checkout import RealTaskCheckoutManager  # noqa: E402

TASK = "NSC-005"
RELATED_TASK = "NSC-010"
IMPL = "Assets/Scripts/PlayerMana.cs"
TEST = "Assets/Tests/PlayerManaTests.cs"
OTHER = "Assets/Scripts/Other.cs"
MODEL = "pooled-crew-model"
OTHER_MODEL = "pooled-crew-other-model"
PROVIDER = "claude-code"
OTHER_PROVIDER = "openai-codex"
REPOSITORY = "https://github.com/cathode26/NoSafeCircle.git"
OTHER_REPOSITORY = "https://github.com/cathode26/Other.git"
OTHER_COMMIT = "b" * 40
BASE = dt.datetime(2026, 9, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
ROLE_CLASSES = {
    "contract_locality_auditor": "high_reasoning",
    "implementer": "standard",
    "test_author": "low_cost",
    "validator": "high_reasoning",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected: type[BaseException]) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def cmd(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args), check=True, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def artifact_digest(path: Path) -> str:
    """Return the SHA-256 of the bytes this artifact actually holds on disk.

    Pooled evidence is decided by bytes, so every fixture hashes the file as it
    exists rather than the string it hoped to write. Text-mode writing translates
    "\\n" to "\\r\\n" on Windows, which would silently make a tamper test hash
    bytes it never wrote and pass for the wrong reason.
    """

    payload = path.read_bytes()
    require(b"\r\n" not in payload, f"{path.name} was newline-translated on disk")
    return hashlib.sha256(payload).hexdigest()


def rewrite_role_artifact(run_dir: Path, artifact: str, mutate) -> str:
    """Rewrite one persisted role artifact as exact bytes; return its on-disk digest."""

    path = run_dir / artifact
    record = json.loads(path.read_bytes().decode("utf-8"))
    mutate(record)
    payload = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(payload)
    require(path.read_bytes() == payload, "the artifact on disk is not the bytes written")
    return artifact_digest(path)


def task_contract(task_id: str, key: str, title: str) -> dict:
    return {
        "schema_version": "2.0", "id": task_id, "contract_revision": 1,
        "contract_disposition": "active", "title": title, "reconciliation_key": key,
        "kind": "implementation", "execution_scope": "single_agent",
        "execution_reason": "Bounded fixture component that owns its own state.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Fixture requires no missing design.",
        "parent": "NSC-001", "depends_on": [], "exclusive_resources": [],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "fixture",
             "requirement": "Mana behavior is implemented."}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "fixture",
             "requirement": "Unity behavior is verified."}
        ],
        "downstream_integration_obligations": [], "provenance": {"origin": "fixture"},
    }


def fixture(parent: Path, *, directory_name: str = "source") -> Path:
    """Create one throwaway source checkout with a valid persistent work graph."""

    root = parent / directory_name
    root.mkdir()
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    cmd(root, "config", "user.name", "Pooled Crew Smoke")
    cmd(root, "config", "user.email", "pooled-crew@example.invalid")
    # Pooled reuse crosses tasks, so the crew proves the repository identity from
    # the checkout's own origin rather than trusting the caller.
    cmd(root, "remote", "add", "origin", REPOSITORY)
    write(root / IMPL, "public class PlayerMana { }\n")
    write(root / TEST, "public class PlayerManaTests { }\n")
    write(root / OTHER, "public class Other { }\n")
    root_task = {
        "schema_version": "2.0", "id": "NSC-001", "contract_revision": 1,
        "contract_disposition": "active", "title": "No Safe Circle",
        "reconciliation_key": "no-safe-circle", "kind": "feature",
        "execution_scope": "not_applicable", "execution_reason": "Project root.",
        "decomposition_state": "needs_decomposition",
        "decomposition_reason": "Project root.", "parent": "", "depends_on": [],
        "exclusive_resources": [], "acceptance_criteria": [], "completion_gates": [],
        "downstream_integration_obligations": [], "provenance": {"origin": "fixture"},
    }
    tasks = [
        root_task,
        task_contract(TASK, "player-mana", "Mana"),
        task_contract(RELATED_TASK, "related-fixture", "Related Fixture Dependency"),
    ]
    for task in tasks:
        write(root / f"Tasks/{task['id']}.yaml", json.dumps(task) + "\n")
    write(
        root / "Pipeline/TaskGraph/WORK_ID_MAP.json",
        json.dumps({"id_map": {task["reconciliation_key"]: task["id"] for task in tasks}}) + "\n",
    )
    write(root / "Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml", json.dumps({"requirements": []}) + "\n")
    write(root / "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml", json.dumps({"resource_groups": []}) + "\n")
    write(
        root / "Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json",
        json.dumps({
            "schema_version": "1.0", "bootstrap_status": "complete",
            "serialization_format": "yaml_1_2_json_subset",
            "output_sha256": {"Tasks/NSC-001.yaml": "fixture"},
        }) + "\n",
    )
    write(root / "Docs/GDD/No_Safe_Circle_GDD.md", "# GDD\nMana exists.\n")
    write(root / "Docs/Engineering/UNITY_TESTING_POLICY.md", "# Policy\nNever claim tests passed.\n")
    write(
        root / "Docs/Engineering/ENGINEERING_STANDARDS.md",
        "# Engineering Standards\n## Reuse and tool selection\nSearch before creating parallel infrastructure.\n",
    )
    cmd(root, "add", ".")
    cmd(root, "commit", "-qm", "baseline")
    return root


class State:
    """Records what each pooled role invocation actually received."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.invocations: list[dict] = []
        self.assigned = itertools.count(1)

    def attempts(self, role: str) -> int:
        return sum(1 for item in self.invocations if item["role"] == role)

    def for_role(self, role: str) -> list[dict]:
        return [item for item in self.invocations if item["role"] == role]


class PooledFakeProvider:
    """A fake provider that honors an exact session binding and confirms it.

    It answers to the exact provider identity the lease authorizes. A fake that
    called itself something else would let the evidence claim `claude-code` while
    a different provider actually ran, which is the identity the pooled boundary
    exists to prove.
    """

    provider_identifier = "claude-code"

    def __init__(self, state, repo, writable, role, session, session_ledger):
        self.state = state
        self.repo = repo
        self.writable = writable
        self.role = role
        self.session = session
        self.session_ledger = session_ledger

    def invoke(self, request, model):
        state = self.state
        attempt = state.attempts(self.role) + 1
        state.invocations.append({
            "role": self.role, "attempt": attempt, "prompt": request.prompt,
            "capability_class": request.model_capability_class,
            "mode": None if self.session is None else self.session.mode,
            "session_id": None if self.session is None else self.session.session_id,
        })
        if self.session is not None and not self.withholds_identity(attempt):
            observed = self.session.session_id or (
                f"beef0000-1111-4111-8111-{next(state.assigned):012x}"
            )
            self.session_ledger.record(self.session.confirm(observed))
        self.maybe_terminal_provider_error(attempt)
        output = self.role_output(attempt)
        return ProviderInvocationResponse(output, "fake log\n", ("runtime-claim.cs",),
                                          Usage(attempt, attempt + 1, attempt + 10), True, ())

    def withholds_identity(self, attempt: int) -> bool:
        """Model a turn that ends before the transcript ever names its conversation.

        The fixed Claude adapter records an identity only when the terminal event
        proves it, so a scenario that proves nothing must leave the ledger empty
        rather than fabricate a plausible UUID.
        """

        scenario = self.state.scenario
        if scenario == "test_author_identity_unproven":
            return self.role == "test_author" and attempt == 1
        if scenario == "test_author_success_without_identity":
            return self.role == "test_author"
        return False

    def maybe_terminal_provider_error(self, attempt: int) -> None:
        """Reproduce the live NSC-914 terminal failure for one role, once.

        The Test Author emitted several StructuredOutput tool calls and the CLI
        then closed the turn with an error. The conversation is unaffected by
        that; only the turn's output is. `ProviderFailure` is exactly what the
        real adapter raises for it, and AgentRuntime classifies it
        `provider_error`.
        """

        if self.role != "test_author" or attempt != 1:
            return
        if self.state.scenario in (
            "test_author_format_failure", "test_author_identity_unproven"
        ):
            raise ProviderFailure(
                "Claude Code reported an unsuccessful result "
                "(is_error=True, subtype='error_during_execution', "
                "terminal_reason='error')",
                raw_log="fake log\n",
            )

    def role_output(self, attempt: int) -> dict:
        scenario = self.state.scenario
        if self.role == "contract_locality_auditor":
            return self.audit_output(scenario)
        if self.role == "implementer":
            if scenario == "schema_invalid_implementer":
                return {}
            target = OTHER if scenario == "scope_rejected_implementer" else IMPL
            write(self.repo / target,
                  "public class PlayerMana { public int Mana;"
                  + (" public int Repaired;" if attempt == 2 else "") + " }\n")
            return {"summary": "implementation", "claimed_changed_paths": [target],
                    "blockers": [], "notes": []}
        if self.role == "test_author":
            write(self.repo / TEST,
                  "public class PlayerManaTests { public void ManaTest() {}"
                  + (" public void RepairTest() {}" if attempt == 2 else "") + " }\n")
            return {"summary": "tests", "claimed_changed_paths": [TEST],
                    "test_cases_added_or_updated": ["ManaTest"], "blockers": [],
                    "known_limitations": ["not run"], "proposed_unity_test_scope": "Play Mode"}
        status = "needs_changes" if (scenario == "repair" and attempt == 1) else "pass"
        return {
            "status": status, "summary": "review",
            "criteria_results": [
                {"id": "AC-001", "status": "pass", "reason_code": "proved",
                 "evidence": "source review"},
                {"id": "VAL-001", "status": "not_proven", "reason_code": "runtime_not_executed",
                 "evidence": "Unity was not run"},
            ],
            "blocking_issues": ([{"path": IMPL, "issue": "fix mana",
                                  "required_fix": "add repaired marker"}]
                                if status == "needs_changes" else []),
            "risks": [], "files_reviewed": [IMPL, TEST],
        }

    def audit_output(self, scenario: str) -> dict:
        def local(entry_id: str, entry_type: str) -> dict:
            return {"id": entry_id, "entry_type": entry_type, "classification": "local_to_task",
                    "evidence": "owned locally by this task", "related_task_ids": [],
                    "recommended_action": "keep"}

        entries = [local("AC-001", "acceptance_criterion"), local("VAL-001", "completion_gate")]
        if scenario != "contract_review_required":
            return {"status": "pass", "summary": "locality audit", "entry_results": entries,
                    "blocking_findings": [], "files_reviewed": [IMPL, TEST]}
        entries[1] = {
            "id": "VAL-001", "entry_type": "completion_gate",
            "classification": "requires_declared_dependency",
            "evidence": "cannot be proven without another task's already-integrated behavior",
            "related_task_ids": [RELATED_TASK], "recommended_action": "add_dependency",
        }
        return {
            "status": "contract_review_required", "summary": "locality audit",
            "entry_results": entries,
            "blocking_findings": [{"entry_id": "VAL-001",
                                   "reason_code": "requires_declared_dependency",
                                   "issue": "needs a declared dependency",
                                   "recommended_action": "add_dependency",
                                   "related_task_ids": [RELATED_TASK]}],
            "files_reviewed": [IMPL, TEST],
        }


def factory(state: State, *, provider_identity: str = PROVIDER, model: str = MODEL):
    """Return a session-aware provider factory bound to one exact identity.

    The configuration provider and model are what AgentRuntime resolves and what
    `AgentResult` then reports, so a scenario can state a wrong provider or a
    wrong routed model and the pooled boundary must refuse it.
    """

    def create(provider, repo, writable, role, session=None, session_ledger=None):
        key = f"{provider}-crew"
        config = RuntimeConfiguration({
            key: {"provider": provider_identity,
                  "models": {"low_cost": model, "standard": model, "high_reasoning": model}}
        })
        fake = PooledFakeProvider(state, repo, writable, role, session, session_ledger)
        fake.provider_identifier = provider_identity
        return key, config, {provider_identity: fake}

    return create


def ephemeral_factory(state: State):
    """A historical four-argument factory that cannot carry a pooled session."""

    def create(provider, repo, writable, role):
        return factory(state)(provider, repo, writable, role)

    return create


def identity_factory(start: int = 1):
    counter = itertools.count(start)

    def make() -> str:
        value = next(counter)
        return f"{value:08x}-1111-4111-8111-{value:012x}"

    return make


def source_identity(root: Path) -> tuple[str, str]:
    """Return the exact head and checkout identity `run_crew` will capture."""

    top = Path(cmd(root, "rev-parse", "--show-toplevel")).resolve()
    return cmd(top, "rev-parse", "--verify", "HEAD"), str(top)


def new_pool(*, identity_start: int = 1) -> SessionPool:
    return SessionPool(identity_factory=identity_factory(identity_start), clock=lambda: BASE)


def compatibility(role: str, *, repository: str = REPOSITORY,
                  capability_class: str | None = None) -> SessionCompatibility:
    return SessionCompatibility(
        "claude-code", MODEL, None, role,
        capability_class or ROLE_CLASSES[role], repository,
        CREW_SESSION_PROTOCOL_VERSION, "worker",
    )


def lease_for(pool: SessionPool, role: str, *, head: str, checkout: str, run_id: str,
              task_id: str = TASK, repository: str = REPOSITORY,
              capability_class: str | None = None, slot: str = "worker-slot-1",
              now: dt.datetime | None = None) -> AssignmentLease:
    return pool.checkout(
        compatibility=compatibility(role, repository=repository,
                                    capability_class=capability_class),
        worker_slot_id=slot, task_id=task_id, worker_run_id=run_id,
        source_commit=head, checkout_identity=checkout, now=now or BASE,
    )


def all_leases(pool: SessionPool, *, head: str, checkout: str, run_id: str,
               now: dt.datetime | None = None) -> dict[str, AssignmentLease]:
    return {
        role: lease_for(pool, role, head=head, checkout=checkout, run_id=run_id,
                        slot="worker-slot-1", now=now)
        for role in ROLE_CLASSES
    }


def pooled_run(source: Path, outputs: Path, *, run_id: str, leases, state: State,
               repository: str = REPOSITORY, factory_kind=factory,
               checkout_identity_manifest: Path | None = None,
               crew_profile: str | None = None,
               validation_profile: str | None = None):
    return run_crew(
        source=source, output_root=outputs, task_id=TASK, provider_name="claude",
        implementation_paths=(IMPL,), test_paths=(TEST,), run_id=run_id,
        execution_model=MODEL, provider_factory=factory_kind(state),
        _require_physical_read_only_source=False, role_session_leases=leases,
        scheduler_repository_identity=repository,
        checkout_identity_manifest=checkout_identity_manifest,
        crew_profile=crew_profile,
        validation_profile=validation_profile,
    ), outputs / run_id


# --------------------------------------------- 1: exact execution identity


def test_full_run_refuses_a_lease_from_another_execution() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        require(crew_repository_identity(Path(checkout)) == REPOSITORY, "origin identity drifted")

        cases = (
            ("commit", {"head": OTHER_COMMIT}, "bound to source commit"),
            ("checkout", {"checkout": str(parent / "elsewhere")}, "bound to source checkout"),
            ("repository", {"repository": OTHER_REPOSITORY}, "bound to repository"),
            ("capability class", {"capability_class": "low_cost"}, "capability class"),
        )
        for index, (label, override, expected) in enumerate(cases):
            pool = new_pool()
            run_id = f"nsc-005-identity-{index}"
            state = State("pass")
            leases = {
                "implementer": lease_for(
                    pool, "implementer", head=override.get("head", head),
                    checkout=override.get("checkout", checkout), run_id=run_id,
                    repository=override.get("repository", REPOSITORY),
                    capability_class=override.get("capability_class"),
                )
            }
            blocked = rejects(
                lambda leases=leases, run_id=run_id, state=state: pooled_run(
                    source, outputs, run_id=run_id, leases=leases, state=state
                ),
                CrewBlocked,
            )
            require(expected in str(blocked), f"{label}: {blocked}")
            require(not state.invocations, f"{label}: a provider ran before the lease was proven")

        # A repository the scheduler asserts but the checkout does not confirm is
        # refused even when every lease agrees with the scheduler.
        pool = new_pool()
        run_id = "nsc-005-identity-scheduler"
        state = State("pass")
        leases = {
            "implementer": lease_for(pool, "implementer", head=head, checkout=checkout,
                                     run_id=run_id, repository=OTHER_REPOSITORY)
        }
        blocked = rejects(
            lambda: pooled_run(source, outputs, run_id=run_id, leases=leases, state=state,
                               repository=OTHER_REPOSITORY),
            CrewBlocked,
        )
        require("differs from the source checkout's repository" in str(blocked), str(blocked))
        require(not state.invocations, "a provider ran for an unproven repository")

        # Pooled leases require the scheduler to state the repository at all.
        blocked = rejects(
            lambda: run_crew(
                source=source, output_root=outputs, task_id=TASK, provider_name="claude",
                implementation_paths=(IMPL,), test_paths=(TEST,), run_id="nsc-005-identity-none",
                execution_model=MODEL, provider_factory=factory(State("pass")),
                _require_physical_read_only_source=False, role_session_leases=leases,
            ),
            CrewBlocked,
        )
        require("scheduler-proven repository identity" in str(blocked), str(blocked))


def test_a_lease_from_another_crew_protocol_is_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        head, checkout = source_identity(source)
        pool = new_pool()
        lease = lease_for(pool, "implementer", head=head, checkout=checkout, run_id="nsc-005-p")
        common = {
            "task_id": TASK, "run_id": "nsc-005-p", "provider_identifier": "claude-code",
            "model": MODEL, "reasoning_effort": None, "source_commit": head,
            "checkout_identity": checkout, "repository_identity": REPOSITORY,
        }
        require(
            validate_role_session_leases({"implementer": lease}, **common)
            == {"implementer": lease},
            "the matching lease was refused",
        )
        blocked = rejects(
            lambda: validate_role_session_leases({"implementer": lease}, protocol_version="9.9",
                                                 **common),
            CrewBlocked,
        )
        require("crew/session protocol" in str(blocked), str(blocked))
        # A durable lease that speaks another protocol cannot even be restored.
        rejects(lambda: AssignmentLease.from_dict({**lease.to_dict(), "protocol_version": "9.9"}),
                SessionPoolError)


# ------------------------------------------- 2: reusability requires proof


def test_a_scope_rejected_implementer_is_never_reusable() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-scope"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("scope_rejected_implementer")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "rejected", str(result["crew_status"]))
        require("implementer" not in result["reusable_role_sessions"],
                str(result["reusable_role_sessions"]))
        evidence = result["durable_assignment_results"]["implementer"]
        require(evidence["changed_path_validation"] == "rejected", str(evidence))
        require(evidence["assignment_outcome"] == "output_failure", str(evidence))
        require(evidence["status"] == "completed",
                "a role whose process finished must not be reported as a provider failure")
        # The provider confirmed a session; that confirmation alone must not recycle it.
        require(evidence["confirmed_session"]["session_id"] == leases["implementer"].session_id,
                str(evidence["confirmed_session"]))
        session = pool.check_in(
            lease=leases["implementer"],
            result=DurableAssignmentResult.from_dict(evidence),
            evidence_root=run_dir,
        )
        # A proven output failure is counted by the committed policy and held on
        # probation: never advertised, never reusable, never offered by checkout.
        require(session.state == "probation", str(session.state))
        require("changed paths rejected" in (session.probation_reason or ""),
                str(session.probation_reason))
        require(not session.is_reusable_at(BASE), "a scope-rejected session stayed reusable")
        require(session.lifecycle.consecutive_provider_output_failures == 1,
                str(session.lifecycle))
        later = lease_for(pool, "implementer", head=head, checkout=checkout,
                          run_id="nsc-005-scope-2", now=BASE + dt.timedelta(seconds=60))
        require(later.mode == "start", "a scope-rejected conversation was offered as warm")


def test_failed_role_output_is_never_reusable() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-schema"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("schema_invalid_implementer")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "rejected", str(result["crew_status"]))
        require("implementer" not in result["reusable_role_sessions"],
                str(result["reusable_role_sessions"]))
        evidence = result["durable_assignment_results"]["implementer"]
        require(evidence["status"] == "failed", str(evidence))
        require(evidence["assignment_outcome"] in {"output_failure", "provider_failure",
                                                   "other_failure"}, str(evidence))
        record = json.loads((run_dir / evidence["role_result_artifact"]).read_text(encoding="utf-8"))
        require(record["agent_status"] == "failed", str(record["agent_status"]))
        session = pool.check_in(
            lease=leases["implementer"],
            result=DurableAssignmentResult.from_dict(evidence),
            evidence_root=run_dir,
        )
        require(session.state == "probation", str(session.state))
        require(not session.is_reusable_at(BASE), "a failed role stayed reusable")
        # The committed streak is reachable from a real run: one deliberate,
        # compatible retry is offered, and a second counted failure retires it.
        retry = pool.offer_probation_retry(
            compatibility=compatibility("implementer"), record_id=session.record_id,
            worker_slot_id="worker-slot-2", task_id=TASK, worker_run_id="nsc-005-schema-2",
            source_commit=head, checkout_identity=checkout,
            now=BASE + dt.timedelta(seconds=60),
        )
        require(retry.mode == "resume" and retry.session_id == session.session_id, str(retry))
        second, second_dir = pooled_run(source, parent / "outputs-retry",
                                        run_id="nsc-005-schema-2",
                                        leases={"implementer": retry},
                                        state=State("schema_invalid_implementer"))
        require("implementer" not in second["reusable_role_sessions"],
                str(second["reusable_role_sessions"]))
        retired = pool.check_in(
            lease=retry,
            result=DurableAssignmentResult.from_dict(
                second["durable_assignment_results"]["implementer"]
            ),
            evidence_root=second_dir,
        )
        require(retired.retirement_reason == "consecutive_provider_output_failures",
                str(retired.retirement_reason))
        require(not retired.is_reusable_at(BASE) and not retired.is_retry_offerable_at(BASE),
                "a retired conversation was still offerable")


def test_a_successful_roles_exact_artifact_checks_in_and_resumes() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-pass"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("pass")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "review_ready", str(result["crew_status"]))
        require(set(result["reusable_role_sessions"]) == set(ROLE_CLASSES),
                str(result["reusable_role_sessions"]))
        for role, lease in leases.items():
            evidence = DurableAssignmentResult.from_dict(result["durable_assignment_results"][role])
            require(evidence.is_reusable, f"{role}: {evidence.assignment_outcome}")
            require(evidence.capability_class == ROLE_CLASSES[role], f"{role}: {evidence}")
            require(evidence.crew_run_id == run_id, f"{role}: {evidence.crew_run_id}")
            require(evidence.source_commit == head and evidence.checkout_identity == checkout,
                    f"{role}: {evidence}")
            # The provider and model that actually ran are the lease's, and the
            # artifact on disk hashes exactly to the durable claim on any
            # platform and binds itself to this exact assignment.
            require(evidence.provider_identifier == PROVIDER and evidence.model == MODEL,
                    f"{role}: {evidence.provider_identifier} {evidence.model}")
            payload = (run_dir / evidence.role_result_artifact).read_bytes()
            require(hashlib.sha256(payload).hexdigest() == evidence.role_result_sha256,
                    f"{role}: the on-disk artifact does not hash to its durable claim")
            require(b"\r\n" not in payload, f"{role}: the artifact was newline-translated")
            record = json.loads(payload.decode("utf-8"))
            require(record["provider"] == PROVIDER and record["model"] == MODEL,
                    f"{role}: {record['provider']} {record['model']}")
            require(record["pooled_assignment_evidence"] == evidence.role_evidence_binding(),
                    f"{role}: the artifact binding differs from its durable claim")
            require(record["pooled_assignment_evidence"]["confirmed_session"]
                    == evidence.confirmed_session.to_dict(), role)
            returned = pool.check_in(lease=lease, result=evidence, evidence_root=run_dir)
            require(returned.state == "idle", f"{role}: {returned.state}")
            require(returned.completed_assignment_count == 1, f"{role}: {returned}")
        # A warm conversation is offered back to the same role on the next run.
        warm = lease_for(pool, "implementer", head=head, checkout=checkout,
                         run_id="nsc-005-pass-2", now=BASE + dt.timedelta(seconds=60))
        require(warm.mode == "resume", "a proven session was not reused")
        require(warm.session_id == leases["implementer"].session_id, "a different conversation")


def test_missing_or_tampered_role_evidence_cannot_check_in() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        run_id = "nsc-005-evidence"

        def prepared():
            pool = new_pool()
            leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
            state = State("pass")
            output_root = parent / f"outputs-{next(counter)}"
            result, run_dir = pooled_run(source, output_root, run_id=run_id, leases=leases,
                                         state=state)
            evidence = DurableAssignmentResult.from_dict(
                result["durable_assignment_results"]["implementer"]
            )
            return pool, leases["implementer"], evidence, run_dir

        counter = itertools.count(1)
        require(outputs is not None, "output root is required")

        # No crew run directory at all is not evidence.
        pool, lease, evidence, run_dir = prepared()
        session = pool.check_in(lease=lease, result=evidence, evidence_root=None)
        require(session.state == "quarantined", str(session.state))
        require("no crew run directory" in (session.quarantine_reason or ""),
                str(session.quarantine_reason))

        # A deleted artifact is not evidence.
        pool, lease, evidence, run_dir = prepared()
        (run_dir / evidence.role_result_artifact).unlink()
        session = pool.check_in(lease=lease, result=evidence, evidence_root=run_dir)
        require(session.state == "quarantined", str(session.state))
        require("missing or unreadable" in (session.quarantine_reason or ""),
                str(session.quarantine_reason))

        # A tampered artifact no longer hashes to the recorded digest. The
        # tamper and the hash are both taken from the bytes on disk, so this
        # rejection cannot come from platform newline translation.
        pool, lease, evidence, run_dir = prepared()
        require(artifact_digest(run_dir / evidence.role_result_artifact)
                == evidence.role_result_sha256,
                "the run's own artifact does not hash to its durable claim")
        tampered = rewrite_role_artifact(
            run_dir, evidence.role_result_artifact,
            lambda record: record.update({"scope_check_reasons": ["invented after the fact"]}),
        )
        require(tampered != evidence.role_result_sha256, "the tamper did not change the bytes")
        session = pool.check_in(lease=lease, result=evidence, evidence_root=run_dir)
        require(session.state == "quarantined", str(session.state))
        require("SHA-256" in (session.quarantine_reason or ""), str(session.quarantine_reason))

        # Re-hashing a rewritten decision does not help: the artifact must still
        # agree with the durable claim. The rehashed claim is the exact on-disk
        # digest, so the only remaining contradiction is the semantic one.
        pool, lease, evidence, run_dir = prepared()
        digest = rewrite_role_artifact(
            run_dir, evidence.role_result_artifact,
            lambda record: record.update({"deterministic_changed_path_validation": "rejected"}),
        )
        rehashed = DurableAssignmentResult.from_dict({
            **evidence.to_dict(), "role_result_sha256": digest,
        })
        require(artifact_digest(run_dir / rehashed.role_result_artifact)
                == rehashed.role_result_sha256,
                "the rehashed claim is not the on-disk digest")
        session = pool.check_in(lease=lease, result=rehashed, evidence_root=run_dir)
        require(session.state == "quarantined", str(session.state))
        require("disagrees with the durable claim" in (session.quarantine_reason or ""),
                str(session.quarantine_reason))

        # Another role's proven artifact does not prove this role.
        pool, lease, evidence, run_dir = prepared()
        borrowed = DurableAssignmentResult.from_dict({
            **evidence.to_dict(), "role_result_artifact": "role_results/validator_1.json",
        })
        session = pool.check_in(lease=lease, result=borrowed, evidence_root=run_dir)
        require(session.state == "quarantined", str(session.state))

        # The same role's successful artifact from another crew run, lease, and
        # task cannot be copied in either, byte-for-byte and rehashed.
        donor_pool = new_pool(identity_start=200)
        donor_leases = all_leases(donor_pool, head=head, checkout=checkout,
                                  run_id="nsc-005-evidence-donor")
        donor, donor_dir = pooled_run(source, parent / "outputs-donor",
                                      run_id="nsc-005-evidence-donor", leases=donor_leases,
                                      state=State("pass"))
        donor_evidence = DurableAssignmentResult.from_dict(
            donor["durable_assignment_results"]["implementer"]
        )
        pool, lease, evidence, run_dir = prepared()
        require(donor_evidence.role_result_artifact == evidence.role_result_artifact,
                "the copy must reuse the same run-relative path")
        donor_bytes = (donor_dir / donor_evidence.role_result_artifact).read_bytes()
        (run_dir / evidence.role_result_artifact).write_bytes(donor_bytes)
        copied = DurableAssignmentResult.from_dict({
            **evidence.to_dict(),
            "role_result_sha256": hashlib.sha256(donor_bytes).hexdigest(),
        })
        session = pool.check_in(lease=lease, result=copied, evidence_root=run_dir)
        require(session.state == "quarantined", str(session.state))
        reason = session.quarantine_reason or ""
        require("binding disagrees with the durable claim" in reason, reason)
        for field in ("crew_run_id", "lease_id", "record_id", "worker_run_id"):
            require(f"'{field}'" in reason, f"{field} was not compared: {reason}")
        require(not session.is_reusable_at(BASE), "a copied artifact recycled a session")


# ------------------------------------- 3: uninvoked roles and repair cycles


def test_early_contract_audit_termination_leaves_later_roles_unproven() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-audit-stop"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("contract_review_required")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "contract_review_required", str(result["crew_status"]))
        require(result["attempts_used"] == 0, str(result["attempts_used"]))
        require([item["role"] for item in state.invocations] == ["contract_locality_auditor"],
                str([item["role"] for item in state.invocations]))
        require(set(result["reusable_role_sessions"]) == {"contract_locality_auditor"},
                str(result["reusable_role_sessions"]))
        for role in ("implementer", "test_author", "validator"):
            record = result["pooled_role_leases"][role]
            require(record["invoked"] is False, f"{role}: {record['invoked']}")
            require(record["durable_assignment_result"] is None, f"{role}: {record}")
            require(role not in result["durable_assignment_results"], role)
            # A lease with no evidence is returned deliberately, never recycled.
            session = pool.check_in(lease=leases[role], result=None, evidence_root=run_dir)
            require(session.state == "quarantined", f"{role}: {session.state}")
            require("no durable assignment result" in (session.quarantine_reason or ""),
                    str(session.quarantine_reason))
            fresh = lease_for(pool, role, head=head, checkout=checkout, run_id="nsc-005-later",
                              now=BASE + dt.timedelta(seconds=60))
            require(fresh.mode == "start", f"{role}: an unproven conversation was reused")
        auditor = DurableAssignmentResult.from_dict(
            result["durable_assignment_results"]["contract_locality_auditor"]
        )
        returned = pool.check_in(lease=leases["contract_locality_auditor"], result=auditor,
                                 evidence_root=run_dir)
        require(returned.state == "idle", str(returned.state))


def test_a_repair_attempt_keeps_the_same_role_session() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-repair"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("repair")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "review_ready", str(result["crew_status"]))
        require(result["attempts_used"] == 2, str(result["attempts_used"]))
        for role in ("implementer", "test_author", "validator"):
            calls = state.for_role(role)
            require(len(calls) == 2, f"{role}: {len(calls)} invocations")
            require(calls[0]["session_id"] == calls[1]["session_id"] == leases[role].session_id,
                    f"{role}: a repair attempt changed conversation")
            require(calls[1]["mode"] == "resume", f"{role}: a repair attempt started a new session")
        require(len({record["session_id"] for record in result["provider_sessions"]}) == 4,
                str(result["provider_sessions"]))
        # The last attempt's artifact is the evidence, and it still checks in.
        evidence = DurableAssignmentResult.from_dict(
            result["durable_assignment_results"]["implementer"]
        )
        require(evidence.role_result_artifact == "role_results/implementer_2.json",
                evidence.role_result_artifact)
        returned = pool.check_in(lease=leases["implementer"], result=evidence,
                                 evidence_root=run_dir)
        require(returned.state == "idle", str(returned.state))


def test_a_reused_session_receives_the_capsule_once() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        head, checkout = source_identity(source)
        pool = new_pool()
        first_leases = all_leases(pool, head=head, checkout=checkout, run_id="nsc-005-warm-1")
        first, first_dir = pooled_run(source, parent / "outputs-1", run_id="nsc-005-warm-1",
                                      leases=first_leases, state=State("pass"))
        require(first["crew_status"] == "review_ready", str(first["crew_status"]))
        for role, lease in first_leases.items():
            pool.check_in(
                lease=lease,
                result=DurableAssignmentResult.from_dict(first["durable_assignment_results"][role]),
                evidence_root=first_dir,
            )
        warm = all_leases(pool, head=head, checkout=checkout, run_id="nsc-005-warm-2",
                          now=BASE + dt.timedelta(seconds=60))
        require(all(lease.mode == "resume" for lease in warm.values()), str(warm))
        state = State("repair")
        second, _ = pooled_run(source, parent / "outputs-2", run_id="nsc-005-warm-2",
                               leases=warm, state=state)
        require(second["crew_status"] == "review_ready", str(second["crew_status"]))
        for role in ROLE_CLASSES:
            calls = state.for_role(role)
            capsules = [call for call in calls if "New assignment capsule." in call["prompt"]]
            require(len(capsules) == 1, f"{role}: {len(capsules)} capsules for one assignment")
            require(capsules[0]["attempt"] == 1, f"{role}: the capsule was not on the first attempt")
            require("has expired and no longer applies" in capsules[0]["prompt"], role)


def test_a_pooled_lease_requires_a_session_aware_provider() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-ephemeral"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        blocked = rejects(
            lambda: pooled_run(source, parent / "outputs", run_id=run_id, leases=leases,
                               state=State("pass"), factory_kind=ephemeral_factory),
            CrewBlocked,
        )
        require("session binding and ledger" in str(blocked), str(blocked))


# -------------------------------- 4: the identity that is actually invoked


def test_a_pooled_role_is_never_invoked_through_another_provider_or_model() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        head, checkout = source_identity(source)
        for label, kind, expected in (
            ("provider",
             lambda state: factory(state, provider_identity=OTHER_PROVIDER),
             f"resolves provider {OTHER_PROVIDER!r}"),
            ("model",
             lambda state: factory(state, model=OTHER_MODEL),
             f"resolves model {OTHER_MODEL!r}"),
        ):
            pool = new_pool()
            run_id = f"nsc-005-route-{label}"
            leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
            state = State("pass")
            blocked = rejects(
                lambda kind=kind, run_id=run_id, leases=leases, state=state, label=label:
                    pooled_run(source, parent / f"outputs-{label}", run_id=run_id,
                               leases=leases, state=state, factory_kind=kind),
                CrewBlocked,
            )
            require(expected in str(blocked), f"{label}: {blocked}")
            require("its lease authorizes" in str(blocked), f"{label}: {blocked}")
            require(not state.invocations,
                    f"{label}: a provider ran before its identity was proven")
            # Nothing ran, so nothing is advertised and no lease can be checked
            # in as reusable on this run's word.
            for role, lease in leases.items():
                session = pool.check_in(lease=lease, result=None, evidence_root=None)
                require(session.state == "quarantined", f"{label}/{role}: {session.state}")
                require(not session.is_reusable_at(BASE),
                        f"{label}/{role}: an uninvoked lease stayed reusable")
                fresh = lease_for(pool, role, head=head, checkout=checkout,
                                  run_id=f"{run_id}-2", now=BASE + dt.timedelta(seconds=60))
                require(fresh.mode == "start",
                        f"{label}/{role}: an unproven conversation was offered again")


def forged_lease(lease: AssignmentLease, **overrides) -> AssignmentLease:
    """Return an adversarial lease object that never passed lease construction.

    `AssignmentLease` correctly refuses another crew/session protocol outright,
    so the only way to prove that `run_crew` itself refuses one is to hand it an
    object that skipped that construction entirely.
    """

    forged = object.__new__(AssignmentLease)
    for name, value in {**lease.to_dict(), **overrides}.items():
        object.__setattr__(forged, name, value)
    return forged


def test_a_nested_protocol_mismatch_is_refused_by_the_full_run() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-protocol-run"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        # Normal construction refuses it, so the regression uses the adversarial
        # object instead of asserting a state that cannot exist.
        rejects(lambda: AssignmentLease.from_dict(
            {**leases["implementer"].to_dict(), "protocol_version": "9.9"}), SessionPoolError)
        forged = forged_lease(leases["implementer"], protocol_version="9.9")
        require(type(forged) is AssignmentLease, str(type(forged)))
        require(forged.protocol_version == "9.9", forged.protocol_version)
        state = State("pass")
        blocked = rejects(
            lambda: pooled_run(source, parent / "outputs-protocol", run_id=run_id,
                               leases={**leases, "implementer": forged}, state=state),
            CrewBlocked,
        )
        require("crew/session protocol" in str(blocked), str(blocked))
        require(not state.invocations,
                "a provider ran for an unknown crew/session protocol")
        # The run produced no result at all, so no conversation can be recycled
        # on its word: every lease returns deliberately with no evidence.
        for role, lease in leases.items():
            session = pool.check_in(lease=lease, result=None, evidence_root=None)
            require(session.state == "quarantined", f"{role}: {session.state}")
            require(not session.is_reusable_at(BASE), f"{role}: an unproven lease stayed reusable")


def test_full_run_uses_external_manifest_bytes_as_cross_os_checkout_identity() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-manifest-") as text:
        parent = Path(text)
        source = fixture(parent, directory_name=TASK)
        outputs = parent / "outputs-manifest"
        cmd(source, "branch", "-m", "nsc-005-manifest-fixture")
        head, _ = source_identity(source)
        branch = cmd(source, "branch", "--show-current")
        task_bytes = (source / f"Tasks/{TASK}.yaml").read_bytes()
        contract_hash = hashlib.sha256(task_bytes).hexdigest()
        observation = {
            "task": {
                "task_id": TASK,
                "title": "Manifest fixture",
                "contract_path": f"Tasks/{TASK}.yaml",
                "contract_revision": 1,
                "task_contract_sha256": contract_hash,
            },
            "environment": {
                "source_head": head,
                "source_tree": cmd(source, "rev-parse", "HEAD^{tree}"),
            },
        }
        manager = RealTaskCheckoutManager(
            source_root=source,
            task_id=TASK,
            checkout_root=parent,
            worker_id="worker-slot-1",
            allow_local_remote_for_tests=True,
        )
        manager._write_manifest(observation, REPOSITORY)
        manifest_path = manager.manifest_path
        checkout_identity = checkout_manifest_identity(
            manifest_path,
            task_id=TASK,
            repository_identity=REPOSITORY,
            source_branch=branch,
            source_commit=head,
            worker_slot_id="worker-slot-1",
            task_contract_sha256=contract_hash,
        )
        run_id = "nsc-005-manifest-identity"
        pool = new_pool()
        leases = all_leases(
            pool, head=head, checkout=checkout_identity, run_id=run_id
        )
        result, run_dir = pooled_run(
            source,
            outputs,
            run_id=run_id,
            leases=leases,
            state=State("pass"),
            checkout_identity_manifest=manifest_path,
        )
        require(result["crew_status"] == "review_ready", str(result["crew_status"]))
        require(
            all(
                value["checkout_identity"] == checkout_identity
                for value in result["pooled_role_leases"].values()
            ),
            "full run did not bind every role to the external manifest bytes",
        )
        require((run_dir / "crew_result.json").is_file(), "full run result missing")




# ------------------- 5: a role-level provider-format failure stays role-level
#
# NSC-914's first pooled run: the Test Author's turn ended with a provider
# format error. The crew had no way to say so -- it raised a generic block, left
# no authoritative result, and its owner quarantined all four reservations, so
# the entire crew was re-run from scratch and every earlier role re-read its
# context. These tests pin the bounded behavior that replaces it.


def progress_events(run_dir: Path) -> list[dict]:
    lines = (run_dir / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_a_test_author_format_failure_repairs_only_that_role() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-format"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("test_author_format_failure")
        result, run_dir = pooled_run(source, outputs, run_id=run_id, leases=leases, state=state)

        require(result["crew_status"] == "review_ready", str(result["crew_status"]))
        require(result["attempts_used"] == 1, str(result["attempts_used"]))
        # The roles that already succeeded are not recomputed.
        for role in ("contract_locality_auditor", "implementer", "validator"):
            require(len(state.for_role(role)) == 1,
                    f"{role} was re-run for another role's format failure")
        # Only the failing role is retried, exactly once, in its own conversation.
        calls = state.for_role("test_author")
        require(len(calls) == 2, f"test_author: {len(calls)} invocations")
        require(calls[0]["session_id"] == calls[1]["session_id"] == leases["test_author"].session_id,
                f"the repair opened a second conversation: {calls}")
        require(calls[1]["mode"] == "resume", f"the repair restarted the conversation: {calls}")

        events = progress_events(run_dir)
        repairs = [item for item in events if item["event"] == "role_session_repair_started"]
        require(len(repairs) == 1, f"{len(repairs)} repair receipts")
        require(repairs[0]["role"] == "test_author"
                and repairs[0]["failure_classification"] == "provider_error"
                and repairs[0]["session_id"] == leases["test_author"].session_id,
                str(repairs[0]))
        confirmations = [item for item in events if item["event"] == "provider_session_confirmed"]
        require(len(confirmations) == 5, f"{len(confirmations)} confirmation receipts")
        checkouts = [item for item in events if item["event"] == "pooled_role_checked_out"]
        require({item["role"] for item in checkouts} == set(ROLE_CLASSES), str(checkouts))
        published = [item for item in events if item["event"] == "pooled_role_evidence_published"]
        require({item["role"] for item in published} == set(ROLE_CLASSES), str(published))
        require(all(item["reusable"] for item in published), str(published))

        # Every role, including the repaired one, still checks back in reusable.
        for role, lease in leases.items():
            returned = pool.check_in(
                lease=lease,
                result=DurableAssignmentResult.from_dict(result["durable_assignment_results"][role]),
                evidence_root=run_dir,
            )
            require(returned.state == "idle", f"{role}: {returned.state}")
        warm = all_leases(pool, head=head, checkout=checkout, run_id="nsc-005-format-2",
                          now=BASE + dt.timedelta(seconds=60))
        require(all(lease.mode == "resume" for lease in warm.values()), str(warm))
        require(warm["test_author"].session_id == leases["test_author"].session_id,
                "the repaired conversation was not the one offered back")


def test_an_unproven_identity_fails_precisely_without_restarting_earlier_roles() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-unproven"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("test_author_identity_unproven")
        blocked = rejects(
            lambda: pooled_run(source, outputs, run_id=run_id, leases=leases, state=state),
            CrewSessionIdentityUnproven,
        )
        message = str(blocked)
        require("test_author" in message, message)
        require(leases["test_author"].session_id in message, message)
        require("never confirmed" in message and "quarantined" in message, message)
        require("'provider_error'" in message, message)
        require("requested a provider session" not in message,
                f"the misleading generic message survived: {message}")
        # An unproven identity is never repaired in place: a fresh conversation
        # would lose the context and this run cannot prove which one the CLI made.
        require(len(state.for_role("test_author")) == 1, str(state.for_role("test_author")))
        for role in ("contract_locality_auditor", "implementer"):
            require(len(state.for_role(role)) == 1,
                    f"{role} was re-run for another role's unproven identity")
        require(not state.for_role("validator"), "the validator ran after a fail-closed stop")

        events = progress_events(outputs / run_id)
        unproven = [item for item in events
                    if item["event"] == "provider_session_identity_unproven"]
        require(len(unproven) == 1, f"{len(unproven)} quarantine receipts")
        require(unproven[0]["role"] == "test_author"
                and unproven[0]["status"] == "quarantined"
                and unproven[0]["session_mode"] == "start"
                and unproven[0]["requested_session_id"] == leases["test_author"].session_id
                and unproven[0]["lease_id"] == leases["test_author"].lease_id,
                str(unproven[0]))


def test_a_succeeding_role_without_a_confirmed_identity_still_fails_closed() -> None:
    """A clean exit is not identity. Exit code 0 proves nothing about the session."""

    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-silent"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("test_author_success_without_identity")
        blocked = rejects(
            lambda: pooled_run(source, outputs, run_id=run_id, leases=leases, state=state),
            CrewSessionIdentityUnproven,
        )
        message = str(blocked)
        require("'succeeded'" in message, message)
        require(leases["test_author"].session_id in message, message)
        # No durable evidence exists for an unproven role, so nothing it produced
        # can ever recycle its conversation.
        require(not (outputs / run_id / "role_results/test_author_1.json").exists(), message)
        require(len(state.for_role("test_author")) == 1, str(state.for_role("test_author")))
        require(len(state.for_role("implementer")) == 1, str(state.for_role("implementer")))


def test_lean_profile_invokes_only_required_pooled_roles() -> None:
    with tempfile.TemporaryDirectory(prefix="pooled-crew-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        head, checkout = source_identity(source)
        pool = new_pool()
        run_id = "nsc-005-lean-profile"
        leases = all_leases(pool, head=head, checkout=checkout, run_id=run_id)
        state = State("pass")
        result, _run_dir = pooled_run(
            source,
            outputs,
            run_id=run_id,
            leases=leases,
            state=state,
            crew_profile="lean",
            validation_profile="targeted",
        )
        require(result["crew_status"] == "review_ready", str(result))
        require(
            [item["role"] for item in state.invocations]
            == ["implementer", "validator"],
            str(state.invocations),
        )
        require(
            set(result["durable_assignment_results"])
            == {"implementer", "validator"},
            str(result["durable_assignment_results"]),
        )
        for role in ("contract_locality_auditor", "test_author"):
            record = result["pooled_role_leases"][role]
            require(record["invoked"] is False, str(record))
            require(record["durable_assignment_result"] is None, str(record))


TESTS = (
    test_full_run_refuses_a_lease_from_another_execution,
    test_a_lease_from_another_crew_protocol_is_refused,
    test_a_scope_rejected_implementer_is_never_reusable,
    test_failed_role_output_is_never_reusable,
    test_a_successful_roles_exact_artifact_checks_in_and_resumes,
    test_missing_or_tampered_role_evidence_cannot_check_in,
    test_early_contract_audit_termination_leaves_later_roles_unproven,
    test_a_repair_attempt_keeps_the_same_role_session,
    test_a_reused_session_receives_the_capsule_once,
    test_a_pooled_lease_requires_a_session_aware_provider,
    test_a_pooled_role_is_never_invoked_through_another_provider_or_model,
    test_a_nested_protocol_mismatch_is_refused_by_the_full_run,
    test_full_run_uses_external_manifest_bytes_as_cross_os_checkout_identity,
    test_a_test_author_format_failure_repairs_only_that_role,
    test_an_unproven_identity_fails_precisely_without_restarting_earlier_roles,
    test_a_succeeding_role_without_a_confirmed_identity_still_fails_closed,
    test_lean_profile_invokes_only_required_pooled_roles,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print("pooled_run_crew_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
