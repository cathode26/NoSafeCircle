#!/usr/bin/env python3
"""Prove the Stage 1 short-lived atomic Git-ref claim layer.

Against disposable local bare remotes, these tests prove the race contract —
one atomic acquisition attempt admits AT MOST one winner of conflicting
claims (never two), while a zero-winner round is a legal typed outcome that
the caller retries; disjoint tasks proceed in parallel; a multi-ref claim is
all-or-nothing; release is exact-claim-SHA fenced so a stale worker cannot
delete a newer claim; stale claims are inspectable without deletion; only a
proven nonexistence/lease race is claim contention while pre-receive hook
and other remote/policy failures stay operational errors; the durable GitHub
Issue lease handoff holds the claims until the EXACT acquired authority
(task, agent_working, worker, lease_id, state_version, last_event_id) is
re-read and verified; a cleanup failure after verified acquisition returns
the typed lease_acquired_claim_cleanup_required recovery result instead of
ordinary success; a stale ephemeral claim never permanently invalidates this
worker's durable Issue lease (resume + manual exact-SHA repair); and the
real RealTaskReviewWorkflow composition path invokes the claim guard or
fails closed before Issue mutation when claim coordination is not activated.
Claim commit creation must never move the current branch, index, or working
tree.

Races use real concurrent `git push` processes released by a barrier — the
remote's own ref transaction is the arbiter, never timing sleeps.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent import claim_refs as claim_refs_module  # noqa: E402
from Pipeline.TaskReviewAgent import real_workflow as real_workflow_module  # noqa: E402
from Pipeline.TaskReviewAgent.claim_policy import (  # noqa: E402
    ClaimCoordinationNotActivatedError,
    ClaimPolicy,
    ClaimPolicyError,
    activated_claim_namespace,
    load_claim_policy,
    preferred_claim_namespace,
)
from Pipeline.TaskReviewAgent.claim_refs import (  # noqa: E402
    ClaimAcquisition,
    ClaimConflict,
    ClaimRefsError,
    GitRefClaimClient,
    acquire_issue_lease_with_claims,
    build_activated_claim_client,
    canonical_resource_hash,
    probe_remote_claim_namespace,
    resource_claim_ref,
    task_claim_ref,
)
from Pipeline.TaskReviewAgent.goal_loop import GoalAction, assess_goal_state  # noqa: E402
from Pipeline.TaskReviewAgent.issue_workflow_store import (  # noqa: E402
    IssueWorkflowService,
    MemoryIssueBackend,
)
from Pipeline.TaskReviewAgent.real_checkout import CANONICAL_REMOTE  # noqa: E402
from Pipeline.TaskReviewAgent.real_workflow import RealTaskReviewWorkflow  # noqa: E402
from Pipeline.TaskReviewAgent.tests.real_checkout_smoke_test import (  # noqa: E402
    TASK_ID as WORKFLOW_TASK_ID,
    create_fixture as create_workflow_fixture,
)

NAMESPACE = "refs/nsc/claims"
FALLBACK_NAMESPACE = "refs/heads/nsc-claims"
SHARED_RESOURCE = "unity-scene:Assets/Scenes/Shared.unity"
OTHER_RESOURCE = "unity-prefab:Assets/Prefabs/Door.prefab"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120.0,
    )
    require(
        result.returncode == 0,
        f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}",
    )
    return result.stdout.strip()


def git(repo: Path, *args: str) -> str:
    return run("git", "-C", str(repo), *args, cwd=repo)


class Fixture:
    """One bare remote plus two independent worker clones."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.remote = root / "remote.git"
        run("git", "init", "--bare", "--initial-branch=main", str(self.remote), cwd=root)
        seed = root / "seed"
        run("git", "init", "--initial-branch=main", str(seed), cwd=root)
        git(seed, "config", "user.name", "Claim Smoke Fixture")
        git(seed, "config", "user.email", "claim-smoke@example.invalid")
        (seed / "README.md").write_text("claim fixture\n", encoding="utf-8", newline="\n")
        git(seed, "add", "README.md")
        git(seed, "commit", "-m", "Seed claim fixture")
        git(seed, "remote", "add", "origin", str(self.remote))
        git(seed, "push", "-u", "origin", "main")
        self.source_head = git(seed, "rev-parse", "HEAD")
        self.worker_a_repo = root / "worker-a"
        self.worker_b_repo = root / "worker-b"
        run("git", "clone", str(self.remote), str(self.worker_a_repo), cwd=root)
        run("git", "clone", str(self.remote), str(self.worker_b_repo), cwd=root)

    def client(
        self,
        repo: Path,
        worker_id: str,
        namespace: str = NAMESPACE,
    ) -> GitRefClaimClient:
        return GitRefClaimClient(
            local_repository=repo,
            remote=str(self.remote),
            namespace=namespace,
            worker_id=worker_id,
        )

    def remote_claims(self, namespace: str = NAMESPACE) -> dict[str, str]:
        result = subprocess.run(
            ("git", "ls-remote", str(self.remote), f"{namespace}/*"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=120.0,
        )
        claims = {}
        for line in result.stdout.splitlines():
            oid, _, ref = line.partition("\t")
            claims[ref] = oid
        return claims


def git_state(repo: Path) -> dict[str, str]:
    return {
        "head": git(repo, "rev-parse", "HEAD"),
        "symbolic_ref": git(repo, "symbolic-ref", "HEAD"),
        "tree": git(repo, "rev-parse", "HEAD^{tree}"),
        "status": git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
        "staged": git(repo, "diff", "--cached", "--name-status"),
    }


def task(task_id: str, resources: Sequence[str]) -> dict[str, Any]:
    return {
        "id": task_id,
        "title": f"Claim fixture {task_id}",
        "contract_revision": 1,
        "kind": "implementation",
        "execution_scope": "single_agent",
        "decomposition_state": "concrete",
        "execution_reason": "Prove ephemeral claim coordination.",
        "depends_on": [],
        "exclusive_resources": list(resources),
        "acceptance_criteria": [],
        "completion_gates": [],
        "task_contract_sha256": (task_id[-1] * 64),
    }


def race(
    first: Callable[[], Any],
    second: Callable[[], Any],
) -> tuple[Any, Any]:
    """Run two acquisitions concurrently, released together by a barrier.

    Both mutual-conflict retries and the at-most-one-winner assertion belong
    to the caller; this helper only guarantees genuinely overlapping pushes.
    """

    barrier = threading.Barrier(2)
    results: list[Any] = [None, None]
    errors: list[BaseException | None] = [None, None]

    def runner(index: int, action: Callable[[], Any]) -> None:
        try:
            barrier.wait(timeout=60)
            results[index] = action()
        except BaseException as exc:  # surfaced by the caller
            errors[index] = exc

    threads = [
        threading.Thread(target=runner, args=(0, first)),
        threading.Thread(target=runner, args=(1, second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    for error in errors:
        if error is not None:
            raise error
    return results[0], results[1]


def race_until_one_winner(
    first: Callable[[], Any],
    second: Callable[[], Any],
    *,
    attempts: int = 5,
) -> tuple[Any, Any]:
    """Race repeatedly, proving the actual contract: at most one winner.

    One attempt does NOT guarantee exactly one winner: two overlapping atomic
    pushes can abort each other's ref transaction so that both lose, which is
    a normal, corruption-free, typed outcome. Two winners are never tolerated
    in any round; a zero-winner round must be a typed ClaimConflict on both
    sides and is retried here, exactly as a scheduler would recompute and
    retry later.
    """

    for _ in range(attempts):
        result_a, result_b = race(first, second)
        acquired = [r for r in (result_a, result_b) if isinstance(r, ClaimAcquisition)]
        require(len(acquired) <= 1, "two workers both acquired conflicting claims")
        if len(acquired) == 1:
            return result_a, result_b
        # Zero winners: both sides must be typed conflicts, never silent
        # success or an operational exception (those raise out of race()).
        require(
            isinstance(result_a, ClaimConflict) and isinstance(result_b, ClaimConflict),
            f"a zero-winner round was not typed: {result_a!r}, {result_b!r}",
        )
    raise AssertionError(f"no worker acquired the claim in {attempts} race attempts")


def active_test_policy(namespace: str = NAMESPACE) -> ClaimPolicy:
    """An explicitly activated policy object for local wiring tests only."""

    return ClaimPolicy(
        schema_version="1.0",
        mode="resume_only",
        namespace_preference=(NAMESPACE, FALLBACK_NAMESPACE),
        creation="atomic_multi_ref_nonexistence_cas",
        release="atomic_multi_ref_exact_sha_cas",
        stale_claim_repair="manual_exact_sha_only",
        activation_status="active",
        activated_namespace=namespace,
    )


def test_policy_is_resume_only_and_fails_closed(root: Path) -> None:
    policy = load_claim_policy()
    require(policy.mode == "resume_only", "committed claim policy mode must stay resume_only")
    require(
        policy.namespace_preference == (NAMESPACE, FALLBACK_NAMESPACE),
        f"unexpected namespace preference: {policy.namespace_preference}",
    )
    require(
        preferred_claim_namespace(policy) == NAMESPACE,
        "preferred namespace must be the first preference entry",
    )
    # The disposable-GitHub capability probe proved refs/nsc/claims (see
    # Pipeline/TaskReviewAgent/evidence/stage1-github-claim-capability-
    # 20260830.json), so the committed policy is now legitimately active.
    require(
        policy.activation_status == "active" and policy.activated_namespace == NAMESPACE,
        "the committed policy must record the probe-activated namespace: "
        f"{policy.activation_status!r}, {policy.activated_namespace!r}",
    )
    require(
        activated_claim_namespace(policy) == NAMESPACE,
        "the committed active policy must return the activated namespace",
    )
    require(
        activated_claim_namespace(active_test_policy()) == NAMESPACE,
        "an active policy must return exactly its activated namespace",
    )
    # Fail-closed pending behavior must still exist for a policy that has not
    # been activated, proven against a synthetic pending policy object rather
    # than the (now active) committed one.
    pending_policy = dataclasses.replace(
        active_test_policy(),
        activation_status="pending_capability_probe",
        activated_namespace=None,
    )
    try:
        activated_claim_namespace(pending_policy)
    except ClaimCoordinationNotActivatedError:
        pass
    else:
        raise AssertionError(
            "a pending_capability_probe policy handed out an activated namespace"
        )
    base = {
        "schema_version": "1.0",
        "mode": "resume_only",
        "namespace_preference": [NAMESPACE],
        "creation": "atomic_multi_ref_nonexistence_cas",
        "release": "atomic_multi_ref_exact_sha_cas",
        "stale_claim_repair": "manual_exact_sha_only",
        "activation": {"status": "pending_capability_probe", "activated_namespace": None},
    }
    weakenings = (
        {**base, "mode": "fresh_dispatch"},
        {**base, "activation": {"status": "active", "activated_namespace": None}},
        {
            **base,
            "activation": {
                "status": "active",
                "activated_namespace": "refs/other/claims",
            },
        },
        {**base, "activation": {"status": "yolo", "activated_namespace": None}},
    )
    for index, weakened in enumerate(weakenings):
        tampered = root / f"tampered_claim_policy_{index}.json"
        tampered.write_text(json.dumps(weakened), encoding="utf-8")
        try:
            load_claim_policy(tampered)
        except ClaimPolicyError:
            pass
        else:
            raise AssertionError(f"a weakened claim policy was accepted: {weakened}")


def test_same_task_race_admits_at_most_one_winner(root: Path) -> None:
    fixture = Fixture(root / "same-task")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    require(
        client_a.claim_worker_id != client_b.claim_worker_id,
        "claim worker identities must be unique per process/run",
    )
    state_a_before = git_state(fixture.worker_a_repo)
    state_b_before = git_state(fixture.worker_b_repo)

    def acquire(client: GitRefClaimClient) -> Any:
        return client.acquire(
            task_id="NSC-901",
            exclusive_resources=[SHARED_RESOURCE],
            source_head=fixture.source_head,
        )

    result_a, result_b = race_until_one_winner(
        lambda: acquire(client_a), lambda: acquire(client_b)
    )
    winner = result_a if isinstance(result_a, ClaimAcquisition) else result_b
    loser = result_b if winner is result_a else result_a
    require(isinstance(loser, ClaimConflict), f"race loser was not typed: {loser!r}")
    require(loser.status == "claim_conflict", "race loss must be the normal typed outcome")
    remote = fixture.remote_claims()
    expected_refs = {
        task_claim_ref(NAMESPACE, "NSC-901"),
        resource_claim_ref(NAMESPACE, SHARED_RESOURCE),
    }
    require(set(remote) == expected_refs, f"unexpected remote claim refs: {sorted(remote)}")
    require(
        all(oid == winner.claim_oid for oid in remote.values()),
        "remote claim refs do not all point at the winner's exact claim OID",
    )
    require(
        git_state(fixture.worker_a_repo) == state_a_before
        and git_state(fixture.worker_b_repo) == state_b_before,
        "claim creation changed a worker's branch HEAD, index, or working tree",
    )


def test_shared_resource_race_admits_at_most_one_winner(root: Path) -> None:
    fixture = Fixture(root / "shared-resource")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    result_a, result_b = race_until_one_winner(
        lambda: client_a.acquire(
            task_id="NSC-902",
            exclusive_resources=[SHARED_RESOURCE],
            source_head=fixture.source_head,
        ),
        lambda: client_b.acquire(
            task_id="NSC-903",
            exclusive_resources=[SHARED_RESOURCE, OTHER_RESOURCE],
            source_head=fixture.source_head,
        ),
    )
    winner = result_a if isinstance(result_a, ClaimAcquisition) else result_b
    remote = fixture.remote_claims()
    require(
        set(remote) == set(winner.refs),
        "the losing task left claim refs behind despite the shared-resource conflict",
    )
    require(
        all(oid == winner.claim_oid for oid in remote.values()),
        "surviving refs do not all carry the winner's claim OID",
    )


def test_disjoint_tasks_both_acquire(root: Path) -> None:
    fixture = Fixture(root / "disjoint")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    result_a, result_b = race(
        lambda: client_a.acquire(
            task_id="NSC-904",
            exclusive_resources=["unity-scene:Assets/Scenes/A.unity"],
            source_head=fixture.source_head,
        ),
        lambda: client_b.acquire(
            task_id="NSC-905",
            exclusive_resources=["unity-scene:Assets/Scenes/B.unity"],
            source_head=fixture.source_head,
        ),
    )
    require(
        isinstance(result_a, ClaimAcquisition) and isinstance(result_b, ClaimAcquisition),
        f"disjoint tasks could not claim in parallel: {result_a!r}, {result_b!r}",
    )
    remote = fixture.remote_claims()
    require(
        set(remote) == set(result_a.refs) | set(result_b.refs),
        f"unexpected remote refs after disjoint claims: {sorted(remote)}",
    )


def test_no_partial_claim_on_multi_ref_conflict(root: Path) -> None:
    fixture = Fixture(root / "no-partial")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    held = client_a.acquire(
        task_id="NSC-906",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"setup claim failed: {held!r}")
    blocked = client_b.acquire(
        task_id="NSC-907",
        exclusive_resources=[SHARED_RESOURCE, OTHER_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(blocked, ClaimConflict), f"conflicting claim was not typed: {blocked!r}")
    remote = fixture.remote_claims()
    require(
        task_claim_ref(NAMESPACE, "NSC-907") not in remote,
        "the losing worker's task ref was created despite the atomic conflict",
    )
    require(
        resource_claim_ref(NAMESPACE, OTHER_RESOURCE) not in remote,
        "the losing worker's non-conflicting resource ref was created — partial claim",
    )
    require(set(remote) == set(held.refs), "atomic conflict disturbed the holder's refs")


def test_exact_sha_release_and_stale_worker_fencing(root: Path) -> None:
    fixture = Fixture(root / "release")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    first = client_a.acquire(
        task_id="NSC-908",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(first, ClaimAcquisition), f"first claim failed: {first!r}")
    released = client_a.release(first)
    require(released["status"] == "released", f"own-claim release failed: {released}")
    require(fixture.remote_claims() == {}, "release left claim refs behind")

    # The same refs now belong to a NEWER claim by another worker; the stale
    # acquisition handle must be unable to delete them.
    second = client_b.acquire(
        task_id="NSC-908",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(second, ClaimAcquisition), f"second claim failed: {second!r}")
    require(second.claim_oid != first.claim_oid, "distinct claims reused one claim OID")
    stale = client_a.release(first)
    require(
        stale["status"] == "stale_claim_conflict",
        f"stale release was not fenced: {stale}",
    )
    remote = fixture.remote_claims()
    require(
        set(remote) == set(second.refs)
        and all(oid == second.claim_oid for oid in remote.values()),
        "a stale worker deleted or disturbed a newer worker's claim refs",
    )
    require(
        client_b.release(second)["status"] == "released",
        "the current holder could not release its own exact claims",
    )


def test_stale_claim_inspection_reports_without_deleting(root: Path) -> None:
    fixture = Fixture(root / "inspect")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    held = client_b.acquire(
        task_id="NSC-909",
        exclusive_resources=[SHARED_RESOURCE, OTHER_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"claim failed: {held!r}")
    # Simulate a crash: no release. A different process inspects the remote.
    inspector = fixture.client(fixture.worker_a_repo, "inspector")
    before = fixture.remote_claims()
    report = inspector.inspect_claims()
    require(len(report) == len(held.refs), f"inspection missed claim refs: {report}")
    for entry in report:
        require(entry["ref"] in held.refs, f"inspection reported a foreign ref: {entry}")
        require(entry["claim_oid"] == held.claim_oid, "inspection reported the wrong OID")
        receipt = entry["receipt"]
        require(receipt is not None, f"claim receipt was not recovered: {entry}")
        require(
            receipt["schema_version"] == "1.0"
            and receipt["task_id"] == "NSC-909"
            and receipt["claim_worker_id"] == client_b.claim_worker_id
            and receipt["source_head"] == fixture.source_head
            and receipt["exclusive_resources"] == sorted([SHARED_RESOURCE, OTHER_RESOURCE])
            and receipt["resource_hashes"]
            == [canonical_resource_hash(item) for item in sorted([SHARED_RESOURCE, OTHER_RESOURCE])]
            and receipt["created_at_utc"],
            f"claim receipt is incomplete: {receipt}",
        )
    require(
        fixture.remote_claims() == before,
        "inspection modified the remote claim refs",
    )


def test_fallback_namespace_is_explicit_and_works(root: Path) -> None:
    fixture = Fixture(root / "fallback-namespace")
    client = fixture.client(fixture.worker_a_repo, "agent-a", namespace=FALLBACK_NAMESPACE)
    held = client.acquire(
        task_id="NSC-901",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"fallback-namespace claim failed: {held!r}")
    remote = fixture.remote_claims(FALLBACK_NAMESPACE)
    require(
        set(remote) == set(held.refs)
        and all(ref.startswith("refs/heads/nsc-claims/") for ref in remote),
        f"fallback namespace refs are wrong: {sorted(remote)}",
    )
    require(client.release(held)["status"] == "released", "fallback release failed")


class ClaimObservingBackend(MemoryIssueBackend):
    """Records which claim refs exist at the moment the Issue is initialized."""

    def __init__(self, observe_claims: Callable[[], dict[str, str]]) -> None:
        super().__init__()
        self.observe_claims = observe_claims
        self.claims_during_initialization: dict[str, str] | None = None

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        self.claims_during_initialization = self.observe_claims()
        return super().create_issue(**kwargs)


class VerificationFailingService:
    """Delegate that acquires normally but cannot re-verify Issue authority."""

    def __init__(self, inner: IssueWorkflowService) -> None:
        self.inner = inner
        self.worker_id = inner.worker_id

    def acquire_agent_lease(self, **kwargs: Any) -> dict[str, Any]:
        return self.inner.acquire_agent_lease(**kwargs)

    def find(self, task_id: str) -> None:
        return None


def test_issue_handoff_holds_claims_then_releases(root: Path) -> None:
    fixture = Fixture(root / "handoff")
    client = fixture.client(fixture.worker_a_repo, "agent-a")
    fixture_task = task("NSC-910", [SHARED_RESOURCE])
    backend = ClaimObservingBackend(fixture.remote_claims)
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-a",
    )
    result = acquire_issue_lease_with_claims(
        claim_client=client,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-910-task",
        checkout_path=r"C:\NSC\NSC\NSC-910",
        planned_approach="Prove the claim-to-Issue handoff.",
        expected_validation="Vincent validates in Unity.",
        now="2026-08-30T10:00:00Z",
    )
    require(result["status"] == "acquired", f"guarded lease was not acquired: {result}")
    held = backend.claims_during_initialization
    require(
        held is not None and task_claim_ref(NAMESPACE, "NSC-910") in held,
        f"claim refs were not held during Issue initialization: {held}",
    )
    require(
        resource_claim_ref(NAMESPACE, SHARED_RESOURCE) in held,
        "resource claim ref was not held during Issue initialization",
    )
    require(
        result["ephemeral_claim"]["release"]["status"] == "released",
        f"claims were not released after verified handoff: {result['ephemeral_claim']}",
    )
    require(fixture.remote_claims() == {}, "handoff left ephemeral claim refs behind")
    verified = service.find("NSC-910")
    require(
        verified is not None
        and verified.state is not None
        and verified.state.state.value == "agent_working"
        and verified.state.worker_id == "agent-a",
        "durable Issue lease is not this worker's agent_working authority",
    )


def test_issue_handoff_failed_verification_is_not_success(root: Path) -> None:
    fixture = Fixture(root / "handoff-verify-fail")
    client = fixture.client(fixture.worker_a_repo, "agent-a")
    fixture_task = task("NSC-910", [SHARED_RESOURCE])
    service = VerificationFailingService(
        IssueWorkflowService(
            backend=MemoryIssueBackend(),
            task_loader=lambda task_id: fixture_task,
            worker_id="agent-a",
        )
    )
    result = acquire_issue_lease_with_claims(
        claim_client=client,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-910-task",
        checkout_path=r"C:\NSC\NSC\NSC-910",
        planned_approach="Verification must fail closed.",
        expected_validation="The handoff must not pretend success.",
        now="2026-08-30T10:01:00Z",
    )
    require(
        result["status"] == "blocked",
        f"failed authority verification pretended handoff success: {result}",
    )
    require(
        any("verified" in reason for reason in result["reasons"]),
        f"verification failure reason missing: {result['reasons']}",
    )
    require(
        result["ephemeral_claim_release"]["status"] == "released",
        "an active process could not release its own claims after the failure",
    )
    require(fixture.remote_claims() == {}, "failed verification left claim refs behind")


def test_issue_handoff_blocked_issue_releases_claims(root: Path) -> None:
    fixture = Fixture(root / "handoff-blocked")
    fixture_task = task("NSC-910", [SHARED_RESOURCE])
    backend = MemoryIssueBackend()
    holder = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-a",
    )
    holder.acquire_agent_lease(
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-910-task",
        checkout_path=r"C:\NSC\NSC\NSC-910",
        planned_approach="Hold the durable lease first.",
        expected_validation="Vincent validates in Unity.",
        now="2026-08-30T10:02:00Z",
    )
    other = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-b",
    )
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    result = acquire_issue_lease_with_claims(
        claim_client=client_b,
        issue_workflow=other,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-910-task",
        checkout_path=r"C:\NSC\NSC\NSC-910",
        planned_approach="The durable Issue must refuse this worker.",
        expected_validation="Blocked outcome passes through.",
        now="2026-08-30T10:03:00Z",
    )
    require(result["status"] == "blocked", f"leased Issue did not block: {result}")
    require(
        result["ephemeral_claim_release"]["status"] == "released",
        "claims were not released after the normal blocked Issue outcome",
    )
    require(fixture.remote_claims() == {}, "blocked handoff left claim refs behind")


def test_claim_race_loss_result_shape(root: Path) -> None:
    fixture = Fixture(root / "loss-shape")
    fixture_task = task("NSC-901", [SHARED_RESOURCE])
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    held = client_a.acquire(
        task_id="NSC-901",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"setup claim failed: {held!r}")
    service = IssueWorkflowService(
        backend=MemoryIssueBackend(),
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-b",
    )
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    result = acquire_issue_lease_with_claims(
        claim_client=client_b,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-901-task",
        checkout_path=r"C:\NSC\NSC\NSC-901",
        planned_approach="Losing the claim race is a normal scheduling result.",
        expected_validation="Typed blocked outcome, no Issue mutation.",
        now="2026-08-30T10:04:00Z",
    )
    require(result["status"] == "blocked", f"claim conflict was not a normal result: {result}")
    require(
        result["ephemeral_claim"]["status"] == "claim_conflict",
        f"claim conflict outcome is untyped: {result}",
    )
    require(
        service.find("NSC-901") is None,
        "a claim-race loser still initialized the durable Issue",
    )
    remote = fixture.remote_claims()
    require(
        set(remote) == set(held.refs)
        and all(oid == held.claim_oid for oid in remote.values()),
        "a lost claim race corrupted the winner's refs",
    )


def test_probe_refuses_production_remote_and_works_locally(root: Path) -> None:
    fixture = Fixture(root / "probe")
    try:
        probe_remote_claim_namespace(
            local_repository=fixture.worker_a_repo,
            remote=CANONICAL_REMOTE,
            namespace=NAMESPACE,
        )
    except ClaimRefsError:
        pass
    else:
        raise AssertionError("the capability probe accepted the production remote by default")
    report = probe_remote_claim_namespace(
        local_repository=fixture.worker_a_repo,
        remote=str(fixture.remote),
        namespace=NAMESPACE,
    )
    require(report["capability"] is True, f"local capability probe failed: {report}")
    require(fixture.remote_claims() == {}, "the capability probe left its ref behind")


def remote_claims_at(remote: Path, namespace: str = NAMESPACE) -> dict[str, str]:
    result = subprocess.run(
        ("git", "ls-remote", str(remote), f"{namespace}/*"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=120.0,
    )
    claims: dict[str, str] = {}
    for line in result.stdout.splitlines():
        oid, _, ref = line.partition("\t")
        claims[ref] = oid
    return claims


def _fake_push_result(stdout: str, stderr: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(
        args=("git", "push"),
        returncode=1,
        stdout=stdout.encode("utf-8"),
        stderr=stderr.encode("utf-8"),
    )


def test_github_nonexistence_cas_rejection_is_recognized_as_contention(root: Path) -> None:
    """Reproduce the real GitHub same-task-race porcelain shape.

    The losing ref carries the exact nonexistence-CAS proof inline in its
    OWN porcelain reason (``cannot lock ref '<exact ref>': reference already
    exists``), while the sibling ref in the same ``--atomic`` transaction
    reports only the bare, unproven reason ``failed``. This must classify as
    contention, not an operational error.
    """

    task_ref = task_claim_ref(NAMESPACE, "NSC-991")
    resource_ref = resource_claim_ref(NAMESPACE, SHARED_RESOURCE)
    refs = (task_ref, resource_ref)
    stdout = (
        "To https://github.com/example/example.git\n"
        f"!\t{'b' * 40}:{task_ref}\t"
        f"[remote rejected] (cannot lock ref '{task_ref}': reference already exists)\n"
        f"!\t{'c' * 40}:{resource_ref}\t[remote rejected] (failed)\n"
        "Done\n"
    )
    stderr = (
        f"error: cannot lock ref '{task_ref}': reference already exists\n"
        "error: failed to push some refs to 'https://github.com/example/example.git'\n"
    )
    classification, details = claim_refs_module._classify_failed_claim_push(
        refs, _fake_push_result(stdout, stderr)
    )
    require(
        classification == "contention",
        "the real GitHub nonexistence-CAS rejection shape was misclassified: "
        f"{classification} ({details})",
    )

    # End to end through acquire(): the same shape must surface as a typed
    # ClaimConflict(kind="held_by_other"), never an operational exception.
    fixture = Fixture(root / "github-shape-contention")
    client = fixture.client(fixture.worker_a_repo, "agent-a")
    real_run_git = claim_refs_module._run_git

    def faked_run_git(repository: Path, *args: str, **kwargs: Any) -> Any:
        if args and args[0] == "push":
            return _fake_push_result(stdout, stderr)
        return real_run_git(repository, *args, **kwargs)

    claim_refs_module._run_git = faked_run_git
    try:
        outcome = client.acquire(
            task_id="NSC-991",
            exclusive_resources=[SHARED_RESOURCE],
            source_head=fixture.source_head,
        )
    finally:
        claim_refs_module._run_git = real_run_git
    require(
        isinstance(outcome, ClaimConflict) and outcome.kind == "held_by_other",
        f"the GitHub nonexistence-CAS shape was not a held_by_other ClaimConflict: {outcome!r}",
    )


def test_bare_failed_reason_alone_is_not_contention(root: Path) -> None:
    """A bare "(failed)" reason on every rejected ref, with no proof anywhere,
    must stay an operational error, never contention."""

    task_ref = task_claim_ref(NAMESPACE, "NSC-992")
    resource_ref = resource_claim_ref(NAMESPACE, SHARED_RESOURCE)
    refs = (task_ref, resource_ref)
    stdout = (
        "To https://github.com/example/example.git\n"
        f"!\t{'b' * 40}:{task_ref}\t[remote rejected] (failed)\n"
        f"!\t{'c' * 40}:{resource_ref}\t[remote rejected] (failed)\n"
        "Done\n"
    )
    stderr = "error: failed to push some refs to 'https://github.com/example/example.git'\n"
    classification, _ = claim_refs_module._classify_failed_claim_push(
        refs, _fake_push_result(stdout, stderr)
    )
    require(
        classification == "operational",
        f"a bare 'failed' reason with no proof was treated as contention: {classification}",
    )


def test_unrelated_ref_proof_is_not_contention(root: Path) -> None:
    """A "cannot lock ref" proof for a ref this push never requested must not
    taint this push's own unproven "(failed)" rejections."""

    task_ref = task_claim_ref(NAMESPACE, "NSC-993")
    resource_ref = resource_claim_ref(NAMESPACE, SHARED_RESOURCE)
    refs = (task_ref, resource_ref)
    unrelated_ref = "refs/heads/unrelated-branch"
    stdout = (
        "To https://github.com/example/example.git\n"
        f"!\t{'b' * 40}:{task_ref}\t[remote rejected] (failed)\n"
        f"!\t{'c' * 40}:{resource_ref}\t[remote rejected] (failed)\n"
        "Done\n"
    )
    stderr = (
        f"error: cannot lock ref '{unrelated_ref}': reference already exists\n"
        "error: failed to push some refs to 'https://github.com/example/example.git'\n"
    )
    classification, _ = claim_refs_module._classify_failed_claim_push(
        refs, _fake_push_result(stdout, stderr)
    )
    require(
        classification == "operational",
        "proof for an unrelated non-requested ref was treated as this push's "
        f"own contention: {classification}",
    )


def test_hook_rejection_is_operational_error_not_claim_conflict(root: Path) -> None:
    """A pre-receive policy rejection must never look like a lost claim race."""

    fixture = Fixture(root / "hook-rejection")
    hook = fixture.remote / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        'echo "claims are administratively refused by repository policy" >&2\n'
        "exit 1\n",
        encoding="utf-8",
        newline="\n",
    )
    hook.chmod(0o755)
    client = fixture.client(fixture.worker_a_repo, "agent-a")
    try:
        outcome = client.acquire(
            task_id="NSC-911",
            exclusive_resources=[SHARED_RESOURCE],
            source_head=fixture.source_head,
        )
    except ClaimRefsError as exc:
        require(
            "not a claim race" in str(exc),
            f"hook rejection error does not say it is not a race: {exc}",
        )
    else:
        raise AssertionError(
            f"a pre-receive hook rejection was returned as a claim outcome: {outcome!r}"
        )
    require(fixture.remote_claims() == {}, "the rejected push left claim refs behind")

    # The same hook must also make a fenced delete operational, not stale.
    hook.unlink()
    held = client.acquire(
        task_id="NSC-911",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"post-hook claim failed: {held!r}")
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    try:
        release = client.release(held)
    except ClaimRefsError:
        pass
    else:
        raise AssertionError(
            f"a hook-rejected release was returned as a claim outcome: {release}"
        )


def test_input_validation_and_foreign_release_refusal(root: Path) -> None:
    fixture = Fixture(root / "input-validation")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")

    def expect_claim_error(action: Callable[[], Any], text: str) -> None:
        try:
            action()
        except ClaimRefsError as exc:
            require(text in str(exc), f"unexpected error for {text!r}: {exc}")
        else:
            raise AssertionError(f"expected ClaimRefsError containing {text!r}")

    expect_claim_error(
        lambda: client_a.acquire(
            task_id="NSC-916",
            exclusive_resources=[123],  # type: ignore[list-item]
            source_head=fixture.source_head,
        ),
        "must be strings",
    )
    expect_claim_error(
        lambda: client_a.acquire(
            task_id="NSC-916",
            exclusive_resources=["   "],
            source_head=fixture.source_head,
        ),
        "non-empty",
    )
    require(fixture.remote_claims() == {}, "rejected input still created claim refs")

    held = client_a.acquire(
        task_id="NSC-916",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(held, ClaimAcquisition), f"claim failed: {held!r}")
    # A different run of the same worker (fresh claim identity) must not be
    # able to locally release this acquisition; repair stays manual.
    later_run = fixture.client(fixture.worker_a_repo, "agent-a")
    expect_claim_error(lambda: later_run.release(held), "repair_stale_claim")
    # A client bound to another namespace must refuse the acquisition too.
    other_namespace = fixture.client(
        fixture.worker_a_repo, "agent-a", namespace=FALLBACK_NAMESPACE
    )
    expect_claim_error(lambda: other_namespace.release(held), "namespace")
    expect_claim_error(
        lambda: client_a.repair_stale_claim(
            refs=["refs/heads/main"], expected_claim_oid=held.claim_oid
        ),
        "namespace",
    )
    require(
        set(fixture.remote_claims()) == set(held.refs),
        "a refused release still touched the remote claim refs",
    )
    require(
        client_a.release(held)["status"] == "released",
        "the owning client could not release its own claims",
    )


def test_claim_worker_issue_worker_mismatch_fails_before_mutation(root: Path) -> None:
    fixture = Fixture(root / "worker-mismatch")
    fixture_task = task("NSC-917", [SHARED_RESOURCE])
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-b",
    )
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    try:
        acquire_issue_lease_with_claims(
            claim_client=client_a,
            issue_workflow=service,
            task=fixture_task,
            source_head=fixture.source_head,
            branch="nsc-917-task",
            checkout_path=r"C:\NSC\NSC\NSC-917",
            planned_approach="Identity mismatch must fail first.",
            expected_validation="No remote mutation may occur.",
            now="2026-08-30T11:00:00Z",
        )
    except ClaimRefsError as exc:
        require("worker_id" in str(exc), f"mismatch error lacks identity detail: {exc}")
    else:
        raise AssertionError("a claim/Issue worker identity mismatch was accepted")
    require(fixture.remote_claims() == {}, "the mismatch still created claim refs")
    require(backend.issues == {}, "the mismatch still initialized the GitHub Issue")


class WrongLeaseService:
    """Delegate whose re-read reports the same worker under a DIFFERENT lease."""

    def __init__(self, inner: IssueWorkflowService) -> None:
        self.inner = inner
        self.worker_id = inner.worker_id

    def acquire_agent_lease(self, **kwargs: Any) -> dict[str, Any]:
        return self.inner.acquire_agent_lease(**kwargs)

    def find(self, task_id: str) -> Any:
        snapshot = self.inner.find(task_id)
        if snapshot is None or snapshot.state is None:
            return snapshot
        return dataclasses.replace(
            snapshot,
            state=dataclasses.replace(snapshot.state, lease_id="f" * 64),
        )


def test_same_worker_wrong_lease_id_fails_handoff(root: Path) -> None:
    fixture = Fixture(root / "wrong-lease")
    fixture_task = task("NSC-918", [SHARED_RESOURCE])
    service = WrongLeaseService(
        IssueWorkflowService(
            backend=MemoryIssueBackend(),
            task_loader=lambda task_id: fixture_task,
            worker_id="agent-a",
        )
    )
    client = fixture.client(fixture.worker_a_repo, "agent-a")
    result = acquire_issue_lease_with_claims(
        claim_client=client,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-918-task",
        checkout_path=r"C:\NSC\NSC\NSC-918",
        planned_approach="Same worker, different lease, must fail.",
        expected_validation="Handoff must be refused.",
        now="2026-08-30T11:01:00Z",
    )
    require(
        result["status"] == "blocked",
        f"a same-worker different-lease state passed the handoff: {result}",
    )
    require(
        any("different lease" in reason for reason in result["reasons"]),
        f"lease mismatch reason missing: {result['reasons']}",
    )
    require(
        result["ephemeral_claim_release"]["status"] == "released",
        "claims were not released after the refused handoff",
    )
    require(fixture.remote_claims() == {}, "refused handoff left claim refs behind")


class ClaimSabotagingBackend(MemoryIssueBackend):
    """Runs a sabotage callback once, while the Issue is being initialized."""

    def __init__(self, sabotage: Callable[[], None]) -> None:
        super().__init__()
        self.sabotage = sabotage
        self.sabotaged = False

    def create_issue(self, **kwargs: Any) -> dict[str, Any]:
        issue = super().create_issue(**kwargs)
        if not self.sabotaged:
            self.sabotaged = True
            self.sabotage()
        return issue


def test_cleanup_failure_is_not_ordinary_success(root: Path) -> None:
    """A superseded claim at release time must surface as a recovery result."""

    fixture = Fixture(root / "cleanup-failure")
    client_a = fixture.client(fixture.worker_a_repo, "agent-a")
    client_b = fixture.client(fixture.worker_b_repo, "agent-b")
    fixture_task = task("NSC-919", [SHARED_RESOURCE])
    newer: dict[str, Any] = {}

    def sabotage() -> None:
        # Simulate a bad manual repair racing this run: worker A's claim
        # refs are deleted out from under it and re-claimed by worker B.
        held = fixture.remote_claims()
        git(
            fixture.worker_b_repo,
            "push",
            str(fixture.remote),
            *(f":{ref}" for ref in sorted(held)),
        )
        acquisition = client_b.acquire(
            task_id="NSC-919",
            exclusive_resources=[SHARED_RESOURCE],
            source_head=fixture.source_head,
        )
        require(
            isinstance(acquisition, ClaimAcquisition),
            f"sabotage reclaim failed: {acquisition!r}",
        )
        newer["acquisition"] = acquisition

    backend = ClaimSabotagingBackend(sabotage)
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-a",
    )
    result = acquire_issue_lease_with_claims(
        claim_client=client_a,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-919-task",
        checkout_path=r"C:\NSC\NSC\NSC-919",
        planned_approach="Cleanup failure must not look successful.",
        expected_validation="Recovery status with the lease fact preserved.",
        now="2026-08-30T11:02:00Z",
    )
    require(
        result["status"] == "lease_acquired_claim_cleanup_required",
        f"cleanup failure returned an ordinary outcome: {result['status']}",
    )
    require(
        result["issue_result"]["status"] == "acquired",
        f"the acquired durable lease fact was lost: {result['issue_result']}",
    )
    require(
        result["ephemeral_claim_release"]["status"] == "stale_claim_conflict",
        f"release outcome is not the fenced conflict: {result['ephemeral_claim_release']}",
    )
    acquisition = newer["acquisition"]
    remote = fixture.remote_claims()
    require(
        set(remote) == set(acquisition.refs)
        and all(oid == acquisition.claim_oid for oid in remote.values()),
        "the newer worker's claim refs were deleted despite the exact-SHA fence",
    )
    verified = service.find("NSC-919")
    require(
        verified is not None
        and verified.state is not None
        and verified.state.state.value == "agent_working"
        and verified.state.worker_id == "agent-a",
        "the durable Issue lease itself was lost during cleanup failure",
    )


def test_durable_resume_without_stale_claim(root: Path) -> None:
    fixture = Fixture(root / "durable-resume")
    fixture_task = task("NSC-920", [SHARED_RESOURCE])
    service = IssueWorkflowService(
        backend=MemoryIssueBackend(),
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-a",
    )
    first_run = fixture.client(fixture.worker_a_repo, "agent-a")
    first = acquire_issue_lease_with_claims(
        claim_client=first_run,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-920-task",
        checkout_path=r"C:\NSC\NSC\NSC-920",
        planned_approach="Acquire, then resume from a later run.",
        expected_validation="Ordinary acquire and ordinary resume.",
        now="2026-08-30T11:03:00Z",
    )
    require(first["status"] == "acquired", f"initial guarded acquire failed: {first}")
    second_run = fixture.client(fixture.worker_a_repo, "agent-a")
    require(
        second_run.claim_worker_id != first_run.claim_worker_id,
        "a later run reused the earlier run's claim identity",
    )
    resumed = acquire_issue_lease_with_claims(
        claim_client=second_run,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-920-task",
        checkout_path=r"C:\NSC\NSC\NSC-920",
        planned_approach="Resume the durable lease.",
        expected_validation="Same worker, same lease, clean claims.",
        now="2026-08-30T11:04:00Z",
    )
    require(resumed["status"] == "resumed", f"durable resume failed: {resumed}")
    require(
        "stale_ephemeral_claim" not in resumed,
        f"a clean resume reported a stale claim: {resumed}",
    )
    require(
        resumed["ephemeral_claim"]["release"]["status"] == "released",
        "resume claims were not released",
    )
    require(fixture.remote_claims() == {}, "resume left ephemeral claim refs behind")


def test_durable_resume_with_stale_claim_and_manual_repair(root: Path) -> None:
    """A stale claim from a crashed run must not invalidate the durable lease."""

    fixture = Fixture(root / "stale-resume")
    fixture_task = task("NSC-921", [SHARED_RESOURCE])
    backend = MemoryIssueBackend()
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-a",
    )
    crashed_run = fixture.client(fixture.worker_a_repo, "agent-a")
    stale = crashed_run.acquire(
        task_id="NSC-921",
        exclusive_resources=[SHARED_RESOURCE],
        source_head=fixture.source_head,
    )
    require(isinstance(stale, ClaimAcquisition), f"prior-run claim failed: {stale!r}")
    acquired = service.acquire_agent_lease(
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-921-task",
        checkout_path=r"C:\NSC\NSC\NSC-921",
        planned_approach="Prior run acquires, then crashes before release.",
        expected_validation="Claims remain; the durable lease is authoritative.",
        now="2026-08-30T11:05:00Z",
    )
    require(acquired["status"] == "acquired", f"prior-run Issue acquire failed: {acquired}")
    # The prior process crashes here: its claims are never released.

    new_run = fixture.client(fixture.worker_a_repo, "agent-a")
    resumed = acquire_issue_lease_with_claims(
        claim_client=new_run,
        issue_workflow=service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-921-task",
        checkout_path=r"C:\NSC\NSC\NSC-921",
        planned_approach="Resume past the stale claim.",
        expected_validation="Durable authority wins; stale claim reported.",
        now="2026-08-30T11:06:00Z",
    )
    require(
        resumed["status"] == "resumed",
        f"a stale claim invalidated this worker's durable lease: {resumed}",
    )
    stale_report = resumed.get("stale_ephemeral_claim")
    require(
        stale_report is not None and sorted(stale_report["refs"]) == sorted(stale.refs),
        f"the stale claim was not reported for repair: {resumed}",
    )
    for entry in stale_report["claims"]:
        require(
            entry["claim_oid"] == stale.claim_oid
            and entry["receipt"] is not None
            and entry["receipt"]["claim_worker_id"] == crashed_run.claim_worker_id,
            f"stale-claim identity was not inspectable: {entry}",
        )
    remote = fixture.remote_claims()
    require(
        set(remote) == set(stale.refs)
        and all(oid == stale.claim_oid for oid in remote.values()),
        "the stale claim was deleted automatically; repair must stay manual",
    )
    require(
        resumed["workflow_state"]["lease_id"]
        == acquired["workflow_state"]["lease_id"],
        "the resumed lease is not the exact durable lease",
    )

    # A DIFFERENT worker must stay blocked by both the claim and the lease.
    other_service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: fixture_task,
        worker_id="agent-b",
    )
    other = acquire_issue_lease_with_claims(
        claim_client=fixture.client(fixture.worker_b_repo, "agent-b"),
        issue_workflow=other_service,
        task=fixture_task,
        source_head=fixture.source_head,
        branch="nsc-921-task",
        checkout_path=r"C:\NSC\NSC\NSC-921",
        planned_approach="Another worker must not steal the resume.",
        expected_validation="Blocked without mutation.",
        now="2026-08-30T11:07:00Z",
    )
    require(other["status"] == "blocked", f"a different worker resumed: {other}")
    require(
        other["ephemeral_claim"]["status"] == "claim_conflict",
        f"the other worker's loss was untyped: {other}",
    )
    still = service.find("NSC-921")
    require(
        still is not None
        and still.state is not None
        and still.state.worker_id == "agent-a",
        "the durable lease changed hands during the blocked attempt",
    )

    # Manual exact-SHA repair: a wrong OID must not delete anything.
    wrong = new_run.repair_stale_claim(
        refs=list(stale.refs), expected_claim_oid="e" * 40
    )
    require(
        wrong["status"] == "stale_claim_conflict",
        f"a wrong-OID repair was not fenced: {wrong}",
    )
    require(
        fixture.remote_claims() == remote,
        "a wrong-OID repair deleted or disturbed claim refs",
    )
    repaired = new_run.repair_stale_claim(
        refs=list(stale.refs), expected_claim_oid=stale.claim_oid
    )
    require(repaired["status"] == "released", f"exact-SHA repair failed: {repaired}")
    require(fixture.remote_claims() == {}, "exact-SHA repair left claim refs behind")


def workflow_task_record(controller: Path) -> dict[str, Any]:
    raw = subprocess.check_output(
        ("git", "-C", str(controller), "show", f"HEAD:Tasks/{WORKFLOW_TASK_ID}.yaml")
    )
    return {
        **json.loads(raw.decode("utf-8-sig")),
        "task_contract_sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_real_workflow_invokes_claim_guard(root: Path) -> None:
    """RealTaskReviewWorkflow.acquire_agent_lease must run the claim guard."""

    fixture_root = root / "workflow-guard"
    fixture_root.mkdir(parents=True, exist_ok=True)
    controller, remote, _ = create_workflow_fixture(fixture_root)
    task_record = workflow_task_record(controller)
    backend = ClaimObservingBackend(lambda: remote_claims_at(remote))
    service = IssueWorkflowService(
        backend=backend,
        task_loader=lambda task_id: task_record,
        worker_id="agent-a",
    )
    client = GitRefClaimClient(
        local_repository=controller,
        remote=str(remote),
        namespace=NAMESPACE,
        worker_id="agent-a",
    )
    workflow = RealTaskReviewWorkflow(
        source=controller,
        task_id=WORKFLOW_TASK_ID,
        checkout_root=fixture_root / "operator",
        worker_id="agent-a",
        issue_workflow_service=service,
        claim_client=client,
        allow_local_remote_for_tests=True,
    )
    observation = workflow.observe_goal_state()
    require(
        assess_goal_state(observation).action is GoalAction.ACQUIRE_AGENT_LEASE,
        "workflow fixture did not request a lease",
    )
    result = workflow.acquire_agent_lease(
        planned_approach="Prove the workflow claim guard.",
        expected_validation="Claims held during Issue init, then released.",
    )
    require(result["status"] == "acquired", f"guarded workflow lease failed: {result}")
    held = backend.claims_during_initialization
    require(
        held is not None and task_claim_ref(NAMESPACE, WORKFLOW_TASK_ID) in held,
        f"the workflow did not hold claim refs during Issue initialization: {held}",
    )
    require(
        result["ephemeral_claim"]["release"]["status"] == "released",
        f"workflow claims were not released: {result['ephemeral_claim']}",
    )
    require(remote_claims_at(remote) == {}, "workflow left ephemeral claim refs behind")


def test_production_composition_fails_closed_without_activation(root: Path) -> None:
    """The self-composed mutating path must stop before any Issue mutation.

    Stage 1's committed claim policy is now activated (refs/nsc/claims), so
    this fail-closed proof passes an explicit synthetic pending policy to the
    self-composed production path rather than relying on the committed
    policy's current activation status.
    """

    fixture_root = root / "production-fail-closed"
    fixture_root.mkdir(parents=True, exist_ok=True)
    controller, remote, _ = create_workflow_fixture(fixture_root)
    backend = MemoryIssueBackend()
    pending_policy = dataclasses.replace(
        active_test_policy(),
        activation_status="pending_capability_probe",
        activated_namespace=None,
    )
    original_backend_type = real_workflow_module.GhIssueBackend
    real_workflow_module.GhIssueBackend = lambda **kwargs: backend  # type: ignore[assignment]
    try:
        workflow = RealTaskReviewWorkflow(
            source=controller,
            task_id=WORKFLOW_TASK_ID,
            checkout_root=fixture_root / "operator",
            worker_id="agent-a",
            claim_policy=pending_policy,
            allow_local_remote_for_tests=True,
        )
        require(
            workflow.claim_coordination_required,
            "the self-composed production path did not require claim coordination",
        )
        workflow.observe_goal_state()
        try:
            workflow.acquire_agent_lease(
                planned_approach="Must fail closed before Issue mutation.",
                expected_validation="No Issue and no claim refs are created.",
            )
        except ClaimCoordinationNotActivatedError as exc:
            require(
                "pending_capability_probe" in str(exc),
                f"fail-closed error does not name the pending activation: {exc}",
            )
        else:
            raise AssertionError(
                "the production path fell back to Issue-only admission without "
                "activated claim coordination"
            )
    finally:
        real_workflow_module.GhIssueBackend = original_backend_type
    require(backend.issues == {}, "the fail-closed path still mutated the Issue store")
    require(remote_claims_at(remote) == {}, "the fail-closed path created claim refs")


def test_production_composition_builds_activated_claim_client(root: Path) -> None:
    """With an active policy the self-composed path builds the configured client."""

    fixture_root = root / "production-active"
    fixture_root.mkdir(parents=True, exist_ok=True)
    controller, remote, _ = create_workflow_fixture(fixture_root)
    backend = ClaimObservingBackend(lambda: remote_claims_at(remote))
    original_backend_type = real_workflow_module.GhIssueBackend
    real_workflow_module.GhIssueBackend = lambda **kwargs: backend  # type: ignore[assignment]
    try:
        workflow = RealTaskReviewWorkflow(
            source=controller,
            task_id=WORKFLOW_TASK_ID,
            checkout_root=fixture_root / "operator",
            worker_id="agent-a",
            claim_policy=active_test_policy(),
            allow_local_remote_for_tests=True,
        )
        workflow.observe_goal_state()
        result = workflow.acquire_agent_lease(
            planned_approach="Prove activated production wiring.",
            expected_validation="The configured claim client guards admission.",
        )
    finally:
        real_workflow_module.GhIssueBackend = original_backend_type
    require(result["status"] == "acquired", f"activated wiring failed: {result}")
    client = workflow.claim_client
    require(client is not None, "no claim client was composed from the active policy")
    require(
        client.namespace == NAMESPACE,
        f"the composed client uses the wrong namespace: {client.namespace}",
    )
    require(
        client.worker_id == "agent-a",
        f"the composed client uses the wrong worker: {client.worker_id}",
    )
    require(
        client.remote == git(controller, "remote", "get-url", "origin"),
        f"the composed client uses the wrong remote: {client.remote}",
    )
    held = backend.claims_during_initialization
    require(
        held is not None and task_claim_ref(NAMESPACE, WORKFLOW_TASK_ID) in held,
        f"the composed client did not hold claims during Issue init: {held}",
    )
    require(remote_claims_at(remote) == {}, "activated wiring left claim refs behind")


def test_build_activated_claim_client_matches_policy(root: Path) -> None:
    fixture = Fixture(root / "builder")
    committed_client = build_activated_claim_client(
        local_repository=fixture.worker_a_repo,
        remote=str(fixture.remote),
        worker_id="agent-a",
        policy=load_claim_policy(),
    )
    require(
        committed_client.namespace == NAMESPACE,
        "the builder did not honor the committed active policy's namespace: "
        f"{committed_client.namespace}",
    )
    client = build_activated_claim_client(
        local_repository=fixture.worker_a_repo,
        remote=str(fixture.remote),
        worker_id="agent-a",
        policy=active_test_policy(FALLBACK_NAMESPACE),
    )
    require(
        client.namespace == FALLBACK_NAMESPACE,
        "the builder ignored the explicitly activated namespace",
    )
    # Fail-closed pending behavior must still exist for a policy that has not
    # been activated.
    pending_policy = dataclasses.replace(
        active_test_policy(),
        activation_status="pending_capability_probe",
        activated_namespace=None,
    )
    try:
        build_activated_claim_client(
            local_repository=fixture.worker_a_repo,
            remote=str(fixture.remote),
            worker_id="agent-a",
            policy=pending_policy,
        )
    except ClaimCoordinationNotActivatedError:
        pass
    else:
        raise AssertionError("a pending_capability_probe policy built a claim client")


def main() -> int:
    tests = (
        test_policy_is_resume_only_and_fails_closed,
        test_same_task_race_admits_at_most_one_winner,
        test_shared_resource_race_admits_at_most_one_winner,
        test_disjoint_tasks_both_acquire,
        test_no_partial_claim_on_multi_ref_conflict,
        test_exact_sha_release_and_stale_worker_fencing,
        test_stale_claim_inspection_reports_without_deleting,
        test_fallback_namespace_is_explicit_and_works,
        test_issue_handoff_holds_claims_then_releases,
        test_issue_handoff_failed_verification_is_not_success,
        test_issue_handoff_blocked_issue_releases_claims,
        test_claim_race_loss_result_shape,
        test_probe_refuses_production_remote_and_works_locally,
        test_github_nonexistence_cas_rejection_is_recognized_as_contention,
        test_bare_failed_reason_alone_is_not_contention,
        test_unrelated_ref_proof_is_not_contention,
        test_hook_rejection_is_operational_error_not_claim_conflict,
        test_input_validation_and_foreign_release_refusal,
        test_claim_worker_issue_worker_mismatch_fails_before_mutation,
        test_same_worker_wrong_lease_id_fails_handoff,
        test_cleanup_failure_is_not_ordinary_success,
        test_durable_resume_without_stale_claim,
        test_durable_resume_with_stale_claim_and_manual_repair,
        test_real_workflow_invokes_claim_guard,
        test_production_composition_fails_closed_without_activation,
        test_production_composition_builds_activated_claim_client,
        test_build_activated_claim_client_matches_policy,
    )
    with tempfile.TemporaryDirectory(prefix="nsc-claim-refs-") as temporary:
        root = Path(temporary)
        for test in tests:
            test(root)
            print(f"PASS {test.__name__}")
    print(f"TaskReviewAgent claim refs tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
