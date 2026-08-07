from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_DIR))

from retrieval import GDDRetriever  # noqa: E402


STRICT_FIRST = {
    "spell_tooltips": {
        "tap_fireball": "nsc-gdd-006",
        "charged_fireball": "nsc-gdd-009",
        "frost_field": "nsc-gdd-010",
        "force_wave": "nsc-gdd-011",
    },
    "door_tutorial": {
        "door_cross_and_lock": "nsc-gdd-021",
        "door_health_recovery": "nsc-gdd-012",
        "door_breach": "nsc-gdd-022",
    },
    "failure_hints": {
        "poor_positioning": "nsc-gdd-012",
        "low_mana": "nsc-gdd-012",
        "force_wave_misuse": "nsc-gdd-024",
    },
}

# Some production queries legitimately have more than one canonical chunk that can
# answer the question. For those, test retrieval coverage instead of overfitting
# to one arbitrary first-place ranking.
COVERAGE_RULES = {
    ("door_tutorial", "door_opening"): {
        "required_chunks": {"nsc-gdd-008", "nsc-gdd-021"},
        "within_top": 2,
    },
    ("door_tutorial", "persistent_pursuit"): {
        "required_chunks": {"nsc-gdd-022"},
        "within_top": 3,
    },
    ("failure_hints", "waited_too_long"): {
        "required_chunks": {"nsc-gdd-022"},
        "within_top": 3,
    },
}


class ProductionQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request_dir = PIPELINE_DIR / "content_requests"
        cls.retriever = GDDRetriever(
            PIPELINE_DIR
            / "knowledge_base"
            / "No_Safe_Circle_GDD_RAG.json"
        )

    def load_request(self, request_name: str) -> dict:
        path = self.request_dir / f"{request_name}.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def retrieve_item(self, request_name: str, item_id: str):
        request = self.load_request(request_name)
        item = next(item for item in request["items"] if item["id"] == item_id)
        results = self.retriever.retrieve(
            item["query"],
            top_k=int(item.get("top_k", 4)),
        )

        self.assertTrue(results, f"{request_name}/{item_id}: no results")
        self.assertTrue(
            all(result["domain"] == "game_design" for result in results),
            f"{request_name}/{item_id}: returned non-game_design chunk",
        )
        self.assertTrue(
            all(result["canonical"] is True for result in results),
            f"{request_name}/{item_id}: returned noncanonical chunk",
        )
        return results

    def test_strict_primary_queries(self) -> None:
        failures: list[str] = []

        for request_name, items in STRICT_FIRST.items():
            for item_id, expected_chunk in items.items():
                results = self.retrieve_item(request_name, item_id)
                actual_chunk = results[0]["chunk_id"]
                if actual_chunk != expected_chunk:
                    failures.append(
                        f"{request_name}/{item_id}: expected first "
                        f"{expected_chunk}, got {actual_chunk} "
                        f"({results[0]['title']})"
                    )

        self.assertEqual(
            [],
            failures,
            "Strict production retrieval failures:\n" + "\n".join(failures),
        )

    def test_multi_source_queries_have_required_evidence(self) -> None:
        failures: list[str] = []

        for (request_name, item_id), rule in COVERAGE_RULES.items():
            results = self.retrieve_item(request_name, item_id)
            top_results = results[: int(rule["within_top"])]
            top_ids = {result["chunk_id"] for result in top_results}
            missing = set(rule["required_chunks"]) - top_ids

            if missing:
                ranked = ", ".join(
                    f"{i + 1}:{result['chunk_id']}"
                    for i, result in enumerate(results)
                )
                failures.append(
                    f"{request_name}/{item_id}: missing {sorted(missing)} "
                    f"within top {rule['within_top']}; got [{ranked}]"
                )

        self.assertEqual(
            [],
            failures,
            "Production evidence coverage failures:\n" + "\n".join(failures),
        )

    def test_all_request_items_are_covered_by_tests(self) -> None:
        tested = {
            (request_name, item_id)
            for request_name, items in STRICT_FIRST.items()
            for item_id in items
        } | set(COVERAGE_RULES)

        actual = set()
        for request_name in ("spell_tooltips", "door_tutorial", "failure_hints"):
            request = self.load_request(request_name)
            actual.update(
                (request_name, item["id"])
                for item in request["items"]
            )

        self.assertEqual(
            actual,
            tested,
            "Production request items changed; update tests intentionally.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
