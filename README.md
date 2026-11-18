# SteamSalePredictor
The objective of this project is to create a nn model that can accurately predict the number of days from the end of the last sale of a steam game until the next one.

# File Architecture
An outline of all folders, and the contained files
- GameListDataset: This is where the Kaggle library steam_games.csv goes
- CompileDataset: Directory for fetching the data from the external sources
  - CreateGameList: Directory for querying the Kaggle dataset
    - compile_game_list.py: queries steam_games.csv and outputs a list of 1000 games
    - grouped_sample.csv: List of 1000 games
  - Fetch Game Metadata: Directory for querying the Steam API
    - fetch_game_metadata.py: Sends an API request to Steam to get metadata for each game in grouped_sample.csv
    - game_metadata.json: Stores important Steam game metadata
  - Fetch Sale History: directory for fetching steam game sales
    - fetch_sale_data.py: Takes each steam game in game_metadata.json and fetches all sale data up to January 1st 2022. Generates sale_history.json
    - sale_history_example.json: Example of the first 3 games for sale_history.json. Used due to sale_history.json's large file size
- MachineLearning: Directory contains the machine learning code
  - CreateDataset: Directory for assembling a completed dataset with some pre-processing
    - create_dataset.py: Creates the dataset used to train the models. Saves dataset to sale_dataset.csv
  - ModelRunning: Directory for running the model cleaning, analysis, and creation code
    - data_cleaning.ipynb: Notebook used to perform data analysis, cleaning, model creation, and evaluation.


# Data Collection

The first step of this game is to collect the desired data for each game. 

## Required Setup to collect data

### API Key Required
This project useds the IsThereAnyDeal API to collect steam sale history.
To use it, create a .env file that is a copy of .env.example, and replace
ITAD_API_KEY value with an API key obtained from IsThereAnyDeal.com

### Kaggle Dataset used
There are over 100,000 games on steam, and querying each one via the Steam API
would provide a too many requests error. Insead, I am using a kaggle dataset found here: https://www.kaggle.com/datasets/fronkongames/steam-games-dataset
Its over 1 GB, so it is not stored in the Git repo. I used this to filter down the list of steam games to a more reasonable 1000.

## Fetch list of games
First, I needed compile a list of 1000 games. To perform this, rather than use a large amount of queries to the Steam store API key for the metadata of every game, which would take a very long time due to rate limiting, I decided it would be better to use a pre-assembled Kaggle dataset of all Steam games. This dataset has a few mistakes, and is missing data I would desire, but it will work for assembling a list of games before I fetch the metadata for each game.

`CompileDataset/CreateGameList/compile_game_list.py` queries the kaggle database, which is stored in `GameListDataset/steam_games.csv`, and groups the data by several different categories. It groups the data by price range, release date range, and the range of how many games their publisher made. The data is grouped to ensure diversity in the games selected. Then, steam games for each category are randomly sampled from the kaggle dataset, while ensuring that each group has representation proportional to how many games are in that group, with a minimum of 3 games per group. The game IDs, and the group information for auditing purposes, are stored in `grouped_sample.csv`

## Grab game metadata
Now that a list of steam games has been compiled, updated metadata for each game needs to be fetched. `CompileDataset/FetchGameMetadata/fetch_game_metadata.py` goes through each app_id in grouped_sample, and queries the steampowered api to fetch the metadata for each game. The program only performs 1 query per 2 seconds, to prevent potential rate limiting. https://steamcommunity.com/dev/apiterms

## Fetch sale history
The steam metadata doesn't contain the sale history of the game, so the IsThereAnyDeal API needs to be queried to fetch all of the sale history. For each steam game, I query ITAD API for the ITAD_ID for that game, then query the API for the sale history of the game, up to January 1st, 2022. The complete response is stored in sale_history.json. the file size is too large to put on the github, so you can either run the code yourself to see the file (it will take several minutes), or you can see an example of the first 3 rows fetched in sale_history_example.json.

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