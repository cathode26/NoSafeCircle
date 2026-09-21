"""Owner decision revision and fresh re-check rounds for a GER packet whose re-audit needed decisions.

    python ger_decision_revision.py build --packet <dir> --revised <json> --decisions <md> --change-log <md>
    python ger_decision_revision.py recheck --packet <dir> --report <md> --reviewer <text>

build writes the immutable 07-owner-decision-revision round: the GER owner's revised contract, the
decisions it applies and a change log, bound by hash to the round-03 and round-04 outputs. It refuses a
contract whose top-level keys differ from the current task file, that changes an invariant field, that
does not raise contract_revision by exactly one, or that adds task_design_ger records.

recheck writes the immutable 08-claude-recheck round from a fresh Claude reviewer's result. That result
is one JSON object declaring its verdict, bound to the exact REVISED_CONTRACT.json bytes it reviewed;
the reviewer no longer names a 16-hex prefix in prose and nothing here reads a verdict out of Markdown.
The report is stored verbatim as RESULT.json and rendered into OUTPUT.md as a labelled human view.

Round 08 is an IMPORT. The result is handed over by the GER owner rather than produced by a provider run
here, so it carries no exit code and no session id, and inventing either would be fabricating evidence
for a run that did not happen. Its record says `provider_evidence: imported` and names the file it came
from, which is what ger_round.check_record requires of an import before any consumer will read it.

`--legacy` reads a report written before the cutover with the old Markdown parser. It is a declaration
by the caller and is never inferred from the bytes: a new-format result that fails to validate is
refused, never retried through the old reader.

apply_contract.py commits only when the recommendation is commit_contract or
commit_contract_then_decompose. Neither command edits the repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess

import apply_contract
# apply_contract puts Tools/Host and Tools/Host/ger on sys.path; these two are
# named explicitly because this module uses them directly, not through it.
import ger_round  # noqa: E402
import review_result  # noqa: E402

BUILD = "07-owner-decision-revision"
RECHECK = "08-claude-recheck"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def repository_head() -> str:
    return subprocess.run(["git", "-C", str(apply_contract.REPO), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def fail(round_dir: pathlib.Path, reason: str) -> None:
    (round_dir / "FAILED.json").write_text(json.dumps({"failed_at": utc_now(), "reason": reason}, indent=2) + "\n",
                                           encoding="utf-8")
    raise SystemExit(f"{round_dir.name} failed: {reason}")


def build(args: argparse.Namespace) -> int:
    packet = args.packet.resolve()
    identity = json.loads((packet / "SOURCE_IDENTITY.json").read_text(encoding="utf-8"))
    task_id = identity["task_id"]
    inputs = {}
    for name in ("03-codex-refine", "04-claude-reaudit"):
        if (packet / name / "FAILED.json").exists() or not (packet / name / "OUTPUT.md").is_file():
            raise SystemExit(f"round {name} is missing or failed")
        inputs[f"{name}/OUTPUT.md"] = sha256((packet / name / "OUTPUT.md").read_bytes())
    round_dir = packet / BUILD
    round_dir.mkdir()  # immutable: fails if the round already exists
    try:
        revised = json.loads(args.revised.read_bytes())
        current = json.loads((apply_contract.REPO / "Tasks" / f"{task_id}.yaml").read_bytes())
    except (OSError, ValueError) as error:
        fail(round_dir, f"could not read the revised or current contract: {error}")
    if set(revised) != set(current):
        fail(round_dir, f"top-level keys differ from Tasks/{task_id}.yaml: missing {sorted(set(current) - set(revised))}, "
                        f"extra {sorted(set(revised) - set(current))}")
    for field in apply_contract.INVARIANT_FIELDS:
        if revised.get(field) != current.get(field):
            fail(round_dir, f"invariant field {field} changed: {current.get(field)!r} -> {revised.get(field)!r}")
    if revised.get("contract_revision") != current.get("contract_revision", 0) + 1:
        fail(round_dir, f"contract_revision must be {current.get('contract_revision', 0) + 1}, got {revised.get('contract_revision')}")
    current_ger = (current.get("provenance") or {}).get("task_design_ger")
    if (revised.get("provenance") or {}).get("task_design_ger") != current_ger:
        fail(round_dir, "the revised contract must not add or change provenance.task_design_ger; apply_contract.py appends it")

    contract_bytes = (json.dumps(revised, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    decisions = args.decisions.read_bytes()
    change_log = args.change_log.read_bytes()
    (round_dir / "REVISED_CONTRACT.json").write_bytes(contract_bytes)
    (round_dir / "DECISIONS.md").write_bytes(decisions)
    (round_dir / "CHANGE_LOG.md").write_bytes(change_log)
    changed = sorted(key for key in set(current) | set(revised) if current.get(key) != revised.get(key))
    output = (
        f"# {task_id} owner decision revision\n\n"
        "The GER owner (Claude, at Vincent's direction) applied the recorded design decisions and the round-04 "
        "re-audit's required changes to the round-03 proposal. DECISIONS.md and CHANGE_LOG.md explain every change.\n\n"
        f"- Revised contract sha256: `{sha256(contract_bytes)}`\n"
        f"- Contract revision: {current.get('contract_revision')} -> {revised['contract_revision']}\n"
        f"- Fields that differ from the current contract: {', '.join(changed)}\n\n"
        "## Decisions\n\n" + decisions.decode("utf-8").strip() + "\n\n"
        "## Change log\n\n" + change_log.decode("utf-8").strip() + "\n\n"
        "## Revised task contract\n\n```json\n" + contract_bytes.decode("utf-8") + "```\n"
    ).encode("utf-8")
    (round_dir / "OUTPUT.md").write_bytes(output)
    inputs.update({"DECISIONS.md": sha256(decisions), "CHANGE_LOG.md": sha256(change_log)})
    metadata = {"round": BUILD, "task_id": task_id, "created_at": utc_now(),
                "author": "GER owner (Claude) at Vincent's direction", "packet_source_head": identity["source_head"],
                "repository_head": repository_head(), "input_sha256": inputs,
                "revised_contract_sha256": sha256(contract_bytes), "output_sha256": sha256(output),
                "changed_fields": changed}
    (round_dir / "METADATA.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"round": BUILD, "task_id": task_id, "revised_contract_sha256": sha256(contract_bytes),
                      "changed_fields": changed}, indent=2))
    return 0


def recheck(args: argparse.Namespace) -> int:
    packet = args.packet.resolve()
    build_dir = packet / BUILD
    if (build_dir / "FAILED.json").exists() or not (build_dir / "METADATA.json").is_file():
        raise SystemExit(f"{BUILD} is missing or failed")
    build_meta = json.loads((build_dir / "METADATA.json").read_text(encoding="utf-8"))
    build_output = (build_dir / "OUTPUT.md").read_bytes()
    if sha256(build_output) != build_meta["output_sha256"]:
        raise SystemExit(f"{BUILD}/OUTPUT.md changed after it was built")
    revised_sha = build_meta["revised_contract_sha256"]
    if sha256((build_dir / "REVISED_CONTRACT.json").read_bytes()) != revised_sha:
        raise SystemExit(f"{BUILD}/REVISED_CONTRACT.json changed after it was built")
    report = args.report.read_bytes()
    task_id = build_meta["task_id"]
    revised_bytes = (build_dir / "REVISED_CONTRACT.json").read_bytes()
    round_dir = packet / RECHECK
    round_dir.mkdir()  # immutable

    # Round 08 is an IMPORT: a fresh reviewer's result, handed over by the GER
    # owner rather than produced by a provider run here. So it carries no exit
    # code and no session id, and inventing either would be fabricating evidence
    # for a run that did not happen. The record says `provider_evidence:
    # imported` and names where it came from, which is what ger_round.check_record
    # requires of an import before it will read the decision.
    if args.legacy:
        # The explicitly labelled legacy path, for a report written before the
        # cutover. A declaration by the caller, never inferred from the bytes.
        #
        # One exception, and it only ever REFUSES: a new-format result read with
        # --legacy sails through both old checks by accident. Its
        # reviewed_artifact_sha256 field contains the 16-hex prefix the identity
        # check looks for, and the legacy grep finds `commit_contract` inside
        # `"recommendation": "commit_contract"`. So a mislabelled JSON result
        # would have its verdict read by a grep, which is precisely the
        # cross-format confusion this protocol exists to remove. Refusing here is
        # fail-closed; the forbidden direction is retrying a failed JSON parse as
        # Markdown, and that remains impossible.
        text = report.decode("utf-8", errors="replace")
        try:
            looks_like_json = isinstance(json.loads(text), dict)
        except ValueError:
            looks_like_json = False
        if looks_like_json:
            fail(round_dir, "--legacy was given a JSON document; a new-format result "
                            "must be read as one, not grepped")
        if revised_sha[:16] not in text:
            raise SystemExit("the reviewer report does not name the reviewed contract "
                             "(first 16 hex characters of its sha256)")
        recommendation = apply_contract.final_recommendation(text)
        if recommendation is None:
            raise SystemExit("the reviewer report has no final recommendation")
        review_status, protocol = "complete", "legacy-markdown"
        (round_dir / "OUTPUT.md").write_bytes(report)
        result_sha = None
    else:
        try:
            result = review_result.load(
                report,
                task_id=task_id,
                review_kind="ger",
                reviewed_artifact_kind="ger_round_output",
                reviewed_artifact_sha256=sha256(revised_bytes),
            )
        except review_result.ReviewResultError as error:
            fail(round_dir, f"the reviewer result is not valid ({error.code}): {error.message}")
            raise SystemExit(f"the reviewer result is not valid ({error.code}): {error.message}")
        if not result.is_complete:
            fail(round_dir, "the reviewer declared the review incomplete")
            raise SystemExit("the reviewer declared the review incomplete; there is "
                             "no verdict to record")
        recommendation = result.recommendation
        review_status, protocol = result.review_status, "json-v1"
        (round_dir / ger_round.RESULT_FILE).write_bytes(report)
        (round_dir / "OUTPUT.md").write_text(
            ger_round.render_output(result, f"{BUILD}/REVISED_CONTRACT.json"),
            encoding="utf-8")
        result_sha = sha256(report)

    metadata = {"round": RECHECK, "task_id": task_id, "created_at": utc_now(),
                "reviewer": args.reviewer,
                "repository_head": repository_head(),
                "protocol": protocol,
                "provider_evidence": "imported",
                "imported_from": str(args.report.resolve()),
                "review_status": review_status,
                "input_sha256": {f"{BUILD}/OUTPUT.md": sha256(build_output),
                                 f"{BUILD}/REVISED_CONTRACT.json": revised_sha},
                "output_sha256": sha256((round_dir / "OUTPUT.md").read_bytes()),
                "result_file": ger_round.RESULT_FILE if result_sha else None,
                "result_sha256": result_sha,
                "reviewed": f"{BUILD}/REVISED_CONTRACT.json",
                "recommendation": recommendation}
    (round_dir / "METADATA.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"round": RECHECK, "task_id": task_id, "protocol": protocol,
                      "recommendation": recommendation}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--packet", required=True, type=pathlib.Path)
    build_parser.add_argument("--revised", required=True, type=pathlib.Path)
    build_parser.add_argument("--decisions", required=True, type=pathlib.Path)
    build_parser.add_argument("--change-log", required=True, type=pathlib.Path)
    recheck_parser = commands.add_parser("recheck")
    recheck_parser.add_argument("--packet", required=True, type=pathlib.Path)
    recheck_parser.add_argument("--report", required=True, type=pathlib.Path)
    recheck_parser.add_argument("--reviewer", required=True)
    recheck_parser.add_argument("--legacy", action="store_true",
                                help="the report predates the JSON protocol and is read with "
                                     "the legacy Markdown parser. A declaration by the caller, "
                                     "never inferred: a new-format result that fails to "
                                     "validate is refused, never retried through the old reader.")
    args = parser.parse_args()
    return build(args) if args.command == "build" else recheck(args)


if __name__ == "__main__":
    raise SystemExit(main())
