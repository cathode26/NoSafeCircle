#!/usr/bin/env python
"""Realistic GER round records, built once for every suite that needs them.

Astra MJ-P2-03: the first versions of these tests wrote `{"protocol": "json-v1"}`
as a round's whole METADATA.json and called it complete. That is not what
ger_round publishes, and testing against it meant the reader's evidence checks
had nothing to check - which is precisely how the reader shipped without them.

A record here carries what a real one carries: the result hash, the copied
completion fields, and the provider evidence check_run required at write time.
Negative cases are produced by overriding one field, so a test that weakens the
record says exactly which fact it removed.

This module exists rather than a helper per suite because three suites need the
same shape, and three copies of one fixture drift the same way three copies of a
guard do - which is the failure this whole family keeps repeating.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ger_round  # noqa: E402
import review_result  # noqa: E402

TASK = "NSC-001"
REAUDIT = "04-claude-reaudit"
REVIEWED = "03-codex-refine"
CANDIDATE = b"The refined candidate.\n"


def result_bytes(*, task_id: str = TASK, artifact: bytes = CANDIDATE,
                 **overrides) -> bytes:
    """One valid GER decision, as a provider would emit it."""
    body = {
        "schema_version": 1,
        "review_kind": "ger",
        "task_id": task_id,
        "reviewed_artifact_kind": "ger_round_output",
        "reviewed_artifact_sha256": ger_round.sha256_bytes(artifact),
        "review_status": "complete",
        "recommendation": "commit_contract",
        "report_markdown": "All prior findings resolved.",
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


def reviewed(packet: Path, artifact: bytes = CANDIDATE,
             directory: str = REVIEWED) -> bytes:
    """The prior round whose bytes a decision round is bound to."""
    (packet / directory).mkdir(parents=True, exist_ok=True)
    (packet / directory / "OUTPUT.md").write_bytes(artifact)
    (packet / directory / "METADATA.json").write_text(
        json.dumps({"round": directory, "protocol": "none",
                    "review_status": "not-a-decision-round", "exit_code": 0}),
        encoding="utf-8")
    return artifact


def decision(packet: Path, raw: bytes | None = None, *, round_name: str = REAUDIT,
             view: str | None = None, **metadata_overrides) -> bytes:
    """A completed decision round, recorded the way ger_round records one.

    `metadata_overrides` weakens or corrupts exactly one fact for a negative
    case; passing `result_sha256=...` or `exit_code=9` produces the records Astra
    used to reproduce MJ-P2-03.
    """
    raw = result_bytes() if raw is None else raw
    directory = packet / round_name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ger_round.RESULT_FILE).write_bytes(raw)

    body = {}
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        pass
    if view is None:
        view = review_result.DERIVED_VIEW_HEADER + "\n\n(rendered human view)\n"
    (directory / "OUTPUT.md").write_text(view, encoding="utf-8")

    metadata = {
        "round": round_name,
        "protocol": "json-v1",
        "result_file": ger_round.RESULT_FILE,
        "result_sha256": ger_round.sha256_bytes(raw),
        "review_status": body.get("review_status") if isinstance(body, dict) else None,
        "recommendation": body.get("recommendation") if isinstance(body, dict) else None,
        "reviewed": f"{REVIEWED}/OUTPUT.md",
        "exit_code": 0,
        "is_error": None,
        "session_id": "session-fixture",
        "model": "fixture-model",
    }
    metadata.update(metadata_overrides)
    (directory / "METADATA.json").write_text(json.dumps(metadata, indent=2),
                                             encoding="utf-8")
    return raw


def legacy(packet: Path, text: str, *, round_name: str = REAUDIT) -> None:
    """A round as it was recorded before the cutover: no protocol, prose output."""
    directory = packet / round_name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "OUTPUT.md").write_text(text, encoding="utf-8")
    (directory / "METADATA.json").write_text(
        json.dumps({"round": round_name, "exit_code": 0,
                    "session_id": "session-legacy"}), encoding="utf-8")
