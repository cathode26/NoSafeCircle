from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "Pipeline" / "Reconciliation"
OUTPUT_DIR = AGENT_ROOT / "outputs"
RUNS_DIR = OUTPUT_DIR / "runs"
LEGACY_VERIFICATIONS_DIR = OUTPUT_DIR / "verifications"
CURRENT_DIR = OUTPUT_DIR / "current"
LATEST_POINTER_PATH = OUTPUT_DIR / "LATEST.json"
LATEST_VERIFICATION_POINTER_PATH = OUTPUT_DIR / "LATEST_VERIFICATION.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return value


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def verification_root(source_run_id: str) -> Path:
    """New layout: verification history lives under its source run."""
    return RUNS_DIR / source_run_id / "verifications"


def resolve_verification_dir(source_run_id: str, verification_run_id: str) -> Path:
    """Resolve new nested layout first, then the pre-migration legacy layout."""
    nested = verification_root(source_run_id) / verification_run_id
    if nested.exists():
        return nested

    legacy = LEGACY_VERIFICATIONS_DIR / source_run_id / verification_run_id
    if legacy.exists():
        return legacy

    return nested


def _copy_optional(source: Path | None, target: Path) -> None:
    if source is not None and source.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    elif target.exists():
        target.unlink()


def render_current_status(metadata: dict[str, Any]) -> str:
    status = str(metadata.get("status", "unknown"))
    source_run = str(metadata.get("source_reconciliation_run_id", ""))
    verification_run = str(metadata.get("verification_run_id", ""))
    candidate = str(metadata.get("candidate_source", ""))
    delta = str(metadata.get("delta_source", ""))
    execution_unknown = int(metadata.get("execution_scope_unknown_count", 0) or 0)

    lines = [
        "# Current Reconciliation Status",
        "",
        "> Convenience view only. Immutable historical evidence lives under `outputs/runs/`.",
        "",
        f"- **Status:** `{status}`",
        f"- **Source reconciliation:** `{source_run}`",
    ]
    if verification_run:
        lines.append(f"- **Verification:** `{verification_run}`")
    lines.extend(
        [
            f"- **Current candidate source:** `{candidate}`",
            f"- **Current graph-delta source:** `{delta}`",
            f"- **Unknown execution scopes:** `{execution_unknown}`",
            "- **Persistent `Tasks/*.yaml` mutated:** `false`",
            "",
        ]
    )

    if status == "needs_human_review":
        lines.extend(
            [
                "## What this means",
                "",
                "The latest refined candidate still has material verifier findings. It is the current candidate, **not an approved final graph seed**.",
                "",
            ]
        )
    elif status in {"verified", "verified_with_findings"}:
        lines.extend(
            [
                "## What this means",
                "",
                "The latest candidate completed automated verification but still requires human approval before graph seeding.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## What this means",
                "",
                "The latest reconciliation is available here for review. Run verification before treating it as an approved bootstrap seed.",
                "",
            ]
        )

    lines.extend(
        [
            "## Files to read",
            "",
            "- `CANDIDATE.md` — current human-readable reconciliation candidate",
            "- `PROPOSED_GRAPH_DELTA.md` — current proposed persistent-graph seed/delta",
            "- `VERIFICATION.md` — latest verifier report, when one exists",
            "- `CURRENT.json` — machine-readable pointer metadata",
            "",
        ]
    )
    return "\n".join(lines)


def write_current_view(
    *,
    source_reconciliation_run_id: str,
    status: str,
    candidate_json: Path,
    candidate_markdown: Path,
    delta_json: Path,
    delta_markdown: Path,
    verification_run_id: str | None = None,
    verification_summary_json: Path | None = None,
    verification_markdown: Path | None = None,
) -> dict[str, Any]:
    """
    Replace the mutable human-facing `outputs/current/` convenience view.

    Historical run artifacts are never changed by this function.
    """
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)

    _copy_optional(candidate_json, CURRENT_DIR / "CANDIDATE.json")
    _copy_optional(candidate_markdown, CURRENT_DIR / "CANDIDATE.md")
    _copy_optional(delta_json, CURRENT_DIR / "PROPOSED_GRAPH_DELTA.json")
    _copy_optional(delta_markdown, CURRENT_DIR / "PROPOSED_GRAPH_DELTA.md")
    _copy_optional(verification_summary_json, CURRENT_DIR / "VERIFICATION_SUMMARY.json")
    _copy_optional(verification_markdown, CURRENT_DIR / "VERIFICATION.md")

    candidate_payload = load_json(candidate_json)
    unknown_execution = sum(
        1
        for item in candidate_payload.get("work_items", [])
        if item.get("kind") in {"implementation", "artifact"}
        and item.get("graph_status") == "open"
        and str(item.get("execution_scope", "unknown")) == "unknown"
    )

    metadata = {
        "schema_version": "1.0",
        "updated_at_utc": utc_now_iso(),
        "status": status,
        "source_reconciliation_run_id": source_reconciliation_run_id,
        "verification_run_id": verification_run_id or "",
        "candidate_source": candidate_json.relative_to(ROOT).as_posix(),
        "delta_source": delta_json.relative_to(ROOT).as_posix(),
        "verification_summary_source": (
            verification_summary_json.relative_to(ROOT).as_posix()
            if verification_summary_json is not None and verification_summary_json.exists()
            else ""
        ),
        "execution_scope_unknown_count": unknown_execution,
        "persistent_graph_mutated": False,
    }
    save_json(CURRENT_DIR / "CURRENT.json", metadata)
    (CURRENT_DIR / "STATUS.md").write_text(
        render_current_status(metadata), encoding="utf-8"
    )
    (CURRENT_DIR / "README.md").write_text(
        "# Current Reconciliation View\n\n"
        "This directory is intentionally mutable and exists only to answer: "
        "**what should I read right now?**\n\n"
        "Immutable reconciliation and verification history remains under "
        "`../runs/<reconciliation-run>/`. Do not treat files in `current/` as "
        "historical evidence.\n",
        encoding="utf-8",
    )
    return metadata
