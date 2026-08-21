from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()

VERIFICATION = ROOT / "Pipeline" / "Reconciliation" / "verification_crew.py"
PARALLEL = ROOT / "Pipeline" / "Reconciliation" / "parallel_verification_crew.py"
REFINER_PROMPT = ROOT / "Pipeline" / "Reconciliation" / "prompts" / "verification" / "refiner.md"
SMOKE = ROOT / "Pipeline" / "Reconciliation" / "verification_smoke_test.py"
RESUME = ROOT / "Pipeline" / "Reconciliation" / "resume_parallel_refinement.py"

MARKER = "REFINER_DELTA_SCHEMA"


def require(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing expected repository file: {path}")
    return path.read_text(encoding="utf-8-sig")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly one matching block, found {count}. "
            "Repository may have changed since this patch was prepared."
        )
    return text.replace(old, new, 1)


def patch_verification_crew() -> None:
    text = require(VERIFICATION)
    if MARKER in text:
        print("verification_crew.py already contains delta refiner support; skipping core insertion.")
        return

    text = replace_once(
        text,
        "import argparse\nimport json\n",
        "import argparse\nimport copy\nimport json\n",
        "verification imports",
    )

    text = replace_once(
        text,
        "    CLAUDE_DISALLOWED_TOOLS,\n    RECONCILIATION_SCHEMA,\n",
        "    CLAUDE_DISALLOWED_TOOLS,\n"
        "    RECONCILIATION_SCHEMA,\n"
        "    WORK_ITEM_SCHEMA,\n"
        "    NON_CODE_SCHEMA,\n"
        "    DEFERRED_SCHEMA,\n"
        "    UNRESOLVED_SCHEMA,\n",
        "reconciliation schema imports",
    )

    text = replace_once(
        text,
        '        "refiner_findings": run_dir / "REFINER_FINDINGS.json",\n'
        '        "refined_raw": run_dir / "refined_candidate.raw.json",\n',
        '        "refiner_findings": run_dir / "REFINER_FINDINGS.json",\n'
        '        "refiner_delta": run_dir / "REFINER_DELTA.json",\n'
        '        "refined_raw": run_dir / "refined_candidate.raw.json",\n',
        "verification output paths",
    )

    delta_block = r'''
REFINER_RESOLUTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_agent": {"type": "string"},
        "finding_id": {"type": "string"},
        "disposition": {
            "type": "string",
            "enum": [
                "corrected",
                "preserved_unresolved",
                "rejected_as_unsupported",
            ],
        },
        "explanation": {"type": "string"},
    },
    "required": [
        "source_agent",
        "finding_id",
        "disposition",
        "explanation",
    ],
}

REFINER_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "desired_state_summary": {"type": "string"},
        "current_state_summary": {"type": "string"},
        "major_findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "desired_state_summary",
        "current_state_summary",
        "major_findings",
    ],
}

REFINER_SEED_ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ready", "ready_with_warnings", "blocked"],
        },
        "blockers": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "blockers", "warnings"],
}

REFINER_DELTA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": REFINER_SUMMARY_SCHEMA,
        "seed_assessment": REFINER_SEED_ASSESSMENT_SCHEMA,
        "files_reviewed_add": {"type": "array", "items": {"type": "string"}},
        "historical_sources_reviewed_add": {
            "type": "array",
            "items": {"type": "string"},
        },
        "work_items_upsert": {"type": "array", "items": WORK_ITEM_SCHEMA},
        "work_item_keys_remove": {"type": "array", "items": {"type": "string"}},
        "non_code_requirements_upsert": {
            "type": "array",
            "items": NON_CODE_SCHEMA,
        },
        "non_code_requirement_titles_remove": {
            "type": "array",
            "items": {"type": "string"},
        },
        "deferred_or_excluded_upsert": {
            "type": "array",
            "items": DEFERRED_SCHEMA,
        },
        "deferred_or_excluded_titles_remove": {
            "type": "array",
            "items": {"type": "string"},
        },
        "unresolved_questions_upsert": {
            "type": "array",
            "items": UNRESOLVED_SCHEMA,
        },
        "unresolved_question_texts_remove": {
            "type": "array",
            "items": {"type": "string"},
        },
        "finding_resolutions": {
            "type": "array",
            "items": REFINER_RESOLUTION_SCHEMA,
            "minItems": 1,
        },
        "reasoning": {"type": "string"},
    },
    "required": [
        "summary",
        "seed_assessment",
        "files_reviewed_add",
        "historical_sources_reviewed_add",
        "work_items_upsert",
        "work_item_keys_remove",
        "non_code_requirements_upsert",
        "non_code_requirement_titles_remove",
        "deferred_or_excluded_upsert",
        "deferred_or_excluded_titles_remove",
        "unresolved_questions_upsert",
        "unresolved_question_texts_remove",
        "finding_resolutions",
        "reasoning",
    ],
}


def validate_refiner_resolutions(
    delta: dict[str, Any],
    refiner_findings: dict[str, Any],
) -> None:
    expected = Counter()
    for report in refiner_findings.get("findings", []):
        finding = report.get("finding", {})
        pair = (
            str(report.get("source_agent", "")).strip(),
            str(finding.get("finding_id", "")).strip(),
        )
        if not all(pair):
            raise RuntimeError(
                "REFINER_FINDINGS contains a finding without source_agent/finding_id."
            )
        expected[pair] += 1

    actual = Counter()
    for resolution in delta.get("finding_resolutions", []):
        pair = (
            str(resolution.get("source_agent", "")).strip(),
            str(resolution.get("finding_id", "")).strip(),
        )
        if not all(pair):
            raise RuntimeError(
                "Refiner delta contains a resolution without source_agent/finding_id."
            )
        actual[pair] += 1

    if actual != expected:
        missing = list((expected - actual).elements())
        extra = list((actual - expected).elements())
        details: list[str] = []
        if missing:
            details.append(f"missing resolutions: {missing}")
        if extra:
            details.append(f"unexpected/duplicate resolutions: {extra}")
        raise RuntimeError(
            "Refiner delta must resolve every supplied finding exactly once; "
            + "; ".join(details)
        )


def _unique_field_values(
    records: list[dict[str, Any]],
    field: str,
    label: str,
) -> None:
    values = [str(record.get(field, "")).strip() for record in records]
    if any(not value for value in values):
        raise RuntimeError(f"{label} contains a blank {field}.")
    duplicates = sorted(
        value for value, count in Counter(values).items() if count > 1
    )
    if duplicates:
        raise RuntimeError(
            f"{label} contains duplicate {field} values: {duplicates}"
        )


def _apply_record_delta(
    existing: list[dict[str, Any]],
    upserts: list[dict[str, Any]],
    removes: list[str],
    *,
    field: str,
    label: str,
) -> list[dict[str, Any]]:
    _unique_field_values(upserts, field, f"{label} upserts")
    remove_values = [str(value).strip() for value in removes]
    if any(not value for value in remove_values):
        raise RuntimeError(f"{label} removals contain a blank identifier.")
    duplicate_removes = sorted(
        value for value, count in Counter(remove_values).items() if count > 1
    )
    if duplicate_removes:
        raise RuntimeError(
            f"{label} removals contain duplicates: {duplicate_removes}"
        )

    remove_set = set(remove_values)
    result = [
        copy.deepcopy(record)
        for record in existing
        if str(record.get(field, "")).strip() not in remove_set
    ]

    index = {
        str(record.get(field, "")).strip(): idx
        for idx, record in enumerate(result)
    }

    for replacement in upserts:
        key = str(replacement.get(field, "")).strip()
        value = copy.deepcopy(replacement)
        if key in index:
            result[index[key]] = value
        else:
            index[key] = len(result)
            result.append(value)

    return result


def _append_unique_strings(existing: list[Any], additions: list[Any]) -> list[str]:
    result = [str(value) for value in existing]
    seen = set(result)
    for value in additions:
        normalized = str(value)
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def apply_refiner_delta(
    *,
    source_payload: dict[str, Any],
    delta: dict[str, Any],
    refiner_findings: dict[str, Any],
) -> dict[str, Any]:
    # Apply only changed/new records, then let normal semantic validation check
    # the projected full candidate.
    validate_refiner_resolutions(delta, refiner_findings)

    remove_work = [
        str(value).strip()
        for value in delta.get("work_item_keys_remove", [])
    ]
    if "no-safe-circle" in remove_work:
        raise RuntimeError("Refiner delta may not remove the no-safe-circle root.")

    refined = copy.deepcopy(source_payload)
    refined["summary"] = copy.deepcopy(delta["summary"])
    refined["seed_assessment"] = copy.deepcopy(delta["seed_assessment"])

    sources = refined.setdefault("sources", {})
    sources["files_reviewed"] = _append_unique_strings(
        sources.get("files_reviewed", []),
        delta.get("files_reviewed_add", []),
    )
    sources["historical_sources_reviewed"] = _append_unique_strings(
        sources.get("historical_sources_reviewed", []),
        delta.get("historical_sources_reviewed_add", []),
    )

    refined["work_items"] = _apply_record_delta(
        refined.get("work_items", []),
        delta.get("work_items_upsert", []),
        remove_work,
        field="key",
        label="work_items",
    )
    refined["non_code_requirements"] = _apply_record_delta(
        refined.get("non_code_requirements", []),
        delta.get("non_code_requirements_upsert", []),
        delta.get("non_code_requirement_titles_remove", []),
        field="title",
        label="non_code_requirements",
    )
    refined["deferred_or_excluded"] = _apply_record_delta(
        refined.get("deferred_or_excluded", []),
        delta.get("deferred_or_excluded_upsert", []),
        delta.get("deferred_or_excluded_titles_remove", []),
        field="title",
        label="deferred_or_excluded",
    )
    refined["unresolved_questions"] = _apply_record_delta(
        refined.get("unresolved_questions", []),
        delta.get("unresolved_questions_upsert", []),
        delta.get("unresolved_question_texts_remove", []),
        field="question",
        label="unresolved_questions",
    )

    return refined
'''
    text = replace_once(
        text,
        "\n# ============================================================\n# BOUNDED REFINER\n# ============================================================\n",
        "\n" + delta_block + "\n"
        "# ============================================================\n"
        "# BOUNDED REFINER\n"
        "# ============================================================\n",
        "delta refiner insertion",
    )

    start = text.index("def run_refiner(\n")
    end_marker = "\n\n# ============================================================\n# REPORTING\n# ============================================================\n"
    end = text.index(end_marker, start)
    new_run_refiner = r'''def run_refiner(
    *,
    source_candidate: Path,
    merged_findings_path: Path,
    source_run_id: str,
    model: str,
) -> dict[str, Any]:
    base = load_prompt("refiner.md")
    candidate_rel = source_candidate.relative_to(ROOT).as_posix()
    findings_rel = merged_findings_path.relative_to(ROOT).as_posix()

    prompt = (
        base
        + "\n\n---\n\n"
        + "# Inputs\n\n"
        + f"- Reconciliation source run: `{source_run_id}`\n"
        + f"- Candidate: `{candidate_rel}`\n"
        + f"- Independent merged findings: `{findings_rel}`\n\n"
        + "Read both inputs. Return ONLY the bounded correction delta required by "
        + "the supplied schema; do not reproduce unchanged work items or the full "
        + "candidate. Resolve every supplied finding exactly once in "
        + "finding_resolutions. Use the current GDD and current repository as "
        + "primary truth. Inspect repository files only when a supplied finding "
        + "cannot be resolved from the candidate, cited evidence, and GDD. "
        + "If credible findings conflict and the sources cannot resolve the "
        + "conflict, preserve the uncertainty through an unresolved-question "
        + "upsert instead of inventing certainty. If the GDD is silent about a "
        + "behavior, do not turn that silence into a binding acceptance criterion.\n"
    )

    return invoke_read_only_agent(
        agent_name="Reconciliation Verification Refiner",
        model=model,
        prompt=prompt,
        schema=REFINER_DELTA_SCHEMA,
        timeout_seconds=REFINER_TIMEOUT_SECONDS,
        max_turns=REFINER_MAX_TURNS,
    )
'''
    text = text[:start] + new_run_refiner + text[end:]

    text = replace_once(
        text,
        "        source_run_id, source_candidate = resolve_source_snapshot(args.run_id)\n"
        "        paths = create_verification_paths(source_run_id)\n",
        "        source_run_id, source_candidate = resolve_source_snapshot(args.run_id)\n"
        "        source_payload = load_json(source_candidate)\n"
        "        paths = create_verification_paths(source_run_id)\n",
        "base verifier source payload load",
    )

    old_main = '''            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )
            refined_payload = refiner["result"]
            save_new_json(paths["refined_raw"], refined_payload)
'''
    new_main = '''            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )
            refiner_delta = refiner["result"]
            save_new_json(paths["refiner_delta"], refiner_delta)
            refined_payload = apply_refiner_delta(
                source_payload=source_payload,
                delta=refiner_delta,
                refiner_findings=refiner_findings,
            )
            save_new_json(paths["refined_raw"], refined_payload)
'''
    text = replace_once(text, old_main, new_main, "base verifier refiner application")

    VERIFICATION.write_text(text, encoding="utf-8")


def patch_parallel_verifier() -> None:
    text = require(PARALLEL)

    if 'RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS", "36"' not in text:
        text = replace_once(
            text,
            '    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS", "24")\n',
            '    __import__("os").environ.get("RECONCILIATION_PARALLEL_VERIFY_EVIDENCE_TURNS", "36")\n',
            "parallel evidence default turns",
        )

    if 'base.apply_refiner_delta(' not in text:
        old = '''            refiner = base.run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )

            refined_payload = refiner["result"]
            base.save_new_json(paths["refined_raw"], refined_payload)
'''
        new = '''            refiner = base.run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["refiner_findings"],
                source_run_id=source_run_id,
                model=refiner_model,
            )

            refiner_delta = refiner["result"]
            base.save_new_json(paths["refiner_delta"], refiner_delta)
            refined_payload = base.apply_refiner_delta(
                source_payload=source_payload,
                delta=refiner_delta,
                refiner_findings=refiner_findings,
            )
            base.save_new_json(paths["refined_raw"], refined_payload)
'''
        text = replace_once(text, old, new, "parallel refiner application")

    PARALLEL.write_text(text, encoding="utf-8")


def patch_refiner_prompt() -> None:
    text = require(REFINER_PROMPT)

    if "minimal correction delta" not in text:
        text = replace_once(
            text,
            "Your job is to produce a corrected full reconciliation candidate.",
            "Your job is to produce a minimal correction delta that Python will apply "
            "deterministically to the frozen reconciliation candidate.",
            "refiner prompt purpose",
        )

        delta_contract = r'''
## Delta output contract

Do **not** reproduce the full reconciliation candidate.

Return only the fields required by the supplied delta schema:

- `work_items_upsert`: full records only for work items that are changed or added;
- `work_item_keys_remove`: exact keys only for work items that must be removed;
- typed non-code/deferred/unresolved upserts and removals only when changed;
- `files_reviewed_add` / `historical_sources_reviewed_add` only for newly inspected
  approved evidence paths;
- a compact projected `summary` and `seed_assessment`;
- one `finding_resolutions` record for **every supplied finding exactly once**.

For a finding you conclude is wrong, use `rejected_as_unsupported` and explain the
source-based reason. Do not mutate the graph merely to satisfy an incorrect
auditor.

For a credible finding whose answer is genuinely not specified, use
`preserved_unresolved` and add/update the appropriate unresolved question.

For a supported correction, use `corrected` and emit only the records that
actually change.

The deterministic merger will preserve every unchanged record from the frozen
candidate and the normal semantic validator will validate the projected full
candidate afterward.

### Bounded inspection

Start with the frozen candidate, the supplied findings, and the GDD. Do not
perform a broad repository crawl. Inspect only exact current-project files that
are necessary to resolve a supplied finding or verify a changed evidence/status
claim.

### No canon from silence

A missing GDD statement is not permission to invent behavior. Never create or
preserve a binding acceptance criterion solely because a verifier guessed at an
unspecified mechanic. If the GDD is silent and the behavior is not required for
a supported architecture contract, remove/reject the unsupported assertion
rather than turning it into canon.
'''
        text = replace_once(
            text,
            "## Finding policy\n",
            delta_contract + "\n\n## Finding policy\n",
            "refiner delta contract insertion",
        )

    text = text.replace(
        "Return only the full reconciliation JSON required by the supplied schema.",
        "Return only the minimal correction delta required by the supplied schema.",
        1,
    )

    REFINER_PROMPT.write_text(text, encoding="utf-8")


def patch_smoke_test() -> None:
    text = require(SMOKE)
    if "delta_source =" in text:
        print("verification_smoke_test.py already contains delta tests; skipping.")
        return

    block = r'''
    delta_source = {
        "summary": {
            "desired_state_summary": "desired",
            "current_state_summary": "current",
            "major_findings": [],
        },
        "sources": {
            "gdd": "Docs/GDD/No_Safe_Circle_GDD.md",
            "code_root": "Assets/",
            "historical_sources_reviewed": [],
            "files_reviewed": ["Docs/GDD/No_Safe_Circle_GDD.md"],
        },
        "work_items": [
            {"key": "no-safe-circle", "notes": "root"},
            {"key": "task-a", "notes": "old"},
            {"key": "task-b", "notes": "remove"},
        ],
        "non_code_requirements": [
            {"title": "Keep", "status": "unknown"},
        ],
        "deferred_or_excluded": [],
        "unresolved_questions": [],
        "seed_assessment": {
            "status": "ready_with_warnings",
            "blockers": [],
            "warnings": ["old"],
        },
    }
    delta_findings = {
        "findings": [
            {
                "source_agent": "Test Auditor",
                "finding": {"finding_id": "F-1"},
            }
        ]
    }
    delta_patch = {
        "summary": {
            "desired_state_summary": "desired",
            "current_state_summary": "refined",
            "major_findings": ["fixed"],
        },
        "seed_assessment": {
            "status": "ready",
            "blockers": [],
            "warnings": [],
        },
        "files_reviewed_add": ["Assets/Test.cs"],
        "historical_sources_reviewed_add": [],
        "work_items_upsert": [
            {"key": "task-a", "notes": "new"},
            {"key": "task-c", "notes": "added"},
        ],
        "work_item_keys_remove": ["task-b"],
        "non_code_requirements_upsert": [],
        "non_code_requirement_titles_remove": [],
        "deferred_or_excluded_upsert": [],
        "deferred_or_excluded_titles_remove": [],
        "unresolved_questions_upsert": [],
        "unresolved_question_texts_remove": [],
        "finding_resolutions": [
            {
                "source_agent": "Test Auditor",
                "finding_id": "F-1",
                "disposition": "corrected",
                "explanation": "Smoke-test repair.",
            }
        ],
        "reasoning": "Only changed records are emitted.",
    }
    delta_result = crew.apply_refiner_delta(
        source_payload=delta_source,
        delta=delta_patch,
        refiner_findings=delta_findings,
    )
    assert [item["key"] for item in delta_result["work_items"]] == [
        "no-safe-circle",
        "task-a",
        "task-c",
    ]
    assert next(
        item for item in delta_result["work_items"] if item["key"] == "task-a"
    )["notes"] == "new"
    assert delta_source["work_items"][1]["notes"] == "old"
    assert delta_result["sources"]["files_reviewed"][-1] == "Assets/Test.cs"
    assert delta_result["seed_assessment"]["status"] == "ready"

    missing_resolution = dict(delta_patch)
    missing_resolution["finding_resolutions"] = []
    try:
        crew.apply_refiner_delta(
            source_payload=delta_source,
            delta=missing_resolution,
            refiner_findings=delta_findings,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Refiner delta must not silently omit a supplied finding."
        )


'''
    text = replace_once(
        text,
        "\n    legacy = {\n",
        "\n" + block + "    legacy = {\n",
        "delta smoke tests",
    )
    SMOKE.write_text(text, encoding="utf-8")


RESUME_SCRIPT = r'''from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import parallel_verification_crew as parallel
import verification_crew as base
from output_layout import write_current_view
from reconciliation_agent import (
    build_proposed_graph_delta,
    render_graph_delta_markdown,
    render_markdown,
    repair_missing_dependency_references,
    run_semantic_validation,
    sanitize_forbidden_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resume a failed parallel verification at the Refiner stage without "
            "rerunning the preserved pass-1 auditors."
        )
    )
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--verification-run-id", required=True)
    parser.add_argument(
        "--no-reverify",
        action="store_true",
        help="Stop after producing and validating the refined candidate.",
    )
    return parser.parse_args()


def build_paths(source_run_id: str, verification_run_id: str) -> dict[str, Any]:
    run_dir = base.verification_root(source_run_id) / verification_run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Verification directory not found: {run_dir}")

    return {
        "verification_run_id": verification_run_id,
        "created_at_utc": base.utc_now_iso(),
        "source_run_id": source_run_id,
        "run_dir": run_dir,
        "model_assignments": run_dir / "MODEL_ASSIGNMENTS.json",
        "pass1_dir": run_dir / "pass1",
        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
        "refiner_findings": run_dir / "REFINER_FINDINGS.json",
        "refiner_delta": run_dir / "REFINER_DELTA.json",
        "refined_raw": run_dir / "refined_candidate.raw.json",
        "refined_json": run_dir / "refined_candidate.json",
        "refined_markdown": run_dir / "REFINED_RECONCILIATION.md",
        "refined_delta_json": run_dir / "PROPOSED_REFINED_GRAPH_DELTA.json",
        "refined_delta_markdown": run_dir / "PROPOSED_REFINED_GRAPH_DELTA.md",
        "pass2_dir": run_dir / "pass2",
        "merged_pass2": run_dir / "MERGED_FINDINGS_PASS2.json",
        "summary_json": run_dir / "VERIFICATION_SUMMARY.json",
        "summary_markdown": run_dir / "VERIFICATION.md",
    }


def load_pass1_audits(pass1_dir: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for spec in parallel.SPECS:
        path = pass1_dir / f"{spec.key}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Cannot resume: preserved auditor result is missing: {path}"
            )
        audits.append(base.load_json(path))
    audits.sort(key=lambda item: str(item.get("agent", "")))
    return audits


def main() -> int:
    paths: dict[str, Any] | None = None
    try:
        args = parse_args()
        paths = build_paths(args.source_run_id, args.verification_run_id)

        source_candidate = base.RUNS_DIR / args.source_run_id / "reconciliation.json"
        if not source_candidate.exists():
            raise FileNotFoundError(
                f"Source reconciliation not found: {source_candidate}"
            )

        for required in (
            paths["model_assignments"],
            paths["merged_pass1"],
            paths["refiner_findings"],
        ):
            if not required.exists():
                raise FileNotFoundError(
                    f"Cannot resume; required preserved artifact is missing: {required}"
                )

        for output in (
            paths["refiner_delta"],
            paths["refined_raw"],
            paths["refined_json"],
            paths["refined_markdown"],
            paths["refined_delta_json"],
            paths["refined_delta_markdown"],
            paths["merged_pass2"],
            paths["summary_json"],
            paths["summary_markdown"],
        ):
            if output.exists():
                raise RuntimeError(
                    "Resume target already contains post-refiner output; refusing "
                    f"to overwrite immutable artifact: {output}"
                )
        if paths["pass2_dir"].exists():
            raise RuntimeError(
                f"Resume target already contains pass2 directory: {paths['pass2_dir']}"
            )

        assignments = base.load_json(paths["model_assignments"])
        refiner_model = str(assignments.get("refiner", "")).strip()
        pass2_assignments = assignments.get("pass2", {})
        if not refiner_model:
            raise RuntimeError("MODEL_ASSIGNMENTS.json has no refiner model.")
        if not isinstance(pass2_assignments, dict):
            raise RuntimeError("MODEL_ASSIGNMENTS.json has invalid pass2 assignments.")

        source_payload = base.load_json(source_candidate)
        pass1_audits = load_pass1_audits(paths["pass1_dir"])
        merged1 = base.load_json(paths["merged_pass1"])
        refiner_findings = base.load_json(paths["refiner_findings"])

        print()
        print("=" * 72)
        print("RESUMING PARALLEL VERIFICATION AT REFINER")
        print("=" * 72)
        print(f"Source reconciliation: {args.source_run_id}")
        print(f"Verification run: {args.verification_run_id}")
        print("Preserved pass-1 auditors will NOT be rerun.")
        print(f"Refiner model: {refiner_model}")
        print("=" * 72)

        refiner = base.run_refiner(
            source_candidate=source_candidate,
            merged_findings_path=paths["refiner_findings"],
            source_run_id=args.source_run_id,
            model=refiner_model,
        )
        refiner_delta = refiner["result"]
        base.save_new_json(paths["refiner_delta"], refiner_delta)

        refined_payload = base.apply_refiner_delta(
            source_payload=source_payload,
            delta=refiner_delta,
            refiner_findings=refiner_findings,
        )
        base.save_new_json(paths["refined_raw"], refined_payload)

        removed = sanitize_forbidden_evidence(refined_payload)
        if removed:
            print(
                "Warning: Refiner returned forbidden evidence that was removed: "
                + ", ".join(removed)
            )

        removed_tracking = base.sanitize_refiner_input_tracking(refined_payload)
        if removed_tracking:
            print(
                "Normalized Refiner bookkeeping paths from files_reviewed: "
                + ", ".join(removed_tracking)
            )

        repair_missing_dependency_references(refined_payload)
        run_semantic_validation(refined_payload)

        base.save_new_json(paths["refined_json"], refined_payload)
        base.save_new_text(paths["refined_markdown"], render_markdown(refined_payload))

        refined_graph_delta = build_proposed_graph_delta(
            refined_payload,
            run_id=args.source_run_id,
            created_at_utc=paths["created_at_utc"],
        )
        refined_graph_delta["verification_run_id"] = args.verification_run_id
        refined_graph_delta["source_reconciliation_run_id"] = args.source_run_id
        base.save_new_json(paths["refined_delta_json"], refined_graph_delta)
        base.save_new_text(
            paths["refined_delta_markdown"],
            render_graph_delta_markdown(refined_graph_delta),
        )

        final_candidate = paths["refined_json"]
        final_merged = merged1
        selected_pass2_keys: set[str] = set()

        if not args.no_reverify:
            selected_pass2_keys = parallel.changed_audit_keys(
                source_payload,
                refined_payload,
            )
            selected_pass2_keys.update(
                parallel.auditors_with_findings(pass1_audits)
            )
            selected_specs = [
                spec for spec in parallel.SPECS
                if spec.key in selected_pass2_keys
            ]

            print()
            print("=" * 72)
            print("SELECTIVE PASS 2")
            print("=" * 72)
            print(
                f"Rerunning {len(selected_specs)} of {len(parallel.SPECS)} auditors."
            )
            if selected_specs:
                print("Auditors: " + ", ".join(spec.key for spec in selected_specs))
            print("=" * 72)

            if selected_specs:
                pass2_audits = parallel.run_specs(
                    specs=selected_specs,
                    candidate_path=final_candidate,
                    source_run_id=args.source_run_id,
                    pass_label="pass2-selective-resume",
                    output_dir=paths["pass2_dir"],
                    assignments=pass2_assignments,
                )
            else:
                paths["pass2_dir"].mkdir(parents=True, exist_ok=False)
                pass2_audits = []

            final_audits = parallel.final_audit_set(
                pass1_audits=pass1_audits,
                rerun_audits=pass2_audits,
                selected_keys=selected_pass2_keys,
            )
            final_merged = base.merge_findings(final_audits)
            final_merged["selective_pass2"] = {
                "enabled": True,
                "rerun_auditor_count": len(selected_specs),
                "total_auditor_count": len(parallel.SPECS),
                "rerun_keys": sorted(selected_pass2_keys),
                "reuse_policy": (
                    "Pass-1 results are reused only for auditors outside the "
                    "Refiner's changed territory that did not themselves report "
                    "a finding requiring recheck."
                ),
                "resumed_from_preserved_pass1": True,
            }
            base.save_new_json(paths["merged_pass2"], final_merged)

        status = base.status_from_pass2(final_merged)
        summary = {
            "schema_version": "2.1-parallel-resume",
            "source_run_id": args.source_run_id,
            "verification_run_id": args.verification_run_id,
            "created_at_utc": paths["created_at_utc"],
            "status": status,
            "source_candidate": source_candidate.relative_to(base.ROOT).as_posix(),
            "final_candidate": final_candidate.relative_to(base.ROOT).as_posix(),
            "refinement_performed": True,
            "resumed_after_refiner_failure": True,
            "parallel_auditor_count": len(parallel.SPECS),
            "parallel_max_workers": parallel.PARALLEL_MAX_WORKERS,
            "model_assignments": {
                "pass1": assignments.get("pass1"),
                "refiner": refiner_model,
                "pass2": (
                    {
                        key: pass2_assignments[key]
                        for key in sorted(selected_pass2_keys)
                    }
                    if not args.no_reverify
                    else None
                ),
            },
            "pass1": merged1,
            "final_pass": final_merged,
            "human_approval_required": True,
            "persistent_graph_mutated": False,
        }

        base.save_new_json(paths["summary_json"], summary)
        base.save_new_text(
            paths["summary_markdown"],
            base.render_verification_markdown(summary),
        )
        base.write_latest_verification_pointer(paths, status)

        write_current_view(
            source_reconciliation_run_id=args.source_run_id,
            status=status,
            candidate_json=final_candidate,
            candidate_markdown=paths["refined_markdown"],
            delta_json=paths["refined_delta_json"],
            delta_markdown=paths["refined_delta_markdown"],
            verification_run_id=args.verification_run_id,
            verification_summary_json=paths["summary_json"],
            verification_markdown=paths["summary_markdown"],
        )

        print()
        print("=" * 72)
        print("RESUMED PARALLEL VERIFICATION COMPLETE")
        print("=" * 72)
        print(f"Status: {status}")
        print(
            "Pass 1 material findings: "
            f"{merged1.get('material_finding_count', 0)}"
        )
        if not args.no_reverify:
            print(
                f"Pass 2 auditors rerun: "
                f"{len(selected_pass2_keys)} / {len(parallel.SPECS)}"
            )
        print(
            "Final material findings: "
            f"{final_merged.get('material_finding_count', 0)}"
        )
        print(
            f"Refined candidate: "
            f"{paths['refined_json'].relative_to(base.ROOT)}"
        )
        print("Preserved pass-1 auditors were not rerun.")
        print("Tasks/*.yaml was not modified.")
        print("=" * 72)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("RESUMED PARALLEL VERIFICATION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        if paths is not None:
            print(
                "Verification directory preserved: "
                f"{paths['run_dir'].relative_to(base.ROOT)}",
                file=sys.stderr,
            )
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def create_resume_script() -> None:
    if RESUME.exists():
        existing = RESUME.read_text(encoding="utf-8-sig")
        if "RESUMING PARALLEL VERIFICATION AT REFINER" in existing:
            print("resume_parallel_refinement.py already exists; skipping.")
            return
        raise RuntimeError(f"Refusing to overwrite existing unrelated file: {RESUME}")
    RESUME.write_text(RESUME_SCRIPT, encoding="utf-8")


def main() -> int:
    for path in (VERIFICATION, PARALLEL, REFINER_PROMPT, SMOKE):
        if not path.exists():
            raise FileNotFoundError(
                "Run this patch from the NoSafeCircle repository root. "
                f"Missing: {path}"
            )

    patch_verification_crew()
    patch_parallel_verifier()
    patch_refiner_prompt()
    patch_smoke_test()
    create_resume_script()

    print()
    print("Refiner delta fix applied.")
    print("Changed:")
    print("  Pipeline/Reconciliation/verification_crew.py")
    print("  Pipeline/Reconciliation/parallel_verification_crew.py")
    print("  Pipeline/Reconciliation/prompts/verification/refiner.md")
    print("  Pipeline/Reconciliation/verification_smoke_test.py")
    print("Created:")
    print("  Pipeline/Reconciliation/resume_parallel_refinement.py")
    print()
    print("Evidence auditors now default to 36 turns; max-turn recovery becomes 48.")
    print("The Refiner now emits a bounded delta instead of a full reconciliation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
