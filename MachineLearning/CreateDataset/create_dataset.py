"""T."""

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = PROJECT_ROOT / "CompileDataset/FetchGameMetadata/game_metadata.json"
SALE_HISTORY_PATH = PROJECT_ROOT / "CompileDataset/FetchSaleHistory/sale_history.json"

# List was obtained from https://fredericksen.substack.com/p/steam-video-game-ratings-and-mature
CONTENT_DESCRIPTORS = {
    1: "some_nudity",
    2: "frequent_violence",
    3: "adult_only",
    4: "frequent_nudity",
    5: "general_mature"
}

def extract_metadata(row: pd.Series) -> dict:
    """Extract the relevant metadata fields from a row of the merged dataset."""
    release_date = row.get("release_date")
    release_year = None
    release_month = None
    release_day = None
    if isinstance(release_date, str):
        try:
            parsed_release_date = datetime.strptime(
                release_date.strip(),
                "%Y-%m-%d",
            )
        except ValueError:
            parsed_release_date = None
        if parsed_release_date is not None:
            release_year = parsed_release_date.year
            release_month = parsed_release_date.month
            release_day = parsed_release_date.day

    metadata = {
        "app_id": row.get("app_id"),
        "name": row.get("name"),
        "price": row.get("price"),
        "currency": row.get("currency"),
        "coming_soon": row.get("coming_soon"),
        "publisher_game_count": row.get("publisher_game_count"),
        "release_year": release_year,
        "release_month": release_month,
        "release_day": release_day,
    }

    for field, prefix in (
        ("categories", "category"),
        ("genres", "genre"),
    ):
        values = row.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            description = value.get("description")
            if not isinstance(description, str) or not description.strip():
                continue
            column_name = re.sub(
                r"[^a-z0-9]+",
                "_",
                description.strip().lower(),
            ).strip("_")
            if column_name:
                metadata[f"{prefix}_{column_name}"] = 1

    content_descriptors = row.get("content_descriptors")
    if isinstance(content_descriptors, list):
        for descriptor in content_descriptors:
            if not isinstance(descriptor, int):
                continue
            metadata[f"content_descriptor_{CONTENT_DESCRIPTORS[descriptor]}"] = 1

    return metadata

def extract_sale_history(
    history: list[dict],
    index: int
) -> dict:
    """Extract summary features and the target for one sale-history entry."""
    if not 0 <= index < len(history):
        raise ValueError("index must refer to an entry in sale_history")

    def timestamp_for(history_index: int) -> datetime | None:
        timestamp = history[history_index].get("timestamp")
        if not isinstance(timestamp, str):
            return None
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    def discount_for(history_index: int) -> float | None:
        deal = history[history_index].get("deal")
        if not isinstance(deal, dict):
            return None
        discount = deal.get("cut")
        if isinstance(discount, bool) or not isinstance(discount, (int, float)):
            return None
        return float(discount)

    # If there are no previous sales, use the release date as the starting
    # point for calculating the time between sales.
    release_date = timestamp_for(-1)

    previous_sales = [
        previous_index
        for previous_index in range(index + 1, len(history))
        if (discount := discount_for(previous_index)) is not None
        and discount >= 20
    ]
    previous_discounts = [
        discount
        for previous_index in previous_sales
        if (discount := discount_for(previous_index)) is not None
    ]
    previous_timestamps = [
        timestamp
        for previous_index in previous_sales
        if (timestamp := timestamp_for(previous_index)) is not None
    ]

    intervals = [
        abs((current - previous).total_seconds()) / 86400
        for current, previous in zip(
            previous_timestamps,
            previous_timestamps[1:],
        )
    ]

    previous_discount_length = None
    if previous_sales:
        previous_sale_index = previous_sales[0]
        previous_sale_start = timestamp_for(previous_sale_index)
        previous_sale_end = (
            timestamp_for(previous_sale_index - 1)
            if previous_sale_index > 0
            else None
        )
        if previous_sale_start is not None and previous_sale_end is not None:
            previous_discount_length = (
                previous_sale_end - previous_sale_start
            ).total_seconds() / 86400

    target_days = None
    if previous_sales:
        previous_sale_index = previous_sales[0]
        previous_sale_end = (
            timestamp_for(previous_sale_index - 1)
            if previous_sale_index > 0
            else None
        )
        current_sale_start = timestamp_for(index)
        if previous_sale_end is not None and current_sale_start is not None:
            target_days = (
                current_sale_start - previous_sale_end
            ).total_seconds() / 86400
    else:
        current_sale_start = timestamp_for(index)
        if release_date is not None and current_sale_start is not None:
            target_days = (
                current_sale_start - release_date
            ).total_seconds() / 86400

    return {
        "sales_since_cutoff": len(previous_sales),
        "last_sale_year": previous_timestamps[0].year
            if previous_timestamps else release_date.year if release_date else None,
        "last_sale_month": previous_timestamps[0].month
            if previous_timestamps else release_date.month if release_date else None,
        "last_sale_day": previous_timestamps[0].day
            if previous_timestamps else release_date.day if release_date else None,
        "average_time_between_sales": (
            sum(intervals) / len(intervals) if intervals else None
        ),
        "average_discount": (
            sum(previous_discounts) / len(previous_discounts)
            if previous_discounts
            else None
        ),
        "max_discount": max(previous_discounts)
            if previous_discounts
            else None,
        "last_discount": previous_discounts[0]
            if previous_discounts
            else None,
        "previous_discount_length": previous_discount_length,
        "has_previous_sale": int(bool(previous_sales)),
        "target_days": target_days,
    }

def calculate_game_data(row: pd.Series) -> list[dict]:
    """Return up to 10 rows of the 10 previous sales for the game.
    Include the general game metadata
    """

    metadata = extract_metadata(row)

    sale_data = []
    history = row.get("sale_history")
    if not isinstance(history, list):
        return []

    for i, sale in enumerate(history):
        if len(sale_data) >= 10:
            break

        deal = sale.get("deal")
        cut = deal.get("cut") if isinstance(deal, dict) else None
        if isinstance(cut, (int, float)) and not isinstance(cut, bool) and cut >= 20:
            sale_data.append(
                metadata
                | extract_sale_history(
                    history,
                    i
                )
            )

    if not sale_data:
        return []

    return sale_data

def create_dataset():
    """Combine the data from the game metadata and sale history into a single dataset."""
    # Load the metadata and sale history
    metadata = pd.read_json(METADATA_PATH, orient="records")
    sale_history = pd.read_json(SALE_HISTORY_PATH, orient="records")

    # Merge the metadata and sale history on app_id
    merged_data = pd.merge(metadata, sale_history, on="app_id", how="left")

    game_rows = []
    for _, row in merged_data.iterrows():
        game_rows.extend(calculate_game_data(row))

    dataset = pd.DataFrame(game_rows)

    # Grab all one-hot encoded columns
    one_hot_columns = [
        column for column in dataset.columns
        if column.startswith(("category_", "genre_", "content_descriptor_"))
    ]
    # These columns should be filled with 0s, if they are missing
    dataset[one_hot_columns] = dataset[one_hot_columns].fillna(0).astype("int8")

    dataset.to_csv("MachineLearning/CreateDataset/sale_dataset.csv", index=False)

if __name__ == "__main__":
    create_dataset()