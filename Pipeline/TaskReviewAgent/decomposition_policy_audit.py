"""Deterministic repository-level audit of the committed decomposition child templates.

`Pipeline/TaskReviewAgent/authoritative_validation_policy.json` carries two
independent maps. `tasks` binds one concrete task to the exact Unity test filters
that prove it. `decomposition_child_templates` binds one *decomposition parent* to
the variant table its future children inherit, and is read by
`downstream_resilience.decomposition_validation_policy_for`.

Nothing in the repository previously cross-checked the second map against the
committed graph. The reader validates one template at the moment it is used, long
after a provider has run, an Issue has moved, and a checkout exists; and it
demands the exact three-key document shape, so an absent map made *every*
decomposition parent resolution raise rather than merely leaving that one parent
untemplated. This module closes both halves: it proves the whole map against the
whole committed graph, and it does so early enough to block.

Four ideas shape it.

One rule set. Every field, authority, platform, filter, and duplicate rule comes
from `downstream_resilience.resolve_decomposition_template`. This module adds only
the facts that need the graph -- which parents exist, which are eligible, which
require a template, and whether the variants partition the parent's exclusive
resources. It never restates a rule the reader already owns.

Requirement is authority-scoped, not scope-scoped. A parent requires a template
only when its decomposition would be validated through the automated decomposition
authority, because the template's own committed `authority` literal is
`committed_private_synthetic_gauntlet_decomposition_child_policy` and
`decomposition_replay._validate_automated_authority` is reached only for a machine
approval. A human-approved decomposition of an ordinary production parent never
reads this map, so an ordinary parent neither needs nor may carry a template. An
empty map is therefore correct exactly while the committed graph holds no
automated-authority parent.

Bind to a commit, never to "now". An already-authorized decomposition is replayed
against the policy and the parent contract at its bound source commit. Auditing
current main during such a replay would reject a decomposition that was valid when
it was authorized, so every entry point states which commit it means.

A template outlives its assignment. Applying a decomposition deliberately rewrites
its parent -- `kind` becomes `feature`, `execution_scope` becomes
`not_applicable`, `decomposition_state` becomes `decomposed`, the revision is
bumped and `exclusive_resources` is emptied -- while the template stays committed
because the new children inherit their test plan through it. Re-binding every
template to the current parent contract would therefore reject the map the moment
the decomposition it exists for succeeds, permanently. A template whose parent has
already been decomposed is instead proven against the parent contract its own
committed children record, and its variants are matched one-for-one against those
children rather than against a parent that no longer owns any resources.

Fail closed, mutate nothing. This module reads; it never writes the policy, never
generates a template, and never repairs one. `prepare_synthetic_gauntlet.py`
remains the single generator.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = ROOT / "Pipeline"
TASK_GRAPH_ROOT = PIPELINE_ROOT / "TaskGraph"
for _module_root in (ROOT, PIPELINE_ROOT, TASK_GRAPH_ROOT):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))

from Pipeline.TaskDecomposition.context_builder import (  # noqa: E402
    DecompositionPreflightError,
    validate_task_selection,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.downstream_resilience import (  # noqa: E402
    require_decomposition_policy_document,
    read_decomposition_policy_document,
    resolve_decomposition_template,
)
from TaskDecomposition.policy import semantic_json_sha256  # noqa: E402


VALIDATION_POLICY_RELATIVE = "Pipeline/TaskReviewAgent/authoritative_validation_policy.json"
DECOMPOSITION_TEMPLATE_AUTHORITY = (
    "committed_private_synthetic_gauntlet_decomposition_child_policy"
)
# The exact eligibility the D1A graph-delta planner enforces before it will plan a
# decomposition at all (`Pipeline/TaskGraph/graph_delta.py`). A template may only
# name a parent that could actually reach the reader.
ELIGIBLE_EXECUTION_SCOPE = "needs_execution_decomposition"
ELIGIBLE_DECOMPOSITION_STATE = "concrete"
# The state an applied parent is rewritten into. Its template stays committed
# because its children still inherit from it.
DECOMPOSED_STATE = "decomposed"
ELIGIBLE_DISPOSITION = "active"
ELIGIBLE_KIND = "implementation"

_TASK_ID = re.compile(r"^NSC-\d{3}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ValidationPolicyAuditError(DecompositionPreflightError):
    """Raised when the committed decomposition policy cannot be proven.

    It subclasses :class:`DecompositionPreflightError` deliberately. The
    scheduler already treats that exception as "this candidate may not be offered
    for decomposition", and the host launcher already lets it escape as a hard
    stop before any lease, checkout, or provider call. One exception type
    therefore produces the correct behavior at both boundaries without either of
    them learning a new failure mode.
    """


def _git_text(source: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(source), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=180.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationPolicyAuditError(
            f"committed decomposition policy could not be read: {type(exc).__name__}: {exc}"
        ) from exc
    if completed.returncode != 0:
        raise ValidationPolicyAuditError(
            "committed decomposition policy could not be read: "
            + completed.stderr.decode("utf-8", "replace").strip()
        )
    return completed.stdout.decode("utf-8-sig")


def _exact_commit(commit: Any) -> str:
    if type(commit) is not str or _COMMIT.fullmatch(commit) is None:
        raise ValidationPolicyAuditError(
            "bound decomposition source commit must be one exact lowercase Git object ID"
        )
    return commit


def read_policy_document(source: Path | str, *, commit: str | None = None) -> Mapping[str, Any]:
    """Return the exact decomposition policy document for one stated revision.

    ``commit`` is the bound source commit of an already-authorized decomposition.
    ``None`` means the working tree, which is what a fresh admission audits.
    """

    if commit is None:
        try:
            return read_decomposition_policy_document(source)
        except DownstreamPipelineError as exc:
            raise ValidationPolicyAuditError(str(exc)) from exc
    text = _git_text(
        Path(source), "show", f"{_exact_commit(commit)}:{VALIDATION_POLICY_RELATIVE}"
    )
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationPolicyAuditError(
            f"decomposition policy at the bound source commit is not valid JSON: {exc}"
        ) from exc
    try:
        return require_decomposition_policy_document(document)
    except DownstreamPipelineError as exc:
        raise ValidationPolicyAuditError(str(exc)) from exc


def read_committed_tasks(
    source: Path | str, *, commit: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return every committed task contract for one stated revision, by task ID."""

    repository = Path(source)
    tasks: dict[str, dict[str, Any]] = {}
    if commit is None:
        paths = sorted((repository / "Tasks").glob("NSC-*.yaml"))
        payloads = ((path.stem, path.read_bytes()) for path in paths)
        for task_id, payload in payloads:
            tasks[task_id] = _parsed_contract(task_id, payload.decode("utf-8-sig"))
        return tasks
    exact = _exact_commit(commit)
    listing = _git_text(repository, "ls-tree", "-r", "--name-only", exact, "--", "Tasks")
    for line in listing.splitlines():
        name = line.strip()
        if not name.startswith("Tasks/") or not name.endswith(".yaml"):
            continue
        task_id = name[len("Tasks/"):-len(".yaml")]
        if _TASK_ID.fullmatch(task_id) is None:
            continue
        tasks[task_id] = _parsed_contract(
            task_id, _git_text(repository, "show", f"{exact}:{name}")
        )
    return tasks


def _parsed_contract(task_id: str, text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationPolicyAuditError(
            f"committed task contract is not valid JSON: {task_id}"
        ) from exc
    if not isinstance(value, dict) or value.get("id") != task_id:
        raise ValidationPolicyAuditError(
            f"committed task contract identity does not match its path: {task_id}"
        )
    return value


def parent_semantic_hash(task: Mapping[str, Any]) -> str:
    """Return the exact parent contract hash a template must carry.

    This is the semantic hash of the contract with the injected
    ``task_contract_sha256`` removed -- the identical construction
    `decomposition_replay._semantic_task_hash`, `synthetic_gauntlet_approver`, and
    `prepare_synthetic_gauntlet` already use, so a template written by the
    generator and a template checked here can never disagree about identity.
    """

    payload = dict(task)
    payload.pop("task_contract_sha256", None)
    return semantic_json_sha256(payload)


def is_decomposition_eligible_parent(task: Mapping[str, Any]) -> bool:
    """Return whether D1A would accept this contract as a decomposition parent."""

    return (
        isinstance(task, Mapping)
        and task.get("contract_disposition") == ELIGIBLE_DISPOSITION
        and task.get("kind") == ELIGIBLE_KIND
        and task.get("execution_scope") == ELIGIBLE_EXECUTION_SCOPE
        and task.get("decomposition_state") == ELIGIBLE_DECOMPOSITION_STATE
    )


def is_decomposed_parent(task: Mapping[str, Any]) -> bool:
    """Return whether this contract has already been decomposed.

    Applying a decomposition deliberately rewrites its parent: `graph_delta`
    sets `kind` to `feature`, `execution_scope` to `not_applicable`,
    `decomposition_state` to `decomposed`, bumps `contract_revision`, and empties
    `exclusive_resources`. The template is not stale at that point -- it is the
    binding the parent's children still inherit through
    `validation_plan_for`'s progressive-decomposition path -- so it must be
    audited against the assignment it actually describes rather than against the
    contract the apply step replaced.
    """

    return (
        isinstance(task, Mapping)
        and task.get("decomposition_state") == DECOMPOSED_STATE
    )


def decomposition_children_of(
    tasks: Mapping[str, Mapping[str, Any]], parent_id: str
) -> list[Mapping[str, Any]]:
    """Return the committed children one applied decomposition produced.

    Exactly the population `validation_plan_for` resolves through the template:
    a task whose provenance names `progressive_decomposition` and this parent.
    """

    children = []
    for task in tasks.values():
        provenance = task.get("provenance")
        if (
            isinstance(provenance, Mapping)
            and provenance.get("origin") == "progressive_decomposition"
            and provenance.get("parent_task_id") == parent_id
        ):
            children.append(task)
    return sorted(children, key=lambda item: str(item.get("id")))


def uses_automated_decomposition_authority(task: Mapping[str, Any]) -> bool:
    """Return whether this parent's decomposition is machine-approved.

    Only a machine approval reaches the child-template reader:
    `decomposition_replay.inspect_authorized_decomposition_replay` guards the
    whole policy proof behind ``if automated:``, and the one committed generator
    of these templates emits them exclusively for contracts carrying a
    ``provenance.gauntlet_id``. A human-approved production decomposition never
    consults this map, so its parent must not be required -- or permitted -- to
    carry an entry stamped with the private synthetic-gauntlet authority.
    """

    provenance = task.get("provenance")
    if not isinstance(provenance, Mapping):
        return False
    gauntlet_id = provenance.get("gauntlet_id")
    return type(gauntlet_id) is str and bool(gauntlet_id.strip())


def requires_decomposition_child_template(task: Mapping[str, Any]) -> bool:
    """Return whether the committed policy must carry a template for this parent."""

    return is_decomposition_eligible_parent(task) and uses_automated_decomposition_authority(
        task
    )


def _normalized_resources(value: Any, *, task_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValidationPolicyAuditError(
            f"decomposition template {task_id} has a variant with no exclusive resources"
        )
    resources: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise ValidationPolicyAuditError(
                f"decomposition template {task_id} has a non-string exclusive resource"
            )
        if item != item.strip():
            raise ValidationPolicyAuditError(
                f"decomposition template {task_id} has an unnormalized exclusive resource: {item!r}"
            )
        resources.append(item)
    if len(set(resources)) != len(resources):
        raise ValidationPolicyAuditError(
            f"decomposition template {task_id} repeats an exclusive resource inside one variant"
        )
    canonical = sorted(resources, key=str.casefold)
    if resources != canonical:
        # The reader sorts before hashing, so an unsorted committed variant still
        # resolves -- and silently produces a policy_sha256 that the committed
        # bytes do not show. Requiring the canonical order keeps the file itself
        # readable as the thing that was proven.
        raise ValidationPolicyAuditError(
            f"decomposition template {task_id} has unsorted exclusive resources: {resources!r}"
        )
    return tuple(resources)


def _historical_parent_hash(
    *, task_id: str, children: list[Mapping[str, Any]]
) -> str:
    """Return the pre-apply parent hash this template's own children agree on.

    An applied parent no longer hashes to the value its template names, and it
    must not: `graph_delta` writes each child a
    `provenance.parent_contract_sha256` recording the parent contract that was
    decomposed, and `validation_plan_for` matches the template against exactly
    that value. Recovering the hash from the children means the template still
    cannot certify its own identity -- the committed children do.
    """

    if not children:
        raise ValidationPolicyAuditError(
            f"decomposition template for {task_id} names a decomposed parent with no "
            "committed children, so nothing can prove which contract it describes"
        )
    hashes = set()
    for child in children:
        provenance = child.get("provenance")
        value = (
            provenance.get("parent_contract_sha256")
            if isinstance(provenance, Mapping)
            else None
        )
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValidationPolicyAuditError(
                f"decomposition child {child.get('id')!r} of {task_id} has no exact "
                "parent contract hash"
            )
        hashes.add(value)
    if len(hashes) != 1:
        raise ValidationPolicyAuditError(
            f"decomposition children of {task_id} disagree about the parent contract "
            f"they were produced from: {sorted(hashes)}"
        )
    return hashes.pop()


def _audit_one_template(
    *,
    task_id: str,
    document: Mapping[str, Any],
    tasks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    parent = tasks.get(task_id)
    if parent is None:
        raise ValidationPolicyAuditError(
            f"decomposition template names a task that is not in the committed graph: {task_id}"
        )
    if parent.get("contract_disposition") != ELIGIBLE_DISPOSITION:
        raise ValidationPolicyAuditError(
            f"decomposition template names an inactive parent: {task_id}"
        )
    if not uses_automated_decomposition_authority(parent):
        raise ValidationPolicyAuditError(
            f"decomposition template names {task_id}, whose decomposition is not "
            "machine-approved; only an automated-authority parent may carry the "
            f"{DECOMPOSITION_TEMPLATE_AUTHORITY} template"
        )
    # A template outlives the assignment that needed it, because its children
    # keep inheriting from it. Which contract it must bind to therefore depends
    # on whether that decomposition has been applied yet.
    applied = is_decomposed_parent(parent)
    children = decomposition_children_of(tasks, task_id) if applied else []
    if applied:
        expected_hash = _historical_parent_hash(task_id=task_id, children=children)
    else:
        if not is_decomposition_eligible_parent(parent):
            raise ValidationPolicyAuditError(
                f"decomposition template names an ineligible parent: {task_id} is "
                f"kind={parent.get('kind')!r} execution_scope={parent.get('execution_scope')!r} "
                f"decomposition_state={parent.get('decomposition_state')!r}"
            )
        expected_hash = parent_semantic_hash(parent)
    raw = document["decomposition_child_templates"][task_id]
    if isinstance(raw, Mapping) and raw.get("parent_task_contract_sha256") != expected_hash:
        raise ValidationPolicyAuditError(
            f"decomposition template for {task_id} is stale: it names parent contract "
            f"{raw.get('parent_task_contract_sha256')!r}; the "
            f"{'decomposed' if applied else 'committed'} contract is {expected_hash!r}"
        )
    try:
        # Every field, authority, platform, filter, and duplicate-variant rule is
        # the reader's own. Nothing here is a second copy of them.
        resolved = resolve_decomposition_template(
            document, task_id, parent_semantic_hash=expected_hash
        )
    except DownstreamPipelineError as exc:
        raise ValidationPolicyAuditError(str(exc)) from exc

    raw_variants = raw["validation_variants"]
    committed_order: list[tuple[str, ...]] = []
    for variant in raw_variants:
        committed_order.append(
            _normalized_resources(
                variant.get("required_exclusive_resources"), task_id=task_id
            )
        )
    resolved_order = [
        tuple(item["required_exclusive_resources"])
        for item in resolved["validation_variants"]
    ]
    # The reader sorts the variants before hashing, so a file committed in
    # another order still resolves -- and produces a policy_sha256 the committed
    # bytes do not show. Comparing the committed order itself keeps the file
    # readable as the exact thing that was proven.
    if committed_order != resolved_order:
        raise ValidationPolicyAuditError(
            f"decomposition template {task_id} variants are not in canonical order"
        )

    # A child inherits by exact resource-set equality, so overlapping variants make
    # the inherited plan ambiguous for any child that owns part of two of them, and
    # a partial cover leaves a legitimate child with no plan at all.
    seen: dict[str, int] = {}
    for index, resources in enumerate(committed_order):
        for resource in resources:
            if resource in seen:
                raise ValidationPolicyAuditError(
                    f"decomposition template {task_id} variants overlap on {resource!r}: "
                    f"variants {seen[resource]} and {index} both claim it"
                )
            seen[resource] = index
    if applied:
        # The apply step empties the parent's own exclusive_resources, so the
        # population the variants must cover is the committed children. This is
        # exactly the match `validation_plan_for` performs for each child, moved
        # to a preflight where drift is cheap to see.
        claimed = [_child_resources(child, task_id=task_id) for child in children]
        if sorted(claimed) != sorted(committed_order):
            raise ValidationPolicyAuditError(
                f"decomposition template {task_id} variants do not match its committed "
                f"children one-for-one (children={[list(item) for item in sorted(claimed)]}, "
                f"variants={[list(item) for item in sorted(committed_order)]})"
            )
    else:
        parent_resources = parent.get("exclusive_resources")
        if not isinstance(parent_resources, list) or any(
            type(item) is not str for item in parent_resources
        ):
            raise ValidationPolicyAuditError(
                f"decomposition parent {task_id} has no exact exclusive_resources list"
            )
        if set(seen) != set(parent_resources):
            missing = sorted(set(parent_resources) - set(seen))
            extra = sorted(set(seen) - set(parent_resources))
            raise ValidationPolicyAuditError(
                f"decomposition template {task_id} variants do not partition the parent's "
                f"exclusive resources (uncovered={missing}, unknown={extra})"
            )
    return {
        "parent_task_id": task_id,
        "parent_contract_sha256": expected_hash,
        "parent_decomposed": applied,
        "variant_count": len(resolved_order),
        "policy_sha256": resolved["policy_sha256"],
    }


def _child_resources(child: Mapping[str, Any], *, task_id: str) -> tuple[str, ...]:
    resources = child.get("exclusive_resources")
    if not isinstance(resources, list) or any(
        type(item) is not str or not item.strip() for item in resources
    ):
        raise ValidationPolicyAuditError(
            f"decomposition child {child.get('id')!r} of {task_id} has no exact "
            "exclusive_resources list"
        )
    return tuple(sorted(resources, key=str.casefold))


def audit_decomposition_policy(
    source: Path | str,
    *,
    commit: str | None = None,
    document: Mapping[str, Any] | None = None,
    tasks: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prove the whole committed template map against the whole committed graph.

    Returns a deterministic receipt. Raises :class:`ValidationPolicyAuditError` on
    a missing, orphaned, ineligible, stale, malformed, duplicated, overlapping, or
    non-partitioning template. ``document`` and ``tasks`` let a caller supply
    already-proven bytes; otherwise both are read at ``commit`` (or the working
    tree when ``commit`` is ``None``).
    """

    if document is None:
        document = read_policy_document(source, commit=commit)
    else:
        try:
            document = require_decomposition_policy_document(document)
        except DownstreamPipelineError as exc:
            raise ValidationPolicyAuditError(str(exc)) from exc
    if tasks is None:
        tasks = read_committed_tasks(source, commit=commit)

    templates = document["decomposition_child_templates"]
    if not isinstance(templates, Mapping):
        raise ValidationPolicyAuditError(
            "authoritative validation policy omitted decomposition templates"
        )
    for task_id in templates:
        if type(task_id) is not str or _TASK_ID.fullmatch(task_id) is None:
            raise ValidationPolicyAuditError(
                f"decomposition template key is not one exact task ID: {task_id!r}"
            )

    required = sorted(
        task_id
        for task_id, task in tasks.items()
        if requires_decomposition_child_template(task)
    )
    missing = [task_id for task_id in required if task_id not in templates]
    if missing:
        raise ValidationPolicyAuditError(
            "committed decomposition policy has no child template for "
            f"machine-approved decomposition parent(s): {missing}"
        )

    audited = [
        _audit_one_template(task_id=task_id, document=document, tasks=tasks)
        for task_id in sorted(templates)
    ]
    return {
        "policy_path": VALIDATION_POLICY_RELATIVE,
        "source_commit": commit,
        "committed_task_count": len(tasks),
        "eligible_decomposition_parents": sorted(
            task_id
            for task_id, task in tasks.items()
            if is_decomposition_eligible_parent(task)
        ),
        "templates_required": required,
        "templates_audited": audited,
    }


def decomposition_preflight(
    source: Path | str,
    task_id: str,
    task: Mapping[str, Any],
    *,
    commit: str | None = None,
    document: Mapping[str, Any] | None = None,
    tasks: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the complete deterministic decomposition preflight for one candidate.

    The committed selection rules run first, then the repository-level policy
    audit, so a candidate is neither offered nor started while the template map
    that its future children will inherit is missing, stale, or malformed. Both
    failures raise :class:`DecompositionPreflightError`, which the scheduler
    already treats as "do not offer" and the host launcher already treats as a
    hard stop before any provider call, Issue mutation, graph mutation, checkout,
    or claim acquisition.
    """

    validate_task_selection(task_id, dict(task))
    return audit_decomposition_policy(
        source, commit=commit, document=document, tasks=tasks
    )


__all__ = [
    "DECOMPOSITION_TEMPLATE_AUTHORITY",
    "VALIDATION_POLICY_RELATIVE",
    "ValidationPolicyAuditError",
    "audit_decomposition_policy",
    "decomposition_children_of",
    "decomposition_preflight",
    "is_decomposed_parent",
    "is_decomposition_eligible_parent",
    "parent_semantic_hash",
    "read_committed_tasks",
    "read_policy_document",
    "requires_decomposition_child_template",
    "uses_automated_decomposition_authority",
]
