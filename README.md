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

### ItThereAnyDeal API
Docs Site: https://docs.isthereanydeal.com/