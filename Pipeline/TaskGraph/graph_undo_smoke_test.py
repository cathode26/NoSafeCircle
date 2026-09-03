from __future__ import annotations

import tempfile
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
ROOT = PIPELINE.parent
for module_root in (str(ROOT), str(PIPELINE), str(HERE)):
    if module_root not in sys.path:
        sys.path.insert(0, module_root)

from apply_graph_delta import apply_graph_delta
from graph_apply_smoke_test import (
    UNRELATED_TRACKED_PATH,
    approved_identity_environment,
    commit_count,
    commit_fixture_change,
    create_fixture,
    git,
    status,
)
from undo_graph_delta import (
    GraphDeltaUndoError,
    inspect_graph_delta_undo,
    undo_graph_delta,
)


def test_exact_apply_can_be_undone_and_reapplied() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-undo-reapply-") as temporary:
        fixture = create_fixture(Path(temporary))
        with approved_identity_environment():
            applied = apply_graph_delta(
                fixture.root,
                fixture.selector,
                fixture.decomposition_result,
                fixture.stored_plan,
                expected_head=fixture.initial_head,
            )
            assert applied.status == "applied"
            undo_plan = inspect_graph_delta_undo(
                fixture.root,
                fixture.stored_plan,
                expected_head=applied.new_commit_sha,
            )
            assert undo_plan.apply_commit == applied.new_commit_sha
            undone = undo_graph_delta(
                fixture.root,
                fixture.stored_plan,
                expected_head=applied.new_commit_sha,
            )
        assert undone.status == "undone"
        assert git(fixture.root, "rev-parse", "HEAD^{tree}") == git(
            fixture.root, "rev-parse", f"{fixture.initial_head}^{{tree}}"
        )
        assert status(fixture.root) == ""
        assert commit_count(fixture.root) == 3

        # The additive undo restores semantic source state, so the same exact
        # independently reviewed decomposition remains eligible to apply again.
        with approved_identity_environment():
            reapplied = apply_graph_delta(
                fixture.root,
                fixture.selector,
                fixture.decomposition_result,
                fixture.stored_plan,
                expected_head=undone.undo_commit,
            )
        assert reapplied.status == "applied"
        assert status(fixture.root) == ""


def test_later_history_refuses_automatic_undo() -> None:
    with tempfile.TemporaryDirectory(prefix="d1c-undo-later-history-") as temporary:
        fixture = create_fixture(Path(temporary))
        with approved_identity_environment():
            applied = apply_graph_delta(
                fixture.root,
                fixture.selector,
                fixture.decomposition_result,
                fixture.stored_plan,
            )
        assert applied.status == "applied"
        unrelated = fixture.root / UNRELATED_TRACKED_PATH
        unrelated.write_text(
            "Later work may depend on decomposed children.\n",
            encoding="utf-8",
            newline="\n",
        )
        later_head = commit_fixture_change(
            fixture.root,
            "fixture: later dependent history",
            UNRELATED_TRACKED_PATH,
        )
        before_count = commit_count(fixture.root)
        with approved_identity_environment():
            try:
                undo_graph_delta(fixture.root, fixture.stored_plan)
            except GraphDeltaUndoError as exc:
                assert "HEAD is not the exact D1C decomposition commit" in str(exc)
            else:
                raise AssertionError("later history was automatically undone")
        assert git(fixture.root, "rev-parse", "HEAD") == later_head
        assert commit_count(fixture.root) == before_count
        assert status(fixture.root) == ""


def main() -> int:
    test_exact_apply_can_be_undone_and_reapplied()
    print("PASS test_exact_apply_can_be_undone_and_reapplied")
    test_later_history_refuses_automatic_undo()
    print("PASS test_later_history_refuses_automatic_undo")
    print("TaskGraph graph undo smoke tests: PASS (2 tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
