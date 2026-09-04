#!/usr/bin/env python3
"""Deterministic regressions for the ExecutionCrew prompt-context reduction.

Classification: in-memory/temporary-repository behavior tests. Every test drives
the real prompt builders, and most drive the real `run_crew`, against throwaway
Git repositories with a fake provider. No live provider, container, network
call, Unity invocation, or tracked repository file is involved.

The load-bearing claims are:

  * exactly one role prompt carries the full inline committed GDD, and it is the
    Contract Locality Auditor -- the only role that must make an exhaustive
    negative claim about canon (`missing_design`) before any diff exists to
    anchor a targeted read;
  * the aggregate fixed prompt now scales with the GDD payload exactly once
    rather than four times, which is what proves three payload copies were
    actually removed rather than merely relabelled;
  * every one of the four invocation requests still binds the exact committed
    GDD path in `context_paths`, and that path is the same constant the prompts
    name, so the file a role is told to read cannot drift from the file the
    invocation carries;
  * each role that lost the inline copy is told, unambiguously, to read the
    committed GDD at that path before making a canon-dependent claim, and is
    told that remembered or earlier-assignment GDD text is not canon;
  * a reused pooled session that already saw a different GDD receives no stale
    canon text and no inline canon text at all;
  * the auditor still fails closed on `missing_design` and on the other nonlocal
    classifications after its dependent-contract payload was reduced;
  * the reduced dependent payload keeps every requirement-bearing field verbatim
    and names the exact committed file for the fields it omits;
  * prompt construction is byte-identical across repeated runs.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True
# Throwaway repositories only: pin checkout conversion so a host autocrlf
# setting cannot change the bytes these fixtures commit or the byte counts the
# payload-scaling proof depends on.
os.environ["GIT_CONFIG_COUNT"] = "1"
os.environ["GIT_CONFIG_KEY_0"] = "core.autocrlf"
os.environ["GIT_CONFIG_VALUE_0"] = "false"

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.AgentRuntime.config import RuntimeConfiguration  # noqa: E402
from Pipeline.AgentRuntime.contracts import Usage  # noqa: E402
from Pipeline.AgentRuntime.providers.base import ProviderInvocationResponse  # noqa: E402
from Pipeline.ExecutionCrew import run_crew as run_crew_module  # noqa: E402
from Pipeline.ExecutionCrew.contract_locality import (  # noqa: E402
    DEPENDENT_CONTRACT_OMITTED_FIELDS,
    ContractLocalityError,
    auditor_dependent_contract_payload,
    build_task_catalog,
    direct_dependency_contracts,
    direct_dependent_contracts,
    validate_locality_audit_output,
)
from Pipeline.ExecutionCrew.prompts import (  # noqa: E402
    COMMITTED_GDD_PATH,
    contract_locality_auditor_prompt,
    implementer_prompt,
    test_author_prompt,
    validator_prompt,
)
from Pipeline.ExecutionCrew.run_crew import run_crew  # noqa: E402
from Pipeline.ExecutionCrew.session_pool import (  # noqa: E402
    CREW_SESSION_PROTOCOL_VERSION,
    DurableAssignmentResult,
    SessionCompatibility,
    SessionPool,
)

TASK = "NSC-005"
DEPENDENCY_TASK = "NSC-002"
DEPENDENT_TASK = "NSC-010"
IMPL = "Assets/Scripts/PlayerMana.cs"
TEST = "Assets/Tests/PlayerManaTests.cs"
MODEL = "context-reduction-model"
REPOSITORY = "https://github.com/cathode26/NoSafeCircle.git"
ROLES = ("contract_locality_auditor", "implementer", "test_author", "validator")
INLINE_GDD_ROLE = "contract_locality_auditor"
NO_INLINE_GDD_ROLES = tuple(role for role in ROLES if role != INLINE_GDD_ROLE)
ROLE_CLASSES = {
    "contract_locality_auditor": "high_reasoning",
    "implementer": "standard",
    "test_author": "low_cost",
    "validator": "high_reasoning",
}

# A distinctive line that exists only inside the committed GDD payload. A prompt
# holding this string is holding the GDD body itself, not a reference to it.
GDD_SENTINEL = "FULL_ROLE_PROMPT_SENTINEL_SECRET"
STALE_GDD_SENTINEL = "STALE_POOLED_ASSIGNMENT_GDD_SENTINEL"

# Sentinels planted in the dependent contract's requirement-bearing fields. Each
# one must survive the payload reduction verbatim, because a locality decision
# can turn on any of them.
DEPENDENT_CRITERION_SENTINEL = "DEPENDENT_ACCEPTANCE_REQUIREMENT_SENTINEL"
DEPENDENT_GATE_SENTINEL = "DEPENDENT_COMPLETION_GATE_SENTINEL"
DEPENDENT_NOTES_SENTINEL = "DEPENDENT_OWNERSHIP_NOTES_SENTINEL"
DEPENDENT_OBLIGATION_SENTINEL = "DEPENDENT_DOWNSTREAM_OBLIGATION_SENTINEL"
DEPENDENT_RESOURCE_SENTINEL = "Assets/Scripts/DependentExclusiveResourceSentinel.cs"
DEPENDENT_EXECUTION_REASON_SENTINEL = "DEPENDENT_EXECUTION_REASON_SENTINEL"
DEPENDENT_DECOMPOSITION_REASON_SENTINEL = "DEPENDENT_DECOMPOSITION_REASON_SENTINEL"

# Sentinels planted in the fields the reduction omits. None may appear in the
# auditor prompt afterwards; each must be listed under `omitted_fields`.
DEPENDENT_PROVENANCE_SENTINEL = "DEPENDENT_PROVENANCE_METADATA_SENTINEL"
DEPENDENT_GDD_EVIDENCE_SENTINEL = "DEPENDENT_GDD_EVIDENCE_EXCERPT_SENTINEL"
DEPENDENT_BOOTSTRAP_SENTINEL = "DEPENDENT_BOOTSTRAP_OBSERVATION_SENTINEL"

# Sentinels the dependency contract carries. Dependency contracts are the most
# locality-critical context the auditor has and are deliberately not reduced.
DEPENDENCY_CRITERION_SENTINEL = "DEPENDENCY_ACCEPTANCE_REQUIREMENT_SENTINEL"
DEPENDENCY_PROVENANCE_SENTINEL = "DEPENDENCY_PROVENANCE_METADATA_SENTINEL"

FAILURES: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def cmd(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args), check=True, stdout=subprocess.PIPE, text=True
    ).stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def gdd_text(sentinel: str = GDD_SENTINEL, *, padding: int = 0) -> str:
    """A committed GDD body large enough that an inline copy is unmistakable."""
    body = f"# GDD\n{sentinel}\nApproved behavior for the fixture.\n"
    if padding:
        body += ("P" * padding) + "\n"
    return body


# --------------------------------------------------------------- fixtures


def root_task() -> dict:
    return {
        "schema_version": "2.0", "id": "NSC-001", "contract_revision": 1,
        "contract_disposition": "active", "title": "No Safe Circle",
        "reconciliation_key": "no-safe-circle", "kind": "feature",
        "execution_scope": "not_applicable", "execution_reason": "Project root.",
        "decomposition_state": "needs_decomposition", "decomposition_reason": "Project root.",
        "parent": "", "depends_on": [], "exclusive_resources": [],
        "acceptance_criteria": [], "completion_gates": [],
        "downstream_integration_obligations": [], "provenance": {"origin": "fixture"},
    }


def dependency_task() -> dict:
    """A task NSC-005 declares as a dependency; its contract is never reduced."""
    return {
        "schema_version": "2.0", "id": DEPENDENCY_TASK, "contract_revision": 2,
        "contract_disposition": "active", "title": "Shared Mana Pool",
        "reconciliation_key": "shared-mana-pool", "kind": "implementation",
        "execution_scope": "single_agent",
        "execution_reason": "Bounded fixture component owning the shared pool.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Fixture requires no missing design.",
        "parent": "NSC-001", "depends_on": [], "exclusive_resources": [],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "fixture",
             "requirement": DEPENDENCY_CRITERION_SENTINEL}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "fixture",
             "requirement": "Shared pool behavior is verified."}
        ],
        "downstream_integration_obligations": [],
        "provenance": {"origin": DEPENDENCY_PROVENANCE_SENTINEL},
    }


def selected_task() -> dict:
    return {
        "schema_version": "2.0", "id": TASK, "contract_revision": 3,
        "contract_disposition": "active", "title": "Mana",
        "reconciliation_key": "player-mana", "kind": "implementation",
        "execution_scope": "single_agent",
        "execution_reason": "Bounded fixture component that owns its own mana state.",
        "decomposition_state": "concrete",
        "decomposition_reason": "Fixture requires no missing design.",
        "parent": "NSC-001", "depends_on": [DEPENDENCY_TASK], "exclusive_resources": [],
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


def dependent_task() -> dict:
    """A task declaring a dependency on NSC-005, carrying both a full set of
    requirement-bearing fields and a full set of the fields the reduction omits."""
    return {
        "schema_version": "2.0", "id": DEPENDENT_TASK, "contract_revision": 4,
        "contract_disposition": "active", "title": "Mana Consumer",
        "reconciliation_key": "mana-consumer", "kind": "implementation",
        "execution_scope": "single_agent",
        "execution_reason": DEPENDENT_EXECUTION_REASON_SENTINEL,
        "decomposition_state": "concrete",
        "decomposition_reason": DEPENDENT_DECOMPOSITION_REASON_SENTINEL,
        "parent": "NSC-001", "depends_on": [TASK],
        "exclusive_resources": [f"repo-file:{DEPENDENT_RESOURCE_SENTINEL}"],
        "acceptance_criteria": [
            {"criterion_id": "AC-001", "reference": "fixture",
             "requirement": DEPENDENT_CRITERION_SENTINEL}
        ],
        "completion_gates": [
            {"gate_id": "VAL-001", "reference": "fixture",
             "requirement": DEPENDENT_GATE_SENTINEL}
        ],
        "downstream_integration_obligations": [
            {"obligation_id": "INT-001", "reference": "fixture",
             "requirement": DEPENDENT_OBLIGATION_SENTINEL}
        ],
        "notes": DEPENDENT_NOTES_SENTINEL,
        "provenance": {"origin": DEPENDENT_PROVENANCE_SENTINEL},
        "gdd_evidence": [
            {"reference": "Section 1", "requirement": DEPENDENT_GDD_EVIDENCE_SENTINEL}
        ],
        "repository_evidence_at_bootstrap": [
            {"path": IMPL, "evidence_type": "code", "observation": DEPENDENT_BOOTSTRAP_SENTINEL}
        ],
        "repository_state_at_bootstrap": "missing",
    }


def all_tasks() -> list[dict]:
    return [root_task(), dependency_task(), selected_task(), dependent_task()]


def fixture(parent: Path, *, sentinel: str = GDD_SENTINEL, directory_name: str = "source") -> Path:
    """One throwaway source checkout with a valid persistent work graph."""
    root = parent / directory_name
    root.mkdir()
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    cmd(root, "config", "user.name", "Prompt Context Smoke")
    cmd(root, "config", "user.email", "prompt-context@example.invalid")
    cmd(root, "remote", "add", "origin", REPOSITORY)
    write(root / IMPL, "public class PlayerMana { }\n")
    write(root / TEST, "public class PlayerManaTests { }\n")
    tasks = all_tasks()
    for task in tasks:
        write(root / f"Tasks/{task['id']}.yaml", json.dumps(task) + "\n")
    write(
        root / "Pipeline/TaskGraph/WORK_ID_MAP.json",
        json.dumps({"id_map": {t["reconciliation_key"]: t["id"] for t in tasks}}) + "\n",
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
    write(root / COMMITTED_GDD_PATH, gdd_text(sentinel))
    write(root / "Docs/Engineering/UNITY_TESTING_POLICY.md",
          "# Policy\nNever claim tests passed.\n")
    write(root / "Docs/Engineering/ENGINEERING_STANDARDS.md",
          "# Engineering Standards\n## Reuse and tool selection\n"
          "Search before creating parallel infrastructure.\n")
    cmd(root, "add", ".")
    cmd(root, "commit", "-qm", "baseline")
    return root


# ------------------------------------------------------------ fake provider


class State:
    """Records the exact AgentInvocationRequest every role actually received."""

    def __init__(self, *, audit: str = "pass", feedback: str | None = None) -> None:
        self.audit = audit
        self.feedback = feedback
        self.requests: list = []

    def by_role(self, role: str) -> list:
        return [r for r in self.requests if r.role == role]

    def first(self, role: str):
        matches = self.by_role(role)
        require(matches, f"{role} was never invoked")
        return matches[0]


def _audit_output(state: State) -> dict:
    def local(entry_id: str, entry_type: str) -> dict:
        return {"id": entry_id, "entry_type": entry_type, "classification": "local_to_task",
                "evidence": "owned locally by this task", "related_task_ids": [],
                "recommended_action": "keep"}

    entries = [local("AC-001", "acceptance_criterion"), local("VAL-001", "completion_gate")]
    blocking: list[dict] = []
    status = "pass"
    if state.audit == "missing_design":
        entries[0] = {
            "id": "AC-001", "entry_type": "acceptance_criterion", "classification": "missing_design",
            "evidence": "the committed GDD does not authorize the required behavior",
            "related_task_ids": [], "recommended_action": "clarify_design",
        }
        blocking = [{"entry_id": "AC-001", "reason_code": "missing_design",
                     "issue": "committed canon lacks the approved design authority",
                     "recommended_action": "clarify_design", "related_task_ids": []}]
        status = "contract_review_required"
    elif state.audit == "requires_declared_dependency":
        entries[1] = {
            "id": "VAL-001", "entry_type": "completion_gate",
            "classification": "requires_declared_dependency",
            "evidence": "needs the dependent task's already-integrated behavior",
            "related_task_ids": [DEPENDENT_TASK], "recommended_action": "add_dependency",
        }
        blocking = [{"entry_id": "VAL-001", "reason_code": "requires_declared_dependency",
                     "issue": "needs a declared dependency", "recommended_action": "add_dependency",
                     "related_task_ids": [DEPENDENT_TASK]}]
        status = "contract_review_required"
    return {"status": status, "summary": "locality audit", "entry_results": entries,
            "blocking_findings": blocking, "files_reviewed": [IMPL, TEST]}


class FakeProvider:
    provider_identifier = "fake"

    def __init__(self, state: State, repo: Path, writable: bool, role: str,
                 session=None, session_ledger=None) -> None:
        self.state = state
        self.repo = repo
        self.writable = writable
        self.role = role
        self.session = session
        self.session_ledger = session_ledger

    @staticmethod
    def reviewing(request) -> bool:
        return "HUMAN REVIEW REJECTION FROM PRIOR REVIEW-READY CANDIDATE" in request.prompt

    def invoke(self, request, model):
        self.state.requests.append(request)
        if self.session is not None:
            observed = self.session.session_id or (
                f"beef0000-1111-4111-8111-{len(self.state.requests):012x}")
            self.session_ledger.record(self.session.confirm(observed))
        if self.role == "contract_locality_auditor":
            output = _audit_output(self.state)
        elif self.role == "implementer":
            # A human-review retry seeds the clone with the rejected candidate, so
            # the corrected candidate must actually differ from it.
            corrected = " public int ManaBarPixels;" if self.reviewing(request) else ""
            write(self.repo / IMPL,
                  "public class PlayerMana { public int Mana;" + corrected + " }\n")
            output = {"summary": "implemented", "claimed_changed_paths": [IMPL],
                      "blockers": [], "notes": []}
        elif self.role == "test_author":
            corrected = (" public void HumanReviewRegression() {}"
                         if self.reviewing(request) else "")
            write(self.repo / TEST,
                  "public class PlayerManaTests { public void ManaTest() {}"
                  + corrected + " }\n")
            output = {"summary": "tests", "claimed_changed_paths": [TEST],
                      "test_cases_added_or_updated": ["ManaTest"], "blockers": [],
                      "known_limitations": ["not run"], "proposed_unity_test_scope": "Play Mode"}
        else:
            output = {"status": "pass", "summary": "reviewed", "criteria_results": [
                {"id": "AC-001", "status": "pass", "reason_code": "proved", "evidence": "source review"},
                {"id": "VAL-001", "status": "not_proven", "reason_code": "runtime_not_executed",
                 "evidence": "Unity was not run"}],
                "blocking_issues": [], "risks": [], "files_reviewed": [IMPL, TEST]}
        return ProviderInvocationResponse(output, "fake log\n", (), Usage(1, 2, 3), True, ())


def factory(state: State, *, provider_identity: str = "fake"):
    def create(provider, repo, writable, role, session=None, session_ledger=None):
        key = f"{provider}-crew"
        config = RuntimeConfiguration({
            key: {"provider": provider_identity,
                  "models": {"low_cost": MODEL, "standard": MODEL, "high_reasoning": MODEL}}
        })
        fake = FakeProvider(state, repo, writable, role, session, session_ledger)
        fake.provider_identifier = provider_identity
        return key, config, {provider_identity: fake}
    return create


def execute(source: Path, outputs: Path, *, run_id: str, state: State, leases=None,
            provider: str = "claude", provider_identity: str = "fake", **extra):
    """Run the real crew quietly; role prompts are captured through `state`."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return run_crew(
            source=source, output_root=outputs, task_id=TASK, provider_name=provider,
            implementation_paths=(IMPL,), test_paths=(TEST,), run_id=run_id,
            execution_model=MODEL, provider_factory=factory(state, provider_identity=provider_identity),
            _require_physical_read_only_source=False, role_session_leases=leases, **extra,
        )


# ------------------------------------------------- 1: exactly one inline GDD


def test_exactly_one_role_prompt_carries_the_inline_committed_gdd() -> None:
    """Before this change every one of the four prompts embedded the whole GDD.

    The auditor is the role that keeps it: it is the only role required to make
    an exhaustive negative claim about canon (`missing_design`), and the only
    one that runs before any diff, patch, or changed-path set exists to scope a
    targeted read.
    """
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State()
        result = execute(source, parent / "outputs", run_id="inline-gdd", state=state)
        require(result["crew_status"] == "review_ready",
                f"unexpected status {result['crew_status']}")

        gdd = (source / COMMITTED_GDD_PATH).read_text(encoding="utf-8")
        carrying = [role for role in ROLES if gdd in state.first(role).prompt]
        require(carrying == [INLINE_GDD_ROLE],
                f"expected only {INLINE_GDD_ROLE} to inline the GDD; got {carrying}")

        for role in NO_INLINE_GDD_ROLES:
            prompt = state.first(role).prompt
            require(GDD_SENTINEL not in prompt,
                    f"{role} still carries GDD body text")
        require(GDD_SENTINEL in state.first(INLINE_GDD_ROLE).prompt,
                "the auditor lost its inline GDD")


# ------------------------------------- 2: context_paths still bind the GDD


def test_every_invocation_still_binds_the_exact_committed_gdd_path() -> None:
    """Removing the inline copy must not remove the role's access to the file."""
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State()
        execute(source, parent / "outputs", run_id="context-paths", state=state)

        require(run_crew_module.GDD_PATH == COMMITTED_GDD_PATH,
                "run_crew and the prompts disagree about the committed GDD path")
        require((source / COMMITTED_GDD_PATH).is_file(),
                "the committed GDD path does not name a real committed file")
        for role in ROLES:
            for request in state.by_role(role):
                require(COMMITTED_GDD_PATH in request.context_paths,
                        f"{role} lost the committed GDD path from context_paths")
                require("repository_read" in request.allowed_capabilities,
                        f"{role} cannot read the committed GDD it is told to read")


# ------------------------------- 3: explicit committed-path read instruction


def test_roles_without_the_inline_gdd_are_told_to_read_the_committed_file() -> None:
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State()
        execute(source, parent / "outputs", run_id="read-instruction", state=state)

        required_fragments = (
            "COMMITTED CANONICAL GDD - READ IT; IT IS NOT INLINED IN THIS PROMPT",
            COMMITTED_GDD_PATH,
            "at the exact source commit this assignment names",
            "bound to this invocation in context_paths",
            "read the relevant committed sections",
            "Remembered GDD text, GDD text from an earlier assignment or conversation",
            "report it as missing or ambiguous design",
        )
        for role in NO_INLINE_GDD_ROLES:
            prompt = state.first(role).prompt
            for fragment in required_fragments:
                require(fragment in prompt, f"{role} prompt is missing: {fragment!r}")


# ------------------------- 4: pooled reuse substitutes no stale canon text


def test_a_reused_pooled_session_receives_no_stale_or_inline_canon() -> None:
    """The same conversation, a second assignment, and a changed committed GDD.

    A resumed session must not be able to fall back on the GDD it saw before,
    so the second assignment's reduced prompts must contain neither the old nor
    the new GDD body -- only the instruction to read the current committed file.
    """
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent, sentinel=STALE_GDD_SENTINEL)
        outputs = parent / "outputs"
        head_one = cmd(source, "rev-parse", "HEAD")
        checkout = str(Path(cmd(source, "rev-parse", "--show-toplevel")).resolve())

        pool = SessionPool()
        first_state = State()
        leases_one = {
            role: pool.checkout(
                compatibility=SessionCompatibility(
                    "claude-code", MODEL, None, role, ROLE_CLASSES[role], REPOSITORY,
                    CREW_SESSION_PROTOCOL_VERSION, "worker"),
                worker_slot_id="worker-slot-1", task_id=TASK, worker_run_id="pooled-one",
                source_commit=head_one, checkout_identity=checkout)
            for role in ROLES
        }
        first = execute(source, outputs, run_id="pooled-one", state=first_state,
                        leases=leases_one, provider="claude",
                        provider_identity="claude-code",
                        scheduler_repository_identity=REPOSITORY)
        require(first["crew_status"] == "review_ready", str(first["crew_status"]))
        require(STALE_GDD_SENTINEL in first_state.first(INLINE_GDD_ROLE).prompt,
                "the first assignment never saw the original GDD")
        # Return every proven conversation so the second assignment really
        # resumes the same session rather than starting a cold one.
        for role, lease in leases_one.items():
            evidence = DurableAssignmentResult.from_dict(
                first["durable_assignment_results"][role])
            require(evidence.is_reusable, f"{role}: {evidence.assignment_outcome}")
            pool.check_in(lease=lease, result=evidence, evidence_root=outputs / "pooled-one")

        # The committed canon moves under the pooled conversation.
        write(source / COMMITTED_GDD_PATH, gdd_text(GDD_SENTINEL))
        cmd(source, "add", "--", COMMITTED_GDD_PATH)
        cmd(source, "commit", "-qm", "canon moved")
        head_two = cmd(source, "rev-parse", "HEAD")
        require(head_two != head_one, "the fixture did not actually move the committed GDD")

        second_state = State()
        leases_two = {
            role: pool.checkout(
                compatibility=SessionCompatibility(
                    "claude-code", MODEL, None, role, ROLE_CLASSES[role], REPOSITORY,
                    CREW_SESSION_PROTOCOL_VERSION, "worker"),
                worker_slot_id="worker-slot-1", task_id=TASK, worker_run_id="pooled-two",
                source_commit=head_two, checkout_identity=checkout)
            for role in ROLES
        }
        for role, lease in leases_two.items():
            require(lease.mode == "resume",
                    f"{role} did not resume the pooled conversation")
        execute(source, outputs, run_id="pooled-two", state=second_state, leases=leases_two,
                provider="claude", provider_identity="claude-code",
                scheduler_repository_identity=REPOSITORY)

        for role in NO_INLINE_GDD_ROLES:
            prompt = second_state.first(role).prompt
            require(STALE_GDD_SENTINEL not in prompt,
                    f"{role} carried the previous assignment's GDD text")
            require(GDD_SENTINEL not in prompt, f"{role} inlined the current GDD text")
            require("COMMITTED CANONICAL GDD - READ IT; IT IS NOT INLINED IN THIS PROMPT" in prompt,
                    f"{role} lost the committed-GDD read instruction on a pooled assignment")
            require("has expired and no longer applies" in prompt,
                    f"{role} lost the pooled assignment capsule")
            require(f"Current source commit: {head_two}" in prompt,
                    f"{role} was not bound to the current source commit")

        auditor = second_state.first(INLINE_GDD_ROLE).prompt
        require(GDD_SENTINEL in auditor, "the auditor did not receive the current canon")
        require(STALE_GDD_SENTINEL not in auditor,
                "the auditor received the previous assignment's canon")


# ------------------------------ 5: the auditor still fails closed, reduced


def test_the_auditor_still_fails_closed_on_missing_design() -> None:
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State(audit="missing_design")
        result = execute(source, parent / "outputs", run_id="missing-design", state=state)
        require(result["crew_status"] == "contract_review_required",
                f"missing_design did not stop the crew: {result['crew_status']}")
        require(result["attempts_used"] == 0, "writers ran after a nonlocal audit")
        for role in ("implementer", "test_author", "validator"):
            require(not state.by_role(role), f"{role} ran after a nonlocal audit")


def test_the_auditor_still_fails_closed_on_a_missing_declared_dependency() -> None:
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State(audit="requires_declared_dependency")
        result = execute(source, parent / "outputs", run_id="needs-dependency", state=state)
        require(result["crew_status"] == "contract_review_required",
                f"requires_declared_dependency did not stop the crew: {result['crew_status']}")
        require(not state.by_role("implementer"), "the Implementer ran after a nonlocal audit")


def test_deterministic_locality_validation_is_unchanged() -> None:
    """The output checks that make a nonlocal audit stick are untouched."""
    task = selected_task()
    valid = frozenset({TASK, DEPENDENCY_TASK, DEPENDENT_TASK})

    clean = {"status": "contract_review_required", "summary": "s", "files_reviewed": [],
             "entry_results": [
                 {"id": "AC-001", "entry_type": "acceptance_criterion",
                  "classification": "missing_design", "evidence": "e",
                  "related_task_ids": [], "recommended_action": "clarify_design"},
                 {"id": "VAL-001", "entry_type": "completion_gate",
                  "classification": "local_to_task", "evidence": "e",
                  "related_task_ids": [], "recommended_action": "keep"}],
             "blocking_findings": [
                 {"entry_id": "AC-001", "reason_code": "missing_design", "issue": "i",
                  "recommended_action": "clarify_design", "related_task_ids": []}]}
    require(validate_locality_audit_output(clean, task=task, valid_task_ids=valid) == [],
            "a well-formed missing_design audit was rejected")

    unpaired = json.loads(json.dumps(clean))
    unpaired["blocking_findings"] = []
    require(validate_locality_audit_output(unpaired, task=task, valid_task_ids=valid),
            "a missing_design entry without a blocking finding was accepted")

    empty_related = json.loads(json.dumps(clean))
    empty_related["entry_results"][0].update(
        classification="requires_declared_dependency", recommended_action="add_dependency")
    empty_related["blocking_findings"][0].update(
        reason_code="requires_declared_dependency", recommended_action="add_dependency")
    require(validate_locality_audit_output(empty_related, task=task, valid_task_ids=valid),
            "requires_declared_dependency with empty related_task_ids was accepted")


# --------------------- 6: the reduced dependent payload keeps what matters


def test_the_reduced_dependent_payload_keeps_every_requirement_field() -> None:
    tasks_by_id = {task["id"]: task for task in all_tasks()}
    raw = direct_dependent_contracts(TASK, tasks_by_id)
    require(set(raw) == {DEPENDENT_TASK}, f"unexpected dependents: {sorted(raw)}")
    payload = auditor_dependent_contract_payload(raw)
    entry = payload[DEPENDENT_TASK]

    for field in ("id", "title", "depends_on", "acceptance_criteria", "completion_gates",
                  "downstream_integration_obligations", "notes", "exclusive_resources",
                  "contract_disposition", "execution_reason", "decomposition_reason"):
        require(field in entry, f"the reduced payload dropped requirement field {field!r}")
        require(entry[field] == raw[DEPENDENT_TASK][field],
                f"{field!r} was not preserved verbatim")

    for field in DEPENDENT_CONTRACT_OMITTED_FIELDS:
        require(field not in entry, f"{field!r} was expected to be omitted")
    require(entry["omitted_fields"]
            == sorted(set(raw[DEPENDENT_TASK]) & DEPENDENT_CONTRACT_OMITTED_FIELDS),
            "omitted_fields does not enumerate exactly what was omitted")
    require(entry["committed_contract_path"] == f"Tasks/{DEPENDENT_TASK}.yaml",
            "the reduced payload does not name the exact committed contract file")

    # An unclassified field is retained, so a future schema addition cannot be
    # dropped from the audit silently.
    extended = json.loads(json.dumps(raw))
    extended[DEPENDENT_TASK]["a_future_requirement_field"] = "FUTURE_FIELD_SENTINEL"
    require(auditor_dependent_contract_payload(extended)[DEPENDENT_TASK]
            ["a_future_requirement_field"] == "FUTURE_FIELD_SENTINEL",
            "an unclassified contract field was dropped")

    # A contract that already used a synthesized name fails closed.
    colliding = json.loads(json.dumps(raw))
    colliding[DEPENDENT_TASK]["omitted_fields"] = ["not-pipeline-metadata"]
    try:
        auditor_dependent_contract_payload(colliding)
    except ContractLocalityError:
        pass
    else:
        raise AssertionError("a reserved-field collision was silently accepted")


def test_the_auditor_prompt_still_carries_the_locality_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        state = State()
        execute(source, parent / "outputs", run_id="locality-evidence", state=state)
        prompt = state.first(INLINE_GDD_ROLE).prompt

        for sentinel in (DEPENDENT_CRITERION_SENTINEL, DEPENDENT_GATE_SENTINEL,
                         DEPENDENT_NOTES_SENTINEL, DEPENDENT_OBLIGATION_SENTINEL,
                         DEPENDENT_RESOURCE_SENTINEL, DEPENDENT_EXECUTION_REASON_SENTINEL,
                         DEPENDENT_DECOMPOSITION_REASON_SENTINEL):
            require(sentinel in prompt, f"the auditor lost dependent evidence: {sentinel}")
        for sentinel in (DEPENDENT_PROVENANCE_SENTINEL, DEPENDENT_GDD_EVIDENCE_SENTINEL,
                         DEPENDENT_BOOTSTRAP_SENTINEL):
            require(sentinel not in prompt, f"redundant dependent data survived: {sentinel}")

        # Dependency contracts are the most locality-critical context there is
        # and are deliberately not reduced at all.
        for sentinel in (DEPENDENCY_CRITERION_SENTINEL, DEPENDENCY_PROVENANCE_SENTINEL):
            require(sentinel in prompt, f"a dependency contract was reduced: {sentinel}")

        require(f"Tasks/{DEPENDENT_TASK}.yaml" in prompt,
                "the auditor was not given the on-demand committed contract path")
        require("Never treat an omitted field as absent from the committed contract" in prompt,
                "the auditor was not told how to read an omitted dependent field")
        require((source / f"Tasks/{DEPENDENT_TASK}.yaml").is_file(),
                "the on-demand contract path does not name a real committed file")
        require(DEPENDENT_TASK in prompt and TASK in prompt,
                "the auditor lost the dependency edge under review")


# ------------------------- 7: everything else each role needs is still there


def test_each_role_still_receives_its_required_context() -> None:
    feedback_text = "HUMAN_REVIEW_FEEDBACK_SENTINEL: mana bar is invisible.\n"
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        state = State()
        first = execute(source, outputs, run_id="context-first", state=state)
        require(first["crew_status"] == "review_ready",
                f"unexpected status {first['crew_status']}")

        contract = (source / f"Tasks/{TASK}.yaml").read_text(encoding="utf-8")
        policy = (source / "Docs/Engineering/UNITY_TESTING_POLICY.md").read_text(encoding="utf-8")

        auditor = state.first("contract_locality_auditor").prompt
        require(contract in auditor, "the auditor lost the exact committed task contract")
        require("DETERMINISTIC TASK CATALOG" in auditor, "the auditor lost the task catalog")
        require("QUESTION YOU MUST ANSWER" in auditor, "the auditor lost its question")
        require("You have no write authority" in auditor, "the auditor gained write authority")

        implementer = state.first("implementer").prompt
        require(contract in implementer, "the Implementer lost the exact committed task contract")
        require("ENGINEERING REUSE / TOOL SELECTION" in implementer,
                "the Implementer lost engineering guidance")
        require("EXISTING TRACKED FILES YOU MAY EDIT" in implementer
                and IMPL in implementer, "the Implementer lost its write boundary")
        require("Test Author-owned work is not an Implementer blocker" in implementer,
                "the Implementer lost its blocker policy")

        test_author = state.first("test_author").prompt
        require(contract in test_author, "the Test Author lost the exact committed task contract")
        require(policy in test_author, "the Test Author lost the committed Unity testing policy")
        require("EXACT DETERMINISTIC IMPLEMENTATION DIFF" in test_author
                and "public int Mana" in test_author,
                "the Test Author lost the implementation diff")
        require("ENGINEERING REUSE / TOOL SELECTION" in test_author,
                "the Test Author lost engineering guidance")

        validator = state.first("validator").prompt
        require(contract in validator, "the Validator lost the exact committed task contract")
        require("EXACT FULL CANDIDATE GIT PATCH" in validator
                and "public class PlayerManaTests" in validator,
                "the Validator lost the candidate patch")
        require("EXACT DETERMINISTIC ACTUAL CHANGED PATHS" in validator,
                "the Validator lost the deterministic changed paths")
        require("IMPLEMENTER STRUCTURED OUTPUT" in validator
                and "TEST AUTHOR STRUCTURED OUTPUT" in validator,
                "the Validator lost the writer role outputs")
        require("ENGINEERING REUSE / TOOL SELECTION" in validator,
                "the Validator lost engineering guidance")

        # Human-review feedback still reaches exactly the roles it always did.
        # The feedback file must resolve strictly underneath the output root.
        feedback_file = outputs / "human-review" / "feedback.md"
        feedback_file.parent.mkdir(parents=True, exist_ok=True)
        feedback_file.write_bytes(feedback_text.encode("utf-8"))
        retry_state = State()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            retry = run_crew(
                source=source, output_root=outputs, run_id="context-retry",
                retry_run_id="context-first", review_feedback_file=feedback_file,
                provider_factory=factory(retry_state), _require_physical_read_only_source=False,
            )
        require(retry["crew_status"] == "review_ready",
                f"unexpected retry status {retry['crew_status']}")
        for role in ("implementer", "test_author", "validator"):
            prompt = retry_state.first(role).prompt
            require(feedback_text in prompt, f"{role} lost the human-review feedback")
            require("HUMAN REVIEW REJECTION FROM PRIOR REVIEW-READY CANDIDATE" in prompt,
                    f"{role} lost the human-review header")
        require(feedback_text not in retry_state.first(INLINE_GDD_ROLE).prompt,
                "human-review feedback leaked into the auditor prompt")


# --------------------------------------------------- 8: determinism of bytes


def test_prompt_construction_is_byte_identical_across_repeated_runs() -> None:
    with tempfile.TemporaryDirectory(prefix="prompt-context-") as text:
        parent = Path(text)
        source = fixture(parent)
        outputs = parent / "outputs"
        captured = []
        for index in (1, 2):
            state = State()
            execute(source, outputs, run_id=f"determinism-{index}", state=state)
            captured.append({role: state.first(role).prompt for role in ROLES})
        for role in ROLES:
            require(captured[0][role].encode("utf-8") == captured[1][role].encode("utf-8"),
                    f"{role} prompt is not deterministic across runs")


# ------------------- 9: the payload-scaling proof and the exact byte counts


def _fixed_prompts(gdd: str) -> dict[str, str]:
    """The four fixed role prompts for one committed GDD payload.

    Every input except the GDD body is a fixed literal, so the only thing that
    can move a byte count between two calls is the payload itself.
    """
    tasks_by_id = {task["id"]: task for task in all_tasks()}
    task = tasks_by_id[TASK]
    contract = json.dumps(task, indent=2)
    policy = "# Policy\nNever claim tests passed.\n"
    patch = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
    return {
        "contract_locality_auditor": contract_locality_auditor_prompt(
            task_id=TASK, title=task["title"], task_contract=contract, gdd=gdd,
            execution_scope=task["execution_scope"], execution_reason=task["execution_reason"],
            decomposition_state=task["decomposition_state"],
            decomposition_reason=task["decomposition_reason"],
            dependency_contracts=direct_dependency_contracts(task, tasks_by_id),
            dependent_contracts=auditor_dependent_contract_payload(
                direct_dependent_contracts(TASK, tasks_by_id)),
            task_catalog=build_task_catalog(tasks_by_id),
            source_head="a" * 40, source_tree="b" * 40),
        "implementer": implementer_prompt(
            task_id=TASK, title=task["title"], task_contract=contract,
            implementation_paths=(IMPL,), new_implementation_paths=(),
            pipeline_sidecars=(), other_role_paths=(TEST,)),
        "test_author": test_author_prompt(
            task_id=TASK, title=task["title"], task_contract=contract, policy=policy,
            implementation_patch=patch, implementation_paths=(IMPL,),
            implementation_actual_paths=(IMPL,), test_paths=(TEST,), new_test_paths=(),
            pipeline_sidecars=()),
        "validator": validator_prompt(
            task_id=TASK, title=task["title"], task_contract=contract, candidate_patch=patch,
            changed_paths=(IMPL, TEST),
            implementer_output={"summary": "implemented", "blockers": []},
            test_author_output={"summary": "tests", "blockers": []}),
    }


def test_the_aggregate_prompt_scales_with_the_gdd_payload_exactly_once() -> None:
    """The threshold-free proof that three payload copies were actually removed.

    Growing the committed GDD by N bytes must grow the aggregate fixed prompt by
    exactly N. Before this change it grew by 4N, because all four prompts
    embedded the payload. The assertion therefore cannot be satisfied by
    shortening prose; only by removing three copies of the payload itself.
    """
    padding = 50_000
    small = gdd_text()
    large = gdd_text(padding=padding)
    require(len(large.encode("utf-8")) - len(small.encode("utf-8")) == padding + 1,
            "the padded fixture did not grow by the expected payload size")
    payload_delta = padding + 1

    before = _fixed_prompts(small)
    after = _fixed_prompts(large)
    aggregate_before = sum(len(p.encode("utf-8")) for p in before.values())
    aggregate_after = sum(len(p.encode("utf-8")) for p in after.values())
    require(aggregate_after - aggregate_before == payload_delta,
            "the aggregate fixed prompt does not carry the GDD payload exactly once: "
            f"delta {aggregate_after - aggregate_before} for a {payload_delta}-byte payload change")

    copies_removed = 0
    for role in ROLES:
        role_delta = len(after[role].encode("utf-8")) - len(before[role].encode("utf-8"))
        if role == INLINE_GDD_ROLE:
            require(role_delta == payload_delta,
                    f"{role} does not carry exactly one GDD payload copy")
        else:
            require(role_delta == 0, f"{role} still scales with the GDD payload")
            copies_removed += 1
    require(copies_removed == 3, f"expected three removed payload copies, proved {copies_removed}")


def test_the_measured_fixed_prompt_bytes_drop_materially() -> None:
    """Exact UTF-8 byte counts on the deterministic fixture, reported not guessed."""
    gdd = gdd_text(padding=80_000)
    gdd_bytes = len(gdd.encode("utf-8"))
    prompts = _fixed_prompts(gdd)
    counts = {role: len(prompts[role].encode("utf-8")) for role in ROLES}
    total = sum(counts.values())

    # A prompt smaller than the payload cannot contain the payload. Combined
    # with the scaling proof above this pins the count at exactly one.
    for role in NO_INLINE_GDD_ROLES:
        require(counts[role] < gdd_bytes,
                f"{role} is large enough to still hold an inline GDD copy")
    require(counts[INLINE_GDD_ROLE] > gdd_bytes, "the auditor lost its inline GDD")

    # Before the change the aggregate held four copies, so it necessarily
    # exceeded 4x the payload; it now cannot even reach 2x.
    require(total < 2 * gdd_bytes,
            f"the aggregate fixed prompt ({total} bytes) still holds more than one GDD copy "
            f"({gdd_bytes} bytes)")

    print("    fixed prompt bytes (UTF-8), "
          f"{gdd_bytes}-byte committed GDD payload:")
    for role in ROLES:
        print(f"      {role:28s} {counts[role]:9d}")
    print(f"      {'TOTAL':28s} {total:9d}")


# --------------------------------------------------------------------- main


def main() -> int:
    tests = [
        value for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
        and getattr(value, "__module__", None) == __name__
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            FAILURES.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if FAILURES:
        print(f"prompt_context_reduction_smoke_test: FAIL ({len(FAILURES)})")
        return 1
    print("prompt_context_reduction_smoke_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
