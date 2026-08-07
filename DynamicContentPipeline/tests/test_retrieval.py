from __future__ import annotations

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from retrieval import GDDRetriever  # noqa: E402


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        knowledge_base = (
            PIPELINE_DIR
            / "knowledge_base"
            / "No_Safe_Circle_GDD_RAG.json"
        )
        cls.retriever = GDDRetriever(knowledge_base)

    def retrieve(self, query: str, top_k: int = 4):
        results = self.retriever.retrieve(query, top_k=top_k)
        self.assertTrue(results, f"No results returned for query: {query}")
        self.assertTrue(
            all(result["domain"] == "game_design" for result in results),
            f"Non-game-design result returned for query: {query}",
        )
        self.assertTrue(
            all(result["canonical"] is True for result in results),
            f"Noncanonical result returned for query: {query}",
        )
        return results

    def assert_first(self, query: str, expected_chunk_id: str) -> None:
        results = self.retrieve(query)
        self.assertEqual(
            expected_chunk_id,
            results[0]["chunk_id"],
            f"Unexpected first result for query: {query}",
        )

    def test_01_frost_field_limitations(self) -> None:
        self.assert_first(
            "What limitations apply to Frost Field against ranged enemies?",
            "nsc-gdd-010",
        )

    def test_02_force_wave_use_and_cooldown(self) -> None:
        self.assert_first(
            "When should the player use Force Wave, and why can it not be used repeatedly?",
            "nsc-gdd-011",
        )

    def test_03_door_opening_and_locking(self) -> None:
        results = self.retrieve(
            "What interrupts opening a sealed door, what happens after the player locks it, and can the door be reopened?"
        )
        top_two = {result["chunk_id"] for result in results[:2]}
        self.assertEqual(
            {"nsc-gdd-008", "nsc-gdd-021"},
            top_two,
            "The two primary door-opening chunks were not the top two results",
        )

    def test_04_door_breach_and_persistence(self) -> None:
        self.assert_first(
            "What happens when a locked door breaks, and how do surviving enemies carry forward into later rooms?",
            "nsc-gdd-022",
        )

    def test_05_ruined_entry(self) -> None:
        self.assert_first(
            "What is the layout, tactical purpose, route choice, and player lesson of Ruined Entry?",
            "nsc-gdd-015",
        )

    def test_06_bone_archive(self) -> None:
        self.assert_first(
            "What is the layout, tactical purpose, route choice, and player lesson of Bone Archive?",
            "nsc-gdd-016",
        )

    def test_07_chapel_of_ash(self) -> None:
        self.assert_first(
            "What is the layout, tactical purpose, route choice, and player lesson of Chapel of Ash?",
            "nsc-gdd-017",
        )

    def test_08_lower_vault(self) -> None:
        self.assert_first(
            "What is the layout, tactical purpose, route choice, and player lesson of Lower Vault?",
            "nsc-gdd-018",
        )

    def test_09_final_room(self) -> None:
        self.assert_first(
            "What is the layout, tactical purpose, route choice, and player lesson of Final Room?",
            "nsc-gdd-019",
        )

    def test_10_excluded_loot_and_equipment(self) -> None:
        self.assert_first(
            "What loot and equipment progression does the player use?",
            "nsc-gdd-023",
        )

    def test_11_fireball_tap_versus_charge(self) -> None:
        results = self.retrieve(
            "What is the difference between tap Fireball and Charged Fireball, and when is charging unsafe?"
        )
        self.assertEqual("nsc-gdd-009", results[0]["chunk_id"])
        top_two = {result["chunk_id"] for result in results[:2]}
        self.assertIn(
            "nsc-gdd-006",
            top_two,
            "The general Fireball action chunk should appear in the top two",
        )

    def test_12_declared_chunk_count_matches(self) -> None:
        data = self.retriever.data
        self.assertEqual(
            data["document"]["total_chunks"],
            len(data["chunks"]),
        )
        self.assertEqual(39, len(data["chunks"]))

    def test_13_chunk_ids_are_unique(self) -> None:
        chunk_ids = [chunk["chunk_id"] for chunk in self.retriever.data["chunks"]]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))

    def test_14_source_paths_exist(self) -> None:
        data = self.retriever.data
        paths = {
            data["document"]["source_docx"],
            data["document"]["canonical_markdown"],
        }
        paths.update(chunk["source"]["file"] for chunk in data["chunks"])
        missing = [
            str(path)
            for path in sorted(paths)
            if not (REPO_ROOT / path).exists()
        ]
        self.assertEqual([], missing, f"Missing source paths: {missing}")

    def test_15_top_k_is_respected(self) -> None:
        results = self.retrieve(
            "How does Frost Field work?",
            top_k=3,
        )
        self.assertEqual(3, len(results))

    def test_16_empty_query_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "at least one searchable term",
        ):
            self.retriever.retrieve("the and what")

    def test_17_results_are_deterministic(self) -> None:
        query = "What is the tactical purpose of Chapel of Ash?"
        first_run = self.retriever.retrieve(query, top_k=4)
        second_run = self.retriever.retrieve(query, top_k=4)
        self.assertEqual(first_run, second_run)


if __name__ == "__main__":
    unittest.main(verbosity=2)
