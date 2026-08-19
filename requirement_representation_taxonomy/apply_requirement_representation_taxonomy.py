from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()

def read(path: str) -> str:
    p = ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"Expected repository file not found: {p}")
    return p.read_text(encoding="utf-8")

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")

def replace_once(path: str, old: str, new: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}")
    write(path, text.replace(old, new, 1))
    print(f"patched: {path} [{marker}]")

def insert_before_once(path: str, anchor: str, addition: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(f"Anchor not found in {path}: {anchor!r}")
    write(path, text[:idx] + addition + text[idx:])
    print(f"patched: {path} [{marker}]")

def insert_after_once(path: str, anchor: str, addition: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError(f"Anchor not found in {path}: {anchor!r}")
    idx += len(anchor)
    write(path, text[:idx] + addition + text[idx:])
    print(f"patched: {path} [{marker}]")

def regex_replace_once(path: str, pattern: str, replacement: str, marker: str) -> None:
    text = read(path)
    if marker in text:
        print(f"already patched: {path} [{marker}]")
        return
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one regex patch target in {path}; found {count}"
        )
    write(path, new_text)
    print(f"patched: {path} [{marker}]")

# ============================================================================
# reconciliation_agent.py
# ============================================================================

path = "Pipeline/Reconciliation/reconciliation_agent.py"

replace_once(
    path,
    '''        "gdd_evidence": {
            "type": "array",
            "items": GDD_EVIDENCE_SCHEMA,
        },
        "repository_state": {
''',
    '''        "gdd_evidence": {
            "type": "array",
            "items": GDD_EVIDENCE_SCHEMA,
        },
        "acceptance_criteria": {
            "type": "array",
            "items": GDD_EVIDENCE_SCHEMA,
        },
        "validation_requirements": {
            "type": "array",
            "items": GDD_EVIDENCE_SCHEMA,
        },
        "repository_state": {
''',
    marker='"acceptance_criteria": {',
)

replace_once(
    path,
    '''        "gdd_evidence",
        "repository_state",
''',
    '''        "gdd_evidence",
        "acceptance_criteria",
        "validation_requirements",
        "repository_state",
''',
    marker='        "acceptance_criteria",\n        "validation_requirements",',
)

insert_after_once(
    path,
    "8. Current repository evidence is required for implemented/partial claims.",
    '''
9. Added work items must distinguish requirement provenance from completion rules:
   - `gdd_evidence` explains why the work item exists;
   - `acceptance_criteria` records required behavior/constraints the implementation must satisfy;
   - `validation_requirements` records explicit checks/evidence needed to validate it.
   Do not create extra work items merely to represent acceptance or validation statements.''',
    marker="Added work items must distinguish requirement provenance",
)

insert_before_once(
    path,
    "def ensure_execution_scope_defaults(",
    '''def ensure_requirement_detail_defaults(
    payload: dict[str, Any],
) -> list[str]:
    # Upgrade legacy candidates that predate first-class requirement-detail fields.
    upgraded: list[str] = []
    for item in payload.get("work_items", []):
        changed = False
        if "acceptance_criteria" not in item:
            item["acceptance_criteria"] = []
            changed = True
        if "validation_requirements" not in item:
            item["validation_requirements"] = []
            changed = True
        if changed:
            upgraded.append(str(item.get("key", "")))
    return upgraded


''',
    marker="def ensure_requirement_detail_defaults(",
)

replace_once(
    path,
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_execution_scope_defaults(payload)
''',
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_requirement_detail_defaults(payload)
    ensure_execution_scope_defaults(payload)
''',
    marker="    ensure_requirement_detail_defaults(payload)\n    ensure_execution_scope_defaults(payload)",
)

replace_once(
    path,
    '''                    "kind": item.get("kind"),
                    "proposed_status": item.get("graph_status"),
''',
    '''                    "kind": item.get("kind"),
                    "acceptance_criteria": item.get("acceptance_criteria", []),
                    "validation_requirements": item.get(
                        "validation_requirements", []
                    ),
                    "proposed_status": item.get("graph_status"),
''',
    marker='"validation_requirements": item.get(',
)

replace_once(
    path,
    '''        repo_evidence = item.get("repository_evidence", [])
        if repo_evidence:
''',
    '''        acceptance = item.get("acceptance_criteria", [])
        if acceptance:
            lines.append("**Acceptance criteria**")
            lines.append("")
            for criterion in acceptance:
                lines.append(
                    f"- `{_cell(criterion.get('reference'))}` — "
                    f"{_cell(criterion.get('requirement'))}"
                )
            lines.append("")

        validation = item.get("validation_requirements", [])
        if validation:
            lines.append("**Validation requirements**")
            lines.append("")
            for requirement in validation:
                lines.append(
                    f"- `{_cell(requirement.get('reference'))}` — "
                    f"{_cell(requirement.get('requirement'))}"
                )
            lines.append("")

        repo_evidence = item.get("repository_evidence", [])
        if repo_evidence:
''',
    marker='lines.append("**Acceptance criteria**")',
)

# ============================================================================
# Main reconciliation prompt
# ============================================================================

path = "Pipeline/Reconciliation/prompts/reconcile.md"

insert_before_once(
    path,
    "# Evidence requirements",
    '''# Requirement representation inside work items

Do not confuse a required GDD statement with a requirement for a separate graph
node.

For every work item, use these three fields deliberately:

## `gdd_evidence`

Answers:

> Why does this work item exist?

Use it as requirement provenance/basis.

## `acceptance_criteria`

Answers:

> What required behavior or constraint must be true for this work item to be
> considered correctly implemented?

Use acceptance criteria for requirements that belong to an existing owner and
do not need a separate executable node.

Examples:

- click/hold semantics can be acceptance criteria on player movement;
- "Ranged Enemy is never introduced alone" can be an acceptance criterion on
  encounter activation/authoring;
- the three-to-eight-enemy encounter range can be an acceptance criterion on
  encounter work;
- a spell's cooldown/behavioral restriction can be an acceptance criterion on
  that spell rather than a separate task.

## `validation_requirements`

Answers:

> What explicit test, inspection, runtime check, or evidence must validate the
> work?

Use this for checks rather than implementation responsibilities.

Examples from the current GDD include:

- Bone Archive lane/pathing validation;
- Chapel of Ash projectile-occlusion validation;
- Lower Vault active-enemy-cap priority validation;
- isometric sprite-sorting checks;
- visual/gameplay alignment checks.

Those requirements may cause implementation changes if a test fails, but the
check itself is not automatically a separate gameplay work item.

## Representation rule

A GDD statement should become a separate `work_item` only when it describes a
distinct feature, artifact, reusable foundation, or executable implementation
responsibility that must be tracked independently.

Do NOT create a work item merely because a sentence is required.

Required statements may instead be represented as:

- acceptance criteria on an owning work item;
- validation requirements on an owning work item;
- non-code/delivery requirements under `non_code_requirements`;
- development/pipeline constraints under `non_code_requirements`;
- intentionally deferred design through a feature marked
  `needs_future_decomposition`;
- stretch/excluded scope under `deferred_or_excluded`.

The goal is durable requirement coverage without garbage microtasks.

''',
    marker="# Requirement representation inside work items",
)

insert_after_once(
    path,
    "Do not turn them into coding tasks merely because they exist in the GDD.",
    '''

Required delivery obligations (for example, producing the Windows build) and
development-process invariants (for example, agents not modifying the same
Unity asset concurrently) belong here when they are not themselves executable
gameplay implementation work.''',
    marker="Required delivery obligations (for example, producing the Windows build)",
)

# ============================================================================
# verification_crew.py
# ============================================================================

path = "Pipeline/Reconciliation/verification_crew.py"

text = read(path)
if '"requirement_representation_problem"' not in text:
    anchor = '                "execution_scope_problem",\n'
    if anchor not in text:
        raise RuntimeError("Could not find finding-category anchor in verification_crew.py")
    text = text.replace(
        anchor,
        anchor + '                "requirement_representation_problem",\n',
        1,
    )
    write(path, text)
    print(f"patched: {path} [requirement_representation_problem]")
else:
    print(f"already patched: {path} [requirement_representation_problem]")

regex_replace_once(
    path,
    r'''("representation":\s*\{\s*"type":\s*"string",\s*"enum":\s*\[)\s*
                "work_item",\s*
                "non_code_requirement",\s*
                "deferred_or_excluded",\s*
                "unrepresented",\s*
                "ambiguous",\s*
            (\],\s*\},)''',
    r'''\1
                "work_item",
                "acceptance_criterion",
                "validation_requirement",
                "non_code_requirement",
                "delivery_requirement",
                "pipeline_constraint",
                "deferred_design",
                "deferred_or_excluded",
                "unrepresented",
                "ambiguous",
            \2''',
    marker='"acceptance_criterion",',
)

taxonomy_function = r'''def deterministic_audit_checks(audits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []

    allowed_by_classification = {
        "required_gameplay": {
            "work_item",
            "acceptance_criterion",
            "validation_requirement",
            "deferred_design",
        },
        "required_non_code": {
            "non_code_requirement",
            "delivery_requirement",
        },
        "required_process": {
            "pipeline_constraint",
            "validation_requirement",
            "non_code_requirement",
        },
        "stretch": {"deferred_or_excluded"},
        "excluded": {"deferred_or_excluded"},
    }

    mapped_key_representations = {
        "work_item",
        "acceptance_criterion",
        "validation_requirement",
        "deferred_design",
    }

    for audit in audits:
        agent = str(audit.get("agent", ""))
        result = audit.get("result", {})
        requirements = result.get("requirements", [])
        if not isinstance(requirements, list):
            continue

        for requirement in requirements:
            classification = str(requirement.get("classification", ""))
            representation = str(requirement.get("representation", ""))
            mapped_keys = [
                str(value)
                for value in requirement.get("mapped_keys", [])
                if str(value).strip()
            ]

            problem: str | None = None
            category = "requirement_representation_problem"
            title = "Required GDD requirement has an unsafe representation"
            requires_human_review = False

            if classification.startswith("required_"):
                if representation == "unrepresented":
                    problem = (
                        "A required GDD statement has no durable representation."
                    )
                    title = "Required GDD requirement is unrepresented"
                elif representation == "ambiguous":
                    problem = (
                        "A required GDD statement has ambiguous representation. "
                        "Ambiguity is a coverage problem, not proof that a new "
                        "work item is required."
                    )
                    title = "Required GDD requirement has ambiguous representation"
                    requires_human_review = True
                elif representation not in allowed_by_classification.get(
                    classification, set()
                ):
                    problem = (
                        f"{representation!r} is not a valid representation for "
                        f"{classification!r}."
                    )
                elif (
                    representation in mapped_key_representations
                    and not mapped_keys
                ):
                    problem = (
                        f"{representation!r} requires at least one mapped work "
                        "key so the requirement cannot be silently lost."
                    )

            elif classification in {"stretch", "excluded"}:
                if representation not in {
                    "deferred_or_excluded",
                    "unrepresented",
                }:
                    problem = (
                        f"{classification!r} scope is represented as "
                        f"{representation!r}, which risks leaking optional/"
                        "excluded scope into required work."
                    )
                    category = "scope_leak"
                    title = "Stretch/excluded scope has an unsafe representation"

            if problem is None:
                continue

            generated.append(
                {
                    "source_agent": "Deterministic Coverage Check",
                    "source_model": "python",
                    "finding": {
                        "finding_id": (
                            "deterministic-representation-"
                            + str(requirement.get("requirement_id", "unknown"))
                        ),
                        "severity": "error",
                        "category": category,
                        "title": title,
                        "description": (
                            f"{agent} classified requirement "
                            f"{requirement.get('requirement_id')} as "
                            f"{classification}/{representation}. {problem}"
                        ),
                        "affected_keys": mapped_keys,
                        "gdd_evidence": [
                            {
                                "reference": str(
                                    requirement.get("reference", "")
                                ),
                                "requirement": str(
                                    requirement.get("requirement", "")
                                ),
                            }
                        ],
                        "repository_evidence": [],
                        "recommended_change": (
                            "Classify the requirement by representation semantics "
                            "before changing the graph. Create a new work item only "
                            "when the requirement is a distinct feature/artifact/"
                            "implementation responsibility. Otherwise map it as an "
                            "acceptance criterion, validation requirement, non-code/"
                            "delivery requirement, pipeline constraint, or deferred "
                            "design as appropriate."
                        ),
                        "requires_human_review": requires_human_review,
                    },
                }
            )

    return generated
'''

text = read(path)
if "allowed_by_classification = {" not in text:
    pattern = r'''def deterministic_audit_checks\(audits: list\[dict\[str, Any\]\]\) -> list\[dict\[str, Any\]\]:.*?(?=\ndef merge_findings\()'''
    new_text, count = re.subn(pattern, taxonomy_function + "\n\n", text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(
            f"Could not replace deterministic_audit_checks in {path}; found {count}"
        )
    write(path, new_text)
    print(f"patched: {path} [taxonomy-aware deterministic coverage]")
else:
    print(f"already patched: {path} [taxonomy-aware deterministic coverage]")

# ============================================================================
# Coverage auditor prompt
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md"

insert_before_once(
    path,
    "## Finding severity",
    '''## Requirement representation taxonomy

Your job is to determine whether each GDD requirement is represented in the
RIGHT WAY, not whether every required sentence has its own task.

Use these representation values:

### `work_item`

Use when the requirement is itself a distinct feature, artifact, reusable
foundation, or executable implementation responsibility that needs independent
graph state.

### `acceptance_criterion`

Use when the requirement is required behavior/constraint owned by an existing
mapped work item and does not need a separate executable node.

Examples:

- click/hold behavior on player movement;
- an encounter-size range on encounter work;
- "Ranged Enemy is not introduced alone" on encounter activation/authoring;
- spell-specific cooldown or interruption semantics on the spell/door owner.

Map `mapped_keys` to the owning work item(s).

### `validation_requirement`

Use when the requirement describes a check, test, inspection, or evidence
needed to validate mapped work rather than a distinct implementation
responsibility.

Examples from this GDD include Bone Archive lane/pathing checks, Chapel of Ash
occlusion checks, Lower Vault active-enemy-cap priority checks, isometric
sprite-sorting checks, and visual/gameplay alignment checks.

Map `mapped_keys` to the work being validated. Do not create a gameplay task
merely because a Play Mode check is required.

### `non_code_requirement`

Use for a required non-code obligation recorded in the candidate's
`non_code_requirements` section that is neither primarily a build/delivery
artifact nor a development-pipeline invariant.

### `delivery_requirement`

Use for a required deliverable/build obligation such as producing the required
Windows build. It should be durably represented as non-code/delivery scope, not
invented as a gameplay system.

### `pipeline_constraint`

Use for required development-process invariants such as agent/tool boundaries,
human integration gates, or "do not modify the same Unity asset concurrently."
These constrain the development pipeline; they are not gameplay work items.

### `deferred_design`

Use when required game scope is known but approved design is intentionally not
specific enough for concrete implementation/authoring yet. It must map to a
work/feature key whose decomposition state preserves that deferred design.

This is not the same as stretch scope.

### `deferred_or_excluded`

Use for stretch or explicitly excluded scope represented in the candidate's
deferred/excluded section.

### `unrepresented`

Use only when the requirement genuinely has no durable representation.

### `ambiguous`

Use only when the candidate does not let you determine which representation is
correct. Ambiguity is a human-review/coverage problem. It is NOT evidence that a
new work item must be created.

## Mapping rules

- `work_item`, `acceptance_criterion`, `validation_requirement`, and
  `deferred_design` must map to at least one candidate work key.
- `delivery_requirement`, `non_code_requirement`, and `pipeline_constraint`
  may legitimately have no work key because they are not executable gameplay
  nodes.
- Do not downgrade a requirement to `work_item` merely because it is important.
- Do not treat explicit validation language as implementation scope by default.
- Do not treat process constraints as gameplay scope.
- Do not require one work item per GDD sentence.

Before reporting `missing_required_work`, first ask whether the missing thing is
actually a work item, acceptance criterion, validation requirement, delivery
requirement, pipeline constraint, or deferred-design marker.

If the representation type is the problem rather than missing executable work,
use `category: requirement_representation_problem`.

''',
    marker="## Requirement representation taxonomy",
)

insert_after_once(
    path,
    "Every required requirement classified as `unrepresented` must have a material finding.",
    "\n\nEvery required requirement classified as `ambiguous` must also be surfaced, but do not label it missing work unless you independently establish that the correct representation is `work_item`.",
    marker="Every required requirement classified as `ambiguous`",
)

# ============================================================================
# Verification Refiner prompt
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/refiner.md"

insert_before_once(
    path,
    "## Refinement boundaries",
    '''## Requirement-representation repair policy

A coverage error does NOT automatically authorize a new work item.

When a finding says a required GDD statement is missing, ambiguous, or
misrepresented, classify the statement first:

- distinct executable/organizational responsibility -> `work_item`;
- behavior/constraint owned by an existing item -> `acceptance_criterion`;
- explicit test/check/inspection -> `validation_requirement`;
- required non-code obligation -> `non_code_requirement`;
- build/delivery obligation -> `delivery_requirement`;
- development-process invariant -> `pipeline_constraint`;
- required but intentionally underspecified design -> `deferred_design`;
- stretch/excluded scope -> `deferred_or_excluded`.

For acceptance criteria, add/correct the requirement under the mapped work
item's first-class `acceptance_criteria` field.

For validation requirements, add/correct the requirement under the mapped work
item's first-class `validation_requirements` field.

For delivery/non-code/pipeline constraints, preserve them under
`non_code_requirements` rather than manufacturing gameplay tasks.

For deferred design, keep the owning feature/work represented and use
`decomposition_state: needs_future_decomposition` when appropriate. Do not
invent the missing design.

Only add a new work item after establishing that `work_item` is the correct
representation type.

''',
    marker="## Requirement-representation repair policy",
)

text = read(path)
if "- every work item has `acceptance_criteria`, `validation_requirements`" not in text:
    variants = [
        "- every work item has an `execution_scope`, `execution_reason`, and `exclusive_resources`;",
        "- every work item has an `execution_scope` and `execution_reason`;",
    ]
    patched = False
    for old in variants:
        if old in text:
            if "exclusive_resources" in old:
                new = "- every work item has `acceptance_criteria`, `validation_requirements`, an `execution_scope`, `execution_reason`, and `exclusive_resources`;"
            else:
                new = "- every work item has `acceptance_criteria`, `validation_requirements`, an `execution_scope`, and an `execution_reason`;"
            text = text.replace(old, new, 1)
            write(path, text)
            print(f"patched: {path} [closure requirement detail]")
            patched = True
            break
    if not patched:
        raise RuntimeError("Could not find Refiner closure-check anchor")
else:
    print(f"already patched: {path} [closure requirement detail]")

# ============================================================================
# Verification smoke tests
# ============================================================================

path = "Pipeline/Reconciliation/verification_smoke_test.py"

insert_after_once(
    path,
    '    assert merged["findings"][0]["source_agent"] == "Deterministic Coverage Check"\n',
    r'''

    # Representation taxonomy: required statements do not all imply work items.
    taxonomy_ok = [
        {
            "agent": "GDD Coverage Auditor A",
            "requested_model": crew.MODEL_POOL[0],
            "result": {
                "requirements": [
                    {
                        "requirement_id": "REQ-ACCEPT",
                        "reference": "Section Test",
                        "requirement": "Behavior owned by an existing task",
                        "classification": "required_gameplay",
                        "representation": "acceptance_criterion",
                        "mapped_keys": ["existing-task"],
                        "explanation": "Acceptance criterion.",
                    },
                    {
                        "requirement_id": "REQ-VALIDATE",
                        "reference": "Section Test",
                        "requirement": "Explicit validation check",
                        "classification": "required_gameplay",
                        "representation": "validation_requirement",
                        "mapped_keys": ["existing-task"],
                        "explanation": "Validation requirement.",
                    },
                    {
                        "requirement_id": "REQ-PIPELINE",
                        "reference": "Section Test",
                        "requirement": "Do not concurrently modify one Unity asset",
                        "classification": "required_process",
                        "representation": "pipeline_constraint",
                        "mapped_keys": [],
                        "explanation": "Pipeline invariant.",
                    },
                    {
                        "requirement_id": "REQ-DELIVERY",
                        "reference": "Section Test",
                        "requirement": "Produce the Windows build",
                        "classification": "required_non_code",
                        "representation": "delivery_requirement",
                        "mapped_keys": [],
                        "explanation": "Delivery requirement.",
                    },
                ]
            },
        }
    ]
    assert crew.deterministic_audit_checks(taxonomy_ok) == []

    taxonomy_bad = [
        {
            "agent": "GDD Coverage Auditor A",
            "requested_model": crew.MODEL_POOL[0],
            "result": {
                "requirements": [
                    {
                        "requirement_id": "REQ-AMBIG",
                        "reference": "Section Test",
                        "requirement": "Required but mapping is unclear",
                        "classification": "required_gameplay",
                        "representation": "ambiguous",
                        "mapped_keys": [],
                        "explanation": "Ambiguous on purpose.",
                    },
                    {
                        "requirement_id": "REQ-WRONG-TYPE",
                        "reference": "Section Test",
                        "requirement": "Gameplay incorrectly called process",
                        "classification": "required_gameplay",
                        "representation": "pipeline_constraint",
                        "mapped_keys": [],
                        "explanation": "Wrong representation on purpose.",
                    },
                    {
                        "requirement_id": "REQ-NO-OWNER",
                        "reference": "Section Test",
                        "requirement": "Acceptance criterion without owner",
                        "classification": "required_gameplay",
                        "representation": "acceptance_criterion",
                        "mapped_keys": [],
                        "explanation": "Missing owner on purpose.",
                    },
                    {
                        "requirement_id": "REQ-STRETCH-LEAK",
                        "reference": "Section Test",
                        "requirement": "Stretch item incorrectly seeded",
                        "classification": "stretch",
                        "representation": "work_item",
                        "mapped_keys": ["bad-stretch-task"],
                        "explanation": "Scope leak on purpose.",
                    },
                ]
            },
        }
    ]
    taxonomy_findings = crew.deterministic_audit_checks(taxonomy_bad)
    assert len(taxonomy_findings) == 4
    categories = {
        item["finding"]["category"] for item in taxonomy_findings
    }
    assert "requirement_representation_problem" in categories
    assert "scope_leak" in categories
    ambiguous = next(
        item
        for item in taxonomy_findings
        if item["finding"]["finding_id"].endswith("REQ-AMBIG")
    )
    assert ambiguous["finding"]["requires_human_review"] is True
    assert "new work item" in ambiguous["finding"]["recommended_change"]
''',
    marker="# Representation taxonomy: required statements do not all imply work items.",
)

insert_before_once(
    path,
    '    print("verification smoke test passed")',
    r'''    requirement_legacy = {
        "work_items": [
            {"key": "legacy-requirement-task"},
        ]
    }
    requirement_upgraded = reconciliation.ensure_requirement_detail_defaults(
        requirement_legacy
    )
    assert requirement_upgraded == ["legacy-requirement-task"]
    assert requirement_legacy["work_items"][0]["acceptance_criteria"] == []
    assert requirement_legacy["work_items"][0]["validation_requirements"] == []

''',
    marker="requirement_upgraded = reconciliation.ensure_requirement_detail_defaults",
)

# ============================================================================
# README
# ============================================================================

path = "Pipeline/Reconciliation/README.md"

replace_once(
    path,
    "- GDD evidence;\n- current repository state;",
    "- GDD evidence;\n- first-class acceptance criteria;\n- first-class validation requirements;\n- current repository state;",
    marker="- first-class acceptance criteria;",
)

text = read(path)
if "## Requirement representation taxonomy" not in text:
    insertion_marker = "## Exclusive resources and concurrency"
    if insertion_marker not in text:
        insertion_marker = "## Verification refiner sizing and recovery"
    idx = text.find(insertion_marker)
    if idx < 0:
        raise RuntimeError("Could not find README insertion point for requirement taxonomy")
    addition = '''## Requirement representation taxonomy

A required GDD sentence does not automatically become a task.

The reconciliation/verification pipeline distinguishes:

- `work_item` — a distinct feature/artifact/implementation responsibility;
- `acceptance_criterion` — behavior/constraint owned by an existing task;
- `validation_requirement` — a test/check/inspection of mapped work;
- `non_code_requirement` — a required non-code obligation;
- `delivery_requirement` — a required build/delivery obligation;
- `pipeline_constraint` — a development-process invariant;
- `deferred_design` — required scope whose approved design is intentionally not
  concrete enough yet;
- `deferred_or_excluded` — stretch or explicitly excluded scope.

Work items carry `acceptance_criteria` and `validation_requirements` as
first-class structured fields so these requirements survive graph seeding
without becoming garbage microtasks.

The deterministic coverage check now reports ambiguous/misclassified
representation as `requirement_representation_problem`. It no longer equates
"required + ambiguous" with "missing task." A new task is created only after the
representation is established as `work_item`.

Examples:

- isometric sprite sorting check -> `validation_requirement`;
- Bone Archive lane/pathing check -> `validation_requirement`;
- Chapel of Ash occlusion check -> `validation_requirement`;
- encounter size 3–8 -> `acceptance_criterion`;
- Ranged Enemy not introduced alone -> `acceptance_criterion`;
- Windows build -> `delivery_requirement`;
- no concurrent edits to one Unity asset -> `pipeline_constraint`.

'''
    text = text[:idx] + addition + text[idx:]
    write(path, text)
    print(f"patched: {path} [Requirement representation taxonomy]")
else:
    print(f"already patched: {path} [Requirement representation taxonomy]")

text = read(path)
if "Required GDD statements are represented at the correct level:" not in text:
    anchors = [
        "10. Obvious shared file/scene/prefab integration surfaces are represented by identical `exclusive_resources` keys so otherwise-ready tasks cannot be dispatched concurrently against the same non-merge-safe resource.",
        "9. Every open executable item has a credible execution-scope classification before autonomous selection.",
    ]
    inserted = False
    for anchor in anchors:
        if anchor in text:
            number = "11" if anchor.startswith("10.") else "10"
            text = text.replace(
                anchor,
                anchor + f"\n{number}. Required GDD statements are represented at the correct level: work item, acceptance criterion, validation requirement, non-code/delivery requirement, pipeline constraint, or deferred design.",
                1,
            )
            write(path, text)
            print(f"patched: {path} [requirement taxonomy checklist]")
            inserted = True
            break
    if not inserted:
        raise RuntimeError("Could not find README human-review checklist anchor")

# ============================================================================
# Final marker verification
# ============================================================================

checks = {
    "Pipeline/Reconciliation/reconciliation_agent.py": [
        '"acceptance_criteria": {',
        '"validation_requirements": {',
        "def ensure_requirement_detail_defaults",
        '"acceptance_criteria": item.get("acceptance_criteria", [])',
        'lines.append("**Acceptance criteria**")',
    ],
    "Pipeline/Reconciliation/prompts/reconcile.md": [
        "# Requirement representation inside work items",
        "The goal is durable requirement coverage without garbage microtasks.",
    ],
    "Pipeline/Reconciliation/verification_crew.py": [
        '"acceptance_criterion",',
        '"pipeline_constraint",',
        '"deferred_design",',
        '"requirement_representation_problem"',
        "allowed_by_classification = {",
    ],
    "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md": [
        "## Requirement representation taxonomy",
        "Before reporting `missing_required_work`",
    ],
    "Pipeline/Reconciliation/prompts/verification/refiner.md": [
        "## Requirement-representation repair policy",
        "Only add a new work item after establishing",
    ],
    "Pipeline/Reconciliation/verification_smoke_test.py": [
        "# Representation taxonomy: required statements do not all imply work items.",
        "ensure_requirement_detail_defaults",
    ],
    "Pipeline/Reconciliation/README.md": [
        "## Requirement representation taxonomy",
        "first-class acceptance criteria",
    ],
}

missing = []
for file_path, markers in checks.items():
    text = read(file_path)
    for marker in markers:
        if marker not in text:
            missing.append(f"{file_path}: {marker}")

if missing:
    raise RuntimeError(
        "Requirement-representation taxonomy patch is incomplete:\n- "
        + "\n- ".join(missing)
    )

print()
print("Requirement-representation taxonomy patch applied successfully.")
print("Required GDD statements can now be represented without forcing one task per sentence.")
print()
print("Next command:")
print("docker compose run --rm claude python3 Pipeline/Reconciliation/verification_smoke_test.py")
