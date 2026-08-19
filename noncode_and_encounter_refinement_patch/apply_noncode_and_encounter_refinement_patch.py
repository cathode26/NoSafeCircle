from __future__ import annotations

from pathlib import Path

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


# ============================================================================
# 1) reconciliation_agent.py
# First-class typed non-code/delivery/pipeline storage.
# ============================================================================

path = "Pipeline/Reconciliation/reconciliation_agent.py"

replace_once(
    path,
    '''NON_CODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["confirmed", "not_assessable", "unknown"],
        },
        "gdd_evidence": {"type": "array", "items": GDD_EVIDENCE_SCHEMA},
        "evidence": {"type": "string"},
    },
    "required": ["title", "status", "gdd_evidence", "evidence"],
}
''',
    '''NON_CODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "requirement_type": {
            "type": "string",
            "enum": [
                "non_code_requirement",
                "delivery_requirement",
                "pipeline_constraint",
            ],
        },
        "status": {
            "type": "string",
            "enum": ["confirmed", "not_assessable", "unknown"],
        },
        "gdd_evidence": {"type": "array", "items": GDD_EVIDENCE_SCHEMA},
        "evidence": {"type": "string"},
    },
    "required": [
        "title",
        "requirement_type",
        "status",
        "gdd_evidence",
        "evidence",
    ],
}
''',
    marker='"requirement_type": {\n            "type": "string",\n            "enum": [\n                "non_code_requirement"',
)

insert_before_once(
    path,
    "def ensure_requirement_detail_defaults(",
    '''def ensure_non_code_requirement_type_defaults(
    payload: dict[str, Any],
) -> list[str]:
    # Upgrade legacy reconciliation candidates that predate typed non-code records.
    upgraded: list[str] = []
    for item in payload.get("non_code_requirements", []):
        if item.get("requirement_type"):
            continue
        item["requirement_type"] = "non_code_requirement"
        upgraded.append(str(item.get("title", "")))
    return upgraded


''',
    marker="def ensure_non_code_requirement_type_defaults(",
)

replace_once(
    path,
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_requirement_detail_defaults(payload)
''',
    '''def run_semantic_validation(payload: dict[str, Any]) -> None:
    ensure_non_code_requirement_type_defaults(payload)
    ensure_requirement_detail_defaults(payload)
''',
    marker="    ensure_non_code_requirement_type_defaults(payload)\n    ensure_requirement_detail_defaults(payload)",
)

# Render typed non-code records.
replace_once(
    path,
    '''            lines.append(
                f"- **[{_cell(item.get('status'))}] "
                f"{_cell(item.get('title'))}:** "
                f"{_cell(item.get('evidence'))}"
            )
''',
    '''            lines.append(
                f"- **[{_cell(item.get('requirement_type'))} / "
                f"{_cell(item.get('status'))}] "
                f"{_cell(item.get('title'))}:** "
                f"{_cell(item.get('evidence'))}"
            )
''',
    marker="item.get('requirement_type'))} /",
)

# ============================================================================
# 2) Reconciliation prompt
# Require typed records and separate known runtime mechanism from deferred design.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/reconcile.md"

insert_after_once(
    path,
    '''# Non-code requirements

Report required non-code/build/delivery requirements separately.
''',
    '''
Every non-code record must set `requirement_type`:

- `non_code_requirement` — a required non-code obligation that is neither
  primarily a build/delivery obligation nor a pipeline invariant;
- `delivery_requirement` — a required build/submission/delivery obligation such
  as the Windows build;
- `pipeline_constraint` — a required development-process invariant such as
  human inspection gates, source-control/credential constraints, or rules that
  limit concurrent agent changes.

Do not collapse these categories back into an untyped generic record.
''',
    marker="Every non-code record must set `requirement_type`",
)

insert_before_once(
    path,
    "# Work kinds",
    '''# Known runtime behavior vs deferred content authoring

A feature may contain BOTH:

1. a fully specified runtime mechanism that can already be implemented from
   approved GDD rules; and
2. content/authoring details whose exact design is still intentionally unknown.

Do not hide (1) behind `needs_future_decomposition` merely because (2) is
unknown.

When this happens:

- preserve the unknown authoring/content scope as a feature using
  `needs_future_decomposition`;
- create a separate concrete/coarse implementation work item for the already
  specified runtime mechanism;
- attach the runtime acceptance criteria and validation requirements to that
  implementation item;
- use real dependencies only for concrete prerequisites.

Current GDD example: encounter placement/composition/trigger details and exact
per-door durability values may remain deferred authoring, but the activation
rule that enforces the fifteen-active-enemy ceiling is already specified:
new-encounter activation is delayed/reduced first and existing pursuers are
never removed. That runtime enforcement must not become undispatchable merely
because room-specific encounter authoring is deferred.

''',
    marker="# Known runtime behavior vs deferred content authoring",
)

# ============================================================================
# 3) verification_crew.py
# Link coverage records to typed non-code storage and select structural warnings
# for refinement without reopening all warnings.
# ============================================================================

path = "Pipeline/Reconciliation/verification_crew.py"

# Coverage schema: optional structurally linked non-code titles.
replace_once(
    path,
    '''        "mapped_keys": {
            "type": "array",
            "items": {"type": "string"},
        },
        "explanation": {"type": "string"},
''',
    '''        "mapped_keys": {
            "type": "array",
            "items": {"type": "string"},
        },
        "mapped_non_code_titles": {
            "type": "array",
            "items": {"type": "string"},
        },
        "explanation": {"type": "string"},
''',
    marker='"mapped_non_code_titles": {',
)

replace_once(
    path,
    '''        "representation",
        "mapped_keys",
        "explanation",
''',
    '''        "representation",
        "mapped_keys",
        "mapped_non_code_titles",
        "explanation",
''',
    marker='        "mapped_non_code_titles",',
)

# Deterministic mapping policy: typed non-code representations need a mapped record.
replace_once(
    path,
    '''    mapped_key_representations = {
        "work_item",
        "acceptance_criterion",
        "validation_requirement",
        "deferred_design",
    }
''',
    '''    mapped_key_representations = {
        "work_item",
        "acceptance_criterion",
        "validation_requirement",
        "deferred_design",
    }
    mapped_non_code_representations = {
        "non_code_requirement",
        "delivery_requirement",
        "pipeline_constraint",
    }
''',
    marker="mapped_non_code_representations = {",
)

replace_once(
    path,
    '''            mapped_keys = [
                str(value)
                for value in requirement.get("mapped_keys", [])
                if str(value).strip()
            ]

            problem: str | None = None
''',
    '''            mapped_keys = [
                str(value)
                for value in requirement.get("mapped_keys", [])
                if str(value).strip()
            ]
            mapped_non_code_titles = [
                str(value)
                for value in requirement.get("mapped_non_code_titles", [])
                if str(value).strip()
            ]

            problem: str | None = None
''',
    marker="mapped_non_code_titles = [",
)

replace_once(
    path,
    '''                elif (
                    representation in mapped_key_representations
                    and not mapped_keys
                ):
                    problem = (
                        f"{representation!r} requires at least one mapped work "
                        "key so the requirement cannot be silently lost."
                    )
''',
    '''                elif (
                    representation in mapped_key_representations
                    and not mapped_keys
                ):
                    problem = (
                        f"{representation!r} requires at least one mapped work "
                        "key so the requirement cannot be silently lost."
                    )
                elif (
                    representation in mapped_non_code_representations
                    and not mapped_non_code_titles
                ):
                    problem = (
                        f"{representation!r} requires at least one mapped typed "
                        "non-code record title so the requirement cannot be "
                        "silently claimed without durable storage."
                    )
''',
    marker="requires at least one mapped typed",
)

# Add narrowly selected warnings to Refiner input and allow them to trigger refinement.
insert_before_once(
    path,
    "def has_material_findings(merged: dict[str, Any]) -> bool:",
    '''REFINER_WARNING_CATEGORIES = {
    "under_decomposition",
    "overgrouped_work",
    "shared_capability_hidden",
}


def is_refiner_relevant_report(report: dict[str, Any]) -> bool:
    finding = report.get("finding", {})
    severity = str(finding.get("severity", ""))
    category = str(finding.get("category", ""))

    if severity in {"blocker", "error"}:
        return True

    return (
        severity == "warning"
        and category in REFINER_WARNING_CATEGORIES
    )


def has_refiner_relevant_findings(merged: dict[str, Any]) -> bool:
    return any(
        is_refiner_relevant_report(report)
        for report in merged.get("findings", [])
    )


''',
    marker="REFINER_WARNING_CATEGORIES = {",
)

replace_once(
    path,
    '''def build_refiner_findings(merged: dict[str, Any]) -> dict[str, Any]:
    # The Refiner's mandatory job is blocker/error repair. Warnings and
    # suggestions remain in the full pass-1 merge and are independently
    # reassessed during pass 2.
    material = [
        report
        for report in merged.get("findings", [])
        if report.get("finding", {}).get("severity") in {"blocker", "error"}
    ]
    return {
        "schema_version": "1.0",
        "source_finding_count": int(merged.get("finding_count", 0)),
        "material_finding_count": len(material),
        "findings": material,
        "selection_policy": (
            "Refiner input contains blocker/error findings only. Warnings and "
            "suggestions remain in MERGED_FINDINGS_PASS1.json and are checked "
''',
    '''def build_refiner_findings(merged: dict[str, Any]) -> dict[str, Any]:
    selected = [
        report
        for report in merged.get("findings", [])
        if is_refiner_relevant_report(report)
    ]
    material_count = sum(
        1
        for report in selected
        if report.get("finding", {}).get("severity")
        in {"blocker", "error"}
    )
    selected_warning_count = len(selected) - material_count

    return {
        "schema_version": "1.1",
        "source_finding_count": int(merged.get("finding_count", 0)),
        "material_finding_count": material_count,
        "selected_finding_count": len(selected),
        "selected_structural_warning_count": selected_warning_count,
        "findings": selected,
        "selection_policy": (
            "Refiner input contains all blocker/error findings plus warnings "
            "whose categories indicate hidden/overgrouped/under-decomposed "
            "required work. Ordinary warnings and suggestions remain in "
            "MERGED_FINDINGS_PASS1.json and are reassessed during pass 2. "
''',
    marker='"selected_structural_warning_count": selected_warning_count',
)

# The tail of selection_policy still contains old prose; replace its final sentence.
replace_once(
    path,
    '''            "independently during pass 2."
        ),
    }
''',
    '''            "This keeps refinement bounded while ensuring scheduler-relevant "
            "structural warnings are not invisible to the Refiner."
        ),
    }
''',
    marker="scheduler-relevant structural warnings are not invisible",
)

replace_once(
    path,
    '''        if has_material_findings(merged1) and not args.no_refine:
''',
    '''        if has_refiner_relevant_findings(merged1) and not args.no_refine:
''',
    marker="if has_refiner_relevant_findings(merged1)",
)

# ============================================================================
# 4) Coverage auditor prompt
# Require exact mapping to typed non-code records.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md"

replace_once(
    path,
    '''- `delivery_requirement`, `non_code_requirement`, and `pipeline_constraint`
  may legitimately have no work key because they are not executable gameplay
  nodes.
''',
    '''- `delivery_requirement`, `non_code_requirement`, and `pipeline_constraint`
  may legitimately have no work key because they are not executable gameplay
  nodes, but they MUST map through `mapped_non_code_titles` to one or more
  actual records in the candidate's `non_code_requirements` array.
- For those typed non-code representations, the referenced candidate record's
  `requirement_type` must exactly match the representation value.
''',
    marker="MUST map through `mapped_non_code_titles`",
)

insert_after_once(
    path,
    '''Map `mapped_keys` to the owning work item(s).''',
    '''

For any `non_code_requirement`, `delivery_requirement`, or
`pipeline_constraint`, set `mapped_non_code_titles` to the exact title(s) of
the matching typed record(s) in the candidate. For work-item-backed
representations, normally use an empty `mapped_non_code_titles` list.''',
    marker="set `mapped_non_code_titles` to the exact title",
)

# ============================================================================
# 5) Structure auditor prompt
# Make the known-runtime/deferred-authoring split scheduler-safety relevant.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/structure_auditor.md"

insert_after_once(
    path,
    '''8. Does a `needs_future_decomposition` node defer only the design that is truly unknown, while preserving concrete foundations that are already required?''',
    '''
8a. Does any `needs_future_decomposition` feature also own a fully specified
runtime mechanism that could already be implemented and validated without
inventing the deferred content? If so, the runtime mechanism must be separated
from the deferred authoring/content scope.''',
    marker="8a. Does any `needs_future_decomposition` feature",
)

insert_before_once(
    path,
    "If ordering is uncertain, report it rather than inventing certainty.",
    '''Treat a fully specified required runtime mechanism becoming
**undispatchable** solely because it is bundled inside deferred content
authoring as an `under_decomposition` **error**, not merely a warning. That
structure can cause `taskcontrol ready` to hide required work indefinitely.

For this GDD, specifically test encounter work for the distinction between:

- deferred per-room placements, trigger positions, exact compositions, and
  durability authoring; versus
- the already-specified runtime activation/cap rule that delays or reduces new
  encounter activation before ever removing persistent pursuers.

Do not invent the deferred encounter content while performing this check.

''',
    marker="Treat a fully specified required runtime mechanism becoming",
)

# ============================================================================
# 6) Refiner prompt
# Selected structural warnings are actionable + explicit encounter invariant.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/refiner.md"

replace_once(
    path,
    '''Warnings may be corrected when the correction is clearly supported and does not expand scope.
Suggestions are optional.
''',
    '''`REFINER_FINDINGS.json` may also contain selected structural warnings
(`under_decomposition`, `overgrouped_work`, or `shared_capability_hidden`).
Those warnings were deliberately promoted into the bounded Refiner input
because they can make required work undispatchable or hide real prerequisites.
Verify them and correct them when the GDD/current repository supports the
finding. Ordinary warnings remain outside the Refiner input and are reassessed
in pass 2.

Suggestions are optional.
''',
    marker="selected structural warnings",
)

insert_before_once(
    path,
    "## Refinement boundaries",
    '''## Known-runtime / deferred-authoring split invariant

Do not leave a fully specified executable runtime responsibility solely inside
a feature marked `needs_future_decomposition` just because that feature also
contains content/authoring details that are still unknown.

When both are mixed:

1. keep the unknown authoring/content scope deferred;
2. create or preserve a separate implementation item for the already-specified
   runtime mechanism;
3. move the runtime acceptance criteria and validation requirements to that
   implementation item;
4. give it only the concrete dependencies established by canon/current
   architecture.

Current GDD check: encounter authoring may still need future design for exact
placements, trigger positions, room compositions, and durability values, but
the active-enemy ceiling enforcement is already specified. The runtime
activation mechanism must enforce that when existing pursuers plus a new
encounter would exceed fifteen active enemies, new encounter activation is
delayed/reduced first and existing pursuers are never removed. If encounter
work combines this runtime mechanism with deferred authoring, split them rather
than making the runtime mechanism `not_applicable`/undispatchable.

''',
    marker="## Known-runtime / deferred-authoring split invariant",
)

# Typed non-code Refiner rules.
replace_once(
    path,
    '''For delivery/non-code/pipeline constraints, preserve them under
`non_code_requirements` rather than manufacturing gameplay tasks.
''',
    '''For delivery/non-code/pipeline constraints, preserve them under
`non_code_requirements` rather than manufacturing gameplay tasks, and set each
record's `requirement_type` to exactly one of `non_code_requirement`,
`delivery_requirement`, or `pipeline_constraint`.
''',
    marker="record's `requirement_type` to exactly one",
)

insert_after_once(
    path,
    '''- missing design remains marked for future decomposition instead of invented;''',
    '''
- every non-code record has the correct `requirement_type`, with Windows/build
  obligations represented as `delivery_requirement` and development-agent/tool
  invariants represented as `pipeline_constraint` when supported by the GDD;
- no fully specified runtime mechanism is hidden only inside a
  `needs_future_decomposition` authoring/content feature;''',
    marker="every non-code record has the correct `requirement_type`",
)

# ============================================================================
# 7) verification_smoke_test.py
# Update coverage schema fixtures and refiner-selection behavior.
# ============================================================================

path = "Pipeline/Reconciliation/verification_smoke_test.py"

# Add mapped_non_code_titles after all mapped_keys entries in this smoke test
# if not already present. We do this conservatively line-by-line.
text = read(path)
if '"mapped_non_code_titles"' not in text:
    lines = text.splitlines()
    out = []
    for idx, line in enumerate(lines):
        out.append(line)
        stripped = line.strip()
        if stripped.startswith('"mapped_keys":'):
            indent = line[: len(line) - len(line.lstrip())]
            # Valid pipeline/delivery fixtures need a real typed non-code mapping.
            nearby = "\n".join(lines[max(0, idx - 8): idx + 2])
            if '"requirement_id": "REQ-PIPELINE"' in nearby:
                value = '["No concurrent Unity asset edits"]'
            elif '"requirement_id": "REQ-DELIVERY"' in nearby:
                value = '["Windows build"]'
            else:
                value = "[]"
            out.append(f'{indent}"mapped_non_code_titles": {value},')
    write(path, "\n".join(out) + "\n")
    print(f"patched: {path} [mapped_non_code_titles fixtures]")
else:
    print(f"already patched: {path} [mapped_non_code_titles fixtures]")

# Replace Refiner selection test.
replace_once(
    path,
    '''    refiner_findings = crew.build_refiner_findings(
        {
            "finding_count": 3,
            "findings": [
                {"finding": {"severity": "error", "title": "must fix"}},
                {"finding": {"severity": "warning", "title": "recheck later"}},
                {"finding": {"severity": "suggestion", "title": "optional"}},
            ],
        }
    )
    assert refiner_findings["source_finding_count"] == 3
    assert refiner_findings["material_finding_count"] == 1
    assert len(refiner_findings["findings"]) == 1
    assert refiner_findings["findings"][0]["finding"]["title"] == "must fix"
''',
    '''    refiner_findings = crew.build_refiner_findings(
        {
            "finding_count": 4,
            "findings": [
                {
                    "finding": {
                        "severity": "error",
                        "category": "missing_required_work",
                        "title": "must fix",
                    }
                },
                {
                    "finding": {
                        "severity": "warning",
                        "category": "under_decomposition",
                        "title": "structural warning must refine",
                    }
                },
                {
                    "finding": {
                        "severity": "warning",
                        "category": "other",
                        "title": "ordinary warning waits for pass2",
                    }
                },
                {
                    "finding": {
                        "severity": "suggestion",
                        "category": "other",
                        "title": "optional",
                    }
                },
            ],
        }
    )
    assert refiner_findings["source_finding_count"] == 4
    assert refiner_findings["material_finding_count"] == 1
    assert refiner_findings["selected_finding_count"] == 2
    assert refiner_findings["selected_structural_warning_count"] == 1
    assert len(refiner_findings["findings"]) == 2
    assert {
        item["finding"]["title"]
        for item in refiner_findings["findings"]
    } == {"must fix", "structural warning must refine"}
    assert crew.has_refiner_relevant_findings(
        {
            "findings": [
                {
                    "finding": {
                        "severity": "warning",
                        "category": "under_decomposition",
                    }
                }
            ]
        }
    )
''',
    marker="structural warning must refine",
)

# Add non-code legacy default smoke test.
insert_before_once(
    path,
    '    print("verification smoke test passed")',
    '''    non_code_legacy = {
        "non_code_requirements": [
            {
                "title": "Legacy requirement",
                "status": "unknown",
                "gdd_evidence": [],
                "evidence": "Legacy candidate",
            }
        ]
    }
    non_code_upgraded = (
        reconciliation.ensure_non_code_requirement_type_defaults(
            non_code_legacy
        )
    )
    assert non_code_upgraded == ["Legacy requirement"]
    assert (
        non_code_legacy["non_code_requirements"][0]["requirement_type"]
        == "non_code_requirement"
    )

''',
    marker="non_code_upgraded = (",
)

# ============================================================================
# 8) README.md
# ============================================================================

path = "Pipeline/Reconciliation/README.md"

insert_after_once(
    path,
    '''- no concurrent edits to one Unity asset -> `pipeline_constraint`.
''',
    '''

Non-code requirements are stored as first-class typed records with
`requirement_type`:

- `non_code_requirement`
- `delivery_requirement`
- `pipeline_constraint`

Coverage auditors name the exact stored record through
`mapped_non_code_titles`; they cannot claim a delivery/process requirement is
represented merely because the GDD mentions it.
''',
    marker="Coverage auditors name the exact stored record",
)

replace_once(
    path,
    '''Only `blocker` and `error` findings are sent to the Refiner. Warnings and
suggestions remain preserved in the full pass-1 merge and are reassessed by the
independent pass-2 auditors.
''',
    '''All `blocker` and `error` findings are sent to the Refiner. In addition,
warnings in the narrowly selected structural categories
`under_decomposition`, `overgrouped_work`, and `shared_capability_hidden` are
also sent because they can make required work undispatchable or hide real
prerequisites. Other warnings and suggestions remain preserved in the full
pass-1 merge and are reassessed by the independent pass-2 auditors.
''',
    marker="narrowly selected structural categories",
)

insert_before_once(
    path,
    "## Important rules",
    '''## Deferred authoring must not hide known runtime work

`needs_future_decomposition` applies only to the design/content that is truly
unknown. If the same feature also contains a runtime rule already fully
specified by the GDD, reconciliation/refinement must split that runtime
responsibility into an implementation item rather than making it
undispatchable.

For encounter work this means room-specific placements, trigger positions,
exact compositions, and durability values may remain deferred, while the
specified active-enemy-ceiling activation rule is tracked as executable runtime
work.

''',
    marker="## Deferred authoring must not hide known runtime work",
)

# ============================================================================
# Final verification
# ============================================================================

checks = {
    "Pipeline/Reconciliation/reconciliation_agent.py": [
        '"requirement_type": {',
        "def ensure_non_code_requirement_type_defaults",
        "item.get('requirement_type'))} /",
    ],
    "Pipeline/Reconciliation/prompts/reconcile.md": [
        "Every non-code record must set `requirement_type`",
        "# Known runtime behavior vs deferred content authoring",
    ],
    "Pipeline/Reconciliation/verification_crew.py": [
        '"mapped_non_code_titles": {',
        "mapped_non_code_representations = {",
        "REFINER_WARNING_CATEGORIES = {",
        "def has_refiner_relevant_findings",
        '"selected_structural_warning_count": selected_warning_count',
        "if has_refiner_relevant_findings(merged1)",
    ],
    "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md": [
        "MUST map through `mapped_non_code_titles`",
    ],
    "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": [
        "8a. Does any `needs_future_decomposition` feature",
        "undispatchable",
    ],
    "Pipeline/Reconciliation/prompts/verification/refiner.md": [
        "selected structural warnings",
        "## Known-runtime / deferred-authoring split invariant",
        "record's `requirement_type` to exactly one",
    ],
    "Pipeline/Reconciliation/verification_smoke_test.py": [
        '"mapped_non_code_titles"',
        "structural warning must refine",
        "ensure_non_code_requirement_type_defaults",
    ],
    "Pipeline/Reconciliation/README.md": [
        "Coverage auditors name the exact stored record",
        "narrowly selected structural categories",
        "## Deferred authoring must not hide known runtime work",
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
        "Patch is incomplete:\n- " + "\n- ".join(missing)
    )

print()
print("Typed non-code storage + encounter refinement visibility patch applied.")
print("Next command:")
print(
    "docker compose run --rm claude python3 "
    "Pipeline/Reconciliation/verification_smoke_test.py"
)
