"""Unit tests for the compile_game_list module."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

#pylint: disable=missing-function-docstring

from CompileDataset.CreateGameList.compile_game_list import (
    DATASET_PATH,
    OUTPUT_PATH,
    PROJECT_ROOT,
    categorize_price,
    categorize_publisher_count,
    categorize_release_date,
    create_grouped_sample,
    get_publisher_game_count,
)


class PathConfigurationTests(unittest.TestCase):
    def test_dataset_path_resolves_from_repository_root(self) -> None:
        repository_root = Path(__file__).resolve().parents[2]

        self.assertEqual(PROJECT_ROOT, repository_root)
        self.assertEqual(
            DATASET_PATH,
            repository_root / "GameListDataset" / "steam_games.csv",
        )
        self.assertTrue(DATASET_PATH.is_file())

    def test_output_path_is_next_to_script(self) -> None:
        self.assertEqual(
            OUTPUT_PATH,
            Path(__file__).resolve().parent / "grouped_sample.csv",
        )


class CategorizationTests(unittest.TestCase):
    """Tests for dataset categorization helpers."""

    def test_categorize_release_date_boundaries(self) -> None:
        cases = {
            "2016-12-31": "Before 2017",
            "2017-01-01": "2017-2020",
            "2020-12-31": "2017-2020",
            "2021-01-01": "2021-2024",
            "2024-12-31": "2021-2024",
            "2025-01-01": "2025 onward",
        }

        for date, expected in cases.items():
            with self.subTest(date=date):
                self.assertEqual(
                    categorize_release_date(pd.Timestamp(date)),
                    expected,
                )

    def test_categorize_price_boundaries(self) -> None:
        cases = {
            0: "Under $10",
            9.99: "Under $10",
            10: "$10-$25",
            25: "$10-$25",
            25.01: "$25-$55",
            55: "$25-$55",
            55.01: "$55+",
        }

        for price, expected in cases.items():
            with self.subTest(price=price):
                self.assertEqual(categorize_price(price), expected)

    def test_categorize_publisher_count_boundaries(self) -> None:
        cases = {
            0: "Under 5 games",
            4: "Under 5 games",
            5: "5-20 games",
            20: "5-20 games",
            21: "20-50 games",
            50: "20-50 games",
            51: "50-100 games",
            100: "50-100 games",
            101: "100+ games",
        }

        for count, expected in cases.items():
            with self.subTest(count=count):
                self.assertEqual(categorize_publisher_count(count), expected)

    def test_get_publisher_game_count_counts_each_publisher(self) -> None:
        publishers = pd.Series(
            ["['A', 'B']", "['A']", "['C', 'B']", "[]"],
        )

        counts = get_publisher_game_count(publishers)

        self.assertEqual(counts.to_dict(), {"A": 2, "B": 2, "C": 1})


class CreateGroupedSampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = pd.DataFrame(
            {
                "category": ["small"] * 3 + ["medium"] * 10 + ["large"] * 87,
                "app_id": range(100),
            }
        )

    def test_writes_exact_size_with_minimum_and_proportional_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "sample.csv"

            sample = create_grouped_sample(
                self.games.groupby("category"),
                output_path,
                sample_size=30,
                random_state=42,
            )
            sample_counts = sample.groupby("category").size().to_dict()
            saved_sample = pd.read_csv(output_path)

        self.assertEqual(len(sample), 30)
        self.assertEqual(sample_counts, {"large": 24, "medium": 3, "small": 3})
        self.assertEqual(len(saved_sample), 30)
        self.assertTrue(sample["app_id"].is_unique)

    def test_seed_makes_sample_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sample.csv"
            grouped = self.games.groupby("category")

            first = create_grouped_sample(
                grouped, output_path, sample_size=30, random_state=123
            )
            second = create_grouped_sample(
                grouped, output_path, sample_size=30, random_state=123
            )

        self.assertEqual(first["app_id"].tolist(), second["app_id"].tolist())

    def test_rejects_empty_groupby(self) -> None:
        empty_games = pd.DataFrame(columns=["category", "app_id"])

        with self.assertRaisesRegex(ValueError, "empty groupby"):
            create_grouped_sample(empty_games.groupby("category"), sample_size=3)

    def test_rejects_invalid_sample_parameters(self) -> None:
        grouped = self.games.groupby("category")

        for sample_size, minimum_per_group in ((0, 3), (30, 0), (8, 3)):
            with self.subTest(
                sample_size=sample_size,
                minimum_per_group=minimum_per_group,
            ):
                with self.assertRaises(ValueError):
                    create_grouped_sample(
                        grouped,
                        sample_size=sample_size,
                        minimum_per_group=minimum_per_group,
                    )

    def test_rejects_sample_larger_than_available_data(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds the number"):
            create_grouped_sample(
                self.games.groupby("category"),
                sample_size=101,
            )

    def test_rejects_group_smaller_than_minimum(self) -> None:
        games = pd.DataFrame(
            {"category": ["small"] * 2 + ["large"] * 10}
        )

        with self.assertRaisesRegex(ValueError, "at least minimum_per_group"):
            create_grouped_sample(games.groupby("category"), sample_size=6)


if __name__ == "__main__":
    unittest.main()
