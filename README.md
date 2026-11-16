# SteamSalePredictor
The objective of this project is to create a nn model that can accurately predict how long until the steam game goes on sale.

# Setup

## Data Collection
This project useds the IsThereAnyDeal API to collect steam sale history.
To use it, create a .env file that is a copy of .env.example, and replace
ITAD_API_KEY value with an API key obtained from IsThereAnyDeal.com

### Kaggle Dataset used
There are over 100,000 games on steam, and querying each one via the Steam API
would provide a too many requests error. Insead, I am using a kaggle dataset found here: https://www.kaggle.com/datasets/fronkongames/steam-games-dataset
Its over 1 GB, so it is not stored in the Git repo. I used this to filter down the list of steam games to a more reasonable 1000.

### Steam game metadata
Fetch current metadata for each app in `CompileDataset/CreateGameList/grouped_sample.csv`:

```bash
python CompileDataset/FetchGameMetadata/fetch_game_metadata.py
```

The script writes `CompileDataset/FetchGameMetadata/game_metadata.json` as a JSON
list, preserving the input order and `publisher_game_count`. It fetches each
app's list price and the currency Steam returns, without currency conversion or
a forced country. The numeric `price` is the API's `initial` amount divided by
100. The output includes Steam's content-descriptor notes as a string array.
Free games remain in the output with null `price` and `currency`; their app IDs
are printed. Failed requests are retried up to three times, each
attempt is spaced at least two seconds from the previous request, and the
affected record is retained with a `fetch_error` field.

### ItThereAnyDeal API
Docs Site: https://docs.isthereanydeal.com/