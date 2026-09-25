"""A CONTRACT diagnosis renders an evidence-only GER problem packet, and nothing else."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.ger_problem_packet import (  # noqa: E402
    ProblemPacketError,
    build_problem_packet,
    publish_problem_packet,
)
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.run_diagnosis import diagnose_run, load_run_snapshot  # noqa: E402
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    needs_human_review,
    pass_review,
    provider_factory,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import create_repository, decomposed_result  # noqa: E402


def produce(base: Path, *, contract_stop: bool) -> Path:
    tasks = create_repository(base / "source")
    parent = tasks["NSC-010"]
    raw = decomposed_result(parent)
    digest = candidate_sha256(validated_candidate(raw, parent, tasks))
    if contract_stop:
        review = needs_human_review(digest)
        review["findings"][0]["affected_contracts"] = ["NSC-010 AC-001", "NSC-010", "NSC-012", "proposed:child"]
    else:
        review = pass_review(digest)
    run_round_robin_decomposition(
        source=base / "source", output_root=base / "output", task_id="NSC-010",
        provider_order=("codex", "claude"), max_calls=2, run_id="packet-run",
        provider_factory=provider_factory({"codex": QueueProvider([raw]), "claude": QueueProvider([review])}),
        _require_physical_read_only_source=False,
    )
    return base / "output" / "packet-run"


def packet_for(run_dir: Path) -> dict[str, Any]:
    return build_problem_packet(run_dir, diagnose_run(run_dir), load_run_snapshot(run_dir).result)


def refused(action: Callable[[], Any], fragment: str) -> None:
    try:
        action()
    except ProblemPacketError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected a refusal containing {fragment!r}")


def test_a_contract_stop_renders_quoted_evidence_only() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        base = Path(text)
        run_dir = produce(base, contract_stop=True)
        assert diagnose_run(run_dir)["primary"]["route"] == "CONTRACT"
        packet = packet_for(run_dir)
        assert packet["authority"] == "diagnostic_only_not_applied" and packet["retry_authorized"] is False
        assert "does not establish that the contract is defective" in packet["meaning"]
        finding = packet["reviews"][0]["findings"][0]
        quoted = {clause["reference"]: clause for clause in finding["quoted_parent_clauses"]}
        assert quoted["NSC-010 AC-001"]["requirement"] == "selected-parent acceptance.", quoted
        assert quoted["NSC-010"]["entry_id"] is None
        assert {item["reference"] for item in finding["unresolved_references"]} == {"NSC-012", "proposed:child"}
        assert "context.json" in packet["input_sha256"] and "rounds/02/review.json" in packet["input_sha256"]

        out = base / "packet"
        hashes = publish_problem_packet(out, packet)
        markdown = (out / "GER_PROBLEM.md").read_text(encoding="utf-8")
        assert markdown.startswith("# Unapproved decomposition diagnostic - evidence only")
        assert "> **NSC-010 AC-001** (acceptance_criteria): selected-parent acceptance." in markdown
        assert "No replacement contract text, approval or GER decision is proposed here." in markdown
        manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["ger_problem_md_sha256"] == hashes["GER_PROBLEM.md"]
        for forbidden in ("revised_contract", "patch", "approval", "decision_record"):
            assert forbidden not in manifest, forbidden
        refused(lambda: publish_problem_packet(out, packet), "refusing to overwrite")


def test_only_a_contract_diagnosis_gets_a_packet() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
        run_dir = produce(Path(text), contract_stop=False)
        refused(lambda: packet_for(run_dir), "only built for a CONTRACT diagnosis")


def test_tampered_or_unbound_evidence_is_refused() -> None:
    def rewrite(path: Path, change: Callable[[dict], None]) -> None:
        value = json.loads(path.read_text(encoding="utf-8"))
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    cases = (
        ("review.json", lambda run_dir: rewrite(run_dir / "rounds" / "02" / "review.json",
                                                lambda r: r["findings"][0].update(problem="rewritten")),
         "differs between the result and retained files"),
        ("context", lambda run_dir: rewrite(run_dir / "context.json",
                                            lambda c: c["selected_task"]["contract"].update(notes="edited")),
         "does not hash to the run's context_sha256"),
    )
    for label, tamper, fragment in cases:
        with tempfile.TemporaryDirectory(prefix="nsc-ger-packet-") as text:
            run_dir = produce(Path(text), contract_stop=True)
            diagnosis = diagnose_run(run_dir)
            result = deepcopy(load_run_snapshot(run_dir).result)
            tamper(run_dir)
            refused(lambda: build_problem_packet(run_dir, diagnosis, result), fragment)


TESTS = (
    test_a_contract_stop_renders_quoted_evidence_only,
    test_only_a_contract_diagnosis_gets_a_packet,
    test_tampered_or_unbound_evidence_is_refused,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition GER problem packet smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
