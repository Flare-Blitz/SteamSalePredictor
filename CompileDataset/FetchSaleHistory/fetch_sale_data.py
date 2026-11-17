"""Fetch and persist IsThereAnyDeal sale history for Steam games."""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
METADATA_PATH = PROJECT_ROOT / "CompileDataset" / "FetchGameMetadata" / "game_metadata.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "sale_history.json"
BASE_URL = "https://api.isthereanydeal.com"
ITAD_API_KEY = os.getenv("ITAD_API_KEY")
STEAM_SHOP_ID = 61
COUNTRY = "US"
START_DATE = "2022-01-01T00:00:00Z"
LOOKUP_DATE = "2021-12-31T23:59:59Z"
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_INTERVAL_SECONDS = 0.35
MAX_ATTEMPTS = 3


def load_game_metadata(
    metadata_path: Path = METADATA_PATH,
) -> list[int]:
    """Load and validate only the Steam app IDs from the metadata file."""
    with metadata_path.open(encoding="utf-8") as metadata_file:
        records = json.load(metadata_file)

    if not isinstance(records, list):
        raise ValueError(f"{metadata_path} must contain a JSON list")

    app_ids: list[int] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{metadata_path} contains a non-object record")
        app_id = record.get("app_id")
        if isinstance(app_id, bool) or not isinstance(app_id, int) or app_id <= 0:
            raise ValueError(f"Invalid app_id in {metadata_path}: {app_id!r}")
        app_ids.append(app_id)
    return app_ids


class ITADClient:
    """Fetch ITAD data while spacing requests apart."""

    def __init__(self) -> None:
        self._last_request: float | None = None

    def _request_get(
        self,
        url: str,
        params: dict[str, str],
    ) -> requests.Response:
        """Make a rate-limited GET request with up to three attempts."""
        last_error: requests.RequestException | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            now = time.monotonic()
            if self._last_request is not None:
                elapsed = now - self._last_request
                if elapsed < REQUEST_INTERVAL_SECONDS:
                    time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)

            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                self._last_request = time.monotonic()
                response.raise_for_status()
                return response
            except requests.RequestException as error:
                last_error = error
                if attempt == MAX_ATTEMPTS:
                    raise

        raise RuntimeError("Request failed without an error") from last_error

    def _request_post(
        self,
        url: str,
        params: dict[str, str],
        json_body: list[str],
    ) -> requests.Response:
        """Make a rate-limited POST request with up to three attempts."""
        last_error: requests.RequestException | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            now = time.monotonic()
            if self._last_request is not None:
                elapsed = now - self._last_request
                if elapsed < REQUEST_INTERVAL_SECONDS:
                    time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)

            try:
                response = requests.post(
                    url,
                    params=params,
                    json=json_body,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                self._last_request = time.monotonic()
                response.raise_for_status()
                return response
            except requests.RequestException as error:
                last_error = error
                if attempt == MAX_ATTEMPTS:
                    raise

        raise RuntimeError("Request failed without an error") from last_error

    @staticmethod
    def _require_api_key() -> str:
        if not ITAD_API_KEY:
            raise RuntimeError("ITAD_API_KEY is not set in the environment")
        return ITAD_API_KEY

    def get_id_from_steam_game_id(self, steam_game_id: int) -> str | None:
        """Resolve a Steam app ID to its ITAD game ID."""
        response = self._request_post(
            f"{BASE_URL}/lookup/id/shop/{STEAM_SHOP_ID}/v1",
            {"key": self._require_api_key()},
            [f"app/{steam_game_id}"],
        )
        data = response.json()

        if isinstance(data, dict):
            direct_id = data.get(f"steam:{steam_game_id}")
            if isinstance(direct_id, str):
                return direct_id
            app_id = data.get(f"app/{steam_game_id}")
            if isinstance(app_id, str):
                return app_id
            game = data.get("game")
            if isinstance(game, dict) and isinstance(game.get("id"), str):
                return game["id"]
        return None

    def get_price_history(
        self,
        game_id: str,
        country: str = COUNTRY,
    ) -> list[dict[str, Any]]:
        """Fetch Steam price changes at or after January 1, 2022."""
        response = self._request_get(
            f"{BASE_URL}/games/history/v2",
            {
                "key": self._require_api_key(),
                "id": game_id,
                "country": country,
                "shops": str(STEAM_SHOP_ID),
                "since": LOOKUP_DATE,
            },
        )
        data = response.json()

        if isinstance(data, list):
            history = data
        elif isinstance(data, dict) and isinstance(data.get("data"), list):
            history = data["data"]
        else:
            raise ValueError("ITAD returned an invalid price-history response")

        start_datetime = datetime.fromisoformat(START_DATE.replace("Z", "+00:00"))
        filtered_history: list[dict[str, Any]] = []
        for entry in history:
            if not isinstance(entry, dict) or not isinstance(entry.get("timestamp"), str):
                continue
            try:
                timestamp = datetime.fromisoformat(
                    entry["timestamp"].replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if timestamp >= start_datetime:
                filtered_history.append(entry)
        return filtered_history


def write_history(
    records: list[dict[str, Any]],
    output_path: Path = OUTPUT_PATH,
) -> None:
    """Write all collected records as one JSON array."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    temporary_path.replace(output_path)


def collect_sale_history(
    metadata_path: Path = METADATA_PATH,
    output_path: Path = OUTPUT_PATH,
) -> list[dict[str, Any]]:
    """Append one complete sale-history array for each metadata app ID."""
    metadata = load_game_metadata(metadata_path)
    records: list[dict[str, Any]] = []
    failed_fetches: list[int] = []
    client = ITADClient()

    for index, app_id in enumerate(metadata, start=1):
        try:
            itad_game_id = client.get_id_from_steam_game_id(app_id)
            if itad_game_id is None:
                raise LookupError(f"ITAD game ID not found for Steam app {app_id}")
            history = client.get_price_history(itad_game_id)
        except (LookupError, OSError, requests.RequestException, ValueError) as error:
            print(f"Failed app {app_id}: {error}")
            failed_fetches.append(app_id)
            history = []

        records.append({"app_id": app_id, "sale_history": history})
        print(f"Processed {index}/{len(metadata)}: app_id={app_id}")

    write_history(records, output_path)
    print(f"Failed_fetches: {failed_fetches}")
    return records


def main() -> int:
    records = collect_sale_history()
    print(f"Wrote {len(records)} records to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())