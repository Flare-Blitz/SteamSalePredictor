import os
import requests
from dotenv import load_dotenv

load_dotenv()
ITAD_API_KEY = os.getenv("ITAD_API_KEY")

BASE_URL = "https://api.isthereanydeal.com"

def get_game_id(title: str) -> str | None:
    """Finds the internal ITAD UUID for a given game title."""
    url = f"{BASE_URL}/games/lookup/v1"
    params = {
        "key": ITAD_API_KEY,
        "title": title
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    # lookup/v1 returns game details if found (including 'id') or null/empty
    if data and "game" in data and data["game"]:
        return data["game"]["id"]
    return None

def get_price_history(game_id: str, country: str = "US", limit: int = 10):
    """Fetches the price change history log for a game ID."""
    url = f"{BASE_URL}/games/history/v2"
    params = {
        "key": ITAD_API_KEY,
        "id": game_id,
        "country": country
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    history_entries = response.json()
    return history_entries

def get_shops() -> dict:
    """Fetches the list of shops from ITAD."""
    url = f"{BASE_URL}/service/shops/map/v1"
    params = {
        "key": ITAD_API_KEY
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    shops_data = response.json()
    print(shops_data)  # Debugging: print the raw response
    return shops_data.get("data", {}).get("shops", {})

if __name__ == "__main__":

    shops = get_shops()
    print(shops)

    # game_title = "Hollow Knight"
    # print(f"Searching for ID: {game_title}...")

    # game_id = get_game_id(game_title)
    # if not game_id:
    #     print("Game not found.")
    #     exit()

    # print(f"Found Game ID: {game_id}")
    # print(f"Fetching price history...\n")

    # history = get_price_history(game_id, country="US", limit=10)

    # for entry in history:
    #     timestamp = entry.get("timestamp")
    #     shop = entry.get("shop", {}).get("name", "Unknown Shop")
    #     deal = entry.get("deal", {})
    #     price = deal.get("price", {}).get("amount")
    #     currency = deal.get("price", {}).get("currency")
    #     cut = deal.get("cut", 0)

    #     print(f"[{timestamp}] {shop}: {price} {currency} (-{cut}%)")