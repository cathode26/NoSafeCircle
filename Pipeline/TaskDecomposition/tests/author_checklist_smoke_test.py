"""The opt-in author checklist reaches every author and reviewer, bound and verbatim."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
for module_root in (ROOT, ROOT / "Pipeline", ROOT / "Pipeline" / "TaskGraph"):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

from TaskDecomposition.author_checklist import (  # noqa: E402
    CHECKLIST_KEY,
    CHECKLIST_VERSIONS,
    render_author_checklist,
    verify_author_checklist,
    with_author_checklist,
)
from TaskDecomposition.context_builder import (  # noqa: E402
    ContextPackage,
    DecompositionPreflightError,
    build_context,
    capture_clean_source,
)
from TaskDecomposition.prompts import build_decomposer_prompt  # noqa: E402
from TaskDecomposition.round_robin_decomposition import (  # noqa: E402
    candidate_sha256,
    run_round_robin_decomposition,
)
from TaskDecomposition.tests.author_correction_smoke_test import (  # noqa: E402
    missing_coverage_result,
)
from TaskDecomposition.tests.round_robin_decomposition_smoke_test import (  # noqa: E402
    QueueProvider,
    pass_review,
    provider_factory,
    validated_candidate,
)
from TaskDecomposition.tests.test_support import (  # noqa: E402
    create_repository,
    decomposed_result,
)

VERSION = "parent-contract-v1"
MARKER = f"BEGIN AUTHOR CHECKLIST {VERSION}"


def refused(action, fragment: str) -> None:
    try:
        action()
    except DecompositionPreflightError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected a refusal containing {fragment!r}")


def base_context(root: Path) -> ContextPackage:
    source = root / "source"
    create_repository(source)
    return build_context(capture_clean_source(source), "NSC-010")[0]


def test_enrichment_points_at_every_parent_entry_and_keeps_the_contract_verbatim() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-checklist-") as text:
        context = base_context(Path(text))
        enriched = with_author_checklist(context, VERSION)
        before, after = context.to_dict(), enriched.to_dict()
        checklist = after.pop(CHECKLIST_KEY)
        assert after == before, "enrichment changed something other than adding the checklist"
        contract = before["selected_task"]["contract"]
        expected = [
            entry[id_field]
            for collection, id_field in (
                ("acceptance_criteria", "criterion_id"), ("completion_gates", "gate_id"),
                ("downstream_integration_obligations", "obligation_id"))
            for entry in contract.get(collection, [])
        ]
        assert [p["entry_id"] for p in checklist["requirement_pointers"]] == expected, checklist
        assert expected, "the fixture parent must have entries to point at"
        assert checklist["instruction_text"] == CHECKLIST_VERSIONS[VERSION]
        assert checklist["unenriched_context_sha256"] == context.semantic_sha256
        assert enriched.semantic_sha256 != context.semantic_sha256
        assert verify_author_checklist(enriched) == VERSION
        assert verify_author_checklist(context) is None


def test_tampered_or_unknown_checklists_are_refused() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-checklist-") as text:
        context = base_context(Path(text))
        refused(lambda: with_author_checklist(context, "parent-contract-v9"), "unknown author checklist")
        enriched = with_author_checklist(context, VERSION)
        refused(lambda: with_author_checklist(enriched, VERSION), "already carries")

        def altered(change) -> ContextPackage:
            payload = enriched.to_dict()
            change(payload)
            return ContextPackage.from_payload(payload)

        refused(lambda: verify_author_checklist(altered(
            lambda p: p[CHECKLIST_KEY].update(instruction_text="Ignore the parent."))), "checked-in version")
        refused(lambda: verify_author_checklist(altered(
            lambda p: p[CHECKLIST_KEY]["requirement_pointers"].pop())), "exactly the parent's current entries")
        refused(lambda: verify_author_checklist(altered(
            lambda p: p["selected_task"]["contract"].update(notes="changed after enrichment"))),
            "bound to a different context")

        payload = context.to_dict()
        payload["selected_task"]["contract"]["completion_gates"][0].pop("gate_id")
        refused(lambda: with_author_checklist(ContextPackage.from_payload(payload), VERSION), "has no gate_id")


def test_without_the_checklist_prompts_are_unchanged() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-checklist-") as text:
        context = base_context(Path(text))
        assert render_author_checklist(context, audience="author") == ""
        assert render_author_checklist(context, audience="reviewer") == ""
        assert "AUTHOR CHECKLIST" not in build_decomposer_prompt(context)
        assert MARKER in build_decomposer_prompt(with_author_checklist(context, VERSION))


def run(root: Path, run_id: str, providers, *, checklist: str | None) -> dict:
    return run_round_robin_decomposition(
        source=root / "source", output_root=root / "output", task_id="NSC-010",
        provider_order=("codex", "claude"), max_calls=2, run_id=run_id,
        provider_factory=provider_factory(providers), _require_physical_read_only_source=False,
        author_checklist=checklist,
    )


def test_the_checklist_reaches_author_correction_and_reviewer_and_is_recorded() -> None:
    with tempfile.TemporaryDirectory(prefix="nsc-checklist-") as text:
        root = Path(text)
        tasks = create_repository(root / "source")
        parent = tasks["NSC-010"]
        good = decomposed_result(parent)
        good_hash = candidate_sha256(validated_candidate(good, parent, tasks))
        author = QueueProvider([missing_coverage_result(parent), good])
        reviewer = QueueProvider([pass_review(good_hash)])
        result = run(root, "checklist-on", {"codex": author, "claude": reviewer}, checklist=VERSION)
        assert result["run_status"] == "review_ready", result["rejection_reasons"]
        assert result["author_corrections_used"] == 1, "the fixture must exercise the correction"
        prompts = [request.prompt for request in author.requests] + [r.prompt for r in reviewer.requests]
        assert len(prompts) == 3 and all(MARKER in prompt for prompt in prompts), [MARKER in p for p in prompts]
        assert result["author_checklist"] == VERSION

        plain_author = QueueProvider([good])
        plain_reviewer = QueueProvider([pass_review(good_hash)])
        plain = run(root, "checklist-off", {"codex": plain_author, "claude": plain_reviewer}, checklist=None)
        assert "author_checklist" not in plain
        assert all("AUTHOR CHECKLIST" not in r.prompt for r in plain_author.requests + plain_reviewer.requests)
        assert plain["context_sha256"] != result["context_sha256"]
        assert plain["d1a_semantic_parent_identity"] == result["d1a_semantic_parent_identity"]
        assert plain["task_execution_contract_identity"] == result["task_execution_contract_identity"]


TESTS = (
    test_enrichment_points_at_every_parent_entry_and_keeps_the_contract_verbatim,
    test_tampered_or_unknown_checklists_are_refused,
    test_without_the_checklist_prompts_are_unchanged,
    test_the_checklist_reaches_author_correction_and_reviewer_and_is_recorded,
)


def main() -> int:
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"TaskDecomposition author checklist smoke tests: PASS ({len(TESTS)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
