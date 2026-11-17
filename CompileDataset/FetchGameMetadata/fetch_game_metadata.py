"""Fetch Steam appdetails metadata for the grouped game sample."""

import csv
import json
import time
from datetime import datetime
from http.client import HTTPException
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "CompileDataset" / "CreateGameList" / "grouped_sample.csv"
OUTPUT_PATH = Path(__file__).resolve().parent / "game_metadata.json"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails?l=english&cc=us&"
REQUEST_TIMEOUT_SECONDS = 15
REQUEST_INTERVAL_SECONDS = 2.0
MAX_ATTEMPTS = 3
USER_AGENT = "SteamSalePredictor/1.0"

def fetch_appdetails_payload(app_id: int) -> object:
    """Request and decode one Steam appdetails response."""
    url = f"{APPDETAILS_URL}{urlencode({'appids': app_id})}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def load_source_rows(input_path: Path = INPUT_PATH) -> list[dict[str, int]]:
    """Load app IDs and publisher game counts without reading the full dataset."""
    with input_path.open(encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        required_columns = {"app_id", "publisher_game_count"}
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"{input_path} is missing required columns: {missing}")

        rows: list[dict[str, int]] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                app_id = int(row["app_id"])
                publisher_game_count = int(row["publisher_game_count"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid app_id or publisher_game_count on CSV line {line_number}"
                ) from error
            if app_id <= 0 or publisher_game_count < 0:
                raise ValueError(f"Invalid values on CSV line {line_number}")
            rows.append(
                {
                    "app_id": app_id,
                    "publisher_game_count": publisher_game_count,
                }
            )
    return rows


def parse_exact_release_date(value: object) -> str | None:
    """Return an ISO date only when Steam's release-date text is exact."""
    if not isinstance(value, str):
        return None
    for date_format in ("%Y-%m-%d", "%b %d, %Y", "%d %b, %Y"):
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _record_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {"id": item["id"], "description": item["description"]}
        for item in value
        if isinstance(item, dict)
        and "id" in item
        and isinstance(item.get("description"), str)
    ]


def _content_descriptors(data: dict[str, Any]) -> list[str]:
    descriptors = data.get("content_descriptors")
    if not isinstance(descriptors, dict):
        return []
    notes = descriptors.get("notes")
    if not isinstance(notes, list):
        return []
    return [note for note in notes if isinstance(note, str)]


def _price_fields(data: dict[str, Any]) -> tuple[float | None, str | None]:
    if data.get("is_free") is True:
        return None, None
    price_overview = data.get("price_overview")
    if not isinstance(price_overview, dict):
        return None, None
    initial = price_overview.get("initial")
    currency = price_overview.get("currency")
    if isinstance(initial, bool) or not isinstance(initial, (int, float)):
        return None, None
    if not isinstance(currency, str) or not currency:
        return None, None
    return initial / 100, currency


def normalize_game(
    app_id: int,
    publisher_game_count: int,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Select and normalize the metadata fields used by the sale checker."""
    release_info = data.get("release_date")
    if not isinstance(release_info, dict):
        release_info = {}
    release_date_text = release_info.get("date")
    if not isinstance(release_date_text, str) or not release_date_text.strip():
        release_date_text = None

    price, currency = _price_fields(data)
    name = data.get("name")
    if not isinstance(name, str) or not name:
        name = None

    return {
        "name": name,
        "app_id": app_id,
        "release_date": parse_exact_release_date(release_date_text),
        "release_date_text": release_date_text,
        "coming_soon": (
            release_info.get("coming_soon")
            if isinstance(release_info.get("coming_soon"), bool)
            else None
        ),
        "price": price,
        "currency": currency,
        "content_descriptors": _content_descriptors(data),
        "categories": _record_list(data.get("categories")),
        "genres": _record_list(data.get("genres")),
        "publisher_game_count": publisher_game_count,
    }


class SteamAppDetailsClient:
    """Fetch appdetails while spacing every request attempt by at least two seconds."""

    def __init__(
        self,
        fetch_payload: Callable[[int], object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        request_interval: float = REQUEST_INTERVAL_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        if request_interval < 0:
            raise ValueError("request_interval cannot be negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._fetch_payload = fetch_payload or fetch_appdetails_payload
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._request_interval = request_interval
        self._max_attempts = max_attempts
        self._last_request_started: float | None = None

    def _wait_for_request_slot(self) -> None:
        """Sleep until at least request_interval seconds have passed since the last request."""
        now = self._monotonic()
        if self._last_request_started is not None:
            remaining = self._request_interval - (
                now - self._last_request_started
            )
            if remaining > 0:
                self._sleeper(remaining)
                now = self._monotonic()
        self._last_request_started = now

    def fetch(self, app_id: int) -> tuple[dict[str, Any] | None, str | None]:
        """Return appdetails data or a useful failure message."""
        for attempt in range(1, self._max_attempts + 1):
            self._wait_for_request_slot()
            try:
                payload = self._fetch_payload(app_id)
            except (
                URLError,
                TimeoutError,
                OSError,
                HTTPException,
                ValueError,
            ) as error:
                if attempt == self._max_attempts:
                    return None, str(error) or type(error).__name__
                continue

            if not isinstance(payload, dict):
                return None, "Steam returned an invalid response"
            app_result = payload.get(str(app_id))
            if not isinstance(app_result, dict):
                return None, "Steam response did not contain the requested app ID"
            if app_result.get("success") is not True:
                return None, "Steam appdetails returned success=false"
            data = app_result.get("data")
            if not isinstance(data, dict):
                return None, "Steam appdetails response had no data object"
            return data, None

        return None, "Steam appdetails request failed"


class AppDetailsFetcher(Protocol):
    def fetch(self, app_id: int) -> tuple[dict[str, Any] | None, str | None]:
        """Return appdetails data or a useful failure message."""
        ...


def _unavailable_record(
    app_id: int,
    publisher_game_count: int,
    error: str,
) -> dict[str, Any]:
    record = normalize_game(app_id, publisher_game_count, {})
    record["fetch_error"] = error
    return record


def collect_metadata(
    source_rows: list[dict[str, int]],
    client: AppDetailsFetcher
) -> tuple[list[dict[str, Any]], list[int]]:
    """Fetch each source row, retaining free and failed apps in the output."""
    records: list[dict[str, Any]] = []
    failed_app_ids: list[int] = []

    for fetched_count, source_row in enumerate(source_rows, start=1):
        app_id = source_row["app_id"]
        publisher_game_count = source_row["publisher_game_count"]
        data, error = client.fetch(app_id)
        if error is not None or data is None:
            failed_app_ids.append(app_id)
            records.append(
                _unavailable_record(app_id, publisher_game_count, error or "No data")
            )
        else:
            records.append(normalize_game(app_id, publisher_game_count, data))
        if fetched_count % 50 == 0:
            # Display prgoress every 50 games fetched
            print(
                f"Fetched {fetched_count}/{len(source_rows)} games "
                f"({len(failed_app_ids)} failures)"
            )

    return records, failed_app_ids


def write_metadata(records: list[dict[str, Any]], output_path: Path = OUTPUT_PATH) -> None:
    """Write the normalized records as a UTF-8 JSON list."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def main() -> int:
    source_rows = load_source_rows()
    records, failed_app_ids = collect_metadata(
        source_rows,
        SteamAppDetailsClient(),
    )
    write_metadata(records)
    print(f"Wrote {len(records)} records to {OUTPUT_PATH}")
    if failed_app_ids:
        print(
            "Metadata fetch failed for app IDs: "
            + ", ".join(map(str, failed_app_ids))
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
