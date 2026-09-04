#!/usr/bin/env python3
"""Regression tests for the committed decomposition child-template policy audit.

Classification: pure/component tests plus temporary-Git-repository behavior
tests. No provider, container, network call, GitHub Issue, Unity invocation, or
tracked repository file is involved; the only tracked file any test reads is the
real committed `authoritative_validation_policy.json`, which is read and never
written.

The load-bearing claims are: the committed policy document satisfies the schema
its own decomposition reader demands; every machine-approved decomposition parent
that can be selected carries exactly one template; a template can never name an
unknown, inactive, ineligible, or human-approved parent; a template whose parent
hash has drifted is stale; variants that are empty, malformed, duplicated,
unsorted, overlapping, or that fail to partition the parent's exclusive resources
fail closed; the one committed generator's output passes the audit unchanged; a
bound source commit is audited at that commit rather than at current main; and
ordinary concrete-task resolution is byte-identical to what it was before.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Pipeline.TaskReviewAgent.decomposition_policy_audit import (  # noqa: E402
    DECOMPOSITION_TEMPLATE_AUTHORITY,
    VALIDATION_POLICY_RELATIVE,
    ValidationPolicyAuditError,
    audit_decomposition_policy,
    decomposition_preflight,
    is_decomposition_eligible_parent,
    parent_semantic_hash,
    read_committed_tasks,
    read_policy_document,
    requires_decomposition_child_template,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    decomposition_validation_policy_for,
    validation_plan_for,
)
from Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet import (  # noqa: E402
    POLICY_RELATIVE,
    build_bundle,
)
import Pipeline.TaskReviewAgent.prepare_synthetic_gauntlet as gauntlet  # noqa: E402


# The exact resolution NSC-042 has today. Pinned so the migration is provably
# byte-neutral for every ordinary concrete task.
NSC_042_CONTRACT_SHA256 = (
    "85b133ffa0af42f6a26c21180878c79ed9121a57ba6df151a88b2c6611d359a0"
)
NSC_042_POLICY_SHA256 = (
    "796b843af99b33d8a29cbfa3d058bb54c8e18354244213ad0cce852266146445"
)
NSC_020_CONTRACT_SHA256 = (
    "f8c9e326646e16e2c4bcf5eba4a6505494a5044491bc70127d5b0a1603150a3b"
)
NSC_020_POLICY_SHA256 = (
    "52da0aab0e66829fd6bfa4a90455c440f74676c5fec1364f9d59f45e6cf8111f"
)

PARENT_ID = "NSC-911"
ALPHA = "repo-file:Assets/Fixture/Alpha.cs"
ALPHA_META = "repo-file:Assets/Fixture/Alpha.cs.meta"
BETA = "repo-file:Assets/Fixture/Beta.cs"
BETA_META = "repo-file:Assets/Fixture/Beta.cs.meta"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def rejects(action, expected: type[BaseException]) -> BaseException:
    try:
        action()
    except expected as exc:
        return exc
    raise AssertionError(f"expected {expected.__name__}")


def parent_contract(**changes: Any) -> dict[str, Any]:
    """One machine-approved decomposition parent owning two disjoint file pairs."""

    value: dict[str, Any] = {
        "schema_version": "2.0",
        "id": PARENT_ID,
        "contract_revision": 1,
        "contract_disposition": "active",
        "title": "Fixture Parent: Split Alpha and Beta",
        "reconciliation_key": "fixture-parent-alpha-beta",
        "kind": "implementation",
        "execution_scope": "needs_execution_decomposition",
        "decomposition_state": "concrete",
        "parent": "NSC-001",
        "depends_on": [],
        "exclusive_resources": [ALPHA, ALPHA_META, BETA, BETA_META],
        "acceptance_criteria": [],
        "completion_gates": [],
        "downstream_integration_obligations": [],
        "provenance": {"origin": "fixture", "gauntlet_id": "fixture-gauntlet-v1"},
    }
    value.update(changes)
    return value


def variant(resources: list[str], filter_name: str) -> dict[str, Any]:
    return {
        "required_exclusive_resources": list(resources),
        "required_test_platforms": ["EditMode"],
        "test_filters": {"EditMode": f"NoSafeCircle.Fixture.Tests.{filter_name}"},
    }


def template_for(task: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "parent_task_contract_sha256": parent_semantic_hash(task),
        "validation_variants": variants,
        "authority": DECOMPOSITION_TEMPLATE_AUTHORITY,
    }


def policy_document(templates: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "tasks": {},
        "decomposition_child_templates": {} if templates is None else templates,
    }


def workspace(
    tasks: list[dict[str, Any]], document: dict[str, Any]
) -> tempfile.TemporaryDirectory[str]:
    """Materialize one throwaway checkout with exact task contracts and a policy."""

    handle = tempfile.TemporaryDirectory(prefix="decomposition-policy-audit-")
    root = Path(handle.name)
    (root / "Tasks").mkdir(parents=True)
    for task in tasks:
        (root / "Tasks" / f"{task['id']}.yaml").write_text(
            json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    policy_path = root / VALIDATION_POLICY_RELATIVE
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    return handle


def healthy_case() -> tuple[dict[str, Any], dict[str, Any]]:
    task = parent_contract()
    document = policy_document(
        {
            PARENT_ID: template_for(
                task,
                [
                    variant([ALPHA, ALPHA_META], "AlphaTests"),
                    variant([BETA, BETA_META], "BetaTests"),
                ],
            )
        }
    )
    return task, document


# ------------------------------------- 1: the real committed policy document


def test_committed_policy_satisfies_the_decomposition_reader_schema() -> None:
    """The G12 regression, stated against the real committed file.

    `decomposition_validation_policy_for` demands the exact three-key document.
    Before the migration the committed file had two keys, so EVERY decomposition
    parent resolution raised "schema is unsupported" -- a document-level failure
    that says nothing about the parent and cannot be repaired by adding a
    template. It must now fail, if at all, only for the exact parent asked about.
    """

    document = read_policy_document(ROOT)
    require(
        set(document) == {"schema_version", "tasks", "decomposition_child_templates"},
        str(sorted(document)),
    )
    require(document["schema_version"] == "1.0", str(document["schema_version"]))
    require(
        isinstance(document["decomposition_child_templates"], dict),
        str(type(document["decomposition_child_templates"])),
    )
    blocked = rejects(
        lambda: decomposition_validation_policy_for(
            ROOT, {"id": "NSC-014"}, parent_semantic_hash="a" * 64
        ),
        DownstreamPipelineError,
    )
    require(
        "schema is unsupported" not in str(blocked),
        f"a decomposition parent still fails on the document schema: {blocked}",
    )
    require("NSC-014" in str(blocked), str(blocked))


def test_committed_policy_audits_clean_against_the_committed_graph() -> None:
    tasks = read_committed_tasks(ROOT)
    policy = read_policy_document(ROOT)
    expected_eligible = sorted(
        task_id
        for task_id, task in tasks.items()
        if is_decomposition_eligible_parent(task)
    )
    expected_required = sorted(
        task_id
        for task_id, task in tasks.items()
        if requires_decomposition_child_template(task)
    )
    expected_templates = sorted(policy["decomposition_child_templates"])
    receipt = audit_decomposition_policy(ROOT)
    require(
        receipt["templates_required"] == expected_required,
        str(receipt["templates_required"]),
    )
    require(
        [item["parent_task_id"] for item in receipt["templates_audited"]]
        == expected_templates,
        str(receipt["templates_audited"]),
    )
    require(receipt["committed_task_count"] >= 60, str(receipt))
    eligible = receipt["eligible_decomposition_parents"]
    require(eligible == expected_eligible, str(eligible))
    for task_id in eligible:
        require(is_decomposition_eligible_parent(tasks[task_id]), task_id)
        require(
            requires_decomposition_child_template(tasks[task_id])
            == (task_id in expected_required),
            f"{task_id} requirement classification drifted from the exact graph",
        )


# --------------------------------------------- 10: ordinary tasks are unchanged


def test_ordinary_concrete_task_resolution_is_byte_identical() -> None:
    """Guard: the migration must be invisible to every ordinary concrete task."""

    policy = copy.deepcopy(read_policy_document(ROOT))
    entries = policy["tasks"]
    require(bool(entries), "committed policy has no ordinary task entries")
    baseline = copy.deepcopy(policy)
    baseline.pop("decomposition_child_templates")
    with tempfile.TemporaryDirectory() as text:
        policy_path = Path(text) / VALIDATION_POLICY_RELATIVE
        policy_path.parent.mkdir(parents=True, exist_ok=True)

        def resolve(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
            policy_path.write_text(
                json.dumps(document, indent=2) + "\n", encoding="utf-8"
            )
            resolved: dict[str, dict[str, Any]] = {}
            for task_id, entry in entries.items():
                plan = validation_plan_for(
                    Path(text),
                    {
                        "task_id": task_id,
                        "task_contract_sha256": entry["task_contract_sha256"],
                    },
                )
                require(plan is not None, task_id)
                require("inherited_from_decomposition" not in plan, str(plan))
                resolved[task_id] = plan
            return resolved

        before = resolve(baseline)
        after = resolve(policy)
    require(before == after, "decomposition template map changed ordinary resolution")

    # Preserve the exact historical production guards when this checkout still
    # carries those exact contract revisions. Rehearsal repositories may carry
    # intentionally different NSC-020/NSC-042 contracts and policy identities.
    for task_id, contract_hash, expected in (
        ("NSC-042", NSC_042_CONTRACT_SHA256, NSC_042_POLICY_SHA256),
        ("NSC-020", NSC_020_CONTRACT_SHA256, NSC_020_POLICY_SHA256),
    ):
        entry = entries.get(task_id)
        if not isinstance(entry, dict) or entry.get("task_contract_sha256") != contract_hash:
            continue
        require(
            after[task_id]["policy_sha256"] == expected,
            f"{task_id}: {after[task_id]['policy_sha256']}",
        )


# --------------------------------------------------- 2: missing template


def test_a_selectable_machine_approved_parent_must_have_a_template() -> None:
    task, _document = healthy_case()
    with workspace([task], policy_document()) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("no child template" in str(blocked), str(blocked))
        require(PARENT_ID in str(blocked), str(blocked))
    # The same parent, human-approved, needs no template at all.
    human = parent_contract(provenance={"origin": "fixture"})
    with workspace([human], policy_document()) as text:
        receipt = audit_decomposition_policy(Path(text))
        require(receipt["templates_required"] == [], str(receipt))


# ------------------------------------------------ 3: orphan / extra template


def test_a_template_cannot_name_an_unknown_inactive_or_ineligible_parent() -> None:
    task, document = healthy_case()
    cases = (
        ([], "not in the committed graph"),
        ([parent_contract(contract_disposition="cancelled")], "inactive parent"),
        ([parent_contract(execution_scope="single_agent")], "ineligible parent"),
        ([parent_contract(decomposition_state="coarse")], "ineligible parent"),
        ([parent_contract(kind="feature")], "ineligible parent"),
        ([parent_contract(provenance={"origin": "fixture"})], "not machine-approved"),
    )
    for tasks, expected in cases:
        with workspace(tasks, document) as text:
            blocked = rejects(
                lambda text=text: audit_decomposition_policy(Path(text)),
                ValidationPolicyAuditError,
            )
            require(expected in str(blocked), f"{expected!r} not in {blocked}")
    # A template key that is not one exact task ID never reaches the graph check.
    stray = policy_document({"not-a-task": document["decomposition_child_templates"][PARENT_ID]})
    with workspace([task], stray) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("not one exact task ID" in str(blocked), str(blocked))


# ------------------------------------------------------- 4: stale parent hash


def test_a_template_bound_to_a_drifted_parent_contract_is_stale() -> None:
    task, document = healthy_case()
    with workspace([task], document) as text:
        require(audit_decomposition_policy(Path(text))["templates_audited"], "healthy case failed")
    # Editing the contract without re-binding the template must fail closed.
    drifted = parent_contract(contract_revision=2)
    with workspace([drifted], document) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("is stale" in str(blocked), str(blocked))
        require(parent_semantic_hash(drifted) in str(blocked), str(blocked))
    # A template that simply asserts a wrong hash is equally stale.
    wrong = copy.deepcopy(document)
    wrong["decomposition_child_templates"][PARENT_ID]["parent_task_contract_sha256"] = "b" * 64
    with workspace([task], wrong) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("is stale" in str(blocked), str(blocked))


# ----------------------------------------- 5: empty / duplicate / malformed


def test_empty_duplicate_and_malformed_variants_fail_closed() -> None:
    task, document = healthy_case()

    def mutated(mutate) -> dict[str, Any]:
        value = copy.deepcopy(document)
        mutate(value["decomposition_child_templates"][PARENT_ID])
        return value

    alpha = variant([ALPHA, ALPHA_META], "AlphaTests")
    beta = variant([BETA, BETA_META], "BetaTests")
    cases = (
        (lambda entry: entry.update(validation_variants=[]), "no variants"),
        (
            lambda entry: entry.update(validation_variants=[alpha, copy.deepcopy(alpha)]),
            "duplicate variants",
        ),
        (
            lambda entry: entry.update(validation_variants=[{**alpha, "extra": 1}, beta]),
            "invalid variant fields",
        ),
        (
            lambda entry: entry.update(
                validation_variants=[{**alpha, "required_test_platforms": ["Runtime"]}, beta]
            ),
            "invalid variant values",
        ),
        (
            lambda entry: entry.update(
                validation_variants=[
                    {**alpha, "test_filters": {"PlayMode": "X"}},
                    beta,
                ]
            ),
            "invalid variant values",
        ),
        (
            lambda entry: entry.update(
                validation_variants=[{**alpha, "required_exclusive_resources": []}, beta]
            ),
            "invalid variant values",
        ),
        (lambda entry: entry.pop("authority"), "invalid fields"),
        (
            lambda entry: entry.update(authority="committed_task_specific_authoritative_validation_policy"),
            "invalid authority",
        ),
        (
            lambda entry: entry.update(
                validation_variants=[
                    variant([ALPHA_META, ALPHA], "AlphaTests"),
                    beta,
                ]
            ),
            "unsorted exclusive resources",
        ),
        (
            lambda entry: entry.update(
                validation_variants=[
                    variant([f" {ALPHA}", ALPHA_META], "AlphaTests"),
                    beta,
                ]
            ),
            "unnormalized exclusive resource",
        ),
        # The reader sorts variants before hashing, so a file committed in
        # another order still resolves -- to a policy_sha256 its own bytes do
        # not show. The committed order must therefore be the canonical one.
        (
            lambda entry: entry.update(validation_variants=[beta, alpha]),
            "not in canonical order",
        ),
    )
    for mutate, expected in cases:
        document_case = mutated(mutate)
        with workspace([task], document_case) as text:
            blocked = rejects(
                lambda text=text: audit_decomposition_policy(Path(text)),
                ValidationPolicyAuditError,
            )
            require(expected in str(blocked), f"{expected!r} not in {blocked}")


# ------------------------------------------ 6: overlapping / partial partition


def test_overlapping_or_partial_child_resource_partitions_fail_closed() -> None:
    task, _document = healthy_case()
    overlapping = policy_document(
        {
            PARENT_ID: template_for(
                task,
                [
                    variant([ALPHA, ALPHA_META], "AlphaTests"),
                    variant([ALPHA_META, BETA, BETA_META], "BetaTests"),
                ],
            )
        }
    )
    with workspace([task], overlapping) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("variants overlap on" in str(blocked), str(blocked))
        require(ALPHA_META in str(blocked), str(blocked))

    partial = policy_document(
        {PARENT_ID: template_for(task, [variant([ALPHA, ALPHA_META], "AlphaTests")])}
    )
    with workspace([task], partial) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("do not partition" in str(blocked), str(blocked))
        require(BETA in str(blocked), str(blocked))

    unknown = policy_document(
        {
            PARENT_ID: template_for(
                task,
                [
                    variant([ALPHA, ALPHA_META], "AlphaTests"),
                    variant([BETA, BETA_META], "BetaTests"),
                    variant(["repo-file:Assets/Fixture/Gamma.cs"], "GammaTests"),
                ],
            )
        }
    )
    with workspace([task], unknown) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("do not partition" in str(blocked), str(blocked))
        require("unknown=" in str(blocked), str(blocked))


# ----------------------------- 7: an applied decomposition keeps its template


def applied_case() -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Return the graph exactly as `graph_delta` leaves it after one apply.

    Applying a decomposition rewrites its parent to kind=feature,
    execution_scope=not_applicable, decomposition_state=decomposed, bumps
    contract_revision, and empties exclusive_resources. The template stays
    committed because the two new children inherit their test plan through it.
    """

    original = parent_contract()
    historical = parent_semantic_hash(original)
    decomposed = parent_contract(
        contract_revision=2,
        kind="feature",
        execution_scope="not_applicable",
        decomposition_state="decomposed",
        exclusive_resources=[],
        decomposition_children=["NSC-912", "NSC-913"],
    )

    def child(task_id: str, resources: list[str]) -> dict[str, Any]:
        return parent_contract(
            id=task_id,
            kind="implementation",
            execution_scope="single_agent",
            decomposition_state="concrete",
            exclusive_resources=list(resources),
            parent=PARENT_ID,
            reconciliation_key=f"fixture-child-{task_id.lower()}",
            provenance={
                "origin": "progressive_decomposition",
                "parent_task_id": PARENT_ID,
                "parent_contract_revision": 1,
                "parent_contract_sha256": historical,
                "graph_delta_plan_id": "GDP-" + "a" * 64,
            },
        )

    document = policy_document(
        {
            PARENT_ID: {
                "parent_task_contract_sha256": historical,
                "validation_variants": [
                    variant([ALPHA, ALPHA_META], "AlphaTests"),
                    variant([BETA, BETA_META], "BetaTests"),
                ],
                "authority": DECOMPOSITION_TEMPLATE_AUTHORITY,
            }
        }
    )
    tasks = [
        decomposed,
        child("NSC-912", [ALPHA, ALPHA_META]),
        child("NSC-913", [BETA, BETA_META]),
    ]
    return tasks, document, historical


def test_an_applied_decomposition_keeps_its_template_provable() -> None:
    """The template outlives the assignment, because its children still read it.

    A whole-map audit that re-bound every template to the CURRENT parent contract
    would reject its own entry the moment the decomposition it exists for is
    applied -- permanently disabling every later decomposition, including the
    remaining parents of a multi-wave gauntlet. The retained binding is proven
    against the parent contract the children record instead.
    """

    tasks, document, historical = applied_case()
    with workspace(tasks, document) as text:
        receipt = audit_decomposition_policy(Path(text))
        entry = receipt["templates_audited"][0]
        require(entry["parent_task_id"] == PARENT_ID, str(entry))
        require(entry["parent_decomposed"] is True, str(entry))
        require(entry["parent_contract_sha256"] == historical, str(entry))
        # A decomposed parent no longer requires a template; it retains one.
        require(receipt["templates_required"] == [], str(receipt["templates_required"]))
        require(
            receipt["eligible_decomposition_parents"] == [],
            str(receipt["eligible_decomposition_parents"]),
        )
    # And an unrelated candidate's preflight is not poisoned by the retained
    # template. Before the lifecycle split, the applied entry made every
    # decomposition preflight in the repository fail forever.
    fresh = parent_contract(
        id="NSC-950",
        reconciliation_key="fixture-fresh",
        provenance={"origin": "fixture"},
    )
    with workspace(tasks + [fresh], document) as text:
        receipt = decomposition_preflight(Path(text), "NSC-950", fresh)
        require(
            [item["parent_task_id"] for item in receipt["templates_audited"]] == [PARENT_ID],
            str(receipt),
        )
        require(receipt["templates_required"] == [], str(receipt))

    # The retained binding is still proven, not merely tolerated.
    stale_children = [
        task if task["id"] == PARENT_ID else {**task, "provenance": {**task["provenance"], "parent_contract_sha256": "c" * 64}}
        for task in tasks
    ]
    with workspace(stale_children, document) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("is stale" in str(blocked), str(blocked))

    orphaned = [task for task in tasks if task["id"] == PARENT_ID]
    with workspace(orphaned, document) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("no committed children" in str(blocked), str(blocked))

    mismatched = [
        {**task, "exclusive_resources": [ALPHA]} if task["id"] == "NSC-912" else task
        for task in tasks
    ]
    with workspace(mismatched, document) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("do not match its committed children" in str(blocked), str(blocked))

    disagreeing = [
        task if task["id"] != "NSC-913" else {**task, "provenance": {**task["provenance"], "parent_contract_sha256": "d" * 64}}
        for task in tasks
    ]
    with workspace(disagreeing, document) as text:
        blocked = rejects(
            lambda: audit_decomposition_policy(Path(text)), ValidationPolicyAuditError
        )
        require("disagree about the parent contract" in str(blocked), str(blocked))


# ------------------------------------------------------- 8: the one generator


def test_the_generated_synthetic_gauntlet_policy_passes_the_audit() -> None:
    """`prepare_synthetic_gauntlet.py` stays the single template generator.

    The audit is applied to that generator's real output, so the two can never
    disagree about what a valid template is, and nothing here has to author a
    second template-construction algorithm to test against.
    """

    with tempfile.TemporaryDirectory(prefix="decomposition-policy-gauntlet-") as text:
        target = Path(text) / "source"
        _copy_graph(target)
        bundle, summary = build_bundle(target)
        original_run = gauntlet._run
        gauntlet._run = lambda _source, *_command: ""
        try:
            gauntlet.apply_bundle(target, bundle)
        finally:
            gauntlet._run = original_run
        document = json.loads((target / POLICY_RELATIVE).read_text(encoding="utf-8"))
        receipt = audit_decomposition_policy(target, document=document)
        parents = sorted(summary["decomposition_parents"])
        require(receipt["templates_required"] == parents, str(receipt["templates_required"]))
        require(
            [item["parent_task_id"] for item in receipt["templates_audited"]] == parents,
            str(receipt["templates_audited"]),
        )
        require(
            all(item["variant_count"] == 2 for item in receipt["templates_audited"]),
            str(receipt["templates_audited"]),
        )
        # Removing one generated template is exactly the drift the audit exists for.
        broken = copy.deepcopy(document)
        del broken["decomposition_child_templates"][parents[0]]
        blocked = rejects(
            lambda: audit_decomposition_policy(target, document=broken),
            ValidationPolicyAuditError,
        )
        require(parents[0] in str(blocked), str(blocked))


def _copy_graph(target: Path) -> None:
    """Copy the exact committed graph inputs the generator reads."""

    target.mkdir(parents=True, exist_ok=True)
    for relative in (
        "Tasks",
        "Pipeline/TaskGraph/WORK_ID_MAP.json",
        "Pipeline/TaskGraph/PROJECT_REQUIREMENTS.yaml",
        "Pipeline/TaskGraph/RESOURCE_GROUPS.yaml",
        "Pipeline/TaskGraph/BOOTSTRAP_PERSISTED.json",
        VALIDATION_POLICY_RELATIVE,
    ):
        source = ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            for item in sorted(source.iterdir()):
                if item.is_file():
                    (destination / item.name).parent.mkdir(parents=True, exist_ok=True)
                    (destination / item.name).write_bytes(item.read_bytes())
        else:
            destination.write_bytes(source.read_bytes())


# --------------------------------------------- 9: bound commit, never main


def test_a_bound_source_commit_is_audited_at_that_commit() -> None:
    """Historical replay must read the policy and the parent contract at its commit.

    A decomposition authorized at commit A must keep proving against commit A's
    policy and contract even after main has moved. Auditing the working tree
    would silently substitute current main and reject a plan that was valid when
    it was authorized.
    """

    task, document = healthy_case()
    with workspace([task], document) as text:
        root = Path(text)
        _git(root, "init", "-b", "main")
        _git(root, "config", "user.name", "Policy Audit Fixture")
        _git(root, "config", "user.email", "policy-audit@nosafecircle.invalid")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "authorized state")
        authorized = _git(root, "rev-parse", "HEAD")

        # Main moves on: the contract is revised and the template is not re-bound.
        drifted = parent_contract(contract_revision=2)
        (root / "Tasks" / f"{PARENT_ID}.yaml").write_text(
            json.dumps(drifted, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / VALIDATION_POLICY_RELATIVE).write_text(
            json.dumps(policy_document(), indent=2) + "\n", encoding="utf-8"
        )
        _git(root, "add", ".")
        _git(root, "commit", "-m", "moved main")
        moved = _git(root, "rev-parse", "HEAD")
        require(moved != authorized, "fixture did not move HEAD")

        # The bound commit still proves. Current main is a different question.
        historical = audit_decomposition_policy(root, commit=authorized)
        require(
            [item["parent_task_id"] for item in historical["templates_audited"]] == [PARENT_ID],
            str(historical),
        )
        require(historical["source_commit"] == authorized, str(historical))
        require(
            historical["templates_audited"][0]["parent_contract_sha256"]
            == parent_semantic_hash(task),
            str(historical),
        )
        # Current main genuinely fails the same audit, which is exactly why the
        # bound commit has to be stated rather than assumed: auditing "now" would
        # have rejected an authorization that was and remains valid.
        current = rejects(
            lambda: audit_decomposition_policy(root), ValidationPolicyAuditError
        )
        require("no child template" in str(current), str(current))
        require(PARENT_ID in str(current), str(current))
        blocked = rejects(
            lambda: audit_decomposition_policy(root, commit="9" * 40),
            ValidationPolicyAuditError,
        )
        require("could not be read" in str(blocked), str(blocked))
        rejects(
            lambda: audit_decomposition_policy(root, commit="HEAD"),
            ValidationPolicyAuditError,
        )


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


# ------------------------------------- preflight composition (offer boundary)


def test_the_preflight_runs_selection_rules_and_the_policy_audit_together() -> None:
    task, document = healthy_case()
    with workspace([task], document) as text:
        require(
            decomposition_preflight(Path(text), PARENT_ID, task)["templates_audited"],
            "healthy preflight produced no audited template",
        )
    from Pipeline.TaskDecomposition.context_builder import DecompositionPreflightError

    # A selection failure and a policy failure are the same exception family, so
    # the scheduler's existing "do not offer" handler covers both -- but they are
    # different facts and each half must be able to block on its own.
    with workspace([task], policy_document()) as text:
        blocked = rejects(
            lambda: decomposition_preflight(Path(text), PARENT_ID, task),
            DecompositionPreflightError,
        )
        require(isinstance(blocked, ValidationPolicyAuditError), str(type(blocked)))
        require("no child template" in str(blocked), str(blocked))
    # The selection half must block against a repository whose policy audits
    # CLEAN, or this proves nothing about the selection rules at all.
    already_concrete = parent_contract(
        id="NSC-912", execution_scope="single_agent", decomposition_state="concrete"
    )
    with workspace([task, already_concrete], document) as text:
        require(
            audit_decomposition_policy(Path(text))["templates_audited"],
            "the selection sub-case needs a repository whose policy audits clean",
        )
        blocked = rejects(
            lambda: decomposition_preflight(Path(text), "NSC-912", already_concrete),
            DecompositionPreflightError,
        )
        require(
            not isinstance(blocked, ValidationPolicyAuditError),
            f"the policy audit, not the selection rules, produced the block: {blocked}",
        )
        require("already concrete single_agent work" in str(blocked), str(blocked))


TESTS = (
    test_committed_policy_satisfies_the_decomposition_reader_schema,
    test_committed_policy_audits_clean_against_the_committed_graph,
    test_ordinary_concrete_task_resolution_is_byte_identical,
    test_a_selectable_machine_approved_parent_must_have_a_template,
    test_a_template_cannot_name_an_unknown_inactive_or_ineligible_parent,
    test_a_template_bound_to_a_drifted_parent_contract_is_stale,
    test_empty_duplicate_and_malformed_variants_fail_closed,
    test_overlapping_or_partial_child_resource_partitions_fail_closed,
    test_an_applied_decomposition_keeps_its_template_provable,
    test_the_generated_synthetic_gauntlet_policy_passes_the_audit,
    test_a_bound_source_commit_is_audited_at_that_commit,
    test_the_preflight_runs_selection_rules_and_the_policy_audit_together,
)


def main(argv: list[str] | None = None) -> int:
    selected = set(argv or [])
    for test in TESTS:
        if selected and test.__name__ not in selected:
            continue
        test()
        print(f"PASS {test.__name__}")
    print(
        "TaskReviewAgent decomposition policy audit smoke tests: "
        f"PASS ({len(TESTS)} tests)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
