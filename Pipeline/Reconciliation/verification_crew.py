from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import subprocess
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from output_layout import (
    LATEST_VERIFICATION_POINTER_PATH,
    verification_root,
    write_current_view,
)

from reconciliation_agent import (
    RECONCILIATION_SCHEMA,
    ensure_execution_scope_defaults,
    build_proposed_graph_delta,
    render_graph_delta_markdown,
    render_markdown,
    repair_missing_dependency_references,
    run_semantic_validation,
    sanitize_forbidden_evidence,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "Pipeline" / "Reconciliation"
OUTPUT_DIR = AGENT_ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "runs"
LATEST_POINTER_PATH = OUTPUT_DIR / "LATEST.json"
PROMPT_DIR = AGENT_ROOT / "prompts" / "verification"

VERIFY_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_VERIFY_TIMEOUT_SECONDS", "1200")
)
VERIFY_MAX_TURNS = int(
    os.environ.get("RECONCILIATION_VERIFY_MAX_TURNS", "30")
)
VERIFY_MAX_WORKERS = int(
    os.environ.get("RECONCILIATION_VERIFY_MAX_WORKERS", "4")
)
REFINER_TIMEOUT_SECONDS = int(
    os.environ.get("RECONCILIATION_VERIFY_REFINER_TIMEOUT_SECONDS", "1200")
)
REFINER_MAX_TURNS = int(
    os.environ.get("RECONCILIATION_VERIFY_REFINER_MAX_TURNS", "35")
)

DEFAULT_MODEL_POOL = "opus,sonnet"
MODEL_POOL = [
    value.strip()
    for value in os.environ.get(
        "RECONCILIATION_VERIFIER_MODELS", DEFAULT_MODEL_POOL
    ).split(",")
    if value.strip()
]

if not MODEL_POOL:
    raise RuntimeError("RECONCILIATION_VERIFIER_MODELS must contain a model.")


# ============================================================
# STRUCTURED OUTPUT SCHEMAS
# ============================================================

AUDIT_GDD_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reference": {"type": "string"},
        "requirement": {"type": "string"},
    },
    "required": ["reference", "requirement"],
}

AUDIT_REPOSITORY_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "path": {"type": "string"},
        "observation": {"type": "string"},
    },
    "required": ["path", "observation"],
}

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "finding_id": {"type": "string"},
        "severity": {
            "type": "string",
            "enum": ["blocker", "error", "warning", "suggestion"],
        },
        "category": {
            "type": "string",
            "enum": [
                "missing_required_work",
                "overgrouped_work",
                "incorrect_parent",
                "missing_dependency",
                "incorrect_dependency",
                "premature_decomposition",
                "under_decomposition",
                "unsupported_complete",
                "incorrect_repository_state",
                "scope_leak",
                "non_code_misclassification",
                "evidence_problem",
                "shared_capability_hidden",
                "execution_scope_problem",
                "other",
            ],
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "affected_keys": {
            "type": "array",
            "items": {"type": "string"},
        },
        "gdd_evidence": {
            "type": "array",
            "items": AUDIT_GDD_EVIDENCE_SCHEMA,
        },
        "repository_evidence": {
            "type": "array",
            "items": AUDIT_REPOSITORY_EVIDENCE_SCHEMA,
        },
        "recommended_change": {"type": "string"},
        "requires_human_review": {"type": "boolean"},
    },
    "required": [
        "finding_id",
        "severity",
        "category",
        "title",
        "description",
        "affected_keys",
        "gdd_evidence",
        "repository_evidence",
        "recommended_change",
        "requires_human_review",
    ],
}

COMMON_AUDIT_PROPERTIES: dict[str, Any] = {
    "verdict": {
        "type": "string",
        "enum": ["pass", "pass_with_findings", "fail"],
    },
    "findings": {"type": "array", "items": FINDING_SCHEMA},
    "notes": {"type": "array", "items": {"type": "string"}},
}

COMMON_AUDIT_REQUIRED = ["verdict", "findings", "notes"]

COVERAGE_REQUIREMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "requirement_id": {"type": "string"},
        "reference": {"type": "string"},
        "requirement": {"type": "string"},
        "classification": {
            "type": "string",
            "enum": [
                "required_gameplay",
                "required_non_code",
                "required_process",
                "stretch",
                "excluded",
            ],
        },
        "representation": {
            "type": "string",
            "enum": [
                "work_item",
                "non_code_requirement",
                "deferred_or_excluded",
                "unrepresented",
                "ambiguous",
            ],
        },
        "mapped_keys": {
            "type": "array",
            "items": {"type": "string"},
        },
        "explanation": {"type": "string"},
    },
    "required": [
        "requirement_id",
        "reference",
        "requirement",
        "classification",
        "representation",
        "mapped_keys",
        "explanation",
    ],
}

COVERAGE_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **COMMON_AUDIT_PROPERTIES,
        "requirements": {
            "type": "array",
            "items": COVERAGE_REQUIREMENT_SCHEMA,
            "minItems": 1,
        },
    },
    "required": COMMON_AUDIT_REQUIRED + ["requirements"],
}

GENERAL_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": COMMON_AUDIT_PROPERTIES,
    "required": COMMON_AUDIT_REQUIRED,
}


# ============================================================
# PATHS / IO
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_new_json(path: Path, value: Any) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite immutable artifact: {path}")
    save_json(path, value)


def save_new_text(path: Path, text: str) -> None:
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite immutable artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return value


def resolve_source_snapshot(run_id: str | None) -> tuple[str, Path]:
    if run_id:
        run_dir = RUNS_DIR / run_id
        candidate = run_dir / "reconciliation.json"
        if not candidate.exists():
            raise FileNotFoundError(
                f"Validated reconciliation not found for run {run_id}: {candidate}"
            )
        return run_id, candidate

    if not LATEST_POINTER_PATH.exists():
        raise FileNotFoundError(
            "No reconciliation LATEST.json exists. Run reconciliation first."
        )

    pointer = load_json(LATEST_POINTER_PATH)
    latest_run_id = str(pointer.get("latest_successful_run_id", "")).strip()
    if not latest_run_id:
        raise RuntimeError("LATEST.json does not contain latest_successful_run_id.")

    candidate_text = str(pointer.get("reconciliation_json", "")).strip()
    candidate = ROOT / candidate_text if candidate_text else RUNS_DIR / latest_run_id / "reconciliation.json"
    if not candidate.exists():
        raise FileNotFoundError(f"Latest reconciliation file does not exist: {candidate}")

    return latest_run_id, candidate



def sanitize_refiner_input_tracking(payload: dict[str, Any]) -> list[str]:
    """
    Remove verification-pipeline bookkeeping inputs from sources.files_reviewed.

    The Refiner legitimately reads the frozen reconciliation candidate and the
    merged verifier findings, but those generated Pipeline/Reconciliation/outputs
    files are NOT project/GDD evidence and must not be reported as reviewed
    repository source paths.

    Keep semantic validation strict for actual repository_evidence; this helper
    only normalizes the files_reviewed audit trail.
    """
    sources = payload.setdefault("sources", {})
    reviewed = sources.get("files_reviewed", [])
    cleaned: list[Any] = []
    removed: list[str] = []

    internal_prefix = "Pipeline/Reconciliation/outputs/"

    for value in reviewed:
        path = str(value).replace("\\", "/").lstrip("./")
        if path.startswith(internal_prefix):
            removed.append(path)
        else:
            cleaned.append(value)

    sources["files_reviewed"] = cleaned
    return sorted(set(removed))



def create_verification_paths(source_run_id: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    verification_run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    run_dir = verification_root(source_run_id) / verification_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    return {
        "verification_run_id": verification_run_id,
        "created_at_utc": utc_now_iso(),
        "source_run_id": source_run_id,
        "run_dir": run_dir,
        "model_assignments": run_dir / "MODEL_ASSIGNMENTS.json",
        "pass1_dir": run_dir / "pass1",
        "merged_pass1": run_dir / "MERGED_FINDINGS_PASS1.json",
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


# ============================================================
# MODEL DIVERSITY
# ============================================================

def choose_audit_models(rng: random.Random) -> dict[str, str]:
    """
    Assign models per independent auditor.

    With two or more models, the two coverage auditors are guaranteed to use
    different requested models. Structure/evidence are also made different
    when possible, and execution scope is varied across the configured pool. The random seed and exact requested assignments are saved.
    """
    if len(MODEL_POOL) == 1:
        only = MODEL_POOL[0]
        return {
            "coverage_a": only,
            "coverage_b": only,
            "structure": only,
            "evidence": only,
            "execution": only,
        }

    coverage_a, coverage_b = rng.sample(MODEL_POOL, 2)
    structure = rng.choice(MODEL_POOL)
    evidence_choices = [model for model in MODEL_POOL if model != structure]
    evidence = rng.choice(evidence_choices or MODEL_POOL)
    execution_choices = [model for model in MODEL_POOL if model != evidence]
    execution = rng.choice(execution_choices or MODEL_POOL)

    return {
        "coverage_a": coverage_a,
        "coverage_b": coverage_b,
        "structure": structure,
        "evidence": evidence,
        "execution": execution,
    }


def choose_refiner_model(rng: random.Random, pass1: dict[str, str]) -> str:
    # Prefer a model that was not used by both coverage auditors when possible.
    least_used = Counter(pass1.values())
    min_count = min(least_used.values())
    candidates = [model for model in MODEL_POOL if least_used.get(model, 0) == min_count]
    return rng.choice(candidates or MODEL_POOL)


# ============================================================
# CLAUDE INVOCATION
# ============================================================

def load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Verification prompt not found: {path}")
    return path.read_text(encoding="utf-8-sig")


def invoke_read_only_agent(
    *,
    agent_name: str,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    timeout_seconds: int,
    max_turns: int,
) -> dict[str, Any]:
    compact_schema = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
    command = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        "dontAsk",
        "--tools",
        "Read,Glob,Grep",
        "--allowedTools",
        "Read,Glob,Grep",
        "--disallowedTools",
        "Edit,Write,mcp__*",
        "--json-schema",
        compact_schema,
        "--input-format",
        "text",
    ]

    print(f"Starting verifier: {agent_name} [{model}]")
    started = time.monotonic()

    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"{agent_name} [{model}] exceeded {timeout_seconds} seconds."
        ) from exc

    duration = round(time.monotonic() - started, 2)

    if process.returncode != 0:
        error_text = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(
            f"{agent_name} [{model}] failed with exit code {process.returncode}.\n"
            f"{error_text}"
        )

    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{agent_name} [{model}] returned invalid Claude JSON."
        ) from exc

    structured_output = envelope.get("structured_output")
    if not isinstance(structured_output, dict):
        raise RuntimeError(
            f"{agent_name} [{model}] did not return structured_output."
        )

    print(f"Completed verifier: {agent_name} [{model}] in {duration} seconds.")
    return {
        "agent": agent_name,
        "requested_model": model,
        "duration_seconds": duration,
        "result": structured_output,
    }


def build_audit_prompt(
    *,
    prompt_file: str,
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
) -> str:
    base = load_prompt(prompt_file)
    relative_candidate = candidate_path.relative_to(ROOT).as_posix()
    return (
        base
        + "\n\n---\n\n"
        + "# Frozen candidate for this independent audit\n\n"
        + f"- Reconciliation source run: `{source_run_id}`\n"
        + f"- Verification pass: `{pass_label}`\n"
        + f"- Candidate file: `{relative_candidate}`\n\n"
        + "Read that candidate directly. Do not use or imitate another verifier's "
        + "findings. This pass must be independent.\n"
    )


def run_audit_pass(
    *,
    candidate_path: Path,
    source_run_id: str,
    pass_label: str,
    output_dir: Path,
    assignments: dict[str, str],
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=False)

    specs = [
        (
            "coverage_a",
            "GDD Coverage Auditor A",
            "coverage_auditor.md",
            COVERAGE_AUDIT_SCHEMA,
        ),
        (
            "coverage_b",
            "GDD Coverage Auditor B",
            "coverage_auditor.md",
            COVERAGE_AUDIT_SCHEMA,
        ),
        (
            "structure",
            "Dependency and Decomposition Auditor",
            "structure_auditor.md",
            GENERAL_AUDIT_SCHEMA,
        ),
        (
            "evidence",
            "Repository Evidence Auditor",
            "evidence_auditor.md",
            GENERAL_AUDIT_SCHEMA,
        ),
        (
            "execution",
            "Execution Scope Auditor",
            "execution_scope_auditor.md",
            GENERAL_AUDIT_SCHEMA,
        ),
    ]

    results: list[dict[str, Any]] = []

    def run_one(spec: tuple[str, str, str, dict[str, Any]]) -> dict[str, Any]:
        key, agent_name, prompt_file, schema = spec
        prompt = build_audit_prompt(
            prompt_file=prompt_file,
            candidate_path=candidate_path,
            source_run_id=source_run_id,
            pass_label=pass_label,
        )
        return invoke_read_only_agent(
            agent_name=agent_name,
            model=assignments[key],
            prompt=prompt,
            schema=schema,
            timeout_seconds=VERIFY_TIMEOUT_SECONDS,
            max_turns=VERIFY_MAX_TURNS,
        )

    max_workers = max(1, min(VERIFY_MAX_WORKERS, len(specs)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(run_one, spec): spec[0] for spec in specs}
        for future in as_completed(future_map):
            result = future.result()
            results.append(result)
            filename = result["agent"].lower().replace(" ", "_").replace("/", "_")
            save_new_json(output_dir / f"{filename}.json", result)

    results.sort(key=lambda item: item["agent"])
    return results


# ============================================================
# DETERMINISTIC FINDING MERGE
# ============================================================

def deterministic_audit_checks(audits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []

    for audit in audits:
        agent = str(audit.get("agent", ""))
        result = audit.get("result", {})
        requirements = result.get("requirements", [])
        if not isinstance(requirements, list):
            continue

        for requirement in requirements:
            classification = str(requirement.get("classification", ""))
            representation = str(requirement.get("representation", ""))
            if classification.startswith("required_") and representation in {
                "unrepresented",
                "ambiguous",
            }:
                generated.append(
                    {
                        "source_agent": "Deterministic Coverage Check",
                        "source_model": "python",
                        "finding": {
                            "finding_id": (
                                "deterministic-coverage-"
                                + str(requirement.get("requirement_id", "unknown"))
                            ),
                            "severity": "error",
                            "category": "missing_required_work",
                            "title": "Required GDD requirement is not safely represented",
                            "description": (
                                f"{agent} classified required requirement "
                                f"{requirement.get('requirement_id')} as "
                                f"{representation}."
                            ),
                            "affected_keys": list(requirement.get("mapped_keys", [])),
                            "gdd_evidence": [
                                {
                                    "reference": str(requirement.get("reference", "")),
                                    "requirement": str(requirement.get("requirement", "")),
                                }
                            ],
                            "repository_evidence": [],
                            "recommended_change": (
                                "Resolve the coverage gap explicitly before graph seeding."
                            ),
                            "requires_human_review": representation == "ambiguous",
                        },
                    }
                )

    return generated


def merge_findings(audits: list[dict[str, Any]]) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []

    for audit in audits:
        result = audit.get("result", {})
        for finding in result.get("findings", []):
            reports.append(
                {
                    "source_agent": audit.get("agent"),
                    "source_model": audit.get("requested_model"),
                    "finding": finding,
                }
            )

    reports.extend(deterministic_audit_checks(audits))

    severity_counts = Counter(
        str(report.get("finding", {}).get("severity", "")) for report in reports
    )
    category_counts = Counter(
        str(report.get("finding", {}).get("category", "")) for report in reports
    )

    material = [
        report
        for report in reports
        if report.get("finding", {}).get("severity") in {"blocker", "error"}
    ]

    return {
        "schema_version": "1.0",
        "audit_count": len(audits),
        "finding_count": len(reports),
        "material_finding_count": len(material),
        "severity_counts": dict(sorted(severity_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "findings": reports,
        "merge_policy": (
            "Union of independent findings. No majority vote is used; a material "
            "finding must be resolved or explicitly preserved for human review."
        ),
    }


def has_material_findings(merged: dict[str, Any]) -> bool:
    return int(merged.get("material_finding_count", 0)) > 0


# ============================================================
# BOUNDED REFINER
# ============================================================

def run_refiner(
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
        + "Read both inputs. Resolve every blocker/error finding with the current "
        + "GDD and repository as primary truth. If credible findings conflict and "
        + "cannot be resolved from evidence, preserve the uncertainty in "
        + "unresolved_questions instead of inventing certainty.\n"
    )

    return invoke_read_only_agent(
        agent_name="Reconciliation Verification Refiner",
        model=model,
        prompt=prompt,
        schema=RECONCILIATION_SCHEMA,
        timeout_seconds=REFINER_TIMEOUT_SECONDS,
        max_turns=REFINER_MAX_TURNS,
    )


# ============================================================
# REPORTING
# ============================================================

def status_from_pass2(merged: dict[str, Any]) -> str:
    findings = merged.get("findings", [])
    severities = {
        str(report.get("finding", {}).get("severity", "")) for report in findings
    }
    if "blocker" in severities or "error" in severities:
        return "needs_human_review"
    if "warning" in severities or "suggestion" in severities:
        return "verified_with_findings"
    return "verified"


def render_verification_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Reconciliation Multi-Model Verification")
    lines.append("")
    lines.append(
        "> Independent model-diverse audit of a reconciliation snapshot. "
        "Verification never mutates `Tasks/*.yaml`."
    )
    lines.append("")
    lines.append(f"- **Source reconciliation:** `{summary.get('source_run_id', '')}`")
    lines.append(f"- **Verification run:** `{summary.get('verification_run_id', '')}`")
    lines.append(f"- **Status:** `{summary.get('status', '')}`")
    lines.append(f"- **Refinement performed:** `{str(summary.get('refinement_performed', False)).lower()}`")
    lines.append("")

    lines.append("## Model Assignments")
    lines.append("")
    assignments = summary.get("model_assignments", {})
    for pass_name in ("pass1", "refiner", "pass2"):
        value = assignments.get(pass_name)
        if value is None:
            continue
        lines.append(f"### {pass_name}")
        lines.append("")
        if isinstance(value, dict):
            for key, model in value.items():
                lines.append(f"- `{key}` → `{model}`")
        else:
            lines.append(f"- `{value}`")
        lines.append("")

    lines.append("## Pass 1")
    lines.append("")
    pass1 = summary.get("pass1", {})
    lines.append(f"- Findings: **{pass1.get('finding_count', 0)}**")
    lines.append(f"- Material findings: **{pass1.get('material_finding_count', 0)}**")
    lines.append("")

    if summary.get("refinement_performed"):
        lines.append("## Refined Candidate")
        lines.append("")
        lines.append(
            "A bounded Refiner produced a new candidate. The original immutable "
            "reconciliation snapshot was not changed."
        )
        lines.append("")

    lines.append("## Final Verification Pass")
    lines.append("")
    final_pass = summary.get("final_pass", {})
    lines.append(f"- Findings: **{final_pass.get('finding_count', 0)}**")
    lines.append(f"- Material findings: **{final_pass.get('material_finding_count', 0)}**")
    lines.append("")

    findings = final_pass.get("findings", [])
    if findings:
        lines.append("### Remaining Findings")
        lines.append("")
        for report in findings:
            finding = report.get("finding", {})
            lines.append(
                f"- **[{finding.get('severity', '')}] {finding.get('title', '')}** "
                f"— {report.get('source_agent', '')} / {report.get('source_model', '')}"
            )
            lines.append(f"  - {finding.get('description', '')}")
            lines.append(f"  - Recommended: {finding.get('recommended_change', '')}")
        lines.append("")
    else:
        lines.append("No remaining findings were reported by the final audit pass.")
        lines.append("")

    lines.append("## Human Gate")
    lines.append("")
    lines.append(
        "Even `verified` means **candidate ready for human approval**, not "
        "permission to write the persistent task graph automatically."
    )
    lines.append("")
    return "\n".join(lines)


def write_latest_verification_pointer(paths: dict[str, Any], status: str) -> None:
    pointer = {
        "schema_version": "1.0",
        "source_reconciliation_run_id": paths["source_run_id"],
        "latest_verification_run_id": paths["verification_run_id"],
        "status": status,
        "created_at_utc": paths["created_at_utc"],
        "verification_directory": paths["run_dir"].relative_to(ROOT).as_posix(),
        "verification_summary": paths["summary_json"].relative_to(ROOT).as_posix(),
        "verification_markdown": paths["summary_markdown"].relative_to(ROOT).as_posix(),
    }
    save_json(LATEST_VERIFICATION_POINTER_PATH, pointer)


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run independent multi-model verification over an immutable "
            "No Safe Circle reconciliation snapshot."
        )
    )
    parser.add_argument(
        "--run-id",
        help="Reconciliation run ID to verify. Defaults to outputs/LATEST.json.",
    )
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help="Audit only; do not produce a refined candidate when errors are found.",
    )
    parser.add_argument(
        "--no-reverify",
        action="store_true",
        help="After refinement, do not run the independent audit crew a second time.",
    )
    return parser.parse_args()


def main() -> int:
    paths: dict[str, Any] | None = None

    try:
        args = parse_args()
        source_run_id, source_candidate = resolve_source_snapshot(args.run_id)
        paths = create_verification_paths(source_run_id)

        seed = secrets.randbits(64)
        rng = random.Random(seed)
        pass1_assignments = choose_audit_models(rng)
        refiner_model = choose_refiner_model(rng, pass1_assignments)
        pass2_assignments = choose_audit_models(rng)

        model_assignments = {
            "schema_version": "1.0",
            "random_seed": seed,
            "model_pool": MODEL_POOL,
            "pass1": pass1_assignments,
            "refiner": refiner_model,
            "pass2": pass2_assignments,
            "note": (
                "Requested model aliases/names are recorded for auditability. "
                "Assignments are intentionally varied; no majority voting is used."
            ),
        }
        save_new_json(paths["model_assignments"], model_assignments)

        print()
        print("=" * 72)
        print("NO SAFE CIRCLE -- MULTI-MODEL RECONCILIATION VERIFICATION")
        print("=" * 72)
        print(f"Source reconciliation: {source_run_id}")
        print(f"Model pool: {', '.join(MODEL_POOL)}")
        print(f"Random assignment seed: {seed}")
        print("Auditors run independently; findings are unioned, not voted.")
        print("=" * 72)

        pass1_audits = run_audit_pass(
            candidate_path=source_candidate,
            source_run_id=source_run_id,
            pass_label="pass1",
            output_dir=paths["pass1_dir"],
            assignments=pass1_assignments,
        )
        merged1 = merge_findings(pass1_audits)
        save_new_json(paths["merged_pass1"], merged1)

        refinement_performed = False
        final_candidate = source_candidate
        final_merged = merged1

        if has_material_findings(merged1) and not args.no_refine:
            refinement_performed = True
            refiner = run_refiner(
                source_candidate=source_candidate,
                merged_findings_path=paths["merged_pass1"],
                source_run_id=source_run_id,
                model=refiner_model,
            )
            refined_payload = refiner["result"]
            save_new_json(paths["refined_raw"], refined_payload)

            removed = sanitize_forbidden_evidence(refined_payload)
            if removed:
                print(
                    "Warning: Refiner returned forbidden evidence that was "
                    "removed before validation: " + ", ".join(removed)
                )

            removed_tracking = sanitize_refiner_input_tracking(refined_payload)
            if removed_tracking:
                print(
                    "Normalized Refiner bookkeeping paths out of "
                    "sources.files_reviewed: " + ", ".join(removed_tracking)
                )

            repair_missing_dependency_references(refined_payload)
            run_semantic_validation(refined_payload)

            save_new_json(paths["refined_json"], refined_payload)
            save_new_text(paths["refined_markdown"], render_markdown(refined_payload))

            refined_delta = build_proposed_graph_delta(
                refined_payload,
                run_id=source_run_id,
                created_at_utc=paths["created_at_utc"],
            )
            # This is a verification candidate delta, never an automatic graph write.
            refined_delta["verification_run_id"] = paths["verification_run_id"]
            refined_delta["source_reconciliation_run_id"] = source_run_id
            save_new_json(paths["refined_delta_json"], refined_delta)
            save_new_text(
                paths["refined_delta_markdown"],
                render_graph_delta_markdown(refined_delta),
            )
            final_candidate = paths["refined_json"]

            if not args.no_reverify:
                pass2_audits = run_audit_pass(
                    candidate_path=final_candidate,
                    source_run_id=source_run_id,
                    pass_label="pass2",
                    output_dir=paths["pass2_dir"],
                    assignments=pass2_assignments,
                )
                final_merged = merge_findings(pass2_audits)
                save_new_json(paths["merged_pass2"], final_merged)

        status = status_from_pass2(final_merged)

        summary = {
            "schema_version": "1.0",
            "source_run_id": source_run_id,
            "verification_run_id": paths["verification_run_id"],
            "created_at_utc": paths["created_at_utc"],
            "status": status,
            "source_candidate": source_candidate.relative_to(ROOT).as_posix(),
            "final_candidate": final_candidate.relative_to(ROOT).as_posix(),
            "refinement_performed": refinement_performed,
            "model_assignments": {
                "pass1": pass1_assignments,
                "refiner": refiner_model if refinement_performed else None,
                "pass2": (
                    pass2_assignments
                    if refinement_performed and not args.no_reverify
                    else None
                ),
            },
            "pass1": merged1,
            "final_pass": final_merged,
            "human_approval_required": True,
            "persistent_graph_mutated": False,
        }
        save_new_json(paths["summary_json"], summary)
        save_new_text(paths["summary_markdown"], render_verification_markdown(summary))
        write_latest_verification_pointer(paths, status)

        if refinement_performed:
            current_delta_json = paths["refined_delta_json"]
            current_delta_markdown = paths["refined_delta_markdown"]
            current_candidate_markdown = paths["refined_markdown"]
        else:
            source_dir = RUNS_DIR / source_run_id
            current_delta_json = source_dir / "PROPOSED_GRAPH_DELTA.json"
            current_delta_markdown = source_dir / "PROPOSED_GRAPH_DELTA.md"
            current_candidate_markdown = source_dir / "RECONCILIATION.md"

        write_current_view(
            source_reconciliation_run_id=source_run_id,
            status=status,
            candidate_json=final_candidate,
            candidate_markdown=current_candidate_markdown,
            delta_json=current_delta_json,
            delta_markdown=current_delta_markdown,
            verification_run_id=paths["verification_run_id"],
            verification_summary_json=paths["summary_json"],
            verification_markdown=paths["summary_markdown"],
        )

        print()
        print("=" * 72)
        print("MULTI-MODEL VERIFICATION COMPLETE")
        print("=" * 72)
        print(f"Status: {status}")
        print(f"Pass 1 material findings: {merged1.get('material_finding_count', 0)}")
        print(
            "Final material findings: "
            f"{final_merged.get('material_finding_count', 0)}"
        )
        print(f"Refinement performed: {refinement_performed}")
        print(f"Saved: {paths['summary_markdown'].relative_to(ROOT)}")
        print(f"Saved: {paths['summary_json'].relative_to(ROOT)}")
        if refinement_performed:
            print(f"Refined candidate: {paths['refined_json'].relative_to(ROOT)}")
            print(
                "The original immutable reconciliation snapshot was not modified."
            )
        print("Tasks/*.yaml was not modified.")
        print("=" * 72)
        return 0

    except Exception as exc:
        print()
        print("=" * 72, file=sys.stderr)
        print("RECONCILIATION VERIFICATION FAILED", file=sys.stderr)
        print("=" * 72, file=sys.stderr)
        if paths is not None:
            print(
                f"Verification directory preserved: {paths['run_dir'].relative_to(ROOT)}",
                file=sys.stderr,
            )
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
