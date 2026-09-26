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

import ast
import copy
import re
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

from Pipeline.TaskReviewAgent.committed_tasks import load_committed_task  # noqa: E402
from Pipeline.TaskReviewAgent.decomposition_policy_audit import (  # noqa: E402
    DECOMPOSITION_TEMPLATE_AUTHORITY,
    POLICY_CHILD_UNPINNED,
    POLICY_PIN_STALE,
    POLICY_UNREADABLE,
    VALIDATION_POLICY_RELATIVE,
    ValidationPolicyAuditError,
    REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY,
    REBIND_SKIPPED_NOT_REWRITTEN,
    REBIND_SKIPPED_PRE_EXISTING,
    applied_policy_findings,
    apply_pin_rebind,
    audit_decomposition_policy,
    describe_policy_findings,
    describe_pin_rebind,
    plan_pin_rebind,
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
    build_validation_repair_bundle,
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


def test_committed_direct_policies_match_exact_task_contract_bytes() -> None:
    """Every direct policy must remain bound to its exact committed task bytes."""

    document = read_policy_document(ROOT)
    tasks = read_committed_tasks(ROOT)
    for task_id in sorted(document["tasks"]):
        require(
            task_id in tasks,
            f"direct validation policy names unknown task {task_id}",
        )
        task = load_committed_task(ROOT, task_id)
        plan = validation_plan_for(ROOT, task)
        require(
            plan is not None,
            f"direct validation policy did not resolve for {task_id}",
        )
        require(
            plan["task_contract_sha256"] == task["task_contract_sha256"],
            f"direct validation policy for {task_id} drifted from its task contract",
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
        synthetic_paths = [
            target / "Tasks" / f"NSC-{number:03d}.yaml"
            for number in range(gauntlet.GAUNTLET_FIRST_ID, 991)
        ]
        if all(path.is_file() for path in synthetic_paths):
            bundle, _summary = build_validation_repair_bundle(target)
        else:
            require(
                not any(path.is_file() for path in synthetic_paths),
                "fixture has only a partial synthetic gauntlet",
            )
            bundle, _summary = build_bundle(target)
        original_run = gauntlet._run
        gauntlet._run = lambda _source, *_command: ""
        try:
            gauntlet.apply_bundle(target, bundle)
        finally:
            gauntlet._run = original_run
        document = json.loads((target / POLICY_RELATIVE).read_text(encoding="utf-8"))
        receipt = audit_decomposition_policy(target, document=document)
        parents = sorted(document["decomposition_child_templates"])
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


def _write_graph(root: Path, tasks: list[dict[str, Any]], document: dict[str, Any]) -> None:
    (root / "Tasks").mkdir(parents=True, exist_ok=True)
    for task in tasks:
        (root / "Tasks" / f"{task['id']}.yaml").write_text(
            json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    policy_path = root / VALIDATION_POLICY_RELATIVE
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _commit_all(root: Path, message: str) -> str:
    _git(root, "add", "--all")
    _git(root, "-c", "user.name=No Safe Circle TaskReviewAgent",
         "-c", "user.email=task-review-agent@nosafecircle.invalid",
         "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def test_an_inherited_child_policy_survives_a_clone_to_receiver_merge() -> None:
    """A decomposition applied in an isolated clone keeps its children's policy.

    The D1C commit is made in a clone while the receiving checkout gains an
    unrelated policy entry; after an ordinary merge each child must resolve to
    the same non-None plan on both sides, still bound to the original parent's
    semantic hash. A relevant template change on the receiver is still refused.
    """

    applied_tasks, document, historical = applied_case()
    with tempfile.TemporaryDirectory(prefix="decomposition-policy-transfer-") as text:
        root = Path(text)
        receiver = root / "receiver"
        receiver.mkdir()
        _git(receiver, "init", "-q")
        _write_graph(receiver, [parent_contract()], document)
        _commit_all(receiver, "fixture: concrete parent with its child template")
        clone = root / "clone"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(receiver), str(clone)],
                       check=True, capture_output=True)
        _write_graph(clone, applied_tasks, document)
        d1c = _commit_all(clone, "fixture: D1C applied in the isolated clone")

        unrelated = copy.deepcopy(document)
        unrelated["tasks"]["NSC-977"] = {"note": "an unrelated direct policy row"}
        _write_graph(receiver, [parent_contract()], unrelated)
        _commit_all(receiver, "fixture: unrelated policy change on the receiver")
        _git(receiver, "fetch", "-q", str(clone), d1c)
        _git(receiver, "-c", "user.name=No Safe Circle TaskReviewAgent",
             "-c", "user.email=task-review-agent@nosafecircle.invalid",
             "merge", "--no-ff", "-q", "-m", "fixture: land the clone D1C", d1c)
        merged = _git(receiver, "rev-parse", "HEAD")

        for child_id in ("NSC-912", "NSC-913"):
            candidate = validation_plan_for(
                clone, load_committed_task(clone, child_id, commit=d1c))
            landed = validation_plan_for(
                receiver, load_committed_task(receiver, child_id, commit=merged))
            require(candidate is not None, f"{child_id} resolved no plan on the clone")
            require(candidate == landed, f"{child_id}: {candidate} != {landed}")
            provenance = load_committed_task(receiver, child_id, commit=merged)["provenance"]
            require(provenance["parent_contract_sha256"] == historical, str(provenance))

        drifted = copy.deepcopy(unrelated)
        drifted["decomposition_child_templates"][PARENT_ID][
            "parent_task_contract_sha256"] = "e" * 64
        (receiver / VALIDATION_POLICY_RELATIVE).write_text(
            json.dumps(drifted, indent=2) + "\n", encoding="utf-8")
        blocked = rejects(
            lambda: validation_plan_for(
                receiver, load_committed_task(receiver, "NSC-912", commit=merged)),
            DownstreamPipelineError,
        )
        require("is stale" in str(blocked), str(blocked))


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


# ------------------------------------ 16: what an apply leaves behind in the policy
#
# Applying a decomposition rewrites contracts and writes nothing to the policy, so it
# silently invalidates every pin it rewrote and gives its new children no entry.
# `test_committed_direct_policies_match_exact_task_contract_bytes` above is the check
# that catches the first half -- hours later, on CI -- and it CANNOT catch the second
# half at all: it iterates `document["tasks"]`, so a child with no entry is not in the
# loop. An assertion over the entries that exist can never see the entry nobody wrote.

APPLY_PARENT = "NSC-921"
APPLY_BYSTANDER = "NSC-922"
APPLY_UNTOUCHED = "NSC-923"
APPLY_CHILDREN = ("NSC-924", "NSC-925")


def _pinned_entry(sha256: str) -> dict[str, Any]:
    return {
        "task_contract_sha256": sha256,
        "required_test_platforms": ["EditMode"],
        "test_filters": {"EditMode": "NoSafeCircle.Fixture.Tests.Editor.PinnedTests"},
        "authority": "committed_task_specific_authoritative_validation_policy",
    }


def _plain_task(task_id: str, revision: int, **extra: Any) -> dict[str, Any]:
    task = {
        "id": task_id,
        "schema_version": "1.0",
        "title": f"fixture {task_id}",
        "kind": "implementation",
        "contract_disposition": "active",
        "contract_revision": revision,
        "exclusive_resources": [f"repo-file:Assets/Fixture/{task_id}.cs"],
    }
    task.update(extra)
    return task


def _write_task(root: Path, task: dict[str, Any]) -> None:
    (root / "Tasks").mkdir(parents=True, exist_ok=True)
    (root / "Tasks" / f"{task['id']}.yaml").write_bytes(
        (json.dumps(task, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _write_policy(root: Path, entries: dict[str, Any]) -> None:
    path = root / VALIDATION_POLICY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps({
            "schema_version": "1.0",
            "tasks": entries,
            "decomposition_child_templates": {},
        }, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _apply_fixture(stack: Path, *, pin_parent: bool = True, keep_policy: bool = True,
                   pre_stale: str | None = None) -> tuple[str, str]:
    """Build before/after commits shaped like a real decomposition apply.

    Three commits, because a pin can only be written once its contract's committed
    bytes exist: contracts, then the policy that pins them, then the apply. The pins
    are read back with `load_committed_task` rather than computed here, so the fixture
    cannot disagree with the reader about what "the committed bytes" are -- and
    `core.autocrlf` is pinned off so the committed bytes are the bytes written.
    """

    _git(stack, "init", "-b", "master")
    _git(stack, "config", "user.name", "Policy Audit Fixture")
    _git(stack, "config", "user.email", "policy-audit@nosafecircle.invalid")
    _git(stack, "config", "core.autocrlf", "false")
    for task_id in (APPLY_PARENT, APPLY_BYSTANDER, APPLY_UNTOUCHED):
        _write_task(stack, _plain_task(task_id, 1))
    _git(stack, "add", ".")
    _git(stack, "commit", "-q", "-m", "contracts")
    contracts = _git(stack, "rev-parse", "HEAD")

    entries = {}
    for task_id in (APPLY_PARENT, APPLY_BYSTANDER, APPLY_UNTOUCHED):
        if task_id == APPLY_PARENT and not pin_parent:
            continue
        exact = load_committed_task(stack, task_id, commit=contracts)["task_contract_sha256"]
        entries[task_id] = _pinned_entry("0" * 64 if task_id == pre_stale else exact)
    _write_policy(stack, entries)
    _git(stack, "add", ".")
    _git(stack, "commit", "-q", "-m", "policy pins the contracts")
    before = _git(stack, "rev-parse", "HEAD")

    # The apply: the parent is rewritten, every task that referenced it is
    # re-serialized, the children are created, and the policy is not touched.
    _write_task(stack, _plain_task(APPLY_PARENT, 2, decomposition_state="decomposed",
                                  decomposition_children=list(APPLY_CHILDREN)))
    _write_task(stack, _plain_task(APPLY_BYSTANDER, 2, depends_on=list(APPLY_CHILDREN)))
    for child_id in APPLY_CHILDREN:
        _write_task(stack, _plain_task(child_id, 1, parent=APPLY_PARENT))
    if not keep_policy:
        (stack / VALIDATION_POLICY_RELATIVE).unlink()
    _git(stack, "add", "--all")
    _git(stack, "commit", "-q", "-m", "apply the decomposition")
    return before, _git(stack, "rev-parse", "HEAD")


def _findings(root: Path, before: str, after: str) -> tuple[dict[str, Any], ...]:
    return applied_policy_findings(
        root, before_commit=before, after_commit=after,
        parent_task_id=APPLY_PARENT, child_task_ids=list(APPLY_CHILDREN),
    )


def _by_condition(findings, condition: str) -> list[dict[str, Any]]:
    return [item for item in findings if item["condition"] == condition]


def test_an_apply_names_the_parent_pin_it_broke() -> None:
    """The pin the apply invalidated is reported, and attributed to the apply."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        findings = _findings(root, before, after)
        stale = _by_condition(findings, POLICY_PIN_STALE)
        named = {item["task_id"] for item in stale}
        require(APPLY_PARENT in named, f"the parent's broken pin was not reported: {named}")
        parent = next(item for item in stale if item["task_id"] == APPLY_PARENT)
        require(parent["stale_before_this_apply"] is False,
                f"the parent pin was blamed on the wrong commit: {parent}")
        require(parent["rewritten_by_this_apply"] is True, str(parent))
        require("the decomposed parent" in parent["detail"], parent["detail"])
        require(APPLY_UNTOUCHED not in named,
                f"an entry the apply never touched was reported stale: {named}")


def test_an_apply_names_the_bystander_pins_it_broke_not_only_the_parent() -> None:
    """A task rewritten only because it referenced the parent is reported too.

    This is the half a parent-scoped fix would miss, and it is the majority of the
    real damage: measured on the two applies that caused this defect, `644e3c4f` broke
    NSC-007 (its parent) and NSC-098 (a bystander), and `b5c64602` broke NSC-099 alone
    while leaving its own parent's pin untouched because NSC-015 carries no entry. Two
    of the three broken pins belonged to tasks that were not being decomposed.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        stale = _by_condition(_findings(root, before, after), POLICY_PIN_STALE)
        named = {item["task_id"] for item in stale}
        require(APPLY_BYSTANDER in named,
                f"a rewritten bystander's broken pin was not reported: {named}")
        item = next(entry for entry in stale if entry["task_id"] == APPLY_BYSTANDER)
        require(item["rewritten_by_this_apply"] is True, str(item))
        require(item["stale_before_this_apply"] is False, str(item))
        require("referenced the parent" in item["detail"], item["detail"])


def test_a_pin_already_stale_before_the_apply_is_not_blamed_on_the_apply() -> None:
    """Pre-existing staleness is reported and explicitly not attributed to the apply.

    Both halves matter. Reporting it is right -- it is a real defect and this is the
    moment someone is looking. Attributing it to the apply would overstate the apply's
    damage, which is how a cause that accounts for part of a phenomenon gets published
    as the whole of it.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root, pre_stale=APPLY_UNTOUCHED)
        stale = _by_condition(_findings(root, before, after), POLICY_PIN_STALE)
        item = next((entry for entry in stale if entry["task_id"] == APPLY_UNTOUCHED), None)
        require(item is not None, f"a pre-existing stale pin went unreported: {stale}")
        require(item["stale_before_this_apply"] is True, str(item))
        require(item["rewritten_by_this_apply"] is False, str(item))
        require("did not cause it" in item["detail"], item["detail"])
        # And it must NOT stop there. "This apply did not cause it" is true and sends the
        # reader hunting a second cause class; traced across main's history every pin that
        # ever went stale was broken by a decomposition apply, so the finding has to say
        # the inherited case is a backlog of the same defect.
        require("BACKLOG OF THIS SAME DEFECT" in item["detail"], item["detail"])
        require("do not go looking outside the apply path" in item["detail"], item["detail"])
        broke = next(entry for entry in stale if entry["task_id"] == APPLY_PARENT)
        require("THIS APPLY BROKE IT" in broke["detail"], broke["detail"])
        require("BACKLOG" not in broke["detail"],
                "a pin this apply broke was described as inherited")
        parent = next(entry for entry in stale if entry["task_id"] == APPLY_PARENT)
        require(parent["stale_before_this_apply"] is False,
                "the apply's own damage was mislabelled as pre-existing")


def test_an_apply_names_every_child_it_left_unpinned() -> None:
    """A child with no entry is reported, which no assertion over the entries can do."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        unpinned = _by_condition(_findings(root, before, after), POLICY_CHILD_UNPINNED)
        require({item["task_id"] for item in unpinned} == set(APPLY_CHILDREN),
                f"the unpinned children were not reported: {unpinned}")
        for item in unpinned:
            require(item["parent_task_id"] == APPLY_PARENT, str(item))
            require("authored Unity test class names" in item["detail"], item["detail"])


def test_a_child_is_only_called_unpinned_when_its_parent_was_pinned() -> None:
    """No entry is the NORMAL case, so it is only a finding when coverage was lost.

    65 of the 128 committed contracts carry no policy entry and never needed one. A
    finding on every entry-less task would fire on the majority of the graph and
    train its reader to ignore it, so the condition is the narrower one that needs no
    authored value: the parent was pinned and the child is not.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root, pin_parent=False)
        findings = _findings(root, before, after)
        require(_by_condition(findings, POLICY_CHILD_UNPINNED) == [],
                f"an unpinned child was reported although nothing was pinned: {findings}")
        # The control: the same children ARE reported when the parent carries an entry,
        # so the empty result above is a decision and not a broken query.
    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        require(len(_by_condition(_findings(root, before, after), POLICY_CHILD_UNPINNED)) == 2,
                "the control did not reproduce the reported case")


def test_an_unreadable_policy_is_not_reported_as_a_consistent_one() -> None:
    """Nobody-could-look and nothing-is-wrong are different states.

    Both would otherwise return an empty finding list, and collapsing them is how an
    unchecked policy reads as a clean one -- the same defect as a container sweep that
    reports "nothing was orphaned" when in fact nothing could be enumerated.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root, keep_policy=False)
        findings = _findings(root, before, after)
        require(len(findings) == 1, f"expected exactly one finding, got {findings}")
        require(findings[0]["condition"] == POLICY_UNREADABLE, str(findings))
        require("nobody could look" not in describe_policy_findings(findings),
                "the one-line description should name the condition, not editorialise")
        require("policy_unreadable" in describe_policy_findings(findings),
                describe_policy_findings(findings))


def test_a_consistent_policy_says_so_rather_than_returning_silence() -> None:
    """An empty finding list must be describable as a positive statement."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, _after = _apply_fixture(root)
        # `before` against itself: nothing was rewritten and nothing is stale.
        findings = applied_policy_findings(
            root, before_commit=before, after_commit=before,
            parent_task_id=APPLY_PARENT, child_task_ids=[],
        )
        require(findings == (), f"a consistent policy produced findings: {findings}")
        described = describe_policy_findings(findings)
        require("no stale pin, no unpinned child" in described, described)


def test_the_stale_rule_is_the_one_every_candidate_validation_already_uses() -> None:
    """Pin the verdict against `validation_plan_for`, in the other module.

    A check whose expectations come from the artifact it checks is self-consistent by
    construction. So the authority for both conditions is the reader the pipeline
    already runs: it RAISES "authoritative validation policy for <id> is stale" for a
    drifted pin, and RETURNS None for a task with no entry and no inherited template.
    If either rule moves, this fails here rather than in production.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        findings = _findings(root, before, after)

        parent = load_committed_task(root, APPLY_PARENT, commit=after)
        refusal = rejects(lambda: validation_plan_for(root, parent), DownstreamPipelineError)
        require("is stale" in str(refusal), str(refusal))
        require(APPLY_PARENT in str(refusal), str(refusal))
        require(APPLY_PARENT in {item["task_id"] for item in
                                 _by_condition(findings, POLICY_PIN_STALE)},
                "the reader calls the parent stale and the findings do not")

        child = load_committed_task(root, APPLY_CHILDREN[0], commit=after)
        require(validation_plan_for(root, child) is None,
                "the reader resolved a plan for a child this fixture left unpinned")
        require(APPLY_CHILDREN[0] in {item["task_id"] for item in
                                      _by_condition(findings, POLICY_CHILD_UNPINNED)},
                "the reader gives that child no plan and the findings do not say so")

        # And the untouched entry still resolves, so the two rules above are
        # discriminating rather than refusing everything this fixture builds.
        untouched = load_committed_task(root, APPLY_UNTOUCHED, commit=after)
        plan = validation_plan_for(root, untouched)
        require(plan is not None and plan["task_id"] == APPLY_UNTOUCHED, str(plan))


def test_the_apply_computes_and_records_the_findings() -> None:
    """Pin the wiring, not just the helper.

    A helper nothing calls is a helper that reports nothing, and a whole-file revert
    would only ever produce an ImportError -- a failure with no assertion in it. This
    reads the apply's own syntax tree so that removing the call, or dropping the
    record field, fails on a sentence.
    """

    module = ast.parse(
        (ROOT / "Pipeline" / "AssistantControl" / "decomposition.py").read_text(
            encoding="utf-8"
        )
    )
    locked = next(
        (node for node in ast.walk(module)
         if isinstance(node, ast.FunctionDef) and node.name == "_apply_locked"),
        None,
    )
    require(locked is not None, "_apply_locked is gone from decomposition.py")
    called = {
        node.func.id for node in ast.walk(locked)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    require("applied_policy_findings" in called,
            "_apply_locked never computes the validation policy findings, so an apply"
            " still leaves a stale pin and an unpinned child unreported")
    updates = [
        node for node in ast.walk(locked)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
    ]
    recorded = {keyword.arg for node in updates for keyword in node.keywords}
    require("validation_policy_findings" in recorded,
            "the applied record does not carry validation_policy_findings, so the"
            " findings die with the process that computed them")
    require("describe_policy_findings" in called,
            "_apply_locked computes the findings and never renders them to a log")


# --------------------------------- 17: repairing the pins the apply itself broke
#
# Detection names the damage; this repairs the half that needs no authored value. The scope is
# deliberately narrower than "every stale pin": a pin that was already stale belongs to whoever
# revised that contract, and an apply that silently repaired it would hide a second writer's defect
# inside a decomposition's diff.


def _reasons(plan_or_result):
    return {item["task_id"]: item["reason"] for item in (plan_or_result.get("skipped") or [])}


def test_a_rebind_plan_covers_only_the_pins_this_apply_broke() -> None:
    """The plan takes the two pins this apply broke and refuses the rest, with reasons."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root, pre_stale=APPLY_UNTOUCHED)
        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        named = {item["task_id"] for item in plan["rebinds"]}
        require(named == {APPLY_PARENT, APPLY_BYSTANDER},
                f"the plan rebinds the wrong set: {named}")
        reasons = _reasons(plan)
        require(reasons.get(APPLY_UNTOUCHED) == REBIND_SKIPPED_PRE_EXISTING,
                f"a pre-existing stale pin was not left to its owner: {reasons}")
        for child_id in APPLY_CHILDREN:
            require(reasons.get(child_id) == REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY,
                    f"an unpinned child was not deferred for authored filters: {reasons}")
        for item in plan["rebinds"]:
            require(item["from"] != item["to"], str(item))
            require(re.fullmatch(r"[0-9a-f]{64}", item["to"]) is not None, str(item))


def test_a_rebind_commit_touches_only_the_policy() -> None:
    """One commit, one path. The apply's own commit is not amended and nothing else rides along."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        result = apply_pin_rebind(root, plan, message="policy: rebind the pins the apply broke")
        require(result["status"] == "rebound", str(result))
        require(result["commit"] != after, "the rebind did not create a commit")
        committed = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r",
                         result["commit"]).split()
        require(committed == [VALIDATION_POLICY_RELATIVE],
                f"the rebind commit touched {committed}")
        require(_git(root, "status", "--porcelain").strip() == "",
                "the rebind left the tree dirty")
        require(_git(root, "rev-parse", f"{result['commit']}^") == after,
                "the rebind commit does not sit directly on the apply")


def test_a_rebind_changes_nothing_but_the_named_pins() -> None:
    """Prove it by diffing the parsed documents, not by reading the diff."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        original = json.loads(
            (root / VALIDATION_POLICY_RELATIVE).read_bytes().decode("utf-8-sig")
        )
        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        apply_pin_rebind(root, plan, message="policy: rebind")
        rebound = json.loads(
            (root / VALIDATION_POLICY_RELATIVE).read_bytes().decode("utf-8-sig")
        )
        expected = copy.deepcopy(original)
        for item in plan["rebinds"]:
            expected["tasks"][item["task_id"]]["task_contract_sha256"] = item["to"]
        require(rebound == expected, "the rebound document differs beyond the named pins")
        require(set(rebound["tasks"]) == set(original["tasks"]),
                "the rebind added or removed an entry")
        for task_id, entry in rebound["tasks"].items():
            require(set(entry) == set(original["tasks"][task_id]),
                    f"the rebind changed {task_id}'s key set")


def test_after_a_rebind_the_reader_resolves_the_task_again() -> None:
    """The repair is proven by `validation_plan_for`, in the other module.

    Before the rebind that reader RAISES "is stale" for the parent; after it, it returns a plan
    whose pin is the contract's own. Asserting my own document is self-consistent would prove
    nothing -- the authority has to agree that the task is resolvable again.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        parent = load_committed_task(root, APPLY_PARENT, commit=after)
        stale = rejects(lambda: validation_plan_for(root, parent), DownstreamPipelineError)
        require("is stale" in str(stale), str(stale))

        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        apply_pin_rebind(root, plan, message="policy: rebind")

        resolved = validation_plan_for(root, parent)
        require(resolved is not None, "the reader still refuses the parent after the rebind")
        require(resolved["task_contract_sha256"] == parent["task_contract_sha256"],
                f"the reader resolved a different contract: {resolved}")
        # And the findings the guard produces are now empty for the pins it repaired.
        remaining = _findings(root, before, _git(root, "rev-parse", "HEAD"))
        still_stale = {item["task_id"] for item in remaining
                       if item["condition"] == POLICY_PIN_STALE}
        require(APPLY_PARENT not in still_stale and APPLY_BYSTANDER not in still_stale,
                f"the guard still reports repaired pins as stale: {still_stale}")


def test_a_rebind_refuses_a_dirty_source() -> None:
    """Committing from a dirty tree is how one writer's commit carries another's work."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        (root / "Tasks" / "NSC-926.yaml").write_bytes(b"{}\n")
        refusal = rejects(
            lambda: apply_pin_rebind(root, plan, message="policy: rebind"),
            ValidationPolicyAuditError,
        )
        require("must be clean" in str(refusal), str(refusal))
        require("NSC-926" in str(refusal), str(refusal))


def test_a_rebind_refuses_an_ambiguous_pin_instead_of_guessing() -> None:
    """A textual edit needs the old pin to occur exactly once, and says so when it does not."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        findings = _findings(root, before, after)
        plan = plan_pin_rebind(root, findings, commit=after)
        # Give a second entry the same pin, so the parent's old value appears twice.
        policy_path = root / VALIDATION_POLICY_RELATIVE
        document = json.loads(policy_path.read_bytes().decode("utf-8-sig"))
        parent_pin = document["tasks"][APPLY_PARENT]["task_contract_sha256"]
        document["tasks"][APPLY_UNTOUCHED]["task_contract_sha256"] = parent_pin
        _write_policy(root, document["tasks"])
        _git(root, "add", "--all")
        _git(root, "commit", "-q", "-m", "fixture: duplicate a pin")
        refusal = rejects(
            lambda: apply_pin_rebind(root, plan, message="policy: rebind"),
            ValidationPolicyAuditError,
        )
        require("occurs 2 times" in str(refusal), str(refusal))
        require("ambiguous" in str(refusal), str(refusal))
        # And it left the document alone rather than half-editing it.
        require(json.loads(policy_path.read_bytes().decode("utf-8-sig")) == document,
                "the refusal still modified the policy")


def test_a_plan_that_went_stale_refuses_rather_than_editing_the_wrong_field() -> None:
    """A plan is read at a commit; the write happens in the working tree. They can diverge.

    This is the one scenario that reaches the document-equality check, and it was found by removing
    that check and watching every test still pass. The construction is deliberate rather than
    natural: the parent's pin is changed and its OLD value is parked in another entry's `authority`,
    so the old value still occurs exactly once -- passing the ambiguity guard -- while no longer
    belonging to the entry the plan names. A textual edit would rewrite that `authority` field and
    leave the policy quietly wrong.
    """

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root)
        plan = plan_pin_rebind(root, _findings(root, before, after), commit=after)
        parent_rebind = next(item for item in plan["rebinds"] if item["task_id"] == APPLY_PARENT)

        policy_path = root / VALIDATION_POLICY_RELATIVE
        document = json.loads(policy_path.read_bytes().decode("utf-8-sig"))
        document["tasks"][APPLY_PARENT]["task_contract_sha256"] = "b" * 64
        document["tasks"][APPLY_UNTOUCHED]["authority"] = parent_rebind["from"]
        _write_policy(root, document["tasks"])
        _git(root, "add", "--all")
        _git(root, "commit", "-q", "-m", "fixture: the plan is now stale")
        committed = json.loads(policy_path.read_bytes().decode("utf-8-sig"))

        refusal = rejects(
            lambda: apply_pin_rebind(root, plan, message="policy: rebind a stale plan"),
            ValidationPolicyAuditError,
        )
        require("other than the named pins" in str(refusal), str(refusal))
        require(json.loads(policy_path.read_bytes().decode("utf-8-sig")) == committed,
                "the refusal left the policy modified")
        require(_git(root, "status", "--porcelain").strip() == "",
                "the refusal left the tree dirty")

def test_a_rebind_with_nothing_to_do_says_so() -> None:
    """An empty rebind is a positive statement, not silence."""

    with tempfile.TemporaryDirectory() as text:
        root = Path(text)
        before, after = _apply_fixture(root, pin_parent=False)
        empty = plan_pin_rebind(root, (), commit=before)
        require(empty["rebinds"] == [], str(empty))
        head_before_call = _git(root, "rev-parse", "HEAD")
        require(head_before_call == after, "the fixture did not leave HEAD at the apply")
        result = apply_pin_rebind(root, empty, message="unused")
        require(result["status"] == "nothing_to_rebind", str(result))
        require(result["commit"] is None, str(result))
        require(_git(root, "rev-parse", "HEAD") == head_before_call,
                "a no-op rebind still moved HEAD")
        described = describe_pin_rebind(result)
        require("no pin was rebound" in described, described)


TESTS = (
    test_committed_policy_satisfies_the_decomposition_reader_schema,
    test_committed_policy_audits_clean_against_the_committed_graph,
    test_committed_direct_policies_match_exact_task_contract_bytes,
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
    test_an_inherited_child_policy_survives_a_clone_to_receiver_merge,
    test_an_apply_names_the_parent_pin_it_broke,
    test_an_apply_names_the_bystander_pins_it_broke_not_only_the_parent,
    test_a_pin_already_stale_before_the_apply_is_not_blamed_on_the_apply,
    test_an_apply_names_every_child_it_left_unpinned,
    test_a_child_is_only_called_unpinned_when_its_parent_was_pinned,
    test_an_unreadable_policy_is_not_reported_as_a_consistent_one,
    test_a_consistent_policy_says_so_rather_than_returning_silence,
    test_the_stale_rule_is_the_one_every_candidate_validation_already_uses,
    test_the_apply_computes_and_records_the_findings,
    test_a_rebind_plan_covers_only_the_pins_this_apply_broke,
    test_a_rebind_commit_touches_only_the_policy,
    test_a_rebind_changes_nothing_but_the_named_pins,
    test_after_a_rebind_the_reader_resolves_the_task_again,
    test_a_rebind_refuses_a_dirty_source,
    test_a_rebind_refuses_an_ambiguous_pin_instead_of_guessing,
    test_a_rebind_with_nothing_to_do_says_so,
    test_a_plan_that_went_stale_refuses_rather_than_editing_the_wrong_field,
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
    from Pipeline.TaskReviewAgent.tests.synthetic_fixture_authority import run_with_synthetic_authority
    raise SystemExit(run_with_synthetic_authority(main, sys.argv[1:]))
