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
            f"Expected exactly one regex target in {path}; found {count}"
        )
    write(path, new_text)
    print(f"patched: {path} [{marker}]")


# ============================================================================
# PRECHECK: confirm the first half of the previous patch is present.
# ============================================================================

prechecks = {
    "Pipeline/Reconciliation/reconciliation_agent.py": [
        '"requirement_type": {',
        "def ensure_non_code_requirement_type_defaults",
    ],
    "Pipeline/Reconciliation/prompts/reconcile.md": [
        "Every non-code record must set `requirement_type`",
        "# Known runtime behavior vs deferred content authoring",
    ],
    "Pipeline/Reconciliation/verification_crew.py": [
        '"mapped_non_code_titles": {',
        "mapped_non_code_representations = {",
        "REFINER_WARNING_CATEGORIES = {",
        '"selected_structural_warning_count": selected_warning_count',
    ],
}

missing = []
for file_path, markers in prechecks.items():
    text = read(file_path)
    for marker in markers:
        if marker not in text:
            missing.append(f"{file_path}: {marker}")

if missing:
    raise RuntimeError(
        "The previous patch did not reach the expected partial state. "
        "Do not continue automatically.\n- " + "\n- ".join(missing)
    )


# ============================================================================
# 1) verification_crew.py
# Repair the partially patched Refiner selection function robustly.
# ============================================================================

path = "Pipeline/Reconciliation/verification_crew.py"

correct_build_refiner = '''def build_refiner_findings(merged: dict[str, Any]) -> dict[str, Any]:
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
            "This keeps refinement bounded while ensuring scheduler-relevant "
            "structural warnings are not invisible to the Refiner."
        ),
    }


'''

regex_replace_once(
    path,
    r'''def build_refiner_findings\(merged: dict\[str, Any\]\) -> dict\[str, Any\]:.*?(?=\n# ============================================================\n# BOUNDED REFINER)''',
    correct_build_refiner,
    marker="scheduler-relevant structural warnings are not invisible to the Refiner.",
)

replace_once(
    path,
    "        if has_material_findings(merged1) and not args.no_refine:\n",
    "        if has_refiner_relevant_findings(merged1) and not args.no_refine:\n",
    marker="if has_refiner_relevant_findings(merged1)",
)

# Make the runtime Refiner instruction match its new supplied input.
replace_once(
    path,
    '''        + "Read both inputs. Resolve every blocker/error finding with the current "
        + "GDD and repository as primary truth. If credible findings conflict and "
''',
    '''        + "Read both inputs. Resolve every supplied finding with the current "
        + "GDD and repository as primary truth. The supplied set contains every "
        + "blocker/error plus only selected scheduler-relevant structural warnings. "
        + "If credible findings conflict and "
''',
    marker="only selected scheduler-relevant structural warnings",
)


# ============================================================================
# 2) reconciliation_agent.py
# Strengthen first-class typed non-code storage so it survives seed proposals.
# ============================================================================

path = "Pipeline/Reconciliation/reconciliation_agent.py"

insert_before_once(
    path,
    "def _validate_unresolved_refs(",
    '''def _validate_non_code_requirements(payload: dict[str, Any]) -> None:
    allowed_types = {
        "non_code_requirement",
        "delivery_requirement",
        "pipeline_constraint",
    }
    seen_titles: set[str] = set()

    for item in payload.get("non_code_requirements", []):
        title = str(item.get("title", "")).strip()
        requirement_type = str(item.get("requirement_type", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        gdd_evidence = item.get("gdd_evidence", [])

        if not title:
            raise RuntimeError(
                "Every non-code requirement must have a non-empty title."
            )
        if title in seen_titles:
            raise RuntimeError(
                f"Duplicate non-code requirement title: {title!r}. "
                "Titles are mapping identifiers and must be unique."
            )
        seen_titles.add(title)

        if requirement_type not in allowed_types:
            raise RuntimeError(
                f"{title!r} has invalid requirement_type="
                f"{requirement_type!r}."
            )
        if not gdd_evidence:
            raise RuntimeError(
                f"{title!r} requires at least one GDD evidence entry."
            )
        if not evidence:
            raise RuntimeError(
                f"{title!r} requires non-empty evidence/status rationale."
            )


''',
    marker="def _validate_non_code_requirements(",
)

replace_once(
    path,
    '''    _validate_exclusive_resources(items_by_key)
    _validate_unresolved_refs(payload, items_by_key)
''',
    '''    _validate_exclusive_resources(items_by_key)
    _validate_non_code_requirements(payload)
    _validate_unresolved_refs(payload, items_by_key)
''',
    marker="    _validate_non_code_requirements(payload)",
)

# Preserve typed non-code records in the bootstrap/diff proposal.
replace_once(
    path,
    '''    task_files = sorted(TASKS_DIR.glob("*.yaml")) if TASKS_DIR.exists() else []
    work_items = payload.get("work_items", [])
''',
    '''    task_files = sorted(TASKS_DIR.glob("*.yaml")) if TASKS_DIR.exists() else []
    work_items = payload.get("work_items", [])
    non_code_requirements = payload.get("non_code_requirements", [])
''',
    marker='    non_code_requirements = payload.get("non_code_requirements", [])',
)

replace_once(
    path,
    '''            "exclusive_resource_groups": build_exclusive_resource_groups(
                work_items
            ),
            "proposed_changes": [],
''',
    '''            "exclusive_resource_groups": build_exclusive_resource_groups(
                work_items
            ),
            "proposed_non_code_records": [
                {
                    "title": item.get("title"),
                    "requirement_type": item.get("requirement_type"),
                    "status": item.get("status"),
                    "gdd_evidence": item.get("gdd_evidence", []),
                    "evidence": item.get("evidence", ""),
                }
                for item in non_code_requirements
            ],
            "proposed_changes": [],
''',
    marker='"proposed_non_code_records": [',
)

# Persistent-graph-present branch also needs these records for future deterministic diff.
replace_once(
    path,
    '''        "proposed_seed_records": [],
        "exclusive_resource_groups": build_exclusive_resource_groups(work_items),
        "proposed_changes": [],
''',
    '''        "proposed_seed_records": [],
        "exclusive_resource_groups": build_exclusive_resource_groups(work_items),
        "proposed_non_code_records": [
            {
                "title": item.get("title"),
                "requirement_type": item.get("requirement_type"),
                "status": item.get("status"),
                "gdd_evidence": item.get("gdd_evidence", []),
                "evidence": item.get("evidence", ""),
            }
            for item in non_code_requirements
        ],
        "proposed_changes": [],
''',
    marker='"proposed_non_code_records": [\n            {\n                "title": item.get("title")',
)

# Render those records in the graph-delta Markdown.
insert_before_once(
    path,
    '''    task_files = delta.get("task_files_observed", [])
''',
    '''    non_code = delta.get("proposed_non_code_records", [])
    if non_code:
        lines.append("## Proposed Non-Code / Delivery / Pipeline Records")
        lines.append("")
        lines.append("| Type | Title | Status | Evidence / rationale |")
        lines.append("|---|---|---|---|")
        for item in non_code:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(item.get("requirement_type")),
                        _cell(item.get("title")),
                        _cell(item.get("status")),
                        _cell(item.get("evidence")),
                    ]
                )
                + " |"
            )
        lines.append("")

''',
    marker='lines.append("## Proposed Non-Code / Delivery / Pipeline Records")',
)


# ============================================================================
# 3) Reconciliation prompt
# Finish typed-storage guidance.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/reconcile.md"

insert_after_once(
    path,
    "Do not collapse these categories back into an untyped generic record.",
    '''

Give every non-code record a concise UNIQUE title. Coverage auditors use the
exact title as a stable mapping identifier, so two separate requirements must
not reuse the same title.

Examples:

- `Windows build` -> `delivery_requirement`
- `No concurrent Unity asset edits` -> `pipeline_constraint`
- `Credentials outside source control` -> `pipeline_constraint`
''',
    marker="Coverage auditors use the exact title as a stable mapping identifier",
)


# ============================================================================
# 4) Coverage auditor prompt
# Require exact typed non-code record mapping.
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

For `non_code_requirement`, `delivery_requirement`, and
`pipeline_constraint`, set `mapped_non_code_titles` to the exact title(s) of
the matching typed record(s) in the candidate. For work-item-backed
representations, use an empty `mapped_non_code_titles` list.''',
    marker="set `mapped_non_code_titles` to the exact title",
)


# ============================================================================
# 5) Structure auditor prompt
# Make the encounter runtime split reliably material/actionable.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/structure_auditor.md"

insert_after_once(
    path,
    '''8. Does a `needs_future_decomposition` node defer only the design that is truly unknown, while preserving concrete foundations that are already required?''',
    '''
8a. Does any `needs_future_decomposition` feature also contain a fully
specified runtime mechanism that could already be implemented and validated
without inventing the deferred content? If so, the runtime mechanism must be
separated from the deferred authoring/content scope.''',
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

Do not invent deferred encounter content while performing this check.

''',
    marker="Treat a fully specified required runtime mechanism becoming",
)


# ============================================================================
# 6) Refiner prompt
# Selected structural warnings are mandatory inputs and encounter split is explicit.
# ============================================================================

path = "Pipeline/Reconciliation/prompts/verification/refiner.md"

replace_once(
    path,
    '''Warnings may be corrected when the correction is clearly supported and does not expand scope.
Suggestions are optional.
''',
    '''`REFINER_FINDINGS.json` may also contain selected structural warnings
(`under_decomposition`, `overgrouped_work`, or `shared_capability_hidden`).
Those warnings were deliberately included because they can make required work
undispatchable or hide real prerequisites. Verify and correct every supplied
structural warning when the GDD/current repository supports the finding.
Ordinary warnings remain outside Refiner input and are reassessed in pass 2.

Suggestions are optional.
''',
    marker="Those warnings were deliberately included because they can make required work",
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
4. give it only concrete dependencies established by canon/current architecture.

Current GDD check: encounter authoring may still need future design for exact
placements, trigger positions, room compositions, and durability values, but
the active-enemy ceiling enforcement is already specified. The runtime
activation mechanism must enforce that when existing pursuers plus a new
encounter would exceed fifteen active enemies, new encounter activation is
delayed/reduced first and existing pursuers are never removed. If encounter
work combines this runtime mechanism with deferred authoring, split them rather
than making the runtime mechanism undispatchable.

''',
    marker="## Known-runtime / deferred-authoring split invariant",
)

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
- every non-code record has the correct `requirement_type`, with build/delivery
  obligations represented as `delivery_requirement` and development-agent/tool
  invariants represented as `pipeline_constraint` when supported by the GDD;
- no fully specified runtime mechanism is hidden only inside a
  `needs_future_decomposition` authoring/content feature;''',
    marker="every non-code record has the correct `requirement_type`",
)


# ============================================================================
# 7) verification_smoke_test.py
# Update schema fixtures and test structural-warning selection.
# ============================================================================

path = "Pipeline/Reconciliation/verification_smoke_test.py"
text = read(path)

if '"mapped_non_code_titles"' not in text:
    lines = text.splitlines()
    out = []
    current_requirement_id = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"requirement_id":'):
            try:
                current_requirement_id = stripped.split('"', 3)[3]
            except Exception:
                current_requirement_id = None

        out.append(line)

        if stripped.startswith('"mapped_keys":'):
            indent = line[: len(line) - len(line.lstrip())]
            if current_requirement_id == "REQ-PIPELINE":
                value = '["No concurrent Unity asset edits"]'
            elif current_requirement_id == "REQ-DELIVERY":
                value = '["Windows build"]'
            else:
                value = "[]"
            out.append(
                f'{indent}"mapped_non_code_titles": {value},'
            )

    write(path, "\n".join(out) + "\n")
    print(f"patched: {path} [mapped_non_code_titles fixtures]")
else:
    print(f"already patched: {path} [mapped_non_code_titles fixtures]")

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
# 8) README
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
represented merely because the GDD mentions it. The proposed graph delta also
preserves these typed records so they are not dropped when the persistent work
graph is seeded or reconciled.
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
# FINAL CONSISTENCY CHECKS
# ============================================================================

checks = {
    "Pipeline/Reconciliation/reconciliation_agent.py": [
        '"requirement_type": {',
        "def ensure_non_code_requirement_type_defaults",
        "def _validate_non_code_requirements",
        '"proposed_non_code_records": [',
        'lines.append("## Proposed Non-Code / Delivery / Pipeline Records")',
    ],
    "Pipeline/Reconciliation/prompts/reconcile.md": [
        "Every non-code record must set `requirement_type`",
        "# Known runtime behavior vs deferred content authoring",
        "Coverage auditors use the exact title as a stable mapping identifier",
    ],
    "Pipeline/Reconciliation/verification_crew.py": [
        '"mapped_non_code_titles": {',
        "mapped_non_code_representations = {",
        "REFINER_WARNING_CATEGORIES = {",
        "def has_refiner_relevant_findings",
        "scheduler-relevant structural warnings are not invisible to the Refiner.",
        "if has_refiner_relevant_findings(merged1)",
        "only selected scheduler-relevant structural warnings",
    ],
    "Pipeline/Reconciliation/prompts/verification/coverage_auditor.md": [
        "MUST map through `mapped_non_code_titles`",
    ],
    "Pipeline/Reconciliation/prompts/verification/structure_auditor.md": [
        "8a. Does any `needs_future_decomposition` feature",
        "under_decomposition` **error**",
    ],
    "Pipeline/Reconciliation/prompts/verification/refiner.md": [
        "Those warnings were deliberately included because they can make required work",
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
        "Continuation patch is incomplete:\n- " + "\n- ".join(missing)
    )

print()
print("Typed non-code + encounter-refinement continuation completed successfully.")
print("The previous partial edits were preserved; no rollback was performed.")
print()
print("Next command:")
print(
    "docker compose run --rm claude python3 "
    "Pipeline/Reconciliation/verification_smoke_test.py"
)
