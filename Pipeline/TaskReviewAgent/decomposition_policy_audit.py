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
from typing import Any, Mapping, Sequence


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
from Pipeline.TaskReviewAgent.committed_tasks import (  # noqa: E402
    CommittedTaskError,
    load_committed_task,
)
from Pipeline.TaskReviewAgent.downstream_pipeline import (  # noqa: E402
    DownstreamPipelineError,
)
from Pipeline.TaskReviewAgent.git_identity_guard import (  # noqa: E402
    GitIdentityGuardError,
    validated_agent_git_identity,
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

_TASK_ID = re.compile(r"^NSC-(?:[0-9]{3}|[1-9][0-9]{3,8})$")
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
        payloads = (
            (path.stem, path.read_bytes())
            for path in paths
            if _TASK_ID.fullmatch(path.stem) is not None
        )
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


def historical_parent_hash(
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
        expected_hash = historical_parent_hash(task_id=task_id, children=children)
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


# The three conditions an apply can leave behind in the validation policy, named so
# a caller can branch on them instead of matching prose. POLICY_UNREADABLE is not
# "nothing is wrong": it is the state where nobody could look, and collapsing it
# into an empty finding list is how an unchecked policy reads as a clean one.
POLICY_UNREADABLE = "policy_unreadable"
POLICY_PIN_STALE = "pin_stale"
POLICY_CHILD_UNPINNED = "child_unpinned"


def _rewritten_contract_ids(
    source: Path, before_commit: str, after_commit: str
) -> tuple[str, ...]:
    """Task IDs whose contract bytes differ between the two commits."""

    listing = _git_text(
        source, "diff", "--name-only", _exact_commit(before_commit),
        _exact_commit(after_commit), "--", "Tasks",
    )
    ids = []
    for line in listing.splitlines():
        name = line.strip()
        if not name.startswith("Tasks/") or not name.endswith(".yaml"):
            continue
        task_id = name[len("Tasks/"):-len(".yaml")]
        if _TASK_ID.fullmatch(task_id) is not None:
            ids.append(task_id)
    return tuple(sorted(set(ids)))


def applied_policy_findings(
    source: Path | str,
    *,
    before_commit: str,
    after_commit: str,
    parent_task_id: str,
    child_task_ids: Sequence[str],
) -> tuple[dict[str, Any], ...]:
    """Name what applying a decomposition just invalidated in the validation policy.

    Applying rewrites ``Tasks/*.yaml`` -- it bumps ``contract_revision``, repoints
    every ``depends_on`` that referenced the parent, and re-serializes -- and it
    writes nothing to ``authoritative_validation_policy.json``. The policy pins each
    task by the sha256 of its committed contract bytes, so an apply silently
    invalidates the pin of every task it rewrote, and gives its new children no
    entry at all. Neither condition is reported by the apply today; both surface
    hours later, as a red CI job or as a child with no validation plan.

    THE DAMAGE IS NOT LIMITED TO THE PARENT, which is the part the original report
    of this defect did not carry. Traced to the commit that FIRST broke each pin,
    across main's whole history -- four applies, five pins, and four of the five are
    bystanders:

        9a93f926  apply NSC-066  broke NSC-067  bystander
        84437aa2  apply NSC-088  broke NSC-087  bystander
        644e3c4f  apply NSC-007  broke NSC-007  THE PARENT
        644e3c4f  apply NSC-007  broke NSC-098  bystander
        b5c64602  apply NSC-015  broke NSC-099  bystander

    A bystander is a task that was not being decomposed at all: the apply rewrote it
    because it named the parent in ``depends_on``, bumped nothing of its own, and
    re-serialized it. **So scoping a repair to the parent finds one pin in five.**
    Main holds nineteen applies and only four broke a pin, because a bystander breaks
    one only if it already HAS an entry -- which is why this gets worse as policy
    coverage grows rather than better.

    The stale rule is not restated here. ``downstream_resilience.validation_plan_for``
    refuses an entry whose ``task_contract_sha256`` differs from the contract's own,
    with the message "authoritative validation policy for <id> is stale", and
    ``committed_tasks.load_committed_task`` is what computes that hash from the
    committed bytes. This asks those two, at a stated commit, so the verdict comes
    from the readers the pipeline already trusts rather than from a second opinion
    that can drift from them.

    A missing entry is deliberately NOT reported for every task that lacks one: 65 of
    the 128 committed contracts have no entry and never needed one, so "no entry" is
    the normal case and a finding on it would be noise. It is reported when the
    PARENT carries an entry and a child does not, because then validation that was
    pinned before the split is unpinned after it -- coverage the apply removed rather
    than coverage that never existed.

    Returns one finding per condition, never raising for the conditions themselves:
    the commit is already on the branch by the time this can be measured, and
    refusing here would leave Source moved with the record un-applied, turning a
    rebind that GER does in one pass into an unrecoverable decomposition. The
    findings go into the record and onto stderr instead. Reading them is the
    caller's, and a caller that ignores them is no worse off than today.
    """

    repository = Path(source)
    findings: list[dict[str, Any]] = []
    try:
        document = read_policy_document(repository, commit=after_commit)
    except ValidationPolicyAuditError as exc:
        return ({
            "condition": POLICY_UNREADABLE,
            "task_id": None,
            "detail": (
                "the validation policy could not be read at the applied commit, so"
                " neither a stale pin nor an unpinned child could be looked for here:"
                " %s" % exc
            ),
        },)
    entries = document["tasks"]
    rewritten = _rewritten_contract_ids(repository, before_commit, after_commit)
    children = tuple(sorted(set(child_task_ids)))

    def pinned_matches(task_id: str, commit: str) -> bool | None:
        """True/False when both the entry and the contract exist, else None."""

        entry = entries.get(task_id)
        if not isinstance(entry, Mapping):
            return None
        try:
            contract = load_committed_task(repository, task_id, commit=commit)
        except CommittedTaskError:
            return None
        return entry.get("task_contract_sha256") == contract["task_contract_sha256"]

    for task_id in sorted(entries):
        if pinned_matches(task_id, after_commit) is not False:
            continue
        if task_id == parent_task_id:
            role = "the decomposed parent"
        elif task_id in children:
            role = "a new child of this decomposition"
        elif task_id in rewritten:
            role = (
                "a task this apply rewrote without decomposing it, because it"
                " referenced the parent"
            )
        else:
            role = "a task this apply did not rewrite"
        was_fresh = pinned_matches(task_id, before_commit) is True
        findings.append({
            "condition": POLICY_PIN_STALE,
            "task_id": task_id,
            "detail": (
                "%s pins a contract this apply no longer matches: %s. %s Rebinding the"
                " entry to the committed contract bytes is the whole repair."
                % (
                    task_id, role,
                    "It was consistent immediately before the apply, so THIS APPLY"
                    " BROKE IT." if was_fresh else
                    "It was ALREADY stale immediately before the apply, so this apply"
                    " did not cause it -- but do not go looking outside the apply path"
                    " for what did. Traced across main's history, every pin that ever"
                    " went stale was broken by a decomposition apply, so an inherited"
                    " stale pin is a BACKLOG OF THIS SAME DEFECT rather than a second"
                    " cause.",
                )
            ),
            "rewritten_by_this_apply": task_id in rewritten,
            "stale_before_this_apply": not was_fresh,
        })

    if isinstance(entries.get(parent_task_id), Mapping):
        for child_id in children:
            if isinstance(entries.get(child_id), Mapping):
                continue
            findings.append({
                "condition": POLICY_CHILD_UNPINNED,
                "task_id": child_id,
                "detail": (
                    "%s has no validation policy entry while its parent %s has one, so"
                    " work that was pinned to exact test filters before the split is"
                    " unpinned after it. The entry needs authored Unity test class"
                    " names, which this apply cannot derive -- it is named here so it"
                    " is authored deliberately rather than discovered by a red job."
                    % (child_id, parent_task_id)
                ),
                "parent_task_id": parent_task_id,
            })
    return tuple(findings)


def describe_policy_findings(findings: Sequence[Mapping[str, Any]]) -> str:
    """One line for a log or an error message. Empty findings say so explicitly."""

    if not findings:
        return "validation policy consistent: no stale pin, no unpinned child"
    parts = []
    for condition in (POLICY_UNREADABLE, POLICY_PIN_STALE, POLICY_CHILD_UNPINNED):
        named = [str(f.get("task_id")) for f in findings if f.get("condition") == condition]
        if named:
            parts.append("%s=%s" % (condition, ",".join(named)))
    return "validation policy findings: " + "; ".join(parts)


# Why a rebind is SKIPPED, named so a caller can report it rather than infer it.
REBIND_SKIPPED_PRE_EXISTING = "stale_before_this_apply"
REBIND_SKIPPED_NOT_REWRITTEN = "not_rewritten_by_this_apply"
REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY = "child_entry_needs_authored_test_filters"


def plan_pin_rebind(
    source: Path | str,
    findings: Sequence[Mapping[str, Any]],
    *,
    commit: str,
) -> dict[str, Any]:
    """Name the pins this apply broke and may therefore repair, and what it will not touch.

    THE SCOPE IS DELIBERATELY NARROWER THAN "every stale pin". A pin that was already stale before
    the apply belongs to whoever revised that contract without rebinding; repairing it here would
    make an apply change policy nobody asked it to change, and would hide a second writer's defect
    inside a decomposition's diff. Those are reported as skipped, with the reason, so the caller can
    say what it is leaving alone.

    A child with no entry is skipped for a different reason and it is not a judgement call: an entry
    needs authored Unity test class names, which nothing in the apply path can derive.
    """

    repository = Path(source)
    rebinds: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    for finding in findings:
        condition = finding.get("condition")
        task_id = finding.get("task_id")
        if condition == POLICY_CHILD_UNPINNED:
            skipped.append({"task_id": task_id,
                            "reason": REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY})
            continue
        if condition != POLICY_PIN_STALE:
            continue
        if finding.get("stale_before_this_apply"):
            skipped.append({"task_id": task_id, "reason": REBIND_SKIPPED_PRE_EXISTING})
            continue
        if not finding.get("rewritten_by_this_apply"):
            skipped.append({"task_id": task_id, "reason": REBIND_SKIPPED_NOT_REWRITTEN})
            continue
        document = read_policy_document(repository, commit=commit)
        entry = document["tasks"].get(task_id)
        if not isinstance(entry, Mapping):
            skipped.append({"task_id": task_id,
                            "reason": REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY})
            continue
        contract = load_committed_task(repository, str(task_id), commit=commit)
        rebinds.append({
            "task_id": str(task_id),
            "from": str(entry.get("task_contract_sha256")),
            "to": contract["task_contract_sha256"],
        })
    return {"commit": _exact_commit(commit), "rebinds": rebinds, "skipped": skipped}


def apply_pin_rebind(
    source: Path | str,
    plan: Mapping[str, Any],
    *,
    message: str,
) -> dict[str, Any]:
    """Write exactly the pins the plan names, in one commit that touches only the policy.

    FIVE things are proven rather than assumed, because this writes to Source. The first two were
    added after an audit found the helper accepting a stale plan and committing as the host.

    THE PLAN IS BOUND TO THE CURRENT HEAD. ``plan_pin_rebind`` records the commit it inspected and
    this refuses unless HEAD is still that commit. Without it, a clean contract revision landing
    between plan and apply leaves the old pin TEXT intact, so the edit succeeds and installs a hash
    that is ALREADY STALE while reporting ``rebound`` -- a rebind that reports success and fixes
    nothing is worse than one that refuses.

    EVERY TARGET HASH IS RECOMPUTED HERE. The HEAD check makes that redundant for a plan this module
    produced, and it is not redundant for a plan built by hand or carried across a process: a
    ``to`` value is a claim about a contract's bytes and is checked against those bytes.

    THE COMMIT CARRIES THE VALIDATED AUTOMATION IDENTITY, not the host's. It is configured with
    ``-c`` so no global configuration can win, and then READ BACK off the created commit, because
    configuring an identity and having it applied are different claims.

    The tree is clean first. Committing from a dirty tree is how one writer's commit carries
    another's staged work, which this repository has already paid for once.

    Each old pin occurs EXACTLY ONCE in the file text. The edit is textual so the document keeps its
    own 28KB of formatting and its own hashes; a pin that appeared twice would make a textual edit
    ambiguous, so it refuses instead of guessing.

    Nothing but the named pins changed. The before and after documents are compared as parsed
    objects with the rebound pins substituted into the original -- so a stray edit anywhere else in
    the file fails here rather than in whatever reads it next.
    """

    repository = Path(source)
    rebinds = list(plan.get("rebinds") or [])
    if not rebinds:
        return {"status": "nothing_to_rebind", "commit": None, "rebound": []}
    planned = _exact_commit(plan.get("commit"))
    head = _git_text(repository, "rev-parse", "HEAD").strip()
    if head != planned:
        raise ValidationPolicyAuditError(
            "policy rebind plan was made at %s and HEAD is now %s: re-plan rather than applying a"
            " stale plan, which would install a hash that is already out of date"
            % (planned[:12], head[:12])
        )
    for rebind in rebinds:
        current = load_committed_task(repository, str(rebind["task_id"]), commit=head)
        if current["task_contract_sha256"] != str(rebind["to"]):
            raise ValidationPolicyAuditError(
                "policy rebind target for %s is %s but the committed contract hashes to %s"
                % (rebind["task_id"], str(rebind["to"])[:12],
                   current["task_contract_sha256"][:12])
            )
    dirty = _git_text(repository, "status", "--porcelain", "--untracked-files=all")
    if dirty.strip():
        raise ValidationPolicyAuditError(
            "Source must be clean before a policy rebind commit: " + dirty.strip()
        )
    path = repository / VALIDATION_POLICY_RELATIVE
    original_bytes = path.read_bytes()
    before = json.loads(original_bytes.decode("utf-8-sig"))
    text = original_bytes.decode("utf-8")
    for rebind in rebinds:
        old = str(rebind["from"])
        new = str(rebind["to"])
        if re.fullmatch(r"[0-9a-f]{64}", new) is None:
            raise ValidationPolicyAuditError(
                "a rebind target must be an exact sha256: %r" % new
            )
        occurrences = text.count(old)
        if occurrences != 1:
            raise ValidationPolicyAuditError(
                "policy pin %s for %s occurs %d times in the document, so a textual rebind is"
                " ambiguous" % (old[:12], rebind["task_id"], occurrences)
            )
        text = text.replace(old, new, 1)
    after = json.loads(text.encode("utf-8").decode("utf-8-sig"))
    expected = json.loads(json.dumps(before))
    for rebind in rebinds:
        expected["tasks"][rebind["task_id"]]["task_contract_sha256"] = rebind["to"]
    if after != expected:
        raise ValidationPolicyAuditError(
            "the rebound policy differs from the original in something other than the named pins"
        )
    path.write_bytes(text.encode("utf-8"))
    try:
        _git_text(repository, "add", "--", VALIDATION_POLICY_RELATIVE)
        staged = _git_text(repository, "diff", "--cached", "--name-only")
        if [line.strip() for line in staged.splitlines() if line.strip()] != [
            VALIDATION_POLICY_RELATIVE
        ]:
            raise ValidationPolicyAuditError(
                "a policy rebind staged something other than the policy: %r" % staged
            )
        try:
            author_name, author_email = validated_agent_git_identity()
        except GitIdentityGuardError as exc:
            raise ValidationPolicyAuditError(
                "policy rebind refused: no validated automation git identity: %s" % exc
            ) from exc
        _git_text(repository, "-c", "user.name=" + author_name,
                  "-c", "user.email=" + author_email,
                  "commit", "--only", "-m", message, "--",
                  VALIDATION_POLICY_RELATIVE)
    except ValidationPolicyAuditError:
        path.write_bytes(original_bytes)
        _git_text(repository, "reset", "-q", "--", VALIDATION_POLICY_RELATIVE)
        raise
    rebound_commit = _git_text(repository, "rev-parse", "HEAD").strip()
    stamped = _git_text(
        repository, "log", "-1", "--format=%an%x1f%ae%x1f%cn%x1f%ce", rebound_commit
    ).strip().split("\x1f")
    if stamped != [author_name, author_email, author_name, author_email]:
        raise ValidationPolicyAuditError(
            "policy rebind commit %s carries identity %r rather than the validated automation"
            " identity %r" % (rebound_commit[:12], stamped, [author_name, author_email])
        )
    head = rebound_commit
    committed = _git_text(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", head)
    if [line.strip() for line in committed.splitlines() if line.strip()] != [
        VALIDATION_POLICY_RELATIVE
    ]:
        raise ValidationPolicyAuditError(
            "the policy rebind commit touched more than the policy: %r" % committed
        )
    return {"status": "rebound", "commit": head, "rebound": rebinds,
            "skipped": list(plan.get("skipped") or [])}


def describe_pin_rebind(result: Mapping[str, Any]) -> str:
    """One line. An empty rebind says so rather than returning silence."""

    rebound = list(result.get("rebound") or [])
    skipped = list(result.get("skipped") or [])
    if not rebound:
        return "no pin was rebound (%d finding(s) left to their owners)" % len(skipped)
    return "rebound %s at %s; left alone: %s" % (
        ",".join(item["task_id"] for item in rebound),
        str(result.get("commit"))[:12],
        ", ".join("%s (%s)" % (item["task_id"], item["reason"]) for item in skipped) or "nothing",
    )


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
    "REBIND_SKIPPED_NEEDS_AUTHORED_ENTRY",
    "REBIND_SKIPPED_NOT_REWRITTEN",
    "REBIND_SKIPPED_PRE_EXISTING",
    "apply_pin_rebind",
    "describe_pin_rebind",
    "plan_pin_rebind",
    "POLICY_CHILD_UNPINNED",
    "POLICY_PIN_STALE",
    "POLICY_UNREADABLE",
    "applied_policy_findings",
    "describe_policy_findings",
    "VALIDATION_POLICY_RELATIVE",
    "ValidationPolicyAuditError",
    "audit_decomposition_policy",
    "decomposition_children_of",
    "decomposition_preflight",
    "historical_parent_hash",
    "is_decomposed_parent",
    "is_decomposition_eligible_parent",
    "parent_semantic_hash",
    "read_committed_tasks",
    "read_policy_document",
    "requires_decomposition_child_template",
    "uses_automated_decomposition_authority",
]
