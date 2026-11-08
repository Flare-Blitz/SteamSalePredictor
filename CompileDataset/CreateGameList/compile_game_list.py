"""Filter through the steam_games csv, which has over 140,000 game rows,
and compile a diverse sample of 1000 games. The data from the Kaggle dataset
is possibly incorrect, so it should be validated before use.

The data is grouped by release date, price, and publisher count. Then a
proportionally stratified sample is selected from each group, with a minimum
of 3 games per group.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.core.groupby.generic import DataFrameGroupBy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "GameListDataset" / "steam_games.csv"
OUTPUT_PATH = Path(__file__).resolve().parent / "grouped_sample.csv"
FETCHED_COLUMNS = ["app_id", "name", "release_date", "price", "publishers"]


def categorize_release_date(release_date: pd.Timestamp) -> str:
    """Categorize the release date of the game based on the year"""
    year = release_date.year
    if year < 2017:
        return "Before 2017"
    elif 2017 <= year <= 2020:
        return "2017-2020"
    elif 2021 <= year <= 2024:
        return "2021-2024"
    else:
        return "2025 onward"

def categorize_price(price: float) -> str:
    """Categorize the price of the game based on its value."""
    if price < 10:
        return "Under $10"
    elif 10 <= price <= 25:
        return "$10-$25"
    elif 25 < price <= 55:
        return "$25-$55"
    else:
        return "$55+"

def categorize_publisher_count(game_count: int) -> str:
    """Categorize the number of games published by a publisher."""
    if game_count < 5:
        return "Under 5 games"
    if 5 <= game_count <= 20:
        return "5-20 games"
    if 20 < game_count <= 50:
        return "20-50 games"
    if 50 < game_count <= 100:
        return "50-100 games"
    return "100+ games"

def get_publisher_game_count(publishers: pd.Series) -> pd.Series:
    """Count the number of games associated with each publisher."""
    # 1. Parse the string into an actual Python list using ast.literal_eval
    publishers = publishers.apply(ast.literal_eval)

    # 2. Explode the lists into individual rows and count unique items
    unique_counts = publishers.explode().value_counts()
    return unique_counts


def create_grouped_sample(
    grouped_df: DataFrameGroupBy,
    output_path: Path = OUTPUT_PATH,
    sample_size: int = 1000,
    minimum_per_group: int = 3,
    random_state: int | None = None,
) -> pd.DataFrame:
    """Write a random, proportionally stratified sample of grouped games to CSV."""
    group_sizes = grouped_df.size()
    if group_sizes.empty:
        raise ValueError("Cannot sample from an empty groupby.")
    if sample_size <= 0 or minimum_per_group < 1:
        raise ValueError("Sample size and minimum per group must be positive.")
    if len(group_sizes) * minimum_per_group > sample_size:
        raise ValueError("Sample size is too small to meet the minimum for every group.")
    if (group_sizes < minimum_per_group).any():
        raise ValueError("Every group must contain at least minimum_per_group rows.")
    if sample_size > int(group_sizes.sum()):
        raise ValueError("Sample size exceeds the number of available games.")

    # Reserve the minimum for undersized strata, then apportion the rest by size.
    allocations = [0] * len(group_sizes)
    active_groups = list(range(len(group_sizes)))
    remaining = sample_size
    sizes = group_sizes.to_numpy()

    while active_groups:
        active_size = sum(sizes[index] for index in active_groups)
        ideal_counts = {
            index: remaining * sizes[index] / active_size
            for index in active_groups
        }
        undersized = [
            index
            for index, ideal_count in ideal_counts.items()
            if ideal_count < minimum_per_group
        ]
        if not undersized:
            for index, ideal_count in ideal_counts.items():
                allocations[index] = int(ideal_count)
            slots_left = remaining - sum(allocations[index] for index in active_groups)
            fractional_order = sorted(
                active_groups,
                key=lambda index: ideal_counts[index] - allocations[index],
                reverse=True,
            )
            for index in fractional_order[:slots_left]:
                allocations[index] += 1
            break

        for index in undersized:
            allocations[index] = minimum_per_group
        remaining -= len(undersized) * minimum_per_group
        active_groups = [
            index for index in active_groups if index not in undersized
        ]

    rng = np.random.default_rng(random_state)
    sampled_groups = [
        grouped_df.get_group(group_key).sample(
            n=count,
            random_state=rng,
        )
        for group_key, count in zip(group_sizes.index, allocations)
    ]
    sampled_df = (
        pd.concat(sampled_groups)
        .sample(frac=1, random_state=rng)
        .reset_index(drop=True)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sampled_df.to_csv(output_path, index=False)
    return sampled_df


def main() -> int:
    """Loads the steam_game dataset, filters it, and writes a grouped sample."""
    df = pd.read_csv(DATASET_PATH, usecols=FETCHED_COLUMNS)

    # Filter out free games, and games with artificially inflated prices
    filtered_df = df[(df["price"] > 0) & (df["price"] < 100)]

    # Parse the release date into a datetime object for filtering
    filtered_df['date_parsed'] = pd.to_datetime(filtered_df['release_date'])

    # Filter out games released after August 1, 2026
    # Older games are preferable for data
    filtered_df = filtered_df[filtered_df["date_parsed"] < pd.Timestamp("2026-08-01")]

    # Count the number of games per publisher
    publisher_game_count = get_publisher_game_count(filtered_df["publishers"])

    # Categorize the release date and price of each game
    filtered_df["release_date_category"] = filtered_df["date_parsed"].apply(
        categorize_release_date
    )
    filtered_df["price_category"] = filtered_df["price"].apply(
        categorize_price
    )

    # Categorize the number of games per publisher
    filtered_df["publisher_game_count"] = filtered_df["publishers"].apply(
        lambda publishers: max(
            (publisher_game_count.get(publisher, 0)
            for publisher in ast.literal_eval(publishers))
        , default=0)
    )
    filtered_df["publisher_game_count_category"] = filtered_df["publisher_game_count"].apply(
        categorize_publisher_count
    )

    # Group the games by release date, price, and publisher game count
    grouped_df = filtered_df.groupby(
        ["release_date_category", "price_category", "publisher_game_count_category"])

    # Create a grouped sample from the filtered dataset
    # Write the sampled dataset to the output file
    sampled_df = create_grouped_sample(grouped_df)
    print(f"Wrote {len(sampled_df)} games to {OUTPUT_PATH}")

    return 0



if __name__ == "__main__":
    raise SystemExit(main())
